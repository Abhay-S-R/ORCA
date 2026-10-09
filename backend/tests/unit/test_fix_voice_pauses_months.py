"""FIX-VOICE-7 (2026-10-09): the pause the voice puts in long answers, a direction letter after a degree sign,
"approximately equal", and abbreviated months.

The user heard: a pause after "You" in "...so it should not be relied on. You can head out now." with no
punctuation there; "9.915 N, 76.074 E" read as the letters N and E in the fisherman's answer; "Oct" and "Sept"
mispronounced. The pause is the service cutting its output at about 25 s (measured: the gap stays at 24.9 s
whatever the last sentence says, and is absent from a 372-character text), so long text is split by us at
sentence ends.
"""
from __future__ import annotations

from unittest import mock

import pytest

from orca.agents import bhashini, voice
from orca.agents.voice import _expand_months, speakable, split_for_bhashini

FISHERMAN = (
    "The nearest known fishing zone is about 15 km WSW of Kochi (bearing 248\u00b0), at roughly 9.915\u00b0 N, 76.074\u00b0 E and "
    "28\u201133 m depth. The latest advisory for that zone was issued on 2 Oct 2026 (7 days old) and has now expired, so there is no "
    "current advisory. Current sea conditions (wave \u2248 0.66 m, wind \u2248 0.78 m/s) are within safe limits for small\u2011fishing vessels."
)
MANGALORE = (
    "Conditions off Mangalore are safe for a small\u2011fishing boat \u2013 the sea is flat (about 0.6 m wave height) and the wind is light "
    "(around 2 km/h), with no lightning and no MPA breach. The closest potential fishing zone is roughly 16 km to the NNW of Mangalore, "
    "but its advisory has expired, so it should not be relied on. You can head out now."
)


# --- the fisherman's answer, as the user reported it ---------------------------------------------------------------------------

def test_the_fisherman_answer_says_north_and_east_not_the_letters():
    out = speakable(FISHERMAN, "en")
    assert "9.915 degrees north, 76.074 degrees east" in out
    assert " N," not in out and " E " not in out
    assert "west south-west of Kochi" in out and "bearing 248 degrees" in out
    assert "2 October 2026" in out and "Oct " not in out
    assert "wave about 0.66 meeters, wind about 0.78 meeters per second" in out and "\u2248" not in out
    assert "28 to 33 meeters" in out


@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("at 9.915\u00b0 N, 76.074\u00b0 E", "at 9.915 degrees north, 76.074 degrees east"),
        ("at 19.2\u00b0S 70\u00b0W", "at 19.2 degrees south 70 degrees west"),
        ("bearing 248\u00b0 from the port", "bearing 248 degrees from the port"),
        ("water 28\u00b0C and 12.9894 N", "water 28 degrees C and 12.9894 north"),
    ],
)
def test_a_direction_letter_after_a_degree_sign_is_a_direction(written, spoken):
    assert speakable(written, "en") == spoken


@pytest.mark.parametrize(
    ("written", "spoken"),
    [("wave \u2248 0.66 m", "wave about 0.66 meeters"), ("~12 km", "about 12 kilomeeters"), ("\u00b12 m", "plus or minus 2 meeters")],
)
def test_approximately_equal_and_plus_or_minus_are_words(written, spoken):
    assert speakable(written, "en").strip() == spoken


# --- months in full --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("written", "spoken"),
    [
        ("issued on 2 Oct 2026", "issued on 2 October 2026"),
        ("Oct 2, 2026", "October 2, 2026"),
        ("on 1 Sept 2026 and 3 Sep.", "on 1 September 2026 and 3 September."),
        ("12 Jan, 5 Feb, 7 Mar, 9 Apr, 1 Jun, 2 Jul, 3 Aug, 4 Nov, 5 Dec", "12 January, 5 February, 7 March, 9 April, 1 June, 2 July, 3 August, 4 November, 5 December"),
        ("valid 2026-10-02", "valid 2 October 2026"),
        ("2 October 2026 and 7 May", "2 October 2026 and 7 May"),
    ],
)
def test_abbreviated_months_are_written_in_full_for_the_speaker(written, spoken):
    assert speakable(written, "en") == spoken


def test_a_word_that_merely_starts_like_a_month_is_not_touched():
    text = "Mark the decide of Octave and Sepal, 5 marks, Dec"
    assert _expand_months(text) == text


# --- long text is split by us, at sentence ends --------------------------------------------------------------------------------------

def test_a_text_within_the_limit_is_one_piece_unchanged():
    assert split_for_bhashini("Calm seas near Kochi. You can go.") == ["Calm seas near Kochi. You can go."]
    exactly = "x" * 260
    assert split_for_bhashini(exactly) == [exactly]


def test_the_mangalore_response_that_paused_is_split_at_the_full_stop_not_inside_a_sentence():
    spoken = speakable(MANGALORE, "en")
    assert len(spoken) > 260  # the length that made the service cut it
    pieces = split_for_bhashini(spoken)
    assert len(pieces) == 2 and pieces[1].endswith("You can head out now.")
    assert pieces[0].endswith("breach.") and "You can" not in pieces[0]
    assert " ".join(pieces) == spoken


def test_every_piece_is_within_the_limit_and_no_words_are_lost_or_reordered():
    text = " ".join(f"Sentence number {i} says the sea near port {i} is calm today." for i in range(40))
    pieces = split_for_bhashini(text)
    assert all(len(p) <= 260 for p in pieces) and len(pieces) > 5
    assert " ".join(pieces) == text


def test_one_very_long_sentence_is_cut_at_commas_or_and_never_in_a_word():
    sentence = "The sea is calm near the harbour, " * 4 + "and the wind is light near the shore " + "and the tide is low " * 8 + "today."
    pieces = split_for_bhashini(sentence)
    assert all(len(p) <= 260 for p in pieces) and len(pieces) >= 2
    assert " ".join(pieces).replace(",", "").split() == sentence.replace(",", "").split()


def test_a_sentence_that_cannot_be_cut_is_sent_whole_rather_than_broken():
    word_run = "a" * 400
    assert split_for_bhashini(word_run) == [word_run]


# --- the backend sends the pieces and joins them -------------------------------------------------------------------------------------------

class _FakeTts:
    def __init__(self):
        self.calls = []

    def __call__(self, text, lang, gender="female"):
        import struct

        self.calls.append((text, lang, gender))
        data = struct.pack("<500f", *([0.1] * 500))
        fmt = struct.pack("<HHIIHH", 3, 1, 22050, 22050 * 4, 4, 32)
        body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
        return b"RIFF" + struct.pack("<I", len(body)) + body


@pytest.fixture
def fake_tts():
    fake = _FakeTts()
    with mock.patch.object(bhashini, "bhashini_configured", lambda: True), mock.patch.object(bhashini, "tts", fake):
        yield fake


def test_a_short_answer_is_still_one_call(fake_tts):
    voice.BhashiniTtsBackend().speak("Calm seas near Kochi. You can go.", "en")
    assert fake_tts.calls == [("Calm seas near Kochi. You can go.", "en", "male")]


def test_a_long_answer_is_sent_in_pieces_each_within_the_limit_with_the_male_voice(fake_tts):
    spoken = speakable(MANGALORE, "en")
    audio = voice.BhashiniTtsBackend().speak(spoken, "en")
    assert len(fake_tts.calls) == 2 and all(c[1:] == ("en", "male") for c in fake_tts.calls)
    assert all(len(c[0]) <= 260 for c in fake_tts.calls)
    import io
    import wave

    with wave.open(io.BytesIO(audio)) as w:
        assert w.getnframes() > 2 * 500  # two pieces and the gap between them are one file


def test_the_pieces_of_a_long_answer_with_the_name_keep_the_name_in_the_hindi_voice(fake_tts):
    text = "Hello. I am Sagar Sarathi. " + "The sea near the harbour is calm and the wind is light today. " * 6
    voice.BhashiniTtsBackend().speak(text.strip(), "en")
    voices = [c[1] for c in fake_tts.calls]
    assert voices[0] == "en" and voices[1] == "hi" and set(voices[2:]) == {"en"} and len(voices) >= 4
    assert all(len(c[0]) <= 260 for c in fake_tts.calls if c[1] == "en")


def test_other_languages_are_split_too_with_their_default_voice(fake_tts):
    text = " ".join(["\u0cb8\u0cae\u0cc1\u0ca6\u0ccd\u0cb0 \u0cb6\u0cbe\u0c82\u0ca4\u0cb5\u0cbe\u0c97\u0cbf\u0ca6\u0cc6."] * 40)
    voice.BhashiniTtsBackend().speak(text, "kn")
    assert len(fake_tts.calls) >= 2 and all(c[1:] == ("kn", "female") for c in fake_tts.calls)
    assert all(len(c[0]) <= 260 for c in fake_tts.calls)


# --- Indian-language text and translation ---------------------------------------------------------------------------------------------------

def test_a_direction_letter_after_a_degree_sign_in_native_text_is_the_native_direction():
    from orca.agents.speech_lexicon import COMPASS_NATIVE, LEXICON

    out = speakable("x 9.915\u00b0 N, 76.074\u00b0 E y", "kn")
    assert out == f"x 9.915 {LEXICON['kn']['deg']} {COMPASS_NATIVE['kn']['N']}, 76.074 {LEXICON['kn']['deg']} {COMPASS_NATIVE['kn']['E']} y"


def test_the_translator_sees_a_coordinate_with_its_degree_sign_and_letter_as_one_protected_term():
    from orca.agents.language import _mask_protected_terms

    masked, tokens = _mask_protected_terms("at roughly 9.915\u00b0 N, 76.074\u00b0 E and 28\u201133 m depth")
    assert tokens == ["9.915\u00b0 N, 76.074\u00b0 E", "28\u201133 m"]
    assert "\u00b0" not in masked and "N," not in masked
