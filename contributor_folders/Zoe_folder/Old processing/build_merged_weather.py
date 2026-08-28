#!/usr/bin/env python
"""
Backfill PNWNAmet (1960-2012) with Daymet v4 R1 (2013-2025) on the PNWNAmet grid.

Daymet is pulled from NASA Earthdata OPeNDAP (DAP4 spatial subsetting), which needs
an Earthdata Login. Credentials are read from ~/.netrc:

    machine urs.earthdata.nasa.gov
        login YOUR_USERNAME
        password YOUR_PASSWORD

Register free at https://urs.earthdata.nasa.gov/users/new

Output: ../../data/Global_weather/merged_tavg_prcp_1960_2025.nc  (vars: tavg, pr)
"""
import os
import sys
import time

import numpy as np
import requests
import xarray as xr
from pyproj import CRS, Transformer
from scipy import sparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "..", "data", "Global_weather")
CACHE = os.path.join(HERE, "cache", "daymet")
OUT = os.path.join(DATA, "merged_tavg_prcp_1960_2025.nc")

COLLECTION = "C2532426483-ORNL_CLOUD"
BASE = f"https://opendap.earthdata.nasa.gov/collections/{COLLECTION}/granules"

YEARS = range(2013, 2026)          # Daymet record currently ends 2025-12-31
DAYMET_VARS = ["prcp", "tmax", "tmin"]

# Daymet North America Lambert Conformal Conic grid definition
DAYMET_CRS = CRS.from_proj4(
    "+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 "
    "+x_0=0 +y_0=0 +a=6378137 +rf=298.257223563 +units=m +no_defs"
)
X0, DX, NX = -4560250.0, 1000.0, 7814   # x coordinate origin / spacing / size
Y0, DY, NY = 4984000.0, -1000.0, 8075


# HDF5/netCDF-4 dimension-scale attributes are created internally by the library, so
# writing them back explicitly fails with "NetCDF: String match to name in use". The
# PNWNAmet source files carry them (plus a stale -3.4e+38 _FillValue) into anything
# derived from them, so they must be stripped before writing.
RESERVED_ATTRS = {"NAME", "CLASS", "_Netcdf4Dimid", "DIMENSION_LIST", "REFERENCE_LIST",
                  "_FillValue", "missing_value"}


def sanitize(ds):
    """Drop reserved HDF5 attrs and stale encoding inherited from the source files."""
    for var in ds.variables.values():
        for k in list(var.attrs):
            if k in RESERVED_ATTRS:
                del var.attrs[k]
        var.encoding = {}
    return ds


def target_grid():
    """PNWNAmet lat/lon cell centres and edges (0.0625 deg)."""
    ds = xr.open_dataset(os.path.join(DATA, "PNWNAmet_pr.nc.nc"))
    lat = ds.lat.values      # descending
    lon = ds.lon.values      # ascending
    ds.close()
    h = 0.0625 / 2.0
    lat_asc = lat[::-1]
    lat_edges = np.append(lat_asc - h, lat_asc[-1] + h)
    lon_edges = np.append(lon - h, lon[-1] + h)
    return lat, lon, lat_edges, lon_edges


def subset_window(lat_edges, lon_edges, margin_deg=0.15):
    """Daymet x/y index window covering the target grid, with a margin."""
    tr = Transformer.from_crs("EPSG:4326", DAYMET_CRS, always_xy=True)
    lons = np.linspace(lon_edges[0] - margin_deg, lon_edges[-1] + margin_deg, 80)
    lats = np.linspace(lat_edges[0] - margin_deg, lat_edges[-1] + margin_deg, 80)
    LO, LA = np.meshgrid(lons, lats)
    X, Y = tr.transform(LO.ravel(), LA.ravel())

    xv = X0 + DX * np.arange(NX)
    yv = Y0 + DY * np.arange(NY)
    ix = np.where((xv >= X.min()) & (xv <= X.max()))[0]
    iy = np.where((yv >= Y.min()) & (yv <= Y.max()))[0]
    if not len(ix) or not len(iy):
        raise RuntimeError("target grid falls outside the Daymet North America domain")
    return int(iy[0]), int(iy[-1]), int(ix[0]), int(ix[-1])


def fetch(var, year, win):
    """Download one Daymet variable-year spatial subset via DAP4. Cached on disk."""
    y0, y1, x0, x1 = win
    os.makedirs(CACHE, exist_ok=True)
    raw = os.path.join(CACHE, f"daymet_{var}_{year}_raw.nc4")
    if os.path.exists(raw) and os.path.getsize(raw) > 1_000_000:
        return raw

    url = f"{BASE}/Daymet_Daily_V4R1.daymet_v4_daily_na_{var}_{year}.nc.dap.nc4"
    ce = (
        f"/{var}[0:364][{y0}:{y1}][{x0}:{x1}];"
        f"/lat[{y0}:{y1}][{x0}:{x1}];"
        f"/lon[{y0}:{y1}][{x0}:{x1}];"
        f"/time[0:364]"
    )
    for attempt in range(4):
        try:
            t = time.time()
            r = requests.Session().get(url, params={"dap4.ce": ce}, timeout=1200)
            if r.status_code == 401:
                raise SystemExit(
                    "\nEarthdata authentication failed (HTTP 401).\n"
                    "Add your Earthdata Login to ~/.netrc:\n\n"
                    "    machine urs.earthdata.nasa.gov\n"
                    "        login YOUR_USERNAME\n"
                    "        password YOUR_PASSWORD\n\n"
                    "then: chmod 600 ~/.netrc\n"
                    "Register free at https://urs.earthdata.nasa.gov/users/new\n"
                )
            r.raise_for_status()
            tmp = raw + ".part"
            with open(tmp, "wb") as fh:
                fh.write(r.content)
            os.replace(tmp, raw)
            print(f"  {var} {year}: {len(r.content)/1e6:.1f} MB in {time.time()-t:.0f}s")
            return raw
        except SystemExit:
            raise
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"  {var} {year}: {type(exc).__name__} — retry {attempt+1}/3")
            time.sleep(5 * (attempt + 1))


def build_regridder(sample_nc, lat_edges, lon_edges, nlat, nlon):
    """Sparse matrix mapping Daymet 1 km pixels -> PNWNAmet cells (area mean)."""
    d = xr.open_dataset(sample_nc)
    dlat = d.lat.values.ravel()
    dlon = d.lon.values.ravel()
    d.close()

    iy = np.digitize(dlat, lat_edges) - 1     # index into ASCENDING lat
    ix = np.digitize(dlon, lon_edges) - 1
    ok = (iy >= 0) & (iy < nlat) & (ix >= 0) & (ix < nlon)

    rows = (iy[ok] * nlon + ix[ok]).astype(np.int64)
    cols = np.nonzero(ok)[0]
    M = sparse.csr_matrix(
        (np.ones(rows.size, np.float32), (rows, cols)),
        shape=(nlat * nlon, dlat.size),
    )
    print(f"  regridder: {rows.size} Daymet pixels -> {nlat*nlon} cells "
          f"(~{rows.size/(nlat*nlon):.0f} px/cell)")
    return M


def regrid(nc_path, var, M, nlat, nlon):
    """Average Daymet 1 km pixels onto the PNWNAmet grid, ignoring ocean NaNs."""
    d = xr.open_dataset(nc_path)
    arr = d[var].values.astype(np.float32)        # (time, y, x)
    tvals = d.time.values
    d.close()

    nt = arr.shape[0]
    flat = arr.reshape(nt, -1).T                  # (npix, time)
    finite = np.isfinite(flat)
    sums = M @ np.where(finite, flat, 0.0)        # (ncell, time)
    counts = M @ finite.astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(counts > 0, sums / counts, np.nan)

    # back to (time, lat, lon); lat rows are ascending -> flip to PNWNAmet order
    out = mean.T.reshape(nt, nlat, nlon)[:, ::-1, :]
    return out.astype(np.float32), tvals


def main():
    lat, lon, lat_edges, lon_edges = target_grid()
    nlat, nlon = lat.size, lon.size
    win = subset_window(lat_edges, lon_edges)
    print(f"Daymet window: y[{win[0]}:{win[1]}] x[{win[2]}:{win[3]}]")

    print("\nDownloading Daymet subsets (cached in cache/daymet/) ...")
    paths = {}
    for year in YEARS:
        for var in DAYMET_VARS:
            paths[(var, year)] = fetch(var, year, win)

    M = build_regridder(paths[(DAYMET_VARS[0], YEARS[0])], lat_edges, lon_edges, nlat, nlon)

    print("\nRegridding to the PNWNAmet grid ...")
    per_year = []
    for year in YEARS:
        fields, tvals = {}, None
        for var in DAYMET_VARS:
            fields[var], tv = regrid(paths[(var, year)], var, M, nlat, nlon)
            tvals = tv if tvals is None else tvals
        tavg = (fields["tmax"] + fields["tmin"]) / 2.0
        per_year.append(
            xr.Dataset(
                {
                    "tavg": (("time", "lat", "lon"), tavg),
                    "pr": (("time", "lat", "lon"), fields["prcp"]),
                },
                coords={"time": tvals, "lat": lat, "lon": lon},
            )
        )
        print(f"  {year} done")

    daymet = xr.concat(per_year, dim="time").sortby("time")
    # Daymet timestamps are at 12:00; snap to midnight to match PNWNAmet
    daymet["time"] = daymet.time.dt.floor("D")
    daymet = daymet.sel(time=slice("2013-01-01", None))

    print("\nLoading PNWNAmet 1960-2012 ...")
    pr = xr.open_dataset(os.path.join(DATA, "PNWNAmet_pr.nc.nc")).pr
    tmin = xr.open_dataset(os.path.join(DATA, "PNWNAmet_tasmin.nc.nc")).tasmin
    tmax = xr.open_dataset(os.path.join(DATA, "PNWNAmet_tasmax.nc.nc")).tasmax
    sl = slice("1960-01-01", "2012-12-31")
    pr, tmin, tmax = pr.sel(time=sl), tmin.sel(time=sl), tmax.sel(time=sl)
    tmax = tmax.reindex(time=tmin.time)           # tasmax starts in 1945
    hist = xr.Dataset({"tavg": (tmin + tmax) / 2.0, "pr": pr})

    print("Merging ...")
    merged = sanitize(xr.concat([hist, daymet], dim="time").sortby("time"))

    src = np.where(merged.time.values < np.datetime64("2013-01-01"), 0, 1).astype(np.int8)
    merged = merged.assign_coords(data_source=("time", src))

    merged.tavg.attrs = {
        "standard_name": "air_temperature",
        "long_name": "Daily mean surface (2m) air temperature",
        "units": "degC",
        "cell_methods": "time: mean",
        "comment": "(tasmin+tasmax)/2 from PNWNAmet before 2013; (tmin+tmax)/2 from Daymet v4 R1 from 2013",
    }
    merged.pr.attrs = {
        "standard_name": "precipitation_flux",
        "long_name": "Total precipitation rate",
        "units": "mm/day",
        "cell_methods": "time: sum",
        "comment": "PNWNAmet pr before 2013; Daymet v4 R1 prcp from 2013",
    }
    merged.data_source.attrs = {
        "long_name": "source dataset for this timestep",
        "flag_values": np.array([0, 1], np.int8),
        "flag_meanings": "PNWNAmet Daymet_v4_R1",
    }
    merged.attrs = {
        "title": "Merged daily tavg and precipitation, PNWNAmet + Daymet v4 R1",
        "summary": (
            "PNWNAmet (1960-01-01 to 2012-12-31) spliced with Daymet v4 R1 "
            "(2013-01-01 to 2025-12-31) regridded from 1 km to the PNWNAmet "
            "0.0625-degree grid by area mean."
        ),
        "grid": "0.0625 degree regular lat/lon (PNWNAmet native)",
        "caveats": (
            "1) The two products have different biases; expect a discontinuity at 2013-01-01. "
            "2) Daymet is land-only, so ocean cells are NaN from 2013 onward while PNWNAmet "
            "provides values there. "
            "3) Daymet uses a 365-day calendar: 31 December is absent in leap years "
            "(2016, 2020, 2024)."
        ),
        "source_PNWNAmet": "https://www.pacificclimate.org/data/daily-gridded-meteorological-datasets",
        "source_Daymet": "https://doi.org/10.3334/ORNLDAAC/2129",
        "Conventions": "CF-1.8",
    }

    enc = {v: {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": np.nan}
           for v in ["tavg", "pr"]}
    enc["time"] = {"units": "days since 1960-01-01", "calendar": "standard",
                   "dtype": "float64"}
    merged.to_netcdf(OUT, encoding=enc)
    print(f"\nWrote {OUT}  ({os.path.getsize(OUT)/1e6:.1f} MB)")
    print(merged)


if __name__ == "__main__":
    main()
