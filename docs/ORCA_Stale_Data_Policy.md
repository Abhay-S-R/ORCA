# Stale data policy — "old is shown and labelled, never missing"

**Status:** PFZ and MOSDAC SST/chlorophyll implemented 2026-09-24. Every other
daily / weekly dataset is tracked in §4 and is picked up during the cron setup
pass.
**Grounding:** `docs/ORCA_Data_Freshness_Contract.md` (freshness class per
source) and `backend/orca/data/freshness.py` (the code form of it). This
document adds one rule on top of that contract; it does not change any class.

## 1. The rule

If today's (or this week's) copy of a dataset is missing, the feature it
describes has not stopped existing — cloud cover over a sector does not remove
the fish, it removes the satellite's view of them. So ORCA:

1. **Keeps showing the most recent copy it holds**, per region, on every
   surface: map, `/zones`, agent answers, trace, ops roll-up.
2. **Labels its age everywhere it appears** — on the map without clicking, and
   in the words of every answer. An old item is never styled or narrated as
   current.
3. **Never uses stale data for a safety verdict.** Waves, wind, cyclone,
   lightning are LIVE (see §3): an old copy of those is reported as "no current
   reading", never quietly substituted into GO / NO-GO.

## 2. Bands

Age is `today (IST) − the date the data is valid for`, in whole days. Each
dataset has two thresholds; the bands they create drive both the map style and
the agents' wording, from the single table in `freshness.RECENCY_BANDS`.

| Band | Meaning | Map | Agent wording |
|---|---|---|---|
| `fresh` | within the dataset's normal cycle | normal marker | stated plainly, with its date |
| `hint` | older, still useful as a pointer | faded marker + age label | "the most recent advisory here is from <date> (<n> days old) — a hint, not a current position" |
| `history` | kept for reference only | grey marker | "the latest we hold is <date>; there is no current information for this area" |

Separately, `expired` is true once the valid-for date has passed. The PFZ card
shows **Active** before that and **Expired · n d ago** after it.

## 3. Per-dataset thresholds

| Dataset (source id) | Class | fresh ≤ | hint ≤ | beyond hint | Used for verdict? |
|---|---|---|---|---|---|
| `incois_pfz` | DAILY | 3 d | 7 d | history (grey) | no |
| `mosdac_open_sst` (INSAT-3DR) | DAILY | 3 d | 7 d | history | no |
| `mosdac_open_chl` (EOS-06), `copernicus_cmems` (SST/chl fallback) | WEEKLY | 7 d | 14 d | history | no |
| `incois_osf_ww3`, `incois_osf_hycom` | DAILY | — | — | *to set in cron pass* | forecast context only |
| `open_meteo_marine`, `damini_lightning`, `ndma_sachet`, `gdacs_tc`, `incois_hazard_osf`, `incois_tide_gauge` | LIVE | 0 | 0 | "no current reading" | **yes — never stale** |
| geometry, gazetteers (STATIC) | STATIC | ∞ | ∞ | — | as today |

## 4. Rollout tracker

| Dataset | Latest-per-region loader | Age on map | Age in agent facts | Age in narrative | Done |
|---|---|---|---|---|---|
| INCOIS PFZ | `analytics_loaders.load_pfz_latest` | band-styled fish + card badge | `nearest_pfz.age_days/band/expired`, sector `latest_advisory` | Reporting rule 9 | ✅ 2026-09-24 |
| MOSDAC SST | `satellite_loaders.load_insat_sst` (band tagged at load) | n/a — no SST map layer exists (see §5) | not wired into agent facts — SST reaches only `/trends`, never critic/reporting (see §5) | `/trends` `GranuleAge` caption | ✅ 2026-09-24 |
| MOSDAC chlorophyll | `satellite_loaders.load_eos06_chl` (band tagged at load) | n/a, same as SST | same as SST | `/trends` `GranuleAge` caption | ✅ 2026-09-24 |
| Copernicus CMEMS | `satellite_loaders.load_cmems_sst/_chl` (band tagged at load) | n/a, same as SST | same as SST | `/trends` `GranuleAge` caption | ✅ 2026-09-24 |
| INCOIS OSF WW3 / HYCOM | | | | | ☐ |
| Stormglass tides | | | | | ☐ |
| Remaining DAILY / WEEKLY rows of `freshness.SOURCE_CLASS` | | | | | ☐ |

## 5. PFZ specifics

- **Archive keyed by advisory date.** `pfz/history/<folder>/` used to be named
  after the scrape day, which is the evening *before* the advisory's own
  `valid_for` date — and two scrapes of one advisory made two "days". Loaders
  now group every snapshot by `valid_for` and de-duplicate, so folder names no
  longer matter; the scraper names new folders by `valid_for`.
- **Latest per sector.** Each of SEC001–SEC014 contributes the nodes of its own
  most recent `valid_for` across the live file and every archived snapshot.
- **Nearest is capped at reach.** `nearest_pfz` searches within 150 km. Beyond
  that the honest answer is "none within reach", never a 906 km point on
  another coast.

## 6. MOSDAC SST / chlorophyll / CMEMS specifics

- **Banded at the loader, like PFZ's rows.** `load_insat_sst`, `load_eos06_chl`,
  `load_cmems_sst` and `load_cmems_chl` each tag their own `provenance` dict
  with `age_days`/`band`/`expired` before returning — the same shape PFZ rows
  carry, so every consumer reads it the same way.
- **Two granules, two ages.** `correlate_sst_chlorophyll` degrades its
  confidence to the worse of its own n/lag check and the two grids' recency
  bands — a correlation over two old-but-simultaneous granules (no
  `acquisition_gap` between them, both from the same stale week) would
  otherwise read HIGH; the band check is what catches that.
- **Smaller surface than PFZ, by design, not by omission.** Unlike PFZ, the
  gridded SST/chlorophyll product does not currently reach the map (no SST
  tile layer is built — `tiles.py`'s cmocean ramp is reserved for a future D3
  step that never shipped) or any agent's narrative (`critic.py`/`reporting.py`
  carry no SST facts at all — `correlate_sst_chlorophyll` only ever fed
  `/trends`). Labelling age on a surface that does not exist would be
  fabricating the surface, not the policy; if SST is wired into the map or the
  narrative later, it inherits these bands rather than needing new ones.
