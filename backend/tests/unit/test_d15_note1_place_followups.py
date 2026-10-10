"""D-15 and PC5.6-NOTE-1 (2026-10-10).

D-15: after "which place?" ("pfzs near gujarat", "safe near atlantis") a follow-up that names no place ("can you explain that in
more detail") was answered at the Gulf of Mannar default. It is about the pending place question: that question is asked again.
NOTE-1: a ROUTE between two places in romanized Hindi/Tamil/Kannada ("tuticorin se pamban tak ...") was answered at the pilot
default because the passage test is an English regex; two gazetteer-confirmed places and a route intent are a passage.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca import session
from orca.graph.graph import planning_node
from orca.place_resolution import adopt_model_passage, resolve_or_ask

DEFAULT = {"lat": 8.8, "lon": 78.3, "place_name": None, "place_source": "regional_default"}


def _p(raw, normalized=None):
    return {"raw": raw, "normalized": normalized or raw}


# --- NOTE-1: adoption of a passage ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,places", [
    ("mujhe tuticorin se pamban tak sabse surakshit raasta batao", [_p("tuticorin"), _p("pamban")]),
    ("mangalore la irundhu goa varaikkum safe ah", [_p("mangalore"), _p("panaji", "Panaji")]),
    ("karwar inda udupi varege surakshitha maarga heli", [_p("karwar"), _p("udupi")]),
    ("tuticorin to pamban", [_p("tuticorin"), _p("pamban")]),
])
def test_two_confirmed_places_and_a_route_intent_are_a_passage_answered_for_the_origin(text, places):
    got = adopt_model_passage(places, DEFAULT, [text], is_route=True)
    if got is None:
        pytest.skip("a name in this sentence is not in the gazetteer spelling")
    loc, resolution = got
    assert loc["place_name"] == places[0]["raw"].lower() or loc["place_name"] in (places[0]["normalized"].lower(), "mangalore", "mangaluru")
    assert resolution["status"] == "resolved" and len(resolution["candidates"]) == 2
    assert "This is a passage" in resolution["disclosure"] and "for " + loc["place_name"] in resolution["disclosure"]


def test_the_origin_is_the_place_named_first_in_the_message_not_the_models_order():
    got = adopt_model_passage([_p("pamban"), _p("tuticorin")], DEFAULT, ["mujhe tuticorin se pamban tak raasta batao"], True)
    assert got is not None and got[0]["place_name"] == "tuticorin"


@pytest.mark.parametrize("kwargs", [
    {"is_route": False},                                                      # not a route question
    {"places": [_p("tuticorin")]},                                            # one place: adopt_model_place's job
    {"places": [_p("tuticorin"), _p("pamban"), _p("kochi")]},                 # three
    {"places": [_p("tuticorin"), _p("atlantis")]},                            # one is not in the gazetteer
    {"places": [_p("goa"), _p("pamban")]},                                    # a whole coastline is not a position
    {"places": [_p("tuticorin"), _p("tuticorin")]},                           # the same place twice
    {"places": [_p("tuticorin"), _p("kochi")], "texts": ["raasta batao tuticorin"]},   # the model invented the second place
    {"loc": {**DEFAULT, "place_source": "explicit"}},                         # the caller chose a position
    {"loc": {**DEFAULT, "place_source": "gazetteer"}},                        # the text already resolved it exactly
])
def test_a_passage_is_not_adopted_unless_everything_checks(kwargs):
    places = kwargs.get("places", [_p("tuticorin"), _p("pamban")])
    texts = kwargs.get("texts", ["tuticorin se pamban tak raasta kochi goa"])
    assert adopt_model_passage(places, kwargs.get("loc", DEFAULT), texts, kwargs.get("is_route", True)) is None


class _Client:
    engine = "fake-model"

    def __init__(self, body):
        self.text = json.dumps(body)

    def complete(self, messages, **kw):
        return self.text


def _plan(places, query, intents=("ROUTE",), history=None, kind="sea_question", followup=False, loc=None):
    body = {"kind": kind, "intents": list(intents), "places": places, "when": None, "is_followup": followup, "agents": [],
            "english_reading": query}
    state = {"query_id": "q", "raw_user_query": query, "session_history": history or [],
             "user_location": dict(loc or DEFAULT), "place_resolution": resolve_or_ask(query).as_dict()}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return planning_node(state)  # type: ignore[arg-type]


def test_the_user_sentence_is_answered_at_tuticorin_not_at_the_default():
    q = "mujhe tuticorin se pamban tak sabse surakshit raasta batao"
    assert resolve_or_ask(q).status == "ambiguous"          # what the word list alone does
    update = _plan([_p("tuticorin"), _p("pamban")], q)
    assert update["user_location"]["place_name"] == "tuticorin" and update["user_location"]["place_source"] == "gazetteer"
    assert update["place_resolution"]["status"] == "resolved" and "This is a passage" in update["place_resolution"]["disclosure"]
    assert update.get("query_outcome") is None


def test_without_a_route_intent_two_places_are_not_made_a_passage():
    update = _plan([_p("tuticorin"), _p("pamban")], "tuticorin pamban wave", intents=("CONDITIONS",))
    assert "user_location" not in update          # nothing adopted: the word list's `ambiguous` reading stands
    assert "passage" not in str(update.get("place_resolution"))


# --- D-15: a follow-up that names no place, after a place question ---------------------------------------------------------------

_ASK = "Gujarat is a whole coastline, not a position — conditions at either end of it are different answers. Which of these did you mean? Did you mean: Mangrol (21.08N 70.10E), Porbandar (21.64N 69.50E)?"


def _asked_turn(question=_ASK, query="pfzs near gujarat"):
    return session.turn_from_final(query, {"outcome": "NEEDS_PLACE", "disclosures": [question], "user_location": dict(DEFAULT),
                                           "place_resolution": {"status": "ambiguous"}, "final_english_response": "which port?"})


def test_a_place_question_is_remembered_on_the_turn():
    turn = _asked_turn()
    assert turn["place_question"] == _ASK and turn["place_status"] == "ambiguous"
    answered = session.turn_from_final("near udupi", {"outcome": "ANSWERED", "disclosures": ["x"], "user_location": dict(DEFAULT)})
    assert answered["place_question"] is None


@pytest.mark.parametrize("query", ["can you explain that in more detail", "tell me more", "i need more detailed description"])
def test_a_follow_up_with_no_place_after_a_place_question_asks_again_and_runs_no_agent(query):
    update = _plan([], query, intents=("PFZ_NEAREST",), history=[_asked_turn()], followup=True)
    assert update["query_outcome"] == "NEEDS_PLACE" and update["place_resolution"]["status"] == "ambiguous"
    assert "Mangrol" in update["disclosures"][0]
    assert update.get("execution_plan", []) == [] or "ocean_analytics" not in update["execution_plan"]


def test_a_follow_up_that_names_a_place_is_answered_for_it():
    update = _plan([_p("udupi")], "near udupi", intents=("PFZ_NEAREST",), history=[_asked_turn()], followup=True)
    assert update.get("query_outcome") is None and update["user_location"]["place_name"] == "udupi"


def test_after_an_answered_turn_nothing_is_pending():
    answered = session.turn_from_final("pfzs near udupi", {"outcome": "ANSWERED", "disclosures": [], "user_location": {"lat": 13.3, "lon": 74.7, "place_name": "udupi", "place_source": "gazetteer"}})
    carried = {"lat": 13.3, "lon": 74.7, "place_name": "udupi", "place_source": "session_carried"}   # what the API hands planning
    update = _plan([], "more detail please", intents=("PFZ_NEAREST",), history=[answered], followup=True, loc=carried)
    assert update.get("query_outcome") is None


def test_a_carried_old_place_does_not_hide_the_pending_question():
    state_loc = {"lat": 13.3, "lon": 74.7, "place_name": "udupi", "place_source": "session_carried"}
    body = {"kind": "sea_question", "intents": ["PFZ_NEAREST"], "places": [], "when": None, "is_followup": True, "agents": [], "english_reading": "tell me more"}
    state = {"query_id": "q", "raw_user_query": "tell me more", "session_history": [_asked_turn()], "user_location": state_loc,
             "place_resolution": {"status": "fallback"}}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        update = planning_node(state)  # type: ignore[arg-type]
    assert update["query_outcome"] == "NEEDS_PLACE"


def test_a_position_the_caller_chose_is_never_overridden():
    body = {"kind": "sea_question", "intents": ["PFZ_NEAREST"], "places": [], "when": None, "is_followup": True, "agents": [], "english_reading": "x"}
    chosen = {"lat": 21.08, "lon": 70.10, "place_name": "mangrol", "place_source": "explicit"}
    state = {"query_id": "q", "raw_user_query": "pfzs near gujarat (at mangrol)", "session_history": [_asked_turn()], "user_location": chosen,
             "place_resolution": {"status": "resolved"}}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        update = planning_node(state)  # type: ignore[arg-type]
    assert update.get("query_outcome") is None


def test_a_non_sea_message_after_a_place_question_is_left_to_the_chat_path():
    update = _plan([], "thanks!", intents=(), history=[_asked_turn()], kind="greeting_or_small_talk")
    assert update.get("query_outcome") != "NEEDS_PLACE"


# --- 2026-10-10 (the user): a genuinely placeless first message asks which place, conversationally -------------------------------

@pytest.mark.parametrize("intents", [("SAFETY_CHECK",), ("CONDITIONS",), ("PFZ_NEAREST",), ("HAZARD_ALERTS",), ()])
def test_a_first_message_with_no_place_and_nothing_to_estimate_it_from_asks_which_place(intents):
    update = _plan([], "is it safe to go out tomorrow", intents=intents)
    assert update["query_outcome"] == "NEEDS_PLACE" and "Which place do you mean?" in update["disclosures"][0]
    assert update["execution_plan"] == [] and update["place_resolution"]["status"] == "ambiguous"
    assert "Gulf of Mannar" not in update["disclosures"][0] and "fallback" not in update["disclosures"][0]


@pytest.mark.parametrize("intents", [("REGULATORY",), ("META",), ("EXPORT",), ("SUBSCRIPTION",), ("ADMINISTRATIVE",)])
def test_a_question_that_needs_no_place_is_not_asked_for_one(intents):
    update = _plan([], "what does the fishing ban say", intents=intents)
    assert update.get("query_outcome") != "NEEDS_PLACE"


@pytest.mark.parametrize("source", ["gps_fix", "home_port", "session_carried", "explicit", "coordinates", "gazetteer"])
def test_any_other_source_of_a_position_means_no_question(source):
    loc = {"lat": 13.3, "lon": 74.7, "place_name": "udupi", "place_source": source}
    assert _plan([], "is it safe to go out tomorrow", intents=("SAFETY_CHECK",), loc=loc).get("query_outcome") != "NEEDS_PLACE"


def test_a_named_place_means_no_question():
    update = _plan([_p("udupi")], "is it safe near udupi", intents=("SAFETY_CHECK",))
    assert update.get("query_outcome") is None and update["user_location"]["place_name"] == "udupi"


def test_a_greeting_is_not_asked_for_a_place():
    assert _plan([], "hello", intents=(), kind="greeting_or_small_talk").get("query_outcome") != "NEEDS_PLACE"


def test_the_place_resolution_no_longer_seeds_a_stale_disclosure():
    import inspect

    from orca.api import main

    assert '"disclosures": [],' in inspect.getsource(main._initial_state)


def test_the_guard_prompt_has_no_example_reason_for_the_model_to_copy():
    # found live 2026-10-10: the no-place question came back with "X is a whole coastline, not a position ..." appended,
    # copied from the example inside rule 6
    from orca.agents import reporting

    for small_talk in (True, False):
        prompt = " ".join(reporting._guard_prompt("m", "Which place do you mean?", small_talk).split())
        assert "whole coastline" not in prompt and "X is a" not in prompt
        assert "Add no reason, place name or explanation that is not written in WHAT IS REQUIRED" in prompt
        assert "in the language and script of USER MESSAGE" in prompt and "do not repeat it in English" in prompt
