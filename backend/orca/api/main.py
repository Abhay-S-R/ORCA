"""FastAPI app. Phase 0 exit criterion: a mock /query SSE stream renders in
the browser (plan §6). Real agent wiring lands in Phase 1 — this endpoint is
scaffolding for the frontend nav shell to point at, not a working answer.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from orca.api.discovery_routes import router as discovery_router
from orca.api.geospatial_routes import router as geospatial_router

app = FastAPI(title="ORCA API")

# ponytail: wide-open CORS for local dev only. Tighten to the deployed
# frontend origin when §5.1 deployment actually happens.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# S4/S5 slice endpoints — separate routers (orca/api/discovery_routes.py,
# orca/api/geospatial_routes.py) so this file stays a one-line touch for them.
app.include_router(discovery_router)
app.include_router(geospatial_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ponytail: agent names hardcoded here for the mock only. Real graph in
# Phase 1 drives this from ORCAState.completed_nodes / execution_plan.
_MOCK_AGENTS = ["planning", "weather_intelligence", "geospatial", "risk_assessment", "reporting"]


async def _mock_query_stream(query: str) -> AsyncIterator[str]:
    query_id = str(uuid.uuid4())
    for agent in _MOCK_AGENTS:
        await asyncio.sleep(0.3)
        event = {"type": "agent_span", "agent_name": agent, "query_id": query_id, "status": "ok"}
        yield f"data: {json.dumps(event)}\n\n"
    final = {
        "type": "final_response",
        "query_id": query_id,
        "final_english_response": f"[mock — Phase 1 wires the real graph] You asked: {query!r}",
        "confidence_tier": "LOW_DATA",
        "timestamp": time.time(),
    }
    yield f"data: {json.dumps(final)}\n\n"


@app.get("/query")
async def query(q: str = "") -> StreamingResponse:
    return StreamingResponse(_mock_query_stream(q), media_type="text/event-stream")
