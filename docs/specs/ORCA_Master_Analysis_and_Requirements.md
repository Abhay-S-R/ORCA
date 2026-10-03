# ORCA — Marine EcOsystem Reasoning with Collaborative Agents
## Master Analysis & Requirements Document (PS ID: 26176)

**Organization:** Indian Space Research Organisation (ISRO), Department of Space
**Category:** Software | **Theme:** Miscellaneous (Heavy Disaster Management & Marine Safety Focus)
**Source:** Merges and reconciles prior working documents into one master reference, verified against the live SIH portal as of August 2026.

---

## 1. What This Problem Statement Is Really Asking For

Strip away the Agentic-AI framing and the core ask is: **build a conversational, multi-agent decision-support system that sits on top of India's fragmented marine data ecosystem** (satellite EO data, oceanographic observations, weather forecasts, GIS layers, public advisories) and turns a question like *"Is it safe to go to sea tomorrow?"* into a synthesized, explainable, multi-source answer — in the user's own language, with maps and evidence attached.

Four things separate this from a generic RAG chatbot, and each is a real evaluation axis a judge will probe:

1. **Multi-agent orchestration is explicit, not optional.** The PS names roles it wants to see: planning, marine data discovery, weather intelligence, ocean analytics, geospatial reasoning, risk assessment, visualization, reporting, user interaction. Judges will check whether agents are genuinely decomposed and collaborating, or whether it's one LLM call pretending to be five agents.
2. **Spatial-temporal correlation across heterogeneous sources**, not single-dataset lookups. "Why has fish productivity declined in region X" requires joining SST + chlorophyll + advisory history over time — a reasoning task, not a fetch.
3. **Explainability is a first-class deliverable**, not a nice-to-have. Every answer needs its evidence and reasoning trail attached — which datasets, which time window, which thresholds triggered the recommendation.
4. **Safety & Hazard Alerting is central to the evaluation**, so the safety/alerting layer (cyclones, high waves, lightning, geofencing) is not a bonus feature — it's arguably the primary judged capability, with the conversational layer as the interface to it (even though officially categorized under the "Miscellaneous" theme on the SIH portal).

---

## 2. Complete Feature Requirements (Merged & Deduplicated)

### 2.1 Natural Language & Conversational Intelligence
- [ ] NLU of user intent — direct queries, exploratory questions, "what-if" scenarios
- [ ] Automatic language identification of the incoming query
- [ ] Response generation in the **same language**, with priority on Indian regional languages (Hindi, Tamil, Telugu, Malayalam, Kannada, Bengali, Marathi, Gujarati, Odia — chosen to match actual coastal-state fisherfolk populations, not a token 2–3 language demo)
- [ ] Contextual, multi-turn dialogue — session memory, query refinement, coreference resolution ("what about tomorrow?", "same for that region further north?")
- [ ] Voice-based query intake (STT/TTS) as a first-class channel, not an afterthought — the highest-stakes users (fishermen) are the least likely to type

### 2.2 Agentic / Multi-Agent Architecture
- [ ] Modular multi-agent system with visibly specialized agents (not a monolith wearing different hats)
- [ ] Orchestrator/planning agent that autonomously decomposes a complex query into sub-tasks and routes them
- [ ] Agent-to-agent communication/coordination protocol, with hand-offs visible for demo/audit purposes
- [ ] Tool-use / function-calling so agents can invoke real APIs, databases, and geospatial services
- [ ] Demonstrated autonomous collaboration on at least one genuinely complex query (multi-agent, multi-source) as the centerpiece demo

### 2.3 Data Discovery, Retrieval & Integration
- [ ] Intelligent data catalog selection: dynamically route and query the appropriate pre-indexed datasets per query context, rather than brittle hardcoding or unstable open-web crawling
- [ ] Integration with real Indian sources: INCOIS (PFZ, OSF, ERDDAP, hazard advisories), MOSDAC, Bhuvan, IMD (cyclone/lightning/CAP), Survey of India (tides), plus global providers (Copernicus CMEMS, Open-Meteo Marine, NASA)
- [ ] Handling of heterogeneous formats: NetCDF, GeoTIFF, GRIB, shapefiles/GeoJSON, REST/JSON, OPeNDAP, HTML/WebGIS-scraped tabular data
- [ ] Data harmonization/normalization into a common spatial-temporal reference frame across sources
- [ ] Caching/indexing layer for frequently requested regions/parameters to control latency and prevent upstream API rate-limiting

### 2.4 Spatial, Temporal & Contextual Reasoning
- [ ] Spatial reasoning — nearest PFZ zone, route corridors, EEZ/boundary proximity
- [ ] Temporal reasoning & trends — today vs. tomorrow, seasonal trends over weeks/months, forecast interpretation
- [ ] **Tidal height prediction & sea conditions** — high/low tide timing, water levels, and currents near target fishing/navigation points (explicitly required by PS Query #3)
- [ ] Cross-source correlation — e.g., SST + chlorophyll + wind/current pattern → probable fish aggregation zones; SST + chlorophyll + historical PFZ trend → productivity-decline diagnosis
- [ ] Causal/diagnostic reasoning for "why" questions, not just "what/where" lookups
- [ ] **Deterministic confidence/uncertainty estimation** — structured 3-tier confidence scoring (High / Medium / Low-data) based on data freshness, source authority, and sensor coverage, not arbitrary LLM guessing

### 2.5 Explainable, Evidence-Based Output
- [ ] Every recommendation cites the underlying data/evidence used (source, timestamp, threshold)
- [ ] Auto-generated maps and interactive geospatial visualizations (GeoJSON overlays, heatmaps, zone markers, route vectors) rendered interactively via Leaflet / Mapbox GL
- [ ] Charts/graphs for time-series or comparative data
- [ ] Human-readable, structured, actionable advisory text
- [ ] "Explain this recommendation" reasoning-trace capability, rendered differently for different personas (see §6)

### 2.6 Safety & Hazard Alerting
- [ ] Proactive alerts: adverse weather, high waves, lightning (IMD Damini / nowcasts), cyclones, storm surge, rip currents, low visibility
- [ ] **Geofencing**: IMBL (International Maritime Boundary Line) proximity, restricted/territorial waters, Marine Protected Areas, ecologically sensitive zones, other operational boundaries — treated as **hard constraints**, not soft suggestions
- [ ] Location-aware targeting (current or registered location, or planned route)
- [ ] Alert severity tiering (advisory / warning / danger) with deterministic rule-based triggers
- [ ] **Bathymetry-aware route optimization** — safe navigation planning combining prevailing/forecast weather, wave heights, currents, GEBCO depth contours (avoiding shallow hazards), and geofence polygons

---

## 3. Three-Way Gap Analysis: Description vs. Expected Solution vs. Real-World Practicality

This extends the earlier two-way gap check with a third column grounded in how India's marine-data ecosystem actually works today.

| Area | Implied by "Description" | Explicit in "Expected Solution" | Real-world grounding / treatment |
|---|---|---|---|
| Multi-agent collaboration | Implied ("collaborative AI agents") | Explicit | **Core.** Architect as first-class; make hand-offs visible in the demo. |
| Regional language support | Implied | Explicit | **Core.** Must map to actual coastal-state languages, not a generic i18n demo. |
| Data provenance/evidence citation | Implied ("evidence-based") | Explicit | **Core.** Especially load-bearing for safety alerts, where wrong info is a liability. |
| Real-time/near-real-time ingestion | Implied ("daily... vast volumes") | Not explicit | **Gap, but bounded by reality:** PFZ advisories update ~3×/week, not continuously — the system must expose data freshness ("as of [date]") rather than imply live conditions. |
| Offline / low-connectivity access | Not mentioned | Not mentioned | **Gap — critical.** Fishermen at sea have the least connectivity; India already solves the "last mile" via **Sagar Vani** (SMS/voice/radio/app in regional languages) — reference/integrate rather than reinvent. |
| Multi-modal query input (voice) | Not mentioned | Not mentioned | **Gap — added**, essential for the rural/fisherfolk user base. |
| Data licensing & access control | Not mentioned | Not mentioned | **Gap — added.** ISRO/govt data sources often carry usage policies; don't assume unrestricted redistribution. |
| Scalability across user types | Implied (multiple stakeholders) | Not explicit | **Gap — added.** Fishermen, researchers, and agencies need different depth/UX from the same underlying agents. |
| Geofencing as safety-critical | Mentioned in passing | Explicit | **Treatment:** boundary data must be sourced authoritatively, not LLM-approximated — a boundary error is a legal/safety incident, not a UX bug. |
| Distress/rescue integration | Not mentioned | Not mentioned | **Gap — worth acknowledging.** ISRO's own DAT-SG/Sagarmitra distress-alert program is the natural handoff point for at-sea emergencies. |

---

## 4. Data Ecosystem: Real Sources, Real Formats

### 4.1 Actual operational Indian & global marine-data sources

| Source | Operator | What it provides |
|---|---|---|
| **PFZ Advisory (WebGIS / Text)** | INCOIS | Potential Fishing Zones issued ~3×/week from SST + chlorophyll (NOAA-AVHRR, EUMETSAT, Oceansat-II/3, MODIS), covering ~1,223 coastal nodes |
| **INCOIS ERDDAP & LAS** (`erddap.incois.gov.in`, `las.incois.gov.in`) | INCOIS | Machine-readable oceanographic datasets (RESTful, OPeNDAP, JSON, CSV, NetCDF) — cleaner programmatic access to buoy, model, and satellite parameters |
| **Ocean State Forecast (OSF)** | INCOIS | Wave height, currents, sea-state forecasts, mixed layer depth |
| **Tide Predictions & Tide Gauges** | Survey of India / INCOIS | Official tidal tables (Survey of India) + real-time tide gauge observations (INCOIS TEWS / Ocean Portal); Stormglass.io as global API fallback |
| **Tsunami Early Warning, Storm Surge, High Wave Alerts** | INCOIS | Hazard-specific bulletins and operational warning feeds |
| **Coral Bleaching / Algal Bloom / Marine Heatwave Advisories** | INCOIS | Ecosystem-health signals, relevant to researchers, aquaculture, and MPA stakeholders |
| **Sagar Vani** | INCOIS | Existing multi-channel dissemination system (reference model for alert push via SMS/voice/radio in regional languages) |
| **MOSDAC** | ISRO/SAC | Near-real-time meteorology/oceanography products (SST, ocean color, INSAT-3D/3DR/3DS weather, ocean currents, cyclone track/genesis) |
| **Open-Meteo Marine Weather API** | Open-Meteo / Global Models | Free, open-access, zero-friction REST API for wave height, swell, direction, wave period, and ocean currents |
| **Bhuvan / VEDAS** | NRSC/ISRO | Geoportal hosting PFZ and thematic ocean layers for GIS visualization |
| **IMD (Bulletins, CAP, Damini)** | Ministry of Earth Sciences | Weather forecasts, cyclone bulletins, CAP warning feeds, and Damini lightning alert feeds |
| **GEBCO Global Bathymetry** | IHO / IOC UNESCO | 15 arc-second gridded ocean depth / bathymetry data — prerequisite for realistic, grounded vessel route optimization |
| **Marine Regions (VLIZ) & WDPA** | Flanders Marine Inst. / UNEP-WCMC | Authoritative maritime boundaries (EEZ, IMBL coordinates) and Marine Protected Area polygons (e.g. Gulf of Mannar) |
| **DAT-SG / Sagarmitra** | ISRO + Coast Guard | Distress alert transmitters for at-sea emergencies (reference/handoff integration point) |

**Practical implication:** your "marine data discovery agent" is not discovering data from the open internet — it's an intelligent catalog selector over this known, high-value set of endpoints and downloadable products. A meaningful share of engineering effort should go to the unglamorous ingestion/parsing layer (ERDDAP pulls, HTML/WebGIS scraping, NetCDF subsetting) rather than only the agent-reasoning layer, since that's what makes the demo credible to ISRO judges specifically.

### 4.2 Format & harmonization requirements
- Source formats to handle: **NetCDF, GeoTIFF, GRIB, shapefiles/GeoJSON, REST/JSON, OPeNDAP, and HTML/WebGIS-scraped tabular data**
- A **normalization pipeline** is needed to bring all sources into a common spatial-temporal reference frame before cross-source reasoning is possible — this is prerequisite infrastructure, not a bonus feature
- A **caching/indexing layer** for frequently requested regions/parameters keeps latency acceptable and guards against upstream server throttling

---

## 5. Multi-Agent Architecture (Aligned to ISRO's 9 Named Roles)

Reconciling the PS's explicitly suggested 9 roles with a concrete, buildable architecture:

| # | Agent | Responsibility | Implementation Note |
|---|---|---|---|
| 1 | **Planning Agent (Orchestrator)** | Parses intent, decomposes complex queries into sub-tasks, assigns execution order, and routes to specialists. | Demonstrates visible LangGraph state transitions and tool-routing logic. |
| 2 | **Marine Data Discovery Agent** | Knows the catalog (INCOIS, MOSDAC, ERDDAP, Survey of India, Open-Meteo); retrieves/parses target datasets per location & time. | Emits source metadata, acquisition timestamp, and freshness status. |
| 3 | **Weather Intelligence Agent** | Analyzes wind speed, wave height, swell period, rainfall, lightning alerts, and cyclone genesis/tracks. | Pulls from IMD, MOSDAC INSAT-3DR, and Open-Meteo Marine API. |
| 4 | **Ocean Analytics Agent** | Evaluates SST, chlorophyll-a concentrations, PFZ coordinates, historical persistence, and temporal trends/anomalies. | Handles both instant cross-variable correlation and multi-day temporal trend analysis. |
| 5 | **Geospatial Reasoning Agent** | Calculates vessel-to-zone distances, checks EEZ/IMBL and MPA geofence boundaries, and computes bathymetry-aware routes. | Uses GeoPandas/Shapely against authoritative boundary and GEBCO depth shapefiles. |
| 6 | **Risk Assessment Agent** | Evaluates hazard safety using **deterministic, rule-based threshold gating** (go/no-go, danger tiering, geofence breaches) + confidence scoring. | Critical safeguard: safety decisions are calculated mathematically, never hallucinated by LLM. |
| 7 | **Visualization Agent** | Generates interactive GeoJSON layers, heatmap coordinates, boundary vectors, and chart data for client rendering. | Emits structured JSON for Leaflet / Mapbox GL on the frontend (not static server images). |
| 8 | **Reporting Agent (Synthesis/Critic)** | Compiles synthesized, evidence-cited answers; attaches source datasets, timestamps, and confidence ratings to each claim. | Enforces strict citation standards across all outputs. |
| 9 | **User Interaction Agent** | Handles multilingual language ID, query translation (ingress), multi-turn session memory, and back-translation to user's language (egress). | Interfaces with IndicTrans2 / Bhashini / LLM translation across channels. |

A judge-facing demo must make agent hand-offs visible (e.g., a real-time trace panel showing *"User Interaction (Ingress) → Planning → Marine Discovery + Weather + Ocean Analytics → Geospatial → Risk Assessment → Visualization + Reporting → User Interaction (Egress)"*) rather than hiding orchestration behind a single chat bubble.

---

## 6. Stakeholder Deep-Dive

The PS names four groups explicitly (fishermen, researchers, coastal authorities, maritime operators) plus disaster management agencies. Treat these as **distinct personas** — different queries, literacy levels, connectivity, stakes, and required output depth — not one generic "user."

### 6.1 Small-Scale / Traditional Fishermen — largest, highest-stakes group
- **Context:** ~4 million marine fisherfolk in India, of whom ~0.9 million actively fish; most operate small mechanized or traditional craft with limited connectivity at sea.
- **Core needs:** Simple, voice-friendly, regional-language answers ("Is it safe tomorrow morning near [village]?"); PFZ location relative to home port, not raw lat/long; safety alerts reaching them on low-bandwidth channels.
- **Concrete requirements:** Low-literacy UI (icons, voice-first, minimal text); voice input/output (STT/TTS) in local dialect; offline caching of last-known advisories; **SMS/USSD fallback for feature phones**; proactive cyclone/storm push alerts via SMS in addition to app/chat; simple fuel-cost-aware nearest-viable-zone guidance.
- **Design implication:** Integrate with (or explicitly model your alert layer on) India's own **Sagar Vani** dissemination system rather than assuming a connected smartphone app is sufficient.
- **Risk if ignored:** A slick chatbot that only literate, smartphone-owning, English-speaking users can operate misses the primary beneficiary the PS is nominally protecting.

### 6.2a Commercial & Deep-Sea Fishing Vessel Operators
- **Needs:** Multi-day route optimization, fuel-cost-aware routing towards high-probability PFZs, EEZ/IMBL geofencing as a hard constraint (preventing accidental straying into international waters), ETA impact estimation from adverse sea states, and multi-day vessel planning.
- **Design implication:** Route optimization agent must factor in both bathymetry and fuel efficiency while treating boundary lines as non-negotiable hard barriers.

### 6.2b Maritime Shipping & Port Operators (e.g., JNPA / Major Ports)
- **Needs:** Port-level marine conditions (berthing safety, tidal windows for deep-draft container ships, visibility, approach-channel wave currents, storm surge impacts), extreme weather tracking, and fleet transit safety.
- **Design implication:** Requires high-resolution tide and wind/wave nowcasting for port navigation channels.

### 6.3 Marine & Fisheries Researchers / Scientists
- **Needs:** Raw/derived time-series access, not just prose summaries; downloadable exports (CSV, NetCDF, GeoTIFF); programmatic API access to the platform; historical trend/anomaly analysis (marine heatwaves, algal blooms); citation-grade metadata (sensor, algorithm version, resolution, acquisition time); comparative/what-if queries across long time ranges.
- **Design implication:** The conversational interface needs a "detail mode" — a good place for the Explainability/Reporting Agent to output structured, citable data instead of prose.

### 6.4 Coastal Authorities / State Fisheries Departments / Disaster Management Agencies (NDMA, SDMA, District Collectors, INCOIS)
- **Needs:** Regional/district-level aggregated dashboards; bulk advisory dissemination to registered fishermen in a zone; real-time cyclone/storm-surge tracking integration; escalation workflows that auto-notify agencies when severe thresholds are crossed; evacuation-zone mapping; historical incident correlation for policy planning; multi-user role-based access (admin/analyst/field officer); audit trail of alerts issued and outcomes; post-event reporting.
- **Design implication:** This persona wants dashboards and area rollups more than single Q&A turns — outputs should be reusable as briefing documents. Interoperability with the **Common Alerting Protocol (CAP)** standard is worth targeting so outputs integrate with existing government early-warning systems.

### 6.5 Indian Coast Guard / Navy / Maritime Rescue Coordination Centres (implicit stakeholder)
- Not named directly, but geofencing, IMBL alerts, and distress scenarios sit adjacent to their mandate. ISRO's own **DAT-SG / Sagarmitra** distress-alert program is the natural integration/handoff point for at-sea emergencies rather than reinventing distress signaling.

### 6.6 Coastal Aquaculture, Port, and Blue-Economy Operators
- Coastal aquaculture (shrimp farming, mariculture) is a major economic driver in coastal India, highly sensitive to harmful algal blooms (HABs), water quality degradation, and marine heatwaves. Ports care about wave height, visibility, and storm surge for berthing decisions — both map directly to INCOIS ecosystem & forecast services (Algal Bloom Information Service, Marine Heatwave Advisory, Water Quality Nowcast).

### 6.7 General Public / Coastal Communities / Tourists (lowest priority, still relevant given the Disaster Management theme)
- Simple hazard/safety queries ("is it safe to swim/boat here today"), cyclone/storm-surge evacuation guidance.

### 6.8 Cross-Cutting Needs (all stakeholders)
- Accessibility (screen-reader compatible UI, high-contrast mode)
- Trust & transparency — visible "data as of [timestamp]" freshness indicators everywhere
- Privacy — individual fisherman/vessel location data handled securely, with clear access controls
- Feedback loop — users can flag inaccurate advisories to improve the system over time
- Multi-platform delivery — web app, Android-first mobile app (rural reach), WhatsApp/SMS bot, IVR voice call for the lowest-connectivity zones

---

## 7. Pilot Region Selection: South Tamil Nadu (Thoothukudi–Rameswaram–Kanyakumari, Palk Bay & Gulf of Mannar)

Building a national-scale platform for a hackathon demo is neither feasible nor how ORCA should be judged. A single, well-chosen pilot region lets every agent (§5) and every stakeholder persona (§6) be demonstrated against **real, current, citable ground truth** instead of synthetic data — this section documents that choice and why.

### 7.1 Candidate regions considered

| Region | Pros | Cons |
|---|---|---|
| **South Tamil Nadu** (Thoothukudi–Rameswaram–Kanyakumari, incl. Palk Bay & Gulf of Mannar) | Academically validated, highly persistent PFZ hotspots (published studies show ~44.9% of hits clustering on the mid-shelf near Thoothukudi, driven by Thamirabarani river discharge) — real, citable ground truth to validate the Ocean Analytics agent against. Live, ongoing geofencing use case: the India–Sri Lanka IMBL in the Palk Strait sees fishermen detained regularly through 2026, mapping directly onto the PS's explicit geofencing/IMBL bullet. Gulf of Mannar Marine National Park gives a real MPA polygon for the "ecologically sensitive zones" bullet. NE monsoon cyclone exposure (Bay of Bengal) makes cyclone/lightning alert queries genuinely live, not hypothetical. Two adjacent INCOIS sectors (North TN, South TN) allow sector-boundary handling to be demoed. | Boundary-line data must come from an official/published source, not hand-drawn — given active bilateral sensitivity, the build must stay strictly factual/navigational. Cyclone season is seasonal (Oct–Dec); demoing outside that window is solved by supporting historical replay scenarios (e.g. Cyclone Gaja). |
| **Mumbai–JNPA (Maharashtra Coast)** | India's #1 container port hub (JNPA handles ~50% of India's containerized cargo, ranked 21st globally in 2026); premier demonstration for the "maritime operators / shipping" stakeholder persona; tidal windows and channel navigation are genuine live operational concerns; exposed to Arabian Sea cyclones (e.g. Cyclone Tauktae). | No nearby international boundary line — geofencing demo would have to rely on synthetic boundaries rather than high-stakes real-world boundaries. No comparable published PFZ-persistence ground truth datasets. Farther from the core ISRO/INCOIS Earth-Observation-for-Fisheries mission focus. |
| **Kerala** (Southeastern Arabian Sea coast) | Where PFZ advisories were first validated and remain best-studied (CMFRI/SAC research since 1981). Strong, visually dramatic seasonal upwelling → chlorophyll bloom signal, very telegenic on a map. Highest fishing-community population density in India — strong stakeholder story. Recent (2022–23) fish-landing validation studies exist to benchmark against. | No adjacent international-boundary tension → the geofencing/MPA bullet is weaker to demo with real stakes. Monsoon rough-sea safety angle is strong but less differentiated from any other coastal state. |
| **Gujarat** | Largest marine fish landing state in India — big stakeholder base. Arabian Sea upwelling zones give a distinct chlorophyll/SST signal from the east coast. | The nearby India–Pakistan Sir Creek boundary is undemarcated/disputed — using it as the geofencing demo case is a political-sensitivity risk not worth taking on. Lower cyclone frequency than the Bay of Bengal coast; lacks a well-documented MPA polygon equivalent to Gulf of Mannar. |
| **Andhra Pradesh / Odisha** | Highest cyclone frequency in India (repeated landfalls) — very strong for weather/lightning/cyclone-alert queries. | Two separate INCOIS sectors (North/South AP) plus Odisha adds complexity without a comparably strong geofencing or MPA narrative. Less academically-documented PFZ persistence data to validate against. |

### 7.2 Decision: South Tamil Nadu — Thoothukudi to Rameswaram, including Palk Bay and Gulf of Mannar

This is the one region where **all five stakeholder groups the PS names** have an active, current, non-hypothetical reason to use the platform:

- **Fishermen** — safety-critical: crossing the IMBL here has real, recently-reported consequences (as recent as this month)
- **Researchers** — published, citable PFZ-persistence ground truth to validate the Ocean Analytics agent against
- **Coastal authorities / disaster management** — NE monsoon cyclone exposure makes hazard alerts non-simulated
- **Maritime operators** — route optimization has genuine multi-layer constraints to route around (the international maritime boundary + the shallow/sensitive Gulf of Mannar MPA + depth contours), not an arbitrary polygon

**Why Mumbai–JNPA was evaluated but not chosen as the primary pilot:** While Mumbai–JNPA is India's premier shipping and container gateway, choosing it would leave the geofencing, MPA, and PFZ-validation requirements without real, citable ground truth to demonstrate against. South Tamil Nadu exercises all 9 agent capabilities simultaneously on a single shared map canvas.

**Cyclone Seasonality Mitigation (Replay Mode):** To ensure hazard alerting is fully demonstrable even outside the October–December NE monsoon window, the platform includes a "Historical Event Replay" mode featuring **Cyclone Gaja** (which struck South Tamil Nadu directly). This allows live demonstration of cyclone track tracking, wind/wave threshold breaches, and emergency warning cascades using authentic historic IMD/MOSDAC data.

### 7.3 Framing note for the demo (carries into build guidance, §9–§10)

Present the boundary-crossing feature strictly as a **fisherman-safety navigation aid** ("alert me before I approach the line"), not as commentary on the India–Sri Lanka dispute itself. This keeps the feature squarely technical/safety-oriented, which is also how ISRO/INCOIS judges will want to see it framed — consistent with the existing risk note in §10 that geofencing data must be authoritative and never LLM-approximated.

### 7.4 Implications for earlier sections

- **§4 Data Ecosystem:** prioritize INCOIS's North Tamil Nadu and South Tamil Nadu PFZ sectors, the Gulf of Mannar MPA boundary data, and the published Palk Strait/IMBL reference geometry as the first data-integration targets, ahead of a national rollout.
- **§5 Agent Architecture:** the Geospatial Reasoning Agent's geofencing logic and the Ocean Analytics Agent's PFZ-persistence validation should both be built and tested against this region first.
- **§6 Stakeholders:** use this region's real incident history (IMBL detentions, NE monsoon cyclones) as the concrete scenarios behind the fishermen, researcher, and disaster-management personas rather than generic examples.
- **§12 Sample Queries:** should include region-specific variants, e.g. *"How close am I to the Sri Lanka maritime boundary near Rameswaram?"* and *"Is Palk Bay safe to fish in given the current NE monsoon forecast?"*

---

## 8. Non-Functional Requirements

- **Latency:** Near-real-time response for safety-critical alerts (target: seconds, not minutes)
- **Reliability:** High availability specifically during cyclone/hazard events, when demand spikes hardest
- **Scalability:** Handle concurrent queries from large fisherfolk populations during hazard windows
- **Data freshness:** Explicit staleness indicators; automatic re-fetch scheduling matched to each source's real update cadence (e.g., PFZ ~3×/week, not continuous)
- **Security:** Secure handling of user location/identity data; authenticated access to upstream data sources
- **Interoperability:** Standards-based outputs (GeoJSON, CAP alerts) so the system can plug into existing government systems rather than becoming a silo
- **Explainability/Auditability:** Every generated advisory traceable to its source dataset(s) and reasoning chain — a legal/accountability requirement, not just good UX, given the disaster-management context

---

## 9. Build Plan — High-Level Task Breakdown

1. **Data Layer** — Identify/integrate sources (INCOIS PFZ, OSF, hazard advisories, MOSDAC, IMD, Bhuvan, global EO as needed); build ingestion pipelines, normalization layer, storage/indexing.
2. **Agent Layer** — Design orchestrator + specialist agents (§5); implement tool/function-calling interfaces into the data layer; implement spatial/temporal/contextual reasoning modules.
3. **Language Layer** — Language detection + multilingual NLU/NLG; multi-turn dialogue/session management; voice STT/TTS.
4. **Output Layer** — Map/chart/visualization generation; advisory text generation with evidence citations; explainability/reasoning-trace surface, rendered per-persona (§6).
5. **Alerting Layer** — Hazard-threshold detection logic; multi-channel alert dispatch (app push, SMS, IVR), ideally interoperable with or modeled on Sagar Vani.
6. **Stakeholder Interfaces** — Fishermen-facing simple app/voice/SMS interface; researcher-facing API + data export; authority/agency dashboards with role-based access.
7. **Cross-Cutting** — Auth, roles, privacy, audit logging; monitoring, freshness tracking, feedback loop.

---

## 10. Risks & Gaps to Address Proactively

- **LLM Hallucination in Safety-Critical Recommendations (P0 Risk):** In a marine safety system, an LLM hallucinating that "it is safe to venture to sea" during a high-wave/cyclone warning is a life-threatening failure mode. **Mitigation:** Go/no-go safety decisions and geofence alarms MUST be computed via deterministic, rule-based logic in the Risk Assessment Agent. The LLM acts purely as a linguistic summarizer and explanation synthesizer; it never generates the underlying safety classification.
- **Upstream Rate-Limiting & API Throttling:** Live demo traffic or rapid retries could trigger rate limits on external portals (IMD, INCOIS WebGIS). **Mitigation:** Implement in-memory / Redis caching with short TTLs (5–15 min) for live telemetry and longer TTLs (24h) for PFZ/boundary files.
- **Data latency and reliability:** PFZ advisories update ~3×/week — be explicit about freshness ("Data as of [timestamp]") rather than implying live conditions.
- **Connectivity at sea:** The highest-stakes users are least likely to have a live connection mid-voyage — design for pre-departure queries plus Sagar-Vani-style push alerts, not just a pull-based chatbot.
- **Geofencing accuracy is safety-critical:** An IMBL or MPA boundary error is a legal/safety incident, not a UX bug — source boundary data authoritatively (Marine Regions VLIZ & WDPA), don't let the LLM approximate coordinates.
- **Regional language coverage:** Claiming "supports Indian regional languages" without naming and testing specific languages relevant to actual fisherfolk populations will read as a token gesture to evaluators.
- **Explainability vs. simplicity trade-off:** Researchers want full methodology; fishermen want a one-line answer — design explicit per-persona rendering rather than one-size-fits-all output.
- **Data licensing:** Don't assume unrestricted redistribution rights over ISRO/INCOIS/IMD data products without checking usage terms.
- **Format/scraping fragility:** Several sources (notably PFZ WebGIS) are HTML-first, not REST — build resilient parsing with ERDDAP / fallback cached datasets, since this is a real point of demo failure.

---

## 11. Open Questions to Resolve Before Design Finalization

- Which specific data sources/APIs are officially provided or mandated by ISRO vs. left to participant choice?
- What is the expected user scale — a pilot region or a national rollout?
- Is offline/SMS/IVR delivery in scope for the hackathon submission, or is a connected app/web client assumed sufficient?
- What level of agent autonomy is expected — fully autonomous tool use, or human-in-the-loop review before safety alerts go out?
- Are there existing alert-format standards (e.g., CAP) that outputs are expected to conform to for interoperability with government systems?
- Is real integration with live INCOIS/MOSDAC endpoints expected for the demo, or is a representative subset/mock acceptable given access constraints?

---

## 12. Sample Queries to Design and Test Against

- "आज सबसे नज़दीक़ मछली पकड़ने का क्षेत्र कहाँ है?" (nearest PFZ today, in Hindi)
- "Is it safe to venture into the sea tomorrow morning near [coastal village]?"
- "What are the tide, weather, and sea conditions near [location]?"
- "Any lightning or cyclone alerts in my area this week?"
- "Which regions show high chlorophyll and favourable SST right now?"
- "What's the safest route from [port A] to [fishing ground B] given current sea state?"
- "Why has fish catch declined in [region] over the last month?"
- "Which zones should I avoid due to hazardous conditions or boundary restrictions?"
- *(Researcher persona)* "Show me the chlorophyll anomaly trend for the Arabian Sea over the last quarter, with source metadata."
- *(Authority persona)* "Give me a district-level risk summary for the next 48 hours ahead of the approaching system."

**Pilot-region-specific (South Tamil Nadu / Palk Bay / Gulf of Mannar, per §7):**
- "How close am I to the Sri Lanka maritime boundary near Rameswaram?"
- "Is Palk Bay safe to fish in given the current NE monsoon forecast?"
- "Where are the persistent fishing zones near Thoothukudi this week?"
- "Am I approaching the Gulf of Mannar Marine National Park boundary?"
- "Is there a cyclone risk for the Kanyakumari coast this weekend?"

---

*This master document reconciles the PS-text analysis (grounded in INCOIS/MOSDAC/Bhuvan/Sagar Vani/DAT-SG as of August 2026) with the requirements/task-breakdown document, resolving overlaps and carrying forward every unique requirement, gap, and open question from both.*
