"""Refresh the NASA CMR granule listing for MODIS-Aqua chlorophyll
(`nasa_ocean_color`, WEEKLY — freshness contract §3.3).

What this file is, and is not: `nasa_cmr_modis_chl_granules.json` is the
**granule metadata** CMR returns, not the imagery. ORCA cites it as the
cross-check / fallback for MOSDAC chlorophyll, and the citation needs a current
list of what exists and when it was acquired.

CMR search is public — no Earthdata login is needed for this script. Downloading
the .nc granules themselves *does* require an Earthdata token; that is a separate
job and deliberately not done here (we do not read the pixels today).

Usage: python scripts/refresh_nasa_ocean_color.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "data" / "tier2" / "nasa" / "nasa_cmr_modis_chl_granules.json"

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
PARAMS = {
    "short_name": "MODISA_L3m_CHL_NRT",
    "page_size": 10,
    "sort_key": "-start_date",  # newest first, same query the file on disk records
}


def main() -> int:
    try:
        resp = requests.get(CMR, params=PARAMS, timeout=60,
                            headers={"User-Agent": "ORCA/1.0 (SIH26176)"})
        resp.raise_for_status()
        payload = resp.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
        print(f"[ERROR] CMR search failed: {exc}")
        return 1

    entries = payload.get("feed", {}).get("entry", [])
    if not entries:
        # Writing an empty listing would silently erase the fallback's citation.
        print("[ERROR] CMR returned no granules — leaving the existing file alone.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for e in entries[:5]:
        print(f"  {e.get('time_start', '?')[:10]}  {e.get('producer_granule_id', '?')}")
    print(f"\n{len(entries)} granules, newest {entries[0].get('time_start', '?')[:10]} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
