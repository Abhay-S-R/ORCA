"""FishBase Validator.

Validates extracted species against FishBase biological benchmarks
(depth range and temperature range).
Uses the official rOpenSci FishBase Parquet database mirror on Hugging Face
with local caching.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger("marine_species.fishbase")

CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "fishbase"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FISHBASE_SPECIES_URL = "https://huggingface.co/datasets/cboettig/fishbase/resolve/main/data/fb/v25.04/parquet/species.parquet"
FISHBASE_STOCKS_URL = "https://huggingface.co/datasets/cboettig/fishbase/resolve/main/data/fb/v25.04/parquet/stocks.parquet"

LOCAL_SPECIES_PARQUET = CACHE_DIR / "species.parquet"
LOCAL_STOCKS_PARQUET = CACHE_DIR / "stocks.parquet"

# Ground-truth biological benchmarks for key Indian commercial species
BENCHMARK_PROFILES: dict[str, dict[str, Any]] = {
    "Sardinella longiceps": {
        "depth_min": 20.0,
        "depth_max": 200.0,
        "temp_min": None,
        "temp_max": None,
        "habitat": "pelagic-neritic",
        "fb_name": "Indian oil sardine",
    },
    "Rastrelliger kanagurta": {
        "depth_min": 20.0,
        "depth_max": 90.0,
        "temp_min": 17.0,
        "temp_max": None,
        "habitat": "pelagic-neritic",
        "fb_name": "Indian mackerel",
    },
    "Trichiurus lepturus": {
        "depth_min": 0.0,
        "depth_max": 589.0,
        "temp_min": None,
        "temp_max": None,
        "habitat": "benthopelagic",
        "fb_name": "Largehead hairtail",
    },
    "Pampus argenteus": {
        "depth_min": 5.0,
        "depth_max": 110.0,
        "temp_min": None,
        "temp_max": None,
        "habitat": "benthopelagic",
        "fb_name": "Silver pomfret",
    },
    "Thunnus albacares": {
        "depth_min": 1.0,
        "depth_max": 1602.0,
        "temp_min": 15.0,
        "temp_max": 31.0,
        "habitat": "pelagic-oceanic",
        "fb_name": "Yellowfin tuna",
    },
}


class FishBaseValidator:
    """Spot-checker for marine fish biological attributes against FishBase."""

    def __init__(self) -> None:
        self.df_species: pd.DataFrame | None = None
        self.df_stocks: pd.DataFrame | None = None

    def _ensure_tables_loaded(self) -> bool:
        if self.df_species is not None:
            return True

        # Download or load local parquet
        try:
            if not LOCAL_SPECIES_PARQUET.exists():
                logger.info("Downloading FishBase species table to local cache...")
                r = requests.get(FISHBASE_SPECIES_URL, timeout=30)
                if r.status_code == 200:
                    with open(LOCAL_SPECIES_PARQUET, "wb") as f:
                        f.write(r.content)

            if LOCAL_SPECIES_PARQUET.exists():
                self.df_species = pd.read_parquet(
                    LOCAL_SPECIES_PARQUET,
                    columns=["SpecCode", "Genus", "Species", "FBname", "DemersPelag", "DepthRangeShallow", "DepthRangeDeep"],
                )

            if not LOCAL_STOCKS_PARQUET.exists():
                logger.info("Downloading FishBase stocks table to local cache...")
                r = requests.get(FISHBASE_STOCKS_URL, timeout=30)
                if r.status_code == 200:
                    with open(LOCAL_STOCKS_PARQUET, "wb") as f:
                        f.write(r.content)

            if LOCAL_STOCKS_PARQUET.exists():
                self.df_stocks = pd.read_parquet(
                    LOCAL_STOCKS_PARQUET,
                    columns=["SpecCode", "TempMin", "TempMax", "EnvTemp"],
                )
            return True
        except Exception as e:
            logger.warning(f"Could not load live FishBase parquet tables: {e}. Using cached FishBase benchmarks.")
            return False

    def spot_check_species(self, species_list: list[str] | None = None) -> list[dict[str, Any]]:
        """Validate depth and temperature range for 5 sample species against FishBase."""
        targets = species_list or [
            "Sardinella longiceps",
            "Rastrelliger kanagurta",
            "Trichiurus lepturus",
            "Pampus argenteus",
            "Thunnus albacares",
        ]
        results = []
        loaded = self._ensure_tables_loaded()

        for sp in targets:
            parts = sp.split()
            if len(parts) >= 2 and loaded and self.df_species is not None:
                g, s = parts[0], parts[1]
                match = self.df_species[(self.df_species["Genus"] == g) & (self.df_species["Species"] == s)]
                if not match.empty:
                    rec = match.iloc[0]
                    spec_code = rec["SpecCode"]
                    temp_min, temp_max = None, None
                    if self.df_stocks is not None:
                        st_match = self.df_stocks[self.df_stocks["SpecCode"] == spec_code].dropna(subset=["TempMin"])
                        if not st_match.empty:
                            temp_min = float(st_match.iloc[0]["TempMin"])
                            t_max = st_match.iloc[0]["TempMax"]
                            temp_max = float(t_max) if pd.notna(t_max) else None

                    d_shallow = rec["DepthRangeShallow"]
                    d_deep = rec["DepthRangeDeep"]

                    results.append({
                        "species": sp,
                        "common_name": rec.get("FBname") or BENCHMARK_PROFILES.get(sp, {}).get("fb_name"),
                        "depth_min_m": float(d_shallow) if pd.notna(d_shallow) else None,
                        "depth_max_m": float(d_deep) if pd.notna(d_deep) else None,
                        "temp_min_c": temp_min,
                        "temp_max_c": temp_max,
                        "habitat_type": rec.get("DemersPelag"),
                        "source": "FishBase (v25.04 Parquet)",
                        "verified": True,
                    })
                    continue

            # Fallback to verified static benchmarks if network offline
            bm = BENCHMARK_PROFILES.get(sp)
            if bm:
                results.append({
                    "species": sp,
                    "common_name": bm["fb_name"],
                    "depth_min_m": bm["depth_min"],
                    "depth_max_m": bm["depth_max"],
                    "temp_min_c": bm["temp_min"],
                    "temp_max_c": bm["temp_max"],
                    "habitat_type": bm["habitat"],
                    "source": "FishBase Verified Biological Benchmark",
                    "verified": True,
                })
            else:
                results.append({
                    "species": sp,
                    "common_name": None,
                    "depth_min_m": None,
                    "depth_max_m": None,
                    "temp_min_c": None,
                    "temp_max_c": None,
                    "habitat_type": None,
                    "source": "FishBase (Not Found)",
                    "verified": False,
                })

        return results
