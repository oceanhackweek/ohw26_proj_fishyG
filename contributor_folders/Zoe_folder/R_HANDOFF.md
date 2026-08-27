# Handoff — R / Shiny weather layers (`shinyapp_weather.qmd`)

**Session:** Thursday 2026-08-27
**Author:** zcrookshank + Claude
**Project:** `ohw26_proj_fishyG` — salmon (NuSEDS escapement, Vancouver Island)
**Working dir:** `contributor_folders/Zoe_folder`
**Companion doc:** [`HANDOFF.md`](HANDOFF.md) — how the `.nc` was built
**Plan doc:** <https://claude.ai/code/artifact/c5d774f2-a4f5-475f-8912-40ced3170c00>

---

## 0. Read this first

**None of the R in this handoff has ever been executed.** The machine it was written on has
no R installed — no `Rscript`, no R.framework, no RStudio. The code was reviewed by hand and
delimiter-balanced per chunk, but every R API call in it is an *assumption* until you run it.

Section 4 is a checklist of exactly which assumptions to check, in the order they will fail.
Budget 20–30 minutes for the first run. Don't assume a clean launch.

---

## 1. Goal

Linnea's `Linnea_folder/shinyapp.qmd` maps NuSEDS Chinook survey sites with a model/no-model
filter. She couldn't open both weather variables out of
`data/Global Weather/merged_tavg_prcp_1960_2025.nc`.

Deliverable: **`shinyapp_weather.qmd`** — the same site map, plus `tavg` and `pr` as switchable
raster layers driven by a **daily** date slider.

---

## 2. The blocker, and what it actually was

A `SpatRaster` holds **one** variable. Point `rast()` at a netCDF containing several and it
picks the first data variable, prints a note about the rest, and carries on:

```
varname used: tavg (Daily mean surface (2m) air temperature)
Other variables: pr
```

There is no call that returns both. **Read the file twice, naming the variable each time:**

```r
tavg_r <- rast(nc_path, subds = "tavg")
pr_r   <- rast(nc_path, subds = "pr")
```

Two things were compounding it:

- The app read `~/FishyG/data/Global_weather/PNWNamet_tasmax.nc.nc` — a different,
  single-variable file, in a folder that doesn't exist in the repo. The real path is
  `data/Global Weather/` — **a space, and a capital W**. The `.nc.nc` double extension belongs
  to the two old PNWNAmet files, not the merged one.
- The file also carries `ocean_filled`, `land_corrected` and `data_source`. They appear in
  `rast()`'s variable listing and look like extra layers. They are QC flags — don't map them.

---

## 3. What was measured (and what it changed)

The first plan aggregated the record to 66 annual layers with `tapp()`, on the assumption that
24,104 daily layers would be too slow to scrub through. **That was measured and it was wrong.**

| Read pattern (both variables) | as shipped | rechunked |
|---|---|---|
| First read, cold cache | 0.17 s | 0.001 s |
| Jump to a random date | 0.0043 s | 0.0005 s |
| Drag day by day | <0.001 s | <0.001 s |

So the app does **no precomputation** — it reads one day per frame straight off disk. The
one-off 0.17 s is the file's chunk layout: `tavg` and `pr` are stored in two enormous
`12052 × 10 × 16` time-chunks, so the first read decompresses ~31 MB to retrieve 2 KB, after
which the whole variable sits in the netCDF chunk cache.

**Caveat that matters to you:** those numbers came from the netCDF4 **Python** library. GDAL —
which is what terra reads through — may size its chunk cache differently. See §4.7.

Rechunking is *optional insurance*, not a prerequisite. If terra turns out to be slow:

```bash
nccopy -c "time/30,lat/19,lon/31" -d 4 -s \
  "data/Global Weather/merged_tavg_prcp_1960_2025.nc" merged_rechunked.nc
```

~2 seconds, and the output is **smaller** (66 MB vs 70.9 MB).

Values hard-coded in the app, measured over all 24,104 layers so startup doesn't rescan ~130 MB:

| | value |
|---|---|
| `tavg` range | −22.62 → 32.80 °C |
| `pr` range | 0 → 249.1 mm/day |
| `pr` percentiles | 50th 1.1 · 75th 6.9 · 90th 17.1 · 95th 26.1 · **99th 49.5** |
| `pr` cell-days under 0.1 mm | **46.4 %** |
| dates | 1960-01-01 → 2025-12-31, complete, n = 24,104 |

That precipitation distribution is why `pr` uses `colorBin` on log-ish breaks
(`0, 0.1, 1, 2.5, 5, 10, 20, 35, 50, 249`) and not a linear ramp. A linear scale to the wettest
day on record renders nearly every day as the same near-empty colour.

---

## 4. First-run checklist

### 4.1 Don't knit it — run it

The app lives in a `{r app}` chunk ending in `shinyApp(ui, server)`. **`quarto render` on this
will not give you a working app** — it will hang or emit a dead HTML shell. Same is true of
Linnea's file.

Run the chunks interactively in RStudio (Run All, or Ctrl/Cmd-Shift-Enter per chunk). To get a
served document instead, add `server: shiny` to the YAML and use `quarto serve`.

### 4.2 R version

The app uses the native pipe `|>`, which needs **R ≥ 4.1**. Linnea's file uses magrittr `%>%`.
If you're on older R, swap them — the semantics are the same here.

### 4.3 Packages

```r
install.packages(c("shiny", "leaflet", "terra", "readr", "dplyr"))
```

Linnea's file loads ~25 libraries; most were unused and each one slows app start, so this
version loads only these five. If something is missing at runtime it will be an obvious
`could not find function` — add it back rather than restoring the whole list.

### 4.4 Smoke-test before launching the app

Run this first. It exercises every assumption that matters in about ten lines, and tells you
which one broke without the Shiny layer in the way.

```r
library(terra)
f <- "../../data/Global Weather/merged_tavg_prcp_1960_2025.nc"   # from Zoe_folder

tavg_r <- rast(f, subds = "tavg")
pr_r   <- rast(f, subds = "pr")

nlyr(tavg_r)                    # expect 24104
crs(tavg_r)                     # expect a WKT string, NOT ""
d <- as.Date(terra::time(tavg_r), tz = "UTC")
range(d); length(d)             # expect 1960-01-01 .. 2025-12-31, 24104
sum(format(d, "%m-%d") == "12-31")   # expect 63, not 66 (see §5)

system.time(x <- tavg_r[[ match(as.Date("2020-07-01"), d) ]])   # time this
plot(x)                         # should look like Vancouver Island, right way up
```

If `plot(x)` is upside down or in the wrong hemisphere, the CRS or the descending `lat` axis is
the culprit — not the app.

### 4.5 `leaflet` must be ≥ 2.2.0

`addRasterImage()` only accepts a `SpatRaster` directly from leaflet 2.2.0. The app warns at
load if yours is older. Either upgrade, or wrap each layer:

```r
addRasterImage(raster::raster(tavg_r[[i]]), ...)
```

### 4.6 Assumptions to confirm

| Assumption | If wrong |
|---|---|
| `terra::time()` returns Date/POSIXct, not raw numbers | Parse CF units yourself — but **not** by date arithmetic, see §5 |
| `crs()` returns `""` when unset (not `NA`) | Adjust the `nzchar()` guard in the `rasters` chunk |
| `xmin()`/`ymin()` work on a `SpatExtent` | Use `as.vector(ext(tavg_r))` instead |
| `addLegend(layerId=)` replaces in place | Fall back to `removeControl("wxlegend")` first |
| `clearGroup()` takes a character vector | Call it once per group name |
| `updateSliderInput()` accepts `Date` min/max | Switch the slider to day-of-year integers |
| `method = "ngb"` is valid in `addRasterImage()` | Drop the argument; you lose crisp cell edges |

### 4.7 Time a terra read

The §3 benchmark was Python. Check `system.time()` from §4.4. Roughly ≤50 ms is fine. If it's
hundreds of ms *per slider move*, GDAL isn't caching chunks the way netCDF4 did — rechunk per
§3 and re-point `nc_path`.

---

## 5. Gotchas already handled in the code — don't rediscover

- **Three days are missing from the record.** Daymet uses a 365-day calendar, so **31 December
  is absent in 2016, 2020 and 2024**. There are 24,104 layers where a naive `seq()` of dates
  gives 24,107.
- **Therefore: never resolve a date to a layer by arithmetic.** "Days since 1960-01-01, plus
  one" drifts **one layer late after 2016, two after 2020, three after 2024** — showing
  plausible weather from the wrong day, with no error. The app uses `match()` against the
  stored `time()` vector. This is the single most dangerous trap in the file.
- The day slider is rebuilt per year from the dates actually present, which is *also* what
  stops those three 31 Decembers from being selectable.
- **A single slider over all 24,104 days is unusable** — about one pixel per 100 days in a
  250 px panel. Hence year selector + day slider scoped to that year (≤365 positions, arrow
  keys move exactly one day).
- **Five cells are NaN for the entire record** (SW corner, outside the PNWNAmet domain).
  `na.color = "transparent"` on both palettes, or you get grey squares over open water.
- **`stream_observed_count` uses `-989898` as its missing sentinel.** Set to `NA`, or popups
  report negative Chinook.
- **The map fits to the weather grid, not the sites.** Survey data reaches Haida Gwaii and up
  the mainland (lat 48.4–51.2); the raster is eastern Vancouver Island only (48.5–49.7).
  Fitting to the sites opens on mostly empty ocean. Off-grid sites still draw — there is just
  no weather under them.
- **`crs(r) <- ...` inside a `for` loop over a list does nothing.** R copy-on-modify: it
  reassigns the loop variable and discards it. Set each raster explicitly. (This was a real bug
  in the first draft.)

### Corrections to the plan doc — the artifact is right, earlier drafts of it were not

- **Do not use `clearControls()` to clear the legend.** It also removes the layers control added
  in `renderLeaflet`, so the marker toggle disappears on the first slider move. Give the legend
  a `layerId` — re-adding with the same id replaces it in place.
- **Do not put the two rasters in leaflet `baseGroups`.** A base group whose layers are added
  *after* the control exists is drawn regardless of which radio is lit, so both ramps stack
  until you toggle, and each redraw reads two layers instead of one. The app uses plain
  `radioButtons()`. Deterministic, half the I/O, trivial legend logic.

---

## 6. Next steps

1. **Run §4.4, then the app.** Everything else is downstream of that.
2. **Decide what the markers should do.** They currently show one pin per stream, with a
   checkbox for "only sites surveyed this year". Filtering annual survey counts to a single
   *date* would show nothing, so this was a judgement call — change it if the ecology wants
   something else.
3. **Decide the year range.** Survey years run 1929–2024; the weather record is 1960–2025. The
   selector is driven by the raster, so pre-1960 survey years are unreachable. If you'd rather
   span the survey range and show no raster before 1960, that's a small change to `nc_years`.
4. **Consider adding the annual view back as a second mode.** Daily answers "what were
   conditions during this spawning window"; it does *not* answer "is this river warming". The
   annual version is `tapp(tavg_r, format(nc_dates, "%Y"), mean)` and
   `tapp(pr_r, ..., sum)` on the same two rasters — cheap, and a different question.
5. **Extract per-site time series.** The obvious join to Hannah's RF model
   (`Hannah_folder/fishyG_RFModel_20260825.qmd`): `terra::extract()` the two variables at the
   survey coordinates gives a daily weather record per stream. Note only sites inside the grid
   return values; the rest come back `NA`.
6. **Not started — flow data.** `data/{Nanaimo,Cowichan,Chemanius,LilQualicum}_Riv_Flow.csv`
   exist and match the four modelled streams. Overlaying gauge flow on the same date slider is
   the natural next layer.

---

## 7. Files

| File | Role |
|---|---|
| `shinyapp_weather.qmd` | **The deliverable.** Site map + daily `tavg`/`pr` layers |
| `../Linnea_folder/shinyapp.qmd` | Original site map this extends — left untouched |
| `../../data/Global Weather/merged_tavg_prcp_1960_2025.nc` | The weather file (70.9 MB) |
| `../../data/survey_sites_vancouver_isl.csv` | 11,008 rows, 265 streams, Chinook only, 1929–2024 |
| `HANDOFF.md` | How the `.nc` was built, and its caveats |

### Structure of `shinyapp_weather.qmd`

| Chunk | Does |
|---|---|
| `load-packages` | 5 libraries + leaflet version check |
| `paths` | Walks up from `getwd()` to find `data/` — runs from Zoe_folder or repo root |
| `sites` | Reads the CSV, adds `model`, nulls the `-989898` sentinel |
| `rasters` | Two `rast(subds=)` calls, CRS assertion, date vector, `layer_for()` |
| `palettes` | Fixed domains, binned precip breaks, colours, grid extent |
| `app` | `ui` + `server` + `shinyApp()` |

---

## 8. Status

| | |
|---|---|
| Written | ✅ `contributor_folders/Zoe_folder/shinyapp_weather.qmd` |
| Delimiter-balanced per chunk | ✅ |
| Reviewed by hand | ✅ (4 bugs found and fixed pre-delivery) |
| **Executed** | ❌ **never — no R on the authoring machine** |
| Committed | ❌ untracked, not pushed |
