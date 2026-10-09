"""Re-scrape the ISRO Bhuvan / VEDAS portal manifest (`bhuvan_wms`, WEEKLY).

The manifest records which NRSC/SAC portals answered and how big their landing
pages were — it is a reachability record for the basemap/imagery layers, not
imagery itself, which is why a week-old copy is acceptable (freshness contract
§3.3) and why its breach is cosmetic rather than dangerous.

It also carries `core_wms_services`, the OGC service catalog that
`analytics_loaders.load_bhuvan_wms_services()` serves to Agent Discovery. That
catalog used to live in `bhuvan_15days_marine_manifest.json`, which nothing
refreshed — so `freshness.py` reported the age of *this* file while the app
served a manifest last written 2026-08-30. One writer and one reader now, so
the badge and the served catalog cannot drift apart again.

No credentials: every URL here is a public landing page.

Usage: python scripts/refresh_bhuvan_manifest.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
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


# The OGC endpoints Discovery lists for `bhuvan_wms`. A curated catalog, not a
# scrape result: these are service descriptions (endpoint + layer names), and
# GetCapabilities is already probed by the `bhuvan_wms` entry in PORTALS above.
# Same reasoning as PORTALS — held as a constant so a bad run cannot shrink it.
WMS_SERVICES: tuple[dict, ...] = (
    {
        "name": "Bhuvan 2D Vector WMS",
        "url": "https://bhuvan-vec1.nrsc.gov.in/bhuvan/gwc/service/wms/",
        "type": "OGC WMS / WMTS",
        "layers": ["india_coastal_boundary", "india_states", "major_ports", "inshore_waterways"],
    },
    {
        "name": "Bhuvan Satellite Basemap WMTS Tile Cache",
        "url": "https://vtile1.nrsc.gov.in/bhuvan/gwc/service/wmts/",
        "type": "OGC WMTS Tile Service",
        "matrix_sets": ["EPSG:4326", "EPSG:3857"],
        "tile_endpoints": [
            "https://vtile1.nrsc.gov.in/bhuvan/gwc/service/wmts/",
            "https://vtile2.nrsc.gov.in/bhuvan/gwc/service/wmts/",
            "https://vtile3.nrsc.gov.in/bhuvan/gwc/service/wmts/",
            "https://vtile4.nrsc.gov.in/bhuvan/gwc/service/wmts/",
        ],
    },
    {
        "name": "Bhuvan Ocean Thematic Services",
        "url": "https://bhuvan-app1.nrsc.gov.in/thematic/thematic/index.php",
        "type": "Thematic GIS Portal",
        "layers": ["coastal_land_use", "coral_reef_zonation", "mangrove_wetlands", "shoreline_change"],
    },
    {
        "name": "SAC VEDAS Marine Geoportal",
        "url": "https://vedas.sac.gov.in/",
        "type": "Scientific Geo-Visualization",
        "layers": ["ocean_color_ocm3", "sst_insat3dr", "scatterometer_winds_scatsat"],
    },
)


def scrape(name: str, url: str) -> dict:
    now = datetime.now(UTC).isoformat()
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
    manifest = {
        "summary": summary,
        "core_wms_services": [dict(svc) for svc in WMS_SERVICES],
        "scraped_at": datetime.now(UTC).isoformat(),
    }
    out = OUT_DIR / "bhuvan_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for entry in summary:
        detail = entry.get("error", f"{entry.get('size_bytes', 0)} bytes")
        print(f"  {entry['name']:14} {entry['status']:8} {detail}")
    ok = sum(1 for e in summary if e["status"] == "success")
    print(f"\n{ok}/{len(summary)} portals reachable, "
          f"{len(WMS_SERVICES)} OGC services catalogued -> {out}")
    # A portal being down is a degradation to record, not a failure to refresh:
    # the manifest is now current either way. Only a total blackout is an error.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
