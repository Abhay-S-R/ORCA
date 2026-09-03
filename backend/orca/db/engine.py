"""Engine + session factory. One engine per process (module-level, not
per-request) — SQLAlchemy pools connections internally, so re-creating the
engine per call would defeat pooling for no benefit.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Same .env auto-load convention as orca/llm/tiers.py.
for _p in [Path(__file__).resolve().parents[3] / ".env", Path(__file__).resolve().parents[2] / ".env"]:
    if _p.exists():
        load_dotenv(_p)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set — see .env.example")
    # docker-compose / .env.example both use the plain postgresql:// scheme;
    # this process talks to it through psycopg (v3), so the driver must be
    # named explicitly rather than relying on SQLAlchemy's psycopg2 default.
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency — one session per request, always closed."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
