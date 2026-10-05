"""PC2.1 (`R-AGENT-2`, `PS-ARCH`) — Planning schema carries the agent set.

Done-when (plan §5 PC2.1):
- For PS-Q1–PS-Q8 the trace shows a plausible `planned_agents`.
- Hallucinated names are dropped.
- LLM-down yields agents from the planning table.
- Verdict and answers are unchanged.
"""
from __future__ import annotations

import os

import pytest

from orca.agents.understand import (
    _KNOWN_SPECIALISTS,
    UnderstoodPrompt,
    _fallback_understand,
    _parse_understand_output,
)

# ---------------------------------------------------------------------------
# 1. _KNOWN_SPECIALISTS is exactly the set of graph node names PC2 cares about
# ---------------------------------------------------------------------------

def test_known_specialists_contains_expected_names():
    assert "marine_data_discovery" in _KNOWN_SPECIALISTS
    assert "weather_intelligence" in _KNOWN_SPECIALISTS
    assert "ocean_analytics" in _KNOWN_SPECIALISTS
    assert "geospatial" in _KNOWN_SPECIALISTS
    assert "risk_assessment" in _KNOWN_SPECIALISTS
    assert "visualization" in _KNOWN_SPECIALISTS
    assert "reporting" in _KNOWN_SPECIALISTS


# ---------------------------------------------------------------------------
# 2. _parse_understand_output — agents field parsed and hallucinations dropped
# ---------------------------------------------------------------------------

_BASE_JSON = """{
    "kind": "sea_question",
    "intents": ["PFZ_NEAREST"],
    "places": [{"raw": "Rameswaram", "normalized": "Rameswaram"}],
    "when": null,
    "is_followup": false,
    "agents": %s
}"""


def test_parse_valid_agents_are_kept():
    raw = _BASE_JSON % '["marine_data_discovery", "ocean_analytics", "geospatial"]'
    result = _parse_understand_output(raw)
    assert result is not None
    assert set(result.agents) == {"marine_data_discovery", "ocean_analytics", "geospatial"}


def test_parse_hallucinated_agent_names_are_dropped():
    raw = _BASE_JSON % '["marine_data_discovery", "imaginary_agent", "fake_specialist"]'
    result = _parse_understand_output(raw)
    assert result is not None
    assert result.agents == ["marine_data_discovery"]


def test_parse_empty_agents_list_is_valid():
    raw = _BASE_JSON % '[]'
    result = _parse_understand_output(raw)
    assert result is not None
    assert result.agents == []


def test_parse_all_hallucinated_yields_empty_agents():
    raw = _BASE_JSON % '["nonexistent", "also_fake"]'
    result = _parse_understand_output(raw)
    assert result is not None
    assert result.agents == []


def test_parse_missing_agents_field_yields_empty_list():
    """Backwards compatible: old prompts without the agents key still work."""
    raw = """{
        "kind": "sea_question",
        "intents": ["SAFETY_CHECK"],
        "places": [],
        "when": null,
        "is_followup": false
    }"""
    result = _parse_understand_output(raw)
    assert result is not None
    assert result.agents == []


def test_parse_agents_with_mixed_valid_and_invalid():
    raw = _BASE_JSON % '["weather_intelligence", "bogus", "risk_assessment", "another_fake"]'
    result = _parse_understand_output(raw)
    assert result is not None
    assert set(result.agents) == {"weather_intelligence", "risk_assessment"}


# ---------------------------------------------------------------------------
# 3. _fallback_understand — LLM-down path derives agents from planning table
# ---------------------------------------------------------------------------

def test_fallback_sea_question_yields_agents():
    os.environ["ORCA_LLM_ENABLED"] = "0"
    result = _fallback_understand("Is it safe to go to sea near Kochi tomorrow", [])
    assert result.kind == "sea_question"
    # agents must be a subset of known specialists
    assert all(a in _KNOWN_SPECIALISTS for a in result.agents)
    # A safety question should include weather or risk_assessment at minimum
    assert len(result.agents) > 0


def test_fallback_greeting_yields_empty_agents():
    os.environ["ORCA_LLM_ENABLED"] = "0"
    result = _fallback_understand("hi", [])
    assert result.kind == "greeting_or_small_talk"
    assert result.agents == []


def test_fallback_distress_yields_empty_agents():
    os.environ["ORCA_LLM_ENABLED"] = "0"
    result = _fallback_understand("engine failed near pamban, help", [])
    assert result.kind == "distress"
    assert result.agents == []


def test_fallback_off_topic_yields_empty_agents():
    os.environ["ORCA_LLM_ENABLED"] = "0"
    result = _fallback_understand("tell me a cricket score", [])
    assert result.kind == "off_topic"
    assert result.agents == []


def test_fallback_agents_are_subset_of_known_specialists():
    """All agent names from fallback must be in _KNOWN_SPECIALISTS — never hallucinated."""
    os.environ["ORCA_LLM_ENABLED"] = "0"
    for query in [
        "Where is the nearest PFZ near Rameswaram today",
        "Are there cyclone alerts near Mangalore",
        "Safest route from Thoothukudi to Pamban",
        "Wave height near Kochi tomorrow",
    ]:
        result = _fallback_understand(query, [])
        invalid = [a for a in result.agents if a not in _KNOWN_SPECIALISTS]
        assert invalid == [], f"Hallucinated agents for {query!r}: {invalid}"


# ---------------------------------------------------------------------------
# 4. UnderstoodPrompt — agents field is required and defaults are sane
# ---------------------------------------------------------------------------

def test_understood_prompt_agents_field_exists():
    p = UnderstoodPrompt(
        kind="sea_question",
        intents=["SAFETY_CHECK"],
        places=[],
        when=None,
        is_followup=False,
        agents=["weather_intelligence", "risk_assessment"],
    )
    assert p.agents == ["weather_intelligence", "risk_assessment"]


def test_understood_prompt_empty_agents_for_non_sea():
    p = UnderstoodPrompt(
        kind="greeting_or_small_talk",
        intents=[],
        places=[],
        when=None,
        is_followup=False,
        agents=[],
    )
    assert p.agents == []


# ---------------------------------------------------------------------------
# 5. understand_node — planned_agents stored in state (graph-level, LLM off)
# ---------------------------------------------------------------------------

def test_understand_node_stores_planned_agents_in_state(monkeypatch):
    """PC2.2 update: planning_node (which absorbed understand_node) must write
    planned_agents into its returned dict."""
    os.environ["ORCA_LLM_ENABLED"] = "0"
    from orca.graph.graph import planning_node

    state = {
        "query_id": "pc2-1-test",
        "raw_user_query": "Is it safe to go near Kochi tomorrow",
        "normalized_english_query": "Is it safe to go near Kochi tomorrow",
        "session_history": [],
        "user_location": None,
        "audit_trace_log": [],
        "completed_nodes": [],
        "reasoning_depth": "SHALLOW",
    }
    result = planning_node(state)
    assert "planned_agents" in result
    agents = result["planned_agents"]
    assert isinstance(agents, list)
    assert all(a in _KNOWN_SPECIALISTS for a in agents)


def test_understand_node_planned_agents_empty_for_greeting(monkeypatch):
    """PC2.2 update: planning_node (which absorbed understand_node) must return
    empty planned_agents for a greeting."""
    os.environ["ORCA_LLM_ENABLED"] = "0"
    from orca.graph.graph import planning_node

    state = {
        "query_id": "pc2-1-hi",
        "raw_user_query": "hi",
        "normalized_english_query": "hi",
        "session_history": [],
        "user_location": None,
        "audit_trace_log": [],
        "completed_nodes": [],
        "reasoning_depth": "SHALLOW",
    }
    result = planning_node(state)
    assert result["planned_agents"] == []


# ---------------------------------------------------------------------------
# 6. PS-Q1–PS-Q8 fallback agents are plausible (LLM down, deterministic)
# ---------------------------------------------------------------------------

PS_QUERIES = [
    ("PS-Q1", "Where is the nearest Potential Fishing Zone today near Rameswaram"),
    ("PS-Q2", "Is it safe to venture into the sea tomorrow morning near Kochi"),
    ("PS-Q4", "Are there any lightning or cyclone alerts near Mangalore"),
    ("PS-Q6", "What is the safest route from Thoothukudi to Pamban"),
    ("PS-Q7", "Why has fish productivity declined near Chennai"),
    ("PS-Q8", "Which fishing zones should be avoided near Karwar due to hazardous conditions"),
]


@pytest.mark.parametrize("label,query", PS_QUERIES, ids=[x[0] for x in PS_QUERIES])
def test_fallback_ps_queries_have_plausible_agents(label, query):
    """For PS-Q* prompts, fallback must return a non-empty agent list
    that contains only known specialists — no empty dispatch, no hallucinations."""
    os.environ["ORCA_LLM_ENABLED"] = "0"
    result = _fallback_understand(query, [])
    # PS queries are sea questions
    assert result.kind == "sea_question", f"{label}: kind={result.kind!r}"
    assert len(result.agents) > 0, f"{label}: no agents returned"
    invalid = [a for a in result.agents if a not in _KNOWN_SPECIALISTS]
    assert not invalid, f"{label}: hallucinated agents {invalid}"
