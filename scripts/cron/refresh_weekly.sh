#!/bin/sh
# ORCA weekly refresh — see docs/ORCA_Data_Refresh_Cron_Guide.md.
cd "$(dirname "$0")/../.." || exit 1
PY=backend/.venv/bin/python

"$PY" scripts/refresh_cmems.py
"$PY" scripts/refresh_gfw_ais.py
"$PY" scripts/refresh_nasa_ocean_color.py
"$PY" scripts/refresh_bhuvan_manifest.py
"$PY" scripts/refresh_openmeteo_caches.py

cd backend && ../"$PY" -m orca.data.freshness
