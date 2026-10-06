# Sea Route Voyage Planning Engine

Real-world coastal sea route calculation and voyage planning engine for Indian waters.

---

## 1. Overview & Geographic Scope

- **Region**: India only (`lat 5.0 to 24.0`, `lng 66.0 to 95.0`), explicitly encompassing:
  - Mainland Western Coast (Gujarat, Maharashtra, Goa, Karnataka, Kerala)
  - Mainland Eastern Coast (Tamil Nadu, Andhra Pradesh, Odisha, West Bengal)
  - Union Territories: **Lakshadweep** and **Andaman & Nicobar Islands**
- **Safety Guarantee**:
  - The calculated route follows the real coastline and **never crosses land**.
  - Routes **never cut through blocking restricted areas** (e.g., Pakistan IMBL, military firing zones).
  - Routes naturally curve around headlands, gulfs (Gulf of Kutch, Gulf of Khambhat, Gulf of Mannar), and the southern tip of India (**Kanyakumari**), exactly as a vessel would navigate.
  - Straight-line routing between nautical waypoints across landmass is strictly disallowed.

---

## 2. Three Voyage Modes

1. **Port -> Fishing Zone (`port_to_zone`)**:
   - User selects a departure port and an active fishing zone (INCOIS PFZ advisory or offshore bank).
   - Route computes from the port's sea fairway to the zone's entry point (nearest boundary point or advisory centroid).
2. **Port -> Port (`port_to_port`)**:
   - User selects a departure port and destination port.
   - Calculates realistic inter-port transit (e.g., Kochi to Chennai curving around Kanyakumari; Mumbai to Kochi down the Konkan coast; Chennai to Port Blair across the Bay of Bengal; Kochi to Kavaratti across the Laccadive Sea).
3. **Map-pick -> Map-pick (`map_pick`)**:
   - User clicks anywhere in the sea to define arbitrary departure and arrival waypoints.
   - If a click lands on terra firma, the engine rejects it with:
     `"Selected point is on land, please choose a point in the sea"`.
   - If a click falls outside the regional bounding box, the engine rejects it with:
     `"Please select a point within Indian waters"`.

---

## 3. Architecture & Data Flow

```
Raw Geo Data (data/raw/ or data/tier1/)
   │
   ├── prep_land.py                ──> data/sea_route/land_india.geojson
   ├── prep_ports.py               ──> data/sea_route/ports.geojson
   ├── prep_maritime_boundaries.py ──> data/sea_route/restricted_areas.geojson
   ├── prep_eez.py                 ──> data/sea_route/india_eez.geojson
   ├── prep_protected.py           ──> data/sea_route/protected_areas.geojson
   └── prep_fishing_zones.py       ──> data/sea_route/fishing_zones.geojson
                                            │
                                            ▼
                           orca/sea_route/datasets.py (lru_cache)
                                            │
                                            ▼
                              orca/sea_route/grid.py
                          (2D NumPy boolean navigability grid)
                                            │
                                            ▼
                             orca/sea_route/astar.py
                           (8-neighbourhood A* search,
                          no diagonal corner-cutting)
                                            │
                                            ▼
                            orca/sea_route/smoother.py
                         (STRtree line-of-sight pruning)
                                            │
                                            ▼
                            orca/sea_route/router.py
                           (Distance, ETA, Warnings, Cache)
                                            │
                                            ▼
                         FastAPI: /api/sea-route (POST/GET)
                                            │
                                            ▼
                         Next.js MapLibre Interactive UI
```

---

## 4. API Endpoints

Mounted on `/api` alongside existing ORCA endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/api/sea-route` | `POST` | Primary route calculation endpoint. Accepts `mode`, coordinates/IDs, speed, departure time. |
| `/api/sea-route/ports` | `GET` | Returns list of available ports with coordinates and state. |
| `/api/sea-route/fishing-zones` | `GET` | Returns GeoJSON FeatureCollection of active fishing grounds. |
| `/api/sea-route/restricted-areas` | `GET` | Returns GeoJSON FeatureCollection of restricted and boundary polygons. |

---

## 5. Maintenance & Data Updates

### How to Add or Update Ports
1. Edit `scripts/prep_ports.py` to add entries to `SEED_MAJOR` or supply `data/raw/UpdatedPub150.csv` / `data/raw/fishing_harbours.csv`.
2. Run:
   ```bash
   python scripts/prep_ports.py
   ```
3. Restart or trigger reload of the backend service to clear in-memory caches.

### How to Add or Update Fishing Zones
1. Place updated fishing zones GeoJSON in `data/raw/fishing_zones.geojson`, or update INCOIS PFZ advisories in `data/incois_osf_pfz/pfz/all_india_pfz_advisories.geojson`.
2. Run:
   ```bash
   python scripts/prep_fishing_zones.py
   ```

### How to Swap Official IMBL / Boundary Data
1. Current boundary geometries are derived from Marine Regions VLIZ lines buffered by 2.0 nautical miles and marked with explicit `PLACEHOLDER` notices.
2. To replace with official Hydrographic Department / Indian Navy / MEA boundary coordinates:
   - Save the official boundary shapefile or GeoJSON to `data/raw/india_maritime_boundary_lines.geojson`.
   - Run:
     ```bash
     python scripts/prep_maritime_boundaries.py --input /path/to/official_imbl.geojson --buffer 2.0
     ```

### Master Rebuild & Validation
Run the master prep pipeline to refresh all 6 datasets:
```bash
python scripts/prep_all.py
```
Run data validation:
```bash
python scripts/validate_sea_route_data.py
```

---

## 6. Testing

Run the full suite of unit and integration tests:
```bash
pytest backend/tests/test_sea_route.py -v
```
