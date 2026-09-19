"""P5.30 — live cyclone track and cone from GDACS. Shapes below are trimmed
from a real GDACS response (event DUJUAN-26, 2026-09-19), moved into the Bay
of Bengal so the North Indian Ocean filter keeps it."""
import httpx
import pytest

from orca.agents import weather_intelligence as wi

_EVENT_NIO = {
    "geometry": {"type": "Point", "coordinates": [88.0, 15.0]},
    "properties": {"eventid": 1, "episodeid": 3, "eventname": "TEST-26", "alertlevel": "Orange",
                   "iscurrent": "true", "fromdate": "2026-09-17T00:00:00", "todate": "2026-09-19T00:00:00",
                   "source": "JTWC", "severitydata": {"severitytext": "Tropical Storm (90 km/h)"},
                   "url": {"report": "https://www.gdacs.org/report.aspx?eventid=1"}},
}
_EVENT_PACIFIC = {"geometry": {"type": "Point", "coordinates": [138.2, 27.8]},
                  "properties": {**_EVENT_NIO["properties"], "eventid": 2}}
_EVENT_OLD = {"geometry": {"type": "Point", "coordinates": [85.0, 12.0]},
              "properties": {**_EVENT_NIO["properties"], "eventid": 3, "iscurrent": "false"}}


def _circle(lon, lat, d=0.1):
    return {"type": "Polygon", "coordinates": [[[lon - d, lat], [lon, lat + d], [lon + d, lat], [lon, lat - d], [lon - d, lat]]]}


_GEOMETRY = {"features": [
    {"geometry": {"type": "LineString", "coordinates": [[87, 13], [88, 15]]}, "properties": {"Class": "Line_Line_0", "polygonlabel": "TS"}},
    {"geometry": _circle(87, 13), "properties": {"Class": "Point_Polygon_Point_0", "polygonlabel": "18/09 12:00 UTC"}},
    {"geometry": _circle(89, 17), "properties": {"Class": "Point_Polygon_Point_1", "polygonlabel": "20/09 00:00 UTC"}},
    {"geometry": _circle(88, 15, 2), "properties": {"Class": "Poly_Cones", "polygonlabel": "Uncertainty Cones"}},
    {"geometry": _circle(88, 15, 1), "properties": {"Class": "Poly_Red", "polygonlabel": "120 km/h"}},
]}


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "gdacs_tc_tracks.json"
    monkeypatch.setattr(wi, "cached_gdacs_tc_path", lambda: path)
    return path


def test_keeps_only_current_nio_systems_and_the_right_features(monkeypatch, cache):
    def fake_get(url, **kw):
        if url == wi.GDACS_EVENTS_URL:
            return _Resp({"features": [_EVENT_NIO, _EVENT_PACIFIC, _EVENT_OLD]})
        assert kw["params"]["eventid"] == 1  # only the NIO system's geometry is fetched
        return _Resp(_GEOMETRY)

    monkeypatch.setattr(wi.httpx, "get", fake_get)
    r = wi.get_cyclone_tracks()

    assert r["available"] and not r["cached"]
    assert [s["name"] for s in r["systems"]] == ["TEST-26"]
    kinds = [f["properties"]["kind"] for f in r["geojson"]["features"]]
    assert kinds == ["track", "position", "position", "cone"]  # wind buffer dropped
    positions = [f for f in r["geojson"]["features"] if f["properties"]["kind"] == "position"]
    assert positions[0]["geometry"]["coordinates"] == [87.0, 13.0]
    assert [p["properties"]["time"] for p in positions] == ["2026-09-18T12:00:00Z", "2026-09-20T00:00:00Z"]
    assert [p["properties"]["forecast"] for p in positions] == [False, True]
    assert "1 active system" in r["note"] and "GDACS" in r["note"]
    assert cache.exists()  # a successful fetch becomes the fallback


def test_no_active_system_says_so(monkeypatch, cache):
    monkeypatch.setattr(wi.httpx, "get", lambda url, **kw: _Resp({"features": [_EVENT_PACIFIC]}))
    r = wi.get_cyclone_tracks()
    assert r["available"] and r["systems"] == [] and r["geojson"]["features"] == []
    assert r["note"].startswith("No active cyclone in the North Indian Ocean")


def test_failure_serves_the_last_fetch_marked_cached_then_unavailable(monkeypatch, cache):
    def boom(url, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(wi.httpx, "get", boom)
    r = wi.get_cyclone_tracks()
    assert r["available"] is False and r["geojson"]["features"] == []  # nothing invented

    monkeypatch.setattr(wi.httpx, "get", lambda url, **kw: _Resp(
        {"features": [_EVENT_NIO]} if url == wi.GDACS_EVENTS_URL else _GEOMETRY))
    fresh = wi.get_cyclone_tracks()
    monkeypatch.setattr(wi.httpx, "get", boom)
    stale = wi.get_cyclone_tracks()
    assert stale["cached"] is True and stale["fetched_at"] == fresh["fetched_at"]
    assert "cached" in stale["note"]
