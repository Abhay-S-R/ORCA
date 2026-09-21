"""P2.1 (`R-JUDGE-1`) — what actually computed a span.

Every agent span reports an **engine**, not only the three nodes that may call
an LLM. Before this, `model` was populated for LLM agents and left `null` for
everyone else, so "no AI in our safety core" was a claim made in prose next to
a UI that said nothing at all about the safety node. A judge's first question
is which parts are a model and which are arithmetic; this is the field that
answers it without anyone having to be believed.

Two sources, in order:

1. **What the agent recorded.** `AgentResult.engine` — the authoritative one,
   because the LLM-backed agents are *conditionally* LLM-backed and a static
   table would have to guess. Reporting and the Critic fall back to a
   deterministic template whenever the provider is absent, disabled (P2.11) or
   rate-limited (P2.13), and Planning reaches its model only on a Tier-3
   fallback. On exactly those runs the honest label is `Deterministic`, not a
   model id that never ran.
2. **The static table below**, for the agents that are deterministic (or
   IndicTrans2) by construction and have nothing to decide at runtime.

The strings are user-facing: they are rendered verbatim on the `/ask` activity
strip and the `/reasoning` inspector.
"""
from __future__ import annotations

import os

DETERMINISTIC = "Deterministic"

# Agent 1's real weights (orca/agents/language.py `IndicTrans2Backend`) — local
# inference, no API, which is the point worth showing: the translation half of
# the pipeline is not a cloud model either.
INDICTRANS2 = "IndicTrans2 · indictrans2-indic-en-dist-200M (local)"

# Which tier each LLM-capable agent draws from (plan §3.2). Unchanged from the
# two copies of this ladder that previously lived in `api/main.py` and
# `api/trace_routes.py` — they are now both this dict.
AGENT_TIER: dict[str, str] = {
    "planning": "cheap",          # Tier 3 only, and only when 1 and 2 find nothing
    "reporting": "mid",
    "ocean_analytics": "reasoning",  # reserved; see LLM_AGENTS below — nothing uses it yet
    "critic": "reasoning",
}

# The agents that *may* call a model. Not the agents that always do — see the
# module docstring; `engine_for` prefers what the agent recorded.
#
# **`ocean_analytics` is deliberately NOT here, and that is a correction.**
# Both previous copies of this set (`api/main.py` and `api/trace_routes.py`)
# listed it, on the strength of plan §3.2 assigning Agent 5 a reasoning tier
# for its DEEP catch-decline diagnosis. That diagnosis is deterministic:
# `orca/agents/ocean_analytics.py` imports nothing from `orca.llm` and says so
# in its own docstring ("No LLM call anywhere in this module"). So every Ocean
# Analytics span has been reporting `used_llm: true` and a Gemini model id for
# work that is arithmetic and table lookups — the exact kind of untraceable
# claim P2.1 exists to remove, pointing the wrong way. If a DEEP LLM pass is
# ever added there, it must record its own `engine` like Reporting and the
# Critic do, and be added back here in the same change.
LLM_AGENTS: frozenset[str] = frozenset({"reporting", "critic"})

# Deterministic *by construction*, named individually rather than by
# "everything else" so that a new node has to make a deliberate choice here.
#
# The three LLM-capable agents are deliberately absent. They set their own
# `engine` at runtime, and for a row that predates that field the honest
# fallback is the model they would have used, NOT `Deterministic` — see
# `engine_for`. Labelling a Reporting span deterministic because nobody
# recorded otherwise would overclaim in the one direction that matters: it
# makes ORCA look more model-free than it is, which is precisely the claim a
# judge is entitled to test. Planning stays here because it *is* deterministic
# in every case but a Tier-3 fallback, and it records that case itself.
_STATIC_ENGINE: dict[str, str] = {
    "language_ingress": INDICTRANS2,
    "language_egress": INDICTRANS2,
    "distress": DETERMINISTIC,
    "distress_check": DETERMINISTIC,
    "planning": DETERMINISTIC,
    "marine_data_discovery": DETERMINISTIC,
    "weather_intelligence": DETERMINISTIC,
    "geospatial": DETERMINISTIC,
    "risk_assessment": DETERMINISTIC,
    "visualization": DETERMINISTIC,
    # Arithmetic and table lookups only — verified against the module, not
    # assumed from the tier table. See LLM_AGENTS above.
    "ocean_analytics": DETERMINISTIC,
}

_DEFAULT_MODEL = "gemini-3.5-flash-lite"


def model_for_tier(tier: str | None) -> str | None:
    """The model id a tier resolves to, read from env exactly as
    `orca/llm/tiers.py` reads it — one ladder, so a span can never name a
    model the call would not have used."""
    if not tier:
        return None
    return os.environ.get(f"ORCA_LLM_{tier.upper()}_MODEL") or _DEFAULT_MODEL


def provider_for_tier(tier: str | None) -> str | None:
    if not tier:
        return None
    return os.environ.get(f"ORCA_LLM_{tier.upper()}_PROVIDER") or "gemini"


def llm_engine(tier: str) -> str:
    """The label for a span that really did reach a model."""
    return f"{provider_for_tier(tier)} · {model_for_tier(tier)}"


def deterministic(why: str) -> str:
    """A deterministic label that says *why* it is deterministic — "the
    provider is off", "the tier never ran", "rate-limited". A fallback that is
    not disclosed is a lie (plan principle 3), and a bare `Deterministic` on
    Reporting would read as a design choice rather than a degraded run."""
    return f"{DETERMINISTIC} — {why}"


def engine_for(agent_name: str, recorded: str | None = None) -> str:
    """What to render for this span. `recorded` is `AgentResult.engine` as it
    reached the trace entry; absent (an older row, or an agent with nothing to
    decide) falls to the static table, and an unknown agent is reported
    `Deterministic` rather than blank — an unlabelled node is the exact
    ambiguity this point exists to remove."""
    if recorded:
        return recorded
    static = _STATIC_ENGINE.get(agent_name)
    if static is not None:
        return static
    if agent_name in LLM_AGENTS:
        # No recorded engine on an LLM-capable agent: an older trace row, from
        # before agents recorded this. Report the model it would have used —
        # never `Deterministic`, which would be an unearned claim.
        return llm_engine(AGENT_TIER[agent_name])
    return DETERMINISTIC


def used_llm(agent_name: str, engine: str | None = None) -> bool:
    """Whether this span actually reached a model. Reads the engine label when
    there is one — a Reporting run that fell back to its template did not use
    an LLM, whatever the agent's name is in `LLM_AGENTS`."""
    if engine:
        return not engine.startswith(DETERMINISTIC) and engine != INDICTRANS2
    return agent_name in LLM_AGENTS


if __name__ == "__main__":
    assert engine_for("risk_assessment") == DETERMINISTIC
    assert engine_for("geospatial") == DETERMINISTIC
    assert engine_for("visualization") == DETERMINISTIC
    assert engine_for("language_ingress") == INDICTRANS2
    assert engine_for("language_egress") == INDICTRANS2
    # A recorded engine always wins over the table.
    assert engine_for("reporting", "gemini · gemini-3.5-flash-lite") == "gemini · gemini-3.5-flash-lite"
    # A Reporting run that fell back records it, and the recorded value wins.
    assert engine_for("reporting", deterministic("provider disabled")).startswith(DETERMINISTIC)
    # ... but an UNRECORDED one must not be claimed deterministic: an older
    # trace row says nothing about the engine, and guessing "no model" is the
    # one guess that flatters ORCA's central claim.
    assert not engine_for("reporting").startswith(DETERMINISTIC)
    assert engine_for("reporting") == llm_engine("mid")
    assert engine_for("critic") == llm_engine("reasoning")
    # Agent 5 runs no model today, whatever the tier table reserves for it.
    assert engine_for("ocean_analytics") == DETERMINISTIC
    assert used_llm("ocean_analytics") is False
    # Planning is deterministic unless Tier 3 ran, and it records that case.
    assert engine_for("planning") == DETERMINISTIC
    # An unknown node is deterministic, never blank.
    assert engine_for("some_new_node") == DETERMINISTIC
    assert used_llm("reporting", "gemini · x") is True
    assert used_llm("reporting", deterministic("provider disabled")) is False
    assert used_llm("language_ingress", INDICTRANS2) is False
    assert used_llm("risk_assessment") is False
    print("engines self-check ok")
