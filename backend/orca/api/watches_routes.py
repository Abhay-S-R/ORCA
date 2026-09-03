"""HTTP surface for /watches (Phase 3 D2). Thin — logic is in
orca/db/notifications_repo.py. Same pattern as auth_routes.py: identity from
the bearer token, never the body; every lookup is owner-scoped in the repo's
SQL so a missed check here still cannot leak another user's watch.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from orca.auth.rbac import get_current_user
from orca.db.engine import get_db
from orca.db.models import User
from orca.db.notifications_models import SentinelSubscription
from orca.db.notifications_repo import (
    create_watch,
    delete_watch,
    get_watch_for_user,
    list_notifications_for_user,
    list_watches_for_user,
    update_watch,
    watch_location,
)
from orca.db.repositories import persist_security_event
from orca.notifications.contracts import NotificationOut, WatchIn, WatchOut
from orca.notifications.watch_badges import watch_badges_for_user

router = APIRouter(prefix="/api", tags=["watches"])


def _watch_out(w: SentinelSubscription) -> WatchOut:
    loc = watch_location(w) if w.watch_point is not None else None
    return WatchOut(
        id=w.id,
        watch_type=w.watch_type,  # type: ignore[arg-type]
        lat=loc["lat"] if loc else None,
        lon=loc["lon"] if loc else None,
        radius_km=float(w.radius_km) if w.radius_km is not None else None,
        vessel_id=w.vessel_id,
        thresholds=dict(w.thresholds or {}),
        channels=list(w.channels or []),
        enabled=w.enabled,
        last_fired_at=w.last_fired_at,
        created_at=w.created_at,
    )


@router.get("/watches", response_model=list[WatchOut])
def list_watches(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[WatchOut]:
    return [_watch_out(w) for w in list_watches_for_user(db, user.id)]


@router.get("/watches/badges")
def watch_badges(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """The watch-badge handoff for D3's map (plan §14). Owner-scoped — a
    watch point is SENSITIVE and never crosses a user boundary."""
    badges = watch_badges_for_user(db, user.id)
    from orca.notifications.watch_badges import badges_as_map_layer

    return {"badges": badges, "map_layer": badges_as_map_layer(badges)}


@router.post("/watches", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
def create(body: WatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> WatchOut:
    watch = create_watch(
        db,
        user_id=user.id,
        watch_type=body.watch_type,
        lat=body.lat,
        lon=body.lon,
        area_geojson=body.area_geojson,
        radius_km=body.radius_km,
        vessel_id=body.vessel_id,
        thresholds=body.thresholds,
        channels=body.channels,
        enabled=body.enabled,
    )
    db.commit()
    persist_security_event(
        db, query_id=uuid.uuid4(), event="subscription_change", status="ok",
        outputs={"user_id": str(user.id), "watch_id": str(watch.id), "action": "create"},
    )
    return _watch_out(watch)


@router.get("/watches/{watch_id}", response_model=WatchOut)
def get_one(watch_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> WatchOut:
    watch = get_watch_for_user(db, watch_id, user.id)
    if watch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watch not found")
    return _watch_out(watch)


@router.put("/watches/{watch_id}", response_model=WatchOut)
def replace(
    watch_id: uuid.UUID, body: WatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WatchOut:
    watch = get_watch_for_user(db, watch_id, user.id)
    if watch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watch not found")
    update_watch(
        db, watch,
        watch_type=body.watch_type,
        lat=body.lat,
        lon=body.lon,
        radius_km=body.radius_km,
        thresholds=body.thresholds,
        channels=body.channels,
        enabled=body.enabled,
    )
    db.commit()
    persist_security_event(
        db, query_id=uuid.uuid4(), event="subscription_change", status="ok",
        outputs={"user_id": str(user.id), "watch_id": str(watch.id), "action": "update"},
    )
    return _watch_out(watch)


@router.delete("/watches/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(watch_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    watch = get_watch_for_user(db, watch_id, user.id)
    if watch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watch not found")
    delete_watch(db, watch)
    db.commit()
    persist_security_event(
        db, query_id=uuid.uuid4(), event="subscription_change", status="ok",
        outputs={"user_id": str(user.id), "watch_id": str(watch_id), "action": "delete"},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watches/{watch_id}/history", response_model=list[NotificationOut])
def history(
    watch_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[NotificationOut]:
    """Alert history per watch, with the exact payload that was dispatched."""
    watch = get_watch_for_user(db, watch_id, user.id)
    if watch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "watch not found")
    rows = [
        n for n in list_notifications_for_user(db, user.id, limit=200) if n.watch_id == watch_id
    ]
    return [
        NotificationOut(
            id=n.id, watch_id=n.watch_id, query_id=n.query_id, severity=n.severity,  # type: ignore[arg-type]
            title=n.title, body=n.body, channel=n.channel, status=n.status,  # type: ignore[arg-type]
            rendered_payload=n.rendered_payload, read=n.read_at is not None, created_at=n.created_at,
        )
        for n in rows
    ]
