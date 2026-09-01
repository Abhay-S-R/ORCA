# 🗺️ ORCA — Implementation Plan (v1.0)

> **Status:** LIVING DOCUMENT — this is the execution plan the whole team works from.
> **Authority:** [`ORCA_Agentic_Architecture_final.md`](./ORCA_Agentic_Architecture_final.md) (v4.0) is the design authority. This document does not re-litigate design decisions; it schedules them, assigns them, and adds the layers that architecture doc left thin (repo layout, UI information architecture, provider-agnosticism, team split).
> **Requirements source:** [`ORCA_Master_Analysis_and_Requirements.md`](./ORCA_Master_Analysis_and_Requirements.md)
> **Data status:** [`data_verification_audit.md`](./data_verification_audit.md) — procurement complete, 98 files, 25/25 datasets, 8/8 PS queries covered.
> **Team:** 6 people · **Duration:** 4 weeks + 2 days buffer · **Pilot region:** South Tamil Nadu (Thoothukudi–Rameswaram–Kanyakumari, Palk Bay, Gulf of Mannar)

If this document and the architecture doc disagree, the architecture doc wins and this one gets fixed. If this document and the code disagree, that is a bug in one of them — resolve it before building further.

---

## 0. Where We Actually Are (Day 0)

| Layer | State | Evidence |
|---|---|---|
| **Data** | ✅ Complete | 98 files / 18.72 GB, 25/25 datasets, 5 integrity defects fixed, PFZ fallback proxy built |
| **Data tooling** | ✅ 5 scripts | `build_mpa_geofence.py`, `build_pfz_fallback.py`, `scrape_pfz_advisories.py`, `extract_osf_pilot.py`, `orca_grid_utils.py` |
| **Architecture** | ✅ Committed | v4.0 — 12 agents, routing table, state schema, hand-off contract, failover, 19 optimizations |
| **Application code** | ❌ **Zero** | No backend, no frontend, no agent implementations |
| **Infrastructure** | ❌ None | No Postgres/PostGIS, no Redis, no CI, no container setup |
| **Team environments** | ✅ Data in place | All 6 engineers already have the `data/` tree locally. Credentials still to confirm — §1.1 |

**The honest read:** the hard research is done and the design is unusually well-specified for a hackathon. What remains is four weeks of disciplined engineering against a spec that already exists. The main risk is not "what do we build" — it is coordination, integration, and holding the line on scope.

**A standing note on `data/`:** it is gitignored (correctly — 18.72 GB does not belong in git), and every engineer already has it. That means it is **out-of-band state that git will not keep in sync for us**. When someone re-runs a procurement script and regenerates a file, nobody else's copy changes. Keep `data/incois_osf_pfz/dataset_manifest.json` authoritative, and announce regenerations in the team channel — a silent divergence in the geofence or PFZ files would surface as an unreproducible agent bug during integration week, which is an expensive place to find it.

---

## 1. Phase 0 Checks — Close Before Feature Work

Data distribution is **not** an issue: every engineer already has the `data/` tree. Two smaller items remain, neither of which stops the team from starting.

### 1.1 🟡 Credential distribution

**[`.env.example`](../.env.example) is committed** — every key the build will need, annotated with where to get it, which phase needs it, and zero values. Copy it to `.env` and fill in.

Two notes from writing it:

1. **The live `.env` currently holds only two keys** (Stormglass, GFW) — everything else the build needs is not yet provisioned by anyone. That is fine for Day 1, but it means "do we have credentials" was never really a yes.
2. **Where a service allows free self-registration — Gemini, Anthropic, OpenAI, Copernicus, NASA Earthdata — every engineer registers their own key.** Six people behind one key is a real rate-limit failure during integration week. Only the paid or limited services (Stormglass at 10 req/day, Bhashini) get one shared key with one named owner.

Nothing here blocks Day 1: INCOIS ERDDAP, the PFZ endpoint, Open-Meteo, NDMA SACHET, GEBCO, VLIZ and WDPA need no key at all, and those cover the entire Phase 1 safety path.

### 1.2 🟡 Endpoint liveness re-check

The data audit verified files on disk. It did not re-verify that every **live** endpoint still answers today. Before Phase 1 agents are coded against them, `curl` each once and record the result:

- INCOIS ERDDAP (`erddap.incois.gov.in`) — cert is pinned at `certs/incois_cert.pem`, confirm it still validates
- INCOIS PFZ text endpoint (`/MarineFisheries/TextData?secid=SEC001..SEC014`)
- Open-Meteo Marine (`marine-api.open-meteo.com/v1/marine`)
- IMD API (`api.imd.gov.in`) and NDMA SACHET CAP feed
- IMD Damini lightning nowcast

Every one of these has a cached local fallback already on disk, so a dead endpoint is a degradation, not a stoppage — but we need to know *which* are degraded before we demo, not during.

**Already resolved from architecture §16.1:** the MOSDAC access-tier ambiguity is closed in practice — real MOSDAC `.h5` SST and `.nc` chlorophyll products are downloaded and verified in `data/tier3/mosdac/`. Update §16.1 of the architecture doc to reflect this.

---

## 2. Ground Rules (non-negotiable, carried from Architecture §1)

These get quoted in code review. They are not aspirational.

1. **Intent decides what fires. Persona decides how it's said.** This applies to the UI layer too — see §4.3. Hiding a nav item must never disable an agent.
2. **Zero LLM on safety.** `evaluate_marine_safety`, geofence breach, hazard tiering, distress detection — deterministic Python. The LLM writes prose about the verdict; it never produces the verdict.
3. **Every claim carries provenance.** Dataset, acquisition timestamp, confidence tier. No number reaches the UI without a source attached — the UI is built to display it (§4.4), so an unsourced number is a visible bug, not a silent one.
4. **Uncertainty degrades conservative.** LOW-DATA renders amber for every persona including fisherman. Unresolved persona renders the cautious composite.
5. **Nothing is provider-locked.** See §3.
6. **Every non-trivial module ships one runnable check.** Not a test suite per function — one `assert`-based check that fails if the logic breaks. The safety core (Agent 7, owned by S2) is the exception: it gets real coverage, because it is the one place a bug is a life-safety issue.

---

## 3. Agent-Agnostic Architecture (Requirement: agent/model agnosticism)

The system must not be welded to one LLM vendor or one agent framework. Two separate concerns, handled differently.

### 3.1 Model agnosticism — enforced structurally

```
orca/llm/
  provider.py    # Protocol: complete(messages, **kw) -> str ; stream(...) -> Iterator[str]
  registry.py    # {"anthropic": ..., "openai": ..., "google": ..., "ollama": ...}
  tiers.py       # "cheap" | "mid" | "reasoning" -> (provider, model), from env/config, never hardcoded
```

**Rules:**
- No file under `orca/agents/` may import a vendor SDK. Enforced by a one-line CI grep — cheap, and it fails loudly the first time someone shortcuts it.
- Agents call `llm(tier="cheap").complete(...)`. They never name a model or a vendor.
- Tier→model mapping lives in config. Swapping the reasoning tier from one vendor to another is an env change, not a code change. Tiers are per-agent and fixed (§3.2); providers are per-tier and configurable (§3.3).
- **Agents 6 (Geospatial) and 7 (Risk Assessment) make zero LLM calls.** The entire safety path is provider-independent by construction, not by discipline. This is the strongest form of the guarantee and it is free — it falls out of Ground Rule 2.

**Acceptance test:** run the Phase 1 safety-path suite against two different providers. Verdicts must be byte-identical (they are deterministic), and prose must differ only in wording. If a verdict changes when the model changes, Ground Rule 2 has been violated somewhere.

### 3.2 Which agents actually need an LLM — and which tier

**Only 5 of the 12 agents call an LLM at all.** This is the most important fact about our provider decision, and it is worth establishing before anyone shops for API keys.

| # | Agent | LLM? | Tier | Why |
|---|---|---|---|---|
| 1 | User Interaction | Partial | **cheap** | Language ID and translation are Bhashini / IndicTrans2, not an LLM. Only persona inference needs a small classifier |
| 2 | Planning | Fallback only | **cheap** | Rules tier routes first (§9.5). The LLM is the third-tier fallback and should rarely fire |
| 3 | Marine Data Discovery | Light | **cheap** | Source selection is a deterministic priority cascade. The LLM only writes the human-readable *reason* string |
| 4 | Weather Intelligence | ✗ | — | API fetch plus threshold comparison |
| 5 | Ocean Analytics | Yes, at DEEP | **reasoning** | "Why has catch declined" is genuine multi-factor causal reasoning. Shallow lookups need no LLM |
| 6 | Geospatial | **✗ by design** | — | Ground Rule 2 — Shapely/pyproj math only |
| 7 | Risk Assessment | **✗ by design** | — | Ground Rule 2 — the go/no-go verdict is arithmetic |
| 8 | Visualization | ✗ | — | Deterministic layer and chart specs |
| 9 | Reporting | Yes | **mid** | Synthesis with strict citation discipline. Needs good instruction-following, not frontier reasoning |
| 10 | Critic | Yes | **reasoning** | LLM-as-judge on causal-claim strength and citation completeness — the hardest judgement in the system |
| 11 | Sentinel | ✗ | — | Threshold-crossing comparison |
| 12 | Distress | **✗ by design** | — | Ground Rule 2 — deterministic multilingual pattern match |

Two consequences worth stating:

- **The entire safety path is LLM-free.** Agents 4, 6, 7, 11 and 12 — everything between "is it dangerous" and "tell the Coast Guard" — never calls a model. Provider choice cannot affect a safety verdict, which is Ground Rule 2 enforced by architecture rather than by discipline.
- **Synthesis happens in English, translation at the edge.** Agent 9 writes English; Agent 1 translates on egress via IndicTrans2/Bhashini. So we do **not** need to pick models for Indic-language generation quality — that is a translation-stack decision, not an LLM one. This meaningfully widens the field of usable providers.

### 3.3 Provider selection — three tiers, decided by bake-off, not by reputation

Per-agent *tiers* are fixed (table above). Per-tier *providers* are configuration. Current landscape as of September 2026, for the bake-off shortlist:

| Tier | Used by | Candidates (list price, input/output per MTok) |
|---|---|---|
| **reasoning** | Agents 5 (DEEP), 10 | GPT-5.6 Sol $5/$30 · Claude Opus 5 $5/$25 · Gemini 3.1 Pro $2/$12 |
| **mid** | Agent 9 | Claude Sonnet 5 $2/$10 · Gemini 3.6 Flash $1.50/$7.50 |
| **cheap** | Agents 1, 2, 3 | GPT-5.6 Luna $0.20/$1.20 · Gemini 3.5 Flash-Lite $0.30/$2.50 · DeepSeek V4 Pro $0.435/$0.87 · Claude Haiku 4.5 $1/$5 |

**Recommendation:**

1. **Do not lock providers now.** §3.1 makes this an env change. Committing before we have real prompts is guessing.
2. **Run a bake-off in Phase 2**, once Agent 9 and Agent 5 have real prompts. Score on three ORCA-specific axes, not generic benchmarks: *citation discipline* (does it invent a source?), *causal-claim restraint* (does it say "caused" when the data only supports "correlated"?), and *refusal to fill gaps* (does it fabricate a wave height when the tool returned nothing?). A model that scores 2 points higher on GPQA but invents a citation is strictly worse for us.
3. **Going multi-provider is justified here, for a reason specific to a hackathon:** free-tier stacking. Six engineers developing against one key will hit rate limits daily. Spreading tiers across providers means each engineer's day-to-day work draws on a different quota. That is a real operational benefit, independent of any quality argument.
4. **Know the cost of the split.** Prompt caches are model-scoped — a multi-provider cascade forfeits cache reuse across its models. Measure whether the cheap tier actually saves money after lost cache hits before treating it as an optimization.
5. **The Critic is where the reasoning tier earns its price.** It is the only agent whose job is judgement rather than generation. If budget forces one frontier-model slot, spend it here.

**Open decision (not blocking):** final provider-per-tier assignment. Owner: S1. Due: end of Phase 2, after the bake-off.

### 3.4 Framework agnosticism — bounded, not absolute

LangGraph is the committed orchestrator (Architecture §10). Making the system swap orchestration frameworks freely would be speculative work we will never cash in — we are not going to migrate mid-hackathon.

What we *do* guarantee, because it costs almost nothing:
- **Agent logic lives in plain functions** with the signature `(ORCAState) -> AgentResult`. LangGraph nodes are thin wrappers over those functions.
- **No agent imports `langgraph`.** Only `orca/graph/` does.
- Consequence: every agent is unit-testable without a graph, callable from the Sentinel background loop (Agent 11) without spinning up a graph run, and portable if the framework choice ever changes.

That is the useful 90% of framework-agnosticism for one line of discipline. We are explicitly *not* building an orchestrator abstraction layer.

---

## 4. UI Architecture (Requirements: standout UI, dynamic maps, persona-differentiated surfaces, distributed navigation)

The architecture doc specifies *what* to render (§11) but not *where it lives* in the product. This section closes that gap.

### 4.1 Design stance

ORCA is not a chatbot with a map bolted on. It is a **map-first decision surface** with a conversational entry point. The map is the primary canvas on every screen that has a spatial answer; chat is one of several ways to drive it.

Visual direction: dark marine theme, high-contrast safety colors (the GO/CAUTION/NO_GO badge must be legible in direct sunlight on a phone at sea), generous touch targets, icon-led for the fisherman surface. Accessibility is a stated cross-cutting requirement (Master doc §6.8), not a polish item: screen-reader labels and a high-contrast mode land in Phase 3, not Phase 4.

### 4.2 Information architecture — distributed navigation

Ten destinations plus one persistent control. Left rail on desktop, bottom tab bar (5 primary + overflow) on mobile.

| Nav item | Route | What lives there |
|---|---|---|
| **Ask** | `/` | Conversational + voice entry, answer card, inline mini-map, agent activity strip |
| **Safety** | `/safety` | Go/No-Go verdict, active hazards, geofence status, vessel-class selector |
| **Map** | `/map` | Full-screen layer explorer — PFZ, SST, chlorophyll, bathymetry, boundaries, hazards, forecast time slider |
| **Fishing Zones** | `/zones` | Nearest PFZ, distance + bearing from home port, persistence score, sector status |
| **Voyage** | `/voyage` | Route planner, vessel draft, waypoints, ETA, tidal berthing windows |
| **Trends** | `/trends` | Time-series, anomalies, diagnostic "why has catch declined" workspace |
| **Data** | `/data` | Catalog browser, source metadata, CSV/NetCDF/GeoJSON export, API access |
| **District Ops** | `/ops` | District threat matrix, CAP payload builder, broadcast composer, audit trail |
| **Watches** | `/watches` | Sentinel subscriptions, threshold config, alert history |
| **Reasoning** | `/reasoning` | Full agent DAG explorer, span timeline, provenance drill-down |
| **SOS** | persistent | Floating control on every screen, every persona, always. Never in a menu. |

This is the direct answer to "don't cluster everything in one place": nine capability surfaces, each with one job, reachable in one tap.

### 4.3 Persona visibility matrix

✅ primary · ◐ visible, secondary · ✗ hidden from nav

| Nav item | 🐟 fisherman | 🚢 navigator | 🔬 researcher | 🚨 authority | ❓ unresolved |
|---|:--:|:--:|:--:|:--:|:--:|
| Ask | ✅ | ✅ | ✅ | ✅ | ✅ |
| Safety | ✅ | ✅ | ◐ | ✅ | ✅ |
| Map | ✅ simplified | ✅ | ✅ full | ✅ | ✅ simplified |
| Fishing Zones | ✅ | ✅ | ◐ | ✗ | ✅ |
| Voyage | ✗ | ✅ | ✗ | ◐ | ✗ |
| Trends | ✗ | ◐ | ✅ | ✅ | ✗ |
| Data | ✗ | ✗ | ✅ | ◐ | ✗ |
| District Ops | ✗ | ✗ | ✗ | ✅ | ✗ |
| Watches | ✅ simplified | ✅ | ◐ | ✅ | ✅ |
| Reasoning | ✗ | ◐ toggle | ✅ toggle-on | ◐ toggle | ✗ *(behind "Show technical detail")* |
| SOS | ✅ | ✅ | ✅ | ✅ | ✅ |

> **⚠️ The rule that makes this safe:** *nav visibility is a rendering concern and never a capability gate.* A hidden route stays reachable by direct URL, and the agents behind it still run at full depth. Gating execution on persona is the exact bug Architecture v2.0 fixed at the routing layer — re-introducing it in the UI layer would be the same defect wearing a different hat. Hide the door, never remove the room.

### 4.4 The reasoning graph (Requirement: persona-gated reasoning tree toggle)

**Source of truth:** the OpenTelemetry span stream from §9.18 — the same stream that populates `audit_trace_log`. One pipeline, two views. The judge-facing trace panel and the compliance-facing audit log are never two systems to keep in sync.

**Two renderings:**

1. **Live activity strip** — during a query, a horizontal row of agent pills that light as spans open and close, with elapsed time. Shown to navigator / researcher / authority.
2. **Reasoning graph** — an on-demand DAG. Nodes are agents; edges are hand-offs; node colour encodes confidence tier. Clicking a node opens `inputs_consumed`, `outputs`, `source_provenance`, `confidence`, and latency straight from the `AgentResult` envelope (Architecture §6). Multi-match fan-out, early-exit cancellations, and Critic re-invocation loops all render as real graph structure — because they are.

**Toggle defaults by persona:**

| Persona | Activity strip | Reasoning graph | Default |
|---|---|---|---|
| fisherman | ✗ — plain one-line progress instead | ✗ absent entirely | — |
| commercial_navigator | ✅ | available | off |
| researcher | ✅ | available | **on** |
| coastal_authority | ✅ | available | off |
| unresolved | ✗ | reachable via "Show technical detail" | off |

**Why the fisherman surface removes it rather than collapsing it:** on a small screen in bad conditions, a reasoning graph competes for attention with the GO/NO_GO badge. That is not clutter, it is a safety regression. The fisherman gets a plain progress line and, if they ever want more, the persona-correction tap (§2.5) re-renders the *already-computed* facts in a richer persona instantly — no re-query. That control is also the cleanest live demonstration that intent and persona are genuinely decoupled.

### 4.5 What makes the UI visibly agentic

Seven differentiators, each mapped to a phase:

| # | Feature | Phase |
|---|---|---|
| 1 | Live agent activity strip during query execution | 1 (scaffold) → 3 |
| 2 | Full reasoning DAG with per-node provenance drill-down | 3 |
| 3 | **Click any number → provenance popover** (dataset, timestamp, freshness, confidence) | 2 |
| 4 | **Source-selection narration** — MDD explains *why* it chose MOSDAC NRT over Copernicus reanalysis | 2 |
| 5 | **Visible Critic self-correction** — draft → flagged issue → corrected answer | 4 |
| 6 | Sentinel watch badges rendered live on the map | 3 |
| 7 | **Persona correction re-renders instantly with no re-query** | 3 |

Items 3, 4, 5 and 7 are the ones judges have not seen before. Prioritise them over visual polish if time compresses.

---

### 4.6 Voyage planning — the constraint-aware corridor

**Decision: we ship a constraint-aware corridor route. A\*/Dijkstra pathfinding is out of scope — not a stretch goal.** This is a design choice with a defensible rationale, and every one of us should be able to give that rationale in Q&A without sounding like we ran out of time.

#### What it computes

```
origin, destination, vessel_draft, vessel_class, departure_time
  │
  ├─ 1. Geodesic line (pyproj), densified into ~0.5 NM segments
  ├─ 2. Per-segment ETA from vessel speed
  │       └── each segment is evaluated at the time the vessel would
  │           actually BE there — not all at departure time
  ├─ 3. Per-segment constraint sampling:
  │       GEBCO depth       < vessel_draft + margin   → SHALLOW    (hard)
  │       EEZ / IMBL polygon containment              → BOUNDARY   (hard)
  │       MPA polygon containment (geofence_usable)   → MPA        (hard)
  │       WW3 Hs at segment ETA vs vessel-class band  → ROUGH_SEA  (soft)
  │       Lightning nowcast at segment ETA            → LIGHTNING  (soft)
  ├─ 4. Corridor buffer (~2 NM either side) so we warn on APPROACH,
  │     not only on crossing
  └─ 5. Classify each segment: CLEAR | CAUTION | BLOCKED
        → GeoJSON polyline, per-segment properties, distance, ETA,
          hazard summary
```

**Hard vs soft is load-bearing.** A hard constraint (depth, boundary, MPA) marks a segment `BLOCKED` and makes Agent 7 return `NO_GO` for the voyage — the geofence stays a hard constraint exactly as Architecture §1 requires. Soft constraints (waves, lightning) produce `CAUTION` overlays and never silently block a route.

#### Why this is the right build, not the smaller one

- **It is what production maritime tools actually show.** A route annotated with the hazards it crosses is more useful to a skipper than a mysterious rerouted line they cannot audit. The user can see *why* a leg is red.
- **Time-aware sampling is the genuinely sophisticated part.** Evaluating segment 40's wave height at the hour you would reach it, rather than at departure, is what makes the answer correct. An A\* that ignored this would be a more complex algorithm producing a *worse* answer.
- **The innovation is the layer combination**, and we deliver it in full: GEBCO bathymetry + EEZ/IMBL + MPA + WW3 waves + lightning, resolved into one decision per segment. A\* on its own is a textbook algorithm, not a contribution.
- **It is deterministic and fast.** No LLM (Ground Rule 2), and it computes in milliseconds rather than the seconds a 500K-cell grid search would take. A route that takes 30 seconds during a live demo is a failed feature regardless of how correct it is.
- **The real cost of A\* was never the algorithm.** It is converting the 720×720 GEBCO grid into a weighted navigability graph, threading vessel draft through as a dynamic passability threshold, folding WW3 in as time-varying edge costs, and then making it fast. That is multiple days of specialist GIS work with a demo-day failure mode attached.

#### The upgrade path — and the Q&A answer

The per-segment classification **is** the cost surface A\* would search over. Adding pathfinding later is additive, not a rewrite.

That gives us the honest answer if a judge asks *"why not A\*?"*:

> "We built the constraint evaluation first, because that is the hard and safety-relevant half. Pathfinding on top of it is a weighted-graph search over exactly this cost surface — we scoped it out deliberately: a route that crosses the IMBL is a legal incident, and a route that takes thirty seconds to compute is a failed demo. Here is the cost surface. The search is the easy half."

That answer demonstrates we understood the design space and chose within it, which is the thing being evaluated — rather than a checkbox we ticked and cannot defend.

---

## 5. Repository Layout & Deployment

Fixed in Phase 0, Day 1. Everyone branches from this; changing it later is expensive.

```
orca/
├── backend/
│   ├── orca/
│   │   ├── agents/          # one module per agent, plain (ORCAState) -> AgentResult functions
│   │   ├── tools/           # the callable tools from Architecture §3 tables
│   │   ├── graph/           # LangGraph wiring — the ONLY place langgraph is imported
│   │   ├── llm/             # provider protocol, registry, tier config (§3.1)
│   │   ├── data/            # loaders over data/ — NetCDF, GeoJSON, CSV, cached JSON
│   │   ├── state.py         # ORCAState (Architecture §5) — frozen contract
│   │   ├── contracts.py     # AgentResult envelope (Architecture §6) — frozen contract
│   │   ├── trace.py         # OTel spans -> audit_trace_log
│   │   └── api/             # FastAPI routes, SSE streaming
│   └── tests/
├── frontend/                # Next.js (App Router)
│   ├── app/                 # one directory per §4.2 route
│   ├── components/
│   │   ├── map/             # Leaflet layers, controls, time slider
│   │   ├── reasoning/       # activity strip, DAG explorer
│   │   ├── persona/         # selector, correction control, visibility matrix
│   │   └── evidence/        # provenance popovers, citation chips
│   └── lib/                 # SSE client, typed API contracts
├── data/                    # gitignored — already present on every machine, kept in sync out-of-band
├── scripts/                 # existing procurement + new sync tooling
├── docs/                    # architecture, requirements, this plan
└── infra/                   # docker-compose (Postgres+PostGIS, Redis), CI
```

### 5.1 Deployment topology — Vercel + PWA (after the internal round)

**Scheduling decision: deployment is not in scope for the internal round.** The month targets a local demo. This section is the committed plan for *after* it, recorded now so nothing gets built in a way that forecloses it.

**Decided when we get there:** frontend on Vercel, installable as a PWA. That settles the frontend; it does **not** settle the backend, and the split matters.

| Piece | Where | Why |
|---|---|---|
| Next.js frontend | **Vercel** | Native target. Preview deploys per PR are a real team benefit with six people merging daily |
| FastAPI + LangGraph backend | **A container host** (Render / Railway / Fly.io / HF Spaces) | Not Vercel — see below |
| Postgres + PostGIS | Managed Postgres with the PostGIS extension | Session persistence and `audit_trace_log` |
| Redis | Managed Redis | Cache TTLs, request coalescing |
| Pilot-region `data/` subset | Baked into the backend image, or object storage | The full 18.72 GB never deploys |

**Why the backend cannot be Vercel serverless functions** — three independent blockers, each sufficient on its own:

1. **Bundle size.** GeoPandas, Shapely, pyproj, xarray, h5py and the tree-sitter stack blow past serverless bundle limits before any of our own code is added.
2. **Sentinel is a background loop.** Agent 11 runs continuously, independent of the request/response graph (Architecture §3.2). Serverless has no always-on process to run it in. This is architectural, not a config problem.
3. **Cold starts.** Loading a 720×720 GEBCO grid and five boundary files on every cold invocation is fatal to the "seconds, not minutes" safety-latency NFR.

So: **Vercel for the frontend, one always-on container for the backend.**

**The only thing this asks of us during the month:** write the backend `Dockerfile` in Phase 0 and keep it working. That is an hour, it makes every engineer's environment reproducible regardless of deployment, and it means the eventual deploy is a push rather than an archaeology project. Everything else here waits.

### 5.2 The PWA is a requirement, not a checkbox

The master requirements call out offline and low-connectivity access as a **critical gap** — fishermen at sea are the least-connected users and the highest-stakes ones. A PWA is the cheapest honest answer to that, and it is worth building deliberately rather than by dropping in a manifest:

- **Service worker caches the last safety verdict per location**, with its timestamp. Opening the app with no signal shows the last known answer, explicitly stamped stale and forced to the LOW-DATA amber treatment — never a confident-looking cached GO.
- **Installable, Android-first**, which is the "Android-first rural reach" requirement met without building and shipping a native app.
- App-shell caching so the UI loads instantly on a poor connection and populates as data arrives — the same progressive-rendering discipline as §9.19, applied to the cold start.

That last point is the one to get right: **a cached verdict must never render like a live one.** The offline path reuses the existing degraded-response contract (Architecture §12.2) rather than inventing a second set of rules.

**Lands:** after the internal round, alongside the first deploy. The design constraint it places on us *now* is only this — the offline path must reuse the existing degraded-response contract, so keep that contract clean and the PWA is a small addition later rather than a second set of staleness rules.

---

## 6. Phase Plan

### Phase 0 — Foundation & Unblocking · Days 1–2

**Goal:** every one of 6 engineers can clone, install, run, and see something on screen.

- Confirm credentials across all six machines (§1.1)
- Repo scaffolding per §5; `docker-compose` with Postgres+PostGIS and Redis; a working backend `Dockerfile` (reproducible envs now, deployable later)
- **Freeze the contracts:** `ORCAState`, `AgentResult`, tool signatures. Everything downstream depends on these; they land before feature work, not alongside it
- LLM provider abstraction (§3.1) with two providers registered
- CI: lint, typecheck, test, plus the vendor-SDK-import guard
- Endpoint liveness sweep (§1.2)
- Next.js app skeleton with the §4.2 nav shell rendering (dead links are fine)

**Exit criteria:** `docker compose up` works on all 6 machines · CI green on an empty test · a mock `/query` SSE stream renders in the browser.

---

### Phase 1 — Core Safety Vertical Slice · Days 3–7

**Goal:** one query — *"Is it safe to go to sea tomorrow morning near Thoothukudi?"* — asked in Tamil, answered end-to-end in Tamil, with a real deterministic verdict, a real map, and a captured trace.

Full detail and per-person assignment: **[`ORCA_Phase1_Plan.md`](./ORCA_Phase1_Plan.md)**

- Agent 7 (Risk Assessment) with vessel-class deltas and confidence tiers, properly tested
- Agents 4 (Weather) + 6 (Geospatial) — minimum viable tool set for the safety path
- Agent 12 (Distress) — pattern detection + MRCC surfacing. **Built now, not deferred**; it is the highest-severity gap the architecture audit found
- Agent 1 (Language) — Tamil + Hindi ingress/egress
- LangGraph skeleton: Planning → [WIA ∥ GRA] → RAA → Reporting
- Frontend: nav shell, persona system, Ask + Safety surfaces, Leaflet map, streaming verdict card

**Exit criteria:** the Tamil safety query returns a correct verdict end-to-end · the same query in Hindi and English works · SOS surfaces MRCC contact in under 2 seconds · every displayed number carries a source · the trace is captured (rendering it is Phase 3).

---

### Phase 2 — Full Agent Roster & Multi-Intent · Days 8–14

**Goal:** all nine core agents live; the system answers every PS sample-query category, not just safety.

- Agent 5 (Ocean Analytics) — SST/chlorophyll correlation, PFZ proximity + persistence scoring, tide prediction, diagnostic mode
- Agent 3 (Marine Data Discovery) — full catalog routing with **narratable** source selection (§4.4). This is the PS's "tool selection" requirement; it must be visible, not internal
- Multi-intent: union resolution (§4.1), no-match fallback (§4.2)
- Agent 9 (Reporting) — full persona rendering matrix, evidence citations, export-formatter mode
- Researcher persona end-to-end: structured report, CSV/NetCDF export
- Frontend: Map explorer with real layers, Fishing Zones, Trends, Data surfaces; **provenance popovers** (differentiator 3); **source-selection narration** (differentiator 4)
- Redis caching with source-cadence-aware TTLs (§9.1, §9.11)
- **LLM provider bake-off** (§3.3) — now that Agents 5 and 9 have real prompts to score against

**Exit criteria:** all 8 PS sample queries return substantive answers · researcher export produces a valid CSV with full metadata · multi-intent queries visibly activate the union of agents.

---

### Phase 3 — Differentiation: Sentinel, Critic, Voice, Personas · Days 15–21

**Goal:** the capabilities that separate ORCA from a RAG chatbot. This is the week that wins or loses the demo.

- **Agent 11 (Sentinel)** — background monitor, threshold-crossing detection. **Dispatch is simulated in-app**: the alert lands in the UI and renders the exact Sagar-Vani SMS payload that would have been sent, rather than sending it. Build behind a `Dispatcher` interface with one `InAppDispatcher` implementation, so a real gateway is a new class and not a refactor. (A real Indian SMS gateway also needs DLT registration, which does not fit a four-week window.) Fixed polling first; adaptive frequency (§9.17) only if ahead
- **Agent 10 (Critic)** — depth-triggered, with the async-upgrade carve-out so it never blocks a safety verdict
- **Voice pipeline** — Bhashini ASR/TTS with local Whisper fallback, wired for the fisherman surface
- Full language coverage across all named coastal languages
- All four personas complete + persona-correction control (differentiator 7)
- **Reasoning graph explorer** (differentiator 2) + Sentinel watch badges (differentiator 6)
- **Voyage planner: the constraint-aware corridor route** (§4.6) — the committed design, not a fallback. A* is explicitly out of scope
- District Ops surface: threat matrix, CAP payload, broadcast composer
- Accessibility pass: screen-reader labels, high-contrast mode

**Exit criteria:** a Tamil voice query works end-to-end · Sentinel fires a real threshold-crossing alert · persona correction re-renders with zero re-query · the reasoning graph renders a real multi-agent trace.

---

### Phase 4 — Optimization, Replay & Demo · Days 22–28

**Goal:** fast, resilient, and rehearsed.

- Optimizations, now that the graph is stable — never before: cost-based short-circuit (§9.3), early-cancel (§9.4), request coalescing (§9.9), semantic cache (§9.1), stale-while-revalidate (§9.14, scoped away from safety-gating data)
- Progressive/streaming rendering polish (§9.19) — safety badge populates **last**, never as an optimistic placeholder
- **Cyclone Gaja historical replay mode** — makes hazard alerting demonstrable outside cyclone season
- **Visible Critic self-correction** (differentiator 5)
- Failure-mode rehearsal: kill each upstream source and confirm the degraded-response contract (§12.2) actually fires, including forced-amber on all-sources-down
- Demo script: one query per persona, plus distress handoff and proactive geofence as the two centerpiece flows
- Load smoke test on the priority lane (§9.10)

**Exit criteria:** full demo runs twice, unrehearsed-machine, without a stumble · every failure mode in §12.2 verified by actually triggering it · p95 latency on the safety path under target.

---

### Buffer — Days 29–30

Deliberately unplanned. It will be consumed; every project of this shape consumes it. Do not pre-spend it.

---

## 7. Slice Ownership (whole month)

Everyone on this team is full-stack, so the work is split **vertically**: each person owns a capability from the agent that computes it through the API that serves it to the surface that renders it. Nobody hands a number to somebody else to draw.

This beats a backend/frontend split for us for one concrete reason: **the person who computes a value also displays it**, so the provenance requirement (Ground Rule 3) has a single owner per number instead of a negotiation across a team boundary. It also removes the largest source of integration debt — the frontend and backend disagreeing about a payload shape — because there is no boundary to disagree across.

| # | Slice | Agents owned | Surfaces owned | Shared concern owned |
|---|---|---|---|---|
| **S1** | **Platform & Orchestration** *(lead)* | 2 Planning | `/reasoning`, agent activity strip | Contracts, LangGraph, LLM provider layer, FastAPI + SSE, trace pipeline, CI, **deployment** |
| **S2** | **Safety & Distress** | 7 Risk · 12 Distress | `/safety`, persistent SOS control | Safety palette + verdict-badge component |
| **S3** | **Weather & Sentinel** | 4 Weather · 11 Sentinel | Hazard panels, `/watches` | The `orca/data/` loader layer |
| **S4** | **Ocean & Discovery** | 5 Ocean Analytics · 3 Data Discovery | `/zones`, `/trends`, `/data` | Chart components + provenance popover |
| **S5** | **Geospatial & Visualization** | 6 Geospatial · 8 Visualization | `/map`, `/voyage` | The Leaflet map shell everyone adds layers to |
| **S6** | **Synthesis, Language & Personas** | 9 Reporting · 10 Critic · 1 User Interaction | `/` (Ask), persona system, nav IA, `/ops` | Design system + component library |

Twelve agents, six people, two each — except S1, which carries one agent but all of the platform, and S6, which carries three tightly-coupled ones. **S6's three are genuinely one concern:** Reporting synthesises, Critic validates what Reporting wrote, and User Interaction translates it out. That whole chain is "how the answer reaches a human", and splitting it across people would put a handoff in the middle of a feedback loop.

**Each person also owns exactly one shared concern.** This is what keeps vertical slicing from producing six inconsistent UIs — every cross-cutting thing (design system, map shell, charts, loaders) has one named owner, and everyone else consumes it rather than reinventing it.

**Where slicing costs us, and the mitigation:** vertical teams drift visually. Two defences — S6 owns the design system and every other slice builds from its components, and the Friday integration checkpoint (§8) includes a UI consistency pass across all six surfaces, not just a functional demo.

**Heaviest slice:** S5. GEBCO grids, geodesic boundary math, and route geometry are the deepest domain work in the project. If a slice slips it will be this one — plan to move S3 onto it in Week 3 once the weather tools stabilise.

---

## 8. Integration Discipline

Six people writing against one graph fails in a predictable way. Three rules prevent it.

1. **Contracts freeze on Day 1, before feature code.** `ORCAState` and `AgentResult` change only by explicit team agreement, never in a feature branch. A contract change is announced, not merged quietly.
2. **Fixtures before integration.** Every agent ships with a recorded fixture of its own output. Frontend builds against fixtures; backend agents test against fixtures. Nobody blocks on anybody. With vertical slices each person builds their own UI against their own fixtures, so nobody waits on anybody from Day 3.
3. **Integration checkpoint every Friday.** All branches merge, full path runs end-to-end, demo of the week's slice. A branch that has not merged by Friday is a schedule risk, reported as such.

**Daily:** 15-minute standup, and a single shared blockers channel. The one thing that must be said out loud is "I am blocked on X" — with six people and a hard deadline, a silent blocker is the expensive failure.

---

## 9. Acceptance Traceability

Every PS requirement mapped to the phase where it lands and the slice that owns it. This is the checklist for "is the product actually functional and complete."

Read **Phase 0–4** as the calendar and **S1–S6** as the people (§7) — the two were ambiguous in an earlier draft and are now deliberately distinct.

| Requirement (Master doc) | Lands in | Owner |
|---|---|---|
| Multi-agent orchestration, visible hand-offs | Ph1 skeleton → Ph2 full roster → Ph3 graph UI | S1 |
| Language ID + regional-language response | Ph1 (Ta/Hi) → Ph3 (full set) | S6 |
| Voice STT/TTS as first-class channel | Ph3 | S6 |
| Multi-turn dialogue, coreference | Ph3 | S6, S1 |
| Intelligent catalog selection ("tool selection") | Ph2, narratable | S4 |
| Heterogeneous format handling (NetCDF/GeoJSON/CSV/HTML) | Ph1 loaders → Ph2 full | S3 |
| Spatial reasoning — PFZ, corridors, boundary proximity | Ph1 (proximity) → Ph2 (zones) → Ph3 (routes) | S5 |
| Temporal reasoning & trends | Ph2 | S4 |
| Tidal prediction | Ph2 | S4 |
| Cross-source correlation (SST + Chl + PFZ) | Ph2 | S4 |
| Causal/diagnostic "why" reasoning | Ph2 → Ph4 with Critic | S4, S6 |
| Deterministic confidence tiering | Ph1 | S2 |
| Evidence citation on every claim | Ph1 backend → Ph2 UI popovers | S6 backend, S4 popover |
| Interactive maps + charts | Ph1 base → Ph2 layers → Ph4 replay | S5, S4 |
| Reasoning-trace, persona-differentiated | Ph1 capture → Ph3 render | S1 |
| Proactive hazard alerting (simulated dispatch) | Ph3 (Sentinel) | S3 |
| Geofencing as hard constraint | Ph1 | S5 |
| Alert severity tiering | Ph1 | S2 |
| Bathymetry-aware route optimization | Ph3 — constraint-aware corridor (§4.6) | S5 |
| Persona-differentiated output | Ph1 (fisherman) → Ph2 (researcher) → Ph3 (all four) | S6 |
| Distress / DAT-SG handoff | **Ph1** | S2 |
| CAP-format interoperability | Ph3 | S6 |
| Data-freshness indicators | Ph1 | S3 |
| Degraded-response contract | Ph2 → verified Ph4 | S3 |
| Offline / low-connectivity access (PWA) | **After internal round** — degraded-response contract kept clean in Ph2 so it drops in | S6 |
| Accessibility | Ph3 | S6 |
| Audit trail / explainability | Ph1 capture → Ph3 surface | S1 |
| Deployment (Vercel + backend container) | Ph0 Dockerfile only → **after internal round** | S1 |

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `data/` copies silently diverge between machines | Medium | High — unreproducible agent bugs found late | `dataset_manifest.json` stays authoritative; any regeneration is announced in the team channel (§0) |
| Credentials missing on some machines | Low | Medium | §1.1, closed on Day 1 |
| Contract churn after Day 3 | Medium | High — rework across 6 branches | Freeze on Day 1; changes need team sign-off |
| Someone starts building A* pathfinding | Medium | High — it eats Week 3 | A* is **out of scope**, not a stretch (§4.6). The corridor route is the deliverable. If a judge asks why, §4.6 has the answer |
| Bhashini access still pending | **Confirmed** | High — voice is a headline feature | **Local IndicTrans2 + quantized Whisper are the primary path, not the fallback**, until access lands. Pre-downloaded and warm from Phase 1. Bhashini swaps in behind the same tool interface when granted, so it is a config change and never a rewrite |
| Live endpoint dies during demo | Medium | High | Every source already has a cached local fallback. Rehearse the air-gapped path in Phase 4 and be ready to demo fully offline |
| Integration debt surfaces in Week 4 | Medium | High | Weekly Friday merge checkpoints; no branch older than 5 days |
| UI polish crowds out the agentic differentiators | Medium | Medium | §4.5 priority order is explicit: differentiators 3, 4, 5, 7 beat visual polish |
| Six people, one graph, merge conflicts | High | Medium | Vertical slices with disjoint files by construction (§7); agents and surfaces are separate modules |
| Vertical slices produce six inconsistent UIs | **High** | Medium | S6 owns the design system; every slice builds from its components. Friday checkpoint includes a UI consistency pass, not just a functional demo |
| Deployment deferred, then rushed after the internal round | Medium | Medium | The Phase 0 `Dockerfile` and the clean degraded-response contract are the only two things that must exist during the month for the later deploy to be small (§5.1, §5.2) |
| LLM provider decision drifts unowned | Medium | Low | §3.3 names S1 as owner with a Phase 2 bake-off deadline. Tiers are fixed now; only providers are open |
| Scope creep from the architecture's own optimization list | Medium | Medium | §9 optimizations are Phase 4 *only*. Implementing them before the graph is stable is explicitly forbidden by the architecture |

---

## 11. Definition of Done

The build is done when a stranger can sit down and, without help:

1. Ask *"Is it safe to go to sea tomorrow near Thoothukudi?"* by voice in Tamil and get a correct, sourced, spoken answer
2. Switch to the researcher persona and see the same underlying facts as a cited report with a downloadable CSV
3. Open the reasoning graph and trace every number back to a dataset and a timestamp
4. Trigger SOS and watch a structured distress handoff emit with MRCC contact surfaced
5. Plan a route from Thoothukudi toward Palk Bay and watch the IMBL treated as a hard barrier
6. Watch a Sentinel alert fire on a threshold crossing they did not ask for
7. Replay Cyclone Gaja and see the hazard cascade
8. Pull the network cable and still get a correct, honestly-amber-flagged answer

Eight scenarios. If all eight run clean, the product achieves what the problem statement asked for.

---

*Living document. Update it, dated, whenever a phase boundary or an owner changes. Last updated: 2026-09-02.*
