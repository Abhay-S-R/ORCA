# ORCA (SIH26176) — Master Dataset List, Verified Aug 2026

This document provides the verified, comprehensive catalog of all data sources required for the ORCA multi-agent marine intelligence platform, categorized by priority and access mechanics.

---

## 1. Quick-Reference Comparison Table

| # | Dataset / Source | Owner / Provider | What it gives ORCA | Access Tier | Free Tier? | Needs Org Permission? | Priority |
|---|---|---|---|---|---|---|---|
| 1 | **MOSDAC Open Data** | ISRO / SAC | SST, ocean color, wind vectors, ocean currents, salinity (derived products) | Anonymous | ✅ Free, no login | ❌ No | **P0** |
| 2 | **MOSDAC Registered (NRT/API/SFTP)** | ISRO / SAC | Near-real-time satellite passes & programmatic bulk pull | Registered (General/Privileged) | ⚠️ Free but gated | ✅ Yes — SignUp + admin email approval | **P0** |
| 3 | **INCOIS ERDDAP & LAS** (`erddap.incois.gov.in`, `las.incois.gov.in`) | INCOIS / MoES | RESTful, OPeNDAP, JSON, CSV, NetCDF programmatic access to oceanographic, buoy & satellite data | Public server | ✅ Free, open access | ❌ No — instant programmatic REST queries | **P0** |
| 4 | **Open-Meteo Marine API** | Open-Meteo (NOAA/ECMWF/DWD) | Wave height, direction, period, swell waves, ocean current velocity & direction | Public REST API | ✅ **100% Free, zero API key** | ❌ No | **P0** |
| 5 | **Marine Regions (VLIZ) Geodatabase** | Flanders Marine Institute | Authoritative EEZ, territorial sea, contiguous zone, and India–Sri Lanka IMBL coordinates | Public download | ✅ Free | ❌ No — direct shapefile download | **P0** |
| 6 | **Protected Planet / WDPA** | UNEP-WCMC / IUCN | Marine Protected Area boundary polygons (e.g. Gulf of Mannar Marine National Park) | Public download | ✅ Free | ❌ No — direct shapefile download | **P0** |
| 7 | **Tide Predictions & Gauges** | Survey of India / INCOIS | High/low tide times and tidal water levels along Indian coast (Survey of India tables + INCOIS gauges) | Public download / portal | ✅ Free | ⚠️ No — downloadable tables; Stormglass.io (10 req/day) as API fallback | **P0** |
| 8 | **Copernicus Marine (CMEMS)** | EU / Mercator Ocean | Global ocean reanalysis (SST, currents, salinity, sea level, waves) — mature API | Registered | ✅ Free | ✅ Yes — instant self-serve signup | **P0 (Fallback)** |
| 9 | **NASA Ocean Color (OB.DAAC)** | NASA | Chlorophyll-a concentration, SST, remote-sensing reflectance | Earthdata Login | ✅ Free | ✅ Yes — instant self-serve (Earthdata) | **P0 (Fallback)** |
| 10 | **Bhuvan / VEDAS** | ISRO / NRSC | Geoportal layers (PFZ, thematic ocean layers, coastal land use) | Registered | ⚠️ Free but gated | ✅ Yes — separate signup from MOSDAC | **P0** |
| 11 | **INCOIS PFZ Advisory (WebGIS/Text)** | INCOIS / MoES | Potential Fishing Zone coordinates (~1,223 coastal nodes) | Public page | ✅ Free, no login | ⚠️ View-only; scraping or direct email needed for bulk feed | **P1** |
| 12 | **INCOIS Ocean State Forecast (OSF)** | INCOIS / MoES | Wave height, currents, SST, mixed layer depth, wind | Public page | ✅ Free | ⚠️ Available on portal / ERDDAP | **P1** |
| 13 | **INCOIS Hazard Alerts** | INCOIS / MoES | Operational bulletins for Tsunami, Storm Surge, High Wave alerts | Public | ✅ Free | ⚠️ Bulletins / feed scraping | **P1** |
| 14 | **IMD Cyclone & Weather Warnings** | IMD / MoES | Cyclone tracks, colour-coded warnings, district-wise alerts (4×/day) via CAP feed | Public bulletins / CAP | ✅ Free | ⚠️ CAP feed integration | **P1** |
| 15 | **IMD Damini / Lightning Nowcast** | IMD / IITM | Real-time lightning alerts and thunderstorm nowcasting | Public feed / Damini app | ✅ Free | ⚠️ API/feed endpoint | **P1** |
| 16 | **GEBCO Global Bathymetry Grid** | IHO / IOC UNESCO | 15 arc-second gridded ocean depth data (NetCDF/GeoTIFF) — prerequisite for vessel routing | Public download | ✅ Free | ❌ No — direct download from `gebco.net` | **P1** |
| 17 | **data.gov.in (Fisheries Statistics)** | Govt of India (OGD) | Historical fish catch/landing statistics by district/state (for catch-decline root cause query) | Public / Registered | ✅ Mostly free | ⚠️ Open download / OGD account | **P1** |
| 18 | **INCOIS Sagar Vani** | INCOIS / MoES | Multi-channel advisory dissemination (reference architecture for regional SMS/voice push) | N/A | N/A | ℹ️ Architectural reference model | **Ref** |
| 19 | **DAT-SG / Sagarmitra** | ISRO + Coast Guard | Distress-alert transmitter handoff integration point | N/A | N/A | ℹ️ Emergency handoff reference | **Ref** |
| 20 | **CMFRI Catch/Landing Time-Series** | ICAR-CMFRI | Granular historical fish landing time-series and published PFZ validation studies | Publication / Request | ⚠️ Mixed | ✅ Yes — direct institutional request | **P2** |
| 21 | **Global Fishing Watch (GFW)** | GFW (Oceana/Google) | Vessel AIS tracking, fishing effort density | API Token | ✅ Free tier, rate-limited | ✅ Yes — instant self-serve token | **P3 (Deferred)** |

---

## 2. Deep Analysis of Critical Additions & Fixes

### 🌟 1. INCOIS ERDDAP (`erddap.incois.gov.in`) — High-Value Discovery
- **Why it matters:** Prior planning assumed INCOIS data was strictly locked behind HTML/JSP WebGIS pages requiring fragile scraping. INCOIS operates an active **ERDDAP server**, which provides RESTful, machine-readable data subsets (JSON, CSV, NetCDF) with standard OPeNDAP and REST query parameters.
- **Action:** Query `erddap.incois.gov.in/erddap/` immediately in Phase 0 to identify available datasets (buoy data, OSF parameters, satellite products). This could eliminate significant scraping overhead.

### 🌊 2. Open-Meteo Marine API — Zero-Friction Weather Foundation
- **Why it matters:** 100% free, requires **no API key**, and provides instant global wave height, swell period, direction, and ocean current velocity via simple HTTP GET requests.
- **Endpoint:** `https://marine-api.open-meteo.com/v1/marine?latitude=8.8&longitude=78.1&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity`
- **Role:** Primary live data provider for the Weather Intelligence and Risk Assessment agents.

### ⏱️ 3. Tidal Prediction Data (Survey of India + Stormglass Fallback)
- **Why it matters:** Directly addresses **PS Query #3** (*"What are the tide, weather, and sea conditions near my fishing location?"*), which was previously missing from the dataset catalog.
- **Sources:**
  1. *Survey of India:* Official Indian Tide Tables (published annually/monthly).
  2. *INCOIS TEWS Tide Gauges:* Operational coastal tide gauge network.
  3. *Stormglass.io:* Developer API fallback offering tidal height extremes and hourly tide predictions (free tier: 10 requests/day).

### 🗺️ 4. GEBCO Global Bathymetry Grid
- **Why it matters:** Directly required for **PS Query #6** (*"What is the safest route for a fishing vessel considering weather and sea-state conditions?"*). A routing algorithm that only evaluates wave heights but ignores shallow water hazards is unsafe. GEBCO provides 15 arc-second gridded depth data for calculating safe navigable depth corridors.

### ⚡ 5. IMD Damini / Lightning Feed
- **Why it matters:** Required for **PS Query #4** (*"Are there any lightning or cyclone alerts in my area?"*). IMD/IITM operates the Damini lightning nowcasting system, providing 15-minute lead-time lightning strike warnings.

---

## 3. Clear Priority Execution Stack

```
═══════════════════════════════════════════════════════════════════════════
P0 — MUST ACTION THIS WEEK (Pre-Hackathon Foundation)
═══════════════════════════════════════════════════════════════════════════
├── 1. Register MOSDAC (mosdac.gov.in) — initiate signup immediately (longest approval lag)
├── 2. Register Bhuvan / VEDAS (bhuvan.nrsc.gov.in)
├── 3. Query INCOIS ERDDAP (erddap.incois.gov.in) to catalog machine-readable endpoints
├── 4. Download Marine Regions EEZ/IMBL shapefiles (marineregions.org/downloads.php)
├── 5. Download WDPA Marine Protected Area polygons (protectedplanet.net)
├── 6. Download GEBCO 15 arc-second bathymetry grid for South Tamil Nadu sector (gebco.net)
├── 7. Download Survey of India monthly tide tables for coastal nodes
├── 8. Register instant fallbacks: Copernicus Marine (CMEMS) + NASA Earthdata (instant approval)
└── 9. Test Open-Meteo Marine API with sample coordinates (Thoothukudi: 8.80°N, 78.14°E)

═══════════════════════════════════════════════════════════════════════════
P1 — NEEDED FOR FULL 8-QUERY DEMO EXECUTION
═══════════════════════════════════════════════════════════════════════════
├── 10. Implement INCOIS PFZ text parser / scraper (with fallback pre-cached sector CSV)
├── 11. Connect IMD CAP feed for cyclone bulletins and colour-coded district alerts
├── 12. Connect IMD Damini / nowcast endpoints for lightning warning evaluation
├── 13. Index data.gov.in marine catch statistics for pilot sector historical analysis
└── 14. Pre-download historical "Cyclone Gaja" replay dataset for off-season hazard testing

═══════════════════════════════════════════════════════════════════════════
P2 — BEST-EFFORT / PARALLEL (Do not block build)
═══════════════════════════════════════════════════════════════════════════
├── 15. Send formal request to ESSO-INCOIS for official structured PFZ bulk feed
└── 16. Request CMFRI historical fish landing publications for South Tamil Nadu

═══════════════════════════════════════════════════════════════════════════
P3 — DEFERRED / OUT OF MVP SCOPE
═══════════════════════════════════════════════════════════════════════════
├── 17. Global Fishing Watch API (live AIS vessel tracking — not required for 8 official queries)
└── 18. Live DAT-SG hardware distress relay integration (keep purely as architectural reference)
```

---

## 4. Copy-Paste Request Templates

### 📧 MOSDAC Access Request (mosdac.gov.in)
- **Account Type:** Registered General User
- **Requested Capabilities:** API / SFTP programmatic download credentials
- **Standing Order:** Near-real-time SST, Ocean Color (Oceansat-3 / INSAT-3DR) covering Gulf of Mannar & Palk Bay (8.0°N–10.5°N, 77.5°E–80.0°E).

### 📧 INCOIS Formal Data Request (ESSO-INCOIS Hyderabad)
- **Subject:** Data Feed Request for SIH 2026 — PS SIH26176 (ORCA Platform)
- **Body:** Requesting (1) documented REST/ERDDAP endpoint or bulk structured text feed for PFZ advisories for South Tamil Nadu and North Tamil Nadu coastal sectors, and (2) programmatic Ocean State Forecast (OSF) time-series feeds for wave and current nowcasts. Mentioning participation in SIH 2026 under the ISRO problem statement.

