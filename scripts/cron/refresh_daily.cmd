@echo off
REM ORCA daily refresh — the 6 DAILY-class sources plus their derived artefacts.
REM Scheduled by docs/guides/ORCA_Data_Refresh_Cron_Guide.md. Always deploys
REM to Render after pulling the latest available data. Freshness breaches are
REM logged as warnings (upstream sources may not have published new data).
cd /d "%~dp0..\.."
set PY=backend\.venv\Scripts\python.exe
REM Gazetteer aliases include Tamil script; a cp1252 console kills the job
REM mid-run and the freshness gate never gets to report. Affects stdout only.
set PYTHONIOENCODING=utf-8

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
set FRESHNESS_EXIT=%ERRORLEVEL%
cd /d "%~dp0..\.."

if %FRESHNESS_EXIT% neq 0 (
    echo [WARN] Freshness gate reports breach(es) [exit code %FRESHNESS_EXIT%].
    echo [WARN] Deploying anyway — upstream sources may not have published new data.
)

echo.
echo Deploying refreshed data to Render...
call scripts\deploy_data.cmd
exit /b %ERRORLEVEL%
