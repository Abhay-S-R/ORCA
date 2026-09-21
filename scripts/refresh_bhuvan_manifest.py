"""Re-scrape the ISRO Bhuvan / VEDAS portal manifest (`bhuvan_wms`, WEEKLY).

The manifest records which NRSC/SAC portals answered and how big their landing
pages were — it is a reachability record for the basemap/imagery layers, not
imagery itself, which is why a week-old copy is acceptable (freshness contract
§3.3) and why its breach is cosmetic rather than dangerous.

No credentials: every URL here is a public landing page.

Usage: python scripts/refresh_bhuvan_manifest.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "tier3" / "bhuvan"

# The set already in the manifest on disk — kept as a constant rather than read
# back from the file so a corrupted manifest cannot shrink the next refresh.
PORTALS: tuple[tuple[str, str], ...] = (
    ("bhuvan_main", "https://bhuvan.nrsc.gov.in/"),
    ("bhuvan_2d", "https://bhuvan-app1.nrsc.gov.in/bhuvan2d/"),
    ("vedas_sac", "https://vedas.sac.gov.in/"),
    ("bhuvan_wms", "https://bhuvan-vec1.nrsc.gov.in/bhuvan/wms?service=WMS&request=GetCapabilities"),
)


def scrape(name: str, url: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "ORCA/1.0 (SIH26176)"})
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        return {"name": name, "url": url, "status": "failed", "error": str(exc)[:200],
                "scraped_at": now}
    body = resp.text
    return {
        "name": name,
        "url": url,
        "status": "success",
        "size_bytes": len(resp.content),
        "scripts_count": len(re.findall(r"<script", body, flags=re.IGNORECASE)),
        "links_count": len(re.findall(r"<a\s+[^>]*href=", body, flags=re.IGNORECASE)),
        "scraped_at": now,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = [scrape(name, url) for name, url in PORTALS]
    manifest = {"summary": summary, "scraped_at": datetime.now(timezone.utc).isoformat()}
    out = OUT_DIR / "bhuvan_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for entry in summary:
        detail = entry.get("error", f"{entry.get('size_bytes', 0)} bytes")
        print(f"  {entry['name']:14} {entry['status']:8} {detail}")
    ok = sum(1 for e in summary if e["status"] == "success")
    print(f"\n{ok}/{len(summary)} portals reachable -> {out}")
    # A portal being down is a degradation to record, not a failure to refresh:
    # the manifest is now current either way. Only a total blackout is an error.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
