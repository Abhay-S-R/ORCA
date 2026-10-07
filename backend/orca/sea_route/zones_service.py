"""Fishing zone service: list zones and compute entry points.

If a zone has an explicit entry_lat/entry_lng those are used directly.
Otherwise the entry point is the point on the zone boundary nearest to
the supplied reference position (the selected port).
"""
from __future__ import annotations

import math

from shapely.geometry import Point
from shapely.ops import nearest_points

from orca.sea_route.datasets import FishingZone, load_fishing_zones


def list_zones() -> tuple[FishingZone, ...]:
    return load_fishing_zones()


def get_zone(zone_id: str) -> FishingZone | None:
    for z in load_fishing_zones():
        if z.id == zone_id:
            return z
    return None


def zone_entry_point(
    zone: FishingZone,
    from_lat: float,
    from_lng: float,
) -> tuple[float, float]:
    """Return (lat, lng) of the zone entry point nearest to (from_lat, from_lng).

    Prefers the zone's explicit entry_lat/entry_lng if present.
    Falls back to the nearest point on the zone boundary.
    """
    if zone.entry_lat is not None and zone.entry_lng is not None:
        return zone.entry_lat, zone.entry_lng

    # Nearest point on boundary.
    origin = Point(from_lng, from_lat)
    boundary = zone.geometry.boundary if zone.geometry.geom_type != "Point" else zone.geometry
    p1, _ = nearest_points(boundary, origin)
    return p1.y, p1.x  # (lat, lng)
