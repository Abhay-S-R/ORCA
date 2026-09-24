# ORCA — Cost and Market Case (P6.2, `R-BIZ-1`)

> Every number below is either measured against the running application (with the exact
> command that produced it) or explicitly marked as a figure to confirm against a live rate
> card before the pitch — never a number typed in from memory. This document is the input to
> the demo script's closing card (`docs/DLC_demo_script.md`), which quotes it.

## 1. Cost per query, measured

Measured 2026-09-24 against the real running backend (`agent@orca.test`, `POST /query?q=Is it
safe to go out today at noon&lat=9.1&lon=79.2&persona=fisherman&fresh=1`, `query_id
ca9aa530-8846-4841-89c9-073cbfedfa62`), reading the SSE trace's own `agent_span` events —
the same instrumentation P2.10 (latency) and P2.13 (`llm_call_count`) add to every query, not
a one-off profiling run:

| Agent | Engine | Latency (ms) |
|---|---|---|
| distress_check | Deterministic | 1.0 |
| language_ingress | IndicTrans2 (local) | 0.0 |
| planning | Deterministic | 0.0 |
| marine_data_discovery | Deterministic | 3.0 |
| geospatial | Deterministic | 21.1 |
| ocean_analytics | Deterministic | 1419.5 |
| weather_intelligence | Deterministic (live fetch) | 5379.0 |
| risk_assessment | **Deterministic** | 0.0 |
| visualization | Deterministic | 1324.7 |
| reporting | gemini-3.5-flash-lite | 1697.5 |
| critic | gemini-3.5-flash-lite | 1409.9 |
| language_egress | IndicTrans2 (local) | 1.0 |
| **Total (this query)** | | **≈11.3 s**, dominated by one live upstream fetch |
| **`llm_call_count`** | | **2** (reporting, critic) |

**The verdict itself costs ₹0 to compute.** `risk_assessment` — the one node whose output a
false answer could hurt someone — is tagged `Deterministic` and makes zero model calls, same
as `geospatial`, `marine_data_discovery`, `ocean_analytics`, and `planning`. This is a cost
story and a safety story in one sentence: the two LLM calls this query makes (reporting's
narrative prose, and the critic's pass/fail check on that prose) sit entirely downstream of
the number that decides whether someone goes to sea, and `ORCA_LLM_ENABLED=0` (P2.11) proves
it live — same verdict, same thresholds, same citations, with both calls removed.

**Per-query ₹ cost — formula given, exact rate to confirm.** Token counts are not
instrumented in this codebase today (only call count and latency are — see `orca/llm/
tiers.py`'s `_call_count`), so an exact ₹ figure cannot be read off a trace the way the
numbers above can. The two calls are short: reporting synthesizes from a ~150-200 word
narrative (`inputs_consumed.narrative_len` was 170 characters, i.e. well under 100 tokens, in
the query above) and the critic scores that same narrative against a five-item rubric — both
comfortably inside a "Flash-Lite" class model's cheapest pricing tier, which as a class is
priced in the hundredths-of-a-rupee per query range for prompts this short. **Whoever finalizes
the deck should read the exact current per-token rate off the configured provider's own price
list at pitch time** — `.env.example`'s own note that Gemini's provider pricing can shift
underneath a model name (see its `ORCA_LLM_CHEAP_MODEL` comment) is the same discipline this
document follows rather than quoting a number that could be stale by the time it's spoken
aloud.

## 2. Marginal cost of the 10,000th user

The upstream data this system reasons over — INCOIS PFZ advisories, Open-Meteo Marine, GEBCO
bathymetry, WDPA boundaries, IMD/SACHET hazard feeds — is fetched once per cache window and
shared across every user asking about the same place and time (`orca/query_cache.py`'s
`resolved_key`, 30-minute TTL; `orca/cache.py`'s per-source caches beneath it). The 10,000th
user asking about a location someone already asked about in the last 30 minutes pays **zero**
marginal upstream-fetch cost and, if the exact resolved parameters match, is served the cached
response outright with zero marginal compute cost too. The only cost that scales linearly with
user count is the LLM calls for genuinely distinct queries — two calls, short prompts, per the
table above — plus ordinary web/API infrastructure. There is no per-user data-licensing cost:
every government source this system reads is free at the point of use.

## 3. Who pays

**Institutional, not per-fisherman.** State fisheries departments, INCOIS's own dissemination
arm, and district disaster-management authorities are the named buyers — not a subscription
sold to an individual fisherman. Saying so directly matters because the obvious next question
("would a fisherman actually pay for this app?") is the wrong question for this market: the
free government data this system reasons over is itself distributed through exactly these
institutional channels today (INCOIS bulletins, district ops broadcasts — `/ops`'s own CAP
composer is built for this persona), and ORCA's value to an institutional buyer is turning
that same free data into a queryable, personalized, multi-channel decision-support layer their
existing dissemination process does not have, not a new data source their existing process
would have to trust from scratch.

## 4. What it displaces

Not a competing forecast — INCOIS/IMD remain the authority ORCA cites, never overrides
(`docs/DLC_implementation_plan.md`'s own honesty discipline, P6.5). What it displaces is the
**manual interpretation step**: a fisherman or a district officer today reads a bulletin
written for a whole sector and has to work out, unaided, whether it applies to their specific
position, vessel class, and the next six hours — the step ORCA's deterministic verdict,
geofence distance, and per-vessel threshold deltas (`risk_assessment.py`'s `_VESSEL_DELTAS`)
do automatically and reproducibly.

## 5. Differentiation, in one line

*"[P6.1's accuracy number] against INCOIS's own advisory signal, reproduced by committed test
code against a real historical event — not asserted, because the safety path has no language
model in it to hide behind."*

## 6. Reproducing the measured numbers

```
# 1. bring the stack up (docker compose up, or an existing dev backend on :8000)
# 2. log in as the shared dev account and run a fresh (uncached) query, e.g.:
TOKEN=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"agent@orca.test","password":"orca-agent-local-dev"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -N -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/query?q=Is+it+safe+to+go+out+today+at+noon&lat=9.1&lon=79.2&persona=fisherman&fresh=1"
# 3. read latency_ms per agent_span event and llm_call_count off the final_response event.
```
