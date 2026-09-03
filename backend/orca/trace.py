"""OTel spans on every agent node entry/exit, feeding audit_trace_log (plan
§5.3, §9.18). One pipeline, two views: the same span data is a real OTel
span (for whichever exporter gets configured later — OTEL_EXPORTER_OTLP_ENDPOINT
unset means it stays local, per .env.example) AND a plain JSON-serializable
dict appended to ORCAState.audit_trace_log, because that field is what
actually gets persisted to Postgres (infra/db/001_init.sql) and what the
Phase 3 reasoning-graph UI reads — an OTel Span object is neither
JSON-serializable nor something a graph node should be returning as state.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.state import ORCAState

# A bare TracerProvider with no exporter attached is intentional for Phase 1
# — spans are created and can be inspected via the SDK, but nothing is
# shipped anywhere until OTEL_EXPORTER_OTLP_ENDPOINT names a collector
# (plan .env.example). Attaching an exporter later is additive.
_provider = TracerProvider()
trace.set_tracer_provider(_provider)
_tracer = trace.get_tracer("orca")


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def run_traced_node(
    agent_name: str, fn: Callable[[ORCAState], AgentResult], state: ORCAState
) -> tuple[AgentResult, dict[str, Any]]:
    """Wraps one agent's run(state) call in a real OTel span AND produces the
    plain-dict audit_trace_log entry for that same execution. Every graph
    node in orca/graph/ calls this rather than fn(state) directly — that is
    what "on every node entry and exit" means in practice.

    §5.7 agent exception boundary: an agent raising becomes a `status="failed"`
    AgentResult here, not a crashed graph — one specialist failing degrades
    the answer, it never takes the request down."""
    started = time.time()
    with _tracer.start_as_current_span(agent_name) as span:
        span.set_attribute("agent_name", agent_name)
        span.set_attribute("query_id", state.get("query_id", ""))
        try:
            result = fn(state)
            span.set_attribute("status", result.status)
            span.set_attribute("confidence", result.confidence.score)
        except Exception as exc:  # noqa: BLE001 — deliberately blind: any agent
            # failure must be caught here, whatever its type, so the graph continues.
            span.set_attribute("status", "failed")
            span.record_exception(exc)
            result = AgentResult(
                agent_name=agent_name,
                query_id=state.get("query_id", ""),
                reasoning_depth="SHALLOW",
                inputs_consumed={},
                outputs={},
                source_provenance=SourceProvenance(dataset="n/a — agent raised", acquisition_timestamp="", freshness_minutes=0),
                confidence=Confidence(score="LOW_DATA", rationale="Agent raised an unhandled exception"),
                status="failed",
                error_detail=str(exc),
            )
    ended = time.time()
    entry = {
        "agent_name": result.agent_name,
        "query_id": result.query_id,
        "status": result.status,
        "confidence": result.confidence.score,
        "started_at": _utc_iso(started),
        "ended_at": _utc_iso(ended),
        "latency_ms": round((ended - started) * 1000, 1),
        "error_detail": result.error_detail,
    }
    return result, entry


def record_layer_metric(
    layer_id: str, layer_load_ms: float, render_ms: float, payload_bytes: int, dropped_frames: int
) -> None:
    """§4.7 `/map` instrumentation: `layer_load_ms`, `render_ms`, `payload_bytes`,
    dropped-frame count per layer toggle. "Logged to the console in dev and to
    the existing OTel stream in staging" — the frontend does the dev console.log
    itself; this is that same stream's staging half, reusing the tracer already
    set up above rather than standing up a second metrics pipeline. Engineering
    visibility only, a budget check against §4.7's table, not an observability
    platform — so no audit_trace_log entry, no AgentResult, just a span."""
    with _tracer.start_as_current_span("layer_paint") as span:
        span.set_attribute("layer_id", layer_id)
        span.set_attribute("layer_load_ms", layer_load_ms)
        span.set_attribute("render_ms", render_ms)
        span.set_attribute("payload_bytes", payload_bytes)
        span.set_attribute("dropped_frames", dropped_frames)


def make_stub_entry(agent_name: str, query_id: str, note: str) -> dict[str, Any]:
    """Trace entry for a fixture-backed stub node (plan §6 Fixture Strategy)
    — an agent that hasn't been built yet, standing in so the graph can be
    wired end to end. Always LOW_DATA: a stub is never allowed to read as a
    real, confident measurement in the trace."""
    now = _utc_iso(time.time())
    return {
        "agent_name": agent_name, "query_id": query_id, "status": "ok", "confidence": "LOW_DATA",
        "started_at": now, "ended_at": now, "latency_ms": 0.0, "error_detail": note,
    }
