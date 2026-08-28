# Data quality report — Nanaimo River

## flow (Q)
- raw record: 21767 rows, 1965-05-29 to 2024-12-31
- gaps inserted by reindexing to a complete daily calendar: 0 day(s) across 0 range(s)
- implausible values flagged and set to NaN — negative_Q: 0
- implausible values flagged and set to NaN — Q_gt_50x_median: 0

## temperature (T, tavg)
- raw record: 24104 rows, 1960-01-01 to 2025-12-31
- gaps inserted by reindexing to a complete daily calendar: 3 day(s) across 3 range(s)
  - 2016-12-31 to 2016-12-31 (1 day(s))
  - 2020-12-31 to 2020-12-31 (1 day(s))
  - 2024-12-31 to 2024-12-31 (1 day(s))
- implausible values flagged and set to NaN — T_out_of_[-20,40]C: 0

## precipitation (P, pr)
- raw record: 24104 rows, 1960-01-01 to 2025-12-31
- gaps inserted by reindexing to a complete daily calendar: 3 day(s) across 3 range(s)
  - 2016-12-31 to 2016-12-31 (1 day(s))
  - 2020-12-31 to 2020-12-31 (1 day(s))
  - 2024-12-31 to 2024-12-31 (1 day(s))
- implausible values flagged and set to NaN — negative_P: 0

## Overlap across environmental series
- 1965-05-29 to 2024-12-31

## Spawning record
- 30 spawning-count rows, years 1979–2024

## Usable record (binding constraint on everything downstream)
- **usable years: 30**
- **usable spawning events: 30** (one arrival per usable year)
- years: [1979, 1984, 1986, 1987, 1988, 1989, 1990, 1993, 1994, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2024]

## Target construction
- retained years: 26 / 30
- retained years list: [np.int64(1984), np.int64(1987), np.int64(1988), np.int64(1989), np.int64(1990), np.int64(1994), np.int64(2003), np.int64(2004), np.int64(2005), np.int64(2006), np.int64(2007), np.int64(2008), np.int64(2009), np.int64(2010), np.int64(2011), np.int64(2012), np.int64(2013), np.int64(2014), np.int64(2015), np.int64(2016), np.int64(2018), np.int64(2019), np.int64(2020), np.int64(2021), np.int64(2022), np.int64(2024)]
- total rows: 887, positive rows: 26

### Years dropped at target-construction stage (4)
- 1979: arrival 1979-03-01 falls outside season window [1979-08-01, 1979-12-15]
- 1986: arrival 1986-07-25 falls outside season window [1986-08-01, 1986-12-15]
- 1993: arrival 1993-01-04 falls outside season window [1993-08-01, 1993-12-15]
- 2017: arrival 2018-02-21 falls outside season window [2017-08-01, 2017-12-15]
