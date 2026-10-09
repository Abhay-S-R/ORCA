"""Voice endpoints — plan §4 D1 Day 16-17: `POST /voice/transcribe` and
`POST /voice/speak`, thin HTTP wrappers over orca/agents/voice.py's
speech_to_text / text_to_speech. Neither touches ORCAState or the graph —
voice is a pre/post step around the same `/query` text pipeline every other
channel already uses, not a parallel graph.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal, get_args

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from orca.agents.distress import detect_distress_signal
from orca.agents.language import Language
from orca.agents.voice import (
    LOW_CONFIDENCE_THRESHOLD,
    speech_to_text,
    spoken_language,
    text_to_speech,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])
_VALID_LANGUAGES = set(get_args(Language))


class TranscribeResponse(BaseModel):
    transcript: str
    confidence: float
    rung: Literal["bhashini", "faster_whisper", "unavailable"]
    detected_language: str | None
    needs_confirmation: bool  # plan §4 D1 Day 16: shown to the user for
    # confirmation before becoming a query whenever confidence is low —
    # computed here once so every client applies the same threshold rather
    # than each one guessing its own.
    engine: str | None = None  # P3.8 — "Bhashini ASR · <serviceId>" when
    # that rung served; None on the local (faster-whisper) rung.
    possible_distress: bool = False  # P3.7 — a low-confidence transcript
    # that still matched a distress/medical/romanized pattern routes to
    # "Did you mean SOS?" rather than the generic low-confidence edit box:
    # a mishearing here is a safety incident, not a UX annoyance.


def _coerce_language_hint(value: str | None) -> Language | None:
    return value if value in _VALID_LANGUAGES else None  # type: ignore[return-value]


def _partial_transcript(blob: bytes, language: Language | None) -> TranscribeResponse:
    """Live caption while the user is still speaking — Bhashini only, no
    VAD/denoiser/punctuation, and no local fallback: faster-whisper takes
    ~8 s on CPU, so a partial from it would land after the user had stopped
    talking. An empty caption is the honest result when Bhashini is down;
    the final (non-partial) call on stop still walks every rung."""
    from orca.agents import bhashini

    try:
        language = spoken_language(blob, language)
        if language is None:
            raise bhashini.BhashiniError("partial ASR needs an explicit language")
        transcript, _confidence = bhashini.asr(blob, language, clean=False)
    except bhashini.BhashiniError:
        return TranscribeResponse(transcript="", confidence=0.0, rung="unavailable", detected_language=None, needs_confirmation=True)
    return TranscribeResponse(
        transcript=transcript, confidence=LOW_CONFIDENCE_THRESHOLD, rung="bhashini",
        detected_language=language, needs_confirmation=False,
    )


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language_hint: str | None = Form(default=None),
    partial: bool = Form(default=False),
) -> TranscribeResponse:
    blob = await audio.read()
    if not blob:
        raise HTTPException(status_code=422, detail="empty audio upload")
    language = _coerce_language_hint(language_hint)
    # Both paths block on HTTP / CPU inference — off the event loop, or one
    # user's 8 s faster-whisper fallback stalls every other request, live
    # partials included.
    if partial:
        return await asyncio.to_thread(_partial_transcript, blob, language)
    result = await asyncio.to_thread(speech_to_text, blob, language)
    low_confidence = result.rung == "unavailable" or result.confidence < LOW_CONFIDENCE_THRESHOLD
    # P3.7 — checked only when confidence is already low: a confident
    # transcript containing a distress word is an ordinary query about
    # distress procedure ("what do I do if my crewmate is injured"), not a
    # mishearing to double-check; SOS itself is a separate, always-on control.
    possible_distress = low_confidence and detect_distress_signal(result.transcript)["is_distress"]
    return TranscribeResponse(
        transcript=result.transcript,
        confidence=result.confidence,
        rung=result.rung,
        detected_language=result.detected_language,
        needs_confirmation=low_confidence,
        engine=f"Bhashini ASR · {result.service_id}" if result.rung == "bhashini" and result.service_id else None,
        possible_distress=possible_distress,
    )


class SpeakRequest(BaseModel):
    text: str
    language: str = "en"


@router.post("/speak")
async def speak(req: SpeakRequest) -> Response:
    """TTS synthesis — runs in a thread pool so CPU-bound VITS inference
    doesn't block the async event loop. Results are cached in voice.py's
    _tts_cache so repeated clicks return instantly."""
    lang = _coerce_language_hint(req.language) or "en"
    loop = asyncio.get_running_loop()
    audio, rung = await loop.run_in_executor(None, text_to_speech, req.text, lang)
    if rung == "bhashini_unavailable":
        # Marathi, Gujarati and Odia: no local backup voice, so say why (the UI shows it, in words).
        raise HTTPException(status_code=503, detail={"code": "bhashini_speech_unavailable", "language": lang})
    if audio is None:
        raise HTTPException(status_code=503, detail="No TTS backend available (Bhashini uncredentialed, MMS-TTS failed)")
    return Response(content=audio, media_type="audio/wav", headers={"X-TTS-Rung": rung})


@router.post("/prefetch")
async def prefetch(req: SpeakRequest, background_tasks: BackgroundTasks) -> dict:
    """Fire-and-forget TTS warm-up — the frontend calls this as soon as the
    answer arrives so the audio is cached by the time the user clicks Play.
    Returns immediately with 202-like status; synthesis runs in background."""
    lang = _coerce_language_hint(req.language) or "en"

    def _warm():
        try:
            text_to_speech(req.text, lang)
        except Exception:
            logger.warning("TTS prefetch failed (non-fatal)", exc_info=True)

    background_tasks.add_task(_warm)
    return {"status": "prefetch_queued"}
