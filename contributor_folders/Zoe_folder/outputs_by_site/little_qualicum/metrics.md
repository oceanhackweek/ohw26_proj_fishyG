# Model comparison — leave-one-year-out CV

n_years = 27, n_rows = 1089, n_positives = 27

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.049 | 0.608 | 7.0 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.060 | 0.760 | 5.0 |
| doy_only | doy | 0.081 | 0.805 | 10.0 |
| baseline (mean arrival doy) | -- | -- | -- | 9.0 |

**env_only vs baseline:** beats the mean-arrival-day baseline on median absolute timing error (7.0 vs 9.0 days).

**env_only (AP=0.049) vs doy_only (AP=0.081):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.

**Note:** `doy_only` has the best AP/AUC here but the *worst* median timing error (10.0
days, worse than the baseline's 9.0) -- AP/AUC and timing error are answering different
questions (ranking days by risk vs. picking a single peak day) and can disagree,
especially with a discontinuous 25-year gap splitting the retained years into two
disjoint eras (1967-1986 and 2013-2024, see below) with no continuity between them.

## Permutation importance caveat

Per-feature importance std (held-out folds) is 3-30x the mean for every feature (e.g.
T: mean 0.079, std 0.230; T_trend7 has a *negative* mean). At 27 events, none of this
is distinguishable from noise.

## Guardrails

- **Sample size.** 27 positive events.
- **Extrapolation.** Cannot predict outside the training range; note this record is
  especially discontinuous (see below), so "training range" is really two separate
  eras, not one smooth 1967-2024 span.
- **Precipitation vs. flow.** `P_7` and `Q_7` correlate at r=0.63 (see `feature_corr.png`).
- **Season window.** Aug 1-Dec 15 (same config constant as the other three site runs).
- **This site has a genuine ~25-year gap in discharge data (1987-01-01 to 2012-07-25,
  station 08HB029) -- not a code artifact.** See `data_quality_report.md`. It splits the
  27 retained years into two disjoint clusters (1967-1986, 16 years; 2013-2024, 11 years)
  with a 26-year hole between them and 20 of 47 spawning-record years dropped entirely,
  12 of those specifically because the gap blanks their season window. This is the
  weakest of the four site records for this reason, run for completeness after the
  Nanaimo flow-file correction prompted re-checking all four rivers. Chemainus (44
  events) and Nanaimo (26 events, now-corrected gauge) remain the better records for
  this phase; see `outputs_by_site/`.