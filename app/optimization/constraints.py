import math
from dataclasses import dataclass

from app.statebuilder.decision_context import DecisionContext
from app.statebuilder.categorical_state import CategoricalState


@dataclass(frozen=True)
class SourceConstraint:
    """
    Operational constraint for one energy source.
    """

    source: str
    available: bool
    max_power_kw: float
    reason: str


class ConstraintEvaluator:
    """
    Determines the hard operational limits for each energy source.

    This class does not calculate economic cost and does not choose
    the cheapest source.

    It only determines what is physically and operationally possible.
    """

    def evaluate(
        self,
        context: DecisionContext,
        state: CategoricalState,
    ) -> tuple[SourceConstraint, ...]:

        return (
            self._solar_constraint(context, state),
            self._battery_constraint(context, state),
            self._grid_constraint(context, state),
            self._generator_constraint(context, state),
        )

    # ------------------------------------------------------------------
    # Solar
    # ------------------------------------------------------------------

    def _solar_constraint(
        self,
        context: DecisionContext,
        state: CategoricalState,
    ) -> SourceConstraint:

        if not state.solar_available:
            return SourceConstraint(
                source="solar",
                available=False,
                max_power_kw=0.0,
                reason="Solar is not currently available.",
            )

        solar_power = context.solar_kw

        if not math.isfinite(solar_power):
            return SourceConstraint(
                source="solar",
                available=False,
                max_power_kw=0.0,
                reason="Solar power telemetry is invalid.",
            )

        solar_power = max(solar_power, 0.0)

        if solar_power <= 0.0:
            return SourceConstraint(
                source="solar",
                available=False,
                max_power_kw=0.0,
                reason="Solar is marked available but is producing no power.",
            )

        return SourceConstraint(
            source="solar",
            available=True,
            max_power_kw=solar_power,
            reason="Solar generation is currently available.",
        )

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    def _battery_constraint(
        self,
        context: DecisionContext,
        state: CategoricalState,
    ) -> SourceConstraint:

        if not state.battery_available:
            return SourceConstraint(
                source="battery",
                available=False,
                max_power_kw=0.0,
                reason="Battery is unavailable.",
            )

        if not state.battery_safe:
            return SourceConstraint(
                source="battery",
                available=False,
                max_power_kw=0.0,
                reason="Battery is not safe for discharge.",
            )

        max_discharge = context.battery_max_discharge_kw

        if not math.isfinite(max_discharge):
            return SourceConstraint(
                source="battery",
                available=False,
                max_power_kw=0.0,
                reason="Battery discharge telemetry is invalid.",
            )

        max_discharge = max(max_discharge, 0.0)

        if max_discharge <= 0.0:
            return SourceConstraint(
                source="battery",
                available=False,
                max_power_kw=0.0,
                reason="Battery discharge capacity is unavailable.",
            )

        return SourceConstraint(
            source="battery",
            available=True,
            max_power_kw=max_discharge,
            reason=(
                f"Battery can safely discharge up to "
                f"{max_discharge:.3f} kW."
            ),
        )

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    def _grid_constraint(
        self,
        context: DecisionContext,
        state: CategoricalState,
    ) -> SourceConstraint:

        if not state.grid_available:
            return SourceConstraint(
                source="grid",
                available=False,
                max_power_kw=0.0,
                reason="Grid is unavailable.",
            )

        if not state.grid_stable:
            return SourceConstraint(
                source="grid",
                available=False,
                max_power_kw=0.0,
                reason="Grid is not electrically stable.",
            )

        capacity = context.grid_capacity_kw

        if not math.isfinite(capacity):
            return SourceConstraint(
                source="grid",
                available=False,
                max_power_kw=0.0,
                reason="Grid capacity telemetry is invalid.",
            )

        capacity = max(capacity, 0.0)

        if capacity <= 0.0:
            return SourceConstraint(
                source="grid",
                available=False,
                max_power_kw=0.0,
                reason="Grid capacity is unavailable.",
            )

        return SourceConstraint(
            source="grid",
            available=True,
            max_power_kw=capacity,
            reason=(
                f"Grid is stable and can provide up to "
                f"{capacity:.3f} kW."
            ),
        )

    # ------------------------------------------------------------------
    # Generator
    # ------------------------------------------------------------------

    def _generator_constraint(
        self,
        context: DecisionContext,
        state: CategoricalState,
    ) -> SourceConstraint:

        if not state.generator_available:
            return SourceConstraint(
                source="generator",
                available=False,
                max_power_kw=0.0,
                reason="Generator is unavailable.",
            )

        if not state.generator_ready:
            return SourceConstraint(
                source="generator",
                available=False,
                max_power_kw=0.0,
                reason="Generator is not ready for operation.",
            )

        capacity = context.generator_capacity_kw

        if not math.isfinite(capacity):
            return SourceConstraint(
                source="generator",
                available=False,
                max_power_kw=0.0,
                reason="Generator capacity telemetry is invalid.",
            )

        capacity = max(capacity, 0.0)

        if capacity <= 0.0:
            return SourceConstraint(
                source="generator",
                available=False,
                max_power_kw=0.0,
                reason="Generator capacity is unavailable.",
            )

        return SourceConstraint(
            source="generator",
            available=True,
            max_power_kw=capacity,
            reason=(
                f"Generator is ready and can provide up to "
                f"{capacity:.3f} kW."
            ),
        )