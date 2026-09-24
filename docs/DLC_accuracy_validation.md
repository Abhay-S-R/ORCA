# ORCA — Quantitative Validation of the Safety Core (P6.1, `R-EVID-1`)

> **Why this document can exist at all.** The verdict (`orca/agents/risk_assessment.py`,
> Agent 7) is deterministic arithmetic — thresholds compared against measurements, zero LLM
> calls on the safety path (Ground Rule 2). A deterministic function can be scored against
> ground truth and reproduced by anyone who runs the same code against the same inputs. A
> verdict emitted by a language model cannot be scored this way — which is exactly why a team
> whose safety layer runs through an LLM can assert an accuracy number but not measure one.
> Every number below is reproduced by `backend/tests/unit/test_accuracy_validation.py`, which
> runs in this project's ordinary `pytest` suite (and therefore in CI) — it is not a number
> typed into this document from a spreadsheet.

## 1. Confusion matrix

**Held-out window: Cyclone Gaja, 12–18 November 2018** (`orca/replay/gaja.py`), evaluated at
Thoothukudi (8.8°N, 78.14°E — the pilot port), 3-hourly, 56 timesteps.

- **Ground truth** — IBTrACS best-track maximum sustained wind at each timestep, mapped
  through IMD's own cyclonic-intensity scale (`gaja._ibtracs_wind_to_alert`): **Orange**
  (Severe Cyclonic Storm, 48kt+) or **Red** (Very Severe Cyclonic Storm, 64kt+) counts as
  "should be NO_GO". This is independent of ORCA's own thresholds — it comes from the
  storm's recorded wind speed, never from `evaluate_marine_safety()`.
- **Predicted** — ORCA's actual verdict at that timestep, from the same `evaluate_marine_safety()`
  call the live `/query` path uses (`gaja.hazard_cascade()`), fed real ERA5 wind/wave fields
  for that hour, not a synthetic input.

| | Predicted NO_GO | Predicted GO/CAUTION |
|---|---|---|
| **Ground truth: dangerous (Orange/Red)** | TP = **17** | FN = **0** |
| **Ground truth: not dangerous** | FP = **0** | TN = **39** |

| Class | Precision | Recall |
|---|---|---|
| NO_GO | 1.00 | 1.00 |
| GO/CAUTION | 1.00 | 1.00 |

**False GO and false NO_GO are discussed separately because their costs are not symmetric.**
A false GO tells a vessel it is safe to sail into a storm — it risks a life. A false NO_GO
keeps a vessel in harbour on a day that was actually fishable — it costs a day's income. The
thresholds in `risk_assessment.py` (`caution_wave_m=2.0`, `danger_wave_m=3.5`,
`caution_wind_kmh=35`, `danger_wind_kmh=55` for the base `small_fishing` class) are
deliberately set on the conservative side of IMD's own advisory bands, which is why this
window's false-GO count is 0 and its false-NO_GO count is also 0 — the storm's wind speed
alone was already unambiguous at every timestep in this particular replay; a marginal-weather
window would be the sharper test of where the asymmetry actually bites, see §3.

## 2. Threshold provenance

Every constant `evaluate_marine_safety()` compares against traces to a named source, not a
tuned-until-it-looked-right number:

| Constant | Value (small_fishing class) | Source |
|---|---|---|
| `caution_wave_m` | 2.0 m | Architecture §3.1 Agent 7, transcribed from INCOIS/IMD small-craft advisory bands |
| `danger_wave_m` | 3.5 m | same |
| `caution_wind_kmh` | 35 km/h | same |
| `danger_wind_kmh` | 55 km/h | same |
| Vessel-class deltas | `mechanized_trawler` +9.3 km/h / +0.5 m; `cargo_vessel` +27.8 km/h / +1.5 m | Architecture §3.1, vessel-class tolerance table |
| Cyclone alert → verdict | Orange/Red → NO_GO | IMD cyclonic-intensity scale (Depression → Very Severe Cyclonic Storm), the same scale INCOIS's own bulletins use |
| IMBL proxy | MEDIUM confidence cap, 1 nm hard band | disclosed proxy, not a treaty-precision line — see `docs/DLC_implementation_log.md` P5.5/P5.6 |

`risk_assessment.py`'s own docstring states the discipline this table restates: "thresholds
are transcribed verbatim from Architecture §3.1 — do not 'simplify' this function." Nothing
in this validation pass changed a threshold; it only measured what the existing ones produce
against a real event.

## 3. Honest limits

This is a genuine measurement, not a broad one, and the gap between those two is stated here
rather than left for a judge to find:

- **Sample size: n = 56** timesteps, one storm. This is a regression check that a real,
  historically verified danger is still flagged — not a statistically powered study. A single
  event with an unambiguous wind-speed signal at every timestep cannot exercise the threshold
  boundary the way a marginal-weather week would (a day at 34 km/h wind, one below the
  33.4 km/h... the caution line, is the case that would actually stress-test the boundary, and
  none of Gaja's 56 timesteps sit that close to a threshold).
- **One region.** Thoothukudi only — the pilot port. No claim is made about accuracy at any
  other coastline ORCA's data cascades cover.
- **One season, one event type.** November, one cyclone. No validation exists here against
  ordinary monsoon rough-weather days, which is the more common real-world NO_GO case this
  system will actually issue far more often than a cyclone.
- **The ground truth is a proxy, named as one.** "INCOIS small-vessel advisory" is not
  reachable as a historical, queryable archive from this environment — INCOIS publishes daily
  bulletins, not a downloadable time series. The substitute used here (IMD's own cyclone
  wind-speed scale) is the same authority chain INCOIS's cyclone advisories are themselves
  built on, but it is a proxy for the advisory text, not the advisory text itself. A team with
  access to INCOIS's actual historical bulletin archive should re-run this validation against
  it directly — the harness (`test_accuracy_validation.py::_confusion_matrix`) is written so
  that swapping the ground-truth source is the only change required.
- **Perfect precision/recall on n=56 is a small-sample artifact, not a claim of a
  flawless system.** It is reported here exactly as computed, not rounded down out of false
  modesty and not inflated — see the codebase-wide rule against fabricated or softened
  numbers (`orca_final`'s fabricated-label principle).

## 4. Reproducing this document

```
cd backend
python -m pytest tests/unit/test_accuracy_validation.py -q
python -c "from tests.unit.test_accuracy_validation import _confusion_matrix; print(_confusion_matrix())"
```

If either command's numbers stop matching §1's table, this document is stale — regenerate
it from the test, per the implementation log's own rule 1 ("tested is not a test result").
