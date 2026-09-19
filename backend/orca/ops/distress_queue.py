"""Authority distress queue (plan P4.16, orca_final §13.2 item 4, §15.4).

The one place an authority sees an individual position — and only while the
event is still open or acknowledged. Every read that returns a position and
every state change is written to the audit trail as a security event. Plain
SQL over `distress_events` (infra/db/006_distress_events.sql), like the rest
of /ops."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.db.repositories import persist_security_event

# action -> (states it may be applied from, state it moves to)
_NEXT_STATE = {"acknowledge": (["open"], "acknowledged"), "close": (["open", "acknowledged"], "closed")}


def record_event(db: Session, final_state: dict[str, Any], mrcc_contact: dict[str, Any] | None) -> None:
    """One row per distress query. Called after the answer has already streamed,
    so a failure here can never delay the caller's MRCC contacts."""
    loc = final_state.get("user_location") or {}
    # Same rule as distress._position_of: a regional default is not where the caller is.
    real = loc.get("place_source") != "regional_default"
    lat, lon = (loc.get("lat"), loc.get("lon")) if real else (None, None)
    distress: dict[str, Any] = next((e for e in final_state.get("audit_trace_log") or [] if e.get("agent_name") == "distress"), {})
    detection = (distress.get("outputs") or {}).get("detection") or {}
    db.execute(
        text(
            "INSERT INTO distress_events (query_id, position, place_name, distress_type, matched_language, "
            "matched_phrase, mrcc_contact) VALUES (:qid, "
            "CASE WHEN CAST(:lat AS float8) IS NULL THEN NULL "
            "ELSE ST_SetSRID(ST_MakePoint(CAST(:lon AS float8), CAST(:lat AS float8)), 4326) END, "
            ":place, :dtype, :lang, :phrase, CAST(:mrcc AS jsonb)) ON CONFLICT (query_id) DO NOTHING"
        ),
        {
            "qid": final_state.get("query_id"), "lat": lat, "lon": lon, "place": loc.get("place_name") if real else None,
            "dtype": detection.get("distress_type"), "lang": detection.get("matched_language"),
            "phrase": detection.get("matched_phrase"),
            "mrcc": None if mrcc_contact is None else json.dumps(mrcc_contact),
        },
    )
    db.commit()


def list_events(db: Session, reader_id: uuid.UUID, hours: int = 24) -> list[dict[str, Any]]:
    """Events from the last `hours`, open first. A closed event keeps its row
    but loses its position in the answer — the read is time-boxed to the
    incident. Returning any position is itself audited."""
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
    events = [
        {
            "id": str(r["id"]), "query_id": str(r["query_id"]), "state": r["state"],
            "created_at": r["created_at"].isoformat(), "place_name": r["place_name"],
            "distress_type": r["distress_type"], "matched_language": r["matched_language"],
            "matched_phrase": r["matched_phrase"], "mrcc_contact": r["mrcc_contact"],
            "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None,
            "closed_at": r["closed_at"].isoformat() if r["closed_at"] else None,
            "lat": r["lat"], "lon": r["lon"],
        }
        for r in rows
    ]
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
