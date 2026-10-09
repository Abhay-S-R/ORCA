"""P2.9 (`R-PS-3`, `R-CONV-1`) — which boat the question is about, read from
the question.

`vessel_class` reached the graph only as a `/query` parameter, so a vessel
named in the *text* set nothing: "and in a trawler?" typed into the Ask chat
was answered with `small_fishing` thresholds, which is the wrong answer to the
question that was asked. It errs in the safe direction — `small_fishing` is
the strictest band in `risk_assessment._VESSEL_DELTAS`, so nobody was told a
trip was fine when it was not — but "conservative and wrong" is still wrong,
and the third clause of P2.9's Done-when ("and in a trawler?") is exactly this
case.

Deterministic, and it stays that way: this feeds `risk_assessment`'s threshold
selection, which is the safety path, and `scripts/verify_ci_guards.py` holds
that path to no LLM imports.

The vocabulary is the DB's user-facing enum (`infra/db/001_init.sql`,
`orca/auth/schemas.py`), not the risk engine's three-way one — P0.13 settled
that there is exactly one translation point between those, in
`risk_assessment.risk_vessel_class`, and this must not become a second.
"""
from __future__ import annotations

import re

# DB enum value -> the words people actually use for it. Ordered longest-first
# at match time so "fibreglass boat" cannot be matched as "boat".
#
# Deliberately NOT including bare "boat": it is the default already, it appears
# in half of all queries ("can I take my boat out"), and matching it would make
# every such question look like an explicit vessel choice — which would then be
# rendered as an inherited chip the user never set.
_VESSEL_WORDS: dict[str, tuple[str, ...]] = {
    "trawler": ("trawler", "trawlers", "trawling boat"),
    "mechanised": ("mechanised", "mechanized", "motorised boat", "motorized boat", "motor boat", "inboard"),
    "catamaran": ("catamaran", "kattumaram", "kattumaran", "vallam"),
    "fibreglass": ("fibreglass", "fiberglass", "frp boat", "frp"),
    "cargo": ("cargo vessel", "cargo ship", "merchant vessel", "freighter"),
}

# What a chip says. Neither vocabulary's raw value is a word to show a
# fisherman. Keyed by BOTH: the DB enum (what a question's text names) and the
# risk engine's class (what the state, the session and the response carry).
VESSEL_LABELS: dict[str, str] = {
    "trawler": "Trawler",
    "mechanised": "Mechanised boat",
    "catamaran": "Catamaran",
    "fibreglass": "Fibreglass boat",
    "cargo": "Cargo vessel",
    "small_fishing": "Small fishing boat",
    "mechanized_trawler": "Mechanised trawler",
    "cargo_vessel": "Cargo vessel",
}

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        db_value,
        # Word boundaries, unlike the distress patterns: these are ordinary
        # words inside ordinary sentences, and the false-positive direction
        # here silently changes which safety thresholds are applied.
        re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.IGNORECASE),
    )
    for db_value, words in _VESSEL_WORDS.items()
)


def vessel_class_from_text(text: str | None) -> str | None:
    """The DB-enum vessel class this question names, or None.

    None means "not named", never "small boat" — the default belongs to
    `risk_assessment.run`, which already applies the most conservative class
    when nothing is given, and duplicating it here would be a second place
    that decides a safety threshold.
    """
    if not text:
        return None
    for db_value, pattern in _PATTERNS:
        if pattern.search(text):
            return db_value
    return None


def resolve_vessel_class(
    explicit: str | None, text: str | None, remembered: str | None,
) -> str | None:
    """Which vessel class this request's safety thresholds are computed for,
    **in the risk engine's own vocabulary** — the only vocabulary
    `risk_assessment.evaluate_marine_safety` accepts.

    Precedence is what the user actually said, most specific first: an explicit
    parameter (a registered vessel or the picker), then a vessel named in this
    question ("and in a trawler?"), then the one remembered from earlier in the
    chat. None means nothing was given, and `risk_assessment.run` applies the
    most conservative class — the safety default keeps its single home.

    The first version of P2.9 returned the DB-enum name ("trawler") from here
    and put it straight into state. The risk engine has no such key, the agent
    raised, its exception boundary turned that into an EMPTY verdict, and the
    follow-up rendered with no safety verdict at all. Found by asking the
    question in the browser; the translation is `risk_vessel_class`, and
    P0.13 said there would be exactly one place it happens — this is it."""
    from orca.agents.risk_assessment import risk_vessel_class

    if explicit:
        return explicit
    named = vessel_class_from_text(text)
    if named:
        return risk_vessel_class(named)
    return remembered or None


def vessel_named_in(text: str | None) -> bool:
    """Whether the user named a vessel in this message — used to tell an
    inherited vessel from one the user just chose (P2.9's chips)."""
    return vessel_class_from_text(text) is not None


if __name__ == "__main__":
    assert vessel_class_from_text("and in a trawler?") == "trawler"
    assert vessel_class_from_text("what about a mechanised boat tomorrow") == "mechanised"
    assert vessel_class_from_text("is it safe in my kattumaram") == "catamaran"
    assert vessel_class_from_text("FRP boat, is it ok") == "fibreglass"
    assert vessel_class_from_text("can this cargo vessel sail") == "cargo"

    # Not named is None, never a default — the safety default has exactly one
    # home and it is not this file.
    assert vessel_class_from_text("is it safe to go to sea today") is None
    assert vessel_class_from_text("can I take my boat out") is None
    assert vessel_class_from_text("") is None
    assert vessel_class_from_text(None) is None

    # Word boundaries: a vessel word inside another word is not a vessel.
    assert vessel_class_from_text("the cargoes were unloaded") is None
    assert vessel_class_from_text("trawlermen went on strike") is None

    # The resolver speaks the risk engine's language, never the DB's.
    assert resolve_vessel_class(None, "and in a trawler?", None) == "mechanized_trawler"
    assert resolve_vessel_class(None, "what about tomorrow", "small_fishing") == "small_fishing"
    assert resolve_vessel_class("cargo_vessel", "and in a trawler?", "small_fishing") == "cargo_vessel"
    assert resolve_vessel_class(None, "what about tomorrow", None) is None
    assert vessel_named_in("and in a trawler?") is True
    assert vessel_named_in("what about tomorrow?") is False

    # Every DB enum value this module can return must have a label, or a chip
    # would show a raw enum value to a fisherman.
    assert set(_VESSEL_WORDS) <= set(VESSEL_LABELS)
    # ... and every class the risk engine can carry has one too, or a chip for
    # an inherited vessel would show "mechanized_trawler" to a fisherman.
    from orca.agents.risk_assessment import _VESSEL_DELTAS

    assert {str(k) for k in _VESSEL_DELTAS} <= set(VESSEL_LABELS), {str(k) for k in _VESSEL_DELTAS} - set(VESSEL_LABELS)

    # ... and every value must be one risk_assessment actually knows, or the
    # translation point P0.13 settled would silently fall back to small_fishing.
    from orca.agents.risk_assessment import DB_VESSEL_CLASS_TO_RISK_CLASS

    assert set(_VESSEL_WORDS) <= set(DB_VESSEL_CLASS_TO_RISK_CLASS), (
        set(_VESSEL_WORDS) - set(DB_VESSEL_CLASS_TO_RISK_CLASS)
    )
    print("vessel self-check ok")
