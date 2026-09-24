"""HTTP surface for /ops — District Ops (Phase 3 D2, plan §4 D2 Day 20).
Coastal-authority only (require_role). Sector threat matrix, CAP 1.2 builder,
four-channel broadcast preview, audit trail. Aggregation is a hard constraint
(orca/ops/aggregation.py): counts per sector, never plottable individuals.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.auth.rbac import require_role
from orca.db.engine import get_db
from orca.db.models import User
from orca.api.trace_routes import get_trace, render_query
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
        headline=headline, description=description, instruction=instruction, severity=severity,
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
        "exported_at": datetime.now(timezone.utc).isoformat(),
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
