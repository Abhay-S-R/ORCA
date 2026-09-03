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


def generate_bathymetry_tiles():
    print("\n[1/1] Building the bathymetry raster tile pyramid (GEBCO, cmocean 'deep')...")
    try:
        from orca.agents.geospatial import _bathymetry
        from orca.tiles import generate_layer_tiles

        elevation = _bathymetry()["elevation"]
        meta = generate_layer_tiles(
            elevation,
            layer_id="bathymetry",
            out_dir=TILES_ROOT / "bathymetry",
            cmap_name="bathymetry",
            unit="m",
            valid_predicate=lambda v: v < 0,  # GEBCO: negative elevation = ocean
            to_display=lambda v: -v,  # legend reads positive depth, not signed elevation
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
    print(f"\nDone! Tiles written under {TILES_ROOT}")
