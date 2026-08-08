from dataclasses import dataclass
from typing import Literal


EnergySource = Literal[
    "solar",
    "battery",
    "grid",
    "generator",
    "shutdown_risk",
]


@dataclass
class RuleDecision:
    source: EnergySource
    reason: str
    priority: int
    estimated_cost_per_kwh: float
    emergency: bool = False


@dataclass
class RuleEvaluation:
    rule_name: str
    passed: bool
    reason: str


@dataclass
class EngineDecision:
    selected_source: EnergySource
    reason: str

    estimated_cost_per_kwh: float

    emergency_mode: bool

    evaluations: list[RuleEvaluation]