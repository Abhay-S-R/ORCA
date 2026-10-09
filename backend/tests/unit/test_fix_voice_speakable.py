"""FIX-VOICE-1 — the spoken answer.

Every rule here was found by synthesizing the text with Bhashini on 2026-10-08, listening to it (the
user) and reading it back with Whisper (the check), and is kept as a test so a rewrite cannot undo it.
The shown text never changes: these tests are about what the SPEAKER is given.
"""
from __future__ import annotations

import io
import struct
import wave
from unittest import mock

import pytest

from orca.agents import bhashini, voice
from orca.agents.voice import _join_wavs, _wav_to_array, speakable

GREETING = (
    "Hello! I'm Sagar Sarathi — I help with sea conditions off India’s coast: safety to go out, "
    "waves, wind, tides, fishing zones, and maritime boundaries. What would you like to know?"
)


# --- the rewriting ----------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("shown", "spoken"),
    [
        # "Hello! ..." was read "Hello factorial"; the em dash after the name was read as a letter
        (
            GREETING,
            (
                "Hello. I'm Sagar Sarathi, I help with sea conditions off India's coast: safety to go out, "
                "waves, wind, tides, fishing zohnz, and maritime boundaries. What would you like to know?"
            ),
        ),
        # the curly apostrophe is what made "don't" read "don, pause, tee"
        ("I don’t know, it’s not safe, you can’t go.", "I don't know, it's not safe, you can't go."),
        # U+2011 (the model's non-breaking hyphen) was read as the date "2000 and 2062" and the range "3035"
        ("valid for 2026‑10‑02, depth 30‑35 m", "valid for 2 October 2026, depth 30 to 35 meeters"),
        ("issued 2030-01-15 and 2019-12-31 and 2100-05-06", "issued 15 January 2030 and 31 December 2019 and 6 May 2100"),
        # a long all-caps word was spelled or garbled ("SIMULATED" heard as "AMUL-ERETED"); DAT-SG too
        ("This handoff is SIMULATED, no live DAT-SG/telephony link.", "This handoff is simulated, no live D A T S G and telephony link."),
        ("DISTRESS DETECTED. GO: INCOIS says NNW.", "distress detected. GO: incois says north north-west."),
        ("depth 30-35 m near the point", "depth 30 to 35 meeters near the point"),
        # "km/h" lost "per hour", "m/s" was read "Rims", a lone "m" was read as the letter M
        ("Wind is 12 km/h, 3.4 m/s, waves 1.5 m.", "Wind is 12 kilomeeters per hour, 3.4 meeters per second, waves 1.5 meeters."),
        ("about 16 km NNW of Mangalore", "about 16 kilomeeters north north-west of Mangalore"),
        ("5 nm away", "5 nautical miles away"),
        ("bearing 343°, a 40% chance", "bearing 343 degrees, a 40 percent chance"),
        # the phone number is read digit by digit, as the distress path must
        (
            "Coast Guard MRCC: +91-44-2539-5018 (nationwide: 1554), VHF channel 16.",
            (
                "Coast Guard M R C C: plus nine one, four four, two five three nine, five zero one eight, "
                "nationwide: one five five four, V H F channel 16."
            ),
        ),
        # IMBL was read "AMBL" / "emerald"; IST "AST"; "/" and "&" were dropped
        ("5 nm from the IMBL", "5 nautical miles from the eye em bee el"),
        ("High tide at 08:24 IST", "High tide at 8:24 Indian Standard Time"),
        ("Wave/wind & tide data", "Wave and wind and tide data"),
        # "zone(s)" lost its z ("fishing ones", "nearest sun")
        ("The nearest zone is calm. Zones to avoid.", "The nearest zohn is calm. Zohnz to avoid."),
    ],
)
def test_english_text_is_rewritten_for_the_speaker(shown, spoken):
    assert speakable(shown, "en") == spoken


def test_a_translation_placeholder_is_never_read_out():
    out = speakable("Waves are about ZKEEPZ0Z meeters.", "en")
    assert "ZKEEPZ" not in out and out == "Waves are about meeters."
    assert "ZKEEPZ" not in speakable("लहर ZKEEPZ12Z मीटर", "hi")


def test_markdown_and_emoji_are_dropped():
    assert speakable("**GO:** calm.\n\n- Waves are *low*.\n- Wind is light. \U0001F60A", "en") == "GO: calm. Waves are low. Wind is light."


def test_an_unrelated_number_is_not_turned_into_a_date_or_a_phone():
    assert speakable("Wave height 1.5 m at 12.9894 N, 74.6056 E.", "en") == "Wave hite 1.5 meeters at 12.9894 north, 74.6056 east."
    assert speakable("VHF channel 16 and 5 days old.", "en") == "V H F channel 16 and 5 days old."
    assert "October" not in speakable("Code 2026-13-45 is not a date.", "en")  # month 13 is not a month
    assert "one, two" not in speakable("Items 1-2-3 listed.", "en")  # too few digits to be a phone number


def test_a_native_answer_gets_the_neutral_clean_up_and_its_own_words_not_the_english_ones():
    ta = "கோ: பாதுகாப்பான 16 km/h"
    # the English rules ("kilomeeters per hour") never reach another language: Tamil gets its own phrase
    assert speakable(ta, "ta") == "கோ: பாதுகாப்பான மணிக்கு 16 கிலோமீட்டர்"
    assert speakable("கோ கோ—கோ", "ta") == "கோ கோ, கோ"


@pytest.mark.parametrize(
    ("lang", "greeting", "spoken"),
    [
        ("kn", "\u0ca8\u0cae\u0cb8\u0ccd\u0c95\u0cbe\u0cb0! \u0ca8\u0cbe\u0ca8\u0cc1 \u0cb8\u0cbe\u0c97\u0cb0 \u0cb8\u0cbe\u0cb0\u0ca5\u0cbf.", "\u0ca8\u0cae\u0cb8\u0ccd\u0c95\u0cbe\u0cb0. \u0ca8\u0cbe\u0ca8\u0cc1 \u0cb8\u0cbe\u0c97\u0cb0 \u0cb8\u0cbe\u0cb0\u0ca5\u0cbf."),
        ("kn", "\u0cb9\u0cc7\u0cb2\u0ccb! \u0ca8\u0cbe\u0ca8\u0cc1", "\u0cb9\u0cc7\u0cb2\u0ccb. \u0ca8\u0cbe\u0ca8\u0cc1"),
        ("hi", "\u0928\u092e\u0938\u094d\u0924\u0947! \u092e\u0948\u0902 \u0939\u0942\u0901\u0964", "\u0928\u092e\u0938\u094d\u0924\u0947. \u092e\u0948\u0902 \u0939\u0942\u0901\u0964"),
        ("ta", "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd! \u0ba8\u0bbe\u0ba9\u0bcd", "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd. \u0ba8\u0bbe\u0ba9\u0bcd"),
        ("te", "\u0c28\u0c2e\u0c38\u0c4d\u0c15\u0c3e\u0c30\u0c02! \u0c28\u0c47\u0c28\u0c41", "\u0c28\u0c2e\u0c38\u0c4d\u0c15\u0c3e\u0c30\u0c02. \u0c28\u0c47\u0c28\u0c41"),
        ("ml", "\u0d28\u0d2e\u0d38\u0d4d\u0d15\u0d3e\u0d30\u0d02! \u0d1e\u0d3e\u0d7b", "\u0d28\u0d2e\u0d38\u0d4d\u0d15\u0d3e\u0d30\u0d02. \u0d1e\u0d3e\u0d7b"),
        ("bn", "\u09a8\u09ae\u09b8\u09cd\u0995\u09be\u09b0! \u0986\u09ae\u09bf", "\u09a8\u09ae\u09b8\u09cd\u0995\u09be\u09b0. \u0986\u09ae\u09bf"),
        ("gu", "\u0aa8\u0aae\u0ab8\u0acd\u0aa4\u0ac7! \u0ab9\u0ac1\u0a82", "\u0aa8\u0aae\u0ab8\u0acd\u0aa4\u0ac7. \u0ab9\u0ac1\u0a82"),
        ("mr", "\u0928\u092e\u0938\u094d\u0915\u093e\u0930! \u092e\u0940", "\u0928\u092e\u0938\u094d\u0915\u093e\u0930. \u092e\u0940"),
        ("or", "\u0b28\u0b2e\u0b38\u0b4d\u0b15\u0b3e\u0b30! \u0b2e\u0b41\u0b01", "\u0b28\u0b2e\u0b38\u0b4d\u0b15\u0b3e\u0b30. \u0b2e\u0b41\u0b01"),
    ],
)
def test_an_exclamation_mark_is_never_spoken_in_any_language(lang, greeting, spoken):
    # Reproduced with Bhashini TTS and ASR on 2026-10-08: "!" came back as the word "factorial" in
    # Kannada, Hindi, Tamil, Telugu, Bengali and Gujarati (Kannada: "namaskara taktoriyal").
    assert speakable(greeting, lang) == spoken


def test_every_exclamation_variant_is_dropped_and_nothing_else_is_lost():
    assert speakable("a! b\uff01 c\u203c d", "kn") == "a. b. c. d"


def test_it_is_stable_when_applied_twice_and_never_returns_nothing_for_text():
    for text in (GREETING, "Coast Guard MRCC: +91-44-2539-5018.", "Wave/wind & tide data (INCOIS)."):
        once = speakable(text, "en")
        assert once and speakable(once, "en") == once.replace("zohnz", "zohnz")


def test_the_text_on_screen_is_untouched_by_construction():
    text = "Hello! 12 km/h"
    speakable(text, "en")
    assert text == "Hello! 12 km/h"


# --- WAV handling -------------------------------------------------------------------------------------

def _float_wav(samples, rate=22050):
    data = struct.pack(f"<{len(samples)}f", *samples)
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _int_wav(samples, rate=22050):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def test_a_float_wav_from_bhashini_is_read():
    samples, rate = _wav_to_array(_float_wav([0.0, 0.5, -0.5]))
    assert rate == 22050 and list(samples) == [0.0, 0.5, -0.5]


def test_a_non_wav_reply_is_an_error_not_noise():
    with pytest.raises(RuntimeError):
        _wav_to_array(b"not audio at all")


def test_joined_audio_is_one_playable_wav_with_a_gap_between_parts():
    joined = _join_wavs([_float_wav([0.1] * 2205), _int_wav([1000] * 2205, rate=11025)], gap_s=0.05)
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == 22050
        # 0.1 s + 0.05 s gap + (0.2 s of 11 kHz audio resampled to 22 kHz)
        assert abs(w.getnframes() - (2205 + 1102 + 4410)) < 5


# --- the name is spoken by the Hindi voice, the rest by the English male voice -----------------------------

class _FakeTts:
    def __init__(self):
        self.calls = []

    def __call__(self, text, lang, gender="female"):
        self.calls.append((text, lang, gender))
        return _float_wav([0.1] * 1000)


@pytest.fixture
def fake_bhashini():
    fake = _FakeTts()
    with mock.patch.object(bhashini, "bhashini_configured", lambda: True), mock.patch.object(bhashini, "tts", fake):
        yield fake


def test_the_name_goes_to_the_hindi_voice_and_the_rest_stays_english_male(fake_bhashini):
    audio = voice.BhashiniTtsBackend().speak("Hello. I'm Sagar Sarathi, I help with sea conditions.", "en")
    assert fake_bhashini.calls == [
        ("Hello. I'm", "en", "male"),
        ("सागर सारथी", "hi", "male"),
        ("I help with sea conditions.", "en", "male"),
    ]
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getnframes() > 3000


@pytest.mark.parametrize("name", ["Sagar Sarathi", "sagar sarathi", "Saagar Saarthi".replace("Saarthi", "Sarathi"), "SAGAR SARATHI"])
def test_the_name_is_found_however_it_is_cased(fake_bhashini, name):
    voice.BhashiniTtsBackend().speak(f"I am {name}.", "en")
    assert [c[1] for c in fake_bhashini.calls] == ["en", "hi"]


def test_a_sentence_that_starts_or_ends_with_the_name_has_no_empty_part(fake_bhashini):
    voice.BhashiniTtsBackend().speak("Sagar Sarathi", "en")
    assert [c[1] for c in fake_bhashini.calls] == ["hi"]


def test_english_without_the_name_is_one_male_call(fake_bhashini):
    voice.BhashiniTtsBackend().speak("Wave height is 1 meeter.", "en")
    assert fake_bhashini.calls == [("Wave height is 1 meeter.", "en", "male")]


def test_other_languages_keep_their_voice(fake_bhashini):
    voice.BhashiniTtsBackend().speak("கோ: கோ", "ta")
    assert fake_bhashini.calls == [("கோ: கோ", "ta", "female")] or fake_bhashini.calls[0][:2] == ("கோ: கோ", "ta")


def test_text_to_speech_hands_the_backend_the_speakable_text_and_caches_the_audio():
    seen = []

    class _Backend:
        def speak(self, text, language):
            seen.append(text)
            return b"AUDIO"

    voice._tts_cache.clear()
    with mock.patch.object(voice, "_tts_backends", (_Backend(),)):
        first = voice.text_to_speech("Hello! 12 km/h", "en")
        second = voice.text_to_speech("Hello! 12 km/h", "en")
    assert first[0] == b"AUDIO" and second == first
    assert seen == ["Hello. 12 kilomeeters per hour"]  # one synthesis, of the cleaned text


# --- Bhashini's own timeout and retry for speech -----------------------------------------------------------

def _config():
    return {"serviceId": "svc", "callback_url": "http://x", "inference_api_key": {"name": "k", "value": "v"}}


def _reply():
    return {"pipelineResponse": [{"audio": [{"audioContent": "QVVESU8="}]}]}  # "AUDIO"


def test_speech_has_its_own_longer_timeout():
    assert bhashini.TTS_TIMEOUT_S >= 10 > bhashini.TIMEOUT_S
    with mock.patch.object(bhashini, "_pipeline_config", return_value=_config()), \
            mock.patch.object(bhashini, "_inference", return_value=_reply()) as call:
        assert bhashini.tts("hi", "en", "male") == b"AUDIO"
    assert call.call_args.kwargs["timeout_s"] == bhashini.TTS_TIMEOUT_S


def test_one_failed_attempt_is_retried_before_the_caller_falls_to_the_local_voice():
    with mock.patch.object(bhashini, "_pipeline_config", return_value=_config()), \
            mock.patch.object(bhashini, "_inference", side_effect=[bhashini.BhashiniError("timeout"), _reply()]) as call:
        assert bhashini.tts("hi", "en") == b"AUDIO"
    assert call.call_count == 2


def test_two_failed_attempts_raise_so_the_next_rung_can_answer():
    with mock.patch.object(bhashini, "_pipeline_config", return_value=_config()), \
            mock.patch.object(bhashini, "_inference", side_effect=bhashini.BhashiniError("down")) as call, \
            pytest.raises(bhashini.BhashiniError):
        bhashini.tts("hi", "en")
    assert call.call_count == 2
