from fastapi.testclient import TestClient

from orca.api.main import app

client = TestClient(app)


def test_list_species_default():
    response = client.get("/api/species?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert data["total"] == 3602
    assert len(data["species"]) == 5
    assert "report_summary" in data
    assert data["report_summary"]["sources"]["total_harmonized_species"] == 3602
    assert len(data["spot_checks"]) == 5


def test_search_species_by_common_and_scientific_name():
    # Search for pomfret
    response = client.get("/api/species?q=pomfret")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    names = [s["scientific_name"] for s in data["species"]]
    assert "Pampus argenteus" in names

    # Search for scientific name Rastrelliger
    r_rast = client.get("/api/species?q=Rastrelliger")
    assert r_rast.status_code == 200
    d_rast = r_rast.json()
    assert any("kanagurta" in s["scientific_name"] for s in d_rast["species"])


def test_filter_by_confidence():
    response = client.get("/api/species?confidence=High")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert all(s["confidence"] == "High" for s in data["species"])


def test_get_single_species_detail():
    # Pampus argenteus AphiaID 127075
    response = client.get("/api/species/127075")
    assert response.status_code == 200
    data = response.json()
    assert data["species"]["scientific_name"] == "Pampus argenteus"
    assert data["species"]["common_name"] == "Silver pomfret"
    assert data["species"]["confidence"] == "High"
    assert data["fishbase_benchmark"] is not None
    assert data["fishbase_benchmark"]["depth_min_m"] == 5
    assert data["fishbase_benchmark"]["depth_max_m"] == 110


def test_get_single_species_not_found():
    response = client.get("/api/species/999999999")
    assert response.status_code == 404
