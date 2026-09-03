"""ORM models for the tables Phase 3 D2 (Sentinel) reads from Python —
column-for-column against infra/db/001_init.sql (sentinel_subscriptions,
advisory_feedback) and 002_notifications.sql (notifications).

Kept in its own file rather than appended to orca/db/models.py so D1's
Phase 2 models file is a zero-diff during concurrent Phase 3 work. `Base` is
imported from there — one declarative registry, one metadata.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from orca.db.models import Base

# create_type=False: every enum below already exists in the DB (001 / 002).
watch_type_enum = ENUM(
    "weather", "wave_height", "lightning", "cyclone", "geofence_approach", "pfz_shift",
    name="watch_type", create_type=False,
)
feedback_kind_enum = ENUM(
    "helpful", "not_accurate", "report_issue", name="feedback_kind", create_type=False,
)
notification_status_enum = ENUM(
    "sent", "simulated", "failed", name="notification_status", create_type=False,
)


class SentinelSubscription(Base):
    __tablename__ = "sentinel_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vessel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vessels.id", ondelete="CASCADE"))
    watch_type: Mapped[str] = mapped_column(watch_type_enum, nullable=False)
    # SENSITIVE (001 comment): the location a person watches is a location a
    # person goes to — never returned across a user boundary, redacted from logs.
    watch_point: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326))
    watch_area: Mapped[str | None] = mapped_column(Geometry("POLYGON", srid=4326))
    radius_km: Mapped[float | None] = mapped_column(Numeric(6, 2))
    thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{in_app}'"))
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    last_fired_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    watch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sentinel_subscriptions.id", ondelete="SET NULL"))
    query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default="info")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, server_default="in_app")
    status: Mapped[str] = mapped_column(notification_status_enum, nullable=False, server_default="sent")
    rendered_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AdvisoryFeedback(Base):
    __tablename__ = "advisory_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    advisory_ref: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(feedback_kind_enum, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
