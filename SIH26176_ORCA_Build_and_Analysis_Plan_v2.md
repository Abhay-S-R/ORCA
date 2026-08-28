# 🌊 SIH26176 — ORCA: Marine EcOsystem Reasoning with Collaborative Agents
### Consolidated Build & Analysis Plan v2 — Team of 6

> **Sponsor:** ISRO (Department of Space) | **Track:** Software | **Theme:** Miscellaneous / Space Technology
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
User Query (any language, multi-turn)
        │
        ▼
┌────────────────────────┐
│ User Interaction Agent   │ → language ID, translation in/out, session/context memory
└────────────────────────┘
        │
        ▼
┌────────────────────────┐
│ Planning Agent (Orchestr.)│ → intent → sub-task decomposition, agent routing, hand-off order
└────────────────────────┘
        │
   ┌────┼─────────────┬────────────────┬─────────────────┐
   ▼    ▼              ▼                ▼                 ▼
┌────────────┐ ┌───────────────┐ ┌───────────────┐ ┌──────────────────┐
│Marine Data  │ │Weather        │ │Ocean Analytics │ │Geospatial         │
│Discovery    │ │Intelligence   │ │Agent            │ │Reasoning Agent     │
│Agent        │ │Agent           │ │(SST/chl/PFZ    │ │(spatial-temporal   │
│(finds/pulls │ │(wind, waves,   │ │correlation,    │ │correlation, route  │
│right dataset│ │currents,       │ │trend/anomaly)  │ │+ boundary geometry)│
│per query)   │ │cyclone/lightning)│               │ │                    │
└────────────┘ └───────────────┘ └───────────────┘ └──────────────────┘
        │              │                │                    │
        └──────────────┴────────┬───────┴────────────────────┘
                                 ▼
                    ┌─────────────────────┐
                    │ Risk Assessment Agent │ → hazard scoring, geofence violation checks,
                    │                        │   confidence/uncertainty tiering
                    └─────────────────────┘
                                 ▼
                    ┌─────────────────────┐
                    │ Visualization Agent    │ → map overlays, chart generation
                    └─────────────────────┘
                                 ▼
                    ┌─────────────────────┐
                    │ Reporting Agent        │ → evidence-cited synthesized answer,
                    │ (Synthesis/Critic)     │   cites which agent/dataset backs each claim
                    └─────────────────────┘
                                 ▼
                    ┌─────────────────────┐
                    │ User Interaction Agent │ → back-translation, final chat + map response
                    └─────────────────────┘
                                 ▼
                            User (chat + map)
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

## 2. Tech Stack (unchanged core, lightly refined)

| Layer | Choice | Notes |
|---|---|---|
| Agent orchestration | **LangGraph** (preferred) | Explicit state graph proves genuine hand-offs; CrewAI as backup |
| LLM | Model-agnostic API layer | Keep swappable — judges ask "what if the LLM API dies mid-demo" |
| Vector DB / RAG | Chroma or FAISS | For advisories, historical reports, marine documents |
| Data pipeline | Python — pandas, xarray, netCDF4 | Satellite data ships as NetCDF/HDF5; budget real time here |
| Backend | FastAPI | Agent-serving + REST |
| Frontend | Next.js (or Streamlit if time-constrained) | Chat + map |
| Map/geospatial | Leaflet or Mapbox GL + GeoPandas/Shapely for geofence math | SST/chlorophyll heatmaps, PFZ pins, boundary polygons |
| Multilingual | IndicTrans2 / Bhashini API / LLM-native translation | PS explicitly names "Indian regional languages" as a priority, not a stretch |
| Alerts | Polling against IMD/INCOIS feeds | Cyclone/lightning ingestion |

---

## 3. Data Sources — What's Really Available, and the Access Friction (verified)

| Source | What it gives you | Access reality (verified) | Action required |
|---|---|---|---|
| **MOSDAC** (ISRO/SAC) | SST, ocean color, INSAT-3D/3DR weather, ocean currents, salinity, wave/eddy products | Two tiers: (1) **Open Data** — free, no login, non-commercial use, covers Land/Ocean/Atmosphere derived products; (2) **Full/near-real-time data** — requires **registered-user SignUp**, email-verified, then admin approval by email. Near-real-time needs a **"standing order"** placed after login (max 1 month duration, renewable, privileged-user feature). There's also a documented **Satellite Data Download API** and SFTP service. | 🔴 **Register on mosdac.gov.in NOW** (SignUp form → email verification → wait for approval email — this has historically taken days, not hours). Separately request **API/SFTP credentials** if you plan programmatic pulls, and place a **standing order** once approved if you need near-real-time (not just archived) data. |
| **INCOIS** | PFZ advisories (14 coastal sectors: Gujarat→Andaman/Nicobar), Tuna advisory, Ocean State Forecasts (SST, mixed layer depth, wave height, wind), text + WebGIS + GIS-server map layers | PFZ Advisory, WebGIS, and text-data pages (`incois.gov.in/MarineFisheries/...`, `incois.gov.in/geoportal/MFASPFZ`) are **publicly browsable today, no login** — but this is a **map/HTML/text-page product**, not a clean bulk API. Getting structured lat/long PFZ points programmatically means scraping the text-data endpoint or geoportal layer, not calling a documented REST API. | 🟡 No registration needed to view — but you should **email INCOIS (ESSO-INCOIS, Hyderabad) requesting a structured/bulk data feed or API for PFZ advisories** for your specific coastal sector, since the public interface is view-only. Treat scraping as a fallback, not the primary plan — a sponsor-approved feed is a strong judge talking point ("we requested official access"). |
| **Bhuvan / VEDAS** (ISRO/NRSC geoportal) | Imagery, derived geospatial layers, thematic ocean layers (Bhuvan hosts its own PFZ page too, sourced from INCOIS) | Public, registration required for most download/API services (same pattern as MOSDAC — NRSC-run sign-up). | 🔴 **Register on bhuvan.nrsc.gov.in / VEDAS** on day one alongside MOSDAC. |
| **IMD** | Cyclone/lightning alerts, weather warnings | Public bulletins/RSS-style feeds; no clean unified API for all alert types | 🟠 Identify the specific IMD bulletin/RSS endpoints for your target region before committing to "real-time IMD ingestion" as a claim. |
| **Copernicus Marine (CMEMS)** | Global ocean reanalysis — SST, currents, waves | Free registration, mature REST/OPeNDAP API | 🟡 Strong **fallback** if Indian portals lag — register early too, it's low-friction. |
| **NASA Ocean Color / MODIS-Aqua** | Chlorophyll, SST | Free, well-documented API | 🟡 Fallback for chlorophyll if MOSDAC access is delayed. |
| **Global Fishing Watch** | Vessel activity/AIS | Free, rate-limited | 🟢 Optional/stretch — only if geofencing/route-optimization becomes a focus area. |

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
| 1 | **"Multi-agent" is trivially fake-able** with one prompt wearing labels | This is the single most likely judge attack, and the official PS explicitly asks for "collaboration among specialized agents" — judges will have read this line | Structured JSON hand-off contract (Section 1) + visible trace log; rehearse showing Agent A's raw output being consumed by Agent B, live |
| 2 | **MOSDAC/Bhuvan/INCOIS access latency** | Registration approval has historically taken days; near-real-time data needs an extra "standing order" step most teams won't know about | Register everything in the first 48 hours (Section 3 checklist); Copernicus/NASA fallback ready before you need it, not after |
| 3 | **INCOIS PFZ data isn't a clean API** — it's a WebGIS/text page | Teams often discover this only when they try to integrate it, losing a day to scraping | Budget scraping time explicitly in Phase 2, or send the direct INCOIS request early (Section 3, item 5) |
| 4 | **Geofencing correctness** (MPAs, EEZ/international boundary lines, restricted zones) | Getting maritime boundary geometry wrong is both a technical bug and a factual/diplomatic sensitivity (international boundaries) — a domain-literate judge will check this | Use only official/public boundary datasets (e.g., published EEZ shapefiles), don't hand-draw approximate lines; caveat any approximated boundary explicitly in the UI |
| 5 | **Multilingual is core, not a stretch** per the official text ("emphasis on supporting Indian regional languages") | v1 draft treated this as a Phase 5 add-on; the official PS puts it in the *Expected Solution* capability list itself | Design the language-detection/translation layer into the architecture from Phase 1, not bolted on later — even if you ship only 2–3 languages, the pipeline should be structurally first-class |
| 6 | **The "why did catch decline" root-cause query** | Hardest of the 8 official example queries — requires correlating historical trend data your team may not have | Either scope it out explicitly and say so in the demo ("we prioritized the 7 real-time queries; root-cause trend analysis is our stretch goal") or find one real historical dataset (even INCOIS/CMFRI catch statistics) to make one narrow version of this work |
| 7 | **Ocean data messiness** (cloud cover, missing satellite passes) | Real satellite data has gaps; AI-generated pipeline code often fails silently on this | Explicit "no data / low confidence" states everywhere — never let a missing value silently become a wrong answer |
| 8 | **Explainability as a literal grading line, not a vibe** | PS says "reliable recommendations together with the supporting evidence and reasoning used to derive each response" — this is closer to a rubric line than a suggestion | Every final answer must cite which agent + which dataset + what timestamp backed each claim, not just "confidence: high" |
| 9 | **LLM API downtime mid-demo** | Single point of failure | Model-agnostic reasoning layer, backup provider pre-configured and tested, not just claimed |
| 10 | **Scope creep across 9 named agent roles** | Trying to build all 9 as fully separate, fully-functional agents in a hackathon window is unrealistic | Build all 9 as real modular components with real hand-offs, but let some be intentionally thin (e.g., Reporting Agent can be simple templated synthesis) — thinness is fine, fakeness is not |

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
| **Phase 0 (pre-hackathon, do this week)** | Register MOSDAC + Bhuvan/VEDAS + send INCOIS bulk-data request + register Copernicus/NASA fallback; pick coastal region; pre-download snapshot | All 5 registration/request items in Section 3 actioned |
| **Phase 1** | Design 9-agent graph on paper; lock JSON hand-off schema; map each of the 8 official example queries to which agents fire | Architecture doc + schema, reviewed against official PS text line-by-line |
| **Phase 2** | Data-access layer per agent (real API + cached fallback); resolve the INCOIS scraping-vs-API question | Each agent independently fetches/returns structured data with source+timestamp |
| **Phase 3** | Orchestrator + Risk Assessment + Reporting agents; wire real hand-offs | End-to-end query → 9-agent trace → cited answer, logged |
| **Phase 4** | Frontend: chat + map + confidence display + visible trace panel | Working demo UI |
| **Phase 5** | Multilingual layer (should already be structurally wired from Phase 1 — this phase is filling it in, not designing it) | Query/response works in 2–3 languages |
| **Phase 6** | Stress-test: swap a data source live, break an agent's input, test missing-satellite-pass edge case, test a wrong-region geofence query | System degrades visibly and gracefully, never silently |
| **Phase 7** | Demo scripting using the **official 8 example queries** as your script backbone; Q&A rehearsal against Section 7 below | Rehearsed live orchestration-trace demo |

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
