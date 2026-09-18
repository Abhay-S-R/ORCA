# ORCA — DLC Verification Report (2026-09-18)

> **What this is.** A check of `docs/DLC_implementation_plan.md` against `docs/orca_final.md` (the
> complete feature list) and against the working tree. It answers four questions: are the DLC's
> points still true, what does orca_final ask for that the DLC never planned, where do the two
> contradict each other and which side should win, and which stack choices should change.
>
> **Decisions this report was written under** (answered by the team before the analysis):
> conflicts are resolved case by case with a recommendation · the deliverable is this report plus
> updates to the DLC plan and log (orca_final.md is **not** edited) · alert channels are rendered and
> simulated, except web push, which is real · time is not a constraint on recommendations · **8 core
> languages** with full text and voice · the demo runs on **one local laptop (RTX 3050, 6 GB)** · the LLM
> is **Gemini** · **`/demo` (five scenarios) and `/alerts` are in scope**.
>
> Every claim below was checked against the tree on 2026-09-18, with a file and line where it
> matters. Where a claim is my recommendation rather than a finding, it says so.

---

## 1. Summary

| | Count |
|---|---|
| DLC points checked | 69 |
| DLC `Now:` lines that no longer match the tree | **14** (§2) |
| DLC points already partly or fully done but not logged | **7** (§2) |
| orca_final features with **no DLC point** | **31** (§3), of which 20 should be added, 11 dropped or moved to the roadmap |
| Direct contradictions between orca_final and the DLC | **17** (§4) |
| orca_final claims the tree contradicts today | **19** (§5) |
| Recommended stack or approach changes | **10** (§6) |
| Bugs found in passing | **3** (§7) |

**The five findings that matter most**

1. **The safety-path CI guard does not exist.** DLC principle 2 and orca_final §5.5 and §27.3 both say
   CI fails the build if `risk_assessment.py` imports an LLM. `verify_ci_guards.py` has exactly three
   guards: vendor SDK, persona leak, and a secret scan. None of them checks the safety path, and
   `ci.yml` doesn't even run that script (it repeats two of the checks as inline greps). This is the
   project's central claim and nothing enforces it. → new **P0.12**.
2. **Two vocabularies for vessel class.** The DB and auth layer use
   `catamaran / fibreglass / mechanised / trawler / cargo` (`infra/db/001_init.sql:55`,
   `auth/schemas.py:109`). The safety engine uses `small_fishing / mechanized_trawler / cargo_vessel`
   (`risk_assessment.py:21`). Once P3.1 feeds a user's registered vessel into the verdict, every
   registered boat either fails validation or silently falls back to `small_fishing`. → new **P0.13**.
3. **The TTS model's licence is non-commercial.** `facebook/mms-tts-*` is published CC-BY-NC 4.0.
   P6.2's business case names paying institutional buyers (state fisheries departments, INCOIS), and
   a non-commercial voice model contradicts that on the first due-diligence question. Neither
   document mentions it. → §6.2 and new **P3.8**.
4. **orca_final is the judge-facing document, and 19 of its claims are false against the tree**
   (§5): `ORCA_LLM_ENABLED`, "eight CI guards", 47 sources (27 exist), ten languages with voice,
   species tags, WhatsApp/USSD/push delivery, phone OTP, rate limiting, `/demo`, a driver.js tour, a
   Workbox service worker, CARTO Dark Matter + MapTiler. P0.1 only covers the README. → new **P0.14**.
5. **Distress phrases are missing for three of the eight core languages.** `_DISTRESS_PATTERNS` has
   `en 9 · ta 4 · hi 4 · ml 8 · te 8`, and nothing for **kn, bn or mr**. With 8 core languages decided,
   an SOS typed in Kannada, Bengali or Marathi currently isn't detected. P3.7 only covers Tamil.
   → P3.7 widened.

---

## 2. DLC points vs the tree — stale `Now:` lines and unlogged work

"Stale" means the point's description no longer matches the code, so whoever picks it up would
start from a false premise. Each one is corrected in the plan in this change.

| Point | DLC says | Tree says (2026-09-18) | Action |
|---|---|---|---|
| **P0.2** | Delete `p1/p2/p3.png`; `check_early_exit()` at `planning.py:187`; verify the basemap **key** | The PNGs are already gone (`assets/` holds only `orca1–5.png`). The stub is at `planning.py:220`. The basemap is **keyless** CARTO Positron + OpenSeaMap (`frontend/app/map/basemap.ts`), so there's no key to verify | Rewritten. Deleting the stub is fine, but orca_final §4.1 wants a *real* early exit, so a new point (**P2.12**) builds it |
| **P0.3** | `voice.py:141` | Confirmed: `WhisperModel("small", device="cpu", compute_type="int8")` | Valid. Also see §6.1: Whisper is weak on Indic speech |
| **P0.4** | `frontend/app/lib/session.ts:9`, `sessionStorage` | **The file doesn't exist.** The session id is now the chat id held in `localStorage` (`ask/chatStore.ts`, sent at `ask/useAskThread.ts:236`), so reload survival is probably already done | Rewritten: verify the reload half, build only the "say so when history is lost" half |
| **P0.8** | "six of eleven graph nodes contain no AI" | Eleven nodes (`graph.py:439-449`). **Five** never call a model: `distress_check, weather_intelligence, geospatial, risk_assessment, visualization`. `ocean_analytics` calls one at DEEP depth. `language_ingress/egress` run IndicTrans2, which is a neural model | Corrected to "five of eleven nodes call no model — and every node that can stop someone going to sea is among them". The "six" wording is false, and a judge can check it on the trace |
| **P1.1** | Replace `_PILOT_GAZETTEER` (16 South TN places) | **Already done, not logged.** Renamed `_GAZETTEER` (`data/loaders.py:172`), about 121 entries including Veraval, Kakinada, Port Blair and Kavaratti | Run the Done-when test and log it. Native-script keys (P1.5) are still missing |
| **P1.7** | `distress.py:75` is Chennai-only | **Partly done.** `nearest_sar_station()` (`distress.py:90`) finds the nearest ICG station from `icg_sar_stations.json`, but every station's `phone` is `null`, so what the user actually sees is still the Chennai or 1554 contact | Rewritten: show the **parent MRCC's** number for the nearest station (Mumbai / Chennai / Port Blair), not the station's missing one |
| **P2.2** | `lead_with_verdict` "is thrown away at the wire" | **Half done.** It's serialized on the SSE payload (`api/main.py:338`). `verdictScore()` and `ScoreRing` are still rendered (`PersonaAnswerMatrix.tsx:53,59,399`) | Rewritten: frontend half only |
| **P2.4** | No reconciliation | Confirmed for the general case. Lightning dual-source agreement **exists** (`weather_intelligence.py:507`, surfaced at `main.py:377`), and orca_final's conflict banner targets `/safety`, which P4.1 deletes | Point kept. The lightning banner moves to the `/ask` card |
| **P2.5** | Critic runs only at DEEP (`graph.py:411`) | Confirmed. Also, `critic → language_egress` is a straight edge (`graph.py:461`), so a real re-invocation needs a new conditional edge back to the named agent, not just a gate change | Note added |
| **P2.9** | `planning.py:203` passes only the query | **Already passes history**: `classify_intent(query, state.get("session_history"))` at `planning.py:236` | Rewritten: run the Done-when test ("what about tomorrow?"). If it passes, log it DONE |
| **P2.11** | Build an LLM-off toggle | Confirmed missing. **No `ORCA_LLM_ENABLED` exists anywhere**, although orca_final §5.5 and §28 describe it as shipped | Kept. It must be the env var orca_final names |
| **P5.4** | Caches exist for five ports, Visakhapatnam asymmetric | **Largely done.** `data/tier1/weather` holds 104 Open-Meteo caches, and there are 104 marine and 104 lightning caches | Rewritten: verify symmetry, log it |
| **P5.5** | "Gujarat has no IMBL geometry at all" | **The geometry is on disk and loaded.** `india_maritime_boundary_lines.geojson` has `Pakistan - India`, `Bangladesh - India`, `Maldives - India`, Myanmar, Thailand and Indonesia lines, read at `geospatial.py:184`. What's missing is that the verdict's `imbl_distance_nm` is still computed only against the **Sri Lanka EEZ** polygon (`geospatial.py:159`). The fishing ban already has `fishing_ban_status()` (`geospatial.py:679`) and `GET /api/fishing-ban`, but the query path and the verdict never call it | Rewritten: feed the nearest foreign boundary into the verdict, and wire the ban into the query path |
| **P5.11** (`R-NEW-15`) | Bhuvan catalogued, not shipped | Matches (`load_bhuvan_wms_services`) | Valid |

**Internal inconsistencies in the plan itself** (all fixed): the header says 69 points, the footer
says 65; "Phase 0 — 9 points" lists 11; the log's seed entry says 71 requirement IDs, the header 76;
P5.11 is listed after P5.13; the Extension Pack contains a truncated ID `R-SAFE-` (an unfinished
reference, harmless, but it shows up in any ID grep).

**Confirmed accurate** (checked, nothing to change): P0.5 (`safety_floor_for_missing_inputs` at
`resilience.py:175`, no staleness floor yet) · P0.7 (tides 2026-09-16 08:46 → 2026-09-23 04:04 IST,
five stations) · P0.9 (`tsunami_trigger_state` relayed verbatim, `ocean_analytics.py:691`) · P1.3
(no `OUT_OF_SCOPE` / `refusal_reason` anywhere) · P1.6 (`_PILOT_SECTOR = "SEC006"`,
`ocean_analytics.py:56`) · P2.6 (Discovery isn't a node) · P3.1 (no bearer on `/query`) · P3.2
(`session_id=None`, `main.py:459`) · P3.5 (no romanized detection) · P3.6 (`NotImplementedError`,
`risk_assessment.py:139`) · P4.2 (`Clock()` at `StatusBar.tsx:50`, `FeedStatus()` at `:80`) · P5.1 ·
P5.2 (the cascade exists, `discovery.py:103`) · P5.7 (only `offset_east/west` candidates,
`voyage.py:285`; voyage isn't a graph node).

---

## 3. In orca_final, not in the DLC

These features appear in orca_final and have **no point** in the plan, so today they would never be
built, and nobody decided that. Each gets a recommendation. **ADD** points are now in the plan;
**DROP / ROADMAP** items are recorded in plan §11 as decisions, the same way `R-AUTH-4` is.

| orca_final § | Feature | In tree? | Recommendation |
|---|---|---|---|
| §27.3 | Safety-path LLM guard, provenance guard, fabricated-number guard | No (3 guards exist) | **ADD P0.12.** Safety-path guard: 30 minutes, highest value. Provenance guard as a narrow test on the `final_response` payload. Drop "fabricated-number guard" as a CI claim (it can't be checked statically), since P2.2 and P4.6 cover the behaviour |
| — | Vessel-class vocabulary alignment | Mismatch (§1 #2) | **ADD P0.13** |
| §4.1, §24 | Adaptive early exit with cancelled branches drawn dotted | Post-hoc only: ocean data is thrown away at reporting (`graph.py:323`), and the branches have already run | **ADD P2.12** |
| — | Gemini quota budget | Not considered anywhere | **ADD P2.13.** After P2.5 every query makes ≥2 model calls (reporting + critic), and free-tier rate limits will return 429s mid-demo |
| §14.1 | 8 core languages with verified voice | 4 verified TTS (en/hi/ta/te); ASR is `small` on CPU | **ADD P3.8** |
| §13.1 | Distress phrases in every core language | kn/bn/mr have none | **Widen P3.7** |
| §8.1, §9.1, §15.3, §5.2 | Vessel cruise speed, fuel burn, engine redundancy | Not in `vessels` (`001_init.sql:57`) | **ADD P3.9** (migration `005`). Worthwhileness (P5.8), fuel economics (P5.9) and crew deltas (R-NEW-14) can't be computed without these. Today they'd be fabricated |
| §15.3 | Saved locations / Fishing Location Centres, one-tap chips | No | **ADD P3.10.** Cheap, and it's the fisherman's 04:00 interaction |
| — | `/alerts` page (replaces `/safety`) | No | **ADD P4.11–P4.13** (§8 below) |
| §6.3, §7.2 | Five escalation bands, full-screen critical alert, acknowledge-to-stop | No | **ADD**, folded into P4.12 and P5.6 |
| §29.2 | `/demo` with five scenarios | No route | **ADD P6.6–P6.9** |
| §7 | Border-crossing live demonstration (seven beats) | No | **ADD P6.7** |
| §23 | Gaja replay UI | Backend exists (`replay/gaja.py`, `GET /api/replay/gaja`), no surface | **ADD P6.8** |
| §12.1 | WhatsApp, missed-call callback, VHF script, display board, Nabhmitra format | Renderers exist for web/SMS/IVR/USSD only (`channels/renderers.py`). Dispatchers for in-app/SMS/IVR only | **ADD P6.10** (render + simulate, each with `DispatchResult.status="simulated"`) |
| §12.1 | Web push (real) | No | **ADD P7.3** (needs P7.1's service worker) |
| §21 | Offline basemap tiles | Online CARTO only | **ADD P7.4.** Beat 7 of the border demo ("works with the network pulled") needs it |
| §11.2 | Watch geometries: home port, point, area, route, boundary | The DB enum is *condition* types (`weather, wave_height, lightning, cyclone, geofence_approach, pfz_shift`), not geometries | **ADD P5.17** |
| §11.1 | Adaptive Sentinel cadence | Fixed interval | Folded into P5.17 |
| §9.3 | Tides at all Indian tidal ports | 5 stations, 8-day window | **ADD P5.14** (tide model, §6.4) |
| Freshness contract §6 | Live fetch for `incois_hazard_osf` and `incois_tide_gauge` (both LIVE-class, files from 2026-09-03) | No point owns it | **ADD P5.15** |
| §9.1a | Small Vessel Advisory view | No | **Fold into P4.4** (fisherman persona filters to vessel endurance, which needs P3.9) |
| §9.1a | Tuna Advisory layer | No data | **ADD P5.16 as conditional**: check whether INCOIS publishes a scrapable tuna advisory. If yes, extend `scrape_pfz_advisories.py`. If no, record the refusal the way `R-NEW-13` did |
| §9.1a | Species / exploited-stock tags | No data — verified | **DROP** (already decided, `R-NEW-13`). orca_final §9.1a must be corrected (P0.14) |
| §9.1b | Solunar bite-time calendar | No | **DROP.** It serves no PS clause (principle 5), orca_final itself calls it "the weakest-claimed feature", and it adds an astronomy dependency |
| §12.7 | Cooperative corroboration (*k* ≥ 3) | No | **ROADMAP.** A sound design, but it's a new endpoint, a binning store and an anonymity proof, for a feature a judge can't see without real boats reporting |
| §12.6 | Feedback calibration view | Feedback is collected (`POST /api/feedback`); no calibration view | **ROADMAP** |
| §15.1 | Phone OTP | No | **DROP.** It needs real SMS, and SMS is simulated (DLT) |
| §6.1 | Port limits, anchorages, naval exercise areas | No | **DROP.** There's no machine-readable public source. Naval exercise NAVAREA warnings are text bulletins |
| §22.2 | Object storage | No | **DROP.** Single laptop, local disk |
| §25 | Per-user / per-IP rate limits | No | **DROP the claim, or ADD** a one-line middleware. Recommend dropping the claim for the finale |
| §14.3 | Sarvam-105B on the reporting tier | No | **ROADMAP statement only.** A 105B model doesn't run on a 6 GB laptop, so present it as a deployment option, never as something the demo shows |
| §13.2 | Position re-transmission on a tightened interval | No | **ROADMAP** (needs a real device-side loop) |
| §8.4 | GPX / CSV voyage export | No | **ADD**, folded into P5.7 (a navigator persona deliverable, about 30 lines) |

---

## 4. Contradictions — orca_final vs the DLC, and which should win

| # | Topic | orca_final | DLC | Recommend | Why |
|---|---|---|---|---|---|
| 1 | Headline | "10 collaborating agents" | P0.8: stop leading with it | **DLC**, with the corrected count (§2 P0.8) | Engine tags will show 11 nodes on screen, and a count that doesn't match the trace looks invented |
| 2 | Languages | 10, all ✅ voice | 10 detected, 4 verified voice | **Neither: 8 core** (team decision), gu/or text-only until verified | |
| 3 | Bhashini | "the institutional translation and speech backend" | Prepared seam, not a connection | **DLC** | It isn't connected |
| 4 | Species tags §9.1a | Shipped feature | Verified: do not build | **DLC** | The data has no such field |
| 5 | `/safety` | A core route; the lightning banner, tour step 3 and the legend all live there | P4.1 removes it | **DLC**, but move the lightning conflict banner and the threshold tiles onto the `/ask` card | Two pages on one endpoint |
| 6 | Fisherman nav | Ask, Safety, Map, Zones, Watches | `/ask`, `/map`, `/watches` | **Keep `/zones` for the fisherman** (a deviation from the DLC) | PS-Q1 (fishing zones) is the fisherman's first question after safety, and cutting its surface costs more than one nav item |
| 7 | Chat history | Full rail, PostgreSQL, import | `R-AUTH-4`: "deliberately not built" | **Tree wins: it's already built** (`chats_routes.py`, `003_chat_history.sql`, `ChatHistoryRail.tsx`). The DLC line is false | Keep it. The DLC's privacy point still applies, so add the retention window and delete endpoint it asked for |
| 8 | Critic iterations | SHALLOW 1 review, STANDARD 1 revision, DEEP up to 3, async | Every query, cap **one** re-invocation | **DLC** | Latency, and Gemini quota (§6.5). Three passes is up to 4 LLM calls per query |
| 9 | Post-login flow | Language (mandatory) → persona (skippable) → tour | Language → role, **both mandatory** | **DLC** | P4.4 turns persona into different layouts, so an unset persona gives an undefined screen. Anonymous users are unaffected |
| 10 | Tour | driver.js coach-marks | Real queries, not coach-marks over a frozen screen | **DLC.** driver.js isn't installed and shouldn't be | framer-motion is already a dependency |
| 11 | Service worker | Workbox | Hand-written `sw.js`, no plugin | **DLC** | Three cache strategies. Revisit only if it grows past about 150 lines |
| 12 | Basemap | CARTO Dark Matter + MapTiler Ocean | "verify basemap key" | **Neither.** The tree uses keyless CARTO **Positron** (light parchment theme) + OpenSeaMap; add self-hosted PMTiles for offline (§6.3) | |
| 13 | Early exit | Real cancellation, dotted edges | Delete the stub | **Both**: delete the stub, build the real one (P2.12) | |
| 14 | Sentinel alerts in Tamil | Every alert in the user's language | P3.6: the 4 verified languages; keep the raise for others | **DLC rule, orca_final scope**: all 8 core languages once P3.8 verifies them | |
| 15 | PFZ coverage | "353 nodes, all 14 sectors" | P0.6: 591 features, 11 sectors live; 407 / 13 national | **Tree.** Never print a fixed count; render the measured one | The count changes with every scrape |
| 16 | Source count | 47 | Freshness contract: 27 registry ids | **Tree: 27** (`discovery.py`, 27 `DataSource` entries) | |
| 17 | Gazetteer | "~150 entries" | "~120" | **Tree: ~121**. Say "about 120" until native-script keys land | |

---

## 5. orca_final claims the tree contradicts today

This is P0.14's checklist. Each item should either get built or get removed from orca_final.md before
it reaches a judge. (Per the team's decision this report doesn't edit orca_final. P0.14 is the point
that does.)

1. `ORCA_LLM_ENABLED` exists (§5.5, §28, §29.3) — **no**; P2.11 builds it.
2. Eight CI guards (§27.3) — **three**; P0.12.
3. 47 catalogued sources (header, §3.2, PS-C4) — **27**.
4. Ten languages with ✅ voice (§14.1) — **4 verified**; target 8.
5. Bhashini as the institutional backend (§14.3, §14.4) — **prepared seam**.
6. Species tags and the Tuna layer (§9.1a) — **no data**.
7. Solunar (§9.1b) — **not built; drop**.
8. Corroboration (§12.7) — **not built; roadmap**.
9. Twelve delivery channels (§12.1) — **four renderers, three dispatchers**.
10. Phone OTP (§15.1) — **no**.
11. Per-user and per-IP rate limits (§25) — **no**.
12. `/demo` route (§19, §29.2) — **no**; P6.6.
13. driver.js tour (§29.1) — **not installed**.
14. Workbox service worker (§21, §31) — **no service worker at all**.
15. CARTO Dark Matter + MapTiler Ocean (§20.1) — **CARTO Positron + OpenSeaMap**.
16. Suite result "372 passed" (§27.1) — **423 test functions now**; re-run and quote the real number.
17. Five watch geometries (§11.2) — **condition-type enum only**.
18. MRCC routing "nationwide" (§13.2) — **nearest station found; phone numbers null**.
19. `faster-whisper large-v3` with GPU (§14.4) — **`small` on CPU** (P0.3).

---

## 6. Stack and approach — what should change

Like the MapLibre switch: places where the current choice will hurt later, and what to move to.
Each is a recommendation, with the reason and the cost of switching. **Verify every licence on the
model card before swapping. The licence facts below are as published at the time of writing.**

> **Superseded 2026-09-19 — §6.1, §6.2 and §6.9 below.** The team has Bhashini access (ASR, NMT,
> TTS, TLD, ALD, ITN, Punctuation, VAD, Denoiser, NER, TN, Transliteration). Bhashini is now the
> primary speech and language path and the GPU carries no voice model; local faster-whisper `small`
> and IndicTrans2 run on CPU only as the offline rung, and alert audio is pre-rendered through
> Bhashini TTS. Parler-TTS and IndicConformer are dropped. See plan P0.3 and P3.8. The sections are
> kept for the record.

### 6.1 Speech-to-text — keep faster-whisper for English, add an Indic-native ASR

- **Now:** `faster-whisper small`, CPU, int8.
- **Problem:** Whisper's accuracy on Tamil, Telugu, Kannada, Malayalam, Bengali and Marathi is
  noticeably worse than on English, even at `large-v3`, and the voice-first fisherman flow depends on
  exactly those languages. P0.3 fixes speed, not Indic accuracy.
- **Recommend:** run `large-v3` (or `large-v3-turbo`, faster at similar quality) on the GPU for
  English and for **spoken-language ID**, then route Indic audio to **AI4Bharat IndicConformer**
  (multilingual, trained on Indian speech, runs locally). Put it behind the existing `AsrRung` so
  it's another rung, not a rewrite (`voice.py:60`).
- **Cost:** 1–1.5 days including an A/B on 20 recorded clips per language. The A/B is the Done-when.

### 6.2 Text-to-speech — replace MMS-TTS

- **Now:** `facebook/mms-tts-<lang>`, VITS, CC-BY-NC 4.0 (non-commercial).
- **Problem:** the licence conflicts with P6.2's institutional buyer story, and MMS voices are
  intelligible but robotic.
- **Recommend:** **AI4Bharat Indic Parler-TTS** (published Apache-2.0, covers all 8 core languages).
  It's bigger (about 0.9B parameters), so **pre-render the fixed alert vocabulary** (severity tokens,
  band phrases, "do not proceed") at startup through the existing `POST /voice/prefetch`, and
  synthesize only free text live. That also makes the offline border demo's Tamil voice deterministic.
- **Cost:** 1 day. The fallback rung to MMS can stay for non-commercial demos.

### 6.3 Basemap — add a self-hosted offline basemap

- **Now:** CARTO Positron style, fetched live. No service worker.
- **Problem:** orca_final §7.2 beat 7 and §21 promise the map works with the network pulled. A
  hosted style can't do that, and bulk-caching a third-party tile service for offline use generally
  isn't allowed by its terms.
- **Recommend:** a **Protomaps PMTiles** extract of India's coast (one static file served locally),
  using the `pmtiles` protocol for MapLibre. `basemap.ts` already anticipates this swap through the
  `NEXT_PUBLIC_BASEMAP_STYLE` env var. Keep CARTO as the online default if the team prefers its look.
- **Cost:** half a day. → **P7.4**.

### 6.4 Tides — add a global tide model behind the SoI tables

- **Now:** scraped Survey of India tables, 5 stations, an 8-day window that expires 2026-09-23.
- **Problem:** orca_final promises "all Indian tidal ports". Scraping can't deliver that, and the
  window has to be refreshed forever.
- **Recommend:** **pyTMD + FES2022** (or TPXO) as the rung after SoI. It predicts anywhere on the
  coast, for any date, offline, and never expires. SoI stays primary where it exists. The
  chart-datum-vs-MSL warning orca_final §9.3 already describes is exactly the caveat this rung needs
  (model heights are relative to MSL).
- **Cost:** 1 day, plus a one-time model-file download (FES2022 needs a free AVISO registration). →
  **P5.14**.

### 6.5 LLM — Gemini, with a budget

- **Now:** `google-genai` provider (`llm/registry.py:90`), tier env vars empty in `.env.example`.
- **Problem:** free-tier requests-per-minute limits are low. After P2.5 (Critic on every query),
  each query is at least reporting + critic, plus the classifier on Tier-3 fallback, plus ocean
  analytics at DEEP. Five quick demo queries can hit a 429 mid-video.
- **Recommend:** a Flash-Lite-class model for the cheap tier and a Flash-class model for mid and
  reasoning. Treat a 429 as "provider unavailable", which falls to the deterministic template the
  LLM-off switch already needs (P2.11), labelled as such. Cache by the existing query cache, and cap
  the Critic at one pass (the DLC's rule). → **P2.13**.
- A local open-weight model (Ollama) isn't recommended on this laptop: 6 GB is already spoken for (§6.9).

### 6.6 Route search — library least-cost path vs hand-written A*

- **Now:** geodesic track plus fixed offset candidates (`voyage.py:285`).
- **Recommend:** P5.7 as written, with one choice to make. `skimage.graph.MCP_Geometric` gives a
  least-cost path over a cost raster in a few lines (one new dependency, scikit-image), but its cost
  is **static**. The time-aware "wave height at ETA" cost orca_final §8.2 calls load-bearing needs the
  hand-written A* the DLC describes (~150 lines), where the edge cost is looked up at the arrival
  hour. **Recommend the hand-written A***, because time-awareness is the part orca_final sells.

### 6.7 Refresh scheduling — Task Scheduler, not CI

- **Now:** eleven manual scripts, no schedule.
- **Recommend:** P5.12's `refresh_all.py` as written, triggered by **Windows Task Scheduler** on the
  demo laptop (the team's decision to run locally makes this the right place). Not CI: `data/` is
  gitignored, so a CI refresh can't persist, as the log already notes. No new dependency.

### 6.8 Satellite ocean colour and SST — use the official toolbox for Copernicus

- **Now:** Copernicus chlorophyll NRT file holds 2023 data, and SSH ends 2025-04.
- **Recommend:** refresh through the `copernicusmarine` CLI (free account) inside `refresh_all.py`,
  subset to the India bbox. MOSDAC parsing (P5.1) stays primary.

### 6.9 GPU budget on the RTX 3050 (6 GB) — plan it, don't discover it on stage

| Model | Precision | Approx. VRAM |
|---|---|---|
| faster-whisper large-v3 | int8_float16 | ~3 GB |
| IndicTrans2 indic-en + en-indic dist-200M | fp16 | ~1 GB |
| IndicConformer (if §6.1 adopted) | fp16 | ~1.2 GB |
| Indic Parler-TTS (if §6.2 adopted) | fp16 | ~2 GB |
| Browser (MapLibre + deck.gl WebGL) | — | 0.5–1 GB |

That's more than 6 GB if everything is resident. **Recommend:** keep Whisper and IndicTrans2 on the GPU
(the pre-warm in P6.4), run TTS on the CPU for free text and serve alert audio from the pre-rendered
cache, and load IndicConformer only when the language ID isn't English. Record the measured
`nvidia-smi` peak in the P6.4 log entry.

### 6.10 Things that should **not** change

MapLibre (already the right call) · IndicTrans2 distilled 200M · FastAPI + LangGraph · PostGIS ·
Redis with its in-process fallback (`session.py:52`) · Recharts · `@xyflow/react` + dagre · the
deterministic safety core · no state library. None of these is causing a problem, and swapping any
of them is cost with no finale benefit.

---

## 7. Bugs found in passing

1. **Vessel-class vocabulary mismatch.** See §1 #2. → P0.13.
2. **No safety-path guard, and CI doesn't run `verify_ci_guards.py`.** See §1 #1. → P0.12.
3. **The IMBL distance that drives the verdict ignores five of the six foreign boundaries on
   disk.** A position off Sir Creek gets an EEZ-proxy distance to Sri Lanka, not to Pakistan. →
   P5.5 (rewritten).

---

## 8. The `/alerts` page — proposed design (new points P4.11–P4.13)

`/safety` is gone, and a fisherman still needs one place that answers *"what is ORCA warning me
about right now, and what did it send me?"*. Most of the backend already exists: `GET
/api/notifications`, `GET /api/notifications/stream` (SSE), `unread_count`, `read` / `read_all`,
`GET /api/watches/{id}/history`.

- **P4.11 — Alert inbox.** Active alerts first, ranked by severity token, then history. Each row
  shows the text severity token + icon, the triggering value against its threshold, the source and
  acquisition time, the confidence tier, and a link to the trace for its `query_id` (orca_final
  §11.4). It streams live from the existing SSE route.
- **P4.12 — Critical alert takeover.** The ≤1 nm boundary band and cyclone Red take the full
  screen, repeat voice until acknowledged, show the reciprocal heading, and keep SOS visible
  (orca_final §6.3, §7.2 beat 5). It's rendered by a shared component, so it fires on any route, not
  only on `/alerts`.
- **P4.13 — What was sent.** Per alert, the verbatim rendered payload for every channel the user
  has (SMS, IVR script, WhatsApp, push) with delivery status. Simulated channels show `SIMULATED`,
  never `DELIVERED` (orca_final §12.2's "shown verbatim").

Nav: `/alerts` replaces `/safety` in `NAV_ROUTES` for every persona. The bell in the status bar links
to it.

---

## 9. What changed in this commit

- `docs/DLC_verification_report.md` — this file.
- `docs/DLC_implementation_plan.md` — 14 stale points rewritten; new points P0.12–P0.14, P2.12–P2.13,
  P3.8–P3.10, P4.11–P4.13, P5.14–P5.17, P6.6–P6.10, P7.3–P7.4; §11 coverage and the non-build
  decisions extended; §13 added (orca_final reconciliation); counts corrected.
- `docs/DLC_implementation_log.md` — one `NOTE` entry recording the audit, and status-table rows for
  the new points.
- **Not changed:** `docs/orca_final.md` (team decision; P0.14 owns that),
  `docs/ORCA_DLC_Extension_Pack.md`. **Note:** the plan's §2 rule says a stale `Now:` line
  should be fixed in the Extension Pack in the same change. The 14 corrections in §2 above haven't
  been made there yet, and are listed in the log entry so whoever does it has the list.
