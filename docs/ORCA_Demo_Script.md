# 🎬 ORCA — Demo Script

> **Companion to:** [`ORCA_Phase4_Plan.md`](./ORCA_Phase4_Plan.md) §7 · grounded in the parent plan's [Definition of Done](./ORCA_Implementation_Plan.md#11-definition-of-done) (11 scenarios) and the [Phase 3 acceptance test](./ORCA_Phase3_Plan.md#10-acceptance-test) (scenarios A–F), not written from scratch — every beat below is a capability that already exists in the codebase, named with the file/route that proves it.
>
> **Presenter's rule, carried from Ground Rule 3 and the parent doc's own closing line:** never claim a capability the product doesn't have. Where a step is `SIMULATED` (SMS dispatch) or `HISTORICAL OBSERVED` (the Gaja replay), say so out loud — the provenance banner is on screen either way, so the honest answer and the on-screen answer always match.

---

## Running order (≈12 minutes)

| # | Flow | Persona | Route(s) | Proves |
|---|---|---|---|---|
| 1 | Safety query, voice, Tamil | 🐟 fisherman | `/` | Definition of Done #1 |
| 2 | Same facts, researcher persona, zero re-query | 🔬 researcher | `/` (persona tap) | Definition of Done #2, differentiator 7 |
| 3 | Reasoning graph — live, then replayed | 🔬 researcher | `/reasoning` | Definition of Done #3 |
| 4 | **Distress handoff** (centrepiece) | 🐟 fisherman | any screen (persistent SOS) | Definition of Done #4 |
| 5 | Voyage through a hard boundary | 🚢 navigator | `/voyage` | Definition of Done #5 |
| 6 | **Proactive Sentinel alert** (centrepiece) | 🐟 fisherman | `/watches` | Definition of Done #6 |
| 7 | Cyclone Gaja historical replay | 🚨 authority | `GET /api/replay/gaja` | Definition of Done #7 |
| 8 | Network cable pulled | 🐟 fisherman | `/` | Definition of Done #8 |
| 9 | Register, watch, cross-user isolation | 🐟 fisherman | `/register`, `/watches` | Definition of Done #9 |
| 10 | Advisory feedback → full trace | 🔬 researcher | any answer card → `/reasoning` | Definition of Done #10 |
| — | Keyboard + screen reader pass | 🐟 fisherman | `/`, `/safety`, `/map` | Definition of Done #11 |

---

### 1 — Safety query, voice, Tamil (fisherman)

> "நாளை காலை தூத்துக்குடி அருகில் கடலுக்கு போவது பாதுகாப்பானதா?"

Hold the push-to-talk control on `/`. The waveform shows it is listening; the transcript appears for confirmation before it becomes a query (a mis-heard "safe" read as "save" is a safety incident, not a UX nit — this confirmation step is why). The verdict streams back — the GO/CAUTION/NO_GO badge populates **last**, never as a placeholder — and speaks in Tamil. **Say out loud:** which ASR/NMT rung produced it (Bhashini if the credential is live, `faster-whisper`/IndicTrans2 local otherwise) — the answer card names it either way, so the fallback is not hidden.

### 2 — Persona correction, zero re-query (researcher)

From the same answered card, tap "I'm a researcher." The same already-computed facts re-render as a structured report with citations and a CSV export — **open the network panel first and point at the empty space where a second `/query` call would be:** only `POST /render` fires. Every number on screen is byte-identical to the fisherman rendering a moment ago.

### 3 — Reasoning graph, live and replayed (researcher)

Ask a DEEP diagnostic query ("why has catch declined near Thoothukudi") with `/reasoning` open. Nodes light as spans open and close; the parallel weather/geospatial/ocean fan-out draws inside one group box; if the Critic fires, its re-invocation draws as the dashed loop edge back to Reporting. Click Agent 7 — the inspector reads **"deterministic — no LLM"** with full source provenance, which is Ground Rule 2 made visible rather than claimed. Then open the same `query_id` again from a fresh page load: the identical graph re-renders from Postgres, not from memory.

### 4 — Distress handoff (centrepiece)

Tap the floating SOS control — present on every screen, every persona, never in a menu (parent §4.2). It bypasses Reporting and every specialist agent entirely (`orca/graph/graph.py::distress_check_node`) and surfaces MRCC contact — phone, nationwide fallback, VHF channel — in under two seconds. **Say out loud:** the handoff is `SIMULATED` — no live DAT-SG/telephony integration exists — and the response text says so itself, not just this script.

### 5 — Voyage through a hard boundary (navigator)

On `/voyage`, plot a route from Thoothukudi toward Palk Bay that clips the Gulf of Mannar Marine National Park, 3 m draft, departing in 6 hours. The clipping segments render `BLOCKED` and the voyage verdict is `NO_GO` — **not** `CAUTION` — because the geofence is a hard constraint by construction (parent §4.6), not a judgement call. Point out that each segment's wave height was sampled at *that segment's own ETA*, not at departure — the waypoint table states every hazard in text, so the answer survives losing the map.

### 6 — Proactive Sentinel alert (centrepiece)

Pre-register a watch on `/watches` for a demo account's home port (a wave-height threshold, e.g. 2.5 m). Move the fixture forecast across that threshold — Sentinel's background loop fires **unprompted**, without the presenter asking a question: the notification lands in the feed, renders the exact Sagar-Vani SMS payload, labelled `SIMULATED`, and a watch badge appears on the map without a page reload. **Say out loud:** a second identical poll fires nothing — no-spam is a functional requirement, not an aspiration, and it's why the badge doesn't flicker.

### 7 — Cyclone Gaja historical replay

`GET /api/replay/gaja` (authority persona, presented as a district-ops "what would this have looked like" query). This is real IBTrACS best-track and real ERA5 wind/wave data for 12–18 Nov 2018, not a synthesized track — every frame banners `HISTORICAL OBSERVED (IMD/ERA5, Nov 2018)`. The hazard cascade is Agent 7's own unmodified `evaluate_marine_safety()` run against those historical fields, timestep by timestep — walk through the wind category climbing and the verdict flipping to `NO_GO` on **15–16 Nov 2018**, the storm's real landfall window near Vedaranyam. **Say out loud:** this demonstrates hazard alerting works outside cyclone season, using real history rather than an invented storm.

### 8 — Network cable pulled (fisherman)

Disconnect the demo machine's network (or block the upstream hosts) and re-ask the Scenario 1 query. Every source falls back to its cached rung; the verdict still renders, forced to **LOW-DATA amber regardless of what the cached numbers say**, with a plain statement that live data is unavailable. **Say out loud:** no number here was invented to fill the gap — that is Ground Rule 2 at its strongest.

### 9 — Register, watch, cross-user isolation (fisherman)

Register a new account and a vessel on `/register`, set a watch on a home port, and show the alert history is scoped to that account — a second demo account cannot see the first one's home port, vessel, or watch (an explicit 403, not a silently empty list).

### 10 — Advisory feedback → full trace (researcher)

On any advisory card, tap "Not accurate." The feedback joins by `query_id` to `audit_trace_log` — open `/reasoning` on that same `query_id` and show every agent, source and confidence tier that produced the flagged answer. That traceability, not the tap itself, is the feature.

### 11 — Accessibility pass

Unplug the mouse. Complete Ask and Safety keyboard-only, narrating focus order and the live-region announcements; run NVDA/VoiceOver over the same two flows. `axe-core` is zero-criticals in CI — mention it, don't re-run it live.

---

## If something breaks live

- **A live upstream is down for real (not simulated):** this *is* Scenario 8 — say so, and let the degraded-response contract carry the demo rather than restarting anything.
- **Bhashini is unreachable:** the local IndicTrans2/Whisper rung is the primary path already (parent risk register), not a fallback to apologize for.
- **The Gaja replay 404s:** means `data/cyclone_gaja/era5_gaja_20181112_20181118.nc` isn't on this machine — fall back to Scenario 3 (reasoning graph) and note the replay as environment-dependent, not broken.
