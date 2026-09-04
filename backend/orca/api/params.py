"""Shared coordinate parameter types for the API's trust boundary.

Every route that takes a position takes it from the network, so every one of
them is a trust boundary. Before this existed the range check lived only on
`WatchIn` (orca/notifications/contracts.py) and the auth home-port schema,
and the rest of the surface accepted anything: `/api/tides?lat=999&lon=999`
answered 200 by silently snapping to the Thoothukudi station, `/api/depth`
returned a confident `on_land: false`, `/api/pfz/nearest` raised a 500, and
`/query` produced a full "GO — safe to head out" verdict built on a NaN
boundary distance.

`allow_inf_nan=False` matters as much as the range: NaN passes `is None`
checks and then silently clears every threshold comparison downstream
(see risk_assessment._known), so it must be rejected at the door rather
than defused later.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import Field

# Query-parameter form, e.g. `lat: Lat`.
Lat = Annotated[float, Query(ge=-90.0, le=90.0, allow_inf_nan=False)]
Lon = Annotated[float, Query(ge=-180.0, le=180.0, allow_inf_nan=False)]

# Optional query-parameter form, for routes where position is not required.
OptLat = Annotated[float | None, Query(ge=-90.0, le=90.0, allow_inf_nan=False)]
OptLon = Annotated[float | None, Query(ge=-180.0, le=180.0, allow_inf_nan=False)]

# Request-body form, for pydantic models, e.g. `origin_lat: LatField`.
LatField = Annotated[float, Field(ge=-90.0, le=90.0, allow_inf_nan=False)]
LonField = Annotated[float, Field(ge=-180.0, le=180.0, allow_inf_nan=False)]
