###Note this is a function from Claude with the prompt (with some tweaks) : write a function to read in the csvs at this link https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Salmon%20Data/CHEMAINUS%20RIVER_salmon_data.csv and this link https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Chemanius_Riv_Flow.csv. From those csvs, reformat the data to match the recommended discrete-time hazard structure above (including transforming yr-month-day dates into day of year numeric values, creating a binary column for salmon arrival, etc.)
## ---------------------------------------------------------------------------
## Chemainus River: build discrete-time hazard data for first-salmon-arrival
##
## One row per (year, day) that the fish had NOT yet arrived, up to and
## including the arrival day. Target `arrived` is 1 on the arrival day, else 0.
## Every predictor is computed from information available on or before that
## day, so training and prediction conditions are identical by construction.
##
##   read_salmon()        salmon CSV -> one row per year, arrival from time_return
##   read_flow()          flow CSV   -> continuous daily series (auto-detects cols)
##   build_hazard_data()  join the two into the hazard table
##
## Base R only.
## ---------------------------------------------------------------------------
## ---------------------------------------------------------------------------
##
## year |	integer	Calendar year, from ANALYSIS_YR
## date |		Date	The day this row describes
## doy	 |	1–366	Day of year; carries baseline seasonal timing
## days_at_risk	 |	days	Days elapsed since start_doy; 1 on the first row of each year
## arrived	 |	0 / 1	Target. 1 on the arrival day, 0 on every prior day
## flow	 |	m³/s	Daily mean discharge that day
## flow_7d / _14d / _30d	m³/s	 |	Mean discharge over today plus the previous 6 / 13 / 29 days
## flow_delta_14d	 |	m³/s	flow_7d − flow_14d. Positive means flow is rising
## flow_cum_since_start	 |	m³/s·day	Running sum of daily mean discharge since start_doy
## days_since_high_flow	 |	days	Days since discharge last hit the high_flow_q threshold. Resets each calendar year; NA before the first crossing
## jan_jun_mean_flow	m³/s	 |	Mean discharge Jan 1–Jun 30 that year. One value repeated down the year; NA if fewer than min_jan_jun_days observed
## n_missing_flow	 |	days	Count of NA flow days in that year's window. A data-quality flag, not a predictor
## start_doy is the day of year each year's at-risk window opens — the first day the model treats as a day 
#     salmon could arrive. It defaults to 152, which is June 1. Also Where flow_cum_since_start starts accumulating. 
#     The cumulative-discharge feature resets to zero on start_doy each year, so moving it changes that predictor's values, not just the row count.
#     For now, choose to keep start_doy as 152, but could adjust to 200 if decide to change?

SALMON_URL <- paste0(
  "https://raw.githubusercontent.com/oceanhackweek/ohw26_proj_fishyG/",
  "76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Salmon%20Data/",
  "CHEMAINUS%20RIVER_salmon_data.csv")

FLOW_URL <- paste0(
  "https://raw.githubusercontent.com/oceanhackweek/ohw26_proj_fishyG/",
  "76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Chemanius_Riv_Flow.csv")


## --- helpers ---------------------------------------------------------------

## Try several date layouts; return the one that parses the most values.
parse_dates_flex <- function(x) {
  x <- trimws(as.character(x))
  x[x == "" | x %in% c("NA", "NULL", "N/A")] <- NA
  x <- sub("[ T].*$", "", x)          # drop any time component
  fmts <- c("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
            "%d-%b-%y", "%d-%b-%Y", "%b %d, %Y", "%Y%m%d")
  best <- as.Date(rep(NA, length(x))); best_n <- -1L
  for (f in fmts) {
    d <- suppressWarnings(as.Date(x, format = f))
    n <- sum(!is.na(d))
    if (n > best_n) { best <- d; best_n <- n }
  }
  if (best_n == 0 && any(!is.na(x)))
    warning("no date format matched; check the raw column", call. = FALSE)
  best
}

## Causal trailing mean: window is today plus the previous k-1 days.
## NA-tolerant (averages over whatever is present).
roll_mean_causal <- function(x, k) {
  n <- length(x)
  xx <- ifelse(is.na(x), 0, x)
  ok <- as.numeric(!is.na(x))
  cs <- c(0, cumsum(xx)); cn <- c(0, cumsum(ok))
  i  <- seq_len(n); lo <- pmax(i - k, 0)
  s   <- cs[i + 1] - cs[lo + 1]
  cnt <- cn[i + 1] - cn[lo + 1]
  ifelse(cnt == 0, NA_real_, s / cnt)
}

## Days since x last met/exceeded `thr`, counting today. NA before any crossing.
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


## --- arrival column interpretation ------------------------------------------
##
## `time_return` is lowercase where every other column is uppercase, which
## usually means a field derived by the project team rather than part of the
## original DFO export. It could plausibly hold:
##   "date"   an actual date string            -> used directly
##   "doy"    day-of-year 1-366                -> combined with ANALYSIS_YR
##   "offset" days after START_DTT             -> added to the parsed START_DTT
##   "excel"  spreadsheet serial (~20000-60000)-> days since 1899-12-30
##
## `interpret = "auto"` guesses and PRINTS its choice. Check the printed
## sample dates look like plausible Chinook arrivals before trusting them.
## Override with interpret = "doy" (etc.) if the guess is wrong.
interpret_arrival <- function(x, year, start_dtt = NULL,
                              interpret = c("auto", "date", "doy", "offset",
                                            "excel"),
                              verbose = TRUE) {
  interpret <- match.arg(interpret)
  
  chr <- trimws(as.character(x))
  chr[chr %in% c("", "NA", "NULL", "N/A", "-")] <- NA
  num <- suppressWarnings(as.numeric(chr))
  as_date <- suppressWarnings(parse_dates_flex(chr))
  start   <- if (!is.null(start_dtt)) parse_dates_flex(start_dtt) else NULL
  
  n_num  <- sum(!is.na(num))
  n_date <- sum(!is.na(as_date))
  fin    <- num[!is.na(num)]
  
  if (interpret == "auto") {
    interpret <-
      if (n_date > n_num)                          "date"
    else if (!n_num)                             "date"
    else if (all(fin >= 20000 & fin <= 60000))   "excel"
    else if (all(fin >= 1 & fin <= 366) &&
             stats::median(fin) > 100)           "doy"
    else if (!is.null(start) && sum(!is.na(start)) > 0 &&
             all(fin >= 0 & fin <= 400))         "offset"
    else if (all(fin >= 1 & fin <= 366))         "doy"
    else stop("cannot interpret arrival column; values look like: ",
              paste(utils::head(chr[!is.na(chr)], 5), collapse = ", "),
              " -- pass interpret = 'date'/'doy'/'offset'/'excel'")
  }
  
  out <- switch(interpret,
                date   = as_date,
                doy    = as.Date(paste0(year, "-01-01")) + (num - 1),
                excel  = as.Date(num, origin = "1899-12-30"),
                offset = {
                  if (is.null(start)) stop("interpret = 'offset' needs a START_DTT column")
                  start + num
                })
  
  if (verbose) {
    ok <- sum(!is.na(out))
    message("interpret_arrival(): treating column as '", interpret, "' -- ",
            ok, " of ", length(out), " parsed")
    if (ok) {
      doy <- as.integer(format(out, "%j"))
      message("  raw sample : ",
              paste(utils::head(chr[!is.na(out)], 4), collapse = " | "))
      message("  -> dates   : ",
              paste(utils::head(out[!is.na(out)], 4), collapse = " | "))
      message("  -> doy range ", min(doy, na.rm = TRUE), "-",
              max(doy, na.rm = TRUE),
              if (min(doy, na.rm = TRUE) < 100 || max(doy, na.rm = TRUE) > 366)
                "  <-- IMPLAUSIBLE for Chinook, check interpret=" else "")
    }
  }
  out
}


## --- salmon ----------------------------------------------------------------
##
## Known header:
##   WATERBODY, ANALYSIS_YR, SPECIES, RUN_TYPE, TOTAL_RETURN_TO_RIVER,
##   START_DTT, STREAM_ARRIVAL_DT_FROM, time_return
##
## arrival_col defaults to `time_return`. Set it to "STREAM_ARRIVAL_DT_FROM"
## to go back to the previous behaviour.
read_salmon <- function(path = SALMON_URL, species = NULL, run_type = NULL,
                        arrival_col = "time_return",
                        interpret   = "auto",
                        verbose     = TRUE) {
  
  s <- read.csv(path, stringsAsFactors = FALSE, check.names = TRUE,
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
    interpret = interpret, verbose = verbose)
  
  if (!is.null(species))
    s <- s[toupper(trimws(s$SPECIES)) %in% toupper(species), , drop = FALSE]
  if (!is.null(run_type) && "RUN_TYPE" %in% names(s))
    s <- s[toupper(trimws(s$RUN_TYPE)) %in% toupper(run_type), , drop = FALSE]
  
  if (!nrow(s))
    stop("species/run_type filter matched 0 rows. Available SPECIES: ",
         paste(unique(trimws(read.csv(path, stringsAsFactors = FALSE)$SPECIES)),
               collapse = ", "), " -- pass species = NULL to keep everything")
  
  dropped <- sum(is.na(s$arrival_date))
  if (dropped)
    warning(dropped, " row(s) had no parseable arrival date and were dropped",
            call. = FALSE)
  s <- s[!is.na(s$arrival_date) & !is.na(s$year), , drop = FALSE]
  if (!nrow(s))
    stop("no rows survived arrival-date parsing from '", arrival_col,
         "' -- try interpret= or a different arrival_col")
  
  s$arrival_doy <- as.integer(format(s$arrival_date, "%j"))
  
  ## sanity: the constructed date must fall in its own analysis year
  off <- s$year != as.integer(format(s$arrival_date, "%Y"))
  if (any(off))
    warning(sum(off), " row(s) have an arrival date outside ANALYSIS_YR",
            " -- the interpretation is probably wrong", call. = FALSE)
  
  dup <- s$year[duplicated(s$year)]
  if (length(dup))
    warning("multiple rows for year(s): ", paste(unique(dup), collapse = ", "),
            " -- filter by species/run_type, or the earliest is used",
            call. = FALSE)
  s <- s[order(s$year, s$arrival_date), ]
  s <- s[!duplicated(s$year), , drop = FALSE]
  
  keep <- intersect(c("year", "arrival_date", "arrival_doy", "SPECIES",
                      "RUN_TYPE", "TOTAL_RETURN_TO_RIVER"), names(s))
  out <- s[, keep, drop = FALSE]
  rownames(out) <- NULL
  out
}


## --- flow ------------------------------------------------------------------
##
## Water Survey of Canada daily export, station 08HA001:
##   ID,PARAM,Date,Value,SYM
##   08HA001,1,1914/05/13,14.7,
##
## PARAM 1 = discharge (m3/s), 2 = water level. SYM is the WSC data qualifier:
##   E = estimated, A = partial day, B = ice conditions, D = dry, S = sample.
## `drop_symbols` blanks out values carrying those flags. B is the one that
## matters -- ice-affected discharge is backcalculated and unreliable -- but it
## only occurs in winter, so it will rarely touch a Jun-Nov window.
read_flow <- function(path = FLOW_URL,
                      param        = 1,
                      drop_symbols = c("B"),
                      verbose      = TRUE) {
  
  ## WSC exports open with a title banner before the real header, e.g.
  ##   Daily Discharge (m3/s) (PARAM = 1) and Daily Water Level (m) (PARAM = 2)
  ##    ID,PARAM,Date,Value,SYM
  ## Find the header line rather than assuming how many banner lines there are.
  lines <- readLines(path, warn = FALSE)
  hdr_i <- grep("^\\s*ID\\s*,\\s*PARAM\\s*,", lines)[1]
  if (is.na(hdr_i))
    stop("could not find the 'ID,PARAM,Date,Value,SYM' header line in ", path)
  if (verbose && hdr_i > 1)
    message("read_flow(): skipped ", hdr_i - 1, " preamble line(s): ",
            sQuote(trimws(lines[1])))
  
  f <- read.csv(text = lines[hdr_i:length(lines)], stringsAsFactors = FALSE,
                strip.white = TRUE, colClasses = "character",
                check.names = FALSE)
  
  ## the header carries a leading space, so name the columns rather than
  ## letting make.names() turn ' ID' into 'X.ID'
  if (ncol(f) != 5)
    stop("expected 5 WSC columns, got ", ncol(f), ": ",
         paste(names(f), collapse = ", "))
  names(f) <- c("ID", "PARAM", "Date", "Value", "SYM")
  
  n_all <- nrow(f)
  f <- f[suppressWarnings(as.numeric(f$PARAM)) == param, , drop = FALSE]
  
  out <- data.frame(
    date = as.Date(f$Date, format = "%Y/%m/%d"),
    flow = suppressWarnings(as.numeric(f$Value)),
    sym  = if ("SYM" %in% names(f)) trimws(f$SYM) else NA_character_,
    stringsAsFactors = FALSE
  )
  
  bad_date <- sum(is.na(out$date))
  if (bad_date)
    warning(bad_date, " row(s) failed %Y/%m/%d date parsing", call. = FALSE)
  out <- out[!is.na(out$date), , drop = FALSE]
  
  n_flagged <- 0L
  if (length(drop_symbols)) {
    hit <- out$sym %in% drop_symbols
    n_flagged <- sum(hit & !is.na(out$flow))
    out$flow[hit] <- NA_real_
  }
  
  out <- out[order(out$date), ]
  out <- out[!duplicated(out$date), , drop = FALSE]
  
  ## reindex to a gap-free daily grid so rolling windows mean what they say
  full <- data.frame(date = seq(min(out$date), max(out$date), by = "day"))
  out  <- merge(full, out, by = "date", all.x = TRUE)
  out  <- out[order(out$date), ]
  rownames(out) <- NULL
  
  if (verbose)
    message(sprintf(
      "read_flow(): %s rows -> %s PARAM==%s days | %s to %s | %s missing (%.1f%%)%s",
      n_all, nrow(out), param, min(out$date), max(out$date),
      sum(is.na(out$flow)), 100 * mean(is.na(out$flow)),
      if (n_flagged) sprintf(" | %s blanked as [%s]", n_flagged,
                             paste(drop_symbols, collapse = "")) else ""))
  out
}


## --- coverage check --------------------------------------------------------
##
## Run this BEFORE modelling. Reports, per salmon year, how many days of flow
## are missing in the at-risk window. WSC stations get discontinued and
## reactivated; a year with a hole in it will silently poison the rolling
## features rather than error.
check_coverage <- function(salmon, flow, start_doy = 152, max_gap = 10) {
  if (!nrow(salmon)) stop("check_coverage(): salmon has 0 rows")
  flow$year <- as.integer(format(flow$date, "%Y"))
  flow$doy  <- as.integer(format(flow$date, "%j"))
  
  do.call(rbind, lapply(seq_len(nrow(salmon)), function(i) {
    yr  <- salmon$year[i]
    adt <- salmon$arrival_date[i]
    d <- flow[flow$year == yr & flow$doy >= start_doy & flow$date <= adt, ,
              drop = FALSE]
    data.frame(
      year         = yr,
      arrival_date = adt,
      arrival_doy  = salmon$arrival_doy[i],
      window_days  = nrow(d),
      missing_flow = sum(is.na(d$flow)),
      pct_missing  = if (nrow(d)) round(100 * mean(is.na(d$flow)), 1) else NA,
      usable       = nrow(d) > 0 && sum(is.na(d$flow)) <= max_gap,
      stringsAsFactors = FALSE
    )
  }))
}


## --- hazard table ----------------------------------------------------------
##
## start_doy    first at-risk day each year (default 152 = Jun 1)
## high_flow_q  quantile of the whole flow record defining a "high flow" event
## max_gap      drop a year if more than this many flow days are missing in
##              its at-risk window
build_hazard_data <- function(salmon, flow,
                              start_doy   = 152,
                              high_flow_q = 0.75,
                              max_gap     = 10,
                              min_jan_jun_days = 120) {
  
  flow <- flow[order(flow$date), ]
  flow$year <- as.integer(format(flow$date, "%Y"))
  flow$doy  <- as.integer(format(flow$date, "%j"))
  
  ## rolling features on the FULL continuous series, so windows that reach
  ## back before start_doy are still complete
  flow$flow_7d  <- roll_mean_causal(flow$flow, 7)
  flow$flow_14d <- roll_mean_causal(flow$flow, 14)
  flow$flow_30d <- roll_mean_causal(flow$flow, 30)
  flow$flow_delta_14d <- flow$flow_7d - roll_mean_causal(flow$flow, 14)
  
  thr <- quantile(flow$flow, high_flow_q, na.rm = TRUE)
  flow$days_since_high_flow <- unlist(lapply(
    split(flow$flow, flow$year), days_since_above, thr = thr),
    use.names = FALSE)
  
  ## within-year cumulative flow from start_doy, and the Jan-Jun mean
  by_year <- split(flow, flow$year)
  flow <- do.call(rbind, lapply(by_year, function(d) {
    d <- d[order(d$doy), ]
    v <- ifelse(is.na(d$flow), 0, d$flow)
    v[d$doy < start_doy] <- 0
    d$flow_cum_since_start <- cumsum(v)
    ## Jan-Jun mean, but NA rather than a misleading partial figure. The WSC
    ## record opens 1914-05-13, so the first year has ~7 weeks and any
    ## reactivation year may also be short.
    jj <- d$flow[d$doy <= 181]
    d$jan_jun_mean_flow <- if (sum(!is.na(jj)) >= min_jan_jun_days)
      mean(jj, na.rm = TRUE) else NA_real_
    d
  }))
  rownames(flow) <- NULL
  
  rows <- lapply(seq_len(nrow(salmon)), function(i) {
    yr  <- salmon$year[i]
    adt <- salmon$arrival_date[i]
    fy  <- flow[flow$year == yr, , drop = FALSE]
    if (!nrow(fy)) {
      warning("year ", yr, ": no flow data, skipped", call. = FALSE); return(NULL)
    }
    if (salmon$arrival_doy[i] < start_doy) {
      warning("year ", yr, ": arrival (doy ", salmon$arrival_doy[i],
              ") precedes start_doy ", start_doy, ", skipped", call. = FALSE)
      return(NULL)
    }
    d <- fy[fy$doy >= start_doy & fy$date <= adt, , drop = FALSE]
    if (!nrow(d)) {
      warning("year ", yr, ": empty at-risk window, skipped", call. = FALSE)
      return(NULL)
    }
    gaps <- sum(is.na(d$flow))
    if (gaps > max_gap) {
      warning("year ", yr, ": ", gaps, " missing flow days in window, skipped",
              call. = FALSE)
      return(NULL)
    }
    
    data.frame(
      year        = yr,
      date        = d$date,
      doy         = d$doy,
      days_at_risk = seq_len(nrow(d)),
      arrived     = as.integer(d$date == adt),
      flow                 = d$flow,
      flow_7d              = d$flow_7d,
      flow_14d             = d$flow_14d,
      flow_30d             = d$flow_30d,
      flow_delta_14d       = d$flow_delta_14d,
      flow_cum_since_start = d$flow_cum_since_start,
      days_since_high_flow = d$days_since_high_flow,
      jan_jun_mean_flow    = d$jan_jun_mean_flow,
      n_missing_flow       = gaps,
      stringsAsFactors = FALSE
    )
  })
  
  out <- do.call(rbind, rows)
  if (is.null(out))
    stop("no usable years from ", nrow(salmon), " salmon row(s). ",
         "Run check_coverage(salmon, flow) to see per-year flow gaps; ",
         "if pct_missing is high everywhere, raise max_gap (currently ",
         max_gap, ") or move start_doy later to shorten the window.")
  rownames(out) <- NULL
  
  ## every retained year must end in exactly one arrival
  chk <- tapply(out$arrived, out$year, sum)
  bad <- names(chk)[chk != 1]
  if (length(bad))
    warning("year(s) with != 1 arrival row: ", paste(bad, collapse = ", "),
            call. = FALSE)
  
  out[order(out$year, out$date), ]
}


## --- example ---------------------------------------------------------------
if (sys.nframe() == 0) {
  
  ## 1. look at the salmon file before filtering anything
  salmon_raw <- read.csv(SALMON_URL, stringsAsFactors = FALSE)
  print(table(salmon_raw$SPECIES, salmon_raw$RUN_TYPE))
  print(range(salmon_raw$ANALYSIS_YR, na.rm = TRUE))
  
  ## 2. read both sources
  salmon <- read_salmon()   # arrival from time_return; check the printed guess
  flow   <- read_flow()
  
  ## 3. CHECK COVERAGE BEFORE MODELLING -- do not skip this
  cov <- check_coverage(salmon, flow)
  print(cov)
  cat("years with any missing flow:", sum(cov$missing_flow > 0), "of", nrow(cov), "\n")
  
  ## 4. build
  hz <- build_hazard_data(salmon, flow)
  cat("\nrows:", nrow(hz), " years:", length(unique(hz$year)),
      " arrivals:", sum(hz$arrived), "\n")
  print(utils::head(hz))
  
}

################################################################################################
## Actually make the hazard files for 
## 1. Chemainus
## 2. Cowichan
## 3. LilQualicum
## 4. Nanaimo
## Name each output (the hz file as hz_river)
################################################################################################


######################################### Chemainus ######################################### 
SALMON_URL <- paste0(
  "https://raw.githubusercontent.com/oceanhackweek/ohw26_proj_fishyG/",
  "76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Salmon%20Data/",
  "CHEMAINUS%20RIVER_salmon_data.csv")

FLOW_URL <- paste0(
  "https://raw.githubusercontent.com/oceanhackweek/ohw26_proj_fishyG/",
  "76c0f7785620e3f0f42571b73357cbce4e2ea0a0/data/Chemanius_Riv_Flow.csv")


## 1. look at the salmon file before filtering anything
salmon_raw <- read.csv(SALMON_URL, stringsAsFactors = FALSE)
print(table(salmon_raw$SPECIES, salmon_raw$RUN_TYPE))
print(range(salmon_raw$ANALYSIS_YR, na.rm = TRUE))

## 2. read both sources
salmon <- read_salmon()   # arrival from time_return; check the printed guess
flow   <- read_flow()

## 3. CHECK COVERAGE BEFORE MODELLING -- do not skip this
cov <- check_coverage(salmon, flow)
print(cov)
cat("years with any missing flow:", sum(cov$missing_flow > 0), "of", nrow(cov), "\n")

## 4. build
hz_chemainus <- build_hazard_data(salmon, flow)
cat("\nrows:", nrow(hz_chemainus), " years:", length(unique(hz_chemainus$year)),
    " arrivals:", sum(hz_chemainus$arrived), "\n")
print(utils::head(hz_chemainus))

######################################### Cowichan #########################################

SALMON_URL <- paste0(
  "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/Salmon%20Data/COWICHAN%20RIVER_salmon_data.csv")

FLOW_URL <- paste0(
  "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/Cowichan_Riv_Flow.csv")


## 1. look at the salmon file before filtering anything
salmon_raw <- read.csv(SALMON_URL, stringsAsFactors = FALSE)
print(table(salmon_raw$SPECIES, salmon_raw$RUN_TYPE))
print(range(salmon_raw$ANALYSIS_YR, na.rm = TRUE))

## 2. read both sources
salmon <- read_salmon()   # arrival from time_return; check the printed guess
flow   <- read_flow()

## 3. CHECK COVERAGE BEFORE MODELLING -- do not skip this
cov <- check_coverage(salmon, flow)
print(cov)
cat("years with any missing flow:", sum(cov$missing_flow > 0), "of", nrow(cov), "\n")

## 4. build
hz_cowichan <- build_hazard_data(salmon, flow)
cat("\nrows:", nrow(hz_cowichan), " years:", length(unique(hz_cowichan$year)),
    " arrivals:", sum(hz_cowichan$arrived), "\n")
print(utils::head(hz_cowichan))

######################################### LilQualicum #########################################

SALMON_URL <- paste0(
  "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/",
  "717e8ce794b893b458ed9e5f27de7ec15062af90/data/Salmon%20Data/LITTLE%20QUALICUM%20RIVER_salmon_data.csv")

FLOW_URL <- paste0(
  "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/LilQualicum_Riv_Flow.csv")

## 1. look at the salmon file before filtering anything
salmon_raw <- read.csv(SALMON_URL, stringsAsFactors = FALSE)
print(table(salmon_raw$SPECIES, salmon_raw$RUN_TYPE))
print(range(salmon_raw$ANALYSIS_YR, na.rm = TRUE))

## 2. read both sources
salmon <- read_salmon()   # arrival from time_return; check the printed guess
flow   <- read_flow()

## 3. CHECK COVERAGE BEFORE MODELLING -- do not skip this
cov <- check_coverage(salmon, flow)
print(cov)
cat("years with any missing flow:", sum(cov$missing_flow > 0), "of", nrow(cov), "\n")

## 4. build
hz_lilqualicum <- build_hazard_data(salmon, flow)
cat("\nrows:", nrow(hz_lilqualicum), " years:", length(unique(hz_lilqualicum$year)),
    " arrivals:", sum(hz_lilqualicum$arrived), "\n")
print(utils::head(hz_lilqualicum))

######################################### Nanaimo #########################################

SALMON_URL <- paste0(
  "https://github.com/oceanhackweek/ohw26_proj_fishyG/",
  "blob/717e8ce794b893b458ed9e5f27de7ec15062af90/data/Salmon%20Data/NANAIMO%20RIVER_salmon_data.csv")

FLOW_URL <- paste0(
  "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/main/data/Nanaimo_Riv_Flow.csv")

## 1. look at the salmon file before filtering anything
salmon_raw <- read.csv(SALMON_URL, stringsAsFactors = FALSE)
print(table(salmon_raw$SPECIES, salmon_raw$RUN_TYPE))
print(range(salmon_raw$ANALYSIS_YR, na.rm = TRUE))

## 2. read both sources
salmon <- read_salmon()   # arrival from time_return; check the printed guess
flow   <- read_flow()

## 3. CHECK COVERAGE BEFORE MODELLING -- do not skip this
cov <- check_coverage(salmon, flow)
print(cov)
cat("years with any missing flow:", sum(cov$missing_flow > 0), "of", nrow(cov), "\n")

## 4. build
hz_nanaimo <- build_hazard_data(salmon, flow)
cat("\nrows:", nrow(hz_nanaimo), " years:", length(unique(hz_nanaimo$year)),
    " arrivals:", sum(hz_nanaimo$arrived), "\n")
print(utils::head(hz_nanaimo))