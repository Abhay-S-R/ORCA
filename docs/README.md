# ORCA docs — where things live

| Folder | What goes here |
|---|---|
| `specs/` | What ORCA is and must do: the problem statement (`ORCA_PS_SIH26176_Problem_Statement.md` — canonical), the DLC requirement register, `orca_final.md` (target end state), architecture, analysis, the pipeline walkthrough |
| `plans/` | Work still to be done, as numbered points: `DLC_implementation_plan.md`, the routing revamp, the chatbot response plan, the pipeline consolidation plan |
| `logs/` | Append-only records: `DLC_implementation_log.md` (mandatory for every point implemented), the verification report |
| `data/` | Datasets, freshness and stale-data policy, procurement, coverage |
| `deployment/` | Deploying and load-testing (Render, Vercel, Cloudflare) |
| `guides/` | How-to guides: data refresh, cron, manual verification, update notes |
| `competition/` | SIH pitch and judging material, demo script, business case, accuracy evidence |
| `archive/` | Superseded; history only, not for planning |

Rules: a new document goes in the folder that matches the table, not in `docs/`
root. Cite the problem-statement clause (`PS-C*`, `PS-Q*`, `PS-ARCH`) a document
serves. Plans are phases of independently pickable points, never per-developer
tracks. Implementation is **one point at a time**, logged before and after.

Paths inside `logs/DLC_implementation_log.md` entries written before 2026-10-03
use the old flat layout (`docs/<name>.md`); the files moved into the folders
above on that date, and the log is not rewritten.
