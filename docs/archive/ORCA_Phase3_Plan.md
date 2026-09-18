# 🎙️ ORCA — Phase 3 Execution Plan (Days 15–21)

> **Parent plan:** [`ORCA_Implementation_Plan.md`](./ORCA_Implementation_Plan.md) · **Design authority:** [`ORCA_Agentic_Architecture_final.md`](./ORCA_Agentic_Architecture_final.md) · **Predecessor:** [`ORCA_Phase2_Plan.md`](./ORCA_Phase2_Plan.md)
> **Duration:** 7 working days · **Team: 3, all full-stack** · **Precondition:** Phase 2 is closed — all eight PS queries answer, auth and vessels are live, `audit_trace_log` is in Postgres, the map explorer paints real layers, and the §0 verification gate below is green.
>
> **This is the week the demo is won or lost.** Parent §6 calls Phase 3 "the capabilities that separate ORCA from a RAG chatbot". Nothing in the parent plan's Phase 3 list is cut, deferred or compressed here. Two Phase-4 items are pulled *forward* (§7), because they become nearly free once the reasoning graph replays a stored trace and cost more later than they do now.
>
> **The standing rule for this phase:** the UI is not a wrapper around the agents, it is the evidence that the agents exist. Every item below has a visible surface, and an item is not done when the backend returns the right JSON — it is done when a judge can see it happen.

---

## 0. Phase 2 Verification Gate — Day 15, 09:00, all three

Phase 3 assumes ten Phase-2 exit criteria hold. Phase 3 builds *on top of* every one of them, so a Phase-2 regression discovered on Day 20 costs a day of the most valuable week in the project. **This gate is run once, live, together, before any Phase 3 code is written**, against the merged `main` — not against anyone's branch and not from memory.

| # | Phase 2 exit criterion | How it is verified at the gate | Depended on by |
|---|---|---|---|
| 1 | All 8 PS queries return substantive answers | Run all eight live, one recorded run each | Everything |
| 2 | Researcher export produces a valid CSV with full metadata | Open the file; every column carries dataset + acquisition timestamp | D1 personas |
| 3 | Multi-intent visibly activates the union of agents | Activity strip + `audit_trace_log` | D3 reasoning graph fan-out |
| 4 | Two accounts, no cross-read, refusal audited | Two logins, one 403, one audit row | D2 Sentinel subscribers |
| 5 | Killed INCOIS yields a degraded answer naming the rung | E2E degradation variant in CI | D1 Critic, D2 alerts |
| 6 | Time slider walks 56 frames with zero agent invocations | Network panel empty of `/query` | D3 flow overlay |
| 7 | `audit_trace_log` rows are in Postgres | `SELECT * FROM audit_trace_log WHERE query_id = …` | **D3 reasoning graph replay — hard blocker** |
| 8 | Every `MapLayer` / `ChartSpec` passed `validate_payload` | Reject-path test green | D3 new layer types |
| 9 | Containment still runs on full-precision geometry | The simplification assertion test | D3 voyage corridor |
| 10 | All 3 slices merged, CI green | `git log main`, CI run | Everything |

**Plus a frontend walk, in a real browser, not a screenshot:** every route in §4.2 of the parent plan (`/`, `/safety`, `/map`, `/zones`, `/trends`, `/data`, `/ops`, `/watches`, `/reasoning`, `/voyage`, `/design`) is opened, in both the desktop rail and the mobile tab bar, on each of the four personas plus `unresolved`. What is being checked is not "does it load" but: the persona visibility matrix is honoured, a hidden route is still reachable by direct URL, every number opens its provenance popover, the safety triad still out-contrasts everything else on screen, and no surface has drifted off the design tokens. `/design` is walked first because it makes the rest mechanical.

**If anything fails, it is fixed before Phase 3 work starts, by whoever owns it, that morning.** A failing gate item is the standup's only topic. Phase 3 has no slack to absorb Phase 2 debt, and the differentiators are all *visible on top of* Phase 2 surfaces — a persona correction that re-renders a broken answer card demonstrates nothing.

---

## 1. Slice Partition — D1–D3 continue, re-labelled

The three lanes from Phase 2 carry forward with the same owners. Phase 3's work does not naturally divide the same way Phase 2's did, so the lanes are re-labelled — but they are not re-shuffled, because each Phase 3 item lands on a surface or a subsystem its Phase 2 owner already built.

| New | Name | Continues | Agents owned | Surfaces owned | Shared concerns owned |
|---|---|---|---|---|---|
| **D1** | **Language, Voice, Personas & Critic** *(lead)* | D1 (platform, identity, synthesis) | 1 User Interaction (full) · 9 Reporting (personas) · **10 Critic** | `/` voice + answer card, persona system, persona-correction control | Contracts, trace-replay API, channel renderers, streaming polish, a11y CI gate, CI |
| **D2** | **Sentinel, Alerting, Feedback & District Ops** | D2 (ocean + analytic surfaces) | **11 Sentinel** | `/watches`, `/ops`, notification feed, advisory-feedback controls | `Dispatcher` layer, alert schema, `002` migration, aggregation rules |
| **D3** | **Reasoning Graph, Voyage & Flow Fields** | D3 (geospatial, viz, map) | 6 Geospatial (route extensions) · 8 Visualization (new layer types) | `/reasoning`, `/voyage`, `/map` additions | React Flow graph component, deck.gl overlay, map layer registry |

**Why these three and not others:**

- **D1 keeps the whole "how the answer reaches a human" chain.** Parent §7 put Reporting, Critic and User Interaction in one slice for a reason: Reporting synthesises, Critic validates what Reporting wrote, and User Interaction translates it out. Splitting them puts a handoff inside a feedback loop. D1 already owns Agent 9 and the response contract from Phase 2, so voice, personas and the Critic land on code they wrote.
- **D2 takes Sentinel because Sentinel is an analytic loop, not a new domain.** It reuses Agent 4's and Agent 7's tool interfaces on a schedule — and D2 spent Phase 2 building the analytic surfaces that read those tools. `/ops` is a rollup of the same numbers `/trends` already renders, and parent §4.10 explicitly puts feedback surfacing on the analytic cards (S4 = D2).
- **D3 takes the reasoning graph even though parent §4.4 names S1 as the owner.** The split is at the payload boundary: **D1 owns the trace payload and the replay API** (it owns the trace pipeline), **D3 renders it**. D3 spent two phases building visual systems on real payloads, and the reasoning graph is the single most-scrutinised screen in the product. Voyage and the flow overlay sit on D3's map for the same reason they always did.

**The load is deliberately uneven again.** D1's week is evenly loaded but has the most distinct subsystems (four). D2's is back-loaded — `/ops` is the largest single surface and it cannot be composed until Sentinel produces alerts to roll up. D3's is front-loaded — the reasoning graph consumes three days starting Day 15, because parent §6 says it "gets a whole slice-week, not an afternoon", and because everything else D3 owns is additive to a working map.

---

## 2. Tech Stack — Phase 3 additions

Everything from Phase 0–2 stays. These are the additions, each a decision with a reason.

### Frontend

| Concern | Package | Status | Why this one |
|---|---|---|---|
| Reasoning DAG | `@xyflow/react` | ✅ installed | Pan/zoom, custom nodes, edge routing and selection are exactly what we would hand-roll badly |
| DAG layout | `dagre` | 🆕 install | Left-to-right by execution depth, computed **once per trace and cached** — the graph does not re-layout on every SSE frame |
| Flow fields | `@deck.gl/core` + `@deck.gl/mapbox` | 🆕 install | Animated wind/current vectors as an overlay on the existing MapLibre instance. It does not replace a single MapLibre layer |
| Motion | `framer-motion` | ✅ installed | Node pulses, in-flight edges, persona crossfade. All `prefers-reduced-motion` gated — motion is never the sole carrier of state |
| Voice capture | native `MediaRecorder` + Web Audio API | platform | A recorder library buys nothing over 30 lines. Opus/WebM blob to the backend; Web Audio drives the live waveform |
| A11y CI | `@axe-core/playwright` | 🆕 install | Per-flow assertions in the existing Playwright E2E run. `@axe-core/cli` already covers `/design`; the six named flows need in-browser state |
| Charts / map / icons | `recharts`, `maplibre-gl`, `lucide-react` | ✅ installed | Unchanged |

```bash
cd frontend
npm install dagre @deck.gl/core @deck.gl/mapbox
npm install -D @axe-core/playwright @types/dagre
```

### Backend (`backend/.venv`, Python)

| Concern | Choice | Why this one |
|---|---|---|
| **ASR** | Bhashini/ULCA ASR → **`faster-whisper` large-v3 on CUDA** | Bhashini access is **pending** (`.env.example` says so). The local GPU path is therefore the *primary* and Bhashini is registered behind the same interface as a drop-in. A demo that depends on a credential we do not have is not a demo |
| **NMT** | Bhashini NMT → **IndicTrans2 (CT2/HF, CUDA)**, English-pivot both directions | Same interface, same fallback order. English pivot is what makes 10 languages a config list rather than 90 language pairs |
| **TTS** | Bhashini TTS → **`facebook/mms-tts-<lang>` local** → Google Cloud TTS | Three rungs, declared. MMS covers all ten target languages offline on the GPU |
| **Voice model host** | The CUDA machine, models warm at process start | Cold-loading large-v3 mid-demo is a 20-second silence |
| **Sentinel scheduler** | `APScheduler` `AsyncIOScheduler`, in-process, single-instance advisory lock | Celery + a broker is a second deployable for one periodic job. `ponytail:` single process — move to a worker if the loop and the API ever contend |
| **Dispatch** | `Dispatcher` protocol · `InAppDispatcher` ships · `SMSDispatcher`/`IVRDispatcher` raise `NotImplementedError` | Parent §4.9 verbatim. Nothing anywhere claims a message was delivered when it was rendered |
| **Critic** | LLM-as-judge at the `reasoning` tier via the existing `orca/llm/registry.py` | Model-agnostic by construction; no vendor SDK enters `orca/agents/` |
| **Voyage corridor** | `pyproj` geodesic densify + `shapely` STRtree containment over the existing GEBCO / WW3 / boundary loaders | Deterministic, no LLM, milliseconds. A\* is out of scope — not a stretch goal (parent §4.6) |
| **Migrations** | raw SQL `infra/db/002_notifications.sql`, matching `001` | No Alembic while there are no ORM-as-source-of-truth models (parent §5.3) |

**Already in the schema, needs ORM models only:** `sentinel_subscriptions`, `advisory_feedback`. **New in `002`:** `notifications` (the in-app feed), plus the `notification_status` enum.

**What is *not* being added:** no state-management library, no WebSocket layer (SSE already carries the stream), no queue, no second database, no chart library beyond Recharts, no UI kit. Every one of those would be a new dependency where an installed one already does the job.

---

## 3. The Objective

By end of Day 21, ORCA stops being a very good multi-agent answer engine and starts being visibly one — and it speaks, watches, checks itself, and routes a boat.

Seven differentiators from parent §4.5, and the phase each lands in. Phase 3 lands five of them:

| # | Differentiator | Phase | Owner |
|---|---|---|---|
| 1 | Live agent activity strip during execution | 1 → **3** (full) | D1 payload, D3 render |
| 2 | **Full reasoning DAG with per-node provenance drill-down** | **3** | D3 |
| 3 | Click any number → provenance popover | ✅ 2 | — |
| 4 | Source-selection narration | ✅ 2 | — |
| 5 | **Visible Critic self-correction** | 4 → **pulled into 3** (§7) | D1 + D3 |
| 6 | **Sentinel watch badges live on the map** | **3** | D2 + D3 |
| 7 | **Persona correction re-renders instantly, no re-query** | **3** | D1 |

Plus the capabilities that are not differentiators but are named PS requirements Phase 3 finally closes: **voice in and out**, **all ten coastal languages**, **PS query #6 (safest route A → B)**, **proactive push alerting**, and **WCAG 2.1 AA verified rather than assumed**.

---

## 4. Exit Criteria

Phase 3 is done when all fourteen hold. The first six are parent §6's Phase 3 exit criteria verbatim; the rest are what this partition and the §7 pull-forward add.

| # | Criterion | Verified by |
|---|---|---|
| 1 | A Tamil **voice** query works end to end — spoken in, spoken out | Recorded run, audio both directions |
| 2 | Sentinel fires a real threshold crossing to a **registered** subscriber | Move a fixture threshold; the notification lands and the audit row says `SIMULATED` |
| 3 | Persona correction re-renders with **zero re-query** | Network panel shows no `/query`; the numbers are byte-identical |
| 4 | The reasoning graph renders a real multi-agent trace **including one parallel fan-out and one Critic loop**, every node stating that agent's reasoning and its sources | Live run, then replay of the same `query_id` |
| 5 | All six named flows complete **keyboard-only with a screen reader** | NVDA pass, recorded; `axe-core` zero criticals in CI |
| 6 | A flagged advisory resolves to its full agent trace by `query_id` | Click "Not accurate" → open trace → every source and confidence tier is there |
| 7 | All **ten** coastal languages round-trip text; the named subset also speaks | One query per language in the acceptance suite |
| 8 | A voyage with a **hard** constraint on any segment returns `NO_GO` from Agent 7, not a CAUTION | Route through the Gulf of Mannar MPA; segment is `BLOCKED`, verdict is `NO_GO` |
| 9 | The Critic **never** blocks a safety verdict | `SAFETY_CHECK` at DEEP depth: verdict emits first, critique upgrades the explanation in place afterwards |
| 10 | The `Dispatcher` is the only thing Sentinel calls — no gateway anywhere in Agent 11 | Grep + a test that a `NotImplementedError` from `SMSDispatcher` degrades rather than crashes the loop |
| 11 | Sentinel watch badges render live on the map and clear when the watch clears | Toggle a watch; the badge appears and disappears without a map remount |
| 12 | The flow overlay honours `prefers-reduced-motion` and the heavy-layer budget | Reduced motion → static vectors; a third heavy layer on mobile still evicts with a visible notice |
| 13 | The reasoning graph replays **any** historical `query_id` from Postgres, not only the live one | Replay a `query_id` from the Phase 2 acceptance run |
| 14 | All 3 slices merged to `main`, CI green including the a11y gate | Day 21 checkpoint |

---

## 5. Day-15 Deliverables Everyone Else Waits On

Four, all landing Day 15. Three contracts at 10:00 and one fixture at 12:00 — the same discipline as Phase 2 §4, for the same reason: three people carrying five subsystems means more shapes cross a person boundary than stay inside one.

### 5.1 Contract addendum — 10:00

Additive only. **Nothing in `contracts.py` or `state.py` is edited, only extended.** `ORCAState` already carries `critic_pass`, `critic_iteration_count` and `sentinel_subscription` from the Phase 1 freeze — they are populated this week, not added.

| Contract | Owner | Consumers | Shape |
|---|---|---|---|
| **`TraceGraph`** — the replay payload | D1 | D3 (`/reasoning`), D2 (feedback drill-down) | `{query_id, nodes: [{id, agent_name, depth, status, confidence_tier, latency_ms, reasoning_summary, source_count, used_llm, model, tier}], edges: [{from, to, kind: handoff\|critic_loop\|cancelled, label}], groups: [{id, node_ids, reason: "parallel_fanout"}]}` |
| **`PersonaRender`** — render-only re-render | D1 | D2 (`/ops` authority rendering), D3 (graph persona defaults) | `POST /render {query_id, persona}` → the same `AgentResult` set re-rendered. **Never re-executes an agent** |
| **`Notification` + `WatchIn/WatchOut` + `Dispatcher`** | D2 | D1 (renderers), D3 (map badges) | `Notification{id, user_id, watch_id, severity, title, body, channel, status: sent\|simulated\|failed, rendered_payload, query_id, created_at}` · `Dispatcher.send(recipient, rendered_payload, channel) -> DispatchResult` |
| **`VoyagePlan` + new `MapLayer` types** | D3 | D1 (response envelope), D2 (`/ops` route awareness) | `VoyagePlan{segments: [{index, geometry, eta, depth_m, hazards: [], classification: CLEAR\|CAUTION\|BLOCKED}], distance_nm, eta_total, hazard_summary}` · `MapLayer.type` gains `flow_field`, `route`, `watch_badge` |

If any of the four is not on `main` by 10:00, it is the standup's only topic.

### 5.2 The trace fixture — 12:00, D1 → D3

D3's most valuable three days sit on a shape D1 owns. So D1 ships a **recorded `TraceGraph` fixture first, the live API second**, and the fixture is not a toy: it contains **one parallel fan-out** (weather ∥ geospatial ∥ ocean analytics) and **one Critic loop** (a DEEP query where the Critic flagged a causal-claim issue and Reporting re-ran), because those two are exit criterion 4 and D3 cannot draw an edge kind that never appears in the data.

The live `GET /trace/{query_id}` lands end of Day 15 and must be a **drop-in swap** — same shape, same field names. If the shapes diverge, that is a D1 bug, not a D3 rewrite.

### 5.3 Design system — additions only, again

Same rule as Phase 2 §4.3: **anyone may add a primitive, nobody refactors an existing one.** Phase 3's new primitives — `AgentNode` and `TraceEdge` (D3), `VoiceButton` and `WaveformMeter` (D1), `NotificationToast` and `WatchCard` (D2), `SegmentLegend` (D3), `FeedbackControl` (D2) — are built on the existing tokens and merged like any other component.

**One addition to the rule this phase:** every new primitive lands on `/design` **in the same commit**, in every state it can be in. `/design` is where the Day-21 a11y gate runs first, and a primitive that is not on it will not be audited.

---

## 6. Slice Assignments

---

### 🎙️ D1 — Language, Voice, Personas & Critic *(lead)*

**Owns:** Agent 1 (full) · Agent 9 (persona matrix complete) · Agent 10 (Critic) · `/` voice surface · persona system · channel renderers · trace-replay API · a11y CI gate.

**Four distinct subsystems in one week.** They are ordered so that each one unblocks somebody before it is needed: the trace API on Day 15 unblocks D3's whole week, the Critic on Day 18 gives D3 real loop edges to draw on Day 19, and the renderers on Day 19 give D2's broadcast composer something to compose on Day 20.

| Day | Work |
|---|---|
| **15** | **Contracts on `main` by 10:00** (§5.1). **`TraceGraph` fixture to D3 by 12:00** (§5.2) — with a real fan-out and a real Critic loop in it. Then `GET /trace/{query_id}`: reconstruct the DAG from `audit_trace_log` in Postgres — node depth from `completed_nodes` ordering, parallel groups from overlapping span windows, edge labels from what each `AgentResult` actually handed on. `POST /render` for persona re-rendering, reading the stored `AgentResult` set and calling **only** Agent 9 — asserted in a test that no specialist agent is invoked |
| **16** | **Agent 1 ASR.** `speech_to_text` behind one interface with three rungs: Bhashini ASR (registered, credential-gated, skipped when absent) → `faster-whisper` large-v3 on CUDA → an explicit "could not hear you" that asks again rather than guessing. Models warm at process start, never lazily mid-request. `POST /voice/transcribe` taking an Opus/WebM blob + language hint, returning transcript + confidence + the rung it used. `detect_language` extended to all ten (fastText, with the ASR's own language ID as a cross-check). **A low-confidence transcript is shown to the user for confirmation before it becomes a query** — mishearing "safe" as "save" on a safety query is a safety incident, not a UX annoyance |
| **17** | **Agent 1 NMT + TTS + the voice surface.** IndicTrans2 English-pivot both directions across all ten languages, Bhashini NMT registered ahead of it; `text_to_speech` with the same three-rung pattern (Bhashini TTS → local MMS-TTS → Google Cloud TTS), `POST /voice/speak`. **Voice UI on `/`:** a push-to-talk control that is the largest touch target on the fisherman surface, a live waveform driven by Web Audio (so the user knows it is listening), the transcript rendered as editable text before submit, and TTS playback of the verdict that **auto-plays for the fisherman persona and does not for the others**. Full keyboard operation: space to record, escape to cancel, `aria-live` on the transcript |
| **18** | **Agent 10 — Critic.** The five-part rubric from Architecture §3.2 verbatim (factual consistency, temporal coherence, causal-claim strength, citation completeness, spatial accuracy), LLM-as-judge at the `reasoning` tier, `MAX_ITERATIONS = 3`, deterministic issue→agent re-invocation mapping, and the disclaimer path when it exhausts iterations. **Triggers on `reasoning_depth == DEEP` for any persona — never on persona.** The CI persona-leak guard is extended to `orca/agents/critic.py` the same day, because gating the Critic by persona is the v1.0 routing bug wearing a quality-control hat. **The safety carve-out is the load-bearing part:** if `matched_intent_rows` includes `SAFETY_CHECK`, Reporting emits the RAA-backed verdict immediately and uncritiqued, and the Critic reviews only the *explanatory* text asynchronously, upgrading it in place over SSE. Tested by asserting the verdict SSE frame precedes the critique frame |
| **19** | **Channel renderers** (parent §4.9) — `render_web`, `render_sms` (≤160 GSM-7 chars, verdict + one hazard + timestamp, vernacular), `render_ivr` (TTS script: short sentences, no numerals-as-digits, one repeat), `render_ussd` (≤182 chars, menu-structured). Each a **pure function of the same `ORCAState`** — the test is that all four render the same query and none of them fetches anything. Delivered to D2 by EOD for the Day-20 broadcast composer. GSM-7 encodability is asserted for every supported language's rendered SMS |
| **20** | **All four personas complete, plus the correction control** (differentiator 7). The §2.6 rendering matrix fully realised in the UI: fisherman banner, navigator waypoint table, researcher statistical summary with export, authority threat matrix + CAP payload. The correction control on every card — one tap, re-renders from `POST /render`, **zero re-query**, sets `stakeholder_persona_source: "explicit"`, persists for the session, logs the correction. The `unresolved` composite: fisherman-style banner + "Show technical detail". The **LOW-DATA amber treatment applied identically across all four personas** — a low confidence tier is never hidden from the fisherman. **Progressive streaming polish** (§7 pull-forward): panels populate as spans close and **the safety badge populates last, never as an optimistic placeholder** |
| **21** | **A11y gate**: `@axe-core/playwright` assertions over the six named flows (Ask, Safety, Map incl. layer toggles and the time slider, Fishing Zones, alert interaction, feedback interaction), wired into CI at zero criticals. NVDA pass on Ask and Safety personally; D2 and D3 run their own surfaces against the same harness. Integration, acceptance suite, CI green |

**Done when:** a Tamil voice query is spoken in and spoken back, a persona tap re-renders identical numbers with no network call, a DEEP query visibly loops through the Critic, a safety query at DEEP depth answers *before* the Critic runs, and all four channel renderers produce a valid payload from one `ORCAState`.

---

### 📡 D2 — Sentinel, Alerting, Feedback & District Ops

**Owns:** Agent 11 (Sentinel) · `/watches` · `/ops` · notification feed · advisory feedback · `Dispatcher` layer · `002` migration.

**Back-loaded by construction.** `/ops` is the largest surface in the phase and it is a rollup of alerts — it cannot be composed honestly until Sentinel is producing them. Days 15–17 build the engine, Days 18–20 build the two surfaces, Day 21 proves the crossing end to end.

| Day | Work |
|---|---|
| **15** | **Contracts on `main` by 10:00** (§5.1) — `Notification`, `WatchIn/WatchOut`, and the `Dispatcher` protocol. `infra/db/002_notifications.sql`: the `notifications` table and its status enum, applied the same way `001` was. SQLAlchemy models + repositories for `sentinel_subscriptions` and `advisory_feedback` (the tables exist in `001`; the models do not) and for `notifications`. **The location-sensitivity comment in `001` is honoured in the repository layer**: a watch point is a place a person goes, so it is redacted from logs by D1's Phase-2 filter and never returned across a user boundary |
| **16** | **Agent 11 core.** `AsyncIOScheduler` on a fixed interval, single-instance via a Postgres advisory lock so two processes never double-fire. `list_monitored_locations` over enabled subscriptions (home ports, vessel positions, authority watch areas). The **cheap check**: fetch the latest Agent 4 + Agent 7 outputs for that location through the *same tool interfaces the on-demand graph uses* — no duplicate logic, no second threshold table. `get_last_broadcast_verdict`, then the crossing test: `GO→CAUTION`, `CAUTION→NO_GO`, any new active hazard, any new geofence approach. **Unchanged conditions are a no-op** — no notification spam is a functional requirement, and it gets a test that a second identical poll produces zero notifications. Only a genuine crossing escalates to a full graph invocation |
| **17** | **Dispatch and the feed.** `generate_alert_payload` (Agent 7's tool, reused not re-derived) → `Dispatcher`. `InAppDispatcher` writes the notification and shows the payload verbatim; `SMSDispatcher` and `IVRDispatcher` raise `NotImplementedError` and the loop **degrades rather than crashes** — asserted. Every simulated dispatch is labelled `SIMULATED` in the UI and stored with `status='degraded'` in `audit_trace_log`. The broadcast is written into `session_history` so a later on-demand query from the same user is consistent with what they were already told — the one thing that makes proactive alerting feel like one system instead of two. Notification feed API + the toast/bell surface, `aria-live="polite"` (`assertive` for a distress-class alert). **Watch/notification feed shape to D3 by EOD** for Day-20 map badges |
| **18** | **`/watches`.** Subscription CRUD against the real schema — watch type, point or area, radius, thresholds (`{"wave_height_m": 2.5, "wind_kt": 25}`), channel preferences, enable/disable. Alert history per watch with the exact payload that was dispatched. The **fisherman variant is simplified, not crippled**: "watch my home port" is one tap with sane default thresholds, and the full threshold editor is behind "advanced" — same capability, different default surface. Home-port and vessel pickers reuse D1's Phase-2 map picker rather than a second one |
| **19** | **Advisory feedback** (parent §4.10). Helpful · Not accurate · Report issue on **every** advisory card, one tap, no dialog; "Report issue" opens an optional free-text box. On the fisherman surface: icons **with visible text labels**, placed below the verdict badge, never competing with it. `POST /feedback` writing `advisory_feedback` with `query_id`, `advisory_ref`, `session_id`, `user_id` where authenticated. **The drill-down is the feature:** a flagged advisory opens D1's `/trace/{query_id}` in D3's reasoning graph, reconstructing every agent, source and confidence tier behind it. Explicitly not built: no auto-retraining, no threshold auto-tuning |
| **20** | **`/ops` — District Ops.** The sector threat matrix (SEC001–SEC014) with severity per hazard class; the CAP payload builder producing valid CAP 1.2 XML from an alert; the broadcast composer previewing the message in **all four of D1's channel renderers side by side** before it goes anywhere; the audit trail view. **§5.5 aggregation rules are hard constraints here:** counts per sector, never plottable individual vessels — the authority sees "14 vessels in SEC004", never fourteen dots. Tested, because a demo that shows individual fishermen's positions to an authority persona is a privacy incident on stage |
| **21** | **Sentinel E2E**: move a fixture threshold, watch the crossing fire to a registered subscriber, land in the feed, render the exact Sagar-Vani SMS payload, badge the map, and write a `SIMULATED` audit row. Fixtures for every Sentinel and notification output. A11y pass on `/watches`, `/ops` and the alert + feedback flows. Integration |

**Done when:** a threshold crossing reaches a real registered subscriber unprompted, an unchanged condition produces silence, the exact SMS that would have been sent is visible and labelled `SIMULATED`, a flagged advisory opens its own full trace, and an authority sees sector counts rather than people.

---

### 🕸️ D3 — Reasoning Graph, Voyage & Flow Fields

**Owns:** `/reasoning` · `/voyage` · Agent 6 route extensions · Agent 8 new layer types · deck.gl overlay · Sentinel badges on the map.

**Front-loaded, because the reasoning graph is the screen the demo is judged on.** Days 15–17 are the graph and nothing else. It starts on D1's fixture at 12:00 on Day 15, so no day is lost waiting for the live API.

| Day | Work |
|---|---|
| **15** | **Contracts on `main` by 10:00** (§5.1) — `VoyagePlan`, `RouteSegment`, and the three new `MapLayer` types. `npm install dagre @deck.gl/core @deck.gl/mapbox`. Then the `/reasoning` skeleton against D1's fixture: React Flow mounted, `dagre` left-to-right layout by execution depth, **computed once per trace and cached** — the graph must not re-layout on every SSE frame, and there is a test that it does not |
| **16** | **Graph part 1 — the node is the deliverable.** A node is not a labelled box; it is a readable summary of that agent's reasoning: agent icon, agent number and name, confidence tier **as text and as border colour**, latency, a one-line reasoning summary (`Hs 2.4 m vs class band 2.0 m → exceeded`), and the provenance line (`3 sources · deterministic · no LLM`). Execution state in the fill: pending dim, running pulse, done, cancelled dashed, failed red + ✗. **Every channel carries information and none of it is colour alone.** Parallel fan-out drawn as a real bounding group box, so parallelism is *seen*, not inferred |
| **17** | **Graph part 2 — edges, inspector, live and replay.** Edge style carries meaning: solid = data hand-off, **dashed = Critic re-invocation loop**, dotted = early-exit cancellation; edge labels name what crossed (`verdict`, `hazards[3]`, `geofence_status`); in-flight hand-offs animate. Node click opens the **inspector drawer** with the full `AgentResult` envelope — `inputs_consumed`, `outputs`, `source_provenance` with per-source timestamps and freshness, confidence, latency, and model + tier where one was used. **Deterministic agents say "deterministic — no LLM"**, which is Ground Rule 2 made visible rather than claimed. **Live and replay are the same component**: spans arrive over SSE during a query, and the same graph re-renders any historical `query_id` from D1's API. Reduced motion: instant state changes, running state carried by a text label. The activity strip (differentiator 1) is finished as the collapsed rendering of the same stream — not a second implementation |
| **18** | **Voyage part 1 — the corridor, computed** (parent §4.6). Geodesic line via `pyproj`, densified to ~0.5 NM segments; per-segment ETA from vessel speed; **each segment evaluated at the time the vessel would actually be there, not at departure** — that is the genuinely sophisticated part and it gets its own test. Per-segment constraint sampling: GEBCO depth < draft + margin → `SHALLOW` (hard); EEZ/IMBL containment → `BOUNDARY` (hard); MPA containment → `MPA` (hard); WW3 Hs at segment ETA vs vessel-class band → `ROUGH_SEA` (soft); lightning nowcast at segment ETA → `LIGHTNING` (soft). ~2 NM corridor buffer so we warn on **approach**, not only on crossing. Classification per segment: `CLEAR | CAUTION | BLOCKED`. **Containment runs against full-precision geometry**, the Phase 2 carve-out extended to the route — asserted |
| **19** | **Voyage part 2 — `/voyage`.** Origin/destination pickers on the existing map instance, vessel draft, class and departure-time inputs, waypoints. The route polyline coloured per segment **and labelled per segment in text** (severity is never colour alone), the waypoint table with lat/long + ETA + depth + hazards, tidal berthing windows from Phase 2's tide tools, and the hazard summary. **A hard constraint on any segment makes Agent 7 return `NO_GO` for the voyage** — the geofence stays a hard constraint, and this is exit criterion 8. Soft constraints produce CAUTION overlays and never silently block. The `/reasoning` graph now has a route query to draw, which is the best possible test of both |
| **20** | **deck.gl flow overlay + the remaining Agent 8 layer types.** Animated wind and surface-current vectors as a `MapboxOverlay` on the *existing* MapLibre instance — an overlay, not a replacement, and nothing else depends on it. Budget-guarded: it counts as a heavy layer against the §4.7 concurrency limit, it honours `prefers-reduced-motion` by rendering static direction glyphs, and it is skipped entirely on the WebGL-fallback path. Agent 8 gains `flow_field`, `route` and `watch_badge` layer generation, all through `validate_payload`. **Sentinel watch badges rendered live on the map** (differentiator 6) from D2's Day-17 feed — appearing and clearing via `source.setData()`, never a map remount |
| **21** | Performance re-check with the new layers against the Phase 2 budget (layer toggle ≤ 400 ms, ≥ 45 fps panning, ≤ 2 heavy layers on mobile) — the flow overlay is the most likely thing to break it and the LRU notice must still fire. WebGL-unavailable path re-verified for the graph and the route: **a missing map is never a missing answer**, so the voyage renders as a waypoint table with the full hazard list in text. Fixtures. A11y pass on `/map`, `/voyage` and `/reasoning` — the graph is keyboard-navigable node to node, and the inspector is reachable and dismissible without a mouse. Integration |

**Done when:** the reasoning graph renders a live trace *and* replays a Phase 2 one, with a real fan-out group box and a real dashed Critic loop; a route through the Gulf of Mannar MPA comes back `BLOCKED` and `NO_GO`; the flow field animates without breaking the frame budget; and a watch badge appears on the map the moment Sentinel fires.

---

## 7. Two Items Pulled Forward From Phase 4

Everything else in parent §6's Phase 4 list stays in Phase 4. These two move, and the reason is the same for both: they cost almost nothing once the reasoning graph replays a stored trace, and they cost a rebuild if they wait.

| Item | Was | Now | Why it moves |
|---|---|---|---|
| **Visible Critic self-correction** (differentiator 5) | Phase 4 | **Phase 3 — D1 Day 18 + D3 Day 17** | It *is* a stored trace opened in the reasoning graph: draft → flagged issue → corrected answer, drawn as the dashed re-invocation edge D3 is already building. Building the graph without it means building the graph twice. It is also exit criterion 4's "one Critic loop" — the criterion already requires the data |
| **Progressive / streaming render polish** (§9.19) | Phase 4 | **Phase 3 — D1 Day 20** | The rule is "the safety badge populates **last**, never as an optimistic placeholder". That is not an optimization, it is a correctness property of the answer card, and Phase 3 is the last week the answer card changes shape. Retrofitting it after four personas ship is more work than building it into them |

**Explicitly *not* pulled forward:** Cyclone Gaja replay, the §9 optimization list (semantic cache, early-cancel, coalescing, short-circuit), circuit breakers, the real-device map budget verification, and the failure-mode rehearsal. The architecture forbids optimizing before the graph is stable, and the graph gains three agents this week.

---

## 8. Day-by-Day

| Day | D1 Language, Voice, Personas & Critic | D2 Sentinel, Alerts & Ops | D3 Reasoning Graph, Voyage & Flow |
|---|---|---|---|
| **15** | **Gate 09:00** · **Contracts 10:00** · **Trace fixture 12:00** · `/trace/{query_id}` + `/render` | **Gate 09:00** · **Contracts 10:00** · `002` migration + ORM models | **Gate 09:00** · **Contracts 10:00** · installs · graph skeleton + dagre layout |
| **16** | Agent 1 ASR (Bhashini → faster-whisper CUDA) | Agent 11 core loop + crossing detection | Graph: node anatomy, states, fan-out group |
| **17** | Agent 1 NMT + TTS + voice UI on `/` | Dispatcher + notification feed → **shape to D3 EOD** | Graph: edges, inspector, live + replay |
| **18** | **Agent 10 Critic** + safety async carve-out | `/watches` surface | Voyage corridor computation |
| **19** | Channel renderers → **to D2 EOD** | Advisory feedback + trace drill-down | `/voyage` surface + NO_GO wiring |
| **20** | Four personas + correction control + streaming polish | `/ops`: threat matrix, CAP, broadcast composer | deck.gl flow field + watch badges + Agent 8 types |
| **21** | A11y CI gate + NVDA pass + integration | Sentinel E2E + fixtures + a11y | Perf + WebGL fallback + fixtures + a11y |

**Five cross-slice dependencies, all one-directional and all named:**

1. **Day 15, 10:00 — all three → everyone.** The four contracts (§5.1).
2. **Day 15, 12:00 — D1 → D3.** The `TraceGraph` fixture with a fan-out and a Critic loop in it, so D3's three graph days start immediately.
3. **Day 17 EOD — D2 → D3.** Notification/watch feed shape, so map badges land Day 20.
4. **Day 18 EOD — D1 → D3.** Real Critic loop spans, so Day 19's dashed edge is drawn against real data rather than the fixture.
5. **Day 19 EOD — D1 → D2.** The four channel renderers, so the Day-20 broadcast composer previews real output.

Nothing else crosses a person boundary.

---

## 9. What Phase 3 Deliberately Does Not Build

| Deferred | To | Why |
|---|---|---|
| A\* / Dijkstra pathfinding | Out of scope entirely | Parent §4.6 — not a stretch goal. The per-segment classification **is** the cost surface a search would run over; the Q&A answer is written and every one of us can give it |
| A real SMS / IVR / USSD gateway | Out of scope | DLT template registration is a regulatory process, not an engineering one. Renderers ship, delivery does not, and nothing claims otherwise |
| Automatic retraining or threshold tuning from feedback | Out of scope | A fisherman disagreeing with a wave threshold is a signal to review, not an instruction to move it |
| Adaptive Sentinel polling frequency (§9.17) | Phase 4, only if ahead | Fixed polling first. Adaptive scheduling on an unproven loop is optimization before stability |
| Cyclone Gaja replay UI | Phase 4 | The data was procured in Phase 2; the replay is assembly |
| Every §9 optimization + circuit breakers | Phase 4 | The graph gains three agents this week. Optimizing it now is explicitly forbidden by the architecture |
| Real-device map budget verification | Phase 4 | Verified on a mid-range Android over 3G, not on a developer laptop |
| **Deployment, hosting and the PWA** | **End of project** | The internal round does not generally require a live link. Hosting effort now is effort taken off deliverables. The degraded-response contract keeps both cheap whenever they happen |
| DAT-SG hardware distress integration | Out of scope | Architected for, not built. The handoff payload is real; the transport is not |

---

## 10. Acceptance Test

Runs Day 21, recorded, so Phase 4 regressions are caught. Five scenarios, each hitting a different pair of slices.

**A — Voice, end to end, in Tamil (D1)**

```
GIVEN  a fisherman persona on a phone-sized viewport
WHEN   the user holds the voice control and asks, in Tamil, whether it is safe to go to sea
THEN   the waveform shows it is listening, and the transcript appears for confirmation
AND    the transcript is translated, routed persona-blind, and answered
AND    the verdict is spoken back in Tamil and rendered as a banner
AND    the answer card names which ASR and NMT rung produced it
AND    with the Bhashini credential absent, the local rung is used and the answer is unchanged
```

**B — Persona correction with zero re-query (D1)**

```
GIVEN  an answered query rendered under the fisherman persona
WHEN   the user taps "I'm a researcher"
THEN   the same already-computed facts re-render as a statistical summary with export
AND    the network panel shows no /query call — only POST /render
AND    every number is byte-identical to the fisherman rendering
AND    stakeholder_persona_source becomes "explicit" and persists for the session
```

**C — Sentinel crossing to a real subscriber (D2 + D1)**

```
GIVEN  a registered user with a home port at Thoothukudi and a wave-height watch at 2.5 m
WHEN   the fixture forecast crosses 2.5 m between two Sentinel polls
THEN   exactly one notification is dispatched, and a second identical poll dispatches none
AND    the in-app feed shows it, labelled SIMULATED, with the exact Sagar-Vani SMS payload
AND    audit_trace_log carries the broadcast with status 'degraded'
AND    a watch badge appears on the map without a map remount
AND    a later on-demand query from the same user is consistent with what they were told
```

**D — The reasoning graph, live and replayed (D3 + D1)**

```
GIVEN  a DEEP diagnostic query ("why has catch declined near Thoothukudi")
WHEN   it runs with the reasoning graph open
THEN   nodes light in real time as spans open and close
AND    the parallel specialists are drawn inside one group box
AND    the Critic's re-invocation is drawn as a dashed edge to the agent it corrected
AND    clicking Agent 7 shows "deterministic — no LLM" and its full source provenance
AND    replaying the same query_id afterwards renders an identical graph from Postgres
AND    replaying a query_id from the Phase 2 acceptance run also renders
```

**E — Voyage with a hard constraint, and a flagged advisory (D3 + D2)**

```
GIVEN  a navigator plotting a route that clips the Gulf of Mannar Marine National Park
WHEN   the route is computed with a 3 m draft departing in 6 hours
THEN   the clipping segments are BLOCKED and the voyage verdict is NO_GO, not CAUTION
AND    each segment's wave height was sampled at that segment's ETA, not at departure
AND    the waypoint table states every hazard in text, so the answer survives losing the map
WHEN   the user then taps "Not accurate" on the advisory
THEN   the feedback row joins by query_id, and the trace opens in the reasoning graph
       with every agent, source and confidence tier that produced it
```

**F — Accessibility (all three)**

```
GIVEN  the six named flows: Ask, Safety, Map, Fishing Zones, alert interaction, feedback
WHEN   each is completed keyboard-only, then again with NVDA
THEN   every control is reachable, labelled and operable, with no traps
AND    the time slider announces its forecast time via aria-valuetext
AND    the reasoning graph is navigable node to node and its inspector is dismissible
AND    axe-core reports zero criticals in CI
AND    every severity is carried by a text token, never by colour alone
```

---

## 11. Risks

The parent register still applies. These are the ones this phase adds or sharpens.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Bhashini access never arrives** | **High** — it was already pending on 2026-09-02 | Low, by design | The local GPU stack is the *primary* from Day 16, not the fallback. Bhashini is a registered rung that lights up if the credential appears. Nothing is blocked on a government portal |
| Indic ASR/TTS quality is demo-embarrassing on some language | Medium | Medium | Ta / Hi / En are the demo languages and get the most testing. Low-confidence transcripts are confirmed by the user before becoming a query, so a mishearing is visible rather than answered |
| **The reasoning graph is three days of one person's week with no slack** | Medium | **High** — it is the screen the demo is judged on | It starts Day 15 on a fixture, not Day 17 on an API. It is split into three independently shippable parts: layout (15), nodes (16), edges + inspector + replay (17). Nodes alone already demonstrate the agents |
| GPU models make the backend slow to start or fat to run | Medium | Medium | Models warm once at process start and stay resident; ASR/TTS live behind an interface so a CPU-only machine degrades to a smaller model rather than failing |
| The Critic lands in the safety path by accident | Low | **High** — a blocked go/no-go decision | The carve-out is tested on the day the Critic ships: assert the verdict SSE frame precedes the critique frame for a `SAFETY_CHECK` at DEEP depth |
| The Critic re-introduces persona gating | Medium | **High** — the exact v1.0 bug | CI persona-leak guard extended to `orca/agents/critic.py` on Day 18. It triggers on `reasoning_depth`, never on persona |
| Sentinel double-fires from two processes, or spams on unchanged conditions | Medium | Medium | Postgres advisory lock for single-instance; a test that a second identical poll produces zero notifications |
| deck.gl breaks the map performance budget | Medium | Medium | It counts as a heavy layer against the existing concurrency limit and is measured on Day 21 against Phase 2's numbers. It is an overlay nothing depends on — if it fails the budget it is turned off, and no other feature notices |
| `/ops` leaks individual vessel positions to an authority | Low | **High** — a privacy incident on stage | §5.5 aggregation is a hard constraint with a test, not a rendering preference: counts per sector, never plottable individuals |
| Voice, personas, Critic and renderers are four subsystems for one person in one week | **High** | Medium | They are ordered by who they unblock, and each is independently shippable. If Day 20 compresses, the persona *matrix* is already in Agent 9 from Phase 2 — only the surfaces are new |
| Three people, three merges, one graph that gained three agents | Medium | Medium | Slices stay disjoint. Merge daily, no branch older than 24 hours, contract check on Day 18 |
| Phase 2 debt surfaces mid-Phase-3 | Medium | **High** | §0 gate, Day 15 morning, before any Phase 3 code. That is what the gate is for |

---

## 12. Standing Rituals

Unchanged from Phase 2, with two additions.

- **Daily standup, 15 min.** What landed, what is next, what is blocked. Blockers get an owner in the room.
- **Merge daily.** No branch older than 24 hours.
- **Mid-phase contract check, Day 18.** Ten minutes, one question each: has anything you shipped changed a shape someone else consumes?
- **Day-21 integration checkpoint.** The §10 acceptance test run live, plus the UI consistency pass across all eleven surfaces.
- **New: `/design` is updated in the same commit as any new primitive** (§5.3). A primitive that is not on `/design` will not be audited on Day 21.
- **New: every differentiator gets a 60-second recorded clip on the day it lands.** Not for the judges — for us. Five differentiators land this week across three people, and the one thing worse than not building them is nobody knowing they work until Day 21.

---

## 13. Parent Plan Amendments

Apply these to `ORCA_Implementation_Plan.md` so the documents do not disagree.

1. **§6 Phase 3** — add "Team: 3" and a pointer to this document, as Phases 1 and 2 point to theirs.
2. **§6 Phase 3** — deck.gl moves from "⏸️ only if ahead of schedule" to **committed scope**, D3 Day 20. §4.1's table row updates to match.
3. **§6 Phase 4** — remove "Visible Critic self-correction" and "Progressive/streaming rendering polish"; both moved to Phase 3 per §7 of this document.
4. **§4.4** — the reasoning graph owner splits: D1 owns the span stream, `TraceGraph` payload and replay API; D3 owns the renderer. Parent's "Owner: S1" becomes "Owner: D1 (payload) / D3 (renderer)".
5. **§4.9** — renderer owner S6 → D1; dispatcher and Sentinel owner S3 → D2.
6. **§4.10** — feedback control owner S6 → D2 (control, API and analytic-card surfacing all land in one lane).
7. **§4.11** — a11y audit: D1 owns the harness and CI gate, each dev audits their own surfaces on Day 21.
8. **§5.1 / §5.2** — deployment and the PWA are restated as **end-of-project**, after every deliverable is complete, not as a Phase 4 line item.
9. **§0 status table** — Frontend moves to "🟢 All eleven surfaces real"; Agents to "🟢 12 of 12".

---

*Phase 3 of 4. Scope is the parent plan's Phase 3 in full, plus two items pulled forward from Phase 4 — nothing cut, nothing deferred, nothing pushed out. On completion, update the parent plan per §13 and proceed to Phase 4. Last updated: 2026-09-03.*
