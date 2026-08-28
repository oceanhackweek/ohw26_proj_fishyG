# Cross-site comparison

Same pipeline (`src/load.py` -> `features.py` -> `target.py` -> `model.py`), same config
(SEED=42, Aug 1-Dec 15 season window, RF hyperparameters fixed per the plan), run once
per site. Each site's full output (data quality report, metrics, plots, pickled model)
is in its own subdirectory here.

**CV strategy differs by site** (set via `src/config.py`'s `CV_METHOD`, see that file's
comment for the full rationale): Chemainus and Cowichan have long enough, reasonably
continuous usable-year records for **forward-chaining** (expanding-window rolling-origin
CV -- train on every retained year strictly before the test year, first 5 retained years
are warm-up-only). Nanaimo and Little Qualicum each have a real multi-year hole splitting
their usable years into two disjoint eras, so they use **leave-one-era-out** block CV
instead (`model.era_blocks`, gap threshold 5 years) -- leave-one-YEAR-out would still let
the model train on other years from the *same* era as the held-out year, which understates
how well it generalizes across a genuine regime change. Because the CV strategy differs by
site, **AP/AUC/timing numbers are not directly comparable across the forward-chaining sites
and the leave-one-era-out sites** -- compare within a CV family, not across it.

| site | CV strategy | usable years / events | env_only AP | env_plus_doy AP | doy_only AP | env_only beats baseline? | best model overall |
|---|---|---|---|---|---|---|---|
| Chemainus | forward-chaining (39 tested yrs, from 1971) | 44 | 0.034 | 0.044 | 0.057 | yes (12.0 vs 14.0 d) | doy_only (AP, AUC) |
| Cowichan | forward-chaining (12 tested yrs, from 2012) | 17 | 0.075 | 0.140 | **0.151** | no (5.0 vs 3.0 d) | doy_only (AP); env_plus_doy (AUC, timing) |
| Nanaimo | leave-one-era-out (2 eras: 1984-1994, 2003-2024) | 26 | 0.047 | 0.072 | 0.075 | no (10.5 vs 7.0 d) | doy_only / env_plus_doy (close; both beat env_only) |
| Little Qualicum | leave-one-era-out (2 eras: 1967-1986, 2013-2024) | 27 | **0.062** | 0.062 | 0.043 | yes (5.0 vs 17.0 d) | **env_only / env_plus_doy** (only site where env clearly helps) |

## What's consistent across sites

- **Day-of-year is doing most of the work at three of four sites.** Chemainus, Cowichan,
  and Nanaimo all have `doy_only` at or near the best average precision of the three runs.
  **Little Qualicum breaks that pattern under leave-one-era-out** -- `env_only` and
  `env_plus_doy` both beat `doy_only` on AP and crush the baseline (5.0 vs 17.0 days),
  where under the old leave-one-year-out CV this site looked like the other three
  (`doy_only` won). That reversal is the headline result of switching to block CV: arrival
  timing apparently drifted enough between Little Qualicum's two eras (1967-1986 vs
  2013-2024) that a pure calendar-day baseline, fit on one era, transfers badly to the
  other -- while the environmental features (dominated by `T`, temperature) carry signal
  that *does* transfer. Nanaimo, the other leave-one-era-out site, does not show this;
  its two eras (1984-1994, 2003-2024) don't diverge from each other in the way Little
  Qualicum's do.
- **No individual environmental feature's permutation importance is distinguishable
  from noise at any site.** Every site's importance std is comparable to or larger than
  its mean, and signs flip between sites and between the two CV families (e.g. `T` is the
  top feature at Little Qualicum and Cowichan, but near-zero/negative at Chemainus).
  Don't read a "top feature" across sites from these plots.
- **Data completeness dominates data quantity.** Little Qualicum has more nominal
  years of salmon record (47) than Chemainus (46) but resolves to fewer usable years
  (27 vs 44) because of a single 25-year discharge gap -- the same gap that makes it a
  leave-one-era-out site rather than a forward-chaining one. Sample size alone would not
  have predicted this -- it took actually running the gap-detection logic per site.

## Site-specific data issues found

- **Nanaimo**: as of 2026-08-27 its flow file was a byte-identical mislabeled copy of
  Little Qualicum's gauge (station 08HB029). It has since been replaced with real data
  from station 08HB034, clean, no gaps. All Nanaimo numbers above use the corrected file.
  Its leave-one-era-out split (1984-1994 vs 2003-2024) comes from a ~9-year hole in the
  *spawning survey* record (1995-2002), not a flow gap -- the flow record itself has no
  long gaps.
- **Little Qualicum**: genuine ~25-year gap in discharge values (1987-01-01 to
  2012-07-25) at station 08HB029, confirmed against the raw CSV (rows exist for every
  date, `Value` field is blank). Not a Nanaimo-style mislabeling -- this is this
  gauge's own record. This is the gap `era_blocks` splits on (threshold: 5 years).
- **Cowichan**: cleanest discharge record of the four (1.3% blank, no long gaps), but
  the salmon-count record itself only starts in 2002, so forward-chaining only produces
  12 tested years (2012-2024) after the 5-year warm-up -- a short-record test by
  construction, not a data-quality problem.
- **Chemainus**: scattered short gaps in 1972-1974 (weeks, not years), mostly outside
  the Aug-Dec season window; longest, most complete usable record of the four, and the
  only site with enough history (39 tested years) for forward-chaining to be a
  reasonably stable estimate rather than a handful of folds.

## Recommendation

`src/config.py` is currently set back to **Chemainus** (the strongest single record:
most usable years, cleanest season-window coverage) with `CV_METHOD = "forward_chaining"`
as the "live" default. The other three sites' full outputs (each under its own CV
strategy) are preserved here for reference. Little Qualicum is the one site where
environmental features earned their keep once evaluated under the harder,
regime-change-aware leave-one-era-out split -- worth prioritizing if this phase moves
toward a single fielded model rather than four independent per-site baselines. None of
the other three sites currently justifies promoting environmental features over a
day-of-year baseline as the phase's headline model -- that is the honest result of this
phase, not a modeling shortfall to be tuned away (per the plan's explicit instruction not
to tune hyperparameters against the held-out CV score).
