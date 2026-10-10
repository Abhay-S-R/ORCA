# Marine Fish Species Data Pipeline

An automated Python pipeline that integrates, harmonizes, and validates marine fish species data across Indian waters by merging three complementary sources:

1. **OBIS (Ocean Biodiversity Information System)**: Verified observed spatial occurrences from scientific cruises (FORV *Sagar Sampada*, CMLRE, IndOBIS).
2. **AquaMaps**: Predicted half-degree (0.5° × 0.5°) grid environmental habitat suitability distributions.
3. **CMFRI (ICAR-Central Marine Fisheries Research Institute)**: Ground-truth commercial landing statistics from official annual publications and data.gov.in.

All taxonomic entities are harmonized using **WoRMS (World Register of Marine Species) AphiaIDs**, evaluated with a multi-factor confidence model, and spot-checked against **FishBase** benchmarks.

---

## 1. Quickstart

### Installation
Ensure dependencies are installed:
```bash
pip install -r scripts/marine_species_pipeline/requirements.txt
```

### Execution Options

#### A. Run for a Specific Ocean Area (User WKT Polygon)
```bash
python -m scripts.marine_species_pipeline.pipeline \
  --wkt "POLYGON((80.2 12.5, 80.8 12.5, 80.8 13.2, 80.2 13.2, 80.2 12.5))" \
  --prob-threshold 0.5 \
  --output-dir data/marine_species_output
```

#### B. Run for Entire Indian Waters (Arabian Sea, Bay of Bengal, Andaman Sea)
```bash
python -m scripts.marine_species_pipeline.pipeline \
  --all-india \
  --prob-threshold 0.5 \
  --output-dir data/marine_species_output
```

#### C. Run with Optional Depth Constraints
```bash
python -m scripts.marine_species_pipeline.pipeline \
  --wkt "POLYGON((80.2 12.5, 80.8 12.5, 80.8 13.2, 80.2 13.2, 80.2 12.5))" \
  --depth-min 10 \
  --depth-max 100
```

---

## 2. Pipeline Architecture & Workflow

```
[OBIS API (api.obis.org/v3)]    [AquaMaps (0.5° Grid Model)]    [CMFRI 2024 Booklet (pdfplumber)]
       │                                     │                                    │
       ▼                                     ▼                                    ▼
  obis_species.csv                  aquamaps_species.csv                 cmfri_landings.csv
       │                                     │                                    │
       └──────────────────────────────┬──────┴────────────────────────────────────┘
                                      ▼
                        [WoRMS REST API Harmonization]
                         (Valid Name & AphiaID Merge)
                                      ▼
                            [Confidence Scoring]
                           (High / Medium / Low)
                                      ▼
                        [FishBase Benchmark Validation]
                                      ▼
                            final_species_list.csv
```

---

## 3. Confidence Scoring Methodology

| Confidence | Definition & Criteria |
| :--- | :--- |
| **High** | Present in **OBIS** observed occurrence records (supported by survey telemetry, and often corroborated by AquaMaps or regional landings). |
| **Medium** | Modeled in **AquaMaps** with probability $\ge 0.5$ AND actively landed according to **CMFRI** for the spatially matched coastal state. |
| **Low** | Modeled in **AquaMaps only** without field sampling, OR recorded in **CMFRI landings** without spatial ocean records in that polygon. |

---

## 4. Output Deliverables

The pipeline produces four CSV files and a JSON audit report in `data/marine_species_output/`:

1. `obis_species.csv`: Direct scientific observations, total record counts, last observed year, depth ranges, and dataset attribution.
2. `aquamaps_species.csv`: Environmental suitability predictions aggregated across overlapping half-degree cells (`max_probability`, `mean_probability`, `cells_count`).
3. `cmfri_landings.csv`: Commercial fisheries landing tonnages by state and species extracted directly from CMFRI reports via `pdfplumber`.
4. `final_species_list.csv`: Merged master table indexed by WoRMS `aphia_id`, with source boolean flags, numerical metrics, and confidence ratings.
5. `species_pipeline_report.json`: Execution metadata, source overlap matrices, warning logs, and FishBase spot-check results.

---

## 5. Automated Cron Job & Refreshment

Because OBIS incorporates new cruise surveys and CMFRI releases seasonal/annual bulletins, an automated refresh runner is provided.

### Manual Run
```bash
python -m scripts.marine_species_pipeline.cron_refresh --all-india
```

### Running as a Background Daemon (e.g. Every 24 Hours)
```bash
python -m scripts.marine_species_pipeline.cron_refresh --all-india --interval-hours 24
```

### Setting up a System Cron Job (Linux / macOS)
Add to your `crontab -e` to run weekly at 02:00 AM on Sundays:
```cron
0 2 * * 0 cd /path/to/ORCA && python -m scripts.marine_species_pipeline.cron_refresh --all-india
```

### Setting up on Windows (Task Scheduler)
Use PowerShell:
```powershell
$Action = New-ScheduledTaskAction -Execute 'python' -Argument '-m scripts.marine_species_pipeline.cron_refresh --all-india' -WorkingDirectory 'c:\Users\hemab\OneDrive\Desktop\ORCA'
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2am
Register-ScheduledTask -Action $Action -Trigger $Trigger -TaskName "ORCA_Marine_Species_Refresh"
```

Execution history is recorded in `scripts/marine_species_pipeline/.cache/cron_refresh_history.json`.

---

## 6. Known Limitations & Scientific Truths

1. **Telemetry vs. Biology**: Satellite radiometry (SST, Chlorophyll-$a$) identifies productive ocean fronts (Potential Fishing Zones), but **cannot sense underwater species identities or depth multipliers**.
2. **Survey Sampling Sparsity**: Low OBIS record counts in an offshore bounding box indicate sparse sampling effort in that specific box, **not biological absence**.
3. **Spatial Resolution of Catch**: CMFRI landings are recorded at coastal landing harbours (~1,265 centres), not mid-ocean GPS coordinates. Spatial matching maps coordinates to coastal maritime states.
4. **AquaMaps Public API**: `aquamaps.org` returns HTTP 403 and does not provide an open public REST API; this pipeline relies on the official 0.5° grid environmental envelope model and supports local SQLite dumps (`am.db`).
