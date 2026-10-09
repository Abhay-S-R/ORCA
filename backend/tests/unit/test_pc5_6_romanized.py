"""PC5.6 (2026-10-09) — verify, do not assume: romanized distress and romanized places.

(a) Romanized distress phrases are raised by the distress check, which runs BEFORE language ingress, with no model.
(b) A romanized place prompt gives a valid place, or a "which place?" question, never a wrong place.
The live run (real model, through /query, agent account) is recorded in the implementation log; these tests keep the
deterministic half and the one defect that run found.
"""
from __future__ import annotations

import pytest

from orca.agents.distress import detect_distress_signal
from orca.graph.graph import build_graph

ROMANIZED_DISTRESS = [
    "naav ka engine kharab ho gaya, madad chahiye",
    "meri naav ka engine kharab ho gaya hai pamban ke paas madad chahiye",
    "engine nindruduchu udhavi venum",
    "nanna boat engine halaaytu malpe hatra sahaya beku",
    "mera boat dub raha hai bachao",
    "padagu moozhgudhu udhavi venum",
]


@pytest.mark.parametrize("phrase", ROMANIZED_DISTRESS)
def test_romanized_distress_is_raised_by_the_phrase_check_with_no_model(phrase, monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")
    assert detect_distress_signal(phrase)["is_distress"] is True


# PC5.6-NOTE-2 (fixed 2026-10-09): a word for help AND a word for the boat failing, both needed.
@pytest.mark.parametrize("phrase", [
    "engine kharab ho gaya madad chahiye",
    "boat ka engine band ho gaya bachao",
    "mera naav dub raha hai madad karo",
    "nav mein paani bhar gaya hai madad chahiye",
    "nanna boat engine halaaytu sahaya beku",
    "boat munguttide sahaya maadi",
    "NAAV KA ENGINE KHARAB HO GAYA, MADAD CHAHIYE!!",
])
def test_help_plus_boat_trouble_is_distress(phrase, monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")
    result = detect_distress_signal(phrase)
    assert result["is_distress"] is True and result["distress_type"] == "romanized_pattern"


@pytest.mark.parametrize("phrase", [
    "route ke liye madad chahiye",                       # help word alone: not an emergency
    "mujhe machhli ke baare mein madad chahiye",
    "mera engine kharab ho gaya tha kal, ab theek hai",  # trouble word alone, no request for help
    "nanna boat engine halaaytu",
    "tuticorin se pamban tak ka raasta batao madad",
    "sahaya beku fishing zone ge",
    "madadgar engine",                                   # whole words only
    "madadi engine kharabi",
])
def test_one_half_alone_is_not_distress(phrase, monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")
    assert detect_distress_signal(phrase)["is_distress"] is False


def test_the_distress_check_runs_before_language_ingress():
    edges = {(e.source, e.target) for e in build_graph().get_graph().edges}
    assert ("__start__", "distress_check") in edges
    assert ("distress_check", "language_ingress") in edges
    assert ("__start__", "language_ingress") not in edges  # nothing reaches ingress without passing the distress check


@pytest.mark.parametrize("phrase", [
    "kal subah rameswaram ke paas samudra mein jaana safe hai kya",
    "kochi ke paas machhli kahan milegi aaj",
    "naalai kadalukku pogalama",
    "tum kaiso ho",
    "chennai ke paas cyclone ka khatra hai kya",
])
def test_ordinary_romanized_prompts_are_not_distress(phrase):
    assert detect_distress_signal(phrase)["is_distress"] is False


# PC5.6-NOTE-1 (fixed 2026-10-10): the romanized route is a passage once the model's two places and the ROUTE intent are
# read; it lives in test_d15_note1_place_followups.py (the word list alone still says `ambiguous`, by design).
