# Handoff — merged weather dataset (`merged_tavg_prcp_1960_2025.nc`)

**Session:** Wednesday 2026-08-26, afternoon (~15:30–17:00)
**Updated:** 2026-08-28 — pipeline finished and verified; scripts relocated to
`Old processing/` (see §9); notebook caveats refreshed to match.
**Author:** zcrookshank + Claude
**Project:** `ohw26_proj_fishyG` — salmon (NuSEDS escapement, Johnstone Strait / Strait of Georgia)
**Working dir:** `contributor_folders/Zoe_folder/Old processing` (scripts moved here after this
session; this doc's original commands assumed `contributor_folders/Zoe_folder` — `cd` one
level deeper than written below, or see the README at the folder root).

---

## 1. Goal

Extend the PNWNAmet gridded weather record (which stops at **2012-12-31**) to the present,
producing one merged `.nc` with **`tavg`** and **`pr`** for the region of interest, on the
native PNWNAmet grid.

**Region of interest = the PNWNAmet grid itself**, *not* the wider bbox that was in the
original notebook (`box(-125.5, 48.5, -122.5, 50.5)`):

| | value |
|---|---|
| grid | 19 lat × 31 lon, 0.0625° regular lat/lon |
| lat | 49.65625 → 48.53125 (**descending**) |
| lon | −125.09375 → −123.21875 (ascending) |

---

## 2. The original blocker, and what it actually was

The notebook used `pydaymet` with an SSL-verification bypass. **That could never have
worked.** ORNL's Daymet services now 301-redirect to **NASA Earthdata Login (URS)**; the
failure was HTTP **401**, not a certificate problem. Disabling cert checks does nothing
for a 401.

**Resolution:** the user already had valid credentials in `~/.netrc`:

```
machine urs.earthdata.nasa.gov
    login <user>
    password <pass>
```
(`chmod 600 ~/.netrc`; register free at <https://urs.earthdata.nasa.gov/users/new>)

`requests` re-applies netrc on cross-host redirect, so a plain `requests.Session().get()`
authenticates with no extra code. `pydaymet` was dropped entirely — it was never installed.

---

## 3. Data sources actually used

| Period | Source | Access | Notes |
|---|---|---|---|
| 1960–2012 | **PNWNAmet** | local files | `tavg=(tasmin+tasmax)/2`, `pr` |
| 2013–2025 land | **Daymet v4 R1** (1 km) | Earthdata **OPeNDAP DAP4** | area-averaged, ~29 px/cell |
| 2013–2025 ocean | **NCEP NARR** (32 km) | NOAA PSL, **no auth** | Daymet is land-only |

**Daymet record ends 2025-12-31.** 2026 is not published; requests past the end *silently
clamp* to the last day rather than erroring — easy to be fooled by.

### Rejected alternatives (don't re-investigate)
- **`thredds.daac.ornl.gov` NCSS** — migrated behind Earthdata; catalog paths 404.
- **GES DISC aggregated OPeNDAP (MERRA-2)** — returns **`410 Service Retired`**. Without
  it MERRA-2 is one granule *per day* (~16,800 requests).
- **ARCO-ERA5 on GCS** — anonymous access works, but chunks are `(1, 721, 1440)`: one hour
  of the *whole globe* each. Our box would mean reading ~2 TB.
- **Planetary Computer Daymet Zarr** — stops at 2020.
- **ERA5 via Copernicus CDS** — genuinely the best option (0.25°, server-side subsetting)
  but needs a free CDS account + `~/.cdsapirc`, which the user does not have. **This is the
  upgrade path if finer marine resolution is ever wanted.**

---

## 4. Pipeline — run in this order

All three steps below have already been run once end-to-end (see §5) and produced the
committed deliverable. This is the procedure to **re-run from scratch** if the source data
changes or the fit needs to be redone — not something to run routinely.

```bash
cd "Old processing"              # scripts live here, not at the Zoe_folder root
python build_merged_weather.py   # 1. PNWNAmet + Daymet splice   (~35 min cold, cached after)
python fill_ocean_cells.py       # 2. NARR marine fill            (~2 min, cached after)
python bias_correct_land.py      # 3. land bias correction
```

All downloads cache under `Old processing/cache/` and are skipped on re-run (the cache is
gitignored and not currently present on disk — a fresh run repopulates it). **`cache/daymet`
is 1.3 GB — do not commit it.**

> **Step 3 is NOT idempotent** and is guarded by a `land_bias_corrected` file attribute:
> running it against an already-corrected file raises `SystemExit` instead of double
> correcting. To refit, re-run steps 1 → 2 → 3 from scratch (step 1 rebuilds the merged file
> without the guard attribute set).

Two more scripts derive monthly-aggregate `.nc` files from the daily merged output above;
run them after step 3, not before — see §9.

---

## 5. Status at end of session

### Done and verified
- `data/Global_weather/merged_tavg_prcp_1960_2025.nc` (70.8 MB) — steps 1 and 2 complete.
- Time axis: **24,104 steps**, 1960-01-01 → 2025-12-31. That is 24,107 calendar days minus
  exactly the 3 Daymet leap-year drops (`2016-12-31`, `2020-12-31`, `2024-12-31`).
- Ocean fill validated **out-of-sample** (fitted 1979–2012, tested 2013+):

  | | 2012→2013 step |
  |---|---|
  | marine cells (NARR, corrected) | **−0.03 °C** |
  | land cells (Daymet, *uncorrected*) | **+0.85 °C** |

  Marine 2003–2012 and 2013–2022 means are identical (10.27 °C both).
- Notebook `global_weather_view.ipynb` rewritten: pydaymet cells replaced with load,
  splice diagnostics, and caveats.

### Completed at the very end of the session
- Overlap download finished **99/99, 0 failures**, and **`bias_correct_land.py` was run.**
  All three pipeline steps are now complete. 500 land cells corrected, 89 marine, 5 NaN.

### Measured land bias — IMPORTANT CORRECTION
An early naive comparison (2003–2012 PNWNAmet vs 2013–2022 Daymet) suggested Daymet was
**10.5% drier**. **That figure was wrong** — it compared *different decades*, so it mixed
product bias with real climate variability.

Fitted properly on **1980–2012, the same years in both products**, the actual monthly
precipitation ratios are:

```
J:1.03 F:1.07 M:1.04 A:1.02 M:0.95 J:0.90 J:0.95 A:0.97 S:0.96 O:1.05 N:1.06 D:1.06
```

Annual mean ratio **1.01** — Daymet's dry bias in this region is roughly **1%**, not 10.5%.
Direction is right (wet-season months need +3–7%, summer is slightly wet) but the magnitude
is small. Temperature offsets: −2.40 to +3.38 °C, mean −0.20 °C.

**Lesson: always fit bias corrections on overlapping years.** Cross-decade comparisons
conflate bias with climate change.

---

## 6. Status (updated 2026-08-28) and remaining optional work

All three pipeline steps ran to completion and were verified (§5). The notebook
(`global_weather_view.ipynb`) has been updated to describe all three steps and to quote the
corrected figures below rather than the earlier uncorrected/mis-fit ones. Nothing here is
required to use the deliverable — the two items below are optional upgrades, not fixes.

Post-correction splice step, for reference:

| | 2012→2013 step |
|---|---|
| land (corrected) | **+0.65 °C** |
| ocean (corrected) | **−0.03 °C** |

The land step did **not** collapse to ~0. The monthly-mean correction removed the
systematic component; the residual is probably mostly *real* — 2013–2015 were warm, and
the independently-sourced marine cells show the same warmth. It cannot be fully separated
from a single year's data. **Do not assume the splice is artifact-free.**

1. **Optional, discussed but not started — quantile mapping.** The current correction fixes
   *monthly means* only, not variability or extremes. For salmon this may matter (peak flows
   scour redds). Quantile mapping over the same 1980–2012 overlap is the upgrade; it would
   need the overlap re-downloaded (the cache was cleared after the run — see §4).

2. **Optional, offered and deferred — ocean variables.** The user chose "fill the ocean gaps
   in air temp/precip" over adding marine variables. If they later want SST/salinity:
   - **BC Lightstations** (DFO IOS via CIOOS ERDDAP, `BCSOP_daily`) — daily SST **and
     salinity** from **1914**; 13 stations inside the region (Entrance Island, Chrome Island,
     Departure Bay, Sisters Islets, Active Pass, Porlier Pass, Cape Beale, …). This mirror
     ends 2019-11-30; DFO publishes newer data on its own site.
   - **NOAA OISST v2.1** — daily SST 0.25°, 1981-09→present, no auth, via NOAA PSL THREDDS.
     Coarse here: only 20 of 45 cells in the box are valid ocean.

---

## 7. Gotchas discovered (all already handled in code — don't rediscover)

- **Reserved HDF5 attrs.** PNWNAmet coords carry `NAME`, `CLASS='DIMENSION_SCALE'`,
  `_Netcdf4Dimid`. netCDF-4 creates these internally, so writing them back raises
  `AttributeError: NetCDF: String match to name in use`. All three scripts strip them plus
  a stale `_FillValue`/`missing_value` of `-3.4e+38` on `pr`, and clear `.encoding`.
- **PSL `addLatLon=true` is broken for NARR** — returns lat −89.97, lon +70. Coordinates are
  derived from the Lambert params instead. Its `false_easting`/`false_northing` are in **km**
  while `x`/`y` are in **metres**. Verified against the file's own bbox to within half a cell.
- **`tasmax` starts 1945**, `tasmin`/`pr` start 1960. *Not* a bug in the original notebook —
  xarray's default `arithmetic_join='inner'` already clips to the intersection.
- **Daymet 365-day calendar** — 31 Dec dropped in leap years. Left absent rather than
  inserting fake NaN rows.
- **5 cells are NaN for the entire record** (48.53–48.59 °N, ~−125.0 °W, SW corner). They
  fall outside the PNWNAmet domain, so there is no reference to calibrate a fill against.
- **`pip` targets a different interpreter than `python`** on this machine — use
  `python -m pip`. Installing `gcsfs` upgraded `fsspec` to 2026.7.0, which pip flagged as
  incompatible with the existing `s3fs` 2025.3.2. Nothing in this pipeline uses s3fs.
- **NARR `air.2m` is a true daily mean**, not `(tmin+tmax)/2` like PNWNAmet/Daymet. The
  monthly offset absorbs the systematic part, but they are not identical.

---

## 8. Files

All paths below are relative to `Old processing/` (see §9 for why).

| File | Role |
|---|---|
| `build_merged_weather.py` | PNWNAmet + Daymet splice → merged `.nc` |
| `fill_ocean_cells.py` | NARR marine fill, bias-corrected vs PNWNAmet 1979–2012 |
| `bias_correct_land.py` | Land bias correction vs PNWNAmet 1980–2012 — **done**, see §5/§6 |
| `build_monthly_weather.py` | Monthly aggregates from the merged daily `.nc` (run last) |
| `extract_monthly_prcp.py` | Standalone monthly precipitation `.nc`, derived from the above |
| `extract_t_max_monthly.py` | Standalone monthly max-temperature `.nc`, derived from the above |
| `global_weather_view.ipynb` | Load, diagnostics, caveats — covers all three splice steps |
| `plot_weather_dates.py`, `lat_long.ipynb`, `salmon_data_proc.ipynb` | Exploratory/plotting scripts from earlier in the project; not part of the build pipeline |
| `cache/daymet/` | 1.3 GB Daymet subsets — **do not commit** (gitignored; not present until a step-1/3 re-run) |
| `cache/narr/` | 6 MB NARR subsets |
| `cache/{build,narr,overlap}.log` | Run logs |
| `../../../data/Global_weather/merged_tavg_prcp_1960_2025.nc` | **The deliverable** |
| `../../../data/Global_weather/{merged_tavg_prcp_1960_2025_monthly,monthly_prcp_1960_2025,t_max_monthly_1960_2025}.nc` | Monthly-aggregate derivatives, built after the deliverable |

### Variables in the output
- `tavg` (°C), `pr` (mm/day), dims `(time, lat, lon)`
- `data_source` (time) — `0` = PNWNAmet, `1` = Daymet
- `ocean_filled` (lat, lon) — `1` = NARR-filled marine cell
- `land_corrected` (lat, lon) — `1` = bias-corrected land cell (added by step 3)

---

## 9. Folder reorg since this session (2026-08-27/28)

The scripts and notebooks described above were moved from the `Zoe_folder` root into
`Zoe_folder/Old processing/` — see the folder's `README.md` for the current top-level
layout (a `src/` salmon-spawning pipeline was added alongside this weather pipeline). The
data path also changed name along the way: the deliverable lives at
`data/Global_weather/` (underscore, no space) — some earlier drafts of this doc referred to
`data/Global Weather/`; the scripts' own `DATA` constant is the source of truth if the two
ever disagree.
