from app.decision.engine import DecisionEngine
from app.statebuilder.decision_context import DecisionContext


def make_context(**overrides):
    context = {
        "site_id": "TEST-SITE-001",
        "country": "Pakistan",
        "hour_of_day": 14,
        "tariff_period": "peak",

        "total_load_kw": 10.0,

        "solar_available": True,
        "solar_capacity_kw": 10.0,
        "solar_kw": 2.0,

        "battery_available": True,
        "battery_capacity_kwh": 20.0,
        "battery_soc_percent": 80.0,
        "battery_soh_percent": 95.0,
        "battery_safe_to_discharge": True,
        "battery_max_charge_kw": 10.0,
        "battery_max_discharge_kw": 10.0,
        "battery_wear_cost_per_kwh": 5.0,

        "grid_available": True,
        "grid_capacity_kw": 10.0,
        "grid_kw": 10.0,
        "grid_frequency_hz": 50.0,
        "grid_tariff_per_kwh": 20.0,
        "peak_tariff_per_kwh": 20.0,
        "off_peak_tariff_per_kwh": 10.0,

        "generator_available": True,
        "generator_capacity_kw": 10.0,
        "generator_kw": 10.0,
        "generator_fuel_level_percent": 80.0,
        "generator_fuel_low_alert": False,
        "generator_fuel_consumption_liter_hour": 2.0,
        "generator_fuel_cost_per_liter": 300.0,

        "current_active_source": "grid",
    }

    context.update(overrides)

    return DecisionContext(**context)


def test_decision_engine_produces_dispatch_plan():

    result = DecisionEngine().evaluate(
        make_context()
    )

    assert result.dispatch_plan is not None

    dispatch = result.dispatch_plan

    assert dispatch.supplied_load_kw > 0
    assert dispatch.unmet_load_kw >= 0
    assert dispatch.total_cost_per_hour >= 0

    assert dispatch.allocations

    allocated_power = sum(
        power_kw
        for _, power_kw, _ in dispatch.allocations
    )

    assert allocated_power == dispatch.supplied_load_kw


def test_dispatch_does_not_exceed_source_capacity():

    result = DecisionEngine().evaluate(
        make_context()
    )

    dispatch = result.dispatch_plan

    assert dispatch is not None

    limits = {
        "solar": 2.0,
        "battery": 10.0,
        "grid": 10.0,
        "generator": 10.0,
    }

    for source, power_kw, _ in dispatch.allocations:
        assert power_kw <= limits[source]


def test_dispatch_uses_authoritative_costs():

    result = DecisionEngine().evaluate(
        make_context(
            solar_kw=0.0,
            battery_wear_cost_per_kwh=5.0,
            grid_tariff_per_kwh=20.0,
            generator_kw=10.0,
            generator_fuel_consumption_liter_hour=2.0,
            generator_fuel_cost_per_liter=300.0,
        )
    )

    dispatch = result.dispatch_plan

    assert dispatch is not None

    assert dispatch.allocations

    # Generator = (2 L/h * 300 PKR/L) / 10 kW
    #            = 60 PKR/kWh
    #
    # Battery = 5 PKR/kWh
    # Grid = 20 PKR/kWh
    #
    # Therefore battery must be dispatched first.
    first_source = dispatch.allocations[0][0]

    assert first_source == "battery"

    first_cost = dispatch.allocations[0][2]

    assert first_cost == 5.0