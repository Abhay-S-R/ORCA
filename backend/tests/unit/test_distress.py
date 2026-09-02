"""Agent 12 tests. Real Tamil/Hindi phrases (verified against real sources
while writing the module, not transliterated from memory — see the module
docstring for the honest coverage caveat this test suite does not paper over)."""
from orca.agents.distress import (
    detect_distress_signal,
    emit_datsg_handoff,
    run,
    surface_mrcc_contact,
)
from orca.state import ORCAState

# --- detect_distress_signal ------------------------------------------------

def test_ui_sos_tap_is_always_distress_no_text_needed():
    result = detect_distress_signal("", ui_control_triggered=True)
    assert result["is_distress"] is True
    assert result["distress_type"] == "sos_control"


def test_english_sinking_detected():
    result = detect_distress_signal("our boat is sinking near Thoothukudi")
    assert result["is_distress"] is True
    assert result["matched_language"] == "en"


def test_english_case_insensitive():
    result = detect_distress_signal("MAYDAY MAYDAY")
    assert result["is_distress"] is True


def test_tamil_boat_sinking_detected():
    result = detect_distress_signal("எங்கள் படகு மூழ்குகிறது")  # "our boat is sinking"
    assert result["is_distress"] is True
    assert result["matched_language"] == "ta"


def test_hindi_boat_sinking_detected():
    result = detect_distress_signal("हमारी नाव डूब रही है")  # "our boat is sinking"
    assert result["is_distress"] is True
    assert result["matched_language"] == "hi"


def test_hindi_bachao_detected():
    result = detect_distress_signal("बचाओ बचाओ")  # "save us / help"
    assert result["is_distress"] is True
    assert result["matched_language"] == "hi"


def test_ordinary_query_is_not_distress():
    result = detect_distress_signal("Is it safe to go to sea tomorrow morning?")
    assert result["is_distress"] is False


def test_casual_use_of_help_is_a_known_false_positive_risk():
    # Documents the honest limitation named in the module docstring — a
    # substring match on "help" alone fires even for a non-emergency use.
    # This is the trade-off the architecture doc accepts explicitly (pattern
    # match over semantic inference), not a bug to silently fix here.
    result = detect_distress_signal("can you help me understand this forecast")
    assert result["is_distress"] is True
    assert result["matched_phrase"] == "help"


# --- surface_mrcc_contact ----------------------------------------------------

def test_mrcc_contact_always_includes_nationwide_number():
    result = surface_mrcc_contact({"lat": 8.80, "lon": 78.14})
    assert result["nationwide_fallback"]["phone"] == "1554"


def test_mrcc_contact_includes_vhf_channel_16():
    result = surface_mrcc_contact(None)
    assert result["primary"]["vhf_channel"] == "16"


def test_mrcc_contact_works_with_no_location_at_all():
    # Architecture §3.2: must never fail just because location is unknown
    result = surface_mrcc_contact(None)
    assert result["nationwide_fallback"]["phone"] == "1554"


# --- emit_datsg_handoff -------------------------------------------------------

def test_handoff_is_labelled_simulated_never_claims_real_delivery():
    result = emit_datsg_handoff({"lat": 8.80, "lon": 78.14}, "boat-123", "sos_control", "2026-09-02T10:00:00Z")
    assert result["status"] == "SIMULATED"
    assert result["format"] == "CAP-fallback"


def test_handoff_works_with_unknown_vessel_id():
    result = emit_datsg_handoff({"lat": 8.80, "lon": 78.14}, None, "text_pattern", "2026-09-02T10:00:00Z")
    assert result["vessel_id"] is None
    assert result["status"] == "SIMULATED"


# --- run() -------------------------------------------------------------------

def test_run_checks_both_raw_and_normalized_query_text():
    # Distress phrase only in the ORIGINAL vernacular field — must still fire
    # even if normalized_english_query already exists and doesn't contain it
    # (e.g. an imperfect translation that dropped the urgency).
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-1", "reasoning_depth": "SHALLOW",
        "raw_user_query": "படகு மூழ்குகிறது",
        "normalized_english_query": "what is the weather like",  # imagine a bad translation
        "distress_flag": False,
    }
    result = run(state)
    assert result.outputs["detection"]["is_distress"] is True
    assert result.outputs["detection"]["matched_language"] == "ta"


def test_run_sos_control_gives_high_confidence():
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-2", "reasoning_depth": "SHALLOW",
        "raw_user_query": "", "normalized_english_query": "", "distress_flag": True,
    }
    result = run(state)
    assert result.confidence.score == "HIGH"
    assert result.outputs["detection"]["distress_type"] == "sos_control"


def test_run_never_high_confidence_off_the_text_pattern_list():
    # Even a real, confirmed match stays MEDIUM — the honest reflection of
    # an unreviewed phrase list, in both directions.
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-3", "reasoning_depth": "SHALLOW",
        "raw_user_query": "mayday mayday", "normalized_english_query": "", "distress_flag": False,
    }
    result = run(state)
    assert result.confidence.score == "MEDIUM"


def test_run_no_distress_still_returns_mrcc_and_handoff_structure():
    # Agent 12 runs on every query (checked before any other node executes,
    # per Architecture §3.2) — a non-distress result must still be a valid,
    # complete AgentResult, not a partial one.
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-4", "reasoning_depth": "SHALLOW",
        "raw_user_query": "is it safe tomorrow", "normalized_english_query": "is it safe tomorrow",
        "distress_flag": False,
    }
    result = run(state)
    assert result.outputs["detection"]["is_distress"] is False
    assert "mrcc_contact" in result.outputs
    assert not hasattr(result, "persona")
