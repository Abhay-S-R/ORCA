# ORCA — Demo Camera Script (P4.0)

> **What this is.** The recording's shot list: every surface on screen, every line of narration,
> and how long each surface holds. `docs/specs/orca_final.md` §29 describes the *scenarios and tour
> beats* (the what); this is the *how* — the actual 3–5 minute cut. It is the input P4.10's
> refinement pass ranks against, and the input every deck slide about the product is built to
> match. Total runtime target: **4:30**. Five surfaces carry the video; the other ten routes in
> §19's table are not filmed and are frozen for this recording per P4.10.

**Surfaces ranked by seconds on camera** (drives P4.10's refinement order — polish top to bottom,
stop when the ranked list runs out):

| Rank | Surface | Seconds on camera |
|---|---|---|
| 1 | `/ask` (verdict card, agent trace, citations, LLM-off toggle) | 100 s |
| 2 | `/demo` — Scenario 2, IMBL border-crossing | 70 s |
| 3 | `/reasoning` (graph on the border-crossing `query_id`) | 30 s |
| 4 | `/ask` (fisherman) vs `/ops` (authority) side-by-side | 30 s |
| 5 | `/demo` — Scenario 3, Cyclone Gaja replay | 30 s |
| — | `/` landing (cold open only) | 20 s |

Every number spoken in narration must be read live off the running app at recording time, never
typed into the script from memory — P0.14's rule applies to this document too.

---

## Shot list

| # | Elapsed | Surface | On screen | Narration |
|---|---|---|---|---|
| 1 | 0:00–0:20 | `/` | Landing page: thesis line, live conditions strip, persona chooser | *"ORCA is decision support for someone deciding whether to go to sea — built on ISRO and INCOIS data, reasoned over, not re-invented."* Click into the fisherman persona. |
| 2 | 0:20–0:55 | `/ask` | Composer, question typed: *"Is it safe to go out tomorrow morning near Rameswaram?"* Agent-trace strip streams span by span — name, engine tag, elapsed ms. | *"Watch the system think — five of eleven graph nodes call no model at all, and every node that can stop someone going to sea is one of them."* Point out `Deterministic` on Risk Assessment and Geospatial as they land. |
| 3 | 0:55–1:20 | `/ask` | Verdict card resolves: GO badge, confidence tier expanded to its derivation chain, a citation opened (source, acquisition time, freshness, provenance badge). | *"The verdict, the confidence, and the reason for the confidence — every number here traces to a measurement in two clicks."* |
| 4 | 1:20–1:40 | `/ask` | Toggle `ORCA_LLM_ENABLED=0`, re-run the identical question. | *"Now the LLM is off entirely."* Verdict re-renders bit-identical; only the prose narration drops to the deterministic template line. *"Same verdict. The model was never load-bearing."* (Proof argument 2, §29.3.) |
| 5 | 1:40–2:15 | `/demo` → Scenario 2 | Beats 1–3 (§7.2): GO departure, the 12 nm advisory chip, the 6 nm Tamil voice notice, boundary polygon pulse. | *"A fishing vessel bound for Palk Bay. The line it's approaching isn't drawn on any chart the crew carries."* |
| 6 | 2:15–2:40 | `/demo` → Scenario 2 | Beats 4–5: CAUTION at 3 nm with the rendered Tamil SMS payload marked `SIMULATED`; NO-GO takeover at 0.9 nm, reciprocal heading, SOS visible throughout. | *"Computed, not scripted — `imbl_distance_nm = 2.8` drives this the same way it would drive a live query."* |
| 7 | 2:40–2:50 | `/demo` → Scenario 2 | Beat 7: presenter pulls the network cable; the next band still fires. | *"No connectivity at all — which is the condition this actually has to work under."* |
| 8 | 2:50–3:20 | `/reasoning` | Graph for that exact `query_id`: node engine tags, `Deterministic` on Geospatial and Risk Assessment, the MEDIUM confidence cap on the IMBL proxy with its derivation one click away. | *"The verdict was arithmetic, and this is the trace that proves it — not a claim, a replayable computation."* |
| 9 | 3:20–3:50 | `/ask` (fisherman) split-screen `/ops` (authority) | Same account family, two personas: fisherman's voice-first single-pin layout beside the authority's sector threat matrix and CAP composer. | *"Same product, four personas — switch persona and the entire screen changes, not just a filter."* (Phase 4 exit gate.) |
| 10 | 3:50–4:20 | `/demo` → Scenario 3 (Gaja replay) | Verdict timeline GO → CAUTION → NO-GO across the 2018 window; the `CAUTION_MISSING_DATA` hour at Thoothukudi rendered as missing, not smoothed; counterfactual hours-of-warning panel. | *"November 2018, real IMD and ERA5 records. Where the data itself was missing, ORCA says so instead of guessing — that's the most honest moment in this whole demo."* |
| 11 | 4:20–4:30 | Closing card | P6.1's accuracy number, P6.2's cost-per-query, one differentiation line. | *"[accuracy]% recall against INCOIS's own small-vessel advisory, at ₹[cost] per query, because the safety path costs nothing to run."* |

---

## What is deliberately not filmed

Per P4.10, every route not in the ranked list above is **frozen** for this recording:
`/profile`, `/zones`, `/voyage`, `/trends`, `/data`, `/watches`, `/alerts`, `/map` (full-screen),
`/login`/`/register`. They may appear as rehearsed-answer fallbacks (§29.4) if a judge asks a
question live, but no shot budgets time for them.

## Owner and status

**Owner: Dev A** per the plan's own assignment (P4.0, §7). Drafted by Claude (Sonnet 5) against
`docs/specs/orca_final.md` §7.2, §29.1–§29.4 and the Phase 4 exit gate, for Dev A to rehearse against
and amend — the ranked list and shot timings are a first cut, not a locked recording order.
