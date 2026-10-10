# ORCA — SIH26176 All-India Coverage & Dataset Collection Guide

> **Project:** SIH 2026 · Problem Statement #SIH26176 · ISRO / Marine Ecosystem Reasoning  
> **Purpose:** Complete reference for expanding ORCA from the South Tamil Nadu pilot to full  
> all-India coastal coverage and ensuring every PS benchmark query is answered correctly.  
> **Share this with:** Every teammate working on data collection, backend agents, or testing.

---

## Section 0 — Data Audit: What Already Exists in `data/`

> ⚠️ **Read this before downloading anything.** A lot of data is already on disk.
> The column **ON-DISK STATUS** in every table below tells you what to skip.
>
> **Audit method (2026-09-16 revision):** every row below was re-checked by grepping the working tree
> for the file path and following the call chain to a caller that actually executes at query time.
> "Wired" here means *a reader exists and runs*, not *a doc says it should*. Several rows in the
> original version of this guide were wrong in both directions — see §0.1.
>
> **2026-09-16:** the "⚙️ on disk, zero readers" table is now **empty**. Every distinct dataset in
> `data/` has a reader that executes, verified by call-chain grep and by 382 passing backend tests.
> A loader existing is not wiring — §0.1b records the six loaders that were written in commit
> `7ed9329` with **no caller at all**, and where each one is now called from.

### Legend used throughout this document
| Icon | Meaning |
|------|---------|
| ✅ ON DISK + WIRED | File exists AND the backend reads it — works today |
| ⚙️ ON DISK, NOT WIRED | File exists on disk BUT no code reads it — needs a code change, not a download |
| ❌ MISSING | File does not exist — must be downloaded or generated |
| 🔴 LIVE API | No file needed — fetched live at query time |
| ⏳ EXPIRED | File exists and is wired, but its validity window has passed — see §8 |

### 0.1 Corrections to the previous revision of this guide

The first version of this document marked wiring status from the plan documents rather than from the
code. Five marks were wrong. Do not carry them forward.

| # | Previous claim | Verified reality | Where |
|---|---|---|---|
| A-1 | HYCOM `RSMC_hycom_20260830.nc` (9.9 GB) — "⚙️ not wired" | **Wired.** `geospatial.py:305-350` opens it and `current_vectors()` serves `/api/currents`, pan-India bbox by default | `agents/geospatial.py` |
| A-2 | WW3 `rsmc_combined_ww3_20260829.nc` (6.5 GB) — "⚙️ not wired" | **Wired.** `voyage.py:57-82` opens the newest WW3 file and samples Hs at each leg's ETA | `agents/voyage.py` |
| A-3 | EOS-06 ScatSat wind `.nc` (2.3 GB) — "⚙️ not wired" | **Wired.** `geospatial.py:353-410` `wind_vectors()` serves `/api/wind-vectors` | `agents/geospatial.py` |
| A-4 | "All 11 PFZ Sectors" | INCOIS publishes **14** sectors (SEC001–SEC014), and the on-disk status file carries all 14. The 11-row table was wrong about both the count and the region mapping — the same defect §0 C-5 of `data_verification_audit.md` already fixed once | `data/incois_osf_pfz/pfz/pfz_sector_status.json` |
| A-5 | INSAT-3D SST `.h5` / EOS-06 chlorophyll `.nc` — "⚙️ not wired, needs a loader" | Correct, but understated. The consuming function `correlate_sst_chlorophyll()` does not read these files *at all*; it reads `data/fixtures/mosdac_{sst,chl}__pilot__*.json`, **a directory that does not exist**, and therefore returns `available: False` on every call in the product's life | `agents/ocean_analytics.py:235-250`, `data/analytics_loaders.py:188-202` |

### 0.1b Second-pass corrections (2026-09-16) — "a loader exists" is not "it is wired"

Commit `7ed9329` ("half work done on dataset") added real, correct loaders for most of the ⚙️ rows
below and wired three of them. Six were left with **zero callers**, which on the running system is
indistinguishable from not having been written: the file was still never read at query time. This
revision closes that gap. Each row names the caller that now executes.

| Loader (written, previously uncalled) | Now called from | What it makes answerable |
|---|---|---|
| `analytics_loaders.load_era5_baseline` | `ocean_analytics.wind_anomaly` → agent `run()` outputs **and** `GET /api/trends` | PS-Q7's word "anomaly" finally has a reference period. `detect_anomaly` took a baseline mean/σ no caller could supply |
| `analytics_loaders.load_imd_nowcast_alerts` | `weather_intelligence.get_imd_nowcast_alerts` → agent `run()` outputs | PS-Q4 gains a genuinely IMD-sourced second hazard source next to the Open-Meteo proxy, plus a `lightning_source_agreement` field (`agree` / `disagree` / `single_source`) |
| `analytics_loaders.load_osf_point_forecasts` | `ocean_analytics.nearest_osf_point_forecast`, and `voyage._ww3_point_fallback` | PS-Q2/Q3/Q6 answer per-point wave + current without opening the 16 GB NetCDF pair, and a checkout without those files no longer crashes voyage planning |
| `analytics_loaders.load_nasa_chl_granules` | `discovery.local_catalog("nasa_ocean_color")` → `GET /api/sources` | The `nasa_ocean_color` cascade rung can now be *shown*. Every entry carries `held_locally: false` — this file is an index of granules, not chlorophyll |
| `analytics_loaders.load_bhuvan_wms_services` | `discovery.local_catalog("bhuvan_wms")` → `GET /api/sources` — **catalog only, deliberately not a map layer** | See the warning below: the manifest's layer names do not exist upstream, so all four services are surfaced as a source catalog and none is rendered |
| `analytics_loaders.load_boundary_provenance` | `GET /api/boundary-provenance` *(endpoint only — no frontend consumer yet)* | PS-C10 citations. 15 audited WDPA records + 2 VLIZ EEZ gazetteer entries (MRGID + citation) are now reachable by the citation panel, not just their timestamp |

Three further datasets the previous revision dismissed are also wired, because each was cheaper than
the sentence explaining why it was skipped:

| Dataset | Now called from | Note |
|---|---|---|
| `incois_osf_pfz/south_india_marine_grid.csv` (400 cells) | `ocean_analytics.nearest_osf_point_forecast` second rung | Covers south India at 0.5° where the 8 point extractions do not. Returns `LOW_DATA` and labels itself a grid cell, never a position-accurate reading |
| `incois_osf_pfz/dataset_manifest.json` | `discovery.local_catalog("incois_osf_ww3" / "incois_osf_hycom" / "incois_pfz")` | Carries the **CC-BY 4.0 (INCOIS/MoES) licence**, recorded nowhere else in the repo |
| `tier2/gfw/gfw_vessels_search_sample.json` | `discovery.local_catalog("gfw_ais")` | Identity records only, no positions. Surfaced as a catalog so the `gfw_ais` registry entry is not a name with nothing behind it. AIS presence stays out of scope |

One row in the 09-13 ✅ ledger was itself wrong in the same way the ⚙️ rows were: the
`incois_tide_gauge_telemetry.json` entry cited `analytics_loaders.py:65`, which is the loader's own
`def` line, not a caller. Nothing read it. It is now called by `ocean_analytics.tide_gauge_observation`,
which reports observed sea level against the gauge's own astronomical prediction and carries INCOIS's
`tsunami_trigger_state` through verbatim — ORCA does not threshold or interpret that field, because a
tsunami determination is INCOIS's to make. This is the lesson of this pass restated: **cite the caller,
never the definition.** A line number inside the loader file proves nothing.

> ⚠️ **The Bhuvan marine manifest is not a verified service description — do not build a map layer from it.**
> Checked against the endpoint's own GetCapabilities on 2026-09-16. All four layer names it lists
> (`india_coastal_boundary`, `india_states`, `major_ports`, `inshore_waterways`) return
> **`400 Unknown layer`**. The server does host 5,136 real layers, but they are land-use, cadastral and
> urban-mapping products (`sisdp`/`nuis`/`mmi`/`sdv`); searching them for *coast, shore, marine, ocean,
> port, coral, mangrove, bathymetry, sea* returns **zero** hits, and `bhuvan-app1` / `bhuvan-ras2` 404
> on GetCapabilities entirely. Two of the manifest's other entries are human-facing portal pages, not
> OGC endpoints.
>
> A first attempt did ship this as a map layer. It failed in the browser on **CORS** — NRSC sends no
> `Access-Control-Allow-Origin` — which looked like a plumbing problem and is not: a same-origin proxy
> was written, and the upstream then answered `400 Unknown layer`. The CORS error was masking bad data.
> The layer and the proxy were both removed. **Re-add a Bhuvan map layer only after a GetCapabilities
> response names a real marine layer** — and keep the proxy in mind when you do, because the CORS
> constraint is real and will still apply.

`backend/scripts/build_all_india_pfz.py` has now been **run**: `all_india_pfz_advisories.geojson`
exists and `load_pfz_live_geojson()` prefers it, so `/zones` renders national PFZ coverage instead of
the pilot box.

> **Corrected 2026-09-19 — the "13 of 14 sectors" in this paragraph was never true.** The builder
> appended 54 *invented* advisory points (Gujarat, Odisha, West Bengal, Andaman, and nine extra South
> Tamil Nadu nodes) with hardcoded coordinates, bearings, depths and `mean_sst_c` values, each stamped
> `"source": "INCOIS Marine Fisheries Advisory"` and `"valid_for": "2026-09-02"`. Two of the sectors it
> appeared to add — SEC001 Gujarat and SEC012 Andaman — had *only* fabricated points. The node lists are
> deleted. The file now carries **723 real advisories across 11 sectors, all valid for the same day**,
> and the three sectors INCOIS did not publish are reported by `sector_status()` as data gaps carrying
> INCOIS's own cloud-cover message. National coverage is what INCOIS publishes, not what we fill in.

### 0.1c Frontend wiring — a field in a response nobody renders is still invisible

Backend wiring does not put anything on screen. Each newly-wired field was checked against the
frontend; these now have a consumer:

| Field | Surface | What the user sees |
|---|---|---|
| `sst_chlorophyll_correlation` | `/trends` | Already wired; the panel flips from the "Awaiting the gridded ocean series" empty state to a real Pearson r (−0.245, weak inverse) over 95 co-located cells |
| `wind_anomaly` | `/trends` — new panel | Observed peak vs ERA5 mean ±σ, z-score, and an anomalous/normal badge. Off a coast with no cached baseline it states that instead of implying "normal" |
| `observed_cross_check` | `/voyage` berthing panel | Observed vs predicted tide height, the sea-level anomaly between them, and INCOIS's `tsunami_trigger_state` verbatim. No gauge in range renders as a one-line statement, not a blank |
| `imd_nowcast`, `lightning_source_agreement` | `/safety` | An "IMD nowcast" readout (district count, or "snapshot window closed"), plus a *sources disagree* banner that appears only on genuine disagreement — the verdict is still computed from the Open-Meteo proxy alone, and the banner says so |
| `all_india_pfz_advisories.geojson`, `sector_for_point` | `/zones`, map PFZ layer | 407 advisories across 13 sectors; asking from Goa returns SEC003 / GOA |

Still endpoint-only, with no frontend consumer: `/api/boundary-provenance`, `local_catalog` on
`/api/sources`, and `osf_point_forecast`. They are reachable and correct; nothing renders them yet.

### 0.2 Verified wiring ledger — every file on disk

`data/` holds **25,679 files / 19 GB**, of which ~25,000 are pre-rendered map tiles. The table below
covers every *distinct dataset*, not every file.

#### ✅ Wired — a reader exists and runs

| Dataset / path | Reader (file:function) | Serves |
|---|---|---|
| `tier1/weather/openmeteo_weather_*.json` (6 ports) | `weather_intelligence.py:136`, `loaders.py:64 port_coordinates`, `ocean_analytics.py:470 wind_rose` | PS-Q2, PS-Q3 — offline fallback + the coordinate table the whole gazetteer is built on |
| `tier1/ocean/openmeteo_marine_*.json` (5 ports) | `weather_intelligence.py:135` | PS-Q2 wave/swell fallback |
| `tier1/hazards/lightning_nowcast_*.json` (5 ports) | `weather_intelligence.py:255` | PS-Q4 lightning fallback |
| `tier1/hazards/ndma_cap_alerts.json` | `weather_intelligence.py:290` | PS-Q4 cyclone/CAP fallback when SACHET is unreachable |
| `tier1/tides/soi_tide_tables_2026.csv` | `analytics_loaders.py:38` | PS-Q3 tide predictions |
| `tier1/tides/soi_tide_stations_metadata.json` | `analytics_loaders.py:32`, `loaders.py:114` | Tide datums **and** the tide-station tier of the place gazetteer. Written by `scripts/refresh_tide_tables.py` from 2026-09-19 (14 stations); before that it was hand-maintained inside gitignored `data/`, so no clone but the original author's had it |
| `tier1/tides/incois_tide_gauge_telemetry.json` | `analytics_loaders.load_tide_gauge_telemetry` → `ocean_analytics.tide_gauge_observation` → agent `run()` + `GET /api/tides` | PS-Q3 observed-vs-predicted cross-check. **Was mis-marked wired in the 09-13 ledger** — the loader existed, nothing called it. Fixed 2026-09-16 |
| `tier2/stormglass/stormglass_tides_*.json` (10 of 14 ports; VIZ, PRD, HDA, PBL pending quota) | `analytics_loaders._stormglass_stem`, `ocean_analytics.py:137` | PS-Q3 tide fallback (MSL datum — not interchangeable with chart datum), and the **only** source at the 9 ports with no published chart-datum offset. The station→file mapping is read from the metadata now; it used to be a second hardcoded dict that would have silently excluded every added port |
| `tier1/fisheries/datagov_marine_fish_landings.csv` | `analytics_loaders.py:174`, `ocean_analytics.py:538` | PS-Q7 productivity diagnosis |
| `incois_osf_pfz/pfz/incois_pfz_live_advisories_master.csv` | `analytics_loaders.py:153`, `ocean_analytics.py:309 nearest_pfz` | PS-Q1 nearest PFZ |
| `incois_osf_pfz/pfz/pfz_sector_status.json` | `analytics_loaders.py:140`, `ocean_analytics.py:389` | PS-Q1 cloud-cover honesty, `/zones` |
| `incois_osf_pfz/pfz/history/<date>/advisories.csv` | `analytics_loaders.py:131`, `ocean_analytics.py:342 score_pfz_persistence` | PS-Q1 persistence. 3 dates on disk (0901, 0916, 0918); the daily cron adds one per morning. Since 2026-09-19 the score counts only snapshots from the **last 7 days** and refuses to label anything below 5 of them — a fortnight-old advisory is not evidence about this week |
| `incois_osf_pfz/pfz/incois_pfz_live_advisories.geojson` | `analytics_loaders.py:162` → `analytics_routes.py:173` | `/zones` map layer |
| `incois_osf_pfz/pfz/pfz_fallback_pilot_region.geojson` | `discovery.py:30` (existence check + cascade) | PS-Q1 cloud-suppressed fallback |
| `tier1/boundaries/india_eez_polygon.geojson`, `srilanka_eez_polygon.geojson`, `india_marine_mpas.geojson` | `geospatial.py:32-34 BOUNDARIES_DIR` | PS-Q8, PS-C8 geofencing |
| `tier1/bathymetry/gebco_2026_*.nc`, `etopo_all_india_bathymetry.nc` | `geospatial.py:34-36` | PS-Q6 depth, UKC, `/api/depth` |
| `incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc` (9.9 GB) | `geospatial.py:305 current_vectors` | Current particle layer, `/api/currents` |
| `incois_osf_pfz/osf_ww3/rsmc_combined_ww3_*.nc` (6.5 GB) | `voyage.py:57 wave_height_at` | PS-Q6 per-leg Hs at ETA |
| `tier3/mosdac/Wind/E06SCTL4AW_*.nc` (2.3 GB) | `geospatial.py:353 wind_vectors` | Wind flow-field overlay — **the only ISRO product currently read at runtime** |
| `tier1/vectors/pan_india_currents_v2.json`, `pan_india_wind.json` | `geospatial_routes.py:63,90` | Pre-computed pan-India vector caches |
| `tier1/tiles/bathymetry/**`, `tier1/tiles/wave_height_forecast/**` (224 MB, 25k tiles, 56 frames) | `main.py:128` static mount → `MapView.tsx:161` | Map raster layers |
| `cyclone_gaja/ibtracs_gaja_2018_besttrack.json` + `era5_gaja_*.nc` | `replay/gaja.py:28-29` → `/api/replay/gaja` | Cyclone demo scenario |
| `tier3/mosdac/Sea surface temp/3RIMG_*.h5` (17 files, 152 MB) | `satellite_loaders.load_insat_sst` → `ocean_analytics._sst_grid` → `correlate_sst_chlorophyll` | PS-Q5, PS-Q7 — **ISRO INSAT-3DR SST, the headline gap, now read** (3,514 bins over the India bbox) |
| `tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` (10 files, 60 MB) | `satellite_loaders.load_eos06_chl` → `correlate_sst_chlorophyll` | PS-Q5, PS-Q7 — ISRO EOS-06 OCM-3 chlorophyll (99 cells). Still **March 2026 and stale**, but read and labelled as such |
| `tier2/copernicus/cmems_*.nc` | `satellite_loaders.load_cmems_sst` → `_sst_grid` rung 2 | The declared SST fallback is now a rung that actually exists (783 cells) |
| `tier1/weather/era5_historical_<port>_30d.json` (104 ports since 2026-09-19) | `analytics_loaders.load_era5_baseline` → `ocean_analytics.wind_anomaly` → agent `run()` + `/api/trends` | PS-Q7 anomaly — the reference period `detect_anomaly` always needed |
| `tier1/hazards/imd_nowcast_alerts.json` | `analytics_loaders.load_imd_nowcast_alerts` → `weather_intelligence.get_imd_nowcast_alerts` | PS-Q4 second hazard source + cross-source disagreement signal |
| `osf_hycom/hycom_latest_points.geojson`, `osf_ww3/ww3_latest_points.geojson` | `analytics_loaders.load_osf_point_forecasts` → `ocean_analytics.nearest_osf_point_forecast`, `voyage._ww3_point_fallback` | Per-point wave/current fast path, and the voyage fallback when the 16 GB grids are absent |
| `incois_osf_pfz/south_india_marine_grid.csv` | `analytics_loaders.load_osf_marine_grid` → `nearest_osf_point_forecast` rung 2 | 0.5° regional coverage beyond the 8 extracted ports |
| `incois_osf_pfz/dataset_manifest.json` | `analytics_loaders.load_osf_dataset_manifest` → `discovery.local_catalog` → `/api/sources` | INCOIS CC-BY 4.0 licence + upstream URL patterns, for citations |
| `tier2/nasa/nasa_cmr_modis_chl_granules.json` | `analytics_loaders.load_nasa_chl_granules` → `discovery.local_catalog` | Names the granules the NASA cascade rung would fetch; `held_locally: false` on every row |
| `tier2/gfw/gfw_vessels_search_sample.json` | `analytics_loaders.load_gfw_vessel_sample` → `discovery.local_catalog` | Backs the `gfw_ais` registry entry with visible evidence |
| `tier3/bhuvan/bhuvan_15days_marine_manifest.json` | `analytics_loaders.load_bhuvan_wms_services` → `discovery.local_catalog` | All 4 services in the source catalog. **Not a map layer** — see the warning below |
| `tier1/boundaries/mpa_geofence_provenance.json`, `vliz_*.json` | `analytics_loaders.load_boundary_provenance` → `GET /api/boundary-provenance` | PS-C10 citation evidence — WDPA site ids and VLIZ MRGIDs |
| `incois_osf_pfz/pfz/all_india_pfz_advisories.geojson` (**generated 2026-09-16**) | `analytics_loaders.load_pfz_live_geojson` → `/zones` | 407 features, 13 of 14 sectors — national PFZ coverage |

#### ⚙️ On disk, zero readers — **empty as of 2026-09-16**

Every distinct dataset in `data/` now has a reader that executes at query time. The previous contents
of this table moved into the ✅ ledger above; §0.1b names the caller for each.

Two residual items, neither of which is a wiring gap:

| Item | Status | Why no wiring |
|---|---|---|
| `pfz/pfz_parsed_webgis.json`, `pfz_webgis_links.json`, `pfz_webgis_text.txt`, `*_master.json`, `pfz_fallback_pilot_region.json` | Kept as provenance | Scraper intermediates and JSON twins of files already read as CSV/GeoJSON. Reading them twice would be the defect |
| `tier1/bathymetry/etopo_all_india_real.nc` (12 MB) | **Duplicate confirmed, not deleted** | Verified identical to the wired `etopo_all_india_bathymetry.nc`: same 1561×1981 grid, same 65–98 E / 0–26 N extent, same value range (−5341.51 to 3500.70 m). `_real.nc` is the raw NOAA download (`lat`/`lon` + `crs`); `_bathymetry.nc` is the derived copy with the `altitude` alias that `geospatial.py:35` opens. Safe to delete `_real.nc` — left in place because `data/` is gitignored working data and deletion is the owner's call, not the wiring pass's |

#### ❌ Missing but required by code that already exists

| What | Consequence today |
|---|---|
| ~~`data/fixtures/mosdac_{sst,chl}__pilot__*.json`~~ | **No longer required.** `correlate_sst_chlorophyll()` now reads the ISRO archives directly (INSAT-3DR SST → CMEMS → fixture; EOS-06 chlorophyll → fixture) and returns a real correlation over 95 co-located 0.25° cells. The fixture is the last rung of a cascade, not the only path |
| ~~`incois_osf_pfz/pfz/all_india_pfz_advisories.geojson`~~ | **Generated 2026-09-16.** `backend/scripts/build_all_india_pfz.py` has been run: 407 features, sectors SEC001–SEC012 + SEC014. Re-run it whenever the live advisory file is refreshed |
| Marine/weather/lightning caches for any port outside the 5–6 pilot ports | Every non-pilot location has no offline fallback; a network failure during judging outside Tamil Nadu produces degraded answers |
| ~~SoI tide predictions outside 5 stations (TUT, PAM, CHE, KOC, BOM)~~ | **Closed 2026-09-19.** The roster in `scripts/refresh_tide_tables.py` is now 14 stations — the 5 pilot ports plus Kandla, Okha, Veraval, Mormugao, New Mangalore, Visakhapatnam, Paradip, Haldia and Port Blair — and the script writes `soi_tide_stations_metadata.json` itself, so a fresh clone gets the roster instead of finding an empty gazetteer tier. **The 9 new ports are answered on mean sea level, not chart datum:** nobody publishes a chart-datum offset for them that we can cite, so none was invented and `predict_tides()` serves them through its declared Stormglass rung, which labels the datum and drops confidence to MEDIUM. Times and high/low ordering are right everywhere; the height at the 9 is on a different datum and says so out to the API response |
| CMFRI landings outside 4 districts | PS-Q7 answerable only for Thoothukudi, Ramanathapuram, Ernakulam and Mumbai Coastal |
| India–Pakistan and India–Bangladesh maritime boundaries | PS-C8 names "international maritime boundaries" plural. Gujarat (Sir Creek) and West Bengal have **no IMBL geometry at all** — the two coasts where boundary incidents are most frequent |
| Ecologically sensitive / fishing-ban / restricted-water layers | PS-C8 names these separately from MPAs. Only WDPA MPAs exist, and of 15 features only 11 are geofence-usable — several of which are **Sri Lankan** (Vankalai, Wedithalathive, Bar Reef) |
| All-India MRCC/MRSC station table | `distress.py:67` holds exactly one regional contact (Chennai) plus nationwide 1554. A distress call from Porbandar is routed to Chennai |

---

## Section 1 — The 8 PS Benchmark Queries ORCA Must Answer

These 8 queries are the formal benchmark matrix for SIH26176. Every single one must be
answered for **all Indian coastal regions** — not just Tamil Nadu.

---

### PS #1 · "Where are the best / nearest fishing zones today?"

**What the system must return:**
- Nearest PFZ name, bearing (degrees), distance (nautical miles) from home port
- Historical persistence score (how many days this zone has been active)
- Cloud-cover status (if satellite advisory is suppressed, say so)

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| Daily PFZ Live Advisories | ✅ ON DISK + WIRED | INCOIS OSF | https://osf.incois.gov.in/index.jsp | JSON | `data/incois_osf_pfz/pfz/incois_pfz_live_advisories.geojson` |
| PFZ Historical Archive — 1 date only | ✅ ON DISK + WIRED (`score_pfz_persistence`) — **data gap, not a wiring gap** | INCOIS OSF | Same portal → Archive tab | JSON | `data/incois_osf_pfz/pfz/history/20260901/` ← only 1 date, need ≥7, so persistence is structurally 1/1 |
| PFZ History — 6 more dates needed | ❌ MISSING | INCOIS OSF | https://osf.incois.gov.in → Archive | JSON | `data/incois_osf_pfz/pfz/history/YYYYMMDD/` |
| PFZ Sectors SEC001–SEC005, SEC007–SEC011 | ❌ MISSING | INCOIS OSF | Same portal | JSON | `data/incois_osf_pfz/pfz/` |
| SST — INSAT-3D (17 files, Aug 13–29) | ✅ ON DISK + WIRED (`satellite_loaders.load_insat_sst`) | MOSDAC | https://mosdac.gov.in → INSAT-3D → SST | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/3RIMG_*.h5` |
| SST — Aug–Sep 2026 (fresh) | ❌ MISSING | MOSDAC | Same portal, pick Aug 30 – today | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/` |
| Chlorophyll — EOS-06 (10 files, March 2026) | ✅ ON DISK + WIRED (`satellite_loaders.load_eos06_chl`) ⏳ stale | MOSDAC | https://mosdac.gov.in → EOS-06 → Ocean Colour | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` |
| Chlorophyll — Jul–Sep 2026 (fresh) | ❌ MISSING | MOSDAC | Same portal, pick Jul–Sep 2026 | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/` |
| Chlorophyll backup | ❌ MISSING | NASA OBPG MODIS | https://oceancolor.gsfc.nasa.gov/l3/ | NetCDF | `data/tier2/nasa/` |

**All 14 PFZ sectors — read from `pfz_sector_status.json`, not assumed.**

INCOIS publishes **14** sectors, not 11, and the region mapping below is INCOIS's own. An earlier
version of this table invented an 11-sector map that assigned the wrong coastline from SEC007 onward;
routing on it would have answered Odisha questions with West Bengal data. (Same defect class as §0 C-5
of `data_verification_audit.md`.)

Node counts are from the on-disk snapshot (`valid_for: 2026-09-02`, 353 nodes, lat 8.13–19.71 N,
lon 71.91–84.80 E):

| Sector | Region | Status in snapshot | Nodes |
|--------|--------|---|---|
| SEC001 | Gujarat | NO_DATA_CLOUD_COVER | 0 |
| SEC002 | Maharashtra | HAS_ADVISORY | 89 |
| SEC003 | Goa | HAS_ADVISORY | 7 |
| SEC004 | Karnataka | HAS_ADVISORY | 24 |
| SEC005 | Kerala | HAS_ADVISORY | 100 |
| SEC006 | South Tamil Nadu ← **the pilot sector** | NO_DATA_CLOUD_COVER | 0 |
| SEC007 | North Tamil Nadu | HAS_ADVISORY | 90 |
| SEC008 | South Andhra Pradesh | HAS_ADVISORY | 17 |
| SEC009 | North Andhra Pradesh | HAS_ADVISORY | 17 |
| SEC010 | Odisha | NO_DATA_CLOUD_COVER | 0 |
| SEC011 | West Bengal | NO_DATA_CLOUD_COVER | 0 |
| SEC012 | Andaman | NO_DATA_CLOUD_COVER | 0 |
| SEC013 | Nicobar | NO_DATA_CLOUD_COVER | 0 |
| SEC014 | Lakshadweep | HAS_ADVISORY | 9 |

> **Two things to read off this table.** First, national PFZ coverage is **already on disk** — 8 of 14
> sectors carry live advisories spanning both coasts. The all-India PFZ gap is not a data gap, it is
> the `_PILOT_SECTOR = "SEC006"` hardcode in `ocean_analytics.py:53` (see §9, B-2). Second, the pilot
> sector is cloud-suppressed in the snapshot, which is exactly why the derived fallback exists — and
> why a judge asking "what if the satellite sees nothing?" is a question ORCA can already answer well.

---

### PS #2 · "Is it safe to go to sea today / tomorrow morning?"

**What the system must return:**
- GO / CAUTION / NO-GO verdict (deterministic rule-based, never LLM-generated)
- Wave height (Hs in metres), wind speed (m/s or knots), swell height
- Safe operating window (e.g., "safe until 14:00 IST, deteriorating after")
- Source cited for every number

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| WaveWatch III (WW3) NetCDF | ✅ ON DISK + WIRED (⏳ forecast window expired) | INCOIS OSF | https://osf.incois.gov.in → Wave | NetCDF | `data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` (6.5 GB) — read by `voyage.py:57` |
| WW3 latest point forecasts | ✅ ON DISK + WIRED (`load_osf_point_forecasts`; also `voyage`'s grid-absent fallback) | INCOIS OSF | Same | GeoJSON/CSV | `data/incois_osf_pfz/osf_ww3/ww3_latest_points.geojson` |
| Open-Meteo Marine — chennai, kochi, mumbai, pamban, thoothukudi | ✅ ON DISK + WIRED | Open-Meteo | https://marine-api.open-meteo.com/v1/marine | JSON | `data/tier1/ocean/openmeteo_marine_*.json` |
| Open-Meteo Marine — 16 new ports | ❌ MISSING | Open-Meteo | Same (free, no key) | JSON | `data/tier1/ocean/openmeteo_marine_<port>.json` |
| Open-Meteo Weather — 6 existing ports | ✅ ON DISK + WIRED | Open-Meteo | https://api.open-meteo.com/v1/forecast | JSON | `data/tier1/weather/openmeteo_weather_*.json` |
| Open-Meteo Weather — 16 new ports | ❌ MISSING | Open-Meteo | Same (free, no key) | JSON | `data/tier1/weather/openmeteo_weather_<port>.json` |
| EOS-06 ScatSat Wind (11 daily files) | ✅ ON DISK + WIRED | MOSDAC | https://mosdac.gov.in → EOS-06 → Wind | NetCDF | `data/tier3/mosdac/Wind/E06SCTL4AW_*.nc` (2.3 GB) — read by `geospatial.py:353`. **The only ISRO product read at runtime today** |
| ERA5 historical wind (all 104 cached ports since 2026-09-19, `scripts/refresh_era5_baselines.py`) | ✅ ON DISK + WIRED (`load_era5_baseline` → `wind_anomaly`) | Open-Meteo archive | https://archive-api.open-meteo.com/v1/era5 | JSON | `data/tier1/weather/era5_historical_*_30d.json` |

**Ports that need Open-Meteo files fetched** (existing: chennai, kochi, mumbai, pamban, thoothukudi, visakhapatnam):

```
# West coast additions
kozhikode   → lat=11.25  lon=75.78
mangalore   → lat=12.85  lon=74.65
karwar      → lat=14.80  lon=73.90
goa/mormugao→ lat=15.40  lon=73.50
ratnagiri   → lat=16.99  lon=73.12
alibag      → lat=18.64  lon=72.72
veraval     → lat=20.90  lon=70.37
okha        → lat=22.47  lon=69.05
kandla      → lat=23.03  lon=70.22

# East coast additions
kakinada    → lat=16.93  lon=82.25
machilipatnam→lat=16.17  lon=81.13
paradeep    → lat=20.32  lon=86.62
haldia      → lat=22.03  lon=88.07
digha       → lat=21.63  lon=87.50
port_blair  → lat=11.67  lon=92.75
```

Fetch command template (run once per port, free):
```bash
curl "https://marine-api.open-meteo.com/v1/marine?latitude=LAT&longitude=LON&hourly=wave_height,wave_period,swell_wave_height,ocean_current_velocity,ocean_current_direction&forecast_days=7&timezone=UTC" \
  > data/tier1/ocean/openmeteo_marine_PORTNAME.json

curl "https://api.open-meteo.com/v1/forecast?latitude=LAT&longitude=LON&hourly=wind_speed_10m,wind_gusts_10m&forecast_days=7&timezone=UTC" \
  > data/tier1/weather/openmeteo_weather_PORTNAME.json
```

---

### PS #3 · "What are the tide, weather, and sea conditions near [location]?"

**What the system must return:**
- Next high tide and low tide: time (IST) + height (metres, chart datum)
- Spring vs neap classification
- Sea state: wave height, period, swell
- Surface current speed (m/s) and direction
- Air and sea temperature

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| SoI Tide Tables 2026 (pilot ports) | ✅ ON DISK + WIRED | Survey of India | https://surveyofindia.gov.in → Tide Tables | CSV | `data/tier1/tides/soi_tide_tables_2026.csv` |
| SoI Tide Tables — 13 new ports | ❌ MISSING | Survey of India | Same portal — 2026 PDF → convert to CSV rows | CSV | Append to `data/tier1/tides/soi_tide_tables_2026.csv` |
| INCOIS Tide Gauge Telemetry | ✅ ON DISK + WIRED | INCOIS | https://incois.gov.in/INCOIS/tidegauge | JSON | `data/tier1/tides/incois_tide_gauge_telemetry.json` |
| Stormglass Tides — 5 ports | ✅ ON DISK + WIRED | Stormglass | https://stormglass.io (API key needed) | JSON | `data/tier2/stormglass/stormglass_tides_*.json` |
| HYCOM current point forecasts (8 ports) | ✅ ON DISK + WIRED (`load_osf_point_forecasts`) | INCOIS OSF | Already on disk | GeoJSON | `data/incois_osf_pfz/osf_hycom/hycom_latest_points.geojson` |
| CMEMS Sea Level | ❌ MISSING | Copernicus | https://data.marine.copernicus.eu → `SEALEVEL_IND_PHY_L4_MY_008_062` | NetCDF | `data/tier2/copernicus/` |

**Missing tide table ports:**
```
Mangalore, Karwar, Mormugao (Goa), Ratnagiri, Mumbai (full),
Hazira, Kandla, Okha, Kakinada, Paradeep, Haldia, Port Blair, Kavaratti (Lakshadweep)
```

---

### PS #4 · "Any lightning, cyclone, or storm warnings in my area?"

**What the system must return:**
- Active cyclone: name, track, intensity (category), closest point of approach, ETA
- Lightning nowcast: active or clear in next 30 minutes (radius-based)
- SACHET CAP emergency alerts filtered by user's district/coast

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| NDMA SACHET CAP alerts | 🔴 LIVE API | NDMA | https://sachet.ndma.gov.in/api/cap | JSON (live) | Live — no file |
| IMD nowcast alerts (cached) | ✅ ON DISK + WIRED | IMD | Already fetched | JSON | `data/tier1/hazards/imd_nowcast_alerts.json` (224 KB) |
| Lightning nowcast — chennai, kochi, mumbai, pamban, thoothukudi | ✅ ON DISK + WIRED | IMD/Open-Meteo | Already fetched | JSON | `data/tier1/hazards/lightning_nowcast_*.json` |
| Lightning nowcast — 7 new ports | ❌ MISSING | Open-Meteo | https://api.open-meteo.com/v1/forecast?hourly=lightning_potential | JSON | `data/tier1/hazards/lightning_nowcast_<port>.json` |
| IMD Cyclone track (RSMC) | 🔴 LIVE API | IMD | https://rsmcnewdelhi.imd.gov.in | JSON/KML | Live — no file |
| Cyclone Gaja replay (SIH demo) | ✅ ON DISK + WIRED | Repo | `data/cyclone_gaja/` | NetCDF | Already present — ready for demo |

> ⚠️ **SIH Demo Note:** Cyclone Gaja (2018) historical replay is already in the repo at
> `data/cyclone_gaja/`. Use this for demo/evaluation. Judges will test the cyclone scenario.

---

### PS #5 · "Am I near the IMBL or any restricted / protected zone?"

**What the system must return:**
- Geodesic distance (nautical miles) to nearest IMBL / EEZ boundary
- Alert level: INSIDE / DANGER (<1 nm) / CAUTION (<5 nm) / CLEAR
- Whether inside a Marine Protected Area (MPA) — name + designation
- Nearest boundary point coordinates

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| India EEZ boundary | ✅ ON DISK + WIRED | VLIZ MarineRegions | https://www.marineregions.org/downloads.php | GeoJSON | `data/tier1/boundaries/india_eez_polygon.geojson` (3.1 MB) |
| Sri Lanka EEZ boundary | ✅ ON DISK + WIRED | VLIZ MarineRegions | Same portal | GeoJSON | `data/tier1/boundaries/srilanka_eez_polygon.geojson` (2.4 MB) |
| India Marine MPAs | ✅ ON DISK + WIRED | WDPA | https://www.protectedplanet.net | GeoJSON | `data/tier1/boundaries/india_marine_mpas.geojson` (158 KB) |
| India–Pakistan maritime boundary | ❌ MISSING | VLIZ | https://www.marineregions.org → India–Pakistan | GeoJSON | `data/tier1/boundaries/india_pakistan_boundary.geojson` |
| India–Bangladesh maritime boundary | ❌ MISSING | VLIZ | Same portal | GeoJSON | `data/tier1/boundaries/india_bangladesh_boundary.geojson` |
| Andaman & Nicobar EEZ sub-zone | ❌ MISSING | VLIZ | Same portal | GeoJSON | `data/tier1/boundaries/andaman_eez.geojson` |
| Lakshadweep EEZ sub-zone | ❌ MISSING | VLIZ | Same portal | GeoJSON | `data/tier1/boundaries/lakshadweep_eez.geojson` |
| Indian district boundaries | ❌ MISSING | data.gov.in | https://data.gov.in → India districts boundary | GeoJSON | `data/tier1/boundaries/india_districts.geojson` |

---

### PS #6 · "What is the safest route from Port A to Fishing Ground B?"

**What the system must return:**
- Waypoint list avoiding shallow water (<10 m), MPAs, IMBL, and rough sea corridors
- Under-keel clearance at each waypoint (from bathymetry)
- Estimated transit time based on current + wind
- Wave height along the route

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| GEBCO 2026 (South India, 7.5–10.5 N) | ✅ ON DISK + WIRED | GEBCO | https://download.gebco.net | NetCDF | `data/tier1/bathymetry/gebco_2026_n10.5_s7.5_w77.5_e80.5.nc` (1 MB) |
| ETOPO all-India bathymetry | ✅ ON DISK + WIRED | NOAA ETOPO | https://www.ncei.noaa.gov/products/etopo | NetCDF | `data/tier1/bathymetry/etopo_all_india_bathymetry.nc` (24.7 MB) |
| GEBCO wider all-India extract | ❌ MISSING | GEBCO | https://download.gebco.net → select 4–26 N, 60–100 E | NetCDF | `data/tier1/bathymetry/gebco_all_india.nc` |
| WW3 NetCDF wave forecast | ✅ ON DISK + WIRED (⏳ expired) | INCOIS OSF | Already downloaded | NetCDF | `data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` (6.5 GB) — per-leg Hs at ETA, `voyage.py` |
| HYCOM current vectors NetCDF | ✅ ON DISK + WIRED (⏳ expired) | INCOIS | Already downloaded | NetCDF | `data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc` (9.9 GB) — `current_vectors()`, `geospatial.py:305` |

---

### PS #7 · "Why has fish catch / productivity declined in [region]?"

**What the system must return:**
- Multi-factor diagnostic: SST anomaly (°C above/below mean), Chlorophyll trend (mg/m³), catch vs historical
- Causal reasoning: "correlated with" (not "caused by" unless evidence supports it)
- Attribution: every figure names its source dataset + acquisition timestamp
- Time-series output: 30–90 day trend chart data

**Datasets required:**

| Dataset | ON-DISK STATUS | Source | URL | Format | Path in repo |
|---------|---------------|--------|-----|--------|--------------|
| ICAR-CMFRI catch records (national) | ✅ ON DISK + WIRED | data.gov.in | https://data.gov.in → marine fish landing | CSV | `data/tier1/fisheries/datagov_marine_fish_landings.csv` (3.4 KB — national only) |
| CMFRI catch — state/district breakdown | ❌ MISSING | ICAR-CMFRI | https://eprints.cmfri.org.in → Marine Fisheries Census | CSV | `data/tier1/fisheries/cmfri_catch_by_state.csv` |
| SST INSAT-3D (Aug 13–29, 17 files) | ✅ ON DISK + WIRED (`satellite_loaders.load_insat_sst`) | MOSDAC | Already downloaded | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/3RIMG_*.h5` |
| Chlorophyll EOS-06 (March 2026, 10 files) | ✅ ON DISK + WIRED (`satellite_loaders.load_eos06_chl`) | MOSDAC | Already downloaded | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` — **stale, 6 months old** |
| Chlorophyll fresh (Jul–Sep 2026) | ❌ MISSING | MOSDAC | https://mosdac.gov.in → EOS-06 → Ocean Colour → Aug–Sep 2026 | NetCDF | `data/tier3/mosdac/chlorophyll/` |
| CMEMS BGC (nutrients) | ❌ MISSING | Copernicus | https://data.marine.copernicus.eu → `OCEANCOLOUR_IND_BGC_L4_MY_009_152` | NetCDF | `data/tier2/copernicus/` |
| River discharge data | ❌ MISSING | CWC / WRIS | https://indiawris.gov.in | CSV | `data/tier1/` |

---

### PS #8 · "Distress — I need help! / Boat is sinking!"

**What the system must return:**
- Emergency bypass within 2 seconds (bypasses all 10-agent pipeline)
- Nearest MRCC station name, VHF channel (always Channel 16), phone number
- Nationwide fallback: Indian Coast Guard 1554
- GPS coordinates extracted and transmitted in DAT-SG / Nabhmitra payload format
- Never an LLM output for this path — hardcoded, deterministic

**Datasets required:**

| Dataset | Source | URL | Format | Path in repo |
|---------|--------|-----|--------|-------------|
| MRCC station lookup | Indian Coast Guard | https://indiancoastguard.gov.in → Rescue / MRCC | JSON (hand-curated) | Backend hardcode in `agents/weather_intelligence.py` |
| Nabhmitra relay API | Ministry of Fisheries | https://nabhmitra.nic.in | REST API | Live integration — Phase 2 |
| DAT-SG format spec | ISRO / SAC | Internal spec — contact ISRO SAC | JSON schema | Backend `agents/` |

> ✅ **Already implemented:** Distress bypass (Agent 12), SOS button, MRCC contact retrieval.
> **Simulated in current build** — DAT-SG relay is not live yet (Phase 2 scope).

---

## Section 2 — Persona-Specific Requirements

### 🐟 Small-Scale Fisherman

**How they ask:** Voice in Tamil/Hindi/Telugu/Malayalam — "நாளை காலையில் கடலுக்கு போவது பாதுகாப்பானதா?"

**What they must get:**
- Single GO / CAUTION / NO-GO badge (no jargon)
- Bearing and distance to nearest PFZ in their language
- Voice output (TTS) in their regional language

**Datasets / components needed:**

| Need | Source | Status |
|------|--------|--------|
| Voice STT (regional languages) | Google Cloud STT / Azure / Bhashini | Backend `agents/voice.py` — present |
| TTS regional output | Same + iSpeech / ISRO Bhashini | Backend `agents/voice.py` — present |
| Bhashini (ISRO/GOI regional NLP) | https://bhashini.gov.in/api | REST API — integration needed |
| PFZ all coastal sectors | INCOIS OSF | Currently only SEC006 |

---

### 🚢 Commercial Navigator / Vessel Operator

**How they ask:** "What's the safest route avoiding shallow waters, IMBL, and high swells?"

**What they must get:**
- Waypoint table (lat/lon) with ETA
- Under-keel clearance at each point (requires bathymetry per-waypoint lookup)
- IMBL hard-barrier enforcement (NO-GO zone, not just a warning)
- Wave height profile along route

**Datasets / components needed:**

| Need | Source | Status |
|------|--------|--------|
| GEBCO all-India extent | GEBCO | Fetch wider extract (currently South India only) |
| HYCOM currents all coasts | INCOIS OSF | Present for pilot area; expand bbox |
| WaveWatch III forecast | INCOIS OSF | Need to wire into route planner |
| Missing boundary files | VLIZ | India-Pakistan, India-Bangladesh, Andaman EEZ |

---

### 🔬 Marine / Fisheries Researcher

**How they ask:** "Show me chlorophyll anomaly and SST trend for Gulf of Mannar, last quarter."

**What they must get:**
- Statistical summary: mean, Δ (anomaly), R² (correlation with catch or SST)
- Sensor provenance: satellite name, resolution, acquisition timestamp per data point
- Time-series data exportable as CSV / JSON / NetCDF
- Citation-backed: every figure attributed to dataset + timestamp

**Datasets / components needed:**

| Need | Source | Status |
|------|--------|--------|
| MOSDAC SST multi-month | MOSDAC FTP | Partial (Aug 13–29 only) — fetch 90-day archive |
| MOSDAC Chlorophyll multi-month | MOSDAC | March 2026 only — fetch Jul–Sep 2026 |
| CMFRI catch records (per region) | ICAR-CMFRI / data.gov.in | Single national CSV — need region breakdown |
| Export formatter | `backend/orca/agents/reporting.py` | CSV export exists; NetCDF export not yet |

---

### 🚨 Coastal Authority / NDMA / SDMA / INCOIS

**How they ask:** "Give me district-level risk summary and CAP alert payload for next 48 hours."

**What they must get:**
- District rollup: wave height, wind, cyclone proximity, IMBL breach incidents
- CAP 1.2 format payload (machine-readable, for Sagar Vani / bulk SMS broadcast)
- Evacuation threat matrix (ranked by district, severity)

**Datasets / components needed:**

| Need | Source | Status |
|------|--------|--------|
| SACHET CAP feed | NDMA | Live — already integrated |
| IMD district advisory | IMD | https://mausam.imd.gov.in → District forecast | Not integrated |
| Indian district boundary shapefile | Survey of India / data.gov.in | https://data.gov.in → India districts GeoJSON | Not in repo |
| Sagar Vani broadcast API | Ministry of Fisheries | https://sagarvani.com.in | REST API — integration needed |

---

## Section 3 — Place Name Gazetteer (All-India)

Add all entries below to `backend/orca/data/loaders.py` → `_PILOT_GAZETTEER`.
Coordinates are **offshore positions** (~10–20 nm from coast), not town centres.

### West Coast — Arabian Sea

```python
# ── Kerala ──────────────────────────────────────────────────────────
"kerala":                  (10.50,  76.00),
"kerala coast":            (10.50,  76.00),
"thiruvananthapuram":      ( 8.49,  76.95),
"trivandrum":              ( 8.49,  76.95),
"kollam":                  ( 8.89,  76.60),
"quilon":                  ( 8.89,  76.60),
"alappuzha":               ( 9.49,  76.33),
"alleppey":                ( 9.49,  76.33),
"kochi":                   ( 9.90,  76.00),
"cochin":                  ( 9.90,  76.00),
"ernakulam":               ( 9.90,  76.00),
"thrissur":                (10.50,  76.10),
"kozhikode":               (11.25,  75.78),
"calicut":                 (11.25,  75.78),
"kannur":                  (11.87,  75.37),
"cannanore":               (11.87,  75.37),
"kasaragod":               (12.50,  74.98),
"lakshadweep":             (10.57,  72.64),
"minicoy":                 ( 8.28,  73.04),
"kavaratti":               (10.57,  72.64),
"agatti":                  (10.85,  72.17),

# ── Karnataka ───────────────────────────────────────────────────────
"karnataka":               (13.50,  74.50),
"karnataka coast":         (13.50,  74.50),
"mangalore":               (12.85,  74.65),
"mangaluru":               (12.85,  74.65),
"udupi":                   (13.33,  74.60),
"karwar":                  (14.80,  73.90),
"ankola":                  (14.65,  74.30),
"bhatkal":                 (13.97,  74.55),
"kundapur":                (13.63,  74.62),

# ── Goa ─────────────────────────────────────────────────────────────
"goa":                     (15.50,  73.50),
"goa coast":               (15.50,  73.50),
"panaji":                  (15.50,  73.70),
"mormugao":                (15.40,  73.80),
"vasco da gama":           (15.40,  73.80),

# ── Maharashtra ─────────────────────────────────────────────────────
"maharashtra":             (17.50,  71.00),
"maharashtra coast":       (17.50,  71.00),
"sindhudurg":              (16.00,  73.40),
"ratnagiri":               (16.99,  73.12),
"raigad":                  (18.50,  72.80),
"alibag":                  (18.64,  72.72),
"mumbai":                  (18.96,  72.68),
"bombay":                  (18.96,  72.68),
"vasai":                   (19.40,  72.70),
"dahanu":                  (19.97,  72.73),
"tarapur":                 (19.91,  72.72),

# ── Gujarat ─────────────────────────────────────────────────────────
"gujarat":                 (21.50,  70.00),
"gujarat coast":           (21.50,  70.00),
"surat":                   (21.10,  72.30),
"bharuch":                 (21.70,  72.50),
"veraval":                 (20.90,  70.37),
"somnath":                 (20.90,  70.37),
"dwarka":                  (22.24,  68.70),
"okha":                    (22.47,  69.05),
"jamnagar":                (22.47,  69.97),
"porbandar":               (21.64,  69.50),
"bhavnagar":               (21.77,  72.15),
"mandvi":                  (22.83,  69.35),
"mundra":                  (22.70,  69.50),
"kandla":                  (23.03,  70.22),
"hazira":                  (21.12,  72.66),
"gulf of kutch":           (22.50,  69.50),
"gulf of khambhat":        (21.00,  72.50),
"arabian sea":             (12.00,  72.00),
```

### East Coast — Bay of Bengal

```python
# ── Tamil Nadu (extend from pilot) ──────────────────────────────────
"tamil nadu":              ( 9.50,  79.50),
"tamil nadu coast":        ( 9.50,  79.50),
"rameswaram":              ( 9.28,  79.30),
"pondicherry":             (11.93,  79.87),
"puducherry":              (11.93,  79.87),
"karaikal":                (10.92,  79.84),
"velankanni":              (10.68,  79.85),
"porto novo":              (11.50,  79.75),
"ennore":                  (13.22,  80.32),
"mahabalipuram":           (12.63,  80.19),

# ── Andhra Pradesh ──────────────────────────────────────────────────
"andhra pradesh":          (15.00,  80.50),
"andhra coast":            (15.00,  80.50),
"nellore":                 (14.43,  80.05),
"ongole":                  (15.50,  80.33),
"krishnapatnam":           (14.25,  80.12),
"machilipatnam":           (16.17,  81.13),
"kakinada":                (16.93,  82.25),
"bhimavaram":              (16.54,  81.52),

# ── Odisha ──────────────────────────────────────────────────────────
"odisha":                  (19.50,  85.50),
"odisha coast":            (19.50,  85.50),
"gopalpur":                (19.27,  84.90),
"puri":                    (19.80,  85.85),
"chilika":                 (19.72,  85.32),
"paradeep":                (20.32,  86.62),
"dhamra":                  (20.75,  86.97),
"balasore":                (21.50,  87.00),
"chandipur":               (21.50,  87.07),

# ── West Bengal ─────────────────────────────────────────────────────
"west bengal":             (21.63,  88.00),
"west bengal coast":       (21.63,  88.00),
"haldia":                  (22.03,  88.07),
"sagar island":            (21.65,  88.08),
"sundarbans":              (21.93,  88.88),
"digha":                   (21.63,  87.50),
"kolkata":                 (22.03,  88.07),

# ── Andaman & Nicobar ───────────────────────────────────────────────
"andaman":                 (12.00,  93.00),
"andaman coast":           (12.00,  93.00),
"andaman sea":             (10.00,  95.00),
"port blair":              (11.67,  92.75),
"nicobar":                 ( 8.00,  93.50),
"car nicobar":             ( 9.17,  92.83),
"little andaman":          (10.67,  92.57),
"north andaman":           (13.25,  93.00),
"havelock island":         (12.02,  92.98),

# ── Ocean regions ───────────────────────────────────────────────────
"bay of bengal":           (13.00,  82.00),
"indian ocean":            ( 7.00,  76.00),
"palk bay":                ( 9.50,  79.20),
"gulf of mannar":          ( 8.80,  78.70),
"palk strait":             ( 9.80,  79.60),
"laccadive sea":           (10.00,  74.00),
```

---

## Section 4 — Master Dataset Table (with On-Disk Status)

> Legend: ✅ = on disk & wired · ⚙️ = on disk, code not wired · ❌ = must download · 🔴 = live API
>
> **As of 2026-09-16 no row in this table is ⚙️.** Rows still marked ❌ are genuine downloads, not
> code gaps — that distinction is the whole point of this table, so do not confuse the two when
> planning work.
>
> **How to actually get the ❌ and ⏳ rows: `docs/ORCA_Dataset_Procurement_Runbook.md`** (2026-09-16,
> every endpoint probed live). Its §0 corrects four rows below that are wrong as written — the two
> `*_IND_*` Copernicus product ids (18, 20) do not exist, `osf.incois.gov.in` (3, 4, 6) does not
> resolve, the bilateral boundary lines (29, 30) are a WFS query rather than a portal download, and
> the Lakshadweep EEZ (32) is not a separate feature at all.

| # | Dataset | On-Disk Status | Source Portal | Direct URL | Free? | Reg? | Format | Repo Path |
|---|---------|---------------|--------------|------------|-------|------|--------|-----------|
| 1 | PFZ Daily Advisories | ✅ | INCOIS OSF | https://osf.incois.gov.in | ✅ | No | JSON | `data/incois_osf_pfz/pfz/incois_pfz_live_advisories.geojson` |
| 2 | PFZ History — 1 date | ✅ | INCOIS OSF | Same → Archive | ✅ | No | JSON | `data/incois_osf_pfz/pfz/history/20260901/` |
| 3 | PFZ History — 6 more dates + all sectors | ❌ | INCOIS OSF | Same → Archive | ✅ | No | JSON | `data/incois_osf_pfz/pfz/history/` |
| 4 | HYCOM current NetCDF (9.9 GB) | ✅ ⏳ | INCOIS OSF | https://osf.incois.gov.in → Ocean Current | ✅ | No | NetCDF | `data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc` |
| 5 | HYCOM current point GeoJSON (8 ports) | ✅ | INCOIS OSF | Already on disk | ✅ | No | GeoJSON | `data/incois_osf_pfz/osf_hycom/hycom_latest_points.geojson` |
| 6 | WW3 wave NetCDF (6.5 GB) | ✅ ⏳ | INCOIS OSF | https://osf.incois.gov.in → Wave | ✅ | No | NetCDF | `data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` |
| 7 | WW3 point GeoJSON | ✅ | INCOIS OSF | Already on disk | ✅ | No | GeoJSON | `data/incois_osf_pfz/osf_ww3/ww3_latest_points.geojson` |
| 8 | INSAT-3D SST (17 files, Aug 13–29) | ✅ | MOSDAC | https://mosdac.gov.in → INSAT-3D → SST | ✅ | Yes | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/3RIMG_*.h5` |
| 9 | SST fresh files (Aug 30 – today) | ❌ | MOSDAC | Same portal | ✅ | Yes | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/` |
| 10 | EOS-06 Chlorophyll (10 files, March 2026) | ✅ ⏳ | MOSDAC | https://mosdac.gov.in → EOS-06 → Ocean Colour | ✅ | Yes | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` |
| 11 | Chlorophyll fresh (Jul–Sep 2026) | ❌ | MOSDAC | Same portal | ✅ | Yes | NetCDF | `data/tier3/mosdac/chlorophyll/` |
| 12 | EOS-06 ScatSat Wind (11 files) | ✅ | MOSDAC | https://mosdac.gov.in → EOS-06 → Wind | ✅ | Yes | NetCDF | `data/tier3/mosdac/Wind/E06SCTL4AW_*.nc` |
| 13 | Open-Meteo Marine — 5 existing ports | ✅ | Open-Meteo | https://marine-api.open-meteo.com/v1/marine | ✅ | No | JSON | `data/tier1/ocean/openmeteo_marine_*.json` |
| 14 | Open-Meteo Marine — 16 new ports | ❌ | Open-Meteo | Same (free) | ✅ | No | JSON | `data/tier1/ocean/openmeteo_marine_<port>.json` |
| 15 | Open-Meteo Weather — 6 existing ports | ✅ | Open-Meteo | https://api.open-meteo.com/v1/forecast | ✅ | No | JSON | `data/tier1/weather/openmeteo_weather_*.json` |
| 16 | Open-Meteo Weather — 16 new ports | ❌ | Open-Meteo | Same (free) | ✅ | No | JSON | `data/tier1/weather/openmeteo_weather_<port>.json` |
| 17 | CMEMS SST / Physics | ✅ | Copernicus | https://data.marine.copernicus.eu → `GLOBAL_ANALYSISFORECAST_PHY_001_024` | ✅ | Yes (EU) | NetCDF | `data/tier2/copernicus/` |
| 18 | CMEMS Ocean Colour | ❌ | Copernicus | https://data.marine.copernicus.eu → `OCEANCOLOUR_IND_BGC_L4_MY_009_152` | ✅ | Yes | NetCDF | `data/tier2/copernicus/` |
| 19 | CMEMS Wave | ❌ | Copernicus | https://data.marine.copernicus.eu → `GLOBAL_ANALYSISFORECAST_WAV_001_027` | ✅ | Yes | NetCDF | `data/tier2/copernicus/` |
| 20 | CMEMS Sea Level | ❌ | Copernicus | https://data.marine.copernicus.eu → `SEALEVEL_IND_PHY_L4_MY_008_062` | ✅ | Yes | NetCDF | `data/tier2/copernicus/` |
| 21 | NASA MODIS Chlorophyll | ❌ | NASA OBPG | https://oceancolor.gsfc.nasa.gov/l3/ | ✅ | Yes | NetCDF | `data/tier2/nasa/` |
| 22 | NASA GHRSST SST | ❌ | NASA PODAAC | https://podaac.earthdata.nasa.gov → GHRSST | ✅ | Yes | NetCDF | `data/tier2/nasa/` |
| 23 | GEBCO South India | ✅ | GEBCO | https://download.gebco.net | ✅ | No | NetCDF | `data/tier1/bathymetry/gebco_2026_n10.5_s7.5_w77.5_e80.5.nc` |
| 24 | ETOPO All India | ✅ | NOAA NCEI | https://www.ncei.noaa.gov/products/etopo | ✅ | No | NetCDF | `data/tier1/bathymetry/etopo_all_india_bathymetry.nc` |
| 25 | GEBCO all-India wider extract | ❌ | GEBCO | https://download.gebco.net → select 4–26 N, 60–100 E | ✅ | No | NetCDF | `data/tier1/bathymetry/gebco_all_india.nc` |
| 26 | India EEZ boundary | ✅ | VLIZ | https://www.marineregions.org/downloads.php | ✅ | No | GeoJSON | `data/tier1/boundaries/india_eez_polygon.geojson` |
| 27 | Sri Lanka EEZ boundary | ✅ | VLIZ | Same | ✅ | No | GeoJSON | `data/tier1/boundaries/srilanka_eez_polygon.geojson` |
| 28 | India Marine MPAs | ✅ | WDPA | https://www.protectedplanet.net | ✅ | Yes | GeoJSON | `data/tier1/boundaries/india_marine_mpas.geojson` |
| 29 | India–Pakistan boundary | ❌ | VLIZ | https://www.marineregions.org | ✅ | No | GeoJSON | `data/tier1/boundaries/india_pakistan_boundary.geojson` |
| 30 | India–Bangladesh boundary | ❌ | VLIZ | Same | ✅ | No | GeoJSON | `data/tier1/boundaries/india_bangladesh_boundary.geojson` |
| 31 | Andaman & Nicobar EEZ | ❌ | VLIZ | Same | ✅ | No | GeoJSON | `data/tier1/boundaries/andaman_eez.geojson` |
| 32 | Lakshadweep EEZ | ❌ | VLIZ | Same | ✅ | No | GeoJSON | `data/tier1/boundaries/lakshadweep_eez.geojson` |
| 33 | Indian District Boundaries | ❌ | data.gov.in | https://data.gov.in → India districts | ✅ | No | GeoJSON | `data/tier1/boundaries/india_districts.geojson` |
| 34 | SoI Tide Tables 2026 (pilot ports) | ✅ | Survey of India | https://surveyofindia.gov.in → Tide Tables | ✅ | No | CSV | `data/tier1/tides/soi_tide_tables_2026.csv` |
| 35 | SoI Tide Tables — new ports | ❌ | Survey of India | Same | ✅ | No | CSV | Append to same file |
| 36 | INCOIS Tide Gauge Telemetry | ✅ | INCOIS | https://incois.gov.in/INCOIS/tidegauge | ✅ | No | JSON | `data/tier1/tides/incois_tide_gauge_telemetry.json` |
| 37 | Stormglass Tides (5 ports) | ✅ | Stormglass | https://stormglass.io | Freemium | Yes | JSON | `data/tier2/stormglass/stormglass_tides_*.json` |
| 38 | NDMA SACHET CAP alerts | 🔴 | NDMA | https://sachet.ndma.gov.in/api/cap | ✅ | No | Live JSON | Live API |
| 39 | IMD nowcast alerts (cached) | ✅ | IMD | Already on disk | ✅ | No | JSON | `data/tier1/hazards/imd_nowcast_alerts.json` |
| 40 | Lightning nowcast — 5 ports | ✅ | IMD/Open-Meteo | Already on disk | ✅ | No | JSON | `data/tier1/hazards/lightning_nowcast_*.json` |
| 41 | Lightning nowcast — new ports | ❌ | Open-Meteo | https://api.open-meteo.com → `lightning_potential` | ✅ | No | JSON | `data/tier1/hazards/lightning_nowcast_<port>.json` |
| 42 | IMD RSMC Cyclone track | 🔴 | IMD | https://rsmcnewdelhi.imd.gov.in | ✅ | No | KML | Live API |
| 43 | Cyclone Gaja replay | ✅ | Repo | `data/cyclone_gaja/` | ✅ | — | NetCDF | `data/cyclone_gaja/` |
| 44 | ICAR-CMFRI catch (national) | ✅ | data.gov.in | https://data.gov.in → marine fish landing | ✅ | No | CSV | `data/tier1/fisheries/datagov_marine_fish_landings.csv` |
| 45 | CMFRI catch — state breakdown | ❌ | ICAR-CMFRI | https://eprints.cmfri.org.in | ✅ | No | CSV | `data/tier1/fisheries/cmfri_catch_by_state.csv` |
| 46 | ISRO Bhashini (regional TTS/STT) | 🔴 | Bhashini | https://bhashini.gov.in/api | ✅ | Yes (ISRO) | REST API | Live API |
| 47 | Sagar Vani broadcast | 🔴 | Govt fisheries | https://sagarvani.com.in | ✅ | Yes | REST API | Phase 2 |

---

## Section 5 — Code Changes Checklist

| # | File | Change | For PS Query | Priority |
|---|------|--------|-------------|----------|
| C1 | `backend/orca/data/loaders.py` | ~~Add 120+ all-India place names to `_PILOT_GAZETTEER`~~ | All | ✅ **Done** — `_GAZETTEER`, ~150 entries, whole-word matching |
| C2 | `backend/orca/data/loaders.py` | Add 15 new ports to `CACHED_MARINE_PORTS` and `CACHED_WEATHER_PORTS` | #2, #3 | 🔴 Critical |
| C3 | `backend/orca/agents/ocean_analytics.py` | ~~Wire `hycom_latest_points.geojson`~~ | #1, #3 | ✅ **Done** — `nearest_osf_point_forecast()` (points, then the 0.5° grid) |
| C4 | `backend/orca/data/satellite_loaders.py` | ~~Wire MOSDAC INSAT-3D SST `.h5` files → HDF5 loader~~ | #1, #7, DATA LIMITED fix | ✅ **Done** — `load_insat_sst()` |
| C5 | `backend/orca/agents/ocean_analytics.py` | ~~Expand from `_PILOT_SECTOR = "SEC006"` to all sectors by lat/lon~~ | #1 | ✅ **Done** — `sector_for_point()`, all **14** sectors (not 11) |
| C6 | `backend/orca/agents/reporting.py` | Add informational query path — return value + citation, not just GO/NO-GO | #3 | 🟡 High |
| C7 | `backend/orca/data/satellite_loaders.py` | ~~Wire chlorophyll EOS-06 `.nc` → correlate with SST~~ | #7, DATA LIMITED fix | ✅ **Done** — `load_eos06_chl()`, co-located on a 0.25° grid. *Fetching fresh files is still open* |
| C8 | `backend/orca/data/loaders.py` | Add India district boundary shapefile loader | #4 (CAP alerts) | 🟡 High |
| C9 | `backend/orca/api/geospatial_routes.py` | Add missing boundary files (India-Pakistan, Bangladesh, Andaman) | #5 | 🟡 High |
| C10 | `backend/orca/agents/` | Add `route_planner.py` agent — waypoint routing with bathymetry + geofence | #6 | 🟠 Medium |
| C11 | `backend/orca/agents/reporting.py` | Add CAP 1.2 payload formatter for coastal authority persona | #8, authority persona | 🟠 Medium |
| C12 | `backend/orca/agents/voice.py` | Integrate ISRO Bhashini API for regional language TTS | Fisherman persona | 🟠 Medium |
| C13 | `backend/orca/agents/ocean_analytics.py` | Add CMFRI catch trend reader + anomaly correlator | #7 | 🟨 Partly done — `wind_anomaly()` supplies the ERA5 reference period; a CMFRI-specific correlator is still open |
| C14 | All agents | Ensure all confidence tiers include provenance + freshness for every output | Meta / trust | 🟡 High |

---

## Section 6 — What "DATA LIMITED" Means and How to Fix It

The DATA LIMITED badge appears when **any** agent returns `LOW_DATA` confidence. Here is every root cause and its fix:

| Root Cause | Agent | Fix |
|-----------|-------|-----|
| ~~MOSDAC SST files not read by code~~ | `ocean_analytics` | ✅ Fixed 2026-09-16 — `satellite_loaders.load_insat_sst` |
| PFZ history is 3 folders, needs 5 in a 7-day window | `ocean_analytics` | **Self-healing 2026-09-19.** `scripts/cron/refresh_daily` runs `scrape_pfz_advisories.py`, which archives one folder per morning, so the window fills by ~23 Sep. Until it does, `score_pfz_persistence` returns `INDICATIVE` / `LOW_DATA` naming the shortfall instead of scoring 0/3 and calling it TRANSIENT |
| MOSDAC Chlorophyll files stale (March) | `ocean_analytics` | Fetch Jul–Sep 2026 files from MOSDAC |
| Live Open-Meteo fails → stale Aug 30 cache | `weather_intelligence` | Refresh cached files for all ports |
| CMEMS SST/currents for non-pilot regions | `ocean_analytics` | The reader exists (`load_cmems_sst`); the **file** covers 77–80.5 E / 7.5–10.5 N only. Download the full-India bbox |
| ~~No ERA5 baseline outside Thoothukudi~~ | `ocean_analytics` | **Closed 2026-09-19.** `scripts/refresh_era5_baselines.py` fetches a 30-day ERA5 window from the Open-Meteo archive for every port with a cached forecast — 104 of them, both coasts and the islands — so PS-Q7's anomaly leg answers nationally. Same provider and same km/h units as the forecast it is compared against, deliberately: `wind_anomaly()` does no unit conversion, so a different provider would put a systematic offset into the z-score |
| IMD nowcast snapshot window closed | `weather_intelligence` | The cache is one 3-hour window from 2026-08-30. Re-fetch; the code already reports `expired: true` rather than presenting it as current |

Once all data files are present and wired, `LOW_DATA` should only appear when satellite
coverage is genuinely obscured (cloud cover) or when a location has no cached fallback — and the system will say so explicitly, not silently.

---

## Section 7 — SIH Judge / Evaluator Checklist

These are the meta-questions judges will ask. Each must be answerable from the system:

| Judge Question | How ORCA answers it | Status |
|----------------|--------------------|----|
| "Why should the user trust this advice?" | Every output cites dataset name + acquisition timestamp + confidence tier | ✅ Implemented in citations |
| "Can the LLM hallucinate a safety verdict?" | Safety verdict is deterministic Python rule-based — LLM only formats prose | ✅ Architecture enforced |
| "What if satellite data is cloud-covered?" | Fallback chain exposed: INCOIS cloud → historical persistence → Open-Meteo | ⚠️ Only for pilot region |
| "What if there is no internet?" | Tier-1 cached files serve every answer — no live call required | ✅ Fallback implemented |
| "How do you warn users who haven't opened the app?" | Sentinel Agent + Watches + push notifications via Sagar Vani | ⚠️ Sentinel present, Sagar Vani Phase 2 |
| "Does it work in Tamil / regional languages?" | Voice agent STT/TTS — Bhashini integration needed for full coverage | ⚠️ voice.py present, Bhashini not yet wired |
| "Can you demo a cyclone scenario?" | Cyclone Gaja historical replay in `data/cyclone_gaja/` | ✅ Ready for demo |
| "What about distress at sea?" | SOS button → Agent 12 bypass → MRCC contact in <2 seconds | ✅ Implemented |

---

## Section 8 — Validity windows: what has already expired

Every cached dataset in `data/` has a validity window, and several have passed it. A forecast read
outside its window is not "slightly old" — it is a number with no relationship to the day being asked
about. Checked 2026-09-13:

| Dataset | Stamp on disk | Window | State on 2026-09-13 |
|---|---|---|---|
| SoI tide tables | 2026-08-30 → **2026-09-08** | The dates in the file | ⏳ **EXPIRED.** `predict_tides()` has no future extreme to return for any port. PS-Q3 is broken today, everywhere |
| PFZ advisories | `valid_for: 2026-09-02` | 1 day (INCOIS reissues daily) | ⏳ 11 days stale. PS-Q1 answers cite a zone that may no longer be advised |
| WW3 wave forecast | run 2026-08-29 | 7 days | ⏳ Expired — `wave_height_at()` returns LOW_DATA for any present-day ETA |
| HYCOM currents | run 2026-08-30 | 7 days | ⏳ Expired — the current layer renders history, labelled as forecast |
| Wave-height tiles | frames 2026-09-01 → 09-07 | 7 days | ⏳ Expired |
| Open-Meteo caches | fetched 2026-09-03 | 7 days | ⏳ Expired (live API is primary, so this bites only when offline — i.e. exactly during the offline demo beat) |
| ScatSat wind | day-of-year 239 ≈ 2026-08-27 | Archived by design | Labelled "archived, not live" in code — honest |
| MOSDAC chlorophyll | March 2026 | — | 6 months stale, and unread anyway |
| NDMA CAP cache | — | Live-first | Fallback only |

**Two consequences, both requirements:**

1. **A refresh run is mandatory before any demo or judging session.** Treat it as part of the demo
   checklist, not as a data task. The tide expiry alone silently removes a named PS query.
2. **The system must notice this itself.** DLC `R-SAFE-1` (staleness ceiling) is currently rated one
   hour of work and is the difference between "we were unlucky with the cache" and "the platform told
   the judge its own data was expired, out loud, before the judge noticed." Ship it before the refresh,
   not after — the expired state on disk right now is a free test fixture.

---

## Section 9 — The three code blockers that gate all-India coverage — **all three cleared**

Data volume was not what stopped all-India coverage; three specific pieces of code were. **All three
are fixed as of 2026-09-16.** The table is kept as the record of what they were, because the shape of
each defect is worth remembering: in every case national coverage was sitting on disk already.

| # | Blocker | File:line | Effect today | Fix |
|---|---|---|---|---|
| B-1 ✅ | ~~The place gazetteer is pilot-only~~ — 16 South Tamil Nadu entries plus 5 tide stations plus 6 port fixtures | `data/loaders.py:151-171` | A query naming **Veraval, Paradeep, Digha, Port Blair, Kavaratti, Gopalpur** or any of ~100 other coastal places resolves to nothing, falls to `DEFAULT_LAT/LON = 8.80, 78.30` (Gulf of Mannar), and is answered **confidently about the wrong coast**. This is the single highest-harm defect in the product | Apply §3 of this guide to `_PILOT_GAZETTEER`; pair with DLC `R-NEW-1` so a fallback position is always disclosed |
| B-2 ✅ | ~~User sector is hardcoded~~ | `ocean_analytics.py:53,691` — `_PILOT_SECTOR = "SEC006"` | Every user in India is shown **South Tamil Nadu's** sector status. A Kerala fisherman is told his sector is cloud-suppressed while SEC004 has 24 live advisories on disk | Point-in-sector lookup from lat/lon; the sector geometry is derivable from the advisory node coordinates already on disk |
| B-3 ✅ | ~~SST/chlorophyll correlation reads a directory that does not exist~~ | `analytics_loaders.py:27,196` — `data/fixtures/` | PS-Q5 has **no working path at all**, and the two ISRO satellite archives on disk (212 MB) are never opened. The README claim that PFZ derives from SST + chlorophyll is not true of the running code | DLC `R-SCI-1` — a parser that writes the fixtures the seam already expects |

**Resolutions.** B-1: `loaders._GAZETTEER` carries ~150 all-India entries and resolves on whole-word
matches, so short names like "goa" no longer fire inside ordinary English. B-2:
`ocean_analytics.sector_for_point()` resolves SEC001–SEC014 from a coast-side + latitude-band rule —
sector geometry could not be recovered from the advisory nodes alone, because the six cloud-suppressed
sectors have zero nodes and those are precisely the sectors a user most needs named. B-3:
`correlate_sst_chlorophyll()` reads the ISRO archives directly through
`satellite_loaders`, co-locating INSAT-3DR SST and EOS-06 chlorophyll on a 0.25° grid and reporting
the acquisition gap between the two granules rather than implying simultaneity.

**What remains is downloads, not code.** Fresh MOSDAC granules, ≥7 days of PFZ history, Open-Meteo
caches for the 16 new ports, SoI tide tables beyond 5 stations, the missing IMBL geometries, and the
full-India CMEMS bbox. None of these is blocked on a code change.

---

*Document prepared 2026-09-12 · wiring ledger, sector table, validity windows and code blockers
re-verified against the working tree 2026-09-13 · **second wiring pass completed and re-verified
2026-09-16**: six uncalled loaders given callers, three further datasets wired, the all-India PFZ file
generated, and every ⚙️ mark in this document retired. Verification: call-chain grep for every loader
plus `pytest tests -q -p no:randomly` → 382 passed, 2 skipped.*
*Grounded in `docs/ORCA_PS_SIH26176_Problem_Statement.md` — clause IDs in this file refer to it.*
