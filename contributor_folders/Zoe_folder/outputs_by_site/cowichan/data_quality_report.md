# Data quality report — Cowichan River

## flow (Q)
- raw record: 23742 rows, 1960-01-01 to 2024-12-31
- gaps inserted by reindexing to a complete daily calendar: 0 day(s) across 0 range(s)
- implausible values flagged and set to NaN — negative_Q: 0
- implausible values flagged and set to NaN — Q_gt_50x_median: 0
- gaps longer than 2 days left as NaN (4 range(s)):
  - 1961-10-01 to 1961-11-30 (61 days)
  - 1963-08-18 to 1964-01-12 (148 days)
  - 1964-01-14 to 1964-04-05 (83 days)
  - 2003-09-28 to 2003-10-06 (9 days)

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
- 1960-01-01 to 2024-12-31

## Spawning record
- 18 spawning-count rows, years 2002–2025

## Usable record (binding constraint on everything downstream)
- **usable years: 17**
- **usable spawning events: 17** (one arrival per usable year)
- years: [2002, 2005, 2009, 2010, 2011, 2012, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

## Target construction
- retained years: 17 / 18
- retained years list: [np.int64(2002), np.int64(2005), np.int64(2009), np.int64(2010), np.int64(2011), np.int64(2012), np.int64(2014), np.int64(2015), np.int64(2016), np.int64(2017), np.int64(2018), np.int64(2019), np.int64(2020), np.int64(2021), np.int64(2022), np.int64(2023), np.int64(2024)]
- total rows: 648, positive rows: 17

### Years dropped at target-construction stage (1)
- 2025: 39 day(s) in [2025-08-01, 2025-09-08] have NaN feature(s)
