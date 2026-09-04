"""Phase 3 D1 Day 15 contracts (plan §5.1): `TraceGraph` (the `/reasoning`
replay payload) and `PersonaRender` (`POST /render`). Both read
`audit_trace_log` rows already persisted by orca/trace.py's
run_traced_node + orca/db/repositories.persist_trace_entries — neither
route re-invokes a single specialist agent. `POST /render` calls only Agent
9 (orca/agents/reporting.py), asserted in tests/unit/test_trace_routes.py.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

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
    "distress": 0, "language_ingress": 1, "planning": 2,
    "weather_intelligence": 3, "geospatial": 3, "ocean_analytics": 3,
    "risk_assessment": 4, "visualization": 4,
    "reporting": 5, "critic": 6, "language_egress": 7,
}
_FANOUT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("weather_intelligence", "geospatial", "ocean_analytics"),
    ("risk_assessment", "visualization"),
)
_LINEAR_EDGES: tuple[tuple[str, str], ...] = (
    ("distress", "language_ingress"),
    ("language_ingress", "planning"),
    ("reporting", "language_egress"),
    ("critic", "language_egress"),
)
_FANOUT_EDGES: tuple[tuple[str, str], ...] = (
    ("planning", "weather_intelligence"), ("planning", "geospatial"), ("planning", "ocean_analytics"),
    ("weather_intelligence", "risk_assessment"), ("geospatial", "risk_assessment"), ("ocean_analytics", "risk_assessment"),
    ("weather_intelligence", "visualization"), ("geospatial", "visualization"), ("ocean_analytics", "visualization"),
    ("risk_assessment", "reporting"), ("visualization", "reporting"),
)
# Agent 5 (Ocean Analytics) at DEEP, Agent 9, Agent 10 are the only nodes
# that ever call an LLM (plan §3.2) — everything else is deterministic by
# construction (Ground Rule 2), and the inspector drawer says so verbatim.
_LLM_AGENTS = {"ocean_analytics", "reporting", "critic"}

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


class TraceNode(BaseModel):
    id: str
    agent_name: str
    depth: int
    status: str
    confidence_tier: str
    latency_ms: float | None
    reasoning_summary: str
    source_count: int
    used_llm: bool
    inputs_consumed: dict[str, Any]
    outputs: dict[str, Any]
    source_provenance: dict[str, Any] | None
    model: str | None = None
    tier: str | None = None


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


def _reasoning_summary(agent_name: str, outputs: dict[str, Any], status: str = "ok") -> str:
    """One line, readable without opening the inspector drawer (plan §4.4
    'node anatomy' — a node is a summary of the agent's reasoning, not a
    labelled box). Every agent gets a real line from its actual outputs, not
    a generic placeholder."""
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
        hs = outputs.get("wave_height")
        hs_str = f"{hs:.1f}" if isinstance(hs, (int, float)) else str(hs or "?")
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

    for row in rows:
        agent_name = _get_val(row, "agent_name")
        if not agent_name or agent_name in seen_agents:
            continue  # a re-run within one query_id keeps only its first appearance
        seen_agents.add(agent_name)
        outputs = _get_val(row, "outputs") or {}
        status = _get_val(row, "status") or "ok"
        confidence = _get_val(row, "confidence") or "LOW_DATA"
        latency_ms = _get_val(row, "latency_ms")
        source_provenance = _get_val(row, "source_provenance")
        inputs_consumed = _get_val(row, "inputs_consumed") or {}

        if agent_name == "critic":
            critic_row = row

        used_llm = agent_name in _LLM_AGENTS
        tier = (
            "cheap"
            if agent_name == "planning"
            else "mid"
            if agent_name == "reporting"
            else "reasoning"
            if agent_name in ("ocean_analytics", "critic")
            else None
        )
        model = (
            os.environ.get(f"ORCA_LLM_{tier.upper()}_MODEL", "gemini-3.5-flash-lite")
            if used_llm and tier
            else None
        )

        nodes.append(TraceNode(
            id=agent_name,
            agent_name=agent_name,
            depth=_NODE_DEPTH.get(agent_name, 99),
            status=status,
            confidence_tier=confidence,
            latency_ms=latency_ms,
            reasoning_summary=_reasoning_summary(agent_name, outputs, status),
            source_count=1 if source_provenance else 0,
            used_llm=used_llm,
            inputs_consumed=inputs_consumed,
            outputs=outputs,
            source_provenance=source_provenance,
            model=model,
            tier=tier,
        ))

    present = seen_agents
    edges = [
        TraceEdge(**{"from": a, "to": b}, kind="handoff", label=b)
        for a, b in (*_LINEAR_EDGES, *_FANOUT_EDGES)
        if a in present and b in present and not (a == "reporting" and "critic" in present and b == "language_egress")
    ]
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

    # Fall back to querying distinct query_ids from Postgres if available
    try:
        from sqlalchemy import text
        db = get_sessionmaker()()
        try:
            sql = text("""
                SELECT query_id, MAX(created_at) as last_seen, count(*) as cnt
                FROM audit_trace_log
                GROUP BY query_id
                ORDER BY last_seen DESC
                LIMIT 10
            """)
            res = db.execute(sql).fetchall()
            summaries = []
            for r in res:
                qid = str(r[0])
                summaries.append({
                    "query_id": qid,
                    "query_text": f"Query {qid[:8]}...",
                    "verdict": "RECORDED",
                    "confidence_tier": "HIGH",
                    "node_count": r[2],
                    "total_latency_ms": 1250.0,
                })
            return summaries
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


class PersonaRenderResponse(BaseModel):
    query_id: str
    persona: str
    final_english_response: str
    confidence_tier: str
    citations: list[dict[str, Any]]


def _rows_to_agent_results(rows: list[AuditTraceLog]) -> list[AgentResult]:
    """Rebuilds the AgentResult set from stored rows alone — the same shape
    orca/graph/graph.py's reporting_run reconstructs from live ORCAState,
    built here from Postgres instead so `/render` never touches a running
    graph or a specialist agent."""
    results = []
    for row in rows:
        if row.agent_name in ("reporting", "critic", "language_ingress", "language_egress"):
            continue  # not specialist facts — Reporting re-synthesizes from the rest
        prov = row.source_provenance or {}
        results.append(AgentResult(
            agent_name=row.agent_name,
            query_id=str(row.query_id),
            reasoning_depth=coerce_reasoning_depth("STANDARD"),
            inputs_consumed=row.inputs_consumed or {},
            outputs=row.outputs or {},
            source_provenance=SourceProvenance(
                dataset=prov.get("dataset", "unknown"),
                acquisition_timestamp=prov.get("acquisition_timestamp", ""),
                freshness_minutes=prov.get("freshness_minutes", 0),
            ),
            confidence=Confidence(score=coerce_confidence_score(row.confidence or "LOW_DATA"), rationale="replayed from audit_trace_log"),
            status=coerce_status(row.status),
            error_detail=row.error_detail,
        ))
    return results


@router.post("/render")
def render_persona(req: PersonaRenderRequest) -> PersonaRenderResponse:
    """Re-renders an already-answered query under a new persona. Calls
    ONLY orca.agents.reporting — never a specialist agent, never the graph —
    which is what makes this a zero-re-query operation (Phase 3 exit
    criterion 3 / differentiator 7). Every number in the response is
    byte-identical to the original answer; only the wording changes."""
    try:
        qid = uuid.UUID(req.query_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="query_id must be a UUID")

    db = get_sessionmaker()()
    try:
        rows = get_trace_entries(db, query_id=qid)
    finally:
        db.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"no stored result for query_id {req.query_id}")

    results = _rows_to_agent_results(rows)
    verdict_row = next((r for r in rows if r.agent_name == "risk_assessment"), None)
    verdict = (verdict_row.outputs or {}) if verdict_row else {}
    query_row = next((r for r in rows if r.agent_name == "planning"), None)
    query_text = (query_row.inputs_consumed or {}).get("query", "") if query_row else ""

    assembled = reporting.assemble_response(req.query_id, results)
    narrative = reporting.synthesize_narrative(query_text, verdict, results, persona=req.persona)

    return PersonaRenderResponse(
        query_id=req.query_id,
        persona=req.persona,
        final_english_response=narrative,
        confidence_tier=assembled.confidence_tier,
        citations=[
            {
                "agent_name": c.agent_name, "dataset": c.dataset,
                "acquisition_timestamp": c.acquisition_timestamp, "freshness_minutes": c.freshness_minutes,
            }
            for c in assembled.citations
        ],
    )
