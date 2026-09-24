"""Chatbot plan C0.2(f) — every prompt that reaches /ask gets a written answer.

The rule (docs/ORCA_Chatbot_Response_Plan.md §1): a model writes the answer,
whatever the prompt and whichever provider is down; the model never changes the
verdict; and when no model at all can be reached, the answer is still never
blank and never only the bare verdict line (which the chat hides as a repeat of
its status row — that is how a 2026-09-24 Gemini outage produced an empty
Response on /ask).

Runs in CI: no data/, no network, no provider key. Providers are scripted
fakes behind `tiers.get_provider`; the chain, the narration fallback, the guard
writer and the cache rule are the real code.
"""
from __future__ import annotations

import pytest

from orca.agents import reporting
from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.llm import tiers

# The PS's three sample questions (docs/ORCA_PS_SIH26176_Problem_Statement.md),
# a greeting, an inland place, and a vernacular question.
PROMPTS = [
    "Where is the nearest Potential Fishing Zone today?",
    "Is it safe to venture into the sea tomorrow morning?",
    "What are the tide, weather, and sea conditions near my fishing location?",
    "hi",
    "sea conditions near Delhi",
    "நாளை காலை கடலுக்குச் செல்வது பாதுகாப்பானதா?",
]

_VERDICT = {
    "go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits",
    "readings": {"wave_height_m": 0.98, "wind_speed_ms": 4.4, "valid_time": "2026-09-24T12:00:00Z"},
}
_BARE_VERDICT = "GO: All Parameters Within Safe Operational Limits"
_TIMEOUT = RuntimeError("504 DEADLINE_EXCEEDED")
_BUSY = RuntimeError("503 UNAVAILABLE: the model is overloaded")


def _result(agent_name: str, outputs: dict) -> AgentResult:
    return AgentResult(
        agent_name=agent_name, query_id="q-1", reasoning_depth="SHALLOW", inputs_consumed={}, outputs=outputs,
        source_provenance=SourceProvenance(dataset="d", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(score="MEDIUM", rationale="r"),
    )


_RESULTS = [
    _result("geospatial", {"imbl_distance_nm": 47.6, "mpa_violation": False}),
    _result("ocean_analytics", {
        "tide": {"tidal_state": "FALLING", "station_name": "Thoothukudi",
                 "next_high": {"when": "2026-09-24T20:12:00Z", "height_m": 0.9}},
        "nearest_pfz": {"found": True, "distance_km": 6.5, "compass": "E", "valid_for": "2026-09-19",
                        "age_days": 5, "band": "hint"},
    }),
    _result("risk_assessment", _VERDICT),
]
_LOCATION = {"lat": 8.8, "lon": 78.3, "place_name": "Thoothukudi", "place_source": "gazetteer"}


class _Scripted:
    """One fake provider for every rung, answering per model id from a script:
    a string is a reply, an exception is a failure, a list is played in order."""

    def __init__(self, script: dict):
        self.script = script
        self.calls: list[tuple[str, float | None]] = []

    def complete(self, messages, *, model, **kw):
        self.calls.append((model, kw.get("timeout_s")))
        step = self.script[model]
        action = step.pop(0) if isinstance(step, list) else step
        if isinstance(action, Exception):
            raise action
        return action


@pytest.fixture
def providers(monkeypatch):
    monkeypatch.setenv("ORCA_LLM_MID_CHAIN", "gemini:primary,gemini:second,ollama:local")
    monkeypatch.delenv("ORCA_LLM_MID_BUDGET_S", raising=False)
    monkeypatch.delenv("ORCA_LLM_ENABLED", raising=False)
    monkeypatch.setattr(tiers, "_RETRY_BACKOFF_S", 0)

    def install(script: dict) -> _Scripted:
        fake = _Scripted(script)
        monkeypatch.setattr(tiers, "get_provider", lambda name: fake)
        return fake

    return install


# --- the chain --------------------------------------------------------------

def test_a_stalled_primary_is_not_retried_and_the_next_rung_answers(providers):
    fake = providers({"primary": _TIMEOUT, "second": "written by the second model"})
    client = tiers.llm("mid")
    assert client.complete([{"role": "user", "content": "x"}]) == "written by the second model"
    assert client.engine == "gemini · second (fallback)"
    assert [m for m, _ in fake.calls] == ["primary", "second"], "a timeout must not be retried on the same rung"


def test_a_busy_primary_is_retried_once_before_moving_on(providers):
    fake = providers({"primary": [_BUSY, "second try worked"], "second": "unused"})
    client = tiers.llm("mid")
    assert client.complete([{"role": "user", "content": "x"}]) == "second try worked"
    assert client.engine == "gemini · primary"
    assert [m for m, _ in fake.calls] == ["primary", "primary"]


def test_an_empty_reply_is_not_an_answer(providers):
    providers({"primary": "   ", "second": "a real answer"})
    assert tiers.llm("mid").complete([{"role": "user", "content": "x"}]) == "a real answer"


def test_the_local_rung_always_keeps_its_share_of_the_budget(providers, monkeypatch):
    monkeypatch.setenv("ORCA_LLM_MID_BUDGET_S", "40")
    fake = providers({"primary": _TIMEOUT, "second": _TIMEOUT, "local": "written locally"})
    client = tiers.llm("mid")
    assert client.complete([{"role": "user", "content": "x"}]) == "written locally"
    assert client.engine == "ollama · local (fallback)"
    hosted = [t for m, t in fake.calls if m != "local"]
    (local_timeout,) = [t for m, t in fake.calls if m == "local"]
    assert all(t is not None and t <= 40 - tiers._LOCAL_RESERVE_S for t in hosted)
    assert local_timeout >= tiers._LOCAL_RESERVE_S - 1


def test_every_rung_failing_names_every_reason(providers):
    providers({"primary": _TIMEOUT, "second": _BUSY, "local": RuntimeError("connection refused")})
    with pytest.raises(tiers.LLMUnavailable) as err:
        tiers.llm("mid").complete([{"role": "user", "content": "x"}])
    for rung in ("primary", "second", "local"):
        assert rung in err.value.reason


def test_a_chain_entry_splits_on_its_first_colon(monkeypatch):
    monkeypatch.setenv("ORCA_LLM_MID_CHAIN", "gemini:gemini-3.5-flash-lite, ollama:gemma4:e4b")
    assert tiers.chain_for("mid") == [("gemini", "gemini-3.5-flash-lite"), ("ollama", "gemma4:e4b")]


def _no_groq(monkeypatch) -> None:
    import os

    for name in [n for n in os.environ if n.startswith("GROQ_API_KEY")]:
        monkeypatch.delenv(name)


def test_only_the_answer_writing_tier_defaults_to_the_local_model(monkeypatch):
    _no_groq(monkeypatch)
    for tier in ("CHEAP", "MID", "REASONING"):
        monkeypatch.delenv(f"ORCA_LLM_{tier}_CHAIN", raising=False)
        monkeypatch.setenv(f"ORCA_LLM_{tier}_PROVIDER", "gemini")
        monkeypatch.setenv(f"ORCA_LLM_{tier}_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.delenv("ORCA_LLM_LOCAL_MODEL", raising=False)
    assert tiers.chain_for("mid") == [
        ("gemini", "gemini-3.5-flash-lite"), ("gemini", tiers._SECOND_GEMINI), ("ollama", tiers._LOCAL_MODEL),
    ]
    assert all(p != "ollama" for p, _ in tiers.chain_for("cheap"))
    assert all(p != "ollama" for p, _ in tiers.chain_for("reasoning"))


def test_a_machine_without_a_local_model_loses_nothing(providers, monkeypatch):
    """Not every teammate has Ollama or a GPU. There the local rung must be
    gone entirely — not a slow failure, and not a 20 s reserve cut out of the
    hosted rungs' budget."""
    monkeypatch.setattr(tiers, "_LOCAL_MISSING", {"local"})
    monkeypatch.setenv("ORCA_LLM_MID_BUDGET_S", "40")
    assert [p for p, _ in tiers.chain_for("mid")] == ["gemini", "gemini"]
    fake = providers({"primary": _TIMEOUT, "second": "written by the second model"})
    assert tiers.llm("mid").complete([{"role": "user", "content": "x"}]) == "written by the second model"
    assert fake.calls[0][1] == tiers._HOSTED_CAP_S, "no reserve held back for a model this machine does not have"


def test_the_startup_warm_up_decides_whether_the_local_rung_exists(monkeypatch):
    monkeypatch.setattr(tiers, "_LOCAL_MISSING", set())
    monkeypatch.setenv("ORCA_LLM_MID_CHAIN", "gemini:primary,ollama:local")

    class _NoOllama:
        def warm(self, model):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(tiers, "get_provider", lambda name: _NoOllama())
    tiers.warm_local_models()
    assert tiers.chain_for("mid") == [("gemini", "primary")]


def test_groq_keys_join_every_tier_right_after_the_primary(monkeypatch):
    _no_groq(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "k1")
    monkeypatch.delenv("ORCA_LLM_GROQ_MODEL", raising=False)
    for tier in ("cheap", "mid", "reasoning"):
        monkeypatch.delenv(f"ORCA_LLM_{tier.upper()}_CHAIN", raising=False)
        monkeypatch.setenv(f"ORCA_LLM_{tier.upper()}_PROVIDER", "gemini")
        monkeypatch.setenv(f"ORCA_LLM_{tier.upper()}_MODEL", "gemini-3.5-flash-lite")
        assert tiers.chain_for(tier)[1] == ("groq", tiers._GROQ_MODEL)  # type: ignore[arg-type]


def test_groq_keys_are_read_in_env_order_and_a_rate_limited_key_hands_on(monkeypatch):
    from orca.llm import registry

    _no_groq(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "first")
    monkeypatch.setenv("GROQ_API_KEY_2", "third, fourth")
    monkeypatch.setenv("GROQ_API_KEY_1", "second")
    assert registry.groq_keys() == ["first", "second", "third", "fourth"]

    used: list[str] = []

    class _Resp:
        def __init__(self, status: int):
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"{self.status_code}")

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "<think>hmm</think>Calm seas."}}]}

    class _Http:
        def post(self, url, headers, json, timeout):
            used.append(headers["Authorization"].split()[-1])
            return _Resp(429 if len(used) < 3 else 200)

    provider = registry.GroqProvider()
    provider._http = _Http()  # type: ignore[assignment]
    assert provider.complete([{"role": "user", "content": "x"}], model="m") == "Calm seas."
    assert used == ["first", "second", "third"]


# --- the answer ---------------------------------------------------------------

@pytest.mark.parametrize("prompt", PROMPTS)
def test_every_prompt_is_written_by_a_model_when_the_primary_is_down(providers, prompt):
    providers({"primary": _TIMEOUT, "second": _BUSY, "local": f"GO: calm at Thoothukudi, answering {prompt!r}"})
    engine: list[str] = []
    text = reporting.synthesize_narrative(prompt, _VERDICT, _RESULTS, user_location=_LOCATION, engine_out=engine)
    assert text.strip() and text.strip() != _BARE_VERDICT
    assert engine == ["ollama · local (fallback)"]


@pytest.mark.parametrize("prompt", PROMPTS)
def test_with_every_model_down_the_answer_is_never_blank_or_only_the_verdict(providers, prompt):
    providers({"primary": _TIMEOUT, "second": _BUSY, "local": RuntimeError("connection refused")})
    engine: list[str] = []
    text = reporting.synthesize_narrative(prompt, _VERDICT, _RESULTS, user_location=_LOCATION, engine_out=engine)
    assert text.startswith(_BARE_VERDICT), "the verdict still leads, unchanged"
    assert text.strip() != _BARE_VERDICT
    # The readings the verdict was computed from, not a restated verdict.
    for figure in ("waves 0.98 m", "wind 16 km/h", "47.6 nm", "6.5 km", "2026-09-19", "20:12 UTC"):
        assert figure in text, (figure, text)
    assert engine and engine[0].startswith("Deterministic")


def test_the_facts_paragraph_says_so_when_there_is_nothing_to_report():
    text = reporting.facts_paragraph({"go_no_go": "CAUTION", "reason": "Missing data"}, [])
    assert text.startswith("CAUTION: Missing data.") and "No further readings" in text


def test_an_unreadable_input_is_never_written_up_as_calm():
    verdict = {"go_no_go": "CAUTION", "reason": "Missing data", "readings": {"wave_height_m": None, "wind_speed_ms": None}}
    assert "waves" not in reporting.facts_paragraph(verdict, [])


# --- guard replies ------------------------------------------------------------

_OUT_OF_SCOPE = "I can't answer that. I only answer questions about conditions at sea off India."
_OUT_OF_RANGE = "That position is outside the sea area ORCA holds data for (5-25N, 66-96E)."


def test_a_greeting_gets_a_model_written_reply_not_a_refusal(providers):
    providers({"primary": "[SMALL_TALK] Hello! Ask me about the sea off your coast.", "second": "", "local": ""})
    text, engine, small_talk = reporting.write_guard_reply("hi", _OUT_OF_SCOPE, allow_small_talk=True)
    assert text == "Hello! Ask me about the sea off your coast."
    assert small_talk is True and engine == "gemini · primary"


def test_small_talk_is_only_recognised_where_the_guard_allows_it(providers):
    providers({"primary": "[SMALL_TALK] Hello!", "second": "", "local": ""})
    _, _, small_talk = reporting.write_guard_reply("hi", _OUT_OF_RANGE)
    assert small_talk is False


def test_a_guard_reply_may_repeat_the_guards_own_figures(providers):
    reply = "[REPLY] I only hold data between 5 and 25 N and 66 to 96 E — try a position in that area."
    providers({"primary": reply, "second": "", "local": ""})
    text, engine, _ = reporting.write_guard_reply("waves at 30N 60E", _OUT_OF_RANGE)
    assert text.startswith("I only hold data") and not engine.startswith("Deterministic")


def test_a_guard_reply_that_adds_a_figure_is_discarded(providers):
    """P1.3: a refusal carries no marine content. A reply inventing a wave
    height is not trusted — the guard's own text goes out instead."""
    providers({"primary": "[REPLY] Waves there are 2.5 m, but I can't help.", "second": "", "local": ""})
    text, engine, _ = reporting.write_guard_reply("tell me a joke", _OUT_OF_SCOPE, allow_small_talk=True)
    assert text == _OUT_OF_SCOPE and engine.startswith("Deterministic")


def test_with_no_model_a_guard_still_replies_with_its_own_text(providers):
    providers({"primary": _TIMEOUT, "second": _BUSY, "local": RuntimeError("connection refused")})
    text, engine, small_talk = reporting.write_guard_reply("hi", _OUT_OF_SCOPE, allow_small_talk=True)
    assert text == _OUT_OF_SCOPE and engine.startswith("Deterministic") and small_talk is False


# --- the cache ----------------------------------------------------------------

def test_an_answer_written_without_a_model_is_never_cached(monkeypatch):
    """Cached, an outage answer would be replayed for 30 minutes after the
    providers came back."""
    from orca import query_cache

    stored: list[str] = []

    class _Redis:
        def setex(self, key, ttl, value):
            stored.append(key)

    monkeypatch.setattr(query_cache, "redis_client", lambda: _Redis())
    query_cache.store("outage", {"response_engine": "Deterministic — provider unavailable (timeout)"})
    query_cache.store("written", {"response_engine": "gemini · gemini-3.5-flash-lite"})
    query_cache.store("older-shape", {})
    assert stored == ["written", "older-shape"]
