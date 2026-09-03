"""Build the raster tile pyramid(s) for Agent 8's Raster map layers (Phase 2
D3 step 1). Offline/build-time only — reprojecting a 720x720+ grid into a
zoom 5-11 XYZ pyramid is too expensive to redo per `/query`; this writes PNG
tiles + a meta.json sidecar to disk once, and orca/agents/visualization.py
only ever reads that sidecar at request time.

Tiles land in data/tier1/tiles/{layer_id}/ — data/ is gitignored (existing
project convention), so this script is how a fresh checkout gets tiles, the
same role scripts/download_ml_models.py plays for the ML weight caches.

Usage (from backend/, with backend/.venv active):
    pip install -r requirements.txt
    python scripts/generate_tiles.py
"""
import io
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ on sys.path, matches download_ml_models.py's peers

TILES_ROOT = Path(__file__).resolve().parents[2] / "data" / "tier1" / "tiles"
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def generate_wave_height_forecast_tiles():
    """Plan §5.10 Day 12: `forecast_frames` over the 56 WW3 3-hourly steps
    (2026-09-01T00:00Z -> 2026-09-07T21:00Z), real data — the significant
    wave height (`HS`) variable off `data/incois_osf_pfz/osf_ww3/`.

    ponytail: cropped to the pilot bbox + margin before tiling (the source
    grid is basin-wide, 901x901 at every one of 56 steps) and built at zoom
    5-8 rather than the static layers' 5-11 — a moving 56-frame pyramid at
    z11 is a multi-hour offline job for a demo-scale pilot region; z8 is
    already well past what a phone screen resolves for a whole-basin wave
    field. Upgrade path: widen to DEFAULT_ZOOM_RANGE once this runs on a
    real build machine, not a laptop.
    """
    print("\n[1/1] Building the wave-height forecast tile pyramid (WW3, cmocean 'amp')...")
    try:
        import datetime

        import numpy as np
        import xarray as xr

        from orca.tiles import generate_forecast_tiles

        ww3_files = sorted((DATA_ROOT / "incois_osf_pfz" / "osf_ww3").glob("*.nc"))
        if not ww3_files:
            print("[WARN] No WW3 .nc file found under data/incois_osf_pfz/osf_ww3/ — skipping.")
            return
        ds = xr.open_dataset(ww3_files[0], decode_times=False)

        # TIME units are "hours since 0001-01-01" (proleptic Gregorian) —
        # cftime isn't a project dependency and pandas' datetime64 overflows
        # trying to represent year-1 references, so decode by hand. The
        # actual offsets land in 2026, well inside plain datetime's range.
        ref = datetime.datetime(1, 1, 1, tzinfo=datetime.timezone.utc)
        timestamps = [
            (ref + datetime.timedelta(hours=float(h))).strftime("%Y-%m-%dT%H:%M:%SZ")
            for h in ds["TIME"].values
        ]

        # Pan-India maritime bounds matching INCOIS RSMC domain & user's reference image
        west, south, east, north = 65.0, 2.0, 96.0, 25.0
        cropped = ds["HS"].sel(IOXAXIS=slice(west, east), IOYAXIS=slice(south, north))
        cropped = cropped.rename({"IOXAXIS": "lon", "IOYAXIS": "lat"})

        frames = {
            ts: cropped.isel(TIME=i).where(np.isfinite(cropped.isel(TIME=i)))
            for i, ts in enumerate(timestamps)
        }
        import shutil
        shutil.rmtree(TILES_ROOT / "wave_height_forecast", ignore_errors=True)
        meta = generate_forecast_tiles(
            frames, layer_id="wave_height_forecast", out_dir=TILES_ROOT / "wave_height_forecast",
            cmap_name="wave_height", unit="m",
            valid_predicate=lambda v: np.isfinite(v) & (v >= 0) & (v < 30),  # HS fill values read as huge negatives/positives
            zoom_range=(5, 8),
        )
        print(
            f"[OK] {meta['tile_count']} tiles across {len(meta['timestamps'])} frames written, "
            f"zoom {meta['min_zoom']}-{meta['max_zoom']}, "
            f"wave height range {meta['color_ramp']['data_min']:.1f}-{meta['color_ramp']['data_max']:.1f}m."
        )
    except ImportError as e:
        print(f"[WARN] Missing dependency for forecast tile generation: {e}. Run: pip install -r requirements.txt")
    except Exception as e:  # noqa: BLE001 — best-effort setup script, report and continue
        print(f"[ERROR] Error building wave-height forecast tiles: {e}")


def generate_bathymetry_tiles():
    print("\n[1/1] Building the bathymetry raster tile pyramid (ETOPO Pan-India, cmocean 'deep')...")
    try:
        import xarray as xr
        from orca.tiles import generate_layer_tiles

        pan_india = DATA_ROOT / "tier1" / "bathymetry" / "etopo_all_india_bathymetry.nc"
        etopo_file = DATA_ROOT / "tier1" / "bathymetry" / "etopo_south_india_bathymetry.nc"
        if pan_india.exists():
            ds = xr.open_dataset(pan_india)
            da = ds["altitude"].rename({"latitude": "lat", "longitude": "lon"})
        elif etopo_file.exists():
            ds = xr.open_dataset(etopo_file)
            da = ds["altitude"].rename({"latitude": "lat", "longitude": "lon"})
        else:
            from orca.agents.geospatial import _bathymetry
            da = _bathymetry()["elevation"]

        meta = generate_layer_tiles(
            da,
            layer_id="bathymetry",
            out_dir=TILES_ROOT / "bathymetry",
            cmap_name="bathymetry",
            unit="m",
            valid_predicate=lambda v: v < 0,  # Negative elevation/altitude = ocean
            to_display=lambda v: -v,  # legend reads positive depth, not signed elevation
            zoom_range=(5, 8),
        )
        print(
            f"[OK] {meta['tile_count']} tiles written, zoom {meta['min_zoom']}-{meta['max_zoom']}, "
            f"depth range {meta['color_ramp']['data_min']:.0f}-{meta['color_ramp']['data_max']:.0f}m."
        )
    except ImportError as e:
        print(f"[WARN] Missing dependency for tile generation: {e}. Run: pip install -r requirements.txt")
    except Exception as e:  # noqa: BLE001 — best-effort setup script, report and continue
        print(f"[ERROR] Error building bathymetry tiles: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("ORCA — Building Raster Tile Pyramids (Phase 2 D3)")
    print("=" * 60)
    generate_bathymetry_tiles()
    generate_wave_height_forecast_tiles()
    print(f"\nDone! Tiles written under {TILES_ROOT}")
