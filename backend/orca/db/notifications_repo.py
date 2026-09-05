"""Plain functions over a Session for watches / notifications / advisory
feedback — same style as orca/db/repositories.py (no repository classes;
one implementation each).

Ownership rule enforced in the SQL, not just at the route: every
user-facing lookup filters by user_id in the WHERE clause, so a forgotten
route check can never leak another user's watch or notification — the query
cannot return it. The watch location is SENSITIVE (001 comment): it is
returned only to its owner, and `watch_location()` is the single accessor.
"""
from __future__ import annotations

import uuid
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, shape
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from orca.db.notifications_models import AdvisoryFeedback, Notification, SentinelSubscription

# Namespace for pg_advisory_lock keys — two arbitrary constants so Sentinel's
# single-instance lock never collides with another feature that also uses
# advisory locks. (classid, objid) form; objid 1 == "the sentinel poll loop".
SENTINEL_LOCK_CLASS = 424242
SENTINEL_LOCK_OBJ = 1


def _point_wkb(lat: float | None, lon: float | None) -> Any:
    if lat is None or lon is None:
        return None
    return from_shape(Point(lon, lat), srid=4326)


def _latlon(geom: Any) -> dict[str, float] | None:
    if geom is None:
        return None
    shp = to_shape(geom)
    return {"lat": shp.y, "lon": shp.x}


# --------------------------------------------------------------------------
# watches (sentinel_subscriptions)
# --------------------------------------------------------------------------

def create_watch(
    db: Session,
    *,
    user_id: uuid.UUID,
    watch_type: str,
    lat: float | None = None,
    lon: float | None = None,
    area_geojson: dict[str, Any] | None = None,
    radius_km: float | None = None,
    vessel_id: uuid.UUID | None = None,
    thresholds: dict[str, float] | None = None,
    channels: list[str] | None = None,
    enabled: bool = True,
) -> SentinelSubscription:
    watch = SentinelSubscription(
        user_id=user_id,
        vessel_id=vessel_id,
        watch_type=watch_type,
        watch_point=_point_wkb(lat, lon),
        watch_area=(from_shape(shape(area_geojson), srid=4326) if area_geojson else None),
        radius_km=radius_km,
        thresholds=thresholds or {},
        channels=channels or ["in_app"],
        enabled=enabled,
    )
    db.add(watch)
    db.flush()
    return watch


def list_watches_for_user(db: Session, user_id: uuid.UUID) -> list[SentinelSubscription]:
    stmt = select(SentinelSubscription).where(SentinelSubscription.user_id == user_id).order_by(
        SentinelSubscription.created_at.desc()
    )
    return list(db.execute(stmt).scalars())


def get_watch_for_user(db: Session, watch_id: uuid.UUID, user_id: uuid.UUID) -> SentinelSubscription | None:
    """None for a watch that exists but belongs to someone else — the caller
    cannot tell 'not found' from 'not yours' (001 §5.5, same as vessels)."""
    stmt = select(SentinelSubscription).where(
        SentinelSubscription.id == watch_id, SentinelSubscription.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


def update_watch(db: Session, watch: SentinelSubscription, **fields: Any) -> SentinelSubscription:
    if "lat" in fields or "lon" in fields:
        watch.watch_point = _point_wkb(fields.pop("lat", None), fields.pop("lon", None))
    for k, v in fields.items():
        setattr(watch, k, v)
    db.flush()
    return watch


def delete_watch(db: Session, watch: SentinelSubscription) -> None:
    db.delete(watch)
    db.flush()


def list_enabled_watches(db: Session) -> list[SentinelSubscription]:
    """Every enabled watch across all users — Sentinel's monitored-location
    list. The only cross-user query in this module, and it is used solely by
    the background loop, never by a request handler."""
    return list(db.execute(select(SentinelSubscription).where(SentinelSubscription.enabled)).scalars())


def mark_watch_fired(db: Session, watch_id: uuid.UUID) -> None:
    db.execute(
        text("UPDATE sentinel_subscriptions SET last_fired_at = now() WHERE id = :id"), {"id": watch_id}
    )


def watch_location(watch: SentinelSubscription) -> dict[str, float] | None:
    """The single accessor for a watch point. SENSITIVE — callers must be
    the owner. Area watches return their centroid for display only."""
    if watch.watch_point is not None:
        return _latlon(watch.watch_point)
    if watch.watch_area is not None:
        c = to_shape(watch.watch_area).centroid
        return {"lat": c.y, "lon": c.x}
    return None


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------

def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    title: str,
    body: str,
    severity: str = "info",
    channel: str = "in_app",
    status: str = "sent",
    watch_id: uuid.UUID | None = None,
    query_id: uuid.UUID | None = None,
    rendered_payload: dict[str, Any] | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        watch_id=watch_id,
        query_id=query_id,
        severity=severity,
        title=title,
        body=body,
        channel=channel,
        status=status,
        rendered_payload=rendered_payload or {},
    )
    db.add(n)
    db.flush()
    return n


def list_notifications_for_user(
    db: Session, user_id: uuid.UUID, *, limit: int = 50, unread_only: bool = False
) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(min(limit, 200))
    return list(db.execute(stmt).scalars())


def unread_count(db: Session, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    return int(db.execute(stmt).scalar_one())


def mark_notification_read(db: Session, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Returns True if a row belonging to this user was updated. Idempotent."""
    result = db.execute(
        text(
            "UPDATE notifications SET read_at = now() "
            "WHERE id = :id AND user_id = :uid AND read_at IS NULL"
        ),
        {"id": notification_id, "uid": user_id},
    )
    return result.rowcount > 0


def mark_all_read(db: Session, user_id: uuid.UUID) -> int:
    result = db.execute(
        text("UPDATE notifications SET read_at = now() WHERE user_id = :uid AND read_at IS NULL"),
        {"uid": user_id},
    )
    return result.rowcount


# --------------------------------------------------------------------------
# advisory feedback
# --------------------------------------------------------------------------

def create_feedback(
    db: Session,
    *,
    query_id: uuid.UUID,
    kind: str,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    advisory_ref: str | None = None,
    comment: str | None = None,
) -> AdvisoryFeedback:
    fb = AdvisoryFeedback(
        query_id=query_id,
        kind=kind,
        user_id=user_id,
        session_id=session_id,
        advisory_ref=advisory_ref,
        comment=comment,
    )
    db.add(fb)
    db.flush()
    return fb


def feedback_for_query(db: Session, query_id: uuid.UUID) -> list[AdvisoryFeedback]:
    return list(
        db.execute(select(AdvisoryFeedback).where(AdvisoryFeedback.query_id == query_id)).scalars()
    )


# --------------------------------------------------------------------------
# advisory lock — Sentinel single-instance guard (plan §2, §11)
# --------------------------------------------------------------------------

def try_sentinel_lock(db: Session) -> bool:
    """pg_try_advisory_lock: non-blocking. True == this process owns the
    sentinel poll loop; False == another process already does, so skip this
    tick. Session-scoped lock — released on connection close or explicit
    unlock. No second process ever double-fires a watch (plan §11)."""
    return bool(
        db.execute(
            text("SELECT pg_try_advisory_lock(:c, :o)"),
            {"c": SENTINEL_LOCK_CLASS, "o": SENTINEL_LOCK_OBJ},
        ).scalar_one()
    )


def release_sentinel_lock(db: Session) -> None:
    db.execute(
        text("SELECT pg_advisory_unlock(:c, :o)"),
        {"c": SENTINEL_LOCK_CLASS, "o": SENTINEL_LOCK_OBJ},
    )
