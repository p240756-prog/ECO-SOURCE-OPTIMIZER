from dataclasses import dataclass

from app.statebuilder.decision_context import DecisionContext


@dataclass
class PowerAnomaly:
    """
    Result of power-system anomaly detection.

    This module detects suspicious or physically inconsistent
    power telemetry. It does not make energy-source decisions.
    """

    detected: bool
    severity: str
    reasons: list[str]

    @property
    def is_critical(self) -> bool:
        return self.severity == "CRITICAL"


class PowerAnomalyDetector:
    """
    Detects abnormal power relationships in telemetry.

    This is intentionally independent from:
        - StateBuilder
        - SafetyGuard
        - OptimizationEngine
        - DecisionEngine

    It provides diagnostic intelligence that can later influence
    safety and recommendation decisions.
    """

    def detect(
        self,
        context: DecisionContext,
    ) -> PowerAnomaly:

        reasons: list[str] = []

        load = context.total_load_kw

        # --------------------------------------------------
        # Basic load validation
        # --------------------------------------------------

        if load < 0:
            reasons.append(
                f"Tower load is negative ({load:.3f} kW)."
            )

        # --------------------------------------------------
        # Solar anomaly
        # --------------------------------------------------

        if context.solar_kw < 0:
            reasons.append(
                f"Solar power is negative ({context.solar_kw:.3f} kW)."
            )

        if (
            context.solar_available
            and context.solar_kw <= 0
        ):
            reasons.append(
                "Solar is marked available but produces zero power."
            )

        # --------------------------------------------------
        # Grid anomaly
        # --------------------------------------------------

        if context.grid_kw < 0:
            reasons.append(
                f"Grid power is negative ({context.grid_kw:.3f} kW)."
            )

        if (
            context.grid_available
            and context.grid_capacity_kw <= 0
        ):
            reasons.append(
                "Grid is marked available but has no usable capacity."
            )

        if (
            context.grid_available
            and context.grid_kw > context.grid_capacity_kw
        ):
            reasons.append(
                "Grid power exceeds configured grid capacity."
            )

        # --------------------------------------------------
        # Generator anomaly
        # --------------------------------------------------

        if context.generator_kw < 0:
            reasons.append(
                f"Generator power is negative "
                f"({context.generator_kw:.3f} kW)."
            )

        if (
            context.generator_available
            and context.generator_kw > context.generator_capacity_kw
        ):
            reasons.append(
                "Generator output exceeds configured generator capacity."
            )

        # --------------------------------------------------
        # Frequency anomaly
        # --------------------------------------------------

        if context.grid_available:
            if (
                context.grid_frequency_hz < 45.0
                or context.grid_frequency_hz > 55.0
            ):
                reasons.append(
                    f"Grid frequency is physically abnormal "
                    f"({context.grid_frequency_hz:.2f} Hz)."
                )

        # --------------------------------------------------
        # Severity
        # --------------------------------------------------

        if not reasons:
            return PowerAnomaly(
                detected=False,
                severity="NORMAL",
                reasons=[],
            )

        critical_keywords = (
            "negative",
            "exceeds",
            "physically abnormal",
        )

        critical = any(
            any(
                keyword in reason.lower()
                for keyword in critical_keywords
            )
            for reason in reasons
        )

        return PowerAnomaly(
            detected=True,
            severity="CRITICAL" if critical else "WARNING",
            reasons=reasons,
        )