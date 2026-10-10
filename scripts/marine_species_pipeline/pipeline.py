"""Marine Fish Species Integration Pipeline.

Combines:
  1. OBIS (Observed occurrence records)
  2. AquaMaps (Predicted 0.5° grid habitat suitability)
  3. CMFRI (Commercial fisheries landings)
Harmonized via WoRMS AphiaIDs with multi-factor confidence scoring and FishBase spot-checks.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .aquamaps_client import AquaMapsEngine
from .cmfri_client import CMFRIClient
from .fishbase_validator import FishBaseValidator
from .obis_client import OBISClient
from .worms_resolver import WoRMSResolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("marine_species.pipeline")

DEFAULT_USER_WKT = "POLYGON((80.2 12.5, 80.8 12.5, 80.8 13.2, 80.2 13.2, 80.2 12.5))"
ALL_INDIA_WKT = "POLYGON((65.0 5.0, 95.0 5.0, 95.0 25.0, 65.0 25.0, 65.0 5.0))"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "marine_species_output"


def run_pipeline(
    geometry_wkt: str = DEFAULT_USER_WKT,
    depth_min: float | None = None,
    depth_max: float | None = None,
    prob_threshold: float = 0.5,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    aquamaps_db: Path | str | None = None,
) -> dict[str, Any]:
    """Execute the full 6-step marine species pipeline."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    logger.info("=" * 70)
    logger.info("STARTING MARINE FISH SPECIES PIPELINE")
    logger.info(f"Target Geometry WKT: {geometry_wkt[:60]}... (Length: {len(geometry_wkt)})")
    logger.info(f"Depth Filter: {depth_min}m to {depth_max}m | AquaMaps Prob Threshold: {prob_threshold}")
    logger.info(f"Output Directory: {out_dir}")
    logger.info("=" * 70)

    # -------------------------------------------------------------------------
    # STEP 1: OBIS (Observed records)
    # -------------------------------------------------------------------------
    logger.info("\n>>> STEP 1: OBIS (Observed Records) <<<")
    obis = OBISClient()
    obis_df = obis.process_obis_species(geometry_wkt, depth_min, depth_max)
    obis_csv_path = out_dir / "obis_species.csv"
    obis_df.to_csv(obis_csv_path, index=False)
    logger.info(f"Exported {len(obis_df)} OBIS species to {obis_csv_path}")

    # -------------------------------------------------------------------------
    # STEP 2: AquaMaps (Predicted distribution)
    # -------------------------------------------------------------------------
    logger.info("\n>>> STEP 2: AquaMaps (Predicted Distribution) <<<")
    aq_engine = AquaMapsEngine(db_path=Path(aquamaps_db) if aquamaps_db else None)
    aq_df = aq_engine.query_distribution(geometry_wkt, probability_threshold=prob_threshold)
    aq_csv_path = out_dir / "aquamaps_species.csv"
    aq_df.to_csv(aq_csv_path, index=False)
    logger.info(f"Exported {len(aq_df)} AquaMaps species to {aq_csv_path}")

    # -------------------------------------------------------------------------
    # STEP 3: CMFRI (Commercial landings)
    # -------------------------------------------------------------------------
    logger.info("\n>>> STEP 3: CMFRI (Commercial Landings) <<<")
    cmfri = CMFRIClient()
    cmfri_df = cmfri.get_landings_for_geometry(geometry_wkt)
    cmfri_csv_path = out_dir / "cmfri_landings.csv"
    cmfri_df.to_csv(cmfri_csv_path, index=False)
    logger.info(f"Exported {len(cmfri_df)} CMFRI landing groups to {cmfri_csv_path}")

    # -------------------------------------------------------------------------
    # STEP 4: Harmonize Names via WoRMS
    # -------------------------------------------------------------------------
    logger.info("\n>>> STEP 4: Taxonomic Harmonization via WoRMS <<<")
    all_raw_names: set[str] = set()
    if not obis_df.empty:
        all_raw_names.update(obis_df["scientificName"].dropna())
    if not aq_df.empty:
        all_raw_names.update(aq_df["species"].dropna())
    if not cmfri_df.empty:
        all_raw_names.update(cmfri_df["species"].dropna())

    logger.info(f"Collected {len(all_raw_names)} distinct raw taxonomic names across all 3 sources")
    resolver = WoRMSResolver()
    resolved_map = resolver.resolve_names(list(all_raw_names))

    # Helper function to get valid AphiaID and valid name
    def get_valid_taxon(name: str) -> tuple[int | None, str]:
        info = resolved_map.get(name)
        if info and info.get("valid_aphia_id"):
            return info["valid_aphia_id"], info["valid_name"]
        return None, name

    # Map datasets to valid AphiaIDs
    obis_by_aphia: dict[int, dict[str, Any]] = {}
    if not obis_df.empty:
        for _, row in obis_df.iterrows():
            aphia_id, valid_name = get_valid_taxon(row["scientificName"])
            if aphia_id:
                obis_by_aphia[aphia_id] = {
                    "valid_name": valid_name,
                    "record_count": row["record_count"],
                    "last_observed_year": row["last_observed_year"],
                    "family": row.get("family"),
                    "order": row.get("order"),
                    "dataset_name": row.get("dataset_name"),
                }

    aq_by_aphia: dict[int, dict[str, Any]] = {}
    if not aq_df.empty:
        for _, row in aq_df.iterrows():
            aphia_id, valid_name = get_valid_taxon(row["species"])
            if aphia_id:
                aq_by_aphia[aphia_id] = {
                    "valid_name": valid_name,
                    "max_prob": row["max_probability"],
                    "mean_prob": row["mean_probability"],
                    "cells_count": row["cells_count"],
                }

    cmfri_by_aphia: dict[int, dict[str, Any]] = {}
    if not cmfri_df.empty:
        for _, row in cmfri_df.iterrows():
            aphia_id, valid_name = get_valid_taxon(row["species"])
            if aphia_id:
                cmfri_by_aphia[aphia_id] = {
                    "valid_name": valid_name,
                    "tonnes": row["tonnes"],
                    "state": row["state"],
                    "common_name": row["common_name"],
                }

    # -------------------------------------------------------------------------
    # STEP 5: Merge and Confidence Scoring
    # -------------------------------------------------------------------------
    logger.info("\n>>> STEP 5: Merging and Scoring Confidence <<<")
    all_aphia_ids = sorted(set(obis_by_aphia.keys()) | set(aq_by_aphia.keys()) | set(cmfri_by_aphia.keys()))
    final_rows: list[dict[str, Any]] = []

    for aid in all_aphia_ids:
        in_obis = aid in obis_by_aphia
        in_aq = aid in aq_by_aphia
        in_cmfri = aid in cmfri_by_aphia

        o_data = obis_by_aphia.get(aid, {})
        a_data = aq_by_aphia.get(aid, {})
        c_data = cmfri_by_aphia.get(aid, {})

        valid_name = o_data.get("valid_name") or a_data.get("valid_name") or c_data.get("valid_name")
        common_name = c_data.get("common_name")

        prob = a_data.get("max_prob")
        tonnes = c_data.get("tonnes")
        records = o_data.get("record_count")

        # Confidence Scoring:
        # High   = in OBIS (and ideally also AquaMaps)
        # Medium = AquaMaps probability >= 0.5 and in CMFRI for the region
        # Low    = AquaMaps only, or CMFRI only
        if in_obis:
            confidence = "High"
            if in_aq and in_cmfri:
                rationale = "Triply validated: Observed in OBIS, modelled high by AquaMaps, and commercially landed by CMFRI"
            elif in_aq:
                rationale = "Observed directly in OBIS telemetry and supported by AquaMaps environmental suitability"
            elif in_cmfri:
                rationale = "Observed directly in OBIS sampling and confirmed in regional commercial landings"
            else:
                rationale = "Observed directly in scientific marine surveys recorded in OBIS"
        elif in_aq and in_cmfri and (prob is not None and prob >= 0.5):
            confidence = "Medium"
            rationale = f"AquaMaps probability {prob:.2f} >= 0.5 and confirmed landed in region ({tonnes:,} tonnes)"
        else:
            confidence = "Low"
            if in_aq and not in_cmfri:
                rationale = f"Modelled suitability only ({prob:.2f}), absent from recent scientific surveys and landing logs"
            else:
                rationale = f"Reported in regional landing logs ({tonnes:,} t), but unverified by local spatial survey points"

        final_rows.append({
            "aphia_id": aid,
            "scientific_name": valid_name,
            "common_name": common_name,
            "family": o_data.get("family"),
            "order": o_data.get("order"),
            "in_obis": in_obis,
            "in_aquamaps": in_aq,
            "in_cmfri": in_cmfri,
            "obis_records": records,
            "last_observed_year": o_data.get("last_observed_year"),
            "aquamaps_prob": prob,
            "cmfri_tonnes": tonnes,
            "confidence": confidence,
            "confidence_rationale": rationale,
        })

    final_df = pd.DataFrame(final_rows)
    if not final_df.empty:
        # Sort by confidence order (High, Medium, Low) then by obis_records / tonnes
        conf_map = {"High": 1, "Medium": 2, "Low": 3}
        final_df["_sort_rank"] = final_df["confidence"].map(conf_map)
        final_df = final_df.sort_values(by=["_sort_rank", "obis_records", "cmfri_tonnes"], ascending=[True, False, False]).drop(columns=["_sort_rank"])

    final_csv_path = out_dir / "final_species_list.csv"
    final_df.to_csv(final_csv_path, index=False)
    logger.info(f"Exported {len(final_df)} merged species to {final_csv_path}")

    # -------------------------------------------------------------------------
    # STEP 6: Validate & Spot-Check against FishBase
    # -------------------------------------------------------------------------
    logger.info("\n>>> STEP 6: Validation and FishBase Spot-Check <<<")
    n_obis = len(obis_df)
    n_aq = len(aq_df)
    n_cmfri = len(cmfri_df)
    n_merged = len(final_df)

    # Overlaps
    set_o = set(obis_by_aphia.keys())
    set_a = set(aq_by_aphia.keys())
    set_c = set(cmfri_by_aphia.keys())

    overlap_oa = len(set_o & set_a)
    overlap_oc = len(set_o & set_c)
    overlap_ac = len(set_a & set_c)
    overlap_all = len(set_o & set_a & set_c)

    # Check for sparse OBIS warning
    warnings = []
    if n_obis < 10:
        warning_msg = (
            f"WARNING: OBIS returned only {n_obis} species for this selection. "
            "Sparse sampling in this ocean bounding box does NOT constitute proof of biological absence."
        )
        logger.warning(warning_msg)
        warnings.append(warning_msg)

    # FishBase Spot-Check
    fb_validator = FishBaseValidator()
    spot_check_results = fb_validator.spot_check_species()

    logger.info("\n" + "=" * 50)
    logger.info("FISHBASE SPOT-CHECK VERIFICATION TABLE (5 Sample Species):")
    logger.info("=" * 50)
    for sc in spot_check_results:
        logger.info(
            f"• {sc['species']} ({sc.get('common_name')}): "
            f"Depth: {sc.get('depth_min_m')}m – {sc.get('depth_max_m')}m | "
            f"Temp: {sc.get('temp_min_c')}°C – {sc.get('temp_max_c')}°C | "
            f"Habitat: {sc.get('habitat_type')}"
        )

    # Summary JSON Report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "duration_seconds": round(time.time() - start_time, 2),
        "input_geometry": geometry_wkt[:100],
        "sources": {
            "obis_unique_species": n_obis,
            "aquamaps_predicted_species": n_aq,
            "cmfri_landings_groups": n_cmfri,
            "total_harmonized_species": n_merged,
        },
        "overlaps": {
            "obis_and_aquamaps": overlap_oa,
            "obis_and_cmfri": overlap_oc,
            "aquamaps_and_cmfri": overlap_ac,
            "triply_validated_all_three": overlap_all,
        },
        "confidence_breakdown": {
            "High": int((final_df["confidence"] == "High").sum()) if not final_df.empty else 0,
            "Medium": int((final_df["confidence"] == "Medium").sum()) if not final_df.empty else 0,
            "Low": int((final_df["confidence"] == "Low").sum()) if not final_df.empty else 0,
        },
        "warnings": warnings,
        "fishbase_spot_checks": spot_check_results,
        "output_files": {
            "obis_csv": str(obis_csv_path),
            "aquamaps_csv": str(aq_csv_path),
            "cmfri_csv": str(cmfri_csv_path),
            "final_species_csv": str(final_csv_path),
        },
    }

    report_path = out_dir / "species_pipeline_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"\nExecution finished in {report['duration_seconds']}s. Full report saved to {report_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Marine Fish Species Data Pipeline (OBIS + AquaMaps + CMFRI)")
    parser.add_argument("--wkt", type=str, default=DEFAULT_USER_WKT, help="Polygon or bounding box in WKT format")
    parser.add_argument("--all-india", action="store_true", help="Run for the entire Indian EEZ / waters (65-95E, 5-25N)")
    parser.add_argument("--depth-min", type=float, default=None, help="Minimum depth filter in meters")
    parser.add_argument("--depth-max", type=float, default=None, help="Maximum depth filter in meters")
    parser.add_argument("--prob-threshold", type=float, default=0.5, help="AquaMaps probability threshold (default: 0.5)")
    parser.add_argument("--aquamaps-db", type=str, default=None, help="Path to local AquaMaps SQLite database (am.db)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory for generated CSVs")

    args = parser.parse_args()

    target_wkt = ALL_INDIA_WKT if args.all_india else args.wkt
    run_pipeline(
        geometry_wkt=target_wkt,
        depth_min=args.depth_min,
        depth_max=args.depth_max,
        prob_threshold=args.prob_threshold,
        output_dir=Path(args.output_dir),
        aquamaps_db=Path(args.aquamaps_db) if args.aquamaps_db else None,
    )


if __name__ == "__main__":
    main()
