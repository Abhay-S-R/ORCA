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
    """Plan §5.10 Day 12: `forecast_frames` over the 56 WW3 3-hourly steps of
    the **newest** run on disk — real data, the significant wave height (`HS`)
    variable off `data/incois_osf_pfz/osf_ww3/`.

    Take the last file of the sorted glob, not the first: `refresh_osf_forecasts.py`
    writes a new `rsmc_combined_ww3_<date>.nc` each run and leaves the old one
    beside it, so `[0]` pins the animated layer to the oldest run forever
    (R-FRESH-1 — it did exactly that, for 17 days). Same reasoning as
    `geospatial._hycom()`.

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
        ds = xr.open_dataset(ww3_files[-1], decode_times=False)
        print(f"        source run: {ww3_files[-1].name} (newest of {len(ww3_files)} on disk)")

        # TIME units are "hours since 0001-01-01" with calendar "standard" —
        # cftime isn't a project dependency and pandas' datetime64 overflows
        # trying to represent year-1 references, so decode by hand. The
        # actual offsets land in 2026, well inside plain datetime's range.
        #
        # The -48 h is not a fudge: "standard" that far back is Julian, and
        # Python's proleptic-Gregorian datetime(1, 1, 1) sits two days after it.
        # Without the shift every frame is labelled two days into the future —
        # the 2026-09-17 run rendered as a 09-20 -> 09-26 forecast. Same
        # correction as `voyage._ww3_hours_since_epoch` and
        # `extract_osf_pilot`, which have always had it right.
        ref = datetime.datetime(1, 1, 1, tzinfo=datetime.timezone.utc)
        JULIAN_OFFSET_H = 48.0
        times = [
            ref + datetime.timedelta(hours=float(h) - JULIAN_OFFSET_H)
            for h in ds["TIME"].values
        ]
        timestamps = [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times]

        # A run cannot forecast its own past, and it starts within a day of
        # being issued. This is the check that fails if the epoch drifts again.
        run_date = datetime.datetime.strptime(
            ww3_files[-1].stem.split("_")[-1], "%Y%m%d"
        ).replace(tzinfo=datetime.timezone.utc)
        if not run_date <= times[0] <= run_date + datetime.timedelta(days=2):
            print(
                f"[ERROR] First frame {timestamps[0]} is implausible for a run dated "
                f"{run_date:%Y-%m-%d} — the TIME epoch decode is wrong. Not writing tiles."
            )
            return

        # A forecast pyramid whose last frame is already in the past is not a
        # forecast. Warn loudly rather than failing — the tiles are still the
        # best available — but nobody should discover this from the map legend.
        last_frame = datetime.datetime.strptime(timestamps[-1], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
        if last_frame < datetime.datetime.now(datetime.timezone.utc):
            print(
                f"[WARN] Newest frame {timestamps[-1]} is already in the past — "
                f"run scripts/refresh_osf_forecasts.py before relying on this layer."
            )

        # Pan-India maritime bounds matching INCOIS RSMC domain & user's reference image
        west, south, east, north = 65.0, 2.0, 96.0, 25.0
        cropped = ds["HS"].sel(IOXAXIS=slice(west, east), IOYAXIS=slice(south, north))
        cropped = cropped.rename({"IOXAXIS": "lon", "IOYAXIS": "lat"})

        # Super-sample and smooth the wave field across Pan-India to eliminate
        # 11km blocky pixels, aligning the wave front with the natural high-resolution coastline.
        from scipy import ndimage

        etopo_path = DATA_ROOT / "tier1" / "bathymetry" / "etopo_all_india_bathymetry.nc"
        alt_data = None
        if etopo_path.exists():
            etopo = xr.open_dataset(etopo_path)
            alt = etopo["altitude"].rename({"latitude": "lat", "longitude": "lon"})
            # Subsample etopo slightly (stride 2) for optimal tile rendering speed (~0.03 deg / 3km resolution)
            alt_data = alt.sel(lat=slice(south, north), lon=slice(west, east)).isel(lat=slice(None, None, 2), lon=slice(None, None, 2))

        def _smooth_frame(da: xr.DataArray) -> xr.DataArray:
            vals = da.values.copy()
            mask = np.isnan(vals)
            if not mask.any():
                return da
            # Nearest neighbor ocean extrapolation into coastal land cells
            ind = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
            filled = vals[tuple(ind)]

            if alt_data is not None:
                scale_y = alt_data.shape[0] / filled.shape[0]
                scale_x = alt_data.shape[1] / filled.shape[1]
                smooth = ndimage.zoom(filled, (scale_y, scale_x), order=3)[:alt_data.shape[0], :alt_data.shape[1]]
                smooth[alt_data.values >= 0] = np.nan
                target_lat, target_lon = alt_data.lat, alt_data.lon
            else:
                smooth = ndimage.zoom(filled, 3.0, order=3)
                mask_coarse = ndimage.zoom(mask.astype(float), 3.0, order=1) > 0.6
                smooth[mask_coarse] = np.nan
                target_lat = np.linspace(float(da.lat.min()), float(da.lat.max()), smooth.shape[0])
                target_lon = np.linspace(float(da.lon.min()), float(da.lon.max()), smooth.shape[1])

            out = xr.DataArray(smooth, coords={"lat": target_lat, "lon": target_lon}, dims=["lat", "lon"])
            return out.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=False).rio.write_crs("epsg:4326", inplace=False)

        print("[*] Smoothing 56 forecast frames with cubic spline & ETOPO high-res coastline...")
        frames = {
            ts: _smooth_frame(cropped.isel(TIME=i))
            for i, ts in enumerate(timestamps)
        }
        # Build into a sibling temp directory and swap it in with one os.replace
        # once every frame and meta.json are written — an interrupted run (a
        # laptop closed mid-build, a kill -9) then leaves the previous good
        # pyramid live instead of an empty/half-written layer with no
        # meta.json (R-FRESH-1: that exact interruption is what produced the
        # 8/56-frames-no-meta.json state this replaces).
        import shutil

        live_dir = TILES_ROOT / "wave_height_forecast"
        build_dir = TILES_ROOT / "wave_height_forecast.building"
        shutil.rmtree(build_dir, ignore_errors=True)
        meta = generate_forecast_tiles(
            frames, layer_id="wave_height_forecast", out_dir=build_dir,
            cmap_name="wave_height", unit="m",
            valid_predicate=lambda v: np.isfinite(v) & (v >= 0) & (v < 30),  # HS fill values read as huge negatives/positives
            zoom_range=(5, 8),
        )
        old_dir = TILES_ROOT / "wave_height_forecast.old"
        shutil.rmtree(old_dir, ignore_errors=True)
        if live_dir.exists():
            live_dir.rename(old_dir)
        build_dir.rename(live_dir)
        shutil.rmtree(old_dir, ignore_errors=True)
        print(
            f"[OK] {meta['tile_count']} tiles across {len(meta['timestamps'])} frames written, "
            f"zoom {meta['min_zoom']}-{meta['max_zoom']}, "
            f"wave height range {meta['color_ramp']['data_min']:.1f}-{meta['color_ramp']['data_max']:.1f}m."
        )
    except ImportError as e:
        print(f"[WARN] Missing dependency for forecast tile generation: {e}. Run: pip install -r requirements.txt")
    except Exception as e:
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
    except Exception as e:
        print(f"[ERROR] Error building bathymetry tiles: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("ORCA — Building Raster Tile Pyramids (Phase 2 D3)")
    print("=" * 60)
    generate_bathymetry_tiles()
    generate_wave_height_forecast_tiles()
    print(f"\nDone! Tiles written under {TILES_ROOT}")
