"""Agent 1 (User Interaction) — language detection & translation interface,
plan §4 S6 Day 6.

`detect_language` is real: deterministic Unicode-block script detection for
Ta/Hi/En. Ta and Hi scripts don't overlap, so this is exact, not a
statistical guess, and it stays deterministic in the same spirit as Agent
12's distress detection (plan §4 S2 — pattern match, not semantic inference).

Translation is an interface only this session. Real IndicTrans2 inference
needs `transformers` + `torch`, which `backend/requirements.txt` explicitly
keeps out "until Agent 1's actual IndicTrans2 inference code does" — and the
weights are a multi-GB pull (plan's pre-Phase-1 S6 action item,
`backend/scripts/download_ml_models.py`) that has to run on the demo
machine, not in this environment. `translate_to_english` /
`translate_from_english` are the seam Bhashini slots into later (same
interface, config swap) — calling either without a registered backend
raises loudly rather than silently returning source text as if translated.
"""
from __future__ import annotations

from typing import Literal, Protocol

Language = Literal["ta", "hi", "en"]

_TAMIL_BLOCK = (0x0B80, 0x0BFF)
_DEVANAGARI_BLOCK = (0x0900, 0x097F)


def detect_language(text: str) -> Language:
    """Script-range detection. Falls back to "en" when no Tamil/Devanagari
    codepoint is present.
    """
    tamil_count = 0
    devanagari_count = 0
    for ch in text:
        cp = ord(ch)
        if _TAMIL_BLOCK[0] <= cp <= _TAMIL_BLOCK[1]:
            tamil_count += 1
        elif _DEVANAGARI_BLOCK[0] <= cp <= _DEVANAGARI_BLOCK[1]:
            devanagari_count += 1
    if tamil_count == 0 and devanagari_count == 0:
        return "en"
    return "ta" if tamil_count >= devanagari_count else "hi"


class TranslationBackend(Protocol):
    """The seam IndicTrans2 (Phase 1 primary) and Bhashini (when access
    lands) both implement — a config swap, not a code change.
    """

    def translate(self, text: str, source: Language, target: Language) -> str: ...


_backend: TranslationBackend | None = None


def register_translation_backend(backend: TranslationBackend) -> None:
    global _backend
    _backend = backend


def translate_to_english(text: str, source: Language) -> str:
    if source == "en":
        return text
    if _backend is None:
        raise RuntimeError(
            "No translation backend registered. Pull IndicTrans2 weights via "
            "backend/scripts/download_ml_models.py and register an IndicTrans2 "
            "backend before calling this (plan §4 S6 pre-Phase-1 action item)."
        )
    return _backend.translate(text, source=source, target="en")


def translate_from_english(text: str, target: Language) -> str:
    if target == "en":
        return text
    if _backend is None:
        raise RuntimeError(
            "No translation backend registered. Pull IndicTrans2 weights via "
            "backend/scripts/download_ml_models.py and register an IndicTrans2 "
            "backend before calling this (plan §4 S6 pre-Phase-1 action item)."
        )
    return _backend.translate(text, source="en", target=target)


if __name__ == "__main__":
    assert detect_language("நாளை காலை கடலுக்குச் செல்வது பாதுகாப்பானதா?") == "ta"
    assert detect_language("क्या कल सुबह समुद्र में जाना सुरक्षित है?") == "hi"
    assert detect_language("Is it safe to go to sea tomorrow morning?") == "en"
    assert translate_to_english("hello", "en") == "hello"
    try:
        translate_to_english("வணக்கம்", "ta")
        raise AssertionError("expected RuntimeError with no backend registered")
    except RuntimeError:
        pass
    print("language self-check ok")
