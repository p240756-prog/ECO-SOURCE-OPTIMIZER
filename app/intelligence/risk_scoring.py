from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RiskInput:
    battery_soc_percent: float
    temperature: float
    tower_load_kw: float
    solar_power_kw: float
    grid_power_kw: float


@dataclass(frozen=True)
class RiskResult:
    score: float
    level: RiskLevel
    reasons: tuple[str, ...]


class RiskScorer:
    """
    Calculates an operational risk score for a telecom tower.

    The score ranges from 0 to 100:
        0-24   LOW
        25-49  MODERATE
        50-74  HIGH
        75-100 CRITICAL

    This class only scores risk. It does not select an energy source.
    """

    def __init__(
        self,
        critical_soc_percent: float = 20.0,
        warning_soc_percent: float = 40.0,
        high_temperature: float = 45.0,
        critical_temperature: float = 55.0,
    ) -> None:
        self.critical_soc_percent = critical_soc_percent
        self.warning_soc_percent = warning_soc_percent
        self.high_temperature = high_temperature
        self.critical_temperature = critical_temperature

    def calculate(self, data: RiskInput) -> RiskResult:
        self._validate(data)

        score = 0.0
        reasons: list[str] = []

        # Battery risk: maximum contribution = 40
        if data.battery_soc_percent <= self.critical_soc_percent:
            score += 40
            reasons.append("Battery SOC is at or below the critical threshold.")
        elif data.battery_soc_percent < self.warning_soc_percent:
            score += 25
            reasons.append("Battery SOC is below the warning threshold.")
        elif data.battery_soc_percent < 60:
            score += 10

        # Temperature risk: maximum contribution = 20
        if data.temperature >= self.critical_temperature:
            score += 20
            reasons.append("Temperature is at or above the critical threshold.")
        elif data.temperature >= self.high_temperature:
            score += 12
            reasons.append("Temperature is above the high-temperature threshold.")
        elif data.temperature >= 40:
            score += 5

        # Load risk: maximum contribution = 15
        if data.tower_load_kw > 0:
            available_power = data.solar_power_kw + data.grid_power_kw

            if available_power <= 0:
                score += 15
                reasons.append("No solar or grid power is currently available.")
            elif available_power < data.tower_load_kw:
                score += 10
                reasons.append("Available primary power is below tower load.")
            elif available_power < data.tower_load_kw * 1.10:
                score += 5

        # Solar availability risk: maximum contribution = 10
        if data.tower_load_kw > 0:
            solar_ratio = data.solar_power_kw / data.tower_load_kw

            if solar_ratio == 0:
                score += 10
                reasons.append("Solar generation is unavailable.")
            elif solar_ratio < 0.25:
                score += 5

        # Grid availability risk: maximum contribution = 15
        if data.grid_power_kw <= 0:
            score += 15
            reasons.append("Grid power is unavailable.")
        elif data.tower_load_kw > 0 and data.grid_power_kw < data.tower_load_kw:
            score += 10
            reasons.append("Grid capacity is below tower load.")

        score = min(100.0, max(0.0, score))
        level = self._get_level(score)

        return RiskResult(
            score=score,
            level=level,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _get_level(score: float) -> RiskLevel:
        if score >= 75:
            return RiskLevel.CRITICAL

        if score >= 50:
            return RiskLevel.HIGH

        if score >= 25:
            return RiskLevel.MODERATE

        return RiskLevel.LOW

    @staticmethod
    def _validate(data: RiskInput) -> None:
        if not 0 <= data.battery_soc_percent <= 100:
            raise ValueError("battery_soc_percent must be between 0 and 100.")

        if data.temperature < -50:
            raise ValueError("temperature is outside the supported range.")

        if data.tower_load_kw < 0:
            raise ValueError("tower_load_kw cannot be negative.")

        if data.solar_power_kw < 0:
            raise ValueError("solar_power_kw cannot be negative.")

        if data.grid_power_kw < 0:
            raise ValueError("grid_power_kw cannot be negative.")