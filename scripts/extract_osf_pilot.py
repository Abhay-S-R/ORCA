"""
Re-extract INCOIS OSF (WW3 wave + HYCOM ocean) forecasts at the ORCA pilot ports.

Replaces the original pilot CSVs, which used a plain nearest-neighbour lookup and
therefore returned NaN wherever a port's true coordinates fell in a land cell.
Every row now carries the grid point actually sampled and the snap distance, so the
Weather Intelligence and Ocean Analytics agents can cite a real provenance chain.

Usage:  python scripts/extract_osf_pilot.py
"""

import glob
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from orca_grid_utils import build_wet_mask, snap_to_wet_cell

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _newest(subdir, pattern):
    """Newest matching grid under data/incois_osf_pfz/<subdir>/.

    Globbed rather than pinned to a run date: `scripts/refresh_osf_forecasts.py`
    writes a new file every day, and a hardcoded name silently re-extracts the
    expired run.
    """
    hits = sorted(glob.glob(os.path.join(ROOT, "data/incois_osf_pfz", subdir, pattern)))
    if not hits:
        raise SystemExit("no %s in %s — run scripts/refresh_osf_forecasts.py" % (pattern, subdir))
    return hits[-1]


WW3_NC = _newest("osf_ww3", "rsmc_combined_ww3_*.nc")
HYCOM_NC = _newest("osf_hycom", "RSMC_hycom_*.nc")
# SST lives in its own product since INCOIS stopped bundling TEMP/SALN/MLD/SSH
# into the daily HYCOM file. Optional: without it the temperature column is
# empty, which is the honest result, not a reason to fail the run.
SST_NC = next(iter(sorted(glob.glob(os.path.join(ROOT, "data/incois_osf_pfz/osf_hycom/SST_NIO_*.nc")))[-1:]), None)

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

# Open-water sample points, one per pilot port, sitting far enough offshore that
# the model cell is genuinely marine. These — not the harbour points above — are
# what `analytics_loaders.load_osf_point_forecasts()` serves to Ocean Analytics
# and to the voyage planner's wave fallback.
OFFSHORE_POINTS = {
    "Thoothukudi Offshore":   (8.75, 78.30),
    "Pamban / Palk Strait":   (9.25, 79.40),
    "Kanyakumari Offshore":   (7.95, 77.60),
    "Chennai Offshore":       (13.08, 80.45),
    "Kochi Offshore":         (9.90, 76.05),
    "Mumbai Offshore":        (18.95, 72.65),
    "Visakhapatnam Offshore": (17.65, 83.45),
    "Mangalore Offshore":     (12.85, 74.65),
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
    return [epoch + timedelta(**{scale: float(v)}) - _calendar_shift(time_var, epoch)
            for v in raw]


def _calendar_shift(time_var, epoch):
    """The 2-day gap between CF's 'standard' calendar and Python's proleptic one.

    WW3 stamps its axis 'hours since 0001-01-01' with calendar 'standard', which
    is Julian that far back; `datetime(1, 1, 1)` is proleptic Gregorian and sits
    two days later, so decoding naively dates every forecast step two days into
    the future. Silent and plausible-looking — the run still "covers a week" —
    which is exactly why it survived: it just answers with the wrong step.
    """
    standard = time_var.attrs.get("calendar", "standard").lower() in ("standard", "gregorian")
    return timedelta(days=2) if standard and epoch.year == 1 else timedelta(0)


def _r(value, digits):
    """Round, mapping NaN to None so it serialises as an empty CSV field."""
    v = float(value)
    return None if np.isnan(v) else round(v, digits)


def _snap_all(lats, lons, wet, label, points=None):
    """Resolve every requested point to a wet cell, printing an audit line for each."""
    resolved = {}
    for port, (tlat, tlon) in (points or PILOT_PORTS).items():
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


def extract_ww3(points=None):
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

    resolved = _snap_all(lats, lons, wet, "WW3", points)
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


def extract_hycom(points=None):
    print("\n" + "=" * 72)
    print("HYCOM ocean model -> pilot ports")
    print("=" * 72)
    ds = xr.open_dataset(HYCOM_NC, engine="scipy", decode_times=False)
    lats = ds["LAT"].values
    lons = ds["LON"].values
    times = decode_time_axis(ds["TIME"])

    # UVEL, not TEMP, is the wet/dry discriminator now: the current subset is the
    # one variable guaranteed to be in every published run.
    wet = build_wet_mask(ds["UVEL"].isel(TIME=0, DEPTH=0).values)
    print("grid %dx%d @ %.3f deg | wet cells %s/%s | %d steps (%s .. %s UTC)"
          % (len(lats), len(lons), abs(lats[1] - lats[0]),
             format(int(wet.sum()), ","), format(int(wet.size), ","), len(times),
             times[0].strftime("%Y-%m-%d %H:%M"), times[-1].strftime("%Y-%m-%d %H:%M")))

    sst_ds = None
    if SST_NC:
        sst_ds = xr.open_dataset(SST_NC, engine="scipy", decode_times=False)
        if not (np.allclose(sst_ds["LAT"].values, lats) and np.allclose(sst_ds["LON"].values, lons)):
            print("  SST grid does not match the current grid — temperature left empty")
            sst_ds.close()
            sst_ds = None
    else:
        print("  no SST_NIO_*.nc on disk — temperature left empty")

    def series(dataset, name, iy, ix, depth_axis):
        """A per-cell time series, or NaNs when the run does not carry the variable.

        SALN / MLD / SSH came with the retired RSMC_hycom bundle and have no
        current public equivalent here. An empty column says so; reusing the
        August values under a September timestamp would not."""
        if dataset is None or name not in dataset.variables:
            return np.full(len(times), np.nan)
        arr = dataset[name].values
        return arr[:, 0, iy, ix] if depth_axis else arr[:, iy, ix]

    resolved = _snap_all(lats, lons, wet, "HYCOM", points)
    rows = []
    for port, (tlat, tlon, iy, ix, glat, glon, dist) in resolved.items():
        sst = series(sst_ds, "SST", iy, ix, depth_axis=True)
        saln = series(ds, "SALN", iy, ix, depth_axis=True)
        u = ds["UVEL"].values[:, 0, iy, ix]
        v = ds["VVEL"].values[:, 0, iy, ix]
        mld = series(ds, "MLD", iy, ix, depth_axis=False)
        ssh = series(ds, "SSH", iy, ix, depth_axis=False)
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
    if sst_ds is not None:
        sst_ds.close()
    return pd.DataFrame(rows)


GEOJSON_RENAME = {"mean_wave_dir_deg": "mean_wave_direction_deg"}


def write_latest_points(df, path):
    """The single forecast step nearest *now*, one feature per offshore point.

    Regenerating this matters more than the CSVs: it is the file the agents read
    at query time, so a fresh grid that never reaches it changes nothing.
    """
    # Deliberately dropped back to naive after being read in UTC: the `_when`
    # column below is naive (the "Z" is stripped before parsing), and subtracting
    # an aware datetime from a naive one raises. `utcnow()` said the same thing
    # without recording which clock it meant.
    now = datetime.now(UTC).replace(tzinfo=None)
    df = df.copy()
    df["_when"] = pd.to_datetime(df["time"].str.rstrip("Z"))
    step = min(df["_when"].unique(), key=lambda t: abs(pd.Timestamp(t).to_pydatetime() - now))
    features = []
    for _, r in df[df["_when"] == step].iterrows():
        props = {GEOJSON_RENAME.get(k, k): (None if pd.isna(v) else v)
                 for k, v in r.items()
                 if k not in ("city", "time", "time_index", "snap_distance_km", "_when")}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["grid_lon"], r["grid_lat"]]},
            "properties": {"location": r["city"],
                           "base_port": r["city"].split(" Offshore")[0].split(" /")[0],
                           "forecast_time": pd.Timestamp(step).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           **props},
        })
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, indent=1)
    print("  -> wrote %s (%d points @ %s)" % (path, len(features), pd.Timestamp(step)))


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

    for product, extract, subdir in (("ww3", extract_ww3, "osf_ww3"),
                                     ("hycom", extract_hycom, "osf_hycom")):
        off = extract(OFFSHORE_POINTS)
        base = os.path.join(ROOT, "data/incois_osf_pfz", subdir)
        off.to_csv(os.path.join(base, "%s_offshore_forecasts.csv" % product), index=False)
        write_latest_points(off, os.path.join(base, "%s_latest_points.geojson" % product))

    print("\n" + "=" * 72)
    print("Remaining missing values: WW3 %d, HYCOM %d" % (miss_w, miss_h))
    print("=" * 72)
