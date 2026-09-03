"""Auth / session schema — the Day-8 contract addendum (Phase 2 plan §4.1).
Additive only: nothing here touches contracts.py or state.py."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Role = Literal["user", "authority", "admin"]


class RegisterIn(BaseModel):
    identifier: str = Field(min_length=3, description="phone (E.164) or email")
    password: str = Field(min_length=8)
    display_name: str | None = None
    language: str = "en"


class LoginIn(BaseModel):
    identifier: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    display_name: str | None
    role: Role
    language: str
    home_port: dict[str, float] | None = None
    home_port_name: str | None = None


class SessionToken(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class HomePortIn(BaseModel):
    lat: float
    lon: float
    name: str | None = None

    @field_validator("lat")
    @classmethod
    def _lat_range(cls, v: float) -> float:
        if not -90.0 <= v <= 90.0:
            raise ValueError("lat must be in [-90, 90]")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_range(cls, v: float) -> float:
        if not -180.0 <= v <= 180.0:
            raise ValueError("lon must be in [-180, 180]")
        return v


VesselClass = Literal["catamaran", "fibreglass", "mechanised", "trawler", "cargo"]


class VesselIn(BaseModel):
    vessel_class: VesselClass
    name: str | None = None
    registration_no: str | None = None
    draft_m: float | None = Field(default=None, gt=0)
    length_m: float | None = Field(default=None, gt=0)
    crew_size: int | None = Field(default=None, ge=0)


class VesselOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    vessel_class: VesselClass
    name: str | None
    registration_no: str | None
    draft_m: float | None
    length_m: float | None
    crew_size: int | None
    last_position: dict[str, float] | None = None
