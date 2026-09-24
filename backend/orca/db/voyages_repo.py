"""Plain functions over a Session for voyages (plan P5.20) — same style and
ownership discipline as orca/db/repositories.py: every lookup filters by
owner_user_id in the SQL, so a forgotten check at the route still cannot
leak another user's plan. The route itself is SENSITIVE (001 comment, same
class as watch_point/watch_area): a voyage plan is a place and a time a
person goes to sea.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.db.models import Voyage
from orca.db.notifications_repo import create_watch


def _linestring_wkb(points: list[tuple[float, float]]) -> Any:
    """`points` as [(lat, lon), ...] — the convention every other route in
    this codebase takes them in; internally WKB is (lon, lat)."""
    return from_shape(LineString([(lon, lat) for lat, lon in points]), srid=4326)


def route_latlons(voyage: Voyage) -> list[dict[str, float]]:
    shp = to_shape(voyage.route)
    return [{"lat": lat, "lon": lon} for lon, lat in shp.coords]


def create_voyage(
    db: Session,
    *,
    user_id: uuid.UUID,
    route: list[tuple[float, float]],
    departure_at: datetime,
    name: str | None = None,
    vessel_id: uuid.UUID | None = None,
) -> Voyage:
    voyage = Voyage(
        owner_user_id=user_id, vessel_id=vessel_id, name=name,
        route=_linestring_wkb(route), departure_at=departure_at,
    )
    db.add(voyage)
    db.flush()
    return voyage


def list_voyages_for_user(db: Session, user_id: uuid.UUID) -> list[Voyage]:
    stmt = select(Voyage).where(Voyage.owner_user_id == user_id).order_by(Voyage.departure_at.desc())
    return list(db.execute(stmt).scalars())


def get_voyage_for_user(db: Session, voyage_id: uuid.UUID, user_id: uuid.UUID) -> Voyage | None:
    """None for a voyage that exists but belongs to someone else — same
    can't-tell-not-found-from-not-yours discipline as vessels/watches."""
    return db.execute(
        select(Voyage).where(Voyage.id == voyage_id, Voyage.owner_user_id == user_id)
    ).scalar_one_or_none()


def delete_voyage(db: Session, *, voyage_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    voyage = get_voyage_for_user(db, voyage_id, user_id)
    if voyage is None:
        return False
    db.delete(voyage)
    db.flush()
    return True


# P5.17/P5.20 — the corridor buffer a promoted route watch is evaluated over.
# Wide enough to cover ordinary track drift and GPS/geodesic-vs-planned-line
# error without watching the whole ocean; a disclosed, fixed cut, the same
# kind P5.8's day-trip distance and P5.21's CAP-alert proxy already are.
_ROUTE_WATCH_BUFFER_NM = 5.0


def promote_voyage_to_watch(
    db: Session, *, voyage: Voyage, channels: list[str] | None = None, thresholds: dict[str, float] | None = None,
) -> Voyage:
    """P5.17/P5.20 — a saved voyage becomes a route watch: Sentinel evaluates
    conditions over a corridor buffered around the planned track, using the
    "weather" watch type's existing cheap-check/crossing path (the watch_type
    enum has no dedicated "route" value, and a route's exposure is exactly
    the wave/wind/lightning/cyclone conditions that path already checks —
    the corridor polygon is what's new, not the condition being watched).
    Re-promoting an already-promoted voyage replaces its existing watch
    rather than accumulating duplicates.
    """
    from orca.agents.voyage import _corridor_polygon

    points_lonlat = [(p["lon"], p["lat"]) for p in route_latlons(voyage)]
    area_geojson = _corridor_polygon(points_lonlat, _ROUTE_WATCH_BUFFER_NM)
    watch = create_watch(
        db,
        user_id=voyage.owner_user_id,
        watch_type="weather",
        area_geojson=area_geojson,
        vessel_id=voyage.vessel_id,
        thresholds=thresholds or {},
        channels=channels or ["in_app"],
        enabled=True,
    )
    voyage.watch_id = watch.id
    db.flush()
    return voyage


def unpromote_voyage(db: Session, *, voyage: Voyage) -> Voyage:
    """Detach the voyage from its route watch without deleting the watch
    itself — the owner may still want the standing area watch even after
    un-tracking this specific plan."""
    voyage.watch_id = None
    db.flush()
    return voyage
