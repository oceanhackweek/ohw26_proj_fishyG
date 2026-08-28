"""Regional published-trend context for the four project rivers.

Nanaimo, Chemainus, Cowichan, and Little Qualicum Rivers (see
data/river_coordinates.csv, all ~48.7-49.4N on the Strait of Georgia side of
Vancouver Island) fall within the Pacific Salmon Foundation's "East Vancouver
Island & Mainland Inlets" (EVIMI) region as defined in the Pacific Salmon
Explorer / State of Salmon Report. The project targets Fall Chinook (see
README.md), matching species_name="Chinook" in the PSF tables.

There is no river-level trend in the published data -- PSF aggregates
spawner/run-size time series to the region level (data/Trend_resources/
Metadata551.pdf describes dataset551_sps-data.csv, the per-year time series
with fitted trend lines; Metadata552.pdf describes dataset552_sps-metrics.csv,
the region-level summary stats). This script pulls the EVIMI/Chinook slice
out of both tables and joins them into one tidy, per-year reference CSV so
our four rivers' results can later be compared against the region they
belong to -- one row per (metric, year):

  - metric: "spawners" or "runsize"
  - raw_value / smoothed_value / anomaly_pct: that year's observed data
  - short_trend_fit(_lwr/_upr): the fitted value (and 95% interval) from the
    linear trend over the most recent 3 generations -- NaN before that window
  - long_trend_fit(_lwr/_upr): the fitted value from the linear trend over
    the entire record
  - short_trend / long_trend / *_cat: the region-level annualized % change
    and up/down/stable category (constant across years, repeated from
    dataset552 for convenience -- these are summary stats, not per-year fits)
  - current_status, current_abundance, average_abundance, gen_length,
    nyears, rangeyears: region-level context, also repeated from dataset552

-989898 (PSF's null sentinel) is converted to NaN throughout.

Run:
    python contributor_folders/Zoe_folder/src/build_regional_trends.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
ZOE_ROOT = Path(__file__).resolve().parents[1]
TREND_DIR = REPO_ROOT / "data" / "Trend_resources"
OUT_PATH = ZOE_ROOT / "outputs" / "regional_trends_evi_chinook.csv"

REGION = "East Vancouver Island & Mainland Inlets"
SPECIES = "Chinook"
NULL_CODE = -989898

COLUMN_ORDER = [
    "region", "species_name", "metric", "year",
    "raw_value", "smoothed_value", "anomaly_pct",
    "short_trend_fit", "short_trend_fit_lwr", "short_trend_fit_upr",
    "long_trend_fit", "long_trend_fit_lwr", "long_trend_fit_upr",
    "short_trend", "short_trend_cat", "long_trend", "long_trend_cat",
    "current_status", "current_abundance", "current_abundance_year",
    "average_abundance", "previous_gen_abundance", "gen_length",
    "nyears", "rangeyears", "source_id", "datasetversion",
]


def _denull(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace(NULL_CODE, pd.NA)


def load_yearly() -> pd.DataFrame:
    """dataset551, filtered to EVIMI/Chinook and reshaped long by metric."""
    df = pd.read_csv(TREND_DIR / "dataset551_sps-data.csv")
    df = df[(df["region"] == REGION) & (df["species_name"] == SPECIES)]
    df = _denull(df)

    metric_cols = {
        "spawners": [
            "spawners", "smoothedspawners", "spawnersanomaly",
            "spawners_short_trend", "spawners_short_trend_lwr", "spawners_short_trend_upr",
            "spawners_long_trend", "spawners_long_trend_lwr", "spawners_long_trend_upr",
        ],
        "runsize": [
            "runsize", "smoothedrunsize", "runsizeanomaly",
            "runsize_short_trend", "runsize_short_trend_lwr", "runsize_short_trend_upr",
            "runsize_long_trend", "runsize_long_trend_lwr", "runsize_long_trend_upr",
        ],
    }
    renamed_names = [
        "raw_value", "smoothed_value", "anomaly_pct",
        "short_trend_fit", "short_trend_fit_lwr", "short_trend_fit_upr",
        "long_trend_fit", "long_trend_fit_lwr", "long_trend_fit_upr",
    ]

    parts = []
    for metric, cols in metric_cols.items():
        sub = df[["region", "species_name", "year", "source_id"] + cols].rename(
            columns=dict(zip(cols, renamed_names))
        )
        sub.insert(2, "metric", metric)
        parts.append(sub)

    return pd.concat(parts, ignore_index=True)


def load_summary() -> pd.DataFrame:
    """dataset552, filtered to EVIMI/Chinook: one row per metric with
    region-level summary stats."""
    df = pd.read_csv(TREND_DIR / "dataset552_sps-metrics.csv")
    df = df[(df["region"] == REGION) & (df["species_name"] == SPECIES)]
    df = _denull(df)
    df = df.assign(metric=df["type"].map({"Spawners": "spawners", "Run Size": "runsize"}))
    return df.drop(columns=["region", "species_name", "type"])


def main():
    yearly = load_yearly()
    summary = load_summary()

    merged = yearly.merge(summary, on="metric", how="left")
    merged = merged[COLUMN_ORDER].sort_values(["metric", "year"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH} ({len(merged)} rows)")
    print(merged.groupby("metric")["year"].agg(["min", "max", "count"]))


if __name__ == "__main__":
    main()
