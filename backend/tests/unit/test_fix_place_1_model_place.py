"""FIX-PLACE-1 (2026-10-09): the model's validated place sets the position; the word list is the fast path and the fallback.

Found by the user: "oh sorry i meant kundapura" was answered at the pilot default (Thoothukudi) while the card spoke of
Kundapura, and the next message "kundapura" said no data. The word list read the raw text ("kundapura" is not an exact
gazetteer name: a near-miss "did you mean?", no position, so the default); the model read it correctly and validation
accepted "Kundapur", but nothing used it for the position.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca import session
from orca.agents.reporting import _describe_recent_turns
from orca.graph.graph import planning_node
from orca.place_resolution import adopt_model_place, resolve_or_ask

DEFAULT = {"lat": 8.8, "lon": 78.3, "place_name": None, "place_source": "regional_default"}


def _p(raw, normalized=None):
    return [{"raw": raw, "normalized": normalized or raw}]


# --- adoption --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,normalized,expected", [
    ("kundapura", "Kundapur", "kundapur"),
    ("cochin", "Kochi", "kochi"),
    ("mangalore", "Mangaluru", "mangaluru"),
    ("tuticorine", "Tuticorin", "tuticorin"),
    ("kochchi", "Kochi", "kochi"),
])
def test_a_spelling_the_word_list_does_not_hold_but_the_model_read_sets_the_position(raw, normalized, expected):
    loc, resolution, _note = adopt_model_place(_p(raw, normalized), DEFAULT, [f"is it safe near {raw}"])  # type: ignore[misc]
    assert loc["place_name"] == expected and loc["place_source"] == "gazetteer"
    assert (loc["lat"], loc["lon"]) != (8.8, 78.3) or expected == "tuticorin"
    assert resolution["status"] == "resolved" and resolution["place_name"] == expected


def test_the_answer_says_what_was_read_as_what():
    _, _, note = adopt_model_place(_p("kundapura", "Kundapur"), DEFAULT, ["oh sorry i meant kundapura"])  # type: ignore[misc]
    assert note == "Read “kundapura” as Kundapur."


def test_an_exact_spelling_needs_no_note():
    loc = {**DEFAULT, "place_source": "session_carried"}
    _, _, note = adopt_model_place(_p("udupi", "Udupi"), loc, ["near udupi"])  # type: ignore[misc]
    assert note is None


@pytest.mark.parametrize("places", [
    _p("goa", "Goa"),                          # a whole coastline is not a position
    _p("atlantis", "Atlantis"),                # not in the gazetteer
    _p("delhi", "Delhi"),                      # inland
    [],                                        # the model found no place
    _p("kundapura", "Kundapur") + _p("udupi"),  # two places: not this function's call
])
def test_anything_the_gazetteer_does_not_confirm_is_not_adopted(places):
    assert adopt_model_place(places, DEFAULT, ["goa atlantis delhi kundapura udupi"]) is None


def test_the_model_cannot_invent_a_place_the_user_did_not_write():
    assert adopt_model_place(_p("kochi", "Kochi"), DEFAULT, ["wave height near udupi"]) is None


@pytest.mark.parametrize("source", ["explicit", "coordinates", "gazetteer", "port_fixture", "tide_station"])
def test_a_position_the_caller_chose_or_the_text_resolved_exactly_is_never_replaced(source):
    assert adopt_model_place(_p("kundapura", "Kundapur"), {**DEFAULT, "place_source": source}, ["kundapura"]) is None


@pytest.mark.parametrize("source", ["regional_default", "session_carried", "home_port", "gps_fix"])
def test_a_place_the_user_named_beats_a_guess(source):
    got = adopt_model_place(_p("kundapura", "Kundapur"), {**DEFAULT, "place_source": source}, ["kundapura"])
    assert got is not None and got[0]["place_name"] == "kundapur"


def test_native_script_places_are_checked_against_the_message_the_model_read():
    got = adopt_model_place(_p("ಕುಂದಾಪುರ", "Kundapur"), DEFAULT, ["ಕುಂದಾಪುರ ಹತ್ತಿರ ಸುರಕ್ಷಿತವೇ"])
    assert got is not None and got[0]["place_name"] == "kundapur"


# --- through planning, with the user's own conversation ----------------------------------------------------------------------

class _Client:
    engine = "fake-model"

    def __init__(self, body):
        self.text = json.dumps(body)

    def complete(self, messages, **kw):
        return self.text


def _plan(places, query, loc=DEFAULT, followup=True):
    body = {"kind": "sea_question", "intents": ["PFZ_NEAREST"], "places": places, "when": None, "is_followup": followup,
            "agents": [], "english_reading": query}
    state = {"query_id": "q", "raw_user_query": query, "session_history": [], "user_location": dict(loc),
             "place_resolution": resolve_or_ask(query).as_dict()}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return planning_node(state)  # type: ignore[arg-type]


def test_oh_sorry_i_meant_kundapura_is_answered_at_kundapur_not_at_thoothukudi():
    assert resolve_or_ask("oh sorry i meant kundapura").status == "ambiguous"  # what the word list alone does
    update = _plan(_p("kundapura", "Kundapur"), "oh sorry i meant kundapura")
    assert update["user_location"]["place_name"] == "kundapur" and update["user_location"]["place_source"] == "gazetteer"
    assert update["place_resolution"]["status"] == "resolved"
    assert not update.get("disclosures")  # no "Read X as Y" banner: the user can correct a misread
    assert update.get("query_outcome") is None


def test_the_sst_and_chlorophyll_question_for_kundapura_in_kannada_too():
    update = _plan(_p("kundapura", "Kundapur"), "okay fine give me the SST and chlorophyll deatils of kundapura in kannada")
    assert update["user_location"]["place_name"] == "kundapur"


def test_a_whole_coastline_still_asks_which_port():
    update = _plan(_p("karnataka", "Karnataka"), "pfzs near ktaka", followup=False)
    assert update["query_outcome"] == "NEEDS_PLACE" and "user_location" not in update


def test_the_next_turn_remembers_the_adopted_place():
    update = _plan(_p("kundapura", "Kundapur"), "oh sorry i meant kundapura")
    turn = session.turn_from_final("oh sorry i meant kundapura", {"user_location": update["user_location"], "place_resolution": update["place_resolution"]})
    assert session.last_place([turn]) is not None and session.last_place([turn])[2] == "kundapur"


# --- chat replies are told what really happened -----------------------------------------------------------------------------

def test_a_turn_answered_at_the_default_is_recorded_as_such_for_the_chat_model():
    turn = session.turn_from_final("oh sorry i meant kundapura", {"user_location": dict(DEFAULT), "place_resolution": {"status": "ambiguous"}})
    assert turn["place_status"] == "ambiguous"
    text = _describe_recent_turns([{**turn, "english_query": "oh sorry i meant kundapura", "answer": "x"}]) or ""
    assert "no place was resolved for it" in text and "pilot default position" in text


def test_the_chat_prompt_forbids_guessing_a_reason_or_apologising_for_an_unrecorded_fault():
    import inspect

    from orca.agents import reporting

    source = inspect.getsource(reporting.write_chat_reply)
    assert "say only what the conversation above records" in source and "do not apologise for a fault the record does not show" in source


# --- the model's wording varies: a close, single near-miss is accepted, and said --------------------------------------------

@pytest.mark.parametrize("raw,normalized,expected", [
    ("kundapura", "Kundapura", "kundapur"),     # the model did not normalise it to the gazetteer's spelling
    ("tuticorine", "Tuticorine", "tuticorin"),
])
def test_when_the_model_keeps_the_users_spelling_a_close_single_near_miss_is_still_that_place(raw, normalized, expected):
    got = adopt_model_place(_p(raw, normalized), DEFAULT, [f"i meant {raw}"])
    assert got is not None and got[0]["place_name"] == expected
    assert got[2] is not None and "Read" in got[2]


def test_planning_does_not_ask_which_place_for_that_case():
    update = _plan(_p("kundapura", "Kundapura"), "oh sorry i meant kundapura")
    assert update.get("query_outcome") is None and update["user_location"]["place_name"] == "kundapur"


@pytest.mark.parametrize("name", ["karnataka", "gujarat", "goa"])
def test_a_whole_coastline_never_counts_as_a_close_match(name):
    from orca.place_resolution import resolve_confident

    assert resolve_confident(name).status == "ambiguous"


def test_a_far_name_is_not_a_close_match():
    from orca.place_resolution import resolve_confident

    assert resolve_confident("xyzabc").status != "resolved"
