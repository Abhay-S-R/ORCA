"""Sea-route grid builder.

Builds a 2-D boolean navigability array over the India bbox at startup.
The grid is built once and cached; Floyd–Warshall reads it on every request.

Coordinate convention:
  row 0 = north edge (lat_max), row increases southward.
  col 0 = west edge (lng_min), col increases eastward.

Cell (row, col) represents the square centred on:
  lat = lat_max - (row + 0.5) * cell_deg
  lng = lng_min + (col + 0.5) * cell_deg
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from shapely.geometry import Point
from shapely.strtree import STRtree

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger("orca.sea_route.grid")

# Nautical miles per degree of latitude (approximate, good enough for a grid).
_NM_PER_DEG_LAT = 60.0


def _nm_to_deg(nm: float, lat_deg: float) -> float:
    """Convert nautical miles to degrees at a given latitude."""
    lat_rad = math.radians(lat_deg)
    lng_per_nm = 1.0 / (60.0 * math.cos(lat_rad)) if math.cos(lat_rad) > 1e-9 else 1.0
    lat_per_nm = 1.0 / _NM_PER_DEG_LAT
    # Use the larger of lat/lng deg-per-nm so the buffer is conservative.
    return nm * max(lat_per_nm, lng_per_nm)


@dataclass
class SeaGrid:
    """Navigability grid over the India bbox.

    navigable[row, col] is True when a ship may traverse that cell.
    """
    navigable: np.ndarray   # shape (nrows, ncols), dtype bool
    cell_deg: float
    lat_max: float
    lat_min: float
    lng_min: float
    lng_max: float
    nrows: int
    ncols: int

    def cell_to_latlon(self, row: int, col: int) -> tuple[float, float]:
        lat = self.lat_max - (row + 0.5) * self.cell_deg
        lng = self.lng_min + (col + 0.5) * self.cell_deg
        # Refine fairway coordinates for the narrow Pamban navigational channel
        # (lat ~9.22 to 9.30, lon ~79.16 to 79.23) so waypoints follow the dredged
        # Scherzer Lift Bridge fairway (lon 79.198) and avoid Mandapam shore/island rocks.
        if 9.26 <= lat <= 9.30 and 79.16 <= lng <= 79.23:
            return 9.280, 79.198
        if 9.22 <= lat <= 9.26 and 79.16 <= lng <= 79.23:
            return 9.245, 79.170
        return lat, lng

    def latlon_to_cell(self, lat: float, lng: float) -> tuple[int, int]:
        row = int((self.lat_max - lat) / self.cell_deg)
        col = int((lng - self.lng_min) / self.cell_deg)
        row = max(0, min(self.nrows - 1, row))
        col = max(0, min(self.ncols - 1, col))
        return row, col

    def _is_navigable_open(self, r: int, c: int) -> bool:
        if not (0 <= r < self.nrows and 0 <= c < self.ncols and self.navigable[r, c]):
            return False
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.nrows and 0 <= nc < self.ncols and self.navigable[nr, nc]:
                    return True
        return False

    def snap_to_sea(self, lat: float, lng: float, max_search: int = 30) -> tuple[int, int] | None:
        """Return the nearest navigable cell to (lat, lng), within max_search steps."""
        r0, c0 = self.latlon_to_cell(lat, lng)
        if self._is_navigable_open(r0, c0):
            return r0, c0
        # Spiral outward.
        for dist in range(1, max_search + 1):
            for dr in range(-dist, dist + 1):
                for dc in range(-dist, dist + 1):
                    if max(abs(dr), abs(dc)) != dist:
                        continue
                    r, c = r0 + dr, c0 + dc
                    if self._is_navigable_open(r, c):
                        return r, c
        return None



def _build_land_index(land_polygons, buffer_deg: float) -> STRtree:
    """STRtree of (possibly buffered) land polygons for fast containment queries."""
    if buffer_deg > 0:
        buffered = [p.buffer(buffer_deg) for p in land_polygons]
    else:
        buffered = list(land_polygons)
    return STRtree(buffered)


def _build_blocked_index(
    restricted_areas,
    protected_areas,
    eez_polygon,
) -> tuple[STRtree | None, STRtree | None, object | None]:
    """Return STRtrees for blocking restricted areas, blocking protected areas, EEZ."""

    block_geoms = [a.geometry for a in restricted_areas if a.mode == "block"]
    block_tree = STRtree(block_geoms) if block_geoms else None

    prot_block = [a.geometry for a in protected_areas if a.mode == "block"]
    prot_tree = STRtree(prot_block) if prot_block else None

    return block_tree, prot_tree, eez_polygon


@lru_cache(maxsize=1)
def build_grid(
    cell_deg: float = 0.05,
    lat_min: float = 5.0,
    lat_max: float = 24.0,
    lng_min: float = 66.0,
    lng_max: float = 95.0,
    land_buffer_nm: float = 2.0,
    eez_blocking: bool = False,
) -> SeaGrid:
    """Build and cache the navigability grid.

    Called once at startup (triggered by the first routing request).
    Subsequent calls return the cached result instantly.
    """
    import numpy as np

    from orca.sea_route.datasets import (
        load_eez_polygon,
        load_land_polygons,
        load_protected_areas,
        load_restricted_areas,
    )

    log.info("sea_route: building grid (cell=%.3f°, %.0f×%.0f) …", cell_deg,
             (lat_max - lat_min) / cell_deg, (lng_max - lng_min) / cell_deg)

    nrows = round((lat_max - lat_min) / cell_deg)
    ncols = round((lng_max - lng_min) / cell_deg)
    navigable = np.ones((nrows, ncols), dtype=bool)

    # Mid-latitude for buffer conversion (use India's geographic centre).
    mid_lat = (lat_min + lat_max) / 2.0
    buffer_deg = _nm_to_deg(land_buffer_nm, mid_lat)

    land_polygons = load_land_polygons()
    land_tree = _build_land_index(land_polygons, buffer_deg) if land_polygons else None
    raw_land_tree = STRtree(list(land_polygons)) if land_polygons else None

    restricted = load_restricted_areas()
    protected = load_protected_areas()
    eez_polygon = load_eez_polygon() if eez_blocking else None

    # Buffer thin linear/ribbon restricted areas so grid cells cannot step across them
    barrier_buffer = cell_deg * 0.7
    block_rest = [
        a.geometry.buffer(barrier_buffer) if a.geometry.geom_type in ("LineString", "MultiLineString") else a.geometry
        for a in restricted if a.mode == "block"
    ]
    rest_tree = STRtree(block_rest) if block_rest else None

    block_prot = [
        a.geometry.buffer(barrier_buffer) if a.geometry.geom_type in ("LineString", "MultiLineString") else a.geometry
        for a in protected if a.mode == "block"
    ]
    prot_tree = STRtree(block_prot) if block_prot else None

    # Block shallow waters < 2.5m using vectorized GEBCO elevation so corridors stay in deep navigable sea
    try:
        import xarray as xr

        from orca.agents.geospatial import _bathymetry
        ds = _bathymetry()
        lats_arr = [lat_max - (r + 0.5) * cell_deg for r in range(nrows)]
        lons_arr = [lng_min + (c + 0.5) * cell_deg for c in range(ncols)]
        lat_idx = xr.DataArray(lats_arr, dims="grid_lat")
        lon_idx = xr.DataArray(lons_arr, dims="grid_lon")
        elev = ds["elevation"].sel(lat=lat_idx, lon=lon_idx, method="nearest").values
        # Cells with elevation > -4.5m have depth < 4.5m or are land; filter out to keep routes in deep water.
        # Preserve designated coastal channels (Pamban Pass and Palk Strait) where navigable depths are 1.5–4.0m.
        shallow_mask = (elev > -4.5)
        for r_idx, lat_val in enumerate(lats_arr):
            if 9.15 <= lat_val <= 10.35:
                for c_idx, lng_val in enumerate(lons_arr):
                    if 79.15 <= lng_val <= 80.05 and elev[r_idx, c_idx] <= -1.5:
                        shallow_mask[r_idx, c_idx] = False
        navigable[shallow_mask] = False
    except Exception as exc:
        log.warning("sea_route: bathymetry depth filter skipped: %s", exc)

    # Block Adam's Bridge / Ram Setu: natural shallow limestone reef barrier (1-2m depths)
    # and IMBL border between Dhanushkodi and Mannar Island that is unnavigable for coastal vessels.
    for r in range(nrows):
        lat = lat_max - (r + 0.5) * cell_deg
        if 9.04 <= lat <= 9.25:
            for c in range(ncols):
                lng = lng_min + (c + 0.5) * cell_deg
                if 79.35 <= lng <= 79.80:
                    navigable[r, c] = False

    for row in range(nrows):
        lat = lat_max - (row + 0.5) * cell_deg
        for col in range(ncols):
            if not navigable[row, col]:
                continue
            lng = lng_min + (col + 0.5) * cell_deg
            pt = Point(lng, lat)

            # In Pamban Pass (lat 9.22 to 9.32, lon 79.17 to 79.22), use raw unbuffered land
            # so the 1.5 nm coastal buffer does not artificially close the 0.8 nm wide navigation channel.
            is_pamban = (9.22 <= lat <= 9.32 and 79.17 <= lng <= 79.22)
            tree_to_check = raw_land_tree if is_pamban else land_tree

            # Block if on/near land.
            if tree_to_check is not None:
                hits = tree_to_check.query(pt, predicate="intersects")
                if len(hits) > 0:
                    navigable[row, col] = False
                    continue

            # Block if inside a blocking restricted area.
            if rest_tree is not None:
                hits = rest_tree.query(pt, predicate="intersects")
                if len(hits) > 0:
                    navigable[row, col] = False
                    continue

            # Block if inside a blocking protected area.
            if prot_tree is not None:
                hits = prot_tree.query(pt, predicate="intersects")
                if len(hits) > 0:
                    navigable[row, col] = False
                    continue

            # Block if outside India EEZ.
            if eez_polygon is not None and not eez_polygon.contains(pt):
                navigable[row, col] = False
                continue

    sea_count = int(navigable.sum())
    log.info("sea_route: grid built — %d/%d cells navigable", sea_count, nrows * ncols)

    return SeaGrid(
        navigable=navigable,
        cell_deg=cell_deg,
        lat_max=lat_max,
        lat_min=lat_min,
        lng_min=lng_min,
        lng_max=lng_max,
        nrows=nrows,
        ncols=ncols,
    )
