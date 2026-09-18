@echo off
REM ORCA weekly refresh — the WEEKLY-class sources not already covered by the
REM daily MOSDAC run, plus the Open-Meteo offline caches (7-day validity).
REM Scheduled by docs/Guide/ORCA_Data_Refresh_Cron_Guide.md.
cd /d "%~dp0..\.."
set PY=backend\.venv\Scripts\python.exe

%PY% scripts\refresh_cmems.py
%PY% scripts\refresh_gfw_ais.py
%PY% scripts\refresh_nasa_ocean_color.py
%PY% scripts\refresh_bhuvan_manifest.py
%PY% scripts\refresh_openmeteo_caches.py
REM Rolls the 30-day ERA5 reference period forward. Skips every port whose
REM window is still current, so most weeks this is a no-op.
%PY% scripts\refresh_era5_baselines.py

cd backend
..\%PY% -m orca.data.freshness
exit /b %ERRORLEVEL%
