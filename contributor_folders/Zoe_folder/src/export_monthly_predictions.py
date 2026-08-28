"""Monthly actual-vs-predicted export for the Shiny dashboard.

One row per (site, run, year, month): whether the true arrival fell in that
month (and its date, if so), plus the model's mean predicted daily
probability for that month -- so the dashboard can plot "predicted risk"
against "actual return" on a shared month axis, per river and per feature
set.

Reuses plot_cross_site.compute_all(), which reuses model.py's LOYO CV code
directly -- no separate model-fitting logic, no re-derived numbers.

Run:
    cd contributor_folders/Zoe_folder
    python src/export_monthly_predictions.py
"""
from __future__ import annotations

import calendar

import pandas as pd

from plot_cross_site import OUT_DIR, RUN_ORDER, SITES, compute_all


def build_monthly_table(all_results: dict) -> pd.DataFrame:
    rows = []
    for site in SITES:
        df = all_results[site]["df"]
        for name in RUN_ORDER:
            oof_proba = all_results[site]["runs"][name]["oof_proba"]
            tmp = df[["year", "date", "started"]].copy()
            tmp["month"] = tmp["date"].dt.month
            tmp["proba"] = oof_proba

            for (year, month), grp in tmp.groupby(["year", "month"]):
                arrival = grp.loc[grp["started"] == 1, "date"]
                rows.append(
                    {
                        "site": site,
                        "run": name,
                        "year": int(year),
                        "month": int(month),
                        "month_name": calendar.month_abbr[int(month)],
                        "n_days": len(grp),
                        "actual_arrival_month": int(len(arrival) > 0),
                        "actual_arrival_date": arrival.iloc[0].date() if len(arrival) else None,
                        "mean_predicted_probability": grp["proba"].mean(),
                    }
                )
    return pd.DataFrame(rows).sort_values(["site", "run", "year", "month"]).reset_index(drop=True)


def main():
    all_results = compute_all()
    table = build_monthly_table(all_results)
    out_path = OUT_DIR / "monthly_predictions_dashboard.csv"
    table.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(table)} rows)")
    print(table.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
