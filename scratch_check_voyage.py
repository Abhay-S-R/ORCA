import sys
from datetime import datetime, timezone
from orca.agents.geospatial import depth_at_point, point_in_polygon, check_boundary_proximity
from orca.agents.voyage import plan_voyage, densify_route

# Let's test several routes:
# 1. From Tuticorin port area / offshore (8.75, 78.20) to Gulf of Mannar offshore (8.50, 78.50)
# 2. Open water in Gulf of Mannar (8.40, 78.30) to (8.20, 78.60)
# 3. Along coast: (8.75, 78.25) to (8.40, 78.15)
# 4. Near Rameswaram / Adams bridge (9.28, 79.30) to (9.15, 79.50)
# 5. Outside Gulf of Mannar (e.g. Kerala coast: 8.5, 76.8 to 8.2, 76.9)

test_routes = [
    ("Open ocean 1", (8.40, 78.30), (8.20, 78.60)),
    ("Tuticorin offshore to GoM", (8.75, 78.25), (8.50, 78.50)),
    ("Tuticorin nearshore to offshore", (8.76, 78.16), (8.60, 78.35)),
    ("Tuticorin port to GoM", (8.75, 78.20), (9.05, 78.95)),
    ("Kerala coast", (8.50, 76.80), (8.20, 76.90)),
    ("Palk Bay shallow", (9.25, 79.20), (9.15, 79.40)),
]

for name, orig, dest in test_routes:
    print(f"\n=================== Route: {name} ({orig} -> {dest}) ===================")
    plan = plan_voyage(orig, dest, vessel_class="small_fishing", speed_kn=8.0)
    print(f"Verdict: {plan.verdict} | Reason: {plan.verdict_reason}")
    for seg in plan.segments[:10]:
        mid_lat = (seg.start[0] + seg.end[0]) / 2
        mid_lon = (seg.start[1] + seg.end[1]) / 2
        dp = depth_at_point(mid_lat, mid_lon)
        print(f"  {seg.segment_id}: {seg.start} -> {seg.end} | status={seg.status} hazard={seg.hazard_class} detail={seg.detail} | mid=({mid_lat:.4f}, {mid_lon:.4f}) dp={dp}")
    if len(plan.segments) > 10:
        print(f"  ... total {len(plan.segments)} segments")
