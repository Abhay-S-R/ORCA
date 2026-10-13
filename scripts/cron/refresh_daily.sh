#!/bin/sh
# ORCA daily refresh — see docs/guides/ORCA_Data_Refresh_Cron_Guide.md.
# No `set -e`: one provider being down should not skip the other five refreshes.
# The freshness report at the end is what decides the exit code.
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

"$PY" scripts/refresh_osf_forecasts.py
"$PY" scripts/extract_osf_pilot.py
"$PY" backend/scripts/generate_tiles.py
"$PY" scripts/scrape_pfz_advisories.py
"$PY" backend/scripts/build_all_india_pfz.py
"$PY" scripts/refresh_tide_tables.py
# MOSDAC last: 54 MB granules over a link that drops, by far the longest step.
"$PY" scripts/refresh_mosdac.py

"$PY" -m orca.data.freshness
