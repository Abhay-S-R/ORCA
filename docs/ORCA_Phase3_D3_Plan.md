# ORCA Phase 3 — D3 Implementation Plan (Reasoning Graph, Voyage & Flow Fields)

Solo-build plan for D3 only. D1 (Language, Voice, Personas & Critic) and D2
(Sentinel, Alerting, Feedback & District Ops) are being built in parallel by
teammates, nothing from either has landed on `origin/main` yet. This plan
does not follow `ORCA_Phase3_Plan.md`'s Day-15→Day-21 calendar — that
schedule assumes three people synced on one shared week; D3 is built here in
whatever order is technically sensible for one contributor.

**Scope decisions carried over from the planning conversation (not to be
re-litigated mid-build):**

1. `VoyagePlan` / `RouteSegment` are added directly to the shared
   `backend/orca/contracts.py` now, additive-only, no teammate coordination
   needed first.
2. The flow-field overlay ships **both** vector fields at once: live HYCOM
   currents (already wired) and archived MOSDAC/ScatSat wind — each with its
   own honest freshness label. The wind data is a stack of daily snapshots
   (day-of-year 225–239, 2026 = mid-to-late August), not a live feed, and
   must never be presented as if it were.
3. Two pieces are **hard-blocked on teammates' unshipped work** and are
   explicitly **out of scope for now**, with no fixture stand-in:
   - the dashed Critic-loop edge on `/reasoning` (needs D1's Agent 10 output)
   - Sentinel watch badges on the map (needs D2's notification/watch feed
     shape)

## 0. One technical fact this plan depends on

`data/incois_osf_pfz/osf_ww3/rsmc_combined_ww3_20260829.nc` (WW3 wave
forecast) has a real `TIME` dimension of **56 steps at a 3-hour stride**
(168 hours = 7 days of forecast lead time), confirmed via:

```
TIME: 56, units "hours since 0001-01-01 00:00:00", calendar "standard"
diffs between steps: {3.0} (hours)
```

This means genuine **per-segment-ETA** wave-height sampling for the voyage
corridor is real and worth building, not a false promise — a multi-day
route can sample each segment's hazard at the forecast hour closest to when
the vessel would actually be there, not just at departure time.

The file's time units (`hours since 0001-01-01`) overflow pandas'
nanosecond-precision `datetime64`, which is why plain `xr.open_dataset()`
raises (and why it falls through to a `cftime` import that isn't installed).
No new dependency is needed to fix this: `datetime.datetime` itself handles
year-1 dates fine, so decode manually —

```python
from datetime import datetime, timedelta
step_time = datetime(1, 1, 1) + timedelta(hours=float(ds["TIME"].values[i]))
```

— and open the file everywhere else with `decode_times=False`. This goes in
the new voyage module (§3 below), not in `geospatial.py`'s existing
`_hycom()`/`_bathymetry()` cache helpers, since it's WW3-specific.

## 1. Backend contracts — `backend/orca/contracts.py`

Additive only, appended after `ChartSpec`. Mirrors the existing dataclass
style (frozen, `SourceProvenance`/`Confidence` embedded, no new `Literal`
values needed on `MapLayer` — `"Polyline"` already exists and is unpopulated).

```python
@dataclass(frozen=True)
class RouteSegment:
    """One geodesic leg of a VoyagePlan, already resolved to a hazard class —
    the frontend renders these, it does not reclassify them."""
    segment_id: str
    start: tuple[float, float]  # (lat, lon)
    end: tuple[float, float]
    distance_nm: float
    eta: str  # ISO 8601 UTC — when the vessel is expected to be at `end`
    hazard_class: Literal["SHALLOW", "BOUNDARY", "MPA", "ROUGH_SEA", "LIGHTNING", "CLEAR"]
    status: Literal["CLEAR", "CAUTION", "BLOCKED"]
    detail: str  # e.g. "Depth 3.2m at draft 4.0m — BLOCKED" — the sentence a waypoint-table row needs, not just the enum
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True)
class VoyagePlan:
    """Agent 6/8-adjacent voyage-corridor output (plan §5.1, D3-owned).
    `verdict` rolls up per-segment status to the same GO/CAUTION/NO_GO
    vocabulary risk_assessment.py already uses — any BLOCKED segment forces
    NO_GO, never averaged (Ground Rule 4)."""
    voyage_id: str
    origin: tuple[float, float]
    destination: tuple[float, float]
    vessel_class: str
    departure_time: str  # ISO 8601 UTC
    segments: tuple[RouteSegment, ...]
    verdict: Literal["GO", "CAUTION", "NO_GO"]
    verdict_reason: str
    corridor_geojson: dict[str, Any]  # the ~2NM-buffer polygon, for the map layer
    confidence: Confidence
```

No `MapLayer.layer_type` change needed — `"Polyline"` is already declared,
just unused. No `TraceGraph`/`Notification`/`PersonaRender`/`Dispatcher`
additions here — those are D1/D2's contracts to add when they're ready.

## 2. Voyage-corridor computation — new `backend/orca/agents/voyage.py`

Not wired into the LangGraph as a graph node — voyage planning is a
separate, on-demand product surface (like `/map-layers` or
`/current-vectors`), not a query-driven agent hand-off. It's a new module
because it has a distinct concern (a route, not a point query), but it
**reuses** Agent 6's existing full-precision functions rather than
reimplementing spatial logic:

- `geospatial.point_in_polygon(lat, lon)` — MPA/boundary hard-constraint checks per sample point
- `geospatial.check_boundary_proximity(lat, lon, boundary_name)` — IMBL proximity
- `geospatial.depth_at_point(lat, lon)` — SHALLOW hard constraint vs. vessel draft
- `geospatial.bearing_and_distance(...)` — already geodesic (pyproj), reused for leg bearing display

New in `voyage.py`:

- `densify_route(origin, destination, *, step_nm=1.0) -> list[(lat, lon)]` —
  `pyproj.Geod.npts()` geodesic densification between the two endpoints (not
  a straight great-circle-on-a-flat-map lerp — matches how `bearing_and_distance`
  already does geodesy in `geospatial.py`).
- `_ww3_wave_height_at(lat, lon, when: datetime) -> float | None` — nearest
  WW3 grid cell + nearest of the 56 3-hourly steps to `when` (§0's manual
  time decode); returns `None` (not 0.0) outside the WW3 file's spatial or
  temporal coverage so a caller can degrade confidence honestly rather than
  silently reporting calm seas it never measured.
- `classify_segment(...) -> RouteSegment` — hard constraints (SHALLOW,
  BOUNDARY, MPA) always win over soft ones (ROUGH_SEA, LIGHTNING) when both
  fire on one segment, same "worst tier wins" rule as Ground Rule 4.
- `plan_voyage(origin, destination, vessel_class, departure_time, speed_kn) -> VoyagePlan`
  — walks the densified points in order, assigns a running ETA from
  cumulative distance / speed, buckets consecutive points into segments,
  classifies each, buffers the corridor polygon at ~2NM (`shapely.buffer`
  on a locally-projected line, consistent with the rest of `geospatial.py`'s
  shapely usage), and rolls up the verdict (any `BLOCKED` segment ⇒ `NO_GO`;
  any `CAUTION` and no `BLOCKED` ⇒ `CAUTION`; else `GO`).

Self-check: `if __name__ == "__main__":` block asserting (a) a route
crossing a known-shallow cell classifies `BLOCKED`/`SHALLOW`, (b) a clear
open-water route classifies `GO`, (c) segment ETAs are monotonically
increasing — matching the existing assert-based pattern in
`geospatial.py`/`risk_assessment.py`. Plus one `pytest` in
`backend/tests/unit/test_voyage.py` asserting full-precision (not
simplified/decimated) geometry is used for the corridor containment check,
mirroring the existing precision test in `test_geospatial.py` — this is the
"genuinely sophisticated part" the plan calls out, so it gets its own test,
not just the `__main__` smoke check.

## 3. Wind vectors — `geospatial.py` addition + new endpoint

Mirrors `current_vectors()` exactly (§2 of the prior research), added right
after it in `geospatial.py`:

```python
WIND_DIR = DATA_ROOT / "tier3" / "mosdac" / "Wind"

def wind_vectors(stride: int = 4) -> dict[str, Any]:
    """Archived ScatSat gridded wind (§ tier3/mosdac/Wind/*.nc) — the most
    recent snapshot on disk, cropped to the pilot bbox. NOT a live feed:
    returns its own acquisition date so the caller can label it honestly,
    same shape as current_vectors() otherwise (U/V -> speed_ms/direction_deg)."""
```

Picks the lexicographically-latest `E06SCTL4AW_*.nc` file (day-of-year in
the filename), decodes U/V the same way `current_vectors()` does, and
returns `{"points": [...], "bounds": [...], "acquisition_date": "2026-08-27"}`
(parsed from the filename's day-of-year, not "now" — that's the whole point
of the honest label).

New route in `geospatial_routes.py`, same pattern as `/current-vectors`:

```python
@router.get("/wind-vectors")
def wind_vectors_route() -> dict: ...
```

New route in a new `backend/orca/api/voyage_routes.py` (mirrors
`geospatial_routes.py`'s `APIRouter(prefix="/api", tags=[...])` mounting
pattern), one line added to `main.py`:
`app.include_router(voyage_router)`:

```python
@router.post("/voyage-plan")
def voyage_plan_route(req: VoyagePlanRequest) -> dict: ...
```

## 4. Frontend — flow overlay (`MapView.tsx`)

Extends the existing `MapboxOverlay` + `WindParticleLayer` setup that
already renders currents. Both layers passed into the same
`overlay.current.setProps({ layers: [...] })` call, not two separate
overlays:

- Currents layer: unchanged, still labeled live (HYCOM).
- New wind layer: same `WindParticleLayer`, distinct color ramp (so the two
  are visually distinguishable, never overlapping in the same hue), its own
  `LayerToggle` entry reading `wind-vectors` response's `acquisition_date`
  into the legend text — e.g. "Wind (archived — Aug 27, 2026)" vs. "Currents
  (live)". Registered in `HEAVY_KEYS` (both particle layers are GPU-heavy)
  so the existing LRU eviction budget covers it without new eviction logic.
  Wired through `measureLayerToggle`/`reportLayerMetrics` on toggle, same as
  every other heavy layer already is.

## 5. Frontend — `/voyage` page

Replaces the current `Planned` stub. Reuses the existing `MapView` instance
rather than a second map (one MapLibre instance is already the pattern
elsewhere in the app):

- Origin/destination pickers: click-to-set on the map (two click states,
  origin then destination), with lat/lon fallback text inputs for precision.
- Vessel draft / class / departure-time / speed inputs — a small form panel,
  same `Panel` component pattern already used elsewhere in `MapView.tsx`.
- On submit: `POST /api/voyage-plan`, render `corridor_geojson` as a new
  `Polyline` `MapLayer` (via the Agent 8 generator in §6) colored **and**
  text-labeled per segment status (never color-alone — CLEAR/CAUTION/BLOCKED
  as both a stroke color and a small status chip at the segment midpoint,
  since color-only fails the same accessibility bar the rest of the app
  holds to).
- Waypoint table below the map: lat/lon, ETA, depth, hazard class, per
  segment — the sentence-level `detail` field from `RouteSegment` renders
  directly, no client-side re-derivation of what the backend already computed.
- Tidal berthing windows: reuses `ocean_analytics.predict_tides()` /
  `nearest_station()` as-is (already built in Phase 2) for the
  destination point — no new tide logic, just calling the existing function
  with the voyage's destination coordinates and rendering its existing
  output shape.
- Hazard summary: a one-line rollup of the `verdict`/`verdict_reason`, same
  visual weight as the `/safety` page's GO/CAUTION/NO_GO badge, for
  consistency across the app.

## 6. Backend — Agent 8 route-layer generator (`visualization.py`)

One new function, e.g. `voyage_route_layer(plan: VoyagePlan) -> MapLayer`,
populating the `Polyline` `layer_type` (declared, currently unused) from a
computed `VoyagePlan`'s `corridor_geojson` — a GeoJSON `LineString`/`Polygon`
FeatureCollection with per-segment `status` as a feature property, which is
what the frontend's per-segment coloring in §5 keys off. Ground Rule 2
applies here same as every other Agent 8 function: this shapes an
already-computed `VoyagePlan`, it does not itself do hazard reasoning.

## 7. Frontend — `/reasoning` page

Replaces the current `Planned` stub. React Flow (`@xyflow/react`, already
installed) + `dagre` for auto-layout (**not currently in
`frontend/package.json`** — confirmed via grep, needs
`npm install dagre @types/dagre` before this page can be built; every other
D3 frontend dependency is already present).

**One open design call, flagging it rather than deciding it silently:**
the real `/query` SSE stream today only carries
`{type: "agent_span", agent_name, status}` per node — no reasoning summary,
source count, or depth (confirmed in `trace.py`/`main.py`). A genuinely
"live" reasoning graph with rich per-node content isn't buildable against
what the backend actually emits right now; that richer shape is D1's
`TraceGraph` contract to add. Building `/reasoning` against a fixture that
*pretends* to be live per-node content would violate the same honesty rule
`Planned.tsx` itself documents (Ground Rule 3 — never fake data to look more
finished than it is).

**Plan: build `/reasoning` as replay-only for now.** A self-authored fixture
file matching D1's documented `TraceGraph` shape from the Phase 3 plan's
§5.1 contracts table drives a **static, clearly-labeled example trace**
("Example trace — replay" in the page header, not "Live"). This gets the
real UI built — DAG layout, node inspector drawer, edge styling, the
Critic-loop dashed edge *slot* left empty/hidden rather than wired to
nothing — and when D1 ships the real `TraceGraph` endpoint, swapping the
fixture fetch for a real `GET /trace/{query_id}` call is a one-line change,
not a rebuild. The live per-node "agent_span" events the real SSE stream
already emits can additionally drive a **thin live strip** (just node
status pips lighting up in order, no rich content) above the replay graph,
since that much is honestly supported by what exists today — this is a
nice-to-have addition, not required to call `/reasoning` done.

If this replay-only framing isn't what's wanted (e.g. skip the live strip
entirely, or hold the whole page until D1 ships `TraceGraph`), that's a
one-line answer, not a rebuild — flagging now rather than guessing.

Components: `AgentNode` (status color, agent name, confidence badge),
directed edges laid out via `dagre` (computed once per trace, not
re-laid-out per frame — matches the plan's own performance note), a node
inspector drawer on click showing that node's fixture detail. Critic-loop
edge and Sentinel watch badges: not built, not stubbed, per the explicit
scope exclusion — no dashed edge placeholder, no fake badge slot, nothing
that implies work exists where it doesn't.

## 8. Explicit non-scope (do not build, not even fixture-backed)

- Dashed Critic-loop edge on `/reasoning` — needs D1's Agent 10.
- Sentinel watch badges on the map — needs D2's notification/watch feed shape.

## 9. Build order (no calendar, just dependency order)

1. `contracts.py` additions (§1) — everything else imports these.
2. `voyage.py` module + its `pytest`/`__main__` self-checks (§2) — the
   hardest, most-isolated piece; get it right in isolation before wiring UI to it.
3. `geospatial.wind_vectors()` + both new routes (§3) — small, mirrors an
   existing function almost line-for-line.
4. Agent 8 `voyage_route_layer()` (§6) — thin, depends on §1+§2.
5. `MapView.tsx` dual-vector-field overlay (§4) — independent of voyage work, can slot in any time after §3.
6. `/voyage` page (§5) — depends on §2+§3+§4+§6 all being live.
7. `npm install dagre @types/dagre`, then `/reasoning` page + fixture (§7) — fully independent of 1–6, could equally be done first.
