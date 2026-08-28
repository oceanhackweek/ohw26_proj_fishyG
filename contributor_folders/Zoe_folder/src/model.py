"""Leave-one-year-out CV, three comparison runs, and reporting.

Random k-fold is not used and must never be used here: adjacent days within
a season are near-identical rows, so a held-out day leaks through its
neighbours under random folds and reports a meaningless, inflated score.
GroupKFold / LeaveOneGroupOut with `year` as the group holds out an entire
season at a time, which is the only split that asks a question the model
will actually face at deployment: predict a year it has never seen.
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

from config import FEATURE_COLUMNS, OUTPUTS_DIR, PROCESSED_DIR, SEED

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


def loyo_predict(df: pd.DataFrame, feature_cols: list[str]):
    """Leave-one-year-out CV. Returns pooled out-of-fold probabilities
    (one per row, aligned to df's index), plus per-fold fitted models and
    held-out row indices for downstream timing/importance analysis.
    """
    X = df[feature_cols].to_numpy()
    y = df["started"].to_numpy()
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


def timing_errors(df: pd.DataFrame, oof_proba: np.ndarray) -> pd.DataFrame:
    """For each held-out year, the highest-probability day vs the true
    arrival day, in signed days (predicted - actual)."""
    tmp = df.assign(_proba=oof_proba)
    rows = []
    for year, grp in tmp.groupby("year"):
        pred_row = grp.loc[grp["_proba"].idxmax()]
        true_row = grp.loc[grp["started"] == 1].iloc[0]
        err = (pred_row["date"] - true_row["date"]).days
        rows.append({"year": year, "pred_date": pred_row["date"], "true_date": true_row["date"], "error_days": err})
    return pd.DataFrame(rows)


def baseline_timing_errors(df: pd.DataFrame) -> pd.DataFrame:
    """Predict each year's arrival as the mean arrival day-of-year across
    all OTHER retained years (leave-one-out mean -- no peeking at the held
    out year's own arrival date)."""
    arrivals = df.loc[df["started"] == 1, ["year", "date", "doy"]].reset_index(drop=True)
    rows = []
    for _, row in arrivals.iterrows():
        others = arrivals[arrivals["year"] != row["year"]]
        mean_doy = others["doy"].mean()
        pred_date = pd.Timestamp(int(row["year"]), 1, 1) + pd.Timedelta(days=round(mean_doy) - 1)
        err = (pred_date - row["date"]).days
        rows.append({"year": row["year"], "pred_date": pred_date, "true_date": row["date"], "error_days": err})
    return pd.DataFrame(rows)


def held_out_permutation_importance(df: pd.DataFrame, feature_cols: list[str], fold_models):
    X = df[feature_cols].to_numpy()
    y = df["started"].to_numpy()
    per_fold = []
    for year, test_idx, model in fold_models:
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


def run_one(df: pd.DataFrame, run_name: str, feature_cols: list[str]):
    oof_proba, fold_models = loyo_predict(df, feature_cols)
    y = df["started"].to_numpy()

    ap = average_precision_score(y, oof_proba)
    auc = roc_auc_score(y, oof_proba)
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


def plot_timing_errors(results: dict, baseline: pd.DataFrame, out_path):
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
    ax.set_title("Leave-one-year-out timing error by model")
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

    results = {}
    for name, cols in RUNS.items():
        print(f"Running {name} ({cols}) ...")
        results[name] = run_one(df, name, cols)

    baseline = baseline_timing_errors(df)

    lines = ["# Model comparison — leave-one-year-out CV\n"]
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

    plot_timing_errors(results, baseline, OUTPUTS_DIR / "timing_errors.png")

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
