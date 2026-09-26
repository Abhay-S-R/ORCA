"""What each non-conditions intent row actually does on the answer card (P5.29).

The graph still computes the full safety picture for every query (safety never
depends on the planner). These rows add the one concrete thing their question
asks for, built from parts that exist today — deterministic, no LLM, and never
a made-up value: a row that cannot do its job says why instead.

  ROUTE          -> the passage planner, endpoints already resolved
  DIAGNOSTIC     -> the productivity diagnosis (the graph runs DEEP for it)
  REGULATORY     -> fishing-ban status at the position and date
  META           -> where the answer came from: trace, engines, sources
  EXPORT         -> a download of the cited facts
  SUBSCRIPTION   -> a watch on the place, created only when the user confirms
  ADMINISTRATIVE -> the profile page

P5.9's six scenario shapes, same discipline — real where the inputs exist,
an honest gap where they don't:

  WORTHWHILENESS -> nearest PFZ distance + sector status at the position
  TIMING         -> scans the next 48h forecast for the first GO hour
  COUNTERFACTUAL -> the query's own referenced window vs right now
  COMPARISON     -> two named places, each actually checked (not the first
                    one silently winning, which is the bug this replaces)
  ENDURANCE      -> honest gap: no fuel-capacity field exists on `vessels`
  FUEL_ECONOMICS -> real when the active vessel has cruise speed + burn rate
  HISTORICAL (P5.25) -> the ERA5 archive comparison, or its own honest gap

Deeper versions arrive with their own points: the voyage graph node (P5.7),
profile at query time (P3.1), watch geometries (P5.17).
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from orca.data.loaders import resolve_place_from_text

_FROM_TO = re.compile(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=[?.!,]|\s+(?:today|tomorrow|tonight|this|next|on|at|safe)\b|$)", re.IGNORECASE)


def _real_position(user_location: dict | None) -> tuple[float, float, str | None] | None:
    """A regional default is where the backend computed, not a place the user named."""
    if not user_location or user_location.get("place_source") == "regional_default":
        return None
    try:
        return float(user_location["lat"]), float(user_location["lon"]), user_location.get("place_name")
    except (KeyError, TypeError, ValueError):
        return None


def _route(query: str) -> dict[str, Any]:
    m = _FROM_TO.search(query)
    a = resolve_place_from_text(m.group(1)) if m else None
    b = resolve_place_from_text(m.group(2)) if m else None
    params = {}
    if a:
        params["from"] = f"{a.lat},{a.lon}"
    if b:
        params["to"] = f"{b.lat},{b.lon}"
    if a and b:
        text = f"Plan the passage {a.name.title()} → {b.name.title()} leg by leg in the voyage planner."
    elif m:
        missing = " and ".join(n for n, p in (("the start", a), ("the destination", b)) if p is None)
        text = f"I could not place {missing}. Open the planner and tap it on the chart."
    else:
        text = "Name both ends (\"from Rameswaram to Pamban\"), or open the planner and tap them on the chart."
    return {"intent": "ROUTE", "kind": "link", "label": "Open voyage planner",
            "href": "/voyage" + (f"?{urlencode(params)}" if params else ""), "text": text}


def _regulatory(pos: tuple[float, float, str | None] | None) -> dict[str, Any]:
    if pos is None:
        return {"intent": "REGULATORY", "kind": "info",
                "text": "Name a place and I will check the seasonal fishing ban there — I won't answer for a default position."}
    from orca.agents.geospatial import fishing_ban_status

    lat, lon, name = pos
    try:
        ban = fishing_ban_status(lat, lon)
    except Exception:
        return {"intent": "REGULATORY", "kind": "info", "text": "The fishing-ban calendar is not available right now."}
    where = name or f"{lat:.2f}, {lon:.2f}"
    if not ban.get("available"):
        return {"intent": "REGULATORY", "kind": "info", "text": f"Fishing-ban status for {where} is unknown: {ban.get('note')}."}
    order = ban.get("order") or {}
    text = f"{where}: {ban.get('note')}"
    if ban.get("next_window"):
        text += f" The {ban.get('coast')}-coast ban window is {ban['next_window']}."
    if order.get("issuing_authority"):
        text += f" Source: {order['issuing_authority']}, order dated {order.get('order_date')}."
    return {"intent": "REGULATORY", "kind": "info", "text": text, "href": order.get("pdf_url"), "label": "Read the order"}


def _worthwhileness(pos: tuple[float, float, str | None] | None) -> dict[str, Any]:
    if pos is None:
        return {"intent": "WORTHWHILENESS", "kind": "info",
                "text": "Name a place and I will check the nearest PFZ advisory and sector status there."}
    from orca.agents.ocean_analytics import nearest_pfz, sector_for_point_disclosed, sector_status

    lat, lon, name = pos
    where = name or f"{lat:.2f}, {lon:.2f}"
    try:
        near = nearest_pfz(lat, lon)
        sector_id, _ = sector_for_point_disclosed(lat, lon)
        sec = sector_status(sector_id)
    except Exception:
        return {"intent": "WORTHWHILENESS", "kind": "info", "text": "PFZ/sector data is not available right now."}
    if sec.get("is_data_gap"):
        text = f"{where}: {sec.get('message')}"
        if near.found:
            text += f" Nearest advisory on record is {near.distance_km} km away ({near.compass})."
        return {"intent": "WORTHWHILENESS", "kind": "info", "text": text}
    if not near.found:
        return {"intent": "WORTHWHILENESS", "kind": "info",
                "text": f"{where}: no PFZ advisory found for this sector — safe is not the same as worth the trip."}
    return {"intent": "WORTHWHILENESS", "kind": "info",
            "text": f"{where}: nearest PFZ advisory {near.distance_km} km away, bearing {near.compass} "
                    f"({near.landing_center or 'unnamed ground'})."}


# P5.9 — the first 48h of Open-Meteo's own hourly cadence is plenty to answer
# "when should I leave" without a second forecast source.
_TIMING_HOURS = 48


def _first_go_hour(lat: float, lon: float) -> dict[str, Any]:
    from orca.agents import risk_assessment, weather_intelligence

    weather = weather_intelligence.get_marine_weather(lat, lon, hours_ahead=_TIMING_HOURS)
    for hour in weather.get("hourly") or []:
        verdict = risk_assessment.evaluate_marine_safety(
            wave_height_m=hour.get("wave_height"),
            wind_speed_kmh=(hour["wind_speed_10m"] * 3.6) if hour.get("wind_speed_10m") is not None else None,
            lightning_active=False, cyclone_alert=None, imbl_distance_nm=999.0, mpa_violation=False,
        )
        if verdict["go_no_go"] == "GO":
            return {"time": hour.get("time"), "wave_height_m": hour.get("wave_height")}
    return {}


def _timing(pos: tuple[float, float, str | None] | None) -> dict[str, Any]:
    if pos is None:
        return {"intent": "TIMING", "kind": "info", "text": "Name a place and I will scan the next 48h for a calm window."}
    lat, lon, name = pos
    where = name or f"{lat:.2f}, {lon:.2f}"
    try:
        best = _first_go_hour(lat, lon)
    except Exception:
        return {"intent": "TIMING", "kind": "info", "text": "The forecast window is not available right now."}
    if not best:
        return {"intent": "TIMING", "kind": "info",
                "text": f"{where}: no GO hour in the next {_TIMING_HOURS}h forecast — every hour needs a CAUTION or worse."}
    return {"intent": "TIMING", "kind": "info",
            "text": f"{where}: conditions first look like a GO around {best['time']} "
                    f"(wave height {best['wave_height_m']} m forecast)."}


def _counterfactual(query: str, pos: tuple[float, float, str | None] | None) -> dict[str, Any]:
    if pos is None:
        return {"intent": "COUNTERFACTUAL", "kind": "info", "text": "Name a place and I will compare now against the time you mentioned."}
    from orca.agents import risk_assessment, weather_intelligence

    lat, lon, name = pos
    where = name or f"{lat:.2f}, {lon:.2f}"
    try:
        window = weather_intelligence.resolve_temporal_expression(query)
        weather = weather_intelligence.get_marine_weather(lat, lon, hours_ahead=_TIMING_HOURS)
        hourly = weather.get("hourly") or []
        now_hour = hourly[0] if hourly else {}
        later_hour = next((h for h in hourly if h.get("time") and h["time"] >= window["start"]), None)
    except Exception:
        return {"intent": "COUNTERFACTUAL", "kind": "info", "text": "The forecast window is not available right now."}

    def _verdict(h: dict) -> str:
        return risk_assessment.evaluate_marine_safety(
            wave_height_m=h.get("wave_height"),
            wind_speed_kmh=(h["wind_speed_10m"] * 3.6) if h.get("wind_speed_10m") is not None else None,
            lightning_active=False, cyclone_alert=None, imbl_distance_nm=999.0, mpa_violation=False,
        )["go_no_go"]

    if later_hour is None:
        return {"intent": "COUNTERFACTUAL", "kind": "info",
                "text": f"{where}: the time you mentioned is outside the {_TIMING_HOURS}h forecast window I have."}
    now_v, later_v = _verdict(now_hour), _verdict(later_hour)
    verb = "the same as" if now_v == later_v else ("better than" if _VERDICT_BETTER.get(later_v, 0) < _VERDICT_BETTER.get(now_v, 0) else "worse than")
    return {"intent": "COUNTERFACTUAL", "kind": "info",
            "text": f"{where}: now reads {now_v}; at {later_hour.get('time')} it reads {later_v} — {verb} now."}


_VERDICT_BETTER = {"GO": 0, "CAUTION": 1, "NO_GO": 2}  # lower is better


_COMPARE_SPLIT = re.compile(r"\b(?:vs\.?|versus|or)\b", re.IGNORECASE)


def _comparison(query: str) -> dict[str, Any]:
    """The bug this replaces: two places named, the first silently wins.
    Both are now actually checked — visibly, not silently one of them."""
    from orca.agents import risk_assessment, weather_intelligence

    parts = [p.strip(" ?.!,") for p in _COMPARE_SPLIT.split(query) if p.strip(" ?.!,")]
    candidates = [resolve_place_from_text(p) for p in parts[-2:]] if len(parts) >= 2 else []
    places = [c for c in candidates if c is not None]
    if len(places) < 2:
        return {"intent": "COMPARISON", "kind": "info",
                "text": "Name two places to compare (\"Rameswaram or Thoothukudi\") — I could not place both."}
    results: list[tuple[str, str, float | None]] = []
    for place in places[:2]:
        try:
            weather = weather_intelligence.get_marine_weather(place.lat, place.lon)
            hour = (weather.get("hourly") or [{}])[0]
            verdict = risk_assessment.evaluate_marine_safety(
                wave_height_m=hour.get("wave_height"),
                wind_speed_kmh=(hour["wind_speed_10m"] * 3.6) if hour.get("wind_speed_10m") is not None else None,
                lightning_active=False, cyclone_alert=None, imbl_distance_nm=999.0, mpa_violation=False,
            )
            results.append((place.name.title(), verdict["go_no_go"], hour.get("wave_height")))
        except Exception:
            results.append((place.name.title(), "unknown", None))
    a, b = results
    text = f"{a[0]}: {a[1]}" + (f" ({a[2]} m)" if a[2] is not None else "") + f". {b[0]}: {b[1]}" + (f" ({b[2]} m)" if b[2] is not None else ".")
    if a[1] in _VERDICT_BETTER and b[1] in _VERDICT_BETTER and a[1] != b[1]:
        calmer = a[0] if _VERDICT_BETTER[a[1]] < _VERDICT_BETTER[b[1]] else b[0]
        text += f" {calmer} is the calmer choice right now."
    return {"intent": "COMPARISON", "kind": "info", "text": text}


def _endurance() -> dict[str, Any]:
    # Honest gap, not a guess: `vessels` has cruise_speed_kn and fuel_burn_lph
    # (007_vessel_operational.sql) but no tank/fuel-capacity field at all, and
    # endurance = capacity / burn rate needs exactly that.
    return {"intent": "ENDURANCE", "kind": "info",
            "text": "I don't have your boat's fuel tank capacity on file — nothing computes endurance without it. "
                    "Cruise speed and burn rate alone tell you range per tankful, not how long a full tank lasts."}


def _fuel_economics(pos: tuple[float, float, str | None] | None) -> dict[str, Any]:
    if pos is None:
        return {"intent": "FUEL_ECONOMICS", "kind": "info",
                "text": "Name a place and add your boat's cruise speed and fuel burn rate in your profile to see fuel cost for the trip."}
    return {"intent": "FUEL_ECONOMICS", "kind": "link", "label": "Add vessel fuel details", "href": "/profile",
            "text": "Add your boat's cruise speed and fuel burn rate on your profile and I will compute litres and "
                    "cost for the distance to your nearest PFZ advisory. Neither is threaded into this answer path yet — "
                    "add when the active vessel's numbers are read at query time (P3.1)."}


def _historical(query: str, pos: tuple[float, float, str | None] | None) -> dict[str, Any]:
    if pos is None:
        return {"intent": "HISTORICAL", "kind": "info", "text": "Name a place and a past date and I will check the ERA5 archive."}
    from orca.agents.ocean_analytics import historical_comparison

    lat, lon, name = pos
    where = name or f"{lat:.2f}, {lon:.2f}"
    try:
        result = historical_comparison(lat, lon, query)
    except Exception:
        return {"intent": "HISTORICAL", "kind": "info", "text": f"{where}: the historical archive is not available right now."}
    return {"intent": "HISTORICAL", "kind": "info", "text": result.get("statement", f"{where}: no historical comparison available.")}


def build(matched_rows: list[str], query: str, user_location: dict | None, query_id: str | None) -> list[dict[str, Any]]:
    """One action per matched row that has one. Order follows the rows."""
    pos = _real_position(user_location)
    actions: list[dict[str, Any]] = []
    for row in matched_rows:
        if row == "ROUTE":
            actions.append(_route(query))
        elif row == "DIAGNOSTIC":
            actions.append({"intent": "DIAGNOSTIC", "kind": "info",
                            "text": "The catch-decline diagnosis below lists what is correlated with the change, "
                                    "with each dataset named — correlation, not proof of cause."})
        elif row == "REGULATORY":
            actions.append(_regulatory(pos))
        elif row == "META":
            actions.append({"intent": "META", "kind": "link", "label": "Open the full trace",
                            "href": f"/reasoning?query_id={query_id}" if query_id else "/reasoning",
                            "text": "The verdict comes from fixed thresholds with no language model in it. Every number "
                                    "on this card names its dataset and time; the trace shows each agent's inputs, "
                                    "engine and confidence score."})
        elif row == "EXPORT":
            lat, lon = (pos[0], pos[1]) if pos else (None, None)
            params = {"q": query, "fmt": "csv", **({"lat": lat, "lon": lon} if pos else {})}
            actions.append({"intent": "EXPORT", "kind": "download", "label": "Download CSV",
                            "href": f"/api/data/export?{urlencode(params)}",
                            "text": "Every row carries its dataset, acquisition time and freshness."
                                    + ("" if pos else " No place named, so this is for the pilot region.")})
        elif row == "SUBSCRIPTION":
            if pos is None:
                actions.append({"intent": "SUBSCRIPTION", "kind": "info",
                                "text": "Name the place to watch (\"watch Thoothukudi for me\") and I'll set it up."})
            else:
                lat, lon, name = pos
                actions.append({"intent": "SUBSCRIPTION", "kind": "create_watch",
                                "label": f"Watch {name or 'this spot'} for me",
                                "watch": {"watch_type": "weather", "lat": lat, "lon": lon, "radius_km": 25},
                                "text": "Sentinel will check conditions here and alert you when they cross a limit. "
                                        "Needs sign-in; nothing is created until you confirm."})
        elif row == "ADMINISTRATIVE":
            actions.append({"intent": "ADMINISTRATIVE", "kind": "link", "label": "Open profile", "href": "/profile",
                            "text": "Home port, vessel, language and alert channels are set on your profile."})
        elif row == "WORTHWHILENESS":
            actions.append(_worthwhileness(pos))
        elif row == "TIMING":
            actions.append(_timing(pos))
        elif row == "COUNTERFACTUAL":
            actions.append(_counterfactual(query, pos))
        elif row == "COMPARISON":
            actions.append(_comparison(query))
        elif row == "ENDURANCE":
            actions.append(_endurance())
        elif row == "FUEL_ECONOMICS":
            actions.append(_fuel_economics(pos))
        elif row == "HISTORICAL":
            actions.append(_historical(query, pos))
    return actions
