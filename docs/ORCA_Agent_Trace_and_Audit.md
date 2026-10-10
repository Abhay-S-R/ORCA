# ORCA: Agent Trace revamp and the audit of every agent

*Started 2026-10-10 on the user's direction. This is the main priority. **Update this file every time work is done on the trace or on an agent audit** (add a dated line under the agent's section and update the status table). The implementation log (`docs/logs/DLC_implementation_log.md`) still records each change; this file is the plan and the findings.*

## 1. The goal (the user's words, 2026-10-10)

Replace today's agent strip with a trace that reads like ChatGPT's and Claude's: a quiet line above the answer, "Worked for 33s", that opens into a plain, ordered account of what happened ("Searched 9 websites", "Fetched official contest data", "Prepared official links"). The same template for our multi-agent pipeline, professional and clean:

- "Finished distress check"
- "Routed to the planning agent", then the planning agent's trace as its own LLM reasoning
- "Planning agent calls <agent X>", "Parallel specialists run"
- the later agents, in order
- when the critic thinks something must run again: "Critic agent calls <agent X> again", then the re-run
- "Language egress", done.

## 2. The principle: the trace may only say what the backend really did

The UI draws what the backend reports. If an agent does something different from what its span says, the trace lies, and a clean trace that lies is worse than the messy one we have. So **audit first, then trace**: every agent is audited for what it really does, what it consumes, what it produces and whether the others obey it. Defects found are fixed (or recorded and decided) before the trace is drawn from them.

For each agent the audit answers:
1. What does it do, in one sentence a judge could repeat?
2. What does it consume, and from where?
3. What does it produce, and who reads it? (A producer nobody reads is decoration.)
4. Does the rest of the pipeline obey it where it claims to decide something?
5. What does its span say today, and is that true?
6. What must the trace say for it, and what does the backend still need to emit?

## 3. What the trace needs from the backend (to be designed after the audits)

Today the stream has one `agent_span` per node (name, status, engine, latency, inputs, outputs, skip reason). A readable trace needs, in addition (to confirm during the audits, nothing built yet):
- **who called whom** (planning chose these agents; the critic sent it back to reporting) as a field on the event, not inferred by the UI;
- **parallel groups** (the three specialists start together);
- **a short human sentence per step**, written by the agent (or by deterministic code), not assembled by the UI from raw fields;
- **the planner's reasoning in words** (today it returns JSON only: no rationale field);
- **the loop**: critic verdict, which agent it re-invoked, and why;
- **real timings** per step and for the whole run ("Worked for 33s");
- **honest labels**: which model or rule actually served each step (this is PC5.7's job for the language agents).

## 4. Status of the audit

| # | Agent (graph node) | Audited | Defects found | Fixed | Trace sentence designed |
|---|---|---|---|---|---|
| 1 | distress_check | no | | | |
| 2 | language_ingress (+ PC5.7 labels) | no | | | |
| 3 | planning (understand + validate + route) | no | | | |
| 4 | **marine_data_discovery** | **yes, 2026-10-10** | 8 (5 + 3 found while fixing) | **A1-A4 verified; A5, A6 done (waiting for the user's check)** | **yes (`trace_line`, backend)** |
| 5 | weather_intelligence | no | | | |
| 6 | **geospatial** | **yes, 2026-10-10** | 8 (G1-G8) | no (waiting for the user's decisions) | no |
| 7 | ocean_analytics | no | | | |
| 8 | risk_assessment | no | | | |
| 9 | visualization | no | | | |
| 10 | reporting | no | | | |
| 11 | critic (+ the facts-list parity problem) | no | | | |
| 12 | language_egress (+ PC5.7 labels) | no | | | |
| | control nodes: out_of_scope, planned_distress, critic_cancelled, critic_reinvoke | no | | | |

**PC5.7** (honest provenance labels) is not solved by the trace UI: it is the data side, what the ingress and egress spans say. It is done inside audits 2 and 12, before the trace is drawn.

## 5. Audit 4: marine_data_discovery (Agent 3), 2026-10-10

*Read from the code (`orca/agents/discovery.py`, `orca/graph/graph.py`) and checked by running the agent and by searching every consumer. Not yet exercised under failure conditions.*

### What it does
A **source-selection agent**. For each kind of data a question needs (a "data type"), it picks which of 29 catalogued sources to use, explains the choice, and checks that local files actually hold usable data.
- **Catalog:** `SOURCE_REGISTRY`, 29 sources (Open-Meteo, INCOIS PFZ/OSF/tide gauge, MOSDAC, CMEMS, Survey of India tide tables, NDMA SACHET, Damini lightning, EEZ/IMBL, ...), each with an authority tier and a typical freshness; 11 declared fallback cascades (Architecture §12.1).
- **Which data types:** always five (wave_height, wind_speed, boundary, lightning, cyclone); three more when ocean analytics is in the plan (pfz, tide, catch_statistics); plus extras per matched intent (e.g. SAFETY_CHECK adds tide and cyclone, CONDITIONS adds current_speed and sst).
- **How it picks:** rank by authority tier, then freshness; splice in the declared cascade; skip sources marked down or whose circuit breaker is open.
- **Arrival check:** only for data held on disk (PFZ advisories, tide tables, OSF points, boundary geometry): a probe that the file is non-empty and values are in a physical range. Live sources are reported `checked: false, "validated on fetch, not before it"`.
- **Output:** `source_selections` (per data type: chosen source, narrative, considered, fallback chain, arrival result, rejected rungs), `unusable_data_types`, `fell_through`, and a confidence (HIGH / MEDIUM when something fell to a fallback / LOW_DATA when a type has no usable source).

### How it passes data on
Two state fields: `discovery_sources` (a dict keyed by data type, "what did Agent 3 pick for wave_height?") and `discovery_data.source_selections` (what the card shows). Written once, before the specialists fan out.

### Do the parallel specialists obey it? **No.** It is advice and a citation layer, not a decision they follow.
Every reader of the decision, found by searching the whole backend:
- `ocean_analytics`: copies the pfz / tide / catch_statistics decisions into its own output with a `decided_by: marine_data_discovery` label. **Display only: which loader runs does not change.**
- `_attach_discovery` (graph.py): annotates the weather and geospatial *spans* with the decision. **Display only.**
- `api/main.py`: sends `source_selections` to the card. Display.
- `weather_intelligence`, `geospatial`, `risk_assessment`, `reporting`, `visualization`: **never read it.**
- `unusable_data_types`: written, **read by nobody**.

So each specialist chooses its own source by its own hard-coded rule: weather = live Open-Meteo, else its own cached nearest-port file; tide = Survey of India tables, else Stormglass (its own `down` list); sea-surface temperature and chlorophyll = INSAT / CMEMS / EOS-06 files, freshest wins (and, since NOTE-CHL, a list of its own); PFZ = its own loaders.

### Defects found
1. **The declared fallback is not the real fallback.** On 2026-10-09 an answer used "Open-Meteo Marine/Forecast API (cached tier1 fallback, port=gangolli) (192 h old)" while Agent 3 said "open_meteo_marine, primary, no fall-through". Agent 3's declared next rung is the INCOIS WW3 model; weather instead falls to its own old port cache. The trace would have said one thing and the answer used another.
2. **"Arrival ok" checks readability, not coverage.** Tide: Agent 3 says `soi_tide_tables` is valid ("137 tide events, heights within range") while the table ended 2026-10-07 and the answers say "tide table ends before the requested time". It does not check that the requested window is covered.
3. **Arrival ignores age.** PFZ: "6 PFZ advisory features on disk, ok" while the advisory is 8 days old and expired.
4. **SST: the pick is not what is used.** Agent 3 picks `mosdac_open_sst` and marks it "live, validated on fetch" although it is a local file; ocean analytics reads INSAT / CMEMS / the INCOIS model itself. Nobody validates on fetch.
5. **Selections nobody consumes.** `unusable_data_types`, and (not yet verified one by one) current_speed and catch_statistics.

**Not yet checked:** whether this agent's confidence feeds the final confidence tier; how it behaves when a primary actually fails (the cascade logic is unit-tested, a live failure is not).

### The decision this audit needs (the user's, in Part C of the checklist since 2026-10-09)
- **A. Make it binding (recommended).** Each specialist gets its source from Agent 3 (where there is a real choice: wave/wind source, tide source, SST/chlorophyll, PFZ), reports which it actually used, and the trace shows "decided: X, used: X" and flags any difference. The arrival check also tests coverage of the requested time and age. This is what makes "the planning agent calls X, discovery picks sources, the specialists run" true.
- **B. Keep it a citation layer.** Then it is not an agent that decides, the trace must not present it as one ("source catalog note"), and the specialists' real choices are what the trace shows.

Under both, defects 2 and 3 should be fixed (the arrival check must not say "ok" for data that cannot answer the question).

### What the trace should say for it (draft, after the decision)
"Chose data sources: wave and wind from Open-Meteo (live), tide from the Survey of India tables (ends 7 Oct: not covering tomorrow, falling back to Stormglass), fishing zones from INCOIS (8 days old)." One line, built from the real decisions, with the fall-through named.

### Decision (the user, 2026-10-10): **A, make it binding.** "A 100% marine data agent should have agency, not just citation: it passes the right data, and the specialists obey it."

### Three more defects found while building A1
6. **The PFZ probe read the wrong file.** It probed the cloud-cover *fallback* geojson (six undated front cells), not the INCOIS advisory rows the PFZ agent actually quotes. "6 PFZ features on disk, ok" said nothing about the advisory.
7. **The Stormglass tide rung was called "live, validated on fetch".** It is a cache on disk, and it is exactly what a station with no Survey of India rows falls back to (New Mangalore has none). It was never checked.
8. **One station's gap would have opened a global breaker.** A coverage failure (this station, this time) was counted as a failure of the whole source. And Agent 3 asked the circuit breaker about `open_meteo_marine`, an id nothing ever trips (weather trips `open_meteo`), so a source the specialists had given up on still looked healthy to it.

### Phases of A
| Phase | What | State |
|---|---|---|
| **A1** | Honest arrival: tide checked per station and per requested time; PFZ probe reads the real advisory and reports its age (`stale`, never rejected); Stormglass cache probed; coverage gaps do not trip the breaker; breaker aliases; the question's position and time handed to the probes | **DONE 2026-10-10**, waiting for the user's check |
| A2 | Make the catalog true: the real last-resort rung weather falls to (`open_meteo_port_cache`, with a probe: nearest port, distance, age) is in the catalog and the cascade; a `readable` flag so sources ORCA cannot read values from (MOSDAC registered NRT x3 = the same files as the open products, NASA = a granule listing, Bhuvan = a WMS manifest, ERDDAP = a closed archive, scatterometer wind = a map overlay) are never *chosen* | **DONE 2026-10-10**, waiting for the user's check |
| A3 | Bind tide: ocean_analytics takes its tide source from Agent 3 (`tide_down_from_decision` -> `predict_tides(down=...)`), reports `source_decided`, `source_used`, `obeyed` | **DONE 2026-10-10**, waiting for the user's check |
| A4 | Bind weather: wave, wind and lightning follow Agent 3: the catalog says what is really read (Damini unreadable, `open_meteo_lightning_proxy` added; WW3 is not weather's rung), weather skips the live attempt when Agent 3 names the cached rung, and its output carries `source_report` (decided / used / obeyed per data type); the cached label says how far the port is | **DONE 2026-10-10**, waiting for the user's check |
| A5 | Bind SST/chlorophyll and PFZ: Agent 3 probes the satellite grids (INSAT, EOS-06, CMEMS) for a cell AT THE POSITION and their age, settles sst and chlorophyll whenever the question asks, ocean's headline follows the decision (and reads the CoastWatch last rung only when decided), `source_report` decided / used / obeyed for sst, chlorophyll, pfz and tide | **DONE 2026-10-10**, waiting for the user's check |
| A6 | Decided vs used on the trace: every specialist (weather, ocean, geospatial) reports `source_report`; the run-level `source_check` is on the answer (lists, logs and says any difference); Agent 3's step carries `trace_line`, a plain sentence built from the real decisions | **DONE 2026-10-10 (backend half)**, waiting for the user's check; the trace UI itself is the next programme stage |

## 5b. Audit 6: geospatial (Agent 6), 2026-10-10

*Read from the code (`orca/agents/geospatial.py`, `graph.geospatial_run` / `geospatial_node`, every consumer) and checked by running the real boundary data. Not changed yet.*

### What it does
The **where-are-you-relative-to-lines-on-the-map** specialist. For the resolved position it answers four things, from files on disk (no network):
1. **How far to the nearest treaty boundary line** (`nearest_boundary_line`): the closest of the 24 India-and-another-state lines in the Marine Regions IMBL file (the 8 baseline / 200 NM lines are excluded: they are India's own limits, not something to cross), geodesic nautical miles, with the line's name, who it is between, the treaty and its date, and the bearing to it. Falls back to the Sri Lankan EEZ polygon edge only if that file is absent.
2. **Marine protected area:** is the position inside the "Gulf of Mannar Marine National Park" polygon (`check_boundary_proximity`).
3. **Seasonal fishing ban:** which coast (east/west, via the nearest Coast Guard station's parent MRCC), whether the uniform ban is in force today, and whether the position is beyond the 12 NM state-waters carve-out (`fishing_ban_status`, the dates read from the Department of Fisheries order via the refresh script).
4. Its own **confidence** (always MEDIUM: "geodesic distance to a coarse boundary, not independently verified") and **coverage** (always 2 of 2).

It also holds a toolbox the main pipeline does not reach: bathymetry depth and shallow hazard, point-in-polygon, zones within a radius, ocean-current and wind vectors, map layers (used by the map routes, the voyage planner and `place_resolution`'s on-land check).

### How the data routes
`geospatial_node` (always runs for a sea question: it is a core verdict input) writes `geospatial_data` = its outputs + a scored confidence. Readers, found by searching the backend:
- **risk_assessment:** `imbl_distance_nm` (<= 1 nm or `mpa_violation` -> CRITICAL_GEOFENCE / NO_GO; <= 3 nm -> CAUTION; unreadable -> CAUTION "missing"), `mpa_violation`. **This is where a geospatial defect becomes a safety verdict.**
- **reporting:** hands the narrator `imbl_distance_nm` ONLY when the question was about boundaries (ZONES_TO_AVOID) or the verdict is not GO, plus `mpa_violation`.
- **critic:** the same two as measured facts.
- **api/main:** `imbl_distance_nm`, `imbl_alert_level`, `mpa_violation`, `mpa_alert_level` into the answer's `hazard_breakdown`; `trace_routes` for the span summary; the fishing-ban regulatory disclosure is raised by the node itself.
- **channels/renderers (SMS / WhatsApp):** reads `hazard_breakdown`.
- visualization only checks that geospatial data exists. Discovery decides "boundary" for it (A6 report).

### Defects found (G1-G8)
| # | Severity | Defect | Evidence |
|---|---|---|---|
| **G1** | **safety / regulatory** | The MPA check covers ONE park. `_MPA_BOUNDARY = "Gulf of Mannar Marine National Park"`: of the 11 geofence-usable MPAs, a vessel inside any of the other 9 is not flagged (Adam's Bridge, Vankalai, Wedithalathive, Bar Reef, Sundarbans x2, Chilika, Thillai Vanam, Thane Creek). | Ran the agent's check at a point inside each usable MPA: flagged 2 of 11 (the park and "Mannar Valaiguda"). |
| **G2** | **regulatory** | The fishing-ban 12 NM carve-out uses the distance to the nearest EEZ edge as "distance from shore". Near the Sri Lanka line the nearest EEZ edge is the IMBL, not the coast, so a position 20-34 nm from land is treated as inside the carve-out and the ban is NOT disclosed. | Palk Strait / Gulf of Mannar sample: 20 of 84 sea points in the Indian EEZ had edge <= 12 nm but land > 12 nm (e.g. 8.60 N 79.10 E: edge 3.1 nm, land 27.6 nm). Only matters inside the ban windows (east coast 15 Apr - 14 Jun, west 1 Jun - 31 Jul). |
| **G3** | display / consistency | Two different band tables: geospatial labels DANGER <= 1 nm, CAUTION <= 5 nm, else CLEAR; the verdict is NO_GO <= 1, CAUTION <= 3, else GO. At 4 nm the label says CAUTION while the verdict says GO. | `evaluate_marine_safety` at 2/4/6 nm vs `_alert_level`. |
| **G4** | bug (SMS / WhatsApp) | The channel renderer tests `imbl_alert_level not in (None, "SAFE")`, geospatial emits "CLEAR". Every GO summary with a clear boundary names "IMBL boundary clear" as the hazard instead of "no active hazard". | `_verdict_and_hazard({GO, CLEAR})` -> `('GO', 'IMBL boundary clear')`. |
| **G5** | provenance | The IMBL number cites the boundary vintage 2026-08-30 (the polygon files), but it comes from the treaty-lines file (timestamp 2026-09-16). Agent 3 decides "boundary" = `unep_wcmc_wdpa` (the protected-area file) while the IMBL number is from Marine Regions: the trace line would say "boundaries from UNEP-WCMC WDPA" for a Marine Regions number. | `boundary_data_vintage()` vs the lines file's `timeStamp`; the A6 decision for `boundary`. |
| **G6** | functionality | ZONES_TO_AVOID ("zones to avoid near X") gets only the IMBL distance and the one-park flag. `spatial_query_zones` (zones within a radius) was built for it and is not wired (at Malpe it would return only the EEZ). The bearing to the line, the treaty and its date are computed and dropped, so the answer cannot say which direction the line is. | `spatial_query_zones(13.35, 74.66, 50)`; `geospatial_run` outputs. |
| **G7** | built, unreached | Depth and shallow hazard (`depth_at_point`, `SHALLOW_HAZARD_THRESHOLD_M` = 10 m) are not in the agent's output; only the voyage planner and the on-land check use them. A question about shallow water gets nothing from this agent. | grep of consumers. |
| **G8** | low | Confidence is always MEDIUM and coverage always 2 of 2, whatever was available (e.g. the ban order missing, or the Sri Lankan-EEZ proxy used far from Palk Bay). | `geospatial_run`. |

### What needs the user's decision (G1) and what I can just fix
- **G1 is a legal judgement, not a code fix.** Some of those 9 are Sri Lankan (Adam's Bridge, Vankalai, Wedithalathive, Bar Reef: crossing the IMBL is the larger issue), some are lakes, creeks or reserve forests where fishing is permitted with a permit (Chilika, Thane Creek, Sundarban Reserve Forest). Treating every one as NO_GO could be wrong. Recommended: keep NO_GO for the Gulf of Mannar park (as today), and for every other usable MPA add a REGULATORY disclosure (never a verdict change, like the fishing ban), naming the park; the user (or a fisheries expert) confirms which are hard NO_GO.
- **G2, G3, G4, G5, G6 (zones, bearing), G8:** deterministic fixes with no policy question. G3 needs one choice: use the verdict's 3 nm as the CAUTION edge in the label (recommended, so the label and the verdict agree).
- **G7:** a feature decision (do shallow-water questions belong to this agent?).

## 6. Order of work (proposal, the user decides)
1. Audit 4 decision (A or B), then fix defects 1-5.
2. Audit 2 and 12 (ingress, egress) with PC5.7: honest language labels.
3. Audit the specialists 5, 6, 7 against Agent 3, then 8 (risk), 9, 10, 11 (critic facts parity), 3 (planning), 1.
4. Design the trace event model from what the audits show is true.
5. Build the trace UI (the "Worked for Ns" line and its expansion) on top of the real events.

## 7. Log of work on this file
- 2026-10-10: file created from the user's direction; audit 4 (marine_data_discovery) written.
- 2026-10-10: the user chose A (binding). **Phase A1 built** (`discovery.py`, `graph.marine_data_discovery_run`; 15 tests `test_discovery_arrival_honesty.py`; full gate green): New Mangalore (no Survey of India rows) now falls to the Stormglass cache; a request past 16 Oct is reported "no usable source for tide" instead of "valid"; the PFZ arrival line now reads "newest valid for 2026-10-10, 0 day(s) old, current" (an 8-day-old advisory shows stale and is kept). Also answered: Agent 3's confidence does NOT feed the final confidence tier (no reader in the reporting, risk or confidence code). Until A3-A5 the specialists still choose their own sources, so a decision and a use can differ (A6 will show it).
- 2026-10-10: **A1 verified by the user.** **A2 and A3 built.** A2: `DataSource.readable` / `why_not_readable` (6 sources declared unreadable, each with its reason); `open_meteo_port_cache` added as the real last rung (cascade `open_meteo_marine -> incois_osf_ww3 -> open_meteo_port_cache`, replacing the wrong `stormglass_tides`); a probe for it (nearest port within 300 km, its age; 24 h = stale); Agent 3 never chooses an unreadable source and says when the primary cannot serve values. A3: ocean's tide takes Agent 3's rung; the output carries `source_decided` / `source_used` / `obeyed`. Live (real model): Kochi -> Survey of India, decided = used; New Mangalore -> Stormglass cache with the SOI reason, decided = used; Tuticorin tomorrow -> Survey of India, decided = used. Two pinned tests encoded the old defect (NASA as chlorophyll fallback) and were updated. Full CI gate green except the 2 known friend tests. A4 (weather obeys) is next.
- 2026-10-10: **A2 + A3 verified by the user. A4 built.** Defects found while building it: (9) Agent 3 chose "IMD Damini" for lightning while no Damini feed exists and the answer used Open-Meteo's CAPE-derived proxy (decision named a source never read): `damini_lightning` declared unreadable, `open_meteo_lightning_proxy` added; (10) Agent 3 declared INCOIS WW3 as the wave fallback but weather has no reader for it as a weather frame: removed from the open_meteo_marine cascade (WW3 stays a ranked wave source and ocean_analytics still reads it as an extra point forecast). Weather: `get_marine_weather(skip_live=...)` (Agent 3's cached decision, used when the breaker is open, avoids a 3 s wait), `source_used` / `port` / `port_km`, the cached dataset label now reads "cached tier1 fallback, port=kochi, 4 km away", the lightning nowcast names its source, and `source_report` per data type with `obeyed` (True when used = decided or a later rung of the declared cascade; False when something else; None when no decision was in state). Live: Kochi and Mangalore questions: decided = used = obeyed for wave, wind, lightning. The cached-rung path is covered by tests, not exercised live (the breaker was closed). 12 tests (`test_discovery_weather_binding.py`); CI gate green except the 2 known friend tests. **Not done:** cyclone (NDMA SACHET) and the IMD nowcast are not yet in the report; the verdict inputs and weather's own cache-order safety behaviour are unchanged on purpose.
- 2026-10-10: **A4 verified by the user. A5 built.** Defects found: (11) the satellite grids (INSAT SST, EOS-06 and CMEMS chlorophyll/SST) were "live source, validated on fetch" although they are files: Agent 3's pick said nothing about whether the place had a reading or how old the granule was; (12) chlorophyll was only settled by Agent 3 for the DIAGNOSTIC row, so a plain "SST and chlorophyll" question had no chlorophyll decision at all; (13) ocean chose the national product as the headline by a constant. Now: `_grid_probe` (cell within 60 km of the position, its distance, observed date, age; stale after 3 days; a missing cell is a coverage gap, not a breaker failure); `source_report_entry` shared by weather and ocean; `ocean_analytics.grid_reading`, readings carry `source_id`, `point_readings(..., decided)` follows the decision (a decided source with no cell leaves the default headline, never nothing); Agent 3 settles sst + chlorophyll whenever `_asks_sea_colour`; the declared live last rung (NOAA CoastWatch) is read only when Agent 3 decided it; a probe may now decline (None = "unchecked", never a quiet ok) for data types it has nothing to say about. Live: "sst and chlorophyll for udupi": INSAT cell 1.5 km away (observed 9 Oct, 1.5 d old), EOS-06 cell 13.6 km away; ocean decided = used = obeyed for sst, chlorophyll, pfz and tide; "nearest fishing zone near malpe": PFZ decided = used. 18 tests (`test_discovery_colour_pfz_binding.py`); CI gate green except the 2 known friend tests. **Not done:** the regional SST-vs-chlorophyll correlation (`_sst_grid`/`_chl_grid`, freshest-wins) still picks its own grids; catch_statistics, cyclone and the IMD nowcast are not in the reports; A6 (the trace line) next.
- 2026-10-10: **A6 built (backend half).** `discovery.source_report_entry` accepts a list of used sources (geospatial really reads the treaty lines AND the protected-area file for "boundary"); `discovery.source_check` aggregates the specialists' reports into `{checked, obeyed, mismatches, unknown, line}` (a mismatch is listed, logged at WARNING and said; an entry with no decision is `unknown`, never counted as obeyed); `discovery.discovery_trace_line` writes the plain sentence for Agent 3's step from the real decisions (data types that share a source are grouped; a fall down the cascade and not-current data are said; types with no usable source are named); the discovery span's outputs carry `trace_line`; geospatial's outputs carry `source_report` (boundary, plus eez / mpa / fishing_ban when decided); `final_response` carries `source_check`. Live: "tide times at mangalore please": the step line reads "... tides from Stormglass.io Marine API (fell back: no Survey of India rows for station NMP) ..." and `source_check` = 6 of 6 obeyed, no mismatches; "sst and chlorophyll at karwar": 8 of 8. 16 tests; CI gate green except the 2 known friend tests. **Observation for the UI stage:** the line lists every data type Agent 3 settled for the plan (7 to 9 sources for a simple question) because the specialists need them all; the trace should show a short headline with the full line one click away. **Audit 4 is now complete in code** (A1-A6); what remains is the verification by the user and the cross-check of defect fixes against live failure conditions (a live primary failure, which has not been exercised). Next audit in the order: 2 and 12 (ingress, egress) with PC5.7.
- 2026-10-10: **A5 and A6 verified by the user. Audit 4 closed. Audit 6 (geospatial) written** (defects G1-G8, no code changed): see section 5b.
