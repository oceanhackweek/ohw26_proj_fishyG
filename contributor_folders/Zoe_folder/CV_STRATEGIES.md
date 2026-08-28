# Cross-validation strategies in the salmon-spawning pipeline

Reference notes on how `src/model.py` validates the salmon-arrival model, written up
for further reading/research rather than as project documentation (see `README.md` and
`outputs_by_site/SUMMARY.md` for the project-facing version). Covers what each strategy
does, why it differs by site, and the row-level mechanics of how "grouping" actually
works in the code.

## Why not random k-fold

Each row in `data/processed/features.parquet` is one **day** within a spawning season
window (season start through the arrival date), not one row per year. Adjacent days
within the same season are near-identical -- same year's flow, same year's temperature
trend, arrival only a day or two away. Random k-fold would put some of a season's days
in the training set and others in the test set, so the model leaks information about
the very year it's being tested on. Every strategy below is **group-respecting**:
whatever the grouping rule is, all of a year's rows always land entirely in train or
entirely in test, never split.

## Three strategies, chosen per site

| Site | `CV_METHOD` | Why |
|---|---|---|
| Chemainus | `forward_chaining` | Long (44 usable years), reasonably continuous record |
| Cowichan | `forward_chaining` | Short (17 years) but continuous, no long gaps |
| Nanaimo | `logo_era` | Real ~9-year hole (1995-2002) in the survey record |
| Little Qualicum | `logo_era` | Real ~27-year hole (1987-2012) in the discharge record |

A fourth strategy, `loyo` (plain leave-one-year-out via `LeaveOneGroupOut` grouped on
calendar year), exists in the code and is what the project used before this change, but
no site currently uses it -- kept as the `groups=None` default in `loyo_predict()` since
`logo_era` reuses the same function with a coarser `groups` array.

Set via `src/config.py`'s `CV_METHOD` / `ERA_GAP_YEARS` / `MIN_TRAIN_YEARS`, swapped by
hand alongside the other per-site constants (see that file's comment block).

## Leave-one-era-out (Nanaimo, Little Qualicum)

### Step 1: find the eras

`model.era_blocks(years, min_gap_years)` takes the sorted list of a site's *retained*
years (already filtered by the data-quality/target-construction steps) and walks
consecutive pairs. Whenever the gap between two consecutive retained years exceeds
`ERA_GAP_YEARS` (currently 5), that's an era boundary. This is a **threshold on the gap
size**, not a fixed-width bin -- it does not chop the timeline into uniform 5-year
chunks, and it will produce however many eras the site's actual gaps warrant (here,
exactly two per site, because each has exactly one gap bigger than 5 years).

```python
def era_blocks(years, min_gap_years):
    uniq = sorted(set(int(y) for y in years))
    block_of_year = {uniq[0]: 0}
    current = 0
    for prev, y in zip(uniq[:-1], uniq[1:]):
        if y - prev > min_gap_years:
            current += 1
        block_of_year[y] = current
    ...
    block_ids = np.array([block_of_year[int(y)] for y in years])  # one id PER ROW
    return block_ids, ranges
```

**Little Qualicum** retained years (era boundary marked `|`):
```
1967 1968 1969 1971 1972 1973 1974 1975 1976 1977 1981 1982 1983 1984 1985 1986 | 2013 2014 2015 2016 2017 2019 2020 2021 2022 2023 2024
```
Largest gap *within* an era: 1977 -> 1981 (4 years, does not trigger a split, since the
rule is "greater than 5"). The split happens at 1986 -> 2013 (27 years) -- the same gap
flagged in the original data-quality report as a 25-year hole in the discharge record.
Result: **era 0 = 1967-1986 (16 years), era 1 = 2013-2024 (11 years)**.

**Nanaimo** retained years:
```
1984 1987 1988 1989 1990 1994 | 2003 2004 ... 2024
```
Largest within-era gap: 1990 -> 1994 (4 years, no split). Split at 1994 -> 2003 (9
years) -- a hole in the spawning *survey* record, not a flow gauge gap (Nanaimo's flow
record has no long gaps). Result: **era 0 = 1984-1994 (6 years), era 1 = 2003-2024 (20
years)**.

### Step 2: what "grouping" means at the row level

`era_blocks()` returns `block_ids`, one entry **per row** of the dataframe (not per
year) -- every row belonging to, say, 1970 and every row belonging to 1985 gets the same
label (`0`), because both years are in Little Qualicum's era 0. That array is handed
straight to scikit-learn:

```python
def loyo_predict(df, feature_cols, groups=None):
    ...
    if groups is None:
        groups = df["year"].to_numpy()          # plain LOYO: one group per year
    logo = LeaveOneGroupOut()
    for train_idx, test_idx in logo.split(X, y, groups):
        ...
```

`LeaveOneGroupOut` doesn't know anything about years or eras -- it just looks at how
many **distinct values** appear in whatever array it's given and produces one fold per
distinct value, holding that value's rows out as the test set each time. Feed it
`df["year"]` and you get one fold per year (plain LOYO, unused here). Feed it the era
`block_ids` array (only two distinct values, `0` and `1`) and you get exactly **two
folds**:

- Fold A: train on every row tagged `0` (era 0), test on every row tagged `1` (era 1).
- Fold B: train on every row tagged `1` (era 1), test on every row tagged `0` (era 0).

Every held-out year's prediction therefore comes from a model that never saw *any* year
from its own era -- not just not its own year, like plain LOYO would still allow. That's
the harder question this strategy is asking: does the model generalize across a real
regime change (instrument gap / survey gap), not just across individual seasons within
one continuous era.

Because there are only 2 folds (not one per year), this is a coarser test than
year-by-year CV -- 2 held-out prediction sets instead of up to 27 -- traded for asking a
harder, more honest question.

### Baseline

`baseline_timing_errors_block(df, groups)` mirrors the same restriction for the "predict
the mean arrival day-of-year" baseline: each year's predicted arrival is the mean
arrival doy across years in the **other** era only, never other years from its own
held-out era (which plain leave-one-out would allow, since it only excludes the row's
own single year).

## Forward-chaining / expanding-window rolling-origin CV (Chemainus, Cowichan)

No scikit-learn splitter is used here -- `model.forward_chaining_predict()` is a plain
loop over the sorted list of retained years:

```python
years = np.array(sorted(df["year"].unique()))
for i, test_year in enumerate(years):
    if i < min_train_years:
        continue                              # not enough history yet -- skip, never tested
    train_mask = year_arr < test_year         # every row from every year strictly before
    test_mask  = year_arr == test_year        # every row from that one year
    model = make_model()
    model.fit(X[train_mask], y[train_mask])
    ...
```

The "group" is still calendar year, but the training set is restricted to years that
came **chronologically before** the test year -- never years after. This is the causal
question plain LOYO does not ask: plain leave-one-year-out would happily let a model
trained partly on 1995-2010 predict 1985, which could never happen in real deployment
(you can't train on the future). Forward-chaining never does that.

The first `MIN_TRAIN_YEARS` (currently 5) retained years are used only as training data
and are never themselves tested -- there isn't enough prior history to fit a meaningful
model yet. Their rows stay `NaN` in the out-of-fold probability array and are excluded
from every metric (`average_precision_score`, `roc_auc_score`, `timing_errors`).

**Chemainus**: 44 retained years -> 5 warm-up years -> first tested year is **1971**,
last fold trains on everything through 2023 to test 2024 -> **39 tested years total**.
Each fold's training set grows: the 1971 fold trains on 6 years, the final fold trains
on 43.

**Cowichan**: 17 retained years -> 5 warm-up years -> first tested year is **2012** ->
**12 tested years total** (2012-2024).

### Baseline

`baseline_timing_errors_forward(df, min_train_years)` mirrors the same causality: each
test year's predicted arrival is the mean arrival doy across every retained year
**strictly before** it (an expanding mean) -- never the held-out year's own arrival, and
never a future year.

## Where this lives in code

- `src/model.py`: `era_blocks`, `loyo_predict`, `forward_chaining_predict`,
  `baseline_timing_errors` (plain LOYO), `baseline_timing_errors_block` (era),
  `baseline_timing_errors_forward` (forward-chaining), `run_one` (dispatches on
  `cv_method`), `main` (reads `config.CV_METHOD` and writes the strategy description
  into each site's `metrics.md`).
- `src/config.py`: `CV_METHOD`, `ERA_GAP_YEARS`, `MIN_TRAIN_YEARS`, plus the comment
  block explaining why each site uses which strategy.
- `src/plot_cross_site.py`: `SITES` dict maps each site to its `cv_method` so the
  cross-site comparison figures use the same per-site strategy as the individual runs.
- `outputs_by_site/<site>/metrics.md`: each site's actual fold count / era ranges /
  first-tested-year, generated fresh by `model.main()` each run.
