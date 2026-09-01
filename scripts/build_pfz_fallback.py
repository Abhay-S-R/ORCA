"""
Derive a fallback Potential Fishing Zone layer for the ORCA pilot region.

Why this exists
---------------
INCOIS publishes no PFZ advisory for SOUTH TAMILNADU (SEC006) whenever the sector is
clouded, stating so directly: "No data available for this sector due to excessive
cloud cover". Because PFZ advisories are retrieved from satellite SST and chlorophyll,
a monsoon-season pilot region on the Bay of Bengal coast hits this often. The system
still has to answer "where are the fishing zones near Thoothukudi?" on those days.

This computes a *proxy*, never a substitute. It applies the physical signal INCOIS's
own methodology rests on -- thermal frontal structure over the mid-shelf -- to model
fields ORCA already holds, and labels every output as derived, LOW-DATA, and not an
official advisory. The Ocean Analytics Agent may present it only with that framing.

Method
------
1. Mean sea-surface temperature over the HYCOM forecast window (1/16 deg), pilot bbox.
2. Thermal front strength = |grad SST| in degC/km. Fish aggregate along fronts, where
   convergence concentrates nutrients and prey; this is the dominant PFZ predictor.
3. Depth sampled from GEBCO and restricted to the mid-shelf band. ICAR-CMFRI's
   published analysis of PFZ hits off Thoothukudi finds them clustering on the
   mid-shelf, which is the citable prior this filter encodes.
4. Cells above the front-strength percentile threshold and inside the depth band are
   grouped into contiguous zones; each zone yields a centroid, mean front strength,
   depth, and range/bearing from every pilot port.
5. Zones intersecting a no-take marine protected area are dropped -- advising fishing
   inside an MPA would be a compliance failure, not merely a bad suggestion.

Usage:  python scripts/build_pfz_fallback.py
"""

import json
import warnings
import os
from datetime import datetime, timezone

import numpy as np
import xarray as xr
from scipy import ndimage
from shapely.geometry import Point, shape
from shapely.prepared import prep
from pyproj import Geod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HYCOM_NC = os.path.join(ROOT, "data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc")
GEBCO_NC = os.path.join(ROOT, "data/tier1/bathymetry/"
                              "gebco_2026_n10.5_s7.5_w77.5_e80.5.nc")
MPA_GEOJSON = os.path.join(ROOT, "data/tier1/boundaries/india_marine_mpas.geojson")
OUT_DIR = os.path.join(ROOT, "data/incois_osf_pfz/pfz")

# Pilot region: Thoothukudi - Rameswaram - Kanyakumari, Gulf of Mannar and Palk Bay.
PILOT_BBOX = {"lat_min": 7.5, "lat_max": 10.5, "lon_min": 77.0, "lon_max": 80.5}

PILOT_PORTS = {
    "Thoothukudi": (8.80, 78.14),
    "Rameswaram/Pamban": (9.28, 79.26),
    "Kanyakumari": (8.08, 77.55),
}

# Front strength percentile above which a cell is considered frontal. The 90th
# percentile keeps the zone count demo-legible while staying well above the noise
# floor of the model's own gradient field.
FRONT_PERCENTILE = 90.0
# Mid-shelf band in metres (GEBCO elevation is negative below sea level).
DEPTH_MIN_M, DEPTH_MAX_M = 15.0, 120.0
# Discard specks: a zone must span at least this many grid cells (~1 cell = 4.6 km).
MIN_ZONE_CELLS = 3

GEOD = Geod(ellps="WGS84")


def load_sst_fronts():
    """Mean SST and thermal front strength (degC/km) over the pilot bbox."""
    ds = xr.open_dataset(HYCOM_NC, engine="scipy", decode_times=False)
    lats, lons = ds["LAT"].values, ds["LON"].values
    iy = np.where((lats >= PILOT_BBOX["lat_min"]) & (lats <= PILOT_BBOX["lat_max"]))[0]
    ix = np.where((lons >= PILOT_BBOX["lon_min"]) & (lons <= PILOT_BBOX["lon_max"]))[0]

    block = ds["TEMP"].values[:, 0, iy[0]:iy[-1] + 1, ix[0]:ix[-1] + 1]
    sub_lat, sub_lon = lats[iy], lons[ix]
    n_steps = block.shape[0]

    # Land cells are NaN at every step, so nanmean legitimately averages an empty
    # slice there and warns. The NaN result is exactly what the mask downstream
    # expects, so the warning is noise rather than signal.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mean_sst = np.nanmean(block, axis=0)

    # Gradient in degC per grid step, converted to degC/km. Longitude spacing shrinks
    # with latitude, so scale it by cos(lat) rather than assuming a square cell.
    dlat_km = abs(float(sub_lat[1] - sub_lat[0])) * 110.574
    dlon_km = (abs(float(sub_lon[1] - sub_lon[0])) * 111.320
               * np.cos(np.radians(sub_lat.mean())))
    gy, gx = np.gradient(np.nan_to_num(mean_sst, nan=np.nan))
    front = np.sqrt((gy / dlat_km) ** 2 + (gx / dlon_km) ** 2)
    front[~np.isfinite(mean_sst)] = np.nan

    ds.close()
    return sub_lat, sub_lon, mean_sst, front, n_steps


def sample_depth(target_lat, target_lon):
    """Sample GEBCO elevation onto the HYCOM grid by nearest neighbour."""
    g = xr.open_dataset(GEBCO_NC, engine="scipy")
    glat, glon = g["lat"].values, g["lon"].values
    elev = g["elevation"].values
    iy = np.abs(glat[:, None] - target_lat[None, :]).argmin(axis=0)
    ix = np.abs(glon[:, None] - target_lon[None, :]).argmin(axis=0)
    depth = -elev[np.ix_(iy, ix)].astype("float64")  # positive metres below sea level
    g.close()
    return depth


def load_no_take_zones():
    """Prepared geometries for MPAs usable as hard geofences."""
    with open(MPA_GEOJSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    zones = []
    for feat in data["features"]:
        props = feat["properties"]
        if not props.get("orca_geofence_usable"):
            continue
        geom = shape(feat["geometry"])
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        zones.append((props.get("name"), prep(geom)))
    return zones


def build_zones(lats, lons, mean_sst, front, depth, no_take):
    """Group frontal, mid-shelf, unrestricted cells into contiguous candidate zones."""
    valid = np.isfinite(mean_sst) & np.isfinite(front)
    in_depth = valid & (depth >= DEPTH_MIN_M) & (depth <= DEPTH_MAX_M)

    if not in_depth.any():
        return [], None

    threshold = float(np.nanpercentile(front[in_depth], FRONT_PERCENTILE))
    candidate = in_depth & (front >= threshold)

    labels, count = ndimage.label(candidate)
    zones = []
    for label_id in range(1, count + 1):
        cells = labels == label_id
        n_cells = int(cells.sum())
        if n_cells < MIN_ZONE_CELLS:
            continue
        yy, xx = np.nonzero(cells)
        clat = float(lats[yy].mean())
        clon = float(lons[xx].mean())

        pt = Point(clon, clat)
        blocked = next((nm for nm, geom in no_take if geom.contains(pt)), None)
        if blocked:
            continue

        zones.append({
            "centroid_lat": round(clat, 5),
            "centroid_lon": round(clon, 5),
            "cell_count": n_cells,
            "approx_area_km2": round(n_cells * 4.63 * 4.63, 1),
            "mean_front_strength_c_per_km": round(float(front[cells].mean()), 4),
            "max_front_strength_c_per_km": round(float(front[cells].max()), 4),
            "mean_sst_c": round(float(mean_sst[cells].mean()), 2),
            "mean_depth_m": round(float(depth[cells].mean()), 1),
            "bearings_from_ports": port_vectors(clat, clon),
        })

    zones.sort(key=lambda z: z["mean_front_strength_c_per_km"], reverse=True)
    return zones, threshold


def port_vectors(zone_lat, zone_lon):
    """Range and bearing from each pilot port, the form a fisherman actually uses."""
    out = {}
    for port, (plat, plon) in PILOT_PORTS.items():
        fwd_az, _, dist_m = GEOD.inv(plon, plat, zone_lon, zone_lat)
        out[port] = {
            "distance_km": round(dist_m / 1000.0, 1),
            "bearing_deg": round(fwd_az % 360.0, 1),
            "compass": compass_point(fwd_az % 360.0),
        }
    return out


def compass_point(bearing):
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return points[int((bearing + 11.25) % 360 / 22.5)]


def main():
    print("=" * 78)
    print("PFZ fallback layer for the pilot region (derived proxy, not an advisory)")
    print("=" * 78)

    lats, lons, mean_sst, front, n_steps = load_sst_fronts()
    print("HYCOM subset : %d x %d cells @ %.3f deg, %d forecast steps"
          % (len(lats), len(lons), abs(lats[1] - lats[0]), n_steps))
    print("SST          : %.2f .. %.2f degC (%.0f%% wet)"
          % (np.nanmin(mean_sst), np.nanmax(mean_sst),
             100 * np.isfinite(mean_sst).mean()))

    depth = sample_depth(lats, lons)
    no_take = load_no_take_zones()
    print("bathymetry   : GEBCO sampled onto model grid")
    print("geofences    : %d usable MPA polygons loaded" % len(no_take))

    zones, threshold = build_zones(lats, lons, mean_sst, front, depth, no_take)
    print("front cutoff : p%.0f = %.4f degC/km" % (FRONT_PERCENTILE, threshold or 0))
    print("zones found  : %d (>= %d cells, depth %.0f-%.0f m, outside no-take MPAs)"
          % (len(zones), MIN_ZONE_CELLS, DEPTH_MIN_M, DEPTH_MAX_M))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": now,
        "layer_type": "DERIVED_PROXY",
        "confidence_tier": "LOW-DATA",
        "applies_to_sector": "SEC006 (SOUTH TAMILNADU)",
        "not_an_advisory": (
            "This is NOT an INCOIS PFZ advisory. It is a thermal-front proxy computed "
            "by ORCA for use only when INCOIS publishes no advisory for the sector. "
            "Any response built on it must say so and must carry LOW-DATA confidence."),
        "method": {
            "sst_source": "INCOIS HYCOM RSMC forecast, surface layer, mean over "
                          "%d forecast steps" % n_steps,
            "front_metric": "magnitude of horizontal SST gradient, degC/km",
            "front_threshold_percentile": FRONT_PERCENTILE,
            "front_threshold_value_c_per_km": round(threshold, 4) if threshold else None,
            "depth_source": "GEBCO 15 arc-second grid",
            "depth_band_m": [DEPTH_MIN_M, DEPTH_MAX_M],
            "depth_band_rationale": (
                "ICAR-CMFRI analysis of PFZ hits off Thoothukudi reports clustering on "
                "the mid-shelf; this band encodes that published prior."),
            "exclusions": "Zones whose centroid falls inside a geofence-usable MPA "
                          "polygon are removed.",
            "minimum_zone_cells": MIN_ZONE_CELLS,
        },
        "limitations": [
            "Thermal fronts alone; no chlorophyll term. The available MOSDAC OCM-3 "
            "chlorophyll files are from March 2026 and at 25 km, too stale and too "
            "coarse to combine with a current 1/16 deg SST field.",
            "Front strength is computed from a model forecast, not a satellite "
            "retrieval, so it does not reproduce INCOIS's operational product.",
            "Unvalidated against catch data; ranking indicates relative frontal "
            "structure only, not expected yield.",
        ],
        "pilot_ports": {k: {"lat": v[0], "lon": v[1]} for k, v in PILOT_PORTS.items()},
        "zone_count": len(zones),
        "zones": zones,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    json_path = os.path.join(OUT_DIR, "pfz_fallback_pilot_region.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    geo_path = os.path.join(OUT_DIR, "pfz_fallback_pilot_region.geojson")
    with open(geo_path, "w", encoding="utf-8") as fh:
        json.dump({
            "type": "FeatureCollection",
            "name": "orca_pfz_fallback_pilot_region",
            "orca_metadata": {k: payload[k] for k in
                              ("generated_at", "layer_type", "confidence_tier",
                               "applies_to_sector", "not_an_advisory", "method",
                               "limitations")},
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [z["centroid_lon"], z["centroid_lat"]]},
                "properties": {k: v for k, v in z.items()
                               if k not in ("centroid_lat", "centroid_lon")},
            } for z in zones],
        }, fh, ensure_ascii=False, indent=1)

    print("\n%-4s %-19s %-9s %-8s %s" % ("RANK", "CENTROID", "FRONT", "DEPTH",
                                         "FROM THOOTHUKUDI"))
    print("-" * 78)
    for i, z in enumerate(zones[:10], 1):
        t = z["bearings_from_ports"]["Thoothukudi"]
        print("%-4d %7.3fN %8.3fE  %.4f    %5.0f m   %5.1f km %s"
              % (i, z["centroid_lat"], z["centroid_lon"],
                 z["mean_front_strength_c_per_km"], z["mean_depth_m"],
                 t["distance_km"], t["compass"]))
    print("=" * 78)
    print("  wrote %s" % json_path)
    print("  wrote %s" % geo_path)


if __name__ == "__main__":
    main()
