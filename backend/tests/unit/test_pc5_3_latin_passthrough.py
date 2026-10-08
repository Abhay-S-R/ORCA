"""PC5.3 — Latin-only text skips language detection and translation.

Done-when (plan section 8): "pfzs near rameshwaram" is answered in English with no Bhashini call;
romanized Hindi reaches planning as typed; a Tamil-script question still translates through Bhashini.

Evidence behind it (plan Appendix A): Bhashini's detector labelled 12 of 20 short English prompts as
another language (kochi weather -> Malayalam, thanks -> Kashmiri), so an English question was
answered in that language; and romanized text sent to the translator came back unchanged.
"""
from __future__ import annotations

from unittest import mock

import pytest

from orca.agents import bhashini, language
from orca.agents.language import (
    detect_language,
    english_query,
    query_language,
    run_egress,
    run_ingress,
)


@pytest.fixture(autouse=True)
def _bhashini_must_not_be_called():
    """Any Bhashini call from these tests is a failure: the point of PC5.3 is that Latin text never
    reaches it. Raising makes a stray call visible instead of silently degrading."""
    def boom(*a, **k):
        raise AssertionError("Bhashini was called for text that should have passed straight through")

    with mock.patch.object(bhashini, "detect_language", boom), \
            mock.patch.object(bhashini, "nmt", boom), \
            mock.patch.object(bhashini, "transliterate", boom):
        yield


# --- the old machinery is gone ----------------------------------------------------------------------

def test_the_word_list_and_the_latin_detection_branch_are_removed():
    assert not hasattr(language, "_COMMON_ENGLISH_WORDS")
    assert not hasattr(language, "_low_english_coverage")
    assert not hasattr(language, "detect_language_with_bhashini")


# --- Latin-only text is English-by-script and untouched ------------------------------------------------

LATIN = [
    "pfzs near rameshwaram", "pfz near ktaka tmrw", "kochi weather", "fish off tn coast", "thanks", "hello", "hi",
    "tide at vizag", "wats the time", "is it safe to go to sea tomorrow near kochi", "wave hight at pamban",
    # romanized Indian languages (Appendix A)
    "kal subah rameswaram ke paas samudra mein jaana safe hai kya", "tum kaiso ho", "naalai kadalukku pogalama",
    "repu samudram ki vellochha", "nale kadalil pokamo", "udya samudrat jaaycha ka",
    "naale beligge mangaluru hatra samudrakke hogodu surakshitha ideya", "aaj machhli kahan milegi",
]


@pytest.mark.parametrize("text", LATIN)
def test_latin_text_resolves_to_english_by_script_and_calls_no_service(text):
    assert query_language(text) == "en"


@pytest.mark.parametrize("text", LATIN)
def test_latin_text_is_passed_through_exactly_as_typed(text):
    assert english_query(text, query_language(text)) == (text, "passthrough")


def test_a_user_with_a_saved_language_does_not_change_how_latin_text_is_read():
    assert query_language("pfzs near rameshwaram", user_language_default="ml") == "en"
    assert query_language("kal subah rameswaram ke paas safe hai kya", user_language_default="hi") == "en"


def test_an_empty_message_still_takes_the_users_saved_language():
    """The SOS control sends no text; that behaviour (P3.1) is unchanged."""
    assert query_language("", user_language_default="ta") == "ta"
    assert query_language("   ", user_language_default="hi") == "hi"
    assert query_language("") == "en"


# --- native script is unchanged ------------------------------------------------------------------------------

NATIVE = [
    ("நாளை காலை சென்னை அருகே கடலுக்கு செல்வது பாதுகாப்பானதா?", "ta"),
    ("क्या कल सुबह रामेश्वरम के पास समुद्र में जाना सुरक्षित है?", "hi"),
    ("നാളെ രാവിലെ കൊച്ചിക്ക് സമീപം കടലിൽ പോകുന്നത് സുരക്ഷിതമാണോ?", "ml"),
    ("ನಾಳೆ ಬೆಳಿಗ್ಗೆ ಮಂಗಳೂರು ಬಳಿ ಸಮುದ್ರಕ್ಕೆ ಹೋಗುವುದು ಸುರಕ್ಷಿತವೇ?", "kn"),
    ("రేపు ఉదయం విశాఖపట్నం దగ్గర సముద్రంలోకి వెళ్లడం సురక్షితమేనా?", "te"),
    ("আগামীকাল সকালে দীঘার কাছে সমুদ্রে যাওয়া কি নিরাপদ?", "bn"),
    ("આવતીકાલે સવારે વેરાવળ પાસે દરિયામાં જવું સલામત છે?", "gu"),
    ("ଆସନ୍ତାକାଲି ସକାଳେ ପୁରୀ ନିକଟରେ ସମୁଦ୍ରକୁ ଯିବା ସୁରକ୍ଷିତ କି?", "or"),
]


@pytest.mark.parametrize("text, code", NATIVE)
def test_native_script_is_still_detected_by_its_script(text, code):
    assert query_language(text) == code


def test_a_message_mixing_native_script_and_latin_still_follows_its_native_script():
    """Mixed text is a known gap (deferred), but its detection must not have changed."""
    assert query_language("naalai Rameswaram கடலுக்கு போகலாமா") == "ta"
    assert query_language("kal Rameswaram ke paas मछली कहाँ मिलेगी") == "hi"


def test_native_script_still_translates_through_the_translation_path():
    """The Tamil question still goes to Bhashini NMT (here a fake), not the passthrough."""
    calls = []

    def fake_nmt(text, source, target):
        calls.append((source, target))
        return "Is it safe to go to sea near Chennai tomorrow morning?"

    with mock.patch.object(bhashini, "nmt", fake_nmt):
        text, rung = english_query("நாளை காலை சென்னை அருகே கடலுக்கு செல்வது பாதுகாப்பானதா?", "ta")
    assert rung == "bhashini" and calls == [("ta", "en")] and "Chennai" in text


# --- the ingress node and the reply language -----------------------------------------------------------------------

def _ingress(text):
    return run_ingress({"query_id": "q", "raw_user_query": text})  # type: ignore[arg-type]


def test_ingress_leaves_a_romanized_question_untouched_and_marks_it_english():
    out = _ingress("kal subah rameswaram ke paas samudra mein jaana safe hai kya").outputs
    assert out["detected_language"] == "en"
    assert out["normalized_english_query"] == "kal subah rameswaram ke paas samudra mein jaana safe hai kya"


def test_ingress_reports_no_translation_engine_for_latin_text():
    result = _ingress("pfzs near rameshwaram")
    # Names what ran, which is nothing: it used to be None and the span defaulted to an IndicTrans2 label.
    assert result.engine == "No translation (passthrough)" and result.status == "ok"
    assert "already English" in result.confidence.rationale


def test_the_reply_to_latin_text_is_english_so_egress_does_not_translate_it():
    state = {"query_id": "q", "detected_language": query_language("kal subah rameswaram ke paas safe hai kya"),
             "final_english_response": "GO: All Parameters Within Safe Operational Limits."}
    out = run_egress(state).outputs  # type: ignore[arg-type]
    assert out["final_vernacular_response"] == "GO: All Parameters Within Safe Operational Limits."


def test_script_detection_itself_is_unchanged():
    assert detect_language("pfzs near rameshwaram") == "en"
    assert detect_language("நாளை") == "ta"


# --- the narrative is written in English, whatever the user typed (found live while verifying PC5.3) -----------
#
# Before PC5.3 a romanized prompt was "translated" (returned unchanged) and the narrative model mirrored it,
# which the later translation step then mangled. With the text passed through as typed the mirroring became
# visible: "naalai kaalai rameswaram ..." was answered in Tamil script (with a stray Bengali word) and
# "kal subah rameswaram ..." in romanized Hindi, against decision D11 (Latin text is answered in English).

class _Client:
    engine = "fake-model"

    def __init__(self):
        self.prompts = []

    def complete(self, messages, **kw):
        self.prompts.append(messages[0]["content"])
        return "GO: All Parameters Within Safe Operational Limits. Calm sea near Rameswaram tomorrow morning."


@pytest.mark.parametrize("query", [
    "naalai kaalai rameswaram pakkam kadalukku pogalama",
    "kal subah rameswaram ke paas samudra mein jaana safe hai kya",
    "pfzs near rameshwaram",
])
def test_the_narrative_prompt_demands_english_whatever_the_user_typed(query):
    from orca.agents.reporting import synthesize_narrative

    client = _Client()
    verdict = {"go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits", "status": "OK"}
    with mock.patch("orca.llm.tiers.llm", lambda tier: client):
        synthesize_narrative(query, verdict, [])
    prompt = client.prompts[0]
    assert query in prompt
    assert "12. Language. Write the whole answer in English" in prompt
    assert "do not transliterate" in prompt and "do not mix languages" in prompt
