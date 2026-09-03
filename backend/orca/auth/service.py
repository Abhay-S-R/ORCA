"""Registration/login business logic — plain functions over a Session, no
FastAPI import here, so it's testable (and was tested) without spinning up
the app. orca/api/auth_routes.py is the thin HTTP wrapper around this.
"""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orca.auth.security import TokenPair, hash_password, issue_token_pair, verify_password
from orca.db.models import User
from orca.db.repositories import create_user, get_user_by_identifier, persist_security_event


class AuthError(Exception):
    """Raised for any auth failure the route layer should turn into 4xx.
    One exception type, not several — the route boundary decides the status
    code from `.reason`, callers don't need to catch subclasses."""

    def __init__(self, reason: str, message: str):
        self.reason = reason  # "duplicate" | "invalid_credentials" | "inactive"
        super().__init__(message)


def register(db: Session, *, identifier: str, password: str, display_name: str | None, language: str) -> tuple[User, TokenPair]:
    if get_user_by_identifier(db, identifier) is not None:
        persist_security_event(
            db, query_id=uuid.uuid4(), event="registration", status="failed",
            outputs={"reason": "duplicate_identifier"},
        )
        raise AuthError("duplicate", "an account with this phone/email already exists")

    try:
        user = create_user(
            db, identifier=identifier, password_hash=hash_password(password),
            display_name=display_name, language=language,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AuthError("duplicate", "an account with this phone/email already exists") from None

    persist_security_event(db, query_id=uuid.uuid4(), event="registration", status="ok", outputs={"user_id": str(user.id)})
    return user, issue_token_pair(user.id, user.role)  # type: ignore[arg-type]


def login(db: Session, *, identifier: str, password: str) -> tuple[User, TokenPair]:
    user = get_user_by_identifier(db, identifier)
    if user is None or not verify_password(password, user.password_hash):
        persist_security_event(
            db, query_id=uuid.uuid4(), event="failed_login", status="failed",
            outputs={"identifier": identifier},
        )
        raise AuthError("invalid_credentials", "incorrect phone/email or password")

    if user.status != "active":
        persist_security_event(
            db, query_id=uuid.uuid4(), event="failed_login", status="failed",
            outputs={"user_id": str(user.id), "reason": "inactive"},
        )
        raise AuthError("inactive", "this account is not active")

    persist_security_event(db, query_id=uuid.uuid4(), event="login", status="ok", outputs={"user_id": str(user.id)})
    return user, issue_token_pair(user.id, user.role)  # type: ignore[arg-type]
