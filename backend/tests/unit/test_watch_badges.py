"""Map watch-badge handoff contract (plan §14). The payload D2 hands D3 must
be stable and match the frozen MapLayer shape (layer_type "SentinelWatch").
Pure — the DB-backed builder is exercised in test_notifications.py."""
from orca.contracts import MapLayer, StyleHints
from orca.notifications.watch_badges import badges_as_map_layer

_BADGES = [
    {
        "watch_id": "w-1", "lat": 8.8, "lon": 78.14, "watch_type": "wave_height",
        "status": "active", "severity": "warning", "enabled": True, "unread_count": 1,
        "last_fired_at": "2026-09-03T10:00:00Z", "updated_at": "2026-09-03T10:00:00Z",
        "label": "Wave Height watch",
    },
    {
        "watch_id": "w-2", "lat": 9.1, "lon": 79.0, "watch_type": "weather",
        "status": "clear", "severity": "info", "enabled": True, "unread_count": 0,
        "last_fired_at": None, "updated_at": "2026-09-03T09:00:00Z", "label": "Weather watch",
    },
]


def test_badge_layer_matches_the_frozen_maplayer_shape():
    layer = badges_as_map_layer(_BADGES)
    # constructs cleanly into the frozen contract — no missing/extra fields
    ml = MapLayer(**{**layer, "style_hints": StyleHints(**layer["style_hints"])})
    assert ml.layer_type == "SentinelWatch"
    assert ml.layer_id == "sentinel_watch_badges"
    assert ml.weight == "light"


def test_badge_features_carry_status_and_severity_but_no_bare_latlon_in_properties():
    layer = badges_as_map_layer(_BADGES)
    feats = layer["geojson"]["features"]
    assert len(feats) == 2
    props = feats[0]["properties"]
    assert props["status"] == "active"
    assert props["severity"] == "warning"
    assert props["watch_id"] == "w-1"
    # coordinates live in geometry, not duplicated into properties
    assert "lat" not in props and "lon" not in props
    assert feats[0]["geometry"]["coordinates"] == [78.14, 8.8]


def test_empty_badge_list_still_produces_a_valid_layer_with_india_bounds():
    layer = badges_as_map_layer([])
    assert layer["geojson"]["features"] == []
    assert layer["bounds"] == (68.0, 6.0, 98.0, 24.0)
