"""Prune stale data files that accumulate across daily/weekly refreshes.

Every refresh script writes date-stamped files (e.g. rsmc_combined_ww3_20261019.nc)
and the agents only ever read the newest one. Without pruning, a month of daily
refreshes grows data/ from ~2 GB to 7+ GB — which fills the EC2 30 GB disk and
wastes local space alike.

This script keeps the N newest *complete* files per product and deletes the rest,
including orphaned .part files from interrupted downloads.

    python scripts/cleanup_stale_data.py                # dry run (default)
    python scripts/cleanup_stale_data.py --apply        # actually delete
    python scripts/cleanup_stale_data.py --keep 3       # keep 3 instead of 2

Works identically on Windows (local dev) and Linux (EC2 Docker container).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")

# (directory relative to DATA, glob pattern for complete files, description)
# The glob must match the pattern the agents use to find the newest file.
PRODUCTS: tuple[tuple[str, str, str], ...] = (
    # --- INCOIS OSF (daily, ~289 MB each for WW3, ~79 MB for HYCOM, ~40 MB for SST) ---
    ("incois_osf_pfz/osf_ww3", "rsmc_combined_ww3_*.nc", "WW3 wave forecasts"),
    ("incois_osf_pfz/osf_hycom", "RSMC_hycom_*.nc", "HYCOM current forecasts"),
    ("incois_osf_pfz/osf_hycom", "SST_NIO_*.nc", "OSF sea-surface temperature"),
    # --- MOSDAC (daily, ~51.5 MB wind, ~9 MB SST, ~6 MB chlorophyll) ---
    ("tier3/mosdac/Wind", "E06SCTL4AW_*.nc", "EOS-06 scatterometer wind"),
    ("tier3/mosdac/Sea surface temp", "3RIMG_*_L3B_SST_DLY_*.h5", "INSAT-3DR daily SST"),
    ("tier3/mosdac/chlorophyll", "E06OCML4AC_*.nc", "EOS-06 analysed chlorophyll"),
)

# Orphaned partial downloads — always safe to delete if a complete file exists.
PART_GLOBS: tuple[tuple[str, str], ...] = (
    ("incois_osf_pfz/osf_ww3", "*.part"),
    ("incois_osf_pfz/osf_hycom", "*.part*"),
    ("tier3/mosdac/Wind", "*.part"),
    ("tier3/mosdac/Sea surface temp", "*.part"),
    ("tier3/mosdac/chlorophyll", "*.part"),
)


def _human_size(nbytes: int) -> str:
    if nbytes >= 1 << 30:
        return f"{nbytes / (1 << 30):.1f} GB"
    if nbytes >= 1 << 20:
        return f"{nbytes / (1 << 20):.1f} MB"
    return f"{nbytes / (1 << 10):.1f} KB"


def prune(keep: int = 2, apply: bool = False) -> int:
    """Returns total bytes freed (or would-be-freed in dry-run mode)."""
    total_freed = 0
    total_deleted = 0

    for rel_dir, pattern, label in PRODUCTS:
        directory = DATA / rel_dir
        if not directory.is_dir():
            continue

        files = sorted(directory.glob(pattern))
        if len(files) <= keep:
            continue

        to_delete = files[:-keep]  # oldest first; keep the N newest
        freed = sum(f.stat().st_size for f in to_delete)
        total_freed += freed
        total_deleted += len(to_delete)

        action = "DELETING" if apply else "WOULD DELETE"
        print(f"\n[{label}] {directory}")
        print(f"  Found {len(files)} files, keeping newest {keep}, {action} {len(to_delete)} ({_human_size(freed)})")
        for f in to_delete:
            print(f"    - {f.name}  ({_human_size(f.stat().st_size)})")
            if apply:
                f.unlink()

    # Orphaned .part files
    for rel_dir, pattern in PART_GLOBS:
        directory = DATA / rel_dir
        if not directory.is_dir():
            continue
        parts = list(directory.glob(pattern))
        if not parts:
            continue
        freed = sum(f.stat().st_size for f in parts)
        total_freed += freed
        total_deleted += len(parts)
        action = "DELETING" if apply else "WOULD DELETE"
        print(f"\n[Partial downloads] {directory}")
        print(f"  {action} {len(parts)} .part file(s) ({_human_size(freed)})")
        for f in parts:
            print(f"    - {f.name}  ({_human_size(f.stat().st_size)})")
            if apply:
                f.unlink()

    print(f"\n{'=' * 60}")
    if apply:
        print(f"CLEANED: {total_deleted} files, {_human_size(total_freed)} freed")
    else:
        print(f"DRY RUN: {total_deleted} files, {_human_size(total_freed)} would be freed")
        if total_deleted:
            print("Re-run with --apply to actually delete.")
    return total_freed


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prune stale data files, keeping only the N newest per product."
    )
    ap.add_argument("--keep", type=int, default=2,
                    help="Number of newest complete files to retain per product (default: 2)")
    ap.add_argument("--apply", action="store_true",
                    help="Actually delete files. Without this flag, only a dry run is performed.")
    args = ap.parse_args()

    if args.keep < 1:
        print("[ERROR] --keep must be at least 1")
        return 1

    print(f"Data directory: {DATA}")
    print(f"Retention: keep newest {args.keep} file(s) per product")
    print(f"Mode: {'APPLY (files will be deleted)' if args.apply else 'DRY RUN (no changes)'}")
    prune(keep=args.keep, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
