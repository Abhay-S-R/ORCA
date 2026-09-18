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
| **Plan** | `docs/DLC_implementation_plan.md` — 69 points, Phase 0 – Phase 7 |
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
| P0.5 | R-SAFE-1 | Not started |
| P0.6 | R-INDIA-3 | **DONE** · loader now prefers by `valid_for`, 591 features @ 2026-09-17 |
| P0.7 | R-INDIA-5 (tides) | Not started |
| P0.8 | R-AGENT-4 | Not started |
| P0.9 | R-NEW-11 | Not started |
| P0.10 | R-FRESH-1 | **DONE** · newest WW3 run + past-horizon warning |
| P0.11 | R-FRESH-2 | **DONE** · `read_json_if_fresh` on both vector caches |

### Phase 1 — Never be confidently wrong

| Point | Requirement | Status |
|---|---|---|
| P1.1 | R-INDIA-1 | Not started |
| P1.2 | R-NEW-1, R-NEW-8 | Not started |
| P1.3 | R-EDGE-1 | Not started |
| P1.4 | R-EDGE-3 | Not started |
| P1.5 | R-EDGE-4 | Not started |
| P1.6 | R-INDIA-2 | Not started |
| P1.7 | R-INDIA-7 | Not started |
| P1.8 | R-INDIA-8 | Not started |
| P1.9 | R-EDGE-5 | Not started |

### Phase 2 — The conversation that visibly reasons

| Point | Requirement | Status |
|---|---|---|
| P2.1 | R-JUDGE-1 | Not started |
| P2.2 | R-JUDGE-2 | Not started |
| P2.3 | R-JUDGE-4 | Not started |
| P2.4 | R-PS-5, R-AGENT-3 | Not started |
| P2.5 | R-AGENT-1 | Not started |
| P2.6 | R-AGENT-2, R-PS-4 | Not started |
| P2.7 | R-JUDGE-3 | Not started |
| P2.8 | R-PS-1 | Not started |
| P2.9 | R-PS-3, R-CONV-1 | Not started |
| P2.10 | R-NEW-4 | Not started |
| P2.11 | R-NEW-3 | Not started |

### Phase 3 — Identity, language and onboarding

| Point | Requirement | Status |
|---|---|---|
| P3.1 | R-AUTH-1 | Not started |
| P3.2 | R-AUTH-2 | Not started |
| P3.3 | R-NEW-12 | Not started |
| P3.4 | R-UX-6 | Not started |
| P3.5 | R-PS-2 | Not started |
| P3.6 | R-PS-7 | Not started |
| P3.7 | R-SAFE-2 | Not started · reviewer: **Dev R** |

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

### Phase 5 — Data and science depth

| Point | Requirement | Status |
|---|---|---|
| P5.1 | R-SCI-1 | Not started |
| P5.2 | R-NEW-10 | Not started |
| P5.3 | R-NEW-7 | Not started |
| P5.4 | R-INDIA-4 | Not started |
| P5.5 | R-INDIA-6 | Not started |
| P5.6 | R-PS-8 | Not started |
| P5.7 | R-ROUTE-1, R-PS-9 | Not started |
| P5.8 | R-NEW-2 | Not started |
| P5.9 | R-EDGE-2 | Not started |
| P5.10 | R-INDIA-5 (catch) | Not started |
| P5.12 | R-FRESH-4 | Not started |
| P5.13 | R-FRESH-3, R-FRESH-5 | R-FRESH-5 **DONE** (classes + contract doc) · R-FRESH-3 **DONE** for `/data`; the safety-floor half still rides on P0.5 |
| P5.11 | R-NEW-13/14/15/16 | R-NEW-13 **DONE** (verified, do not build) · 14/15/16 not started |

### Phase 6 — Evidence, business, demo

| Point | Requirement | Status |
|---|---|---|
| P6.1 | R-EVID-1 | Not started · `PARALLEL-OK` from Phase 2 exit |
| P6.2 | R-BIZ-1 | Not started · `PARALLEL-OK` |
| P6.3 | R-DEMO-1 | Not started |
| P6.4 | R-DEMO-2 | Not started |
| P6.5 | R-DEMO-3 | Not started |

### Phase 7 — PWA and the final sweep

| Point | Requirement | Status |
|---|---|---|
| P7.1 | DLC §9 | Not started |
| P7.2 | DLC §13 (all 17) | Not started |

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
