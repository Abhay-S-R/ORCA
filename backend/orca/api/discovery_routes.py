"""HTTP surface for Agent 3 (Discovery) — plan §4 S4. A separate APIRouter,
included from `main.py` with one line, so this slice's endpoints don't
collide with S1's graph/SSE work in that file.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orca.agents.discovery import SOURCE_REGISTRY, load_pfz_advisories, select_best_source

router = APIRouter(prefix="/api", tags=["discovery"])


@router.get("/sources")
def list_sources(data_type: str | None = None) -> dict:
    if data_type is None:
        return {"sources": [s.__dict__ for s in SOURCE_REGISTRY]}
    picked = select_best_source(data_type)
    if picked is None:
        raise HTTPException(404, f"No source covers data_type={data_type!r}")
    return {"source": picked.source.__dict__, "reason": picked.reason}


@router.get("/zones")
def zones() -> dict:
    return load_pfz_advisories()
