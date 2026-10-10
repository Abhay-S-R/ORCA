"""Authority distress queue (plan P4.16, orca_final §13.2 item 4, §15.4).

The one place an authority sees an individual position — and only while the
event is still open or acknowledged. Every read that returns a position and
every state change is written to the audit trail as a security event. Plain
SQL over `distress_events` (infra/db/006_distress_events.sql), like the rest
of /ops."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.db.repositories import persist_security_event

logger = logging.getLogger(__name__)

# action -> (states it may be applied from, state it moves to)
_NEXT_STATE = {"acknowledge": (["open"], "acknowledged"), "close": (["open", "acknowledged"], "closed")}


def _ensure_distress_table_columns(db: Session) -> None:
    """Safely adds target_port, authority_name, and survival_suggestions columns if missing."""
    try:
        db.execute(text("ALTER TABLE distress_events ADD COLUMN IF NOT EXISTS target_port text;"))
        db.execute(text("ALTER TABLE distress_events ADD COLUMN IF NOT EXISTS authority_name text;"))
        db.execute(text("ALTER TABLE distress_events ADD COLUMN IF NOT EXISTS survival_suggestions jsonb;"))
        db.commit()
    except Exception:
        db.rollback()


def record_event(
    db: Session,
    final_state: dict[str, Any],
    mrcc_contact: dict[str, Any] | None,
    user_id: uuid.UUID | None = None,
) -> None:
    """One row per distress query. Called after the answer has already streamed,
    so a failure here can never delay the caller's MRCC contacts.

    Triggers an in-app emergency alert in the coastal authority account associated
    with the user's home port or incident location.
    """
    from datetime import UTC, datetime

    from orca.db.models import User
    from orca.db.notifications_repo import create_notification
    from orca.ops.port_authorities import get_authority_user_for_port

    _ensure_distress_table_columns(db)

    loc = final_state.get("user_location") or {}
    real = loc.get("place_source") != "regional_default"
    lat, lon = (loc.get("lat"), loc.get("lon")) if real else (None, None)
    distress: dict[str, Any] = next((e for e in final_state.get("audit_trace_log") or [] if e.get("agent_name") == "distress"), {})
    outputs = distress.get("outputs") or {}
    detection = outputs.get("detection") or {}
    survival_suggestions = outputs.get("survival_suggestions") or []

    # Resolve target port from:
    # 1. Registered user's home port in DB
    # 2. Location dictionary home_port_name / place_name
    # 3. Output target_authority if already resolved
    # 4. Lat/lon nearest port
    target_port_name: str | None = None
    user: User | None = None
    if user_id:
        user = db.get(User, user_id)
        if user and user.home_port_name:
            target_port_name = user.home_port_name

    if not target_port_name:
        target_auth = outputs.get("target_authority") or {}
        target_port_name = (
            target_auth.get("port_name")
            or loc.get("home_port_name")
            or loc.get("place_name")
        )

    # Resolve coastal authority configuration & account
    cfg, authority_user = get_authority_user_for_port(db, port_name=target_port_name, lat=lat, lon=lon)
    port_name = cfg["port_name"]
    auth_display_name = cfg["display_name"]

    # Keep mrcc_contact unaltered per original contract
    qid = final_state.get("query_id")
    dtype = detection.get("distress_type")
    lang = detection.get("matched_language")
    phrase = detection.get("matched_phrase")

    try:
        db.execute(
            text(
                "INSERT INTO distress_events ("
                "query_id, position, place_name, distress_type, matched_language, "
                "matched_phrase, mrcc_contact, target_port, authority_name, survival_suggestions"
                ") VALUES (:qid, "
                "CASE WHEN CAST(:lat AS float8) IS NULL THEN NULL "
                "ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326) END, "
                ":place, :dtype, :lang, :phrase, CAST(:mrcc AS jsonb), :tport, :aname, CAST(:suggs AS jsonb)) "
                "ON CONFLICT (query_id) DO UPDATE SET "
                "target_port = EXCLUDED.target_port, authority_name = EXCLUDED.authority_name, "
                "survival_suggestions = EXCLUDED.survival_suggestions"
            ),
            {
                "qid": qid, "lat": lat, "lon": lon, "place": loc.get("place_name") if real else None,
                "dtype": dtype, "lang": lang, "phrase": phrase,
                "mrcc": None if mrcc_contact is None else json.dumps(mrcc_contact),
                "tport": port_name, "aname": auth_display_name,
                "suggs": json.dumps(survival_suggestions),
            },
        )
        db.commit()
    except Exception:
        # Fallback to base insert if custom columns not available
        db.rollback()
        db.execute(
            text(
                "INSERT INTO distress_events (query_id, position, place_name, distress_type, matched_language, "
                "matched_phrase, mrcc_contact) VALUES (:qid, "
                "CASE WHEN CAST(:lat AS float8) IS NULL THEN NULL "
                "ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326) END, "
                ":place, :dtype, :lang, :phrase, CAST(:mrcc AS jsonb)) ON CONFLICT (query_id) DO NOTHING"
            ),
            {
                "qid": qid, "lat": lat, "lon": lon, "place": loc.get("place_name") if real else None,
                "dtype": dtype, "lang": lang, "phrase": phrase,
                "mrcc": None if mrcc_contact is None else json.dumps(mrcc_contact),
            },
        )
        db.commit()

    # Trigger emergency notification in coastal authority's account
    try:
        qid_uuid = uuid.UUID(str(qid)) if qid else None
    except (ValueError, TypeError):
        qid_uuid = None

    caller_identity = (
        user.display_name if (user and user.display_name)
        else (user.email or user.phone_e164 if user else "Vessel Operator")
    )
    pos_desc = (
        f"{lat:.4f}°N, {lon:.4f}°E ({loc.get('place_name') or port_name})"
        if lat and lon
        else (loc.get("place_name") or f"{port_name} Sector")
    )

    try:
        create_notification(
            db,
            user_id=authority_user.id,
            severity="danger",
            title=f"🚨 DISTRESS ALERT: {port_name} Coastal Sector",
            body=(
                f"Emergency distress call from {caller_identity} near {pos_desc}. "
                f"Type: {dtype or 'emergency'} ('{phrase or 'SOS'}'). "
                f"Survival suggestions issued to vessel. Immediate coastal rescue dispatch requested."
            ),
            query_id=qid_uuid,
            channel="in_app",
            status="sent",
            rendered_payload={
                "query_id": str(qid) if qid else None,
                "port_name": port_name,
                "authority_name": auth_display_name,
                "emergency_unit": cfg.get("emergency_unit"),
                "caller": caller_identity,
                "position": {"lat": lat, "lon": lon} if lat and lon else None,
                "place_name": loc.get("place_name") or port_name,
                "distress_type": dtype,
                "matched_phrase": phrase,
                "matched_language": lang,
                "survival_suggestions": survival_suggestions,
                "mrcc": mrcc_contact,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Could not dispatch authority alert notification: %s", exc)


def list_events(db: Session, reader_id: uuid.UUID, hours: int = 24) -> list[dict[str, Any]]:
    """Events from the last `hours`, open first. A closed event keeps its row
    but loses its position in the answer — the read is time-boxed to the
    incident. Returning any position is itself audited.

    Includes target port authority routing and flags if assigned to reader.
    """
    from orca.db.models import User

    reader = db.get(User, reader_id)
    reader_port = (reader.home_port_name or "").lower().strip() if reader else ""
    is_admin = (reader.role == "admin") if reader else False

    # Safely query with target_port, authority_name, survival_suggestions if available
    try:
        rows = db.execute(
            text(
                "SELECT id, query_id, state, created_at, place_name, distress_type, matched_language, "
                "matched_phrase, mrcc_contact, target_port, authority_name, survival_suggestions, "
                "acknowledged_at, closed_at, "
                "CASE WHEN state <> 'closed' THEN ST_Y(position) END AS lat, "
                "CASE WHEN state <> 'closed' THEN ST_X(position) END AS lon "
                "FROM distress_events WHERE created_at > now() - make_interval(hours => :h) "
                "ORDER BY (state = 'closed'), (state = 'acknowledged'), created_at DESC"
            ),
            {"h": max(1, min(hours, 24 * 7))},
        ).mappings().all()
    except Exception:
        db.rollback()
        rows = db.execute(
            text(
                "SELECT id, query_id, state, created_at, place_name, distress_type, matched_language, "
                "matched_phrase, mrcc_contact, acknowledged_at, closed_at, "
                "CASE WHEN state <> 'closed' THEN ST_Y(position) END AS lat, "
                "CASE WHEN state <> 'closed' THEN ST_X(position) END AS lon "
                "FROM distress_events WHERE created_at > now() - make_interval(hours => :h) "
                "ORDER BY (state = 'closed'), (state = 'acknowledged'), created_at DESC"
            ),
            {"h": max(1, min(hours, 24 * 7))},
        ).mappings().all()

    events = []
    for r in rows:
        target_port = r.get("target_port")
        auth_name = r.get("authority_name")
        suggs = r.get("survival_suggestions") or []

        target_port_str = str(target_port).lower().strip() if target_port else ""
        is_assigned = (
            is_admin
            or (bool(target_port_str) and target_port_str in reader_port)
            or (bool(reader_port) and bool(target_port_str) and reader_port in target_port_str)
        )

        item = {
            "id": str(r["id"]),
            "query_id": str(r["query_id"]),
            "state": r["state"],
            "created_at": r["created_at"].isoformat(),
            "place_name": r["place_name"],
            "distress_type": r["distress_type"],
            "matched_language": r["matched_language"],
            "matched_phrase": r["matched_phrase"],
            "mrcc_contact": r["mrcc_contact"],
            "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
            "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None,
            "lat": r["lat"],
            "lon": r["lon"],
        }
        if target_port:
            item["target_port"] = target_port
        if auth_name:
            item["authority_name"] = auth_name
        if suggs:
            item["survival_suggestions"] = suggs
        item["is_assigned_to_reader"] = is_assigned
        events.append(item)

    shown = [e["id"] for e in events if e["lat"] is not None]
    if shown:
        persist_security_event(
            db, query_id=uuid.uuid4(), event="distress_position_read",
            outputs={"authority_user_id": str(reader_id), "distress_event_ids": shown},
        )
    return events


def set_state(db: Session, event_id: uuid.UUID, action: str, actor_id: uuid.UUID) -> dict[str, Any] | None:
    """acknowledge: open -> acknowledged. close: open|acknowledged -> closed.
    Returns the new state, or None when the event is missing or already past it."""
    allowed, new_state = _NEXT_STATE[action]
    stamp = "acknowledged" if action == "acknowledge" else "closed"
    row = db.execute(
        text(
            f"UPDATE distress_events SET state = :new, {stamp}_by = :actor, {stamp}_at = now() "
            "WHERE id = :id AND state = ANY(:allowed) RETURNING id, state"
        ),
        {"new": new_state, "actor": actor_id, "id": event_id, "allowed": allowed},
    ).first()
    db.commit()
    if row is None:
        return None
    persist_security_event(
        db, query_id=uuid.uuid4(), event=f"distress_{action}",
        outputs={"authority_user_id": str(actor_id), "distress_event_id": str(event_id)},
    )
    return {"id": str(row[0]), "state": row[1]}
