## ---------------------------------------------------------------------------
## Multi-stream discrete-time hazard tables for first-salmon-arrival
##
## One hazard table per stream. Each row is a (year, day) on which fish had NOT
## yet arrived, up to and including the arrival day; `arrived` is the target.
## Every predictor uses only information available on or before that day.
##
##   gh_raw()             GitHub blob/raw page URL -> raw file URL
##   read_salmon()        salmon CSV  -> one row per year with arrival date
##   read_flow()          WSC CSV     -> gap-free daily discharge series
##   check_coverage()     per-year flow gaps for one stream
##   build_hazard_data()  join into one stream's hazard table
##   build_streams()      run the whole pipeline over a table of streams
##
## Base R only.
## ---------------------------------------------------------------------------

## --- stream registry -------------------------------------------------------
##
## One row per stream. `flow_url` must point at that stream's own WSC gauge --
## Chemainus is 08HA001, Cowichan 08HA011, etc. Fill these in; a stream with
## flow_url = NA is reported as skipped rather than silently paired with the
## wrong river.
STREAMS <- data.frame(
  stream = c("CHEMAINUS RIVER", "COWICHAN RIVER",
             "LITTLE QUALICUM RIVER", "NANAIMO RIVER"),
  salmon_url = c(
    "https://raw.githubusercontent.com/oceanhackweek/ohw26_proj_fishyG/76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Salmon%20Data/CHEMAINUS%20RIVER_salmon_data.csv",
    "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/Salmon%20Data/COWICHAN%20RIVER_salmon_data.csv",
    "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/717e8ce794b893b458ed9e5f27de7ec15062af90/data/Salmon%20Data/LITTLE%20QUALICUM%20RIVER_salmon_data.csv",
    "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/717e8ce794b893b458ed9e5f27de7ec15062af90/data/Salmon%20Data/NANAIMO%20RIVER_salmon_data.csv"),
  flow_url = c(
    "https://raw.githubusercontent.com/oceanhackweek/ohw26_proj_fishyG/76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Chemanius_Riv_Flow.csv",
    "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/Cowichan_Riv_Flow.csv",
    "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/LilQualicum_Riv_Flow.csv",
    "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/Nanaimo_Riv_Flow.csv"),
  stringsAsFactors = FALSE
)


## --- URL handling ----------------------------------------------------------
##
## A github.com/.../blob/... URL serves an HTML page, not the file. Reading one
## with read.csv produces confusing parse errors rather than an honest failure,
## so convert first.
gh_raw <- function(url) {
  sub("^https://github\\.com/([^/]+)/([^/]+)/(?:blob|raw)/",
      "https://raw.githubusercontent.com/\\1/\\2/", url)
}

## Stream name from a salmon filename, if not supplied explicitly.
stream_from_url <- function(url) {
  base <- utils::URLdecode(basename(url))
  trimws(sub("_salmon_data\\.csv$", "", base, ignore.case = TRUE))
}

## Fail early and clearly if a URL served a web page instead of a CSV.
assert_not_html <- function(lines, url) {
  if (length(lines) && grepl("^\\s*(<!DOCTYPE|<html)", lines[1], ignore.case = TRUE))
    stop("got an HTML page, not a CSV, from:\n  ", url,
         "\nUse the raw file URL (gh_raw() converts blob URLs).")
  invisible(TRUE)
}


## --- generic helpers -------------------------------------------------------

parse_dates_flex <- function(x) {
  x <- trimws(as.character(x))
  x[x == "" | x %in% c("NA", "NULL", "N/A", "-")] <- NA
  x <- sub("[ T].*$", "", x)
  fmts <- c("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
            "%d-%b-%y", "%d-%b-%Y", "%b %d, %Y", "%Y%m%d")
  best <- as.Date(rep(NA, length(x))); best_n <- -1L
  for (f in fmts) {
    d <- suppressWarnings(as.Date(x, format = f))
    n <- sum(!is.na(d))
    if (n > best_n) { best <- d; best_n <- n }
  }
  best
}

## Causal trailing mean: today plus the previous k-1 days. NA-tolerant.
roll_mean_causal <- function(x, k) {
  n <- length(x)
  xx <- ifelse(is.na(x), 0, x); ok <- as.numeric(!is.na(x))
  cs <- c(0, cumsum(xx)); cn <- c(0, cumsum(ok))
  i <- seq_len(n); lo <- pmax(i - k, 0)
  s <- cs[i + 1] - cs[lo + 1]; cnt <- cn[i + 1] - cn[lo + 1]
  ifelse(cnt == 0, NA_real_, s / cnt)
}

days_since_above <- function(x, thr) {
  last <- NA_integer_; out <- integer(length(x))
  for (i in seq_along(x)) {
    if (!is.na(x[i]) && x[i] >= thr) last <- i
    out[i] <- if (is.na(last)) NA_integer_ else i - last
  }
  out
}

pick_col <- function(nms, patterns) {
  for (p in patterns) {
    hit <- grep(p, nms, ignore.case = TRUE, value = TRUE)
    if (length(hit)) return(hit[1])
  }
  NA_character_
}

## Remove commas used as digit grouping (12,500 -> 12500). A comma inside an
## unquoted name is deliberately left alone -- that needs quoting, not
## stripping, and is reported instead of silently mangled.
repair_digit_commas <- function(lines) {
  c(lines[1], gsub("(?<=[0-9]),(?=[0-9]{3}([^0-9]|$))", "", lines[-1], perl = TRUE))
}


## --- arrival column interpretation ------------------------------------------
##
## Streams are exported separately and may not agree on format. Handles:
##   "date"   date string                       -> used directly
##   "doy"    day-of-year 1-366                 -> combined with ANALYSIS_YR
##   "offset" days after START_DTT              -> added to parsed START_DTT
##   "excel"  serial number (~20000-60000)      -> days since 1899-12-30
interpret_arrival <- function(x, year, start_dtt = NULL,
                              interpret = "auto", verbose = TRUE,
                              label = "") {
  chr <- trimws(as.character(x))
  chr[chr %in% c("", "NA", "NULL", "N/A", "-")] <- NA
  num     <- suppressWarnings(as.numeric(chr))
  as_date <- parse_dates_flex(chr)
  start   <- if (!is.null(start_dtt)) parse_dates_flex(start_dtt) else NULL
  
  n_num <- sum(!is.na(num)); n_date <- sum(!is.na(as_date))
  fin   <- num[!is.na(num)]
  
  if (identical(interpret, "auto")) {
    interpret <-
      if (n_date > n_num)                        "date"
    else if (!n_num)                           "date"
    else if (all(fin >= 20000 & fin <= 60000)) "excel"
    else if (all(fin >= 1 & fin <= 366) &&
             stats::median(fin) > 100)         "doy"
    else if (!is.null(start) && sum(!is.na(start)) > 0 &&
             all(fin >= 0 & fin <= 400))       "offset"
    else if (all(fin >= 1 & fin <= 366))       "doy"
    else stop("cannot interpret arrival column; sample: ",
              paste(utils::head(chr[!is.na(chr)], 5), collapse = ", "))
  }
  
  out <- switch(interpret,
                date   = as_date,
                doy    = as.Date(paste0(year, "-01-01")) + (num - 1),
                excel  = as.Date(num, origin = "1899-12-30"),
                offset = { if (is.null(start))
                  stop("interpret='offset' needs START_DTT"); start + num },
                stop("unknown interpret: ", interpret))
  
  if (verbose) {
    ok <- sum(!is.na(out))
    msg <- paste0(label, "arrival column read as '", interpret, "' -- ",
                  ok, " of ", length(out), " parsed")
    if (ok) {
      doy <- as.integer(format(out[!is.na(out)], "%j"))
      msg <- paste0(msg, " | doy ", min(doy), "-", max(doy),
                    if (min(doy) < 100 || max(doy) > 366)
                      "  <-- IMPLAUSIBLE, check interpret=" else "")
    }
    message(msg)
  }
  out
}


## --- salmon ----------------------------------------------------------------
read_salmon <- function(path, species = NULL, run_type = NULL,
                        arrival_col = "time_return",
                        interpret   = "auto",
                        verbose     = TRUE,
                        label       = "") {
  
  path  <- gh_raw(path)
  lines <- readLines(path, warn = FALSE)
  assert_not_html(lines, path)
  lines <- lines[nzchar(trimws(lines))]
  if (length(lines) < 2) stop("file has no data rows: ", path)
  
  n_hdr <- length(scan(text = lines[1], what = "", sep = ",", quiet = TRUE))
  nf    <- utils::count.fields(textConnection(lines), sep = ",", quote = "\"")
  
  if (any(nf != n_hdr, na.rm = TRUE)) {
    fixed  <- repair_digit_commas(lines)
    nf_fix <- utils::count.fields(textConnection(fixed), sep = ",", quote = "\"")
    n_bad  <- sum(nf_fix != n_hdr, na.rm = TRUE)
    if (verbose)
      message(label, "repaired ", sum(nf != n_hdr, na.rm = TRUE) - n_bad,
              " malformed line(s)")
    if (n_bad) {
      bad <- which(nf_fix != n_hdr)
      stop(n_bad, " line(s) have the wrong field count, e.g.:\n  ",
           paste(utils::head(fixed[bad], 2), collapse = "\n  "),
           "\nAn unquoted comma inside a text field must be quoted at source.")
    }
    lines <- fixed
  }
  
  s <- read.csv(text = lines, stringsAsFactors = FALSE, check.names = TRUE,
                strip.white = TRUE)
  
  if (!arrival_col %in% names(s))
    stop("arrival column '", arrival_col, "' not found. Have: ",
         paste(names(s), collapse = ", "))
  
  yr_col <- pick_col(names(s), c("^ANALYSIS_YR$", "year", "yr"))
  if (is.na(yr_col)) stop("no year column found")
  s$year <- as.integer(s[[yr_col]])
  
  s$arrival_date <- interpret_arrival(
    s[[arrival_col]], year = s$year,
    start_dtt = if ("START_DTT" %in% names(s)) s$START_DTT else NULL,
    interpret = interpret, verbose = verbose, label = label)
  
  if (!is.null(species) && "SPECIES" %in% names(s))
    s <- s[toupper(trimws(s$SPECIES)) %in% toupper(species), , drop = FALSE]
  if (!is.null(run_type) && "RUN_TYPE" %in% names(s))
    s <- s[toupper(trimws(s$RUN_TYPE)) %in% toupper(run_type), , drop = FALSE]
  if (!nrow(s)) stop("species/run_type filter matched 0 rows")
  
  n_drop <- sum(is.na(s$arrival_date))
  s <- s[!is.na(s$arrival_date) & !is.na(s$year), , drop = FALSE]
  if (!nrow(s)) stop("no rows survived arrival-date parsing")
  if (n_drop && verbose)
    message(label, n_drop, " row(s) dropped for unparseable arrival date")
  
  s$arrival_doy <- as.integer(format(s$arrival_date, "%j"))
  
  off <- s$year != as.integer(format(s$arrival_date, "%Y"))
  if (any(off))
    warning(label, sum(off), " arrival date(s) fall outside ANALYSIS_YR",
            " -- interpretation is probably wrong", call. = FALSE)
  
  ## multiple run types per year: keep the earliest, i.e. FIRST arrival
  s <- s[order(s$year, s$arrival_date), ]
  n_dup <- sum(duplicated(s$year))
  if (n_dup && verbose)
    message(label, n_dup, " duplicate year(s); earliest arrival kept")
  s <- s[!duplicated(s$year), , drop = FALSE]
  
  keep <- intersect(c("year", "arrival_date", "arrival_doy", "SPECIES",
                      "RUN_TYPE", "TOTAL_RETURN_TO_RIVER", "WATERBODY"),
                    names(s))
  out <- s[, keep, drop = FALSE]
  rownames(out) <- NULL
  out
}


## --- flow ------------------------------------------------------------------
##
## WSC daily export. A title banner precedes the real header:
##   Daily Discharge (m3/s) (PARAM = 1) and Daily Water Level (m) (PARAM = 2)
##    ID,PARAM,Date,Value,SYM
## PARAM 1 = discharge (m3/s), 2 = level (m). SYM: E estimated, A partial,
## B ice conditions, D dry, S sample.
.flow_cache <- new.env(parent = emptyenv())

read_flow <- function(path, param = 1, drop_symbols = c("B"),
                      station = NULL, verbose = TRUE, label = "",
                      cache = TRUE) {
  
  path <- gh_raw(path)
  key  <- paste(path, param, paste(drop_symbols, collapse = ""), station)
  if (cache && !is.null(.flow_cache[[key]])) return(.flow_cache[[key]])
  
  lines <- readLines(path, warn = FALSE)
  assert_not_html(lines, path)
  
  hdr_i <- grep("^\\s*ID\\s*,\\s*PARAM\\s*,", lines)[1]
  if (is.na(hdr_i)) stop("no 'ID,PARAM,Date,Value,SYM' header line in ", path)
  
  f <- read.csv(text = lines[hdr_i:length(lines)], stringsAsFactors = FALSE,
                strip.white = TRUE, colClasses = "character",
                check.names = FALSE)
  if (ncol(f) != 5)
    stop("expected 5 WSC columns, got ", ncol(f))
  names(f) <- c("ID", "PARAM", "Date", "Value", "SYM")
  
  ids <- unique(trimws(f$ID))
  if (!is.null(station)) {
    f <- f[trimws(f$ID) == station, , drop = FALSE]
    if (!nrow(f))
      stop("station '", station, "' not in file; present: ",
           paste(ids, collapse = ", "))
  } else if (length(ids) > 1) {
    warning(label, "multiple stations in one file (",
            paste(ids, collapse = ", "), "); pass station= to select one",
            call. = FALSE)
  }
  
  n_all <- nrow(f)
  f <- f[suppressWarnings(as.numeric(f$PARAM)) == param, , drop = FALSE]
  
  out <- data.frame(date = as.Date(f$Date, format = "%Y/%m/%d"),
                    flow = suppressWarnings(as.numeric(f$Value)),
                    sym  = trimws(f$SYM), stringsAsFactors = FALSE)
  out <- out[!is.na(out$date), , drop = FALSE]
  if (!nrow(out)) stop("no rows with PARAM == ", param, " in ", path)
  
  n_flag <- 0L
  if (length(drop_symbols)) {
    hit <- out$sym %in% drop_symbols
    n_flag <- sum(hit & !is.na(out$flow))
    out$flow[hit] <- NA_real_
  }
  
  out <- out[order(out$date), ]
  out <- out[!duplicated(out$date), , drop = FALSE]
  
  ## gap-free daily grid so rolling windows mean what they say
  full <- data.frame(date = seq(min(out$date), max(out$date), by = "day"))
  out  <- merge(full, out, by = "date", all.x = TRUE)
  out  <- out[order(out$date), ]
  rownames(out) <- NULL
  attr(out, "station") <- if (!is.null(station)) station else ids[1]
  
  if (verbose)
    message(sprintf("%sflow [%s]: %s rows -> %s days | %s to %s | %.1f%% missing%s",
                    label, attr(out, "station"), n_all, nrow(out),
                    min(out$date), max(out$date), 100 * mean(is.na(out$flow)),
                    if (n_flag) sprintf(" | %s blanked as [%s]", n_flag,
                                        paste(drop_symbols, collapse = "")) else ""))
  
  if (cache) assign(key, out, envir = .flow_cache)
  out
}


## --- coverage --------------------------------------------------------------
check_coverage <- function(salmon, flow, start_doy = 152, max_gap = 10) {
  if (!nrow(salmon)) stop("check_coverage(): salmon has 0 rows")
  flow$year <- as.integer(format(flow$date, "%Y"))
  flow$doy  <- as.integer(format(flow$date, "%j"))
  
  do.call(rbind, lapply(seq_len(nrow(salmon)), function(i) {
    yr <- salmon$year[i]; adt <- salmon$arrival_date[i]
    d <- flow[flow$year == yr & flow$doy >= start_doy & flow$date <= adt, ,
              drop = FALSE]
    data.frame(year = yr, arrival_date = adt,
               arrival_doy  = salmon$arrival_doy[i],
               window_days  = nrow(d),
               missing_flow = sum(is.na(d$flow)),
               pct_missing  = if (nrow(d)) round(100*mean(is.na(d$flow)),1) else NA,
               usable = nrow(d) > 0 && sum(is.na(d$flow)) <= max_gap,
               stringsAsFactors = FALSE)
  }))
}


## --- hazard table ----------------------------------------------------------
##
## start_doy = "auto" sets the window to open `auto_buffer` days before the
## earliest observed arrival for that stream, floored at 1. Different rivers
## run at different times, so a single fixed value across streams either wastes
## rows or truncates real arrivals.
build_hazard_data <- function(salmon, flow,
                              start_doy   = "auto",
                              auto_buffer = 30,
                              high_flow_q = 0.75,
                              max_gap     = 10,
                              min_jan_jun_days = 120,
                              stream      = NA_character_,
                              verbose     = TRUE,
                              label       = "") {
  
  if (identical(start_doy, "auto"))
    start_doy <- max(1L, min(salmon$arrival_doy, na.rm = TRUE) - auto_buffer)
  if (verbose) message(label, "start_doy = ", start_doy)
  
  flow <- flow[order(flow$date), ]
  flow$year <- as.integer(format(flow$date, "%Y"))
  flow$doy  <- as.integer(format(flow$date, "%j"))
  
  flow$flow_7d  <- roll_mean_causal(flow$flow, 7)
  flow$flow_14d <- roll_mean_causal(flow$flow, 14)
  flow$flow_30d <- roll_mean_causal(flow$flow, 30)
  flow$flow_delta_14d <- flow$flow_7d - flow$flow_14d
  
  ## threshold is per-stream: rivers differ in magnitude by orders of magnitude
  thr <- stats::quantile(flow$flow, high_flow_q, na.rm = TRUE)
  flow$days_since_high_flow <- unlist(
    lapply(split(flow$flow, flow$year), days_since_above, thr = thr),
    use.names = FALSE)
  
  flow <- do.call(rbind, lapply(split(flow, flow$year), function(d) {
    d <- d[order(d$doy), ]
    v <- ifelse(is.na(d$flow), 0, d$flow); v[d$doy < start_doy] <- 0
    d$flow_cum_since_start <- cumsum(v)
    jj <- d$flow[d$doy <= 181]
    d$jan_jun_mean_flow <- if (sum(!is.na(jj)) >= min_jan_jun_days)
      mean(jj, na.rm = TRUE) else NA_real_
    d
  }))
  rownames(flow) <- NULL
  
  skipped <- character(0)
  rows <- lapply(seq_len(nrow(salmon)), function(i) {
    yr <- salmon$year[i]; adt <- salmon$arrival_date[i]
    fy <- flow[flow$year == yr, , drop = FALSE]
    if (!nrow(fy)) { skipped <<- c(skipped, paste0(yr, ":no flow")); return(NULL) }
    if (salmon$arrival_doy[i] < start_doy) {
      skipped <<- c(skipped, paste0(yr, ":arrival before start_doy")); return(NULL)
    }
    d <- fy[fy$doy >= start_doy & fy$date <= adt, , drop = FALSE]
    if (!nrow(d)) { skipped <<- c(skipped, paste0(yr, ":empty window")); return(NULL) }
    gaps <- sum(is.na(d$flow))
    if (gaps > max_gap) {
      skipped <<- c(skipped, paste0(yr, ":", gaps, " missing")); return(NULL)
    }
    data.frame(stream = stream, year = yr, date = d$date, doy = d$doy,
               days_at_risk = seq_len(nrow(d)),
               arrived = as.integer(d$date == adt),
               flow = d$flow, flow_7d = d$flow_7d, flow_14d = d$flow_14d,
               flow_30d = d$flow_30d, flow_delta_14d = d$flow_delta_14d,
               flow_cum_since_start = d$flow_cum_since_start,
               days_since_high_flow = d$days_since_high_flow,
               jan_jun_mean_flow = d$jan_jun_mean_flow,
               n_missing_flow = gaps, stringsAsFactors = FALSE)
  })
  
  out <- do.call(rbind, rows)
  if (is.null(out))
    stop("no usable years from ", nrow(salmon), " salmon row(s). Skips: ",
         paste(utils::head(skipped, 8), collapse = "; "))
  if (length(skipped) && verbose)
    message(label, length(skipped), " year(s) skipped: ",
            paste(utils::head(skipped, 6), collapse = "; "),
            if (length(skipped) > 6) " ..." else "")
  
  rownames(out) <- NULL
  attr(out, "start_doy") <- start_doy
  attr(out, "high_flow_threshold") <- unname(thr)
  out[order(out$year, out$date), ]
}


## --- run every stream ------------------------------------------------------
##
## Returns a named list of hazard tables, one per stream. A per-stream failure
## is recorded, not thrown, so one bad file cannot kill the batch.
## attr(result, "status") holds the summary; attr(result, "combined") stacks
## every table with a `stream` column.
build_streams <- function(streams = STREAMS, species = NULL, run_type = NULL,
                          arrival_col = "time_return", interpret = "auto",
                          start_doy = "auto", verbose = TRUE, ...) {
  
  need <- c("salmon_url", "flow_url")
  if (!all(need %in% names(streams)))
    stop("streams needs columns: ", paste(need, collapse = ", "))
  if (!"stream" %in% names(streams))
    streams$stream <- stream_from_url(streams$salmon_url)
  if (!"station" %in% names(streams)) streams$station <- NA_character_
  
  tables <- vector("list", nrow(streams))
  names(tables) <- streams$stream
  status <- vector("list", nrow(streams))
  
  for (i in seq_len(nrow(streams))) {
    nm  <- streams$stream[i]
    lab <- paste0("[", nm, "] ")
    if (verbose) message("\n=== ", nm, " ===")
    
    res <- tryCatch({
      if (is.na(streams$flow_url[i]))
        stop("no flow_url -- add this stream's own WSC gauge file")
      
      salmon <- read_salmon(streams$salmon_url[i], species = species,
                            run_type = run_type, arrival_col = arrival_col,
                            interpret = interpret, verbose = verbose,
                            label = lab)
      flow   <- read_flow(streams$flow_url[i],
                          station = if (is.na(streams$station[i])) NULL
                          else streams$station[i],
                          verbose = verbose, label = lab)
      hz <- build_hazard_data(salmon, flow, start_doy = start_doy,
                              stream = nm, verbose = verbose, label = lab, ...)
      list(hz = hz, n_salmon = nrow(salmon), err = NA_character_)
    }, error = function(e) list(hz = NULL, n_salmon = NA_integer_,
                                err = conditionMessage(e)))
    
    tables[[i]] <- res$hz
    status[[i]] <- data.frame(
      stream      = nm,
      ok          = !is.null(res$hz),
      salmon_years = res$n_salmon,
      model_years = if (is.null(res$hz)) NA_integer_ else length(unique(res$hz$year)),
      rows        = if (is.null(res$hz)) NA_integer_ else nrow(res$hz),
      start_doy   = if (is.null(res$hz)) NA_integer_ else attr(res$hz, "start_doy"),
      error       = res$err, stringsAsFactors = FALSE)
    if (!is.null(res$err) && !is.na(res$err) && verbose)
      message(lab, "FAILED: ", res$err)
  }
  
  st <- do.call(rbind, status)
  ok <- tables[!vapply(tables, is.null, logical(1))]
  attr(ok, "status")   <- st
  attr(ok, "combined") <- if (length(ok)) do.call(rbind, ok) else NULL
  if (verbose) { message("\n--- summary ---"); print(st[, setdiff(names(st), "error")]) }
  ok
}


## --- example ---------------------------------------------------------------
if (sys.nframe() == 0) {
  
  hz_list <- build_streams(STREAMS)
  
  print(attr(hz_list, "status"))          # what worked, what failed and why
  all_hz <- attr(hz_list, "combined")     # every stream stacked
  
  chem <- hz_list[["CHEMAINUS RIVER"]]
  print(utils::head(chem))
  
  ## model each stream separately -- rivers differ in flow magnitude
  # library(ranger)
  # fit <- ranger(factor(arrived) ~ doy + flow_7d + flow_cum_since_start +
  #                 days_since_high_flow,
  #               data = chem, probability = TRUE, num.trees = 1000)
}

###Output hz_list each list [[]] is a diff stream 
#can write this for github
write.csv(hz_list[[1]], file = "/home/jovyan/Desktop/fishyG/data/stream_hazard_data/chemainus_hazard_data.csv")
write.csv(hz_list[[2]], file = "/home/jovyan/Desktop/fishyG/data/stream_hazard_data/cowichan_hazard_data.csv")
write.csv(hz_list[[3]], file = "/home/jovyan/Desktop/fishyG/data/stream_hazard_data/lilqualicum_hazard_data.csv")
write.csv(hz_list[[4]], file = "/home/jovyan/Desktop/fishyG/data/stream_hazard_data/nanaimo_hazard_data.csv")

###Need to screen for rows to make sure the 1st arrival isn't before July 1 (ex. Nanaimo Riv 1993 Jan 4)
###rm years where doy < 182 