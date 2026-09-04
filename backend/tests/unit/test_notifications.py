"""Watches / notifications / feedback / Sentinel E2E — against the real local
Postgres, same rationale and `db` fixture style as tests/unit/test_auth.py
(a schema/ORM mismatch is exactly what a mock would hide). Skips itself
cleanly when DATABASE_URL points at nothing reachable.

Covers acceptance test C (plan §10): a threshold crossing fires exactly one
notification to a registered subscriber, a second identical poll fires none,
the payload is stored verbatim and labelled, and audit_trace_log carries the
broadcast with status 'degraded' for a SIMULATED channel.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytest.importorskip("psycopg")
pytest.importorskip("geoalchemy2")

from orca.agents import sentinel
from orca.db.engine import get_sessionmaker
from orca.db.notifications_repo import (
    create_feedback,
    create_notification,
    create_watch,
    feedback_for_query,
    get_watch_for_user,
    list_notifications_for_user,
    mark_notification_read,
    unread_count,
)
from orca.db.repositories import create_user
from orca.sentinel_runtime import run_poll_cycle


@pytest.fixture
def db() -> Session:
    try:
        session = get_sessionmaker()()
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("local Postgres not reachable (docker compose up postgres)")
    trans = session.begin_nested() if session.in_transaction() else None
    try:
        yield session
    finally:
        session.rollback()
        # A test that calls db.commit() (needed so run_poll_cycle sees
        # committed rows in the same connection) ends the SAVEPOINT above as
        # part of that commit — trans.rollback() on the now-closed nested
        # transaction would raise and skip session.close() below, leaking
        # the connection (and, worse, its pg_try_advisory_lock) to later tests.
        if trans is not None and trans.is_active:
            trans.rollback()
        session.close()


def _user(db: Session) -> uuid.UUID:
    u = create_user(db, identifier=f"+9198{uuid.uuid4().int % 10**8:08d}", password_hash="x", language="en")
    db.flush()
    return u.id


def _calm(**kw):
    base = {
        "go_no_go": "GO", "reason": "calm", "wave_height_m": 1.0, "wind_speed_ms": 3.0,
        "lightning_active": False, "cyclone_alert": None, "active_hazard_types": [], "confidence": "HIGH",
    }
    base.update(kw)
    return sentinel.WatchSnapshot(**base)


# --- watch CRUD + ownership -------------------------------------------------

def test_watch_is_owned_and_not_cross_readable(db: Session):
    a, b = _user(db), _user(db)
    w = create_watch(db, user_id=a, watch_type="wave_height", lat=8.8, lon=78.14, thresholds={"wave_height_m": 2.5})
    db.flush()
    assert get_watch_for_user(db, w.id, a) is not None
    # b cannot see a's watch — the query itself cannot return it
    assert get_watch_for_user(db, w.id, b) is None


# --- notification feed + read state ----------------------------------------

def test_notification_feed_and_read_state(db: Session):
    u = _user(db)
    n = create_notification(db, user_id=u, title="High waves", body="3m", severity="warning")
    db.flush()
    assert unread_count(db, u) == 1
    assert mark_notification_read(db, n.id, u) is True
    assert unread_count(db, u) == 0
    # idempotent + no leak: marking someone else's / already-read returns False
    assert mark_notification_read(db, n.id, u) is False
    assert mark_notification_read(db, n.id, _user(db)) is False


# --- feedback joins by query_id ------------------------------------------

def test_feedback_joins_by_query_id(db: Session):
    u = _user(db)
    qid = uuid.uuid4()
    create_feedback(db, query_id=qid, kind="not_accurate", user_id=u, comment="waves looked fine")
    db.flush()
    rows = feedback_for_query(db, qid)
    assert len(rows) == 1 and rows[0].kind == "not_accurate"


# --- Sentinel crossing E2E (acceptance test C) ---------------------------

def test_crossing_fires_once_and_a_second_identical_poll_is_silent(db: Session, monkeypatch):
    # run_poll_cycle scans every enabled watch system-wide (correct production
    # behaviour — Sentinel has no notion of "this test's watches"), but this
    # test calls db.commit() below so run_poll_cycle sees its row in the same
    # connection — which also means the row survives past this test's own
    # rollback. Without this, a prior run of this exact test leaves a watch
    # behind that a later run's identical cheap_check patch also crosses,
    # so list_enabled_watches finds N leftover watches instead of 1.
    db.execute(text("DELETE FROM sentinel_subscriptions"))
    u = _user(db)
    create_watch(
        db, user_id=u, watch_type="wave_height", lat=8.8, lon=78.14,
        thresholds={"wave_height_m": 2.5}, channels=["sms"],  # sms -> SIMULATED
    )
    db.commit()

    # forecast has crossed 2.5 m
    monkeypatch.setattr(sentinel, "cheap_check", lambda *a, **k: _calm(go_no_go="CAUTION", wave_height_m=3.0, reason="rough"))

    fired = [d for d in run_poll_cycle(db) if d.fired]
    assert len(fired) == 1

    notes = list_notifications_for_user(db, u)
    assert len(notes) == 1
    note = notes[0]
    assert note.status == "simulated"                       # sms has no transport
    assert note.rendered_payload["alert"]["sagar_vani_sms"]  # exact payload stored verbatim
    assert note.query_id is not None

    # audit row carries the broadcast, status 'degraded' for the simulated channel
    audit = db.execute(
        text("SELECT status FROM audit_trace_log WHERE agent_name='sentinel' AND query_id=:q"),
        {"q": note.query_id},
    ).scalar_one()
    assert audit == "degraded"

    # second identical poll: no new notification (no-spam functional requirement)
    monkeypatch.setattr(sentinel, "cheap_check", lambda *a, **k: _calm(go_no_go="CAUTION", wave_height_m=3.1, reason="rough"))
    run_poll_cycle(db)
    assert len(list_notifications_for_user(db, u)) == 1


def test_unchanged_calm_conditions_produce_zero_notifications(db: Session, monkeypatch):
    u = _user(db)
    create_watch(db, user_id=u, watch_type="weather", lat=8.8, lon=78.14)
    db.commit()
    monkeypatch.setattr(sentinel, "cheap_check", lambda *a, **k: _calm())
    run_poll_cycle(db)
    run_poll_cycle(db)
    assert list_notifications_for_user(db, u) == []


# --- /ops aggregation privacy -------------------------------------------

def test_sector_threat_matrix_never_returns_coordinates_or_vessel_ids(db: Session):
    from orca.ops.aggregation import sector_threat_matrix

    matrix = sector_threat_matrix(db)
    assert len(matrix) == 14
    for row in matrix:
        assert set(row) == {
            "sector_id", "sector_name", "pfz_status", "pfz_message",
            "is_data_gap", "vessel_count", "alert_severity",
        }
        assert isinstance(row["vessel_count"], int)  # a count, never a position
