"""A "which did you mean?" chip re-asks the original question at the chosen
place (found 2026-09-27: clicking Mangrol under "fishing zones near Gujarat"
sent "Conditions at mangrol" and lost the question). Over the real `/query`
route, with the chip's coordinates as the explicit position.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from orca.api.main import app

client = TestClient(app)


def test_a_picked_place_chip_answers_the_original_question_at_that_place():
    response = client.get("/query", params={
        "q": "what are the nearest fishing zones near gujarat (at mangrol)",
        "lat": 21.08, "lon": 70.10, "llm": "off",
    })
    frame = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")][-1]
    assert frame["outcome"] != "NEEDS_PLACE"
    assert frame["user_location"]["place_name"] == "mangrol"


def test_a_cloud_covered_sector_with_nothing_in_reach_still_answers_honestly(monkeypatch):
    # The same Mangrol answer then said "no designated fishing zone within
    # 150 km … outside any regulated zone": Gujarat had no advisory of its own,
    # the nearest was 268 km off, and the reach cap dropped it. Both surfaces
    # (/query's answer and /zones) must give the gap's reason and the nearest held zone.
    from orca.agents import ocean_analytics as oa
    far = {"sector_id": "SEC002", "latitude_dd": "19.0", "longitude_dd": "72.0",
           "valid_for": "2026-09-23", "age_days": 4, "band": "hint", "expired": True}
    monkeypatch.setattr(oa.al, "load_pfz_latest", lambda *_: [far])
    monkeypatch.setattr(oa.al, "load_pfz_sector_status", lambda: {"sectors": [
        {"sector_id": "SEC001", "status": "NO_DATA_CLOUD_COVER",
         "message": "No data available for this sector due to excessive cloud cover"}]})

    zones = client.get("/api/zones", params={"lat": 21.08, "lon": 70.10}).json()
    assert zones["nearest_pfz"]["found"] and zones["nearest_pfz"]["beyond_reach"]
    assert zones["sector_status"]["nearest_advisory_out_of_sector"] is True

    response = client.get("/query", params={
        "q": "what are the nearest fishing zones near mangrol", "llm": "off", "fresh": 1,
    })
    frame = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")][-1]
    answer = frame["final_english_response"]
    assert "cloud cover" in answer and "beyond a day trip" in answer
