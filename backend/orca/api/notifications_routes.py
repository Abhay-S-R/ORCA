"""HTTP surface for the in-app notification feed (Phase 3 D2).

Read/unread state, the bell count, and an SSE stream so the toast/bell
updates without polling from the client. The stream reuses the same
`text/event-stream` + `data: {json}\n\n` framing as /query — no second event
system, no WebSocket layer (plan §8).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from orca.auth.rbac import get_current_user
from orca.auth.security import TokenError, decode_token
from orca.db.engine import get_db, get_sessionmaker
from orca.db.models import User
from orca.db.notifications_repo import (
    list_notifications_for_user,
    mark_all_read,
    mark_notification_read,
    unread_count,
)
from orca.db.repositories import get_user_by_id
from orca.notifications.contracts import NotificationOut

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notifications"])

_STREAM_POLL_SECONDS = 5


def _out(n) -> NotificationOut:
    return NotificationOut(
        id=n.id, watch_id=n.watch_id, query_id=n.query_id, severity=n.severity,
        title=n.title, body=n.body, channel=n.channel, status=n.status,
        rendered_payload=n.rendered_payload, read=n.read_at is not None, created_at=n.created_at,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def feed(
    unread_only: bool = False,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    return [_out(n) for n in list_notifications_for_user(db, user.id, limit=limit, unread_only=unread_only)]


@router.get("/notifications/unread_count")
def unread(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    return {"count": unread_count(db, user.id)}


@router.post("/notifications/read_all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    n = mark_all_read(db, user.id)
    db.commit()
    return {"marked_read": n}


@router.post("/notifications/{notification_id}/read")
def read_one(
    notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, bool]:
    updated = mark_notification_read(db, notification_id, user.id)
    db.commit()
    if not updated:
        # already read, or not this user's — same response either way, no leak
        return {"ok": True}
    return {"ok": True}


@router.get("/notifications/stream")
async def stream(token: str | None = Query(default=None)) -> StreamingResponse:
    """SSE. `EventSource` cannot send an Authorization header, so the access
    token comes as a query param (same tradeoff the wider SSE ecosystem
    makes); it is validated here exactly like the bearer header would be.

    `token` is optional at the signature so that *absent* credentials answer
    401 like every other route, rather than the 422 FastAPI produces for a
    missing required query param — a client cannot tell "log in again" from
    "you built the URL wrong" out of a validation error.
    """
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing access token")
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError) as exc:
        _log.info("rejected stream token: %s", exc)  # reason to the log, not the caller
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc

    async def _events() -> AsyncIterator[str]:
        seen: set[str] = set()
        first = True
        while True:
            db = get_sessionmaker()()
            try:
                if get_user_by_id(db, user_id) is None:
                    break
                rows = list_notifications_for_user(db, user_id, limit=30)
            finally:
                db.close()
            for n in reversed(rows):  # oldest first on the wire
                if str(n.id) in seen:
                    continue
                seen.add(str(n.id))
                if first:
                    continue  # don't replay the backlog as "new" toasts on connect
                yield f"data: {json.dumps(_out(n).model_dump(mode='json'))}\n\n"
            first = False
            yield ": keep-alive\n\n"
            await asyncio.sleep(_STREAM_POLL_SECONDS)

    return StreamingResponse(_events(), media_type="text/event-stream")
