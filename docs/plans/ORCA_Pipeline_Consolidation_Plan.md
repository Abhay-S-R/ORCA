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
| **Audit status** | **NOT DONE — the agent audit is paused part-way (2026-10-04).** Any developer may continue it; an AI agent only when the user prompts it to. What has been looked at so far is recorded below and in §9 as findings, not as a finished audit. Do not add points for an agent that is not yet audited |

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

### Language ingress decisions (agreed with the user, 2026-10-04)

Evidence for all of these is Appendix A, measured against the live services on
2026-10-04. Text input only; voice input is discussed separately and is not
covered here.

**D7 — Three kinds of text input, three paths.** Script detection stays; it is
exact and costs nothing (`detect_language`, `language.py:80`).
- **Native script** (Tamil, Devanagari, …): `language_ingress` translates to
  English with the specialised models, Bhashini NMT first, IndicTrans2 local as
  the existing offline rung. Measured to translate correctly. Unchanged.
- **Latin-only text** (English, English with typos or shortforms, and romanized
  Indic such as "kal subah samudra jaana safe hai kya"): **not translated and not
  language-detected by ingress.** It is passed to `planning` exactly as typed, and
  the planning LLM reads it and returns the English reading.
- **Mixed native + Latin text:** **deferred.** It takes the native-script path
  today and comes back half-translated (Appendix A.3). Not fixed by this plan;
  needs its own design.

**D8 — Why Latin-only text is not machine-translated.** Both specialised
approaches fail on it, measured:
- Bhashini language detection mislabels short typed English as another language
  (12 of 20 prompts, e.g. "kochi weather" → Malayalam 1.00, "fish off tn coast" →
  Odia 0.99); its confidence score does not separate right from wrong, and it
  returned HTTP 500 on 5 of 20 ordinary prompts, including "engine failed near
  pamban".
- Always transliterating then translating damages English: "pfz near ktaka tmrw"
  → "PFJ Near Cuttack TMRV"; "fish off tn coast" → "Fish of Teen Coast".
- Bhashini translating romanized text directly returns it unchanged (a silent
  failure that today is reported as success). With a transliteration step first it
  works (17/24), but only if the language is known, which detection cannot supply.
- Gemini read all 24 romanized Hindi/Tamil/Kannada prompts correctly (24/24) and
  left English alone. Groq `gpt-oss-120b` scored 17/24 and Groq `qwen3.8-27b`
  10/24, with fabricated meanings (Appendix A.2).

**D9 — The 36-word English gate is removed.** `_COMMON_ENGLISH_WORDS` and
`_low_english_coverage` (`language.py:107–119`) decide whether Latin text goes to
the language detector. With D7 there is no such decision, so both go, together with
the Latin-text branch of `detect_language_with_bhashini`. The deterministic script
detector is not a word list and stays.

**D10 — Validation is the safety net, and it has a known limit.** What the
planning LLM reads out of Latin text is validated in code (D2), not trusted:
- **Places** must exist in the gazetteer or region set; a misread such as
  "Carver's" or "Chandamaruta" fails the check and the user is asked which place
  they mean.
- **Dates** are checked against the forecast horizon, **intents** against
  `ROUTING_TABLE`, **agents** against the known set.
- **Limit:** validation does not catch a wrong *meaning* with a valid place and
  date, e.g. "safest route" read as "shortest route", or "engine stopped" read as
  "caught fire" (both occurred in the Groq runs, Appendix A.2). This is the reason
  for D11 and for open question OPEN-2.

**D11 — Reply language (OPEN-1 answered 2026-10-04).** *Answered this while sleepy, subject to change but for now it works fine.* Native-script input is
answered in the language of its script, as today. **Latin-only input, including
romanized Hindi/Tamil/Kannada, is answered in English.** So no language label is
needed for Latin text: `query_language` returns `en` for it and egress passes the
English reply through. This removes the need for a `reply_language` field. The
planning call instead returns `english_reading` (the English rendering of what the
user typed), used only for display (D12), never for routing or place lookup.

**D12 — The reading is shown back (OPEN-2 answered yes, 2026-10-04).** *Answered this while sleepy, subject to change but for now it works fine.* For Latin-only
input that is not already English, the answer card shows "I understood: <English
reading>" so a misreading (D10's known limit) is visible to the user.

**D13 — Groq fallback model (OPEN-3 answered 2026-10-04).** *Answered this while sleepy, subject to change but for now it works fine.* When Gemini is
unavailable the Groq rung uses `openai/gpt-oss-120b`, **not** `qwen/qwen3.8-27b`
(Appendix A.2: 17/24 vs 10/24, and qwen invented an emergency). That is already
the chain's Groq model (`orca/llm/tiers.py`, `_GROQ_MODEL`), so no change is made
for it. Its measured weakness on romanized text is accepted, mitigated by D10
validation and D12. Re-run Appendix A.2 before reordering the chain or changing
that model.

**Open questions:** OPEN-1, OPEN-2 and OPEN-3 were answered on 2026-10-04 (D11, D12, D13). *Answered this while sleepy, subject to change but for now it works fine.* Treat them as the working answer; revisit if the user says so.

**Target flow**

```
distress_check            (phrase list can only escalate; LLM escalate-only check)
  → language_ingress      (native script → Bhashini, IndicTrans2 fallback → English;
                           Latin-only text passes through untouched — D7)
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
- *Required:* ~60 prompts, each with expected `kind`, intent row(s), place, date window, distress flag. Must include the 24 romanized prompts and 6 English controls of Appendix A, and: "hi", "pfzs near ktaka", "pfz near gujurat", "wats time now", "engine failed near pamban", "day after tomorrow near kochi", "kochi on 2026-10-30" (beyond horizon), Tamil/Hindi samples, a follow-up ("and tomorrow?"), and one prompt per `PS-Q1`–`PS-Q8`.
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

## 8. Phase PC5 — Language ingress (text input)

Starts only after the PC2 exit gate: these points need the merged planning node
and its prompt. Same rules as §0, in particular **one point per change set**.

**PC5.1 — Decision record: reply language for romanized input (OPEN-1). DONE 2026-10-04** — answered in English; recorded as D11 (*answered this while sleepy, subject to change but for now it works fine*). No code, nothing to implement.

**PC5.2 — Planning returns `english_reading`. DONE 2026-10-06** (log: PC5.2).
- *Implements:* `PS-C1`, `PS-C10`. *Depends:* PC2.2.
- *Files:* the planning schema, prompt and parse (`agents/planning.py`), `state.py`.
- *Required:* the structured output gains `english_reading` (a short English rendering of the user's message). Stored in state, **display only**: never used for routing, place lookup or validation, so a wrong reading cannot move the verdict. Not yet shown anywhere.
- *Done-when:* on the Appendix A prompts the trace shows a sensible English reading for each romanized prompt and, for English prompts, the prompt itself; `/ask` behaviour unchanged.

**PC5.3 — Latin-only text skips detection and translation. DONE 2026-10-06** (log: PC5.3; also added narrative rule 12, English whatever the user typed).
- *Implements:* `PS-C1`, `PS-C2`. *Depends:* PC5.2.
- *Files:* `agents/language.py` (`query_language`, `english_query`, remove `_COMMON_ENGLISH_WORDS`, `_low_english_coverage` and the Latin branch of `detect_language_with_bhashini`), and the one call site in `api/main.py:1146–1151`.
- *Now:* Latin text can be sent to Bhashini language detection and translation (Appendix A.1, A.3).
- *Required:* text with no native-script codepoint is returned as typed with rung `passthrough`; no Bhashini detection or NMT call is made for it. Native-script behaviour is untouched.
- *Done-when (through `/ask`):* "pfzs near rameshwaram" is answered in English and its trace shows no Bhashini call; "kal subah rameswaram ke paas samudra mein jaana safe hai kya" reaches planning as typed and is understood (Rameswaram, tomorrow, safety); a Tamil-script question still translates through Bhashini.
- *Required, also:* `query_language` returns `en` for Latin-only text, so egress replies in English (D11); a signed-in user's saved language is used only when the message is empty (the SOS control), as today.

**PC5.4 — REMOVED 2026-10-04.** It was "egress uses `reply_language`"; D11 (reply in English) makes it unnecessary and PC5.3 covers the `en` result. The ID is kept so numbering stays stable.

**PC5.5 — Show the reading back (D12).**
- *Implements:* `PS-C10`. *Depends:* PC5.2, PC5.3. *Files:* answer card / reporting, and its i18n strings (all nine dictionaries; `npm run check:i18n` must stay at zero).
- *Required:* for Latin-only input whose reading differs from what was typed, the card shows "I understood: <english_reading>". Nothing extra for input that was already English.
- *Done-when:* a romanized Hindi prompt shows its English reading; "pfzs near rameshwaram" shows nothing extra; the line renders in all nine UI languages.

**PC5.6 — Verify, do not assume: romanized distress and the gazetteer check.**
- *Implements:* `PS-C7`, `R-NEW-1`. *Depends:* PC5.3. *Files:* tests only, unless a gap is found.
- *Required:* (a) romanized distress phrases ("engine nindruduchu udhavi venum", "naav ka engine kharab ho gaya, madad chahiye") are raised by the distress check **before** ingress; (b) the romanized place prompts from Appendix A produce a valid place or a "which place?" question, never the pilot default and never a wrong place.
- *Done-when:* the cases pass, or each failing case is logged as a `NOTE` and fixed as its **own** point. Do not fix a distress gap inside this point.

**PC5.7 — Honest provenance on the native-script path.**
- *Implements:* `R-CLAIM-1` spirit. *Depends:* PC5.3. *Files:* `agents/language.py` only.
- *Now:* an English passthrough span is labelled "IndicTrans2 (local …)" (`language.py:397–398`); a translation that returns the input unchanged is reported as `ok` (Appendix A.1).
- *Required:* the passthrough span says no model ran; native-script output that equals its input is `degraded`. The module docstring's "Bhashini slots in later" text is corrected to say Bhashini is the primary rung.
- *Done-when:* the reasoning page shows "no translation" for English and Latin input and the model that served for native script.

**Exit gate PC5:** the Appendix A set, run live, reads at least as well as the 24/24 measured with Gemini; Latin-only input always gets an English reply; native-script behaviour is identical to before PC5.

## 9. Part B — audit of the remaining agents: NOT DONE

**Status: not done.** Anyone may pick this up (a developer freely; an AI agent only
when the user prompts it). Audit **one agent at a time**, as with everything here, and
for each ask: does it need to exist, does it duplicate another, is a model or code the
right tool. Record the decision in §2 before writing points.

| Agent | Audit status |
|---|---|
| `distress_check`, `query_guard`, `understand`, `planning` | Looked at (Part A, §1–§2). Not formally closed |
| `language_ingress` | Looked at, decisions D7–D13 (answers subject to change, see above). Not formally closed |
| `marine_data_discovery` | **Not decided.** Findings only, below |
| `language_egress` | **Not decided.** Findings only, below |
| `weather_intelligence`, `geospatial`, `ocean_analytics`, `risk_assessment`, `visualization`, `reporting`, `critic` | Not started |

**Findings so far, not decisions** (read from the code on 2026-10-04, none run live):

*`marine_data_discovery`* (`agents/discovery.py`, node at `graph.py:453`)
- No LLM. Ranks a 29-source catalogue by authority tier then declared freshness, follows the declared fallback cascades, validates arrival for the 6 sources held on disk (live APIs are reported "unverified"), and writes a one-sentence reason per pick that the answer card and `/data` page show.
- **The decision is not binding.** `weather_intelligence`, `geospatial` and `risk_assessment` never read `discovery_sources`; `ocean_analytics` copies it into its output. The specialists keep their own fetch logic, so Discovery decides which source is *cited*, not which is *read* (`graph.py:_attach_discovery` only records the hand-off on the span).
- Freshness is a hard-coded per-source number in the catalogue, not measured at query time.
- Not checked: how many of the 29 catalogue sources the specialists really fetch.
- The catalogue and picker are also used outside the graph (`api/discovery_routes.py`, `api/analytics_routes.py`), so the module has value even if the node is thin.
- **Question to put to the user:** should the decision become binding (specialists fetch what Discovery chose), or stay an honest source-citation layer and be labelled that way? Opinion given: keep it (`PS-ARCH`, `PS-C4`), keep it deterministic, do not make it an LLM.

*`language_egress`* (`agents/language.py`, `run_egress`)
- No LLM. Translates the finished English answer to the user's language, Bhashini then IndicTrans2, after masking numbers, units, GO/NO-GO, PFZ, IMBL and sector codes behind placeholders, then restoring them.
- **Nothing verifies that every placeholder came back.** Unmasking is a plain string replace, so a placeholder the translator drops silently deletes that number from the user's answer.
- After D11 it serves native-script users only (romanized input is answered in English).
- IndicTrans2 could not be run on the Windows dev machine, so the local rung is unmeasured.

## 10. Not covered by this plan

- Deleting the word lists or the 120 MB embedding model (Revamp item 5). The one exception is the 36-word English gate in `language.py`, removed by PC5.3 (D9).
- **Mixed native + Latin text** (D7): deferred, needs its own design.
- **Voice input** (ASR, spoken-language detection): to be discussed separately.
- The LLM key/chain cooldown (Revamp item 1) and the LLM-call counter (Revamp §8).
- Any change to the safety thresholds or the verdict logic.

---

## Appendix A — language ingress measurements (2026-10-04)

Live runs against Bhashini and the project's own Groq and Gemini keys, from
throwaway scripts that were **not** added to the repo. One run per prompt, prompts
written by the plan's author (cleaner romanization than real users', so treat
percentages as indicative). Bhashini was given the correct language for each
prompt, which is better than it gets in production. PC0.1 must re-create this set
as a committed test file.

### A.1 Bhashini, romanized text, today's path vs transliterate-then-translate

| Input | Today (direct NMT) | Transliterate, then NMT |
|---|---|---|
| kal subah rameswaram ke paas samudra mein jaana safe hai kya | unchanged | is it safe to go to the sea near rameswaram tomorrow morning |
| tum kaiso ho | "tum kaiso" (detected as Konkani, or as English and skipped) | how are you |
| naalai kadalukku pogalama | unchanged | are you going to the ocean tomorrow |
| repu samudram ki vellochha | garbled (detected as Nepali) | can you go to the sea tomorrow |
| naalai Rameswaram கடலுக்கு போகலாமா (mixed) | naalai rameswaram can you go to the sea | can you go to the sea in rameswaram tomorrow |
| kal Rameswaram ke paas मछली कहाँ मिलेगी (mixed) | kal rameswaram ke paas where to find fish | where to find fish near rameswaram tomorrow |

Native-script Hindi and Tamil translate correctly. IndicTrans2 could **not** be
run on the author's Windows machine (`IndicTransToolkit` needs a C compiler and is
installed only on Linux/Docker), so the local rung is unmeasured here.

### A.2 Romanized Hindi / Tamil / Kannada → English, three models, 24 prompts

Pass = place, time and intent all present in the English output.

| Model | Hindi | Tamil | Kannada | Total |
|---|---|---|---|---|
| Gemini `gemini-3.5-flash-lite` | 8/8 | 8/8 | 8/8 | **24/24** |
| Bhashini (translit → NMT) | 7/8 | 5/8 | 5/8 | 17/24 |
| Groq `openai/gpt-oss-120b` | 7/8 | 4/8 | 6/8 | 17/24 |
| Groq `qwen/qwen3.8-27b` | 6/8 | 1/8 | 3/8 | 10/24 |

The prompts (language, text → what a correct reading must contain):
- hi: kal subah rameswaram ke paas samudra mein jaana safe hai kya → Rameswaram, tomorrow, safe
- hi: kochi ke paas machhli kahan milegi aaj → Kochi, today, fish
- hi: mangalore me kal lehron ki unchai kitni rahegi → Mangalore, tomorrow, wave
- hi: chennai ke paas cyclone ka khatra hai kya → Chennai, cyclone, danger/risk
- hi: mujhe tuticorin se pamban tak sabse surakshit raasta batao → Tuticorin, Pamban, safest, route
- hi: aaj goa me hawa ki raftaar kitni hai → Goa, today, wind
- hi: kya parso vizag ke samudra me jaana theek rahega → Vizag, day after tomorrow, ok
- hi: meri naav ka engine kharab ho gaya hai pamban ke paas madad chahiye → Pamban, engine, help
- ta: naalai kaalai rameswaram pakkam kadalukku pogalama → Rameswaram, tomorrow, sea
- ta: kochi pakkathula innaikku meen enga kidaikkum → Kochi, today, fish
- ta: mangalore la naalaiku alai uyaram evvalavu irukkum → Mangalore, tomorrow, wave
- ta: chennai pakkam puyal echarikkai irukka → Chennai, cyclone/storm, warning
- ta: tuticorin la irundhu pamban varaikkum paadhukaappana vazhi sollunga → Tuticorin, Pamban, safe, route
- ta: indha vaaram kadal romba alaiya irukka → week, sea, rough
- ta: ennoda padagu engine nindruduchu pamban pakkam udhavi venum → Pamban, engine, help
- ta: naalaiku mannar kadal la kaatru vegam evvalavu → Mannar, tomorrow, wind
- kn: naale beligge mangaluru hatra samudrakke hogodu surakshitha ideya → Mangaluru, tomorrow, safe
- kn: karwar hatra ivattu meenu elli sigatte → Karwar, today, fish
- kn: udupi alli naale alegala ettara eshtu irutte → Udupi, tomorrow, wave
- kn: mangaluru hatra chandamaruta echcharike ideya → Mangaluru, cyclone/storm, warning
- kn: karwar inda goa varege surakshitha maarga heli → Karwar, Goa, safe, route
- kn: ivattu samudradalli gaali vega eshtu → today, wind, speed
- kn: nanna boat engine halaaytu malpe hatra sahaya beku → Malpe, engine, help
- kn: ee vaara samudra tumba alegalu ide ya → week, sea, rough/wave

Failures that matter, because they are wrong meaning rather than a missed word:
- Groq `gpt-oss-120b`: "safest route" read as "shortest route"; wave height read as tide height; Mannar dropped; "parso" read as "day before yesterday".
- Groq `qwen3.8-27b`: Tamil "engine stopped, need help" read as **"engine has caught fire, I need a rescue"**; Kannada "karwar hatra…" read as a price-per-kg question; "udupi alli naale alegala ettara eshtu irutte" read as "Did you create a name for Udupi?".
- Bhashini: Karwar → "Carver's"; Kochi dropped for "the side of the lake"; "alai uyaram" (wave height) → "tide height".

English control (Latin text that is already English, should come back unchanged):
Gemini left every completed case alone (2 of 6 calls hit a rate limit, 429, and were not measured). Groq `gpt-oss-120b` turned "pfzs near rameshwaram" into "Fish near Rameshwaram" and "pfz near ktaka tmrw" into "…Kataka tomorrow".

### A.3 Bhashini language detection and always-transliterate, on typed Latin English

Detection returned a non-English label for 12 of 20 short English prompts, with
confidence 0.77–1.00 on the wrong ones (the right ones were 0.77–1.00 too), and
HTTP 500 on 5 of 20 even after a retry ("hi", "pondy beach waves", "any cyclone
alert near chennai", "engine failed near pamban", "show chlorophyll near goa").
Examples: kochi weather → Malayalam 1.00; fish off tn coast → Odia 0.99; thanks →
Kashmiri 0.89; hello → Telugu 0.89; pfzs near rameshwaram → Malayalam 0.82.

English put through transliterate (en→hi) then translate (hi→en):
- pfzs near rameshwaram → "PFJ Near Rameswaram"
- pfz near ktaka tmrw → "PFJ Near Cuttack TMRV" (ktaka became an Odisha town)
- fish off tn coast → "Fish of Teen Coast"
- wats the time → "Watts was the time"
- hi → "The same"
- any cyclone alert near chennai → "Other Cyclone Alerts Near Chennai"

Not yet confirmed through the full `/ask` path: that a wrong detection such as
"pfzs near rameshwaram" → Malayalam actually produces a Malayalam reply.
