# ORCA — Procurement Runbook for the Datasets Still Missing

> **Project:** SIH 2026 · PS #SIH26176 · grounded in `docs/ORCA_PS_SIH26176_Problem_Statement.md`
> **Scope:** every row still marked ❌ in `docs/ORCA_SIH26176_AllIndia_Dataset_Coverage_Guide.md` §4,
> plus the ⏳ expired rows, which are a *refresh* rather than a download but break the same PS queries.
> **Written:** 2026-09-16. Every endpoint below was probed live on that date — the status notes say
> what answered, not what a portal page claims.

Wiring is done. What is left is acquisition, and it splits three ways:

| Group | What it needs | Items | Realistic effort |
|---|---|---|---|
| **A — scriptable now** | Nothing but a network connection | 6 | ~2 h, mostly unattended |
| **B — free account** | One registration each, credentials into `.env` | 3 | ~1 h + approval wait (MOSDAC only) |
| **C — manual / best effort** | A human reading a PDF or a portal | 4 | ~4 h, parallelisable |

---

## 0. Corrections found while verifying — read before following the old guide

Four rows in coverage guide §4 will waste your time as written.

| Guide row | What it says | Verified 2026-09-16 |
|---|---|---|
| 18, 20 | Copernicus `OCEANCOLOUR_IND_BGC_L4_MY_009_152`, `SEALEVEL_IND_PHY_L4_MY_008_062` | **Both 404 on the CMEMS STAC catalog. No `*_IND_*` product exists** — CMEMS regional codes are ARC/ATL/BAL/BLK/MED/IBI/NWS/BS and GLO. Use the global products in §B2 and subset to the India bbox |
| 3, 4, 6 | Source portal `https://osf.incois.gov.in` | **DNS does not resolve.** The OSF NetCDFs are served from `https://incois.gov.in/thredds/` (verified, §A3) |
| 29, 30 | "Download India–Pakistan / India–Bangladesh boundary from marineregions.org" | The downloads page publishes **zone polygons only** — no bilateral-line product. The lines exist in the `MarineRegions:eez_boundaries` WFS layer, which returns **32 India lines in one request** (§A2) |
| 32 | Lakshadweep EEZ sub-zone | **Does not exist as a separate feature.** VLIZ v12 has exactly two Indian EEZ polygons: mainland (MRGID 8480, already on disk) and Andaman & Nicobar (MRGID 8333). Lakshadweep waters sit inside 8480 |

One more, on Sir Creek (PS-C8, "international maritime boundaries"): VLIZ carries the India–Pakistan
line with `line_type: "Median line"`, not `"Treaty"`, because there is no agreed delimitation. The
India–Bangladesh line is `"Court ruling"` (the 2014 PCA award). **Carry `line_type` into the geofence
layer verbatim.** A median line rendered as though it were a treaty boundary is exactly the kind of
confident-but-wrong output the deterministic core exists to prevent.

---

## A. Free, no account, scriptable today

### A1 · Open-Meteo caches for the 16 new ports — guide rows 14, 16, 41

The gazetteer in coverage guide §3 has **113 entries**; `loaders.CACHED_*_PORTS` has 5–6. Every
non-pilot location therefore has no offline fallback, which is the one thing that bites during the
airplane-mode demo beat.

Free, keyless, no rate limit worth worrying about. One loop, three files per port:

```bash
# marine (waves, swell, currents) -> data/tier1/ocean/openmeteo_marine_<port>.json
curl -s "https://marine-api.open-meteo.com/v1/marine?latitude=$LAT&longitude=$LON\
&hourly=wave_height,wave_direction,wave_period,swell_wave_height,ocean_current_velocity,ocean_current_direction\
&timezone=Asia%2FKolkata" -o "data/tier1/ocean/openmeteo_marine_$PORT.json"

# weather -> data/tier1/weather/openmeteo_weather_<port>.json
curl -s "https://api.open-meteo.com/v1/forecast?latitude=$LAT&longitude=$LON\
&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m,precipitation\
&timezone=Asia%2FKolkata" -o "data/tier1/weather/openmeteo_weather_$PORT.json"

# lightning -> data/tier1/hazards/lightning_nowcast_<port>.json
curl -s "https://api.open-meteo.com/v1/forecast?latitude=$LAT&longitude=$LON\
&hourly=lightning_potential,cape&timezone=Asia%2FKolkata" \
  -o "data/tier1/hazards/lightning_nowcast_$PORT.json"
```

Drive it from the §3 gazetteer rather than a second hand-kept port table — `loaders.py` already
derives each port's coordinates from its own cached file, so the fixture is the coordinate source of
record. Fix the known one-port hole while you are there: **visakhapatnam has a weather cache but no
marine cache**, called out in a comment in `loaders.py`.

*Cost: free · Time: minutes · Blocker: none.*

### A2 · All the maritime boundary lines in one request — guide rows 29, 30, 31, 32

Not a portal download. VLIZ's GeoServer WFS is open, CC-BY, and answers with GeoJSON:

```bash
curl -s "https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=2.0.0\
&request=GetFeature&typeName=MarineRegions:eez_boundaries&outputFormat=application/json\
&CQL_FILTER=sovereign1%3D%27India%27%20OR%20sovereign2%3D%27India%27" \
  -o data/tier1/boundaries/india_maritime_boundary_lines.geojson
```

**Verified: 32 features**, including Pakistan–India (median line), Bangladesh–India (court ruling
*and* a median line), four Sri Lanka treaty segments, Maldives, Myanmar, Thailand, Indonesia, the
India and Andaman 200 NM lines, and three India straight-baseline segments — Gujarat/Sir Creek and
West Bengal stop being geometry-less coasts. Each feature carries `line_type`, `source1` and `url1`,
which is what the citation panel needs.

Andaman & Nicobar EEZ polygon (row 31), same server:

```bash
curl -s "https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&version=2.0.0\
&request=GetFeature&typeName=MarineRegions:eez&outputFormat=application/json\
&CQL_FILTER=mrgid%3D8333" -o data/tier1/boundaries/andaman_eez.geojson
```

Row 32 (Lakshadweep) is closed by §0 — nothing to download.

*Cost: free · Time: 5 min · Blocker: none.*

### A3 · Refresh the expired INCOIS forecasts — guide rows 4, 6 (⏳) and the tile frames

`https://incois.gov.in/thredds/` is a live THREDDS server. Its catalog today carries
`rsmc_combined_ww3_20260915.nc` and `CURRENTS_IO_20260915.nc` — one day old, against the 2026-08-29 /
08-30 runs on disk.

Whole file, same shape as what is on disk (6.5 GB / 9.9 GB; `voyage.py` and `geospatial.py` open
these directly):

```bash
curl -L -o "data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260915.nc" \
  "https://incois.gov.in/thredds/fileServer/osf/ww3/rsmc_combined_ww3_20260915.nc"
curl -L -o "data/incois_osf_pfz/osf_hycom/CURRENTS_IO_20260915.nc" \
  "https://incois.gov.in/thredds/fileServer/osf/currents/CURRENTS_IO_20260915.nc"
```

**Prefer the subset.** NCSS is enabled (`/thredds/ncss/grid/…`, confirmed against `dataset.xml`:
56 time steps, 901-point latitude axis), so an India-bbox request returns tens of MB instead of 16 GB
for the pair:

```bash
curl -L -o ww3_india.nc "https://incois.gov.in/thredds/ncss/grid/osf/ww3/rsmc_combined_ww3_20260915.nc\
?var=<names from dataset.xml>&north=26&south=4&west=60&east=100&horizStride=1&accept=netcdf4"
```

Other live OSF catalogs worth knowing, all under `/thredds/catalog/osf/`: `sst`, `sst2`, `chl`,
`k490`, `winds`, `mwh`, `ssg`, `currents2`, plus `/hycom/` (`hycom_sst.nc`, `hycom_sst_ssh.nc`,
`hycom_tchp.nc`). Several of these cover gaps §B otherwise pays a registration for.

Re-run `scripts/extract_osf_pilot.py` after every refresh — the pilot CSVs are derived — and
`backend/scripts/generate_tiles.py` for the wave-height frames.

*Cost: free · Time: 20 min plus transfer · Blocker: none. **Mandatory before any demo** — coverage
guide §8 is right that the expired forecast state silently removes named PS queries.*

### A4 · PFZ history and the missing sectors — guide row 3

Not a procurement problem. `scripts/scrape_pfz_advisories.py` already covers SEC001–SEC014 and
archives to `pfz/history/<date>/`. What is missing is **elapsed days**: `score_pfz_persistence` needs
one run per day. Schedule it now (daily, ~06:00 IST, after INCOIS reissues), then re-run
`backend/scripts/build_all_india_pfz.py`. Every day of delay is a day of persistence data that cannot
be backfilled — the INCOIS WebGIS has no archive endpoint.

*Cost: free · Time: 10 min to schedule · Blocker: the calendar, not access.*

### A5 · Indian district boundaries — guide row 33

`data.gov.in` needs a free API key and publishes district layers inconsistently. The working path is
DataMeet (CC-BY, Census 2011, verified live):

```bash
for ext in shp shx dbf prj; do
  curl -sL -o "data/tier1/boundaries/2011_Dist.$ext" \
    "https://raw.githubusercontent.com/datameet/maps/master/Districts/Census_2011/2011_Dist.$ext"
done
# geopandas reads the shapefile directly; convert to GeoJSON only if a consumer needs it
```

Census 2011 vintage is fine for what this layer does — joining CMFRI / data.gov.in landings by
district for PS-Q7 — and it is **not** a legal boundary source. Label it that way.

*Cost: free · Time: 5 min · Blocker: none.*

### A6 · GEBCO all-India — guide row 25

**Done — and it turned out not to be a form.** `scripts/download_gebco_bathymetry.py`.

The correction: the rebuilt Grid Subsetting App is a Next.js front end over a small REST
service, so there is no clicking to do. `POST /api/queue` with the bbox, grid id and format id
returns a basket id; `GET /api/queue/download/{id}` returns the zip once the job has run. Ids
come from `/api/grids` and `/api/formats` and are pinned in the script rather than looked up, so
a renumbering on GEBCO's side fails loudly instead of fetching the wrong grid.

`gebco_2026_n26.0_s4.0_w60.0_e100.0.nc` — 4–26 N / 60–100 E at 15″, 9600 × 5280 cells, 101.5 MB.
880 square degrees, against the 14,400 the grid's own `maximum_area` allows, so it goes through
as one basket. No email address is sent; the basket id is enough to collect the file.

`geospatial.BATHYMETRY_FILE` now prefers this and falls back to the pilot box, so `depth_at_point`
returns GEBCO rather than ETOPO off Kochi, Veraval, Digha, Mumbai and Port Blair — every one of
which fell through to the 1-arcmin grid before. `bathymetry_heatmap_points` derives its stride
from the grid instead of hard-coding 16, which on a 9600-wide grid would have emitted 200k
features; it emits 772.

Still open here: `etopo_all_india_real.nc` is a confirmed duplicate and is still on disk.
Deleting it is the user's call, not the script's.

*Cost: free · Time: done · Blocker: none.*

---

## B. Free, but one registration each

### B1 · MOSDAC fresh SST and chlorophyll — guide rows 9, 11

ISRO's archive, and the reason SST on disk stopped at 2026-08-29 and chlorophyll at March 2026.

**Done on 2026-09-18 — use `python scripts/refresh_mosdac.py`**, which needs only `MOSDAC_USERNAME`
and `MOSDAC_PASSWORD` in `.env`. There *is* a plain REST API after all (`download_api/gettoken`,
`apios/datasets.json`, `download_api/download`); the script calls it directly, and the dataset ids
— which are not guessable from the filenames — are recorded in
`docs/ORCA_Data_Freshness_Contract.md` §6.3. The manual route below is kept only as background on
where the ids and limits come from.

```bash
curl -LO https://www.mosdac.gov.in/software/mdapi.zip     # verified live
unzip mdapi.zip                                            # -> mdapi.py, config.json
# config.json:
#   user_credentials: {username, password}   (MOSDAC account, Keycloak-backed)
#   datasetId: exact Product Name from https://mosdac.gov.in/catalog-app/satellite.php
#   startTime / endTime: YYYY-MM-DD    count: <= 100    boundingBox: "60,4,100,26"
#   skip_user_prompt: true  -> unattended
pip install requests tqdm && python mdapi.py
```

Match `datasetId` to what is already on disk so the loaders keep working: `3RIMG_*_L3B_SST_DLY_*`
(INSAT-3DR daily SST, read by `satellite_loaders`), `E06OCML4AC_*` (EOS-06 ocean colour L4, 25 km),
`E06SCTL4AW_*` (EOS-06 scatterometer wind L4, 12 km). EOS-06 is listed under its mission name
**OCEANSAT-3** in the catalog.

Three operational facts that would otherwise burn a day:
- **Registration is approval-gated** (SAC admin). Submit today even if nobody downloads until next week.
- **General accounts get L2 and above in NRT, but L1 at 3-day latency.** The products above are L3/L4, so NRT applies — an "account not configured for download" message means this, not a bad password.
- **5,000 files/day per user**, and repeated auth failures lock the account.

*Cost: free · Time: 30 min + approval wait · Blocker: approval lag — start it now.*

### B2 · Copernicus Marine — guide rows 18, 19, 20 (**corrected product IDs**)

Credentials already exist on this machine (`~/.copernicusmarine/.copernicusmarine-credentials`) and
the CLI is installed. Use the **global** products, since the `_IND_` ids in the guide do not exist:

```bash
copernicusmarine subset -i cmems_mod_glo_wav_anfc_0.083deg_PT3H-i \
  -x 60 -X 100 -y 4 -Y 26 -v VHM0 -v VMDR -v VTPK \
  -t 2026-09-16 -T 2026-09-23 -o data/tier2/copernicus   # waves — GLOBAL_ANALYSISFORECAST_WAV_001_027

copernicusmarine subset -i cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D \
  -x 60 -X 100 -y 4 -Y 26 -v CHL -t 2026-06-01 -T 2026-09-15 \
  -o data/tier2/copernicus                                # chlorophyll — OCEANCOLOUR_GLO_BGC_L4_NRT_009_102

copernicusmarine subset -i cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.125deg_P1D \
  -x 60 -X 100 -y 4 -Y 26 -v sla -v adt -t 2026-06-01 -T 2026-09-15 \
  -o data/tier2/copernicus                                # sea level — SEALEVEL_GLO_PHY_L4_NRT_008_046
```

**Corrected 2026-09-17 — the first draft of this section named two datasets that would have failed:**

| Draft said | Why it fails | Use instead |
|---|---|---|
| `…-duacs-0.25deg_P1D` (MY) | DUACS moved to 0.125° at the 202411 release. The 0.25° dataset is **404 on the STAC catalog** — it survives only as a stale thumbnail reference inside the product record, with no `rel: item` link | `…-duacs-0.125deg_P1D` |
| the **MY** sea level and chlorophyll datasets, for June–September dates | Multi-year reanalysis lags. MY sea level 0.125° ends **2026-01-16**, MY gapfree chlorophyll ends **2026-09-08** — the date range above returns nothing, or a short file, without erroring in a way you would notice | the **NRT** datasets above: sea level to 2026-09-16, chlorophyll to 2026-09-15, both checked today |

Use MY only for the historical baselines (`compute_sst_chl_trend`, the Gaja replay window), NRT for
anything inside the demo window. The wave dataset needs no change — `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`
covers to 2026-09-26.

Run `copernicusmarine describe -i <product>` before each pull anyway. CMEMS renames dataset-level ids
more often than product-level ones, and **check the temporal extent in that output, not just that the
id resolves** — that is the mistake this table exists to record.

*Cost: free · Time: 20 min · Blocker: none — credentials are already on disk, though
`copernicusmarine` itself is **not installed in `backend/.venv`**; `pip install copernicusmarine`
first.*

### B3 · NASA chlorophyll and SST backups — guide rows 21, 22

One Earthdata Login (`urs.earthdata.nasa.gov`, instant), then the maintained client rather than
hand-rolled CMR paging. Both collections were verified in CMR today:

```bash
pip install earthaccess
python - <<'PY'
import earthaccess
earthaccess.login(persist=True)            # Earthdata Login, or ~/.netrc
for short_name in ("MODISA_L3m_CHL", "MUR-JPL-L4-GLOB-v4.1"):
    granules = earthaccess.search_data(
        short_name=short_name,
        temporal=("2026-08-01", "2026-09-15"),
        bounding_box=(60, 4, 100, 26),
    )
    earthaccess.download(granules, "data/tier2/nasa")
PY
```

This closes the audit's Flag 1 honestly: `nasa_cmr_modis_chl_granules.json` is an *index*, and its
loader correctly reports `held_locally: false`. These are the rasters behind that index. Priority is
genuinely P2 — MOSDAC EOS-06 is the primary Indian chlorophyll source and `correlate_sst_chlorophyll`
already runs off it.

*Cost: free · Time: 20 min · Blocker: none.*

---

## C. Manual or best effort — a human has to read something

### C1 · Tide predictions for the 13 non-pilot ports — guide row 35, **and the expired file**

Two separate problems, and the second is worse:

1. **Coverage:** predictions exist for 5 stations only, so PS-Q3 is unanswerable for Gujarat, Odisha, West Bengal, Andhra, Goa, Karnataka, A&N and Lakshadweep.
2. **Expiry:** `soi_tide_tables_2026.csv` runs 2026-08-30 → **2026-09-08**. It expired eight days ago, so `predict_tides()` has no future extreme to return **for any port, the pilot ones included.** PS-Q3 is broken right now, everywhere.

Survey of India's tide tables are a **priced print/PDF publication**, which is why the file on disk
was derived from Stormglass harmonics rather than from SoI. Keep that path and extend it. The
Stormglass free tier is **10 requests/day**, and one `tide/extremes/point` call returns many days for
one port, so 18 ports is two days on a single key. Refresh the pilot five first:

```bash
curl -s "https://api.stormglass.io/v2/tide/extremes/point?lat=$LAT&lng=$LON&start=$(date +%F)&end=$(date -d '+7 days' +%F)" \
  -H "Authorization: $STORMGLASS_KEY" -o "data/tier2/stormglass/stormglass_tides_$PORT.json"
```

Then regenerate `soi_tide_tables_2026.csv` from those extremes, keeping the provenance string honest:
**derived from Stormglass harmonics, not an SoI publication.** It is already labelled that way in the
audit; do not let the label get lost in the rebuild.

*Cost: free tier · Time: two days elapsed, 30 min of work · Blocker: the 10/day cap. **Highest-priority
item in this document** — it is a live, silent PS-query failure, not a coverage gap.*

### C2 · CMFRI landings by state / district — guide row 45

**Done.** `scripts/extract_cmfri_state_landings.py`.

Neither of the two routes the runbook suggested was needed. data.gov.in's state-wise resources
are older than the booklet, and `camelot`/`tabula` were unnecessary because the state figures are
in the page text, not in ruled tables — `pdfplumber` plus one anchored regex is the whole
extraction. Source is *Marine Fish Landings in India 2024* (CMFRI Booklet Series 24/2025,
`eprints.cmfri.org.in/19094/`).

`cmfri_state_landings.csv` — 12 states, 3.47 million tonnes, which matches the booklet's own
national figure. Each state's narrative paragraph is carried verbatim as `CMFRI_Note`, so a PS-Q7
answer quotes CMFRI on why a year moved rather than ORCA inferring a cause from one number.

Two limits, both stated in the file rather than papered over: it is **one reporting year, not a
trend** — `diagnose_productivity_decline` now returns `verdict: "single-year state record — not a
trend"` at LOW_DATA when it has fewer than three district-years — and Lakshadweep is not in the
booklet, so it is reported as no data rather than as zero.

*Cost: free · Time: done · Blocker: none.*

### C3 · River discharge for PS-Q7 — guide row "River discharge data"

`indiawris.gov.in` did not resolve from this network today, and its data portal is login-gated
regardless. The substitute you already have credentials for is **Copernicus CDS GloFAS**
(`cems-glofas-historical` / `cems-glofas-forecast`) via `cdsapi` — the same account
`data/cyclone_gaja/fetch_gaja.py` uses for ERA5. Point it at the Godavari, Krishna, Mahanadi and
Narmada outlets and you get the freshwater-influx term that PS-Q7's "why did productivity decline"
narrative wants.

*Cost: free · Time: 1 h · Blocker: none if the CDS key still works — re-check `~/.cdsapirc`, it was
not present on this machine.*

### C4 · The two non-dataset gaps the guide lists under "missing but required"

- **All-India MRCC/MRSC station table — done.** `scripts/scrape_icg_sar_stations.py`. Scraped rather than typed: the ICG's own SAR Organisation page lists the hierarchy, and page order *is* the hierarchy, so each MRSC is assigned to the MRCC printed above it instead of being re-derived from geography. **39/39 stations** located; coordinates come from Open-Meteo's keyless gazetteer and are then range-checked against their MRCC's coarse region box, so a geocode that lands in the wrong sea is dropped, not rounded into place. Three MRCCs, not five: Mumbai, Chennai, Sri Vijaya Puram.

  `distress.surface_mrcc_contact` now resolves the caller's position to the nearest station — Porbandar reaches MRSC Jakhau under MRCC Mumbai, not Chennai. **No per-station phone number was invented**: the ICG publishes none, `phone` is null for every station, and the dialable number stays the verified 1554 / VHF 16. A test asserts that every surfaced number is one of those two.

- **Fishing-ban dates — done.** `scripts/refresh_fishing_ban_order.py`, and the runbook was right that a table is a legitimate answer. The DoF order is a **scanned image**, so the two 61-day windows (east 15 Apr – 14 Jun, west 1 Jun – 31 Jul) were read off the scan and transcribed with the file number that identifies them, `j-2103035/1/2026-Fy (E-27594)`. What the script automates is the part that rots: it asks DoF's own CMS whether a newer ban order exists and exits 2 if one has appeared, rather than letting a superseded window tell a fisher the sea is open.

  `geospatial.fishing_ban_status` and `GET /fishing-ban` expose it. Two distinctions it refuses to blur: the coast split reuses the SAR roster's MRCC hierarchy rather than a longitude threshold (the dividing meridian moves with latitude), and inside 12 NM it returns `applies_here: false` with "check your state's Marine Fishing Regulation Act notification" — the central EEZ order does not reach territorial waters.

- **Ecologically sensitive / restricted-water polygons — still open.** The ban dates above close the schedule half of this bullet; the polygon half is untouched. Of the 15 WDPA features on disk only 11 are geofence-usable, several of them Sri Lankan. Sources remain CRZ/ESA notifications from MoEFCC and OSM `protect_class` relations for sites WDPA publishes as points only, which is the method `scripts/build_mpa_geofence.py` already uses for Gulf of Mannar.

---

## Suggested order

1. **C1 tide refresh** and **A3 forecast refresh** — both are live PS-query failures today, not gaps.
2. **B1 MOSDAC registration** — submit before anything else, then walk away; it is the only item with an approval queue.
3. **A4 schedule the PFZ scraper** — every day of delay is unrecoverable persistence data.
4. **A1, A2, A5** — one unattended afternoon; closes six rows and every boundary gap.
5. **B2, B3, A6** — fallback depth. Real, but the primaries already answer.
6. **C4, C2, C3** — manual, parallelisable, hand to whoever is not writing code.

Nothing here needs a paid subscription, and nothing needs a government approval other than MOSDAC.

---

## Procurement log — 2026-09-17

What was actually run, and what it produced. Everything below is on disk now; `data/` stays
gitignored, so the *scripts* are the deliverable — each one is re-runnable and self-checking
(`--self-check` runs the logic with no network and no API quota).

| Item | Script | Result |
|---|---|---|
| **C1 tides** | `scripts/refresh_tide_tables.py` | 130 extremes, 5 stations, **2026-09-16 → 09-22**. `predict_tides` returns RISING/FALLING with HIGH confidence at all five — it returned `UNKNOWN` / LOW_DATA for every port before. Spends 5 of Stormglass's 10 free daily requests. |
| **A1 caches** | `scripts/refresh_openmeteo_caches.py` | 104 locations × marine/weather/lightning, 0 failures. `CACHED_WEATHER_PORTS` / `CACHED_MARINE_PORTS` now glob the files instead of listing six names, so the refresh widening coverage needs no second edit. Visakhapatnam's missing marine cache is closed. |
| **A2 boundaries** | manual WFS | `india_maritime_boundary_lines.geojson` (32 features, `line_type` preserved), `andaman_eez.geojson`. |
| **A3 forecasts** | `scripts/refresh_osf_forecasts.py` | WW3 **303 MB** and currents **83 MB** for 2026-09-15, against 17 GB of expired whole-basin files — NCSS India-bbox subsets, which this machine needs rather than merely prefers (see below). Plus `SST_NIO`, because INCOIS stopped bundling TEMP/SALN/MLD/SSH into the daily HYCOM file. |
| **A4 PFZ** | `scripts/scrape_pfz_advisories.py` | Run for 2026-09-16: 591 nodes, 11 sectors with advisories, 3 cloud-blocked. **Still needs a daily schedule** — see below. |
| **A5 districts** | manual | `2011_Dist.shp` + sidecars (10.2 MB). |
| **B2 Copernicus** | `copernicusmarine` CLI | Installed into `backend/.venv` (2.4.1). SST `thetao` for the whole India bbox to 09-16 (the CMEMS fallback rung was reading an 8-day-old 3.5°-wide file), plus NRT chlorophyll → 09-15 and sea level (`sla`, `adt`) → 09-16. |
| **A6 GEBCO** | `scripts/download_gebco_bathymetry.py` | Not a form after all — the rebuilt subsetting app is REST (`POST /api/queue`, `GET /api/queue/download/{id}`). National 15″ grid, 9600 × 5280, 101.5 MB. `depth_at_point` now answers from GEBCO off Kochi, Veraval, Digha, Mumbai and Port Blair, all of which fell through to 1-arcmin ETOPO before. |
| **C2 CMFRI** | `scripts/extract_cmfri_state_landings.py` | 12 states, 3.47 Mt, matching the booklet's own national figure, with each state's narrative paragraph carried verbatim. One reporting year — `diagnose_productivity_decline` says "single-year state record — not a trend" at LOW_DATA rather than drawing a line through one point. |
| **C4 SAR** | `scripts/scrape_icg_sar_stations.py` | 39/39 MRCC/MRSC stations, hierarchy read from page order, coordinates range-checked against their MRCC's region. Distress routing is positional now. No station phone number invented — 1554 and VHF 16 remain the only dialable numbers, and a test enforces it. |
| **C4 ban** | `scripts/refresh_fishing_ban_order.py` | Two 61-day windows transcribed from the scanned DoF order with its file number; the script re-checks DoF's CMS for a superseding order and exits 2 if it finds one. Exposed as `geospatial.fishing_ban_status` and `GET /fishing-ban` — regulatory status only, never a sail/no-sail verdict. |
| **Wiring** | `satellite_loaders`, `ocean_analytics` | `load_cmems_chl` and `load_cmems_ssh` added, and the SST/chl cascades now rank by freshness. `correlate_sst_chlorophyll` went from 95 co-located cells across a 171-day gap (MEDIUM) to **7009 cells, HIGH, no acquisition gap**. `tide_gauge_observation` falls through to altimetry past the gauge radius, labelled `source_kind: satellite_altimetry` with the gauge-only fields nulled. |

### Three defects the refresh exposed

1. **WW3 timestamps were two days late.** Its axis is `hours since 0001-01-01` on the CF
   `standard` (Julian) calendar; `datetime(1, 1, 1)` is proleptic Gregorian and sits two days
   later. Every decoded step — and every `voyage.wave_height_at()` lookup — was off by 48 h,
   invisibly: the value returned was a real wave height, for the wrong day. Fixed in
   `scripts/extract_osf_pilot.py` and `backend/orca/agents/voyage.py`.
2. **Two readers were pinned to a filename, not a pattern.** `geospatial.HYCOM_FILE` and
   `extract_osf_pilot.HYCOM_NC` named `RSMC_hycom_20260830.nc` outright, so a refresh would have
   left both reading the expired run. Both glob the newest file now, as `voyage` already did.
3. **Four unit tests asserted a particular day's data**, not behaviour — a cloud-suppressed
   SEC006, a one-day PFZ archive, `pamban` as the nearest cache, the uncorrected WW3 epoch. They
   failed the moment the data improved. Rewritten to assert the rule; suite is 406 passed,
   1 skipped.

### Still open

- **A4 needs a scheduler entry.** Creating the Windows task was blocked by this session's
  sandbox, so run it once by hand:
  `schtasks /create /tn "ORCA PFZ daily scrape" /tr "\"<repo>\backend\.venv\Scripts\python.exe\" \"<repo>\scripts\scrape_pfz_advisories.py\"" /sc daily /st 06:15`
  Two snapshots are on record (09-01, 09-16); `score_pfz_persistence` reads a trend, so every
  missed day is unrecoverable.
- **Registrations only you can do:** MOSDAC (B1, approval queue — start it first), NASA Earthdata
  (B3), Copernicus CDS key for GloFAS (C3).
- **Not started:** C3 river discharge (needs a CDS key), and the polygon half of C4 — ecologically
  sensitive and restricted-water layers. Everything else in A, B-without-registration and C is
  closed; see the log rows above.
- **Procured but unwired:** nothing. The CMEMS chlorophyll and sea-level files are read by
  `satellite_loaders.load_cmems_chl` / `load_cmems_ssh` and reach `correlate_sst_chlorophyll` and
  `tide_gauge_observation`.
- **A latent bug this uncovered:** `load_cmems_sst` picked `sorted(glob("cmems_*.nc"))[-1]`, which
  found the `thetao` file only by lexicographic accident. Once chlorophyll and sea-level files
  landed in the same directory it would have handed the chlorophyll grid to the SST reader. Now
  name-filtered and mtime-sorted.
- **One deletion left to you:** `data/tier1/bathymetry/etopo_all_india_real.nc` is a confirmed
  duplicate (12.4 MB) and `etopo_all_india_bathymetry.nc` supersedes it. Not deleted here.

### Disk

`C:` is at **93 % (35 GB free of 476 GB)** after the GEBCO fetch, and the expired forecasts are
17 GB of it:
`data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` (6.9 GB) and
`osf_hycom/RSMC_hycom_20260830.nc` (10.6 GB). Nothing reads them any more — every reader now
takes the newest file. Deleting them is the single largest reclaim available, but it is a
one-way action on data that cannot be re-downloaded in subset form, so it is left for you to
decide.
