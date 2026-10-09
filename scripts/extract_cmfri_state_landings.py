"""Extract CMFRI's state-wise marine fish landings from its own PDF booklet.

Procurement runbook §C2. `datagov_marine_fish_landings.csv` holds four Tamil
Nadu districts, so `diagnose_productivity_decline` could answer PS-Q7 for
Ramanathapuram and nowhere else. CMFRI publishes no CSV endpoint — the
national estimate is an annual booklet on `eprints.cmfri.org.in` — so this
reads the tables out of the PDF and writes a CSV beside the data.gov.in one.

WHAT THIS GIVES AND WHAT IT DOES NOT. The booklet is one year per edition
and only the 2024 edition is on eprints, so this yields a single-year state
record, not a multi-year series: it widens PS-Q7's *coverage* from four
districts to every maritime state, and does not turn one year into a trend.
Each state's narrative paragraph is carried verbatim as `cmfri_note` so the
answer cites CMFRI's own words about why that year moved, rather than ORCA
inferring a reason from one number.

Lakshadweep is absent by design — the booklet covers mainland India plus the
Andaman & Nicobar Islands, and a state with no row is reported as no data.

    python scripts/extract_cmfri_state_landings.py
    python scripts/extract_cmfri_state_landings.py --self-check   # no network
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
OUT_CSV = DATA / "tier1" / "fisheries" / "cmfri_state_landings.csv"
OUT_META = DATA / "tier1" / "fisheries" / "cmfri_state_landings_provenance.json"
PDF_CACHE = DATA / "tier1" / "fisheries" / "cmfri_marine_fish_landings_2024.pdf"

EPRINT_URL = "https://eprints.cmfri.org.in/19094/"
PDF_URL = ("https://eprints.cmfri.org.in/19094/1/"
           "Marine%20Fish%20Landings%20in%20India%20-%202024.pdf")
REPORT_YEAR = 2024
CITATION = "CMFRI (2025). Marine Fish Landings in India 2024. CMFRI Booklet Series No. 24/2025, ICAR-CMFRI, Kochi."

# The booklet's own state headings, spelled as the PDF spells them. A state
# absent from this list is absent from the booklet, not silently dropped.
STATES = [
    "West Bengal", "Odisha", "Andhra Pradesh", "Tamil Nadu", "Puducherry",
    "Kerala", "Karnataka", "Goa", "Maharashtra", "Gujarat", "Daman & Diu",
    "Andaman & Nicobar Islands",
]
# Coast each state's landings come off, so a query about the Arabian Sea does
# not get handed a Bay of Bengal figure.
COAST = {
    "West Bengal": "east", "Odisha": "east", "Andhra Pradesh": "east",
    "Tamil Nadu": "east", "Puducherry": "east",
    "Kerala": "west", "Karnataka": "west", "Goa": "west",
    "Maharashtra": "west", "Gujarat": "west", "Daman & Diu": "west",
    "Andaman & Nicobar Islands": "islands",
}
LAKH_TONNES = 100_000
FIELDS = ["State", "Coast", "Year", "Total_Landings_Tonnes", "Landings_Lakh_Tonnes", "Source", "CMFRI_Note"]

# "Gujarat 7.54" — the heading line of each state's page block. Anchored on
# the state name so a stray figure elsewhere in the prose cannot match.
_HEADING = r"\s+(\d+\.\d{1,2})\b"


def extract_state_landings(text: str) -> list[dict[str, object]]:
    """[{State, Landings_Lakh_Tonnes, CMFRI_Note}] from the booklet text.

    Split out from the PDF read so --self-check can exercise the parse
    offline: the fragile part is this regex, not pdfplumber.
    """
    found: list[tuple[int, str, float]] = []
    for state in STATES:
        m = re.search(re.escape(state) + _HEADING, text)
        if m:
            found.append((m.start(), state, float(m.group(1))))
    found.sort()

    rows: list[dict[str, object]] = []
    for i, (start, state, lakh) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        note = re.sub(r"\s+", " ", text[start:end]).strip()
        rows.append({
            "State": state,
            "Landings_Lakh_Tonnes": lakh,
            "CMFRI_Note": note[:1200],
        })
    return rows


def pdf_text(path: Path, first_page: int = 7, last_page: int = 14) -> str:
    """Text of the state-profile pages. Page numbers are 0-based indices into
    the 2024 edition; a different edition would need them re-checked, which is
    why the count assertion below fails loudly rather than writing a short CSV."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[first_page:last_page]
        return "\n".join(p.extract_text() or "" for p in pages)


def fetch_pdf(path: Path = PDF_CACHE) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(PDF_URL, timeout=180) as r:
        path.write_bytes(r.read())
    return path


def main() -> int:
    rows = extract_state_landings(pdf_text(fetch_pdf()))
    if len(rows) < len(STATES):
        missing = sorted(set(STATES) - {str(r["State"]) for r in rows})
        print("state headings not found: " + ", ".join(missing) +
              " — the booklet layout changed, re-check the page range", file=sys.stderr)
        return 1

    out = [{
        "State": r["State"],
        "Coast": COAST[str(r["State"])],
        "Year": REPORT_YEAR,
        # Whole tonnes, to match the data.gov.in district file's units.
        "Total_Landings_Tonnes": round(float(r["Landings_Lakh_Tonnes"]) * LAKH_TONNES),
        "Landings_Lakh_Tonnes": r["Landings_Lakh_Tonnes"],
        "Source": "CMFRI Marine Fish Landings in India 2024",
        "CMFRI_Note": r["CMFRI_Note"],
    } for r in rows]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)

    OUT_META.write_text(json.dumps({
        "dataset": "CMFRI estimated marine fish landings by state",
        "authority_tier": "T1",
        "citation": CITATION,
        "report_year": REPORT_YEAR,
        "source_url": EPRINT_URL,
        "pdf_url": PDF_URL,
        "extraction_method": "pdfplumber text extraction of the state-profile pages",
        "acquisition_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "state_count": len(out),
        "coverage_note": "One reporting year. Lakshadweep is not covered by this booklet. "
                         "A state figure is an annual estimate, not a trend.",
    }, indent=2), encoding="utf-8")

    total = sum(int(r["Total_Landings_Tonnes"]) for r in out)
    print("%d states -> %s (%.2f million tonnes total)" % (
        len(out), OUT_CSV.relative_to(REPO_ROOT), total / 1e6))
    return 0


def _self_check() -> None:
    """The regex, on the layout the 2024 booklet actually produces."""
    sample = (
        "West Bengal 2.33  State experienced impact Estimated Landings: lakh tonnes "
        "significant increase 35% record high.\n"
        "Odisha 1.54 primarily attributed\n"
        "Gujarat 7.54 reduced fishing effort Estimated Landings: lakh tonnes\n"
        "Daman & Diu 0.51 Estimated Landings: lakh tonnes declined 44% in 2024\n"
    )
    rows = extract_state_landings(sample)
    got = {str(r["State"]): r["Landings_Lakh_Tonnes"] for r in rows}
    assert got == {"West Bengal": 2.33, "Odisha": 1.54, "Gujarat": 7.54, "Daman & Diu": 0.51}, got
    # Page order, not STATES order — the note must belong to its own state.
    assert [r["State"] for r in rows] == ["West Bengal", "Odisha", "Gujarat", "Daman & Diu"]
    assert "record high" in str(rows[0]["CMFRI_Note"])
    assert "Odisha" not in str(rows[0]["CMFRI_Note"]), "note ran past the state's own block"

    # A percentage in the prose must never be mistaken for a landings figure.
    assert extract_state_landings("Kerala grew 35% in 2024") == []
    # lakh -> tonnes, the unit the district file already uses.
    assert round(2.33 * LAKH_TONNES) == 233000
    assert set(COAST) == set(STATES)
    print("self-check ok: state heading parse, block boundaries, unit conversion")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
