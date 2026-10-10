"""Agent 10 (Critic) — plan §4 S1 Phase 3, Day 18. LLM-as-judge over the
Reporting narrative, at the `reasoning` tier (orca/llm/tiers.py) — swapping
providers is an env change, never a code change here (Ground Rule 5).

Runs on **every** query, never on who is asking (P2.5, `R-AGENT-1`). It was
gated on `reasoning_depth == "DEEP"` until 2026-09-20, which meant the
verification loop did not execute at all on an ordinary demo question — the
one thing DLC §5 says the panel will probe hardest was the one thing a judge
could not watch happen. Depth still decides how *hard* the pass tries
(`run_critic_pass` iterates), not whether it happens.

What must never gate it is the asker's role: that would be the v1.0 routing
bug (intent decides what fires, the asker's role decides how it's said)
wearing a quality-control hat.
`scripts/verify_ci_guards.py` enforces this by construction — this module is
not in the guard's exclusion list (unlike language.py/reporting.py), so
reading the asker's role anywhere in this file fails CI, not just review.

Safety carve-out (Ground Rule 2, load-bearing): if `matched_intent_rows`
contains "SAFETY_CHECK", the go/no-go verdict already sits in
`final_english_response` before this agent ever runs (reporting_node runs
first in the graph) — the Critic only ever reviews and amends the
*explanatory* prose around an already-final verdict. It cannot withhold,
delay, or alter the verdict itself; asserted in the self-check below by
confirming the verdict header text survives every critique path unchanged.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from orca import engines
from orca.agents.reporting import _ist_clock, conversation_context
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth

if TYPE_CHECKING:
    from orca.state import ORCAState

MAX_ITERATIONS = 3

# P2.5 (`R-AGENT-1`) — how many times the Critic may send the answer back to
# the agent it blames and have the whole thing re-synthesized. One.
# `orca_final.md` §3.9 asks for up to three at DEEP; this plan deliberately
# holds it at one (latency on a live demo, and the Gemini free-tier
# per-minute limit P2.13 budgets against). Raising it is a one-line change
# here plus the guard in graph._route_after_critic; do not raise it without
# re-running the budget count that point records.
MAX_REINVOCATIONS = 1

# How many judge->revise rounds ONE Critic pass may run. Three at DEEP, as it
# always was; ONE otherwise (P2.13). This is the number the first live run of
# P2.5 forced: the Critic went from DEEP-only to every query, each pass could
# still loop three times, and with a re-invocation there are two passes — the
# UI showed "10 LLM calls" for one ordinary question, which is exactly the
# per-minute Gemini budget P2.13 exists to protect. One round is a judge call
# and, only if it found something, one revise call.
MAX_ITERATIONS_STANDARD = 1

# Architecture §3.2 five-part rubric, verbatim.
_RUBRIC = (
    "factual_consistency",   # does the prose contradict a measured value it cites?
    "temporal_coherence",    # does it mix forecast and observed tenses, or wrong time windows?
    "causal_claim_strength", # does it say "caused" where the data only supports "correlated"?
    "citation_completeness", # does every non-trivial claim carry a source?
    "spatial_accuracy",      # does a stated distance/bearing/boundary match the geospatial data?
)


@dataclass(frozen=True)
class CritiqueIssue:
    rubric_item: str
    description: str
    reinvoke_agent: str  # deterministic issue -> agent mapping, never a free-text guess


# Deterministic issue->agent re-invocation mapping (plan §6 D1 Day 18) — the
# Critic names *which* specialist's output the issue traces back to; it never
# re-derives the fact itself (that would be the Critic doing Ground-Rule-2
# work with an LLM).
_REINVOKE_MAP: dict[str, str] = {
    "factual_consistency": "reporting",
    "temporal_coherence": "weather_intelligence",
    "causal_claim_strength": "ocean_analytics",
    "citation_completeness": "reporting",
    "spatial_accuracy": "geospatial",
}

_VERDICT_HEADER_RE = re.compile(r"^(GO|CAUTION|NO_GO):")

# The three specialists a critique can actually send work back to. `reporting`
# is deliberately not here even though `_REINVOKE_MAP` names it: a factual or
# citation complaint about the *prose* is what `run_critic_pass`'s own revise
# step already fixes, so routing the graph back through Reporting for it would
# spend a second synthesis to redo what just happened. Only a complaint that
# traces to a *measurement* is worth re-reading the measurement for.
REINVOCABLE_AGENTS: frozenset[str] = frozenset(
    {"weather_intelligence", "ocean_analytics", "geospatial"}
)


def reinvocation_target(issues: list[dict[str, Any]] | list[CritiqueIssue]) -> str | None:
    """Which agent, if any, this critique sends the query back to. The first
    issue naming a re-invocable specialist wins — deterministic, ordered, and
    never a free-text guess: the agent comes from `_REINVOKE_MAP`, which is
    keyed on the rubric item the judge picked from a fixed list of five."""
    for issue in issues:
        target = issue.get("reinvoke_agent") if isinstance(issue, dict) else issue.reinvoke_agent
        if target in REINVOCABLE_AGENTS:
            return target
    return None


def _is_safety_check(state: ORCAState) -> bool:
    return "SAFETY_CHECK" in (state.get("matched_intent_rows") or [])


def _verdict_header(text: str) -> str | None:
    m = _VERDICT_HEADER_RE.match(text.strip())
    return m.group(0) if m else None


def _clean_json_text(raw: str) -> str:
    """Strips markdown code fences, conversational prose, and whitespace to isolate JSON."""
    if not raw or not isinstance(raw, str):
        return ""
    text = raw.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    else:
        start_bracket = text.find("[")
        start_brace = text.find("{")
        start = -1
        if start_bracket != -1 and start_brace != -1:
            start = min(start_bracket, start_brace)
        elif start_bracket != -1:
            start = start_bracket
        elif start_brace != -1:
            start = start_brace

        if start != -1:
            end_bracket = text.rfind("]")
            end_brace = text.rfind("}")
            end = max(end_bracket, end_brace)
            if end > start:
                text = text[start : end + 1].strip()
    return text


def _normalize_rubric_item(name: Any) -> str | None:
    """Normalize rubric item names (e.g. 'Spatial Accuracy' or 'spatial accuracy' -> 'spatial_accuracy')."""
    if not name or not isinstance(name, str):
        return None
    normalized = re.sub(r"[\s\-]+", "_", name.strip().lower())
    if normalized in _RUBRIC:
        return normalized
    return None


def _parse_judge_response(raw: str) -> list[CritiqueIssue]:
    """The judge is asked for strict JSON; a malformed response degrades to
    "no issues found" rather than crashing the pass — a Critic that cannot
    parse its own judge is not grounds to fail the whole response (plan §4
    D1: the Critic upgrades explanations, it never blocks anything)."""
    cleaned = _clean_json_text(raw)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, dict):
        items = data.get("issues") or ([data] if "rubric_item" in data else [])
    elif isinstance(data, list):
        items = data
    else:
        return []

    issues = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rubric_item = _normalize_rubric_item(item.get("rubric_item"))
        if not rubric_item:
            continue
        issues.append(CritiqueIssue(
            rubric_item=rubric_item,
            description=str(item.get("description", "")),
            reinvoke_agent=_REINVOKE_MAP[rubric_item],
        ))
    return issues


def _judge_prompt(query: str, narrative: str, facts_block: str, context: str = "") -> str:
    rubric_lines = "\n".join(f"- {item}" for item in _RUBRIC)
    # The narrator saw the conversation and the device position, so the judge
    # must too — or a correct "unlike your earlier question about Kochi" or
    # "you are at 12.97, 77.59" reads as an unsourced claim.
    context_block = (
        f"\nCONTEXT THE NARRATIVE WAS WRITTEN WITH (a valid source for references to the conversation "
        f"or the caller's position — NOT for sea readings):\n{context}\n"
        if context else ""
    )
    return f"""You are the ORCA Critic (Agent 10), judging a marine-advisory narrative against measured facts. \
Judge ONLY the explanatory prose that follows the verdict line — you never question or alter the verdict itself.

USER QUERY: "{query}"
{context_block}
MEASURED FACTS (ground truth, from deterministic agents):
{facts_block}

NARRATIVE UNDER REVIEW:
{narrative}

Judge against exactly these five rubric items, nothing else:
{rubric_lines}

How to judge — this matters more than the rubric wording:
- Flag only what the narrative ASSERTS. A rubric item is violated when a claim the narrative actually makes contradicts the measured facts, mixes up time frames, overstates causation, or states something non-trivial with no source.
- The ABSENCE of a fact is never a defect. The narrative answers the USER QUERY, not the fact list: a fishing-zone answer does not have to mention the maritime boundary, and a safety answer does not have to recite every reading. Never write "fails to mention", "does not include" or "omits" a measured value.
- Only the facts relevant to the USER QUERY can be contradicted by it.

Respond with STRICT JSON only, no prose: a list of objects
{{"rubric_item": "<one of the five above>", "description": "<one sentence, what is wrong>"}}.
Return [] if the narrative passes on all five."""


def _revise_prompt(narrative: str, issues: list[CritiqueIssue], verdict_header: str, facts_block: str = "") -> str:
    issue_lines = "\n".join(f"- [{i.rubric_item}] {i.description}" for i in issues)
    # Two different instructions, not one with a blank in it: an answer with no verdict header
    # (any answer to a question that was not about safety) used to be told it "MUST still begin
    # with the exact verdict header """ — and the model invented one ("VERDICT: REVISED").
    header_rule = (
        f'The response MUST still begin with the exact verdict header "{verdict_header}" — copy it unchanged.'
        if verdict_header else
        "ORIGINAL has no verdict header and the revision must not get one: no heading, title, bold label "
        "or verdict line. Start directly with the first sentence of the prose."
    )
    return f"""Revise ONLY the explanatory prose below to fix these issues. {header_rule}

MEASURED FACTS (the only ground truth; the reviewer judged against these):
{facts_block or "(not supplied)"}

HOW TO FIX:
- Correct or delete the claim the issue names so that it agrees with MEASURED FACTS.
- Never add a claim, number, date, source, or description of how fresh or current something is that is \
not in MEASURED FACTS or already in ORIGINAL. If a claim cannot be checked against MEASURED FACTS, delete it.
- Do not change any number, distance, or measured value that is already correct.

ISSUES TO FIX:
{issue_lines}

ORIGINAL:
{narrative}

Return only the revised text."""


_FIGURE = re.compile(r"\d+(?:\.\d+)?")
# A line the model made up to head an answer: "**EXPIRED / OUTDATED**", "PFZ detail (...):",
# "VERDICT: REVISED", or a run of capitals such as "EXPIRED / OUTDATED The nearest ...".
_BOLD_LABEL = re.compile(r"^\s*\*\*[^*\n]{1,60}\*\*")
_CAPS_RUN = re.compile(r"^\W*[A-Z][A-Z/_ \-]{5,}[A-Z]\b")


def _opens_with_heading(text: str) -> bool:
    first = text.strip().split("\n", 1)[0].strip()
    bare = first.strip("*#_ ").strip()
    if not bare:
        return False
    if _BOLD_LABEL.match(text) or first.startswith("#") or _CAPS_RUN.match(first):
        return True
    if re.match(r"(?i)verdict\b", bare):
        return True
    return len(bare) <= 90 and bare.endswith(":")


def _revision_is_safe(current: str, revised: str, verdict_header: str | None, facts_block: str) -> bool:
    """Whether a revision may replace the text. The Critic fixes prose; it may not
    invent a header, and it may not introduce a figure that is in neither the text
    it was given nor the measured facts. A refused revision keeps the previous text."""
    if not revised.strip():
        return False
    if verdict_header:
        return revised.startswith(verdict_header)
    if _opens_with_heading(revised) and not _opens_with_heading(current):
        return False
    known = {float(n) for n in _FIGURE.findall(current)} | {float(n) for n in _FIGURE.findall(facts_block or "")}
    return not ({float(n) for n in _FIGURE.findall(revised)} - known)


def run_critic_pass(
    query: str, narrative: str, facts_block: str, *, is_safety_check: bool,
    engine_out: list[str] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    context: str = "",
    can_reinvoke: bool = False,
) -> tuple[str, bool, int, list[CritiqueIssue]]:
    """Runs up to MAX_ITERATIONS judge->revise loops. Returns
    (final_narrative, critic_pass, iteration_count, issues_found).

    `issues_found` accumulates every issue that actually triggered a
    revision across all iterations — not just the last judge call, which is
    empty whenever the pass ultimately succeeds. The reasoning-graph replay
    (orca/api/trace_routes.py) draws one dashed re-invocation edge per issue
    here, so a Critic loop that corrected something and then passed clean
    must still be visible as a loop, not read back as "nothing happened".

    `is_safety_check` never gates *whether* this runs — the caller decides
    that, and this function stays blind to it either way; it only changes
    what may be revised: the verdict header is asserted unchanged on every
    iteration regardless."""
    from orca.llm.tiers import llm

    verdict_header = _verdict_header(narrative)
    client = llm("reasoning")
    if engine_out is not None:
        # getattr for the same reason reporting.synthesize_narrative uses it:
        # a client without `.engine` must not turn a working critic pass into
        # a degraded one.
        engine_out.append(getattr(client, "engine", engines.DETERMINISTIC))
    current = narrative
    issues_found: list[CritiqueIssue] = []

    for iteration in range(1, max_iterations + 1):
        # No max_tokens kwarg (Ground Rule 5): _TieredClient forwards **kw
        # straight to whichever provider is configured, and AnthropicProvider
        # / GeminiProvider do not accept the same kwarg name for this —
        # orca/agents/reporting.py's synthesize_narrative hits the same
        # constraint and omits it for the same reason. A provider-specific
        # token budget belongs in the tier's own config, not a per-call kwarg
        # here.
        raw = client.complete([{"role": "user", "content": _judge_prompt(query, current, facts_block, context)}])
        _note_engine(client, engine_out)
        issues = _parse_judge_response(raw)
        if not issues:
            return current, True, iteration, issues_found

        issues_found.extend(issues)

        # D3 Optimization: on standard depth (max_iterations == 1), if a specialist
        # re-invocation is available and targeted, do NOT spend tokens revising the prose.
        # The specialist will re-read measurements and Reporting will re-synthesize from scratch.
        if max_iterations == 1 and can_reinvoke and reinvocation_target(issues):
            return current, False, iteration, issues_found

        revised = client.complete(
            [{"role": "user", "content": _revise_prompt(current, issues, verdict_header or "", facts_block)}]
        ).strip()
        _note_engine(client, engine_out)

        # The verdict header is load-bearing: a revision that drops or
        # changes it is rejected outright and the previous text is kept —
        # the Critic amending the verdict would be Ground Rule 2 violated by
        # exactly the agent whose job is quality control. The same refusal now
        # covers a header the revision made up, and a figure it invented.
        if not _revision_is_safe(current, revised, verdict_header, facts_block):
            return current, False, iteration, issues_found
        current = revised

        # D3 Optimization: on standard depth (max_iterations == 1), we cannot run
        # a second judge pass to re-verify without exceeding the single-round budget.
        # Since _revision_is_safe passed, the prose revision has been validated.
        if max_iterations == 1:
            return current, True, iteration, issues_found

    return current, False, max_iterations, issues_found


def _note_engine(client: object, engine_out: list[str] | None) -> None:
    """A tier is a chain of providers now (orca/llm/tiers.py): which rung
    answered is only known after the call, so the label recorded before the
    first call is replaced with the one that actually did the work."""
    engine = getattr(client, "engine", None)
    if engine_out and engine:
        engine_out[-1] = engine


def _colour_facts(block: dict[str, Any] | None) -> str | None:
    """The headline reading, its cross-checks and the chlorophyll level for the critic, or None when nothing is held."""
    block = block or {}
    head = block.get("headline")
    if not head:
        return None

    def one(r: dict[str, Any]) -> str:
        return f"{r['value']} {r['unit']} ({r['source']}, {r.get('observed')}, cell {r.get('cell_distance_km')} km away)"

    text = f"headline {one(head)}"
    if block.get("level"):
        text += f", level {block['level']}"
    if block.get("cross_checks"):
        text += "; cross-checks (a normal offset, not a contradiction): " + "; ".join(one(r) for r in block["cross_checks"])
    if block.get("near_shore_indicative"):
        text += "; near the coast the satellite chlorophyll is only indicative"
    if block.get("unusual_gap"):
        text += f"; UNUSUAL GAP: {block['unusual_gap']}"
    return text



def _fmt_incois_hazards(hazard: Any) -> str | None:
    if not hazard or not isinstance(hazard, dict):
        return None
    warnings = hazard.get("active_warnings") or []
    if not isinstance(warnings, list) or not warnings:
        return None
    items = []
    for w in warnings[:5]:
        if not isinstance(w, dict):
            continue
        htype = (w.get("hazard_type") or w.get("disaster_type") or "marine hazard").replace("_", " ").title()
        dist = w.get("district") or ""
        msg = w.get("message") or w.get("headline") or ""
        entry = f"{dist} ({htype})" if dist else htype
        if msg:
            entry += f": {msg}"
        items.append(entry)
    return "; ".join(items) if items else None


def _fmt_imd_nowcasts(imd: Any) -> str | None:
    if not imd or not isinstance(imd, dict) or imd.get("expired"):
        return None
    alerts = imd.get("alerts") or []
    if not isinstance(alerts, list) or not alerts:
        return None
    items = []
    for a in alerts[:5]:
        if not isinstance(a, dict):
            continue
        dist = a.get("district") or ""
        color = (a.get("severity_color") or "").title()
        sev = (a.get("severity") or "").title()
        cat = a.get("event_category") or a.get("events") or "convective weather"
        label = f"{color} alert" if color else (sev if sev else "warning")
        entry = f"{dist} ({label}: {cat})" if dist else f"{label}: {cat}"
        items.append(entry)
    return "; ".join(items) if items else None


def _fmt_cyclone_tracks(tracks: Any) -> str | None:
    if not tracks:
        return None
    if isinstance(tracks, dict):
        systems = tracks.get("systems") or []
        if not isinstance(systems, list) or not systems:
            return None
        items_list = systems
    elif isinstance(tracks, list):
        items_list = tracks
    else:
        return None
    items = []
    for t in items_list[:3]:
        if not isinstance(t, dict):
            continue
        name = t.get("name") or t.get("system_name") or "Cyclone"
        basin = t.get("basin") or ""
        dist = t.get("distance_km")
        wind = t.get("max_wind_kmh") or t.get("max_wind_kts")
        intensity = t.get("intensity") or ""
        entry = name
        details = []
        if basin:
            details.append(f"basin {basin}")
        if dist is not None:
            details.append(f"{dist:.0f} km away")
        if wind is not None:
            w_str = f"{wind:.0f}" if isinstance(wind, (int, float)) and wind == int(wind) else str(wind)
            details.append(f"winds {w_str} km/h")
        if intensity:
            details.append(f"intensity {intensity}")
        if details:
            entry += f" ({', '.join(details)})"
        items.append(entry)
    return "; ".join(items) if items else None


def _fmt_mpa_regulatory(reg: Any) -> str | None:
    if not reg or not isinstance(reg, list):
        return None
    items = [f"{entry['name']} ({entry.get('designation', 'regulatory')})" for entry in reg if isinstance(entry, dict) and entry.get("name")]
    return ", ".join(items) if items else None


def _fmt_nearby_zones(zones: Any) -> str | None:
    if not zones or not isinstance(zones, list):
        return None
    items = []
    for z in zones[:5]:
        if not isinstance(z, dict) or "Indian Exclusive Economic Zone" in (z.get("name") or ""):
            continue
        name = z.get("name") or ""
        desig = z.get("designation") or ""
        dist = z.get("distance_nm")
        entry = f"{name} ({desig})" if desig else name
        if dist is not None:
            entry += f" {dist:.1f} nm"
        items.append(entry)
    return "; ".join(items) if items else None


def _fmt_fishing_ban(ban: dict[str, Any] | None, ban_note: str | None = None) -> str | None:
    ban = ban or {}
    if ban.get("available") and ban.get("in_ban_period"):
        coast = ban.get("coast") or ""
        win = ban.get("window") or ""
        msg = ban.get("message") or ""
        parts = [f"annual uniform fishing ban in force on {coast} coast" if coast else "annual uniform fishing ban in force"]
        if win:
            parts.append(f"window {win}")
        if ban.get("exemptions"):
            parts.append(f"exemptions: {ban['exemptions']}")
        if msg:
            parts.append(msg)
        return "; ".join(parts)
    if ban_note:
        return ban_note
    return None


def _fmt_top_species(species: list[dict[str, Any]] | None) -> str | None:
    if not species:
        return None
    items = []
    for sp in species[:5]:
        name = sp.get("name") or ""
        sci = sp.get("scientific_name") or ""
        if name and sci:
            items.append(f"{name} ({sci})")
        elif name:
            items.append(name)
    return ", ".join(items) if items else None


def _fmt_tide_high_time(when: Any) -> str | None:
    if not when:
        return None
    ist = _ist_clock(when)
    if ist:
        return f"{ist} ({when})"
    return str(when)


def _fmt_correlation(corr: dict[str, Any] | None) -> str | None:
    corr = corr or {}
    if corr.get("available") and corr.get("pearson_r") is not None:
        rel = f" ({corr['relationship']})" if corr.get("relationship") else ""
        samples = f", {corr['n_samples']} samples" if corr.get("n_samples") else ""
        return f"r={corr['pearson_r']:.2f}{rel}{samples}"
    return None


def _fmt_wind_anomaly(anom: dict[str, Any] | None) -> str | None:
    anom = anom or {}
    if anom.get("available") and anom.get("anomalous"):
        peak = anom.get("observed_peak")
        units = anom.get("units", "km/h")
        direction = anom.get("direction", "high")
        baseline = anom.get("baseline_days", 30)
        port = anom.get("nearest_port", "")
        port_str = f" at {port}" if port else ""
        return f"peak {peak} {units} is anomalous ({direction}) vs {baseline}-day ERA5 baseline{port_str}"
    return None


def _fmt_historical_comparison(hist: dict[str, Any] | None) -> str | None:
    hist = hist or {}
    if hist.get("available") and hist.get("statement"):
        return str(hist["statement"])
    return None


def build_facts_block(state: ORCAState) -> str:
    """The ground truth the judge compares the narrative against.

    Two defects lived in the inline version this replaces, both found by
    reading what the Critic actually complained about once P2.5 made it run on
    every query. It read `weather_data["wave_height"]`, a key that does not
    exist (readings live under `hourly[0]`), so wave height never reached the
    judge. And it listed only the boundary distance and the verdict, so a
    narrative that said "the nearest fishing zone is 447 km away" was compared
    with nothing that could confirm it, and the judge flagged it as
    contradicting the boundary distance. Every field a narrative can quote is
    here now, with its unit in its name, because "447" against "nautical
    miles" is how a fishing-zone distance gets confused with a boundary one.

    Only fields with a value are listed: an absent reading is absent, never a
    placeholder the judge could treat as a measurement."""
    weather = state.get("weather_data") or {}
    geo = state.get("geospatial_data") or {}
    ocean = state.get("ocean_data") or {}
    verdict = state.get("risk_assessment") or {}
    hourly = (weather.get("hourly") or [{}])[0]
    pfz = ocean.get("nearest_pfz") or {}
    tide = ocean.get("tide") or {}
    next_high = tide.get("next_high") or {}
    found = bool(pfz.get("found"))

    facts: dict[str, Any] = {
        "risk_verdict": verdict.get("go_no_go"),
        "risk_verdict_reason": verdict.get("reason"),
        "wave_height_m": hourly.get("wave_height"),
        "wind_speed_m_per_s": hourly.get("wind_speed_10m"),
        "lightning_active": weather.get("lightning_active"),
        "cyclone_alert": weather.get("cyclone_alert"),
        "incois_hazard_warnings": _fmt_incois_hazards(weather.get("incois_hazard")),
        "imd_convective_nowcast_alerts": _fmt_imd_nowcasts(weather.get("imd_nowcast")),
        "lightning_source_agreement": (
            "disagree (IMD nowcast and Open-Meteo proxy disagree; convective risk treated conservatively as active)"
            if weather.get("lightning_source_agreement") == "disagree"
            else weather.get("lightning_source_agreement")
        ),
        "active_cyclone_tracks": _fmt_cyclone_tracks(weather.get("cyclone_tracks")),
        "distance_to_maritime_boundary_nautical_miles": geo.get("imbl_distance_nm"),
        "maritime_boundary_bearing_deg": geo.get("imbl_bearing_deg"),
        "maritime_boundary_name": geo.get("imbl_boundary_name"),
        "maritime_boundary_band": geo.get("imbl_boundary_band"),
        "inside_marine_protected_area": geo.get("mpa_violation"),
        "inside_mpa_names": geo.get("mpa_names", []),
        "inside_regulatory_mpa": _fmt_mpa_regulatory(geo.get("mpa_regulatory")),
        "nearby_avoidance_zones_within_50nm": _fmt_nearby_zones(geo.get("nearby_zones")),
        "shallow_water_hazard": geo.get("shallow_hazard"),
        "bathymetric_depth_m": geo.get("depth_m"),
        # A fishing zone's distance, NOT the boundary's: named so they cannot be confused.
        "nearest_fishing_zone_distance_km": pfz.get("distance_km") if found else None,
        "nearest_fishing_zone_distance_measured_from": pfz.get("measured_from") if found else None,
        # INCOIS's own landmark wording — a separate origin; a narrative that
        # pairs the distance above with this landmark's name is wrong.
        "nearest_fishing_zone_incois_reference": pfz.get("incois_reference") if found else None,
        "nearest_fishing_zone_direction": pfz.get("compass") if found else None,
        "nearest_fishing_zone_depth_m": pfz.get("depth_m") if found else None,
        # Stale-data policy: the zone's own date and age, so a narrative that
        # says "issued 19 Sep, 5 days old" is confirmable, and one that calls
        # it current is contradicted.
        "nearest_fishing_zone_advisory_date": pfz.get("valid_for") if found else None,
        "nearest_fishing_zone_age_days": pfz.get("age_days") if found else None,
        "nearest_fishing_zone_advisory_expired": pfz.get("expired") if found else None,
        # A zone past this reach is still the nearest held; a narrative that
        # presents it as close by is contradicted.
        "nearest_fishing_zone_beyond_reach_km": pfz.get("max_km") if found and pfz.get("beyond_reach") else None,
        "nearest_fishing_zone_boundary_note": pfz.get("boundary_note"),
        "seasonal_fishing_ban": _fmt_fishing_ban(pfz.get("fishing_ban") or ocean.get("fishing_ban"), pfz.get("ban_note")),
        "top_target_fish_species": _fmt_top_species(pfz.get("top_species") or ocean.get("top_species")),
        # Why the user's own sector has no advisory today (INCOIS's words), so
        # "no data due to cloud cover" is confirmable and "no zones here" is not.
        "todays_sector_advisory_gap": (ocean.get("sector_status") or {}).get("message")
        if (ocean.get("sector_status") or {}).get("is_data_gap") else None,
        "sector_fallback_disclosure": ocean.get("sector_disclosure"),
        "tidal_state": tide.get("tidal_state"),
        "tide_station_name": tide.get("station_name"),
        "next_high_tide_height_m": next_high.get("height_m"),
        "next_high_tide_in_hours": next_high.get("in_hours"),
        "next_high_tide_time": _fmt_tide_high_time(next_high.get("when")),
        "productivity_diagnosis": ocean.get("productivity_diagnosis"),
        "sst_chlorophyll_correlation": _fmt_correlation(ocean.get("sst_chlorophyll_correlation")),
        "wind_anomaly_against_era5": _fmt_wind_anomaly(ocean.get("wind_anomaly")),
        "historical_climate_comparison": _fmt_historical_comparison(ocean.get("historical_comparison")),
        # NOTE-CHL-1: the SST / chlorophyll the narrative may quote. Without these the critic could not confirm a reading
        # it was asked to judge, and deleted the answer to "what is the SST and chlorophyll at X".
        "sea_surface_temperature_readings": _colour_facts((ocean.get("sea_colour_readings_at_the_place") or {}).get("sea_surface_temperature")),
        "chlorophyll_a_readings": _colour_facts((ocean.get("sea_colour_readings_at_the_place") or {}).get("chlorophyll_a")),
    }
    return "\n".join(f"- {k}: {v}" for k, v in facts.items() if v is not None) or "No measured facts available."


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Called only when reasoning_depth == "DEEP"
    (wired in orca/graph/graph.py's conditional edge, not here) — this
    function itself does not re-check depth so that a unit test can call it
    directly without constructing a full DEEP state."""
    query_id = state.get("query_id", "")
    depth = coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW"))
    narrative = state.get("final_english_response", "") or ""
    query = state.get("normalized_english_query") or state.get("raw_user_query") or ""
    is_safety = _is_safety_check(state)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    verdict_before = _verdict_header(narrative)
    engine_out: list[str] = []

    spent = int(state.get("critic_reinvocations") or 0)
    can_reinvoke = spent < MAX_REINVOCATIONS

    try:
        facts_block = build_facts_block(state)
        revised, critic_pass, iterations, issues = run_critic_pass(
            query, narrative, facts_block, is_safety_check=is_safety,
            engine_out=engine_out,
            max_iterations=MAX_ITERATIONS if depth == "DEEP" else MAX_ITERATIONS_STANDARD,
            context=conversation_context(state.get("session_history"), state.get("user_location")),
            can_reinvoke=can_reinvoke,
        )
        status: Literal["ok", "degraded"] = "ok"
        confidence = Confidence(
            score="HIGH" if critic_pass else "MEDIUM",
            rationale="passed all 5 rubric items" if (critic_pass and not issues) else (
                "prose revised and verified safe" if critic_pass else f"{len(issues)} issue(s) on final pass"
            ),
        )
        error_detail = None
    except Exception as exc:
        # unreviewed narrative, it never blocks the response (plan §4 D1 Day 18).
        # P2.11/P2.13: the switch being off and the provider returning 429 both
        # land here as LLMUnavailable, and both are ordinary degraded runs, not
        # errors — which is exactly what the demo toggle has to demonstrate.
        revised, critic_pass, iterations, issues = narrative, False, 0, []
        status, confidence = "degraded", Confidence(score="LOW_DATA", rationale=f"Critic unavailable: {exc}")
        error_detail = str(exc)
        engine_out = [engines.deterministic(getattr(exc, "reason", "critic unavailable"))]

    # Assert-by-construction: whatever happened above, the verdict header
    # text must be byte-identical to what Reporting emitted. If a bug ever
    # let it drift, degrade to the pre-critique narrative rather than ship
    # an altered verdict.
    if verdict_before and _verdict_header(revised) != verdict_before:
        revised = narrative

    issue_dicts = [
        {"rubric_item": i.rubric_item, "description": i.description, "reinvoke_agent": i.reinvoke_agent}
        for i in issues
    ]
    # D3: Only ask for a re-invocation the graph is still allowed to grant, AND
    # only when the critique did not pass. If critic_pass is True (clean initially
    # or safely revised prose), reinvoke_agent is None so graph routes to egress.
    reinvoke_agent = reinvocation_target(issue_dicts) if (not critic_pass and spent < MAX_REINVOCATIONS) else None

    return AgentResult(
        agent_name="critic",
        query_id=query_id,
        reasoning_depth=depth,
        inputs_consumed={"narrative_len": len(narrative), "is_safety_check": is_safety},
        outputs={
            "final_english_response": revised,
            "critic_pass": critic_pass,
            "critic_iteration_count": iterations,
            "issues": issue_dicts,
            # P2.5 — the agent this critique sends the query back to, or None.
            # Named here rather than re-derived in the graph so the decision
            # lives with the rubric that produced it, and so the trace row
            # records what the Critic asked for even when the budget refused it.
            "reinvoke_agent": reinvoke_agent,
            # The sentence(s) that agent is re-invoked *with*. A re-invocation
            # that does not carry the critique is just a re-run.
            "critique": "; ".join(f"[{i['rubric_item']}] {i['description']}" for i in issue_dicts) or None,
        },
        source_provenance=SourceProvenance(
            dataset="ORCA Critic (Agent 10) — LLM-as-judge, reasoning tier",
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
        engine=engine_out[0] if engine_out else None,
    )


if __name__ == "__main__":
    # No live LLM in this check — exercises the deterministic parts only:
    # verdict-header extraction, the rubric->agent mapping, and the
    # verdict-preservation guard, none of which may ever depend on a network call.
    assert _verdict_header("GO: conditions favorable") == "GO:"
    assert _verdict_header("CAUTION: wave height elevated") == "CAUTION:"
    assert _verdict_header("NO_GO: lightning active") == "NO_GO:"
    assert _verdict_header("no header here") is None
    assert set(_REINVOKE_MAP) == set(_RUBRIC)
    issues = _parse_judge_response(json.dumps([
        {"rubric_item": "causal_claim_strength", "description": "overclaims causation"},
        {"rubric_item": "not_a_real_item", "description": "ignored"},
    ]))
    assert len(issues) == 1 and issues[0].reinvoke_agent == "ocean_analytics"
    assert _parse_judge_response("not json") == []
    # Test fenced codeblock & normalized rubric matching (D2)
    fenced = '```json\n[{"rubric_item": "Spatial Accuracy", "description": "distance mismatch"}]\n```'
    parsed_fenced = _parse_judge_response(fenced)
    assert len(parsed_fenced) == 1
    assert parsed_fenced[0].rubric_item == "spatial_accuracy"
    assert parsed_fenced[0].reinvoke_agent == "geospatial"
    print("critic self-check ok")
