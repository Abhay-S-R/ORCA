"""What ORCA is allowed to call current, and how it checks (DLC §7.4, R-FRESH-1..5).

Two separate ideas live here and they are easy to confuse:

* `typical_freshness_minutes` in `agents/discovery.py` is the **upstream provider's**
  published cadence. INCOIS says it republishes the Ocean State Forecast every six
  hours. That is a fact about INCOIS.
* Everything in this module is about **ORCA's own copy** — how old the bytes we would
  actually serve are, right now, on this machine. That is a fact about us.

`/data` used to render only the first and label it "refreshed roughly every 6 h",
which read as a claim about the second. This module supplies the second so the page
can show both.

The freshness *class* is the obligation: LIVE sources must be fetched per query,
DAILY sources must carry today's date, WEEKLY ones may lag a week, STATIC ones have
no obligation at all. `docs/ORCA_Data_Freshness_Contract.md` justifies every
assignment dataset by dataset — change the contract there and here together.

Observed freshness is measured off the filesystem on every call rather than read out
of a manifest file. A manifest is one more thing that can itself go stale and lie;
`Path.stat()` cannot.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from orca.data.loaders import DATA_DIR

FreshnessClass = Literal["LIVE", "DAILY", "WEEKLY", "STATIC"]

# The obligation per class, as a maximum tolerated age of the bytes we serve.
# LIVE is 0 because a LIVE source read from disk has already failed its contract —
# the disk copy is the fallback, and a fallback is labelled, never presented as live.
MAX_AGE_MINUTES: dict[FreshnessClass, int | None] = {
    "LIVE": 0,
    "DAILY": 24 * 60,
    "WEEKLY": 7 * 24 * 60,
    "STATIC": None,
}

# Class per source id in `agents.discovery.SOURCE_REGISTRY`. Justifications are in
# docs/ORCA_Data_Freshness_Contract.md §3 — one row per id, same ids.
SOURCE_CLASS: dict[str, FreshnessClass] = {
    # --- LIVE: a decision made on yesterday's copy of this is a wrong decision ---
    "open_meteo_marine": "LIVE",
    "incois_hazard_osf": "LIVE",
    "ndma_sachet": "LIVE",
    "damini_lightning": "LIVE",
    "incois_tide_gauge": "LIVE",
    # --- DAILY: published on a daily cycle; a day late is degraded, a week late is wrong ---
    "incois_pfz": "DAILY",
    "incois_osf_ww3": "DAILY",
    "incois_osf_hycom": "DAILY",
    "soi_tide_tables": "DAILY",
    "mosdac_open_sst": "DAILY",
    "mosdac_nrt_sst": "DAILY",
    "incois_erddap": "DAILY",
    # --- WEEKLY: the physical signal moves slower than the publication cycle ---
    "mosdac_open_chl": "WEEKLY",
    "mosdac_nrt_chl": "WEEKLY",
    "mosdac_nrt_wind": "WEEKLY",
    "nasa_ocean_color": "WEEKLY",
    "copernicus_cmems": "WEEKLY",
    "gfw_ais": "WEEKLY",
    "stormglass_tides": "WEEKLY",
    "bhuvan_wms": "WEEKLY",
    # --- STATIC: geometry and gazetteers. Refreshing these is a data-procurement
    # decision on a multi-year cycle, not an operational task. ---
    "gebco_bathymetry": "STATIC",
    "unep_wcmc_wdpa": "STATIC",
    "marineregions_eez": "STATIC",
    "icg_sar": "STATIC",
    "dof_fishing_ban": "STATIC",
    "datagov_catch": "STATIC",
    "icar_cmfri": "STATIC",
}

# Where each source's bytes live, as globs under data/. Used only to measure age —
# the loaders own the real read paths. A source with no entry is one whose freshness
# we cannot observe, and it is reported as unverified rather than assumed fresh.
SOURCE_FILES: dict[str, tuple[str, ...]] = {
    "open_meteo_marine": ("tier1/ocean/openmeteo_marine_*.json", "tier1/weather/openmeteo_weather_*.json"),
    "damini_lightning": ("tier1/hazards/lightning_nowcast_*.json",),
    "ndma_sachet": ("tier1/hazards/ndma_cap_alerts.json",),
    "incois_hazard_osf": ("tier1/hazards/imd_nowcast_alerts.json",),
    "incois_tide_gauge": ("tier1/tides/incois_tide_gauge_telemetry.json",),
    "incois_pfz": ("incois_osf_pfz/pfz/incois_pfz_live_advisories.geojson",),
    "incois_osf_ww3": ("incois_osf_pfz/osf_ww3/rsmc_combined_ww3_*.nc",),
    "incois_osf_hycom": ("incois_osf_pfz/osf_hycom/RSMC_hycom_*.nc",),
    "soi_tide_tables": ("tier1/tides/soi_tide_tables_2026.csv",),
    "mosdac_open_sst": ("tier3/mosdac/Sea surface temp/*.h5",),
    "mosdac_nrt_sst": ("tier3/mosdac/Sea surface temp/*.h5",),
    "mosdac_open_chl": ("tier3/mosdac/chlorophyll/*.nc",),
    "mosdac_nrt_chl": ("tier3/mosdac/chlorophyll/*.nc",),
    "mosdac_nrt_wind": ("tier3/mosdac/Wind/*.nc",),
    "nasa_ocean_color": ("tier2/nasa/nasa_cmr_modis_chl_granules.json",),
    "copernicus_cmems": ("tier2/copernicus/*.nc",),
    "gfw_ais": ("tier2/gfw/gfw_vessels_search_sample.json",),
    "stormglass_tides": ("tier2/stormglass/stormglass_tides_*.json",),
    "bhuvan_wms": ("tier3/bhuvan/bhuvan_manifest.json",),
    "gebco_bathymetry": ("tier1/bathymetry/gebco_*.nc",),
    "unep_wcmc_wdpa": ("tier1/boundaries/india_marine_mpas.geojson",),
    "marineregions_eez": ("tier1/boundaries/india_eez_polygon.geojson",),
    "icg_sar": ("tier1/sar/icg_sar_stations.json",),
    "dof_fishing_ban": ("tier1/fisheries/seasonal_fishing_ban.json",),
    "datagov_catch": ("tier1/fisheries/datagov_marine_fish_landings.csv",),
    "icar_cmfri": ("tier1/fisheries/cmfri_state_landings.csv",),
}

# Sources ORCA actually fetches over HTTP inside `agents/weather_intelligence.py`.
# Anything classed LIVE but absent here is a contract violation, not a config
# choice — see `live_contract_violations()`.
FETCHED_LIVE: frozenset[str] = frozenset(
    {"open_meteo_marine", "damini_lightning", "ndma_sachet"}
)


def max_age_minutes(freshness_class: FreshnessClass) -> int:
    """The window for a class that has one. STATIC has no refresh obligation, so
    asking for its window is a bug at the call site rather than a `None` to thread
    through every caller."""
    limit = MAX_AGE_MINUTES[freshness_class]
    if limit is None:
        raise ValueError(f"{freshness_class} sources have no maximum age")
    return limit


@dataclass(frozen=True)
class Observed:
    """What is true of ORCA's copy right now. `None` age means nothing on disk."""

    source_id: str
    freshness_class: FreshnessClass | None
    last_refresh_utc: str | None  # newest mtime across the source's files
    content_date: str | None  # newest date the data itself describes, when knowable
    age_minutes: int | None  # of the content when we can date it, else of the file
    file_count: int
    fetched_live: bool
    within_contract: bool | None  # None when unobservable

    def as_dict(self) -> dict[str, Any]:
        return {
            "freshness_class": self.freshness_class,
            "observed_last_refresh_utc": self.last_refresh_utc,
            "observed_content_date": self.content_date,
            "observed_age_minutes": self.age_minutes,
            "observed_file_count": self.file_count,
            "fetched_live": self.fetched_live,
            "within_contract": self.within_contract,
        }


# Content dates hide in filenames, and they matter more than mtime: a Copernicus
# granule downloaded yesterday can hold 2023 data, and "we fetched it recently" is
# not "it describes now". Three shapes cover everything in data/ —
#   E06OCML4AC_20260320_25km.nc          -> 20260320
#   3RIMG_13AUG2026_0015_L3B_SST.h5      -> 13AUG2026
#   cmems_..._2026-08-28-2026-08-29.nc   -> 2026-08-28
# Anything else falls back to mtime, which is the conservative direction only for
# freshly downloaded files — hence `content_date` and `last_refresh` stay separate
# fields rather than being collapsed into one number.
_DATE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
    (r"(?<!\d)(20\d{6})(?!\d)", "%Y%m%d"),
    (r"(\d{2}[A-Z]{3}20\d{2})", "%d%b%Y"),
)


def content_date_from_name(name: str) -> str | None:
    """Newest date encoded in a filename, ISO, or None. Newest because granule
    filenames often carry a start and an end date and the end is what we serve."""
    found: list[datetime] = []
    for pattern, fmt in _DATE_PATTERNS:
        for raw in re.findall(pattern, name, flags=re.IGNORECASE):
            # `%b` matches the locale's "Aug", not the "AUG" MOSDAC writes.
            for candidate in (raw, raw.title()):
                try:
                    found.append(datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc))
                    break
                except ValueError:
                    continue
    if not found:
        return None
    return max(found).strftime("%Y-%m-%d")


def _scan(patterns: tuple[str, ...]) -> tuple[datetime | None, str | None, int]:
    """(newest mtime, newest content date, file count) across a source's globs."""
    newest: datetime | None = None
    content: str | None = None
    count = 0
    for pattern in patterns:
        for path in DATA_DIR.glob(pattern):
            if not path.is_file():
                continue
            count += 1
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if newest is None or mtime > newest:
                newest = mtime
            dated = content_date_from_name(path.name)
            if dated and (content is None or dated > content):
                content = dated
    return newest, content, count


def observe(source_id: str, *, now: datetime | None = None) -> Observed:
    """Measure one source's on-disk freshness. Never raises: an unreadable or
    absent dataset is reported as unobserved, which downstream renders as
    "unverified" — the one thing it must never do is silently read as fresh."""
    now = now or datetime.now(timezone.utc)
    cls = SOURCE_CLASS.get(source_id)
    newest, content, count = _scan(SOURCE_FILES.get(source_id, ()))
    fetched_live = source_id in FETCHED_LIVE

    if newest is None:
        # A LIVE source with no cache on disk is fine if we fetch it; it is the
        # live call that satisfies the contract, not a file.
        return Observed(source_id, cls, None, None, None, 0, fetched_live,
                        True if (fetched_live and cls == "LIVE") else None)

    # Age of the *content* where the filename dates it, age of the file otherwise.
    # These diverge badly and in the direction that flatters us: the Copernicus
    # chlorophyll granule was downloaded three weeks ago and holds 2023 data.
    if content:
        content_dt = datetime.strptime(content, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age = max(0, int((now - content_dt).total_seconds() // 60))
    else:
        age = max(0, int((now - newest).total_seconds() // 60))

    limit = MAX_AGE_MINUTES.get(cls) if cls else None
    if cls == "LIVE":
        within = fetched_live  # the cache age is irrelevant while the live call works
    elif cls == "STATIC" or limit is None:
        within = True
    else:
        within = age <= limit

    return Observed(source_id, cls, newest.strftime("%Y-%m-%dT%H:%M:%SZ"), content, age,
                    count, fetched_live, within)


def observe_all(*, now: datetime | None = None) -> dict[str, Observed]:
    now = now or datetime.now(timezone.utc)
    return {sid: observe(sid, now=now) for sid in SOURCE_CLASS}


def live_contract_violations() -> list[str]:
    """LIVE-classed sources ORCA does not actually fetch over HTTP. Empty list is
    the goal; today it returns the tide gauge and the INCOIS hazard feed, both of
    which are read from a cached file and must not be described as live until they
    are not. `scripts/verify_ci_guards.py` can assert on this once they are fixed."""
    return sorted(sid for sid, cls in SOURCE_CLASS.items()
                  if cls == "LIVE" and sid not in FETCHED_LIVE)


# --- the staleness ceiling (R-SAFE-1, plan P0.5) ------------------------------

def staleness_ceiling_minutes(cls: FreshnessClass) -> int | None:
    """Age past which data of this class may not back a GO. Twice the class
    window, never under two hours — LIVE's window is 0 (a disk copy has already
    missed its contract), and a verdict that flips to CAUTION the minute a
    fetch fails would make every offline run a CAUTION. None = never stale."""
    max_age = MAX_AGE_MINUTES[cls]
    return None if max_age is None else max(2 * max_age, 120)


def past_staleness_ceiling(age_minutes: int, cls: FreshnessClass) -> bool:
    ceiling = staleness_ceiling_minutes(cls)
    return ceiling is not None and age_minutes > ceiling


# --- the cache-expiry half (R-FRESH-2) ---------------------------------------

def is_stale(path: Path, max_age_minutes: int, *, now: datetime | None = None) -> bool:
    """True when `path` is missing or older than `max_age_minutes`.

    This exists because three separate call sites had written
    `if path.exists(): return read(path)` — a cache that can never expire, which
    served a 2026-08-27 wind field for three weeks. Existence is not freshness.
    """
    if not path.is_file():
        return True
    now = now or datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime < now - timedelta(minutes=max_age_minutes)


def read_json_if_fresh(path: Path, max_age_minutes: int) -> dict[str, Any] | None:
    """The cached bytes when they are inside their window, else None. A corrupt
    file is treated as absent — regenerating is always safe, serving half a JSON
    document is not."""
    if is_stale(path, max_age_minutes):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def acquisition_date(payload: dict[str, Any], path: Path) -> str:
    """Best available acquisition date for a cached payload: whatever the producer
    recorded, else the file's own mtime. Used to label a stale cache honestly
    rather than dropping it — a labelled old field is useful, an unlabelled one is
    a fabricated claim about now (R-NEW-9)."""
    for key in ("acquisition_date", "acquisition_timestamp", "valid_for", "generated_at"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value[:10]
    if path.is_file():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    return ""


if __name__ == "__main__":  # smallest check that fails if the logic breaks
    import tempfile

    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "cache.json"
        p.write_text('{"acquisition_date": "2026-08-27"}', encoding="utf-8")
        import os

        old = (now - timedelta(days=22)).timestamp()
        os.utime(p, (old, old))
        assert is_stale(p, 360, now=now), "22-day-old cache must be stale at a 6 h TTL"
        assert read_json_if_fresh(p, 360) is None
        assert not is_stale(p, 60 * 24 * 365, now=now), "inside a 1-year TTL it is fresh"
        assert acquisition_date(json.loads(p.read_text()), p) == "2026-08-27"
        assert is_stale(Path(tmp) / "missing.json", 10, now=now), "absent means stale"

    # The three filename date shapes actually present under data/.
    assert content_date_from_name("E06OCML4AC_20260320_25km_v1.0.1.nc") == "2026-03-20"
    assert content_date_from_name("3RIMG_13AUG2026_0015_L3B_SST_DLY.h5") == "2026-08-13"
    assert content_date_from_name("cmems_thetao_2026-08-28-2026-08-29.nc") == "2026-08-29"
    assert content_date_from_name("india_eez_polygon.geojson") is None

    # A LIVE source we do not actually fetch is a contract violation, and today
    # there are exactly two of them — this assert is the tripwire for fixing them.
    assert live_contract_violations() == ["incois_hazard_osf", "incois_tide_gauge"], (
        live_contract_violations()
    )
    assert MAX_AGE_MINUTES["STATIC"] is None
    print("freshness self-check OK")
