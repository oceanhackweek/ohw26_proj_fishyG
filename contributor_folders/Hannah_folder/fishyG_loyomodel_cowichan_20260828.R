#Claude prompt: I want to build a model to predict what day of a given year that the fall chinook salmon will arrive to a stream (and I want the code for this model to be reproducibly run across multiple streams). For this model, I want to input environment variables for the stream, including the average flow that day, a rolling 7day flow average, whether flow is increasing or decreasing over 14 days (flow_delta_14d_z), the average stream flow between January and Jun30 of that year, and the stream temperature. Here is the raw data that I want to use.
#Plan, write code in R, and explain the code to reformat the data for the model, run the model, and display the output.

#* Salmon data https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/fb5467aafebe8ce24a997c6e2d98bc2636ad769d/data/Salmon%20Data/COWICHAN%20RIVER_salmon_data.csv In this csv, the time_return column is the arrival date that I want to predict. ignore ST_DTT and STREAM_ARRIVAL_DT_FROM. For each model, the waterbody, run type, and species will all be the same
#* Stream flow https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/fb5467aafebe8ce24a997c6e2d98bc2636ad769d/data/Cowichan_Riv_Flow.csv
#* Temperature data https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/fb5467aafebe8ce24a997c6e2d98bc2636ad769d/data/cowichan_temp_daily.csv

#Because the stream file is too large, here are the 1st few lines:
# Daily Discharge (m3/s) (PARAM = 1) and Daily Water Level (m) (PARAM = 2)
#ID,PARAM,Date,Value,SYM
#08HA011,1,1960/01/01,62.9,E
#08HA011,1,1960/01/02,58.0,E
#08HA011,1,1960/01/03,54.9,E
#08HA011,1,1960/01/04,51.3,E
#08HA011,1,1960/01/05,47.3,
#08HA011,1,1960/01/06,46.7,
#08HA011,1,1960/01/07,43.9,E
#08HA011,1,1960/01/08,41.9,E
#08HA011,1,1960/01/09,40.8,E
#08HA011,1,1960/01/10,38.5,E

## ===========================================================================
## Predicting fall Chinook arrival date from stream conditions
##
## PLAN
##   1. Read three raw sources per stream: salmon returns, WSC daily flow,
##      daily water temperature.
##   2. Build one continuous daily table per stream, with every predictor
##      computed causally (using only that day and earlier).
##   3. Reshape into discrete-time hazard form: one row per (year, day) the
##      fish had not yet arrived. Target `arrived` is 1 on the arrival day.
##   4. Fit a complementary log-log GLM -- the discrete-time survival model.
##   5. Convert the fitted daily hazards into a predicted arrival DATE, and
##      score it out-of-sample against climatology.
##   6. Separately, model TOTAL_RETURN_TO_RIVER -- run abundance. This is a
##      year-level count, not a daily event, so it gets its own model: a
##      negative-binomial GLM on one row per year, scored against the same
##      kind of out-of-sample benchmark.
##
## Why hazard form rather than one row per year: it lets the model use a
## partial season (you can predict on Aug 27 with no September data), it
## produces a full probability distribution over arrival dates rather than a
## point guess, and it can extrapolate beyond the arrival dates observed.
##
## Needs: splines (base R). Optional: lme4 for the pooled multi-stream model.
## ===========================================================================

library(splines)

## --- stream registry -------------------------------------------------------
## Add a row per stream. Everything below is driven off this table.
STREAMS <- data.frame(
  stream = "COWICHAN RIVER",
  salmon_url = "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/fb5467aafebe8ce24a997c6e2d98bc2636ad769d/data/Salmon%20Data/COWICHAN%20RIVER_salmon_data.csv",
  flow_url   = "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/fb5467aafebe8ce24a997c6e2d98bc2636ad769d/data/Cowichan_Riv_Flow.csv",
  temp_url   = "https://github.com/oceanhackweek/ohw26_proj_fishyG/blob/fb5467aafebe8ce24a997c6e2d98bc2636ad769d/data/cowichan_temp_daily.csv",
  stringsAsFactors = FALSE)

## The five predictors you asked for. `water_temp` is listed last because the
## temperature record is far shorter than the others -- see COVERAGE below.
COVARS_FULL <- c("flow", "flow_7d", "flow_delta_14d", "jan_jun_mean_flow",
                 "water_temp")
COVARS_NOTEMP <- setdiff(COVARS_FULL, "water_temp")

END_DOY <- 350   # last candidate arrival day; prediction window closes here

## Abundance predictors, summarised to one value per year. DECISION_DOY is the
## day the forecast is issued: only conditions up to that day are used, so the
## model is a genuine pre-season forecast rather than a hindcast.
DECISION_DOY   <- 181                      # Jun 30
COVARS_ABUND   <- c("jan_jun_mean_flow", "flow_7d", "flow_delta_14d")
COVARS_ABUND_T <- c(COVARS_ABUND, "water_temp")


## --- small helpers ---------------------------------------------------------

## github.com/.../blob/... serves an HTML page, not the file.
gh_raw <- function(u) sub("^https://github\\.com/([^/]+)/([^/]+)/(?:blob|raw)/",
                          "https://raw.githubusercontent.com/\\1/\\2/", u)

read_lines_csv <- function(url) {
  l <- readLines(gh_raw(url), warn = FALSE)
  if (length(l) && grepl("^\\s*(<!DOCTYPE|<html)", l[1], ignore.case = TRUE))
    stop("got HTML, not CSV, from ", url)
  l[nzchar(trimws(l))]
}

parse_dates_flex <- function(x) {
  x <- trimws(as.character(x)); x[x %in% c("", "NA", "NULL", "N/A", "-")] <- NA
  x <- sub("[ T].*$", "", x)
  best <- as.Date(rep(NA, length(x))); best_n <- -1L
  for (f in c("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y",
              "%d-%b-%y", "%b %d, %Y", "%Y%m%d")) {
    d <- suppressWarnings(as.Date(x, format = f))
    if (sum(!is.na(d)) > best_n) { best <- d; best_n <- sum(!is.na(d)) }
  }
  best
}

## Causal trailing mean: today plus the previous k-1 days only.
roll_mean_causal <- function(x, k) {
  n <- length(x); xx <- ifelse(is.na(x), 0, x); ok <- as.numeric(!is.na(x))
  cs <- c(0, cumsum(xx)); cn <- c(0, cumsum(ok))
  i <- seq_len(n); lo <- pmax(i - k, 0)
  s <- cs[i + 1] - cs[lo + 1]; cnt <- cn[i + 1] - cn[lo + 1]
  ifelse(cnt == 0, NA_real_, s / cnt)
}


## --- 1. read the three sources ---------------------------------------------

## Salmon: arrival date comes from `time_return`, as specified. START_DTT and
## STREAM_ARRIVAL_DT_FROM are ignored. Waterbody/species/run type are constant
## per file so they are not modelled.
read_salmon <- function(url, verbose = TRUE) {
  lines <- read_lines_csv(url)
  ## repair thousands separators (12,500 -> 12500) that split a row
  n_hdr <- length(scan(text = lines[1], what = "", sep = ",", quiet = TRUE))
  nf <- utils::count.fields(textConnection(lines), sep = ",", quote = "\"")
  if (any(nf != n_hdr, na.rm = TRUE))
    lines <- c(lines[1], gsub("(?<=[0-9]),(?=[0-9]{3}([^0-9]|$))", "",
                              lines[-1], perl = TRUE))
  
  s <- read.csv(text = lines, stringsAsFactors = FALSE, strip.white = TRUE)
  for (v in c("ANALYSIS_YR", "time_return"))
    if (!v %in% names(s)) stop("salmon file missing '", v, "'")
  
  s$year         <- as.integer(s$ANALYSIS_YR)
  s$arrival_date <- parse_dates_flex(s$time_return)
  
  ## run abundance: strip any thousands separators before coercing
  s$total_return <- if ("TOTAL_RETURN_TO_RIVER" %in% names(s))
    suppressWarnings(as.numeric(gsub("[, ]", "", as.character(
      s$TOTAL_RETURN_TO_RIVER)))) else NA_real_
  s <- s[!is.na(s$arrival_date) & !is.na(s$year), , drop = FALSE]
  s$arrival_doy  <- as.integer(format(s$arrival_date, "%j"))
  
  ## one arrival per year: the earliest, i.e. FIRST arrival
  s <- s[order(s$year, s$arrival_date), ]
  s <- s[!duplicated(s$year), , drop = FALSE]
  
  if (verbose) {
    message(sprintf("  salmon: %d years (%d-%d), arrival doy %d-%d",
                    nrow(s), min(s$year), max(s$year),
                    min(s$arrival_doy), max(s$arrival_doy)))
    ab <- s$total_return[is.finite(s$total_return) & s$total_return > 0]
    if (length(ab))
      message(sprintf("  return: %d years with abundance, %s to %s (median %s)",
                      length(ab), format(min(ab), big.mark = ","),
                      format(max(ab), big.mark = ","),
                      format(stats::median(ab), big.mark = ",")))
  }
  s[, c("year", "arrival_date", "arrival_doy", "total_return")]
}

## Flow: Water Survey of Canada daily export. A title banner precedes the real
## header. PARAM 1 = discharge (m3/s), 2 = water level. SYM flags: E estimated,
## B ice-affected (unreliable -- blanked), A partial, D dry.
read_flow <- function(url, param = 1, drop_symbols = "B", verbose = TRUE) {
  lines <- read_lines_csv(url)
  h <- grep("^\\s*ID\\s*,\\s*PARAM\\s*,", lines)[1]
  if (is.na(h)) stop("no WSC header line found in ", url)
  
  f <- read.csv(text = lines[h:length(lines)], stringsAsFactors = FALSE,
                colClasses = "character", check.names = FALSE, strip.white = TRUE)
  if (ncol(f) != 5) stop("expected 5 WSC columns, got ", ncol(f))
  names(f) <- c("ID", "PARAM", "Date", "Value", "SYM")
  f <- f[suppressWarnings(as.numeric(f$PARAM)) == param, , drop = FALSE]
  
  out <- data.frame(date = as.Date(f$Date, format = "%Y/%m/%d"),
                    flow = suppressWarnings(as.numeric(f$Value)),
                    stringsAsFactors = FALSE)
  out$flow[trimws(f$SYM) %in% drop_symbols] <- NA_real_
  out <- out[!is.na(out$date), , drop = FALSE]
  out <- out[!duplicated(out$date), ]
  out <- out[order(out$date), ]
  
  if (verbose)
    message(sprintf("  flow  : %s to %s, %.0f%% of days observed",
                    min(out$date), max(out$date), 100 * mean(!is.na(out$flow))))
  out
}

## Temperature: DATE, WATER_TEMP_C, N_READINGS. Returns NULL if unavailable.
read_temp <- function(url, verbose = TRUE) {
  if (is.na(url) || !nzchar(url)) return(NULL)
  out <- tryCatch({
    t <- read.csv(text = read_lines_csv(url), stringsAsFactors = FALSE,
                  strip.white = TRUE)
    tc <- grep("TEMP", names(t), ignore.case = TRUE, value = TRUE)[1]
    dc <- grep("DATE", names(t), ignore.case = TRUE, value = TRUE)[1]
    if (is.na(tc) || is.na(dc)) stop("no DATE / TEMP column")
    d <- data.frame(date = parse_dates_flex(t[[dc]]),
                    water_temp = suppressWarnings(as.numeric(t[[tc]])))
    d <- d[!is.na(d$date), ]; d[!duplicated(d$date), ]
  }, error = function(e) { message("  temp  : unavailable (", conditionMessage(e), ")"); NULL })
  
  if (!is.null(out) && verbose)
    message(sprintf("  temp  : %s to %s (%d days, ~%.1f years)",
                    min(out$date), max(out$date), nrow(out), nrow(out) / 365.25))
  out
}


## --- 2. daily environmental table ------------------------------------------
##
## Everything is built on a gap-free daily grid so that "7-day mean" really
## spans 7 calendar days. All windows look backwards only.
build_daily <- function(flow, temp = NULL, min_jan_jun_days = 120) {
  grid <- data.frame(date = seq(min(flow$date), max(flow$date), by = "day"))
  d <- merge(grid, flow, by = "date", all.x = TRUE)
  if (!is.null(temp)) d <- merge(d, temp, by = "date", all.x = TRUE)
  else d$water_temp <- NA_real_
  d <- d[order(d$date), ]
  
  d$year <- as.integer(format(d$date, "%Y"))
  d$doy  <- as.integer(format(d$date, "%j"))
  
  d$flow_7d  <- roll_mean_causal(d$flow, 7)
  d$flow_14d <- roll_mean_causal(d$flow, 14)
  ## positive = last week wetter than the fortnight, i.e. flow rising
  d$flow_delta_14d <- d$flow_7d - d$flow_14d
  
  ## one year-level value: mean discharge Jan 1 - Jun 30, NA if poorly covered
  d <- do.call(rbind, lapply(split(d, d$year), function(y) {
    jj <- y$flow[y$doy <= 181]
    y$jan_jun_mean_flow <- if (sum(!is.na(jj)) >= min_jan_jun_days)
      mean(jj, na.rm = TRUE) else NA_real_
    y
  }))
  rownames(d) <- NULL
  d
}


## --- 3. hazard reshaping ----------------------------------------------------
##
## fit frame : start_doy .. arrival day      (the at-risk set; arrived = 0/1)
## pred frame: start_doy .. END_DOY          (all candidate days, for forecasting)
##
## The fit frame must stop at arrival -- after arrival the year is no longer at
## risk. The pred frame must run to END_DOY, or there is no way to produce a
## predicted date for a year whose arrival you are pretending not to know.
build_frames <- function(salmon, daily, covars, start_doy = "auto",
                         auto_buffer = 30, end_doy = END_DOY, max_gap = 10,
                         verbose = TRUE) {
  
  if (identical(start_doy, "auto"))
    start_doy <- max(1L, min(salmon$arrival_doy) - auto_buffer)
  
  fit_rows <- pred_rows <- list(); skipped <- character(0)
  for (i in seq_len(nrow(salmon))) {
    yr <- salmon$year[i]; adt <- salmon$arrival_date[i]
    dy <- daily[daily$year == yr & daily$doy >= start_doy & daily$doy <= end_doy, ]
    if (!nrow(dy)) { skipped <- c(skipped, paste0(yr, ":no env data")); next }
    if (salmon$arrival_doy[i] < start_doy || salmon$arrival_doy[i] > end_doy) {
      skipped <- c(skipped, paste0(yr, ":arrival outside window")); next }
    
    at_risk <- dy[dy$date <= adt, ]
    gaps <- sum(is.na(at_risk[, intersect(covars, names(at_risk))]))
    if (sum(is.na(at_risk$flow)) > max_gap) {
      skipped <- c(skipped, paste0(yr, ":", sum(is.na(at_risk$flow)), " flow gaps")); next }
    
    at_risk$arrived <- as.integer(at_risk$date == adt)
    dy$arrived      <- as.integer(dy$date == adt)
    fit_rows[[length(fit_rows) + 1]]   <- at_risk
    pred_rows[[length(pred_rows) + 1]] <- dy
  }
  
  if (!length(fit_rows))
    stop("no usable years. Skips: ", paste(utils::head(skipped, 6), collapse = "; "))
  if (length(skipped) && verbose)
    message("  skipped ", length(skipped), " year(s): ",
            paste(utils::head(skipped, 4), collapse = "; "))
  
  list(fit = do.call(rbind, fit_rows), pred = do.call(rbind, pred_rows),
       start_doy = start_doy, end_doy = end_doy)
}

## Standardise covariates using the FIT rows only, then apply the same centring
## and scaling to the prediction rows. Coefficients then read "per SD".
scale_covars <- function(frames, covars) {
  ctr <- sapply(covars, function(v) mean(frames$fit[[v]], na.rm = TRUE))
  scl <- sapply(covars, function(v) stats::sd(frames$fit[[v]], na.rm = TRUE))
  scl[!is.finite(scl) | scl == 0] <- 1
  for (v in covars) {
    frames$fit[[paste0(v, "_z")]]  <- (frames$fit[[v]]  - ctr[v]) / scl[v]
    frames$pred[[paste0(v, "_z")]] <- (frames$pred[[v]] - ctr[v]) / scl[v]
  }
  frames$centre <- ctr; frames$scale <- scl
  frames
}


## --- 4. the model -----------------------------------------------------------
##
##   arrived ~ ns(doy, 3) + <covariates, standardised>
##
## ns(doy, 3) is the seasonal baseline: the shape of arrival hazard through the
## season with no environmental information. The covariates then shift that
## baseline up or down. cloglog makes this a discrete-time proportional-hazards
## model, so exp(coef) is a hazard ratio.
hazard_fit <- function(dat, covars, df_doy = 3) {
  f <- stats::as.formula(paste("arrived ~ ns(doy,", df_doy, ")",
                               if (length(covars))
                                 paste("+", paste0(covars, "_z", collapse = " + "))
                               else ""))
  suppressWarnings(glm(f, data = dat, family = binomial("cloglog")))
}


## --- 5. hazard -> predicted arrival date ------------------------------------
##
## S(t) = prod(1 - h(u)) for u <= t is the chance of STILL not having arrived.
## The predicted date is the first day where cumulative arrival probability
## passes 0.5. Returns NA when the window closes before reaching 0.5, rather
## than inventing a date.
predict_arrival <- function(fit, newdata, quantile = 0.5) {
  nd <- newdata[order(newdata$doy), ]
  h  <- as.numeric(predict(fit, nd, type = "response"))
  h[is.na(h)] <- 0
  surv <- cumprod(1 - h)
  cdf  <- 1 - surv
  idx  <- which(cdf >= quantile)[1]
  list(doy = if (is.na(idx)) NA_integer_ else nd$doy[idx],
       p_within_window = max(cdf), doys = nd$doy, cdf = cdf, hazard = h)
}


## --- 6. leave-one-year-out --------------------------------------------------
##
## Hold out a year, fit on the rest, predict that year's arrival date. Compare
## against climatology (the median arrival day of the training years), which is
## the benchmark any useful model must beat.
loyo <- function(frames, covars, df_doy = 3) {
  yrs <- sort(unique(frames$fit$year))
  out <- do.call(rbind, lapply(yrs, function(y) {
    tr <- frames$fit[frames$fit$year != y, ]
    te <- frames$pred[frames$pred$year == y, ]
    obs <- unique(frames$fit$arrival_doy_obs[frames$fit$year == y])
    p <- tryCatch({
      fit <- hazard_fit(tr, covars, df_doy)
      predict_arrival(fit, te)$doy
    }, error = function(e) NA_integer_)
    data.frame(year = y, observed = obs, predicted = p,
               climatology = stats::median(
                 unique(tr[, c("year", "arrival_doy_obs")])$arrival_doy_obs),
               stringsAsFactors = FALSE)
  }))
  out$err      <- out$predicted - out$observed
  out$err_clim <- out$climatology - out$observed
  out
}

score <- function(l) {
  ok <- !is.na(l$predicted)
  c(n = sum(ok),
    MAE       = mean(abs(l$err[ok])),
    RMSE      = sqrt(mean(l$err[ok]^2)),
    MAE_clim  = mean(abs(l$err_clim[ok])),
    RMSE_clim = sqrt(mean(l$err_clim[ok]^2)),
    skill     = 1 - mean(l$err[ok]^2) / mean(l$err_clim[ok]^2))
}



## ===========================================================================
## ABUNDANCE MODEL -- TOTAL_RETURN_TO_RIVER
##
## A year-level count, so one row per year, not one per day. That means the
## sample size really is the number of years (~45), and 3-4 predictors is the
## ceiling.
##
## Negative binomial with a log link, not Poisson: escapement counts are far
## more variable than Poisson allows (variance >> mean), and a Poisson fit
## would report standard errors several times too small.
##
## Predictors are summarised at DECISION_DOY, so only conditions known by that
## date enter -- a genuine pre-season forecast. jan_jun_mean_flow is already a
## year-level quantity; the others are read off the decision day.
## ===========================================================================

## One row per year: response, environmental predictors, and lagged returns.
build_year_table <- function(salmon, daily, covars = COVARS_ABUND,
                             decision_doy = DECISION_DOY, verbose = TRUE) {
  
  snap <- daily[daily$doy == decision_doy,
                c("year", intersect(covars, names(daily)))]
  y <- merge(salmon[, c("year", "arrival_doy", "total_return")], snap,
             by = "year", all.x = TRUE)
  
  ## jan_jun_mean_flow is constant within year; take it from anywhere in the year
  if ("jan_jun_mean_flow" %in% covars && !"jan_jun_mean_flow" %in% names(y)) {
    jj <- unique(daily[, c("year", "jan_jun_mean_flow")])
    y <- merge(y, jj, by = "year", all.x = TRUE)
  }
  
  y <- y[order(y$year), ]
  ## previous return and the brood-year return (4 yr for fall Chinook).
  ## Abundance is driven far more by spawners 3-5 years back and by ocean
  ## survival than by freshwater flow, so these are the honest benchmark.
  y$lag1_return  <- y$total_return[match(y$year - 1, y$year)]
  y$brood_return <- y$total_return[match(y$year - 4, y$year)]
  
  y <- y[is.finite(y$total_return) & y$total_return > 0, , drop = FALSE]
  if (verbose)
    message("  abundance table: ", nrow(y), " years with a positive return")
  y
}


## Fit. Negative binomial via MASS; falls back to a lognormal (Gaussian on
## log counts) if MASS is missing or the NB fit fails to converge.
fit_abundance <- function(dat, covars = COVARS_ABUND, include_lag = FALSE) {
  terms <- c(paste0(covars, "_z"), if (include_lag) "log_brood")
  f <- stats::as.formula(paste("total_return ~", paste(terms, collapse = " + ")))
  
  if (requireNamespace("MASS", quietly = TRUE)) {
    m <- tryCatch(suppressWarnings(MASS::glm.nb(f, data = dat)),
                  error = function(e) NULL)
    if (!is.null(m)) { attr(m, "family_used") <- "negative binomial"; return(m) }
    message("  glm.nb did not converge; using lognormal instead")
  }
  fl <- stats::as.formula(paste("log(total_return) ~", paste(terms, collapse = " + ")))
  m <- lm(fl, data = dat)
  attr(m, "family_used") <- "lognormal"
  m
}

## Predict on the count scale regardless of which family was fitted.
predict_abundance <- function(fit, newdata) {
  if (inherits(fit, "lm") && !inherits(fit, "glm"))
    exp(as.numeric(predict(fit, newdata)))    # lognormal (median, no smearing)
  else as.numeric(predict(fit, newdata, type = "response"))
}


## Leave-one-year-out. Scored on the LOG scale, because escapement spans
## orders of magnitude and an error of 5,000 fish means something very
## different on a run of 8,000 than on one of 90,000.
loyo_abundance <- function(dat, covars = COVARS_ABUND, include_lag = FALSE) {
  out <- do.call(rbind, lapply(seq_len(nrow(dat)), function(i) {
    tr <- dat[-i, ]; te <- dat[i, ]
    p <- tryCatch(predict_abundance(fit_abundance(tr, covars, include_lag), te),
                  error = function(e) NA_real_)
    data.frame(year = te$year, observed = te$total_return, predicted = p,
               ## benchmark: geometric mean of the training years
               climatology = exp(mean(log(tr$total_return))),
               stringsAsFactors = FALSE)
  }))
  out$log_err      <- log(out$predicted) - log(out$observed)
  out$log_err_clim <- log(out$climatology) - log(out$observed)
  out
}

score_abundance <- function(l) {
  ok <- is.finite(l$log_err)
  c(n = sum(ok),
    MAE_log      = mean(abs(l$log_err[ok])),
    RMSE_log     = sqrt(mean(l$log_err[ok]^2)),
    MAE_log_clim = mean(abs(l$log_err_clim[ok])),
    ## median multiplicative error: "typically out by a factor of X"
    fold_error   = exp(stats::median(abs(l$log_err[ok]))),
    fold_clim    = exp(stats::median(abs(l$log_err_clim[ok]))),
    skill        = 1 - mean(l$log_err[ok]^2) / mean(l$log_err_clim[ok]^2))
}


## --- 7. one stream, end to end ----------------------------------------------
run_stream <- function(row, covars = COVARS_NOTEMP, df_doy = 3,
                       covars_abund = COVARS_ABUND,
                       decision_doy = DECISION_DOY, verbose = TRUE) {
  if (verbose) message("\n=== ", row$stream, " ===")
  
  salmon <- read_salmon(row$salmon_url, verbose)
  flow   <- read_flow(row$flow_url, verbose = verbose)
  temp   <- read_temp(row$temp_url, verbose)
  
  daily  <- build_daily(flow, temp)
  frames <- build_frames(salmon, daily, covars, verbose = verbose)
  
  ## carry the observed arrival doy onto every row of its year, for scoring
  key <- setNames(salmon$arrival_doy, salmon$year)
  frames$fit$arrival_doy_obs  <- key[as.character(frames$fit$year)]
  frames$pred$arrival_doy_obs <- key[as.character(frames$pred$year)]
  
  ## drop rows missing any covariate; report the cost per predictor
  cover <- sapply(covars, function(v)
    length(unique(frames$fit$year[!is.na(frames$fit[[v]])])))
  if (verbose) {
    message("  years retained per predictor:")
    for (v in names(cover)) message("    ", format(v, width = 20), cover[v])
  }
  keep <- stats::complete.cases(frames$fit[, covars, drop = FALSE])
  frames$fit  <- frames$fit[keep, ]
  frames$pred <- frames$pred[stats::complete.cases(
    frames$pred[, covars, drop = FALSE]), ]
  frames$fit  <- frames$fit[frames$fit$year %in% frames$pred$year, ]
  
  n_yr <- length(unique(frames$fit$year))
  if (verbose) message("  usable years after covariate filtering: ", n_yr)
  if (n_yr < 10) warning("only ", n_yr, " years -- too few to fit reliably",
                         call. = FALSE)
  
  frames <- scale_covars(frames, covars)
  fit    <- hazard_fit(frames$fit, covars, df_doy)
  l      <- loyo(frames, covars, df_doy)
  
  ## ---- abundance ----
  ab <- tryCatch({
    yt <- build_year_table(salmon, daily, covars_abund, decision_doy, verbose)
    yt <- yt[stats::complete.cases(yt[, covars_abund, drop = FALSE]), ]
    if (nrow(yt) < 12) stop("only ", nrow(yt), " years with complete predictors")
    for (v in covars_abund) yt[[paste0(v, "_z")]] <- as.numeric(scale(yt[[v]]))
    yt$log_brood <- log(yt$brood_return)
    fit_a  <- fit_abundance(yt, covars_abund)
    loyo_a <- loyo_abundance(yt, covars_abund)
    ## brood-year benchmark, on the years where a brood return exists
    yb <- yt[is.finite(yt$log_brood), ]
    loyo_b <- if (nrow(yb) >= 12) loyo_abundance(yb, covars_abund, TRUE) else NULL
    list(table = yt, fit = fit_a, loyo = loyo_a, score = score_abundance(loyo_a),
         loyo_brood = loyo_b,
         score_brood = if (is.null(loyo_b)) NULL else score_abundance(loyo_b),
         covars = covars_abund)
  }, error = function(e) { message("  abundance model skipped: ",
                                   conditionMessage(e)); NULL })
  
  list(stream = row$stream, frames = frames, fit = fit, loyo = l,
       score = score(l), covars = covars, n_years = n_yr, abundance = ab)
}

run_streams <- function(streams = STREAMS, covars = COVARS_NOTEMP, ...) {  # ... passes covars_abund, decision_doy
  res <- lapply(seq_len(nrow(streams)), function(i)
    tryCatch(run_stream(streams[i, ], covars, ...),
             error = function(e) { message("FAILED: ", conditionMessage(e)); NULL }))
  names(res) <- streams$stream
  res[!vapply(res, is.null, logical(1))]
}


## --- 8. display -------------------------------------------------------------
report <- function(r) {
  cat("\n================ ", r$stream, " ================\n")
  cat("years:", r$n_years, " predictors:", paste(r$covars, collapse = ", "), "\n")
  
  cat("\n--- hazard ratios (per 1 SD of predictor) ---\n")
  cf <- summary(r$fit)$coefficients
  z  <- grep("_z$", rownames(cf))
  print(round(data.frame(HR = exp(cf[z, 1]), lower = exp(cf[z, 1] - 1.96 * cf[z, 2]),
                         upper = exp(cf[z, 1] + 1.96 * cf[z, 2]),
                         p = cf[z, 4]), 3))
  cat("HR > 1 = arrival more likely that day; CI spanning 1 = no evidence.\n")
  
  cat("\n--- does the environment beat seasonality alone? ---\n")
  null_fit <- hazard_fit(r$frames$fit, character(0))
  print(anova(null_fit, r$fit, test = "Chisq"))
  
  cat("\n--- leave-one-year-out, predicted arrival date ---\n")
  print(round(r$score, 3))
  cat("skill > 0 means better than the climatological median;",
      "<= 0 means it is not.\n")
  print(utils::head(r$loyo[, c("year", "observed", "predicted", "climatology", "err")], 10))
  
  op <- par(mfrow = c(1, 2)); on.exit(par(op))
  plot(r$loyo$observed, r$loyo$predicted, pch = 19,
       xlab = "observed doy", ylab = "predicted doy",
       main = paste(r$stream, "- timing LOYO")); abline(0, 1, col = "red")
  nd <- r$frames$pred[r$frames$pred$year == max(r$frames$pred$year), ]
  pa <- predict_arrival(r$fit, nd)
  plot(pa$doys, pa$cdf, type = "l", lwd = 2, ylim = c(0, 1),
       xlab = "day of year", ylab = "P(arrived by this day)",
       main = paste("cumulative arrival,", max(r$frames$pred$year)))
  abline(h = 0.5, lty = 2)
  
  ## ---------------- abundance ----------------
  a <- r$abundance
  if (is.null(a)) { cat("\n(no abundance model)\n"); return(invisible(r)) }
  
  cat("\n\n--- ABUNDANCE: TOTAL_RETURN_TO_RIVER ---\n")
  cat("years:", nrow(a$table), " family:", attr(a$fit, "family_used"),
      " predictors:", paste(a$covars, collapse = ", "), "\n")
  
  cf <- summary(a$fit)$coefficients
  z  <- grep("_z$|log_brood", rownames(cf))
  if (length(z)) {
    cat("\nmultiplicative effect per 1 SD of predictor:\n")
    print(round(data.frame(
      ratio = exp(cf[z, 1]),
      lower = exp(cf[z, 1] - 1.96 * cf[z, 2]),
      upper = exp(cf[z, 1] + 1.96 * cf[z, 2]),
      p     = cf[z, 4]), 3))
    cat("ratio 1.2 = 20% more fish per SD; CI spanning 1 = no evidence.\n")
  }
  
  cat("\n--- leave-one-year-out (log scale) ---\n")
  print(round(a$score, 3))
  cat("fold_error: typical multiplicative miss. 1.5 = out by ~50%.\n")
  cat("Compare fold_error with fold_clim; skill <= 0 means the geometric\n",
      "mean of past returns is the better forecast.\n")
  
  if (!is.null(a$score_brood)) {
    cat("\n--- with brood-year return (4 yr lag) added ---\n")
    print(round(a$score_brood, 3))
    cat("Abundance is driven mainly by spawners 3-5 years back and by ocean\n",
        "survival. If this is much better, flow was never the main driver.\n")
  }
  
  op2 <- par(mfrow = c(1, 2)); on.exit(par(op2), add = TRUE)
  plot(a$loyo$observed, a$loyo$predicted, pch = 19, log = "xy",
       xlab = "observed return", ylab = "predicted return",
       main = "abundance LOYO (log-log)"); abline(0, 1, col = "red")
  plot(a$table$year, a$table$total_return, type = "b", pch = 19, log = "y",
       xlab = "year", ylab = "total return to river",
       main = "observed run size")
  invisible(r)
}


## --- run --------------------------------------------------------------------
if (sys.nframe() == 0) {
  
  ## Default: no temperature. The Cowichan temperature record is ~2 years,
  ## so including it would reduce the model to ~2 usable years.
  ## Both models: arrival timing and run abundance.
  res <- run_streams(STREAMS, covars = COVARS_NOTEMP,
                     covars_abund = COVARS_ABUND)
  for (r in res) report(r)
  
  ## the year-level abundance table, if you want it directly
  # res[[1]]$abundance$table
  
  ## To see what including temperature costs:
  # res_t <- run_streams(STREAMS, covars = COVARS_FULL,
  #                      covars_abund = COVARS_ABUND_T)
}

## Performance graphics for arrival_model2.R
## Source after it, once you have `res <- run_streams(...)`.
##
##   plot_performance(res[[1]])   # everything, 6 panels
##
## Ordered by how much they tell you:
##   1. error vs baseline, per year   -- does it beat climatology, and when
##   2. PIT histogram                 -- are the probabilities honest
##   3. prediction intervals by year  -- sharpness and coverage together
##   4. abundance obs vs pred (log)   -- does it track peaks, or just the mean
##   5. abundance residuals over time -- drift, regime shifts
##   6. seasonal hazard curve         -- is the fitted biology plausible


## Re-run LOYO keeping the whole predicted distribution, not just the median.
loyo_full <- function(r) {
  frames <- r$frames; covars <- r$covars
  yrs <- sort(unique(frames$fit$year))
  lapply(yrs, function(y) {
    tr <- frames$fit[frames$fit$year != y, ]
    te <- frames$pred[frames$pred$year == y, ]
    obs <- unique(frames$fit$arrival_doy_obs[frames$fit$year == y])
    p <- tryCatch(predict_arrival(hazard_fit(tr, covars), te),
                  error = function(e) NULL)
    if (is.null(p)) return(NULL)
    q <- function(z) { i <- which(p$cdf >= z)[1]
    if (is.na(i)) NA_integer_ else p$doys[i] }
    list(year = y, observed = obs, doys = p$doys, cdf = p$cdf,
         median = q(0.5), q10 = q(0.10), q25 = q(0.25),
         q75 = q(0.75), q90 = q(0.90),
         ## PIT: where the observed day sat in the predicted distribution
         pit = if (obs %in% p$doys) p$cdf[match(obs, p$doys)] else NA_real_)
  })
}


## 1. Error against the baseline, year by year. The honest headline plot:
##    bars below zero are years the model beat climatology.
panel_error_vs_baseline <- function(l) {
  d <- l[!is.na(l$predicted), ]
  gain <- abs(d$err_clim) - abs(d$err)          # positive = model better
  cols <- ifelse(gain > 0, "steelblue", "firebrick")
  barplot(gain, names.arg = d$year, col = cols, border = NA, las = 2,
          cex.names = 0.6, ylab = "days better than climatology",
          main = "Model gain over baseline")
  abline(h = 0); abline(h = mean(gain), lty = 2)
  legend("topleft", bty = "n", cex = 0.7,
         legend = sprintf("mean gain %.1f d | won %d/%d yrs",
                          mean(gain), sum(gain > 0), nrow(d)))
}


## 2. PIT histogram. If the predicted distributions are honest, the observed
##    day falls uniformly across the predicted CDF. A U shape means
##    overconfident (intervals too narrow); a hump means underconfident.
panel_pit <- function(full) {
  pit <- vapply(full, function(x) if (is.null(x)) NA_real_ else x$pit, 1)
  pit <- pit[is.finite(pit)]
  h <- hist(pit, breaks = seq(0, 1, 0.1), plot = FALSE)
  barplot(h$counts, names.arg = sprintf("%.1f", head(h$breaks, -1)),
          col = "grey70", border = NA, las = 2, cex.names = 0.7,
          ylab = "years", main = "PIT (flat = well calibrated)")
  abline(h = length(pit) / 10, col = "red", lwd = 2, lty = 2)
  legend("topright", bty = "n", cex = 0.7, lty = 2, col = "red",
         legend = "expected if honest")
}


## 3. Prediction intervals with the observation on top. Shows sharpness and
##    coverage in one view: the bars should be narrow AND contain the points.
panel_intervals <- function(full) {
  f <- Filter(Negate(is.null), full)
  yr <- vapply(f, `[[`, 1, "year"); ob <- vapply(f, `[[`, 1, "observed")
  md <- vapply(f, function(x) as.numeric(x$median), 1)
  lo <- vapply(f, function(x) as.numeric(x$q10), 1)
  hi <- vapply(f, function(x) as.numeric(x$q90), 1)
  q1 <- vapply(f, function(x) as.numeric(x$q25), 1)
  q3 <- vapply(f, function(x) as.numeric(x$q75), 1)
  
  plot(yr, ob, type = "n", ylim = range(c(lo, hi, ob), na.rm = TRUE),
       xlab = "year", ylab = "arrival day of year",
       main = "Predicted interval vs observed")
  segments(yr, lo, yr, hi, col = "grey80", lwd = 3)
  segments(yr, q1, yr, q3, col = "grey50", lwd = 6)
  points(yr, md, pch = 19, col = "steelblue", cex = 0.8)
  points(yr, ob, pch = 4, lwd = 2, col = "black")
  cov <- mean(ob >= lo & ob <= hi, na.rm = TRUE)
  legend("topleft", bty = "n", cex = 0.7,
         legend = c(sprintf("80%% interval covers %.0f%% of years", 100 * cov),
                    "x = observed, dot = predicted median"))
}


## 4. Abundance: log-log, so proportional error reads correctly. The key
##    question is whether points track the 1:1 line or collapse onto a
##    horizontal band (= predicting the mean every year).
panel_abundance_scatter <- function(a) {
  d <- a$loyo[is.finite(a$loyo$predicted), ]
  plot(d$observed, d$predicted, log = "xy", pch = 19, col = "steelblue",
       xlab = "observed return", ylab = "predicted return",
       main = "Abundance, LOYO (log-log)")
  abline(0, 1, col = "red")
  abline(h = d$climatology[1], lty = 3, col = "grey40")
  legend("topleft", bty = "n", cex = 0.7,
         legend = c("red = perfect", "grey = predict-the-mean"))
}


## 5. Abundance over time: observed, predicted, baseline. Reveals whether the
##    model captures big years, and any regime shift or survey change.
panel_abundance_time <- function(a) {
  d <- a$loyo[is.finite(a$loyo$predicted), ]
  plot(d$year, d$observed, type = "b", pch = 19, log = "y",
       xlab = "year", ylab = "total return",
       main = "Run size: observed vs predicted")
  lines(d$year, d$predicted, type = "b", pch = 1, col = "steelblue", lty = 2)
  abline(h = d$climatology[1], col = "grey50", lty = 3)
  legend("topleft", bty = "n", cex = 0.7, col = c("black", "steelblue", "grey50"),
         lty = c(1, 2, 3), pch = c(19, 1, NA),
         legend = c("observed", "predicted", "geometric mean"))
}


## 6. The fitted seasonal hazard, with actual arrivals underneath. Not a
##    performance plot -- a sanity check that the shape is biologically sane.
panel_seasonal <- function(r) {
  nd <- r$frames$pred[r$frames$pred$year == max(r$frames$pred$year), ]
  for (v in r$covars) nd[[paste0(v, "_z")]] <- 0     # average conditions
  nd$hazard <- as.numeric(predict(r$fit, nd, type = "response"))
  plot(nd$doy, nd$hazard, type = "l", lwd = 2,
       xlab = "day of year", ylab = "daily arrival hazard",
       main = "Fitted seasonal timing")
  rug(unique(r$frames$fit$arrival_doy_obs), col = "firebrick", lwd = 2)
  legend("topright", bty = "n", cex = 0.7, legend = "ticks = observed arrivals")
}


plot_performance <- function(r) {
  full <- loyo_full(r)
  op <- par(mfrow = c(2, 3), mar = c(4.5, 4.5, 3, 1)); on.exit(par(op))
  panel_error_vs_baseline(r$loyo)
  panel_pit(full)
  panel_intervals(full)
  if (!is.null(r$abundance)) {
    panel_abundance_scatter(r$abundance)
    panel_abundance_time(r$abundance)
  } else { plot.new(); plot.new() }
  panel_seasonal(r)
  invisible(full)
}

## --- use --------------------------------------------------------------------
# full <- plot_performance(res[[1]])