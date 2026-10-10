"""Path smoother: removes collinear / redundant waypoints using line-of-sight
visibility checks against land and restricted-area polygons.

After Floyd–Warshall the path is a staircase of grid-cell centres.  The smoother walks
the path with a greedy look-ahead: if the straight segment from waypoint[i]
to waypoint[j] does not intersect any blocking polygon, waypoints i+1 … j-1
are redundant and are removed.  The result hugs the coast naturally.

The safety guarantee is the same as the routing engine's: a segment is only
kept when the corridor between its two endpoints is provably free of land and
blocking restricted areas.  Smoothed segments are tested at the LINE level,
not just at discrete points.
"""
from __future__ import annotations

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from orca.agents.geospatial import depth_at_point
from orca.sea_route.datasets import load_eez_polygon


_TREE_CACHE: dict[float, STRtree] = {}


def _build_blocker_tree(
    land_polygons: tuple[BaseGeometry, ...],
    restricted_areas,            # tuple[RestrictedArea, ...]
    buffer_deg: float = 0.0,
) -> STRtree | None:
    """STRtree of all geometries a route segment must not cross (cached)."""
    key = round(buffer_deg, 6)
    if key in _TREE_CACHE:
        return _TREE_CACHE[key]
    geoms: list[BaseGeometry] = []
    if buffer_deg > 0:
        geoms.extend(p.buffer(buffer_deg) for p in land_polygons)
    else:
        geoms.extend(land_polygons)
    for area in restricted_areas:
        if area.mode == "block":
            geoms.append(area.geometry.buffer(buffer_deg) if buffer_deg > 0 else area.geometry)
    tree = STRtree(geoms) if geoms else None
    if tree is not None:
        _TREE_CACHE[key] = tree
    return tree


def _segment_clear(
    lat_a: float, lng_a: float,
    lat_b: float, lng_b: float,
    tree: STRtree | None,
) -> bool:
    """Return True iff the straight line from A to B does not intersect any blocker."""
    if tree is None:
        return True
    seg = LineString([(lng_a, lat_a), (lng_b, lat_b)])
    hits = tree.query(seg, predicate="intersects")
    return len(hits) == 0


def smooth_path(
    path: list[tuple[float, float]],          # [(lat, lng), …]
    land_polygons: tuple[BaseGeometry, ...],
    restricted_areas,
    standoff_buffer_nm: float = 1.8,
) -> list[tuple[float, float]]:
    """Greedy line-of-sight path smoother.

    Iterates from each waypoint and extends the look-ahead as far as
    possible without crossing a blocker or violating the coastal standoff buffer.
    Guaranteed to return a path with at least the same endpoints as the input.
    """
    if len(path) <= 2:
        return path

    # Raw blockers (land + restricted): zero-tolerance crossing check.
    raw_tree = _build_blocker_tree(land_polygons, restricted_areas, buffer_deg=0.0)

    # Standoff blockers: ensures shortcut chords do not shave within standoff_buffer_nm of coast/headlands.
    deg_per_nm = 1.0 / 60.0
    standoff_deg = standoff_buffer_nm * deg_per_nm
    standoff_tree = _build_blocker_tree(land_polygons, restricted_areas, buffer_deg=standoff_deg) if standoff_deg > 0 else None

    eez_poly = load_eez_polygon()
    result: list[tuple[float, float]] = [path[0]]
    i = 0
    while i < len(path) - 1:
        # Walk backwards from the farthest point down to i + 1
        found = False
        for j in range(len(path) - 1, i, -1):
            lat_a, lng_a = path[i]
            lat_b, lng_b = path[j]
            # Must never cross raw land or blocking areas
            if not _segment_clear(lat_a, lng_a, lat_b, lng_b, raw_tree):
                continue
            # For shortcut chords skipping intermediate waypoints, also respect coastal standoff and safe depth
            if j > i + 1:
                if standoff_tree is not None and not _segment_clear(lat_a, lng_a, lat_b, lng_b, standoff_tree):
                    continue
                # Ensure shortcut chords between points in Indian waters do not cut outside Indian EEZ
                if eez_poly is not None:
                    pt_a = Point(lng_a, lat_a)
                    pt_b = Point(lng_b, lat_b)
                    if eez_poly.contains(pt_a) and eez_poly.contains(pt_b):
                        outside_eez = False
                        for frac in (0.25, 0.5, 0.75):
                            s_lat = lat_a + frac * (lat_b - lat_a)
                            s_lng = lng_a + frac * (lng_b - lng_a)
                            if not eez_poly.contains(Point(s_lng, s_lat)):
                                outside_eez = True
                                break
                        if outside_eez:
                            continue
                # Depth clearance check along shortcut chord (avoid shallow sandbars and headland reefs)
                shallow_chord = False
                for frac in (0.25, 0.5, 0.75):
                    s_lat = lat_a + frac * (lat_b - lat_a)
                    s_lng = lng_a + frac * (lng_b - lng_a)
                    dp = depth_at_point(s_lat, s_lng)
                    if dp.on_land or (dp.depth_m is not None and dp.depth_m < 5.0):
                        shallow_chord = True
                        break
                if shallow_chord:
                    continue
            result.append(path[j])
            i = j
            found = True
            break
        if not found:
            result.append(path[i + 1])
            i += 1

    # Ensure the exact end point is in the result.
    if result[-1] != path[-1]:
        result.append(path[-1])

    return result
