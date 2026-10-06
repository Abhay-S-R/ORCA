#!/usr/bin/env python3
"""Master data preparation script for Sea Route Voyage.

Executes all prep steps in dependency order:
  1. prep_land.py                -> data/sea_route/land_india.geojson
  2. prep_ports.py               -> data/sea_route/ports.geojson
  3. prep_maritime_boundaries.py -> data/sea_route/restricted_areas.geojson
  4. prep_eez.py                 -> data/sea_route/india_eez.geojson
  5. prep_protected.py           -> data/sea_route/protected_areas.geojson
  6. prep_fishing_zones.py       -> data/sea_route/fishing_zones.geojson
  7. validate_sea_route_data.py  -> prints validation report

USAGE
  python scripts/prep_all.py
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_all")

SCRIPTS = [
    "scripts/prep_land.py",
    "scripts/prep_ports.py",
    "scripts/prep_maritime_boundaries.py",
    "scripts/prep_eez.py",
    "scripts/prep_protected.py",
    "scripts/prep_fishing_zones.py",
    "scripts/validate_sea_route_data.py",
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    log.info("Starting master sea-route data preparation...")

    for script_rel in SCRIPTS:
        script_path = root / script_rel
        if not script_path.exists():
            log.warning("Script %s does not exist, skipping.", script_rel)
            continue
        log.info("--------------------------------------------------")
        log.info("Running %s ...", script_rel)
        res = subprocess.run([sys.executable, str(script_path)], cwd=str(root))
        if res.returncode != 0:
            log.error("Script %s failed with code %d", script_rel, res.returncode)
            sys.exit(res.returncode)

    log.info("==================================================")
    log.info("All sea-route datasets prepared and validated successfully.")


if __name__ == "__main__":
    main()
