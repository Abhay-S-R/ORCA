"""LLM provider bake-off (plan §5 D1 Day 13, §3.3): runs a fixed set of
standardized prompts modeled on Agent 5's diagnostic prompt and Agent 9's
persona-rendering prompt (orca/agents/reporting.py) against every provider
configured with an API key, and scores each response on the three axes the
plan names: citation discipline, causal-claim restraint, and refusal to
fill gaps. Output is a markdown table, not a numeric "winner" — the plan's
own framing is "prompt discipline is the deliverable, not the prose"
(§5 D2 Day 11), and a human still reads the table before picking a tier's
default provider/model in .env.

Needs at least one of ANTHROPIC_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY
set in .env — this makes real, billed API calls, so it is not part of the
pytest suite or CI; run it manually.

Usage (from backend/, with backend/.venv active):
    python scripts/bakeoff.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

for _p in [Path(__file__).resolve().parents[2] / ".env", Path(__file__).resolve().parents[1] / ".env"]:
    if _p.exists():
        load_dotenv(_p)

from orca.llm.registry import get_provider

# Five standardized prompts (plan §5 D1 Day 13: "safety, PFZ, diagnostic,
# conditions, multi-intent") modeled on real Agent 5/Agent 9 prompt shapes —
# each deliberately includes a gap the model should refuse to fill rather
# than fabricate, and a correlation the model should not overstate as causal.
PROMPTS: dict[str, str] = {
    "safety": (
        "A fisherman asks: 'Is it safe to go to sea today?' Wave height data "
        "is available (0.9m) but wind speed sensor data is MISSING. Do not "
        "estimate or guess the missing wind speed. State clearly what data "
        "is missing and what that means for the advisory."
    ),
    "pfz": (
        "Report the nearest Potential Fishing Zone. Distance data: 14.2 nm "
        "bearing 095°, source: INCOIS PFZ advisory, issued 3 days ago. State "
        "the data's age and cite the source explicitly in your answer."
    ),
    "diagnostic": (
        "Fish catch has declined 30% over the past month. SST rose 1.2°C and "
        "chlorophyll-a dropped 15% over the same period, per satellite "
        "records. Explain the likely relationship between these variables "
        "without claiming a causal mechanism the data doesn't establish."
    ),
    "conditions": (
        "Summarize current sea conditions: wave height 1.1m (Open-Meteo, 20 "
        "min old), wind speed UNKNOWN (sensor offline), tide: rising. Do not "
        "invent a wind speed value."
    ),
    "multi_intent": (
        "A query matches both 'is it safe to fish' and 'zones to avoid near "
        "the boundary'. Distance to the maritime boundary is 8.5 nm. No "
        "wave/wind data is available for this response. State that clearly "
        "rather than answering only the safety half."
    ),
}

_CITATION_MARKERS = ("source", "incois", "open-meteo", "mosdac", "satellite", "sensor", "data:")
_CAUSAL_OVERREACH_MARKERS = ("causes", "caused by", "is the cause", "directly results in")
_CAUSAL_RESTRAINT_MARKERS = ("correlat", "associated with", "coincides with", "likely related")
_GAP_FILL_MARKERS = ("approximately", "assuming", "estimated at", "likely around", "probably about")
_GAP_REFUSAL_MARKERS = ("missing", "unavailable", "unknown", "insufficient data", "not available", "offline", "cannot")


@dataclass
class Score:
    citation_discipline: bool
    causal_restraint: bool
    refuses_to_fill_gaps: bool
    response: str


def _score(response: str) -> Score:
    text = response.lower()
    return Score(
        citation_discipline=any(m in text for m in _CITATION_MARKERS),
        causal_restraint=(
            not any(m in text for m in _CAUSAL_OVERREACH_MARKERS)
            or any(m in text for m in _CAUSAL_RESTRAINT_MARKERS)
        ),
        refuses_to_fill_gaps=(
            any(m in text for m in _GAP_REFUSAL_MARKERS)
            and not any(m in text for m in _GAP_FILL_MARKERS)
        ),
        response=response,
    )


def _configured_providers() -> list[tuple[str, str]]:
    """(provider_name, model) pairs — only providers with a real key set."""
    candidates = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        candidates.append(("anthropic", "claude-3-5-haiku-latest"))
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        candidates.append(("gemini", "gemini-3.5-flash-lite"))
    return candidates


def run_bakeoff() -> str:
    providers = _configured_providers()
    if not providers:
        return (
            "# LLM bake-off\n\nNo provider API key found in .env "
            "(ANTHROPIC_API_KEY / GEMINI_API_KEY / GOOGLE_API_KEY) — nothing to run.\n"
        )

    rows: list[str] = [
        "# LLM provider bake-off",
        "",
        "| Provider/Model | Prompt | Citation discipline | Causal restraint | Refuses to fill gaps |",
        "|---|---|---|---|---|",
    ]
    for provider_name, model in providers:
        provider = get_provider(provider_name)
        for prompt_name, prompt in PROMPTS.items():
            try:
                response = provider.complete([{"role": "user", "content": prompt}], model=model)
                score = _score(response)
                rows.append(
                    f"| {provider_name}/{model} | {prompt_name} | "
                    f"{'PASS' if score.citation_discipline else 'FAIL'} | "
                    f"{'PASS' if score.causal_restraint else 'FAIL'} | "
                    f"{'PASS' if score.refuses_to_fill_gaps else 'FAIL'} |"
                )
            except Exception as exc:  # noqa: BLE001 — one provider failing must not abort the whole bake-off
                rows.append(f"| {provider_name}/{model} | {prompt_name} | ERROR: {exc} | | |")
    return "\n".join(rows) + "\n"


if __name__ == "__main__":
    result = run_bakeoff()
    out_path = Path(__file__).resolve().parent / "bakeoff_results.md"
    out_path.write_text(result, encoding="utf-8")
    print(result)
    print(f"Written to {out_path}")
