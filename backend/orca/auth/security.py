"""Password hashing (argon2id) and JWT issuance/verification. No framework
dependency here — plain functions, testable without a running FastAPI app or
a database.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from dotenv import load_dotenv

for _p in [Path(__file__).resolve().parents[3] / ".env", Path(__file__).resolve().parents[2] / ".env"]:
    if _p.exists():
        load_dotenv(_p)

_hasher = PasswordHasher()  # argon2id by default (infra/db/001_init.sql comment)

ACCESS_TOKEN_TTL_SECONDS = 15 * 60          # 15 min (plan §5.4)
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
_JWT_ALGORITHM = "HS256"

Role = Literal["user", "authority", "admin"]


def _jwt_secret() -> str:
    secret = os.environ.get("ORCA_JWT_SECRET")
    if not secret:
        raise RuntimeError("ORCA_JWT_SECRET not set — see .env.example")
    return secret


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain)
    except VerifyMismatchError:
        return False


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_TTL_SECONDS


def _issue(user_id: uuid.UUID | str, role: Role, ttl_seconds: int, token_type: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def issue_token_pair(user_id: uuid.UUID | str, role: Role) -> TokenPair:
    return TokenPair(
        access_token=_issue(user_id, role, ACCESS_TOKEN_TTL_SECONDS, "access"),
        refresh_token=_issue(user_id, role, REFRESH_TOKEN_TTL_SECONDS, "refresh"),
    )


class TokenError(Exception):
    pass


def decode_token(token: str, *, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError(f"expected a {expected_type} token, got {payload.get('type')!r}")
    return payload
