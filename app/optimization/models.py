
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DispatchAllocation:
    """
    Power allocation assigned to one energy source.

    power_kw:
        Actual power requested from the source.

    cost_per_kwh:
        Valid operating cost associated with the source.

    estimated_cost_per_hour:
        Cost of operating this allocation for one hour.
    """

    source: str
    power_kw: float
    cost_per_kwh: float
    estimated_cost_per_hour: float
    reason: str


@dataclass(frozen=True)
class OptimizationResult:
    """
    Final result produced by the optimization engine.

    This represents the optimizer's recommended dispatch plan.
    """

    site_id: str

    total_load_kw: float
    supplied_load_kw: float
    unmet_load_kw: float

    allocations: tuple[DispatchAllocation, ...]

    total_operating_cost_per_hour: float

    primary_source: str

    status: str

    emergency_mode: bool

    reason: str

    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def load_fully_supplied(self) -> bool:
        """
        True only when the optimizer completely satisfies
        the requested site load.
        """
        return self.unmet_load_kw <= 0.0

    @property
    def total_allocated_power_kw(self) -> float:
        """
        Total power allocated across all sources.
        """
        return sum(
            allocation.power_kw
            for allocation in self.allocations
        )
