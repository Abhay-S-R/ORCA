"""P3.13 (orca_final §15.2) — "speak to me in Telugu" changes the
conversation's language without being answered as a marine question.

Same shape as `orca/session.py`'s reset-phrase matcher (P2.14): a small,
deterministic, per-language phrase table, checked against the WHOLE
normalised message so it cannot fire on a sentence that merely mentions a
language in passing ("is Telugu spoken in Andhra Pradesh?" must still be
answered, not swallowed as a language switch).
"""
from __future__ import annotations

import re
from typing import Literal

Language = Literal["ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en"]

_PUNCT = str.maketrans({c: " " for c in "?!.,;:\"'"})


def _normalize(text: str) -> str:
    return " ".join(text.translate(_PUNCT).lower().split())


# Every phrase names the TARGET language explicitly — "speak to me in
# <language>" in English, and the natural "<language> மொழியில் பேசு" /
# "<language> mein bolo" shape in each core language's own script and in a
# common romanized form (P3.5/P3.14 territory: the command itself has to
# survive being typed in Latin script too).
_COMMANDS: dict[Language, tuple[str, ...]] = {
    "en": ("speak to me in english", "reply in english", "switch to english", "english please"),
    "ta": (
        "தமிழில் பேசு", "தமிழில் பேசுங்கள்", "தமிழில் பதில் சொல்",
        "tamil mozhiyil pesu", "speak to me in tamil", "reply in tamil", "switch to tamil",
    ),
    "hi": (
        "हिंदी में बोलो", "हिंदी में बोलिए", "हिंदी में जवाब दो",
        "hindi mein bolo", "hindi me bolo", "speak to me in hindi", "reply in hindi", "switch to hindi",
    ),
    "te": (
        "తెలుగులో మాట్లాడు", "తెలుగులో చెప్పు",
        "telugu lo matladu", "speak to me in telugu", "reply in telugu", "switch to telugu",
    ),
    "ml": (
        "മലയാളത്തിൽ സംസാരിക്കൂ", "മലയാളത്തിൽ പറയൂ",
        "malayalam il parayu", "speak to me in malayalam", "reply in malayalam", "switch to malayalam",
    ),
    "kn": (
        "ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಿ", "ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ",
        "kannada dalli matanadi", "speak to me in kannada", "reply in kannada", "switch to kannada",
    ),
    "bn": (
        "বাংলায় বলুন", "বাংলায় কথা বলুন",
        "bangla y bolun", "speak to me in bengali", "reply in bengali", "switch to bengali",
    ),
    "mr": (
        "मराठीत बोला", "मराठीत सांगा",
        "marathi t bola", "speak to me in marathi", "reply in marathi", "switch to marathi",
    ),
    "gu": ("ગુજરાતીમાં બોલો", "speak to me in gujarati", "reply in gujarati", "switch to gujarati"),
    "or": ("ଓଡ଼ିଆରେ କୁହନ୍ତୁ", "speak to me in odia", "reply in odia", "switch to odia"),
}

_NORMALIZED: dict[Language, tuple[str, ...]] = {
    lang: tuple(_normalize(p) for p in phrases) for lang, phrases in _COMMANDS.items()
}


def match_language_command(text: str | None) -> Language | None:
    """The target language this message asks to switch to, or None — never
    fires on ordinary marine text that happens to name a language."""
    if not text:
        return None
    normalized = _normalize(text)
    if not normalized:
        return None
    for lang, phrases in _NORMALIZED.items():
        if normalized in phrases:
            return lang
    return None


if __name__ == "__main__":
    assert match_language_command("speak to me in telugu") == "te"
    assert match_language_command("Reply in Hindi.") == "hi"
    assert match_language_command("hindi mein bolo") == "hi"
    assert match_language_command("தமிழில் பேசு") == "ta"
    assert match_language_command("is telugu spoken in andhra pradesh?") is None
    assert match_language_command("is it safe to go to sea today") is None
    assert match_language_command("") is None
    assert match_language_command(None) is None
    print("language_command self-check ok")
