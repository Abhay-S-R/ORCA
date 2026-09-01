"""
Re-extract INCOIS OSF (WW3 wave + HYCOM ocean) forecasts at the ORCA pilot ports.

Replaces the original pilot CSVs, which used a plain nearest-neighbour lookup and
therefore returned NaN wherever a port's true coordinates fell in a land cell.
Every row now carries the grid point actually sampled and the snap distance, so the
Weather Intelligence and Ocean Analytics agents can cite a real provenance chain.

Usage:  python scripts/extract_osf_pilot.py
"""

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from orca_grid_utils import build_wet_mask, snap_to_wet_cell  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WW3_NC = os.path.join(ROOT, "data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc")
HYCOM_NC = os.path.join(ROOT, "data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc")

# True port coordinates. These stay as the *target*; the snap result is recorded
# separately so nothing pretends the model resolved the harbour itself.
PILOT_PORTS = {
    "Thoothukudi":   (8.80, 78.14),
    "Pamban":        (9.28, 79.26),
    "Kanyakumari":   (8.08, 77.55),
    "Chennai":       (13.08, 80.27),
    "Kochi":         (9.93, 76.26),
    "Mumbai":        (19.08, 72.88),
    "Visakhapatnam": (17.69, 83.29),
}

# Search ceiling. 1.0 deg is ~111 km; a snap that large means the port is not
# resolvable on this grid at all and the row is dropped rather than fabricated.
MAX_SNAP_DEG = 1.0
# Beyond this the value is still real but no longer representative of local
# conditions, so it is flagged rather than silently used.
SNAP_WARN_KM = 25.0


def decode_time_axis(time_var):
    """Decode a CF 'units since epoch' axis without requiring cftime."""
    units = time_var.attrs.get("units", "")
    raw = np.asarray(time_var.values, dtype="float64")
    interval, _, epoch_str = units.partition(" since ")
    epoch_str = epoch_str.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            epoch = datetime.strptime(epoch_str[:19], fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError("Unparseable time epoch: " + repr(units))

    scale = interval.strip()
    if scale not in ("hours", "days", "minutes", "seconds"):
        raise ValueError("Unsupported time interval: " + repr(scale))
    return [epoch + timedelta(**{scale: float(v)}) for v in raw]


def _r(value, digits):
    """Round, mapping NaN to None so it serialises as an empty CSV field."""
    v = float(value)
    return None if np.isnan(v) else round(v, digits)


def _snap_all(lats, lons, wet, label):
    """Resolve every pilot port to a wet cell, printing an audit line for each."""
    resolved = {}
    for port, (tlat, tlon) in PILOT_PORTS.items():
        snap = snap_to_wet_cell(lats, lons, wet, tlat, tlon, MAX_SNAP_DEG)
        if snap is None:
            print("  %-14s SKIPPED - no wet cell within %.1f deg" % (port, MAX_SNAP_DEG))
            continue
        iy, ix, glat, glon, dist = snap
        flag = "  <-- exceeds representativeness threshold" if dist > SNAP_WARN_KM else ""
        print("  %-14s (%6.2f,%6.2f) -> grid (%6.2f,%6.2f)  snap %5.1f km%s"
              % (port, tlat, tlon, glat, glon, dist, flag))
        resolved[port] = (tlat, tlon, iy, ix, glat, glon, dist)
    return resolved


def extract_ww3():
    print("\n" + "=" * 72)
    print("WW3 wave model -> pilot ports")
    print("=" * 72)
    ds = xr.open_dataset(WW3_NC, engine="scipy", decode_times=False)
    lats = ds["IOYAXIS"].values
    lons = ds["IOXAXIS"].values
    times = decode_time_axis(ds["TIME"])

    # HS is the definitive wet/dry discriminator for a wave model: the solver only
    # produces a wave height where there is water.
    wet = build_wet_mask(ds["HS"].isel(TIME=0).values)
    print("grid %dx%d @ %.2f deg | wet cells %s/%s | %d steps (%s .. %s UTC)"
          % (len(lats), len(lons), abs(lats[1] - lats[0]),
             format(int(wet.sum()), ","), format(int(wet.size), ","), len(times),
             times[0].strftime("%Y-%m-%d %H:%M"), times[-1].strftime("%Y-%m-%d %H:%M")))

    resolved = _snap_all(lats, lons, wet, "WW3")
    rows = []
    for port, (tlat, tlon, iy, ix, glat, glon, dist) in resolved.items():
        hs = ds["HS"].values[:, iy, ix]
        mwd = ds["MWD"].values[:, iy, ix]
        t02 = ds["T02"].values[:, iy, ix]
        pwp = ds["PWP"].values[:, iy, ix]
        uw = ds["UWND"].values[:, iy, ix]
        vw = ds["VWND"].values[:, iy, ix]
        wind_speed = np.sqrt(uw ** 2 + vw ** 2)
        # Meteorological convention: the direction the wind blows *from*.
        wind_dir = np.degrees(np.arctan2(-uw, -vw)) % 360.0

        for k, ts in enumerate(times):
            rows.append({
                "city": port,
                "target_lat": tlat, "target_lon": tlon,
                "grid_lat": round(glat, 4), "grid_lon": round(glon, 4),
                "snap_distance_km": round(dist, 2),
                "time_index": k,
                "time": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "significant_wave_height_m": _r(hs[k], 3),
                "mean_wave_dir_deg": _r(mwd[k], 1),
                "mean_wave_period_s": _r(t02[k], 2),
                "peak_wave_period_s": _r(pwp[k], 2),
                "wind_u_ms": _r(uw[k], 3),
                "wind_v_ms": _r(vw[k], 3),
                "wind_speed_ms": _r(wind_speed[k], 3),
                "wind_dir_from_deg": _r(wind_dir[k], 1),
            })
    ds.close()
    return pd.DataFrame(rows)


def extract_hycom():
    print("\n" + "=" * 72)
    print("HYCOM ocean model -> pilot ports")
    print("=" * 72)
    ds = xr.open_dataset(HYCOM_NC, engine="scipy", decode_times=False)
    lats = ds["LAT"].values
    lons = ds["LON"].values
    times = decode_time_axis(ds["TIME"])

    wet = build_wet_mask(ds["TEMP"].isel(TIME=0, DEPTH=0).values)
    print("grid %dx%d @ %.3f deg | wet cells %s/%s | %d steps (%s .. %s UTC)"
          % (len(lats), len(lons), abs(lats[1] - lats[0]),
             format(int(wet.sum()), ","), format(int(wet.size), ","), len(times),
             times[0].strftime("%Y-%m-%d %H:%M"), times[-1].strftime("%Y-%m-%d %H:%M")))

    resolved = _snap_all(lats, lons, wet, "HYCOM")
    rows = []
    for port, (tlat, tlon, iy, ix, glat, glon, dist) in resolved.items():
        sst = ds["TEMP"].values[:, 0, iy, ix]
        saln = ds["SALN"].values[:, 0, iy, ix]
        u = ds["UVEL"].values[:, 0, iy, ix]
        v = ds["VVEL"].values[:, 0, iy, ix]
        mld = ds["MLD"].values[:, iy, ix]
        ssh = ds["SSH"].values[:, iy, ix]
        speed = np.sqrt(u ** 2 + v ** 2)
        # Oceanographic convention: the direction the current flows *towards*.
        cur_dir = np.degrees(np.arctan2(u, v)) % 360.0

        for k, ts in enumerate(times):
            rows.append({
                "city": port,
                "target_lat": tlat, "target_lon": tlon,
                "grid_lat": round(glat, 4), "grid_lon": round(glon, 4),
                "snap_distance_km": round(dist, 2),
                "time_index": k,
                "time": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sea_surface_temp_c": _r(sst[k], 3),
                "salinity_psu": _r(saln[k], 3),
                "u_current_ms": _r(u[k], 4),
                "v_current_ms": _r(v[k], 4),
                "ocean_current_speed_ms": _r(speed[k], 4),
                "current_dir_to_deg": _r(cur_dir[k], 1),
                "mixed_layer_depth_m": _r(mld[k], 2),
                "sea_surface_height_m": _r(ssh[k], 4),
            })
    ds.close()
    return pd.DataFrame(rows)


def report(df, name, key_col):
    print("\n%s coverage:" % name)
    total_missing = 0
    for city, grp in df.groupby("city", sort=False):
        good = int(grp[key_col].notna().sum())
        total_missing += len(grp) - good
        mark = "OK " if good == len(grp) else "GAP"
        print("  [%s] %-14s %3d/%3d  snap %5.1f km"
              % (mark, city, good, len(grp), grp["snap_distance_km"].iloc[0]))
    return total_missing


if __name__ == "__main__":
    ww3 = extract_ww3()
    miss_w = report(ww3, "WW3", "significant_wave_height_m")
    out_w = os.path.join(ROOT, "data/incois_osf_pfz/osf_ww3/ww3_pilot_forecasts.csv")
    ww3.to_csv(out_w, index=False)
    print("  -> wrote %s (%d rows)" % (out_w, len(ww3)))

    hy = extract_hycom()
    miss_h = report(hy, "HYCOM", "sea_surface_temp_c")
    out_h = os.path.join(ROOT, "data/incois_osf_pfz/osf_hycom/hycom_pilot_forecasts.csv")
    hy.to_csv(out_h, index=False)
    print("  -> wrote %s (%d rows)" % (out_h, len(hy)))

    print("\n" + "=" * 72)
    print("Remaining missing values: WW3 %d, HYCOM %d" % (miss_w, miss_h))
    print("=" * 72)
