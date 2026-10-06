# Sea Route Voyage — File Plan

## Stack detected
- **Backend**: FastAPI + Python, Shapely + pyproj (already installed), SQLAlchemy/Postgres for saved voyages, `lru_cache` for in-memory caches, `APIRouter` pattern — one file per feature slice, mounted via `app.include_router()` in `main.py`.
- **Frontend**: Next.js 16 (App Router) + React 19, MapLibre GL JS v6, Tailwind v4, Framer Motion, Lucide icons. Existing design tokens (`ocean-cyan`, `shelf-1/2/3`, `ink`, `hairline`, `glass`, `tactical-frame`…). `Panel`, `Button`, `Field`, `Readout`, `Badge`, `PageHeader` components reused verbatim.

---

## New files to CREATE

### Data prep scripts (`scripts/`)
| File | Purpose |
|------|---------|
| `scripts/prep_land.py` | Clip OSM land polygons to India bbox, simplify, save `data/sea_route/land_india.geojson` |
| `scripts/prep_ports.py` | Merge NGA World Port Index + UN/LOCODE + fishing_harbours.csv → `data/sea_route/ports.geojson` |
| `scripts/prep_maritime_boundaries.py` | Clip IMBL lines to India neighbours, buffer 2 nm → `data/sea_route/restricted_areas.geojson` |
| `scripts/prep_eez.py` | Extract India EEZ polygon → `data/sea_route/india_eez.geojson` |
| `scripts/prep_protected.py` | Filter WDPA marine areas, IND → `data/sea_route/protected_areas.geojson` |
| `scripts/prep_fishing_zones.py` | Validate & normalise `data/raw/fishing_zones.geojson` → `data/sea_route/fishing_zones.geojson` |
| `scripts/prep_all.py` | Master script: runs all prep steps in order |
| `scripts/validate_sea_route_data.py` | Print counts per dataset, report anything outside India bbox |

### Backend — routing engine (`backend/orca/sea_route/`)
| File | Purpose |
|------|---------|
| `backend/orca/sea_route/__init__.py` | Package marker |
| `backend/orca/sea_route/config.py` | Dataclass: `SeaRouteConfig` — grid cell size, land buffer nm, EEZ enabled, depth enabled, draft m |
| `backend/orca/sea_route/datasets.py` | `@lru_cache` loaders for all 6 datasets (land, ports, EEZ, restricted, protected, zones) |
| `backend/orca/sea_route/grid.py` | `build_grid()` — numpy bool array, `SeaGrid` dataclass, `snap_to_sea()` |
| `backend/orca/sea_route/astar.py` | `astar_route()` — 8-dir A* on the grid, haversine cost, returns list of (row, col) |
| `backend/orca/sea_route/smoother.py` | `smooth_path()` — line-of-sight visibility graph pruning against land+restricted polygons |
| `backend/orca/sea_route/router.py` | `sea_route()` — top-level function: snap → A* → smooth → [start]+path+[end], return coords + distance_nm |
| `backend/orca/sea_route/ports_service.py` | `list_ports()`, `get_port()`, `nearest_sea_cell_for_port()` |
| `backend/orca/sea_route/zones_service.py` | `list_zones()`, `zone_entry_point()` — nearest boundary point to a given port |

### Backend — API slice (`backend/orca/api/sea_route_routes.py`)
Single `APIRouter(prefix="/api", tags=["sea-route"])` following the identical pattern of `voyage_routes.py`.

Endpoints:
- `POST /api/sea-route` — main routing endpoint
- `GET /api/sea-route/ports` — port list
- `GET /api/sea-route/fishing-zones` — GeoJSON
- `GET /api/sea-route/restricted-areas` — GeoJSON

### Backend — wire-up (`backend/orca/api/main.py` — 1 line added)
```python
from orca.api.sea_route_routes import router as sea_route_router
app.include_router(sea_route_router)
```

### Frontend — page (`frontend/app/sea-route/`)
| File | Purpose |
|------|---------|
| `frontend/app/sea-route/layout.tsx` | Minimal layout wrapper (matches `/voyage/layout.tsx` pattern) |
| `frontend/app/sea-route/page.tsx` | Main planner page — 3-tab mode selector, MapLibre map, results panel |
| `frontend/app/lib/seaRoute.ts` | API client functions for the 4 sea-route endpoints |

### Tests (`backend/tests/test_sea_route.py`)
7 unit tests matching acceptance criteria.

### Documentation
| File | Purpose |
|------|---------|
| `docs/sea_route/README.md` | How to add ports, zones, restricted areas; how to swap official IMBL data |

---

## Files MODIFIED (minimal touch)

| File | Change |
|------|--------|
| `backend/orca/api/main.py` | +1 import, +1 `app.include_router()` |
| `backend/requirements.txt` | +`heapq` (stdlib), +`numpy>=1.26` (if not already transitive), no new heavy deps |
| `frontend/app/nav.tsx` | Add `/sea-route` nav entry with `Ship` icon |

---

## Data flow
```
Raw files (data/raw/)
    └─ prep_all.py
           ├─ data/sea_route/land_india.geojson
           ├─ data/sea_route/ports.geojson
           ├─ data/sea_route/india_eez.geojson
           ├─ data/sea_route/restricted_areas.geojson
           ├─ data/sea_route/protected_areas.geojson
           └─ data/sea_route/fishing_zones.geojson

POST /api/sea-route
    └─ sea_route_routes.py
           └─ sea_route/router.py
                  ├─ datasets.py (lru_cache)
                  ├─ grid.py     (lru_cache)
                  ├─ astar.py
                  └─ smoother.py
```
