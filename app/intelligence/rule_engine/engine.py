from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.categorical_state import CategoricalState

from app.intelligence.cost_calculator import CostComparison

from app.intelligence.rule_engine.models import (
    EngineDecision,
    RuleEvaluation,
)

from app.intelligence.rule_engine.rules import RuleSet


class RuleEngine:
    """
    Industrial energy-source decision engine.

    Responsibilities:

    1. Evaluate source feasibility.
    2. Respect safety decisions.
    3. Apply source-priority rules.
    4. Optimize operating cost.
    5. Protect battery reserves.
    6. Provide deterministic fallback behavior.
    7. Produce explainable decisions.

    This class decides WHAT source should be used.

    It does not collect telemetry and does not calculate raw
    telemetry states.
    """

    def evaluate(
        self,
        context: DecisionContext,
        state: CategoricalState,
        costs: CostComparison,
    ) -> EngineDecision:

        evaluations: list[RuleEvaluation] = []

        # --------------------------------------------------
        # Evaluate all sources
        # --------------------------------------------------

        solar = RuleSet.evaluate_solar(
            context,
            state,
            costs,
        )

        battery = RuleSet.evaluate_battery(
            context,
            state,
            costs,
        )

        grid = RuleSet.evaluate_grid(
            context,
            state,
            costs,
        )

        generator = RuleSet.evaluate_generator(
            context,
            state,
            costs,
        )

        evaluations.extend(
            [
                solar,
                battery,
                grid,
                generator,
            ]
        )

        # --------------------------------------------------
        # Emergency protection
        # --------------------------------------------------

        usable_sources = []

        if solar.passed:
            usable_sources.append("solar")

        if battery.passed:
            usable_sources.append("battery")

        if grid.passed:
            usable_sources.append("grid")

        if generator.passed:
            usable_sources.append("generator")

        if not usable_sources:

            return EngineDecision(
                selected_source="shutdown_risk",
                reason=(
                    "No energy source can safely satisfy the "
                    "current site demand."
                ),
                estimated_cost_per_kwh=0.0,
                emergency_mode=True,
                evaluations=evaluations,
            )

        # --------------------------------------------------
        # Solar priority
        # --------------------------------------------------

        if solar.passed:

            if context.solar_kw >= context.total_load_kw:

                return EngineDecision(
                    selected_source="solar",
                    reason=(
                        "Solar can fully satisfy the current load "
                        "and has no direct fuel cost."
                    ),
                    estimated_cost_per_kwh=costs.solar.cost_per_kwh,
                    emergency_mode=False,
                    evaluations=evaluations,
                )

        # --------------------------------------------------
        # Build economically valid candidates
        # --------------------------------------------------

        candidates = []

        if solar.passed and context.solar_kw > 0:
            candidates.append(
                (
                    "solar",
                    costs.solar.cost_per_kwh,
                )
            )

        if battery.passed:
            candidates.append(
                (
                    "battery",
                    costs.battery.cost_per_kwh,
                )
            )

        if grid.passed and costs.grid.available:
            candidates.append(
                (
                    "grid",
                    costs.grid.cost_per_kwh,
                )
            )

        if generator.passed and costs.generator.available:
            candidates.append(
                (
                    "generator",
                    costs.generator.cost_per_kwh,
                )
            )

        # --------------------------------------------------
        # Economic optimization
        # --------------------------------------------------

        if candidates:

            selected_source, selected_cost = min(
                candidates,
                key=lambda item: item[1],
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

        # --------------------------------------------------
        # Safety fallback
        # --------------------------------------------------

        if grid.passed:

            return EngineDecision(
                selected_source="grid",
                reason=(
                    "Grid is the safest available fallback because "
                    "no other source has valid economic data."
                ),
                estimated_cost_per_kwh=costs.grid.cost_per_kwh,
                emergency_mode=False,
                evaluations=evaluations,
            )

        if battery.passed:

            return EngineDecision(
                selected_source="battery",
                reason=(
                    "Battery is being used as the fallback source "
                    "because grid is unavailable."
                ),
                estimated_cost_per_kwh=costs.battery.cost_per_kwh,
                emergency_mode=False,
                evaluations=evaluations,
            )

        if generator.passed:

            return EngineDecision(
                selected_source="generator",
                reason=(
                    "Generator is being used as the final available "
                    "power source."
                ),
                estimated_cost_per_kwh=costs.generator.cost_per_kwh,
                emergency_mode=True,
                evaluations=evaluations,
            )

        return EngineDecision(
            selected_source="shutdown_risk",
            reason="No safe energy source remains.",
            estimated_cost_per_kwh=0.0,
            emergency_mode=True,
            evaluations=evaluations,
        )