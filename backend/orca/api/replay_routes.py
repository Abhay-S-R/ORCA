"""HTTP surface for the Cyclone Gaja historical replay (parent plan §1.3,
phase4 plan §3). A separate APIRouter, same pattern as geospatial_routes.py,
so this doesn't collide with main.py's graph/SSE work.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from orca.replay.gaja import replay_payload
from orca.replay.imbl_crossing import imbl_crossing_track

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/replay", tags=["replay"])


@router.get("/gaja")
def gaja_replay() -> dict:
    try:
        return replay_payload()
    except FileNotFoundError as exc:
        # The parent plan's own contingency (§1.3): if the procured dataset
        # is ever missing on a given machine, this is a labelled 404, never
        # a silently invented replay.
        # `exc` names an absolute server path; that goes to the log, and the
        # caller gets the fact without the filesystem layout.
        _log.warning("Gaja replay data missing: %s", exc)
        raise HTTPException(status_code=404, detail="Gaja replay data not found") from exc


@router.get("/imbl-crossing")
def imbl_crossing() -> dict:
    """P6.7 — Scenario 2's stepped track, computed fresh per request (no
    file I/O, unlike gaja_replay: the boundary geometry is already an
    in-process lru_cache in geospatial.py)."""
    return imbl_crossing_track()
