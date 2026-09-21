"""P2.8 (`R-PS-1`) — the Done-when gate: "30 paraphrases the Tier-1 table does
not contain route correctly without Tier 3."

Every query below is checked to contain **no Tier-1 keyword** before it is
checked to route, by `test_no_paraphrase_here_is_a_tier_1_match`. That test is
the one that keeps this file honest: without it, someone could satisfy the gate
by quietly adding keywords to `ROUTING_TABLE` and the embedding tier would
never be exercised at all.

Nothing here calls an LLM. `classify_intent_deterministic` is tiers 1 and 2
only, which is the whole claim being tested — these route on their own words,
with no paid confirmation pass behind them.
"""
from __future__ import annotations

import pytest

from orca import intent_embeddings
from orca.agents.planning import ROUTING_TABLE, classify_intent_deterministic

pytestmark = pytest.mark.skipif(
    not intent_embeddings.available(),
    reason=f"sentence-transformers model unavailable: {intent_embeddings.unavailable_reason()}",
)

# 30 paraphrases, at least two per routing row that has phrasings. Written in
# the register the query actually arrives in — a fisherman's, not a
# specification's — and deliberately sharing no keyword with Tier 1.
PARAPHRASES: tuple[tuple[str, str], ...] = (
    # SAFETY_CHECK
    ("can I take my boat out past the reef this evening", "SAFETY_CHECK"),
    ("should I stay ashore this morning", "SAFETY_CHECK"),
    ("is the water too dangerous for my small craft", "SAFETY_CHECK"),
    # PFZ_NEAREST
    ("where should I drop my nets for the best catch", "PFZ_NEAREST"),
    ("which stretch of water has the most fish right now", "PFZ_NEAREST"),
    ("point me towards the closest productive ground", "PFZ_NEAREST"),
    # CONDITIONS
    ("how rough is the water right now", "CONDITIONS"),
    ("what is the state of the sea this afternoon", "CONDITIONS"),
    ("how strong is the breeze out there", "CONDITIONS"),
    # HAZARD_ALERTS
    ("is there a thunderstorm coming", "HAZARD_ALERTS"),
    ("has any severe weather been announced for my coast", "HAZARD_ALERTS"),
    ("should I worry about a depression forming", "HAZARD_ALERTS"),
    # ZONES_TO_AVOID
    ("which waters should I keep well clear of", "ZONES_TO_AVOID"),
    ("how near am I to another country's waters", "ZONES_TO_AVOID"),
    ("where does the protected stretch begin", "ZONES_TO_AVOID"),
    # ROUTE
    ("chart me a safe crossing to the next harbour", "ROUTE"),
    ("which way should I steer to reach the island", "ROUTE"),
    # DIAGNOSTIC
    ("why are we landing fewer prawns lately", "DIAGNOSTIC"),
    ("what happened to all the fish this season", "DIAGNOSTIC"),
    ("my hauls have got smaller, explain it", "DIAGNOSTIC"),
    # REGULATORY
    ("am I permitted to fish here this month", "REGULATORY"),
    ("when does the closed period start and end", "REGULATORY"),
    ("do I need a permit for these waters", "REGULATORY"),
    # META
    ("how certain are you about that", "META"),
    ("what is the evidence behind this answer", "META"),
    # EXPORT
    ("give me this data as a file I can open", "EXPORT"),
    ("save these figures to my computer", "EXPORT"),
    # SUBSCRIPTION
    ("tell me if the wind picks up overnight", "SUBSCRIPTION"),
    ("keep watch and warn me when it turns dangerous", "SUBSCRIPTION"),
    # ADMINISTRATIVE
    ("update the details you hold about my vessel", "ADMINISTRATIVE"),
)


def test_there_are_thirty_paraphrases() -> None:
    assert len(PARAPHRASES) == 30


def test_no_paraphrase_here_is_a_tier_1_match() -> None:
    """The gate is only meaningful if Tier 1 cannot answer these. If this
    fails, a keyword was added that makes one of them trivial — move the
    paraphrase, do not relax the test."""
    offenders = []
    for query, _ in PARAPHRASES:
        lowered = query.lower()
        for row in ROUTING_TABLE:
            for keyword in row.keywords:
                if keyword in lowered:
                    offenders.append((query, row.name, keyword))
    assert offenders == [], f"these paraphrases are plain Tier-1 matches: {offenders}"


@pytest.mark.parametrize(("query", "expected"), PARAPHRASES)
def test_paraphrase_routes_without_an_llm(query: str, expected: str) -> None:
    matches = classify_intent_deterministic(query)
    assert matches, f"{query!r} routed to nothing — it would have fallen through to Tier 3"
    names = [name for name, _ in matches]
    assert expected in names, f"{query!r} routed to {names}, wanted {expected}"


def test_the_tier_reports_absence_differently_from_no_match() -> None:
    """`None` (the tier could not run) and `[]` (it ran and matched nothing)
    must stay distinguishable — planning.py falls back to word overlap on the
    first and moves to Tier 3 on the second."""
    assert intent_embeddings.match("") == []
    assert intent_embeddings.match("   ") == []


def test_every_routing_row_with_agents_can_be_paraphrased_into() -> None:
    """A row with no example phrasings is invisible to Tier 2 forever. This
    catches a row being added to ROUTING_TABLE without one."""
    missing = [
        row.name for row in ROUTING_TABLE
        if row.name not in intent_embeddings.ROW_PHRASINGS
    ]
    assert missing == [], f"routing rows with no Tier-2 phrasings: {missing}"
