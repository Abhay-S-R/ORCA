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
WEATHER_DIR = DATA_DIR / "tier1" / "weather"
HAZARDS_DIR = DATA_DIR / "tier1" / "hazards"
BOUNDARIES_DIR = DATA_DIR / "tier1" / "boundaries"
OSF_DIR = DATA_DIR / "incois_osf_pfz"
NASA_DIR = DATA_DIR / "tier2" / "nasa"
GFW_DIR = DATA_DIR / "tier2" / "gfw"
BHUVAN_DIR = DATA_DIR / "tier3" / "bhuvan"
SAR_DIR = DATA_DIR / "tier1" / "sar"


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


def load_sar_stations() -> dict[str, Any]:
    """ICG MRCC/MRSC roster — `scripts/scrape_icg_sar_stations.py` writes it.

    Returns an empty roster rather than raising when the file is absent: a
    distress reply must still go out with the nationwide 1554 number, and a
    missing station table is not a reason to fail the one query that cannot
    fail.
    """
    try:
        with open(SAR_DIR / "icg_sar_stations.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"stations": [], "station_count": 0}


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


def load_pfz_live_geojson() -> dict[str, Any]:
    """All INCOIS live advisory points formatted as GeoJSON."""
    all_india = PFZ_DIR / "all_india_pfz_advisories.geojson"
    path = all_india if all_india.exists() else (PFZ_DIR / "incois_pfz_live_advisories.geojson")
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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


def load_cmfri_state_landings() -> list[dict[str, Any]]:
    """CMFRI's state-wise annual landings estimate, extracted from its own
    booklet by `scripts/extract_cmfri_state_landings.py`.

    One reporting year per edition — this is a coverage widening (every
    maritime state instead of four Tamil Nadu districts), not a time series.
    Empty when the extraction has not been run.
    """
    path = FISHERIES_DIR / "cmfri_state_landings.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["Year"] = int(r["Year"])
        r["Total_Landings_Tonnes"] = float(r["Total_Landings_Tonnes"])
        r["Landings_Lakh_Tonnes"] = float(r["Landings_Lakh_Tonnes"])
    return rows


def load_cmfri_provenance() -> dict[str, Any]:
    path = FISHERIES_DIR / "cmfri_state_landings_provenance.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


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


# --- climatological baseline ------------------------------------------------

def load_era5_baseline(port: str = "thoothukudi") -> dict[str, Any] | None:
    """Mean and standard deviation per variable over the cached ERA5 reanalysis
    window — the reference period `detect_anomaly` needs to make an anomaly
    claim at all.

    Without this, `detect_anomaly` was a function nothing could call honestly:
    it takes a baseline mean and sigma, and no caller had one. A 30-day window
    is a short baseline and the returned dict says so in `label` — it supports
    "unusual for the last month", not "unusual for this time of year".
    """
    path = WEATHER_DIR / f"era5_historical_{port}_30d.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    daily = raw.get("daily") or {}
    units = raw.get("daily_units") or {}
    dates = daily.get("time") or []

    stats: dict[str, Any] = {}
    for variable, series in daily.items():
        if variable == "time":
            continue
        values = [float(v) for v in series if v is not None]
        if len(values) < 2:
            continue
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        stats[variable] = {
            "mean": round(mean, 3),
            "std": round(std, 3),
            "n_days": len(values),
            "units": units.get(variable, ""),
        }

    if not stats:
        return None
    return {
        "port": port,
        "label": f"ERA5 reanalysis daily baseline, {dates[0]}..{dates[-1]} ({len(dates)} days)",
        "period_start": dates[0] if dates else None,
        "period_end": dates[-1] if dates else None,
        "latitude": raw.get("latitude"),
        "longitude": raw.get("longitude"),
        "variables": stats,
        "dataset": "Open-Meteo ERA5 archive (reanalysis daily aggregates)",
    }


# --- hazards ----------------------------------------------------------------

def load_imd_nowcast_alerts() -> list[dict[str, Any]]:
    """Cached IMD district convective nowcast entries.

    The only IMD-sourced hazard content on disk. Each entry carries a point
    centroid, an event_category ("Lightning", ...), a severity colour and a
    validity window in IST. Returns [] when the cache is absent — the caller
    treats that as "no second source", never as "no hazard".
    """
    path = HAZARDS_DIR / "imd_nowcast_alerts.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("nowcastDetails", [])


# --- INCOIS OSF pre-extracted point forecasts -------------------------------

def load_osf_point_forecasts(product: str) -> list[dict[str, Any]]:
    """Per-port HYCOM current / WW3 wave forecasts, already extracted from the
    16 GB NetCDF pair by `scripts/extract_osf_pilot.py`.

    `product` is "hycom" or "ww3". Each record is flattened to
    `{lat, lon, **properties}`. Reading these is orders of magnitude cheaper
    than opening the source grids, which is the entire point: a per-port
    number does not justify a 9.9 GB file open.
    """
    filename = {"hycom": "hycom_latest_points.geojson", "ww3": "ww3_latest_points.geojson"}.get(product)
    if filename is None:
        raise ValueError(f"unknown OSF product {product!r} — expected 'hycom' or 'ww3'")
    path = OSF_DIR / f"osf_{product}" / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    out: list[dict[str, Any]] = []
    for feat in data.get("features", []):
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        out.append({"lon": float(coords[0]), "lat": float(coords[1]), **feat.get("properties", {})})
    return out


# --- catalog / provenance sidecars ------------------------------------------

def load_nasa_chl_granules() -> list[dict[str, Any]]:
    """NASA CMR granule *index* for MODIS-Aqua chlorophyll.

    Important distinction, and the reason this is named "granules" rather than
    a loader: this file lists what NASA has, it does not contain chlorophyll.
    Surfacing it as a catalog keeps the `nasa_ocean_color` cascade rung honest
    — ORCA can name the granule it would fetch without pretending to hold it.
    """
    path = NASA_DIR / "nasa_cmr_modis_chl_granules.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        entries = json.load(f).get("feed", {}).get("entry", [])
    return [
        {
            "granule": e.get("producer_granule_id") or e.get("title"),
            "time_start": e.get("time_start"),
            "dataset_id": e.get("dataset_id"),
            "data_center": e.get("data_center"),
            "held_locally": False,
        }
        for e in entries
    ]


def load_bhuvan_wms_services() -> list[dict[str, Any]]:
    """ISRO Bhuvan / NRSC + SAC VEDAS OGC service descriptions.

    A second ISRO-lineage surface and a cheap one: these are WMS/WMTS
    endpoints, so they cost a map layer definition rather than a parser.
    """
    path = BHUVAN_DIR / "bhuvan_15days_marine_manifest.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("core_wms_services", [])


def load_boundary_provenance() -> dict[str, Any]:
    """The evidence behind every boundary citation: the audited per-MPA
    provenance record and the VLIZ EEZ gazetteer entries.

    These files are why ORCA can say *which* WDPA site id or MRGID a boundary
    answer rests on. They were on disk and unreferenced, which meant the
    citations they support could not actually be shown to anyone.
    """
    out: dict[str, Any] = {"marine_protected_areas": [], "eez_gazetteer": []}

    mpa_path = BOUNDARIES_DIR / "mpa_geofence_provenance.json"
    if mpa_path.exists():
        with open(mpa_path, encoding="utf-8") as f:
            mpa = json.load(f)
        out["generated_at"] = mpa.get("generated_at")
        out["marine_protected_areas"] = mpa.get("features", [])

    for name in ("vliz_india_eez_record.json", "vliz_srilanka_eez_record.json"):
        path = BOUNDARIES_DIR / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        out["eez_gazetteer"].append({
            "name": rec.get("preferredGazetteerName"),
            "mrgid": rec.get("MRGID"),
            "place_type": rec.get("placeType"),
            "citation": rec.get("gazetteerSource"),
            "polygon_file": rec.get("orca_polygon_file"),
            "bbox": [rec.get("minLongitude"), rec.get("minLatitude"),
                     rec.get("maxLongitude"), rec.get("maxLatitude")],
        })
    return out


def load_osf_marine_grid() -> list[dict[str, float]]:
    """The 400-cell south-India marine grid extracted from the OSF NetCDF pair.

    Wider coverage than the 8 per-port point extractions and the same price (a
    CSV read), so it is what the point fast-path falls back to before it gives
    up. 0.5 deg spacing over roughly 6-13 N / 72-82 E — a regional picture, not
    a position-accurate reading, and the caller is expected to say so.
    """
    path = OSF_DIR / "south_india_marine_grid.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = []
        for r in csv.DictReader(f):
            try:
                rows.append({k: float(v) for k, v in r.items() if v not in ("", None)})
            except ValueError:
                continue
    return rows


def load_osf_dataset_manifest() -> dict[str, Any]:
    """Per-source description, resolution, update cadence, upstream URL pattern
    and LICENSE for the INCOIS OSF/PFZ collection.

    The license line is the part that matters: ORCA cites INCOIS data, and the
    only place the CC-BY 4.0 (INCOIS/MoES) terms are recorded is this file.
    """
    path = OSF_DIR / "dataset_manifest.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_gfw_vessel_sample() -> list[dict[str, Any]]:
    """Global Fishing Watch vessel-identity sample response.

    Identity records only — no positions, no fishing effort. Surfaced as a
    catalog so the `gfw_ais` registry entry is backed by something visible
    rather than being a name with nothing behind it. AIS presence remains
    out of scope; this does not change that.
    """
    path = GFW_DIR / "gfw_vessels_search_sample.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out: list[dict[str, Any]] = []
    for entry in raw.get("entries", []):
        info = (entry.get("combinedSourcesInfo") or [{}])[0]
        self_reported = (entry.get("selfReportedInfo") or [{}])[0]
        out.append({
            "vessel_id": info.get("vesselId") or self_reported.get("id"),
            "ship_name": self_reported.get("shipname"),
            "flag": self_reported.get("flag"),
            "dataset": entry.get("dataset"),
            "geartypes": [g.get("name") for g in info.get("geartypes", [])],
            "held_locally": False,
        })
    return out
