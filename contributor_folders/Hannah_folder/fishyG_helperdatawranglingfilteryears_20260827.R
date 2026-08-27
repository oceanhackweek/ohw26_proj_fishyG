## Drop every row belonging to a year whose arrival (arrived == 1) occurred
## before `min_doy`. Use `group` (e.g. "stream") if the table holds more than
## one river, so a bad year on one stream doesn't remove that year everywhere.

drop_early_arrival_years <- function(df, min_doy = 182, group = NULL,
                                     verbose = TRUE) {
  
  need <- c("year", "doy", "arrived")
  miss <- setdiff(need, names(df))
  if (length(miss)) stop("missing column(s): ", paste(miss, collapse = ", "))
  if (!is.null(group) && !group %in% names(df))
    stop("group column '", group, "' not found")
  
  key <- if (is.null(group)) as.character(df$year)
  else paste(df[[group]], df$year, sep = " | ")
  
  bad <- unique(key[df$arrived == 1 & df$doy < min_doy])
  
  if (verbose) {
    if (!length(bad)) {
      message("no years with arrival before doy ", min_doy)
    } else {
      hits <- df[df$arrived == 1 & df$doy < min_doy,
                 intersect(c(group, "year", "doy", "date"), names(df)),
                 drop = FALSE]
      message(length(bad), " year(s) with early arrival, removing ",
              sum(key %in% bad), " of ", nrow(df), " rows:")
      print(hits[order(hits$doy), ], row.names = FALSE)
    }
  }
  
  out <- df[!key %in% bad, , drop = FALSE]
  rownames(out) <- NULL
  out
}


## --- use -------------------------------------------------------------------
# hz <- read.csv("hazard_table.csv", stringsAsFactors = FALSE)
# hz <- drop_early_arrival_years(hz)                     # single stream
# hz <- drop_early_arrival_years(hz, group = "stream")   # multi-stream
#
## years that remain
# sort(unique(hz$year))


###Run it on the previously saved hazard tables for each stream
read.csv("/home/jovyan/Desktop/fishyG/data/stream_hazard_data/chemainus_hazard_data.csv") -> chemainus
read.csv("/home/jovyan/Desktop/fishyG/data/stream_hazard_data/cowichan_hazard_data.csv") -> cowichan
read.csv("/home/jovyan/Desktop/fishyG/data/stream_hazard_data/lilqualicum_hazard_data.csv") ->lilc
read.csv("/home/jovyan/Desktop/fishyG/data/stream_hazard_data/nanaimo_hazard_data.csv") -> nanaimo

drop_early_arrival_years(chemainus) %>% dim() #no years, dim3714 16 before & after drop, no change
drop_early_arrival_years(cowichan) %>% dim() #no years, dim 907 16 before & after
drop_early_arrival_years(lilc) %>% dim() #no years, dim 2274 16
drop_early_arrival_years(nanaimo) %>% dim() #2 years early arrival (1993 doy 4, 1979 doy 60)
drop_early_arrival_years(nanaimo) %>% write.csv(file = "/home/jovyan/Desktop/fishyG/data/stream_hazard_data/nanaimo_filteredyears_hazard_data.csv")

#done!