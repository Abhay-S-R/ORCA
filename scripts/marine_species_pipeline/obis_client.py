"""OBIS (Ocean Biodiversity Information System) Client.

Fetches observed marine fish records from the official OBIS API (https://api.obis.org/v3).
Restricts taxonomy to fish classes:
  - Actinopterygii (Ray-finned fishes, WoRMS AphiaID: 10194)
  - Elasmobranchii (Sharks and Rays, WoRMS AphiaID: 10193)
Extracts unique species checklist and detailed occurrence metadata.
Handles caching, rate limits, pagination, and data cleaning.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any
import pandas as pd
import requests

logger = logging.getLogger("marine_species.obis")

OBIS_API_BASE = "https://api.obis.org/v3"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "obis"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# WoRMS Verified Taxon IDs for Marine Fishes
FISH_TAXON_IDS = ["10194", "10193"]  # Actinopterygii, Elasmobranchii


class OBISClient:
    """Client for retrieving and aggregating marine fish records from OBIS."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ORCA-MarineSpeciesPipeline/1.0 (Ocean Research & Conservation Assistant)"
        })

    def _get_cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        # Stable cache filename from endpoint and sorted parameters
        param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in param_str)[:120]
        return self.cache_dir / f"{endpoint}_{safe_name}.json"

    def fetch_checklist(
        self,
        geometry_wkt: str | None = None,
        depth_min: float | None = None,
        depth_max: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page_size: int = 1000,
        max_records: int = 10000,
    ) -> list[dict[str, Any]]:
        """Fetch unique species checklist from OBIS /checklist endpoint."""
        logger.info(f"Querying OBIS /checklist for fish classes (Actinopterygii: 10194, Elasmobranchii: 10193)")
        
        all_species: list[dict[str, Any]] = []
        skip = 0

        while True:
            params: dict[str, Any] = {
                "taxonid": ",".join(FISH_TAXON_IDS),
                "size": page_size,
                "skip": skip,
            }
            if geometry_wkt:
                params["geometry"] = geometry_wkt
            if depth_min is not None:
                params["depthmin"] = depth_min
            if depth_max is not None:
                params["depthmax"] = depth_max
            if start_date:
                params["startdate"] = start_date
            if end_date:
                params["enddate"] = end_date

            cache_file = self._get_cache_path("checklist", params)
            if cache_file.exists():
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = self._fetch_api("checklist", params, cache_file)
            else:
                data = self._fetch_api("checklist", params, cache_file)

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                # Keep only species-level records
                rank = (item.get("taxonRank") or "").lower()
                scientific_name = item.get("scientificName") or ""
                # Drop genus or family aggregates if rank is not species
                if rank == "species" or (len(scientific_name.split()) >= 2 and not rank):
                    all_species.append({
                        "scientificName": scientific_name,
                        "aphiaID": item.get("acceptedNameUsageID") or item.get("taxonID"),
                        "records": item.get("records", 0),
                        "rank": item.get("taxonRank"),
                        "status": item.get("taxonomicStatus"),
                        "family": item.get("family"),
                        "order": item.get("order"),
                        "class": item.get("class"),
                    })

            total = data.get("total", len(results))
            skip += len(results)
            logger.info(f"Retrieved {len(all_species)} species from OBIS checklist (total available: {total})")

            if skip >= total or skip >= max_records or len(results) < page_size:
                break

            time.sleep(0.2)  # Rate limiting

        return all_species

    def fetch_occurrences(
        self,
        geometry_wkt: str | None = None,
        depth_min: float | None = None,
        depth_max: float | None = None,
        page_size: int = 1000,
        max_occurrences: int = 5000,
    ) -> list[dict[str, Any]]:
        """Fetch detailed occurrences from OBIS /occurrence endpoint."""
        logger.info(f"Querying OBIS /occurrence for detailed spatial telemetry")
        occurrences: list[dict[str, Any]] = []
        skip = 0

        while True:
            params: dict[str, Any] = {
                "taxonid": ",".join(FISH_TAXON_IDS),
                "size": page_size,
                "skip": skip,
            }
            if geometry_wkt:
                params["geometry"] = geometry_wkt
            if depth_min is not None:
                params["depthmin"] = depth_min
            if depth_max is not None:
                params["depthmax"] = depth_max

            cache_file = self._get_cache_path("occurrence", params)
            if cache_file.exists():
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = self._fetch_api("occurrence", params, cache_file)
            else:
                data = self._fetch_api("occurrence", params, cache_file)

            results = data.get("results", [])
            if not results:
                break

            for rec in results:
                lat = rec.get("decimalLatitude")
                lon = rec.get("decimalLongitude")
                name = rec.get("scientificName")
                # Drop records with missing coordinates or missing species name
                if lat is None or lon is None or not name:
                    continue

                event_date = rec.get("eventDate") or ""
                year = rec.get("date_year")
                if not year and event_date and len(event_date) >= 4:
                    try:
                        year = int(event_date[:4])
                    except ValueError:
                        year = None

                occurrences.append({
                    "scientificName": name,
                    "aphiaID": rec.get("aphiaID"),
                    "decimalLatitude": float(lat),
                    "decimalLongitude": float(lon),
                    "depth": rec.get("depth") or rec.get("maximumDepthInMeters"),
                    "eventDate": event_date,
                    "year": year,
                    "datasetName": rec.get("datasetName") or rec.get("dataset_id") or "OBIS Marine Node",
                })

            total = data.get("total", len(results))
            skip += len(results)
            if skip >= total or skip >= max_occurrences or len(results) < page_size:
                break

            time.sleep(0.2)

        return occurrences

    def _fetch_api(self, endpoint: str, params: dict[str, Any], cache_file: Path) -> dict[str, Any]:
        url = f"{OBIS_API_BASE}/{endpoint}"
        retries = 3
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    return data
                elif resp.status_code == 429:
                    logger.warning("OBIS rate limit encountered. Backing off 2s...")
                    time.sleep(2.0)
                else:
                    logger.warning(f"OBIS {endpoint} returned status {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/{retries} failed for OBIS {endpoint}: {e}")
                time.sleep(1.0)
        return {"results": [], "total": 0}

    def process_obis_species(
        self,
        geometry_wkt: str | None = None,
        depth_min: float | None = None,
        depth_max: float | None = None,
    ) -> pd.DataFrame:
        """Run full OBIS extraction and return DataFrame with record_count & last_observed_year."""
        checklist = self.fetch_checklist(geometry_wkt, depth_min, depth_max)
        occurrences = self.fetch_occurrences(geometry_wkt, depth_min, depth_max)

        # Build occurrence aggregates per species
        occ_df = pd.DataFrame(occurrences)
        occ_stats: dict[str, dict[str, Any]] = {}
        if not occ_df.empty:
            for name, grp in occ_df.groupby("scientificName"):
                valid_years = grp["year"].dropna()
                valid_depths = grp["depth"].dropna()
                datasets = list(grp["datasetName"].dropna().unique())
                occ_stats[name] = {
                    "last_observed_year": int(valid_years.max()) if not valid_years.empty else None,
                    "min_observed_depth": float(valid_depths.min()) if not valid_depths.empty else None,
                    "max_observed_depth": float(valid_depths.max()) if not valid_depths.empty else None,
                    "dataset_name": datasets[0] if datasets else "OBIS / IndOBIS",
                }

        rows = []
        for sp in checklist:
            name = sp["scientificName"]
            stats = occ_stats.get(name, {})
            rows.append({
                "scientificName": name,
                "aphiaID": sp.get("aphiaID"),
                "record_count": sp.get("records", 1),
                "last_observed_year": stats.get("last_observed_year"),
                "min_observed_depth": stats.get("min_observed_depth"),
                "max_observed_depth": stats.get("max_observed_depth"),
                "family": sp.get("family"),
                "order": sp.get("order"),
                "dataset_name": stats.get("dataset_name") or "OBIS / IndOBIS",
                "source_url": f"https://mapper.obis.org/?taxonid={sp.get('aphiaID')}",
                "retrieval_date": time.strftime("%Y-%m-%d"),
            })

        df = pd.DataFrame(rows)
        if not df.empty:
            # Deduplicate by scientificName keeping highest record count
            df = df.sort_values(by="record_count", ascending=False).drop_duplicates(subset=["scientificName"])
        return df
