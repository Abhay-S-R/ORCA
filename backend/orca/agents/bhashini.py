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

`_PIPELINE_ID` is the public default pipeline every ULCA integration guide
uses — not a secret, unlike the three `BHASHINI_*` credentials, which stay
in `.env.example` as empty placeholders until portal access is confirmed
working end to end (P3.8's own Done-when: a measured latency table, 20
recorded clips per language, is what "working" means here, not "the code
compiles" — that verification is BLOCKED on the credentials, not on this
module).

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

# "Every Bhashini call gets the 3 s safety-path timeout" (plan P3.8) — a hung
# government portal must never hold a query open indefinitely, safety path
# or not.
TIMEOUT_S = 3.0

TaskType = Literal["asr", "translation", "tts", "transliteration", "txt-lang-detection"]


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


def _inference(config: dict[str, Any], pipeline_task: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
    headers = {
        config["inference_api_key"]["name"]: config["inference_api_key"]["value"],
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {"pipelineTasks": [pipeline_task], "inputData": input_data}
    try:
        resp = requests.post(config["callback_url"], headers=headers, json=body, timeout=TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise BhashiniError(f"Bhashini inference call failed: {exc}") from exc


def asr(audio: bytes, source_lang: str) -> tuple[str, float | None]:
    """Voice in: ASR. Returns (transcript, confidence-if-reported)."""
    config = _pipeline_config("asr", source_lang)
    task = {"taskType": "asr", "config": {"language": {"sourceLanguage": source_lang}, "serviceId": config["serviceId"]}}
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


def tts(text: str, target_lang: str, gender: str = "female") -> bytes:
    """Voice out: TTS. Returns audio bytes (ULCA's default WAV format).

    `gender` is REQUIRED by the Dhruva inference endpoint, not documented as
    such anywhere the config call itself surfaces — confirmed live: the
    identical request without it returns a bare `500 Internal Server Error`
    (no JSON body to diagnose from), and succeeds the moment `gender` is
    added. "female" is not a claim about the speaker, just this function's
    default voice; a caller that cares picks "male" explicitly."""
    config = _pipeline_config("tts", target_lang)
    task = {
        "taskType": "tts",
        "config": {"language": {"sourceLanguage": target_lang}, "serviceId": config["serviceId"], "gender": gender},
    }
    payload = {"input": [{"source": text}]}
    data = _inference(config, task, payload)
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


def detect_language(text: str) -> str:
    """TLD — text language detection. Called only when the local
    Unicode-block detector (`language.detect_language`) is ambiguous: Latin
    script with low English vocabulary coverage (P3.5/P3.8).

    NOT CONFIRMED LIVE, unlike every other function in this module — verified
    2026-09-23 against real credentials: `asr`, `translation`, `tts` and
    `transliteration` all round-trip correctly through `_PIPELINE_ID`, but
    that pipeline's `getModelsPipeline` config call rejects `taskType`
    `txt-lang-detection` with `400 TaskType is not valid !`, even though
    `POST /ulca/apis/v0/model/search {"task": "txt-lang-detection"}` shows a
    real model for it (Bhashini-IIITH Textual Language Detection). That
    model's own `inferenceEndPoint.callbackUrl` is empty in the search
    result, so it is reachable through some other integration this default
    pipeline does not expose — not chased further here, since the caller
    (`language.detect_language_with_bhashini`) already treats any exception
    from this function as "fall back to the script-only result," which is
    exactly what happens today. Fix forward: find the right `pipelineId` (or
    direct-model call) for this task before trusting a return value from it."""
    config = _pipeline_config("txt-lang-detection", "auto")
    task = {"taskType": "txt-lang-detection", "config": {"serviceId": config["serviceId"]}}
    payload = {"input": [{"source": text}]}
    data = _inference(config, task, payload)
    try:
        return data["pipelineResponse"][0]["output"][0]["langPrediction"][0]["langCode"]
    except (KeyError, IndexError) as exc:
        raise BhashiniError(f"Bhashini language detection: unexpected response shape: {data}") from exc


if __name__ == "__main__":
    # This module never calls load_dotenv itself (orca/db/engine.py and
    # orca/llm/tiers.py already do, at import time, for the whole process —
    # see their own module docstrings); running this file directly with no
    # other orca import ahead of it sees whatever the shell's environment
    # already has, which is why every other self-check in this package that
    # depends on .env imports orca.db.engine first, not because it needs a
    # database.
    from orca.db import engine as _  # noqa: F401  (triggers load_dotenv)

    if bhashini_configured():
        # Live round-trip, all four confirmed-working services (2026-09-23):
        # translation, TTS, ASR-on-that-TTS-audio, and transliteration.
        # txt-lang-detection is excluded — see detect_language's own
        # docstring for why it is not yet live even with real credentials.
        translated = nmt("Is it safe to go to sea today?", "en", "ta")
        assert translated and translated != "Is it safe to go to sea today?"
        audio = tts("Is it safe to go to sea today?", "en")
        assert len(audio) > 1000
        transcript, _confidence = asr(audio, "en")
        assert "safe" in transcript.lower()
        romanized = transliterate(translated, "ta", "en")
        assert romanized and romanized.isascii()
        print(f"bhashini self-check ok (LIVE): nmt={translated!r} asr_roundtrip={transcript!r} translit={romanized!r}")
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
