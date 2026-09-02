# 🗺️ ORCA — Implementation Plan (v1.3)

> **Status:** LIVING DOCUMENT — this is the execution plan the whole team works from.
> **Authority:** [`ORCA_Agentic_Architecture_final.md`](./ORCA_Agentic_Architecture_final.md) (v4.0) is the design authority. This document does not re-litigate design decisions; it schedules them, assigns them, and adds the layers that architecture doc left thin (repo layout, UI information architecture, provider-agnosticism, team split).
> **Requirements source:** [`ORCA_Master_Analysis_and_Requirements.md`](./ORCA_Master_Analysis_and_Requirements.md)
> **Data status:** [`data_verification_audit.md`](./data_verification_audit.md) — procurement complete, 98 files, 25/25 datasets, 8/8 PS queries covered.
> **Team:** 6 people · **Duration:** 4 weeks + 2 days buffer · **Pilot region:** South Tamil Nadu (Thoothukudi–Rameswaram–Kanyakumari, Palk Bay, Gulf of Mannar)

**What changed in v1.3:** Phase 0 is reconciled with the code that actually exists. Three §0 claims were stale — infrastructure is written (compose, `Dockerfile`, CI with all three guards), the frontend is further along than "scaffold", and `MapView.tsx` carries real Leaflet layers rather than none. So the §4.1 map change is restated as a **port** with a per-construct mapping table, the design-system work names the token rename and its three call sites, `/design` + `axe-core`-in-CI and a reproducible-env task are added as explicit Phase 0 items, and the exit criteria become nine runnable commands including one that checks the ported layers lose no capability. Sections touched: §0, §4.1, §6 Phase 0, §10. No backend, agent or data decision changed.

**What changed in v1.2:** the frontend is re-specified. Leaflet is replaced by MapLibre GL JS, the visualisation stack (charts, agent-graph renderer, icons, motion, theme tokens) is decided rather than left to each slice, the reasoning graph is designed down to node and edge semantics, and the design system moves into Phase 0 so six vertical slices inherit one UI instead of negotiating six. Sections touched: §4.1, §4.4, §4.7, §5 layout, §5.9, §6 (all phases), §7, §9, §10. No backend, agent or data decision changed.

If this document and the architecture doc disagree, the architecture doc wins and this one gets fixed. If this document and the code disagree, that is a bug in one of them — resolve it before building further.

**Status vocabulary — used consistently throughout this document.** An interface existing is not the same thing as a capability working, and the difference is exactly where demo-day surprises come from:

| Marker | Means |
|---|---|
| ✅ **Implemented** | Working in this repository today. Someone can run it. |
| 🟡 **Partially implemented** | The internal half works; an external integration is simulated or stubbed behind a real interface. Named explicitly, never rounded up to ✅. |
| ⏸️ **Deferred** | A known requirement we are deliberately not building in this phase, with the reason stated. |
| 🔗 **Dependency** | Cannot be completed until an external dataset or service is obtained. Blocked on procurement, not on engineering. |
| 📋 **Specified** | Designed and scheduled in this plan; no code yet. Most of this document is here on Day 0. |

---

## 0. Where We Actually Are (Day 0)

| Layer | State | Evidence |
|---|---|---|
| **Data** | ✅ Complete | 98 files / 18.72 GB, 25/25 datasets, 5 integrity defects fixed, PFZ fallback proxy built |
| **Data tooling** | ✅ 5 scripts | `build_mpa_geofence.py`, `build_pfz_fallback.py`, `scrape_pfz_advisories.py`, `extract_osf_pilot.py`, `orca_grid_utils.py` |
| **Architecture** | ✅ Committed | v4.0 — 12 agents, routing table, state schema, hand-off contract, failover, 19 optimizations |
| **Backend** | 🟡 In progress | FastAPI app, contracts/state, LLM registry, normalization, LangGraph skeleton and 9 agent modules exist under `backend/orca/` |
| **Frontend** | 🟡 Ahead of the plan, on the wrong stack | Next.js 16 App Router, all ten §4.2 routes present, persona context + visibility matrix, four primitives (`Card`, `Badge`, `Field`, `SourceChip`), SSE `/query` client on `/`. **`MapView.tsx` is no longer a scaffold** — 163 lines of real Leaflet layers (EEZ/MPA GeoJSON with proximity styling, PFZ markers, click→depth/bearing) against four live backend routes. The §4.1 swap is therefore a **port, not an npm command** — still Phase 0, see §4.1 |
| **Database schema** | ✅ Defined, not yet deployed | [`infra/db/001_init.sql`](../infra/db/001_init.sql) + [`migrate.sh`](../infra/db/migrate.sh) — §5.3 |
| **Infrastructure** | 🟡 Written, not yet proven | [`docker-compose.yml`](../docker-compose.yml) (PostGIS 16-3.4 on host `5433`, Redis 7, backend service), [`backend/Dockerfile`](../backend/Dockerfile) and [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) with the vendor-SDK, persona-leak and secret-scan guards all exist. What does not exist is evidence any of it has been run on six machines — that is Phase 0's job, §6 |
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

### 1.3 🔗 Cyclone Gaja replay data — verified missing, and it is a procurement task

Status: **🔗 Dependency.** The Phase 4 replay (§6, Definition of Done #7) assumes historical Cyclone Gaja data. It is **not on disk.** A repository-wide search for `Gaja` across every text dataset returns hits only in the three docs that *plan* the replay — `data/` contains none.

What is actually there, and why none of it substitutes:

| On disk | Why it does not cover Gaja |
|---|---|
| `data/tier1/hazards/ndma_cap_alerts.json` | Current CAP alerts only. No 2018 archive. |
| `data/tier1/hazards/imd_nowcast_alerts.json` | Nowcast — hours, not history. |
| `data/tier1/weather/era5_historical_thoothukudi_30d.json` | ERA5, but a **30-day window in 2026**. Right product, wrong dates. |
| `data/incois_osf_pfz/osf_ww3/*.nc` | Forecast cycles from Aug–Sep 2026. |

**What the replay actually needs** (Gaja made landfall near Vedaranyam, 15–16 November 2018):

1. **IMD best-track** — 6-hourly position, pressure, max sustained wind for the full lifecycle. Source: IMD RSMC New Delhi best-track archive, or IBTrACS (NOAA NCEI), which is open, machine-readable, and needs no credential. IBTrACS is the pragmatic pick.
2. **Wind and wave fields over the landfall window** — ERA5 hourly single-levels (`u10`, `v10`, `swh`, `mwp`) for 12–18 Nov 2018 over the pilot bbox. Same Copernicus CDS credential path already in `.env.example`; only the date range changes.
3. **Warning text**, optional — IMD bulletins for the period, to make the alert cascade quote real language rather than generated prose.

**Owner: S3. Due: end of Phase 2** — early enough that Phase 4 is assembly, not procurement. Roughly two hours of download against known endpoints, so the risk is that nobody starts it, not that it is hard.

**The rule that keeps this honest:** the replay UI must banner every frame with its provenance class — `HISTORICAL OBSERVED (IMD/ERA5, Nov 2018)` versus `LIVE` versus `SIMULATED`. If item 1 or 2 does not land, the replay ships **⏸️ deferred and labelled as such in the demo script.** We do not synthesise a cyclone track and present it as Gaja.

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

### 4.1 Design stance & frontend stack

ORCA is not a chatbot with a map bolted on. It is a **map-first decision surface** with a conversational entry point. The map is the primary canvas on every screen that has a spatial answer; chat is one of several ways to drive it.

**Visual direction — a maritime command centre, not a dashboard template.** Deep-ocean dark base, one accent family, glass-surfaced panels floating over the map rather than boxing it in, and a safety palette deliberately louder than everything else on screen. The GO / CAUTION / NO_GO badge must be legible in direct sunlight on a phone at sea; nothing else in the UI may compete with it for contrast. Generous touch targets, icon-led for the fisherman surface. Accessibility is a stated cross-cutting requirement (Master doc §6.8), not a polish item: screen-reader labels and a high-contrast mode land in Phase 3, not Phase 4.

**The one rule that keeps the polish honest:** chrome may be beautiful, data may not be decorated. Gradients, blur and motion belong to panels, navigation and empty states. A wave height, a confidence tier and a boundary distance are rendered plainly, with their source one tap away. If a visual treatment makes a number look more certain than its confidence tier says it is, that is a bug (Ground Rule 3).

#### The frontend stack — decided, with the reasoning

The Phase-0 scaffold shipped Leaflet and raw Tailwind. Both are replaced here. Each row is a decision, not a preference:

| Layer | Package | Why this one |
|---|---|---|
| **Framework** | `next` 16 (App Router), React 19, TypeScript | ✅ Keep. Already in place; server components for the static surfaces, client for the map and the graph |
| **Map engine** | `maplibre-gl` + `@vis.gl/react-map-gl` | 🔄 **Replaces Leaflet.** GPU vector rendering holds 60 fps over the IMBL/MPA polygon set that drops frames in Leaflet's DOM renderer; GPU restyling makes a pulsing breach alert a paint-property change; open source, no API-key lock-in. Comparison and budget in §4.7 |
| **Basemap** | CARTO Dark Matter (default) · MapTiler Ocean (bathymetry surfaces) | 🆕 Dark maritime styling with depth contours. Style URLs are config, never code — swapping the basemap must not be a code change |
| **Flow fields** | `@deck.gl/core` + `@deck.gl/mapbox` overlay | 🆕 **Phase 3, conditional.** Animated wind/current vectors only. It does not replace MapLibre layers, and nothing in Phase 1–2 may depend on it |
| **Charts** | `recharts` | 🆕 Wave-height areas, wind bars, SST/chlorophyll trends, confidence meters. Responsive, plain React, no imperative canvas to keep in sync with our state |
| **Reasoning graph** | `@xyflow/react` (React Flow) | 🆕 The agent DAG at `/reasoning`. Pan/zoom, custom nodes, edge routing and selection are exactly the parts we would otherwise hand-roll badly. Design in §4.4 |
| **Icons** | `lucide-react` | 🆕 Anchor, compass, waves, alert-triangle, radio. Tree-shaken; one consistent stroke weight across six slices built by six people |
| **Motion** | `framer-motion` | 🆕 Panel transitions, activity-strip pulses, node state changes. **Gated on `prefers-reduced-motion` (§4.11)** — motion is never the only carrier of state |
| **Styling** | Tailwind CSS v4 + ORCA theme tokens | 🔄 **Upgrade.** Ocean / glass / severity tokens defined once as CSS custom properties in `@theme`. Raw hex in a component is a review rejection |
| **State** | React state + the SSE hook; URL for map view state | ✅ No state library. Results stream in and live in the page; map centre/zoom/layers live in the URL so a view is shareable and the back button works. Add one only when this measurably breaks |

```bash
cd frontend
npm install maplibre-gl @vis.gl/react-map-gl recharts @xyflow/react lucide-react framer-motion
npm uninstall leaflet react-leaflet @types/leaflet
```

**Migration cost, stated plainly — corrected in v1.3.** An earlier draft called `app/components/MapView.tsx` an empty scaffold. It is not: it is 163 lines carrying EEZ/MPA GeoJSON with proximity-gradient styling, PFZ circle markers, a click handler that reads GEBCO depth and bearing, and popups — all wired to `/api/map-layers`, `/api/zones-nearby`, `/api/zones`, `/api/depth`, `/api/bearing`. So the swap is a **half-day port of one file**, not the `npm install` above. What ports how:

| Leaflet today | MapLibre equivalent | Note |
|---|---|---|
| `<MapContainer bounds>` | `<Map initialViewState={{bounds}}>` from `@vis.gl/react-map-gl/maplibre` | Still `ssr: false`; MapLibre touches `window` at module load exactly as Leaflet does |
| OSM raster `<TileLayer>` | CARTO Dark Matter **style URL** | Style is config (`NEXT_PUBLIC_BASEMAP_STYLE`), never a literal in the component |
| `<GeoJSON style={fn}>` | one `<Source type="geojson">` + `<Layer>` with a `case` paint expression on `properties.designation` / the near-set | The per-feature JS style function becomes a data-driven expression — this is the only genuinely new idea in the port, and it is what buys the 60 fps in §4.7 |
| `<CircleMarker>` per PFZ point | one `circle` layer over a single FeatureCollection | N components → 1 layer |
| `layer.bindPopup(html)` | `<Popup>` + `onClick` hit-test via `interactiveLayerIds` | Kills the raw HTML-string popups; provenance goes through `ProvenancePopover` |
| Marker icon CDN patch (`L.Icon.Default`) | deleted | The bundler-path workaround has no MapLibre analogue — three fewer network requests |

The port is still cheap *today* and expensive in Week 3, which is why it is a Day-1 task and why §4.7's budget is written against MapLibre rather than retrofitted onto it. **Nobody adds a layer to `MapView.tsx` until it has landed** — that, not the dependency list, is the thing the exit criterion protects.

#### Design system — built once, in Phase 0

S6 owns it; every other slice consumes it. Six people building six interpretations of "a card" is the predicted failure mode of vertical slicing (§7), and the defence is that the primitives exist before the surfaces do:

- **Tokens** (`app/globals.css`, Tailwind v4 `@theme`): ocean surface ramp, glass elevation levels, the safety triad (`--go` / `--caution` / `--no-go`, each contrast-verified ≥4.5:1 on the dark base), confidence tiers, focus ring.
  - **What is there now, and what it costs to change.** `globals.css` today is a **light theme** — `--background: #ffffff`, with dark handled by a `prefers-color-scheme` block — plus a safety triad named `--color-safety-{go,caution,danger}-{text,bg}` and *no* ocean ramp, glass, confidence or focus tokens. §4.1's direction is dark-*first*, so this is an inversion, not an extension: the dark values become the base and the light block goes away. The triad also loses its `-bg` half (badges become glass over the dark base, not light fills) and `danger` renames to `no-go` to match the verdict vocabulary the API already emits. **Three files consume the old names** — `Badge.tsx`, `SourceChip.tsx`, `MapView.tsx` — so the rename is a same-commit job with them, and `grep -r "color-safety-.*-bg" frontend/app` returning nothing is how it is checked. Do it before the surfaces multiply the call sites.
- **Primitives:** `Panel` (glass), `Card`, `VerdictBadge` (S2 owns its safety semantics), `SourceChip`, `ProvenancePopover`, `ConfidenceMeter`, `AgentPill`, `LayerToggle`, `TimeSlider`, `Skeleton`, `EmptyState`, `ErrorState`.
  - **Four exist** (`Card`, `Badge`, `Field`, `SourceChip`) and are kept, not rewritten: `Badge` becomes the base `VerdictBadge` wraps, `Field` stays as the form primitive the list above forgot to name. **Nine are new.** `lucide-react` icons and `framer-motion` transitions enter *through* these primitives — a surface importing either directly is a review rejection, same rule as raw hex.
- **Every primitive ships keyboard-operable and labelled** (§4.11), so accessibility is inherited rather than retrofitted six times.
- **A `/design` route** rendering every primitive in every state. It makes the Friday UI-consistency check (§8) mechanical, and it is where the `axe-core` pass runs first.

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

This is the most-scrutinised screen in the product: it is where a judge decides whether ORCA is genuinely multi-agent or a chatbot with agent-shaped labels. It gets built as a first-class surface, not as a debug panel.

**Source of truth:** the OpenTelemetry span stream from §9.18 — the same stream that populates `audit_trace_log`. One pipeline, two views. The judge-facing trace panel and the compliance-facing audit log are never two systems to keep in sync.

**Renderer: React Flow (`@xyflow/react`).** Hand-rolling DAG layout with pan, zoom, selection and edge routing is a week of work with a worse result. Layout is left-to-right by execution depth (Planning → parallel specialists → Risk → Reporting), computed once per trace with `dagre` and cached — the graph does not re-layout on every SSE frame.

**Node anatomy — this is the part that carries the requirement.** A node is not a labelled box; it is a summary of that agent's reasoning, readable without clicking:

```
┌─────────────────────────────────────────────┐
│ ⚓ Agent 7 · Risk Assessment      HIGH  1.2s │  ← icon, agent, confidence tier, latency
│ ─────────────────────────────────────────── │
│ Hs 2.4 m vs class band 2.0 m → exceeded     │  ← one-line reasoning summary
│ 3 sources · deterministic · no LLM          │  ← provenance count + how it decided
└─────────────────────────────────────────────┘
```

Clicking a node opens the inspector drawer with the full `AgentResult` envelope (Architecture §6): `inputs_consumed`, `outputs`, `source_provenance` with per-source timestamps and freshness, `confidence`, latency, and the model + tier for the agents that used one. Deterministic agents say **"deterministic — no LLM"** in the drawer, which is Ground Rule 2 made visible rather than claimed.

**Encoding — every visual channel carries information, and none of it is colour alone:**

| Channel | Encodes |
|---|---|
| Node border colour **+ tier label text** | Confidence: HIGH / MEDIUM / LOW / degraded |
| Node fill | Execution state: pending (dim) · running (pulse) · done · cancelled (dashed) · failed (red border + ✗) |
| Edge animation | A hand-off currently in flight |
| Edge label | What crossed the edge — `verdict`, `hazards[3]`, `geofence_status` |
| Edge style | Solid = data hand-off · dashed = Critic re-invocation loop · dotted = early-exit cancellation |
| Group box | Parallel fan-out — WIA ∥ GRA sit in one bounding box, so parallelism is *seen*, not inferred |

**Live and replay are the same component.** During a query, spans arrive over SSE and nodes light in real time; afterwards the same graph re-renders from `audit_trace_log` for any historical `query_id`. That is what makes differentiator 5 (visible Critic self-correction) and the §4.10 feedback drill-down nearly free: both are a stored trace opened in this view.

**Motion, and its limit.** Node pulses and edge flow use Framer Motion, gated on `prefers-reduced-motion` (§4.11). Under reduced motion, state changes are instant and the running state is carried by a text label rather than a pulse.

**Two renderings:**

1. **Live activity strip** — during a query, a horizontal row of agent pills that light as spans open and close, with elapsed time. Shown to navigator / researcher / authority. It is the same span stream, collapsed — not a second implementation.
2. **Reasoning graph** — the full DAG above, at `/reasoning` and as an in-place expansion from any answer card.

**Toggle defaults by persona:**

| Persona | Activity strip | Reasoning graph | Default |
|---|---|---|---|
| fisherman | ✗ — plain one-line progress instead | ✗ absent entirely | — |
| commercial_navigator | ✅ | available | off |
| researcher | ✅ | available | **on** |
| coastal_authority | ✅ | available | off |
| unresolved | ✗ | reachable via "Show technical detail" | off |

**Why the fisherman surface removes it rather than collapsing it:** on a small screen in bad conditions, a reasoning graph competes for attention with the GO/NO_GO badge. That is not clutter, it is a safety regression. The fisherman gets a plain progress line and, if they ever want more, the persona-correction tap (§2.5) re-renders the *already-computed* facts in a richer persona instantly — no re-query. That control is also the cleanest live demonstration that intent and persona are genuinely decoupled.

**Owner:** S1 (span stream, node/edge payload), on S6's design tokens. **Lands:** Phase 1 (activity strip + trace capture), Phase 3 (full graph, inspector drawer, replay).

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

### 4.7 Map engine, performance budget & layer lifecycle

The map carries seven layer types over a 720×720 GEBCO grid, EEZ/MPA polygons with thousands of vertices, and PFZ point sets — on a phone, at sea, on a bad connection. Left alone that becomes an unusable map, and the fisherman persona is exactly the user who suffers first.

**Engine: MapLibre GL JS.** The Phase-0 scaffold used Leaflet; §4.1 replaces it, and this section is written against the replacement. What changes in practice:

| Concern | Leaflet (was) | MapLibre GL JS (is) |
|---|---|---|
| Polygon rendering | DOM/SVG paths — frame drops past ~50 polygons | GPU-composited vector rendering, hundreds of geofence polygons at 60 fps |
| Restyling on alert | Re-create the layer | `setPaintProperty` — a uniform change, no re-upload |
| Raster fields | `L.tileLayer` XYZ | `raster` source, same XYZ pyramid — the tiling job below is unchanged |
| Zoom-dependent detail | Manual layer swap per zoom band | Native zoom expressions in the style |
| Bathymetry legibility | Flat 2D only | `pitch: 35°` on the researcher/navigator surfaces for depth reading |

**Budget — measured on a mid-range Android over 3G, and treated as a build target, not an aspiration:**

| Metric | Budget |
|---|---|
| Payload per layer, over the wire | ≤ 300 KB gzipped |
| Initial map interactive | ≤ 2.5 s |
| Layer toggle → painted | ≤ 400 ms |
| Sustained frame rate while panning, default layer set | ≥ 45 fps |
| Concurrent heavy layers (raster/heatmap), mobile | **2** |
| Concurrent heavy layers, desktop | 4 |

**Raster and gridded fields (SST, chlorophyll, bathymetry, wave height).** Served as XYZ tiles, never as a whole grid pushed to the browser. The backend pre-renders the pilot-region grids to a tile pyramid at build time (zoom 5–11) and serves them statically; MapLibre's `raster` source handles viewport-and-zoom fetching for free. Where a source already publishes WMS (MOSDAC, Copernicus), proxy the WMS rather than re-tiling it. **Never** ship a 720×720 NetCDF slice to the client.

**Vector layers (EEZ, IMBL, MPA, districts).** Pre-simplified per zoom band with Douglas–Peucker at generation time — tolerance ~0.01° for z≤7, ~0.002° for z8–10, full precision z≥11 — and coordinates truncated to 5 decimals (~1 m, well past what any of these decisions need). Simplification happens in the pipeline, not in the browser. **One carve-out, and it is load-bearing: geofence containment tests always run server-side against full-precision geometry in Agent 6.** The simplified polygon is a *drawing* of the boundary; it is never the thing we test a breach against. A simplified IMBL that shifts 200 m is a rendering artifact — treating it as truth would be a legal incident.

**Layer lifecycle.** One map instance per surface, mounted once; layers are added to and removed from it, never by remounting the map. GeoJSON layers update through `source.setData()` rather than teardown-and-recreate — that is what keeps a toggle inside the 400 ms budget. Layers mount on demand and unmount when deselected or scrolled out of the viewport; nothing stays resident "in case". Default-on sets are per persona (fisherman: hazards + PFZ + position; researcher: whatever they pick), and requesting a third heavy layer on mobile evicts the least-recently-used one with a visible notice rather than silently degrading the frame rate.

**WebGL fallback — stated because the fisherman's phone is the one that fails.** If `maplibregl.supported()` returns false (no WebGL, blocklisted driver, GPU-less device), the map area renders a static tile snapshot of the region plus the full textual verdict, hazard list and distance/bearing readouts. **A missing map is never a missing answer** — every spatial fact the map shows is also stated in text on the same card, which is the §4.11 severity rule applied to geometry.

**Instrumentation.** `layer_load_ms`, `render_ms`, `payload_bytes` and dropped-frame count per layer, logged to the console in dev and to the existing OTel stream in staging. Engineering visibility only — this is a budget check, not an observability platform.

**Owner:** S5, with the tiling job in the Phase 2 data pipeline. **Lands:** Phase 1 (MapLibre shell + vector layers), Phase 2 (tiles + simplification + lifecycle), Phase 4 (budget verification on a real device).

### 4.8 Forecast time slider — how it actually works

**It never re-runs the agent graph.** Dragging a slider must not fire twelve agents; it is a frame swap over data already fetched.

**The real temporal resolution, from the data on disk — not assumed:** `ww3_pilot_forecasts.csv` carries **56 time steps at 3-hour spacing**, `2026-09-01T00:00Z` → `2026-09-07T21:00Z` — a 7-day horizon. That is the WW3 cadence and the slider inherits it. Nothing here is hard-coded to 3h in application logic: the frontend reads the timestamp axis the backend returns and renders whatever steps exist.

**Flow:**

1. A forecast query returns, alongside the answer, a `forecast_frames` block: `{layer, frames: [{t, tile_url | geojson_ref}], t_min, t_max, step_seconds, source_provenance}`.
2. The frontend holds the frame index in client state. Vector frames for the pilot region are small enough to prefetch whole; raster frames prefetch the current frame ±2 and fetch the rest lazily.
3. Moving the slider swaps the rendered frame. **No API call for a prefetched frame, no agent invocation ever.**
4. The selected time is displayed in full — absolute local time *and* relative ("+18 h") — because "which forecast hour am I looking at" is a safety-relevant question, not a nicety.

**Mixed cadences — the synchronisation rule.** WW3 waves are 3-hourly, Open-Meteo weather is hourly, HYCOM currents are daily, MOSDAC SST is daily. **The slider's axis is the coarsest layer currently displayed**, and every finer layer is sampled at the selected instant (nearest-neighbour within half a step; otherwise the layer greys out rather than extrapolating). A layer with no frame within tolerance renders as unavailable at that time — never as the nearest value pretending to be current. A "sampled at 12:00, source step 00:00" note appears in the layer legend, so the mismatch is visible rather than silently smoothed.

**Owner:** S5 (frontend + frame payload), S3 (`forecast_frames` assembly in the loader layer). **Lands:** Phase 2.

### 4.9 Delivery channels — one response, many renderers

The master requirements name web, Android, SMS bot and IVR for the lowest-connectivity zones. The plan builds the web app. Rather than leave the rest unmentioned, the pipeline is structured so that the channel is a rendering decision at the edge, not an assumption baked through the system:

```
ORCA response (Agent 9, structured)
   → channel renderer   (how much fits, and in what form)
   → dispatcher         (how it physically leaves the building)
```

**Channel status — stated plainly:**

| Channel | Status | Notes |
|---|---|---|
| Web | 📋 Specified → Phase 1 | The build target |
| PWA (installable, offline verdict cache) | ⏸️ Deferred to after the internal round | §5.2; the degraded-response contract keeps it cheap |
| In-app notification | 📋 Specified → Phase 3 | The Sentinel dispatch path we actually ship |
| SMS | 🟡 Simulated | Renders the exact Sagar-Vani payload; no gateway. See below |
| IVR (voice callback) | ⏸️ Deferred | Renderer defined, no telephony provider |
| USSD | ⏸️ Deferred | Renderer defined, requires a telecom partnership |

WhatsApp is **not** an ORCA channel and is not planned.

**Renderers are cheap and worth defining now**, because they force the response to stay structured rather than becoming a wall of HTML: `render_web()` (full payload with map and provenance), `render_sms()` (≤160 GSM-7 chars, verdict + one hazard + timestamp, vernacular), `render_ivr()` (TTS script — short sentences, no numerals-as-digits, one repeat), `render_ussd()` (≤182 chars, menu-structured). Each is a pure function of the same `ORCAState`.

**Dispatch — the honest statement, and the one to use in Q&A:**

> The ORCA notification layer is gateway-agnostic. The current implementation uses a simulated in-app dispatcher that renders the exact payload that would have been transmitted; a production deployment connects the same `Dispatcher` interface to a compliant SMS/IVR gateway. Indian SMS delivery additionally requires DLT template registration, which is a commercial and regulatory process rather than an engineering one.

```
Dispatcher (protocol)      send(recipient, rendered_payload, channel) -> DispatchResult
  ├── InAppDispatcher      ✅ ships — writes to the notification feed, shows the payload verbatim
  ├── SMSDispatcher        ⏸️ interface only — raises NotImplemented, documented as gateway-pending
  └── IVRDispatcher        ⏸️ interface only
```

Sentinel calls `Dispatcher`, never a gateway. `sentinel_subscriptions.channels` already records the user's preference, so introducing a real gateway later is registering one class — not touching Agent 11. **Nothing anywhere claims a message was delivered when it was rendered.** A simulated dispatch is labelled `SIMULATED` in the UI and stored with `status = 'degraded'` in the audit log.

**Owner:** S3 (dispatcher, Sentinel), S6 (renderers). **Lands:** Phase 3.

### 4.10 Advisory feedback — "this looks wrong"

Distinct from the persona-correction tap, which only changes how an already-computed answer is rendered. This is about the answer being **wrong**, and the requirements ask for it explicitly.

Every advisory card carries three controls: **Helpful** · **Not accurate** · **Report issue**. One tap, no dialog; "Report issue" additionally opens an optional free-text box. On the fisherman surface these are icons with visible text labels, placed below the verdict badge — never competing with it.

Stored in `advisory_feedback` (§5.3) with `query_id`, `advisory_ref`, `session_id`, `user_id` where authenticated, `kind`, optional `comment`, timestamp. Because `query_id` is the same key `audit_trace_log` is written under, a single join reconstructs the complete agent trace, every source, and every confidence tier behind a flagged answer. That traceability *is* the feature.

**Explicitly not doing:** no automatic retraining, no threshold auto-tuning, no model updates from feedback events. A fisherman disagreeing with a wave-height threshold is a signal to review, not an instruction to move the threshold. Analysis is manual and out of scope for the month.

**Owner:** S6 (control + API), S4 (surfacing it on analytic cards). **Lands:** Phase 3.

### 4.11 Accessibility — WCAG 2.1 AA is the target, and it is testable

Stated as the target rather than "an accessibility pass", so it can be failed rather than felt. Baseline, applied as surfaces are built rather than retrofitted:

- **Semantic HTML** — real `<button>`, `<nav>`, `<main>`, `<h1..h3>` hierarchy. No `<div onclick>`.
- **Labels** — every control has an accessible name; icon-only buttons (including SOS) carry `aria-label`. Form fields use `<label for>`, never placeholder-as-label.
- **Keyboard** — every interactive element reachable and operable by keyboard, logical tab order, no traps, a skip-to-content link. Map controls: zoom, layer toggles and the time slider are all keyboard-operable; the slider responds to arrow keys with `role="slider"` and `aria-valuetext` announcing the forecast time.
- **Focus** — a visible focus ring at ≥3:1 against its background. Never `outline: none`.
- **Contrast** — ≥4.5:1 body text, ≥3:1 large text and UI boundaries. The sunlight-legibility requirement pushes the safety palette well past this anyway.
- **Live regions** — streaming answers and incoming Sentinel alerts announce via `aria-live="polite"`; a distress state uses `assertive`.
- **Motion** — honour `prefers-reduced-motion` for the activity strip and any map animation.

**The rule that matters most here: severity is never carried by colour alone.** Every alert leads with a text severity token, and colour reinforces it:

```
✗  a red card
✓  DANGER — Lightning detected within 8 km of your position    (red, ⚡ icon, text token)
✓  CAUTION — Wave height 2.4 m exceeds your vessel class band   (amber, ▲ icon, text token)
```

This is not only an accessibility fix. It is the same discipline as Ground Rule 3: the screen must state what it means, not encode it.

**Testing — six flows, and they are the exit criterion**: Ask, Safety, Map (including layer toggles and the time slider), Fishing Zones, alert interaction, feedback interaction. Each verified by (1) keyboard only, no mouse; (2) NVDA on Windows or VoiceOver on iOS; (3) an automated `axe-core` pass in CI, zero criticals.

**Owner:** S6 (design system, so the baseline is inherited by every slice rather than reimplemented six times). **Lands:** built in from Phase 1, audited in Phase 3.

---

## 5. Repository Layout, Platform & Deployment

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
│   │   │   └── normalize.py # the common data frame (§5.6) — every loader exits through it
│   │   ├── db/              # SQLAlchemy models + repositories over the §5.3 schema
│   │   ├── auth/            # registration, login, sessions, RBAC dependencies (§5.4)
│   │   ├── channels/        # channel renderers + Dispatcher implementations (§4.9)
│   │   ├── resilience.py    # timeouts, fallback cascade, degraded responses (§5.7)
│   │   ├── state.py         # ORCAState (Architecture §5) — frozen contract
│   │   ├── contracts.py     # AgentResult envelope (Architecture §6) — frozen contract
│   │   ├── trace.py         # OTel spans -> audit_trace_log
│   │   └── api/             # FastAPI routes, SSE streaming
│   └── tests/
│       ├── unit/
│       ├── fixtures/        # recorded upstream responses — the only data E2E touches
│       └── e2e/             # full-graph fixture replays (§5.8)
├── frontend/                # Next.js (App Router)
│   ├── app/                 # one directory per §4.2 route
│   ├── components/
│   │   ├── ui/              # design system primitives (§4.1) — the only place tokens are consumed
│   │   ├── map/             # MapLibre shell, layer registry, controls, time slider
│   │   ├── charts/          # Recharts wrappers — series, bands, confidence meters
│   │   ├── reasoning/       # activity strip, React Flow DAG, node inspector drawer
│   │   ├── persona/         # selector, correction control, visibility matrix
│   │   └── evidence/        # provenance popovers, citation chips
│   ├── app/design/          # every primitive in every state — the UI consistency check (§8)
│   └── lib/                 # SSE client, typed API contracts, prefers-reduced-motion hook
├── data/                    # gitignored — already present on every machine, kept in sync out-of-band
├── scripts/                 # existing procurement + new sync tooling
├── docs/                    # architecture, requirements, this plan
└── infra/                   # docker-compose (Postgres+PostGIS, Redis), CI
    └── db/                  # ✅ numbered SQL migrations + migrate.sh (§5.3)
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

### 5.3 Persistent state — the PostgreSQL + PostGIS schema

**Status: ✅ defined and committed** — [`infra/db/001_init.sql`](../infra/db/001_init.sql), applied by [`infra/db/migrate.sh`](../infra/db/migrate.sh). It lands in **Phase 0**, not Phase 2, for one reason: S1 needs `audit_trace_log` on Day 1 and S3 needs `sentinel_subscriptions` in Week 3, and two people improvising two schemas for the same entities is an expensive Week-4 discovery.

**The scope rule, which is the important decision here:** this database holds ORCA's *operational* state — who the user is, what they own, what they asked, what we answered, what we monitor. **Scientific source data never enters it.** The 18.72 GB `data/` tree stays on the filesystem (object storage after deployment) and is read by the loader layer. Postgres stores *references* to datasets, never copies of them. Putting a GEBCO grid in a table would be slower than reading the NetCDF and would fork the provenance story.

| Table | Holds | Notes |
|---|---|---|
| `users` | identity, role, `default_persona`, language, `home_port` (Point), status | Identity is phone-or-email; `password_hash` is argon2id |
| `vessels` | owner FK, class, `draft_m`, registration, `last_position` (Point) | 1..n per user via `owner_user_id` — no join table needed |
| `sessions` | user (nullable — anonymous allowed), persona, language, channel | Anonymous sessions remain first-class |
| `conversation_turns` | per-turn original + normalized-English text, `query_id` | Architecture §5 `session_history` |
| `audit_trace_log` | `query_id`, agent, event, span ids, `inputs_consumed`, `outputs`, `source_provenance`, `confidence`, `status`, latency | Architecture §6 envelope, one row per agent execution |
| `sentinel_subscriptions` | user/vessel, `watch_point`/`watch_area`, thresholds, channels, enabled | Agent 11's subscriber list |
| `advisory_feedback` | `query_id`, kind, comment | §4.10 |

**PostGIS is used where geography is actually queried**, not decoratively: `users.home_port`, `vessels.last_position`, `sentinel_subscriptions.watch_point` / `watch_area`. All SRID 4326; distance comparisons cast to `geography` so they are metres rather than degrees. GIST index on every geometry column — Sentinel's hot loop is "which subscriptions fall inside this hazard polygon", which is a spatial join and nothing else.

**Constraints and lifecycle, since they encode real rules:** `ON DELETE CASCADE` from users to vessels, sessions and subscriptions (deleting an account removes their tracked locations — that is the privacy behaviour we want); `ON DELETE SET NULL` from feedback and audit rows to sessions (the compliance record survives account deletion, de-linked). `users_identity_present` requires phone or email. `sentinel_has_geometry` forbids a watch that watches nowhere. `draft_m > 0`, because a zero draft would silently pass every depth check in §4.6.

**Indexed:** every FK, `audit_trace_log(query_id, created_at)` for trace reconstruction, `audit_trace_log(status) WHERE status <> 'ok'` as a partial index for failure review, `sentinel_subscriptions(watch_type) WHERE enabled`, and the four GIST indexes.

**Sensitive columns — enumerated once, here, and referenced by §5.5:** `users.phone_e164`, `users.email`, `users.password_hash`, `users.home_port`, `vessels.registration_no`, `vessels.last_position`, `sentinel_subscriptions.watch_point`/`watch_area`. Every one of them either identifies a person or says where their boat is.

**Migration strategy:** numbered SQL files, applied in filename order, recorded in `schema_migrations`. No Alembic while there are no ORM models — adopt it if and when SQLAlchemy models become the source of truth. Migrations are forward-only; a mistake is corrected by `002_*.sql`, never by editing `001`.

**Owner:** S1. **Lands:** Phase 0.

### 5.4 Identity — registration, authentication, vessels

**FLAG 7 was the load-bearing gap.** The architecture assumes registered users throughout — Sentinel's "registered home port", persona resolution from "registered account role", `vessel_id` on distress handoff — and none of it existed. Without identity, Sentinel has nobody to notify and every session re-infers persona from scratch.

**This is an MVP, deliberately.** The goal is to make the architecture's assumptions real, not to build an identity platform.

**What ships:**

- **Registration / login** — phone (or email) + password, argon2id hashed. A short OTP flow is the realistic Indian pattern but needs the same SMS gateway we do not have (§4.9), so password it is, and the swap is one adapter later.
- **Sessions** — a signed HTTP-only cookie or bearer JWT (15-min access, 30-day refresh), `sessions` row per login. Anonymous use continues to work for everything that does not need identity; the fisherman who has not signed up still gets a safety verdict.
- **Profile** — persona/role, preferred language, home port (map picker → `users.home_port`).
- **Vessel registration** — name, class, draft, registration number; a user may register several and pick an active one. Draft flows straight into §4.6 corridor routing, which is why this is not cosmetic.
- **Authorization** — three roles, no more: `user` (own resources only), `authority` (district rollups, `/ops`, CAP composer, distress queue), `admin` (operational). Enforced as a FastAPI dependency at the route boundary. **Not** a permission matrix, not per-object ACLs — a hackathon RBAC that grows into one has already failed.

**The boundary that must not be crossed.** Being authenticated changes *rendering and access*, never *routing*. Agent 2 classifies intent from the query text alone; specialist agents still never see a persona; `AgentResult` still has no persona field. Authentication may populate `ORCAState.persona` as a resolved value instead of an inferred one — it may never reach an intent classifier or a specialist agent's inputs. This is the exact bug Architecture v2.0 fixed, and identity is the most tempting place to reintroduce it. **Enforced the same way as the vendor-SDK rule: a CI grep for `persona` under `orca/agents/` excluding Agents 1 and 9.**

**Sentinel uses this model, and does not get its own.** Agent 11 reads `sentinel_subscriptions` joined to `users` and `vessels` — subscriber, monitored geometry, associated vessel, notification channels. There is no separate Sentinel user table and no shadow profile store.

**Owner:** S1 (auth core, RBAC), S6 (registration and profile surfaces), S3 (Sentinel wiring). **Lands:** Phase 2 — auth core and vessel registration early in the week, so Phase 3's Sentinel has real subscribers to notify.

### 5.5 Security Considerations

**Read this section as scoped to a prototype.** ORCA as built during this month is **demo-grade**, and the table below says exactly which line falls where. Claiming otherwise about a system that stores where fishing boats are would be the worst kind of overstatement.

**Threat model, briefly.** The asset worth protecting is not the science — SST is public. It is **the association between a person and a position**: home port, last known vessel position, watch locations, registration number. That data is a physical-safety concern, not merely a privacy one, and it drives every rule below.

| Control | This build | Production would additionally need |
|---|---|---|
| Authentication | ✅ password + JWT/session cookie (§5.4) | OTP/2FA, lockout, breach-password screening |
| Authorization | ✅ three roles at the route boundary | Per-object ACLs, delegated district scoping |
| Transport | ✅ HTTPS in deployment | HSTS, cert pinning on mobile |
| Secrets | ✅ env vars only, `.env` gitignored, `.env.example` zero-valued | Managed secret store, rotation |
| Input validation | ✅ Pydantic on every request | Fuzzing, schema-diff regression |
| Location privacy | ✅ owner-only reads, coarsened aggregates | Retention automation, k-anonymity on rollups |
| Logging hygiene | ✅ coordinates/identifiers redacted | Central log pipeline with DLP |
| Audit | ✅ security events into `audit_trace_log` | Tamper-evident append-only store |
| Rate limiting | ⏸️ deferred | Per-IP and per-account throttles, WAF |
| Encryption at rest | ⏸️ deferred (host-level only) | Column-level encryption on position data |
| Penetration test | ⏸️ not performed | Third-party assessment before public launch |

**Location privacy — the rules, concretely:**

1. **Nobody reads another user's exact position.** Vessel position and home port are returned only to the owner. There are exactly two exceptions, both narrow: an `authority` role during an **active distress** (Agent 12 has fired, and the read is itself audited), and the user's own Sentinel evaluations.
2. **Aggregates are coarsened.** District rollups on `/ops` report counts per sector, never plottable individual vessels. If a cell contains fewer than 5 vessels it reports "<5" rather than a number that could be de-anonymised against a known fleet.
3. **Positions are not written unless a feature needs them.** A one-off safety query uses a coordinate in the request and does not persist it. `vessels.last_position` is written only when the user has an active Sentinel watch or an open voyage.
4. **Retention.** Position history is not accumulated at all in this build — `last_position` is a single overwritten value. That is a data-minimisation decision, not an omission.

**API security.** Nothing from the client is trusted: every request body and query parameter is validated by a Pydantic model; coordinates are range-checked (`-90..90`, `-180..180`) and rejected outside the pilot/India bbox where the endpoint is region-scoped; `user_id` and `vessel_id` are **never accepted from the client as a subject** — the subject comes from the verified token, and any supplied vessel id is checked for ownership before use. `persona` from the client is a *rendering hint only*, validated against the enum, and is never permitted to reach routing (§5.4). SQL is parameterised throughout; PostGIS geometries are constructed from validated numerics, never from client-supplied WKT.

**Secrets.** No API key, database password, token or credential is ever hard-coded, committed, or logged. `.env.example` stays zero-valued and is the only credential file in git. A CI secret-scan step fails the build on a committed key — cheap, and it catches the mistake on the day it is made rather than after the repo is public.

**Logging.** Application logs carry `query_id`, agent name, status and latency. They do **not** carry coordinates, phone numbers, registration marks or tokens; a redaction filter drops these before the formatter, so a careless `logger.info(payload)` cannot leak position. Where a position genuinely must be traced, it goes to `audit_trace_log` under access control — not to stdout.

**Audit.** Login, failed login, registration, role change, vessel registration, subscription change and any authority read of another user's position are all written to `audit_trace_log` with `agent_name = 'security'`. One trace mechanism, not two.

**Owner:** S1. **Lands:** Phase 2 alongside auth; secret-scan and validation from Phase 0.

### 5.6 The common data frame — one normalization layer, not twelve

**FLAG 1.** The master requirements call harmonization "prerequisite infrastructure, not a bonus feature", and the failure mode if every agent normalizes for itself is specific and nasty: Agent 6 reads `(lon, lat)` from GeoJSON while Agent 5 reads `(lat, lon)` from a CSV, and a boundary-distance answer is silently wrong by hundreds of kilometres. Six engineers writing six transposes is how that ships.

**Every loader exits through one function.** Agents consume normalized objects; no agent implements its own CRS or time handling.

```python
# backend/orca/data/normalize.py
def normalize_to_common_frame(
    data,                          # xr.Dataset | gpd.GeoDataFrame | pd.DataFrame | dict (GeoJSON)
    *,
    source: SourceDescriptor,      # dataset id, authority, acquisition time, native CRS/units
    target_crs: str = "EPSG:4326",
    target_time_resolution: str | None = None,   # "1H" | "3H" | "1D" | None = keep native
    target_units: dict[str, str] | None = None,
) -> NormalizedFrame: ...
```

**What it fixes, and the ORCA convention for each:**

| Concern | Convention |
|---|---|
| CRS | EPSG:4326 internally. Reprojection is pyproj, never a hand-rolled formula |
| Axis order | **`(lon, lat)` in every internal payload and GeoJSON.** The single most likely silent bug in this system |
| Longitude range | −180..180 (HYCOM's 0..360 is converted on load) |
| Timestamps | tz-aware UTC, ISO-8601 with `Z`. IST appears only at the rendering edge |
| Temporal resampling | Explicit and downsample-only. Never interpolate a forecast to a finer grid than the model produced |
| Units | m, m/s, °C, hPa, metres depth positive-down. Knots and °F exist only in rendering |
| Missing values | `NaN`, never `-999`/`9999`/`0`. Sentinel values are mapped on load, and the count is recorded |
| Extents | Clipped to the pilot bbox where the caller asks; the clip is recorded in provenance |

**Provenance survives normalization — that is a hard requirement, not a nicety.** `NormalizedFrame` carries `.data` plus `.provenance`: source dataset id, authority tier, acquisition timestamp, native CRS, native units, the ordered list of operations applied (`reproject`, `resample`, `unit_convert`, `clip`, `fill_sentinel`), and the missing-value count. Agent 7 needs the acquisition time to compute a freshness-based confidence tier, and Ground Rule 3 needs the dataset name to reach the UI, so a normalizer that dropped metadata would break both. **Normalization is additive to metadata and never subtractive.**

**Runnable check** (Ground Rule 6): a round-trip test asserting that a known Thoothukudi coordinate survives GeoJSON → normalize → distance-to-IMBL with the same answer as the raw path, and that a 0..360 HYCOM longitude lands in the right hemisphere. That single test catches the axis-order and longitude-range bugs, which are the two that would otherwise reach a demo.

**Owner:** S3 (owns the loader layer already). **Lands:** Phase 1, Days 3–4 — before Agents 4, 5 and 6 build their tools on top of it. This is the one item on this list that cannot slip, because retrofitting it means rewriting every loader.

### 5.7 Error handling — built in Phase 2, verified in Phase 4

**FLAG 22.** Architecture §12 specifies a nine-scenario failover hierarchy; the plan only scheduled *rehearsing* it in Phase 4. You cannot rehearse code that was never written. The handling is built with the agents; Phase 4 keeps only the adversarial verification.

**Layered, in the order failures actually arrive:**

1. **Timeouts, everywhere.** Every upstream call carries an explicit timeout (default 5 s; 3 s on the safety path, where late is the same as absent). No unbounded external call exists anywhere in the codebase. A slow INCOIS never becomes a hung graph.
2. **Fallback cascade, declared not improvised.** Each source declares its ordered fallbacks in the catalog (Architecture §12.1) — INCOIS → cached local → Open-Meteo, and so on. Agent 3 walks the cascade; **each step down lowers the confidence tier and appends to `source_provenance`.** A degraded answer says which rung it came from.
3. **Validation on arrival.** A 200 response is not a valid dataset. Empty payloads, all-NaN grids, out-of-range values and stale timestamps beyond the source's own cadence are rejected as failures and fall through to the next rung. Silent garbage is worse than a clean error.
4. **Agent exception boundary.** Every agent node is wrapped: an unhandled exception becomes `AgentResult(status='failed', confidence='LOW_DATA', error_detail=...)`, written to the audit log, and the graph continues. **One specialist agent failing degrades the answer; it never takes down the request.**
5. **Conflicting sources** keep the architecture's existing behaviour: both values are surfaced with their provenance, confidence drops to MEDIUM, and the *conservative* value drives any safety verdict.
6. **All sources down.** An explicit degraded response — the last cached verdict with its age, forced to LOW-DATA amber, plus a plain statement that live data is unavailable. **No number is ever invented to fill a hole.**
7. **Safety path fails conservative.** If deterministic safety logic cannot obtain an input it requires, the result is CAUTION or NO_GO with the missing input named — never GO, and never an LLM asked to estimate the value. Ground Rule 2 applies hardest exactly here, because a fabricated wave height that reads GO is the one failure in this system that can kill someone.
8. **Circuit breakers — only where measured.** Deferred until Phase 4 and applied only to a source that demonstrably flaps under load. Adding five breakers on speculation buys latency and complexity we cannot justify.

Timeouts, the cascade and the exception boundary live in `orca/resilience.py` as decorators, so an agent opts in with one line rather than reimplementing the pattern.

**Owner:** S3 (cascade, since it owns the loaders), S1 (exception boundary and graph-level behaviour), S2 (the safety-path conservative rules). **Lands:** Phase 2 build → Phase 4 adversarial verification (kill each source in turn and confirm §12.2 fires).

### 5.8 Testing — one real end-to-end path, replayable in CI

**FLAG 13.** Unit checks per module (Ground Rule 6) do not tell us the graph works. One fixture-replayed end-to-end test does, and it is the regression net for the entire month.

**The flagship scenario, and it is deliberately the safety query:**

```
"நாளை காலை தூத்துக்குடி அருகில் கடலுக்கு போவது பாதுகாப்பானதா?"
  → Agent 1 ingress (language ID, translation)
  → Agent 2 planning (intent → routing)
  → Agents 4 + 6 in parallel (weather, geospatial)
  → Agent 7 risk assessment (deterministic verdict)
  → Agent 8 visualization
  → Agent 9 reporting (persona rendering)
  → Agent 1 egress (translation back to Tamil)
```

**Every upstream is a recorded fixture.** `tests/fixtures/` holds captured Open-Meteo, INCOIS, WW3 and boundary responses; the loader layer is patched to read them. The test runs offline, on any machine, at any time, and is byte-deterministic — an LLM is stubbed for the two prose steps, because prose wording is not what this test is asserting.

**Asserted, explicitly:** the routing decision matches the expected agent set; every hand-off writes into `ORCAState` as contracted; every `AgentResult` validates against the envelope schema (required fields present, no persona field on a specialist result); `source_provenance` is non-empty on every claim; the confidence tier matches the expected value for the fixture's freshness; the verdict is the exact expected `GO`/`CAUTION`/`NO_GO`; the map payload is valid GeoJSON with the expected layers; the final response is in Tamil.

**Plus three degradation variants** over the same fixtures, because §5.7 needs a net too: INCOIS returns 503 (expect fallback used, confidence dropped, provenance shows the rung), all sources down (expect degraded response, forced amber, no invented numbers), one agent raises (expect controlled `AgentResult`, graph completes).

**CI:** unit and E2E run on every PR alongside lint, typecheck, the vendor-SDK-import guard, the persona-leak guard (§5.4), secret scan (§5.5) and `axe-core` (§4.11). Nothing here needs a live API key, so CI stays green when an upstream is down — which is also the point.

**Owner:** S1 (harness and CI), each slice contributes its own fixtures. **Lands:** skeleton in Phase 1 as soon as the graph runs end-to-end; degradation variants in Phase 2 with §5.7.

### 5.9 Agent 8 (Visualization) — the tool specification the other agents already had

**FLAG 23.** Every other agent has an itemised tool table; Agent 8 had a sentence. Architecture §11 lists layer and chart *types* without an interface. Closed here at parity, preserving §11's types exactly.

**Separation of concerns, stated first because it is the design constraint:** Agent 8 performs **no scientific reasoning**. It transforms results other agents computed into renderable structures. Ocean Agent decides whether SST is anomalous; Visualization decides it becomes a heatmap with these bounds and this colour ramp. `Ocean Agent → scientific result`, then `Visualization Agent → GeoJSON/chart spec` — never `Visualization Agent → decides whether the sea is safe`. Agent 8 makes zero LLM calls (§3.2) and reads no raw dataset that a specialist has not already interpreted.

| Tool | Inputs | Output |
|---|---|---|
| `generate_map_layers` | `agent_results: list[AgentResult]` (required) · `intent` (required) · `persona` (required — complexity only) · `viewport_bounds` (optional) · `time_range` (optional) | `list[MapLayer]` |
| `generate_chart_specs` | `series_data` (required) · `chart_hint` (optional) · `persona` (required) | `list[ChartSpec]` |
| `generate_route_layer` | `route_segments` from Agent 6 (required) · `vessel_class` (optional) | `MapLayer` (Polyline, per-segment `CLEAR`/`CAUTION`/`BLOCKED` styling) |
| `generate_distress_layer` | `distress_event` from Agent 12 (required) | `MapLayer` (non-dismissible Distress marker) |
| `generate_sentinel_badges` | `active_subscriptions` (required) · `triggered: bool` | `list[MapLayer]` (watch indicators) |
| `validate_payload` | any `MapLayer`/`ChartSpec` | `(bool, list[str])` — called on every payload before egress |

**Coordinate and time contract:** inputs arrive as `NormalizedFrame` (§5.6) — EPSG:4326, `(lon, lat)`, UTC. Agent 8 reprojects nothing and converts no timezone; if a payload arrives unnormalized that is a bug in the producing agent, not something Agent 8 patches over.

**`MapLayer` output:**

```
layer_id, layer_type, geojson (FeatureCollection | null), tile_url (raster/tiled | null),
bounds [w,s,e,n], timestamps [] | null, forecast_frames [] | null   # §4.8
style_hints {palette, opacity, min_zoom, max_zoom, simplify_tolerance}
weight: heavy | light                                               # §4.7 lifecycle budget
persona_visibility [], source_provenance [], result_refs []         # back to AgentResult
```

**Layer types — unchanged from Architecture §11.1:** PointMarker · Polygon · Polyline · Heatmap · Raster (tiled/WMS) · Distress marker (non-dismissible) · Sentinel watch indicator.
**Chart types — unchanged from §11.2:** TimeSeries · BarChart · RadarChart · WindRose. Each maps to a Recharts component (`AreaChart`/`LineChart`, `BarChart`, `RadarChart`, and a `RadialBarChart` for the wind rose), so a `ChartSpec` is data plus bounds plus a colour ramp key — never markup, and never a rendering decision made in the backend.

**Validation is mandatory, not advisory.** `validate_payload` runs on everything before it leaves the backend: geometry structurally valid and correctly wound, coordinates within the declared bounds and inside plausible India-region ranges, `layer_type` in the enum, timestamps tz-aware and monotonic, feature count within the §4.7 budget (over budget → simplify or tile, never ship), `source_provenance` non-empty. A payload that fails validation is dropped with a logged error and a degraded response — a malformed GeoJSON that blanks the MapLibre canvas during a demo is a failure we can prevent in the backend.

**Provenance:** every layer and chart carries `source_provenance` and `result_refs` pointing back to the `AgentResult` (and thus the `query_id`) it was built from. That is what lets a click on a rendered feature open the provenance popover (differentiator 3) without a second query.

**Owner:** S5. **Lands:** Phase 1 (map + point/polygon layers), Phase 2 (heatmap, raster tiles, charts, validation), Phase 3 (route, distress, Sentinel layers).

---

## 6. Phase Plan

### Phase 0 — Foundation & Unblocking · Days 1–2

**Goal:** every one of 6 engineers can clone, install, run, and see something on screen.

- Confirm credentials across all six machines (§1.1)
- Repo scaffolding per §5; `docker-compose` with Postgres+PostGIS and Redis; a working backend `Dockerfile` (reproducible envs now, deployable later)
- **Freeze the contracts:** `ORCAState`, `AgentResult`, tool signatures. Everything downstream depends on these; they land before feature work, not alongside it
- **Apply the database schema** (§5.3) — `infra/db/migrate.sh` against the compose Postgres. It exists already; Phase 0 is where it starts being used, so nobody improvises a second one
- LLM provider abstraction (§3.1) with two providers registered
- CI: lint, typecheck, test, the vendor-SDK-import guard, the persona-leak guard (§5.4) and a **secret scan** (§5.5)
- Endpoint liveness sweep (§1.2)
- **Reproducible local envs — Day 1, first task, S1.** `pip install -r backend/requirements.txt` into a clean venv and `npm ci` in `frontend/`. Both trees are currently installed *partially* on at least one machine (backend venv has no `pandas`, so six test modules fail at import; `frontend/node_modules` predates the current `package.json`), which means "it passes in CI" and "it runs here" are already two different claims. Phase 0's whole point is that they stop being
- **Frontend stack port (§4.1) — S5 + S6, Day 1, before anyone adds a layer.** Install MapLibre + `@vis.gl/react-map-gl`, Recharts, React Flow, lucide-react, Framer Motion; remove Leaflet, `react-leaflet` and `@types/leaflet`; **then port `MapView.tsx`'s existing layers** per the §4.1 table — GeoJSON style function → data-driven paint expression, `CircleMarker`s → one circle layer, `bindPopup` HTML → `<Popup>`. This is a port with a working before-state, so it is checked by behaviour, not by the diff: the five backend routes it calls must return the same picture afterwards
- **Design system v0 (§4.1) — S6, Days 1–2, ahead of the surfaces.** Invert `globals.css` to the dark-first ocean base, add glass / confidence / focus tokens, drop the `-bg` half of the safety triad and rename `danger` → `no-go` **together with its three call sites** (§4.1); keep `Card`/`Badge`/`Field`/`SourceChip`, add the nine missing primitives, all keyboard-operable and labelled from the first commit
- **`/design` route + `axe-core` in CI — S6, Day 2.** The route does not exist today. It renders every primitive in every state, and the frontend CI job gains an `axe-core` step that fails the build on a violation — an accessibility baseline nobody runs is not a baseline (§4.11)
- Next.js app skeleton with the §4.2 nav shell rendering (dead links are fine) — **already true**, ten routes and the persona visibility matrix are in place; Phase 0 only re-bases them on the new tokens and primitives
- **Assign the Cyclone Gaja procurement task to S3** (§1.3) — small, and it must not be discovered in Week 4

**Exit criteria** — each one is a command someone runs, not a judgement call:

| # | Criterion | Check |
|---|---|---|
| 1 | Compose stack up on all 6 machines | `docker compose up -d` then `pg_isready` and `redis-cli ping` |
| 2 | Schema applies from empty on all 6 | `infra/db/migrate.sh` against a fresh volume; every §5.3 table present |
| 3 | Envs reproducible, tests actually collect | `pytest -q` collects 0 errors locally *and* in CI; `npm ci && npm run build` clean |
| 4 | CI green with all four guards firing | vendor-SDK, persona-leak, secret-scan, plus the new `axe-core` step |
| 5 | Mock `/query` SSE renders in the browser | `/` streams tokens from `backend/orca/api/main.py`'s `text/event-stream` route |
| 6 | Leaflet gone | `grep -ri leaflet frontend/app frontend/package.json` returns nothing |
| 7 | MapLibre basemap on the pilot region | `/map` renders CARTO Dark Matter bounded to 77.5–80.5 E / 7.5–10.5 N |
| 8 | **The ported layers still work** | EEZ/MPA polygons, PFZ points and click→depth/bearing behave as they did on Leaflet — the port loses no capability |
| 9 | Design system is real | `/design` renders every primitive, `axe-core` clean, and `grep -rE "#[0-9a-fA-F]{6}" frontend/app --include=*.tsx` returns nothing (raw hex lives in `globals.css` only) |

---

### Phase 1 — Core Safety Vertical Slice · Days 3–7

**Goal:** one query — *"Is it safe to go to sea tomorrow morning near Thoothukudi?"* — asked in Tamil, answered end-to-end in Tamil, with a real deterministic verdict, a real map, and a captured trace.

Full detail and per-person assignment: **[`ORCA_Phase1_Plan.md`](./ORCA_Phase1_Plan.md)**

- **`normalize_to_common_frame` (§5.6) — Days 3–4, before any agent tool is written on top of it.** This is the one item in Phase 1 that cannot slip; retrofitting it means rewriting every loader
- Agent 7 (Risk Assessment) with vessel-class deltas and confidence tiers, properly tested
- Agents 4 (Weather) + 6 (Geospatial) — minimum viable tool set for the safety path
- Agent 12 (Distress) — pattern detection + MRCC surfacing. **Built now, not deferred**; it is the highest-severity gap the architecture audit found
- Agent 1 (Language) — Tamil + Hindi ingress/egress
- LangGraph skeleton: Planning → [WIA ∥ GRA] → RAA → Reporting
- Agent 8 (Visualization) — point and polygon layers with `validate_payload` (§5.9)
- Frontend: nav shell, persona system, Ask + Safety surfaces, **MapLibre map shell with vector hazard/PFZ/boundary layers** (§4.7), streaming verdict card, **live agent activity strip** (differentiator 1) — all built from the Phase 0 primitives, none re-invented per slice
- **End-to-end fixture test skeleton (§5.8)** — stood up the day the graph first runs end-to-end, not later

**Exit criteria:** the Tamil safety query returns a correct verdict end-to-end · the same query in Hindi and English works · SOS surfaces MRCC contact in under 2 seconds · every displayed number carries a source · the trace is captured (rendering it is Phase 3) · **the E2E fixture test passes in CI with no network access**.

---

### Phase 2 — Full Agent Roster & Multi-Intent · Days 8–14

**Goal:** all nine core agents live; the system answers every PS sample-query category, not just safety.

- Agent 5 (Ocean Analytics) — SST/chlorophyll correlation, PFZ proximity + persistence scoring, tide prediction, diagnostic mode
- Agent 3 (Marine Data Discovery) — full catalog routing with **narratable** source selection (§4.4). This is the PS's "tool selection" requirement; it must be visible, not internal
- Multi-intent: union resolution (§4.1), no-match fallback (§4.2)
- Agent 9 (Reporting) — full persona rendering matrix, evidence citations, export-formatter mode
- Researcher persona end-to-end: structured report, CSV/NetCDF export
- **Identity: registration, login, profile, vessel registration, three-role RBAC (§5.4)** — early in the week, so Phase 3's Sentinel has real subscribers rather than a mock list
- **Security controls (§5.5)** — Pydantic validation on every route, ownership checks, log redaction, security events into the audit log
- **Error handling (§5.7)** — timeouts, fallback cascade, arrival validation, agent exception boundary, degraded-response rendering. Built here, verified in Phase 4
- **Map performance (§4.7)** — raster tile pyramid for the pilot region, per-zoom polygon simplification, layer lifecycle
- **Forecast time slider (§4.8)** — `forecast_frames` payload over the 56 WW3 steps, no agent re-invocation
- Agent 8: heatmap, raster, chart specs (§5.9) — rendered through the shared Recharts wrappers, not per-surface chart code
- Frontend: Map explorer with real layers, Fishing Zones, Trends, Data surfaces; **provenance popovers** (differentiator 3); **source-selection narration** (differentiator 4)
- Redis caching with source-cadence-aware TTLs (§9.1, §9.11)
- **LLM provider bake-off** (§3.3) — now that Agents 5 and 9 have real prompts to score against
- **Cyclone Gaja data procured (§1.3)** — IBTrACS best-track + ERA5 Nov-2018 fields. Due end of Phase 2
- E2E degradation variants (§5.8): source 503, all-sources-down, agent raises

**Exit criteria:** all 8 PS sample queries return substantive answers · researcher export produces a valid CSV with full metadata · multi-intent queries visibly activate the union of agents · a user can register, add a vessel, and see their own home port — and cannot see anyone else's · killing INCOIS in a fixture yields a degraded answer with the fallback rung named, not a crash · the time slider moves through 56 frames with zero agent invocations.

---

### Phase 3 — Differentiation: Sentinel, Critic, Voice, Personas · Days 15–21

**Goal:** the capabilities that separate ORCA from a RAG chatbot. This is the week that wins or loses the demo.

- **Agent 11 (Sentinel)** — background monitor, threshold-crossing detection, reading **real subscribers** from `sentinel_subscriptions` (§5.3/§5.4). **Dispatch is simulated in-app** and labelled `SIMULATED`: the alert lands in the UI and renders the exact Sagar-Vani SMS payload that would have been sent, rather than sending it. Behind the `Dispatcher` interface of §4.9, so a real gateway is a registered class and not a refactor. (A real Indian SMS gateway also needs DLT registration, which does not fit a four-week window.) Fixed polling first; adaptive frequency (§9.17) only if ahead
- **Channel renderers (§4.9)** — `render_web`, `render_sms`, `render_ivr`, `render_ussd` over the same response. SMS is simulated; IVR and USSD ship as renderers with no delivery mechanism and are documented as deferred, not as working
- **Advisory feedback (§4.10)** — Helpful / Not accurate / Report issue on every advisory card, joined to the audit trace by `query_id`
- **Agent 10 (Critic)** — depth-triggered, with the async-upgrade carve-out so it never blocks a safety verdict
- **Voice pipeline** — Bhashini ASR/TTS with local Whisper fallback, wired for the fisherman surface
- Full language coverage across all named coastal languages
- All four personas complete + persona-correction control (differentiator 7)
- **Reasoning graph explorer** (differentiator 2) — the full React Flow DAG of §4.4: per-agent reasoning summaries on the node face, confidence and execution state encoded in border/fill *and* text, parallel fan-out drawn as a group box, Critic loops and early-exit cancellations drawn as real edges, node click opening the `AgentResult` inspector, and the same component replaying any historical `query_id`. This is the screen the demo is judged on — it gets a whole slice-week, not an afternoon
- Sentinel watch badges rendered live on the map (differentiator 6)
- ⏸️ **deck.gl wind/current flow overlay (§4.1) — only if Phase 3 is ahead of schedule.** It is an overlay on a working map, so cutting it costs nothing; starting it before the reasoning graph is done would be the wrong trade
- **Voyage planner: the constraint-aware corridor route** (§4.6) — the committed design, not a fallback. A* is explicitly out of scope
- District Ops surface: threat matrix, CAP payload, broadcast composer — with the §5.5 aggregation rules (counts per sector, never plottable individual vessels)
- **Accessibility audit against WCAG 2.1 AA (§4.11)** — keyboard-only and screen-reader passes over the six named flows, `axe-core` clean in CI. The baseline was built in from Phase 1; this week is where it gets *tested*

**Exit criteria:** a Tamil voice query works end-to-end · Sentinel fires a real threshold-crossing alert to a registered subscriber · persona correction re-renders with zero re-query · the reasoning graph renders a real multi-agent trace **including one parallel fan-out and one Critic loop, with every node stating that agent's reasoning and its sources** · all six flows complete keyboard-only with a screen reader · a flagged advisory resolves to its full agent trace by `query_id`.

---

### Phase 4 — Optimization, Replay & Demo · Days 22–28

**Goal:** fast, resilient, and rehearsed.

- Optimizations, now that the graph is stable — never before: cost-based short-circuit (§9.3), early-cancel (§9.4), request coalescing (§9.9), semantic cache (§9.1), stale-while-revalidate (§9.14, scoped away from safety-gating data)
- Progressive/streaming rendering polish (§9.19) — safety badge populates **last**, never as an optimistic placeholder
- **Cyclone Gaja historical replay mode** — makes hazard alerting demonstrable outside cyclone season. 🔗 **Conditional on the §1.3 data landing in Phase 2.** Every frame banners its provenance class (`HISTORICAL OBSERVED` / `LIVE` / `SIMULATED`). If the data does not arrive, the replay is cut and labelled deferred in the demo script — it is not reconstructed from invented values
- **Circuit breakers, only where Phase 2 measurement justified one** (§5.7 item 8) — not on speculation
- **Map performance budget verified on a real mid-range Android over 3G** (§4.7), not on a developer laptop — including the WebGL-unavailable fallback path
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
| **S4** | **Ocean & Discovery** | 5 Ocean Analytics · 3 Data Discovery | `/zones`, `/trends`, `/data` | Recharts chart wrappers + provenance popover |
| **S5** | **Geospatial & Visualization** | 6 Geospatial · 8 Visualization | `/map`, `/voyage` | The MapLibre map shell + layer registry everyone adds layers to |
| **S6** | **Synthesis, Language & Personas** | 9 Reporting · 10 Critic · 1 User Interaction | `/` (Ask), persona system, nav IA, `/ops` | Design system, theme tokens, `/design` route, motion + a11y baseline |

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
| Interactive maps + charts | Ph0 MapLibre shell → Ph1 vector layers → Ph2 raster/charts → Ph4 replay | S5, S4 |
| **Frontend stack + design system** (§4.1) | **Ph0** — swap and tokens before surfaces | S6, S5 |
| **Reasoning graph UI** (§4.4) | Ph1 activity strip → **Ph3 full DAG** | S1 |
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
| Accessibility (**WCAG 2.1 AA**, §4.11) | Ph1 baseline built in → Ph3 audited | S6 |
| Audit trail / explainability | Ph1 capture → Ph3 surface | S1 |
| Deployment (Vercel + backend container) | Ph0 Dockerfile only → **after internal round** | S1 |
| **Data harmonization / normalization** (§5.6) | **Ph1 Days 3–4** — blocks agent tools | S3 |
| **Persistent state schema** (§5.3) | ✅ defined → applied Ph0 | S1 |
| **User registration / auth / vessel profiles** (§5.4) | Ph2 | S1, S6 |
| **Security & location-data handling** (§5.5) | Ph0 (secrets, validation) → Ph2 (auth, privacy rules) | S1 |
| **Error handling & degraded responses** (§5.7) | **Ph2 build** → Ph4 verify | S3, S1, S2 |
| **End-to-end fixture test in CI** (§5.8) | Ph1 skeleton → Ph2 degradation variants | S1 + all |
| **Map performance & layer lifecycle** (§4.7) | Ph2 → Ph4 device verification | S5 |
| **Forecast time slider** (§4.8) | Ph2 | S5, S3 |
| **Delivery channels & Dispatcher** (§4.9) | Ph3 — in-app ✅, SMS 🟡 simulated, IVR/USSD ⏸️ deferred | S3, S6 |
| **Advisory feedback loop** (§4.10) | Ph3 | S6, S4 |
| **Agent 8 tool specification** (§5.9) | Ph1 → Ph2 → Ph3 by layer type | S5 |
| **Cyclone Gaja replay data** (§1.3) | 🔗 procure by end of Ph2, replay Ph4 | S3 |

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
| The map stack port slips past Phase 0 and more layers get written against Leaflet | Medium | **High** — a Week-3 rewrite of every layer | §4.1 makes it a Day-1 task with two Phase 0 exit criteria: `grep -ri leaflet frontend/app` empty **and** the ported layers still behaving. `MapView.tsx` is already 163 lines of real layers, so the cost is a half-day now and grows with every layer added before it lands — no new layer goes in first |
| The port silently drops a capability (a popup, the proximity styling, the depth read) | Medium | Medium — a Phase 1 bug blamed on the backend | Exit criterion 8 checks behaviour against the five existing `/api` routes, not the diff. The Leaflet version stays in git history as the reference |
| WebGL unavailable or GPU-blocklisted on a target Android device | Low | **High** — the fisherman sees no map at all | §4.7 fallback: static snapshot plus the full textual verdict. Every spatial fact is also stated in text, so the answer survives the map failing. Verified on a real device in Phase 4 |
| Six new frontend dependencies add weight and churn | Medium | Low | Each is named with a job in §4.1 and nothing else is added without the same justification. deck.gl is explicitly conditional and cuttable; no state library is adopted at all |
| Six people, one graph, merge conflicts | High | Medium | Vertical slices with disjoint files by construction (§7); agents and surfaces are separate modules |
| Vertical slices produce six inconsistent UIs | **High** | Medium | S6 owns the design system; every slice builds from its components. Friday checkpoint includes a UI consistency pass, not just a functional demo |
| Deployment deferred, then rushed after the internal round | Medium | Medium | The Phase 0 `Dockerfile` and the clean degraded-response contract are the only two things that must exist during the month for the later deploy to be small (§5.1, §5.2) |
| LLM provider decision drifts unowned | Medium | Low | §3.3 names S1 as owner with a Phase 2 bake-off deadline. Tiers are fixed now; only providers are open |
| Scope creep from the architecture's own optimization list | Medium | Medium | §9 optimizations are Phase 4 *only*. Implementing them before the graph is stable is explicitly forbidden by the architecture |
| Normalization layer slips past Day 4 and agents build their own transforms | Medium | **High** — silent coordinate bugs found in Week 4 | §5.6 is a hard Day 3–4 gate for S3; the round-trip check is written the same day |
| Auth slips, so Sentinel has no real subscribers in Week 3 | Medium | High — the headline proactive-alert demo weakens | §5.4 lands *early* in Phase 2, not late; the schema it needs already exists |
| Cyclone Gaja data never procured, replay cut late | **Medium** | Medium — one Definition-of-Done scenario lost | §1.3 assigns S3 with an end-of-Phase-2 date and names IBTrACS + ERA5 as the concrete sources. Cut-and-label is the accepted outcome, not fabrication |
| A simulated dispatch or a stubbed channel gets described as working | Low | **High** — a credibility failure in front of judges | The §4.9 status table is the single source of truth; simulated dispatches are labelled `SIMULATED` in the UI and stored `degraded` in the audit log |
| Persona re-enters routing through the new auth layer | Medium | High — reintroduces the v1.0 bug the architecture fixed | CI persona-leak grep under `orca/agents/` (§5.4), same mechanism as the vendor-SDK guard |
| Location data leaks through ordinary logs | Medium | High | Redaction filter ahead of the formatter (§5.5); positions go to the access-controlled audit log or nowhere |

---

## 11. Definition of Done

The build is done when a stranger can sit down and, without help:

1. Ask *"Is it safe to go to sea tomorrow near Thoothukudi?"* by voice in Tamil and get a correct, sourced, spoken answer
2. Switch to the researcher persona and see the same underlying facts as a cited report with a downloadable CSV
3. Open the reasoning graph and trace every number back to a dataset and a timestamp
4. Trigger SOS and watch a structured distress handoff emit with MRCC contact surfaced
5. Plan a route from Thoothukudi toward Palk Bay and watch the IMBL treated as a hard barrier
6. Watch a Sentinel alert fire on a threshold crossing they did not ask for
7. Replay Cyclone Gaja and see the hazard cascade — 🔗 conditional on §1.3 data landing; cut and labelled if it does not
8. Pull the network cable and still get a correct, honestly-amber-flagged answer
9. Register an account and a vessel, set a watch on a location, and receive the alert it fires — while being unable to see any other user's position
10. Tap "Not accurate" on an advisory and have that feedback resolve to the full agent trace behind it
11. Complete the Ask, Safety and Map flows with a keyboard and a screen reader only

Eleven scenarios. If they run clean, the product achieves what the problem statement asked for.

**And one negative criterion, which matters as much as the eleven above:** nothing in the demo, the UI or these documents describes a capability we did not build. Simulated dispatch is labelled simulated. Deferred channels are labelled deferred. A missing dataset is labelled missing. A verdict computed from a fallback rung says so. The §4.9 and §5.5 status tables are the reference, and they are written to be failed rather than admired.

---

*Living document. Update it, dated, whenever a phase boundary or an owner changes. Last updated: 2026-09-02 — v1.2, re-specifying the frontend stack, the design system and the reasoning-graph UI (§4.1, §4.4, §4.7); v1.1 incorporated the in-scope findings of [`verification_analysis.md`](../verification_analysis.md); change log in [`ORCA_Implementation_Updates.md`](./ORCA_Implementation_Updates.md).*
