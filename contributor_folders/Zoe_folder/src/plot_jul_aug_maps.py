#!/usr/bin/env python
"""
Map monthly max temperature and total precipitation for July and August,
1970 / 1990 / 2005 / 2010, over the PNWNAmet+Daymet grid (Little Qualicum
River region).

Reads the pre-built monthly aggregate (see Old processing/build_monthly_weather.py)
rather than resampling the daily file, since it already carries the tavg
monthly-max / pr monthly-total definitions used elsewhere in this project.

Run:
    python src/plot_jul_aug_maps.py
Output:
    figures/jul_aug_temp_precip_maps.png
"""
from pathlib import Path

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from matplotlib.colors import LinearSegmentedColormap, Normalize

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ZOE_ROOT = HERE.parent

MONTHLY_NC = REPO_ROOT / "data" / "Global_weather" / "merged_tavg_prcp_1960_2025_monthly.nc"
OUT_PNG = ZOE_ROOT / "figures" / "jul_aug_temp_precip_maps.png"

YEARS = [1970, 1990, 2005, 2010]
MONTHS = [7, 8]
MONTH_NAMES = {7: "Jul", 8: "Aug"}

# Sequential single-hue ramps (dataviz skill palette: blue for precip, the
# next categorical slot's orange for the second concurrent sequential context).
TEMP_CMAP = LinearSegmentedColormap.from_list("temp_seq", ["#fdf1ea", "#eb6834", "#7a2e0f"])
PRECIP_CMAP = LinearSegmentedColormap.from_list(
    "precip_seq", ["#eaf2fc", "#3987e5", "#0d366b"]
)


def main():
    ds = xr.open_dataset(MONTHLY_NC)
    sub = ds.sel(time=ds.time.dt.year.isin(YEARS) & ds.time.dt.month.isin(MONTHS))
    sub = sub.assign_coords(
        year=("time", sub.time.dt.year.values), month=("time", sub.time.dt.month.values)
    )

    tavg_norm = Normalize(vmin=float(sub.tavg.min()), vmax=float(sub.tavg.max()))
    pr_norm = Normalize(vmin=0.0, vmax=float(sub.pr.max()))

    fig, axes = plt.subplots(
        len(YEARS),
        4,
        figsize=(14, 3.1 * len(YEARS)),
        subplot_kw={"projection": ccrs.PlateCarree()},
    )
    col_titles = ["Jul tavg (°C)", "Aug tavg (°C)", "Jul precip (mm)", "Aug precip (mm)"]

    for i, year in enumerate(YEARS):
        for j, (month, var, cmap, norm) in enumerate(
            [
                (7, "tavg", TEMP_CMAP, tavg_norm),
                (8, "tavg", TEMP_CMAP, tavg_norm),
                (7, "pr", PRECIP_CMAP, pr_norm),
                (8, "pr", PRECIP_CMAP, pr_norm),
            ]
        ):
            ax = axes[i, j]
            field = sub[var].sel(time=(sub["year"] == year) & (sub["month"] == month))
            field = field.squeeze("time", drop=True)
            mesh = ax.pcolormesh(
                sub.lon,
                sub.lat,
                field,
                cmap=cmap,
                norm=norm,
                shading="auto",
                transform=ccrs.PlateCarree(),
            )
            ax.add_feature(cfeature.COASTLINE, linewidth=0.6, edgecolor="#555555")
            ax.add_feature(cfeature.BORDERS, linewidth=0.4, edgecolor="#888888")
            ax.set_extent(
                [float(sub.lon.min()), float(sub.lon.max()), float(sub.lat.min()), float(sub.lat.max())],
                crs=ccrs.PlateCarree(),
            )
            if i == 0:
                ax.set_title(col_titles[j], fontsize=11)
            if j == 0:
                ax.text(
                    -0.28,
                    0.5,
                    str(year),
                    transform=ax.transAxes,
                    fontsize=12,
                    fontweight="bold",
                    va="center",
                    ha="center",
                    rotation=90,
                )
            if i == len(YEARS) - 1 and j in (1, 3):
                cb = fig.colorbar(mesh, ax=axes[:, j - 1 : j + 1].ravel().tolist(), orientation="horizontal",
                                   fraction=0.03, pad=0.06,
                                   label="Temperature (°C)" if j == 1 else "Precipitation (mm)")

    fig.suptitle(
        "July & August monthly max temperature and total precipitation — 1970, 1990, 2005, 2010",
        fontsize=14,
        y=0.995,
    )
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
