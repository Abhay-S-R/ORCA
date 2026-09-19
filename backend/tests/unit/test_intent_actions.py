"""P5.29 — the seven routing rows added to complete orca_final §3.2, and the one
concrete action each puts on the answer card."""
import pytest

from orca import intent_actions
from orca.agents.planning import ROUTING_TABLE, classify_intent

EXPLICIT = {"lat": 9.28, "lon": 79.31, "place_name": "Rameswaram", "place_source": "explicit"}
DEFAULT = {"lat": 8.8, "lon": 78.14, "place_name": None, "place_source": "regional_default"}


@pytest.mark.parametrize("query, row", [
    ("What is the safest route from Thoothukudi to Rameswaram?", "ROUTE"),
    ("Why has fish catch declined in Thoothukudi?", "DIAGNOSTIC"),
    ("Am I allowed to fish near Rameswaram this month?", "REGULATORY"),
    ("How do you know that?", "META"),
    ("Export this as CSV", "EXPORT"),
    ("Notify me if waves get high at Pamban", "SUBSCRIPTION"),
    ("Change my home port to Kakinada", "ADMINISTRATIVE"),
])
def test_each_new_row_is_reached_by_tier_1(query, row):
    assert row in [name for name, _ in classify_intent(query)]


def test_the_original_rows_still_route_as_before():
    assert [n for n, _ in classify_intent("is it safe to go to sea tomorrow")] == ["SAFETY_CHECK"]
    assert [n for n, _ in classify_intent("nearest pfz please")] == ["PFZ_NEAREST"]


def test_row_names_are_unique_and_match_orca_final():
    names = [r.name for r in ROUTING_TABLE]
    assert len(names) == len(set(names))
    assert set(names) >= {"ROUTE", "DIAGNOSTIC", "REGULATORY", "META", "EXPORT", "SUBSCRIPTION", "ADMINISTRATIVE"}


def test_route_resolves_both_ends_into_the_planner_link():
    [a] = intent_actions.build(["ROUTE"], "safest route from Thoothukudi to Rameswaram tomorrow?", None, "q1")
    assert a["href"].startswith("/voyage?from=") and "&to=" in a["href"]
    assert "Thoothukudi" in a["text"] and "Rameswaram" in a["text"]


def test_route_with_an_unknown_end_says_which_one_instead_of_guessing():
    [a] = intent_actions.build(["ROUTE"], "route from Thoothukudi to Atlantis", None, "q1")
    assert "to=" not in a["href"] and "the destination" in a["text"]


def test_regional_default_is_never_used_as_the_users_place():
    acts = intent_actions.build(["REGULATORY", "SUBSCRIPTION", "EXPORT"], "q", DEFAULT, "q1")
    assert [a["kind"] for a in acts] == ["info", "info", "download"]
    assert "lat=" not in acts[2]["href"] and "pilot region" in acts[2]["text"]


def test_subscription_offers_a_watch_but_never_creates_one():
    [a] = intent_actions.build(["SUBSCRIPTION"], "notify me", EXPLICIT, "q1")
    assert a["kind"] == "create_watch" and a["watch"] == {"watch_type": "weather", "lat": 9.28, "lon": 79.31, "radius_km": 25}


def test_regulatory_answers_from_the_ban_order_on_disk():
    [a] = intent_actions.build(["REGULATORY"], "allowed to fish?", EXPLICIT, "q1")
    assert a["text"].startswith("Rameswaram:")  # names the place, then the order's own words


def test_meta_links_this_answers_trace_and_rows_without_actions_add_nothing():
    [a] = intent_actions.build(["META", "SAFETY_CHECK"], "how do you know", EXPLICIT, "abc")
    assert a["href"] == "/reasoning?query_id=abc"
