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

import math
from typing import Literal, TypedDict

from orca import reconcile
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data.freshness import SOURCE_CLASS, past_staleness_ceiling
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

# P0.13 / prerequisite of R-AUTH-1: the DB's `vessel_class` enum
# (infra/db/001_init.sql:55, orca/auth/schemas.py:109) is the richer,
# user-facing vocabulary — catamaran / fibreglass / mechanised / trawler /
# cargo — and stays that way; this engine's three-way vocabulary above is
# what the safety math was written and reviewed against (Architecture §3.1),
# and stays that way too. One mapping at the single point a registered
# vessel enters this module, rather than two vocabularies drifting until a
# vessel silently becomes "small_fishing" or a request fails outright.
DB_VESSEL_CLASS_TO_RISK_CLASS: dict[str, VesselClass] = {
    "catamaran": "small_fishing",
    "fibreglass": "small_fishing",
    "mechanised": "mechanized_trawler",
    "trawler": "mechanized_trawler",
    "cargo": "cargo_vessel",
    "small_fishing": "small_fishing",
    "mechanized_trawler": "mechanized_trawler",
    "cargo_vessel": "cargo_vessel",
}


def risk_vessel_class(db_vessel_class: str | None) -> VesselClass:
    """A profile vessel's DB-enum class, translated to this module's
    vocabulary. Unknown or absent falls to "small_fishing" — the same
    conservative default `run()` already applies when no vessel is given at
    all, never a guess at a more capable class."""
    if db_vessel_class is None:
        return "small_fishing"
    return DB_VESSEL_CLASS_TO_RISK_CLASS.get(db_vessel_class, "small_fishing")


class SafetyVerdict(TypedDict):
    status: str
    go_no_go: Literal["GO", "CAUTION", "NO_GO"]
    reason: str


def _known(value: float | None) -> bool:
    """A measurement we can actually compare against a threshold. None is an
    absent reading; NaN/inf are what a masked grid cell or a failed geometry
    op produce. Both must be excluded from the bands below, because every
    comparison against NaN is False — `NaN >= danger_hs` and `NaN <= 1.0`
    are BOTH False, so an unguarded chain falls straight through to GO. That
    is the "GO-shaped number conjured from absent data" §5.7 forbids, and it
    is a live path, not a synthetic edge: ERA5 masks swh as NaN at
    Thoothukudi's own point (see orca/replay/gaja.py)."""
    return value is not None and math.isfinite(value)


def evaluate_marine_safety(
    wave_height_m: float | None,
    wind_speed_kmh: float | None,
    lightning_active: bool,
    cyclone_alert: str | None,
    imbl_distance_nm: float | None,
    mpa_violation: bool,
    vessel_class: VesselClass = "small_fishing",
) -> SafetyVerdict:
    wind_delta, hs_delta = _VESSEL_DELTAS[vessel_class]
    danger_wind, danger_hs = 55.0 + wind_delta, 3.5 + hs_delta
    caution_wind, caution_hs = 35.0 + wind_delta, 2.0 + hs_delta

    # Thresholds and ordering below are transcribed verbatim from Architecture
    # §3.1 and must stay that way; the only addition is the _known() guard on
    # each comparison, so an unreadable input can never *clear* a hazard band.
    unknown = [
        name
        for name, value in (
            ("wave_height_m", wave_height_m),
            ("wind_speed_kmh", wind_speed_kmh),
            ("imbl_distance_nm", imbl_distance_nm),
        )
        if not _known(value)
    ]

    if (
        cyclone_alert in ("Red", "Orange")
        or (_known(wave_height_m) and wave_height_m >= danger_hs)  # type: ignore[operator]
        or (_known(wind_speed_kmh) and wind_speed_kmh >= danger_wind)  # type: ignore[operator]
    ):
        return {"status": "DANGER", "go_no_go": "NO_GO", "reason": "Severe Weather / Cyclone Threshold Exceeded"}
    if lightning_active:
        return {"status": "DANGER", "go_no_go": "NO_GO", "reason": "Active Convective Lightning Strike Zone"}
    if (_known(imbl_distance_nm) and imbl_distance_nm <= 1.0) or mpa_violation:  # type: ignore[operator]
        return {"status": "CRITICAL_GEOFENCE", "go_no_go": "NO_GO", "reason": "Imminent Boundary or MPA Breach"}
    if (
        (_known(wave_height_m) and caution_hs <= wave_height_m < danger_hs)  # type: ignore[operator]
        or (_known(wind_speed_kmh) and caution_wind <= wind_speed_kmh < danger_wind)  # type: ignore[operator]
        or (_known(imbl_distance_nm) and imbl_distance_nm <= 3.0)  # type: ignore[operator]
    ):
        return {"status": "WARNING", "go_no_go": "CAUTION", "reason": "Rough Sea State / Boundary Proximity"}
    # Every hazard band came back clear, but a band can only be trusted when
    # its input was readable — so an unreadable input degrades to CAUTION
    # naming it, never GO (plan §5.7).
    if unknown:
        return {
            "status": "CAUTION_MISSING_DATA",
            "go_no_go": "CAUTION",
            "reason": f"Insufficient data — missing: {', '.join(unknown)}",
        }
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

# P3.6 (`R-PS-7`) — the four languages with verified TTS end-to-end
# (orca/agents/voice.py's MmsTtsBackend docstring: en/hi/ta/te round-trip
# confirmed). The other five core languages have a translation backend
# (IndicTrans2 covers all ten) but no verified voice output, and the DLC is
# explicit: mislabelled English is worse than nothing, so they still raise
# rather than silently ship an unverified alert as if it were checked.
_ALERT_VERIFIED_LANGUAGES = frozenset({"en", "hi", "ta", "te"})


def generate_alert_payload(
    hazard_type: str, severity: str, location: str, language: str = "en"
) -> dict[str, str]:
    """Tool per Architecture §3.1 Agent 7. Ground Rule 1 keeps specialist
    agents persona/language-blind for the query path; Sentinel's background
    dispatch has no query-time egress to route through, so this is the one
    place a specialist agent calls Agent 1's `translate_from_english`
    directly (P3.6) — not a second localization system, the same seam.
    Still raises for a language with no verified voice output (module-level
    `_ALERT_VERIFIED_LANGUAGES`): a Tamil-speaking fisherman getting no
    alert is a known, disclosed gap; getting one mislabelled as Odia when
    nobody has heard it spoken is a worse one."""
    if language not in _ALERT_VERIFIED_LANGUAGES:
        raise NotImplementedError(
            f"generate_alert_payload has no verified localization for {language!r} yet "
            f"— only {sorted(_ALERT_VERIFIED_LANGUAGES)} have confirmed end-to-end voice "
            "(orca/agents/voice.py). Falls back to English at the caller (sentinel.build_alert)."
        )
    text = f"{severity.upper()}: {hazard_type} near {location}."
    sms = f"[SAGAR SARATHI {severity.upper()}] {hazard_type} near {location}. Seek safety."[:160]
    if language != "en":
        from orca.agents.language import translate_from_english

        text = translate_from_english(text, target=language)  # type: ignore[arg-type]
        # Not re-truncated to 160 chars here: that limit is GSM-7's, and a
        # translated Indic alert is UCS-2 (P3.11's render_sms), a different
        # per-part budget this function has no business assuming.
        sms = translate_from_english(sms, target=language)  # type: ignore[arg-type]
    return {"text": text, "sms": sms, "language": language}


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
    requested = state.get("vessel_class") or "small_fishing"
    # A class this engine has no thresholds for must never raise: run() sits
    # behind an exception boundary that turns a raise into an EMPTY verdict,
    # and an empty verdict is worse than a strict one. Translate a DB-enum name
    # if that is what arrived, and otherwise fall to the strictest class —
    # never to a more capable one. (P2.9's first version fed "trawler" here.)
    vessel_class: VesselClass = (
        requested if requested in _VESSEL_DELTAS  # type: ignore[assignment]
        else DB_VESSEL_CLASS_TO_RISK_CLASS.get(requested, "small_fishing")
    )

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

    # P2.4 (`R-PS-5`, `R-AGENT-3`) — cross-source reconciliation, before the
    # bands rather than after them. Where Open-Meteo and INCOIS OSF both
    # report a variable and disagree past `orca/reconcile.py`'s threshold, the
    # verdict is computed from the *conservative* reading, not from whichever
    # feed happens to be primary. Pure arithmetic and no LLM — this is the
    # safety path, and `scripts/verify_ci_guards.py` holds it to that.
    #
    # This is the first thing in this module to read `ocean_data`. The note in
    # graph.reporting_run about RAA "never reading ocean_data" is updated
    # there; the *verdict* still depends only on wave/wind/boundary, which is
    # what that note is protecting — nothing here consults PFZ, tide or trend.
    reconciliation = reconcile.reconcile_all(weather, state.get("ocean_data") or {})
    reconciled_wave = reconcile.resolved(reconciliation, "wave_height_m")
    reconciled_wind = reconcile.resolved(reconciliation, "wind_speed_ms")
    if reconciled_wave is not None and wave_height_m is not None:
        wave_height_m = reconciled_wave
    if reconciled_wind is not None and wind_speed_ms is not None:
        wind_speed_ms = reconciled_wind
    # The convective pair, and the one reconciliation that can change the
    # verdict on its own. `lightning_active` is a hard NO_GO band, and until
    # now it was read from Open-Meteo's CAPE proxy alone while IMD's own
    # district nowcast sat in the same dict saying the opposite. Either source
    # reporting lightning is now enough — the only direction this can move a
    # verdict is toward NO_GO, which is the direction Ground Rule 4 requires.
    lightning_active = bool(weather.get("lightning_active", False))
    reconciled_lightning = reconcile.resolved(reconciliation, "lightning_active")
    if reconciled_lightning is not None:
        lightning_active = bool(reconciled_lightning) or lightning_active

    # Unreadable inputs are passed through as None rather than coerced to a
    # stand-in number. The old `or 0.0` read as "dead calm" and the old
    # `else 999.0` as "nowhere near any boundary" — both are the safest
    # possible values, i.e. exactly the GO-shaped fabrications §5.7 forbids.
    # evaluate_marine_safety now takes None and degrades to CAUTION itself,
    # so the floor below is a second line of defence rather than the only one.
    verdict = evaluate_marine_safety(
        wave_height_m=wave_height_m,
        # state carries m/s (normalize.py convention); evaluate_marine_safety's
        # reference signature (Architecture §3.1) is fixed in km/h — ms_to_kmh
        # is the same conversion normalize.py uses in the other direction, not
        # an independently hardcoded factor.
        wind_speed_kmh=ms_to_kmh(wind_speed_ms) if wind_speed_ms is not None else None,
        lightning_active=lightning_active,
        cyclone_alert=weather.get("cyclone_alert"),
        imbl_distance_nm=imbl_distance_nm,
        mpa_violation=geospatial.get("mpa_violation", False),
        vessel_class=vessel_class,
    )

    # evaluate_marine_safety degrades to CAUTION on its own when an input is
    # unreadable, but it can only name its own parameters (`wind_speed_kmh`).
    # `missing` holds the names of the *state* fields that actually came back
    # absent (`wind_speed_10m`), which is what an operator has to go looking
    # for, so the floor's wording wins whenever no readable input proved a
    # hazard by itself.
    # Staleness ceiling (P0.5): weather is the one input read with a measured
    # age. Open-Meteo is LIVE-class; a cached copy past the ceiling cannot back
    # a GO however calm it looks.
    stale: list[str] = []
    weather_age = weather.get("freshness_minutes")
    if isinstance(weather_age, int) and past_staleness_ceiling(weather_age, SOURCE_CLASS["open_meteo_marine"]):
        stale.append(f"{weather.get('dataset') or 'weather forecast'} ({weather_age // 60} h old)")

    floor = safety_floor_for_missing_inputs(missing, stale)
    if floor is not None and verdict["status"] in ("SAFE", "CAUTION_MISSING_DATA"):
        go_no_go, reason = floor
        status = "CAUTION_MISSING_DATA" if missing else "CAUTION_STALE_DATA"
        verdict = {"status": status, "go_no_go": go_no_go, "reason": reason}

    confidence = compute_confidence(
        [c for c in [weather.get("confidence"), geospatial.get("confidence")] if c is not None]
    )
    if missing:
        # Missing required telemetry is never a HIGH- or MEDIUM-confidence
        # answer, whatever the upstream agents individually reported.
        confidence = Confidence(score="LOW_DATA", rationale=f"Missing required input(s): {', '.join(missing)}")
    elif stale:
        confidence = Confidence(score="LOW_DATA", rationale=f"Stale input(s): {', '.join(stale)}")
    elif reconcile.penalty(reconciliation):
        # P2.4 rule 3 — a disagreement between two sources costs exactly one
        # tier, and never raises one. HIGH becomes MEDIUM; MEDIUM and LOW_DATA
        # become LOW_DATA. Applied after the missing/stale branches above
        # because those are already the floor and must not be lifted by this.
        dropped: Literal["MEDIUM", "LOW_DATA"] = "MEDIUM" if confidence.score == "HIGH" else "LOW_DATA"
        confidence = Confidence(
            score=dropped,
            rationale=f"{confidence.rationale} — reduced one tier: {' '.join(reconcile.statements(reconciliation))}",
        )

    # Same lookup `evaluate_marine_safety` made internally to compare the
    # verdict's own bands — recomputed here (not returned by that function)
    # so the UI can show what the reading was measured against.
    wind_delta, hs_delta = _VESSEL_DELTAS[vessel_class]

    return AgentResult(
        agent_name="risk_assessment",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={
            "wave_height_m": current.get("wave_height"), "lightning_active": lightning_active,
            "imbl_distance_nm": geospatial.get("imbl_distance_nm"), "vessel_class": vessel_class,
        },
        outputs={
            **verdict,
            # P2.4 — every pair that was compared, including the ones that
            # agreed: "we checked and they matched" is evidence too, and a
            # judge asking "how do you know your sources agree" has to be able
            # to see the comparison, not be told it happened. Only the
            # disagreements become sentences on the card (reconcile.statements).
            "reconciliation": reconciliation,
            # P4.1 — the bands `evaluate_marine_safety` actually compared this
            # answer against, for this vessel class, so the UI can draw a
            # value against its limit ("1.2 m / 2.0 m caution") instead of a
            # bare reading. The same two numbers `_VESSEL_DELTAS` already
            # produces — never a second copy of the thresholds themselves.
            "thresholds": {
                "vessel_class": vessel_class,
                "caution_wave_m": 2.0 + hs_delta,
                "danger_wave_m": 3.5 + hs_delta,
                "caution_wind_kmh": 35.0 + wind_delta,
                "danger_wind_kmh": 55.0 + wind_delta,
            },
            # The readings this verdict was computed from — the matched hour,
            # after reconciliation — so the written answer quotes the same
            # numbers the verdict used rather than re-deriving "now" from
            # `hourly` itself (chatbot plan C0.2e). None stays None: an
            # unreadable input is never written up as calm.
            "readings": {
                "wave_height_m": wave_height_m,
                "wind_speed_ms": wind_speed_ms,
                "valid_time": current.get("time"),
            },
        },
        source_provenance=SourceProvenance(
            dataset="Deterministic rules over Agent 4 + Agent 6 outputs",
            acquisition_timestamp=weather.get("acquisition_timestamp", ""),
            freshness_minutes=0,
        ),
        confidence=confidence,
        # The three inputs conservative_or tracks (wave, wind, IMBL distance):
        # how many actually arrived is this agent's measured coverage.
        coverage=(3 - len(missing), 3),
    )
