#!/usr/bin/env python
"""Refresh the Copernicus Marine (CMEMS) subsets (`copernicus_cmems`, WEEKLY).

Credentials required — free registration at
https://data.marine.copernicus.eu/register. Put them in the project `.env`:

    COPERNICUS_USERNAME=your_username
    COPERNICUS_PASSWORD=your_password

`_load_credentials()` maps those onto the names the client reads, so the script
is non-interactive and safe to run from a scheduler. The `copernicusmarine`
client is already in backend/requirements.txt, so nothing needs installing.

Why this script exists: the CMEMS directory currently holds a 2023 chlorophyll
granule and 2024-11 -> 2025-04 SSH alongside current thetao. The freshness
catalogue reports the *newest* date per source (contract §7), so that stale pair
is invisible on `/data` — the only way to know is to look, which is what made
this the sneakiest of the breaches.

Usage: python scripts/refresh_cmems.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "tier2" / "copernicus"

# Pan-India maritime bounds, same box as the OSF/tile pipeline.
WEST, EAST, SOUTH, NORTH = 65.0, 96.0, 2.0, 25.0

# (dataset_id, variables, output filename, needs a depth slice)
PRODUCTS: tuple[tuple[str, list[str], str, bool], ...] = (
    ("cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
     ["CHL"], "cmems_chl_india_nrt.nc", False),
    # 0.125deg, not the 0.25deg stream: CMEMS froze `...duacs-0.25deg_P1D` at
    # 2024-11-25 and moved the live feed to the finer grid. The 2024-11 -> 2025-04
    # SSH sitting in data/tier2/copernicus/ is exactly that retirement, not a
    # missed download — the old id cannot be refreshed by anyone.
    ("cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D",
     ["adt", "sla"], "cmems_ssh_india_nrt.nc", False),
    ("cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
     ["thetao"], "cmems_thetao_india_nrt.nc", True),
)


def _load_credentials() -> bool:
    """Take the login out of the project `.env` and hand it to the client under the
    names it actually reads. ORCA stores these as COPERNICUS_USERNAME/_PASSWORD, the
    client wants COPERNICUSMARINE_SERVICE_USERNAME/_PASSWORD — without the mapping the
    script prompts for a login on a terminal that may not be attached to anyone."""
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    user = os.environ.get("COPERNICUS_USERNAME", "").strip()
    pw = os.environ.get("COPERNICUS_PASSWORD", "").strip()
    if not (user and pw):
        return bool(os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"))
    os.environ.setdefault("COPERNICUSMARINE_SERVICE_USERNAME", user)
    os.environ.setdefault("COPERNICUSMARINE_SERVICE_PASSWORD", pw)
    return True


def main() -> int:
    # Credentials first: copernicusmarine reads its env vars once, at import time.
    if not _load_credentials():
        print("[ERROR] No Copernicus credentials. Add COPERNICUS_USERNAME and "
              "COPERNICUS_PASSWORD to .env (register free at "
              "https://data.marine.copernicus.eu/register).")
        return 1

    try:
        import copernicusmarine
    except ImportError:
        print("[ERROR] copernicusmarine not installed. Run: pip install -r backend/requirements.txt")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # A short trailing window rather than "today": NRT products publish with a
    # one-to-three day latency, so asking for today alone reliably returns empty.
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=7)

    failures = 0
    for dataset_id, variables, filename, has_depth in PRODUCTS:
        print(f"[*] {filename} <- {dataset_id}")
        kwargs: dict[str, object] = {
            "dataset_id": dataset_id,
            "variables": variables,
            "minimum_longitude": WEST, "maximum_longitude": EAST,
            "minimum_latitude": SOUTH, "maximum_latitude": NORTH,
            "start_datetime": f"{start}T00:00:00",
            "end_datetime": f"{end}T23:59:59",
            "output_directory": str(OUT_DIR),
            "output_filename": filename,
            "overwrite": True,
        }
        if has_depth:
            kwargs.update(minimum_depth=0.49, maximum_depth=1.0)  # surface layer only
        try:
            copernicusmarine.subset(**kwargs)  # type: ignore[arg-type]
            print(f"    OK -> {OUT_DIR / filename}")
        except Exception as exc:  # noqa: BLE001 — one dead product must not stop the rest
            failures += 1
            msg = str(exc)
            print(f"    [FAIL] {msg[:300]}")
            if "credential" in msg.lower() or "401" in msg or "unauthor" in msg.lower():
                print("    -> Auth failure. Check COPERNICUS_USERNAME / COPERNICUS_PASSWORD in .env.")
            elif "exceed the dataset coordinates" in msg:
                # The window we asked for is newer than anything the dataset has:
                # CMEMS retired the stream and published a replacement id.
                print("    -> This stream has stopped publishing. Find its replacement with "
                      "`copernicusmarine describe --contains <product>` and update PRODUCTS.")

    stale = [p for p in (OUT_DIR / "cmems_chl_india_nrt.nc",) if not p.exists()]
    print(f"\n{len(PRODUCTS) - failures}/{len(PRODUCTS)} products refreshed"
          + (f"; missing: {[p.name for p in stale]}" if stale else ""))
    print("Delete any superseded files by hand — a stale granule left in this "
          "directory is hidden by the newest-date rule (contract §7).")
    return 1 if failures == len(PRODUCTS) else 0


if __name__ == "__main__":
    sys.exit(main())
