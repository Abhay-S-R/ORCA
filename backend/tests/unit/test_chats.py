"""Saved Ask chats (003_chat_history.sql) and refresh-token rotation
(004_refresh_tokens.sql), over HTTP against the real local Postgres — same
reasoning as test_auth.py: an ownership or upsert bug in SQL is exactly what a
mock would hide. Every user created here is deleted at teardown (CASCADE takes
their chats and tokens with them).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from orca import session
from orca.api.main import app
from orca.db.engine import get_sessionmaker
from orca.db.models import RefreshToken, User

client = TestClient(app)
PASSWORD = "correct horse battery"


@pytest.fixture
def make_user():
    created: list[str] = []

    def _make() -> dict:
        identifier = f"chat-test-{uuid.uuid4().hex[:12]}@example.test"
        r = client.post("/api/register", json={"identifier": identifier, "password": PASSWORD})
        assert r.status_code == 201, r.text
        tokens = r.json()
        user_id = client.get("/api/profile", headers=_auth(tokens)).json()["id"]
        created.append(user_id)
        return {"identifier": identifier, "tokens": tokens, "id": user_id}

    yield _make
    db = get_sessionmaker()()
    try:
        db.execute(delete(User).where(User.id.in_([uuid.UUID(u) for u in created])))
        db.commit()
    finally:
        db.close()


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _answer(text="GO: calm seas", **extra) -> dict:
    return {
        "query_id": str(uuid.uuid4()), "final_english_response": text, "detected_language": "en",
        "normalized_english_query": "is it safe near pamban", "matched_intent_rows": ["SAFETY_CHECK"],
        "risk_assessment": {"go_no_go": "GO", "reason": "calm"},
        "user_location": {"lat": 9.28, "lon": 79.2, "place_name": "pamban", "place_source": "gazetteer"},
        "audit_trace_log": [{"agent_name": "x", "outputs": {"big": "y" * 5000}}],
        "visualization_payload": {"map_layers": ["z" * 5000]},
        **extra,
    }


def _save(user, chat_id, question="Is it safe near Pamban?", answer=None, persona="fisherman", query_id=None):
    return client.put(
        f"/api/chats/{chat_id}/turns/{query_id or uuid.uuid4()}", headers=_auth(user["tokens"]),
        json={"asked_query": question, "answer": answer or _answer(), "persona": persona,
              "spans": [{"agent_name": "planning", "status": "ok"}]},
    )


# --- chat CRUD ------------------------------------------------------------------

def test_saving_turns_creates_a_chat_listed_newest_first_with_its_turns_in_order(make_user):
    user = make_user()
    older, newer = uuid.uuid4(), uuid.uuid4()
    assert _save(user, older, "first chat question").status_code == 204
    assert _save(user, newer, "second chat, turn one").status_code == 204
    assert _save(user, newer, "second chat, turn two").status_code == 204

    chats = client.get("/api/chats", headers=_auth(user["tokens"])).json()
    assert [c["id"] for c in chats] == [str(newer), str(older)]
    assert chats[0]["turn_count"] == 2
    assert chats[0]["first_question"] == "second chat, turn one"
    assert chats[0]["last_question"] == "second chat, turn two"
    assert chats[0]["title"] is None and chats[0]["persona"] == "fisherman"

    chat = client.get(f"/api/chats/{newer}", headers=_auth(user["tokens"])).json()
    assert [t["asked_query"] for t in chat["turns"]] == ["second chat, turn one", "second chat, turn two"]
    # confidence_tier rides on every span now (None when the saver sent none).
    assert chat["turns"][0]["spans"] == [{"agent_name": "planning", "status": "ok", "confidence_tier": None}]


def test_stored_answers_drop_the_trace_and_map_layers(make_user):
    user = make_user()
    chat_id = uuid.uuid4()
    _save(user, chat_id)
    answer = client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).json()["turns"][0]["answer"]
    assert "audit_trace_log" not in answer and "visualization_payload" not in answer
    assert answer["final_english_response"] == "GO: calm seas"


def test_resaving_a_turn_updates_it_in_place(make_user):
    user = make_user()
    chat_id, query_id = uuid.uuid4(), uuid.uuid4()
    _save(user, chat_id, query_id=query_id)
    client.put(
        f"/api/chats/{chat_id}/turns/{query_id}", headers=_auth(user["tokens"]),
        json={"asked_query": "Is it safe near Pamban?", "answer": _answer("Re-rendered for a navigator"),
              "rendered_as": "commercial_navigator"},
    )
    turns = client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).json()["turns"]
    assert len(turns) == 1
    assert turns[0]["answer"]["final_english_response"] == "Re-rendered for a navigator"
    assert turns[0]["rendered_as"] == "commercial_navigator"


def test_rename_and_pin_change_only_what_was_sent(make_user):
    user = make_user()
    a, b = uuid.uuid4(), uuid.uuid4()
    _save(user, a)
    _save(user, b)

    renamed = client.patch(f"/api/chats/{a}", headers=_auth(user["tokens"]), json={"title": "  Pamban trip  "}).json()
    assert renamed["title"] == "Pamban trip" and renamed["pinned"] is False

    pinned = client.patch(f"/api/chats/{a}", headers=_auth(user["tokens"]), json={"pinned": True}).json()
    assert pinned["title"] == "Pamban trip" and pinned["pinned"] is True
    # Pinned sorts first even though b is newer.
    assert client.get("/api/chats", headers=_auth(user["tokens"])).json()[0]["id"] == str(a)

    cleared = client.patch(f"/api/chats/{a}", headers=_auth(user["tokens"]), json={"title": "   "}).json()
    assert cleared["title"] is None and cleared["pinned"] is True


def test_search_matches_titles_and_questions_and_treats_wildcards_literally(make_user):
    user = make_user()
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _save(user, a, "Wave height off Kerala?")
    _save(user, b, "Nearest fishing zone")
    _save(user, c, "Tide at 100% moon")
    client.patch(f"/api/chats/{b}", headers=_auth(user["tokens"]), json={"title": "Kochi PFZ"})

    def search(q):
        return {x["id"] for x in client.get("/api/chats", params={"q": q}, headers=_auth(user["tokens"])).json()}

    assert search("kerala") == {str(a)}
    assert search("kochi") == {str(b)}
    assert search("100%") == {str(c)}
    assert search("%") == {str(c)}


def test_delete_removes_the_chat_and_its_turns(make_user):
    user = make_user()
    chat_id = uuid.uuid4()
    _save(user, chat_id)
    assert client.delete(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).status_code == 204
    assert client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).status_code == 404
    assert client.delete(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).status_code == 404


def test_another_users_chat_is_invisible_and_untouchable(make_user):
    owner, other = make_user(), make_user()
    chat_id = uuid.uuid4()
    _save(owner, chat_id, "owner's private question")

    assert client.get(f"/api/chats/{chat_id}", headers=_auth(other["tokens"])).status_code == 404
    assert client.patch(f"/api/chats/{chat_id}", headers=_auth(other["tokens"]), json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/chats/{chat_id}", headers=_auth(other["tokens"])).status_code == 404
    # Writing a turn into someone else's chat id must not take it over.
    assert _save(other, chat_id, "hijack").status_code == 404
    assert client.get("/api/chats", headers=_auth(other["tokens"])).json() == []
    owner_turns = client.get(f"/api/chats/{chat_id}", headers=_auth(owner["tokens"])).json()["turns"]
    assert [t["asked_query"] for t in owner_turns] == ["owner's private question"]


def test_a_chat_row_created_by_an_anonymous_query_is_adopted_on_first_save(make_user):
    """Chatbot plan C0.1. /query creates the `sessions` row for a chat before
    its first save, and when it could not tell who was asking the row has no
    owner. That first save used to 404 ("Not saved yet — retrying", forever),
    so no signed-in user's new chat was ever saved."""
    from orca.db.repositories import get_or_create_session

    user = make_user()
    chat_id = uuid.uuid4()
    db = get_sessionmaker()()
    try:
        get_or_create_session(db, session_id=chat_id, user_id=None, persona="fisherman", language="en")
        db.commit()
    finally:
        db.close()

    assert _save(user, chat_id, "first question in a new chat").status_code == 204
    chats = client.get("/api/chats", headers=_auth(user["tokens"])).json()
    assert [c["id"] for c in chats] == [str(chat_id)]
    # Adopted, not shared: the next account to try it is still refused.
    assert _save(make_user(), chat_id, "hijack").status_code == 404


def test_query_learns_the_caller_from_a_token_in_the_url(make_user):
    """An EventSource cannot send a header, so /ask sends the access token as
    `access_token` — without it every signed-in question reached /query as a
    guest (chatbot plan C0.1). A bad token is still just "anonymous"."""
    from orca.auth.rbac import get_optional_user

    user = make_user()
    db = get_sessionmaker()()
    try:
        found = get_optional_user(credentials=None, access_token=user["tokens"]["access_token"], db=db)
        assert found is not None and str(found.id) == user["id"]
        assert get_optional_user(credentials=None, access_token="not-a-token", db=db) is None
        assert get_optional_user(credentials=None, access_token=None, db=db) is None
    finally:
        db.close()


def test_chat_routes_require_a_signed_in_user():
    assert client.get("/api/chats").status_code == 401
    assert client.put(f"/api/chats/{uuid.uuid4()}/turns/{uuid.uuid4()}", json={}).status_code in (401, 422)


def test_oversized_or_non_answer_payloads_are_rejected(make_user):
    user = make_user()
    assert _save(user, uuid.uuid4(), answer={"final_english_response": "x" * 70_000}).status_code == 422
    assert _save(user, uuid.uuid4(), answer={"not": "an answer"}).status_code == 422


# --- import -----------------------------------------------------------------------

def _import_chat(chat_id, *, title=None, pinned=False, questions=("q1", "q2"), start=None):
    start = start or datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    return {
        "id": str(chat_id), "title": title, "pinned": pinned, "persona": "researcher",
        "turns": [
            {"query_id": str(uuid.uuid4()), "asked_query": q, "answer": _answer(f"answer to {q}"),
             "created_at": (start + timedelta(minutes=i)).isoformat()}
            for i, q in enumerate(questions)
        ],
    }


def test_import_brings_guest_chats_in_with_their_own_titles_and_timeline(make_user):
    user = make_user()
    chat_id = uuid.uuid4()
    r = client.post("/api/chats/import", headers=_auth(user["tokens"]),
                    json={"chats": [_import_chat(chat_id, title="Guest chat", pinned=True)]})
    assert r.json() == {"imported": 1}
    chat = client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).json()
    assert chat["title"] == "Guest chat" and chat["pinned"] is True and chat["persona"] == "researcher"
    assert [t["asked_query"] for t in chat["turns"]] == ["q1", "q2"]
    assert chat["last_seen_at"].startswith("2026-09-01T08:01")


def test_importing_twice_does_not_duplicate_and_merging_never_rewinds_a_chat(make_user):
    user = make_user()
    chat_id = uuid.uuid4()
    payload = {"chats": [_import_chat(chat_id)]}
    client.post("/api/chats/import", headers=_auth(user["tokens"]), json=payload)
    _save(user, chat_id, "asked after import")  # newer activity, server-side
    client.patch(f"/api/chats/{chat_id}", headers=_auth(user["tokens"]), json={"title": "Kept"})

    stale = _import_chat(chat_id, title="Older browser title")
    stale["turns"] = payload["chats"][0]["turns"]
    client.post("/api/chats/import", headers=_auth(user["tokens"]), json={"chats": [stale]})

    chat = client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).json()
    assert [t["asked_query"] for t in chat["turns"]] == ["q1", "q2", "asked after import"]
    assert chat["title"] == "Kept"
    assert not chat["last_seen_at"].startswith("2026-09-01")


def test_import_skips_a_chat_id_that_belongs_to_someone_else(make_user):
    owner, importer = make_user(), make_user()
    chat_id = uuid.uuid4()
    _save(owner, chat_id, "owner's")
    r = client.post("/api/chats/import", headers=_auth(importer["tokens"]), json={"chats": [_import_chat(chat_id)]})
    assert r.json() == {"imported": 0}
    assert [t["asked_query"] for t in client.get(f"/api/chats/{chat_id}", headers=_auth(owner["tokens"])).json()["turns"]] == ["owner's"]


# --- context restore -----------------------------------------------------------------

def test_reopening_a_chat_restores_its_context_window(monkeypatch):
    monkeypatch.setattr(session, "redis_client", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    chat_id = str(uuid.uuid4())
    turns = [{"asked_query": f"q{i}", "answer": _answer(f"a{i}")} for i in range(session.MAX_TURNS)]
    assert client.put(f"/api/session/{chat_id}/context", json={"turns": turns}).status_code == 204
    window = session.get_turns(chat_id)
    assert [t["query"] for t in window] == [f"q{i}" for i in range(session.MAX_TURNS)]
    assert window[0]["intent_rows"] == ["SAFETY_CHECK"] and window[0]["answer"] == "a0"
    too_many = turns + [turns[0]]
    assert client.put(f"/api/session/{chat_id}/context", json={"turns": too_many}).status_code == 422


# --- auth: refresh rotation, reuse, logout, identifiers --------------------------------

def test_refresh_rotates_and_the_old_refresh_token_stops_working(make_user):
    user = make_user()
    old = user["tokens"]
    r = client.post("/api/refresh", json={"refresh_token": old["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != old["refresh_token"]
    assert client.get("/api/profile", headers=_auth(new)).status_code == 200
    assert client.post("/api/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    # Inside the race grace window the new token survives an old one's reuse.
    assert client.post("/api/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 200


def test_reusing_a_long_revoked_refresh_token_revokes_every_session(make_user):
    user = make_user()
    stolen = user["tokens"]["refresh_token"]
    rotated = client.post("/api/refresh", json={"refresh_token": stolen}).json()
    db = get_sessionmaker()()
    try:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == uuid.UUID(user["id"]), RefreshToken.revoked_at.is_not(None))
            .values(revoked_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        )
        db.commit()
    finally:
        db.close()
    assert client.post("/api/refresh", json={"refresh_token": stolen}).status_code == 401
    assert client.post("/api/refresh", json={"refresh_token": rotated["refresh_token"]}).status_code == 401


def test_logout_revokes_the_refresh_token_and_never_errors(make_user):
    user = make_user()
    assert client.post("/api/logout", json={"refresh_token": user["tokens"]["refresh_token"]}).status_code == 204
    assert client.post("/api/refresh", json={"refresh_token": user["tokens"]["refresh_token"]}).status_code == 401
    assert client.post("/api/logout", json={"refresh_token": "not-a-token"}).status_code == 204


def test_access_tokens_are_not_refresh_tokens(make_user):
    user = make_user()
    assert client.post("/api/refresh", json={"refresh_token": user["tokens"]["access_token"]}).status_code == 401


def test_identifiers_are_normalized_so_one_person_is_one_account(make_user):
    user = make_user()
    shouted = user["identifier"].upper()
    assert client.post("/api/login", json={"identifier": f"  {shouted} ", "password": PASSWORD}).status_code == 200
    assert client.post("/api/register", json={"identifier": shouted, "password": PASSWORD}).status_code == 409
    assert client.post("/api/register", json={"identifier": "not-a-phone", "password": PASSWORD}).status_code == 422
    profile = client.get("/api/profile", headers=_auth(user["tokens"])).json()
    assert profile["identifier"] == user["identifier"]


def test_a_saved_span_keeps_its_agent_confidence(make_user):
    """The activity strip's whole point is showing how sure each agent was.
    `Span` declared only agent_name and status, so Pydantic dropped
    `confidence_tier` on every save — a signed-in user's chats could never
    keep it, and a reopened chat drew plain ticks with no confidence at all."""
    user = make_user()
    chat_id = str(uuid.uuid4())
    client.put(
        f"/api/chats/{chat_id}/turns/{uuid.uuid4()}", headers=_auth(user["tokens"]),
        json={
            "asked_query": "Is it safe near Pamban?", "answer": _answer(), "persona": "fisherman",
            "spans": [
                {"agent_name": "planning", "status": "ok", "confidence_tier": "HIGH"},
                {"agent_name": "weather_intelligence", "status": "ok", "confidence_tier": "MEDIUM"},
                {"agent_name": "ocean_analytics", "status": "degraded", "confidence_tier": "LOW_DATA"},
            ],
        },
    )
    turn = client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).json()["turns"][0]
    assert [s["confidence_tier"] for s in turn["spans"]] == ["HIGH", "MEDIUM", "LOW_DATA"]


def test_a_span_with_no_confidence_still_saves(make_user):
    """A failed agent has no tier, and turns saved before the field existed
    have none either. Those must store, not 422."""
    user = make_user()
    chat_id = str(uuid.uuid4())
    res = client.put(
        f"/api/chats/{chat_id}/turns/{uuid.uuid4()}", headers=_auth(user["tokens"]),
        json={"asked_query": "Is it safe near Pamban?", "answer": _answer(), "persona": "fisherman",
              "spans": [{"agent_name": "planning", "status": "failed"}]},
    )
    assert res.status_code == 204
    turn = client.get(f"/api/chats/{chat_id}", headers=_auth(user["tokens"])).json()["turns"][0]
    assert turn["spans"][0]["confidence_tier"] is None


def test_an_invented_confidence_tier_is_rejected(make_user):
    """The tier is a closed vocabulary shared with the confidence scorer; a
    typo must fail loudly rather than reach the strip as an unrenderable
    colour."""
    user = make_user()
    res = client.put(
        f"/api/chats/{uuid.uuid4()}/turns/{uuid.uuid4()}", headers=_auth(make_user()["tokens"]),
        json={"asked_query": "q", "answer": _answer(), "persona": "fisherman",
              "spans": [{"agent_name": "planning", "status": "ok", "confidence_tier": "VERY_HIGH"}]},
    )
    assert res.status_code == 422
    assert user is not None
