"""scripts/refresh_all.py — P5.12: the one pre-demo command.

Eleven-plus refresh/scrape scripts used to be run manually, in no particular
order, with no record of whether any of them actually worked. This runs all
of them, then rebuilds the derived artefacts that read what they wrote
(national PFZ layer, the cloud-cover PFZ fallback, the MPA geofence, the
raster tile pyramid), and writes `data/refresh_manifest.json` recording
`ok`/`last_refresh_utc`/`content_valid_for`/`row_count` per dataset.

A failing step is *recorded*, never fatal — every other step still runs, and
a stale or broken dataset shows up in the manifest (and in `/data`, which
P5.13 wires to read this same file) instead of silently blocking the rest.

Usage (from the repo root, with backend/.venv active — every fetch script
and the tile builders both need its dependencies):
    python scripts/refresh_all.py
    python scripts/refresh_all.py --only tide_tables --only pfz_advisories
    python scripts/refresh_all.py --skip mosdac --skip cmems

Schedule on the demo laptop with Windows Task Scheduler (`data/` is
gitignored, so CI cannot persist a refresh) — see
docs/plans/DLC_implementation_plan.md P5.12.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "data" / "refresh_manifest.json"
_STEP_TIMEOUT_S = 900

# Network fetch/scrape first — independent of each other except that the PFZ
# scrape must land before the national-PFZ derived step below reads it.
_FETCH_STEPS: list[tuple[str, Path]] = [
    ("open_meteo_caches", REPO_ROOT / "scripts" / "refresh_openmeteo_caches.py"),
    ("era5_baselines", REPO_ROOT / "scripts" / "refresh_era5_baselines.py"),
    ("tide_tables", REPO_ROOT / "scripts" / "refresh_tide_tables.py"),
    ("fishing_ban_order", REPO_ROOT / "scripts" / "refresh_fishing_ban_order.py"),
    ("osf_forecasts", REPO_ROOT / "scripts" / "refresh_osf_forecasts.py"),
    ("pfz_advisories", REPO_ROOT / "scripts" / "scrape_pfz_advisories.py"),
    ("icg_sar_stations", REPO_ROOT / "scripts" / "scrape_icg_sar_stations.py"),
    ("bhuvan_manifest", REPO_ROOT / "scripts" / "refresh_bhuvan_manifest.py"),
    ("cmems", REPO_ROOT / "scripts" / "refresh_cmems.py"),
    ("gfw_ais", REPO_ROOT / "scripts" / "refresh_gfw_ais.py"),
    ("nasa_ocean_color", REPO_ROOT / "scripts" / "refresh_nasa_ocean_color.py"),
    ("mosdac", REPO_ROOT / "scripts" / "refresh_mosdac.py"),
]

# Then the derived artefacts that read what the fetch phase just wrote.
# `generate_pan_india_waves.py` is deliberately excluded: it targets one
# hardcoded WW3 filename (`rsmc_combined_ww3_20260829.nc`) rather than the
# newest file on disk the way `generate_tiles.py`'s own wave-tile step
# already does, so it is a stale one-off, not a repeatable refresh step.
_DERIVED_STEPS: list[tuple[str, Path]] = [
    ("national_pfz_build", REPO_ROOT / "backend" / "scripts" / "build_all_india_pfz.py"),
    ("pfz_fallback_build", REPO_ROOT / "scripts" / "build_pfz_fallback.py"),
    ("mpa_geofence_build", REPO_ROOT / "scripts" / "build_mpa_geofence.py"),
    ("tile_pyramid_build", REPO_ROOT / "backend" / "scripts" / "generate_tiles.py"),
]

# ponytail: each script prints its own free-text summary rather than a shared
# machine schema — twelve scripts, twelve formats — so row_count/content_valid_for
# are a best-effort last-match over two common shapes, not a real per-script
# parser. Neither matching leaves both fields None rather than a guess; `ok` and
# `log_tail` are always real. Upgrade path: have each script print one final
# `MANIFEST: {...}` JSON line and parse only that, if per-dataset drilldown
# in `/data` (P5.13) turns out to need more precision than this gives.
_ROW_COUNT_RE = re.compile(r"(\d[\d,]*)\s*(?:refreshed|downloaded|written|granules?|vessels?|stations?|cached|fetched|located)", re.IGNORECASE)
_WINDOW_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\D{1,6}(\d{4}-\d{2}-\d{2})")


def _best_effort_summary(output: str) -> tuple[int | None, str | None]:
    row_count = None
    for m in _ROW_COUNT_RE.finditer(output):
        row_count = int(m.group(1).replace(",", ""))
    valid_for = None
    for m in _WINDOW_RE.finditer(output):
        valid_for = f"{m.group(1)} to {m.group(2)}"
    return row_count, valid_for


def _run_step(script: Path) -> dict:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not script.exists():
        return {"ok": False, "last_refresh_utc": now, "content_valid_for": None,
                "row_count": None, "error": f"script not found: {script}", "log_tail": ""}
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)], cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=_STEP_TIMEOUT_S,
            check=False,  # a failed step is recorded below, never raised
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        ok = False
        output += f"\n[TIMEOUT after {_STEP_TIMEOUT_S}s]"
    row_count, valid_for = _best_effort_summary(output)
    print(f"[{'ok  ' if ok else 'FAIL'}] {script.stem} ({time.monotonic() - started:.1f}s)")
    return {
        "ok": ok,
        "last_refresh_utc": now,
        "content_valid_for": valid_for,
        "row_count": row_count,
        "error": None if ok else output[-2000:],
        "log_tail": output[-2000:],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", action="append", default=[], metavar="NAME", help="dataset name(s) to skip")
    ap.add_argument("--only", action="append", default=None, metavar="NAME", help="run only these dataset name(s)")
    args = ap.parse_args()

    manifest: dict[str, dict] = {}
    for phase_name, steps in (("fetch", _FETCH_STEPS), ("derived", _DERIVED_STEPS)):
        print(f"\n=== {phase_name} ===")
        for name, script in steps:
            if name in args.skip or (args.only and name not in args.only):
                continue
            manifest[name] = _run_step(script)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ok_count = sum(1 for v in manifest.values() if v["ok"])
    print(f"\n{ok_count}/{len(manifest)} datasets refreshed ok -> {MANIFEST_PATH}")
    for name, entry in manifest.items():
        if not entry["ok"]:
            print(f"  FAILED: {name} — {(entry['error'] or '').strip().splitlines()[-1:] or 'see log_tail'}")
    return 0  # failures are recorded in the manifest; this command itself never fails


if __name__ == "__main__":
    sys.exit(main())
