import math
from dataclasses import dataclass

from app.intelligence.cost_calculator import CostComparison
from app.optimization.constraints import SourceConstraint


@dataclass(frozen=True)
class DispatchPlan:
    """
    Power dispatch plan generated from validated constraints
    and authoritative economic results.
    """

    allocations: tuple[tuple[str, float, float], ...]
    supplied_load_kw: float
    unmet_load_kw: float
    total_cost_per_hour: float


class DispatchPlanner:
    """
    Allocates the required load across energy sources.

    The planner consumes:
        - hard operational constraints
        - authoritative CostCalculator results

    It does NOT calculate source economics itself.
    """

    def create_plan(
        self,
        load_kw: float,
        constraints: tuple[SourceConstraint, ...],
        costs: CostComparison,
    ) -> DispatchPlan:

        if not math.isfinite(load_kw):
            raise ValueError("Load must be a finite number.")

        if load_kw < 0:
            raise ValueError("Load cannot be negative.")

        if load_kw == 0:
            return DispatchPlan(
                allocations=(),
                supplied_load_kw=0.0,
                unmet_load_kw=0.0,
                total_cost_per_hour=0.0,
            )

        cost_map = {
            "solar": costs.solar,
            "battery": costs.battery,
            "grid": costs.grid,
            "generator": costs.generator,
        }

        candidates = []

        for constraint in constraints:

            if not constraint.available:
                continue

            if not math.isfinite(constraint.max_power_kw):
                continue

            if constraint.max_power_kw <= 0:
                continue

            source_cost = cost_map.get(constraint.source)

            if source_cost is None:
                continue

            if not source_cost.economically_valid:
                continue

            if source_cost.cost_per_kwh is None:
                continue

            if not math.isfinite(source_cost.cost_per_kwh):
                continue

            if source_cost.cost_per_kwh < 0:
                continue

            candidates.append(
                (
                    constraint.source,
                    constraint.max_power_kw,
                    source_cost.cost_per_kwh,
                )
            )

        # Cheapest authoritative valid source first.
        candidates.sort(
            key=lambda item: item[2]
        )

        remaining_load = load_kw
        allocations = []
        total_cost = 0.0

        for (
            source,
            max_power_kw,
            cost_per_kwh,
        ) in candidates:

            if remaining_load <= 0:
                break

            allocated_power = min(
                remaining_load,
                max_power_kw,
            )

            if allocated_power <= 0:
                continue

            if not math.isfinite(allocated_power):
                continue

            total_cost += (
                allocated_power * cost_per_kwh
            )

            allocations.append(
                (
                    source,
                    allocated_power,
                    cost_per_kwh,
                )
            )

            remaining_load -= allocated_power

        supplied_load = load_kw - remaining_load

        return DispatchPlan(
            allocations=tuple(allocations),
            supplied_load_kw=supplied_load,
            unmet_load_kw=remaining_load,
            total_cost_per_hour=total_cost,
        )