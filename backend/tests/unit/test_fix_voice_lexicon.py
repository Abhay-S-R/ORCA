"""FIX-VOICE-2 step 2 — numbers, units and dates inside a native-language answer.

The user heard a Kannada answer read "30-35 m" as "30 35": the translator leaves numbers and units in
Latin (language._PROTECTED_TERM), and the native voices then drop the word between the two numbers of
a range, spell a lone "m" as two letters ("ಇ ಎಂ") and drop a Latin month ("2 Oct 2026"). The same
rewriting as for English, in each language's own words (orca/agents/speech_lexicon.py).
"""
from __future__ import annotations

import re

import pytest

from orca.agents.speech_lexicon import LEXICON, MONTH_ALIASES
from orca.agents.voice import speakable

LANGS = ["kn", "hi", "mr", "ta", "te", "ml", "bn", "gu", "or"]


# --- the lexicon is complete ----------------------------------------------------------------------------------

def test_every_language_but_english_has_a_lexicon():
    assert sorted(LEXICON) == sorted(LANGS)


@pytest.mark.parametrize("lang", LANGS)
def test_each_lexicon_is_complete_and_well_formed(lang):
    lex = LEXICON[lang]
    for key in ("to", "m", "km", "nm", "deg", "pct", "plus"):
        assert lex[key].strip() and not re.search(r"[A-Za-z]", lex[key]), (lang, key)  # a native word, never Latin
    for key in ("kmh", "ms"):
        assert lex[key].count("{n}") == 1 and lex[key].format(n="12"), (lang, key)
        assert not re.search(r"[A-Za-z]", lex[key].replace("{n}", "")), (lang, key)
    assert len(lex["months"]) == 12 and len(set(lex["months"])) == 12
    assert all(w.strip() and not re.search(r"[A-Za-z]", w) for w in lex["months"])


def test_every_latin_month_the_translator_can_write_is_known():
    for name in ("Jan", "January", "Feb", "Sept", "Sep", "September", "Oct", "October", "Dec", "December", "May"):
        assert name.lower() in MONTH_ALIASES
    assert sorted(set(MONTH_ALIASES.values())) == list(range(1, 13))


def test_the_kannada_and_hindi_words_the_user_can_check():
    kn, hi = LEXICON["kn"], LEXICON["hi"]
    assert kn["to"] == "ರಿಂದ" and kn["m"] == "ಮೀಟರ್" and kn["months"][9] == "ಅಕ್ಟೋಬರ್"
    assert hi["to"] == "से" and hi["m"] == "मीटर" and hi["months"][6] == "जुलाई" and hi["months"][9] == "अक्टूबर"


# --- the user's Kannada answer, exactly ---------------------------------------------------------------------------

USER_ANSWER = (
    "ಮಂಗಳೂರು ಪ್ರದೇಶದ ಇತ್ತೀಚಿನ PFZ ಸಲಹೆಯು ಸುರತ್ಕಲ್ ಪಾಯಿಂಟ್ನ Incois ಉಲ್ಲೇಖ 18-23 km ಎಸ್ಡಬ್ಲ್ಯೂ ಆಧಾರದ ಮೇಲೆ "
    "ಮಂಗಳೂರಿನ 16 km ಎನ್ಎನ್ಡಬ್ಲ್ಯೂ (ಸುರತ್ಕಲ್ ಪಾಯಿಂಟ್ ಬಳಿ) 30-35 m ನ ಆಳದಲ್ಲಿ ಮೀನುಗಾರಿಕೆ ವಲಯವನ್ನು ಸೂಚಿಸುತ್ತದೆ. "
    "2 Oct 2026 ಗಾಗಿ ನೀಡಲಾದ ಸಲಹೆಯು ಆರು ದಿನಗಳ ಹಿಂದೆ ಮುಕ್ತಾಯಗೊಂಡಿದೆ."
)


def test_the_user_s_kannada_answer_is_rewritten_exactly():
    out = speakable(USER_ANSWER, "kn")
    assert "18 ರಿಂದ 23 ಕಿಲೋಮೀಟರ್" in out          # the range word, and km in words
    assert "30 ರಿಂದ 35 ಮೀಟರ್ ನ ಆಳದಲ್ಲಿ" in out    # "30-35 m": the case that was read "30 35"
    assert "16 ಕಿಲೋಮೀಟರ್ ಎನ್ಎನ್ಡಬ್ಲ್ಯೂ" in out
    assert "2 ಅಕ್ಟೋಬರ್ 2026 ಗಾಗಿ" in out           # the month the voice dropped
    assert "30-35" not in out and " m " not in out and "Oct" not in out
    # everything else is untouched, including the Latin names the voice already reads well
    assert "PFZ" in out and "Incois" in out and "ಸುರತ್ಕಲ್ ಪಾಯಿಂಟ್" in out


# --- every rule, in every language ------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_a_range_gets_its_connecting_word_and_a_lone_m_becomes_meeters(lang):
    lex = LEXICON[lang]
    assert speakable("x 30-35 m y", lang) == f"x 30 {lex['to']} 35 {lex['m']} y"
    assert speakable("x 30‑35 m y", lang) == f"x 30 {lex['to']} 35 {lex['m']} y"  # the model's U+2011 and narrow space


@pytest.mark.parametrize("lang", LANGS)
def test_km_and_nautical_miles_and_degrees_and_percent(lang):
    lex = LEXICON[lang]
    assert speakable("a 16 km b", lang) == f"a 16 {lex['km']} b"
    assert speakable("a 5 nm b", lang) == f"a 5 {lex['nm']} b"
    assert speakable("a 343° b", lang) == f"a 343 {lex['deg']} b"
    assert speakable("a 40% b", lang) == f"a 40 {lex['pct']} b"


@pytest.mark.parametrize("lang", LANGS)
def test_speeds_use_the_languages_own_per_hour_and_per_second_phrase(lang):
    lex = LEXICON[lang]
    assert speakable("a 12 km/h b", lang) == "a " + lex["kmh"].format(n="12") + " b"
    assert speakable("a 3.4 m/s b", lang) == "a " + lex["ms"].format(n="3.4") + " b"
    # a range of speeds is one phrase, not a range word stranded between two units
    assert speakable("a 30-35 km/h b", lang) == "a " + lex["kmh"].format(n=f"30 {lex['to']} 35") + " b"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(
    ("written", "month_index"),
    [("2 Oct 2026", 10), ("2 October 2026", 10), ("Oct 2, 2026", 10), ("2026-10-02", 10), ("7 July 2026", 7), ("1 Sept 2026", 9)],
)
def test_a_date_gets_its_native_month_name(lang, written, month_index):
    out = speakable(f"a {written} b", lang)
    assert LEXICON[lang]["months"][month_index - 1] in out
    assert not re.search(r"[A-Za-z]{3}", out.replace(" a ", " ").replace(" b", ""))  # no Latin month left
    assert "2026" in out


@pytest.mark.parametrize("lang", LANGS)
def test_a_phone_number_is_read_digit_by_digit(lang):
    out = speakable("call +91-44-2539-5018 now", lang)
    assert out == f"call {LEXICON[lang]['plus']} 9 1, 4 4, 2 5 3 9, 5 0 1 8 now"


def test_a_number_that_is_not_a_phone_number_or_a_real_date_is_left_alone():
    out = speakable("code 2026-13-45 here", "kn")  # month 13 is not a date, and 8 digits is not a phone number
    assert "2 0 2 6" not in out and "ಅಕ್ಟೋಬರ್" not in out
    assert speakable("coordinates 12.9894 74.6056", "kn") == "coordinates 12.9894 74.6056"
    assert "1 2" not in speakable("code 12-34-56 here", "hi")


@pytest.mark.parametrize("lang", LANGS)
def test_ordinary_latin_words_next_to_numbers_are_not_touched(lang):
    # "mm", "months", "Marine", "May" without a day number are words, not a unit or a month
    text = "3 months and 5 mm of Marine data, in May"
    assert speakable(text, lang) == text
    assert speakable("12 kmx and 5 nmo", lang) == "12 kmx and 5 nmo"


@pytest.mark.parametrize("lang", LANGS)
def test_a_sentence_ending_in_a_month_keeps_its_full_stop(lang):
    assert speakable("valid on 7 July.", lang).endswith(".")


def test_english_is_still_handled_by_its_own_rules_and_unchanged_here():
    assert speakable("depth 30-35 m on 2 Oct 2026", "en").startswith("depth 30 to 35 meeters")
    assert LEXICON.get("en") is None


def test_the_exclamation_rule_still_applies_with_a_lexicon_language():
    assert speakable("ನಮಸ್ಕಾರ! 30-35 m", "kn") == "ನಮಸ್ಕಾರ. 30 ರಿಂದ 35 ಮೀಟರ್"


def test_it_is_stable_when_applied_twice():
    for lang in LANGS:
        once = speakable("a 30-35 m, 12 km/h, 2 Oct 2026, 40% b", lang)
        assert speakable(once, lang) == once, lang


@pytest.mark.parametrize(
    ("lang", "written"),
    [
        ("kn", "ಗಾಳಿ 12 km/ಗಂ ಮತ್ತು"),
        ("ta", "காற்று 12 km/மணி மற்றும்"),
        ("te", "గాలి 12 km/గం మరియు"),
        ("bn", "বাতাসের গতিবেগ 12 km/ঘন্টা এবং"),
    ],
)
def test_a_native_word_for_hour_after_km_slash_is_read_as_per_hour(lang, written):
    # The translator's own abbreviation ("km/ಗಂ"), read "ಗಮ" by the voice before this rule.
    out = speakable(written, lang)
    assert LEXICON[lang]["kmh"].format(n="12") in out
    assert "km" not in out and "/" not in out


def test_a_slash_between_two_native_words_or_after_other_units_is_left_alone():
    assert speakable("ಸಮುದ್ರ/ಗಾಳಿ 5 km ದೂರ", "kn") == "ಸಮುದ್ರ/ಗಾಳಿ 5 ಕಿಲೋಮೀಟರ್ ದೂರ"
