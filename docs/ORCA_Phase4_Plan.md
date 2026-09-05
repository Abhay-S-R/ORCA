# 🚀 ORCA — Phase 4 Execution Plan (Days 22–28)

> **Parent plan:** [`ORCA_Implementation_Plan.md`](./ORCA_Implementation_Plan.md) §6 · **Design authority:** [`ORCA_Agentic_Architecture_final.md`](./ORCA_Agentic_Architecture_final.md) §9 (optimizations) and §12 (failover) · **Predecessor:** [`ORCA_Phase3_Plan.md`](./ORCA_Phase3_Plan.md)
> **Precondition:** Phase 3 is closed — 12/12 agents live, the reasoning graph replays a real trace with a fan-out and a Critic loop, voice round-trips, Sentinel fires to a real subscriber, all four personas render, and `axe-core` is clean in CI.
>
> **The one rule this phase exists to enforce:** parent §6 and the risk register (`Scope creep from the architecture's own optimization list`) are explicit that §9's optimizations, circuit breakers and the Gaja replay are **Phase 4 only, never before** — optimizing a graph that is still gaining agents produces work that gets thrown away. Phase 3 already pulled two items forward (Critic self-correction, streaming polish) precisely because they were free by then; everything left in this document was left here because it was **not** free before now.

---

## 0. Phase 3 Verification Gate — run once, before any Phase 4 code

Same discipline as the Phase 3 plan's own §0: this phase builds *on top of* Phase 3, so a Phase 3 regression found on Day 27 costs the week that has no slack behind it (Days 29–30 are buffer, not a second attempt).

| # | Phase 3 exit criterion (parent §6 / Phase 3 plan §4) | Verified how | Result |
|---|---|---|---|
| 1 | 12/12 agents live, LangGraph runs distress → language → planning → [weather ∥ geospatial ∥ ocean] → [risk ∥ viz] → reporting → (critic) → language egress | Read `orca/graph/graph.py`, ran the graph unit/E2E suite | ✅ confirmed — `backend/orca/graph/graph.py` matches the documented topology exactly |
| 2 | E2E fixture suite covers the safety path, Tamil round-trip, distress bypass, and named degradation variants, offline | `pytest tests/e2e -q` | ✅ `tests/e2e/test_graph.py` — 15 scenarios, all green (see §6 below, this document reuses them for the failure-mode rehearsal rather than duplicating them) |
| 3 | `audit_trace_log` persists to Postgres and the reasoning graph replays a historical `query_id` | `orca/api/trace_routes.py`, `frontend/app/reasoning/*` present and wired | ✅ present |
| 4 | Sentinel fires once on a genuine crossing and stays silent on a repeat identical poll | `pytest tests/unit/test_notifications.py -q` | 🔴 **failure found, root-caused, fixed** — `test_crossing_fires_once_and_a_second_identical_poll_is_silent` failed (`2 == 1`) on a from-scratch run. Traced to the test itself, not Sentinel: the test calls `db.commit()` (needed so `run_poll_cycle` sees its own row), which — against the real local Postgres this suite uses, not a mock — leaves the watch row permanently committed past the fixture's rollback. `list_enabled_watches` correctly scans every enabled watch system-wide (real production behaviour), so a second run of the test suite found 4 leftover watches from earlier sessions, all crossing the same injected threshold at once. `detect_crossing`'s dedup logic itself was never wrong. Fixed by clearing `sentinel_subscriptions` at the top of the test — see §9 |
| 5 | All four personas, `/design`, `axe-core` clean | Not re-run in full this pass (no browser harness available in this session) — flagged as **assumed from the last recorded Phase 3 checkpoint**, not re-verified | 🟡 unverified this session |
| 6 | Full unit suite green | `pytest tests/unit -q` | 🟡 315 passed, 1 pre-existing failure (item 4), 1 skipped (IndicTrans2 weights not present on this machine — expected) |

**Disposition:** item 4 is a test-hygiene bug in a Phase 3 test file, not Sentinel production logic, and not Phase-4 scope by charter. It is fixed opportunistically here because it is small, because a known-red test undermines every other "CI green" claim in this document, and because it was found while establishing this phase's own baseline — but it is tracked separately from the Phase 4 deliverables below, not counted as one of them.

---

## 1. What Is Actually Left — a codebase-grounded scope, not the plan's guess from Day 0

The parent plan wrote Phase 4's scope before any of Phases 1–3 existed. Before committing to a day-by-day plan, this section replaces that guess with what a direct read of `backend/orca/` on Day 22 shows.

| Parent §6 Phase 4 item | Status found on Day 22 | What that changes about this plan |
|---|---|---|
| Cost-based short-circuit (§9.3) | ❌ not built. `ORCAState.early_exit_triggered` exists as a reserved field (Phase 0 freeze) but nothing sets it | Build it — §2 below |
| Speculative dispatch + early-cancel (§9.4) | ❌ not built | **Scoped down**, not built as literally specified — see §2.1's honesty note |
| Request coalescing (§9.9) | ❌ not built | Build it — §2.2 |
| Semantic near-duplicate caching (§9.1) | 🟡 half-built. `orca/cache.py` already does cadence-aware **per-source** caching (covers §9.11 in full). The **whole-query** response cache §9.1 actually describes does not exist | Build the missing half — §2.3 |
| Stale-while-revalidate (§9.14) | ❌ not built, and correctly so — nothing needed it before non-safety surfaces (Trends, Data) existed | Build it narrowly, scoped away from safety data exactly as specified — §2.4 |
| Progressive/streaming rendering (§9.19) | ✅ already shipped — pulled forward into Phase 3 D1 Day 20 | Verify only, do not rebuild |
| Visible Critic self-correction (diff. 5) | ✅ already shipped — pulled forward into Phase 3 | Verify only |
| Cyclone Gaja replay | 🟢 **the data landed** — `data/cyclone_gaja/` has the real IBTrACS best-track (76 points, `provenance_class: "HISTORICAL OBSERVED"`) **and** real ERA5 hourly `u10`/`v10`/`swh`/`mwp` for 12–18 Nov 2018 over the pilot bbox (confirmed by opening the file — it is a zipped multi-stream NetCDF from the CDS API, not a stub). Parent §1.3's "cut and label if it doesn't arrive" clause does **not** apply | Build the real replay, not a deferred placeholder — §3 |
| Circuit breakers (§5.7 item 8, §9.8) | ❌ not built | **Correctly not built.** The architecture's own instruction is "only where measured" — there is no load data from a real demo or pilot to justify tripping a breaker on any specific source. Building one on spec risk is exactly the scope-creep the risk register warns about. Left ⏸️ deferred with the measurement trigger stated — §4 |
| Real-device map budget (§4.7) | Not verifiable in this environment | Best-effort proxy done, physical-device pass stays an outstanding manual step — §5 |
| Failure-mode rehearsal (§5.7, §12.2) | 🟢 **already substantially built**, not from this phase's work — `tests/e2e/test_graph.py` and `tests/unit/` already cover 6 of §12.2's 8 applicable rows | Verify, and name the 2 real remaining gaps honestly rather than paper over them — §6 |
| Adaptive Sentinel polling (§9.17) | ❌ not built | Correctly deferred — parent Phase 3 plan §9 already logged this as "Phase 4, only if ahead of schedule," and there is no schedule slack to spend on a stretch item this pass |
| Demo script + load smoke test | ❌ not written | Build both — §7, §8 |

---

## 2. The §9 Optimizations — what ships, and the honesty note on what doesn't

### 2.1 Cost-based short-circuit (§9.3) — shipped as **response trimming**, not compute cancellation

**What the architecture asks for:** if Weather + Geospatial alone already yield `NO_GO`, cancel non-safety-relevant pending calls (the example given is a co-occurring PFZ lookup) unless the user explicitly asked for that data too.

**What the codebase makes possible, checked before writing any code:** `risk_assessment.run()` never reads `ocean_data` (confirmed — the only agent whose output feeds the verdict is Weather + Geospatial). `ocean_analytics` is a true sibling branch, fired in parallel from Planning, feeding only the answer's supplementary content (PFZ location, tide, sector status) — exactly the "co-occurring PFZ lookup" the architecture's own example names.

**What this phase ships:** in `reporting_run` (`orca/graph/graph.py`), when the verdict is `NO_GO` **and** the matched intent rows do not include `PFZ_NEAREST` or `CONDITIONS` (i.e. the user never separately asked for zone or condition data), the Ocean Analytics contribution is dropped from the assembled citations and the synthesized narrative, and `ORCAState.early_exit_triggered` is set `True` — surfaced in the response so the UI/trace can say *why* a normally-present section is absent, rather than silently vanishing.

**The honesty note, stated once here so it does not need restating per file:** this is **response shaping**, not **compute avoidance**. `ocean_analytics` still runs — LangGraph's static fan-in (`add_edge(["weather_intelligence", "geospatial", "ocean_analytics"], ...)`) has no supported notion of aborting an in-flight parallel branch once dispatched, short of bypassing LangGraph's own scheduler for this one fan-out and hand-rolling `asyncio.Task.cancel()` around three specialist calls — a rewrite of the core execution path, for a `NO_GO`-only, non-explicit-intent case, on the one subsystem Ground Rule 2 says must be touched with the most care. That trade was rejected this phase: the user-visible half of §9.3 (the fisherman told not to go does not see PFZ coordinates in that response) ships; the backend-cost half (not paying for the PFZ fetch at all) is logged as the stated upgrade path, not silently dropped. **§9.4's literal "cancel the in-flight OAA call" is therefore not implemented** — it is the same trade, named honestly rather than rounded up to ✅ (parent doc's own status vocabulary, §0).

**Test:** `tests/unit/test_reporting_short_circuit.py` — a `NO_GO` verdict with no PFZ/conditions intent drops ocean content and sets `early_exit_triggered`; the same verdict *with* `PFZ_NEAREST` matched keeps it.

### 2.2 Request coalescing (§9.9)

**What ships:** an in-process, per-worker in-flight registry in `orca/api/main.py`, keyed on the same resolved parameters the graph itself keys on (`normalized query text, rounded lat/lon, vessel_class, persona, depth`) — deliberately **not** a Redis-backed structure, because coalescing only needs to survive the lifetime of one concurrent burst on one process, and adding a distributed lock for that is exactly the kind of infrastructure the architecture's stack table says not to add speculatively. A second identical `/query` request arriving while the first is still streaming subscribes to the same producer's events instead of starting a second graph run; both callers see identical `agent_span` and `final_response` frames.

**Safety-key discipline carried over from §2.3 below, not duplicated:** the key must include the *resolved* location, never raw query text alone — two villages both asking "is it safe" must never collapse into one answer for the wrong village. The rounded-coordinate key already used by `orca/cache.py`'s pattern is reused rather than inventing a second hashing scheme.

**Test:** `tests/unit/test_query_coalescing.py` — two concurrent identical requests produce exactly one graph invocation (asserted via a call counter on the traced entry point) and both receive the same `query_id`.

### 2.3 Near-duplicate response cache (§9.1) — scoped

**What the architecture describes:** embed the query into a vector, serve a cached full response on a near-duplicate within a TTL capped at the tightest freshness window among the sources the response actually used.

**What ships instead, and why:** an embedding index (`FAISS` or similar, named in the architecture's own tech-stack table as a Phase-2/3 addition that never landed because nothing needed paraphrase-level matching yet) is real new infrastructure for a benefit this pass can get most of without it. `orca/query_cache.py` caches the **full final response** keyed on the same resolved-parameter key as §2.2 (not text similarity), reusing `orca/cache.py`'s existing Redis client and graceful-degradation pattern rather than a second caching mechanism. This covers the architecture's own headline case exactly — "many fishermen from the same home port ask near-identical safety queries" — because same port, same vessel class, same persona, same depth *is* the resolved-parameter key; it does not additionally catch a paraphrase ("is it safe" vs. "can I go out") asked from the same location, which genuine embedding similarity would. That gap is named, not hidden.

**The safety bound, made stricter than the spec rather than looser:** TTL is a **fixed 1800 s (30 min) ceiling** — the architecture's own worked example of the tightest real cadence in the system (lightning nowcast). Rather than computing "the tightest cadence among sources this particular response actually used" per response (real, but one more moving part to get wrong on the safety path), every cached response expires at the system's known safety floor regardless of which sources it drew on. A cached `GO` can therefore never outlive the data that justified it by more than the architecture's own worst case allows — this is a deliberately more conservative constant than a dynamic minimum would produce, marked so the tightening path is clear if a future safety-relevant source ever has a cadence shorter than 30 minutes.

**Test:** `tests/unit/test_query_cache.py` — identical resolved params within TTL return the cached response without a second graph invocation; different resolved params (different rounded location) never share an entry; a Redis outage falls through to a live run rather than failing the request (same contract `orca_cache` already gives every per-source fetch).

### 2.4 Stale-while-revalidate (§9.14) — scoped away from safety data

**What ships:** applied only to `orca_analytics`'s non-safety-gating fields already flagged in the architecture text — SST snapshots and PFZ persistence scores — via a small wrapper in `orca/cache.py` that returns the last cached value immediately (even if past its declared TTL, up to a bound) while triggering a background refresh, rather than blocking the caller. **Never applied to anything `risk_assessment` reads** — wind, wave, lightning, cyclone and boundary proximity are always fetched fresh through the existing (non-stale) cascade, exactly as §9.14's own safety-impact note requires. This is additive to `orca_cache` (a new `stale_ok=True` flag on the same decorator), not a second cache.

**Test:** `tests/unit/test_cache_stale_while_revalidate.py` — a stale-flagged source returns the old value instantly and schedules (does not block on) a refresh; a non-flagged source is unaffected.

---

## 3. Cyclone Gaja Historical Replay

Parent §1.3's contingency ("cut and label if the data does not arrive by end of Phase 2") does not trigger — both required datasets are on disk and verified real, not stub placeholders:

| Dataset | File | Verified |
|---|---|---|
| IBTrACS best-track | `data/cyclone_gaja/ibtracs_gaja_2018_besttrack.json` | 76 track points, 10–19 Nov 2018, `provenance_class: "HISTORICAL OBSERVED"`, source NOAA NCEI IBTrACS v04r01 |
| ERA5 wind + wave fields | `data/cyclone_gaja/era5_gaja_20181112_20181118.nc` | Real Copernicus CDS download (a zipped 2-stream GRIB→NetCDF, `u10`/`v10` hourly on a 25×29 grid and `swh`/`mwp` hourly on a 13×15 grid, 12–18 Nov 2018, over the pilot bbox) — **not** the `era5_gaja_STUB.json` sitting alongside it, which is the pre-procurement placeholder `fetch_gaja.py` writes when credentials are missing and is superseded by the real file |

**What this phase builds — `orca/replay/gaja.py` + `orca/api/replay_routes.py` (`GET /api/replay/gaja`):**

1. **The track**, passed through from the IBTrACS JSON essentially as-is — position, wind, pressure, status per 3-hourly (later 6-hourly as the storm organizes) observation.
2. **The hazard cascade** — the actual deliverable behind Definition of Done #7 ("replay Cyclone Gaja and see the hazard cascade"), computed by calling **the real `evaluate_marine_safety()`** (Agent 7, unmodified — zero LLM, the same function the live safety path uses) once per track timestep, with wind speed and wave height sampled from the ERA5 grid at Thoothukudi's coordinates and interpolated to the track's timestamps. This is the honest version of "replay the hazard cascade": it is not a canned sequence of GO/CAUTION/NO_GO strings, it is Agent 7's real deterministic logic run against real historical geophysical fields.
3. **Wind vector frames** for the map overlay, in the exact `{lat, lon, speed_ms, direction_deg}` shape `orca/agents/geospatial.py::wind_vectors()` already returns and `FlowFieldCanvas.tsx` already consumes — so the replay draws on the frontend's existing flow-field renderer rather than a second visualization path.
4. **Provenance on every frame**, per parent §1.3's rule: `"provenance_class": "HISTORICAL OBSERVED (IMD/ERA5, Nov 2018)"` on the track and every derived frame, so nothing in the replay can be mistaken for `LIVE` or `SIMULATED` data. No value in this endpoint is invented — a timestep the ERA5 grid does not cover is omitted, never interpolated across a gap silently.

**Explicitly out of scope this phase:** a dedicated `/replay` frontend route with its own time-scrubber UI. The backend endpoint and the hazard cascade are the deliverable Definition of Done #7 actually asks for ("watch a hazard cascade"); wiring a bespoke player UI beyond what the existing time-slider/map-layer machinery (§4.7, §4.8) already provides is a larger frontend slice than this pass's remaining time affords, and is named here as the concrete next step rather than silently folded into "done."

**Test:** `tests/unit/test_gaja_replay.py` — the track has the documented point count and provenance class; the hazard cascade produces at least one `NO_GO` timestep around the 15–16 Nov landfall window (the actual regression test: if Agent 7's thresholds ever change in a way that stops flagging a real, historically-verified NO_GO cyclone as dangerous, this test catches it); every frame carries `HISTORICAL OBSERVED` provenance.

---

## 4. Circuit Breakers (§5.7 item 8, §9.8) — deferred, and the trigger for building one

**Not built this phase.** The architecture's own words are the reason, not a scheduling excuse: *"Deferred until Phase 4 and applied only to a source that demonstrably flaps under load. Adding five breakers on speculation buys latency and complexity we cannot justify."* This project has never run under real concurrent load against live upstreams (§8's smoke test is the first time it will), so there is no "demonstrably flaps" evidence for any of the six sources in the fallback table to point a breaker at.

**The trigger, stated so this is a decision and not an oversight:** if §8's load smoke test, or a future pilot run, shows a specific source (INCOIS PFZ and Open-Meteo are the two most likely candidates, being the two external HTTP calls on the hot path) timing out or erroring above some fraction of requests under concurrent load, that source gets a breaker — implemented as a small addition to `walk_fallback_cascade`'s rung selection (a per-rung failure-count/cooldown state, wrapping the existing cascade rather than a new subsystem) — and not before.

---

## 5. Map Performance Budget on a Real Device (§4.7)

**What this environment can verify:** none of it, fully honestly. §4.7's budget (≤2.5s interactive, ≤400ms layer toggle, ≥45fps panning, 2 concurrent heavy layers on mobile) is specified against "a mid-range Android over 3G," and there is no physical device or real 3G radio available in this session.

**Best-effort proxy done this pass:** the existing `layer_load_ms` / `render_ms` / `payload_bytes` instrumentation (§4.7, already shipped per the parent doc) was read to confirm it is wired to every layer add — it is (`frontend/app/lib/layerPerf.ts` reports on toggle). That confirms the *measurement* path exists; it does not substitute for the *device* pass.

**Left as an explicit outstanding manual step, not rounded up:** running Chrome DevTools' "Mid-tier mobile" CPU/network throttling profile against `/map` with the default layer set, and — the one the parent risk register calls out by name — physically disabling WebGL (`chrome://flags` or a GPU-blocklisted profile) to confirm the static-snapshot-plus-full-text fallback actually renders rather than a blank map. Neither requires new code; both require a person with a browser, which this session does not have.

---

## 6. Failure-Mode Rehearsal (§5.7, §12.2)

The parent plan's FLAG 22 already corrected the naive version of this item ("you cannot rehearse code that was never written" — the handling is built with the agents, Phase 4 only re-verifies it). Reading `tests/e2e/test_graph.py` on Day 22 shows most of that rehearsal already happened, incrementally, as each agent shipped:

| §12.2 row | Rehearsed by | Result |
|---|---|---|
| API timeout (any source) | `resilience.py`'s `with_timeout` unit tests + `test_missing_upstream_source_degrades_rather_than_crashes` | ✅ pass |
| INCOIS 503 → fallback, confidence downgraded, rung named | `test_incois_503_degrades_ocean_analytics_without_crashing` | ✅ pass |
| All sources down → forced LOW-DATA amber, no invented numbers | `test_all_sources_down_still_returns_a_forced_low_data_verdict`, `test_network_cut_returns_a_verdict_forced_to_low_data` | ✅ pass |
| Agent raises → controlled `AgentResult(status="failed")`, graph completes | `test_missing_upstream_source_degrades_rather_than_crashes` (E2E — `get_marine_weather` raises, the node's exception boundary catches it, the graph still reaches `language_egress`) | ✅ pass — **corrected from this document's own Day-22 first pass**, which mis-read this as an uncovered gap before actually finding the existing E2E test named above |
| Conflicting sources → both surfaced, confidence → MEDIUM, conservative value drives the verdict | Checked for the underlying mechanism, not just a test | ⏸️ **not implemented — a real gap, not a missing test.** `compute_confidence` combines confidence *tiers* already assigned by upstream agents (worst-of, `test_compute_confidence_takes_the_worst_tier`); nothing anywhere compares two independently-fetched *values* for the same parameter and downgrades on disagreement — that is Architecture §9.12 ("cross-source consistency checking"), which the parent implementation plan's own Phase 4 bullet list does not name (§9.1/§9.3/§9.4/§9.9/§9.14 are the ones it lists). Building real dual-source fetching and comparison for this pass would be a new Discovery/Ocean-Analytics feature adopted under the cover of "filling a test gap" — exactly the scope-creep this document's own §4 declined for circuit breakers. Logged honestly as unbuilt, owned by whoever picks up §9.12, not claimed done. `test_compute_confidence_takes_the_worst_tier` was extended with one more case (`tests/unit/test_risk_assessment.py`) confirming the tier-combination half of this row does work — the value-comparison half does not exist to test |
| Geofence data corruption → cached known-good boundary, alert ops | No self-intersection/corruption path exists in `geospatial.py` to test | ⏸️ **not built** — the boundary files are static, versioned, and loaded once at process start from `data/`; there is no runtime code path that could receive a corrupted polygon from an external call the way a live WFS/WMS feed could. Building a defence against a failure mode the current architecture cannot produce is exactly the speculative work §4 already declined for circuit breakers. Logged as a residual risk if a live boundary feed is ever added, not fixed now |
| Infinite agent loop → force-terminate at `max_iterations` | `critic.py`'s `MAX_ITERATIONS = 3` (Phase 3) | ✅ confirmed by reading the module; `test_deep_query_routes_through_the_critic_and_preserves_the_verdict` exercises the path but doesn't force all 3 iterations — acceptable, the cap is a constant, not a runtime condition worth a dedicated exhaustion test |
| Distress false-negative | No automated mitigation possible (architecture's own words) | ✅ operationally mitigated — the SOS control is not language-dependent, already shipped Phase 1 |

**Opportunistic fix, tracked separately from the table above (§0 item 4):** `tests/unit/test_notifications.py::test_crossing_fires_once_and_a_second_identical_poll_is_silent` leaked a committed `sentinel_subscriptions` row into the shared local Postgres every time it ran (the test's own `db.commit()`, needed for `run_poll_cycle` to see the row on the same connection, survives the fixture's rollback). `orca/agents/sentinel.py`'s dedup logic (`detect_crossing` comparing against `_last_watch_payload`) was correct throughout — the fix is one `DELETE FROM sentinel_subscriptions` at the top of the test, not a change to anything this phase owns.

---

## 7. Demo Script

One recorded run per persona, plus the two centrepiece flows the parent plan names explicitly (distress handoff, proactive geofence). Written to `docs/ORCA_Demo_Script.md`, not duplicated here — it is a standalone rehearsal artifact a presenter reads from, not implementation planning.

---

## 8. Load Smoke Test — the priority lane, honestly scoped

**What the architecture asks for (§9.10):** two request lanes, a resource-guaranteed fast lane for `SAFETY_CHECK`/SHALLOW traffic and a standard lane for everything else, so a cyclone-driven demand spike cannot starve the highest-stakes queries.

**What ships:** `orca/api/main.py` gains two stdlib `asyncio.Semaphore` pools — a `PRIORITY_LANE` sized to guarantee headroom for `SAFETY_CHECK`/SHALLOW-shaped requests (classified by reusing Agent 2's own Tier-1 rules match, `classify_intent` — no second classifier, so "which lane" can never disagree with "which agents actually ran") and a smaller `STANDARD_LANE` for everything else. Two independent pools rather than one shared one is what makes it "resource-guaranteed": standard-lane traffic can never contend for a priority-lane slot. This is the smallest real version of backpressure — no new dependency (no queue broker, matching the tech-stack table's explicit "not adding a queue" line), just a concurrency reservation FastAPI already supports natively. A query-cache hit never touches either semaphore — it doesn't need a lane, since nothing runs.

**The smoke test itself:** `scripts/load_smoke_test.py`, `asyncio` + `httpx`, no new dependency (`httpx` is already in `requirements.txt` for the outbound source calls). Fires a burst of concurrent `SAFETY_CHECK`-shaped requests alongside a burst of standard-lane requests against a locally running instance, and reports p50/p95/p99 latency per lane plus error count. **This is a smoke test, not a benchmark** — it is run once, to confirm the priority lane actually holds up under a burst; it is not wired into CI, and it is not re-run repeatedly chasing a number, per this phase's own instruction not to loop-test.

**Run once, this session, against a locally started `uvicorn` instance (no live upstream mocking — real Open-Meteo/INCOIS/IMD network calls):**

```
Priority lane (SAFETY_CHECK, SHALLOW) — 20 concurrent identical requests, 0 errors
  p50=10.39s  p95=10.40s  p99=10.40s
Standard lane (everything else) — 10 concurrent identical requests, 0 errors
  p50=13.77s  p95=13.77s  p99=13.77s
```

**Read honestly, not rounded up:** every request in each burst used identical resolved parameters on purpose (the point of this run was to exercise §2.2's coalescing under load, not to measure 30 independent real network round-trips) — §2.2's coalescing means only *one* real graph execution happened per burst, and every concurrent caller's wall time is bounded by when that one leader finished, which is why p50 ≈ p95 ≈ p99 within each lane. A **separate**, non-identical-query check in the same session isolated a real cache miss vs. hit: a never-before-asked query took **8.53 s** end-to-end against live upstreams; the identical query repeated immediately after took **0.35 s** (§2.3's cache). Two things follow: (1) the ~10 s single-query latency is dominated by live external API round-trips (Open-Meteo, INCOIS, IMD), not by anything this phase added — bringing that number down is a live-upstream-latency problem, out of this phase's scope; (2) coalescing and the response cache both measurably work, and are the reason a burst of 20 concurrent identical safety queries costs the system one real execution rather than twenty.

**A process-hygiene note earned the hard way this session:** the `uvicorn` instance started for this smoke test was left running (its background Sentinel poll loop still active against the shared local Postgres) after the smoke test finished, and the very next full-suite run showed `test_crossing_fires_once_and_a_second_identical_poll_is_silent` fail again — not because §9 item 4's fix was wrong, but because the still-running server's own Sentinel loop was concurrently writing to `sentinel_subscriptions`/`notifications` while the test suite read them. Killing the leftover process and re-running produced a clean 348-passed result. Recorded here rather than silently reset: **stop any server started for this smoke test before running the suite again.**

---

## 9. Exit Criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | A `NO_GO` verdict with no explicit PFZ/conditions intent omits ocean content and states `early_exit_triggered` | `test_reporting_short_circuit.py` |
| 2 | Two concurrent identical safety queries produce one graph run, both callers get the same `query_id` | `test_query_coalescing.py` |
| 3 | A repeated query within 30 minutes returns the cached response; a different location never shares a cache entry; a Redis outage degrades to a live run | `test_query_cache.py` |
| 4 | SST/PFZ-persistence reads never block on a refresh; nothing `risk_assessment` reads is ever served stale | `test_cache_stale_while_revalidate.py` |
| 5 | The Gaja replay's hazard cascade produces a real `NO_GO` around the historical landfall window, computed by the unmodified Agent 7 function, every frame labelled `HISTORICAL OBSERVED` | `test_gaja_replay.py` |
| 6 | No circuit breaker exists without a named, measured trigger | This document, §4 |
| 7 | Every §12.2 row is either passing in `tests/e2e/test_graph.py`/`tests/unit/`, or explicitly logged as not applicable with a reason | §6 table |
| 8 | The Sentinel double-fire regression found at the Phase 3 gate is fixed and its test passes | `pytest tests/unit/test_notifications.py -q` |
| 9 | The full unit + E2E suite is green | `pytest tests/unit tests/e2e -q` |
| 10 | A demo script exists naming one query per persona plus the distress and geofence centrepieces | `docs/ORCA_Demo_Script.md` |
| 11 | A load smoke test runs once against a local instance and reports priority- vs. standard-lane p50/p95/p99 | `scripts/load_smoke_test.py` output, recorded in this document's §10 |
| 12 | Real-device map budget verification and the frontend a11y re-walk are named as outstanding manual steps, not claimed done | §5, §0 item 5 |

---

## 10. Status Snapshot

*In the same status vocabulary as the parent document — ✅ / 🟡 / ⏸️ / 🔗, never rounded up.*

| Item | Status |
|---|---|
| §2.1 Cost-based response trimming (§9.3) | 🟡 **response-shaping shipped, compute-cancellation not** — `orca/graph/graph.py::reporting_run` drops Ocean Analytics content and sets `early_exit_triggered` on a `NO_GO` with no explicit PFZ/conditions intent. `ocean_analytics` itself still executes (§9.4's literal mid-flight cancellation is out of scope — see §2.1's honesty note). Tested: `tests/unit/test_reporting_short_circuit.py`, 3/3 passing |
| §2.2 Request coalescing (§9.9) | ✅ `orca/query_coalescing.py`, wired into `/query`. Tested: `tests/unit/test_query_coalescing.py`, 3/3 passing. Verified under real load in §8 — one burst of 20 concurrent identical requests produced one graph execution |
| §2.3 Near-duplicate response cache (§9.1, scoped) | ✅ `orca/query_cache.py`, 30-min fixed ceiling, wired into `/query` (distress queries excluded by design). Tested: `tests/unit/test_query_cache.py`, 4/4 passing. Verified live: a fresh query took 8.53 s, its immediate repeat 0.35 s |
| §2.4 Stale-while-revalidate (§9.14, scoped) | ✅ `orca_cache(..., stale_ok=True)` in `orca/cache.py`, never applied to anything `risk_assessment` reads. Tested: `tests/unit/test_cache_stale_while_revalidate.py`, 3/3 passing. **Not yet wired to a real caller** — `ocean_analytics`'s SST/PFZ-persistence fetches are the named candidates and remain on the plain `orca_cache` decorator; flipping the flag on them is a follow-up, not a rebuild |
| §3 Cyclone Gaja replay | ✅ `orca/replay/gaja.py` + `GET /api/replay/gaja`. Real IBTrACS (76 points) + real ERA5 (u10/v10/swh/mwp, 12–18 Nov 2018). The hazard cascade — Agent 7's unmodified `evaluate_marine_safety()` run against the historical fields — correctly flags `NO_GO` from 14–16 Nov 2018, matching the real landfall window (15–16 Nov). Tested: `tests/unit/test_gaja_replay.py`, 4/4 passing. **Not built:** a dedicated `/replay` frontend player route — named in §3 as the concrete next step |
| §4 Circuit breakers | ⏸️ deferred by design — no measured trigger exists yet (§4) |
| §5 Real-device map budget | ⏸️ outstanding manual step — no physical device in this environment (§5) |
| §6 Failure-mode rehearsal | 🟡 verified — 6/8 applicable §12.2 rows pass, already covered by tests that existed before this phase; 1 row (geofence corruption) correctly not applicable (no code path could produce it); 1 row (conflicting sources) is a **real unbuilt feature (§9.12)**, not a test gap — logged honestly rather than claimed, see §6 |
| §6 Sentinel double-fire fix | ✅ fixed — root cause was test hygiene (a leaked committed row in the shared Postgres), not Sentinel logic. `tests/unit/test_notifications.py` passes reliably once the environment isn't polluted by another running process (see §8's process-hygiene note, found the hard way this session) |
| §7 Demo script | ✅ [`ORCA_Demo_Script.md`](./ORCA_Demo_Script.md) — 11 scenarios grounded in the parent Definition of Done, one route/file cited per beat |
| §8 Load smoke test + priority lane | ✅ `orca/api/main.py`'s `PRIORITY_LANE`/`STANDARD_LANE` semaphores + `scripts/load_smoke_test.py`, run once against a local instance — results recorded in §8 |
| §9.17 Adaptive Sentinel polling | ⏸️ deferred — no schedule slack, consistent with Phase 3 plan's own conditional note |
| Full suite | ✅ `pytest tests/unit tests/e2e -q` → **349 passed, 2 skipped** (IndicTrans2 weights absent; one platform-conditional skip), 0 failed |

---

*Phase 4 of 4. Scope is grounded in a Day-22 read of the actual codebase, not the parent plan's Day-0 guess — §1 states every place the two disagree and why. On completion, update the parent plan's §6 Phase 4 section and §0 status table to match. Last updated: 2026-09-04.*
