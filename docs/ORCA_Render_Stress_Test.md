# ORCA — Render memory stress test (on the deployed site)

> Run this **after** deploying the backend on Render (`docs/ORCA_Deployment.md` §2), from the
> live website. It tries to push the Render free service past its memory limit the way real
> users would. Why 512 MB is tight is explained in `docs/ORCA_Deployment.md` §2.1.

## What you watch

Render free gives the backend **512 MB RAM**. If it goes over, Render kills it: every answer in
progress fails, the site shows errors, and the service restarts.

Keep three Render tabs open next to the website the whole time (Render dashboard → the
`orca-backend` service):

| Render tab | What to look at |
|---|---|
| **Metrics** | The **Memory** graph. Set the range to the last hour. This is the main reading. |
| **Events** | Any **"Ran out of memory"** or **"Instance failed"** line. One of these means the test failed. |
| **Logs** | `Traceback`, `Error` or `Killed` lines while you test. |

Write the memory reading down after each stage, in the table at the bottom.

## What "pass" means

| # | Check | Limit |
|---|---|---|
| 1 | No "Ran out of memory" or restart in **Events** during the test | none |
| 2 | Highest point on the **Memory** graph | **≤ 460 MB** (90% of 512, leaving room for what this test missed) |
| 3 | Memory at the end of stage 6 vs the end of stage 2 | grows by **≤ 40 MB**. More is a leak, and a leak kills a service that runs for days. |
| 4 | Every answer on `/ask` finishes; no error card, no "something went wrong" | all of them |

## Before you start

1. **Wake the service.** Free services sleep after 15 idle minutes. Open
   `https://<render-url>/health` and wait until it shows JSON; the first wake takes a minute or
   more.
2. **Sign in** on the Vercel site with a normal account you registered there. Do not register
   `agent@orca.test` on the deployed backend.
3. **Avoid the cache.** Redis remembers answers, and a remembered answer uses almost no memory.
   So in every stage, **use questions you have not asked before**, or press the answer card's
   **try again**, which re-runs every agent. Repeating the same question is not a test.
4. Note the memory reading on the Metrics graph before you begin. That is the idle baseline.

## Stage 1. Every kind of question, one at a time

On `/ask`, ask these one after another, waiting for each answer. Each loads different data
(forecast grids, sea temperature, depth, fish zones, tides, cyclone track, place names):

1. `is it safe to fish near rameswaram today`
2. `what will the sea be like at kochi tomorrow`
3. `where are the fish near chennai`
4. `high tide time at mangalore`
5. `any cyclone coming to odisha this week`
6. `plan a trip from tuticorin to kanyakumari for a small boat`
7. `sea surface temperature near the andamans`
8. `what are the wind and waves like off gujarat`
9. `is fishing banned right now in tamil nadu`
10. `ராமேஸ்வரத்தில் இன்று மீன்பிடிக்க போகலாமா?` (Tamil)
11. `कल मुंबई के पास समुद्र कैसा रहेगा?` (Hindi)
12. `കൊച്ചിയിൽ നാളെ കടൽ എങ്ങനെ?` (Malayalam)
13. `ಮಂಗಳೂರಿನಲ್ಲಿ ಇಂದು ಮೀನುಗಾರಿಕೆ ಸುರಕ್ಷಿತವೇ?` (Kannada)
14. `kal kochi ke paas samundar kaisa rahega` (Hinglish)
15. `hi`, then `what time is it`, then `who won the cricket match`
16. With the browser's location allowed: `is it safe to fish here`
17. A follow-up in the same chat: `and tomorrow?`

Check after each: the answer finished, the Tamil/Hindi/Malayalam/Kannada answers came back in
that language, and the Memory graph did not jump close to 512.

## Stage 2. Every page

Open each page and use it, one at a time: `/map` (pan around, switch on every layer: heatmap,
currents, wind, zones, cyclone track), then `/safety`, `/zones`, `/trends`, `/alerts`,
`/watches` (create one), `/voyage` (plan one), `/reasoning` (an answer's trace), `/ops`, chat
history on `/ask` (open an old chat), and voice (speak a question, play a spoken answer).

**Write down the Memory reading now.** This is the "end of stage 2" figure for check 3.

## Stage 3. The map, several at once

`/map` fires many heavy requests together, so this is the burst most likely to spike memory.

1. Open `/map` in **three tabs at the same time**: middle-click three times, or open one and
   press Ctrl+Shift+T. Switch on every layer in each.
2. Then open it on your phone too, while the tabs are still loading.

## Stage 4. Several people asking at the same moment

This is the case that has never been tested (`docs/ORCA_Deployment.md` §2.8). Ask **different
places** so no two questions share data, and press Enter on all of them within a few seconds.

Use separate windows: one normal, one incognito (sign in again there), plus phones and
teammates' laptops. Each is a separate person.

| Round | People at once | Questions |
|---|---|---|
| 4a | 2 | `is it safe to fish near veraval today`, `where are the fish near paradip` |
| 4b | 4 | add `waves at karwar today`, `is it safe to go out from kakinada` |
| 4c | 6–8 | add Tamil, Hindi, `sea conditions at porbandar tomorrow`, `tides at kollam` |

After each round, check Events for an out-of-memory line. **Write down the largest round that
passed.** That is how many judges can ask at once on Render free. If 4 fails, the demo needs a
2 GB plan (Render Standard) or a rule that one person asks at a time.

## Stage 5. Questions and the map together

The realistic demo: two people ask on `/ask` while a third opens `/map` with every layer on, and
a fourth plays a spoken answer. All at once.

## Stage 6. Steady use for 30 minutes

Memory that only ever goes up eventually kills a service that runs for days. For 30 minutes, ask
a new question every 30 seconds or so, mixing places and languages, and leave `/map` open in
another tab. Sentinel's background check runs every 2 minutes during this too.

At the end, compare the Memory graph with the stage 2 figure (check 3). A line that keeps
climbing and never comes down is a leak even if it has not reached 512 yet.

## Optional: an exact burst from Git Bash

Browsers make it hard to fire requests at the same instant. This sends N uncached questions at
once straight to the backend (`fresh=true` skips the cache). Watch Metrics and Events while it
runs:

```bash
B=https://<render-url>
burst() {
  local n=$1; shift
  printf '%s\n' "$@" | head -n "$n" | while read -r s; do
    curl -s -G "$B/query" --data-urlencode "q=$s" -d fresh=true -o /dev/null \
      -w "%{http_code} %{time_total}s  $s\n" --max-time 600 &
  done; wait
}
Q=("is it safe to fish near rameswaram today" "sea conditions at kochi tomorrow"
   "is it safe to fish near veraval" "where are the fish near paradip"
   "waves at mangalore today" "is it safe to go out from kakinada"
   "ராமேஸ்வரத்தில் இன்று மீன்பிடிக்க போகலாமா?" "कल मुंबई के पास समुद्र कैसा रहेगा?")
burst 2 "${Q[@]}"; burst 4 "${Q[@]}"; burst 8 "${Q[@]}"
```

Any status other than `200`, or an out-of-memory event, is a failure.

## If it fails

1. In **Events**, note the time of the out-of-memory line. In **Logs**, find the request that
   was running just before it.
2. After the service restarts, ask **only that question** on its own (use try again) and watch
   the graph. If one question alone pushes past 512 MB, it is a single-request bug like the
   depth-grid and sea-temperature reads fixed before (`docs/ORCA_Deployment.md` §2.1). Look
   for a whole grid read into memory before it is cropped.
3. If every question passes alone and only stage 3, 4 or 5 fails, the limit is people at once,
   not one request. Either move to a 2 GB plan, or limit how many questions the backend runs
   in parallel.
4. Do not fix a failure by switching off a feature or dropping data. Fix the read that uses the
   memory.

## Results

| Date | Idle (MB) | End of stage 2 (MB) | Highest seen (MB), and in which stage | End of stage 6 (MB) | Most people at once that passed | Out-of-memory events | Pass? | Notes |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |
