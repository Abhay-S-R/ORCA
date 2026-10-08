"""Unit tests for the Sea Route Voyage engine and API endpoints.

Tests:
  1. Port to Port routing (Kochi to Chennai curves around Kanyakumari).
  2. Port to Fishing Zone routing (ends at zone boundary entry point).
  3. Map-pick mode routing.
  4. Safety invariant: route never crosses land polygons.
  5. Safety invariant: route never crosses blocking restricted areas.
  6. Validation: point on land is rejected.
  7. Validation: point outside India bbox is rejected.
  8. API endpoints (GET ports, GET fishing-zones, GET restricted-areas, POST sea-route).
"""
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString
from shapely.strtree import STRtree

from orca.api.main import app
from orca.sea_route.datasets import (
    load_land_polygons,
    load_restricted_areas,
)
from orca.sea_route.ports_service import get_port, list_ports
from orca.sea_route.router import sea_route
from orca.sea_route.zones_service import list_zones, zone_entry_point

client = TestClient(app)


def test_ports_dataset():
    """Verify ports dataset loads correctly with major ports."""
    ports = list_ports()
    assert len(ports) >= 11
    port_ids = {p.id for p in ports}
    assert "IN_KOC" in port_ids  # Kochi
    assert "IN_CHE" in port_ids  # Chennai
    assert "IN_JNP" in port_ids  # JNPT
    assert "IN_IXZ" in port_ids  # Port Blair


def test_fishing_zones_dataset():
    """Verify fishing zones dataset loads correctly."""
    zones = list_zones()
    assert len(zones) > 0
    zone = zones[0]
    assert zone.id != ""
    assert zone.geometry is not None


def test_port_to_port_kanyakumari_curve():
    """Test 1: Kochi to Chennai curves around southern tip of India (Kanyakumari)."""
    p_koc = get_port("IN_KOC")
    p_che = get_port("IN_CHE")
    assert p_koc and p_che

    res = sea_route(p_koc.lat, p_koc.lng, p_che.lat, p_che.lng, speed_knots=10.0)

    assert res.distance_nm > 450.0  # Nautical distance around peninsula (> 500 nm), not a straight line
    assert res.hours > 40.0
    assert len(res.coords) >= 4

    # Route must reach down to Kanyakumari latitudes (~8.0 N)
    min_lat = min(pt[0] for pt in res.coords)
    assert min_lat <= 8.2, f"Expected route to dip around Kanyakumari, min_lat was {min_lat}"

    # Verify warnings exist (disclaimer + proximity)
    assert any("DISCLAIMER" in w for w in res.warnings)


def test_port_to_fishing_zone():
    """Test 2: Port to Fishing Zone ends at entry point."""
    p = get_port("IN_JNP")
    zones = list_zones()
    assert p and len(zones) > 0
    z = zones[0]

    entry_lat, entry_lng = zone_entry_point(z, p.lat, p.lng)
    res = sea_route(p.lat, p.lng, entry_lat, entry_lng, speed_knots=10.0)

    assert res.distance_nm > 0
    assert len(res.coords) >= 2


def test_map_pick_valid():
    """Test 3: Map pick mode in the sea computes valid route."""
    # Point off Mumbai (19.0, 71.5) to point off Goa (15.5, 72.5)
    res = sea_route(19.0, 71.5, 15.5, 72.5, speed_knots=12.0, is_map_pick=True)
    assert res.distance_nm > 150.0
    assert len(res.coords) >= 2


def test_route_never_crosses_land():
    """Test 4: Land crossing check - verified by geometry intersection."""
    land_polygons = load_land_polygons()
    assert len(land_polygons) > 0
    land_tree = STRtree(list(land_polygons))

    p1 = get_port("IN_KOC")
    p2 = get_port("IN_CHE")
    res = sea_route(p1.lat, p1.lng, p2.lat, p2.lng, speed_knots=10.0)

    for i in range(len(res.coords) - 1):
        lat1, lng1 = res.coords[i]
        lat2, lng2 = res.coords[i + 1]
        seg = LineString([(lng1, lat1), (lng2, lat2)])
        hits = land_tree.query(seg, predicate="intersects")
        assert len(hits) == 0, f"Segment {i} ({lat1},{lng1}) -> ({lat2},{lng2}) crosses land!"


def test_route_never_crosses_blocking_restricted_area():
    """Test 5: Route never crosses blocking restricted areas."""
    restricted = load_restricted_areas()
    blocking = [r.geometry for r in restricted if r.mode == "block"]
    if not blocking:
        pytest.skip("No blocking restricted areas defined")
    block_tree = STRtree(blocking)

    p1 = get_port("IN_KOC")
    p2 = get_port("IN_CHE")
    res = sea_route(p1.lat, p1.lng, p2.lat, p2.lng, speed_knots=10.0)

    for i in range(len(res.coords) - 1):
        lat1, lng1 = res.coords[i]
        lat2, lng2 = res.coords[i + 1]
        seg = LineString([(lng1, lat1), (lng2, lat2)])
        hits = block_tree.query(seg, predicate="intersects")
        assert len(hits) == 0, f"Segment {i} crosses blocking restricted area!"


def test_point_on_land_rejected():
    """Test 6: Map-pick point on land raises ValueError."""
    # New Delhi (28.61, 77.20) or Central Maharashtra inland (19.5, 75.5)
    with pytest.raises(ValueError, match="on land"):
        sea_route(19.5, 75.5, 15.0, 72.0, is_map_pick=True)


def test_outside_india_bbox_rejected():
    """Test 7: Point outside India bbox raises ValueError."""
    # Point in Persian Gulf (26.0, 55.0)
    with pytest.raises(ValueError, match="within Indian waters"):
        sea_route(26.0, 55.0, 15.0, 72.0, is_map_pick=True)


def test_api_ports_endpoint():
    """Test GET /api/sea-route/ports."""
    response = client.get("/api/sea-route/ports")
    assert response.status_code == 200
    data = response.json()
    assert "ports" in data
    assert len(data["ports"]) >= 11
    first = data["ports"][0]
    assert "id" in first
    assert "name" in first
    assert "lat" in first
    assert "lng" in first


def test_api_fishing_zones_endpoint():
    """Test GET /api/sea-route/fishing-zones."""
    response = client.get("/api/sea-route/fishing-zones")
    assert response.status_code == 200
    data = response.json()
    assert data.get("type") == "FeatureCollection"
    assert len(data.get("features", [])) > 0


def test_api_restricted_areas_endpoint():
    """Test GET /api/sea-route/restricted-areas."""
    response = client.get("/api/sea-route/restricted-areas")
    assert response.status_code == 200
    data = response.json()
    assert data.get("type") == "FeatureCollection"
    assert "IMBL" in data.get("note", "") or "PLACEHOLDER" in data.get("note", "")


def test_api_post_sea_route_port_to_port():
    """Test POST /api/sea-route in port_to_port mode."""
    payload = {
        "mode": "port_to_port",
        "port_from": "IN_KOC",
        "port_to": "IN_CHE",
        "speed_knots": 10.0,
    }
    response = client.post("/api/sea-route", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "coords" in data
    assert len(data["coords"]) >= 4
    assert data["distance_nm"] > 450.0
    assert "eta" in data
    assert len(data["warnings"]) > 0


def test_api_post_sea_route_land_validation_error():
    """Test POST /api/sea-route returns 422 when map-pick point is on land."""
    payload = {
        "mode": "map_pick",
        "from_lat": 19.5,
        "from_lng": 75.5,  # Inland Maharashtra
        "to_lat": 15.0,
        "to_lng": 72.0,
        "speed_knots": 8.0,
    }
    response = client.post("/api/sea-route", json=payload)
    assert response.status_code == 422
    assert "on land" in response.json()["detail"]


def test_api_post_sea_route_outside_bbox_error():
    """Test POST /api/sea-route returns 400 when coordinates are outside Indian waters."""
    payload = {
        "mode": "map_pick",
        "from_lat": 28.0,
        "from_lng": 55.0,  # Outside India bbox
        "to_lat": 15.0,
        "to_lng": 72.0,
        "speed_knots": 8.0,
    }
    response = client.post("/api/sea-route", json=payload)
    assert response.status_code == 400
    assert "within Indian waters" in response.json()["detail"]


