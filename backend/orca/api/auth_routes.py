"""HTTP surface for D1 (Platform, Identity & Synthesis) — plan §5.4.
`/register`, `/login`, `/profile`, `/vessels`. Thin: all real logic lives in
orca/auth/service.py and orca/db/repositories.py; this file only translates
HTTP <-> those calls, same pattern as discovery_routes.py / geospatial_routes.py.
"""
from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from orca.auth import service
from orca.auth.rbac import get_current_user, require_role
from orca.auth.schemas import (
    HomePortIn,
    LoginIn,
    RegisterIn,
    Role,
    SessionToken,
    UserOut,
    VesselClass,
    VesselIn,
    VesselOut,
)
from orca.db.engine import get_db
from orca.db.models import User, Vessel
from orca.db.repositories import (
    create_vessel,
    get_vessel_for_owner,
    list_vessels_for_owner,
    persist_security_event,
    set_home_port,
    user_home_port,
    vessel_last_position,
)

router = APIRouter(prefix="/api")

_REASON_STATUS = {
    "duplicate": status.HTTP_409_CONFLICT,
    "invalid_credentials": status.HTTP_401_UNAUTHORIZED,
    "inactive": status.HTTP_403_FORBIDDEN,
}


def _user_out(user: User) -> UserOut:
    # cast, not a runtime check: the `user_role` Postgres enum (infra/db/001_init.sql)
    # already guarantees this column can only hold one of the three role
    # literals — SQLAlchemy's ORM column type is just `str`, mypy can't see
    # the DB constraint that makes the value narrower.
    return UserOut(
        id=user.id, display_name=user.display_name, role=cast(Role, user.role), language=user.language,
        home_port=user_home_port(user), home_port_name=user.home_port_name,
    )


def _vessel_out(vessel: Vessel) -> VesselOut:
    return VesselOut(
        id=vessel.id, owner_user_id=vessel.owner_user_id, vessel_class=cast(VesselClass, vessel.vessel_class),
        name=vessel.name, registration_no=vessel.registration_no, draft_m=vessel.draft_m,
        length_m=vessel.length_m, crew_size=vessel.crew_size, last_position=vessel_last_position(vessel),
    )


@router.post("/register", response_model=SessionToken, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> SessionToken:
    try:
        _, tokens = service.register(
            db, identifier=body.identifier, password=body.password,
            display_name=body.display_name, language=body.language,
        )
    except service.AuthError as exc:
        raise HTTPException(_REASON_STATUS[exc.reason], str(exc)) from exc
    return SessionToken(**tokens.__dict__)


@router.post("/login", response_model=SessionToken)
def login(body: LoginIn, db: Session = Depends(get_db)) -> SessionToken:
    try:
        _, tokens = service.login(db, identifier=body.identifier, password=body.password)
    except service.AuthError as exc:
        raise HTTPException(_REASON_STATUS[exc.reason], str(exc)) from exc
    return SessionToken(**tokens.__dict__)


@router.get("/profile", response_model=UserOut)
def get_profile(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.put("/profile/home-port", response_model=UserOut)
def put_home_port(body: HomePortIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    set_home_port(db, user, body.lat, body.lon, body.name)
    db.commit()
    return _user_out(user)


@router.get("/vessels", response_model=list[VesselOut])
def list_vessels(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VesselOut]:
    return [_vessel_out(v) for v in list_vessels_for_owner(db, user.id)]


@router.post("/vessels", response_model=VesselOut, status_code=status.HTTP_201_CREATED)
def register_vessel(body: VesselIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VesselOut:
    # user_id and vessel_id are never accepted from the client as a subject —
    # owner_user_id always comes from the verified token (plan §5.4 Day 10).
    vessel = create_vessel(
        db, owner_user_id=user.id, vessel_class=body.vessel_class, name=body.name,
        registration_no=body.registration_no, draft_m=body.draft_m, length_m=body.length_m,
        crew_size=body.crew_size,
    )
    db.commit()
    persist_security_event(
        db, query_id=uuid.uuid4(), event="vessel_registration", status="ok",
        outputs={"user_id": str(user.id), "vessel_id": str(vessel.id)},
    )
    return _vessel_out(vessel)


@router.get("/vessels/{vessel_id}", response_model=VesselOut)
def get_vessel(vessel_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VesselOut:
    vessel = get_vessel_for_owner(db, vessel_id, user.id)
    if vessel is None:
        # Same 404 whether the vessel doesn't exist or belongs to someone
        # else — the cross-read attempt is still refused and audited below,
        # a client just can't use the response to tell which case it hit.
        persist_security_event(
            db, query_id=uuid.uuid4(), event="cross_user_vessel_read_denied", status="failed",
            outputs={"user_id": str(user.id), "requested_vessel_id": str(vessel_id)},
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vessel not found")
    return _vessel_out(vessel)


@router.get("/authority/vessels/{vessel_id}", response_model=VesselOut)
def authority_get_vessel(
    vessel_id: uuid.UUID, user: User = Depends(require_role("authority", "admin")), db: Session = Depends(get_db)
) -> VesselOut:
    """Authority read of any vessel — cross-owner by design, unlike
    /vessels/{id}, and always audited (plan §5.4: 'authority position reads'
    are a named security event)."""
    vessel = db.get(Vessel, vessel_id)
    if vessel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vessel not found")
    persist_security_event(
        db, query_id=uuid.uuid4(), event="authority_position_read", status="ok",
        outputs={"authority_user_id": str(user.id), "vessel_id": str(vessel_id)},
    )
    return _vessel_out(vessel)
