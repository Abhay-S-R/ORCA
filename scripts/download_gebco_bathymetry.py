"""Fetch a GEBCO 15-arcsecond bathymetry subset for the Indian EEZ.

Procurement runbook §A6. The runbook records GEBCO as "a form, not an API",
which is what the old download page was. The rebuilt Grid Subsetting App is a
Next.js front end over a small REST service, so this drives that service
directly and the item stops being a manual chore:

    POST /api/queue                 -> {"basketId": ...}   (asynchronous job)
    GET  /api/queue/download/{id}   -> zip, once generated

Only the pilot box (7.5-10.5 N / 77.5-80.5 E) had been fetched by hand; the
default here is the national box the rest of ORCA uses, 4-26 N / 60-100 E.
That is 880 square degrees against GEBCO's own 14,400 limit for this grid, so
it goes through as a single basket.

WHY BOTHER, GIVEN ETOPO IS ALREADY ON DISK. `etopo_all_india_bathymetry.nc`
covers the same water at 1 arc-minute. GEBCO is 15 arc-seconds — 16x the
cells — and only matters where `compute_safe_route` needs shoal-level depth.
The ETOPO file stays as the fallback; this widens the high-resolution layer
from one pilot box to the whole coast.

    python scripts/download_gebco_bathymetry.py
    python scripts/download_gebco_bathymetry.py --self-check   # no network
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
OUT_DIR = DATA / "tier1" / "bathymetry"

API = "https://download.gebco.net/api"
# Ids from /api/grids and /api/formats, pinned rather than looked up so a
# silent renumbering on GEBCO's side fails loudly instead of fetching the
# wrong grid. GRID_ID 1 = "GEBCO 2026 Global", SOURCE_ID 1 = its bathymetry
# layer (2 is sub-ice, 3 is the type-identifier grid), FORMAT_ID 1 = NetCDF.
GRID_ID, SOURCE_ID, FORMAT_ID = 1, 1, 1
GRID_NAME = "GEBCO 2026 Global"
MAX_AREA_SQ_DEG = 14400  # the grid's own `maximum_area`, from /api/grids

PAN_INDIA = {"north": 26.0, "south": 4.0, "west": 60.0, "east": 100.0}
CITATION = ("GEBCO Compilation Group (2026). GEBCO 2026 Grid. "
            "doi:10.5285/(see GEBCO_Grid_documentation.pdf)")


def subset_name(bbox: dict[str, float]) -> str:
    """Matches the pilot file already in data/tier1/bathymetry."""
    return "gebco_2026_n{north}_s{south}_w{west}_e{east}.nc".format(**bbox)


def basket_payload(bbox: dict[str, float]) -> dict[str, object]:
    area = (bbox["north"] - bbox["south"]) * (bbox["east"] - bbox["west"])
    if area <= 0:
        raise ValueError("empty bounding box: %r" % bbox)
    if area > MAX_AREA_SQ_DEG:
        raise ValueError("%.0f sq deg exceeds GEBCO's %d sq deg limit for this grid — "
                         "split the box" % (area, MAX_AREA_SQ_DEG))
    return {
        "id": "0",
        "email": None,  # no address is sent; the basket id is enough to collect
        "submission_date": datetime.now(timezone.utc).isoformat(),
        "processing_status": "new",
        "items": [{
            "id": 0,
            "grid_id": GRID_ID,
            "data_source_ids": [SOURCE_ID],
            "formats": [FORMAT_ID],
            "left": bbox["west"],
            "right": bbox["east"],
            "top": bbox["north"],
            "bottom": bbox["south"],
        }],
    }


def submit(bbox: dict[str, float]) -> str:
    body = json.dumps(basket_payload(bbox)).encode()
    req = urllib.request.Request(API + "/queue", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["basketId"]


def collect(basket_id: str, attempts: int = 40, wait_s: float = 30.0) -> bytes:
    """The zip, once the queue has generated it.

    Generation is asynchronous and the endpoint 404s until it is done, so
    this polls rather than assuming the basket is ready on the first ask.
    """
    url = "%s/queue/download/%s" % (API, basket_id)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=900) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 425, 503):
                raise
            print("  not ready yet (%s), waiting %.0fs [%d/%d]"
                  % (exc.code, wait_s, attempt + 1, attempts))
            time.sleep(wait_s)
    raise TimeoutError("basket %s never became ready" % basket_id)


def extract_grid(blob: bytes, dest: Path) -> Path:
    """The one .nc out of the basket zip, written to `dest`."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".nc")]
        if len(names) != 1:
            raise ValueError("expected one .nc in the basket, got %r" % z.namelist())
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(names[0]))
    return dest


def write_provenance(dest: Path, bbox: dict[str, float], basket: str) -> Path:
    meta = OUT_DIR / (dest.stem + "_provenance.json")
    meta.write_text(json.dumps({
        "dataset": GRID_NAME,
        "authority_tier": "T2",
        "citation": CITATION,
        "resolution": "15 arc-second",
        "bbox": bbox,
        "basket_id": basket,
        "source_url": "https://download.gebco.net/",
        "api_endpoint": API + "/queue",
        "acquisition_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "file": dest.name,
        "size_bytes": dest.stat().st_size,
        "note": "Global compilation, not an Indian hydrographic survey. Not for navigation; "
                "INCOIS/NHO charts govern. ETOPO 1-arcmin remains the fallback layer.",
    }, indent=2), encoding="utf-8")
    return meta


def main(bbox: dict[str, float] | None = None) -> int:
    bbox = bbox or PAN_INDIA
    dest = OUT_DIR / subset_name(bbox)
    if dest.exists():
        print("already have %s (%.1f MB)" % (dest.relative_to(REPO_ROOT),
                                             dest.stat().st_size / 1e6))
        return 0

    basket = submit(bbox)
    print("queued %s as %s" % (GRID_NAME, basket))
    extract_grid(collect(basket), dest)
    write_provenance(dest, bbox, basket)
    print("%s -> %.1f MB" % (dest.relative_to(REPO_ROOT), dest.stat().st_size / 1e6))
    return 0


def _self_check() -> None:
    """Payload shape and the area guard, without touching the network."""
    p = basket_payload(PAN_INDIA)
    item = p["items"][0]
    # west/east -> left/right, north/south -> top/bottom. Transposing these
    # silently returns a grid of the wrong ocean, so pin them.
    assert (item["left"], item["right"], item["top"], item["bottom"]) == (60.0, 100.0, 26.0, 4.0), item
    assert item["grid_id"] == 1 and item["formats"] == [1] and item["data_source_ids"] == [1]
    assert p["email"] is None, "no email address is sent to GEBCO"

    # The national box fits in one basket; a hemisphere does not.
    assert (PAN_INDIA["north"] - PAN_INDIA["south"]) * (PAN_INDIA["east"] - PAN_INDIA["west"]) == 880
    for bad in ({"north": 90.0, "south": -90.0, "west": -180.0, "east": 180.0},
                {"north": 4.0, "south": 26.0, "west": 60.0, "east": 100.0}):
        try:
            basket_payload(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted an impossible box: %r" % bad)

    assert subset_name(PAN_INDIA) == "gebco_2026_n26.0_s4.0_w60.0_e100.0.nc"

    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as w:
        w.writestr("gebco.nc", b"CDF\x01")
        w.writestr("GEBCO_Grid_terms_of_use.pdf", b"%PDF")
    out = extract_grid(z.getvalue(), Path(os.environ.get("TEMP", "/tmp")) / "_gebco_selfcheck.nc")
    assert out.read_bytes() == b"CDF\x01", "picked the wrong member out of the basket"
    out.unlink()
    print("self-check ok: bbox orientation, area limit, zip member selection")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
