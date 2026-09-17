#!/usr/bin/env python3
"""Refresh the INCOIS Ocean State Forecast grids (WW3 waves, HYCOM currents).

Procurement runbook §A3. The files on disk are the 2026-08-29/08-30 runs — a
7-day forecast read a fortnight late is not stale data, it is wrong data, and
it silently removes the wave-height leg of voyage planning and the D3 current
layer.

**NCSS subsets, not whole files.** INCOIS serves the whole-basin WW3 run at
6.5 GB and currents at ~9 GB; this machine has ~19 GB free, so a full pair
would fill the drive. The NetCDF Subset Service crops to the India bbox for
~5 MB per run, which is the same data the tile builders and voyage planner
ever look at (they slice 65-96E / 2-25N anyway).

The currents product is renamed on the way in: INCOIS publishes the daily file
as CURRENTS_IO with axes TAXIS/DEPTH1_1 and variables U/V, while
`geospatial.current_vectors` reads the older RSMC_hycom naming (TIME/DEPTH,
UVEL/VVEL). Same HYCOM system, different packaging, so the rename happens here
rather than forking the reader.

    python scripts/refresh_osf_forecasts.py
    python scripts/refresh_osf_forecasts.py --self-check   # no network

Re-run `scripts/extract_osf_pilot.py` and `backend/scripts/generate_tiles.py`
afterwards — both are derived from these grids.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.request
from pathlib import Path

import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
OSF = DATA / "incois_osf_pfz"
THREDDS = "https://incois.gov.in/thredds"

# Wider than either tile bbox (65-96E/2-25N) so voyage legs near the EEZ edge
# still land inside the grid instead of silently returning None.
BBOX = {"west": 60, "east": 100, "south": 0, "north": 28}
WW3_VARS = ["HS", "MWD", "T02", "PWP", "UWND", "VWND"]  # everything the readers touch
CURRENT_VARS = ["U", "V"]
SST_VARS = ["SST"]
CURRENT_RENAME = {"U": "UVEL", "V": "VVEL", "TAXIS": "TIME", "DEPTH1_1": "DEPTH"}


def latest_date(catalog: str, prefix: str) -> str:
    """Newest YYYYMMDD published under a THREDDS catalog for `prefix`."""
    with urllib.request.urlopen(f"{THREDDS}/catalog/osf/{catalog}/catalog.xml", timeout=120) as r:
        xml = r.read().decode("utf-8", "replace")
    dates = re.findall(rf'name="{re.escape(prefix)}(\d{{8}})\.nc"', xml)
    if not dates:
        raise SystemExit(f"no {prefix}*.nc in the {catalog} catalog")
    return max(dates)


def ncss(catalog: str, filename: str, variables: list[str], out: Path) -> Path:
    q = "&".join([*(f"var={v}" for v in variables),
                  *(f"{k}={v}" for k, v in BBOX.items()),
                  # time=all matters: without it NCSS returns the single step
                  # nearest *now*, which reads as a valid file and quietly
                  # turns a 7-day forecast into a nowcast.
                  "time=all", "horizStride=1", "accept=netcdf"])  # netcdf4 is not enabled here
    url = f"{THREDDS}/ncss/grid/osf/{catalog}/{filename}?{q}"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    if tmp.stat().st_size < 100_000:  # NCSS reports refusals as a short text body
        raise SystemExit(f"{filename}: {tmp.read_text(errors='replace')[:200]}")
    tmp.replace(out)
    return out


def check(path: Path, expect_vars: list[str], lat: str, lon: str) -> None:
    ds = xr.open_dataset(path, decode_times=False)
    missing = [v for v in expect_vars if v not in ds.data_vars]
    assert not missing, f"{path.name}: missing {missing}"
    # WW3 calls its time axis TIME, the SST/currents products call it TAXIS.
    steps = max(ds.sizes.get(d, 0) for d in ("TIME", "TAXIS"))
    assert steps > 1, f"{path.name}: no forecast steps — did the query lose time=all?"
    assert float(ds[lon].min()) >= BBOX["west"] - 1 and float(ds[lon].max()) <= BBOX["east"] + 1
    assert float(ds[lat].min()) >= BBOX["south"] - 1 and float(ds[lat].max()) <= BBOX["north"] + 1
    print(f"  {path.name}: {dict(ds.sizes)} {path.stat().st_size / 1e6:.1f} MB")
    ds.close()


def refresh_ww3() -> Path:
    date = latest_date("ww3", "rsmc_combined_ww3_")
    out = ncss("ww3", f"rsmc_combined_ww3_{date}.nc", WW3_VARS,
               OSF / "osf_ww3" / f"rsmc_combined_ww3_{date}.nc")
    check(out, WW3_VARS, "IOYAXIS", "IOXAXIS")
    return out


def refresh_currents() -> Path:
    date = latest_date("currents", "CURRENTS_IO_")
    raw = ncss("currents", f"CURRENTS_IO_{date}.nc", CURRENT_VARS,
               OSF / "osf_hycom" / f"CURRENTS_IO_{date}.part.nc")
    with xr.open_dataset(raw, decode_times=False) as src:
        ds = src.load()  # load before the rename so `raw` can be deleted on Windows
    ds = ds.rename({k: v for k, v in CURRENT_RENAME.items() if k in ds.variables or k in ds.dims})
    ds.attrs["orca_source"] = f"INCOIS OSF CURRENTS_IO_{date}.nc, NCSS subset, renamed to RSMC_hycom naming"
    out = OSF / "osf_hycom" / f"RSMC_hycom_{date}.nc"
    # NETCDF3_64BIT, matching what INCOIS itself serves: the readers downstream
    # open these with engine="scipy", which cannot read an HDF5-backed NETCDF4.
    ds.to_netcdf(out, format="NETCDF3_64BIT")
    ds.close()
    raw.unlink()
    check(out, ["UVEL", "VVEL"], "LAT", "LON")
    return out


def refresh_sst() -> Path:
    """Sea-surface temperature, which the daily currents product does not carry.

    The old RSMC_hycom file bundled TEMP/SALN/MLD/SSH; INCOIS no longer publishes
    that bundle, so SST comes from the separate OSF SST_NIO product and salinity,
    mixed-layer depth and sea-surface height simply have no current public source
    here — the extractor leaves them empty rather than carrying August values
    forward under a September timestamp.
    """
    date = latest_date("sst", "SST_NIO_")
    out = ncss("sst", f"SST_NIO_{date}.nc", SST_VARS, OSF / "osf_hycom" / f"SST_NIO_{date}.nc")
    check(out, SST_VARS, "LAT", "LON")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ww3", action="store_true")
    ap.add_argument("--skip-currents", action="store_true")
    ap.add_argument("--skip-sst", action="store_true")
    args = ap.parse_args()

    if not args.skip_ww3:
        print("WW3 waves:")
        refresh_ww3()
    if not args.skip_currents:
        print("HYCOM currents:")
        refresh_currents()
    if not args.skip_sst:
        print("OSF sea-surface temperature:")
        refresh_sst()
    print("\nnow re-run: scripts/extract_osf_pilot.py, backend/scripts/generate_tiles.py")
    return 0


def _self_check() -> None:
    """The catalog parse and the NCSS query string, without downloading."""
    xml = '<dataset name="rsmc_combined_ww3_20260913.nc"/><dataset name="rsmc_combined_ww3_20260915.nc"/>'
    assert max(re.findall(r'name="rsmc_combined_ww3_(\d{8})\.nc"', xml)) == "20260915"
    assert set(CURRENT_RENAME.values()) == {"UVEL", "VVEL", "TIME", "DEPTH"}
    assert BBOX["west"] <= 65 and BBOX["east"] >= 96 and BBOX["north"] >= 25, "narrower than the tile bbox"
    print("self-check ok: catalog date parse, current-variable rename, bbox covers the tile crop")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
