#!/usr/bin/env python
"""Write the national PFZ layer (`all_india_pfz_advisories.geojson`) from the
current INCOIS scrape. DLC R-INDIA-3.

**This script used to invent advisories.** Until 2026-09-19 it appended 54
hardcoded points — Gujarat, Odisha, West Bengal, Andaman and nine extra South
Tamil Nadu nodes — with made-up coordinates, bearings, depths and `mean_sst_c`
values, each stamped `"source": "INCOIS Marine Fisheries Advisory"` and
`"valid_for": "2026-09-02"`. INCOIS never issued them. They were what made the
national file look like it covered 13 sectors to the live scrape's 11, which is
the coverage claim R-INDIA-3 records and which was never true.

A fabricated fishing advisory is a boat sent to water nobody surveyed, under a
government agency's name. So the node lists are gone rather than relabelled, on
the same reasoning that removed the fabricated tide-gauge reading (see
`ocean_analytics.tide_gauge_observation`). A sector INCOIS did not publish today
is reported as a data gap by `ocean_analytics.sector_status()`, which carries
INCOIS's own cloud-cover message — an honest "no advisory today, here is why"
instead of a confident wrong one.

What remains is a straight national copy of the live scrape, which INCOIS now
publishes for every sector. Worth knowing: that makes this file redundant with
`incois_pfz_live_advisories.geojson` in content. It is kept because
`load_pfz_live_geojson()` still chooses between the two on `valid_for`, which is
the R-INDIA-3 staleness guard.

    python backend/scripts/build_all_india_pfz.py
    python backend/scripts/build_all_india_pfz.py --self-check   # no file writes
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "incois_osf_pfz" / "pfz"
LIVE_FILE = DATA_DIR / "incois_pfz_live_advisories.geojson"
OUT_FILE = DATA_DIR / "all_india_pfz_advisories.geojson"


def _newest_valid_for(features: list[dict]) -> str:
    return max((f.get("properties", {}).get("valid_for") or "" for f in features), default="")


def build(features: list[dict]) -> list[dict]:
    """Keep only the features from the newest advisory day present.

    INCOIS reissues PFZ advisories daily and an advisory is a location for
    *that* day, so a mixed-date collection cannot be served as one answer: the
    map draws every point identically and the older ones would read as current.
    """
    newest = _newest_valid_for(features)
    return [f for f in features if (f.get("properties", {}).get("valid_for") or "") == newest]


def generate() -> None:
    with open(LIVE_FILE, encoding="utf-8") as f:
        live = json.load(f)

    features = build(list(live.get("features", [])))
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=1)

    sectors = Counter(f.get("properties", {}).get("sector_id") for f in features)
    print(f"Wrote {len(features)} advisories valid_for {_newest_valid_for(features) or '?'} "
          f"across {len(sectors)} sector(s) -> {OUT_FILE}")
    for sec, n in sorted(sectors.items(), key=lambda kv: kv[0] or ""):
        print(f"  {sec}: {n}")
    print("Sectors INCOIS did not publish today are reported by sector_status() as a "
          "data gap with INCOIS's own message — they are not filled in here.")


def _self_check() -> None:
    mixed = [
        {"properties": {"valid_for": "2026-09-19", "sector_id": "SEC005"}},
        {"properties": {"valid_for": "2026-09-02", "sector_id": "SEC001"}},
        {"properties": {}},
    ]
    kept = build(mixed)
    # The whole point: a sector that only has old features drops out entirely
    # rather than being served as today's advice.
    assert len(kept) == 1, kept
    assert kept[0]["properties"]["sector_id"] == "SEC005"
    assert build([]) == []
    print("build_all_india_pfz self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        generate()
