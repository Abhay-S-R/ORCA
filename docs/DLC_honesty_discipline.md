# ORCA — The Honesty Discipline, Rehearsed (P6.5, `R-DEMO-3`)

> **Rule:** volunteer every line below before a judge has to ask. A team that discloses its
> own limits is trusted on everything else it claims; a team caught hiding one is trusted on
> nothing. This is the literal card to rehearse from — say these five sentences somewhere in
> the demo, unprompted, not only if asked. `orca_final.md` §29.2 states the same five as prose;
> this is the same list as a presenter's rehearsal card, one line each, kept in sync with it.

## The five lines

1. **"The DAT-SG/Sagarmitra distress handoff is simulated."** A real structured payload is
   built and shown verbatim (`docs/orca_final.md` §13.2) — vessel identity, position, persons
   aboard, nature of distress — but nothing here actually transmits to the Coast Guard's real
   DAT-SG system. Every non-in-app/web-push channel (SMS, WhatsApp, IVR, missed-call callback,
   VHF, harbour board) is rendered and stored, never sent, and is labelled `SIMULATED`
   everywhere it appears — never `DELIVERED` (`orca/notifications/contracts.py`'s
   `NotificationStatus`).

2. **"Bhashini is live; local models are the offline fallback."** *(Current line, since
   `P3.8` went `LIVE-VERIFIED` 2026-09-23 — before that date the honest line was "Bhashini is
   a prepared seam, not a connection," and if credentials or the network are unavailable at
   demo time that older line is the true one again; check `GET /api/system-status` right
   before recording, don't assume.)* IndicTrans2 (local, CPU) is what actually renders every
   Tamil/Hindi line in this demo whenever the network is off, and it is pre-warmed at startup
   (P6.4) specifically so that fallback never costs a 40-second stall mid-recording.

3. **"SMS needs DLT template registration — that's a government process, not a code
   change."** The message is rendered correctly (GSM-7/UCS-2 aware, ≤160 chars, exact payload
   shown on screen) and stored — `orca/notifications/dispatcher.py`'s `SMSDispatcher` raises
   deliberately rather than pretending to send. Registering a sender ID and template with a
   telecom aggregator under India's DLT regulation is outside what this codebase can do for
   itself.

4. **"The IMBL line is an EEZ-boundary proxy, capped at MEDIUM confidence."** The real India–
   Sri Lanka maritime boundary is not published as a machine-readable geometry ORCA can fetch;
   the nearest publishable substitute (the EEZ boundary) is used instead, named as a proxy
   everywhere it drives a verdict, and confidence is capped at MEDIUM rather than reported as
   HIGH on a line that is not the treaty line itself.

5. **"Tsunami state is relayed from INCOIS, never computed."** `tsunami_trigger_state` is
   passed through from INCOIS's own bulletin verbatim (`orca/agents/ocean_analytics.py`) — no
   local threshold logic re-derives or second-guesses a tsunami call. Sovereignty over that
   judgment stays with INCOIS by construction, not by policy alone.

## Where each line's evidence lives, if a judge asks for it

| Line | Evidence to pull up live |
|---|---|
| 1. DAT-SG simulated | `/alerts` → any fired alert → "what was sent" (P4.13) shows every channel's verbatim payload and status |
| 2. Bhashini/local | `GET /api/system-status`; a Tamil `/ask` query with the network on, then off |
| 3. SMS DLT | `orca/notifications/dispatcher.py`'s `_SMS_REASON` string, or `/ops`'s broadcast preview showing the rendered-but-unsent SMS |
| 4. IMBL proxy | `/reasoning` on any Palk Bay query → the geospatial node's confidence derivation, capped MEDIUM |
| 5. Tsunami relay | `grep tsunami_trigger_state backend/orca/agents/ocean_analytics.py` — verbatim pass-through, no comparison operator near it |

## Owner and status

Built alongside `docs/DLC_demo_script.md` (P4.0/P6.6) as its companion rehearsal card — the
shot list says *what* is on screen; this says *what to volunteer* while it is. Re-check line 2
against `GET /api/system-status` the night of any recording, per P6.4's own offline-rehearsal
instruction — it is the one line on this card whose truth depends on the demo environment, not
on the code.
