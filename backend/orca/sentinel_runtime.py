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
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.agents import sentinel
from orca.channels import renderers
from orca.db.models import AuditTraceLog, User
from orca.db.notifications_models import Notification
from orca.db.notifications_repo import (
    create_notification,
    list_due_held_notifications,
    list_enabled_watches,
    mark_watch_fired,
    release_sentinel_lock,
    set_next_poll_at,
    try_sentinel_lock,
    users_with_departure_hour_set,
    watch_location,
)
from orca.db.repositories import user_home_port
from orca.notifications.dispatcher import get_dispatcher

logger = logging.getLogger("orca.sentinel")

POLL_INTERVAL_SECONDS = int(os.environ.get("ORCA_SENTINEL_INTERVAL_S", "120"))
# P5.17 — adaptive cadence: a watch whose last reading was close to firing is
# polled this often instead of at the base interval.
FAST_POLL_INTERVAL_SECONDS = max(30, POLL_INTERVAL_SECONDS // 4)

# P5.22 — quiet hours never hold a `danger`-severity alert (a NO_GO-shaped
# verdict, a CRITICAL geofence band, a new hazard): the whole point of quiet
# hours is "don't wake me for something that can wait", and none of these can.
_QUIET_HOURS_EXEMPT_SEVERITIES = frozenset({"danger"})

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


def _query_stream_shape(decision: sentinel.WatchDecision) -> dict[str, Any]:
    """Adapts a `WatchDecision` into the shape `orca/channels/renderers.py`
    is written against (the `_query_stream` final-event dict) — Sentinel's
    cheap check carries the same facts (verdict, wave/wind, lightning,
    cyclone) flatly in `snapshot_payload` rather than nested under
    `risk_assessment`/`weather_summary`. No boundary reading exists on this
    path (`cheap_check` does not compute one), so `hazard_breakdown` is
    empty — every renderer already treats a missing key as "no active
    hazard" via `.get()`, never as a fabricated SAFE value."""
    snap = decision.snapshot_payload
    if "band" in snap or "has_advisory" in snap:
        # P5.18 — geofence_approach / pfz_shift snapshots carry no
        # go_no_go/hazard shape at all (they are not a wave/wind verdict);
        # `_verdict_and_hazard`'s `.get("go_no_go", "UNKNOWN")` would
        # otherwise render "Verdict: None" over SMS/IVR/USSD, since the key
        # exists with value None rather than being absent. The crossing's own
        # title *is* the content for every channel here.
        return {
            "final_vernacular_response": decision.body,
            "risk_assessment": {"go_no_go": "ALERT"},
            "weather_summary": {},
            "hazard_breakdown": {},
        }
    return {
        "final_vernacular_response": decision.body,
        "risk_assessment": {"go_no_go": snap.get("go_no_go")},
        "weather_summary": {
            "lightning_active": snap.get("lightning_active"),
            "cyclone_alert": snap.get("cyclone_alert"),
        },
        "hazard_breakdown": {},
    }


# --------------------------------------------------------------------------
# P5.22 — quiet hours and per-severity escalation. Pure functions (no I/O),
# unit-testable without a DB — same discipline orca/agents/sentinel.py holds
# its own crossing logic to.
# --------------------------------------------------------------------------

def _parse_hhmm(value: str) -> dt_time:
    hh, mm = value.split(":")
    return dt_time(int(hh), int(mm))


def quiet_hours_window(quiet_hours: dict[str, Any] | None, *, now: datetime | None = None) -> tuple[bool, datetime | None]:
    """(currently inside the window, the UTC instant it next ends).

    `quiet_hours` is `users.quiet_hours` verbatim: `{"start": "22:00", "end":
    "06:00", "tz": "Asia/Kolkata"}`. Missing/malformed input means no window
    is configured — always `(False, None)`, never a guessed default window.
    Handles a window that wraps midnight (22:00-06:00), which is the whole
    point of quiet hours existing.
    """
    if not quiet_hours or not quiet_hours.get("start") or not quiet_hours.get("end"):
        return False, None
    try:
        tz = ZoneInfo(quiet_hours.get("tz") or "UTC")
        start_t, end_t = _parse_hhmm(quiet_hours["start"]), _parse_hhmm(quiet_hours["end"])
    except (ValueError, ZoneInfoNotFoundError, KeyError):
        return False, None

    local_now = (now or datetime.now(timezone.utc)).astimezone(tz)
    today = local_now.date()

    def _at(d: date, t: dt_time) -> datetime:
        return datetime.combine(d, t, tzinfo=tz)

    start_dt = _at(today, start_t)
    end_dt = _at(today, end_t)

    if start_t <= end_t:
        # Same-day window, e.g. 13:00-15:00.
        if start_dt <= local_now < end_dt:
            return True, end_dt.astimezone(timezone.utc)
        return False, None

    # Wraps midnight, e.g. 22:00-06:00.
    if local_now >= start_dt:
        return True, (end_dt + timedelta(days=1)).astimezone(timezone.utc)
    if local_now < end_dt:
        return True, end_dt.astimezone(timezone.utc)
    return False, None


def effective_channels(watch_channels: list[str], escalation: dict[str, Any] | None, severity: str) -> list[str]:
    """P5.22 — a watch's per-severity channel override. `escalation` is
    keyed by `Crossing.severity` (info/advisory/warning/danger) — the one
    vocabulary every `WatchDecision` carries regardless of watch type, unlike
    `go_no_go`, which `geofence_approach`/`pfz_shift` never produce. A
    missing or empty entry for this severity falls back to the watch's own
    `channels`, never to nothing."""
    if escalation and escalation.get(severity):
        return list(escalation[severity])
    return list(watch_channels)


def _is_near_threshold(watch_type: str, thresholds: dict[str, float], decision: sentinel.WatchDecision) -> bool:
    """P5.17 — 'within 20% of the threshold' as the adaptive-cadence
    trigger, defined per watch type since "close to firing" means something
    different for each: a wave-height watch compares its own reading against
    its threshold; a geofence watch is already inside the WATCH band or
    tighter; a verdict-based watch (weather/lightning/cyclone) is one step
    below NO_GO. `pfz_shift` has no numeric closeness to speak of (an
    advisory either exists or it doesn't) and always polls at the base rate.
    """
    snap = decision.snapshot_payload
    if watch_type == "geofence_approach":
        return snap.get("band") in ("WATCH", "WARNING", "CRITICAL")
    if watch_type == "wave_height":
        threshold, wave = thresholds.get("wave_height_m"), snap.get("wave_height_m")
        return threshold is not None and wave is not None and wave >= threshold * 0.8
    if watch_type in ("weather", "lightning", "cyclone"):
        return snap.get("go_no_go") == "CAUTION"
    return False


def flush_due_held_notifications(db: Session) -> int:
    """P5.22 — send every held notification whose quiet-hours window has
    ended. Re-dispatches the payload rendered when the alert first fired
    (nothing is re-evaluated against current conditions — the alert is what
    it was when it happened, not a fresh check run late), through the same
    channels it was headed for, then flips it to whatever `dispatch_decision`
    would have recorded immediately. Returns the count flushed."""
    flushed = 0
    for note in list_due_held_notifications(db):
        rendered = note.rendered_payload or {}
        by_channel = rendered.get("by_channel") or {}
        channels = rendered.get("channels_requested") or [note.channel]
        status = "sent"
        detail = "delivered after quiet hours"
        primary_channel = channels[0] if channels else "in_app"
        if primary_channel != "in_app":
            try:
                result = get_dispatcher(primary_channel, db).send(
                    recipient={"user_id": str(note.user_id)}, rendered_payload=rendered
                )
                status, detail = result.status, result.detail
            except NotImplementedError as exc:
                status, detail = "simulated", str(exc)
        get_dispatcher("in_app", db).send(recipient={"user_id": str(note.user_id)}, rendered_payload=rendered)
        for ch in by_channel:
            by_channel[ch]["status"] = status if ch == primary_channel else by_channel[ch].get("status", "simulated")
        rendered["dispatch_detail"] = detail
        note.status = status
        note.rendered_payload = rendered
        note.deliver_after = None
        flushed += 1
    if flushed:
        db.commit()
    return flushed


def _render_for_channel(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
    """P4.13 — the verbatim text for one channel, using the renderers that
    exist today (`channels/renderers.py`); a channel neither P4.13 nor P6.10
    has built is simply absent from `by_channel` rather than guessed at."""
    if channel == "in_app" or channel == "web":
        return {"body": renderers.render_web(payload).get("final_vernacular_response", "")}
    if channel == "sms":
        return {"body": renderers.render_sms(payload).body}
    if channel == "ivr":
        return {"body": renderers.render_ivr(payload).body}
    if channel == "ussd":
        return {"body": renderers.render_ussd(payload).body}
    # P6.10 — the five channels added alongside the original four; Sentinel's
    # escalation config (P5.22 `effective_channels()`) can name any of these,
    # and until now they silently rendered an empty body when it did.
    if channel == "whatsapp":
        return {"body": renderers.render_whatsapp(payload).body}
    if channel == "missed_call":
        return {"body": renderers.render_missed_call_callback(payload).body}
    if channel == "vhf":
        return {"body": renderers.render_vhf(payload).body}
    if channel == "harbour_board":
        return {"body": renderers.render_harbour_board(payload).body}
    return {"body": ""}


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
    stream_shape = _query_stream_shape(decision)
    # P4.13 — "what was sent" needs every enabled channel's own rendered
    # text, not only the primary one's dispatch status. Rendering is free
    # (pure functions, no I/O) even for channels that were not the primary
    # dispatch target this tick.
    by_channel: dict[str, Any] = {
        ch: {**_render_for_channel(ch, stream_shape), "status": "sent" if ch == "in_app" else "simulated"}
        for ch in dict.fromkeys([*channels, "in_app"])  # in_app always lands regardless of the primary
    }
    rendered: dict[str, Any] = {
        "alert": decision.alert_payload,
        "snapshot": decision.snapshot_payload,
        "channels_requested": channels,
        "by_channel": by_channel,
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
    by_channel[primary_channel]["status"] = status
    by_channel[primary_channel]["detail"] = detail

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


def _hold_decision(
    db: Session, *, user_id: uuid.UUID, watch_id: uuid.UUID, channels: list[str],
    decision: sentinel.WatchDecision, deliver_after: datetime,
) -> Notification:
    """P5.22 — write the notification fully rendered but undelivered, for
    `flush_due_held_notifications` to send once `deliver_after` passes.
    Shares `dispatch_decision`'s rendering so a held alert and an immediate
    one look identical once flushed."""
    stream_shape = _query_stream_shape(decision)
    by_channel: dict[str, Any] = {
        ch: {**_render_for_channel(ch, stream_shape), "status": "held"}
        for ch in dict.fromkeys([*channels, "in_app"])
    }
    rendered: dict[str, Any] = {
        "alert": decision.alert_payload,
        "snapshot": decision.snapshot_payload,
        "channels_requested": channels,
        "by_channel": by_channel,
        "dispatch_detail": f"held for quiet hours until {deliver_after.isoformat()}",
    }
    primary_channel = channels[0] if channels else "in_app"
    note = create_notification(
        db, user_id=user_id, watch_id=watch_id, query_id=uuid.UUID(decision.query_id),
        severity=decision.severity, title=decision.title, body=decision.body,
        channel=primary_channel, status="held", rendered_payload=rendered, deliver_after=deliver_after,
    )
    _persist_audit(db, query_id=decision.query_id, watch_id=watch_id, decision=decision, dispatch_status="held")
    return note


# R-NEW-16 — how long before the stored departure hour the digest goes out.
# Not user-configurable (only the hour itself is a stored preference).
_PRE_DAWN_BRIEFING_LEAD_HOURS = 2


def _due_pre_dawn_briefings(db: Session, *, now: datetime) -> int:
    """Once per local calendar day, `_PRE_DAWN_BRIEFING_LEAD_HOURS` before a
    registered fisherman's stored `typical_departure_hour`, send a cheap-check
    digest for their home port — the same tool path `sentinel.cheap_check`
    already uses for every watch, so this can never disagree with an on-demand
    answer for the same point. Returns the count sent."""
    sent = 0
    for user in users_with_departure_hour_set(db):
        quiet = user.quiet_hours or {}
        try:
            tz = ZoneInfo(quiet.get("tz") or "Asia/Kolkata")
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("Asia/Kolkata")
        local_now = now.astimezone(tz)
        today = local_now.date()
        if user.last_pre_dawn_briefing_date == today:
            continue
        target = (
            datetime.combine(today, dt_time(0, 0), tzinfo=tz)
            + timedelta(hours=user.typical_departure_hour - _PRE_DAWN_BRIEFING_LEAD_HOURS)
        )
        if local_now < target:
            continue
        home = user_home_port(user)
        if home is None:
            continue
        try:
            snap = sentinel.cheap_check(home["lat"], home["lon"])
        except Exception:
            logger.warning("pre-dawn briefing cheap_check failed for user %s", user.id, exc_info=True)
            continue
        severity = {"GO": "info", "CAUTION": "warning", "NO_GO": "danger"}.get(snap.go_no_go, "info")
        parts = [f"{snap.go_no_go} — {snap.reason}."]
        if snap.wave_height_m is not None:
            parts.append(f"Wave height {snap.wave_height_m:.1f} m.")
        if snap.wind_speed_ms is not None:
            parts.append(f"Wind {snap.wind_speed_ms:.1f} m/s.")
        create_notification(
            db, user_id=user.id,
            title=f"Pre-dawn briefing — {user.home_port_name or 'your home port'}",
            body=" ".join(parts), severity=severity, channel="in_app",
            rendered_payload={"kind": "pre_dawn_briefing", "snapshot": snap.as_payload()},
        )
        user.last_pre_dawn_briefing_date = today
        sent += 1
    return sent


_consecutive_lock_misses = 0
# A legitimate second instance (or a rolling deploy overlapping the old one)
# skips for a tick or two, which is normal and not worth a peep. Missing for
# longer than that is the lock-never-released failure mode audited
# 2026-09-22 (a killed process's dead connection still holding the lock) —
# say so loudly instead of leaving it in the debug line below, since nothing
# else here ever surfaces "no watch has fired in a while".
_LOCK_MISS_WARN_THRESHOLD = 5


def run_poll_cycle(db: Session, *, escalate: EscalateFn | None = None) -> list[sentinel.WatchDecision]:
    """One tick. Returns every decision (fired or not) for observability /
    tests. Acquires the advisory lock; if another process holds it, returns
    [] without evaluating anything."""
    global _consecutive_lock_misses
    if not try_sentinel_lock(db):
        _consecutive_lock_misses += 1
        if _consecutive_lock_misses >= _LOCK_MISS_WARN_THRESHOLD:
            logger.warning(
                "sentinel lock held by another process for %d consecutive ticks "
                "(~%ds) — if that process is gone, its connection is orphaned "
                "and holding the lock; it self-clears once Postgres reaps a "
                "dead connection via TCP keepalives",
                _consecutive_lock_misses, _consecutive_lock_misses * POLL_INTERVAL_SECONDS,
            )
        else:
            logger.debug("sentinel lock held by another process — skipping tick")
        return []
    _consecutive_lock_misses = 0

    decisions: list[sentinel.WatchDecision] = []
    try:
        now = datetime.now(timezone.utc)
        _due_pre_dawn_briefings(db, now=now)
        for watch in list_enabled_watches(db, now=now):
            loc = watch_location(watch)
            if loc is None:
                continue
            # P3.6 — the watch owner's stored language, so a proactive alert
            # does not default to English for every subscriber regardless of
            # who they are. `db.get` is a cheap PK lookup, once per watch per
            # tick; missing/deleted user degrades to "en" like before.
            owner = db.get(User, watch.user_id)
            decision = sentinel.evaluate(
                watch_id=str(watch.id),
                watch_type=watch.watch_type,
                location=loc,
                location_name="your watch area" if watch.watch_area is not None else "your watch point",
                thresholds=dict(watch.thresholds or {}),
                last_payload=_last_watch_payload(db, watch.id),
                language=(owner.language if owner is not None else "en") or "en",
            )
            decisions.append(decision)

            # P5.17 — adaptive cadence: due sooner when this reading was
            # close to firing, at the base interval otherwise. Set whether or
            # not this poll fired — "close but not yet crossed" is exactly
            # the case that most needs the shorter interval.
            interval = FAST_POLL_INTERVAL_SECONDS if _is_near_threshold(watch.watch_type, dict(watch.thresholds or {}), decision) else POLL_INTERVAL_SECONDS
            set_next_poll_at(db, watch.id, now + timedelta(seconds=interval))

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

            channels = effective_channels(list(watch.channels or ["in_app"]), dict(watch.escalation or {}), decision.severity)
            # P5.22 — quiet hours hold a non-critical alert instead of firing
            # it now; a `danger`-severity one (NO_GO-shaped, CRITICAL geofence
            # band, a new hazard) always goes out regardless of the hour.
            in_quiet, deliver_after = (
                quiet_hours_window(owner.quiet_hours, now=now) if owner is not None else (False, None)
            )
            if in_quiet and decision.severity not in _QUIET_HOURS_EXEMPT_SEVERITIES and deliver_after is not None:
                _hold_decision(db, user_id=watch.user_id, watch_id=watch.id, channels=channels,
                                decision=decision, deliver_after=deliver_after)
            else:
                dispatch_decision(db, user_id=watch.user_id, watch_id=watch.id, channels=channels, decision=decision)
            mark_watch_fired(db, watch.id)
        flush_due_held_notifications(db)
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
    except Exception:
        logger.info("sentinel: graph unavailable, running cheap-check-only alerts")

    def _tick() -> list[sentinel.WatchDecision]:
        db = get_sessionmaker()()
        try:
            return [d for d in run_poll_cycle(db, escalate=escalate) if d.fired]
        finally:
            db.close()

    while True:
        try:
            fired = await asyncio.to_thread(_tick)
            if fired:
                logger.info("sentinel: %d crossing(s) dispatched", len(fired))
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
