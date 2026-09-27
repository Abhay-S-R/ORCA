"""A place named in an Indic-script question is resolved from its English
translation. `/query` used to run the English-only place parser on the raw
text, so "ಕೊಚ್ಚಿ ಹತ್ತಿರ ಇರುವ ಮೀನುಗಾರಿಕೆ ವಲಯಗಳು ಯಾವುವು?" (fishing zones
near Kochi) was answered at the pilot default, "I do not have data for
Kochi", while the same question in English was answered for Kochi."""
from __future__ import annotations

import asyncio

import pytest

from orca.api import main

KANNADA = "ಕೊಚ್ಚಿ ಹತ್ತಿರ ಇರುವ ಮೀನುಗಾರಿಕೆ ವಲಯಗಳು ಯಾವುವು?"


def _asked(monkeypatch: pytest.MonkeyPatch, q: str, english: str) -> dict:
    monkeypatch.setattr(main, "query_language", lambda raw, default=None: "en" if raw == english else "kn")
    monkeypatch.setattr(main, "english_query", lambda raw, lang: (english, "bhashini"))
    seen: dict = {}

    async def fake_stream(query, lat, lon, vessel_class, distress, persona, depth, place, **kw):
        seen.update(lat=lat, lon=lon, place=place, pretranslated=kw.get("pretranslated"))
        yield ""

    monkeypatch.setattr(main, "_query_stream", fake_stream)
    resp = asyncio.run(main.query(q=q, fresh=True, session_id="t-vernacular", user=None, db=None))  # type: ignore[arg-type]

    async def drain() -> None:
        async for _ in resp.body_iterator:
            pass

    asyncio.run(drain())
    return seen


def test_a_kannada_place_is_resolved_from_the_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _asked(monkeypatch, KANNADA, "What are the fishing zones near Kochi?")
    assert seen["place"][0] == "kochi", seen
    assert seen["place"][1] != "regional_default", seen
    # ingress is handed the same translation rather than paying for a second one
    assert seen["pretranslated"]["english"] == "What are the fishing zones near Kochi?"


def test_no_place_in_either_text_still_falls_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _asked(monkeypatch, "ನಾಳೆ ಸಮುದ್ರಕ್ಕೆ ಹೋಗಬಹುದೇ?", "Can I go to sea tomorrow?")
    assert seen["place"][1] == "regional_default", seen
