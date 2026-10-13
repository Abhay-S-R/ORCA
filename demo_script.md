# ORCA — 5-Minute Demo Video Script

**Total runtime: 5:00 min**
Format: `[ACTION on screen]` → what to show | **"narration text"**

---

## SEGMENT 0 — Problem Statement (0:00 – 0:30)

`[SCREEN: Show "THE PROBLEM" slide — Smart India Hackathon 2026 / Geekmaxxxers]`

### 30-Second Spoken Pitch (Word-for-Word Narration)
**"India has 7,500 kilometers of coastline, 3.7 million fisherfolk, and 2.8 million small boat crews. World-class data already exists from INCOIS, IMD, and ISRO. But this is where existing systems stop: *India has the marine data, but the boat still needs the decision.*"**

**"Signals are fragmented across separate portals, with zero vessel-level context, forcing dangerous manual guesswork. In Cyclone Ockhi, 365 lives were lost to generic warnings. Small boats are left asking: *'What should my boat do right now?'* That is why we built ORCA."**

> *Pacing Note:* Natural, conversational pace. ~77 words (~28–30 seconds).

### Presenter Slide Talking Points & Key Facts
- **The Core Headline:** *"India has the marine data but the boat still needs the decision"* (Cross-source, vessel-level reasoning remains fragmented).
- **WHERE EXISTING SYSTEMS STOP (Key Slide Focus):**
  - **1. Fragmented Signals:** Critical marine data is siloed across separate government systems (INCOIS, IMD, ISRO).
  - **2. No Vessel-Level Context:** Broadcast alerts ignore a boat's hull type, draft, engine capacity, route, and timing.
  - **3. No Cross-Source Answer:** Different sources never reconcile into one contextual decision.
  - **4. Dangerous Manual Reconciliation:** Skippers are forced into high-stress guesswork while at sea.
- **The Stakes & Victims:**
  - **2.8M Small Boat Crews:** Need timely, vessel-specific safety decisions.
  - **3.7M Marine Fisherfolk:** Need vernacular safety advisories in weak-signal risk zones.
  - **365 Lives Lost in Cyclone Ockhi (Nov 2017):** Non-vessel-specific warnings cost lives during rapid storm intensification.
- **The Unresolved Question:** *"What should this boat do now?"*
- **The ORCA Solution:** Reconciles all signals with vessel physics and bathymetry in under 2 seconds, delivering a deterministic GO/NO-GO verdict in 10 Indian languages.

---

## SEGMENT 1 — System Foundation: Personas, Home Port, Language & the Agent Brain (0:30 – 1:25)

### 0:30 – 0:40 | Persona Selection (10s)

`[SCREEN: Open /onboarding or PersonaSelector; show the 4 persona cards side by side]`

**"ORCA serves four personas — Fisherman, Navigator, Researcher, and Coastal Authority. Your choice tailors the interface, language, data depth, and default map layers."**

`[ACTION: Click "Fisherman"]`

### 0:40 – 0:52 | Language + Home Port (12s)

`[SCREEN: Profile settings or onboarding — select "Hindi" (हिन्दी), then Home Port "Mumbai"]`

**"A fisherman in Mumbai selects Hindi and sets his home port. ORCA isn't restricted to Maharashtra — he can query anywhere along India's coastline. The home port simply personalises defaults."**

### 0:52 – 1:10 | Agent Pipeline Overview (18s)

`[SCREEN: Navigate to /reasoning — show 15-node LangGraph pipeline diagram]`

**"Under every query runs a 15-node LangGraph pipeline. Planning validates coordinates, then Weather, Geospatial, and Ocean agents run in parallel. Risk Assessment computes a deterministic verdict, Reporting drafts the answer, and Critic verifies accuracy."**

### 1:10 – 1:25 | Confidence & Determinism Callout (15s)

`[SCREEN: Zoom into agent strip — show confidence badges: HIGH / MEDIUM / LOW-DATA]`

**"Every agent displays a confidence tier: HIGH, MEDIUM, or LOW-DATA. Safety-critical agents never call an LLM — the verdict is purely deterministic. Meanwhile, Sentinel monitors watch zones 24/7 in the background."**

---

## SEGMENT 2 — Fisherman Persona Demo & Marine Chart (1:25 – 2:40)

### 1:25 – 1:35 | Navigation Menu (10s)

`[SCREEN: Show nav rail in Fisherman mode: Ask, Map, Zones, Voyage, Watches]`

**"In Fisherman mode, navigation is distraction-free: Ask, Marine Chart, Fishing Zones, Voyage planning, and Watches."**

### 1:35 – 1:50 | Interactive Marine Chart & Map Explorer (15s)

`[SCREEN: Navigate to /map — show MapLibre GL chart: particle flow field (winds/currents), GEBCO depth contours, PFZ markers, boundary lines]`

**"The Marine Chart is our real-time MapLibre canvas. It visualizes live wind and current flow fields, GEBCO depth contours, and INCOIS fishing zones — giving skippers instant spatial awareness before leaving the jetty."**

### 1:50 – 2:10 | Safety Query in Hindi (20s)

`[SCREEN: /ask — type or speak in Hindi: "क्या कल सुबह समुद्र में जाना सुरक्षित है?"]`
`[Show agent strip streaming: Planning → Weather → Geospatial → Ocean Analytics → Risk Assessment → Reporting → Critic]`

**"He asks in Hindi: *'क्या कल सुबह समुद्र में जाना सुरक्षित है?'* Watch the agents stream live — validating Mumbai, fetching weather, and computing risk."**

`[Answer arrives: large GO/CAUTION banner in Hindi, wave height, wind speed, hazard distance readouts]`

**"The verdict is immediate and clear in Hindi. Wave height, wind, and boundary distance are evaluated against his boat's limits, citing INCOIS and GEBCO with timestamps."**

### 2:10 – 2:20 | Voice Playback + Source Chips (10s)

`[ACTION: Tap speaker icon for Bhashini Hindi TTS audio; highlight INCOIS/Open-Meteo/GEBCO chips]`

**"He can listen via Bhashini Hindi text-to-speech. Every data point cites its authoritative source — zero hallucination."**

### 2:20 – 2:32 | Distress Demo (12s)

`[SCREEN: In /ask or /demo Scenario 5: enter Hindi SOS "हमारी नाव डूब रही है" (Our boat is sinking)]`
`[Distress card appears with Mumbai Port Control & Coast Guard MRCC 1554]`

**"If a fisherman sends an SOS like *'हमारी नाव डूब रही है'*, deterministic pattern-matching intercepts it instantly — surfacing Mumbai Port Control and Coast Guard MRCC (1554). The system can only escalate distress, never dismiss it."**

### 2:32 – 2:40 | Zones + Watches Quick Flash (8s)

`[SCREEN: Flash to /zones (PFZ list + profit) → flash to /watches ("Watch my home port" Mumbai)]`

**"Fishing Zones rank profitable catches after fuel costs, while Watches lets him monitor Mumbai's waters with one tap."**

---

## SEGMENT 3 — Commercial Navigator + Researcher (2:40 – 3:55)

### 2:40 – 2:48 | Switch to Commercial Navigator (8s)

`[SCREEN: PersonaSelector — click "Commercial Navigator"; auto-lands on /voyage]`

**"Switching to Commercial Navigator — the interface automatically shifts to the Voyage Planner."**

### 2:48 – 3:08 | Voyage Planning (20s)

`[SCREEN: /voyage — select origin port "Thoothukudi", destination "Rameswaram", vessel "Mechanized Trawler"; click Plan Voyage]`
`[Route polyline shows segments: CLEAR / CAUTION / BLOCKED]`

**"The navigator selects ports and vessel type. ORCA checks weather and depth clearances along every leg at its calculated ETA. Shallow zones and protected areas are automatically skirted, showing clear alternative routes with extra nautical miles disclosed."**

### 3:08 – 3:22 | IMBL Crossing Demo (14s)

`[SCREEN: /demo Scenario 2 "IMBL Border Crossing"; run stepper: 12nm → 6nm → 3nm → 1nm]`

**"Here, a vessel approaches the international border. At 12 miles — advisory. At 6 — voice warning. At 3 — caution SMS. And at 1 mile — a full-screen NO-GO takeover with a reciprocal escape heading."**

### 3:22 – 3:34 | Switch to Researcher Persona (12s)

`[SCREEN: PersonaSelector — click "Researcher"; nav shows Data & Reasoning]`

**"In Researcher mode, answers include full statistical ranges and CSV export. Let's query seasonal ocean productivity."**

### 3:34 – 3:55 | Researcher Query & Reasoning Trace (21s)

`[SCREEN: /ask — type chlorophyll/SST query → answer with statistical breakdown]`
`[Flash to /reasoning — show trace table: agent, dataset, confidence, latency]`

**"The response breaks down Sea Surface Temperature and chlorophyll. On the Reasoning page, auditors can inspect each agent's underlying dataset, latency, and confidence score with complete transparency."**

---

## SEGMENT 4 — Coastal Authority Demo (3:55 – 5:00)

### 3:55 – 4:05 | District Operations (/ops) (10s)

`[SCREEN: PersonaSelector — click "Coastal Authority"; loads /ops]`
`[Show Sector Threat Matrix with 14 INCOIS sectors & vessel counts]`

**"Coastal Authority opens District Operations. The Threat Matrix aggregates all 14 sectors, displaying active risk levels and fleet density without exposing private vessel coordinates."**

### 4:05 – 4:17 | Distress Queue (12s)

`[SCREEN: Scroll to Distress Queue panel on /ops — show active SOS incident row]`

**"The Distress Queue logs active SOS signals across the district, allowing operators to coordinate rescue handoffs instantly."**

### 4:17 – 4:33 | CAP 1.2 Builder & Multi-Channel Broadcast (16s)

`[SCREEN: Generate CAP 1.2 XML alert → Scroll to Broadcast Composer → click Publish]`

**"One click generates a standard CAP 1.2 XML alert for NDMA and IMD. The authority can then publish multi-channel broadcasts across SMS, IVR voice calls, in-app push, and VHF Channel 16 scripts simultaneously."**

### 4:33 – 4:48 | Alert Received in Fisherman View (15s)

`[SCREEN: Switch to fisherman tab /alerts — new alert arrives live]`

**"The fisherman immediately receives the alert in-app with multi-channel details. Autonomous Sentinel monitoring and authority broadcasts unite to protect the boat."**

### 4:48 – 5:00 | Closing Shot (12s)

`[SCREEN: Pull back to ORCA home / landing page with glowing GO verdict]`

**"ORCA unifies India's marine safety: deterministic verdicts, ten regional languages, and real-time agent intelligence. One answer for the fisherman, one console for the authority."**

`[Fade out]`

---

## Screen Action Cheat Sheet (in order)

| Time | Screen | Key action |
|---|---|---|
| 0:00 | Presentation Slide | Present Problem Statement (2.8M boat crews, 3.7M fisherfolk, Ockhi tragedy, INCOIS/IMD/ISRO data gap) |
| 0:30 | `/onboarding` or PersonaSelector | Click Fisherman → Language: Hindi (हिन्दी) → Home Port: Mumbai |
| 0:52 | `/reasoning` | Show agent graph / 15-node pipeline |
| 1:10 | Any prior answer's agent strip | Zoom on confidence tier badges (Deterministic vs LLM) |
| 1:25 | `/ask` (Fisherman, Hindi) | Show simplified nav rail |
| 1:35 | `/map` | **Show interactive Marine Chart:** animated particle flow field, GEBCO bathymetry, PFZ markers, boundary lines |
| 1:50 | `/ask` | Type Hindi safety question (*"क्या कल सुबह समुद्र में जाना सुरक्षित है?"*) → stream answer |
| 2:10 | Answer card | Tap TTS speaker (Hindi voice); show source chips (INCOIS, Open-Meteo, GEBCO) |
| 2:20 | `/ask` or `/demo` | Trigger Distress at sea (Hindi SOS: *"हमारी नाव डूब रही है"* → MRCC Mumbai & Port Control) |
| 2:32 | `/zones` & `/watches` | Flash PFZ list + Watch Mumbai home port |
| 2:40 | PersonaSelector | Switch → Commercial Navigator |
| 2:48 | `/voyage` | Plan route (origin, destination, vessel, hazard clearance) |
| 3:08 | `/demo` | Run Scenario 2 — IMBL Crossing stepper (12nm → 6nm → 3nm → 1nm NO-GO takeover) |
| 3:22 | PersonaSelector | Switch → Researcher |
| 3:34 | `/ask` & `/reasoning` | Type chlorophyll/SST question → show expanded audit trace with latency & datasets |
| 3:55 | PersonaSelector | Switch → Coastal Authority → `/ops` |
| 4:05 | `/ops` | Show Distress Queue panel |
| 4:17 | `/ops` | Build CAP 1.2 XML alert → Broadcast Composer → Preview & Publish |
| 4:33 | Second tab / `/alerts` | Show broadcast alert received live in fisherman's view |
| 4:48 | `/ask` or landing | Closing GO verdict shot |

---

## Tips for Recording

- **Problem Slide**: Start on the presentation slide for the first 30 seconds, speaking with authority using the exact points from the Geekmaxxxers SIH 2026 slide.
- **Phone mockup for fisherman segment**: Record the fisherman part on mobile viewport (375px) — it shows the bottom tab bar, which looks great for mobile-first storytelling.
- **Desktop for navigator + authority**: Wide viewport, split screen if possible (voyage map on left, leg table on right).
- **Pre-load pages**: Have all tabs pre-opened and logged in before recording — `/` (or slide), `/map`, `/ask` (fisherman Hindi, Mumbai), `/demo`, `/voyage`, `/ops`, `/alerts`.
- **Pre-fill the Hindi text**: Copy-paste the Hindi question (`क्या कल सुबह समुद्र में जाना सुरक्षित है?`) and distress phrase (`हमारी नाव डूब रही है`) so you don't fumble while typing live.
- **Marine Chart showcase**: On `/map`, have the particle flow field and bathymetry layer visible to make the visual pop during those 15 seconds.
- **The CAP XML**: Build it before recording so the XML is already visible when you reach that segment.
- **The agent strip timing**: The live stream takes 3–6 seconds — start the question, let it run, narrate over the streaming animation.
