"""Registration/login business logic — plain functions over a Session, no
FastAPI import here, so it's testable (and was tested) without spinning up
the app. orca/api/auth_routes.py is the thin HTTP wrapper around this.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orca.auth.security import (
    TokenError,
    TokenPair,
    decode_token,
    hash_password,
    issue_token_pair,
    verify_password,
)
from orca.db.models import RefreshToken, User
from orca.db.repositories import (
    create_user,
    get_user_by_id,
    get_user_by_identifier,
    persist_security_event,
)

# Two tabs refreshing at the same moment both present the same token; the
# loser finds it revoked seconds earlier. That is a race, not theft, so inside
# this window only that one request is refused — the frontend then picks up
# the winner's new token (frontend/app/lib/auth.ts). Past it, reuse revokes
# every live token for the account.
_REUSE_GRACE = timedelta(seconds=30)


class AuthError(Exception):
    """Raised for any auth failure the route layer should turn into 4xx.
    One exception type, not several — the route boundary decides the status
    code from `.reason`, callers don't need to catch subclasses."""

    def __init__(self, reason: str, message: str):
        self.reason = reason  # "duplicate" | "invalid_credentials" | "inactive" | "invalid_token"
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
    return user, _issue_recorded(db, user)


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
    return user, _issue_recorded(db, user)


def _issue_recorded(db: Session, user: User) -> TokenPair:
    """Every token pair this service hands out has its refresh token recorded
    (004_refresh_tokens.sql) — an unrecorded refresh token can't be refreshed
    or revoked, so it would be dead weight at best."""
    tokens = issue_token_pair(user.id, user.role)  # type: ignore[arg-type]
    claims = decode_token(tokens.refresh_token, expected_type="refresh")
    db.add(RefreshToken(
        jti=uuid.UUID(claims["jti"]), user_id=user.id,
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
    ))
    db.commit()
    return tokens


def refresh(db: Session, *, refresh_token: str) -> tuple[User, TokenPair]:
    """Rotate: revoke the presented refresh token, issue a fresh pair."""
    invalid = AuthError("invalid_token", "invalid or expired refresh token")
    try:
        claims = decode_token(refresh_token, expected_type="refresh")
    except TokenError:
        raise invalid from None

    # FOR UPDATE: two concurrent refreshes with one token serialize here, so
    # exactly one rotates and the other sees it already revoked.
    row = db.get(RefreshToken, uuid.UUID(claims["jti"]), with_for_update=True)
    if row is None or str(row.user_id) != claims["sub"]:
        # Includes every token issued before refresh tokens were recorded —
        # those sessions simply sign in again once.
        db.rollback()
        raise invalid

    if row.revoked_at is not None:
        if datetime.now(timezone.utc) - row.revoked_at > _REUSE_GRACE:
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=func.now())
            )
            db.commit()
            persist_security_event(
                db, query_id=uuid.uuid4(), event="refresh_token_reuse", status="failed",
                outputs={"user_id": str(row.user_id)},
            )
        else:
            db.rollback()
        raise invalid

    user = get_user_by_id(db, row.user_id)
    row.revoked_at = datetime.now(timezone.utc)
    if user is None or user.status != "active":
        db.commit()
        raise AuthError("inactive", "this account is not active")
    return user, _issue_recorded(db, user)  # commits the revocation and the new token together


def logout(db: Session, *, refresh_token: str) -> None:
    """Revoke one refresh token. Silent on anything invalid: signing out must
    always succeed from the caller's point of view, and must not tell a
    stranger whether a token they hold is live."""
    try:
        claims = decode_token(refresh_token, expected_type="refresh")
    except TokenError:
        return
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.jti == uuid.UUID(claims["jti"]),
            RefreshToken.user_id == uuid.UUID(claims["sub"]),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    db.commit()
