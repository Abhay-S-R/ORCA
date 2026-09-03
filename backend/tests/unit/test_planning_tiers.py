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
        assert 0.45 <= score <= 1.0


def test_classify_intent_falls_through_to_tier2_when_tier1_finds_nothing():
    matches = classify_intent("can I take my boat out")
    names = [n for n, _ in matches]
    assert "SAFETY_CHECK" in names
    # Tier 2 confidence is real word-overlap, never Tier 1's flat 1.0.
    assert all(score < 1.0 for _, score in matches)


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
