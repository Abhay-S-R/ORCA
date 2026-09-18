@echo off
REM ORCA daily refresh — the 6 DAILY-class sources plus their derived artefacts.
REM Scheduled by docs/ORCA_Data_Refresh_Cron_Guide.md. Exits 1 if any source is
REM in breach afterwards, so Task Scheduler's Last Run Result is the alarm.
cd /d "%~dp0..\.."
set PY=backend\.venv\Scripts\python.exe

%PY% scripts\refresh_osf_forecasts.py
%PY% scripts\extract_osf_pilot.py
%PY% backend\scripts\generate_tiles.py
%PY% scripts\scrape_pfz_advisories.py
%PY% backend\scripts\build_all_india_pfz.py
%PY% scripts\refresh_tide_tables.py
REM MOSDAC last: 54 MB granules over a link that drops, by far the longest step.
%PY% scripts\refresh_mosdac.py

cd backend
..\%PY% -m orca.data.freshness
exit /b %ERRORLEVEL%
