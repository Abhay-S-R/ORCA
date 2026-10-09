"""Top-level sea-route computation function.

Coordinates the full pipeline:
  1. Load grid (cached).
  2. Validate start/end inside India bbox and in the sea.
  3. Snap start/end to nearest free sea cell.
  4. Run Floyd–Warshall on a land-checked corridor.
  5. Convert cell path to lat/lng.
  6. Smooth path with line-of-sight pruning.
  7. Prepend exact start + append exact end.
  8. Compute distance, duration, ETA, warnings.
  9. Return SeaRouteResult.

Also exports `sea_route_no_cache` for unit tests that need a fresh run.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from orca.sea_route.config import DEFAULT_CONFIG, SeaRouteConfig
from orca.sea_route.datasets import (
    load_land_polygons,
    load_protected_areas,
    load_restricted_areas,
)
from orca.sea_route.grid import build_grid
from orca.sea_route.smoother import smooth_path
from orca.sea_route.warshall import path_distance_nm, warshall_route

log = logging.getLogger("orca.sea_route.router")

# India bbox (same as config defaults, kept explicit here for clarity).
_BBOX_W, _BBOX_E, _BBOX_S, _BBOX_N = 66.0, 95.0, 5.0, 24.0

_KM_PER_NM = 1.852


@dataclass
class SeaRouteResult:
    coords: list[tuple[float, float]]    # [(lat, lng), …]
    distance_nm: float
    distance_km: float
    hours: float
    eta: str                             # ISO-8601 UTC
    warnings: list[str]


def _inside_india_bbox(lat: float, lng: float) -> bool:
    return _BBOX_S <= lat <= _BBOX_N and _BBOX_W <= lng <= _BBOX_E


def _is_on_land(lat: float, lng: float, land_tree: STRtree | None) -> bool:
    if land_tree is None:
        return False
    pt = Point(lng, lat)
    hits = land_tree.query(pt, predicate="within")
    return len(hits) > 0


def _is_in_blocking_restricted(lat: float, lng: float, restricted_areas, protected_areas) -> str | None:
    """Return area name if point is inside a blocking restricted/protected area, else None."""
    pt = Point(lng, lat)
    for area in restricted_areas:
        if area.mode == "block" and area.geometry.contains(pt):
            return area.name
    for area in protected_areas:
        if area.mode == "block" and area.geometry.contains(pt):
            return area.name
    return None


def _warn_near_restricted(
    coords: list[tuple[float, float]],
    restricted_areas,
    warn_nm: float = 5.0,
) -> list[str]:
    """Return warning strings for each restricted area the route passes within warn_nm nm."""
    if not restricted_areas:
        return []
    from shapely.geometry import LineString as LS

    _R_NM = 3440.065

    warnings: list[str] = []
    # Build a linestring from the route for proximity checks.
    if len(coords) < 2:
        return []

    # Convert warn_nm to approximate degrees for fast pre-filter.
    warn_deg = warn_nm / 60.0

    for area in restricted_areas:
        geom = area.geometry
        # Quick bounding-box check first.
        minx, miny, maxx, maxy = geom.bounds
        # Check if any route point is near the bounding box.
        near = False
        for lat, lng in coords:
            if (minx - warn_deg <= lng <= maxx + warn_deg and
                    miny - warn_deg <= lat <= maxy + warn_deg):
                near = True
                break
        if not near:
            continue
        # Precise check: distance from linestring to area boundary.
        route_line = LS([(lng, lat) for lat, lng in coords])
        dist_deg = route_line.distance(geom)
        # Rough conversion deg -> nm at mid-latitude.
        mid_lat = (coords[0][0] + coords[-1][0]) / 2
        dist_nm = dist_deg * 60.0 * math.cos(math.radians(mid_lat))
        if dist_nm <= warn_nm:
            warnings.append(
                f"Route passes within {dist_nm:.1f} nm of restricted area: {area.name}"
            )
    return warnings


@lru_cache(maxsize=256)
def _cached_route(
    start_lat: float, start_lng: float,
    end_lat: float, end_lng: float,
    speed_knots: float,
    departure_iso: str,
    cell_deg: float,
    land_buffer_nm: float,
    eez_blocking: bool,
    standoff_buffer_nm: float = 1.8,
    is_map_pick: bool = False,
) -> SeaRouteResult:
    """Cached wrapper so repeated port-to-port queries reuse the result."""
    return _compute_route(
        start_lat, start_lng, end_lat, end_lng,
        speed_knots, departure_iso, cell_deg, land_buffer_nm, eez_blocking,
        standoff_buffer_nm=standoff_buffer_nm,
        is_map_pick=is_map_pick,
    )


def _compute_route(
    start_lat: float, start_lng: float,
    end_lat: float, end_lng: float,
    speed_knots: float,
    departure_iso: str,
    cell_deg: float,
    land_buffer_nm: float,
    eez_blocking: bool,
    standoff_buffer_nm: float = 1.8,
    is_map_pick: bool = False,
) -> SeaRouteResult:
    """Core routing pipeline (not cached directly — wrap via sea_route())."""
    land_polygons = load_land_polygons()
    restricted = load_restricted_areas()
    protected = load_protected_areas()

    land_tree: STRtree | None = STRtree(list(land_polygons)) if land_polygons else None

    # ── Validate start / end ──────────────────────────────────────────────────
    if not _inside_india_bbox(start_lat, start_lng):
        raise ValueError("Please select a point within Indian waters (start is outside India bbox)")
    if not _inside_india_bbox(end_lat, end_lng):
        raise ValueError("Please select a point within Indian waters (end is outside India bbox)")

    start_on_land = _is_on_land(start_lat, start_lng, land_tree)
    end_on_land = _is_on_land(end_lat, end_lng, land_tree)

    blocked_start = _is_in_blocking_restricted(start_lat, start_lng, restricted, protected)
    if blocked_start:
        raise ValueError(f"Start point is inside a restricted area: {blocked_start}. Choose a different point.")
    blocked_end = _is_in_blocking_restricted(end_lat, end_lng, restricted, protected)
    if blocked_end:
        raise ValueError(f"End point is inside a restricted area: {blocked_end}. Choose a different point.")

    # ── Build / retrieve grid ─────────────────────────────────────────────────
    grid = build_grid(
        cell_deg=cell_deg,
        lat_min=_BBOX_S, lat_max=_BBOX_N,
        lng_min=_BBOX_W, lng_max=_BBOX_E,
        land_buffer_nm=land_buffer_nm,
        eez_blocking=eez_blocking,
    )

    # ── Snap start/end to nearest sea cell ───────────────────────────────────
    start_cell = grid.snap_to_sea(start_lat, start_lng)
    end_cell = grid.snap_to_sea(end_lat, end_lng)

    if start_cell is None:
        if start_on_land:
            raise ValueError("Selected point is on land, please choose a point in the sea (start)")
        raise ValueError("No sea route found — start is too far from navigable water")
    if end_cell is None:
        if end_on_land:
            raise ValueError("Selected point is on land, please choose a point in the sea (end)")
        raise ValueError("No sea route found — end is too far from navigable water")

    if is_map_pick:
        # If user picked on land, allow coastal snapping within 25 nm (ports/jetties),
        # but reject points deep inland (e.g. inland cities).
        from orca.sea_route.warshall import _haversine_nm
        if start_on_land:
            snapped_lat, snapped_lng = grid.cell_to_latlon(*start_cell)
            if _haversine_nm(start_lat, start_lng, snapped_lat, snapped_lng) > 25.0:
                raise ValueError("Selected point is on land, please choose a point in the sea (start)")
        if end_on_land:
            snapped_lat, snapped_lng = grid.cell_to_latlon(*end_cell)
            if _haversine_nm(end_lat, end_lng, snapped_lat, snapped_lng) > 25.0:
                raise ValueError("Selected point is on land, please choose a point in the sea (end)")

    # ── Floyd–Warshall (corridor; land and bbox are infinite-cost) ────────────
    cell_path = warshall_route(start_cell[0], start_cell[1], end_cell[0], end_cell[1], grid)
    if cell_path is None:
        raise ValueError("No sea route found between these points")

    # Convert cell indices to lat/lng.
    latlon_path: list[tuple[float, float]] = [
        grid.cell_to_latlon(r, c) for r, c in cell_path
    ]

    # ── Smooth ────────────────────────────────────────────────────────────────
    smoothed = smooth_path(latlon_path, land_polygons, restricted, standoff_buffer_nm=standoff_buffer_nm)

    # ── Insert start/end coordinates safely without land or boundary crossing ──
    block_geoms = list(land_polygons)
    for a in restricted:
        if a.mode == "block":
            block_geoms.append(a.geometry)
    for a in protected:
        if a.mode == "block":
            block_geoms.append(a.geometry)
    block_tree = STRtree(block_geoms) if block_geoms else None

    from orca.agents.geospatial import depth_at_point
    start_depth = depth_at_point(start_lat, start_lng)
    end_depth = depth_at_point(end_lat, end_lng)

    start_pt = (start_lat, start_lng)
    if start_on_land or start_depth.on_land or (start_depth.depth_m is not None and start_depth.depth_m < 2.0):
        start_pt = smoothed[0]
    elif block_tree:
        seg = LineString([(start_lng, start_lat), (smoothed[0][1], smoothed[0][0])])
        if len(block_tree.query(seg, predicate="intersects")) > 0:
            start_pt = smoothed[0]

    end_pt = (end_lat, end_lng)
    if end_on_land or end_depth.on_land or (end_depth.depth_m is not None and end_depth.depth_m < 2.0):
        end_pt = smoothed[-1]
    elif block_tree:
        seg = LineString([(end_lng, end_lat), (smoothed[-1][1], smoothed[-1][0])])
        if len(block_tree.query(seg, predicate="intersects")) > 0:
            end_pt = smoothed[-1]

    coords: list[tuple[float, float]] = []
    if start_pt != smoothed[0]:
        coords.append(start_pt)
    coords.extend(smoothed)
    if end_pt != smoothed[-1] and end_pt != coords[-1]:
        coords.append(end_pt)

    if len(coords) < 2:
        coords = [smoothed[0], smoothed[-1]]

    # ── Distance & timing ─────────────────────────────────────────────────────
    dist_nm = path_distance_nm(coords)
    dist_km = dist_nm * _KM_PER_NM
    hours = dist_nm / max(speed_knots, 0.1)

    dep = datetime.fromisoformat(departure_iso.replace("Z", "+00:00")) if departure_iso else datetime.now(timezone.utc)
    eta_dt = dep + timedelta(hours=hours)
    eta_str = eta_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Warnings ──────────────────────────────────────────────────────────────
    warnings: list[str] = []
    warnings += _warn_near_restricted(coords, restricted)
    warnings += _warn_near_restricted(coords, protected)

    # Monsoon warning for small vessels (June–September).
    if dep.month in (6, 7, 8, 9):
        warnings.append(
            "Monsoon season (June–September): sea conditions may be severe for small vessels. "
            "Follow Coast Guard advisories before departure."
        )

    warnings.append(
        "DISCLAIMER: Route is for planning only. Follow official navigation and Coast Guard instructions."
    )
    warnings.append(
        "NOTE: Maritime boundary data is PLACEHOLDER. Replace with official IMBL data before operational use."
    )

    return SeaRouteResult(
        coords=coords,
        distance_nm=round(dist_nm, 2),
        distance_km=round(dist_km, 2),
        hours=round(hours, 2),
        eta=eta_str,
        warnings=warnings,
    )


def sea_route(
    start_lat: float, start_lng: float,
    end_lat: float, end_lng: float,
    speed_knots: float = 8.0,
    departure_iso: str = "",
    cfg: SeaRouteConfig = DEFAULT_CONFIG,
    is_map_pick: bool = False,
) -> SeaRouteResult:
    """Public entry point.  Uses the module-level LRU cache for repeated calls."""
    dep_key = departure_iso or ""
    return _cached_route(
        round(start_lat, 4), round(start_lng, 4),
        round(end_lat, 4), round(end_lng, 4),
        round(speed_knots, 2), dep_key,
        cfg.cell_deg, cfg.land_buffer_nm, cfg.eez_blocking,
        standoff_buffer_nm=cfg.standoff_buffer_nm,
        is_map_pick=is_map_pick,
    )


def sea_route_no_cache(
    start_lat: float, start_lng: float,
    end_lat: float, end_lng: float,
    speed_knots: float = 8.0,
    departure_iso: str = "",
    cfg: SeaRouteConfig = DEFAULT_CONFIG,
    is_map_pick: bool = False,
) -> SeaRouteResult:
    """Non-cached entry point for testing or dynamic configs."""
    return _compute_route(
        start_lat, start_lng, end_lat, end_lng,
        speed_knots, departure_iso,
        cfg.cell_deg, cfg.land_buffer_nm, cfg.eez_blocking,
        standoff_buffer_nm=cfg.standoff_buffer_nm,
        is_map_pick=is_map_pick,
    )

