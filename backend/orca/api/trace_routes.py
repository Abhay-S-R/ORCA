"""Phase 3 D1 Day 15 contracts (plan §5.1): `TraceGraph` (the `/reasoning`
replay payload) and `PersonaRender` (`POST /render`). Both read
`audit_trace_log` rows already persisted by orca/trace.py's
run_traced_node + orca/db/repositories.persist_trace_entries — neither
route re-invokes a single specialist agent. `POST /render` calls only Agent
9 (orca/agents/reporting.py), asserted in tests/unit/test_trace_routes.py.
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from orca import engines
from orca.agents import reporting
from orca.contracts import (
    AgentResult,
    Confidence,
    SourceProvenance,
    coerce_confidence_score,
    coerce_reasoning_depth,
    coerce_status,
)
from orca.db.engine import get_sessionmaker
from orca.db.models import AuditTraceLog
from orca.db.repositories import get_trace_entries

router = APIRouter()

# The pipeline's own fixed structure (orca/graph/graph.py) — depth and group
# membership are a property of the graph wiring, not of any one trace, so
# they are named here rather than inferred from span timing (§4.4's "layout
# ... computed once ... from execution depth" refers to the frontend's
# dagre pass over this same fixed shape).
_NODE_DEPTH: dict[str, int] = {
    # "distress" is orca/graph/graph.py's actual run_traced_node agent_name
    # for the distress_check node (Agent 12 runs once, named after the
    # agent, not the graph node) — this dict is keyed on what's actually
    # written to audit_trace_log, not on LangGraph's own node names.
    # marine_data_discovery (P2.6) sits between planning and the fan-out,
    # which is a real depth, so everything downstream of it moved down one.
    "distress": 0, "language_ingress": 1, "planning": 2,
    "marine_data_discovery": 3,
    "weather_intelligence": 4, "geospatial": 4, "ocean_analytics": 4,
    "risk_assessment": 5, "visualization": 5,
    "reporting": 6, "critic": 7, "language_egress": 8,
}
_FANOUT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("weather_intelligence", "geospatial", "ocean_analytics"),
    ("risk_assessment", "visualization"),
)
_LINEAR_EDGES: tuple[tuple[str, str], ...] = (
    ("distress", "language_ingress"),
    ("language_ingress", "planning"),
    ("planning", "marine_data_discovery"),
    ("reporting", "language_egress"),
    # `reporting -> critic` was missing from this table entirely: the Critic
    # node had no incoming edge in any replay and floated free of the graph.
    # It only surfaced once P2.5 made the Critic run on every query instead of
    # only on DEEP ones nobody looked at.
    ("reporting", "critic"),
    ("critic", "language_egress"),
)
_FANOUT_EDGES: tuple[tuple[str, str], ...] = (
    # P2.6 — the fan-out hangs off Agent 3 now, not Planning.
    ("marine_data_discovery", "weather_intelligence"),
    ("marine_data_discovery", "geospatial"),
    ("marine_data_discovery", "ocean_analytics"),
    ("weather_intelligence", "risk_assessment"), ("geospatial", "risk_assessment"), ("ocean_analytics", "risk_assessment"),
    ("weather_intelligence", "visualization"), ("geospatial", "visualization"), ("ocean_analytics", "visualization"),
    ("risk_assessment", "reporting"), ("visualization", "reporting"),
)

# In-memory LRU ring buffer for recent query traces (last 25 queries)
# Guarantees that /trace/{query_id} and recent trace selection work out of
# the box even when PostgreSQL is offline.
_RECENT_TRACES: dict[str, dict[str, Any]] = {}
_RECENT_SUMMARIES: list[dict[str, Any]] = []


def record_recent_trace(
    query_id: str,
    query_text: str,
    verdict: str | None,
    confidence_tier: str,
    rows: list[Any],
) -> None:
    if not query_id:
        return
    _RECENT_TRACES[query_id] = {
        "query_id": query_id,
        "query_text": query_text,
        "verdict": verdict or "UNKNOWN",
        "confidence_tier": confidence_tier,
        "rows": rows,
    }
    # Keep only last 25 in memory
    if len(_RECENT_TRACES) > 25:
        oldest = next(iter(_RECENT_TRACES))
        _RECENT_TRACES.pop(oldest, None)

    total_latency = 0.0
    for r in rows:
        lat = r.get("latency_ms") if isinstance(r, dict) else getattr(r, "latency_ms", 0.0)
        if lat:
            total_latency += float(lat)

    summary = {
        "query_id": query_id,
        "query_text": query_text,
        "verdict": verdict or "INFO",
        "confidence_tier": confidence_tier,
        "node_count": len(rows),
        "total_latency_ms": round(total_latency, 1),
    }
    # Prepend to list, dedup by query_id, cap at 20
    global _RECENT_SUMMARIES
    _RECENT_SUMMARIES = [summary] + [s for s in _RECENT_SUMMARIES if s["query_id"] != query_id][:19]


def recent_traces_sql(limit: int = 10) -> str:
    return f"""
        SELECT query_id,
               MAX(created_at) AS last_seen,
               COUNT(*) AS node_count,
               SUM(latency_ms) AS total_latency_ms,
               MAX(inputs_consumed->>'raw_user_query') FILTER (WHERE agent_name = 'language_ingress') AS ingress_text,
               MAX(inputs_consumed->>'normalized_query') FILTER (WHERE agent_name = 'planning') AS planning_text,
               MAX(inputs_consumed->>'text') FILTER (WHERE agent_name = 'distress') AS distress_text,
               BOOL_OR((outputs->'detection'->>'is_distress')::boolean) FILTER (WHERE agent_name = 'distress') AS is_distress,
               MAX(outputs->>'go_no_go') FILTER (WHERE agent_name = 'risk_assessment') AS go_no_go,
               MAX(confidence::text) FILTER (WHERE agent_name = 'risk_assessment') AS risk_tier
        FROM audit_trace_log
        WHERE agent_name NOT IN ('security', 'sentinel', 'feedback')
        GROUP BY query_id
        ORDER BY last_seen DESC
        LIMIT {int(limit)}
    """


def _undouble(t: str | None) -> str | None:
    """The distress agent stores raw + normalized text joined; for an English
    query those are the same sentence twice."""
    if not t:
        return t
    t = t.strip()
    half = len(t) // 2
    return t[:half].strip() if t[:half].strip() == t[half:].strip() else t


def recent_summary_from_row(r: dict[str, Any]) -> dict[str, Any]:
    """One switcher entry from stored audit rows only. Missing -> None."""
    verdict = "DISTRESS" if r.get("is_distress") else r.get("go_no_go")
    total = r.get("total_latency_ms")
    return {
        "query_id": str(r["query_id"]),
        "query_text": r.get("ingress_text") or r.get("planning_text") or _undouble(r.get("distress_text")),
        "verdict": verdict,
        "confidence_tier": r.get("risk_tier"),
        "node_count": int(r.get("node_count") or 0),
        "total_latency_ms": None if total is None else round(float(total), 1),
    }


class TraceNode(BaseModel):
    id: str
    agent_name: str
    depth: int
    status: str
    confidence_tier: str
    confidence_score: int | None = None
    confidence_detail: dict[str, Any] | None = None
    latency_ms: float | None
    reasoning_summary: str
    source_count: int
    used_llm: bool
    inputs_consumed: dict[str, Any]
    outputs: dict[str, Any]
    source_provenance: dict[str, Any] | None
    # P2.1 — what computed this node. Always present: "Deterministic" for the
    # safety path, the IndicTrans2 weights for Agent 1, a model id for a span
    # that actually reached one. `model`/`tier` stay for existing readers.
    engine: str = engines.DETERMINISTIC
    model: str | None = None
    tier: str | None = None
    # P2.7/P2.12 — why a node did not run, when it did not.
    skip_reason: str | None = None
    # How many times this agent ran in the query. A Critic-driven re-invocation runs the named
    # specialist, Reporting and the Critic a second time (P2.5); the replay draws ONE node per
    # agent and says so here. `latency_ms` on such a node is the SUM of its runs.
    run_count: int = 1


class TraceEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    kind: Literal["handoff", "critic_loop", "cancelled"]
    label: str


class TraceGroup(BaseModel):
    id: str
    node_ids: list[str]
    reason: str = "parallel_fanout"


class TraceGraph(BaseModel):
    query_id: str
    nodes: list[TraceNode]
    edges: list[TraceEdge]
    groups: list[TraceGroup]


def _reasoning_summary(
    agent_name: str, outputs: dict[str, Any], status: str = "ok",
    skip_reason: str | None = None,
) -> str:
    """One line, readable without opening the inspector drawer (plan §4.4
    'node anatomy' — a node is a summary of the agent's reasoning, not a
    labelled box). Every agent gets a real line from its actual outputs, not
    a generic placeholder."""
    if status in ("skipped", "cancelled") and skip_reason:
        # P2.7/P2.12 — a node that deliberately did not run says why. "no
        # output produced" on a skipped node reads as a failure, which is the
        # opposite of what a plan-gated skip or an early exit means.
        return f"{'Cancelled' if status == 'cancelled' else 'Skipped'} — {skip_reason}"
    if not outputs:
        return "no output produced"
    if agent_name == "distress" or agent_name == "distress_check":
        det = outputs.get("detection") or {}
        if det.get("is_distress"):
            return f"DISTRESS DETECTED: {det.get('matched_phrase') or 'Emergency signal'}"
        return "No distress flag — standard marine routing"
    if agent_name == "language_ingress":
        lang = outputs.get("detected_language") or "en"
        return f"Language: {lang.upper()} · Normalized to standard query"
    if agent_name == "planning":
        intents = outputs.get("matched_intent_rows") or []
        intent_str = intents[0] if intents else "STANDARD"
        return f"Intent {intent_str} · Fanned out to 3 specialist agents"
    if agent_name == "risk_assessment":
        return f"{outputs.get('go_no_go', '?')}: {outputs.get('reason', 'no reason recorded')}"
    if agent_name == "geospatial":
        imbl = outputs.get("imbl_distance_nm")
        imbl_str = f"{imbl:.1f}" if isinstance(imbl, (int, float)) else str(imbl or "?")
        return f"IMBL {imbl_str} nm · MPA violation={outputs.get('mpa_violation', False)}"
    if agent_name == "weather_intelligence":
        # weather_intelligence.run puts readings under hourly[0], never at the top level.
        hs = (outputs.get("hourly") or [{}])[0].get("wave_height")
        hs_str = f"{hs:.1f}" if isinstance(hs, (int, float)) and math.isfinite(hs) else "?"
        return f"Hs {hs_str} m · lightning={outputs.get('lightning_active', False)}"
    if agent_name == "ocean_analytics":
        tide = outputs.get("tide")
        tide_desc = "Slack tide"
        if isinstance(tide, dict):
            state = tide.get("tidal_state") or "Slack"
            station = tide.get("station_name") or tide.get("station_code") or ""
            sn = tide.get("spring_neap")
            sn_str = f", {sn}" if sn and sn != "UNKNOWN" else ""
            st_str = f" ({station})" if station else ""
            tide_desc = f"{state.title()}{st_str}{sn_str}"
        elif tide:
            tide_desc = str(tide).title()

        pfz = outputs.get("nearest_pfz")
        pfz_str = ""
        if isinstance(pfz, dict) and pfz.get("found"):
            dist = pfz.get("distance_km")
            compass = pfz.get("compass") or ""
            compass_str = f" {compass}" if compass else ""
            pfz_str = f" · Nearest PFZ: {dist} km{compass_str}"
        elif isinstance(pfz, dict) and pfz.get("distance_km") is not None:
            pfz_str = f" · Nearest PFZ: {pfz.get('distance_km')} km"
        return f"Tide: {tide_desc}{pfz_str}"
    if agent_name == "visualization":
        layers = outputs.get("map_layers") or []
        charts = outputs.get("chart_specs") or []
        return f"Generated {len(layers)} map layers and {len(charts)} chart specs"
    if agent_name == "reporting":
        citations = outputs.get("citations", [])
        if citations:
            return f"Assembled the narrative, citing {len(citations)} source{'s' if len(citations) != 1 else ''}."
        eng = outputs.get("final_english_response")
        if eng:
            return eng
        return "Synthesized final narrative with authoritative citations"
    if agent_name == "language_egress":
        return "Translated the verdict and reasoning back to the query's language."
    if agent_name == "critic":
        if status == "degraded":
            return "Critic unavailable — narrative shipped unreviewed"
        n = len(outputs.get("issues", []))
        return f"{n} issue(s) fixed over {outputs.get('critic_iteration_count', '?')} iteration(s)" if n else "passed all 5 rubric items"
    first_items = []
    for k, v in list(outputs.items())[:2]:
        if isinstance(v, dict):
            inner = ", ".join(f"{dk}: {dv}" for dk, dv in list(v.items())[:2])
            first_items.append(f"{k} ({inner})")
        else:
            first_items.append(f"{k}={v}")
    return ", ".join(first_items) or "no output produced"


def _get_val(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def build_trace_graph(query_id: str, rows: list[Any]) -> TraceGraph:
    nodes: list[TraceNode] = []
    seen_agents: set[str] = set()
    critic_row: Any = None

    # Runs per agent, and their summed time. Before this, a re-run was dropped without a trace: the
    # second Critic pass, the re-invoked specialist and the second Reporting were simply missing
    # from the replay, so the loop the Critic exists to run was invisible on /reasoning.
    run_counts: dict[str, int] = {}
    run_latency: dict[str, float] = {}
    for row in rows:
        name = _get_val(row, "agent_name")
        if name:
            run_counts[name] = run_counts.get(name, 0) + 1
            run_latency[name] = run_latency.get(name, 0.0) + float(_get_val(row, "latency_ms") or 0.0)

    for row in rows:
        agent_name = _get_val(row, "agent_name")
        if not agent_name or agent_name in seen_agents:
            continue  # one node per agent; its later runs are counted above, not drawn again
        seen_agents.add(agent_name)
        outputs = _get_val(row, "outputs") or {}
        status = _get_val(row, "status") or "ok"
        confidence = _get_val(row, "confidence") or "LOW_DATA"
        latency_ms = _get_val(row, "latency_ms")
        source_provenance = _get_val(row, "source_provenance")
        inputs_consumed = _get_val(row, "inputs_consumed") or {}

        if agent_name == "critic":
            critic_row = row

        # P2.1 — the same resolved label the live SSE span carries, from the
        # same function. A row persisted before `engine` existed falls to
        # engines.py's static table, so an old trace replays labelled rather
        # than blank.
        engine = engines.engine_for(agent_name, _get_val(row, "engine"))
        used_llm = engines.used_llm(agent_name, engine)
        tier = engines.AGENT_TIER.get(agent_name) if used_llm else None
        model = engines.model_for_tier(tier)

        nodes.append(TraceNode(
            id=agent_name,
            agent_name=agent_name,
            depth=_NODE_DEPTH.get(agent_name, 99),
            status=status,
            confidence_tier=confidence,
            confidence_score=_get_val(row, "confidence_score"),
            confidence_detail=_get_val(row, "confidence_detail"),
            latency_ms=latency_ms,
            reasoning_summary=_reasoning_summary(agent_name, outputs, status, _get_val(row, "skip_reason")),
            source_count=1 if source_provenance else 0,
            used_llm=used_llm,
            inputs_consumed=inputs_consumed,
            outputs=outputs,
            source_provenance=source_provenance,
            engine=engine,
            model=model,
            tier=tier,
            skip_reason=_get_val(row, "skip_reason"),
        ))

    for node in nodes:
        node.run_count = run_counts.get(node.agent_name, 1)
        if node.run_count > 1:
            node.latency_ms = round(run_latency[node.agent_name], 1)

    present = seen_agents
    status_by_agent = {n.agent_name: n.status for n in nodes}
    edges = []
    for a, b in (*_LINEAR_EDGES, *_FANOUT_EDGES):
        if a not in present or b not in present:
            continue
        if a == "reporting" and "critic" in present and b == "language_egress":
            continue
        # P2.12 — an edge INTO a node that was cancelled is drawn dotted. The
        # node itself carries the reason; the edge is what makes "this branch
        # was pending and got stopped" visible at a glance on the graph.
        cancelled = status_by_agent.get(b) == "cancelled"
        edges.append(TraceEdge(
            **{"from": a, "to": b},
            kind="cancelled" if cancelled else "handoff",
            label="cancelled" if cancelled else b,
        ))
    # The dashed re-invocation loop: one edge per issue the Critic actually found
    if critic_row is not None:
        c_outputs = _get_val(critic_row, "outputs") or {}
        for issue in c_outputs.get("issues", []):
            target = issue.get("reinvoke_agent")
            if target in present:
                edges.append(TraceEdge(**{"from": "critic", "to": target}, kind="critic_loop", label=issue.get("rubric_item", "issue")))

    groups = [
        TraceGroup(id=f"fanout_{i}", node_ids=[n for n in grp if n in present])
        for i, grp in enumerate(_FANOUT_GROUPS)
        if any(n in present for n in grp)
    ]
    return TraceGraph(query_id=query_id, nodes=nodes, edges=edges, groups=groups)


@router.get("/traces/recent")
@router.get("/api/traces/recent")
def get_recent_traces() -> list[dict[str, Any]]:
    """Returns metadata for recent query traces for the Reasoning page switcher."""
    if _RECENT_SUMMARIES:
        return _RECENT_SUMMARIES

    # Fall back to Postgres (e.g. after a backend restart). Every field comes
    # from the stored rows; one the rows don't hold is None, never a stand-in
    # value — this used to return "HIGH" and 1250 ms for every trace.
    # Security/Sentinel/feedback rows share the table but are not queries.
    try:
        db = get_sessionmaker()()
        try:
            rows = db.execute(text(recent_traces_sql())).mappings().all()
            return [recent_summary_from_row(dict(r)) for r in rows]
        finally:
            db.close()
    except Exception:
        pass

    return _RECENT_SUMMARIES


@router.get("/trace/{query_id}")
def get_trace(query_id: str) -> TraceGraph:
    # 1. First check in-memory trace cache (guarantees offline / DB-less dev works)
    if query_id in _RECENT_TRACES:
        cached = _RECENT_TRACES[query_id]
        return build_trace_graph(query_id, cached["rows"])

    try:
        qid = uuid.UUID(query_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="query_id must be a UUID")

    # 2. Fall back to Postgres if available
    try:
        db = get_sessionmaker()()
        try:
            rows = get_trace_entries(db, query_id=qid)
        finally:
            db.close()
        if rows:
            return build_trace_graph(query_id, rows)
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"no trace recorded for query_id {query_id}")


class PersonaRenderRequest(BaseModel):
    query_id: str
    persona: Literal["fisherman", "commercial_navigator", "researcher", "coastal_authority"]
    # P3.13 (orca_final §15.2) — "speak to me in Telugu" re-renders the
    # ALREADY-ANSWERED query in a new language, same zero-re-query contract
    # as the persona switch: no agent runs again, only the wording changes.
    # None keeps today's behaviour (English only).
    language: str | None = None


class PersonaRenderResponse(BaseModel):
    query_id: str
    persona: str
    final_english_response: str
    final_vernacular_response: str | None = None
    language: str | None = None
    confidence_tier: str
    citations: list[dict[str, Any]]


def _rows_to_agent_results(rows: list[AuditTraceLog]) -> list[AgentResult]:
    """Rebuilds the AgentResult set from stored rows alone — the same shape
    orca/graph/graph.py's reporting_run reconstructs from live ORCAState,
    built here from Postgres instead so `/render` never touches a running
    graph or a specialist agent."""
    results = []
    for row in rows:
        # _get_val, not attribute access: rows arrive either as ORM objects
        # (Postgres) or as the plain audit_trace_log dicts the in-memory ring
        # buffer holds. build_trace_graph has always read them this way; this
        # function had not, so a cache-served re-render crashed on .agent_name.
        agent_name = _get_val(row, "agent_name")
        if agent_name in ("reporting", "critic", "language_ingress", "language_egress"):
            continue  # not specialist facts — Reporting re-synthesizes from the rest
        prov = _get_val(row, "source_provenance") or {}
        results.append(AgentResult(
            agent_name=agent_name,
            query_id=str(_get_val(row, "query_id")),
            reasoning_depth=coerce_reasoning_depth("STANDARD"),
            inputs_consumed=_get_val(row, "inputs_consumed") or {},
            outputs=_get_val(row, "outputs") or {},
            source_provenance=SourceProvenance(
                dataset=prov.get("dataset", "unknown"),
                acquisition_timestamp=prov.get("acquisition_timestamp", ""),
                freshness_minutes=prov.get("freshness_minutes", 0),
            ),
            confidence=Confidence(
                score=coerce_confidence_score(_get_val(row, "confidence") or "LOW_DATA"),
                rationale="replayed from audit_trace_log",
            ),
            status=coerce_status(_get_val(row, "status")),
            error_detail=_get_val(row, "error_detail"),
        ))
    return results


def render_query(query_id: str, persona: str, language: str | None = None) -> PersonaRenderResponse:
    """The actual re-render — calls ONLY orca.agents.reporting, never a
    specialist agent, never the graph, which is what makes this a
    zero-re-query operation (Phase 3 exit criterion 3 / differentiator 7).
    Every number in the response is byte-identical to the original answer;
    only the wording (and, with `language` set, the script) changes.

    Extracted from the `/render` route (P3.13) so `orca/api/main.py`'s
    deterministic "speak to me in Telugu" handler can call this directly —
    an in-process function call, not a second HTTP round-trip to itself."""
    # Same two-tier read as GET /trace/{query_id}: the in-memory ring buffer
    # first, Postgres second. Reading only Postgres here meant a query
    # answered while the DB was offline was inspectable on /reasoning but
    # 404'd on the persona switcher — one surface saying the answer exists
    # and the other saying it doesn't, for the same query_id.
    cached = _RECENT_TRACES.get(query_id)
    rows = cached["rows"] if cached else []

    if not rows:
        try:
            qid = uuid.UUID(query_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="query_id must be a UUID")
        db = get_sessionmaker()()
        try:
            rows = get_trace_entries(db, query_id=qid)
        finally:
            db.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"no stored result for query_id {query_id}")

    results = _rows_to_agent_results(rows)

    def _row(agent: str) -> Any:
        return next((r for r in rows if _get_val(r, "agent_name") == agent), None)

    verdict_row = _row("risk_assessment")
    verdict = (_get_val(verdict_row, "outputs") or {}) if verdict_row else {}
    query_row = _row("planning")
    query_text = (_get_val(query_row, "inputs_consumed") or {}).get("query", "") if query_row else ""

    assembled = reporting.assemble_response(query_id, results)
    # A re-render reads back what the original run recorded; geospatial's
    # inputs_consumed is where the position it actually used was persisted, so
    # the re-rendered narrative claims the same location the first one did.
    geo_row = _row("geospatial")
    user_location = (_get_val(geo_row, "inputs_consumed") or {}).get("user_location") if geo_row else None
    narrative = reporting.synthesize_narrative(
        query_text, verdict, results, persona=persona, user_location=user_location,
    )

    vernacular: str | None = None
    if language and language != "en":
        from orca.agents.language import _ALL_LANGUAGES, translate_from_english

        if language in _ALL_LANGUAGES:
            try:
                vernacular = translate_from_english(narrative, target=language)  # type: ignore[arg-type]
            except RuntimeError:
                # Degrade to English rather than fail the re-render — same
                # contract as language_egress (principle 3: say so, don't hide
                # it). The caller sees `final_vernacular_response is None` and
                # `language` echoed back, so it can fall back visibly.
                vernacular = None

    return PersonaRenderResponse(
        query_id=query_id,
        persona=persona,
        final_english_response=narrative,
        final_vernacular_response=vernacular,
        language=language,
        confidence_tier=assembled.confidence_tier,
        citations=[
            {
                "agent_name": c.agent_name, "dataset": c.dataset,
                "acquisition_timestamp": c.acquisition_timestamp, "freshness_minutes": c.freshness_minutes,
            }
            for c in assembled.citations
        ],
    )


@router.post("/render")
def render_persona(req: PersonaRenderRequest) -> PersonaRenderResponse:
    """Re-renders an already-answered query under a new persona and/or
    language. Thin HTTP wrapper — see `render_query` for the actual logic."""
    return render_query(req.query_id, req.persona, req.language)
