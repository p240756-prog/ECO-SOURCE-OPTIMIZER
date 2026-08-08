from app.decision.engine import DecisionEngine
from app.statebuilder.decision_context import DecisionContext


def make_generator_only_context() -> DecisionContext:
    return DecisionContext(
        site_id="TEST-GEN-001",
        country="Pakistan",

        hour_of_day=14,
        tariff_period="peak",

        total_load_kw=5.0,

        solar_available=False,
        solar_capacity_kw=10.0,
        solar_kw=0.0,

        battery_available=False,
        battery_capacity_kwh=100.0,
        battery_soc_percent=80.0,
        battery_soh_percent=90.0,
        battery_safe_to_discharge=True,
        battery_max_charge_kw=10.0,
        battery_max_discharge_kw=10.0,
        battery_wear_cost_per_kwh=5.0,

        grid_available=False,
        grid_capacity_kw=10.0,
        grid_kw=0.0,
        grid_frequency_hz=50.0,
        grid_tariff_per_kwh=50.0,
        peak_tariff_per_kwh=60.0,
        off_peak_tariff_per_kwh=30.0,

        generator_available=True,
        generator_capacity_kw=10.0,
        generator_kw=5.0,
        generator_fuel_level_percent=80.0,
        generator_fuel_low_alert=False,
        generator_fuel_consumption_liter_hour=2.0,
        generator_fuel_cost_per_liter=300.0,

        current_active_source="generator",
    )


def test_decision_engine_uses_actual_generator_output_for_cost():
    context = make_generator_only_context()

    decision = DecisionEngine().evaluate(context)

    # 2 L/hour × 300 PKR/L = 600 PKR/hour
    # 600 / actual generator output of 5 kW = 120 PKR/kWh
    expected_cost_per_kwh = 120.0

    assert decision.selected_source == "generator"

    assert (
        decision.costs.generator.cost_per_kwh
        == expected_cost_per_kwh
    )

    assert (
        decision.estimated_cost_per_kwh
        == expected_cost_per_kwh
    )

    assert decision.emergency_mode is False