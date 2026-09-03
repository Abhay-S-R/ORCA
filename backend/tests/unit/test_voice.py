# faster-whisper / MMS-TTS weights are real local models (present on this
# machine, backend/scripts/download_ml_models.py downloads faster-whisper;
# MMS-TTS lazy-downloads per language on first use) — not guaranteed on a
# fresh CI checkout, so the real round trip below skips itself the same way
# test_language.py's IndicTrans2 integration test does.
from pathlib import Path

import pytest

from orca.agents.voice import (
    LOW_CONFIDENCE_THRESHOLD,
    BhashiniAsrBackend,
    BhashiniTtsBackend,
    TranscriptionResult,
    speech_to_text,
    text_to_speech,
)

_HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"
_WHISPER_PRESENT = any(_HF_HUB.glob("models--Systran--faster-whisper-small"))
_MMS_EN_PRESENT = any(_HF_HUB.glob("models--facebook--mms-tts-eng"))


def test_bhashini_asr_raises_when_uncredentialed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BHASHINI_USER_ID", raising=False)
    monkeypatch.delenv("BHASHINI_ULCA_API_KEY", raising=False)
    monkeypatch.delenv("BHASHINI_INFERENCE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        BhashiniAsrBackend().transcribe(b"", None)


def test_bhashini_tts_raises_when_uncredentialed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BHASHINI_USER_ID", raising=False)
    with pytest.raises(RuntimeError):
        BhashiniTtsBackend().speak("hi", "en")


def test_speech_to_text_falls_through_to_the_next_rung_when_bhashini_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _WorkingWhisper:
        def transcribe(self, audio, language_hint):
            return TranscriptionResult(transcript="is it safe today", confidence=0.9, rung="faster_whisper", detected_language="en")

    monkeypatch.setattr("orca.agents.voice._asr_backends", (BhashiniAsrBackend(), _WorkingWhisper()))
    result = speech_to_text(b"fake-audio-bytes")
    assert result.rung == "faster_whisper"
    assert result.transcript == "is it safe today"


def test_speech_to_text_returns_unavailable_rung_not_an_exception_when_every_rung_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AlwaysFails:
        def transcribe(self, audio, language_hint):
            raise RuntimeError("no signal")

    monkeypatch.setattr("orca.agents.voice._asr_backends", (_AlwaysFails(),))
    result = speech_to_text(b"fake-audio-bytes")
    assert result.rung == "unavailable"
    assert result.transcript == ""
    assert result.confidence == 0.0


def test_text_to_speech_returns_none_and_unavailable_when_every_rung_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AlwaysFails:
        def speak(self, text, language):
            raise RuntimeError("model not cached")

    monkeypatch.setattr("orca.agents.voice._tts_backends", (_AlwaysFails(),))
    audio, rung = text_to_speech("hello", "en")
    assert audio is None
    assert rung == "unavailable"


def test_low_confidence_threshold_is_a_real_fraction() -> None:
    assert 0.0 < LOW_CONFIDENCE_THRESHOLD < 1.0


@pytest.mark.skipif(not (_WHISPER_PRESENT and _MMS_EN_PRESENT), reason="faster-whisper / MMS-TTS models not downloaded on this machine")
def test_real_tts_then_asr_round_trip_produces_a_nonempty_transcript() -> None:
    audio, rung = text_to_speech("hello there, this is a test of the ORCA voice pipeline", "en")
    assert rung == "mms_tts"
    assert audio is not None and len(audio) > 100

    result = speech_to_text(audio, language_hint="en")
    assert result.rung == "faster_whisper"
    assert result.transcript.strip() != ""
    assert 0.0 <= result.confidence <= 1.0
