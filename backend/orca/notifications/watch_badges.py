"""Map watch-badge data handoff — D2 owns the INTERFACE, D3 owns the map
rendering (plan §14).

D2 emits the smallest stable payload D3 needs to draw a badge and does NOT
touch MapView / the layer registry. The payload doubles as a `MapLayer` of
the frozen `layer_type="SentinelWatch"` (already in orca/contracts.py) so
D3 can feed it straight through `validate_payload` with no reshaping.

A watch point is SENSITIVE (001) — this is only ever built for, and returned
to, the watch's own owner. There is no cross-user badge feed.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # keep this module importable (for badges_as_map_layer) without the DB stack
    from sqlalchemy.orm import Session

    from orca.db.notifications_models import SentinelSubscription

# The per-badge contract handed to D3. Additive-only from here.
#   watch_id     — stable id, so D3 can setData() incrementally, no remount
#   lat, lon     — badge anchor
#   watch_type   — weather | wave_height | lightning | cyclone | geofence_approach | pfz_shift
#   status       — "clear" | "active"   (active == an unread crossing notification exists)
#   severity     — info | advisory | warning | danger  (highest unread; "info" when clear)
#   enabled      — the watch toggle; a disabled watch still returns a badge with status "clear"
#   last_fired_at, updated_at — ISO 8601 UTC or null
#   label        — short human string for the badge tooltip


def _iso(dt: Any) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt is not None else None


def badge_for_watch(db: Session, watch: SentinelSubscription) -> dict[str, Any]:
    from orca.db.notifications_models import Notification
    from orca.db.notifications_repo import watch_location

    loc = watch_location(watch) or {"lat": None, "lon": None}
    unread = (
        db.query(Notification)
        .filter(Notification.watch_id == watch.id, Notification.read_at.is_(None))
        .order_by(Notification.created_at.desc())
        .all()
    )
    rank = {"info": 0, "advisory": 1, "warning": 2, "danger": 3}
    severity = "info"
    for n in unread:
        if rank.get(n.severity, 0) > rank.get(severity, 0):
            severity = n.severity
    active = bool(unread) and watch.enabled
    return {
        "watch_id": str(watch.id),
        "lat": loc["lat"],
        "lon": loc["lon"],
        "watch_type": watch.watch_type,
        "status": "active" if active else "clear",
        "severity": severity if active else "info",
        "enabled": watch.enabled,
        "unread_count": len(unread),
        "last_fired_at": _iso(watch.last_fired_at),
        "updated_at": _iso(watch.updated_at),
        "label": f"{watch.watch_type.replace('_', ' ').title()} watch",
    }


def watch_badges_for_user(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    from orca.db.notifications_repo import list_watches_for_user, watch_location

    return [
        badge_for_watch(db, w)
        for w in list_watches_for_user(db, user_id)
        if watch_location(w) is not None
    ]


def badges_as_map_layer(badges: list[dict[str, Any]]) -> dict[str, Any]:
    """The same badge list as a frozen-contract MapLayer (layer_type
    "SentinelWatch"). D3 renders this; D2 never calls MapView."""
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
            "properties": {k: v for k, v in b.items() if k not in ("lat", "lon")},
        }
        for b in badges
        if b["lat"] is not None and b["lon"] is not None
    ]
    lons = [b["lon"] for b in badges if b["lon"] is not None]
    lats = [b["lat"] for b in badges if b["lat"] is not None]
    bounds = (
        (min(lons), min(lats), max(lons), max(lats)) if lons else (68.0, 6.0, 98.0, 24.0)
    )
    return {
        "layer_id": "sentinel_watch_badges",
        "layer_type": "SentinelWatch",
        "geojson": {"type": "FeatureCollection", "features": features},
        "tile_url": None,
        "bounds": bounds,
        "timestamps": None,
        "forecast_frames": None,
        "style_hints": {
            "palette": "risk-red-amber-green",
            "opacity": 1.0,
            "min_zoom": 0,
            "max_zoom": 22,
            "simplify_tolerance": 0.0,
            "color_ramp": None,
        },
        "weight": "light",
        "persona_visibility": (),
        "source_provenance": (),
        "result_refs": ("sentinel",),
    }
