#!/usr/bin/env python
"""
Fill the marine (ocean) cells of merged_tavg_prcp_1960_2025.nc for 2013 onward.

PNWNAmet interpolates over water, so ocean cells are already populated for 1960-2012.
Daymet is land-only, so those same cells go NaN from 2013. This script patches them with
NARR (NCEP North American Regional Reanalysis, 32 km, 1979-2026), which is a full
atmospheric reanalysis and so has values over water.

NARR is bias-corrected against PNWNAmet over their 1979-2012 overlap, per cell and per
calendar month (additive offset for temperature, multiplicative ratio for precipitation),
so the filled ocean series is continuous with the PNWNAmet history rather than stepping
at 2013.

Source: NOAA PSL THREDDS - no authentication required.
Run AFTER build_merged_weather.py. Idempotent: only NaN cells are touched.
"""
import os
import time

import numpy as np
import requests
import xarray as xr
from pyproj import CRS, Transformer
from scipy import sparse
from scipy.spatial import Delaunay

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "..", "data", "Global_weather")
CACHE = os.path.join(HERE, "cache", "narr")
MERGED = os.path.join(DATA, "merged_tavg_prcp_1960_2025.nc")

PSL = "https://psl.noaa.gov/thredds/ncss/grid/Datasets/NARR/Dailies/monolevel"
BOX = dict(north=49.8, south=48.4, west=-125.3, east=-123.1)

CAL_START, CAL_END = 1979, 2012     # PNWNAmet overlap used to fit the bias correction
FILL_START = 2013                   # first year needing a marine fill
NARR_VARS = {"air.2m": "air", "apcp": "apcp"}

# NARR Lambert conformal grid (false_easting/northing are in km; x/y are in metres)
NARR_CRS = CRS.from_dict({
    "proj": "lcc", "lat_1": 50.0, "lat_2": 50.0, "lat_0": 50.0, "lon_0": -107.0,
    "x_0": 5632.64222547 * 1000.0, "y_0": 4612.54565137 * 1000.0,
    "a": 6371229.0, "b": 6371229.0,
})


def fetch_narr(fname, var, year):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"narr_{var}_{year}.nc")
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return path
    url = f"{PSL}/{fname}.{year}.nc"
    params = {
        "var": var, "horizStride": 1, "accept": "netcdf",
        "time_start": f"{year}-01-01T00:00:00Z",
        "time_end": f"{year}-12-31T23:59:59Z", **BOX,
    }
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=600)
            r.raise_for_status()
            tmp = path + ".part"
            with open(tmp, "wb") as fh:
                fh.write(r.content)
            os.replace(tmp, path)
            return path
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"  {var} {year}: {type(exc).__name__} — retry {attempt+1}/3")
            time.sleep(5 * (attempt + 1))


def narr_lonlat(sample):
    """NARR cell-centre lon/lat, derived from the Lambert grid (PSL's addLatLon is wrong)."""
    d = xr.open_dataset(sample)
    X, Y = np.meshgrid(d.x.values, d.y.values)
    d.close()
    tr = Transformer.from_crs(NARR_CRS, "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(X, Y)
    return lon.ravel(), lat.ravel(), X.shape


def interp_weights(src_lon, src_lat, tgt_lon, tgt_lat):
    """Sparse barycentric (linear) interpolation matrix, NARR points -> target points."""
    src = np.column_stack([src_lon, src_lat])
    tgt = np.column_stack([tgt_lon, tgt_lat])
    tri = Delaunay(src)
    simp = tri.find_simplex(tgt)
    if (simp < 0).any():
        raise RuntimeError("target cells fall outside the NARR subset — widen BOX")
    T = tri.transform[simp, :2]
    r = tgt - tri.transform[simp, 2]
    b = np.einsum("ijk,ik->ij", T, r)
    bary = np.column_stack([b, 1.0 - b.sum(axis=1)])
    verts = tri.simplices[simp]
    rows = np.repeat(np.arange(len(tgt)), 3)
    return sparse.csr_matrix(
        (bary.ravel(), (rows, verts.ravel())), shape=(len(tgt), len(src))
    )


def load_narr(var, years, W, ncell):
    """Download, interpolate to the target cells, return (time, ncell)."""
    chunks, times = [], []
    for fname, v in NARR_VARS.items():
        if v != var:
            continue
        for year in years:
            p = fetch_narr(fname, v, year)
            d = xr.open_dataset(p)
            arr = d[v].values.reshape(d[v].shape[0], -1)      # (t, npix)
            chunks.append((W @ arr.T).T)                       # (t, ncell)
            times.append(d.time.values)
            d.close()
    return np.concatenate(chunks).astype(np.float32), np.concatenate(times)


def main():
    if not os.path.exists(MERGED):
        raise SystemExit(f"{MERGED} not found — run build_merged_weather.py first")

    ds = xr.open_dataset(MERGED).load()
    for _v in ds.variables.values():          # same reserved-attr problem on rewrite
        for _k in ("NAME", "CLASS", "_Netcdf4Dimid", "_FillValue", "missing_value"):
            _v.attrs.pop(_k, None)
        _v.encoding = {}
    lat, lon = ds.lat.values, ds.lon.values
    LO, LA = np.meshgrid(lon, lat)
    ncell = LO.size

    years = list(range(CAL_START, 2026))
    print(f"Downloading NARR {years[0]}-{years[-1]} (cached in cache/narr/) ...")
    sample = fetch_narr("air.2m", "air", CAL_START)
    for fname, v in NARR_VARS.items():
        for y in years:
            fetch_narr(fname, v, y)
    print("  done")

    slon, slat, shape = narr_lonlat(sample)
    print(f"NARR subset grid: {shape[0]}x{shape[1]} cells")
    W = interp_weights(slon, slat, LO.ravel(), LA.ravel())

    print("Interpolating NARR to the PNWNAmet grid ...")
    air, t_air = load_narr("air", years, W, ncell)
    air = air - 273.15                                        # K -> degC
    apcp, t_apcp = load_narr("apcp", years, W, ncell)         # kg/m2 == mm/day
    narr = xr.Dataset(
        {
            "tavg": (("time", "cell"), air),
            "pr": (("time", "cell"), apcp[: len(t_air)] if len(t_apcp) != len(t_air) else apcp),
        },
        coords={"time": t_air, "cell": np.arange(ncell)},
    )

    # ---- fit monthly bias correction over the PNWNAmet overlap -------------------
    print(f"Fitting bias correction on {CAL_START}-{CAL_END} ...")
    ref = ds.sel(time=slice(f"{CAL_START}-01-01", f"{CAL_END}-12-31"))
    ref_flat = xr.Dataset(
        {
            "tavg": (("time", "cell"), ref.tavg.values.reshape(ref.sizes["time"], -1)),
            "pr": (("time", "cell"), ref.pr.values.reshape(ref.sizes["time"], -1)),
        },
        coords={"time": ref.time.values, "cell": np.arange(ncell)},
    )
    nar_ref = narr.sel(time=slice(f"{CAL_START}-01-01", f"{CAL_END}-12-31"))
    nar_ref = nar_ref.reindex(time=ref_flat.time)

    ref_m = ref_flat.groupby("time.month").mean("time")
    nar_m = nar_ref.groupby("time.month").mean("time")
    t_off = (ref_m.tavg - nar_m.tavg).values                        # (12, ncell) additive
    with np.errstate(invalid="ignore", divide="ignore"):
        p_rat = np.where(nar_m.pr.values > 0.01, ref_m.pr.values / nar_m.pr.values, 1.0)
    p_rat = np.clip(np.nan_to_num(p_rat, nan=1.0), 0.2, 5.0)        # (12, ncell) multiplicative
    print(f"  temperature offset: {np.nanmin(t_off):+.2f} to {np.nanmax(t_off):+.2f} degC")
    print(f"  precipitation ratio: {p_rat.min():.2f} to {p_rat.max():.2f}")

    # ---- apply to the fill period ------------------------------------------------
    fill = narr.sel(time=slice(f"{FILL_START}-01-01", None)).reindex(
        time=ds.time.sel(time=slice(f"{FILL_START}-01-01", None))
    )
    mon = fill.time.dt.month.values - 1
    tavg_c = fill.tavg.values + t_off[mon, :]
    pr_c = fill.pr.values * p_rat[mon, :]

    nt = fill.sizes["time"]
    tavg_c = tavg_c.reshape(nt, lat.size, lon.size)
    pr_c = pr_c.reshape(nt, lat.size, lon.size)

    tgt = ds.sel(time=slice(f"{FILL_START}-01-01", None))
    gap = np.isnan(tgt.tavg.values)
    n_before = int(gap.sum())
    filled_t = np.where(gap, tavg_c, tgt.tavg.values)
    filled_p = np.where(np.isnan(tgt.pr.values), pr_c, tgt.pr.values)

    ds["tavg"].loc[dict(time=tgt.time)] = filled_t
    ds["pr"].loc[dict(time=tgt.time)] = filled_p

    still = int(np.isnan(ds.sel(time=tgt.time).tavg.values).sum())
    print(f"Filled {n_before - still} of {n_before} missing tavg values from {FILL_START} "
          f"({still} still NaN)")
    if still:
        print("  remaining NaN cells sit outside the PNWNAmet domain, so there is no "
              "reference to calibrate against; they are NaN for the whole record.")

    # per-cell flag: was this cell ever ocean-filled?
    ever = np.zeros((lat.size, lon.size), np.int8)
    ever[gap.any(axis=0)] = 1
    ds["ocean_filled"] = (("lat", "lon"), ever)
    ds["ocean_filled"].attrs = {
        "long_name": "cell was gap-filled from NARR for 2013 onward",
        "flag_values": np.array([0, 1], np.int8),
        "flag_meanings": "not_filled NARR_filled",
    }
    ds.attrs["ocean_fill"] = (
        f"Marine cells from {FILL_START} onward filled with NCEP NARR (32 km), "
        f"bias-corrected against PNWNAmet over {CAL_START}-{CAL_END} by calendar month "
        "(additive offset for tavg, multiplicative ratio for pr). "
        "NARR daily air.2m is a true daily mean rather than (tmin+tmax)/2; the monthly "
        "offset absorbs the systematic part of that difference."
    )
    ds.attrs["source_NARR"] = "https://psl.noaa.gov/data/gridded/data.narr.html"

    enc = {v: {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": np.nan}
           for v in ["tavg", "pr"]}
    enc["ocean_filled"] = {"zlib": True, "complevel": 4, "dtype": "int8"}
    enc["time"] = {"units": "days since 1960-01-01", "calendar": "standard",
                   "dtype": "float64"}
    tmp = MERGED + ".tmp"
    ds.to_netcdf(tmp, encoding=enc)
    os.replace(tmp, MERGED)
    print(f"\nUpdated {MERGED} ({os.path.getsize(MERGED)/1e6:.1f} MB)")
    print(f"ocean-filled cells: {int(ever.sum())} of {ever.size}")


if __name__ == "__main__":
    main()
