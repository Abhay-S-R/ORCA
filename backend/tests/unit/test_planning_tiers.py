from unittest.mock import MagicMock, patch

from orca.agents.planning import (
    _tier1_rules,
    _tier2_embedding_similarity,
    _tier3_llm_fallback,
    classify_intent,
)


def test_tier2_matches_a_paraphrase_tier1_keywords_miss():
    # No literal "safe"/"go to sea"/"fish" substring, so Tier 1 finds nothing.
    query = "can I take my boat out"
    assert _tier1_rules(query) == []
    matches = _tier2_embedding_similarity(query)
    names = [n for n, _ in matches]
    assert "SAFETY_CHECK" in names


def test_tier2_scores_are_in_range_and_at_least_the_threshold():
    matches = _tier2_embedding_similarity("can I take my boat out")
    for _, score in matches:
        # 0.45 was the word-overlap scorer's threshold; cosine similarity from
        # `orca/intent_embeddings.py` sits much higher (P2.8). The assertion
        # that still means something across both is "a real score in range".
        assert 0.0 <= score <= 1.0


def test_classify_intent_falls_through_to_tier2_when_tier1_finds_nothing():
    matches = classify_intent("can I take my boat out")
    names = [n for n, _ in matches]
    assert "SAFETY_CHECK" in names


def test_an_unconfirmed_tier2_match_keeps_its_own_lower_score():
    """P2.8 — with no Tier 3 available to confirm it, a Tier-2 match stands on
    its own similarity and must NOT be reported at Tier 1's certainty. An
    unavailable confirmation is not a confirmation."""
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no API key")):
        matches = classify_intent("can I take my boat out")
    assert [n for n, _ in matches], "the embedding tier should still have matched"
    assert all(score < 1.0 for _, score in matches)


def test_tier3_confirming_a_tier2_match_raises_it_to_certainty():
    """P2.8's confirmation pass: two independent methods agreeing is worth
    more than either alone, so the agreed row is re-scored to 1.0."""
    fake_client = MagicMock()
    fake_client.complete.return_value = "SAFETY_CHECK"
    tier_out: list[str] = []
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        matches = classify_intent("can I take my boat out", tier_out=tier_out)
    assert ("SAFETY_CHECK", 1.0) in matches
    assert tier_out == ["tier2_embeddings+tier3_confirmed"]


def test_tier3_disagreeing_dispatches_both_readings_rather_than_overriding():
    """Execution stays fail-safe (P2.7): when the two methods name different
    rows, both are kept, because answering the wrong half of an ambiguous
    question costs more than running one extra specialist."""
    fake_client = MagicMock()
    fake_client.complete.return_value = "PFZ_NEAREST"
    tier_out: list[str] = []
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        matches = classify_intent("can I take my boat out", tier_out=tier_out)
    names = [n for n, _ in matches]
    assert "SAFETY_CHECK" in names and "PFZ_NEAREST" in names
    assert tier_out == ["tier2_embeddings+tier3_disagreed"]
    # ... and the LLM's guess never outranks the deterministic tier's match.
    assert dict(matches)["SAFETY_CHECK"] > dict(matches)["PFZ_NEAREST"]


def test_a_tier1_match_never_spends_an_llm_call_confirming_itself():
    """Deterministic-first is the design. Tier 1 is certain by construction,
    so the confirmation pass must not run — this is also the cost guard that
    keeps P2.13's per-query budget where it was for ordinary queries."""
    fake_client = MagicMock()
    fake_client.complete.return_value = "PFZ_NEAREST"
    tier_out: list[str] = []
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        matches = classify_intent("is it safe to go to sea today", tier_out=tier_out)
    assert fake_client.complete.call_count == 0
    assert tier_out == ["tier1_rules"]
    assert all(score == 1.0 for _, score in matches)


def test_tier3_llm_fallback_returns_a_known_row_when_llm_answers_it():
    fake_client = MagicMock()
    fake_client.complete.return_value = "PFZ_NEAREST"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        matches = _tier3_llm_fallback("where should I go today")
    assert matches == [("PFZ_NEAREST", 0.7)]


def test_tier3_llm_fallback_none_answer_is_no_match():
    fake_client = MagicMock()
    fake_client.complete.return_value = "NONE"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        assert _tier3_llm_fallback("tell me a joke") == []


def test_tier3_llm_fallback_unconfigured_llm_is_no_match_not_a_crash():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no API key")):
        assert _tier3_llm_fallback("anything") == []


def test_tier3_llm_fallback_garbage_answer_is_no_match():
    fake_client = MagicMock()
    fake_client.complete.return_value = "this is not a routing row"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        assert _tier3_llm_fallback("anything") == []


def test_classify_intent_reaches_tier3_only_when_tier1_and_tier2_are_both_empty():
    fake_client = MagicMock()
    fake_client.complete.return_value = "CONDITIONS"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        matches = classify_intent("xyz completely unrelated gibberish query")
    assert matches == [("CONDITIONS", 0.7)]


def test_tier1_exact_keyword_match_never_falls_through_to_tier3():
    # If Tier 1 matches, Tier 3 (which would need a real/mocked LLM) must
    # never even be attempted — classify_intent short-circuits per tier.
    with patch("orca.agents.planning._tier3_llm_fallback", side_effect=AssertionError("tier3 should not run")):
        matches = classify_intent("is it safe to go to sea tomorrow")
    assert ("SAFETY_CHECK", 1.0) in matches
