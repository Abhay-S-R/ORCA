# 🏛️ ORCA — Unified Agentic Architecture (v4.0)

> **Status:** LIVING DOCUMENT — the whole team routes decisions through this file.
> **Lineage:** Merges `ORCA_Agentic_Architecture_v3.md` (the persona-blind-routing lineage, adopted as base) with targeted backfill from `ORCA_Agentic_Architecture.md` v0.1 (the 7-agent alternate-lineage document — mined for tool-level detail, tech stack, critic loop, visualization spec, and phased plan, all absent or thin in v3). Cross-checked against `ORCA_Master_Analysis_and_Requirements.md` for full use-case and NFR coverage.
> **Problem Statement:** SIH26176 (ISRO / Department of Space) · **Track:** Software · **Theme:** Disaster Management
> **Pilot region:** South Tamil Nadu — Thoothukudi, Rameswaram, Kanyakumari, Palk Bay, Gulf of Mannar
> **Target stack:** LangGraph + FastAPI (Python 3.11) + Next.js/Leaflet — see §10 for the full committed stack

---

## 0. Why v4, and what changed structurally

v3.0 fixed the single most important bug in the earlier lineage (persona was gating the execution graph itself — a researcher misclassified as a fisherman would silently get truncated analysis, not just a different display). That fix — **intent decides what fires, persona decides how it's said** — is kept as the load-bearing principle of this document and is not renegotiable.

What v3.0 was thin on, and what this revision adds:

| Gap in v3.0 | Fix in v4.0 |
|---|---|
| No quality-validation loop for deep/complex reasoning | **Critic Agent** reinstated (§3, Tier 2), but retargeted from "researcher-only" to "triggers on `reasoning_depth == DEEP`, regardless of persona" — a diagnostic query from a fisherman that gets escalated to DEEP depth deserves the same fact-checking a researcher's query does |
| No committed tech stack beyond a one-line mention | §10 commits to specific tools per layer, with fallback options and cost/latency notes |
| Traces were bullet-point summaries, not tool-call-level | §8 gives full tool-call-level worked traces for 9 representative queries |
| No itemized visualization/chart spec | §11 itemizes map layer types and chart types per intent |
| No phased build schedule | §15 gives a week-by-week plan with owners-TBD placeholders |
| Proactive/push alerting was implied (Sagar Vani reference) but never architected as a real flow | **Sentinel Agent** (new, Tier 2, §3) — decoupled background monitor that makes push alerts a real capability, not a footnote |
| DAT-SG/Sagarmitra distress handoff was named as "the natural integration point" in the master doc but **never appears in either architecture document as an actual flow** | **Distress & Emergency Handoff Agent** (new, Tier 2, §3) — closes this gap |
| No systematic audit of the master doc's use cases against the architecture | §7 — full use-case coverage audit, one row per sample query / scenario, gap called out explicitly where v3-as-written doesn't handle it |
| No optimization pass beyond correctness | §9 — 19 concrete optimizations across latency, cost, reliability, and scale, none of which were in either source document |

**One framing decision worth stating up front:** v3's "9 agents, 1:1 mapped to the PS's named roles" was explicitly a *judge-legibility* choice, not an engineering ceiling. The three additions in this revision (Critic, Sentinel, Distress-Handoff) are **Tier 2 — Support Agents**. They sit outside the PS's literal 9-role list, the same way v3 kept persona resolution and language handling inside "Agent 1" rather than inventing new top-level roles. When you demo, the headline is still "9 core agents, mapped to what ISRO asked for" — the support agents are the infrastructure that makes those 9 trustworthy, not a rebuttal of the framing.

---

## 1. Core Design Principles (v4)

1. **Nine agents, mapped 1:1 onto ISRO's own named roles.** Strategic constraint, kept from v3.
2. **Intent decides *what fires*. Persona decides *how it's said*.** Kept from v3 — this is the fix for the v1.0 persona-gate bug and is the single most important sentence in this document.
3. **Zero LLM hallucination on safety.** Go/no-go decisions, geofence breaches, and hazard tiers are computed with deterministic Python math, never generated as free text.
4. **Every claim is provenance-stamped.** Source dataset, acquisition timestamp, and a 3-tier confidence rating travel with every fact.
5. **Persona is resolved explicitly wherever possible; inference is a fallback, never a gate.**
6. **Uncertainty defaults to the safety-conservative rendering, never to a guess.** Low-confidence persona inference, LOW-DATA safety confidence, ambiguous intent — all degrade toward "ask/clarify" or "show the cautious version," never toward silently picking one interpretation.
7. **Quality validation scales with reasoning depth, not with persona.** *(NEW v4.0)* Any query that gets escalated to `DEEP` reasoning — regardless of who asked — passes through the Critic Agent before it reaches the user. Depth-gating quality control by persona (as both prior documents effectively did) means a fisherman's diagnostic "why" query, which the routing table already forces to STANDARD+ depth, gets zero fact-checking on a causal claim. That's backwards: the fisherman is the user least equipped to catch a bad inference himself.
8. **Safety-critical monitoring does not wait for a query.** *(NEW v4.0)* The architecture must support push, not just pull. A fisherman who never opens the app before a cyclone should still get an SMS. This requires a process that runs independent of the request/response graph — see Sentinel Agent, §3.
9. **Every emergency signal has exactly one owner and it is never the LLM.** *(NEW v4.0)* Distress detection and Coast Guard handoff is deterministic pattern-matching + human/agency escalation, mirroring principle 3's treatment of safety math — see Distress & Emergency Handoff Agent, §3.
10. **Cost and latency optimizations must never trade against principles 3, 6, or 8.** *(NEW v4.0)* Every optimization in §9 is checked against this before being accepted — see the "Safety impact" column in that section.

---

## 2. The Persona System

*(Unchanged from v3.0 unless flagged — this system was already correct; the fix in v3 was routing, not persona modeling itself.)*

### 2.1 Taxonomy

| Persona code | Covers (from PS text) | Primary mode |
|---|---|---|
| `fisherman` | Fishermen | Fast, low-literacy, voice-first safety & PFZ answers |
| `commercial_navigator` | Maritime operators | Route optimization, fuel/ETA, hard geofence constraints |
| `researcher` | Researchers | Multi-year trends, raw data, citable methodology |
| `coastal_authority` | Coastal authorities + disaster management agencies | District rollups, CAP-format alerts, escalation |

### 2.2 Intent vs. persona split

Planning Agent routes by intent, persona-blind (§4). Reporting Agent renders by persona, at the last stage. Persona sets a *default* for optional depth — never a ceiling.

### 2.3 `reasoning_depth`

`SHALLOW | STANDARD | DEEP` — persona supplies a default, query complexity can only push it up:

| Persona | Default depth |
|---|---|
| `fisherman` | SHALLOW |
| `commercial_navigator` | STANDARD |
| `researcher` | DEEP |
| `coastal_authority` | STANDARD |

Root-cause/diagnostic queries force at least STANDARD in data-gathering regardless of persona default. **(v4 addition, §1 principle 7):** any query pushed to `DEEP` — regardless of starting persona — routes through the Critic Agent before Reporting.

### 2.4 Resolution mechanism

1. **Explicit** (preferred): UI persona selector at session start, or registered account role. `stakeholder_persona_source: "explicit"`.
2. **Inferred**: zero-shot classification on phrasing/vocabulary, run only when no explicit signal exists. Returns `stakeholder_persona_confidence: float [0,1]`.
   - **≥ 0.70** → treat as resolved. `stakeholder_persona_source: "inferred_high"`.
   - **< 0.70** → do **not** guess a specific persona. `stakeholder_persona: "unresolved"`, `stakeholder_persona_source: "inferred_low"`. Reporting renders the **most conservative composite**: fisherman-style banner (GO/CAUTION/NO_GO, plain language) plus a "Show technical detail" expand affordance. This never blocks the underlying computation — Risk Assessment and intent-routed agents still ran at full depth per §4; only the *default rendering choice* is conservative.
   - Threshold (0.70) is a placeholder — see §9.16 for the proposed validation methodology (new in v4).

### 2.5 Persona correction affordance

Every rendered response carries a visible, one-tap "This isn't quite right for me / I'm a [other persona]" control (`persona_correction_available: true`). Selecting it re-renders the *same already-computed* facts under the new persona (no re-query — the direct payoff of the intent/persona split), sets `stakeholder_persona_source: "explicit"`, persists for the session, and logs as a training signal for threshold tuning.

### 2.6 Output rendering matrix

| Persona | Output structure |
|---|---|
| 🐟 `fisherman` | SAFE/DO NOT GO banner, plain distance/direction, regional-language audio, single map pin |
| 🚢 `commercial_navigator` | Waypoint table w/ lat-long + ETA, bathymetry profile, tidal berthing windows, route polyline |
| 🔬 `researcher` | Statistical summary (mean, Δ, R²), full sensor metadata, time-series chart spec, CSV/NetCDF export |
| 🚨 `coastal_authority` | District threat matrix, CAP-format alert payload, SMS/IVR broadcast template, evacuation buffers |
| *(any)* on `confidence.score == "LOW-DATA"` | Banner/verdict still renders, but with a distinct amber "Data limited — verify locally before deciding" treatment instead of a confident color. Applies identically across all four personas — the fact confidence was low is never hidden from any persona, including fisherman. |
| *(any)* on active `DISTRESS` flag *(NEW v4)* | All persona formatting is bypassed. See Agent 12, §3.4. |

---

## 3. The Agents

### 3.1 Tier 1 — Core Agents (PS-mapped, 9 total)

These are unchanged in responsibility from v3.0. What v4 adds per agent: concrete tool tables (backfilled from the alternate-lineage doc's level of detail, since v3 only listed data sources, not callable tools), and explicit optimization hooks referenced from §9.

#### Agent 1 — User Interaction (Ingress & Egress)
**Role:** Linguistic bridge, session/context manager, persona resolver.

- Detects input language (Tamil, Telugu, Malayalam, Kannada, Bengali, Odia, Marathi, Gujarati, Hindi, English).
- **Speech-to-text (ingress voice path):**

  | Source | Tier | Verified? |
  |---|---|---|
  | Bhashini/ULCA ASR API | 🟢 T1 | Same govt-run endpoint family as the translation API (✅ verified real) — confirm the ASR sub-endpoint specifically |
  | Whisper (local, small/medium) | 🟣 internal | Offline/rate-limit fallback — verify Indic-language WER before relying on it as primary fallback (see §9.15 quantization note) |

- Resolves `stakeholder_persona` + `stakeholder_persona_source` + `stakeholder_persona_confidence` (§2.4).
- Normalizes vernacular coastal terms.
- Reads `session_history` to detect follow-up/elliptical queries and resolves them against the prior turn's `target_bbox`/`target_time_window` before handing off to Planning.
- Egress: back-translates + renders per persona (§2.6); generates TTS for voice channel; attaches `persona_correction_available` control.
- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `detect_language` | raw text/audio | ISO 639-1 code + confidence | fastText / Bhashini LangID |
  | `speech_to_text` | audio blob, lang hint | transcript + confidence | Bhashini ASR → Whisper fallback |
  | `translate_to_english` | text, source_lang | English text | IndicTrans2 / Bhashini NMT |
  | `translate_from_english` | text, target_lang | Localized text | IndicTrans2 / Bhashini NMT |
  | `resolve_persona` | query text, channel, session profile | persona + source + confidence | Rule cascade + zero-shot classifier |
  | `resolve_coreference` | current query, session_history | enriched query with resolved bbox/time | Rule-based slot-fill against last turn |
  | `text_to_speech` | text, target_lang | audio blob | Bhashini TTS / Google Cloud TTS fallback |
  | `format_for_channel` | payload, channel | Channel-appropriate payload (160-char SMS, IVR script, chat card) | Template engine |

#### Agent 2 — Planning (Orchestrator)
**Role:** Intent classifier + persona-blind router.

- Inspects `(normalized_query, session_history)` — **not persona** — to decide which specialist agents fire.
- Sets `reasoning_depth` default from persona, allows query complexity to push it up.
- **Multi-match resolution:** when `normalized_query` matches more than one intent row, activates the **union** of both rows' agents, not just the first match. Logged in the trace.
- **No-match fallback:** if no row matches above a minimum confidence, activates a minimal default path (Discovery + Weather + Ocean Analytics) and has Reporting explicitly state it answered the closest general-conditions interpretation, with an offer to narrow the query. Never silently drops the query.
- Full routing table in §4.
- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `classify_intent` | normalized_query | list of `(intent_row, confidence)` | Rule-based table match + embedding-similarity fallback (§9.5) |
  | `generate_execution_plan` | matched intent rows, reasoning_depth | ordered/parallel agent dispatch plan | Deterministic composition over §4 table |
  | `check_early_exit` | partial agent_results | bool: can remaining agents be skipped? | Cost-based short-circuit logic (§9.3) |

#### Agent 3 — Marine Data Discovery
**Role:** Catalog selector + retriever. Home of the PS's "tool selection" capability.

| Source | Tier | Verified? |
|---|---|---|
| INCOIS ERDDAP (`erddap.incois.gov.in`) | 🟢 T1 | Plausible/standard ERDDAP pattern — test the literal endpoint before Phase 0 is "done" |
| MOSDAC Open Data catalog | 🟢 T1 *or* 🟠 T3 | ⚠️ Unresolved — Phase 0 blocker, see §12.1 |
| Copernicus Marine (CMEMS) | 🔵 T2 | ✅ Real, instant free registration |
| NASA Ocean Color / OB.DAAC | 🔵 T2 | ✅ Real, instant via Earthdata Login |
| Local pre-cached snapshot | 🟣 internal | Air-gapped demo reliability |

- Give MDD an explicit, narratable choice logic — prefer Copernicus reanalysis over MOSDAC NRT for a researcher-depth historical query; prefer MOSDAC NRT for freshness on a same-day fisherman query. Surfaced as its own visible trace step.
- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `fetch_erddap_dataset` | dataset_id, bbox, time range | Normalized JSON/DataFrame | INCOIS ERDDAP |
  | `fetch_pfz_advisory` | sector_id, date | PFZ coordinates + validity | INCOIS WebGIS scraper |
  | `fetch_mosdac_product` | product_type, region, date | Raster reference | MOSDAC portal |
  | `fetch_copernicus_sst` | bbox, time range | SST grid | CMEMS API |
  | `fetch_catch_statistics` | state, district, year range | Catch time-series | data.gov.in |
  | `check_data_freshness` | source_id | Last update timestamp + staleness tier | Internal cache metadata |
  | `select_best_source` | parameter_type, persona_depth_hint | Ranked source list + chosen source + reason | Priority-cascade logic (narratable) |

#### Agent 4 — Weather Intelligence
**Role:** Waves, wind, lightning, cyclone tracks.

| Source | Tier | Verified? |
|---|---|---|
| Open-Meteo Marine API | 🟢 T1 | ✅ `https://marine-api.open-meteo.com/v1/marine`. Global model, 6h updates; resolution inside Palk Bay may be coarser than open coast |
| IMD CAP bulletins / cyclone tracks | 🟢 T1 | ✅ Real — SACHET is IMD's CAP integration point |
| IMD Damini lightning nowcast | 🟢 T1 | Real service; verify current endpoint before coding against it |

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `get_marine_weather` | lat, lon, hours_ahead | Hourly forecast array (Hs, wind, swell, currents) | Open-Meteo Marine API |
  | `get_cyclone_status` | basin (BoB/AS) | Active cyclone tracks, intensity, landfall forecast | IMD CAP + MOSDAC |
  | `get_lightning_nowcast` | lat, lon, radius_km | Lightning strike proximity, 30-min forecast | IMD Damini |
  | `get_incois_hazard_alerts` | region | Active warnings (tsunami, storm surge, high wave) | INCOIS portal |
  | `resolve_temporal_expression` | text ("tomorrow morning") | ISO datetime range | Rule-based parser |

#### Agent 5 — Ocean Analytics
**Role:** SST/chlorophyll correlation, PFZ interpretation, tide prediction, root-cause/trend diagnostics.

| Source | Tier | Verified? |
|---|---|---|
| INCOIS PFZ Advisory | 🟢/🟠 | ✅ Real, updated **daily** as of 2025–2026 |
| Survey of India tide tables + Stormglass.io fallback | 🟢/🔵 | Plausible, standard pattern |
| data.gov.in fisheries catch stats | 🟢 T1 | Plausible, standard open-data portal |
| ICAR-CMFRI archives | 🟠 T3 | Real institution; 44.9% mid-shelf-persistence Thoothukudi stat independently confirmed |

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `analyze_pfz_proximity` | user_lat, user_lon, date | Nearest PFZ coordinates, distance, bearing | INCOIS PFZ (via MDD) |
  | `get_sst_snapshot` | bbox, date | SST grid + anomaly vs. climatology | ERDDAP / Copernicus |
  | `get_chlorophyll_snapshot` | bbox, date | Chl-a concentration grid | ERDDAP / NASA OB.DAAC |
  | `get_tide_prediction` | station_id or nearest_to(lat,lon), date | High/low tide times + heights | Survey of India / Stormglass |
  | `compute_sst_chl_trend` | bbox, date_range | Time-series + trend line + anomaly flags | Computed |
  | `diagnose_productivity_decline` | region, date_range | Multi-factor analysis report | Computed (SST + Chl + catch stats) |
  | `score_pfz_persistence` | sector_id, lookback_weeks | Persistence score (0-1) across recent advisories | Computed from advisory history |

#### Agent 6 — Geospatial Reasoning
**Role:** Boundary geometry, bathymetry, route optimization.

| Source | Tier | Verified? |
|---|---|---|
| Marine Regions (VLIZ) EEZ/IMBL | 🟢 T1 | Standard, credible |
| Protected Planet / WDPA (Gulf of Mannar MPA) | 🟢 T1 | Standard, credible |
| GEBCO bathymetry grid | 🟢 T1 | Standard, credible |

**Why geometry is never LLM-generated:** an LLM approximating "you're probably about 15 km from the boundary" when the real answer is 3 km is a legal/safety catastrophe. All spatial computation uses GeoPandas/Shapely against authoritative geometries.

**Highest engineering-risk feature:** full A*/Dijkstra bathymetry-aware routing. Owner and date must be assigned in the team tracker. Fallback (build first): straight line from origin to destination, buffered away from geofence/shallow polygons.

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `check_boundary_proximity` | lat, lon, boundary_type | Distance (NM), nearest point, alert level | Marine Regions / WDPA shapefiles |
  | `compute_safe_route` | origin, destination, vessel_draft, constraints | Route GeoJSON + distance + hazard notes | GEBCO + boundary files + WIA overlay |
  | `spatial_query_zones` | query_type, params | Matching zone features (GeoJSON) | Indexed geospatial data |
  | `point_in_polygon` | lat, lon, polygon_set | Boolean + polygon metadata if inside | Shapely against indexed boundaries |
  | `generate_map_layers` | layer_specs[] | GeoJSON FeatureCollection per layer | Computed |
  | `precompute_geofence_grid` *(NEW, §9.13)* | boundary_set, resolution_m | Rasterized exclusion grid | Batch job, run offline |

#### Agent 7 — Risk Assessment (Deterministic Safeguard)
**Role:** Pure-math safety classifier. Always runs when intent requires it, regardless of persona.

```python
def evaluate_marine_safety(wave_height_m, wind_speed_kmh, lightning_active,
                            cyclone_alert, imbl_distance_nm, mpa_violation) -> dict:
    if cyclone_alert in ["Red", "Orange"] or wave_height_m >= 3.5 or wind_speed_kmh >= 55:
        return {"status": "DANGER", "go_no_go": "NO_GO", "reason": "Severe Weather / Cyclone Threshold Exceeded"}
    if lightning_active:
        return {"status": "DANGER", "go_no_go": "NO_GO", "reason": "Active Convective Lightning Strike Zone"}
    if imbl_distance_nm <= 1.0 or mpa_violation:
        return {"status": "CRITICAL_GEOFENCE", "go_no_go": "NO_GO", "reason": "Imminent Boundary or MPA Breach"}
    if 2.0 <= wave_height_m < 3.5 or 35 <= wind_speed_kmh < 55 or imbl_distance_nm <= 3.0:
        return {"status": "WARNING", "go_no_go": "CAUTION", "reason": "Rough Sea State / Boundary Proximity"}
    return {"status": "SAFE", "go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits"}
```

**Vessel-class adjustment** *(backfilled from alternate-lineage doc — v3 didn't specify this despite `commercial_navigator`'s `vessel_class` field existing conceptually)*:

```
VESSEL CLASS THRESHOLD DELTAS (applied before evaluate_marine_safety)
════════════════════════════════════════════════════════════════════
  small_fishing:      base thresholds above (most conservative — default)
  mechanized_trawler:  wind +5 kt on each band, Hs +0.5 m on each band
  cargo_vessel:        wind +15 kt on each band, Hs +1.5 m on each band
════════════════════════════════════════════════════════════════════
```

Confidence tiers: **HIGH** (official govt source + <6h old + full coverage) / **MEDIUM** (global model fallback + <24h) / **LOW-DATA** (incomplete coverage / cloud occlusion / extrapolated). LOW-DATA triggers the amber rendering treatment for every persona.

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `evaluate_marine_safety` | weather + geofence + hazard inputs, vessel_class | SafetyVerdict + reason | Deterministic rules (above) |
  | `check_active_hazards` | lat, lon, radius_km | List of active hazard alerts with severity | INCOIS + IMD feeds (via WIA) |
  | `compute_confidence` | data_sources_used[] | Confidence tier + explanation | Freshness + coverage rules |
  | `generate_alert_payload` | hazard_type, severity, location, language | Formatted alert (text + Sagar Vani SMS template) | Template engine |

#### Agent 8 — Visualization
**Role:** GeoJSON FeatureCollections for Leaflet/Mapbox GL, heatmap coordinate arrays, chart specs. Content is intent-driven, complexity is persona-driven. Full itemized spec in §11 (backfilled — v3 only had one sentence here).

#### Agent 9 — Reporting (Synthesis & Citation)
**Role:** The persona-rendering stage. Compiles specialist outputs into a persona-tailored narrative, attaches source/timestamp/confidence to every claim, formats multi-channel payloads (web, mobile card, CAP XML, SMS), applies the LOW-DATA treatment and the persona-correction control. `reasoning_depth` and `stakeholder_persona` are applied only here — everything upstream is persona-blind. **(v4)** Also the exit point for the Critic loop when `reasoning_depth == DEEP` (§3.2).

### 3.2 Tier 2 — Support Agents (new in v4.0)

These don't count against the "9 core agents" judge-facing framing (§0) — they're quality/safety/proactivity infrastructure, the same category v3 already put Language handling and Persona resolution into inside Agent 1.

#### Agent 10 — Critic / Quality Validation
**Role:** Fact-checks a synthesized response before it reaches the user. Backfilled from the alternate-lineage document's §8, but **retargeted**: triggers on `reasoning_depth == DEEP` for *any* persona, not on `persona == researcher`. This is a direct consequence of Principle 7 (§1) — the intent/persona split means a fisherman's diagnostic query can legitimately reach DEEP depth, and if it does, it deserves the same scrutiny a researcher's query gets. Gating the critic by persona (as both source documents effectively did) reintroduces a smaller version of the exact bug v3 fixed for routing — this time for quality control instead of data-fetching.

**What it validates:**

```
VALIDATION RUBRIC
  1. FACTUAL CONSISTENCY — do cited values match what the data sources actually returned?
     Are units correct and consistent (m vs km, knots vs m/s)?
  2. TEMPORAL COHERENCE — are comparisons made across matching time windows?
     Is the "data as of" timestamp accurate?
  3. CAUSAL CLAIM STRENGTH — if the response says "X caused Y," does the evidence support
     causation or merely correlation? Are alternative explanations acknowledged?
  4. CITATION COMPLETENESS — is every quantitative claim backed by a source? Is source
     metadata sufficient (sensor, resolution, algorithm version)?
  5. SPATIAL ACCURACY — do coordinates and region names match? Are distance calculations
     plausible given the geography?
```

**Loop:**

```python
MAX_ITERATIONS = 3

for i in range(MAX_ITERATIONS):
    response = reporting_agent.generate(agent_results, persona, reasoning_depth)
    if reasoning_depth != "DEEP":
        return response   # critic only engages at DEEP depth (v4 rule)
    critique = critic.evaluate(response, validation_rubric)
    if critique.pass_:
        return response
    for issue in critique.issues:
        agent_results[issue.source_agent] = re_invoke(issue.source_agent, issue.correction_hint)

return response + disclaimer("Some claims could not be fully validated. See flagged items.")
```

**Latency consequence, made explicit:** engaging the critic adds ~5-15s. This is acceptable for a researcher's exploratory query (tolerates minutes) and for a coastal_authority's 48-hour district brief (not time-critical to the second), but it must **never** sit in the critical path of a `SAFETY_CHECK` intent even if that query happens to hit DEEP depth (e.g., a diagnostic "why is it dangerous right now" query). Rule: if `matched_intent_rows` includes `SAFETY_CHECK`, Reporting emits the RAA-backed verdict **immediately**, uncritiqued (RAA is already deterministic — nothing for the critic to add there), and the critic only reviews the *explanatory* text that accompanies it, asynchronously, upgrading the response in-place if it flags something. The user is never blocked on the critic for a go/no-go decision.

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `evaluate_response` | draft response, source agent_results, rubric | List of issues (or pass) | LLM-as-judge against structured rubric |
  | `request_correction` | issue, source_agent | Re-invocation instruction | Deterministic mapping issue→agent |

#### Agent 11 — Sentinel / Proactive Monitoring
**Role:** A background process, decoupled from the request/response graph, that turns Sagar Vani-style **push** alerting from a footnote into an actual architectural component. Neither source document specifies *how* a fisherman who never opens the app gets warned before a cyclone — this agent is that mechanism.

```
LOOP (runs continuously, independent of user queries):
  1. For every registered home port / vessel-current-position on file:
       fetch latest WIA + RAA outputs for that location (reuses the same
       tool interfaces as the on-demand graph — no duplicate logic)
  2. Compare new verdict against last-broadcast verdict for that location
  3. IF verdict crossed a severity threshold (GO→CAUTION, CAUTION→NO_GO,
     or any new active hazard/geofence alert):
       generate_alert_payload() (Agent 7's tool) → dispatch via Sagar-Vani-
       compatible channel (SMS/IVR/push) for every registered user at that
       location
       write the broadcast to session_history / audit_trace_log so a
       later on-demand query from the same user is consistent with what
       they were already told
  4. ELSE: no-op, no notification spam on unchanged conditions
```

**Why this is a separate agent and not "just run the graph on a cron":** running the full LangGraph pipeline per registered location on a schedule is wasteful — most locations don't change verdict between runs. Sentinel does the cheap check (steps 1-2) itself and only escalates to a full graph invocation when a threshold crossing is detected, reusing Agent 7's `generate_alert_payload` tool directly rather than re-deriving it. See §9.9 (request coalescing) and §9.17 (hazard-window scheduling) for how this scales during a cyclone spike without hammering upstream APIs.

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `list_monitored_locations` | — | All registered home ports / vessel positions due for a check | Internal registry |
  | `get_last_broadcast_verdict` | location_id | Last verdict sent + timestamp | Internal store |
  | `dispatch_alert` | payload, channel, recipient_list | Delivery status | Sagar-Vani-modeled dispatcher (SMS/IVR/push) |

#### Agent 12 — Distress & Emergency Handoff
**Role:** Closes a gap flagged in the master requirements doc (§6.5, §10) but never actually built out in either prior architecture: **ISRO's own DAT-SG/Sagarmitra distress-alert program is the natural handoff point for at-sea emergencies**, and this system sits adjacent to that mandate whether or not it says so explicitly. If ORCA is deployed and a user's message indicates an active emergency (not a hypothetical safety query), silently answering with a normal advisory card is a failure mode worth designing against.

**Detection, deterministically, not by LLM judgment call (mirrors Principle 3 and 9):**

```
TRIGGER CONDITIONS (any one is sufficient):
  • Explicit distress keywords/phrases in the user's own language, matched
    against a maintained multilingual pattern list (maritime distress
    terminology — "sinking," "man overboard," "taking on water," "engine
    failure adrift," equivalents in Tamil/Telugu/etc.) — pattern match,
    not semantic inference, to avoid both false negatives from paraphrase
    and false positives from casual language
  • A structured "SOS" control tap in the app/USSD/IVR interface
  • DAT-SG hardware signal, if/when integrated (out of scope for MVP,
    architected for)
```

**On trigger:**

```
1. Bypass the normal persona-rendering pipeline entirely — this is not a
   Reporting Agent job.
2. Surface the user's last known/reported position immediately (from
   session context, GPS if available, or ask ONE question: "Where are you?"
   if location is unknown — this is the one case where even the fisherman
   persona's "never ask, assume conservative default" rule is overridden,
   because assuming a default location in an actual emergency is worse
   than a 5-second delay).
3. Emit a structured handoff payload matching DAT-SG/Sagarmitra's intake
   format (or the closest CAP-compatible equivalent if direct integration
   isn't available for the hackathon build) — position, vessel ID if known,
   timestamp, distress type if determinable.
4. Simultaneously surface Coast Guard MRCC contact info directly to the
   user in their language and via voice, in case the automated handoff
   channel doesn't reach a human in time.
5. Log as a P0 audit event, distinct from normal query logging.
```

**Demo framing note:** present this exactly as ORCA's own boundary-crossing framing note in the master doc recommends — a technical safety/handoff capability, not a claim that ORCA replaces or automates Coast Guard response. It is a faster on-ramp to the existing distress-response chain, not a new one.

- **Tools:**

  | Tool | Input | Output | Source |
  |---|---|---|---|
  | `detect_distress_signal` | raw query text/audio, UI control state | Boolean + distress_type if matched | Multilingual pattern list, deterministic |
  | `emit_datsg_handoff` | position, vessel_id, distress_type, timestamp | Handoff payload (DAT-SG format or CAP fallback) | Structured template |
  | `surface_mrcc_contact` | user_location, language | MRCC contact details, localized | Static reference data |

---

## 4. Orchestration Logic — Intent Routing Table (v4, extended)

The Planning Agent consults this table on `normalized_query` (and `session_history` for follow-ups). No row references persona. Rows marked **NEW** were absent from v3's table but are needed to cover master-doc sample queries found missing in the audit (§7).

| Query pattern | Agents activated |
|---|---|
| "Where is the nearest PFZ" | Discovery, Ocean Analytics, Geospatial |
| "Is it safe to go to sea" | Discovery, Weather, Ocean Analytics, **Risk Assessment** (always) |
| "Tide / weather / sea conditions near me" | Discovery, Weather, Ocean Analytics |
| "Lightning / cyclone alerts" | Weather, **Risk Assessment** |
| "High chlorophyll + favourable SST regions" | Discovery, Ocean Analytics |
| "Safest route for a vessel" | Discovery, Weather, Ocean Analytics, **Geospatial**, Risk Assessment |
| "Why has productivity declined" (root-cause) | Discovery, **Ocean Analytics (diagnostic mode, forces STANDARD+ depth)**, Geospatial |
| "Zones to avoid / geofencing" | Geospatial, **Risk Assessment** |
| **"Export / download this data" *(NEW)*** | Discovery, [whichever of Weather/Ocean Analytics the referenced data belongs to], **Reporting (export-formatter mode)** |
| **"Notify me if conditions change" *(NEW)*** | Registers a Sentinel (Agent 11) watch on the resolved location — does not run the full graph synchronously; Reporting confirms subscription and states what threshold will trigger a notification |
| **"Boundary proximity — proactive / continuous" *(NEW)*** e.g. "am I approaching the MPA" | Geospatial, **Risk Assessment**; if channel supports it, also registers a short-lived Sentinel watch for the remainder of the session/voyage |
| **Distress / SOS trigger *(NEW — bypasses this table entirely)*** | Routes directly to **Agent 12**, skipping Planning's normal dispatch. See §3.2. |

### 4.1 Multi-match resolution

When `normalized_query` matches more than one row (e.g. "is it safe to take the route to X" matches both "is it safe" and "safest route"), the Planning Agent activates the **union** of both rows' agents, not just the first match. Cheap — specialists already run in parallel — and avoids silently dropping a sub-intent. Log which rows matched in the trace.

### 4.2 No-match fallback

If `normalized_query` matches no row above a minimum confidence, activate a minimal default path — Discovery + Weather + Ocean Analytics — and have Reporting explicitly state it answered the closest general-conditions interpretation, with an offer to narrow the query. Never silently drop the query or return an empty/error response.

### 4.3 Cost-based early exit *(NEW v4, see §9.3)*

If `SAFETY_CHECK` is among the matched intents and Weather + Geospatial alone are already sufficient to produce a `NO_GO` from Risk Assessment, Planning may cancel any still-pending non-safety-relevant agent calls (e.g., an Ocean Analytics chlorophyll lookup that only mattered for a co-occurring `LOCATION_QUERY` sub-intent) **unless** the user's query explicitly asked for that data too. Never cancel a call that the persona's default rendering or an explicit sub-intent depends on — this is a cost optimization for wasted computation, not a feature reduction.

### 4.4 Making "tool selection" demonstrable

Give the Marine Data Discovery Agent an explicit, narratable choice logic — e.g., prefer Copernicus reanalysis over MOSDAC NRT for a researcher-depth historical query; prefer MOSDAC NRT for freshness on a same-day fisherman query. Surface this as its own visible trace step, not just a failure-triggered fallback.

---

## 5. State Schema (`ORCAState`, v4)

```python
class ORCAState(TypedDict):
    session_id: str
    query_id: str
    raw_user_query: str
    normalized_english_query: str
    detected_language: str

    session_history: List[Dict[str, Any]]           # prior turns (query, resolved bbox/time,
                                                      # persona, verdict) for follow-up resolution

    stakeholder_persona: str          # "fisherman" | "commercial_navigator" | "researcher" |
                                       # "coastal_authority" | "unresolved"
    stakeholder_persona_source: str   # "explicit" | "inferred_high" | "inferred_low"
    stakeholder_persona_confidence: float   # 0.0-1.0, only set when source starts with "inferred"
    reasoning_depth: str              # "SHALLOW" | "STANDARD" | "DEEP"

    execution_plan: List[str]
    matched_intent_rows: List[str]    # which §4 rows matched (supports multi-match)
    early_exit_triggered: bool        # NEW v4 — did §4.3 cancel any pending calls?
    next_node: str
    completed_nodes: Annotated[List[str], operator.add]

    target_bbox: Dict[str, float]
    target_time_window: Dict[str, str]
    user_location: Optional[Dict[str, float]]
    vessel_class: Optional[str]       # NEW v4 — surfaced at state level, was only in
                                       # commercial_navigator profile YAML before; RAA needs
                                       # it directly (§3.1 Agent 7 vessel-class deltas)

    discovery_data: Dict[str, Any]
    weather_data: Dict[str, Any]
    ocean_data: Dict[str, Any]
    geospatial_data: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    visualization_payload: Dict[str, Any]

    critic_pass: Optional[bool]              # NEW v4 — only set when reasoning_depth == DEEP
    critic_iteration_count: int               # NEW v4

    distress_flag: bool                       # NEW v4 — set by Agent 12's detection, checked
                                               # before any other node executes
    sentinel_subscription: Optional[Dict]     # NEW v4 — set on ALERT_SUBSCRIPTION intent

    final_english_response: str
    final_vernacular_response: str
    evidence_citations: List[Dict[str, Any]]
    confidence_tier: str
    persona_correction_available: bool
    audit_trace_log: Annotated[List[Dict[str, Any]], operator.add]
```

---

## 6. Inter-Agent JSON Hand-off Contract

*(Unchanged core shape from v3 — extended with the Critic and Sentinel fields.)*

```json
{
  "agent_name": "weather_intelligence",
  "query_id": "8f3b2a1c-7e4d-4b9a-bc29-81a93b4512e0",
  "reasoning_depth": "STANDARD",
  "inputs_consumed": {"lat": 8.80, "lon": 78.14, "time_window": "2026-08-29T06:00:00Z"},
  "outputs": {
    "significant_wave_height_m": 1.4, "wave_period_s": 7.2, "wind_speed_kmh": 22.0,
    "swell_direction_deg": 140, "lightning_risk": false, "active_warnings": []
  },
  "source_provenance": {
    "dataset": "Open-Meteo Marine API / ECMWF WAM Blend",
    "acquisition_timestamp": "2026-08-29T01:00:00Z",
    "freshness_minutes": 75
  },
  "confidence": {"score": "HIGH", "rationale": "Direct high-resolution NWP grid matching target window"}
}
```

`persona_context` remains intentionally absent — specialist agents don't need to know who's asking. Only Reporting consumes persona. Critic evaluation results and Sentinel dispatch logs use the same `AgentResult`-shaped envelope with `agent_name: "critic"` / `"sentinel"` respectively, so the trace panel renders them identically to specialist output — no special-casing in the UI layer.

---

## 7. Use-Case Coverage Audit

Every sample query and named scenario in the master requirements doc (§6 stakeholder needs, §7 pilot-region queries, §12 sample queries), plus scenarios implied by both architecture documents' own worked examples. For each: does v3-as-written handle it correctly, and if not, what changes in v4 close the gap. This is the audit the user asked for, done exhaustively rather than illustratively.

| # | Scenario / Sample Query | Persona | Matched Row(s) (§4) | v3-as-written | v4 Change |
|---|---|---|---|---|---|
| 1 | "आज सबसे नज़दीक़ मछली पकड़ने का क्षेत्र कहाँ है?" (Hindi, nearest PFZ today) | fisherman | PFZ nearest | **Adequate.** Intent routing, language handling, and SHALLOW rendering all covered. | None functionally; full trace given in §8.2 for demo-script use. |
| 2 | "Is it safe to venture into sea tomorrow morning near [village]?" | fisherman | Safety check | **Adequate.** This is v3's own Trace A. | None. |
| 3 | "What are the tide, weather, and sea conditions near [location]?" | fisherman / general | Conditions | **Adequate.** | None. |
| 4 | "Any lightning or cyclone alerts in my area this week?" | fisherman / authority | Lightning/cyclone | **Adequate** for the query itself, but v3 never specifies what happens if the user *isn't actively asking* and a cyclone forms mid-week. | **Gap closed by Sentinel Agent (§3.2, Agent 11)** — this is precisely the push-notification case v3 left unbuilt. |
| 5 | "Which regions show high chlorophyll and favourable SST right now?" | researcher / fisherman | Chlorophyll/SST regions | **Adequate** for researcher. For a fisherman phrasing the same intent colloquially ("where's the water looking good"), persona-blind routing correctly still fires the same agents — this is the intent/persona split working as designed. | None; noted as a positive-case validation of the core v3 principle. |
| 6 | "Safest route from [port A] to [fishing ground B] given current sea state" | commercial_navigator | Route | **Gap.** v3's routing table fires Geospatial correctly, but nowhere does v3 specify vessel-class threshold adjustment reaching Risk Assessment — the YAML-style vessel profile concept existed only in the alternate-lineage doc. | **Fixed:** `vessel_class` promoted to a first-class `ORCAState` field (§5) and RAA's threshold-delta table backfilled into Agent 7 (§3.1). Full trace §8.6. |
| 7 | "Why has fish catch declined in [region] over the last month?" | researcher / fisherman | Diagnostic | **Partial gap.** v3 correctly forces STANDARD+ depth, but has no quality-validation step at all for a causal claim — the exact kind of claim most likely to overstate correlation as causation. | **Fixed by Critic Agent (§3.2, Agent 10)**, triggered on depth not persona — so this closes the gap for *both* a researcher's version and a fisherman's version of this query. Full trace §8.3. |
| 8 | "Which zones should I avoid due to hazardous conditions or boundary restrictions?" | fisherman / operator | Zones to avoid | **Adequate.** | None. |
| 9 | *(Researcher)* "Chlorophyll anomaly trend for the Arabian Sea, last quarter, with source metadata" | researcher | **Missing row entirely in v3.** | **Gap.** v3's intent table has no export-shaped row; "SST/Chl trend" queries fall under "high chlorophyll + SST regions," which doesn't imply an export/download deliverable. | **New intent row added (§4): "Export / download this data."** Reporting gets an explicit export-formatter mode (CSV/NetCDF/GeoJSON) rather than inferring it from persona alone. Full trace §8.4. |
| 10 | *(Authority)* "District-level risk summary, next 48 hours" | coastal_authority | Safety + conditions (union) | **Adequate**, exercises multi-match resolution (§4.1) correctly — "risk summary" hits both the safety row and conditions row. | None; noted as a validation case for multi-match logic. Full trace §8.5. |
| 11 | "How close am I to the Sri Lanka maritime boundary near Rameswaram?" | any (esp. fisherman) | Zones to avoid / geofence | **Adequate.** | None. |
| 12 | "Is Palk Bay safe to fish in given the current NE monsoon forecast?" | fisherman | Safety check | **Adequate.** | None. |
| 13 | "Where are the persistent fishing zones near Thoothukudi this week?" | fisherman / researcher | PFZ nearest | **Partial gap.** v3's Ocean Analytics agent spec never mentions a persistence-scoring tool, even though the master doc's pilot-region rationale explicitly leans on "persistent PFZ hotspots" as the region's defining, citable data story. | **Fixed:** `score_pfz_persistence` tool added to Agent 5 (§3.1). |
| 14 | "Am I approaching the Gulf of Mannar Marine National Park boundary?" | fisherman / operator | Geofence, proactive | **Gap.** A single on-demand query answers "am I close right now," but the phrasing ("approaching") implies a continuous check across a voyage, which v3's request/response graph cannot do by itself. | **Fixed:** new "Boundary proximity — proactive/continuous" row (§4) registers a short-lived Sentinel watch alongside the immediate answer. Full trace §8.9. |
| 15 | "Is there a cyclone risk for the Kanyakumari coast this weekend?" | fisherman / authority | Lightning/cyclone | **Adequate** for the on-demand answer; same Sentinel gap as #4 applies if the user doesn't check back. | Covered by the same Sentinel fix as #4. |
| 16 | Multi-intent: "Is it safe tomorrow and where's the nearest PFZ?" | fisherman | Safety + PFZ (union) | **Adequate** — this is exactly what §4.1 multi-match resolution is for. | None; validation case. |
| 17 | Low-confidence persona inference (ambiguous phrasing, no explicit profile) | unresolved | any | **Adequate.** This is v3's own Trace E and its best-designed mechanism. | None. Full trace §8.7 (extended with the correction-tap follow-through, which v3's Trace E stops short of showing). |
| 18 | Multi-turn follow-up: "what about tomorrow evening?" | fisherman | Safety check (re-resolved) | **Adequate.** v3's own Trace D. | None. Full trace §8.8. |
| 19 | No-match / garbled or off-topic query | any | No-match fallback | **Adequate** — v3's §5.2 (now §4.2) explicitly covers this. | None. |
| 20 | "Notify me if conditions change" (alert subscription) | fisherman / operator | **Missing row entirely in v3.** | **Gap.** v3's own intent taxonomy (inherited conceptually from the alternate-lineage doc's `ALERT_SUBSCRIPTION` category) was never actually given a routing row or an executing agent. | **Fixed:** new "Notify me if conditions change" row (§4) + Sentinel Agent (§3.2) as the actual executor. This was the single largest functional gap found in the audit. |
| 21 | All upstream sources down simultaneously | any | any | **Partial gap.** v3's Failover Hierarchy (§ below, per-source) handles individual source failure, but never states the terminal case where every fallback in a chain is exhausted for a *safety-relevant* query. | **Fixed:** explicit degraded-response contract added to §12 error handling — a stale-cache verdict is never presented with the same visual confidence as a live one, and the amber LOW-DATA treatment is forced regardless of what RAA's math would otherwise output. Full trace §8.11. |
| 22 | Geofence breach imminent mid-voyage | fisherman / operator | Geofence (interrupt) | **Adequate conceptually** — RAA's `CRITICAL_GEOFENCE` status exists — but v3 never states this should *interrupt* an in-progress session rather than wait to be asked. | **Fixed:** treated as a special case of the Sentinel-registered proactive watch (#14) — once a route or continuous-check subscription exists, a boundary crossing triggers immediate push, not just an on-demand answer. |
| 23 | Distress / emergency signal ("boat is sinking," SOS tap) | fisherman (any) | **Not addressed in either source document at all.** | **Severe gap.** Master doc §6.5 names DAT-SG/Sagarmitra as the natural handoff point; neither architecture document builds a flow for it. | **Fixed:** new Distress & Emergency Handoff Agent (§3.2, Agent 12) — the single most important addition in v4, closing a real gap rather than an optimization. Full trace §8.10. |
| 24 | Vessel-class-aware routing (mechanized trawler vs. cargo vessel thresholds) | commercial_navigator | Route + Safety | **Gap**, same root cause as #6. | Same fix as #6. |
| 25 | Conflicting data sources (SST from ERDDAP disagrees with Copernicus by >1°C) | any | any | **Gap.** Present in the alternate-lineage doc's error-handling table (§9) but absent from v3 entirely — v3's Failover Hierarchy only covers a source being *down*, not a source *disagreeing*. | **Fixed:** added to §12 error handling — report both values with sources, flag the discrepancy to the user, and downgrade confidence to MEDIUM regardless of individual source freshness. Full trace §8.11. |

**Audit summary:** 15 of 25 scenarios were already adequately handled by v3.0 as written — its core routing fix was sound and most sample queries just ride on it correctly. Of the 10 gaps found: 2 were missing intent-routing rows entirely (export, alert subscription), 2 were missing state fields/logic (vessel class, persistence scoring), 3 required genuinely new agents (Critic retargeting, Sentinel, Distress-Handoff), and 3 were missing failure-mode specifications (all-sources-down, conflicting sources, proactive geofence interrupt). None of the gaps were in the core persona/routing split itself — that part of v3 held up under the full audit.

---

## 8. Deep-Dive Traces (tool-call level)

Eleven traces, chosen to cover every agent at least once and every gap fix identified in §7 at least once.

### 8.1 Fisherman, Tamil, safety check (baseline — validates core routing is intact after all v4 additions)

**Query:** *"நாளை காலையில் கடலுக்கு போவது பாதுகாப்பானதா?"* — "Is it safe to go to sea tomorrow morning?"

```
Agent 1 (Ingress)
  detect_language → "ta" (Tamil)
  translate_to_english → "Is it safe to go to sea tomorrow morning?"
  session lookup → profile: fisherman, home port Thoothukudi (8.80°N, 78.14°E)
  distress check → detect_distress_signal(query) → false (no interrupt)

Agent 2 (Planning)
  classify_intent → [("Is it safe to go to sea", 0.94)]
  reasoning_depth → SHALLOW (fisherman default; no complexity push)
  execution_plan → WIA, [parallel: OAA(tide), GRA(boundary)], RAA, Visualization, Reporting

Agent 4 (WIA)
  get_marine_weather(8.80, 78.14, hours_ahead=24)
    → { wind: 14 kt NE, Hs: 1.1 m, swell_period: 9s, visibility: 8 km }
  get_lightning_nowcast(8.80, 78.14, 50) → { strikes_30min: 0 }
  get_cyclone_status("BoB") → { active_cyclones: 0 }

Agent 5 (OAA, parallel)
  get_tide_prediction(nearest_to(8.80, 78.14), "2026-08-30")
    → { high_tide: "05:42 IST, 0.7m", low_tide: "11:58 IST, 0.2m" }

Agent 6 (GRA, parallel)
  check_boundary_proximity(8.80, 78.14, "IMBL") → { distance_nm: 42.3, status: "CLEAR" }
  check_boundary_proximity(8.80, 78.14, "MPA_GULF_OF_MANNAR") → { distance_nm: 18.7, status: "CLEAR" }

Agent 7 (RAA, after 4/5/6 complete)
  evaluate_marine_safety(wave_height_m=1.1, wind_speed_kmh=25.9, lightning_active=False,
                          cyclone_alert=None, imbl_distance_nm=42.3, mpa_violation=False)
    → { status: "SAFE", go_no_go: "GO", reason: "All Parameters Within Safe Operational Limits" }
  compute_confidence(sources=[Open-Meteo <2h, INCOIS boundary files]) → HIGH

reasoning_depth == SHALLOW → Critic Agent (10) skipped entirely

Agent 9 (Reporting, fisherman format)
  🟢 பாதுகாப்பானது — நாளை காலை கடலுக்கு செல்லலாம்
  காற்று: 14 நாட் வடகிழக்கு | அலை: 1.1 மீ | ஏற்றம்: காலை 5:42
  எல்லை: பாதுகாப்பான தூரம் (42 கடல் மைல்)
  Map: single pin, green GO badge. Voice: Tamil TTS.
```

**What this confirms:** all v4 additions (distress check, critic-gate, vessel_class field) sit inline without adding latency to the shallow fisherman path — the whole point of Principle 10 (§1).

---

### 8.2 Fisherman, Hindi, PFZ nearest

**Query:** *"आज सबसे नज़दीक़ मछली पकड़ने का क्षेत्र कहाँ है?"*

```
Agent 1 → detect "hi", translate → "Where is the nearest fishing zone today?"
Agent 2 → intent: PFZ nearest (0.91), depth SHALLOW, plan: OAA, GRA, Reporting
Agent 5 (OAA)
  analyze_pfz_proximity(user_lat, user_lon, "2026-08-29")
    → { pfz_coords: (8.95, 78.30), distance_km: 17.2, bearing_deg: 34, advisory_age_hours: 19 }
  score_pfz_persistence(sector_id="TN_SOUTH_03", lookback_weeks=4) → { persistence_score: 0.81 }
Agent 6 (GRA) — spatial_query_zones to confirm PFZ point isn't inside any exclusion polygon → clear
Agent 9 (Reporting, fisherman format)
  📍 அருகிலுள்ள மீன்பிடி மண்டலம்: 17.2 கிமீ தொலைவில், வடகிழக்கு திசையில்
  (advisory issued 19h ago — within the ~3x/week freshness window, no staleness flag needed)
  Map: single pin at PFZ coordinates + user position, direction arrow.
```

---

### 8.3 Diagnostic "why has catch declined" — Critic Agent engaged (closes gap #7)

**Query (researcher persona):** "Why has fish catch declined in Thoothukudi over the last month?"

```
Agent 2 → intent: Diagnostic (0.89) → forces depth STANDARD+ → researcher default is
  already DEEP, no change; plan: MDD, OAA(diagnostic mode), GRA

Agent 5 (OAA)
  diagnose_productivity_decline(region="Thoothukudi", date_range="last_30_days")
    → {
        sst_anomaly_c: +1.3, chl_a_delta_pct: -22, catch_delta_pct: -18,
        monsoon_shift_days: 6,
        hypothesis: "Elevated SST correlating with reduced chlorophyll and catch;
                      monsoon onset delay is a plausible contributing factor.",
        evidence_strength: { sst_chl_correlation: "MODERATE", catch_correlation: "WEAK-MODERATE" }
      }

reasoning_depth == DEEP → Agent 10 (Critic) engages BEFORE Reporting

  Draft response (pre-critic) claims: "SST rise caused the chlorophyll drop, which caused
  the catch decline."

  critic.evaluate() flags:
    ISSUE 1 [CAUSAL_CLAIM_STRENGTH]: "caused...caused" chains two moderate correlations
      into an asserted causal pathway; evidence_strength only supports "associated with,"
      and a 6-day monsoon shift is not ruled out as a confound.
    ISSUE 2 [CITATION_COMPLETENESS]: catch_delta_pct sourced from data.gov.in but no
      district-level breakdown citation was attached.

  request_correction(ISSUE 1, "ocean_analytics") → re-invoke diagnose_productivity_decline
    with instruction to report correlation strength explicitly and name monsoon shift as
    an unresolved confound, not a footnote.
  request_correction(ISSUE 2, "marine_data_discovery") → re-fetch with explicit district
    filter + citation metadata attached.

  Second pass → critic.evaluate() → PASS

Agent 9 (Reporting, researcher format)
  "SST in the Thoothukudi sector was ~1.3°C above the seasonal mean over the past 30 days,
  coinciding with a 22% drop in chlorophyll-a and an 18% drop in reported catch (source:
  data.gov.in, Thoothukudi district, Aug 2026). Correlation strength between SST and
  chlorophyll is moderate; between SST and catch, weak-to-moderate. A 6-day delay in
  monsoon onset over the same window is a plausible confounding factor and has not been
  ruled out. This is an association, not a confirmed causal chain — a longer time-series
  comparison would be needed to isolate the dominant driver."
  [Full sensor metadata, methodology note, and CSV export link attached.]
```

**Why this matters:** the pre-critic draft was the kind of overconfident causal claim that would embarrass ORCA in front of an ISRO/INCOIS judge who knows the underlying science. This is exactly the failure mode Principle 7 was written to catch, and it would have shipped unexamined under v3's persona-gated critic.

---

### 8.4 Researcher data export — closes gap #9 (missing intent row)

**Query:** "Show me the chlorophyll anomaly trend for the Arabian Sea over the last quarter, with source metadata."

```
Agent 2 → intent match: "High chlorophyll + SST regions" (0.61) AND new "Export/download
  this data" row (0.85) → multi-match union: Discovery, Ocean Analytics, Reporting
  (export-formatter mode)

Agent 5 (OAA)
  compute_sst_chl_trend(bbox=ARABIAN_SEA, date_range="last_quarter")
    → time-series array + anomaly flags + per-point sensor/algorithm metadata

Agent 9 (Reporting, export-formatter mode — NEW in v4)
  Structured report: mean anomaly, trend line chart spec, full sensor chain
  (MODIS-Aqua L3, NASA OB.DAAC, algorithm v2022.0, 4km resolution)
  Export buttons: CSV, NetCDF, GeoJSON — generated by the same Visualization Agent
  tooling used for map layers, just serialized to a downloadable file instead of
  rendered.

  Without the new export row, v3 would have matched only the SST/Chl "regions" row,
  which produces a *snapshot* answer — it has no formatter path that thinks in terms
  of "quarter," "trend," or "downloadable," so the user's actual ask (an export) would
  have silently degraded into a prose summary of current conditions. This was a real
  functional miss, not a cosmetic one.
```

---

### 8.5 Coastal authority, 48h district brief — validates multi-match (no gap)

**Query:** "Give me a district-level risk summary for the next 48 hours ahead of the approaching system."

```
Agent 2 → matches BOTH "Is it safe to go to sea" (0.72) and "Tide/weather/sea conditions"
  (0.68) → union: Discovery, Weather, Ocean Analytics, Risk Assessment
  reasoning_depth: STANDARD (authority default), time window overridden to next_48_hours
  per persona profile

Agent 4 (WIA) → get_cyclone_status("BoB") → active system, track projected within 300km
  of district coastline in 36h
Agent 7 (RAA) → evaluate_marine_safety(...) per-sector across district grid →
  aggregate: 3 sectors GREEN, 2 sectors YELLOW (CAUTION), 0 RED yet — trending toward
  RED in the 300km cyclone band per WIA's projection
  confidence: HIGH (IMD CAP + Open-Meteo, <2h old)

Agent 9 (Reporting, dashboard format)
  District Marine Brief — Thoothukudi
  Overall (now): 3/5 sectors GREEN, 2/5 CAUTION
  48h projection: escalating — cyclone track brings sector 4-5 into NO-GO band by hour 36
  CAP-format alert payload generated, ready for escalation trigger if any sector crosses RED
  briefing_export: true → PDF generated
```

---

### 8.6 Maritime operator, route with vessel class — closes gaps #6/#24

**Query:** "Safest route from Thoothukudi to fishing ground 40km SE, I'm running a mechanized trawler."

```
Agent 1 → vessel_class extracted from query text, written to ORCAState.vessel_class =
  "mechanized_trawler" (NEW v4 field — previously this only lived inside a persona YAML
  block in the alternate-lineage doc and had no path into RAA in v3 at all)

Agent 2 → intent: "Safest route" (0.90) → plan: MDD, WIA, OAA, GRA, RAA

Agent 6 (GRA)
  compute_safe_route(origin=THOOTHUKUDI_PORT, destination=FISHING_GROUND_SE,
                      vessel_draft=MECHANIZED_TRAWLER_DRAFT, constraints=[IMBL_buffer, MPA_polygon])
    → straight-line-buffered route (A* fallback not yet built per §3.1 risk note) +
      hazard annotations: passes within 6.2 NM of Gulf of Mannar MPA boundary — inside
      CAUTION band under DEFAULT thresholds

Agent 7 (RAA)
  Applies vessel_class delta BEFORE evaluate_marine_safety: mechanized_trawler →
  wind band +5kt, Hs band +0.5m on each threshold
  evaluate_marine_safety(wave_height_m=1.9, wind_speed_kmh=28, ..., mpa_violation=False)
    → with small_fishing thresholds this would read CAUTION (Hs 1.9 is in the 1.5-2.5
      band); with mechanized_trawler's relaxed bands, Hs 1.9 falls under the relaxed
      GO ceiling → { status: "SAFE", go_no_go: "GO" }

  Without the vessel_class fix, RAA would have applied small_fishing's conservative
  thresholds to every persona uniformly (v3's stated table had the concept in the
  alternate-lineage doc only) — a mechanized trawler operator would get an over-cautious
  CAUTION rating on genuinely fine-for-their-vessel conditions, which erodes trust in
  the safety layer for the persona that most needs to trust it operationally.

Agent 9 (Reporting, operational_brief format)
  Route polyline + waypoint table w/ ETA, GO badge, MPA-proximity annotation kept
  visible even though the vessel-class-adjusted verdict is GO (geofence proximity is
  never suppressed regardless of safety verdict — Principle 3).
```

---

### 8.7 Low-confidence persona inference, through to correction tap

**Query (no explicit persona set):** "What's the SST trend near Palk Bay and is it safe to be out there right now?"

```
Agent 1 → resolve_persona → classifier confidence 0.55 (phrasing has both researcher-
  and fisherman-shaped signals) → stakeholder_persona: "unresolved",
  stakeholder_persona_source: "inferred_low"

Agent 2 → intent routing is persona-blind regardless — matches BOTH "SST/Chl regions"
  and "Is it safe" rows → full union dispatch: MDD, WIA, OAA, RAA all run at full depth.
  (This is the part v3 already got right — inference confidence affects rendering only,
  never computation completeness.)

Agent 9 (Reporting) → conservative composite render:
  🟡 Top: plain-language GO/CAUTION/NO_GO banner (fisherman-style)
  Below: "Show technical detail" expand → reveals SST trend numbers + sensor metadata
  persona_correction_available: true, control shown: "This isn't quite right for me —
  I'm a [Fisherman / Researcher / Authority / Operator]"

--- USER TAPS "Researcher" ---

Agent 9 re-renders WITHOUT re-querying (v4 confirms this stays true — all underlying
  agent_results are already in state from the full-depth run above):
  Full structured_report format, statistical summary, sensor metadata, export links.
  stakeholder_persona_source set to "explicit", persisted for session.
  Correction logged as a training signal for future threshold tuning (§9.16).
```

---

### 8.8 Multi-turn follow-up

```
Turn 1 (fisherman): "Is it safe to go to sea from Thoothukudi tomorrow morning?"
  → resolved, SAFE/GO. session_history appends
    {bbox: THOOTHUKUDI, time_window: "tomorrow_AM", persona: fisherman, verdict: GO}

Turn 2: "What about tomorrow evening?"
  Agent 1 → resolve_coreference: detects elliptical follow-up, resolves bbox from
    session_history[-1] (location unchanged), updates only time_window → "tomorrow_PM"
  Agent 2 → routes the same "is it safe" pattern with the new time window
  Agent 4/7 → fresh WIA + RAA call for the new window only (bbox-cached data reused
    where TTL allows — see §9.14 stale-while-revalidate)
  Agent 9 → states the new verdict directly, without re-asking for location:
    "Tomorrow evening near Thoothukudi: 🟡 CAUTION — wind picking up to 22kt after 6PM."
```

---

### 8.9 Proactive geofence approach — closes gap #14

**Query:** "Am I approaching the Gulf of Mannar Marine National Park boundary?"

```
Agent 2 → matches new "Boundary proximity — proactive/continuous" row → Geospatial,
  Risk Assessment, PLUS registers a Sentinel watch (Agent 11) scoped to this session's
  vessel position for the remainder of the voyage (or a bounded time window, e.g. 6h)

Agent 6 (GRA) → check_boundary_proximity(current_lat, current_lon, "MPA_GULF_OF_MANNAR")
  → { distance_nm: 3.1, status: "APPROACHING" }
Agent 7 (RAA) → CAUTION (within 0.5-2 NM band would be NO_GO; 3.1 NM is CAUTION)

Agent 9 → immediate answer given: "🟡 You are 3.1 NM from the Gulf of Mannar boundary
  and closing. I'll alert you if you get within 0.5 NM." Sentinel subscription
  confirmed in the payload (sentinel_subscription field populated in ORCAState).

--- 40 minutes later, still within the voyage window ---

Sentinel (Agent 11) background check for this session's watch:
  new position → check_boundary_proximity → { distance_nm: 0.4, status: "BREACHED" }
  → verdict crossed CAUTION→NO_GO threshold → dispatch_alert() fires immediately via
    the user's active channel (push/SMS), NOT queued for the next on-demand query.
  → written to audit_trace_log as a P0 event.
```

**Why v3 couldn't do this:** v3's graph only executes in response to a query. Nothing re-checked the user's position 40 minutes later unless they asked again. This is the concrete cost of leaving Sagar-Vani-style push as a reference rather than a built component — the Sentinel Agent is what makes this scenario (a real, recurring IMBL-detention risk per the master doc's own pilot-region rationale) actually work.

---

### 8.10 Distress signal — closes gap #23, the most severe gap found

**Message (fisherman, voice channel, Tamil):** *"படகு மூழ்குகிறது!"* — "The boat is sinking!"

```
Agent 1 (Ingress) — BEFORE normal persona/intent processing:
  detect_distress_signal(transcript) → pattern match against multilingual maritime
    distress term list → TRUE, distress_type: "vessel_taking_on_water"

  ORCAState.distress_flag = True → this SHORT-CIRCUITS the entire graph. Planning,
  intent classification, persona resolution for rendering purposes — all bypassed.
  Routes directly to Agent 12.

Agent 12 (Distress & Emergency Handoff)
  position lookup: GPS available from channel metadata → (8.81, 78.12)
  (if unavailable: ONE question asked, overriding even the fisherman "never ask"
   rule — "Where are you right now?" — because a wrong default location here is
   worse than a 5-second delay)

  emit_datsg_handoff(position=(8.81,78.12), vessel_id=session.registered_vessel_id,
                      distress_type="vessel_taking_on_water",
                      timestamp="2026-08-29T14:32:00+05:30")
    → structured payload in DAT-SG/Sagarmitra-compatible format (or CAP-fallback
      structure if direct integration isn't wired up for the hackathon build)

  surface_mrcc_contact(user_location, "ta")
    → Coast Guard MRCC Tuticorin contact number + VHF channel, read aloud via TTS
      in Tamil simultaneously with the handoff dispatch — belt-and-suspenders in
      case the automated channel doesn't reach a human fast enough

  Logged as a P0 audit_trace_log event, separate stream from ordinary query logs,
  flagged for immediate human review regardless of what happens downstream.

Response to user (voice, immediate, no persona formatting applied):
  "உங்கள் இருப்பிடம் கடலோர காவல் படைக்கு அனுப்பப்பட்டது. உதவிக்கு அழைக்கவும்: [MRCC number]."
  ("Your location has been sent to the Coast Guard. Call for help: [MRCC number].")
```

**Why this is the single highest-priority fix in v4:** neither source architecture document has any flow like this at all, despite the master requirements doc explicitly naming DAT-SG/Sagarmitra as "the natural handoff point... rather than reinventing distress signaling" and listing it as a Risk/Gap to address. A disaster-management-themed PS that has zero path from "user says they're in danger" to "the right agency is notified" is a real, demo-visible hole, not a nice-to-have.

---

### 8.11 Degraded response: all sources down + conflicting sources — closes gaps #21/#25

**Scenario A — total outage:**

```
Agent 4 (WIA) attempts get_marine_weather → Open-Meteo timeout → fallback Stormglass
  → also timeout → fallback: cached data, 14h old
Agent 6 (GRA) boundary files → local, unaffected (static data, no live dependency)
Agent 7 (RAA) → confidence.score forced to LOW-DATA regardless of what the deterministic
  math would otherwise output — even if wind/wave numbers from the stale cache would
  mathematically classify as GO, the LOW-DATA amber treatment overrides the visual
  confidence (per §2.6's rendering matrix — applies to every persona, fisherman included)
Agent 9 → "🟡 Data limited — using last known conditions from 14h ago. Verify locally
  before deciding. [stale GO badge in amber, not green]"
```

**Scenario B — conflicting sources:**

```
Agent 5 (OAA) get_sst_snapshot via ERDDAP → 28.4°C
              get_sst_snapshot via Copernicus (cross-check per §9 optimization) → 29.7°C
  Delta = 1.3°C > 1.0°C discrepancy threshold → BOTH values reported, source-attributed,
  discrepancy flagged to user rather than silently picking one.
  confidence_tier downgraded to MEDIUM even though each individual source is <6h old —
  disagreement itself is treated as a confidence signal, not just staleness.
```

Neither of these failure modes was specified anywhere in v3.0. Both are now explicit contract behavior, not implementation-time improvisation.

---

## 9. New Optimizations (v4.0 — none of these existed in either source document)

Every optimization here was checked against **Principle 10** (§1): it must not weaken safety-critical determinism, evidence citation, or the conservative-default behavior. The "Safety impact" column makes that check explicit rather than assumed.

### Latency

**9.1 — Semantic near-duplicate query caching.**
Many fishermen from the same home port ask near-identical safety queries on any given morning ("is it safe today," "safe to go now," "can I go out"). Embed the normalized query + resolved bbox/time into a vector, and if a semantically near-duplicate query was answered within the last cache TTL (aligned to each source's real freshness cadence, not a fixed number), serve the cached full response instead of re-running the graph.
*Safety impact:* cache key must include the resolved `target_bbox` + `target_time_window`, never just raw text similarity — two different villages asking "is it safe" must never share a cache entry. TTL is capped at the tightest freshness window among the sources actually used (e.g., lightning nowcast's 30-min window governs, not PFZ's 3x/week window), so a cached GO can never outlive the data that justified it.

**9.2 — Predictive pre-computation for registered locations.**
Rather than computing safety verdicts only on-demand, run a lightweight version of the WIA+RAA path proactively for every registered home port on a schedule (this is what Sentinel, Agent 11, already does for monitoring — 9.2 is the recognition that its output doubles as a warm cache for on-demand queries from the same location). A fisherman's 6am query then often hits an already-computed answer from Sentinel's 5:55am check rather than triggering a fresh graph run.
*Safety impact:* pre-computed results still carry their own freshness timestamp and are subject to the same staleness rules as a live call — "pre-computed" is a performance property, not a confidence downgrade or upgrade.

**9.3 — Cost-based agent short-circuiting.**
Detailed in §4.3. If Weather + Geospatial alone already yield a RAA `NO_GO`, cancel non-safety-relevant pending calls (e.g. a co-occurring PFZ lookup) unless the user explicitly asked for that data too.
*Safety impact:* only ever cancels agents whose output the *current* response doesn't depend on. Never cancels RAA itself, never cancels a call an explicit sub-intent needs.

**9.4 — Speculative parallel dispatch with early-cancel.**
Fire WIA, GRA, and OAA in parallel as usual, but if RAA can reach a `NO_GO` verdict from WIA+GRA alone before OAA returns, cancel the in-flight OAA call (a fisherman told not to go doesn't need PFZ coordinates in that same response — though the Reporting layer should still offer "want to know where the nearest zone is for when it clears?").
*Safety impact:* cancellation only ever trims non-safety data attached to an already-final safety verdict; the verdict computation itself is never shortened.

**9.9 — Request coalescing during hazard-window spikes.**
During a cyclone, many users in the same district ask functionally the same question within seconds of each other. Deduplicate concurrent in-flight requests that resolve to the same `(bbox, time_window, intent)` key into a single upstream computation, fan the result out to all waiting sessions. This is what actually makes the Sentinel Agent's district-wide checks (§3.2) affordable at scale rather than one full graph run per registered user.
*Safety impact:* coalescing happens only on *identical* resolved parameters — never on textually-similar-but-differently-located queries (see 9.1's cache-key discipline, same principle applies here).

**9.14 — Stale-while-revalidate caching at the MDD layer.**
For non-safety-critical, slower-changing data (SST snapshots, PFZ persistence scores), serve the last cached value immediately while triggering a background refresh, rather than blocking the response on a fresh fetch. Used in the multi-turn trace (§8.8) — turn 2's unchanged bbox reuses cached WIA data if still within TTL instead of a full re-fetch.
*Safety impact:* explicitly **not** used for any value RAA consumes directly (wind, wave, lightning, cyclone, boundary proximity) — those are always fetched fresh or explicitly marked stale, never silently served from a background-refresh cache. This optimization is scoped to informational, not safety-gating, data.

**9.19 — Progressive/streaming response rendering.**
Stream partial results to the UI as each specialist agent completes rather than waiting for the full graph — e.g., render the map pin and weather numbers as soon as WIA/GRA return, then update with the RAA verdict badge a moment later, rather than a single blocking spinner. Improves perceived latency without changing actual compute time.
*Safety impact:* the safety badge is explicitly the *last* thing populated, never a placeholder "probably fine" state — a user must never see an unbadged or ambiguous state and assume a favorable one.

### Cost

**9.5 — Hybrid rule-based + embedding-similarity intent classification.**
Keep the deterministic table match (§4) as the primary router — it's fast, free, and auditable. Only fall back to an embedding-similarity classifier (cheaper and faster than an LLM call) when the query doesn't cleanly match a row above a confidence threshold, before falling back further to a full LLM classification pass. Three-tier cascade: rules → embeddings → LLM, each tier only invoked if the previous one is inconclusive.
*Safety impact:* none of the three tiers changes what happens once intent is resolved — routing logic (§4) is unchanged; this only optimizes *how* the match is found.

**9.6 — Cost-tiered LLM model cascade.**
Use a small/cheap model for intent classification, language detection confidence scoring, and SHALLOW-depth response drafting. Reserve the larger/more capable model for DEEP-depth synthesis and the Critic Agent's evaluation pass, where reasoning quality actually matters for the citation/causal-claim checks in §3.2.
*Safety impact:* RAA and GRA are never LLM calls at all (Principle 3) — this cascade only applies to the generative/explanatory layer, never to the deterministic safety math.

**9.11 — Content-addressable MDD cache keys.**
Cache keys built from `(source, dataset_id, bbox_hash, time_window, params_hash)` rather than opaque per-query keys, so two different user queries that happen to need the same underlying dataset slice (e.g., two fishermen in adjacent villages both needing the same SST tile) share a cache hit even though their raw queries look nothing alike.
*Safety impact:* neutral — purely a cache-hit-rate improvement, doesn't touch what data is fetched or how fresh it must be.

### Reliability

**9.8 — Circuit breaker with background health-check pinger.**
Rather than discovering a source is down only when a user query fails against it (reactive), run lightweight background health pings against each upstream source on an interval matched to its own volatility (frequent for Open-Meteo, sparse for GEBCO bathymetry which never changes). Trip the circuit breaker proactively so the fallback cascade (Failover Hierarchy, §12) is already engaged before the next user query arrives, rather than eating one full timeout per affected query.
*Safety impact:* strictly an availability/latency improvement — the fallback behavior itself (§12) is unchanged, just triggered earlier.

**9.12 — Cross-source consistency checking as a first-class QA step, not just an incidental error case.**
Doc'd as a reactive error case in §12 (originating from gap #25 in §7), but worth stating as a proactive optimization too: for any parameter where two independent sources are cheaply queryable in parallel (e.g., SST from both ERDDAP and Copernicus), run both when the query is safety-relevant or diagnostic, not only when one source fails. Disagreement above threshold is itself useful information (data quality signal), not just a fallback trigger.
*Safety impact:* directly strengthens Principle 4 (provenance) — this is a safety-positive optimization, not a neutral one.

### Scale

**9.10 — Priority lane / backpressure design for hazard-window traffic.**
The master doc's NFR explicitly calls out "high availability specifically during cyclone/hazard events, when demand spikes hardest." Architect two request lanes: a fast, resource-guaranteed lane for `SAFETY_CHECK`-intent, SHALLOW-depth queries (the exact shape of what a scared fisherman asks during a cyclone), and a standard lane for everything else (researcher exploration, data export, DEEP-depth diagnostics) that gets rate-limited or queued first under load.
*Safety impact:* explicitly safety-positive — it's the mechanism that keeps go/no-go answers fast for the highest-stakes users precisely when the system is under the most stress, at the cost of researcher/export queries queuing longer.

**9.17 — Adaptive Sentinel polling frequency.**
Agent 11's background loop shouldn't poll every registered location at a fixed interval regardless of conditions. Scale polling frequency to hazard proximity: locations near an active cyclone track or already at CAUTION get checked every few minutes; locations with stable GREEN conditions and no active regional hazard get checked hourly. This keeps steady-state background load low without sacrificing responsiveness exactly when it matters.
*Safety impact:* safety-positive by construction — polling frequency scales *up* with risk, never down.

### Voice/Edge

**9.15 — Edge/quantized local STT for the Whisper fallback.**
Since Whisper is the offline/rate-limit fallback for Bhashini ASR (§3.1, Agent 1), and fishermen at sea are the connectivity-poorest users, evaluate a quantized (int8) small/medium Whisper variant that can run acceptably on lower-spec edge hardware or a lightweight server tier, rather than assuming a full-precision model is always reachable. This is a cost/latency optimization with a direct reliability payoff for exactly the persona the master doc calls "highest-stakes, least likely to have connectivity."
*Safety impact:* must be validated against Indic-language word-error-rate before being trusted as primary fallback (already flagged as unresolved in §16) — quantization is a deployment optimization, not a substitute for that validation.

### Evaluation / Observability

**9.16 — A/B evaluation harness for the persona-inference confidence threshold.**
The 0.70 threshold (§2.4) is a placeholder in both v3 and this document. Rather than leaving it as an unowned TODO, define the actual methodology: log every inferred-persona decision alongside its eventual outcome (did the user hit the persona-correction control? §2.5), compute precision/recall per persona pair against that signal, and run a scheduled threshold-tuning pass (weekly during active pilot use) rather than a one-time guess. The persona-correction tap (§2.5) already generates exactly the labeled data this needs — it was designed as a UX affordance in v3 but doubles as an evaluation dataset if actually logged and used.
*Safety impact:* directly improves the reliability of Principle 6's "degrade toward conservative" behavior over time — a threshold that's too low produces confidently-wrong personas more often; too high produces unnecessary conservative-composite renders. Both failure directions are safe by construction (§2.4), so tuning is a UX/trust optimization, not a safety one — but it compounds with everything else if left unowned.

**9.18 — Distributed tracing instrumentation for the "visible execution trace" requirement.**
Both source documents *describe* wanting a visible agent hand-off trace for judges/auditors but neither specifies how it's actually built. Instrument every agent node with OpenTelemetry spans (agent name, inputs, outputs, latency, source-provenance) feeding a trace panel in the UI, and persist the same spans to `audit_trace_log` in `ORCAState` for the explainability/audit requirement (master doc §8, "Explainability/Auditability"). This turns "the demo should show a trace panel" from a UI mockup decision into an actual observability pipeline that also satisfies the legal/accountability NFR, not just the demo.
*Safety impact:* directly serves Principle 4 and the master doc's explicit audit requirement — every advisory must be traceable to its source dataset(s) and reasoning chain.

---

## 10. Technology Stack (committed, backfilled from the alternate-lineage doc and extended for v4's new agents)

| Layer | Technology | Rationale |
|---|---|---|
| **Agent Framework** | LangGraph (Python) | Stateful graph, conditional routing, checkpointing, native visibility into agent hand-offs — matches the "visible orchestration" requirement directly. |
| **LLM (shallow/cheap tier)** | A fast, low-cost model for intent classification, language ID confidence scoring, SHALLOW-depth drafting | Cost-tiered per §9.6; exact model choice left to implementation-time benchmarking rather than hardcoded here — verify current offerings before locking in, since prior-generation model names age quickly. |
| **LLM (deep tier)** | A stronger reasoning model for DEEP-depth synthesis and the Critic Agent's evaluation pass | Same caveat — benchmark at build time. |
| **Translation** | Bhashini API + IndicTrans2 (local fallback) | Government-endorsed, supports all target coastal languages; IndicTrans2 covers the offline/rate-limit case. |
| **Voice (ASR)** | Bhashini ASR (primary) + quantized local Whisper (fallback, §9.15) | Matches voice-first requirement; fallback addresses connectivity gap explicitly named in the master doc. |
| **Voice (TTS)** | Bhashini TTS (primary) + Google Cloud TTS (fallback) | Regional-language coverage with a commercial fallback for resilience. |
| **Geospatial** | GeoPandas, Shapely, pyproj | Industry standard for vector geometry — deterministic, auditable, matches Principle 3. |
| **Caching** | Redis (TTL-based, source-cadence-aware per §9.1/§9.14) | Fast in-memory cache; TTLs configured per source's real update cadence, not a single global value. |
| **Vector/embedding index** | A lightweight embedding store (e.g. FAISS or a managed vector DB) for §9.1 (semantic cache) and §9.5 (embedding-tier intent fallback) | Small enough footprint for a hackathon build; avoids needing a full LLM call for near-duplicate detection. |
| **Message/queue layer** | A lightweight queue (e.g. Redis Streams or equivalent) for §9.9 request coalescing and §9.10 priority lanes | Needed to implement backpressure and coalescing without a heavyweight broker. |
| **Frontend Map** | Leaflet + plugins | Open-source, lightweight, proven for marine visualization. |
| **Frontend Charts** | Chart.js or Recharts | Lightweight, responsive time-series and bar charts. |
| **Backend API** | FastAPI (Python) | Async, typed, auto-documented, integrates cleanly with LangGraph. |
| **Frontend** | Next.js (React) | SSR, component-based UI, good mobile experience — matters for the Android-first rural-reach requirement. |
| **Database** | PostgreSQL + PostGIS | Spatial queries, GeoJSON storage, session persistence, and the store for `session_history`/`audit_trace_log`. |
| **Raster Processing** | xarray, rioxarray, netCDF4 | Standard tools for NetCDF/GeoTIFF oceanographic data. |
| **Observability** | OpenTelemetry (traces) + a metrics/log backend | Backs §9.18's instrumentation requirement and the audit/explainability NFR directly. |
| **Alert dispatch** | SMS/IVR gateway modeled on Sagar Vani's channel mix, push notification service | Backs the Sentinel Agent (§3.2) and the alert-subscription intent row (§4). |

---

## 11. Visualization & Output Spec (itemized — backfilled and extended)

### 11.1 Map layer types

| Layer type | Used for |
|---|---|
| PointMarker | PFZ locations, user/vessel position, tide stations |
| Polygon | EEZ, MPA, IMBL buffer zones, alert zones, district boundaries |
| Polyline | Routes, with safety-gradient coloring (green/amber/red segments) |
| Heatmap | SST grid, chlorophyll concentration, wave height |
| Raster (WMS tile) | MOSDAC/Copernicus satellite imagery overlay |
| **Distress marker** *(NEW v4)* | Active Agent 12 handoff position — rendered with a distinct, non-dismissible marker style, visible to authority-persona dashboards monitoring a district |
| **Sentinel watch indicator** *(NEW v4)* | Shows an active proactive-monitoring subscription (§8.9) on the user's own map view — a small "watching this boundary" badge, and on authority dashboards, an aggregate count of active watches per district |

### 11.2 Chart types

| Chart type | Used for |
|---|---|
| TimeSeries | SST trend, chlorophyll trend, wave height forecast |
| BarChart | Fish catch by district/year, PFZ hit frequency |
| RadarChart | Multi-parameter safety score visualization (researcher/authority view) |
| WindRose | Wind direction distribution |

### 11.3 Persona-specific rendering (carried from §2.6, cross-referenced here for completeness)

fisherman → SimpleCard(icon, 2-line summary, GO/CAUTION/NO_GO badge, map pin, voice audio)
researcher → StructuredReport(tables, charts, methodology, citations, export links)
authority → DashboardCard(summary tile, expandable detail, alert cascade button, evacuation-buffer overlay)
operator → OperationalBrief(route overlay, condition summary, ETA, safety badge)

---

## 12. Failover Hierarchy & Error Handling (merged, extended)

### 12.1 Per-source failover

| Primary | Failure mode | Fallback |
|---|---|---|
| MOSDAC | 504 / auth delay / unclear open-access status — **Phase 0 blocker, see §16.1** | 1. Copernicus CMEMS · 2. Pre-cached NetCDF |
| INCOIS PFZ | HTML structure change | 1. INCOIS ERDDAP · 2. Local sector CSV |
| Open-Meteo Marine | Timeout >3s | 1. Stormglass API · 2. IMD CAP regional table |
| Bhashini ASR (ingress voice) | Timeout / rate limit | 1. Local Whisper (quantized, §9.15) |
| LLM provider | Rate limit / downtime | Model-agnostic swapper (both cost tiers, §9.6) |

### 12.2 Failure-mode / degraded-response contract

| Failure Scenario | Detection | Response |
|---|---|---|
| API timeout (any source) | Circuit breaker trip (§9.8) or per-call timeout | Fall back to cached data + explicit staleness warning |
| API rate limit | 429 response | Use cached data; backoff; queue for retry |
| No data for region | Empty result set | "No data available for [region]" with suggestion to widen area |
| **All sources in a chain exhausted (safety-relevant query)** | Every fallback in §12.1 fails for a source RAA depends on | **v4 explicit rule:** RAA still computes off the last-known-good cached values, but the LOW-DATA amber treatment is forced regardless of what the math outputs, for every persona including fisherman. Never present a stale verdict with the same visual confidence as a live one (§8.11 Scenario A). |
| **Conflicting data sources** | Two independently-queried sources disagree beyond threshold (e.g. SST >1.0°C apart) | Report both values with sources, flag the discrepancy, downgrade confidence_tier to MEDIUM regardless of individual freshness (§8.11 Scenario B, §9.12). |
| LLM hallucination in a DEEP-depth summary | Critic Agent catches value mismatch (§3.2, Agent 10) | Regenerate summary from raw data, up to 3 iterations, then ship with a flagged-items disclaimer |
| Geofence data corruption | Polygon validation fails (self-intersection) | Fall back to cached known-good boundary file; alert ops team |
| Infinite agent loop | iteration_count > max_agent_iterations | Force-terminate, return best available result with disclaimer |
| **Distress detection false negative risk** *(NEW v4)* | Pattern list doesn't cover a paraphrase of genuine distress | No automated mitigation possible without risking false positives from broader matching — mitigated operationally: the SOS UI control (§3.2, Agent 12) is always available as a non-language-dependent path, and this is logged as a residual risk (§16), not silently assumed solved. |

---

## 13. Non-Functional Requirements Traceability

Mapping each NFR from the master requirements doc (§8) to the specific v4 mechanism that satisfies it — makes the "we thought about this" claim checkable rather than asserted.

| NFR (master doc §8) | v4 mechanism |
|---|---|
| Near-real-time response for safety-critical alerts (target: seconds) | §9.3/§9.4 cost-based short-circuit + early-cancel; §9.9 request coalescing; §9.10 priority lane; Critic Agent explicitly excluded from the safety-verdict critical path (§3.2, Agent 10) |
| High availability during cyclone/hazard events | §9.10 priority lane + backpressure design; §9.17 adaptive Sentinel polling; §9.8 proactive circuit breakers |
| Scalability for concurrent queries during hazard windows | §9.9 request coalescing; §9.1/§9.2 caching and pre-computation reduce redundant graph runs at the source |
| Explicit staleness indicators, source-cadence-matched re-fetch | §12.2 degraded-response contract; §9.14 stale-while-revalidate (scoped away from safety-gating data) |
| Secure handling of location/identity data | Not newly addressed in this pass — flagged as an explicit open item in §16, since neither source document specified an auth/encryption model either |
| Standards-based outputs (GeoJSON, CAP) | Agent 8/9 output formats (§3.1); CAP-format alert payload explicit in authority persona rendering (§2.6, §8.5) |
| Explainability/Auditability — every advisory traceable to source + reasoning chain | §9.18 distributed tracing + `audit_trace_log`; §6 hand-off contract's `source_provenance` field on every agent result |

---

## 14. Observability & Evaluation Summary

- **Trace panel** (judge/demo-facing) and **audit log** (compliance-facing) are the *same* underlying OpenTelemetry span stream (§9.18) — not two systems to keep in sync.
- **Persona-inference threshold tuning** runs on a schedule against the correction-tap signal (§9.16) rather than being fixed at build time and forgotten.
- **Cross-source disagreement rate** (§9.12) is worth tracking as its own metric over the pilot period — a rising disagreement rate on a given parameter is an early signal one of the sources has degraded, independent of any single query surfacing it.
- **Sentinel dispatch volume and false-alarm rate** should be monitored explicitly once live — a Sentinel that fires too often on marginal threshold crossings trains users to ignore it, which is worse than not having it; tune the crossing-detection logic (§3.2, Agent 11) against real usage before wide rollout.

---

## 15. Build Plan — Phased Roadmap (v4)

### Phase 0: Foundation & Blockers (Week 1, Days 1-2)
- [ ] **Resolve MOSDAC access-tier ambiguity** (§12.1, §16.1) — hard gate before anything else in the data layer proceeds. Assign an explicit owner.
- [ ] Verify literal endpoints for INCOIS ERDDAP, Open-Meteo Marine, IMD CAP/Damini — don't assume documentation matches reality.
- [ ] Boundary data: download + index Marine Regions EEZ/IMBL, WDPA MPA, GEBCO bathymetry.

### Phase 1: Core Safety Path (Week 1, Days 3-7)
- [ ] Agent 7 (RAA): deterministic safety scoring engine, vessel-class deltas included from the start (§3.1) — not bolted on later.
- [ ] Agents 4/6 (WIA/GRA): minimal viable tool set for the safety path.
- [ ] LangGraph skeleton: Planning → WIA → GRA → RAA → Reporting (minimal graph).
- [ ] Fisherman persona: end-to-end "Is it safe?" flow, Tamil + Hindi.
- [ ] **Agent 12 (Distress Handoff): build in parallel, not deferred** — given it's the highest-severity gap found in §7, it should not be a Phase 3/4 afterthought the way it would be if treated as a "nice to have." Minimum viable version: keyword-pattern detection + MRCC contact surfacing, even before full DAT-SG payload formatting exists.

### Phase 2: Core Agents & Multi-Intent (Week 2)
- [ ] Agent 5 (OAA): SST/Chl analysis, PFZ proximity + persistence scoring, tide integration.
- [ ] Agent 3 (MDD): full catalog routing with narratable source-selection logic (§4.4).
- [ ] Multi-intent handling: parallel fan-out, union resolution (§4.1), no-match fallback (§4.2).
- [ ] Researcher persona: structured report format, evidence citations, new export-formatter mode (§8.4).
- [ ] New intent rows wired: Export/download, Alert subscription (registration only, Sentinel execution comes in Phase 3).

### Phase 3: Differentiation, Sentinel, Critic (Week 3)
- [ ] Persona correction control (§2.5) + confidence-threshold rendering (§2.4).
- [ ] **Agent 10 (Critic):** depth-triggered (not persona-triggered), wired into the DEEP-depth path with the async-upgrade rule for safety-adjacent queries (§3.2).
- [ ] **Agent 11 (Sentinel):** background loop, threshold-crossing detection, dispatch via SMS/IVR-modeled channel. Start with fixed polling, add adaptive frequency (§9.17) if time allows.
- [ ] Language Service: full Bhashini/IndicTrans2 integration for all named coastal languages.
- [ ] Voice pipeline: STT → agent → TTS for fisherman, Whisper fallback wired (quantization as stretch, §9.15).
- [ ] Coastal authority persona: dashboard format, alert cascade, CAP payload.
- [ ] Maritime operator persona: route overlay (straight-line-buffered fallback per §3.1's risk note — full A*/Dijkstra only if ahead of schedule), vessel-class-aware safety.
- [ ] Multi-turn conversation: session memory, coreference resolution.

### Phase 4: Optimization Pass & Polish (Week 4)
- [ ] §9.3/§9.4/§9.9: cost-based short-circuiting, early-cancel, request coalescing — implement once the base graph is stable, not before.
- [ ] §9.1/§9.14: semantic + stale-while-revalidate caching.
- [ ] Execution trace panel (§9.18 OpenTelemetry instrumentation) — visible agent hand-offs in UI.
- [ ] Historical replay mode: Cyclone Gaja scenario (or most recent NE-monsoon cyclone at build time).
- [ ] Diagnostic reasoning end-to-end, with Critic loop visibly engaging (good demo moment — showing a self-corrected answer is more impressive than a first-pass-correct one).
- [ ] Demo script: one query per persona showing differentiated output, plus the distress-handoff flow and the proactive-geofence Sentinel flow as the two "this is genuinely agentic, not just a chatbot" centerpieces.

---

## 16. Residual Open Risks (carried forward + new in v4)

### 16.1 Carried forward from v3.0, still unresolved
- **MOSDAC access model** — unresolved, Phase 0 blocker. Someone must visit mosdac.gov.in unauthenticated and document exactly what's downloadable without login vs. what needs standing-order registration.
- **"~1,223 coastal nodes" figure** — unverified, treat as approximate, don't repeat to judges without a primary source.
- **Persona-inference threshold (0.70)** — placeholder; methodology for validating it is now specified (§9.16), but the validation itself hasn't run yet.
- **STT accuracy for Indic languages** — Whisper fallback's WER for Tamil/Telugu/Malayalam under real fishing-village audio conditions is unverified.
- **No-match fallback UX copy** — needs actual review per persona so it reads as helpful, not evasive.

### 16.2 New in v4
- **Distress-detection false-negative risk** — a keyword/pattern approach (chosen deliberately over semantic inference, per Agent 12's own rationale) will miss paraphrases outside the maintained list. The SOS UI control mitigates but doesn't eliminate this. Needs a maintained, regularly reviewed multilingual term list, not a one-time build.
- **DAT-SG actual integration availability** — the master doc names it as "the natural handoff point," but whether a hackathon team can get real integration access (vs. building to a CAP-compatible fallback format) is unverified — treat as unresolved the same way MOSDAC's access model is, and don't claim real integration in a demo unless it's confirmed.
- **Sentinel infrastructure cost at scale** — a background monitor per registered location is cheap for a pilot region's user base but the cost model needs revisiting before any claim of "national rollout ready" — flagged explicitly so it isn't discovered late.
- **Security/auth model for location and identity data** — named as an NFR in the master doc, not newly designed in this pass. Needs its own design pass before handling real user location data beyond the pilot demo.
- **Critic Agent latency-vs-value tradeoff for coastal_authority persona** — DEEP-depth authority queries (48h district briefs, escalation-adjacent) will now hit the critic loop; verify in practice that the 5-15s addition doesn't conflict with an authority user's own expectation of near-real-time response during an active hazard window — may need a persona-specific latency budget carve-out even though the trigger itself stays depth-based, not persona-based.

---

## 17. Changelog

**v4.0 (this document):**
- Backfilled Critic Agent from the alternate-lineage document, retargeted to trigger on `reasoning_depth == DEEP` rather than `persona == researcher` (§1 Principle 7, §3.2 Agent 10) — closes a quality-validation gap that affected any persona's diagnostic queries, not just researchers.
- Added Sentinel / Proactive Monitoring Agent (§3.2, Agent 11) — makes Sagar-Vani-style push alerting an actual architectural component instead of a reference note; closes gaps #4, #14, #15, #20, #22 from the use-case audit.
- Added Distress & Emergency Handoff Agent (§3.2, Agent 12) — closes the single most severe gap found in the audit (#23): neither prior document had any flow from "user signals an emergency" to "the right agency is notified," despite the master doc explicitly naming DAT-SG/Sagarmitra as the intended handoff point.
- Added `vessel_class` as a first-class `ORCAState` field and backfilled RAA's vessel-class threshold-delta table (§3.1, Agent 7) — closes gaps #6/#24.
- Added `score_pfz_persistence` tool to Ocean Analytics (§3.1, Agent 5) — closes gap #13, aligns with the master doc's own pilot-region rationale.
- Added two missing intent-routing rows: Export/download and Alert subscription (§4) — closes gaps #9 and #20.
- Added proactive/continuous boundary-proximity intent row, backed by Sentinel (§4, §8.9) — closes gap #14.
- Extended failure-mode contract: all-sources-down degraded rendering and conflicting-source disagreement handling (§12.2) — closes gaps #21/#25, neither specified in v3.
- Ran a full use-case coverage audit against the master requirements doc (§7) — 25 scenarios, 10 gaps found and fixed, 15 confirmed already-adequate.
- Added 19 concrete optimizations across latency, cost, reliability, scale, and observability (§9), each explicitly checked against a new Principle 10 (never trade safety-critical behavior for performance).
- Committed a concrete technology stack (§10), itemized visualization spec (§11), NFR traceability matrix (§13), and phased build plan (§15) — all backfilled from the alternate-lineage document or built fresh where neither document had sufficient detail.
- Carried forward all v3.0 open verification items (§16.1) and added five new residual risks specific to v4's additions (§16.2) rather than presenting the new agents as risk-free.

**v3.0 (superseded):** Added persona-inference confidence threshold with conservative-composite fallback; added persona-correction affordance; added LOW-DATA amber rendering across all personas; documented ingress STT path; added session-history-based follow-up resolution; added multi-match/no-match intent handling; escalated MOSDAC ambiguity to a Phase 0 blocker.

**v2.0 (superseded):** Fixed persona-as-hard-gate bug — routing made intent-driven and persona-blind; persona governs rendering + defaults only. Added `reasoning_depth`, `stakeholder_persona_source`. Corrected PFZ freshness. Flagged route optimization and MOSDAC ambiguity.

**v1.0 (superseded):** Initial 9-agent baseline, persona-execution-matrix routing (later found to be buggy), deterministic risk gating, JSON hand-off schema, failover hierarchy, latency budget.

---

*This is a living document. Update it, dated, in §17 whenever a design decision changes during build. If code and doc disagree, that's a bug in one of them — figure out which before building on top of it.*
