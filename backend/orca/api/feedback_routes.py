"""Advisory feedback (Phase 3 D2, plan §4.10).

Helpful / Not accurate / Report issue on any advisory card — one tap, no
dialog; "Report issue" carries an optional comment. Writes `advisory_feedback`
joined by `query_id`, audited in `audit_trace_log`. The drill-down is the
feature: the response hands back the trace route so a flagged advisory opens
its full agent trace in D3's reasoning graph.

Explicitly NOT built: auto-retraining, threshold auto-tuning (plan §4.10).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from orca.db.engine import get_db
from orca.db.models import AuditTraceLog, User
from orca.db.notifications_repo import create_feedback, feedback_for_query
from orca.db.repositories import get_user_by_id
from orca.notifications.contracts import FeedbackIn

router = APIRouter(prefix="/api", tags=["feedback"])
_bearer = HTTPBearer(auto_error=False)


def _optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Feedback is first-class for anonymous sessions too (a fisherman using
    the PWA without an account still gets to say 'not accurate'). A valid
    token attributes the row; anything else falls through to None."""
    if credentials is None:
        return None
    try:
        from orca.auth.security import decode_token

        payload = decode_token(credentials.credentials, expected_type="access")
        return get_user_by_id(db, uuid.UUID(payload["sub"]))
    except Exception:  # noqa: BLE001
        return None


@router.post("/feedback")
def submit(
    body: FeedbackIn, user: User | None = Depends(_optional_user), db: Session = Depends(get_db)
) -> dict:
    fb = create_feedback(
        db,
        query_id=body.query_id,
        kind=body.kind,
        user_id=user.id if user else None,
        advisory_ref=body.advisory_ref,
        comment=body.comment,
    )
    db.add(
        AuditTraceLog(
            query_id=body.query_id,
            session_id=None,
            agent_name="feedback",
            event="agent_complete",
            outputs={"kind": body.kind, "advisory_ref": body.advisory_ref, "has_comment": bool(body.comment)},
            status="ok",
        )
    )
    db.commit()
    return {
        "id": fb.id,
        "query_id": str(body.query_id),
        "kind": body.kind,
        # The drill-down: open the full agent trace for this advisory. D3's
        # /reasoning consumes D1's /trace/{query_id}; if that endpoint is not
        # up yet the route still renders and shows "trace unavailable".
        "trace_route": f"/reasoning?query_id={body.query_id}",
    }


@router.get("/feedback/{query_id}")
def for_query(query_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    rows = feedback_for_query(db, query_id)
    return {
        "query_id": str(query_id),
        "count": len(rows),
        "feedback": [
            {"id": r.id, "kind": r.kind, "comment": r.comment, "created_at": r.created_at.isoformat()}
            for r in rows
        ],
        "trace_route": f"/reasoning?query_id={query_id}",
    }
