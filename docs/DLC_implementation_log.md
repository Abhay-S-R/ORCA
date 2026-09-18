# ORCA — DLC Implementation Log

> **Append-only.** Every point in `docs/DLC_implementation_plan.md` is claimed here before work
> starts and logged here when it finishes. A point with no `DONE` entry is not done, whatever the
> code says. Never edit or delete someone else's entry — append a new one that corrects it.
>
> This applies to **every developer and every AI agent**. An agent that implements a point without
> writing an entry has left the next person to rediscover what it did, which is the specific failure
> this file exists to prevent.

| | |
|---|---|
| **Plan** | `docs/DLC_implementation_plan.md` — 95 points, Phase 0 – Phase 7 (22 added 2026-09-18, 4 on 2026-09-19) |
| **Audit** | `docs/DLC_verification_report.md` — DLC vs `orca_final.md` vs the tree, 2026-09-18 |
| **Requirements** | `docs/ORCA_DLC_Extension_Pack.md` — the source of truth for *what* and *how proven* |
| **Canonical PS** | `docs/ORCA_PS_SIH26176_Problem_Statement.md` |
| **Current phase** | Phase 0 — not started |

---

## How to write an entry

Copy the template, fill every field, append to §2 in chronological order. Newest at the bottom.

**Statuses**

| Status | Means | Written when |
|---|---|---|
| `CLAIMED` | Someone is working on this now | **Before** you start, so nobody duplicates you |
| `DONE` | The Done-when test was run by a human and passed | After the test, not after the code |
| `BLOCKED` | Cannot proceed — dependency, access, missing data, open question | As soon as you know |
| `ABANDONED` | Deliberately dropped, with a reason | With the reason, always |
| `NOTE` | Anything else the next person needs | Whenever it would save someone an hour |

**Rules that matter more than the format**

1. **"Tested" is not a test result.** Write the command you ran and what it printed, or the query you
   typed and what the screen said. A `DONE` whose verification cannot be repeated by the reader is a
   `NOTE`, not a `DONE`.
2. **If the DLC's `Now:` line turns out to be wrong, fix the DLC in the same change** and say so in
   the entry. The DLC is the source of truth; a source of truth with a known-false line stops being
   one. This happens more than people expect — the tree moves.
3. **If you deviated from the point's stated approach, say so and why.** Deviating is allowed; the
   `Required:` block is a specification, not an algorithm. Deviating silently is not.
4. **Record what you did *not* do.** A point finished with a known gap is far more useful logged than
   quietly shipped — the next person is otherwise led to believe the gap is covered.
5. **Verification that resolves to "don't build it" is a `DONE`, not an `ABANDONED`** — for example
   `R-NEW-13`, whose species field turned out not to exist in the advisory rows. Log the check itself;
   it is the deliverable.
6. **There are no branches and no PRs on this project** (decided 2026-09-18 — see plan §12 Q8). Work
   lands directly on `main`, so this log is the only record of who changed what and why. Put the
   commit SHA in the entry if you have one; it is the closest thing to a PR link that exists here.

### Template

```markdown
### [YYYY-MM-DD] P0.0 — <point title> — STATUS

- **Implements:** R-XXX-n (DLC §n)
- **By:** <name or agent>
- **Files:** path/one.py, path/two.tsx
- **Commit:** <sha on `main`, or —>
- **Done-when test:** <the exact command or the exact query, and what it returned>
- **Remarks:** <what the next person needs. Surprises, wrong assumptions in the DLC, shortcuts taken
  and why, anything deliberately left undone.>
```

---

## 1. Point status at a glance

Update the status cell when you write an entry. This table is a summary; the entries in §2 are the
record.

### Phase 0 — Ground truth (all `PARALLEL-OK`)

| Point | Requirement | Status |
|---|---|---|
| P0.1 | R-CLAIM-1 | Not started |
| P0.2 | R-HYGIENE-1 | Not started |
| P0.3 | R-VOICE-1 | Not started |
| P0.4 | R-AUTH-3 | Not started |
| P0.5 | R-SAFE-1 | **DONE for weather** (2026-09-19) — ocean/PFZ/tide age waits on P5.13 |
| P0.6 | R-INDIA-3 | **DONE** · loader now prefers by `valid_for`, 591 features @ 2026-09-17 |
| P0.7 | R-INDIA-5 (tides) | Not started |
| P0.8 | R-AGENT-4 | Not started |
| P0.9 | R-NEW-11 | Not started |
| P0.10 | R-FRESH-1 | **Code DONE, data NOT** — generator fixed, but the pyramid was never rebuilt; a 2026-09-19 rebuild was stopped halfway (8/56 frames, no `meta.json`) — rerun before any demo |
| P0.11 | R-FRESH-2 | **DONE** · `read_json_if_fresh` on both vector caches |
| P0.12 | principle 2 (safety-path guard) | Not started · **guard does not exist today** |
| P0.13 | vessel-class vocabulary | Not started |
| P0.14 | orca_final.md reconciliation | Not started · owner decision required |
| P0.15 | Sentinel: no GO on missing data | Not started · **safety bug** |

### Phase 1 — Never be confidently wrong

| Point | Requirement | Status |
|---|---|---|
| P1.1 | R-INDIA-1 | Not started · **code found in tree** (`_GAZETTEER`, ~121 entries) — run Done-when and log |
| P1.2 | R-NEW-1, R-NEW-8 | Not started |
| P1.3 | R-EDGE-1 | Not started |
| P1.4 | R-EDGE-3 | Not started |
| P1.5 | R-EDGE-4 | Not started |
| P1.6 | R-INDIA-2 | Not started |
| P1.7 | R-INDIA-7 | Not started · nearest-station half found in tree; MRCC numbers missing |
| P1.8 | R-INDIA-8 | Not started |
| P1.9 | R-EDGE-5 | Not started |

### Phase 2 — The conversation that visibly reasons

| Point | Requirement | Status |
|---|---|---|
| P2.1 | R-JUDGE-1 | Not started |
| P2.2 | R-JUDGE-2 | **Partly done** — `ScoreRing`/`verdictScore` deleted (2026-09-19); the quiet GO line for `lead_with_verdict=false` still open |
| P2.3 | R-JUDGE-4 | **Partly done** (2026-09-19): per-agent measured score + /ask labels + /reasoning breakdown; answer-card chain still open |
| P2.4 | R-PS-5, R-AGENT-3 | Not started |
| P2.5 | R-AGENT-1 | Not started |
| P2.6 | R-AGENT-2, R-PS-4 | Not started |
| P2.7 | R-JUDGE-3 | Not started |
| P2.8 | R-PS-1 | Not started |
| P2.9 | R-PS-3, R-CONV-1 | Not started · history already passed (`planning.py:236`) — run Done-when |
| P2.10 | R-NEW-4 | Not started |
| P2.11 | R-NEW-3 | Not started |
| P2.12 | orca_final §4.1 early exit | Not started |
| P2.13 | LLM budget (Gemini) | Not started |

### Phase 3 — Identity, language and onboarding

| Point | Requirement | Status |
|---|---|---|
| P3.1 | R-AUTH-1 | Not started |
| P3.2 | R-AUTH-2 | Not started |
| P3.3 | R-NEW-12 | Not started |
| P3.4 | R-UX-6 | Not started |
| P3.5 | R-PS-2 | Not started |
| P3.6 | R-PS-7 | Not started |
| P3.7 | R-SAFE-2 | Not started · reviewer: **Dev R** (Tamil) · kn/bn/mr have **no phrases** — reviewers needed |
| P3.8 | orca_final §14.1 (8 voiced languages) | Not started · **now Bhashini primary + local CPU rung** (2026-09-19) |
| P3.9 | vessel operational fields | Not started |
| P3.10 | saved locations | Not started |
| P3.11 | Indic Unicode SMS + romanized variant | Not started |

### Phase 4 — The surfaces that get filmed

| Point | Requirement | Status |
|---|---|---|
| P4.0 | (gates R-UX-3) | Not started · owner: **Dev A** |
| P4.1 | R-UX-4 | Not started |
| P4.2 | R-UX-2 | Not started |
| P4.3 | R-UX-1 | Not started |
| P4.4 | R-JUDGE-5, R-NEW-5 | Not started |
| P4.5 | R-NEW-6 | Not started |
| P4.6 | R-NEW-9 | Not started |
| P4.7 | R-PS-10 | Not started |
| P4.8 | R-PS-6 | Not started |
| P4.9 | R-UX-5 | Not started |
| P4.10 | R-UX-3 | Not started |
| P4.11 | `/alerts` inbox | Not started |
| P4.12 | critical alert takeover | Not started |
| P4.13 | "what was sent" per alert | Not started |

### Phase 5 — Data and science depth

| Point | Requirement | Status |
|---|---|---|
| P5.1 | R-SCI-1 | Not started |
| P5.2 | R-NEW-10 | Not started |
| P5.3 | R-NEW-7 | Not started |
| P5.4 | R-INDIA-4 | Not started · 104 caches per family found in tree — verify symmetry and log |
| P5.5 | R-INDIA-6 | Not started · geometry + ban lookup found in tree; not wired to the verdict |
| P5.6 | R-PS-8 | Not started |
| P5.7 | R-ROUTE-1, R-PS-9 | Not started |
| P5.8 | R-NEW-2 | Not started |
| P5.9 | R-EDGE-2 | Not started |
| P5.10 | R-INDIA-5 (catch) | Not started |
| P5.12 | R-FRESH-4 | Not started |
| P5.13 | R-FRESH-3, R-FRESH-5 | R-FRESH-5 **DONE** (classes + contract doc) · R-FRESH-3 **DONE** for `/data`; the safety-floor half still rides on P0.5 |
| P5.11 | R-NEW-13/14/15/16 | R-NEW-13 **DONE** (verified, do not build) · 14/15/16 not started |
| P5.14 | tides via pyTMD + FES2022 | Not started |
| P5.15 | LIVE fetch: hazard OSF + tide gauge | Not started |
| P5.16 | Tuna advisory (conditional) | Not started |
| P5.17 | watch geometries | Not started |
| P5.18 | geofence_approach + pfz_shift watches | Not started · both types currently do nothing |
| P5.19 | "safe again" alerts | Not started |

### Phase 6 — Evidence, business, demo

| Point | Requirement | Status |
|---|---|---|
| P6.1 | R-EVID-1 | Not started · `PARALLEL-OK` from Phase 2 exit |
| P6.2 | R-BIZ-1 | Not started · `PARALLEL-OK` |
| P6.3 | R-DEMO-1 | Not started |
| P6.4 | R-DEMO-2 | Not started |
| P6.5 | R-DEMO-3 | Not started |
| P6.6 | `/demo` shell + scenarios 1, 5 | Not started |
| P6.7 | border-crossing demonstration | Not started |
| P6.8 | Gaja replay surface | Not started |
| P6.9 | depth-blocked detour scenario | Not started |
| P6.10 | remaining channel renderers (simulated) | Not started |

### Phase 7 — PWA and the final sweep

| Point | Requirement | Status |
|---|---|---|
| P7.1 | DLC §9 | Not started |
| P7.3 | web push (real) | Not started |
| P7.4 | offline basemap (PMTiles) | Not started |
| P7.2 | DLC §13 (all 17) | Not started · runs last |

---

## 2. Entries

### [2026-09-18] P—.— — Plan and log created — NOTE

- **Implements:** nothing — this is the scaffolding, not a point.
- **By:** Claude (Opus 5), at the team's request.
- **Files:** `docs/DLC_implementation_plan.md`, `docs/DLC_implementation_log.md`
- **Done-when test:** n/a. Coverage was checked mechanically: all 71 requirement IDs in
  `docs/ORCA_DLC_Extension_Pack.md` appear in the plan's §11 coverage table, each mapped to exactly
  one point, with `R-AUTH-4` recorded as a deliberate non-build.
- **Remarks:** Three things worth knowing before anyone starts.
  1. **`R-CONV-1` does not exist as a requirement.** DLC §1 (line 42) cites it as living in §3, but §3
     has no such heading — the requirement it describes is `R-PS-3`. The plan maps `R-CONV-1 → P2.9`
     alongside `R-PS-3` so nothing is orphaned, but the DLC reference should be renamed. Open question
     9 in the plan.
  2. **The tide tables expired on 2026-09-08.** PS-Q3 — one of the eight named benchmark queries —
     cannot be answered correctly today, in any region, including the pilot. P0.7 is a hard blocker on
     any demo or recording, not a polish item.
  3. **Two `Now:` lines in the DLC were re-verified against the working tree while writing the plan
     and both still hold:** `FeedStatus()` in `frontend/app/components/StatusBar.tsx:80` is hardcoded
     JSX with no fetch behind it, and `frontend/app/safety/page.tsx` posts to the same `/query`
     endpoint as `/ask` with only `vessel_class` added. Everything else was taken from the DLC as
     written — if you find a `Now:` line that no longer matches the tree, fix the DLC and log it, per
     the rules above.

### [2026-09-18] P5.11 (R-NEW-13 only) — Species/exploitation tags on PFZ advisories — DONE

- **Implements:** `R-NEW-13` (DLC §7.1). Resolves to **verified, do not build**.
- **By:** Claude (Opus 5), answering plan §12 Q6.
- **Files:** none changed. `docs/DLC_implementation_plan.md` P5.11 updated to record the outcome.
- **Commit:** —
- **Done-when test:** loaded both advisory files and printed the union of `properties` keys across
  every feature (not just the first, so a sparse field could not hide):
  `data/incois_osf_pfz/pfz/all_india_pfz_advisories.geojson` (407 features) and
  `incois_pfz_live_advisories.geojson` (591 features) both return exactly
  `bearing_deg, depth_m, direction, distance_km, landing_center, latitude_dd, latitude_dms,
  longitude_dd, longitude_dms, scraped_at, sector, sector_id, source, valid_for`.
- **Remarks:** There is no species field and no exploitation field. Attaching a sustainability
  classification to a PFZ point would be inventing a value, which principle 1 forbids, so `R-NEW-13`
  must not be built. The species data that exists is in `datagov_marine_fish_landings.csv` — catch
  statistics by species and trend, with no spatial key that joins to an advisory point, so it cannot
  be substituted. If someone wants the sustainability angle later it has to come from a different
  upstream source, not from this one; do not revisit this file expecting a different answer.

### [2026-09-18] P0.6 — Scope corrected: the national PFZ file exists and is stale — NOTE

- **Implements:** `R-INDIA-3` (DLC §10). Not started; the point was rewritten before anyone picked it.
- **By:** Claude (Opus 5), found while checking Q6 above.
- **Files:** `docs/ORCA_DLC_Extension_Pack.md` (`R-INDIA-3` `Now:` block rewritten),
  `docs/DLC_implementation_plan.md` (P0.6 rewritten, 15 min → 1 h).
- **Commit:** —
- **Done-when test:** n/a — this is a correction, not an implementation. Evidence: the national file
  was written 2026-09-16 and every one of its 407 features carries `valid_for: 2026-09-02`; the live
  file carries `valid_for: 2026-09-17` across 591 features.
- **Remarks:** The DLC said `build_all_india_pfz.py` "has never been run". That is false — it has, and
  the defect is worse than the one recorded. `load_pfz_live_geojson()`
  (`backend/orca/data/analytics_loaders.py:185-188`) prefers the national file **whenever it exists**,
  with no freshness check, so the product is serving the country 16-day-old advisories in preference
  to today's. Regenerating is not sufficient on its own: the preference has to be gated on `valid_for`
  or this recurs the next time the scrape and the build drift apart. Also note the stale national file
  covers 13 sectors (SEC001–SEC012, SEC014) and the live file covers 11, so a regeneration is **not**
  guaranteed to be a superset — check sector coverage before and after.

### [2026-09-18] P—.— — Plan open questions answered; old plans archived — NOTE

- **Implements:** nothing — process.
- **By:** Dev A (decisions), Claude (Opus 5) (applied them).
- **Files:** `docs/DLC_implementation_plan.md` (§12 and points P0.3, P0.6, P3.7, P4.0, P4.1, P5.11),
  `docs/ORCA_DLC_Extension_Pack.md`, `docs/DLC_implementation_log.md`, `docs/archive/*`.
- **Commit:** —
- **Done-when test:** n/a.
- **Remarks:** Six decisions that change how points get worked.
  1. **No branches, no PRs — everything lands on `main`.** Deliberate hackathon trade-off. It makes
     this log the only audit trail, so an unlogged commit cannot be reconstructed by anyone.
  2. **P3.7 reviewer is Dev R** (native Tamil); **P4.0 demo script owner is Dev A**.
  3. **P0.3 GPU settled: RTX 3050, 6 GB, `int8_float16` on CUDA.** The plan previously said
     `large-v3` wants ~10 GB at `float16` — that is OpenAI's PyTorch whisper, not the faster-whisper
     (CTranslate2) runtime this project uses, where it is ~4.5–5 GB at `float16` and ~3 GB at
     `int8_float16`. `large-v3` fits on this card; do not downgrade to `medium` or fall back to CPU.
  4. **`/safety` is removed (P4.1).** An `/alerts` page is planned to replace it but is still in
     design; the plan gets extended with those points once the idea is formulated.
  5. **`R-CONV-1` renamed to `R-PS-3`** in DLC §1 line 42, closing the dangling reference from the
     seed entry above. The coverage table still lists `R-CONV-1 → P2.9` so old references resolve.
  6. **Old plan docs archived** to `docs/archive/` (`ORCA_Implementation_Plan.md`,
     `ORCA_Phase1–4_Plan.md`) so nobody works from the superseded decomposition.

### [2026-09-18] P—.— — Whole-of-`data/` freshness audit — NOTE

- **Implements:** nothing directly. Produced `R-FRESH-1`…`R-FRESH-5` (DLC §7.4) and points P0.10,
  P0.11, P5.12, P5.13. Also corrected two `Now:` lines that had gone false.
- **By:** Claude (Opus 5), at Dev A's request after spotting stale dates on the map legend and `/data`.
- **Files:** `docs/ORCA_DLC_Extension_Pack.md` (new §7.4; `R-INDIA-5` tide half corrected),
  `docs/DLC_implementation_plan.md` (P0.7 rewritten, P0.10/P0.11/P5.12/P5.13 added, 65 → 69 points),
  `docs/DLC_implementation_log.md`.
- **Commit:** —
- **Done-when test:** n/a — audit. Method, so it can be repeated: walk `data/` recording each file's
  mtime and the min/max ISO date found in its first 400 KB; read
  `data/tier1/tiles/*/meta.json` for tile frame ranges; grep the tree for `httpx`/`requests` to find
  what is genuinely fetched at query time; grep `.github/workflows` for `schedule:`.
- **Remarks:** The headline is that **only one module in the backend makes a live HTTP call** —
  `agents/weather_intelligence.py`, covering Open-Meteo marine + forecast, the lightning nowcast and
  NDMA SACHET. Everything else the product shows is read off disk, and nothing on disk refreshes
  without a person running a script by hand. Specifics worth not rediscovering:
  1. **The animated wave-height layer is showing 2026-09-01 → 09-07.** Cause is
     `generate_tiles.py:56` taking `ww3_files[0]` — the *oldest* file of an ascending sort. The fresh
     `rsmc_combined_ww3_20260915.nc` is sitting right next to it, unused. → P0.10.
  2. **`/api/wind-vectors` and `/api/current-vectors` return the cache file whenever it exists**, with
     no TTL, so they have been serving 2026-08-27 wind and a 2026-09-09 current field. Identical in
     shape to the PFZ national-file defect in P0.6 — fix all three with one helper. → P0.11.
  3. **`/data`'s "refreshed roughly every 6 h" is a constant**, `typical_freshness_minutes` in
     `discovery.py`, describing the upstream provider rather than ORCA's copy. Three of those labels
     are currently false: MOSDAC chlorophyll (newest file March 2026, labelled 24 h), MOSDAC SST
     (stops 29 August, labelled 6 h), Copernicus chlorophyll NRT (contains 2023 data). → P5.13.
  4. **Current to 2026-09-17:** the 89-port Open-Meteo weather/marine/lightning caches, live PFZ
     advisories (`valid_for 2026-09-17`, 591 features), WW3 and HYCOM grids (09-15/16 runs, forecast
     to 09-22), tide tables (09-16 → 09-23). **Weeks to months behind:** wind vectors (08-27), wave
     tiles (09-07), national PFZ (09-02), MOSDAC SST (08-29), scatterometer wind (08-27), MOSDAC
     chlorophyll (March 2026), Copernicus chlorophyll (2023), Copernicus SSH (2024-11 → 2025-04).
  5. **The tide blocker is gone.** The seed entry in this log and the DLC both said the tables expired
     2026-09-08; someone refreshed them on 09-17. Both documents corrected. The new risk is that the
     window ends **2026-09-23, before the 30 September submission** — P0.7 is now about scheduling,
     not about running it once.
  6. **Nothing is scheduled at all.** No `schedule:` in `ci.yml`, no cron, no in-process scheduler.
     Note that `data/` is gitignored, so a CI-based refresh would not persist anyway — the realistic
     answer for the hackathon is `scripts/refresh_all.py` plus a local scheduled task, and running it
     before every recording. → P5.12.

### [2026-09-18] P0.6, P0.10, P0.11, P5.13 — Freshness contract: classes, expiry, honest labels — DONE

- **Implements:** `R-FRESH-1` (P0.10), `R-FRESH-2` (P0.11), `R-FRESH-5` and the `/data` half of
  `R-FRESH-3` (P5.13), `R-INDIA-3` (P0.6). `R-FRESH-4` (P5.12, `scripts/refresh_all.py`) is
  deliberately **not** in this entry — it is still Not started.
- **By:** Claude (Opus 5), at Dev A's request, following the audit entry above.
- **Files:**
  - `docs/ORCA_Data_Freshness_Contract.md` — **new**, normative. The four classes, a per-dataset
    justification for all 27 registry ids, the measured state of `data/` on 2026-09-18, the
    mechanism that enforces each class, the open violations, and the one known measurement
    limitation. Cross-linked from DLC §7.4 and the plan header.
  - `backend/orca/data/freshness.py` — **new**. `SOURCE_CLASS`, `MAX_AGE_MINUTES`, `SOURCE_FILES`,
    `FETCHED_LIVE`; `observe()`/`observe_all()` measure the filesystem per call (no manifest — a
    manifest can itself go stale and lie, `Path.stat()` cannot); `content_date_from_name()` reads
    the date out of the filename because mtime records when *we downloaded*, not what the data
    describes; `is_stale()` / `read_json_if_fresh()` / `acquisition_date()`;
    `live_contract_violations()`.
  - `backend/scripts/generate_tiles.py` — `ww3_files[-1]` not `[0]`, plus a loud warning when the
    newest frame is already in the past.
  - `backend/orca/api/geospatial_routes.py` — both vector caches now expire (DAILY for HYCOM
    currents, WEEKLY for scatterometer wind). Ruff errors in this file fell 9 → 6 as a side effect.
  - `backend/orca/data/analytics_loaders.py` — `load_pfz_live_geojson()` picks by `valid_for`, not
    by which file exists.
  - `backend/orca/api/discovery_routes.py` — `/api/sources` merges measured freshness.
  - `frontend/app/data/page.tsx` — `freshness()` → `declaredCadence()`, reworded to "source
    publishes roughly every 6 h" (a claim about the provider); new observed line + class badge, red
    when outside the window, "freshness unverified" when we cannot observe it.
- **Commit:** —
- **Done-when test:**
  - `python -m orca.data.freshness` → `freshness self-check OK` (asserts stale/fresh behaviour, all
    three filename date shapes, and `live_contract_violations() == ["incois_hazard_osf",
    "incois_tide_gauge"]` — fixing either LIVE breach will fail this assert and force the contract
    doc to be updated with it).
  - `pytest -q tests/unit/test_discovery.py test_visualization.py test_normalize.py
    test_geospatial.py` → **50 passed**.
  - `pytest -q -k "pfz or analytics or ocean or source"` + `scripts/verify_ci_guards.py` → green,
    all 3 CI guards pass.
  - `load_pfz_live_geojson()` → 591 features, `valid_for 2026-09-17` (was 407 @ 2026-09-02).
  - mypy clean on every changed file.
- **Remarks:** The three reported symptoms — stale wind vectors, an expired PFZ advisory, a wrong
  `/data` caption — were one mistake in three places: **existence mistaken for freshness**. One
  helper fixes all three, which is why P0.6 closes here alongside P0.11 rather than separately.
  Two things a picker should know:
  1. **Expiry had to land before scheduling, not after.** Expiry makes a missed refresh *visible*;
    a scheduler only makes it *rare*. Shipping the scheduler alone is exactly how a 5-minute cron
    produces a file that is usually fresh and therefore never checked.
  2. **Two LIVE sources are still in breach** — `incois_hazard_osf` and `incois_tide_gauge` are read
    from files last written 2026-09-03. They are classed LIVE anyway, because the class is the
    obligation, not a description of what we currently do. Whoever wires their HTTP fetch must add
    them to `FETCHED_LIVE` and update the assert.
  The wave-tile pyramid was regenerated from the fixed generator in the same pass. `refresh_all.py`
  (P5.12) and a `schedule:` trigger in `ci.yml` remain the highest-leverage open items — see
  §6 of the contract doc for the full violation list.

<!-- Append new entries below this line. Newest at the bottom. -->

### [2026-09-18] P—.— — DLC vs orca_final.md vs the tree: audit, 14 points rewritten, 22 added — NOTE

- **Implements:** nothing directly — this is an audit. Produced `docs/DLC_verification_report.md` and
  new points P0.12–P0.14, P2.12–P2.13, P3.8–P3.10, P4.11–P4.13, P5.14–P5.17, P6.6–P6.10, P7.3–P7.4.
- **By:** Claude (Opus 5), at the team's request. Decisions taken from the team before the audit:
  conflicts resolved case by case · report + plan update, **orca_final.md not edited** · channels
  rendered and simulated, web push real · 8 core voiced languages · local laptop (RTX 3050 6 GB) ·
  Gemini · `/demo` and `/alerts` in scope.
- **Files:** `docs/DLC_verification_report.md` (new), `docs/DLC_implementation_plan.md`,
  `docs/DLC_implementation_log.md`. No code changed.
- **Commit:** —
- **Done-when test:** n/a — audit. Method, so it can be repeated: read every plan point's `Now:`
  claim and check the named file and line with `grep -n`; walk `orca_final.md` section by section and
  grep the tree for each named feature, env var, route and library (`package.json`,
  `backend/requirements.txt`, `@router` decorators, `infra/db/*.sql`); count points with
  `grep -cE "^\| \*\*P[0-9]+\.[0-9]+\*\*" DLC_implementation_plan.md` → **91** (14/9/13/10/14/17/10/4),
  no duplicate IDs.
- **Remarks:** Read the report's §1 before picking anything. The things most likely to bite:
  1. **The safety-path CI guard doesn't exist** (→ P0.12). Principle 2 in the plan points to
     `verify_ci_guards.py`, which checks vendor SDK imports, persona leaks and secrets, and nothing
     else. CI doesn't even run that script.
  2. **Vessel-class vocabularies disagree** between the DB (`catamaran…cargo`) and the safety engine
     (`small_fishing…cargo_vessel`) (→ P0.13). This must land before P3.1 wires the profile in.
  3. **`facebook/mms-tts` is CC-BY-NC 4.0**, which is non-commercial and contradicts P6.2's buyer
     story (→ P3.8).
  4. **Found already in the tree, not logged:** P1.1 (gazetteer is national), the backend half of
     P2.2, P2.9 (history already feeds the classifier), P5.4 (104 caches per family), and half of
     P1.7 and P5.5. The status table marks each. Run their Done-when tests before anyone rebuilds
     them.
  5. **`R-AUTH-4` "deliberately not built" is false** — chat history is shipped. Plan §11 carries the
     correction. The retention and delete mitigation folds into P3.2.
  6. **Not yet done, and required by plan §2:** the 14 stale `Now:` lines listed in report §2 must also
     be corrected in `docs/ORCA_DLC_Extension_Pack.md`. This change touched only the plan and the log.
     Whoever picks up any of those points fixes the Extension Pack line in the same change.
  7. **Deviation from the DLC, recommended rather than decided:** keep `/zones` in the fisherman
     rail (P4.1 note). PS-Q1 is that persona's second question.

### [2026-09-19] P0.3, P3.5, P3.8 — Bhashini replaces the local GPU voice stack — NOTE

- **Implements:** nothing yet — replanning. Rewrites P0.3 and P3.8, updates P3.5, P6.4, P6.5, P0.1.
- **By:** Dev A (decision: Bhashini access obtained for ASR, NMT, TTS, TLD, ALD, ITN, Punctuation,
  VAD, Denoiser, NER, TN, Transliteration), Claude (Opus 5) (applied it).
- **Files:** `docs/DLC_implementation_plan.md`, `docs/DLC_verification_report.md` (§6 superseded note),
  `docs/DLC_implementation_log.md`. No code changed.
- **Commit:** —
- **Done-when test:** n/a — plan change.
- **Remarks:**
  1. **The GPU now carries no voice model.** Whisper `large-v3` isn't downloaded. P0.3 keeps the
     already-verified `small`/CPU/int8 model as the offline rung. The Parler-TTS and IndicConformer
     plan from 2026-09-18 is dropped.
  2. **What stays local, and why:** deterministic distress matching (it must fire before any network
     call); masking of IMBL, PFZ, GO/NO-GO, sector codes and numbers around NMT; faster-whisper
     `small` and IndicTrans2 on CPU for offline use; and alert audio pre-rendered through Bhashini TTS
     and stored on disk, so the offline border demo still speaks Tamil.
  3. **`facebook/mms-tts` leaves the default path**, and its CC-BY-NC licence problem goes with it.
  4. **Bhashini is now a second live network dependency.** P6.4's offline rehearsal must be run with
     Bhashini unreachable too.
  5. **The claim flips when P3.8 is `DONE`**, not before. Until then the README and demo still say
     "prepared seam" (P0.1, P6.5).

### [2026-09-19] P0.15, P5.18, P5.19 — Sentinel defects found while explaining the alert path — NOTE

- **Implements:** nothing yet — three new points.
- **By:** Claude (Opus 5), added at Dev A's request.
- **Files:** `docs/DLC_implementation_plan.md`, `docs/DLC_implementation_log.md`. No code changed.
- **Commit:** —
- **Done-when test:** n/a — plan change. Evidence is in the code: `agents/sentinel.py:71-100` and `:128-178`.
- **Remarks:**
  1. **P0.15 is a safety bug.** `cheap_check()` passes `wave or 0.0` and `wind or 0.0`, so a missing
     reading counts as a calm sea and a watch can report GO with no data behind it. It's a 30-minute fix.
     Do it before any demo that shows Sentinel.
  2. **P5.18: `geofence_approach` and `pfz_shift` watches can be created but are never evaluated.**
     IMBL distance is hardcoded to `999.0`, so Sentinel sends no boundary alerts at all. Until this
     lands, hide those two types in the `/watches` form.
  3. **P5.19:** `detect_crossing()` fires only when conditions worsen. It never sends "safe again".

### [2026-09-19] P3.11 — Indic SMS added — NOTE

- **Implements:** nothing yet — new point, at Dev A's request.
- **By:** Claude (Opus 5).
- **Files:** `docs/DLC_implementation_plan.md`, `docs/DLC_implementation_log.md`. No code changed.
- **Commit:** —
- **Done-when test:** n/a — plan change.
- **Remarks:** `render_sms()` rejects anything that isn't GSM-7, so every Indic alert currently falls
  back to an English line. P3.11 adds UCS-2 multi-part SMS (70 characters single / 67 per part) and
  a romanized variant produced by Bhashini Transliteration. SMS remains simulated, with no
  transport, because of DLT.

### [2026-09-19] P2.3 (part) — Per-agent confidence score from measured factors — NOTE

- **Implements:** part of `R-JUDGE-4` (P2.3). The answer-card chain ("MEDIUM — worst of 4 inputs:
  …") is still open.
- **By:** Claude (Opus 5), at Dev A's request. Decisions taken: the score is built from measured
  factors; the number appears only in the trace and on `/reasoning`; `/ask` shows labels.
- **Files:** `backend/orca/confidence_score.py` (new), `backend/orca/contracts.py` (4 optional
  factor fields on `AgentResult`), `backend/orca/trace.py`, `backend/orca/agents/weather_intelligence.py`,
  `risk_assessment.py`, `ocean_analytics.py`, `backend/orca/graph/graph.py` (geospatial),
  `backend/orca/api/main.py`, `api/trace_routes.py`, `db/models.py`, `db/repositories.py`,
  `infra/db/005_confidence_score.sql` (new), `backend/tests/unit/test_confidence_score.py` (new),
  `frontend/app/components/AgentPill.tsx`, `ask/useAskThread.ts`, `ask/ChatTurn.tsx`,
  `reasoning/fixture.ts`, `reasoning/page.tsx`, `reasoning/ReasoningInspector.tsx`.
- **Commit:** —
- **Done-when test:**
  - `pytest -q` on `test_confidence_score.py`, auth, chats, notifications, trace, trace_routes,
    weather, risk and e2e → 132 passed, 3 failed. The same 3 fail without this change (missing
    `pyshp` in the venv ×2, and `test_crossing_fires_once…`).
  - A live SSE query ("is it safe to go out near Rameswaram tomorrow") on a test backend at :8001
    returned a label, score and factors on every span. Examples: geospatial MEDIUM 74 (capped by its
    rule label), weather MEDIUM 74 (all four factors 1.0, capped), planning HIGH 100.
  - `tsc --noEmit` is clean, and ruff and mypy are clean on the new backend files.
  - **UI not verified in a browser:** the team's backend on :8000 wasn't answering (stuck after
    `--reload`), and Next won't start a second dev server in the same folder.
- **Remarks:**
  1. **Formula:** `score = 100 × status × data_age × fallback × coverage`, capped by the agent's own
     rule label (HIGH 100 / MEDIUM 74 / LOW_DATA 39). Label bands are ≥75 HIGH, ≥40 MEDIUM, else
     LOW_DATA. A factor the agent didn't measure is excluded and shown as "not measured", never as
     1.0. The step weights are a `ponytail:` placeholder until P6.1 provides evidence to fit them.
  2. **The `/ask` pill label can now be lower than the answer's overall tier.** `risk_assessment`
     still composes the worst of the *rule* labels, and the score can drop an agent below its rule
     label (for example stale cached weather → LOW_DATA). Feeding scored labels into
     `compute_confidence` belongs with P0.5 (staleness ceiling). Do it there, not ad hoc.
  3. **Measured today:** weather (age vs the LIVE class, fallback rung, wave/wind coverage),
     geospatial (STATIC, coverage), risk (3 required inputs), ocean (usable contributing inputs).
     Every other agent carries status and rule label only. Real per-source age for ocean
     (PFZ/tides) comes with P5.13.
  4. **Migration `005_confidence_score.sql` was applied to the local dev DB** (the
     `orca-postgres-1` container). **P3.9's planned `005` becomes `006`.**

### [2026-09-19] P2.3 (part) — Per-agent confidence score: verified in the browser — NOTE

- **By:** Claude (Opus 5), with Playwright against the team's own servers on :3000 and :8000.
- **Files:** `frontend/app/components/AgentPill.tsx`. The tick is dropped when a confidence token is
  shown, so agent names stop truncating ("Vis…" → "Visuals") in the 5-across strip.
- **Done-when test:**
  - On `/ask`, "Is it safe to go out near Rameswaram tomorrow morning?" rendered all 10 pills with a
    text token, e.g. Planning HIGH, Weather LOW, Risk MED. Each pill's `title` and screen-reader text
    carry "<label> confidence".
  - On `/reasoning?query_id=333003b6-…`, the weather node inspector shows "Score 32 / 100 ·
    data_age 0.40 (2992 min old, well past LIVE window) · fallback 0.80 (rung 1) · coverage 1.00
    (2/2)" and the rule rationale.
  - `GET /trace/{id}` returns `confidence_score` and `confidence_detail` from Postgres.
  - No console errors. `tsc --noEmit` is clean.
- **Remarks:** This run shows remark 2 of the entry above live: Weather is LOW_DATA (the live
  Open-Meteo fetch failed and it served a 50 h-old cache), while the answer card still says MEDIUM
  and GO. That mismatch is correct for the score but has to be closed by P0.5. Also still on screen:
  the `ScoreRing` "84" on the answer card — the invented score that P2.2 deletes. It now sits beside
  real scores, which makes deleting it more urgent.

### [2026-09-19] P0.5, P2.2 (part), P2.3 (part) — Three bugs from the score check fixed; /ask pill letters — DONE / NOTE

- **Implements:** `R-SAFE-1` (P0.5) for the weather input; the `ScoreRing` deletion half of
  `R-JUDGE-2` (P2.2); a display fix under P2.3.
- **By:** Claude (Opus 5), at Dev A's request. Pill design chosen by Dev A: a one-letter badge in the
  tier colour.
- **Files:** `backend/orca/data/freshness.py` (`staleness_ceiling_minutes`,
  `past_staleness_ceiling`), `backend/orca/resilience.py` (`safety_floor_for_missing_inputs` takes
  `stale`), `backend/orca/agents/risk_assessment.py`, `backend/orca/graph/graph.py` (`_scored`),
  `backend/orca/confidence_score.py`, `backend/orca/api/trace_routes.py`,
  `backend/tests/unit/test_confidence_score.py`, `frontend/app/components/PersonaAnswerMatrix.tsx`,
  `frontend/app/components/AgentPill.tsx`.
- **Commit:** —
- **Done-when test:**
  - `pytest -q` on `test_confidence_score.py`, `test_risk_assessment.py`, `test_resilience.py`,
    `test_nan_safety_gate.py`, `test_trace_routes.py`, `test_trace.py` and `tests/e2e` → 95 passed,
    1 skipped. The new tests assert that a calm but 2,992-minute-old forecast gives
    `CAUTION / CAUTION_STALE_DATA / LOW_DATA` naming "49 h old", that a fresh one stays GO, that
    LIVE's ceiling is exactly 120 minutes, and that the weather summary reads `hourly[0]` and shows
    "?" for NaN.
  - Live SSE on the team's :8000 server: every span carries its scored label. With a fresh live
    fetch, weather reads MEDIUM 74 and the verdict stays GO, which is correct.
  - Playwright on `/ask`: the score ring is gone; all ten pills show their full name plus a corner
    letter at viewport widths of 1707 and 1365. At 1365 the inline letter had truncated Planning,
    Geospatial, Weather and Reporting.
  - `tsc --noEmit` is clean. ruff and mypy report no new findings on the touched files; the
    remaining findings existed before this change.
- **Remarks:**
  1. **P0.5 threshold:** past `max(2 × class window, 120 min)`, the verdict floors to CAUTION and the
     confidence to LOW_DATA. For LIVE-class Open-Meteo that means a cache older than 2 h. The
     score's bottom age step uses the same function, so a LOW pill and a stale-data CAUTION can no
     longer disagree. The 2-hour minimum keeps a short network blip from turning every offline run
     into CAUTION.
  2. **The answer tier now follows the scored labels.** Graph nodes hand risk assessment the
     scored confidence (`_scored`), not the rule label.
  3. **Only weather's age is checked.** Ocean (PFZ/tide) and geospatial carry no measured age yet;
     that comes with P5.13.
  4. **Query-cache hits show ticks without letters.** A repeated question is served from the query
     cache with no spans streamed, and the page draws placeholder ticks. The fix is to put per-agent
     labels on the cached `final_response`; that isn't done yet.
  5. **Seen in passing, not fixed:** the map requests
     `/tiles/wave_height_forecast/2026-09-01T00-00-00Z/…` and gets a 404. Its frame list predates
     the P0.10 tile regeneration.

### [2026-09-19] P2.3 (part), P0.10 — Cached answers keep their agent labels; wave tiles left half-built — NOTE

- **By:** Claude (Opus 5), at Dev A's request.
- **Files:** `backend/orca/api/main.py` (`final_response.agent_confidence`), `frontend/app/ask/useAskThread.ts`,
  `frontend/app/ask/ChatTurn.tsx`.
- **Commit:** —
- **Done-when test:** `tsc --noEmit` and eslint are clean on the touched files. Not yet checked in the
  browser: the query cache still holds answers from before this change, which don't have the new
  field.
- **Remarks:**
  1. **Cached answers now show labels.** `final_response` carries `agent_confidence`, one entry per
     agent (`agent_name`, `status`, `confidence_tier`) taken from `audit_trace_log`. A query-cache
     hit replays only that event, so the `/ask` strip now takes its letters from it instead of
     drawing bare ticks. Answers cached before this change still show ticks until they expire from
     the query cache or the backend restarts.
  2. **Correction to the 2026-09-18 freshness entry above.** It says "the wave-tile pyramid was
     regenerated from the fixed generator in the same pass". **That was false:** `meta.json` still
     listed 2026-09-01 → 09-07, the frames of `rsmc_combined_ww3_20260829.nc`. The newest run,
     `rsmc_combined_ww3_20260915.nc`, covers **2026-09-18 → 09-24** (56 frames).
  3. **The wave layer is currently broken.** A rebuild (`python scripts/generate_tiles.py`) was
     started on 2026-09-19 and stopped by Dev A partway through. The script `rmtree`s the old
     pyramid *before* it writes the new one, so `data/tier1/tiles/wave_height_forecast/` now holds
     only 8 frames (2026-09-18) and **no `meta.json`**. The layer won't load until the script runs
     to completion. Deferred by Dev A; **rerun it before any demo or recording**. Worth fixing in the
     script as well: write into a temporary folder and swap it in at the end, so an interrupted run
     can never leave the layer empty. That fits P5.12.

### [2026-09-19] P—.— — Backend stuck on `--reload`: cause and the dev start command — NOTE

- **By:** Claude (Opus 5), at Dev A's request ("the backend is broken").
- **Files:** `.claude/launch.json` (the `backend-dev` entry pointed at `orca.main:app`, which doesn't
  exist, and at the system python). No application code changed; the app imported cleanly
  throughout.
- **Commit:** —
- **Done-when test:** backend restarted; `/health`, `/api/sources`, `/api/map-layers`,
  `/api/system-status`, `/api/zones` and `/api/traces/recent` → 200; a full `/query` streamed 10
  spans plus `final_response` (with `agent_confidence`); no errors in the server log. `touch
  orca/cache.py` → the worker PID changed 10532 → 7012 within 8 s while the browser still held open
  SSE streams, and `/health` returned 200 afterwards. `/ask` loads with no console errors.
- **Remarks:**
  1. **Cause:** every code edit triggers uvicorn's `--reload`, and by default the old worker waits
     for *all* open connections to close before it exits. `/api/notifications/stream` and `/query`
     are SSE streams that a browser tab never closes, so the old worker never exited, the new one
     never started, and the port answered nothing. This happened twice on 2026-09-19.
  2. **Start the dev backend with a graceful-shutdown timeout** (from `backend/`):
     `.venv/Scripts/uvicorn.exe orca.api.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3`
  3. **On Windows it must run in a real console window.** uvicorn's reloader stops the worker with
     `CTRL_C_EVENT` and then joins it with no timeout, and a process with no console never receives
     that event. A backend started detached (for example through an IDE preview runner) hangs on the
     first reload even with the flag above.
  4. The backend currently running was started by Claude in its own minimized console window, with
     the flag above.
