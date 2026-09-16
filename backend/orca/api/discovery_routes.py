"""HTTP surface for Agent 3 (Discovery) — plan §4 S4. A separate APIRouter,
included from `main.py` with one line, so this slice's endpoints don't
collide with S1's graph/SSE work in that file.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from orca.agents.discovery import (
    FALLBACK_CASCADES,
    SOURCE_REGISTRY,
    local_catalog,
    select_source_with_fallback,
)

router = APIRouter(prefix="/api", tags=["discovery"])


@router.get("/sources")
def list_sources(data_type: str | None = None, down: str | None = None) -> dict:
    """Full catalog, or — with `data_type` — Agent 3's cascade-aware pick and
    its comparison narrative. `down` is a comma-separated list of source ids
    to treat as unavailable (exercises the §12.1 fallback chain).

    `/zones` moved to analytics_routes (Phase 2 D2 owns that surface).
    """
    if data_type is None:
        return {
            "sources": [
                {
                    **s.__dict__,
                    "fallback_chain": list(FALLBACK_CASCADES.get(s.id, ())),
                    # Index-only sources (NASA CMR granules, Bhuvan WMS
                    # services) ship what ORCA can name locally; an empty list
                    # means no local index, not an empty source.
                    "local_catalog": local_catalog(s.id),
                }
                for s in SOURCE_REGISTRY
            ]
        }
    down_ids = tuple(x.strip() for x in down.split(",") if x.strip()) if down else ()
    decision = select_source_with_fallback(data_type, down=down_ids)
    if decision is None:
        raise HTTPException(404, f"No source covers data_type={data_type!r}")
    return {
        "source": decision.chosen.__dict__,
        "local_catalog": local_catalog(decision.chosen.id),
        "reason": decision.narrative,
        "considered": [s.id for s in decision.considered],
        "fallback_chain": list(decision.fallback_chain),
    }
