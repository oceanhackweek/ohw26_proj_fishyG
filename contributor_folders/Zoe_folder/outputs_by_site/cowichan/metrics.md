# Model comparison — leave-one-year-out CV

n_years = 17, n_rows = 648, n_positives = 17

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.076 | 0.720 | 7.0 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.150 | 0.917 | 1.0 |
| doy_only | doy | 0.127 | 0.836 | 2.0 |
| baseline (mean arrival doy) | -- | -- | -- | 4.0 |

**env_only vs baseline:** does NOT beat the mean-arrival-day baseline on median absolute timing error (7.0 vs 4.0 days).

**env_only (AP=0.076) vs doy_only (AP=0.127):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.

**Note:** unlike Chemainus and Nanaimo, `env_plus_doy` (AP=0.150, ROC AUC=0.917) clearly
beats `doy_only` (AP=0.127, ROC AUC=0.836) here -- the only one of the four sites where
adding weather to the calendar produces the best model overall, not just a marginal
timing improvement. Given the small sample (17 events) this could be a real Cowichan-
specific signal or could be a handful of years the environmental features happen to fit
well; see the guardrails below before treating it as established.

## Permutation importance caveat

Per-feature importance std (held-out folds) is 2-8x the mean for every feature (e.g.
Q_pulse: mean 0.100, std 0.241). Q_pulse and T_trend7 have the best signal-to-noise
ratio of any site run so far, but at 17 positive events this is still far short of a
result that would survive, e.g., dropping any single influential year and re-running.

## Guardrails

- **Sample size.** Only 17 positive events -- the smallest of the four sites run, and
  well below the ~15-year scale the plan already flagged as overfit-prone. Hyperparameters
  were fixed at the plan's specified values, not tuned against the LOYO score.
- **Extrapolation.** The fitted model cannot predict outside its training range
  (2002-2024 at this site, itself a narrow window); a year outside historical bounds
  gets clipped predictions.
- **Precipitation vs. flow.** `P_7` and `Q_7` correlate at r=0.60 (see `feature_corr.png`)
  -- the lowest of the four sites, consistent with Cowichan's flow gauge and precipitation
  grid cell being less co-located than at the other rivers.
- **Season window.** Aug 1-Dec 15 (same config constant as the other three site runs).
  Only 2025 was dropped, for lacking flow coverage past 2024-12-31 -- see
  `data_quality_report.md`.
- **Record length.** This site's salmon-count record only starts in 2002 (vs. decades
  earlier for the other three rivers), so this run answers "how well does the model do
  on a short, recent, single-decade-plus record" rather than testing across a longer
  climate range.