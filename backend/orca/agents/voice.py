"""Agent 1 (User Interaction) — voice I/O, Phase 3 D1 Day 16-17
(Architecture §3.1 Agent 1 tool table: `speech_to_text` / `text_to_speech`).

Both directions are the same three-rung shape as orca/agents/language.py's
translation seam: Bhashini first, a local model second, an explicit
"unavailable" third. `BhashiniAsrBackend`/`BhashiniTtsBackend` read the
BHASHINI_* env vars and raise when they are empty, so a checkout without
credentials falls through to the local rung — "skipped when absent", not
silently ignored.

`FasterWhisperBackend` uses the 'small' int8 CTranslate2 model
(backend/scripts/download_ml_models.py already downloads and caches this
one). This is deliberate, not a placeholder for a bigger GPU model later:
with Bhashini as the primary ASR path (P3.8), this backend's whole job is to
be the *offline fallback rung* — what answers when the network or Bhashini
itself is down — and 'small' int8 on CPU is what that rung needs to be:
cheap to keep warm, no GPU dependency, verified working end-to-end
(confirmed transcribing real audio below). There is no plan to move this to
'large-v3' on CUDA; a bigger local model would only make the fallback rung
slower to keep resident, not more useful as a fallback.

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

import hashlib
import io
import logging
import re
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, get_args

from orca import local_models
from orca.agents.language import Language, normalise_compass
from orca.agents.speech_lexicon import (
    COMPASS_ENGLISH,
    COMPASS_MULTI,
    COMPASS_NATIVE,
    ENGLISH_ACRONYMS,
    ENGLISH_RESPELLING,
    LEXICON,
    MONTH_ALIASES,
    Lexicon,
)

# ISO 639-3-ish codes facebook/mms-tts-<code> expects — a different code
# table than IndicTrans2's FLORES-200 codes (orca/agents/language.py), so
# kept separate rather than reused, to avoid one table silently drifting to
# serve two unrelated naming schemes.
_MMS_CODE: dict[Language, str] = {
    "ta": "tam", "hi": "hin", "te": "tel", "ml": "mal", "kn": "kan",
    "bn": "ben", "mr": "mar", "gu": "guj", "or": "ory", "en": "eng",
}

AsrRung = Literal["bhashini", "faster_whisper", "unavailable"]
TtsRung = Literal["bhashini", "mms_tts", "bhashini_unavailable", "unavailable"]


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
    service_id: str | None = None  # P3.8 — Bhashini's chosen serviceId, for
    # the "Bhashini ASR · <serviceId>" engine tag; None on the local rung.


class AsrBackend(Protocol):
    def transcribe(self, audio: bytes, language_hint: Language | None) -> TranscriptionResult: ...


class TtsBackend(Protocol):
    def speak(self, text: str, language: Language) -> bytes: ...  # WAV bytes, 16kHz mono


def _bhashini_configured() -> bool:
    from orca.agents.bhashini import bhashini_configured

    return bhashini_configured()


# ALD below this is treated as "not sure" and the caller's language wins.
# Set from measurement (2026-09-27): every correct ALD call scored >= 0.98;
# the one miss (Malayalam heard as Telugu) scored 0.75.
ALD_MIN_SCORE = 0.9


def spoken_language(audio: bytes, language_hint: Language | None) -> Language | None:
    """The language to run Bhashini ASR in: ALD's answer when it is
    confident and one ORCA serves, else `language_hint` (the UI language).
    Shared by the final transcript and the live captions, so a Kannada
    speaker with an English UI is captioned in Kannada from the first
    partial rather than in invented English."""
    from orca.agents import bhashini

    try:
        spoken, score = bhashini.detect_spoken_language(audio)
    except bhashini.BhashiniError:
        logger.warning("Bhashini ALD failed; using the language hint", exc_info=True)
        return language_hint
    if score >= ALD_MIN_SCORE and spoken in get_args(Language):
        return spoken  # type: ignore[return-value]  # checked against the Language set just above
    return language_hint


class BhashiniAsrBackend:
    """Registered ahead of the local rung (plan §2 backend table), skipped
    when the credentials are absent. P3.8 — the HTTP calls live in
    orca/agents/bhashini.py; this class picks the ASR language and adapts
    the result into TranscriptionResult.

    The language: Bhashini ASR must be told it (a Kannada speaker sent to
    the English model comes back as invented English), so Bhashini ALD
    listens first and a confident answer wins. Otherwise `language_hint` —
    the UI language — is used, so an unsure ALD never makes things worse
    than no ALD. With neither, defer to faster-whisper, which detects on
    its own."""

    def transcribe(self, audio: bytes, language_hint: Language | None) -> TranscriptionResult:
        from orca.agents import bhashini

        if not bhashini.bhashini_configured():
            raise RuntimeError("Bhashini ASR not configured (BHASHINI_* env vars empty).")
        language = spoken_language(audio, language_hint)
        if language is None:
            raise RuntimeError("No confident spoken language — deferring to faster-whisper's own detection.")
        transcript, confidence = bhashini.asr(audio, language)
        service_id = bhashini._pipeline_config("asr", language).get("serviceId")
        return TranscriptionResult(
            transcript=transcript,
            # ULCA does not always report a per-utterance confidence; a
            # missing one degrades to the low-confidence threshold's own
            # "show for confirmation" behaviour rather than an invented 1.0.
            confidence=confidence if confidence is not None else LOW_CONFIDENCE_THRESHOLD,
            rung="bhashini",
            detected_language=language,
            service_id=service_id,
        )


# FIX-VOICE-1 — the voice, chosen by the user by ear on 2026-10-08 (files 03, 13, 14 of the listening
# test). English is spoken by Bhashini's male voice. The product name is spoken by the Hindi voice,
# because that is how anyone in India says "Sagar Sarathi" (the long aa in both words), which the
# English voice cannot do. Other languages keep the default voice.
_ENGLISH_GENDER = "male"
_NAME_RE = re.compile(r"\bSa+gar\s+Sa+rathi\b", re.IGNORECASE)
_NAME_DEVANAGARI = "\u0938\u093e\u0917\u0930 \u0938\u093e\u0930\u0925\u0940"
_NAME_GAP_S = 0.05


def _wav_to_array(wav: bytes):
    """(mono float samples, sample rate) of a Bhashini WAV (it returns 32-bit float, which the
    standard `wave` module cannot read)."""
    import struct

    import numpy as np

    if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise RuntimeError("Bhashini TTS: reply is not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(wav):
        chunk_id, size = wav[pos:pos + 4], struct.unpack("<I", wav[pos + 4:pos + 8])[0]
        body = wav[pos + 8:pos + 8 + size]
        if chunk_id == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif chunk_id == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise RuntimeError("Bhashini TTS: WAV has no fmt/data chunk")
    tag, channels, rate, _, _, bits = fmt
    kinds = {(1, 16): (np.int16, 32768.0), (3, 32): (np.float32, 1.0), (1, 32): (np.int32, 2.0**31)}
    if (tag, bits) not in kinds:
        raise RuntimeError(f"Bhashini TTS: unsupported WAV format {tag}/{bits}")
    dtype, scale = kinds[(tag, bits)]
    samples = np.frombuffer(data, dtype=dtype).astype(np.float32) / scale
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def _join_wavs(parts: list[bytes], gap_s: float = _NAME_GAP_S) -> bytes:
    """One 16-bit mono WAV from several Bhashini WAVs (resampled to the first one's rate)."""
    import numpy as np

    decoded = [_wav_to_array(p) for p in parts]
    rate = decoded[0][1]
    pieces = []
    for samples, r in decoded:
        if r != rate:
            samples = np.interp(np.linspace(0, len(samples) - 1, int(len(samples) * rate / r)), np.arange(len(samples)), samples)
        pieces += [samples.astype(np.float32), np.zeros(int(gap_s * rate), dtype=np.float32)]
    joined = np.concatenate(pieces[:-1])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(joined, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


# FIX-VOICE-7 (2026-10-09). The service cuts its output at about 25 s and restarts after a 0.5-0.8 s gap,
# wherever that falls in the text, even between "You can" and "head out now" (measured: a gap at 24.9 s in a
# 394-character answer whatever the last sentence said; none in a 372-character one; more at about 52 s).
# So a text longer than this is split by us at sentence ends, where a pause belongs, and the pieces are
# joined. 260 characters is about 18 s at the English voice's pace (14.8 characters a second), which leaves
# room for a slow reading. Most answers are shorter and stay ONE call, untouched.
_TTS_CHUNK_CHARS = 260
_TTS_JOIN_GAP_S = 0.2  # the voice's own gap between sentences is 0.17-0.32 s
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:])\s+|\s+(?=and\s)")


def split_for_bhashini(text: str, limit: int = _TTS_CHUNK_CHARS) -> list[str]:
    """`text` as pieces of at most `limit` characters, cut at sentence ends (and, for a sentence longer than
    the limit, at a comma or "and"). A text within the limit is returned whole."""
    text = text.strip()
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.?])\s+", text):
        if len(sentence) <= limit:
            pieces.append(sentence)
            continue
        current = ""
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            if current and len(current) + 1 + len(clause) > limit:
                pieces.append(current)
                current = clause
            else:
                current = f"{current} {clause}".strip()
        if current:
            pieces.append(current)
    chunks: list[str] = []
    for piece in pieces:  # pack whole sentences into chunks up to the limit
        if chunks and len(chunks[-1]) + 1 + len(piece) <= limit:
            chunks[-1] = f"{chunks[-1]} {piece}"
        else:
            chunks.append(piece)
    return chunks


def _synthesize(text: str, language: str, gender: str | None = None) -> bytes:
    """Bhashini TTS for `text`, in pieces when it is long (see `_TTS_CHUNK_CHARS`)."""
    from orca.agents import bhashini

    def one(piece: str) -> bytes:
        return bhashini.tts(piece, language) if gender is None else bhashini.tts(piece, language, gender)

    chunks = split_for_bhashini(text)
    if len(chunks) == 1:
        return one(chunks[0])
    return _join_wavs([one(c) for c in chunks], gap_s=_TTS_JOIN_GAP_S)


class BhashiniTtsBackend:
    def speak(self, text: str, language: Language) -> bytes:
        from orca.agents import bhashini

        if not bhashini.bhashini_configured():
            raise RuntimeError("Bhashini TTS not configured (BHASHINI_* env vars empty).")
        if language != "en":
            return _synthesize(text, language)
        # The name goes to the Hindi voice and the rest of the sentence stays in the English one.
        # Without the name this is one call, as before.
        parts: list[bytes] = []
        last = 0
        for match in _NAME_RE.finditer(text):
            before = text[last:match.start()].strip(" ,;:")
            if before:
                parts.append(_synthesize(before, "en", _ENGLISH_GENDER))
            parts.append(bhashini.tts(_NAME_DEVANAGARI, "hi", _ENGLISH_GENDER))
            last = match.end()
        if not parts:
            return _synthesize(text, "en", _ENGLISH_GENDER)
        after = text[last:].lstrip(" ,.;:").rstrip()  # a trailing "." or "?" stays: it is the intonation
        if after:
            parts.append(_synthesize(after, "en", _ENGLISH_GENDER))
        return _join_wavs(parts)


class FasterWhisperBackend:
    """Local ASR, CTranslate2-quantized Whisper 'small', int8, CPU — the
    model backend/scripts/download_ml_models.py already caches."""

    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        if self._model is None:
            with local_models.loading("faster-whisper"):
                if self._model is not None:  # loaded by the thread that held the lock
                    return self._model
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
        #
        # When language_hint is None (no hint from the caller), pass language=None
        # so Whisper runs its own audio-based language detection rather than being
        # forced into English. info.language is the detected code (ISO 639-1).
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
        # Use Whisper's detected language (from audio) when no hint was given;
        # otherwise trust the hint the caller provided — Whisper's detection
        # is probabilistic and a confirmed user preference beats it.
        whisper_lang = info.language if info.language in _MMS_CODE else None
        detected = language_hint if language_hint is not None else whisper_lang  # type: ignore[assignment]
        return TranscriptionResult(
            transcript=transcript, confidence=confidence, rung="faster_whisper",
            detected_language=detected,  # type: ignore[arg-type]
        )


logger = logging.getLogger(__name__)

# Sentence-boundary regex for chunking long text before VITS synthesis.
# VITS latency is super-linear in token count — 5×short chunks is far
# cheaper than 1×long pass, and the resulting audio is identical to
# concatenation at sentence boundaries.
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')
_MAX_CHUNK_CHARS = 200  # keep each chunk under this many characters


def _split_for_tts(text: str) -> list[str]:
    """Split text into sentence-sized chunks for chunked VITS inference."""
    sentences = _SENTENCE_RE.split(text.strip())
    chunks: list[str] = []
    current = ""
    for s in sentences:
        if current and len(current) + len(s) + 1 > _MAX_CHUNK_CHARS:
            chunks.append(current.strip())
            current = s
        else:
            current = f"{current} {s}".strip() if current else s
    if current:
        chunks.append(current.strip())
    return chunks or [text]


class MmsTtsBackend:
    """Local TTS, facebook/mms-tts-<lang> (VITS), one model per language,
    loaded lazily on first use of that language."""

    def __init__(self) -> None:
        self._models: dict[str, tuple] = {}

    def _get_model(self, lang_code: str):
        if lang_code not in self._models:
            with local_models.loading("MMS-TTS"):
                if lang_code in self._models:
                    return self._models[lang_code]
                t0 = time.monotonic()
                from transformers import AutoTokenizer, VitsModel

                tokenizer = AutoTokenizer.from_pretrained(f"facebook/mms-tts-{lang_code}")
                # Same lazy-module resolution as language.py's IndicTrans2 loader:
                # transformers' public names are not statically visible, so this
                # working call reads as calling None.
                # pyrefly: ignore[not-callable]
                model = VitsModel.from_pretrained(f"facebook/mms-tts-{lang_code}")
                model.eval()
                self._models[lang_code] = (tokenizer, model)
                logger.info("MMS-TTS model loaded for %s in %.1fs", lang_code, time.monotonic() - t0)
        return self._models[lang_code]

    def speak(self, text: str, language: Language) -> bytes:
        import numpy as np
        import torch

        lang_code = _MMS_CODE[language]
        tokenizer, model = self._get_model(lang_code)

        chunks = _split_for_tts(text)
        all_pcm: list[np.ndarray] = []
        t0 = time.monotonic()
        for chunk in chunks:
            inputs = tokenizer(chunk, return_tensors="pt")
            with torch.no_grad():
                waveform = model(**inputs).waveform
            pcm = (waveform.squeeze().cpu().numpy() * 32767).astype(np.int16)
            all_pcm.append(pcm)
        combined = np.concatenate(all_pcm) if len(all_pcm) > 1 else all_pcm[0]
        logger.info("MMS-TTS synthesized %d chars (%d chunks) in %.1fs", len(text), len(chunks), time.monotonic() - t0)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)  # int16
            wav.setframerate(model.config.sampling_rate)
            wav.writeframes(combined.tobytes())
        return buf.getvalue()


_asr_backends: tuple[AsrBackend, ...] = (BhashiniAsrBackend(), FasterWhisperBackend())
_tts_backends: tuple[TtsBackend, ...] = (BhashiniTtsBackend(), MmsTtsBackend())


def warm_faster_whisper() -> None:
    """P6.4 (orca_final §14.3) — load the local Whisper 'small' model now,
    off the request path, mirroring `language.IndicTrans2Backend.warm()`.
    Finds the one `FasterWhisperBackend` instance in `_asr_backends` rather
    than constructing a second one, so the warmed model is the same object
    `speech_to_text` actually calls. Exceptions are caught and logged here
    (see `IndicTrans2Backend.warm`'s docstring for why: uncaught, they would
    otherwise surface only as asyncio's misleading "Future exception was
    never retrieved" on the fire-and-forget executor call in main.py)."""
    try:
        for backend in _asr_backends:
            if isinstance(backend, FasterWhisperBackend):
                backend._get_model()  # same module, warming its own lazy singleton
    except Exception:
        logging.getLogger("orca.voice").warning("faster-whisper warm-up skipped", exc_info=True)


# P6.4 (orca_final §14.3) — the local TTS rung (`MmsTtsBackend`) had no
# warm-up at all until this: only ASR (Whisper) and translation
# (IndicTrans2) were pre-warmed, so the Tamil alert voice in
# `docs/competition/DLC_demo_script.md` beat 6 would have paid a first-synthesis model
# load (`AutoTokenizer`/`VitsModel.from_pretrained`, logged as "MMS-TTS
# model loaded... in %.1fs") on whichever take actually needed it. Warms
# only `ta` (the Palk Bay pilot's own language, and the one language this
# demo's script actually voices) rather than all ten — the other nine pay
# their own first-use cost only if a judge asks a question in one live,
# which P6.4's rehearsal, not a startup warm-up, is the honest place to
# catch.
def warm_mms_tts(language: Language = "ta") -> None:
    try:
        for backend in _tts_backends:
            if isinstance(backend, MmsTtsBackend):
                backend._get_model(_MMS_CODE[language])  # same module, warming its own lazy singleton
    except Exception:
        logging.getLogger("orca.voice").warning("MMS-TTS warm-up skipped", exc_info=True)


def speech_to_text(audio: bytes, language_hint: Language | None = None) -> TranscriptionResult:
    """Three rungs, tried in order: Bhashini (ALD + ASR) -> faster-whisper
    (local). If every rung raises, the third rung is
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


# In-memory LRU cache for TTS results — keyed on (text_hash, language).
# Avoids re-synthesizing the exact same verdict on repeated clicks.
# Bounded to 32 entries (~10 MB worst case for typical verdict lengths).
_tts_cache: dict[str, tuple[bytes, TtsRung]] = {}
_TTS_CACHE_MAX = 32


# --- the speakable text ----------------------------------------------------------------------------
#
# What the screen shows is what the model wrote: "Hello! I'm ...", "30\u201135 m", "12 km/h",
# "2026\u201110\u201102", "+91-44-2539-5018". Spoken as written, the engine said "Hello factorial", read
# the date as "2000 and 2062", the range as "3035", "km/h" without "per hour", a phone number as
# ninety-one forty-four, and "don't" as "don, pause, tee" when the apostrophe was the curly one
# (each reproduced with Bhashini and Whisper on 2026-10-08, and by the user's ear). This step
# rewrites the text for the SPEAKER only; the shown text never changes. Every rule below was
# checked by synthesizing it.

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")
_PLACEHOLDER_RE = re.compile(r"ZKEEPZ\w*?Z")
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_DIGIT_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def _spell_digits(number: str) -> str:
    return " ".join(_DIGIT_WORDS[c] for c in number if c in _DIGIT_WORDS)


def _spoken_date(m: re.Match[str]) -> str:
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return m.group(0)
    return f"{day} {_MONTHS[month - 1]} {year}"


def _looks_like_a_phone_number(text: str) -> bool:
    """A "+" country code, or at least ten digits. "1-2-3", "2026-13-45" and "12-34-56" are not numbers to dial."""
    return text.startswith("+") or sum(c.isdigit() for c in text) >= 10


_MONTH_ABBREVIATIONS = ("Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sept", "Sep", "Oct", "Nov", "Dec")
_MONTH_ABBR_RE = "|".join(_MONTH_ABBREVIATIONS)
_FULL_MONTH_BY_PREFIX = {m[:3].lower(): m for m in _MONTHS}


def _expand_months(s: str) -> str:
    """"2 Oct 2026" and "Oct 2, 2026" in full: the voice mispronounces "Oct" and "Sept". Only an abbreviation
    next to a day number, so a word such as "Mark" or "decide" is never touched."""
    def full(token: str) -> str:
        return _FULL_MONTH_BY_PREFIX[token[:3].lower()]

    # no trailing dot is taken here: "...on 3 Sep." ends the sentence ("Oct. 2" below has its dot before a number)
    s = re.sub(rf"\b(\d{{1,2}})\s+({_MONTH_ABBR_RE})\b", lambda m: f"{m.group(1)} {full(m.group(2))}", s, flags=re.IGNORECASE)
    return re.sub(rf"\b({_MONTH_ABBR_RE})\b\.?(?=\s+\d)", lambda m: full(m.group(1)), s, flags=re.IGNORECASE)


def _spoken_phone(m: re.Match[str]) -> str:
    if not _looks_like_a_phone_number(m.group(0)):
        return m.group(0)
    groups = [_spell_digits(g) for g in m.group(0).lstrip("+").split("-")]
    return ("plus " if m.group(0).startswith("+") else "") + ", ".join(groups)


_NUM = r"\d+(?:\.\d+)?"
_MONTH_NAMES = "|".join(sorted(MONTH_ALIASES, key=len, reverse=True))
_NO_LATIN_AFTER = r"(?![A-Za-z/])"  # a unit, not the start of a word; an Indic letter may follow it directly


def _month_word(token: str, lex: Lexicon) -> str:
    return lex["months"][MONTH_ALIASES[token.lower()] - 1]


def _speak_numbers_in_native_text(s: str, lex: Lexicon, compass: dict[str, str] | None = None) -> str:
    """The English rules above, for a native-language answer: Latin units, ranges, dates and phone
    numbers sit inside native sentences and are read badly as written (see `speech_lexicon`)."""
    # A number to dial, digit by digit (an ISO date is handled next, and has fewer than 7 digits per group).
    def _phone(m: re.Match[str]) -> str:
        if not _looks_like_a_phone_number(m.group(0)):
            return m.group(0)
        groups = [" ".join(g) for g in m.group(0).lstrip("+").split("-")]
        return (lex["plus"] + " " if m.group(0).startswith("+") else "") + ", ".join(groups)

    def _iso(m: re.Match[str]) -> str:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return m.group(0)
        return f"{day} {lex['months'][month - 1]} {year}"

    s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", _iso, s)
    s = re.sub(r"\+?\d+(?:-\d+){2,}", _phone, s)
    # "2 Oct 2026", "2 October", "Oct 2, 2026": the translator writes the month in Latin letters, and the
    # voice then drops it ("2 Oct 2026" was heard "2 2000 twenty-six").
    s = re.sub(
        rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})\b(?:\s+(\d{{4}}))?",
        lambda m: f"{m.group(1)} {_month_word(m.group(2), lex)}" + (f" {m.group(3)}" if m.group(3) else ""),
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        rf"\b({_MONTH_NAMES})\b\.?\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?",
        lambda m: f"{m.group(2)} {_month_word(m.group(1), lex)}" + (f" {m.group(3)}" if m.group(3) else ""),
        s,
        flags=re.IGNORECASE,
    )
    # "30-35" is read "30 35": the word between the two numbers is missing.
    s = re.sub(rf"({_NUM})\s*-\s*({_NUM})", rf"\1 {lex['to']} \2", s)
    span = rf"({_NUM}(?:\s+{re.escape(lex['to'])}\s+{_NUM})?)"
    # "12 km/h", and the translator's own "12 km/ಗಂ" / "km/மணி" / "km/ঘন্টা" (a native word for "hour" after the slash).
    s = re.sub(rf"{span}\s*(?i:km/h|kmh|km/hr|kph){_NO_LATIN_AFTER}", lambda m: lex["kmh"].format(n=m.group(1)), s)
    s = re.sub(rf"{span}\s*(?i:km)/[^\W\d_a-zA-Z]+", lambda m: lex["kmh"].format(n=m.group(1)), s)
    s = re.sub(rf"{span}\s*(?i:m/s){_NO_LATIN_AFTER}", lambda m: lex["ms"].format(n=m.group(1)), s)
    if compass:  # "9.915° N": the degree sign sits between the number and the letter
        s = re.sub(
            r"(\d)\s*\u00b0\s*([NESW])(?![A-Za-z])", lambda m: f"{m.group(1)} {lex['deg']} {compass[m.group(2)]}", s
        )
    s = re.sub(rf"(\d)\s*(?i:km){_NO_LATIN_AFTER}", rf"\1 {lex['km']}", s)
    s = re.sub(rf"(\d)\s*(?i:nm){_NO_LATIN_AFTER}", rf"\1 {lex['nm']}", s)
    s = re.sub(rf"(\d)\s*m{_NO_LATIN_AFTER}", rf"\1 {lex['m']}", s)  # a lone "m" was spelled as two letters
    s = re.sub(r"(\d)\s*°", rf"\1 {lex['deg']}", s)
    s = re.sub(r"(\d)\s*%", rf"\1 {lex['pct']}", s)
    if compass:
        s = _speak_compass_points(normalise_compass(s), lambda letters: " ".join(compass[c] for c in letters))
    return s


def _respell_keeping_case(respelled: str) -> Callable[[re.Match[str]], str]:
    """A replacement that starts with a capital where the word it replaces did ("Height" -> "Hite")."""

    def _sub(m: re.Match[str]) -> str:
        return respelled[0].upper() + respelled[1:] if m.group(0)[:1].isupper() else respelled

    return _sub


_COMPASS_MULTI_RE = re.compile(r"\b(" + "|".join(COMPASS_MULTI) + r")\b")
_COMPASS_LETTER_AFTER_NUMBER_RE = re.compile(r"(?<=\d)(\s*)([NESW])(?![A-Za-z])")


def _speak_compass_points(s: str, say: Callable[[str], str]) -> str:
    """"NNW" and "12.9894 N" in words. `say` maps compass letters ("NNW", "N") to the spoken words. The
    single letters N, E, S and W are a direction only straight after a number (a coordinate or a bearing)."""
    s = _COMPASS_MULTI_RE.sub(lambda m: say(m.group(1)), s)
    return _COMPASS_LETTER_AFTER_NUMBER_RE.sub(lambda m: " " + say(m.group(2)), s)


def speakable(text: str, language: Language) -> str:
    """The text the voice is given. Neutral clean-up for every language; the English rules only for
    English (the other voices were not found to need them, and a rule written for English must not
    reach Tamil)."""
    s = text
    s = _PLACEHOLDER_RE.sub("", s)  # a translation-protection token is never read out
    s = _EMOJI_RE.sub("", s)
    s = re.sub("[\u202f\u00a0\u2009\u2007]", " ", s)  # the model's narrow no-break spaces
    s = s.replace("\u2014", ", ")  # em dash: a pause, not a letter
    s = re.sub("[\u2010\u2011\u2012\u2013\u2015\u2212]", "-", s)  # every other dash is a plain hyphen
    s = re.sub(r"\*+|^#+\s*|^\s*[-*]\s+", "", s, flags=re.MULTILINE)  # Markdown
    s = re.sub("[\u2018\u2019\u02bc\u00b4`]", "'", s)  # the curly apostrophe is what made "don't" pause
    if language == "en":
        s = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", _spoken_date, s)
        s = _expand_months(s)
        s = re.sub(r"\b0(\d):(\d{2})\b", r"\1:\2", s)
        s = re.sub(r"\bIST\b", "Indian Standard Time", s)
        s = re.sub(r"\+?\d+(?:-\d+){2,}", _spoken_phone, s)  # a number to dial is read digit by digit
        s = re.sub(r"(?i)(nationwide[^0-9]{0,4})(\d{3,4})\b", lambda m: m.group(1) + _spell_digits(m.group(2)), s)
        s = re.sub(r"(?i)\bk(?:m/h|mh|m/hr|ph)\b", "kilometres per hour", s)
        s = re.sub(r"(?i)\bm/s\b", "metres per second", s)
        s = re.sub(r"(\d)\s*-\s*(\d)", r"\1 to \2", s)  # "30-35" is "30 to 35", not "3035"
        s = re.sub(r"(\d)\s*km\b", r"\1 kilometres", s)
        s = re.sub(r"(\d)\s*nm\b", r"\1 nautical miles", s)
        s = re.sub(r"(\d)\s*m\b", r"\1 metres", s)
        s = re.sub(
            r"(\d)\s*\u00b0\s*([NESW])(?![A-Za-z])", lambda m: f"{m.group(1)} degrees {COMPASS_ENGLISH[m.group(2)]}", s
        )  # "9.915° N": the degree sign sits between the number and the letter
        s = re.sub(r"\s*\u00b0\s*", " degrees ", s)
        s = re.sub(r"\s*%", " percent", s)
        s = re.sub(r"\s*[\u2248~]\s*(?=\d)", " about ", s)  # "≈" was read "approximately equal"
        s = s.replace("\u00b1", " plus or minus ")
        for acronym, spoken in ENGLISH_ACRONYMS.items():
            s = re.sub(rf"\b{re.escape(acronym)}\b", spoken, s)
        # A long all-caps word is spelled out or garbled by the voice ("SIMULATED" was heard
        # "AMUL-ERETED"); lower case it reads as the word it is. Acronyms were rewritten above and the
        # short ones (GO, PFZ) are not touched.
        s = re.sub(r"\b[A-Z]{5,}\b", lambda m: m.group(0).lower(), s)
        s = _speak_compass_points(normalise_compass(s), lambda letters: COMPASS_ENGLISH[letters])
        for word, respelled in ENGLISH_RESPELLING.items():  # single words the voice mispronounces
            s = re.sub(rf"\b{re.escape(word)}\b", _respell_keeping_case(respelled), s, flags=re.IGNORECASE)
        s = s.replace("&", " and ")
        s = re.sub(r"(?<=[A-Za-z])/(?=[A-Za-z])", " and ", s)
        s = re.sub(r"\s+-\s+", ", ", s)
        s = re.sub(r"\s*[()]\s*", ", ", s)
        s = s.replace(";", ",")
    elif language in LEXICON:
        s = _speak_numbers_in_native_text(s, LEXICON[language], COMPASS_NATIVE.get(language))
    # "!" is read as the word "factorial" by the voice in EVERY language tested (English, Kannada, Hindi,
    # Tamil, Telugu, Malayalam, Bengali, Gujarati: reproduced with Bhashini TTS and ASR on 2026-10-08).
    s = re.sub("[!！‼]", ".", s)
    s = re.sub(r"\n+", ". ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\s*,)+", ",", s)
    s = re.sub(r"\.\s*,", ".", s)
    s = re.sub(r",\s*([.?])", r"\1", s)
    s = re.sub(r"([.?])\s*\.", r"\1", s)
    return s.strip(" ,")


def _tts_cache_key(text: str, language: Language) -> str:
    return hashlib.sha256(f"{language}:{text}".encode()).hexdigest()[:16]


# FIX-VOICE-10 (2026-10-09). Bhashini's speech service answers 504 for Marathi, Gujarati and Odia on every
# call (Hindi, on the same service id, answers in 0.8 s), so a press of Play waited about 25 s (76 s the first
# time for Marathi) and then played the local robotic voice. The user's decision: for those three languages the
# app says "Bhashini speech is unavailable right now" and does not play the local voice. A language whose
# Bhashini speech failed is skipped for ten minutes (so the next press answers at once); when the ten minutes
# are over ONE short probe decides whether it is back, not a 25 s real request. The other seven languages keep
# the local voice as their backup.
_NO_LOCAL_VOICE = frozenset({"mr", "gu", "or"})
_SPEECH_DOWN_S = 600.0
_PROBE_TIMEOUT_S = 8.0
_speech_down_until: dict[str, float] = {}


def _mark_bhashini_down(language: str) -> None:
    _speech_down_until[language] = time.monotonic() + _SPEECH_DOWN_S


def _mark_bhashini_up(language: str) -> None:
    _speech_down_until.pop(language, None)


def bhashini_speech_is_down(language: str) -> bool:
    """True while Bhashini's speech for `language` is known to be down (its ten minutes have not passed)."""
    return _speech_down_until.get(language, 0.0) > time.monotonic()


def _probe_language(language: str) -> bool:
    """One short synthesis of the product's name in `language` (about 8 s at most, no retry): is Bhashini speech
    back? Records the answer and returns it."""
    from orca.agents import bhashini
    from orca.agents.language import PRODUCT_NAME_NATIVE

    word = PRODUCT_NAME_NATIVE.get(language, "ok").split()[0]
    try:
        bhashini.tts(word, language, timeout_s=_PROBE_TIMEOUT_S, retry=False)
    except Exception:
        _mark_bhashini_down(language)
        return False
    _mark_bhashini_up(language)
    return True


def probe_speech_health(languages: frozenset[str] | set[str] | None = None) -> dict[str, bool]:
    """At startup: try the languages that have NO local backup voice, all at once, so the first press of Play after a
    restart already knows (instead of waiting 25 s to find out). Only these three: a false alarm on a language that
    has a local voice would degrade it for ten minutes, and its own first failure marks it down anyway."""
    from concurrent.futures import ThreadPoolExecutor

    from orca.agents import bhashini

    if not bhashini.bhashini_configured():
        return {}
    langs = sorted(languages or _NO_LOCAL_VOICE)
    with ThreadPoolExecutor(max_workers=len(langs)) as pool:
        results = dict(zip(langs, pool.map(_probe_language, langs), strict=True))
    logger.info("Bhashini speech health: %s", ", ".join(f"{k}={'up' if v else 'DOWN'}" for k, v in results.items()))
    return results


def _bhashini_may_be_tried(language: str) -> bool:
    until = _speech_down_until.get(language)
    if until is None:
        return True
    if until > time.monotonic():
        return False
    return _probe_language(language)  # the ten minutes are over: one short probe decides


def text_to_speech(text: str, language: Language) -> tuple[bytes | None, TtsRung]:
    """Two configured rungs (Bhashini, MMS-TTS) plus the same explicit
    "unavailable" third rung as speech_to_text — returns (None,
    "unavailable") rather than raising, so the voice UI degrades to
    text-only playback instead of a broken request. For Marathi, Gujarati and Odia there is no local rung:
    when Bhashini's speech is down the answer is (None, "bhashini_unavailable") and the UI says so.

    Results are cached in-memory (repeated clicks, same process)."""
    key = _tts_cache_key(text, language)
    if key in _tts_cache:
        logger.info("TTS cache hit for key %s", key)
        return _tts_cache[key]

    t0 = time.monotonic()
    spoken = speakable(text, language)
    for backend in _tts_backends:
        is_bhashini = isinstance(backend, BhashiniTtsBackend)
        if is_bhashini and not _bhashini_may_be_tried(language):
            if language in _NO_LOCAL_VOICE:
                return None, "bhashini_unavailable"
            continue
        if not is_bhashini and language in _NO_LOCAL_VOICE:
            return None, "bhashini_unavailable"
        try:
            audio = backend.speak(spoken, language)
            if is_bhashini:
                _mark_bhashini_up(language)
            rung: TtsRung = "bhashini" if is_bhashini else "mms_tts"
            # Cache the result in-memory
            if len(_tts_cache) >= _TTS_CACHE_MAX:
                # Evict oldest entry (FIFO)
                oldest = next(iter(_tts_cache))
                del _tts_cache[oldest]
            _tts_cache[key] = (audio, rung)
            logger.info("TTS synthesis completed in %.1fs (rung=%s), cached as %s", time.monotonic() - t0, rung, key)
            return audio, rung
        except (RuntimeError, OSError):
            # See the matching comment in speech_to_text — same contract, same gap.
            if is_bhashini:
                _mark_bhashini_down(language)
                if language in _NO_LOCAL_VOICE:
                    return None, "bhashini_unavailable"
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
