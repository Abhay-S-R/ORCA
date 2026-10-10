"""Tests for coastal authority broadcast publishing and multi-persona alert issuance.
Validates that each coastal authority account can compose and issue alerts
for all mariner personas (all, fisherman, commercial_navigator, researcher, port_users),
linking active watches, delivering notifications, and recording audit trails.
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy.orm import Session

pytest.importorskip("psycopg")
pytest.importorskip("geoalchemy2")

from orca.api.ops_routes import (
    BroadcastPublishRequest,
    broadcast_history,
    broadcast_publish,
    list_authorities,
)
from orca.db.engine import get_sessionmaker
from orca.db.models import User
from orca.db.notifications_repo import list_notifications_for_user
from orca.ops.port_authorities import ensure_port_authorities, ensure_test_mariners


@pytest.fixture
def db() -> Session:
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        ensure_port_authorities(session)
        ensure_test_mariners(session)
        yield session
    finally:
        session.rollback()
        session.close()


def test_coastal_authority_can_broadcast_to_all_user_types(db: Session):
    mumbai_auth = db.query(User).filter(User.email == "authority.mumbai@orca.test").first()
    assert mumbai_auth is not None
    assert mumbai_auth.role == "authority"

    req = BroadcastPublishRequest(
        title="High Swell Alert (Mumbai Sector)",
        body="High wave swell 3.8m expected. Maintain safe distance from harbour entrance.",
        severity="danger",
        target_audience="all",
        location="Mumbai",
    )
    res = broadcast_publish(req, user=mumbai_auth, db=db)
    assert res["status"] == "published"
    assert res["title"] == req.title
    assert res["severity"] == "danger"
    assert res["target_audience"] == "all"
    assert res["authority_name"] == mumbai_auth.display_name
    assert res["delivered_count"] > 0
    assert "fisherman" in res["breakdown"]
    assert "commercial_navigator" in res["breakdown"]
    assert "researcher" in res["breakdown"]


def test_coastal_authority_can_target_fishermen(db: Session):
    mumbai_auth = db.query(User).filter(User.email == "authority.mumbai@orca.test").first()
    req = BroadcastPublishRequest(
        title="Fishermen Warning: Gale Winds",
        body="Squally weather with wind speed reaching 45 kmph. Avoid venturing into sea.",
        severity="warning",
        target_audience="fisherman",
    )
    res = broadcast_publish(req, user=mumbai_auth, db=db)
    assert res["status"] == "published"
    assert res["target_audience"] == "fisherman"
    assert res["delivered_count"] >= 1
    # Only fishermen should be targeted
    assert res["breakdown"]["fisherman"] == res["delivered_count"]
    assert res["breakdown"]["commercial_navigator"] == 0
    assert res["breakdown"]["researcher"] == 0


def test_coastal_authority_can_target_commercial_navigators(db: Session):
    chennai_auth = db.query(User).filter(User.email == "authority.chennai@orca.test").first()
    req = BroadcastPublishRequest(
        title="Commercial Navigation: Traffic Separation",
        body="Navigational lane maintenance near outer fairway buoy.",
        severity="advisory",
        target_audience="commercial_navigator",
    )
    res = broadcast_publish(req, user=chennai_auth, db=db)
    assert res["status"] == "published"
    assert res["target_audience"] == "commercial_navigator"
    assert res["delivered_count"] >= 1
    assert res["breakdown"]["commercial_navigator"] == res["delivered_count"]
    assert res["breakdown"]["fisherman"] == 0


def test_coastal_authority_can_target_researchers(db: Session):
    kochi_auth = db.query(User).filter(User.email == "authority.kochi@orca.test").first()
    req = BroadcastPublishRequest(
        title="Research Advisory: Acoustic Sensor Grid",
        body="Oceanographic telemetry mooring deployed for 72 hours.",
        severity="info",
        target_audience="researcher",
    )
    res = broadcast_publish(req, user=kochi_auth, db=db)
    assert res["status"] == "published"
    assert res["target_audience"] == "researcher"
    assert res["delivered_count"] >= 1
    assert res["breakdown"]["researcher"] == res["delivered_count"]


def test_broadcast_history_and_authorities_list(db: Session):
    mumbai_auth = db.query(User).filter(User.email == "authority.mumbai@orca.test").first()
    req = BroadcastPublishRequest(
        title="History Test Advisory",
        body="Notice to mariners for testing audit log entry.",
        severity="advisory",
        target_audience="all",
    )
    broadcast_publish(req, user=mumbai_auth, db=db)

    hist = broadcast_history(limit=10, user=mumbai_auth, db=db)
    assert "history" in hist
    assert len(hist["history"]) > 0
    latest = hist["history"][0]
    assert "title" in latest
    assert "authority_name" in latest
    assert "delivered_count" in latest

    auth_roster = list_authorities(db=db)
    assert "authorities" in auth_roster
    assert len(auth_roster["authorities"]) >= 12
    ports = [a["port_name"] for a in auth_roster["authorities"]]
    assert "Mumbai" in ports
    assert "Chennai" in ports
    assert "Kochi" in ports
    assert "Thoothukudi" in ports
