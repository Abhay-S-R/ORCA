"""
Shared grid utilities for ORCA data extraction.

The central problem this solves: INCOIS operational model grids (WW3 at 0.1 deg,
HYCOM at 1/16 deg) carry a land mask. A coastal port's true coordinates frequently
fall inside a land cell, so a naive `.sel(method='nearest')` returns NaN. That is
what produced the empty significant-wave-height column for Thoothukudi, Kochi,
Mumbai and Visakhapatnam in the original pilot extraction.

The fix is to snap the target to the nearest *wet* (non-NaN) cell and to record how
far the snap moved, so that downstream agents can cite the actual grid point they
used rather than implying the value was sampled at the port itself. Provenance is a
first-class requirement in the ORCA architecture, so a silent snap would be as much
of a defect as the NaN was.
"""

import numpy as np

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Accepts scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def snap_to_wet_cell(lats, lons, wet_mask, target_lat, target_lon,
                     max_search_deg=1.0):
    """
    Find the nearest ocean cell to (target_lat, target_lon).

    `wet_mask` is a 2-D boolean array shaped (len(lats), len(lons)) that is True
    where the model has valid data. The search grows a square window outward from
    the nearest index until it finds at least one wet cell, then picks the closest
    of those by true great-circle distance rather than by index offset -- index
    distance is anisotropic in longitude and would bias the pick equatorward.

    Returns (iy, ix, grid_lat, grid_lon, distance_km), or None if no wet cell lies
    within `max_search_deg`.
    """
    iy0 = int(np.argmin(np.abs(lats - target_lat)))
    ix0 = int(np.argmin(np.abs(lons - target_lon)))

    lat_step = abs(float(lats[1] - lats[0]))
    lon_step = abs(float(lons[1] - lons[0]))
    max_ry = max(1, int(round(max_search_deg / lat_step)))
    max_rx = max(1, int(round(max_search_deg / lon_step)))
    max_r = max(max_ry, max_rx)

    for radius in range(0, max_r + 1):
        y_lo, y_hi = max(0, iy0 - radius), min(len(lats), iy0 + radius + 1)
        x_lo, x_hi = max(0, ix0 - radius), min(len(lons), ix0 + radius + 1)
        window = wet_mask[y_lo:y_hi, x_lo:x_hi]
        if not window.any():
            continue

        wy, wx = np.nonzero(window)
        cand_iy = wy + y_lo
        cand_ix = wx + x_lo
        dists = haversine_km(target_lat, target_lon, lats[cand_iy], lons[cand_ix])
        best = int(np.argmin(dists))
        iy, ix = int(cand_iy[best]), int(cand_ix[best])
        return iy, ix, float(lats[iy]), float(lons[ix]), float(dists[best])

    return None


def build_wet_mask(reference_slice):
    """Ocean cells are those with valid (non-NaN) data in a reference 2-D slice."""
    return ~np.isnan(np.asarray(reference_slice, dtype="float64"))
