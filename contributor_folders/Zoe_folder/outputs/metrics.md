# Model comparison

**CV strategy:** forward-chaining / expanding-window rolling-origin CV (train on every retained year strictly before the test year; the earliest 5 retained years are warm-up-only training data, never scored; first tested year is 1971) -- 39 tested year(s).

n_years = 44, n_rows = 1736, n_positives = 44

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.034 | 0.543 | 12.0 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.044 | 0.589 | 7.0 |
| doy_only | doy | 0.057 | 0.686 | 8.0 |
| baseline (mean arrival doy) | -- | -- | -- | 14.0 |

**env_only vs baseline:** beats the mean-arrival-day baseline on median absolute timing error (12.0 vs 14.0 days).

**env_only (AP=0.034) vs doy_only (AP=0.057):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.