# Model comparison

**CV strategy:** forward-chaining / expanding-window rolling-origin CV (train on every retained year strictly before the test year; the earliest 5 retained years are warm-up-only training data, never scored; first tested year is 2012) -- 12 tested year(s).

n_years = 17, n_rows = 648, n_positives = 17

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.075 | 0.635 | 5.0 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.140 | 0.882 | 2.0 |
| doy_only | doy | 0.151 | 0.878 | 1.5 |
| baseline (mean arrival doy) | -- | -- | -- | 3.0 |

**env_only vs baseline:** does NOT beat the mean-arrival-day baseline on median absolute timing error (5.0 vs 3.0 days).

**env_only (AP=0.075) vs doy_only (AP=0.151):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.