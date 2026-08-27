"""Map tavg and precipitation from the merged PNWNAmet+Daymet file on selected dates.

Usage:  python plot_weather_dates.py [YYYY-MM-DD ...]
Default dates: 2025-07-01, 2025-08-01, 2025-09-01
"""
import sys
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NC = REPO / "data" / "global weather" / "merged_tavg_prcp_1960_2025.nc"
OUT = Path(__file__).resolve().parent / "figures"

DATES = sys.argv[1:] or ["2025-07-01", "2025-08-01", "2025-09-01"]

# cell-centre coords -> cell edges, so pcolormesh draws the grid honestly
def edges(c):
    c = np.asarray(c, float)
    h = np.diff(c) / 2
    return np.concatenate([[c[0] - h[0]], c[:-1] + h, [c[-1] + h[-1]]])


ds = xr.open_dataset(NC)
frames = [ds.sel(time=d) for d in DATES]
lon_e, lat_e = edges(ds.lon), edges(ds.lat)

# one shared scale per variable so the three dates are directly comparable
rows = [
    dict(var="tavg", cmap="YlOrRd", label="Daily mean air temperature (°C)",
         stat=lambda a: f"mean {np.nanmean(a):.1f} °C"),
    dict(var="pr", cmap="Blues", label="Precipitation (mm/day)",
         stat=lambda a: f"area mean {np.nanmean(a):.2f} mm"),
]
for r in rows:
    stack = np.concatenate([f[r["var"]].values.ravel() for f in frames])
    r["vmin"], r["vmax"] = np.nanmin(stack), np.nanmax(stack)
    if r["var"] == "pr":                       # precip floors at zero
        r["vmin"] = 0.0
        r["vmax"] = max(r["vmax"], 1e-6)

proj = ccrs.PlateCarree()
fig, axes = plt.subplots(
    len(rows), len(DATES), figsize=(3.5 * len(DATES) + 1.6, 2.9 * len(rows)),
    subplot_kw={"projection": proj}, constrained_layout=True,
)
axes = np.atleast_2d(axes)

for i, r in enumerate(rows):
    for j, (d, f) in enumerate(zip(DATES, frames)):
        ax = axes[i, j]
        arr = f[r["var"]].values
        m = ax.pcolormesh(lon_e, lat_e, arr, cmap=r["cmap"],
                          vmin=r["vmin"], vmax=r["vmax"],
                          shading="flat", transform=proj)
        ax.add_feature(
            cfeature.NaturalEarthFeature("physical", "coastline", "10m"),
            edgecolor="0.2", facecolor="none", linewidth=0.7)
        ax.set_extent([lon_e[0], lon_e[-1], lat_e[0], lat_e[-1]], crs=proj)
        gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="0.8", alpha=0.6)
        gl.top_labels = gl.right_labels = False
        gl.left_labels = (j == 0)
        gl.bottom_labels = (i == len(rows) - 1)
        gl.xlabel_style = gl.ylabel_style = {"size": 8, "color": "0.35"}
        ax.set_title(f"{d}\n{r['stat'](arr)}", fontsize=10)
    cb = fig.colorbar(m, ax=axes[i, :].tolist(), shrink=0.9, aspect=18, pad=0.02)
    cb.set_label(r["label"], fontsize=9)
    cb.ax.tick_params(labelsize=8)

fig.suptitle("Merged PNWNAmet + Daymet v4 R1 daily fields, Salish Sea grid",
             fontsize=13)

OUT.mkdir(exist_ok=True)
png = OUT / ("weather_" + "_".join(d.replace("-", "") for d in DATES) + ".png")
fig.savefig(png, dpi=180, bbox_inches="tight")
print("wrote", png)

for d, f in zip(DATES, frames):
    print(f"{d}  tavg {float(f.tavg.min()):5.1f} to {float(f.tavg.max()):5.1f} °C"
          f"   pr {float(f.pr.min()):.2f} to {float(f.pr.max()):.2f} mm/day"
          f"   source={'Daymet' if int(f.data_source)==1 else 'PNWNAmet'}")
