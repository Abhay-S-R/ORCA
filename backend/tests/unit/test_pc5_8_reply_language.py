"""PC5.8 — an explicit "answer in <language>" request is honoured.

Rule (user, 2026-10-07): when the user explicitly asks for a language the response is in it;
otherwise English is the default for Latin text and the script's language for native-script
text (unchanged). Found by tracing "answer this in kannda: pfzs near mangalore": ingress set
the language from the script alone ("en"), planning noticed the request but had nowhere to
put it, egress translated to "en".
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca.agents import bhashini, planning
from orca.agents.language import _ALL_LANGUAGES, run_egress
from orca.agents.understand import (
    _REPLY_LANGUAGES,
    _build_understand_prompt,
    _clean_reply_language,
    _fallback_understand,
    _parse_understand_output,
)
from orca.graph.graph import planning_node


@pytest.fixture(autouse=True)
def _model_off(monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")


class _Client:
    engine = "fake-model"

    def __init__(self, text):
        self.text = text

    def complete(self, messages, **kw):
        return self.text


def _reading(reply_language="<absent>", **over):
    body = {"kind": "sea_question", "intents": ["PFZ_NEAREST"], "places": [{"raw": "mangalore", "normalized": "Mangalore"}],
            "when": None, "is_followup": False, "agents": [], "english_reading": "Answer in Kannada: PFZs near Mangalore."}
    if reply_language != "<absent>":
        body["reply_language"] = reply_language
    body.update(over)
    return json.dumps(body)


def _plan(model_text, query="answer this in kannda: pfzs near mangalore"):
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(model_text)), \
            mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return planning.run({"query_id": "q", "raw_user_query": query, "session_history": []})  # type: ignore[arg-type]


# --- validation: the model proposes, code decides ------------------------------------------------

def test_the_reply_languages_are_exactly_the_ones_egress_can_translate_to():
    assert set(_REPLY_LANGUAGES) == set(_ALL_LANGUAGES)


@pytest.mark.parametrize("code", ["ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en"])
def test_every_supported_code_is_kept(code):
    assert _clean_reply_language(code) == code
    assert _clean_reply_language(f"  {code.upper()} ") == code


@pytest.mark.parametrize("value", [None, "", "  ", "kannada", "Kannada", "xx", "fr", "kn-IN", "kan", 7, ["kn"], {"a": 1}, True])
def test_anything_that_is_not_exactly_a_supported_code_is_no_request(value):
    assert _clean_reply_language(value) is None


def test_the_parser_carries_it_and_defaults_to_none():
    assert _parse_understand_output(_reading("kn")).reply_language == "kn"       # type: ignore[union-attr]
    assert _parse_understand_output(_reading()).reply_language is None            # type: ignore[union-attr]
    assert _parse_understand_output(_reading("klingon")).reply_language is None   # type: ignore[union-attr]
    assert _parse_understand_output(_reading(None)).reply_language is None        # type: ignore[union-attr]


def test_the_offline_fallback_never_requests_a_language():
    assert _fallback_understand("answer in kannada pfzs near mangalore", None).reply_language is None


# --- the prompt ------------------------------------------------------------------------------------------

def test_the_prompt_defines_the_field_and_says_script_is_not_a_request():
    prompt = _build_understand_prompt("x", None, None, "2026-10-07T10:00")
    assert '"reply_language"' in prompt and "17. REPLY LANGUAGE" in prompt
    assert "ONLY when the user explicitly asks" in prompt and "is NOT a request for a reply in it" in prompt
    assert "kannda" in prompt   # misspellings are named as in scope


# --- planning and the graph node -----------------------------------------------------------------------------

def test_planning_outputs_the_requested_language_and_still_reads_the_sea_question():
    out = _plan(_reading("kn")).outputs
    assert out["reply_language"] == "kn"
    assert out["kind"] == "sea_question" and out["matched_intent_rows"] == ["PFZ_NEAREST"]
    assert [p["normalized"] for p in out["places"]] == ["Mangalore"]


def test_planning_outputs_none_when_no_language_was_requested():
    assert _plan(_reading(None), query="pfzs near mangalore").outputs["reply_language"] is None


def test_a_garbled_request_cannot_send_the_reply_somewhere_unsupported():
    assert _plan(_reading("klingon")).outputs["reply_language"] is None


def test_planning_with_no_model_requests_nothing():
    out = planning.run({"query_id": "q", "raw_user_query": "answer in kannada: pfzs near mangalore", "session_history": []}).outputs  # type: ignore[arg-type]
    assert out["reply_language"] is None


def test_the_graph_node_stores_it_in_state():
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(_reading("ta"))), \
            mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        update = planning_node({"query_id": "q", "raw_user_query": "tamil mein batao: pfzs near chennai", "session_history": []})  # type: ignore[arg-type]
    assert update["reply_language"] == "ta"


def test_an_injected_state_carries_it_through():
    out = planning.run({"query_id": "q", "raw_user_query": "x", "understood_kind": "sea_question", "understood_intents": ["PFZ_NEAREST"],
                        "understood_places": [], "understood_when": None, "reply_language": "hi"}).outputs  # type: ignore[arg-type]
    assert out["reply_language"] == "hi"


@pytest.mark.parametrize("requested", [None, "kn", "en"])
def test_the_request_changes_nothing_but_the_language(requested):
    base = _plan(_reading(None)).outputs
    out = _plan(_reading(requested)).outputs
    for field in ("kind", "matched_intent_rows", "execution_plan", "places", "when", "query_outcome", "agents"):
        assert out[field] == base[field], field


# --- egress: the request wins, otherwise the old behaviour -------------------------------------------------------

def _egress(**state):
    base = {"query_id": "q", "final_english_response": "The nearest PFZ is about 16 km NNW of Mangalore."}
    base.update(state)
    return run_egress(base)  # type: ignore[arg-type]


def _fake_nmt(calls):
    def nmt(text, source, target):
        calls.append((source, target))
        return f"[{target}] {text}"
    return nmt


def test_an_explicit_request_translates_a_latin_question_s_answer():
    calls = []
    with mock.patch.object(bhashini, "nmt", _fake_nmt(calls)):
        out = _egress(detected_language="en", reply_language="kn").outputs
    assert calls and all(c == ("en", "kn") for c in calls)
    assert out["final_vernacular_response"].startswith("[kn]")


def test_no_request_keeps_latin_text_in_english_and_calls_no_service():
    with mock.patch.object(bhashini, "nmt", side_effect=AssertionError("must not translate")):
        out = _egress(detected_language="en", reply_language=None).outputs
    assert out["final_vernacular_response"] == "The nearest PFZ is about 16 km NNW of Mangalore."


def test_no_request_keeps_native_script_in_its_own_language():
    calls = []
    with mock.patch.object(bhashini, "nmt", _fake_nmt(calls)):
        out = _egress(detected_language="ta", reply_language=None).outputs
    assert calls and all(c == ("en", "ta") for c in calls) and out["final_vernacular_response"].startswith("[ta]")


def test_a_request_overrides_the_script_s_language():
    calls = []
    with mock.patch.object(bhashini, "nmt", _fake_nmt(calls)):
        _egress(detected_language="ta", reply_language="hi")
    assert calls and all(c == ("en", "hi") for c in calls)


def test_asking_for_english_overrides_a_native_script_question():
    with mock.patch.object(bhashini, "nmt", side_effect=AssertionError("must not translate")):
        out = _egress(detected_language="ta", reply_language="en").outputs
    assert out["final_vernacular_response"] == "The nearest PFZ is about 16 km NNW of Mangalore."


def test_an_unsupported_value_in_state_falls_back_instead_of_raising():
    with mock.patch.object(bhashini, "nmt", side_effect=AssertionError("must not translate")):
        out = _egress(detected_language="en", reply_language="xx").outputs
    assert out["final_vernacular_response"].startswith("The nearest PFZ")


# --- the response payload ------------------------------------------------------------------------------------------------

def test_the_payload_reports_the_language_the_answer_is_in():
    import inspect

    from orca.api import main

    source = inspect.getsource(main)
    assert 'final_state.get("reply_language") or final_state.get("detected_language", "en")' in source


# --- the narrative must be English, even when the user asks for another language -------------------------------------
#
# Found live: with "Say in Kannada: pfzs near Mangalore" the narrative model wrote Kannada into the
# English field; egress then translated Kannada "from English" into garbage ("I can only answer in
# English ...").

from orca.agents.reporting import is_english_text, synthesize_narrative


@pytest.mark.parametrize("text", [
    "The nearest PFZ is about 16 km NNW of Mangalore.",
    "GO: All Parameters Within Safe Operational Limits. Calm sea near Rameswaram (ರಾಮೇಶ್ವರಂ).",
    "kal subah rameswaram ke paas samudra mein jaana safe hai kya",
    "16 km, 0.6 m, 5 days.",
    "",
])
def test_english_romanised_and_mixed_with_a_name_pass(text):
    assert is_english_text(text)


@pytest.mark.parametrize("text", [
    "ಮಂಗಳೂರಿನ ವಾಯುವ್ಯಕ್ಕೆ ಸುಮಾರು 16 ಕಿಲೋಮೀಟರ್ ದೂರದಲ್ಲಿ ಮೀನುಗಾರಿಕಾ ವಲಯವಿದೆ (PFZ).",
    "சென்னைக்கு கிழக்கே 23 km தொலைவில் மீன்பிடி மண்டலம் உள்ளது.",
    "कोच्चि के पास मछली पकड़ने का क्षेत्र लगभग 15 km है।",
])
def test_a_narrative_in_another_script_is_not_english(text):
    assert not is_english_text(text)


def test_a_narrative_the_model_wrote_in_kannada_is_replaced_by_the_english_facts():
    kannada = "ಮಂಗಳೂರಿನ ವಾಯುವ್ಯಕ್ಕೆ ಸುಮಾರು 16 ಕಿಲೋಮೀಟರ್ ದೂರದಲ್ಲಿ ಮೀನುಗಾರಿಕಾ ವಲಯವಿದೆ. ಸುರತ್ಕಲ್ ಪಾಯಿಂಟ್ ಬಳಿ ಇದೆ."
    verdict = {"go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits", "status": "OK"}
    engine = []
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(kannada)):
        out = synthesize_narrative("Say in Kannada: pfzs near Mangalore", verdict, [], lead_with_verdict=False, engine_out=engine)
    assert is_english_text(out) and out.strip()
    assert engine and engine[0].startswith("Deterministic") and "not in English" in engine[0]


def test_an_english_narrative_is_kept_untouched():
    verdict = {"go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits", "status": "OK"}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client("The nearest zone is about 16 km NNW of Mangalore.")):
        out = synthesize_narrative("Say in Kannada: pfzs near Mangalore", verdict, [], lead_with_verdict=False)
    assert out == "The nearest zone is about 16 km NNW of Mangalore."


def test_the_prompt_tells_the_model_to_leave_a_language_request_to_the_translation_step():
    seen = []

    class _Spy(_Client):
        def complete(self, messages, **kw):
            seen.append(messages[0]["content"])
            return "The nearest zone is about 16 km NNW of Mangalore."

    verdict = {"go_no_go": "GO", "reason": "ok", "status": "OK"}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Spy("")):
        synthesize_narrative("Say in Kannada: pfzs near Mangalore", verdict, [], lead_with_verdict=False)
    assert "do NOT mention the language request or apologise for it" in seen[0] and "translation step that runs after you" in seen[0]
    assert "NOT part of the question and NOT a text to translate" in seen[0]
    assert "Never translate, quote or repeat the question as your answer" in seen[0]


def test_the_narrative_sees_the_question_not_the_language_request():
    import inspect

    from orca.graph import graph

    source = inspect.getsource(graph)
    assert 'if state.get("reply_language") and reading:' in source and "query_text = reading" in source
    assert "WITHOUT any instruction about the reply language" in inspect.getsource(__import__("orca.agents.understand", fromlist=["x"]))
