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

print("\nALL 3 CI GUARDS VERIFIED GREEN!")
