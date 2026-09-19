"""P4.16 — the authority distress queue, against the real local Postgres (the
same reasoning as test_auth.py: a schema mismatch is what a mock would hide).
The queue functions commit, so every row this file writes is deleted at the
end; the security-audit rows they add are kept, as for the auth tests."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from orca.db.engine import get_sessionmaker
from orca.db.repositories import create_user
from orca.ops import distress_queue as dq


@pytest.fixture
def db():
    session = get_sessionmaker()()
    made: dict[str, list] = {"queries": [], "users": []}
    yield session, made
    session.rollback()
    for qid in made["queries"]:
        session.execute(text("DELETE FROM distress_events WHERE query_id = :q"), {"q": qid})
    for uid in made["users"]:
        session.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    session.commit()
    session.close()


def _state(qid: str, lat: float | None, lon: float | None) -> dict:
    return {
        "query_id": qid,
        "user_location": None if lat is None else {"lat": lat, "lon": lon, "place_name": "Rameswaram"},
        "audit_trace_log": [{"agent_name": "distress", "outputs": {"detection": {
            "is_distress": True, "distress_type": "text_pattern", "matched_language": "ta", "matched_phrase": "உதவி"}}}],
    }


def _authority(session, made) -> uuid.UUID:
    user = create_user(session, identifier=f"auth-{uuid.uuid4().hex[:10]}@example.test", password_hash="x")
    session.commit()
    made["users"].append(user.id)
    return user.id


def _event(session, qid):
    return next(e for e in dq.list_events(session, reader_id=uuid.uuid4(), hours=1) if e["query_id"] == qid)


def test_recorded_once_with_position_and_phrase(db):
    session, made = db
    qid = str(uuid.uuid4())
    made["queries"].append(qid)
    dq.record_event(session, _state(qid, 9.28, 79.31), {"primary": {"name": "MRCC Chennai"}})
    dq.record_event(session, _state(qid, 9.28, 79.31), None)  # the same query never queues twice

    e = _event(session, qid)
    assert e["state"] == "open" and e["matched_phrase"] == "உதவி" and e["matched_language"] == "ta"
    assert (round(e["lat"], 2), round(e["lon"], 2)) == (9.28, 79.31)
    assert e["mrcc_contact"] == {"primary": {"name": "MRCC Chennai"}}
    n = session.execute(text("SELECT count(*) FROM distress_events WHERE query_id = :q"), {"q": qid}).scalar()
    assert n == 1


def test_no_position_is_recorded_as_none_not_invented(db):
    session, made = db
    qid = str(uuid.uuid4())
    made["queries"].append(qid)
    dq.record_event(session, _state(qid, None, None), None)
    e = _event(session, qid)
    assert e["lat"] is None and e["lon"] is None


def test_acknowledge_then_close_and_the_position_is_withheld_once_closed(db):
    session, made = db
    actor = _authority(session, made)
    qid = str(uuid.uuid4())
    made["queries"].append(qid)
    dq.record_event(session, _state(qid, 9.28, 79.31), None)
    eid = uuid.UUID(_event(session, qid)["id"])

    assert dq.set_state(session, eid, "acknowledge", actor) == {"id": str(eid), "state": "acknowledged"}
    assert dq.set_state(session, eid, "acknowledge", actor) is None  # can't go back to it
    assert _event(session, qid)["lat"] is not None  # still an active incident

    assert dq.set_state(session, eid, "close", actor)["state"] == "closed"
    closed = _event(session, qid)
    assert closed["lat"] is None and closed["closed_at"] is not None  # time-boxed to the incident
    assert dq.set_state(session, eid, "close", actor) is None


def test_every_position_read_is_audited(db):
    session, made = db
    qid = str(uuid.uuid4())
    made["queries"].append(qid)
    dq.record_event(session, _state(qid, 9.28, 79.31), None)
    reader = uuid.uuid4()
    dq.list_events(session, reader_id=reader, hours=1)
    row = session.execute(text(
        "SELECT outputs FROM audit_trace_log WHERE agent_name = 'security' AND event = 'distress_position_read' "
        "AND outputs->>'authority_user_id' = :r"), {"r": str(reader)}).scalar()
    assert row is not None and _event(session, qid)["id"] in row["distress_event_ids"]


def test_a_regional_default_is_never_queued_or_handed_off_as_the_callers_position(db):
    from orca.agents.distress import _position_of, surface_mrcc_contact

    default = {"lat": 8.8, "lon": 78.14, "place_name": None, "place_source": "regional_default"}
    assert _position_of(default) == (None, None)
    assert surface_mrcc_contact(default).get("note") == "no position on the query"
    assert _position_of({**default, "place_source": "explicit"}) == (8.8, 78.14)

    session, made = db
    qid = str(uuid.uuid4())
    made["queries"].append(qid)
    state = _state(qid, 8.8, 78.14)
    state["user_location"]["place_source"] = "regional_default"
    dq.record_event(session, state, None)
    e = _event(session, qid)
    assert e["lat"] is None and e["place_name"] is None
