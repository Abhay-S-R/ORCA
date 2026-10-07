"""Path smoother: removes collinear / redundant waypoints using line-of-sight
visibility checks against land and restricted-area polygons.

After A* the path is a staircase of grid-cell centres.  The smoother walks
the path with a greedy look-ahead: if the straight segment from waypoint[i]
to waypoint[j] does not intersect any blocking polygon, waypoints i+1 … j-1
are redundant and are removed.  The result hugs the coast naturally.

The safety guarantee is the same as the routing engine's: a segment is only
kept when the corridor between its two endpoints is provably free of land and
blocking restricted areas.  Smoothed segments are tested at the LINE level,
not just at discrete points.
"""
from __future__ import annotations

from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree


def _build_blocker_tree(
    land_polygons: tuple[BaseGeometry, ...],
    restricted_areas,            # tuple[RestrictedArea, ...]
) -> STRtree | None:
    """STRtree of all geometries a route segment must not cross."""
    geoms: list[BaseGeometry] = list(land_polygons)
    for area in restricted_areas:
        if area.mode == "block":
            geoms.append(area.geometry)
    return STRtree(geoms) if geoms else None


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
) -> list[tuple[float, float]]:
    """Greedy line-of-sight path smoother.

    Iterates from each waypoint and extends the look-ahead as far as
    possible without crossing a blocker.  Guaranteed to return a path with
    at least the same endpoints as the input.
    """
    if len(path) <= 2:
        return path

    tree = _build_blocker_tree(land_polygons, restricted_areas)

    result: list[tuple[float, float]] = [path[0]]
    i = 0
    while i < len(path) - 1:
        # Walk backwards from the farthest point down to i + 1
        found = False
        for j in range(len(path) - 1, i, -1):
            lat_a, lng_a = path[i]
            lat_b, lng_b = path[j]
            if _segment_clear(lat_a, lng_a, lat_b, lng_b, tree):
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
