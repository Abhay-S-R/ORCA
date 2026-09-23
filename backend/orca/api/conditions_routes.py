"""P4.3 (`R-UX-1`) — the one cheap, non-fabricated reading the greeting and
the landing page's live-conditions strip need: today's verdict for a single
position, without paying for a full agent-graph invocation.

Reuses `sentinel.cheap_check` (P0.15's guarded Agent 4 + Agent 7 read) rather
than adding a second threshold path — the greeting can never disagree with
an on-demand `/query` answer for the same position.
"""
from __future__ import annotations

from fastapi import APIRouter

from orca.agents.sentinel import cheap_check
from orca.api.params import Lat, Lon

router = APIRouter(prefix="/api", tags=["conditions"])


@router.get("/quick-conditions")
def quick_conditions(lat: Lat, lon: Lon, vessel_class: str | None = None) -> dict:
    snapshot = cheap_check(lat, lon, vessel_class=vessel_class)
    return snapshot.as_payload()
