#!/bin/sh
# ORCA daily refresh — see docs/ORCA_Data_Refresh_Cron_Guide.md.
# No `set -e`: one provider being down should not skip the other five refreshes.
# The freshness report at the end is what decides the exit code.
cd "$(dirname "$0")/../.." || exit 1
PY=backend/.venv/bin/python

"$PY" scripts/refresh_osf_forecasts.py
"$PY" scripts/extract_osf_pilot.py
"$PY" backend/scripts/generate_tiles.py
"$PY" scripts/scrape_pfz_advisories.py
"$PY" backend/scripts/build_all_india_pfz.py
"$PY" scripts/refresh_tide_tables.py
# MOSDAC last: 54 MB granules over a link that drops, by far the longest step.
"$PY" scripts/refresh_mosdac.py

cd backend && ../"$PY" -m orca.data.freshness
