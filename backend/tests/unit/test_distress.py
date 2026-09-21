"""Agent 12 tests. Real Tamil/Hindi phrases (verified against real sources
while writing the module, not transliterated from memory — see the module
docstring for the honest coverage caveat this test suite does not paper over)."""
from orca.agents import distress
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


def test_malayalam_boat_sinking_detected():
    result = detect_distress_signal("ഞങ്ങളുടെ വള്ളം മുങ്ങുന്നു")  # "our boat is sinking"
    assert result["is_distress"] is True
    assert result["matched_language"] == "ml"


def test_malayalam_save_me_detected():
    result = detect_distress_signal("എന്നെ രക്ഷിക്കൂ")  # "save me"
    assert result["is_distress"] is True
    assert result["matched_language"] == "ml"


def test_telugu_boat_sinking_detected():
    result = detect_distress_signal("మా పడవ మునిగిపోతోంది")  # "our boat is sinking"
    assert result["is_distress"] is True
    assert result["matched_language"] == "te"


def test_telugu_save_me_detected():
    result = detect_distress_signal("నన్ను రక్షించండి")  # "save me"
    assert result["is_distress"] is True
    assert result["matched_language"] == "te"


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


# --- MRCC routing now reads the ICG station roster (runbook C4) ----------

def test_mrcc_contact_routes_to_the_nearest_station_not_always_chennai():
    """The roster is gitignored data, so an empty one is legitimate — what
    must never happen is a Gujarat position handed the Tamil Nadu centre."""
    gujarat = distress.surface_mrcc_contact({"lat": 23.1, "lon": 68.5})
    andaman = distress.surface_mrcc_contact({"latitude": 11.6, "longitude": 92.7})
    if gujarat["nearest_station"] is None:
        assert andaman["nearest_station"] is None  # roster absent, not a routing bug
        return
    assert gujarat["nearest_station"]["coordinating_mrcc"] == "MRCC Mumbai"
    assert andaman["nearest_station"]["coordinating_mrcc"] == "MRCC Sri Vijaya Puram"
    assert gujarat["nearest_station"]["straight_line_distance_km"] < 200


def test_every_surfaced_number_is_one_of_the_verified_ones():
    """P1.7. No station-level phone number is published, so none may be
    invented — a distress reply that offers an unreachable number is worse
    than one that offers only 1554. What IS published is the three MRCCs, and
    those are the only numbers this may ever surface."""
    verified = {c["phone"] for c in distress.MRCC_CONTACTS.values()}
    reply = distress.surface_mrcc_contact({"lat": 23.1, "lon": 68.5})
    assert reply["primary"]["phone"] in verified
    assert reply["nationwide_fallback"]["phone"] == "1554"
    assert reply["vhf_channel"] == "16"
    if reply["nearest_station"] is not None:
        assert reply["nearest_station"]["phone"] is None


def test_the_number_surfaced_is_the_coordinating_mrccs_own():
    """P1.7's whole point: a boat off Gujarat used to be handed MRCC Chennai's
    queue (or a generic one). Its case is run from Mumbai, so Mumbai's number
    is the one to dial, with 1554 still on the card behind it."""
    gujarat = distress.surface_mrcc_contact({"lat": 20.9, "lon": 70.37})
    if gujarat["nearest_station"] is None:
        return  # roster absent in this environment — covered by the test above
    assert gujarat["primary"] == distress.MRCC_CONTACTS["MRCC Mumbai"]
    assert "1554" in gujarat["note"]

    andaman = distress.surface_mrcc_contact({"lat": 11.67, "lon": 92.75})
    assert andaman["primary"] == distress.MRCC_CONTACTS["MRCC Sri Vijaya Puram"]


def test_the_nabhmitra_line_says_it_is_not_a_live_alert_and_fits_one_message():
    """P1.7 / orca_final §13.2 — a renderer, no transport. The simulated
    marker is inside the body, so copying the line out of ORCA cannot strip
    it into something that reads like a real distress alert."""
    handoff = distress.emit_datsg_handoff(
        {"lat": 20.9, "lon": 70.37}, "IND-GJ-1234", "text_pattern", "2026-09-20T10:00:00Z"
    )
    line = distress.render_nabhmitra_text(handoff)
    assert "SIM" in line and line.isascii()
    assert "20.9000N" in line and "70.3700E" in line
    assert len(line) <= distress.NABHMITRA_MAX_CHARS

    no_fix = distress.render_nabhmitra_text(distress.emit_datsg_handoff(None, None, None, "2026-09-20T10:00:00Z"))
    assert "POS UNKNOWN" in no_fix and "SIM" in no_fix


def test_missing_position_still_yields_a_dialable_number():
    reply = distress.surface_mrcc_contact(None)
    assert reply["primary"]["phone"] == "1554"
    assert reply["nearest_station"] is None


# P1.10 (orca_final §13.1, PS-Q8) — five injury phrasings per core language.
# Before this, every one of these matched no routing row and came back with a
# weather answer.
_INJURY_PHRASINGS: dict[str, list[str]] = {
    "en": [
        "my crewmate is injured, what do I do",
        "he is bleeding badly on the boat",
        "one of the crew is unconscious",
        "chest pain, we need a doctor out here",
        "his leg is broken, broken leg, we are 20 km out",
    ],
    "ta": [
        "நண்பருக்கு காயம் பட்டது என்ன செய்வது",
        "காயம் பட்டார் மிகவும் மோசம்",
        "ரத்தம் வருகிறது நிற்கவில்லை",
        "மயக்கம் அடைந்துவிட்டார்",
        "நெஞ்சு வலி மிகவும் அதிகம்",
    ],
    "hi": [
        "मेरा साथी घायल है",
        "खून बह रहा है बहुत",
        "वह बेहोश हो गया है",
        "लगता है दिल का दौरा पड़ा है",
        "उसे डॉक्टर चाहिए तुरंत",
    ],
    "ml": [
        "കൂടെയുള്ളയാൾക്ക് പരിക്ക് പറ്റി",
        "പരിക്കേറ്റു ഉടനെ സഹായം വേണം",
        "രക്തം വരുന്നു നിൽക്കുന്നില്ല",
        "അവന് ബോധം കെട്ടു",
        "ഡോക്ടറെ വേണം ഇപ്പോൾ",
    ],
    "te": [
        "మా వాడికి గాయం అయ్యింది",
        "గాయపడ్డాడు సహాయం కావాలి",
        "రక్తం కారుతోంది ఆగడం లేదు",
        "స్పృహ తప్పింది ఇప్పుడే",
        "గుండెపోటు వచ్చినట్టు ఉంది",
    ],
}


def test_five_injury_phrasings_per_core_language_reach_the_distress_path():
    """Reaching the path is the requirement. A phrasing that also contains a
    plain distress word ("help", "உதவி", "సహాయం") is reported as
    `text_pattern` rather than `medical_pattern`, which is the intended
    precedence — a sinking is still a sinking — and is equally a pass here."""
    for lang, phrasings in _INJURY_PHRASINGS.items():
        assert len(phrasings) >= 5, lang
        for text in phrasings:
            detection = distress.detect_distress_signal(text)
            assert detection["is_distress"] is True, (lang, text)
            assert detection["distress_type"] in ("medical_pattern", "text_pattern"), (lang, text)


def test_every_medical_phrase_in_every_language_fires_on_its_own():
    """The list itself, phrase by phrase — so a language whose entries are all
    shadowed by a distress word above cannot pass the test above while
    contributing nothing of its own."""
    for lang, phrases in distress._MEDICAL_PATTERNS.items():
        for phrase in phrases:
            detection = distress.detect_distress_signal(phrase)
            assert detection["distress_type"] == "medical_pattern", (lang, phrase)


def test_an_injury_query_gets_the_mrcc_short_circuit_not_a_weather_answer():
    """The routing half of P1.10 — detection alone is not the point, reaching
    the MRCC contact is."""
    state = {
        "query_id": "q-injury",
        "raw_user_query": "my crewmate is injured, what do I do",
        "normalized_english_query": "my crewmate is injured, what do I do",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 20.9, "lon": 70.37, "place_source": "gazetteer"},
        "distress_flag": False,
    }
    result = distress.run(state)  # type: ignore[arg-type]
    assert result.outputs["detection"]["is_distress"] is True
    assert result.outputs["mrcc_contact"]["nationwide_fallback"]["phone"] == "1554"


def test_a_word_that_merely_contains_a_medical_phrase_is_not_distress():
    """P1.10's own acceptance criterion: "injury" inside a non-distress word
    must not fire. `_MEDICAL_PATTERNS` are ordinary words that occur inside
    ordinary sentences, so unlike `_DISTRESS_PATTERNS` they are matched on
    word boundaries."""
    for text in [
        "the uninjured fish were returned to the sea",
        "is it safe to go to sea tomorrow morning",
        "what is the wave height near Veraval",
    ]:
        assert distress.detect_distress_signal(text)["is_distress"] is False, text


def test_a_text_detected_distress_call_is_labelled_DISTRESS_on_the_wire():
    """`query_outcome` is seeded from the `distress=` query parameter (the SOS
    button). A distress call detected from the TEXT alone must set it too, or
    the field a client branches on reads "ANSWERED" while the body reads
    "DISTRESS DETECTED" — the one outcome that must never be mislabelled."""
    from orca.graph.graph import distress_check_node

    state = {
        "query_id": "q-wire",
        "raw_user_query": "our boat is sinking help",
        "normalized_english_query": "our boat is sinking help",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 9.28, "lon": 79.2, "place_source": "gazetteer"},
        "distress_flag": False,
    }
    update = distress_check_node(state)  # type: ignore[arg-type]
    assert update["distress_flag"] is True
    assert update["query_outcome"] == "DISTRESS"

    calm = {**state, "raw_user_query": "is it safe tomorrow", "normalized_english_query": "is it safe tomorrow"}
    assert "query_outcome" not in distress_check_node(calm)  # type: ignore[arg-type]
