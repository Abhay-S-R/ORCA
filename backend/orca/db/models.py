"""ORM models — column-for-column against infra/db/001_init.sql. Only the
tables D1's Phase 2 surfaces touch (users, vessels, sessions,
audit_trace_log) are mapped; sentinel_subscriptions/advisory_feedback stay
Phase 3's (Agent 11) to map when they're first read from Python.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# match=False: these enums already exist in the DB (created by
# infra/db/001_init.sql); SQLAlchemy must not try to CREATE TYPE again.
user_role_enum = ENUM("user", "authority", "admin", name="user_role", create_type=False)
account_status_enum = ENUM("active", "suspended", "deleted", name="account_status", create_type=False)
vessel_class_enum = ENUM(
    "catamaran", "fibreglass", "mechanised", "trawler", "cargo", name="vessel_class", create_type=False
)
confidence_tier_enum = ENUM("HIGH", "MEDIUM", "LOW_DATA", name="confidence_tier", create_type=False)
execution_status_enum = ENUM(
    "ok", "degraded", "failed", "skipped", "cancelled", name="execution_status", create_type=False
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    phone_e164: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(user_role_enum, nullable=False, server_default="user")
    default_persona: Mapped[str] = mapped_column(Text, nullable=False, server_default="unresolved")
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    # SENSITIVE — never returned to another user (plan §5.5).
    home_port: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    home_port_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(account_status_enum, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    # SENSITIVE — identifies a real boat and its crew (plan §5.5).
    registration_no: Mapped[str | None] = mapped_column(Text, unique=True)
    vessel_class: Mapped[str] = mapped_column("class", vessel_class_enum, nullable=False)
    draft_m: Mapped[float | None] = mapped_column(Numeric(4, 2))
    length_m: Mapped[float | None] = mapped_column(Numeric(5, 2))
    crew_size: Mapped[int | None] = mapped_column(SmallInteger)
    # SENSITIVE — last known position (plan §5.5).
    last_position: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    last_position_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    persona: Mapped[str] = mapped_column(Text, nullable=False, server_default="unresolved")
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    channel: Mapped[str] = mapped_column(Text, nullable=False, server_default="web")
    started_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AuditTraceLog(Base):
    __tablename__ = "audit_trace_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"))
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    span_id: Mapped[str | None] = mapped_column(Text)
    parent_span_id: Mapped[str | None] = mapped_column(Text)
    inputs_consumed: Mapped[dict | None] = mapped_column(JSONB)
    outputs: Mapped[dict | None] = mapped_column(JSONB)
    source_provenance: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[str | None] = mapped_column(confidence_tier_enum)
    status: Mapped[str] = mapped_column(execution_status_enum, nullable=False, server_default="ok")
    error_detail: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
