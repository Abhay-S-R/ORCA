"""HTTP surface for D1 (Platform, Identity & Synthesis) — plan §5.4.
`/register`, `/login`, `/profile`, `/vessels`. Thin: all real logic lives in
orca/auth/service.py and orca/db/repositories.py; this file only translates
HTTP <-> those calls, same pattern as discovery_routes.py / geospatial_routes.py.
"""
from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from orca.auth import service
from orca.auth.rbac import get_current_user, require_role
from orca.auth.schemas import (
    ActiveVesselIn,
    HomePortIn,
    LoginIn,
    RefreshIn,
    RegisterIn,
    Role,
    SavedLocationIn,
    SavedLocationOut,
    SessionToken,
    UserOut,
    VesselClass,
    VesselIn,
    VesselOut,
)
from orca.db.engine import get_db
from orca.db.models import SavedLocation, User, Vessel
from orca.db.repositories import (
    create_saved_location,
    create_vessel,
    delete_saved_location,
    get_vessel_for_owner,
    list_saved_locations,
    list_vessels_for_owner,
    persist_security_event,
    saved_location_point,
    set_active_vessel,
    set_home_port,
    user_home_port,
    vessel_last_position,
)

router = APIRouter(prefix="/api")

_REASON_STATUS = {
    "duplicate": status.HTTP_409_CONFLICT,
    "invalid_credentials": status.HTTP_401_UNAUTHORIZED,
    "inactive": status.HTTP_403_FORBIDDEN,
    "invalid_token": status.HTTP_401_UNAUTHORIZED,
}


def _user_out(user: User) -> UserOut:
    # cast, not a runtime check: the `user_role` Postgres enum (infra/db/001_init.sql)
    # already guarantees this column can only hold one of the three role
    # literals — SQLAlchemy's ORM column type is just `str`, mypy can't see
    # the DB constraint that makes the value narrower.
    return UserOut(
        id=user.id, identifier=user.email or user.phone_e164, display_name=user.display_name, role=cast(Role, user.role), language=user.language,
        default_persona=user.default_persona,
        home_port=user_home_port(user), home_port_name=user.home_port_name,
        active_vessel_id=user.active_vessel_id,
    )


def _vessel_out(vessel: Vessel) -> VesselOut:
    return VesselOut(
        id=vessel.id, owner_user_id=vessel.owner_user_id, vessel_class=cast(VesselClass, vessel.vessel_class),
        name=vessel.name, registration_no=vessel.registration_no, draft_m=vessel.draft_m,
        length_m=vessel.length_m, crew_size=vessel.crew_size,
        cruise_speed_kn=vessel.cruise_speed_kn, fuel_burn_lph=vessel.fuel_burn_lph, engine_count=vessel.engine_count,
        last_position=vessel_last_position(vessel),
    )


def _saved_location_out(loc: SavedLocation) -> SavedLocationOut:
    point = saved_location_point(loc)
    return SavedLocationOut(id=loc.id, name=loc.name, lat=point["lat"], lon=point["lon"])


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


@router.post("/refresh", response_model=SessionToken)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> SessionToken:
    """Trade a refresh token for a new pair (rotation — the presented one is
    revoked). The 15-minute access token was issued with no way to renew it,
    so every signed-in surface silently signed out after 15 minutes."""
    try:
        _, tokens = service.refresh(db, refresh_token=body.refresh_token)
    except service.AuthError as exc:
        raise HTTPException(_REASON_STATUS[exc.reason], str(exc)) from exc
    return SessionToken(**tokens.__dict__)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn, db: Session = Depends(get_db)) -> Response:
    """Revoke the refresh token server-side. Needs no access token: signing
    out has to work after the access token has already expired."""
    service.logout(db, refresh_token=body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        crew_size=body.crew_size, cruise_speed_kn=body.cruise_speed_kn,
        fuel_burn_lph=body.fuel_burn_lph, engine_count=body.engine_count,
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


@router.put("/profile/active-vessel", response_model=UserOut)
def put_active_vessel(body: ActiveVesselIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """P3.9/orca_final §15.3 — several vessels, one active. `vessel_id: null`
    clears the selection (e.g. after deleting the active vessel)."""
    try:
        set_active_vessel(db, user, body.vessel_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vessel not found") from None
    db.commit()
    return _user_out(user)


# --------------------------------------------------------------------------
# P3.10 — saved locations. Signed-out users get the same feature from
# localStorage (frontend/app/ask/chatStore.ts's pattern); these routes are
# the signed-in half only, always owner-scoped in the repo's SQL.
# --------------------------------------------------------------------------

@router.get("/saved-locations", response_model=list[SavedLocationOut])
def list_saved(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SavedLocationOut]:
    return [_saved_location_out(loc) for loc in list_saved_locations(db, user.id)]


@router.post("/saved-locations", response_model=SavedLocationOut, status_code=status.HTTP_201_CREATED)
def create_saved(body: SavedLocationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SavedLocationOut:
    loc = create_saved_location(db, user_id=user.id, name=body.name, lat=body.lat, lon=body.lon)
    db.commit()
    return _saved_location_out(loc)


@router.delete("/saved-locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(location_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    deleted = delete_saved_location(db, user.id, location_id)
    db.commit()
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "saved location not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
