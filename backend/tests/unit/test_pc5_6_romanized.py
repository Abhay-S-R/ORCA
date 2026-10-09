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


# PC5.6 NOTE-2 (a SAFETY gap, to be fixed as its own point, not inside PC5.6): the phrase check misses these three
# romanized phrases. Live, through /query, all three WERE raised, but one step later, by the planner's model reading
# (`planned_distress`), i.e. after language ingress and only while a model is reachable. With no model they would be
# answered as ordinary prompts.
_MISSED_BY_THE_PHRASE_CHECK = {
    "naav ka engine kharab ho gaya, madad chahiye",
    "meri naav ka engine kharab ho gaya hai pamban ke paas madad chahiye",
    "nanna boat engine halaaytu malpe hatra sahaya beku",
}


@pytest.mark.parametrize("phrase", [
    pytest.param(p, marks=pytest.mark.xfail(strict=True, reason="PC5.6 NOTE-2: the phrase check misses it")) if p in _MISSED_BY_THE_PHRASE_CHECK else p
    for p in ROMANIZED_DISTRESS
])
def test_romanized_distress_is_raised_by_the_phrase_check_with_no_model(phrase, monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")
    assert detect_distress_signal(phrase)["is_distress"] is True


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
])
def test_ordinary_romanized_prompts_are_not_distress(phrase):
    assert detect_distress_signal(phrase)["is_distress"] is False


@pytest.mark.xfail(
    strict=True,
    reason="PC5.6 NOTE-1: romanized Hindi 'tuticorin se pamban tak' reads as two places, status 'ambiguous', yet the "
           "question is answered at the pilot default position (disclosed, but the answer text still says 'your route "
           "from Tuticorin to Pamban'). The English form resolves as a passage. To be fixed as its own point.",
)
def test_a_romanized_route_between_two_places_is_not_answered_at_the_pilot_default():
    from orca.place_resolution import resolve_or_ask

    result = resolve_or_ask("mujhe tuticorin se pamban tak sabse surakshit raasta batao")
    assert result.status in ("resolved", "ambiguous")
    assert result.status == "resolved"  # as "safest route from tuticorin to pamban" does
