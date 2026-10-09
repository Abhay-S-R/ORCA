"""P2.4 (`R-PS-5`, `R-AGENT-3`) — cross-source reconciliation.

Two sources cover wave height off Thoothukudi: Open-Meteo's marine forecast
(Agent 4) and INCOIS' own Ocean State Forecast WW3 point series (Agent 5).
Until now ORCA read both and reported one, which is "we combine sources".
PS-C5 asks for something else: when they disagree, say so, take the
conservative one, and lose confidence for it. That is reconciliation, and it
is the difference between a system that has many feeds and a system that
knows its feeds can be wrong.

**No LLM, by construction** — this module imports nothing from `orca.llm` and
`risk_assessment.py` (which calls it) must keep passing
`scripts/verify_ci_guards.py`. It is subtraction and a comparison.

Three rules, all of them one-directional:

1. **Only compare like with like in time.** Two readings taken eight hours
   apart are two different states of the sea, not a disagreement — the same
   reasoning `weather_intelligence`'s `lightning_source_agreement` already
   applies to IMD's nowcast validity window. Past `MAX_TIME_GAP_MINUTES` the
   pair is reported `not_comparable` and changes nothing.
2. **Conservative wins, never the average.** Ground Rule 4: uncertainty
   degrades conservative, it never nets out. For wave height and wind speed
   conservative is the *higher* reading — the one that is more likely to
   produce a CAUTION.
3. **Disagreement costs confidence.** One tier, once, however many variables
   disagreed: a second disagreeing variable is more evidence of the same
   fact (these feeds differ here), not a second independent reason to doubt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Past this, two readings describe different times, not the same time
# differently. Six hours is the coarser of the two feeds' own update cadences
# (INCOIS OSF publishes every 6 h; see discovery.SOURCE_REGISTRY).
MAX_TIME_GAP_MINUTES = 360

# A divergence has to clear BOTH an absolute floor and a relative one to
# count. The floor stops a 0.05 m difference between two 0.2 m readings —
# arithmetically a 25 % divergence — from being announced as a disagreement;
# the ratio stops a fixed 0.5 m from being treated as equally significant at
# 0.6 m and at 4.0 m.
@dataclass(frozen=True)
class Variable:
    key: str
    label: str
    unit: str
    absolute_floor: float
    relative_threshold: float  # fraction of the larger reading


WAVE_HEIGHT = Variable("wave_height_m", "wave height", "m", absolute_floor=0.4, relative_threshold=0.30)
WIND_SPEED = Variable("wind_speed_ms", "wind speed", "m/s", absolute_floor=2.0, relative_threshold=0.30)


@dataclass(frozen=True)
class Reading:
    value: float | None
    source: str
    timestamp: str | None  # ISO 8601; None means "no time recorded"


def _finite(value: Any) -> float | None:
    """A reading we can subtract. None is absent; NaN is what a masked grid
    cell produces, and every comparison against it is False — which would
    silently report "no divergence" (see risk_assessment._known for the same
    trap on the verdict side)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _gap_minutes(a: str | None, b: str | None) -> float | None:
    """None means at least one reading carries no time — which is *not* the
    same as "they are simultaneous". An untimed pair is compared anyway
    (better than silently skipping a real disagreement) but says so."""
    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return None
    return abs((da - db).total_seconds()) / 60.0


def compare(variable: Variable, primary: Reading, secondary: Reading) -> dict[str, Any] | None:
    """One variable, two sources. Returns None when there is nothing to
    compare (either reading absent) — an absent second opinion is not
    agreement and must not be recorded as one."""
    a, b = _finite(primary.value), _finite(secondary.value)
    if a is None or b is None:
        return None

    gap = _gap_minutes(primary.timestamp, secondary.timestamp)
    divergence = abs(a - b)
    larger = max(abs(a), abs(b))
    relative = divergence / larger if larger else 0.0
    conservative = max(a, b)
    conservative_source = primary.source if a >= b else secondary.source

    row: dict[str, Any] = {
        "variable": variable.key,
        "label": variable.label,
        "unit": variable.unit,
        "primary": {"value": round(a, 3), "source": primary.source, "timestamp": primary.timestamp},
        "secondary": {"value": round(b, 3), "source": secondary.source, "timestamp": secondary.timestamp},
        "divergence": round(divergence, 3),
        "divergence_pct": round(relative * 100, 1),
        "time_gap_minutes": None if gap is None else round(gap, 1),
    }

    if gap is not None and gap > MAX_TIME_GAP_MINUTES:
        row.update({
            "status": "not_comparable",
            "used_value": round(a, 3),
            "used_source": primary.source,
            "confidence_penalty": False,
            "statement": (
                f"{primary.source} and {secondary.source} both report {variable.label}, but "
                f"{round(gap / 60)} h apart — too far to compare. Using {primary.source}."
            ),
        })
        return row

    disagrees = divergence >= variable.absolute_floor and relative >= variable.relative_threshold
    if not disagrees:
        row.update({
            "status": "agree",
            "used_value": round(a, 3),
            "used_source": primary.source,
            "confidence_penalty": False,
            "statement": (
                f"{primary.source} and {secondary.source} agree on {variable.label} "
                f"({a:.1f} {variable.unit} vs {b:.1f} {variable.unit})."
            ),
        })
        return row

    row.update({
        "status": "diverged",
        "used_value": round(conservative, 3),
        "used_source": conservative_source,
        "confidence_penalty": True,
        "statement": (
            f"Two sources disagree on {variable.label} ({a:.1f} {variable.unit} vs "
            f"{b:.1f} {variable.unit}). Using the higher. Confidence reduced."
        ),
    })
    return row


def reconcile_weather(weather: dict[str, Any], ocean: dict[str, Any]) -> list[dict[str, Any]]:
    """The two pairs ORCA actually holds two sources for today.

    Primary is Open-Meteo, because it is the feed the verdict has always been
    computed from and the one with a live timestamp; INCOIS OSF is the second
    opinion. "Primary" decides nothing on its own — where the two diverge the
    conservative reading wins regardless of which feed it came from.
    """
    hourly = (weather.get("hourly") or [{}])[0]
    weather_source = weather.get("dataset") or "Open-Meteo Marine"
    weather_time = hourly.get("time") or weather.get("acquisition_timestamp")

    osf = ocean.get("osf_point_forecast") or {}
    wave = osf.get("wave") or {}
    if not wave or not osf.get("available"):
        return []
    osf_source = "INCOIS Ocean State Forecast (WW3)"
    osf_time = wave.get("forecast_time")

    rows = []
    for variable, primary_value, secondary_value in (
        (WAVE_HEIGHT, hourly.get("wave_height"), wave.get("significant_wave_height_m")),
        (WIND_SPEED, hourly.get("wind_speed_10m"), wave.get("wind_speed_ms")),
    ):
        row = compare(
            variable,
            Reading(primary_value, weather_source, weather_time),
            Reading(secondary_value, osf_source, osf_time),
        )
        if row is not None:
            rows.append(row)
    return rows


def reconcile_all(weather: dict[str, Any], ocean: dict[str, Any]) -> list[dict[str, Any]]:
    """Every pair ORCA holds two sources for: the numeric ones against INCOIS
    OSF, and the categorical convective one against IMD."""
    rows = reconcile_weather(weather, ocean)
    lightning = reconcile_lightning(weather)
    if lightning is not None:
        rows.append(lightning)
    return rows


def reconcile_lightning(weather: dict[str, Any]) -> dict[str, Any] | None:
    """Convective risk, where the two sources are categorical rather than
    numeric: Open-Meteo's CAPE proxy and IMD's own Damini district nowcast.

    `weather_intelligence.run` has computed this agreement for a while and
    **nothing acted on it** — the flag reached the response and the verdict
    went on being taken from the proxy alone. That is the half of PS-C5 this
    point is about: noticing a disagreement is not reconciling it.

    Conservative here is unambiguous and one-directional: if either source
    says there is lightning, the verdict is computed as though there is.
    `single_source` (IMD's snapshot expired or empty) is not a disagreement —
    two statements about different days never are, which is the same rule
    `MAX_TIME_GAP_MINUTES` applies to the numeric pairs.
    """
    agreement = weather.get("lightning_source_agreement")
    if agreement not in ("agree", "disagree"):
        return None
    proxy = bool(weather.get("lightning_active"))
    imd = bool((weather.get("imd_nowcast") or {}).get("lightning_flagged"))
    conservative = proxy or imd
    imd_source = weather.get("imd_nowcast_dataset") or "IMD Damini nowcast"
    primary_source = weather.get("dataset") or "Open-Meteo Marine"

    row: dict[str, Any] = {
        "variable": "lightning_active",
        "label": "lightning",
        "unit": "",
        "primary": {"value": proxy, "source": primary_source, "timestamp": weather.get("acquisition_timestamp")},
        "secondary": {"value": imd, "source": imd_source, "timestamp": (weather.get("imd_nowcast") or {}).get("issued_at")},
        "divergence": None,
        "divergence_pct": None,
        "time_gap_minutes": None,
        "used_value": conservative,
        "used_source": imd_source if imd and not proxy else primary_source,
    }
    if agreement == "agree":
        row.update({
            "status": "agree",
            "confidence_penalty": False,
            "statement": f"{primary_source} and {imd_source} agree on lightning ({'active' if proxy else 'clear'}).",
        })
        return row
    row.update({
        "status": "diverged",
        "confidence_penalty": True,
        "statement": (
            f"Two sources disagree on lightning ({primary_source}: "
            f"{'active' if proxy else 'clear'} vs {imd_source}: {'active' if imd else 'clear'}). "
            "Treating it as active. Confidence reduced."
        ),
    })
    return row


def resolved(rows: list[dict[str, Any]], variable_key: str) -> float | None:
    """The value the verdict should be computed from for `variable_key` —
    the conservative one where the sources diverged, the primary otherwise.
    None when nothing was reconciled, so the caller keeps its own reading
    rather than being handed a substitute it cannot trace."""
    for row in rows:
        if row["variable"] == variable_key:
            return row.get("used_value")
    return None


def penalty(rows: list[dict[str, Any]]) -> bool:
    """Whether confidence drops a tier. Once, not once per variable — see
    rule 3 in the module docstring."""
    return any(row.get("confidence_penalty") for row in rows)


def statements(rows: list[dict[str, Any]]) -> list[str]:
    """The sentences that go ABOVE the answer, as disclosures. Only real
    disagreements. Two feeds quietly agreeing is not news, and — the lesson
    of the first live run — neither is a second source too old to compare:
    the INCOIS OSF point series on disk is days old, so `not_comparable` fired
    on every single query and put two "75 h apart — too far to compare"
    banners above every answer. That is the same skim-training noise P2.2
    removes from the verdict, and it is not a hazard: nothing about the answer
    is degraded by a second opinion being unusable. Those rows still travel
    with the response and render in the cross-source panel below the answer,
    where the comparison is evidence rather than an alert."""
    return [row["statement"] for row in rows if row["status"] == "diverged"]


if __name__ == "__main__":
    t = "2026-09-20T06:00:00Z"

    # The plan's own worked example: 1.1 m against 2.4 m.
    diverged = compare(WAVE_HEIGHT, Reading(1.1, "Open-Meteo", t), Reading(2.4, "INCOIS OSF", t))
    assert diverged is not None
    assert diverged["status"] == "diverged"
    assert diverged["used_value"] == 2.4, diverged
    assert diverged["used_source"] == "INCOIS OSF"
    assert diverged["confidence_penalty"] is True
    assert "Using the higher. Confidence reduced." in diverged["statement"]

    # The conservative reading wins even when it is the primary's.
    other_way = compare(WAVE_HEIGHT, Reading(2.4, "Open-Meteo", t), Reading(1.1, "INCOIS OSF", t))
    assert other_way is not None and other_way["used_value"] == 2.4 and other_way["used_source"] == "Open-Meteo"

    # Small absolute differences between small readings are not disagreements,
    # however large the percentage.
    calm = compare(WAVE_HEIGHT, Reading(0.20, "A", t), Reading(0.32, "B", t))
    assert calm is not None and calm["status"] == "agree" and calm["confidence_penalty"] is False
    # ... and a large absolute difference between large readings that is
    # proportionally small is not one either.
    big = compare(WAVE_HEIGHT, Reading(4.0, "A", t), Reading(4.5, "B", t))
    assert big is not None and big["status"] == "agree", big

    # Two readings eight hours apart are two sea states, not a disagreement.
    apart = compare(WAVE_HEIGHT, Reading(1.1, "A", "2026-09-20T06:00:00Z"), Reading(2.4, "B", "2026-09-19T20:00:00Z"))
    assert apart is not None and apart["status"] == "not_comparable"
    assert apart["used_value"] == 1.1 and apart["confidence_penalty"] is False

    # An absent or unreadable second opinion is never recorded as agreement.
    assert compare(WAVE_HEIGHT, Reading(1.1, "A", t), Reading(None, "B", t)) is None
    assert compare(WAVE_HEIGHT, Reading(1.1, "A", t), Reading(float("nan"), "B", t)) is None

    # The whole-state path, with the real output shapes.
    rows = reconcile_weather(
        {"hourly": [{"time": t, "wave_height": 1.1, "wind_speed_10m": 3.0}], "dataset": "Open-Meteo Marine"},
        {"osf_point_forecast": {"available": True, "wave": {
            "forecast_time": t, "significant_wave_height_m": 2.4, "wind_speed_ms": 3.4,
        }}},
    )
    assert len(rows) == 2, rows
    assert resolved(rows, "wave_height_m") == 2.4
    assert resolved(rows, "wind_speed_ms") == 3.0, "wind agreed, so the primary stands"
    assert penalty(rows) is True
    assert len(statements(rows)) == 1, "only the disagreement is worth a sentence"
    assert resolved(rows, "not_a_variable") is None

    # The categorical pair. A disagreement is resolved toward "active" —
    # whichever source said so — and costs a tier.
    disagree = reconcile_lightning({
        "lightning_source_agreement": "disagree", "lightning_active": False,
        "imd_nowcast": {"lightning_flagged": True}, "dataset": "Open-Meteo", "imd_nowcast_dataset": "IMD Damini",
    })
    assert disagree is not None and disagree["status"] == "diverged"
    assert disagree["used_value"] is True, "either source saying lightning must win"
    assert disagree["used_source"] == "IMD Damini"
    assert disagree["confidence_penalty"] is True
    # ... and in the other direction too: the proxy alone is enough.
    other = reconcile_lightning({
        "lightning_source_agreement": "disagree", "lightning_active": True,
        "imd_nowcast": {"lightning_flagged": False},
    })
    assert other is not None and other["used_value"] is True
    agree_row = reconcile_lightning({
        "lightning_source_agreement": "agree", "lightning_active": False,
        "imd_nowcast": {"lightning_flagged": False},
    })
    assert agree_row is not None and agree_row["status"] == "agree" and agree_row["confidence_penalty"] is False
    # An expired or absent IMD snapshot is not a second opinion.
    assert reconcile_lightning({"lightning_source_agreement": "single_source", "lightning_active": True}) is None
    assert reconcile_lightning({}) is None

    # No second source at all: nothing is reconciled, and nothing is claimed.
    assert reconcile_weather({"hourly": [{"wave_height": 1.1}]}, {}) == []
    assert reconcile_all({"hourly": [{"wave_height": 1.1}]}, {}) == []
    assert reconcile_weather({"hourly": [{"wave_height": 1.1}]}, {"osf_point_forecast": {"available": False}}) == []
    assert penalty([]) is False and statements([]) == []
    print("reconcile self-check ok")
