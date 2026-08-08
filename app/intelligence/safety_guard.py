from dataclasses import dataclass

from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.thresholds import (
    BatteryThresholds,
    GeneratorThresholds,
)

from app.intelligence.source_feasibility import SourceFeasibility


@dataclass
class SafetyDecision:
    """
    Final safety authorization for each source.

    Safety always has priority over economics.
    """

    solar_allowed: bool
    battery_allowed: bool
    grid_allowed: bool
    generator_allowed: bool

    solar_reason: str
    battery_reason: str
    grid_reason: str
    generator_reason: str

    emergency_mode: bool = False

    @property
    def any_source_allowed(self) -> bool:
        return (
            self.solar_allowed
            or self.battery_allowed
            or self.grid_allowed
            or self.generator_allowed
        )


class SafetyGuard:
    """
    Applies safety and reliability constraints.

    This class does not optimize cost.
    """

    def evaluate(
        self,
        context: DecisionContext,
        state: CategoricalState,
        feasibility: SourceFeasibility,
    ) -> SafetyDecision:

        # ==========================================================
        # SOLAR
        # ==========================================================

        if not feasibility.solar:
            solar_allowed = False
            solar_reason = feasibility.solar_reason

        elif state.overall_state == "CRITICAL":
            solar_allowed = False
            solar_reason = (
                "System is in a critical state and solar cannot "
                "be independently relied upon."
            )

        else:
            solar_allowed = True
            solar_reason = (
                "Solar is technically feasible and passes safety validation."
            )

        # ==========================================================
        # BATTERY
        # ==========================================================

        if not feasibility.battery:
            battery_allowed = False
            battery_reason = feasibility.battery_reason

        elif not context.battery_safe_to_discharge:
            battery_allowed = False
            battery_reason = (
                "Battery telemetry explicitly marks discharge unsafe."
            )

        elif context.battery_soh_percent < BatteryThresholds.HEALTH_WARNING:
            battery_allowed = False
            battery_reason = (
                f"Battery health ({context.battery_soh_percent:.1f}%) "
                f"is below the safe threshold "
                f"({BatteryThresholds.HEALTH_WARNING:.1f}%)."
            )

        elif context.battery_soc_percent <= BatteryThresholds.CRITICAL_SOC:
            battery_allowed = False
            battery_reason = (
                f"Battery SOC ({context.battery_soc_percent:.1f}%) "
                "is critically low."
            )

        else:
            battery_allowed = True

            if (
                context.battery_soc_percent
                < BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC
            ):
                battery_reason = (
                    f"Battery is technically safe at "
                    f"{context.battery_soc_percent:.1f}% SOC, "
                    "but it is below the normal optimization reserve. "
                    "Economic optimization must not intentionally prefer it."
                )
            else:
                battery_reason = (
                    "Battery passes SOC, health, and discharge safety checks."
                )

        # ==========================================================
        # GRID
        # ==========================================================

        if not feasibility.grid:
            grid_allowed = False
            grid_reason = feasibility.grid_reason

        elif not state.grid_stable:
            grid_allowed = False
            grid_reason = (
                "Grid frequency is outside the configured safe range."
            )

        else:
            grid_allowed = True
            grid_reason = (
                "Grid passes availability, stability, and capacity checks."
            )

        # ==========================================================
        # GENERATOR
        # ==========================================================

        if not feasibility.generator:
            generator_allowed = False
            generator_reason = feasibility.generator_reason

        elif (
            context.generator_fuel_level_percent
            <= GeneratorThresholds.CRITICAL_FUEL_PERCENT
        ):
            generator_allowed = False
            generator_reason = (
                f"Generator fuel ({context.generator_fuel_level_percent:.1f}%) "
                "is critically low."
            )

        else:
            generator_allowed = True
            generator_reason = (
                "Generator passes availability and fuel safety checks."
            )

        # ==========================================================
        # EMERGENCY
        # ==========================================================

        emergency_mode = not (
            solar_allowed
            or battery_allowed
            or grid_allowed
            or generator_allowed
        )

        return SafetyDecision(
            solar_allowed=solar_allowed,
            battery_allowed=battery_allowed,
            grid_allowed=grid_allowed,
            generator_allowed=generator_allowed,
            solar_reason=solar_reason,
            battery_reason=battery_reason,
            grid_reason=grid_reason,
            generator_reason=generator_reason,
            emergency_mode=emergency_mode,
        )