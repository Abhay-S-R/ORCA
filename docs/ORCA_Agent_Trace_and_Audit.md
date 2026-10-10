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
| 4 | **marine_data_discovery** | **yes, 2026-10-10** | 8 (5 + 3 found while fixing) | **A1 verified; A2 + A3 done (waiting for the user's check)**; A4-A6 pending | no |
| 5 | weather_intelligence | no | | | |
| 6 | geospatial | no | | | |
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
| A4 | Bind weather: wave and wind follow Agent 3's ladder (Open-Meteo, then the next rung Agent 3 names), not weather's own private cache order | to do |
| A5 | Bind SST/chlorophyll and PFZ: the headline source order comes from Agent 3 | to do |
| A6 | Decided vs used: every specialist reports `source_used` per data type; the span and the trace show "decided X, used X" and flag any difference | to do |

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
