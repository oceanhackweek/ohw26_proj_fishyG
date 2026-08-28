"""Plots for the EVIMI/Chinook regional trend reference table.

Reads outputs/regional_trends_evi_chinook.csv (built by
build_regional_trends.py from the PSF State of Salmon dataset) and produces
two figures:

  regional_trends_timeseries.png -- raw + smoothed abundance with both fitted
    trend lines (short = most recent 3 generations, long = entire record)
    and their 95% intervals, one panel per metric (spawners, run size).

  regional_trends_anomaly.png -- per cent anomaly from the long-term average
    by year, diverging color by sign, one panel per metric.

Run:
    python contributor_folders/Zoe_folder/src/plot_regional_trends.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ZOE_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ZOE_ROOT / "outputs" / "regional_trends_evi_chinook.csv"
OUT_DIR = ZOE_ROOT / "outputs"

METRIC_ORDER = ["spawners", "runsize"]
METRIC_LABELS = {"spawners": "Spawners", "runsize": "Run size"}

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
RED = "#e34948"
GRAY = "#898781"


def plot_timeseries(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(len(METRIC_ORDER), 1, figsize=(10, 8), sharex=True)

    for ax, metric in zip(axes, METRIC_ORDER):
        sub = df[df["metric"] == metric].sort_values("year")

        ax.fill_between(
            sub["year"], sub["long_trend_fit_lwr"], sub["long_trend_fit_upr"],
            color=AQUA, alpha=0.15, linewidth=0,
        )
        ax.plot(sub["year"], sub["long_trend_fit"], color=AQUA, linewidth=2, label="long-term trend (full record)")

        ax.fill_between(
            sub["year"], sub["short_trend_fit_lwr"], sub["short_trend_fit_upr"],
            color=ORANGE, alpha=0.2, linewidth=0,
        )
        ax.plot(sub["year"], sub["short_trend_fit"], color=ORANGE, linewidth=2, label="recent trend (last 3 generations)")

        ax.plot(sub["year"], sub["smoothed_value"], color=BLUE, linewidth=1.5, label="smoothed abundance")
        ax.scatter(sub["year"], sub["raw_value"], color=BLUE, s=14, alpha=0.5, zorder=3, label="raw abundance")

        cat_label = {"arrow-up": "increasing", "arrow-down": "decreasing", "arrows-left-right": "stable"}
        row = sub.iloc[-1]
        annotation = (
            f"short-term: {row['short_trend'] * 100:+.1f}%/yr ({cat_label.get(row['short_trend_cat'], row['short_trend_cat'])})\n"
            f"long-term: {row['long_trend'] * 100:+.1f}%/yr ({cat_label.get(row['long_trend_cat'], row['long_trend_cat'])})\n"
            f"current status: {row['current_status'] * 100:+.0f}% vs. long-term average"
        )
        ax.text(
            0.02, 0.97, annotation, transform=ax.transAxes, fontsize=9,
            va="top", ha="left", color="#52514e",
            bbox=dict(boxstyle="round", facecolor="#fcfcfb", edgecolor="#e1e0d9"),
        )

        ax.set_ylabel(f"{METRIC_LABELS[metric]}")
        ax.set_title(METRIC_LABELS[metric])
        ax.set_ylim(bottom=0)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("East Vancouver Island & Mainland Inlets — Chinook: abundance and fitted trends", fontsize=13)
    axes[-1].set_xlabel("year")
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def plot_anomaly(df: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(len(METRIC_ORDER), 1, figsize=(10, 7), sharex=True)

    for ax, metric in zip(axes, METRIC_ORDER):
        sub = df[df["metric"] == metric].sort_values("year").dropna(subset=["anomaly_pct"])
        colors = [BLUE if v >= 0 else RED for v in sub["anomaly_pct"]]
        ax.bar(sub["year"], sub["anomaly_pct"], color=colors, width=0.8)
        ax.axhline(0, color=GRAY, linewidth=1, linestyle="--")
        ax.set_ylabel("anomaly (%)")
        ax.set_title(METRIC_LABELS[metric])

    fig.suptitle(
        "East Vancouver Island & Mainland Inlets — Chinook: per cent anomaly from long-term average",
        fontsize=13,
    )
    axes[-1].set_xlabel("year")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def main():
    df = pd.read_csv(CSV_PATH)
    plot_timeseries(df, OUT_DIR / "regional_trends_timeseries.png")
    plot_anomaly(df, OUT_DIR / "regional_trends_anomaly.png")


if __name__ == "__main__":
    main()
