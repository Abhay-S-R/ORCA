"""Fishing Zone Profit Engine — pre-calculation module.

Implements the algorithm described in the fishing_zone_profit_implementation_plan.md:
  - Catch share estimation (section 5)
  - Profit calculation per port × zone × vessel type (section 6)
  - Colour classification by margin (section 7)
  - Home-port zone filtering (section 8)
  - Vessel-type behaviour (section 9)

All monetary values are estimates and are labelled as such in the API response.
Numbers are pre-calculated; the API route only reads and returns them.
"""
from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

# ---------------------------------------------------------------------------
# Constants (plan §4.6 / §6)
# ---------------------------------------------------------------------------

DIESEL_PRICE_INR_PER_LITRE = 95.0
PROFIT_RANGE_FACTOR = 0.15  # ±15% for the low/high range band
TOP_N_SPECIES_PER_ZONE = 8  # plan §5, keep top 8 by CMFRI tonnes

# Base fuel burn rates in litres per hour (L/h) at 8-knot reference cruise speed.
# Exactly matches backend/orca/agents/voyage.py and frontend/app/voyage/page.tsx.
BASE_FUEL_BURN_LPH: dict[str, float] = {
    "small_fishing": 4.5,
    "mechanized_trawler": 22.0,
    "cargo_vessel": 110.0,
}

DEFAULT_CRUISE_SPEED_KN = 8.0
KM_PER_NM = 1.852


def calculate_fuel_burn_rate(vessel_key: str, speed_kn: float = DEFAULT_CRUISE_SPEED_KN) -> float:
    """Automatic maritime fuel burn rate formula based on vessel class and cruising speed.
    Identical to the voyage planner formula in backend/orca/agents/voyage.py.
    Power / consumption scales quadratically with speed relative to 8-knot cruise reference.
    """
    base_rate = BASE_FUEL_BURN_LPH.get(vessel_key, 4.5)
    s = max(speed_kn, 1.0)
    return round(base_rate * ((s / 8.0) ** 2), 2)


def calculate_fuel_consumption(
    distance_km: float,
    vessel_key: str,
    speed_kn: float = DEFAULT_CRUISE_SPEED_KN,
    fuel_burn_lph: float | None = None,
    round_trip: bool = True,
) -> tuple[float, float, float]:
    """Calculate fuel consumption using the Sagar Sarathi voyage formula.

    Returns:
        (fuel_liters, effective_fuel_burn_lph, round_trip_nm)

    Formula (matches backend/orca/agents/voyage.py):
        total_distance_nm = (distance_km * 2) / 1.852
        steaming_hours = total_distance_nm / speed_kn
        fuel_liters = steaming_hours * fuel_burn_lph
    """
    total_km = distance_km * (2.0 if round_trip else 1.0)
    total_nm = total_km / KM_PER_NM
    s = max(speed_kn, 0.1)
    if fuel_burn_lph is None or fuel_burn_lph <= 0:
        eff_burn_lph = calculate_fuel_burn_rate(vessel_key, s)
    else:
        eff_burn_lph = fuel_burn_lph

    fuel_liters = round((total_nm / s) * eff_burn_lph, 1)
    return fuel_liters, eff_burn_lph, round(total_nm, 1)


# Vessel profiles (plan §4.6). Keys match the DB vessel_class enum values
# PLUS the risk engine's canonical names.
VESSEL_PROFILES: dict[str, dict] = {
    # DB enum: "mechanised" | "catamaran" | "fibreglass" — all treated as small
    "small_fishing": {
        "label": "Small fishing boat",
        "base_fuel_burn_lph": 4.5,
        "fuel_lph": 0.5,          # legacy fallback
        "fixed_cost_inr": 6_000,  # per trip (crew, ice, food, port fees)
        "base_catch_kg": 250,
        "show_profit": True,
    },
    "mechanized_trawler": {
        "label": "Mechanized trawler",
        "base_fuel_burn_lph": 22.0,
        "fuel_lph": 3.0,
        "fixed_cost_inr": 25_000,
        "base_catch_kg": 750,
        "show_profit": True,
    },
    "cargo_vessel": {
        "label": "Cargo vessel",
        "base_fuel_burn_lph": 110.0,
        "fuel_lph": 10.0,
        "fixed_cost_inr": 0,
        "base_catch_kg": 0,
        "show_profit": False,
    },
}

# Map DB vessel_class enum values → profit engine key
DB_VESSEL_TO_PROFIT_KEY: dict[str, str] = {
    "catamaran":   "small_fishing",
    "fibreglass":  "small_fishing",
    "mechanised":  "small_fishing",
    "trawler":     "mechanized_trawler",
    "cargo":       "cargo_vessel",
    # Risk engine canonical names (already correct)
    "small_fishing":        "small_fishing",
    "mechanized_trawler":   "mechanized_trawler",
    "cargo_vessel":         "cargo_vessel",
}

# Colour thresholds (plan §7, margin-based)
MARGIN_HIGH = 50.0   # ≥50% → green
MARGIN_MED  = 25.0   # 25–50% → orange
# <25% → red

# ---------------------------------------------------------------------------
# Data file paths
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

SPECIES_PRICES_CSV = os.path.join(DATA_DIR, "fish_price", "final_species_with_prices.csv")

# ---------------------------------------------------------------------------
# Pre-defined Ports (plan §4.1)
# ---------------------------------------------------------------------------

PORTS: list[dict] = [
    {"port_id": "kochi",       "port_name": "Kochi",       "state": "Kerala",     "lat": 9.9312,  "lon": 76.2673},
    {"port_id": "kozhikode",   "port_name": "Kozhikode",   "state": "Kerala",     "lat": 11.2588, "lon": 75.7804},
    {"port_id": "thiruvananthapuram", "port_name": "Thiruvananthapuram", "state": "Kerala", "lat": 8.5241, "lon": 76.9366},
    {"port_id": "mangaluru",   "port_name": "Mangaluru",   "state": "Karnataka",  "lat": 12.8698, "lon": 74.8430},
    {"port_id": "karwar",      "port_name": "Karwar",      "state": "Karnataka",  "lat": 14.8137, "lon": 74.1303},
    {"port_id": "chennai",     "port_name": "Chennai",     "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707},
    {"port_id": "tuticorin",   "port_name": "Tuticorin",   "state": "Tamil Nadu", "lat": 8.7642,  "lon": 78.1348},
    {"port_id": "mumbai",      "port_name": "Mumbai",      "state": "Maharashtra","lat": 18.9388, "lon": 72.8354},
    {"port_id": "veraval",     "port_name": "Veraval",     "state": "Gujarat",    "lat": 20.9072, "lon": 70.3673},
    {"port_id": "paradip",     "port_name": "Paradip",     "state": "Odisha",     "lat": 20.3170, "lon": 86.6093},
    {"port_id": "visakhapatnam","port_name":"Visakhapatnam","state": "Andhra Pradesh","lat": 17.6868,"lon": 83.2185},
]

# ---------------------------------------------------------------------------
# Pre-defined Fishing Zones (plan §4.2)
# Each zone is associated with one state. Zones include the species aphia_ids
# that are most commonly observed/landed in that coastal region.
# ---------------------------------------------------------------------------

# We define zones for each state with realistic coordinates and species mixes.
# Species are selected from the priced species list based on CMFRI landings
# and regional fishing patterns.

ZONES: list[dict] = [
    # ----- KERALA -----
    {
        "zone_id":    "kerala-z1",
        "zone_name":  "Kochi Nearshore",
        "state":      "Kerala",
        "zone_type":  "nearshore",
        "lat": 9.80, "lon": 76.20,
        "description": "Coastal waters near Kochi; sardine, mackerel and squid dominant",
        # Verified aphia_ids: Indian mackerel, Oil sardine, Ribbonfish, Lesser sardines,
        # Bombayduck, Threadfin breams, Scads, Lizard fishes
        "species_aphia_ids": [127020, 212269, 127089, 272269, 217661, 218515, 218427, 217663],
    },
    {
        "zone_id":    "kerala-z2",
        "zone_name":  "Kochi Offshore",
        "state":      "Kerala",
        "zone_type":  "offshore",
        "lat": 9.50, "lon": 75.80,
        "description": "Offshore trawling grounds; tuna, seer fish and ribbonfish",
        # Yellowfin tuna, Indian mackerel, Scomberomorus commerson, Ribbonfish,
        # Auxis, Katsuwonus, Silverbellies, Silver pomfret
        "species_aphia_ids": [127027, 127020, 127024, 127089, 126057, 127018, 398536, 127075],
    },
    {
        "zone_id":    "kerala-z3",
        "zone_name":  "Kozhikode Banks",
        "state":      "Kerala",
        "zone_type":  "offshore",
        "lat": 11.30, "lon": 75.40,
        "description": "Rich sardine and mackerel grounds off Kozhikode",
        # Indian mackerel, Oil sardine, Ribbonfish, Scads, Threadfin breams,
        # Euthynnus affinis, Croakers, Horse mackerel
        "species_aphia_ids": [127020, 212269, 127089, 218427, 218515, 219708, 276103, 218430],
    },
    {
        "zone_id":    "kerala-z4",
        "zone_name":  "Trivandrum Deep",
        "state":      "Kerala",
        "zone_type":  "deep_sea",
        "lat": 8.20, "lon": 76.20,
        "description": "Deep-sea zone with tuna, seer and high-value species",
        # Yellowfin tuna, Scomberomorus commerson, Katsuwonus, Auxis,
        # Bill fishes, Rock cods, Barracudas, Sharks
        "species_aphia_ids": [127027, 127024, 127018, 126057, 158812, 218200, 345843, 105793],
    },
    {
        "zone_id":    "kerala-z5",
        "zone_name":  "Lakshadweep Approach",
        "state":      "Kerala",
        "zone_type":  "deep_sea",
        "lat": 10.50, "lon": 74.80,
        "description": "Productive deep-sea zone approaching Lakshadweep; tuna dominant",
        # Yellowfin tuna, Katsuwonus, Auxis, Scomberomorus commerson,
        # Bill fishes, Acanthocybium, Euthynnus affinis, Rock cods
        "species_aphia_ids": [127027, 127018, 126057, 127024, 158812, 127014, 219708, 218200],
    },

    # ----- KARNATAKA -----
    {
        "zone_id":    "karnataka-z1",
        "zone_name":  "Mangaluru Coast",
        "state":      "Karnataka",
        "zone_type":  "nearshore",
        "lat": 12.70, "lon": 74.40,
        "description": "Nearshore Mangaluru zone with pomfret and seer fish",
        # Indian mackerel, Silver pomfret, Scomberomorus commerson, Ribbonfish,
        # Oil sardine, Threadfin breams, Croakers, Catfishes
        "species_aphia_ids": [127020, 127075, 127024, 127089, 212269, 218515, 276103, 275569],
    },
    {
        "zone_id":    "karnataka-z2",
        "zone_name":  "Karwar Banks",
        "state":      "Karnataka",
        "zone_type":  "offshore",
        "lat": 14.60, "lon": 73.80,
        "description": "Offshore Karwar banks; diverse pelagic species",
        # Yellowfin tuna, Indian mackerel, Ribbonfish, Oil sardine,
        # Scads, Scomberomorus commerson, Euthynnus affinis, Auxis
        "species_aphia_ids": [127027, 127020, 127089, 212269, 218427, 127024, 219708, 126057],
    },

    # ----- TAMIL NADU -----
    {
        "zone_id":    "tamilnadu-z1",
        "zone_name":  "Chennai Nearshore",
        "state":      "Tamil Nadu",
        "zone_type":  "nearshore",
        "lat": 13.00, "lon": 80.40,
        "description": "High-traffic near-shore zone off Chennai; mixed demersal",
        # Indian mackerel, Ribbonfish, Threadfin breams, Croakers,
        # Lizard fishes, Catfishes, Soles, Snappers
        "species_aphia_ids": [127020, 127089, 218515, 276103, 217663, 275569, 274211, 218496],
    },
    {
        "zone_id":    "tamilnadu-z2",
        "zone_name":  "Palk Bay",
        "state":      "Tamil Nadu",
        "zone_type":  "nearshore",
        "lat": 9.50, "lon": 79.20,
        "description": "Shallow Palk Bay; squid, rays and diverse reef fish",
        # Threadfin breams, Silverbellies, Croakers, Rock cods,
        # Rays, Snappers, Pig-face breams, Soles
        "species_aphia_ids": [218515, 398536, 276103, 218200, 105854, 218496, 212081, 274211],
    },
    {
        "zone_id":    "tamilnadu-z3",
        "zone_name":  "Gulf of Mannar",
        "state":      "Tamil Nadu",
        "zone_type":  "offshore",
        "lat": 8.50, "lon": 78.30,
        "description": "Protected marine park adjacent zone; reef fish and tuna",
        # Yellowfin tuna, Scomberomorus commerson, Rock cods, Snappers,
        # Pig-face breams, Bill fishes, Barracudas, Euthynnus affinis
        "species_aphia_ids": [127027, 127024, 218200, 218496, 212081, 158812, 345843, 219708],
    },

    # ----- MAHARASHTRA -----
    {
        "zone_id":    "maharashtra-z1",
        "zone_name":  "Mumbai Offshore",
        "state":      "Maharashtra",
        "zone_type":  "offshore",
        "lat": 18.50, "lon": 72.20,
        "description": "High-volume Bombay duck and mackerel zone",
        # Bombayduck, Indian mackerel, Ribbonfish, Oil sardine,
        # Silver pomfret, Scads, Croakers, Catfishes
        "species_aphia_ids": [217661, 127020, 127089, 212269, 127075, 218427, 276103, 275569],
    },
    {
        "zone_id":    "maharashtra-z2",
        "zone_name":  "Ratnagiri Banks",
        "state":      "Maharashtra",
        "zone_type":  "offshore",
        "lat": 16.80, "lon": 72.80,
        "description": "Pomfret and seer fish grounds off Ratnagiri",
        # Silver pomfret, Scomberomorus commerson, Indian mackerel, Ribbonfish,
        # Bombayduck, Yellowfin tuna, Scads, Leather-jackets
        "species_aphia_ids": [127075, 127024, 127020, 127089, 217661, 127027, 218427, 218432],
    },

    # ----- GUJARAT -----
    {
        "zone_id":    "gujarat-z1",
        "zone_name":  "Saurashtra Banks",
        "state":      "Gujarat",
        "zone_type":  "offshore",
        "lat": 21.20, "lon": 69.80,
        "description": "Rich demersal grounds off Saurashtra; pomfret and sharks",
        # Silver pomfret, Indian mackerel, Ribbonfish, Sharks,
        # Rays, Catfishes, Croakers, Lizard fishes
        "species_aphia_ids": [127075, 127020, 127089, 105793, 105854, 275569, 276103, 217663],
    },
    {
        "zone_id":    "gujarat-z2",
        "zone_name":  "Gulf of Kutch",
        "state":      "Gujarat",
        "zone_type":  "nearshore",
        "lat": 22.80, "lon": 69.50,
        "description": "Tidal creek fishery with mullets, hilsa and croakers",
        # Hilsa shad, Mullets, Catfishes, Croakers, Eels,
        # Silverbellies, Setipinna, Thryssa
        "species_aphia_ids": [278568, 126983, 275569, 276103, 217456, 398536, 282768, 275559],
    },

    # ----- ODISHA -----
    {
        "zone_id":    "odisha-z1",
        "zone_name":  "Paradip Offshore",
        "state":      "Odisha",
        "zone_type":  "offshore",
        "lat": 20.10, "lon": 87.00,
        "description": "Offshore Bay of Bengal; ribbonfish, hilsa and mixed demersal",
        # Ribbonfish, Hilsa shad, Indian mackerel, Threadfin breams,
        # Croakers, Silverbellies, Bombayduck, Catfishes
        "species_aphia_ids": [127089, 278568, 127020, 218515, 276103, 398536, 217661, 275569],
    },

    # ----- ANDHRA PRADESH -----
    {
        "zone_id":    "andhra-z1",
        "zone_name":  "Visakhapatnam Bay",
        "state":      "Andhra Pradesh",
        "zone_type":  "nearshore",
        "lat": 17.50, "lon": 83.50,
        "description": "Bay of Bengal coast with mixed commercial species",
        # Indian mackerel, Ribbonfish, Threadfin breams, Croakers,
        # Lizard fishes, Silverbellies, Scads, Catfishes
        "species_aphia_ids": [127020, 127089, 218515, 276103, 217663, 398536, 218427, 275569],
    },
    {
        "zone_id":    "andhra-z2",
        "zone_name":  "Krishna-Godavari Estuary",
        "state":      "Andhra Pradesh",
        "zone_type":  "nearshore",
        "lat": 16.20, "lon": 81.80,
        "description": "Estuarine and nearshore fishery; hilsa, mullets and catfishes",
        # Hilsa shad, Mullets, Setipinna, Thryssa, Eels,
        # Catfishes, Croakers, Silverbellies
        "species_aphia_ids": [278568, 126983, 282768, 275559, 217456, 275569, 276103, 398536],
    },
]

# Straight-line distance table: port_id → zone_id → km.
# Built dynamically from lat/lon below; no manual entry required.

# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_priced_species() -> list[dict]:
    """Load and return all species with has_price=True from the master CSV."""
    species: list[dict] = []
    if not os.path.exists(SPECIES_PRICES_CSV):
        return species
    with open(SPECIES_PRICES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("has_price", "").strip().lower() == "true":
                try:
                    aphia_id = int(float(row["aphia_id"]))
                    cmfri_tonnes = float(row["cmfri_tonnes"]) if row.get("cmfri_tonnes") else 0.0
                    price_low  = float(row["price_low_inr_per_kg"]) if row.get("price_low_inr_per_kg") else 0.0
                    price_high = float(row["price_high_inr_per_kg"]) if row.get("price_high_inr_per_kg") else 0.0
                    price_mid  = float(row["price_mid_inr_per_kg"]) if row.get("price_mid_inr_per_kg") else 0.0
                    species.append({
                        "aphia_id":     aphia_id,
                        "scientific_name": row.get("scientific_name", ""),
                        "common_name":  row.get("common_name", "") or row.get("scientific_name", ""),
                        "cmfri_tonnes": cmfri_tonnes,
                        "price_low":    price_low,
                        "price_high":   price_high,
                        "price_mid":    price_mid,
                        "category":     row.get("category", ""),
                        "price_confidence": row.get("price_confidence", ""),
                    })
                except (ValueError, KeyError):
                    continue
    # Index by aphia_id for fast lookup
    return species


@lru_cache(maxsize=1)
def species_index() -> dict[int, dict]:
    return {s["aphia_id"]: s for s in load_priced_species()}


# ---------------------------------------------------------------------------
# Distance calculation (straight-line, plan §4.5)
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def port_zone_distance_km(port: dict, zone: dict) -> float:
    return _haversine_km(port["lat"], port["lon"], zone["lat"], zone["lon"])


# ---------------------------------------------------------------------------
# Catch-share estimation (plan §5)
# ---------------------------------------------------------------------------

def compute_catch_shares(zone_species_ids: list[int]) -> list[dict]:
    """Return share dicts for the top-N priced species in a zone,
    sorted by CMFRI tonnes (largest first)."""
    idx = species_index()
    present = [idx[aid] for aid in zone_species_ids if aid in idx]
    # Sort by CMFRI tonnes descending, keep top N
    present.sort(key=lambda s: s["cmfri_tonnes"], reverse=True)
    top = present[:TOP_N_SPECIES_PER_ZONE]
    total_tonnes = sum(s["cmfri_tonnes"] for s in top)
    if total_tonnes == 0:
        return []
    shares = []
    for sp in top:
        share = sp["cmfri_tonnes"] / total_tonnes
        shares.append({**sp, "share": share})
    return shares


# ---------------------------------------------------------------------------
# Profit calculation (plan §6)
# ---------------------------------------------------------------------------

def _round_500(value: float) -> int:
    """Round to nearest ₹500."""
    return int(round(value / 500) * 500)


def calculate_profit(
    port: dict,
    zone: dict,
    vessel_key: str,
    speed_kn: float = DEFAULT_CRUISE_SPEED_KN,
    fuel_burn_lph: float | None = None,
) -> dict:
    """Calculate profit estimate for one port × zone × vessel combination.

    Returns a dict with all the data the front-end needs.
    plan §6 steps 1–8, using the Sagar Sarathi voyage fuel formula.
    """
    profile = VESSEL_PROFILES[vessel_key]
    distance_km = port_zone_distance_km(port, zone)

    # Step 4: Fuel cost using voyage formula (round trip)
    fuel_liters, eff_burn_lph, round_trip_nm = calculate_fuel_consumption(
        distance_km=distance_km,
        vessel_key=vessel_key,
        speed_kn=speed_kn,
        fuel_burn_lph=fuel_burn_lph,
        round_trip=True,
    )
    fuel_cost = fuel_liters * DIESEL_PRICE_INR_PER_LITRE

    # Step 5: Total cost
    total_cost = fuel_cost + profile["fixed_cost_inr"]

    # Cargo vessels don't fish
    if not profile["show_profit"]:
        cargo_species = []
        for sp in compute_catch_shares(zone["species_aphia_ids"]):
            cargo_species.append({
                "aphia_id":        sp["aphia_id"],
                "common_name":     sp["common_name"],
                "scientific_name": sp["scientific_name"],
                "share_pct":       round(sp["share"] * 100, 1),
                "est_kg":          0.0,
                "price_low":       sp["price_low"],
                "price_high":      sp["price_high"],
                "price_mid":       sp["price_mid"],
                "income_mid":      0,
            })
        return {
            "zone_id":          zone["zone_id"],
            "zone_name":        zone["zone_name"],
            "zone_type":        zone["zone_type"],
            "state":            zone["state"],
            "lat":              zone["lat"],
            "lon":              zone["lon"],
            "distance_km":      round(distance_km, 1),
            "vessel_key":       vessel_key,
            "vessel_label":     profile["label"],
            "show_profit":      False,
            "priced_species":   cargo_species,
            "income_low":       None,
            "income_high":      None,
            "profit_low":       None,
            "profit_high":      None,
            "profit_mid":       None,
            "margin_pct":       None,
            "profit_label":     "cargo",
            "profit_color":     "neutral",
            "fuel_cost":        round(fuel_cost),
            "fuel_liters":      round(fuel_liters, 1),
            "fuel_burn_lph":    round(eff_burn_lph, 2),
            "round_trip_nm":    round_trip_nm,
            "total_cost":       round(total_cost),
            "sort_rank":        999,
            "limited_data":     False,
            "zone_description": zone.get("description", ""),
        }

    shares = compute_catch_shares(zone["species_aphia_ids"])

    # Steps 1–3: Income per fish, total income
    base_catch = profile["base_catch_kg"]
    species_rows = []
    total_income_low  = 0.0
    total_income_high = 0.0
    total_income_mid  = 0.0

    for sp in shares:
        kg = base_catch * sp["share"]
        inc_low  = kg * sp["price_low"]
        inc_high = kg * sp["price_high"]
        inc_mid  = kg * sp["price_mid"]
        total_income_low  += inc_low
        total_income_high += inc_high
        total_income_mid  += inc_mid
        species_rows.append({
            "aphia_id":        sp["aphia_id"],
            "common_name":     sp["common_name"],
            "scientific_name": sp["scientific_name"],
            "share_pct":       round(sp["share"] * 100, 1),
            "est_kg":          round(kg, 1),
            "price_low":       sp["price_low"],
            "price_high":      sp["price_high"],
            "price_mid":       sp["price_mid"],
            "income_mid":      round(inc_mid),
        })

    # Step 6: Profit
    profit_low  = total_income_low  - total_cost
    profit_high = total_income_high - total_cost
    profit_mid  = total_income_mid  - total_cost

    # Step 7: Margin (using mid prices)
    margin_pct = (profit_mid / total_income_mid * 100) if total_income_mid > 0 else 0.0

    # Step 8: Round to nearest ₹500
    profit_low_r  = _round_500(profit_low)
    profit_high_r = _round_500(profit_high)

    # plan §7: colour label
    if margin_pct >= MARGIN_HIGH:
        profit_label = "High profit"
        profit_color = "green"
    elif margin_pct >= MARGIN_MED:
        profit_label = "Medium profit"
        profit_color = "orange"
    else:
        profit_label = "Low profit"
        profit_color = "red"

    limited_data = len(shares) < 3

    return {
        "zone_id":          zone["zone_id"],
        "zone_name":        zone["zone_name"],
        "zone_type":        zone["zone_type"],
        "state":            zone["state"],
        "lat":              zone["lat"],
        "lon":              zone["lon"],
        "distance_km":      round(distance_km, 1),
        "vessel_key":       vessel_key,
        "vessel_label":     profile["label"],
        "show_profit":      True,
        "priced_species":   species_rows,
        "income_low":       _round_500(total_income_low),
        "income_high":      _round_500(total_income_high),
        "income_mid":       round(total_income_mid),
        "profit_low":       profit_low_r,
        "profit_high":      profit_high_r,
        "profit_mid":       round(profit_mid),
        "margin_pct":       round(margin_pct, 1),
        "profit_label":     profit_label,
        "profit_color":     profit_color,
        "fuel_cost":        round(fuel_cost),
        "fuel_liters":      round(fuel_liters, 1),
        "fuel_burn_lph":    round(eff_burn_lph, 2),
        "round_trip_nm":    round_trip_nm,
        "fixed_cost":       profile["fixed_cost_inr"],
        "total_cost":       round(total_cost),
        "sort_rank":        round(-profit_mid),   # negative so highest profit = lowest rank
        "limited_data":     limited_data,
        "zone_description": zone.get("description", ""),
    }


# ---------------------------------------------------------------------------
# Zone cache (pre-calculated)
# ---------------------------------------------------------------------------

# Module-level cache: {(port_id, vessel_key): [zone_result, ...]}
_ZONE_CACHE: dict[tuple[str, str], list[dict]] = {}
_CACHE_BUILT = False


def _build_cache() -> None:
    """Pre-calculate all port × vessel combinations. Called once on startup."""
    global _CACHE_BUILT
    if _CACHE_BUILT:
        return
    ports_by_id  = {p["port_id"]: p for p in PORTS}
    zones_by_state: dict[str, list[dict]] = {}
    for zone in ZONES:
        zones_by_state.setdefault(zone["state"], []).append(zone)

    for port in PORTS:
        state_zones = zones_by_state.get(port["state"], [])
        for vessel_key in VESSEL_PROFILES:
            results = [
                calculate_profit(port, zone, vessel_key, speed_kn=DEFAULT_CRUISE_SPEED_KN, fuel_burn_lph=None)
                for zone in state_zones
            ]
            # Sort by profit descending (cargo: by distance ascending)
            if VESSEL_PROFILES[vessel_key]["show_profit"]:
                results.sort(key=lambda r: -(r.get("profit_mid") or 0))
            else:
                results.sort(key=lambda r: r["distance_km"])
            _ZONE_CACHE[(port["port_id"], vessel_key)] = results

    _CACHE_BUILT = True


def get_zone_profits(
    port_lat: float,
    port_lon: float,
    vessel_key: str,
    port_name: str | None = None,
    speed_kn: float | None = None,
    fuel_burn_lph: float | None = None,
) -> dict[str, Any]:
    """Main entry point for the API.

    Finds the nearest known port to the supplied lat/lon,
    returns zone profit data for that port and the supplied vessel_key.
    Uses the voyage fuel consumption formula based on vessel class and cruise speed.

    Returns a dict ready to be serialised as JSON.
    """
    _build_cache()

    # Resolve nearest known port
    best_port = min(
        PORTS,
        key=lambda p: _haversine_km(port_lat, port_lon, p["lat"], p["lon"]),
    )
    nearest_km = _haversine_km(port_lat, port_lon, best_port["lat"], best_port["lon"])

    # Normalise vessel_key
    normalised_vessel = DB_VESSEL_TO_PROFIT_KEY.get(vessel_key, "small_fishing")
    fallback_message: str | None = None

    if vessel_key and vessel_key not in DB_VESSEL_TO_PROFIT_KEY:
        # Unknown vessel key → default to small fishing
        normalised_vessel = "small_fishing"
        fallback_message = "Vessel type not recognised — showing estimates for the small fishing boat."
    elif not vessel_key:
        fallback_message = "Vessel not set — showing estimates for the small fishing boat."

    # Custom speed or fuel burn rate: compute dynamically
    has_custom_speed = speed_kn is not None and abs(speed_kn - DEFAULT_CRUISE_SPEED_KN) > 0.01
    has_custom_burn = fuel_burn_lph is not None and fuel_burn_lph > 0

    if has_custom_speed or has_custom_burn:
        eff_speed = speed_kn if speed_kn is not None else DEFAULT_CRUISE_SPEED_KN
        zones_by_state: dict[str, list[dict]] = {}
        for zone in ZONES:
            zones_by_state.setdefault(zone["state"], []).append(zone)
        state_zones = zones_by_state.get(best_port["state"], [])
        zones = [
            calculate_profit(best_port, z, normalised_vessel, speed_kn=eff_speed, fuel_burn_lph=fuel_burn_lph)
            for z in state_zones
        ]
        if VESSEL_PROFILES[normalised_vessel]["show_profit"]:
            zones.sort(key=lambda r: -(r.get("profit_mid") or 0))
        else:
            zones.sort(key=lambda r: r["distance_km"])
    else:
        cached = _ZONE_CACHE.get((best_port["port_id"], normalised_vessel), [])
        zones = [dict(z) for z in cached]

    # Mark "Best zone" badge (plan §10.2)
    for i, z in enumerate(zones):
        z = dict(z)
        z["is_best_zone"] = (i == 0 and z.get("show_profit") and (z.get("profit_mid") or 0) > 0)
        zones[i] = z

    vessel_profile = VESSEL_PROFILES[normalised_vessel]
    eff_speed = speed_kn if speed_kn is not None else DEFAULT_CRUISE_SPEED_KN
    eff_burn = fuel_burn_lph if fuel_burn_lph is not None else calculate_fuel_burn_rate(normalised_vessel, eff_speed)

    return {
        "port_id":          best_port["port_id"],
        "port_name":        best_port["port_name"],
        "port_state":       best_port["state"],
        "port_lat":         best_port["lat"],
        "port_lon":         best_port["lon"],
        "supplied_lat":     port_lat,
        "supplied_lon":     port_lon,
        "nearest_port_km":  round(nearest_km, 1),
        "vessel_key":       normalised_vessel,
        "vessel_label":     vessel_profile["label"],
        "show_profit":      vessel_profile["show_profit"],
        "fallback_message": fallback_message,
        "zones":            zones,
        "speed_kn":         eff_speed,
        "fuel_burn_lph":    round(eff_burn, 2),
        "diesel_price_inr": DIESEL_PRICE_INR_PER_LITRE,
        "disclaimer":       (
            "Approximate values. Prices are estimates cross-checked against CMFRI landings. "
            "Catch shares are modelled from national landings data, not measured per zone. "
            "Actual catch and prices vary by season and market conditions. "
            "Fuel consumption calculated using Sagar Sarathi voyage quadratic power formula."
        ),
    }


def get_all_ports() -> list[dict]:
    return PORTS


def get_all_zones() -> list[dict]:
    return ZONES
