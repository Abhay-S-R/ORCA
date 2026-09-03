"""Phase 3 D1 Day 15 contracts (plan §5.1): `TraceGraph` (the `/reasoning`
replay payload) and `PersonaRender` (`POST /render`). Both read
`audit_trace_log` rows already persisted by orca/trace.py's
run_traced_node + orca/db/repositories.persist_trace_entries — neither
route re-invokes a single specialist agent. `POST /render` calls only Agent
9 (orca/agents/reporting.py), asserted in tests/unit/test_trace_routes.py.
"""
from __future__ import annotations

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
    if agent_name == "risk_assessment":
        return f"{outputs.get('go_no_go', '?')}: {outputs.get('reason', 'no reason recorded')}"
    if agent_name == "geospatial":
        return f"IMBL {outputs.get('imbl_distance_nm', '?')} nm · MPA violation={outputs.get('mpa_violation', '?')}"
    if agent_name == "weather_intelligence":
        return f"Hs {outputs.get('wave_height', '?')} m · lightning={outputs.get('lightning_active', '?')}"
    if agent_name == "critic":
        if status == "degraded":
            return "Critic unavailable — narrative shipped unreviewed"
        n = len(outputs.get("issues", []))
        return f"{n} issue(s) fixed over {outputs.get('critic_iteration_count', '?')} iteration(s)" if n else "passed all 5 rubric items"
    first_items = list(outputs.items())[:2]
    return ", ".join(f"{k}={v}" for k, v in first_items) or "no output produced"


def build_trace_graph(query_id: str, rows: list[AuditTraceLog]) -> TraceGraph:
    nodes: list[TraceNode] = []
    seen_agents: set[str] = set()
    critic_row: AuditTraceLog | None = None

    for row in rows:
        if row.agent_name in seen_agents:
            continue  # a re-run within one query_id keeps only its first appearance
        seen_agents.add(row.agent_name)
        outputs = row.outputs or {}
        if row.agent_name == "critic":
            critic_row = row
        nodes.append(TraceNode(
            id=row.agent_name,
            agent_name=row.agent_name,
            depth=_NODE_DEPTH.get(row.agent_name, 99),
            status=row.status,
            confidence_tier=row.confidence or "LOW_DATA",
            latency_ms=row.latency_ms,
            reasoning_summary=_reasoning_summary(row.agent_name, outputs, row.status),
            source_count=1 if row.source_provenance else 0,
            used_llm=row.agent_name in _LLM_AGENTS,
            inputs_consumed=row.inputs_consumed or {},
            outputs=outputs,
            source_provenance=row.source_provenance,
        ))

    present = seen_agents
    edges = [
        TraceEdge(**{"from": a, "to": b}, kind="handoff", label=b)
        for a, b in (*_LINEAR_EDGES, *_FANOUT_EDGES)
        if a in present and b in present and not (a == "reporting" and "critic" in present and b == "language_egress")
    ]
    # The dashed re-invocation loop (plan §4.4 edge style, §7 pulled-forward
    # differentiator 5): one edge per issue the Critic actually found and
    # revised, from critic to the specialist whose output the issue traced
    # back to (orca/agents/critic.py's deterministic _REINVOKE_MAP — never a
    # free-text guess here either).
    if critic_row is not None:
        for issue in (critic_row.outputs or {}).get("issues", []):
            target = issue.get("reinvoke_agent")
            if target in present:
                edges.append(TraceEdge(**{"from": "critic", "to": target}, kind="critic_loop", label=issue.get("rubric_item", "issue")))

    groups = [
        TraceGroup(id=f"fanout_{i}", node_ids=[n for n in grp if n in present])
        for i, grp in enumerate(_FANOUT_GROUPS)
        if any(n in present for n in grp)
    ]
    return TraceGraph(query_id=query_id, nodes=nodes, edges=edges, groups=groups)


@router.get("/trace/{query_id}")
def get_trace(query_id: str) -> TraceGraph:
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
        raise HTTPException(status_code=404, detail=f"no trace recorded for query_id {query_id}")
    return build_trace_graph(query_id, rows)


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
