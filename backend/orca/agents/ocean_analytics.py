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

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from orca.agents import geospatial
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data import analytics_loaders as al
from orca.state import ORCAState

NM_PER_KM = 1 / 1.852

_COMPASS_16 = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)

# South Tamil Nadu is the pilot sector (SEC006); the pilot region's own
# default position is Thoothukudi, matching the Phase 1 acceptance query.
_PILOT_SECTOR = "SEC006"
_DEFAULT_LAT, _DEFAULT_LON = 8.80, 78.14


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
        confidence = Confidence(
            score="MEDIUM",
            rationale=f"SOI 2026 table exhausted for {code}; fell to the declared Stormglass "
            "fallback — heights are on mean sea level, not chart datum",
        )
    elif not (next_high and next_low):
        confidence = Confidence(score="MEDIUM", rationale="Only one of the next high/low falls in the published window")
    else:
        confidence = Confidence(score="HIGH", rationale=f"SOI 2026 predicted tide table, station {code}")

    src = events[0]["source"] if events else "Survey of India 2026 Tide Tables"
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
            acquisition_timestamp=when.isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,  # astronomical prediction — the table does not go stale
        ),
        confidence=confidence,
    )


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


def correlate_sst_chlorophyll(bbox: dict[str, float] | None = None) -> dict[str, Any]:
    """Cross-source SST + chlorophyll relationship over the pilot bbox.

    Consumes D3's normalized gridded fixtures (§4.2). Until those land this
    returns available=False with LOW_DATA and the reason — it does not
    synthesise a correlation from nothing.
    """
    sst = al.load_ocean_grid_fixture("sst")
    chl = al.load_ocean_grid_fixture("chl")
    if sst is None or chl is None:
        missing = [n for n, v in (("SST", sst), ("chlorophyll", chl)) if v is None]
        return {
            "available": False,
            "note": f"awaiting D3 gridded loader fixtures for {', '.join(missing)} "
                    "(Phase 2 plan §4.2 — mosdac_*__pilot__*.json)",
            "confidence": Confidence(score="LOW_DATA", rationale="gridded ocean-colour / SST inputs not yet available"),
        }

    sst_series = [r["value"] for r in sst.get("frame", []) if r.get("value") is not None]
    chl_series = [r["value"] for r in chl.get("frame", []) if r.get("value") is not None]
    n = min(len(sst_series), len(chl_series))
    if n < 3:
        return {
            "available": False,
            "note": "fixture present but fewer than 3 co-located samples",
            "confidence": Confidence(score="LOW_DATA", rationale="insufficient overlapping SST/chl samples"),
        }
    r = _pearson(sst_series[:n], chl_series[:n])
    return {
        "available": True,
        "pearson_r": round(r, 3),
        "relationship": _describe_r(r),
        "n_samples": n,
        "sst_provenance": sst.get("provenance"),
        "chl_provenance": chl.get("provenance"),
        "confidence": Confidence(
            score="MEDIUM" if n < 20 else "HIGH",
            rationale=f"{n} co-located SST/chlorophyll samples over the pilot bbox",
        ),
    }


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


def nearest_pfz(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON, *, sector_id: str | None = None) -> NearestPFZ:
    """Closest INCOIS PFZ advisory node to a point, with distance, true
    bearing and 16-point compass heading — 'which way and how far', the only
    form of this answer usable from a boat."""
    rows = al.load_pfz_master()
    if sector_id:
        rows = [r for r in rows if r.get("sector_id") == sector_id]
    parsed: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        try:
            plat, plon = float(r["latitude_dd"]), float(r["longitude_dd"])
        except (KeyError, ValueError):
            continue
        parsed.append((_km_between(lat, lon, plat, plon), r))
    if not parsed:
        return NearestPFZ(False, None, None, None, None, None, None, None, None, sector_id)
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
    )


def score_pfz_persistence(lat: float, lon: float, *, sector_id: str, radius_km: float = 25.0) -> dict[str, Any]:
    """How consistently a PFZ has been advised near a point across the
    archived daily runs. score = (days with an advisory node within
    `radius_km`) / (days on record). Fewer than 2 snapshots → the score is
    'indicative' and confidence is LOW_DATA — one day is not a trend."""
    dates = al.available_pfz_history_dates()
    hits = 0
    for date in dates:
        nodes = al.load_pfz_history_advisories(date)
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
    if n < 2:
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"only {n} archived PFZ snapshot(s) — persistence needs a run of days, not one",
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
        "radius_km": radius_km,
        "confidence": confidence,
    }


def sector_status(sector_id: str = _PILOT_SECTOR) -> dict[str, Any]:
    """First-class sector status. A cloud-suppressed sector returns
    NO_DATA_CLOUD_COVER carrying INCOIS's own message text — never an empty
    result that reads as an ORCA failure (data audit C-2)."""
    status = al.load_pfz_sector_status()
    names = status.get("sector_names", {})
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
            }
    return {
        "sector_id": sector_id,
        "sector_name": names.get(sector_id),
        "status": "UNKNOWN",
        "message": "This sector is not present in the current INCOIS PFZ status feed.",
        "node_count": 0,
        "valid_for": None,
        "is_data_gap": True,
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
    rows.sort(key=lambda r: r["Year"])
    if len(rows) < 3:
        return {
            "district": district_sector,
            "verdict": "insufficient data",
            "detail": f"only {len(rows)} year(s) of landings on record for '{district_sector}'",
            "factors": [],
            "confidence": Confidence(score="LOW_DATA", rationale="fewer than 3 years of catch data"),
        }

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
    loc = state.get("user_location") or {}
    lat = loc.get("lat", _DEFAULT_LAT)
    lon = loc.get("lon", _DEFAULT_LON)
    when = _now(state)
    query = (state.get("normalized_english_query") or state.get("raw_user_query") or "").lower()
    depth = coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW"))

    tide = predict_tides(lat, lon, when=when)
    near = nearest_pfz(lat, lon)
    # The user's own sector governs the status they see. Pilot deployment is
    # SEC006 (South Tamil Nadu); a full point→sector lookup is Agent 6's
    # boundary domain, out of scope here.
    user_sector = _PILOT_SECTOR
    persistence = score_pfz_persistence(lat, lon, sector_id=near.sector_id or user_sector)
    sec_status = sector_status(user_sector)
    sec_status["nearest_advisory_out_of_sector"] = bool(
        near.found and near.sector_id and near.sector_id != user_sector
    )
    correlation = correlate_sst_chlorophyll(state.get("target_bbox"))

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
        },
        "nearest_pfz": {
            "found": near.found,
            "landing_center": near.landing_center,
            "distance_km": near.distance_km,
            "bearing_deg": near.bearing_deg,
            "compass": near.compass,
            "depth_m": near.depth_m,
            "coordinates": [near.longitude, near.latitude] if near.found else None,
            "valid_for": near.valid_for,
        },
        "pfz_persistence": {k: v for k, v in persistence.items() if k != "confidence"},
        "sector_status": sec_status,
        "sst_chlorophyll_correlation": {k: v for k, v in correlation.items() if k != "confidence"},
    }

    contributing = [tide.confidence, persistence["confidence"], correlation["confidence"]]

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
    )


if __name__ == "__main__":
    st: Any = {
        "query_id": "selfcheck",
        "raw_user_query": "why has catch declined near Thoothukudi and where are the PFZs",
        "normalized_english_query": "why has catch declined near Thoothukudi and where are the PFZs",
        "reasoning_depth": "DEEP",
        "user_location": {"lat": 8.80, "lon": 78.14},
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
