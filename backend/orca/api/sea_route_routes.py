"""HTTP surface for the Sea Route Voyage feature.

Same single-router, one-line-mount pattern as voyage_routes.py /
geospatial_routes.py.  All endpoints live under /api to match the
existing convention (APIRouter prefix="/api").

POST /api/sea-route
GET  /api/sea-route/ports
GET  /api/sea-route/fishing-zones   (GeoJSON FeatureCollection)
GET  /api/sea-route/restricted-areas (GeoJSON FeatureCollection)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orca.api.params import LatField, LonField
from orca.sea_route.config import DEFAULT_CONFIG
from orca.sea_route.datasets import (
    load_fishing_zones,
    load_protected_areas,
    load_restricted_areas,
)
from orca.sea_route.ports_service import get_port, list_ports
from orca.sea_route.router import sea_route
from orca.sea_route.zones_service import get_zone, zone_entry_point

log = logging.getLogger("orca.api.sea_route")

router = APIRouter(prefix="/api", tags=["sea-route"])

# ── India bbox for map-pick validation ───────────────────────────────────────
_BBOX_W, _BBOX_E, _BBOX_S, _BBOX_N = 66.0, 95.0, 5.0, 24.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Request / Response models ─────────────────────────────────────────────────

class SeaRouteRequest(BaseModel):
    """Unified routing request for all three modes."""
    mode: Literal["port_to_port", "port_to_zone", "map_pick"]

    # port_to_port / port_to_zone: set port_from (required) and port_to or zone_id.
    port_from: str | None = None
    port_to: str | None = None
    zone_id: str | None = None

    # map_pick: set from_lat/from_lng/to_lat/to_lng explicitly.
    from_lat: LatField | None = None
    from_lng: LonField | None = None
    to_lat: LatField | None = None
    to_lng: LonField | None = None

    speed_knots: float = Field(default=8.0, gt=0, le=50)
    departure: str | None = None  # ISO-8601; None → now


class SeaRouteResponse(BaseModel):
    coords: list[list[float]]      # [[lat, lng], …]
    distance_nm: float
    distance_km: float
    hours: float
    eta: str
    warnings: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_endpoints(req: SeaRouteRequest) -> tuple[float, float, float, float]:
    """Return (start_lat, start_lng, end_lat, end_lng) for any mode."""
    if req.mode == "port_to_port":
        if not req.port_from or not req.port_to:
            raise HTTPException(400, "port_to_port mode requires port_from and port_to")
        p_from = get_port(req.port_from)
        p_to = get_port(req.port_to)
        if p_from is None:
            raise HTTPException(404, f"Port not found: {req.port_from}")
        if p_to is None:
            raise HTTPException(404, f"Port not found: {req.port_to}")
        return p_from.lat, p_from.lng, p_to.lat, p_to.lng

    if req.mode == "port_to_zone":
        if not req.port_from or not req.zone_id:
            raise HTTPException(400, "port_to_zone mode requires port_from and zone_id")
        port = get_port(req.port_from)
        zone = get_zone(req.zone_id)
        if port is None:
            raise HTTPException(404, f"Port not found: {req.port_from}")
        if zone is None:
            raise HTTPException(404, f"Fishing zone not found: {req.zone_id}")
        entry_lat, entry_lng = zone_entry_point(zone, port.lat, port.lng)
        return port.lat, port.lng, entry_lat, entry_lng

    if req.mode == "map_pick":
        for field, val in [
            ("from_lat", req.from_lat), ("from_lng", req.from_lng),
            ("to_lat", req.to_lat), ("to_lng", req.to_lng),
        ]:
            if val is None:
                raise HTTPException(400, f"map_pick mode requires {field}")
        # Bounds check — friendly messages matching the spec.
        for label, lat, lng in [("start", req.from_lat, req.from_lng), ("end", req.to_lat, req.to_lng)]:
            if not (_BBOX_S <= lat <= _BBOX_N and _BBOX_W <= lng <= _BBOX_E):  # type: ignore[operator]
                raise HTTPException(400, "Please select a point within Indian waters")
        return req.from_lat, req.from_lng, req.to_lat, req.to_lng  # type: ignore[return-value]

    raise HTTPException(400, f"Unknown mode: {req.mode}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sea-route", response_model=SeaRouteResponse)
def compute_sea_route(req: SeaRouteRequest) -> SeaRouteResponse:
    """Calculate a realistic sea route that follows the real Indian coastline."""
    start_lat, start_lng, end_lat, end_lng = _resolve_endpoints(req)
    departure_iso = req.departure or _now_iso()

    try:
        result = sea_route(
            start_lat, start_lng, end_lat, end_lng,
            speed_knots=req.speed_knots,
            departure_iso=departure_iso,
            cfg=DEFAULT_CONFIG,
            is_map_pick=(req.mode == "map_pick"),
        )
    except ValueError as exc:
        msg = str(exc)
        # Map domain errors to appropriate HTTP status codes.
        if "on land" in msg:
            raise HTTPException(422, msg) from exc
        if "within Indian waters" in msg or "bbox" in msg:
            raise HTTPException(422, msg) from exc
        if "restricted area" in msg:
            raise HTTPException(422, msg) from exc
        if "No sea route found" in msg:
            raise HTTPException(422, msg) from exc
        raise HTTPException(400, msg) from exc
    except Exception as exc:
        log.exception("sea_route computation failed")
        raise HTTPException(500, "Internal routing error") from exc

    return SeaRouteResponse(
        coords=[[lat, lng] for lat, lng in result.coords],
        distance_nm=result.distance_nm,
        distance_km=result.distance_km,
        hours=result.hours,
        eta=result.eta,
        warnings=result.warnings,
    )


@router.get("/sea-route/ports")
def sea_route_ports() -> dict:
    """List all seaports and fishing harbours in the India dataset."""
    ports = list_ports()
    return {
        "ports": [
            {
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "type": p.type,
                "state": p.state,
                "lat": p.lat,
                "lng": p.lng,
            }
            for p in ports
        ]
    }


@router.get("/sea-route/fishing-zones")
def sea_route_fishing_zones() -> dict:
    """Return fishing zones as a GeoJSON FeatureCollection."""
    from shapely import to_geojson as _to_geojson
    zones = load_fishing_zones()
    features = []
    for z in zones:
        encoded = _to_geojson(z.geometry)
        if encoded is None:
            continue
        try:
            geom_dict = json.loads(encoded)
        except Exception:
            continue
        features.append({
            "type": "Feature",
            "geometry": geom_dict,
            "properties": {
                "id": z.id,
                "name": z.name,
                "entry_lat": z.entry_lat,
                "entry_lng": z.entry_lng,
                **{k: v for k, v in z.properties.items()
                   if k not in ("id", "name", "entry_lat", "entry_lng")},
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/sea-route/restricted-areas")
def sea_route_restricted_areas() -> dict:
    """Return restricted areas as a GeoJSON FeatureCollection.

    PLACEHOLDER — geometry derived from Marine Regions VLIZ data.
    Replace with official IMBL data for operational use.
    """
    from shapely import to_geojson as _to_geojson
    areas = list(load_restricted_areas()) + list(load_protected_areas())
    features = []
    for a in areas:
        encoded = _to_geojson(a.geometry)
        if encoded is None:
            continue
        try:
            geom_dict = json.loads(encoded)
        except Exception:
            continue
        features.append({
            "type": "Feature",
            "geometry": geom_dict,
            "properties": {
                "id": a.id,
                "name": a.name,
                "mode": a.mode,
                "note": a.note,
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "note": "PLACEHOLDER — maritime boundary data. Replace with official IMBL data.",
    }
