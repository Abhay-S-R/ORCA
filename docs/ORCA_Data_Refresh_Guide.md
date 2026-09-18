# ORCA Data Refresh Guide

**Status:** operational. **Audience:** every developer with a clone of this repo.
**Grounded in:** the canonical SIH26176 problem statement (PS-C3 "near real-time", PS-C10
citation requirement), via `docs/ORCA_Data_Freshness_Contract.md`, which is the normative
document. This one is the *procedure*; the contract is the *obligation*. If they disagree,
the contract wins and this file is wrong.
**Companion:** `docs/ORCA_Stale_Data_Cleanup.md` — what to delete once you have refreshed.

---

## 0. What this gets you

A clone has no `data/` — the directory is gitignored, so nothing you pull contains a single
byte of it. Every dataset on your machine got there by a script, and this page is that list
in the order that works.

When you are done, this must print `0 breach(es)`:

```bash
cd backend
.venv/Scripts/python.exe -m orca.data.freshness     # Windows
.venv/bin/python -m orca.data.freshness             # macOS / Linux
```

That is the whole verification. It exits 0 when clean and 1 when anything is in breach, so it
also works as a CI or pre-demo gate. Skip to §4 for what its output means.

---

## 1. Before you start: credentials

Four providers need an account. **None of them requires you to click through a portal** —
each script reads the project `.env` and runs unattended. Copy `.env.example` to `.env` and
fill in these six keys:

```
COPERNICUS_USERNAME=...      # https://data.marine.copernicus.eu/register  — instant
COPERNICUS_PASSWORD=...
GFW_API_KEY=...              # https://globalfishingwatch.org/our-apis/tokens — instant,
                             #   tick the Vessels API + 4Wings scopes
MOSDAC_USERNAME=...          # https://www.mosdac.gov.in/ — APPROVAL IS MANUAL, allow days
MOSDAC_PASSWORD=...
STORMGLASS_API_KEY=...        # https://stormglass.io/ — instant, free tier is enough.
                              #   Needed by refresh_tide_tables.py: Survey of India sells
                              #   its tide tables as a priced volume, so the predictions are
                              #   computed from Stormglass harmonics and shifted onto each
                              #   station's chart datum.
```

**Register for MOSDAC first, today, before you need it.** SAC approves accounts by hand and it
can take several days. Everything else in this guide is instant or public.

`.env` is gitignored. Do not paste a token into a script, a doc, or a commit message; the
scripts read the real environment first and the file second, so CI can inject secrets without
one existing.

Repeated MOSDAC auth failures lock the account, which is why `refresh_mosdac.py` stops on a
401 rather than retrying it.

---

## 2. The refresh, in dependency order

Run from the repo root. The order matters where a later script consumes an earlier one's
output — those are marked. Everything else is independent and can be run alone. `python` below
means the backend venv's interpreter (`backend/.venv/Scripts/python.exe` on Windows) — the
system one does not have `requests`, `copernicusmarine` or `python-dotenv`.

```bash
# --- forecasts, and the two things derived from them ---
python scripts/refresh_osf_forecasts.py        # INCOIS WW3 / HYCOM / OSF SST
python scripts/extract_osf_pilot.py            # <- consumes the WW3 run above
python backend/scripts/generate_tiles.py       # <- rebuilds the wave tile pyramid

# --- tides, fishing zones, weather ---
python scripts/refresh_tide_tables.py          # tide tables + the 14-station roster
python scripts/scrape_pfz_advisories.py        # INCOIS PFZ sector advisories
python backend/scripts/build_all_india_pfz.py  # <- consumes the advisories above
python scripts/refresh_openmeteo_caches.py
python scripts/refresh_era5_baselines.py       # ERA5 reference period, 104 ports
python scripts/refresh_fishing_ban_order.py

# --- satellite and vessel products ---
python scripts/refresh_nasa_ocean_color.py     # NASA CMR granule listing (public)
python scripts/refresh_bhuvan_manifest.py      # ISRO Bhuvan WMS layers (public)
python scripts/refresh_cmems.py                # needs COPERNICUS_* in .env
python scripts/refresh_gfw_ais.py              # needs GFW_API_KEY in .env
python scripts/refresh_mosdac.py               # needs MOSDAC_* in .env
```

Three things worth knowing before you watch it run:

**MOSDAC is slow and that is normal.** The scatterometer wind granules are 54 MB each over a
link that drops mid-transfer. The script resumes from a `.part` file with an HTTP `Range`
request and retries eight times, so a granule crawls forward across attempts instead of
restarting from zero. Let it finish. If it prints `[STOP] daily limit`, you have hit the
provider's 5,000-files-per-day cap — resume tomorrow, nothing is lost.

**A "no new data" result is not a failure.** INCOIS and MOSDAC publish in arrears: on any given
day the newest run available is usually yesterday's or the day before's. The contract accounts
for this (see §4), so a source sitting at a two-day-old content date is still `ok`.

**The tide job is rate-limited and knows it.** Stormglass's free tier is 10 requests a day and
there are 14 ports, so the script only refetches a station whose cache no longer reaches 3 days
ahead. On a cold clone that means two runs on two days to fill every port; `HTTP 402 … daily
quota reached` is the expected way the first run ends, and nothing already written is lost.

**Nothing here refreshes the LIVE sources.** Five of them — Open-Meteo, Damini lightning, NDMA
SACHET, the INCOIS hazard bulletins and the IOC tide gauges — are fetched over HTTP on every
query and have no refresh step at all. They need a working internet connection, not a download.

---

## 3. Sources with no refresh script

Some datasets are one-time downloads on a multi-year cycle, not an operational task. If your
`data/` is missing one of these, fetch it once and forget it:

| Source | How |
|---|---|
| GEBCO bathymetry | `python scripts/download_gebco_bathymetry.py` |
| Marine protected areas | `python scripts/build_mpa_geofence.py` |
| Coast Guard SAR stations | `python scripts/scrape_icg_sar_stations.py` |
| CMFRI state landings | `python scripts/extract_cmfri_state_landings.py` |
| PFZ fallback grid | `python scripts/build_pfz_fallback.py` |

These are classed STATIC. They will never show as a breach, however old they are, because they
describe geometry and gazetteers rather than conditions.

---

## 4. Verifying, and reading the output

```bash
cd backend && .venv/Scripts/python.exe -m orca.data.freshness
```

It runs the module's self-checks, then prints one line per declared source, worst first:

```
ok         DAILY  incois_osf_ww3           1.9d  2026-09-17       3 file(s)
ok         LIVE   incois_tide_gauge        live  -                1 file(s)
UNOBSERVED STATIC incois_erddap               -  -                0 file(s)

27 sources | 0 breach(es) | live violations: none
```

| Column | Meaning |
|---|---|
| status | `ok`, `BREACH`, or `UNOBSERVED` (nothing on disk to measure) |
| class | LIVE / DAILY / WEEKLY / STATIC — the obligation, defined in the contract §3 |
| age | age of the **content**, not of the file. `live` means it is fetched per query |
| content date | the date the data *describes*, parsed out of the filename where possible |

**Age is measured on content, not on `mtime`,** because "we downloaded this an hour ago" is not
"this describes an hour ago". A Copernicus granule fetched this morning can hold 2023 data.
That distinction is the entire reason this system exists — see the contract §1.

### What to expect after a clean refresh

- **`0 breach(es)`** and **`live violations: none`**. Anything else is a real problem.
- **`UNOBSERVED STATIC incois_erddap  0 file(s)` is correct** and is the one line that will not
  say `ok`. INCOIS's ERDDAP server is a closed historical archive — its SST ends in 2011 — so
  ORCA keeps no copy of it. Reporting it as unobserved is honest; reporting it as fresh would
  not be. Do not "fix" this by downloading something.
- **DAILY sources reading 1.8–2.0 days are fine.** `PUBLICATION_LAG_MINUTES` in `freshness.py`
  records how far behind the *provider's* newest cycle runs — 24 h for the INCOIS forecasts and
  MOSDAC SST, measured rather than guessed. The class window is unchanged; we simply stopped
  counting the publisher's lag against ourselves. If one of these does breach, either the
  provider is more than a day further behind than usual, or your refresh did not actually run.

### If you see a BREACH

1. Re-run that source's script from §2 and read its output — it says why it stopped.
2. Check the credential it needs is in `.env` and has not expired (GFW tokens do).
3. If the provider genuinely has nothing newer, that is a provider outage, not a bug in your
   clone. Record it; do not widen the class window to make the line go green. Whether a
   threshold moves is a decision for the contract — made once, in writing, with a reason.

---

## 5. Keeping it fresh without having to remember

There is no `schedule:` trigger in CI, and there cannot usefully be one: `data/` is gitignored,
so a CI run has nowhere to persist what it downloads. The realistic answer is a local scheduled
task — Task Scheduler on Windows, `cron` elsewhere. **`docs/ORCA_Data_Refresh_Cron_Guide.md`
sets that up**: which of the 27 sources actually need a timer (11 do), the two jobs that cover
them, and the wrapper scripts. Beyond it lies point
P5.12 (`R-FRESH-4`, `refresh_all.py`) in the DLC implementation plan; the command list above is
deliberately written in the order that script should use, so whoever picks that point is
transcribing a known-good sequence rather than rediscovering it.

Until then: run §2 the morning of any demo, then §4. Two commands, and you will know rather
than hope.

---

## 6. After refreshing: clean up

Refreshing adds; it does not remove. Superseded granules stay on disk and `data/` grows past
20 GB. `docs/ORCA_Stale_Data_Cleanup.md` lists exactly what is safe to delete, what is not,
and why.

**Read it before deleting anything.** The careful half of that document is the *keep* list: a
naive "delete anything older than N days" sweep destroys the PFZ history series, the 2018
Cyclone Gaja replay data and the ERA5 climatological baseline — all of which are supposed to be
old. And the single biggest file in `data/`, at 10.58 GB, is one you must not delete yet.
