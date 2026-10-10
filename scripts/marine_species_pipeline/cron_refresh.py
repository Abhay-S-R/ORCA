"""Automated Cron Job and Refreshment Runner for Marine Species Data Pipeline.

Handles recurring automated updates for:
  - OBIS new research cruise / spatial observations
  - CMFRI annual and seasonal fishery landings
  - WoRMS taxonomic synonym revisions
Logs every execution and refreshes final merged datasets.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import DEFAULT_USER_WKT, ALL_INDIA_WKT, DEFAULT_OUTPUT_DIR, run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [CRON-REFRESH] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("marine_species.cron")

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
HISTORY_LOG = CACHE_DIR / "cron_refresh_history.json"


def record_history(status: str, details: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    history = []
    if HISTORY_LOG.exists():
        try:
            with open(HISTORY_LOG, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "details": details,
    })

    # Keep last 50 runs
    with open(HISTORY_LOG, "w", encoding="utf-8") as f:
        json.dump(history[-50:], f, indent=2)


def run_refresh_cycle(geometry_wkt: str, prob_threshold: float, output_dir: Path) -> dict:
    logger.info("Executing scheduled marine species data refresh cycle...")
    try:
        report = run_pipeline(
            geometry_wkt=geometry_wkt,
            prob_threshold=prob_threshold,
            output_dir=output_dir,
        )
        record_history("SUCCESS", {
            "duration_seconds": report.get("duration_seconds"),
            "species_count": report.get("sources", {}).get("total_harmonized_species"),
            "obis_count": report.get("sources", {}).get("obis_unique_species"),
        })
        logger.info("Refresh cycle completed successfully.")
        return report
    except Exception as e:
        logger.error(f"Refresh cycle failed with error: {e}", exc_info=True)
        record_history("ERROR", {"error": str(e)})
        raise


def daemon_loop(interval_hours: float, geometry_wkt: str, prob_threshold: float, output_dir: Path) -> None:
    logger.info(f"Starting Marine Species Pipeline daemon loop (Refresh interval: {interval_hours} hours)")
    while True:
        try:
            run_refresh_cycle(geometry_wkt, prob_threshold, output_dir)
        except Exception as e:
            logger.error(f"Error during refresh loop: {e}. Retrying at next interval.")
        
        sleep_seconds = int(interval_hours * 3600)
        logger.info(f"Sleeping for {interval_hours}h ({sleep_seconds}s) until next refresh...")
        time.sleep(sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cron / Daemon Refresh Runner for Marine Species Pipeline")
    parser.add_argument("--interval-hours", type=float, default=None, help="Run as background daemon refreshing every N hours")
    parser.add_argument("--all-india", action="store_true", help="Run refresh for all Indian waters")
    parser.add_argument("--wkt", type=str, default=DEFAULT_USER_WKT, help="Target geometry WKT")
    parser.add_argument("--prob-threshold", type=float, default=0.5, help="AquaMaps threshold")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory")

    args = parser.parse_args()
    target_wkt = ALL_INDIA_WKT if args.all_india else args.wkt
    out_dir = Path(args.output_dir)

    if args.interval_hours is not None and args.interval_hours > 0:
        daemon_loop(args.interval_hours, target_wkt, args.prob_threshold, out_dir)
    else:
        # Run one refresh cycle
        run_refresh_cycle(target_wkt, args.prob_threshold, out_dir)


if __name__ == "__main__":
    main()
