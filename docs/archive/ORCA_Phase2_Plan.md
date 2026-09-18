# 🧭 ORCA — Phase 2 Execution Plan (Days 8–14)

> **Parent plan:** [`ORCA_Implementation_Plan.md`](./ORCA_Implementation_Plan.md) · **Design authority:** [`ORCA_Agentic_Architecture_final.md`](./ORCA_Agentic_Architecture_final.md)
> **Duration:** 7 working days · **Team: 3, all full-stack** · **Precondition:** Phase 0 and Phase 1 are closed — contracts frozen, design system on `main`, LangGraph pipeline running end-to-end, Tamil safety query answering with a deterministic verdict.
>
> **⚠️ The one structural change from the parent plan:** the team is three people for this phase, not six. **Scope is unchanged — every Phase 2 item in parent §6 ships.** What changes is the partition: six vertical slices (S1–S6) collapse into three (D1–D3), each carrying roughly two of the original slices plus their shared concerns. The §7 rationale still holds — the person who computes a number still displays it — but each person now owns about twice the surface area, so the coordination rules in §4 are tighter than Phase 1's, not looser.

---

## 1. Slice Re-Partition — S1–S6 → D1–D3

The merge is not arbitrary. Each pairing puts two slices together that already shared a contract boundary in Phase 1, so the merge *removes* a handoff rather than creating one.

| New | Name | Absorbs | Agents owned | Surfaces owned | Shared concerns owned |
|---|---|---|---|---|---|
| **D1** | **Platform, Identity & Synthesis** *(lead)* | S1 + S6-backend + S2's Phase-2 residue | 2 Planning (multi-intent) · 9 Reporting (full) | `/register`, `/login`, `/profile`, `/vessels`, answer-card persona rendering | Contracts, LangGraph, DB layer, auth + RBAC, security controls, `resilience.py`, Redis, CI, LLM bake-off |
| **D2** | **Ocean, Discovery & Analytic Surfaces** | S4 + S6-analytics | 5 Ocean Analytics · 3 Marine Data Discovery | `/zones`, `/trends`, `/data` | Recharts chart wrappers, provenance popover, source-selection narration |
| **D3** | **Geospatial, Visualization & Data Layer** | S5 + S3 | 6 Geospatial (extensions) · 8 Visualization (full) | `/map`, forecast time slider | MapLibre shell + layer registry, `orca/data/` loader layer, tile pipeline, `forecast_frames` |

**Why these three pairings and not others:**

- **D1 takes Agent 9 because the parent plan already sanctioned it.** `ORCA_Phase1_Plan.md` §9 names "move Agent 9 to S1, which owns the graph terminal node anyway" as the accepted contingency. Reporting is the graph's terminal node and the export-formatter is a response-contract concern — it belongs with whoever owns the response contract. This also keeps auth, security and synthesis (the three things that touch every route) under one person, so there is no negotiation over `ORCAState` mid-phase.
- **D2 takes Agents 5 and 3 unchanged from S4**, because Agent 5's causal reasoning consumes Agent 3's source selection directly — the "why has catch declined" answer *is* a narration of which sources were chosen and what they showed. Splitting them would put a handoff inside one reasoning chain.
- **D3 takes S3's loader layer with S5's map**, because in Phase 2 they become the same pipeline: the tile pyramid, the polygon simplification job and `forecast_frames` are all "read a normalized dataset, turn it into something the map can paint". One owner, one pipeline, one place `normalize_to_common_frame` is called from.

**The load is not evenly three-way, and that is deliberate.** D1's week is front-loaded (auth blocks D2's home-port features and D1's own profile surface); D2's is middle-loaded (Agent 5 is the single largest agent in the phase); D3's is back-loaded (the map explorer cannot be assembled until the tiles and frames exist). Day 8 and Day 14 are the only days all three are working on the same kind of thing.

---

## 2. The Objective

By end of Day 14, ORCA answers **all eight Problem Statement queries**, not just the safety one, and a registered user with a registered vessel gets answers scoped to their own boat and their own home port.

| PS # | Query | Lands via | Owner |
|---|---|---|---|
| #1 | "Where are the best fishing zones near me?" | Agent 5 PFZ proximity + persistence, `/zones` | D2 |
| #2 | "Is it safe to go to sea today?" | ✅ Phase 1 — regression only | D1 |
| #3 | "What are the tide, weather and sea conditions?" | Agent 5 tide prediction + Agent 4, `/zones` + time slider | D2, D3 |
| #4 | "Any cyclone or storm warnings?" | ✅ Phase 1 hazard tools — surfaced on `/map` with real layers | D3 |
| #5 | "Am I near the IMBL or a restricted zone?" | ✅ Phase 1 Agent 6 — plus full-precision containment carve-out (§5) | D3 |
| #6 | "Safest route from A to B?" | Constraint sampling groundwork only; the corridor route itself is Phase 3 | D3 |
| #7 | "Why has fish catch declined?" | Agent 5 diagnostic DEEP mode, `/trends` | D2 |
| #8 | "Distress — I need help!" | ✅ Phase 1 — regression, plus `vessel_id` on the handoff now that vessels exist | D1 |

Phase 1 proved one query end-to-end. **Phase 2 proves the roster** — every agent that was a stub or absent is now real, and the multi-intent path visibly fires the union of them.

---

## 3. Exit Criteria

Phase 2 is done when all ten hold. The first six are the parent plan's §6 exit criteria verbatim; the last four are what the three-person partition adds because they are now the boundaries between people rather than inside one person's head.

| # | Criterion | Verified by |
|---|---|---|
| 1 | All 8 PS sample queries return substantive answers | Acceptance suite, one recorded run per query |
| 2 | Researcher export produces a valid CSV with full metadata | Open the file; every column carries dataset + acquisition timestamp |
| 3 | Multi-intent queries visibly activate the union of agents | Activity strip shows both agent sets; `audit_trace_log` confirms |
| 4 | A user can register, add a vessel, see their own home port — and cannot see anyone else's | Two accounts, cross-read returns 403, and the attempt is in the audit log |
| 5 | Killing INCOIS in a fixture yields a degraded answer naming the fallback rung, not a crash | E2E degradation variant in CI |
| 6 | The time slider moves through 56 frames with zero agent invocations | Network panel + `audit_trace_log` empty for the interaction |
| 7 | `audit_trace_log` rows are in **Postgres**, not just in `ORCAState` | `SELECT` after a query — Phase 1 captured it in memory only |
| 8 | Every `MapLayer` and `ChartSpec` leaving the backend passed `validate_payload` | Reject-path test: a malformed layer is dropped and logged, never shipped |
| 9 | Geofence containment still runs against full-precision geometry after simplification ships | Assert the simplified polygon is never the containment input |
| 10 | All 3 slices merged to `main`, CI green including the two new guards | Friday checkpoint |

---

## 4. Day-8 Deliverables Everyone Else Waits On

Phase 1 had two coordination points. Phase 2 has **three**, all landing Day 8, because three people carrying six slices means more contracts cross a person boundary, not fewer.

### 4.1 Contract addendum — 10:00, D1 and D3 jointly

Frozen the same way `ORCAState` was frozen on Day 3: announced, not merged quietly. Three additions, all additive to Phase 1's contracts — **nothing in `contracts.py` or `state.py` is edited, only extended.**

| Contract | Owner | Consumers |
|---|---|---|
| **Auth / session schema** — `UserOut`, `VesselIn/Out`, `SessionToken`, the three role literals, and the `Depends(require_role(...))` signature | D1 | D2 (`/zones` home-port distance), D3 (`/map` persona defaults) |
| **`MapLayer` + `ChartSpec`** — exactly the §5.9 field lists, no additions | D3 | D2 (Recharts wrappers consume `ChartSpec`), D1 (Agent 9 embeds `result_refs`) |
| **`forecast_frames`** — `{layer, frames:[{t, tile_url \| geojson_ref}], t_min, t_max, step_seconds, source_provenance}` (§4.8) | D3 | D2 (`/trends` shares the time axis), D1 (response envelope) |

If any of the three is not on `main` by 10:00, it is the standup's only topic. Everything else that day is internal to a slice.

### 4.2 Loader fixtures — 12:00, D3 → D2

D2's entire week sits on datasets D3 owns the loaders for. D3 ships **recorded fixtures first, real loaders second**: `mosdac_sst__pilot__*.json`, `mosdac_chl__pilot__*.json`, `soi_tides__5ports.json`, `pfz_history__sec001_014.json`. Fixtures are cheap (they are already on disk under `data/`), and they mean D2 starts Agent 5 on Day 9 morning rather than Day 10.

The real loaders land end of Day 8 and must be a **drop-in swap** — same shape, same `NormalizedFrame` provenance. If the shapes diverge, that is a D3 bug, not a D2 rewrite.

### 4.3 Design system is frozen for the phase — additions only

With no dedicated design-system owner this phase, the rule is: **anyone may add a primitive, nobody refactors an existing one.** A token change or a `Badge` signature change blocks two other people mid-sprint for no functional gain. New primitives Phase 2 needs — provenance popover (D2), chart wrappers (D2), time slider (D3), auth form fields (D1) — are built on the existing tokens and merged like any other component. The consistency pass moves to the Day-14 checkpoint.

---

## 5. Slice Assignments

---

### 🔧 D1 — Platform, Identity & Synthesis *(lead)*

**Owns:** Agent 2 (multi-intent) · Agent 9 (full) · auth surfaces · contracts, DB layer, auth + RBAC, security, `resilience.py`, Redis, CI, bake-off.

**Front-loaded on purpose.** Auth is not just this slice's largest item — it is the parent plan's stated precondition for Phase 3's Sentinel having real subscribers (§5.4: "auth core and vessel registration early in the week"). Everything else in D1's week is downstream of it.

| Day | Work |
|---|---|
| **8** | **Contract addendum on `main` by 10:00** (§4.1). `orca/db/` — SQLAlchemy models + repositories over the existing `infra/db/001_init.sql`; no Alembic while there are no ORM-as-source-of-truth models (parent §5.3). **`audit_trace_log` starts writing to Postgres** — Phase 1 captured trace entries into `ORCAState` and never persisted them, and Phase 3's reasoning graph replays from the table, not from memory |
| **9** | Auth core (§5.4): registration and login on phone-or-email + argon2id, JWT 15-min access / 30-day refresh, one `sessions` row per login, anonymous sessions still first-class. Three-role RBAC (`user` / `authority` / `admin`) as a FastAPI dependency at the route boundary — not a permission matrix. Pydantic validation sweep across every existing route with coordinate range checks (§5.5) |
| **10** | Vessel CRUD with ownership checks — `user_id` and `vessel_id` never accepted from the client as a subject, always from the verified token. Log redaction filter ahead of the formatter. Security events (`login`, `failed_login`, `registration`, `role_change`, `vessel_registration`, `subscription_change`, authority position reads) into `audit_trace_log` with `agent_name='security'`. Auth surfaces: `/register`, `/login`, `/profile` with a home-port map picker built on D3's existing shell, `/vessels`. **Extend the CI persona-leak guard to cover `orca/auth/`** — identity is the most tempting place to reintroduce the v1.0 routing bug |
| **11** | Agent 2 multi-intent: union resolution when a query matches several §4 routing rows, no-match fallback, and the second and third routing tiers (embedding similarity, then LLM at `cheap`) that Phase 1 deliberately left out. This lands mid-week because exit criterion 3 is D2's and D3's to demonstrate |
| **12** | Agent 9 full: the four-persona rendering matrix, evidence citations attached per claim with `result_refs` back to the `AgentResult`, and export-formatter mode producing the CSV/NetCDF metadata block D2's `/data` surface serves |
| **13** | `orca/resilience.py` (§5.7) — timeout decorators (5 s default, **3 s on the safety path**), the declared fallback-cascade walker that lowers confidence and appends provenance one rung at a time, arrival validation (empty payload, all-NaN grid, out-of-range, stale-beyond-cadence all count as failures), the agent exception boundary promoted out of `trace.py` into a reusable decorator, and the safety-path conservative rule — a missing required input yields CAUTION or NO_GO naming the input, never GO, never an LLM estimate. Redis caching with source-cadence-aware TTLs (§9.1/§9.11): PFZ ~3×/week, WW3 per cycle, Open-Meteo hourly. **LLM provider bake-off** runs in the background today against Agent 5 and Agent 9 prompts, scored on citation discipline, causal-claim restraint and refusal to fill gaps |
| **14** | E2E degradation variants (§5.8): INCOIS 503, all-sources-down, one agent raises. Integration, acceptance suite, CI green |

**Done when:** two accounts exist, each sees only its own vessels and home port, the cross-read attempt is refused *and* audited, `audit_trace_log` is queryable in Postgres, and killing a source in a fixture produces a degraded answer that names the rung it fell to.

---

### 🌊 D2 — Ocean, Discovery & Analytic Surfaces

**Owns:** Agent 5 · Agent 3 · `/zones`, `/trends`, `/data` · Recharts wrappers, provenance popover, source-selection narration.

**This is the deepest scientific week in the project.** Agent 5 is the only agent in the system doing genuine multi-factor causal reasoning, and it is the one that carries PS queries #1, #3 and #7 on its own.

| Day | Work |
|---|---|
| **8** | Agent 3 full catalog routing: the complete source registry across all 25 datasets with their declared fallback cascades (Architecture §12.1), the deterministic priority cascade, and `select_best_source` returning the **human-readable reason string** the Phase 1 skeleton stubbed. That string is the PS's "tool selection" requirement made visible — *"MOSDAC NRT chosen over Copernicus reanalysis: 6 h old vs 5 d, same authority tier"* — and it is a first-class output, not a log line |
| **9** | Agent 5 part 1 — cross-source SST + chlorophyll correlation over MOSDAC and NASA MODIS granules, anomaly detection against the climatological baseline, tide prediction from SOI tide tables with the Stormglass fallback. Built on D3's Day-8 fixtures, swapped to real loaders when they land. Recharts wrappers for the four §5.9 chart types (TimeSeries, Bar, Radar, WindRose) against the frozen `ChartSpec` |
| **10** | Agent 5 part 2 — PFZ proximity and `score_pfz_persistence` over the archived `pfz/history/<date>/` runs. **Sector status is a first-class output:** a cloud-suppressed sector returns `NO_DATA_CLOUD_COVER` carrying INCOIS's own wording, never an empty result that reads as a failure (data audit C-2). **Provenance popover** (differentiator 3) — the click-through upgrade of Phase 1's `SourceChip`, showing dataset, acquisition timestamp, freshness and confidence, resolved from `result_refs` with no second query |
| **11** | Agent 5 part 3 — diagnostic DEEP mode, `diagnose_productivity_decline`: catch statistics against SST trend, chlorophyll trend and PFZ history, at the `reasoning` tier. **The prompt discipline is the deliverable, not the prose:** the agent says "correlated with" unless the data supports "caused by", and returns "insufficient data" rather than filling a gap. This is exactly what D1's bake-off scores two days later, so the prompt lands before the bake-off, not after |
| **12** | `/zones` full: nearest PFZ with distance and bearing **from the registered home port** (D1's auth landed Day 10), persistence score, sector status per SEC001–SEC014. `/trends`: time-series with anomaly bands and the diagnostic "why has catch declined" workspace |
| **13** | `/data` catalog browser: source metadata per dataset, CSV / NetCDF / GeoJSON export against D1's export-formatter, API access panel. **Researcher persona end-to-end** — the same underlying facts as the fisherman verdict, rendered as a cited report with a downloadable CSV whose every column carries dataset and timestamp |
| **14** | **Source-selection narration** (differentiator 4) surfaced in the UI — Agent 3's reason string rendered on the answer card and in the activity strip, not buried in the trace. Fixtures for every Agent 5 and Agent 3 output; integration |

**Done when:** PS queries #1, #3 and #7 return substantive, cited answers; a researcher can export a CSV whose metadata survives the round trip; and clicking any number anywhere in the product opens its provenance.

---

### 🗺️ D3 — Geospatial, Visualization & Data Layer

**Owns:** Agent 6 (extensions) · Agent 8 (full) · `/map`, time slider · MapLibre shell + layer registry, `orca/data/` loader layer, tile pipeline, `forecast_frames`.

**Back-loaded by construction.** The map explorer is an assembly of things that must exist first — tiles, simplified vectors, layer specs, frames. Days 8–12 build the pipeline; Days 13–14 assemble and measure it.

| Day | Work |
|---|---|
| **8** | **`MapLayer` / `ChartSpec` / `forecast_frames` contracts on `main` by 10:00** (§4.1). **Loader fixtures to D2 by 12:00** (§4.2). Then the real loaders: MOSDAC SST `.h5` and chlorophyll `.nc`, SOI tide tables, PFZ advisory history — every one exiting through `normalize_to_common_frame`, with provenance carried forward and the missing-value count recorded |
| **9** | Raster tile pyramid, zoom 5–11, pre-rendered at build time over the pilot bbox for SST, chlorophyll, bathymetry and wave height; served statically. WMS proxied rather than re-tiled where MOSDAC or Copernicus already publish it. **A 720×720 NetCDF slice is never shipped to the client.** In the background: **Cyclone Gaja procurement** (§1.3) — IBTrACS best-track plus ERA5 hourly `u10`/`v10`/`swh`/`mwp` for 12–18 Nov 2018 over the pilot bbox. Roughly two hours against known endpoints; the parent plan's stated risk is that nobody starts it, so it starts on Day 9 rather than Day 14 |
| **10** | Per-zoom polygon simplification in the pipeline (Douglas–Peucker ~0.01° for z≤7, ~0.002° for z8–10, full precision z≥11; coordinates truncated to 5 decimals) — **never in the browser.** The load-bearing carve-out ships the same day and is asserted in a test: **geofence containment always runs server-side against full-precision geometry in Agent 6.** A simplified IMBL that shifts 200 m is a rendering artifact; treating it as truth is a legal incident. Agent 8 `validate_payload` — mandatory on every payload before egress, not advisory |
| **11** | Agent 8 full: `generate_map_layers` extended to Heatmap and Raster (tiled/WMS) types, `generate_chart_specs` for the four chart types, `weight: heavy \| light` set per layer for the §4.7 lifecycle budget, `persona_visibility` and `result_refs` populated so D2's popover resolves. Agent 8 makes zero LLM calls and interprets no raw dataset — it transforms what a specialist already decided |
| **12** | `forecast_frames` assembly over the 56 WW3 steps (3-hourly, `2026-09-01T00:00Z` → `2026-09-07T21:00Z`, read from the timestamp axis, never hard-coded). The mixed-cadence synchronisation rule: **the slider's axis is the coarsest layer currently displayed**, finer layers sampled nearest-neighbour within half a step, and a layer with no frame in tolerance **greys out rather than extrapolating**, with a "sampled at 12:00, source step 00:00" note in the legend. Time slider frontend: `role="slider"`, arrow-key operable, `aria-valuetext` announcing the forecast time, absolute local time *and* relative offset both displayed |
| **13** | `/map` explorer with real layers — PFZ, SST, chlorophyll, bathymetry, boundaries, hazards. Layer lifecycle: one map instance per surface mounted once, GeoJSON updated via `source.setData()` never teardown-and-recreate, layers mounted on demand and unmounted when deselected, LRU eviction at 2 concurrent heavy layers on mobile / 4 on desktop **with a visible notice** rather than a silent frame-rate collapse |
| **14** | Performance instrumentation — `layer_load_ms`, `render_ms`, `payload_bytes`, dropped-frame count per layer into the existing OTel stream. WebGL-unavailable fallback re-verified now that there are real layers to fail on: static snapshot plus the full textual verdict, because **a missing map is never a missing answer.** Fixtures; integration |

**Done when:** a layer toggle paints inside 400 ms, the slider walks all 56 frames without a single agent invocation, `validate_payload` has a passing reject-path test, and the simplification pipeline provably never feeds a containment check.

---

## 6. Day-by-Day

| Day | D1 Platform & Identity | D2 Ocean & Analytics | D3 Geospatial & Map |
|---|---|---|---|
| **8** | **Contracts 10:00**, `orca/db/`, trace → Postgres | Agent 3 full routing + reason strings | **Contracts 10:00**, **fixtures 12:00**, real loaders |
| **9** | Auth core, RBAC, Pydantic sweep | Agent 5: SST/chl correlation, tides; chart wrappers | Raster tile pyramid; *Gaja procurement (bg)* |
| **10** | Vessels, ownership, redaction, audit; auth surfaces | Agent 5: PFZ persistence; **provenance popover** | Polygon simplification + containment carve-out; `validate_payload` |
| **11** | Agent 2 multi-intent (union, no-match, tiers 2–3) | Agent 5: diagnostic DEEP mode | Agent 8 full — heatmap, raster, chart specs |
| **12** | Agent 9 full persona matrix + export formatter | `/zones` + `/trends` | `forecast_frames` + time slider |
| **13** | `resilience.py` + Redis TTLs; *bake-off (bg)* | `/data` + researcher export end-to-end | `/map` explorer + layer lifecycle |
| **14** | **Degradation E2E + integration** | **Source narration** + fixtures | Perf instrumentation + WebGL fallback |

**Four cross-slice dependencies, all one-directional and all named:**

1. **Day 8, 10:00 — D1 + D3 → everyone.** Contract addendum.
2. **Day 8, 12:00 — D3 → D2.** Loader fixtures, so Agent 5 starts on Day 9.
3. **Day 10 EOD — D1 → D2.** Auth live, so `/zones` can compute distance from a *registered* home port on Day 12.
4. **Day 12 EOD — D1 → D2.** Agent 9's export-formatter, so `/data`'s researcher export works on Day 13.

Nothing else crosses a person boundary. Every other day is internal to a slice, which is what makes three people carrying six slices workable at all.

---

## 7. What Phase 2 Deliberately Does Not Build

Unchanged from the parent plan — the three-person partition does not move anything *out* of Phase 2, and it does not pull anything *in* from Phase 3 either.

| Deferred | To | Why |
|---|---|---|
| Agent 10 (Critic), Agent 11 (Sentinel) | Phase 3 | Sentinel needs the real subscriber list auth creates this week; that is exactly why auth is Days 9–10 and not Day 14 |
| Voice STT/TTS pipeline | Phase 3 | Text-first; the models are already warm from Phase 1 |
| Reasoning graph DAG, node inspector, replay | Phase 3 | Phase 2 makes it *possible* by persisting `audit_trace_log` to Postgres (D1, Day 8). Rendering it is Phase 3 |
| Voyage corridor routing (§4.6) | Phase 3 | A\* remains out of scope entirely, not a stretch goal |
| Channel renderers + `Dispatcher` (§4.9) | Phase 3 | SMS 🟡 simulated, IVR/USSD ⏸️ deferred |
| Advisory feedback controls (§4.10) | Phase 3 | Needs an advisory worth flagging first |
| Languages beyond Ta/Hi/En; all four personas in the UI | Phase 3 | Agent 9's persona *matrix* lands this week; the remaining persona *surfaces* are Phase 3 |
| Every §9 optimization — semantic cache, early-cancel, coalescing, short-circuit | Phase 4 | The architecture forbids optimizing before the graph is stable. Redis TTL caching this week is correctness-and-cadence, not an optimization |
| Circuit breakers | Phase 4 | Only where Phase 2 measurement justifies one (§5.7 item 8) |
| Cyclone Gaja **replay UI** | Phase 4 | The **data** is procured this week (D3, Day 9). The replay is Phase 4 assembly |
| PWA, deployment | After the internal round | Keep the degraded-response contract clean and both drop in |
| Accessibility **audit** | Phase 3 | The baseline is built into every new primitive this week; Phase 3 is where it gets tested with a screen reader |

---

## 8. Acceptance Test

Runs Day 14, recorded, so Phase 3 regressions are caught. Three scenarios beyond Phase 1's, each hitting a different pair of slices.

**A — Multi-intent, researcher persona (D1 + D2)**

```
GIVEN  a registered researcher account with a home port at Thoothukudi
WHEN   asked "Why has catch declined near Thoothukudi, and where are the PFZs now?"
THEN   Agent 2 resolves the union of the diagnostic and PFZ-lookup routing rows
AND    the activity strip shows both agent sets firing, not one
AND    Agent 5 returns a causal analysis that says "correlated with" where the data
       supports only correlation, and names any factor it lacked data for
AND    Agent 3's source-selection reason string is visible on the card
AND    every number opens a provenance popover with dataset, timestamp and freshness
AND    the CSV export contains those same sources as metadata columns
```

**B — Identity and location privacy (D1)**

```
GIVEN  two registered users, each with one vessel and one home port
WHEN   user A requests user B's vessel position by id
THEN   the request is refused at the route boundary by the RBAC dependency
AND    the attempt is written to audit_trace_log with agent_name='security'
AND    no coordinate from either user appears in the application log
AND    user A's own home port and vessel still render correctly on /profile
```

**C — Map, frames and degradation (D3 + D1)**

```
GIVEN  the /map explorer with SST raster and boundary vector layers active
WHEN   the forecast slider is dragged from frame 0 to frame 55
THEN   every frame renders from prefetched tiles with zero agent invocations
AND    a layer with no frame within half a step greys out rather than extrapolating
AND    requesting a third heavy layer on mobile evicts the least-recent with a visible notice
AND    with INCOIS forced to 503 in the fixture, the answer still returns, degraded,
       naming the fallback rung it came from, with confidence dropped and no invented number
```

---

## 9. Phase 2 Risks — the three-person delta

The parent plan's risk register still applies in full. These are the risks the partition *adds* or *sharpens*.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **D1 is the critical path for two other slices in the same week it builds auth** | **High** | High | Auth is Days 9–10, before anything else in D1's week. If Day 10 slips, D2 builds `/zones` against a fixture home port and swaps — the shape is frozen Day 8, so the swap is not a rewrite |
| Agent 5 is one person's four consecutive days with no slack | Medium | **High** — PS #1, #3 and #7 all ride on it | It is split into three independently shippable parts (Days 9, 10, 11). Correlation and tides alone already answer #3; persistence alone answers #1. Only #7 needs all three |
| No dedicated design-system owner → visual drift across three surfaces | Medium | Medium | §4.3 — the system is frozen for the phase, additions only. Consistency pass moves into the Day-14 checkpoint as a named agenda item rather than an assumed one |
| Contract addendum is co-owned by two people (D1 + D3) and lands late | Medium | **High** — blocks all three | Split cleanly: D1 owns auth schema, D3 owns map/chart/frames. They are independent files and neither waits on the other; only the 10:00 announcement is joint |
| The tile pipeline and simplification job land after the surfaces that need them | Medium | Medium | D3's Days 9–10 are pipeline, Days 13–14 are assembly. The order is deliberate — do not reorder to "see something on screen sooner" |
| Cyclone Gaja procurement is again nobody's Tuesday | **Medium** | Medium | Moved to Day 9 as a background download rather than an end-of-phase task. It is two hours of work whose only real risk is never being started |
| Redis TTL caching quietly becomes a §9 optimization | Low | Medium | It is scoped to source-cadence correctness only. Semantic cache, coalescing and stale-while-revalidate stay Phase 4 |
| Auth reintroduces persona into routing | Medium | **High** — the exact v1.0 bug | CI persona-leak guard extended to `orca/auth/` on Day 10. Authentication may populate `ORCAState.persona` as a *resolved* value; it may never reach an intent classifier or a specialist agent |
| Simplified geometry reaches a containment check | Low | **High** — a wrong IMBL answer is a detained fisherman | Asserted in a test on the day simplification ships (D3, Day 10), not reviewed for later |
| Three people, three merges, one graph | Medium | Medium | Slices remain disjoint by construction. Merge daily; no branch older than 24 hours |

---

## 10. Standing Rituals

Unchanged from Phase 1, with one addition.

- **Daily standup, 15 min.** What landed, what is next, what is blocked. Blockers get an owner in the room.
- **Blockers channel.** With three people carrying six slices, a silent blocker is now more expensive than it was with six.
- **Merge daily.** No branch older than 24 hours.
- **Day-14 integration checkpoint.** The §8 acceptance test run live, not a status update — **plus the UI consistency pass across all six surfaces**, which no longer has a dedicated owner and so has to be an explicit agenda item.
- **New: a mid-phase contract check on Day 11.** Ten minutes, three people, one question each — "has anything you shipped changed a shape someone else consumes?" Phase 1 could skip this because six slices each owned one contract. Three slices owning six means a shape change is twice as likely to be invisible to its consumer.

---

## 11. Parent Plan Amendments

These follow from the re-partition and should be applied to `ORCA_Implementation_Plan.md` so the two documents do not disagree (parent plan preamble: "If this document and the code disagree, that is a bug in one of them").

1. **§7 Slice Ownership** — add a note that from Phase 2 the six slices are executed by three people as D1–D3 per §1 of this document, with the S1–S6 lineage preserved for Phase 3 reference.
2. **§9 Acceptance Traceability** — the Owner column entries for Phase 2 rows remap: S1 → D1, S2 → D1, S3 → D3, S4 → D2, S5 → D3, S6 → D1 (backend synthesis) or D2 (analytic surfaces).
3. **§6 Phase 2** — add "Team: 3" and a pointer to this document, exactly as Phase 1 points to `ORCA_Phase1_Plan.md`.
4. **§0 status table** — Frontend moves from "🟡 Scaffold only" to "🟡 In progress", and Infrastructure from "❌ None" to "🟡 compose + schema applied, no CI on hosted runners".
5. **§1.3** — Gaja owner changes from S3 to D3, due date unchanged (end of Phase 2).
6. **§3.3** — bake-off owner changes from S1 to D1, due date unchanged.

---

*Phase 2 of 4. Scope is the parent plan's Phase 2 in full — nothing cut, nothing deferred, nothing moved to Phase 3. On completion, update the parent plan's phase table per §11 and proceed to Phase 3. Last updated: 2026-09-03.*
