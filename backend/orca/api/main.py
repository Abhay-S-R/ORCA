"""FastAPI app. /query runs the real LangGraph pipeline (plan §Phase-1, S1
Day 5) — Agents 2, 4, 7, 12 and the graph itself. S4/S5's Agent 3/6 surfaces
are mounted as separate routers below; Agent 9 (S6) is still the graph's
fixture stub — see orca/graph/graph.py for exactly which nodes that covers.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from orca.api.discovery_routes import router as discovery_router
from orca.api.geospatial_routes import router as geospatial_router
from orca.graph.graph import build_graph
from orca.state import ORCAState

app = FastAPI(title="ORCA API")

# ponytail: wide-open CORS for local dev only. Tighten to the deployed
# frontend origin when §5.1 deployment actually happens.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# S4/S5 slice endpoints — separate routers (orca/api/discovery_routes.py,
# orca/api/geospatial_routes.py) so this file stays a one-line touch for them.
# Both mount under /api and don't collide with /query or /health (checked).
app.include_router(discovery_router)
app.include_router(geospatial_router)

# Compiled once at import time — a LangGraph StateGraph is stateless
# structure; compiling per-request would just waste cycles on every call.
_graph = build_graph()

# Thoothukudi — the pilot region's own default per the Phase 1 acceptance
# query, used only when the caller doesn't supply a real position.
_DEFAULT_LAT, _DEFAULT_LON = 8.80, 78.14


def _initial_state(query: str, lat: float, lon: float) -> ORCAState:
    return {  # type: ignore[typeddict-item]
        "query_id": str(uuid.uuid4()),
        "raw_user_query": query,
        "normalized_english_query": query,  # Agent 1 (S6) not built yet — English-only for now
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": lat, "lon": lon},
        "distress_flag": False,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _query_stream(query: str, lat: float, lon: float) -> AsyncIterator[str]:
    state = _initial_state(query, lat, lon)
    emitted = 0  # every graph node appends exactly one completed_nodes entry
    # AND exactly one audit_trace_log entry in the same call (see graph.py) —
    # so the two lists grow in lockstep and index-pairing them is correct,
    # not a coincidence to be careful of.
    final_state: ORCAState | None = None

    async for values in _graph.astream(state, stream_mode="values"):
        final_state = values
        completed = values.get("completed_nodes", [])
        trace_log = values.get("audit_trace_log", [])
        for node_name, trace_entry in zip(completed[emitted:], trace_log[emitted:]):
            event = {
                "type": "agent_span", "agent_name": node_name, "query_id": values.get("query_id"),
                "status": trace_entry["status"],
            }
            yield f"data: {json.dumps(event)}\n\n"
        emitted = len(completed)

    if final_state is not None:
        final = {
            "type": "final_response",
            "query_id": final_state.get("query_id"),
            "final_english_response": final_state.get("final_english_response", ""),
            "confidence_tier": final_state.get("confidence_tier", "LOW_DATA"),
            "risk_assessment": final_state.get("risk_assessment"),
            "distress_flag": final_state.get("distress_flag", False),
        }
        yield f"data: {json.dumps(final)}\n\n"


@app.get("/query")
async def query(q: str = "", lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> StreamingResponse:
    return StreamingResponse(_query_stream(q, lat, lon), media_type="text/event-stream")
