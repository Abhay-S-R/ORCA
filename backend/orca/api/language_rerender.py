"""CONTEXT-2 and P3.13 share one way to put the last answer into another language.

CONTEXT-2 ("answer the same in Kannada", read by the model): the chat's memory keeps the last turn's whole finished answer
(`session.turn_from_final` stores it as `frame`), so the SAME answer is translated: the verdict card, numbers and citations
are the earlier ones, no specialist runs and no new forecast is fetched, and the frame still carries what the chat remembers
about a turn (the place, the routing rows, the English query), so the NEXT follow-up ("and the wave height there?") keeps
its place and intent. P3.13's fixed-phrase path ("speak to me in Telugu") may also fall back to re-writing the narrative
from the stored trace when no frame is held (`rewrite_from_trace`); CONTEXT-2 never does, because that rewrite produces a
different answer.
"""
from __future__ import annotations

import logging
from typing import Any

from orca.api.trace_routes import render_query

logger = logging.getLogger("orca.language")


def _translate(english: str, language: str) -> str | None:
    """The English text in `language`, the way language_egress does it (placeholders, product name); None on failure."""
    if language == "en":
        return english
    from orca.agents.language import _translate_with_rung

    try:
        return _translate_with_rung(english, "en", language)[0]  # type: ignore[arg-type]
    except RuntimeError:
        return None


def rerender_last_answer(
    history: list[dict[str, Any]], language: str, persona: str = "fisherman", rewrite_from_trace: bool = False,
) -> dict[str, Any] | None:
    """The `final_response` frame for the last answered turn of this chat in `language`, or None when there is no
    answered turn or it cannot be put into `language` (the caller then runs the normal pipeline or just confirms)."""
    last = next((t for t in reversed(history) if t.get("query_id")), None)
    if last is None:
        return None
    frame = last.get("frame")
    if isinstance(frame, dict) and frame.get("final_english_response"):
        vernacular = _translate(str(frame["final_english_response"]), language)
        if vernacular is not None:
            reason = frame.get("confidence_reason")
            if reason and language != "en":
                reason = _translate(str(reason), language) or reason
            return {
                **frame,
                "type": "final_response",
                "final_vernacular_response": vernacular,
                "detected_language": language,
                "confidence_reason": reason,
                "disclosures": list(frame.get("disclosures") or []),   # nothing is added: no "same answer in X" note (the user, 2026-10-10)
                "language_rerender": True,
            }
    if not rewrite_from_trace:
        return None
    try:
        rendered = render_query(last["query_id"], persona, language)
    except Exception:
        logger.warning("language re-render failed", exc_info=True)
        return None
    return {
        "type": "final_response",
        "query_id": rendered.query_id,
        "outcome": "LANGUAGE_CHANGED",
        "final_english_response": rendered.final_english_response,
        "final_vernacular_response": rendered.final_vernacular_response or rendered.final_english_response,
        "detected_language": language,
        "confidence_tier": rendered.confidence_tier,
        "citations": rendered.citations,
        "risk_assessment": None,
        "disclosures": [],
        "distress_flag": False,
        "inherited": [],
        "normalized_english_query": last.get("english_query") or last.get("query"),
        "matched_intent_rows": last.get("intent_rows") or [],
        "user_location": last.get("user_location"),
        "vessel_class": last.get("vessel_class"),
        "verdict": last.get("verdict"),
    }
