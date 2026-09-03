# The real weights (backend/scripts/download_ml_models.py) are a multi-GB,
# gated HuggingFace download — present on this machine, not guaranteed on
# CI or a fresh clone. The integration test below skips itself rather than
# failing a build that has no way to get the weights.
import importlib.util
from pathlib import Path

import pytest

from orca.agents.language import (
    IndicTrans2Backend,
    detect_language,
    register_translation_backend,
    run_egress,
    run_ingress,
    translate_from_english,
    translate_to_english,
)
from orca.state import ORCAState

_TOOLKIT_PRESENT = importlib.util.find_spec("IndicTransToolkit") is not None

_HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"
_INDICTRANS2_WEIGHTS_PRESENT = (
    _TOOLKIT_PRESENT
    and any(_HF_HUB.glob("models--ai4bharat--indictrans2-indic-en*"))
    and any(_HF_HUB.glob("models--ai4bharat--indictrans2-en-indic*"))
)


def test_detect_language_tamil() -> None:
    assert detect_language("நாளை காலை கடலுக்குச் செல்வது பாதுகாப்பானதா?") == "ta"


def test_detect_language_hindi() -> None:
    assert detect_language("क्या कल सुबह समुद्र में जाना सुरक्षित है?") == "hi"


def test_detect_language_english() -> None:
    assert detect_language("Is it safe to go to sea tomorrow morning?") == "en"


def test_translate_to_english_is_identity_when_already_english() -> None:
    assert translate_to_english("hello", "en") == "hello"


def test_translate_from_english_is_identity_when_target_is_english() -> None:
    assert translate_from_english("hello", "en") == "hello"


def test_translate_raises_without_a_registered_backend() -> None:
    with pytest.raises(RuntimeError):
        translate_to_english("வணக்கம்", "ta")


def test_registered_backend_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EchoBackend:
        def translate(self, text: str, source: str, target: str) -> str:
            return f"[{source}->{target}] {text}"

    monkeypatch.setattr("orca.agents.language._backend", _EchoBackend())
    assert translate_to_english("வணக்கம்", "ta") == "[ta->en] வணக்கம்"


class _EchoBackend:
    def translate(self, text: str, source: str, target: str) -> str:
        return f"[{source}->{target}] {text}"


def _state(**overrides) -> ORCAState:
    base = {"query_id": "q-1", "reasoning_depth": "SHALLOW"}
    base.update(overrides)
    return base  # type: ignore[return-value]


# --- run_ingress / run_egress (mocked backend — fast, CI-safe) --------------

def test_run_ingress_translates_tamil_and_sets_detected_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orca.agents.language._backend", _EchoBackend())
    result = run_ingress(_state(raw_user_query="வணக்கம்"))
    assert result.outputs["detected_language"] == "ta"
    assert result.outputs["normalized_english_query"] == "[ta->en] வணக்கம்"
    assert result.status == "ok"
    assert not hasattr(result, "persona")


def test_run_ingress_english_query_passes_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orca.agents.language._backend", _EchoBackend())
    result = run_ingress(_state(raw_user_query="Is it safe today?"))
    assert result.outputs["detected_language"] == "en"
    assert result.outputs["normalized_english_query"] == "Is it safe today?"


def test_run_ingress_degrades_not_crashes_without_a_backend() -> None:
    # No backend registered — must not raise out of the graph node, must
    # pass the raw text through so Planning's no-match fallback (not a crash)
    # is what the user sees.
    result = run_ingress(_state(raw_user_query="வணக்கம்"))
    assert result.status == "degraded"
    assert result.outputs["normalized_english_query"] == "வணக்கம்"
    assert result.confidence.score == "LOW_DATA"


def test_run_egress_translates_english_response_to_detected_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orca.agents.language._backend", _EchoBackend())
    result = run_egress(_state(detected_language="ta", final_english_response="GO: all clear."))
    assert result.outputs["final_vernacular_response"] == "[en->ta] GO: all clear."


def test_run_egress_english_query_stays_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("orca.agents.language._backend", _EchoBackend())
    result = run_egress(_state(detected_language="en", final_english_response="GO: all clear."))
    assert result.outputs["final_vernacular_response"] == "GO: all clear."


def test_run_egress_degrades_to_english_without_a_backend() -> None:
    result = run_egress(_state(detected_language="hi", final_english_response="GO: all clear."))
    assert result.status == "degraded"
    assert result.outputs["final_vernacular_response"] == "GO: all clear."  # degraded to English, not crashed


# --- Real IndicTrans2 integration — only runs where the actual gated ------
# weights are present locally (see _INDICTRANS2_WEIGHTS_PRESENT above).
# This is the test that actually proves the pinned transformers==4.46.3 /
# IndicTransToolkit combination works, not just that the interface is wired.

@pytest.mark.skipif(not _INDICTRANS2_WEIGHTS_PRESENT, reason="IndicTrans2 weights not downloaded on this machine")
def test_real_indictrans2_round_trip() -> None:
    backend = IndicTrans2Backend()
    register_translation_backend(backend)
    try:
        english = translate_to_english(
            "நாளை காலை தூத்துக்குடி அருகே கடலுக்குச் செல்வது பாதுகாப்பானதா?", source="ta"
        )
        assert "thoothukudi" in english.lower() or "safe" in english.lower()

        tamil = translate_from_english("Is it safe to go to sea tomorrow morning?", target="ta")
        assert any(0x0B80 <= ord(ch) <= 0x0BFF for ch in tamil)  # real Tamil script came back
    finally:
        register_translation_backend(None)  # type: ignore[arg-type]
