"""Loaders over data/ — JSON, CSV, GeoJSON, NetCDF (plan §5 repo layout, S3
Day 3). Every loader here is a thin read; normalization happens in
normalize.py, not in here — a loader's job is "get bytes into memory", not
"fix axis order".
"""
from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ponytail: CSV/GeoJSON/NetCDF loaders are one-liners over pandas/geopandas/
# xarray — no wrapper earns its keep until a caller needs more than "read the
# file". Reuse scripts/orca_grid_utils.py for wet-cell snapping on a NetCDF
# grid; do not re-implement it (plan §5 Day 3 note).
#
#   import pandas as pd; pd.read_csv(path)
#   import geopandas as gpd; gpd.read_file(path)
#   import xarray as xr; xr.open_dataset(path)


def cached_weather_path(port: str) -> Path:
    return DATA_DIR / "tier1" / "weather" / f"openmeteo_weather_{port}.json"


def cached_marine_path(port: str) -> Path:
    return DATA_DIR / "tier1" / "ocean" / f"openmeteo_marine_{port}.json"


def cached_lightning_path(port: str) -> Path:
    return DATA_DIR / "tier1" / "hazards" / f"lightning_nowcast_{port}.json"


def cached_ndma_cap_alerts_path() -> Path:
    return DATA_DIR / "tier1" / "hazards" / "ndma_cap_alerts.json"


def cached_gdacs_tc_path() -> Path:
    """Last successful GDACS tropical-cyclone fetch — the fallback for the map layer."""
    return DATA_DIR / "tier1" / "hazards" / "gdacs_tc_tracks.json"


# Ports with a cached fallback on disk. Globbed from the files themselves rather
# than hand-listed, so `scripts/refresh_openmeteo_caches.py` widening coverage
# (it fetches every _GAZETTEER coordinate) is picked up without a second edit
# here — and a port whose marine fetch failed simply stays out of
# CACHED_MARINE_PORTS instead of being offered and then missing.
_PILOT_PORTS = ("chennai", "kochi", "mumbai", "pamban", "thoothukudi", "visakhapatnam")


def _cached_ports(template: Path) -> tuple[str, ...]:
    """Port names behind a `cached_*_path("*")` pattern, pilot six if data/ is absent."""
    prefix, suffix = template.name.split("*")
    found = tuple(sorted(f.name[len(prefix):-len(suffix)] for f in template.parent.glob(template.name)))
    return found or _PILOT_PORTS


CACHED_WEATHER_PORTS = _cached_ports(cached_weather_path("*"))
CACHED_MARINE_PORTS = _cached_ports(cached_marine_path("*"))

# Port name -> (lat, lon), lazily built from each port's own cached weather
# fixture rather than a second hand-maintained coordinate table — the file
# already carries its own latitude/longitude. Shared by weather_intelligence's
# nearest-cached-port fallback and resolve_place_from_text() below.
_PORT_COORDS: dict[str, tuple[float, float]] | None = None


def port_coordinates() -> dict[str, tuple[float, float]]:
    global _PORT_COORDS
    if _PORT_COORDS is None:
        coords = {}
        for port in CACHED_WEATHER_PORTS:
            path = cached_weather_path(port)
            if path.exists():
                d = load_json(path)
                coords[port] = (d["latitude"], d["longitude"])
        _PORT_COORDS = coords
    return _PORT_COORDS


# The position a query is answered at when it names no place we can resolve and
# carries no GPS fix: roughly 10 nm off Thoothukudi in the Gulf of Mannar, on
# the fishing grounds the pilot region is about.
#
# The old default (8.80, 78.14) was the *town*, which /api/depth reports as
# on_land: true — so every locationless query was answered at a point no vessel
# can occupy, with a seabed depth of null and a shallow-water hazard check that
# could never fire. This one is wet (22 m over GEBCO), clear of the Gulf of
# Mannar Marine National Park boundary, and ~45 nm inside the IMBL, so a
# default-position answer is a plausible one rather than a nonsensical one.
# It is still a *default*: main.py labels it `place_source="regional_default"`
# so nothing downstream mistakes it for the user's actual position.
DEFAULT_LAT, DEFAULT_LON = 8.80, 78.30

# Alternate spellings people actually type, mapped onto a CACHED_WEATHER_PORTS
# name. Not an exhaustive gazetteer — just the ones a real query is likely to use.
_PORT_ALIASES = {"cochin": "kochi", "vizag": "visakhapatnam", "bombay": "mumbai", "madras": "chennai"}


# ---------------------------------------------------------------------------
# Pilot-region gazetteer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedPlace:
    """Where a query's coordinates came from. `source` is the point of this
    type: the caller has to be able to tell a real resolution from the
    regional default, because a wrong-but-confident position is the most
    dangerous output this system can produce — the IMBL distance at Palk Bay
    is 0.4 nm (DANGER) and at Thoothukudi is 53 nm (GO)."""

    name: str  # display name, as it should appear to a user
    lat: float
    lon: float
    source: str  # "port_fixture" | "tide_station" | "pilot_gazetteer"


def tide_station_coordinates() -> dict[str, tuple[float, float]]:
    """Station name fragments -> coordinates, read from the SoI tide-station
    metadata already on disk rather than re-typed here. The file's
    `station_name` carries the parenthesised alternates people actually use
    ("Cochin Port (Kochi)", "Pamban Pass / Rameswaram"), so splitting on the
    punctuation gives the alias list for free."""
    path = DATA_DIR / "tier1" / "tides" / "soi_tide_stations_metadata.json"
    if not path.exists():
        return {}
    out: dict[str, tuple[float, float]] = {}
    for st in load_json(path).get("stations", []):
        coords = (st["latitude"], st["longitude"])
        for fragment in re.split(r"[(),/]", st.get("station_name", "")):
            name = fragment.strip().lower()
            # "Port", "Pass" etc. on their own are not place names; require a
            # word that could plausibly identify a location.
            if len(name) >= 4 and name not in ("port", "pass", "point", "harbour"):
                out.setdefault(name, coords)
    return out


# Pilot-region places that have no fixture and no tide gauge but appear in
# real queries and in the architecture doc's own scenario table. Coordinates
# are the centroid of the named water body or the landing centre itself, to
# 4 dp — enough for a boundary-proximity answer, which is what they are for.
# This is deliberately a short, auditable, hand-checked list rather than a
# geocoder call: an LLM or a network geocoder guessing a coastline position
# is exactly the fabricated-input failure §5.7 forbids.
#
# Where a place has both a cached weather fixture and an entry here, this
# entry wins. A fixture's coordinate is an Open-Meteo *grid-cell* snap chosen
# to name a file, not a position a vessel occupies, and using one as a
# position has already produced a wrong verdict: the pamban fixture snaps to
# (9.2443, 79.2281), which falls inside this repo's MEDIUM-precision Gulf of
# Mannar Marine National Park polygon (OSM relation 415570), so every "is it
# safe near Pamban" answered NO_GO — Imminent Boundary or MPA Breach. The
# surveyed Pamban Pass position below sits 1.6 nm clear of the same polygon.
#
# ALL-INDIA COVERAGE. The pilot-only version of this table was the single
# highest-harm defect in the product: a query naming Veraval, Paradeep, Digha,
# Port Blair or Kavaratti resolved to nothing, fell through to DEFAULT_LAT/LON
# in the Gulf of Mannar, and was then answered *confidently about the wrong
# coast* — an IMBL distance for Tamil Nadu presented to a fisherman off
# Gujarat. Coordinates below are offshore positions (~10-20 nm out), not town
# centres, for the same reason the Thoothukudi entry is a harbour approach: a
# depth or wave reading at a town centre is a reading on dry land.
#
# 2026-09-22: `scripts/verify_gazetteer_at_sea.py` still found 60 entries
# (of 203) GEBCO reads as on_land — the hand-picked offshore nudge above
# wasn't applied consistently. Each was moved to the nearest wet GEBCO cell
# with `scripts/orca_grid_utils.snap_to_wet_cell` (the same nearest-wet-cell
# search used for the WW3/HYCOM model grids), aliases sharing a coordinate
# (alappuzha/alleppey, kollam/quilon, etc.) snapped together so they stay
# equal. `verify_gazetteer_at_sea.py` now reports 0 on land.
_GAZETTEER: dict[str, tuple[float, float]] = {
    # Surveyed tide-gauge position (SoI station PAM), not the weather-grid snap.
    "pamban": (9.2833, 79.2000),
    # Harbour approach rather than the town centre: the town itself is on land
    # (GEBCO on_land: true), which makes every depth and wave reading at it
    # meaningless for a query that is really about going to sea from there.
    "thoothukudi": (8.7700, 78.2300),
    "tuticorin": (8.7700, 78.2300),
    "palk bay": (9.5000, 79.2000),
    "palk strait": (9.8000, 79.6000),
    "gulf of mannar": (8.8000, 78.7000),
    "mandapam": (9.2812, 79.1312),
    "dhanushkodi": (9.1500, 79.4167),
    "tiruchendur": (8.4938, 78.1312),
    "kanyakumari": (8.0771, 77.5437),
    "kulasekarapattinam": (8.3938, 78.0604),
    "vembar": (9.1188, 78.4354),
    "kilakarai": (9.2229, 78.7812),
    "nagapattinam": (10.7646, 79.8521),
    "cuddalore": (11.7521, 79.7896),
    "tamil nadu": (9.50, 79.50),
    "tamil nadu coast": (9.50, 79.50),
    "rameswaram": (9.2938, 79.2979),
    "pondicherry": (11.93, 79.87),
    "puducherry": (11.93, 79.87),
    "karaikal": (10.9104, 79.8521),
    "velankanni": (10.6813, 79.8562),
    "porto novo": (11.5021, 79.7729),
    "ennore": (13.2104, 80.3271),
    "mahabalipuram": (12.6229, 80.2021),
    "chennai": (13.1000, 80.3200),
    "chennai port": (13.1000, 80.3200),
    "madras": (13.1000, 80.3200),
    "v.o. chidambaranar port": (8.7700, 78.2300),
    "voc port": (8.7700, 78.2300),
    # ── Kerala ──────────────────────────────────────────────────────────
    "kerala": (10.50, 76.00),
    "kerala coast": (10.50, 76.00),
    "thiruvananthapuram": (8.4646, 76.9271),
    "trivandrum": (8.4646, 76.9271),
    "kollam": (8.8771, 76.5854),
    "quilon": (8.8771, 76.5854),
    "alappuzha": (9.4938, 76.3187),
    "alleppey": (9.4938, 76.3187),
    "kochi": (9.9667, 76.2000),
    "cochin": (9.9667, 76.2000),
    "cochin port": (9.9667, 76.2000),
    "ernakulam": (9.90, 76.00),
    "thrissur": (10.5021, 76.1104),
    "kozhikode": (11.2479, 75.7729),
    "calicut": (11.2479, 75.7729),
    "kannur": (11.8563, 75.3771),
    "cannanore": (11.8563, 75.3771),
    "kasaragod": (12.4938, 74.9771),
    "lakshadweep": (10.57, 72.64),
    "minicoy": (8.28, 73.04),
    "kavaratti": (10.57, 72.64),
    "agatti": (10.85, 72.17),
    # ── Karnataka ───────────────────────────────────────────────────────
    "karnataka": (13.50, 74.50),
    "karnataka coast": (13.50, 74.50),
    "mangalore": (12.85, 74.65),
    "mangaluru": (12.85, 74.65),
    "udupi": (13.33, 74.60),
    "karwar": (14.80, 73.90),
    "ankola": (14.6521, 74.2854),
    "bhatkal": (13.9604, 74.5396),
    "kundapur": (13.63, 74.62),
    # ── Goa ─────────────────────────────────────────────────────────────
    "goa": (15.50, 73.50),
    "goa coast": (15.50, 73.50),
    "panaji": (15.50, 73.70),
    "mormugao": (15.3979, 73.7937),
    "mormugao port": (15.3979, 73.7937),
    "vasco da gama": (15.3979, 73.7937),
    # ── Maharashtra ─────────────────────────────────────────────────────
    "maharashtra": (17.50, 71.00),
    "maharashtra coast": (17.50, 71.00),
    "mumbai": (18.9200, 72.7800),
    "bombay": (18.9200, 72.7800),
    "mumbai port": (18.9200, 72.7800),
    "apollo bunder": (18.9200, 72.7800),
    "jnpt": (18.9200, 72.7800),
    "sindhudurg": (16.00, 73.40),
    "ratnagiri": (16.99, 73.12),
    "raigad": (18.50, 72.80),
    "alibag": (18.64, 72.72),
    "vasai": (19.40, 72.70),
    "dahanu": (19.9646, 72.7271),
    "tarapur": (19.9271, 72.7354),
    # ── Gujarat ─────────────────────────────────────────────────────────
    "gujarat": (21.3604, 69.8646),
    "gujarat coast": (21.3604, 69.8646),
    "surat": (21.10, 72.30),
    "bharuch": (21.70, 72.50),
    "veraval": (20.90, 70.37),
    "somnath": (20.90, 70.37),
    "dwarka": (22.24, 68.70),
    "okha": (22.47, 69.05),
    "okha port": (22.47, 69.05),
    "jamnagar": (22.5063, 69.9521),
    "porbandar": (21.64, 69.50),
    "bhavnagar": (21.7771, 72.2312),
    "mandvi": (22.8146, 69.3479),
    "mundra": (22.70, 69.50),
    "kandla": (23.0313, 70.2229),
    "deendayal port": (23.0313, 70.2229),
    "hazira": (21.12, 72.66),
    "gulf of kutch": (22.50, 69.50),
    "gulf of khambhat": (21.00, 72.50),
    # ── Andhra Pradesh ──────────────────────────────────────────────────
    "andhra pradesh": (15.00, 80.50),
    "andhra coast": (15.00, 80.50),
    "nellore": (14.3229, 80.1604),
    "ongole": (15.50, 80.33),
    "krishnapatnam": (14.2521, 80.1312),
    "machilipatnam": (16.1063, 81.1937),
    "kakinada": (16.93, 82.25),
    "visakhapatnam": (17.6800, 83.3200),
    "visakhapatnam port": (17.6800, 83.3200),
    "vizag": (17.6800, 83.3200),
    "bhimavaram": (16.3563, 81.5437),
    # ── Odisha ──────────────────────────────────────────────────────────
    "odisha": (19.50, 85.50),
    "odisha coast": (19.50, 85.50),
    "gopalpur": (19.2604, 84.9146),
    "puri": (19.80, 85.85),
    "chilika": (19.7021, 85.3146),
    # Both spellings: the port authority writes "Paradip", the older charts and
    # most of the coast write "Paradeep". Only the second was here, so "tide at
    # Paradip" resolved to nothing.
    "paradeep": (20.2688, 86.6771),
    "paradip": (20.2688, 86.6771),
    "dhamra": (20.7646, 86.9562),
    "balasore": (21.4563, 87.0479),
    "chandipur": (21.4771, 87.0896),
    # ── West Bengal ─────────────────────────────────────────────────────
    "west bengal": (21.63, 88.00),
    "west bengal coast": (21.63, 88.00),
    "haldia": (22.0188, 88.0812),
    "haldia dock complex": (22.0188, 88.0812),
    "sagar island": (21.6313, 88.0812),
    "sundarbans": (21.9188, 88.8521),
    "digha": (21.6146, 87.5021),
    "kolkata": (22.0188, 88.0812),
    # ── Andaman & Nicobar ───────────────────────────────────────────────
    "andaman": (12.0021, 93.0104),
    "andaman coast": (12.0021, 93.0104),
    "andaman sea": (10.00, 95.00),
    "port blair": (11.67, 92.75),
    "nicobar": (8.00, 93.50),
    "car nicobar": (9.17, 92.83),
    "little andaman": (10.6688, 92.5812),
    "north andaman": (13.2729, 93.0187),
    "havelock island": (12.0313, 92.9771),
    # ── Fishing harbours and landing centres ────────────────────────────
    #
    # Audited 2026-09-20: 84 of 87 real Indian coastal fishing places tested
    # resolved to NOTHING, and a query naming one was answered at the pilot
    # default 1,500 km away ("nearest fishing zone near Mangrol" -> Karankadu,
    # Gulf of Mannar). The PFZ, weather and lightning data for those coasts was
    # already on disk and already all-India; the gazetteer was the bottleneck.
    #
    # Each coordinate is nudged seaward of the town centre, matching the
    # existing entries (Porbandar is 69.50, the town is 69.60) and for the same
    # reason DEFAULT_LAT/LON was moved offshore: a town point reads on_land to
    # /api/depth, which nulls the seabed and disarms the shallow-water check.
    # `scripts/verify_gazetteer_at_sea.py` is the runnable check on that.
    # ── Gujarat
    "mangrol": (21.08, 70.10),
    "jakhau": (23.17, 68.62),
    "diu": (20.68, 70.98),
    "jafrabad": (20.83, 71.37),
    "navabandar": (20.75, 71.10),
    "sutrapada": (20.81, 70.45),
    "valsad": (20.58, 72.88),
    "navsari": (20.85, 72.70),
    "umbergaon": (20.17, 72.68),
    "mahuva": (21.02, 71.77),
    "salaya": (22.40, 69.60),
    "vanakbara": (20.70, 70.80),
    # ── Maharashtra
    "malvan": (16.05, 73.42),
    "vengurla": (15.85, 73.58),
    "harnai": (17.81, 73.05),
    "dabhol": (17.58, 73.12),
    "shrivardhan": (18.04, 72.97),
    "murud": (18.33, 72.90),
    "uran": (18.85, 72.92),
    "satpati": (19.71, 72.66),
    "arnala": (19.46, 72.72),
    "versova": (19.13, 72.78),
    # ── Karnataka
    "malpe": (13.35, 74.66),
    "gangolli": (13.65, 74.62),
    "honnavar": (14.28, 74.40),
    "belekeri": (14.71, 74.22),
    "tadri": (14.52, 74.35),
    "kumta": (14.42, 74.37),
    # ── Kerala
    "beypore": (11.16, 75.76),
    "ponnani": (10.77, 75.87),
    "munambam": (10.18, 76.12),
    "vizhinjam": (8.35, 77.00),
    "neendakara": (8.93, 76.50),
    "azhikkal": (11.93, 75.25),
    "thalassery": (11.74, 75.45),
    "chavakkad": (10.58, 75.98),
    # ── Tamil Nadu (Comorin and Gulf of Mannar)
    "colachel": (8.15, 77.24),
    "thengapattinam": (8.15, 77.25),
    "muttom": (8.10, 77.31),
    "kadiapatnam": (8.10, 77.40),
    "manapad": (8.35, 78.10),
    "uvari": (8.28, 77.98),
    "periyathalai": (8.41, 78.07),
    "chinnamuttom": (8.06, 77.56),
    "tharuvaikulam": (8.88, 78.25),
    "punnakayal": (8.62, 78.17),
    # ── Tamil Nadu (Coromandel)
    "nagore": (10.82, 79.89),
    "tharangambadi": (11.03, 79.89),
    "tranquebar": (11.03, 79.89),
    "poompuhar": (11.14, 79.90),
    "parangipettai": (11.49, 79.82),
    "marakkanam": (12.19, 79.99),
    "pulicat": (13.42, 80.37),
    # ── Andhra Pradesh
    "nizampatnam": (15.87, 80.70),
    "kalingapatnam": (18.33, 84.18),
    "bheemunipatnam": (17.89, 83.50),
    "narsapur": (16.25, 81.80),
    "antarvedi": (16.30, 81.77),
    "uppada": (17.08, 82.40),
    "gangavaram": (17.62, 83.27),
    "vadarevu": (15.82, 80.55),
    "suryalanka": (15.85, 80.64),
    "ramayapatnam": (15.04, 80.10),
    # ── Odisha
    "astaranga": (20.00, 86.45),
    "jatadhari": (20.24, 86.74),
    "talchua": (20.70, 87.05),
    "chandbali": (20.60, 87.00),
    "konark": (19.85, 86.12),
    "dhamara": (20.75, 87.05),
    # ── West Bengal
    "shankarpur": (21.60, 87.60),
    "junput": (21.66, 87.78),
    "kakdwip": (21.82, 88.20),
    "namkhana": (21.50, 88.20),
    "frasergunj": (21.53, 88.27),
    "diamond harbour": (22.15, 88.20),
    # ── Andaman & Nicobar
    "mayabunder": (12.93, 92.95),
    "rangat": (12.49, 92.99),
    "diglipur": (13.30, 93.10),
    "hutbay": (10.58, 92.62),
    "campbell bay": (6.9938, 93.9146),
    "kamorta": (8.05, 93.45),
    # ── Ocean regions ───────────────────────────────────────────────────
    "bay of bengal": (13.00, 82.00),
    "arabian sea": (12.00, 72.00),
    "indian ocean": (7.00, 76.00),
    "laccadive sea": (10.00, 74.00),
}

# ── P1.5 (`R-EDGE-4`) — Tamil-script keys ──────────────────────────────────
#
# A fully-Tamil query resolved NOTHING before this: only the Latin keys above
# matched, so "தூத்துக்குடியில் கடல் எப்படி இருக்கும்?" fell through to
# DEFAULT_LAT/LON and was answered at the Gulf of Mannar default. This will
# happen in the Tamil demo, which is why it is a Phase 1 point.
#
# HONEST GAP, the same standard distress.py holds its phrase lists to: these
# are the standard Tamil spellings of places whose English names are already
# in the table above, mapped onto the SAME coordinates — so a Tamil query and
# its English translation can never resolve to two different positions. They
# have NOT been reviewed by a native speaker; that review is P3.7's and these
# belong in it. Colloquial and dialect spellings are not covered.
_TAMIL_ALIASES: dict[str, str] = {
    "தூத்துக்குடி": "thoothukudi",
    "பாம்பன்": "pamban",
    "இராமேஸ்வரம்": "rameswaram",
    "ராமேஸ்வரம்": "rameswaram",
    "மண்டபம்": "mandapam",
    "தனுஷ்கோடி": "dhanushkodi",
    "திருச்செந்தூர்": "tiruchendur",
    "கன்னியாகுமரி": "kanyakumari",
    "குலசேகரப்பட்டினம்": "kulasekarapattinam",
    "கிளாக்கரை": "kilakarai",
    "வேம்பார்": "vembar",
    "நாகப்பட்டினம்": "nagapattinam",
    "கடலூர்": "cuddalore",
    "சென்னை": "chennai",
    "புதுச்சேரி": "puducherry",
    "காரைக்கால்": "karaikal",
    "வேளாங்கண்ணி": "velankanni",
    "எண்ணூர்": "ennore",
    "மாமல்லபுரம்": "mahabalipuram",
    "மன்னார் வளைகுடா": "gulf of mannar",
    "பாக் விரிகுடா": "palk bay",
    "பாக் ஜலசந்தி": "palk strait",
    "தமிழ்நாடு": "tamil nadu",
    "கொச்சி": "kochi",
    "மும்பை": "mumbai",
}

# Folded into the gazetteer rather than kept as a second lookup, so every
# consumer — resolve_place_from_text, resolve_all_places_from_text,
# places_within_region, the cache-refresh script that fetches every gazetteer
# coordinate — sees the Tamil keys without a second edit each.
_GAZETTEER.update(
    {tamil: _GAZETTEER[latin] for tamil, latin in _TAMIL_ALIASES.items() if latin in _GAZETTEER}
)
# Chennai, Kochi, Mumbai and Visakhapatnam have no gazetteer row — they are
# resolved from their own cached weather fixture instead — so their Tamil keys
# go where the Latin aliases already live, not into the table above.
_PORT_ALIASES.update(
    {tamil: latin for tamil, latin in _TAMIL_ALIASES.items() if latin not in _GAZETTEER}
)
# Latin spellings of a gazetteer place that machine translation produces
# (Bhashini renders Kannada/Hindi "ರಾಮೇಶ್ವರಂ"/"रामेश्वरम" as "Rameshwaram"),
# folded in the same way as the Tamil keys above.
_LATIN_VARIANTS = {"rameshwaram": "rameswaram"}
_GAZETTEER.update({v: _GAZETTEER[latin] for v, latin in _LATIN_VARIANTS.items()})


def resolve_place_from_text(text: str) -> ResolvedPlace | None:
    """First pilot-region place named in free text, or None if the text names
    no place we know. Deterministic case-insensitive **whole-word** matching
    over three tiers, most-specific first: a port with its own cached fixture,
    a tide-gauge station, then the hand-checked gazetteer above.

    Whole-word, not substring, because the all-India table is full of short
    names that are substrings of ordinary English and of each other — "goa"
    in "goal", "puri" in "purification", "okha", "vembar". Under the old
    substring rule those fire on text that names no place at all, and a false
    resolution is worse than None: None makes the caller say "name a place",
    a false one answers confidently about the wrong coast.

    Returning None is a real answer, not a failure: it means "this query
    names no location I can place", and the caller must say so rather than
    quietly answering about somewhere else.

    ponytail: first match wins if a query names more than one place (e.g.
    "compare Chennai and Pamban") — good enough for a single-location query,
    revisit with real multi-location handling if that becomes a real query shape.
    """
    lowered = text.lower()

    # Longest name first within each tier, so "gulf of mannar" wins over a bare
    # "mannar" and "palk strait" is never swallowed by "palk bay".
    for source, table in (
        ("gazetteer", _GAZETTEER),
        ("tide_station", tide_station_coordinates()),
    ):
        for name, (lat, lon) in sorted(table.items(), key=lambda kv: -len(kv[0])):
            if _names_place(lowered, name):
                canonical = _PORT_ALIASES.get(name, name)
                return ResolvedPlace(canonical, lat, lon, source)

    # Weather-fixture coordinates last: they are grid-cell snaps, accurate
    # enough to pick a cache file and not much more (see _GAZETTEER).
    coords = port_coordinates()
    for alias, port in _PORT_ALIASES.items():
        if _names_place(lowered, alias) and port in coords:
            lat, lon = coords[port]
            return ResolvedPlace(port, lat, lon, "port_fixture")
    for port, (lat, lon) in coords.items():
        if _names_place(lowered, port):
            return ResolvedPlace(port, lat, lon, "port_fixture")
    return None


def _names_place(lowered: str, name: str) -> bool:
    """Whole-word containment. Compiled per distinct name and cached, because
    resolve_place_from_text walks ~150 names on every query."""
    return _name_pattern(name).search(lowered) is not None


@lru_cache(maxsize=512)
def _name_pattern(name: str) -> re.Pattern[str]:
    """Whole-word for Latin names, prefix-anchored for everything else.

    English needs the trailing boundary: the all-India table is full of short
    names that are substrings of ordinary English ("goa" in "goal"). Tamil —
    and every other Indic script here — needs the opposite, because case is a
    suffix glued onto the noun: "தூத்துக்குடியில்" ("in Thoothukudi") is the
    normal way to say it and has no word boundary after the place name at all,
    so a trailing \\b would miss every inflected form, which is most of them."""
    if name.isascii():
        return re.compile(rf"\b{re.escape(name)}\b")
    # A Tamil noun ending in ம் drops it in every oblique form — Nagapattinam
    # is "நாகப்பட்டினம்" on its own and "நாகப்பட்டினத்தில்" in "at
    # Nagapattinam", which is how it is actually asked. Matching the stem with
    # the ம் optional catches both; the stem is long enough that nothing else
    # in the table can collide with it.
    stem = name.removesuffix("ம்")
    tail = "(?:ம்)?" if stem != name else ""
    return re.compile(rf"(?<!\w){re.escape(stem)}{tail}")


# A misspelt place name is the commonest way a real query names a place we
# hold and still resolves to nothing — "gujurat", "thootukudi", "porbander".
# Exact matching drops those straight to the pilot default, which answers a
# Gujarat question with Gulf of Mannar numbers. Near-misses are never resolved
# silently: the caller turns them into "did you mean Gujarat?", because a
# guessed place is the one output this module exists to prevent.
_FUZZY_CUTOFF = 0.82  # "gujurat" -> "gujarat" scores 0.857; unrelated words fall well below


@lru_cache(maxsize=1)
def _single_token_place_names() -> tuple[str, ...]:
    """Every one-word Latin-script name worth spell-checking against. Multi-word
    names ("gulf of mannar") are excluded — the match is per token."""
    names = set(_GAZETTEER) | set(tide_station_coordinates()) | set(port_coordinates()) | set(_PORT_ALIASES)
    return tuple(n for n in names if n.isascii() and len(n) >= 4 and " " not in n)


def near_miss_place_names(text: str, limit: int = 3) -> list[str]:
    """Names a token in `text` is probably a misspelling of. Only meaningful
    when exact resolution already found nothing."""
    known = _single_token_place_names()
    hits: list[str] = []
    for token in re.findall(r"[a-z]{4,}", text.lower()):
        for match in difflib.get_close_matches(token, known, n=1, cutoff=_FUZZY_CUTOFF):
            if match not in hits:
                hits.append(match)
    return hits[:limit]


# A curated, stable geographic fact (India's coastal states and UTs do not
# change), not a per-place hardcode: everything else in the Census list is
# landlocked. Found 2026-09-25 — "sea conditions near Delhi" matched nothing
# in `_GAZETTEER` and fell through to `resolve_or_ask`'s pilot-default
# fallback exactly like a query naming no place at all, so it was answered
# 1,400 km away with nothing on the card to say so beyond the model's own
# wording (when a model happened to run). Delhi is not a missing coastal
# port — it is a real, well-known place a caller might genuinely mean, that
# ORCA has no sea near. That is `unresolvable`, not `fallback`: see
# `inland_place_name` below and its use in `place_resolution.resolve_or_ask`.
_COASTAL_STATES: frozenset[str] = frozenset(
    {
        "andaman & nicobar island", "andhra pradesh", "daman & diu", "goa",
        "gujarat", "karnataka", "kerala", "lakshadweep", "maharashtra",
        "odisha", "puducherry", "tamil nadu", "west bengal",
    }
)
# District names that are compass directions rather than place names in their
# own right ("East", "North West" — several of NCT of Delhi's districts are
# named this way). A whole-word match on "west" would fire on ordinary marine
# wording ("wind from the west"), which is the one thing this check must
# never do.
_GENERIC_DIRECTIONS: frozenset[str] = frozenset({"north", "south", "east", "west", "central"})


@lru_cache(maxsize=1)
def _inland_place_names() -> tuple[str, ...]:
    """State and district names from the Census 2011 shapefile
    (`tier1/boundaries/2011_Dist.shp`, already on disk for
    `geospatial.district_at_point` — read again here rather than imported,
    because `place_resolution` is deliberately import-light and this file
    must not pull in shapely/pyshp's geometry machinery for a name list).
    Landlocked states and UTs only, and their districts; a coastal state's
    own inland districts (Coimbatore in Tamil Nadu) are out of scope — this
    answers "does the text name a whole landlocked region", not "how far is
    this district from the coast". Longest names first, same order
    `resolve_all_places_from_text` claims spans in, so "new delhi" is not
    also reported as the generic-and-excluded "delhi" some other district
    happened to be named (it is not, here, but the ordering rule is shared).
    """
    path = DATA_DIR / "tier1" / "boundaries" / "2011_Dist.shp"
    if not path.exists():
        return ()
    import shapefile  # pyshp: pure-python .shp/.dbf reader, no GDAL

    reader = shapefile.Reader(str(path))
    names: set[str] = set()
    for sr in reader.shapeRecords():
        record = sr.record
        if record is None:
            continue
        raw_state = record["ST_NM"]
        state = str(raw_state).strip() if raw_state is not None else ""
        if not state or state.lower() in _COASTAL_STATES:
            continue
        raw_district = record["DISTRICT"]
        district = str(raw_district).strip() if raw_district is not None else ""
        if district and district.lower() not in _GENERIC_DIRECTIONS:
            names.add(district.lower())
        # "NCT of Delhi" -> "Delhi": the one general cleanup this needs. The
        # ST_NM column carries the administrative prefix; nobody asks about
        # sea conditions near "NCT of Delhi".
        names.add(state.removeprefix("NCT of ").strip().lower())
    # Lowercase, matching `_GAZETTEER`'s own convention (`_name_pattern` is
    # case-sensitive by construction, so a title-cased table would silently
    # never match `resolve_or_ask`'s already-lowercased query text).
    return tuple(sorted({n for n in names if len(n) >= 4}, key=len, reverse=True))


def inland_place_name(text: str) -> str | None:
    """The first landlocked state or district `text` names, title-cased for
    display, or None.

    Meaningful only after the coastal gazetteer/tide-station/port tables
    already matched nothing (see `resolve_or_ask`) — a name that resolves
    there never reaches this check, so there is no double match to arbitrate.
    """
    lowered = text.lower()
    for name in _inland_place_names():
        if _name_pattern(name).search(lowered):
            return name.title()
    return None


# Gazetteer keys that name a *region*, not a position. A state's coastline is
# 300-600 km long and the entry below is its centroid, so answering "is it safe
# in Kerala?" at one of these is the same confidently-wrong failure the
# all-India table was added to fix, one level up: the numbers would be real,
# they would just belong to a stretch of sea the asker may be 400 km from.
# Several are not even wet — Kerala's (10.50, 76.00) is inland.
#
# The named gulfs, bays and straits are deliberately NOT here: Palk Bay and the
# Gulf of Mannar are fishing grounds small enough that one position genuinely
# represents them, which is why the pilot region answers at them.
_REGION_KEYS: frozenset[str] = frozenset(
    {
        "tamil nadu", "kerala", "karnataka", "goa", "maharashtra", "gujarat",
        "andhra pradesh", "odisha", "west bengal", "andaman", "nicobar",
        "lakshadweep", "bay of bengal", "arabian sea", "indian ocean",
        "laccadive sea", "andaman sea",
    }
    | {f"{s} coast" for s in ("tamil nadu", "kerala", "karnataka", "goa", "maharashtra", "gujarat", "odisha", "west bengal", "andaman")}
    | {"andhra coast", "தமிழ்நாடு"}  # the Tamil key for the state is a region too (P1.5)
)


def is_region_name(name: str) -> bool:
    """True when `name` is a whole coastline or ocean basin rather than a place
    a vessel can be at. `resolve_or_ask` turns these into a "which of these?"
    instead of an answer (P1.2/P1.4)."""
    return name.lower() in _REGION_KEYS


def places_within_region(name: str, limit: int = 4) -> list[ResolvedPlace]:
    """The specific gazetteer places closest to a region's own centroid — the
    candidate list a region query is answered with. Derived from the table
    rather than hand-grouped, so adding a port to `_GAZETTEER` cannot leave a
    second list out of step with it."""
    here = _GAZETTEER.get(name.lower())
    if here is None:
        return []
    # First name per coordinate only — the table carries aliases ("kozhikode"
    # and "calicut" are one port), and offering both as separate choices is
    # not a choice.
    by_coord: dict[tuple[float, float], ResolvedPlace] = {}
    for n, (la, lo) in _GAZETTEER.items():
        if not is_region_name(n):
            by_coord.setdefault((la, lo), ResolvedPlace(n, la, lo, "gazetteer"))
    specific = sorted(by_coord.values(), key=lambda p: (p.lat - here[0]) ** 2 + (p.lon - here[1]) ** 2)
    return specific[:limit]


def resolve_all_places_from_text(text: str) -> list[ResolvedPlace]:
    """Every distinct place the text names, most-specific first — the input to
    the "you named two places, which did you mean?" guard (P1.4).

    Matches are claimed by span so a longer name swallows the shorter names
    inside it: "tamil nadu coast" is one place, not also "tamil nadu", and
    "gulf of mannar" is never additionally reported as some other row that
    happens to sit inside the same words.
    """
    lowered = text.lower()
    claimed: list[tuple[int, int]] = []
    found: list[ResolvedPlace] = []
    seen: set[tuple[float, float]] = set()

    def _take(name: str, lat: float, lon: float, source: str) -> None:
        m = _name_pattern(name).search(lowered)
        if m is None or any(m.start() < e and s < m.end() for s, e in claimed):
            return
        claimed.append((m.start(), m.end()))
        if (lat, lon) not in seen:
            seen.add((lat, lon))
            found.append(ResolvedPlace(name, lat, lon, source))

    for source, table in (("gazetteer", _GAZETTEER), ("tide_station", tide_station_coordinates())):
        for name, (lat, lon) in sorted(table.items(), key=lambda kv: -len(kv[0])):
            _take(name, lat, lon, source)

    coords = port_coordinates()
    for alias, port in sorted(_PORT_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if port in coords:
            _take(alias, *coords[port], "port_fixture")
    for port, (lat, lon) in sorted(coords.items(), key=lambda kv: -len(kv[0])):
        _take(port, lat, lon, "port_fixture")

    return found
