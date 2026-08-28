"""Cross-river comparison of the salmon-arrival model.

Turns the four already-fitted per-river runs (outputs_by_site/<site>_data) into
two comparison figures plus a machine-readable metrics table, so the
day-of-year-dominance pattern documented in outputs_by_site/SUMMARY.md is
visible across rivers at a glance rather than read row-by-row from four
separate metrics.md files.

Each site uses its own CV strategy (see config.py's CV_METHOD comment for why
they differ): forward-chaining for Chemainus/Cowichan (long, mostly
continuous records -- "could this have been predicted at the time" is
meaningful), leave-one-era-out for Nanaimo/Little Qualicum (each has a real
multi-year hole splitting usable years into two disjoint eras). Reuses
model.py's RUNS / run_one / era_blocks / baseline_* functions directly so
these numbers are guaranteed to match the existing per-site metrics.md files
(same CV code, same SEED), not a parallel reimplementation.

Run:
    cd contributor_folders/Zoe_folder
    python src/plot_cross_site.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import ERA_GAP_YEARS, FIGURES_DIR, MIN_TRAIN_YEARS, ZOE_ROOT
from model import (
    RUNS,
    baseline_timing_errors,
    baseline_timing_errors_block,
    baseline_timing_errors_forward,
    era_blocks,
    run_one,
)

# site -> (outputs_by_site subdir, CV strategy for that site)
SITES = {
    "Chemainus": ("chemainus_data", "forward_chaining"),
    "Nanaimo": ("nanaimo_data", "logo_era"),
    "Cowichan": ("cowichan_data", "forward_chaining"),
    "Little Qualicum": ("little_qualicum_data", "logo_era"),
}

RUN_ORDER = ["env_only", "env_plus_doy", "doy_only"]
RUN_COLORS = {"env_only": "#2a78d6", "env_plus_doy": "#eb6834", "doy_only": "#1baf7a"}
BASELINE_COLOR = "#898781"
BASELINE_LABEL = "baseline (mean doy)"
CATEGORIES = RUN_ORDER + ["baseline"]
CATEGORY_COLORS = [RUN_COLORS[n] for n in RUN_ORDER] + [BASELINE_COLOR]
CATEGORY_LABELS = RUN_ORDER + [BASELINE_LABEL]

OUT_DIR = ZOE_ROOT / "outputs_by_site"


def compute_all() -> dict:
    """Per-site cross-validated evaluation for every (site, run) pair, using
    each site's own CV strategy (see SITES above).

    Returns {site: {"df": DataFrame, "runs": {run_name: run_one(...) dict}, "baseline": DataFrame, "cv_method": str}}.
    `df` is kept alongside the fitted results (each run's oof_proba is aligned to
    df's row order) so downstream consumers can re-derive per-day predictions
    without re-fitting.
    """
    all_results = {}
    for site, (dirname, cv_method) in SITES.items():
        path = OUT_DIR / dirname / "processed" / "features.parquet"
        df = pd.read_parquet(path)

        groups = None
        if cv_method == "logo_era":
            groups, _ = era_blocks(df["year"].to_numpy(), ERA_GAP_YEARS)

        runs = {
            name: run_one(df, name, cols, cv_method=cv_method, groups=groups, min_train_years=MIN_TRAIN_YEARS)
            for name, cols in RUNS.items()
        }

        if cv_method == "logo_era":
            baseline = baseline_timing_errors_block(df, groups)
        elif cv_method == "forward_chaining":
            baseline = baseline_timing_errors_forward(df, MIN_TRAIN_YEARS)
        else:
            baseline = baseline_timing_errors(df)

        all_results[site] = {"df": df, "runs": runs, "baseline": baseline, "cv_method": cv_method}

        print(f"{site} ({cv_method}): n_years={df['year'].nunique()}")
        for name in RUN_ORDER:
            r = runs[name]
            med = r["timing"]["error_days"].abs().median()
            print(f"  {name}: AP={r['average_precision']:.3f} AUC={r['roc_auc']:.3f} med|err|={med:.1f}")
        base_med = baseline["error_days"].abs().median()
        print(f"  baseline: med|err|={base_med:.1f}")
    return all_results


def write_metrics_csv(all_results: dict, out_path) -> None:
    rows = []
    for site, data in all_results.items():
        for name in RUN_ORDER:
            r = data["runs"][name]
            rows.append(
                {
                    "site": site,
                    "cv_method": data["cv_method"],
                    "run": name,
                    "average_precision": r["average_precision"],
                    "roc_auc": r["roc_auc"],
                    "median_abs_timing_error_days": r["timing"]["error_days"].abs().median(),
                }
            )
        rows.append(
            {
                "site": site,
                "cv_method": data["cv_method"],
                "run": "baseline",
                "average_precision": np.nan,
                "roc_auc": np.nan,
                "median_abs_timing_error_days": data["baseline"]["error_days"].abs().median(),
            }
        )
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"Wrote {out_path}")


def _grouped_bars(ax, sites, values_by_category, categories, colors, labels, ylabel, title):
    x = np.arange(len(sites))
    n = len(categories)
    width = 0.8 / n
    for k, cat in enumerate(categories):
        offset = (k - (n - 1) / 2) * width
        ax.bar(x + offset, values_by_category[cat], width, color=colors[k], label=labels[k])
    ax.set_xticks(x)
    ax.set_xticklabels(sites, rotation=15, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_title(title)


def plot_summary_bars(all_results: dict, out_path) -> None:
    sites = list(SITES.keys())

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    ap = {name: [all_results[s]["runs"][name]["average_precision"] for s in sites] for name in RUN_ORDER}
    auc = {name: [all_results[s]["runs"][name]["roc_auc"] for s in sites] for name in RUN_ORDER}
    _grouped_bars(
        axes[0], sites, ap, RUN_ORDER, [RUN_COLORS[n] for n in RUN_ORDER], RUN_ORDER,
        "average precision", "Average precision",
    )
    _grouped_bars(
        axes[1], sites, auc, RUN_ORDER, [RUN_COLORS[n] for n in RUN_ORDER], RUN_ORDER,
        "ROC AUC", "ROC AUC",
    )

    timing = {name: [all_results[s]["runs"][name]["timing"]["error_days"].abs().median() for s in sites] for name in RUN_ORDER}
    timing["baseline"] = [all_results[s]["baseline"]["error_days"].abs().median() for s in sites]
    _grouped_bars(
        axes[2], sites, timing, CATEGORIES, CATEGORY_COLORS, CATEGORY_LABELS,
        "median |predicted − actual| (days)", "Timing error",
    )

    handles, labels = axes[2].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.05))
    fig.suptitle(
        "Cross-validated comparison across four rivers\n"
        "(forward-chaining: Chemainus, Cowichan · leave-one-era-out: Nanaimo, Little Qualicum)",
        fontsize=13,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def plot_timing_boxplots(all_results: dict, out_path) -> None:
    sites = list(SITES.keys())

    all_errors = []
    for site in sites:
        for name in RUN_ORDER:
            all_errors.append(all_results[site]["runs"][name]["timing"]["error_days"].to_numpy())
        all_errors.append(all_results[site]["baseline"]["error_days"].to_numpy())
    ymin = min(a.min() for a in all_errors)
    ymax = max(a.max() for a in all_errors)
    pad = 0.05 * (ymax - ymin)

    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharey=True)

    for ax, site in zip(axes.flat, sites):
        data = [all_results[site]["runs"][name]["timing"]["error_days"].to_numpy() for name in RUN_ORDER]
        data.append(all_results[site]["baseline"]["error_days"].to_numpy())
        bp = ax.boxplot(data, tick_labels=CATEGORY_LABELS, showmeans=True, patch_artist=True)
        for patch, color in zip(bp["boxes"], CATEGORY_COLORS):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax.axhline(0, color="grey", linewidth=1, linestyle="--")
        ax.set_ylim(ymin - pad, ymax + pad)
        ax.set_title(f"{site} ({all_results[site]['cv_method']})")
        ax.tick_params(axis="x", labelrotation=15)

    for ax in axes[:, 0]:
        ax.set_ylabel("predicted − actual arrival (days)")

    fig.suptitle("Timing error by river and model (each river's own CV strategy)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


def main():
    all_results = compute_all()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    write_metrics_csv(all_results, OUT_DIR / "cross_site_metrics.csv")
    plot_summary_bars(all_results, FIGURES_DIR / "cross_site_summary.png")
    plot_timing_boxplots(all_results, FIGURES_DIR / "cross_site_timing_boxplots.png")


if __name__ == "__main__":
    main()
