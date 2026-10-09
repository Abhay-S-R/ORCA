# ORCA / Sagar Sarathi: to-do checklist

Written 2026-10-09 from the implementation log (`docs/logs/DLC_implementation_log.md`) and the conversation.

**How to read this file**
- `[ ]` is open. **Nothing is ticked by Claude.** An item is ticked only after the user has verified it, because "done in code" has been wrong before (the voice was declared fixed once and was not).
- Part A is new work to do. VOICE-8 and VOICE-9 are LOW PRIORITY and are not counted in the open total (user, 2026-10-09). Part B is work already written, tested and logged, **waiting for the user's check**. Part C is decisions only the user can make.
- Each item has a short tag so the log, this file and the chat can point at the same thing.

---

## Part A: still to implement

### A1. Voice (the English voice mispronounces words; all of these are open)

*VOICE-3 (word respellings), VOICE-4 (compass points), VOICE-5 (double voice, accepted) and VOICE-6 (the check script) were implemented on 2026-10-09; they are tracked in Part B, not here.*
- [x] **VOICE-7: Marathi, Gujarati and Odia say "Bhashini speech is unavailable right now" (WRITTEN 2026-10-09, waiting for your check).** Cause: Bhashini's speech service times out for these three (same service as Hindi, which works). Now: the first failure (or the probe at server start) marks the language down for ten minutes, Play answers at once with that sentence and the local robotic voice is NOT played for these three; after ten minutes one 8 s probe decides if it is back. The other seven languages keep the local voice as backup. *To verify:* start the app, choose Marathi, ask anything, press Play: the message appears within a second or two, not 25 s; repeat for Gujarati and Odia; English and Hindi still play.
- [ ] **VOICE-8 (LOW PRIORITY, not in the count): a visible marker when the local (robotic) voice is used**
  The response already says which voice served (`X-TTS-Rung`); nothing shows it, so "the voice is off" cannot be told apart from "the fallback played".
- [ ] **VOICE-9 (LOW PRIORITY, not in the count): spoken numbers inside Indian-language answers: first-person checks**
  Native-reader review of `orca/agents/speech_lexicon.py` (words for to, metres, km/h, degrees, months) for Tamil, Telugu, Malayalam, Bengali, Gujarati, Odia. Kannada and Hindi were confirmed by the user.

### A2. The /ask page

- [ ] **PERSONA-AUDIT: audit the answer for each persona, one at a time** (the user, 2026-10-09: "response for each persona needs to be audited individually"; "next prompt testing ... related to the response, which needs to be revamped again")
  For each persona (fisherman, commercial navigator, researcher, coastal authority, and the unresolved / no-vessel case) read its answers on the same ten or so prompts and decide wording, depth and facts for THAT reader; one persona per point, logged separately.
  *Starting evidence, the fisherman's answer for "nearest fishing zone near Kochi":* "about 15 km WSW of Kochi (bearing 248°), at roughly 9.915° N, 76.074° E and 28-33 m depth ... issued on 2 Oct 2026 (7 days old) and has now expired ... wave ≈ 0.66 m, wind ≈ 0.78 m/s ... small-fishing vessels." It is a navigator's answer: a bearing, coordinates and a depth range for someone who wants "go this way, about 15 km, the advisory is old"; it mixes units (wind in m/s, distances in km, where a fisherman reads wind in km/h or knots); it says "roughly" and "about" twice; it does not say whether to go. Questions for the audit: what does each persona need first, which numbers do they use, which units, how long, and what must never be missing (the go / no-go and its reason).

- [x] **PLAN-ASK-1: remove the map from /ask completely (WRITTEN 2026-10-09, waiting for your check)**
  Map panel, collapse/expand buttons, distress pin, 42% map column and the two i18n keys are gone from /ask. *To verify:* open /ask, ask a question: no map, the answer uses the full column; other pages (/map) still have theirs; switch languages: no missing-text.
- [x] **PLAN-ASK-2: composer in the ChatGPT style (WRITTEN 2026-10-09, waiting for your check)**
  One rounded pill: ship button (vessel) at the left in place of "+", the field, a quiet mic, a round up-arrow send button. No outer card, no "Ask" word, no note line (it would need nine translations; say if you want it). Sample questions sit below the pill. The "Vessel not set" chip is replaced by the ship button (a small dot shows when no vessel is set; its menu says so). *To verify:* /ask signed in: type, press Enter and the arrow; the mic records; click the ship and pick a vessel; signed out: no ship button.
- [x] **PLAN-ASK-3: the composer keeps one width with the sidebar open or closed (WRITTEN 2026-10-09, waiting for your check)**
  The thread and the composer share one centred column, max width 56rem. *To verify:* open and close the chat-history sidebar with a long chat: the input box stays the same width (it only slides sideways); same on the welcome screen.
- [ ] **PLAN-ASK-4: no "New chat" button and no first-question text in the /ask header (written 2026-10-09).** *To verify:* open a chat on /ask: the header shows only "ASK SAGAR SARATHI"; New chat still works from the history sidebar.
- [ ] **PLAN-CHART-1: the weather chart on the answer card**
  It "dances" (line animation replays on every redraw, worst with the map open), uses dark-theme colours on the cream theme, puts wave (m) and wind (m/s) on one axis, shows raw ISO timestamps and overlapping labels. Fix each; removing the map (ASK-1) removes the trigger.
- [ ] **UI-ICONS: share and "more" icons** on the action row (copy, play, try again are done)
  Only if they have a real job; nothing exists for them yet.

### A3. Plan phases (`docs/plans/ORCA_Pipeline_Consolidation_Plan.md`)

- [ ] **PC4.1: confirm the reasoning page** renders every stage after the planning merge (no empty or missing stage).
- [ ] **PC4.2: update the docs that name removed nodes** (`orca_pipeline_walkthrough.md`, `orca_final.md`, README, `state.py` mention of `query_guard`). Docs only; the log is never edited. *(The IndicTrans2 fallback sentence stays, by the user's decision.)*
- [ ] **PC4.3: update the revamp doc's status** (`ORCA_Prompt_Routing_Revamp.md` section 6 points at the consolidation plan).
- [ ] **PC5.5: show the reading back** ("I understood: ...") for romanized input, in all nine UI languages (`npm run check:i18n` must stay at zero).
- [ ] **PC5.6: verify romanized distress and the gazetteer** ("naav ka engine kharab ho gaya, madad chahiye" must raise distress before ingress; romanized places must resolve or ask "which place?").
- [ ] **PC5.7: honest provenance labels** on the native-script path (a translation that returns its input unchanged is `degraded`; the docstring says Bhashini is primary). Two of the friend's tests (`test_pc5_language_ingress.py`) specify this and PC5.5; they fail until these are built.
- [ ] **Part B: audit the remaining agents, one at a time** (plan section 9: marine_data_discovery, language_egress, weather, geospatial, ocean_analytics, risk, visualization, reporting, critic). Decide for each: does it need to exist, does it duplicate another, model or code. Record the decision before writing points.
- [ ] **The core agentic architecture change** (the user's: "we are making changes to the core architecture now")
  Not written down anywhere yet: the question on record is whether planning coordinates the parallel specialists and whether they obey marine_data_discovery. **The user's usability case for the visualization agent is also not recorded and has to be restated.** First step is to write it as plan points, then implement one at a time.

### A4. Defects and quality

- [ ] **D-15:** a follow-up after "which place?" is answered at the default position instead of the place the user then names.
- [ ] **Critic false positives:** the critic deletes boundary information (IMBL distance) from correct answers.
- [ ] **Marathi is detected as Hindi**, so Marathi chat replies come back in Hindi script.
- [ ] **Foreign-script letters in a model's reply:** a Kannada reply twice contained a Korean word and a nonsense phrase. Proposed: reject a reply containing a script other than its own and Latin, and fall back to a translated English sentence.
- [ ] **Bengali "Hello!" becomes "আসসালামুয়ালাইকুম"** (a Muslim greeting) by the translator; swap to a neutral "নমস্কার" before translating, if the user wants.
- [ ] **Mixed-script and romanized-reading quality** (a known weak spot; mixed script was deliberately skipped earlier).
- [ ] **The product name in the UI dictionaries** stays in Latin letters inside native sentences (and in SMS / CAP text). Whether the Kannada UI should read ಸಾಗರ ಸಾರಥಿ is a user decision (Part C).
- [ ] **Name spellings for ta, te, ml, bn, gu, or** are derived from Bhashini, not confirmed by a native reader (Kannada and Devanagari are confirmed).

### A5. Config and operations

- [ ] **Cheap-tier time cap:** when Gemini fails slowly (18 s), Groq is never tried (the budget is spent). Proposed: cap each planning-model attempt at about 5 s.
- [ ] **Tide table ended 2026-10-07:** run `python scripts/refresh_tide_tables.py --days 7` (needs the Stormglass key; free tier 10 requests a day). Until then every port's tide answer is "unknown" and one unit test fails.
- [ ] **Startup is about 18 s** (Whisper, the Tamil voice and the routing model load one after another). Decide on `ORCA_LOCAL_MODELS=0` as the default for demos and friends' machines (loses offline voice and voice input).
- [ ] **BYOK (bring your own key):** users plug in their own free or pro model key. An idea only; nothing built.
- [ ] **Frontend `next build`, the e2e tests and the hosted GitHub run** have not been run since these changes; the last hosted run failed on infrastructure.
- [ ] **The friend's sea-route feature** was reverted by the friend. When re-pushed it must pass ruff, mypy, pyrefly and the frontend lint, with the data-missing case failing loudly instead of routing blind.
- [ ] **Commit and push** (the user does this; Claude never commits).

---

## Part B: written, tested and logged: waiting for the user to verify in the real app

*Tick each one only after checking it yourself. "How" is what to look at.*

### Chat understanding and safety
- [ ] **D-1: "engine failed near pamban" is a distress.** *How:* send it; expect the MRCC response and no sea agents. Also "what should i do if my engine fails at sea" must get a normal answer.
- [ ] **D-3: a Tamil place name no longer becomes "New York".** *How:* send `தூத்துக்குடியில் கடல் பாதுகாப்பானதா`; the answer must not mention New York.
- [ ] **D-2: an English question never gets a Malayalam reply.** *How:* "pfzs near rameshwaram" answers in English.
- [ ] **PC5.8: "answer in <language>" is honoured**, otherwise English for Latin text and the script's language for native script. *How:* "answer this in kannada: pfzs near mangalore" gives Kannada (**you confirmed this one**); "answer in english: <a Tamil question>" gives English.
- [ ] **Identity questions** ("who are you", "what is your name") in all nine languages are answered as identity, with the right name. *How:* ask in a few languages.
- [ ] **Planning model is Gemini flash-lite** (`ORCA_LLM_CHEAP_CHAIN`). *How:* a trace's planning step names `gemini · gemini-flash-lite-latest`.
- [ ] **No Ollama and no IndicTrans2** anywhere in startup or use. *How:* the backend log has no mention of either; the first query is no slower.

### The answer card
- [ ] **UI-CARD-3: the card is decluttered** (no "Cross-source check", no routing line, no empty header row above chat replies).
- [ ] **UI-CARD-4: one action row (copy, play, try again) under every response**, including chat replies and distress; play is a small icon, not the blue button.
- [ ] **D-16: a translated answer is never blank** (the "GO: reason" header split). *How:* Kannada/Tamil/Hindi answers show their text.
- [ ] **D-7: no raw `understand_llm` text on the card** (the routing line was removed entirely).
- [ ] **Sources & provenance dropdown** is closed by default and holds the evidence.
- [ ] **D-4: the PFZ answer still shows its map/layer** (flagged in the guide, never checked).

### Speed
- [ ] **FIX-COLD / FIX-COLD-2: the first query and the first Play are no longer slow.** *How:* restart (no `--reload`), wait about 20 s, ask one question and press Play; both should feel like the later ones. Via `localhost` a Python client pays ~2 s extra; browsers should not.

### Voice (what was fixed on 2026-10-08/09, English and Indian languages)
- [ ] **No "factorial"** after "Hello!" in English, Kannada, Hindi, Tamil and the others.
- [ ] **Straight apostrophe:** "don't" and "it's" no longer pause.
- [ ] **Dates, ranges and units are spoken properly in English:** "2 October 2026" (the year in digits, the form you approved), "30 to 35 meeters", "12 kilomeeters per hour".
- [ ] **Phone numbers are read digit by digit** (the distress message).
- [ ] **Male English voice; the name "Sagar Sarathi" in the Hindi voice.** *Not heard yet:* the male Hindi voice for the name (you approved the female one).
- [ ] **Indian-language answers:** "30-35 m" reads as a range with its connecting word, "m" as metres, "km/<hour>" as per hour, "2 Oct 2026" with the native month. *How:* play a Kannada PFZ answer.
- [ ] **Pressing Play twice never starts two overlapping audios.**

### Voice words, compass points and the check script (written 2026-10-09)

**D0 (male voice, cleaned text, one call for short answers) is the chosen setup and is what the app does.** *To start:* stop your backend, start it from `backend` with `uvicorn orca.api.main:app` (no `--reload`), wait for "ORCA ready after ...", hard-reload the page (Ctrl+Shift+R).

**A text you can always check (does not depend on what the model writes).** Open http://localhost:8000/docs, find `POST /voice/speak`, press "Try it out", paste a body, press Execute, play the audio ("Download file"). Body for the response you reported:
`{"text": "Conditions off Mangalore are safe for a small\u2011fishing boat \u2013 the sea is flat (about 0.6 m wave height) and the wind is light (around 2 km/h), with no lightning and no MPA breach. The closest potential fishing zone is roughly 16 km to the NNW of Mangalore, but its advisory has expired, so it should not be relied on. You can head out now.", "language": "en"}`
and for the fisherman answer:
`{"text": "The nearest known fishing zone is about 15 km WSW of Kochi (bearing 248\u00b0), at roughly 9.915\u00b0 N, 76.074\u00b0 E and 28\u201133 m depth. The latest advisory for that zone was issued on 2 Oct 2026 (7 days old) and has now expired, so there is no current advisory. Current sea conditions (wave \u2248 0.66 m, wind \u2248 0.78 m/s) are within safe limits for small\u2011fishing vessels.", "language": "en"}`
(Ready-made audio of both: `Desktop\voice-tests\fix-voice-7\E1b_...` and `E2b_...`; E1 and E2 are the same without "meeters".)

- [x] **VOICE-3: the reported words read right in English.** "height", "roughly", "relied", "marine protected area" (was "MPE"), "zone" with its z; also "gauge" and PFZ ("pee ef zee"). *You have confirmed in D0, D7, D8:* these were pronounced correctly. *Not heard yet:* gauge, PFZ.
- [x] **VOICE-4: compass points in words, in every language.** *Fixed 2026-10-09 after your report* (it failed in Kannada and Tamil: a distance and direction like "16 km NNW" went through the translator as two adjacent numbers, which it merged or dropped, and the fallback spelled "WSW" in letters). Now "16 km NNW" is one protected phrase, "N-N-W" and "west south-west" are normalised, and the voice says the compass point in the language's own words. *How:* on the site ask `answer in kannada: pfzs near mangalore`, `answer in tamil: pfzs near kochi` (this one has WSW), `answer in tamil: nearest fishing zone near mangalore`; press Play: Kannada should say ಉತ್ತರ ಉತ್ತರ ಪಶ್ಚಿಮ (and ಪಶ್ಚಿಮ ದಕ್ಷಿಣ ಪಶ್ಚಿಮ for WSW), Tamil வடக்கு வடக்கு மேற்கு / மேற்கு தெற்கு மேற்கு. The text on screen keeps "NNW" in Latin letters on purpose. The same in Hindi, Gujarati, Odia; the Tamil, Telugu, Malayalam, Bengali, Gujarati and Odia direction words need a native reader.
- [x] **VOICE-11: no pause in the middle of a long answer.** The pause after "You" in "You can head out now." came from the voice cutting every call at about 25 s; long answers are now split at sentence ends. *How:* play E1 (or the first /docs body above, or `pfzs near mangalore`-style long answers on the site): "You can head out now." should be one phrase with no gap after "You". `python scripts/voice_check.py --limit 30` now also prints any silence over 0.45 s. *Compare:* D0 (old, with the pause at 24.9 s) against E1 (new). Answers up to 260 characters are unchanged (one call); only longer ones are split, so tell me if a long answer now sounds worse than D0 in any other way (the splice point, the joined sentence rhythm).
- [x] **VOICE-12: months in full.** "2 Oct 2026" is spoken "2 October 2026", "Sept" as "September", "Oct 2, 2026" as "October 2, 2026" (English; the Indian languages already speak the native month name). *How:* the second /docs body above (E2).
- [x] **VOICE-13: "≈" is read "about", "±" as "plus or minus"** (it was "approximately equal"). *How:* the same E2 audio ("wave about 0.66 metres, wind about 0.78 metres per second").
- [x] **VOICE-10: "metres" is spoken "meeters" and "kilometres" "kilomeeters"** (your choices by ear, M3 and K2, 2026-10-09). *How:* play `Desktop\voice-tests\fix-voice-7\E2b_fisherman_answer_with_meeters.wav` ("28 to 33 meeters depth", "15 kilomeeters", "wave about 0.66 meeters, wind about 0.78 meeters per second"), or any depth, distance or wave answer on the site. (E2b was made before K2 was added; it still says "kilometres".)
- [x] **VOICE-5: the double voice: ACCEPTED as a residual by the user (2026-10-09: "forget about doubled voice, its fine now, its very subtle").** Not worked on further. Tick this only to record the decision; the tools (`voice_check.py --timeline`, `voice_respell.py`) stay if it ever matters again.
- [x] **VOICE-6: the voice check script.** `.venv\Scripts\python.exe scripts\voice_check.py --limit 3` from `backend`: three real answers voiced and read back, a summary of words heard differently, and now any long silence. `--text "..." --timeline` prints each word with its second.

### Language and numbers

- [ ] **FIX-FOLLOWLANG-1: "answer the same in <language>" after an answer re-answers in that language (written 2026-10-09).** *To verify:* ask "answer this in gujarati: pfzs near mangrol", then "okay fine answer the same in kannada": the same PFZ answer appears in Kannada (not "Sure thing..."). Try "in hindi please", then "change language" (still a reset), and "clear the conversation".
- [ ] **The name is spelled correctly in every language** (ಸಾಗರ ಸಾರಥಿ, सागर सारथी, ...), in translated answers and chat replies.
- [ ] **No number is lost in a translated answer** (the Marathi/Bengali "झेडकेईईपीझेड5झेड" leak; the Hindi `ZKEEPZ` leak). *How:* a Marathi or Bengali PFZ/weather answer shows 16 km, 30-35 m, 1.5 m.

### Earlier fixes that are verified (for the record, tick if you agree)
- [ ] D-9 (PFZ questions run the PFZ agent), D-10 (follow-ups about the last reply), D-11/D-14 (no unrequested GO banner), D-12 (no "odd reply"), D-13 (inland places answered directly), D-6.

---

## Part C: decisions waiting for the user

- [ ] **PC3.1 sign-off:** "approved as is" or what to change.
- [ ] **The "Vessel not set" chip:** it only changes go/no-go limits for larger vessels (a small boat is the safe default). Suggestion: show it only once a vessel is set and move the setting into the profile. Also what the composer's "+" should do (or omit it).
- [ ] **Marine data discovery: does it bind the specialists or only provide a citation layer?** (part of the architecture change)
- [ ] **The other persona-only blocks** (unresolved, researcher, coastal authority) on the answer card: keep, change or remove.
- [ ] **Bengali greeting**, **UI product name in native script**, **default of `ORCA_LOCAL_MODELS=0`** (items above).

---

## Known facts to remember

- The earlier log entry "FIX-VOICE-1 done" was **only true for English and for the words tested**; FIX-VOICE-2 reopened it for the other languages, and VOICE-3/4/5 above reopen it again for English words. Treat a voice item as done only after you have listened.
- Probe scripts and test audio are in `%TEMP%` and `Desktop\voice-tests`; none is in the repo yet (see VOICE-6).
- Nothing is committed. All work is in the tree for the user to review.
