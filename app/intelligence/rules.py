from dataclasses import dataclass

from app.intelligence.cost_calculator import CostComparison
from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.thresholds import (
    BatteryThresholds,
)


# ==============================================================
# DATA STRUCTURES
# ==============================================================


@dataclass
class RuleEvaluation:
    rule_name: str
    passed: bool
    reason: str


@dataclass
class EngineDecision:
    selected_source: str
    reason: str
    estimated_cost_per_kwh: float | None
    emergency_mode: bool
    evaluations: list[RuleEvaluation]


# ==============================================================
# RULE ENGINE
# ==============================================================


class RuleEngine:
    """
    Deterministic industrial energy-source decision engine.

    Decision hierarchy:

        1. Emergency protection
        2. Safety
        3. Feasibility
        4. Battery reserve protection
        5. Economic validity
        6. Cost optimization
        7. Deterministic fallback

    This class makes the final source-selection decision.
    """

    def decide(
        self,
        context: DecisionContext,
        state: CategoricalState,
        costs: CostComparison,
    ) -> EngineDecision:

        evaluations: list[RuleEvaluation] = []

        # ==========================================================
        # TIER 0 — EMERGENCY
        # ==========================================================

        emergency = self._check_emergency(
            context=context,
            state=state,
            evaluations=evaluations,
        )

        if emergency:

            return self._emergency_decision(
                context=context,
                evaluations=evaluations,
            )

        # ==========================================================
        # TIER 1 — SOLAR
        # ==========================================================

        if self._solar_valid(
            context,
            state,
            costs,
            evaluations,
        ):

            return EngineDecision(
                selected_source="solar",
                reason=(
                    "Solar is producing usable energy and can "
                    "safely satisfy part or all of the current load. "
                    "Solar has zero direct fuel cost and is therefore "
                    "preferred before higher-cost sources."
                ),
                estimated_cost_per_kwh=0.0,
                emergency_mode=False,
                evaluations=evaluations,
            )

        # ==========================================================
        # TIER 2 — BATTERY RESERVE
        # ==========================================================

        battery_allowed = self._battery_valid(
            context,
            state,
            costs,
            evaluations,
        )

        # ==========================================================
        # TIER 3 — GRID
        # ==========================================================

        grid_allowed = self._grid_valid(
            context,
            state,
            evaluations,
        )

        # ==========================================================
        # TIER 4 — GENERATOR
        # ==========================================================

        generator_allowed = self._generator_valid(
            context,
            state,
            costs,
            evaluations,
        )

        # ==========================================================
        # TIER 5 — ECONOMIC SELECTION
        # ==========================================================

        candidates = []

        if battery_allowed and costs.battery.economically_valid:
            candidates.append(
                (
                    "battery",
                    costs.battery.cost_per_kwh,
                )
            )

        if grid_allowed and costs.grid.economically_valid:
            candidates.append(
                (
                    "grid",
                    costs.grid.cost_per_kwh,
                )
            )

        if generator_allowed and costs.generator.economically_valid:
            candidates.append(
                (
                    "generator",
                    costs.generator.cost_per_kwh,
                )
            )

        # ==========================================================
        # NO ECONOMIC CANDIDATE
        # ==========================================================

        if not candidates:

            return self._fallback_decision(
                context=context,
                evaluations=evaluations,
            )

        # ==========================================================
        # SELECT CHEAPEST VALID SOURCE
        # ==========================================================

        selected_source, selected_cost = min(
            candidates,
            key=lambda item: item[1],
        )

        evaluations.append(
            RuleEvaluation(
                rule_name="ECONOMIC_OPTIMIZATION",
                passed=True,
                reason=(
                    f"{selected_source.capitalize()} has the lowest "
                    f"known valid operating cost among safe and "
                    f"feasible sources."
                ),
            )
        )

        return EngineDecision(
            selected_source=selected_source,
            reason=(
                f"{selected_source.capitalize()} has the lowest "
                f"valid operating cost among safe and feasible "
                f"energy sources."
            ),
            estimated_cost_per_kwh=selected_cost,
            emergency_mode=False,
            evaluations=evaluations,
        )

    # ==============================================================
    # EMERGENCY CHECK
    # ==============================================================

    def _check_emergency(
        self,
        context: DecisionContext,
        state: CategoricalState,
        evaluations: list[RuleEvaluation],
    ) -> bool:

        if state.overall_state == "CRITICAL":

            evaluations.append(
                RuleEvaluation(
                    rule_name="EMERGENCY_STATE",
                    passed=True,
                    reason=(
                        "System is in a critical operational state."
                    ),
                )
            )

            return True

        if (
            not context.grid_available
            and not context.generator_available
            and not context.battery_available
            and not context.solar_available
        ):

            evaluations.append(
                RuleEvaluation(
                    rule_name="TOTAL_SOURCE_FAILURE",
                    passed=True,
                    reason=(
                        "No energy source is currently available. "
                        "Site is at immediate power risk."
                    ),
                )
            )

            return True

        evaluations.append(
            RuleEvaluation(
                rule_name="EMERGENCY_STATE",
                passed=False,
                reason="No emergency condition detected.",
            )
        )

        return False

    # ==============================================================
    # SOLAR RULE
    # ==============================================================

    def _solar_valid(
        self,
        context,
        state,
        costs,
        evaluations,
    ) -> bool:

        if not state.solar_available:
            evaluations.append(
                RuleEvaluation(
                    rule_name="SOLAR_AVAILABILITY",
                    passed=False,
                    reason=(
                        "Solar is not currently available."
                    ),
                )
            )

            return False

        if context.solar_kw <= 0:
            evaluations.append(
                RuleEvaluation(
                    rule_name="SOLAR_OUTPUT",
                    passed=False,
                    reason=(
                        "Solar system is available but currently "
                        "producing no usable power."
                    ),
                )
            )

            return False

        evaluations.append(
            RuleEvaluation(
                rule_name="SOLAR_AVAILABILITY",
                passed=True,
                reason=(
                    f"Solar is producing {context.solar_kw:.3f} kW "
                    f"of usable power."
                ),
            )
        )

        return True

    # ==============================================================
    # BATTERY RULE
    # ==============================================================

    def _battery_valid(
        self,
        context,
        state,
        costs,
        evaluations,
    ) -> bool:

        if not context.battery_available:

            evaluations.append(
                RuleEvaluation(
                    rule_name="BATTERY_AVAILABILITY",
                    passed=False,
                    reason="Battery is unavailable.",
                )
            )

            return False

        if not state.battery_safe:

            evaluations.append(
                RuleEvaluation(
                    rule_name="BATTERY_SAFETY",
                    passed=False,
                    reason=(
                        "Battery state does not permit safe discharge."
                    ),
                )
            )

            return False

        if not context.battery_safe_to_discharge:

            evaluations.append(
                RuleEvaluation(
                    rule_name="BATTERY_DISCHARGE",
                    passed=False,
                    reason=(
                        "Battery telemetry explicitly indicates "
                        "that discharge is unsafe."
                    ),
                )
            )

            return False

        if (
            context.battery_soc_percent
            <= BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC
        ):

            evaluations.append(
                RuleEvaluation(
                    rule_name="BATTERY_RESERVE",
                    passed=False,
                    reason=(
                        f"Battery SOC is {context.battery_soc_percent:.1f}%. "
                        f"Discharge is blocked below the "
                        f"{BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC:.1f}% "
                        "minimum reserve."
                    ),
                )
            )

            return False

        if context.battery_max_discharge_kw < context.total_load_kw:

            evaluations.append(
                RuleEvaluation(
                    rule_name="BATTERY_CAPACITY",
                    passed=False,
                    reason=(
                        f"Battery maximum discharge capacity "
                        f"({context.battery_max_discharge_kw:.3f} kW) "
                        f"is below current load "
                        f"({context.total_load_kw:.3f} kW)."
                    ),
                )
            )

            return False

        evaluations.append(
            RuleEvaluation(
                rule_name="BATTERY_DISCHARGE",
                passed=True,
                reason=(
                    f"Battery can safely provide the required load "
                    f"at {context.battery_soc_percent:.1f}% SOC."
                ),
            )
        )

        if not costs.battery.economically_valid:

            evaluations.append(
                RuleEvaluation(
                    rule_name="BATTERY_COST_DATA",
                    passed=False,
                    reason=(
                        "Battery is physically usable but its "
                        "degradation cost is unknown. It will not "
                        "be treated as free energy."
                    ),
                )
            )

        return True

    # ==============================================================
    # GRID RULE
    # ==============================================================

    def _grid_valid(
        self,
        context,
        state,
        evaluations,
    ) -> bool:

        if not context.grid_available:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GRID_NORMAL",
                    passed=False,
                    reason="Grid is unavailable.",
                )
            )

            return False

        if not state.grid_stable:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GRID_STABILITY",
                    passed=False,
                    reason=(
                        "Grid is available but frequency is outside "
                        "the configured stability range."
                    ),
                )
            )

            return False

        if context.grid_capacity_kw < context.total_load_kw:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GRID_CAPACITY",
                    passed=False,
                    reason=(
                        f"Grid capacity "
                        f"({context.grid_capacity_kw:.3f} kW) "
                        f"is below current load "
                        f"({context.total_load_kw:.3f} kW)."
                    ),
                )
            )

            return False

        evaluations.append(
            RuleEvaluation(
                rule_name="GRID_NORMAL",
                passed=True,
                reason=(
                    "Grid is available, stable, and capable "
                    "of supplying the current load."
                ),
            )
        )

        return True

    # ==============================================================
    # GENERATOR RULE
    # ==============================================================

    def _generator_valid(
        self,
        context,
        state,
        costs,
        evaluations,
    ) -> bool:

        if not context.generator_available:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GENERATOR_AVAILABILITY",
                    passed=False,
                    reason="Generator is unavailable.",
                )
            )

            return False

        if not state.generator_ready:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GENERATOR_FUEL",
                    passed=False,
                    reason=(
                        "Generator fuel state does not permit "
                        "normal operation."
                    ),
                )
            )

            return False

        if context.generator_capacity_kw < context.total_load_kw:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GENERATOR_CAPACITY",
                    passed=False,
                    reason=(
                        f"Generator capacity "
                        f"({context.generator_capacity_kw:.3f} kW) "
                        f"is below current load "
                        f"({context.total_load_kw:.3f} kW)."
                    ),
                )
            )

            return False

        evaluations.append(
            RuleEvaluation(
                rule_name="GENERATOR_OPERATIONAL",
                passed=True,
                reason=(
                    f"Generator can provide the required load "
                    f"with {context.generator_fuel_level_percent:.1f}% fuel."
                ),
            )
        )

        if not costs.generator.economically_valid:

            evaluations.append(
                RuleEvaluation(
                    rule_name="GENERATOR_COST_DATA",
                    passed=False,
                    reason=(
                        "Generator fuel consumption or fuel cost "
                        "data is unavailable; generator is excluded "
                        "from economic optimization."
                    ),
                )
            )

        return True

    # ==============================================================
    # EMERGENCY DECISION
    # ==============================================================

    def _emergency_decision(
        self,
        context,
        evaluations,
    ) -> EngineDecision:

        # Solar
        if context.solar_available and context.solar_kw > 0:

            return EngineDecision(
                selected_source="solar",
                reason=(
                    "Emergency mode: solar is currently producing "
                    "usable power and is the safest available source."
                ),
                estimated_cost_per_kwh=0.0,
                emergency_mode=True,
                evaluations=evaluations,
            )

        # Battery
        if (
            context.battery_available
            and context.battery_safe_to_discharge
            and context.battery_soc_percent
            > BatteryThresholds.CRITICAL_SOC
        ):

            return EngineDecision(
                selected_source="battery",
                reason=(
                    "Emergency mode: battery is being used to "
                    "protect site uptime."
                ),
                estimated_cost_per_kwh=None,
                emergency_mode=True,
                evaluations=evaluations,
            )

        # Generator
        if (
            context.generator_available
            and context.generator_fuel_level_percent
            > 10
        ):

            return EngineDecision(
                selected_source="generator",
                reason=(
                    "Emergency mode: generator is being used "
                    "to preserve site uptime."
                ),
                estimated_cost_per_kwh=None,
                emergency_mode=True,
                evaluations=evaluations,
            )

        # Grid
        if context.grid_available:

            return EngineDecision(
                selected_source="grid",
                reason=(
                    "Emergency mode fallback: grid is the only "
                    "remaining available source."
                ),
                estimated_cost_per_kwh=None,
                emergency_mode=True,
                evaluations=evaluations,
            )

        # No source
        return EngineDecision(
            selected_source="shutdown_risk",
            reason=(
                "Critical condition: no safe energy source "
                "is currently available."
            ),
            estimated_cost_per_kwh=None,
            emergency_mode=True,
            evaluations=evaluations,
        )

    # ==============================================================
    # NORMAL FALLBACK
    # ==============================================================

    def _fallback_decision(
        self,
        context,
        evaluations,
    ) -> EngineDecision:

        if context.grid_available:

            evaluations.append(
                RuleEvaluation(
                    rule_name="FALLBACK_GRID",
                    passed=True,
                    reason=(
                        "No economically valid alternative was "
                        "available; stable grid selected as fallback."
                    ),
                )
            )

            return EngineDecision(
                selected_source="grid",
                reason=(
                    "Grid selected as the safe operational fallback "
                    "because no alternative source has sufficiently "
                    "valid economic data."
                ),
                estimated_cost_per_kwh=None,
                emergency_mode=False,
                evaluations=evaluations,
            )

        if (
            context.battery_available
            and context.battery_safe_to_discharge
            and context.battery_soc_percent
            > BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC
        ):

            return EngineDecision(
                selected_source="battery",
                reason=(
                    "Battery selected as operational fallback because "
                    "grid is unavailable and battery can safely support "
                    "the site."
                ),
                estimated_cost_per_kwh=None,
                emergency_mode=False,
                evaluations=evaluations,
            )

        if context.generator_available:

            return EngineDecision(
                selected_source="generator",
                reason=(
                    "Generator selected as fallback because other "
                    "economically valid sources are unavailable."
                ),
                estimated_cost_per_kwh=None,
                emergency_mode=False,
                evaluations=evaluations,
            )

        return EngineDecision(
            selected_source="shutdown_risk",
            reason=(
                "No safe and feasible source is available."
            ),
            estimated_cost_per_kwh=None,
            emergency_mode=True,
            evaluations=evaluations,
        )