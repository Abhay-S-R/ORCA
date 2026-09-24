"""HTTP surface for /api/voyages (plan P5.20) — saved passage plans, distinct
from /api/voyage-plan's stateless planning call. Same pattern as
watches_routes.py: identity from the bearer token, never the body; every
lookup is owner-scoped in the repo's SQL so a missed check here still cannot
leak another user's plan.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from orca.api.params import LatField, LonField
from orca.auth.rbac import get_current_user
from orca.db.engine import get_db
from orca.db.models import User, Voyage
from orca.db.repositories import persist_security_event
from orca.db.voyages_repo import (
    create_voyage,
    delete_voyage,
    get_voyage_for_user,
    list_voyages_for_user,
    promote_voyage_to_watch,
    route_latlons,
    unpromote_voyage,
)
from orca.notifications.contracts import Channel

router = APIRouter(prefix="/api", tags=["voyages"])


class RoutePoint(BaseModel):
    lat: LatField
    lon: LonField


class VoyageIn(BaseModel):
    """`user_id`/`owner_user_id` deliberately absent — identity comes from
    the bearer token at the route (same discipline as WatchIn)."""

    name: str | None = None
    route: list[RoutePoint] = Field(min_length=2)
    departure_at: datetime
    vessel_id: uuid.UUID | None = None


class VoyageOut(BaseModel):
    id: uuid.UUID
    name: str | None
    route: list[RoutePoint]
    departure_at: datetime
    vessel_id: uuid.UUID | None
    watch_id: uuid.UUID | None
    created_at: datetime


class PromoteIn(BaseModel):
    channels: list[Channel] = Field(default_factory=lambda: ["in_app"])
    thresholds: dict[str, float] = Field(default_factory=dict)


def _voyage_out(v: Voyage) -> VoyageOut:
    return VoyageOut(
        id=v.id, name=v.name, route=[RoutePoint(**p) for p in route_latlons(v)],
        departure_at=v.departure_at, vessel_id=v.vessel_id, watch_id=v.watch_id, created_at=v.created_at,
    )


@router.get("/voyages", response_model=list[VoyageOut])
def list_voyages(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VoyageOut]:
    return [_voyage_out(v) for v in list_voyages_for_user(db, user.id)]


@router.post("/voyages", response_model=VoyageOut, status_code=status.HTTP_201_CREATED)
def create(body: VoyageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VoyageOut:
    voyage = create_voyage(
        db, user_id=user.id, route=[(p.lat, p.lon) for p in body.route],
        departure_at=body.departure_at, name=body.name, vessel_id=body.vessel_id,
    )
    db.commit()
    persist_security_event(
        db, query_id=uuid.uuid4(), event="subscription_change", status="ok",
        outputs={"user_id": str(user.id), "voyage_id": str(voyage.id), "action": "create_voyage"},
    )
    return _voyage_out(voyage)


@router.get("/voyages/{voyage_id}", response_model=VoyageOut)
def get_one(voyage_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VoyageOut:
    voyage = get_voyage_for_user(db, voyage_id, user.id)
    if voyage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "voyage not found")
    return _voyage_out(voyage)


@router.delete("/voyages/{voyage_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(voyage_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    if not delete_voyage(db, voyage_id=voyage_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "voyage not found")
    db.commit()
    persist_security_event(
        db, query_id=uuid.uuid4(), event="subscription_change", status="ok",
        outputs={"user_id": str(user.id), "voyage_id": str(voyage_id), "action": "delete_voyage"},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/voyages/{voyage_id}/watch", response_model=VoyageOut)
def promote(
    voyage_id: uuid.UUID, body: PromoteIn | None = None,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> VoyageOut:
    """P5.17/P5.20 — promote a saved voyage to a route watch: Sentinel starts
    evaluating conditions over a corridor buffered around the planned track."""
    voyage = get_voyage_for_user(db, voyage_id, user.id)
    if voyage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "voyage not found")
    body = body or PromoteIn()
    voyage = promote_voyage_to_watch(db, voyage=voyage, channels=list(body.channels), thresholds=body.thresholds)
    db.commit()
    return _voyage_out(voyage)


@router.delete("/voyages/{voyage_id}/watch", response_model=VoyageOut)
def unpromote(voyage_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VoyageOut:
    voyage = get_voyage_for_user(db, voyage_id, user.id)
    if voyage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "voyage not found")
    voyage = unpromote_voyage(db, voyage=voyage)
    db.commit()
    return _voyage_out(voyage)
