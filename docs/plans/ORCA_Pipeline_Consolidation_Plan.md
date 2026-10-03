# ORCA — Pipeline Consolidation Plan (audit part A: `distress → ingress → planning`)

Written 2026-10-03 after the first half of the agent audit. **No code has been
changed for anything in this document.** It records what the audit found, the
decisions taken with the user, and the work as numbered points that can be
picked up cold.

| | |
|---|---|
| **Serves** | `PS-C1` (understand intent), `PS-C3` (multi-turn), `PS-C4` (autonomous discovery), `PS-ARCH` (multi-agent) — see `docs/specs/ORCA_PS_SIH26176_Problem_Statement.md` |
| **Requirement IDs** | `R-PS-1`, `R-AGENT-2`, `R-NEW-1`, `R-EDGE-3` — see `docs/specs/ORCA_DLC_Extension_Pack.md` |
| **Extends** | `docs/plans/ORCA_Prompt_Routing_Revamp.md` §6. Where §6's target routing (separate UNDERSTAND and VALIDATE steps) disagrees with this file, **this file wins** |
| **Founding principle** | *Talk like a chatbot, stay accurate like an instrument.* (`CLAUDE.md`) |
| **Log** | Every point lands in `docs/logs/DLC_implementation_log.md` with a `PC` ID |
| **Audit status** | **Part A done (this file). Part B not yet audited** — see §8. Do not add Part B points until it is |

---

## 0. READ THIS BEFORE TOUCHING ANYTHING — one point at a time

The duplicate agents and the dead branches this plan removes came from landing
large amounts of work at once and checking it all at the end. This plan must
not be executed that way.

1. **One point per change set.** Claim it in the log (`CLAIMED`) first. Finish
   it. Run its **Done-when** test. Log it `DONE`. Only then claim the next.
2. **Never combine points**, even adjacent ones, even when "it's the same file".
   Two points in one diff is the failure this rule exists to prevent.
3. **No "while I'm here" cleanup.** Anything you notice outside the point goes in
   the log as a `NOTE`, not into the diff.
4. **Each point leaves the app working.** After every point the full chat path
   (`/ask`) must still answer, with the LLM up and with it down. A point that
   needs the next point to work is mis-sliced: stop and log `BLOCKED`.
5. **Phases are gates.** Do not start phase *n+1* until every point in *n* is
   `DONE` and the phase's exit gate has been run by a human.
6. **A human runs the Done-when.** Green unit tests are necessary, not
   sufficient: verify through the real `/ask` path (agent account in
   `CLAUDE.md`), not by calling a function.
7. **Touching a second node means stop.** If a point turns out to need a change
   in a node it does not name, log `BLOCKED` and ask — do not widen the point.
8. **No commits by agents.** Leave the work in the tree and the log updated; the
   user reviews and commits (`main`, no branches).

## 1. What the audit found (verified against the tree, 2026-10-03)

**F1 — `query_guard` is a node that is only a caller.** `graph.py:246`. Its three
checks are plain functions in `place_resolution.py` (`resolve_or_ask`,
`time_guard`, `position_guard`). The node adds no judgement of its own.

**F2 — `query_guard` runs before `understand`, so its Understand-based branches
are dead.** Edges (`graph.py:1336–1340`):
`START → distress_check → query_guard → language_ingress → understand → planning`.
The node reads `understood_kind`, `understood_places`, `understood_when`, which
`understand` has not written yet. In practice only the old fallbacks run: place
resolution done earlier by the API handler, and `time_guard` on raw-text regexes.
That is a word list making a decision before any model has read the prompt — the
exact pattern the Revamp set out to remove.

**F3 — `understand` and `planning` are two nodes for one job.** `understand` is
the LLM call; `planning` makes no LLM call and only maps `understood_intents`
onto `ROUTING_TABLE` (`planning.py:522`, ~125 lines, mostly fallback tiers). The
name "planning" currently overstates what it does.

**F4 — the "parallel routing" is not routing.** After `marine_data_discovery`
the fan-out to `weather_intelligence`, `geospatial`, `ocean_analytics` is
unconditional (`graph.py:1349–1360`, comment at 1349). The plan only gates work
*inside* `ocean_analytics_node`. This was deliberate and fail-safe (an all-of
join hangs if a branch is skipped), but it means the plan does not decide which
agents run.

**F5 — what is fine.** The frontend stage list (`ReasoningTimeline.tsx:20`)
already shows one "Planning & Intent" stage and no `query_guard` / `understand`
stage, so the UI needs no change when the nodes are merged (confirmed again in PC4.1).

## 2. Decisions (agreed with the user, 2026-10-03)

**D1 — One LLM call reads the prompt *and* plans.** The node keeps the name
**`planning`**. It is called through function-calling / structured output so the
result can be validated. It sees the last 5 turns, the live location, the current
clock and the data extent as context — the model is expected to handle typos,
plurals, shortenings and mixed language itself. Effort goes into its system
prompt, not into word lists.

**D2 — The checks stay, as pure functions, not as a node.** The model may not
enforce a limit it cannot know: the 7-day horizon (`FORECAST_HORIZON_DAYS`,
`place_resolution.py:113`), whether a coordinate is land (bathymetry grid), whether
a place exists (gazetteer). So after the model returns, code validates, with no
LLM: places → gazetteer/regions, `when` → horizon and past, user coordinates →
`position_guard`, intents → `ROUTING_TABLE`, agents → known specialists. A
failure ends the turn with the existing reply (`NEEDS_PLACE` / `OUT_OF_RANGE`).

**D3 — The model proposes the agent set; code enforces the invariants.**
- Unknown agent names are dropped.
- Dependency order is code's, not the model's (discovery → specialists in
  parallel → risk and visualization → reporting → critic → egress).
- *Provisional, to be confirmed in PC3.1:* `weather_intelligence`, `geospatial`
  and `risk_assessment` always run for a sea question, because the GO/CAUTION/NO_GO
  verdict is computed for every sea query from wave, wind, boundary, lightning and
  cyclone (`_CORE_DATA_TYPES`, `graph.py`). `reporting`, `critic`, `language_egress`
  always run. `ocean_analytics` and `visualization` are the candidates the model
  may skip.
- The verdict is never produced or altered by the model.

**D4 — `ROUTING_TABLE` is kept.** It becomes (a) the capability catalogue shown to
the model ("these are the agents, this is what each is for"), (b) the validation
set for intents, (c) the offline fallback when every model is down. The word
lists are not deleted by this plan (Revamp item 5 owns that).

**D5 — The name is `planning`, the mechanism is function calling.** Not
"reasoning": that word already means the reasoning tier / depth and the
`/reasoning` page. If asked whether planning is deterministic: *an LLM reads the
question and plans which agents run via function calling; deterministic code then
validates the plan and enforces the safety invariants.*

**D6 — LLM down means fall back, never refuse.** If no model answers, planning
uses the table and the old deterministic tiers, as today, and still answers.
Local models (Ollama) stay lowest priority in the chain.

**Target flow**

```
distress_check            (phrase list can only escalate; LLM escalate-only check)
  → language_ingress      (unchanged in this plan; audited in Part B)
  → planning              (LLM read+plan → code validate → route)
        ├─ NEEDS_PLACE / OUT_OF_RANGE / non-sea kinds → END (existing replies)
        └─ sea question → marine_data_discovery → [chosen specialists, parallel]
                          → risk_assessment / visualization → reporting → critic → language_egress
```

---

## 3. Phase PC0 — Baseline (nothing changes in the app)

**PC0.1 — Messy-prompt baseline file.**
- *Implements:* `R-EDGE-5` spirit; Revamp §7 item 6 (no such test file exists in `backend/tests/unit` today — confirm before creating).
- *Depends:* none.
- *Files:* new test data + test; no source change.
- *Required:* ~60 prompts, each with expected `kind`, intent row(s), place, date window, distress flag. Must include: "hi", "pfzs near ktaka", "pfz near gujurat", "wats time now", "engine failed near pamban", "day after tomorrow near kochi", "kochi on 2026-10-30" (beyond horizon), Tamil/Hindi samples, a follow-up ("and tomorrow?"), and one prompt per `PS-Q1`–`PS-Q8`.
- *Done-when:* the file runs against the **current** tree with the LLM disabled and reports a pass rate; the failures are recorded in the log as the baseline. Nothing is fixed here.

**PC0.2 — Baseline of cost and latency.**
- *Depends:* PC0.1. *Files:* none (log only).
- *Required:* for 5 of the prompts, record real LLM calls, wall time and `routing_tier` on the current tree, LLM up.
- *Done-when:* the numbers are in the log. This is what PC2.x must not regress.

**Exit gate PC0:** baseline recorded; user has seen the failing prompts.

## 4. Phase PC1 — Make the checks honest, without merging anything

**PC1.1 — Extract the validate step as one pure function.**
- *Implements:* `R-NEW-1`, `R-EDGE-3`. *Depends:* PC0.
- *Files:* `backend/orca/place_resolution.py` (or one new module), unit test. **Not** `graph.py`.
- *Now:* the same checks are spread across `query_guard_node` (`graph.py:246–304`) and the API handler.
- *Required:* `validate_reading(places, when, user_location, now) -> Outcome | None` that composes the existing `resolve_or_ask` / horizon / `position_guard` logic and returns the same outcome codes and the same wording. No behaviour change.
- *Done-when:* unit tests cover: unknown place → `NEEDS_PLACE`; `when` past and beyond horizon → `OUT_OF_RANGE`; land coordinate → disclosure; valid → `None`. Existing guard tests still pass untouched.
- *Not in scope:* touching the graph; deleting the node.

**PC1.2 — Run the guard after `understand`.**
- *Implements:* `R-NEW-1`. *Depends:* PC1.1.
- *Files:* `graph.py` edges and `query_guard_node` only.
- *Now:* `distress_check → query_guard → language_ingress → understand` (F2).
- *Required:* rewire to `distress_check → language_ingress → understand → query_guard → planning`; the node now calls `validate_reading` with the model's `places` / `when`. The deterministic `time_guard` stays only as the fallback when `understood_when` is empty because the model was down.
- *Done-when (through `/ask`):* with the LLM up, "safe near kochi on 2026-10-30" is refused as beyond the horizon **using the model's `when`**; "pfzs near rameshwaram" still answers; with the LLM disabled the same two prompts behave as in the PC0 baseline.
- *Not in scope:* merging nodes.

**Exit gate PC1:** PC0 baseline re-run; no prompt got worse; the Understand-based branches of `query_guard` are demonstrably live (a log line or trace span shows them used).

## 5. Phase PC2 — One planning node

**PC2.1 — Planning schema carries the agent set (recorded, not yet acted on).**
- *Implements:* `R-AGENT-2`, `PS-ARCH`. *Depends:* PC1.
- *Files:* `agents/understand.py` (schema, prompt, parse), `state.py`.
- *Required:* the structured output gains `agents` (a subset of the known specialists). It is validated against the known set and stored in state as `planned_agents`. **Routing is unchanged**: the graph still fans out to all three.
- *Done-when:* for the `PS-Q1`–`PS-Q8` prompts the trace shows a plausible `planned_agents`; hallucinated names are dropped; a prompt with the LLM down yields the table's agents. Verdict and answers unchanged.

**PC2.2 — Merge `understand` into `planning`.**
- *Implements:* `R-PS-1`, `PS-C1`. *Depends:* PC2.1.
- *Files:* `agents/planning.py`, `agents/understand.py`, `graph.py` (remove the `understand` node and its edge).
- *Now:* two nodes (F3). *Required:* `planning.run` makes the one LLM call (reusing `understand`'s prompt/parse/validate code), then does the table lookup. The offline fallback path is kept as is. `understand_node` and its graph edge are removed; its trace span is now `planning`'s.
- *Done-when:* the PC0 baseline pass rate is ≥ before; LLM-call count per turn is not higher than recorded in PC0.2; `/ask` works LLM-up and LLM-down; the reasoning page still renders the run.
- *Not in scope:* removing `query_guard`; changing routing.

**PC2.3 — Fold `query_guard` into planning's validate step.**
- *Implements:* `R-NEW-1`. *Depends:* PC2.2.
- *Files:* `graph.py`, `agents/planning.py`, `state.py` if needed.
- *Required:* planning calls `validate_reading` itself and sets `query_outcome`; the graph routes `NEEDS_PLACE` / `OUT_OF_RANGE` to END from planning. The `query_guard` node and its edges are deleted.
- *Done-when:* the PC1.2 prompts give identical replies; `graph.py` no longer defines `query_guard`; README / docs that name it are updated in PC4.2, not here.

**PC2.4 — System prompt pass for planning.**
- *Implements:* `R-PS-1`, `PS-C3`. *Depends:* PC2.3.
- *Files:* the planning prompt only.
- *Required:* the prompt is given the live clock, location, data extent, last 5 turns and the capability catalogue; it must handle greetings, clock/position, capability questions, resets, off-topic, typos, state shortforms, follow-ups, mixed language. Every miss found afterwards goes into the PC0 file, **never into a word list**.
- *Done-when:* the PC0 file's live run (real models) reports its pass rate; misses are listed in the log.

**Exit gate PC2:** the graph has no `understand` and no `query_guard`; PC0 baseline beaten or equal on every row; cost not higher.

## 6. Phase PC3 — The plan really routes the parallel agents

**PC3.1 — Decide what may be skipped (decision record, no code).**
- *Implements:* `R-AGENT-2`. *Depends:* PC2.
- *Required:* read `risk_assessment` and the graph's `_CORE_DATA_TYPES` and write down, in this file's §2 D3, which specialists the verdict genuinely needs for each intent. Confirm or change the provisional list.
- *Done-when:* the user signs off the list.

**PC3.2 — Spike: how to skip a branch without hanging the join.**
- *Depends:* PC3.1. *Files:* a throwaway test only.
- *Now:* the all-of join `add_edge([...], "risk_assessment")` waits for every branch (F4).
- *Required:* a minimal test that proves either (a) a skipped branch still emits a `skipped` result so joins fire (the existing `ocean_analytics` pattern), or (b) conditional edges / `Send` can fan out to a subset without hanging. Pick one and write it down.
- *Done-when:* the test passes for subsets of 1, 2 and 3 specialists. No production code changes.

**PC3.3 — Route the specialists from `planned_agents`.**
- *Depends:* PC3.2. *Files:* `graph.py` routing; specialist nodes only if (a) is chosen.
- *Required:* the chosen mechanism, with D3's invariants enforced **in code** after the model's plan is read: forced agents are added, unknown ones dropped, order is code's.
- *Done-when:* a conditions-only question does not run `ocean_analytics`; a PFZ question does; trace spans show what was skipped and why.

**PC3.4 — Invariant test.**
- *Depends:* PC3.3.
- *Required:* a test that feeds adversarial plans (empty, only `visualization`, hallucinated names, `risk_assessment` omitted) and asserts the verdict inputs are always produced and the verdict equals what the all-agents run gives for the same data.
- *Done-when:* passes; run once through `/ask` by a human for `PS-Q2`.

**Exit gate PC3:** the verdict is byte-identical to the all-agents run for the same inputs on every `PS-Q` prompt.

## 7. Phase PC4 — Surfaces and docs

**PC4.1 — Confirm the reasoning page.** `frontend/app/reasoning/ReasoningTimeline.tsx` (`PIPELINE_STAGES`) already shows "Planning & Intent"; verify a run renders with no missing or empty stage after PC2/PC3. Fix only if it does not.

**PC4.2 — Update the docs that name removed nodes.** `docs/specs/orca_pipeline_walkthrough.md`, `docs/specs/orca_final.md`, `README.md`, and the `query_guard` mention in `backend/orca/state.py`. Docs only; `docs/logs/` entries are never edited (append-only).

**PC4.3 — Update the plan's own status** in `docs/plans/ORCA_Prompt_Routing_Revamp.md` §6 to point at this file.

## 8. Part B — not yet audited (do not plan from this list)

The audit continues one agent at a time, and nothing below is a decision:
`language_ingress` (can a multilingual model read the prompt directly, leaving
translation for the reply side?), `marine_data_discovery`, `weather_intelligence`,
`geospatial`, `ocean_analytics`, `risk_assessment`, `visualization`, `reporting`,
`critic`, `language_egress`. Each gets the same questions: does it need to exist,
does it duplicate another, is a model or code the right tool.

## 9. Not covered by this plan

- Deleting the word lists or the 120 MB embedding model (Revamp item 5).
- The LLM key/chain cooldown (Revamp item 1) and the LLM-call counter (Revamp §8).
- Any change to the safety thresholds or the verdict logic.
