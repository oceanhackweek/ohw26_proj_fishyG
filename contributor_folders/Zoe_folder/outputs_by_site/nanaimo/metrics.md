# Model comparison

**CV strategy:** leave-one-era-out block CV (retained years split wherever a gap > 5 years separates two consecutive retained years) -- 2 eras: era 0: 1984–1994; era 1: 2003–2024.

n_years = 26, n_rows = 887, n_positives = 26

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.047 | 0.631 | 10.5 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.072 | 0.730 | 4.0 |
| doy_only | doy | 0.075 | 0.724 | 9.0 |
| baseline (mean arrival doy) | -- | -- | -- | 7.0 |

**env_only vs baseline:** does NOT beat the mean-arrival-day baseline on median absolute timing error (10.5 vs 7.0 days).

**env_only (AP=0.047) vs doy_only (AP=0.075):** day-of-year alone is at least as informative as flow/precip/temperature -- the environmental features are not earning their keep for this site/record.