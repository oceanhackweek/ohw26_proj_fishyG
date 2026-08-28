# Handoff — cross-site model comparison, Shiny dashboard export, regional trend context

**Session:** Friday 2026-08-28, afternoon/evening
**Author:** zoe + Claude
**Project:** `ohw26_proj_fishyG` — salmon (NuSEDS escapement), four rivers: Chemainus,
Nanaimo, Cowichan, Little Qualicum
**Scope:** this covers the cross-validated CV pipeline in `contributor_folders/Zoe_folder/src/`
(load → features → target → model), the four-river comparison built on top of it, a
Shiny-dashboard CSV export, and a new regional-trend reference dataset. It does **not**
cover the weather-data splice pipeline (PNWNAmet/Daymet/NARR) — see `HANDOFF.md` for that.

---

## 1. What was done

1. **Read through `src/` and explained the (then leave-one-year-out) CV model.**
   Confirmed a real day-of-year bias: `doy_only` beat `env_only` on average precision
   and ROC AUC at 3 of 4 rivers (only Cowichan, the shortest record, went the other
   way), both structurally (the label's positive row is always the last row of each
   year's group; `T`/`T_7`/`T_trend7` ride the seasonal cooling trend even without
   touching `doy` directly) and empirically (see `outputs_by_site/SUMMARY.md`, already
   the project's own documented finding — not something newly discovered this session).

2. **Built `src/plot_cross_site.py`** — pulls all four rivers' already-fitted CV results
   together (reusing `model.py`'s CV code directly, not a reimplementation) into:
   - `outputs_by_site/cross_site_summary.png` — grouped bars: average precision, ROC
     AUC, median timing error, per river per feature set (`env_only` / `env_plus_doy` /
     `doy_only` / baseline).
   - `outputs_by_site/cross_site_timing_boxplots.png` — 2×2 grid, full timing-error
     distribution per river.
   - `outputs_by_site/cross_site_metrics.csv` — the same numbers, machine-readable.

3. **Built `src/export_monthly_predictions.py`** for the Shiny dashboard — one row per
   (site, run, year, month): whether the true arrival fell in that month
   (`actual_arrival_month`, `actual_arrival_date`) and the model's mean predicted daily
   probability for that month (`mean_predicted_probability`), so predicted-vs-actual can
   be plotted on one time axis. Output: `monthly_predictions_dashboard.csv`.

4. **Investigated `data/Trend_resources/`** (Pacific Salmon Foundation State of Salmon
   Report data: `dataset551_sps-data.csv`, `dataset552_sps-metrics.csv`, two metadata
   PDFs) to see where our four rivers fit in the published regional trend. Found:
   - All four rivers fall in PSF's **"East Vancouver Island & Mainland Inlets" (EVIMI)**
     region (confirmed via `data/river_coordinates.csv` — all four sit at 48.7–49.4°N on
     the Strait of Georgia side of Vancouver Island). Species match: `Chinook`.
   - **Our own raw per-river data is confirmed 100% `RUN_TYPE == FALL`** (checked
     directly in `data/Salmon Data/*.csv`).
   - **The PSF regional series is *not* confirmed run-timing-specific** — its schema has
     no spring/summer/fall field at all, so "EVIMI Chinook" should be read as a
     same-species regional backdrop, not a verified fall-run-matched benchmark. (Its one
     source, `CTC_20250714`, likely draws mostly on fall-run Georgia Strait indicator
     stocks in practice, but that's not stated in the PSF metadata itself.)
   - Headline: regional Chinook spawners are **+236% above the long-term average as of
     2024** (short-term trend +13.4%/yr, "increasing"; long-term 46-yr trend only
     +1.1%/yr, "stable" — not statistically significant). Run size is similar (+215%
     current, +12.9%/yr short-term, +1.5%/yr long-term, this one *is* significant).

5. **Built `src/build_regional_trends.py`** — joins the two PSF tables, filtered to
   EVIMI/Chinook, into one tidy per-year CSV: `outputs/regional_trends_evi_chinook.csv`
   (100 rows = 2 metrics × 50 years, 1975–2024; raw/smoothed/anomaly values, both
   fitted trend lines with 95% intervals, region-level summary stats repeated per row;
   PSF's `-989898` null sentinel converted to `NaN`).

6. **Built `src/plot_regional_trends.py`** — two figures from that CSV:
   `outputs/regional_trends_timeseries.png` (raw + smoothed abundance with both fitted
   trend lines) and `outputs/regional_trends_anomaly.png` (per cent anomaly by year,
   diverging color by sign). Both cover spawners and run size, one panel each.

---

## 2. Important — CV methodology changed mid-session, not by me

Partway through, `config.py`, `model.py`, `plot_cross_site.py`, and `features.py` were
substantially revised (by zoe, working in parallel — see the repo's own commit history,
e.g. `0b5e22b`, `16dd08d`, `b438945`, `c33e45e`, `a51658f`) to replace pure
leave-one-year-out CV with a **per-site strategy**, set by `config.CV_METHOD`:

- **`forward_chaining`** (expanding-window rolling-origin CV) for **Chemainus,
  Cowichan** — long enough, reasonably continuous records for a causal "could this have
  been predicted at the time" evaluation.
- **`logo_era`** (leave-one-era-out block CV, `model.era_blocks`) for **Nanaimo, Little
  Qualicum** — both have a real multi-year gap splitting usable years into two disjoint
  eras (Little Qualicum's 1987–2012 discharge gap; Nanaimo's ~1995–2002 survey gap), so
  plain leave-one-year-out would still let the model train on other years from the
  *same* era as the held-out year.

Figures also moved: `model.py` and `features.py` now write per-site diagnostic plots
(`feature_corr.png`, `timing_errors.png`, `permutation_importance.png`) into a shared
`FIGURES_DIR` (`contributor_folders/Zoe_folder/figures/`), prefixed by `SITE_SLUG`,
instead of duplicating them under each site's own `outputs_by_site/<site>/`.

**Consequence for the outputs above:**
- `cross_site_metrics.csv` / `cross_site_summary.png` / `cross_site_timing_boxplots.png`
  — **already refreshed** under the new per-site CV (`cross_site_metrics.csv` has a
  `cv_method` column showing `forward_chaining` for Chemainus, confirmed by direct
  inspection). Current.
- **`monthly_predictions_dashboard.csv` is stale.** It was generated once, before this
  refactor, under the old pure-LOYO `compute_all()`, and has not been regenerated since.
  It now also lives at a new top-level path — `model_output/monthly_predictions_dashboard.csv`
  (moved out of `outputs_by_site/` in commit `b438945`, "Create model outputs folder",
  presumably so the Shiny app has one stable path to read from regardless of contributor
  folder structure) — but its *contents* still reflect the old methodology.

---

## 3. Where things live now

| What | Path |
|---|---|
| Cross-site comparison (current) | `contributor_folders/Zoe_folder/outputs_by_site/cross_site_{summary.png,timing_boxplots.png,metrics.csv}` |
| Monthly predictions for Shiny (**stale — see §2**) | `model_output/monthly_predictions_dashboard.csv` |
| Regional trend CSV (EVIMI/Chinook) | `contributor_folders/Zoe_folder/outputs/regional_trends_evi_chinook.csv` |
| Regional trend figures | `contributor_folders/Zoe_folder/outputs/regional_trends_{timeseries,anomaly}.png` |
| Cross-site / dashboard / regional-trend scripts | `contributor_folders/Zoe_folder/src/{plot_cross_site,export_monthly_predictions,build_regional_trends,plot_regional_trends}.py` |
| Per-site diagnostic figures (new home) | `contributor_folders/Zoe_folder/figures/<site>_{feature_corr,timing_errors,permutation_importance}.png` |
| Zoe's own earlier figures (untouched this session) | `contributor_folders/Zoe_folder/figures/{jul_aug_temp_precip_maps,weather_20250701_20250801_20250901}.png` |
| PSF trend source data + metadata | `data/Trend_resources/` |

---

## 4. Remaining tasks

1. ~~Regenerate `monthly_predictions_dashboard.csv` under the new per-site CV.~~
   **Deliberately left as-is (zoe, 2026-08-28):** the per-site CV modes
   (`forward_chaining` / `logo_era`) aren't finished/settled yet, so the dashboard CSV
   staying on plain LOYO for now is fine. Re-run `src/export_monthly_predictions.py`
   (it already imports `compute_all()` from `plot_cross_site.py`, so no code change is
   needed) once the other CV modes are finalized — and at that point also point its
   output at `model_output/` to match where the file now actually lives.
2. **Untracked files not yet committed:**
   `outputs_by_site/{little_qualicum,nanaimo}/regional_trends_{anomaly.png,evi_chinook.csv,timeseries.png}`
   (6 files) and `figures/chemainus_feature_corr.png`. Worth confirming intentional
   (regional trends are region-level, identical across all four sites — duplicating them
   per-site subfolder is presumably deliberate for the dashboard's convenience, but
   confirm before committing) and committing or removing as appropriate.
3. **Fall-run specificity of the PSF regional benchmark is unresolved** (§1.4 above) —
   if a fall-run-matched regional comparison matters later, pull the underlying
   `CTC_20250714` source (*Annual Report of Catch and Escapement for 2024*, PSC report
   TCCHINOOK 25-02) and check which indicator stocks/run-timings feed the Georgia Strait
   number PSF aggregates.
4. **`outputs_by_site/SUMMARY.md`** (the four-site headline comparison doc) predates the
   CV-methodology refactor and was written describing pure LOYO results — it should be
   revisited to confirm its numbers/conclusions still hold under `forward_chaining` /
   `logo_era`, or updated if they've shifted.
5. Nothing above has been pushed — everything is local/uncommitted or committed locally
   only (see `git log`/`git status` for current state at hand-off time).
