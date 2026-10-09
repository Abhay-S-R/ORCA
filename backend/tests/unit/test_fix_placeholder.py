"""FIX-PLACEHOLDER-1 — protected numbers survive translation in every language.

The placeholder for a number or unit was `ZKEEPZ{n}Z`. In Marathi, Bengali and sometimes Hindi the
translator spelled that Latin pseudo-word by ear ("झेडकेईईपीझेड5झेड") and the answer LOST the number it stood
for, e.g. a wave height. Measured 2026-10-09 (six answers, nine languages): `ZKEEPZ{n}Z` 312 of 333
survived, a 7-digit number 314 (the translator regrouped it "70,00,043"), a 3-digit number 333. The
placeholder is now a 3-digit number, ranges are one token, and a token that does not come back exactly
once makes the sentence be translated again unmasked, so a number is never silently dropped.
"""
from __future__ import annotations

from unittest import mock

import pytest

from orca.agents import bhashini
from orca.agents.language import (
    _MAX_PLACEHOLDERS,
    _PLACEHOLDER_BASE,
    _mask_protected_terms,
    _translate_with_rung,
    _unmask_protected_terms,
    normalise_compass,
    normalise_for_translation,
)

LANGS = ["kn", "hi", "mr", "ta", "te", "ml", "bn", "gu", "or"]
ANSWER = (
    "CAUTION: wave 2.4 m above the 2.0 m limit near SEC104, wind 12 km/h, 10.5 m/s gusts, "
    "PFZ 16.2 km NNW, depth 30-35 m, IMBL 4.2 nm, valid 2026-10-09, 40% data, 343°C."
)


# --- what is protected ---------------------------------------------------------------------------------------

def test_every_number_range_unit_and_term_is_one_placeholder_and_nothing_else_is_masked():
    masked, tokens = _mask_protected_terms(ANSWER)
    assert tokens == [
        "2.4 m", "2.0 m", "SEC104", "12 km/h", "10.5 m/s", "PFZ", "16.2 km NNW", "30-35 m", "IMBL",
        "4.2 nm", "2026-10-09", "40%", "343\u00b0C",
    ]  # "16.2 km NNW" is ONE token: two adjacent placeholders were run together by the translator
    assert masked == (
        "CAUTION: wave 801 above the 802 limit near 803, wind 804, 805 gusts, 806 807, "
        "depth 808, 809 810, valid 811, 812 data, 813."
    )  # words stay for the translator; every digit left is a placeholder


def test_a_range_is_one_token_not_two_run_together():
    masked, tokens = _mask_protected_terms("depth 30-35 m and 30–35 m")
    assert tokens == ["30-35 m", "30–35 m"]
    assert masked == f"depth {_PLACEHOLDER_BASE} and {_PLACEHOLDER_BASE + 1}"


def test_a_date_is_one_token():
    assert _mask_protected_terms("on 2026-10-09 it")[1] == ["2026-10-09"]


def test_the_placeholders_are_three_digit_numbers_and_distinct():
    masked, tokens = _mask_protected_terms(" ".join(f"{i} m" for i in range(1, 41)))
    assert len(tokens) == 40
    numbers = masked.split()
    assert len(set(numbers)) == 40 and all(len(n) == 3 and n.isdigit() for n in numbers)


def test_an_answer_with_too_many_numbers_is_left_unmasked_not_overflowed():
    text = " ".join(f"{i} m" for i in range(1, _MAX_PLACEHOLDERS + 5))
    masked, tokens = _mask_protected_terms(text)
    assert masked == text and tokens == []


# --- putting them back ----------------------------------------------------------------------------------------------

def test_unmasking_restores_every_original_and_reports_complete():
    masked, tokens = _mask_protected_terms(ANSWER)
    restored, complete = _unmask_protected_terms(masked, tokens)
    assert restored == ANSWER and complete


def test_a_translator_that_reorders_or_surrounds_the_placeholders_is_fine():
    _, tokens = _mask_protected_terms("wave 2.4 m near SEC104")
    # native text around and between them, in any order, with native punctuation
    out = f"ಸಮ {_PLACEHOLDER_BASE + 1}। ಸಮು ({_PLACEHOLDER_BASE})"
    restored, complete = _unmask_protected_terms(out, tokens)
    assert complete and "SEC104" in restored and "2.4 m" in restored


@pytest.mark.parametrize("corruption", ["drop", "duplicate", "garble"])
def test_a_dropped_repeated_or_garbled_placeholder_is_detected(corruption):
    masked, tokens = _mask_protected_terms("a 2.4 m b 12 km c")
    one, two = str(_PLACEHOLDER_BASE), str(_PLACEHOLDER_BASE + 1)
    bad = {
        "drop": masked.replace(two, ""),
        "duplicate": masked + f" {one}",
        "garble": masked.replace(two, "झेडकेई"),  # "झेडकेई": spelled by ear
    }[corruption]
    assert _unmask_protected_terms(bad, tokens)[1] is False


def test_an_unrelated_number_in_the_output_is_left_alone():
    masked, tokens = _mask_protected_terms("a 2.4 m b")
    restored, complete = _unmask_protected_terms(f"{masked} 5 days 1999", tokens)
    assert complete and "5 days 1999" in restored and "2.4 m" in restored


# --- the translation: no number is silently lost, in any language -------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_a_translator_that_keeps_the_placeholders_returns_the_exact_numbers(lang):
    seen = []

    def nmt(text, source, target):
        seen.append(text)
        return "[" + target + "] " + text

    with mock.patch.object(bhashini, "nmt", nmt):
        out, rung = _translate_with_rung(ANSWER, "en", lang)  # type: ignore[arg-type]
    assert rung == "bhashini" and len(seen) == 1  # one call: nothing lost
    for original in ("2.4 m", "30-35 m", "12 km/h", "2026-10-09", "SEC104", "343°C"):
        assert original in out
    assert "ZKEEPZ" not in seen[0] and "2.4" not in seen[0]  # the translator never saw the numbers


@pytest.mark.parametrize("lang", LANGS)
def test_a_translator_that_garbles_a_placeholder_is_retried_sentence_by_sentence(lang):
    calls = []

    def nmt(text, source, target):
        calls.append(text)
        if len(calls) == 1:  # the Marathi/Bengali failure: a placeholder is spelled by ear
            return text.replace(str(_PLACEHOLDER_BASE + 1), "\u091d\u0947\u0921\u0915\u0947\u0908")
        return "[" + target + "] " + text

    with mock.patch.object(bhashini, "nmt", nmt):
        out, _ = _translate_with_rung("wave 2.4 m and wind 12 km/h", "en", lang)  # type: ignore[arg-type]
    assert len(calls) == 2 and str(_PLACEHOLDER_BASE) in calls[1]  # the retry is per sentence and still protected
    assert "2.4 m" in out and "12 km/h" in out  # the numbers are in the answer


@pytest.mark.parametrize("lang", LANGS)
def test_a_sentence_that_cannot_be_protected_is_translated_unmasked_and_the_others_keep_their_protection(lang):
    calls = []

    def nmt(text, source, target):
        calls.append(text)
        if "801" in text and "bad" in text:  # one sentence always loses its placeholder
            return text.replace("801", "")
        return "[" + target + "] " + text

    with mock.patch.object(bhashini, "nmt", nmt):
        out, _ = _translate_with_rung("The wave is 2.4 m. The bad wind is 12 km/h. The tide is 0.5 m.", "en", lang)  # type: ignore[arg-type]
    assert "2.4 m" in out and "12 km/h" in out and "0.5 m" in out
    assert "The bad wind is 12 km/h." in calls  # that one sentence was sent as written
    assert sum(1 for c in calls if "801" in c) >= 3  # the other two stayed protected


def test_the_local_rung_is_also_checked():
    from orca.agents import language

    calls = []

    class Backend:
        def translate(self, text, source, target):
            calls.append(text)
            return text if len(calls) > 1 else "no placeholders at all"

    with mock.patch.object(bhashini, "nmt", side_effect=RuntimeError("down")), mock.patch.object(language, "_backend", Backend()):
        out, rung = _translate_with_rung("wave 2.4 m", "en", "hi")
    assert rung == "indictrans2" and len(calls) == 2 and "2.4 m" in out


def test_text_with_no_numbers_is_translated_as_is_in_one_call():
    with mock.patch.object(bhashini, "nmt", lambda text, source, target: "x " + text) as nmt:
        out, _ = _translate_with_rung("calm seas", "en", "mr")
    assert out == "x calm seas"
    assert nmt is not None


# --- FIX-COMPASS-1: the adjacent-placeholder failure, and the normalising before masking -----------------------------------

def test_a_number_with_its_unit_and_compass_point_is_one_token_and_a_coordinate_pair_is_one_token():
    masked, tokens = _mask_protected_terms("about 16 km NNW of Mangalore, around 81.397 E, 15.911 N, 5 nm ENE, at 08:24")
    assert tokens == ["16 km NNW", "81.397 E, 15.911 N", "5 nm ENE", "08:24"]
    assert masked == "about 801 of Mangalore, around 802, 803, at 804"


@pytest.mark.parametrize("written", ["2 Oct 2026", "October 2, 2026", "2 October", "Oct 2", "2026-10-02"])
def test_a_written_date_is_one_token(written):
    assert _mask_protected_terms(f"valid on {written} only")[1] == [written]


def test_a_translator_that_treats_adjacent_numbers_as_one_cannot_swallow_the_distance_and_direction():
    # Hindi, 2026-10-09: "about 801 802 of Mangalore" came back with BOTH placeholders dropped. With the phrase
    # as one token there is nothing adjacent to merge, and a translator that does drop one is caught.
    seen = []

    def nmt(text, source, target):
        seen.append(text)
        return text.replace("801 802", "") if "801 802" in text else "[hi] " + text

    with mock.patch.object(bhashini, "nmt", nmt):
        out, _ = _translate_with_rung("The nearest zone is about 16 km NNW of Mangalore.", "en", "hi")
    assert "801 802" not in seen[0] and "16 km NNW" in out


@pytest.mark.parametrize(
    ("written", "normalised"),
    [
        ("16 km N-N-W of it", "16 km NNW of it"),
        ("a N\u2011N\u2011W swell", "a NNW swell"),
        ("from the N.N.W.", "from the NNW"),
        ("S-W wind and E-S-E", "SW wind and ESE"),
        ("20 km north-north-west of the port", "20 km NNW of the port"),
        ("west south-west of Kochi", "WSW of Kochi"),
        ("east north-east, then north\u2011northwest", "ENE, then NNW"),
        ("the north-west and south east and N-S", "the north-west and south east and N-S"),  # two-part and non-points stay
        ("N-X-W and A-N-W", "N-X-W and A-N-W"),
    ],
)
def test_compass_spellings_are_normalised_to_the_abbreviation(written, normalised):
    assert normalise_compass(written) == normalised


@pytest.mark.parametrize(
    ("written", "normalised"),
    [
        ("14.9 kilometres WSW of Kochi", "14.9 km WSW of Kochi"),
        ("28 to 33 meters deep", "28-33 m deep"),
        ("5 nautical miles away", "5 nm away"),
        ("2 to 3 days and 3 to 4 weeks", "2 to 3 days and 3 to 4 weeks"),  # a range with no unit is left as words
        ("a metre of sea and 12 metres", "a metre of sea and 12 m"),
    ],
)
def test_spelled_units_become_symbols_so_a_phrase_is_one_token(written, normalised):
    assert normalise_for_translation(written) == normalised


def test_a_kannada_and_tamil_style_answer_comes_back_with_its_direction_distance_and_date():
    en = "The nearest zone is 14.9 kilometres west south-west of Kochi, at 28 to 33 meters depth, advisory from October 2, 2026."
    seen = []

    def nmt(text, source, target):
        seen.append(text)
        return "[" + target + "] " + text  # keeps every placeholder

    with mock.patch.object(bhashini, "nmt", nmt):
        out, _ = _translate_with_rung(en, "en", "ta")
    assert out == "[ta] The nearest zone is 14.9 km WSW of Kochi, at 28-33 m depth, advisory from October 2, 2026."
    assert len(seen) == 1 and "WSW" not in seen[0] and "kilometres" not in seen[0]
