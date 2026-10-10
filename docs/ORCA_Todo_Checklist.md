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

- [x] **PLAN-ASK-1: REVERTED on 2026-10-09: the map is back on /ask** (the team wanted it). Was ticked as "removed"; reopened because the behaviour is the opposite now. *To verify:* open /ask, ask a question: the map appears beside the thread, the collapse/expand buttons work, a distress call pins its position, /map is unchanged, the composer pill and the header (no New chat) are as before.
- [x] **PLAN-ASK-2: composer in the ChatGPT style (WRITTEN 2026-10-09, waiting for your check)**
  One rounded pill: ship button (vessel) at the left in place of "+", the field, a quiet mic, a round up-arrow send button. No outer card, no "Ask" word, no note line (it would need nine translations; say if you want it). Sample questions sit below the pill. The "Vessel not set" chip is replaced by the ship button (a small dot shows when no vessel is set; its menu says so). *To verify:* /ask signed in: type, press Enter and the arrow; the mic records; click the ship and pick a vessel; signed out: no ship button.
- [x] **PLAN-ASK-3: the composer keeps one width with the sidebar open or closed (WRITTEN 2026-10-09, waiting for your check)**
  The thread and the composer share one centred column, max width 56rem. *To verify:* open and close the chat-history sidebar with a long chat: the input box stays the same width (it only slides sideways); same on the welcome screen.
- [x] **PLAN-ASK-4: no "New chat" button and no first-question text in the /ask header (written 2026-10-09).** *To verify:* open a chat on /ask: the header shows only "ASK SAGAR SARATHI"; New chat still works from the history sidebar.
- [ ] **PLAN-CHART-1: the weather chart on the answer card**
  It "dances" (line animation replays on every redraw, worst with the map open), uses dark-theme colours on the cream theme, puts wave (m) and wind (m/s) on one axis, shows raw ISO timestamps and overlapping labels. Fix each; removing the map (ASK-1) removes the trigger.

### A3. Plan phases (`docs/plans/ORCA_Pipeline_Consolidation_Plan.md`)

- [ ] **PC4.1: confirm the reasoning page** renders every stage after the planning merge (no empty or missing stage).
- [x] **PC4.2: update the docs that name removed nodes** (`orca_pipeline_walkthrough.md`, `orca_final.md`, README, `state.py` mention of `query_guard`). Docs only; the log is never edited. *(The IndicTrans2 fallback sentence stays, by the user's decision.)*
- [x] **PC4.3: update the revamp doc's status** (`ORCA_Prompt_Routing_Revamp.md` section 6 points at the consolidation plan).
- [x] **PC5.6: RUN on 2026-10-09, result in the log; two notes became their own points below** (distress phrases: all 6 raised live, 3 only by the planner's model; places: 11 of 16 right, 5 no-place prompts answered at the disclosed default, 1 route wrong).
- [x] **PC5.6-NOTE-2 (SAFETY): romanized "help + boat failing" is distress with no model (written 2026-10-09).** *To verify:* send "naav ka engine kharab ho gaya, madad chahiye" and "nanna boat engine halaaytu malpe hatra sahaya beku": both give the MRCC response at once (not after 4-5 s); "route ke liye madad chahiye" must NOT raise an SOS. Hindi and Kannada only; native review still owed.
- [x] **PC5.6-NOTE-1: a romanized route between two places is a passage answered for the origin (written 2026-10-10, checked live).** *To verify:* ask "mujhe tuticorin se pamban tak sabse surakshit raasta batao" and "karwar inda udupi varege surakshitha maarga heli": each answered for the first place (Tuticorin / Karwar), not the Gulf of Mannar default. (A route that names a whole coastline such as Goa still asks which port.)
- [ ] **PC5.7 (now part of TRACE-1, audits 2 and 12): honest provenance labels** on the native-script path (a translation that returns its input unchanged is `degraded`; the docstring says Bhashini is primary). Two of the friend's tests (`test_pc5_language_ingress.py`) specify this and PC5.5; they fail until these are built.
- [ ] **Part B: audit the remaining agents, one at a time** (plan section 9: marine_data_discovery, language_egress, weather, geospatial, ocean_analytics, risk, visualization, reporting, critic). Decide for each: does it need to exist, does it duplicate another, model or code. Record the decision before writing points.
- [ ] **The core agentic architecture change** (the user's: "we are making changes to the core architecture now")
  Not written down anywhere yet: the question on record is whether planning coordinates the parallel specialists and whether they obey marine_data_discovery. **The user's usability case for the visualization agent is also not recorded and has to be restated.** First step is to write it as plan points, then implement one at a time.

### A4. Defects and quality

- [x] **D-15: a follow-up that names no place, after a "which place?" question, asks the question again (written 2026-10-10, checked live).** *To verify:* ask "pfzs near gujarat" (it lists ports), then "can you explain that in more detail": it asks which port again, not an answer at the Gulf of Mannar; then "near porbandar": answered for Porbandar.
- [ ] **Critic false positives (the class, not only IMBL):** the critic judges the answer against a hand-written facts list (`critic.build_facts_block`); anything the narrator may say that is not on that list gets flagged and deleted. The IMBL case did NOT reproduce on 2026-10-10 (3 live boundary questions passed or were corrected correctly); the same class deleted the SST/chlorophyll answer on 2026-10-09 (fixed for those fields). Proposed: build the critic's facts from the same data view the narrator sees + a parity test. Not built.
- [ ] **Marathi is detected as Hindi**, so Marathi chat replies come back in Hindi script.
- [ ] **Foreign-script letters in a model's reply:** a Kannada reply twice contained a Korean word and a nonsense phrase. Proposed: reject a reply containing a script other than its own and Latin, and fall back to a translated English sentence.
- [ ] **Bengali "Hello!" becomes "আসসালামুয়ালাইকুম"** (a Muslim greeting) by the translator; swap to a neutral "নমস্কার" before translating, if the user wants.
- [ ] **Mixed-script and romanized-reading quality** (a known weak spot; mixed script was deliberately skipped earlier).
- [ ] **The product name in the UI dictionaries** stays in Latin letters inside native sentences (and in SMS / CAP text). Whether the Kannada UI should read ಸಾಗರ ಸಾರಥಿ is a user decision (Part C).
- [ ] **Name spellings for ta, te, ml, bn, gu, or** are derived from Bhashini, not confirmed by a native reader (Kannada and Devanagari are confirmed).

- [x] **CONTEXT-2: "answer the same in <language>" translates the same earlier answer (written 2026-10-09).** *To verify:* ask "answer this in gujarati: pfzs near mangrol", then "okay fine answer the same in kannada": about 7 s, the SAME fishing-zone answer in Kannada (the verdict card unchanged); then "now in english please"; then "and the wave height there?" (answers for Mangrol); then "in hindi please, and what about tomorrow?" (a full new answer). "speak to me in Telugu" still works.

- [x] **NOTE-CHL-1 / NOTE-CHL-2: SST and chlorophyll at a place: one reading per quantity, no "sources disagree" unless truly unusual (written 2026-10-10; checked live with working keys).** *To verify:* ask a NEW phrasing, e.g. "udupi sst plus chlorophyll values wanted": you get ONE sea surface temperature (INSAT-3DR, with date and age) and ONE chlorophyll value with its level (low/moderate/high) and "close to the coast only indicative"; it does NOT say the sources disagree, and does not use the words "headline" or "cross-check". Kannada version has the same numbers.

- [ ] **NOTE-LANG-3: a reply asked "in kannada" can come back with the Kannada text inside the English field** (found live 2026-10-10: "ok and for kundapura now, in kannada" produced an English CAUTION banner followed by Kannada, which was then translated again). Likely related to the foreign-script item above. *Your call:* fix it as one point (the English field must be English; if the narrative model returns another script, keep the data-built English answer).

- [x] **PLAN-FORCE-1: ocean analytics is forced to run for tide, fishing-zone, SST and chlorophyll questions (written 2026-10-10, checked live).** *To verify:* open /reasoning (or the agent strip on /ask) for "any hazard alerts and the tide at kochi tomorrow": Ocean Analytics ran (not skipped) and the answer mentions the tide; same for "which fishing zones should I avoid near malpe, and where is the nearest pfz"; "sst and chlorophyll at udupi" then "and for karwar" give each place its own SST and chlorophyll.
- [x] **VOICE-10: Kannada rates read in your chosen order (B), written 2026-10-10.** *To verify:* a Kannada answer with wind (e.g. "is it safe near udupi, answer in kannada") and press Play: the wind is read "ಪ್ರತಿ ಸೆಕೆಂಡಿಗೆ 2 ಮೀಟರ್" (and km/h "ಪ್ರತಿ ಗಂಟೆಗೆ 12 ಕಿಲೋಮೀಟರ್"). Other languages unchanged (VOICE-9).

- [x] **CI-FIX-1 / CI-FIX-2: the CI Lint job failed twice after the merge (ruff 0.17.0 findings, then a strict xfail that my distress fix closed); both fixed locally (2026-10-10), not pushed.** *To verify:* commit and push, then the GitHub "CI — Lint" run is green. ruff is now pinned to 0.17.0 in `backend/requirements.txt` (CI-FIX-3, your yes). From now on I run the CI's own steps (including `tests/test_messy_prompts.py` and `tests/unit/test_response_guarantee.py`), not only `tests/unit`.

- [ ] **TRACE-1 (MAIN PRIORITY, the user, 2026-10-10): revamp the agent trace like ChatGPT/Claude ("Worked for 33s" that expands into a clean ordered account) and, BEFORE it, audit every agent so the trace only says what the backend really did.** Tracked in `docs/ORCA_Agent_Trace_and_Audit.md` (updated on every piece of work). Audit 4 (marine_data_discovery) is written: it is advice, not obeyed, with five defects; waiting for your decision A (bind the specialists, recommended) or B (citation layer). PC5.7 is folded into the ingress/egress audits.
  - [x] **AUDIT-4 A1 (written 2026-10-10): Agent 3's arrival check is honest.** *To verify:* open the agent trace/inspector for a tide question at Kochi ("tide at kochi"): the discovery step says tide from the Survey of India tables "for station KOC, covering <today>"; at New Mangalore ("tide at mangalore"): it says the Survey of India has no rows for NMP and falls to the Stormglass cache; a PFZ question shows the advisory's date and age. Decision A chosen; A2-A6 (catalog truth, binding tide/weather/SST/PFZ, decided-vs-used) are next.
  - [x] **AUDIT-4 A2 + A3 (written 2026-10-10, checked live): the catalog tells the truth; tide obeys Agent 3.** *To verify:* "what is the tide at kochi" / "tide times at mangalore please" / "tide at tuticorin tomorrow": in the inspector Agent 3 names the tide source (Survey of India for Kochi and Tuticorin; the Stormglass cache for Mangalore, with "no Survey of India rows for station NMP") and Ocean Analytics' tide shows decided = used. A chlorophyll question still answers (CMEMS is now the fallback, not NASA). A4 (weather), A5 (SST/chlorophyll/PFZ) and A6 (decided vs used on the trace) are next.
  - [x] **AUDIT-4 A4 (written 2026-10-10, checked live): weather obeys Agent 3.** *To verify:* "is it safe near kochi tomorrow morning": in the inspector Agent 3 names open_meteo_marine for waves and wind and open_meteo_lightning_proxy for lightning (no more "IMD Damini"), and the Weather Intelligence step shows `source_report` with decided = used and obeyed true for each; if Open-Meteo ever fails, the cached label now says how far the port is ("port=kochi, 4 km away"). Safety verdicts are unchanged.
  - [x] **AUDIT-4 A5 (written 2026-10-10, checked live): SST, chlorophyll and PFZ obey Agent 3.** *To verify:* "give me the sst and chlorophyll values for udupi right now": in the inspector Agent 3 shows sst (INSAT: "cell N km away, observed <date>, N d old"), chlorophyll (EOS-06, same shape) and the PFZ advisory's date and age; Ocean Analytics' `source_report` shows decided = used and obeyed true for sst, chlorophyll, pfz and tide. A plain "is it safe near udupi" shows only tide and pfz in the report. The answer's numbers are unchanged.
  - [x] **AUDIT-4 A6 (written 2026-10-10, checked live): decided vs used is on the trace data.** *To verify:* in the inspector, the Marine Data Discovery step has a plain sentence `trace_line` ("Chose data sources: wave height and wind speed from Open-Meteo ...; tides from ... ; fishing zones from INCOIS ..."; for "tide times at mangalore please" it says tides fell back to Stormglass because the Survey of India has no rows for NMP); each specialist's output has `source_report` (weather, ocean, geospatial); the final answer data has `source_check` = all checks obeyed, no mismatches. The UI does not draw these yet (next stage: the trace revamp). Audit 4 is complete in code after A1-A6.
  - [/] **AUDIT-6 geospatial (2026-10-10): 8 defects G1-G8 in `docs/ORCA_Agent_Trace_and_Audit.md` section 5b.** G1-G7 FIXED and verified with unit tests (G1 all 11 MPAs checked, G2 fishing-ban shore distance, G3 proximity bands synchronized at 3 nm, G4 SMS renderer clear boundary bug, G5 treaty line vintage provenance, G6 spatial_query_zones wiring + bearing + treaty date, G7 depth and shallow hazard). G8 (confidence & coverage reporting) remaining.

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
- [x] **D-1: "engine failed near pamban" is a distress.** *How:* send it; expect the MRCC response and no sea agents. Also "what should i do if my engine fails at sea" must get a normal answer.
- [x] **D-3: a Tamil place name no longer becomes "New York".** *How:* send `தூத்துக்குடியில் கடல் பாதுகாப்பானதா`; the answer must not mention New York.
- [x] **D-2: an English question never gets a Malayalam reply.** *How:* "pfzs near rameshwaram" answers in English.
- [x] **PC5.8: "answer in <language>" is honoured**, otherwise English for Latin text and the script's language for native script. *How:* "answer this in kannada: pfzs near mangalore" gives Kannada (**you confirmed this one**); "answer in english: <a Tamil question>" gives English.
- [x] **Identity questions** ("who are you", "what is your name") in all nine languages are answered as identity, with the right name. *How:* ask in a few languages.
- [x] **Planning model is Gemini flash-lite** (`ORCA_LLM_CHEAP_CHAIN`). *How:* a trace's planning step names `gemini · gemini-flash-lite-latest`.
- [x] **No Ollama and no IndicTrans2** anywhere in startup or use. *How:* the backend log has no mention of either; the first query is no slower.

### The answer card
- [x] **UI-CARD-3: the card is decluttered** (no "Cross-source check", no routing line, no empty header row above chat replies).
- [x] **UI-CARD-4: one action row (copy, play, try again) under every response**, including chat replies and distress; play is a small icon, not the blue button.
- [x] **D-16: a translated answer is never blank** (the "GO: reason" header split). *How:* Kannada/Tamil/Hindi answers show their text.
- [x] **D-7: no raw `understand_llm` text on the card** (the routing line was removed entirely).
- [x] **Sources & provenance dropdown** is closed by default and holds the evidence.
- [x] **D-4: the PFZ answer still shows its map/layer** (flagged in the guide, never checked).

### Speed
- [x] **FIX-COLD / FIX-COLD-2: the first query and the first Play are no longer slow.** *How:* restart (no `--reload`), wait about 20 s, ask one question and press Play; both should feel like the later ones. Via `localhost` a Python client pays ~2 s extra; browsers should not.

### Voice (what was fixed on 2026-10-08/09, English and Indian languages)
- [x] **No "factorial"** after "Hello!" in English, Kannada, Hindi, Tamil and the others.
- [x] **Straight apostrophe:** "don't" and "it's" no longer pause.
- [x] **Dates, ranges and units are spoken properly in English:** "2 October 2026" (the year in digits, the form you approved), "30 to 35 meeters", "12 kilomeeters per hour".
- [x] **Phone numbers are read digit by digit** (the distress message).
- [x] **Male English voice; the name "Sagar Sarathi" in the Hindi voice.** *Not heard yet:* the male Hindi voice for the name (you approved the female one).
- [x] **Indian-language answers:** "30-35 m" reads as a range with its connecting word, "m" as metres, "km/<hour>" as per hour, "2 Oct 2026" with the native month. *How:* play a Kannada PFZ answer.
- [x] **Pressing Play twice never starts two overlapping audios.**

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

- [x] **NO-PLACE-1: a message with no place anywhere asks "Which place do you mean?" in your language (written 2026-10-10, checked live).** *To verify:* in a NEW chat (and signed out, or with no home port, no location permission) ask "is it safe to go out tomorrow": it asks which place, in one friendly sentence, no "fallback position" text and no stray "X is a whole coastline"; reply "near udupi": answered for Udupi; "and tomorrow?": still Udupi. Ask the same in Kannada: the question comes back in Kannada only. "hello" and "what does the fishing ban order say" are not asked for a place.
- [ ] **NOTE-BAN-1: "(LOW PRIORITY) what does the fishing ban order say" with no place answers "no information for the Gulf of Mannar" (found 2026-10-10, not investigated).** The order is on disk (the REGULATORY row reads it); the answer should come from it, for the coast the user means, or ask which coast. *Your call:* look into it.

- [x] **NO-BANNER-1: no banner or chip above an answer; "same place" is worked out from the chat (written 2026-10-10, checked live).** *To verify:* ask "is it safe near mangalore", then "okay fine now answer in english: SST and chlorophyll of the same place": SST and chlorophyll for Mangalore, NOTHING drawn above the answer (no "This question names no place ..." box, no "Carried over" chip); "okay same place in hindi": the same answer in Hindi with no "Same answer in hi" note; "wave height near kochi", "wave height near goa panaji", "sst of the first place": answered for Kochi.

- [x] **FIX-PLACE-1: a spelling variant of a place is that place, and the answer says so (written 2026-10-09).** *To verify:* ask "pfzs near ktaka" (it asks which port), then "near udupi", then "oh sorry i meant kundapura": the answer is for Kundapur (no "Read X as Y" banner, removed on request) and is not the Thoothukudi default; then "okay fine give me the SST and chlorophyll details of kundapura in kannada". Also try "wave height near cochin", "is it safe near tuticorine", "wave near karwr" (all answered), "safe near gujurat" and "wind near atlantis" (both still ask).

- [x] **FIX-CONTEXT-1: the chat keeps 20 turns, all questions in view (written 2026-10-09).** *To verify:* in one chat ask 7 different things (e.g. wave near Kochi, wind, tide, SST, PFZ, wave near Goa), then "what was my first question in this chat?": it names the wave height near Kochi. Also try a correction ("no I meant Kozhikode") and "why is that?" after an answer.

- [x] **FIX-FOLLOWLANG-1: "answer the same in <language>" after an answer re-answers in that language (written 2026-10-09).** *To verify:* ask "answer this in gujarati: pfzs near mangrol", then "okay fine answer the same in kannada": the same PFZ answer appears in Kannada (not "Sure thing..."). Try "in hindi please", then "change language" (still a reset), and "clear the conversation".
- [x] **The name is spelled correctly in every language** (ಸಾಗರ ಸಾರಥಿ, सागर सारथी, ...), in translated answers and chat replies.
- [x] **No number is lost in a translated answer** (the Marathi/Bengali "झेडकेईईपीझेड5झेड" leak; the Hindi `ZKEEPZ` leak). *How:* a Marathi or Bengali PFZ/weather answer shows 16 km, 30-35 m, 1.5 m.

### Earlier fixes that are verified (for the record, tick if you agree)
- [x] D-9 (PFZ questions run the PFZ agent), D-10 (follow-ups about the last reply), D-11/D-14 (no unrequested GO banner), D-12 (no "odd reply"), D-13 (inland places answered directly), D-6.

---

## Part C: decisions waiting for the user

- [x] **PC3.1 sign-off (approved 2026-10-10, as is; the force-ocean-analytics rule is a separate point, PLAN-FORCE-1):** "approved as is" or what to change.
- [ ] **The "Vessel not set" chip:** it only changes go/no-go limits for larger vessels (a small boat is the safe default). Suggestion: show it only once a vessel is set and move the setting into the profile. Also what the composer's "+" should do (or omit it).
- [ ] **Marine data discovery: does it bind the specialists or only provide a citation layer?** (part of the architecture change)
- [ ] **The other persona-only blocks** (unresolved, researcher, coastal authority) on the answer card: keep, change or remove.
- [x] **Bengali greeting**, **UI product name in native script**, **default of `ORCA_LOCAL_MODELS=0`** (items above).

---

## Known facts to remember

- The earlier log entry "FIX-VOICE-1 done" was **only true for English and for the words tested**; FIX-VOICE-2 reopened it for the other languages, and VOICE-3/4/5 above reopen it again for English words. Treat a voice item as done only after you have listened.
- Probe scripts and test audio are in `%TEMP%` and `Desktop\voice-tests`; none is in the repo yet (see VOICE-6).
- Nothing is committed. All work is in the tree for the user to review.
