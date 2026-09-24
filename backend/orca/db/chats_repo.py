"""Saved Ask chats for signed-in users (003_chat_history.sql) — plain
functions over a Session, same style as notifications_repo.py.

A chat is a `sessions` row; each answered question is two
`conversation_turns` rows (role user + role assistant) sharing a query_id.

Ownership rule enforced in the SQL, not just at the route: every lookup,
update and delete filters by user_id in its WHERE clause, so a forgotten
route check still cannot read or change another user's chat.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from orca.db.models import ConversationTurn, SessionRow

# The final_response fields the chat card never reads but that dominate its
# size: the full agent trace (already persisted per query_id in
# audit_trace_log) and the map layers (re-derived when the map is focused).
_UNSTORED_ANSWER_KEYS = ("audit_trace_log", "visualization_payload")


class ChatOwnershipError(Exception):
    """The chat id exists but belongs to someone else. Routes turn this into
    the same 404 as a missing chat, so an id can't be probed for existence."""


def storable_answer(answer: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in answer.items() if k not in _UNSTORED_ANSWER_KEYS}


def _like(q: str) -> str:
    # "!" as the ESCAPE character, not a backslash: a backslash has to survive
    # Python's string escaping and then SQL's, and it once reached Postgres as
    # an empty ESCAPE clause — so a search for "100%" matched nothing.
    escaped = q.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return f"%{escaped}%"


def list_chats(
    db: Session, user_id: uuid.UUID, *, q: str | None = None, limit: int = 200, chat_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """The history rail: pinned first, then most recently active. A session
    with no user turns (one Sentinel wrote into, say) is not a chat.
    `chat_id` narrows it to one row — what a rename/pin returns."""
    filters = ""
    params: dict[str, Any] = {"uid": user_id, "limit": limit}
    if chat_id is not None:
        filters += " AND s.id = :cid"
        params["cid"] = chat_id
    if q and q.strip():
        # ponytail: ILIKE scan over the user's own turns — fine for hundreds of
        # chats per user; add a trigram index if one account ever holds thousands.
        filters += """
          AND (s.title ILIKE :pat ESCAPE '!' OR EXISTS (
                SELECT 1 FROM conversation_turns ts
                WHERE ts.session_id = s.id AND ts.role = 'user' AND ts.text_original ILIKE :pat ESCAPE '!'))"""
        params["pat"] = _like(q.strip())
    rows = db.execute(
        text(f"""
        SELECT s.id, s.title, s.pinned, s.persona::text AS persona, s.language,
               s.started_at, s.last_seen_at,
               count(t.id) AS turn_count,
               (array_agg(t.text_original ORDER BY t.created_at, t.id))[1] AS first_question,
               (array_agg(t.text_original ORDER BY t.created_at DESC, t.id DESC))[1] AS last_question
        FROM sessions s
        JOIN conversation_turns t ON t.session_id = s.id AND t.role = 'user'
        WHERE s.user_id = :uid AND s.channel = 'web' {filters}
        GROUP BY s.id
        ORDER BY s.pinned DESC, s.last_seen_at DESC
        LIMIT :limit
        """),
        params,
    ).mappings()
    return [dict(r) for r in rows]


def get_chat(db: Session, user_id: uuid.UUID, chat_id: uuid.UUID) -> SessionRow | None:
    return db.execute(
        select(SessionRow).where(SessionRow.id == chat_id, SessionRow.user_id == user_id)
    ).scalar_one_or_none()


def chat_turns(db: Session, chat_id: uuid.UUID) -> list[dict[str, Any]]:
    """Answered turns in the order they were asked. Call only after
    get_chat() confirmed ownership. Assistant rows with no user row
    (Sentinel's broadcasts) are not chat turns and are skipped."""
    rows = db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.session_id == chat_id)
        .order_by(ConversationTurn.created_at, ConversationTurn.id)
    ).scalars()
    by_query: dict[uuid.UUID, dict[str, Any]] = {}
    order: list[uuid.UUID] = []
    for row in rows:
        entry = by_query.setdefault(row.query_id, {"query_id": row.query_id})
        if row.role == "user":
            order.append(row.query_id)
            entry["asked_query"] = row.text_original or ""
            entry["created_at"] = row.created_at
        elif row.payload is not None:
            entry["answer"] = row.payload.get("answer")
            entry["spans"] = row.payload.get("spans") or []
            entry["rendered_as"] = row.payload.get("rendered_as")
    return [by_query[qid] for qid in order if by_query[qid].get("answer") is not None]


def _claim_chat(db: Session, user_id: uuid.UUID, chat_id: uuid.UUID, persona: str, language: str) -> bool:
    """Create the chat on its first saved turn, or confirm the caller owns it.
    INSERT ... ON CONFLICT DO NOTHING then a read, so two concurrent first
    saves can't both create it and a chat id can't be taken over. Returns
    whether this call created it."""
    created = db.execute(
        insert(SessionRow)
        .values(id=chat_id, user_id=user_id, persona=persona, language=language, channel="web")
        .on_conflict_do_nothing(index_elements=[SessionRow.id])
        .returning(SessionRow.id)
    ).first() is not None
    # An ownerless row is adopted, the same rule get_or_create_session applies
    # ("an anonymous chat that later signs in"). /query creates this row first
    # and cannot always tell who is asking, so without this every signed-in
    # user's new chat 404'd on its first save (chatbot plan C0.1). The UPDATE
    # only matches a NULL owner, so a row somebody else owns is never taken.
    db.execute(
        update(SessionRow)
        .where(SessionRow.id == chat_id, SessionRow.user_id.is_(None))
        .values(user_id=user_id)
    )
    owner = db.execute(select(SessionRow.user_id).where(SessionRow.id == chat_id)).scalar_one()
    if owner != user_id:
        raise ChatOwnershipError(str(chat_id))
    return created


def _upsert_turn_rows(
    db: Session, *, chat_id: uuid.UUID, query_id: uuid.UUID, asked_query: str,
    answer: dict[str, Any], spans: list[dict[str, Any]], rendered_as: str | None,
    created_at: datetime | None = None,
) -> None:
    for role, values in (
        ("user", {
            "text_original": asked_query,
            "text_english": answer.get("normalized_english_query") or asked_query,
            # No "payload" key at all: JSONB would store Python None as JSON
            # null rather than SQL NULL.
        }),
        ("assistant", {
            "text_original": answer.get("final_vernacular_response") or answer.get("final_english_response"),
            "text_english": answer.get("final_english_response"),
            "payload": {"answer": storable_answer(answer), "spans": spans, "rendered_as": rendered_as},
        }),
    ):
        stmt = insert(ConversationTurn).values(
            session_id=chat_id, query_id=query_id, role=role,
            **({"created_at": created_at} if created_at else {}), **values,
        )
        db.execute(stmt.on_conflict_do_update(
            index_elements=[ConversationTurn.session_id, ConversationTurn.query_id, ConversationTurn.role],
            set_={k: stmt.excluded[k] for k in values},
        ))


def save_turn(
    db: Session, *, user_id: uuid.UUID, chat_id: uuid.UUID, query_id: uuid.UUID, asked_query: str,
    answer: dict[str, Any], spans: list[dict[str, Any]], rendered_as: str | None, persona: str,
) -> None:
    """Idempotent: saving the same query_id again (a persona re-render, a
    retried request) updates that turn in place."""
    _claim_chat(db, user_id, chat_id, persona, answer.get("detected_language") or "en")
    _upsert_turn_rows(
        db, chat_id=chat_id, query_id=query_id, asked_query=asked_query,
        answer=answer, spans=spans, rendered_as=rendered_as,
    )
    db.execute(update(SessionRow).where(SessionRow.id == chat_id).values(last_seen_at=func.now()))
    db.commit()


def update_chat(
    db: Session, user_id: uuid.UUID, chat_id: uuid.UUID, *, fields: dict[str, Any]
) -> bool:
    """Rename and/or pin. `fields` holds only what the caller actually sent,
    so renaming never un-pins and pinning never clears a title. Does not touch
    last_seen_at: organising a chat isn't activity in it."""
    if not fields:
        return get_chat(db, user_id, chat_id) is not None
    result = cast(
        CursorResult,
        db.execute(
            update(SessionRow)
            .where(SessionRow.id == chat_id, SessionRow.user_id == user_id)
            .values(**fields)
        ),
    )
    db.commit()
    return result.rowcount == 1


def delete_chat(db: Session, user_id: uuid.UUID, chat_id: uuid.UUID) -> bool:
    """Hard delete — its turns go with it (ON DELETE CASCADE). The per-query
    audit_trace_log rows are the compliance record and stay, detached
    (ON DELETE SET NULL); they never held the chat's text."""
    result = cast(
        CursorResult,
        db.execute(delete(SessionRow).where(SessionRow.id == chat_id, SessionRow.user_id == user_id)),
    )
    db.commit()
    return result.rowcount == 1


def import_chats(db: Session, user_id: uuid.UUID, chats: list[dict[str, Any]]) -> int:
    """Guest chats from a browser, moved into the account on consent. One
    transaction for the whole batch. A chat id already owned by another
    account is skipped (not an error — it can't be the caller's); one the
    caller already owns is merged, turn by turn, idempotently."""
    imported = 0
    for chat in chats:
        chat_id = chat["id"]
        turns = chat["turns"]
        if not turns:
            continue
        try:
            created = _claim_chat(
                db, user_id, chat_id, chat["persona"], turns[0]["answer"].get("detected_language") or "en",
            )
        except ChatOwnershipError:
            continue
        for turn in turns:
            _upsert_turn_rows(
                db, chat_id=chat_id, query_id=turn["query_id"], asked_query=turn["asked_query"],
                answer=turn["answer"], spans=turn["spans"], rendered_as=turn["rendered_as"],
                created_at=turn["created_at"],
            )
        first_at, last_at = turns[0]["created_at"], turns[-1]["created_at"]
        # A new chat takes the browser's own title, pin and timeline. Merging
        # into a chat the account already has only ever adds to it — never
        # replaces its title or moves its last activity backwards.
        values: dict[str, Any] = (
            {"title": chat["title"], "pinned": chat["pinned"], "started_at": first_at, "last_seen_at": last_at}
            if created
            else {
                "title": func.coalesce(SessionRow.title, chat["title"]),
                "pinned": SessionRow.pinned | chat["pinned"],
                "started_at": func.least(SessionRow.started_at, first_at),
                "last_seen_at": func.greatest(SessionRow.last_seen_at, last_at),
            }
        )
        db.execute(update(SessionRow).where(SessionRow.id == chat_id).values(**values))
        imported += 1
    db.commit()
    return imported
