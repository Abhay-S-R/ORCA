"""Per-agent confidence score — deterministic, from measured factors only.

Every agent already sets a rule label (HIGH / MEDIUM / LOW_DATA) with a
rationale. This turns that label plus what the agent measured about its own
inputs into a 0–100 number, so a judge can see *why* a label is what it is:

    score = 100 × status × data_age × fallback × coverage, capped by the rule label

A factor the agent did not measure is left out of the product and reported
as "not measured" — it never counts as a perfect 1.0 it didn't earn. No LLM
anywhere: the Critic's own LLM-derived pass/fail arrives here only as its rule
label, and this number never feeds `evaluate_marine_safety`.

The label shown on /ask is the score's band, which by construction is never
higher than the agent's own rule label (the cap). The number itself goes to
the trace and /reasoning, not to the /ask pills.
"""
from __future__ import annotations

from typing import Any

from orca.contracts import AgentResult
from orca.data.freshness import MAX_AGE_MINUTES, past_staleness_ceiling

_STATUS = {"ok": 1.0, "degraded": 0.6, "failed": 0.0, "skipped": 0.0, "cancelled": 0.0}
# ponytail: step weights, not a fitted curve — the evidence to fit one is P6.1's
# confusion-matrix work. Change them here only; every agent reads this table.
_FALLBACK = (1.0, 0.8, 0.6, 0.4)
_AGE_WITHIN, _AGE_2X, _AGE_BEYOND = 1.0, 0.7, 0.4
_CAP = {"HIGH": 100, "MEDIUM": 74, "LOW_DATA": 39}


def band(score: int) -> str:
    return "HIGH" if score >= 75 else "MEDIUM" if score >= 40 else "LOW_DATA"


def _age_factor(age_minutes: int, freshness_class: str) -> tuple[float, str]:
    max_age = MAX_AGE_MINUTES.get(freshness_class)  # type: ignore[call-overload]
    if max_age is None:
        return 1.0, f"{freshness_class} source — age does not apply"
    if age_minutes <= max_age:
        return _AGE_WITHIN, f"{age_minutes} min old, within {freshness_class} window"
    # Same ceiling that floors the verdict to CAUTION (risk_assessment, P0.5),
    # so a LOW score for age and a stale-data CAUTION always agree.
    if not past_staleness_ceiling(age_minutes, freshness_class):  # type: ignore[arg-type]
        return _AGE_2X, f"{age_minutes} min old, past {freshness_class} window"
    return _AGE_BEYOND, f"{age_minutes} min old, past the staleness ceiling"


def score_agent(result: AgentResult) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []

    def add(name: str, value: float | None, detail: str) -> None:
        factors.append({"factor": name, "value": value, "detail": detail})

    add("status", _STATUS.get(result.status, 0.0), result.status)

    if result.data_age_minutes is not None and result.freshness_class:
        value, detail = _age_factor(result.data_age_minutes, result.freshness_class)
        add("data_age", value, detail)
    else:
        add("data_age", None, "not measured")

    if result.fallback_depth is not None:
        depth = result.fallback_depth
        add("fallback", _FALLBACK[min(depth, len(_FALLBACK) - 1)],
            "primary source" if depth == 0 else f"fallback rung {depth}")
    else:
        add("fallback", None, "not measured")

    if result.coverage is not None and result.coverage[1] > 0:
        present, expected = result.coverage
        add("coverage", present / expected, f"{present}/{expected} expected readings present")
    else:
        add("coverage", None, "not measured")

    raw = 100.0
    for f in factors:
        if f["value"] is not None:
            raw *= f["value"]
    cap = _CAP.get(result.confidence.score, _CAP["LOW_DATA"])
    score = min(round(raw), cap)
    return {
        "score": score,
        "label": band(score),
        "rule_label": result.confidence.score,
        "rule_rationale": result.confidence.rationale,
        "capped_by_rule_label": round(raw) > cap,
        "factors": factors,
    }
