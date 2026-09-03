import re
import glob
import sys

# 1. Vendor SDK guard
vendor_matches = []
for f in glob.glob("orca/agents/**/*.py", recursive=True):
    content = open(f, encoding="utf-8").read()
    if re.search(r"^\s*(import|from)\s+(anthropic|openai|google\.generativeai|google\.genai)", content, re.MULTILINE):
        vendor_matches.append(f)
assert not vendor_matches, f"Vendor SDK imported in agents: {vendor_matches}"
print("[PASS] CI Guard 1: Vendor SDK guard passed.")

# 2. Persona leak guard
pattern = re.compile(r"\bstakeholder_persona\b|\bpersona['\"]?\s*[:=]|\[['\"]persona['\"]]|\.get\(['\"]persona")
fails = []
for f in glob.glob("orca/agents/**/*.py", recursive=True):
    if any(x in f for x in ["language.py", "reporting.py"]):
        continue
    content = open(f, encoding="utf-8").read()
    if pattern.search(content):
        fails.append(f)
for f in glob.glob("orca/auth/**/*.py", recursive=True):
    content = open(f, encoding="utf-8").read()
    if pattern.search(content):
        fails.append(f)
assert not fails, f"Persona leak found in: {fails}"
print("[PASS] CI Guard 2: Persona leak guard passed (including orca/auth/).")

# 3. Secret scan
env_example = open("../.env.example", encoding="utf-8").read()
secret_matches = re.findall(r"=[A-Za-z0-9_\-]{12,}", env_example)
assert not secret_matches, f"Secret found in .env.example: {secret_matches}"
print("[PASS] CI Guard 3: Zero-valued secret scan passed.")

print("\nALL 3 CI GUARDS VERIFIED GREEN!")
