#!/usr/bin/env python
"""
Aggregate merged_tavg_prcp_1960_2025.nc (daily) to calendar-month values.

    tavg -> monthly maximum of daily values
    pr   -> monthly total (sum of daily mm/day values -> mm/month)

Static per-cell flags (ocean_filled, land_corrected) are carried through unchanged.
The per-timestep data_source flag (0=PNWNAmet, 1=Daymet) is reduced to the fraction
of days in each month sourced from Daymet, since a single month can straddle the
2013-01-01 splice only in the first affected month.

Run AFTER the daily pipeline (build_merged_weather.py -> fill_ocean_cells.py ->
bias_correct_land.py) is complete.

Output: ../../../data/Global_weather/merged_tavg_prcp_1960_2025_monthly.nc
"""
import os

import numpy as np
import xarray as xr

HERE = os.path.dirname(os.path.abspath(__file__))
DAILY_DATA = os.path.join(HERE, "..", "..", "..", "data", "Global Weather")
OUT_DATA = os.path.join(HERE, "..", "..", "..", "data", "Global_weather")
DAILY = os.path.join(DAILY_DATA, "merged_tavg_prcp_1960_2025.nc")
OUT = os.path.join(OUT_DATA, "merged_tavg_prcp_1960_2025_monthly.nc")


def monthly_from_daily(ds):
    """Resample a daily merged dataset to calendar months."""
    n_days = ds.tavg.resample(time="MS").count(dim="time").astype(np.int16)
    tavg_m = ds.tavg.resample(time="MS").max(dim="time", skipna=True)
    pr_m = ds.pr.resample(time="MS").sum(dim="time", skipna=True, min_count=1)
    src_m = ds.data_source.astype(np.float32).resample(time="MS").mean(dim="time")

    out = xr.Dataset(
        {
            "tavg": tavg_m,
            "pr": pr_m,
            "n_days": n_days,
            "data_source_frac_daymet": src_m,
        },
        coords={"lat": ds.lat, "lon": ds.lon},
    )
    for flag in ("ocean_filled", "land_corrected"):
        if flag in ds:
            out[flag] = ds[flag]
    return out


def main():
    if not os.path.exists(DAILY):
        raise SystemExit(f"{DAILY} not found - run the daily pipeline first")

    ds = xr.open_dataset(DAILY).load()
    monthly = monthly_from_daily(ds)

    monthly.tavg.attrs = {
        "standard_name": "air_temperature",
        "long_name": "Monthly maximum daily surface (2m) air temperature",
        "units": "degC",
        "cell_methods": "time: mean within days time: maximum over days",
        "comment": "maximum of the daily tavg values (each a daily mean) within the month",
    }
    monthly.pr.attrs = {
        "standard_name": "precipitation_amount",
        "long_name": "Total monthly precipitation",
        "units": "mm/month",
        "cell_methods": "time: sum within days time: sum over days",
    }
    monthly.n_days.attrs = {
        "long_name": "number of daily observations aggregated into this month",
        "comment": "should equal the calendar month length; fewer indicates missing days",
    }
    monthly.data_source_frac_daymet.attrs = {
        "long_name": "fraction of days in this month sourced from Daymet v4 R1 (vs PNWNAmet)",
    }

    monthly.attrs = dict(ds.attrs)
    monthly.attrs["title"] = "Monthly max tavg and total precipitation, PNWNAmet + Daymet v4 R1"
    monthly.attrs["summary"] = (
        f"Monthly aggregation of {os.path.basename(DAILY)}: tavg is the monthly maximum of "
        "daily values, pr is the monthly total of daily mm/day values. See n_days for the "
        "number of daily observations behind each month."
    )
    monthly.attrs["source_script"] = (
        "build_monthly_weather.py, aggregating merged_tavg_prcp_1960_2025.nc"
    )

    enc = {v: {"zlib": True, "complevel": 4, "dtype": "float32", "_FillValue": np.nan}
           for v in ["tavg", "pr", "data_source_frac_daymet"]}
    enc["n_days"] = {"zlib": True, "complevel": 4, "dtype": "int16"}
    for v in ("ocean_filled", "land_corrected"):
        if v in monthly:
            enc[v] = {"zlib": True, "complevel": 4, "dtype": "int8"}
    enc["time"] = {"units": "days since 1960-01-01", "calendar": "standard", "dtype": "float64"}

    monthly.to_netcdf(OUT, encoding=enc)
    print(f"Wrote {OUT} ({os.path.getsize(OUT)/1e6:.1f} MB)")
    print(monthly)


if __name__ == "__main__":
    main()
