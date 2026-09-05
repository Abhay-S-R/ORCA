import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from orca.agents.voice import TranscriptionResult
from orca.api.main import app

client = TestClient(app)


def test_transcribe_returns_the_transcript_confidence_and_rung() -> None:
    fake_result = TranscriptionResult(transcript="is it safe today", confidence=0.9, rung="faster_whisper", detected_language="en")
    with patch("orca.api.voice_routes.speech_to_text", return_value=fake_result):
        resp = client.post("/voice/transcribe", files={"audio": ("q.wav", io.BytesIO(b"fake-wav-bytes"), "audio/wav")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "is it safe today"
    assert body["rung"] == "faster_whisper"
    assert body["needs_confirmation"] is False


def test_transcribe_flags_low_confidence_for_confirmation() -> None:
    fake_result = TranscriptionResult(transcript="save the boat", confidence=0.2, rung="faster_whisper", detected_language="en")
    with patch("orca.api.voice_routes.speech_to_text", return_value=fake_result):
        resp = client.post("/voice/transcribe", files={"audio": ("q.wav", io.BytesIO(b"fake-wav-bytes"), "audio/wav")})
    assert resp.json()["needs_confirmation"] is True


def test_transcribe_rejects_an_empty_upload() -> None:
    resp = client.post("/voice/transcribe", files={"audio": ("q.wav", io.BytesIO(b""), "audio/wav")})
    assert resp.status_code == 422


def test_speak_returns_wav_audio_bytes() -> None:
    with patch("orca.api.voice_routes.text_to_speech", return_value=(b"RIFF....WAVEfmt ", "mms_tts")):
        resp = client.post("/voice/speak", json={"text": "GO: conditions favorable", "language": "en"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.headers["x-tts-rung"] == "mms_tts"
    assert resp.content == b"RIFF....WAVEfmt "


def test_speak_returns_503_when_no_tts_backend_is_available() -> None:
    with patch("orca.api.voice_routes.text_to_speech", return_value=(None, "unavailable")):
        resp = client.post("/voice/speak", json={"text": "GO: conditions favorable", "language": "en"})
    assert resp.status_code == 503
