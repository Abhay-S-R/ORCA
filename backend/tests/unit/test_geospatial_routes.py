"""HTTP surface for Agent 6's D3 additions: /current-vectors and the §4.7
layer-metrics instrumentation sink. TestClient over the real app, same
pattern as test_analytics_routes.py."""
from __future__ import annotations

from fastapi.testclient import TestClient

from orca.api.main import app

client = TestClient(app)


def test_current_vectors_route_returns_points_and_bounds():
    r = client.get("/api/current-vectors")
    assert r.status_code == 200
    body = r.json()
    assert body["points"]
    assert len(body["bounds"]) == 4


def test_layer_metrics_route_accepts_a_valid_payload():
    r = client.post(
        "/api/layer-metrics",
        json={
            "layer_id": "bathymetry",
            "layer_load_ms": 120.5,
            "render_ms": 45.0,
            "payload_bytes": 204800,
            "dropped_frames": 0,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_layer_metrics_route_rejects_a_malformed_payload():
    r = client.post("/api/layer-metrics", json={"layer_id": "bathymetry"})
    assert r.status_code == 422


# --- boundary provenance is reachable, not just timestamped --------------

def test_boundary_provenance_endpoint_surfaces_the_citation_evidence():
    from orca.api.geospatial_routes import boundary_provenance

    prov = boundary_provenance()
    assert prov["marine_protected_areas"], "audited WDPA records must be reachable"
    assert prov["eez_gazetteer"], "VLIZ EEZ gazetteer records must be reachable"
    assert prov["boundary_data_vintage"]
    assert prov["boundary_line_vintage"] == "2026-09-16T19:19:33.460Z"
    assert all(e["mrgid"] for e in prov["eez_gazetteer"])
