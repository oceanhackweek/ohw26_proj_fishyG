"""Discrete-time survival target construction.

Question asked: "does the run start today, given it has not started yet?"
Not: "will a run start this year" (that's not a per-day question) and not
"label every day 0/1 including after arrival" (the data can't answer whether
the run has "stopped" on any given day).

For each year:
  1. Subset to the season window [SEASON_START, SEASON_END].
  2. Label started=1 on the arrival date, 0 on every prior day in the window.
  3. Drop all days after the arrival date.
  4. If the arrival date falls outside the window, exclude the year and say
     why -- never clip it silently.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    FEATURE_COLUMNS,
    INTERIM_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    SEASON_END_MONTH_DAY,
    SEASON_START_MONTH_DAY,
)


def season_window(year: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year, *SEASON_START_MONTH_DAY)
    end = pd.Timestamp(year, *SEASON_END_MONTH_DAY)
    return start, end


def build_target_table(
    daily_features: pd.DataFrame, spawning: pd.DataFrame
) -> tuple[pd.DataFrame, list[tuple[int, str]]]:
    dropped: list[tuple[int, str]] = []
    rows = []

    for _, row in spawning.iterrows():
        year = int(row["year"])
        arrival = row["arrival_date"]

        if pd.isna(arrival):
            dropped.append((year, "no arrival date on record"))
            continue

        win_start, win_end = season_window(year)
        if arrival < win_start or arrival > win_end:
            dropped.append(
                (
                    year,
                    f"arrival {arrival.date()} falls outside season window "
                    f"[{win_start.date()}, {win_end.date()}]",
                )
            )
            continue

        year_df = daily_features[
            (daily_features["date"] >= win_start) & (daily_features["date"] <= arrival)
        ].copy()

        if year_df.empty:
            dropped.append((year, "no environmental record covering the season window"))
            continue

        if year_df["date"].max() != arrival:
            dropped.append((year, f"arrival date {arrival.date()} missing from daily environmental record"))
            continue

        if year_df[FEATURE_COLUMNS].isna().any().any():
            n_nan_rows = year_df[FEATURE_COLUMNS].isna().any(axis=1).sum()
            dropped.append(
                (year, f"{n_nan_rows} day(s) in [{win_start.date()}, {arrival.date()}] have NaN feature(s)")
            )
            continue

        year_df["started"] = 0
        year_df.loc[year_df["date"] == arrival, "started"] = 1
        year_df["year"] = year
        year_df["total_count"] = row["total_count"]
        rows.append(year_df)

    if not rows:
        raise RuntimeError("No years survived target construction -- check season window / data gaps")

    out = pd.concat(rows, ignore_index=True)
    return out, dropped


def main():
    daily_features = pd.read_parquet(INTERIM_DIR / "daily_features.parquet")
    spawning = pd.read_parquet(INTERIM_DIR / "spawning.parquet")

    table, dropped = build_target_table(daily_features, spawning)

    retained_years = sorted(table["year"].unique())
    print(f"Retained years: {len(retained_years)} / {len(spawning)} spawning-record years")
    print(f"Retained years list: {retained_years}")
    if dropped:
        print(f"\nDropped {len(dropped)} year(s):")
        for yr, reason in dropped:
            print(f"  {yr}: {reason}")

    positives_per_year = table.groupby("year")["started"].sum()
    assert (positives_per_year == 1).all(), (
        f"expected exactly one positive per retained year, got:\n{positives_per_year[positives_per_year != 1]}"
    )
    assert not table[FEATURE_COLUMNS].isna().any().any(), "NaN found in feature columns after filtering"

    print(f"\nTotal rows: {len(table)}  |  positive rows: {int(table['started'].sum())}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    keep_cols = ["year", "date"] + FEATURE_COLUMNS + ["doy", "started", "total_count"]
    table[keep_cols].to_parquet(PROCESSED_DIR / "features.parquet", index=False)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUTS_DIR / "data_quality_report.md", "a") as f:
        f.write("\n\n## Target construction\n")
        f.write(f"- retained years: {len(retained_years)} / {len(spawning)}\n")
        f.write(f"- retained years list: {retained_years}\n")
        f.write(f"- total rows: {len(table)}, positive rows: {int(table['started'].sum())}\n")
        if dropped:
            f.write(f"\n### Years dropped at target-construction stage ({len(dropped)})\n")
            for yr, reason in dropped:
                f.write(f"- {yr}: {reason}\n")

    return table, dropped


if __name__ == "__main__":
    main()
