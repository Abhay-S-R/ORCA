# ORCA — Prompt Routing Revamp (diagnosis and plan)

Written 2026-09-28, at the end of a diagnosis session. No code has been changed
for anything in this document yet. It records what is wrong with how `/ask`
reads a prompt, the evidence, why, and the agreed direction, so the work can be
picked up cold. Grounded in the chatbot rule in `ORCA_Chatbot_Response_Plan.md`:
every prompt gets an LLM-written answer. This document extends that to *reading*
the prompt as well.

Remember this: "the model reads every prompt, and word lists are only a fallback, never the final say.", our project is literally a chatbot and any typo, problems, edge cases in the prompt, the reponse of the prompt should be addressed the way any typical chatbot addresses, THIS IS THE MAIN RULE, DO NOT FORGET, THE CHATBOT IS THE PRIORITY AND THE PRODUCT

## 0. Priority: CRITICAL, blocks all other feature work

> **Talk like a chatbot, stay accurate like an instrument.** This is ORCA's founding principle (see the top of `CLAUDE.md`).

Set by the user on 2026-09-28. The chatbot is the product. It must read and
answer prompts the way a general LLM assistant does in conversation:
- understand typos, plurals, shortenings, slang and mixed-language text;
- follow context changes across turns, using the message history and a sensible
  context window;
- answer small talk, the clock and off-topic messages naturally rather than
  refusing them;
- write every response in a conversational way, in the user's language.

The agentic architecture stays: the agents reconcile heterogeneous data, and
code owns the facts and the safety verdict. But if the conversation is poor,
none of that shows, and the project misses its most fundamental point. Nothing
in this document is optional polish. The work items in section 7 come before any
other feature fix or new feature.

## 1. What is and is not broken

**Not broken:** the data agents, the deterministic risk verdict, reporting,
the critic, Bhashini translation, vernacular place resolution, and the answer
card. Facts and the go/no-go verdict are owned by code, which stays.

**Broken:** the step that *reads* the message. A language model writes every
answer, but before any model sees the message, hand-written word lists decide
whether it is a sea question, what it is about, where and when. When a list
misses, nothing smarter looks again. The scope gate says so in its own docstring
(`planning.is_out_of_scope`): *"Deterministic, no LLM: a refusal decided by a
model is a refusal that cannot be explained to a judge."* That was a reasonable
early choice and is now the bottleneck.

## 2. Reported symptoms and root causes

### 2.1 The "which place do you mean?" reply is slow, and inconsistently so
- The reply is written by the mid-tier chain in `orca/llm/tiers.py`: Gemini
  `gemini-3.5-flash-lite`, then Groq `openai/gpt-oss-120b`, then
  `gemini-flash-lite-latest`, then the local Ollama model.
- Backend log during the session: Gemini returned **503 Service Unavailable**
  repeatedly and once **504 after ~12 s**. A 503 is retried once, so Gemini
  alone costs 10–20 s before Groq answers in ~1–2 s.
- Measured on :8001: "…near gujarat" 19.2 s, "…near karnataka" 23.4 s, "pfzs
  near ktaka" 16.1 s, all answered by `groq · openai/gpt-oss-120b (fallback)`.
- `_ChainClient` has no memory across calls: every call starts at Gemini again,
  so every call pays the failure. Google's overload comes and goes, so latency
  is 2–4 s one minute and 20 s the next.
- The keys authenticate. These are server-side 5xx errors, not auth errors.

### 2.2 Gujarat got the "whole coastline" intro, Karnataka did not
- Both hit the same path: `place_resolution.resolve_or_ask` → `is_region_name`
  → the fixed text "X is a whole coastline, not a position… Which of these did
  you mean?" plus four ports.
- That text is reworded by `reporting.write_guard_reply`, whose prompt only
  requires keeping place names and numbers. A model may drop the reason
  sentence. When every rung fails, the verbatim fixed text shows instead. Which
  one the user sees depends on which rung answered. The user did not misspell
  anything.

### 2.3 "pfzs near ktaka" refused as out of scope
- `is_out_of_scope("pfzs near ktaka")` is True; `"pfz near ktaka"` is False.
- `_MARINE_VOCAB` has `pfz` but not `pfzs`: `_significant_words` does no
  singularising. The tier-1 keyword is "nearest pfz", which "pfzs near" does not
  contain.
- "ktaka" is not in the gazetteer. `near_miss_place_names` (difflib, cutoff
  0.82) scores ktaka/karnataka at 0.71, so it is treated as naming no place.
- The refusal happens before the tier-2/tier-3 classifiers. **No model ever
  read the question.** The "3 LLM calls" on the card were the refusal wording.
- Place resolution had already fallen back to "Gulf of Mannar (default)".

### 2.4 "wats time now" refused
- ORCA *can* answer the time: `graph.out_of_scope_node` answers self-context
  questions from the real clock. That path is reached only when the text
  contains one of the 20 exact phrases in `_SELF_CONTEXT_PHRASES`. "what's the
  time" matches; "wats time now" does not, so it is refused. The capability
  exists; a phrase list stands in front of it.

## 3. Inventory of the word lists (counted 2026-09-28)

About 38 fixed lists and patterns, roughly 1,400 hand-written entries, and one
typo checker (`near_miss_place_names`, place names only). Nothing handles
plurals, shortenings or typos in any other list.

| Area | Lists (entries) |
|---|---|
| Understanding (`planning.py`) | `ROUTING_TABLE` (19 rows, 128 keywords), `_MARINE_VOCAB` (136), `_NON_MARINE_TASKS` (20), `_INJECTION_PATTERNS` (14), `_SELF_CONTEXT_PHRASES` (20), `_STOPWORDS` (21), `_SYNONYMS` (4/10), `_CONTINUATION_OPENERS` (12); `intent_embeddings.ROW_PHRASINGS` (93) |
| Places (`loaders.py`, `place_resolution.py`) | `_GAZETTEER` (249), `_REGION_KEYS` (28), `_COASTAL_STATES` (13), `_TAMIL_ALIASES` (25), `_PORT_ALIASES` (4), `_LATIN_VARIANTS` (1), `_GENERIC_DIRECTIONS` (5), `_UNPLACEABLE_SELF_REFERENCE` (25), `_PAST_CUES` (10) + date/coordinate/passage regexes |
| Time (`weather_intelligence.py`) | `_TEMPORAL_PATTERNS` (7: today / tomorrow / tonight / this morning / in N hours) |
| Safety and control | distress (74), medical (64), romanised distress (2), `_RESET_PHRASES` (43), language commands (57), `_VESSEL_WORDS` (21), `_COMMON_ENGLISH_WORDS` (36) |
| Small agent-internal markers | `_HISTORICAL_DAYS_BACK`, SST-stress, upwelling, `_WATER_BODY_WORDS`, `_PROTECTED_TERM` |

## 4. Probe results (deterministic path, 2026-09-28)

| Prompt | Today |
|---|---|
| "engine failed near pamban" | not distress, **and** refused as out of scope |
| "water coming into boat", "my friend fell in the water" | not distress; answered as a normal conditions question |
| "pfzs near ktaka" | refused |
| "i want to cook the fish i catch near kochi, how rough is it" | refused ("cook") |
| "wats the time" / "wats time now" | refused |
| "safe to go day after tomorrow near kochi" | answered for **tomorrow**, silently |
| "kochi next friday", "kochi on 5th october", "tmrw sea ok…" | answered for **now**, silently |
| "kochi on 2026-10-05" | passes the time guard, but the weather lookup answers for **now** |
| "pondy beach waves", "fish off tn coast" | answered at the Gulf of Mannar default (disclosed) |
| "hows the water at vizag", "swell at rameswaram", "take my boat out near chennai" | work |

The two worst classes are **missed distress** and **wrong dates answered as if
right**: both look like a normal answer.

## 5. The rule going forward

A language model **reads** every prompt, not only writes the answer. Word
lists are a fast path or the offline fallback when every model is unreachable;
they never refuse, misroute or silently reinterpret a prompt. A miss is never
fixed by adding the missing word to a list. Distress is the one-directional
exception: the phrase list may raise the alarm instantly, but a list miss must
not rule distress out.

## 6. Target routing

> **Status & Consolidation note (2026-10-04):** Superseded and implemented by [`ORCA_Pipeline_Consolidation_Plan.md`](ORCA_Pipeline_Consolidation_Plan.md). The UNDERSTAND step (LLM reading) and VALIDATE step (`validate_reading`) have been merged directly into the unified `planning` node (`orca/agents/planning.py`), deleting the standalone `understand` and `query_guard` graph nodes while preserving all deterministic validation checks, fallback logic, and safety routing.

```
message
  1. distress phrase list          instant alarm, can only escalate        (kept)
  2. UNDERSTAND                    one cheap-tier LLM call; sees the last 5 turns,
                                   the live location and the current clock
  3. VALIDATE                      code checks the model's output against real data
  4. act                           answer directly / ask one question / run agents
  5. reporting LLM writes the answer                                        (as today)
```

**Understand** returns a fixed structure:
`kind` (sea question / greeting or small talk / clock or position / what can
ORCA do / reset / language switch / distress / off-topic), `intents` (the 19
routing rows), `places` (as typed and normalised, e.g. ktaka → Karnataka,
pondy → Puducherry), `when` (a real date range), `is_followup`.

**Validate**
- A place counts only if it maps to the gazetteer or a region. An unknown place
  produces "which place do you mean by X?", never the pilot default.
- A date beyond the forecast horizon or in the past gets the existing time-guard
  message.
- Intents not in `ROUTING_TABLE` are dropped.
- A distress reading escalates; nothing can remove a distress alarm.
- The safety verdict stays deterministic.

**Act**: clock, greeting, capability and off-topic messages get a short
model-written answer immediately, with the clock and position passed in as
facts. Sea questions run the agents exactly as today.

**Cost**: one cheap call that replaces the tier-3 classifier call most questions
already make, so it is roughly neutral. It depends on 7.1 first, otherwise it
pays the Gemini failure on every message.

## 7. Work items, in order

_Status 2026-09-29: item 1 and the section 8 counter fix are done (see the implementation log). Items 2–6 are open._

1. **LLM keys and chain: reassign the Groq and Gemini keys properly** and add a
   per-rung cooldown. Gemini is returning 5xx.
   - Re-check which key each provider reads (`GEMINI_API_KEY`/`GOOGLE_API_KEY`,
     `GROQ_API_KEY`), and which model each tier uses (`chain_for` in
     `orca/llm/tiers.py`). Decide whether Groq should be the primary: on
     2026-09-26 it measured 1.7 s against Gemini's best of 4.1 s.
   - In `_ChainClient`: after a 503, a 504 or a timeout, skip that rung for about
     2 minutes; clear the skip on success. Don't retry a 503 on the same rung when
     a healthy rung is next.
2. **The Understand call and validation** (section 6).
   - It replaces, as gates, `is_out_of_scope`'s vocabulary test,
     `_TEMPORAL_PATTERNS`, the `_PAST_CUES`/`_DAYS_AHEAD` date guessing,
     `_SELF_CONTEXT_PHRASES` and `_CONTINUATION_OPENERS`.
   - The routing keywords and place lists stay as the offline fallback.
3. **System prompt changes.**
   - Write the Understand prompt.
   - Revise `reporting._guard_prompt` (`write_guard_reply`) so the reply must keep
     *why* it is asking, not only place names and numbers.
   - Add a check that falls back to the fixed text when the reason sentence is
     dropped.
   - Review the other system prompts (narrative, critic, tier-3) against the new
     flow. Every call still gets the last 5 turns and the live location.
4. **Distress model check** that can only escalate. This closes "engine failed",
   "water coming into boat" and "fell in the water".
5. **Delete** `_SYNONYMS` and the word-overlap backup (`_tier2_word_overlap`).
   Decide whether the 120 MB embedding model (`intent_embeddings`) is still
   worth keeping as the offline fallback.
6. **Messy-prompt test file**: a few hundred prompts with expected
   kind, intent, place, date and distress.
   - In CI (no keys): checks the validation and makes sure the fallback never
     refuses or misdates.
   - As a live script: runs the file against the real models and reports a pass
     rate. New misses go into the file, never into a word list.

Before implementing, these are to be written as numbered points in the DLC
implementation plan, per the standing planning rule. Each point is recorded in
`DLC_implementation_log.md` as it lands.

## 8. Logged 2026-09-29: the "N LLM calls" counter counts failed attempts

A "nearest fishing zone from my current location" turn showed **"12 LLM calls"**
and 43.3 s of agent time, with the Critic slowest at 16.2 s.

- **Cause:** `tiers._count_call()` runs inside `_TieredClient.complete`, which
  runs once per *attempt*, not once per answered call.
- **What that turn made:** it made about four real model calls: Planning's
  classifier, the Reporting narrative, the Critic judge and the Critic revise.
  But while Gemini returns 503, each call is a Gemini attempt, a retry and then
  Groq, so 4 × 3 = 12.
- **What to fix:** report the calls that returned text, and optionally the
  failed attempts separately (e.g. "4 LLM calls · 8 failed attempts"). Once the
  per-rung cooldown in item 1 lands, the failed-attempt count should mostly fall
  to zero on its own.
