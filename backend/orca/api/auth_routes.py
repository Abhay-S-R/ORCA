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
    LanguageIn,
    LoginIn,
    PersonaIn,
    QuietHoursIn,
    RefreshIn,
    RegisterIn,
    Role,
    SavedLocationIn,
    SavedLocationOut,
    SessionToken,
    TypicalDepartureHourIn,
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
    saved_location_latlon,
    set_active_vessel,
    set_default_persona,
    set_home_port,
    set_quiet_hours,
    set_typical_departure_hour,
    set_user_language,
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
        id=user.id, identifier=user.email or user.phone_e164, display_name=user.display_name, role=cast(Role, user.role),
        default_persona=user.default_persona, language=user.language,
        home_port=user_home_port(user), home_port_name=user.home_port_name,
        active_vessel_id=user.active_vessel_id, quiet_hours=user.quiet_hours,
        typical_departure_hour=user.typical_departure_hour,
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
    point = saved_location_latlon(loc)
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


CANONICAL_TO_DB_VESSEL_CLASS: dict[str, str] = {
    "small_fishing": "fibreglass",
    "mechanized_trawler": "trawler",
    "cargo_vessel": "cargo",
    "catamaran": "catamaran",
    "fibreglass": "fibreglass",
    "mechanised": "mechanised",
    "trawler": "trawler",
    "cargo": "cargo",
}


@router.post("/vessels", response_model=VesselOut, status_code=status.HTTP_201_CREATED)
def register_vessel(body: VesselIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VesselOut:
    # user_id and vessel_id are never accepted from the client as a subject —
    # owner_user_id always comes from the verified token (plan §5.4 Day 10).
    db_class = CANONICAL_TO_DB_VESSEL_CLASS.get(body.vessel_class, body.vessel_class)
    vessel = create_vessel(
        db, owner_user_id=user.id, vessel_class=db_class, name=body.name,
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


@router.put("/profile/language", response_model=UserOut)
def put_language(body: LanguageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """P3.3/P3.13 — the language chooser (first screen after sign-in) and
    "speak to me in Telugu" both write here; the account-menu switcher is
    this same call."""
    set_user_language(db, user, body.language)
    db.commit()
    return _user_out(user)


@router.put("/profile/persona", response_model=UserOut)
def put_persona(body: PersonaIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """P3.4 — the setup wizard's mandatory "role" screen."""
    set_default_persona(db, user, body.default_persona)
    db.commit()
    return _user_out(user)


@router.put("/profile/active-vessel", response_model=UserOut)
def put_active_vessel(body: ActiveVesselIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """P3.9/P3.1 (orca_final §15.3) — which of the owner's several vessels is
    "the boat" a place-less, vessel-less query defaults its thresholds to."""
    if get_vessel_for_owner(db, body.vessel_id, user.id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vessel not found")
    set_active_vessel(db, user, body.vessel_id)
    db.commit()
    return _user_out(user)


@router.put("/profile/quiet-hours", response_model=UserOut)
def put_quiet_hours(body: QuietHoursIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    """P3.9 / P5.22 — a window in which a non-critical Sentinel alert is held
    rather than fired. `None` body clears it (no quiet hours set)."""
    set_quiet_hours(db, user, body.model_dump() if body else None)
    db.commit()
    return _user_out(user)


@router.put("/profile/typical-departure-hour", response_model=UserOut)
def put_typical_departure_hour(
    body: TypicalDepartureHourIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> UserOut:
    """R-NEW-16 — the local hour this user typically departs, so Sentinel can
    send a pre-dawn briefing before it. `None` body turns the feature off."""
    set_typical_departure_hour(db, user, body.hour if body else None)
    db.commit()
    return _user_out(user)


@router.get("/locations", response_model=list[SavedLocationOut])
def list_locations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SavedLocationOut]:
    return [_saved_location_out(loc) for loc in list_saved_locations(db, user.id)]


@router.post("/locations", response_model=SavedLocationOut, status_code=status.HTTP_201_CREATED)
def add_location(body: SavedLocationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SavedLocationOut:
    """P3.10 (orca_final §15.3) — a one-tap saved place, name kept exactly as
    the owner typed or spoke it (their own script, not transliterated)."""
    loc = create_saved_location(db, user_id=user.id, name=body.name, lat=body.lat, lon=body.lon)
    db.commit()
    return _saved_location_out(loc)


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_location(location_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    if not delete_saved_location(db, location_id=location_id, user_id=user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "location not found")
    db.commit()
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
