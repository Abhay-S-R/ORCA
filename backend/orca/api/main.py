"""FastAPI app. /query runs the full LangGraph pipeline — Agents 1, 2, 4, 6,
7, 9, 12, and the graph itself. S4/S5's Agent 3/6 surfaces are additionally
mounted as separate routers below for direct map/zone queries outside the
main graph. See orca/graph/graph.py for the exact node wiring.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from orca import engines, intent_actions, local_models
from orca import session as session_memory
from orca.agents import distress as distress_agent
from orca.agents import reporting
from orca.agents.geospatial import DATA_ROOT, depth_at_point
from orca.agents.language import (
    english_query,
    query_language,
)
from orca.agents.planning import carry_intent, classify_intent_deterministic
from orca.api.analytics_routes import router as analytics_router
from orca.api.auth_routes import router as auth_router
from orca.api.chats_routes import router as chats_router
from orca.api.conditions_routes import router as conditions_router
from orca.api.discovery_routes import router as discovery_router
from orca.api.feedback_routes import router as feedback_router
from orca.api.geospatial_routes import router as geospatial_router
from orca.api.notifications_routes import router as notifications_router
from orca.api.ops_routes import router as ops_router
from orca.api.params import OptLat, OptLon
from orca.api.replay_routes import router as replay_router
from orca.api.sea_route_routes import router as sea_route_router
from orca.api.system_status_routes import router as system_status_router
from orca.api.trace_routes import (
    _reasoning_summary,
    record_recent_trace,
)
from orca.api.trace_routes import render_query as trace_routes_render_query
from orca.api.trace_routes import (
    router as trace_router,
)
from orca.api.voice_routes import router as voice_router
from orca.api.voyage_routes import router as voyage_router
from orca.api.voyages_routes import router as voyages_router
from orca.api.watches_routes import router as watches_router
from orca.auth.rbac import get_optional_user
from orca.data.loaders import DEFAULT_LAT as _DEFAULT_LAT
from orca.data.loaders import DEFAULT_LON as _DEFAULT_LON
from orca.data.loaders import resolve_all_places_from_text
from orca.db.engine import get_db
from orca.db.models import User
from orca.db.repositories import get_vessel_for_owner, user_home_port
from orca.graph.graph import build_graph
from orca.language_command import match_language_command
from orca.llm.tiers import llm_enabled, reset_llm_call_count, set_llm_override
from orca.logging_utils import (
    bind_query_id,
    configure_logging,
    install_uvicorn_access_filter,
    log_startup_memory,
    start_memory_watchdog,
)
from orca.place_resolution import resolve_or_ask
from orca.profile_prompts import profile_prompt
from orca.query_cache import get as query_cache_get
from orca.query_cache import resolved_key
from orca.query_cache import store as query_cache_store
from orca.query_coalescing import coalesce
from orca.state import ORCAState
from orca.vessel import VESSEL_LABELS, resolve_vessel_class, vessel_named_in


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Log redaction ahead of the formatter (plan §5.4 Day 10) — configured
    # once here, before any request can log a coordinate or identity value.
    configure_logging()
    # Strip query strings (?token=…) from uvicorn's access log so SSE auth
    # tokens never leak to Render's log drain.  Must run after
    # configure_logging (which sets up the root handler) but before any
    # request can arrive.
    install_uvicorn_access_filter()
    # OOM breadcrumb — log RSS + PID so a gap between "started" and the
    # previous log line proves a silent OOM kill (vs. a clean redeploy).
    log_startup_memory()
    # Translation is Bhashini only (decision 2026-10-08): no local translator is registered, loaded or
    # warmed, so a machine without those weights or IndicTransToolkit starts and behaves the same.
    # ORCA_LOCAL_MODELS=0 (orca/local_models.py) skips every warm-up below, and each loader
    # refuses a lazy load too, so a small host never holds these models in memory.
    warmups: list[asyncio.Future] = []
    if local_models.enabled():
        # P6.4 (orca_final §14.3) — pre-warm IndicTrans2 and Whisper now, same
        # fire-and-forget `run_in_executor` shape as the intent-embedding warm-up
        # directly below: a 40s model-load stall on the first Tamil/Hindi query
        # or the first voice query is exactly what destroys a six-minute demo.
        try:
            from orca.agents.voice import warm_faster_whisper, warm_mms_tts

            loop = asyncio.get_running_loop()
            warmups.append(loop.run_in_executor(None, warm_faster_whisper))
            # P6.4 — the local TTS rung was the one warm-up missing (see
            # voice.warm_mms_tts's own docstring): only ASR and translation were
            # pre-warmed before this, leaving the demo's Tamil alert voice to pay
            # a first-synthesis model load on whichever take needed it first.
            warmups.append(loop.run_in_executor(None, warm_mms_tts))
        except Exception:  # warm-up is an optimisation, never a startup dependency
            logging.getLogger("orca.language").warning("model warm-up not started", exc_info=True)
        # P2.8 — load the Tier-2 intent-embedding model now, off the event loop,
        # rather than inside the first user's query. It is optional by
        # construction (see orca/intent_embeddings.py): a machine that cannot
        # download it logs one warning and routes with word overlap, and startup
        # never waits on it.
        try:
            from orca import intent_embeddings

            warmups.append(asyncio.get_running_loop().run_in_executor(None, intent_embeddings.warm))
        except Exception:  # warm-up is an optimisation, never a startup dependency
            logging.getLogger("orca.intent").warning("intent embedding warm-up not started", exc_info=True)
    # FIX-COLD — the first query and the first Play Verdict used to pay one-off setup costs
    # (the Gemini client import and TLS, the Bhashini pipeline-config lookup): measured 9.4 s vs
    # 3.2 s for the first distress check, 5.4 s vs 3.4 s for the first speak. Pay them here.
    warmups.append(asyncio.get_running_loop().run_in_executor(None, _prime_first_request))
    # Marathi, Gujarati and Odia speech have no local backup: find out NOW whether Bhashini is serving them, in
    # the background (a failing language takes 8 s to give up), so the first press of Play already knows.
    asyncio.get_running_loop().run_in_executor(None, _probe_speech_health)
    # Everything above is waited for, so "the server is up" means "the
    # server is fast": a request that arrives while these load competes with them for the CPU
    # (measured: the first distress check took 9.5 s during warm-up and 3.6 s after).
    await _wait_until_warm(warmups)
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
        logging.getLogger("orca.sentinel").warning("sentinel failed to start", exc_info=True)
    # Memory watchdog — log RSS every 60s so there's always a reading within
    # the last minute before a silent Render OOM kill.
    _memory_watchdog_task = None
    try:
        _memory_watchdog_task = await start_memory_watchdog()
    except Exception:
        logging.getLogger("orca.runtime").warning("memory watchdog not started", exc_info=True)
    yield
    # ── Shutdown ──────────────────────────────────────────────────────
    if _memory_watchdog_task is not None:
        _memory_watchdog_task.cancel()
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
app.include_router(chats_router)  # Ask chat history — /api/chats CRUD + /api/session/{id}/context
app.include_router(conditions_router)  # P4.3 — /api/quick-conditions, the greeting's cheap read
app.include_router(analytics_router)  # Agent 5 — /zones, /trends, /tides, /data (Phase 2 D2)
app.include_router(voyage_router)  # D3 — /voyage-plan, /wind-vectors already mounted via geospatial_router
app.include_router(voyages_router)  # P5.20 — /api/voyages: saved passage plans, promotable to a route watch
app.include_router(sea_route_router)  # Sea Route Voyage — /api/sea-route realistic coastal pathfinding
app.include_router(trace_router)  # D1 Phase 3 — /trace/{query_id} replay, /render persona re-render
app.include_router(voice_router)  # D1 Phase 3 Day 16-17 — /voice/transcribe, /voice/speak

# Phase 3 D2 — Sentinel / alerting / feedback / district ops. Same one-line
# include pattern; none collide with /query or the routers above (checked).
app.include_router(watches_router)
app.include_router(notifications_router)
app.include_router(feedback_router)
app.include_router(ops_router)
app.include_router(replay_router)  # Phase 4 — /api/replay/gaja, historical replay (parent plan §1.3)
app.include_router(system_status_router)  # /api/system-status — live/fallback/simulated disclosure

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


def _is_priority_shaped(query: str, depth: str | None, session_history: list[dict] | None = None) -> bool:
    """Cheap pre-classification at the route layer — reuses Agent 2's own
    Tier-1 rules match (classify_intent) rather than a second classifier, so
    "which lane" can never disagree with "which agents actually ran". That
    includes Agent 2's follow-up rule: "what about tomorrow evening?" after a
    safety question runs SAFETY_CHECK, so it gets the safety lane too."""
    if depth not in (None, "SHALLOW"):
        return False
    # Deterministic tiers only (P2.8/P2.11). `classify_intent` can now make a
    # Tier-3 LLM call as a confirmation pass, and this runs in the route layer
    # BEFORE `_query_stream` sets the per-request LLM switch and call counter —
    # so an `llm=off` demo query would still have spent a provider call here,
    # uncounted, which is precisely the claim P2.11 exists to disprove. Which
    # lane a request queues in never needs a paid opinion.
    rows = classify_intent_deterministic(query) or carry_intent(session_history)
    return any(name == "SAFETY_CHECK" for name, _score in rows)


_PERSONAS = ("fisherman", "commercial_navigator", "researcher", "coastal_authority")


_DEPTHS = ("SHALLOW", "STANDARD", "DEEP")


async def _wait_until_warm(warmups: list[asyncio.Future], cap_s: float = 90.0) -> None:
    """FIX-COLD — hold startup until the warm-ups finish, at most `cap_s`. A warm-up that is
    still running at the cap (a slow first download) keeps going in the background; the server
    starts either way."""
    if not warmups:
        return
    started = time.monotonic()
    done, pending = await asyncio.wait(warmups, timeout=cap_s)
    for fut in done:
        fut.exception()  # each warm-up logs its own failure; this only marks it retrieved
    logging.getLogger("orca.startup").info(
        "ORCA ready after %.1fs of warm-up (%d done, %d still loading)", time.monotonic() - started, len(done), len(pending),
    )


def _probe_speech_health() -> None:
    try:
        from orca.agents.voice import probe_speech_health

        probe_speech_health()
    except Exception:
        logging.getLogger("orca.startup").warning("speech health probe skipped", exc_info=True)


def _prime_first_request() -> None:
    """FIX-COLD — one tiny model call and one short synthesis, off the request path, so the
    first real user does not pay the client imports, the TLS handshakes and the Bhashini
    pipeline-config lookup. Every step is best-effort: priming is an optimisation, never a
    startup dependency, and an outage here just means the first user pays as before."""
    log = logging.getLogger("orca.startup")
    try:
        from orca.llm.tiers import llm, llm_enabled

        if llm_enabled():
            llm("cheap").complete([{"role": "user", "content": "Reply with the single word: ready"}])
    except Exception:
        log.warning("model priming skipped", exc_info=True)
    try:
        from orca.agents.voice import text_to_speech

        text_to_speech("ORCA is ready.", "en")
    except Exception:
        log.warning("speech priming skipped", exc_info=True)
    # Bhashini resolves a pipeline config per (task, language) and caches it, so the first Play or
    # the first translated answer in each language paid its own round trip (a user saw ~5 s on the
    # first Play). Resolve them all now; each is a small lookup, no synthesis, and one failing
    # (Bhashini down, not configured) must not stop the others.
    try:
        from orca.agents import bhashini
        from orca.agents.language import _ALL_LANGUAGES

        if bhashini.bhashini_configured():
            for lang in _ALL_LANGUAGES:
                for task, args in (("tts", (lang,)), ("translation", ("en", lang))):
                    if task == "translation" and lang == "en":
                        continue
                    try:
                        bhashini._pipeline_config(task, *args)  # type: ignore[arg-type]
                    except Exception:
                        log.warning("bhashini %s config for %s not primed", task, lang)
    except Exception:
        log.warning("bhashini config priming skipped", exc_info=True)


def _initial_state(
    query: str, lat: float, lon: float, vessel_class: str | None,
    distress: bool = False, persona: str | None = None, depth: str | None = None,
    place: tuple[str | None, str] = (None, "explicit"),
    session_id: str | None = None,
    session_history: list[dict] | None = None,
    resolution: dict | None = None,
    fix_on_land: bool = False,
    user_language_default: str | None = None,
    demo_scenario: str | None = None,
    raw_fix: tuple[float, float] | None = None,
    pretranslated: dict[str, str] | None = None,
) -> ORCAState:
    return {  # type: ignore[typeddict-item]
        "session_id": session_id or "",
        # Last few turns of this chat (checklist P0 #1 — multi-turn memory),
        # read once by query() — Planning continues a follow-up's intent,
        # Agent 9 reads the conversation, and a follow-up with no place of its
        # own was already resolved against the last one this chat actually
        # named (see session.last_place, used by query() before this).
        "session_history": session_history or [],
        "query_id": str(uuid.uuid4()),
        "raw_user_query": query,
        # Overwritten by language_ingress_node once the graph runs. The guards
        # before it (time, self-context) read this, so it starts as query()'s
        # own translation when there is one.
        "normalized_english_query": (pretranslated or {}).get("english", query),
        # P3.1 — a signed-in user's stored language, consulted only when the
        # text itself carries no script signal (see language.run_ingress).
        "user_language_default": user_language_default,
        "pretranslated": pretranslated,
        # A real query-complexity classifier for reasoning_depth is Agent 2's
        # job (plan §9.5's rules-tier routing) and is not built yet — this
        # accepts an explicit override so DEEP-only paths (ocean_analytics'
        # causal diagnosis, the Critic) are reachable and testable via the
        # API today rather than permanently unreachable until that
        # classifier lands. It is a testing knob, not a persona- or
        # intent-routing decision (Ground Rule 1 is untouched by it).
        "reasoning_depth": depth if depth in _DEPTHS else "SHALLOW",
        # `place_name` is None and `place_source` is "regional_default" when
        # the query named no location we could resolve. Agent 9 must say so
        # rather than dress the default up as the user's own place.
        # `fix_on_land` says the browser did send a position and it was
        # discarded for being inland. Without it the default's numbers get
        # narrated as "your nearest fishing zone" to somebody 1,500 km away,
        # and the prompt claims no fix was supplied when one was.
        "user_location": {
            "lat": lat, "lon": lon, "place_name": place[0], "place_source": place[1],
            **({"fix_lat": raw_fix[0], "fix_lon": raw_fix[1]} if raw_fix is not None else {}),
            **({"fix_on_land": True} if fix_on_land else {}),
        },
        "vessel_class": vessel_class,  # None -> risk_assessment.run() defaults to "small_fishing"
        # P6.6 — set only by `/demo`. See orca/demo_fixtures.py and ORCAState's
        # own field comment; None on every ordinary query.
        "demo_scenario": demo_scenario,
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
        # P1.2 — how that position was arrived at, in full: status, candidates
        # and the sentence the card has to show before the answer. The graph's
        # place_guard reads it; nothing downstream may quietly ignore it.
        "place_resolution": resolution,
        "query_outcome": "DISTRESS" if distress else "ANSWERED",
        # Seeded with the place disclosure when there is one, appended to by
        # any node with something else to disclose (operator.add in ORCAState).
        "disclosures": [d] if (d := (resolution or {}).get("disclosure")) and (resolution or {}).get("status") == "fallback" else [],
    }


def _json_safe(obj: Any) -> Any:
    """Non-finite floats are not JSON. json.dumps happily emits a bare `NaN`
    or `Infinity` literal, which no strict parser accepts — including the
    browser's own JSON.parse, which is what the frontend runs on every SSE
    frame (app/ask/page.tsx, app/safety/page.tsx). A single NaN anywhere in
    the payload therefore throws away the whole answer client-side, silently.
    Upstream already treats a non-finite reading as "no reading at all"
    (resilience.conservative_or), so null is the honest wire form of the same
    fact."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _latency_summary(entries: list[dict]) -> dict:
    """P2.10 (`R-NEW-4`) — per-agent latency plus a total.

    The total is the **sum of the spans**, not wall-clock: three specialists
    run in parallel, so summing them overstates the elapsed time. That is the
    honest direction to be wrong in for a cost/evidence number (it never
    claims to have been faster than it was), and both figures are labelled so
    nobody reads one as the other. `slowest` is the useful one for a judge
    asking where the time goes."""
    timed: list[dict[str, Any]] = [
        {"agent_name": e.get("agent_name"), "latency_ms": float(e.get("latency_ms") or 0.0)}
        for e in entries
        if e.get("agent_name")
    ]
    if not timed:
        return {"per_agent": [], "agent_time_ms": 0.0, "slowest": None}
    slowest = max(timed, key=lambda row: row["latency_ms"])
    return {
        "per_agent": timed,
        # Named `agent_time_ms`, not `total_ms`: it is time spent inside
        # agents, summed, and the graph overlaps some of it.
        "agent_time_ms": round(sum(row["latency_ms"] for row in timed), 1),
        "slowest": slowest,
    }


def _inherited_values(final_state: Mapping[str, Any], history: list[dict] | None) -> list[dict]:
    """P2.9 (`R-PS-3`, `R-CONV-1`, orca_final §16.2) — what this answer took
    from earlier in the conversation rather than from the question itself.

    Session history has fed classification for a while; what was missing is
    that the user could not *see* it. "and in a trawler?" inheriting a place
    from two turns ago is correct behaviour and completely invisible, which
    makes it indistinguishable from ORCA guessing — and there was no way to
    say "no, not there". Each entry is a chip the UI can show and remove;
    removing one re-asks the question with that value overridden.

    Only values genuinely carried from a previous turn appear here. A place
    named in this question is not inherited, and neither is the regional
    default — that is a fallback, and it is disclosed as one.
    """
    if not history:
        return []
    inherited: list[dict] = []

    location = final_state.get("user_location") or {}
    if location.get("place_source") == "session_carried" and location.get("place_name"):
        inherited.append({
            "field": "place",
            "label": "Place",
            "value": location["place_name"],
            "detail": "carried from an earlier message in this chat",
        })

    # The intent, when this turn matched no routing row of its own and
    # continued the previous turn's (planning.carry_intent).
    planning_entry = next(
        (e for e in (final_state.get("audit_trace_log") or []) if e.get("agent_name") == "planning"),
        None,
    )
    if (planning_entry or {}).get("outputs", {}).get("routing_tier") == "carried_from_previous_turn":
        rows = final_state.get("matched_intent_rows") or []
        if rows:
            inherited.append({
                "field": "intent",
                "label": "Question type",
                "value": " + ".join(rows),
                "detail": "this question matched no topic of its own, so it continues the previous one",
            })

    vessel = final_state.get("vessel_class")
    # Carried only when a previous turn is where it came from — a vessel named
    # in this question is the user's own choice, not an inheritance.
    if (
        vessel
        and any(t.get("vessel_class") == vessel for t in history)
        and not vessel_named_in(final_state.get("raw_user_query") or "")
    ):
        inherited.append({
            "field": "vessel_class",
            "label": "Vessel",
            "value": VESSEL_LABELS.get(vessel, vessel),
            "detail": "carried from an earlier message in this chat",
        })

    return inherited


def _routing_summary(final_state: Mapping[str, Any]) -> dict:
    """P2.7 (`R-JUDGE-3`) — the routing decision, in the response.

    Multi-intent classification has existed for a while and nothing rendered
    it, so a compound question looked exactly like a simple one. This is the
    "Intents: SAFETY_CHECK + PFZ_NEAREST → 5 agents dispatched" line, built
    from what Planning actually decided rather than re-derived here."""
    planning_entry = next(
        (e for e in (final_state.get("audit_trace_log") or []) if e.get("agent_name") == "planning"),
        None,
    )
    outputs = (planning_entry or {}).get("outputs") or {}
    rows = final_state.get("matched_intent_rows") or []
    plan = final_state.get("execution_plan") or []
    skipped = final_state.get("skipped_agents") or []
    return {
        "matched_intent_rows": rows,
        "execution_plan": plan,
        "routing_tier": outputs.get("routing_tier"),
        "routing_scores": outputs.get("routing_scores") or [],
        # Agents dispatched is the plan minus the plan's own agents that were
        # skipped — the number the line quotes has to be the number that
        # actually ran. Only skips that were IN the plan count: a Critic
        # cancelled by P2.12 was never part of the plan, so subtracting it
        # would under-report a compound query's dispatch by one.
        "agents_dispatched": len(plan) - sum(1 for s in skipped if s.get("agent_name") in plan),
        "multi_intent": len(rows) > 1,
    }


def _sse(payload: dict) -> str:
    """Every SSE frame goes out through here. allow_nan=False is the tripwire:
    if _json_safe ever misses a case, this raises here instead of shipping
    invalid JSON that only fails later, in the client."""
    return f"data: {json.dumps(_json_safe(payload), allow_nan=False)}\n\n"


@app.get("/health")
@app.head("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _query_stream(
    query: str, lat: float, lon: float, vessel_class: str | None,
    distress: bool = False, persona: str | None = None, depth: str | None = None,
    place: tuple[str | None, str] = (None, "explicit"),
    on_final: Callable[[dict], None] | None = None,
    session_id: str | None = None,
    session_history: list[dict] | None = None,
    resolution: dict | None = None,
    llm: bool | None = None,
    fix_on_land: bool = False,
    user_id: uuid.UUID | None = None,
    user_language_default: str | None = None,
    demo_scenario: str | None = None,
    raw_fix: tuple[float, float] | None = None,
    pretranslated: dict[str, str] | None = None,
) -> AsyncIterator[str]:
    """`on_final`, when given, is called once with the same dict that gets
    JSON-serialized into the `final_response` SSE frame — the query-cache
    write hook (phase4 plan §2.3), kept as a callback rather than a return
    value so this stays a plain generator callers can iterate directly.

    `llm=False` re-runs this query with every provider disabled (P2.11,
    `R-NEW-3`) — the verdict, thresholds, geofence, citations and confidence
    all still render; only the prose narration degrades to the deterministic
    line. `None` means "whatever ORCA_LLM_ENABLED says", which is the ordinary
    path."""
    # Set on the task that drives the graph, not as a `with` block around the
    # `async for`: LangGraph may run a sync node on a worker thread whose
    # context was copied at a different moment, and the counter is a mutable
    # list precisely so it survives that copy either way.
    set_llm_override(llm)
    llm_calls = reset_llm_call_count()
    state = _initial_state(
        query, lat, lon, vessel_class, distress, persona, depth, place, session_id, session_history,
        resolution, fix_on_land, user_language_default, demo_scenario, raw_fix=raw_fix,
        pretranslated=pretranslated,
    )
    # P6.12 (orca_final §28) — every log line the graph emits from here on
    # carries this query_id, so an incident is one grep away instead of a
    # timestamp-range guess.
    bind_query_id(state["query_id"])
    # P3.2 — a real `sessions` row for this chat, threaded into every
    # audit_trace_log row below. Created once per query (idempotent — the
    # same session_id just gets its last_seen_at touched on later turns).
    session_uuid = _ensure_session_row(
        session_id, user_id, persona if persona in _PERSONAS else None, user_language_default,
    )
    emitted = 0  # every graph node appends exactly one completed_nodes entry
    # AND exactly one audit_trace_log entry in the same call (see graph.py) —
    # so the two lists grow in lockstep and index-pairing them is correct,
    # not a coincidence to be careful of.
    final_state: ORCAState | None = None

    async for values in _graph.astream(state, stream_mode="values"):
        # `astream` is typed as yielding a plain dict; every value it yields
        # here is the graph's own ORCAState, so the cast is a name for what
        # LangGraph's signature cannot express, not a claim about new data.
        final_state = cast(ORCAState, values)
        completed = values.get("completed_nodes", [])
        trace_log = values.get("audit_trace_log", [])
        for node_name, trace_entry in zip(completed[emitted:], trace_log[emitted:]):
            agent_real = trace_entry.get("agent_name", node_name)
            # P2.1 — one resolved label per span, computed at the trace
            # boundary (orca/trace.py) rather than re-derived here and again
            # in trace_routes.py from two copies of the same ladder.
            engine = engines.engine_for(agent_real, trace_entry.get("engine"))
            used_llm = engines.used_llm(agent_real, engine)
            tier = engines.AGENT_TIER.get(agent_real) if used_llm else None
            model = engines.model_for_tier(tier)
            event = {
                "type": "agent_span",
                "agent_name": node_name,
                "agent_real_name": agent_real,
                "query_id": values.get("query_id"),
                "status": trace_entry.get("status", "ok"),
                "confidence_tier": trace_entry.get("confidence", "LOW_DATA"),
                "confidence_score": trace_entry.get("confidence_score"),
                "confidence_detail": trace_entry.get("confidence_detail"),
                "latency_ms": trace_entry.get("latency_ms", 0.0),
                "reasoning_summary": _reasoning_summary(
                    agent_real, trace_entry.get("outputs", {}), trace_entry.get("status", "ok"),
                    trace_entry.get("skip_reason"),
                ),
                "inputs_consumed": trace_entry.get("inputs_consumed", {}),
                "outputs": trace_entry.get("outputs", {}),
                "source_provenance": trace_entry.get("source_provenance"),
                "used_llm": used_llm,
                # P2.1 — `engine` is the field every surface renders now.
                # `model` stays for the two clients that already read it, and
                # is None on a deterministic span exactly as before.
                "engine": engine,
                "model": model,
                "tier": tier,
                # P2.7/P2.12 — why a span did not run. Null on every span that did.
                "skip_reason": trace_entry.get("skip_reason"),
            }
            yield _sse(event)
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
            # Chatbot plan C0.2 — which engine wrote the answer, so the chat
            # can label the last-resort facts paragraph ("Deterministic — …"),
            # and whether a refused message was only small talk.
            "response_engine": final_state.get("response_engine"),
            "small_talk": final_state.get("small_talk", False),
            # The language the ANSWER is in, which the card uses for its font, the spoken reply and
            # the "English translation" box: an explicit "answer in <language>" request (PC5.8)
            # wins over the language the question was typed in.
            "detected_language": final_state.get("reply_language") or final_state.get("detected_language", "en"),
            # What the chat's context window remembers this turn as
            # (session.turn_from_final) — English query and matched routing
            # rows, so a Tamil follow-up still continues the right intent.
            "normalized_english_query": final_state.get("normalized_english_query") or query,
            "matched_intent_rows": final_state.get("matched_intent_rows") or [],
            # The one concrete thing a ROUTE / DIAGNOSTIC / REGULATORY / META /
            # EXPORT / SUBSCRIPTION / ADMINISTRATIVE question asks for (P5.29).
            "intent_actions": intent_actions.build(
                final_state.get("matched_intent_rows") or [], query,
                final_state.get("user_location"), final_state.get("query_id"),
            ),
            # How many earlier turns this answer was given with. The chat UI
            # compares it to its own thread: 0 after earlier answers means the
            # context expired, and it says so instead of the follow-up quietly
            # being answered as turn one (docs/specs/ORCA_DLC_Extension_Pack.md R-AUTH-3).
            "context_turns": len(session_history or []),
            "confidence_tier": final_state.get("confidence_tier", "LOW_DATA"),
            "confidence_reason": final_state.get("confidence_reason"),
            # Per-agent scored labels, carried on the answer itself because a
            # query-cache hit replays only this event — no agent_span events —
            # and the /ask strip would otherwise draw bare ticks for it.
            "agent_confidence": [
                {
                    "agent_name": e.get("agent_name"), "status": e.get("status", "ok"),
                    "confidence_tier": e.get("confidence"),
                    # P2.1/P2.3/P2.10 — a query-cache hit replays only this
                    # frame and no spans, so the engine, the derivation and
                    # the latency have to ride here too or a cached answer
                    # silently loses all three.
                    "engine": engines.engine_for(e.get("agent_name", ""), e.get("engine")),
                    "confidence_rationale": e.get("confidence_rationale"),
                    "latency_ms": e.get("latency_ms"),
                    "skip_reason": e.get("skip_reason"),
                }
                for e in final_state.get("audit_trace_log") or []
                if e.get("agent_name")
            ],
            # P2.3 (`R-JUDGE-4`) — the derivation of the tier the card shows:
            # the inputs Reporting took the worst of, each with its own tier
            # and rationale. From the LAST reporting span, because a Critic
            # re-invocation (P2.5) runs Reporting twice and the second is the
            # answer the user sees. Absent (None) on a refusal or a distress
            # response, which never reach Reporting.
            "confidence_inputs": next(
                (
                    (e.get("outputs") or {}).get("confidence_inputs")
                    for e in reversed(final_state.get("audit_trace_log") or [])
                    if e.get("agent_name") == "reporting"
                ),
                None,
            ),
            "risk_assessment": final_state.get("risk_assessment"),
            # Same gate graph.py already applies to the narrative's verdict
            # header (reporting.should_lead_with_verdict) — exposed so the
            # frontend can decide whether to show the GO/CAUTION/NO_GO badge
            # at all, instead of banner-ing every query regardless of intent.
            "lead_with_verdict": reporting.should_lead_with_verdict(
                final_state.get("risk_assessment") or {}, final_state.get("matched_intent_rows") or []
            ),
            "citations": final_state.get("evidence_citations", []),
            "distress_flag": final_state.get("distress_flag", False),
            # Phase 1. `outcome` is contracts.QueryOutcome — the UI renders a
            # refusal or a "which place?" card for anything but "ANSWERED",
            # and must not draw a verdict badge on one. `place_resolution`
            # carries the candidates that question needs to be answerable, and
            # `disclosures` are the sentences that go ABOVE the answer, not
            # below it: a fallback that is not disclosed is a lie (principle 3).
            "outcome": final_state.get("query_outcome") or ("DISTRESS" if final_state.get("distress_flag") else "ANSWERED"),
            "place_resolution": final_state.get("place_resolution"),
            # A refused question was never answered at a position, so the place
            # disclosure seeded before routing has nothing left to disclose —
            # showing it would read as "here is where we answered", next to a
            # card that says we did not. `disclosures` is an additive channel
            # (ORCAState), so the node that refuses cannot clear it; here can.
            "disclosures": [] if final_state.get("query_outcome") == "OUT_OF_SCOPE" else final_state.get("disclosures", []),
            # Which position every number in this response was computed at,
            # and how it was arrived at. The UI has to be able to show this:
            # a "GO" that silently belongs to the regional default rather
            # than the place the user asked about is the single most
            # dangerous output shape here, and it is invisible without this.
            "user_location": final_state.get("user_location"),
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
                # Two independent convective sources: Open-Meteo's CAPE proxy
                # (the `lightning_active` flag above) and IMD's own district
                # nowcast. When they disagree the user sees that, rather than
                # ORCA silently picking one — "single_source" when the IMD
                # snapshot is empty or out of its validity window, because two
                # statements about different days are not a disagreement.
                "lightning_source_agreement": weather.get("lightning_source_agreement", "single_source"),
                "imd_nowcast": weather.get("imd_nowcast"),
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
            # Since P2.6 these come from the marine_data_discovery node, so
            # they are present on every answer rather than only the ones that
            # reached Ocean Analytics.
            "source_selections": discovery.get("source_selections", []),
            # P2.4 — every pair of sources that was compared for this answer.
            # The disagreements are also in `disclosures` (they belong above
            # the answer); this is the full record, agreements included, for
            # the panel that shows what was checked.
            "reconciliation": final_state.get("reconciliation", []),
            # P2.7 — what the plan decided not to do, and why. A smaller
            # answer is a decision, and this is what lets the UI say so
            # instead of rendering a gap.
            "skipped_agents": final_state.get("skipped_agents", []),
            # P2.7 — the routing decision itself, named: which rows matched,
            # which tier decided, and how many agents that dispatched.
            "routing": _routing_summary(final_state),
            # P2.10 (`R-NEW-4`) — latency as evidence. Per-agent values have
            # always been on the spans and the UI under-used them; the total
            # is the number that retires an unverifiable "≤3 sec" claim, and
            # a query-cache hit replays only this frame, so it has to be here
            # and not only summable from spans the client may never see.
            "latency": _latency_summary(final_state.get("audit_trace_log") or []),
            # P2.13 — measured, not asserted. §6.2's cost-per-query number is
            # computed from this rather than from an estimate of it.
            "llm_call_count": llm_calls[0],
            # Failed attempts cost quota too, but are not calls (2026-09-29).
            "llm_failed_attempts": llm_calls[1],
            # P2.11 — whether any LLM was reachable for this query at all, so
            # the UI can label a deterministic run instead of it silently
            # looking like an ordinary one.
            "llm_enabled": llm_enabled() if llm is None else llm,
            # P2.9 — which boat this answer's thresholds were computed for.
            # On the payload because `session.turn_from_final` builds the
            # remembered turn from exactly this dict, so a vessel named in
            # turn 3 is what turn 4 inherits.
            "vessel_class": final_state.get("vessel_class"),
            # P2.9 / orca_final §16.2 — the values this answer took from
            # earlier in the conversation, as removable chips. Carrying
            # context is correct; carrying it invisibly is indistinguishable
            # from guessing, and leaves the user no way to say "not there".
            "inherited": _inherited_values(final_state, session_history),
            # P3.4 — "ask at the moment it first matters." Never on a
            # refusal or a distress response: neither is the moment to ask
            # anything else of the caller.
            "profile_prompt": (
                profile_prompt(
                    user_id=user_id,
                    matched_intent_rows=final_state.get("matched_intent_rows") or [],
                    place_source=(final_state.get("user_location") or {}).get("place_source"),
                )
                if final_state.get("query_outcome", "ANSWERED") == "ANSWERED" and not final_state.get("distress_flag")
                else None
            ),
        }
        _persist_audit_trace_log(final_state.get("query_id", ""), final_state.get("audit_trace_log", []), session_uuid)
        if final_state.get("distress_flag"):
            _mrcc = final.get("mrcc_contact")
            _record_distress_event(final_state, _mrcc if isinstance(_mrcc, dict) else None)
        # The turn itself is remembered by _remember_turns in query(), not
        # here: a query-cache hit or a coalesced follower never runs this
        # generator, and remembering only here left those turns out of the
        # chat's context window entirely.
        if on_final is not None:
            on_final(final)
        try:
            verdict = "DISTRESS" if final_state.get("distress_flag") else (final_state.get("risk_assessment") or {}).get("go_no_go", "INFO")
            record_recent_trace(
                query_id=final_state.get("query_id", ""),
                query_text=query,
                verdict=verdict,
                confidence_tier=final_state.get("confidence_tier", "LOW_DATA"),
                rows=final_state.get("audit_trace_log", []),
            )
        except Exception:  # the reasoning ribbon is a convenience; the answer still ships
            logging.getLogger("orca.trace").warning("recent trace not recorded", exc_info=True)
        yield _sse(final)


async def _reset_stream() -> AsyncIterator[str]:
    """P2.14 — the whole response to a reset: one confirmation frame, no
    agents, no spans, no marine content. `outcome: "RESET"` is what tells the
    chat UI to drop its inherited-value chips (P2.9) rather than render this
    as an answer.

    The confirmation is worded by a model (chatbot plan defect 4, fixed
    2026-09-25) rather than the same fixed English sentence every time —
    `reporting.write_confirmation_reply` falls back to that exact sentence
    whenever no model answers, so this never regresses to silence."""
    reply, engine = reporting.write_confirmation_reply(session_memory.RESET_CONFIRMATION)
    yield _sse({
        "type": "final_response",
        "query_id": str(uuid.uuid4()),
        "outcome": "RESET",
        "final_english_response": reply,
        "final_vernacular_response": reply,
        "response_engine": engine,
        "confidence_tier": "HIGH",
        "context_turns": 0,
        "inherited": [],
        "risk_assessment": None,
        "citations": [],
        "disclosures": [],
        "distress_flag": False,
    })


async def _language_change_stream(
    language: str, session_id: str | None, history: list[dict], user: User | None,
) -> AsyncIterator[str]:
    """P3.13 (orca_final §15.2) — "speak to me in Telugu" changes the
    conversation's language WITHOUT being answered as a marine question.
    Persists the choice (this chat, and the account when signed in), then —
    zero re-query, same contract as `POST /render` — re-renders the last
    answered turn in this chat into the new language when there is one;
    otherwise just confirms the switch. Never routes through Planning."""
    if session_id:
        try:
            sid = uuid.UUID(session_id)
        except ValueError:
            sid = None
        if sid is not None:
            try:
                from orca.db.engine import get_sessionmaker
                from orca.db.repositories import set_session_language

                db = get_sessionmaker()()
                try:
                    set_session_language(db, session_id=sid, language=language)
                    db.commit()
                finally:
                    db.close()
            except Exception:
                logging.getLogger("orca.session").warning("session language not persisted", exc_info=True)
    if user is not None:
        try:
            from orca.db.engine import get_sessionmaker

            db = get_sessionmaker()()
            try:
                db_user = db.get(User, user.id)
                if db_user is not None:
                    db_user.language = language
                    db.commit()
            finally:
                db.close()
        except Exception:
            logging.getLogger("orca.auth").warning("account language not persisted", exc_info=True)

    last_turn = next((t for t in reversed(history) if t.get("query_id")), None)
    if last_turn is not None:
        try:
            rendered = trace_routes_render_query(last_turn["query_id"], "fisherman", language)
            yield _sse({
                "type": "final_response",
                "query_id": rendered.query_id,
                "outcome": "LANGUAGE_CHANGED",
                "final_english_response": rendered.final_english_response,
                "final_vernacular_response": rendered.final_vernacular_response or rendered.final_english_response,
                "detected_language": language,
                "confidence_tier": rendered.confidence_tier,
                "citations": rendered.citations,
                "context_turns": len(history),
                "risk_assessment": None,
                "disclosures": [f"Switched replies to {language} — this is your last answer, re-rendered."],
                "distress_flag": False,
                "inherited": [],
            })
            return
        except Exception:
            logging.getLogger("orca.language").warning("language-change re-render failed; confirming only", exc_info=True)

    # Worded by a model (chatbot plan defect 4, fixed 2026-09-25) rather than
    # the same fixed English sentence every time; falls back to that sentence
    # whenever no model answers. Rephrased BEFORE translation, not after —
    # the target is `language`, not the language `q` was typed in, so this
    # cannot reuse write_guard_reply's "reply in the message's own language"
    # framing.
    confirmation_en, engine = reporting.write_confirmation_reply(
        "Done — I'll reply in this language from now on."
    )
    try:
        from orca.agents.language import _ALL_LANGUAGES, translate_from_english

        confirmation = translate_from_english(confirmation_en, target=language) if language in _ALL_LANGUAGES else confirmation_en  # type: ignore[arg-type]
    except RuntimeError:
        confirmation = confirmation_en
    yield _sse({
        "type": "final_response",
        "query_id": str(uuid.uuid4()),
        "outcome": "LANGUAGE_CHANGED",
        "final_english_response": confirmation_en,
        "final_vernacular_response": confirmation,
        "response_engine": engine,
        "detected_language": language,
        "confidence_tier": "HIGH",
        "context_turns": len(history),
        "inherited": [],
        "risk_assessment": None,
        "citations": [],
        "disclosures": [],
        "distress_flag": False,
    })


async def _remember_turns(session_id: str | None, query: str, stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Adds each answered turn to the chat's context window (orca/session.py).
    Wraps the stream query() actually returns because that is the one point a
    fresh run, a query-cache hit and a coalesced follower all pass through —
    each yields the same `final_response` frame. Remembered *before* that
    frame is sent, so the follow-up the user types next can never beat it."""
    async for line in stream:
        if session_id and '"final_response"' in line:
            try:
                payload = json.loads(line.removeprefix("data: "))
                if payload.get("type") == "final_response":
                    session_memory.append_turn(session_id, session_memory.turn_from_final(query, payload))
            except Exception:  # memory is best-effort; the answer itself must still ship
                logging.getLogger("orca.session").warning("session: could not remember turn", exc_info=True)
        yield line


def _record_distress_event(final_state: Mapping[str, Any], mrcc_contact: dict | None) -> None:
    """Puts the distress query on the authority queue (P4.16). Best-effort for
    the same reason as the audit write below: the caller's MRCC contacts are
    in the answer already, and a DB outage must not fail that answer."""
    try:
        from orca.db.engine import get_sessionmaker
        from orca.ops.distress_queue import record_event

        db = get_sessionmaker()()
        try:
            record_event(db, dict(final_state), mrcc_contact)
        finally:
            db.close()
    except Exception:
        logging.getLogger("orca.distress").warning("distress event not queued", exc_info=True)


def _persist_audit_trace_log(query_id: str, entries: list[dict], session_id: uuid.UUID | None = None) -> None:
    """Exit criterion 7 (Phase 2 plan §3): rows land in Postgres, not just
    ORCAState. Best-effort — a DB outage degrades to Phase-1 behaviour
    (in-memory only, shipped with the SSE response above) rather than
    failing the user-facing request; the trace itself already reached the
    client either way.

    P3.2 — `session_id` is a real `sessions.id` (see `_ensure_session_row`),
    not the unconditional `None` this used to pass: the mapped `sessions`
    table was otherwise dead, and the reasoning trail could not be read back
    per-user or per-session, which is what a coastal-authority persona needs."""
    if not entries:
        return
    try:
        from orca.db.engine import get_sessionmaker
        from orca.db.repositories import persist_trace_entries

        db = get_sessionmaker()()
        try:
            persist_trace_entries(db, query_id=query_id, session_id=session_id, entries=entries)
        finally:
            db.close()
    except Exception:
        # outage here must never fail the request, and there is nothing more to do
        # than degrade to Phase-1 behaviour (the trace already shipped in the SSE body).
        pass


def _ensure_session_row(
    session_id: str | None, user_id: uuid.UUID | None, persona: str | None, language: str | None,
) -> uuid.UUID | None:
    """P3.2 (`R-AUTH-2`) — a real `sessions` row for this chat. `api/main.py`
    used to pass `session_id=None` unconditionally to `persist_trace_entries`,
    so the mapped `sessions` table (`infra/db/001_init.sql`) was permanently
    empty. Only /ask sends a `session_id` (a `crypto.randomUUID()` chat id —
    `/safety`, `/reasoning` and the SOS control stay session-less); anything
    else is left alone rather than guessed at. Best-effort, same
    degrade-not-fail contract as `_persist_audit_trace_log`: a DB outage here
    must not fail an answer that has already been decided."""
    if not session_id:
        return None
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return None
    try:
        from orca.db.engine import get_sessionmaker
        from orca.db.repositories import get_or_create_session

        db = get_sessionmaker()()
        try:
            get_or_create_session(db, session_id=sid, user_id=user_id, persona=persona, language=language)
            db.commit()
        finally:
            db.close()
    except Exception:
        logging.getLogger("orca.session").warning("session row not persisted", exc_info=True)
    return sid


def _usable_fix(fix_lat: float | None, fix_lon: float | None) -> tuple[float, float] | None:
    """The browser's GPS fix as a position ORCA can answer at, or None.

    A fix is only a position if there is sea at it. A phone indoors in
    Bengaluru is a perfectly valid GPS reading and a useless marine one: taken
    as the answer's position it hands `place_guard` a point with no sea at it,
    so every query that doesn't name a port dead-ends on "12.9380, 77.4953 is
    on land" — strictly worse than the pilot default it replaced. On land, the
    caller falls through to the text and then the default, exactly as they did
    before the frontend ever sent a fix.
    """
    if fix_lat is None or fix_lon is None:
        return None
    lat, lon = float(fix_lat), float(fix_lon)
    return None if depth_at_point(lat, lon).on_land else (lat, lon)


@app.get("/query")
async def query(
    q: str = "", lat: OptLat = None, lon: OptLon = None, vessel_class: str | None = None,
    distress: bool = False, persona: str | None = None, depth: str | None = None,
    session_id: str | None = None, llm: str | None = None, drop: str | None = None,
    fresh: bool = False, fix_lat: OptLat = None, fix_lon: OptLon = None,
    demo_scenario: str | None = None,
    user: User | None = Depends(get_optional_user), db: Session = Depends(get_db),
) -> StreamingResponse:
    """`llm=off` (P2.11, `R-NEW-3`) re-runs this exact query with every LLM
    provider disabled. It is the demo beat: the same question, the same
    verdict, thresholds, geofence, citations and confidence, and only the
    prose narration degraded to the deterministic line. `llm=on` forces the
    opposite even when `ORCA_LLM_ENABLED=0` is set in the environment;
    omitting it entirely uses whatever the environment says.

    `drop=place,vessel_class,intent` (P2.9, orca_final §16.2) refuses to inherit
    the named values from earlier in this chat — what the ✕ on a "Carried over"
    chip sends. It acts where each inheritance actually happens: the place is
    not taken from `session.last_place`, the vessel not from
    `session.last_vessel_class`, and Planning's follow-up rule sees no previous
    intent. Rewriting the question text cannot do this, and the first version
    tried: it re-asked "(not Kannur…)", which put the name back into the text
    and resolved Kannur again.

    `fresh=1` is the answer card's "try again": run every agent again for a
    question that has already been answered, rather than replaying the cached
    answer. It skips the cache *read* and the coalescer, but still writes what
    it produces back to the cache — a re-run is the newest answer, so the next
    ordinary asker should get it rather than the one it replaced.

    It deliberately does NOT remember the turn (see `_remember_turns`): the
    question is already in this chat's context window with its previous answer,
    and appending it again would make the window read as if it had been asked
    twice. The client re-pushes the window through
    PUT /api/session/{id}/context once the re-run lands, which replaces it
    wholesale with the new answer in place.
    """
    # P3.1 (`R-AUTH-1`) — an optional Bearer token. Anonymous callers (no
    # token, or one that fails verification) get today's exact path: no
    # login wall, nothing above can fail because of this. A verified token
    # supplies *defaults only* — an explicit `persona`/`vessel_class` param
    # or a place actually named in the text always wins; see below.
    if persona is None and user is not None and user.default_persona in _PERSONAS:
        persona = user.default_persona

    dropped = {d.strip() for d in (drop or "").split(",") if d.strip()}
    # An explicit lat/lon from the caller always wins — a resolved GPS fix or
    # a registered home port (Phase 2 D1) is real; a place name in free text is
    # a fallback for the caller that has no location at all yet. Only when
    # neither is given do we try to name a pilot-region place in the query text
    # (e.g. "near Pamban"), then the last place THIS session actually resolved
    # (checklist P0 #1 — "what about tomorrow instead?" names no place of its
    # own but should still mean the place just asked about), then the browser's
    # GPS fix (`fix_lat`/`fix_lon`), and only then the regional default.
    #
    # `fix_*` is deliberately a *different* parameter from `lat`/`lon` rather
    # than a second way of setting them. `lat`/`lon` mean "answer here, I chose
    # this"; an ambient GPS fix means "this is where I happen to be". If the
    # ambient fix overrode the text, a fisherman in Thoothukudi asking "what
    # about Pamban?" would get Thoothukudi's numbers under Pamban's name — the
    # exact failure the paragraph below exists to prevent. So the fix is only
    # consulted once the text has resolved to nothing: it replaces the pilot
    # default, never a place the user actually named.
    #
    # `place_name`/`place_source` are carried onward deliberately: falling back
    # to the default is *not* the same event as resolving a place, and the
    # difference has to survive all the way to Agent 9. Otherwise "am I safe
    # off Palk Bay?" is answered with Thoothukudi's numbers under Palk Bay's
    # name — 53 nm from the IMBL instead of 0.4 nm, GO instead of DANGER.
    # Read once per request: place carry-over, the priority lane, Planning's
    # follow-up rule and Agent 9's prompt all see the same window. Only the
    # Ask chat sends a session_id; /safety, /reasoning and the SOS control
    # don't, so they stay exactly as stateless (and cacheable) as before.
    # P2.14 — "forget that, start fresh" clears the window and confirms in one
    # line. Placed here, ahead of place resolution and the graph, because a
    # reset is not a marine question: routing it would answer something nobody
    # asked, using exactly the context the user just told us to drop.
    #
    # It is NOT ahead of Agent 12 in spirit — the distress control (`distress=`)
    # is checked first below, and a *typed* distress call can never be a reset
    # because `is_reset_request` matches the whole message and no reset phrase
    # is a distress phrase. A message that is nothing but "forget it" is not
    # someone in trouble.
    # Every parser from here to the graph — reset, language command, vessel,
    # place, priority lane — matches English words, so a Kannada "ಕೊಚ್ಚಿ"
    # never became Kochi and the question was answered at the pilot default.
    # Translate once here; ingress reuses it (state["pretranslated"]).
    # Place resolution tries the raw text first, since the gazetteer also
    # holds Tamil-script names.
    q_language = query_language(q, user.language if user is not None else None)
    try:
        q_en, q_rung = english_query(q, q_language)
        pretranslated: dict[str, str] | None = {"raw": q, "language": q_language, "english": q_en, "rung": q_rung}
    except RuntimeError:
        q_en, pretranslated = q, None  # no translator — ingress degrades and says so

    if not distress and (session_memory.is_reset_request(q) or session_memory.is_reset_request(q_en)):
        session_memory.clear(session_id)
        return StreamingResponse(_reset_stream(), media_type="text/event-stream")

    history = session_memory.get_turns(session_id)

    # P3.13 — "speak to me in Telugu" changes the language, never answered as
    # a marine question. Checked here, same footing as the reset phrase above
    # and for the same reason: a distress call is never swallowed by either.
    if not distress:
        lang_cmd = match_language_command(q) or match_language_command(q_en)
        if lang_cmd is not None:
            return StreamingResponse(
                _language_change_stream(lang_cmd, session_id, history, user),
                media_type="text/event-stream",
            )
    if "intent" in dropped:
        # Turns stay (Agent 9 still reads the conversation); only the carried
        # intent is withheld from Planning.
        history = [{**turn, "intent_rows": []} for turn in history]

    # P2.9 — which boat this question is about. Three sources, in the order
    # that respects what the user actually said:
    #   1. an explicit `vessel_class` parameter (a registered vessel, or the
    #      picker) — always wins;
    #   2. a vessel named in this question's text ("and in a trawler?"), which
    #      set nothing at all before this point;
    #   3. the vessel from earlier in this chat, so the two follow-ups after
    #      "in a trawler?" stay about the trawler.
    # Nothing at all stays None, and `risk_assessment.run` applies the most
    # conservative class — the safety default keeps its single home.
    vessel_class = resolve_vessel_class(
        vessel_class, q if q_en == q else f"{q} {q_en}", None if "vessel_class" in dropped else session_memory.last_vessel_class(history),
    )
    # P3.1 — lowest precedence of all: a signed-in user's active vessel
    # (P3.9), consulted only when nothing more specific (an explicit param, a
    # vessel named in this question, or one remembered from this chat) gave
    # an answer. Never overrides "and in a trawler?" or the chat's own memory.
    if vessel_class is None and user is not None and user.active_vessel_id is not None and "vessel_class" not in dropped:
        active_vessel = get_vessel_for_owner(db, user.active_vessel_id, user.id)
        if active_vessel is not None:
            vessel_class = active_vessel.vessel_class

    # None = follow the environment. Anything unrecognised is also None rather
    # than an error: a mistyped demo parameter must not fail a safety query.
    llm_override = {"off": False, "0": False, "false": False, "on": True, "1": True, "true": True}.get(
        (llm or "").strip().lower()
    )

    place_name: str | None = None
    place_source = "explicit"
    fix_on_land = False
    resolution: dict | None = None
    if lat is None or lon is None:
        # P1.2 — one shared guard, not a second copy of the old inline
        # if-ladder. It returns four outcomes, and the two that cannot be
        # answered at a position (`ambiguous`, `unresolvable`) are stopped by
        # the graph's place_guard node, *after* Agent 12 has had the query —
        # never here, where a distress call would be refused for naming no port.
        carried = None if "place" in dropped else session_memory.last_place(history)
        resolved = resolve_or_ask(q, {"last_place": carried} if carried else None)
        if q_en != q and resolved.status in ("fallback", "unresolvable"):
            resolved = resolve_or_ask(q_en, {"last_place": carried} if carried else None)
        resolution = resolved.as_dict()
        usable = _usable_fix(fix_lat, fix_lon)
        # Sent a position, and it was dropped for being inland — a different
        # situation from never having one, and Agent 9 has to be told which.
        fix_on_land = fix_lat is not None and fix_lon is not None and usable is None
        home_port = user_home_port(user) if user is not None else None
        if resolved.place is not None and not (
            (usable is not None or home_port is not None) and resolved.place.source == "regional_default"
        ):
            lat, lon = resolved.place.lat, resolved.place.lon
            place_source = resolved.place.source
            # The regional default is nobody's place name. Leaving place_name
            # None there is what stops Agent 9 putting the user's words on the
            # default's numbers. A carried-over place IS a real name — it just
            # came from the previous turn rather than this one, which is what
            # place_source and the disclosure say.
            place_name = None if place_source == "regional_default" else resolved.place.name
        elif usable is not None and resolved.status != "ambiguous":
            # The text named nothing we hold (or nothing at all) but the browser
            # gave us a real fix — that beats the pilot default outright, and is
            # what `resolve_or_ask`'s own fallback disclosure asks the caller for
            # ("Name a place or send your position"). `place_source="gps_fix"`
            # keeps it distinguishable from both a named place and the default,
            # so Agent 9 can say where the answer is really about.
            #
            # Ambiguity is excluded on purpose: "Gujarat" has to keep asking
            # which port was meant. Silently answering it at the caller's own
            # position would resolve the ambiguity by ignoring the question.
            (lat, lon), place_source = usable, "gps_fix"
            place_name = None
            resolution = {**(resolution or {}), "status": "resolved", "place_source": "gps_fix"}
        elif home_port is not None and resolved.status != "ambiguous":
            # P3.1 — a signed-in user's registered home port beats the
            # regional default: it is a real, chosen position, just not one
            # named in this particular question. `place_source="home_port"`
            # keeps it distinguishable from both a named place and the
            # anonymous default, same reasoning as `gps_fix` above.
            # Ambiguous is excluded for the same reason it is above — "Gujarat"
            # must keep asking, not be silently answered at the caller's own port.
            lat, lon, place_source = home_port["lat"], home_port["lon"], "home_port"
            place_name = None
            resolution = {**(resolution or {}), "status": "resolved", "place_source": "home_port"}
        else:
            # Unresolvable or ambiguous: the graph will stop before any agent
            # reads this, and "regional_default" is what tells Agent 12 in the
            # meantime that it has no position for this caller (P4.16).
            lat, lon, place_source = _DEFAULT_LAT, _DEFAULT_LON, "regional_default"
    else:
        # A chosen position that is exactly a place the text names — a picked
        # "which did you mean?" chip, or a saved location — keeps that place's
        # name, so the answer says "Mangrol" rather than an unnamed position.
        place_name = next(
            (p.name for p in resolve_all_places_from_text(q) + resolve_all_places_from_text(q_en) if (p.lat, p.lon) == (lat, lon)), None
        )

    # P3.1 — carried into `_query_stream` so `user_language_default` reaches
    # `language.run_ingress` and `user_id` reaches `_ensure_session_row` (P3.2).
    user_id = user.id if user is not None else None
    user_language_default = user.language if user is not None else None
    raw_fix = (float(fix_lat), float(fix_lon)) if fix_lat is not None and fix_lon is not None else None
    # The device position is in every model prompt now (reporting.conversation_context),
    # so an answer may quote it: it is part of what the answer depends on, and
    # one caller's position must never be served from the cache to another.
    # Same precision the prompt prints it at.
    fix_suffix = f":fix={raw_fix[0]:.4f},{raw_fix[1]:.4f}" if raw_fix is not None else ""

    # A distress query is never cached or coalesced onto another in-flight
    # request (phase4 plan §2.2/§2.3) — every SOS is its own, always-fresh
    # invocation. Ground Rule 2's safety-path discipline applies to the
    # request-handling layer too: a second, real emergency call must never
    # be silently folded into a stale answer meant for a different call.
    if distress:
        return StreamingResponse(
            _remember_turns(session_id, q, _query_stream(
                q, lat, lon, vessel_class, distress, persona, depth, (place_name, place_source),
                session_id=session_id, session_history=history, resolution=resolution,
                llm=llm_override, fix_on_land=fix_on_land,
                user_id=user_id, user_language_default=user_language_default,
                demo_scenario=demo_scenario,
                raw_fix=raw_fix, pretranslated=pretranslated,
            )),
            media_type="text/event-stream"
        )

    if demo_scenario:
        # P6.6 — never cached and never coalesced onto another in-flight
        # request, same rule as `distress` above and for the same reason: a
        # cache entry keyed only by (q, lat, lon, vessel_class, persona,
        # depth) does not know a request was pinned to a fixture, so an
        # ordinary live query at the same resolved parameters could be
        # served the demo's fixture answer, or vice versa, if this shared
        # the cache path at all.
        return StreamingResponse(
            _query_stream(
                q, lat, lon, vessel_class, distress, persona, depth, (place_name, place_source),
                session_id=session_id, session_history=history, resolution=resolution,
                llm=llm_override, fix_on_land=fix_on_land,
                user_id=user_id, user_language_default=user_language_default,
                demo_scenario=demo_scenario,
                raw_fix=raw_fix, pretranslated=pretranslated,
            ),
            media_type="text/event-stream",
        )

    if fresh:
        # A follow-up's answer depends on its conversation, so it is never
        # written to the shared cache — the same rule the ordinary path below
        # applies, and the reason this is not simply `on_final=store`.
        shared_key = None if history else resolved_key(q, lat, lon, vessel_class, persona, depth) + fix_suffix
        # P2.11 — same rule as the ordinary path below: an LLM-disabled run is
        # a DIFFERENT answer, so `fresh=1&llm=off` must not overwrite the
        # ordinary (LLM-on) answer sitting in the shared cache slot.
        if shared_key is not None and llm_override is not None:
            shared_key = f"{shared_key}:llm={'on' if llm_override else 'off'}"
        return StreamingResponse(
            _query_stream(
                q, lat, lon, vessel_class, distress, persona, depth, (place_name, place_source),
                on_final=None if shared_key is None else (lambda final: query_cache_store(shared_key, final)),
                session_id=session_id, session_history=history, resolution=resolution,
                llm=llm_override, fix_on_land=fix_on_land,
                user_id=user_id, user_language_default=user_language_default,
                raw_fix=raw_fix, pretranslated=pretranslated,
            ),
            media_type="text/event-stream",
        )

    cache_key = resolved_key(q, lat, lon, vessel_class, persona, depth) + fix_suffix
    # P2.11 — an LLM-disabled run is a DIFFERENT answer to the same question,
    # so it must not be served from, or written into, the ordinary answer's
    # cache slot. Without this the demo shows the cached LLM narration back
    # with the toggle off, which is precisely the claim being disproved.
    if llm_override is not None:
        cache_key = f"{cache_key}:llm={'on' if llm_override else 'off'}"
    # A follow-up's answer depends on its conversation, not just its resolved
    # parameters: "why?" means something different in every chat. So it is
    # never served from or written to the shared query cache, and it only
    # coalesces with its own chat — never folded into another chat's
    # identical-looking in-flight request. A chat's first turn has no history
    # and stays exactly as cacheable as before.
    follow_up = bool(history)
    if follow_up:
        cache_key = f"{cache_key}:session:{session_id}"
    lane = PRIORITY_LANE if _is_priority_shaped(q_en, depth, history) else STANDARD_LANE

    async def _produce() -> AsyncIterator[str]:
        cached = None if follow_up else query_cache_get(cache_key)
        if cached is not None:
            yield _sse(cached)
            return
        async with lane:
            async for line in _query_stream(
                q, lat, lon, vessel_class, distress, persona, depth, (place_name, place_source),
                on_final=None if follow_up else (lambda final: query_cache_store(cache_key, final)),
                session_id=session_id, session_history=history, resolution=resolution,
                llm=llm_override, fix_on_land=fix_on_land,
                user_id=user_id, user_language_default=user_language_default,
                raw_fix=raw_fix, pretranslated=pretranslated,
            ):
                yield line

    return StreamingResponse(
        _remember_turns(session_id, q, coalesce(cache_key, _produce)), media_type="text/event-stream",
    )
