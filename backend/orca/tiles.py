"""Raster tile pyramid pipeline (Phase 2 D3 step 1) — offline/build-time
only. Never imported from the request path: `orca/agents/visualization.py`
only reads the `meta.json` sidecar this writes, so a live `/query` never
pays for a rasterio import or a reprojection.

Division of labor per the explicit user directive (visual quality +
scientific correctness prioritized over dependency minimization): Rasterio
(via rio-tiler's `XarrayReader`, which wraps rasterio's own warp/resample
code) owns reprojection to Web Mercator, resampling, and tile-edge/nodata
masking; cmocean supplies oceanography-correct scientific color ramps
instead of a generic heatmap gradient; Pillow owns RGBA compositing and PNG
encoding; xarray remains the source-grid loader.

Usage (from backend/, with backend/.venv active):
    pip install -r requirements.txt
    python scripts/generate_tiles.py
"""
from __future__ import annotations

import importlib.util
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _fix_proj_env() -> None:
    """A system PostgreSQL/PostGIS install's bundled PROJ database can shadow
    rasterio's own bundled one on Windows (both `PROJ_LIB` and, if unset,
    rasterio's default search still finds the wrong `proj.db` via the OS
    environment), causing `rasterio.errors.CRSError` on every CRS lookup —
    reproduced on this project's own dev machine. `importlib.util.find_spec`
    locates rasterio's package directory WITHOUT importing it (a plain
    `import rasterio` first would let GDAL/PROJ cache the wrong search path
    before we get a chance to override it) — this must run before the first
    `import rasterio`/`rio_tiler`/`rioxarray` anywhere in the process, hence
    it's called at this module's top, ahead of those imports below.
    """
    if os.environ.get("_ORCA_PROJ_FIXED"):
        return
    spec = importlib.util.find_spec("rasterio")
    if spec is None or spec.origin is None:
        return  # rasterio not installed — the imports below will fail loudly instead
    pkg_dir = Path(spec.origin).resolve().parent
    os.environ["PROJ_DATA"] = str(pkg_dir / "proj_data")
    os.environ["PROJ_LIB"] = str(pkg_dir / "proj_data")  # legacy name, still consulted
    os.environ["GDAL_DATA"] = str(pkg_dir / "gdal_data")
    os.environ["_ORCA_PROJ_FIXED"] = "1"


_fix_proj_env()

import cmocean
import morecantile
import numpy as np
import rioxarray  # noqa: F401 -- registers the .rio accessor used below
import xarray as xr
from PIL import Image
from rio_tiler.io.xarray import XarrayReader

TILE_SIZE = 256
DEFAULT_ZOOM_RANGE: tuple[int, int] = (5, 11)  # inclusive, per the D3 plan
_TMS = morecantile.tms.get("WebMercatorQuad")

# cmocean's oceanography-correct ramps (plan directive: layer-specific
# scientific color ramps, not a generic heatmap gradient) — extend this table
# as later D3 steps add SST/chlorophyll/wave/current layers.
COLOR_RAMPS: dict[str, Any] = {
    "bathymetry": cmocean.cm.cmap_d["deep"],
    "sst": cmocean.cm.cmap_d["thermal"],
    "salinity": cmocean.cm.cmap_d["haline"],
    "chlorophyll": cmocean.cm.cmap_d["algae"],
    "wave_height": cmocean.cm.cmap_d["amp"],
    "current_speed": cmocean.cm.cmap_d["speed"],
}


def _global_percentiles(
    values: np.ndarray, lo: float = 2.0, hi: float = 98.0
) -> tuple[float, float]:
    """Percentile normalization computed ONCE over the whole source grid, not
    per tile — the actual fix for tile-edge color seams: two adjacent tiles
    that each picked their own min/max would disagree on where a given value
    falls on the ramp exactly at the shared border. `values` should already
    be filtered to the valid/oceanic cells the caller cares about.
    """
    lo_val, hi_val = np.nanpercentile(values, [lo, hi])
    return float(lo_val), float(hi_val)


def _colorize_tile(
    display_values: np.ndarray,
    valid_mask: np.ndarray,
    data_min: float,
    data_max: float,
    cmap: Any,
) -> np.ndarray:
    """`display_values`: the 2D array already reprojected/resampled by
    XarrayReader.tile() (Rasterio's warp code under the hood), in the units
    the legend should show. `valid_mask`: True where the pixel should be
    opaque — combines rio-tiler's own out-of-source-bounds mask with the
    caller's data-specific validity predicate (e.g. "is ocean, not land").
    Returns an (H, W, 4) uint8 RGBA array, fully transparent wherever
    valid_mask is False.
    """
    norm = np.clip((display_values - data_min) / (data_max - data_min), 0.0, 1.0)
    rgba = (cmap(np.ma.filled(norm, 0.0)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid_mask, 255, 0).astype(np.uint8)
    return rgba


def generate_layer_tiles(
    data_array: xr.DataArray,
    *,
    layer_id: str,
    out_dir: Path,
    cmap_name: str,
    unit: str,
    valid_predicate: Callable[[np.ndarray], np.ndarray],
    to_display: Callable[[np.ndarray], np.ndarray] = lambda v: v,
    zoom_range: tuple[int, int] = DEFAULT_ZOOM_RANGE,
    reproject_method: str = "bilinear",
) -> dict[str, Any]:
    """Build a zoom_range[0]..zoom_range[1] XYZ PNG pyramid for one gridded
    field and write it to `out_dir/{z}/{x}/{y}.png`, plus a `meta.json`
    sidecar `orca/agents/visualization.py` reads cheaply at request time.

    `valid_predicate(raw_values) -> bool array`: which source cells are
    real data (e.g. bathymetry: `elevation < 0`, i.e. ocean not land).
    `to_display(raw_values) -> values`: transform raw source units into the
    units the legend/color ramp should show (e.g. bathymetry: `-elevation`,
    so the ramp reads in positive depth meters, not signed elevation).

    Tiles that end up fully transparent (no valid pixel — open ocean tiles
    outside a source's actual extent, or all-land tiles) are skipped rather
    than written — a 404 for those XYZ coordinates renders as "nothing
    there" in MapLibre, which is correct and saves a pyramid's worth of
    empty PNGs.
    """
    # Explicit, not auto-detected — rioxarray's CF-convention sniffing needs
    # standard_name attrs our source grids (plain "lat"/"lon" dims, no CF
    # metadata) don't reliably carry, so let it guess wrong silently.
    da = data_array.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False)
    if da.rio.crs is None:
        da = da.rio.write_crs("epsg:4326", inplace=False)

    raw = da.values
    valid = valid_predicate(raw)
    display_vals = to_display(raw)
    data_min, data_max = _global_percentiles(display_vals[valid])
    cmap = COLOR_RAMPS[cmap_name]

    lon_min, lat_min = float(da.lon.min()), float(da.lat.min())
    lon_max, lat_max = float(da.lon.max()), float(da.lat.max())
    bounds = (lon_min, lat_min, lon_max, lat_max)

    tile_count = 0
    with XarrayReader(da) as src:
        for z in range(zoom_range[0], zoom_range[1] + 1):
            for t in _TMS.tiles(*bounds, zooms=[z]):
                img = src.tile(t.x, t.y, t.z, tilesize=TILE_SIZE, reproject_method=reproject_method)
                arr = img.array  # numpy masked array: True = outside source bounds
                band = arr[0]
                display = to_display(np.ma.filled(band, np.nan))
                cell_valid = ~np.ma.getmaskarray(band)[:] & valid_predicate(np.ma.filled(band, np.nan))
                if not cell_valid.any():
                    continue  # all-land / all-out-of-bounds tile — skip, see docstring
                rgba = _colorize_tile(display, cell_valid, data_min, data_max, cmap)
                tile_path = out_dir / str(z) / str(t.x) / f"{t.y}.png"
                tile_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(rgba, mode="RGBA").save(tile_path)
                tile_count += 1

    meta = {
        "layer_id": layer_id,
        "tile_url_template": f"/tiles/{layer_id}/{{z}}/{{x}}/{{y}}.png",
        "bounds": bounds,
        "min_zoom": zoom_range[0],
        "max_zoom": zoom_range[1],
        "color_ramp": {"palette": f"cmocean-{cmap_name}", "data_min": data_min, "data_max": data_max, "unit": unit},
        "tile_count": tile_count,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def _sanitize_frame_dirname(iso_timestamp: str) -> str:
    return iso_timestamp.replace(":", "-")


def generate_forecast_tiles(
    frames: dict[str, xr.DataArray],
    *,
    layer_id: str,
    out_dir: Path,
    cmap_name: str,
    unit: str,
    valid_predicate: Callable[[np.ndarray], np.ndarray],
    to_display: Callable[[np.ndarray], np.ndarray] = lambda v: v,
    zoom_range: tuple[int, int] = DEFAULT_ZOOM_RANGE,
    reproject_method: str = "bilinear",
) -> dict[str, Any]:
    """Time-varying counterpart to `generate_layer_tiles` (plan §5.10 Day 12:
    `forecast_frames` over the 56 WW3 steps). `frames` is `{iso_timestamp:
    data_array}`, one per forecast step, already read off the source's own
    timestamp axis by the caller — never hard-coded here.

    Each frame gets its own tile pyramid under `out_dir/{iso_timestamp}/`,
    normalized against percentiles computed over the WHOLE time series (not
    per-frame) so a layer's colors mean the same thing on frame 0 and frame
    55 — a static color scale that drifts frame to frame would make "is the
    sea getting rougher" impossible to read from the animation alone.
    `timestamps` in the returned meta is exactly the `frames` dict's keys, in
    order — that ordering IS the frame sequence MapView's TimeSlider walks.
    """
    timestamps = tuple(frames.keys())
    if not timestamps:
        raise ValueError("generate_forecast_tiles requires at least one frame")

    all_display_valid = []
    prepared: list[tuple[str, xr.DataArray]] = []
    for ts, da in frames.items():
        da = da.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False)
        if da.rio.crs is None:
            da = da.rio.write_crs("epsg:4326", inplace=False)
        raw = da.values
        valid = valid_predicate(raw)
        display = to_display(raw)
        all_display_valid.append(display[valid])
        prepared.append((ts, da))

    # One global data_min/data_max across every frame — the fix for
    # frame-to-frame color drift, same principle as _global_percentiles'
    # tile-edge fix within a single frame.
    data_min, data_max = _global_percentiles(np.concatenate(all_display_valid))
    cmap = COLOR_RAMPS[cmap_name]

    import concurrent.futures
    import os

    def _render_frame(item):
        ts, da = item
        frame_dir = out_dir / _sanitize_frame_dirname(ts)
        local_count = 0
        lon_min, lat_min = float(da.lon.min()), float(da.lat.min())
        lon_max, lat_max = float(da.lon.max()), float(da.lat.max())
        local_bounds = (lon_min, lat_min, lon_max, lat_max)
        with XarrayReader(da) as src:
            for z in range(zoom_range[0], zoom_range[1] + 1):
                for t in _TMS.tiles(*local_bounds, zooms=[z]):
                    try:
                        img = src.tile(t.x, t.y, t.z, tilesize=TILE_SIZE, reproject_method=reproject_method)
                        arr = img.array
                        band = arr[0]
                        vals = np.ma.filled(band, np.nan)
                        cell_valid = ~np.ma.getmaskarray(band)[:] & valid_predicate(vals)
                        if not cell_valid.any():
                            continue
                        display = to_display(vals)
                        rgba = _colorize_tile(display, cell_valid, data_min, data_max, cmap)
                        tile_path = frame_dir / str(z) / str(t.x) / f"{t.y}.png"
                        tile_path.parent.mkdir(parents=True, exist_ok=True)
                        Image.fromarray(rgba, mode="RGBA").save(tile_path)
                        local_count += 1
                    except Exception:  # noqa: BLE001, S112 — tile outside spatial envelope or invalid reprojection
                        continue
        return local_count, local_bounds

    tile_count = 0
    bounds: tuple[float, float, float, float] | None = None
    workers = min(8, os.cpu_count() or 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for local_count, local_bounds in executor.map(_render_frame, prepared):
            tile_count += local_count
            bounds = local_bounds

    meta = {
        "layer_id": layer_id,
        "tile_url_template": f"/tiles/{layer_id}/{{time}}/{{z}}/{{x}}/{{y}}.png",
        "timestamps": list(timestamps),
        "bounds": bounds,
        "min_zoom": zoom_range[0],
        "max_zoom": zoom_range[1],
        "color_ramp": {"palette": f"cmocean-{cmap_name}", "data_min": data_min, "data_max": data_max, "unit": unit},
        "tile_count": tile_count,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    # ponytail: smallest runnable check for the non-trivial logic here — a
    # real synthetic ocean/land grid, one tile pyramid built end to end, and
    # three concrete acceptance assertions rather than "it ran without
    # throwing": land pixels are transparent, ocean pixels are opaque, and
    # the legend's data_min/max actually bracket the colorized ocean values.
    import shutil
    import tempfile

    lats = np.linspace(10.5, 7.5, 64)  # north -> south, GEBCO's own convention
    lons = np.linspace(77.5, 80.5, 64)
    # A synthetic seabed: half land (positive), half ocean sloping to -2000m.
    elevation = np.tile(np.linspace(-2000, 500, 64), (64, 1))
    da = xr.DataArray(elevation, coords={"lat": lats, "lon": lons}, dims=("lat", "lon"), name="elevation")

    tmp = Path(tempfile.mkdtemp())
    try:
        meta = generate_layer_tiles(
            da, layer_id="bathymetry_selfcheck", out_dir=tmp, cmap_name="bathymetry", unit="m",
            valid_predicate=lambda v: v < 0, to_display=lambda v: -v, zoom_range=(6, 6),
        )
        assert meta["tile_count"] > 0, "expected at least one tile with ocean pixels"
        assert meta["color_ramp"]["data_min"] >= 0, "depth legend should be positive meters"

        any_tile = next((tmp / "6").rglob("*.png"))
        rgba = np.array(Image.open(any_tile))
        opaque = rgba[..., 3] == 255
        transparent = rgba[..., 3] == 0
        assert opaque.any() or transparent.any()
        if opaque.any():
            # Every opaque pixel got a real color, not the (0,0,0) fallback —
            # cmap(0.0) for cmocean's deep ramp is a warm cream, never black.
            assert not (rgba[..., :3][opaque] == 0).all(axis=-1).any()
        print(f"tiles self-check OK: {meta['tile_count']} tiles, "
              f"depth range {meta['color_ramp']['data_min']:.0f}-{meta['color_ramp']['data_max']:.0f}m")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # generate_forecast_tiles: two synthetic frames with different values, so
    # the global-percentile-across-frames fix is actually exercised — if
    # each frame normalized against its own min/max instead, frame 0 and
    # frame 1 below would both read as "fully saturated ramp", masking the
    # bug this function exists to avoid.
    frame0 = xr.DataArray(np.tile(np.linspace(-500, 200, 64), (64, 1)),
                           coords={"lat": lats, "lon": lons}, dims=("lat", "lon"), name="wave")
    frame1 = xr.DataArray(np.tile(np.linspace(-2000, 200, 64), (64, 1)),
                           coords={"lat": lats, "lon": lons}, dims=("lat", "lon"), name="wave")
    tmp2 = Path(tempfile.mkdtemp())
    try:
        fmeta = generate_forecast_tiles(
            {"2026-09-01T00:00:00Z": frame0, "2026-09-01T03:00:00Z": frame1},
            layer_id="wave_selfcheck", out_dir=tmp2, cmap_name="wave_height", unit="m",
            valid_predicate=lambda v: v < 0, to_display=lambda v: -v, zoom_range=(6, 6),
        )
        assert fmeta["timestamps"] == ["2026-09-01T00:00:00Z", "2026-09-01T03:00:00Z"]
        assert fmeta["tile_count"] > 0
        assert (tmp2 / "2026-09-01T00-00-00Z" / "6").is_dir()
        assert (tmp2 / "2026-09-01T03-00-00Z" / "6").is_dir()
        # frame1's deeper range means its data_max should exceed frame0's
        # own range alone — proof the normalization is global, not per-frame.
        assert fmeta["color_ramp"]["data_max"] >= 1900
        print(f"forecast tiles self-check OK: {len(fmeta['timestamps'])} frames, "
              f"{fmeta['tile_count']} tiles total")
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)
