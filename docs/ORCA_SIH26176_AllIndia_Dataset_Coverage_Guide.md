# ORCA — SIH26176 All-India Coverage & Dataset Collection Guide

> **Project:** SIH 2026 · Problem Statement #SIH26176 · ISRO / Marine Ecosystem Reasoning  
> **Purpose:** Complete reference for expanding ORCA from the South Tamil Nadu pilot to full  
> all-India coastal coverage and ensuring every PS benchmark query is answered correctly.  
> **Share this with:** Every teammate working on data collection, backend agents, or testing.

---

## Section 0 — Data Audit: What Already Exists in `e:/ORCA/data/`

> ⚠️ **Read this before downloading anything.** A lot of data is already on disk.
> The column **ON-DISK STATUS** in every table below tells you what to skip.

### Legend used throughout this document
| Icon | Meaning |
|------|---------|
| ✅ ON DISK + WIRED | File exists AND the backend reads it — works today |
| ⚙️ ON DISK, NOT WIRED | File exists on disk BUT no agent reads it yet — needs code change |
| ❌ MISSING | File does not exist — must be downloaded |
| 🔴 LIVE API | No file needed — fetched live at query time |

### Quick Summary
| Category | Count | Action needed |
|----------|-------|---------------|
| ✅ Present & wired (works now) | 22 datasets | None — don't re-download |
| ⚙️ Present on disk, not wired | 11 datasets | Code fix only — zero downloads |
| ❌ Completely missing | ~12 dataset groups | Download from URLs in tables below |

**The biggest opportunity:** HYCOM currents (10.5 GB), WW3 wave forecast (6.9 GB), MOSDAC SST `.h5` files, and EOS-06 Chlorophyll `.nc` files are **ALL already on disk** — they just need code wiring. Fix those first before fetching anything new.

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
| PFZ Historical Archive — 1 date only | ⚙️ ON DISK, NOT WIRED | INCOIS OSF | Same portal → Archive tab | JSON | `data/incois_osf_pfz/pfz/history/20260901/` ← only 1 date, need ≥7 |
| PFZ History — 6 more dates needed | ❌ MISSING | INCOIS OSF | https://osf.incois.gov.in → Archive | JSON | `data/incois_osf_pfz/pfz/history/YYYYMMDD/` |
| PFZ Sectors SEC001–SEC005, SEC007–SEC011 | ❌ MISSING | INCOIS OSF | Same portal | JSON | `data/incois_osf_pfz/pfz/` |
| SST — INSAT-3D (17 files, Aug 13–29) | ⚙️ ON DISK, NOT WIRED | MOSDAC | https://mosdac.gov.in → INSAT-3D → SST | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/3RIMG_*.h5` |
| SST — Aug–Sep 2026 (fresh) | ❌ MISSING | MOSDAC | Same portal, pick Aug 30 – today | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/` |
| Chlorophyll — EOS-06 (10 files, March 2026) | ⚙️ ON DISK, NOT WIRED | MOSDAC | https://mosdac.gov.in → EOS-06 → Ocean Colour | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` |
| Chlorophyll — Jul–Sep 2026 (fresh) | ❌ MISSING | MOSDAC | Same portal, pick Jul–Sep 2026 | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/` |
| Chlorophyll backup | ❌ MISSING | NASA OBPG MODIS | https://oceancolor.gsfc.nasa.gov/l3/ | NetCDF | `data/tier2/nasa/` |

**All 11 PFZ Sectors:**

| Sector | Region |
|--------|--------|
| SEC001 | Gujarat coast (Arabian Sea, north) |
| SEC002 | Maharashtra coast |
| SEC003 | Goa + Karnataka coast |
| SEC004 | Kerala coast |
| SEC005 | Tamil Nadu north + Pondicherry |
| SEC006 | Tamil Nadu south + Gulf of Mannar ← **only this one active today** |
| SEC007 | Andhra Pradesh coast |
| SEC008 | Odisha coast |
| SEC009 | West Bengal coast |
| SEC010 | Andaman & Nicobar Islands |
| SEC011 | Lakshadweep |

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
| WaveWatch III (WW3) NetCDF | ⚙️ ON DISK, NOT WIRED | INCOIS OSF | https://osf.incois.gov.in → Wave | NetCDF | `data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` (6.9 GB) |
| WW3 latest point forecasts | ⚙️ ON DISK, NOT WIRED | INCOIS OSF | Same | GeoJSON/CSV | `data/incois_osf_pfz/osf_ww3/ww3_latest_points.geojson` |
| Open-Meteo Marine — chennai, kochi, mumbai, pamban, thoothukudi | ✅ ON DISK + WIRED | Open-Meteo | https://marine-api.open-meteo.com/v1/marine | JSON | `data/tier1/ocean/openmeteo_marine_*.json` |
| Open-Meteo Marine — 16 new ports | ❌ MISSING | Open-Meteo | Same (free, no key) | JSON | `data/tier1/ocean/openmeteo_marine_<port>.json` |
| Open-Meteo Weather — 6 existing ports | ✅ ON DISK + WIRED | Open-Meteo | https://api.open-meteo.com/v1/forecast | JSON | `data/tier1/weather/openmeteo_weather_*.json` |
| Open-Meteo Weather — 16 new ports | ❌ MISSING | Open-Meteo | Same (free, no key) | JSON | `data/tier1/weather/openmeteo_weather_<port>.json` |
| EOS-06 ScatSat Wind (11 daily files) | ⚙️ ON DISK, NOT WIRED | MOSDAC | https://mosdac.gov.in → EOS-06 → Wind | NetCDF | `data/tier3/mosdac/Wind/E06SCTL4AW_*.nc` |
| ERA5 historical wind (Thoothukudi only) | ⚙️ ON DISK, NOT WIRED | Open-Meteo archive | https://archive-api.open-meteo.com/v1/era5 | JSON | `data/tier1/weather/era5_historical_thoothukudi_30d.json` |

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
| HYCOM current point forecasts (8 ports) | ⚙️ ON DISK, NOT WIRED | INCOIS OSF | Already on disk | GeoJSON | `data/incois_osf_pfz/osf_hycom/hycom_latest_points.geojson` |
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
| WW3 NetCDF wave forecast | ⚙️ ON DISK, NOT WIRED | INCOIS OSF | Already downloaded | NetCDF | `data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` (6.9 GB) |
| HYCOM current vectors NetCDF | ⚙️ ON DISK, NOT WIRED | INCOIS | Already downloaded | NetCDF | `data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc` (10.5 GB) |

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
| SST INSAT-3D (Aug 13–29, 17 files) | ⚙️ ON DISK, NOT WIRED | MOSDAC | Already downloaded | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/3RIMG_*.h5` |
| Chlorophyll EOS-06 (March 2026, 10 files) | ⚙️ ON DISK, NOT WIRED | MOSDAC | Already downloaded | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` — **stale, 6 months old** |
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

| # | Dataset | On-Disk Status | Source Portal | Direct URL | Free? | Reg? | Format | Repo Path |
|---|---------|---------------|--------------|------------|-------|------|--------|-----------|
| 1 | PFZ Daily Advisories | ✅ | INCOIS OSF | https://osf.incois.gov.in | ✅ | No | JSON | `data/incois_osf_pfz/pfz/incois_pfz_live_advisories.geojson` |
| 2 | PFZ History — 1 date | ⚙️ | INCOIS OSF | Same → Archive | ✅ | No | JSON | `data/incois_osf_pfz/pfz/history/20260901/` |
| 3 | PFZ History — 6 more dates + all sectors | ❌ | INCOIS OSF | Same → Archive | ✅ | No | JSON | `data/incois_osf_pfz/pfz/history/` |
| 4 | HYCOM current NetCDF (10.5 GB) | ⚙️ | INCOIS OSF | https://osf.incois.gov.in → Ocean Current | ✅ | No | NetCDF | `data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc` |
| 5 | HYCOM current point GeoJSON (8 ports) | ⚙️ | INCOIS OSF | Already on disk | ✅ | No | GeoJSON | `data/incois_osf_pfz/osf_hycom/hycom_latest_points.geojson` |
| 6 | WW3 wave NetCDF (6.9 GB) | ⚙️ | INCOIS OSF | https://osf.incois.gov.in → Wave | ✅ | No | NetCDF | `data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` |
| 7 | WW3 point GeoJSON | ⚙️ | INCOIS OSF | Already on disk | ✅ | No | GeoJSON | `data/incois_osf_pfz/osf_ww3/ww3_latest_points.geojson` |
| 8 | INSAT-3D SST (17 files, Aug 13–29) | ⚙️ | MOSDAC | https://mosdac.gov.in → INSAT-3D → SST | ✅ | Yes | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/3RIMG_*.h5` |
| 9 | SST fresh files (Aug 30 – today) | ❌ | MOSDAC | Same portal | ✅ | Yes | HDF5 `.h5` | `data/tier3/mosdac/Sea surface temp/` |
| 10 | EOS-06 Chlorophyll (10 files, March 2026) | ⚙️ | MOSDAC | https://mosdac.gov.in → EOS-06 → Ocean Colour | ✅ | Yes | NetCDF `.nc` | `data/tier3/mosdac/chlorophyll/E06OCML4AC_*.nc` |
| 11 | Chlorophyll fresh (Jul–Sep 2026) | ❌ | MOSDAC | Same portal | ✅ | Yes | NetCDF | `data/tier3/mosdac/chlorophyll/` |
| 12 | EOS-06 ScatSat Wind (11 files) | ⚙️ | MOSDAC | https://mosdac.gov.in → EOS-06 → Wind | ✅ | Yes | NetCDF | `data/tier3/mosdac/Wind/E06SCTL4AW_*.nc` |
| 13 | Open-Meteo Marine — 5 existing ports | ✅ | Open-Meteo | https://marine-api.open-meteo.com/v1/marine | ✅ | No | JSON | `data/tier1/ocean/openmeteo_marine_*.json` |
| 14 | Open-Meteo Marine — 16 new ports | ❌ | Open-Meteo | Same (free) | ✅ | No | JSON | `data/tier1/ocean/openmeteo_marine_<port>.json` |
| 15 | Open-Meteo Weather — 6 existing ports | ✅ | Open-Meteo | https://api.open-meteo.com/v1/forecast | ✅ | No | JSON | `data/tier1/weather/openmeteo_weather_*.json` |
| 16 | Open-Meteo Weather — 16 new ports | ❌ | Open-Meteo | Same (free) | ✅ | No | JSON | `data/tier1/weather/openmeteo_weather_<port>.json` |
| 17 | CMEMS SST / Physics | ❌ | Copernicus | https://data.marine.copernicus.eu → `GLOBAL_ANALYSISFORECAST_PHY_001_024` | ✅ | Yes (EU) | NetCDF | `data/tier2/copernicus/` |
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
| C1 | `backend/orca/data/loaders.py` | Add 120+ all-India place names to `_PILOT_GAZETTEER` | All | 🔴 Critical |
| C2 | `backend/orca/data/loaders.py` | Add 15 new ports to `CACHED_MARINE_PORTS` and `CACHED_WEATHER_PORTS` | #2, #3 | 🔴 Critical |
| C3 | `backend/orca/agents/ocean_analytics.py` | Wire `hycom_latest_points.geojson` → `current_speed_at()` function | #1, #3 | 🔴 Critical |
| C4 | `backend/orca/agents/ocean_analytics.py` | Wire MOSDAC INSAT-3D SST `.h5` files → HDF5 loader | #1, #7, DATA LIMITED fix | 🔴 Critical |
| C5 | `backend/orca/agents/ocean_analytics.py` | Expand from `_PILOT_SECTOR = "SEC006"` to all 11 sectors by lat/lon | #1 | 🟡 High |
| C6 | `backend/orca/agents/reporting.py` | Add informational query path — return value + citation, not just GO/NO-GO | #3 | 🟡 High |
| C7 | `backend/orca/agents/ocean_analytics.py` | Fetch + wire chlorophyll EOS-06 `.nc` → correlate with SST | #7, DATA LIMITED fix | 🟡 High |
| C8 | `backend/orca/data/loaders.py` | Add India district boundary shapefile loader | #4 (CAP alerts) | 🟡 High |
| C9 | `backend/orca/api/geospatial_routes.py` | Add missing boundary files (India-Pakistan, Bangladesh, Andaman) | #5 | 🟡 High |
| C10 | `backend/orca/agents/` | Add `route_planner.py` agent — waypoint routing with bathymetry + geofence | #6 | 🟠 Medium |
| C11 | `backend/orca/agents/reporting.py` | Add CAP 1.2 payload formatter for coastal authority persona | #8, authority persona | 🟠 Medium |
| C12 | `backend/orca/agents/voice.py` | Integrate ISRO Bhashini API for regional language TTS | Fisherman persona | 🟠 Medium |
| C13 | `backend/orca/agents/ocean_analytics.py` | Add CMFRI catch trend reader + anomaly correlator | #7 | 🟠 Medium |
| C14 | All agents | Ensure all confidence tiers include provenance + freshness for every output | Meta / trust | 🟡 High |

---

## Section 6 — What "DATA LIMITED" Means and How to Fix It

The DATA LIMITED badge appears when **any** agent returns `LOW_DATA` confidence. Here is every root cause and its fix:

| Root Cause | Agent | Fix |
|-----------|-------|-----|
| MOSDAC SST files not read by code | `ocean_analytics` | Wire HDF5 loader (C4) |
| Only 1 PFZ history folder | `ocean_analytics` | Download 7 days history for all 11 sectors |
| MOSDAC Chlorophyll files stale (March) | `ocean_analytics` | Fetch Jul–Sep 2026 files from MOSDAC |
| Live Open-Meteo fails → stale Aug 30 cache | `weather_intelligence` | Refresh cached files for all ports |
| CMEMS SST/currents for non-pilot regions | `ocean_analytics` | Download CMEMS files for full India bbox |

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

*Document prepared: 2026-09-12 · ORCA / SIH26176 · All-India expansion from South Tamil Nadu pilot*  
*File: `e:/ORCA/docs/ORCA_SIH26176_AllIndia_Dataset_Coverage_Guide.md`*
