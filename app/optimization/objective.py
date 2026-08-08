from dataclasses import dataclass

from app.statebuilder.decision_context import DecisionContext


@dataclass(frozen=True)
class SourceObjective:
    """
    Economic information for one energy source.
    """

    source: str
    valid: bool
    cost_per_kwh: float | None
    reason: str


@dataclass(frozen=True)
class ObjectiveResult:
    """
    Economic evaluation of all energy sources.
    """

    solar: SourceObjective
    battery: SourceObjective
    grid: SourceObjective
    generator: SourceObjective


class ObjectiveCalculator:
    """
    Calculates economically valid operating costs.

    Important:
        Missing cost data is INVALID.
        It is never interpreted as free energy.
    """

    def calculate(
        self,
        context: DecisionContext,
    ) -> ObjectiveResult:

        return ObjectiveResult(
            solar=self._solar_cost(context),
            battery=self._battery_cost(context),
            grid=self._grid_cost(context),
            generator=self._generator_cost(context),
        )

    # ------------------------------------------------------------------
    # Solar
    # ------------------------------------------------------------------

    def _solar_cost(
        self,
        context: DecisionContext,
    ) -> SourceObjective:

        if context.solar_kw <= 0:
            return SourceObjective(
                source="solar",
                valid=False,
                cost_per_kwh=None,
                reason="Solar is not currently producing power.",
            )

        # Direct operating/fuel cost of solar is zero.
        #
        # This is NOT the same as saying solar has zero economic
        # lifecycle cost. At this layer we are calculating direct
        # operating cost only.

        return SourceObjective(
            source="solar",
            valid=True,
            cost_per_kwh=0.0,
            reason=(
                "Solar is generating power and has no direct "
                "fuel operating cost."
            ),
        )

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    def _battery_cost(
        self,
        context: DecisionContext,
    ) -> SourceObjective:

        if not context.battery_available:
            return SourceObjective(
                source="battery",
                valid=False,
                cost_per_kwh=None,
                reason="Battery is unavailable.",
            )

        cost = context.battery_wear_cost_per_kwh

        if cost is None:
            return SourceObjective(
                source="battery",
                valid=False,
                cost_per_kwh=None,
                reason="Battery degradation cost is missing.",
            )

        if cost <= 0:
            return SourceObjective(
                source="battery",
                valid=False,
                cost_per_kwh=None,
                reason=(
                    "Battery degradation cost must be greater than "
                    "zero for economic optimization."
                ),
            )

        return SourceObjective(
            source="battery",
            valid=True,
            cost_per_kwh=cost,
            reason=(
                "Battery cost is based on the configured estimated "
                "degradation/wear cost per kWh."
            ),
        )

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    def _grid_cost(
        self,
        context: DecisionContext,
    ) -> SourceObjective:

        if not context.grid_available:
            return SourceObjective(
                source="grid",
                valid=False,
                cost_per_kwh=None,
                reason="Grid is unavailable.",
            )

        tariff = context.grid_tariff_per_kwh

        if tariff is None:
            return SourceObjective(
                source="grid",
                valid=False,
                cost_per_kwh=None,
                reason="Grid electricity tariff is missing.",
            )

        if tariff <= 0:
            return SourceObjective(
                source="grid",
                valid=False,
                cost_per_kwh=None,
                reason=(
                    "Grid electricity tariff must be greater than "
                    "zero for economic optimization."
                ),
            )

        return SourceObjective(
            source="grid",
            valid=True,
            cost_per_kwh=tariff,
            reason=(
                "Grid cost is based on the current electricity "
                "tariff."
            ),
        )

    # ------------------------------------------------------------------
    # Generator
    # ------------------------------------------------------------------

    def _generator_cost(
        self,
        context: DecisionContext,
    ) -> SourceObjective:

        if not context.generator_available:
            return SourceObjective(
                source="generator",
                valid=False,
                cost_per_kwh=None,
                reason="Generator is unavailable.",
            )

        fuel_consumption = (
            context.generator_fuel_consumption_liter_hour
        )

        fuel_cost = context.generator_fuel_cost_per_liter

        if fuel_consumption <= 0:
            return SourceObjective(
                source="generator",
                valid=False,
                cost_per_kwh=None,
                reason=(
                    "Generator fuel consumption data is missing "
                    "or invalid."
                ),
            )

        if fuel_cost <= 0:
            return SourceObjective(
                source="generator",
                valid=False,
                cost_per_kwh=None,
                reason=(
                    "Generator fuel price is missing or invalid."
                ),
            )

        generator_power = context.generator_capacity_kw

        if generator_power <= 0:
            return SourceObjective(
                source="generator",
                valid=False,
                cost_per_kwh=None,
                reason=(
                    "Generator rated power is missing or invalid."
                ),
            )

        cost_per_kwh = (
            fuel_consumption * fuel_cost
        ) / generator_power

        if cost_per_kwh <= 0:
            return SourceObjective(
                source="generator",
                valid=False,
                cost_per_kwh=None,
                reason=(
                    "Calculated generator cost is invalid."
                ),
            )

        return SourceObjective(
            source="generator",
            valid=True,
            cost_per_kwh=cost_per_kwh,
            reason=(
                "Generator cost is calculated from fuel consumption, "
                "fuel price, and generator output capacity."
            ),
        )