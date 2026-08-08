from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.thresholds import (
    BatteryThresholds,
    GeneratorThresholds,
    SolarThresholds,
)


class StateBuilder:
    """
    Converts DecisionContext into meaningful operational states.

    This layer interprets telemetry.

    It does NOT:
        - select an energy source
        - calculate cost
        - optimize
        - override safety decisions
    """

    def build(
        self,
        telemetry: DecisionContext,
    ) -> CategoricalState:

        # ==========================================================
        # BATTERY
        # ==========================================================

        if not telemetry.battery_available:
            battery_state = "UNAVAILABLE"

        elif telemetry.battery_soc_percent <= BatteryThresholds.CRITICAL_SOC:
            battery_state = "CRITICAL"

        elif telemetry.battery_soc_percent <= BatteryThresholds.LOW_SOC:
            battery_state = "LOW"

        elif telemetry.battery_soc_percent >= BatteryThresholds.HIGH_SOC:
            battery_state = "HIGH"

        else:
            battery_state = "NORMAL"

        # ==========================================================
        # SOLAR
        # ==========================================================

        if not telemetry.solar_available:
            solar_state = "LOW"

        elif telemetry.solar_kw <= 0:
            solar_state = "LOW"

        elif telemetry.total_load_kw <= 0:
            solar_state = "FULL"

        else:
            solar_ratio = (
                telemetry.solar_kw / telemetry.total_load_kw
            )

            if solar_ratio >= SolarThresholds.FULL_LOAD_COVERAGE:
                solar_state = "FULL"

            elif solar_ratio >= SolarThresholds.PARTIAL_LOAD_COVERAGE:
                solar_state = "PARTIAL"

            else:
                solar_state = "LOW"

        # ==========================================================
        # GRID
        # ==========================================================

        if not telemetry.grid_available:
            grid_state = "FAILED"

        elif (
            telemetry.grid_frequency_hz <= 0
            or telemetry.grid_frequency_hz < 49.0
            or telemetry.grid_frequency_hz > 51.0
        ):
            grid_state = "UNSTABLE"

        else:
            grid_state = "STABLE"

        # ==========================================================
        # GENERATOR
        # ==========================================================

        if not telemetry.generator_available:
            generator_state = "UNAVAILABLE"

        elif telemetry.generator_fuel_level_percent <= 0:
            generator_state = "CRITICAL_FUEL"

        elif (
            telemetry.generator_fuel_level_percent
            <= GeneratorThresholds.CRITICAL_FUEL_PERCENT
        ):
            generator_state = "CRITICAL_FUEL"

        elif (
            telemetry.generator_fuel_level_percent
            <= GeneratorThresholds.LOW_FUEL_PERCENT
        ):
            generator_state = "LOW_FUEL"

        else:
            generator_state = "AVAILABLE"

        # ==========================================================
        # OVERALL STATE
        # ==========================================================

        if battery_state == "CRITICAL":
            overall_state = "BATTERY_RISK"

        elif (
            grid_state == "FAILED"
            and generator_state in {
                "UNAVAILABLE",
                "CRITICAL_FUEL",
            }
            and battery_state in {
                "CRITICAL",
                "LOW",
                "UNAVAILABLE",
            }
        ):
            overall_state = "POWER_RISK"

        elif (
            battery_state == "LOW"
            or generator_state == "LOW_FUEL"
            or grid_state == "UNSTABLE"
        ):
            overall_state = "WARNING"

        else:
            overall_state = "NORMAL"

        return CategoricalState(
            battery_state=battery_state,
            solar_state=solar_state,
            grid_state=grid_state,
            generator_state=generator_state,
            overall_state=overall_state,
        )