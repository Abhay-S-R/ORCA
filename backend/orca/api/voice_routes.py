"""Voice endpoints — plan §4 D1 Day 16-17: `POST /voice/transcribe` and
`POST /voice/speak`, thin HTTP wrappers over orca/agents/voice.py's
speech_to_text / text_to_speech. Neither touches ORCAState or the graph —
voice is a pre/post step around the same `/query` text pipeline every other
channel already uses, not a parallel graph.
"""
from __future__ import annotations

from typing import Literal, get_args

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from orca.agents.language import Language
from orca.agents.voice import LOW_CONFIDENCE_THRESHOLD, speech_to_text, text_to_speech

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


def _coerce_language_hint(value: str | None) -> Language | None:
    return value if value in _VALID_LANGUAGES else None  # type: ignore[return-value]


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...), language_hint: str | None = Form(default=None),
) -> TranscribeResponse:
    blob = await audio.read()
    if not blob:
        raise HTTPException(status_code=422, detail="empty audio upload")
    result = speech_to_text(blob, language_hint=_coerce_language_hint(language_hint))
    return TranscribeResponse(
        transcript=result.transcript,
        confidence=result.confidence,
        rung=result.rung,
        detected_language=result.detected_language,
        needs_confirmation=result.rung == "unavailable" or result.confidence < LOW_CONFIDENCE_THRESHOLD,
    )


class SpeakRequest(BaseModel):
    text: str
    language: str = "en"


@router.post("/speak")
def speak(req: SpeakRequest) -> Response:
    lang = _coerce_language_hint(req.language) or "en"
    audio, rung = text_to_speech(req.text, lang)
    if audio is None:
        raise HTTPException(status_code=503, detail="No TTS backend available (Bhashini uncredentialed, MMS-TTS failed)")
    return Response(content=audio, media_type="audio/wav", headers={"X-TTS-Rung": rung})
