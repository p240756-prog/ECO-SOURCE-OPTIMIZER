from types import SimpleNamespace

from app.intelligence.rule_engine.rules import RuleSet
from app.statebuilder.thresholds import BatteryThresholds


def make_state(
    *,
    solar_available=True,
    battery_available=True,
    grid_stable=True,
):
    return SimpleNamespace(
        solar_available=solar_available,
        battery_available=battery_available,
        grid_stable=grid_stable,
    )


def make_costs(*, generator_available=True):
    return SimpleNamespace(
        generator=SimpleNamespace(
            available=generator_available,
        )
    )


def make_context(**overrides):
    context = {
        "solar_kw": 5.0,
        "total_load_kw": 5.0,

        "battery_safe_to_discharge": True,
        "battery_soc_percent": 80.0,
        "battery_soh_percent": 90.0,
        "battery_capacity_kwh": 100.0,
        "battery_max_discharge_kw": 20.0,

        "grid_available": True,
        "grid_capacity_kw": 10.0,

        "generator_available": True,
        "generator_fuel_level_percent": 80.0,
        "generator_capacity_kw": 10.0,
    }

    context.update(overrides)

    return SimpleNamespace(**context)


def test_solar_exactly_covers_load():
    context = make_context(
        solar_kw=5.0,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_solar(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is True
    assert result.rule_name == "SOLAR_FULL_COVERAGE"


def test_solar_below_load_is_partial():
    context = make_context(
        solar_kw=4.99,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_solar(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is True
    assert result.rule_name == "SOLAR_PARTIAL"


def test_solar_zero_generation_fails():
    context = make_context(
        solar_kw=0.0,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_solar(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "SOLAR_GENERATION"


def test_battery_at_critical_soc_fails():
    context = make_context(
        battery_soc_percent=BatteryThresholds.CRITICAL_SOC,
    )

    result = RuleSet.evaluate_battery(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "BATTERY_CRITICAL_RESERVE"


def test_battery_just_above_critical_soc_is_not_critical():
    context = make_context(
        battery_soc_percent=BatteryThresholds.CRITICAL_SOC + 0.1,
    )

    result = RuleSet.evaluate_battery(
        context,
        make_state(),
        make_costs(),
    )

    assert result.rule_name != "BATTERY_CRITICAL_RESERVE"


def test_battery_at_minimum_discharge_soc_fails():
    context = make_context(
        battery_soc_percent=BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC,
    )

    result = RuleSet.evaluate_battery(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "BATTERY_LOW_RESERVE"


def test_battery_at_health_warning_threshold_is_allowed():
    context = make_context(
        battery_soh_percent=BatteryThresholds.HEALTH_WARNING,
    )

    result = RuleSet.evaluate_battery(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is True


def test_battery_below_health_warning_threshold_fails():
    context = make_context(
        battery_soh_percent=BatteryThresholds.HEALTH_WARNING - 0.1,
    )

    result = RuleSet.evaluate_battery(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "BATTERY_HEALTH"


def test_grid_exactly_at_load_capacity_is_allowed():
    context = make_context(
        grid_capacity_kw=5.0,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_grid(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is True
    assert result.rule_name == "GRID_NORMAL"


def test_grid_below_load_capacity_fails():
    context = make_context(
        grid_capacity_kw=4.99,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_grid(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "GRID_CAPACITY"


def test_generator_at_critical_fuel_fails():
    context = make_context(
        generator_fuel_level_percent=10.0,
    )

    result = RuleSet.evaluate_generator(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "GENERATOR_CRITICAL_FUEL"


def test_generator_above_critical_fuel_can_pass():
    context = make_context(
        generator_fuel_level_percent=10.1,
    )

    result = RuleSet.evaluate_generator(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is True
    assert result.rule_name == "GENERATOR_READY"


def test_generator_exactly_at_load_capacity_is_allowed():
    context = make_context(
        generator_capacity_kw=5.0,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_generator(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is True


def test_generator_below_load_capacity_fails():
    context = make_context(
        generator_capacity_kw=4.99,
        total_load_kw=5.0,
    )

    result = RuleSet.evaluate_generator(
        context,
        make_state(),
        make_costs(),
    )

    assert result.passed is False
    assert result.rule_name == "GENERATOR_CAPACITY"