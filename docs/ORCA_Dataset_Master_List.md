# 🌊 ORCA (SIH26176) — Dataset Checklist & Master Data Source Catalog

**System Target:** Multi-Agent Marine Intelligence & Conversational Decision Support Platform  
**Sponsor & Theme:** ISRO (Department of Space) | Disaster Management & Marine Safety Focus  
**Last Verified:** August 2026  

---

## 1. 📋 Simple & Proper Dataset Checklist

Use this checklist to track dataset procurement, API integration, and fallback verification across development phases.

### 🟢 Tier 1: 100% Free & Open Access (Zero Friction / Instant Access)

| Status | Dataset / API Name | Domain & Parameters | Priority | Target Agent | Source URL / Endpoint |
| :---: | :--- | :--- | :---: | :--- | :--- |
| [x] | **Open-Meteo Marine API** | Wave height ($H_s$), wave period ($T_p$), swell, currents | `P0 Core` | `Weather Intelligence Agent` | [marine-api.open-meteo.com](https://marine-api.open-meteo.com/v1/marine) |
| [x] | **INCOIS ERDDAP Data Server** | In-situ buoy telemetry, SST, salinity, ocean models (Pinned Cert) | `P0 Core` | `Marine Data Discovery Agent` | [erddap.incois.gov.in](https://erddap.incois.gov.in/erddap/) |
| [x] | **MOSDAC Open Data Portal** | Oceansat-3, INSAT-3D/3DR SST, Chlorophyll, Winds (`2.6 GB`) | `P0 Core` | `Ocean Analytics Agent` | [mosdac.gov.in](https://mosdac.gov.in) |
| [x] | **Survey of India / Stormglass Tides** | High/low tide predictions & astronomical heights | `P0 Core` | `Ocean Analytics Agent` | [api.stormglass.io](https://api.stormglass.io/v2/tide/extremes/point) |
| [x] | **INCOIS Tide Gauge Network** | Real-time coastal tide gauge water level telemetry | `P1 Validation` | `Ocean Analytics Agent` | [tsunami.incois.gov.in](https://tsunami.incois.gov.in/TEWS/TGMap.jsp) |
| [x] | **Marine Regions (VLIZ)** | Full MultiPolygons: EEZ (200 NM), Territorial Waters, Palk Strait IMBL | `P0 Core` | `Geospatial Reasoning Agent` | [marineregions.org](https://www.marineregions.org/downloads.php) |
| [x] | **Protected Planet (WDPA)** | Marine Protected Areas (MPAs) boundary polygons | `P0 Core` | `Geospatial Reasoning Agent` | [protectedplanet.net](https://www.protectedplanet.net) |
| [x] | **GEBCO 15" Bathymetry Grid** | 15 arc-second high-resolution ocean depth ($450\text{m}$) | `P0 Core` | `Geospatial Reasoning Agent` | [download.gebco.net](https://download.gebco.net/) |
| [x] | **INCOIS PFZ Advisories** | Potential Fishing Zone text & web nodes (318 live nodes across 14 sectors) | `P0 Core` | `Marine Data Discovery Agent` | [incois.gov.in/PFZ](https://incois.gov.in/MarineFisheries/PfzWebGis) |
| [x] | **INCOIS Hazard Alerts** | Swell surge, Kallakkadal, high wave advisories | `P0 Core` | `Risk Assessment Agent` | [incois.gov.in/site/multihazard.jsp](https://incois.gov.in/site/multihazard.jsp) |
| [x] | **NDMA SACHET & IMD CAP Feed** | Live disaster alerts (CAP 1.2 XML/JSON) & IMD nowcasts | `P0 Core` | `Weather Intelligence Agent` | [sachet.ndma.gov.in](https://sachet.ndma.gov.in/) |
| [x] | **IMD Damini / Lightning Nowcast** | Real-time lightning strike probability & convective CAPE | `P0 Core` | `Weather Intelligence Agent` | [damini.tropmet.res.in](https://damini.tropmet.res.in/) |
| [x] | **data.gov.in Catch Stats** | Historical district marine fish landings & species trends | `P1 Diagnostic` | `Ocean Analytics Agent` | [data.gov.in](https://data.gov.in/) |

---

### 🔵 Tier 2: Free Self-Serve Registration (Instant Sign-Up / Tokens)

| Status | Dataset / API Name | Domain & Parameters | Priority | Target Agent | Source URL / Endpoint |
| :---: | :--- | :--- | :---: | :--- | :--- |
| [x] | **Copernicus Marine (CMEMS)** | Global SST reanalysis ($0.05^\circ$), currents, waves (SDK installed) | `P0 Fallback` | `Ocean Analytics Agent` | [marine.copernicus.eu](https://marine.copernicus.eu/) |
| [x] | **NASA Ocean Color / CMR** | Chlorophyll-a ($mg/m^3$), MODIS/VIIRS NRT granules | `P0 Fallback` | `Ocean Analytics Agent` | [cmr.earthdata.nasa.gov](https://cmr.earthdata.nasa.gov) |
| [x] | **Stormglass.io Marine API** | Astronomical tide extremes point API (Token in `.env`) | `P0 Core` | `Ocean Analytics Agent` | [api.stormglass.io](https://api.stormglass.io/v2/tide/extremes/point) |
| [x] | **Global Fishing Watch (GFW)** | AIS vessel presence & fishing effort density (Token in `.env`) | `P3 Stretch` | `Geospatial Reasoning Agent` | [globalfishingwatch.org](https://globalfishingwatch.org/our-apis/) |

---

### 🟠 Tier 3: Gated Government Portals (ISRO / MoES Datasets)

| Status | Dataset / API Name | Domain & Parameters | Priority | Target Agent | Source URL / Endpoint |
| :---: | :--- | :--- | :---: | :--- | :--- |
| [x] | **MOSDAC Registered Portal** | EOS-06 OCM-3 Chlorophyll, INSAT-3DR SST, ScatSat Winds (`2.6 GB` on disk) | `P0 Core` | `Marine Data Discovery Agent` | [mosdac.gov.in](https://mosdac.gov.in) |
| [x] | **Bhuvan / VEDAS (NRSC)** | WMS/WMTS ocean thematic maps & 15-day satellite manifest | `P0 Core` | `Visualization Agent` | [bhuvan.nrsc.gov.in](https://bhuvan.nrsc.gov.in/) |
| [x] | **INCOIS WW3 & HYCOM Models** | Full 3D numerical wave & ocean forecast models (`16.4 GB` on disk) | `P0 Core` | `Weather / Risk / Ocean Agents` | [incois.gov.in/thredds](https://incois.gov.in/thredds/) |
| [x] | **ICAR-CMFRI Research Data** | Long-term landing archives & stock assessment baseline | `P1 Diagnostic` | `Ocean Analytics Agent` | [cmfri.org.in](http://www.cmfri.org.in/) |

---

### 🟣 Tier 4: Architectural Integration & Emergency Systems

| Status | System Name | Role in ORCA | Target Agent | Source URL / Integration |
| :---: | :--- | :--- | :--- | :--- |
| [x] | **INCOIS Sagar Vani** | Multi-channel SMS/IVR regional language broadcast template | `User Interaction Agent` | [incois.gov.in/SagarVani](https://incois.gov.in/SagarVani) |
| [x] | **ISRO DAT-SG / Nabhmitra** | At-sea emergency distress beacon & Coast Guard MRCC handoff | `Distress Handoff Agent` | [isro.gov.in/DAT](https://www.isro.gov.in/DAT.html) |
| [x] | **IMD Marine API** | Official coastal bulletin developer platform | `Weather Intelligence Agent` | [api.imd.gov.in](https://api.imd.gov.in/) |
| [x] | **DoF VCSS (Vessel Comm)** | National Vessel Communication & Support System protocol | `Distress Handoff Agent` | Department of Fisheries |

---

## 2. 🗺️ Dataset Master List: Detailed Source & Retrieval Catalog

Below is the complete dataset master list detailing **where to take each dataset from**, the exact API endpoints/urls, protocols, target agents, parameters provided, and step-by-step retrieval instructions.

---

### 🟢 TIER 1: 100% Free & Open Access (Zero Friction / Public Endpoints)

#### 1.1 🌊 Marine Weather, Waves & Ocean Currents

* **Dataset / API:** **Open-Meteo Marine Weather API**
  * **Where to Take Data From:** `https://marine-api.open-meteo.com/v1/marine`
  * **Provider:** Open-Meteo / Global NWP Ensemble (NOAA GFS Wave, ECMWF WAM, DWD ICON Wave)
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Significant wave height ($H_s$), wave direction, wave period ($T_p$), swell wave height/period/direction, wind wave height, ocean current velocity ($m/s$) and current direction ($^\circ$).
  * **Data Format:** REST JSON over HTTP GET
  * **Example Retrieval Query:**
    ```bash
    curl -X GET "https://marine-api.open-meteo.com/v1/marine?latitude=8.80&longitude=78.14&hourly=wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction&timezone=Asia%2FKolkata"
    ```
  * **Relevance / Priority:** **P0 Core** — Primary live weather and sea-state engine. Zero friction, instant implementation.

#### 1.2 🛰️ Earth Observation & In-Situ Ocean Analytics

* **Dataset / API:** **INCOIS ERDDAP Data Server**
  * **Where to Take Data From:** `https://erddap.incois.gov.in/erddap/`
  * **Provider:** ESSO-INCOIS (Ministry of Earth Sciences, Govt of India)
  * **Target Agent:** `Marine Data Discovery Agent`, `Ocean Analytics Agent`
  * **Parameters Provided:** In-situ ocean buoy telemetry (SST, salinity, currents, wave spectrum), model forecast grids, satellite SST/chlorophyll products.
  * **Data Format:** REST, OPeNDAP, JSON, CSV, NetCDF, GeoTIFF
  * **Example Retrieval Query:**
    ```bash
    curl -X GET "https://erddap.incois.gov.in/erddap/tabledap/index.json"
    ```
  * **Relevance / Priority:** **P0 Core** — Machine-readable programmatic access to Indian ocean buoy telemetry without fragile web scraping.

* **Dataset / API:** **MOSDAC Open Data Portal**
  * **Where to Take Data From:** `https://mosdac.gov.in` (Open Data Catalog section)
  * **Provider:** Space Applications Centre (SAC / ISRO)
  * **Target Agent:** `Marine Data Discovery Agent`, `Ocean Analytics Agent`
  * **Parameters Provided:** Satellite Earth Observation products: SST (Oceansat-3, INSAT-3D/3DR/3DS), Chlorophyll-a, ocean color, Scatterometer ocean surface winds.
  * **Data Format:** NetCDF4, HDF5, GeoTIFF
  * **Relevance / Priority:** **P0 Core** — Authoritative ISRO satellite observations.

#### 1.3 ⏱️ Tides, Water Levels & Coastal Dynamics

* **Dataset / API:** **Survey of India (SOI) Annual Tidal Tables**
  * **Where to Take Data From:** `https://www.surveyofindia.gov.in/`
  * **Provider:** Survey of India (SOI), Department of Science & Technology
  * **Target Agent:** `Ocean Analytics Agent`, `Geospatial Reasoning Agent`
  * **Parameters Provided:** High tide and low tide prediction times, astronomical tide heights (in meters above chart datum) for Indian ports (Tuticorin, Pamban, Chennai, Kochi, Visakhapatnam, Mumbai).
  * **Data Format:** Downloadable PDF / CSV / Tabular Tables
  * **Relevance / Priority:** **P0 Core** — Directly resolves **PS Query #3** (*"What are tide, weather, and sea conditions...?"*).

* **Dataset / API:** **INCOIS Tide Gauge Network (TEWS)**
  * **Where to Take Data From:** `https://tsunami.incois.gov.in/TEWS/TGMap.jsp`
  * **Provider:** ESSO-INCOIS Tsunami Early Warning Centre
  * **Target Agent:** `Ocean Analytics Agent`
  * **Parameters Provided:** Real-time sea-level anomaly observations and tide gauge water levels.
  * **Data Format:** Public Web Portal / HTML / GeoJSON
  * **Relevance / Priority:** **P0 Core** — Real-time validation of tidal water levels.

#### 1.4 🗺️ Geospatial Boundaries, Bathymetry & Restricted Zones

* **Dataset / API:** **Marine Regions (VLIZ) Maritime Boundaries**
  * **Where to Take Data From:** `https://www.marineregions.org/downloads.php`
  * **Provider:** Flanders Marine Institute (VLIZ)
  * **Target Agent:** `Geospatial Reasoning Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Exclusive Economic Zones (EEZ 200 NM), Territorial Seas (12 NM), Contiguous Zones, and India–Sri Lanka Palk Strait IMBL polygon coordinates.
  * **Data Format:** GeoJSON, Shapefile
  * **Relevance / Priority:** **P0 Core** — Essential for hard geofencing constraints; prevents accidental boundary crossing into international waters.

* **Dataset / API:** **Protected Planet / World Database on Protected Areas (WDPA)**
  * **Where to Take Data From:** `https://www.protectedplanet.net/en/thematic-areas/marine-protected-areas`
  * **Provider:** UNEP-WCMC & IUCN
  * **Target Agent:** `Geospatial Reasoning Agent`, `Visualization Agent`
  * **Parameters Provided:** Polygons and metadata for Marine Protected Areas (MPAs) (e.g., Gulf of Mannar Marine National Park, Gahirmatha Sanctuary).
  * **Data Format:** GeoJSON, Shapefile
  * **Relevance / Priority:** **P0 Core** — Mandatory for MPA alert notifications and restricted area geofencing.

* **Dataset / API:** **GEBCO Global Bathymetry Grid**
  * **Where to Take Data From:** `https://download.gebco.net/`
  * **Provider:** General Bathymetric Chart of the Oceans (IHO / IOC UNESCO)
  * **Target Agent:** `Geospatial Reasoning Agent`
  * **Parameters Provided:** 15 arc-second gridded 3D ocean depth and bathymetric elevation terrain grid.
  * **Data Format:** NetCDF, GeoTIFF (Sub-settable by Bounding Box, e.g., 7.5°N–10.5°N, 77.0°E–80.5°E for South Tamil Nadu)
  * **Relevance / Priority:** **P1 Core** — Prerequisite for bathymetry-aware safe route optimization (avoids shallow shoals).

#### 1.5 🐟 Fisheries Intelligence & Potential Fishing Zones

* **Dataset / API:** **INCOIS PFZ Advisories**
  * **Where to Take Data From:** `https://incois.gov.in/MarineFisheries/PfzWebGis`
  * **Provider:** ESSO-INCOIS (Ministry of Earth Sciences)
  * **Target Agent:** `Marine Data Discovery Agent`, `Ocean Analytics Agent`
  * **Parameters Provided:** Coordinates of Potential Fishing Zones across 14 Indian coastal sectors (~1,223 coastal nodes), bearing and distance from fish landing centers, validity time windows.
  * **Data Format:** WebGIS / HTML text bulletin / Tabular parsing
  * **Relevance / Priority:** **P1 Core** — Answers **PS Query #1** (*"Where is the nearest Potential Fishing Zone today?"*).

#### 1.6 ⚠️ Marine Hazards, Cyclones & Severe Weather Warnings

* **Dataset / API:** **INCOIS Hazard Alerts & Ocean State Warnings**
  * **Where to Take Data From:** `https://incois.gov.in/portal/osf/osf.jsp`
  * **Provider:** ESSO-INCOIS
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Swell surge advisories, Kallakkadal warnings, high wave alerts, storm surge alerts, tsunami advisories.
  * **Data Format:** RSS/XML, Public Bulletins
  * **Relevance / Priority:** **P1 Core** — Safety gating inputs for deterministic risk assessment.

* **Dataset / API:** **IMD Cyclone Bulletins & CAP Feed**
  * **Where to Take Data From:** `https://mausam.imd.gov.in/` & `https://sachet.ndma.gov.in/` (NDMA CAP Alert Portal)
  * **Provider:** India Meteorological Department (IMD / MoES)
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Tropical cyclone genesis, track forecast coordinates, intensity categories, color-coded district coastal warnings.
  * **Data Format:** Common Alerting Protocol (CAP XML) & Web Bulletins
  * **Relevance / Priority:** **P1 Core** — Answers **PS Query #4** (*"Any lightning or cyclone alerts in my area?"*).

* **Dataset / API:** **IMD Damini / Lightning Nowcast Feed**
  * **Where to Take Data From:** `https://damini.tropmet.res.in/`
  * **Provider:** Indian Institute of Tropical Meteorology (IITM) / IMD
  * **Target Agent:** `Weather Intelligence Agent`, `Risk Assessment Agent`
  * **Parameters Provided:** Real-time lightning strike locations and 15–30 minute convective thunderstorm nowcasts.
  * **Data Format:** Mobile API / Web Feed
  * **Relevance / Priority:** **P1 Core** — Critical safety check for pre-departure fishing planning.

* **Dataset / API:** **data.gov.in Fisheries Catch Statistics**
  * **Where to Take Data From:** `https://data.gov.in/`
  * **Provider:** Department of Fisheries / Open Government Data (OGD) Platform India
  * **Target Agent:** `Ocean Analytics Agent`, `Reporting Agent`
  * **Parameters Provided:** Historical district-wise and state-wise marine fish landings, species composition, and annual catch trends.
  * **Data Format:** CSV, REST API
  * **Relevance / Priority:** **P1 Diagnostic** — Answers **PS Query #7** (*"Why has fish productivity declined in a particular coastal region?"*).

---

### 🔵 TIER 2: Free Self-Serve Registration (Instant Sign-Up / Free API Tokens)

#### 2.1 🛰️ Global Earth Observation Fallbacks

* **Dataset / API:** **Copernicus Marine Service (CMEMS)**
  * **Where to Take Data From:** `https://marine.copernicus.eu/`
  * **Provider:** European Union / Mercator Ocean International
  * **Target Agent:** `Ocean Analytics Agent`, `Marine Data Discovery Agent`
  * **Parameters Provided:** Global multi-satellite SST reanalysis ($0.05^\circ$), ocean currents, salinity, sea surface height anomalies, wave spectra.
  * **Data Format:** Python `copernicusmarine` CLI, REST API, OPeNDAP, NetCDF
  * **Access Workflow:** Free instant sign-up on `marine.copernicus.eu` → Obtain API credentials.
  * **Relevance / Priority:** **P0 Fallback** — Instant secondary fallback if MOSDAC access experiences latency during evaluation.

* **Dataset / API:** **NASA Ocean Color / Earthdata (MODIS-Aqua / VIIRS / PACE)**
  * **Where to Take Data From:** `https://oceancolor.gsfc.nasa.gov/` & `https://urs.earthdata.nasa.gov/`
  * **Provider:** NASA Ocean Biology Processing Group (OBPG)
  * **Target Agent:** `Ocean Analytics Agent`
  * **Parameters Provided:** High-resolution Chlorophyll-a ($mg/m^3$), Photosynthetically Available Radiation (PAR), Diffuse Attenuation Coefficient ($K_d490$).
  * **Data Format:** HTTPS REST, OPeNDAP via Earthdata Login
  * **Access Workflow:** Free instant sign-up on `urs.earthdata.nasa.gov`.
  * **Relevance / Priority:** **P0 Fallback** — Instant fallback for chlorophyll data.

#### 2.2 ⏱️ Tidal API Fallback

* **Dataset / API:** **Stormglass.io Marine API (Free Tier)**
  * **Where to Take Data From:** `https://api.stormglass.io/v2/tide/extremes/point?lat={lat}&lng={lon}`
  * **Provider:** Stormglass AB
  * **Target Agent:** `Ocean Analytics Agent`
  * **Parameters Provided:** Astronomical tide extremes (high/low water levels and exact times), swell parameters.
  * **Data Format:** REST JSON (Rate limit: 10 free requests/day)
  * **Access Workflow:** Instant sign-up on `stormglass.io` → API Key generated immediately.
  * **Relevance / Priority:** **P0 Fallback** — Programmatic API validation for tide extremes.

#### 2.3 🚢 Global Vessel Activity (Stretch Goal)

* **Dataset / API:** **Global Fishing Watch (GFW) API**
  * **Where to Take Data From:** `https://globalfishingwatch.org/our-apis/`
  * **Provider:** Global Fishing Watch (Oceana / SkyTruth / Google)
  * **Target Agent:** `Geospatial Reasoning Agent`
  * **Parameters Provided:** Aggregated fishing effort density (vessel hours per $km^2$), AIS vessel presence tracks.
  * **Data Format:** REST API (Bearer Token)
  * **Relevance / Priority:** **P3 Stretch** — Optional stretch goal for fleet tracking demo.

---

### 🟠 TIER 3: Gated Government Registration & Request Access (Approval Lag)

#### 3.1 🛰️ Near-Real-Time ISRO Satellite Feeds

* **Dataset / API:** **MOSDAC Registered NRT Data Portal**
  * **Where to Take Data From:** `https://mosdac.gov.in` (Registered User Portal)
  * **Provider:** Space Applications Centre (SAC / ISRO)
  * **Target Agent:** `Marine Data Discovery Agent`, `Weather Intelligence Agent`
  * **Parameters Provided:** Near-Real-Time Level-2/3 INSAT-3DR/3DS atmospheric & ocean products, Oceansat-3 OCM Chlorophyll, Scatterometer winds.
  * **Data Format:** SFTP / FTP / HTTPS Data Download API
  * **Access Step-by-Step Workflow:**
    1. Sign up on `mosdac.gov.in`.
    2. Complete email verification.
    3. Wait for SAC admin approval.
    4. Place a "Standing Order" for NRT sector data.
  * **Relevance / Priority:** **P0 Priority** — Submit registration immediately due to approval lead time.

#### 3.2 🗺️ NRSC Spatial Layers & Ocean Maps

* **Dataset / API:** **Bhuvan / VEDAS Geoportal (NRSC / ISRO)**
  * **Where to Take Data From:** `https://bhuvan.nrsc.gov.in/` & `https://vedas.sac.gov.in/`
  * **Provider:** National Remote Sensing Centre (NRSC / ISRO)
  * **Target Agent:** `Visualization Agent`, `Marine Data Discovery Agent`
  * **Parameters Provided:** Web Map Service (WMS) thematic layers: INCOIS PFZ overlays, coastal geomorphology, coral reef maps, land use/land cover.
  * **Data Format:** OGC WMS/WFS, KML, GeoTIFF
  * **Access Workflow:** User registration on `bhuvan.nrsc.gov.in`.
  * **Relevance / Priority:** **P0 Priority** — Necessary for native Bhuvan map layer visualization.

#### 3.3 🐟 Bulk Government Data Feeds

* **Dataset / API:** **INCOIS Structured Bulk PFZ & OSF Feeds**
  * **Where to Take Data From:** Direct formal request to ESSO-INCOIS (Hyderabad)
  * **Provider:** ESSO-INCOIS
  * **Target Agent:** `Marine Data Discovery Agent`
  * **Parameters Provided:** Structured JSON/CSV stream of sector PFZs and Ocean State Forecast numerical model outputs.
  * **Access Workflow:** Send official email request mentioning *SIH 2026 PS SIH26176*.
  * **Relevance / Priority:** **P2 Best Effort** — Parallel track while utilizing ERDDAP & pre-downloaded sector CSVs.

* **Dataset / API:** **ICAR-CMFRI Marine Fisheries Datasets**
  * **Where to Take Data From:** `http://www.cmfri.org.in/` & `https://eprints.cmfri.org.in/`
  * **Provider:** Central Marine Fisheries Research Institute (ICAR-CMFRI)
  * **Target Agent:** `Ocean Analytics Agent`
  * **Parameters Provided:** Long-term localized fish landing archives, species stock assessments, validated PFZ catch-enhancement ratios.
  * **Access Workflow:** Research publication extraction & institutional repository pull.
  * **Relevance / Priority:** **P2 Best Effort**.

---

### 🟣 TIER 4: Architectural Integration & Emergency Systems

#### 4.1 📢 Multi-Channel Broadcast Format Reference

* **System / Model:** **INCOIS Sagar Vani**
  * **Where to Take Architecture Reference From:** `https://incois.gov.in/SagarVani`
  * **Operating Agency:** ESSO-INCOIS
  * **Role in ORCA:** Architectural reference for multi-channel regional-language alert dissemination (SMS, IVR voice calls, community radio, mobile push).
  * **Target Agent:** `User Interaction Agent`

#### 4.2 🆘 Maritime Distress & Search-and-Rescue Handoff

* **System / Model:** **ISRO DAT-SG / Sagarmitra Distress Program**
  * **Where to Take Handoff Target From:** `https://www.isro.gov.in/DAT.html`
  * **Operating Agency:** ISRO & Indian Coast Guard (MRCC)
  * **Role in ORCA:** Emergency escalation handoff. When a user query indicates an active emergency (capsizing, engine breakdown, medical crisis), ORCA outputs official distress beacon guidance and MRCC emergency contacts.
  * **Target Agent:** `User Interaction Agent`, `Risk Assessment Agent`

---

## 3. 🎯 Agent-to-Dataset Mapping Matrix

| # | Specialized Agent Role | Primary Datasets & Sources Needed | Access Tiers Covered |
|---|---|---|---|
| 1 | **Planning Agent** | Internal intent taxonomy & domain routing rulebooks | System Internal |
| 2 | **Marine Data Discovery Agent** | INCOIS ERDDAP, MOSDAC Open Data, Bhuvan, Copernicus CMEMS | 🟢 Tier 1 / 🔵 Tier 2 / 🟠 Tier 3 |
| 3 | **Weather Intelligence Agent** | Open-Meteo Marine API, IMD CAP & Bulletins, IMD Damini, MOSDAC INSAT-3DR | 🟢 Tier 1 / 🟠 Tier 3 |
| 4 | **Ocean Analytics Agent** | INCOIS ERDDAP, Survey of India Tide Tables, NASA Ocean Color, data.gov.in Catch Data | 🟢 Tier 1 / 🔵 Tier 2 |
| 5 | **Geospatial Reasoning Agent** | Marine Regions EEZ/IMBL, WDPA MPAs, GEBCO Bathymetry Grid | 🟢 Tier 1 |
| 6 | **Risk Assessment Agent** | INCOIS Hazard Advisories, IMD Cyclone Feeds, Open-Meteo Wave Thresholds, EEZ Polygons | 🟢 Tier 1 |
| 7 | **Visualization Agent** | Bhuvan WMS, Leaflet / Mapbox GL GeoJSON generators | 🟢 Tier 1 / 🟠 Tier 3 |
| 8 | **Reporting Agent** | Dataset provenance metadata, timestamp generators, 3-tier confidence engine | System Internal |
| 9 | **User Interaction Agent** | IndicTrans2, Bhashini API, Sagar Vani templates, ISRO DAT-SG contacts | 🟢 Tier 1 / 🟣 Tier 4 |

---

## 4. ⚡ Phase 0 Data Procurement Execution Plan

```
==============================================================================
PHASE 0 IMMEDIATE DATA PROCUREMENT STEPS
==============================================================================
[ ] 1. TIER 1 DIRECT DOWNLOADS (Do First — Instant):
    ├── Download Marine Regions EEZ + India-Sri Lanka IMBL GeoJSON (marineregions.org)
    ├── Download WDPA Gulf of Mannar Marine National Park shapefile (protectedplanet.net)
    ├── Download GEBCO 15 arc-sec bathymetry grid for pilot sector (gebco.net)
    └── Download Survey of India 2026 tidal prediction tables for Tuticorin / Pamban / Chennai

[ ] 2. TIER 1 & TIER 2 API INTEGRATION TESTS:
    ├── Test Open-Meteo Marine API request for Thoothukudi coords (8.80°N, 78.14°E)
    ├── Test INCOIS ERDDAP server query (erddap.incois.gov.in/erddap/) for active datasets
    ├── Register Copernicus Marine (marine.copernicus.eu) — instant confirmation
    └── Register NASA Earthdata (urs.earthdata.nasa.gov) — instant confirmation

[ ] 3. TIER 3 GOVERNMENT ACCESS REGISTRATIONS (Initiate Now):
    ├── Submit MOSDAC SignUp registration form (mosdac.gov.in)
    ├── Submit Bhuvan / VEDAS user registration (bhuvan.nrsc.gov.in)
    └── Send formal data request email to ESSO-INCOIS Hyderabad for SIH26176 PFZ bulk feeds
```
