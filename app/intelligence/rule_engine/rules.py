from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.thresholds import BatteryThresholds
from app.intelligence.cost_calculator import CostComparison
from app.intelligence.rule_engine.models import RuleEvaluation


class RuleSet:
    """
    Collection of deterministic rules used by the Rule Engine.

    Rules evaluate whether an energy source is safe, feasible,
    and operationally appropriate.

    This class does NOT select the final energy source.
    Final source selection belongs to RuleEngine.
    """

    # ==========================================================
    # SOLAR
    # ==========================================================

    @staticmethod
    def evaluate_solar(
        context: DecisionContext,
        state: CategoricalState,
        costs: CostComparison,
    ) -> RuleEvaluation:

        if not state.solar_available:
            return RuleEvaluation(
                rule_name="SOLAR_AVAILABILITY",
                passed=False,
                reason="Solar is not currently available.",
            )

        if context.solar_kw <= 0:
            return RuleEvaluation(
                rule_name="SOLAR_GENERATION",
                passed=False,
                reason="Solar generation is zero.",
            )

        if context.solar_kw < context.total_load_kw:
            return RuleEvaluation(
                rule_name="SOLAR_PARTIAL",
                passed=True,
                reason=(
                    "Solar is producing power but cannot fully "
                    "cover the site load."
                ),
            )

        return RuleEvaluation(
            rule_name="SOLAR_FULL_COVERAGE",
            passed=True,
            reason="Solar can fully cover the current site load.",
        )

    # ==========================================================
    # BATTERY FEASIBILITY
    # ==========================================================

    @staticmethod
    def evaluate_battery(
        context: DecisionContext,
        state: CategoricalState,
        costs: CostComparison,
    ) -> RuleEvaluation:

        if not state.battery_available:
            return RuleEvaluation(
                rule_name="BATTERY_AVAILABILITY",
                passed=False,
                reason="Battery is unavailable.",
            )

        if not context.battery_safe_to_discharge:
            return RuleEvaluation(
                rule_name="BATTERY_SAFETY",
                passed=False,
                reason="Battery is not safe to discharge.",
            )

        if (
            context.battery_soc_percent
            <= BatteryThresholds.CRITICAL_SOC
        ):
            return RuleEvaluation(
                rule_name="BATTERY_CRITICAL_RESERVE",
                passed=False,
                reason=(
                    f"Battery SOC is critically low at "
                    f"{context.battery_soc_percent:.1f}%."
                ),
            )

        if (
            context.battery_soc_percent
            <= BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC
        ):
            return RuleEvaluation(
                rule_name="BATTERY_LOW_RESERVE",
                passed=False,
                reason=(
                    f"Battery SOC is only "
                    f"{context.battery_soc_percent:.1f}%; "
                    "battery discharge is restricted."
                ),
            )

        if context.battery_soh_percent < BatteryThresholds.HEALTH_WARNING:
            return RuleEvaluation(
                rule_name="BATTERY_HEALTH",
                passed=False,
                reason=(
                    f"Battery health is too low at "
                    f"{context.battery_soh_percent:.1f}%."
                ),
            )

        if context.battery_capacity_kwh <= 0:
            return RuleEvaluation(
                rule_name="BATTERY_CAPACITY",
                passed=False,
                reason="Battery capacity is invalid.",
            )

        if context.battery_max_discharge_kw <= 0:
            return RuleEvaluation(
                rule_name="BATTERY_DISCHARGE_CAPACITY",
                passed=False,
                reason="Battery discharge capacity is unavailable.",
            )

        return RuleEvaluation(
            rule_name="BATTERY_DISCHARGE",
            passed=True,
            reason=(
                f"Battery can safely discharge at "
                f"{context.battery_soc_percent:.1f}% SOC."
            ),
        )

    # ==========================================================
    # BATTERY RESERVE
    # ==========================================================

    @staticmethod
    def evaluate_battery_reserve(
        context: DecisionContext,
    ) -> RuleEvaluation:

        # If grid has failed, battery reserve may be required
        # to maintain site continuity.
        if not context.grid_available:

            return RuleEvaluation(
                rule_name="BATTERY_GRID_FAILURE_SUPPORT",
                passed=True,
                reason=(
                    "Grid is unavailable; battery reserve may be "
                    "used to maintain site continuity."
                ),
            )

        if (
            context.battery_soc_percent
            <= BatteryThresholds.RESERVE_SOC
        ):

            return RuleEvaluation(
                rule_name="BATTERY_RESERVE_PROTECTION",
                passed=False,
                reason=(
                    f"Battery SOC is "
                    f"{context.battery_soc_percent:.1f}%, "
                    f"near or below the protected reserve of "
                    f"{BatteryThresholds.RESERVE_SOC:.1f}%."
                ),
            )

        return RuleEvaluation(
            rule_name="BATTERY_RESERVE_AVAILABLE",
            passed=True,
            reason=(
                f"Battery has sufficient reserve above "
                f"{BatteryThresholds.RESERVE_SOC:.1f}%."
            ),
        )

    # ==========================================================
    # GRID
    # ==========================================================

    @staticmethod
    def evaluate_grid(
        context: DecisionContext,
        state: CategoricalState,
        costs: CostComparison,
    ) -> RuleEvaluation:

        if not context.grid_available:
            return RuleEvaluation(
                rule_name="GRID_AVAILABILITY",
                passed=False,
                reason="Grid is unavailable.",
            )

        if not state.grid_stable:
            return RuleEvaluation(
                rule_name="GRID_STABILITY",
                passed=False,
                reason="Grid frequency is outside the safe range.",
            )

        if context.grid_capacity_kw < context.total_load_kw:
            return RuleEvaluation(
                rule_name="GRID_CAPACITY",
                passed=False,
                reason=(
                    "Grid capacity is insufficient for the current load."
                ),
            )

        return RuleEvaluation(
            rule_name="GRID_NORMAL",
            passed=True,
            reason=(
                "Grid is available, stable, and capable "
                "of supplying the current load."
            ),
        )

    # ==========================================================
    # GENERATOR
    # ==========================================================

    @staticmethod
    def evaluate_generator(
        context: DecisionContext,
        state: CategoricalState,
        costs: CostComparison,
    ) -> RuleEvaluation:

        if not context.generator_available:
            return RuleEvaluation(
                rule_name="GENERATOR_AVAILABILITY",
                passed=False,
                reason="Generator is unavailable.",
            )

        if context.generator_fuel_level_percent <= (
            10.0
        ):
            return RuleEvaluation(
                rule_name="GENERATOR_CRITICAL_FUEL",
                passed=False,
                reason=(
                    f"Generator fuel is critically low at "
                    f"{context.generator_fuel_level_percent:.1f}%."
                ),
            )

        if context.generator_capacity_kw < context.total_load_kw:
            return RuleEvaluation(
                rule_name="GENERATOR_CAPACITY",
                passed=False,
                reason=(
                    "Generator capacity is insufficient "
                    "for the current load."
                ),
            )

        if not costs.generator.available:
            return RuleEvaluation(
                rule_name="GENERATOR_COST_DATA",
                passed=False,
                reason=(
                    "Generator fuel consumption or fuel cost "
                    "data is unavailable; generator is excluded "
                    "from economic optimization."
                ),
            )

        return RuleEvaluation(
            rule_name="GENERATOR_READY",
            passed=True,
            reason=(
                "Generator is available, fueled, and "
                "economically evaluable."
            ),
        )