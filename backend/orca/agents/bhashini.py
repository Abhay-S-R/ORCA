"""Bhashini ULCA API client (P3.8, orca_final §14.1).

Real HTTP wiring behind the credential gate `BhashiniAsrBackend` /
`BhashiniTtsBackend` (orca/agents/voice.py) already declared as stubs, plus
the NMT/Transliteration/TLD services `orca/agents/language.py` and
`orca/channels/renderers.py` need. One client, one config cache, one
timeout — every other file calls through here rather than growing its own
`requests.post()`.

Contract: MeitY's ULCA two-step pipeline (confirmed live against the real
`getModelsPipeline` endpoint while writing this — it returns
`400 BAD_REQUEST: Error in fetching ulcaApiKey` for a well-formed request
with a fake key, not a malformed-payload error, which is what validates the
request shape below without needing a real credential):

  1. POST `_CONFIG_URL` with `{userID, ulcaApiKey}` headers and a
     `{pipelineTasks, pipelineRequestConfig: {pipelineId}}` body ->
     a `pipelineInferenceAPIEndPoint` (`callbackUrl` + `inferenceApiKey`)
     plus, per task, which `serviceId`/`modelId` Bhashini has selected for
     that language pair. Cached per (task_type, source, target) for the
     life of the process — a repeat config round-trip ahead of every
     inference call would spend the whole 3s safety timeout on bookkeeping
     alone.
  2. POST `callback_url` with the `inferenceApiKey` header and a
     `{pipelineTasks: [...with serviceId...], inputData}` body -> the
     actual ASR/NMT/TTS/Transliteration/TLD result.

`_PIPELINE_ID` is the "Initial Pipeline Models" pipeline from Bhashini's
docs — not a secret. Its config call hands out only asr / translation /
transliteration / tts; every other taskType is `400 TaskType is not valid !`.

Language detection (text and audio) is not in any pipeline: the docs call it
straight on the compute endpoint with a documented `serviceId`
(`_TLD_SERVICE_ID`, `_ALD_SERVICE_ID`). The config call's `inferenceApiKey`
is `BHASHINI_INFERENCE_API_KEY` itself (confirmed live 2026-09-27), so those
two calls use it directly with no config round trip.

The three credentials, and where each goes:
  BHASHINI_USER_ID + BHASHINI_ULCA_API_KEY -> `userID` / `ulcaApiKey`
      headers on the config call only.
  BHASHINI_INFERENCE_API_KEY -> `Authorization` on every compute call.

Every function here raises `BhashiniError` (a `RuntimeError` subclass) on
any failure — not configured, unreachable, timed out, or an unexpected
response shape — so every caller's existing `except (RuntimeError, OSError):
continue` rung-fallback pattern (voice.py, language.py) catches it with no
change to that pattern.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Literal

import requests

logger = logging.getLogger(__name__)

_CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
_PIPELINE_ID = "64392f96daac500b55c543cd"  # MeitY's public default pipeline
_COMPUTE_URL = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
# Service IDs from the docs' "Available Models for usage" page. Both were
# measured 2026-09-27: IndicLID (23 languages) read romanized Tamil and Hindi
# correctly; IIT Mandi's ALD got ta/kn/hi/bn/en right on synthesized speech
# and was only unsure (0.75) on the Malayalam clip it missed, where the
# other listed ALD (`bhashini/ald`) was wrong at 0.999 — hence this one.
_TLD_SERVICE_ID = "bhashini/indic-lang-detection-all"
_ALD_SERVICE_ID = "bhashini/iitmandi/audio-lang-detection/gpu"

# "Every Bhashini call gets the 3 s safety-path timeout" (plan P3.8) — a hung
# government portal must never hold a query open indefinitely, safety path
# or not.
TIMEOUT_S = 3.0
# Speech synthesis of a whole answer takes longer than a lookup or a translation, and a 3 s limit
# was dropping it to the local robotic voice, which is then cached for that text (FIX-VOICE-1).
TTS_TIMEOUT_S = 12.0

TaskType = Literal["asr", "translation", "tts", "transliteration"]


def bhashini_configured() -> bool:
    return bool(
        os.environ.get("BHASHINI_USER_ID")
        and os.environ.get("BHASHINI_ULCA_API_KEY")
        and os.environ.get("BHASHINI_INFERENCE_API_KEY")
    )


class BhashiniError(RuntimeError):
    """One exception type for every Bhashini failure, so callers do not need
    a second except clause alongside the credential-gate RuntimeError the
    stub classes already raise."""


_config_cache: dict[tuple[str, str, str | None], dict[str, Any]] = {}


def _ulca_config_headers() -> dict[str, str]:
    return {
        "userID": os.environ["BHASHINI_USER_ID"],
        "ulcaApiKey": os.environ["BHASHINI_ULCA_API_KEY"],
        "Content-Type": "application/json",
    }


def _pipeline_config(task_type: TaskType, source_lang: str, target_lang: str | None = None) -> dict[str, Any]:
    """Step 1 of the ULCA contract, cached per language pair."""
    key = (task_type, source_lang, target_lang)
    cached = _config_cache.get(key)
    if cached is not None:
        return cached
    if not bhashini_configured():
        raise BhashiniError(
            "Bhashini not configured (BHASHINI_USER_ID / BHASHINI_ULCA_API_KEY / "
            "BHASHINI_INFERENCE_API_KEY empty — access pending per .env.example)."
        )
    language: dict[str, str] = {"sourceLanguage": source_lang}
    if target_lang is not None:
        language["targetLanguage"] = target_lang
    body: dict[str, Any] = {
        "pipelineTasks": [{"taskType": task_type, "config": {"language": language}}],
        "pipelineRequestConfig": {"pipelineId": _PIPELINE_ID},
    }
    try:
        resp = requests.post(_CONFIG_URL, headers=_ulca_config_headers(), json=body, timeout=TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise BhashiniError(f"Bhashini pipeline config failed: {exc}") from exc
    try:
        task_config = data["pipelineResponseConfig"][0]["config"][0]
        endpoint = data["pipelineInferenceAPIEndPoint"]
        resolved = {
            "serviceId": task_config["serviceId"],
            "callback_url": endpoint["callbackUrl"],
            "inference_api_key": {
                "name": endpoint["inferenceApiKey"]["name"],
                "value": endpoint["inferenceApiKey"]["value"],
            },
        }
    except (KeyError, IndexError) as exc:
        raise BhashiniError(f"Bhashini pipeline config: unexpected response shape: {data}") from exc
    _config_cache[key] = resolved
    return resolved


def _inference(
    config: dict[str, Any], pipeline_task: dict[str, Any], input_data: dict[str, Any], timeout_s: float | None = None,
) -> dict[str, Any]:
    headers = {
        config["inference_api_key"]["name"]: config["inference_api_key"]["value"],
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {"pipelineTasks": [pipeline_task], "inputData": input_data}
    try:
        resp = requests.post(config["callback_url"], headers=headers, json=body, timeout=timeout_s or TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise BhashiniError(f"Bhashini inference call failed: {exc}") from exc


def _direct_config() -> dict[str, Any]:
    """Compute-call target for the service-ID-only tasks (TLD, ALD), in the
    same shape `_pipeline_config` returns so `_inference` serves both."""
    if not bhashini_configured():
        raise BhashiniError("Bhashini not configured (BHASHINI_* env vars empty).")
    return {
        "callback_url": _COMPUTE_URL,
        "inference_api_key": {"name": "Authorization", "value": os.environ["BHASHINI_INFERENCE_API_KEY"]},
    }


def _audio_format(audio: bytes) -> str:
    # Dhruva returns a bare 500 when `audioFormat` is omitted for anything but
    # WAV — confirmed live 2026-09-23: the browser's MediaRecorder WebM/Opus
    # failed on every call until declared. RIFF is our own TTS output and the
    # test fixtures; everything else is the browser's recording.
    # ponytail: WAV/WebM only — Safari's MP4 recording still 500s and falls
    # through to the local rung; sniff `ftyp` here if Safari voice matters.
    return "wav" if audio[:4] == b"RIFF" else "webm"


def asr(audio: bytes, source_lang: str, *, clean: bool = True) -> tuple[str, float | None]:
    """Voice in: ASR. Returns (transcript, confidence-if-reported).

    `clean` runs Bhashini's VAD + denoiser before recognition and ITN +
    punctuation after it (inline pre/post-processors on the ASR task — the
    default pipeline rejects them as standalone taskTypes). Live partials pass
    `clean=False`: VAD trims the half-spoken last word of a mid-sentence
    clip, and the processors add ~0.5-1 s a live caption cannot afford."""
    config = _pipeline_config("asr", source_lang)
    asr_config: dict[str, Any] = {
        "language": {"sourceLanguage": source_lang},
        "serviceId": config["serviceId"],
        "audioFormat": _audio_format(audio),
    }
    if clean:
        asr_config["preProcessors"] = ["vad", "denoiser"]
        asr_config["postProcessors"] = ["itn", "punctuation"]
    task = {"taskType": "asr", "config": asr_config}
    payload = {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]}
    data = _inference(config, task, payload)
    try:
        output = data["pipelineResponse"][0]["output"][0]
        return output["source"], output.get("confidence")
    except (KeyError, IndexError) as exc:
        raise BhashiniError(f"Bhashini ASR: unexpected response shape: {data}") from exc


def nmt(text: str, source_lang: str, target_lang: str) -> str:
    """Text translation — the NMT leg of both voice-in (post-ASR) and
    text-in, and the rung `language.py`'s `_translate_with_rung` tries
    before the local IndicTrans2 fallback."""
    if source_lang == target_lang:
        return text
    config = _pipeline_config("translation", source_lang, target_lang)
    task = {
        "taskType": "translation",
        "config": {
            "language": {"sourceLanguage": source_lang, "targetLanguage": target_lang},
            "serviceId": config["serviceId"],
        },
    }
    payload = {"input": [{"source": text}]}
    data = _inference(config, task, payload)
    try:
        return data["pipelineResponse"][0]["output"][0]["target"]
    except (KeyError, IndexError) as exc:
        raise BhashiniError(f"Bhashini NMT: unexpected response shape: {data}") from exc


def tts(
    text: str, target_lang: str, gender: str = "female", *, timeout_s: float | None = None, retry: bool = True,
) -> bytes:
    """Voice out: TTS. Returns audio bytes (ULCA's default WAV format).

    `gender` is REQUIRED by the Dhruva inference endpoint, not documented as
    such anywhere the config call itself surfaces — confirmed live: the
    identical request without it returns a bare `500 Internal Server Error`
    (no JSON body to diagnose from), and succeeds the moment `gender` is
    added. "female" is not a claim about the speaker, just this function's
    default voice; a caller that cares picks "male" explicitly.

    `text-normalization` (the docs' TTS pre-processor) spells out numbers,
    units and times before synthesis. Measured by round-tripping the audio
    through ASR: English "wind 18 km/h" came back as "Vain 18K image" without
    it and "wind 18 kmh" with it; ta/hi were unchanged; no added latency."""
    config = _pipeline_config("tts", target_lang)
    task = {
        "taskType": "tts",
        "config": {
            "language": {"sourceLanguage": target_lang},
            "serviceId": config["serviceId"],
            "gender": gender,
            "preProcessors": ["text-normalization"],
        },
    }
    payload = {"input": [{"source": text}]}
    limit = timeout_s or TTS_TIMEOUT_S
    try:
        data = _inference(config, task, payload, timeout_s=limit)
    except BhashiniError:
        if not retry:  # a health probe wants the answer once, quickly
            raise
        # One more try before the caller falls to the local voice: a timeout or a 5xx from the
        # service is usually gone a second later, and the local voice would be cached for this text.
        data = _inference(config, task, payload, timeout_s=limit)
    try:
        b64 = data["pipelineResponse"][0]["audio"][0]["audioContent"]
        return base64.b64decode(b64)
    except (KeyError, IndexError) as exc:
        raise BhashiniError(f"Bhashini TTS: unexpected response shape: {data}") from exc


def transliterate(text: str, source_lang: str, target_lang: str) -> str:
    """Script transliteration — NOT translation: same language, a different
    script (e.g. Tamil script -> Latin script romanization). P3.5 uses this
    on the input side (romanized-Indic detection) and P3.11 on the output
    side (a romanized SMS variant for handsets with poor Indic font
    rendering)."""
    config = _pipeline_config("transliteration", source_lang, target_lang)
    task = {
        "taskType": "transliteration",
        "config": {
            "language": {"sourceLanguage": source_lang, "targetLanguage": target_lang},
            "serviceId": config["serviceId"],
        },
    }
    payload = {"input": [{"source": text}]}
    data = _inference(config, task, payload)
    try:
        # Unlike NMT's `target` (a plain string), transliteration's `target`
        # is a list of candidate romanizations — confirmed live. The first
        # is the service's top pick; this function promises one string, not
        # a ranked list a caller would have to know to index into.
        return data["pipelineResponse"][0]["output"][0]["target"][0]
    except (KeyError, IndexError) as exc:
        raise BhashiniError(f"Bhashini transliteration: unexpected response shape: {data}") from exc


def _lang_prediction(data: dict[str, Any], what: str) -> tuple[str, float]:
    try:
        top = data["pipelineResponse"][0]["output"][0]["langPrediction"][0]
        return top["langCode"], float(top["langScore"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise BhashiniError(f"Bhashini {what}: unexpected response shape: {data}") from exc


def detect_language(text: str) -> str:
    """TLD — text language detection. Called only when the local
    Unicode-block detector (`language.detect_language`) is ambiguous: Latin
    script with low English vocabulary coverage (P3.5/P3.8), e.g. romanized
    Tamil "naalai kadalukku pogalama" -> "ta" (measured, score 1.0)."""
    task = {"taskType": "txt-lang-detection", "config": {"serviceId": _TLD_SERVICE_ID}}
    data = _inference(_direct_config(), task, {"input": [{"source": text}]})
    return _lang_prediction(data, "language detection")[0]


def detect_spoken_language(audio: bytes) -> tuple[str, float]:
    """ALD — which language is being spoken in `audio`. Returns
    (language code, score 0-1). `audioFormat` is not in the docs' ALD payload
    but is required for anything other than WAV, exactly as for ASR: the
    browser's WebM/Opus recording is a bare 500 without it (measured)."""
    task = {
        "taskType": "audio-lang-detection",
        "config": {"serviceId": _ALD_SERVICE_ID, "audioFormat": _audio_format(audio)},
    }
    data = _inference(_direct_config(), task, {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]})
    return _lang_prediction(data, "audio language detection")


if __name__ == "__main__":
    # This module never calls load_dotenv itself (orca/db/engine.py and
    # orca/llm/tiers.py already do, at import time, for the whole process —
    # see their own module docstrings); running this file directly with no
    # other orca import ahead of it sees whatever the shell's environment
    # already has, which is why every other self-check in this package that
    # depends on .env imports orca.db.engine first, not because it needs a
    # database.
    from orca.db import engine as _  # noqa: F401  (triggers load_dotenv)

    assert _audio_format(b"RIFF....WAVE") == "wav" and _audio_format(bytes.fromhex("1a45dfa3")) == "webm"
    if bhashini_configured():
        # Live round-trip of every service ORCA uses: translation, TTS,
        # ASR-on-that-TTS-audio, transliteration, and both detectors.
        translated = nmt("Is it safe to go to sea today?", "en", "ta")
        assert translated and translated != "Is it safe to go to sea today?"
        audio = tts("Is it safe to go to sea today?", "en")
        assert len(audio) > 1000
        transcript, _confidence = asr(audio, "en")
        assert "safe" in transcript.lower()
        romanized = transliterate(translated, "ta", "en")
        assert romanized and romanized.isascii()
        assert detect_language("naalai kadalukku pogalama") == "ta"
        spoken, score = detect_spoken_language(tts(translated, "ta"))
        assert spoken == "ta" and score > 0.9, (spoken, score)
        print(f"bhashini self-check ok (LIVE): nmt={translated!r} asr_roundtrip={transcript!r} translit={romanized!r} ald=({spoken}, {score:.3f})")
    else:
        try:
            nmt("hello", "en", "ta")
            raise AssertionError("expected BhashiniError with no credentials configured")
        except BhashiniError:
            pass
        print(
            "bhashini self-check ok (credential gate only — BHASHINI_USER_ID / "
            "BHASHINI_ULCA_API_KEY / BHASHINI_INFERENCE_API_KEY are not set in this "
            "environment, so only the not-configured gate was exercised)."
        )
