import pytest

from orca.agents.language import (
    detect_language,
    translate_from_english,
    translate_to_english,
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
