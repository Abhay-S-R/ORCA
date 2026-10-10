"""Coastal Authority Registry and Account Management.

Provides pre-configured coastal authority accounts for all major Indian ports
(Mumbai, Thoothukudi, Chennai, Kochi, Visakhapatnam, Mangalore, Rameswaram,
Kanyakumari, Paradip, Veraval, Kakinada, Kolkata/Haldia).

Handles port resolution from user location / home port and ensures authority
accounts exist with role='authority' and persona='coastal_authority'.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.auth.security import hash_password
from orca.db.models import User, Vessel

logger = logging.getLogger("orca.ops.port_authorities")

# Default credentials for local dev / testing
DEFAULT_AUTHORITY_PASSWORD = "orca-authority-local-dev"
DEMO_USER_EMAIL = "demouser@orca.test"
DEMO_USER_PASSWORD = "demouser123"

# Roster of coastal authority configurations for all major ports
PORT_AUTHORITIES: list[dict[str, Any]] = [
    {
        "port_name": "Mumbai",
        "slug": "mumbai",
        "aliases": ["bombay", "mumbai port", "nhava sheva", "jnp"],
        "lat": 18.9446,
        "lon": 72.8347,
        "email": "authority.mumbai@orca.test",
        "display_name": "Mumbai Coastal Authority",
        "state": "Maharashtra",
        "phone": "022-22612348",
        "alt_phone": "022-24388065",
        "emergency_unit": "Mumbai Port Trust & Yellow Gate Coastal Police",
        "coordinating_mrcc": "MRCC Mumbai",
    },
    {
        "port_name": "Thoothukudi",
        "slug": "thoothukudi",
        "aliases": ["tuticorin", "tuticorine", "thoothukkudi"],
        "lat": 8.7642,
        "lon": 78.1348,
        "email": "authority.thoothukudi@orca.test",
        "display_name": "Thoothukudi Coastal Authority",
        "state": "Tamil Nadu",
        "phone": "0461-2352290",
        "alt_phone": "1093",
        "emergency_unit": "Thoothukudi Coastal Security Group",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Chennai",
        "slug": "chennai",
        "aliases": ["madras", "ennore", "kamarajar"],
        "lat": 13.0827,
        "lon": 80.2707,
        "email": "authority.chennai@orca.test",
        "display_name": "Chennai Coastal Authority",
        "state": "Tamil Nadu",
        "phone": "044-25362201",
        "alt_phone": "044-25395018",
        "emergency_unit": "Chennai Port Trust & Coastal Police",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Kochi",
        "slug": "kochi",
        "aliases": ["cochin", "ernakulam", "vallarpadam"],
        "lat": 9.9312,
        "lon": 76.2673,
        "email": "authority.kochi@orca.test",
        "display_name": "Kochi Coastal Authority",
        "state": "Kerala",
        "phone": "0484-2582400",
        "alt_phone": "1093",
        "emergency_unit": "Cochin Port Signal Station & Coastal Police Kerala",
        "coordinating_mrcc": "MRCC Mumbai",
    },
    {
        "port_name": "Visakhapatnam",
        "slug": "visakhapatnam",
        "aliases": ["vizag", "vishakhapatnam", "waltair"],
        "lat": 17.6868,
        "lon": 83.2185,
        "email": "authority.visakhapatnam@orca.test",
        "display_name": "Visakhapatnam Port Authority",
        "state": "Andhra Pradesh",
        "phone": "0891-2873333",
        "alt_phone": "1093",
        "emergency_unit": "Vizag Port Control & Marine Police",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Mangalore",
        "slug": "mangalore",
        "aliases": ["new mangalore", "mangaluru", "panambur"],
        "lat": 12.9141,
        "lon": 74.8560,
        "email": "authority.mangalore@orca.test",
        "display_name": "New Mangalore Port Authority",
        "state": "Karnataka",
        "phone": "0824-2407298",
        "alt_phone": "1093",
        "emergency_unit": "New Mangalore Port Signal Station & CSG",
        "coordinating_mrcc": "MRCC Mumbai",
    },
    {
        "port_name": "Rameswaram",
        "slug": "rameswaram",
        "aliases": ["pamban", "mandapam", "dhanushkodi"],
        "lat": 9.2876,
        "lon": 79.3129,
        "email": "authority.rameswaram@orca.test",
        "display_name": "Rameswaram Coastal Police",
        "state": "Tamil Nadu",
        "phone": "04573-221213",
        "alt_phone": "1093",
        "emergency_unit": "Pamban & Rameswaram Marine Police Station",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Kanyakumari",
        "slug": "kanyakumari",
        "aliases": ["cape comorin", "chinnamuttam"],
        "lat": 8.0883,
        "lon": 77.5385,
        "email": "authority.kanyakumari@orca.test",
        "display_name": "Kanyakumari Marine Police",
        "state": "Tamil Nadu",
        "phone": "04652-246260",
        "alt_phone": "1093",
        "emergency_unit": "Kanyakumari Coastal Security Group",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Paradip",
        "slug": "paradip",
        "aliases": ["paradeep"],
        "lat": 20.2644,
        "lon": 86.6083,
        "email": "authority.paradip@orca.test",
        "display_name": "Paradip Port Authority",
        "state": "Odisha",
        "phone": "06722-222157",
        "alt_phone": "1093",
        "emergency_unit": "Paradip Port Control & Marine Police",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Veraval",
        "slug": "veraval",
        "aliases": ["somnath", "porbandar", "kandla", "mundra"],
        "lat": 20.9077,
        "lon": 70.3678,
        "email": "authority.veraval@orca.test",
        "display_name": "Veraval Coastal Authority",
        "state": "Gujarat",
        "phone": "02876-220002",
        "alt_phone": "1093",
        "emergency_unit": "Veraval Port Control & Gujarat Marine Police",
        "coordinating_mrcc": "MRCC Mumbai",
    },
    {
        "port_name": "Kakinada",
        "slug": "kakinada",
        "aliases": ["cocanada"],
        "lat": 16.9891,
        "lon": 82.2475,
        "email": "authority.kakinada@orca.test",
        "display_name": "Kakinada Port Authority",
        "state": "Andhra Pradesh",
        "phone": "0884-2364016",
        "alt_phone": "1093",
        "emergency_unit": "Kakinada Port Control & Marine Police",
        "coordinating_mrcc": "MRCC Chennai",
    },
    {
        "port_name": "Kolkata",
        "slug": "kolkata",
        "aliases": ["calcutta", "haldia", "diamond harbour"],
        "lat": 22.5726,
        "lon": 88.3639,
        "email": "authority.kolkata@orca.test",
        "display_name": "Kolkata / Haldia Port Authority",
        "state": "West Bengal",
        "phone": "03224-252100",
        "alt_phone": "1093",
        "emergency_unit": "Haldia Port Control & Marine Police",
        "coordinating_mrcc": "MRCC Chennai",
    },
]

_EARTH_RADIUS_KM = 6371.0


def _km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _point_wkb(lat: float, lon: float) -> Any:
    return from_shape(Point(lon, lat), srid=4326)


def resolve_port_authority_config(
    port_name: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Finds the best-matching authority record from the registry.

    1. First tries exact or alias match on port_name.
    2. Then, if coordinates are available, finds the geographically closest port.
    3. Falls back to Mumbai or Thoothukudi.
    """
    if port_name:
        clean = port_name.lower().strip()
        for p in PORT_AUTHORITIES:
            if clean == p["port_name"].lower() or clean == p["slug"]:
                return p
            for alias in p.get("aliases", []):
                if alias in clean or clean in alias:
                    return p

    if lat is not None and lon is not None:
        best = min(PORT_AUTHORITIES, key=lambda p: _km_between(lat, lon, p["lat"], p["lon"]))
        return best

    # Fallback default: Mumbai
    return PORT_AUTHORITIES[0]


def ensure_port_authorities(db: Session) -> list[User]:
    """Ensures a coastal authority user account exists in PostgreSQL for every port.

    Idempotent: if the account already exists, verifies role='authority' and updates
    home_port if missing. If not, creates the account with password DEFAULT_AUTHORITY_PASSWORD.
    """
    created_or_found: list[User] = []
    pw_hash = hash_password(DEFAULT_AUTHORITY_PASSWORD)

    for cfg in PORT_AUTHORITIES:
        email = cfg["email"]
        stmt = select(User).where(User.email == email)
        user = db.execute(stmt).scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                password_hash=pw_hash,
                display_name=cfg["display_name"],
                role="authority",
                default_persona="coastal_authority",
                language="en",
                home_port=_point_wkb(cfg["lat"], cfg["lon"]),
                home_port_name=cfg["port_name"],
                status="active",
            )
            db.add(user)
            db.flush()
            logger.info("Created coastal authority account: %s (%s)", email, cfg["port_name"])
        else:
            # Ensure correct role & port metadata
            changed = False
            if user.role != "authority":
                user.role = "authority"
                changed = True
            if user.default_persona != "coastal_authority":
                user.default_persona = "coastal_authority"
                changed = True
            if not user.home_port_name:
                user.home_port_name = cfg["port_name"]
                user.home_port = _point_wkb(cfg["lat"], cfg["lon"])
                changed = True
            if changed:
                db.flush()

        created_or_found.append(user)

    # Ensure single general demo account exists for mariner personas
    demo = db.execute(select(User).where(User.email == DEMO_USER_EMAIL)).scalar_one_or_none()
    if demo is None:
        demo = User(
            email=DEMO_USER_EMAIL,
            password_hash=hash_password(DEMO_USER_PASSWORD),
            display_name="Demo Mariner",
            role="user",
            default_persona="fisherman",
            language="en",
            home_port=_point_wkb(18.9446, 72.8347),
            home_port_name="Mumbai",
            status="active",
        )
        db.add(demo)
        db.flush()

    # Ensure demouser has active vessel (fibreglass boat)
    vessel = db.execute(select(Vessel).where(Vessel.owner_user_id == demo.id)).scalar_one_or_none()
    if vessel is None:
        vessel = Vessel(
            owner_user_id=demo.id,
            name="Sagar Demo",
            vessel_class="fibreglass",
            length_m=9.5,
            draft_m=1.2,
            crew_size=4,
            cruise_speed_kn=12.0,
            fuel_burn_lph=14.0,
            engine_count=1,
            last_position=_point_wkb(18.9446, 72.8347),
        )
        db.add(vessel)
        db.flush()
    if demo.active_vessel_id != vessel.id:
        demo.active_vessel_id = vessel.id
        db.flush()

    db.commit()
    return created_or_found


def get_authority_user_for_port(
    db: Session,
    port_name: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> tuple[dict[str, Any], User]:
    """Resolves the port authority config AND finds (or creates) the User database row."""
    cfg = resolve_port_authority_config(port_name, lat, lon)
    stmt = select(User).where(User.email == cfg["email"])
    user = db.execute(stmt).scalar_one_or_none()

    if user is None:
        # Lazy creation if not seeded yet
        pw_hash = hash_password(DEFAULT_AUTHORITY_PASSWORD)
        user = User(
            email=cfg["email"],
            password_hash=pw_hash,
            display_name=cfg["display_name"],
            role="authority",
            default_persona="coastal_authority",
            language="en",
            home_port=_point_wkb(cfg["lat"], cfg["lon"]),
            home_port_name=cfg["port_name"],
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return cfg, user


def ensure_test_mariners(db: Session) -> list[User]:
    """Ensures at least one active test user exists for each mariner persona
    (fisherman, commercial_navigator, researcher) so broadcast targeting can be verified."""
    mariners: list[dict[str, Any]] = [
        {
            "email": "fisherman@orca.test",
            "display_name": "Kadal Meenavan (Fisherman)",
            "persona": "fisherman",
            "home_port_name": "Mumbai",
            "lat": 18.9446,
            "lon": 72.8347,
        },
        {
            "email": "navigator@orca.test",
            "display_name": "MV Sagar Deep (Commercial Navigator)",
            "persona": "commercial_navigator",
            "home_port_name": "Mumbai",
            "lat": 18.9446,
            "lon": 72.8347,
        },
        {
            "email": "researcher@orca.test",
            "display_name": "NIO Ocean Research (Researcher)",
            "persona": "researcher",
            "home_port_name": "Mumbai",
            "lat": 18.9446,
            "lon": 72.8347,
        },
    ]
    created: list[User] = []
    pw_hash = hash_password(DEFAULT_AUTHORITY_PASSWORD)
    for m in mariners:
        stmt = select(User).where(User.email == m["email"])
        user = db.execute(stmt).scalar_one_or_none()
        lat = float(m["lat"])
        lon = float(m["lon"])
        persona = str(m["persona"])
        home_port_name = str(m["home_port_name"])
        if user is None:
            user = User(
                email=str(m["email"]),
                password_hash=pw_hash,
                display_name=str(m["display_name"]),
                role="user",
                default_persona=persona,
                language="en",
                home_port=_point_wkb(lat, lon),
                home_port_name=home_port_name,
                status="active",
            )
            db.add(user)
            db.flush()
        else:
            if user.default_persona != persona:
                user.default_persona = persona
            if not user.home_port_name:
                user.home_port_name = home_port_name
                user.home_port = _point_wkb(lat, lon)
        created.append(user)
    db.commit()
    return created

