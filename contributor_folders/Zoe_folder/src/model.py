"""Cross-validated evaluation, three comparison runs, and reporting.

Random k-fold is not used and must never be used here: adjacent days within
a season are near-identical rows, so a held-out day leaks through its
neighbours under random folds and reports a meaningless, inflated score.
Three group-respecting strategies are supported instead, selected per site
via `config.CV_METHOD` (the sites' usable-year records aren't uniform enough
for one strategy to fit all of them):

  "loyo"              -- leave-one-year-out (GroupKFold/LeaveOneGroupOut on
                         calendar year). The default: holds out one season at
                         a time, which is the question the model will
                         actually face at deployment for a site with a
                         reasonably continuous record.
  "logo_era"          -- leave-one-era-out block CV. Retained years are split
                         into blocks wherever a gap > `config.ERA_GAP_YEARS`
                         separates two consecutive retained years, then each
                         block is held out in turn. For sites whose usable
                         years fall into disjoint multi-year eras (a long
                         instrument gap, a multi-year survey gap), testing
                         leave-one-YEAR-out still lets the model train on
                         other years from the *same* era as the held-out
                         year -- leave-one-ERA-out is the harder, more
                         honest question of whether the model generalizes
                         across eras, not just within one.
  "forward_chaining"  -- expanding-window rolling-origin CV: train on every
                         retained year strictly before the test year, once at
                         least `config.MIN_TRAIN_YEARS` such years exist.
                         Suited to sites with a long, mostly continuous
                         record, where "could this have been predicted at
                         the time" is a meaningful question -- LOYO lets a
                         model trained partly on years *after* the test year
                         predict it, which forward-chaining never allows.
"""
from __future__ import annotations

import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut

from config import (
    CV_METHOD,
    ERA_GAP_YEARS,
    FEATURE_COLUMNS,
    MIN_TRAIN_YEARS,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    SEED,
)

RUNS = {
    "env_only": FEATURE_COLUMNS,
    "env_plus_doy": FEATURE_COLUMNS + ["doy"],
    "doy_only": ["doy"],
}


def make_model():
    return RandomForestClassifier(
        n_estimators=500,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight="balanced",
        random_state=SEED,
        n_jobs=-1,
    )


def era_blocks(years: np.ndarray, min_gap_years: int) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Split retained years into blocks wherever two consecutive *retained*
    years are more than `min_gap_years` apart. Returns (block id per input
    row, [(block_id, min_year, max_year), ...]) so callers can report which
    calendar years fall in which era instead of just an opaque integer.
    """
    uniq = sorted(set(int(y) for y in years))
    if len(uniq) < 2:
        raise ValueError("era_blocks needs at least 2 distinct years")

    block_of_year = {uniq[0]: 0}
    current = 0
    for prev, y in zip(uniq[:-1], uniq[1:]):
        if y - prev > min_gap_years:
            current += 1
        block_of_year[y] = current
    n_blocks = current + 1
    if n_blocks < 2:
        raise ValueError(
            f"era_blocks found only 1 block (no gap > {min_gap_years} years between "
            "consecutive retained years) -- logo_era needs at least 2 eras; lower "
            "ERA_GAP_YEARS or switch CV_METHOD"
        )

    ranges = [
        (b, min(y for y, bl in block_of_year.items() if bl == b), max(y for y, bl in block_of_year.items() if bl == b))
        for b in range(n_blocks)
    ]
    block_ids = np.array([block_of_year[int(y)] for y in years])
    return block_ids, ranges


def loyo_predict(df: pd.DataFrame, feature_cols: list[str], groups: np.ndarray | None = None):
    """Leave-one-group-out CV. `groups` defaults to calendar year (leave-
    one-year-out); pass a coarser grouping (e.g. era block id, for
    leave-one-era-out) to hold out that unit instead. Returns pooled
    out-of-fold probabilities (one per row, aligned to df's index), plus
    per-fold fitted models and held-out row indices for downstream
    timing/importance analysis.
    """
    X = df[feature_cols].to_numpy()
    y = df["started"].to_numpy()
    if groups is None:
        groups = df["year"].to_numpy()

    logo = LeaveOneGroupOut()
    oof_proba = np.full(len(df), np.nan)
    fold_models = []

    for train_idx, test_idx in logo.split(X, y, groups):
        model = make_model()
        model.fit(X[train_idx], y[train_idx])
        proba = model.predict_proba(X[test_idx])[:, 1]
        oof_proba[test_idx] = proba
        fold_models.append((groups[test_idx][0], test_idx, model))

    assert not np.isnan(oof_proba).any()
    return oof_proba, fold_models


def forward_chaining_predict(df: pd.DataFrame, feature_cols: list[str], min_train_years: int):
    """Expanding-window rolling-origin CV. Retained years are sorted; each
    year is tested against a model trained on every retained year strictly
    before it, once at least `min_train_years` such years exist. Years
    without enough prior history are never tested -- their rows stay NaN in
    oof_proba and they only ever appear as training data (never scored).
    """
    X = df[feature_cols].to_numpy()
    y = df["started"].to_numpy()
    year_arr = df["year"].to_numpy()
    years = np.array(sorted(df["year"].unique()))

    oof_proba = np.full(len(df), np.nan)
    fold_models = []

    for i, test_year in enumerate(years):
        if i < min_train_years:
            continue
        train_mask = year_arr < test_year
        test_mask = year_arr == test_year
        model = make_model()
        model.fit(X[train_mask], y[train_mask])
        proba = model.predict_proba(X[test_mask])[:, 1]
        oof_proba[test_mask] = proba
        fold_models.append((test_year, np.where(test_mask)[0], model))

    if not fold_models:
        raise ValueError(
            f"forward_chaining_predict produced zero test folds -- only {len(years)} "
            f"retained years but MIN_TRAIN_YEARS={min_train_years}"
        )
    return oof_proba, fold_models


def timing_errors(df: pd.DataFrame, oof_proba: np.ndarray) -> pd.DataFrame:
    """For each held-out year with an out-of-fold prediction, the highest-
    probability day vs the true arrival day, in signed days (predicted -
    actual). Years that were never tested (all-NaN -- forward-chaining
    warm-up years) are skipped rather than scored."""
    tmp = df.assign(_proba=oof_proba)
    rows = []
    for year, grp in tmp.groupby("year"):
        if grp["_proba"].isna().all():
            continue
        pred_row = grp.loc[grp["_proba"].idxmax()]
        true_row = grp.loc[grp["started"] == 1].iloc[0]
        err = (pred_row["date"] - true_row["date"]).days
        rows.append({"year": year, "pred_date": pred_row["date"], "true_date": true_row["date"], "error_days": err})
    return pd.DataFrame(rows)


def baseline_timing_errors(df: pd.DataFrame) -> pd.DataFrame:
    """LOYO baseline: predict each year's arrival as the mean arrival
    day-of-year across all OTHER retained years (leave-one-out mean -- no
    peeking at the held-out year's own arrival date)."""
    arrivals = df.loc[df["started"] == 1, ["year", "date", "doy"]].reset_index(drop=True)
    rows = []
    for _, row in arrivals.iterrows():
        others = arrivals[arrivals["year"] != row["year"]]
        mean_doy = others["doy"].mean()
        pred_date = pd.Timestamp(int(row["year"]), 1, 1) + pd.Timedelta(days=round(mean_doy) - 1)
        err = (pred_date - row["date"]).days
        rows.append({"year": row["year"], "pred_date": pred_date, "true_date": row["date"], "error_days": err})
    return pd.DataFrame(rows)


def baseline_timing_errors_block(df: pd.DataFrame, groups: np.ndarray) -> pd.DataFrame:
    """Leave-one-era-out baseline: predict each year's arrival as the mean
    arrival day-of-year across years in OTHER eras only -- never other years
    in its own held-out era, matching what loyo_predict(groups=...) allows
    the model to see."""
    arrivals = df.loc[df["started"] == 1, ["year", "date", "doy"]].reset_index(drop=True)
    year_to_group = dict(zip(df["year"].to_numpy(), groups))
    arrivals["group"] = arrivals["year"].map(year_to_group)
    rows = []
    for _, row in arrivals.iterrows():
        others = arrivals[arrivals["group"] != row["group"]]
        mean_doy = others["doy"].mean()
        pred_date = pd.Timestamp(int(row["year"]), 1, 1) + pd.Timedelta(days=round(mean_doy) - 1)
        err = (pred_date - row["date"]).days
        rows.append({"year": row["year"], "pred_date": pred_date, "true_date": row["date"], "error_days": err})
    return pd.DataFrame(rows)


def baseline_timing_errors_forward(df: pd.DataFrame, min_train_years: int) -> pd.DataFrame:
    """Forward-chaining baseline: predict each test year's arrival as the
    mean arrival day-of-year across every retained year strictly before it
    (an expanding causal mean) -- never the held-out year's own arrival, and
    never a future year, matching forward_chaining_predict's cutoff."""
    arrivals = df.loc[df["started"] == 1, ["year", "date", "doy"]].sort_values("year").reset_index(drop=True)
    rows = []
    for i, row in arrivals.iterrows():
        if i < min_train_years:
            continue
        prior = arrivals.iloc[:i]
        mean_doy = prior["doy"].mean()
        pred_date = pd.Timestamp(int(row["year"]), 1, 1) + pd.Timedelta(days=round(mean_doy) - 1)
        err = (pred_date - row["date"]).days
        rows.append({"year": row["year"], "pred_date": pred_date, "true_date": row["date"], "error_days": err})
    return pd.DataFrame(rows)


def held_out_permutation_importance(df: pd.DataFrame, feature_cols: list[str], fold_models):
    X = df[feature_cols].to_numpy()
    y = df["started"].to_numpy()
    per_fold = []
    for _, test_idx, model in fold_models:
        r = permutation_importance(
            model,
            X[test_idx],
            y[test_idx],
            scoring="average_precision",
            n_repeats=20,
            random_state=SEED,
        )
        per_fold.append(r.importances_mean)
    per_fold = np.array(per_fold)  # (n_folds, n_features)
    return pd.DataFrame(
        {
            "feature": feature_cols,
            "importance_mean": per_fold.mean(axis=0),
            "importance_std": per_fold.std(axis=0),
        }
    ).sort_values("importance_mean", ascending=False)


def run_one(
    df: pd.DataFrame,
    run_name: str,
    feature_cols: list[str],
    cv_method: str = "loyo",
    groups: np.ndarray | None = None,
    min_train_years: int | None = None,
):
    if cv_method == "loyo":
        oof_proba, fold_models = loyo_predict(df, feature_cols)
    elif cv_method == "logo_era":
        oof_proba, fold_models = loyo_predict(df, feature_cols, groups=groups)
    elif cv_method == "forward_chaining":
        oof_proba, fold_models = forward_chaining_predict(df, feature_cols, min_train_years)
    else:
        raise ValueError(f"Unknown cv_method: {cv_method!r}")

    y = df["started"].to_numpy()
    eval_mask = ~np.isnan(oof_proba)

    ap = average_precision_score(y[eval_mask], oof_proba[eval_mask])
    auc = roc_auc_score(y[eval_mask], oof_proba[eval_mask])
    timing = timing_errors(df, oof_proba)

    return {
        "run": run_name,
        "features": feature_cols,
        "average_precision": ap,
        "roc_auc": auc,
        "timing": timing,
        "fold_models": fold_models,
        "oof_proba": oof_proba,
    }


def plot_timing_errors(results: dict, baseline: pd.DataFrame, out_path, title: str):
    fig, ax = plt.subplots(figsize=(9, 5))
    data = []
    labels = []
    for name in ["env_only", "env_plus_doy", "doy_only"]:
        data.append(results[name]["timing"]["error_days"].to_numpy())
        labels.append(name)
    data.append(baseline["error_days"].to_numpy())
    labels.append("baseline\n(mean doy)")

    ax.boxplot(data, tick_labels=labels, showmeans=True)
    ax.axhline(0, color="grey", linewidth=1, linestyle="--")
    ax.set_ylabel("predicted − actual arrival (days)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_permutation_importance(imp_df: pd.DataFrame, out_path):
    fig, ax = plt.subplots(figsize=(7, 4))
    imp_df = imp_df.sort_values("importance_mean")
    ax.barh(imp_df["feature"], imp_df["importance_mean"], xerr=imp_df["importance_std"])
    ax.set_xlabel("permutation importance (mean drop in held-out average precision)")
    ax.set_title("Permutation importance -- env_only model, held-out folds")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    df = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    cv_method = CV_METHOD
    groups = None
    era_ranges = None
    if cv_method == "logo_era":
        groups, era_ranges = era_blocks(df["year"].to_numpy(), ERA_GAP_YEARS)

    results = {}
    for name, cols in RUNS.items():
        print(f"Running {name} ({cols}) via {cv_method} ...")
        results[name] = run_one(
            df, name, cols, cv_method=cv_method, groups=groups, min_train_years=MIN_TRAIN_YEARS
        )

    if cv_method == "logo_era":
        baseline = baseline_timing_errors_block(df, groups)
    elif cv_method == "forward_chaining":
        baseline = baseline_timing_errors_forward(df, MIN_TRAIN_YEARS)
    else:
        baseline = baseline_timing_errors(df)

    lines = ["# Model comparison\n"]
    if cv_method == "loyo":
        lines.append("**CV strategy:** leave-one-year-out (GroupKFold/LeaveOneGroupOut on calendar year).\n")
    elif cv_method == "logo_era":
        era_desc = "; ".join(f"era {b}: {lo}–{hi}" for b, lo, hi in era_ranges)
        lines.append(
            f"**CV strategy:** leave-one-era-out block CV (retained years split wherever a "
            f"gap > {ERA_GAP_YEARS} years separates two consecutive retained years) -- "
            f"{len(era_ranges)} eras: {era_desc}.\n"
        )
    elif cv_method == "forward_chaining":
        sorted_years = sorted(df["year"].unique())
        n_folds = len(results["env_only"]["fold_models"])
        first_tested_year = int(sorted_years[MIN_TRAIN_YEARS])
        lines.append(
            f"**CV strategy:** forward-chaining / expanding-window rolling-origin CV "
            f"(train on every retained year strictly before the test year; the earliest "
            f"{MIN_TRAIN_YEARS} retained years are warm-up-only training data, never scored; "
            f"first tested year is {first_tested_year}) -- {n_folds} tested year(s).\n"
        )
    lines.append(f"n_years = {df['year'].nunique()}, n_rows = {len(df)}, n_positives = {int(df['started'].sum())}\n")
    lines.append("| run | features | average precision | ROC AUC | median \\|timing error\\| (days) |")
    lines.append("|---|---|---|---|---|")
    for name in RUNS:
        r = results[name]
        med_abs = r["timing"]["error_days"].abs().median()
        lines.append(
            f"| {name} | {', '.join(r['features'])} | {r['average_precision']:.3f} | "
            f"{r['roc_auc']:.3f} | {med_abs:.1f} |"
        )
    base_med_abs = baseline["error_days"].abs().median()
    lines.append(f"| baseline (mean arrival doy) | -- | -- | -- | {base_med_abs:.1f} |")
    lines.append("")

    env_med = results["env_only"]["timing"]["error_days"].abs().median()
    lines.append(
        f"**env_only vs baseline:** {'beats' if env_med < base_med_abs else 'does NOT beat'} "
        f"the mean-arrival-day baseline on median absolute timing error "
        f"({env_med:.1f} vs {base_med_abs:.1f} days)."
    )
    lines.append("")
    lines.append(
        f"**env_only (AP={results['env_only']['average_precision']:.3f}) vs doy_only "
        f"(AP={results['doy_only']['average_precision']:.3f}):** "
        + (
            "environment adds signal beyond the calendar."
            if results["env_only"]["average_precision"] > results["doy_only"]["average_precision"]
            else "day-of-year alone is at least as informative as flow/precip/temperature -- "
            "the environmental features are not earning their keep for this site/record."
        )
    )

    (OUTPUTS_DIR / "metrics.md").write_text("\n".join(lines))
    print("\n".join(lines))

    title = {
        "loyo": "Leave-one-year-out timing error by model",
        "logo_era": "Leave-one-era-out timing error by model",
        "forward_chaining": "Forward-chaining (expanding-window) timing error by model",
    }[cv_method]
    plot_timing_errors(results, baseline, OUTPUTS_DIR / "timing_errors.png", title)

    imp_df = held_out_permutation_importance(df, FEATURE_COLUMNS, results["env_only"]["fold_models"])
    imp_df.to_csv(OUTPUTS_DIR / "permutation_importance.csv", index=False)
    plot_permutation_importance(imp_df, OUTPUTS_DIR / "permutation_importance.png")
    print("\nPermutation importance (env_only, held-out folds):")
    print(imp_df.to_string(index=False))

    final_model = make_model()
    final_model.fit(df[FEATURE_COLUMNS].to_numpy(), df["started"].to_numpy())
    with open(OUTPUTS_DIR / "model_env_only.pkl", "wb") as f:
        pickle.dump({"model": final_model, "feature_columns": FEATURE_COLUMNS, "seed": SEED}, f)

    return results, baseline, imp_df


if __name__ == "__main__":
    main()
