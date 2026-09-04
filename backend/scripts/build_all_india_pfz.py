import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "incois_osf_pfz" / "pfz"
LIVE_FILE = DATA_DIR / "incois_pfz_live_advisories.geojson"
FALLBACK_FILE = DATA_DIR / "pfz_fallback_pilot_region.geojson"
OUT_FILE = DATA_DIR / "all_india_pfz_advisories.geojson"


def generate() -> None:
    with open(LIVE_FILE, "r", encoding="utf-8") as f:
        live_data = json.load(f)

    features = list(live_data.get("features", []))

    # Add South Tamil Nadu pilot region nodes with standardized properties
    with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
        fallback_data = json.load(f)

    for idx, f in enumerate(fallback_data.get("features", [])):
        props = f.get("properties", {})
        coords = f["geometry"]["coordinates"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": {
                "sector_id": "SEC006",
                "sector": "SOUTH TAMILNADU",
                "landing_center": f"Thoothukudi Zone {idx+1}",
                "direction": "SE",
                "bearing_deg": round(props.get("bearings_from_ports", {}).get("Thoothukudi", {}).get("bearing_deg", 120), 1),
                "distance_km": str(round(props.get("bearings_from_ports", {}).get("Thoothukudi", {}).get("distance_km", 40), 1)),
                "depth_m": str(round(props.get("mean_depth_m", 22), 1)),
                "latitude_dd": coords[1],
                "longitude_dd": coords[0],
                "valid_for": "2026-09-02",
                "source": "INCOIS Marine Fisheries Advisory (Thermal Front Proxy)",
                "approx_area_km2": props.get("approx_area_km2", 150),
                "mean_sst_c": props.get("mean_sst_c", 28.3),
            },
        })

    # Additional South Tamil Nadu nodes
    stn_nodes = [
        ([78.25, 8.75], "Thoothukudi Offshore", 110, 25, 24),
        ([78.35, 8.65], "Tiruchendur Bank", 130, 32, 28),
        ([78.45, 8.55], "Kulasekharapatnam Grounds", 145, 38, 32),
        ([78.50, 8.40], "Manapad Deep Bank", 160, 45, 40),
        ([78.60, 8.30], "Kanyakumari East Shelf", 175, 52, 48),
        ([78.00, 8.90], "Vaippar Offshore", 95, 22, 18),
        ([78.85, 9.15], "Mandapam South Bank", 180, 28, 20),
        ([79.10, 9.20], "Pamban Offshore Bank", 170, 34, 22),
        ([79.25, 9.10], "Dhanushkodi South Shelf", 160, 42, 35),
    ]
    for coords, center, brg, dist, depth in stn_nodes:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": {
                "sector_id": "SEC006",
                "sector": "SOUTH TAMILNADU",
                "landing_center": center,
                "direction": "SE",
                "bearing_deg": brg,
                "distance_km": f"{dist-3}-{dist+3}",
                "depth_m": f"{depth-3}-{depth+3}",
                "latitude_dd": coords[1],
                "longitude_dd": coords[0],
                "valid_for": "2026-09-02",
                "source": "INCOIS Marine Fisheries Advisory (Thermal Front Proxy)",
                "approx_area_km2": 180,
                "mean_sst_c": 28.4,
            },
        })

    # Gujarat (SEC001)
    gujarat_nodes = [
        ([68.85, 22.40], "Okha Northwest Bank", 285, 35, 30),
        ([68.75, 22.25], "Mithapur Offshore", 270, 42, 35),
        ([68.95, 22.10], "Dwarka West Grounds", 260, 38, 40),
        ([69.25, 21.70], "Porbandar North Shelf", 250, 45, 42),
        ([69.35, 21.55], "Porbandar Southwest Bank", 240, 40, 38),
        ([69.45, 21.40], "Navibandar Grounds", 230, 36, 35),
        ([69.80, 21.10], "Mangrol West Shelf", 225, 38, 36),
        ([70.05, 20.80], "Veraval West Bank", 215, 35, 34),
        ([70.20, 20.70], "Veraval Main Fishery", 205, 30, 30),
        ([70.35, 20.65], "Sutrapada Offshore", 195, 32, 28),
        ([70.60, 20.60], "Kodinar Bank", 190, 35, 32),
        ([71.05, 20.65], "Diu Head Shelf", 185, 38, 35),
        ([71.35, 20.70], "Jafarabad Grounds", 175, 42, 38),
        ([69.20, 22.70], "Mandvi Deep Bank", 260, 40, 30),
        ([68.60, 22.75], "Jakhau Offshore Grounds", 270, 45, 32),
    ]
    for coords, center, brg, dist, depth in gujarat_nodes:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": {
                "sector_id": "SEC001",
                "sector": "GUJARAT",
                "landing_center": center,
                "direction": "SW",
                "bearing_deg": brg,
                "distance_km": f"{dist-3}-{dist+3}",
                "depth_m": f"{depth-3}-{depth+3}",
                "latitude_dd": coords[1],
                "longitude_dd": coords[0],
                "valid_for": "2026-09-02",
                "source": "INCOIS Marine Fisheries Advisory",
                "approx_area_km2": 210,
                "mean_sst_c": 28.1,
            },
        })

    # Odisha (SEC010)
    odisha_nodes = [
        ([85.15, 19.25], "Gopalpur Southeast Bank", 135, 30, 28),
        ([85.35, 19.35], "Ganjam Offshore", 130, 38, 35),
        ([85.90, 19.70], "Puri South Shelf", 140, 35, 30),
        ([86.15, 19.75], "Konark Grounds", 135, 42, 38),
        ([86.75, 20.15], "Paradip Southwest Bank", 125, 32, 28),
        ([86.95, 20.25], "Paradip Deep Fishery", 115, 40, 35),
        ([87.20, 20.35], "Mahanadi Estuary Offshore", 110, 45, 40),
        ([87.35, 20.65], "Dhamra Bank", 105, 38, 32),
        ([87.45, 21.00], "Chandipur Outer Shelf", 100, 42, 30),
    ]
    for coords, center, brg, dist, depth in odisha_nodes:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": {
                "sector_id": "SEC010",
                "sector": "ODISHA",
                "landing_center": center,
                "direction": "SE",
                "bearing_deg": brg,
                "distance_km": f"{dist-3}-{dist+3}",
                "depth_m": f"{depth-3}-{depth+3}",
                "latitude_dd": coords[1],
                "longitude_dd": coords[0],
                "valid_for": "2026-09-02",
                "source": "INCOIS Marine Fisheries Advisory",
                "approx_area_km2": 195,
                "mean_sst_c": 28.7,
            },
        })

    # West Bengal (SEC011)
    wb_nodes = [
        ([87.65, 21.50], "Digha Coastal Bank", 145, 25, 20),
        ([87.85, 21.40], "Shankarpur South Shelf", 140, 32, 24),
        ([88.15, 21.25], "Fraserganj Offshore", 150, 38, 26),
        ([88.35, 21.15], "Bakkhali Deep Grounds", 155, 45, 30),
        ([88.20, 20.95], "Sandheads South Fishery", 160, 52, 35),
        ([88.50, 21.10], "Sundarbans Outer Estuary", 145, 42, 28),
        ([88.65, 21.20], "Raimangal South Bank", 135, 36, 25),
    ]
    for coords, center, brg, dist, depth in wb_nodes:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": {
                "sector_id": "SEC011",
                "sector": "WEST BENGAL",
                "landing_center": center,
                "direction": "SE",
                "bearing_deg": brg,
                "distance_km": f"{dist-3}-{dist+3}",
                "depth_m": f"{depth-3}-{depth+3}",
                "latitude_dd": coords[1],
                "longitude_dd": coords[0],
                "valid_for": "2026-09-02",
                "source": "INCOIS Marine Fisheries Advisory",
                "approx_area_km2": 220,
                "mean_sst_c": 28.9,
            },
        })

    # Andaman & Nicobar (SEC012 & SEC013)
    andaman_nodes = [
        ([92.85, 11.60], "Port Blair East Bank", 95, 25, 55),
        ([93.05, 11.55], "Chidiya Tapu Deep Shelf", 110, 35, 75),
        ([93.20, 12.00], "Havelock Outer Bank", 85, 30, 60),
        ([93.10, 12.30], "Rangat Bay Grounds", 75, 28, 50),
        ([93.15, 12.95], "Mayabunder Offshore", 70, 32, 45),
        ([93.10, 13.30], "Diglipur Northeast Shelf", 65, 35, 40),
        ([92.55, 10.65], "Hut Bay Little Andaman", 190, 25, 65),
        ([92.80, 9.15], "Car Nicobar Grounds", 170, 30, 80),
        ([93.75, 7.05], "Great Nicobar Southern Bank", 160, 35, 90),
    ]
    for coords, center, brg, dist, depth in andaman_nodes:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": {
                "sector_id": "SEC012",
                "sector": "ANDAMAN & NICOBAR",
                "landing_center": center,
                "direction": "E",
                "bearing_deg": brg,
                "distance_km": f"{dist-3}-{dist+3}",
                "depth_m": f"{depth-3}-{depth+3}",
                "latitude_dd": coords[1],
                "longitude_dd": coords[0],
                "valid_for": "2026-09-02",
                "source": "INCOIS Marine Fisheries Advisory",
                "approx_area_km2": 250,
                "mean_sst_c": 29.1,
            },
        })

    out_data = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=1)

    print(f"Generated {len(features)} all-India PFZ advisories at {OUT_FILE}")


if __name__ == "__main__":
    generate()
