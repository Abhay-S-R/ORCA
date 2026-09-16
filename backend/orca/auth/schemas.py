"""Auth / session schema — the Day-8 contract addendum (Phase 2 plan §4.1).
Additive only: nothing here touches contracts.py or state.py."""
from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Role = Literal["user", "authority", "admin"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_identifier(value: str) -> str:
    """One canonical form per account, applied on both register and login.
    Before this, any 3+ characters without an "@" were stored as a phone
    number, and "Name@Mail.com" and "name@mail.com" were different accounts.

    Emails are lower-cased. Phones may be typed the way people actually
    write them — spaces, dashes, or a bare 10-digit Indian mobile number —
    and are stored as E.164 (users.phone_e164)."""
    value = value.strip()
    if "@" in value:
        value = value.lower()
        if not _EMAIL.match(value):
            raise ValueError("Enter a valid email address")
        return value
    digits = re.sub(r"[\s\-()]", "", value)
    if re.fullmatch(r"\d{10}", digits):
        digits = "+91" + digits
    if not _E164.match(digits):
        raise ValueError("Enter a valid email, or a phone number like +91 98765 43210")
    return digits


class RegisterIn(BaseModel):
    identifier: str = Field(min_length=3, description="phone (E.164) or email")
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)
    language: str = "en"

    @field_validator("identifier")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_identifier(v)


class LoginIn(BaseModel):
    identifier: str
    password: str

    @field_validator("identifier")
    @classmethod
    def _normalize(cls, v: str) -> str:
        # Never reject here: a malformed identifier is just a failed login
        # (one generic 401), not a validation error that confirms the format.
        try:
            return normalize_identifier(v)
        except ValueError:
            return v.strip()


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    # The account's own phone or email — only ever returned to that account
    # (/profile is token-scoped), so the account menu can say who is signed in.
    identifier: str | None = None
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
