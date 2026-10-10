"""India State Fishing Boundary Rules.

Legal Framework:
- Article 297 Constitution + UNCLOS: India's territorial waters = 0–12 NM from baseline.
- Entry 21 (State List): Each coastal state regulates fishing within their 0–12 NM territory.
- Entry 57 (Union List): Beyond 12 NM (EEZ, up to 200 NM) = Central Government / DFHMAD.
- Marine Fishing Regulation Acts (MFRAs): Each state has its own MFRA enforcing:
    * Traditional-craft reserved zones (0–3 NM to 0–5 NM typically; non-mechanised only)
    * Seasonal bans (61-day uniform ban + state-specific)
    * Gear restrictions (mesh size, trawl type)
    * Inter-state intrusion prohibition: fishing vessels must hold the HOME state's licence.

Key Rules for Sagar Sarathi:
1. A fisherman from Kerala CANNOT legally fish in Tamil Nadu's territorial waters
   without Tamil Nadu's permission/licence — the system must only show Kerala zones.
2. The 12 NM boundary is not a "no-go" line for navigation, but for FISHING ACTIVITY.
3. Within 5 NM (approx) many states reserve for traditional/artisanal craft only.

State zone sectors align with the 'sector' field in FishingZone.properties.sector.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── State → [zone-sector strings that legally belong to this state] ───────────
# Zone sector names must match `properties.sector` in the FishingZone dataset.
STATE_ZONE_SECTORS: dict[str, list[str]] = {
    "Gujarat": ["Gujarat", "GUJARAT"],
    "Maharashtra": ["Maharashtra", "MAHARASHTRA"],
    "Goa": ["Goa", "GOA"],
    "Karnataka": ["Karnataka", "KARNATAKA"],
    "Kerala": ["Kerala", "KERALA"],
    "Tamil Nadu": ["Tamil Nadu", "TAMIL NADU", "TN"],
    "Andhra Pradesh": ["Andhra Pradesh", "ANDHRA PRADESH", "AP"],
    "Odisha": ["Odisha", "ODISHA"],
    "West Bengal": ["West Bengal", "WEST BENGAL", "WB"],
    "Andaman & Nicobar": ["Andaman & Nicobar", "ANDAMAN & NICOBAR", "ANDAMAN"],
    "Lakshadweep": ["Lakshadweep", "LAKSHADWEEP"],
    # Aliases for INCOIS PFZ sector codes
    "Puducherry": ["Tamil Nadu", "Puducherry", "PUDUCHERRY"],  # Puducherry coast is in Tamil Nadu waters
}

# ── Traditional/artisanal zone distances (NM from shore) ──────────────────────
# Mechanised trawlers are PROHIBITED inside these distances under each MFRA.
STATE_TRADITIONAL_ZONE_NM: dict[str, float] = {
    "Gujarat": 3.0,
    "Maharashtra": 5.0,
    "Goa": 3.0,
    "Karnataka": 3.0,
    "Kerala": 3.0,    # MFRA 1980: 3 NM reserved for traditional crafts
    "Tamil Nadu": 5.0,  # 5 NM reserved for non-mechanised boats
    "Andhra Pradesh": 4.3,  # 4.3 NM (7 km) under AP MFRA
    "Odisha": 5.0,
    "West Bengal": 5.0,
    "Andaman & Nicobar": 5.0,
    "Lakshadweep": 5.0,
}

# ── Seasonal fishing ban windows by coast (DFHMAD uniform 61-day ban) ─────────
# Format: (month_start, day_start, month_end, day_end) — inclusive, both years-rolling
STATE_FISHING_BAN: dict[str, dict[str, Any]] = {
    # West Coast ban: June 15 – July 31 (61 days) — align with southwest monsoon onset
    "Gujarat": {"start_month": 6, "start_day": 15, "end_month": 7, "end_day": 31,
                "description": "61-day seasonal fishing ban (Gujarat MFRA) — Southwest Monsoon"},
    "Maharashtra": {"start_month": 6, "start_day": 15, "end_month": 7, "end_day": 31,
                    "description": "61-day seasonal fishing ban (Maharashtra MFRA) — Southwest Monsoon"},
    "Goa": {"start_month": 6, "start_day": 1, "end_month": 7, "end_day": 31,
            "description": "61-day seasonal fishing ban (Goa MFRA) — Southwest Monsoon"},
    "Karnataka": {"start_month": 6, "start_day": 15, "end_month": 7, "end_day": 31,
                  "description": "61-day seasonal fishing ban (Karnataka MFRA) — Southwest Monsoon"},
    "Kerala": {"start_month": 6, "start_day": 15, "end_month": 7, "end_day": 31,
               "description": "61-day seasonal fishing ban (Kerala MFRA 1980) — Southwest Monsoon"},
    # East Coast ban: April 15 – June 14 (61 days) — North-East Monsoon retreat / spawning season
    "Tamil Nadu": {"start_month": 4, "start_day": 15, "end_month": 6, "end_day": 14,
                   "description": "61-day seasonal fishing ban (Tamil Nadu MFRA) — Spawning season"},
    "Andhra Pradesh": {"start_month": 4, "start_day": 15, "end_month": 6, "end_day": 14,
                       "description": "61-day seasonal fishing ban (AP MFRA) — Spawning season"},
    "Odisha": {"start_month": 4, "start_day": 15, "end_month": 6, "end_day": 14,
               "description": "61-day seasonal fishing ban (Odisha MFRA) — Spawning season"},
    "West Bengal": {"start_month": 4, "start_day": 15, "end_month": 6, "end_day": 14,
                    "description": "61-day seasonal fishing ban (West Bengal MFRA) — Spawning season"},
    # Island territories follow the nearest mainland coast pattern
    "Andaman & Nicobar": {"start_month": 4, "start_day": 15, "end_month": 6, "end_day": 14,
                           "description": "61-day seasonal fishing ban — Bay of Bengal spawning season"},
    "Lakshadweep": {"start_month": 6, "start_day": 15, "end_month": 7, "end_day": 31,
                    "description": "61-day seasonal fishing ban — Southwest Monsoon"},
}


@dataclass(frozen=True)
class StateFishingBoundary:
    """Boundary rules for a single coastal state."""
    state: str
    zone_sectors: list[str]                  # FishingZone sector values for this state
    traditional_zone_nm: float               # NM from shore reserved for non-mech craft
    max_fishing_nm: float                    # = 12 NM (territorial waters limit)
    seasonal_ban: dict[str, Any] | None     # ban period dict or None


def get_state_boundary(state: str) -> StateFishingBoundary | None:
    """Return fishing boundary rules for a coastal state."""
    sectors = STATE_ZONE_SECTORS.get(state)
    if sectors is None:
        # Try partial match
        for k, v in STATE_ZONE_SECTORS.items():
            if state.lower() in k.lower() or k.lower() in state.lower():
                sectors = v
                state = k
                break
    if sectors is None:
        return None
    return StateFishingBoundary(
        state=state,
        zone_sectors=sectors,
        traditional_zone_nm=STATE_TRADITIONAL_ZONE_NM.get(state, 3.0),
        max_fishing_nm=12.0,          # UNCLOS + Constitution Art.297 fixed limit
        seasonal_ban=STATE_FISHING_BAN.get(state),
    )


def filter_zones_for_state(zones: list[Any], state: str) -> list[Any]:
    """Return only the fishing zones that legally belong to a given state.

    Args:
        zones: List of FishingZone objects (or dicts with 'properties.sector').
        state: The fisherman's home state name.

    Returns:
        Filtered list of zones whose sector matches the state's allowed sectors.
    """
    boundary = get_state_boundary(state)
    if boundary is None:
        return zones  # Unknown state — return all (fail-open)

    allowed = {s.upper() for s in boundary.zone_sectors}
    result = []
    for z in zones:
        props = z.properties if hasattr(z, "properties") else z.get("properties", {})
        sector = str(props.get("sector", "")).upper()
        if sector:
            if sector in allowed or boundary.state.upper() in sector:
                result.append(z)
        else:
            lat = getattr(z, "entry_lat", None) or props.get("entry_lat")
            lng = getattr(z, "entry_lng", None) or props.get("entry_lng")
            if lat is not None and lng is not None:
                from orca.sea_route.datasets import _guess_coastal_state
                inferred = _guess_coastal_state(float(lat), float(lng)).upper()
                if inferred in allowed or boundary.state.upper() == inferred:
                    result.append(z)
    return result


def get_state_fishing_rule_text(state: str) -> str:
    """Human-readable fishing rules for a state, for AI system prompt injection."""
    b = get_state_boundary(state)
    if b is None:
        return ""
    lines = [
        f"State fishing jurisdiction ({state}):",
        f"  • Territorial waters: 0–{b.max_fishing_nm} NM from baseline (state jurisdiction, {state} MFRA).",
        f"  • Traditional craft reserved zone: 0–{b.traditional_zone_nm} NM — mechanised vessels prohibited.",
        f"  • Fishermen licensed in {state} must fish within {state}'s 0–12 NM waters only.",
        "  • Fishing in another state's territorial waters requires that state's licence.",
        "  • Beyond 12 NM: EEZ (12–200 NM) regulated by Central Government (DFHMAD).",
    ]
    if b.seasonal_ban:
        ban = b.seasonal_ban
        lines.append(
            f"  • Seasonal ban: {ban.get('description', '')} "
            f"({ban.get('start_month'):02d}/{ban.get('start_day'):02d} – "
            f"{ban.get('end_month'):02d}/{ban.get('end_day'):02d})."
        )
    return "\n".join(lines)
