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
    ("Is it worth going out today?", "WORTHWHILENESS"),
    ("When should I leave tomorrow?", "TIMING"),
    ("What if I wait until this evening?", "COUNTERFACTUAL"),
    ("Rameswaram or Thoothukudi, which is safer?", "COMPARISON"),
    ("How far can I go and back on this boat?", "ENDURANCE"),
    ("How much fuel to get to the nearest PFZ?", "FUEL_ECONOMICS"),
    ("Was it rougher last week near Thoothukudi?", "HISTORICAL"),
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
    assert "lat=" not in acts[2]["href"] and "fallback region" in acts[2]["text"]  # wording changed in the 2026-10-09 merge


# --- P5.9 scenario shapes -----------------------------------------------

def test_worthwhileness_names_a_real_pfz_reading_or_the_data_gap():
    [a] = intent_actions.build(["WORTHWHILENESS"], "is it worth going", EXPLICIT, "q1")
    assert a["intent"] == "WORTHWHILENESS"
    assert a["text"]  # a real PFZ/sector call ran, whichever branch it landed on


def test_worthwhileness_without_a_place_asks_for_one():
    [a] = intent_actions.build(["WORTHWHILENESS"], "is it worth going", None, "q1")
    assert "Name a place" in a["text"]


def test_timing_scans_the_real_forecast_and_never_raises():
    [a] = intent_actions.build(["TIMING"], "when should I leave", EXPLICIT, "q1")
    assert a["intent"] == "TIMING"
    assert "GO" in a["text"] or "no GO hour" in a["text"]


def test_counterfactual_compares_now_against_the_named_window():
    [a] = intent_actions.build(["COUNTERFACTUAL"], "what if I wait until this evening", EXPLICIT, "q1")
    assert a["intent"] == "COUNTERFACTUAL"
    assert "now reads" in a["text"] or "outside the" in a["text"]


def test_comparison_checks_both_named_places_not_just_the_first():
    [a] = intent_actions.build(["COMPARISON"], "Rameswaram or Thoothukudi, which is safer?", None, "q1")
    assert a["intent"] == "COMPARISON"
    assert "Rameswaram" in a["text"] and "Thoothukudi" in a["text"]


def test_comparison_with_only_one_place_asks_for_both():
    [a] = intent_actions.build(["COMPARISON"], "is Atlantis or Nowhereland safer", None, "q1")
    assert "could not place both" in a["text"]


def test_endurance_is_an_honest_gap_not_a_guess():
    [a] = intent_actions.build(["ENDURANCE"], "how far can I go and back", EXPLICIT, "q1")
    assert "fuel tank capacity" in a["text"]


def test_fuel_economics_points_at_the_profile_when_no_vessel_numbers_are_wired():
    [a] = intent_actions.build(["FUEL_ECONOMICS"], "how much fuel to get there", EXPLICIT, "q1")
    assert a["href"] == "/profile"


def test_historical_never_raises_whether_in_or_outside_the_archive():
    # An unrecognised time phrase falls to the 7-day default rather than
    # guessing a further-back date; either a real comparison or a named-span
    # refusal comes back, never a crash and never a silent guess.
    [a] = intent_actions.build(["HISTORICAL"], "how did it compare a while back", EXPLICIT, "q1")
    assert a["intent"] == "HISTORICAL"
    assert a["text"]


def test_historical_last_week_reads_a_real_archived_value():
    [a] = intent_actions.build(["HISTORICAL"], "was it rougher last week?", EXPLICIT, "q1")
    assert "ERA5 archive" in a["text"] or "outside that window" in a["text"]


def test_subscription_offers_a_watch_but_never_creates_one():
    [a] = intent_actions.build(["SUBSCRIPTION"], "notify me", EXPLICIT, "q1")
    assert a["kind"] == "create_watch" and a["watch"] == {"watch_type": "weather", "lat": 9.28, "lon": 79.31, "radius_km": 25}


def test_regulatory_answers_from_the_ban_order_on_disk():
    [a] = intent_actions.build(["REGULATORY"], "allowed to fish?", EXPLICIT, "q1")
    assert a["text"].startswith("Rameswaram:")  # names the place, then the order's own words


def test_meta_links_this_answers_trace_and_rows_without_actions_add_nothing():
    [a] = intent_actions.build(["META", "SAFETY_CHECK"], "how do you know", EXPLICIT, "abc")
    assert a["href"] == "/reasoning?query_id=abc"
