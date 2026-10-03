# ORCA — Feature Analysis Report
### Marine EcOsystem Reasoning with Collaborative Agents | SIH 26176 (ISRO)

---

## 1. Existing Features Extracted from the Problem Statement

Reading the SIH 26176 brief closely, the mandated feature set breaks into five layers:

**A. Conversational / NLP layer**
- Natural-language query understanding, intent decomposition into executable tasks
- Automatic language identification and reply in the same language, with priority on Indian regional languages
- Multi-turn, contextual conversation with query refinement

**B. Data-integration layer**
- Autonomous discovery/retrieval of satellite EO data (Oceansat SST, chlorophyll), GIS layers, weather services, oceanographic observations, marine advisories
- Fusion of heterogeneous public-domain sources into one pipeline

**C. Reasoning layer**
- Spatial, temporal and contextual reasoning that correlates multiple data sources (not single-dataset lookups)
- Explainable, evidence-backed recommendations (reasoning shown, not just an answer)
- Root-cause style queries (e.g. "why has fish productivity declined")

**D. Safety & compliance layer**
- Proactive hazard alerts: high waves, lightning, cyclones, adverse weather
- Geofencing notifications near IMBL/restricted waters/MPAs/ecologically sensitive zones
- Identification of zones to avoid due to hazards or geofencing

**E. Decision-support & output layer**
- Potential Fishing Zone (PFZ) discovery ("nearest PFZ today")
- Tide/weather/sea-state summaries for a specific location
- Route optimisation / safe navigation planning
- Outputs via conversational text, maps, alerts, interactive geospatial visualisation
- Multi-agent architecture: planner, marine data discovery, weather intelligence, ocean analytics, geospatial reasoning, risk assessment, visualisation, reporting, user-interaction agents, working collaboratively

This is the full "required" feature envelope every team is being scored against — it is intentionally broad and data-source-agnostic, which is why (as the research below shows) most teams converge on a similar architecture.

---

## 2. Existing Solutions Researched

### 2.1 Government / official India platforms

| Platform | Owner | Key features |
|---|---|---|
| **PFZ Advisory (WebGIS)** | INCOIS | Daily PFZ bulletins for <cite index="3-1">around 1,223 coastal nodes</cite> using SST + chlorophyll from Oceansat/NOAA; layer toggles for SST, chlorophyll, PFZ, EEZ sectors, landing centres, bathymetry; species-specific advisories to separate exploited vs under-exploited stocks |
| **SAMUDRA mobile app** | INCOIS | <cite index="12-1">Multilingual access in English, Hindi and eight coastal languages</cite>; <cite index="17-1">home-screen active-alert feed for high-wave, swell-surge, currents, tsunami and storm-surge</cite>; <cite index="12-1">Tuna Fishing Advisory and Small Vessel Advisory screens, saved/favourite fishing-zone lookup</cite>; <cite index="12-1">5-day Ocean State Forecast and tide predictions</cite> |
| **Bhuvan (ISRO/NRSC)** | ISRO | PFZ layer embedded in Bhuvan 2D portal, generalized national GIS base layers |
| **SMS-based PFZ/OSF service** | INCOIS | <cite index="4-1">Legacy SMS delivery of fishing-zone and ocean-state forecasts to roughly seven lakh fishermen</cite> — the pre-app fallback channel that still matters for connectivity-poor users |

**What these are missing:** none of them are conversational, none reason across sources to produce a single synthesized answer, none explain *why* a recommendation was made, and geofencing/route-planning is not present as a user-facing feature.

### 2.2 Global marine-weather & fishing apps

| Product | Notable features |
|---|---|
| **Windy / Windy.app** | 40+ overlaid model layers, animated wind/wave tracker, manual multi-model comparison |
| **PredictWind** | <cite index="37-1">Proprietary PWAi/PWG/PWE forecast models blended with ECMWF, GFS, ICON, UKMO</cite>; <cite index="37-1">user-configurable threshold alerts for wind/wave conditions</cite> |
| **FishWeather** | <cite index="41-1">125,000+ crowd and government weather stations fused with NOAA/NWS/METAR/ASOS/CWOP feeds</cite>, proprietary "Nearcast AI" short-range prediction |
| **Fishbrain / FishAngler** | Crowd-sourced catch logs, community hotspot maps, solunar bite-time calendars, offline maps |
| **SeaLegs AI** | <cite index="38-1">Automated agreement/disagreement scoring across 12+ weather models</cite>, route-based AI trip-safety analysis |
| **Global Fishing Watch** | <cite index="39-1">Public vessel-track monitoring across EEZs and marine protected areas, aimed at curbing illegal fishing and habitat destruction</cite> — a transparency/enforcement tool rather than a fisher-safety tool |

**Gap vs India context:** none of these ingest Indian-specific IMD/INCOIS bulletins, none speak Indian regional languages, none are built for low-literacy/low-connectivity coastal users, and none combine safety + PFZ + geofencing + route planning in one conversational agent.

### 2.3 Direct competitor prototypes (other SIH 26176 teams — most relevant benchmark)

Since this is an active hackathon problem statement, multiple teams have already published prototypes literally named "ORCA" for SIH26176. These are the most useful comparison set because they show what "good enough" and "differentiated" look like at this exact brief:

- **Team DeTABIS (dhrubojyotihazra/ORCA):** <cite index="32-1">LangGraph multi-agent mesh with a planner (intent + geocoding + language detection), specialist Ocean/Weather/Risk agents, and a synthesizer agent producing zero-hallucination grounded regional answers</cite>; <cite index="32-1">ingests ISRO MOSDAC Oceansat-3 SST/chlorophyll and INCOIS ERDDAP feeds, with Supabase PostGIS for geofencing and conversation state</cite>; polished 3D WebGL globe front-end, Groq-based voice (Whisper ASR) pipeline.
- **Team ICARUS (Anbu-00001/ORCA):** Positions itself as a "reasoning and safety layer" that <cite index="30-1">synthesizes multi-source marine observations, detects safety-vs-opportunity conflicts, and enforces a deterministic safety-override policy in code</cite> rather than trusting an LLM with safety-critical numbers.
- **Kushall-07/ORCA:** Explicit design philosophy — <cite index="29-1">the LLM only interprets and explains the question, while deterministic code computes every risk number and enforces every safety rule; evidence backs every claim and the human makes the final call</cite>; ships a data-provenance legend distinguishing live/reference/derived/demo/missing data, and is transparent that <cite index="29-1">SST/chlorophyll ingestion is not yet implemented, with disabled placeholder toggles rather than fabricated values</cite>.
- **abhimanyu-kotari/Orca:** <cite index="31-1">A dedicated weather agent scoring wind, gusts, wave height, swell, wave period, precipitation and thunderstorms against IMD/INCOIS thresholds to output SAFE/CAUTION/DANGER, cross-checked by an LLM</cite>; <cite index="31-1">a PFZ agent backed by a curated database of 21+ fishing zones spanning every Indian coastal state</cite>.
- **Abhinav1480/sih:** <cite index="24-1">A "strict circuit breaker" that asks for clarification instead of silently defaulting to a fallback city when critical parameters like route endpoints are missing</cite>; <cite index="24-1">a documented LIVE mode (real Copernicus/Open-Meteo/INCOIS feeds) vs DEMO mode (fully deterministic, offline, no API keys) for guaranteed hackathon-day reliability</cite>.
- **ORCA-SIH/ORCA (backend-focused):** <cite index="26-1">Concurrent async querying of weather/ocean/marine agents, auditable timestamped evidence items, WGS84-validated requests, and mock-query endpoints to unblock frontend work independently of backend readiness</cite>.
- **SeaSarathi (Manav-Sonawane):** <cite index="16-1">Sarvam-105B LLM for Hindi/Tamil/English multilingual chat and voice synthesis, deterministic rules engine for SAFE/CAUTION/DO-NOT-VENTURE verdicts, Copernicus Marine Service integration</cite>.
- **SagarMitra-AI:** <cite index="21-1">Environmental covariate regression combining SST and chlorophyll-a anomalies, NASA GIBS Earthdata ingestion (MUR SST, VIIRS chlorophyll) as a failover to INCOIS ERDDAP</cite>.

**Take-away:** the "table stakes" for a competitive ORCA submission now include: LangGraph-style multi-agent orchestration, a deterministic (non-LLM) safety-rules engine, PostGIS/GeoJSON geofencing against MPA/IMBL boundaries, a LIVE/DEMO dual-mode for reliability, multilingual voice, and an evidence/provenance layer. Anything you submit needs to at least match these, and differentiation has to come from *what none of them have done yet* (Section 5).

---

## 3. Which Existing Features We Can Implement

Realistically buildable within a hackathon/early-product timeframe, all backed by free/public data:

| Feature | Source to reuse | Feasibility |
|---|---|---|
| PFZ lookup by location | INCOIS ERDDAP / PFZ bulletins (public) | High |
| SST & chlorophyll overlays | MOSDAC (Oceansat), NASA GIBS (VIIRS/MUR) as failover | High |
| Wind/wave/swell safety scoring | Open-Meteo Marine API, IMD bulletins | High |
| Cyclone/high-wave/lightning alerts | IMD, INCOIS ESSO bulletins (WMO codes as thunderstorm proxy) | Medium — proxy signals only, not certified detection |
| Geofencing vs IMBL / MPA / sanctuary zones | Public GeoJSON boundaries (Marine Protected Areas, IMBL reference lines), PostGIS | High |
| Multilingual conversational interface | LLM + i18n string tables + regional TTS/ASR (Sarvam, Bhashini, Groq Whisper) | High |
| Multi-agent orchestration (planner → specialists → synthesizer) | LangGraph / custom async dispatcher | High |
| Route suggestion around hazards | A*/Dijkstra over a hazard-weighted grid | Medium |
| Deterministic safety engine (LLM never decides risk) | Rule thresholds from IMD/INCOIS safety criteria | High — and should be treated as a hard requirement, not optional |
| Evidence/provenance display per answer | Timestamp + source tag on every data point pulled | High |

---

## 4. Feature Gaps vs Existing Solutions

Comparing the SIH-mandated scope and the researched competitors against a typical baseline build surfaces these gaps:

1. **Offline / low-bandwidth fallback** — SAMUDRA still needs the old SMS channel for a reason: most other prototypes (including several ORCA clones) assume a smartphone with data connectivity. A pure web/app chatbot alone is not accessible to a fisher on a rented feature-phone.
2. **Voice-first / low-literacy UX** — several competitors mention voice as a stretch goal (Groq Whisper) but text is still the primary interface everywhere, including SAMUDRA. Coastal fishing communities have meaningfully lower smartphone-literacy rates than urban users.
3. **Verified real-time hazard feeds vs proxies** — Kushall-07/ORCA is unusually honest that lightning/cyclone signals are WMO-code proxies, not certified detections. This is a gap across almost every prototype we found, including likely across most competing teams — a genuine, well-sourced lightning/cyclone feed (e.g., IMD's Damini lightning alert, national cyclone tracks) would be a real differentiator.
4. **Post-hoc accountability / feedback loop** — none of the researched products let a fisher report "the PFZ was empty" or "the sea was rougher than predicted" and feed that back into future confidence scoring.
5. **Vessel- and crew-specific risk, not generic risk** — safety thresholds in every competitor are generic (wind/wave cutoffs). None adjust for vessel size/type, crew experience, or trip duration — a small catamaran and a 15m trawler do not share the same "safe" wave height.
6. **Community / social layer** — Global fleets use Fishbrain-style crowd reporting; no Indian marine-safety tool currently lets fishers corroborate or dispute conditions from other nearby vessels in near-real time.
7. **Cross-border / EEZ incursion prevention with escalation** — geofencing exists in several prototypes as a passive map overlay, but none couple it with proactive, distance-decaying alerts (e.g. "you are 8 km from the IMBL and closing") or automatic escalation to coast guard/authorities.
8. **Explainability depth** — "evidence" in most prototypes means "we show the raw numbers we used." True explainability (e.g., "wave height alone would be SAFE, but combined with today's swell period this becomes CAUTION because...") is largely absent.
9. **Post-catch / economic feedback loop** — no product studied ties conditions back to actual catch outcomes to improve future PFZ confidence (a genuine agentic-learning opportunity).
10. **Institutional/researcher mode** — every product studied is fisher-facing; the problem statement explicitly also names researchers, coastal authorities, and disaster-management agencies as users, and none of the researched tools have a distinct analytical mode for them (e.g. "why did productivity decline in this region over 6 months").

---

## 5. Innovative / Differentiating Features to Propose

These are features we did **not** find in INCOIS/SAMUDRA, in global apps (Windy, PredictWind, Fishbrain, SeaLegs AI, Global Fishing Watch), or in the other SIH26176 ORCA prototypes surveyed. Each is scoped to be genuinely buildable, not just aspirational.

### 5.1 IVR / Missed-Call & WhatsApp Fallback Channel
- **What it does:** Lets a fisher with no smartphone or data get the same safety verdict and nearest-PFZ answer over a basic phone call or WhatsApp text, in their language.
- **How it works:** A phone number receives a call/SMS/WhatsApp message; a lightweight gateway transcribes speech (or parses keywords), routes it into the same agent pipeline used by the app, and replies via IVR text-to-speech or WhatsApp text.
- **Why useful:** Closes the exact accessibility gap SAMUDRA's legacy SMS channel exists for, but keeps it conversational instead of one-way broadcast.
- **Implementation:** Twilio/Exotel-style telephony API or WhatsApp Business Cloud API in front of the existing planner agent; cache last-known advisory per registered village/port so it still works if the live pipeline is briefly down.
- **Tech/data needed:** Telephony/WhatsApp Business API, existing agent backend, a registered-user/village directory.
- **Status:** New — none of the researched competitors implement this; it directly closes Gap #1.

### 5.2 Vessel- and Crew-Aware Risk Profiles
- **What it does:** Instead of one universal "SAFE/CAUTION/DANGER" threshold, the risk engine adjusts thresholds by vessel class (traditional catamaran, motorised boat, trawler), crew count, and trip duration, which the user sets once during onboarding.
- **How it works:** A small lookup table of safety-threshold multipliers per vessel class feeds into the deterministic risk agent already required by the problem statement.
- **Why useful:** A generic wave-height cutoff either under-warns large trawlers (false confidence) or over-warns small catamarans (advisory fatigue that leads to it being ignored).
- **Implementation:** Extend the existing rules engine with a `vessel_profile` parameter; store the profile against the user's session/account.
- **Tech/data needed:** Just structured config + a user profile table — no new external data source required.
- **Status:** New — no competitor studied personalises risk by vessel.

### 5.3 Confidence-Calibrated Advisories with Ground-Truth Feedback Loop
- **What it does:** After a trip, the app asks a one-tap question ("Was the sea calmer / rougher / as expected? Did you find fish here?") and uses accumulated responses to display a confidence percentage alongside future advisories for that zone/season.
- **How it works:** Store (predicted condition, predicted PFZ, reported outcome) tuples; run a simple Bayesian or frequency-based calibration per grid cell/season rather than a black-box ML retrain, so it stays explainable.
- **Why useful:** Builds trust over time and gives ISRO/INCOIS a validated feedback signal on their own advisories — something the Springer PFZ-validation study noted was a known gap (PFZ advisories don't currently predict catch *quantity*).
- **Implementation:** A lightweight feedback microservice + a scheduled aggregation job that updates a per-cell reliability score consumed by the synthesizer agent.
- **Tech/data needed:** A time-series store (Postgres/TimescaleDB), no new external API.
- **Status:** New concept for this domain — inspired by, but distinct from, Fishbrain's catch-logging (which is social, not calibration-feeding).

### 5.4 Proactive, Distance-Decaying Geofence Escalation
- **What it does:** Rather than a static "you have crossed the boundary" alert, the assistant proactively narrates closing distance to IMBL/MPA boundaries ("12 km... 6 km... 2 km, turn back now") and, past a hard threshold, offers a one-tap alert to a designated shore contact or coast guard channel.
- **How it works:** Continuous (or periodic, connectivity-permitting) position check against the existing GeoJSON boundary layer; a decaying alert cadence as distance shrinks; an opt-in SMS/webhook to a shore contact at the final threshold.
- **Why useful:** Every competitor prototype treats geofencing as a passive map layer; none couple it to an escalating, human-in-the-loop safety action.
- **Implementation:** Extend the existing PostGIS geofence agent with a distance-bucketed alert state machine; integrate with the IVR/WhatsApp channel above for the escalation message.
- **Tech/data needed:** Same GeoJSON boundary data most competitors already use (IMBL, MPA, sanctuary polygons) + a notification channel.
- **Status:** New — extends a feature every competitor already has, but none automate the escalation.

### 5.5 "Why Did Productivity Decline" — Longitudinal Root-Cause Agent
- **What it does:** Directly answers the problem statement's example query by correlating historical SST/chlorophyll anomalies, PFZ advisory frequency, and (where available) catch-landing statistics over a chosen period and region, then narrates the most plausible contributing factors with confidence caveats.
- **How it works:** A dedicated "Analytics/Research" agent (separate from the real-time safety path) that queries a historical data warehouse rather than live feeds, runs simple anomaly-correlation (e.g., SST anomaly vs advisory-issuance trend) and returns a ranked, evidence-linked explanation — explicitly flagged as *analytical hypothesis*, not certainty.
- **Why useful:** This is one of the problem statement's own example queries, and no researched competitor (all of which focus on the safety/PFZ real-time path) actually builds a historical/root-cause reasoning agent.
- **Implementation:** Reuse the existing multi-agent framework; add a data warehouse fed by CMFRI landing statistics (where public) and archived MOSDAC/INCOIS bulletins; keep it strictly evidence-cited to avoid hallucinated causal claims.
- **Tech/data needed:** CMFRI fisheries statistics, historical MOSDAC/INCOIS archives, a time-series store.
- **Status:** New — fills a functional gap that is explicitly in-scope but unimplemented by every prototype surveyed.

### 5.6 Cooperative "Nearby Vessel" Corroboration (Privacy-Preserving)
- **What it does:** Lets users who opt in see an anonymised, aggregated signal like "3 other boats within 15 km reported calmer-than-forecast seas in the last 2 hours," without ever exposing individual vessel identity or exact position.
- **How it works:** Coarse-grained spatial binning (e.g. 10–20 km grid cells) and time-windowed aggregation of opt-in condition reports; only cell-level aggregates are ever shown, never per-vessel data.
- **Why useful:** Global Fishing Watch shows aggregated vessel activity is valuable at scale; Fishbrain shows crowd reports build trust; neither exists for Indian small-craft fishing safety, and doing it privacy-first avoids the surveillance concerns that make raw AIS-style tracking sensitive for small traditional craft.
- **Implementation:** A report-submission endpoint feeding the same grid used for PFZ/advisory display; strict k-anonymity threshold (don't show an aggregate until ≥3 independent reports exist in a cell/window).
- **Tech/data needed:** No new external API — built entirely on user-submitted data plus the existing geospatial grid.
- **Status:** New — a privacy-conscious adaptation of a pattern (crowd corroboration) that exists elsewhere but not in this domain/market.

### 5.7 Institutional / Researcher Analytical Mode
- **What it does:** A second interface mode (same backend, different framing) for coastal authorities, disaster-management agencies and researchers to run broader spatial/temporal queries — e.g. "map all cyclone alerts issued in the last 3 years for this district" or "compare PFZ hit-rate across two seasons" — with exportable charts/reports rather than a single conversational verdict.
- **How it works:** Reuses the planner/analytics agents but skips the "give me one safe/unsafe answer" framing in favour of structured query building and downloadable outputs (CSV/PDF/map export).
- **Why useful:** The problem statement explicitly names researchers and coastal/disaster-management authorities as target users, but every competitor prototype we found builds purely for the individual-fisher use case.
- **Implementation:** A role-based UI toggle; reuse existing agents with a report-generation agent added to the pipeline (chart rendering + PDF export).
- **Tech/data needed:** Same data sources already integrated; add a reporting/export layer.
- **Status:** New — a clear, currently-unaddressed segment of the problem statement's own stated audience.

### 5.8 Edge-Cached "Last-Known-Good" Mode for Mid-Sea Connectivity Loss
- **What it does:** Before departure, the app pre-downloads a compact, offline-usable summary (safety verdict, PFZ locations, geofence boundaries, tide table) for the fisher's planned route/area, so guidance remains available once the boat loses signal at sea.
- **How it works:** A "prepare for departure" action bundles the relevant tiles/GeoJSON/advisory text into local storage sized for low-end devices; the app clearly marks this data as "last synced at [time]" once offline.
- **Why useful:** Real connectivity at sea is patchy to nonexistent for most small craft; competitors' LIVE/DEMO toggle (Abhinav1480/sih) solves *developer* reliability, not *fisher* reliability at sea — this solves the actual field problem.
- **Implementation:** Service-worker/local-storage caching on the client; a clear "stale data" indicator once offline beyond a set time window.
- **Tech/data needed:** No new data source — packaging/caching layer on top of existing APIs.
- **Status:** New for this application, though offline caching itself is a well-known mobile pattern (e.g. Fishbrain/Navionics offline maps) not yet applied to safety-critical Indian marine advisories.

---

## 6. Summary Comparison Table

| Capability | Problem statement mandates it? | INCOIS/SAMUDRA has it? | Global apps have it? | Other SIH26176 prototypes have it? | Recommended for ORCA |
|---|---|---|---|---|---|
| Conversational multilingual NLP | Yes | Partial (multilingual, not conversational) | No (Indian langs) | Yes | Build — table stakes |
| PFZ lookup | Yes | Yes | No | Yes | Build — table stakes |
| Weather/sea-state safety verdict | Yes | Partial (raw forecast only) | Yes (generic) | Yes | Build — table stakes |
| Geofencing (IMBL/MPA) | Yes | No | Partial (GFW, enforcement-focused) | Yes | Build — table stakes |
| Route optimisation | Yes | No | No | Partial | Build — differentiator if done well |
| Deterministic (non-LLM) safety engine | Implied | N/A | N/A | Yes (best teams) | Build — required to be credible |
| Voice / IVR / WhatsApp fallback | Not explicit, but accessibility-implied | Legacy SMS only | No | Rare (voice only) | **New — high-value differentiator** |
| Vessel/crew-aware risk | No | No | No | No | **New — differentiator** |
| Feedback-calibrated confidence | No | No | Partial (catch logs, not calibration) | No | **New — differentiator** |
| Escalating geofence alerts | No | No | No | No | **New — differentiator** |
| Root-cause/historical analytics agent | Yes (explicit example query) | No | No | No | **New — fills mandated gap** |
| Privacy-preserving crowd corroboration | No | No | Yes (social, not privacy-first) | No | **New — differentiator** |
| Researcher/authority analytical mode | Yes (implied by stated users) | No | No | No | **New — fills mandated gap** |
| Offline last-known-good mode | No | Partial (SMS as fallback) | Yes (offline maps) | No | **New — differentiator** |

---

## 7. Suggested Prioritisation

1. **Must-have (parity):** conversational multilingual UI, PFZ + weather fusion, deterministic safety engine, geofencing, evidence/provenance display, LIVE/DEMO dual mode for demo reliability.
2. **High-value differentiators (build if time allows):** vessel/crew-aware risk, escalating geofence alerts, root-cause analytics agent (directly answers a named example query the judges will likely test), offline last-known-good caching.
3. **Stretch/vision (mention in pitch, prototype minimally):** IVR/WhatsApp fallback, feedback-calibrated confidence, privacy-preserving crowd corroboration, researcher/authority mode.

This prioritisation is designed so the core demo matches or exceeds what the other ~10 competing ORCA teams have already published, while the pitch narrative leans on the features in tiers 2–3 that none of them currently have.
