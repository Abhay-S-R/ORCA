"""One shared place-resolution guard (P1.2, `R-NEW-1`/`R-NEW-8`), used by
`/query` and `/api/voyage-plan`, plus the position/time guard clauses that
hang off it (P1.4, `R-EDGE-3`).

The rule this file exists to enforce: **never substitute a position the user
did not choose and cannot see.** Before it, a query naming no resolvable place
was answered at `loaders.DEFAULT_LAT/LON` with nothing on the card to say so,
and a query naming a whole state was answered at that state's centroid — in
Kerala's case, a point inland.

Four outcomes, and the caller must render all four differently:

* ``resolved``     — a real place, from the text, a bare coordinate pair, or an
  explicit fix the caller already had. Answer normally.
* ``ambiguous``    — the text names more than one place, or names a region
  rather than a position. Return candidates with coordinates and ask.
* ``unresolvable`` — the text names a place *and we cannot place it* ("near my
  village"). Say "I don't know where that is" and ask. Never a default.
* ``fallback``     — the text names no place at all. Answering somewhere is
  still better than refusing, but the disclosure goes on the card **before**
  the answer, never after it.

It is deliberately import-light: `orca.data.loaders` and the stdlib only, so
the route layer can call it before the graph starts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from orca.data.loaders import (
    DEFAULT_LAT,
    DEFAULT_LON,
    ResolvedPlace,
    inland_place_name,
    is_region_name,
    near_miss_place_names,
    places_within_region,
    resolve_all_places_from_text,
)

Status = Literal["resolved", "ambiguous", "unresolvable", "fallback"]


@dataclass(frozen=True)
class PlaceResolution:
    status: Status
    place: ResolvedPlace | None
    candidates: list[ResolvedPlace] = field(default_factory=list)
    disclosure: str | None = None

    @property
    def is_answerable(self) -> bool:
        """False only for ``unresolvable`` — the one status that must not be
        answered at a position at all."""
        return self.place is not None

    def as_dict(self) -> dict[str, Any]:
        """Wire form for the answer card. `candidates` carry coordinates
        because "did you mean Veraval or Porbandar?" is not a real choice
        without them."""
        return {
            "status": self.status,
            "place_name": self.place.name if self.place else None,
            "place_source": self.place.source if self.place else None,
            "lat": self.place.lat if self.place else None,
            "lon": self.place.lon if self.place else None,
            "candidates": [
                {"name": c.name, "lat": c.lat, "lon": c.lon} for c in self.candidates
            ],
            "disclosure": self.disclosure,
        }


# Phrases that name a location the speaker can see and we cannot. These are
# the "near my village" case from the Phase 1 exit gate: the query IS about a
# place, so falling back to the pilot default and answering confidently is the
# exact failure this phase is named after. Whole-word matched.
#
# ponytail: English only. A Tamil or Hindi "my village" reaches here before
# Agent 1's translation runs (the route layer resolves place before the graph
# starts), so it currently lands on `fallback`, which is disclosed but weaker
# than the refusal it deserves. Add per-language phrases when P3.7's native
# reviewers look at the distress lists — same reviewers, same standard.
_UNPLACEABLE_SELF_REFERENCE: tuple[str, ...] = (
    "my village", "our village", "my place", "my area", "our area", "my side",
    "my town", "my beach", "my landing", "my island", "my usual spot",
    "my spot", "my port", "my harbour", "my harbor", "my coast", "my waters",
    "home port", "where i am", "where i live", "where we fish", "round here",
    "over here", "here", "nearby",
)

# "8.7N 78.2E", "8.7 N, 78.2 E", "lat 8.7 lon 78.2", "8.7, 78.2" — the shapes a
# fisherman's plotter or a WhatsApp forward actually produces. Signed decimal
# degrees only; degrees-minutes-seconds is not parsed, and guessing at one
# would be exactly the fabricated-input failure this module exists to stop.
_COORD_PAIR = re.compile(
    r"(?:lat(?:itude)?\s*)?(-?\d{1,2}(?:\.\d+)?)\s*°?\s*([NnSs])?\s*[,;/ ]\s*"
    r"(?:lon(?:g(?:itude)?)?\s*)?(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([EeWw])?"
)

# India's maritime neighbourhood, as a box. A coordinate pair outside it is a
# real position we have no data for, not a place name — P1.4's "outside the
# data extent" guard. Matches the span every dataset under data/ covers
# (Arabian Sea through the Andaman Sea), not a guess at the EEZ.
DATA_EXTENT = (5.0, 25.0, 66.0, 96.0)  # (lat_min, lat_max, lon_min, lon_max)

# Every forecast product in the tree is a 7-day one (Open-Meteo, WW3). A
# question about day 9 has no answer here and must be told so rather than
# answered off the last frame we do have.
FORECAST_HORIZON_DAYS = 7


def parse_coordinates(text: str) -> ResolvedPlace | None:
    """A bare coordinate pair in free text, or None. Out-of-range values
    (|lat| > 90, |lon| > 180) are not coordinates and return None rather than
    being clamped into a position nobody named."""
    m = _COORD_PAIR.search(text)
    if m is None:
        return None
    lat, lat_hem, lon, lon_hem = float(m.group(1)), m.group(2), float(m.group(3)), m.group(4)
    if lat_hem and lat_hem.upper() == "S":
        lat = -abs(lat)
    if lon_hem and lon_hem.upper() == "W":
        lon = -abs(lon)
    if abs(lat) > 90 or abs(lon) > 180:
        return None
    # A bare "2, 3" in "boat 2, 3 men aboard" is not a position. Require either
    # an explicit hemisphere/label or a fractional part on both numbers — the
    # shape a real fix always has and a stray integer pair never does.
    if not (lat_hem or lon_hem or ("." in m.group(1) and "." in m.group(3))):
        return None
    return ResolvedPlace(f"{lat:.4f}, {lon:.4f}", lat, lon, "coordinates")


def names_unplaceable_location(text: str) -> bool:
    """True when the text points at a place it does not name well enough to
    resolve. The caller must ask, not guess."""
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(p)}\b", lowered) for p in _UNPLACEABLE_SELF_REFERENCE)


# "from X to Y", "between X and Y" — the shapes that name two places on
# purpose. Matched on the sentence structure rather than by asking Agent 2 for
# the ROUTE intent, because this runs at the route layer before Planning does,
# and the two must not be able to disagree about a question's own grammar.
_PASSAGE_SHAPE = re.compile(r"\bfrom\b.+\bto\b|\bbetween\b.+\band\b", re.IGNORECASE)


def _names_a_passage(text: str) -> bool:
    return _PASSAGE_SHAPE.search(text) is not None


def resolve_or_ask(text: str, session: dict | None = None) -> PlaceResolution:
    """The one entry point. `session` may carry ``last_place`` as
    ``(lat, lon, name)`` — the place this chat last actually resolved — which
    is used only as a *disclosed* carry-over, never as a silent one.
    """
    coords = parse_coordinates(text)
    if coords is not None:
        # A pair outside the data extent is still a resolved position — it is
        # just one we hold nothing for, which is `position_guard`'s answer to
        # give, once, for every position however it was arrived at. Repeating
        # the extent test here would be a second copy free to disagree.
        return PlaceResolution("resolved", coords, [], None)

    places = resolve_all_places_from_text(text)

    if len(places) > 1:
        named = ", ".join(p.name for p in places)
        if _names_a_passage(text):
            # "Safest route from Thoothukudi to Pamban" names two places on
            # purpose, and asking "which did you mean?" back would be absurd.
            # The conditions on this card are still one position's, so it says
            # which: the origin, where the vessel is now.
            origin = places[0]
            return PlaceResolution(
                "resolved", origin, places,
                f"This is a passage ({named}). The conditions below are for {origin.name}, "
                "the origin — plan the whole corridor for a leg-by-leg verdict.",
            )
        return PlaceResolution(
            "ambiguous", None, places,
            f"This names more than one place ({named}). Pick one — conditions at them differ.",
        )

    if len(places) == 1:
        place = places[0]
        if is_region_name(place.name):
            candidates = places_within_region(place.name)
            return PlaceResolution(
                "ambiguous", None, candidates,
                f"{place.name.title()} is a whole coastline, not a position — conditions at "
                f"either end of it are different answers. Which of these did you mean?",
            )
        return PlaceResolution("resolved", place, [], None)

    # Nothing matched exactly. Before treating the query as naming no place at
    # all, check it is not naming one we hold with a typo in it — "gujurat" fell
    # through to the pilot default and got answered with Gulf of Mannar numbers
    # under a Gujarat question. Offered as a question, never resolved silently.
    near = near_miss_place_names(text)
    if near:
        suggested: list[ResolvedPlace] = []
        for name in near:
            suggested.extend(
                places_within_region(name) if is_region_name(name)
                else resolve_all_places_from_text(name)
            )
        if suggested:
            spelled = ", ".join(n.title() for n in near)
            return PlaceResolution(
                "ambiguous", None, suggested[:6],
                f"No place in that question matches anything I hold — did you mean {spelled}? "
                f"Pick one of these and I will answer for it.",
            )

    if names_unplaceable_location(text):
        return PlaceResolution(
            "unresolvable", None, [],
            "I don't know where that is. Name the port, landing centre or stretch of "
            "coast you are asking about, or send your position, and I will answer for it.",
        )

    # A real, well-known place ("Delhi") is not the same absence as naming no
    # place at all. Before this it fell straight through to the pilot default
    # below — answered 1,400 km away with nothing but the model's own wording
    # (when a model happened to run) to say so. Found 2026-09-25.
    inland = inland_place_name(text)
    if inland:
        return PlaceResolution(
            "unresolvable", None, [],
            f"{inland} is inland — I only cover conditions at sea off India's coast. "
            "Name a coastal port or landing centre, or send your position, and I will "
            "answer for it.",
        )

    carried = (session or {}).get("last_place")
    if carried:
        lat, lon, name = carried
        return PlaceResolution(
            "fallback", ResolvedPlace(name, lat, lon, "session_carried"), [],
            f"This question names no place, so it is answered at {name} — the last place "
            f"this conversation named. Name another one if you meant somewhere else.",
        )

    return PlaceResolution(
        "fallback", ResolvedPlace("Gulf of Mannar (default)", DEFAULT_LAT, DEFAULT_LON, "regional_default"), [],
        "This question names no place. It is answered at the pilot default position in the "
        "Gulf of Mannar (8.80N 78.30E) — not your position. Name a place or send your "
        "position for an answer about where you actually are.",
    )


# ---------------------------------------------------------------------------
# P1.4 — the remaining position and time guard clauses (`R-EDGE-3`)
# ---------------------------------------------------------------------------

# Tomorrow / day names / "next week" are answerable; these are the shapes that
# ask for a day the forecast does not reach or has already passed.
_PAST_CUES = (
    "yesterday", "last week", "last month", "last year", "last night",
    "the other day", "a week ago", "days ago", "weeks ago", "months ago",
)
_DATE_IN_TEXT = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAYS_AHEAD = re.compile(r"\b(?:in|after)\s+(\d{1,3})\s+(day|days|week|weeks|month|months)\b")


def _explicit_date(text: str) -> date | None:
    m = _DATE_IN_TEXT.search(text)
    if m is None:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def time_guard(text: str, now: datetime | None = None) -> str | None:
    """The sentence to say when a query asks about a time we have no forecast
    for, or None when the asked-about time is inside the horizon.

    Both directions are real failures: a past date answered off today's
    forecast is a fabricated hindcast, and day 10 answered off day 7's frame
    is a fabricated forecast."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    lowered = text.lower()
    horizon = today + timedelta(days=FORECAST_HORIZON_DAYS)

    asked = _explicit_date(text)
    if asked is not None:
        if asked < today:
            return (
                f"{asked.isoformat()} is in the past. ORCA holds forecasts, not an archive of "
                f"past conditions — I can answer from {today.isoformat()} to {horizon.isoformat()}."
            )
        if asked > horizon:
            return (
                f"{asked.isoformat()} is beyond the {FORECAST_HORIZON_DAYS}-day forecast every "
                f"source here runs to. I can answer up to {horizon.isoformat()}."
            )
        return None

    m = _DAYS_AHEAD.search(lowered)
    if m is not None:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}[unit]
        if days > FORECAST_HORIZON_DAYS:
            return (
                f"{n} {unit} ahead is beyond the {FORECAST_HORIZON_DAYS}-day forecast every source "
                f"here runs to. I can answer up to {horizon.isoformat()}."
            )
        return None

    if any(re.search(rf"\b{re.escape(c)}\b", lowered) for c in _PAST_CUES):
        return (
            "That asks about a time that has passed. ORCA holds forecasts, not an archive of past "
            f"conditions — I can answer from {today.isoformat()} to {horizon.isoformat()}."
        )
    return None


def position_guard(lat: float, lon: float) -> str | None:
    """The sentence to say when a position is one no marine answer is valid
    at — on land, or outside every dataset's extent — or None when it is a
    position we can honestly answer for.

    The land check is the expensive one (it opens the bathymetry grid), so it
    runs last and degrades to "no objection" if the grid is unreadable: a
    missing dataset must not turn into a confident claim about dry land in
    either direction."""
    lat0, lat1, lon0, lon1 = DATA_EXTENT
    if not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1):
        return (
            f"{lat:.4f}, {lon:.4f} is outside the sea area ORCA holds data for "
            f"({lat0:g}-{lat1:g}N, {lon0:g}-{lon1:g}E). I have nothing to answer it with."
        )
    try:
        from orca.agents.geospatial import depth_at_point

        depth = depth_at_point(lat, lon)
    except Exception:
        return None
    if getattr(depth, "on_land", False):
        return (
            f"{lat:.4f}, {lon:.4f} is on land. Wave, tide and depth readings there are not "
            "measurements of anything — name a port or a position at sea."
        )
    return None


# The eighth guard, expired cache, is deliberately NOT here. P0.5 already
# built it: `freshness.past_staleness_ceiling` decides it, `risk_assessment`
# floors the verdict to CAUTION_STALE_DATA on it and names the age in the
# reason, and `confidence_score` bands it. A second implementation in this
# file could only disagree with that one. What Phase 1 adds is putting the
# same fact on the card as a disclosure — see graph.risk_assessment_node.


if __name__ == "__main__":  # self-check; `python -m orca.place_resolution`
    assert resolve_or_ask("is it safe near Veraval").status == "resolved"
    assert resolve_or_ask("conditions at 8.75N 78.25E").status == "resolved"
    assert resolve_or_ask("compare Chennai and Pamban").status == "ambiguous"
    assert resolve_or_ask("is it safe in Kerala").status == "ambiguous"
    assert resolve_or_ask("is it safe near my village").status == "unresolvable"
    delhi = resolve_or_ask("sea conditions near Delhi")
    assert delhi.status == "unresolvable" and "Delhi" in (delhi.disclosure or ""), delhi
    typo = resolve_or_ask("what are the nearest fishing zones near gujurat")
    assert typo.status == "ambiguous" and "did you mean Gujarat" in (typo.disclosure or ""), typo
    assert [c.name for c in typo.candidates] == [c.name for c in resolve_or_ask("near gujarat").candidates]
    assert position_guard(40.0, 10.0) is not None  # resolved, but outside the extent
    assert resolve_or_ask("is it safe to go to sea tomorrow").status == "fallback"
    r = resolve_or_ask("what about tomorrow?", {"last_place": (9.28, 79.20, "pamban")})
    assert r.status == "fallback" and r.place is not None and r.place.name == "pamban", r
    assert time_guard("was it rough yesterday") is not None
    assert time_guard("is it safe in 3 weeks") is not None
    assert time_guard("is it safe tomorrow") is None
    assert position_guard(200.0, 0.0) is not None
    assert position_guard(DEFAULT_LAT, DEFAULT_LON) is None  # the default is wet, by construction
    print("place_resolution self-check OK")
