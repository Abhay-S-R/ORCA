# Stale data policy — "old is shown and labelled, never missing"

**Status:** All rows in §4's rollout tracker are resolved as of 2026-09-24 —
either banded (PFZ, MOSDAC SST/chlorophyll/CMEMS, OSF WW3/HYCOM), fixed at the
acquisition-timestamp level (Stormglass tides), or found structurally exempt
(the remaining `SOURCE_CLASS` rows — see §9).
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
| `incois_osf_ww3`, `incois_osf_hycom` | DAILY | 3 d | 7 d | history | forecast context only |
| `stormglass_tides`, `soi_tide_tables` | WEEKLY / DAILY | — | — | not banded — see §8 | no |
| `open_meteo_marine`, `damini_lightning`, `ndma_sachet`, `gdacs_tc`, `incois_hazard_osf`, `incois_tide_gauge` | LIVE | 0 | 0 | "no current reading" | **yes — never stale** |
| geometry, gazetteers (STATIC) | STATIC | ∞ | ∞ | — | as today |

## 4. Rollout tracker

| Dataset | Latest-per-region loader | Age on map | Age in agent facts | Age in narrative | Done |
|---|---|---|---|---|---|
| INCOIS PFZ | `analytics_loaders.load_pfz_latest` | band-styled fish + card badge | `nearest_pfz.age_days/band/expired`, sector `latest_advisory` | Reporting rule 9 | ✅ 2026-09-24 |
| MOSDAC SST | `satellite_loaders.load_insat_sst` (band tagged at load) | n/a — no SST map layer exists (see §5) | not wired into agent facts — SST reaches only `/trends`, never critic/reporting (see §5) | `/trends` `GranuleAge` caption | ✅ 2026-09-24 |
| MOSDAC chlorophyll | `satellite_loaders.load_eos06_chl` (band tagged at load) | n/a, same as SST | same as SST | `/trends` `GranuleAge` caption | ✅ 2026-09-24 |
| Copernicus CMEMS | `satellite_loaders.load_cmems_sst/_chl` (band tagged at load) | n/a, same as SST | same as SST | `/trends` `GranuleAge` caption | ✅ 2026-09-24 |
| INCOIS OSF WW3 / HYCOM | `ocean_analytics.nearest_osf_point_forecast` (band tagged per product) | n/a — the grid-CSV and raster-tile fallbacks have no per-cell date or no frontend reader (see §7) | `outputs["osf_point_forecast"]["wave"/"ocean"].age_days/band/expired` | reaches both the `/query` trace and the written answer (fixed 2026-09-25, see §7) | ✅ 2026-09-24 |
| Stormglass tides | `ocean_analytics.predict_tides` fallback rung | n/a — no map layer | `source_provenance.acquisition_timestamp` now the cache's real date, not query time | `/voyage` Berthing window `SourceChip` (fallback only) | ✅ 2026-09-24 — fixed, not banded (see §8) |
| Remaining DAILY / WEEKLY rows of `freshness.SOURCE_CLASS` | — | — | — | — | ✅ 2026-09-24 — exempt (see §9) |

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

## 7. INCOIS OSF WW3 / HYCOM specifics

- **Banded per product, off its own `forecast_time`.** `nearest_osf_point_forecast`
  tags `wave` (WW3) and `ocean` (HYCOM) separately, each against its own
  `forecast_time` — the step nearest "now" at the moment
  `extract_osf_pilot.py` last ran — rather than one shared "fetched at" stamp
  for both products. The banded values reach the Ocean Analytics span's
  `outputs["osf_point_forecast"]` on the `/query` stream, which the
  Reasoning page shows, **and** the written answer: `graph.py`'s reporting
  node hands the model `osf_point_forecast` alongside `tide`, `nearest_pfz`,
  `sector_status`, `pfz_persistence` and `productivity_diagnosis` from Ocean
  Analytics (gap found and corrected 2026-09-24; the narrative-input miss
  fixed 2026-09-25, `docs/DLC_implementation_log.md`'s defect 3). Whether a
  given answer's prose mentions the age is the model's own choice, same as
  any other fact in the block.
- **Smaller surface than PFZ, by design, not by omission**, same reasoning as
  §6: `load_osf_marine_grid()` (the rung-2 grid-cell fallback inside the same
  function) has no per-cell date to band; the raster `wave_height_forecast`
  tile pyramid's `SourceProvenance.acquisition_timestamp` is built empty and
  has no frontend reader; and `current_vectors_route` / `wind_vectors_route`
  (the HYCOM-currents and ScatSat-wind map layers) already carry their own
  `valid_time` / `acquisition_date` fields, consumed by `MapView.tsx`'s
  slider-sync grey-out and date-label mechanism — duplicating that with bands
  would be two mechanisms disagreeing about the same layer's age.

## 8. Stormglass tides — fixed, not banded

Forecast data is not observational data. A three-day-old satellite frame is a
wrong picture of today; a three-day-old *prediction* of tomorrow's high tide
is still the same prediction, correct until the window it was made for runs
out. Bands answer "how old is this copy", which is the wrong question for a
cached forecast pull — the right question, "is this prediction still inside
its stated window", is already answered by the LOW_DATA-on-exhaustion logic
`predict_tides` had before this pass.

The real gap was narrower and more honest to fix directly: when `predict_tides`
fell back from the Survey of India table to the cached Stormglass rung, it
reported `acquisition_timestamp` as the query time (`when`) rather than the
cache's own vintage — a old pull silently relabelled as fetched "now".
`analytics_loaders.load_stormglass_cache_date` reads the cache's real
`meta.start`, and `predict_tides` now reports that date when `fell_back` is
true. The SOI table needs no such fix — it is computed fresh on every call, so
`when` is already its honest acquisition time.

`soi_tide_tables` is exempt for the same reason: it is not a dated file on
disk to go stale, it is a computation over an always-current table.

## 9. Remaining `SOURCE_CLASS` rows — structurally exempt

The rest of `freshness.SOURCE_CLASS`'s DAILY/WEEKLY rows hold no dated local
copy for ORCA to band the age of, checked against `discovery.py`'s
`SOURCE_REGISTRY` and each loader's actual return shape:

- **`mosdac_nrt_sst`, `mosdac_nrt_chl`** — `freshness.SOURCE_FILES` points
  these at the identical globs as the already-banded `mosdac_open_sst` /
  `mosdac_open_chl`; they are the same files under a second registry id, not a
  second copy with its own age.
- **`nasa_ocean_color`, `bhuvan_wms`, `gfw_ais`** — every entry these loaders
  return carries `held_locally: False` (see `discovery.py`'s
  `nasa_ocean_color` docstring and `load_gfw_vessel_sample`'s own comment).
  They are catalogs — a granule listing, a WMS service list, a vessel-identity
  sample — not the data itself, so there is no per-item valid-for date to
  band; labelling the age of an index would misstate what it is an index of.
- **`mosdac_nrt_wind`** — has real files on disk, but no separate loader
  reaches it through `discovery.py`'s local-catalog dispatch (it falls
  through to "no local index for this source"); its one actual consumer is
  the same `wind_vectors_route` map layer already covered by the grey-out
  mechanism in §7.

None of these needed new code. Fabricating a band for a source with nothing to
date would be inventing a surface the policy doesn't require, not implementing
it.
