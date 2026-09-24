"""Agent 5 — Ocean Analytics (Architecture §3.1; Phase 2 plan §4 D2).

The system's only genuine multi-factor reasoning agent. It carries PS #1
(nearest / most persistent PFZ), PS #3 (tide + sea state) and PS #7 (why has
catch declined) on its own.

Three independently-shippable parts, per the plan's Day 9/10/11 split:

  part 1 — SST + chlorophyll correlation, anomaly vs climatology, tide
           prediction from the SOI tide tables
  part 2 — PFZ proximity + `score_pfz_persistence`; sector status as a
           first-class output (a cloud-suppressed sector returns
           NO_DATA_CLOUD_COVER carrying INCOIS's own wording, never an empty
           result — data audit C-2)
  part 3 — diagnostic DEEP mode, `diagnose_productivity_decline`

PROMPT / OUTPUT DISCIPLINE (the deliverable, not the prose): this agent says
"correlated with" unless the data supports "caused by", and it returns
"insufficient data" for a factor it could not measure rather than filling the
gap. This is exactly what D1's LLM bake-off scores.

No LLM call anywhere in this module — it is arithmetic and table lookups over
real datasets, the same discipline as Agent 4. `persona` is never referenced
(Ground Rule 1).

The gridded SST/chlorophyll loaders belong to D3 (§4.2). Until D3 ships the
`mosdac_*__pilot__*.json` fixtures, `correlate_sst_chlorophyll` degrades to
LOW_DATA and names the gap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from orca.agents import geospatial
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data import analytics_loaders as al
from orca.data import satellite_loaders as sl
from orca.data.freshness import recency
from orca.data.loaders import DEFAULT_LAT as _DEFAULT_LAT
from orca.data.loaders import DEFAULT_LON as _DEFAULT_LON
from orca.state import ORCAState

NM_PER_KM = 1 / 1.852

_COMPASS_16 = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)

# South Tamil Nadu is the pilot sector (SEC006) and stays the *fallback* only:
# it is what a point outside every band below resolves to, never what a
# located user is assumed to be in. The default position itself lives in
# loaders.DEFAULT_LAT/LON — one copy, so it cannot drift out of step with what
# /query actually answers a locationless request at.
_PILOT_SECTOR = "SEC006"

# INCOIS sector geometry is not published as polygons, and it cannot be
# recovered from the advisory nodes alone: 6 of the 14 sectors (SEC001
# Gujarat, SEC006 South TN, SEC010 Odisha, SEC011 WB, SEC012 Andaman, SEC013
# Nicobar) have *zero* nodes on disk today because they are cloud-suppressed,
# and a sector with no nodes would be unreachable by a nearest-node rule —
# which is precisely the sector a user most needs named, since that is the
# sector whose answer is "no data, here is why".
#
# So: coast side, then a latitude band, matching INCOIS's own state-wise
# division. Bands below are checked against the measured node extents of the
# 8 sectors that do have nodes (see test_wiring.py). Precision is a band
# boundary in open water, not a coastline — good enough to name the right
# state's sector and nothing finer is claimed.
_ISLAND_SECTORS = (  # (sector_id, min_lat, max_lat, min_lon, max_lon)
    ("SEC014", 8.0, 12.5, 71.0, 74.3),   # Lakshadweep
    ("SEC013", 6.0, 10.4, 92.0, 94.5),   # Nicobar
    ("SEC012", 10.4, 14.5, 91.5, 94.5),  # Andaman
)
_WEST_COAST_BANDS = (  # north -> south, Arabian Sea side
    ("SEC001", 20.5),  # Gujarat
    ("SEC002", 15.7),  # Maharashtra
    ("SEC003", 14.9),  # Goa
    ("SEC004", 12.8),  # Karnataka
    ("SEC005", -90.0),  # Kerala (down to Kanyakumari)
)
_EAST_COAST_BANDS = (  # north -> south, Bay of Bengal side
    ("SEC011", 21.4),  # West Bengal
    ("SEC010", 19.0),  # Odisha
    ("SEC009", 16.2),  # North Andhra Pradesh
    ("SEC008", 13.5),  # South Andhra Pradesh
    ("SEC007", 10.3),  # North Tamil Nadu
    ("SEC006", -90.0),  # South Tamil Nadu
)
# Longitude of Kanyakumari — the peninsula's tip, and so the meridian that
# separates "Arabian Sea coast" from "Bay of Bengal coast" for any mainland
# point. The pilot box (78.3 E) falls east of it, as it should.
_PENINSULA_TIP_LON = 77.6


def sector_for_point(lat: float, lon: float) -> str:
    """INCOIS PFZ sector id containing a position (SEC001–SEC014).

    Replaces the hardcoded pilot sector. Before this, every user in India was
    shown South Tamil Nadu's sector status — a Kerala fisherman was told his
    sector was cloud-suppressed while SEC005 had live advisories on disk.
    """
    for sector_id, lat0, lat1, lon0, lon1 in _ISLAND_SECTORS:
        if lat0 <= lat < lat1 and lon0 <= lon <= lon1:
            return sector_id
    return sector_for_point_disclosed(lat, lon)[0]


# The bands below have no outer edge by design — the southernmost entry on each
# coast is open-ended so no Indian coastal position can fall through them. That
# also means a position in the middle of the Arabian Sea off Oman would be
# handed SEC001 Gujarat with a straight face, so the lookup is bounded here
# first. Matches place_resolution.DATA_EXTENT, widened by nothing.
_SECTOR_EXTENT = (5.0, 25.0, 66.0, 96.0)  # (lat_min, lat_max, lon_min, lon_max)


def sector_for_point_disclosed(
    lat: float, lon: float, place_source: str | None = None
) -> tuple[str, str | None]:
    """P1.6 (`R-INDIA-2`) — the sector AND, when it is not really the user's,
    the sentence saying so.

    `sector_for_point` answers the first half and always has. The half that
    was missing is that its answer is indistinguishable from a fallback: a
    caller got a bare "SEC006" whether that was derived from a real position
    or was the pilot sector standing in for one. SEC006 survives here only as
    a *disclosed* fallback, which is what the point asks for.
    """
    lat0, lat1, lon0, lon1 = _SECTOR_EXTENT
    if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
        return _PILOT_SECTOR, (
            f"{lat:.2f}N {lon:.2f}E is outside every INCOIS PFZ sector "
            f"({lat0:g}-{lat1:g}N, {lon0:g}-{lon1:g}E). The sector status shown is the pilot "
            "sector's, as a placeholder — it is not a statement about this position."
        )
    for sector_id, la0, la1, lo0, lo1 in _ISLAND_SECTORS:
        if la0 <= lat < la1 and lo0 <= lon <= lo1:
            return sector_id, _default_position_note(sector_id, place_source)
    bands = _WEST_COAST_BANDS if lon < _PENINSULA_TIP_LON else _EAST_COAST_BANDS
    for sector_id, min_lat in bands:
        if lat >= min_lat:
            return sector_id, _default_position_note(sector_id, place_source)
    return _PILOT_SECTOR, (
        f"No INCOIS sector band covers {lat:.2f}N {lon:.2f}E; the pilot sector "
        f"{_PILOT_SECTOR} is shown as a fallback."
    )


def _default_position_note(sector_id: str, place_source: str | None) -> str | None:
    """A sector derived from the pilot default position is the pilot's sector
    however it was arrived at. Saying "your sector is SEC006" to someone whose
    position we never learned is the exact claim P1.6 exists to stop."""
    if place_source != "regional_default":
        return None
    return (
        f"Sector {sector_id} was derived from the pilot default position, not from yours — "
        "this question named no place. Name one, or send your position, for your own sector."
    )


def _compass(bearing_deg: float) -> str:
    return _COMPASS_16[round(bearing_deg / 22.5) % 16]


def _km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    _, dist_nm = geospatial.bearing_and_distance(lat1, lon1, lat2, lon2)
    return dist_nm / NM_PER_KM


def _now(state: ORCAState | None = None) -> datetime:
    if state:
        window = state.get("target_time_window") or {}
        start = window.get("start")
        if start:
            try:
                return datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                pass
    return datetime.now(timezone.utc)


# --- part 1: tide prediction ----------------------------------------------

@dataclass(frozen=True)
class TidePrediction:
    station_code: str
    station_name: str
    next_high: dict[str, Any] | None
    next_low: dict[str, Any] | None
    tidal_state: str  # "RISING" | "FALLING" | "UNKNOWN"
    range_m: float | None
    spring_neap: str  # "SPRING" | "NEAP" | "MID" | "UNKNOWN"
    datum: str  # "chart datum (LAT)" | "mean sea level" — NOT interchangeable
    fell_back: bool
    source_provenance: SourceProvenance
    confidence: Confidence


def nearest_station(lat: float, lon: float) -> dict[str, Any]:
    stations = al.load_tide_stations()
    return min(stations, key=lambda s: _km_between(lat, lon, s["latitude"], s["longitude"]))


def predict_tides(
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
    *,
    when: datetime | None = None,
    down: tuple[str, ...] = (),
) -> TidePrediction:
    """Next high and low tide at the nearest SOI station, plus the current
    rising/falling state and a spring/neap classification from the station's
    own published spring and neap ranges. Predicted (astronomical) heights —
    not observed; the INCOIS tide-gauge feed is the observed cross-check and
    a separate call.

    Fallback cascade (Architecture §12.1, `soi_tide_tables`): SOI 2026 tables
    → Stormglass cached extremes. `down` names sources treated as
    unavailable, the same lever `discovery.select_source_with_fallback` takes,
    so D1's degradation E2E can force the rung without patching a loader. The
    rung is named in the provenance and drops confidence, and because
    Stormglass quotes **mean sea level** while SOI quotes **chart datum
    (LAT)**, `datum` says which one the heights are on — those numbers are not
    interchangeable, only the times and the high/low ordering are.
    """
    when = when or datetime.now(timezone.utc)
    station = nearest_station(lat, lon)
    code = station["station_code"]
    datum = "chart datum (LAT)"
    fell_back = False

    # Rung 1 — SOI. Unusable means the source is declared down OR it simply
    # carries no rows for this station (several metadata stations have no
    # published table). "No rows" is a source gap, not "no tide", and the two
    # must not render the same way.
    events: list[dict[str, Any]] = []
    if "soi_tide_tables" not in down:
        events = [e for e in al.load_soi_tide_events() if e["station_code"] == code]

    # Rung 2 — Stormglass cached extremes (Architecture §12.1).
    if not events and "stormglass_tides" not in down:
        events = al.load_stormglass_tide_events(code)
        if events:
            fell_back, datum = True, "mean sea level"

    events.sort(key=lambda e: e["when"])
    future = [e for e in events if e["when"] >= when]
    past = [e for e in events if e["when"] < when]

    def _fmt(e: dict[str, Any]) -> dict[str, Any]:
        return {
            "when": e["when"].isoformat().replace("+00:00", "Z"),
            "height_m": e["height_m"],
            "in_hours": round((e["when"] - when).total_seconds() / 3600, 1),
        }

    next_high = next((_fmt(e) for e in future if e["tide_event"] == "HIGH TIDE"), None)
    next_low = next((_fmt(e) for e in future if e["tide_event"] == "LOW TIDE"), None)

    if future and past:
        tidal_state = "RISING" if future[0]["tide_event"] == "HIGH TIDE" else "FALLING"
    else:
        tidal_state = "UNKNOWN"

    range_m = spring_neap = None
    if next_high and next_low:
        range_m = round(abs(next_high["height_m"] - next_low["height_m"]), 2)
        spring = station.get("spring_range_m")
        neap = station.get("neap_range_m")
        if spring and neap:
            midpoint = (spring + neap) / 2
            if range_m >= spring - 0.05:
                spring_neap = "SPRING"
            elif range_m <= neap + 0.05:
                spring_neap = "NEAP"
            elif range_m >= midpoint:
                spring_neap = "MID→SPRING"
            else:
                spring_neap = "MID→NEAP"

    if not events:
        # No heights at all, so claiming they are on chart datum is a claim
        # about numbers that do not exist.
        datum = "n/a — no tide source for this station"
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"No tide source available for station {code}: SOI table has no rows for it "
            "and the Stormglass fallback covers no matching port",
        )
    elif not future:
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"Tide table for {code} ends before the requested time — "
            "no predicted extreme in the published window",
        )
    elif fell_back:
        # Two different reasons land on the same rung and a user deciding
        # whether to trust a height needs to know which: the pilot ports have a
        # chart-datum table that can run out, the nine ports added for national
        # coverage never had one, because no chart-datum offset is published for
        # them that we could cite.
        published = station.get("msl_above_chart_datum_m") is not None
        why = (
            f"SOI 2026 table exhausted for {code}"
            if published
            else f"no SOI chart-datum table is published for {code}"
        )
        confidence = Confidence(
            score="MEDIUM",
            rationale=f"{why}; fell to the declared Stormglass fallback — heights are on "
            "mean sea level, not chart datum",
        )
    elif not (next_high and next_low):
        confidence = Confidence(score="MEDIUM", rationale="Only one of the next high/low falls in the published window")
    else:
        confidence = Confidence(score="HIGH", rationale=f"SOI 2026 predicted tide table, station {code}")

    src = events[0]["source"] if events else "Survey of India 2026 Tide Tables"
    # The SOI table is held locally and computed fresh every call, so "now" is
    # its honest acquisition time. The Stormglass rung is a dated external
    # pull — reporting it as fetched "now" would hide how old that pull is,
    # even though the predictions it contains stay valid until their window
    # runs out (docs/ORCA_Stale_Data_Policy.md §6).
    acquired = when
    if fell_back:
        cached = al.load_stormglass_cache_date(code)
        if cached:
            acquired = datetime.fromisoformat(cached).replace(tzinfo=timezone.utc)
    return TidePrediction(
        station_code=code,
        station_name=station["station_name"],
        next_high=next_high,
        next_low=next_low,
        tidal_state=tidal_state,
        range_m=range_m,
        spring_neap=spring_neap or "UNKNOWN",
        datum=datum,
        fell_back=fell_back,
        source_provenance=SourceProvenance(
            dataset=f"{src} (station {code})",
            acquisition_timestamp=acquired.isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,  # astronomical prediction — the table does not go stale
        ),
        confidence=confidence,
    )


def predicted_height_at(lat: float, lon: float, when: datetime) -> dict[str, Any] | None:
    """Astronomical tide height at an arbitrary instant, cosine-interpolated
    between the SoI table's bracketing high/low events.

    P5.3 (`R-NEW-7`): the gauge reading and the astronomical prediction for
    the same station and hour are both already on disk and were never
    compared. `predict_tides` only names the *next* extreme, not a
    continuous curve, so it cannot answer "what height was predicted at
    14:07" — this does, with the standard half-cosine approximation between
    two known extremes (no harmonic constituents on disk yet; that is
    P5.14's pyTMD/FES2022 scope).

    None when `when` falls outside the bracket the table actually covers —
    no estimate is produced past the table's real edges, since that is
    exactly the fabricated-value failure this cross-check exists to avoid.
    """
    station = nearest_station(lat, lon)
    code = station["station_code"]
    events = sorted(
        (e for e in al.load_soi_tide_events() if e["station_code"] == code),
        key=lambda e: e["when"],
    )
    before = [e for e in events if e["when"] <= when]
    after = [e for e in events if e["when"] > when]
    if not before or not after:
        return None
    e1, e2 = before[-1], after[0]
    span_s = (e2["when"] - e1["when"]).total_seconds()
    if span_s <= 0:
        return None
    frac = (when - e1["when"]).total_seconds() / span_s
    height = e1["height_m"] + (e2["height_m"] - e1["height_m"]) * (1 - math.cos(math.pi * frac)) / 2
    return {
        "station_code": code,
        "station_name": station["station_name"],
        "predicted_height_m": round(height, 3),
        "datum": "chart datum (LAT)",
        "method": "half-cosine interpolation between SoI 2026 bracketing extremes",
    }


# --- part 1: SST / chlorophyll correlation + anomaly ----------------------

def detect_anomaly(value: float, baseline_mean: float, baseline_std: float) -> dict[str, Any]:
    """z-score of a reading against a climatological baseline. |z| >= 2 is
    flagged anomalous — the same 2σ convention the plan's anomaly-band chart
    uses. No baseline → not an anomaly claim, an 'unknown'."""
    if baseline_std <= 0:
        return {"anomalous": False, "z": None, "note": "no usable baseline spread"}
    z = round((value - baseline_mean) / baseline_std, 2)
    return {
        "anomalous": abs(z) >= 2.0,
        "z": z,
        "direction": "above" if z > 0 else "below",
    }


def _freshest(*grids: dict[str, Any] | None) -> dict[str, Any] | None:
    """The freshest readable grid, ties going to the earlier argument.

    discovery.py ranks sources on freshness first (its own docstring: "MOSDAC
    NRT SST chosen over Copernicus CMEMS: 6 h old vs ..."), so a plain
    `a or b` cascade only matches that ranking while the national archive is
    actually the fresher file. It is not always: the EOS-06 chlorophyll
    archive stops at March 2026 while the CMEMS NRT file is days old, and
    correlating across that gap compares two different seasons.
    """
    readable = [g for g in grids if g and g.get("provenance", {}).get("freshness_minutes") is not None]
    if not readable:
        return next((g for g in grids if g), None)
    return min(readable, key=lambda g: g["provenance"]["freshness_minutes"])


def _sst_grid(bbox: dict[str, float] | None) -> dict[str, Any] | None:
    """SST source cascade: ISRO INSAT-3D (national mission data, the answer
    this product should give) against CMEMS, freshest wins; NOAA CoastWatch
    (P5.2, live) only when neither archive on disk reads at all — a live
    fetch is the last rung, not a competitor to freshness-ranked local
    files — and D3's normalized fixture when nothing else reads either."""
    local = _freshest(sl.load_insat_sst(bbox), sl.load_cmems_sst(bbox))
    if local is not None:
        return local
    return sl.load_coastwatch_sst(bbox) or al.load_ocean_grid_fixture("sst")


def _chl_grid(bbox: dict[str, float] | None) -> dict[str, Any] | None:
    """Chlorophyll cascade, same rule: EOS-06 OCM-3 first by authority, CMEMS
    gap-free NRT when it is the fresher of the two, NOAA CoastWatch (P5.2,
    live) only when neither local archive reads."""
    local = _freshest(sl.load_eos06_chl(bbox), sl.load_cmems_chl(bbox))
    if local is not None:
        return local
    return sl.load_coastwatch_chl(bbox) or al.load_ocean_grid_fixture("chl")


def correlate_sst_chlorophyll(bbox: dict[str, float] | None = None) -> dict[str, Any]:
    """Cross-source SST + chlorophyll relationship over a bbox.

    Reads the ISRO archives directly (INSAT-3D L3B SST, EOS-06 OCM L4
    chlorophyll), co-locating them on a 0.25° grid because the two products
    are on different native grids and a pairwise correlation between
    unaligned series is a number about nothing. Either side falls back to
    CMEMS when CMEMS holds the fresher granule, and to D3's fixture when
    neither archive reads; if none of the three rungs yields a grid this still
    returns available=False with the reason rather than a synthesised number.

    "Correlated with", never "caused by": upwelling raises chlorophyll and
    lowers SST together, but this function measures association only.
    """
    sst = _sst_grid(bbox)
    chl = _chl_grid(bbox)
    if sst is None or chl is None:
        missing = [n for n, v in (("SST", sst), ("chlorophyll", chl)) if v is None]
        return {
            "available": False,
            "note": f"no readable gridded source for {', '.join(missing)} "
                    "(tried INSAT-3D/CMEMS for SST, EOS-06/CMEMS for chlorophyll)",
            "confidence": Confidence(score="LOW_DATA", rationale="gridded ocean-colour / SST inputs not available"),
        }

    sst_cells = sl.bin_to_grid(sst.get("frame", []))
    chl_cells = sl.bin_to_grid(chl.get("frame", []))
    shared = sorted(set(sst_cells) & set(chl_cells))
    if len(shared) < 3:
        return {
            "available": False,
            "note": f"grids read but only {len(shared)} co-located 0.25 deg cells — "
                    "the SST and chlorophyll granules do not overlap enough to compare",
            "sst_provenance": sst.get("provenance"),
            "chl_provenance": chl.get("provenance"),
            "confidence": Confidence(score="LOW_DATA", rationale="insufficient overlapping SST/chl cells"),
        }

    r = _pearson([sst_cells[c] for c in shared], [chl_cells[c] for c in shared])
    n = len(shared)
    # The two granules can still be days or months apart even after the
    # freshness pick — nothing guarantees both archives ran the same week.
    # Saying so is the difference between an honest association and an
    # implied simultaneity.
    lag_note = _acquisition_gap(sst.get("provenance"), chl.get("provenance"))
    tier = Confidence(
        score="MEDIUM" if n < 20 or lag_note else "HIGH",
        rationale=f"{n} co-located SST/chlorophyll cells at 0.25 deg"
                  + (f"; {lag_note}" if lag_note else ""),
    )
    # Stale-data policy: a correlation over two old-but-simultaneous granules
    # (no acquisition_gap, same week, both from March) would otherwise read
    # HIGH — this is the check that catches that case.
    band = _worst_band(sst.get("provenance"), chl.get("provenance"))
    confidence = tier if not band or band == "fresh" else _worst(
        tier, Confidence(score={"hint": "MEDIUM", "history": "LOW_DATA"}[band],
                          rationale=f"granule(s) in the '{band}' recency band"),
    )
    return {
        "available": True,
        "pearson_r": round(r, 3),
        "relationship": _describe_r(r),
        "n_samples": n,
        "grid_resolution_deg": 0.25,
        "acquisition_gap": lag_note,
        "sst_provenance": sst.get("provenance"),
        "chl_provenance": chl.get("provenance"),
        "confidence": confidence,
    }


def _acquisition_gap(sst_prov: dict[str, Any] | None, chl_prov: dict[str, Any] | None) -> str | None:
    """Human-readable gap between the two granules' acquisition times, or None
    when they are within a day of each other."""
    if sst_prov is None or chl_prov is None:
        return None
    try:
        t_sst = datetime.fromisoformat(sst_prov["acquisition_timestamp"].replace("Z", "+00:00"))
        t_chl = datetime.fromisoformat(chl_prov["acquisition_timestamp"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    days = abs((t_sst - t_chl).days)
    if days <= 1:
        return None
    return f"SST and chlorophyll granules are {days} days apart — association, not a simultaneous observation"


_BAND_RANK = {"fresh": 0, "hint": 1, "history": 2}


def _worst_band(*provenances: dict[str, Any] | None) -> str | None:
    """The staler of the two granules' recency bands (`satellite_loaders`
    tags each with one at load time). None when neither carries a band —
    the D3 fixture rung predates the policy and is exempt."""
    bands = [p["band"] for p in provenances if p and p.get("band")]
    return max(bands, key=lambda b: _BAND_RANK.get(b, 0)) if bands else None


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx > 0 and sy > 0 else 0.0


def _describe_r(r: float) -> str:
    mag = abs(r)
    strength = "strong" if mag >= 0.7 else "moderate" if mag >= 0.4 else "weak"
    sign = "inverse" if r < 0 else "positive"
    return f"{strength} {sign} correlation"


# --- part 2: PFZ proximity, persistence, sector status --------------------

@dataclass(frozen=True)
class NearestPFZ:
    found: bool
    landing_center: str | None
    distance_km: float | None
    bearing_deg: float | None
    compass: str | None
    depth_m: str | None
    latitude: float | None
    longitude: float | None
    valid_for: str | None
    sector_id: str | None
    # docs/ORCA_Stale_Data_Policy.md — the advisory's age, so no surface can
    # present a cloud-season zone as today's. None when nothing was found.
    age_days: int | None = None
    band: str | None = None  # fresh | hint | history
    expired: bool | None = None
    max_km: float | None = None  # the reach the search was capped at
    # INCOIS's own landmark description of the zone ("52-57 km NW of
    # Kunzhathur"). A different origin from distance_km/compass, which are
    # ORCA's, measured from the queried point — kept apart so no answer can
    # read "32 km WSW of Kunzhathur", a distance from one place and a name
    # from another.
    incois_reference: str | None = None


# Beyond this a "nearest" zone is on another coast: the 906 km Betul answer to
# "PFZs near Rameswaram". None within reach is the honest result past it.
# ponytail: one fixed reach for every boat; per-vessel reach (cruise speed)
# is what /zones' fisherman view already computes if this needs to follow it.
PFZ_MAX_REACH_KM = 150.0


def nearest_pfz(
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
    *,
    sector_id: str | None = None,
    max_km: float = PFZ_MAX_REACH_KM,
) -> NearestPFZ:
    """Closest INCOIS PFZ advisory node to a point within `max_km`, with
    distance, true bearing and 16-point compass heading — 'which way and how
    far', the only form of this answer usable from a boat.

    Searches every sector's *latest* advisory (analytics_loaders.load_pfz_latest),
    not only today's file: a cloud-covered sector still has zones, and the
    result carries their age so the caller says how old they are."""
    rows = al.load_pfz_latest()
    if sector_id:
        rows = [r for r in rows if r.get("sector_id") == sector_id]
    parsed: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        try:
            plat, plon = float(r["latitude_dd"]), float(r["longitude_dd"])
        except (KeyError, ValueError):
            continue
        dist = _km_between(lat, lon, plat, plon)
        if dist <= max_km:
            parsed.append((dist, r))
    if not parsed:
        return NearestPFZ(False, None, None, None, None, None, None, None, None, sector_id, max_km=max_km)
    dist_km, row = min(parsed, key=lambda t: t[0])
    plat, plon = float(row["latitude_dd"]), float(row["longitude_dd"])
    bearing, _ = geospatial.bearing_and_distance(lat, lon, plat, plon)
    return NearestPFZ(
        found=True,
        landing_center=row.get("landing_center"),
        distance_km=round(dist_km, 1),
        bearing_deg=round(bearing),
        compass=_compass(bearing),
        depth_m=row.get("depth_m"),
        latitude=plat,
        longitude=plon,
        valid_for=row.get("valid_for"),
        sector_id=row.get("sector_id"),
        age_days=row.get("age_days"),
        band=row.get("band"),
        expired=row.get("expired"),
        max_km=max_km,
        incois_reference=_incois_reference(row),
    )


def _incois_reference(row: dict[str, Any]) -> str | None:
    landing, dist, direction = row.get("landing_center"), row.get("distance_km"), row.get("direction")
    if not (landing and dist and direction):
        return None
    return f"{dist} km {direction} of {landing}"


def score_pfz_persistence(
    lat: float,
    lon: float,
    *,
    sector_id: str,
    radius_km: float = 25.0,
    window_days: int = 7,
    min_days: int = 5,
) -> dict[str, Any]:
    """How consistently a PFZ has been advised near a point across the
    archived daily runs. score = (days with an advisory node within
    `radius_km`) / (days on record). Fewer than `min_days` snapshots → the
    score is 'indicative' and confidence is LOW_DATA — one day is not a trend,
    and neither are three.

    Only snapshots from the last `window_days` count. The archive also holds
    older runs, and a fortnight-old advisory is not evidence about this week:
    counting it silently changes the denominator of a number the user reads as
    "how reliable is this spot right now". The daily PFZ job accumulates one
    snapshot per morning, so the window fills itself; until it does, this says
    so rather than scoring 0/3 and labelling the result TRANSIENT.
    """
    cutoff = (_now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    by_date = al.pfz_advisories_by_date()
    archived = list(by_date)
    dates = [d for d in archived if d >= cutoff]
    hits = 0
    for date in dates:
        nodes = by_date[date]
        near = False
        for node in nodes:
            if sector_id and node.get("sector_id") != sector_id:
                continue
            try:
                nlat, nlon = float(node["latitude_dd"]), float(node["longitude_dd"])
            except (KeyError, ValueError):
                continue
            if _km_between(lat, lon, nlat, nlon) <= radius_km:
                near = True
                break
        hits += int(near)

    n = len(dates)
    score = round(hits / n, 2) if n else None
    if n < min_days:
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"only {n} PFZ snapshot(s) in the last {window_days} days "
            f"({len(archived)} on record in total) — persistence needs a run of days, "
            f"and {min_days} is the shortest run this will score",
        )
        label = "INDICATIVE"
    elif score is not None and score >= 0.6:
        confidence = Confidence(score="MEDIUM", rationale=f"advisory present near this point on {hits}/{n} archived days")
        label = "PERSISTENT"
    else:
        confidence = Confidence(score="MEDIUM", rationale=f"advisory present near this point on {hits}/{n} archived days")
        label = "TRANSIENT"

    return {
        "score": score,
        "label": label,
        "days_present": hits,
        "days_on_record": n,
        "window_days": window_days,
        "days_archived_total": len(archived),
        "radius_km": radius_km,
        "confidence": confidence,
    }


def sector_status(sector_id: str = _PILOT_SECTOR) -> dict[str, Any]:
    """First-class sector status. A cloud-suppressed sector returns
    NO_DATA_CLOUD_COVER carrying INCOIS's own message text — never an empty
    result that reads as an ORCA failure (data audit C-2)."""
    status = al.load_pfz_sector_status()
    names = status.get("sector_names", {})
    latest = _latest_advisory(sector_id)
    for sec in status.get("sectors", []):
        if sec.get("sector_id") == sector_id:
            return {
                "sector_id": sector_id,
                "sector_name": names.get(sector_id, sec.get("sector")),
                "status": sec.get("status"),
                "message": sec.get("message") or _default_status_message(sec.get("status")),
                "node_count": sec.get("node_count", 0),
                "valid_for": sec.get("valid_for"),
                "is_data_gap": sec.get("status") not in ("HAS_ADVISORY", None),
                "latest_advisory": latest,
            }
    return {
        "sector_id": sector_id,
        "sector_name": names.get(sector_id),
        "status": "UNKNOWN",
        "message": "This sector is not present in the current INCOIS PFZ status feed.",
        "node_count": 0,
        "valid_for": None,
        "is_data_gap": True,
        "latest_advisory": latest,
    }


def _latest_advisory(sector_id: str) -> dict[str, Any] | None:
    """The sector's most recent advisory ORCA holds, whatever today's status
    says — so "no data today (cloud)" can go on to "last advisory 19 Sep, 34
    km out" instead of stopping. None only when the sector has never had one."""
    rows = [r for r in al.load_pfz_latest() if r.get("sector_id") == sector_id]
    if not rows:
        return None
    first = rows[0]
    return {
        "valid_for": first.get("valid_for"),
        "node_count": len(rows),
        "age_days": first.get("age_days"),
        "band": first.get("band"),
        "expired": first.get("expired"),
    }


def all_sector_status() -> list[dict[str, Any]]:
    """Every sector SEC001–SEC014, in id order (plan §4 D2 Day 12 — `/zones`
    shows sector status per SEC001–SEC014, not only the user's own). A sector
    missing from the feed still gets a row saying so; the list length is the
    roster, not whatever happened to be published."""
    feed = al.load_pfz_sector_status()
    names: dict[str, str] = feed.get("sector_names", {})
    roster = sorted(names) or [f"SEC{n:03d}" for n in range(1, 15)]
    return [sector_status(sid) for sid in roster]


def _default_status_message(status: str | None) -> str:
    return {
        "NO_DATA_CLOUD_COVER": "No data available for this sector due to excessive cloud cover",
        "HAS_ADVISORY": "Advisory published for this sector",
    }.get(status or "", f"Sector status: {status}")


# --- wind rose (the fourth §5.9 chart's data) ---------------------------

# Beaufort-ish working bins for a small fishing vessel, in m/s: what you can
# work in, what you watch, what keeps you in port.
_WIND_BINS: tuple[tuple[str, float, float], ...] = (
    ("calm_0_5", 0.0, 5.0),
    ("moderate_5_10", 5.0, 10.0),
    ("strong_10_plus", 10.0, float("inf")),
)


def wind_rose(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> dict[str, Any]:
    """Directional wind frequency over the cached forecast window, binned into
    the 16 compass sectors × three working speed bands — the data behind the
    §5.9 WindRose chart.

    Reads the cached Open-Meteo weather fixture Agent 4 already keeps on disk
    (m/s after `normalize_to_common_frame`'s convention is applied here at the
    one place that needs it: the fixture stores km/h). Direction is the
    meteorological convention — the direction the wind is coming FROM.
    """
    from orca.data.loaders import CACHED_WEATHER_PORTS, cached_weather_path, load_json
    from orca.data.normalize import kmh_to_ms

    # Read each port's own coordinates once, from the fixture itself, rather
    # than keeping a second hand-maintained registry that can drift from it.
    coords = {p: c for p in CACHED_WEATHER_PORTS if (c := _port_latlon(p)) is not None}
    if not coords:
        return {
            "available": False,
            "note": "no cached weather fixtures on disk",
            "confidence": Confidence(score="LOW_DATA", rationale="wind fixture missing"),
        }
    port = min(coords, key=lambda p: _km_between(lat, lon, *coords[p]))

    raw = load_json(cached_weather_path(port))
    hourly = raw.get("hourly", {})
    speeds = hourly.get("wind_speed_10m") or []
    directions = hourly.get("wind_direction_10m") or []

    # counts[compass][bin] — the roster is fixed so an unrepresented sector
    # renders as a zero spoke rather than vanishing from the rose.
    counts = {c: {b[0]: 0 for b in _WIND_BINS} for c in _COMPASS_16}
    total = 0
    for spd_kmh, deg in zip(speeds, directions):
        if spd_kmh is None or deg is None:
            continue
        spd = kmh_to_ms(float(spd_kmh))
        sector = _compass(float(deg))
        for name, lo, hi in _WIND_BINS:
            if lo <= spd < hi:
                counts[sector][name] += 1
                total += 1
                break

    if total == 0:
        return {
            "available": False,
            "note": "cached wind fixture carries no usable speed/direction pairs",
            "confidence": Confidence(score="LOW_DATA", rationale="no usable wind readings"),
        }

    return {
        "available": True,
        "port": port,
        "hours_counted": total,
        "bins": [b[0] for b in _WIND_BINS],
        "petals": [{"compass": c, **counts[c]} for c in _COMPASS_16],
        "dataset": f"Open-Meteo Forecast API (cached, port={port})",
        "confidence": Confidence(
            score="MEDIUM",
            rationale=f"{total} cached hourly wind readings at {port}; a forecast window, not a climatology",
        ),
    }


# A gauge further than this is a different stretch of coast; its observed
# level says nothing about the user's. INCOIS runs 6 gauges nationally, so
# most of the coastline legitimately has none in range.
_TIDE_GAUGE_MAX_KM = 150.0

# --- the live gauge feed (freshness contract: `incois_tide_gauge` is LIVE) ---
#
# INCOIS's own TEWS endpoint (tsunami.incois.gov.in/TEWS/tg_data.jsp) returns 404,
# which is why `incois_tide_gauge_telemetry.json` beside it was only ever a schema
# fixture with representative values — not readings. A gauge is an instrument: a
# made-up water level is not a degraded measurement, it is a false one.
#
# The IOC/UNESCO Sea Level Monitoring facility carries the same Indian gauges,
# unauthenticated, at one-minute resolution, so LIVE can actually be honoured.
IOC_SEA_LEVEL_URL = "https://www.ioc-sealevelmonitoring.org/service.php"
IOC_TIMEOUT_S = 12.0
# Only the five Indian coastal gauges that actually return a series. IOC also lists
# Minicoy, Veraval and Visakhapatnam, all of which answer with an empty array — a
# station that publishes nothing is worse than no station, because it would win the
# nearest-gauge search and then have no reading to give. DART platforms are excluded
# on purpose: deep-ocean tsunami pressure recorders, not coastal tide gauges.
IOC_GAUGES: tuple[tuple[str, str, float, float], ...] = (
    ("chenn", "Chennai", 13.10, 80.30),
    ("coch", "Cochin", 9.96, 76.26),
    ("marm", "Marmagao", 15.41, 73.80),
    ("ptbl", "Port Blair", 11.68, 92.76),
    ("nanc", "Nancowry", 8.05, 93.55),
)


def _fetch_ioc_gauge(code: str) -> tuple[float, datetime] | None:
    """Newest sea level (m) and its UTC timestamp from one IOC gauge, or None.

    `period=0.05` is roughly the last 72 minutes — enough that a gauge which has
    briefly stopped reporting comes back empty rather than handing us an hours-old
    value dressed as current.
    """
    import httpx

    try:
        resp = httpx.get(IOC_SEA_LEVEL_URL, timeout=IOC_TIMEOUT_S,
                         params={"query": "data", "code": code,
                                 "period": 0.05, "format": "json"})
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            return None
        last = rows[-1]
        when = datetime.strptime(last["stime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return float(last["slevel"]), when
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return None


def tide_gauge_observation(lat: float, lon: float) -> dict[str, Any]:
    """Observed sea level at the nearest INCOIS tide gauge, against that
    gauge's own astronomical prediction.

    `predict_tides` returns *predicted* heights and says so; this is the
    observed cross-check that docstring promises, and it was the one dataset
    in the ledger still marked wired with no caller behind it. The residual
    (observed minus predicted) is the gauge's published `sea_level_anomaly_m`
    — a storm surge or a set-up, not an error in the tide table.

    `tsunami_trigger_state` is carried through verbatim from INCOIS. ORCA
    does not interpret it, threshold it, or derive a verdict from it: a
    tsunami determination is INCOIS's to make, and reporting their state is
    the honest thing a client can do with it.

    Six gauges cannot cover 7,500 km of coast, so a point with none in range
    falls through to CMEMS altimetry (`source_kind: satellite_altimetry`)
    rather than returning nothing. The two are not interchangeable and the
    reply says which one it is.
    """
    live = _live_gauge_observation(lat, lon)
    if live is not None:
        return live

    # No live gauge in range, or the feed is down. The fall-through is altimetry,
    # NOT `incois_tide_gauge_telemetry.json`: that file was written as a schema
    # fixture with representative values because INCOIS's TEWS endpoint 404s
    # (docs/archive/data_verification_audit.md), so its water levels were never
    # readings. Serving one would be a fabricated instrument observation on a
    # safety path — strictly worse than admitting there is no gauge here.
    return _altimetric_sea_level(
        lat, lon,
        f"no live IOC gauge within {_TIDE_GAUGE_MAX_KM:.0f} km reporting right now",
    )


def _live_gauge_observation(lat: float, lon: float) -> dict[str, Any] | None:
    """The nearest live IOC gauge in range, or None to let the caller fall back.

    Returns only what the feed actually carries. IOC publishes sea level and a
    timestamp — not an astronomical prediction, not a water temperature, and not a
    tsunami determination. Those come back `None` with `fields_unavailable` naming
    them, because the alternative is to fill them from the fixture and present
    invented numbers beside a real one, which is the failure this whole change
    exists to undo. A tsunami call stays INCOIS's to make and ORCA will not imply
    one from a pressure reading.
    """
    in_range = [
        (code, name, glat, glon, _km_between(lat, lon, glat, glon))
        for code, name, glat, glon in IOC_GAUGES
    ]
    code, name, glat, glon, km = min(in_range, key=lambda g: g[4])
    if km > _TIDE_GAUGE_MAX_KM:
        return None  # caller decides between the cached roster and altimetry

    reading = _fetch_ioc_gauge(code)
    if reading is None:
        return None
    level_m, observed_at = reading
    age_min = (datetime.now(timezone.utc) - observed_at).total_seconds() / 60.0

    # P5.3 (`R-NEW-7`) — the observed-versus-predicted cross-check. Both
    # numbers were already on disk and never compared. `predicted_height_at`
    # is keyed to the GAUGE's own position (glat/glon), not the caller's —
    # the prediction has to be for the same station the reading came from.
    predicted = predicted_height_at(glat, glon, observed_at)
    predicted_m = predicted["predicted_height_m"] if predicted else None
    anomaly_m = round(level_m - predicted_m, 3) if predicted_m is not None else None
    unavailable = ["water_temp_c", "tsunami_trigger_state"]
    if predicted_m is None:
        unavailable = ["predicted_astronomical_m", "sea_level_anomaly_m", *unavailable]

    # A divergence beyond this floors confidence one tier — same rule P2.4
    # applies to the wave/wind reconciliation, second variable (P5.3). Not a
    # measured constant: a disclosed cut wide enough to clear the datum-offset
    # caveat above and still catch a genuine storm-surge-magnitude anomaly.
    _ANOMALY_TOLERANCE_M = 0.3
    diverged = anomaly_m is not None and abs(anomaly_m) > _ANOMALY_TOLERANCE_M
    confidence = (
        Confidence(
            score="MEDIUM",
            rationale=(f"observed-vs-predicted residual at {name} is {anomaly_m:+.2f} m, "
                       f"beyond the {_ANOMALY_TOLERANCE_M:.1f} m tolerance — reduced one tier"),
        )
        if diverged else
        Confidence(score="HIGH", rationale=f"live gauge reading at {name}, {km:.0f} km away, {age_min:.0f} min old")
    )

    return {
        "available": True,
        "source_kind": "in_situ_gauge",
        "station_id": f"IOC_{code.upper()}",
        "station_name": name,
        "distance_km": round(km, 1),
        "observed_level_m": round(level_m, 4),
        "predicted_astronomical_m": predicted_m,
        "sea_level_anomaly_m": anomaly_m,
        # IOC publishes sea level against the gauge's own local station zero,
        # not necessarily the SoI table's chart datum (LAT) — so this residual
        # can carry a fixed per-station offset alongside any real surge. A
        # sustained, growing anomaly is the storm-surge-setup signal the plan
        # calls out; a single reading's exact value should not be over-read.
        "anomaly_datum_caveat": (
            None if predicted_m is None else
            "residual is against SoI chart datum (LAT); the gauge's own reference "
            "may carry a fixed offset from that datum — read a sustained trend, "
            "not one instant"
        ),
        "water_temp_c": None,
        "sensor_type": "pressure (prs)",
        "status": "OPERATIONAL",
        "tsunami_trigger_state": None,
        "fields_unavailable": unavailable,
        "observed_at_utc": observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observation_age_minutes": round(age_min, 1),
        "dataset": "IOC/UNESCO Sea Level Monitoring — Indian gauge network (live)",
        "confidence": confidence,
    }


def _altimetric_sea_level(lat: float, lon: float, why: str) -> dict[str, Any]:
    """Satellite altimetry standing in for an out-of-range tide gauge.

    INCOIS runs six gauges nationally, so most of the coastline has none
    within 150 km and PS-Q "is the water standing higher than usual here?"
    had no answer at all outside those six. CMEMS DUACS covers the whole
    bbox at 0.125 deg. It is a different measurement and is labelled as one:
    an anomaly against a 20-year mean sea surface, not a residual against
    tonight's astronomical prediction, and it carries no tsunami state —
    that determination stays INCOIS's alone.
    """
    alt = sl.load_cmems_ssh(lat, lon)
    if alt is None:
        return {
            "available": False,
            "note": f"{why}; no CMEMS sea-level file on disk either",
            "confidence": Confidence(score="LOW_DATA", rationale="no tide gauge in range and no altimetry fallback"),
        }
    return {
        "available": True,
        "source_kind": "satellite_altimetry",
        "station_id": None,
        "station_name": None,
        "sea_level_anomaly_m": alt["sea_level_anomaly_m"],
        "absolute_dynamic_topography_m": alt["absolute_dynamic_topography_m"],
        "observed_level_m": None,
        "predicted_astronomical_m": None,
        "tsunami_trigger_state": None,
        "observed_at_ist": None,
        "acquisition_timestamp": alt["provenance"]["acquisition_timestamp"],
        "dataset": alt["provenance"]["dataset"],
        "provenance": alt["provenance"],
        "note": f"{why}; substituted satellite altimetry, which is an anomaly "
                "against a multi-year mean sea surface, not a residual against a tide prediction",
        "confidence": Confidence(
            score="MEDIUM",
            rationale=f"CMEMS DUACS sla averaged over {alt['cells_averaged']} cells "
                      f"within {alt['sample_radius_deg']} deg; no in-situ gauge within "
                      f"{_TIDE_GAUGE_MAX_KM:.0f} km",
        ),
    }


def wind_anomaly(lat: float, lon: float) -> dict[str, Any]:
    """Is the coming forecast window unusual against the ERA5 reference period?

    `detect_anomaly` has existed since Phase 2 and took a baseline mean and
    sigma no caller could supply — so PS-Q7's word "anomaly" had no reference
    period behind it. This supplies one: the cached ERA5 reanalysis window
    (`tier1/weather/era5_historical_<port>_30d.json`), compared against the
    peak wind in the same port's cached forecast.

    Both sides are km/h, straight from Open-Meteo's own units, so no unit
    conversion happens here at all — the comparison is like-for-like or it
    does not happen. A 30-day window is a short baseline and the returned
    `baseline_label` says exactly what it is: this supports "unusual for the
    last month", never "unusual for this time of year".
    """
    from orca.data.loaders import CACHED_WEATHER_PORTS, cached_weather_path, load_json

    coords = {p: c for p in CACHED_WEATHER_PORTS if (c := _port_latlon(p)) is not None}
    if not coords:
        return {
            "available": False,
            "note": "no cached weather fixtures on disk",
            "confidence": Confidence(score="LOW_DATA", rationale="wind fixture missing"),
        }
    port = min(coords, key=lambda p: _km_between(lat, lon, *coords[p]))

    baseline = al.load_era5_baseline(port)
    if baseline is None:
        # ERA5 is cached for the pilot port only. Saying which port has one is
        # more useful than a bare "no": it names the download that would fix it.
        held = sorted(p for p in CACHED_WEATHER_PORTS if al.load_era5_baseline(p) is not None)
        return {
            "available": False,
            "nearest_port": port,
            "note": f"no ERA5 reference period cached for {port} "
                    f"(held for: {', '.join(held) or 'none'}) — anomaly needs a baseline, "
                    "and ORCA will not compare a forecast against a climatology it does not have",
            "confidence": Confidence(score="LOW_DATA", rationale=f"no ERA5 baseline for {port}"),
        }

    stats = baseline["variables"].get("wind_speed_10m_max")
    speeds = [v for v in (load_json(cached_weather_path(port)).get("hourly", {}).get("wind_speed_10m") or []) if v is not None]
    if stats is None or not speeds or stats["std"] <= 0:
        return {
            "available": False,
            "nearest_port": port,
            "note": "ERA5 baseline or forecast wind series unusable (missing variable, empty series, or zero variance)",
            "confidence": Confidence(score="LOW_DATA", rationale="baseline/forecast pair incomplete"),
        }

    observed = max(float(v) for v in speeds)
    result = detect_anomaly(observed, stats["mean"], stats["std"])
    return {
        "available": True,
        "nearest_port": port,
        "variable": "wind_speed_10m_max",
        "units": stats["units"] or "km/h",
        "observed_peak": round(observed, 1),
        "baseline_mean": stats["mean"],
        "baseline_std": stats["std"],
        "baseline_label": baseline["label"],
        "baseline_days": stats["n_days"],
        "z": result["z"],
        "anomalous": result["anomalous"],
        "direction": result["direction"],
        "dataset": baseline["dataset"],
        "confidence": Confidence(
            score="MEDIUM",
            rationale=f"{stats['n_days']}-day ERA5 reference period at {port} — a monthly baseline, not a seasonal climatology",
        ),
    }


# P5.25 (`R-EDGE-2`, orca_final §9.2/§18.1) — "was last week rougher?" needs
# an actual value on a specific past date, not the mean/std `wind_anomaly`
# already reads. `wind_speed_10m_max` is the only per-day variable the
# cached ERA5 extract carries (no stored daily wave-height history exists on
# disk — WW3 point extracts are forecast-only, never archived) — the answer
# says which variable it is rather than implying it covers wave height too.
_HISTORICAL_DAYS_BACK = {"last month": 30, "a month ago": 30, "last week": 7, "a week ago": 7}
_DEFAULT_HISTORICAL_DAYS_BACK = 7


def historical_comparison(lat: float, lon: float, query: str) -> dict[str, Any]:
    """Compare a referenced past date's ERA5 wind peak against today's
    forecast peak, at the nearest port with a cached archive. Outside the
    archive's actual span, an honest refusal naming that span — never a
    guessed value for a date ORCA does not hold."""
    from datetime import timedelta

    from orca.data.loaders import CACHED_WEATHER_PORTS, cached_weather_path, load_json

    coords = {p: c for p in CACHED_WEATHER_PORTS if (c := _port_latlon(p)) is not None}
    if not coords:
        return {"available": False, "statement": "No cached weather archive on disk to compare against."}
    port = min(coords, key=lambda p: _km_between(lat, lon, *coords[p]))

    baseline = al.load_era5_baseline(port)
    daily = al.load_era5_daily_series(port)
    if baseline is None or daily is None:
        return {"available": False, "statement": f"No ERA5 archive is cached for {port} — nothing to compare against."}

    query_lower = query.lower()
    days_back = next((n for phrase, n in _HISTORICAL_DAYS_BACK.items() if phrase in query_lower), _DEFAULT_HISTORICAL_DAYS_BACK)
    target_date = (_now() - timedelta(days=days_back)).date().isoformat()

    dates = daily.get("time") or []
    if target_date not in dates:
        return {
            "available": False,
            "statement": f"The ERA5 archive for {port} covers {baseline['period_start']}..{baseline['period_end']} "
                         f"only — {target_date} is outside that window.",
        }
    past_value = (daily.get("wind_speed_10m_max") or [None] * len(dates))[dates.index(target_date)]
    speeds = [v for v in (load_json(cached_weather_path(port)).get("hourly", {}).get("wind_speed_10m") or []) if v is not None]
    today_value = max(float(v) for v in speeds) if speeds else None
    if past_value is None or today_value is None:
        return {"available": False, "statement": f"Wind data for {port} on one of the two dates is missing."}

    comparison = "rougher" if past_value > today_value else ("calmer" if past_value < today_value else "about the same")
    return {
        "available": True,
        "port": port,
        "variable": "wind_speed_10m_max",
        "target_date": target_date,
        "past_value": round(float(past_value), 1),
        "today_value": round(today_value, 1),
        "comparison": comparison,
        "dataset": baseline["dataset"],
        "statement": (
            f"{target_date} at {port} (ERA5 archive): peak wind {float(past_value):.1f} km/h. "
            f"Today's forecast peak: {today_value:.1f} km/h. {target_date} was {comparison} — wind only, "
            "no stored daily wave-height history exists to compare."
        ),
    }


# Beyond this the extracted point is a different sea state, not this one. The
# OSF grids are ~1/12 deg, so 60 km is many cells away — far enough that the
# honest answer is "no nearby extraction", not a stretched one.
_OSF_POINT_MAX_KM = 60.0
# The grid is 0.5 deg (~55 km) spaced, so half a diagonal is ~39 km — past
# that the query point is nearer some other cell that is not on the grid at
# all, i.e. outside the extraction's footprint.
_OSF_GRID_MAX_KM = 40.0


def nearest_osf_point_forecast(lat: float, lon: float) -> dict[str, Any]:
    """INCOIS OSF wave + current conditions at the nearest pre-extracted point.

    `scripts/extract_osf_pilot.py` already pulled per-port series out of the
    16 GB HYCOM/WW3 NetCDF pair, and nothing read them: every per-point
    question re-opened a 9.9 GB file instead. This is the fast path — a JSON
    read for a single-point answer, with the grids left for actual grids.

    Returns available=False rather than the nearest-of-anything when the
    position is outside `_OSF_POINT_MAX_KM` of every extraction.
    """
    out: dict[str, Any] = {"available": False}
    best: dict[str, Any] = {}
    for product in ("ww3", "hycom"):
        points = al.load_osf_point_forecasts(product)
        if not points:
            continue
        nearest = min(points, key=lambda p: _km_between(lat, lon, p["lat"], p["lon"]))
        km = _km_between(lat, lon, nearest["lat"], nearest["lon"])
        if km > _OSF_POINT_MAX_KM:
            continue
        # Stale-data policy: `forecast_time` is the step nearest "now" at the
        # moment `extract_osf_pilot.py` last ran, so its own age is the age of
        # that run — a source id per product, same DAILY bands as PFZ.
        source_id = "incois_osf_ww3" if product == "ww3" else "incois_osf_hycom"
        best[product] = {
            "location": nearest.get("location"),
            "base_port": nearest.get("base_port"),
            "distance_km": round(km, 1),
            "forecast_time": nearest.get("forecast_time"),
            **recency(source_id, (nearest.get("forecast_time") or "")[:10]),
            **{k: v for k, v in nearest.items()
               if k not in ("lat", "lon", "location", "base_port", "forecast_time",
                            "target_lat", "target_lon", "grid_lat", "grid_lon")},
        }

    if not best:
        # Second rung: the 400-cell south-India grid extracted from the same
        # NetCDF pair. Coarser (0.5 deg) and regional rather than per-port,
        # which is why it is tried second and labelled as a grid cell.
        cells = al.load_osf_marine_grid()
        if cells:
            cell = min(cells, key=lambda c: _km_between(lat, lon, c["latitude"], c["longitude"]))
            km = _km_between(lat, lon, cell["latitude"], cell["longitude"])
            if km <= _OSF_GRID_MAX_KM:
                return {
                    "available": True,
                    "grid_cell": {
                        "distance_km": round(km, 1),
                        "latitude": cell["latitude"],
                        "longitude": cell["longitude"],
                        **{k: v for k, v in cell.items() if k not in ("latitude", "longitude")},
                    },
                    "dataset": "INCOIS Ocean State Forecast — south-India 0.5 deg marine grid (pre-extracted)",
                    "confidence": Confidence(
                        score="LOW_DATA",
                        rationale=f"nearest 0.5 deg OSF grid cell is {km:.0f} km away — a regional value, not this position",
                    ),
                }
        return {
            **out,
            "note": f"no INCOIS OSF extraction within {_OSF_POINT_MAX_KM:.0f} km of this position, "
                    f"and no grid cell within {_OSF_GRID_MAX_KM:.0f} km "
                    "(both extractions cover south India only)",
            "confidence": Confidence(score="LOW_DATA", rationale="position outside the extracted OSF point set and grid"),
        }

    return {
        "available": True,
        "wave": best.get("ww3"),
        "ocean": best.get("hycom"),
        "dataset": "INCOIS Ocean State Forecast — WW3 waves + HYCOM currents (pre-extracted point series)",
        "confidence": Confidence(
            score="MEDIUM",
            rationale="single-cell extraction from the OSF grids, at the nearest cached point rather than this exact position",
        ),
    }


def _port_latlon(port: str) -> tuple[float, float] | None:
    from orca.data.loaders import cached_weather_path, load_json

    path = cached_weather_path(port)
    if not path.exists():
        return None
    d = load_json(path)
    return d["latitude"], d["longitude"]


# --- part 3: diagnostic DEEP mode ---------------------------------------

# Drivers text in the catch dataset that name a productivity mechanism. The
# match is on the recorded driver string, not a claim ORCA invents.
_SST_STRESS_MARKERS = ("sst anomaly", "marine heatwave", "thermal stress", "bleaching", "warm water", "warm water pool", "el nino", "el niño")
_UPWELLING_MARKERS = ("upwelling", "chakara", "mudbank", "convective mixing", "nutrient enrichment")


def _state_landings_record(place: str, district_years: int) -> dict[str, Any]:
    """What CMFRI recorded for a state, when the district series is too short.

    The district file covers four Tamil Nadu districts; before the CMFRI
    booklet was extracted (runbook §C2) every other coastline got
    "insufficient data" and nothing else. A single-year state estimate is not
    a trend and is not dressed as one — `verdict` says so, the confidence
    stays LOW_DATA, and CMFRI's own paragraph is quoted rather than
    paraphrased into a cause.
    """
    needle = place.lower().strip()
    match = next(
        (r for r in al.load_cmfri_state_landings()
         if needle in r["State"].lower() or r["State"].lower() in needle),
        None,
    )
    if match is None:
        # P5.10 (R-INDIA-5, catch half) — name what IS on record, not just what
        # isn't: "why has Kakinada declined" must read as "I have landings
        # data for these four districts; Kakinada is not among them", never
        # a trend quietly reasoned from the national/state aggregate as if it
        # were local to a place that has none.
        covered = sorted({r["District_Sector"] for r in al.load_fish_landings()})
        return {
            "district": place,
            "verdict": "insufficient data",
            "detail": (
                f"I have landings data for these {len(covered)} districts: {', '.join(covered)}. "
                f"'{place}' is not among them (only {district_years} year(s) on record for it), "
                "and no CMFRI state estimate covers it either."
            ),
            "factors": [],
            "confidence": Confidence(score="LOW_DATA", rationale="fewer than 3 years of catch data"),
        }

    prov = al.load_cmfri_provenance()
    return {
        "district": place,
        "state": match["State"],
        "verdict": "single-year state record — not a trend",
        "detail": f"{match['State']} landed {match['Landings_Lakh_Tonnes']} lakh tonnes "
                  f"({int(match['Total_Landings_Tonnes']):,} t) in {match['Year']}, on the "
                  f"{match['Coast']} coast. Only {district_years} year(s) of district-level "
                  f"landings exist for '{place}', so no direction can be read from this.",
        "landings_tonnes": match["Total_Landings_Tonnes"],
        "year": match["Year"],
        "cmfri_note": match["CMFRI_Note"],
        "citation": prov.get("citation"),
        "factors": [{
            "factor": "year-on-year direction",
            "year": match["Year"],
            "relationship": "insufficient data",
            "evidence": "one reporting year on record for this state; "
                        "a second edition of the CMFRI booklet is what closes this",
        }],
        "confidence": Confidence(
            score="LOW_DATA",
            rationale=f"single-year CMFRI state estimate for {match['State']}; no multi-year series",
        ),
    }


def _district_key(name: str) -> str:
    """Letters only, doubled letters collapsed — a spelling-tolerant key for
    matching district names across sources that romanise them differently."""
    letters = [c for c in name.lower() if c.isalpha()]
    return "".join(c for i, c in enumerate(letters) if i == 0 or c != letters[i - 1])


def diagnose_productivity_decline(district_sector: str) -> dict[str, Any]:
    """PS #7 — 'why has fish catch declined'. Correlates the recorded catch
    trend against the recorded productivity drivers for a district.

    Discipline: every factor is reported as 'correlated with', never 'caused
    by'. A factor ORCA cannot independently measure here — the live SST and
    chlorophyll *trend*, which needs D3's gridded series — is returned as
    'insufficient data', not guessed.
    """
    rows = [r for r in al.load_fish_landings() if r["District_Sector"].lower().startswith(district_sector.lower())
            or district_sector.lower() in r["District_Sector"].lower()]
    if not rows:
        # Census 2011 and data.gov transliterate the same district differently
        # ("Thoothukkudi" vs "Thoothukudi"), so a position resolved off the
        # district shapefile would otherwise miss its own landings series.
        key = _district_key(district_sector)
        rows = [r for r in al.load_fish_landings() if _district_key(r["District_Sector"]).startswith(key)]
    rows.sort(key=lambda r: r["Year"])
    if len(rows) < 3:
        return _state_landings_record(district_sector, len(rows))

    latest, prior = rows[-1], rows[-2]
    delta_t = latest["Total_Landings_Tonnes"] - prior["Total_Landings_Tonnes"]
    pct = round(100 * delta_t / prior["Total_Landings_Tonnes"], 1)

    # last-3-year net direction — a single good year does not end a decline
    recent = rows[-3:]
    net_pct = round(100 * (recent[-1]["Total_Landings_Tonnes"] - recent[0]["Total_Landings_Tonnes"])
                    / recent[0]["Total_Landings_Tonnes"], 1)
    trend_dir = "declining" if net_pct < 0 else "recovering/stable"
    declined = pct < -2.0 or net_pct < -2.0

    factors: list[dict[str, Any]] = []
    for r in rows[-3:]:
        drivers = r["Key_Productivity_Drivers"].lower()
        if any(m in drivers for m in _SST_STRESS_MARKERS):
            factors.append({
                "factor": "elevated sea-surface temperature / thermal stress",
                "year": r["Year"],
                "relationship": "correlated with",
                "evidence": f"{r['Year']} drivers on record: \"{r['Key_Productivity_Drivers']}\"; "
                            f"catch trend that year: {r['Catch_Trend']}",
            })
        if any(m in drivers for m in _UPWELLING_MARKERS):
            factors.append({
                "factor": "monsoon upwelling strength",
                "year": r["Year"],
                "relationship": "correlated with",
                "evidence": f"{r['Year']} drivers on record: \"{r['Key_Productivity_Drivers']}\"; "
                            f"catch trend that year: {r['Catch_Trend']}",
            })

    # the factor ORCA cannot close here
    factors.append({
        "factor": "live SST / chlorophyll trend (independent measurement)",
        "year": None,
        "relationship": "insufficient data",
        "evidence": "requires D3's gridded SST/chlorophyll time series (§4.2); "
                    "not inferred from the catch record alone",
    })

    if declined:
        named = sorted({f["factor"] for f in factors if f["relationship"] == "correlated with"})
        step = (f"fell {abs(pct)}% year-on-year ({prior['Year']}→{latest['Year']})"
                if pct < -2.0 else
                f"is down {abs(net_pct)}% over {recent[0]['Year']}→{latest['Year']}")
        verdict = (
            f"Landings at {latest['District_Sector']} {step}; the multi-year direction is {trend_dir}. "
            + (f"This is correlated with {', '.join(named)} in the recorded productivity drivers. "
               if named else "The recorded drivers do not name a dominant mechanism. ")
            + "ORCA does not have an independent SST/chlorophyll trend to confirm causation."
        )
        conf = Confidence(score="MEDIUM", rationale="catch record is complete; corroborating ocean series is not available")
    else:
        verdict = (
            f"Landings at {latest['District_Sector']} changed {pct:+}% year-on-year "
            f"({prior['Year']}→{latest['Year']}) — not a decline on the most recent step. "
            f"Multi-year direction: {trend_dir}."
        )
        conf = Confidence(score="MEDIUM", rationale="no recent-year decline in the catch record")

    # Anomaly band: the district's own landings mean ±2σ over the years on
    # record. This is the ONLY baseline ORCA holds independently — the SST and
    # chlorophyll climatologies are D3's gridded series (§4.2) and are absent
    # above, which is why the band is labelled by what it actually is rather
    # than as a generic "normal range".
    totals = [r["Total_Landings_Tonnes"] for r in rows]
    mean = sum(totals) / len(totals)
    std = (sum((t - mean) ** 2 for t in totals) / len(totals)) ** 0.5
    series = []
    for r in rows:
        anomaly = detect_anomaly(r["Total_Landings_Tonnes"], mean, std)
        series.append({
            "year": r["Year"],
            "total_tonnes": r["Total_Landings_Tonnes"],
            "trend": r["Catch_Trend"],
            "z": anomaly["z"],
            "anomalous": anomaly["anomalous"],
        })

    return {
        "district": latest["District_Sector"],
        "verdict": verdict,
        "year_on_year_pct": pct,
        "declined": declined,
        "series": series,
        "baseline": {
            "label": f"{rows[0]['Year']}–{latest['Year']} landings mean ±2σ",
            "mean_tonnes": round(mean, 1),
            "std_tonnes": round(std, 1),
            "band_low": round(mean - 2 * std, 1),
            "band_high": round(mean + 2 * std, 1),
        },
        "factors": factors,
        "confidence": conf,
    }


# --- agent entry point ---------------------------------------------------

def _worst(*confidences: Confidence) -> Confidence:
    order = ("HIGH", "MEDIUM", "LOW_DATA")
    worst = max(confidences, key=lambda c: order.index(c.score))
    return Confidence(score=worst.score, rationale="; ".join(c.rationale for c in confidences))


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Directly callable, no langgraph import
    (plan §3.4). Always returns tide + nearest-PFZ + sector status; adds the
    productivity diagnosis when the query is a 'why has catch declined' one
    or reasoning_depth is DEEP."""
    from orca import demo_fixtures

    pinned = demo_fixtures.fixture_result(state, "ocean_analytics")
    if pinned is not None:
        return pinned

    loc = state.get("user_location") or {}
    lat = loc.get("lat", _DEFAULT_LAT)
    lon = loc.get("lon", _DEFAULT_LON)
    when = _now(state)
    query = (state.get("normalized_english_query") or state.get("raw_user_query") or "").lower()
    depth = coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW"))

    tide = predict_tides(lat, lon, when=when)
    near = nearest_pfz(lat, lon)

    # Agent 3's source-selection reasoning for the data types this agent
    # actually consumes — a first-class output surfaced on the answer card and
    # the activity strip (differentiator 4), not buried in the trace.
    #
    # P2.6: this agent no longer chooses its own sources. `marine_data_discovery`
    # runs once before the fan-out, validates arrival, and its decision is in
    # `state["discovery_sources"]`; this reads it. Choosing here as well was
    # the "each specialist fetches independently" arrangement P2.6 replaces —
    # two components each deciding which tide source to cite, with nothing to
    # keep them agreeing. The fallback to deciding locally is only for a state
    # that never went through Agent 3 (a unit test, or a caller invoking this
    # agent directly), and it uses the same picker Agent 3 does.
    from orca.agents.discovery import select_validated_source

    decided = (state.get("discovery_sources") or {}).get("by_data_type") or {}
    source_selections = []
    for dtype in ("pfz", "tide", "catch_statistics"):
        d = decided.get(dtype) or select_validated_source(dtype)
        if d is not None and d.get("chosen"):
            source_selections.append({
                "data_type": dtype,
                "chosen": d["chosen"],
                "chosen_dataset": d["chosen_dataset"],
                "narrative": d["narrative"],
                "considered": d["considered"],
                "fallback_chain": d["fallback_chain"],
                # Where the decision came from, so a trace reader can see this
                # agent consumed Agent 3's call rather than making its own.
                "decided_by": "marine_data_discovery" if dtype in decided else "ocean_analytics (no Agent 3 decision in state)",
            })

    # The user's own sector governs the status they see — resolved from their
    # actual position, not assumed to be the pilot's.
    user_sector, sector_disclosure = sector_for_point_disclosed(lat, lon, loc.get("place_source"))
    persistence = score_pfz_persistence(lat, lon, sector_id=near.sector_id or user_sector)
    sec_status = sector_status(user_sector)
    sec_status["nearest_advisory_out_of_sector"] = bool(
        near.found and near.sector_id and near.sector_id != user_sector
    )
    correlation = correlate_sst_chlorophyll(state.get("target_bbox"))
    rose = wind_rose(lat, lon)
    anomaly_wind = wind_anomaly(lat, lon)
    gauge = tide_gauge_observation(lat, lon)
    osf_point = nearest_osf_point_forecast(lat, lon)

    outputs: dict[str, Any] = {
        "tide": {
            "station_code": tide.station_code,
            "station_name": tide.station_name,
            "next_high": tide.next_high,
            "next_low": tide.next_low,
            "tidal_state": tide.tidal_state,
            "range_m": tide.range_m,
            "spring_neap": tide.spring_neap,
            "datum": tide.datum,
            "fell_back": tide.fell_back,
            "dataset": tide.source_provenance.dataset,
            # Predicted heights, cross-checked against what a gauge actually
            # measured — the observed side predict_tides deliberately omits.
            "observed_cross_check": {k: v for k, v in gauge.items() if k != "confidence"},
        },
        "nearest_pfz": {
            "found": near.found,
            # distance_km / bearing / compass are ORCA's, from THIS point;
            # the landing centre is INCOIS's landmark, with its own distance
            # in incois_reference. Named so the two cannot be recombined.
            "measured_from": loc.get("place_name") or f"{lat:.2f}, {lon:.2f}",
            "distance_km": near.distance_km,
            "bearing_deg": near.bearing_deg,
            "compass": near.compass,
            "landing_center": near.landing_center,
            "incois_reference": near.incois_reference,
            "depth_m": near.depth_m,
            "coordinates": [near.longitude, near.latitude] if near.found else None,
            "valid_for": near.valid_for,
            "age_days": near.age_days,
            "band": near.band,
            "expired": near.expired,
            "max_km": near.max_km,
        },
        "pfz_persistence": {k: v for k, v in persistence.items() if k != "confidence"},
        "sector_status": sec_status,
        "sst_chlorophyll_correlation": {k: v for k, v in correlation.items() if k != "confidence"},
        "wind_rose": {k: v for k, v in rose.items() if k != "confidence"},
        "wind_anomaly": {k: v for k, v in anomaly_wind.items() if k != "confidence"},
        "osf_point_forecast": {k: v for k, v in osf_point.items() if k != "confidence"},
        "source_selections": source_selections,
        # P1.6 — None when the sector really is this position's. A sentence
        # when it is a fallback, which graph.ocean_analytics_node puts on the
        # card above the answer rather than leaving it to be inferred.
        "sector_disclosure": sector_disclosure,
    }

    # Primary operational confidence: tide + PFZ proximity
    contributing = [tide.confidence]
    if near.found:
        compass_str = f" ({near.compass})" if near.compass else ""
        # An old advisory is still shown (stale-data policy) but is worth less:
        # zones follow SST/chlorophyll fronts that move within days.
        score = {"fresh": "HIGH", "hint": "MEDIUM"}.get(near.band or "", "LOW_DATA")
        age = "" if near.band == "fresh" else f", issued {near.valid_for} ({near.age_days} d old)"
        contributing.append(Confidence(score=score, rationale=f"INCOIS PFZ advisory at {near.distance_km} km{compass_str}{age}"))
    else:
        contributing.append(Confidence(score="MEDIUM", rationale=f"No PFZ advisory within {near.max_km:.0f} km in any advisory ORCA holds"))

    # Multi-day persistence is an analytical trend: it grades the answer only
    # once it has enough days to score (label PERSISTENT/TRANSIENT). An
    # INDICATIVE result — too few archived runs — is still reported on
    # pfz_persistence, but a thin archive says nothing about today's sea, so it
    # must not drag the verdict to LOW_DATA. (The old ">= 2 days" gate did
    # exactly that for 2-4 days, since scoring itself starts at 5.)
    if persistence["label"] != "INDICATIVE":
        contributing.append(persistence["confidence"])

    # P5.3 — a real gauge reading diverging from its own station's prediction
    # by more than the disclosed tolerance floors confidence here too, the
    # same rule P2.4 applies to the wave/wind reconciliation (second
    # variable). Altimetry's own confidence already reflects a coarser
    # measurement and is left alone; only a genuine in-situ divergence counts.
    if gauge.get("source_kind") == "in_situ_gauge" and gauge.get("confidence") is not None:
        contributing.append(gauge["confidence"])

    # Gridded SST/chlorophyll correlation is a specialized oceanographic layer (D3 seam).
    # If the user specifically asks about ocean temperature/colour, or if gridded data is available,
    # it contributes to confidence.
    is_ocean_color_query = any(w in query for w in ("sst", "chlorophyll", "temperature", "plankton", "water quality", "satellite"))
    if correlation.get("available") or is_ocean_color_query:
        contributing.append(correlation["confidence"])

    is_decline_query = any(w in query for w in ("decline", "declined", "why has", "productivity", "catch dropped", "fewer fish"))
    if is_decline_query or depth == "DEEP":
        district = "Thoothukudi" if lon >= 78 and lat <= 9.5 else near.landing_center or "Thoothukudi"
        diag = diagnose_productivity_decline(district)
        outputs["productivity_diagnosis"] = {k: v for k, v in diag.items() if k != "confidence"}
        contributing.append(diag["confidence"])

    confidence = _worst(*contributing)

    return AgentResult(
        agent_name="ocean_analytics",
        query_id=state.get("query_id", ""),
        reasoning_depth=depth,
        inputs_consumed={"lat": lat, "lon": lon, "when": when.isoformat().replace("+00:00", "Z"), "sector_id": user_sector},
        outputs=outputs,
        source_provenance=SourceProvenance(
            dataset="INCOIS PFZ advisories + Survey of India 2026 tide tables (Agent 5)",
            acquisition_timestamp=when.isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        confidence=confidence,
        # Coverage = contributing inputs that produced a usable reading (not
        # LOW_DATA) out of those this query needed. Data age is not measured
        # here yet — PFZ/tide freshness is P5.13's observed-freshness work.
        coverage=(sum(1 for c in contributing if c.score != "LOW_DATA"), len(contributing)),
    )


if __name__ == "__main__":
    st: Any = {
        "query_id": "selfcheck",
        "raw_user_query": "why has catch declined near Thoothukudi and where are the PFZs",
        "normalized_english_query": "why has catch declined near Thoothukudi and where are the PFZs",
        "reasoning_depth": "DEEP",
        "user_location": {"lat": _DEFAULT_LAT, "lon": _DEFAULT_LON},
    }
    res = run(st)
    assert res.agent_name == "ocean_analytics"
    assert res.outputs["tide"]["station_code"], res.outputs["tide"]
    assert res.outputs["nearest_pfz"]["found"] is True
    assert "productivity_diagnosis" in res.outputs
    diag = res.outputs["productivity_diagnosis"]
    assert "caused by" not in diag["verdict"].lower(), "must not claim causation"
    assert any(f["relationship"] == "insufficient data" for f in diag["factors"])
    assert res.outputs["sector_status"]["status"], res.outputs["sector_status"]
    # anomaly helper
    a = detect_anomaly(31.0, 28.4, 0.8)
    assert a["anomalous"] and a["direction"] == "above", a
    print("ocean_analytics self-check ok:", res.confidence.score)
    print(" tide:", res.outputs["tide"]["next_high"], res.outputs["tide"]["spring_neap"])
    print(" pfz :", res.outputs["nearest_pfz"]["compass"], res.outputs["nearest_pfz"]["distance_km"], "km")
    print(" diag:", diag["verdict"][:160])

    # Record a fixture for every Agent 5 output (plan §4 D2 Day 14), the same
    # way the other slices do (plan §6) — the SSE mock and the frontend
    # fixtures replay these exact shapes. Tool-level outputs are wrapped in
    # the AgentResult envelope the harness expects.
    from dataclasses import asdict as _asdict

    from orca.testing.fixtures import record_fixture

    def _wrap(scenario: str, outputs: dict[str, Any], conf: Confidence, dataset: str) -> None:
        record_fixture(
            AgentResult(
                agent_name="ocean_analytics",
                query_id=f"fixture-{scenario}",
                reasoning_depth="STANDARD",
                inputs_consumed={"lat": _DEFAULT_LAT, "lon": _DEFAULT_LON},
                outputs=outputs,
                source_provenance=SourceProvenance(dataset=dataset, acquisition_timestamp="", freshness_minutes=0),
                confidence=conf,
            ),
            scenario,
        )
        print(f" fixture written: ocean_analytics__{scenario}.json")

    record_fixture(res, "thoothukudi_deep_multi_intent")
    print(" fixture written: ocean_analytics__thoothukudi_deep_multi_intent.json")

    # tide, both rungs of the §12.1 cascade
    t_primary = predict_tides()
    _wrap("tide_soi_primary", {k: v for k, v in _asdict(t_primary).items()
                               if k not in ("source_provenance", "confidence")},
          t_primary.confidence, t_primary.source_provenance.dataset)
    t_fb = predict_tides(down=("soi_tide_tables",))
    assert t_fb.fell_back and t_fb.datum == "mean sea level"
    _wrap("tide_stormglass_fallback", {k: v for k, v in _asdict(t_fb).items()
                                       if k not in ("source_provenance", "confidence")},
          t_fb.confidence, t_fb.source_provenance.dataset)

    # the cloud-suppressed sector, and the full SEC001-SEC014 roster
    _wrap("sector_cloud_cover", {"sector_status": sector_status("SEC006"), "all_sectors": all_sector_status()},
          Confidence(score="LOW_DATA", rationale="pilot sector suppressed by cloud cover"),
          "INCOIS PFZ sector status feed")

    # wind rose (the fourth §5.9 chart's data)
    rose = wind_rose()
    _wrap("wind_rose_thoothukudi", {k: v for k, v in rose.items() if k != "confidence"},
          rose["confidence"], rose.get("dataset", "Open-Meteo Forecast API (cached)"))

    # a district with no recent decline, so the no-decline branch is recorded too
    steady = diagnose_productivity_decline("Mumbai Coastal")
    _wrap("catch_diagnosis_mumbai", {k: v for k, v in steady.items() if k != "confidence"},
          steady["confidence"], "data.gov.in Marine Fish Landings")

    # the degraded SST/chlorophyll path, so consumers have the LOW_DATA shape
    corr = correlate_sst_chlorophyll(None)
    _wrap("sst_chl_awaiting_d3", {k: v for k, v in corr.items() if k != "confidence"},
          corr["confidence"], "MOSDAC SST + chlorophyll (awaiting D3 fixtures, §4.2)")
