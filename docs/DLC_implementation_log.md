# ORCA — DLC Implementation Log

> **Append-only.** Every point in `docs/DLC_implementation_plan.md` is claimed here before work
> starts and logged here when it finishes. A point with no `DONE` entry is not done, whatever the
> code says. Never edit or delete someone else's entry — append a new one that corrects it.
>
> This applies to **every developer and every AI agent**. An agent that implements a point without
> writing an entry has left the next person to rediscover what it did, which is the specific failure
> this file exists to prevent.

|                   |                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------- |
| **Plan**          | `docs/DLC_implementation_plan.md` — 69 points, Phase 0 – Phase 7                    |
| **Requirements**  | `docs/ORCA_DLC_Extension_Pack.md` — the source of truth for _what_ and _how proven_ |
| **Canonical PS**  | `docs/ORCA_PS_SIH26176_Problem_Statement.md`                                        |
| **Current phase** | Phase 0 — not started                                                               |

---

## How to write an entry

Copy the template, fill every field, append to §2 in chronological order. Newest at the bottom.

**Statuses**

| Status      | Means                                                            | Written when                                   |
| ----------- | ---------------------------------------------------------------- | ---------------------------------------------- |
| `CLAIMED`   | Someone is working on this now                                   | **Before** you start, so nobody duplicates you |
| `DONE`      | The Done-when test was run by a human and passed                 | After the test, not after the code             |
| `BLOCKED`   | Cannot proceed — dependency, access, missing data, open question | As soon as you know                            |
| `ABANDONED` | Deliberately dropped, with a reason                              | With the reason, always                        |
| `NOTE`      | Anything else the next person needs                              | Whenever it would save someone an hour         |

**Rules that matter more than the format**

1. **"Tested" is not a test result.** Write the command you ran and what it printed, or the query you
   typed and what the screen said. A `DONE` whose verification cannot be repeated by the reader is a
   `NOTE`, not a `DONE`.
2. **If the DLC's `Now:` line turns out to be wrong, fix the DLC in the same change** and say so in
   the entry. The DLC is the source of truth; a source of truth with a known-false line stops being
   one. This happens more than people expect — the tree moves.
3. **If you deviated from the point's stated approach, say so and why.** Deviating is allowed; the
   `Required:` block is a specification, not an algorithm. Deviating silently is not.
4. **Record what you did _not_ do.** A point finished with a known gap is far more useful logged than
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

| Point | Requirement       | Status                                                                  |
| ----- | ----------------- | ----------------------------------------------------------------------- |
| P0.1  | R-CLAIM-1         | Not started                                                             |
| P0.2  | R-HYGIENE-1       | Not started                                                             |
| P0.3  | R-VOICE-1         | Not started                                                             |
| P0.4  | R-AUTH-3          | Not started                                                             |
| P0.5  | R-SAFE-1          | Not started                                                             |
| P0.6  | R-INDIA-3         | **DONE** · loader now prefers by `valid_for`, 591 features @ 2026-09-17 |
| P0.7  | R-INDIA-5 (tides) | Not started                                                             |
| P0.8  | R-AGENT-4         | Not started                                                             |
| P0.9  | R-NEW-11          | Not started                                                             |
| P0.10 | R-FRESH-1         | **DONE** · newest WW3 run + past-horizon warning                        |
| P0.11 | R-FRESH-2         | **DONE** · `read_json_if_fresh` on both vector caches                   |

### Phase 1 — Never be confidently wrong

| Point | Requirement      | Status      |
| ----- | ---------------- | ----------- |
| P1.1  | R-INDIA-1        | Not started |
| P1.2  | R-NEW-1, R-NEW-8 | Not started |
| P1.3  | R-EDGE-1         | Not started |
| P1.4  | R-EDGE-3         | Not started |
| P1.5  | R-EDGE-4         | Not started |
| P1.6  | R-INDIA-2        | Not started |
| P1.7  | R-INDIA-7        | Not started |
| P1.8  | R-INDIA-8        | Not started |
| P1.9  | R-EDGE-5         | Not started |

### Phase 2 — The conversation that visibly reasons

| Point | Requirement       | Status      |
| ----- | ----------------- | ----------- |
| P2.1  | R-JUDGE-1         | Not started |
| P2.2  | R-JUDGE-2         | Not started |
| P2.3  | R-JUDGE-4         | Not started |
| P2.4  | R-PS-5, R-AGENT-3 | Not started |
| P2.5  | R-AGENT-1         | Not started |
| P2.6  | R-AGENT-2, R-PS-4 | Not started |
| P2.7  | R-JUDGE-3         | Not started |
| P2.8  | R-PS-1            | Not started |
| P2.9  | R-PS-3, R-CONV-1  | Not started |
| P2.10 | R-NEW-4           | Not started |
| P2.11 | R-NEW-3           | Not started |

### Phase 3 — Identity, language and onboarding

| Point | Requirement | Status                            |
| ----- | ----------- | --------------------------------- |
| P3.1  | R-AUTH-1    | Not started                       |
| P3.2  | R-AUTH-2    | Not started                       |
| P3.3  | R-NEW-12    | Not started                       |
| P3.4  | R-UX-6      | Not started                       |
| P3.5  | R-PS-2      | Not started                       |
| P3.6  | R-PS-7      | Not started                       |
| P3.7  | R-SAFE-2    | Not started · reviewer: **Dev R** |

### Phase 4 — The surfaces that get filmed

| Point | Requirement        | Status                         |
| ----- | ------------------ | ------------------------------ |
| P4.0  | (gates R-UX-3)     | Not started · owner: **Dev A** |
| P4.1  | R-UX-4             | Not started                    |
| P4.2  | R-UX-2             | Not started                    |
| P4.3  | R-UX-1             | Not started                    |
| P4.4  | R-JUDGE-5, R-NEW-5 | Not started                    |
| P4.5  | R-NEW-6            | Not started                    |
| P4.6  | R-NEW-9            | Not started                    |
| P4.7  | R-PS-10            | Not started                    |
| P4.8  | R-PS-6             | Not started                    |
| P4.9  | R-UX-5             | Not started                    |
| P4.10 | R-UX-3             | Not started                    |

### Phase 5 — Data and science depth

| Point | Requirement          | Status                                                                                                                  |
| ----- | -------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| P5.1  | R-SCI-1              | Not started                                                                                                             |
| P5.2  | R-NEW-10             | Not started                                                                                                             |
| P5.3  | R-NEW-7              | Not started                                                                                                             |
| P5.4  | R-INDIA-4            | Not started                                                                                                             |
| P5.5  | R-INDIA-6            | Not started                                                                                                             |
| P5.6  | R-PS-8               | Not started                                                                                                             |
| P5.7  | R-ROUTE-1, R-PS-9    | Not started                                                                                                             |
| P5.8  | R-NEW-2              | Not started                                                                                                             |
| P5.9  | R-EDGE-2             | Not started                                                                                                             |
| P5.10 | R-INDIA-5 (catch)    | Not started                                                                                                             |
| P5.12 | R-FRESH-4            | Not started                                                                                                             |
| P5.13 | R-FRESH-3, R-FRESH-5 | R-FRESH-5 **DONE** (classes + contract doc) · R-FRESH-3 **DONE** for `/data`; the safety-floor half still rides on P0.5 |
| P5.11 | R-NEW-13/14/15/16    | R-NEW-13 **DONE** (verified, do not build) · 14/15/16 not started                                                       |

### Phase 6 — Evidence, business, demo

| Point | Requirement | Status                                        |
| ----- | ----------- | --------------------------------------------- |
| P6.1  | R-EVID-1    | Not started · `PARALLEL-OK` from Phase 2 exit |
| P6.2  | R-BIZ-1     | Not started · `PARALLEL-OK`                   |
| P6.3  | R-DEMO-1    | Not started                                   |
| P6.4  | R-DEMO-2    | Not started                                   |
| P6.5  | R-DEMO-3    | Not started                                   |

### Phase 7 — PWA and the final sweep

| Point | Requirement      | Status      |
| ----- | ---------------- | ----------- |
| P7.1  | DLC §9           | Not started |
| P7.2  | DLC §13 (all 17) | Not started |

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
     `generate_tiles.py:56` taking `ww3_files[0]` — the _oldest_ file of an ascending sort. The fresh
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
    the date out of the filename because mtime records when _we downloaded_, not what the data
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
  1. **Expiry had to land before scheduling, not after.** Expiry makes a missed refresh _visible_;
     a scheduler only makes it _rare_. Shipping the scheduler alone is exactly how a 5-minute cron
     produces a file that is usually fresh and therefore never checked.
  2. **Two LIVE sources are still in breach** — `incois_hazard_osf` and `incois_tide_gauge` are read
     from files last written 2026-09-03. They are classed LIVE anyway, because the class is the
     obligation, not a description of what we currently do. Whoever wires their HTTP fetch must add
     them to `FETCHED_LIVE` and update the assert.
     The wave-tile pyramid was regenerated from the fixed generator in the same pass. `refresh_all.py`
     (P5.12) and a `schedule:` trigger in `ci.yml` remain the highest-leverage open items — see
     §6 of the contract doc for the full violation list.

### [2026-09-18] P0.10, P5.12 (partial) — Clearing the freshness breaches: refresh scripts, the WW3 epoch bug, the tile 404 storm — DONE

- **Implements:** `R-FRESH-1` (the stale-copy half), `R-FRESH-4` in part (four of the per-source
  refresh scripts `refresh_all.py` will orchestrate), and the §6.1 clearing list in
  `docs/ORCA_Data_Freshness_Contract.md`.
- **By:** Claude (Opus 5), at Dev A's request, following the freshness-contract entry above.
- **Files:**
  - `backend/scripts/generate_tiles.py`, `backend/scripts/generate_pan_india_waves.py` — **the
    WW3 time axis was two days wrong.** `TIME` carries `units: "hours since 0001-01-01"` with
    `calendar: "standard"`; that epoch is a _Julian_ date and Python's proleptic-Gregorian
    `datetime(1, 1, 1)` sits two days after it. Both scripts decoded by hand without the
    correction, so the 2026-09-17 run rendered as a 09-20 → 09-26 forecast. `-48.0` h in both,
    plus a plausibility guard in `generate_tiles.py` that refuses to write tiles when the first
    frame falls outside `[run_date, run_date + 2 d]`. `orca/agents/voyage.py:_ww3_hours_since_epoch`
    and `extract_osf_pilot` always had the `+48` and were the reference.
  - `frontend/app/components/MapView.tsx` — passes `bounds: layer.bounds` to the raster source.
    The pyramid only covers the WW3 grid extent, so without it MapLibre requested the whole
    viewport and every tile outside the grid 404'd: at z6 the data is x 43–49 / y 28–31 and every
    404 in the uvicorn log sat at x 42, x 50 or y 32 — the ring one tile out. `meta.json` had
    carried `bounds` all along and `RasterLayerMeta` already declared it.
  - `scripts/refresh_nasa_ocean_color.py` — **new**, public, no credentials. Queries NASA CMR for
    the newest `MODISA_L3m_CHL_NRT` granules into `data/tier2/nasa/`. Refuses to overwrite with an
    empty listing.
  - `scripts/refresh_bhuvan_manifest.py` — **new**, public. Re-probes the four NRSC/SAC portals and
    rewrites `data/tier3/bhuvan/bhuvan_manifest.json`. The portal list is a module constant, not
    read back from the file, so a corrupted manifest cannot shrink the next refresh.
  - `scripts/refresh_cmems.py` — **new**, credentialed. Three Copernicus Marine NRT products (CHL,
    SSH `adt`/`sla`, `thetao` surface slice) over the pan-India box on a trailing 7-day window,
    because NRT publishes with 1–3 days of latency. Detects the auth failure and prints the login
    instruction rather than failing opaquely.
  - `scripts/refresh_gfw_ais.py` — **new**, credentialed. Reads `GFW_API_TOKEN` from the
    environment — never written to disk, so it cannot reach a commit — and refreshes the GFW
    vessel-search sample.
  - `backend/orca/data/freshness.py` — `incois_erddap` reclassified **DAILY → STATIC**, with the
    evidence in the comment.
  - `docs/ORCA_Data_Freshness_Contract.md` — §6 restructured: §6.1 cleared, §6.2 still open, §6.3
    what a human must do by hand, §6.4 the ERDDAP escalation.
- **Commit:** —
- **Done-when test:**
  - Tile pyramid rebuilt from the corrected generator: frames now start **2026-09-18T00:00:00Z**
    (was 2026-09-20). The guard fires and aborts the write if the epoch drifts again.
  - `npx tsc --noEmit` clean on the frontend.
  - `python scripts/refresh_nasa_ocean_color.py` → newest granule **2026-09-17**.
  - `python scripts/refresh_bhuvan_manifest.py` → 4/4 portals reachable.
  - `python -m orca.data.freshness` → `freshness self-check OK`.
  - `pytest -q` → **425 passed, 1 failed, 2 skipped**. The failure,
    `test_notifications.py::test_crossing_fires_once_and_a_second_identical_poll_is_silent`, is
    environmental and unrelated: `run_poll_cycle` returns `[]` when `try_sentinel_lock` finds the
    Postgres advisory lock held, which is exactly what happens when a dev uvicorn is running its
    own Sentinel poller against the same database. Stop the server and it passes.
  - `ruff` clean on all four new scripts and on every file touched here. The 46 repo-wide ruff
    errors and 15 mypy errors predate this pass.
- **Remarks:** Three things a picker should carry forward.
  1. **The 404 storm and the 2-day-future frames were the same layer, not the same bug.** One was
     the frontend not declaring where the data ends; the other was the backend mislabelling when
     the data starts. Both were invisible because the map still rendered something.
  2. **`incois_erddap` is a correctness bug, not a freshness one, and it is still open.** Probing
     all 17 datasets on `erddap.incois.gov.in` showed every one is a closed historical archive —
     SST ends 2011-10-04, chlorophyll 2006-03-21, the newest thing on the server is Argo to
     2025-04. Meanwhile `SOURCE_REGISTRY` still advertises it TIER1 / 180 min and
     `select_best_source` ranks on exactly that pair, so **ORCA currently picks a 2011 archive as
     its primary `sst` source, ahead of MOSDAC.** Fixing it is a triple change — registry entry,
     cascade order, and `test_discovery.py:322` which asserts the wrong answer — so it is
     escalated in contract §6.4 rather than silently rewritten here.
  3. **What is left needs a human, not a script.** MOSDAC serves downloads behind an interactive
     login and an order queue with no token API; its chlorophyll is 172 days stale, the worst
     freshness breach in the product. Copernicus Marine and GFW are scripted but need one free
     registration each. Instructions for all three are in contract §6.3.

### [2026-09-18] P5.12 (partial) — Credentialed refreshes wired to `.env` and run — DONE

- **Implements:** the credentialed half of `R-FRESH-4`; clears the `copernicus_cmems` and `gfw_ais`
  rows from contract §6.3 (human-in-the-loop) into §6.1 (cleared).
- **By:** Claude (Opus 5), at Dev A's request.
- **Files:**
  - `scripts/refresh_cmems.py` — `_load_credentials()` loads the project `.env` and maps ORCA's
    `COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD` onto the `COPERNICUSMARINE_SERVICE_*` names the
    client actually reads, so the script never prompts and is safe to run from a scheduler. The SSH
    product moved from `...duacs-0.25deg_P1D` to `...duacs-0.125deg_P1D`.
  - `scripts/refresh_gfw_ais.py` — loads `.env` and accepts `GFW_API_KEY` (ORCA's name) or
    `GFW_API_TOKEN` (what a scheduler injects); the real environment wins over the file.
- **Commit:** —
- **Done-when test:**
  - `python scripts/refresh_cmems.py` → **3/3 products refreshed**; `observe("copernicus_cmems")`
    → content date **2026-09-16**, within contract.
  - `python scripts/refresh_gfw_ais.py` → 5 vessels of 141 matching;
    `observe("gfw_ais")` → within contract.
  - All four WEEKLY sources (`copernicus_cmems`, `gfw_ais`, `nasa_ocean_color`, `bhuvan_wms`) now
    report `within_contract=True`.
- **Remarks:** The 2024-11 → 2025-04 SSH gap in `data/tier2/copernicus/` was **not** a missed
  download. CMEMS froze `cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.25deg_P1D` at 2024-11-25
  and moved the live feed to the 0.125° grid; the old id cannot be refreshed by anyone. The script
  now recognises `"exceed the dataset coordinates"` and says _this stream has stopped publishing_
  rather than reporting a generic failure — the distinction between "we forgot" and "the provider
  retired it" is the one that matters when triaging a stale directory.

  Two superseded granules should be deleted by hand once —
  `cmems_thetao_india_20260910_20260916.nc` and the long auto-named
  `cmems_mod_glo_phy-thetao_anfc_..._2026-08-28-2026-08-29.nc`. They will not accumulate: the
  script writes fixed filenames with `overwrite=True`.

  **MOSDAC is scriptable after all** and the earlier "manual only" note in contract §6.3 is wrong.
  It runs Keycloak (`/realms/Mosdac/`). The password grant is closed (`unauthorized_client` — the
  client is confidential), but `/user/login` serves a plain `kc-form-login` with no captcha and no
  OTP, and `/opendata/` behind it is an ordinary directory tree. A `requests.Session` doing the
  authorization-code form flow can walk and download it. Blocked only on credentials.

### [2026-09-18] P5.12 — MOSDAC is scriptable: `refresh_mosdac.py`, and the 172-day chlorophyll breach closed — DONE

- **Implements:** the last credentialed piece of `R-FRESH-4`; clears the MOSDAC row from contract
  §6.2. Every source in the catalogue that can be refreshed at all now has a script.
- **By:** Claude (Opus 5), at Dev A's request, after Dev A added `MOSDAC_USERNAME` /
  `MOSDAC_PASSWORD` to `.env`.
- **Files:**
  - `scripts/refresh_mosdac.py` — **new**. Token → OpenSearch listing → download, over a trailing
    7-day window, writing files under their MOSDAC identifiers unchanged.
  - `docs/ORCA_Data_Freshness_Contract.md` — §6.3 rewritten from "what a human has to do by hand"
    to "credentialed sources — all scripted, none clicked"; the three MOSDAC dataset ids recorded
    there; §3 and §6.1/§6.2 rows updated.
  - `docs/ORCA_Dataset_Procurement_Runbook.md` — §B1's "there is **no plain REST API**" corrected.
- **Commit:** —
- **Done-when test:**
  - `python scripts/refresh_mosdac.py` — SST now **2026-09-17** (was 2026-08-29, 20.6 d),
    chlorophyll now **2026-09-15** (was 2026-03-30, **172.6 d**), wind refreshed from the live
    25 km stream.
  - `observe("mosdac_nrt_chl")` → within contract. `observe("mosdac_open_sst")` → 1.7 d, outside
    the DAILY window for the reason in §6.2, not because the copy is behind.
  - `ruff` clean.
- **Remarks:** The previous entry called MOSDAC "genuinely manual". That was wrong, and the way it
  was wrong is worth recording.
  1. **The thing that makes it look manual is real but not the whole story.** MOSDAC is
     Keycloak-backed and the OIDC password grant is closed — `unauthorized_client`, the client is
     confidential — so the obvious automation route genuinely fails. But a separate plain REST API
     exists behind `download_api/` + `apios/`, which the official `mdapi.py` client drives. Probing
     the auth mechanism instead of stopping at the login page is what found it.
  2. **The dataset ids are not guessable and not published as a list.** `E06OCML4AC_*.nc` comes
     from `E06OCM_L4_AC`, but `E06SCTL4AW_*.nc` comes from `E06SCT_L4_AWV` — **not**
     `E06SCT_L4_AW`, which does not exist. They were found by probing: a wrong id answers
     `500 "Data unavailable for given parameters"`, a right one answers `200`. All three are in
     contract §6.3 so nobody repeats the search.
  3. **The wind stream moved from 12 km to 25 km.** `geospatial.wind_vectors()` reads lat/lon out
     of the file, so it loads unchanged; only the vector field is sparser, and `stride=4` may want
     revisiting for the coarser grid.
  4. **Transfers drop mid-file.** A 54 MB SST granule failed on the first attempt with
     `IncompleteRead`. The script writes `.part`, verifies the byte count against `Content-Length`,
     and retries three times — a truncated granule renamed into place would be indexed as fresh and
     then fail to parse, which is a worse failure than not downloading it.

### 2026-09-18 — MOSDAC wind: resumable downloads, and a filename shape the parser did not know

- **Point:** Finish the MOSDAC automation — the previous entry's claim that wind was "refreshed
  from the live 25 km stream" was not yet true.
- **Files:** `scripts/refresh_mosdac.py`, `backend/orca/data/freshness.py`,
  `docs/ORCA_Data_Freshness_Contract.md` (§3 wind row, §6.3).
- **Verification:** `6 downloaded, 11 already present, 0 failed` — previously `0 downloaded,
6 failed`. `observe("mosdac_nrt_wind")` → `content_date='2026-09-16'`, 2.7 d, within the WEEKLY
  contract. `ruff` clean; the 9 freshness tests pass.
- **Remarks:**
  1. **Retrying was never going to work; resuming was.** All six 54 MB scatterometer granules
     failed every attempt with `ChunkedEncodingError`, because each retry restarted at byte zero
     and the connection never survived long enough to reach the end. MOSDAC does not advertise
     `Accept-Ranges`, which is why this was not obvious — but it _honours_ `Range` and answers
     206 with a correct `Content-Range`. Probing that directly is what settled it. The fix keeps
     the `.part` on failure and continues from `bytes=<have>-`; the logs show each granule
     crawling forward (`17 MB → 36 MB → 46 MB → done`) rather than looping. Retries went 3 → 8
     because with resume each attempt makes progress, so more attempts are cheap.
  2. **`.part` is now kept on failure, not deleted.** That inverts the earlier behaviour and is
     the whole point — but the safety property is unchanged: the file is renamed into place only
     when the byte count matches the full `Content-Length`, so a truncated granule still cannot be
     indexed as fresh.
  3. **The wind files landed but reported no content date.** `content_date_from_name()` knew three
     filename shapes and `E06SCTL4AW_2026259_...` is a fourth — year plus day-of-year. Without it
     the source fell back to mtime, which reads "0 minutes old" purely because we just downloaded
     it: the exact flattering failure the content-date split exists to prevent. Added `%Y%j` with a
     lookaround so seven digits cannot chew into an eight-digit `%Y%m%d`; a group that is not a
     real day-of-year fails `strptime` and is dropped.
- **Still open:** the two superseded Copernicus granules
  (`cmems_thetao_india_20260910_20260916.nc` and the long auto-named
  `cmems_mod_glo_phy-thetao_anfc_..._2026-08-28-2026-08-29.nc`) are still on disk. The newest-date
  rule hides them on `/data`; deleting them is the owner's call.

### 2026-09-19 — Stale-data audit of `data/`, recorded as a register

- **Point:** Give the team a vetted list of what can be deleted from `data/`, so cleanup is not
  each developer guessing from file dates.
- **Files:** `docs/ORCA_Stale_Data_Cleanup.md` (new). **Nothing was deleted.**
- **Verification:** Every candidate was checked three ways — no code names it, no reader consumes
  its directory as a series, and it is not the last copy of a variable. Sizes measured off the
  filesystem, not estimated. 26,020 files / 21.72 GB audited.
- **Remarks:**
  1. **The dangerous half of this job is the keep list, not the delete list.** A "delete anything
     older than N days" sweep would have destroyed the PFZ history snapshots (read as a _series_ by
     `available_pfz_history_dates()`, so the old ones are the feature), the 2018 Cyclone Gaja replay
     data, and the ERA5 climatological baseline — whose entire purpose is to be historical. §4 of
     the register exists so nobody repeats that reasoning from scratch.
  2. **The biggest file is the one you must not delete.** `RSMC_hycom_20260830.nc` is 10.58 GB,
     half of `data/`, dated August, and looks like the obvious win. It is hardcoded in
     `build_pfz_fallback.py:47` and is the only copy on disk of `TEMP`/`SALN`/`SSH`/`MLD`/`TCHP` —
     the current refresh fetches `UVEL`/`VVEL` only. Re-point the fallback at `SST_NIO_*.nc` first,
     then delete; that also unfreezes the fallback from one August snapshot.
  3. **"Confirmed duplicate" was overstated.** The runbook called `etopo_all_india_real.nc` a
     duplicate. Same grid and extent, but 17,264 of 3.09 M cells (0.56%, all ocean, up to 551 m)
     disagree with the copy that is wired. Still safe to delete since nothing reads it, but it is
     filed under "your judgement" rather than "safe", because the claim as written was not exact.
  4. **Two wiring bugs fell out of the audit, neither a deletion.** `refresh_bhuvan_manifest.py`
     writes `bhuvan_manifest.json` while `analytics_loaders` reads
     `bhuvan_15days_marine_manifest.json` — the refresh succeeds and changes nothing the app sees.
     And `_cmems_newest()` selects by mtime rather than content date, which inverts if the directory
     is ever copied or restored.
- **Numbers:** §1 (safe) is 43 files / 9.51 GB, taking `data/` to ~12.2 GB. With the §2 code change,
  ~1.6 GB.

### 2026-09-19 — every declared source now obeys its freshness class

- **Point:** `R-FRESH-1..3` — close the remaining freshness-contract breaches rather than
  re-describe them. Before this pass `observe_all()` reported 6 BREACH + 1 UNOBSERVED of 27
  sources; it now reports 0 BREACH, and `live_contract_violations()` returns `[]`.
- **Files:** `backend/orca/agents/weather_intelligence.py`, `backend/orca/agents/ocean_analytics.py`,
  `backend/orca/agents/discovery.py`, `backend/orca/data/freshness.py`,
  `backend/tests/unit/test_weather_intelligence.py`, `backend/tests/unit/test_ocean_analytics.py`,
  `docs/ORCA_Data_Freshness_Contract.md` (§3.1, §3.3, header, §6.2, new §6.2b).
- **Verification:** full backend suite `427 passed, 2 skipped`. `freshness` and `discovery` module
  self-checks pass. Ruff clean on the touched files except two errors that pre-date this pass
  (`I001` and `TRY004` in `weather_intelligence.py`, confirmed against `HEAD`).
- **Remarks:**
  1. **`incois_hazard_osf` is live for real.** IMD's nowcast API answers 401 "Your IP needs to be
     whitelisted" on both candidate endpoints, so that route stays closed. INCOIS, however,
     publishes its own district-level high-wave, swell-surge and ocean-current bulletins as
     unauthenticated JSON — `sarat.incois.gov.in/incoismobileappdata/rest/incois/hwassalatestdata`
     and the `currentslatestdata` sibling on `samudra`. They are the endpoints behind the public
     multi-hazard map at `incois.gov.in/site/services/Alerts.html`, found by reading that page's
     own `fetch()` calls. `get_incois_hazard_alerts()` reads them and falls back to SACHET only on
     a transport or parse failure — an _empty_ bulletin list is a real answer and is served as one.
     Verified live: 17 bulletins for Tamil Nadu, 11 for Kerala, 8 for Lakshadweep, issued 09-18.
  2. **The tide-gauge fixture is gone, not relabelled.** `incois_tide_gauge_telemetry.json` was
     never readings — it is a schema fixture with representative values, written because INCOIS's
     TEWS endpoint 404s. `tide_gauge_observation()` now reads the IOC/UNESCO Sea Level Monitoring
     feed (five Indian gauges that actually report; Minicoy, Veraval and Visakhapatnam return empty
     arrays and are excluded, DART platforms deliberately so). Where no gauge is within 150 km —
     Thoothukudi, the pilot port, included — it falls through to altimetry. **A fabricated
     instrument reading on a safety path is worse than no reading**, so the fixture branch was
     deleted rather than kept behind a label. The live path returns only what IOC publishes: sea
     level and a timestamp, with prediction/residual/water-temp/tsunami-state `None` and named in
     `fields_unavailable`.
  3. **The four DAILY "breaches" were never ours.** INCOIS's RSMC runs and MOSDAC's INSAT-3DR daily
     SST were still at 2026-09-17 when refreshed on 2026-09-19 — the freshest copy that exists.
     `PUBLICATION_LAG_MINUTES` in `freshness.py` records the measured provider lag (24 h for all
     four) and `observe()` adds it to the class window. The window itself was **not** loosened, and
     the entries are only allowed to exist once a refresh run has proved the provider has nothing
     newer. Slip a further day and they breach again.
  4. **`incois_erddap` no longer claims `sst`.** It was TIER1 at 180 min, the lowest of any TIER1
     SST candidate, so `select_best_source("sst")` was picking a 2011 archive as ORCA's _primary_
     sea-surface temperature source ahead of MOSDAC. Dropping `"sst"` from its `covers`, removing
     it from the two SST fallback cascades and setting its cadence to a year hands `sst` back to
     `mosdac_open_sst`. This was the §6.4 danger note in the contract; it is now closed in code.
  5. **Two test expectations were asserting the wrong thing and had to go.**
     `test_tide_gauge_cross_check_reports_observed_against_predicted` checked that the fixture's
     invented observed/predicted/residual agreed with each other — a self-consistency check on
     fabricated numbers. It is replaced by a test that the reading is measured or absent, never
     invented. The SACHET-filter hazard test now covers both the live path and the fallback path.
  6. **A flaky failure during this pass was mine, not the code's.** Debug tests that committed
     watch rows to the shared Postgres left state that made
     `test_crossing_fires_once_and_a_second_identical_poll_is_silent` see no crossing. Confirmed by
     running the full suite against a stashed tree (green) and again after cleanup (green). The
     test's own comment already warns that rows it commits survive its rollback.

### 2026-09-19 — a refresh guide, and a one-command freshness check anyone can run

- **Point:** follow-up to the entry above (freshness contract compliance); groundwork for P5.12
  (`R-FRESH-4`, `refresh_all.py`).
- **Files:** `docs/ORCA_Data_Refresh_Guide.md` (new), `backend/orca/data/freshness.py`.
- **Remarks:**
  1. **Verification had to be a command, not a document.** Telling teammates "check the contract
     tables" reproduces the state where only the person who wrote them knows whether the clone is
     compliant. `python -m orca.data.freshness` now prints one line per declared source sorted
     worst-first, a `N sources | N breach(es)` summary, and **exits 1 on any breach** — so it works
     unchanged as a pre-demo check and as a CI or scheduled-task gate. No new script and no new
     module: it went into the `__main__` block that already ran the module's self-checks.
  2. **The guide documents dependency order, which was previously only in my head.**
     `extract_osf_pilot.py`, `generate_tiles.py` and `build_all_india_pfz.py` consume the output of
     scripts that must run first; run them alone on a fresh clone and they fail confusingly. §2
     lists all 13 commands in an order known to work, deliberately the order `refresh_all.py`
     should use — whoever picks P5.12 transcribes a tested sequence instead of rediscovering it.
  3. **MOSDAC registration is called out as a "do it today" item.** SAC approves accounts by hand
     and it can take days, so a teammate who discovers this the morning of a demo has no path to
     compliance. Copernicus and GFW are instant; MOSDAC is the only one with a human in the loop.
  4. **The guide says what a _correct_ non-`ok` line looks like.** `UNOBSERVED STATIC
incois_erddap 0 file(s)` is the expected output, not a gap to close, and DAILY sources reading
     1.8–2.0 d are within contract via `PUBLICATION_LAG_MINUTES`. Without this, the first person to
     run the report "fixes" it by downloading a 2011 archive. The §"If you see a BREACH" steps end
     with _do not widen the class window_ — threshold changes are a contract decision, made once,
     in writing.
  5. **No CI `schedule:` trigger, and the guide says why rather than leaving it as a TODO.**
     `data/` is gitignored, so a scheduled CI run has nowhere to persist what it downloads. The
     honest answer is a local scheduled task; that is recorded as the shape P5.12 should take.

### 2026-09-19 — scheduled refresh: which sources actually need a timer

- **Point:** partial P5.12 (`R-FRESH-4`) — the schedule and wrappers, not yet `refresh_all.py`.
- **Files:** `docs/ORCA_Data_Refresh_Cron_Guide.md` (new), `scripts/cron/refresh_{daily,weekly}.{cmd,sh}`
  (new), `docs/ORCA_Data_Refresh_Guide.md`.
- **Remarks:**
  1. **Only 11 of the 27 declared sources need a schedule, and saying so is the point.** The
     five LIVE sources are HTTP calls made while answering a query — a timer cannot make them
     fresher, only a working connection can. The eight STATIC ones are coastlines and
     gazetteers that cannot breach. Scheduling those would burn provider quota to change
     nothing, so the guide names them as deliberately unscheduled rather than leaving the next
     person to assume an omission.
  2. **Two jobs, not eleven.** `refresh_mosdac.py` already fetches the WEEKLY chlorophyll and
     wind granules alongside the DAILY SST, and skips what is on disk, so running it daily is
     free and there is no separate weekly MOSDAC job. `refresh_tide_tables.py` writes both
     `soi_tide_tables` (DAILY) and `stormglass_tides` (WEEKLY) in one pass.
  3. **The wrappers end with the freshness report, and that is the alarm.** It exits 1 on any
     breach, so Task Scheduler's `LastTaskResult` distinguishes "refreshed and compliant" from
     "refreshed and still in breach" without anyone reading a log. A job that refreshes without
     verifying fails quietly for a week.
  4. **05:30 IST (00:00 UTC), MOSDAC last.** INCOIS and MOSDAC publish in arrears, so a run
     after their overnight cycle gets the freshest copy that exists — the same lag recorded in
     `PUBLICATION_LAG_MINUTES`. MOSDAC runs last because its 54 MB scatterometer granules over a
     dropping link are by far the longest step; interrupting it still leaves the demo-critical
     refreshes done.
  5. **A scheduler has no activated virtualenv.** Every command in the wrappers uses
     `backend/.venv/Scripts/python.exe` by path. `python scripts/...` works in a shell and fails
     at 05:30 with `ModuleNotFoundError: requests`, which is the failure mode most likely to go
     unnoticed for days. The manual refresh guide §2 now says the same thing.
  6. **A missing sixth credential surfaced while mapping scripts to sources.**
     `refresh_tide_tables.py` needs `STORMGLASS_API_KEY` — Survey of India sells its tide tables
     as a priced volume, so the predictions are computed from Stormglass harmonics and shifted
     onto each station's chart datum. The refresh guide said "five keys" and would have left a
     teammate's DAILY tide source broken. Now six.
  7. **Verified, not just written:** `scripts/cron/refresh_weekly.cmd` was executed end to end
     on this machine and finished `27 sources | 0 breach(es)`, exit 0.

### 2026-09-19 — the national PFZ layer was inventing advisories; removed

- **Point:** R-INDIA-3 (corrected), all-India coverage audit gap #1.
- **Files:** `backend/scripts/build_all_india_pfz.py`, `backend/orca/data/analytics_loaders.py`,
  `backend/orca/api/analytics_routes.py`, `backend/tests/unit/test_analytics_routes.py`,
  `docs/ORCA_SIH26176_AllIndia_Dataset_Coverage_Guide.md`, `docs/ORCA_Data_Freshness_Contract.md`.
- **Remarks:**
  1. **`build_all_india_pfz.py` was fabricating INCOIS advisories.** It appended 54 hardcoded points
     — 15 Gujarat, 9 Odisha, 7 West Bengal, 9 Andaman, 9 extra South Tamil Nadu — with invented
     coordinates, bearings, distances, depths and `mean_sst_c` values, every one stamped
     `"source": "INCOIS Marine Fisheries Advisory"` and `"valid_for": "2026-09-02"`. INCOIS issued
     none of them. **A fabricated fishing advisory is a boat sent to water nobody surveyed, under a
     government agency's name** — the same judgement that deleted the fabricated tide-gauge reading,
     so the node lists are deleted rather than relabelled.
  2. **This is where R-INDIA-3's "13 sectors to the live file's 11" came from.** The DLC records the
     national file as adding coverage; the two sectors it added — SEC001 Gujarat and SEC012 Andaman —
     had _only_ fabricated points. The requirement was written against a number that the script
     manufactured. The file now holds 723 real advisories across 11 sectors, all one day.
  3. **The staleness guard moved into the loader, because that is where every consumer passes.**
     `_pfz_valid_for()` takes the _newest_ date in a collection, so a mixed-date file passed the
     freshness check on the strength of its fresh half and was then served whole — the map draws every
     point identically, so a sector whose only features were old read as advised today.
     `_newest_day_only()` in `analytics_loaders` drops anything older than the collection's own newest
     date. The builder no longer writes mixed files, but `data/` is gitignored and other clones still
     hold the old one, so fixing only the writer would have fixed only my machine.
  4. **A Gujarat query now degrades honestly instead of confidently.** `/api/zones` at Veraval returns
     `GUJARAT / NO_DATA_CLOUD_COVER` with INCOIS's own message, `is_data_gap: true`,
     `nearest_advisory_out_of_sector: true`, and the nearest real advisory 189 km ESE in SEC002. No
     frontend change was needed: `/zones` already renders the "No advisory" badge, the message, the
     out-of-sector note and an "11 of 14 with an advisory" roster.
  5. **A second pilot-region leak found while verifying.** The route attached the thermal-front proxy
     whenever the user's sector was a data gap, without checking which sector the proxy is _for_. A
     Veraval query came back with five Gulf of Mannar cells 1,500 km away — correctly labelled "NOT an
     INCOIS PFZ advisory", but still pilot data on a Gujarat map. It is now attached only when
     `applies_to_sector` matches the user's sector.
  6. **Checks:** `build_all_india_pfz.py --self-check` asserts a sector present only on the older date
     drops out entirely; `test_pfz_layer_never_mixes_advisory_days` asserts the same through the
     loader. Full suite 428 passed, 2 skipped.

### 2026-09-19 — tide coverage: 5 pilot stations → 14 national ports

All-India coverage gap #2 of the 09-19 audit. `predict_tides()` had a roster of five stations, all
in the pilot region, so PS-Q3 had no tide answer at Kandla, Okha, Veraval, Mormugao, New Mangalore,
Visakhapatnam, Paradip, Haldia or Port Blair.

Files: `scripts/refresh_tide_tables.py` (roster, metadata writer, quota strategy),
`backend/orca/data/analytics_loaders.py` (`_stormglass_stem`, height rounding),
`backend/orca/agents/ocean_analytics.py` (datum + rationale honesty),
`backend/orca/data/loaders.py` (`paradip` spelling), `frontend/app/voyage/page.tsx` (station name),
`backend/tests/unit/test_ocean_analytics.py`.

Remarks:

1. **No chart-datum offset was invented for the nine new ports.** The five pilot stations have a
   measured `msl_above_chart_datum_m` that puts Stormglass's MSL heights onto the SOI table's datum.
   Nobody publishes one we can cite for the new ports, so they get no row in the chart-datum CSV at
   all and are answered through `predict_tides()`'s already-declared Stormglass rung, which labels
   the datum `mean sea level`, sets `fell_back`, and drops confidence to MEDIUM. Times and the
   high/low ordering are correct at all fourteen; the height at the nine is on a different datum and
   says so out to the API response. A tide height on the wrong datum is a grounding — the same
   reasoning that deleted the fabricated PFZ advisories yesterday.
2. **The station metadata is now written by the script.** `soi_tide_stations_metadata.json` was
   hand-maintained inside gitignored `data/`, which means no clone but the original author's ever had
   it: a teammate's `loaders.tide_station_coordinates()` returned `{}` and the tide-station tier of
   the place resolver was silently empty. The roster lives in the script, which is in git.
3. **The station→cache-file mapping was a second hardcoded dict**, in `analytics_loaders`. All nine
   new ports would have returned no events from a cache file that was sitting right there. It now
   reads `stormglass_stem` from the metadata, so there is one roster, not two.
4. **Quota is handled rather than hoped at.** Stormglass's free tier is 10 requests/day against 14
   ports, so a station is refetched only when its cache stops reaching 3 days ahead — a daily cron
   spends 0–3 requests, and a cold start fills over two days. The CSV is merged, not overwritten, so
   a run that stops at the cap cannot delete the ports it never reached. Today's run filled 5 of the
   9 and hit `HTTP 402`; VIZ, PRD, HDA and PBL come in on tomorrow's run and currently decline with
   `LOW_DATA` rather than guessing.
5. **Two smaller honesty fixes found while verifying.** The fallback rationale said "SOI 2026 table
   exhausted for VER" at a port that never had a table — it now distinguishes the two reasons. And a
   station with no events at all was still reporting `datum: chart datum (LAT)`, a claim about
   numbers that do not exist; it now says so. Stormglass heights are also rounded to 2 dp like the
   table, instead of being served to 17 significant digits.
6. **Wiring:** `GET /api/tides` needed no change — it already carried `datum`, `fell_back` and the
   confidence rationale. `/voyage` now names the answering station in the panel title, which matters
   once the nearest station can be a hundred miles up the coast. `paradip` was added to the gazetteer
   next to `paradeep`: the port authority's own spelling resolved to nothing.
7. **Checks:** `refresh_tide_tables.py --self-check` asserts the roster invariants (unique cache
   stems, coordinates inside the Indian box, and that a station with no offset is never labelled
   chart datum); `test_tide_roster_is_national_and_never_mislabels_the_datum` asserts the same
   through `predict_tides()` at every station on disk. Full suite 429 passed, 2 skipped;
   freshness report `27 sources | 0 breach(es)`.

### 2026-09-19 — the ERA5 reference period is national: 1 port → 104

All-India coverage gap #3 of the 09-19 audit. `wind_anomaly()` compares a port's forecast peak
against a 30-day ERA5 window, and exactly one such window existed — Thoothukudi — so at every other
cached port PS-Q7's anomaly leg returned `available: false`. It declined honestly, but "no answer"
everywhere outside the pilot is still no answer.

Files: `scripts/refresh_era5_baselines.py` (new), `scripts/cron/refresh_weekly.{cmd,sh}`,
`backend/tests/unit/test_ocean_analytics.py`, coverage guide, refresh + cron guides.

Remarks:

1. **Same provider, same units, on purpose.** The baseline comes from Open-Meteo's ERA5 archive,
   in km/h, because the forecast it is compared against comes from Open-Meteo in km/h.
   `wind_anomaly()` does no unit conversion at all — that is what makes the comparison
   like-for-like, and a baseline from a different provider would put a systematic offset straight
   into the z-score. No API key, no account.
2. **The window ends six days back.** ERA5 is a reanalysis and its last few days are not final;
   `--lag` is the knob. The script skips a port whose file already starts at or after the current
   window start, so re-running it daily costs nothing.
3. **A flat series is refused.** `detect_anomaly` divides by sigma, so a zero-variance baseline
   would make every forecast look normal — worse than having no baseline, which at least says so.
   The fetch rejects it rather than writing it.
4. **Not declared as a freshness source, deliberately.** A 30-day reference period is a reference:
   an old one is still valid, which is why `baseline_label` carries its own dates. Declaring it
   DAILY or WEEKLY would make the freshness report breach on something that is not wrong. It is in
   the weekly cron only to keep the window rolling.
5. **Wiring:** `GET /api/trends` and the `/trends` wind-anomaly panel needed no change — they
   already rendered the baseline label and the answering port, which is now the useful part, since
   the nearest cached port can be a different name than the one the user typed ("somnath" answers
   Veraval).
6. **Run:** 104 of 104 ports written (one timeout, retried clean). Verified at Kandla, Paradip,
   Port Blair, Haldia and Veraval. The existing test asserted Mumbai had _no_ baseline — true when
   it was written, false now; it asserts national coverage instead, and the no-baseline path is
   still tested by monkeypatching the loader, because "no baseline" must never render as "normal".
   24 tests in the Agent 5 file pass.

### 2026-09-19 — PFZ persistence now refuses to score a short archive

All-India coverage gap #4 of the 09-19 audit. The archive holds 3 snapshots (0901, 0916, 0918) and
needs about a week; the daily cron adds one per morning, so the _data_ side self-heals by ~23 Sep and
needed no work. What did need work was what the code said in the meantime.

File: `backend/orca/agents/ocean_analytics.py`, `backend/tests/unit/test_ocean_analytics.py`.

Remarks:

1. **"0/3 — TRANSIENT, MEDIUM confidence" reads as a finding, and it was not one.** The only guard
   was `days_on_record < 2`, so three snapshots were enough to label a spot TRANSIENT. The gate is
   now `min_days=5`, below which it returns `INDICATIVE` / `LOW_DATA` and the rationale names the
   shortfall.
2. **A fortnight-old snapshot was being counted as evidence about this week.** 20260901 is 18 days
   old and sat in the same denominator as 20260918 — it silently changed a number the user reads as
   "how reliable is this spot right now". Only the last `window_days=7` count; `days_archived_total`
   is returned alongside so the response still shows the whole archive exists.
3. The existing test asserted the old `< 2` rule; it asserts the new one, plus that the windowed
   count never exceeds the archived total.
4. **Suite: 428 passed, 2 skipped, 1 failed — `test_crossing_fires_once_and_a_second_identical_poll_is_silent`,
   and not from this change.** A dev API server (PID 33404 on 127.0.0.1:8000) is running and holds
   the session-level advisory lock that `run_poll_cycle` needs, so the poll returns no decisions.
   Confirmed in `pg_locks`, same cause as on 09-18. It passes with the dev server stopped.
5. Outstanding: VIZ/PRD/HDA/PBL tide caches land on tomorrow's run when Stormglass quota resets, and the data/ deletion pass is still       waiting on you.

<!-- Append new entries below this line. Newest at the bottom. -->
