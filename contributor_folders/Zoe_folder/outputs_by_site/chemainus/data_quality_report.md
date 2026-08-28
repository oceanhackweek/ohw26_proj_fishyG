# Data quality report — Chemainus River

## flow (Q)
- raw record: 40776 rows, 1914-05-13 to 2025-12-31
- gaps inserted by reindexing to a complete daily calendar: 0 day(s) across 0 range(s)
- implausible values flagged and set to NaN — negative_Q: 0
- implausible values flagged and set to NaN — Q_gt_50x_median: 2
- gaps longer than 2 days left as NaN (14 range(s)):
  - 1917-04-01 to 1952-11-30 (13028 days)
  - 1954-04-01 to 1954-06-30 (91 days)
  - 1972-01-01 to 1972-01-10 (10 days)
  - 1972-01-12 to 1972-02-23 (43 days)
  - 1972-02-25 to 1972-03-05 (10 days)
  - 1972-03-07 to 1972-04-25 (50 days)
  - 1972-04-27 to 1972-06-08 (43 days)
  - 1972-06-10 to 1972-08-08 (60 days)
  - 1972-08-10 to 1972-09-14 (36 days)
  - 1972-09-16 to 1972-11-05 (51 days)
  - 1973-11-09 to 1973-11-14 (6 days)
  - 1973-11-29 to 1973-12-27 (29 days)
  - 1974-01-08 to 1974-01-30 (23 days)
  - 1974-11-01 to 1974-12-19 (49 days)

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
- 1960-01-01 to 2025-12-31

## Spawning record
- 46 spawning-count rows, years 1962–2024

## Usable record (binding constraint on everything downstream)
- **usable years: 46**
- **usable spawning events: 46** (one arrival per usable year)
- years: [1962, 1967, 1968, 1969, 1970, 1971, 1972, 1973, 1974, 1975, 1976, 1977, 1978, 1979, 1980, 1981, 1982, 1983, 1984, 1985, 1986, 1987, 1988, 1989, 1990, 1991, 1992, 1993, 1994, 1995, 1996, 1999, 2002, 2004, 2005, 2006, 2007, 2008, 2009, 2011, 2015, 2018, 2020, 2022, 2023, 2024]

## Target construction
- retained years: 30 / 46
- retained years list: [np.int64(1962), np.int64(1967), np.int64(1968), np.int64(1969), np.int64(1970), np.int64(1971), np.int64(1974), np.int64(1975), np.int64(1976), np.int64(1977), np.int64(1982), np.int64(1983), np.int64(1985), np.int64(1987), np.int64(1988), np.int64(1991), np.int64(1995), np.int64(1996), np.int64(2005), np.int64(2006), np.int64(2007), np.int64(2008), np.int64(2009), np.int64(2011), np.int64(2015), np.int64(2018), np.int64(2020), np.int64(2022), np.int64(2023), np.int64(2024)]
- total rows: 560, positive rows: 30

### Years dropped at target-construction stage (16)
- 1972: 2 day(s) in [1972-09-01, 1972-09-02] have NaN feature(s)
- 1973: arrival 1973-08-28 falls outside season window [1973-09-01, 1973-12-15]
- 1978: arrival 1978-08-07 falls outside season window [1978-09-01, 1978-12-15]
- 1979: arrival 1979-08-25 falls outside season window [1979-09-01, 1979-12-15]
- 1980: arrival 1980-08-05 falls outside season window [1980-09-01, 1980-12-15]
- 1981: arrival 1981-08-05 falls outside season window [1981-09-01, 1981-12-15]
- 1984: arrival 1984-08-25 falls outside season window [1984-09-01, 1984-12-15]
- 1986: arrival 1986-08-15 falls outside season window [1986-09-01, 1986-12-15]
- 1989: arrival 1989-08-25 falls outside season window [1989-09-01, 1989-12-15]
- 1990: arrival 1990-08-25 falls outside season window [1990-09-01, 1990-12-15]
- 1992: arrival 1992-08-20 falls outside season window [1992-09-01, 1992-12-15]
- 1993: arrival 1993-07-18 falls outside season window [1993-09-01, 1993-12-15]
- 1994: arrival 1994-08-20 falls outside season window [1994-09-01, 1994-12-15]
- 1999: arrival 1999-08-19 falls outside season window [1999-09-01, 1999-12-15]
- 2002: arrival 2002-08-07 falls outside season window [2002-09-01, 2002-12-15]
- 2004: arrival 2004-08-20 falls outside season window [2004-09-01, 2004-12-15]


## Target construction
- retained years: 44 / 46
- retained years list: [np.int64(1962), np.int64(1967), np.int64(1968), np.int64(1969), np.int64(1970), np.int64(1971), np.int64(1973), np.int64(1974), np.int64(1975), np.int64(1976), np.int64(1977), np.int64(1978), np.int64(1979), np.int64(1980), np.int64(1981), np.int64(1982), np.int64(1983), np.int64(1984), np.int64(1985), np.int64(1986), np.int64(1987), np.int64(1988), np.int64(1989), np.int64(1990), np.int64(1991), np.int64(1992), np.int64(1994), np.int64(1995), np.int64(1996), np.int64(1999), np.int64(2002), np.int64(2004), np.int64(2005), np.int64(2006), np.int64(2007), np.int64(2008), np.int64(2009), np.int64(2011), np.int64(2015), np.int64(2018), np.int64(2020), np.int64(2022), np.int64(2023), np.int64(2024)]
- total rows: 1736, positive rows: 44

### Years dropped at target-construction stage (2)
- 1972: 33 day(s) in [1972-08-01, 1972-09-02] have NaN feature(s)
- 1993: arrival 1993-07-18 falls outside season window [1993-08-01, 1993-12-15]
