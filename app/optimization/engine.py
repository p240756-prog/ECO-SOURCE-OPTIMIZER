
from dataclasses import dataclass

from app.intelligence.cost_calculator import CostComparison
from app.intelligence.safety_guard import SafetyDecision
from app.intelligence.source_feasibility import SourceFeasibility
from app.optimization.constraints import (
    ConstraintEvaluator,
    SourceConstraint,
)
from app.optimization.dispatch import (
    DispatchPlan,
    DispatchPlanner,
)
from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.thresholds import BatteryThresholds


@dataclass
class OptimizationCandidate:
    source: str
    cost_per_kwh: float | None
    eligible: bool
    reason: str


@dataclass
class OptimizationDecision:
    selected_source: str | None
    estimated_cost_per_kwh: float | None
    emergency_mode: bool
    reason: str
    candidates: list[OptimizationCandidate]
    dispatch_plan: DispatchPlan | None = None


class OptimizationEngine:
    """
    Selects the best energy source after technical,
    safety, reserve, and economic validation.

    Decision hierarchy:

        1. Safety
        2. Technical feasibility
        3. Battery reserve protection
        4. Economic validity
        5. Cost optimization
        6. Physical dispatch

    CostCalculator remains the authoritative economics layer.

    Dispatch is restricted to sources that have passed
    the optimization eligibility checks.
    """

    def __init__(self) -> None:
        self.constraint_evaluator = ConstraintEvaluator()
        self.dispatch_planner = DispatchPlanner()

    def optimize(
        self,
        context: DecisionContext,
        state: CategoricalState,
        feasibility: SourceFeasibility,
        safety: SafetyDecision,
        costs: CostComparison,
    ) -> OptimizationDecision:

        candidates: list[OptimizationCandidate] = []

        source_map = {
            "solar": (
                feasibility.solar,
                safety.solar_allowed,
                costs.solar,
                "Solar",
            ),
            "battery": (
                feasibility.battery,
                safety.battery_allowed,
                costs.battery,
                "Battery",
            ),
            "grid": (
                feasibility.grid,
                safety.grid_allowed,
                costs.grid,
                "Grid",
            ),
            "generator": (
                feasibility.generator,
                safety.generator_allowed,
                costs.generator,
                "Generator",
            ),
        }

        # ==========================================================
        # 1. CANDIDATE VALIDATION
        # ==========================================================

        for source, (
            feasible,
            safe,
            cost,
            label,
        ) in source_map.items():

            if not feasible:
                candidates.append(
                    OptimizationCandidate(
                        source=source,
                        cost_per_kwh=cost.cost_per_kwh,
                        eligible=False,
                        reason=(
                            f"Source is technically infeasible: "
                            f"{self._source_reason(source, feasibility)}"
                        ),
                    )
                )
                continue

            if not safe:
                candidates.append(
                    OptimizationCandidate(
                        source=source,
                        cost_per_kwh=cost.cost_per_kwh,
                        eligible=False,
                        reason=(
                            f"{label} failed safety validation: "
                            f"{self._safety_reason(source, safety)}"
                        ),
                    )
                )
                continue

            if not cost.economically_valid:
                candidates.append(
                    OptimizationCandidate(
                        source=source,
                        cost_per_kwh=None,
                        eligible=False,
                        reason=(
                            f"{label} is technically available, but "
                            "its operating economics are incomplete "
                            "or invalid. It cannot participate in "
                            "normal cost optimization."
                        ),
                    )
                )
                continue

            # ------------------------------------------------------
            # Battery reserve protection
            # ------------------------------------------------------

            if source == "battery":
                reserve_soc = (
                    BatteryThresholds.MIN_DISCHARGE_RESERVE_SOC
                )
                current_soc = context.battery_soc_percent

                if current_soc < reserve_soc:
                    candidates.append(
                        OptimizationCandidate(
                            source="battery",
                            cost_per_kwh=cost.cost_per_kwh,
                            eligible=False,
                            reason=(
                                f"Battery SOC ({current_soc:.1f}%) "
                                f"is below the configured minimum "
                                f"discharge reserve "
                                f"({reserve_soc:.1f}%)."
                            ),
                        )
                    )
                    continue

            # ------------------------------------------------------
            # Fully eligible
            # ------------------------------------------------------

            candidates.append(
                OptimizationCandidate(
                    source=source,
                    cost_per_kwh=cost.cost_per_kwh,
                    eligible=True,
                    reason=(
                        f"{label} passed technical feasibility, "
                        "safety, economic validation, and all "
                        "source-specific constraints."
                    ),
                )
            )

        # ==========================================================
        # 2. HARD CONSTRAINTS
        # ==========================================================

        constraints = self.constraint_evaluator.evaluate(
            context=context,
            state=state,
        )

        # ==========================================================
        # 3. ECONOMIC OPTIMIZATION
        # ==========================================================

        eligible = [
            candidate
            for candidate in candidates
            if candidate.eligible
            and candidate.cost_per_kwh is not None
        ]

        if eligible:
            eligible.sort(
                key=lambda candidate: candidate.cost_per_kwh
            )

            selected = eligible[0]

            # ------------------------------------------------------
            # IMPORTANT:
            #
            # Dispatch may only use sources that survived ALL
            # optimization checks above.
            #
            # This prevents a source rejected by SafetyGuard or
            # reserve protection from entering physical dispatch
            # merely because ConstraintEvaluator says it is
            # technically available.
            # ------------------------------------------------------

            eligible_sources = {
                candidate.source
                for candidate in eligible
            }

            dispatch_constraints: tuple[SourceConstraint, ...] = tuple(
                constraint
                for constraint in constraints
                if constraint.source in eligible_sources
            )

            # ======================================================
            # 4. ACTUAL DISPATCH
            # ======================================================

            dispatch_plan = self.dispatch_planner.create_plan(
                load_kw=context.total_load_kw,
                constraints=dispatch_constraints,
                costs=costs,
            )

            # If no eligible source can physically serve any load,
            # the system must enter emergency mode.
            if dispatch_plan.supplied_load_kw <= 0:
                return OptimizationDecision(
                    selected_source=None,
                    estimated_cost_per_kwh=None,
                    emergency_mode=True,
                    reason=(
                        "Economically valid and safety-approved "
                        "sources exist, but the dispatch layer "
                        "could not allocate any power to the site load."
                    ),
                    candidates=candidates,
                    dispatch_plan=dispatch_plan,
                )

            # ------------------------------------------------------
            # Dispatch is authoritative for the actual primary
            # source and actual blended operating cost.
            # ------------------------------------------------------

            primary_source = dispatch_plan.allocations[0][0]

            actual_cost_per_kwh = (
                dispatch_plan.total_cost_per_hour
                / dispatch_plan.supplied_load_kw
            )

            ranking = ", ".join(
                (
                    f"{candidate.source}="
                    f"{candidate.cost_per_kwh:.4f} PKR/kWh"
                )
                for candidate in eligible
            )

            unmet_text = ""

            if dispatch_plan.unmet_load_kw > 0:
                unmet_text = (
                    " Dispatch cannot fully satisfy the site load; "
                    f"{dispatch_plan.unmet_load_kw:.3f} kW remains unmet."
                )

            return OptimizationDecision(
                selected_source=primary_source,
                estimated_cost_per_kwh=actual_cost_per_kwh,
                emergency_mode=dispatch_plan.unmet_load_kw > 0,
                reason=(
                    f"{primary_source} selected at "
                    f"{actual_cost_per_kwh:.4f} PKR/kWh effective "
                    "dispatch cost. The source set passed technical "
                    "feasibility, safety, reserve, and economic "
                    f"validation. Eligible cost ranking: {ranking}."
                    f"{unmet_text}"
                ),
                candidates=candidates,
                dispatch_plan=dispatch_plan,
            )

        # ==========================================================
        # 5. RELIABILITY FALLBACK
        # ==========================================================

        emergency_sources = [
            source
            for source, (
                feasible,
                safe,
                _,
                _,
            ) in source_map.items()
            if feasible and safe
        ]

        if emergency_sources:
            reliability_priority = [
                "grid",
                "battery",
                "generator",
                "solar",
            ]

            selected_source = next(
                (
                    source
                    for source in reliability_priority
                    if source in emergency_sources
                ),
                None,
            )

            return OptimizationDecision(
                selected_source=selected_source,
                estimated_cost_per_kwh=None,
                emergency_mode=True,
                reason=(
                    f"{selected_source} selected under reliability "
                    "fallback because no source has complete valid "
                    "economic data. Economic optimization is suspended "
                    "rather than assigning an artificial zero cost."
                ),
                candidates=candidates,
                dispatch_plan=None,
            )

        # ==========================================================
        # 6. NO SAFE SOURCE
        # ==========================================================

        return OptimizationDecision(
            selected_source=None,
            estimated_cost_per_kwh=None,
            emergency_mode=True,
            reason=(
                "No energy source passed both technical feasibility "
                "and safety validation. Site power continuity is "
                "at risk."
            ),
            candidates=candidates,
            dispatch_plan=None,
        )

    # ==============================================================
    # REASON HELPERS
    # ==============================================================

    @staticmethod
    def _source_reason(
        source: str,
        feasibility: SourceFeasibility,
    ) -> str:
        reasons = {
            "solar": feasibility.solar_reason,
            "battery": feasibility.battery_reason,
            "grid": feasibility.grid_reason,
            "generator": feasibility.generator_reason,
        }

        return reasons.get(
            source,
            "Source failed technical feasibility.",
        )

    @staticmethod
    def _safety_reason(
        source: str,
        safety: SafetyDecision,
    ) -> str:
        reasons = {
            "solar": safety.solar_reason,
            "battery": safety.battery_reason,
            "grid": safety.grid_reason,
            "generator": safety.generator_reason,
        }

        return reasons.get(
            source,
            "Source failed safety validation.",
        )
