# ORCA Data Freshness Contract

**Status:** normative. **Owner:** whoever touches `data/` or `orca/data/freshness.py`.
**Grounded in:** the canonical SIH26176 problem statement (PS-C10 citation requirement, PS-C3 "near real-time"),
`docs/ORCA_DLC_Extension_Pack.md` §7.4 (`R-FRESH-1..5`).
**Implemented by:** `backend/orca/data/freshness.py`. **Observed on:** 2026-09-19 — every declared
source is within its class and `live_contract_violations()` is empty. Refresh runs are recorded
in §6.1; the last four breaches closed in §6.2b.

Change this document and `SOURCE_CLASS` in `freshness.py` together. They are the same
decision written twice — once for people, once for the machine.

---

## 1. Why this document exists

On 2026-09-18 the running site showed a wind vector field dated **2026-08-27**, a PFZ
advisory reading **"VALID UNTIL 2026-09-02"**, and a `/data` page promising every source was
*"refreshed roughly every 3 h / 6 h / 15 min"*. All three were on the same laptop, on the
same day, and none of them were lying deliberately. They were three symptoms of one
mistake repeated in three places: **treating the existence of a file as evidence of its
freshness**, and **printing the provider's publication cadence as if it were ours**.

Two different facts were being conflated:

| Fact | Whose fact | Where it lives |
|---|---|---|
| "INCOIS republishes the Ocean State Forecast every 6 h" | **theirs** | `typical_freshness_minutes` in `agents/discovery.py` |
| "the OSF bytes ORCA would serve you right now are 3.6 days old" | **ours** | `orca/data/freshness.py`, measured per call |

`/data` rendered only the first and captioned it in a way that read as the second. A judge
reading "refreshed every 6 h" next to a 22-day-old field is entitled to conclude the whole
provenance story is decorative. That is the risk this contract removes.

---

## 2. The four classes

A class is an **obligation**, not a description. It is the answer to "how wrong is a
decision made on our copy of this?"

| Class | Max age of the bytes we serve | The obligation | Failure mode if breached |
|---|---|---|---|
| **LIVE** | 0 — must be fetched over HTTP *during the query* | A disk copy is a labelled fallback, never the answer | Someone sails into a squall that our cache predates |
| **DAILY** | 24 h | Must carry **today's** date; a job runs daily | Advice degrades — yesterday's PFZ is a worse fishing bet, not a fatal one |
| **WEEKLY** | 7 days | May lag a week; refreshed on a weekly job | Chlorophyll from last Tuesday is scientifically fine |
| **STATIC** | none | No refresh obligation at all | None. Re-procurement is a multi-year decision, not an ops task |

Encoded in `freshness.py`:

```python
MAX_AGE_MINUTES = {"LIVE": 0, "DAILY": 24*60, "WEEKLY": 7*24*60, "STATIC": None}
```

`STATIC` maps to `None` rather than a huge number on purpose: asking "what is the maximum
age of a STATIC source" is a bug at the call site, so `max_age_minutes("STATIC")` raises
`ValueError` instead of quietly handing back infinity.

**The test that decides the class** — apply in order, stop at the first yes:

1. Would a decision made on **yesterday's** copy be *unsafe*? → **LIVE**.
2. Does the provider publish on a **daily cycle**, and does the physical signal change
   meaningfully day to day? → **DAILY**.
3. Does the **physical signal move slower than the publication cycle** (the data is
   published often, but last week's value is still substantially correct)? → **WEEKLY**.
4. Is it **geometry, a gazetteer, or a regulation** — something that changes when a
   committee meets, not when the weather does? → **STATIC**.

Note what the test is *not*: it is not "how often does the provider publish." Scatterometer
wind publishes daily and is classed WEEKLY, because a 10 m wind context layer does not
become dangerous at 30 hours old — whereas the lightning nowcast, which also publishes
frequently, is LIVE because it does.

---

## 3. Per-dataset justification

One row per id in `SOURCE_CLASS`. **Observed** columns are the measured state on
2026-09-18, from `observe_all()`.

### 3.1 LIVE

| Source id | Dataset | Why LIVE | Observed 2026-09-18 |
|---|---|---|---|
| `open_meteo_marine` | Open-Meteo marine + weather | The wave height and wind that produce the sail / no-sail verdict. This is the single number a fisherman bets a boat on; a cached one is a guess about the past. | OK — fetched live per query; 208 cached files as fallback, newest 09-16 |
| `damini_lightning` | IMD Damini lightning nowcast | A lightning nowcast has a useful life measured in tens of minutes. Serving a cached one is worse than serving nothing, because it looks authoritative. | OK — fetched live; 104 cached nowcasts |
| `ndma_sachet` | NDMA SACHET CAP alerts | Statutory alerts (cyclone, tsunami). An alert issued after our last fetch is precisely the alert that matters. | OK — fetched live |
| `incois_hazard_osf` | INCOIS hazard bulletins / IMD nowcast | Same reasoning as SACHET — it feeds the risk cascade. | OK — fetched live since 2026-09-19 from INCOIS's own public multi-hazard endpoints (`hwassalatestdata` + `currentslatestdata`), the ones behind incois.gov.in/site/services/Alerts.html. SACHET stays the fallback |
| `incois_tide_gauge` | INCOIS real-time tide gauge telemetry | A *gauge* is an instrument reading. "The observed water level at Chennai" with a 15-day-old timestamp is not a degraded reading, it is a false one. | OK — fetched live since 2026-09-19 from the IOC/UNESCO Sea Level Monitoring feed, which carries the Indian gauges INCOIS's own 404-ing TEWS endpoint does not. Out of gauge range it falls to altimetry, never to the old fixture |
| `gdacs_tc` | GDACS tropical-cyclone track and cone (EU JRC; JTWC forecast) | A cyclone's position and forecast cone move every six hours; yesterday's track draws the storm where it no longer is. Map layer only — the verdict's cyclone level stays SACHET's. | OK — fetched live since 2026-09-19 (`get_cyclone_tracks`, P5.30); the last good fetch is the fallback, served with its own timestamp |

### 3.2 DAILY

| Source id | Dataset | Why DAILY | Observed 2026-09-18 |
|---|---|---|---|
| `incois_pfz` | INCOIS Potential Fishing Zone advisories | INCOIS issues these **once per day** and stamps each with an explicit `valid_for`. An expired advisory is not conservative — it points a boat at yesterday's fish. Not LIVE because the upstream does not change intra-day; a daily fetch captures everything there is. | OK — 777 features, `valid_for` **2026-09-19** (advisories are forward-looking) |
| `incois_osf_ww3` | WAVEWATCH III significant wave height | A **forecast** product: each run projects 56 × 3-hourly steps forward. The run itself is daily, and a run whose horizon has already elapsed is not a forecast at all. | `rsmc_combined_ww3_20260917.nc` — the newest run INCOIS has published. Reads 1.6 d, see §6.2 |
| `incois_osf_hycom` | HYCOM surface currents | Same daily-run forecast structure as WW3; currents drive drift, transit time and fuel. | `RSMC_hycom_20260917.nc`, same as above |
| `soi_tide_tables` | Survey of India tide tables | The published table is annual, but ORCA materialises a **rolling window** (132 rows, 09-18→09-24, 5 chart-datum stations; the other 9 of the 14-station roster are MSL-only and live in the Stormglass caches). The window must always contain today, so the materialisation is a daily job even though the source is not. | OK — window 2026-09-18 → 09-24. **Expires before the 30 Sep submission; must be re-run** |
| `mosdac_open_sst`, `mosdac_nrt_sst` | MOSDAC INSAT-3D SST | SST is a daily L3B product and a real day-to-day signal — a thermal front moves. DAILY rather than LIVE because a satellite pass is itself a daily event; there is no "now" to fetch. | Refreshed 2026-09-18 by `scripts/refresh_mosdac.py`; content **2026-09-17**, 1.7 d. Reads outside the DAILY window only because MOSDAC's newest granule is always dated yesterday — §6.2 |
| ~~`incois_erddap`~~ | INCOIS ERDDAP Data Server | **Reclassified STATIC on 2026-09-18** — see §3.4 and §6.4. It is a historical archive, not a daily server | — |

### 3.3 WEEKLY

| Source id | Dataset | Why WEEKLY | Observed 2026-09-18 |
|---|---|---|---|
| `mosdac_open_chl`, `mosdac_nrt_chl` | MOSDAC ocean colour / chlorophyll | Chlorophyll blooms evolve over **days to weeks**, and optical products are heavily cloud-gapped, so a daily composite is often mostly missing data anyway. Last week's field is scientifically defensible; last week's wave height is not. | Refreshed 2026-09-18 by `scripts/refresh_mosdac.py`; content **2026-09-15**, 3.7 d. Was 172.6 d — the worst breach in the product, now the best-covered source |
| `mosdac_nrt_wind` | Scatterometer 10 m wind | Used as a **context layer** on the map, not as the verdict input (`open_meteo_marine` is). Its role tolerates a week; its swath revisit does not support better. | Refreshed 2026-09-18 by `scripts/refresh_mosdac.py`, newest content date 2026-09-16 (2.7 d). The live stream is 25 km, not the 12 km previously on disk; `wind_vectors()` reads the grid out of the file, so only the vector spacing changes |
| `nasa_ocean_color` | NASA CMR MODIS chlorophyll granules | Cross-check / fallback for MOSDAC chlorophyll; same physical reasoning, and a fallback is by definition not the freshest thing we hold. | OK — newest granule **2026-09-17**, via `scripts/refresh_nasa_ocean_color.py` |
| `copernicus_cmems` | Copernicus Marine (SSH, thetao, chl) | Reanalysis-grade product with an inherent multi-day-to-weeks latency. Demanding daily from it would guarantee a permanent breach of a contract we chose ourselves. | Reports 2.6 d — **see the limitation in §7**; the directory also holds 2023 chlorophyll and 2024-11→2025-04 SSH |
| `gfw_ais` | Global Fishing Watch AIS | Vessel-density context: where fleets generally operate, not where a specific hull is now. Aggregate patterns are weekly-stable. | OK — refreshed 2026-09-18 by `scripts/refresh_gfw_ais.py`, 0.1 d |
| `stormglass_tides` | Stormglass tide API | **Fallback** for `soi_tide_tables`, and a paid, rate-limited API. Classing a rate-limited fallback DAILY would burn quota maintaining a copy we hope never to serve. | OK — 1.8 d |
| `bhuvan_wms` | ISRO Bhuvan WMS layers | A basemap/imagery service. The manifest describes which layers exist, and layers do not appear and disappear daily. | OK — re-scraped 2026-09-18, 4/4 portals reachable, via `scripts/refresh_bhuvan_manifest.py` |

### 3.4 STATIC

All of the following are **geometry, gazetteers, or regulation**. They change when a
committee publishes, not when the weather does, and refreshing them is a procurement
decision on a multi-year cycle. They carry `MAX_AGE_MINUTES = None` and are always
`within_contract`. Their honesty obligation is a **vintage label**, not a refresh —
`boundary_data_vintage()` already reports the oldest contributing source, and
`/api/boundary-provenance` exposes the WDPA site ids and VLIZ MRGIDs behind each polygon
(PS-C10).

| Source id | Dataset | Why STATIC |
|---|---|---|
| `gebco_bathymetry` | GEBCO / ETOPO bathymetry | The seabed. Re-surveyed on a multi-year cycle. |
| `unep_wcmc_wdpa` | UNEP-WCMC marine protected areas | Changes only by government notification. A "stale" MPA boundary is still the legally correct one until a gazette says otherwise. |
| `marineregions_eez` | VLIZ MarineRegions EEZ polygons | Treaty geometry. Changing weekly would be alarming, not desirable. |
| `icg_sar` | Indian Coast Guard SAR station positions | Physical infrastructure — buildings and helipads. |
| `dof_fishing_ban` | Dept. of Fisheries seasonal ban dates | A published annual regulation with fixed dates. The *ban status* is computed live from today's date against those dates; the dates themselves do not move. |
| `datagov_catch` | data.gov.in marine fish landings | Official annual statistics, published with a multi-month lag by design. |
| `icar_cmfri` | ICAR-CMFRI state landings | Same — an annual research statistic. |
| `incois_erddap` | INCOIS ERDDAP Data Server | **Moved here from DAILY on 2026-09-18.** Probing all 17 datasets on `erddap.incois.gov.in` showed every one is a closed historical archive: SST ends **2011-10-04**, chlorophyll **2006-03-21**, TMI **2014**, OceanSat-2 **2020**, ASCAT **2023**, and the newest thing on the server — Argo floats — ends **2025-04-23**. There is no near-real-time product to refresh, so a DAILY obligation was one we could never meet. Read §6.4 before using it for anything. |

---

## 4. How to make each class actually hold

This is the operative half. A class nobody enforces is a comment.

### 4.1 LIVE — enforce by *removing the file path*

A LIVE source is live when the code path that answers a query issues an HTTP request. It is
**not** made live by refreshing a cache more often, and this is the trap: a 5-minute cron
produces a file that is *usually* fresh, which is worse than an obviously stale one because
nobody checks it.

Mechanism:

1. The fetch lives in `agents/weather_intelligence.py` and is called per query. Add the
   source id to `FETCHED_LIVE` in `freshness.py` **only when that is true**.
2. On upstream failure, fall back to the cached file **and label it**:
   `acquisition_date(payload, path)` returns the real timestamp, which the frontend renders
   instead of "now". A labelled old value is useful; an unlabelled one is fabricated
   (R-NEW-9).
3. `live_contract_violations()` returns every id classed LIVE that is absent from
   `FETCHED_LIVE`. It is asserted in the `freshness.py` self-check and is the intended
   assertion for `scripts/verify_ci_guards.py` once the list is empty.

```
$ python -m orca.data.freshness
freshness self-check OK     # fails loudly if a LIVE source stops being fetched
```

### 4.2 DAILY — enforce by *expiring the cache*, then by a scheduled job

Two independent mechanisms, and the order matters: **expiry first**. Expiry is what makes a
missed refresh *visible*; the scheduler is what makes it *rare*. Shipping only the
scheduler is how we got here.

1. **Expiry.** Every derived cache read goes through
   `read_json_if_fresh(path, max_age_minutes("DAILY"))`, which returns `None` past the
   window and triggers a rebuild. Never `if path.exists(): return json.load(path)`.
2. **Preference by freshness, not existence.** Where two files could answer, compare their
   content dates. `load_pfz_live_geojson()` now compares `valid_for` across the national and
   live advisory files rather than preferring the national one because it is bigger.
3. **A scheduled job.** `scripts/refresh_all.py` (plan point P5.12) runs every daily fetcher
   and writes a manifest. `.github/workflows/ci.yml` currently has **no `schedule:` trigger
   anywhere** — nothing in this repository refreshes automatically today. Adding one is the
   single highest-leverage fix in this document.
4. **Fail the build, not the query.** Before a demo, `refresh_all.py --check` should exit
   non-zero if any DAILY source is outside its window.

### 4.3 WEEKLY — same mechanism, wider window, plus honesty in the label

Identical to DAILY with `max_age_minutes("WEEKLY")`. The additional obligation is
**presentational**: a WEEKLY layer must render its acquisition date on the map, because
seven days is long enough for a user to be wrong about what they are looking at.
`/api/wind-vectors` ships `acquisition_date` for exactly this.

Note that rebuilding a derived WEEKLY cache only helps once someone has downloaded a newer
granule — expiry forces the rebuild, the rebuild reads whatever is on disk. Both halves are
needed, and the honest label is what covers the gap between them.

### 4.4 STATIC — enforce by *never claiming a refresh*

The only failure available to a STATIC source is pretending to be fresh. So:

- `/data` renders "static — no refresh due" instead of an age.
- `boundary_data_vintage()` reports the **oldest** contributing source, not the newest, so a
  mixed-vintage answer is described by its weakest part.
- `fallback_chain` is empty and the page says "no live fallback — static reference geometry".

### 4.5 Forecast products — always take the newest run

A forecast has a second, separate failure mode: picking the wrong *run*.
`refresh_osf_forecasts.py` writes `rsmc_combined_ww3_<date>.nc` and leaves the previous file
beside it, so `sorted(glob)[0]` pins the layer to the **oldest** run forever — which is
exactly what happened, for 17 days. Always `[-1]`, and warn when the last frame is already
in the past (R-FRESH-1):

```python
ds = xr.open_dataset(ww3_files[-1], decode_times=False)   # newest run, not [0]
...
if last_frame < datetime.now(timezone.utc):
    print("[WARN] Newest frame is already in the past — run scripts/refresh_osf_forecasts.py")
```

---

## 5. How freshness is measured

`observe_all()` scans the filesystem **on every call**. There is deliberately no
`refresh_manifest.json`: a manifest is one more artefact that can itself go stale and lie,
and `Path.stat()` cannot.

Age is taken from the **content date** where the filename encodes one, and from mtime only
otherwise. mtime records when *we downloaded*, not what the data *describes* — the first run
of this module cheerfully reported `copernicus_cmems` as fresh while it held 2023 data.
Three filename shapes cover everything under `data/`:

```
E06OCML4AC_20260320_25km.nc            -> 2026-03-20
3RIMG_13AUG2026_0015_L3B_SST.h5        -> 2026-08-13   (note: %b does not match "AUG")
cmems_..._2026-08-28-2026-08-29.nc     -> 2026-08-29   (end date, not start)
```

`/api/sources` merges these into every catalogue entry, and `/data` renders the class badge,
the measured age, and `· outside its <CLASS> window` in red when breached. A source we cannot
observe reads **"freshness unverified"** — never as fresh.

---

## 6. Open contract violations

### 6.1 Cleared on 2026-09-18

Everything with an existing refresh script under `scripts/` was run, in dependency order:

```
scripts/refresh_osf_forecasts.py       # WW3 / HYCOM / OSF SST -> 2026-09-17 runs
scripts/extract_osf_pilot.py           # pilot subset, 0 missing values
backend/scripts/generate_tiles.py      # wave pyramid rebuilt off the new run
scripts/refresh_tide_tables.py         # 132 rows, 2026-09-18 -> 09-24; 14-station roster,
                                       #   10 cached (VIZ/PRD/HDA/PBL await tomorrow's quota)
scripts/scrape_pfz_advisories.py       # 11 sectors, 723 nodes, 3 cloud-blocked
backend/scripts/build_all_india_pfz.py # 723 national advisories, all valid_for 09-19
scripts/refresh_openmeteo_caches.py
scripts/refresh_fishing_ban_order.py
scripts/refresh_nasa_ocean_color.py    # NEW — CMR granule listing, newest 2026-09-17
scripts/refresh_bhuvan_manifest.py     # NEW — 4/4 NRSC/SAC portals reachable
scripts/refresh_cmems.py               # NEW — needs COPERNICUS_* in .env
scripts/refresh_gfw_ais.py             # NEW — needs GFW_API_KEY in .env
scripts/refresh_mosdac.py              # NEW — needs MOSDAC_* in .env
```

That is the whole content of `refresh_all.py` (`R-FRESH-4`, P5.12) — written down here so the
person who picks that point is transcribing a known-good order rather than rediscovering it.
Every `NEW` entry was written during this pass because no refresh path existed for it. The first
two are public; the last three read their credentials from the project `.env` and are listed here
rather than held back, because they now run unattended — see §6.3.

### 6.2 Still open

| Violation | Class | Why it is not fixed yet | Fix |
|---|---|---|---|
| `incois_erddap` holds 0 files | STATIC | It is a closed historical archive we keep no copy of; the archive itself is not in breach of anything. Reported as UNOBSERVED rather than fresh, which is the correct answer | Nothing to refresh. Fixed separately in `discovery.py`: it no longer covers `sst` — see §6.4 |
| No `schedule:` trigger in `ci.yml` | all | — | The root cause of every row that has a refresh script. Note `data/` is gitignored, so CI cannot persist a refresh; the realistic answer is a local scheduled task running `refresh_all.py` |

### 6.2b Closed on 2026-09-19

| Was | Class | What closed it |
|---|---|---|
| `incois_hazard_osf` read from a cached file (09-03) | LIVE | INCOIS publishes its own high-wave, swell-surge and ocean-current bulletins as unauthenticated JSON — `sarat.incois.gov.in/incoismobileappdata/rest/incois/hwassalatestdata` and the `currentslatestdata` sibling, the endpoints behind the public multi-hazard map. `get_incois_hazard_alerts()` now reads them and falls back to SACHET only on a transport failure. IMD's nowcast API stays unusable (401, "Your IP needs to be whitelisted") |
| `incois_tide_gauge` read from a cached file (09-03) | LIVE | The cached file was never readings — it is a schema fixture with representative values, written because INCOIS's TEWS endpoint 404s. The IOC/UNESCO Sea Level Monitoring facility carries the Indian gauges live at one-minute resolution, so `tide_gauge_observation()` reads that, and where no gauge is in range it falls to altimetry. The fixture branch is gone: a fabricated instrument reading on a safety path is worse than no reading |
| MOSDAC SST reads 1.8 d; WW3 / HYCOM read 1.8 d | DAILY | Neither was a real breach, and they are no longer reported as one. `PUBLICATION_LAG_MINUTES` in `freshness.py` records how far behind the *provider's* newest cycle runs — 24 h for both, measured by refreshing on 2026-09-19 and finding 2026-09-17 was the newest thing published. The class window is unchanged; what changed is that we no longer count the publisher's lag against ourselves. Slip a further day and it breaches again |


`live_contract_violations()` now returns `[]`, and the self-check in `freshness.py` asserts
exactly that — so the moment a source is classed LIVE without a real fetch behind it, the
module fails to import and this document has to be updated alongside the code.

### 6.3 Credentialed sources — all scripted, none clicked

Three sources sit behind an account. **None of them requires a human to visit a portal.** Each has
a script that loads the project `.env`, so a scheduler can run all three unattended. Register once,
put the credentials in `.env`, and never open the website again.

| Source | `.env` keys | Script | Registration |
|---|---|---|---|
| Copernicus Marine | `COPERNICUS_USERNAME`, `COPERNICUS_PASSWORD` | `scripts/refresh_cmems.py` | <https://data.marine.copernicus.eu/register> — instant |
| Global Fishing Watch | `GFW_API_KEY` | `scripts/refresh_gfw_ais.py` | <https://globalfishingwatch.org/our-apis/tokens> — instant; needs the Vessels API + 4Wings scopes |
| MOSDAC | `MOSDAC_USERNAME`, `MOSDAC_PASSWORD` | `scripts/refresh_mosdac.py` | <https://www.mosdac.gov.in/> — **approval is manual and can take days**, so register before you need the data |

Two notes that cost an afternoon to learn, kept here so nobody pays for them twice.

**MOSDAC is not manual, despite what every guide says.** It is Keycloak-backed, and the OIDC
password grant is closed (`unauthorized_client` — the client is confidential), which is what makes
people conclude it can only be clicked. But it also exposes a plain REST API that the official
`mdapi.py` client drives: `download_api/gettoken` for a bearer token, `apios/datasets.json` for an
OpenSearch listing, `download_api/download?id=<record_id>` for the bytes.
`scripts/refresh_mosdac.py` calls those three directly rather than vendoring 778 lines of
interactive prompts.

**The MOSDAC dataset ids are not guessable from the filenames and are not published as a list.**
They were found by probing the search endpoint — a wrong id answers `500 "Data unavailable for
given parameters"`, a right one answers `200`:

| File on disk | `datasetId` |
|---|---|
| `3RIMG_*_L3B_SST_DLY_*.h5` | `3RIMG_L3B_SST_DLY` |
| `E06OCML4AC_*.nc` | `E06OCM_L4_AC` |
| `E06SCTL4AW_*.nc` | `E06SCT_L4_AWV` — **not** `E06SCT_L4_AW`, which does not exist |

The wind stream now serves 25 km, not the 12 km on disk from an older stream.
`geospatial.wind_vectors()` reads lat/lon out of the file, so the coarser grid loads unchanged —
only the vector field is sparser.

The scatterometer granules are ~54 MB and MOSDAC's connection drops partway through
almost every time. `_download()` therefore keeps the partial `.part` and resumes it with
`Range: bytes=<have>-`; the server answers 206 with a correct `Content-Range` even though it
never advertises `Accept-Ranges`. Without resuming, every attempt restarts at byte zero and
no 54 MB file ever lands — that is exactly what the first run of this script did. The file is
only renamed into place once the byte count matches the full `Content-Length`, so a truncated
granule can never be indexed as fresh.

Provider limits worth knowing before scheduling: 5,000 files/day per user and a per-minute cap
(the script waits out the minute cap and stops on the daily one), and repeated auth failures lock
the account — which is why a 401 aborts rather than retries. Transfers drop mid-file often enough
that the script writes `.part`, checks the byte count against `Content-Length`, and retries three
times; a truncated granule renamed into place would be indexed as fresh and then fail to parse.

### 6.4 Escalation — ORCA currently picks a 2011 archive as its primary SST source

Found on 2026-09-18 while trying to write a refresh script for `incois_erddap`. This is not a
freshness breach; it is a correctness bug, and it is the most serious thing in this document.

- `SOURCE_REGISTRY` advertises `incois_erddap` as `TIER1, typical_freshness_minutes=180`
  (`backend/orca/agents/discovery.py:58`).
- `select_best_source` ranks candidates by `(tier, typical_freshness_minutes)` and takes the
  `min` (`discovery.py:~130`).
- `incois_erddap` covers `"sst"`, is TIER1, and claims 180 min — the lowest of any TIER1 SST
  candidate. So it wins, ahead of MOSDAC. `discovery.py:322` asserts this outcome as correct.
- The server's SST holdings **end 2011-10-04**.

The registry's cadence number is the single input that produced this, and it is simply false.
Three things have to change together, which is why this is written up rather than patched
inside a freshness pass:

1. Correct or remove the `typical_freshness_minutes=180` claim. Note that `0` is *not* the fix —
   this codebase uses `0` for static reference geometry, and `0` sorts first, so it would win
   even harder.
2. Decide whether `incois_erddap` should still declare `"sst"` in `covers` at all. An archive
   ending in 2011 is a legitimate source for climatology and not for a fishing verdict.
3. Update the assertion at `discovery.py:322`, which currently pins the wrong answer in place.

Until that is done, treat any SST provenance chip naming "INCOIS ERDDAP Data Server" as wrong.

---

## 7. Known limitation

`_scan()` takes the **newest** content date across all of a source's files. A directory
holding both a current granule and an ancient one therefore reports as current:
`copernicus_cmems` shows 2.6 days while a 2023 chlorophyll granule and 2024-11→2025-04 SSH
sit in the same folder. This is acceptable for a catalogue-level indicator and wrong for a
per-layer one. The fix, when a layer needs it, is to observe the **specific file a loader
opened** rather than the source's glob — which is why `Observed` keeps `content_date` and
`last_refresh_utc` as separate fields instead of collapsing them into one number.
