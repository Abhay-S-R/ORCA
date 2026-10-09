"""Build the Indian Coast Guard MRCC/MRSC station table behind PS-Q8.

Procurement runbook §C4. `distress.surface_mrcc_contact()` shipped with two
entries — nationwide 1554 and MRCC Chennai — and ignored `user_location`
entirely, so a distress call from Gujarat was handed the Tamil Nadu centre.
The authoritative roster is the Coast Guard's own SAR Organisation page,
which lists three MRCCs and their subordinate MRSCs by name.

TWO THINGS THIS DELIBERATELY DOES NOT DO, both for the same reason — a
rescue contact that is wrong is worse than one that is missing:

  * It does not invent per-station phone numbers. The ICG publishes none for
    MRSCs; `phone` is null for every station and the callable numbers stay
    the verified pair already in distress.py (1554, VHF 16).
  * It does not guess coordinates. Each station is geocoded against
    Open-Meteo's gazetteer and then range-checked against the MRCC region it
    is listed under; anything that lands in the wrong sea is dropped, not
    rounded into place. GEOCODE_OVERRIDES carries the handful the gazetteer
    cannot resolve (renamed, or too small to be a populated place).

    python scripts/scrape_icg_sar_stations.py
    python scripts/scrape_icg_sar_stations.py --self-check   # no network
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
OUT_PATH = DATA / "tier1" / "sar" / "icg_sar_stations.json"

SAR_PAGE = "https://indiancoastguard.gov.in/sar-organisation"
GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search"

# Station names as the page writes them -> (lat, lon), for the ones the
# gazetteer cannot return. Each is a coastal facility whose location is
# unambiguous but which is not a populated place under that name.
GEOCODE_OVERRIDES: dict[str, tuple[float, float]] = {
    # Renamed from Port Blair in 2024; gazetteers still carry the old name.
    "Sri Vijaya Puram": (11.623, 92.726),
    "Hutbay": (10.583, 92.550),      # Little Andaman, jetty settlement
    "Frazerganj": (21.567, 88.267),  # South 24 Parganas fishing harbour
    "Jakhau": (23.221, 68.719),      # Kutch fishing harbour
    "Vadinar": (22.359, 69.722),     # Gulf of Kutch oil terminal
    "Nizampatinam": (15.900, 80.673),
    "Murud Janjira": (18.298, 72.965),
    "Androth": (10.818, 73.688),
    "Kavarathi": (10.567, 72.642),   # Kavaratti, Lakshadweep
    "Minicoy": (8.283, 73.050),
    "Kamorta": (8.117, 93.522),
    "Pipavav": (20.917, 71.517),
    "Goa": (15.404, 73.804),              # ICG station at Mormugao/Vasco
    "New Mangalore": (12.923, 74.803),    # New Mangalore Port, Panambur
    "Vishakhapatnam": (17.686, 83.288),   # page spelling; Visakhapatnam Port
    "Krishnapatnam": (14.274, 80.120),
}

# Each MRCC's area of responsibility, as a coarse box used only to reject a
# geocode that landed on the wrong coast (a "Goa" in Portugal, a "Mandapam"
# inland). Not an operational SAR region boundary — those are ICG's.
MRCC_REGIONS: dict[str, tuple[float, float, float, float]] = {
    # name: (min_lat, max_lat, min_lon, max_lon)
    "MRCC Mumbai": (8.0, 24.0, 68.0, 77.6),            # west coast + Lakshadweep
    "MRCC Chennai": (8.0, 22.5, 76.5, 89.5),           # east coast
    "MRCC Sri Vijaya Puram": (6.0, 14.5, 92.0, 94.5),  # Andaman & Nicobar
}

_STATION_LINE = re.compile(r"^(MRCC|MRSC)\s+(.+?)$", re.IGNORECASE)


def fetch_station_names(url: str = SAR_PAGE) -> list[tuple[str, str]]:
    """[(kind, name)] in page order, which is also MRCC-then-its-MRSCs order."""
    with urllib.request.urlopen(url, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", raw))
    return parse_station_names(text)


def parse_station_names(text: str) -> list[tuple[str, str]]:
    """Pulled out of the fetch so --self-check can exercise it offline."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for line in (raw_line.strip() for raw_line in text.split("\n")):
        m = _STATION_LINE.match(line)
        if not m:
            continue
        kind, name = m.group(1).upper(), m.group(2).strip()
        # The page's own glossary repeats "MRSC - Maritime Rescue Sub Centre".
        if name.startswith("-") or len(name) > 40:
            continue
        if name.islower() or name.isupper():
            name = name.title()
        key = kind + " " + name
        if key in seen:
            continue
        seen.add(key)
        out.append((kind, name))
    return out


def assign_regions(stations: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Each MRSC belongs to the MRCC listed above it — the page's structure is
    the hierarchy, so it is read rather than re-derived from geography."""
    rows: list[dict[str, str]] = []
    current = "MRCC Mumbai"
    for kind, name in stations:
        full = kind + " " + name
        if kind == "MRCC":
            current = full
        rows.append({"kind": kind, "name": name, "station": full, "mrcc": current})
    return rows


def geocode(name: str) -> tuple[float, float] | None:
    if name in GEOCODE_OVERRIDES:
        return GEOCODE_OVERRIDES[name]
    q = urllib.parse.urlencode({"name": name, "count": 10, "country": "IN", "language": "en"})
    try:
        with urllib.request.urlopen(GEOCODE_API + "?" + q, timeout=30) as r:
            results = json.load(r).get("results") or []
    except Exception:
        return None
    for hit in results:
        if hit.get("country_code") == "IN":
            return round(float(hit["latitude"]), 4), round(float(hit["longitude"]), 4)
    return None


def in_region(mrcc: str, lat: float, lon: float) -> bool:
    lo_la, hi_la, lo_lo, hi_lo = MRCC_REGIONS[mrcc]
    return lo_la <= lat <= hi_la and lo_lo <= lon <= hi_lo


def main() -> int:
    rows = assign_regions(fetch_station_names())
    if not rows:
        print("SAR page returned no station lines — page structure changed", file=sys.stderr)
        return 1

    located: list[dict[str, object]] = []
    dropped: list[str] = []
    for row in rows:
        coords = geocode(row["name"])
        if coords is None or not in_region(row["mrcc"], *coords):
            dropped.append("%s (%s)" % (row["station"], coords))
            continue
        located.append({
            "station": row["station"],
            "kind": row["kind"],
            "name": row["name"],
            "mrcc": row["mrcc"],
            "latitude": coords[0],
            "longitude": coords[1],
            "coordinate_source": "override" if row["name"] in GEOCODE_OVERRIDES else "open-meteo-geocoding",
            # The ICG publishes no per-station telephone number. Null is the
            # honest value; 1554 and VHF 16 are what a caller actually dials.
            "phone": None,
        })
        if row["name"] not in GEOCODE_OVERRIDES:
            time.sleep(0.4)

    payload = {
        "network_name": "Indian Coast Guard Maritime Rescue Coordination Centres and Sub Centres",
        "source_url": SAR_PAGE,
        "acquisition_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "authority_tier": "T1",
        "national_distress_number": "1554",
        "vhf_distress_channel": "16",
        "station_count": len(located),
        "listed_count": len(rows),
        "unlocated": dropped,
        "note": "Station roster is authoritative (ICG SAR Organisation page). Coordinates are "
                "geocoded facility locations, not surveyed positions, and no per-station "
                "telephone number is published — dial 1554 or VHF 16.",
        "stations": located,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("%d/%d stations -> %s" % (len(located), len(rows), OUT_PATH.relative_to(REPO_ROOT)))
    for d in dropped:
        print("  unlocated:", d)
    return 0


def _self_check() -> None:
    """Parsing and hierarchy, without touching the network."""
    page = (
        "SAR Organisation\nDGICG (NMSARCA)\n"
        "MRCC Mumbai\nMRSC Jakhau\nMRSC Okha\n"
        "MRCC Chennai\nMRSC Haldia\n"
        "MRCC Sri Vijaya Puram\nMRSC Campbell Bay\n"
        "MRSC\n- Maritime Rescue Sub Centre"
    )
    names = parse_station_names(page)
    assert [k for k, _ in names].count("MRCC") == 3, names
    assert ("MRSC", "Jakhau") in names
    assert all(not n.startswith("-") for _, n in names), "glossary line leaked in"

    rows = assign_regions(names)
    by_station = {r["station"]: r["mrcc"] for r in rows}
    # The hierarchy comes from page order: Haldia sits under Chennai, not Mumbai.
    assert by_station["MRSC Haldia"] == "MRCC Chennai", by_station
    assert by_station["MRSC Jakhau"] == "MRCC Mumbai"
    assert by_station["MRSC Campbell Bay"] == "MRCC Sri Vijaya Puram"

    # Region boxes reject a geocode that landed on the wrong coast.
    assert in_region("MRCC Mumbai", 23.221, 68.719)      # Jakhau, Gujarat
    assert not in_region("MRCC Mumbai", 21.567, 88.267)  # Frazerganj is Bay of Bengal
    assert in_region("MRCC Sri Vijaya Puram", 11.623, 92.726)
    assert not in_region("MRCC Chennai", 41.9, 12.5)     # Rome
    assert in_region("MRCC Mumbai", 8.383, 76.989)      # Vizhinjam is west coast

    assert all(v is not None for v in GEOCODE_OVERRIDES.values())
    print("self-check ok: station parse, MRCC hierarchy from page order, region rejection")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
