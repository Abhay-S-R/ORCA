"""Sentinel's background execution — the DB + dispatch + audit wiring around
the pure logic in orca/agents/sentinel.py, plus the poll loop itself.

Scheduler: a bare asyncio interval task started from the FastAPI lifespan.
ponytail: one periodic job does not need APScheduler + a job store; a
`while True: sleep(interval)` task is the whole scheduler. Move to a real
worker only if the loop and the API ever contend for the process.

Single-instance: a Postgres session-level advisory lock
(pg_try_advisory_lock). If a second process holds it, this tick is skipped —
two processes never double-fire a watch (plan §11, exit criterion covered by
tests/unit/test_sentinel.py::test_second_process_skips).
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.agents import sentinel
from orca.db.models import AuditTraceLog
from orca.db.notifications_models import Notification
from orca.db.notifications_repo import (
    create_notification,
    list_enabled_watches,
    mark_watch_fired,
    release_sentinel_lock,
    try_sentinel_lock,
    watch_location,
)
from orca.notifications.dispatcher import get_dispatcher

logger = logging.getLogger("orca.sentinel")

POLL_INTERVAL_SECONDS = int(os.environ.get("ORCA_SENTINEL_INTERVAL_S", "120"))

# Optional graph-escalation hook. Left None by default so importing this
# module never drags in langgraph; the runtime sets it at startup if the
# graph is importable. Signature: (initial_state: dict) -> dict (final state).
EscalateFn = Callable[[dict[str, Any]], dict[str, Any]]


def _last_watch_payload(db: Session, watch_id: uuid.UUID) -> dict[str, Any] | None:
    row = (
        db.query(Notification)
        .filter(Notification.watch_id == watch_id)
        .order_by(Notification.created_at.desc())
        .first()
    )
    return row.rendered_payload.get("snapshot") if row and row.rendered_payload else None


def _persist_audit(
    db: Session, *, query_id: str, watch_id: uuid.UUID, decision: sentinel.WatchDecision, dispatch_status: str
) -> None:
    """One audit_trace_log row per Sentinel evaluation that fired. status
    'degraded' when the dispatch was SIMULATED (acceptance test C), 'ok'
    when it was a real in-app delivery."""
    db.add(
        AuditTraceLog(
            query_id=uuid.UUID(query_id),
            session_id=None,
            agent_name="sentinel",
            event="agent_complete" if dispatch_status == "sent" else "fallback",
            inputs_consumed={"watch_id": str(watch_id)},
            outputs={"title": decision.title, "severity": decision.severity, "dispatch": dispatch_status},
            source_provenance=None,
            confidence=decision.snapshot_payload.get("confidence", "LOW_DATA"),
            status="degraded" if dispatch_status != "sent" else "ok",
            error_detail=None,
        )
    )


def _write_session_history(db: Session, user_id: uuid.UUID, query_id: str, decision: sentinel.WatchDecision) -> None:
    """Write the broadcast into conversation_turns so a later on-demand query
    from the same user is consistent with what they were already told — the
    one thing that makes proactive alerting feel like one system (plan §4 D2
    Day 17). Best-effort: the user may have no open session row."""
    try:
        session_id = db.execute(
            text("SELECT id FROM sessions WHERE user_id = :uid ORDER BY last_seen_at DESC LIMIT 1"),
            {"uid": user_id},
        ).scalar_one_or_none()
        if session_id is None:
            return
        db.execute(
            text(
                "INSERT INTO conversation_turns (session_id, query_id, role, text_english) "
                "VALUES (:sid, :qid, 'assistant', :txt)"
            ),
            {"sid": session_id, "qid": query_id, "txt": f"[Sentinel] {decision.title}: {decision.body}"},
        )
    except Exception:
        logger.debug("session_history write skipped", exc_info=True)


def dispatch_decision(
    db: Session,
    *,
    user_id: uuid.UUID,
    watch_id: uuid.UUID,
    channels: list[str],
    decision: sentinel.WatchDecision,
) -> Notification:
    """Write the notification row, then hand it to each requested channel's
    Dispatcher. in_app -> 'sent'; sms/ivr/ussd raise NotImplementedError,
    caught here -> the row is stored 'simulated' with the rendered payload
    verbatim, and the loop keeps going (never crashes — exit criterion 10)."""
    primary_channel = channels[0] if channels else "in_app"
    rendered = {
        "alert": decision.alert_payload,
        "snapshot": decision.snapshot_payload,
        "channels_requested": channels,
    }

    status = "sent"
    detail = "written to the in-app feed"
    if primary_channel != "in_app":
        try:
            result = get_dispatcher(primary_channel, db).send(recipient={"user_id": str(user_id)}, rendered_payload=rendered)
            status, detail = result.status, result.detail
        except NotImplementedError as exc:
            status, detail = "simulated", str(exc)
            logger.info("watch %s: %s dispatch simulated — %s", watch_id, primary_channel, exc)

    rendered["dispatch_detail"] = detail
    note = create_notification(
        db,
        user_id=user_id,
        watch_id=watch_id,
        query_id=uuid.UUID(decision.query_id),
        severity=decision.severity,
        title=decision.title,
        body=decision.body,
        channel=primary_channel,
        status=status,
        rendered_payload=rendered,
    )
    # in_app always also lands in the feed even if another channel was primary.
    get_dispatcher("in_app", db).send(recipient={"user_id": str(user_id)}, rendered_payload=rendered)
    _persist_audit(db, query_id=decision.query_id, watch_id=watch_id, decision=decision, dispatch_status=status)
    _write_session_history(db, user_id, decision.query_id, decision)
    return note


def run_poll_cycle(db: Session, *, escalate: EscalateFn | None = None) -> list[sentinel.WatchDecision]:
    """One tick. Returns every decision (fired or not) for observability /
    tests. Acquires the advisory lock; if another process holds it, returns
    [] without evaluating anything."""
    if not try_sentinel_lock(db):
        logger.debug("sentinel lock held by another process — skipping tick")
        return []

    decisions: list[sentinel.WatchDecision] = []
    try:
        for watch in list_enabled_watches(db):
            loc = watch_location(watch)
            if loc is None:
                continue
            decision = sentinel.evaluate(
                watch_id=str(watch.id),
                watch_type=watch.watch_type,
                location=loc,
                location_name="your watch area" if watch.watch_area is not None else "your watch point",
                thresholds=dict(watch.thresholds or {}),
                last_payload=_last_watch_payload(db, watch.id),
            )
            decisions.append(decision)
            if not decision.fired:
                continue

            if escalate is not None:
                try:
                    escalate({
                        "query_id": decision.query_id,
                        "raw_user_query": f"sentinel watch {watch.watch_type} crossing",
                        "normalized_english_query": f"conditions at watch point: {decision.title}",
                        "reasoning_depth": "STANDARD",
                        "user_location": loc,
                        "distress_flag": False,
                    })
                except Exception:
                    logger.warning("watch %s escalation failed; dispatching cheap-check alert", watch.id, exc_info=True)

            dispatch_decision(
                db, user_id=watch.user_id, watch_id=watch.id,
                channels=list(watch.channels or ["in_app"]), decision=decision,
            )
            mark_watch_fired(db, watch.id)
        db.commit()
    finally:
        release_sentinel_lock(db)
    return decisions


# --------------------------------------------------------------------------
# asyncio loop — started/stopped from orca/api/main.py lifespan
# --------------------------------------------------------------------------

_task: asyncio.Task | None = None


async def _loop() -> None:
    from orca.db.engine import get_sessionmaker

    # Escalation is wired lazily so this module never hard-imports langgraph.
    escalate: EscalateFn | None = None
    try:
        from orca.graph.graph import build_graph

        _graph = build_graph()
        escalate = _graph.invoke  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        logger.info("sentinel: graph unavailable, running cheap-check-only alerts")

    while True:
        try:
            db = get_sessionmaker()()
            try:
                fired = [d for d in run_poll_cycle(db, escalate=escalate) if d.fired]
                if fired:
                    logger.info("sentinel: %d crossing(s) dispatched", len(fired))
            finally:
                db.close()
        except Exception:
            logger.warning("sentinel poll tick failed", exc_info=True)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_sentinel() -> None:
    global _task
    if os.environ.get("ORCA_SENTINEL_ENABLED", "1") != "1":
        logger.info("sentinel disabled (ORCA_SENTINEL_ENABLED != 1)")
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
        logger.info("sentinel poll loop started (interval %ds)", POLL_INTERVAL_SECONDS)


async def stop_sentinel() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
