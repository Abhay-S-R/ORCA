"""HTTP surface for /ops — District Ops (Phase 3 D2, plan §4 D2 Day 20).
Coastal-authority only (require_role). Sector threat matrix, CAP 1.2 builder,
four-channel broadcast preview, audit trail. Aggregation is a hard constraint
(orca/ops/aggregation.py): counts per sector, never plottable individuals.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from orca.auth.rbac import require_role
from orca.db.engine import get_db
from orca.db.models import User
from orca.ops.aggregation import notification_severity_counts, sector_threat_matrix
from orca.ops.cap import build_cap_xml, four_channel_preview

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
