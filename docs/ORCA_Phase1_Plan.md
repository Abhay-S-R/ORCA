# ⚙️ ORCA — Phase 1 Execution Plan (Days 3–7)

> **Parent plan:** [`ORCA_Implementation_Plan.md`](./ORCA_Implementation_Plan.md) · **Design authority:** [`ORCA_Agentic_Architecture_final.md`](./ORCA_Agentic_Architecture_final.md)
> **Duration:** 5 working days · **Team:** 6, all full-stack · **Precondition:** Phase 0 is closed (`.env` filled from `.env.example`, repo scaffold, infra, Dockerfile, contract freeze). `data/` is already present on every machine.
>
> **⚠️ Pre-Phase-1 action (S6):** Download IndicTrans2 weights and quantized Whisper model to the demo machine **before Day 3**. These are multi-GB downloads and will eat hours on a slow connection. The local translation/STT path is the Phase 1 primary (Bhashini access is still pending), so these models must be warm, not fetched mid-sprint.

---

## 1. The Objective — One Slice, All The Way Through

By end of Day 7, this query works end to end:

> **"நாளை காலை தூத்துக்குடி அருகே கடலுக்குச் செல்வது பாதுகாப்பானதா?"**
> *(“Is it safe to go to sea tomorrow morning near Thoothukudi?”)*

Asked in Tamil. Answered in Tamil. The verdict computed by deterministic Python from real wave, wind, lightning and boundary data. Rendered on a real map. Every number carrying its source. The whole trace captured.

**We are not building twelve agents this week. We are building one query correctly.** A thin slice that runs end-to-end on Day 7 is worth more than twelve agents that have never met each other — it proves the contracts hold, the graph wires up, and every layer agrees, while there is still time to fix all three.

### Why this specific query

It exercises the safety path (the primary judged capability), the fisherman persona (the highest-stakes user), the deterministic risk core (the P0 hallucination guard), the Tamil pipeline, and real pilot-region geography — simultaneously. Every other query in the product is a variation on machinery this one forces us to build.

---

## 2. Exit Criteria

Phase 1 is done when all eight hold:

| # | Criterion | Verified by |
|---|---|---|
| 1 | Tamil safety query returns a correct verdict end-to-end | Manual + recorded acceptance test |
| 2 | Same query in Hindi and English works | Acceptance test ×3 languages |
| 3 | Verdict is computed by `evaluate_marine_safety`, never by an LLM | Code review + provider-swap test (§8) |
| 4 | Every number on screen carries dataset + timestamp | UI inspection — an unsourced number is a bug |
| 5 | SOS surfaces MRCC contact in < 2 s, bypassing normal rendering | Manual test |
| 6 | Map renders IMBL + Gulf of Mannar MPA + user position correctly | Visual check against known coordinates |
| 7 | `audit_trace_log` captures every agent hand-off | Log inspection (*rendering* the trace is Phase 3) |
| 8 | All 6 slices merged to `main`, CI green | Friday checkpoint |

---

## 3. Two Day-3 Deliverables Everyone Else Waits On

Both land by **10:00 on Day 3**. Nothing else meaningful starts until they are on `main`.

### 3.1 Contracts (S1)

**Freeze the *full* `ORCAState` from Architecture §5, not a Phase-1 subset.** Fields we do not use this week simply stay unset. A subset now guarantees a painful widening later, and widening a TypedDict that six branches import is exactly the churn we are trying to avoid.

**The snippet below is illustrative — it shows the `AgentResult` envelope shape, not the complete contract.** The actual `contracts.py` on Day 3 must include the full `ORCAState` TypedDict from Architecture §5 (all ~25 fields, including `critic_pass`, `distress_flag`, `sentinel_subscription`, `early_exit_triggered`, etc.) and the supporting types below.

```python
# backend/orca/contracts.py  — frozen Day 3

@dataclass(frozen=True)
class SourceProvenance:
    dataset: str                  # "Open-Meteo Marine API / ECMWF WAM Blend"
    acquisition_timestamp: str    # ISO 8601, UTC
    freshness_minutes: int

@dataclass(frozen=True)
class Confidence:
    score: Literal["HIGH", "MEDIUM", "LOW_DATA"]   # underscore, not hyphen — matches the DB enum
    rationale: str

@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    query_id: str
    reasoning_depth: Literal["SHALLOW", "STANDARD", "DEEP"]
    inputs_consumed: dict
    outputs: dict
    source_provenance: SourceProvenance
    confidence: Confidence
    # persona_context is deliberately absent — specialists never learn who is asking.
```

**Agent signature — every agent, no exceptions:**

```python
def run(state: ORCAState) -> AgentResult: ...
```

Plain function. No `langgraph` import anywhere under `orca/agents/`. LangGraph nodes in `orca/graph/` are thin wrappers. This keeps agents unit-testable without a graph and callable directly from Sentinel's background loop in Phase 3.

### 3.2 Design system (S6)

Because the team is sliced vertically, six people build UI this week. Without a shared component vocabulary landing *first*, we get six visual dialects and spend Week 4 reconciling them.

Minimum on Day 3: colour tokens (including the safety palette), type scale, spacing scale, and the four primitives every surface needs — `Card`, `Field`, `Badge`, `SourceChip`. Not a full library; the smallest set that stops divergence.

**The accessibility baseline ships inside these primitives, not as a Phase 3 retrofit** (parent plan §4.11). Semantic elements, an accessible name on every control, a visible focus ring at ≥3:1, and ≥4.5:1 body contrast are properties of `Card`/`Field`/`Badge` — so six slices inherit them instead of six people each remembering. `Badge` in particular **always renders a text severity token** (`DANGER`, `CAUTION`, `GO`), with colour as reinforcement: severity is never carried by colour alone. Phase 3 audits this; Phase 1 builds it.

---

## 4. Slice Assignments

Each person owns their agents *and* the surface that renders them. Nobody hands a number to somebody else to draw.

---

### 🔧 S1 — Platform & Orchestration *(lead)*

**Owns:** Agent 2 (Planning) · `/reasoning` + activity strip · contracts, graph, LLM layer, SSE, trace, CI, deployment.

**UI load this week is deliberately near zero** — the trace is *captured* in Phase 1 and *rendered* in Phase 3 — because platform load is at its maximum. Five people are blocked whenever this person is.

| Day | Work |
|---|---|
| 3 | **Contracts on `main` by 10:00** (§3.1). LLM provider layer with three tiers (`cheap`/`mid`/`reasoning`, §3.1–3.3 of parent plan). **Mock `/query` SSE endpoint streaming a canned agent sequence** — this is what lets five people build against a real stream from Day 3 |
| 4 | LangGraph skeleton, stub nodes: `Planning → [WIA ∥ GRA] → RAA → Reporting`. `trace.py` — OTel spans into `audit_trace_log` on every node entry and exit |
| 5 | FastAPI `/query` with real SSE. Agent 2 (Planning): rule-based intent match against the Architecture §4 table — rules tier only; embedding and LLM fallback are Phase 2 |
| 6 | Swap stubs for real agents as they land |
| 7 | End-to-end integration, bug triage, acceptance harness |

**Done when:** a POST to `/query` streams agent-by-agent results, terminates with a verdict payload, and `audit_trace_log` is populated.

---

### 🛡️ S2 — Safety & Distress

**Owns:** Agents 7 (Risk) + 12 (Distress) · `/safety` + persistent SOS · the safety palette and verdict-badge component.

**Starts Day 3 with zero dependencies.** Agent 7 is pure arithmetic over primitives — no APIs, no data files, no graph, no contracts. Do not wait for anything.

| Day | Work |
|---|---|
| 3 | `evaluate_marine_safety` exactly per Architecture §3.1, vessel-class deltas included **from the start**. Real unit tests: every threshold boundary, every vessel class, both sides of each band |
| 4 | `compute_confidence` (HIGH/MEDIUM/LOW-DATA from freshness + authority + coverage), `generate_alert_payload`, `check_active_hazards`. **Ship the verdict-badge component and safety palette into the design system today** — other slices consume it |
| 5 | Agent 12: `detect_distress_signal` — deterministic multilingual pattern list (Ta/Hi/En), *not* semantic inference. `surface_mrcc_contact` with real MRCC data. `emit_datsg_handoff` in CAP-compatible format |
| 6 | `/safety` surface: verdict card, hazard list, vessel-class selector. Persistent SOS control wired to Agent 12 |
| 7 | Integration; verify the LOW-DATA amber path renders for every persona |

**Done when:** the safety engine has genuine coverage on every threshold boundary — the one module in the codebase where a bug is a life-safety issue, and so the one place the "one runnable check" rule is deliberately exceeded. Distress detection fires on real Tamil and Hindi phrasing.

---

### 🌦️ S3 — Weather & Sentinel

**Owns:** Agents 4 (Weather) + 11 (Sentinel) · hazard panels + `/watches` · the `orca/data/` loader layer.

Sentinel is Phase 3, so this week is Agent 4 plus the loader layer. **The loader layer is the more important deliverable** — six people parsing NetCDF and cached JSON six different ways is how the data layer rots. Land it Day 3; S4 and S5 both build on it.

| Day | Work |
|---|---|
| 3 | `orca/data/` loaders — JSON, CSV, GeoJSON, NetCDF via xarray. **Reuse `scripts/orca_grid_utils.py`; do not re-implement wet-cell snapping** |
| 3–4 | **`normalize_to_common_frame` (parent plan §5.6) — every loader exits through it.** CRS, `(lon, lat)` axis order, UTC timestamps, units, sentinel-value handling, and provenance carried forward. Ship the round-trip check the same day. This is a hard gate: S4 and S5 build their tools on top of it, and retrofitting it later means rewriting every loader |
| 4 | `get_marine_weather` — live Open-Meteo with cached `tier1/` fallback. `resolve_temporal_expression` ("tomorrow morning" → ISO range) |
| 5 | `get_cyclone_status` (NDMA SACHET CAP), `get_lightning_nowcast` (Damini + cached), `get_incois_hazard_alerts` |
| 6 | `check_data_freshness` with real staleness tiers feeding S2's confidence scoring. Hazard panel components consumed by S2's `/safety` |
| 7 | Failover cascade per Architecture §12.1; fixtures |

**Done when:** weather tools return correct values with provenance for all 7 pilot ports — and still do, staleness-flagged, with the network disconnected.

---

### 🌊 S4 — Ocean & Discovery

**Owns:** Agents 5 (Ocean Analytics) + 3 (Data Discovery) · `/zones`, `/trends`, `/data` · chart components + the provenance popover.

**Honest note: this is the lightest Phase 1 slice**, because Agent 5 is a Phase 2 deliverable. Rather than pad it, this week is spent on two things that are genuinely on the critical path plus a running start on Phase 2.

| Day | Work |
|---|---|
| 3 | Agent 3 skeleton: source registry, `select_best_source` returning a **human-readable reason string** (Phase 2 surfaces it; the reason must exist from day one or it gets retrofitted badly) |
| 4 | **`SourceChip` — the inline "dataset · timestamp · confidence" display.** Exit criterion 4 depends on this existing, so it is Phase 1 work, not Phase 2. The full click-through popover is Phase 2 |
| 5 | **Fixture and acceptance-test infrastructure** (§6) — the recording convention, the replay harness, the directory layout every other slice writes into |
| 6 | `/zones` surface scaffold rendering PFZ from cached advisories |
| 7 | Phase 2 groundwork: MOSDAC SST/chlorophyll loading, PFZ history parsing for `score_pfz_persistence`. Fixtures |

**Done when:** every number any slice renders can be wrapped in a `SourceChip`, and the fixture harness is in use by all six slices.

---

### 🗺️ S5 — Geospatial & Visualization

**Owns:** Agents 6 (Geospatial) + 8 (Visualization) · `/map`, `/voyage` · the Leaflet map shell everyone adds layers to.

**Use in-memory GeoPandas for spatial computation this week.** Five boundary files and a 720×720 bathymetry grid load in under a second and fit comfortably in memory — geofence and proximity math has no reason to go through a database.

**This is not the same as "no database".** The schema is applied in Phase 0 (`infra/db/migrate.sh`, parent plan §5.3) and S1 writes `audit_trace_log` from Day 3, because the trace has to be captured before Phase 3 can render it. What waits for Phase 2 is *using* Postgres for anything spatial: users, vessels and Sentinel subscriptions land with auth (parent plan §5.4). Nobody in Phase 1 should be loading a boundary polygon out of PostGIS.

| Day | Work |
|---|---|
| 3 | Load `tier1/boundaries/` into GeoPandas with an STRtree index. **Honour `orca_geofence_usable`** — the 4 centroid-only features must never be used for containment. That flag exists because defect C-1 in the data audit was exactly this bug. Leaflet shell with pilot-region bounds |
| 4 | `check_boundary_proximity` — geodesic nautical miles via pyproj, nearest point, alert level. `point_in_polygon` via Shapely. Boundary layers with proximity-gradient styling |
| 5 | GEBCO depth-at-point from `gebco_2026_n10.5_s7.5_w77.5_e80.5.nc`; shallow-hazard flagging. User position marker, distance and bearing readout |
| 6 | `generate_map_layers` → GeoJSON, and the Leaflet layers that consume it. PFZ pin rendering |
| 7 | `spatial_query_zones`; visual QA against known coordinates; fixtures |

**Done when:** IMBL distance from a known Palk Bay coordinate is correct to within 100 m against an independent check, geofence containment never consults a centroid-only feature, and boundary geometry renders at correct coordinates.

> ⚠️ **The IMBL distance is the single highest-consequence number in the product.** A wrong answer is a detained fisherman, not a UX complaint. Verify it against an independent source before it ships, and never let it be interpolated, approximated, or LLM-generated.

---

### 🗣️ S6 — Synthesis, Language & Personas

**Owns:** Agents 9 (Reporting) + 10 (Critic) + 1 (User Interaction) · `/` (Ask), persona system, nav IA, `/ops` · the design system.

Critic is Phase 3, so this week is Reporting, Language, and the entire frontend shell. **This is the heaviest Phase 1 slice** — it balances out in Phase 3 when other slices take on Sentinel and routing.

| Day | Work |
|---|---|
| 3 | **Design system on `main` by 10:00** (§3.2). Next.js App Router scaffold. Nav shell with all 10 routes from parent §4.2 — dead links are fine today |
| 4 | Persona system: selector, React context, and the **visibility matrix from parent §4.3 driving nav rendering**. Implement as declarative config, not scattered conditionals — Phase 3 adds surfaces to it |
| 5 | `/` Ask surface: query input, SSE consumption, progressively-rendering answer card |
| 6 | Agent 1: `detect_language`, `translate_to_english`, `translate_from_english` — **local IndicTrans2 is the primary path** while Bhashini access is pending; Bhashini slots in behind the same tool interface when granted. Agent 9 (thin): assemble `AgentResult`s into a fisherman-shaped payload with citations attached |
| 7 | Tamil and Hindi round-trip through the live graph |

**Done when:** switching persona changes what renders **while every route stays reachable by direct URL** (parent §4.3). A hidden route that 404s means the persona-gate bug is back in the UI layer.

> ⚠️ **Bhashini access is still pending, so local IndicTrans2 is the primary path — not the fallback.** Pull IndicTrans2 and the quantized Whisper weights onto the demo machine this week and verify the local path end-to-end. Because both sit behind the same tool interface, Bhashini becomes a config change whenever access lands. Build as though it never does; be pleasantly surprised if it arrives.

---

## 5. Day-by-Day

| Day | S1 Platform | S2 Safety | S3 Weather | S4 Ocean | S5 Geospatial | S6 Synthesis |
|---|---|---|---|---|---|---|
| **3** | **Contracts 10:00**, LLM tiers, mock SSE | `evaluate_marine_safety` + tests | Data loaders | Agent 3 skeleton | Boundaries + Leaflet shell | **Design system 10:00**, nav shell |
| **4** | LangGraph skeleton, trace | Confidence, alerts, **badge component** | `get_marine_weather` | **`SourceChip`** | Proximity + boundary layers | Persona system + matrix |
| **5** | FastAPI SSE, Planning | Agent 12 distress | Hazard tools | Fixture harness | GEBCO depth, position marker | Ask surface |
| **6** | Real agents in | `/safety` + SOS | Freshness, hazard panels | `/zones` scaffold | `generate_map_layers`, PFZ pins | Agent 1 + Agent 9 |
| **7** | **Integration + acceptance** | LOW-DATA path | Failover + fixtures | Phase 2 groundwork | Visual QA | Ta/Hi round-trip |

**One coordination point, down from two.** Day 3, 10:00: contracts (S1) and design system (S6) both land. Everything else is internal to a slice.

> The old backend/frontend split needed a separate Day-3 agreement between whoever computed map layers and whoever drew them. Vertical slicing deletes that meeting — **S5 owns both sides of that contract**, so there is nobody to negotiate with.

---

## 6. Fixture Strategy — Why Nobody Blocks

S4 owns this infrastructure (Day 5). Every slice records a fixture of its agent's output on the day it first works:

```
backend/tests/fixtures/
  weather_intelligence__thoothukudi__2026-09-05.json
  geospatial__palk_bay_imbl_proximity.json
  risk_assessment__caution_verdict.json
  ...
```

- Every slice builds its **own** UI against its **own** fixtures from Day 3 — no cross-slice waiting at all.
- **S1** wires the graph against fixtures before real agents exist.
- Real integration on Day 6–7 becomes a swap, not a discovery, because the shapes already matched.

---

## 7. What Phase 1 Deliberately Does Not Build

Named explicitly so nobody quietly starts them:

| Deferred | To | Why |
|---|---|---|
| Agents 3 (full), 5, 8, 10, 11 | Phase 2–3 | One slice through the safety path first |
| PostGIS **for spatial computation** | Phase 2+ | GeoPandas in memory is sufficient for 5 files. The schema itself is applied in Phase 0 and `audit_trace_log` is written from Day 3 (parent §5.3) |
| User accounts, login, vessel registration | Phase 2 | Parent §5.4. Phase 1 sessions are anonymous; persona is inferred, exactly as today |
| Advisory feedback control | Phase 3 | Parent §4.10 — needs an advisory worth flagging first |
| SMS / IVR / USSD channels | Phase 3 (SMS 🟡 simulated) / ⏸️ deferred (IVR, USSD) | Parent §4.9. The `Dispatcher` and renderer interfaces are what make this a later addition rather than a rewrite |
| Forecast time slider | Phase 2 | Parent §4.8. Phase 1 renders a single valid time |
| Map tiling and polygon simplification | Phase 2 | Parent §4.7. Pilot-region layers are small enough to ship raw for one week — but do not let that become the pattern |
| Any deployment work | After the internal round | The month targets a local demo. Phase 0's Dockerfile is the only deployment-adjacent thing that exists |
| PWA manifest / offline caching | After the internal round | Keep the degraded-response contract clean and it drops in later as a small addition |
| Voice STT/TTS | Phase 3 | Text-first this week — *but pre-download the models now* (S6) |
| Reasoning graph UI | Phase 3 | Phase 1 **captures** the trace; rendering it is a Phase 3 surface |
| Voyage routing | Phase 3 | The constraint-aware corridor (parent §4.6). A* is out of scope entirely |
| Provider bake-off | Phase 2 | Needs real prompts to score. Tiers are fixed now; providers stay config |
| Embedding/LLM intent fallback | Phase 2 | Rules tier alone covers the Phase 1 query set |
| Every §9 optimization | Phase 4 | The architecture explicitly forbids optimizing before the graph is stable |
| Languages beyond Ta/Hi/En | Phase 3 | Three languages prove the pipeline; the rest is configuration |

---

## 8. Acceptance Test

Runs on Day 7. Recorded, so Phase 2 regressions are caught.

```
GIVEN  a fisherman persona, Tamil language, position near Thoothukudi (8.80°N, 78.14°E)
WHEN   asked "நாளை காலை கடலுக்குச் செல்வது பாதுகாப்பானதா?"
THEN   the response is in Tamil
AND    the verdict is one of GO / CAUTION / NO_GO
AND    the verdict came from evaluate_marine_safety, not from an LLM
AND    wave height, wind speed and lightning status each carry a dataset + timestamp
AND    IMBL distance is present and geodesically correct
AND    the confidence tier is HIGH, MEDIUM or LOW-DATA with a stated rationale
AND    audit_trace_log contains one entry per agent that ran
AND    the map shows user position, IMBL, and the Gulf of Mannar MPA
```

**Plus three hardening checks:**

1. **Provider swap** — repoint the `reasoning` and `mid` tiers at a different vendor. The verdict must be byte-identical; only prose wording may differ. A changed verdict means the LLM has leaked into the safety path. (This is also a free early validation of the §3.3 bake-off plumbing.)
2. **Network cut** — disconnect and rerun. A verdict must still return from cached data, forced to LOW-DATA amber for every persona including fisherman (Architecture §12.2).
3. **SOS** — trigger the distress control; MRCC contact must surface in under 2 seconds with all persona formatting bypassed.

---

## 9. Phase 1 Risks

| Risk | Mitigation |
|---|---|
| Either Day-3 deliverable slips | Contracts (S1) and design system (S6) are each that person's only Day-3 output. If either is not merged by 10:00, it is the standup's only topic |
| Six people building UI produces six dialects | S6's design system lands first and S2 ships the safety badge into it on Day 4. Friday checkpoint includes a UI consistency pass |
| S5 discovers boundary geometry problems | The data audit already fixed C-1 (Gulf of Mannar was a centroid) — but **verify `orca_geofence_usable` is honoured in code**, or the fixed data gets misused anyway |
| S6 is overloaded in Phase 1 | Known and accepted — it inverts in Phase 3. If it slips by Day 5, move Agent 9 (thin) to S1, which owns the graph terminal node anyway |
| S4 under-loaded and drifts into Phase 2 scope | Their Day 5 fixture harness is on everyone's critical path. Phase 2 groundwork is explicitly sanctioned for Day 7 only |
| Bhashini access never arrives | Already assumed. Local IndicTrans2 is the Phase 1 primary, behind an interface Bhashini can slot into later. Nothing in the plan depends on the grant |
| Someone starts Phase 2 work early | §7 exists to make that visible. Finishing the slice beats starting the next agent |

---

## 10. Standing Rituals

- **Daily standup, 15 min.** Three things only: what landed, what is next, what is blocked. Blockers get an owner in the room, not a follow-up.
- **Blockers channel.** With six people and a hard deadline, a silent blocker is the most expensive thing in the project.
- **Merge daily.** No branch older than 24 hours during Phase 1.
- **Friday integration checkpoint.** Full end-to-end run, live, in front of everyone — the §8 acceptance test, not a status update — plus a UI consistency pass across all six surfaces.

---

*Phase 1 of 4. On completion, update the parent plan's phase table and proceed to Phase 2. Last updated: 2026-09-02.*
