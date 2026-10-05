"""D-11 / D-14 — narration defects that were prompt-only, now enforced in code.

D-11: "GO – sea conditions are safe ..." opened a PFZ answer although
`lead_with_verdict` was false. The prompt asked the model not to; nothing checked.

D-14: after "more detailed description" the Critic's reviser produced
"**VERDICT: REVISED**", "**EXPIRED / OUTDATED**" and "…remains classed as a 'fresh'
zone due to updated conditions". Two causes: an answer with no verdict header was
told it "MUST still begin with the exact verdict header ''" (so the model invented
one), and the reviser was never shown the measured facts (so it invented claims).
"""
from __future__ import annotations

from unittest import mock

import pytest

from orca.agents import critic, reporting
from orca.agents.critic import (
    CritiqueIssue,
    _opens_with_heading,
    _revise_prompt,
    _revision_is_safe,
    run_critic_pass,
)
from orca.agents.reporting import strip_unrequested_verdict, synthesize_narrative

REASON = "All Parameters Within Safe Operational Limits"
GO = {"go_no_go": "GO", "reason": REASON, "status": "OK"}


# --- D-11: a GO header the model wrote on a non-safety answer is removed ------------------

@pytest.mark.parametrize("written, expected", [
    ("GO – sea conditions are safe (wave≈0.6 m, wind≈2 km/h). The nearest zone is 49 km WNW.",
     "Sea conditions are safe (wave≈0.6 m, wind≈2 km/h). The nearest zone is 49 km WNW."),
    ("**GO** – The nearest zone is 49 km WNW.", "The nearest zone is 49 km WNW."),
    ("GO: The nearest zone is 49 km WNW.", "The nearest zone is 49 km WNW."),
    ("GO. The nearest zone is 49 km WNW.", "The nearest zone is 49 km WNW."),
    ("**VERDICT: GO** The nearest zone is 49 km WNW.", "The nearest zone is 49 km WNW."),
    (f"GO: {REASON}\n\nThe nearest zone is 49 km WNW.", "The nearest zone is 49 km WNW."),
    (f"GO: {REASON}.  \nThe nearest zone is 49 km WNW.", "The nearest zone is 49 km WNW."),
])
def test_a_go_header_is_removed_and_the_answer_is_kept(written, expected):
    assert strip_unrequested_verdict(written, "GO", REASON) == expected


@pytest.mark.parametrize("text", [
    "Go fishing north of the harbour, the zone is 49 km WNW.",   # an ordinary sentence
    "The nearest zone is 49 km WNW. GO is not needed.",          # not at the start
    "Nearest PFZ: about 49 km WNW of Mangrol.",
    "Going out is fine: the zone is 49 km WNW.",
])
def test_ordinary_text_is_never_touched(text):
    assert strip_unrequested_verdict(text, "GO", REASON) == text


@pytest.mark.parametrize("verdict", ["CAUTION", "NO_GO", "UNKNOWN"])
def test_only_a_go_is_ever_stripped_so_a_warning_can_never_be_hidden(verdict):
    text = f"{verdict}: waves are high. The zone is 49 km WNW."
    assert strip_unrequested_verdict(text, verdict, "waves are high") == text


def test_a_header_only_answer_strips_to_empty_so_the_caller_can_fall_back():
    assert strip_unrequested_verdict("GO –", "GO", REASON) == ""


class _Client:
    engine = "fake-model"

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, messages, **kw):
        self.prompts.append(messages[0]["content"])
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def _narrate(model_text, lead):
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client([model_text])):
        return synthesize_narrative("pfzs near mangrol", GO, [], lead_with_verdict=lead)


def test_a_non_safety_answer_never_opens_with_go_even_when_the_model_writes_it():
    out = _narrate("GO – sea conditions are safe. The nearest zone is 49 km WNW.", lead=False)
    assert not out.startswith("GO") and out.startswith("Sea conditions are safe")


def test_a_model_that_only_wrote_a_header_falls_back_to_the_deterministic_paragraph():
    out = _narrate("GO –", lead=False)
    assert out and not out.startswith("GO")


def test_a_safety_answer_still_leads_with_its_verdict():
    out = _narrate("GO: All Parameters Within Safe Operational Limits. Calm sea.", lead=True)
    assert out.startswith("GO:")


def test_a_non_go_verdict_leads_whatever_was_asked():
    caution = {"go_no_go": "CAUTION", "reason": "Rough Sea State", "status": "WARNING"}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(["CAUTION: Rough Sea State. The zone is 49 km WNW."])):
        out = synthesize_narrative("pfzs near mangrol", caution, [], lead_with_verdict=False)
    assert out.startswith("CAUTION:")


def test_the_prompt_for_a_non_safety_answer_forbids_the_verdict_word_and_headings():
    client = _Client(["The nearest zone is 49 km WNW."])
    with mock.patch("orca.llm.tiers.llm", lambda tier: client):
        synthesize_narrative("pfzs near mangrol", GO, [], lead_with_verdict=False)
    assert 'must not be "GO"' in client.prompts[0] and "title, heading or bold label" in client.prompts[0]


# --- D-14: the reviser's prompt ------------------------------------------------------------

ISSUE = [CritiqueIssue("factual_consistency", "Calls an expired advisory current.", "reporting")]
FACTS = "- nearest_pfz: distance_km=49, valid_for=2026-10-02, expired=True, age_days=3"


def test_with_no_header_the_prompt_says_so_instead_of_asking_for_an_empty_one():
    prompt = _revise_prompt("The zone is 49 km WNW.", ISSUE, "", FACTS)
    assert 'verdict header ""' not in prompt and "MUST still begin" not in prompt
    assert "must not get one" in prompt and "no heading, title, bold label" in prompt


def test_with_a_header_it_is_still_required_unchanged():
    assert 'MUST still begin with the exact verdict header "GO:"' in _revise_prompt("GO: fine.", ISSUE, "GO:", FACTS)


def test_the_reviser_is_shown_the_measured_facts_and_told_never_to_add_claims():
    prompt = _revise_prompt("The zone is 49 km WNW.", ISSUE, "", FACTS)
    assert FACTS in prompt and "MEASURED FACTS" in prompt
    assert "Never add a claim" in prompt and "delete it" in prompt


# --- D-14: a revision that invents a header or a figure is refused --------------------------

PLAIN = "The nearest zone is 49 km WNW of Mangrol. The advisory for 2 Oct 2026 has expired."


@pytest.mark.parametrize("revised", [
    "**VERDICT: REVISED**\n\nThe nearest zone is 49 km WNW of Mangrol.",
    "**EXPIRED / OUTDATED** The nearest zone is 49 km WNW of Mangrol.",
    "**PFZ detail (data measured at Mangrol):**\n- The nearest zone is 49 km WNW.",
    "EXPIRED / OUTDATED\nThe nearest zone is 49 km WNW of Mangrol.",
    "VERDICT: REVISED\nThe nearest zone is 49 km WNW.",
    "## Summary\nThe nearest zone is 49 km WNW.",
])
def test_an_invented_heading_is_refused(revised):
    assert _opens_with_heading(revised)
    assert not _revision_is_safe(PLAIN, revised, None, FACTS)


def test_a_figure_not_in_the_text_or_the_facts_is_refused():
    assert not _revision_is_safe(PLAIN, "The nearest zone is 49 km WNW and 31 m deep.", None, FACTS)


def test_a_figure_that_is_in_the_facts_is_allowed():
    assert _revision_is_safe(PLAIN, "The nearest zone is 49 km WNW; the advisory is 3 days old and has expired.", None, FACTS)


def test_a_plain_corrected_paragraph_is_accepted():
    assert _revision_is_safe(PLAIN, "The nearest zone is 49 km WNW of Mangrol. That advisory expired on 2 Oct 2026.", None, FACTS)


def test_an_original_that_already_opened_with_a_label_is_not_blamed_for_it():
    original = "**Nearest zone:** 49 km WNW of Mangrol."
    assert _revision_is_safe(original, "**Nearest zone:** 49 km WNW of Mangrol (advisory expired).", None, FACTS)


def test_an_empty_revision_is_refused():
    assert not _revision_is_safe(PLAIN, "   ", None, FACTS)


def test_the_verdict_header_rule_is_unchanged_for_a_safety_answer():
    assert _revision_is_safe("GO: fine. Calm.", "GO: fine. Calm sea.", "GO:", FACTS)
    assert not _revision_is_safe("GO: fine. Calm.", "CAUTION: fine. Calm sea.", "GO:", FACTS)


# --- D-14: through the whole critic pass ---------------------------------------------------

JUDGE_FLAGS = '[{"rubric_item": "factual_consistency", "description": "Calls an expired advisory current."}]'


def _pass(replies, narrative=PLAIN):
    client = _Client(replies)
    with mock.patch("orca.llm.tiers.llm", lambda tier: client):
        return run_critic_pass("more detail", narrative, FACTS, is_safety_check=False, max_iterations=1), client


def test_a_revision_that_invents_a_heading_is_dropped_and_the_original_text_is_kept():
    (text, passed, _, _), _ = _pass([JUDGE_FLAGS, "**VERDICT: REVISED**\n\nThe nearest zone is 49 km WNW."])
    assert text == PLAIN and passed is False


def test_a_good_revision_replaces_the_text():
    good = "The nearest zone is 49 km WNW of Mangrol. That advisory expired on 2 Oct 2026."
    (text, _, _, issues), client = _pass([JUDGE_FLAGS, good])
    assert text == good and issues
    assert FACTS in client.prompts[1]  # the reviser saw the facts


def test_when_the_judge_finds_nothing_no_revise_call_is_made():
    (text, passed, _, _), client = _pass(["[]"])
    assert text == PLAIN and passed is True and len(client.prompts) == 1


def test_the_module_still_exports_what_the_graph_uses():
    assert critic.MAX_ITERATIONS_STANDARD == 1 and critic.reinvocation_target([]) is None
    assert reporting.should_lead_with_verdict(GO, ["PFZ_NEAREST"]) is False


# --- D-14: the narrator is not handed the word "fresh" for an expired advisory --------------

from orca.agents.reporting import narration_view
from orca.contracts import AgentResult, Confidence, SourceProvenance


def test_an_expired_advisory_labelled_fresh_by_the_data_is_shown_as_not_today():
    row = {"found": True, "distance_km": 49, "valid_for": "2026-10-02", "age_days": 3, "band": "fresh", "expired": True}
    seen = narration_view({"nearest_pfz": row})["nearest_pfz"]
    assert "band" not in seen and seen["recency"] == "latest_held_not_today"
    assert seen["expired"] is True and seen["age_days"] == 3 and seen["distance_km"] == 49   # facts untouched


@pytest.mark.parametrize("band, expired, expected", [
    ("fresh", False, "current"),
    ("fresh", None, "current"),
    ("hint", True, "pointer_only_not_current"),
    ("history", True, "pointer_only_not_current"),
])
def test_every_band_maps_to_a_plain_recency(band, expired, expected):
    assert narration_view({"band": band, "expired": expired})["recency"] == expected


def test_it_walks_nested_dicts_and_lists_and_never_mutates_its_input():
    original = {"sector_status": {"latest_advisory": {"band": "fresh", "expired": True, "valid_for": "2026-10-02"}},
                "pfz_list": [{"band": "history", "expired": True}], "tide": {"tidal_state": "falling"}}
    snapshot = repr(original)
    view = narration_view(original)
    assert view["sector_status"]["latest_advisory"]["recency"] == "latest_held_not_today"
    assert view["pfz_list"][0]["recency"] == "pointer_only_not_current"
    assert view["tide"] == {"tidal_state": "falling"}
    assert "band" not in repr(view) and repr(original) == snapshot


def test_the_narrator_prompt_carries_recency_not_the_band_word_and_forbids_calling_expired_items_fresh():
    ocean = AgentResult(
        agent_name="ocean_analytics", query_id="q", reasoning_depth="SHALLOW", inputs_consumed={},
        outputs={"nearest_pfz": {"found": True, "distance_km": 49, "valid_for": "2026-10-02", "age_days": 3,
                                 "band": "fresh", "expired": True}},
        source_provenance=SourceProvenance(dataset="INCOIS PFZ", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(score="HIGH", rationale="x"),
    )
    client = _Client(["The nearest zone is 49 km away; its advisory expired on 2 Oct 2026."])
    with mock.patch("orca.llm.tiers.llm", lambda tier: client):
        synthesize_narrative("pfzs near mangrol", GO, [ocean], lead_with_verdict=False)
    prompt = client.prompts[0]
    assert "recency': 'latest_held_not_today'" in prompt and "'band'" not in prompt and "band=" not in prompt
    assert "never call an expired" in prompt and "item fresh" in prompt
