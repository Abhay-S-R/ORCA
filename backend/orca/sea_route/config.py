"""Configuration for the sea-route routing engine.

All tuneable knobs live here so ops can change them without touching
routing logic.  Values come from environment variables with sensible
defaults for the India-only scope.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SeaRouteConfig:
    # Grid cell size in degrees.  0.05 ° ≈ 5.5 km; allowed range 0.01–0.1.
    cell_deg: float = float(os.getenv("SEA_ROUTE_CELL_DEG", "0.05"))

    # India bounding box (lng_min, lat_min, lng_max, lat_max).
    # Includes Lakshadweep (lng ~72) and Andaman & Nicobar (lng ~93).
    bbox_w: float = 66.0
    bbox_e: float = 95.0
    bbox_s: float = 5.0
    bbox_n: float = 24.0

    # Land-buffer: cells within this many nautical miles of the land polygon
    # edge are also blocked (keeps ships off rocks).
    land_buffer_nm: float = float(os.getenv("SEA_ROUTE_LAND_BUFFER_NM", "1.5"))

    # Coastal standoff buffer: keep routes safely offshore when smoothing (1.5 NM ≈ 2.8 km).
    standoff_buffer_nm: float = float(os.getenv("SEA_ROUTE_STANDOFF_BUFFER_NM", "1.5"))


    # Restricted-area buffer (nm around IMBL/boundary lines).
    restricted_buffer_nm: float = float(os.getenv("SEA_ROUTE_RESTRICTED_BUFFER_NM", "2.0"))

    # Block cells outside the India EEZ polygon (off by default to permit passage around Sri Lanka / Andaman transit).
    eez_blocking: bool = os.getenv("SEA_ROUTE_EEZ_BLOCKING", "0") == "1"

    # Block cells shallower than draft_m (only when gebco file exists).
    depth_blocking: bool = os.getenv("SEA_ROUTE_DEPTH_BLOCKING", "0") == "1"
    draft_m: float = float(os.getenv("SEA_ROUTE_DRAFT_M", "3.0"))

    # Warning distance to restricted area (nm).
    warn_restricted_nm: float = 5.0

    # Optional: round-trip mode (port → zone → port).
    round_trip: bool = os.getenv("SEA_ROUTE_ROUND_TRIP", "0") == "1"

    # Optional: monsoon warning for small vessels (June–September).
    monsoon_warning: bool = os.getenv("SEA_ROUTE_MONSOON_WARNING", "1") == "1"


# Singleton used everywhere; callers may instantiate their own for tests.
DEFAULT_CONFIG = SeaRouteConfig()
