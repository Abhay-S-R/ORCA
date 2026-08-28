# ORCA — Marine EcOsystem Reasoning with Collaborative Agents
## Master Analysis & Requirements Document (PS ID: 26176)

**Organization:** Indian Space Research Organisation (ISRO), Department of Space
**Category:** Software | **Theme:** Disaster Management
**Source:** Merges and reconciles two prior working documents — a PS-text analysis grounded in India's real marine-data ecosystem, and a requirements/task-breakdown document — into one master reference.

---

## 1. What This Problem Statement Is Really Asking For

Strip away the Agentic-AI framing and the core ask is: **build a conversational, multi-agent decision-support system that sits on top of India's fragmented marine data ecosystem** (satellite EO data, oceanographic observations, weather forecasts, GIS layers, public advisories) and turns a question like *"Is it safe to go to sea tomorrow?"* into a synthesized, explainable, multi-source answer — in the user's own language, with maps and evidence attached.

Four things separate this from a generic RAG chatbot, and each is a real evaluation axis a judge will probe:

1. **Multi-agent orchestration is explicit, not optional.** The PS names roles it wants to see: planning, marine data discovery, weather intelligence, ocean analytics, geospatial reasoning, risk assessment, visualization, reporting, user interaction. Judges will check whether agents are genuinely decomposed and collaborating, or whether it's one LLM call pretending to be five agents.
2. **Spatial-temporal correlation across heterogeneous sources**, not single-dataset lookups. "Why has fish productivity declined in region X" requires joining SST + chlorophyll + advisory history over time — a reasoning task, not a fetch.
3. **Explainability is a first-class deliverable**, not a nice-to-have. Every answer needs its evidence and reasoning trail attached — which datasets, which time window, which thresholds triggered the recommendation.
4. **This sits under the Disaster Management theme**, so the safety/alerting layer (cyclones, high waves, lightning, geofencing) is not a bonus feature — it's arguably the primary judged capability, with the conversational layer as the interface to it.

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
- [ ] Autonomous discovery of relevant datasets per query context, rather than hardcoded per-query API calls
- [ ] Integration with real Indian sources: INCOIS (PFZ, OSF, hazard advisories), MOSDAC, Bhuvan, IMD, plus global EO providers (NASA, Copernicus) where useful
- [ ] Handling of heterogeneous formats: NetCDF, GeoTIFF, GRIB, shapefiles, REST/JSON, HTML/WebGIS-scraped tabular data (many INCOIS products are not clean REST APIs — budget real engineering time here)
- [ ] Data harmonization/normalization into a common spatial-temporal reference frame across sources
- [ ] Caching/indexing for frequently requested regions/parameters to control latency and API load

### 2.4 Spatial, Temporal & Contextual Reasoning
- [ ] Spatial reasoning — nearest zone, route corridors, EEZ/boundary proximity
- [ ] Temporal reasoning — today vs. tomorrow, trend over days/weeks, forecast interpretation
- [ ] Cross-source correlation — e.g., SST + chlorophyll + wind pattern → probable fish aggregation zones; SST + chlorophyll + historical PFZ trend → productivity-decline diagnosis
- [ ] Causal/diagnostic reasoning for "why" questions, not just "what/where" lookups
- [ ] Confidence/uncertainty estimation when correlating multiple heterogeneous, possibly conflicting sources

### 2.5 Explainable, Evidence-Based Output
- [ ] Every recommendation cites the underlying data/evidence used (source, timestamp, threshold)
- [ ] Auto-generated maps and interactive geospatial visualizations (heatmaps, overlays, zone markers)
- [ ] Charts/graphs for time-series or comparative data
- [ ] Human-readable, structured, actionable advisory text
- [ ] "Explain this recommendation" reasoning-trace capability, rendered differently for different personas (see §6)

### 2.6 Safety & Hazard Alerting
- [ ] Proactive alerts: adverse weather, high waves, lightning, cyclones, storm surge, rip currents, low visibility
- [ ] **Geofencing**: IMBL (International Maritime Boundary Line) proximity, restricted/territorial waters, Marine Protected Areas, ecologically sensitive zones, other operational boundaries — treated as **hard constraints**, not soft suggestions
- [ ] Location-aware targeting (current or registered location, or planned route)
- [ ] Alert severity tiering (advisory / warning / danger) in clear, non-technical language
- [ ] Route optimization / safe navigation planning using current + forecast conditions

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

### 4.1 Actual operational Indian marine-data sources

| Source | Operator | What it provides |
|---|---|---|
| **PFZ Advisory (WebGIS)** | INCOIS | Potential Fishing Zones issued ~3×/week from SST + chlorophyll (NOAA-AVHRR, EUMETSAT, Oceansat-II, MODIS), covering ~1,200+ coastal nodes, delivered via WebGIS/HTML-first pages rather than clean REST |
| **Ocean State Forecast (OSF)** | INCOIS | Wave height, currents, sea-state forecasts |
| **Tsunami Early Warning, Storm Surge Warning, High Wave Alerts** | INCOIS | Hazard-specific alerts, already operational |
| **Coral Bleaching / Algal Bloom / Marine Heatwave Advisories** | INCOIS | Ecosystem-health signals, relevant to researchers and MPA-adjacent stakeholders |
| **Sagar Vani** | INCOIS | Existing multi-channel dissemination system — pushes advisories/warnings in regional languages via radio, TV, voice calls, SMS, social media, mobile apps, email. The natural "last mile" for your alert layer. |
| **MOSDAC** | ISRO/SAC | Near-real-time meteorology/oceanography products, including cloudburst/heavy-rain alerts and cyclone genesis/track/intensity prediction |
| **Bhuvan** | NRSC/ISRO | Geoportal hosting PFZ and other ocean-service layers for GIS visualization |
| **IMD** | Ministry of Earth Sciences | Weather forecasts, cyclone bulletins |
| **DAT-SG / Sagarmitra** | ISRO + Coast Guard | Distress alert transmitters for at-sea emergencies, feeding Coast Guard Maritime Rescue Coordination Centres |

**Practical implication:** your "marine data discovery agent" is not discovering data from the open internet — it's an orchestration layer over a known, finite set of INCOIS/MOSDAC/Bhuvan/IMD endpoints and downloadable products. A meaningful share of engineering effort should go to the unglamorous ingestion/parsing layer (HTML/WebGIS scraping, format conversion) rather than only the agent-reasoning layer, since that's what makes the demo credible to ISRO judges specifically.

### 4.2 Format & harmonization requirements
- Source formats to handle: **NetCDF, GeoTIFF, GRIB, shapefiles, REST/JSON, and HTML/WebGIS-scraped tabular data**
- A **normalization pipeline** is needed to bring all sources into a common spatial-temporal reference frame before cross-source reasoning is possible — this is prerequisite infrastructure, not a bonus feature
- A **caching/indexing layer** for frequently requested regions/parameters keeps latency acceptable, especially important since some source pages are not built for high query volume

---

## 5. Multi-Agent Architecture

Reconciling the PS's named roles with a concrete, buildable agent set:

| # | Agent | Responsibility |
|---|---|---|
| 1 | **Orchestrator / Planning Agent** | Parses intent, detects language, decomposes the query into sub-tasks, routes to specialists, merges results. This is the piece that must visibly demonstrate "agentic" behavior for judges. |
| 2 | **Marine Data Discovery / Retrieval Agent** | Knows the INCOIS/MOSDAC/Bhuvan/IMD catalog; fetches/parses the right products for the query's location and time window. |
| 3 | **Weather Intelligence Agent** | Cyclone tracks, lightning, wind, rainfall forecasts. |
| 4 | **Ocean Analytics Agent** | SST/chlorophyll trend analysis, PFZ interpretation, anomaly detection. |
| 5 | **Geospatial / Spatial Reasoning Agent** | Distance/route calculations, EEZ/IMBL/MPA geofencing checks, nearest-zone queries. |
| 6 | **Temporal Reasoning Agent** | Historical comparison, trend extraction, forecast-window interpretation (can be merged with #4 in a leaner build, but keep the function distinct). |
| 7 | **Risk / Hazard-Safety Agent** | Combines hazard signals into a go/no-go or risk-tier recommendation with explicit thresholds. |
| 8 | **Visualization Agent** | Renders maps, chart overlays, geofence boundaries. |
| 9 | **Explainability / Reporting Agent** | Compiles the evidence trail — sources, timestamps, thresholds used — attached to every answer; also produces researcher/authority-grade structured output. |
| 10 | **User Interaction Agent** | Manages multi-turn state, language rendering, and channel formatting (chat vs. alert vs. dashboard vs. Sagar-Vani-style broadcast). |

A judge-facing demo should make agent hand-offs visible (e.g., a trace/log panel showing *"Planning Agent → Ocean Analytics Agent → Risk Agent → Reporting Agent"*) rather than hiding orchestration behind a single chat bubble.

---

## 6. Stakeholder Deep-Dive

The PS names four groups explicitly (fishermen, researchers, coastal authorities, maritime operators) plus disaster management agencies. Treat these as **distinct personas** — different queries, literacy levels, connectivity, stakes, and required output depth — not one generic "user."

### 6.1 Small-Scale / Traditional Fishermen — largest, highest-stakes group
- **Context:** ~4 million marine fisherfolk in India, of whom ~0.9 million actively fish; most operate small mechanized or traditional craft with limited connectivity at sea.
- **Core needs:** Simple, voice-friendly, regional-language answers ("Is it safe tomorrow morning near [village]?"); PFZ location relative to home port, not raw lat/long; safety alerts reaching them on low-bandwidth channels.
- **Concrete requirements:** Low-literacy UI (icons, voice-first, minimal text); voice input/output (STT/TTS) in local dialect; offline caching of last-known advisories; **SMS/USSD fallback for feature phones**; proactive cyclone/storm push alerts via SMS in addition to app/chat; simple fuel-cost-aware nearest-viable-zone guidance.
- **Design implication:** Integrate with (or explicitly model your alert layer on) India's own **Sagar Vani** dissemination system rather than assuming a connected smartphone app is sufficient.
- **Risk if ignored:** A slick chatbot that only literate, smartphone-owning, English-speaking users can operate misses the primary beneficiary the PS is nominally protecting.

### 6.2 Commercial / Deep-Sea Fishing Vessel Operators & Maritime Operators (shipping, ports, logistics)
- **Needs:** Multi-day route optimization, fuel-cost-aware routing around PFZs, EEZ/IMBL geofencing as a hard constraint (Indian fishermen straying into Sri Lankan/Pakistani waters is a recurring real incident category), ETA impact estimation from adverse conditions, port-level advisories (berthing safety, visibility, tidal windows), fleet-level multi-vessel monitoring.
- **Design implication:** Forecast confidence/uncertainty must be exposed, not just point predictions; the routing agent must treat geofences as non-negotiable constraints.

### 6.3 Marine & Fisheries Researchers / Scientists
- **Needs:** Raw/derived time-series access, not just prose summaries; downloadable exports (CSV, NetCDF, GeoTIFF); programmatic API access to the platform; historical trend/anomaly analysis (marine heatwaves, algal blooms); citation-grade metadata (sensor, algorithm version, resolution, acquisition time); comparative/what-if queries across long time ranges.
- **Design implication:** The conversational interface needs a "detail mode" — a good place for the Explainability/Reporting Agent to output structured, citable data instead of prose.

### 6.4 Coastal Authorities / State Fisheries Departments / Disaster Management Agencies (NDMA, SDMA, District Collectors, INCOIS)
- **Needs:** Regional/district-level aggregated dashboards; bulk advisory dissemination to registered fishermen in a zone; real-time cyclone/storm-surge tracking integration; escalation workflows that auto-notify agencies when severe thresholds are crossed; evacuation-zone mapping; historical incident correlation for policy planning; multi-user role-based access (admin/analyst/field officer); audit trail of alerts issued and outcomes; post-event reporting.
- **Design implication:** This persona wants dashboards and area rollups more than single Q&A turns — outputs should be reusable as briefing documents. Interoperability with the **Common Alerting Protocol (CAP)** standard is worth targeting so outputs integrate with existing government early-warning systems.

### 6.5 Indian Coast Guard / Navy / Maritime Rescue Coordination Centres (implicit stakeholder)
- Not named directly, but geofencing, IMBL alerts, and distress scenarios sit adjacent to their mandate. ISRO's own **DAT-SG / Sagarmitra** distress-alert program is the natural integration/handoff point for at-sea emergencies rather than reinventing distress signaling.

### 6.6 Aquaculture, Port, and Blue-Economy Operators (secondary)
- Coastal aquaculture cares about harmful algal blooms, water quality, marine heatwaves; ports/shipping care about wave height, visibility, storm surge for berthing decisions — both map to existing INCOIS services (Algal Bloom Information Service, Marine Heatwave Advisory, Water Quality Nowcast) your discovery agent should be able to reach.

### 6.7 General Public / Coastal Communities / Tourists (lowest priority, still relevant given the Disaster Management theme)
- Simple hazard/safety queries ("is it safe to swim/boat here today"), cyclone/storm-surge evacuation guidance.

### 6.8 Cross-Cutting Needs (all stakeholders)
- Accessibility (screen-reader compatible UI, high-contrast mode)
- Trust & transparency — visible "data as of [timestamp]" freshness indicators everywhere
- Privacy — individual fisherman/vessel location data handled securely, with clear access controls
- Feedback loop — users can flag inaccurate advisories to improve the system over time
- Multi-platform delivery — web app, Android-first mobile app (rural reach), WhatsApp/SMS bot, IVR voice call for the lowest-connectivity zones

---

## 7. Non-Functional Requirements

- **Latency:** Near-real-time response for safety-critical alerts (target: seconds, not minutes)
- **Reliability:** High availability specifically during cyclone/hazard events, when demand spikes hardest
- **Scalability:** Handle concurrent queries from large fisherfolk populations during hazard windows
- **Data freshness:** Explicit staleness indicators; automatic re-fetch scheduling matched to each source's real update cadence (e.g., PFZ ~3×/week, not continuous)
- **Security:** Secure handling of user location/identity data; authenticated access to upstream data sources
- **Interoperability:** Standards-based outputs (GeoJSON, CAP alerts) so the system can plug into existing government systems rather than becoming a silo
- **Explainability/Auditability:** Every generated advisory traceable to its source dataset(s) and reasoning chain — a legal/accountability requirement, not just good UX, given the disaster-management context

---

## 8. Build Plan — High-Level Task Breakdown

1. **Data Layer** — Identify/integrate sources (INCOIS PFZ, OSF, hazard advisories, MOSDAC, IMD, Bhuvan, global EO as needed); build ingestion pipelines, normalization layer, storage/indexing.
2. **Agent Layer** — Design orchestrator + specialist agents (§5); implement tool/function-calling interfaces into the data layer; implement spatial/temporal/contextual reasoning modules.
3. **Language Layer** — Language detection + multilingual NLU/NLG; multi-turn dialogue/session management; voice STT/TTS.
4. **Output Layer** — Map/chart/visualization generation; advisory text generation with evidence citations; explainability/reasoning-trace surface, rendered per-persona (§6).
5. **Alerting Layer** — Hazard-threshold detection logic; multi-channel alert dispatch (app push, SMS, IVR), ideally interoperable with or modeled on Sagar Vani.
6. **Stakeholder Interfaces** — Fishermen-facing simple app/voice/SMS interface; researcher-facing API + data export; authority/agency dashboards with role-based access.
7. **Cross-Cutting** — Auth, roles, privacy, audit logging; monitoring, freshness tracking, feedback loop.

---

## 9. Risks & Gaps to Address Proactively

- **Data latency and reliability:** PFZ advisories update ~3×/week — be explicit about freshness rather than implying live conditions.
- **Connectivity at sea:** the highest-stakes users are least likely to have a live connection mid-voyage — design for pre-departure queries plus Sagar-Vani-style push alerts, not just a pull-based chatbot.
- **Geofencing accuracy is safety-critical:** an IMBL or MPA boundary error is a legal/safety incident, not a UX bug — source boundary data authoritatively, don't let the LLM approximate it.
- **Regional language coverage:** claiming "supports Indian regional languages" without naming and testing specific languages relevant to actual fisherfolk populations will read as a token gesture to evaluators.
- **Explainability vs. simplicity trade-off:** researchers want full methodology; fishermen want a one-line answer — design explicit per-persona rendering rather than one-size-fits-all output.
- **Data licensing:** don't assume unrestricted redistribution rights over ISRO/INCOIS/IMD data products without checking usage terms.
- **Format/scraping fragility:** several sources (notably PFZ WebGIS) are HTML-first, not REST — build resilient parsing with fallbacks, since this is a real point of demo failure.

---

## 10. Open Questions to Resolve Before Design Finalization

- Which specific data sources/APIs are officially provided or mandated by ISRO vs. left to participant choice?
- What is the expected user scale — a pilot region or a national rollout?
- Is offline/SMS/IVR delivery in scope for the hackathon submission, or is a connected app/web client assumed sufficient?
- What level of agent autonomy is expected — fully autonomous tool use, or human-in-the-loop review before safety alerts go out?
- Are there existing alert-format standards (e.g., CAP) that outputs are expected to conform to for interoperability with government systems?
- Is real integration with live INCOIS/MOSDAC endpoints expected for the demo, or is a representative subset/mock acceptable given access constraints?

---

## 11. Sample Queries to Design and Test Against

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

---

*This master document reconciles the PS-text analysis (grounded in INCOIS/MOSDAC/Bhuvan/Sagar Vani/DAT-SG as of August 2026) with the requirements/task-breakdown document, resolving overlaps and carrying forward every unique requirement, gap, and open question from both.*
