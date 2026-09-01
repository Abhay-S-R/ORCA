"""
Rebuild the marine protected-area geofence layer for the ORCA Geospatial Agent.

Why this exists
---------------
The original `india_marine_mpas.geojson` carried "Gulf of Mannar" as a WDPA
*point* record (site_id 900665, the UNESCO-MAB Biosphere Reserve), not a polygon.
A point cannot answer `point_in_polygon` or `check_boundary_proximity`, so the
pilot region's flagship geofence query -- "Am I approaching the Gulf of Mannar
Marine National Park boundary?" -- had no geometry to compute against.

This was not a sloppy extraction. A spatial query against the authoritative UNEP-WCMC
WDPA polygon service (ProtectedSites/The_World_Database_of_Protected_Areas, layer 1)
over 77-80.5E / 7.5-10.5N returns 147 polygons, none of which is the Gulf of Mannar
Marine National Park; the site exists in WDPA only in the point layer. The polygon
genuinely is not published there, so it has to come from elsewhere.

What this script does
---------------------
Assembles a geofence layer from the best available geometry per site and, critically,
tags every feature with `orca_geofence_usable` so the Risk Assessment Agent can never
silently treat a centroid as a boundary. Point-only records are retained for advisory
context but are explicitly excluded from hard geofence math.

Sources, in order of authority:
  1. UNEP-WCMC WDPA polygon service  -- authoritative, used wherever a polygon exists.
  2. OpenStreetMap relation 415570   -- Gulf of Mannar Marine National Park. Coarse
     (5 parts, ~66 nodes) but correctly delineates the 21-island chain, carries
     protect_class=2 and wikidata Q5617576. Flagged as MEDIUM precision so the agent
     can widen its caution buffer accordingly.

Usage:  python scripts/build_mpa_geofence.py
"""

import json
import os
import time

import requests
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform
from pyproj import Geod, Transformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOUNDARIES = os.path.join(ROOT, "data/tier1/boundaries")
EXISTING = os.path.join(BOUNDARIES, "india_marine_mpas.geojson")
OUTPUT = os.path.join(BOUNDARIES, "india_marine_mpas.geojson")
PROVENANCE = os.path.join(BOUNDARIES, "mpa_geofence_provenance.json")

HEADERS = {"User-Agent": "ORCA-SIH26176-marine-safety/1.0"}

WDPA_POLY = ("https://data-gis.unep-wcmc.org/arcgis/rest/services/ProtectedSites/"
             "The_World_Database_of_Protected_Areas/FeatureServer/1/query")

# Pilot-region envelope: Gulf of Mannar, Palk Bay, Palk Strait approaches.
PILOT_ENVELOPE = "77.0,7.5,80.5,10.5"

# WDPA polygons inside the envelope that are genuinely marine and relevant to the
# pilot region. The envelope also returns ~140 Sri Lankan inland forest reserves,
# which are noise for a marine geofence, so the layer is allow-listed by site_id.
WDPA_KEEP = {
    555790794: "Adam's Bridge Marine National Park (TN, declared 2024)",
    555795353: "Mannar Valaiguda Ramsar site (Gulf of Mannar island chain)",
    62936:     "Bar Reef Marine Sanctuary (Sri Lanka)",
    555790807: "Wedithalathive Nature Reserve (Sri Lanka)",
    555790806: "Vankalai Sanctuary (Sri Lanka)",
}

OSM_GULF_OF_MANNAR = 415570

GEOD = Geod(ellps="WGS84")


def fetch_wdpa_polygons():
    """Pull WDPA polygons over the pilot envelope, keeping the allow-listed sites."""
    params = {
        "geometry": PILOT_ENVELOPE,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "outFields": "*",
        "f": "geojson",
    }
    r = requests.get(WDPA_POLY, params=params, headers=HEADERS, timeout=300)
    r.raise_for_status()
    data = r.json()

    kept = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        sid = props.get("site_id")
        if sid not in WDPA_KEEP:
            continue
        feat["properties"] = _normalise_props(
            props,
            source="UNEP-WCMC WDPA (ProtectedSites/The_World_Database_of_Protected_Areas)",
            source_ref="site_id=%s" % sid,
            precision="HIGH",
            note=WDPA_KEEP[sid],
        )
        kept.append(feat)
        print("  [WDPA] %-11s %s" % (sid, props.get("name")))
    return kept


def fetch_osm_gulf_of_mannar():
    """
    Fetch the Gulf of Mannar Marine National Park outline from OpenStreetMap.

    Nominatim's `lookup` returns the assembled multipolygon directly, which avoids
    having to stitch the relation's member ways by hand. The geometry is coarse, and
    that is recorded honestly in the feature properties rather than smoothed over.
    """
    r = requests.get(
        "https://nominatim.openstreetmap.org/lookup",
        params={"osm_ids": "R%d" % OSM_GULF_OF_MANNAR, "format": "json",
                "polygon_geojson": 1, "extratags": 1},
        headers=HEADERS, timeout=120,
    )
    r.raise_for_status()
    rec = r.json()[0]
    geom = rec["geojson"]
    extra = rec.get("extratags", {})

    props = _normalise_props(
        {
            "site_id": None,
            "name": "Gulf of Mannar Marine National Park",
            "name_eng": "Gulf of Mannar Marine National Park",
            "desig_eng": "Marine National Park",
            "desig_type": "National",
            "iucn_cat": "II" if extra.get("protect_class") == "2" else "Not Reported",
            "rep_area": 560.0,
            "rep_m_area": 560.0,
            "status": "Designated",
            "status_yr": 1986,
            "no_take": "Not Reported",
            "iso3": "IND",
        },
        source="OpenStreetMap relation %d" % OSM_GULF_OF_MANNAR,
        source_ref="wikidata=%s; protect_class=%s" % (
            extra.get("wikidata"), extra.get("protect_class")),
        precision="MEDIUM",
        note=("Not published as a polygon in WDPA (point record site_id=900665 only). "
              "OSM outline delineates the 21-island chain; vertex density is low, so "
              "treat the boundary as approximate and widen the caution buffer."),
    )
    print("  [OSM ] R%-10d %s" % (OSM_GULF_OF_MANNAR, props["name"]))
    return [{"type": "Feature", "properties": props, "geometry": geom}]


def carry_forward_existing(already_have):
    """
    Retain every record from the previous file that this rebuild does not resupply.

    Two categories come through here. Polygons outside the pilot envelope (Sundarbans,
    Chilika, Thane Creek and the like) are kept so the layer retains national coverage
    rather than shrinking to the pilot region. Point-only records are kept because
    dropping the Biosphere Reserve entirely would lose real information -- but each is
    marked `orca_geofence_usable: false` so no agent can mistake a centroid for a
    boundary.

    `already_have` holds the site_ids refetched above; those are skipped so the
    authoritative copy wins over the stale one.
    """
    if not os.path.exists(EXISTING):
        return []
    with open(EXISTING, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    carried = []
    for feat in data.get("features", []):
        props = {k.lower(): v for k, v in feat.get("properties", {}).items()}
        sid = props.get("site_id")
        if sid in already_have:
            continue

        gtype = feat.get("geometry", {}).get("type")
        if gtype in ("Point", "MultiPoint"):
            precision = "CENTROID_ONLY"
            note = ("Point record: WDPA publishes no boundary for this site. Advisory "
                    "context only - excluded from geofence math.")
            tag = "PT  "
        else:
            precision = "HIGH"
            note = ("Authoritative WDPA polygon outside the pilot envelope, carried "
                    "forward to preserve national coverage.")
            tag = "KEEP"

        props = _normalise_props(
            props,
            source="UNEP-WCMC WDPA (carried forward from previous extract)",
            source_ref="site_id=%s" % sid,
            precision=precision,
            note=note,
        )
        carried.append({"type": "Feature", "properties": props,
                        "geometry": feat["geometry"]})
        print("  [%s] %-11s %s" % (tag, sid, props.get("name")))
    return carried


def _normalise_props(props, source, source_ref, precision, note):
    """Project WDPA-style attributes onto a stable schema the agents can rely on."""
    lower = {k.lower(): v for k, v in props.items()}
    return {
        "site_id": lower.get("site_id"),
        "name": lower.get("name") or lower.get("name_eng"),
        "designation": lower.get("desig_eng"),
        "designation_type": lower.get("desig_type"),
        "iucn_category": lower.get("iucn_cat"),
        "status": lower.get("status"),
        "status_year": lower.get("status_yr"),
        "no_take": lower.get("no_take"),
        "iso3": lower.get("iso3") or lower.get("prnt_iso3"),
        "reported_area_km2": lower.get("rep_area"),
        "reported_marine_area_km2": lower.get("rep_m_area"),
        # ORCA-specific fields consumed by the Geospatial Reasoning Agent.
        "orca_source": source,
        "orca_source_ref": source_ref,
        "orca_precision": precision,
        "orca_geofence_usable": precision in ("HIGH", "MEDIUM"),
        "orca_note": note,
    }


def annotate_geometry(features):
    """Attach vertex count, geodesic area and validity to each feature."""
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
    for feat in features:
        geom = shape(feat["geometry"])
        props = feat["properties"]
        props["orca_vertex_count"] = _count_vertices(feat["geometry"]["coordinates"])
        props["orca_geometry_type"] = feat["geometry"]["type"]

        if geom.geom_type in ("Polygon", "MultiPolygon"):
            valid = geom.is_valid
            if not valid:
                # buffer(0) is the standard repair for self-intersecting rings; the
                # architecture's error contract calls for exactly this fallback.
                repaired = geom.buffer(0)
                if repaired.is_valid and not repaired.is_empty:
                    feat["geometry"] = mapping(repaired)
                    geom = repaired
                    props["orca_geometry_repaired"] = True
            props["orca_geometry_valid"] = bool(geom.is_valid)
            area_m2 = abs(GEOD.geometry_area_perimeter(geom)[0])
            props["orca_computed_area_km2"] = round(area_m2 / 1e6, 3)
            bounds = geom.bounds
            props["orca_bbox"] = [round(b, 5) for b in bounds]
        else:
            props["orca_geometry_valid"] = bool(geom.is_valid)
            props["orca_computed_area_km2"] = None
            props["orca_bbox"] = [round(b, 5) for b in geom.bounds]
    return features


def _count_vertices(coords):
    if not coords:
        return 0
    if isinstance(coords[0], (int, float)):
        return 1
    return sum(_count_vertices(c) for c in coords)


if __name__ == "__main__":
    print("=" * 72)
    print("Rebuilding marine protected-area geofence layer")
    print("=" * 72)

    print("\nWDPA polygons (authoritative):")
    features = fetch_wdpa_polygons()

    print("\nOpenStreetMap fallback for sites WDPA has no polygon for:")
    time.sleep(1.0)
    features += fetch_osm_gulf_of_mannar()

    print("\nCarried forward from the previous extract:")
    refetched = {f["properties"]["site_id"] for f in features}
    features += carry_forward_existing(refetched)

    features = annotate_geometry(features)

    usable = [f for f in features if f["properties"]["orca_geofence_usable"]]
    collection = {
        "type": "FeatureCollection",
        "name": "orca_india_marine_mpas",
        "crs": {"type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3/CRS84"}},
        "orca_metadata": {
            "purpose": "Marine protected-area geofence layer for the Geospatial "
                       "Reasoning Agent (check_boundary_proximity, point_in_polygon).",
            "pilot_envelope": PILOT_ENVELOPE,
            "feature_count": len(features),
            "geofence_usable_count": len(usable),
            "rule": "Only features with orca_geofence_usable == true may be used for "
                    "hard geofence decisions. CENTROID_ONLY records are advisory "
                    "context and must never be treated as boundaries.",
            "precision_tiers": {
                "HIGH": "Authoritative WDPA polygon.",
                "MEDIUM": "OpenStreetMap outline; approximate boundary, widen buffer.",
                "CENTROID_ONLY": "Point record; no boundary published.",
            },
        },
        "features": features,
    }

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(collection, fh, ensure_ascii=False, indent=1)

    with open(PROVENANCE, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "features": [
                {k: f["properties"][k] for k in (
                    "name", "designation", "orca_source", "orca_source_ref",
                    "orca_precision", "orca_geofence_usable", "orca_vertex_count",
                    "orca_computed_area_km2", "orca_geometry_valid", "orca_bbox")}
                for f in features
            ],
        }, fh, ensure_ascii=False, indent=1)

    print("\n" + "=" * 72)
    print("%-44s %-9s %6s %10s" % ("FEATURE", "PRECISION", "VERTS", "AREA km2"))
    print("-" * 72)
    for f in features:
        p = f["properties"]
        print("%-44s %-9s %6d %10s" % (
            str(p["name"])[:44], p["orca_precision"], p["orca_vertex_count"],
            p["orca_computed_area_km2"]))
    print("=" * 72)
    print("wrote %s  (%d features, %d geofence-usable)"
          % (OUTPUT, len(features), len(usable)))
    print("wrote %s" % PROVENANCE)
