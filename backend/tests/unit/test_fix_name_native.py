"""FIX-NAME-1 — the product name is written correctly in every language.

Bhashini translates a name by its sound, and a model writing a reply in Kannada does the same: the
Kannada answer said "ಸಾಗರ್ ಸಾರಥಿ", "ಸಾಗರ ಸರಥಿ", "ಸಾರथि" (with a Devanagari letter) and, in Bengali,
"স্যারথি". The user's spelling is "ಸಾಗರ ಸಾರಥಿ" (and Devanagari "सागर सारथी"). Code owns the name: it
is hidden from the translator and put back, and a model's spelling by ear is corrected, in each of the
nine languages, not only Kannada.
"""
from __future__ import annotations

from unittest import mock

import pytest

from orca.agents import bhashini
from orca.agents.language import (
    PRODUCT_NAME_NATIVE,
    _mask_protected_terms,
    _skeleton,
    _translate_with_rung,
    localize_product_name,
    run_egress,
)

LANGS = ["hi", "mr", "kn", "ta", "te", "ml", "bn", "gu", "or"]
KANNADA = "ಸಾಗರ ಸಾರಥಿ"
DEVANAGARI = "सागर सारथी"


def test_every_supported_language_but_english_has_a_spelling():
    assert sorted(PRODUCT_NAME_NATIVE) == sorted(LANGS)
    assert all(len(v.split()) == 2 for v in PRODUCT_NAME_NATIVE.values())


def test_the_spellings_the_user_gave_are_exactly_these():
    assert PRODUCT_NAME_NATIVE["kn"] == KANNADA
    assert PRODUCT_NAME_NATIVE["hi"] == PRODUCT_NAME_NATIVE["mr"] == DEVANAGARI


def test_english_is_never_changed():
    assert localize_product_name("I am Sagar Sarathi.", "en") == "I am Sagar Sarathi."


# --- the Latin name is converted, in every language ----------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("latin", ["Sagar Sarathi", "sagar sarathi", "SAGAR SARATHI", "Saagar  Saarathi", "Sagar Sarati"])
def test_the_latin_name_inside_a_native_sentence_becomes_the_native_spelling(lang, latin):
    out = localize_product_name(f"x {latin}, y", lang)
    assert out == f"x {PRODUCT_NAME_NATIVE[lang]}, y"


# --- a model's spelling by ear is corrected, in every language ------------------------------------------------

def _by_ear_variants(native: str) -> list[str]:
    """What a model writes by sound: no vowel signs at all, a final virama on the first word, a lone
    consonant of the wrong kind left out of the second word's sign."""
    first, second = native.split()
    virama = _virama(native)
    return [
        " ".join("".join(c for c in w if not _is_sign(c)) for w in (first, second)),  # no vowel signs
        first + virama + " " + second,  # a final virama on the first word
        "".join(c for c in first if not _is_sign(c)) + " " + second,  # only the first word bare
    ]


def _is_sign(c: str) -> bool:
    import unicodedata

    return unicodedata.category(c) in ("Mn", "Mc")


def _virama(native: str) -> str:
    import unicodedata

    for c in native:
        if "VIRAMA" in unicodedata.name(c, ""):
            return c
    # a script whose name has no virama in it: borrow the one of the same script block
    return {"hi": "्", "mr": "्", "kn": "್", "ta": "்", "te": "్", "ml": "്",
            "bn": "্", "gu": "્", "or": "୍"}[next(k for k, v in PRODUCT_NAME_NATIVE.items() if v == native)]


@pytest.mark.parametrize("lang", LANGS)
def test_a_spelling_by_ear_is_corrected(lang):
    native = PRODUCT_NAME_NATIVE[lang]
    for variant in _by_ear_variants(native):
        assert localize_product_name(f"a {variant}. b", lang) == f"a {native}. b", variant


@pytest.mark.parametrize(
    ("lang", "wrong"),
    [
        ("kn", "ನಾನು ಸಾಗರ್ ಸಾರಥಿ, ಹಾಯ್"),       # the translator's: a final virama
        ("kn", "ಸಾಗರ ಸರಥಿ"),                   # the user's report: short "ra"
        ("kn", "ಸಾಗರ ಸಾರथि"),          # a Devanagari letter inside Kannada
        ("bn", "আমি সাগর স্যারথি"),             # Bengali's ya-phala
        ("ta", "நான் ஸாகர் சாரதி"),              # Tamil's grantha sa
    ],
)
def test_real_misspellings_seen_in_answers(lang, wrong):
    assert PRODUCT_NAME_NATIVE[lang] in localize_product_name(wrong, lang)


def test_punctuation_around_the_name_is_kept():
    assert localize_product_name("(ಸಾಗರ್ ಸಾರಥಿ).", "kn") == f"({KANNADA})."
    assert localize_product_name("“ಸಾಗರ ಸರಥಿ”,", "kn") == f"“{KANNADA}”,"


def test_two_words_that_only_resemble_the_name_are_left_alone():
    assert localize_product_name("ಸಾಗರ ಸಾಗತಿ ಎಂದು", "kn") == "ಸಾಗರ ಸಾಗತಿ ಎಂದು"  # sa-ga-ra, sa-ga-ti: not the name
    assert localize_product_name("ಸಾಗರ ತೀರ", "kn") == "ಸಾಗರ ತೀರ"  # "sea shore": the first word alone is not the name


def test_an_unrelated_word_pair_in_every_language_is_untouched():
    for lang in LANGS:
        text = "ಸಮುದ್ರ ಅಲೆ ಗಾಳಿ" if lang == "kn" else PRODUCT_NAME_NATIVE[lang].split()[0] + " x"
        assert localize_product_name(text, lang) == text


def test_the_skeleton_is_script_free():
    assert _skeleton("ಸಾಗರ್") == _skeleton("सागर") == _skeleton("ସାଗର") == ("SA", "GA", "RA")
    assert _skeleton("சாகர") == ("SA", "GA", "RA")  # Tamil writes sa as ca and ga as ka


# --- translation: the name is NOT hidden (FIX-NAME-2); the spelling is corrected after -------------------------
#
# FIX-NAME-1 hid the name behind a placeholder. In Marathi and Bengali the translator transliterated the
# placeholder into gibberish ("आমি জেডকেইপিজেড0জেড") and the shown answer lost the name. The translator now
# sees the name and writes it by ear; the correction after translation fixes any spelling.

@pytest.mark.parametrize("lang", LANGS)
def test_the_translator_is_shown_the_name_and_whatever_it_writes_is_corrected(lang):
    seen = []

    def nmt(text, source, target):
        seen.append(text)
        return f"[{target}] " + text  # a translator that leaves the name in Latin

    with mock.patch.object(bhashini, "nmt", nmt):
        out, rung = _translate_with_rung("Hello, I am Sagar Sarathi.", "en", lang)  # type: ignore[arg-type]
    assert rung == "bhashini" and PRODUCT_NAME_NATIVE[lang] in out and "Sagar" not in out
    assert "Sagar Sarathi" in seen[0] and "ZKEEPZ" not in seen[0]


@pytest.mark.parametrize("lang", LANGS)
def test_a_translator_that_spells_the_name_by_ear_is_corrected(lang):
    wrong = " ".join("".join(c for c in w if not _is_sign(c)) for w in PRODUCT_NAME_NATIVE[lang].split())
    with mock.patch.object(bhashini, "nmt", lambda text, source, target: f"x {wrong} y"):
        out, _ = _translate_with_rung("I am Sagar Sarathi", "en", lang)  # type: ignore[arg-type]
    assert out == f"x {PRODUCT_NAME_NATIVE[lang]} y"


@pytest.mark.parametrize("lang", LANGS)
def test_a_translator_that_mangles_nothing_but_the_numbers_cannot_take_the_name_with_it(lang):
    # The Marathi/Bengali failure: the answer's numbers go through the placeholder, the name does not.
    seen = []

    def nmt(text, source, target):
        seen.append(text)
        return text.replace("I am", "x")

    with mock.patch.object(bhashini, "nmt", nmt):
        out, _ = _translate_with_rung("I am Sagar Sarathi, wave 1.5 m.", "en", lang)  # type: ignore[arg-type]
    assert PRODUCT_NAME_NATIVE[lang] in out and "ZKEEPZ" not in out
    assert "ZKEEPZ" not in seen[0].split(",")[0]  # the name part of the sentence carries no placeholder


def test_the_name_is_never_masked():
    masked, tokens = _mask_protected_terms("Sagar Sarathi")
    assert masked == "Sagar Sarathi" and tokens == []


def test_the_egress_answer_carries_the_exact_kannada_spelling():
    with mock.patch.object(bhashini, "nmt", lambda text, source, target: text.replace("I am", "ನಾನು")):
        out = run_egress({"query_id": "q", "detected_language": "kn", "final_english_response": "I am Sagar Sarathi."})  # type: ignore[arg-type]
    assert out.outputs["final_vernacular_response"] == f"ನಾನು {KANNADA}."


# --- chat replies are written by a model in the user's language: the graph corrects them -------------------------

@pytest.fixture(autouse=True)
def _model_off(monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")


@pytest.mark.parametrize("lang", LANGS)
def test_a_chat_reply_in_any_language_gets_the_right_spelling(lang):
    from orca.graph import graph

    wrong = " ".join("".join(c for c in w if not _is_sign(c)) for w in PRODUCT_NAME_NATIVE[lang].split())
    out = graph._in_name_spelling({"detected_language": lang}, f"{wrong} p {wrong} q")  # type: ignore[typeddict-item]
    assert out == f"{PRODUCT_NAME_NATIVE[lang]} p {PRODUCT_NAME_NATIVE[lang]} q"
    # the reply's own script decides, not the state: the model answered in this language although the
    # question was English and no reply language was recorded ("answer in kannada: ...")
    other = graph._in_name_spelling({"detected_language": "en"}, f"{wrong} x {wrong} y")  # type: ignore[typeddict-item]
    assert other == f"{PRODUCT_NAME_NATIVE[lang]} x {PRODUCT_NAME_NATIVE[lang]} y"
    # a native-script reply that spells the name in Latin letters (as the prompt asks) is converted too
    latin = graph._in_name_spelling({}, f"{wrong} z Sagar Sarathi")  # type: ignore[typeddict-item]
    assert latin.endswith(PRODUCT_NAME_NATIVE[lang])


def test_an_english_reply_is_left_alone_even_when_the_question_was_not_english():
    from orca.graph import graph

    english = "Hello! I'm Sagar Sarathi. I help with sea conditions."  # the no-model fallback sentence
    assert graph._in_name_spelling({"detected_language": "hi"}, english) == english  # type: ignore[typeddict-item]
    assert graph._in_name_spelling({"reply_language": "kn"}, english) == english  # type: ignore[typeddict-item]


def test_who_are_you_is_an_identity_question_not_a_sea_question():
    import inspect

    from orca.agents import understand

    source = inspect.getsource(understand)
    assert "who are you" in source and "what is your name" in source
    assert "A question about the assistant itself is never a sea question." in source


def test_the_answer_writer_knows_its_name_and_may_not_invent_another():
    import inspect

    from orca.agents import reporting

    assert "You are Sagar Sarathi, a marine safety advisor" in inspect.getsource(reporting)
    assert "never give or invent another one" in inspect.getsource(reporting)


def test_the_guard_reply_path_applies_it_for_every_reply_writer():
    import inspect

    from orca.graph import graph

    source = inspect.getsource(graph)
    assert source.count("_in_name_spelling(state, reply)") == 4  # guard, self-context, inland/chat, capability


def test_the_reply_prompts_tell_the_model_to_write_the_name_in_latin():
    import inspect

    from orca.agents import reporting

    assert inspect.getsource(reporting).count("write it in Latin letters exactly as Sagar Sarathi") == 3
