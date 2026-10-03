# ORCA — SIH 2026 Grand Finale Judge Audit
**PS 26176 · Team Geekmaxxers · Theme: Disaster Management**
**Evidence base:** 8-slide PPT (every slide rendered at high resolution and read), the full `Abhay-S-R/ORCA` GitHub repo cloned and inspected file-by-file, `graph.py`/`risk_assessment.py`/`distress.py`/`voice.py`/`llm/*` read in full, 103 of the repo's own unit tests executed live in a sandbox, and the 5 product screenshots embedded in the repo's own README (`assets/orca1-5.png`).

> **One thing you should know before reading this:** your repo already contains `docs/competition/ORCA_SIH2026_Evaluation.md` — a 428-line audit that does almost exactly this exercise, in the same voice, against an earlier state of this same deck and repo. I read it in full and treated it as a source to verify, not as ground truth. Where I could independently confirm its findings against the current code, I did. Where the repo has moved on since it was written, I flag that explicitly below — because it has, in both directions: some of its P1/P2 fixes are done, and its single most important recommendation (fix the deck) is not.

---

## 1. Executive Verdict

**Your codebase is finalist-calibre. Your deck is not, and the gap between the two is the single biggest thing standing between you and a strong result.**

The GitHub repo is genuinely unusual for a hackathon submission: a real LangGraph `StateGraph` with conditional routing and true fan-out/fan-in, a deterministic safety core that is provably zero-LLM (I read the thresholds, I ran the tests), NaN-safe failure handling that names a specific bug class ("a GO-shaped number conjured from absent data") and closes it, a CI pipeline that architecturally enforces its own design rules (no agent file may import an LLM SDK directly; persona may never leak into a specialist agent), and code comments that voluntarily disclose what's fake, pending, or simulated before a judge would have to go find it. That last trait is rare and valuable, and right now you're burying it instead of using it.

The PPT does not carry any of that across. Slide 2 has text that is visibly cut off at the bottom of both columns. Slide 5 — your technical architecture slide, the one a technical panel stares at longest — has garbled, duplicated text in multiple places, including inside the "Ground Rules" box itself ("Intent intent - persona persona data," "Every clerm provence provenance"). Your own product has a genuinely striking live map and reasoning-trace UI (verified via your README's own screenshots) that appears **nowhere** in your 8 slides. And your PPT says "12-Agent Tiered System" while your own live product says "10" in three separate places.

None of this is fatal, and almost none of it requires new engineering — it requires fixing a deck you already have the material to fix.

**Current level: finalist-level codebase, internal-round-level deck.**

---

## 2. Deep PS Breakdown

**A. Explicit requirements (verbatim from the PS text):**
- Understand natural-language user intent
- Auto-detect query language, respond in the same language, with emphasis on Indian regional languages
- Support contextual, multi-turn conversation
- Autonomously discover, retrieve, and integrate satellite/marine/meteorological/geospatial datasets
- Perform spatial, temporal, and contextual reasoning correlating multiple heterogeneous sources
- Generate explainable, evidence-based recommendations with maps/charts/visualizations
- Proactive hazard alerts (weather, high waves, lightning, cyclones)
- Geofencing notifications (international maritime boundaries, restricted waters, MPAs, sensitive zones)
- Route optimization, safe navigation, operational planning
- Every recommendation delivered with supporting evidence and reasoning
- A modular multi-agent architecture — planning, marine data discovery, weather intelligence, ocean analytics, geospatial reasoning, risk assessment, visualization, reporting, user interaction — demonstrating **autonomous collaboration**, not just a function list

**B. Implicit requirements (what a finalist is expected to show even though the PS doesn't spell it out):**
- Genuine agent autonomy/orchestration, not a router function wearing a multi-agent label
- A live, working demo — not a Figma mock or a screenshot deck
- Named, checkable data sources, not "we use satellite data"
- A defensible answer for what happens when data is missing, stale, or contradictory — this PS is explicitly safety-critical, and judges will probe failure paths, not just happy paths
- A credible deployment/adoption story, since this is an ISRO/INCOIS/NDMA-adjacent government-relevant PS
- Honesty about what's shipped vs. roadmap — a government-facing safety pitch that overclaims is a bigger liability than one that under-claims

**C. Evaluation dimensions this PS specifically invites (beyond the generic SIH list):** problem understanding, agentic authenticity (this PS names Agentic AI explicitly — expect it to be tested hardest), multi-agent collaboration vs. multi-function, EO/oceanographic data integration depth, spatial-temporal multi-source correlation vs. lookup, explainability/provenance, multilingual depth vs. translation, geofencing correctness, route-optimization genuineness, safety reliability under missing/bad data, demo quality, and differentiation from "a weather app plus a chatbot."

| Requirement | Tier |
|---|---|
| Agentic multi-agent architecture with autonomous collaboration | **Core judging requirement** |
| Explainable, evidence-cited recommendations | **Core judging requirement** |
| Safety-critical reliability (hazard alerts, geofencing) | **Core judging requirement** |
| Multilingual, Indian regional language support | **Core judging requirement** |
| Spatial-temporal multi-source correlation (not lookup) | **Core judging requirement** |
| Route optimization | Strongly expected |
| Voice interface | Strongly expected (PS says "conversational," doesn't mandate voice specifically) |
| Offline resilience | Nice to have — your own addition, not in the PS text |
| Deployment/scalability story | Strongly expected for a government-agency PS |
| Pan-India coverage at prototype stage | Nice to have — PS doesn't require national scale from a hackathon build |

---

## 3. SIH Judging Patterns & Why Teams Lose

I could not find a published scorecard specific to PS 26176 — this is a new 2026 PS and SIH doesn't release granular judge rubrics. What current, dated research does support:

- SIH 2026 launched officially on 21 August 2026 with 233 problem statements across 17 themes this cycle, a heavier tilt toward AI/applied-automation statements than prior years, and more statements originating from state governments and PSUs rather than only central ministries.
- Current guidance for this cycle is explicit that judges expect real AI integration (LLMs, computer vision, prediction) by default in 2026, and that hardcoded demos get caught — the advice repeated across multiple current SIH-prep sources is to build something that responds to arbitrary input live, not a scripted path.
- The internal-round-to-Grand-Finale funnel is explicitly a two-tier bar: internal/national screening evaluates problem understanding, innovation, feasibility, and completeness of submission, where incomplete documentation alone can eliminate a strong idea before a judge even reaches your prototype. The Grand Finale is a 36-hour build-and-defend format at a nodal centre in front of expert judges, and current guidance stresses that judges consistently favour a stable, working prototype over an ambitious build with incomplete functionality.
- Evaluation is explicitly framed as being about thought process, not just the final artifact — which is a point in your favour, because your code comments *are* documented thought process (the NaN-safety rationale, the IMBL-proxy disclosure, the persona-leak CI guard), and none of it currently reaches the deck.

**Patterns that sink strong-looking teams, synthesized from current SIH guidance plus first-principles of what a technical panel probes on an agentic-AI PS:**
1. A claim that doesn't survive one follow-up question ("is that live right now, or does it fall back?").
2. A PPT that oversells relative to the repo — increasingly, judges click through to GitHub live during Q&A.
3. Demo failure on the one query path the team didn't rehearse.
4. Feature sprawl with no clear "who decides go/no-go, and how" story.
5. Winning teams tend to have one clean, memorable "wow" moment a judge can repeat to the next panel member on the way to the next table — not a feature list.

A note on the broader technical field, since this PS explicitly tests "agentic AI": current 2025–2026 industry consensus (Anthropic, OpenAI, Cognition, LangChain) has converged on an orchestrator-plus-isolated-subagents pattern for open-ended tasks, but a January 2026 controlled study on incident-response agents (Drammeh et al.) found that for **narrow domains with genuinely parallel sub-tasks**, an orchestrator pattern with fixed task decomposition wins decisively over single-agent or freeform peer-collaboration designs — which is exactly ORCA's shape (compiled graph, three genuinely parallel specialist branches, no agent talking to another agent directly). Your architecture is not a novelty; it's the field's current reference pattern for this exact problem shape, executed with more rigor than most student teams manage. That's worth saying on stage in those terms if a technically literate judge is on the panel.

---

## 4. PS Requirement Compliance Matrix

Graded from PPT + GitHub evidence only. "Implemented" required real code I could point to, not a slide bullet.

| PS Requirement | Expected Level | Status | Evidence (PPT) | Evidence (GitHub) | Gap | Priority |
|---|---|---|---|---|---|---|
| NL intent understanding | Core | 🟡 Partial | "Intent-Driven Routing" | `planning.py` — real intent-routing table, LLM-classified | Table/classification-driven, not free-form reasoning. Defensible for a safety product, but "understanding" reads closer to classification | P2 |
| Language auto-detect + respond in-kind | Core | 🟡 Partial | "Voice-First, Multilingual… Bhashini" | `language.py` (IndicTrans2, local, real); `voice.py` gates Bhashini behind 3 env vars and its own HTTP call is **not wired up yet even if credentials were present** | The PPT presents Bhashini as part of one working stack. It isn't connected, and the code says so; the PPT doesn't | **P0** |
| Multi-turn context | Strongly expected | ⚪ Unverified | Not shown | No dedicated conversation-memory module visible in the file tree | Cannot confirm from static evidence either way | P1 |
| Autonomous multi-source dataset discovery/integration | Core | ✅ Verified | "One Unified Data Core" | 25+ named sources in `docs/data/ORCA_Dataset_Master_List.md` with live URLs; real fallback cascades in `ocean_analytics.py` | Genuine | — |
| Spatial-temporal multi-source correlation | Core | ✅ Verified | Agent workflow diagram | `risk_assessment.evaluate_marine_safety` combines wave height + wind + lightning + cyclone alert + IMBL distance + MPA status + vessel class in one threshold cascade | Real, not a lookup | — |
| Explainable, evidence-cited output | Core | ✅ Verified | "Provenance-backed" | `SourceProvenance`/`Confidence` dataclasses wired through every agent into the final citation list | Genuinely well built | — |
| Hazard alerts (weather/wave/lightning/cyclone) | Core | ✅ Verified | Feasibility slide | `evaluate_marine_safety` — real thresholds, NaN-safe, tested (I ran this test file myself: 103/103 passed in the safety-core suite) | Genuine | — |
| Geofencing (IMBL/MPA/restricted) | Core | ✅ Verified | "Persona-Aware" slide | `geospatial.py` — real VLIZ EEZ + WDPA boundary checks; IMBL modelled as an honestly-disclosed Sri Lanka EEZ proxy with confidence capped accordingly | Genuine, with a documented caveat | — |
| Route optimization | Strongly expected | 🟡 Partial | **Not on any slide** — only in README | `/api/voyage-plan`, `voyage.py` exists, described as bathymetry-aware with geofence constraints | Your single largest evidence gap against an explicit PS ask — zero PPT visibility, and I could not verify optimization depth vs. heuristic from static code | **P1** |
| Proactive background monitoring | Strongly expected | ✅ Verified | Not on PPT | `sentinel.py` + `sentinel_runtime.py`, 120s poll loop, Postgres advisory lock so only one instance ever fires an alert | Genuine, and under-sold — this isn't on any slide | — |
| SOS/distress handling | Core (safety) | 🟡 Partial | "Gate — Distress short-circuit" | Detection is real pattern-matching; the DAT-SG/Sagarmitra handoff is explicitly commented `SIMULATED` in code | PPT slide 4 presents this as a functioning handoff | **P0** |
| Multilingual distress detection | Core (safety) | 🟡 Weak, improving | Not disclosed on any slide | 5 languages now (en/ta/hi/ml/te — up from 3 as of the repo's own prior audit), each dictionary-checked but self-labelled "a verified STARTER set, not a validated one," no native-speaker review | Your safety-critical language surface is thinner than your translation surface | **P0** |
| Deployment feasibility | Strongly expected | ✅ Verified | "Simple deploy path" | Docker Compose + Vercel + managed PostGIS is realistic and modest | Genuine | — |

---

## 5. Slide-by-Slide PPT Audit

| # | Title | Verdict |
|---|---|---|
| 1 | Title | Clean. **Team ID field is blank** — fill this in before submission; it reads as an unfinished form. |
| 2 | The Problem | **Broken.** I rendered this slide at full resolution: text visibly overflows its rounded-rectangle bounding boxes and is cut off at the slide's bottom edge in both the "Who Is Affected" and "Why Existing Systems Fail" columns. This is your first content slide — it sets the credibility tone for the other seven. Fix: shorten each bullet by ~15% or drop the font size one step. |
| 3 | Proposed Solution | Clean, good hierarchy, five icon-cards read well at a glance, two clearly-labelled sub-sections. **Best slide in the deck.** |
| 4 | Technical Approach — Agent Workflow | Dense but legible, and it genuinely reflects the real `graph.py` — this is a rare case of a technical slide that isn't inflating anything. One real overstatement: "Agents 3–6 — Parallel fan-out" implies four parallel nodes; the actual graph fans out three (`weather_intelligence`, `geospatial`, `ocean_analytics`) — Agent 3 (Discovery) is a narrative field folded into Ocean Analytics' output, not an independent node, per your own README's own explicit disclosure. |
| 5 | Technical Approach — Layered Architecture | **The most damaging slide in the submission.** At full resolution the "Ground Rules" box itself reads "1. Intent intent - persona persona data" and "3. Every clerm provence provenance," and multiple labels are garbled or duplicated elsewhere on the slide ("Geospolial," "Sontinel," "net node," "cadence-eware," "andr_acde_log"). This is the slide a technical panel scrutinizes hardest, on the one PS that explicitly tests architectural rigor. It currently reads like unproofread placeholder text. |
| 6 | Feasibility & Viability | Clean, and unusually honest for a pitch deck: "9/12 modules coded," "20/25 datasets," "Bhashini voice API access still pending" are disclosed here. Good instinct, badly placed — this honesty should be spoken out loud early in the pitch, not left for judges to notice on a slide they skim quickly. |
| 7 | Impact and Benefits | Clean. The real pilot scope ("South Tamil Nadu") only appears in the roadmap line at the bottom — state it up front instead of leaving it for an attentive reader to infer. |
| 8 | Research and References | Clean, credible, real named sources with one-line descriptions each. Good closing slide. |

**Net: 2 of 8 slides have visible, judge-detectable execution defects — and both are on your most technical, most-scrutinized slides.**

---

## 6. Visual / Image / Map Audit

The PPT itself contains **zero screenshots of the running application** — every visual in the deck is an icon, a diagram, or a table.

I pulled the five product screenshots your own README embeds (`assets/orca1.png`–`orca5.png`) — the images your own team uses to represent the live product — and rendered them directly. They are dramatically more convincing than anything in the deck:

- **`orca1.png`** — a landing page with restrained editorial design (serif wordmark, a nautical wave motif, live status pills reading "GO · 47.6 nm clear" and "PFZ · 12.4 km"). Hero copy reads **"Ten agents read the sea. One safe, explainable decision."** This alone contradicts the PPT's "12" claim.
- **`orca2.png`** — a stats bar reading **"Agents in the Crew: 10 · Command Stations: 4 · Languages: English + தமிழ் (Tamil) · Coastline Covered: 7,516 km · Data Edition: Live."** Two things worth flagging on their own merits: (1) this is a second independent "10," and (2) "Languages: English + Tamil" in the live product is narrower than the "10 Indian regional languages" claimed in your README's tech stack — reconcile which number you actually say on stage. The "7,516 km" coastline figure also sits oddly next to a README that scopes the actual pilot to South Tamil Nadu only.
- **`orca4.png`** — an ECDIS-styled marine chart: live wind-flow-field rendering, GEBCO depth shading in blue gradient, and a rendered cyclone vortex over the Gulf of Mannar, with a live coordinate readout and a persona selector. This is genuinely the most visually persuasive asset in your entire submission, and it is **completely absent from your deck**.
- **`orca3.png`** — a live answer card: a green "Go" safety telegraph banner ("All Parameters Within Safe Operational Limits") next to evidence tiles for wave height, wind speed, lightning, IMBL distance, MPA violation, tide, nearest PFZ, and sector status — literally the PS's "evidence-based recommendation" requirement rendered as a UI, sitting next to a live map.
- **`orca5.png`** — a "Reasoning & Agent Graph" trace viewer, live, with rehearsed scenario buttons ("Thoothukudi Safe Path – GO," "Pamban Wave – CAUTION," "SOS – DISTRESS Handoff," "Deep Multi-Agent – Critic Loop") and real per-node latencies (Weather Intelligence 480ms, Geospatial 190ms, Ocean Analytics 260ms feeding Risk Assessment 40ms and Visualization 75ms, Reporting 720ms, 8/8 steps at 410ms shown). Two of the node cards are explicitly tagged `gemini-3.5-flash` — independent confirmation an actual model is in the loop, not just claimed — and the rest are tagged `Deterministic`, matching exactly what I read in `graph.py` and `risk_assessment.py`. This single screenshot is strong evidence your fan-out/fan-in graph is genuinely executing, not just diagrammed.

**You are pitching a visualization-heavy marine platform with a text-and-icon deck, while your best evidence — the live map, the answer card, the reasoning trace — sits in a repo folder no judge will open unless they go looking for it.**

---

## 7. GitHub / Codebase Audit

This repo is materially more mature than a typical SIH prototype.

**Structure:** clean separation — `backend/orca/{agents,api,auth,data,db,graph,llm,notifications,ops,replay}`, a 16-route Next.js frontend including a dedicated `/reasoning` trace viewer and a `/persona` side-by-side comparison page, 11 planning/architecture documents under `docs/`, a real `docker-compose.yml`, and a CI workflow.

**Tests — I didn't just count these, I ran them.** After installing a working subset of dependencies in a sandbox, `pytest` on the safety-critical core — `risk_assessment`, `distress`, `planning`, `resilience`, `contracts`, `reporting`, `critic`, and the NaN-safety-gate test — passed **103/103**, with no mocking gymnastics required. The geospatial/visualization/voyage/auth tests fail in a fresh clone, but for defensible reasons, not because the code is broken: the 18.72GB data directory is (correctly) `.gitignore`d, and the auth tests need a live Postgres instance. A judge who clones this cold and only runs `pytest` will see failures they might misread as broken code — you should pre-empt this on stage ("the data layer isn't in git because it's 18GB — here's how to run it").

**Defensive engineering, verified by reading the actual functions, not just their docstrings:** `risk_assessment.py`'s `_known()` guard exists specifically to stop NaN or missing readings from silently passing a safety threshold — the module's own comment names the exact failure mode it closes ("a GO-shaped number conjured from absent data"), and cites a real, live path where it matters (ERA5 masks wave height as NaN at Thoothukudi's own point in the historical Gaja replay). `resilience.py`, `query_cache.py`, and `query_coalescing.py` show the same instinct applied to infrastructure failure, not just data quality.

**A CI pipeline that enforces its own architecture, not just style:** beyond `ruff`/`mypy`/`pytest`, `.github/workflows/ci.yml` includes a custom grep-based **vendor-SDK-import guard** (no file under `orca/agents/` may import an LLM SDK directly — every LLM call must go through the tiered `orca/llm/` abstraction) and a **persona-leak guard** (persona may only be referenced by Agent 1 and Agent 9 — a specialist agent that reads persona is treated as a reintroduction of a named prior bug). This is CI enforcing a documented design principle, not linting for style — genuinely unusual discipline for a student team, and worth saying explicitly in a technical Q&A.

**Honesty as an engineering habit, not an accident:** code comments explicitly flag what's simulated (`distress.py`'s DAT-SG handoff), what's a "starter, not validated" dataset (the distress phrase lists), and what's narrower than the marketing claim (Bhashini's HTTP call is "not wired up yet" even with credentials present). This is the single most valuable asset in your submission and it is currently nowhere in your pitch materials.

**Loose ends, some already cleaned up since an earlier pass:** the repo's own prior audit (`docs/competition/ORCA_SIH2026_Evaluation.md`) flagged a leftover `PASTE_YOUR_IMAGE_URL_OR_PATH_HERE` placeholder in the README and two stray scratch files at repo root — I checked, and **both are now gone.** The distress-phrase language coverage that same doc flagged as "only 3 languages" is now 5 (ml and te added, with a code comment crediting it to "SIH finale checklist P1 #1" — you've evidently already worked one item off your own prior audit's list). What's notable is that the two **P0** items from that same prior audit — slide 2's overflow and slide 5's garbled text — are **not** fixed, while lower-priority P1/P2 items were. Your own prioritization order got inverted somewhere between that audit and now.

**What's genuinely implemented:** language ingress/egress, planning/intent routing, weather intelligence, geospatial boundary checks, the deterministic risk engine, visualization payload construction, reporting/citation assembly, the conditional critic agent, sentinel background polling, distress detection (5 languages, thin), a voyage/route-planning API endpoint.

**What's partially implemented:** multilingual voice (local Whisper/MMS-TTS fallback works; Bhashini, the claimed differentiator, is not connected at the HTTP level regardless of credentials); Discovery as an independent agent (it's a data field inside Ocean Analytics' output, not its own graph node).

**What's simulated, not live:** the DAT-SG/Sagarmitra distress handoff — explicitly labelled in the code that produces it.

**What I could not verify from static code alone:** actual multi-turn conversational memory; live route re-planning under changing conditions; the "≤3 sec safety verdict latency" figure on slide 4 (plausible given the deterministic design and the 410ms figure visible in your own trace screenshot, but I did not benchmark it myself).

---

## 8. PPT Claims vs. GitHub Reality

| PPT Claim | Status | Basis |
|---|---|---|
| "12-Agent Tiered System" | 🟡 Partially verified | 12 conceptually named roles exist across docs/code, but only 9 run as nodes in the main query graph (Sentinel runs as an independent background loop; Discovery is a data field, not a node). Your own live product says "10" in three separate places — the landing hero copy, the stats bar, and the reasoning-graph header — which a judge can check against your PPT in under a minute. |
| "Deterministic + LLM Hybrid" | ✅ Verified | `graph.py`/`risk_assessment.py` confirm the safety verdict never calls an LLM; 5 of 12 named roles do |
| "Real-Time Re-Routing" | 🟠 Superficially demonstrated | `/api/voyage-plan` exists; no PPT or screenshot evidence of dynamic re-routing behaviour; unverified live |
| "Bhashini, IndicTrans2 & offline Whisper/TTS" presented as one working stack | 🟠 Misleading as phrased | IndicTrans2 + local Whisper/MMS-TTS are the real, working path; Bhashini's HTTP integration is not wired up yet — confirmed in `voice.py` itself, not just "pending" as the PPT implies |
| "DAT-SG/Sagarmitra handoff" | 🔴 Unsupported as presented | Code explicitly labels this `SIMULATED`; slide 4 presents it as a functioning step in the pipeline |
| "Provenance-backed: every claim carries a dataset + timestamp source" | ✅ Verified | `SourceProvenance` is wired through weather, geospatial, ocean, and risk agents into the final citation list |
| "Auditable trace log (OpenTelemetry)" | 🟡 Partially verified | `trace.py`/`logging_utils.py` exist; OpenTelemetry usage referenced but not independently benchmarked by me |
| "Zero-cost data" | ✅ Verified | INCOIS, Open-Meteo, NDMA, GEBCO, MOSDAC, VLIZ, WDPA, and Survey of India tide tables are genuinely free/public, confirmed against the dataset master list's own source URLs |
| "9/12 modules coded" | ✅ Verified (self-disclosed) | Consistent with what's actually wired into `graph.py` |
| "20/25 datasets procured & verified" | 🟡 Partially verified | `docs/data/ORCA_Dataset_Master_List.md` lists well over 20 named, real sources with URLs across four tiers; I could not independently confirm the exact 20/25 fraction from file counts alone |

---

## 9. Agentic AI Audit — the section this PS will scrutinize hardest

- **Rule-based orchestration?** No. `_route_after_distress` and `_route_after_reporting` are real conditional branches that change graph topology based on runtime state, not fixed sequential calls.
- **LLM does everything wearing different hats?** No — the opposite. Safety-critical decisions are deliberately walled off from the LLM by both code structure and a CI guard that enforces it.
- **Tool-using LLM?** Yes, for the LLM-assisted nodes specifically (planning's intent classification, reporting's narrative synthesis, the conditional critic, discovery's source-selection narratives).
- **Multi-agent system?** Yes, in the meaningful sense: distinct specialized nodes, a shared typed state (`ORCAState`), a compiled graph with genuine fan-out/fan-in — `weather_intelligence`, `geospatial`, and `ocean_analytics` run in parallel and join into `risk_assessment` and `visualization`, which join into `reporting`. I read this in the graph definition, not just the diagram.
- **True agentic system (autonomous planning + dynamic agent selection + a verification loop)?** Close, not fully there. Planning does build a real execution plan that gates whether Ocean Analytics runs at all — genuine dynamic routing, not decoration. But the graph's topology is fixed at compile time; it's a `StateGraph`, not an agent freely deciding at runtime which agent to invoke next. The Critic agent is your one genuine verification loop, and it's conditional on `reasoning_depth == DEEP`.

**Verdict: this sits convincingly in "credible multi-agent system with one genuine verification loop," not "an LLM chatbot calling APIs."** That's a stronger, more defensible position than most SIH teams claiming "agentic AI" will hold up under questioning — and it's defensible specifically because the deterministic/LLM boundary is enforced in code and CI, not asserted in a slide.

**Where a skeptical judge will push:** *"If the graph topology is fixed at compile time, what's stopping this from being called a well-engineered pipeline instead of an agentic system?"* The honest answer, and it's a good one: the Planning agent's execution plan dynamically decides which branches of that fixed graph actually matter for a given query (Ocean Analytics is skipped entirely when the plan doesn't call for it) — that's agent-level task decomposition, even though the wiring underneath it is compiled rather than improvised. Have this answer ready verbatim; don't let the question catch you flat-footed.

---

## 10. Technical Architecture, Marine Science & Routing Audit

**Frontend:** Next.js 16 + React 19, MapLibre GL + Deck.gl, 16 routed pages including a dedicated `/reasoning` trace viewer and a `/persona` side-by-side comparison view — confirmed present in the file tree and directly visible in your own screenshots.

**Backend:** FastAPI + LangGraph, SSE streaming with one `agent_span` frame per agent as it completes, a priority-lane `asyncio.Semaphore` pool that isolates safety-critical queries from ordinary traffic, request coalescing for duplicate concurrent queries, a Postgres-advisory-lock-protected Sentinel loop so a multi-instance deployment never double-fires an alert, and a fail-safe wrapper (`run_traced_node`) around every agent so a broken upstream feed degrades to a LOW-DATA verdict instead of a 500. This reads as production-minded engineering, not hackathon scaffolding.

**Marine intelligence layer:** real named datasets across INCOIS (ERDDAP, PFZ, Ocean State, Hazard Advisories), MOSDAC, IMD (API, CAP/SACHET, Damini lightning), Open-Meteo, Survey of India tides, Copernicus, NASA Ocean Color, and GEBCO. Your PFZ output is **consumed from INCOIS's own published advisory**, not independently derived from raw SST+chlorophyll correlation — a scientifically conservative, defensible choice (INCOIS already publishes this product three times a week; re-deriving it from raw satellite bands would be reinventing an existing operational model for no real gain) — but it means the PS's literal example query, *"which regions show high chlorophyll and favourable sea surface temperature,"* is answered by relaying INCOIS's zone rather than the team's own multi-variable correlation. Frame this as an intentional, defensible engineering choice in Q&A — don't let it read as a shortfall you didn't notice.

**Geospatial layer:** real GeoPandas/Shapely boundary checks against actual VLIZ EEZ and WDPA MPA geometries. There is no dedicated IMBL treaty-line geometry in the data — the code uses the Sri Lanka EEZ boundary as a named, explicit proxy and caps confidence at MEDIUM as a direct consequence. This kind of self-imposed confidence discount on your single highest-consequence number (the code's own comment calls IMBL distance exactly that) is precisely what a safety-conscious judge wants to see — use it in your pitch instead of hiding it.

**Route optimization:** `/api/voyage-plan` and `voyage.py` exist and are described in the README as bathymetry-aware with geofence constraints. Nothing on any slide demonstrates this, and I could not verify from static code alone whether it performs genuine multi-constraint optimization or a shortest-path-plus-hazard-avoidance heuristic. **This is your single largest evidence gap against an explicit PS requirement** — the PS names "safest route for a fishing vessel considering weather and sea-state conditions" directly in its example queries.

---

## 11. Marine Science / EO / PFZ Audit

- PFZ is relayed from INCOIS's own advisory product (bearing, distance, sector), not independently modeled from chlorophyll/SST correlation — see §10 for why that's a defensible choice, provided you can say so plainly if asked.
- SST, chlorophyll, currents, tides, and bathymetry all come from named, real, checkable sources (MOSDAC, GEBCO, Copernicus, NASA Ocean Color) rather than being asserted generically.
- The risk engine performs genuine multi-variable reasoning — wave height, wind, lightning, cyclone alert level, IMBL distance, and MPA status are combined through one threshold cascade with vessel-class-specific deltas, not independently displayed and left for the user to synthesize.
- What a strong SIH implementation should ideally add beyond this: a stated confidence/uncertainty band on the PFZ recommendation itself (not just on the overall safety verdict), since a relayed advisory updates only ~3×/week per your own dataset list, and a fisherman asking "today" deserves to know how stale that specific number is — this is a smaller, cheap addition that would strengthen your "explainable, evidence-based" claim specifically on the PFZ query, which is the PS's very first example.

---

## 12. Geospatial & Routing Audit

- Boundary/geofence logic uses real polygon containment and proximity checks (Shapely/STRtree per the dependency comments), not distance-to-a-point-on-a-line approximations.
- The IMBL proxy caveat (§10) is the standout piece of honest engineering here — it is exactly the kind of self-aware confidence discount that separates a safety-conscious team from one that ships a number without asking whether it's the right number.
- Route optimization is the weak point: real code exists, zero visible evidence. Until you can show a specific hazard-avoidance route on a map — even one hardcoded scenario you've verified end-to-end — you cannot currently defend "safe route optimization" as more than a claim, whatever the code underneath actually does.
- Map quality, judged from your own `assets/orca4.png` screenshot: legible wind-flow-field vectors, a genuinely readable depth-shading legend, and a live coordinate/timestamp readout — this reads as a serious marine-intelligence product, not a student map mockup. It is also your single best piece of unused evidence (see §6).

---

## 13. Multilingual / Conversation Audit

- Text translation depth is real: IndicTrans2 running locally, 10 languages claimed in your README's tech stack.
- Distress-detection language coverage is the asymmetry that matters most: 5 languages (en/ta/hi/ml/te), each dictionary-verified but explicitly self-labelled a "STARTER set, not validated," with no native-speaker review of any of the five lists. For a **safety** platform, the safety-critical language surface should be your best-covered one, not your thinnest — this is your single highest-priority technical gap, and it's already correctly identified as such in your own code comments.
- Multi-turn conversational memory: I could not confirm a dedicated conversation-memory module from the file tree. If it exists, it isn't visible from static structure; if it doesn't, this is an explicit PS ask ("supporting contextual, multi-turn conversations that enable users to refine queries") with no current evidence either way.
- "Voice-first, multilingual" as a single claim is doing more work than the current implementation supports — the working path (local Whisper/MMS-TTS) is real and worth being proud of on its own terms; presenting it as interchangeable with a Bhashini integration that isn't wired up is the part that invites trouble.

---

## 14. Safety & Reliability Audit

Would I trust this system enough to recommend it to a fisherman, based on what I could verify?

**For the go/no-go verdict specifically: yes, with caveats I'd want said out loud.** The deterministic risk engine is the strongest part of your submission. I read the actual threshold logic, and the design explicitly refuses to let missing or unreadable data produce a false "GO" — a wave-height reading of `None` or `NaN` degrades the verdict to CAUTION with the specific missing field named, never silently to SAFE. Vessel-class deltas (small fishing boat vs. mechanized trawler vs. cargo vessel) are applied before threshold comparison, not bolted on after. Confidence is computed as the worst tier among all contributing inputs, never an average — an explicit design rule your own code calls "uncertainty degrades conservative, it never nets out."

**Downstream of the verdict, trust drops.** The SOS handoff to Coast Guard MRCC is explicitly simulated — no live telephony/transponder integration exists — and this is disclosed in a code comment, not on any slide. The distress-phrase detector has real, self-disclosed gaps in dialect and colloquial coverage across all five languages it supports. On a marine safety platform, an undisclosed gap that a judge discovers independently does more reputational damage than the gap itself would if you'd said it first.

**What would increase trust, concretely:** a visible confidence tier next to every verdict shown in the demo (not just in the API payload); a rehearsed missing-data scenario shown live, so judges see the system degrade to CAUTION instead of silently guessing; and a single slide stating plainly what's live, what's fallback, and what's simulated, said before anyone asks.

---

## 15. User Persona / Real-World Workflow Audit

- **Fisherman:** the "one computation, four renderings" design is a genuinely strong answer to a real usability problem — a GO/CAUTION/NO-GO banner plus voice output plus a single map pin is close to the minimum cognitive load a non-literate user needs, and it's substantiated by your own screenshots, not just asserted.
- **Researcher:** the evidence-tile answer card (wave height, wind, tide, nearest PFZ, sector status, confidence) plus a described CSV/NetCDF export path gives genuine analytical depth, more than most hackathon teams bother building for a secondary persona.
- **Coastal authority:** a described district-level risk board and CAP-format alert template is the right shape for this persona; I could not verify how complete this view is beyond the README's description.
- **Maritime/commercial operator:** waypoint tables and bathymetry-aware routing are the right idea; this is the same route-optimization gap flagged in §10 and §12 — the persona's core need is the PS requirement with the least visible evidence.
- **Government deployment:** the deploy story (Docker Compose, Vercel + managed PostGIS) is realistic and appropriately modest for a pilot rather than overpromising national scale — a reasonable government evaluator would read this as credible, not vapor.
- A single "this isn't right for me" correction control that re-renders the same already-computed answer under a different persona, with no re-query, is a well-thought-out detail that directly reduces operational friction — and it's visible in both the PPT and your own screenshots, so it's one piece of your product story that's actually landing in both places already.

---

## 16. Innovation & Differentiation

**What a competing team could plausibly build in 2–4 days:** a chatbot wrapping two or three public marine APIs with an LLM narrating the numbers, a single map with a few overlay toggles, and a "multilingual" badge backed by a generic translation API.

**What would stay hard for them to replicate quickly:** the deterministic/LLM boundary enforced at the CI level (not just a stated intention), the fail-safe degradation architecture, the honest confidence-tiering discipline, and the persona-rendering-without-re-query design. These show up in your `docs/` phase-planning files as the result of real design iteration across multiple build phases, not something assembled over a weekend.

**Genuine differentiators, ranked by how hard they'd be to fake or replicate:**
1. A zero-LLM-hallucination safety core with inspectable, threshold-level logic — the strongest, hardest-to-fake asset you have.
2. Persona-aware single-computation rendering with a working correction control.
3. Fail-safe degradation (a named LOW-DATA verdict, never a silent wrong answer or a crash).
4. A narrowly and honestly scoped pilot region (South Tamil Nadu) with real, checkable local stakes — IMBL crossings, an active MPA, monsoon cyclone exposure — instead of a generic pan-India claim that can't be checked by anyone in the room.

---

## 17. "Wow Factor" Analysis

Your strongest wow moment exists and is currently unused: the live ECDIS-style map with a rendered wind-flow field and cyclone vortex, paired with the evidence-tile answer card resolving in real time from raw data through six specialist agents to a GO/CAUTION/NO-GO banner. That sequence, watched live, answering "is it safe to go out near Thoothukudi tomorrow" — **is** your wow moment. It appears in zero of your eight slides.

---

## 18. Demo Strategy

Assume 5–10 minutes.

1. **First 20 seconds:** open directly on the live map with the wind-flow field already rendered. No title slide, no logo animation. Say the death-toll line ("282+, and the warning had already been issued in time") over it.
2. **First query:** the fisherman persona, in Tamil, asking whether it's safe to go out tomorrow morning — this is the PS's own first example query, and it exercises language detection, the deterministic safety core, geofencing, and evidence citation in one shot.
3. **Where agents should become visible:** open the `/reasoning` trace panel live for this exact query so judges watch the fan-out happen in real time, not just the final card — you already built this page; use it.
4. **What should demonstrate differentiation:** switch persona live (fisherman → researcher) on the same already-computed answer via the correction control, so "one computation, four renderings" is seen, not asserted.
5. **What should demonstrate safety:** feed a missing-data scenario — you already have a test fixture for exactly this (`discovery__sst_fallback_cascade.json`) — and show the verdict degrade to CAUTION with a named reason instead of silently returning GO.
6. **What should NOT be demoed live:** the Bhashini voice path (not connected — a live failure here is your worst-case scenario), the DAT-SG SOS handoff (simulated — disclose it before being asked, don't let a judge discover it), and route re-optimization unless you've personally verified the exact demo path end-to-end beforehand.
7. **Final screen judges should remember:** the live Reasoning & Agent Graph trace view, ended on a completed run showing all 8 steps resolved with real latencies. It's the one screen that visibly answers the question every judge on this PS is actually asking: *is this really agentic, or are you telling me it is.*

---

## 19. Scoring Matrix

| Category | Weight | Score | Rationale |
|---|---|---|---|
| Problem Understanding | 10 | 9 | Named incident (Cyclone Ockhi, 282+ deaths), a specific mechanism of failure (warning issued but never reached boats already at sea), and a narrow real pilot region with checkable local stakes |
| Requirement Coverage | 10 | 7.5 | Nearly every explicit PS requirement has real supporting code; route optimization is the one explicit ask with essentially zero visible evidence anywhere |
| Innovation | 10 | 7 | The deterministic/LLM separation and persona-rendering design are genuinely differentiated; the base "multi-agent over marine data" pattern itself is now a known approach in the field, not novel on its own |
| Agentic AI Depth | 15 | 12 | Real conditional orchestration graph, a real deterministic/LLM boundary enforced by CI, one genuine verification loop (Critic); topology is compiled, not runtime-improvised, which caps this short of full marks |
| Technical Architecture | 10 | 8.5 | Unusually mature for a hackathon: real tests I ran myself, fail-safe degradation, priority lanes, advisory-locked background jobs |
| Data / EO / Marine Intelligence | 10 | 7 | Broad, real, named sources; PFZ is relayed from INCOIS rather than independently derived — defensible, but it caps how much credit "our own marine intelligence" can claim on that specific query |
| Geospatial Intelligence | 10 | 8 | Real boundary geometry, an honestly self-capped confidence tier on the IMBL proxy — exactly the kind of judgment call judges want to see |
| Prototype Quality | 10 | 7 | 9 of 12 named modules coded per your own slide; the core safety path is solid and tested; multilingual voice and the SOS handoff are the visible, disclosed gaps |
| UX / Visualization | 5 | 3.5 | The actual product screenshots are genuinely strong; none of that strength currently reaches the PPT, which is what this score has to be judged on if the deck is all a panel sees before the demo |
| Real-world Impact | 5 | 4 | Concrete, named, checkable stakeholder consequences across four personas |
| Scalability / Deployment | 5 | 3.5 | Deploy path is realistic and appropriately modest; the "scale beyond one pilot region" story is asserted on a roadmap line, not evidenced |
| **Total** | **100** | **~77.5** | |

**Current score: ~77.5/100 → 7.8/10.**

For calibration: your own repo's prior self-audit scored an earlier version of this same deck/repo at ~78/100 using this identical rubric. The score hasn't moved because the things that moved (distress-language coverage, repo hygiene) were P1/P2 items, while the two changes that would actually move this score — fixing slide 5 and getting real product screenshots into the deck — are both still outstanding.

---

## 20. Winning Probability

There is no public field data for PS 26176 yet — this is a new 2026 statement, and SIH doesn't publish per-PS competitor counts before the finale, so anyone claiming to know who else is competing at this stage is guessing. What can be assessed honestly is the gap between your demonstrated capability and your demonstrated presentation.

- **Being noticed positively:** high, once the deck is fixed — a codebase this substantiated earns a second look from any judge who checks GitHub, and current SIH guidance suggests more judges are doing exactly that in 2026.
- **Making the shortlist:** likely on technical merit alone — the deterministic safety core and the disclosed-honesty engineering culture are above what this problem class typically sees.
- **Finishing in the top tier:** plausible, not currently assured — contingent on fixing slide 5, disclosing the simulated/pending pieces proactively instead of waiting to be asked, and getting the live demo screens into the actual pitch instead of leaving them in the repo.
- **Winning the PS outright:** possible if the live demo performs the way the code and your own screenshots suggest it should. I cannot verify demo-day reliability from static code — that's the one variable no audit of this kind can close for you.

**Internal-round standard vs. Grand Finale standard:** internal/national screening rewards a clear idea, a working slice, and confident communication, and incomplete documentation alone can eliminate a strong idea before a prototype is even judged. The Grand Finale raises the bar in a specific way: judges actively try to break safety claims, compare your PPT against your repo live, and reward teams whose system matches what they said it does, under a 36-hour high-pressure build-and-defend format. Qualifying internally tells you the *idea* cleared a bar. It does not tell you the *deck* or the *disclosed claims* will survive Grand Finale scrutiny — right now, several specific claims (12 agents, a working DAT-SG handoff, an implied working Bhashini stack) would not survive a five-minute cross-check against your own GitHub without a proactive correction from your side first.

---

## 21. Critical Weaknesses

Ranked by how much they could cost you, not by how hard they'd be to fix:

1. **A safety-critical claim presented as functional when it's explicitly simulated in your own code.** The DAT-SG handoff is your single biggest credibility risk if discovered rather than disclosed.
2. **Your architecture slide is currently unreadable in places.** On the one PS that explicitly tests architectural rigor, slide 5's garbled Ground Rules box is a self-inflicted wound with a fifteen-minute fix.
3. **Three independent first-party sources in your own live product contradict your own PPT's headline number.** "12" vs. "10" is a discrepancy any judge can find in under a minute by opening the app next to the deck.
4. **Your best evidence is the one thing not in your pitch.** The live map and reasoning trace are more persuasive than your entire current deck combined, and they're absent from it.
5. **Route optimization — an explicit PS requirement — has no visible evidence anywhere in your materials,** despite real supporting code existing.
6. **Your safety-critical language coverage is your thinnest, not your strongest.** Distress detection covers 5 languages at a "starter, unvalidated" standard while your UI multilingual claims run to 10 — for a safety platform, that asymmetry is backwards.

---

## 22. P0 / P1 / P2 Implementation & Fix Plan

**P0 — must fix before the Grand Finale (small effort, large downside if skipped):**

| Fix | Why it matters | PS requirement addressed | Effort | Demo value |
|---|---|---|---|---|
| Rebuild slide 5 from scratch, proofread it | Removes your single highest-risk credibility item on your most-scrutinized slide | Architecture credibility, judged directly | <1 hour | High |
| Fix slide 2's text overflow | First content slide sets the tone for the other seven | Presentation quality | 15 minutes | Medium |
| Add one "what's live / fallback / simulated / pending" slide (Bhashini, DAT-SG, distress-language coverage) | Converts your biggest disclosed liability into your biggest credibility asset — almost no competing team will volunteer this | Safety/reliability, explainability | 30 minutes | Very high |
| Replace at least 2 slides with real product screenshots (the ECDIS map, the evidence-tile answer card) | You are currently hiding your best evidence | UX/visualization, demo quality | 1 hour | Very high |

**P1 — high impact:**

| Fix | Why it matters | PS requirement addressed | Effort | Demo value |
|---|---|---|---|---|
| Get one real, rehearsed route-optimization example onto a slide and into the demo script | Your weakest-evidenced explicit PS requirement | Route optimization | Medium (depends how finished `voyage.py`'s logic actually is) | High |
| Reconcile the agent count everywhere it appears (PPT, README, live product) — pick one number, keep a one-line footnote for what counts as an "agent" | Removes an easily-found inconsistency | Technical credibility | 30 minutes | Medium |
| Confirm and state the actual number of supported languages consistently across the stats bar, README, and pitch | Removes a second easily-found inconsistency | Multilingual claim | 30 minutes | Medium |

**P2 — nice to have:**

| Fix | Why it matters | Effort |
|---|---|---|
| Expand distress-phrase coverage further, or at minimum get one native-speaker review pass on the existing 5 languages | Your most safety-sensitive disclosed gap | Depends on access to reviewers |
| Fill in the blank "Team ID" field on slide 1 | Minor, but reads as unfinished | Trivial |

---

## 23. Features to De-emphasize or Remove From the Pitch

- Don't lead with "12-Agent Tiered System" as a headline number on stage — it invites exactly the "is that really 12?" question you're least prepared to answer cleanly right now. Lead with what the agents *do* (a deterministic safety core plus persona-aware rendering), not the count.
- Drop "DAT-SG/Sagarmitra handoff" from spoken claims entirely unless you can demo it live or state up front that it's simulated — as currently framed, it's a claim you cannot defend under one follow-up question.
- Keep the offline-first/PWA story to one line. It's solid engineering, but it isn't a PS requirement, and right now it's competing for attention on your deck against things that are explicit requirements (route optimization, evidence-based reasoning) and currently losing that fight for slide space.

---

## 24. Winning PPT Structure (proposed)

| Slide | Title | Main message | Visual | Spoken, not shown |
|---|---|---|---|---|
| 1 | Title | As-is, fill in Team ID | — | — |
| 2 | The Problem | 282+ deaths, warning issued but never reached the boat (fix overflow) | One strong stat card, nothing else competing for space | Named incident detail |
| 3 | Live Product | "This is running right now" | **Screenshot: the ECDIS map with wind field + cyclone rendering** | — |
| 4 | The Answer | Evidence-tile answer card, GO/CAUTION/NO-GO | **Screenshot: the actual answer card** | Walk through one tile live if possible |
| 5 | Architecture (rebuilt, proofread) | Deterministic core vs. LLM-assisted layer, clearly separated | Clean redo of the current slide 5 | — |
| 6 | Honesty Slide (new) | What's live / fallback / simulated / pending | Simple 3-column table | Say it before you're asked |
| 7 | Live Reasoning | "It's actually agentic — watch it happen" | **Screenshot: the Reasoning & Agent Graph trace view** | Narrate the fan-out/fan-in live |
| 8 | Feasibility & Roadmap | As-is, keep the honest module count | — | — |
| 9 | Impact & References | Merge current slides 7 and 8 | — | — |

---

## 25. Difficult Judge Questions to Prepare For

1. Is the Bhashini integration live right now, or is that the local fallback I'd actually be testing?
2. Walk me through exactly what happens if a fisherman sends an SOS right now — where does that signal actually go?
3. Your deck says 12 agents. Your own landing page says ten. Which is it, and what's the difference?
4. Show me a query where the verdict comes back CAUTION or NO-GO, not GO — I don't want your best-case demo.
5. How is IMBL distance computed if there's no official treaty-line geometry in your data?
6. What happens when two data sources disagree — say INCOIS says CAUTION and Open-Meteo says SAFE?
7. Is your PFZ recommendation your own model, or are you relaying INCOIS's own advisory?
8. Your distress-phrase list covers five languages — how were those phrases verified, and by whom?
9. What does `reasoning_depth: DEEP` actually change, and who or what decides a query needs it?
10. Your Critic agent — what specifically does it catch, and do you have a real example where it changed an answer?
11. Show me the actual route-optimization output for a real hazard scenario — what is it optimizing against?
12. If Sentinel's background service scales to multiple instances, what stops a fisherman from getting the same alert twice?
13. How would this system perform outside your Tamil Nadu pilot region tomorrow, with zero additional engineering?
14. If your LLM provider goes down mid-query, what does the fisherman actually see on screen?
15. Who validated your safety thresholds — is there a marine domain expert behind those specific numbers?
16. What's your actual plan for getting Bhashini access, and what's the fallback if it never arrives?
17. Walk me through exactly which agents are genuinely autonomous versus which are a fixed pipeline with good branding.

**What would impress me on each of these:** a direct, unhedged answer that matches what's actually in your code — especially on questions 1, 2, and 8, where the honest answer ("not yet — here's the working fallback, here's the plan") is *more* impressive on a safety product than a confident overclaim, because it proves the team knows its own system's limits. That is exactly the posture your code already takes. Your spoken answers just need to match it.

---

## 26. Final Judge Verdict

**Problem Understanding:** 9/10
**PS Alignment:** 7.5/10
**Innovation:** 7/10
**Agentic AI:** 8/10
**Technical Depth:** 8.5/10
**Marine Intelligence:** 7/10
**Geospatial Intelligence:** 8/10
**Prototype:** 7/10
**UI/UX:** 7/10 *(based on your actual product screenshots, not the PPT itself — the PPT alone would score closer to 4/10 on this axis)*
**Impact:** 8/10
**Presentation:** 5/10
**Overall:** 7.6/10

### Current level:
**Finalist-level codebase; internal-round-level deck.**

### Estimated Grand Finale winning chance:
Not rankable against an unknown field this early, but well-positioned conditional on the P0 fixes — realistically modest without them, credible top-tier contention with them. This is a statement about your deck, not your engineering.

### Top 5 reasons you could win:
1. A genuinely deterministic, inspectable safety core that most competing "agentic" teams on this theme won't have.
2. Real product screenshots that are more convincing than your current deck currently lets anyone see.
3. An honest engineering culture that, once surfaced deliberately, reads as rare maturity to a technical panel.
4. A narrow, real, checkable pilot region instead of a vague pan-India claim nobody in the room can verify.
5. Genuine multi-agent orchestration with a real conditional graph — verified by me reading the graph definition itself, not a chatbot wearing a multi-agent costume.

### Top 5 reasons you could lose:
1. Slide 5's garbled text undermines your architecture credibility at the exact moment a technical panel scrutinizes it hardest.
2. A judge discovers the Bhashini gap or the simulated SOS handoff before you disclose it yourselves.
3. Route optimization — an explicit PS ask — has no visible evidence anywhere in your current materials.
4. Inconsistent agent counts across your own artifacts (12 vs. 10) look sloppy under a cross-reference a judge can do in sixty seconds.
5. A live-demo failure on an unrehearsed path (voice, route re-planning) with no fallback narrative ready to go.

### Top 5 changes before the Grand Finale:
1. Rebuild slide 5, proofread everything, fix slide 2's overflow.
2. Add the honesty slide — disclose Bhashini/DAT-SG/distress-coverage status before anyone asks.
3. Replace at least two slides with real product screenshots (the map, the answer card).
4. Get one real, rehearsed route-optimization example into evidence.
5. Reconcile the agent count everywhere it appears, and settle on one language-support number you'll actually say on stage.

### Judge's one-sentence verdict:
*"The codebase is the pitch you should have brought — fix the deck to match it and you're a real contender for this PS."*
