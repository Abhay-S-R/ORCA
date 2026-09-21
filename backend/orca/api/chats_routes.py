"""HTTP surface for saved Ask chats (003_chat_history.sql). Thin — logic is
in orca/db/chats_repo.py. Same pattern as watches_routes.py: identity from the
bearer token, never the body; every lookup is owner-scoped in the repo's SQL.

One route here is deliberately unauthenticated: PUT /api/session/{id}/context
restores a chat's conversational context window (orca/session.py) when it is
reopened — for guest chats too, which only exist in the browser. It grants
nothing /query doesn't already: any caller holding a session id can already
add turns to that window by asking with it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from orca import session as session_memory
from orca.auth.rbac import get_current_user
from orca.db import chats_repo
from orca.db.engine import get_db
from orca.db.models import User

router = APIRouter(prefix="/api", tags=["chats"])

Persona = Literal["fisherman", "commercial_navigator", "researcher", "coastal_authority", "unresolved"]

# A stored answer is the /query final_response minus its trace and map layers
# (chats_repo.storable_answer) — a few KB in practice. The cap only stops a
# client from parking arbitrary blobs in the database under a chat.
# ponytail: per-field cap, no whole-request cap — Starlette reads the body
# before validation; put a body-size limit on the proxy when this is deployed.
_MAX_ANSWER_BYTES = 64_000


def _checked_answer(answer: dict[str, Any]) -> dict[str, Any]:
    answer = chats_repo.storable_answer(answer)
    if not isinstance(answer.get("final_english_response"), str):
        # ValueError, not TypeError: pydantic turns only ValueError/AssertionError
        # from a validator into a 422 — a TypeError would surface as a 500.
        raise ValueError("answer must be a /query final_response (final_english_response missing)")  # noqa: TRY004
    if len(json.dumps(answer, default=str)) > _MAX_ANSWER_BYTES:
        raise ValueError(f"answer exceeds {_MAX_ANSWER_BYTES} bytes")
    return answer


class Span(BaseModel):
    """One agent's entry in a saved turn's activity strip.

    `confidence_tier` is NOT optional decoration: without it this model
    silently dropped the field on every save — Pydantic discards what a model
    does not declare — so a signed-in user's chats could never keep their
    agent confidence, and a reopened chat drew plain ticks. Guest chats in
    localStorage were unaffected, which is why it looked like an "old chats"
    problem rather than an account-store one.

    Still optional on the way in: a turn that genuinely has no tier for an
    agent (a failed one, or a turn saved before the field existed) must save
    rather than 422."""
    agent_name: str = Field(max_length=64)
    status: str = Field(max_length=16)
    confidence_tier: Literal["HIGH", "MEDIUM", "LOW_DATA"] | None = None


class TurnIn(BaseModel):
    asked_query: str = Field(min_length=1, max_length=2000)
    answer: dict[str, Any]
    spans: list[Span] = Field(default_factory=list, max_length=40)
    rendered_as: Persona | None = None

    @field_validator("answer")
    @classmethod
    def _answer(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _checked_answer(v)


class SaveTurnIn(TurnIn):
    persona: Persona = "unresolved"


class ChatSummaryOut(BaseModel):
    id: uuid.UUID
    title: str | None
    pinned: bool
    persona: str
    language: str
    started_at: datetime
    last_seen_at: datetime
    turn_count: int
    first_question: str | None
    last_question: str | None


class ChatTurnOut(BaseModel):
    query_id: uuid.UUID
    asked_query: str
    answer: dict[str, Any]
    spans: list[Span]
    rendered_as: Persona | None
    created_at: datetime


class ChatOut(ChatSummaryOut):
    turns: list[ChatTurnOut]


class ChatPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        # A blank rename clears the custom title, so the chat falls back to
        # its first question again — rather than saving an empty name.
        return (v or "").strip() or None


class ImportTurnIn(TurnIn):
    query_id: uuid.UUID
    created_at: datetime


class ImportChatIn(BaseModel):
    id: uuid.UUID
    title: str | None = Field(default=None, max_length=120)
    pinned: bool = False
    persona: Persona = "unresolved"
    turns: list[ImportTurnIn] = Field(max_length=100)


class ImportIn(BaseModel):
    chats: list[ImportChatIn] = Field(max_length=25)


class ContextTurnIn(BaseModel):
    asked_query: str = Field(min_length=1, max_length=2000)
    answer: dict[str, Any]

    @field_validator("answer")
    @classmethod
    def _answer(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _checked_answer(v)


class ContextIn(BaseModel):
    turns: list[ContextTurnIn] = Field(max_length=session_memory.MAX_TURNS)


_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "chat not found")


def _summary(db: Session, user: User, chat_id: uuid.UUID) -> ChatSummaryOut:
    rows = chats_repo.list_chats(db, user.id, chat_id=chat_id)
    if not rows:
        raise _NOT_FOUND
    return ChatSummaryOut(**rows[0])


@router.get("/chats", response_model=list[ChatSummaryOut])
def list_chats(
    q: str | None = Query(default=None, max_length=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatSummaryOut]:
    return [ChatSummaryOut(**row) for row in chats_repo.list_chats(db, user.id, q=q)]


@router.get("/chats/{chat_id}", response_model=ChatOut)
def get_chat(chat_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ChatOut:
    summary = _summary(db, user, chat_id)
    return ChatOut(**summary.model_dump(), turns=[ChatTurnOut(**t) for t in chats_repo.chat_turns(db, chat_id)])


@router.put("/chats/{chat_id}/turns/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def save_turn(
    chat_id: uuid.UUID, query_id: uuid.UUID, body: SaveTurnIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> Response:
    """Creates the chat on its first turn. Idempotent per query_id."""
    try:
        chats_repo.save_turn(
            db, user_id=user.id, chat_id=chat_id, query_id=query_id, asked_query=body.asked_query,
            answer=body.answer, spans=[s.model_dump() for s in body.spans],
            rendered_as=body.rendered_as, persona=body.persona,
        )
    except chats_repo.ChatOwnershipError:
        db.rollback()
        raise _NOT_FOUND from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/chats/{chat_id}", response_model=ChatSummaryOut)
def update_chat(
    chat_id: uuid.UUID, body: ChatPatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ChatSummaryOut:
    """Rename and/or pin — only the fields actually sent change."""
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    if fields.get("pinned", False) is None:
        del fields["pinned"]
    if not chats_repo.update_chat(db, user.id, chat_id, fields=fields):
        raise _NOT_FOUND
    return _summary(db, user, chat_id)


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    if not chats_repo.delete_chat(db, user.id, chat_id):
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chats/import")
def import_chats(body: ImportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Guest chats from this browser, moved into the account on consent."""
    chats = [
        {**c.model_dump(exclude={"turns"}), "turns": [
            {**t.model_dump(), "spans": [s.model_dump() for s in t.spans]}
            for t in sorted(c.turns, key=lambda t: t.created_at)
        ]}
        for c in body.chats
    ]
    return {"imported": chats_repo.import_chats(db, user.id, chats)}


@router.put("/session/{session_id}/context", status_code=status.HTTP_204_NO_CONTENT)
def restore_context(session_id: uuid.UUID, body: ContextIn) -> Response:
    """Rebuild a reopened chat's context window from its stored turns, so a
    follow-up continues the conversation instead of being answered as new."""
    session_memory.replace_turns(
        str(session_id), [session_memory.turn_from_final(t.asked_query, t.answer) for t in body.turns],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
