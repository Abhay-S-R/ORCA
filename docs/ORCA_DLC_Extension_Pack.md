# ORCA — DLC Extension Pack

**Everything that must be built, fixed, or proven to turn ORCA from a strong national finalist into the PS 26176 winner.**

| | |
|---|---|
| **Sources merged** | `docs/ORCA_SIH2026_Judge_Verdict.md` (code-forensic audit), `docs/ORCA_SIH2026_Grand_Finale_Judge_Audit.md` (PPT + repo audit, external), the verbatim PS 26176 capability list, and the five flags raised by the internal-round judge |
| **Written for** | Team GeekMaxxers, SIH 2026 Grand Finale |
| **Prime directive** | The PS is a **conversational agentic platform** first. The chatbot, the agents, and their visible collaboration are the product. Everything else is evidence that the product is real. |
| **Rule of this document** | Every requirement has a file-level root cause and a **binary acceptance test**. If the test can't be run in front of a judge, the requirement isn't done. |

---

## 0. How to read this

Requirements are numbered `R-<area>-<n>` so they can be assigned and tracked. Each carries:

- **Now** — what the code actually does today, with `file:line` where it matters.
- **Required** — the end state.
- **Accept** — the demonstrable test. No test, no credit.
- **Effort** — rough, single-developer.

Priority bands are defined in §8, not inline, so that the requirements can be read as a specification rather than a to-do list.

---

## 1. Corrections to the external Grand Finale Judge Audit

Your friend's audit is good and mostly accurate — its reading of the deterministic core, the CI guards, the IMBL proxy, and the honesty-as-engineering-culture point are all correct and independently confirmed. But it audited a **GitHub snapshot plus a PPT**, and several findings are stale, wrong, or softer than the code warrants. Do not carry these into your planning.

| # | External audit says | Reality in this working tree | Consequence |
|---|---|---|---|
| C1 | Multi-turn memory: *"⚪ Unverified — no dedicated conversation-memory module visible in the file tree"*, later *"I could not confirm… if it doesn't [exist], this is an explicit PS ask with no current evidence"* | **Wrong.** `backend/orca/session.py` is a real Redis-backed session store: `TTL_SECONDS = 1800`, `MAX_TURNS = 5`, a `_REAL_PLACE_SOURCES` allowlist and `last_place()` that stops a follow-up inheriting a regional-default location. It is wired end to end — `frontend/app/ask/page.tsx:150` sends `session_id`, and `graph.py:369` feeds `session_history` into reporting | You are **credited too low** on an explicit PS requirement. This is a strength, not a gap — demo it (§3, R-CONV-1) |
| C2 | *"103/103 passed in the safety-core suite"* | Understated. The **full** suite is **372 passed, 2 skipped, 138.66s** | Use the real number. It is a better number |
| C3 | *"a 16-route Next.js frontend"* | 13 routed pages (`frontend/app/**/page.tsx`) | Minor, but don't repeat a count a judge can check in 20 seconds |
| C4 | Route optimization: *"I could not verify optimization depth vs. heuristic from static code"* | **Verified, and it is a heuristic.** `voyage.py` generates exactly three fixed candidates (`offset_east`, `offset_west`, `wait_6h`) and constraint-checks them. There is no search over a cost surface. It is also **not a LangGraph node** — the file says so itself | The gap is worse than the external audit could tell, and the fix is known (R-ROUTE-1) |
| C5 | PFZ: *"SST, chlorophyll… come from named, real sources"*, implying they are used | **Half wrong.** `correlate_sst_chlorophyll()` returns `available=False` on every live call because `data/fixtures/` does not exist on disk. ~212 MB of MOSDAC chlorophyll `.nc` and INSAT-3DR SST `.h5` sit in `data/` with **zero readers** | This is the single biggest claim-vs-code gap, and the external audit missed it entirely (R-SCI-1) |
| C6 | Its entire P0 block is PPT work (slide 2 overflow, slide 5 garbled text, screenshot slides) | **Out of scope** for this cycle — there is no deck under review here | Their P0 list mostly evaporates. What survives is the *honesty slide* concept, which becomes a **spoken** discipline (R-DEMO-3) |
| C7 | *"Agents 3–6 — parallel fan-out"* implies four; actual is three | **Correct.** `graph.py:457` fans out `weather_intelligence`, `geospatial`, `ocean_analytics` only | Keep the correction; say "three parallel specialists" |
| C8 | Discovery is a data field on Ocean Analytics' output, not a node | **Correct.** `graph.py:171-176` rides `source_selections` out on `discovery_data` | Correct — and §5 argues this should change |
| C9 | Scores the project **7.6/10**, same as the internal code-forensic audit's **7.6/10**, by two independent routes | Genuine agreement. Treat 7.6 as the calibrated baseline | The remaining 2.4 points are enumerated in this document |

**Net:** the external audit's diagnosis is right; its evidence base was thinner. Where the two audits disagree, this working tree wins.

---

## 2. The prime directive: this is a chatbot PS

Read the PS's own emphasis. Every one of its ten capability bullets is phrased around a **user asking something in natural language and getting a reasoned, evidenced answer back**. The maps, the routing, the geofencing, the satellite data — all of it exists in the PS text as *things the conversation can do*, not as standalone features.

ORCA's current centre of gravity is inverted. The engineering mass sits in the deterministic safety core and the geospatial layer; the conversational layer is the thinnest, most keyword-driven part of the system (`planning.py`'s five-row `ROUTING_TABLE`). That is backwards relative to how this PS will be judged.

**The single most important structural change in this document:** move engineering effort from *more capability* to *a conversation that visibly reasons*. Concretely, §5 (agentic collaboration) and §3's conversational clauses outrank everything else, including route optimization and the satellite-data revival — not because those don't matter, but because a judge who is unconvinced by the conversation will not stay long enough to be impressed by the rest.

---

## 3. PS capability contract — the ten clauses that MUST work

This is the acceptance contract. The PS text is quoted verbatim; each clause gets a pass/fail test a judge could run unprompted. **Nothing here may be half-implemented on demo day.** A clause that works only on a rehearsed phrasing is a failed clause.

### R-PS-1 — "Understanding user intent expressed in natural language"

- **Now:** `planning.py` Tier 1 is substring matching over 5 rows × ~6 keywords. Tier 2 is word-overlap against a 4-entry synonym dict at `_TIER2_THRESHOLD = 0.45`. Tier 3 (LLM) only fires when both find nothing. Realistically, most novel phrasings land on Tier 1 or the `NO_MATCH_FALLBACK_AGENTS` default.
- **Required:** intent classification that survives arbitrary phrasing, including code-mixed input ("boat safe-a irukka?"), and that **names the intent it inferred in the response**. Keep all three tiers — the tiering is defensible and deterministic-first — but (a) widen Tier 1 keyword coverage, (b) raise Tier 3 from last resort to a **confirmation pass** whenever Tier 1/2 confidence is below 1.0, and (c) surface the classification.
- **Accept:** a judge types five queries you have never rehearsed, including one code-mixed and one indirect ("my nets are still out past the reef, should I go get them tonight?"). All five route to a sensible intent, and the UI shows which intent was chosen and by which tier.
- **Effort:** 1 day.

### R-PS-2 — "Automatically identifying the language of the user's query and responding in the same language"

- **Now:** detection is deterministic Unicode-block matching across 8 scripts (Marathi/Hindi conflated, disclosed in code). Translation is real, local IndicTrans2 (`indictrans2-indic-en-dist-200M` / `-en-indic-dist-200M`). Failure degrades to passthrough **and drops confidence to LOW_DATA**, which is correct behaviour.
- **Required:** no code change to the core path — this clause largely works. What's missing is (a) **visibility** (see R-JUDGE-1), (b) romanized-Indic input ("kadal safe ah irukka" in Latin script) which the Unicode detector cannot see at all, and (c) an honest, consistent language count.
- **Accept:** Tamil script in → Tamil out. Romanized Tamil in → correctly detected, not silently treated as English. The response card names the detected language and the translation engine.
- **Effort:** 0.5 day for romanized detection (a short n-gram/keyword heuristic per language, deterministic, no model).

### R-PS-3 — "Supporting contextual, multi-turn conversations that enable users to refine queries and explore related scenarios"

- **Now:** **Already real** and under-sold (see C1). `session.py` holds 5 turns at 1800s TTL with place-source guarding; `graph.py:369` passes `session_history` to reporting.
- **Required:** prove coreference and refinement explicitly. Session history currently informs *narration*; it should also inform *classification* — `classify_intent` already accepts `(normalized_query, session_history)` in its contract but `run()` passes only the query (`planning.py:203`). Wire the history in so "what about tomorrow?" inherits the prior intent rather than falling to the no-match default.
- **Accept:** the three-turn chain runs live, unrehearsed: *"Is it safe near Rameswaram tomorrow?"* → *"What about the day after?"* → *"And the nearest fishing zone there?"* Turn 2 must inherit **both** the place and the intent; turn 3 must inherit the place while changing intent. Nothing resets to a default location.
- **Effort:** 0.5 day.

### R-PS-4 — "Autonomously discovering, retrieving, and integrating relevant satellite, marine, meteorological, and geospatial datasets"

- **Now:** `discovery.py` is genuinely the best agentic artifact in the project — a 25-source registry with `authority_tier`, `FALLBACK_CASCADES`, and narrated `SourceDecision`s ("MOSDAC NRT SST chosen over Copernicus CMEMS reanalysis: 6 h old vs ~5 d, same Tier-1 authority — freshness decided it"). But it is **not a graph node** (`graph.py:171-176` smuggles its output out on `discovery_data` via Ocean Analytics), and the registry advertises `mosdac_open_chl` / `mosdac_nrt_sst` as **string labels with no readers behind them**.
- **Required:** promote Discovery to a real node (R-AGENT-2) and make at least the two ISRO-lineage sources genuinely readable (R-SCI-1).
- **Accept:** the reasoning trace shows a `marine_data_discovery` span with its own latency, and its narrative names a source it *rejected* and why. At least one named ISRO product (MOSDAC / INSAT-3DR) is read from a real file during the demo.
- **Effort:** see R-AGENT-2, R-SCI-1.

### R-PS-5 — "Performing spatial, temporal, and contextual reasoning by correlating observations from multiple heterogeneous data sources"

- **Now:** spatial reasoning is strong (STRtree, geodesic, polygon containment, GEBCO depth). Temporal reasoning is real in `voyage.py` (per-leg evaluation at leg ETA) and in tides. **Cross-source correlation is the weak clause**: `risk_assessment` combines sources through a threshold cascade — which *is* multi-variable reasoning — but the system has **no notion of two sources disagreeing**.
- **Required:** a deterministic **cross-source agreement check**. When two sources cover the same variable (e.g. cached INCOIS ocean-state vs live Open-Meteo wave height), compute the divergence; if it exceeds a threshold, (a) take the conservative value, (b) drop confidence a tier, and (c) say so in the answer: *"Two sources disagree on wave height (1.1 m vs 2.4 m). Using the higher. Confidence reduced."* This is pure arithmetic — no LLM — and it directly answers the judge question the external audit predicted ("what happens when two data sources disagree?").
- **Accept:** a judge asks the disagreement question; you don't answer it verbally — you trigger it live with a fixture and the UI states the conflict.
- **Effort:** 1 day. **This is the highest-value single addition in the entire document** — it converts "we combine sources" into "we reconcile sources", which is what the PS clause actually asks for.

### R-PS-6 — "Generating explainable, evidence-based recommendations supported by maps, charts, geospatial visualizations, and marine advisories"

- **Now:** the strongest clause. Per-agent citations with dataset + acquisition timestamp + freshness, `SourceProvenance` threaded through every agent, deterministic worst-tier confidence, a `/reasoning` trace viewer, MapLibre/Deck.gl rendering, and `SourceNarration` on the answer card.
- **Required:** two gaps only — charts are thinner than maps (`chartSpec.ts` exists but time-series are under-used), and the **IMBL line is never drawn** despite being the headline geospatial number.
- **Accept:** every number on the answer card can be traced to a named dataset and a timestamp in ≤2 clicks. The IMBL standoff distance has a corresponding line and warning ring on the chart.
- **Effort:** 1 day.

### R-PS-7 — "Enhancing fishermen safety through proactive alerts for adverse weather, high waves, lightning, cyclones"

- **Now:** the deterministic core is excellent and provable: `risk_assessment.py` has no LLM import, `_known()` closes the NaN-fallthrough class, vessel-class deltas are applied before comparison, and unreadable inputs degrade to `CAUTION_MISSING_DATA` naming the missing field. Sentinel polls in the background under a Postgres advisory lock. **But** `generate_alert_payload` **raises `NotImplementedError` for any non-English language** (`risk_assessment.py:139-144`), so a Tamil-speaking fisherman receives no proactive alert at all, and SMS dispatch raises.
- **Required:** route Sentinel's alert text through Agent 1's `translate_from_english` for the languages with verified TTS (en/hi/ta/te), exactly as the docstring anticipates. Keep the raise for unverified languages — mislabelled English is worse than nothing.
- **Accept:** a Sentinel-triggered alert arrives in Tamil, in-app, with Tamil voice output.
- **Effort:** 0.5 day.

### R-PS-8 — "Geofencing-based notifications when approaching international maritime boundaries, restricted waters, marine protected areas, ecologically sensitive zones"

- **Now:** real VLIZ EEZ and WDPA MPA geometry with per-feature `orca_precision` tiering and a refusal to geofence against imprecise centroids — genuinely good. IMBL is an **honestly disclosed Sri Lanka EEZ proxy** capped at MEDIUM confidence (`graph.py:62-64`). Hard block at ≤1 nm, CAUTION at ≤3 nm.
- **Required:** (a) draw the line (R-PS-6), (b) make the proxy caveat a **spoken opener**, never a discovered flaw, and (c) add approach-direction awareness — "47.6 nm clear" is much less useful than "47.6 nm, and your current heading closes it in ~6 h."
- **Accept:** move the position toward the boundary live and watch CLEAR → CAUTION → NO_GO with the line visible on the chart.
- **Effort:** 1 day.

### R-PS-9 — "Assisting with route optimization, safe navigation, and operational planning"

- See **R-ROUTE-1** in §6. This is the clause with the largest gap between PS wording and implementation.

### R-PS-10 — "Delivering reliable recommendations together with the supporting evidence and reasoning used to derive each response"

- **Now:** covered by R-PS-6's machinery, plus the Critic loop on DEEP.
- **Required:** the reasoning must be legible to a *fisherman*, not only to a researcher. Today the `/reasoning` page is the evidence surface and it is engineer-facing.
- **Accept:** in fisherman persona, "Why this answer?" produces three plain sentences naming the deciding factor, the source, and the freshness — no agent names, no jargon.
- **Effort:** 0.5 day.

### R-PS-ARCH — "Modular multi-agent architecture… demonstrating autonomous collaboration among agents"

- The whole of §5. This is the clause the panel will probe hardest, and the one ORCA is furthest from satisfying in spirit.

---

## 4. The internal-round judge's five flags

All five are legitimate. Three of them are sharper than either written audit, and one of them (flag 2) uncovers a defect neither audit caught.

### R-JUDGE-1 — Show the IndicTrans2 tag on both ingress and egress in the reasoning pipeline

- **Now:** the SSE span emitter (`backend/orca/api/main.py:261-285`) already computes a `model` field — but **only for LLM agents** (`used_llm = agent_real in _LLM_AGENTS`, with a tier→model mapping). `language_ingress` and `language_egress` are not LLM agents, so `model` is `None` and the frontend renders a bare `AgentPill` with a name and a status. The engine that actually did the work is invisible.
- **Root cause:** the span schema has a slot for "which model", but only LLM agents fill it. Translation is a model too.
- **Required:** generalize the field from `model` to `engine` — every span reports what executed it. `language_ingress`/`language_egress` → `IndicTrans2 · indictrans2-indic-en-dist-200M (local)`; `risk_assessment`/`geospatial`/`visualization` → `Deterministic`; LLM nodes keep their model ID. When Bhashini lands, only this string changes, which is exactly the seam the judge anticipated.
- **Accept:** the reasoning trace and the agent strip both show `IndicTrans2` on the ingress pill **and** the egress pill, and `Deterministic` on the safety pill, in the same run.
- **Effort:** 2 hours. **Highest value-per-hour item in this document** — it simultaneously answers this flag and makes the "our safety core has no AI in it" claim visible rather than spoken.

### R-JUDGE-2 — GO/NO_GO is shown for prompts that don't need a verdict, and it looks hardcoded

The judge is right, and the underlying problem is worse than the flag states. Three separate defects:

1. **The verdict chip always renders.** `frontend/app/ask/page.tsx:315` renders `PersonaAnswerMatrix` whenever `answer.risk_assessment` exists — and `risk_assessment` runs for **every** query by deliberate design (`graph.py:155-160`: a misrouted "what's the tide" from someone about to sail into a gale must still produce a hazard warning). That design decision is **correct and must not be reverted**. But the *rendering* consequence was never handled: `PersonaAnswerMatrix.tsx:402` prints a verdict Badge unconditionally, so "where are the fishing zones?" gets a "Go" chip it never asked for.
2. **The backend already solved half of this and the frontend ignores it.** `reporting.should_lead_with_verdict(verdict, matched_rows)` exists precisely to demote a GO on a non-safety question — it is passed at `graph.py:367` and it shapes the *narrative*. It is **never sent to the frontend**, so the card can't honour it.
3. **There is a genuinely fabricated number on screen.** `PersonaAnswerMatrix.tsx:53-57`'s `verdictScore()` maps GO→88, CAUTION→55, NO_GO→16 with a small confidence penalty, and renders it in a `ScoreRing` as a hard number out of 100. **It is not computed from any measurement.** A judge who asks "what is 88 out of 100?" has no good answer. This is the clearest instance in the product of a number that looks derived and isn't — it must go.

- **Required:**
  - Add `lead_with_verdict: bool` to the `final_response` SSE payload (the value already exists server-side — just serialize it).
  - When `false` **and** the verdict is GO: render the safety state as a **quiet inline reassurance line** ("Conditions safe · full check"), not a verdict chip. When the verdict is CAUTION or NO_GO it leads regardless of intent — that asymmetry is already correct in the backend and must be preserved in the UI.
  - **Delete `verdictScore` and `ScoreRing`.** Replace with the confidence tier, which is real.
- **Accept:** "Where are the nearest fishing zones?" returns a PFZ-led answer with no GO banner. The same query, run when a cyclone alert is active, is led by NO_GO. No number appears on screen that cannot be traced to a measurement.
- **Effort:** 0.5 day.

### R-JUDGE-3 — Intent-based and multi-intent routing of agents

- **Now:** multi-intent classification **already exists** — `classify_intent` returns a list, and `generate_execution_plan` (`planning.py:168-184`) unions the agents of every matched row. But the graph **almost entirely ignores the plan**: `graph.py:161-163` is the *only* place `execution_plan` gates anything, and it gates exactly one agent (Ocean Analytics). Weather, geospatial, risk and visualization run unconditionally on every query.
- **The tension to resolve honestly:** the unconditional execution is a deliberate fail-safe (a misrouted safety question must still get a safety verdict). Do **not** trade that away. The fix is to separate **execution** from **presentation and emphasis**:
  - Execution stays fail-safe: safety-relevant agents always run.
  - The plan decides what is *foregrounded*, what is *elaborated*, and what is *trimmed* from the response — which the codebase already does once, for NO_GO early-exit (`graph.py:322-325`).
  - Genuinely optional analytical agents (Ocean Analytics' DEEP diagnosis, the voyage planner once it is a node, trends) are plan-gated for real.
- **Required:** (a) surface `matched_intent_rows` in the response and in the trace so multi-intent is *visible* ("Intents: SAFETY_CHECK + PFZ_NEAREST → 5 agents dispatched"), (b) plan-gate every genuinely optional agent, (c) make a compound query demonstrably dispatch a larger agent set than a simple one.
- **Accept:** *"Is it safe to go out tomorrow, and where are the fishing zones?"* visibly matches **two** intents, dispatches a visibly larger agent set than *"is it safe tomorrow?"*, and the answer addresses both halves in order.
- **Effort:** 1 day.

### R-JUDGE-4 — Confidence must not be LLM-generated

- **Now:** **you already pass this**, and the judge could not tell — which is itself the problem. `risk_assessment.compute_confidence` (`risk_assessment.py:112-124`) is a pure worst-tier composition over upstream `Confidence` objects, never an average ("uncertainty degrades conservative, it never nets out"). `reporting.py:64-74` recomputes the same worst-tier rule over contributing agents. No LLM emits a confidence anywhere in the pipeline.
- **The two real defects behind the flag:**
  1. **Illegibility.** The UI shows a tier with no derivation. A judge cannot distinguish a deterministic tier from a hallucinated one by looking at it.
  2. **One genuine violation of the spirit** — `verdictScore`'s fabricated 0–100 number (R-JUDGE-2, defect 3). Whatever else is deterministic, that number is invented, and it sits in the most prominent position on the card.
- **Required:** make the derivation visible. `ConfidenceMeter` should expand to show the chain: *"MEDIUM — worst of 4 inputs: geospatial MEDIUM (IMBL proxy boundary, not treaty line)."* The `rationale` string is already carried on every `Confidence` object and is currently thrown away at the UI boundary. And delete the score ring.
- **Accept:** a judge clicks the confidence tier and sees which agent dragged it down and why, in one line. You can state truthfully: *"no language model anywhere in this system emits a confidence value — it is a worst-tier composition, and here is the arithmetic."*
- **Effort:** 0.5 day.

### R-JUDGE-5 — Persona personalization must go far beyond the navbar

The judge is partially right and partially working from an outdated view — resolve it with facts:

- **What already exists beyond the navbar:** `PersonaAnswerMatrix.tsx` genuinely restructures the answer per persona — fisherman gets a plain-language distance line plus a "Why this answer?" disclosure; commercial navigator gets a navigation readout grid; researcher gets three grouped statistical sections plus CSV/JSON export; coastal authority gets a district threat level and a CAP payload preview. There is also a live `PersonaCorrection` control that re-renders an already-computed answer under a different persona **without re-querying**. That is real, and it is more than most teams build.
- **What the judge is correctly reacting to:** everything *outside* the answer card is persona-blind. `persona/config.ts` is explicitly and only a **nav visibility matrix** — its own header says so ("nav visibility is a rendering concern only, never a capability gate"). The map defaults, the chart complexity, the input affordances, the density, the typography, and the landing surface are identical for a non-literate fisherman on a phone at sea and a researcher at a desk.
- **Required — aggressive personalization, in priority order:**
  1. **Fisherman:** voice-first layout (mic is the primary control, not a sibling of a text box), one map pin and no layer stack, ≥18px body text, maximum contrast for sunlight legibility, and no jargon anywhere. This persona should look like a different application, not a filtered one.
  2. **Commercial navigator:** open on `/voyage`, not `/ask`. Waypoint table and draft/UKC front and centre. Units in nm/knots throughout.
  3. **Researcher:** data density is a feature — multi-layer map on by default, time-series charts expanded, export always visible, raw JSON one click away.
  4. **Coastal authority:** open on `/ops`. District roll-up first, individual query second. CAP builder promoted from preview to primary.
  5. Per-persona **map defaults** (`initialLayers`) and **chart complexity**, driven from one extension of the existing config table — not scattered conditionals, matching the pattern already established in `persona/config.ts`.
- **Accept:** a judge switches persona and the **entire screen** changes — layout, density, default map layers, primary call to action — not just the nav rail and the answer card. Screenshot the four side by side; they should be unmistakably different products.
- **Effort:** 2 days. This is the largest single UI item in this document and it directly answers a judge who has already told you what he will look for a second time.

---

## 5. Agentic collaboration — the section that decides the PS

The PS asks for *"autonomous collaboration among agents."* Both audits converged on the same verdict from different evidence: **ORCA is a genuine multi-agent system with a static topology, not an agentic one.** Fan-in is state merging; agents never see each other's work mid-flight; only the Critic loops, and only on DEEP.

The goal is **not** to rebuild as a free-roaming agent swarm. A compiled graph with a deterministic safety core is the *correct* architecture for a life-safety product, and the external audit is right that fixed-decomposition orchestration is the current reference pattern for narrow domains with parallel sub-tasks. The goal is to add the **three specific collaboration behaviours** whose absence is currently visible, without surrendering determinism.

### R-AGENT-1 — Make the Critic real, unconditional, and visible

- **Now:** `critic.py` is a genuine LLM-as-judge loop with `MAX_ITERATIONS = 3`, a 5-item rubric, and a verdict-header preservation guard that reverts any revision altering `^(GO|CAUTION|NO_GO):`. It also builds a deterministic `_REINVOKE_MAP` naming which agent should be re-run — **and then never re-invokes it.** Worse, it only runs when `reasoning_depth == DEEP` (`graph.py:411`), so on a default demo query **the verification loop does not execute at all**.
- **Required:**
  1. Run the Critic on **every** query. It is the PS's "agent verifying the work" and it cannot be conditional. If latency is the concern, run it in a cheap tier and stream its result after the answer — the SSE stream already flushes per step, and `graph.py:406-411` documents that the verdict frame lands before the critique frame anyway.
  2. **Honour `_REINVOKE_MAP`.** When the Critic identifies a specific agent as the source of a deficiency, actually re-invoke that agent with the critique attached, then re-synthesize. Cap at one re-invocation to bound latency. This is the difference between a proofreader and a collaborator, and it is the single change that most upgrades ORCA's agentic standing.
  3. Emit the critique as a visible span: *"Critic: reporting omitted the tide citation → re-invoked ocean_analytics → citation added (iteration 1/3)."*
- **Accept:** on an ordinary, unrehearsed query a judge sees the Critic run, find something, cause another agent to re-run, and improve the answer. Have one reliable scenario where it demonstrably changes the output.
- **Effort:** 1.5 days. **Do this before anything in §6.**

### R-AGENT-2 — Promote Discovery to a real graph node

- **Now:** the most genuinely agentic component in the system is not an agent. `discovery.py` makes real runtime source decisions with narrated rationale, and `graph.py:171-176` smuggles the output out as a field on Ocean Analytics' result.
- **Required:** a `marine_data_discovery` node running **before** the fan-out, whose output (chosen sources per data type, with rationale) is consumed by the three specialists rather than each fetching independently. This is the PS's named "marine data discovery" agent and it is the only structural change that makes the fan-out genuinely *planned* rather than merely parallel.
- **Accept:** the trace shows Discovery executing first with its own latency, and its narrative names a rejected source and the reason. Kill one source in front of the judge and watch the cascade choose the fallback and say so.
- **Effort:** 1 day.

### R-AGENT-3 — Cross-agent reconciliation (see R-PS-5)

The other half of "collaboration": agents whose outputs are checked *against each other*, deterministically, before synthesis. Specified in R-PS-5. Architecturally this belongs as a small step inside `risk_assessment` (which already reads both weather and geospatial) plus a new field on the response.

### R-AGENT-4 — Settle the agent count and change the claim

Both audits flagged the "10 agents" framing as the weakest defensible claim, and the external audit found three first-party artifacts disagreeing with a fourth. Pick one number, footnote it once, and **stop leading with it**.

**Lead with this instead — it is true, verifiable in ten seconds, and far more memorable:**

> *"Six of our eleven graph nodes contain no AI at all — including every node that can stop someone from going to sea. The language model writes the explanation. It is structurally forbidden from writing the verdict, and our CI fails the build if anyone tries."*

That claim is backed by `risk_assessment.py` having no LLM import, `critic.py`'s header guard, and `scripts/verify_ci_guards.py`. Show the CI guard failing on a deliberately broken branch if you want the room silent.

---

## 6. Consolidated requirements from both audits

Deduplicated. Where the two audits overlapped, the sharper diagnosis is kept.

### R-SCI-1 — Revive SST/chlorophyll from data already on disk

- **Now:** `correlate_sst_chlorophyll()` returns `{"available": False, "note": "awaiting D3 gridded loader fixtures…"}` on every call, because `analytics_loaders.py` bails at `if not OCEAN_FIXTURE_DIR.is_dir()` and **`data/fixtures/` does not exist**. Meanwhile `README.md:389` advertises PFZ "from SST + chlorophyll", and ~212 MB of MOSDAC chlorophyll `.nc` + INSAT-3DR SST `.h5` sit in `data/` with zero readers.
- **Required:** a parser that reads the on-disk OCM-3 `.nc` and INSAT-3DR L3B `.h5`, subsets to the pilot bbox, and emits `mosdac_sst__pilot__*.json` / `mosdac_chl__pilot__*.json` into a new `data/fixtures/`. `xarray` and `h5py` are already dependencies. **`data/` stays gitignored — the fixtures are generated by the script, never committed.**
- **Why this outranks its old P2 rating:** it closes the only real claim-vs-code gap, and it converts "our only live data source is a European weather API on a Department of Space PS" into "we read ISRO EOS-06 OCM-3 and INSAT-3DR products from native product files."
- **Accept:** a query returns a real SST/chlorophyll correlation with an ISRO product named in the citation.
- **Effort:** 0.5–1 day. Budget the first hour for L3B scale factors and fill values — expect everything to read as 65535 until they're applied.

### R-ROUTE-1 — Earn the word "optimization", and put routing inside the graph

- **Now:** `voyage.py` does genuinely good work — 2 nm densification, per-leg evaluation **at each leg's ETA** (not against current conditions, which is the mistake most teams make), draft + 2.0 m margin against GEBCO, MPA/IMBL checks along the path, worst-case rollup. But it generates exactly **three fixed candidates** (`offset_east`, `offset_west`, `wait_6h` — and the third is a schedule change, not a route), and the file states it is **"Not a LangGraph node."**
- **Required, in order:**
  1. **Rename honestly everywhere** to "constraint-checked voyage planning with alternatives" until (2) ships. `README.md:302` currently says "bathymetry-aware route optimization".
  2. **A\* over a coarse GEBCO grid**, with depth < draft+margin, MPA polygons, and the IMBL buffer as an impassability mask, and a cost function over distance + forecast wave height at ETA. ~150 lines, and it makes "optimization" true.
  3. **Bring it into the graph** as a plan-gated node so the navigator persona's core capability is part of the agentic story rather than adjacent to it.
- **Accept:** a judge names a start and end that require detouring around a shallow bank; the route bends around it, the blocked direct path is shown, and the cost difference is stated.
- **Effort:** 2 days for all three.

### R-SAFE-1 — Staleness ceiling

- **Now:** freshness metadata is carried on every `SourceProvenance`, but nothing forces a verdict downgrade on stale data. A cached "calm seas" fixture from three weeks ago can still produce a confident GO.
- **Required:** `if freshness_minutes > threshold: floor verdict to CAUTION and name the stale source`. The mechanism already exists — `safety_floor_for_missing_inputs` in `resilience.py` does exactly this shape for missing inputs; extend it to stale ones.
- **Accept:** back-date a fixture and watch GO become CAUTION with the stale dataset named.
- **Effort:** 1 hour. Best safety-value-per-line remaining.

### R-SAFE-2 — Distress phrase coverage

- **Now:** `distress.py`'s own docstring calls this *"the single highest-consequence piece of unverified content in the whole build"* — five languages, dictionary-checked, **no native-speaker review of any list**, and Tamil has **4 phrases**. The handoff is correctly tagged `"status": "SIMULATED"`.
- **Required:** (a) one native Tamil speaker expands the list to 25–30 phrases including colloquial and dialect forms; (b) the SOS button remains always-visible and always-functional independent of text detection; (c) a low-confidence ASR transcript containing any distress-adjacent token routes to a "Did you mean SOS?" confirmation rather than to normal query handling.
- **Accept:** a native speaker's unprompted distress phrasing triggers detection.
- **Effort:** 2–3 hours plus reviewer access.

### R-VOICE-1 — Whisper on GPU

- **Now:** `faster-whisper` `small`, `device="cpu"`, `compute_type="int8"`, justified in-code by "this machine has no CUDA device" — which is **no longer true of the current development machine**.
- **Required:** `WhisperModel("large-v3", device="cuda", compute_type="float16")`. Two lines, and it materially improves Tamil recognition — the demo moment judges remember.
- **Accept:** unrehearsed Tamil speech transcribes correctly on the first attempt.
- **Effort:** 15 minutes plus model download.

### R-CLAIM-1 — Fix the three false README claims

`README.md:418` says "Bhashini ASR → Whisper (fallback)" — Bhashini raises `NotImplementedError` even with credentials present. `README.md:419` says "Google Cloud TTS fallback" — the actual backend is `facebook/mms-tts` VITS. `README.md:109` claims ten languages of voice — TTS is verified for four. Rewrite as: *"Bhashini integration seam prepared; IndicTrans2 + Whisper + MMS-TTS are the active local stack. 10 languages detected, 4 with verified voice output."* **A judge who catches one wrong claim discounts the other twenty.** 30 minutes.

### R-HYGIENE-1 — Repo and demo hygiene

- Resolve `p1.png`/`p2.png`/`p3.png` at repo root (terminal-green UI, Mumbai region, **"API KEY REQUIRED" watermarks**, unreferenced by the README). Delete or move to `docs/archive/`. Independently, **verify the basemap key is licensed and loaded on the demo machine** — a watermarked map during judging is a self-inflicted kill shot.
- Fix the legend text clipping and cut edge labels visible in `assets/orca4.png`.
- Delete `check_early_exit()` (`planning.py:187-193`, returns `False` unconditionally) or implement it. A stub function is free ammunition.
- Hide `/design` and `/login` from the nav for the demo. Thirteen routes where nine are polished scores worse than nine routes where nine are polished.

### R-DEMO-1 — Capture the missing visuals

Every existing screenshot is a green GO. Capture and keep on a hotkey: a **NO_GO** verdict, a **depth-blocked route with detour**, the **cloud-cover sector** tile, and the **cross-source disagreement** state from R-PS-5.

### R-DEMO-2 — Offline rehearsal and warm start

One live network dependency exists in the entire backend (`weather_intelligence.py`, the only `httpx` consumer). Run the full demo with the network off the night before and confirm the fallback path renders identically. Pre-warm IndicTrans2 and Whisper on startup — they lazy-load, and a 40-second first-query stall destroys a six-minute demo.

### R-DEMO-3 — The honesty discipline

The one genuinely excellent idea in the external audit's P0 block, translated from a slide into speech. Volunteer, before anyone asks: the DAT-SG handoff is **simulated**; Bhashini is a **prepared seam**, not a connection; SMS needs **DLT template registration**, which is a government process rather than a code change; IMBL is an **EEZ proxy** capped at MEDIUM. A team that discloses its own limits is trusted on everything else it claims. A team caught hiding one is trusted on nothing.

---

## 7. Gaps neither audit named

Added because, as you said, everyone misses things.

### R-NEW-1 — The system has no idea when it is wrong about *where*

`session.py`'s `_REAL_PLACE_SOURCES` allowlist prevents a follow-up from inheriting a default location — good. But when no place is resolvable at all, the API picks a regional default and the answer is narrated confidently for that place. A fisherman in Kanyakumari reading an answer computed for Thoothukudi has been actively misled. **Required:** when `place_source` is a fallback, say so on the card — *"No location in your question; showing Thoothukudi. Not your position? Set it here."* 2 hours, and it closes the most realistic real-world harm path in the product.

### R-NEW-2 — A GO with no fishing zone is an incomplete answer

"Is it worth going out?" ≠ "is it safe?". Today a GO verdict with SEC006 cloud-suppressed and the nearest PFZ **181.7 km away** (visible in `assets/orca3.png`) is technically correct and practically useless. **Required:** an explicit rendering — *"Safe to sail. But no fishing advisory for your sector today (cloud cover), and the nearest is 181 km — not a day trip."* Safe and worthwhile are different questions and the product currently answers only one.

### R-NEW-3 — Nothing proves the LLM is optional

The strongest claim in the project is that safety doesn't depend on AI. Nothing demonstrates it. **Required:** a demo toggle that disables every LLM provider and re-runs the query. The verdict, the thresholds, the geofence, the citations and the confidence all still render; only the prose narration degrades to the deterministic line. **This is a 20-second demo beat that no competing team can match**, and it turns an architectural argument into something the room watches happen.

### R-NEW-4 — Latency is a claim with no evidence

The external audit could not verify the "≤3 sec safety verdict" figure. **Required:** show per-agent latency in the trace (the SSE span already carries `latency_ms` — it is emitted at `main.py:284` and under-used in the UI) and a total. Free, since the data already flows.

### R-NEW-5 — Personas are renderings, not workflows

Flagged in the code-forensic audit and worth restating as a requirement because it is the gap between "finalist" and "deployable". A coastal authority's real workflow is *receive → validate → approve → broadcast → log*; ORCA renders a CAP payload and stops. There is not time to close this. There **is** time to name it as roadmap on the last slide, which converts a weakness into demonstrated product maturity.

### R-NEW-6 — Accessibility as a safety feature

`VerdictBadge.tsx` already respects `useReducedMotion` and uses `role="status"` so a verdict is announced rather than only painted — someone thought about this. Extend the same care to the fisherman persona under R-JUDGE-5: sunlight contrast, large tap targets, and full voice operability without reading. For this user base accessibility is not compliance, it is the difference between an alert being acted on and an alert being missed.

---

## 8. Priority and sequencing

Ordered by *judge-visible impact per hour*, not by difficulty.

### Tier 1 — The chatbot and its agents (do first, ~6 days)

| ID | Item | Effort |
|---|---|---|
| R-JUDGE-1 | Engine tag on every span, IndicTrans2 on ingress **and** egress | 2 h |
| R-JUDGE-2 | Verdict shown only when warranted; delete the fabricated score ring | 0.5 d |
| R-JUDGE-4 | Confidence derivation made visible | 0.5 d |
| R-AGENT-1 | Critic on every query, with real re-invocation | 1.5 d |
| R-JUDGE-3 | Multi-intent routing made real and visible | 1 d |
| R-PS-5 / R-AGENT-3 | Cross-source disagreement detection | 1 d |
| R-AGENT-2 | Discovery promoted to a graph node | 1 d |
| R-PS-3 | Session history feeds intent classification | 0.5 d |
| R-AGENT-4 | Change the headline claim | 1 h |

### Tier 2 — Credibility and the remaining PS clauses (~5 days)

`R-JUDGE-5` (aggressive persona UI, 2 d) · `R-SCI-1` (revive SST/chl, 1 d) · `R-ROUTE-1` steps 1–2 (rename + A\*, 1.5 d) · `R-PS-1` (intent robustness, 1 d) · `R-PS-7` (localized alerts, 0.5 d) · `R-PS-8` (draw the IMBL line, 1 d) · `R-SAFE-1` (staleness ceiling, 1 h) · `R-CLAIM-1` (README, 30 min) · `R-VOICE-1` (GPU Whisper, 15 min)

### Tier 3 — Polish, safety margin, and demo (~2 days)

`R-SAFE-2` (Tamil distress phrases) · `R-NEW-1` (location honesty) · `R-NEW-2` (safe ≠ worthwhile) · `R-NEW-3` (LLM-off toggle) · `R-NEW-4` (latency display) · `R-HYGIENE-1` · `R-DEMO-1/2/3` · `R-PS-2` (romanized Indic) · `R-PS-6` (charts) · `R-PS-10` (plain-language reasoning)

### Tier 4 — PWA (last, by design)

§9. Deliberately last: it adds no PS-clause coverage and is pure upside once everything above holds.

---

## 9. PWA — Progressive Web App (do this last)

### Why it is worth doing at all

The PS never asks for offline capability, and the external audit correctly advises keeping the offline story to one line so it doesn't crowd out explicit requirements. But for **this** user base the argument writes itself: a fisherman 20 km offshore has no connectivity, and the moment they most need the last verdict is the moment they cannot fetch it. "Installable, works with the network off" is a 30-second demo beat that reframes ORCA from a website into a device.

Treat it as a **bounded, one-day addition with a scripted demo beat**, not as an architecture project. If Tier 1–3 are not finished, do not start this.

### Current state

No manifest, no service worker, no offline handling. `frontend/public/` contains only default Next.js SVGs, `orca-chart-style.json`, and the MapLibre worker bundles. `frontend/next.config.ts` exists and is unmodified for PWA purposes.

### Implementation

**Do not add a PWA plugin.** Next 16's App Router has native manifest support, and the offline surface ORCA needs is small enough that a hand-written service worker is both shorter and far less likely to break against a framework version a plugin hasn't caught up to. This is also the honest answer if a judge asks how it works.

**Step 1 — Manifest (native, ~20 lines).** Create `frontend/app/manifest.ts` exporting a `MetadataRoute.Manifest`: `name: "ORCA — Marine Intelligence"`, `short_name: "ORCA"`, `display: "standalone"`, `start_url: "/ask"`, `orientation: "portrait"`, background and theme colours matching the ECDIS palette already in the design tokens, and 192/512 px maskable icons. Next serves this at `/manifest.webmanifest` and links it automatically — no `next.config.ts` change and no `<link>` tag needed.

**Step 2 — Service worker (~60 lines, `frontend/public/sw.js`).** Three cache strategies, chosen per resource class:

| Resource | Strategy | Reason |
|---|---|---|
| App shell (HTML, JS, CSS, fonts, icons) | **Cache-first**, versioned cache name | The UI must open instantly with no network |
| Map tiles and the MapLibre worker bundles | **Stale-while-revalidate**, capped entry count | Tiles are large and change rarely; an LRU cap keeps storage bounded |
| `/query`, `/render` and all API calls | **Network-first with cache fallback** | A stale safety verdict must never win over a fresh one |

The network-first rule on API calls is the safety-critical part and is non-negotiable: cached marine data is only ever a fallback, never a preference.

**Step 3 — Register it.** A small client component in `frontend/app/layout.tsx` that calls `navigator.serviceWorker.register("/sw.js")` inside a `useEffect`, guarded on `"serviceWorker" in navigator`. Register on load, not on interaction.

**Step 4 — Offline UX (the part that actually earns points).** A service worker alone is invisible. What a judge sees must be:

- A persistent **offline banner** when `navigator.onLine` is false: *"Offline — showing the last verdict from 14:20, 38 minutes ago."*
- The **last successful verdict persisted to IndexedDB** (or `localStorage` — the payload is a few KB, so don't over-build), with its original timestamp and confidence, rendered read-only.
- **Ageing that degrades honestly.** This is where the PWA connects to the safety architecture rather than sitting beside it: a cached verdict is subject to the same staleness ceiling as R-SAFE-1. Past the threshold it must stop presenting as a verdict and become *"This reading is 4 hours old. Do not rely on it. Seek a current advisory."* An offline GO that silently ages into a lie is worse than no offline mode at all.
- **The install prompt**, captured from `beforeinstallprompt` and offered as a quiet "Install ORCA" affordance rather than a modal.

**Step 5 — Do not build** background sync, push notifications, or offline write queues. They need a push service, server keys and permission flows, and none of it is demonstrable in the time available. Say it is the roadmap.

### The demo beat

Load a verdict → turn on airplane mode in front of the judges → the app still opens, still shows the verdict, and honestly labels it as cached and ageing. Thirty seconds, and it lands the product thesis harder than any slide: **a system built on the assumption that its data will be missing.**

### Acceptance

- Lighthouse PWA audit passes and the app is installable on Android Chrome.
- With the network disabled, `/ask` opens, renders the last verdict, and shows the offline banner with a real timestamp.
- A cached verdict past the staleness threshold refuses to present itself as current.
- Effort: **1 day**, including the demo rehearsal.

---

## 10. Definition of done

ORCA is Grand-Finale-ready when all of the following are true at once:

1. A judge types **five unrehearsed queries**, including one in Tamil and one code-mixed, and all five return correct, evidenced, correctly-routed answers.
2. A **multi-intent** query visibly dispatches more agents than a simple one, and the response addresses both intents.
3. The **Critic runs on an ordinary query**, finds something, causes another agent to re-run, and improves the answer — visibly.
4. Two sources **disagree** and the system says so, takes the conservative value, and lowers its confidence.
5. **IndicTrans2 is named on both the ingress and the egress span**; the safety span reads `Deterministic`.
6. No **GO banner** appears on a question that didn't ask about safety — and a CAUTION or NO_GO leads regardless of what was asked.
7. **No number on screen is unexplainable.** Every confidence tier can be traced to the agent that set it.
8. Switching persona **changes the entire screen**, not the nav rail.
9. Every LLM provider can be **switched off** and the safety verdict still renders.
10. The whole demo runs **with the network disconnected**, and the app is installable and honest about staleness when offline.

Ten for ten is a PS winner. The current state passes three.

---

*Compiled from the ORCA code-forensic judge verdict, the external Grand Finale judge audit (corrected per §1), the verbatim PS 26176 capability list, and the internal-round judge's flags. Every "Now" statement in this document was verified against the working tree, not inferred from documentation.*
