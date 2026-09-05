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
        }


@dataclass
class Crossing:
    fired: bool
    severity: str          # info | advisory | warning | danger
    title: str
    reason: str
    snapshot: WatchSnapshot


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
        wave_height_m=wave or 0.0,
        wind_speed_kmh=(wind or 0.0) * 3.6,
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

    # 2. a new active hazard not present last time
    new_hazards = set(snapshot.active_hazard_types) - prev_hazards
    if new_hazards:
        return Crossing(
            fired=True,
            severity="danger",
            title=f"New hazard: {', '.join(sorted(new_hazards))}",
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

    # unchanged — the no-notification-spam functional requirement
    return Crossing(fired=False, severity="info", title="", reason="no change", snapshot=snapshot)


def build_alert(watch_type: str, location_name: str, crossing: Crossing) -> dict[str, str]:
    """Agent 7's tool, reused — not re-derived (exit criterion: generate_alert_payload
    is Agent 7's, Sentinel does not own alert text)."""
    severity_word = "danger" if crossing.severity == "danger" else "warning"
    return risk_assessment.generate_alert_payload(
        hazard_type=crossing.title,
        severity=severity_word,
        location=location_name,
        language="en",  # localisation is Agent 1's egress job, per Ground Rule 1
    )


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
    check: Callable[..., WatchSnapshot] | None = None,
) -> WatchDecision:
    """`check` is injectable so tests supply a deterministic snapshot instead
    of hitting Open-Meteo (same pattern as the e2e graph test mocking wia).
    Resolved as `check or cheap_check` rather than a bound default — a bound
    default captures the original function object at def time, which a test's
    `monkeypatch.setattr(sentinel, "cheap_check", ...)` can never reach."""
    query_id = str(uuid.uuid4())
    snapshot = (check or cheap_check)(location["lat"], location["lon"], vessel_class=vessel_class)
    crossing = detect_crossing(watch_type, thresholds, snapshot, last_payload)

    if not crossing.fired:
        return WatchDecision(
            watch_id=watch_id, query_id=query_id, fired=False, severity="info",
            title="", body="", alert_payload={}, snapshot_payload=snapshot.as_payload(),
        )

    alert = build_alert(watch_type, location_name, crossing)
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
