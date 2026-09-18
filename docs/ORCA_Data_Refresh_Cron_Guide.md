# ORCA Scheduled Refresh (cron / Task Scheduler) Guide

**Status:** operational. **Audience:** every developer with a clone.
**Companion:** `docs/ORCA_Data_Refresh_Guide.md` — the manual procedure and the credential
setup. Do that once, by hand, and confirm `0 breach(es)` **before** you automate anything.
Automating a run you have never seen succeed just schedules a silent failure.
**Normative source:** `docs/ORCA_Data_Freshness_Contract.md` §3 assigns every class below.

---

## 1. The short answer

Of ORCA's 27 declared sources, **11 need a schedule**. The other 16 do not, and setting a
timer for them wastes bandwidth and provider quota:

| Group | Count | Schedule |
|---|---|---|
| LIVE — fetched over HTTP on every query | 5 | **never**. Nothing to download. |
| DAILY — must carry a current date | 6 | **daily** |
| WEEKLY — physical signal moves slower than publication | 8 | **weekly** (5 of them; 3 ride along with the daily MOSDAC run) |
| STATIC — geometry and gazetteers | 8 | **never**, except one monthly liveness check |

That is **two scheduled jobs**, plus one optional monthly one. Everything else is noise.

---

## 2. Which datasets need a job, and why

### Daily — job `orca-refresh-daily`

| Source id | Class | Script | Why daily |
|---|---|---|---|
| `incois_osf_ww3` | DAILY | `refresh_osf_forecasts.py` | INCOIS republishes the Ocean State Forecast on a 6 h cycle; the 7-day wave forecast read a fortnight late is not stale data, it is *wrong* data |
| `incois_osf_hycom` | DAILY | `refresh_osf_forecasts.py` | same run, the currents half |
| `incois_pfz` | DAILY | `scrape_pfz_advisories.py` | INCOIS issues potential-fishing-zone advisories for the day; yesterday's sends a boat to the wrong water |
| `soi_tide_tables` | DAILY | `refresh_tide_tables.py` | the table holds a rolling **7-day** horizon. Once its last row falls into the past, `predict_tides()` returns `UNKNOWN` for *every* port — the query becomes unanswerable, not degraded |
| `mosdac_open_sst` | DAILY | `refresh_mosdac.py` | INSAT-3DR publishes a daily SST composite |
| `mosdac_nrt_sst` | DAILY | `refresh_mosdac.py` | same granules, registered separately |

Three derived artefacts must run **after** their input in the same job, or they rebuild from
yesterday's grids: `extract_osf_pilot.py` and `backend/scripts/generate_tiles.py` consume the
WW3 run, and `backend/scripts/build_all_india_pfz.py` consumes the PFZ advisories.

`refresh_mosdac.py` also refreshes `mosdac_*_chl` and `mosdac_nrt_wind`, which are only
WEEKLY. Running them daily is free — the script skips files already on disk — so there is no
separate weekly MOSDAC job.

### Weekly — job `orca-refresh-weekly`

| Source id | Class | Script | Why weekly is enough |
|---|---|---|---|
| `copernicus_cmems` | WEEKLY | `refresh_cmems.py` | analysed reanalysis products; multi-GB, published in arrears |
| `gfw_ais` | WEEKLY | `refresh_gfw_ais.py` | ORCA cites fleet-activity *context*, not live hull tracking |
| `nasa_ocean_color` | WEEKLY | `refresh_nasa_ocean_color.py` | a granule *listing* used to cross-check MOSDAC, not pixels |
| `bhuvan_wms` | WEEKLY | `refresh_bhuvan_manifest.py` | a reachability record for basemap layers, not imagery |
| `stormglass_tides` | WEEKLY | `refresh_tide_tables.py` | written by the daily tide job; listed here only so the mapping is complete |
| `mosdac_open_chl`, `mosdac_nrt_chl`, `mosdac_nrt_wind` | WEEKLY | `refresh_mosdac.py` | covered by the daily job above |

Add `refresh_openmeteo_caches.py` to this job. Open-Meteo is LIVE and needs no download, but
these caches are its **offline fallback** — the reason a network failure mid-demo degrades an
answer instead of killing it — and they carry a 7-day validity window.

### Never scheduled

- **The 5 LIVE sources** — `open_meteo_marine`, `incois_hazard_osf`, `ndma_sachet`,
  `damini_lightning`, `incois_tide_gauge`. These are HTTP calls made while answering a query.
  A cron job cannot make them fresher; only a working connection can. If one of these breaches,
  a scheduler is not the fix.
- **The 8 STATIC sources** — bathymetry, EEZ and MPA polygons, SAR stations, CMFRI landings,
  the fishing-ban order, the data.gov catch series, and `incois_erddap`. These are coastlines
  and gazetteers. Refreshing them is a procurement decision on a multi-year cycle. They cannot
  breach, so a job for them would never have anything to report.

### Optional monthly — `orca-check-ban-order`

`refresh_fishing_ban_order.py` is the one exception worth a timer. The ban order itself is
STATIC, but the script asks the Department of Fisheries' CMS whether a **newer order has been
published** and fails loudly if one has. A superseded ban window sitting in the data tells a
fisher the sea is open when it is closed. Monthly is enough — the order changes annually — and
the check is a single cheap request.

---

## 3. Setting it up

### The one thing that breaks every scheduled run

**A scheduler has no activated virtualenv and often no useful `PATH`.** `python scripts/...`
works in your shell and fails at 05:30 with `ModuleNotFoundError: requests`. Every command
below uses the venv interpreter by absolute path, which is also the project rule:

```
backend\.venv\Scripts\python.exe     (Windows)
backend/.venv/bin/python             (macOS / Linux)
```

Also set the working directory to the repo root — the scripts resolve `data/` and `.env`
relative to it.

### Windows: two wrapper scripts, two tasks

The wrappers are in the repo. `scripts/cron/refresh_daily.cmd`:

```bat
@echo off
cd /d "%~dp0..\.."
set PY=backend\.venv\Scripts\python.exe

%PY% scripts\refresh_osf_forecasts.py
%PY% scripts\extract_osf_pilot.py
%PY% backend\scripts\generate_tiles.py
%PY% scripts\scrape_pfz_advisories.py
%PY% backend\scripts\build_all_india_pfz.py
%PY% scripts\refresh_tide_tables.py
%PY% scripts\refresh_mosdac.py

cd backend && ..\%PY% -m orca.data.freshness
exit /b %ERRORLEVEL%
```

The last two lines are the point of the whole thing: the freshness report **exits 1 on any
breach**, so the task's own "Last Run Result" column in Task Scheduler becomes your breach
alarm. A job that refreshes without verifying is a job that fails quietly for a week.

`scripts/cron/refresh_weekly.cmd` is the same shape:

```bat
@echo off
cd /d "%~dp0..\.."
set PY=backend\.venv\Scripts\python.exe

%PY% scripts\refresh_cmems.py
%PY% scripts\refresh_gfw_ais.py
%PY% scripts\refresh_nasa_ocean_color.py
%PY% scripts\refresh_bhuvan_manifest.py
%PY% scripts\refresh_openmeteo_caches.py

cd backend && ..\%PY% -m orca.data.freshness
exit /b %ERRORLEVEL%
```

Register both. Use PowerShell rather than `schtasks`, because only this form gets
`-StartWhenAvailable`, and a laptop that was asleep at 05:30 is the normal case:

```powershell
$repo = "C:\Users\<you>\Desktop\orca"
$set  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
          -RunOnlyIfNetworkAvailable -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "orca-refresh-daily" -Settings $set `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 5:30am) `
  -Action  (New-ScheduledTaskAction -Execute "$repo\scripts\cron\refresh_daily.cmd" `
                                    -WorkingDirectory $repo)

Register-ScheduledTask -TaskName "orca-refresh-weekly" -Settings $set `
  -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 6:30am) `
  -Action  (New-ScheduledTaskAction -Execute "$repo\scripts\cron\refresh_weekly.cmd" `
                                    -WorkingDirectory $repo)
```

Run it once by hand before trusting it:

```powershell
Start-ScheduledTask -TaskName "orca-refresh-daily"
(Get-ScheduledTaskInfo "orca-refresh-daily").LastTaskResult   # 0 = clean, 1 = breach
```

### macOS / Linux: crontab

```cron
# m  h  dom mon dow   command
  30 5  *   *   *     cd ~/orca && scripts/cron/refresh_daily.sh   >> /tmp/orca-daily.log 2>&1
  30 6  *   *   0     cd ~/orca && scripts/cron/refresh_weekly.sh  >> /tmp/orca-weekly.log 2>&1
  0  7  1   *   *     cd ~/orca && backend/.venv/bin/python scripts/refresh_fishing_ban_order.py >> /tmp/orca-ban.log 2>&1
```

`scripts/cron/refresh_daily.sh` and `refresh_weekly.sh` are the same lists with
`backend/.venv/bin/python`. Neither uses `set -e` on purpose: one provider being down should not
skip the other five refreshes, and the freshness report at the end is what sets the exit code.
`cron` does not run missed jobs after a sleep; `anacron` or a `systemd` timer with
`Persistent=true` does, if that matters on your machine.

### Why 05:30 IST

INCOIS and MOSDAC publish **in arrears** — the newest run available on any given morning is
usually yesterday's. 05:30 IST (00:00 UTC) is after their overnight cycle and before anyone
starts work, so the first person at the machine already has the freshest copy that exists.
This is the same provider lag recorded in `PUBLICATION_LAG_MINUTES` in `freshness.py`, which
is why a DAILY source reading 1.8–2.0 days old is still `ok`.

MOSDAC runs last in the daily job on purpose: its scatterometer granules are 54 MB over a link
that drops mid-transfer, and it retries with resume, so it is by far the longest step. Putting
it last means the fast, demo-critical refreshes have already finished if you interrupt it.

---

## 4. Checking it is actually working

```bash
cd backend && .venv/Scripts/python.exe -m orca.data.freshness
```

`0 breach(es)` means the schedule is holding. If you see a breach, the question is not "what
is wrong with the data" but **"did the job run at all"**:

1. Windows: Task Scheduler → History tab, and `LastTaskResult`. `0x1` is our own breach exit,
   anything else (`0x2`, `0x41303`) means the task never got as far as our code — usually a
   wrong working directory or a laptop that was off.
2. Linux/macOS: read the log file the crontab line redirects to.
3. Check the credential the failing source needs is still in `.env`. GFW tokens expire.
4. If the provider genuinely has nothing newer, that is a provider outage. Record it; **do not
   widen the class window** to make the line go green. Threshold changes are a contract
   decision, made once, in writing, with a reason.

One warning worth repeating from the manual guide: `UNOBSERVED STATIC incois_erddap 0 file(s)`
is the **correct** output, not something for the scheduler to fix.

---

## 5. What this is not

This is a per-developer local schedule, not CI. There is no GitHub Actions `schedule:` trigger
and there cannot usefully be one — `data/` is gitignored, so a CI runner has nowhere to persist
what it downloads and would start from an empty directory every time.

The wrapper scripts above are deliberately dumb: a list of commands and an exit code. Point
P5.12 (`R-FRESH-4`, `refresh_all.py`) in the DLC implementation plan replaces them with a single
Python entry point that does the same thing with proper logging and per-source failure
reporting. When that lands, the task actions change to call it and the schedule stays as it is.

Refreshing only ever adds files. Once these jobs have been running for a while, `data/` grows —
see `docs/ORCA_Stale_Data_Cleanup.md`, and read its *keep* list before deleting anything.
