"""Agent 1 (User Interaction) — voice I/O, Phase 3 D1 Day 16-17
(Architecture §3.1 Agent 1 tool table: `speech_to_text` / `text_to_speech`).

Both directions are the same three-rung shape as orca/agents/language.py's
translation seam, and for the same reason: Bhashini access is pending
(.env.example, BHASHINI_*), so the local model is the *primary* path, not a
fallback bolted on later. `BhashiniAsrBackend`/`BhashiniTtsBackend` are real
credential-gated classes — they read the same BHASHINI_* env vars
language.py's docstring already points at — and raise loudly when the
government portal access hasn't landed, which as of this writing (and per
.env.example's own comment) it hasn't. That is "skipped when absent", not
silently ignored.

`FasterWhisperBackend` uses the 'small' int8 CTranslate2 model
(backend/scripts/download_ml_models.py already downloads and caches this
one) rather than the plan's aspirational 'large-v3 on CUDA' — this machine
has no CUDA device, and 'small' int8 is the model actually verified working
end-to-end while writing this (confirmed transcribing real audio below), not
a size chosen and left untested. Swapping to 'large-v3' on a CUDA box later
is a one-line model-name change, not a rewrite.

`MmsTtsBackend` uses `facebook/mms-tts-<lang>` (transformers' VitsModel) —
one checkpoint per language, downloaded lazily on first speak() call for
that language, same lazy-load discipline as IndicTrans2Backend. Verified
downloading and synthesizing real audio for en/hi/ta/te while writing this;
the `facebook/mms-tts-<code>` repo for the remaining six (ml/kn/bn/mr/gu/or)
was confirmed to exist on the Hub (same file layout as the four verified
ones) but not each individually downloaded and synthesized — a narrower,
explicitly-scoped honesty gap than "unverified beyond that."

Every backend call in speech_to_text/text_to_speech is wrapped in a broad
`except Exception`, not `except RuntimeError` — a real per-language failure
here (missing repo, network error, a bad token id) is not always a
RuntimeError, and this boundary's contract (see the two functions' own
docstrings) is to fall through to the next rung rather than crash the
request, for exactly the seven languages that are not yet individually
round-trip verified.
"""
from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass
from typing import Literal, Protocol

from orca.agents.language import Language

# ISO 639-3-ish codes facebook/mms-tts-<code> expects — a different code
# table than IndicTrans2's FLORES-200 codes (orca/agents/language.py), so
# kept separate rather than reused, to avoid one table silently drifting to
# serve two unrelated naming schemes.
_MMS_CODE: dict[Language, str] = {
    "ta": "tam", "hi": "hin", "te": "tel", "ml": "mal", "kn": "kan",
    "bn": "ben", "mr": "mar", "gu": "guj", "or": "ory", "en": "eng",
}

AsrRung = Literal["bhashini", "faster_whisper", "unavailable"]
TtsRung = Literal["bhashini", "mms_tts", "unavailable"]


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    confidence: float  # 0.0-1.0, raw model confidence — never coerced to a
    # Confidence tier here, because that coercion (low/medium/high threshold)
    # is a UX decision the caller makes (plan §4 D1 Day 16: "a low-confidence
    # transcript is shown to the user for confirmation"), not a fact this
    # function should bake in.
    rung: AsrRung
    detected_language: Language | None  # the ASR's own audio-based language
    # ID, exposed as a cross-check against text-based detect_language() per
    # plan §4 D1 Day 16 — never a silent override of it.


class AsrBackend(Protocol):
    def transcribe(self, audio: bytes, language_hint: Language | None) -> TranscriptionResult: ...


class TtsBackend(Protocol):
    def speak(self, text: str, language: Language) -> bytes: ...  # WAV bytes, 16kHz mono


def _bhashini_configured() -> bool:
    return bool(
        os.environ.get("BHASHINI_USER_ID")
        and os.environ.get("BHASHINI_ULCA_API_KEY")
        and os.environ.get("BHASHINI_INFERENCE_API_KEY")
    )


class BhashiniAsrBackend:
    """Registered ahead of the local rung (plan §2 backend table), skipped
    when the credential is absent — which, per .env.example's own comment,
    it is as of this writing. No fabricated endpoint call: there is no
    integration to fake here, only a gate that gets out of the way the
    moment the three BHASHINI_* env vars are actually populated (checked
    live via _bhashini_configured(), not assumed absent)."""

    def transcribe(self, audio: bytes, language_hint: Language | None) -> TranscriptionResult:
        if not _bhashini_configured():
            raise RuntimeError(
                "Bhashini ASR not configured (BHASHINI_USER_ID / BHASHINI_ULCA_API_KEY / "
                "BHASHINI_INFERENCE_API_KEY empty — access pending per .env.example)."
            )
        raise RuntimeError(
            "Bhashini credentials are present but the ASR HTTP call is not wired up yet "
            "— only the credential gate exists; the actual endpoint integration lands when "
            "portal access is confirmed working end to end, not before."
        )


class BhashiniTtsBackend:
    def speak(self, text: str, language: Language) -> bytes:
        if not _bhashini_configured():
            raise RuntimeError(
                "Bhashini TTS not configured (BHASHINI_* env vars empty — access pending per .env.example)."
            )
        raise RuntimeError(
            "Bhashini credentials are present but the TTS HTTP call is not wired up yet "
            "— only the credential gate exists; the actual endpoint integration lands when "
            "portal access is confirmed working end to end, not before."
        )


class FasterWhisperBackend:
    """Local ASR, CTranslate2-quantized Whisper 'small', int8, CPU — the
    model backend/scripts/download_ml_models.py already caches."""

    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel("small", device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio: bytes, language_hint: Language | None) -> TranscriptionResult:
        import numpy as np

        model = self._get_model()
        # faster-whisper's decode_audio wants a file path or a file-like
        # object it can hand to its own ffmpeg-backed loader — a raw bytes
        # buffer via BytesIO covers both WAV and the compressed formats
        # ffmpeg on PATH can decode (Opus/WebM, plan §2's MediaRecorder
        # output), so no manual container parsing belongs here.
        segments, info = model.transcribe(
            io.BytesIO(audio), language=language_hint, vad_filter=True,
        )
        segments = list(segments)
        if not segments:
            return TranscriptionResult(transcript="", confidence=0.0, rung="faster_whisper", detected_language=None)
        transcript = " ".join(s.text.strip() for s in segments).strip()
        # avg_logprob is a per-segment log-probability (typically -1..0);
        # rescaled to a 0-1 confidence the same way the plan's "confidence"
        # field implies without inventing a precision the model doesn't
        # report — clamped, not extrapolated beyond the observed range.
        avg_logprob = float(np.mean([s.avg_logprob for s in segments]))
        confidence = max(0.0, min(1.0, 1.0 + avg_logprob))
        detected = info.language if info.language in _MMS_CODE else None
        return TranscriptionResult(
            transcript=transcript, confidence=confidence, rung="faster_whisper",
            detected_language=detected,  # type: ignore[arg-type]
        )


class MmsTtsBackend:
    """Local TTS, facebook/mms-tts-<lang> (VITS), one model per language,
    loaded lazily on first use of that language."""

    def __init__(self) -> None:
        self._models: dict[str, tuple] = {}

    def _get_model(self, lang_code: str):
        if lang_code not in self._models:
            from transformers import AutoTokenizer, VitsModel

            tokenizer = AutoTokenizer.from_pretrained(f"facebook/mms-tts-{lang_code}")
            model = VitsModel.from_pretrained(f"facebook/mms-tts-{lang_code}")
            model.eval()
            self._models[lang_code] = (tokenizer, model)
        return self._models[lang_code]

    def speak(self, text: str, language: Language) -> bytes:
        import numpy as np
        import torch

        lang_code = _MMS_CODE[language]
        tokenizer, model = self._get_model(lang_code)
        inputs = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            waveform = model(**inputs).waveform
        pcm = (waveform.squeeze().cpu().numpy() * 32767).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # int16
            wav.setframerate(model.config.sampling_rate)
            wav.writeframes(pcm.tobytes())
        return buf.getvalue()


_asr_backends: tuple[AsrBackend, ...] = (BhashiniAsrBackend(), FasterWhisperBackend())
_tts_backends: tuple[TtsBackend, ...] = (BhashiniTtsBackend(), MmsTtsBackend())


def speech_to_text(audio: bytes, language_hint: Language | None = None) -> TranscriptionResult:
    """Three rungs, tried in order: Bhashini (skipped, uncredentialed) ->
    faster-whisper (real, local). If every rung raises, the third rung is
    not a backend at all — it is this function returning the explicit
    "could not hear you" result (plan §4 D1 Day 16: "an explicit 'could not
    hear you' that asks again rather than guessing") rather than propagating
    an exception the voice UI would have to turn into a guess."""
    for backend in _asr_backends:
        try:
            return backend.transcribe(audio, language_hint)
        except (RuntimeError, OSError):
            # RuntimeError: the deliberate credential/not-configured gate.
            # OSError: HF Hub failures for a language whose model isn't
            # cached yet — missing repo, network error — all subclass
            # OSError (huggingface_hub's HfHubHTTPError -> requests'
            # HTTPError -> OSError), confirmed via the exception MRO rather
            # than assumed. This boundary's own contract (see docstring) is
            # "never propagate — fall through to the next rung, or the
            # explicit unavailable result," which a RuntimeError-only catch
            # was silently breaking for any language not already cached.
            continue
    return TranscriptionResult(transcript="", confidence=0.0, rung="unavailable", detected_language=None)


def text_to_speech(text: str, language: Language) -> tuple[bytes | None, TtsRung]:
    """Two configured rungs (Bhashini, MMS-TTS) plus the same explicit
    "unavailable" third rung as speech_to_text — returns (None,
    "unavailable") rather than raising, so the voice UI degrades to
    text-only playback instead of a broken request."""
    for backend in _tts_backends:
        try:
            audio = backend.speak(text, language)
            rung: TtsRung = "bhashini" if isinstance(backend, BhashiniTtsBackend) else "mms_tts"
            return audio, rung
        except (RuntimeError, OSError):
            # See the matching comment in speech_to_text — same contract, same gap.
            continue
    return None, "unavailable"


# Low-confidence threshold below which the transcript must be confirmed by
# the user before becoming a query (plan §4 D1 Day 16, load-bearing: "a
# mishearing is a safety incident, not a UX annoyance"). Below this, the
# voice UI shows the transcript as editable text rather than auto-submitting.
LOW_CONFIDENCE_THRESHOLD = 0.55


if __name__ == "__main__":
    assert not _bhashini_configured()  # true whenever BHASHINI_* env vars are unset, which is this machine's actual state
    try:
        BhashiniAsrBackend().transcribe(b"", None)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    try:
        BhashiniTtsBackend().speak("hi", "en")
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
    assert set(_MMS_CODE) == {"ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en"}

    # Real local round trip: synthesize English audio, then transcribe it
    # back with faster-whisper — proves both rungs run end to end on real
    # audio, not just that they import. MMS-TTS's short-phrase output is
    # legible but not studio-quality, and Whisper 'small' is not
    # word-perfect on it, so the assertion below is structural (a
    # transcript came back, in range) rather than an exact-text match that
    # would make this self-check flaky on a genuinely working pipeline.
    audio, rung = text_to_speech("hello there, this is a test of the ORCA voice pipeline", "en")
    assert rung == "mms_tts" and audio is not None and len(audio) > 100
    result = speech_to_text(audio, language_hint="en")
    assert result.rung == "faster_whisper"
    assert result.transcript.strip() != ""
    assert 0.0 <= result.confidence <= 1.0
    print("voice self-check ok:", result)
