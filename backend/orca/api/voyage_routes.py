"""HTTP surface for voyage planning (D3, plan §5.1/§6). Separate APIRouter,
same one-line-mount pattern as geospatial_routes.py, so this slice's
endpoint doesn't collide with anything else in main.py.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orca.agents.risk_assessment import VesselClass
from orca.agents.visualization import validate_payload, voyage_route_layer
from orca.agents.voyage import plan_voyage
from orca.api.params import LatField, LonField

router = APIRouter(prefix="/api", tags=["voyage"])


class VoyagePlanRequest(BaseModel):
    origin_lat: LatField
    origin_lon: LonField
    destination_lat: LatField
    destination_lon: LonField
    vessel_class: VesselClass = "small_fishing"
    departure_time: str | None = None  # ISO 8601 UTC; None -> now
    speed_kn: float = Field(default=8.0, gt=0)
    draft_m: float | None = Field(default=None, gt=0)


@router.post("/voyage-plan")
def voyage_plan_route(req: VoyagePlanRequest) -> dict:
    try:
        plan = plan_voyage(
            (req.origin_lat, req.origin_lon), (req.destination_lat, req.destination_lon),
            vessel_class=req.vessel_class, departure_time=req.departure_time,
            speed_kn=req.speed_kn, draft_m=req.draft_m,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Agent 8's mandatory gate (visualization.py) applies here too, same as
    # every other MapLayer this codebase ships — a route layer is not
    # exempt just because it came from a different agent.
    route_layer = voyage_route_layer(plan)
    kept, _, dropped = validate_payload([route_layer], [])
    return {**asdict(plan), "route_layer": asdict(kept[0]) if kept else None, "route_layer_dropped": dropped}
