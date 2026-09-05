"""Plain functions over a Session — no repository *classes*, there is
exactly one implementation of each and a class here would be a rung-1
violation (ladder rung 1: does this need to exist at all as an abstraction?
No — a function is the whole repository).

Ownership rule enforced here, not just at the route: every vessel lookup
takes the requesting user_id and filters by it in the SQL WHERE clause, so
"forgot the check at the route" can never leak another user's row — the
query itself cannot return it.
"""
from __future__ import annotations

import uuid
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.db.models import AuditTraceLog, User, Vessel


def _point_wkb(lat: float | None, lon: float | None) -> Any:
    if lat is None or lon is None:
        return None
    return from_shape(Point(lon, lat), srid=4326)


def _point_latlon(geom: Any) -> dict[str, float] | None:
    if geom is None:
        return None
    shp = to_shape(geom)
    return {"lat": shp.y, "lon": shp.x}


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------

def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_user_by_identifier(db: Session, identifier: str) -> User | None:
    """identifier is a phone (E.164) or an email — registration/login accept
    either (infra/db/001_init.sql users_identity_present)."""
    stmt = select(User).where((User.phone_e164 == identifier) | (User.email == identifier))
    return db.execute(stmt).scalar_one_or_none()


def create_user(
    db: Session,
    *,
    identifier: str,
    password_hash: str,
    display_name: str | None = None,
    language: str = "en",
) -> User:
    is_email = "@" in identifier
    user = User(
        email=identifier if is_email else None,
        phone_e164=None if is_email else identifier,
        password_hash=password_hash,
        display_name=display_name,
        language=language,
    )
    db.add(user)
    db.flush()
    return user


def set_home_port(db: Session, user: User, lat: float, lon: float, name: str | None = None) -> User:
    user.home_port = _point_wkb(lat, lon)
    user.home_port_name = name
    db.flush()
    return user


def user_home_port(user: User) -> dict[str, float] | None:
    return _point_latlon(user.home_port)


# --------------------------------------------------------------------------
# vessels — every function below takes owner_user_id and filters by it;
# there is no vessel-lookup-by-id-alone function in this module on purpose.
# --------------------------------------------------------------------------

def create_vessel(
    db: Session,
    *,
    owner_user_id: uuid.UUID,
    vessel_class: str,
    name: str | None = None,
    registration_no: str | None = None,
    draft_m: float | None = None,
    length_m: float | None = None,
    crew_size: int | None = None,
) -> Vessel:
    vessel = Vessel(
        owner_user_id=owner_user_id,
        name=name,
        registration_no=registration_no,
        vessel_class=vessel_class,
        draft_m=draft_m,
        length_m=length_m,
        crew_size=crew_size,
    )
    db.add(vessel)
    db.flush()
    return vessel


def list_vessels_for_owner(db: Session, owner_user_id: uuid.UUID) -> list[Vessel]:
    stmt = select(Vessel).where(Vessel.owner_user_id == owner_user_id)
    return list(db.execute(stmt).scalars())


def get_vessel_for_owner(db: Session, vessel_id: uuid.UUID, owner_user_id: uuid.UUID) -> Vessel | None:
    """Returns None for a vessel that exists but belongs to someone else —
    the caller cannot distinguish "not found" from "not yours", which is the
    point (plan §5.5 — no confirmation-by-error-message leak)."""
    stmt = select(Vessel).where(Vessel.id == vessel_id, Vessel.owner_user_id == owner_user_id)
    return db.execute(stmt).scalar_one_or_none()


def vessel_last_position(vessel: Vessel) -> dict[str, float] | None:
    return _point_latlon(vessel.last_position)


# --------------------------------------------------------------------------
# audit_trace_log — exit criterion 7: rows land in Postgres, not just
# ORCAState. persist_trace_entries takes the same plain-dict entries
# orca/trace.py already builds; no reshaping at the call site.
# --------------------------------------------------------------------------

def persist_trace_entries(
    db: Session,
    *,
    query_id: str,
    session_id: uuid.UUID | None,
    entries: list[dict[str, Any]],
) -> None:
    for entry in entries:
        db.add(
            AuditTraceLog(
                query_id=uuid.UUID(query_id) if not isinstance(query_id, uuid.UUID) else query_id,
                session_id=session_id,
                agent_name=entry["agent_name"],
                event="agent_complete" if entry.get("status") == "ok" else "error",
                # Phase 3 D1: populated so /trace/{query_id} and /render can
                # reconstruct the full AgentResult from this row alone — see
                # orca/trace.py's run_traced_node, which is the only writer.
                inputs_consumed=entry.get("inputs_consumed"),
                outputs=entry.get("outputs"),
                source_provenance=entry.get("source_provenance"),
                confidence=entry.get("confidence"),
                status=entry.get("status", "ok"),
                error_detail=entry.get("error_detail"),
                latency_ms=int(entry["latency_ms"]) if entry.get("latency_ms") is not None else None,
            )
        )
    db.commit()


def get_trace_entries(db: Session, *, query_id: uuid.UUID) -> list[AuditTraceLog]:
    """Every row for one query, oldest first — the exact reconstruction
    order `/trace/{query_id}` (orca/api/trace_routes.py) needs, and the same
    order `/render` reads to rebuild the AgentResult set without
    re-invoking a single specialist agent."""
    stmt = (
        select(AuditTraceLog)
        .where(AuditTraceLog.query_id == query_id, AuditTraceLog.agent_name != "security")
        .order_by(AuditTraceLog.id)
    )
    return list(db.execute(stmt).scalars())


def persist_security_event(
    db: Session,
    *,
    query_id: uuid.UUID,
    event: str,
    status: str = "ok",
    outputs: dict[str, Any] | None = None,
    error_detail: str | None = None,
) -> None:
    """Security events (login, failed_login, registration, role_change,
    vessel_registration, subscription_change, authority position reads) —
    always agent_name='security' (plan §5.4 Day 10)."""
    db.add(
        AuditTraceLog(
            query_id=query_id,
            session_id=None,
            agent_name="security",
            event=event,
            outputs=outputs,
            status=status,
            error_detail=error_detail,
        )
    )
    db.commit()
