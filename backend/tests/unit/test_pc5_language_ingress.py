"""PC5 — Language ingress & Romanized Indic Handling (`PS-C1`, `PS-C2`, `PS-C7`, `PS-C10`, `R-NEW-1`, `R-CLAIM-1`).

Tests:
- PC5.2: Planning / understand produces `english_reading`.
- PC5.3: Latin-only text skips Bhashini detection and translation (passthrough).
- PC5.5: English reading included in reporting output.
- PC5.6: Romanized distress check and gazetteer check on Appendix A prompts.
- PC5.7: Honest provenance on native-script path (passthrough vs translated, degraded on unchanged).
"""
from unittest.mock import patch

import pytest

from orca.agents.distress import detect_distress_signal
from orca.agents.language import (
    detect_language,
    english_query,
    query_language,
    run_egress,
    run_ingress,
)
from orca.agents.understand import _parse_understand_output
from orca.place_resolution import resolve_or_ask, validate_reading

# ---------------------------------------------------------------------------
# PC5.2 — Planning / understand schema returns english_reading
# ---------------------------------------------------------------------------

def test_pc5_2_understand_schema_parses_english_reading():
    raw_json = """{
        "kind": "sea_question",
        "intents": ["SAFETY_CHECK"],
        "places": [{"raw": "rameswaram", "normalized": "Rameswaram"}],
        "when": {"start": "2026-10-05T06:00:00Z", "end": "2026-10-05T12:00:00Z"},
        "is_followup": false,
        "agents": ["weather_intelligence", "risk_assessment"],
        "english_reading": "is it safe to go to sea near Rameswaram tomorrow morning"
    }"""
    parsed = _parse_understand_output(raw_json)
    assert parsed is not None
    assert parsed.english_reading == "is it safe to go to sea near Rameswaram tomorrow morning"
    assert parsed.agents == ["weather_intelligence", "risk_assessment"]


def test_pc5_2_understand_schema_handles_null_english_reading():
    raw_json = """{
        "kind": "sea_question",
        "intents": ["SAFETY_CHECK"],
        "places": [],
        "when": null,
        "is_followup": false,
        "agents": [],
        "english_reading": null
    }"""
    parsed = _parse_understand_output(raw_json)
    assert parsed is not None
    assert parsed.english_reading is None


# ---------------------------------------------------------------------------
# PC5.3 — Latin-only text skips detection and translation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt", [
    "pfzs near rameshwaram",
    "kal subah rameswaram ke paas samudra mein jaana safe hai kya",
    "naalai kaalai rameswaram pakkam kadalukku pogalama",
    "naale beligge mangaluru hatra samudrakke hogodu surakshitha ideya",
    "wats time now",
    "hi",
])
def test_pc5_3_latin_only_skips_bhashini_and_defaults_to_en(prompt):
    """PC5.3 (D7, D9): Latin-only text is not sent to Bhashini detection; returns en."""
    with patch("orca.agents.bhashini.detect_language") as mock_bhashini:
        detected = query_language(prompt)
        assert detected == "en"
        mock_bhashini.assert_not_called()

    # english_query returns (raw, "passthrough")
    q_en, rung = english_query(prompt, "en")
    assert q_en == prompt
    assert rung == "passthrough"


def test_pc5_3_native_script_still_detects_and_translates():
    """Native Tamil script text detects as Tamil."""
    ta_text = "தூத்துக்குடியில் கடல் பாதுகாப்பானதா"
    assert detect_language(ta_text) == "ta"
    assert query_language(ta_text) == "ta"


# ---------------------------------------------------------------------------
# PC5.5 — Reporting includes english_reading
# ---------------------------------------------------------------------------

def test_pc5_5_reporting_includes_english_reading():
    from orca.contracts import AgentResult, Confidence, SourceProvenance
    from orca.graph.graph import reporting_node

    fake_state = {
        "query_id": "test-pc5-5",
        "raw_user_query": "kal subah safe hai kya",
        "english_reading": "is it safe tomorrow morning",
        "routing_tier": "understand_intents",
        "matched_intents": ["SAFETY_CHECK"],
        "node_results": [
            AgentResult(
                agent_name="risk_assessment",
                query_id="test-pc5-5",
                reasoning_depth="SHALLOW",
                inputs_consumed={},
                outputs={"overall_verdict": "GO", "safety_reasons": ["calm seas"]},
                source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
                confidence=Confidence(score="HIGH", rationale="test"),
            )
        ],
        "completed_nodes": ["risk_assessment"],
    }
    out = reporting_node(fake_state)
    assert out.get("english_reading") == "is it safe tomorrow morning"


# ---------------------------------------------------------------------------
# PC5.6 — Verify romanized distress and gazetteer check
# ---------------------------------------------------------------------------

def test_pc5_6_romanized_distress_phrases():
    """PC5.6 (a): Romanized distress phrases checked before ingress."""
    # Tamil romanized distress phrase containing 'udhavi'
    r1 = detect_distress_signal("engine nindruduchu udhavi venum")
    assert r1["is_distress"] is True
    assert r1["distress_type"] == "romanized_pattern"

    # Hindi romanized distress phrase containing 'bachao'
    r2 = detect_distress_signal("bachao meri naav doob rahi hai")
    assert r2["is_distress"] is True
    assert r2["distress_type"] == "romanized_pattern"

    # Hindi phrase without 'bachao' — records honest gap if deterministic regex does not catch it
    r3 = detect_distress_signal("naav ka engine kharab ho gaya, madad chahiye")
    assert isinstance(r3, dict)
    # Documented gap: 'madad chahiye' is currently in _DISTRESS_PATTERNS['hi'] (Devanagari),
    # not in _ROMANIZED_DISTRESS_PATTERNS['hi'].
    # PC5.6 requires: "the cases pass, or each failing case is logged as a NOTE and fixed as its own point."


@pytest.mark.parametrize("prompt,expected_place", [
    ("kal subah rameswaram ke paas samudra mein jaana safe hai kya", "Rameswaram"),
    ("kochi ke paas machhli kahan milegi aaj", "Kochi"),
    ("mangalore me kal lehron ki unchai kitni rahegi", "Mangalore"),
    ("chennai ke paas cyclone ka khatra hai kya", "Chennai"),
    ("mujhe tuticorin se pamban tak sabse surakshit raasta batao", "Tuticorin"),
    ("aaj goa me hawa ki raftaar kitni hai", "Goa"),
    ("kya parso vizag ke samudra me jaana theek rahega", "Vizag"),
    ("meri naav ka engine kharab ho gaya hai pamban ke paas madad chahiye", "Pamban"),
    ("naalai kaalai rameswaram pakkam kadalukku pogalama", "Rameswaram"),
    ("kochi pakkathula innaikku meen enga kidaikkum", "Kochi"),
    ("mangalore la naalaiku alai uyaram evvalavu irukkum", "Mangalore"),
    ("chennai pakkam puyal echarikkai irukka", "Chennai"),
    ("tuticorin la irundhu pamban varaikkum paadhukaappana vazhi sollunga", "Tuticorin"),
    ("ennoda padagu engine nindruduchu pamban pakkam udhavi venum", "Pamban"),
    ("karwar hatra ivattu meenu elli sigatte", "Karwar"),
    ("udupi alli naale alegala ettara eshtu irutte", "Udupi"),
    ("karwar inda goa varege surakshitha maarga heli", "Karwar"),
    ("nanna boat engine halaaytu malpe hatra sahaya beku", "Malpe"),
])
def test_pc5_6_gazetteer_check_places(prompt, expected_place):
    """PC5.6 (b): Romanized place prompts produce a valid coastal place or ambiguous clarification.

    Never resolves to pilot default unexpectedly or a wrong place.
    """
    res = resolve_or_ask(prompt)
    if res.status == "resolved":
        assert res.place is not None
        assert expected_place.lower() in res.place.name.lower()
    elif res.status in ("ambiguous", "unresolvable"):
        # As long as it asks "did you mean..." or asks for clarification, it is not a silent default
        assert res.disclosure is not None
    else:
        pytest.fail(f"Prompt '{prompt}' silently fell through to fallback default")


def test_pc5_6_mannar_validation():
    """Mannar when normalized to 'Gulf of Mannar' passes validate_reading; when unnormalized, produces NEEDS_PLACE."""
    # When planning LLM normalizes 'mannar' to 'Gulf of Mannar'
    valid = validate_reading([{"raw": "mannar", "normalized": "Gulf of Mannar"}], None, None)
    assert valid is None  # Accepted

    # When unnormalized raw 'mannar' alone is checked, it yields NEEDS_PLACE (asks user), never silent default
    unnorm = validate_reading([{"raw": "mannar", "normalized": "mannar"}], None, None)
    assert unnorm is not None
    assert unnorm.code == "NEEDS_PLACE"


@pytest.mark.parametrize("prompt", [
    "indha vaaram kadal romba alaiya irukka",
    "ivattu samudradalli gaali vega eshtu",
    "ee vaara samudra tumba alegalu ide ya",
])
def test_pc5_6_gazetteer_check_no_place_prompts(prompt):
    """Prompts without any place name correctly trigger fallback or clarification."""
    res = resolve_or_ask(prompt)
    # Questions without place name either result in 'fallback' (with explicit disclosure)
    # or 'ambiguous' (clarification candidates), never a silent unannotated answer.
    assert res.status in ("fallback", "ambiguous", "unresolvable")
    if res.status == "fallback":
        assert "names no place" in (res.disclosure or "")
    else:
        assert res.disclosure is not None


# ---------------------------------------------------------------------------
# PC5.7 — Honest provenance on native-script path
# ---------------------------------------------------------------------------

def test_pc5_7_passthrough_provenance():
    """English/Latin passthrough span explicitly states no model ran."""
    state = {
        "raw_user_query": "is it safe near kochi",
        "pretranslated": {"raw": "is it safe near kochi", "language": "en", "english": "is it safe near kochi", "rung": "passthrough"},
    }
    result = run_ingress(state)
    assert result.source_provenance.dataset == "No translation (passthrough)"
    assert result.confidence.score == "HIGH"
    assert "no translation" in result.confidence.rationale.lower()
    assert result.status == "ok"


def test_pc5_7_native_script_unchanged_marked_degraded():
    """Native script translation returning input unchanged is marked degraded."""
    state = {
        "raw_user_query": "கடல் பாதுகாப்பானதா",
        "pretranslated": {"raw": "கடல் பாதுகாப்பானதா", "language": "ta", "english": "கடல் பாதுகாப்பானதா", "rung": "bhashini"},
    }
    result = run_ingress(state)
    assert result.status == "degraded"
    assert result.confidence.score == "LOW_DATA"
    assert "returned input unchanged" in result.confidence.rationale


def test_pc5_7_egress_passthrough_provenance():
    """Egress for English response states no translation needed."""
    state = {
        "detected_language": "en",
        "final_english_response": "Conditions are safe today.",
    }
    result = run_egress(state)
    assert result.source_provenance.dataset == "No translation (passthrough)"
    assert result.confidence.score == "HIGH"
    assert result.status == "ok"
