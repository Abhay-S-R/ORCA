"""Messy-prompt test harness (Prompt Routing Revamp §7.6).

Runs prompts from tests/messy_prompts.jsonl through the Understand agent
and validates the output against expected values.

In CI (no keys): checks validation logic and fallback behavior.
As live script: runs against real models and reports pass rate.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.orca.agents.understand import run
from backend.orca.state import ORCAState


@dataclass
class TestCase:
    prompt: str
    expected_kind: str
    expected_intents: list[str]
    expected_places: list[dict[str, Any]]
    expected_when: Any
    expected_followup: bool
    distress: bool


def load_test_cases(path: Path) -> list[TestCase]:
    cases = []
    with path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                cases.append(TestCase(
                    prompt=data["prompt"],
                    expected_kind=data["expected_kind"],
                    expected_intents=data["expected_intents"],
                    expected_places=data["expected_places"],
                    expected_when=data["expected_when"],
                    expected_followup=data["expected_followup"],
                    distress=data["distress"],
                ))
            except json.JSONDecodeError as e:
                print(f"Line {line_num}: JSON decode error: {e}")
            except KeyError as e:
                print(f"Line {line_num}: Missing key {e}")
    return cases


def check_kind(actual: str, expected: str) -> bool:
    return actual == expected


def check_intents(actual: list[str], expected: list[str]) -> bool:
    return set(actual) == set(expected)


def check_places(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> bool:
    if len(actual) != len(expected):
        return False
    for a, e in zip(actual, expected):
        if a.get("raw") != e.get("raw"):
            return False
        a_norm = a.get("normalized")
        e_norm = e.get("normalized")
        if e_norm is not None and a_norm != e_norm:
            return False
    return True


def check_when(actual: dict[str, Any] | None, expected: Any) -> bool:
    if expected is None:
        return actual is None
    if expected == "has_range":
        return actual is not None and "start" in actual and "end" in actual
    if expected in ("past", "future"):
        return actual is not None
    return False


def check_followup(actual: bool, expected: bool) -> bool:
    return actual == expected


TEST_FILE = Path(__file__).parent / "messy_prompts.jsonl"
CASES = load_test_cases(TEST_FILE)


@pytest.fixture(autouse=True)
def _ci_mode():
    # CI mode: disable LLM to test deterministic fallback
    os.environ["ORCA_LLM_ENABLED"] = "0"
    yield
    os.environ.pop("ORCA_LLM_ENABLED", None)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.prompt[:60])
def test_messy_prompt(case: TestCase):
    state: ORCAState = {
        "query_id": f"test-{hash(case.prompt) & 0xffff}",
        "raw_user_query": case.prompt,
        "session_history": [],
        "user_location": None,
    }
    result = run(state)
    outputs = result.outputs or {}

    assert check_kind(outputs.get("kind", ""), case.expected_kind), \
        f"kind: got {outputs.get('kind')}, expected {case.expected_kind}"
    assert check_intents(outputs.get("intents", []), case.expected_intents), \
        f"intents: got {outputs.get('intents')}, expected {case.expected_intents}"
    assert check_places(outputs.get("places", []), case.expected_places), \
        f"places: got {outputs.get('places')}, expected {case.expected_places}"
    assert check_when(outputs.get("when"), case.expected_when), \
        f"when: got {outputs.get('when')}, expected {case.expected_when}"
    assert check_followup(outputs.get("is_followup", False), case.expected_followup), \
        f"is_followup: got {outputs.get('is_followup')}, expected {case.expected_followup}"


if __name__ == "__main__":
    ci_mode = "--ci" in sys.argv or os.environ.get("CI") == "true"
    if ci_mode:
        os.environ["ORCA_LLM_ENABLED"] = "0"

    passed = 0
    failures = []

    for case in CASES:
        state: ORCAState = {
            "query_id": f"test-{hash(case.prompt) & 0xffff}",
            "raw_user_query": case.prompt,
            "session_history": [],
            "user_location": None,
        }
        result = run(state)
        outputs = result.outputs or {}

        ok = True
        reasons = []

        if not check_kind(outputs.get("kind", ""), case.expected_kind):
            ok = False
            reasons.append(f"kind: got {outputs.get('kind')}, expected {case.expected_kind}")

        if not check_intents(outputs.get("intents", []), case.expected_intents):
            ok = False
            reasons.append(f"intents: got {outputs.get('intents')}, expected {case.expected_intents}")

        if not check_places(outputs.get("places", []), case.expected_places):
            ok = False
            reasons.append(f"places: got {outputs.get('places')}, expected {case.expected_places}")

        if not check_when(outputs.get("when"), case.expected_when):
            ok = False
            reasons.append(f"when: got {outputs.get('when')}, expected {case.expected_when}")

        if not check_followup(outputs.get("is_followup", False), case.expected_followup):
            ok = False
            reasons.append(f"is_followup: got {outputs.get('is_followup')}, expected {case.expected_followup}")

        if ok:
            passed += 1
        else:
            failures.append(f"'{case.prompt}': " + "; ".join(reasons))

    print(f"Messy-prompt tests: {passed}/{len(CASES)} passed")
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("All tests passed.")
        sys.exit(0)