"""
Scrape INCOIS Potential Fishing Zone (PFZ) advisories for all 14 coastal sectors.

Why this replaces the previous extract
--------------------------------------
The original snapshot held 318 nodes but none for the ORCA pilot region. The cause
was not a scraper bug: INCOIS publishes nothing for SOUTH TAMILNADU when the sector
is clouded, and says so explicitly --

    "No data available for this sector due to excessive cloud cover"

PFZ advisories are derived from satellite SST and chlorophyll retrievals, so cloud
cover suppresses issuance outright. A pilot region on the Bay of Bengal coast will
hit this regularly, which means "no advisory today" is a normal operating state the
system must answer gracefully, not an error to swallow.

So this scraper records sector *status* as a first-class result. A clouded sector
produces a NO_DATA_CLOUD_COVER row carrying INCOIS's own wording, which the Ocean
Analytics Agent can surface verbatim instead of returning an empty result that looks
like a failure. That is the same honesty the architecture already demands of the
freshness and LOW-DATA confidence tiers.

Each run also archives itself under pfz/history/<date>/, so repeated runs accumulate
the advisory time-series that Agent 5's `score_pfz_persistence` tool needs.

Endpoints (discovered via the INCOIS sitemap; the WebGIS iframe's JSON service sits
on an internal 172.16.x.x address and is not reachable publicly):
    /MarineFisheries/TextDataHome?mfid=1&request_locale=<lang>   sector index
    /MarineFisheries/TextData?secid=SEC001..SEC014               per-sector advisory

Usage:  python scripts/scrape_pfz_advisories.py
"""

import json
import os
import re
import sys
import time
import warnings
from datetime import datetime, timezone

import requests

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFZ_DIR = os.path.join(ROOT, "data/incois_osf_pfz/pfz")
HISTORY_DIR = os.path.join(PFZ_DIR, "history")
CERT = os.path.join(ROOT, "certs/incois_cert.pem")

BASE = "https://incois.gov.in/MarineFisheries"
HOME = BASE + "/TextDataHome"
SECTOR = BASE + "/TextData"

HEADERS = {"User-Agent": "Mozilla/5.0 ORCA-SIH26176-marine-research/1.0"}

# INCOIS serves the same advisory in ten languages. English drives the data model;
# the others are fetched only for the pilot sectors, to back the User Interaction
# Agent's vernacular rendering with INCOIS's own official wording rather than a
# machine translation of it.
LANGUAGES = ["en", "hi", "ta", "te", "ml", "kn", "mr", "gu", "or", "bn"]
PILOT_SECTORS = ["SEC006", "SEC007"]

SECTOR_COUNT = 14
REQUEST_PAUSE = 0.5  # be a polite client against a government portal


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = CERT if os.path.exists(CERT) else True
    return s


def strip_tags(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def fetch_sector_names(session):
    """Read the secid -> sector-name map out of the index page's selector."""
    r = session.get(HOME, params={"mfid": 1, "request_locale": "en"}, timeout=90)
    r.raise_for_status()
    names = {}
    for sec, label in re.findall(
            r"secid=(SEC\d+)'\s*>\s*([^<]+?)\s*</option>", r.text):
        names[sec] = label.strip()
    return names, r.text


def dms_to_decimal(text):
    """Convert '13 19 10 N' to signed decimal degrees."""
    m = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*([NSEW])\s*$", text.strip(), re.I)
    if not m:
        return None
    deg, minutes, seconds, hemi = m.groups()
    value = int(deg) + int(minutes) / 60.0 + float(seconds) / 3600.0
    if hemi.upper() in ("S", "W"):
        value = -value
    return round(value, 6)


def parse_validity(text):
    """Pull the advisory's validity date, e.g. '2 SEP 2026'."""
    m = re.search(r"(\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
                  r"[A-Z]*\s+\d{4})", text, re.I)
    if not m:
        return None
    raw = re.sub(r"\s+", " ", m.group(1)).strip()
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw.title(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def classify_empty(plain_text):
    """
    Distinguish why a sector carries no advisory.

    Cloud cover is the dominant cause and INCOIS states it explicitly, so it gets its
    own status rather than being lumped into a generic empty result. Downstream this
    is the difference between "we could not reach the data" and "the satellite could
    not see the sea", which are very different things to tell a fisherman.
    """
    low = plain_text.lower()
    # The page carries no sentence punctuation around the notice, so anchor on the
    # notice's own leading words rather than sentence boundaries -- a greedy
    # "[^.]*cloud cover[^.]*" swallows the surrounding site chrome instead.
    # Prefer the full notice including its stated cause; fall back to the bare
    # "no data" phrase when no cause is given. Both patterns run forward from the
    # notice's opening words and are length-bounded, so neither can reach the
    # surrounding site chrome.
    notice = (re.search(r"(No\s+data\s+available.{0,90}?cloud\s+cover)", plain_text, re.I)
              or re.search(r"(No\s+data\s+available[^A-Z]{0,90})", plain_text, re.I))
    message = re.sub(r"\s+", " ", notice.group(1)).strip() if notice else None

    if "cloud cover" in low:
        return "NO_DATA_CLOUD_COVER", (
            message or "No data available for this sector due to excessive cloud cover")
    if "not available" in low or "no data" in low:
        return "NO_DATA_OTHER", (message or "No data available for this sector")
    return "NO_DATA_OTHER", "Sector returned no advisory rows and no explanatory message"


def parse_sector(html, sector_id, sector_name):
    """Parse one sector page into (status, message, validity, node rows)."""
    plain = strip_tags(html)
    validity = parse_validity(plain)

    rows = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).replace("&nbsp;", " ").strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)]
        cells = [c for c in cells if c]
        # A data row is exactly: centre, direction, bearing, distance, depth, lat, lon.
        if len(cells) != 7:
            continue
        centre, direction, bearing, distance, depth, lat_dms, lon_dms = cells
        lat = dms_to_decimal(lat_dms)
        lon = dms_to_decimal(lon_dms)
        if lat is None or lon is None:
            continue  # header row or malformed entry
        rows.append({
            "sector_id": sector_id,
            "sector": sector_name,
            "landing_center": centre,
            "direction": direction,
            "bearing_deg": _int_or_none(bearing),
            "distance_km": distance,
            "depth_m": depth,
            "latitude_dms": lat_dms,
            "longitude_dms": lon_dms,
            "latitude_dd": lat,
            "longitude_dd": lon,
            "valid_for": validity,
        })

    if rows:
        return "HAS_ADVISORY", None, validity, rows
    status, message = classify_empty(plain)
    return status, message, validity, []


def _int_or_none(text):
    m = re.match(r"^\s*(\d+)", text)
    return int(m.group(1)) if m else None


def fetch_vernacular(session, sector_id, sector_name):
    """Capture INCOIS's own wording per language for the pilot sectors."""
    out = {}
    for lang in LANGUAGES:
        try:
            session.get(HOME, params={"mfid": 1, "request_locale": lang}, timeout=60)
            r = session.get(SECTOR, params={"secid": sector_id}, timeout=60)
            plain = strip_tags(r.text)
            status, message, validity, rows = parse_sector(r.text, sector_id, sector_name)
            out[lang] = {"status": status, "message": message,
                         "row_count": len(rows), "valid_for": validity}
        except requests.RequestException as exc:
            out[lang] = {"status": "FETCH_ERROR", "message": str(exc)[:120]}
        time.sleep(REQUEST_PAUSE)
    # restore English for subsequent calls
    session.get(HOME, params={"mfid": 1, "request_locale": "en"}, timeout=60)
    return out


def main():
    os.makedirs(PFZ_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    session = make_session()

    print("=" * 78)
    print("INCOIS PFZ advisory scrape")
    print("=" * 78)

    try:
        sector_names, _ = fetch_sector_names(session)
    except requests.RequestException as exc:
        print("FATAL: could not reach INCOIS sector index: %s" % exc)
        return 1
    print("sector index: %d sectors\n" % len(sector_names))

    all_rows = []
    sector_status = []
    for i in range(1, SECTOR_COUNT + 1):
        sid = "SEC%03d" % i
        name = sector_names.get(sid, sid)
        try:
            r = session.get(SECTOR, params={"secid": sid}, timeout=90)
            r.raise_for_status()
        except requests.RequestException as exc:
            print("  %-7s %-18s FETCH_ERROR %s" % (sid, name[:18], str(exc)[:40]))
            sector_status.append({"sector_id": sid, "sector": name,
                                  "status": "FETCH_ERROR", "message": str(exc)[:200],
                                  "node_count": 0, "valid_for": None})
            continue

        status, message, validity, rows = parse_sector(r.text, sid, name)
        all_rows.extend(rows)
        sector_status.append({
            "sector_id": sid, "sector": name, "status": status,
            "message": message, "node_count": len(rows), "valid_for": validity,
        })
        note = "" if status == "HAS_ADVISORY" else "  <- %s" % (message or "")[:52]
        print("  %-7s %-18s %-22s nodes=%-4d valid=%s%s"
              % (sid, name[:18], status, len(rows), validity, note))
        time.sleep(REQUEST_PAUSE)

    # Vernacular capture for the pilot sectors only -- ten languages across all
    # fourteen sectors would be 140 requests against a government portal.
    print("\nvernacular capture (pilot sectors, %d languages):" % len(LANGUAGES))
    vernacular = {}
    for sid in PILOT_SECTORS:
        name = sector_names.get(sid, sid)
        vernacular[sid] = {"sector": name, "languages": fetch_vernacular(session, sid, name)}
        got = sum(1 for v in vernacular[sid]["languages"].values()
                  if v.get("status") != "FETCH_ERROR")
        print("  %-7s %-18s %d/%d languages captured" % (sid, name[:18], got, len(LANGUAGES)))

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d")

    write_outputs(all_rows, sector_status, vernacular, sector_names, now, stamp)
    return 0


def write_outputs(rows, sector_status, vernacular, sector_names, now, stamp):
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for row in rows:
        row["source"] = "INCOIS Marine Fisheries Advisory (TextData)"
        row["scraped_at"] = iso

    fields = ["sector_id", "sector", "landing_center", "direction", "bearing_deg",
              "distance_km", "depth_m", "latitude_dms", "longitude_dms",
              "latitude_dd", "longitude_dd", "valid_for", "source", "scraped_at"]

    csv_path = os.path.join(PFZ_DIR, "incois_pfz_live_advisories_master.csv")
    _write_csv(csv_path, rows, fields)

    json_path = os.path.join(PFZ_DIR, "incois_pfz_live_advisories_master.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)

    geojson = {
        "type": "FeatureCollection",
        "name": "incois_pfz_live_advisories",
        "orca_metadata": {
            "scraped_at": iso,
            "node_count": len(rows),
            "sectors_with_advisory": sum(1 for s in sector_status
                                         if s["status"] == "HAS_ADVISORY"),
            "note": "Sectors absent from this collection are not failures -- consult "
                    "pfz_sector_status.json for why (commonly cloud cover).",
        },
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [r["longitude_dd"], r["latitude_dd"]]},
            "properties": {k: r[k] for k in fields if k in r},
        } for r in rows],
    }
    geo_path = os.path.join(PFZ_DIR, "incois_pfz_live_advisories.geojson")
    with open(geo_path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh, ensure_ascii=False, indent=1)

    status_doc = {
        "scraped_at": iso,
        "sector_names": sector_names,
        "summary": {
            "total_sectors": len(sector_status),
            "with_advisory": sum(1 for s in sector_status if s["status"] == "HAS_ADVISORY"),
            "cloud_cover": sum(1 for s in sector_status
                               if s["status"] == "NO_DATA_CLOUD_COVER"),
            "other_no_data": sum(1 for s in sector_status if s["status"] == "NO_DATA_OTHER"),
            "fetch_error": sum(1 for s in sector_status if s["status"] == "FETCH_ERROR"),
            "total_nodes": len(rows),
        },
        "sectors": sector_status,
        "pilot_vernacular": vernacular,
        "agent_contract": {
            "HAS_ADVISORY": "Nodes present; analyze_pfz_proximity may run normally.",
            "NO_DATA_CLOUD_COVER": "INCOIS issued no advisory because satellite "
                                   "retrieval was blocked by cloud. Report this reason "
                                   "verbatim and fall back to pfz_persistence_baseline"
                                   ".json; confidence tier must be LOW-DATA.",
            "NO_DATA_OTHER": "No advisory and no stated cause. Same fallback as cloud "
                             "cover but state the cause as unknown.",
            "FETCH_ERROR": "Upstream unreachable. Use cached history and mark stale.",
        },
    }
    status_path = os.path.join(PFZ_DIR, "pfz_sector_status.json")
    with open(status_path, "w", encoding="utf-8") as fh:
        json.dump(status_doc, fh, ensure_ascii=False, indent=1)

    # Archive this run so repeated runs accumulate the persistence time-series.
    run_dir = os.path.join(HISTORY_DIR, stamp)
    os.makedirs(run_dir, exist_ok=True)
    _write_csv(os.path.join(run_dir, "advisories.csv"), rows, fields)
    with open(os.path.join(run_dir, "sector_status.json"), "w", encoding="utf-8") as fh:
        json.dump(status_doc, fh, ensure_ascii=False, indent=1)

    s = status_doc["summary"]
    print("\n" + "=" * 78)
    print("sectors: %d with advisory | %d cloud-blocked | %d other | %d errors"
          % (s["with_advisory"], s["cloud_cover"], s["other_no_data"], s["fetch_error"]))
    print("nodes:   %d" % s["total_nodes"])
    print("=" * 78)
    for path in (csv_path, json_path, geo_path, status_path, run_dir):
        print("  wrote %s" % path)


def _write_csv(path, rows, fields):
    import csv
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
