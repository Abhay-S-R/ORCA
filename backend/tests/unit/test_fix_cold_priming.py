"""FIX-COLD — startup priming is best-effort and never a startup dependency."""
from __future__ import annotations

from unittest import mock

from orca.api.main import _prime_first_request


class _Client:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, **kw):
        self.calls += 1
        return "ready"


def test_it_makes_one_model_call_and_one_synthesis():
    client = _Client()
    with mock.patch("orca.llm.tiers.llm", lambda tier: client), mock.patch("orca.llm.tiers.llm_enabled", lambda: True), \
            mock.patch("orca.agents.voice.text_to_speech", return_value=(b"x", "bhashini")) as tts:
        _prime_first_request()
    assert client.calls == 1 and tts.call_count == 1 and tts.call_args.args == ("ORCA is ready.", "en")


def test_with_models_off_it_makes_no_model_call():
    client = _Client()
    with mock.patch("orca.llm.tiers.llm", lambda tier: client), mock.patch("orca.llm.tiers.llm_enabled", lambda: False), \
            mock.patch("orca.agents.voice.text_to_speech", return_value=(None, "unavailable")):
        _prime_first_request()
    assert client.calls == 0


def test_a_failing_model_or_voice_never_raises():
    def boom(tier):
        raise RuntimeError("provider down")

    with mock.patch("orca.llm.tiers.llm", boom), mock.patch("orca.llm.tiers.llm_enabled", lambda: True), \
            mock.patch("orca.agents.voice.text_to_speech", side_effect=OSError("no audio")):
        _prime_first_request()


def test_it_resolves_the_bhashini_config_for_every_language_and_survives_a_failure():
    from orca.agents import bhashini

    seen = []

    def fake(task, *langs):
        seen.append((task, *langs))
        if langs == ("kn",):
            raise bhashini.BhashiniError("one language down")
        return {}

    with mock.patch("orca.llm.tiers.llm_enabled", lambda: False), mock.patch("orca.agents.voice.text_to_speech", return_value=(b"x", "bhashini")), \
            mock.patch.object(bhashini, "bhashini_configured", lambda: True), mock.patch.object(bhashini, "_pipeline_config", fake):
        _prime_first_request()
    tts = {t[1] for t in seen if t[0] == "tts"}
    nmt = {t[2] for t in seen if t[0] == "translation"}
    assert tts == {"ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en"}
    assert nmt == {"ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or"} and all(t[1] == "en" for t in seen if t[0] == "translation")


def test_with_bhashini_unconfigured_it_looks_nothing_up():
    from orca.agents import bhashini

    with mock.patch("orca.llm.tiers.llm_enabled", lambda: False), mock.patch("orca.agents.voice.text_to_speech", return_value=(None, "unavailable")), \
            mock.patch.object(bhashini, "bhashini_configured", lambda: False), \
            mock.patch.object(bhashini, "_pipeline_config", side_effect=AssertionError("must not be called")):
        _prime_first_request()


def test_startup_does_not_register_load_or_warm_a_local_translator_or_llm():
    """Decision 2026-10-08: no IndicTrans2 and no Ollama at startup. A machine without either
    must start and behave the same, so the app module must not reach for them."""
    import inspect

    from orca.api import main

    source = inspect.getsource(main)
    for banned in ("IndicTrans2Backend", "register_translation_backend", "warm_local_models", "_translation_backend"):
        assert banned not in source, banned


def test_the_language_spans_never_claim_a_translator_ran_on_english():
    from orca.agents.language import run_egress, run_ingress

    ing = run_ingress({"query_id": "q", "raw_user_query": "pfzs near kochi"})  # type: ignore[arg-type]
    egr = run_egress({"query_id": "q", "detected_language": "en", "final_english_response": "ok"})  # type: ignore[arg-type]
    for span in (ing, egr):
        assert "IndicTrans2" not in (span.source_provenance.dataset or "") and "IndicTrans2" not in (span.engine or "")
        assert span.engine == "No translation (passthrough)" and span.confidence.score == "HIGH"


def test_a_failed_translation_degrades_without_a_local_fallback():
    from orca.agents import bhashini
    from orca.agents.language import run_egress, run_ingress

    with mock.patch.object(bhashini, "nmt", side_effect=bhashini.BhashiniError("down")):
        ing = run_ingress({"query_id": "q", "raw_user_query": "கடல் பாதுகாப்பானதா"})  # type: ignore[arg-type]
        egr = run_egress({"query_id": "q", "detected_language": "ta", "final_english_response": "Calm seas."})  # type: ignore[arg-type]
    assert ing.status == "degraded" and ing.outputs["normalized_english_query"] == "கடல் பாதுகாப்பானதா"
    assert egr.status == "degraded" and egr.outputs["final_vernacular_response"] == "Calm seas."
    assert "IndicTrans2" not in (ing.source_provenance.dataset + egr.source_provenance.dataset)
