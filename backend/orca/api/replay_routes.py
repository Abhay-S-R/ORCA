"""HTTP surface for the Cyclone Gaja historical replay (parent plan §1.3,
phase4 plan §3). A separate APIRouter, same pattern as geospatial_routes.py,
so this doesn't collide with main.py's graph/SSE work.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orca.replay.gaja import replay_payload

router = APIRouter(prefix="/api/replay", tags=["replay"])


@router.get("/gaja")
def gaja_replay() -> dict:
    try:
        return replay_payload()
    except FileNotFoundError as exc:
        # The parent plan's own contingency (§1.3): if the procured dataset
        # is ever missing on a given machine, this is a labelled 404, never
        # a silently invented replay.
        raise HTTPException(status_code=404, detail=f"Gaja replay data not found: {exc}") from exc
