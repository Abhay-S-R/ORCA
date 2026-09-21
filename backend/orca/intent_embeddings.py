"""P2.8 (`R-PS-1`) — Tier 2 of Agent 2's routing, as sentence embeddings.

Tier 2 was word overlap (`planning._tier2_embedding_similarity`, named for the
thing it was not): it scored a query against each routing row by how many
significant words they shared, after a four-entry synonym table. That is why
arbitrary phrasing missed. "Can I take the boat out past the reef this
evening?" shares no scored word with `safe to go to sea`, so Tier 2 found
nothing and the question fell through to a paid LLM call — or, worse, to the
no-match fallback path, which answers the closest general-conditions
interpretation of a safety question.

This replaces the scorer, not the tier. Deterministic-first is still the
design: Tier 1's exact keyword match runs first and still handles almost
everything, and this only sees what Tier 1 did not match.

**Stack.** `intfloat/multilingual-e5-small` — 384-dimensional, ~120 MB, CPU,
no GPU, and multilingual, which matters because a Tamil or Hindi query that
Agent 1 failed to translate still arrives here as text. The routing rows'
phrasings are embedded once at import of the first query (or at startup, see
`warm()`), not per request.

**It is optional by construction.** No model, no package, or no network on
first run degrades to `None` from every entry point, and `planning.py` falls
back to the word-overlap scorer it has always had. A machine that cannot
download 120 MB gets ORCA's previous routing behaviour, not a broken ORCA.

**e5 prefixes are load-bearing.** The model was trained with `query: ` on the
thing being searched with and `passage: ` on the thing being searched over.
Dropping them costs real accuracy; they are applied in `_encode`, once, so no
caller has to remember.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger("orca.intent")

# `or`, not a get() default: .env.example lists these keys BLANK, and load_dotenv turns a blank
# line into an empty-string variable, for which get(key, default) returns "" and not the default.
# An empty threshold would have crashed at import (float("")) and an empty model name would have
# silently switched the embedding tier off.
MODEL_NAME = os.environ.get("ORCA_INTENT_EMBED_MODEL") or "intfloat/multilingual-e5-small"

# Cosine similarity above which a routing row is considered matched.
#
# Tuned on the 30-paraphrase set in tests/unit/test_intent_embeddings.py, which
# is the Done-when for P2.8 — it is not a guessed constant. e5 packs ordinary
# short text into a narrow, high band (two unrelated marine sentences still sit
# around 0.80), so this threshold is high by the standards of other embedding
# models and must be retuned if MODEL_NAME ever changes.
THRESHOLD = float(os.environ.get("ORCA_INTENT_EMBED_THRESHOLD") or "0.835")

# How far below the best row a second row may sit and still be reported. A
# compound question ("is it safe, and where are the fish?") genuinely matches
# two rows, and Tier 2 must be able to say so — that is what P2.7 renders as
# "Intents: SAFETY_CHECK + PFZ_NEAREST".
MULTI_MATCH_MARGIN = 0.02

# The phrasings each row is embedded as.
#
# NOT `RoutingRow.keywords`, and that distinction is the whole difficulty of
# this point. Tier 1's keywords are substrings chosen to be *matched* ("go to
# sea today", "nearest pfz"); e5 was trained on sentences, and embedding
# fragments packs every row into a 0.77–0.87 band where a fish curry recipe
# scores higher on PFZ_NEAREST (0.834) than a genuine safety paraphrase scores
# on SAFETY_CHECK (0.810). Measured, on 2026-09-20, before these were written.
#
# So each row gets whole questions, in the register a fisherman actually uses,
# deliberately avoiding the Tier-1 keywords — a phrasing that contains one
# would never reach this tier anyway.
ROW_PHRASINGS: dict[str, tuple[str, ...]] = {
    "SAFETY_CHECK": (
        "Is it safe for me to take my boat out today?",
        "Can I go fishing this morning without danger?",
        "Should I stay ashore or put out to sea?",
        "Are conditions all right for a small boat right now?",
        "Is the weather too dangerous to sail today?",
    ),
    "PFZ_NEAREST": (
        "Where should I drop my nets to find fish?",
        "Which area has the best catch right now?",
        "How far is the closest good fishing ground?",
        "Where are the shoals gathering today?",
        "Point me to the nearest productive waters.",
    ),
    "CONDITIONS": (
        "How rough is the water at the moment?",
        "What is the sea like right now?",
        "How high are the waves and how strong is the breeze?",
        "When is the water highest today?",
        "Describe the state of the sea this afternoon.",
    ),
    "HAZARD_ALERTS": (
        "Is there a thunderstorm on the way?",
        "Are there any dangerous weather warnings for my area?",
        "Is a big storm approaching the coast?",
        "Has any severe weather been announced?",
        "Should I be worried about a depression forming?",
    ),
    "ZONES_TO_AVOID": (
        "Which waters should I keep out of?",
        "Am I close to a line I should not cross?",
        "Where does the protected area begin?",
        "Which places are off limits for my boat?",
        "How near am I to another country's waters?",
    ),
    "ROUTE": (
        "What is the best way to sail from one harbour to another?",
        "Chart me a safe passage to the next port.",
        "Which way should I steer to get there?",
        "Help me work out my crossing.",
        "How do I get from here to the island safely?",
    ),
    "DIAGNOSTIC": (
        "Why am I catching so much less than before?",
        "What happened to all the fish this season?",
        "My hauls have got smaller — what is going on?",
        "Explain the drop in what we are landing.",
        "Why has the water stopped producing?",
    ),
    "REGULATORY": (
        "Am I permitted to fish here this month?",
        "Is there a rule stopping me going out now?",
        "When does the closed period start and end?",
        "Do I need a permit for these waters?",
        "Is fishing lawful in this area today?",
    ),
    "META": (
        "How do you know all this?",
        "Where did you get these numbers from?",
        "Can I rely on what you are telling me?",
        "Who built you and how certain are you?",
        "What is the evidence behind this answer?",
    ),
    "EXPORT": (
        "Give me this data as a file I can open.",
        "Can I save these figures to my computer?",
        "Send me the numbers in a spreadsheet.",
        "I want to take this information away with me.",
        "Produce a downloadable copy of this.",
    ),
    "SUBSCRIPTION": (
        "Let me know if this changes.",
        "Keep watch and warn me when it gets dangerous.",
        "Send me a message if a storm comes.",
        "Can you monitor this for me while I sleep?",
        "Ping me when the sea calms down.",
    ),
    "ADMINISTRATIVE": (
        "I want to change where my boat is registered.",
        "Update the details you hold about my vessel.",
        "Change the harbour I sail out of.",
        "Edit my personal settings.",
        "Fix the information on my account.",
    ),
}

_lock = threading.Lock()
_model: Any = None
_row_names: list[str] = []
_row_matrix: Any = None  # (n_phrasings, dim), L2-normalised
_row_index: list[int] = []  # phrasing index -> position in _row_names
_unavailable_reason: str | None = None


def _load() -> bool:
    """Loads the model and embeds the routing table's phrasings, once.

    Returns False (and remembers why) when the model cannot be had — a missing
    package, no local cache and no network. Never raises: a routing tier that
    takes the API down is worse than a routing tier that is absent."""
    global _model, _row_matrix, _row_names, _row_index, _unavailable_reason
    if _model is not None:
        return True
    if _unavailable_reason is not None:
        return False
    with _lock:
        if _model is not None:
            return True
        if _unavailable_reason is not None:
            return False
        try:
            from sentence_transformers import SentenceTransformer

            from orca.agents.planning import ROUTING_TABLE

            model = SentenceTransformer(MODEL_NAME)
            names: list[str] = []
            phrasings: list[str] = []
            index: list[int] = []
            for row in ROUTING_TABLE:
                examples = ROW_PHRASINGS.get(row.name)
                if not examples:
                    # A routing row with no phrasings is invisible to this
                    # tier. That is a bug in ROW_PHRASINGS, not a design, so
                    # it is logged rather than quietly tolerated — the failure
                    # mode is a whole intent that can never be paraphrased into.
                    logger.warning("routing row %s has no example phrasings — Tier 2 cannot match it", row.name)
                    continue
                position = len(names)
                names.append(row.name)
                for example in examples:
                    phrasings.append(f"passage: {example}")
                    index.append(position)
            matrix = model.encode(phrasings, normalize_embeddings=True, show_progress_bar=False)
        except Exception as exc:  # noqa: BLE001 — absence is a supported state
            _unavailable_reason = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "intent embeddings unavailable (%s) — Tier 2 falls back to word overlap",
                _unavailable_reason,
            )
            return False
        _model, _row_names, _row_matrix, _row_index = model, names, matrix, index
        logger.info("intent embeddings ready: %s, %d phrasings over %d rows", MODEL_NAME, len(phrasings), len(names))
        return True


def warm() -> bool:
    """Load at startup rather than on the first user's query, so nobody pays a
    cold model load inside a request. Called from the API lifespan; safe to
    call more than once, and safe to ignore the result."""
    return _load()


def available() -> bool:
    return _load()


def unavailable_reason() -> str | None:
    return _unavailable_reason


def match(query: str) -> list[tuple[str, float]] | None:
    """Routing rows this query is semantically close to, best first.

    `None` means the tier could not run at all (no model) — distinct from `[]`,
    which means it ran and found nothing. The caller must treat those
    differently: the first falls back to another scorer, the second is a real
    no-match and moves on to Tier 3.
    """
    if not query or not query.strip():
        return []
    if not _load():
        return None
    try:
        vector = _model.encode([f"query: {query}"], normalize_embeddings=True, show_progress_bar=False)[0]
        # Both sides are L2-normalised, so the dot product IS the cosine.
        scores = _row_matrix @ vector
    except Exception as exc:  # noqa: BLE001 — a runtime encode failure is a no-tier, not a 500
        logger.warning("intent embedding encode failed: %s", exc)
        return None

    # A row's score is its best-matching phrasing, not its average: a row with
    # six phrasings must not be penalised for the five that do not apply.
    best: dict[str, float] = {}
    for position, score in zip(_row_index, scores):
        name = _row_names[position]
        value = float(score)
        if value > best.get(name, -1.0):
            best[name] = value

    if not best:
        return []
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[0][1]
    if top < THRESHOLD:
        return []
    cutoff = max(THRESHOLD, top - MULTI_MATCH_MARGIN)
    return [(name, round(score, 3)) for name, score in ranked if score >= cutoff]


if __name__ == "__main__":
    if not available():
        print("intent embeddings unavailable:", unavailable_reason())
        raise SystemExit(0)

    # Paraphrases the Tier-1 keyword table does not contain, one per row, as a
    # smoke check — the full 30-paraphrase gate is the unit test.
    for phrase, expected in (
        ("can I take my boat out past the reef this evening", "SAFETY_CHECK"),
        ("where should I drop my nets for the best catch", "PFZ_NEAREST"),
        ("how rough is the water right now", "CONDITIONS"),
        ("is there a thunderstorm coming", "HAZARD_ALERTS"),
        ("am I allowed to fish here this month", "REGULATORY"),
    ):
        got = match(phrase)
        assert got is not None, "the tier loaded, so it must return a list"
        names = [n for n, _ in got]
        assert expected in names, f"{phrase!r} -> {got} (wanted {expected})"

    assert match("") == []
    print("intent embedding self-check ok")
