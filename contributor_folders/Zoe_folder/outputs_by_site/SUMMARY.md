# Cross-site comparison

Same pipeline (`src/load.py` -> `features.py` -> `target.py` -> `model.py`), same config
(SEED=42, Aug 1-Dec 15 season window, RF hyperparameters fixed per the plan), run once
per site. Each site's full output (data quality report, metrics, plots, pickled model)
is in its own subdirectory here.

| site | usable years / events | env_only AP | env_plus_doy AP | doy_only AP | env_only beats baseline? | best model overall |
|---|---|---|---|---|---|---|
| Chemainus | 44 | 0.034 | 0.043 | 0.054 | yes (9.0 vs 15.0 d) | doy_only (AP, AUC) |
| Nanaimo | 26 | 0.039 | 0.080 | 0.117 | no (7.5 vs 6.0 d) | doy_only (AP); env_plus_doy (timing) |
| Cowichan | 17 | 0.076 | **0.150** | 0.127 | no (7.0 vs 4.0 d) | **env_plus_doy** (only site where env clearly helps) |
| Little Qualicum | 27 | 0.049 | 0.060 | 0.081 | yes (7.0 vs 9.0 d) | doy_only (AP, AUC); worst timing of the four |

## What's consistent across sites

- **Day-of-year is doing most of the work everywhere.** In 3 of 4 sites, `doy_only`
  has the best average precision and ROC AUC of the three runs. Only Cowichan breaks
  that pattern, and Cowichan has the shortest, most recent record (17 events, all
  2002-2024) -- the weakest basis for trusting a difference in kind rather than a
  small-sample fluctuation.
- **No individual environmental feature's permutation importance is distinguishable
  from noise at any site.** Every site's importance std is several times its mean, and
  signs flip between sites (e.g. `T_trend7` is the top feature at Cowichan, near-zero
  at Chemainus, and negative at Little Qualicum). Don't read a "top feature" across
  sites from these plots.
- **Data completeness dominates data quantity.** Little Qualicum has more nominal
  years of salmon record (47) than Chemainus (46) but resolves to fewer usable years
  (27 vs 44) because of a single 25-year discharge gap. Sample size alone would not
  have predicted this -- it took actually running the gap-detection logic per site.

## Site-specific data issues found

- **Nanaimo**: as of this morning (2026-08-27) its flow file was a byte-identical
  mislabeled copy of Little Qualicum's gauge (station 08HB029). It has since been
  replaced with real data from station 08HB034, clean, no gaps. All Nanaimo numbers
  above use the corrected file.
- **Little Qualicum**: genuine ~25-year gap in discharge values (1987-01-01 to
  2012-07-25) at station 08HB029, confirmed against the raw CSV (rows exist for every
  date, `Value` field is blank). Not a Nanaimo-style mislabeling -- this is this
  gauge's own record. Splits the usable years into two disjoint eras (1967-1986,
  2013-2024) with no continuity between them.
- **Cowichan**: cleanest discharge record of the four (1.3% blank, no long gaps), but
  the salmon-count record itself only starts in 2002, so this is a short-record test
  by construction, not a data-quality problem.
- **Chemainus**: scattered short gaps in 1972-1974 (weeks, not years), mostly outside
  the Aug-Dec season window; longest, most complete usable record of the four.

## Recommendation

`src/config.py` is currently set back to **Chemainus** (the strongest single record:
most usable years, cleanest season-window coverage). The other three sites' full
outputs are preserved here for reference. None of the four sites currently justifies
promoting environmental features over a day-of-year baseline as the phase's headline
model -- that is the honest result of this phase, not a modeling shortfall to be tuned
away (per the plan's explicit instruction not to tune hyperparameters against the LOYO
score).
