"""Sea-route grid builder.

Builds a 2-D boolean navigability array over the India bbox at startup.
The grid is built once and cached; A* reads it on every request.

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

from shapely.geometry import Point, box
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
    # Use the larger of lat/lng deg-per-nm so the buffer is conservative.
    return nm / _NM_PER_DEG_LAT


@dataclass
class SeaGrid:
    """Navigability grid over the India bbox.

    navigable[row, col] is True when a ship may traverse that cell.
    """
    navigable: "np.ndarray"   # shape (nrows, ncols), dtype bool
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
        return lat, lng

    def latlon_to_cell(self, lat: float, lng: float) -> tuple[int, int]:
        row = int((self.lat_max - lat) / self.cell_deg)
        col = int((lng - self.lng_min) / self.cell_deg)
        row = max(0, min(self.nrows - 1, row))
        col = max(0, min(self.ncols - 1, col))
        return row, col

    def snap_to_sea(self, lat: float, lng: float, max_search: int = 30) -> tuple[int, int] | None:
        """Return the nearest navigable cell to (lat, lng), within max_search steps."""
        r0, c0 = self.latlon_to_cell(lat, lng)
        if self.navigable[r0, c0]:
            return r0, c0
        # Spiral outward.
        for dist in range(1, max_search + 1):
            for dr in range(-dist, dist + 1):
                for dc in range(-dist, dist + 1):
                    if max(abs(dr), abs(dc)) != dist:
                        continue
                    r, c = r0 + dr, c0 + dc
                    if 0 <= r < self.nrows and 0 <= c < self.ncols and self.navigable[r, c]:
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
    import numpy as np  # local import to avoid polluting module-level namespace

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
    eez_blocking: bool = True,
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

    nrows = int(round((lat_max - lat_min) / cell_deg))
    ncols = int(round((lng_max - lng_min) / cell_deg))
    navigable = np.ones((nrows, ncols), dtype=bool)

    # Mid-latitude for buffer conversion (use India's geographic centre).
    mid_lat = (lat_min + lat_max) / 2.0
    buffer_deg = _nm_to_deg(land_buffer_nm, mid_lat)

    land_polygons = load_land_polygons()
    land_tree = _build_land_index(land_polygons, buffer_deg) if land_polygons else None

    restricted = load_restricted_areas()
    protected = load_protected_areas()
    eez_polygon = load_eez_polygon() if eez_blocking else None

    # Buffer thin linear/ribbon restricted areas so grid cells cannot step across them
    barrier_buffer = cell_deg * 0.7
    block_rest = [a.geometry.buffer(barrier_buffer) for a in restricted if a.mode == "block"]
    rest_tree = STRtree(block_rest) if block_rest else None

    block_prot = [a.geometry.buffer(barrier_buffer) for a in protected if a.mode == "block"]
    prot_tree = STRtree(block_prot) if block_prot else None

    for row in range(nrows):
        lat = lat_max - (row + 0.5) * cell_deg
        for col in range(ncols):
            lng = lng_min + (col + 0.5) * cell_deg
            pt = Point(lng, lat)

            # Block if on/near land.
            if land_tree is not None:
                hits = land_tree.query(pt, predicate="intersects")
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
