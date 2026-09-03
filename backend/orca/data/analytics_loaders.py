"""Thin reads over the datasets Agent 5 (Ocean Analytics) consumes — plan
§4 D2. Same contract as loaders.py: a loader gets bytes into memory, it does
not reason about them. Everything here is a plain file on disk under data/;
nothing fetches.

The gridded SST / chlorophyll loaders are deliberately NOT here. Per Phase 2
plan §1 and §4.2 those belong to D3's `orca/data/` loader layer, which ships
`mosdac_sst__pilot__*.json` / `mosdac_chl__pilot__*.json` fixtures first and
real `.h5`/`.nc` loaders second, both exiting through
`normalize_to_common_frame`. `load_ocean_grid_fixture` reads those fixtures
when they land and returns None until then — the D3 seam is a file drop, not
a code change here (plan §4.2: "drop-in swap").
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from typing import Any

from orca.data.loaders import DATA_DIR

TIDES_DIR = DATA_DIR / "tier1" / "tides"
PFZ_DIR = DATA_DIR / "incois_osf_pfz" / "pfz"
PFZ_HISTORY_DIR = PFZ_DIR / "history"
FISHERIES_DIR = DATA_DIR / "tier1" / "fisheries"
OCEAN_FIXTURE_DIR = DATA_DIR / "fixtures"  # D3-owned (§4.2)


# --- tides -----------------------------------------------------------------

def load_tide_stations() -> list[dict[str, Any]]:
    """SOI tide station metadata — datum, spring/neap range, coordinates."""
    with open(TIDES_DIR / "soi_tide_stations_metadata.json", encoding="utf-8") as f:
        return json.load(f)["stations"]


def load_soi_tide_events() -> list[dict[str, Any]]:
    """The 2026 SOI predicted high/low tide table, one row per extreme.

    Rows: station_code, station_name, datetime_utc (parsed to tz-aware),
    tide_event ("HIGH TIDE" | "LOW TIDE"), height_m, source.
    """
    events: list[dict[str, Any]] = []
    with open(TIDES_DIR / "soi_tide_tables_2026.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            events.append({
                "station_code": row["station_code"],
                "station_name": row["station_name"],
                "when": _parse_soi_utc(row["datetime_utc"]),
                "tide_event": row["tide_event"].strip().upper(),
                "height_m": float(row["height_above_chart_datum_m"]),
                "source": row["source"],
            })
    return events


def _parse_soi_utc(raw: str) -> datetime:
    # "2026-08-30 03:43:00 UTC"
    return datetime.strptime(raw.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )


def load_tide_gauge_telemetry() -> dict[str, Any]:
    with open(TIDES_DIR / "incois_tide_gauge_telemetry.json", encoding="utf-8") as f:
        return json.load(f)


STORMGLASS_DIR = DATA_DIR / "tier2" / "stormglass"

# SOI station code -> the Stormglass point fixture covering the same port.
# Checked against the actual filenames on disk, not assumed.
STORMGLASS_BY_STATION = {
    "TUT": "thoothukudi",
    "PAM": "pamban",
    "CHE": "chennai",
    "KOC": "kochi",
    "BOM": "mumbai",
}


def load_stormglass_tide_events(station_code: str) -> list[dict[str, Any]]:
    """Stormglass tide extremes for a port, normalised to the same event
    shape `load_soi_tide_events` returns so Agent 5 can swap sources without
    a second code path.

    DATUM WARNING, carried into the event rows and out to the caller:
    Stormglass publishes heights relative to **mean sea level** (they go
    negative), while the SOI tables are metres above **chart datum (LAT)**.
    The two are not interchangeable numbers — only the *times* and the
    high/low ordering are directly comparable. Any answer built on this
    fallback must say which datum it is quoting.
    """
    port = STORMGLASS_BY_STATION.get(station_code)
    if port is None:
        return []
    path = STORMGLASS_DIR / f"stormglass_tides_{port}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    events: list[dict[str, Any]] = []
    for row in raw.get("data", []):
        try:
            when = datetime.fromisoformat(row["time"])
        except (KeyError, ValueError):
            continue
        events.append({
            "station_code": station_code,
            "station_name": port.title(),
            "when": when.astimezone(timezone.utc),
            "tide_event": "HIGH TIDE" if row.get("type") == "high" else "LOW TIDE",
            "height_m": float(row["height"]),
            "datum": "mean sea level",  # NOT chart datum — see docstring
            "source": "Stormglass.io tide extremes API (cached)",
        })
    return events


# --- PFZ -----------------------------------------------------------------

def available_pfz_history_dates() -> list[str]:
    """YYYYMMDD directory names under pfz/history/, oldest first."""
    if not PFZ_HISTORY_DIR.is_dir():
        return []
    return sorted(p.name for p in PFZ_HISTORY_DIR.iterdir() if p.is_dir() and p.name.isdigit())


def load_pfz_history_advisories(date: str) -> list[dict[str, Any]]:
    """One history snapshot's advisory nodes (pfz/history/<date>/advisories.csv)."""
    path = PFZ_HISTORY_DIR / date / "advisories.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_pfz_sector_status(date: str | None = None) -> dict[str, Any]:
    """Per-sector status (HAS_ADVISORY / NO_DATA_CLOUD_COVER / ...). When
    `date` is None, the current top-level pfz_sector_status.json is used."""
    if date is not None:
        path = PFZ_HISTORY_DIR / date / "sector_status.json"
    else:
        path = PFZ_DIR / "pfz_sector_status.json"
    if not path.exists():
        return {"sectors": [], "sector_names": {}, "summary": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_pfz_master() -> list[dict[str, Any]]:
    """The flattened master advisory list with decimal-degree coordinates."""
    path = PFZ_DIR / "incois_pfz_live_advisories_master.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# --- catch statistics --------------------------------------------------------

def load_fish_landings() -> list[dict[str, Any]]:
    """data.gov.in district marine fish landings + species/trend rows."""
    path = FISHERIES_DIR / "datagov_marine_fish_landings.csv"
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["Year"] = int(r["Year"])
        for col in ("Total_Landings_Tonnes", "Pelagic_Tonnes", "Demersal_Tonnes"):
            r[col] = float(r[col])
    return rows


# --- gridded ocean fixtures (D3 seam, §4.2) --------------------------------

def load_ocean_grid_fixture(param: str) -> dict[str, Any] | None:
    """Read D3's `mosdac_<param>__pilot__*.json` normalized-frame fixture.

    `param` is "sst" or "chl". Returns the newest matching fixture, or None
    when D3 has not shipped it yet — Agent 5 degrades to LOW_DATA and says so
    rather than inventing a grid (plan §5.7: no number invented to fill a
    hole).
    """
    if not OCEAN_FIXTURE_DIR.is_dir():
        return None
    matches = sorted(OCEAN_FIXTURE_DIR.glob(f"mosdac_{param}__pilot__*.json"))
    if not matches:
        return None
    with open(matches[-1], encoding="utf-8") as f:
        return json.load(f)
