"""Unit tests for fishing zone profit engine and voyage fuel consumption integration."""
from orca.fishing_profit import (
    BASE_FUEL_BURN_LPH,
    DIESEL_PRICE_INR_PER_LITRE,
    KM_PER_NM,
    PORTS,
    ZONES,
    calculate_fuel_burn_rate,
    calculate_fuel_consumption,
    calculate_profit,
    get_zone_profits,
)


def test_base_fuel_burn_rates_match_voyage():
    """Ensure base rates align identically with voyage planner."""
    assert BASE_FUEL_BURN_LPH["small_fishing"] == 4.5
    assert BASE_FUEL_BURN_LPH["mechanized_trawler"] == 22.0
    assert BASE_FUEL_BURN_LPH["cargo_vessel"] == 110.0


def test_calculate_fuel_burn_rate_quadratic_scaling():
    """Fuel burn scales quadratically relative to 8 knots cruise."""
    # At 8 knots, matches base rate
    assert calculate_fuel_burn_rate("small_fishing", 8.0) == 4.5
    assert calculate_fuel_burn_rate("mechanized_trawler", 8.0) == 22.0
    assert calculate_fuel_burn_rate("cargo_vessel", 8.0) == 110.0

    # At 10 knots: 4.5 * (10 / 8)^2 = 7.03
    assert calculate_fuel_burn_rate("small_fishing", 10.0) == 7.03

    # At 6 knots: 22.0 * (6 / 8)^2 = 12.38
    assert calculate_fuel_burn_rate("mechanized_trawler", 6.0) == 12.38


def test_calculate_fuel_consumption_round_trip():
    """Test fuel liters calculation for round trip distance in nautical miles."""
    distance_km = 60.0
    # 60 km one way -> 120 km round trip = 120 / 1.852 = 64.79 NM
    # At 8 knots -> 8.099 hours
    # At 4.5 L/h -> 36.45 L -> rounds to 36.4 or 36.5 L
    fuel_liters, burn_lph, round_trip_nm = calculate_fuel_consumption(
        distance_km=distance_km,
        vessel_key="small_fishing",
        speed_kn=8.0,
        fuel_burn_lph=None,
        round_trip=True,
    )
    assert round_trip_nm == round(120.0 / KM_PER_NM, 1)
    assert burn_lph == 4.5
    assert 36.0 <= fuel_liters <= 37.0


def test_calculate_profit_includes_voyage_fuel_metrics():
    """Verify calculate_profit returns fuel_liters, fuel_burn_lph, and fuel_cost."""
    port = PORTS[0]  # Kochi
    zone = ZONES[0]  # Kerala zone
    res = calculate_profit(port, zone, "small_fishing", speed_kn=8.0)

    assert "fuel_cost" in res
    assert "fuel_liters" in res
    assert "fuel_burn_lph" in res
    assert "round_trip_nm" in res
    assert res["fuel_burn_lph"] == 4.5
    assert res["fuel_cost"] == round(res["fuel_liters"] * DIESEL_PRICE_INR_PER_LITRE)
    assert res["total_cost"] == res["fuel_cost"] + res["fixed_cost"]


def test_get_zone_profits_api_contract():
    """Verify get_zone_profits returns zones with voyage fuel data."""
    res = get_zone_profits(
        port_lat=9.96,
        port_lon=76.26,
        vessel_key="small_fishing",
        speed_kn=9.0,
    )
    assert res["port_id"] == "kochi"
    assert res["speed_kn"] == 9.0
    assert len(res["zones"]) > 0
    first_zone = res["zones"][0]
    assert "fuel_liters" in first_zone
    assert "fuel_burn_lph" in first_zone
    assert first_zone["fuel_cost"] > 0
