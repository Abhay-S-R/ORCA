# ORCA — Stale Data Cleanup Register

**Status:** advisory. Nothing in this document has been deleted.
**Audited:** 2026-09-19. **Re-verified against live disk 2026-09-22**, after the daily and weekly
refresh jobs were run end to end; `data/` now holds 26,449 files, 22.35 GB. Every entry below was
re-checked file by file on that date — all 43 files in §1 are still present and still unreferenced,
and the sizes are unchanged (§1 totals 9.51 GB decimal / 8.86 GiB, which is the same bytes counted
two ways). Three things did change, and they are marked **[2026-09-22]** where they appear: §1.8 is
new, §5 has shifted by one run, and both wiring problems in §6 are now fixed.
**Grounded in:** `docs/ORCA_PS_SIH26176_Problem_Statement.md` (canonical), `docs/ORCA_Data_Freshness_Contract.md`
(which defines LIVE / DAILY / WEEKLY / STATIC), and `docs/ORCA_SIH26176_AllIndia_Dataset_Coverage_Guide.md`
(which records what each file is wired to).

---

## 0. Read this before deleting anything

`data/` is gitignored. Nothing in it can be recovered from the repo — only by re-downloading,
and **some of it can no longer be re-downloaded at all** because the upstream stream was retired.
So the standard for putting a file on this list is not "it looks old". It is:

1. **No code path reads it.** Verified by grepping every `glob()` and every hardcoded path in
   `backend/orca/`, `backend/scripts/`, `scripts/`, and `frontend/app/`.
2. **Nothing reads it as part of a series.** Several ORCA readers deliberately take the *newest*
   file and ignore the rest (`satellite_loaders._newest`, `geospatial._latest_wind_file`,
   `voyage`, `generate_tiles`). For those, older granules are genuinely dead. But others read a
   *history* — `analytics_loaders.available_pfz_history_dates()` walks every snapshot directory —
   and for those, an old file is the feature, not the debt.
3. **It is not the last copy of something.** A file can be stale *and* irreplaceable.

Old ≠ useless. §4 lists the files that look deletable and are not; read it before you start.

---

## 1. Safe to delete — verified unused

Every file here is unreferenced by any code path, superseded on disk by a newer copy of the same
thing, or an explicitly-labelled placeholder. **Total: 43 files, 9.51 GB.**

### 1.1 `rsmc_combined_ww3_20260829.nc` — 6,910 MB (single file, the biggest easy win)

`data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc`

The August full-domain WaveWatch III download. Three readers touch this directory
(`voyage.py:69`, `generate_tiles.py:58`, `generate_pan_india_waves.py:32`) and all three take the
newest filename, so this file is never selected while `rsmc_combined_ww3_20260917.nc` exists.

It is not merely a duplicate — it is genuinely *bigger* than what replaced it, and that deserves
stating plainly before you delete 6.9 GB:

| | Aug file | current file |
|---|---|---|
| domain | 30–120 °E, 60 °S–30 °N | 60–100 °E, 0–28 °N |
| grid | 901 × 901 | 281 × 401 |
| variables | 18 (incl. swell partitions `PHS00/01`, `PTP00/01`, `PDI00/01`, `DP`, `SPR`, `LM`, `FP`) | 6 (`HS`, `T02`, `PWP`, `MWD`, `UWND`, `VWND`) |

Neither extra is reachable. ORCA's pan-India box is 65–96 °E, 2–25 °N — inside the current
subset, so the wider domain is unused. And a grep for every one of the twelve extra variable names
across the backend returns nothing. The swell partitions have never been read by anything.

The honest counter-argument is "a future feature might want swell partitions." It would want them
for *this week's* sea state, not 29 August's. If that feature arrives, the fix is to add those
variables to `WW3_VARS` in `scripts/refresh_osf_forecasts.py` and refetch — not to keep a
three-week-old file on the off chance.

### 1.2 MOSDAC scatterometer wind, 12 km — 11 files, 2,376 MB

`data/tier3/mosdac/Wind/E06SCTL4AW_20262{25,26,27,28,29,30,31,32,37,38,39}_12km_v1.0.5.nc`

Days 225–239 of 2026 (14–27 August), 216 MB each. These came from a stream MOSDAC **no longer
serves** — see freshness contract §6.3. `geospatial._latest_wind_file()` sorts by filename and
takes the last, which is now a 25 km September granule, so these are never opened. No code
anywhere mentions `12km`.

Note the irreversibility: delete these and the 12 km resolution is gone for good, because the
stream that produced it is dead. That is acceptable — they are 3+ weeks stale, `mosdac_nrt_wind`
is a WEEKLY context layer, and a wind field from August has no use in answering a question about
today. But it is a one-way door, so it is called out rather than buried.

### 1.3 MOSDAC INSAT-3DR SST, August granules — 17 files, 159 MB

`data/tier3/mosdac/Sea surface temp/3RIMG_{13..29}AUG2026_0015_L3B_SST_DLY_V02R00.h5`

`satellite_loaders.py:125` takes the newest by parsed filename date. The September run
(11–17 Sep, 7 files) supersedes all of these. Nothing reads SST as a time series.

### 1.4 MOSDAC chlorophyll, March granules — 10 files, 62 MB

`data/tier3/mosdac/chlorophyll/E06OCML4AC_202603{20..30}_25km_v1.0.1.nc`

These are the granules that produced the 172-day freshness breach. `satellite_loaders.py:172`
takes the newest, which is now `20260915`. Nothing computes a chlorophyll trend or anomaly from
this directory — the productivity diagnosis (`ocean_analytics.py:538`) reads CMFRI catch records,
not these files.

### 1.5 Superseded Copernicus thetao — 2 files, 4.3 MB

```
data/tier2/copernicus/cmems_thetao_india_20260910_20260916.nc
data/tier2/copernicus/cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m_thetao_77.00E-80.50E_7.50N-10.50N_0.49-5727.92m_2026-08-28-2026-08-29.nc
```

Both hold sea temperature over the same area as `cmems_thetao_india_nrt.nc`, at older dates.
`satellite_loaders._cmems_newest()` picks by **mtime**, so today it correctly picks the current
file — but mtime records when the byte was written on this machine, not what date the data
describes. Restore from a backup or copy the directory and that ordering can invert, at which
point the SST fallback rung serves August data labelled as current. Deleting these removes the
trap. (Separately worth doing: switch `_cmems_newest()` to `content_date_from_name()`, the parser
`freshness.py` already uses.)

### 1.6 `pan_india_currents.json` — 0.3 MB

`data/tier1/vectors/pan_india_currents.json`

The v1 cache. `geospatial_routes.py:80` reads `pan_india_currents_v2.json`. A repo-wide grep for
the v1 filename returns three hits, all in documentation describing v2. Zero code references.

### 1.7 `era5_gaja_STUB.json` — 2 KB

`data/cyclone_gaja/era5_gaja_STUB.json`

The pre-procurement placeholder `fetch_gaja.py` writes when CDS credentials are missing. The real
download (`era5_gaja_20181112_20181118.nc`) sits beside it, and `orca/replay/gaja.py:5` says in so
many words that the stub "sits alongside, unused".

### 1.8 `bhuvan_15days_marine_manifest.json` — 11 KB **[2026-09-22, new]**

```
data/tier3/bhuvan/bhuvan_15days_marine_manifest.json
```

**This entry moved here from §4, because the code moved.** On 2026-09-19 this was the file
`load_bhuvan_wms_services()` actually read, which is why the audit told you to leave it alone. The
wiring bug in §6.1 has since been fixed the other way round: `refresh_bhuvan_manifest.py` now writes
the `core_wms_services` catalogue into `bhuvan_manifest.json` — the file the freshness contract has
always watched — and the reader was repointed at it. `local_catalog("bhuvan_wms")` returns 4 services
from the monitored file.

That leaves this one genuinely orphaned. A repo-wide grep finds it in exactly three places, all of
them prose explaining the history: a comment in `agents/visualization.py:118`, the docstring in
`data/analytics_loaders.py:448`, and the module docstring of `scripts/refresh_bhuvan_manifest.py:10`.
No code opens it. It is 11 KB, so deleting it buys nothing but tidiness — it is listed for
correctness, not for space.

---

## 2. Blocked — do not delete until the code moves first

### `RSMC_hycom_20260830.nc` — 10,582 MB

`data/incois_osf_pfz/osf_hycom/RSMC_hycom_20260830.nc`

**This is the single largest file in `data/` — half the total — and it is the one you must not
delete today.** It is tempting precisely because it is huge and dated August. Two things pin it:

1. **It is hardcoded.** `scripts/build_pfz_fallback.py:47` names this exact file and reads `TEMP`
   from it (line 81) to compute the thermal-front proxy that answers "where are the fishing zones"
   on days when INCOIS publishes no advisory for a clouded sector.
2. **It is the last copy of five variables.** The current refresh
   (`scripts/refresh_osf_forecasts.py`) fetches only `UVEL`/`VVEL`, so `RSMC_hycom_20260917.nc` is
   83 MB and carries currents alone. `TEMP`, `SALN`, `SSH`, `MLD`, `TCHP` and `TEMP_CT` exist
   nowhere else on disk. `extract_osf_pilot.py:221` already documents this: those variables "came
   with the retired RSMC_hycom bundle and have no current public equivalent here."

**To unblock it:** re-point `build_pfz_fallback.py` at `SST_NIO_20260917.nc`, which carries `SST`
on a 337 × 481 grid over 0–28 °N / 60–100 °E — a superset of the pilot box (7.5–10.5 °N,
77–80.5 °E) and the same 1/12° spacing the fallback already assumes. Re-run the builder, confirm
`pfz_fallback_pilot_region.geojson` still resolves, and only then delete. That frees 10.58 GB and
also makes the fallback refreshable instead of frozen to one August snapshot.

Until someone does that work, this file stays.

---

## 3. Your judgement — unused, but not an exact duplicate

### `etopo_all_india_real.nc` — 12.4 MB

`data/tier1/bathymetry/etopo_all_india_real.nc`

No code reads it; `geospatial.py:39` reads `etopo_all_india_bathymetry.nc`. Both cover exactly
0.008–26.008 °N, 65.008–98.008 °E on an identical 1561 × 1981 grid.

`docs/ORCA_Dataset_Procurement_Runbook.md:184` calls it "a confirmed duplicate". That is very
nearly true but not exactly, and the difference is worth one sentence: comparing the two `z`
arrays cell by cell, **17,264 of 3,092,341 cells differ (0.56%), all of them ocean cells, up to
551 m, 99th percentile 235 m.** They are two slightly different ETOPO renderings, not one file
copied twice.

It is still safe to delete — nothing reads it, and ETOPO is only the *fallback* rung anyway
(GEBCO 2026 at 15″ is preferred, `geospatial.py:369`) — but you are discarding 0.56% of cells
that disagree with the copy you keep, not a byte-identical twin. Flagged so the call is yours.

---

## 4. Looks stale, is not — leave these alone

This is the important half of the audit. Every entry below would fail a "delete anything older
than N days" sweep, and every one of them is load-bearing.

| File / directory | Why it looks stale | Why it stays |
|---|---|---|
| `incois_osf_pfz/pfz/history/20260901/` | Three weeks old, and two newer snapshot dirs sit beside it | **Read as a series.** `analytics_loaders.available_pfz_history_dates()` returns *every* snapshot and `ocean_analytics.py:470` iterates them. Deleting old snapshots deletes the history feature. |
| `cyclone_gaja/*` (except the STUB) | 2018 data, eight years old | The Cyclone Gaja historical replay — `orca/replay/gaja.py`, `api/replay_routes.py`. A replay of a 2018 cyclone needs 2018 data. |
| `tier1/weather/era5_historical_thoothukudi_30d.json` | Dated 2026-09-03, never refreshed | It is a **climatological baseline**. `ocean_analytics.detect_anomaly` compares the forecast against this reference period; a baseline that tracked the present would measure nothing. |
| `tier1/fisheries/cmfri_marine_fish_landings_2024.pdf`, `datagov_marine_fish_landings.csv` | 2024 records | Annual statistics. STATIC by the freshness contract — 2024 is the current edition. |
| `pfz/pfz_parsed_webgis.json`, `pfz_webgis_links.json`, `pfz_webgis_text.txt`, `*_master.json`, `pfz_fallback_pilot_region.json` | Scraper intermediates and JSON twins of files also stored as CSV/GeoJSON | Coverage Guide §170 keeps them **as provenance** — they evidence where a scraped advisory came from. Deliberate, not accidental. |
| `tier1/bathymetry/gebco_2026_n10.5_s7.5_w77.5_e80.5.nc` | Superseded by the 101 MB national GEBCO extract | Still the pilot-box fallback (`geospatial.py:350`) **and** the grid `build_pfz_fallback.py:48` reads for its depth filter. |
| `tier1/bathymetry/etopo_south_india_bathymetry.nc` | Older, smaller, regional | Wired as `ETOPO_PILOT_FILE` (`geospatial.py:40`). |
| ~~`tier1/tiles/bathymetry/{7,8}/**` — 41 tiles dated 2026-09-03~~ **[2026-09-22: resolved, nothing to decide]** | Older than the other 491 tiles in the same pyramid | **Gone, and not by deletion.** These were orphans: tiles from an earlier build that a later, re-scoped build left behind because `generate_layer_tiles` wrote straight into the live directory and only then overwrote `meta.json`. The writer now renders into a `.building` sibling and swaps atomically, and the pyramid was rebuilt. Verified 2026-09-22: **490 PNGs on disk = 490 in `meta.json`**, zooms 5–8, 0 tiles predating the rebuild, 0 stray `.building`/`.old` directories. The advice in this row still stands for the future — never hand-delete tiles, regenerate the pyramid. |
| ~~`tier3/bhuvan/bhuvan_15days_marine_manifest.json`~~ **[2026-09-22: moved to §1.8]** | Dated 2026-08-30, and a newer `bhuvan_manifest.json` sits beside it | **This row is now wrong and is kept only to show why.** It was correct on 2026-09-19: this was the file the reader opened. The §6.1 wiring bug was fixed by moving the catalogue into `bhuvan_manifest.json` and repointing the reader, so this file is no longer read by anything. See §1.8. |
| `tier1/boundaries/2011_Dist.{dbf,prj,shx}` | Tiny files next to a 10 MB `.shp` | Shapefile sidecars. A `.shp` without its `.dbf` and `.shx` is unreadable. All four or none. |
| `incois_osf_pfz/south_india_marine_grid.{csv,geojson}`, `dataset_manifest.json` | Dated 2026-08-30 | The grid is rung 2 of `nearest_osf_point_forecast`; the manifest carries the **INCOIS CC-BY 4.0 licence**, recorded nowhere else in the repo. Deleting it deletes ORCA's right to cite the data. |

---

## 5. Optional — previous-run granules

**[2026-09-22: this section has shifted by one run.]** The daily job has since fetched the **20260921** set, so there are now three dated runs on disk (0915, 0917, 0921) where the audit saw two. Under this section's own "keep one previous run" rule the *current* previous run is **0917**, and the 0915 set has dropped to two runs back:

`RSMC_hycom_20260915.nc`, `SST_NIO_20260915.nc`, `rsmc_combined_ww3_20260915.nc` — 427 MB (408 MiB), **now eligible**.

Re-verified 2026-09-22 against all three questions in §8. No code names them: the only grep hit for `20260915` is a fixture string inside `refresh_osf_forecasts.py`'s own self-check assertion, not a file read. Every reader takes the newest of a glob and would now pick 0921 — `voyage.py:80` and `geospatial.py:462` both `sorted(...)[-1]`, `generate_pan_india_waves.py:33` uses `max(...)`, `extract_osf_pilot.py:41-42` uses `_newest`. And they are not a last copy: 0917 and 0921 carry the same six WW3 variables and the same `UVEL`/`VVEL`. Keeping 0917 preserves the insurance policy this section exists for.

The original text follows, and still applies to whichever run is the most recent one back:

~~`RSMC_hycom_20260915.nc`, `SST_NIO_20260915.nc`, `rsmc_combined_ww3_20260915.nc` — 427 MB.~~

Superseded by the 17 September run and not read. **Recommendation: keep them.** One previous run
is a cheap insurance policy against a refresh landing a corrupt or truncated file, which is not
hypothetical — the MOSDAC transfers dropped mid-file on almost every attempt (contract §6.3).
Delete only if you are short of disk.

The same logic applies to the September MOSDAC granules that are not the newest
(SST 11–16 Sep, chlorophyll 12–14 Sep). Keep a few days; they cost ~100 MB.

---

## 6. Two wiring problems this audit surfaced — **both fixed 2026-09-22**

Neither was a deletion, which is why this section existed separately. Both have now been fixed in
code; the original text of each is kept so the reasoning is still readable.

1. ~~**The Bhuvan manifest refresh writes a file nobody reads.**~~ **FIXED 2026-09-22.** The fix went
   into the writer, not the freshness entry: repointing the contract at the file the reader opened
   would have looked like a one-line rename and silently broken it, because the two manifests have
   **different schemas** — `bhuvan_manifest.json` had no `core_wms_services` key at all, so the
   reader would have returned `[]` with a green badge above it. `refresh_bhuvan_manifest.py` now
   owns a `WMS_SERVICES` constant for the four OGC endpoints in use and writes them into
   `bhuvan_manifest.json`, and `load_bhuvan_wms_services()` reads that same file. One file is now
   written, monitored and read. Verified: `local_catalog("bhuvan_wms")` returns 4 services. The
   file this orphaned is §1.8. Original finding:

   > **The Bhuvan manifest refresh writes a file nobody reads.**
   `scripts/refresh_bhuvan_manifest.py:60` writes `bhuvan_manifest.json`, but
   `analytics_loaders.load_bhuvan_wms_services()` reads `bhuvan_15days_marine_manifest.json`.
   So the refresh script runs, succeeds, and changes nothing the app sees — while the file the app
   does read has not been updated since 30 August. One of the two names has to move.

2. ~~**`_cmems_newest()` picks by mtime, not content date.**~~ **FIXED 2026-09-22.** Described in
   §1.5. Deleting the two stale granules would have removed only today's exposure; the selector
   itself now sorts on `content_date_from_name()` — the same parser the freshness contract grades
   these files with — so the SST fallback rung and the badge above it can no longer disagree, and
   restoring a backup can no longer reorder the directory into serving August data as current.

   One wrinkle worth recording, because the obvious version of this fix is wrong and was caught
   only by running it: sorting undated filenames *oldest* regresses the selection. CMEMS ships the
   rolling near-real-time product under a fixed undated name (`cmems_thetao_india_nrt.nc`) and
   archives snapshots under dated ones, so an undated file is current by construction and must sort
   **newest** — otherwise the September archive beats today's NRT data. mtime survives only as a
   tiebreak. Guarded by `tests/unit/test_loaders.py::test_cmems_picks_the_current_file_even_if_a_stale_one_was_written_last`, which backdates the
   August extract's mtime to now and asserts the NRT file still wins.

   **This does not retire §1.5.** The two superseded granules are still unread and still deletable;
   they are simply no longer a trap.

---

## 7. Summary

| Tier | What | Files | Size |
|---|---|---:|---:|
| §1 | Safe to delete — verified unused | 44 | **9.51 GB** |
| §2 | Blocked on a code change (`RSMC_hycom_20260830.nc`) | 1 | 10.58 GB |
| §3 | Unused, not an exact duplicate (`etopo_all_india_real.nc`) | 1 | 0.01 GB |
| §5 | Two runs back (0915) — **now eligible [2026-09-22]** | 3 | 0.43 GB |
| §5 | One run back (0917) — recommended keep | 3 | 0.43 GB |
| | **`data/` on 2026-09-19** | 26,020 | 21.72 GB |
| | **`data/` today (2026-09-22, after both refresh jobs)** | 26,449 | **22.35 GB** |

Acting on §1 alone takes `data/` from 22.35 GB to about 12.8 GB; adding the now-eligible 0915 run
from §5 takes off a further 0.43 GB. Doing the §2 code change as well takes it to roughly 2.2 GB.

**The §1 file count is 44, not 43+1:** §1.8 was added and nothing was removed, because all 43
original files were re-confirmed present and unreferenced on 2026-09-22. The GB figure is unchanged
because §1.8 is 11 KB.

---

## 8. Re-running this audit

The three questions, in order, for any file you are unsure about:

```bash
# 1. Does any code name it, or glob its directory?
grep -rn "<filename or its glob>" --include=*.py --include=*.ts --include=*.tsx \
     backend/orca backend/scripts scripts frontend/app

# 2. If a glob — does the reader take the newest, or all of them?
#    `_newest(...)` / `sorted(...)[-1]` / `max(...)`  -> older files are dead
#    a bare `for path in dir.glob(...)`               -> it is a series; leave it

# 3. Is it the last copy of a variable?
python -c "import xarray as xr; print(list(xr.open_dataset('<path>').data_vars))"
```

If all three come back clean, add it here with the evidence — not to a delete script. `data/` is
gitignored, so a wrong deletion is permanent.
