from types import SimpleNamespace

from app.intelligence.safety_guard import SafetyGuard
from app.statebuilder.thresholds import (
    BatteryThresholds,
    GeneratorThresholds,
)


def make_context(**overrides):
    context = {
        "battery_safe_to_discharge": True,
        "battery_soh_percent": 90.0,
        "battery_soc_percent": 80.0,
        "generator_fuel_level_percent": 80.0,
    }

    context.update(overrides)

    return SimpleNamespace(**context)


def make_state(
    *,
    overall_state="NORMAL",
    grid_stable=True,
):
    return SimpleNamespace(
        overall_state=overall_state,
        grid_stable=grid_stable,
    )


def make_feasibility(
    *,
    solar=True,
    battery=True,
    grid=True,
    generator=True,
):
    return SimpleNamespace(
        solar=solar,
        battery=battery,
        grid=grid,
        generator=generator,
        solar_reason="Solar not feasible.",
        battery_reason="Battery not feasible.",
        grid_reason="Grid not feasible.",
        generator_reason="Generator not feasible.",
    )


def test_all_sources_allowed_when_safe():
    result = SafetyGuard().evaluate(
        make_context(),
        make_state(),
        make_feasibility(),
    )

    assert result.solar_allowed is True
    assert result.battery_allowed is True
    assert result.grid_allowed is True
    assert result.generator_allowed is True
    assert result.emergency_mode is False
    assert result.any_source_allowed is True


def test_solar_blocked_when_not_feasible():
    result = SafetyGuard().evaluate(
        make_context(),
        make_state(),
        make_feasibility(solar=False),
    )

    assert result.solar_allowed is False
    assert result.solar_reason == "Solar not feasible."


def test_solar_blocked_in_critical_system_state():
    result = SafetyGuard().evaluate(
        make_context(),
        make_state(overall_state="CRITICAL"),
        make_feasibility(),
    )

    assert result.solar_allowed is False
    assert "critical state" in result.solar_reason.lower()


def test_battery_blocked_when_discharge_is_unsafe():
    result = SafetyGuard().evaluate(
        make_context(
            battery_safe_to_discharge=False,
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.battery_allowed is False
    assert "unsafe" in result.battery_reason.lower()


def test_battery_blocked_below_health_threshold():
    result = SafetyGuard().evaluate(
        make_context(
            battery_soh_percent=BatteryThresholds.HEALTH_WARNING - 0.1,
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.battery_allowed is False
    assert "health" in result.battery_reason.lower()


def test_battery_allowed_at_health_threshold():
    result = SafetyGuard().evaluate(
        make_context(
            battery_soh_percent=BatteryThresholds.HEALTH_WARNING,
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.battery_allowed is True


def test_battery_blocked_at_critical_soc():
    result = SafetyGuard().evaluate(
        make_context(
            battery_soc_percent=BatteryThresholds.CRITICAL_SOC,
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.battery_allowed is False
    assert "critically low" in result.battery_reason.lower()


def test_battery_below_reserve_remains_allowed():
    result = SafetyGuard().evaluate(
        make_context(
            battery_soc_percent=(
                BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC - 0.1
            ),
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.battery_allowed is True
    assert result.emergency_mode is False
    assert "below the normal optimization reserve" in result.battery_reason


def test_battery_at_reserve_has_normal_reason():
    result = SafetyGuard().evaluate(
        make_context(
            battery_soc_percent=BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC,
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.battery_allowed is True
    assert (
        result.battery_reason
        == "Battery passes SOC, health, and discharge safety checks."
    )


def test_grid_blocked_when_not_feasible():
    result = SafetyGuard().evaluate(
        make_context(),
        make_state(),
        make_feasibility(grid=False),
    )

    assert result.grid_allowed is False
    assert result.grid_reason == "Grid not feasible."


def test_grid_blocked_when_unstable():
    result = SafetyGuard().evaluate(
        make_context(),
        make_state(grid_stable=False),
        make_feasibility(),
    )

    assert result.grid_allowed is False
    assert "frequency" in result.grid_reason.lower()


def test_generator_blocked_at_critical_fuel():
    result = SafetyGuard().evaluate(
        make_context(
            generator_fuel_level_percent=(
                GeneratorThresholds.CRITICAL_FUEL_PERCENT
            ),
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.generator_allowed is False
    assert "critically low" in result.generator_reason.lower()


def test_generator_allowed_above_critical_fuel():
    result = SafetyGuard().evaluate(
        make_context(
            generator_fuel_level_percent=(
                GeneratorThresholds.CRITICAL_FUEL_PERCENT + 0.1
            ),
        ),
        make_state(),
        make_feasibility(),
    )

    assert result.generator_allowed is True


def test_emergency_mode_when_no_source_is_allowed():
    result = SafetyGuard().evaluate(
        make_context(
            battery_safe_to_discharge=False,
            battery_soh_percent=50.0,
            battery_soc_percent=10.0,
            generator_fuel_level_percent=5.0,
        ),
        make_state(
            overall_state="CRITICAL",
            grid_stable=False,
        ),
        make_feasibility(
            solar=False,
            battery=False,
            grid=False,
            generator=False,
        ),
    )

    assert result.solar_allowed is False
    assert result.battery_allowed is False
    assert result.grid_allowed is False
    assert result.generator_allowed is False

    assert result.any_source_allowed is False
    assert result.emergency_mode is True