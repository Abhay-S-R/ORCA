"""WoRMS (World Register of Marine Species) Name Harmonizer.

Resolves scientific and common names to accepted WoRMS valid names and AphiaIDs.
Uses the official WoRMS REST API (https://www.marinespecies.org/rest/) with
local caching, chunked batch resolution, and full logging of unresolved taxa.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any
import requests

logger = logging.getLogger("marine_species.worms")

WORMS_API_BASE = "https://www.marinespecies.org/rest"
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_FILE = CACHE_DIR / "worms_cache.json"
UNRESOLVED_LOG = CACHE_DIR / "unresolved_taxa.log"


class WoRMSResolver:
    """Batch resolver for marine species taxonomy via WoRMS."""

    def __init__(self, cache_file: Path | None = None) -> None:
        self.cache_file = cache_file or CACHE_FILE
        self.cache_dir = self.cache_file.parent
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, dict[str, Any] | None] = self._load_cache()
        self.unresolved: list[str] = []

    def _load_cache(self) -> dict[str, dict[str, Any] | None]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load WoRMS cache: {e}. Starting fresh.")
        return {}

    def _save_cache(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save WoRMS cache: {e}")

    def resolve_names(self, names: list[str], chunk_size: int = 50) -> dict[str, dict[str, Any] | None]:
        """Resolve a list of scientific names to accepted WoRMS taxonomy."""
        unique_names = sorted(set(n.strip() for n in names if n and n.strip()))
        to_fetch = [n for n in unique_names if n not in self.cache]

        if to_fetch:
            logger.info(f"Resolving {len(to_fetch)} new names against WoRMS API (cached: {len(unique_names) - len(to_fetch)})")
            for i in range(0, len(to_fetch), chunk_size):
                chunk = to_fetch[i : i + chunk_size]
                self._resolve_batch(chunk)
                time.sleep(0.2)  # Respect rate limits
            self._save_cache()

        results = {name: self.cache.get(name) for name in unique_names}
        self._write_unresolved_log()
        return results

    def _resolve_batch(self, chunk: list[str]) -> None:
        params = [("scientificnames[]", name) for name in chunk]
        url = f"{WORMS_API_BASE}/AphiaRecordsByNames"
        try:
            resp = requests.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                for name, records in zip(chunk, data):
                    if records and len(records) > 0:
                        rec = records[0]
                        resolved = {
                            "input_name": name,
                            "scientific_name": rec.get("scientificname"),
                            "aphia_id": rec.get("AphiaID"),
                            "valid_name": rec.get("valid_name") or rec.get("scientificname"),
                            "valid_aphia_id": rec.get("valid_AphiaID") or rec.get("AphiaID"),
                            "status": rec.get("status"),
                            "rank": rec.get("taxonRankID"),
                            "family": rec.get("family"),
                            "order": rec.get("order"),
                            "class": rec.get("class"),
                            "is_marine": rec.get("isMarine"),
                            "source_url": rec.get("url"),
                            "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                        self.cache[name] = resolved
                    else:
                        # Fallback to single lookup if batch missed it
                        single = self._resolve_single(name)
                        self.cache[name] = single
                        if single is None:
                            self.unresolved.append(name)
            elif resp.status_code == 204:
                for name in chunk:
                    self.cache[name] = None
                    self.unresolved.append(name)
            else:
                logger.warning(f"WoRMS batch query returned status {resp.status_code}. Falling back to single queries.")
                for name in chunk:
                    self.cache[name] = self._resolve_single(name)
        except Exception as e:
            logger.error(f"Error resolving chunk with WoRMS: {e}")
            for name in chunk:
                if name not in self.cache:
                    self.cache[name] = self._resolve_single(name)

    def _resolve_single(self, name: str) -> dict[str, Any] | None:
        url = f"{WORMS_API_BASE}/AphiaRecordsByName/{requests.utils.quote(name)}"
        try:
            resp = requests.get(url, params={"like": "false"}, timeout=15)
            if resp.status_code == 200:
                records = resp.json()
                if records:
                    rec = records[0]
                    return {
                        "input_name": name,
                        "scientific_name": rec.get("scientificname"),
                        "aphia_id": rec.get("AphiaID"),
                        "valid_name": rec.get("valid_name") or rec.get("scientificname"),
                        "valid_aphia_id": rec.get("valid_AphiaID") or rec.get("AphiaID"),
                        "status": rec.get("status"),
                        "family": rec.get("family"),
                        "order": rec.get("order"),
                        "class": rec.get("class"),
                        "is_marine": rec.get("isMarine"),
                        "source_url": rec.get("url"),
                        "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
        except Exception as e:
            logger.debug(f"Single resolution failed for '{name}': {e}")
        return None

    def _write_unresolved_log(self) -> None:
        if self.unresolved:
            with open(UNRESOLVED_LOG, "a", encoding="utf-8") as f:
                for u in sorted(set(self.unresolved)):
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unresolved name: {u}\n")
            logger.info(f"{len(set(self.unresolved))} names could not be resolved by WoRMS (logged to {UNRESOLVED_LOG})")
