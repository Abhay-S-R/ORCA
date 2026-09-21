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
    return actions
