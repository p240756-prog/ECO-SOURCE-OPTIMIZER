
from dataclasses import dataclass

from app.intelligence.cost_calculator import (
    CostCalculator,
    CostComparison,
)
from app.intelligence.safety_guard import (
    SafetyDecision,
    SafetyGuard,
)
from app.intelligence.source_feasibility import (
    SourceFeasibility,
    SourceFeasibilityEngine,
)
from app.optimization.dispatch import DispatchPlan
from app.optimization.engine import (
    OptimizationDecision,
    OptimizationEngine,
)
from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.state_builder import StateBuilder


@dataclass
class EngineDecision:
    """
    Final authoritative decision produced by the
    EcoSourceOptimizer pipeline.

    Contains the complete decision trail for:
        - auditability
        - explanation
        - debugging
        - API exposure
        - future reporting
    """

    selected_source: str | None
    estimated_cost_per_kwh: float | None

    emergency_mode: bool

    reason: str
    dispatch_plan: DispatchPlan | None

    state: CategoricalState
    feasibility: SourceFeasibility
    safety: SafetyDecision
    costs: CostComparison
    optimization: OptimizationDecision


class DecisionEngine:
    """
    Production decision orchestrator.

    Pipeline:

        Telemetry
            ↓
        StateBuilder
            ↓
        Feasibility
            ↓
        Safety
            ↓
        Economics
            ↓
        Optimization
            ↓
        Dispatch
            ↓
        Final Decision

    This class orchestrates the layers.

    It does not contain source-specific business rules.
    """

    def __init__(self) -> None:
        self.state_builder = StateBuilder()
        self.feasibility_engine = SourceFeasibilityEngine()
        self.safety_guard = SafetyGuard()
        self.cost_calculator = CostCalculator()
        self.optimization_engine = OptimizationEngine()

    def evaluate(
        self,
        context: DecisionContext,
    ) -> EngineDecision:
        # ==========================================================
        # 1. STATE
        # ==========================================================

        state = self.state_builder.build(context)

        # ==========================================================
        # 2. FEASIBILITY
        # ==========================================================

        feasibility = self.feasibility_engine.evaluate(
            context=context,
            state=state,
        )

        # ==========================================================
        # 3. SAFETY
        # ==========================================================

        safety = self.safety_guard.evaluate(
            context=context,
            state=state,
            feasibility=feasibility,
        )

        # ==========================================================
        # 4. ECONOMICS
        # ==========================================================

        costs = self.cost_calculator.calculate(
            context=context,
        )

        # ==========================================================
        # 5. OPTIMIZATION
        # ==========================================================

        optimization = self.optimization_engine.optimize(
            context=context,
            state=state,
            feasibility=feasibility,
            safety=safety,
            costs=costs,
        )

        # ==========================================================
        # 6. FINAL AUTHORITATIVE DECISION
        # ==========================================================

        return EngineDecision(
            selected_source=optimization.selected_source,
            estimated_cost_per_kwh=optimization.estimated_cost_per_kwh,
            emergency_mode=optimization.emergency_mode,
            reason=optimization.reason,
            dispatch_plan=optimization.dispatch_plan,
            state=state,
            feasibility=feasibility,
            safety=safety,
            costs=costs,
            optimization=optimization,
        )

