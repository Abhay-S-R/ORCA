"""Fishing Zone Profit API routes.

GET /api/fishing-profit
  ?lat=<float>&lon=<float>&vessel=<vessel_key>

Returns pre-calculated profit estimates for fishing zones near the user's
home port, tailored to their vessel type.

Plan refs: §8 (home-port filtering), §9 (vessel behaviour), §11 (pre-calculation).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from orca.auth.rbac import get_optional_user
from orca.db.engine import get_db
from orca.db.models import User
from orca.db.repositories import get_vessel_for_owner, user_home_port
from orca.fishing_profit import (
    DB_VESSEL_TO_PROFIT_KEY,
    get_all_ports,
    get_all_zones,
    get_zone_profits,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fishing-profit"])

# Default position when neither the user nor the caller supplies one
# (south-west tip of Kerala / Trivandrum coast).
_DEFAULT_LAT = 8.50
_DEFAULT_LON = 76.95


@router.get("/api/fishing-profit")
async def fishing_profit(
    lat: float | None = Query(default=None, description="Home port latitude"),
    lon: float | None = Query(default=None, description="Home port longitude"),
    vessel: str | None = Query(default=None, description="Vessel class key (optional override)"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> JSONResponse:
    """Return profit estimates for fishing zones near the user's home port.

    Priority for position:
      1. Explicit lat/lon query params (caller override)
      2. User's registered home port (if signed in)
      3. Default position

    Priority for vessel:
      1. Explicit `vessel` param
      2. User's active vessel class (if signed in and vessel registered)
      3. Default → "small_fishing"
    """
    # ── 1. Resolve position ─────────────────────────────────────────────────
    if lat is not None and lon is not None:
        port_lat, port_lon = lat, lon
    elif current_user is not None:
        hp = user_home_port(current_user)
        if hp:
            port_lat, port_lon = hp["lat"], hp["lon"]
        else:
            port_lat, port_lon = _DEFAULT_LAT, _DEFAULT_LON
    else:
        port_lat, port_lon = _DEFAULT_LAT, _DEFAULT_LON

    # ── 2. Resolve vessel ────────────────────────────────────────────────────
    vessel_key = vessel  # may be None or an explicit override

    if vessel_key is None and current_user is not None and current_user.active_vessel_id is not None:
        vessel_row = get_vessel_for_owner(db, current_user.active_vessel_id, current_user.id)
        if vessel_row is not None:
            vessel_key = vessel_row.vessel_class  # DB enum value

    # ── 3. Run the profit engine ─────────────────────────────────────────────
    try:
        result = get_zone_profits(
            port_lat=port_lat,
            port_lon=port_lon,
            vessel_key=vessel_key or "",
            port_name=getattr(current_user, "home_port_name", None) if current_user else None,
        )
        return JSONResponse(content=result)
    except Exception as exc:
        logger.exception("fishing_profit error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Profit calculation unavailable. Please try again later."},
        )


@router.get("/api/fishing-profit/ports")
async def fishing_profit_ports() -> JSONResponse:
    """List of all known home ports."""
    return JSONResponse(content={"ports": get_all_ports()})


@router.get("/api/fishing-profit/zones")
async def fishing_profit_zones() -> JSONResponse:
    """List of all fishing zones (without pre-calculated profit — raw zone data)."""
    return JSONResponse(content={"zones": get_all_zones()})
