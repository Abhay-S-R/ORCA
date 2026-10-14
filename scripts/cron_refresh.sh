#!/usr/bin/env bash
# ==============================================================================
# ORCA Unified Cron Data Refresh Script
#
# Runs inside the Docker container on AWS EC2 or standalone in local dev.
# Executed via:
#   docker exec orca-backend /bin/sh /scripts/cron_refresh.sh
# ==============================================================================
set -u

echo "========================================================================"
echo "  ORCA: Scheduled Data Refresh started at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================================================"

# Determine base directory (repo root or /app inside container)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT" 2>/dev/null || cd /app || exit 1

# Detect python executable
if [ -x "backend/.venv/bin/python" ]; then
    PY="backend/.venv/bin/python"
elif [ -x "backend/.venv/Scripts/python.exe" ]; then
    PY="backend/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    PY="python"
fi

export PYTHONIOENCODING=utf-8
if [ -d "backend" ]; then
    export PYTHONPATH="${PYTHONPATH:-.}:backend"
else
    export PYTHONPATH="${PYTHONPATH:-.}"
fi

# ------------------------------------------------------------------------------
# Phase 1: Daily Critical Datasets (Runs Every Single Day)
# ------------------------------------------------------------------------------
echo ""
echo "--- [1/3] Running Daily Datasets ---"
echo ">> Fetching INCOIS Ocean State Forecasts (WW3 & HYCOM)..."
"$PY" scripts/refresh_osf_forecasts.py || true

echo ">> Extracting OSF pilot data..."
"$PY" scripts/extract_osf_pilot.py || true

echo ">> Generating derived raster wave tiles..."
"$PY" backend/scripts/generate_tiles.py || true

echo ">> Scraping INCOIS Potential Fishing Zone (PFZ) advisories..."
"$PY" scripts/scrape_pfz_advisories.py || true

echo ">> Building National All-India PFZ GeoJSON..."
"$PY" backend/scripts/build_all_india_pfz.py || true

echo ">> Refreshing rolling 7-day Tide Tables (Survey of India / Stormglass)..."
"$PY" scripts/refresh_tide_tables.py || true

echo ">> Refreshing MOSDAC INSAT-3DR Sea Surface Temperature (SST)..."
"$PY" scripts/refresh_mosdac.py || true

# ------------------------------------------------------------------------------
# Phase 2: Weekly Datasets (Runs on Sundays, day 7)
# ------------------------------------------------------------------------------
DAY_OF_WEEK=$(date +%u) # 1 = Monday, 7 = Sunday
if [ "$DAY_OF_WEEK" -eq 7 ] || [ "${FORCE_WEEKLY:-0}" = "1" ]; then
    echo ""
    echo "--- [2/3] Sunday Weekly Datasets ---"
    echo ">> Refreshing Copernicus CMEMS..."
    "$PY" scripts/refresh_cmems.py || true

    echo ">> Refreshing Global Fishing Watch AIS..."
    "$PY" scripts/refresh_gfw_ais.py || true

    echo ">> Refreshing NASA Ocean Color MODIS granules..."
    "$PY" scripts/refresh_nasa_ocean_color.py || true

    echo ">> Checking ISRO Bhuvan WMS service reachability..."
    "$PY" scripts/refresh_bhuvan_manifest.py || true

    echo ">> Updating Open-Meteo offline marine fallback caches..."
    "$PY" scripts/refresh_openmeteo_caches.py || true

    echo ">> Rolling 30-day ERA5 baseline window forward..."
    "$PY" scripts/refresh_era5_baselines.py || true
else
    echo ""
    echo "--- [2/3] Skipping weekly-only datasets (runs automatically on Sundays) ---"
fi

# ------------------------------------------------------------------------------
# Phase 3: Freshness Audit
# ------------------------------------------------------------------------------
echo ""
echo "--- [3/3] Auditing Overall Data Freshness ---"
"$PY" -m orca.data.freshness || true

echo ""
echo "========================================================================"
echo "  ORCA: Data Refresh completed at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================================================"
