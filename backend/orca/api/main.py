"""FastAPI app. /query runs the full LangGraph pipeline — Agents 1, 2, 4, 6,
7, 9, 12, and the graph itself. S4/S5's Agent 3/6 surfaces are additionally
mounted as separate routers below for direct map/zone queries outside the
main graph. See orca/graph/graph.py for the exact node wiring.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from orca.agents import distress as distress_agent
from orca.agents.geospatial import DATA_ROOT
from orca.agents.language import IndicTrans2Backend, register_translation_backend
from orca.api.analytics_routes import router as analytics_router
from orca.api.auth_routes import router as auth_router
from orca.api.discovery_routes import router as discovery_router
from orca.api.feedback_routes import router as feedback_router
from orca.api.geospatial_routes import router as geospatial_router
from orca.api.notifications_routes import router as notifications_router
from orca.api.ops_routes import router as ops_router
from orca.api.replay_routes import router as replay_router
from orca.api.trace_routes import router as trace_router
from orca.api.voice_routes import router as voice_router
from orca.api.voyage_routes import router as voyage_router
from orca.api.watches_routes import router as watches_router
from orca.data.loaders import resolve_port_from_text
from orca.graph.graph import build_graph
from orca.agents.planning import classify_intent
from orca.logging_utils import configure_logging
from orca.query_cache import get as query_cache_get
from orca.query_cache import resolved_key
from orca.query_cache import store as query_cache_store
from orca.query_coalescing import coalesce
from orca.state import ORCAState


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Log redaction ahead of the formatter (plan §5.4 Day 10) — configured
    # once here, before any request can log a coordinate or identity value.
    configure_logging()
    # Registered once at startup, not per-request — IndicTrans2Backend loads
    # its models lazily on first actual translate() call, so this itself is
    # cheap; the first Tamil/Hindi query after a cold start pays the model
    # load cost, not every query.
    register_translation_backend(IndicTrans2Backend())
    # Agent 11 (Sentinel, Phase 3 D2) — an in-process asyncio poll loop,
    # single-instance via a Postgres advisory lock. Disabled with
    # ORCA_SENTINEL_ENABLED=0; a DB outage degrades it to a no-op tick, never
    # blocks startup.
    _stop_sentinel = None
    try:
        from orca.sentinel_runtime import start_sentinel, stop_sentinel

        start_sentinel()
        _stop_sentinel = stop_sentinel
    except Exception:  # Sentinel must never block the API coming up
        import logging

        logging.getLogger("orca.sentinel").warning("sentinel failed to start", exc_info=True)
    yield
    if _stop_sentinel is not None:
        await _stop_sentinel()


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
app.include_router(auth_router)  # D1 — /register, /login, /profile, /vessels (Phase 2 D1)
app.include_router(analytics_router)  # Agent 5 — /zones, /trends, /tides, /data (Phase 2 D2)
app.include_router(voyage_router)  # D3 — /voyage-plan, /wind-vectors already mounted via geospatial_router
app.include_router(trace_router)  # D1 Phase 3 — /trace/{query_id} replay, /render persona re-render
app.include_router(voice_router)  # D1 Phase 3 Day 16-17 — /voice/transcribe, /voice/speak

# Phase 3 D2 — Sentinel / alerting / feedback / district ops. Same one-line
# include pattern; none collide with /query or the routers above (checked).
app.include_router(watches_router)
app.include_router(notifications_router)
app.include_router(feedback_router)
app.include_router(ops_router)
app.include_router(replay_router)  # Phase 4 — /api/replay/gaja, historical replay (parent plan §1.3)

# Agent 8 raster tile pyramid (orca/tiles.py) — serves the PNGs
# scripts/generate_tiles.py writes offline, at the same "/tiles/{layer_id}/
# {z}/{x}/{y}.png" path each meta.json's tile_url_template already assumes.
# Guarded, not unconditional: a fresh checkout has no data/tier1/tiles until
# that script has been run once, and StaticFiles raises on a missing dir.
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


_TILES_DIR = DATA_ROOT / "tier1" / "tiles"
if _TILES_DIR.is_dir():
    app.mount("/tiles", NoCacheStaticFiles(directory=_TILES_DIR), name="tiles")

# Compiled once at import time — a LangGraph StateGraph is stateless
# structure; compiling per-request would just waste cycles on every call.
_graph = build_graph()

# Thoothukudi — the pilot region's own default per the Phase 1 acceptance
# query, used only when the caller doesn't supply a real position.
_DEFAULT_LAT, _DEFAULT_LON = 8.80, 78.14

# Priority lane / backpressure (Architecture §9.10, phase4 plan §8) — a
# resource-guaranteed concurrency budget for SAFETY_CHECK/SHALLOW requests
# (the exact shape of what a scared fisherman asks during a cyclone),
# separate from a smaller budget for everything else, so a hazard-window
# demand spike cannot starve the highest-stakes queries. Two independent
# asyncio.Semaphore pools (stdlib, no queue broker) rather than one shared
# pool: standard-lane traffic can never contend for a priority-lane slot,
# which is what "resource-guaranteed" actually requires.
PRIORITY_LANE = asyncio.Semaphore(int(os.environ.get("ORCA_PRIORITY_LANE_SIZE", "8")))
STANDARD_LANE = asyncio.Semaphore(int(os.environ.get("ORCA_STANDARD_LANE_SIZE", "4")))


def _is_priority_shaped(query: str, depth: str | None) -> bool:
    """Cheap pre-classification at the route layer — reuses Agent 2's own
    Tier-1 rules match (classify_intent) rather than a second classifier, so
    "which lane" can never disagree with "which agents actually ran"."""
    if depth not in (None, "SHALLOW"):
        return False
    return any(name == "SAFETY_CHECK" for name, _score in classify_intent(query))


_PERSONAS = ("fisherman", "commercial_navigator", "researcher", "coastal_authority")


_DEPTHS = ("SHALLOW", "STANDARD", "DEEP")


def _initial_state(
    query: str, lat: float, lon: float, vessel_class: str | None,
    distress: bool = False, persona: str | None = None, depth: str | None = None,
) -> ORCAState:
    return {  # type: ignore[typeddict-item]
        "query_id": str(uuid.uuid4()),
        "raw_user_query": query,
        # Overwritten by language_ingress_node once the graph runs — this is
        # only the value used if that node is somehow skipped.
        "normalized_english_query": query,
        # A real query-complexity classifier for reasoning_depth is Agent 2's
        # job (plan §9.5's rules-tier routing) and is not built yet — this
        # accepts an explicit override so DEEP-only paths (ocean_analytics'
        # causal diagnosis, the Critic) are reachable and testable via the
        # API today rather than permanently unreachable until that
        # classifier lands. It is a testing knob, not a persona- or
        # intent-routing decision (Ground Rule 1 is untouched by it).
        "reasoning_depth": depth if depth in _DEPTHS else "SHALLOW",
        "user_location": {"lat": lat, "lon": lon},
        "vessel_class": vessel_class,  # None -> risk_assessment.run() defaults to "small_fishing"
        # An explicit persona choice (the selector, or a logged-in user's
        # resolved role — plan §4 D1 Day 10). It is a *resolved value* only:
        # Agent 9 renders with it, no intent classifier ever reads it
        # (Ground Rule 1, CI persona-leak guard).
        "stakeholder_persona": persona if persona in _PERSONAS else "fisherman",
        "stakeholder_persona_source": "explicit" if persona in _PERSONAS else "inferred_low",
        # True when the SOS control was tapped: Agent 12 treats an explicit
        # control as sufficient on its own, with no text needed, and the
        # graph then routes straight to END (Architecture §3.2 step 1).
        "distress_flag": distress,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _query_stream(
    query: str, lat: float, lon: float, vessel_class: str | None,
    distress: bool = False, persona: str | None = None, depth: str | None = None,
    on_final: Callable[[dict], None] | None = None,
) -> AsyncIterator[str]:
    """`on_final`, when given, is called once with the same dict that gets
    JSON-serialized into the `final_response` SSE frame — the query-cache
    write hook (phase4 plan §2.3), kept as a callback rather than a return
    value so this stays a plain generator callers can iterate directly."""
    state = _initial_state(query, lat, lon, vessel_class, distress, persona, depth)
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
        ocean = final_state.get("ocean_data") or {}
        discovery = final_state.get("discovery_data") or {}
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
            # Cost-based short-circuit (Architecture §9.3, phase4 plan §2.1):
            # true when a NO_GO verdict caused Ocean Analytics' PFZ/tide/trend
            # content to be dropped from this response rather than shown
            # alongside a "don't go" verdict nobody asked for more data under.
            "early_exit_triggered": final_state.get("early_exit_triggered", False),
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
            # Agent 5 (Phase 2 D2) — tide / nearest-PFZ / sector status / the
            # DEEP catch-decline diagnosis, for a card that shows the ocean
            # facts behind the verdict, not just the badge.
            "ocean_summary": {
                "tide": ocean.get("tide"),
                "nearest_pfz": ocean.get("nearest_pfz"),
                "sector_status": ocean.get("sector_status"),
                "productivity_diagnosis": ocean.get("productivity_diagnosis"),
            },
            # Agent 3's source-selection narratives (differentiator 4) — on
            # the answer card and the activity strip, not buried in the trace.
            "source_selections": discovery.get("source_selections", []),
        }
        _persist_audit_trace_log(final_state.get("query_id", ""), final_state.get("audit_trace_log", []))
        if on_final is not None:
            on_final(final)
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
    distress: bool = False, persona: str | None = None, depth: str | None = None,
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

    # A distress query is never cached or coalesced onto another in-flight
    # request (phase4 plan §2.2/§2.3) — every SOS is its own, always-fresh
    # invocation. Ground Rule 2's safety-path discipline applies to the
    # request-handling layer too: a second, real emergency call must never
    # be silently folded into a stale answer meant for a different call.
    if distress:
        return StreamingResponse(
            _query_stream(q, lat, lon, vessel_class, distress, persona, depth), media_type="text/event-stream"
        )

    cache_key = resolved_key(q, lat, lon, vessel_class, persona, depth)
    lane = PRIORITY_LANE if _is_priority_shaped(q, depth) else STANDARD_LANE

    async def _produce() -> AsyncIterator[str]:
        cached = query_cache_get(cache_key)
        if cached is not None:
            yield f"data: {json.dumps(cached)}\n\n"
            return
        async with lane:
            async for line in _query_stream(
                q, lat, lon, vessel_class, distress, persona, depth,
                on_final=lambda final: query_cache_store(cache_key, final),
            ):
                yield line

    return StreamingResponse(coalesce(cache_key, _produce), media_type="text/event-stream")
