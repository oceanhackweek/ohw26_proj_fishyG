#!/usr/bin/env python
"""
Pull the precipitation variable out of merged_tavg_prcp_1960_2025_monthly.nc
into its own standalone .nc file.

Run AFTER build_monthly_weather.py.

Output: ../../../data/Global_weather/monthly_prcp_1960_2025.nc
"""
import os

import numpy as np
import xarray as xr

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "..", "data", "Global_weather")
MONTHLY = os.path.join(DATA, "merged_tavg_prcp_1960_2025_monthly.nc")
OUT = os.path.join(DATA, "monthly_prcp_1960_2025.nc")


def main():
    if not os.path.exists(MONTHLY):
        raise SystemExit(f"{MONTHLY} not found - run build_monthly_weather.py first")

    ds = xr.open_dataset(MONTHLY).load()

    out = xr.Dataset(
        {
            "pr": ds.pr,
            "n_days": ds.n_days,
            "ocean_filled": ds.ocean_filled,
            "land_corrected": ds.land_corrected,
        },
        coords={"lat": ds.lat, "lon": ds.lon, "time": ds.time},
    )
    out.pr.attrs = ds.pr.attrs
    out.n_days.attrs = ds.n_days.attrs
    out.ocean_filled.attrs = ds.ocean_filled.attrs
    out.land_corrected.attrs = ds.land_corrected.attrs

    out.attrs = dict(ds.attrs)
    out.attrs["title"] = "Monthly total precipitation, PNWNAmet + Daymet v4 R1"
    out.attrs["summary"] = (
        f"Precipitation extracted from {os.path.basename(MONTHLY)}. "
        "pr is the monthly total (sum of daily mm/day values -> mm/month)."
    )
    out.attrs["source_script"] = (
        f"extract_monthly_prcp.py, extracted from {os.path.basename(MONTHLY)}"
    )

    enc = {"pr": {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": np.nan}}
    enc["n_days"] = {"zlib": True, "complevel": 4, "dtype": "int16"}
    for v in ("ocean_filled", "land_corrected"):
        enc[v] = {"zlib": True, "complevel": 4, "dtype": "int8"}
    enc["time"] = {"units": "days since 1960-01-01", "calendar": "standard", "dtype": "float64"}

    out.to_netcdf(OUT, encoding=enc)
    print(f"Wrote {OUT} ({os.path.getsize(OUT)/1e6:.1f} MB)")
    print(out)


if __name__ == "__main__":
    main()
