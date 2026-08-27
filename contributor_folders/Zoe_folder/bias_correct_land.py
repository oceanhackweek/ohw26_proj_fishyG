#!/usr/bin/env python
"""
Bias-correct the LAND half of the 2013+ splice against PNWNAmet.

The marine cells are already corrected (fill_ocean_cells.py calibrates NARR against
PNWNAmet). The land cells are still raw Daymet, which steps roughly +0.85 degC at
2013-01-01 and is known to under-report precipitation in coastal BC, where much of the
rainfall is orographic and Daymet's interpolation smooths the terrain.

Daymet and PNWNAmet overlap for 1980-2012, so the correction is fitted on those 33 years,
per cell and per calendar month:

    tavg  ->  additive offset       PNWNAmet_monthly_mean - Daymet_monthly_mean
    pr    ->  multiplicative ratio  PNWNAmet_monthly_mean / Daymet_monthly_mean

and applied to 2013-2025. A multiplicative factor is the right form for precipitation: it
preserves dry days and scales wet ones, whereas an additive offset would invent drizzle on
every dry day.

Run AFTER build_merged_weather.py and fill_ocean_cells.py.
NOT idempotent by construction, so it refuses to run twice (guarded by a file attribute).
"""
import os

import numpy as np
import xarray as xr

import build_merged_weather as B

DATA = B.DATA
MERGED = os.path.join(DATA, "merged_tavg_prcp_1960_2025.nc")

OVERLAP = range(1980, 2013)     # Daymet starts 1980; PNWNAmet ends 2012
APPLY_FROM = "2013-01-01"
RATIO_CLIP = (0.5, 2.5)         # guard against noisy dry-month ratios
GUARD_ATTR = "land_bias_corrected"


def daymet_overlap(lat, lon, lat_edges, lon_edges):
    """Regrid Daymet over the overlap years onto the PNWNAmet grid."""
    nlat, nlon = lat.size, lon.size
    win = B.subset_window(lat_edges, lon_edges)
    paths = {(v, y): B.fetch(v, y, win) for y in OVERLAP for v in B.DAYMET_VARS}
    M = B.build_regridder(paths[(B.DAYMET_VARS[0], OVERLAP[0])],
                          lat_edges, lon_edges, nlat, nlon)
    per = []
    for year in OVERLAP:
        f, tv = {}, None
        for v in B.DAYMET_VARS:
            f[v], t = B.regrid(paths[(v, year)], v, M, nlat, nlon)
            tv = t if tv is None else tv
        per.append(xr.Dataset(
            {"tavg": (("time", "lat", "lon"), (f["tmax"] + f["tmin"]) / 2.0),
             "pr": (("time", "lat", "lon"), f["prcp"])},
            coords={"time": tv, "lat": lat, "lon": lon}))
    ds = xr.concat(per, dim="time").sortby("time")
    ds["time"] = ds.time.dt.floor("D")
    return ds


def main():
    ds = xr.open_dataset(MERGED).load()
    if ds.attrs.get(GUARD_ATTR):
        raise SystemExit(
            f"{os.path.basename(MERGED)} is already land-bias-corrected "
            f"({ds.attrs[GUARD_ATTR]}).\nRe-run build_merged_weather.py and "
            "fill_ocean_cells.py first if you want to refit."
        )
    for v in ds.variables.values():
        for k in ("NAME", "CLASS", "_Netcdf4Dimid", "_FillValue", "missing_value"):
            v.attrs.pop(k, None)
        v.encoding = {}

    lat, lon, lat_edges, lon_edges = B.target_grid()
    print(f"Regridding Daymet {OVERLAP[0]}-{OVERLAP[-1]} for the overlap ...")
    day = daymet_overlap(lat, lon, lat_edges, lon_edges)

    # PNWNAmet reference over the same years, straight from source (never corrected)
    sl = slice(f"{OVERLAP[0]}-01-01", f"{OVERLAP[-1]}-12-31")
    pr = xr.open_dataset(os.path.join(DATA, "PNWNAmet_pr.nc.nc")).pr.sel(time=sl)
    tmin = xr.open_dataset(os.path.join(DATA, "PNWNAmet_tasmin.nc.nc")).tasmin.sel(time=sl)
    tmax = xr.open_dataset(os.path.join(DATA, "PNWNAmet_tasmax.nc.nc")).tasmax.sel(time=sl)
    ref = xr.Dataset({"tavg": (tmin + tmax) / 2.0, "pr": pr})

    day = day.reindex(time=ref.time)      # drop Daymet's leap-day mismatch

    print("Fitting monthly bias correction ...")
    ref_m = ref.groupby("time.month").mean("time")
    day_m = day.groupby("time.month").mean("time")

    t_off = (ref_m.tavg - day_m.tavg).values                       # (12, lat, lon)
    with np.errstate(invalid="ignore", divide="ignore"):
        p_rat = np.where(day_m.pr.values > 0.01,
                         ref_m.pr.values / day_m.pr.values, 1.0)
    p_rat = np.clip(np.nan_to_num(p_rat, nan=1.0), *RATIO_CLIP)

    # land = everything not filled from NARR, and not permanently missing
    ocean = ds.ocean_filled.values == 1 if "ocean_filled" in ds else np.zeros_like(t_off[0], bool)
    valid = np.isfinite(ds.tavg.sel(time=slice(APPLY_FROM, None)).values).any(axis=0)
    land = valid & ~ocean
    print(f"  land cells to correct: {int(land.sum())} "
          f"(marine {int(ocean.sum())} already corrected, "
          f"{int((~valid).sum())} permanently missing)")

    lt = np.where(land, t_off, np.nan)
    lp = np.where(land, p_rat, np.nan)
    print(f"  tavg offset  (land): {np.nanmin(lt):+.2f} to {np.nanmax(lt):+.2f} degC, "
          f"mean {np.nanmean(lt):+.2f}")
    print(f"  pr    ratio  (land): {np.nanmin(lp):.2f} to {np.nanmax(lp):.2f}, "
          f"mean {np.nanmean(lp):.2f}")
    wet = np.nanmean(lp, axis=(1, 2))
    print("  monthly mean pr ratio: " +
          " ".join(f"{m}:{r:.2f}" for m, r in zip("JFMAMJJASOND", wet)))

    print(f"Applying to {APPLY_FROM} onward (land cells only) ...")
    tgt = ds.sel(time=slice(APPLY_FROM, None))
    mon = tgt.time.dt.month.values - 1
    mask3 = np.broadcast_to(land, tgt.tavg.shape)

    new_t = np.where(mask3, tgt.tavg.values + t_off[mon], tgt.tavg.values)
    new_p = np.where(mask3, tgt.pr.values * p_rat[mon], tgt.pr.values)
    ds["tavg"].loc[dict(time=tgt.time)] = new_t.astype(np.float32)
    ds["pr"].loc[dict(time=tgt.time)] = new_p.astype(np.float32)

    ds["land_corrected"] = (("lat", "lon"), land.astype(np.int8))
    ds["land_corrected"].attrs = {
        "long_name": "land cell bias-corrected against PNWNAmet for 2013 onward",
        "flag_values": np.array([0, 1], np.int8),
        "flag_meanings": "not_corrected corrected",
    }
    ds.attrs[GUARD_ATTR] = (
        f"land cells corrected against PNWNAmet on the {OVERLAP[0]}-{OVERLAP[-1]} overlap, "
        "per cell and calendar month: additive offset for tavg, multiplicative ratio for "
        f"pr (clipped to {RATIO_CLIP}). Marine cells were corrected separately via NARR."
    )
    ds.attrs["caveats"] = (
        "1) Both land and marine cells are now bias-corrected to the PNWNAmet baseline, so "
        "the 2013 splice should be near-continuous; residual step is reported by the "
        "verification in the notebook. "
        "2) Correction is a monthly mean adjustment: it removes systematic bias, not "
        "differences in day-to-day variability or extremes. "
        "3) Daymet uses a 365-day calendar: 31 December is absent in leap years "
        "(2016, 2020, 2024). "
        "4) Five southwest cells lie outside the PNWNAmet domain and are NaN throughout."
    )

    enc = {v: {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": np.nan}
           for v in ["tavg", "pr"]}
    for v in ("ocean_filled", "land_corrected"):
        if v in ds:
            enc[v] = {"zlib": True, "complevel": 4, "dtype": "int8"}
    enc["time"] = {"units": "days since 1960-01-01", "calendar": "standard",
                   "dtype": "float64"}
    tmp = MERGED + ".tmp"
    ds.to_netcdf(tmp, encoding=enc)
    os.replace(tmp, MERGED)
    print(f"\nUpdated {MERGED} ({os.path.getsize(MERGED)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
