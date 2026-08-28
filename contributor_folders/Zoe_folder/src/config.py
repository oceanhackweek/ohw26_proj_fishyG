"""Shared constants for the salmon spawning pipeline.

Scope: one site at a time -- swap the per-site constants below (FLOW_CSV,
SALMON_CSV, SITE_NAME, SITE_LAT/LON, FLOW_STATION_ID, SITE_SLUG, CV_METHOD)
and re-run load.py -> features.py -> target.py -> model.py to switch sites.
"""
from pathlib import Path

SEED = 42

# contributor_folders/Zoe_folder/src/config.py -> repo root is 3 parents up
REPO_ROOT = Path(__file__).resolve().parents[3]
ZOE_ROOT = Path(__file__).resolve().parents[1]

# Raw source files live in the repo-wide shared `data/` directory, not copied
# into this project's data/raw — they are large (the weather netCDF is 70 MB)
# and are shared across contributors' folders. `data/interim` and
# `data/processed` below are local to this pipeline.
RAW_DATA_DIR = REPO_ROOT / "data"
INTERIM_DIR = ZOE_ROOT / "data" / "interim"
PROCESSED_DIR = ZOE_ROOT / "data" / "processed"
OUTPUTS_DIR = ZOE_ROOT / "outputs"

# All plots (feature correlation, timing errors, permutation importance) go
# here rather than into OUTPUTS_DIR / outputs_by_site, so every site's
# figures live in one place instead of being scattered across four
# subdirectories. Filenames are prefixed with SITE_SLUG (below) so they don't
# collide between sites.
FIGURES_DIR = ZOE_ROOT / "figures"

# Four sites were run this phase; each site's full output is preserved under
# ../outputs_by_site/<site>/ (see ../outputs_by_site/SUMMARY.md for the
# cross-site comparison). This config is set to Chemainus -- the strongest
# single record (44 usable years, cleanest season-window coverage) -- as the
# "live" default. Swap the four lines below to switch sites and re-run
# load.py -> features.py -> target.py -> model.py.
FLOW_CSV = RAW_DATA_DIR / "Chemanius_Riv_Flow.csv"
SALMON_CSV = RAW_DATA_DIR / "Salmon Data" / "CHEMAINUS RIVER_salmon_data.csv"
WEATHER_NC = RAW_DATA_DIR / "Global_weather" / "merged_tavg_prcp_1960_2025.nc"

SITE_NAME = "Chemainus River"
SITE_SLUG = "chemainus"  # used as a filename prefix under FIGURES_DIR
# From data/river_coordinates.csv
SITE_LAT = 48.8972
SITE_LON = -123.6797

# Flow gauge station 08HA001 (WSC).
FLOW_STATION_ID = "08HA001"

# Physical plausibility bounds (see plan section 1.4)
Q_MIN = 0.0
P_MIN = 0.0
T_MIN, T_MAX = -20.0, 40.0
Q_OUTLIER_MULTIPLE = 50  # flag discharge > 50x site median

MAX_INTERP_GAP_DAYS = 2  # linear interpolation ceiling; longer gaps stay NaN

# Season window for target construction (config constant, tunable).
# Widened from the plan's Sept 1 default: 14 of 46 Chemainus arrivals fall
# in August and would otherwise be dropped as "outside window" for no
# ecological reason -- these are still RUN_TYPE=FALL Chinook, just an early
# part of the same run. Aug 1 captures all but one (1993-07-18).
SEASON_START_MONTH_DAY = (8, 1)   # Aug 1
SEASON_END_MONTH_DAY = (12, 15)   # Dec 15

FEATURE_COLUMNS = ["Q_7", "Q_pulse", "Q_rising", "P", "P_7", "T", "T_trend7"]

# Cross-validation strategy for src/model.py -- per-site, because the four
# sites' usable-year records aren't uniform. Chemainus and Cowichan have a
# long-enough, reasonably continuous record for a causal rolling-origin
# evaluation. Nanaimo and Little Qualicum each have a real multi-year hole
# splitting their usable years into two disjoint eras (Little Qualicum's
# 1987-2012 discharge gap; Nanaimo's ~1995-2002 survey gap) -- leave-one-YEAR-
# out would still let the model train on other years from the SAME era as the
# held-out year, so leave-one-ERA-out is the harder, honest question there.
#   "loyo"              -- leave-one-year-out (unused by any site currently).
#   "logo_era"          -- leave-one-era-out block CV; see model.era_blocks.
#   "forward_chaining"  -- expanding-window rolling-origin CV; see
#                          model.forward_chaining_predict.
CV_METHOD = "forward_chaining"
ERA_GAP_YEARS = 5       # only used when CV_METHOD == "logo_era"
MIN_TRAIN_YEARS = 5     # only used when CV_METHOD == "forward_chaining"
