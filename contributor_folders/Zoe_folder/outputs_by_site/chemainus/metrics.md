# Model comparison — leave-one-year-out CV

n_years = 44, n_rows = 1736, n_positives = 44

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.034 | 0.520 | 9.0 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.043 | 0.572 | 6.5 |
| doy_only | doy | 0.054 | 0.691 | 8.0 |
| baseline (mean arrival doy) | -- | -- | -- | 15.0 |

**env_only vs baseline:** beats the mean-arrival-day baseline on median absolute timing error (9.0 vs 15.0 days).

**env_only (AP=0.034) vs doy_only (AP=0.054):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.

## Permutation importance caveat

Per-feature importance std (held-out folds) is 4-6x the mean for every feature (e.g.
Q_rising: mean 0.050, std 0.207). No individual environmental feature's importance is
distinguishable from noise at this sample size -- do not read the ranking in
`permutation_importance.png` as "Q_rising matters, P doesn't." It mainly says the
env_only model's held-out AP is barely above chance to begin with, so permuting any
one feature rarely moves it by much either way.

## Guardrails

- **Sample size.** 44 positive events, 7 features. Hyperparameters were fixed at the
  plan's specified values and were *not* tuned against the LOYO score -- doing so would
  turn the validation set into a training set. If tuning is wanted later it needs
  nested CV.
- **Extrapolation.** The fitted model cannot predict outside its training range; a
  year warmer, drier, or wetter than 1962-2024 at this site will get predictions
  clipped to historical bounds.
- **Precipitation vs. flow.** `P_7` and `Q_7` correlate at r=0.73 (see
  `feature_corr.png`) -- not near-duplicates, but not independent either. The Chemainus
  precipitation grid cell and the flow gauge are not perfectly co-located, so some of
  the correlation is genuine watershed lag rather than redundancy.
- **Season window.** Widened from the plan's Sept 1 default to Aug 1 (see
  `data_quality_report.md`) because 15/46 years' arrivals fell in Jul-Aug and would
  otherwise have been dropped as "outside window" for no ecological reason -- these
  are still RUN_TYPE=FALL Chinook. This is a config constant (`src/config.py`) and can
  be changed.
- **Site.** Chosen over Little Qualicum, whose discharge gauge has a genuine ~25-year
  data gap (1987-2012, see `data_quality_report.md`) that cuts its usable record
  roughly in half; Chemainus has no comparable gap over the Aug-Dec season window. At
  the time of this run, Nanaimo's flow file was a mislabeled duplicate of Little
  Qualicum's and was excluded; it has since been corrected with real data and run
  separately -- see `../outputs_by_site/SUMMARY.md` for the full four-site comparison
  (Chemainus, Nanaimo, Cowichan, Little Qualicum).