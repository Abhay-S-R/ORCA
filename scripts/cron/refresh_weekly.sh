#!/bin/sh
# ORCA weekly refresh — see docs/Guide/ORCA_Data_Refresh_Cron_Guide.md.
cd "$(dirname "$0")/../.." || exit 1
PY=backend/.venv/bin/python

"$PY" scripts/refresh_cmems.py
"$PY" scripts/refresh_gfw_ais.py
"$PY" scripts/refresh_nasa_ocean_color.py
"$PY" scripts/refresh_bhuvan_manifest.py
"$PY" scripts/refresh_openmeteo_caches.py
# Rolls the 30-day ERA5 reference period forward; a no-op when every port's
# window is still current.
"$PY" scripts/refresh_era5_baselines.py

cd backend && ../"$PY" -m orca.data.freshness
