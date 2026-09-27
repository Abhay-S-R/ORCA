"""The boundary distance reaches the narrator only when it was asked about (or
is why the verdict is not GO), and a LOW_DATA answer carries the rationale
of the inputs that made it LOW_DATA, so "Data limited" can say why."""
from __future__ import annotations

from orca.agents import ocean_analytics, reporting
from orca.contracts import Confidence
from orca.graph.graph import reporting_run

_GO = {"go_no_go": "GO", "status": "SAFE", "reason": "All Parameters Within Safe Operational Limits"}
_STATE = {
    "query_id": "q1", "reasoning_depth": "SHALLOW", "stakeholder_persona": "fisherman",
    "normalized_english_query": "nearest fishing zones near kochi",
    "geospatial_data": {"imbl_distance_nm": 146.6, "mpa_violation": False},
    "ocean_data": {
        "nearest_pfz": {"distance_km": 41.5},
        "confidence": Confidence(score="LOW_DATA", rationale="INCOIS PFZ advisory 8 days old [score 39: coverage 3/4]"),
    },
    "risk_assessment": _GO, "confidence_tier": "MEDIUM",
}


def _narrated_imbl(monkeypatch, **overrides):
    seen = {}

    def fake(query, verdict, results, **kw):
        seen["geo"] = next(r.outputs for r in results if r.agent_name == "geospatial")
        return "answer"

    monkeypatch.setattr(reporting, "synthesize_narrative", fake)
    result = reporting_run({**_STATE, **overrides})  # type: ignore[arg-type]
    return seen["geo"]["imbl_distance_nm"], result


def test_boundary_distance_is_withheld_from_a_question_not_about_it(monkeypatch):
    imbl, _ = _narrated_imbl(monkeypatch, matched_intent_rows=["PFZ_NEAREST"])
    assert imbl is None


def test_boundary_distance_is_narrated_when_asked_or_when_it_is_not_go(monkeypatch):
    assert _narrated_imbl(monkeypatch, matched_intent_rows=["ZONES_TO_AVOID"])[0] == 146.6
    caution = {**_GO, "go_no_go": "CAUTION"}
    assert _narrated_imbl(monkeypatch, matched_intent_rows=["PFZ_NEAREST"], risk_assessment=caution)[0] == 146.6


def test_low_data_answer_says_which_input_limited_it(monkeypatch):
    _, result = _narrated_imbl(monkeypatch, matched_intent_rows=["PFZ_NEAREST"])
    assert result.confidence.score == "LOW_DATA"
    assert result.outputs["confidence_reason"] == "INCOIS PFZ advisory 8 days old"


def test_ocean_rationale_names_only_the_inputs_that_set_the_grade():
    c = ocean_analytics._worst(
        Confidence(score="HIGH", rationale="tide table"),
        Confidence(score="LOW_DATA", rationale="stale advisory"),
    )
    assert (c.score, c.rationale) == ("LOW_DATA", "stale advisory")
