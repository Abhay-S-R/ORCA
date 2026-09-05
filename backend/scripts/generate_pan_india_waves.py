"""Build Pan-India Wave Height Forecast tile pyramid (56 frames, 65-96 E, 2-25 N).
Uses real INCOIS WaveWatch III model (rsmc_combined_ww3_20260829.nc).
Multi-threaded across all CPU cores for fast generation.
"""
import concurrent.futures
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orca.tiles import (
    _fix_proj_env,
    _sanitize_frame_dirname,
    _colorize_tile,
    COLOR_RAMPS,
    TILE_SIZE,
)
_fix_proj_env()

import morecantile
import numpy as np
from PIL import Image
from rio_tiler.io.xarray import XarrayReader
import xarray as xr

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
TILES_ROOT = DATA_ROOT / "tier1" / "tiles"
WW3_FILE = DATA_ROOT / "incois_osf_pfz" / "osf_ww3" / "rsmc_combined_ww3_20260829.nc"
OUT_DIR = TILES_ROOT / "wave_height_forecast"

_TMS = morecantile.tms.get("WebMercatorQuad")

# Pan-India maritime bounds matching Image 1
BOUNDS = (65.0, 2.0, 96.0, 25.0)
ZOOM_RANGE = (5, 8)


def render_single_frame(args):
    idx, ts, frame_da, data_min, data_max, cmap = args
    frame_dir = OUT_DIR / _sanitize_frame_dirname(ts)
    
    # Pre-setup DataArray spatial dimensions for rioxarray
    da = frame_da.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False)
    if da.rio.crs is None:
        da = da.rio.write_crs("EPSG:4326")

    count = 0
    with XarrayReader(da) as src:
        for z in range(ZOOM_RANGE[0], ZOOM_RANGE[1] + 1):
            for t in _TMS.tiles(*BOUNDS, zooms=[z]):
                try:
                    img = src.tile(t.x, t.y, t.z, tilesize=TILE_SIZE, reproject_method="bilinear")
                    arr = img.array
                    band = arr[0]
                    vals = np.ma.filled(band, np.nan)
                    cell_valid = ~np.ma.getmaskarray(band)[:] & np.isfinite(vals) & (vals >= 0) & (vals < 30)
                    if not cell_valid.any():
                        continue
                    rgba = _colorize_tile(vals, cell_valid, data_min, data_max, cmap)
                    tile_path = frame_dir / str(z) / str(t.x) / f"{t.y}.png"
                    tile_path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(rgba, mode="RGBA").save(tile_path)
                    count += 1
                except Exception:
                    continue
    return idx, ts, count


def main():
    print("=" * 60)
    print("Building Pan-India Wave Height Forecast Tiles (INCOIS WW3)")
    print("=" * 60)

    if not WW3_FILE.exists():
        print(f"[ERROR] Missing WW3 file: {WW3_FILE}")
        return

    ds = xr.open_dataset(WW3_FILE, decode_times=False)

    ref = datetime.datetime(1, 1, 1, tzinfo=datetime.timezone.utc)
    timestamps = [
        (ref + datetime.timedelta(hours=float(h))).strftime("%Y-%m-%dT%H:%M:%SZ")
        for h in ds["TIME"].values
    ]

    west, south, east, north = BOUNDS
    cropped = ds["HS"].sel(IOXAXIS=slice(west, east), IOYAXIS=slice(south, north))
    cropped = cropped.rename({"IOXAXIS": "lon", "IOYAXIS": "lat"})

    # Scientific color ramp & bounds matching Image 1
    cmap = COLOR_RAMPS["wave_height"]
    data_min = 0.5   # Calm
    data_max = 3.5   # High seas

    print(f"Coverage: {BOUNDS}")
    print(f"Frames: {len(timestamps)} timestamps (3-hourly forecast)")
    print(f"Wave Height range: {data_min}m to {data_max}m")
    print(f"Zoom levels: {ZOOM_RANGE}")

    # Prepare tasks
    tasks = []
    for i, ts in enumerate(timestamps):
        frame_da = cropped.isel(TIME=i).where(np.isfinite(cropped.isel(TIME=i)))
        tasks.append((i, ts, frame_da, data_min, data_max, cmap))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total_tiles = 0
    workers = min(8, os.cpu_count() or 4)
    print(f"\nRendering with {workers} parallel worker threads...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(render_single_frame, task) for task in tasks]
        for f in concurrent.futures.as_completed(futures):
            idx, ts, count = f.result()
            total_tiles += count
            print(f"  Frame [{idx+1}/{len(timestamps)}] {ts}: {count} tiles rendered.")

    # Write meta.json
    meta = {
        "layer_id": "wave_height_forecast",
        "tile_url_template": "/tiles/wave_height_forecast/{time}/{z}/{x}/{y}.png",
        "timestamps": timestamps,
        "bounds": list(BOUNDS),
        "min_zoom": ZOOM_RANGE[0],
        "max_zoom": ZOOM_RANGE[1],
        "color_ramp": {
            "palette": "cmocean-wave_height",
            "data_min": data_min,
            "data_max": data_max,
            "unit": "m",
        },
        "tile_count": total_tiles,
    }
    meta_file = OUT_DIR / "meta.json"
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\n[SUCCESS] Wrote {total_tiles} tiles across {len(timestamps)} frames!")
    print(f"Meta updated at: {meta_file}")


if __name__ == "__main__":
    main()
