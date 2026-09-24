"""Agent 11 — Sentinel (Architecture §3.1, plan §4 D2).

An analytic loop, not a new data domain. For each enabled watch it runs the
*cheap check*: it pulls the current Agent 4 (weather) and Agent 7 (risk)
outputs for that location through the SAME tool interfaces the on-demand
graph uses — no duplicate fetching, no second threshold table — and tests
whether a condition has *crossed* since the last time this watch fired.

Rules (plan §4 D2 Day 16):
  * GO -> CAUTION, CAUTION -> NO_GO, or any severity increase   -> fire
  * a threshold named in the watch newly exceeded                -> fire
  * a new active hazard (lightning / cyclone) not seen last time -> fire
  * unchanged conditions                                         -> NO-OP
Only a genuine crossing escalates to a full graph invocation.

No `persona` anywhere in this file (CI persona-leak guard) — Sentinel is
persona-blind by construction; localisation happens at dispatch via Agent 1,
exactly like the on-demand egress path.
"""
from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from orca.agents import risk_assessment, weather_intelligence
from orca.contracts import Confidence

# Severity ladder used for the "did it get worse" test.
_VERDICT_RANK = {"GO": 0, "CAUTION": 1, "NO_GO": 2}
_SEVERITY_FOR_VERDICT = {"GO": "info", "CAUTION": "warning", "NO_GO": "danger"}


@dataclass
class WatchSnapshot:
    """The cheap-check result for one watch at one poll tick."""

    go_no_go: str
    reason: str
    wave_height_m: float | None
    wind_speed_ms: float | None
    lightning_active: bool
    cyclone_alert: str | None
    active_hazard_types: list[str] = field(default_factory=list)
    confidence: str = "LOW_DATA"
    # P5.21 — the CAP alert (if any) covering this watch point, carried
    # verbatim so `detect_crossing`'s "new hazard" branch can name the actual
    # identifier/sender/severity instead of only the generic weather reason.
    cap_alert: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "go_no_go": self.go_no_go,
            "reason": self.reason,
            "wave_height_m": self.wave_height_m,
            "wind_speed_ms": self.wind_speed_ms,
            "lightning_active": self.lightning_active,
            "cyclone_alert": self.cyclone_alert,
            "active_hazard_types": sorted(self.active_hazard_types),
            "confidence": self.confidence,
            "cap_alert": self.cap_alert,
        }


@dataclass
class Crossing:
    fired: bool
    severity: str          # info | advisory | warning | danger
    title: str
    reason: str
    # Duck-typed: WatchSnapshot for weather/wave_height/lightning/cyclone
    # watches, GeofenceSnapshot for geofence_approach, PfzShiftSnapshot for
    # pfz_shift — whichever the watch's own check produced. Every one of the
    # three implements `.as_payload()`, which is all `evaluate()` needs.
    snapshot: Any


# P5.21 — SACHET's public feed carries only a `centroid` and an
# `area_covered` (km2) per alert, never the CAP polygon itself. "Intersects"
# is approximated as: inside a circle of that same area, centred on the
# alert's own centroid — a disclosed proxy, the same discipline P5.5's
# EEZ-proxy IMBL distance already follows for a different geometry gap.
def _cap_alert_overlap(lat: float, lon: float) -> dict[str, Any] | None:
    """The nearest live CAP alert whose equivalent-area circle contains
    (lat, lon), or None. Never raises — a feed failure here degrades to "no
    CAP alert known", not a crashed poll tick; `_fetch_sachet_alerts` already
    falls back to its own cache on a live failure."""
    try:
        alerts, dataset, _confidence = weather_intelligence._fetch_sachet_alerts()
    except Exception:
        return None
    for alert in alerts:
        centroid = weather_intelligence._alert_centroid(alert)
        area_km2_raw = alert.get("area_covered")
        if centroid is None or area_km2_raw is None:
            continue
        try:
            area_km2 = float(area_km2_raw)
        except (TypeError, ValueError):
            continue
        if area_km2 <= 0:
            continue
        radius_km = math.sqrt(area_km2 / math.pi)
        clat, clon = centroid
        _, distance_nm = _geodesic_bearing_distance(lat, lon, clat, clon)
        if distance_nm * 1.852 <= radius_km:
            return {
                "identifier": alert.get("identifier"),
                "disaster_type": alert.get("disaster_type"),
                "severity": alert.get("severity"),
                "area_description": alert.get("area_description"),
                "sender_org_id": alert.get("sender_org_id"),
                "dataset": dataset,
                "geometry_proxy": "equivalent-area circle around the alert centroid — SACHET publishes no polygon",
            }
    return None


def _geodesic_bearing_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """(bearing_deg, distance_nm) — thin re-export of Agent 6's geodesic so
    this module never re-implements great-circle math of its own."""
    from orca.agents import geospatial

    return geospatial.bearing_and_distance(lat1, lon1, lat2, lon2)


def cheap_check(lat: float, lon: float, *, vessel_class: str | None = None) -> WatchSnapshot:
    """Reuse Agent 4 + Agent 7 tools — never a competing fetch path. These
    are the exact functions the on-demand graph's weather/risk nodes call,
    so a Sentinel reading can never disagree with an on-demand one for the
    same inputs."""
    weather = weather_intelligence.get_marine_weather(lat, lon)
    hourly = (weather.get("hourly") or [{}])[0]
    lightning = weather_intelligence.get_lightning_nowcast(lat, lon)
    basin = "BoB" if lon >= 77.5 else "AS"
    cyclone = weather_intelligence.get_cyclone_status(basin)  # type: ignore[arg-type]

    wave = hourly.get("wave_height")
    wind = hourly.get("wind_speed_10m")
    lightning_active = bool(lightning.get("lightning_active"))
    active = cyclone.get("active_cyclones") or []
    cyclone_alert = risk_assessment_cyclone_alert(active)

    verdict = risk_assessment.evaluate_marine_safety(
        # P0.15 / R-SAFE-1: `wave or 0.0` / `(wind or 0.0) * 3.6` turned a
        # missing reading into a calm sea and a still day — the exact
        # fall-through evaluate_marine_safety's own `_known()` guard exists
        # to catch, defeated by masking the gap before it ever got there.
        # None passes through so a missing reading floors to
        # CAUTION_MISSING_DATA, naming the field, instead of a background
        # watch reporting GO on no data.
        wave_height_m=wave,
        wind_speed_kmh=(wind * 3.6) if wind is not None else None,
        lightning_active=lightning_active,
        cyclone_alert=cyclone_alert,
        imbl_distance_nm=999.0,   # geofence handled by geofence_approach watches, not here
        mpa_violation=False,
        vessel_class=(vessel_class or "small_fishing"),  # type: ignore[arg-type]
    )

    hazard_types: list[str] = []
    if lightning_active:
        hazard_types.append("lightning")
    if active:
        hazard_types.append("cyclone")
    # P5.21 — a live CAP alert covering this point is a hazard the existing
    # "new active hazard fires" rule (detect_crossing step 2) already knows
    # how to act on; reusing it means a CAP alert appearing over a watch
    # fires the same way a new cyclone alert does, with the same no-repeat
    # guarantee, at no cost to that rule's own logic.
    cap_alert = _cap_alert_overlap(lat, lon)
    if cap_alert is not None:
        hazard_types.append("cap_alert")

    conf = lightning.get("confidence")
    return WatchSnapshot(
        go_no_go=verdict["go_no_go"],
        reason=verdict["reason"],
        wave_height_m=wave,
        wind_speed_ms=wind,
        lightning_active=lightning_active,
        cyclone_alert=cyclone_alert,
        active_hazard_types=hazard_types,
        confidence=conf.score if isinstance(conf, Confidence) else "MEDIUM",
        cap_alert=cap_alert,
    )


def risk_assessment_cyclone_alert(active_cyclones: list[dict]) -> str | None:
    if not active_cyclones:
        return None
    sev = {c.get("severity") for c in active_cyclones}
    if "Red" in sev:
        return "Red"
    if "Orange" in sev:
        return "Orange"
    return "Yellow"


def detect_crossing(
    watch_type: str,
    thresholds: dict[str, float],
    snapshot: WatchSnapshot,
    last_payload: dict[str, Any] | None,
) -> Crossing:
    """Pure function — no I/O — so every branch is unit-testable. A second
    identical poll (last_payload == snapshot) must return fired=False."""
    prev_verdict = (last_payload or {}).get("go_no_go", "GO")
    prev_hazards = set((last_payload or {}).get("active_hazard_types", []))
    prev_wave = (last_payload or {}).get("wave_height_m")

    # 1. severity increase (GO->CAUTION, CAUTION->NO_GO, ...)
    if _VERDICT_RANK.get(snapshot.go_no_go, 0) > _VERDICT_RANK.get(prev_verdict, 0):
        return Crossing(
            fired=True,
            severity=_SEVERITY_FOR_VERDICT[snapshot.go_no_go],
            title=f"Conditions worsened to {snapshot.go_no_go.replace('_', '-')}",
            reason=snapshot.reason,
            snapshot=snapshot,
        )

    # 1b. severity decrease — the mirror of #1 (P5.19, orca_final §11.3):
    # "it's safe again" is as actionable as "it isn't". Same rank ladder,
    # same no-repeat guarantee (a second identical poll never re-enters this
    # branch because prev_verdict already equals snapshot.go_no_go by then).
    if _VERDICT_RANK.get(snapshot.go_no_go, 0) < _VERDICT_RANK.get(prev_verdict, 0):
        return Crossing(
            fired=True,
            severity="info",
            title=f"Conditions improved to {snapshot.go_no_go.replace('_', '-')}",
            reason=snapshot.reason,
            snapshot=snapshot,
        )

    # 2. a new active hazard not present last time
    new_hazards = set(snapshot.active_hazard_types) - prev_hazards
    if new_hazards:
        # P5.21 — a CAP alert is relayed verbatim (identifier, sender,
        # severity), never re-graded into ORCA's own wording: the generic
        # weather `snapshot.reason` says nothing about which alert arrived.
        if "cap_alert" in new_hazards and snapshot.cap_alert:
            cap = snapshot.cap_alert
            return Crossing(
                fired=True,
                severity="danger",
                title=f"CAP alert: {cap.get('disaster_type') or 'hazard'} ({cap.get('severity')})",
                reason=(
                    f"{cap.get('area_description') or 'Your watch area'} — "
                    f"sender {cap.get('sender_org_id')}, alert {cap.get('identifier')}. "
                    f"Source: {cap.get('dataset')}."
                ),
                snapshot=snapshot,
            )
        return Crossing(
            fired=True,
            severity="danger",
            title=f"New hazard: {', '.join(sorted(new_hazards))}",
            reason=snapshot.reason,
            snapshot=snapshot,
        )

    # 2b. a hazard present last time but cleared now — mirror of #2 (P5.19)
    cleared_hazards = prev_hazards - set(snapshot.active_hazard_types)
    if cleared_hazards:
        return Crossing(
            fired=True,
            severity="info",
            title=f"Hazard cleared: {', '.join(sorted(cleared_hazards))}",
            reason=snapshot.reason,
            snapshot=snapshot,
        )

    # 3. an explicit numeric threshold newly exceeded
    wave_threshold = thresholds.get("wave_height_m")
    if (
        wave_threshold is not None
        and snapshot.wave_height_m is not None
        and snapshot.wave_height_m >= wave_threshold
        and (prev_wave is None or prev_wave < wave_threshold)
    ):
        return Crossing(
            fired=True,
            severity="warning",
            title=f"Wave height crossed {wave_threshold} m",
            reason=f"Forecast wave height {snapshot.wave_height_m:.1f} m at your watch point.",
            snapshot=snapshot,
        )

    # 3b. threshold dropped back below — mirror of #3 (P5.19)
    if (
        wave_threshold is not None
        and snapshot.wave_height_m is not None
        and snapshot.wave_height_m < wave_threshold
        and prev_wave is not None and prev_wave >= wave_threshold
    ):
        return Crossing(
            fired=True,
            severity="info",
            title=f"Wave height dropped back below {wave_threshold} m",
            reason=f"Forecast wave height {snapshot.wave_height_m:.1f} m at your watch point.",
            snapshot=snapshot,
        )

    # unchanged — the no-notification-spam functional requirement
    return Crossing(fired=False, severity="info", title="", reason="no change", snapshot=snapshot)


# --------------------------------------------------------------------------
# P5.18 — geofence_approach and pfz_shift watches. Both types exist in the DB
# enum and the `/watches` form already offers them, but `cheap_check()`
# hardcoded `imbl_distance_nm=999.0` (never crosses any band) and
# `detect_crossing()` has no branch that reads a boundary distance or a PFZ
# sector at all — so a user could create either watch and it would silently
# never fire. These give each type its own check + crossing function,
# dispatched from `evaluate()` below instead of routed through the
# weather/wave/lightning/cyclone path the other four watch types share.
# --------------------------------------------------------------------------

# orca_final §6.3's graded escalation, reused here rather than re-invented:
# (upper bound nm, band name, fired severity). Checked in order, first match
# wins; CLEAR is anything past the widest band.
_GEOFENCE_BANDS: tuple[tuple[float, str, str], ...] = (
    (1.0, "CRITICAL", "danger"),
    (3.0, "WARNING", "danger"),
    (6.0, "WATCH", "warning"),
    (12.0, "ADVISORY", "advisory"),
)
_GEOFENCE_BAND_RANK = {"CLEAR": 0, "ADVISORY": 1, "WATCH": 2, "WARNING": 3, "CRITICAL": 4}


def _geofence_band(distance_nm: float) -> str:
    for upper, name, _severity in _GEOFENCE_BANDS:
        if distance_nm <= upper:
            return name
    return "CLEAR"


@dataclass
class GeofenceSnapshot:
    """The cheap-check result for one geofence_approach watch at one poll."""

    distance_nm: float
    line_name: str | None
    between: list[str | None] | None
    bearing_deg: float | None
    band: str  # CLEAR | ADVISORY | WATCH | WARNING | CRITICAL

    def as_payload(self) -> dict[str, Any]:
        return {
            "distance_nm": self.distance_nm, "line_name": self.line_name,
            "between": self.between, "bearing_deg": self.bearing_deg, "band": self.band,
        }


def geofence_check(lat: float, lon: float, **_ignored: Any) -> GeofenceSnapshot:
    """P5.5's `nearest_boundary_line` re-read for a watch position — the same
    nearest-of-32-treaty-lines measurement the query path uses, not a second
    geometry check invented for Sentinel."""
    from orca.agents import geospatial

    line = geospatial.nearest_boundary_line(lat, lon)
    if line is None:
        return GeofenceSnapshot(distance_nm=999.0, line_name=None, between=None, bearing_deg=None, band="CLEAR")
    return GeofenceSnapshot(
        distance_nm=line["distance_nm"], line_name=line["line_name"], between=line["between"],
        bearing_deg=line["bearing_deg"], band=_geofence_band(line["distance_nm"]),
    )


def detect_geofence_crossing(snapshot: GeofenceSnapshot, last_payload: dict[str, Any] | None) -> Crossing:
    """Fires on entering a new (tighter) band — and its P5.19 mirror, clearing
    back out of one — never on an unchanged band. Band NAME is what fires the
    alert, not the bare distance: 'entering the WARNING band' reads as a
    warning; '2.8 nm' reads as a number someone has to already know how to
    interpret (P5.6's whole point)."""
    prev_band = (last_payload or {}).get("band", "CLEAR")
    prev_rank, new_rank = _GEOFENCE_BAND_RANK[prev_band], _GEOFENCE_BAND_RANK[snapshot.band]
    line_phrase = snapshot.line_name or "the nearest maritime boundary"
    between_phrase = f" ({snapshot.between[0]} – {snapshot.between[1]})" if snapshot.between and all(snapshot.between) else ""
    bearing_phrase = f", bearing {snapshot.bearing_deg:.0f}°" if snapshot.bearing_deg is not None else ""
    reason = f"{snapshot.distance_nm:.1f} nm from {line_phrase}{between_phrase}{bearing_phrase}."

    if new_rank > prev_rank:
        _, _, severity = next(b for b in _GEOFENCE_BANDS if b[1] == snapshot.band)
        return Crossing(
            fired=True, severity=severity,
            title=f"Entering the {snapshot.band.title()} band — {line_phrase}",
            reason=reason, snapshot=snapshot,
        )
    if new_rank < prev_rank:
        return Crossing(
            fired=True, severity="info",
            title=f"Clear of the {prev_band.title()} band — {line_phrase}",
            reason=reason, snapshot=snapshot,
        )
    return Crossing(fired=False, severity="info", title="", reason="no change", snapshot=snapshot)


@dataclass
class PfzShiftSnapshot:
    """The cheap-check result for one pfz_shift watch at one poll — has an
    advisory appeared in or disappeared from the watch's own sector, per
    P1.6's position-to-sector resolution."""

    sector_id: str
    has_advisory: bool
    node_count: int

    def as_payload(self) -> dict[str, Any]:
        return {"sector_id": self.sector_id, "has_advisory": self.has_advisory, "node_count": self.node_count}


def pfz_shift_check(lat: float, lon: float, **_ignored: Any) -> PfzShiftSnapshot:
    from orca.agents import ocean_analytics

    sector_id, _disclosure = ocean_analytics.sector_for_point_disclosed(lat, lon)
    status = ocean_analytics.sector_status(sector_id)
    return PfzShiftSnapshot(
        sector_id=sector_id,
        has_advisory=status.get("status") == "HAS_ADVISORY",
        node_count=status.get("node_count", 0),
    )


def detect_pfz_shift_crossing(snapshot: PfzShiftSnapshot, last_payload: dict[str, Any] | None) -> Crossing:
    """Fires only on appear/disappear, never on the first-ever poll (there is
    no 'shift' to report against a baseline that does not exist yet) and
    never on an unchanged status — the same no-repeat rule every other watch
    type follows."""
    if last_payload is None:
        return Crossing(fired=False, severity="info", title="", reason="no change", snapshot=snapshot)
    prev_has = last_payload.get("has_advisory")
    if snapshot.has_advisory and not prev_has:
        return Crossing(
            fired=True, severity="warning",
            title=f"PFZ advisory now active — sector {snapshot.sector_id}",
            reason=f"{snapshot.node_count} advisory node(s) newly on record for your sector.",
            snapshot=snapshot,
        )
    if prev_has and not snapshot.has_advisory:
        return Crossing(
            fired=True, severity="info",
            title=f"PFZ advisory cleared — sector {snapshot.sector_id}",
            reason="No advisory nodes remain on record for your sector.",
            snapshot=snapshot,
        )
    return Crossing(fired=False, severity="info", title="", reason="no change", snapshot=snapshot)


_GEOMETRY_WATCH_TYPES = {"geofence_approach", "pfz_shift"}


def build_alert(watch_type: str, location_name: str, crossing: Crossing, language: str = "en") -> dict[str, str]:
    """Agent 7's tool, reused — not re-derived (exit criterion: generate_alert_payload
    is Agent 7's, Sentinel does not own alert text).

    P3.6 (`R-PS-7`) — `language` is the watch owner's `users.language`
    (`sentinel_runtime.run_poll_cycle` reads it before calling `evaluate`).
    A language with no verified voice output (anything outside
    `risk_assessment._ALERT_VERIFIED_LANGUAGES`) still gets an alert, in
    English, with `language_fallback` naming what was asked for and why —
    principle 3 (degrade loudly): no proactive alert at all is worse than
    one in the wrong language, but a silent substitution is a lie."""
    severity_word = "danger" if crossing.severity == "danger" else "warning"
    try:
        return risk_assessment.generate_alert_payload(
            hazard_type=crossing.title, severity=severity_word, location=location_name, language=language,
        )
    except NotImplementedError:
        payload = risk_assessment.generate_alert_payload(
            hazard_type=crossing.title, severity=severity_word, location=location_name, language="en",
        )
        payload["language_fallback"] = language
        return payload


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# One poll tick — pure orchestration over the pieces above. The DB / dispatch
# wiring lives in orca/sentinel_runtime.py so this stays graph-free and
# unit-testable (same discipline as every other agent in this package).
# --------------------------------------------------------------------------

@dataclass
class WatchDecision:
    watch_id: str
    query_id: str
    fired: bool
    severity: str
    title: str
    body: str
    alert_payload: dict[str, Any]
    snapshot_payload: dict[str, Any]


def evaluate(
    *,
    watch_id: str,
    watch_type: str,
    location: dict[str, float],
    location_name: str,
    thresholds: dict[str, float],
    last_payload: dict[str, Any] | None,
    vessel_class: str | None = None,
    language: str = "en",
    check: Callable[..., Any] | None = None,
) -> WatchDecision:
    """`check` is injectable so tests supply a deterministic snapshot instead
    of hitting Open-Meteo (same pattern as the e2e graph test mocking wia).
    Resolved as `check or cheap_check` rather than a bound default — a bound
    default captures the original function object at def time, which a test's
    `monkeypatch.setattr(sentinel, "cheap_check", ...)` can never reach.

    P5.18 — `geofence_approach` and `pfz_shift` dispatch to their own
    check + crossing pair instead of the weather/wave/lightning/cyclone path
    every other watch type shares: neither reads wave height or wind, and
    forcing them through `cheap_check`/`detect_crossing` is exactly how they
    ended up permanently silent (`cheap_check` hardcoded a 999 nm boundary
    distance no watch could ever cross)."""
    query_id = str(uuid.uuid4())
    if watch_type == "geofence_approach":
        snapshot = (check or geofence_check)(location["lat"], location["lon"])
        crossing = detect_geofence_crossing(snapshot, last_payload)
    elif watch_type == "pfz_shift":
        snapshot = (check or pfz_shift_check)(location["lat"], location["lon"])
        crossing = detect_pfz_shift_crossing(snapshot, last_payload)
    else:
        snapshot = (check or cheap_check)(location["lat"], location["lon"], vessel_class=vessel_class)
        crossing = detect_crossing(watch_type, thresholds, snapshot, last_payload)

    if not crossing.fired:
        return WatchDecision(
            watch_id=watch_id, query_id=query_id, fired=False, severity="info",
            title="", body="", alert_payload={}, snapshot_payload=snapshot.as_payload(),
        )

    alert = build_alert(watch_type, location_name, crossing, language=language)
    return WatchDecision(
        watch_id=watch_id,
        query_id=query_id,
        fired=True,
        severity=crossing.severity,
        title=crossing.title,
        body=crossing.reason,
        alert_payload={**alert, "sagar_vani_sms": alert.get("sms", ""), "generated_at": now_utc_iso()},
        snapshot_payload=snapshot.as_payload(),
    )
