from dataclasses import dataclass

from app.statebuilder.decision_context import DecisionContext


@dataclass
class SourceCost:
    """
    Economic information for one energy source.

    None means the cost is unknown or invalid.

    Unknown cost is NEVER treated as free.
    """

    source: str
    cost_per_kwh: float | None
    available: bool
    economically_valid: bool
    reason: str


@dataclass
class CostComparison:
    """
    Economic comparison for all energy sources.
    """

    solar: SourceCost
    battery: SourceCost
    grid: SourceCost
    generator: SourceCost


class CostCalculator:
    """
    Calculates source operating economics.

    This class never selects a source.

    CostCalculator is the authoritative economics layer.
    """

    def calculate(
        self,
        context: DecisionContext,
    ) -> CostComparison:

        # ==========================================================
        # SOLAR
        # ==========================================================

        if (
            context.solar_available
            and context.solar_kw > 0
        ):
            solar = SourceCost(
                source="solar",
                cost_per_kwh=0.0,
                available=True,
                economically_valid=True,
                reason=(
                    "Solar is producing usable power. "
                    "No direct marginal fuel cost is applied."
                ),
            )
        else:
            solar = SourceCost(
                source="solar",
                cost_per_kwh=None,
                available=False,
                economically_valid=False,
                reason=(
                    "Solar is not currently producing usable power."
                ),
            )

        # ==========================================================
        # BATTERY
        # ==========================================================

        if not context.battery_available:
            battery = SourceCost(
                source="battery",
                cost_per_kwh=None,
                available=False,
                economically_valid=False,
                reason="Battery is unavailable.",
            )

        elif (
            context.battery_wear_cost_per_kwh is None
            or context.battery_wear_cost_per_kwh <= 0
        ):
            battery = SourceCost(
                source="battery",
                cost_per_kwh=None,
                available=True,
                economically_valid=False,
                reason=(
                    "Battery degradation/wear cost is missing or invalid. "
                    "Battery must not be treated as free energy."
                ),
            )

        else:
            battery = SourceCost(
                source="battery",
                cost_per_kwh=context.battery_wear_cost_per_kwh,
                available=True,
                economically_valid=True,
                reason=(
                    "Battery cost is based on estimated degradation "
                    "or wear cost per delivered kWh."
                ),
            )

        # ==========================================================
        # GRID
        # ==========================================================

        if not context.grid_available:
            grid = SourceCost(
                source="grid",
                cost_per_kwh=None,
                available=False,
                economically_valid=False,
                reason="Grid is unavailable.",
            )

        elif context.grid_tariff_per_kwh <= 0:
            grid = SourceCost(
                source="grid",
                cost_per_kwh=None,
                available=True,
                economically_valid=False,
                reason=(
                    "Grid electricity tariff is missing or invalid."
                ),
            )

        else:
            grid = SourceCost(
                source="grid",
                cost_per_kwh=context.grid_tariff_per_kwh,
                available=True,
                economically_valid=True,
                reason=(
                    "Grid cost is based on the current electricity tariff."
                ),
            )

        # ==========================================================
        # GENERATOR
        # ==========================================================

        if not context.generator_available:
            generator = SourceCost(
                source="generator",
                cost_per_kwh=None,
                available=False,
                economically_valid=False,
                reason="Generator is unavailable.",
            )

        elif context.generator_kw <= 0:
            generator = SourceCost(
                source="generator",
                cost_per_kwh=None,
                available=True,
                economically_valid=False,
                reason=(
                    "Generator is available but current generator "
                    "power output is zero."
                ),
            )

        elif context.generator_fuel_consumption_liter_hour <= 0:
            generator = SourceCost(
                source="generator",
                cost_per_kwh=None,
                available=True,
                economically_valid=False,
                reason=(
                    "Generator fuel consumption data is missing or invalid."
                ),
            )

        elif (
            context.generator_fuel_cost_per_liter is None
            or context.generator_fuel_cost_per_liter <= 0
        ):
            generator = SourceCost(
                source="generator",
                cost_per_kwh=None,
                available=True,
                economically_valid=False,
                reason=(
                    "Generator fuel price is missing or invalid."
                ),
            )

        else:
            # Actual measured generator output is authoritative
            # for the current operating condition.
            fuel_cost_per_hour = (
                context.generator_fuel_consumption_liter_hour
                * context.generator_fuel_cost_per_liter
            )

            generator_cost_per_kwh = (
                fuel_cost_per_hour
                / context.generator_kw
            )

            generator = SourceCost(
                source="generator",
                cost_per_kwh=generator_cost_per_kwh,
                available=True,
                economically_valid=True,
                reason=(
                    "Generator cost is calculated from fuel consumption, "
                    "fuel price, and measured generator output."
                ),
            )

        return CostComparison(
            solar=solar,
            battery=battery,
            grid=grid,
            generator=generator,
        )