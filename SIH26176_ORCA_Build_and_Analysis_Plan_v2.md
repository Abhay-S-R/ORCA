# 🌊 SIH26176 — ORCA: Marine EcOsystem Reasoning with Collaborative Agents
### Consolidated Build & Analysis Plan v2 — Team of 6

> **Sponsor:** ISRO (Department of Space) | **Track:** Software | **Theme:** Miscellaneous (Disaster Management & Marine Safety Focus)
> **Deadline:** 20 September 2026 | **Official portal:** sih.gov.in/sih2026PS | **Live PS page:** sih2026.vuce.in/ps/SIH26176

This replaces the earlier draft, which was built on inferred/reconstructed PS text. The full **official Background / Description / Expected Solution** has now been retrieved from the live SIH portal (verbatim, verified 27 Aug 2026) and is used as ground truth below.

---

## 0. What the PS *actually* says (verbatim-sourced, not inferred)

**Background:** Marine ecosystems support livelihoods, food security, biodiversity, maritime transport, coastal resilience, and the blue economy. ISRO and global agencies generate huge daily volumes of EO/oceanographic data (SST, chlorophyll, weather). Stakeholders (fishermen, researchers, coastal authorities, disaster agencies, maritime operators) need timely access — hence the ask for an **intelligent conversational platform**, not a dashboard.

**Description:** Build an **Agentic AI-powered conversational platform** that:
- Interprets user intent, decomposes requests into executable tasks
- Coordinates **multiple specialized AI agents**
- Retrieves marine/geospatial datasets, does **spatial-temporal reasoning**
- Synthesizes actionable recommendations conversationally
- Integrates satellite EO products, GIS layers, weather services, oceanographic observations, and public-domain marine advisories

**Typical queries (official list — use these verbatim as your demo script backbone):**
1. Where is the nearest Potential Fishing Zone (PFZ) today?
2. Is it safe to venture into the sea tomorrow morning?
3. What are tide, weather, and sea conditions near my fishing location?
4. Any lightning or cyclone alerts in my area?
5. Which regions show high chlorophyll + favourable SST?
6. Safest route for a fishing vessel given weather/sea-state?
7. Why has fish productivity declined in a region? *(root-cause/explanatory — hardest one)*
8. Which zones to avoid due to hazards or geofencing?

**Expected Solution — capabilities explicitly named by ISRO:**
- NL understanding + **automatic language ID and same-language response**, emphasis on **Indian regional languages**
- **Multi-turn, contextual conversation** (query refinement, follow-ups)
- Autonomous discovery/retrieval/integration of heterogeneous datasets
- Spatial + temporal + contextual reasoning across sources
- **Explainable, evidence-based** recommendations with maps/charts/visualizations
- Proactive hazard alerts (weather, waves, lightning, cyclones)
- **Geofencing notifications** (international maritime boundaries, restricted waters, MPAs, ecologically sensitive zones)
- Route optimization / safe navigation / operational planning
- Every recommendation delivered **with its supporting evidence and reasoning**

**Agents ISRO explicitly suggests (this is the rubric — name your agents close to this):**
> Planning · Marine Data Discovery · Weather Intelligence · Ocean Analytics · Geospatial Reasoning · Risk Assessment · Visualization · Reporting · User Interaction

This is **9 named roles**, more granular than either of your earlier drafts' 5–7 agents. You don't need 9 literal LangGraph nodes, but your architecture doc should map cleanly onto these 9 so a judge who has read the PS sees their own rubric reflected back.

---

## 1. Revised Agent Architecture (mapped to ISRO's 9 roles)

```
User Query (any Indian language, voice/text, multi-turn)
        │
        ▼
┌───────────────────────────────┐
│ User Interaction Agent (Ingress)│ → language ID, translates query to English, loads session memory
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│ Planning Agent (Orchestrator) │ → intent classification → sub-task decomposition, routing plan
└───────────────────────────────┘
        │
   ┌────┼─────────────┬────────────────┬─────────────────┐
   ▼    ▼              ▼                ▼                 ▼
┌────────────┐ ┌───────────────┐ ┌───────────────┐ ┌──────────────────┐
│Marine Data  │ │Weather        │ │Ocean Analytics │ │Geospatial         │
│Discovery    │ │Intelligence   │ │Agent            │ │Reasoning Agent     │
│Agent        │ │Agent           │ │(SST/chl/PFZ    │ │(boundary & MPA    │
│(queries     │ │(wind, waves,   │ │correlation,    │ │geometry, GEBCO    │
│ERDDAP,      │ │currents,       │ │tide/temp trends│ │depths, route      │
│MOSDAC, OSF, │ │lightning,      │ │& anomalies)    │ │optimization)      │
│Open-Meteo)  │ │cyclone tracks) │               │ │                  │
└────────────┘ └───────────────┘ └───────────────┘ └──────────────────┘
        │              │                │                    │
        └──────────────┴────────┬───────┴────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │ Risk Assessment Agent   │ → DETERMINISTIC rule-based hazard gating,
                    │ (Deterministic Safeguard│   geofence violation checks, 3-tier confidence
                    └─────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │ Visualization Agent     │ → generates GeoJSON layers, heatmap coordinates,
                    │                         │   and route vectors for Leaflet/Mapbox GL
                    └─────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │ Reporting Agent         │ → evidence-cited synthesized answer,
                    │ (Synthesis / Critic)    │   attaches dataset, timestamp & confidence to claims
                    └─────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │ User Interaction (Egress)│ → back-translation into user's language,
                    │                         │   delivers conversational text + map payload
                    └─────────────────────────┘
                                 ▼
                         User (Chat + Interactive Map)
```

**Non-negotiable for credibility (unchanged from before, now stronger given official emphasis on "evidence and reasoning used to derive each response"):** log every inter-agent hand-off as structured JSON and make the trace visibly inspectable — the PS explicitly demands explainability, so this isn't just a demo trick, it's literally graded criteria.

### JSON hand-off contract (design this in Phase 1, before writing agent code)
Every agent should emit:
```json
{
  "agent": "weather_intelligence",
  "query_id": "uuid",
  "inputs_consumed": {"region": "...", "date_range": "..."},
  "outputs": {"wind_speed_kmh": 0, "wave_height_m": 0, "alerts": []},
  "source_dataset": "MOSDAC INSAT-3DR / IMD",
  "timestamp": "ISO8601",
  "confidence": "high | medium | low-data"
}
```
This single schema, reused across all 9 agent roles, is what makes the orchestration trace demo-able live.

---

## 2. Tech Stack (Refined & Complete)

| Layer | Choice | Notes |
|---|---|---|
| Agent orchestration | **LangGraph** (preferred) | Explicit state graph proves genuine hand-offs; CrewAI as backup |
| LLM | Model-agnostic API layer | Keep swappable (Gemini / Claude / GPT / Ollama) — prevents single-point failure |
| Vector DB / RAG | Chroma or FAISS | For marine advisories, historical event reports, regional guides |
| Data pipeline | Python — pandas, xarray, netCDF4, erddapy | Ingestion for NetCDF, OPeNDAP, GeoTIFF, and REST data |
| Backend | FastAPI | Agent serving, REST endpoints, and async pipeline orchestration |
| Frontend | Next.js (or React + Vite) | Responsive chat UI + map overlay + live trace inspector |
| Map/geospatial | Leaflet or Mapbox GL + GeoPandas/Shapely | SST/chlorophyll heatmaps, PFZ pins, Marine Regions EEZ/IMBL, WDPA MPA polygons, GEBCO depth contours |
| Marine Weather APIs | **Open-Meteo Marine API** + INCOIS ERDDAP | Zero-friction, free global wave/current data; Stormglass as tidal fallback |
| Multilingual | IndicTrans2 / Bhashini API / LLM translation | Seamless English translation bridge for 9+ Indian coastal languages |
| Alerts & Caching | In-memory / Redis cache + IMD CAP / Damini feed | 5–15 min TTL to prevent upstream rate-limiting |

---

## 3. Data Sources — What's Really Available, and the Access Friction (verified)

| Source | What it gives you | Access reality (verified) | Action required |
|---|---|---|---|
| **MOSDAC** (ISRO/SAC) | SST, ocean color, INSAT-3D/3DR/3DS weather, ocean currents, salinity, wave products | Two tiers: (1) **Open Data** — free, no login; (2) **NRT/API data** — requires SignUp, email verification, and admin approval. Near-real-time needs a "standing order". | 🔴 **Register on mosdac.gov.in NOW**. Separately request API/SFTP credentials. |
| **INCOIS ERDDAP & LAS** (`erddap.incois.gov.in`) | RESTful, OPeNDAP, JSON, CSV, NetCDF access to oceanographic & buoy observations | Publicly accessible server, standardized endpoints, much cleaner than scraping HTML. | 🔴 **P0: Query INCOIS ERDDAP immediately** — integrate directly for structured ocean data. |
| **Open-Meteo Marine API** | Wave height, swell direction/period, wind waves, ocean currents | **100% free, zero API key required**, instant HTTP GET queries by lat/long. | 🔴 **P0: Use immediately** for instant, reliable marine weather nowcasts and forecasts. |
| **INCOIS PFZ Advisory** | PFZ points (~1,223 coastal nodes) | Public WebGIS/text page (JSP-based). Structured pull requires scraping text pages or official bulk request. | 🟡 Email INCOIS for bulk feed; keep scraping/cached fallback ready in parallel. |
| **Tide Predictions** (Survey of India / INCOIS) | High/low tide times and heights along Indian coast (Query #3) | Survey of India monthly tables (downloadable); INCOIS tide gauge portal; Stormglass.io (10 req/day free tier) as API fallback. | 🔴 **P0: Download Survey of India tables** & setup Stormglass fallback. |
| **GEBCO Global Bathymetry** | 15 arc-second gridded ocean depth data | Free public download from `gebco.net` (NetCDF/GeoTIFF) — prerequisite for depth-safe vessel routing. | 🟡 **Download GEBCO grid** for South Tamil Nadu / pilot sector. |
| **Bhuvan / VEDAS** | Thematic ocean layers & PFZ visualization | Public, registration required for WMS/API layers. | 🔴 **Register on bhuvan.nrsc.gov.in / VEDAS**. |
| **IMD (CAP, Bulletins, Damini)** | Cyclone bulletins, CAP warnings, lightning alerts | Public bulletins + CAP feed + Damini lightning nowcasts. | 🟠 Target the CAP feed and Damini endpoints directly. |
| **Marine Regions (VLIZ) & WDPA** | Official EEZ boundaries, Palk Strait IMBL coordinates, Gulf of Mannar MPA polygon | Free public download, no registration required. | 🔴 **Download shapefiles NOW** from marineregions.org and protectedplanet.net. |
| **Copernicus Marine (CMEMS)** | Global ocean reanalysis (SST, currents, waves) | Free, mature REST API, instant registration. | 🟡 Register early as an instant fallback safety net. |
| **NASA Ocean Color / MODIS** | Chlorophyll-a, SST | Free Earthdata login, instant access. | 🟡 Fallback for chlorophyll if MOSDAC is delayed. |

### 📩 The formal requests you should actually send (do this literally, in the first 48 hours)
1. **MOSDAC SignUp** (mosdac.gov.in) — registration form + wait for email approval. If no response in a few days, there's typically a listed contact/helpdesk on the portal — follow up directly rather than re-submitting.
2. **MOSDAC standing order** — once your account is approved, place a standing order for near-real-time SST/ocean-color/wind products for your chosen coastal region (renew before the 1-month cap expires if your build phase runs long).
3. **MOSDAC API/SFTP access request** — if you intend to pull data programmatically rather than manually downloading, explicitly request API or SFTP credentials; don't assume SignUp alone grants this.
4. **Bhuvan/VEDAS registration** (bhuvan.nrsc.gov.in) — separate sign-up from MOSDAC even though both are ISRO/NRSC-adjacent.
5. **INCOIS — a direct email/contact-form request** to ESSO-INCOIS asking for (a) a structured/bulk PFZ data feed or API for your target sector, and (b) any documented Ocean State Forecast API, since the public pages are map/text only. Mentioning "SIH 2026, PS SIH26176, ISRO-sponsored" in the request is legitimate context and may speed a response.
6. **Copernicus Marine + NASA Ocean Color** registrations — low friction, do these in parallel as your safety net, not sequentially after the Indian sources.

**Backup plan (keep from v1, it's still correct):** pre-download a fixed snapshot of SST/chlorophyll/wind/PFZ data for **one coastal region** before the event so live API flakiness doesn't sink the demo. Clearly label cached/synthetic data in the UI — the PS's own emphasis on "evidence-based" and "confidence" makes mislabeling data provenance a real credibility risk, not just a nice-to-have.

---

## 4. Pain Points — Ranked by How Likely They Are to Sink the Demo

| # | Pain point | Why it's dangerous | Mitigation |
|---|---|---|---|
| 1 | **"Multi-agent" is trivially fake-able** with one prompt wearing labels | This is the single most likely judge attack, and the official PS explicitly asks for "collaboration among specialized agents" | Structured JSON hand-off contract (Section 1) + visible trace log; rehearse showing Agent A's raw output being consumed by Agent B, live |
| 2 | **LLM Hallucination in safety-critical alerts** | In a disaster/safety context, an LLM generating "it is safe" during an active storm is catastrophic | **Deterministic rule-based gating in Risk Assessment Agent** — safety thresholds are computed in code, not generated by LLM text |
| 3 | **MOSDAC/Bhuvan/INCOIS access latency** | Registration approval takes days; near-real-time needs standing orders | Use Open-Meteo Marine API + Copernicus immediately; keep cached regional snapshot ready |
| 4 | **INCOIS PFZ data isn't a clean REST API** | WebGIS scraping is fragile during live demos | Investigate INCOIS ERDDAP (`erddap.incois.gov.in`); pre-download sector PFZ CSVs as offline fallback |
| 5 | **Geofencing correctness** (MPAs, EEZ/IMBL lines) | Boundary errors are legal/safety incidents | Use authoritative Marine Regions VLIZ shapefiles & WDPA polygons; never let LLM hallucinate coordinates |
| 6 | **Missing Tidal Data (Query #3 requirement)** | Judges testing "tides, weather, sea state" will catch missing tide predictions | Integrate Survey of India tables + Stormglass.io API fallback into Ocean Analytics Agent |
| 7 | **Multilingual is core per Expected Solution** | PS explicitly emphasizes Indian regional languages | Build language-ID and translation pipeline into Phase 1 architecture rather than bolting on at the end |
| 8 | **The "why did catch decline" root-cause query** | Hardest of the 8 queries — requires multi-year historical correlation | Pre-index data.gov.in fisheries statistics + CMFRI published trends for the pilot sector (Thoothukudi) |
| 9 | **Upstream API rate-limiting / mid-demo downtime** | External servers failing or blocking queries during evaluation | In-memory caching (5–15 min TTL) for live feeds; swappable LLM provider layer |
| 10 | **Scope creep across 9 named agent roles** | Trying to over-build all 9 agents as heavy LLM pipelines | Build all 9 as modular nodes in LangGraph, but keep helper agents (Reporting, Visualization) deterministic and lightweight |

---

## 5. Scope Strategy — MVP Definition

**Lock these before writing code:**
1. **One coastal region** (pick one, commit — e.g., Kerala or Tamil Nadu coast, both have strong INCOIS PFZ sector coverage)
2. **Primary query type, end-to-end:** "Is it safe to fish here today/tomorrow?" — naturally exercises Weather Intelligence + Ocean Analytics + Risk Assessment + Geospatial Reasoning
3. **Secondary query types to also demo live:** nearest PFZ, tide/weather/sea conditions, cyclone/lightning alerts (these 4 together cover 5 of the 8 official example queries)
4. **All 9 named agent roles present and real**, even if some are thin — mirror ISRO's own rubric structure
5. **2–3 Indian languages**, text-based, built into the architecture from day one (not deferred)
6. **Map overlay**: PFZ zones, hazard alerts, geofence boundaries, user's queried location
7. **Explicit confidence/uncertainty tiers** on every answer
8. **Visible orchestration trace** viewable on demand — this is your single most important UI element for judging, arguably more important than polish elsewhere

**Explicitly deferred to stretch:** national coverage, voice interface, full root-cause catch-decline reasoning, vessel-tracking/Global Fishing Watch integration, more than one region.

---

## 6. Build Roadmap

| Phase | Focus | Key deliverable |
|---|---|---|
| **Phase 0 (pre-hackathon, do this week)** | Register MOSDAC + Bhuvan/VEDAS; download Marine Regions EEZ/IMBL + WDPA MPA + GEBCO bathymetry; test Open-Meteo & INCOIS ERDDAP; download Survey of India tide tables | All foundational shapefiles stored locally; open APIs tested |
| **Phase 1** | Design 9-agent LangGraph state graph; lock JSON hand-off schema; scaffold multilingual ingress/egress pipeline skeleton | Architecture doc + schema + executable LangGraph skeleton |
| **Phase 2** | Data access layer per specialist agent (Open-Meteo, ERDDAP, PFZ parser, tide calculator, GEBCO depth lookup) with local fallback cache | Each specialist agent returns structured JSON with timestamps & confidence |
| **Phase 3** | Implement deterministic Risk Assessment gating + Geospatial routing + Reporting evidence citation; wire orchestrator | End-to-end multi-agent execution pipeline working in CLI |
| **Phase 4** | Frontend UI: Next.js chat interface + interactive Leaflet/Mapbox GL map + live agent trace inspector panel | Working interactive Web UI |
| **Phase 5** | Multilingual model integration (IndicTrans2 / Bhashini / Gemini Multilingual) for Hindi, Tamil, Telugu, Malayalam, Bengali | Voice/text input-output functioning across coastal languages |
| **Phase 6** | Validation & Stress-Testing: verify factual correctness of output against live INCOIS/IMD pages; test Cyclone Gaja replay scenario; test offline cache fallback | Verified factual accuracy + graceful degradation under errors |
| **Phase 7** | Demo rehearsal using the **8 official PS example queries** as the exact script; judge Q&A drill on agent authenticity and safety gating | Rehearsed live orchestration demo |

---

## 7. Team Role Split — Team of 6

| Role | Count | Focus | Primary agents owned |
|---|---|---|---|
| AI/ML + orchestration lead | 1 | LangGraph state graph, Planning + Risk Assessment + Reporting agents, JSON schema design | Planning, Risk Assessment, Reporting |
| AI/ML + RAG/reasoning engineer | 1 | Ocean Analytics + Geospatial Reasoning agents, RAG over advisories/marine docs | Ocean Analytics, Geospatial Reasoning |
| Backend/data engineer | 1 | MOSDAC/Bhuvan/INCOIS integration, NetCDF/HDF5 pipelines, Marine Data Discovery + Weather Intelligence agents | Marine Data Discovery, Weather Intelligence |
| Frontend/GIS engineer | 1 | Chat UI, map overlays (Leaflet/Mapbox), Visualization agent, orchestration-trace panel | Visualization, User Interaction (UI half) |
| Multilingual/NLP + domain researcher | 1 | IndicTrans2/Bhashini integration, language-ID agent logic, **and** validates every ocean-science claim/threshold for factual correctness | User Interaction (language half), domain QA across all agents |
| PM / presentation lead | 1 | Demo flow scripted around the 8 official example queries, judge Q&A rehearsal (Section 8), tracks the Section 3 registration checklist so nothing falls through | Owns Phase 0 action items end-to-end |

---

## 8. Judge Stress-Test Prep — Updated for the Official Text

Be ready to, **live, on request:**
1. Show one agent's raw structured JSON being consumed by the next agent (the trace).
2. Swap a data source for one agent from cached → live and show the answer change.
3. Explain what happens when an agent gets malformed/missing input (show a real "low confidence / no data" response, not a crash).
4. Run one of ISRO's own 8 example queries live, in a **non-English Indian language**, and show correct language-ID + response-in-kind.
5. Change the target region and show it's a config change, not a rebuild.
6. Explain, for one specific answer, exactly which dataset + timestamp + agent backed each claim in it — this maps directly to the PS's "supporting evidence and reasoning" line.
7. Explain your geofencing boundary source (don't improvise maritime boundary claims live — this is a factual/sensitive-topic risk).

**Weakest point a sharp judge will target first (unchanged from v1, now confirmed by the official rubric language):** whether "collaborative agents" is architecturally real or a UI/naming illusion over a single model call. Give this the majority of rehearsal time.

---

## 9. Immediate Next Steps (send/do this week)

- [ ] Confirm team roles against Section 7
- [ ] **Send MOSDAC SignUp registration** (mosdac.gov.in) — track approval email
- [ ] **Send Bhuvan/VEDAS registration** (bhuvan.nrsc.gov.in)
- [ ] **Send a direct request to ESSO-INCOIS** for structured/bulk PFZ + Ocean State Forecast data access for your target coastal sector — reference "SIH 2026, ISRO PS SIH26176" in the request
- [ ] Register Copernicus Marine (CMEMS) and NASA Ocean Color as fallback — do this in parallel, not after
- [ ] Once MOSDAC is approved: **place a standing order** for near-real-time products in your region, and separately **request API/SFTP credentials** if programmatic access is needed
- [ ] Pick the one coastal region for MVP scope
- [ ] Draft the JSON hand-off schema (Section 1) covering all 9 agent roles
- [ ] Map each of the 8 official example queries to which agents fire, in writing, before coding starts
- [ ] Pick orchestration framework (LangGraph recommended)
- [ ] Start Phase 0 data snapshot download for the backup plan
