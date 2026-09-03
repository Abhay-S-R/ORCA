"""orca/auth + orca/db — plan §5.4, D1 Day 9-10. Runs against the real local
Postgres (docker-compose's `postgres` service, DATABASE_URL in .env) rather
than a mock — the same reasoning orca/tests/e2e/test_graph.py applies to
geospatial: a schema/ORM mismatch is exactly the kind of bug a mock would
hide. `service.register`/`service.login` commit internally (they must, to
persist the security-event audit row on the same call), so those tests use
a fresh random identifier per run instead of a rollback; the repository-only
tests below them share a `db` fixture that rolls back what it can.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from orca.auth import service
from orca.auth.security import (
    hash_password,
    issue_token_pair,
    verify_password,
)
from orca.db.engine import get_sessionmaker
from orca.db.repositories import (
    create_user,
    create_vessel,
    get_vessel_for_owner,
    list_vessels_for_owner,
    set_home_port,
    user_home_port,
    vessel_last_position,
)


@pytest.fixture
def db() -> Session:
    """One connection, one transaction, rolled back at teardown — nothing
    this test file writes is ever actually committed to the shared dev DB."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _unique_identifier(prefix: str = "test") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.test"


# --------------------------------------------------------------------------
# security.py — no DB needed
# --------------------------------------------------------------------------

def test_hash_password_is_never_the_plaintext():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h) is True


def test_verify_password_rejects_wrong_password():
    h = hash_password("correct horse battery staple")
    assert verify_password("wrong password", h) is False


def test_issue_token_pair_round_trips_through_decode(monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    from orca.auth import security

    user_id = uuid.uuid4()
    tokens = issue_token_pair(user_id, "user")
    access_payload = security.decode_token(tokens.access_token, expected_type="access")
    assert access_payload["sub"] == str(user_id)
    assert access_payload["role"] == "user"
    refresh_payload = security.decode_token(tokens.refresh_token, expected_type="refresh")
    assert refresh_payload["sub"] == str(user_id)


def test_decode_token_rejects_the_wrong_type(monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    from orca.auth import security

    tokens = issue_token_pair(uuid.uuid4(), "user")
    with pytest.raises(security.TokenError):
        security.decode_token(tokens.refresh_token, expected_type="access")


# --------------------------------------------------------------------------
# service.py + db/repositories.py — real Postgres
# --------------------------------------------------------------------------

def test_register_creates_a_user_and_issues_tokens(db, monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    identifier = _unique_identifier()
    user, tokens = service.register(db, identifier=identifier, password="hunter2hunter", display_name="Test User", language="en")
    assert user.email == identifier
    assert user.role == "user"
    assert tokens.access_token
    assert tokens.refresh_token


def test_register_rejects_a_duplicate_identifier(db, monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    identifier = _unique_identifier()
    service.register(db, identifier=identifier, password="hunter2hunter", display_name=None, language="en")
    with pytest.raises(service.AuthError) as exc_info:
        service.register(db, identifier=identifier, password="different1", display_name=None, language="en")
    assert exc_info.value.reason == "duplicate"


def test_login_succeeds_with_correct_credentials(db, monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    identifier = _unique_identifier()
    service.register(db, identifier=identifier, password="hunter2hunter", display_name=None, language="en")
    user, tokens = service.login(db, identifier=identifier, password="hunter2hunter")
    assert user.email == identifier
    assert tokens.access_token


def test_login_rejects_wrong_password(db, monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    identifier = _unique_identifier()
    service.register(db, identifier=identifier, password="hunter2hunter", display_name=None, language="en")
    with pytest.raises(service.AuthError) as exc_info:
        service.login(db, identifier=identifier, password="wrong")
    assert exc_info.value.reason == "invalid_credentials"


def test_login_rejects_unknown_identifier(db, monkeypatch):
    monkeypatch.setenv("ORCA_JWT_SECRET", "test-secret-not-for-prod-32bytesmin")
    with pytest.raises(service.AuthError) as exc_info:
        service.login(db, identifier=_unique_identifier("nobody"), password="whatever1")
    assert exc_info.value.reason == "invalid_credentials"


def test_home_port_round_trips_lat_lon(db):
    user = create_user(db, identifier=_unique_identifier(), password_hash="x")
    set_home_port(db, user, lat=8.822495, lon=78.119064, name="Thoothukudi")
    port = user_home_port(user)
    assert port is not None
    assert port["lat"] == pytest.approx(8.822495)
    assert port["lon"] == pytest.approx(78.119064)


# --------------------------------------------------------------------------
# vessel ownership — the acceptance-test-B guarantee at the repository layer
# --------------------------------------------------------------------------

def test_vessel_is_scoped_to_its_owner(db):
    owner_a = create_user(db, identifier=_unique_identifier("a"), password_hash="x")
    owner_b = create_user(db, identifier=_unique_identifier("b"), password_hash="x")
    db.flush()
    vessel = create_vessel(db, owner_user_id=owner_a.id, vessel_class="fibreglass", name="Boat A")
    db.flush()

    assert get_vessel_for_owner(db, vessel.id, owner_a.id) is not None
    # owner_b requesting owner_a's vessel by id gets nothing back — the
    # cross-read cannot be satisfied by the query itself.
    assert get_vessel_for_owner(db, vessel.id, owner_b.id) is None
    assert [v.id for v in list_vessels_for_owner(db, owner_a.id)] == [vessel.id]
    assert list_vessels_for_owner(db, owner_b.id) == []


def test_vessel_last_position_none_when_never_set(db):
    owner = create_user(db, identifier=_unique_identifier(), password_hash="x")
    db.flush()
    vessel = create_vessel(db, owner_user_id=owner.id, vessel_class="trawler")
    assert vessel_last_position(vessel) is None
