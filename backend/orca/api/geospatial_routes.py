"""HTTP surface for Agent 6 (Geospatial) — plan §4 S5. A separate APIRouter,
included from `main.py` with one line, so this slice's endpoints don't
collide with S1's graph/SSE work in that file.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orca.agents.geospatial import (
    DATA_ROOT,
    PILOT_BBOX_WSEN,
    bearing_and_distance,
    check_boundary_proximity,
    current_vectors,
    depth_at_point,
    generate_map_layers,
    point_in_polygon,
    spatial_query_zones,
    wind_vectors,
)
from orca.agents.visualization import generate_map_layers as agent8_generate_map_layers
from orca.trace import record_layer_metric

router = APIRouter(prefix="/api", tags=["geospatial"])


def _feature_summary(f) -> dict:
    return {"name": f.name, "designation": f.designation, "geofence_usable": f.geofence_usable}


@router.get("/map-layers")
def map_layers(lat: float | None = None, lon: float | None = None, zoom: int = 11) -> dict:
    return generate_map_layers(user_lat=lat, user_lon=lon, zoom=zoom)


@router.get("/raster-layers")
def raster_layers(lat: float | None = None, lon: float | None = None) -> dict:
    """Agent 8's Heatmap/Raster map layers (plan §5.10 Day 13 `/map`
    explorer) — a standalone REST surface, separate from `/map-layers`
    above (Agent 6's own boundaries/position, an older, narrower shape kept
    unchanged for its existing callers). Agent 8 normally only runs inside
    the `/query` SSE graph; its `generate_map_layers(state)` is a pure
    transform of `user_location` (bathymetry/tile-pyramid layers need
    nothing else), so a minimal state built here — with no weather/ocean
    data run through the graph — is a legitimate, cheap call, not a
    shortcut around Agent 8's contract.
    """
    state = {"user_location": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None}
    layers = agent8_generate_map_layers(state)  # type: ignore[arg-type]
    return {"layers": [asdict(layer) for layer in layers if layer.layer_type in ("Raster", "Heatmap")]}


@router.get("/current-vectors")
def current_vectors_route(pan_india: bool = True) -> dict:
    """Real HYCOM surface current vectors (plan's revised D3 stack — the
    flow particle layer). Points, not a MapLayer: a vector field the frontend
    turns into an animated flow field client-side."""
    cache_path = DATA_ROOT / "tier1" / "vectors" / "pan_india_currents.json"
    if pan_india and cache_path.exists():
        import json
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"points": current_vectors(), "bounds": list(PILOT_BBOX_WSEN)}


@router.get("/wind-vectors")
def wind_vectors_route(pan_india: bool = True) -> dict:
    """Archived ScatSat 10m wind. NOT live — one snapshot per day —
    so `acquisition_date` ships in the response for the frontend to render
    as an honest freshness label, never silently presented as 'now'."""
    cache_path = DATA_ROOT / "tier1" / "vectors" / "pan_india_wind.json"
    if pan_india and cache_path.exists():
        import json
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return wind_vectors()


class LayerMetricIn(BaseModel):
    layer_id: str
    layer_load_ms: float
    render_ms: float
    payload_bytes: int
    dropped_frames: int


@router.post("/layer-metrics")
def layer_metrics_route(metric: LayerMetricIn) -> dict:
    """§4.7 instrumentation sink — staging half of "console in dev, OTel
    stream in staging". The frontend only calls this outside dev."""
    record_layer_metric(
        metric.layer_id, metric.layer_load_ms, metric.render_ms, metric.payload_bytes, metric.dropped_frames
    )
    return {"ok": True}


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
