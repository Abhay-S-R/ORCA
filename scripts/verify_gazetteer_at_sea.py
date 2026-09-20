"""Check every gazetteer coordinate is a point a vessel can occupy.

A gazetteer entry that lands on the town rather than the harbour approach reads
`on_land: true` to `/api/depth`, which returns a null seabed and silently
disarms the shallow-water hazard check — the same defect that moved
`DEFAULT_LAT/LON` offshore. `graph.place_guard` discloses it, but a disclosure
is not a depth, so the repair belongs here, in the coordinates.

Reports, and exits non-zero on, any entry GEBCO says is on land. Run it after
touching `loaders._GAZETTEER`:

    python scripts/verify_gazetteer_at_sea.py
    python scripts/verify_gazetteer_at_sea.py --added-only   # just the new harbours
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from orca.agents.geospatial import depth_at_point  # noqa: E402
from orca.data import loaders  # noqa: E402

# The harbours added in the 2026-09-20 all-India pass. Kept as a name list so
# --added-only stays meaningful without a second copy of the coordinates.
ADDED = """
mangrol jakhau diu jafrabad navabandar sutrapada valsad navsari umbergaon mahuva salaya vanakbara
malvan vengurla harnai dabhol shrivardhan murud uran satpati arnala versova
malpe gangolli honnavar belekeri tadri kumta
beypore ponnani munambam vizhinjam neendakara azhikkal thalassery chavakkad
colachel thengapattinam muttom kadiapatnam manapad uvari periyathalai chinnamuttom tharuvaikulam punnakayal
nagore tharangambadi tranquebar poompuhar parangipettai marakkanam pulicat
nizampatnam kalingapatnam bheemunipatnam narsapur antarvedi uppada gangavaram vadarevu suryalanka ramayapatnam
astaranga jatadhari talchua chandbali konark dhamara
shankarpur junput kakdwip namkhana frasergunj "diamond harbour"
mayabunder rangat diglipur hutbay "campbell bay" kamorta
""".split()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--added-only", action="store_true", help="only the 2026-09-20 harbours")
    args = ap.parse_args()

    entries = {k: v for k, v in loaders._GAZETTEER.items() if k.isascii()}
    if args.added_only:
        entries = {k: v for k, v in entries.items() if k.replace(" ", "") in
                   {a.replace(" ", "").strip('"') for a in ADDED}}

    on_land, wet, unknown = [], 0, 0
    for name, (lat, lon) in sorted(entries.items()):
        d = depth_at_point(lat, lon)
        if d.on_land:
            on_land.append((name, lat, lon))
        elif d.depth_m is None:
            unknown += 1
        else:
            wet += 1

    print(f"{len(entries)} entries checked: {wet} at sea, {unknown} no GEBCO coverage, "
          f"{len(on_land)} ON LAND")
    for name, lat, lon in on_land:
        print(f"  ON LAND  {name:22} ({lat}, {lon})")
    return 1 if on_land else 0


if __name__ == "__main__":
    raise SystemExit(main())
