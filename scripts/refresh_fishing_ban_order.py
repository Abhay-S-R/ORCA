"""Keep the seasonal fishing-ban window current, and shout when it is not.

Procurement runbook §C4, the half the guide describes as "dates, not polygons
— a table is a legitimate answer here". PS-C8 names fishing-ban waters
separately from MPAs, and nothing in ORCA knew a ban period existed.

THE ORDER IS A SCANNED PDF. The Department of Fisheries publishes the annual
uniform ban as an image, not as text or as data, so the two dates below were
read off the scan by a human and are transcribed here with the file number
that identifies the order they came from. What this script automates is the
part that actually rots: it asks DoF's own CMS whether a newer ban order has
been published, and fails loudly if one has, rather than letting a superseded
window sit in the data telling a fisher the sea is open.

    python scripts/refresh_fishing_ban_order.py           # re-check + rewrite
    python scripts/refresh_fishing_ban_order.py --self-check   # no network
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
OUT_PATH = DATA / "tier1" / "fisheries" / "seasonal_fishing_ban.json"

DOF_API = "https://www.dof.gov.in/cms/wp-json/wp/v2/central_documents"
DOF_MEDIA = "https://www.dof.gov.in/cms/wp-json/wp/v2/media/"

# Transcribed from the order itself, not from a news report or a summary:
#   File No. j-2103035/1/2026-Fy (E-27594), dated 16 March 2026, signed by the
#   Deputy Commissioner (Fisheries), issued under Rule 14(e) of the
#   Sustainable Harnessing of Fisheries in the EEZ Rules, 2025.
ORDER = {
    "file_number": "j-2103035/1/2026-Fy (E-27594)",
    "order_date": "2026-03-16",
    "issuing_authority": "Department of Fisheries, Ministry of Fisheries, Animal Husbandry and Dairying, Government of India",
    "legal_basis": "Rule 14(e), Sustainable Harnessing of Fisheries in the Exclusive Economic Zone Rules, 2025, "
                   "under the Territorial Waters, Continental Shelf, Exclusive Economic Zone and Other "
                   "Maritime Zones Act, 1976",
    "wp_post_id": 17168,
    "pdf_url": "https://dof.gov.in/static/uploads/2026/03/effe936ad06ebd01aaa12990dbb7e7d5.pdf",
    # The order's own scope sentence, which is narrower than "no fishing":
    "applies_to": "all fishing vessels in the Indian EEZ BEYOND territorial waters",
    "exemption": "traditional non-motorized units are exempted",
}

# Both coasts, 61 days each, as printed in the order. Tamil Nadu is listed on
# both coasts because it has one — Kanyakumari round to the Gulf of Mannar is
# west-coast water under this order.
BAN_WINDOWS = [
    {
        "coast": "east",
        "start": "2026-04-15",
        "end": "2026-06-14",
        "days": 61,
        "states": ["West Bengal", "Odisha", "Andhra Pradesh", "Puducherry",
                   "Tamil Nadu", "Andaman & Nicobar Islands"],
    },
    {
        "coast": "west",
        "start": "2026-06-01",
        "end": "2026-07-31",
        "days": 61,
        "states": ["Gujarat", "Daman & Diu", "Karnataka", "Goa",
                   "Maharashtra", "Kerala", "Tamil Nadu", "Lakshadweep"],
    },
]

# Territorial waters are 12 NM; the central order starts outside them. Inside
# 12 NM the ban is each STATE's to notify under its own Marine Fishing
# Regulation Act, and those dates usually but do not always match. ORCA says
# "check your state notification" there rather than asserting the central one.
TERRITORIAL_WATERS_NM = 12.0


def newer_orders(after: str = ORDER["order_date"]) -> list[dict[str, str]]:
    """Ban orders DoF has published since the one transcribed above."""
    q = urllib.parse.urlencode({"search": "Fishing Ban Order", "per_page": 20})
    with urllib.request.urlopen(DOF_API + "?" + q, timeout=60) as r:
        posts = json.load(r)
    out = []
    for p in posts:
        acf = p.get("acf") or {}
        stamp = str(acf.get("file_date") or "")  # YYYYMMDD
        iso = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) == 8 else ""
        if iso and iso > after:
            out.append({"id": p.get("id"), "date": iso,
                        "title": (p.get("title") or {}).get("rendered", "")})
    return out


def build_payload(supersede_warning: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "dataset": "Uniform annual fishing ban in the Indian EEZ",
        "authority_tier": "T1",
        "order": ORDER,
        "territorial_waters_nm": TERRITORIAL_WATERS_NM,
        "windows": BAN_WINDOWS,
        "transcription_note": "The order is published as a scanned image; the dates here were read "
                              "off that scan and are traceable to the file number in `order`. "
                              "Verify against the PDF before relying on it operationally.",
        "state_waters_note": "Inside 12 NM the applicable ban is the state's own notification under "
                             "its Marine Fishing Regulation Act, which this file does not carry.",
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "superseded_by": supersede_warning or [],
    }


def ban_status(lat_coast: str, when: date, distance_from_shore_nm: float | None = None,
               windows: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Is the uniform EEZ ban in force on `when` for a `lat_coast` position?

    Kept here, beside the dates, so the rule and the data it reads cannot
    drift apart; `geospatial.fishing_ban_status` is the caller that knows how
    to turn a lat/lon into a coast.
    """
    for w in windows or BAN_WINDOWS:
        if str(w["coast"]) != lat_coast:
            continue
        start = date.fromisoformat(str(w["start"]))
        end = date.fromisoformat(str(w["end"]))
        if start <= when <= end:
            inshore = distance_from_shore_nm is not None and distance_from_shore_nm < TERRITORIAL_WATERS_NM
            return {
                "in_ban_period": True,
                "coast": lat_coast,
                "window": f"{w['start']} to {w['end']}",
                "days": w["days"],
                "applies_here": not inshore,
                "note": ("Inside territorial waters (12 NM) — the central EEZ order does not reach here; "
                         "the state's own Marine Fishing Regulation Act notification governs. Check it."
                         if inshore else
                         "The central uniform ban is in force in the EEZ beyond 12 NM. "
                         "Traditional non-motorized units are exempt."),
            }
        return {
            "in_ban_period": False,
            "coast": lat_coast,
            "next_window": f"{w['start']} to {w['end']}",
            "applies_here": False,
            "note": "No uniform EEZ fishing ban in force on this date for this coast.",
        }
    return {"in_ban_period": False, "coast": lat_coast, "applies_here": False,
            "note": f"no ban window on record for coast {lat_coast!r}"}


def main() -> int:
    try:
        newer = newer_orders()
    except Exception as exc:  # network down is not a reason to write nothing
        print("could not reach DoF to check for a newer order: %s" % exc, file=sys.stderr)
        newer = []

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(build_payload(newer), indent=2, ensure_ascii=False), encoding="utf-8")
    print("ban windows -> %s" % OUT_PATH.relative_to(REPO_ROOT))
    for w in BAN_WINDOWS:
        print("  %-5s %s to %s (%d days)" % (w["coast"], w["start"], w["end"], w["days"]))
    if newer:
        print("\nSUPERSEDED: DoF has published a newer ban order since %s:" % ORDER["order_date"], file=sys.stderr)
        for n in newer:
            print("  %s  %s" % (n["date"], n["title"][:90]), file=sys.stderr)
        print("Re-read the new scan and update ORDER/BAN_WINDOWS in this file.", file=sys.stderr)
        return 2
    return 0


def _self_check() -> None:
    """The date rule, including the two edges that matter."""
    # Both days inclusive, as the order says in those words.
    assert ban_status("east", date(2026, 4, 15))["in_ban_period"]
    assert ban_status("east", date(2026, 6, 14))["in_ban_period"]
    assert not ban_status("east", date(2026, 4, 14))["in_ban_period"]
    assert not ban_status("east", date(2026, 6, 15))["in_ban_period"]

    # The coasts are offset by six weeks — an east-coast date is not a
    # west-coast ban, which is the mistake a single national window would make.
    assert ban_status("east", date(2026, 5, 1))["in_ban_period"]
    assert not ban_status("west", date(2026, 5, 1))["in_ban_period"]
    assert ban_status("west", date(2026, 7, 31))["in_ban_period"]

    # Inside 12 NM the central order does not apply, and says why.
    inshore = ban_status("west", date(2026, 7, 1), distance_from_shore_nm=5.0)
    assert inshore["in_ban_period"] and inshore["applies_here"] is False
    assert "Marine Fishing Regulation Act" in str(inshore["note"])
    offshore = ban_status("west", date(2026, 7, 1), distance_from_shore_nm=40.0)
    assert offshore["applies_here"] is True

    assert all(w["days"] == 61 for w in BAN_WINDOWS)
    assert build_payload()["order"]["file_number"].startswith("j-2103035")
    print("self-check ok: inclusive edges, per-coast windows, 12 NM territorial-waters carve-out")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
