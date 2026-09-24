"""ORM models — column-for-column against infra/db/001_init.sql. Only the
tables D1's Phase 2 surfaces touch (users, vessels, sessions,
audit_trace_log) are mapped; sentinel_subscriptions/advisory_feedback stay
Phase 3's (Agent 11) to map when they're first read from Python.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, SmallInteger, Text, text
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
persona_enum = ENUM(
    "fisherman", "commercial_navigator", "researcher", "coastal_authority", "unresolved",
    name="persona", create_type=False,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    phone_e164: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(user_role_enum, nullable=False, server_default="user")
    # P3.4 bug found: mapped as Text, the DB column is the `persona` enum —
    # same latent defect as SessionRow.persona below, and for the same
    # reason nothing caught it: nothing wrote `default_persona` from Python
    # until P3.4's `PUT /api/profile/persona` (`UPDATE ... ::VARCHAR` against
    # an enum column, rejected by Postgres). Fixed at the one mapping, not
    # patched at the write site.
    default_persona: Mapped[str] = mapped_column(persona_enum, nullable=False, server_default="unresolved")
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    # SENSITIVE — never returned to another user (plan §5.5).
    home_port: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    home_port_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(account_status_enum, nullable=False, server_default="active")
    # 007_vessel_operational.sql (P3.9) — orca_final §15.3: several vessels,
    # one active. NULL until the owner has at least one vessel and picks one.
    active_vessel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vessels.id", ondelete="SET NULL")
    )
    # {"start": "22:00", "end": "06:00", "tz": "Asia/Kolkata"} or NULL (no
    # quiet hours set) — P5.22 reads this to hold a non-critical alert.
    quiet_hours: Mapped[dict | None] = mapped_column(JSONB)
    # 009_pre_dawn_briefing.sql (R-NEW-16) — local 24h hour this user typically
    # departs, or NULL (feature off). `last_pre_dawn_briefing_date` is the
    # local calendar date Sentinel last sent the digest, so it fires once a day.
    typical_departure_hour: Mapped[int | None] = mapped_column(SmallInteger)
    last_pre_dawn_briefing_date: Mapped[date | None] = mapped_column(Date)
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
    # 007_vessel_operational.sql (P3.9) — NULL means the dependent feature
    # (worthwhileness P5.8, fuel economics P5.9, R-NEW-14 thresholds) says
    # MISSING rather than assuming a value nobody gave it.
    cruise_speed_kn: Mapped[float | None] = mapped_column(Numeric(5, 2))
    fuel_burn_lph: Mapped[float | None] = mapped_column(Numeric(6, 2))
    engine_count: Mapped[int | None] = mapped_column(SmallInteger)
    # SENSITIVE — last known position (plan §5.5).
    last_position: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    last_position_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Voyage(Base):
    """008_phase5_watches_voyages.sql (P5.20) — a saved passage plan. The
    route watch it may be promoted to (P5.17) is a `sentinel_subscriptions`
    row; `watch_id` here is the pointer, never the other way around, so
    deleting the watch never deletes the plan itself."""

    __tablename__ = "voyages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vessel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vessels.id", ondelete="SET NULL"))
    name: Mapped[str | None] = mapped_column(Text)
    # SENSITIVE — same class as watch_point/watch_area (001 comment): a
    # voyage plan is a place and a time a person goes to sea.
    route: Mapped[str] = mapped_column(Geometry("LINESTRING", srid=4326), nullable=False)
    departure_at: Mapped[datetime] = mapped_column(nullable=False)
    watch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sentinel_subscriptions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    # The DB column is the `persona` enum; mapped as Text it bound as VARCHAR,
    # which Postgres refuses for an enum column on INSERT — harmless only while
    # nothing inserted a session from Python.
    persona: Mapped[str] = mapped_column(persona_enum, nullable=False, server_default="unresolved")
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    channel: Mapped[str] = mapped_column(Text, nullable=False, server_default="web")
    started_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    # 003_chat_history.sql — a signed-in user's saved Ask chat is one session.
    title: Mapped[str | None] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)  # "user" | "assistant"
    text_original: Mapped[str | None] = mapped_column(Text)
    text_english: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)  # 003: the assistant answer the chat card renders
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class RefreshToken(Base):
    """004_refresh_tokens.sql — one row per issued refresh token, by jti."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    confidence_score: Mapped[int | None]  # 005_confidence_score.sql
    confidence_detail: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(execution_status_enum, nullable=False, server_default="ok")
    error_detail: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class SavedLocation(Base):
    """007_vessel_operational.sql (P3.10) — a signed-in user's bookmarked
    places, one tap above the /ask composer for today's verdict at that spot.
    Distinct from `users.home_port` (exactly one) and a Sentinel watch (P5.17
    promotes one of these; it does not replace this table)."""

    __tablename__ = "saved_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[str] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
