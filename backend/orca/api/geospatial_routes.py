"""HTTP surface for Agent 6 (Geospatial) — plan §4 S5. A separate APIRouter,
included from `main.py` with one line, so this slice's endpoints don't
collide with S1's graph/SSE work in that file.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from orca.agents.geospatial import (
    bearing_and_distance,
    check_boundary_proximity,
    depth_at_point,
    generate_map_layers,
    point_in_polygon,
    spatial_query_zones,
)

router = APIRouter(prefix="/api", tags=["geospatial"])


def _feature_summary(f) -> dict:
    return {"name": f.name, "designation": f.designation, "geofence_usable": f.geofence_usable}


@router.get("/map-layers")
def map_layers(lat: float | None = None, lon: float | None = None) -> dict:
    return generate_map_layers(user_lat=lat, user_lon=lon)


@router.get("/boundary-proximity")
def boundary_proximity(lat: float, lon: float, boundary_name: str) -> dict:
    try:
        result = check_boundary_proximity(lat, lon, boundary_name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return asdict(result)


@router.get("/point-in-polygon")
def point_in_polygon_route(lat: float, lon: float) -> dict:
    return {"boundaries": [_feature_summary(f) for f in point_in_polygon(lat, lon)]}


@router.get("/depth")
def depth(lat: float, lon: float) -> dict:
    return asdict(depth_at_point(lat, lon))


@router.get("/bearing")
def bearing(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    bearing_deg, distance_nm = bearing_and_distance(from_lat, from_lon, to_lat, to_lon)
    return {"bearing_deg": bearing_deg, "distance_nm": distance_nm}


@router.get("/zones-nearby")
def zones_nearby(lat: float, lon: float, radius_nm: float = 25.0) -> dict:
    return {"boundaries": [_feature_summary(f) for f in spatial_query_zones(lat, lon, radius_nm)]}
