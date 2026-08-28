# Model comparison — leave-one-year-out CV

n_years = 26, n_rows = 887, n_positives = 26

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.039 | 0.636 | 7.5 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.080 | 0.814 | 4.0 |
| doy_only | doy | 0.117 | 0.749 | 1.0 |
| baseline (mean arrival doy) | -- | -- | -- | 6.0 |

**env_only vs baseline:** does NOT beat the mean-arrival-day baseline on median absolute timing error (7.5 vs 6.0 days).

**env_only (AP=0.039) vs doy_only (AP=0.117):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.

## Permutation importance caveat

Per-feature importance std (held-out folds) is 3-15x the mean for every feature (e.g.
T: mean 0.024, std 0.246; several features have a *negative* mean importance, meaning
permuting them randomly improved held-out AP about as often as it hurt it). At 26
positive events no individual environmental feature's importance is distinguishable
from noise -- treat `permutation_importance.png` as evidence the env_only model has
little to work with, not as a ranking of which weather variable matters most.

## Guardrails

- **Sample size.** 26 positive events, 7 features -- smaller than Chemainus's 44 and
  below the ~15-year scale the plan anticipated as already overfit-prone. Hyperparameters
  were fixed at the plan's specified values, not tuned against the LOYO score.
- **Extrapolation.** The fitted model cannot predict outside its training range (1979-2024
  at this site); a year outside historical bounds gets clipped predictions.
- **Precipitation vs. flow.** `P_7` and `Q_7` correlate at r=0.70 (see `feature_corr.png`)
  -- moderate, not near-duplicate.
- **Season window.** Aug 1-Dec 15 (same config constant as the Chemainus run). Four years
  were dropped for having an arrival date far outside any plausible fall-run window
  (1979-03-01, 1986-07-25, 1993-01-04, and a 2017-record arrival dated 2018-02-21) -- see
  `data_quality_report.md`. These read as likely data-entry artifacts (a "survey start"
  date substituting for "arrival date") rather than real early/late runs, but were
  excluded rather than silently reinterpreted.
- **doy_only's AP=0.117 with median timing error of 1.0 day** is the standout number in
  this table. With only 26 events, a handful of years whose "highest-probability day"
  happens to land exactly on the true arrival can swing the median sharply -- this is
  encouraging but should not be over-read as a robust result without more data or a
  sensitivity check (e.g. dropping single influential years and re-running).
- **Site history.** This file (`Nanaimo_Riv_Flow.csv`) was a mislabeled duplicate of
  Little Qualicum's gauge data as of 2026-08-27 morning; it was corrected later that day
  (now station 08HB034, clean record, no long gaps). The Chemainus run (this phase's
  original site pick, made before the correction) is preserved in
  `outputs_by_site/chemainus/`.