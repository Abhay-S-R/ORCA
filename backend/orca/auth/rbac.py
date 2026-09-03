"""FastAPI dependencies — RBAC at the route boundary, not a permission
matrix (plan §5.4 Day 9: "as a FastAPI dependency at the route boundary").
`require_role` is the only gate; there is no second place a route can be
authorized, which is what makes the CI persona-leak-style guard reasoning
possible here too — one call site to audit, not many.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from orca.auth.security import Role, TokenError, decode_token
from orca.db.engine import get_db
from orca.db.models import User
from orca.db.repositories import get_user_by_id

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc

    user = get_user_by_id(db, uuid.UUID(payload["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


def require_role(*roles: Role):
    """Dependency factory: `Depends(require_role("authority", "admin"))`.
    An empty `roles` means "any authenticated user" — used for routes that
    only need identity, not a specific role."""
    allowed: tuple[Role, ...] = roles

    def _dependency(user: User = Depends(get_current_user)) -> User:
        if allowed and user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"role {user.role!r} cannot access this route")
        return user

    return _dependency
