"""Agent 7 — Risk Assessment (Architecture §3.1). Pure-math safety classifier.
Zero LLM calls (Ground Rule 2) — this is the one module in the codebase where
a bug is a life-safety issue, and it is the one place the plan deliberately
overrides the "one runnable check" rule with real coverage (plan §4, S2).

`evaluate_marine_safety`'s base thresholds are transcribed verbatim from
Architecture §3.1 — do not "simplify" this function; the whole point is that
it is inspectable and matches the documented reference exactly for the
default (small_fishing) vessel class.
"""
from __future__ import annotations

from typing import Literal, TypedDict

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data.normalize import ms_to_kmh
from orca.resilience import conservative_or, safety_floor_for_missing_inputs
from orca.state import ORCAState

VesselClass = Literal["small_fishing", "mechanized_trawler", "cargo_vessel"]

# Vessel-class threshold deltas (Architecture §3.1 Agent 7), applied BEFORE
# evaluate_marine_safety compares against the danger/caution bands. Deltas
# are in km/h (wind) and m (wave height), applied to every band for that
# vessel class — a bigger, more capable vessel tolerates rougher conditions
# before the same verdict fires.
_VESSEL_DELTAS: dict[VesselClass, tuple[float, float]] = {  # (wind_kmh_delta, hs_m_delta)
    "small_fishing": (0.0, 0.0),
    "mechanized_trawler": (9.3, 0.5),
    "cargo_vessel": (27.8, 1.5),
}


class SafetyVerdict(TypedDict):
    status: str
    go_no_go: Literal["GO", "CAUTION", "NO_GO"]
    reason: str


def evaluate_marine_safety(
    wave_height_m: float,
    wind_speed_kmh: float,
    lightning_active: bool,
    cyclone_alert: str | None,
    imbl_distance_nm: float,
    mpa_violation: bool,
    vessel_class: VesselClass = "small_fishing",
) -> SafetyVerdict:
    wind_delta, hs_delta = _VESSEL_DELTAS[vessel_class]
    danger_wind, danger_hs = 55.0 + wind_delta, 3.5 + hs_delta
    caution_wind, caution_hs = 35.0 + wind_delta, 2.0 + hs_delta

    if cyclone_alert in ("Red", "Orange") or wave_height_m >= danger_hs or wind_speed_kmh >= danger_wind:
        return {"status": "DANGER", "go_no_go": "NO_GO", "reason": "Severe Weather / Cyclone Threshold Exceeded"}
    if lightning_active:
        return {"status": "DANGER", "go_no_go": "NO_GO", "reason": "Active Convective Lightning Strike Zone"}
    if imbl_distance_nm <= 1.0 or mpa_violation:
        return {"status": "CRITICAL_GEOFENCE", "go_no_go": "NO_GO", "reason": "Imminent Boundary or MPA Breach"}
    if caution_hs <= wave_height_m < danger_hs or caution_wind <= wind_speed_kmh < danger_wind or imbl_distance_nm <= 3.0:
        return {"status": "WARNING", "go_no_go": "CAUTION", "reason": "Rough Sea State / Boundary Proximity"}
    return {"status": "SAFE", "go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits"}


# --- compute_confidence ------------------------------------------------------

_TIER_ORDER = ("HIGH", "MEDIUM", "LOW_DATA")


def compute_confidence(inputs: list[Confidence]) -> Confidence:
    """Tool per Architecture §3.1 Agent 7. Conservative composite — the
    worst tier among every upstream input wins, never an average (Ground
    Rule 4: uncertainty degrades conservative, it never nets out)."""
    if not inputs:
        return Confidence(score="LOW_DATA", rationale="No upstream confidence inputs supplied")
    worst = max(inputs, key=lambda c: _TIER_ORDER.index(c.score))
    if worst.score == "HIGH" and len({c.score for c in inputs}) == 1:
        return Confidence(score="HIGH", rationale="All upstream sources HIGH confidence")
    return Confidence(
        score=worst.score,
        rationale=f"Worst of {len(inputs)} upstream inputs: {worst.rationale}",
    )


# --- generate_alert_payload ---------------------------------------------------

def generate_alert_payload(
    hazard_type: str, severity: str, location: str, language: str = "en"
) -> dict[str, str]:
    """Tool per Architecture §3.1 Agent 7. English only in Phase 1 — Ground
    Rule 1 keeps specialist agents persona/language-blind; localization
    happens at Agent 1's egress (or, for Sentinel's background dispatch in
    Phase 3, via a direct call to Agent 1's translate_from_english). Wiring
    that cross-agent call is Phase 3 work (Sentinel), not built here — this
    raises rather than silently returning English text mislabelled as
    localized."""
    if language != "en":
        raise NotImplementedError(
            f"generate_alert_payload has no localization for {language!r} yet — "
            "Phase 1 only builds the English text. Route through Agent 1's "
            "translate_from_english when this is called from Sentinel (Phase 3)."
        )
    text = f"{severity.upper()}: {hazard_type} near {location}."
    sms = f"[ORCA {severity.upper()}] {hazard_type} near {location}. Seek safety."[:160]
    return {"text": text, "sms": sms, "language": "en"}


# --- check_active_hazards ----------------------------------------------------

def check_active_hazards(lat: float, lon: float, radius_km: float = 25.0) -> dict:
    """Tool per Architecture §3.1 Agent 7. Source is "INCOIS + IMD feeds
    (via WIA)" per the architecture doc itself — composes Agent 4's tools
    rather than re-fetching, since Weather Intelligence already owns those
    integrations."""
    from orca.agents import weather_intelligence as wia  # via WIA, per architecture

    lightning = wia.get_lightning_nowcast(lat, lon, radius_km)
    basin: Literal["BoB", "AS"] = "BoB" if lon >= 77.5 else "AS"
    cyclone = wia.get_cyclone_status(basin)

    hazards = []
    if lightning["lightning_active"]:
        hazards.append({"type": "lightning", "severity": "DANGER"})
    for c in cyclone["active_cyclones"]:
        hazards.append({"type": "cyclone", "severity": c.get("severity", "unknown"), "detail": c})
    return {"hazards": hazards, "confidence": compute_confidence([lightning["confidence"], cyclone["confidence"]])}


# --- Agent entry point -------------------------------------------------------

def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Reads weather_data (Agent 4) and
    geospatial_data (Agent 6, or a Phase-1 fixture stub) from state — never
    fetches anything itself. Ground Rule 2: the verdict is arithmetic over
    already-gathered inputs, never a live call and never an LLM."""
    weather = state.get("weather_data") or {}
    geospatial = state.get("geospatial_data") or {}
    vessel_class: VesselClass = state.get("vessel_class") or "small_fishing"  # type: ignore[assignment]

    # Phase 1 simplification: takes the first hourly record as "now". A real
    # target_time_window match is the forecast-time-slider's job (§4.8,
    # Phase 2) — duplicating that logic here for one demo query isn't worth
    # it yet. Documented, not hidden.
    hourly = weather.get("hourly") or [{}]
    # Match forecast hour to target_time_window if present (e.g. tomorrow morning)
    target_window = state.get("target_time_window") or {}
    start_time = target_window.get("start")
    current = hourly[0]
    if start_time and len(hourly) > 1:
        for h in hourly:
            if h.get("time") and h["time"] >= start_time:
                current = h
                break

    # Resilience §5.7 safety-path rule: a wholly-failed weather agent (an
    # empty `weather_data`, current == {}) must not read as "0.0 m waves,
    # 0.0 km/h wind" — that is indistinguishable from genuinely calm
    # conditions and would silently produce a GO verdict on missing data.
    # conservative_or records the field name in `missing` without altering
    # the value passed to evaluate_marine_safety; the None -> 0.0 fallback
    # below is only for the arithmetic call, never for the confidence/verdict
    # decision, which is driven by `missing` instead.
    missing: list[str] = []
    wave_height_m = conservative_or(current.get("wave_height"), missing_field_name="wave_height_m", missing=missing)
    wind_speed_ms = conservative_or(current.get("wind_speed_10m"), missing_field_name="wind_speed_10m", missing=missing)
    # Same rule for Agent 6's output: a missing geospatial_data must not
    # silently read as "999nm from every boundary" (the safest possible
    # number) — that is a fabricated GO-shaped value, exactly what §5.7
    # forbids, so a genuinely-absent distance is tracked as missing too.
    imbl_distance_nm = conservative_or(geospatial.get("imbl_distance_nm"), missing_field_name="imbl_distance_nm", missing=missing)

    verdict = evaluate_marine_safety(
        wave_height_m=wave_height_m or 0.0,
        # state carries m/s (normalize.py convention); evaluate_marine_safety's
        # reference signature (Architecture §3.1) is fixed in km/h — ms_to_kmh
        # is the same conversion normalize.py uses in the other direction, not
        # an independently hardcoded factor.
        wind_speed_kmh=ms_to_kmh(wind_speed_ms or 0.0),
        lightning_active=weather.get("lightning_active", False),
        cyclone_alert=weather.get("cyclone_alert"),
        imbl_distance_nm=imbl_distance_nm if imbl_distance_nm is not None else 999.0,
        mpa_violation=geospatial.get("mpa_violation", False),
        vessel_class=vessel_class,
    )

    floor = safety_floor_for_missing_inputs(missing)
    if floor is not None and verdict["go_no_go"] == "GO":
        go_no_go, reason = floor
        verdict = {"status": "CAUTION_MISSING_DATA", "go_no_go": go_no_go, "reason": reason}

    confidence = compute_confidence(
        [c for c in [weather.get("confidence"), geospatial.get("confidence")] if c is not None]
    )
    if missing:
        # Missing required telemetry is never a HIGH- or MEDIUM-confidence
        # answer, whatever the upstream agents individually reported.
        confidence = Confidence(score="LOW_DATA", rationale=f"Missing required input(s): {', '.join(missing)}")

    return AgentResult(
        agent_name="risk_assessment",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={
            "wave_height_m": current.get("wave_height"), "lightning_active": weather.get("lightning_active"),
            "imbl_distance_nm": geospatial.get("imbl_distance_nm"), "vessel_class": vessel_class,
        },
        outputs=dict(verdict),
        source_provenance=SourceProvenance(
            dataset="Deterministic rules over Agent 4 + Agent 6 outputs",
            acquisition_timestamp=weather.get("acquisition_timestamp", ""),
            freshness_minutes=0,
        ),
        confidence=confidence,
    )
