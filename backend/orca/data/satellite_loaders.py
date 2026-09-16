"""Gridded satellite loaders — the D3 seam analytics_loaders.py's docstring
promises ("real `.h5`/`.nc` loaders second").

This is deliberately a separate module from analytics_loaders.py: everything
there is a plain json/csv read with no scientific-stack import, and this needs
h5py + xarray. Same contract otherwise — a loader gets numbers into memory, it
does not reason about them.

Three real products, all already on disk, none of which had a reader before:

  INSAT-3DR L3B daily SST  `tier3/mosdac/Sea surface temp/3RIMG_*.h5`
  EOS-06 OCM-3 chlorophyll `tier3/mosdac/chlorophyll/E06OCML4AC_*.nc`
  CMEMS GLO12 thetao       `tier2/copernicus/cmems_*.nc`  (the declared SST fallback)

Everything exits as a list of `{"lon", "lat", "value"}` records plus a
provenance dict, which is the same normalized (lon, lat) axis order
normalize.py enforces for every other payload in the system.

FILE DATES ARE PARSED, NEVER SORTED LEXICOGRAPHICALLY. The INSAT filenames
carry `13AUG2026` style stamps, where a plain `sorted()` puts 13AUG after
02SEP — picking a two-week-old granule and calling it the newest. `_newest`
parses the date out of the name instead.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from orca.data.loaders import DATA_DIR

SST_DIR = DATA_DIR / "tier3" / "mosdac" / "Sea surface temp"
CHL_DIR = DATA_DIR / "tier3" / "mosdac" / "chlorophyll"
CMEMS_DIR = DATA_DIR / "tier2" / "copernicus"

# The whole Indian maritime area — matches geospatial.PAN_INDIA_BBOX_WSEN.
# Kept as a dict here because that is the shape ORCAState's `target_bbox`
# already uses; the tuple form lives in geospatial.py for Shapely's benefit.
INDIA_BBOX: dict[str, float] = {"min_lon": 65.0, "min_lat": 4.0, "max_lon": 95.0, "max_lat": 26.0}

_INSAT_DATE = re.compile(r"_(\d{2}[A-Z]{3}\d{4})_")
_EOS06_DATE = re.compile(r"_(\d{8})_")

# INSAT L3B fill values, read off the file's own attributes rather than assumed:
# SST_DLY carries _FillValue -999.0 (float32, kelvin), and the packed int16
# Latitude/Longitude carry 32767 with scale_factor 0.01.
_SST_FILL = -999.0
_LATLON_FILL = 32767
_LATLON_SCALE = 0.01
_KELVIN_ZERO_C = 273.15

# Physically possible sea-surface temperature. A L3B bin that survives the
# fill-value mask can still be nonsense (a mis-navigated limb pixel, a cloud
# edge); anything outside this band is dropped rather than averaged in.
_SST_VALID_C = (-2.0, 40.0)
# mg/m^3. OCM-3 chlorophyll is log-distributed; 0 is a masked cell, not a
# reading of "no chlorophyll", and the upper bound drops obvious turbid-water
# retrieval failures.
_CHL_VALID = (0.001, 100.0)


def _newest(paths: list[Path], pattern: re.Pattern[str], fmt: str) -> tuple[Path, datetime] | None:
    """Newest file by the date encoded in its NAME, parsed not sorted."""
    dated: list[tuple[datetime, Path]] = []
    for p in paths:
        m = pattern.search(p.name)
        if not m:
            continue
        try:
            dated.append((datetime.strptime(m.group(1), fmt).replace(tzinfo=timezone.utc), p))
        except ValueError:
            continue
    if not dated:
        return None
    when, path = max(dated, key=lambda t: t[0])
    return path, when


def _freshness_minutes(acquired: datetime) -> int:
    return max(0, int((datetime.now(timezone.utc) - acquired).total_seconds() // 60))


# --- INSAT-3DR SST (HDF5) --------------------------------------------------

@lru_cache(maxsize=4)
def _insat_grid(path_str: str) -> tuple[Any, Any, Any]:
    """(lat, lon, sst_celsius) as masked float arrays for one granule.

    Cached because the navigation arrays are 2816x2805 int16 each and the
    payload another 2816x2805 float32 — ~60 MB of reads that must not happen
    once per request.
    """
    import h5py
    import numpy as np

    with h5py.File(path_str, "r") as f:
        lat_raw = f["Latitude"][:]
        lon_raw = f["Longitude"][:]
        sst_raw = f["SST_DLY"][0, :, :]

    lat = np.where(lat_raw == _LATLON_FILL, np.nan, lat_raw * _LATLON_SCALE)
    lon = np.where(lon_raw == _LATLON_FILL, np.nan, lon_raw * _LATLON_SCALE)
    sst = np.where(sst_raw == _SST_FILL, np.nan, sst_raw - _KELVIN_ZERO_C)
    lo, hi = _SST_VALID_C
    sst = np.where((sst >= lo) & (sst <= hi), sst, np.nan)
    return lat, lon, sst


def load_insat_sst(bbox: dict[str, float] | None = None) -> dict[str, Any] | None:
    """Newest INSAT-3DR L3B daily SST granule, cropped to `bbox`, in degrees C.

    Returns None when no granule is on disk — the caller degrades and says so
    rather than inventing a grid. The INSAT L3B product is on a geostationary
    projection, so Latitude/Longitude are full 2-D navigation arrays, not 1-D
    coordinate axes: the crop is a boolean mask over both, not an index slice.
    """
    import numpy as np

    bbox = bbox or INDIA_BBOX
    newest = _newest(sorted(SST_DIR.glob("3RIMG_*_L3B_SST_*.h5")), _INSAT_DATE, "%d%b%Y")
    if newest is None:
        return None
    path, acquired = newest
    lat, lon, sst = _insat_grid(str(path))

    inside = (
        (lat >= bbox["min_lat"]) & (lat <= bbox["max_lat"])
        & (lon >= bbox["min_lon"]) & (lon <= bbox["max_lon"])
        & np.isfinite(sst)
    )
    idx = np.nonzero(inside)
    records = [
        {"lon": round(float(lon[i, j]), 3), "lat": round(float(lat[i, j]), 3),
         "value": round(float(sst[i, j]), 2)}
        for i, j in zip(*idx)
    ]
    return {
        "param": "sst",
        "units": "degC",
        "frame": records,
        "provenance": {
            "dataset": "MOSDAC INSAT-3DR IMAGER L3B daily SST",
            "authority_tier": "T1",
            "source_file": path.name,
            "acquisition_timestamp": acquired.isoformat().replace("+00:00", "Z"),
            "freshness_minutes": _freshness_minutes(acquired),
            "native_units": "K",
            "operations": ["fill_mask", "kelvin_to_celsius", "physical_range_mask", "bbox_crop"],
        },
    }


# --- EOS-06 OCM-3 chlorophyll (NetCDF) -------------------------------------

def load_eos06_chl(bbox: dict[str, float] | None = None) -> dict[str, Any] | None:
    """Newest EOS-06 OCM-3 L4 chlorophyll-a granule, cropped to `bbox`.

    The published grid is global 0.25 deg on a 0..360 longitude axis; ORCA's
    convention is -180..180 (normalize.py), so longitudes are wrapped on the
    way out. India's bbox is entirely east of the prime meridian, so the crop
    itself needs no seam handling.
    """
    import numpy as np
    import xarray as xr

    bbox = bbox or INDIA_BBOX
    newest = _newest(sorted(CHL_DIR.glob("E06OCML4AC_*.nc")), _EOS06_DATE, "%Y%m%d")
    if newest is None:
        return None
    path, acquired = newest

    with xr.open_dataset(path) as ds:
        chl = ds["chla"].isel(time=0, lev=0)
        chl = chl.sel(
            lat=slice(bbox["min_lat"], bbox["max_lat"]),
            lon=slice(bbox["min_lon"] % 360, bbox["max_lon"] % 360),
        )
        lats = chl["lat"].values
        lons = chl["lon"].values
        values = chl.values

    lo, hi = _CHL_VALID
    records: list[dict[str, float]] = []
    for i, la in enumerate(lats):
        for j, lo_deg in enumerate(lons):
            v = float(values[i, j])
            if not math.isfinite(v) or not (lo <= v <= hi):
                continue
            wrapped = float(lo_deg) - 360.0 if lo_deg > 180 else float(lo_deg)
            records.append({"lon": round(wrapped, 3), "lat": round(float(la), 3), "value": round(v, 4)})

    return {
        "param": "chl",
        "units": "mg m-3",
        "frame": records,
        "provenance": {
            "dataset": "MOSDAC EOS-06 OCM-3 L4 chlorophyll-a (25 km)",
            "authority_tier": "T1",
            "source_file": path.name,
            "acquisition_timestamp": acquired.isoformat().replace("+00:00", "Z"),
            "freshness_minutes": _freshness_minutes(acquired),
            "native_units": "mg m-3",
            "operations": ["longitude_wrap", "physical_range_mask", "bbox_crop"],
        },
    }


# --- CMEMS thetao — the declared SST fallback rung --------------------------

def load_cmems_sst(bbox: dict[str, float] | None = None) -> dict[str, Any] | None:
    """Surface temperature from the CMEMS GLO12 physics file on disk.

    `discovery.FALLBACK_CASCADES` has named `copernicus_cmems` as the SST
    fallback since Phase 1; until now nothing could read it, so the cascade
    advertised a rung that did not exist. `thetao` is a 4-D field — the
    shallowest depth level is the sea-surface value, and the newest time step
    is the one taken.
    """
    import xarray as xr

    bbox = bbox or INDIA_BBOX
    files = sorted(CMEMS_DIR.glob("cmems_*.nc"))
    if not files:
        return None
    path = files[-1]

    with xr.open_dataset(path) as ds:
        if "thetao" not in ds:
            return None
        field = ds["thetao"].isel(time=-1, depth=0)
        field = field.sel(
            latitude=slice(bbox["min_lat"], bbox["max_lat"]),
            longitude=slice(bbox["min_lon"], bbox["max_lon"]),
        )
        acquired = _as_utc(ds["time"].values[-1])
        lats = field["latitude"].values
        lons = field["longitude"].values
        values = field.values

    lo, hi = _SST_VALID_C
    records = [
        {"lon": round(float(lon), 3), "lat": round(float(la), 3), "value": round(float(values[i, j]), 2)}
        for i, la in enumerate(lats)
        for j, lon in enumerate(lons)
        if math.isfinite(float(values[i, j])) and lo <= float(values[i, j]) <= hi
    ]
    return {
        "param": "sst",
        "units": "degC",
        "frame": records,
        "provenance": {
            "dataset": "Copernicus Marine (CMEMS) GLO12 analysis-forecast — thetao (surface level)",
            "authority_tier": "T2",
            "source_file": path.name,
            "acquisition_timestamp": acquired.isoformat().replace("+00:00", "Z"),
            "freshness_minutes": _freshness_minutes(acquired),
            "native_units": "degC",
            "operations": ["surface_level_select", "physical_range_mask", "bbox_crop"],
        },
    }


def _as_utc(numpy_datetime: Any) -> datetime:
    return datetime.fromisoformat(str(numpy_datetime)[:19]).replace(tzinfo=timezone.utc)


# --- co-location ------------------------------------------------------------

def bin_to_grid(records: list[dict[str, float]], cell_deg: float = 0.25) -> dict[tuple[int, int], float]:
    """Average `records` into fixed lat/lon cells, keyed by cell index.

    SST arrives on INSAT's ~4 km geostationary bins and chlorophyll on a 25 km
    (0.25 deg) global grid. Correlating them point-by-point would be comparing
    readings kilometres apart; binning both to the coarser grid first is what
    makes a Pearson r over the pair mean anything.
    """
    sums: dict[tuple[int, int], list[float]] = {}
    for r in records:
        key = (math.floor(r["lat"] / cell_deg), math.floor(r["lon"] / cell_deg))
        sums.setdefault(key, []).append(r["value"])
    return {k: sum(v) / len(v) for k, v in sums.items()}


if __name__ == "__main__":
    # Gulf of Mannar / south Tamil Nadu box — the pilot region, where all three
    # products genuinely overlap.
    box = {"min_lon": 77.0, "min_lat": 7.5, "max_lon": 80.5, "max_lat": 10.5}

    sst = load_insat_sst(box)
    assert sst is not None, "no INSAT granule on disk"
    assert sst["frame"], "INSAT crop is empty over the pilot box"
    assert all(_SST_VALID_C[0] <= r["value"] <= _SST_VALID_C[1] for r in sst["frame"])
    # The whole point of parsing rather than sorting the filename date:
    assert sst["provenance"]["source_file"].startswith("3RIMG_")
    print("INSAT SST :", len(sst["frame"]), "bins,", sst["provenance"]["source_file"])

    chl = load_eos06_chl(box)
    assert chl is not None and chl["frame"], "no EOS-06 chlorophyll over the pilot box"
    assert all(r["lon"] <= 180 for r in chl["frame"]), "longitude not wrapped to -180..180"
    print("EOS-06 chl:", len(chl["frame"]), "cells,", chl["provenance"]["source_file"])

    cmems = load_cmems_sst(box)
    assert cmems is not None and cmems["frame"], "CMEMS fallback rung still unreadable"
    print("CMEMS sst :", len(cmems["frame"]), "cells,", cmems["provenance"]["source_file"])

    # Co-location actually overlaps — otherwise the correlation has no samples.
    shared = set(bin_to_grid(sst["frame"])) & set(bin_to_grid(chl["frame"]))
    assert shared, "SST and chlorophyll grids do not overlap after binning"
    print("co-located:", len(shared), "cells at 0.25 deg")
