#!/bin/sh
# ORCA weekly refresh — see docs/guides/ORCA_Data_Refresh_Cron_Guide.md.
cd "$(dirname "$0")/../.." || exit 1
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

"$PY" scripts/refresh_cmems.py
"$PY" scripts/refresh_gfw_ais.py
"$PY" scripts/refresh_nasa_ocean_color.py
"$PY" scripts/refresh_bhuvan_manifest.py
"$PY" scripts/refresh_openmeteo_caches.py
# Rolls the 30-day ERA5 reference period forward; a no-op when every port's
# window is still current.
"$PY" scripts/refresh_era5_baselines.py

"$PY" -m orca.data.freshness
