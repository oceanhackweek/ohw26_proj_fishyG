"""Static daily predicted-arrival-probability plot for one year, all four sites.

Complements the timing-error boxplots (which summarize *error*) and
cross_site_summary.png (which summarizes AP/AUC) with the intuitive "what did
the model actually see, day by day" view: each site's out-of-fold predicted
probability curve for one season, against the real arrival date.

TARGET_YEAR is 2024, not 2025: 2025 is not usable at ANY site. Chemainus and
Nanaimo have no 2025 salmon record at all; Cowichan and Little Qualicum do
have a 2025 record, but it's dropped at target construction (NaN
environmental features in the season window -- see each site's
data_quality_report.md). 2024 is the most recent year retained AND tested at
all four sites.

Reuses plot_cross_site.compute_all() (which reuses model.py's per-site CV
code directly) so these curves come from the exact same fitted folds as the
other cross-site figures -- not a parallel reimplementation.

Run:
    cd contributor_folders/Zoe_folder
    python src/plot_year_predictions.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from config import FIGURES_DIR
from plot_cross_site import BASELINE_COLOR, RUN_COLORS, RUN_ORDER, compute_all

TARGET_YEAR = 2024


def plot_year(all_results: dict, year: int, out_path) -> None:
    sites = list(all_results.keys())
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharey=True)

    for ax, site in zip(axes.flat, sites):
        data = all_results[site]
        df = data["df"]
        year_df = df[df["year"] == year].sort_values("date")
        if year_df.empty:
            ax.set_title(f"{site}: no {year} data")
            continue

        arrival_date = year_df.loc[year_df["started"] == 1, "date"].iloc[0]

        for name in RUN_ORDER:
            oof = data["runs"][name]["oof_proba"]
            proba = oof[year_df.index]
            ax.plot(year_df["date"], proba, label=name, color=RUN_COLORS[name], linewidth=1.8)

        ax.axvline(arrival_date, color="black", linestyle="--", linewidth=1.3, label="actual arrival")

        baseline_row = data["baseline"][data["baseline"]["year"] == year]
        if not baseline_row.empty:
            ax.axvline(
                baseline_row["pred_date"].iloc[0],
                color=BASELINE_COLOR,
                linestyle=":",
                linewidth=1.3,
                label="baseline predicted",
            )

        ax.set_title(f"{site} ({data['cv_method']}) -- {year}")
        ax.set_ylabel("predicted P(arrival today)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.tick_params(axis="x", labelrotation=30)

    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle(f"Daily predicted arrival probability vs. actual arrival -- {year}", fontsize=13)
    fig.tight_layout(rect=[0, 0.05, 1, 0.96])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def main():
    all_results = compute_all()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_year(all_results, TARGET_YEAR, FIGURES_DIR / f"cross_site_predictions_{TARGET_YEAR}.png")


if __name__ == "__main__":
    main()
