"""D2 Phase 3 contract addendum (plan §5.1) — additive only, nothing in
orca/contracts.py or orca/state.py is touched.

`WatchIn`/`WatchOut` are the /watches CRUD shapes; `NotificationOut` is the
feed row; `DispatchResult` + the `Dispatcher` protocol are the delivery
boundary Sentinel calls (and the ONLY thing it calls — exit criterion 10).

Pydantic for the HTTP shapes (same as orca/auth/schemas.py); a frozen
dataclass for `DispatchResult` (same as orca/contracts.py — it crosses an
agent boundary, not an HTTP one).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Mirrors the watch_type enum in infra/db/001_init.sql exactly.
WatchType = Literal[
    "weather", "wave_height", "lightning", "cyclone", "geofence_approach", "pfz_shift"
]
Channel = Literal["in_app", "sms", "ivr", "ussd"]
Severity = Literal["info", "advisory", "warning", "danger"]
NotificationStatus = Literal["sent", "simulated", "failed"]


class WatchIn(BaseModel):
    """Create/replace a watch. `user_id` is deliberately absent — identity
    comes from the bearer token at the route, never the body (plan §5.4)."""

    watch_type: WatchType
    # A watch is a point OR an area (001 CONSTRAINT sentinel_has_geometry).
    lat: float | None = None
    lon: float | None = None
    # GeoJSON Polygon coordinates for an authority-scale area watch.
    area_geojson: dict[str, Any] | None = None
    radius_km: float | None = Field(default=None, gt=0, le=500)
    vessel_id: uuid.UUID | None = None
    # {"wave_height_m": 2.5, "wind_kt": 25} — keys are free-form; Sentinel's
    # crossing test knows which ones it understands and ignores the rest.
    thresholds: dict[str, float] = Field(default_factory=dict)
    channels: list[Channel] = Field(default_factory=lambda: ["in_app"])
    enabled: bool = True

    @field_validator("lat")
    @classmethod
    def _lat_range(cls, v: float | None) -> float | None:
        if v is not None and not -90.0 <= v <= 90.0:
            raise ValueError("lat must be in [-90, 90]")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_range(cls, v: float | None) -> float | None:
        if v is not None and not -180.0 <= v <= 180.0:
            raise ValueError("lon must be in [-180, 180]")
        return v

    @model_validator(mode="after")
    def _has_geometry(self) -> WatchIn:
        has_point = self.lat is not None and self.lon is not None
        if not has_point and self.area_geojson is None:
            raise ValueError("a watch needs either lat+lon or area_geojson")
        return self


class WatchOut(BaseModel):
    id: uuid.UUID
    watch_type: WatchType
    lat: float | None = None
    lon: float | None = None
    radius_km: float | None = None
    vessel_id: uuid.UUID | None = None
    thresholds: dict[str, float]
    channels: list[str]
    enabled: bool
    last_fired_at: datetime | None = None
    created_at: datetime


class NotificationOut(BaseModel):
    id: uuid.UUID
    watch_id: uuid.UUID | None
    query_id: uuid.UUID | None
    severity: Severity
    title: str
    body: str
    channel: Channel
    status: NotificationStatus
    rendered_payload: dict[str, Any]
    read: bool
    created_at: datetime


class FeedbackIn(BaseModel):
    query_id: uuid.UUID
    kind: Literal["helpful", "not_accurate", "report_issue"]
    advisory_ref: str | None = None
    comment: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------
# Dispatcher — the delivery boundary (plan §4.9, §5.1)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchResult:
    channel: Channel
    status: NotificationStatus
    detail: str  # human-readable: "written to feed" / "SMS transport not implemented"


class Dispatcher:
    """Protocol (structural). Sentinel and /ops call `send()` and nothing
    else — there is no gateway object anywhere in Agent 11 (exit criterion
    10). A concrete dispatcher either delivers and returns `sent`, renders
    without transmitting and returns `simulated`, or raises — never claims a
    delivery that did not happen (plan §4.9 verbatim)."""

    channel: Channel

    def send(self, *, recipient: dict[str, Any], rendered_payload: dict[str, Any]) -> DispatchResult:  # pragma: no cover - interface
        raise NotImplementedError
