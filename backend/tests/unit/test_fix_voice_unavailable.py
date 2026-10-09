"""FIX-VOICE-10 (2026-10-09): Marathi, Gujarati and Odia say "Bhashini speech is unavailable right now".

Bhashini's speech service answers 504 for these three languages on every call (Hindi, on the same service id,
answers in 0.8 s). Play used to wait about 25 s (76 s the first time for Marathi) and then play the local robotic
voice. The user's decision: say it is unavailable, and do not play the local voice, for these three. A language
whose Bhashini speech failed is skipped for ten minutes; then one short probe decides.
"""
from __future__ import annotations

import time
from unittest import mock

import pytest

from orca.agents import bhashini, voice
from orca.agents.voice import (
    _NO_LOCAL_VOICE,
    _SPEECH_DOWN_S,
    _speech_down_until,
    bhashini_speech_is_down,
    probe_speech_health,
    text_to_speech,
)


class _DownBhashini(voice.BhashiniTtsBackend):
    def __init__(self):
        self.calls = 0

    def speak(self, text, language):
        self.calls += 1
        raise RuntimeError("Bhashini inference call failed: 504 Gateway Time-out")


class _UpBhashini(voice.BhashiniTtsBackend):
    def __init__(self):
        self.calls = 0

    def speak(self, text, language):
        self.calls += 1
        return b"BHASHINI-AUDIO"


class _Local:
    def __init__(self):
        self.calls = 0

    def speak(self, text, language):
        self.calls += 1
        return b"LOCAL-AUDIO"


@pytest.fixture(autouse=True)
def _clean_state():
    _speech_down_until.clear()
    voice._tts_cache.clear()
    yield
    _speech_down_until.clear()
    voice._tts_cache.clear()


def _use(*backends):
    return mock.patch.object(voice, "_tts_backends", tuple(backends))


def test_the_three_languages_are_exactly_marathi_gujarati_and_odia():
    assert _NO_LOCAL_VOICE == frozenset({"mr", "gu", "or"})


@pytest.mark.parametrize("lang", sorted(_NO_LOCAL_VOICE))
def test_when_bhashini_fails_for_these_languages_the_answer_is_unavailable_and_the_local_voice_is_never_played(lang):
    bh, local = _DownBhashini(), _Local()
    with _use(bh, local):
        audio, rung = text_to_speech("नमस्कार", lang)  # type: ignore[arg-type]
    assert audio is None and rung == "bhashini_unavailable"
    assert bh.calls == 1 and local.calls == 0
    assert bhashini_speech_is_down(lang)


@pytest.mark.parametrize("lang", sorted(_NO_LOCAL_VOICE))
def test_the_next_press_answers_at_once_without_asking_bhashini_again(lang):
    bh, local = _DownBhashini(), _Local()
    with _use(bh, local):
        text_to_speech("one", lang)  # type: ignore[arg-type]
        started = time.monotonic()
        audio, rung = text_to_speech("two", lang)  # type: ignore[arg-type]
    assert (audio, rung) == (None, "bhashini_unavailable") and bh.calls == 1 and local.calls == 0
    assert time.monotonic() - started < 0.5


@pytest.mark.parametrize("lang", ["en", "hi", "kn", "ta", "te", "ml", "bn"])
def test_the_other_languages_keep_the_local_voice_as_their_backup(lang):
    bh, local = _DownBhashini(), _Local()
    with _use(bh, local):
        audio, rung = text_to_speech("hello", lang)  # type: ignore[arg-type]
    assert (audio, rung) == (b"LOCAL-AUDIO", "mms_tts") and local.calls == 1


def test_while_bhashini_is_known_down_another_language_goes_straight_to_the_local_voice():
    bh, local = _DownBhashini(), _Local()
    with _use(bh, local):
        text_to_speech("a", "kn")
        text_to_speech("b", "kn")
    assert bh.calls == 1 and local.calls == 2  # not 25 s of failure on every press


def test_one_language_being_down_does_not_affect_another():
    up, local = _UpBhashini(), _Local()
    _speech_down_until["mr"] = time.monotonic() + 100
    with _use(up, local):
        assert text_to_speech("hi", "hi") == (b"BHASHINI-AUDIO", "bhashini")  # type: ignore[arg-type]
        assert text_to_speech("hi", "mr") == (None, "bhashini_unavailable")  # type: ignore[arg-type]


def test_a_working_bhashini_is_used_and_clears_any_old_down_mark():
    up, local = _UpBhashini(), _Local()
    with _use(up, local):
        audio, rung = text_to_speech("ok", "gu")
    assert (audio, rung) == (b"BHASHINI-AUDIO", "bhashini") and not bhashini_speech_is_down("gu") and local.calls == 0


def test_an_unavailable_answer_is_not_cached():
    bh, local = _DownBhashini(), _Local()
    with _use(bh, local):
        text_to_speech("same text", "or")
    assert not voice._tts_cache
    up = _UpBhashini()
    _speech_down_until.clear()
    with _use(up, local):
        assert text_to_speech("same text", "or") == (b"BHASHINI-AUDIO", "bhashini")


# --- recovery: after ten minutes ONE short probe decides, not a 25 s real request ------------------------------------------

def test_the_down_mark_lasts_ten_minutes():
    assert _SPEECH_DOWN_S == 600.0
    bh = _DownBhashini()
    with _use(bh, _Local()):
        text_to_speech("x", "mr")
    remaining = _speech_down_until["mr"] - time.monotonic()
    assert 590 < remaining <= 600


def test_after_the_ten_minutes_a_short_probe_that_succeeds_brings_the_voice_back():
    _speech_down_until["mr"] = time.monotonic() - 1  # expired
    up = _UpBhashini()
    with _use(up, _Local()), mock.patch.object(bhashini, "tts", return_value=b"x") as tts:
        assert text_to_speech("hi", "mr") == (b"BHASHINI-AUDIO", "bhashini")
    assert tts.call_args.kwargs == {"timeout_s": 8.0, "retry": False}  # the short, single-try probe
    assert not bhashini_speech_is_down("mr")


def test_after_the_ten_minutes_a_probe_that_fails_costs_one_short_try_and_marks_it_down_again():
    _speech_down_until["gu"] = time.monotonic() - 1
    bh, local = _DownBhashini(), _Local()
    with _use(bh, local), mock.patch.object(bhashini, "tts", side_effect=bhashini.BhashiniError("504")):
        assert text_to_speech("hi", "gu") == (None, "bhashini_unavailable")
    assert bh.calls == 0 and local.calls == 0  # the real synthesis was never attempted
    assert bhashini_speech_is_down("gu")


# --- the startup probe -----------------------------------------------------------------------------------------------------------

def test_the_startup_probe_tries_only_the_three_languages_and_marks_the_failing_ones_down():
    def tts(word, lang, gender="female", **kw):
        if lang == "hi":
            raise AssertionError("Hindi must not be probed: it has a local backup")
        if lang == "mr":
            raise bhashini.BhashiniError("504")
        return b"x"

    with mock.patch.object(bhashini, "bhashini_configured", return_value=True), mock.patch.object(bhashini, "tts", tts):
        result = probe_speech_health()
    assert result == {"gu": True, "mr": False, "or": True}
    assert bhashini_speech_is_down("mr") and not bhashini_speech_is_down("gu") and not bhashini_speech_is_down("or")


def test_the_startup_probe_does_nothing_when_bhashini_is_not_configured():
    with mock.patch.object(bhashini, "bhashini_configured", return_value=False), mock.patch.object(
        bhashini, "tts", side_effect=AssertionError("must not be called")
    ):
        assert probe_speech_health() == {}
    assert not _speech_down_until


def test_the_probe_uses_a_short_limit_and_one_try():
    seen = []

    def tts(word, lang, gender="female", **kw):
        seen.append((lang, kw))
        return b"x"

    with mock.patch.object(bhashini, "bhashini_configured", return_value=True), mock.patch.object(bhashini, "tts", tts):
        probe_speech_health()
    assert {lang for lang, _ in seen} == {"mr", "gu", "or"} and all(kw == {"timeout_s": 8.0, "retry": False} for _, kw in seen)


def test_startup_runs_the_probe_without_waiting_for_it():
    import inspect

    from orca.api import main

    source = inspect.getsource(main)
    assert "run_in_executor(None, _probe_speech_health)" in source
    assert "warmups.append(asyncio.get_running_loop().run_in_executor(None, _probe_speech_health))" not in source  # never part of the wait


# --- bhashini.tts: a probe asks once, quickly --------------------------------------------------------------------------------------

def test_a_probe_call_has_no_retry_and_a_short_limit():
    calls = []

    def fail(config, task, payload, timeout_s=None):
        calls.append(timeout_s)
        raise bhashini.BhashiniError("504")

    config = {"serviceId": "s", "callback_url": "http://x", "inference_api_key": {"name": "k", "value": "v"}}
    with mock.patch.object(bhashini, "_pipeline_config", return_value=config), mock.patch.object(bhashini, "_inference", fail):
        with pytest.raises(bhashini.BhashiniError):
            bhashini.tts("x", "mr", timeout_s=8.0, retry=False)
        assert calls == [8.0]
        calls.clear()
        with pytest.raises(bhashini.BhashiniError):
            bhashini.tts("x", "mr")
        assert calls == [bhashini.TTS_TIMEOUT_S, bhashini.TTS_TIMEOUT_S]  # the normal call still retries once


# --- the route says why ----------------------------------------------------------------------------------------------------------------

def test_the_speak_route_answers_503_with_a_machine_readable_reason_for_these_languages():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from orca.api import voice_routes

    app = FastAPI()
    app.include_router(voice_routes.router)
    client = TestClient(app)
    with mock.patch.object(voice_routes, "text_to_speech", return_value=(None, "bhashini_unavailable")):
        res = client.post("/voice/speak", json={"text": "x", "language": "mr"})
    assert res.status_code == 503
    assert res.json()["detail"] == {"code": "bhashini_speech_unavailable", "language": "mr"}
    with mock.patch.object(voice_routes, "text_to_speech", return_value=(b"AUDIO", "bhashini")):
        ok = client.post("/voice/speak", json={"text": "x", "language": "en"})
    assert ok.status_code == 200 and ok.headers["X-TTS-Rung"] == "bhashini" and ok.content == b"AUDIO"
    with mock.patch.object(voice_routes, "text_to_speech", return_value=(None, "unavailable")):
        other = client.post("/voice/speak", json={"text": "x", "language": "en"})
    assert other.status_code == 503 and isinstance(other.json()["detail"], str)
