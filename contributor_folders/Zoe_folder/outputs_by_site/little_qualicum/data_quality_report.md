# Data quality report — Little Qualicum River

## flow (Q)
- raw record: 23468 rows, 1960-10-01 to 2024-12-31
- gaps inserted by reindexing to a complete daily calendar: 0 day(s) across 0 range(s)
- implausible values flagged and set to NaN — negative_Q: 0
- implausible values flagged and set to NaN — Q_gt_50x_median: 0
- gaps longer than 2 days left as NaN (3 range(s)):
  - 1963-10-01 to 1963-11-17 (48 days)
  - 1987-01-01 to 2012-07-25 (9338 days)
  - 2018-01-01 to 2018-12-30 (364 days)

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
- 1960-10-01 to 2024-12-31

## Spawning record
- 47 spawning-count rows, years 1953–2025

## Usable record (binding constraint on everything downstream)
- **usable years: 45**
- **usable spawning events: 45** (one arrival per usable year)
- years: [1967, 1968, 1969, 1971, 1972, 1973, 1974, 1975, 1976, 1977, 1978, 1981, 1982, 1983, 1984, 1985, 1986, 1987, 1988, 1989, 1990, 1993, 1994, 1995, 1996, 1997, 1998, 2003, 2004, 2008, 2009, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]

## Target construction
- retained years: 27 / 47
- retained years list: [np.int64(1967), np.int64(1968), np.int64(1969), np.int64(1971), np.int64(1972), np.int64(1973), np.int64(1974), np.int64(1975), np.int64(1976), np.int64(1977), np.int64(1981), np.int64(1982), np.int64(1983), np.int64(1984), np.int64(1985), np.int64(1986), np.int64(2013), np.int64(2014), np.int64(2015), np.int64(2016), np.int64(2017), np.int64(2019), np.int64(2020), np.int64(2021), np.int64(2022), np.int64(2023), np.int64(2024)]
- total rows: 1089, positive rows: 27

### Years dropped at target-construction stage (20)
- 1953: no environmental record covering the season window
- 1978: arrival 1978-07-01 falls outside season window [1978-08-01, 1978-12-15]
- 1987: 59 day(s) in [1987-08-01, 1987-09-28] have NaN feature(s)
- 1988: 51 day(s) in [1988-08-01, 1988-09-20] have NaN feature(s)
- 1989: 51 day(s) in [1989-08-01, 1989-09-20] have NaN feature(s)
- 1990: 51 day(s) in [1990-08-01, 1990-09-20] have NaN feature(s)
- 1993: 1 day(s) in [1993-08-01, 1993-08-01] have NaN feature(s)
- 1994: 1 day(s) in [1994-08-01, 1994-08-01] have NaN feature(s)
- 1995: 15 day(s) in [1995-08-01, 1995-08-15] have NaN feature(s)
- 1996: 32 day(s) in [1996-08-01, 1996-09-01] have NaN feature(s)
- 1997: arrival 1997-07-01 falls outside season window [1997-08-01, 1997-12-15]
- 1998: 42 day(s) in [1998-08-01, 1998-09-11] have NaN feature(s)
- 2003: 70 day(s) in [2003-08-01, 2003-10-09] have NaN feature(s)
- 2004: 81 day(s) in [2004-08-01, 2004-10-20] have NaN feature(s)
- 2008: 42 day(s) in [2008-08-01, 2008-09-11] have NaN feature(s)
- 2009: 68 day(s) in [2009-08-01, 2009-10-07] have NaN feature(s)
- 2011: 66 day(s) in [2011-08-01, 2011-10-05] have NaN feature(s)
- 2012: 7 day(s) in [2012-08-01, 2012-10-03] have NaN feature(s)
- 2018: 48 day(s) in [2018-08-01, 2018-09-17] have NaN feature(s)
- 2025: 36 day(s) in [2025-08-01, 2025-09-05] have NaN feature(s)
