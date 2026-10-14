#!/usr/bin/env bash
# ==============================================================================
# ORCA Unified Cron Data Refresh Script
#
# Runs inside the Docker container on AWS EC2 or standalone in local dev.
# Executed via:
#   docker exec orca-backend /bin/bash /scripts/cron_refresh.sh
# ==============================================================================
set -u

echo "========================================================================"
echo "  ORCA: Scheduled Data Refresh started at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================================================"

# Determine base directory (repo root or /app inside container)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT" 2>/dev/null || cd /app || exit 1

# Keep attempting independent refreshes, but preserve failures for the exit
# status so cron monitoring cannot mistake a partial run for a clean one.
FAILED_STEPS=0
run_step() {
    label="$1"
    shift
    echo "${label}"
    "$@"
    status=$?
    if [ "$status" -ne 0 ]; then
        echo "[ERROR] ${label} failed (exit ${status})."
        FAILED_STEPS=$((FAILED_STEPS + 1))
    fi
    return 0
}

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
run_step ">> Fetching INCOIS Ocean State Forecasts (WW3 & HYCOM)..." "$PY" scripts/refresh_osf_forecasts.py
run_step ">> Extracting OSF pilot data..." "$PY" scripts/extract_osf_pilot.py
run_step ">> Generating derived raster wave tiles..." "$PY" backend/scripts/generate_tiles.py
run_step ">> Scraping INCOIS Potential Fishing Zone (PFZ) advisories..." "$PY" scripts/scrape_pfz_advisories.py
run_step ">> Building National All-India PFZ GeoJSON..." "$PY" backend/scripts/build_all_india_pfz.py
run_step ">> Refreshing rolling 7-day Tide Tables (Survey of India / Stormglass)..." "$PY" scripts/refresh_tide_tables.py
run_step ">> Refreshing MOSDAC INSAT-3DR Sea Surface Temperature (SST)..." "$PY" scripts/refresh_mosdac.py

# ------------------------------------------------------------------------------
# Phase 2: Weekly Datasets (Runs on Sundays, day 7)
# ------------------------------------------------------------------------------
DAY_OF_WEEK=$(date +%u) # 1 = Monday, 7 = Sunday
if [ "$DAY_OF_WEEK" -eq 7 ] || [ "${FORCE_WEEKLY:-0}" = "1" ]; then
    echo ""
    echo "--- [2/3] Sunday Weekly Datasets ---"
    run_step ">> Refreshing Copernicus CMEMS..." "$PY" scripts/refresh_cmems.py
    run_step ">> Refreshing Global Fishing Watch AIS..." "$PY" scripts/refresh_gfw_ais.py
    run_step ">> Refreshing NASA Ocean Color MODIS granules..." "$PY" scripts/refresh_nasa_ocean_color.py
    run_step ">> Checking ISRO Bhuvan WMS service reachability..." "$PY" scripts/refresh_bhuvan_manifest.py
    run_step ">> Updating Open-Meteo offline marine fallback caches..." "$PY" scripts/refresh_openmeteo_caches.py
    run_step ">> Rolling 30-day ERA5 baseline window forward..." "$PY" scripts/refresh_era5_baselines.py
else
    echo ""
    echo "--- [2/3] Skipping weekly-only datasets (runs automatically on Sundays) ---"
fi

# ------------------------------------------------------------------------------
# Phase 3: Freshness Audit
# ------------------------------------------------------------------------------
echo ""
echo "--- [3/3] Auditing Overall Data Freshness ---"
run_step ">> Checking registered source freshness..." "$PY" -m orca.data.freshness

echo ""
echo "========================================================================"
if [ "$FAILED_STEPS" -eq 0 ]; then
    echo "  ORCA: Data Refresh completed successfully at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
else
    echo "  ORCA: Data Refresh finished with ${FAILED_STEPS} failed step(s) at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
fi
echo "========================================================================"
if [ "$FAILED_STEPS" -ne 0 ]; then
    exit 1
fi
exit 0
