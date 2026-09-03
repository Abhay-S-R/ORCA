"""FastAPI app. /query runs the full LangGraph pipeline — Agents 1, 2, 4, 6,
7, 9, 12, and the graph itself. S4/S5's Agent 3/6 surfaces are additionally
mounted as separate routers below for direct map/zone queries outside the
main graph. See orca/graph/graph.py for the exact node wiring.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from orca.agents import distress as distress_agent
from orca.agents.geospatial import DATA_ROOT
from orca.agents.language import IndicTrans2Backend, register_translation_backend
from orca.api.auth_routes import router as auth_router
from orca.api.discovery_routes import router as discovery_router
from orca.api.geospatial_routes import router as geospatial_router
from orca.data.loaders import resolve_port_from_text
from orca.graph.graph import build_graph
from orca.state import ORCAState


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Registered once at startup, not per-request — IndicTrans2Backend loads
    # its models lazily on first actual translate() call, so this itself is
    # cheap; the first Tamil/Hindi query after a cold start pays the model
    # load cost, not every query.
    register_translation_backend(IndicTrans2Backend())
    yield


app = FastAPI(title="ORCA API", lifespan=_lifespan)

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
app.include_router(auth_router)

# Agent 8 raster tile pyramid (orca/tiles.py) — serves the PNGs
# scripts/generate_tiles.py writes offline, at the same "/tiles/{layer_id}/
# {z}/{x}/{y}.png" path each meta.json's tile_url_template already assumes.
# Guarded, not unconditional: a fresh checkout has no data/tier1/tiles until
# that script has been run once, and StaticFiles raises on a missing dir.
_TILES_DIR = DATA_ROOT / "tier1" / "tiles"
if _TILES_DIR.is_dir():
    app.mount("/tiles", StaticFiles(directory=_TILES_DIR), name="tiles")

# Compiled once at import time — a LangGraph StateGraph is stateless
# structure; compiling per-request would just waste cycles on every call.
_graph = build_graph()

# Thoothukudi — the pilot region's own default per the Phase 1 acceptance
# query, used only when the caller doesn't supply a real position.
_DEFAULT_LAT, _DEFAULT_LON = 8.80, 78.14


def _initial_state(query: str, lat: float, lon: float, vessel_class: str | None, distress: bool = False) -> ORCAState:
    return {  # type: ignore[typeddict-item]
        "query_id": str(uuid.uuid4()),
        "raw_user_query": query,
        # Overwritten by language_ingress_node once the graph runs — this is
        # only the value used if that node is somehow skipped.
        "normalized_english_query": query,
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": lat, "lon": lon},
        "vessel_class": vessel_class,  # None -> risk_assessment.run() defaults to "small_fishing"
        # True when the SOS control was tapped: Agent 12 treats an explicit
        # control as sufficient on its own, with no text needed, and the
        # graph then routes straight to END (Architecture §3.2 step 1).
        "distress_flag": distress,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _query_stream(query: str, lat: float, lon: float, vessel_class: str | None, distress: bool = False) -> AsyncIterator[str]:
    state = _initial_state(query, lat, lon, vessel_class, distress)
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
        weather = final_state.get("weather_data") or {}
        hourly = weather.get("hourly") or [{}]
        geo = final_state.get("geospatial_data") or {}
        # A distress response has no vernacular translation pass (it bypasses
        # Reporting/language_egress entirely) — final_vernacular_response
        # falls back to the English text in that case, never a blank string.
        final = {
            "type": "final_response",
            "query_id": final_state.get("query_id"),
            "final_english_response": final_state.get("final_english_response", ""),
            "final_vernacular_response": final_state.get("final_vernacular_response")
            or final_state.get("final_english_response", ""),
            "detected_language": final_state.get("detected_language", "en"),
            "confidence_tier": final_state.get("confidence_tier", "LOW_DATA"),
            "risk_assessment": final_state.get("risk_assessment"),
            "citations": final_state.get("evidence_citations", []),
            "distress_flag": final_state.get("distress_flag", False),
            # Structured alongside the sentence, so the UI can render a
            # dialable number rather than asking someone in a boat to
            # retype one out of a paragraph. Pure dict lookup — recomputing
            # it here costs nothing and keeps the frozen ORCAState frozen.
            "mrcc_contact": (
                distress_agent.surface_mrcc_contact(final_state.get("user_location"))
                if final_state.get("distress_flag", False)
                else None
            ),
            # Raw values for /safety's gauges — the verdict answers "is it
            # safe", these answer "why", which a vessel-class-aware page
            # needs to show, not just the badge.
            "weather_summary": {
                "wave_height_m": hourly[0].get("wave_height"),
                "wind_speed_ms": hourly[0].get("wind_speed_10m"),
                "lightning_active": weather.get("lightning_active", False),
                "cyclone_alert": weather.get("cyclone_alert"),
            },
            # Exit criterion 7 is "audit_trace_log captures every agent
            # hand-off, verified by log inspection" — with no Postgres in
            # Phase 1 the log lives only in state, so it ships with the
            # response or it cannot be inspected at all.
            "audit_trace_log": final_state.get("audit_trace_log", []),
            "hazard_breakdown": {
                "imbl_distance_nm": geo.get("imbl_distance_nm"),
                "imbl_alert_level": geo.get("imbl_alert_level"),
                "mpa_violation": geo.get("mpa_violation", False),
                "mpa_alert_level": geo.get("mpa_alert_level"),
            },
            # Agent 8 (Phase 2 D3) — map_layers/chart_specs, already
            # validate_payload-clean plain dicts (graph.py's visualization_node).
            "visualization_payload": final_state.get("visualization_payload"),
        }
        _persist_audit_trace_log(final_state.get("query_id", ""), final_state.get("audit_trace_log", []))
        yield f"data: {json.dumps(final)}\n\n"


def _persist_audit_trace_log(query_id: str, entries: list[dict]) -> None:
    """Exit criterion 7 (Phase 2 plan §3): rows land in Postgres, not just
    ORCAState. Best-effort — a DB outage degrades to Phase-1 behaviour
    (in-memory only, shipped with the SSE response above) rather than
    failing the user-facing request; the trace itself already reached the
    client either way."""
    if not entries:
        return
    try:
        from orca.db.engine import get_sessionmaker
        from orca.db.repositories import persist_trace_entries

        db = get_sessionmaker()()
        try:
            persist_trace_entries(db, query_id=query_id, session_id=None, entries=entries)
        finally:
            db.close()
    except Exception:  # noqa: BLE001, S110 — same exception-boundary rule as trace.py; a DB
        # outage here must never fail the request, and there is nothing more to do
        # than degrade to Phase-1 behaviour (the trace already shipped in the SSE body).
        pass


@app.get("/query")
async def query(
    q: str = "", lat: float | None = None, lon: float | None = None, vessel_class: str | None = None,
    distress: bool = False,
) -> StreamingResponse:
    # An explicit lat/lon from the caller always wins — a resolved GPS fix or
    # a registered home port (Phase 2 D1) is real; a port name in free text is
    # a fallback for the caller that has no location at all yet. Only when
    # neither is given do we try to name a pilot port in the query text (e.g.
    # "near Pamban"), and only then fall back to the Thoothukudi default.
    if lat is None or lon is None:
        resolved = resolve_port_from_text(q)
        lat = resolved[1] if resolved else _DEFAULT_LAT
        lon = resolved[2] if resolved else _DEFAULT_LON
    return StreamingResponse(_query_stream(q, lat, lon, vessel_class, distress), media_type="text/event-stream")
