# Model comparison

**CV strategy:** leave-one-era-out block CV (retained years split wherever a gap > 5 years separates two consecutive retained years) -- 2 eras: era 0: 1967–1986; era 1: 2013–2024.

n_years = 27, n_rows = 1089, n_positives = 27

| run | features | average precision | ROC AUC | median \|timing error\| (days) |
|---|---|---|---|---|
| env_only | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7 | 0.062 | 0.670 | 5.0 |
| env_plus_doy | Q_7, Q_pulse, Q_rising, P, P_7, T, T_trend7, doy | 0.062 | 0.672 | 3.0 |
| doy_only | doy | 0.043 | 0.658 | 6.0 |
| baseline (mean arrival doy) | -- | -- | -- | 17.0 |

**env_only vs baseline:** beats the mean-arrival-day baseline on median absolute timing error (5.0 vs 17.0 days).

**env_only (AP=0.062) vs doy_only (AP=0.043):** environment adds signal beyond the calendar.