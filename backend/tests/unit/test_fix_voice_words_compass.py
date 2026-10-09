"""FIX-VOICE-3 and FIX-VOICE-4 (2026-10-09): single words the English voice mispronounces, and compass
points spoken in full.

The user heard, in "Conditions off Mangalore are safe for a small-fishing boat - ... about 0.6 m wave height
... no MPA breach. The closest potential fishing zone is roughly 16 km to the NNW of Mangalore, ... it should
not be relied on": "height" read "hate", "MPA" "MPE", "roughly" "really", "relied" "releaid", and NNW should
be "north north-west". Each respelling was kept only because it read back right in four of four real
sentences (speech_lexicon.ENGLISH_RESPELLING).
"""
from __future__ import annotations

import pytest

from orca.agents.speech_lexicon import (
    COMPASS_ENGLISH,
    COMPASS_MULTI,
    COMPASS_NATIVE,
    ENGLISH_ACRONYMS,
    ENGLISH_RESPELLING,
    LEXICON,
)
from orca.agents.voice import speakable

LANGS = ["kn", "hi", "mr", "ta", "te", "ml", "bn", "gu", "or"]
USER_RESPONSE = (
    "Conditions off Mangalore are safe for a small\u2011fishing boat \u2013 the sea is flat (about 0.6 m wave height) "
    "and the wind is light (around 2 km/h), with no lightning and no MPA breach. The closest potential fishing zone is "
    "roughly 16 km to the NNW of Mangalore, but its advisory has expired, so it should not be relied on. You can head out now."
)


# --- the user's own response -------------------------------------------------------------------------------------

def test_the_response_the_user_reported_is_spoken_with_every_word_fixed():
    out = speakable(USER_RESPONSE, "en")
    assert "wave hite" in out and "hite" in out and "height" not in out  # "hate"
    assert "marine protected area breach" in out and "MPA" not in out  # "MPE"
    assert "ruffley 16 kilomeeters" in out and "roughly" not in out  # "really"
    assert "re-lied on" in out and "relied" not in out  # "releaid"
    assert "north north-west of Mangalore" in out and "NNW" not in out
    assert "small-fishing" in out  # the non-breaking hyphen is a plain one
    assert "2 kilomeeters per hour" in out and "0.6 meeters" in out


# --- the respelling table ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("word", "respelled"), sorted(ENGLISH_RESPELLING.items()))
def test_each_respelling_is_applied_to_the_whole_word_in_any_case(word, respelled):
    assert speakable(f"a {word} b", "en") == f"a {respelled} b"
    assert speakable(f"{word.capitalize()} b", "en") == f"{respelled[0].upper()}{respelled[1:]} b"
    assert speakable(f"a {word.upper()} b", "en").startswith("a ")  # an all-caps word is also handled, not skipped
    if f"{word}s" not in ENGLISH_RESPELLING and word != "zone":
        assert speakable(f"a {word}s b", "en") == f"a {word}s b"  # "heights" is a different word


def test_a_respelling_does_not_touch_a_longer_word_that_contains_it():
    assert speakable("a heightened risk, roughly-hewn, zoned", "en") == "a heightened risk, roughly-hewn, zoned".replace("roughly-hewn", "ruffley-hewn")


def test_the_table_has_no_entry_that_maps_to_itself_or_to_something_empty():
    for word, respelled in ENGLISH_RESPELLING.items():
        assert respelled.strip() and respelled.lower() != word.lower()


def test_acronyms_are_spoken_by_the_table():
    assert speakable("no MPA breach", "en") == "no marine protected area breach"
    for acronym, spoken in ENGLISH_ACRONYMS.items():
        assert speakable(f"x {acronym} y", "en") == f"x {spoken} y"


# --- compass points in full (English) ---------------------------------------------------------------------------------------

def test_all_sixteen_points_are_defined_and_spoken_in_words():
    assert len(COMPASS_ENGLISH) == 16
    assert set(COMPASS_MULTI) == {k for k in COMPASS_ENGLISH if len(k) > 1}
    for letters, words in COMPASS_ENGLISH.items():
        assert words and words == words.lower() and not any(c.isupper() for c in words)
        if len(letters) > 1:
            assert speakable(f"to the {letters} of it", "en") == f"to the {words} of it"


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("16 km NNW of Mangalore", "16 kilomeeters north north-west of Mangalore"),
        ("wind from the SW", "wind from the south-west"),
        ("a NE swell, then ESE", "a north-east swell, then east south-east"),
        ("at 12.9894 N, 74.6056 E", "at 12.9894 north, 74.6056 east"),
        ("at 15.911\u202fN,\u202f81.397\u202fE", "at 15.911 north, 81.397 east"),
        ("19.2 S and 70 W", "19.2 south and 70 west"),
    ],
)
def test_compass_points_and_coordinate_letters(written, spoken):
    assert speakable(written, "en") == spoken


def test_a_capital_n_e_s_or_w_that_is_not_a_direction_is_left_alone():
    assert speakable("Plan E, Sector S and the W team", "en") == "Plan E, Sector S and the W team"
    assert speakable("NEWS and SEA and NEST", "en") == "NEWS and SEA and NEST"  # words that merely contain the letters


# --- compass points in every language ----------------------------------------------------------------------------------------

def test_every_language_has_its_four_directions():
    assert sorted(COMPASS_NATIVE) == sorted(LANGS)
    for words in COMPASS_NATIVE.values():
        assert set(words) == {"N", "E", "S", "W"} and all(w.strip() for w in words.values())
        assert len(set(words.values())) == 4  # four different words


@pytest.mark.parametrize("lang", LANGS)
def test_a_compass_point_inside_native_text_is_read_in_that_language_letter_by_letter(lang):
    n, w = COMPASS_NATIVE[lang]["N"], COMPASS_NATIVE[lang]["W"]
    assert speakable("x 16 km NNW y", lang) == f"x 16 {LEXICON[lang]['km']} {n} {n} {w} y"
    assert speakable("x SW y", lang) == f"x {COMPASS_NATIVE[lang]['S']} {w} y"


@pytest.mark.parametrize("lang", LANGS)
def test_a_coordinate_letter_inside_native_text_is_read_as_the_direction(lang):
    assert speakable("x 12.9894 N, 74.6056 E y", lang) == f"x 12.9894 {COMPASS_NATIVE[lang]['N']}, 74.6056 {COMPASS_NATIVE[lang]['E']} y"


def test_the_translator_never_sees_a_compass_point_so_it_cannot_turn_nnw_into_north_west():
    from orca.agents.language import _mask_protected_terms

    masked, tokens = _mask_protected_terms("16 km NNW of Mangalore at 12.9894 N, 74.6056 E and SEC104")
    assert tokens == ["16 km NNW", "12.9894 N, 74.6056 E", "SEC104"]
    assert "NNW" not in masked and "N," not in masked


def test_a_word_that_merely_contains_compass_letters_is_not_protected():
    from orca.agents.language import _mask_protected_terms

    masked, tokens = _mask_protected_terms("NEWS and the SEA, NEST and SECTOR near Newport")
    assert tokens == [] and masked == "NEWS and the SEA, NEST and SECTOR near Newport"


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("depth 30 m", "depth 30 meeters"),
        ("depth 30-35 m", "depth 30 to 35 meeters"),
        ("wind 3 m/s", "wind 3 meeters per second"),
        ("0.6 metres and 2 meters and a metre and one meter", "0.6 meeters and 2 meeters and a meeter and one meeter"),
        ("Metres are listed", "Meeters are listed"),
    ],
)
def test_metres_are_spoken_meeters_the_users_choice_by_ear(written, spoken):
    # Listening files M1-M4, 2026-10-09: "metres" is not what anyone says; M3 "meeters" is.
    assert speakable(written, "en") == spoken


def test_kilometres_and_other_words_containing_metre_are_left_alone():
    assert speakable("5 kilomeeters, geometry and parametres", "en") == "5 kilomeeters, geometry and parametres"
    assert speakable("16 km", "en") == "16 kilomeeters"


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("16 km away", "16 kilomeeters away"),
        ("wind 12 km/h", "wind 12 kilomeeters per hour"),
        ("5 kilometres, 5 kilometers, one kilometre, one kilometer", "5 kilomeeters, 5 kilomeeters, one kilomeeter, one kilomeeter"),
        ("Kilometres per hour", "Kilomeeters per hour"),
    ],
)
def test_kilometres_are_spoken_kilomeeters_the_users_choice_by_ear(written, spoken):
    # Listening files K1/K2, 2026-10-09: K2 "kilomeeters" is the right one.
    assert speakable(written, "en") == spoken
