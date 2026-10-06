import glob
import re
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


# 1. Vendor SDK guard
vendor_matches = [
    f for f in glob.glob("orca/agents/**/*.py", recursive=True)
    if re.search(
        r"^\s*(import|from)\s+(anthropic|openai|google\.generativeai|google\.genai)",
        _read(f), re.MULTILINE,
    )
]
assert not vendor_matches, f"Vendor SDK imported in agents: {vendor_matches}"
print("[PASS] CI Guard 1: Vendor SDK guard passed.")

# 2. Persona leak guard
pattern = re.compile(r"\bstakeholder_persona\b|\bpersona['\"]?\s*[:=]|\[['\"]persona['\"]]|\.get\(['\"]persona")
fails = [
    f for f in glob.glob("orca/agents/**/*.py", recursive=True)
    if not any(x in f for x in ["language.py", "reporting.py"]) and pattern.search(_read(f))
]
fails += [f for f in glob.glob("orca/auth/**/*.py", recursive=True) if pattern.search(_read(f))]
assert not fails, f"Persona leak found in: {fails}"
print("[PASS] CI Guard 2: Persona leak guard passed (including orca/auth/).")

# 3. Secret scan
secret_matches = re.findall(r"=[A-Za-z0-9_\-]{12,}", _read("../.env.example"))
assert not secret_matches, f"Secret found in .env.example: {secret_matches}"
print("[PASS] CI Guard 3: Zero-valued secret scan passed.")

# 4. Safety-path guard (P0.12, principle 2 / R-JUDGE-4): CI fails if any of
# these files imports orca.llm or a vendor SDK. This is the guard the plan
# says CI is supposed to already have and does not — it does NOT check that
# a number is never fabricated (that cannot be checked statically; P2.2 and
# P4.6 cover the behaviour), only that the files responsible for a go/no-go
# verdict never gain the *means* to call a model at all.
SAFETY_PATH_FILES = [
    "orca/agents/risk_assessment.py",
    "orca/agents/geospatial.py",
    "orca/agents/distress.py",
    "orca/agents/sentinel.py",
    "orca/agents/weather_intelligence.py",
    "orca/agents/visualization.py",
]
llm_import_pattern = re.compile(
    r"^\s*(import|from)\s+(orca\.llm|orca\.agents\.distress_escalation|anthropic|openai|google\.generativeai|google\.genai)",
    re.MULTILINE,
)
safety_path_fails = [
    f for f in SAFETY_PATH_FILES
    if Path(f).exists() and llm_import_pattern.search(_read(f))
]
assert not safety_path_fails, f"Safety-path file imports an LLM: {safety_path_fails}"
print("[PASS] CI Guard 4: Safety-path LLM-import guard passed.")

print("\nALL 4 CI GUARDS VERIFIED GREEN!")
