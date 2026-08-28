"""Feature engineering on the full continuous daily record.

Computed BEFORE any seasonal subsetting -- subsetting first would blank the
first two weeks of every season, since the 7/14-day windows need lookback
into the prior season.

All windows are trailing and include the current day (pandas `rolling`
default). This is what prevents lookahead leakage: a feature on day t only
ever uses data from day t and earlier.
"""
from __future__ import annotations

import pandas as pd

from config import FEATURE_COLUMNS


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """df must have columns date, Q, T, P, sorted and complete-daily."""
    df = df.sort_values("date").reset_index(drop=True)
    assert df["date"].is_monotonic_increasing
    assert df["date"].diff().dropna().eq(pd.Timedelta("1D")).all(), (
        "daily record has a hole in the calendar -- reindex before calling add_features"
    )

    df["Q_7"] = df["Q"].rolling(7, min_periods=7).mean()
    df["Q_14"] = df["Q"].rolling(14, min_periods=14).mean()
    df["P_7"] = df["P"].rolling(7, min_periods=7).sum()
    df["T_7"] = df["T"].rolling(7, min_periods=7).mean()
    df["T_trend7"] = df["T"] - df["T"].shift(7)

    df["Q_pulse"] = df["Q"] - df["Q_7"]
    df["Q_rising"] = df["Q_7"] - df["Q_14"]

    df["doy"] = df["date"].dt.dayofyear

    return df


def feature_correlation_report(df: pd.DataFrame, out_path):
    """Correlation matrix of the final feature set, saved as a figure.
    Any |corr| > 0.9 is returned so the caller can flag it in the report.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    corr = df[FEATURE_COLUMNS].corr()

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(FEATURE_COLUMNS)))
    ax.set_xticklabels(FEATURE_COLUMNS, rotation=45, ha="right")
    ax.set_yticks(range(len(FEATURE_COLUMNS)))
    ax.set_yticklabels(FEATURE_COLUMNS)
    for i in range(len(FEATURE_COLUMNS)):
        for j in range(len(FEATURE_COLUMNS)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="Pearson r")
    ax.set_title("Feature correlation matrix")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    flagged = []
    n = len(FEATURE_COLUMNS)
    for i in range(n):
        for j in range(i + 1, n):
            r = corr.iloc[i, j]
            if abs(r) > 0.9:
                flagged.append((FEATURE_COLUMNS[i], FEATURE_COLUMNS[j], r))

    p_q_corr = df[["P_7", "Q_7"]].corr().iloc[0, 1]
    return corr, flagged, p_q_corr


if __name__ == "__main__":
    from config import FIGURES_DIR, INTERIM_DIR, SITE_SLUG

    env_df = pd.read_parquet(INTERIM_DIR / "daily_env.parquet")
    feat_df = add_features(env_df)
    feat_df.to_parquet(INTERIM_DIR / "daily_features.parquet", index=False)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    corr, flagged, p_q_corr = feature_correlation_report(feat_df, FIGURES_DIR / f"{SITE_SLUG}_feature_corr.png")
    print(corr.round(2))
    print(f"\nP_7 vs Q_7 correlation: {p_q_corr:.3f}")
    if flagged:
        print("\nFLAGGED pairs with |r| > 0.9 (not auto-dropped):")
        for a, b, r in flagged:
            print(f"  {a} vs {b}: r={r:.3f}")
    else:
        print("\nNo feature pair exceeds |r| > 0.9.")
