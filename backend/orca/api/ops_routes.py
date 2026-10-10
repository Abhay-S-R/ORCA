"""HTTP surface for /ops — District Ops (Phase 3 D2, plan §4 D2 Day 20).
Coastal-authority only (require_role). Sector threat matrix, CAP 1.2 builder,
four-channel broadcast preview, audit trail. Aggregation is a hard constraint
(orca/ops/aggregation.py): counts per sector, never plottable individuals.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.api.trace_routes import get_trace, render_query
from orca.auth.rbac import require_role
from orca.db.engine import get_db
from orca.db.models import User
from orca.db.repositories import persist_security_event
from orca.ops.aggregation import notification_severity_counts, sector_threat_matrix
from orca.ops.cap import build_cap_xml, build_multilingual_cap_xml, four_channel_preview
from orca.ops.distress_queue import list_events as list_distress_events
from orca.ops.distress_queue import set_state as set_distress_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ops", tags=["district-ops"])

_authority = require_role("authority", "admin")


@router.get("/sectors")
def sectors(user: User = Depends(_authority), db: Session = Depends(get_db)) -> dict:
    return {
        "district_severity_counts": notification_severity_counts(db),
        "matrix": sector_threat_matrix(db),
    }


class CapRequest(BaseModel):
    headline: str
    description: str
    event: str = "Marine Weather Hazard"
    severity: str = "warning"
    area_desc: str = "Thoothukudi coastal sector"
    instruction: str | None = None
    circle: tuple[float, float, float] | None = None  # (lat, lon, radius_km)
    language: str = "en-IN"


@router.post("/cap")
def cap(body: CapRequest, user: User = Depends(_authority)) -> Response:
    xml = build_cap_xml(
        headline=body.headline,
        description=body.description,
        event=body.event,
        severity=body.severity,
        area_desc=body.area_desc,
        instruction=body.instruction or "Return to the nearest safe harbour. Monitor VHF channel 16.",
        circle=body.circle,
        language=body.language,
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/broadcast/preview")
def broadcast_preview(
    verdict: str = "NO-GO",
    hazard: str = "High waves",
    location: str = "Thoothukudi",
    issued_at: str | None = None,
    user: User = Depends(_authority),
) -> dict:
    """The composer previews the message in all four of D1's channel
    renderers side by side before it goes anywhere (plan §4 D2 Day 20)."""
    return {"channels": four_channel_preview(verdict=verdict, hazard=hazard, location=location, issued_at=issued_at)}


def _geom_latlon(geom: Any) -> dict[str, float] | None:
    if geom is None:
        return None
    try:
        from geoalchemy2.shape import to_shape
        from shapely.geometry import Point

        shp = to_shape(geom)
        if isinstance(shp, Point):
            return {"lat": shp.y, "lon": shp.x}
    except Exception:
        pass
    return None


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class BroadcastPublishRequest(BaseModel):
    title: str
    body: str
    severity: Literal["info", "advisory", "warning", "danger"] = "warning"
    target_audience: Literal["all", "fisherman", "commercial_navigator", "researcher", "port_users"] = "all"
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_km: float = 30.0
    channels: list[str] = ["in_app"]


@router.post("/broadcast/publish")
def broadcast_publish(
    body: BroadcastPublishRequest,
    user: User = Depends(_authority),
    db: Session = Depends(get_db),
) -> dict:
    """Allows each coastal authority account to compose and issue alerts for every
    other user type (all mariners, fishermen, commercial navigators, researchers, or port mariners).
    
    Creates in-app notifications for each target recipient, connects to matching active
    watches in the sector (updating watch alert history), and records an audited security event.
    """
    from sqlalchemy import func, select
    from orca.db.notifications_models import SentinelSubscription
    from orca.db.notifications_repo import (
        create_notification,
        list_watches_for_user,
        mark_watch_fired,
        watch_location,
    )
    from orca.ops.port_authorities import resolve_port_authority_config

    # Resolve target coordinates (explicit -> authority's home port geom -> authority port config)
    target_lat = body.lat
    target_lon = body.lon
    if target_lat is None or target_lon is None:
        if user.home_port is not None:
            hl = _geom_latlon(user.home_port)
            if hl:
                target_lat = hl["lat"]
                target_lon = hl["lon"]
        if target_lat is None and user.home_port_name:
            cfg = resolve_port_authority_config(user.home_port_name)
            target_lat = cfg.get("lat")
            target_lon = cfg.get("lon")

    target_location = body.location or user.home_port_name or "Coastal Sector"

    # Filter recipients: only active non-authority users
    base_query = select(User).where(User.status == "active", User.role != "authority")

    if body.target_audience == "all":
        recipients = list(db.execute(base_query).scalars())
    elif body.target_audience in ("fisherman", "commercial_navigator", "researcher"):
        stmt = base_query.where(User.default_persona == body.target_audience)
        recipients = list(db.execute(stmt).scalars())
    elif body.target_audience == "port_users":
        port_name = (user.home_port_name or target_location).strip()
        if port_name:
            stmt = base_query.where(func.lower(User.home_port_name) == port_name.lower())
            recipients = list(db.execute(stmt).scalars())
            if not recipients:
                recipients = list(db.execute(base_query).scalars())
        else:
            recipients = list(db.execute(base_query).scalars())
    else:
        recipients = list(db.execute(base_query).scalars())

    watches_updated = 0
    query_id = uuid.uuid4()
    breakdown = {"fisherman": 0, "commercial_navigator": 0, "researcher": 0, "unresolved": 0, "other": 0}

    for r in recipients:
        persona = r.default_persona
        if persona in breakdown:
            breakdown[persona] += 1
        else:
            breakdown["other"] += 1

        # Check for active watches matching this sector or location
        user_watches = list_watches_for_user(db, r.id)
        matching_watch: SentinelSubscription | None = None

        for w in user_watches:
            if not w.enabled:
                continue
            if target_lat is not None and target_lon is not None:
                w_loc = watch_location(w)
                if w_loc is not None:
                    dist = _haversine_distance_km(target_lat, target_lon, w_loc["lat"], w_loc["lon"])
                    watch_rad = float(w.radius_km or 25.0)
                    if dist <= (watch_rad + body.radius_km):
                        matching_watch = w
                        break
            if matching_watch is None and w.watch_type in ("all", "weather", "cyclone", "wave_height"):
                matching_watch = w
                break

        matching_watch_id = matching_watch.id if matching_watch is not None else None
        if matching_watch is not None:
            mark_watch_fired(db, matching_watch.id)
            watches_updated += 1

        create_notification(
            db,
            user_id=r.id,
            watch_id=matching_watch_id,
            query_id=query_id,
            severity=body.severity,
            title=body.title,
            body=body.body,
            channel="in_app",
            status="sent",
            rendered_payload={
                "authority_id": str(user.id),
                "authority_name": user.display_name or "Coastal Authority",
                "authority_port": user.home_port_name or target_location,
                "target_audience": body.target_audience,
                "channels": body.channels,
                "location": target_location,
                "lat": target_lat,
                "lon": target_lon,
                "radius_km": body.radius_km,
                "published_at": datetime.now(UTC).isoformat(),
            },
        )

    # Persist security event for full audit traceability
    persist_security_event(
        db,
        query_id=query_id,
        event="coastal_authority_alert_broadcast",
        status="ok",
        outputs={
            "authority_id": str(user.id),
            "authority_name": user.display_name,
            "authority_port": user.home_port_name or target_location,
            "target_audience": body.target_audience,
            "severity": body.severity,
            "title": body.title,
            "location": target_location,
            "delivered_count": len(recipients),
            "watches_updated": watches_updated,
            "breakdown": breakdown,
        },
    )
    db.commit()

    return {
        "status": "published",
        "alert_id": str(query_id),
        "title": body.title,
        "severity": body.severity,
        "target_audience": body.target_audience,
        "authority_name": user.display_name or "Coastal Authority",
        "authority_port": user.home_port_name or target_location,
        "delivered_count": len(recipients),
        "watches_updated": watches_updated,
        "breakdown": breakdown,
        "published_at": datetime.now(UTC).isoformat(),
    }


@router.get("/broadcast/history")
def broadcast_history(
    limit: int = 20,
    user: User = Depends(_authority),
    db: Session = Depends(get_db),
) -> dict:
    """List recent broadcast alerts issued by coastal authorities."""
    rows = db.execute(
        text(
            "SELECT query_id, outputs, created_at FROM audit_trace_log "
            "WHERE event = 'coastal_authority_alert_broadcast' "
            "ORDER BY created_at DESC LIMIT :lim"
        ),
        {"lim": min(limit, 50)},
    ).all()
    history_items = []
    for r in rows:
        outputs = r[1] or {}
        history_items.append({
            "alert_id": str(r[0]),
            "title": outputs.get("title", "Maritime Alert"),
            "severity": outputs.get("severity", "warning"),
            "target_audience": outputs.get("target_audience", "all"),
            "authority_name": outputs.get("authority_name", "Coastal Authority"),
            "authority_port": outputs.get("authority_port", "Unknown"),
            "delivered_count": outputs.get("delivered_count", 0),
            "watches_updated": outputs.get("watches_updated", 0),
            "published_at": r[2].isoformat() if r[2] else None,
        })
    return {"history": history_items}


@router.get("/authorities")
def list_authorities(db: Session = Depends(get_db)) -> dict:
    """Public roster of pre-configured coastal authorities for all major ports."""
    from orca.ops.port_authorities import PORT_AUTHORITIES

    return {
        "authorities": [
            {
                "port_name": a["port_name"],
                "slug": a["slug"],
                "lat": a["lat"],
                "lon": a["lon"],
                "email": a["email"],
                "display_name": a["display_name"],
                "state": a["state"],
                "phone": a["phone"],
            }
            for a in PORT_AUTHORITIES
        ]
    }




# P6.10 — the pilot's two named languages beyond English (orca_final's Palk
# Bay pilot is Tamil-coast; Hindi is the widest second language among the
# other districts the DLC names). Not all ten languages `orca.agents.language`
# supports: an authority composer preview is a live, synchronous call, and
# translating into all ten on every keystroke-adjacent request is not a
# request this endpoint asks anyone to pay for. Extend this list, not the
# translation code, if a specific district needs a different pair.
_CAP_PREVIEW_LANGUAGES: tuple[tuple[str, str], ...] = (("ta-IN", "ta"), ("hi-IN", "hi"))


@router.get("/broadcast/cap-multilingual")
def broadcast_cap_multilingual(
    headline: str,
    description: str,
    instruction: str = "Return to the nearest safe harbour. Monitor VHF channel 16.",
    severity: str = "warning",
    area_desc: str = "Thoothukudi coastal sector",
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float = 25.0,
    user: User = Depends(_authority),
) -> dict:
    """P6.10 (orca_final §12.1) — the CAP 1.2 `<info>` block per language:
    one multilingual CAP document (English + the pilot's named languages,
    each its own `<info>` element per the OASIS spec) so the composer can
    preview exactly what goes out in Tamil and Hindi, not just English. Real
    translation via `orca.agents.language.translate_from_english` — never a
    fabricated string — degrading to English-only with a named reason if no
    translation backend is registered (the same IndicTransToolkit gap
    `run_egress` already discloses elsewhere)."""
    from orca.agents import language as _lang

    circle = (lat, lon, radius_km) if lat is not None and lon is not None else None
    translations: dict[str, tuple[str, str, str]] = {"en-IN": (headline, description, instruction)}
    skipped: list[str] = []
    for cap_lang, code in _CAP_PREVIEW_LANGUAGES:
        try:
            translations[cap_lang] = (
                _lang.translate_from_english(headline, code),  # type: ignore[arg-type]
                _lang.translate_from_english(description, code),  # type: ignore[arg-type]
                _lang.translate_from_english(instruction, code),  # type: ignore[arg-type]
            )
        except Exception as exc:
            skipped.append(cap_lang)
            logger.warning("CAP multilingual preview: %s translation unavailable (%s)", cap_lang, exc)

    xml = build_multilingual_cap_xml(
        severity=severity,
        area_desc=area_desc, circle=circle, translations=translations,
    )
    return {
        "cap_xml": xml,
        "languages": list(translations),
        "skipped_languages": skipped,
        "skipped_reason": (
            "IndicTrans2 not installed/loaded in this environment — see "
            "backend/scripts/download_ml_models.py."
        ) if skipped else None,
    }


@router.get("/audit")
def audit_trail(
    query_id: uuid.UUID | None = None,
    limit: int = 100,
    user: User = Depends(_authority),
    db: Session = Depends(get_db),
) -> dict:
    """The audit trail view — reuses audit_trace_log, no parallel store."""
    if query_id is not None:
        rows = db.execute(
            text(
                "SELECT agent_name, event, status, confidence, latency_ms, error_detail, created_at "
                "FROM audit_trace_log WHERE query_id = :qid ORDER BY created_at"
            ),
            {"qid": query_id},
        ).all()
    else:
        rows = db.execute(
            text(
                "SELECT agent_name, event, status, confidence, latency_ms, error_detail, created_at "
                "FROM audit_trace_log WHERE agent_name IN ('sentinel', 'feedback', 'security') "
                "ORDER BY created_at DESC LIMIT :lim"
            ),
            {"lim": min(limit, 500)},
        ).all()
    return {
        "query_id": str(query_id) if query_id else None,
        "entries": [
            {
                "agent_name": r[0], "event": r[1], "status": r[2], "confidence": r[3],
                "latency_ms": r[4], "error_detail": r[5], "created_at": r[6].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/export")
def export_evidence(
    query_id: uuid.UUID,
    verdict: str | None = None,
    hazard: str | None = None,
    location: str | None = None,
    user: User = Depends(_authority),
    db: Session = Depends(get_db),
) -> dict:
    """P6.13 (orca_final §12.5, §30.6) — everything behind one query's
    verdict, bundled for an authority to hand to an inspector or attach to
    an incident report: the audit trail (this endpoint's own `/audit`
    logic, scoped to one query_id), the full per-agent trace graph
    (`/trace/{query_id}` — every span, its confidence, its source
    provenance), and the citations + re-rendered narrative a coastal-
    authority persona would see (`/render`'s own `render_query`, reused
    rather than duplicated). `verdict`/`hazard`/`location`, if supplied,
    also attach the nine-channel broadcast preview and its CAP 1.2 XML —
    "the evidence behind a CAP broadcast" the point's own text names —
    since no broadcast is persisted anywhere to look up by id (P6.5 names
    this as a disclosed limit, not silently worked around here).
    """
    rows = db.execute(
        text(
            "SELECT agent_name, event, status, confidence, latency_ms, error_detail, created_at "
            "FROM audit_trace_log WHERE query_id = :qid ORDER BY created_at"
        ),
        {"qid": query_id},
    ).all()
    audit_entries = [
        {
            "agent_name": r[0], "event": r[1], "status": r[2], "confidence": r[3],
            "latency_ms": r[4], "error_detail": r[5], "created_at": r[6].isoformat(),
        }
        for r in rows
    ]

    trace = get_trace(str(query_id))
    rendered = render_query(str(query_id), persona="coastal_authority")

    bundle: dict[str, Any] = {
        "query_id": str(query_id),
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": {"user_id": str(user.id), "role": user.role},
        "audit_trail": audit_entries,
        "trace": trace.model_dump(),
        "citations": rendered.citations,
        "final_english_response": rendered.final_english_response,
        "confidence_tier": rendered.confidence_tier,
    }
    if verdict and hazard and location:
        bundle["broadcast_preview"] = four_channel_preview(verdict=verdict, hazard=hazard, location=location)
        bundle["cap_xml"] = build_cap_xml(headline=f"{verdict}: {hazard}", description=f"{hazard} reported near {location}.", area_desc=location)

    persist_security_event(
        db, query_id=query_id, event="evidence_export", status="ok",
        outputs={"user_id": str(user.id), "query_id": str(query_id)},
    )
    db.commit()
    return bundle


# --- Distress queue (P4.16) — the one place an authority sees a position, and
# only while the incident is not closed; every such read is audited. ---------

@router.get("/distress")
def distress_queue(hours: int = 24, user: User = Depends(_authority), db: Session = Depends(get_db)) -> dict:
    return {"events": list_distress_events(db, reader_id=user.id, hours=hours)}


@router.post("/distress/{event_id}/{action}")
def distress_transition(
    event_id: uuid.UUID, action: Literal["acknowledge", "close"],
    user: User = Depends(_authority), db: Session = Depends(get_db),
) -> dict:
    result = set_distress_state(db, event_id, action, user.id)
    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"distress event not found, or already past '{action}'")
    return result
