"""Load and validate raw data for one site (Little Qualicum River).

Produces a single continuous daily environmental series (Q, T, P) plus a
spawning-events table, and writes a data-quality report. Every validation
check prints its result; nothing proceeds silently past a failure.

Run directly to regenerate data/interim/daily_env.parquet,
data/interim/spawning.parquet and outputs/data_quality_report.md:

    python src/load.py
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import xarray as xr

from config import (
    FLOW_CSV,
    INTERIM_DIR,
    MAX_INTERP_GAP_DAYS,
    OUTPUTS_DIR,
    P_MIN,
    Q_MIN,
    Q_OUTLIER_MULTIPLE,
    SALMON_CSV,
    SITE_LAT,
    SITE_LON,
    SITE_NAME,
    T_MAX,
    T_MIN,
    WEATHER_NC,
)


@dataclass
class SeriesReport:
    name: str
    raw_n: int
    raw_start: pd.Timestamp
    raw_end: pd.Timestamp
    inserted_gap_days: int
    gap_ranges: list = field(default_factory=list)
    implausible: dict = field(default_factory=dict)
    long_gap_ranges: list = field(default_factory=list)


def _find_gap_ranges(full_index: pd.DatetimeIndex, present: pd.DatetimeIndex) -> list[tuple]:
    """Contiguous ranges of dates present in full_index but not in present."""
    missing = full_index.difference(present)
    if len(missing) == 0:
        return []
    missing = missing.sort_values()
    ranges = []
    start = prev = missing[0]
    for d in missing[1:]:
        if (d - prev).days == 1:
            prev = d
            continue
        ranges.append((start, prev))
        start = prev = d
    ranges.append((start, prev))
    return ranges


def _reindex_daily(df: pd.DataFrame, date_col: str, name: str) -> tuple[pd.DataFrame, SeriesReport]:
    df = df.sort_values(date_col).drop_duplicates(subset=date_col)
    full_index = pd.date_range(df[date_col].min(), df[date_col].max(), freq="D")
    gap_ranges = _find_gap_ranges(full_index, pd.DatetimeIndex(df[date_col]))
    report = SeriesReport(
        name=name,
        raw_n=len(df),
        raw_start=df[date_col].min(),
        raw_end=df[date_col].max(),
        inserted_gap_days=sum((r[1] - r[0]).days + 1 for r in gap_ranges),
        gap_ranges=gap_ranges,
    )
    df = df.set_index(date_col).reindex(full_index)
    df.index.name = date_col
    return df.reset_index(), report


def _interpolate_short_gaps(df: pd.DataFrame, value_col: str, report: SeriesReport) -> pd.DataFrame:
    """Linearly interpolate runs of <= MAX_INTERP_GAP_DAYS consecutive NaN.
    Longer runs are left as NaN in full and reported -- NOT partially filled.

    pandas' Series.interpolate(limit=N) fills only the first N points of any
    NaN run, however long, which would linearly bridge a 25-year gap with 2
    fabricated points. Each run's full length must be checked before any of
    it is filled.
    """
    date_col = df.columns[0]
    s = df[value_col].to_numpy(dtype=float, copy=True)
    dates = df[date_col].to_numpy()
    is_na = np.isnan(s)
    n = len(s)

    long_gap_ranges = []
    i = 0
    while i < n:
        if not is_na[i]:
            i += 1
            continue
        j = i
        while j < n and is_na[j]:
            j += 1
        gap_len = j - i  # NaN run occupies indices [i, j)
        has_left = i > 0
        has_right = j < n
        if gap_len <= MAX_INTERP_GAP_DAYS and has_left and has_right:
            s[i:j] = np.linspace(s[i - 1], s[j], gap_len + 2)[1:-1]
        else:
            long_gap_ranges.append((pd.Timestamp(dates[i]), pd.Timestamp(dates[j - 1]), gap_len))
        i = j
    report.long_gap_ranges = long_gap_ranges
    out = s
    df = df.copy()
    df[value_col] = out
    return df


def load_flow() -> tuple[pd.DataFrame, SeriesReport]:
    raw = pd.read_csv(FLOW_CSV, skiprows=1)
    raw.columns = [c.strip() for c in raw.columns]
    raw = raw[raw["PARAM"] == 1].copy()  # PARAM 1 = daily discharge (m3/s)
    if raw["ID"].nunique() != 1:
        raise ValueError(f"Expected a single flow station, found {raw['ID'].unique()}")
    raw["date"] = pd.to_datetime(raw["Date"], format="%Y/%m/%d")
    raw["Q"] = pd.to_numeric(raw["Value"], errors="raise")
    df = raw[["date", "Q"]]

    df, report = _reindex_daily(df, "date", "flow (Q)")

    negative = df["Q"] < Q_MIN
    n_negative = int(negative.sum())
    if n_negative:
        df.loc[negative, "Q"] = np.nan
    median_q = df["Q"].median()
    outlier = df["Q"] > Q_OUTLIER_MULTIPLE * median_q
    n_outlier = int(outlier.sum())
    if n_outlier:
        df.loc[outlier, "Q"] = np.nan
    report.implausible = {"negative_Q": n_negative, "Q_gt_50x_median": n_outlier}

    df = _interpolate_short_gaps(df, "Q", report)
    return df, report


def load_weather() -> tuple[pd.DataFrame, SeriesReport, SeriesReport]:
    ds = xr.open_dataset(WEATHER_NC)
    site = ds.sel(lat=SITE_LAT, lon=SITE_LON, method="nearest")
    nearest_lat, nearest_lon = float(site["lat"]), float(site["lon"])
    print(
        f"[load_weather] site ({SITE_LAT}, {SITE_LON}) -> nearest grid cell "
        f"({nearest_lat:.5f}, {nearest_lon:.5f})"
    )

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(site["time"].values).normalize(),
            "T": site["tavg"].values.astype(float),
            "P": site["pr"].values.astype(float),
        }
    )
    df = df.dropna(subset=["date"])

    df, report_t = _reindex_daily(df[["date", "T"]], "date", "temperature (T, tavg)")
    df_p, report_p = _reindex_daily(
        pd.DataFrame(
            {
                "date": pd.to_datetime(site["time"].values).normalize(),
                "P": site["pr"].values.astype(float),
            }
        ),
        "date",
        "precipitation (P, pr)",
    )

    t_bad = (df["T"] < T_MIN) | (df["T"] > T_MAX)
    n_t_bad = int(t_bad.sum())
    if n_t_bad:
        df.loc[t_bad, "T"] = np.nan
    report_t.implausible = {"T_out_of_[-20,40]C": n_t_bad}

    p_bad = df_p["P"] < P_MIN
    n_p_bad = int(p_bad.sum())
    if n_p_bad:
        df_p.loc[p_bad, "P"] = np.nan
    report_p.implausible = {"negative_P": n_p_bad}

    df = _interpolate_short_gaps(df, "T", report_t)
    df_p = _interpolate_short_gaps(df_p, "P", report_p)

    merged = df.merge(df_p, on="date", how="outer")
    return merged, report_t, report_p


def load_spawning() -> pd.DataFrame:
    raw = pd.read_csv(SALMON_CSV)
    expected_cols = {
        "WATERBODY",
        "ANALYSIS_YR",
        "SPECIES",
        "RUN_TYPE",
        "TOTAL_RETURN_TO_RIVER",
        "START_DTT",
        "STREAM_ARRIVAL_DT_FROM",
        "time_return",
    }
    missing = expected_cols - set(raw.columns)
    if missing:
        raise ValueError(f"Salmon CSV missing expected columns: {missing}")

    df = raw.copy()
    df["year"] = df["ANALYSIS_YR"].astype(int)
    df["arrival_date"] = pd.to_datetime(df["time_return"], errors="coerce")
    df["total_count"] = pd.to_numeric(df["TOTAL_RETURN_TO_RIVER"], errors="coerce")

    n_unparsed = int(df["arrival_date"].isna().sum())
    if n_unparsed:
        print(f"[load_spawning] WARNING: {n_unparsed} rows have an unparsable arrival date")

    mismatch = df["arrival_date"].dt.year != df["year"]
    n_mismatch = int(mismatch.sum())
    if n_mismatch:
        print(
            f"[load_spawning] WARNING: {n_mismatch} rows where arrival_date's year "
            f"differs from ANALYSIS_YR: {df.loc[mismatch, 'year'].tolist()}"
        )

    dup_years = df["year"][df["year"].duplicated()].tolist()
    if dup_years:
        print(f"[load_spawning] WARNING: duplicate ANALYSIS_YR rows: {dup_years}")

    out = df[["year", "arrival_date", "total_count"]].sort_values("year").reset_index(drop=True)
    return out


def build_daily_env() -> pd.DataFrame:
    flow_df, flow_report = load_flow()
    weather_df, t_report, p_report = load_weather()

    merged = flow_df.merge(weather_df, on="date", how="outer").sort_values("date").reset_index(drop=True)

    overlap_start = max(flow_report.raw_start, t_report.raw_start, p_report.raw_start)
    overlap_end = min(flow_report.raw_end, t_report.raw_end, p_report.raw_end)

    return merged, [flow_report, t_report, p_report], (overlap_start, overlap_end)


def write_report(env_reports, overlap, spawning_df, usable_years, dropped_years=None):
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# Data quality report — {SITE_NAME}\n"]

    for r in env_reports:
        lines.append(f"## {r.name}")
        lines.append(f"- raw record: {r.raw_n} rows, {r.raw_start.date()} to {r.raw_end.date()}")
        lines.append(
            f"- gaps inserted by reindexing to a complete daily calendar: "
            f"{r.inserted_gap_days} day(s) across {len(r.gap_ranges)} range(s)"
        )
        if r.gap_ranges:
            shown = r.gap_ranges[:20]
            for s, e in shown:
                lines.append(f"  - {s.date()} to {e.date()} ({(e - s).days + 1} day(s))")
            if len(r.gap_ranges) > len(shown):
                lines.append(f"  - ... and {len(r.gap_ranges) - len(shown)} more range(s)")
        if r.implausible:
            for k, v in r.implausible.items():
                lines.append(f"- implausible values flagged and set to NaN — {k}: {v}")
        if r.long_gap_ranges:
            lines.append(
                f"- gaps longer than {MAX_INTERP_GAP_DAYS} days left as NaN "
                f"({len(r.long_gap_ranges)} range(s)):"
            )
            for s, e, n in r.long_gap_ranges[:20]:
                lines.append(f"  - {s.date()} to {e.date()} ({n} days)")
        lines.append("")

    lines.append("## Overlap across environmental series")
    lines.append(f"- {overlap[0].date()} to {overlap[1].date()}")
    lines.append("")

    lines.append("## Spawning record")
    lines.append(f"- {len(spawning_df)} spawning-count rows, years {spawning_df['year'].min()}–{spawning_df['year'].max()}")
    lines.append("")

    lines.append("## Usable record (binding constraint on everything downstream)")
    lines.append(f"- **usable years: {len(usable_years)}**")
    lines.append(f"- **usable spawning events: {len(usable_years)}** (one arrival per usable year)")
    lines.append(f"- years: {sorted(usable_years)}")
    if dropped_years:
        lines.append("")
        lines.append("## Years dropped (arrival outside season window or no environmental coverage)")
        for yr, reason in dropped_years:
            lines.append(f"- {yr}: {reason}")

    report_text = "\n".join(lines)
    (OUTPUTS_DIR / "data_quality_report.md").write_text(report_text)
    print(report_text)
    return report_text


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    env_df, env_reports, overlap = build_daily_env()
    spawning_df = load_spawning()

    env_years = set(range(overlap[0].year, overlap[1].year + 1))
    spawning_years = set(spawning_df["year"])
    usable_years = sorted(env_years & spawning_years)

    print("\n" + "=" * 60)
    print(f"USABLE YEARS: {len(usable_years)}  |  SPAWNING EVENTS: {len(spawning_df[spawning_df['year'].isin(usable_years)])}")
    print("=" * 60 + "\n")

    env_df.to_parquet(INTERIM_DIR / "daily_env.parquet", index=False)
    spawning_df.to_parquet(INTERIM_DIR / "spawning.parquet", index=False)

    write_report(env_reports, overlap, spawning_df, usable_years)

    return env_df, spawning_df, usable_years


if __name__ == "__main__":
    main()
