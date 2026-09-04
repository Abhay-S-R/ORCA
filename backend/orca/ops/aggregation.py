"""§5.5 aggregation rules as a hard constraint (plan §4 D2 Day 20): the
authority sees COUNTS per sector, never a plottable individual vessel. Every
function here returns aggregates only — no coordinates, no vessel ids, no
user ids ever leave this module. tests/unit/test_ops_cap.py asserts it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Coarse longitude bands standing in for a real sector polygon lookup (that
# is Agent 6's job — not duplicated here). Deterministic and offline: enough
# to bucket a COUNT, and it never exposes a position because only the count
# is returned. ponytail: lon-band bucketing, swap for point-in-polygon when
# Agent 6 exposes a sector lookup.
_SECTOR_LON_BANDS = [
    ("SEC001", 68.0, 71.0), ("SEC002", 71.0, 73.0), ("SEC003", 73.0, 74.5),
    ("SEC004", 74.5, 76.0), ("SEC005", 76.0, 77.5), ("SEC006", 77.5, 79.0),
    ("SEC007", 79.0, 80.3), ("SEC008", 80.3, 81.5), ("SEC009", 81.5, 83.0),
    ("SEC010", 83.0, 84.5), ("SEC011", 84.5, 86.5), ("SEC012", 86.5, 88.5),
    ("SEC013", 88.5, 91.0), ("SEC014", 91.0, 98.0),
]


def sector_vessel_counts(db: Session) -> dict[str, int]:
    """{sector_id: count of vessels with a position fix in the last 24h}.
    A COUNT, nothing else — the authority sees '14 in SEC004', never 14 dots."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = db.execute(
        text(
            "SELECT ST_X(last_position::geometry) AS lon "
            "FROM vessels WHERE last_position IS NOT NULL AND last_position_at >= :since"
        ),
        {"since": since},
    ).all()
    counts = {sid: 0 for sid, _, _ in _SECTOR_LON_BANDS}
    for (lon,) in rows:
        for sid, lo, hi in _SECTOR_LON_BANDS:
            if lo <= lon < hi:
                counts[sid] += 1
                break
    return counts


def notification_severity_counts(db: Session, hours: int = 24) -> dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.execute(
        text(
            "SELECT severity, count(*) FROM notifications WHERE created_at >= :since GROUP BY severity"
        ),
        {"since": since},
    ).all()
    out = {"info": 0, "advisory": 0, "warning": 0, "danger": 0}
    for sev, n in rows:
        out[sev] = int(n)
    return out


def sector_threat_matrix(db: Session) -> list[dict[str, Any]]:
    """SEC001–SEC014, one row each: PFZ/data status (Agent 5, reused) +
    aggregate vessel count + a severity derived from active notifications.
    No per-vessel data in the row."""
    from orca.agents import ocean_analytics as oa

    vessel_counts = sector_vessel_counts(db)
    sev_counts = notification_severity_counts(db)
    district_severity = (
        "danger" if sev_counts["danger"] else
        "warning" if sev_counts["warning"] else
        "advisory" if sev_counts["advisory"] else "info"
    )
    matrix = []
    for sec in oa.all_sector_status():
        sid = sec["sector_id"]
        matrix.append({
            "sector_id": sid,
            "sector_name": sec.get("sector_name"),
            "pfz_status": sec.get("status"),
            "pfz_message": sec.get("message"),
            "is_data_gap": sec.get("is_data_gap"),
            "vessel_count": vessel_counts.get(sid, 0),
            # district-wide severity today — per-sector alert routing is a
            # later refinement; the matrix already shows where the boats are.
            "alert_severity": district_severity,
        })
    return matrix
