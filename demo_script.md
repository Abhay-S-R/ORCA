# ORCA — 5-Minute Demo Video Script

**Total runtime: 5:00 min**
Format: `[ACTION on screen]` → what to show | **"narration text"**

---

## SEGMENT 0 — Problem Statement (0:00 – 0:30)

`[SCREEN: Show "THE PROBLEM" slide — Smart India Hackathon 2026 / Geekmaxxxers]`

### 30-Second Spoken Pitch (Word-for-Word Narration)
**"India has over 7,500 kilometers of coastline supporting 3.7 million marine fisherfolk and 2.8 million small boat crews. Today, world-class marine data already exists: INCOIS delivers ocean state and wave advisories, IMD forecasts cyclones and lightning, and ISRO tracks vessels. But here is the critical gap: India has the marine data, but the boat still needs the decision. Signals remain scattered across disparate portals, in formats fishermen cannot decipher at sea, with zero vessel-specific context. In Cyclone Ockhi, 365 lives were lost because warnings were generic and uncoordinated. When a small boat heads out, the unanswered question is: *'What should this specific boat do right now?'* That is why we built ORCA."**

### Presenter Slide Talking Points & Key Facts
- **The Core Dilemma:** *"India has the marine data but the boat still needs the decision."*
- **Who Is Affected:**
  - **2.8M Small Boat Crews:** Require timely, vessel-specific safety decisions and dynamic risk awareness to navigate safely.
  - **3.7M Marine Fisherfolk:** Need vernacular safety advisories that remain accessible even when cellular signals die in coastal risk zones.
  - **365 Lives Lost in Cyclone Ockhi (Nov 2017):** A stark reminder of what happens when rapid intensification meets generic, non-vessel-specific warnings.
- **What Exists Today (The Data Silos):**
  - **INCOIS (SAMUDRA / SVAS):** Potential Fishing Zones (PFZ) & ocean-state advisories, boat-specific wave forecasts.
  - **IMD (SACHET / DAMINI):** Weather forecasts, cyclone alerts, lightning tracking.
  - **ISRO (VCSS / NABHMITRA):** Satellite vessel tracking, SOS emergency beacons, boundary alerts.
- **Where Existing Systems Stop:**
  - **Fragmented Signals:** Critical marine parameters are scattered across disconnected departments.
  - **No Vessel-Level Context:** Alerts fail to account for a boat's hull type, engine capacity, draft, route, or departure time.
  - **Manual Human Reconciliation:** A fisherman or coastal officer has to manually cross-check multiple apps under high-stress, time-critical conditions.
  - **The Unresolved Question:** Existing pipelines stop at data delivery, leaving the boat captain asking: *"What should this boat do now?"*
- **The ORCA Solution:** A unified agentic marine decision intelligence platform that turns fragmented cross-source signals into a deterministic GO/NO-GO verdict in 10 regional Indian languages.

---

## SEGMENT 1 — System Foundation: Personas, Home Port, Language & the Agent Brain (0:30 – 1:25)

### 0:30 – 0:40 | Persona Selection

`[SCREEN: Open /onboarding or PersonaSelector; show the 4 persona cards side by side]`

**"ORCA serves four personas — Fisherman, Commercial Navigator, Researcher, and Coastal Authority. Your choice shapes the entire experience: the nav menu, the language of the answer, the depth of data shown, even which map layers load by default."**

`[ACTION: Click "Fisherman"]`

### 0:40 – 0:52 | Language + Home Port (Hindi & Mumbai)

`[SCREEN: Profile settings or onboarding — show Language dropdown selecting "Hindi" (हिन्दी), then Home Port showing "Mumbai"]`

**"A fisherman in Mumbai selects Hindi as his language and registers his home port. Now — here's something important — ORCA is not limited to one state's waters. A fisherman from Maharashtra can safely query sea conditions near Veraval in Gujarat, Ratnagiri, Goa, or Mangalore. ORCA resolves every place along India's coastline to the right INCOIS sector and bathymetric grid. The home port just personalises defaults — it's never a restriction."**

### 0:52 – 1:10 | Agent Pipeline Overview

`[SCREEN: Navigate to /reasoning — show the agent graph / pipeline diagram with node names visible]`

**"Under every question runs a 15-node LangGraph pipeline. Language Ingress detects and translates the question. Planning reads intent and validates place and time against real data — no hallucinated coordinates. Then specialist agents fire in parallel: Weather Intelligence, Geospatial, Ocean Analytics. Risk Assessment computes the GO or NO-GO verdict using deterministic code — never an LLM guess. Reporting writes the answer around the facts. And the Critic checks it for accuracy before anything goes out."**

### 1:10 – 1:25 | Confidence & Determinism callout

`[SCREEN: Zoom into agent strip from a previous answer — show confidence tier badges: HIGH / MEDIUM / LOW-DATA on individual agents]`

**"Every agent carries a confidence score — HIGH, MEDIUM, or LOW-DATA. Agents that decide whether a boat leaves port — Weather, Geospatial, Risk Assessment — never call a language model. The verdict is deterministic. The Sentinel agent runs in the background 24 by 7, watching registered locations and pushing alerts the moment a threshold is crossed, without the user opening the app."**

---

## SEGMENT 2 — Fisherman Persona Demo & Marine Chart (1:25 – 2:40)

### 1:25 – 1:35 | Navigation Menu

`[SCREEN: Show the nav rail with Fisherman persona active — Ask, Map, Zones, Voyage, Watches highlighted]`

**"In Fisherman mode, the interface is streamlined. The navigation shows: Ask, the interactive Marine Chart, Fishing Zones, Voyage planning, and Watches. Zero clutter."**

### 1:35 – 1:50 | Interactive Marine Chart & Map Explorer (15 Seconds)

`[SCREEN: Navigate to /map — show MapLibre GL marine chart with animated particle flow field (winds/currents), GEBCO bathymetry depth contours, active PFZ zones, and maritime boundaries]`

**"Clicking into the Marine Chart reveals ORCA's real-time geospatial canvas powered by MapLibre GL. It visualizes dynamic particle flow fields for live wind and ocean currents, GEBCO bathymetric depth contours, and active INCOIS PFZ fishing sectors. Fishermen and navigators can inspect depth soundings, satellite SST overlays, and hazard boundaries with zero latency — giving complete visual situational awareness before untying from the jetty."**

### 1:50 – 2:10 | Safety Query in Hindi

`[SCREEN: Navigate to /ask; type or use voice input in Hindi: "क्या कल सुबह समुद्र में जाना सुरक्षित है?" (Is it safe to go to sea tomorrow morning?)]`
`[Show agent strip streaming live: pills lighting up — Planning → Weather → Geospatial → Ocean Analytics → Risk Assessment → Reporting → Critic]`

**"He types — or speaks — his question in Hindi: *'क्या कल सुबह समुद्र में जाना सुरक्षित है?'* Watch the agent strip stream live: Planning fires first, validates Mumbai as his position, then Weather Intelligence, Geospatial, and Ocean Analytics run in parallel. Risk Assessment computes the verdict. Reporting synthesizes the answer in Hindi. And Critic verifies it."**

`[Answer arrives: large GO or CAUTION banner in Hindi, with wave height, wind speed, distance from hazards/shipping corridors, tide state shown as readouts]`

**"The verdict: bold, unmistakable, in Hindi. Wave height compared against his boat's exact safety envelope. Wind speed, tide state, and distance to restricted zones — all citing INCOIS, Open-Meteo, and GEBCO with acquisition timestamps."**

### 2:10 – 2:20 | Voice Playback + Source Chips

`[ACTION: Tap the speaker icon on the Hindi answer — play Bhashini TTS Hindi audio]`
`[Show source chips below the answer — INCOIS, Open-Meteo, GEBCO]`

**"He can have the advisory read aloud in Hindi using Bhashini text-to-speech. Every fact links directly to its authoritative source — INCOIS for waves, Open-Meteo for wind, GEBCO for bathymetry. Nothing is hallucinated."**

### 2:20 – 2:32 | Distress Demo

`[SCREEN: Trigger distress in /ask or Navigate to /demo Scenario 5: enter Hindi SOS phrase "हमारी नाव डूब रही है" (Our boat is sinking)]`
`[Distress card appears instantly with Mumbai Port Control & Coast Guard MRCC 1554 details]`

**"Now — a life-critical safety override. If a fisherman types a Hindi SOS like *'हमारी नाव डूब रही है'*, ORCA's deterministic keyword gate intercepts it before any LLM sees it. It immediately locks coordinates and surfaces the local Mumbai Port Control and Coast Guard MRCC helpline (1554 / 022-22612348) with VHF Channel 16 protocols. The model can only escalate — it can never dismiss a distress signal."**

### 2:32 – 2:40 | Zones + Watches Quick Flash

`[SCREEN: Flash to /zones — show PFZ sector list with ranked zones and profit estimates]`
`[Then flash to /watches — show "Watch my home port" button locked to Mumbai]`

**"The Fishing Zones page ranks every sector with PFZ status and calculates estimated catch profit after fuel costs. On Watches, one tap subscribes to Sentinel alerts for his home port Mumbai — monitoring hazards round-the-clock."**

---

## SEGMENT 3 — Commercial Navigator + Researcher (2:40 – 3:55)

### 2:40 – 2:48 | Switch persona to Commercial Navigator

`[SCREEN: PersonaSelector — click "Commercial Navigator"; nav rail updates: Voyage is now the primary landing page]`

**"Switch to Commercial Navigator — the default landing page is now the Voyage Planner."**

### 2:48 – 3:08 | Voyage Planning

`[SCREEN: /voyage — select origin port "Thoothukudi", destination port "Rameswaram", vessel class "Mechanized Trawler", set departure time; click Plan Voyage]`
`[Route polyline appears on map — segments colour-coded CLEAR / CAUTION / BLOCKED]`

**"The navigator picks origin, destination and vessel. ORCA walks the hazard cascade along every leg at its own ETA — wave height, wind, bathymetry clearance — geofencing constraints on the IMBL and the Marine Protected Area are baked in. Blocked legs are rerouted with alternatives shown and the extra nautical miles disclosed."**

### 3:08 – 3:22 | IMBL Crossing Demo (demo page stepper)

`[SCREEN: Navigate to /demo — scroll to Scenario 2 "IMBL Border Crossing, Palk Bay"; play the stepper]`
`[Stepper advances: 12 nm → advisory badge; 6 nm → regional voice alert plays; 3 nm → CAUTION + SMS render; 1 nm → NO-GO full-screen takeover]`

**"This is our geofence demo. A vessel track is stepped through the production geofence in real-time. At 12 nautical miles — advisory. At 6 — a voice alert fires. At 3 — CAUTION with SMS broadcast rendered. At 1 nautical mile from the international boundary — full-screen NO-GO takeover with a reciprocal heading instruction. All computed live, not scripted."**

### 3:22 – 3:34 | Switch to Researcher persona

`[SCREEN: PersonaSelector — click "Researcher"; nav rail shows Data page and Reasoning as primary]`

**"Researcher persona. The answer card now shows a full statistical summary — sensor metadata, measurement ranges, and a CSV export button. Let's ask a relevant question."**

### 3:34 – 3:55 | Researcher query & Reasoning Trace

`[SCREEN: /ask — type: "Which regions show high chlorophyll and favourable SST for fishing this season?"]`
`[Answer arrives with expanded statistical breakdown — SST value, chlorophyll reading, sector productivity diagnosis]`

`[SCREEN: Flash to /reasoning — show expanded agent trace with each agent's dataset, value, confidence and latency]`

**"The answer includes SST and chlorophyll readings with full provenance. Flip to the Reasoning page — every agent's exact dataset, confidence tier and latency is there for audit. This is the trace that gets stored and is always available after the query."**

---

## SEGMENT 4 — Coastal Authority Demo (3:55 – 5:00)

### 3:55 – 4:05 | Switch to Coastal Authority; show /ops

`[SCREEN: PersonaSelector — click "Coastal Authority"; auto-routes to /ops]`
`[Show the full /ops page: Sector Threat Matrix at the bottom — 14 sectors with GO/CAUTION/NO-GO column and vessel counts]`

**"Coastal Authority lands on the District Operations centre. The sector threat matrix shows all 14 INCOIS sectors — PFZ status, vessel count, alert severity — aggregated. Individual vessel positions are never shown; only counts, by design."**

### 4:05 – 4:17 | Distress Queue

`[SCREEN: Scroll up on /ops to show the Distress Queue panel — show a distress event row with SOS phrase, timestamp, MRCC payload]`

**"The Distress Queue shows every SOS raised in the district — the exact phrase, when it was detected, which MRCC was surfaced. Operators can act directly from here."**

### 4:17 – 4:33 | CAP 1.2 Builder + Broadcast

`[SCREEN: CAP 1.2 Alert Builder panel — fill: Verdict = NO-GO, Hazard = "High waves 4.5 m", Location = "Mumbai Offshore"; click Build CAP alert]`
`[Generated CAP 1.2 XML appears in the panel]`

**"The CAP 1.2 builder generates a valid OASIS-standard XML alert — the exact format used by NDMA, SACHET and IMD — with one click. Now the authority composes a broadcast."**

`[SCREEN: Scroll to Broadcast Composer — set severity to Danger, target audience to Fishermen, channels: In-App + SMS + VHF, click Preview then Publish]`

**"The broadcast goes to all fishermen in the sector. In-app notification — live. SMS formatted to 160 GSM characters. VHF Channel 16 script. IVR voice advisory. All previewed before sending."**

### 4:33 – 4:48 | Alert received in Fisherman's notification

`[SCREEN: Switch to a second browser tab or phone screen — show the fisherman's /alerts page or notification bell with the new alert appearing]`
`[Alert row shows: NO-GO, High waves 4.5 m, triggered by Coastal Authority, with per-channel detail expanded]`

**"The fisherman immediately receives the alert in-app — severity ranked, with the exact SMS text, IVR script and what was sent on each channel. The Sentinel loop and the authority broadcast are two paths to the same fisherman's safety."**

### 4:48 – 5:00 | Closing shot

`[SCREEN: Pull back to the ORCA home / landing page or the ask page with a GO verdict glowing]`

**"ORCA: one platform for India's entire marine safety stack. Deterministic verdicts. Evidence-cited answers. Ten Indian languages. Real-time agent intelligence — for the fisherman who just wants to know if it's safe, and the authority who needs to act when it isn't."**

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
