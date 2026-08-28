# ORCA (SIH26176) — Master Dataset & API Architecture Catalog

**Verified & Grounded:** August 2026  
**System Target:** Multi-Agent Marine Intelligence & Conversational Decision Support Platform  

---

## 1. Access Classification Taxonomy

All 21 datasets and APIs are classified hierarchically into **4 Access Tiers**, sub-divided by **7 Marine Functional Domains**:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       ORCA DATA ACCESS HIERARCHY                           │
├────────────────────────────────────────────────────────────────────────────┤
│ 🟢 TIER 1: 100% Free & Open Access (Zero Friction / Public Endpoints)      │
│ 🔵 TIER 2: Free Self-Serve Registration (Instant Sign-Up / API Tokens)     │
│ 🟠 TIER 3: Gated Government Registration & Request Access (Approval Lag)   │
│ 🟣 TIER 4: Architectural Reference & Emergency Integration Points          │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Comprehensive Catalog by Access Tier & Functionality

---

### 🟢 TIER 1: 100% Free & Open Access (No Registration / Instant API & Direct Downloads)

Zero-friction datasets that can be downloaded or integrated programmatically into the agent pipeline immediately without API keys or admin approvals.

#### 1.1 🌊 Marine Weather, Sea State & Hydrodynamics
* **Dataset / API:** **Open-Meteo Marine Weather API**
  * **Provider:** Open-Meteo / Global NWP blend (NOAA GFS Wave, ECMWF WAM, DWD ICON Wave)
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Significant wave height ($H_s$), wave direction, wave period ($T_p$), swell wave height/period/direction, wind wave height, ocean current velocity ($m/s$) and direction ($^\circ$).
  * **Format / Protocol:** REST JSON via HTTP GET
  * **Endpoint:** `https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity`
  * **Relevance / Priority:** **P0 Core** — Zero-friction, highly reliable foundation for live sea-state queries and vessel safety scoring.

#### 1.2 🛰️ Earth Observation & In-Situ Ocean Analytics
* **Dataset / API:** **INCOIS ERDDAP Data Server**
  * **Provider:** ESSO-INCOIS (Ministry of Earth Sciences, Govt of India)
  * **Target Agent:** `Marine Data Discovery Agent`, `Ocean Analytics Agent`
  * **Parameters Provided:** In-situ ocean observational buoy telemetry (SST, salinity, currents), model forecast grids, satellite-derived SST/chlorophyll parameters.
  * **Format / Protocol:** REST, OPeNDAP, JSON, CSV, NetCDF, GeoTIFF
  * **Endpoint:** `https://erddap.incois.gov.in/erddap/`
  * **Relevance / Priority:** **P0 Core** — High-value discovery; provides machine-readable INCOIS data without fragile HTML scraping.

* **Dataset / API:** **MOSDAC Open Data Portal**
  * **Provider:** Space Applications Centre (SAC / ISRO)
  * **Target Agent:** `Marine Data Discovery Agent`, `Ocean Analytics Agent`
  * **Parameters Provided:** Derived daily/weekly satellite products: SST (Oceansat-3 / INSAT-3D/3DR), ocean color, wind vectors (ScatSat-1 archives), sea surface salinity.
  * **Format / Protocol:** NetCDF4, HDF5, GeoTIFF
  * **Endpoint:** `https://mosdac.gov.in` (Open Data Catalog)
  * **Relevance / Priority:** **P0 Core** — Authoritative ISRO Earth Observation products backing scientific evidence claims.

#### 1.3 ⏱️ Tides, Water Levels & Coastal Dynamics
* **Dataset / API:** **Survey of India Tidal Tables & INCOIS Tide Gauges**
  * **Provider:** Survey of India (SOI) & INCOIS Tsunami Early Warning Centre
  * **Target Agent:** `Ocean Analytics Agent`, `Geospatial Reasoning Agent`
  * **Parameters Provided:** High tide / low tide times, astronomical tide heights, sea level anomalies, hourly tidal predictions across Indian coastal stations.
  * **Format / Protocol:** Downloadable Tables (ASCII/PDF/CSV) & Web Portal
  * **Endpoint:** `https://www.surveyofindia.gov.in/` & `https://tsunami.incois.gov.in/TEWS/TGMap.jsp`
  * **Relevance / Priority:** **P0 Core** — Directly answers **PS Query #3** (*"What are the tide, weather, and sea conditions...?"*).

#### 1.4 🗺️ Geospatial Boundaries & Ocean Bathymetry
* **Dataset / API:** **Marine Regions (VLIZ) Maritime Boundaries Geodatabase**
  * **Provider:** Flanders Marine Institute (VLIZ)
  * **Target Agent:** `Geospatial Reasoning Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Authoritative global polygons for Exclusive Economic Zones (EEZ 200 NM), Territorial Seas (12 NM), Contiguous Zones, and India–Sri Lanka Palk Strait IMBL coordinates.
  * **Format / Protocol:** Shapefile, GeoJSON
  * **Endpoint:** `https://www.marineregions.org/downloads.php`
  * **Relevance / Priority:** **P0 Core** — Essential for hard geofencing constraints; prevents accidental boundary crossing into international waters.

* **Dataset / API:** **Protected Planet / World Database on Protected Areas (WDPA)**
  * **Provider:** UNEP-WCMC & IUCN
  * **Target Agent:** `Geospatial Reasoning Agent`, `Visualization Agent`
  * **Parameters Provided:** Boundary polygons and metadata for Marine Protected Areas (MPAs) and ecologically sensitive zones (e.g. Gulf of Mannar Marine National Park).
  * **Format / Protocol:** Shapefile, GeoJSON
  * **Endpoint:** `https://www.protectedplanet.net/en/thematic-areas/marine-protected-areas`
  * **Relevance / Priority:** **P0 Core** — Directly implements the PS requirement for MPA notifications and restricted zone geofencing.

* **Dataset / API:** **GEBCO Global Bathymetry Grid**
  * **Provider:** General Bathymetric Chart of the Oceans (IHO / IOC UNESCO)
  * **Target Agent:** `Geospatial Reasoning Agent`
  * **Parameters Provided:** 15 arc-second gridded ocean depth / bathymetric terrain elevation.
  * **Format / Protocol:** NetCDF, GeoTIFF (subsettable by bounding box)
  * **Endpoint:** `https://download.gebco.net/`
  * **Relevance / Priority:** **P1 Core** — Prerequisite for depth-safe route optimization; prevents routing fishing vessels through dangerous shallow shoals.

#### 1.5 🐟 Fisheries Intelligence & Potential Fishing Zones
* **Dataset / API:** **INCOIS PFZ Advisory (WebGIS / Text Dissemination)**
  * **Provider:** ESSO-INCOIS (Ministry of Earth Sciences)
  * **Target Agent:** `Marine Data Discovery Agent`, `Ocean Analytics Agent`
  * **Parameters Provided:** Lat/Long coordinates of Potential Fishing Zones (14 coastal sectors, ~1,223 coastal nodes), bearing and distance from landing centers, validity windows.
  * **Format / Protocol:** HTML / WebGIS / Plain text tabular bulletin
  * **Endpoint:** `https://incois.gov.in/MarineFisheries/PfzWebGis`
  * **Relevance / Priority:** **P1 Core** — Answers **PS Query #1** (*"Where is the nearest Potential Fishing Zone today?"*); fallback to pre-parsed regional CSV.

#### 1.6 ⚠️ Marine Hazards, Weather Warnings & Lightning
* **Dataset / API:** **INCOIS Hazard Alerts & Ocean State Warnings**
  * **Provider:** ESSO-INCOIS
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Tsunami warnings, storm surge alerts, high wave (swell surge / Kallakkadal) advisories, coastal roughness warnings.
  * **Format / Protocol:** Public web bulletins, RSS/XML
  * **Endpoint:** `https://incois.gov.in/portal/osf/osf.jsp`
  * **Relevance / Priority:** **P1 Core** — Core safety gating inputs.

* **Dataset / API:** **IMD Cyclone Bulletins & CAP Feed**
  * **Provider:** India Meteorological Department (IMD / MoES)
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Tropical cyclone genesis, track coordinates, intensity categories, colour-coded district coastal warnings (issued 4× daily).
  * **Format / Protocol:** Common Alerting Protocol (CAP XML) & Web Bulletins
  * **Endpoint:** `https://mausam.imd.gov.in/` & National NDMA/IMD CAP Alert Portal
  * **Relevance / Priority:** **P1 Core** — Answers **PS Query #4** (*"Any lightning or cyclone alerts in my area?"*).

* **Dataset / API:** **IMD Damini / Lightning Nowcast Feed**
  * **Provider:** Indian Institute of Tropical Meteorology (IITM) / IMD
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Real-time lightning strike locations and 15–30 minute convective thunderstorm nowcasts.
  * **Format / Protocol:** Mobile API / Web Nowcast feed
  * **Endpoint:** `https://damini.tropmet.res.in/`
  * **Relevance / Priority:** **P1 Core** — Critical fisherman safety requirement during pre-departure planning.

* **Dataset / API:** **data.gov.in Fisheries Catch Statistics**
  * **Provider:** Department of Fisheries / Open Government Data (OGD) India
  * **Target Agent:** `Ocean Analytics Agent`, `Reporting Agent`
  * **Parameters Provided:** Historical district-wise and state-wise marine fish landings, species composition, and annual catch trends.
  * **Format / Protocol:** CSV, JSON REST
  * **Endpoint:** `https://data.gov.in/`
  * **Relevance / Priority:** **P1 (Diagnostic)** — Answers **PS Query #7** (*"Why has fish productivity declined in a particular coastal region?"*).

---

### 🔵 TIER 2: Free Self-Serve Registration (Instant Sign-Up / Free API Tokens)

Services that require a free user account or API key, but grant **instant access** without waiting for manual administrator approval.

#### 2.1 🛰️ Global Earth Observation & Ocean Reanalysis (Fallbacks)
* **Dataset / API:** **Copernicus Marine Service (CMEMS)**
  * **Provider:** European Union / Mercator Ocean International
  * **Target Agent:** `Ocean Analytics Agent`, `Marine Data Discovery Agent`
  * **Parameters Provided:** Global multi-satellite SST reanalysis ($0.05^\circ$), surface/subsurface ocean currents, salinity, sea surface height anomalies, wave spectra.
  * **Format / Protocol:** REST API, OPeNDAP, WMS, NetCDF download via Python `copernicusmarine` CLI
  * **Endpoint:** `https://marine.copernicus.eu/`
  * **Relevance / Priority:** **P0 (Fallback)** — Instant, bulletproof fallback if MOSDAC access experiences downtime during live evaluation.

* **Dataset / API:** **NASA Ocean Color / OB.DAAC (MODIS-Aqua / VIIRS / PACE)**
  * **Provider:** NASA Ocean Biology Processing Group (OBPG)
  * **Target Agent:** `Ocean Analytics Agent`
  * **Parameters Provided:** High-resolution Chlorophyll-a concentration ($mg/m^3$), Photosynthetically Available Radiation (PAR), Diffuse Attenuation Coefficient ($K_d490$).
  * **Format / Protocol:** OPeNDAP, HTTPS REST via Earthdata Login
  * **Endpoint:** `https://oceancolor.gsfc.nasa.gov/` & `https://urs.earthdata.nasa.gov/`
  * **Relevance / Priority:** **P0 (Fallback)** — Reliable secondary chlorophyll provider.

#### 2.2 ⏱️ High-Precision Commercial Tidal & Marine Telemetry (Fallback)
* **Dataset / API:** **Stormglass.io Marine API (Free Tier)**
  * **Provider:** Stormglass AB
  * **Target Agent:** `Ocean Analytics Agent`, `Weather Intelligence Agent`
  * **Parameters Provided:** Astronomical tide extremes (high/low water levels and times), wave swell components, water temperature.
  * **Format / Protocol:** REST JSON (Rate limit: 10 requests/day free)
  * **Endpoint:** `https://api.stormglass.io/v2/tide/extremes/point?lat={lat}&lng={lon}`
  * **Relevance / Priority:** **P0 (Fallback)** — Clean programmatic fallback for instant tide predictions when offline tables need real-time validation.

#### 2.3 🚢 Global Vessel Activity & AIS Analytics (Stretch)
* **Dataset / API:** **Global Fishing Watch (GFW) API**
  * **Provider:** Global Fishing Watch (Oceana / SkyTruth / Google)
  * **Target Agent:** `Geospatial Reasoning Agent` (Vessel Traffic)
  * **Parameters Provided:** Aggregated fishing effort density (vessel hours per $km^2$), AIS vessel presence tracks.
  * **Format / Protocol:** REST API (Bearer Token, free self-serve rate limit)
  * **Endpoint:** `https://globalfishingwatch.org/our-apis/`
  * **Relevance / Priority:** **P3 (Deferred / Stretch)** — Useful only if commercial fleet monitoring is demonstrated; not required for core 8 queries.

---

### 🟠 TIER 3: Gated Government Registration & Request Access (Approval Lag)

Official Indian Government portals that require formal registration, email verification, administrative approval, or direct institutional data-feed requests.

#### 3.1 🛰️ Near-Real-Time ISRO Satellite Telemetry
* **Dataset / API:** **MOSDAC Registered User Portal (NRT / SFTP / API)**
  * **Provider:** Space Applications Centre (SAC / ISRO)
  * **Target Agent:** `Marine Data Discovery Agent`, `Weather Intelligence Agent`
  * **Parameters Provided:** Near-Real-Time (NRT) Level-2/3 products: INSAT-3DR/3DS atmospheric & ocean imagery, Oceansat-3 OCM (Ocean Color Monitor), Scatterometer winds, cyclone track forecasts.
  * **Format / Protocol:** FTP / SFTP, HTTPS Satellite Data Download API
  * **Access Workflow:** SignUp on `mosdac.gov.in` → Email verification → Wait for SAC admin approval → Place "Standing Order" for NRT sector data.
  * **Relevance / Priority:** **P0 (Action Now)** — Initiate on Day 1 due to approval lag.

#### 3.2 🗺️ NRSC Spatial Layers & Ocean Thematics
* **Dataset / API:** **Bhuvan / VEDAS Geoportal (NRSC / ISRO)**
  * **Provider:** National Remote Sensing Centre (NRSC / ISRO)
  * **Target Agent:** `Visualization Agent`, `Marine Data Discovery Agent`
  * **Parameters Provided:** Web Map Service (WMS) thematic layers: INCOIS PFZ overlays, coastal geomorphology, coral reef maps, land use/land cover.
  * **Format / Protocol:** OGC WMS/WFS, GeoTIFF, KML
  * **Access Workflow:** Separate user registration on `bhuvan.nrsc.gov.in` / `vedas.sac.gov.in`.
  * **Relevance / Priority:** **P0 (Action Now)**.

#### 3.3 🐟 Formal Institutional Fisheries & Ocean Feeds
* **Dataset / API:** **INCOIS Structured Bulk PFZ & OSF Feeds (ESSO-INCOIS)**
  * **Provider:** ESSO-INCOIS (Hyderabad)
  * **Target Agent:** `Marine Data Discovery Agent`
  * **Parameters Provided:** Structured JSON/CSV streaming feed of sector PFZs and Ocean State Forecast numerical model outputs.
  * **Access Workflow:** Direct email to ESSO-INCOIS requesting academic/hackathon data access for SIH 2026 (PS SIH26176).
  * **Relevance / Priority:** **P2 (Best Effort)** — Parallel track; proceed with ERDDAP / scraping fallback while awaiting reply.

* **Dataset / API:** **ICAR-CMFRI Marine Fisheries Research Datasets**
  * **Provider:** Central Marine Fisheries Research Institute (ICAR-CMFRI)
  * **Target Agent:** `Ocean Analytics Agent` (Diagnostic)
  * **Parameters Provided:** Long-term localized fish landing archives, species stock assessments, validated PFZ catch-enhancement ratios for South Tamil Nadu.
  * **Access Workflow:** Formal institutional request / research publication extraction.
  * **Relevance / Priority:** **P2 (Best Effort)**.

---

### 🟣 TIER 4: Architectural Reference & Emergency Integration Points

Operational national systems that serve as **architectural models** or **downstream integration handoffs** rather than direct pullable datasets.

#### 4.1 📢 Multi-Channel Alert Push Reference Architecture
* **System / Model:** **INCOIS Sagar Vani**
  * **Operating Agency:** ESSO-INCOIS
  * **Role in ORCA:** Architectural reference for multi-channel, regional-language dissemination (SMS, IVR voice calls, community radio, mobile push).
  * **Design Implication:** ORCA’s alert generation module is designed to format output payloads into Sagar Vani-compatible SMS/IVR templates.

#### 4.2 🆘 Maritime Distress & Search-and-Rescue Handoff
* **System / Model:** **ISRO DAT-SG / Sagarmitra Distress Program**
  * **Operating Agency:** ISRO & Indian Coast Guard (MRCC)
  * **Role in ORCA:** Emergency escalation target. When a user in the conversational interface indicates an active at-sea distress emergency (capsizing, vessel breakdown, medical crisis), ORCA displays the official Sagarmitra distress beacon protocol and Maritime Rescue Coordination Centre contact vectors.

---

## 3. Functional Matrix: Mapping 9 Agents to Datasets & Access Tiers

| # | Agent Role | Primary Functional Domain | Primary Datasets & Sources | Access Tier Breakdown |
|---|---|---|---|---|
| 1 | **Planning Agent** | Orchestration & Intent Routing | Internal intent taxonomy & domain rulebooks | System Internal |
| 2 | **Marine Data Discovery Agent** | Catalog Routing & Retrieval | INCOIS ERDDAP, MOSDAC Open Data, Bhuvan, Copernicus | 🟢 Tier 1 / 🔵 Tier 2 / 🟠 Tier 3 |
| 3 | **Weather Intelligence Agent** | Meteorology, Waves & Extreme Weather | Open-Meteo Marine API, IMD CAP & Bulletins, IMD Damini Lightning, MOSDAC INSAT-3DR | 🟢 Tier 1 / 🟠 Tier 3 |
| 4 | **Ocean Analytics Agent** | SST, Chlorophyll, Tides & PFZ Analytics | INCOIS ERDDAP, Survey of India Tide Tables, NASA Ocean Color, data.gov.in Catch Data | 🟢 Tier 1 / 🔵 Tier 2 |
| 5 | **Geospatial Reasoning Agent** | Boundaries, Geofences & Routing | Marine Regions EEZ/IMBL, WDPA MPAs, GEBCO Bathymetry Grid | 🟢 Tier 1 |
| 6 | **Risk Assessment Agent** | Deterministic Safety & Hazard Gating | INCOIS Hazard Advisories, IMD Cyclone Feeds, Open-Meteo Wave Thresholds, EEZ Polygons | 🟢 Tier 1 |
| 7 | **Visualization Agent** | Map Overlays & Chart Geometry | Bhuvan WMS, GeoJSON layer generators, Leaflet / Mapbox GL pipelines | 🟢 Tier 1 / 🟠 Tier 3 |
| 8 | **Reporting Agent** | Evidence Synthesis & Structured Citations | Dataset provenance metadata, timestamp generators, 3-tier confidence engine | System Internal |
| 9 | **User Interaction Agent** | Multilingual NLU/NLG & Audio Channels | IndicTrans2, Bhashini API, Sagar Vani formatters | 🟢 Tier 1 / 🟣 Tier 4 |

---

## 4. Phase 0 Execution & Procurement Checklist

```
══════════════════════════════════════════════════════════════════════════════
PHASE 0 IMMEDIATE ACTION ITEMS (PRE-HACKATHON WEEK)
══════════════════════════════════════════════════════════════════════════════
[ ] 1. TIER 1 DIRECT DOWNLOADS (Do Today — 0 Minutes Wait Time):
    ├── Download Marine Regions EEZ + India-Sri Lanka IMBL GeoJSON (marineregions.org)
    ├── Download WDPA Gulf of Mannar Marine National Park shapefile (protectedplanet.net)
    ├── Download GEBCO 15 arc-second bathymetry grid for 7.5°N–10.5°N, 77.0°E–80.5°E (gebco.net)
    └── Download Survey of India 2026 tidal prediction tables for Tuticorin / Pamban / Chennai

[ ] 2. TIER 1 & TIER 2 API INTEGRATION TESTS:
    ├── Test Open-Meteo Marine API curl request for Thoothukudi coordinates (8.80°N, 78.14°E)
    ├── Test INCOIS ERDDAP server query (erddap.incois.gov.in/erddap/) for active datasets
    ├── Register Copernicus Marine (marine.copernicus.eu) — instant account confirmation
    └── Register NASA Earthdata (urs.earthdata.nasa.gov) — instant account confirmation

[ ] 3. TIER 3 GOVERNMENT ACCESS REGISTRATIONS (Longest Lead Time):
    ├── Submit MOSDAC SignUp registration form (mosdac.gov.in)
    ├── Submit Bhuvan / VEDAS user registration (bhuvan.nrsc.gov.in)
    └── Send formal data request email to ESSO-INCOIS Hyderabad for SIH26176 PFZ bulk feeds
```


