from dataclasses import dataclass

from app.statebuilder.decision_context import DecisionContext


@dataclass
class FuelAnomaly:
    """
    Result of generator fuel anomaly detection.
    """

    detected: bool
    severity: str
    reasons: list[str]

    @property
    def is_critical(self) -> bool:
        return self.severity == "CRITICAL"


class FuelAnomalyDetector:
    """
    Detects suspicious generator fuel telemetry.

    This module does not calculate generator economics.
    It only identifies telemetry inconsistencies and
    potentially unsafe fuel conditions.
    """

    def detect(
        self,
        context: DecisionContext,
    ) -> FuelAnomaly:

        reasons: list[str] = []

        fuel = context.generator_fuel_level_percent
        consumption = context.generator_fuel_consumption_liter_hour
        generator_power = context.generator_kw

        # --------------------------------------------------
        # Fuel percentage validation
        # --------------------------------------------------

        if fuel < 0 or fuel > 100:
            reasons.append(
                f"Generator fuel level is outside valid range "
                f"({fuel:.2f}%)."
            )

        # --------------------------------------------------
        # Fuel consumption validation
        # --------------------------------------------------

        if consumption < 0:
            reasons.append(
                f"Generator fuel consumption is negative "
                f"({consumption:.3f} L/h)."
            )

        # --------------------------------------------------
        # Generator operating consistency
        # --------------------------------------------------

        if (
            context.generator_available
            and generator_power > 0
            and consumption <= 0
        ):
            reasons.append(
                "Generator is producing power but fuel consumption "
                "is zero or missing."
            )

        if (
            generator_power <= 0
            and consumption > 0
        ):
            reasons.append(
                "Fuel consumption is reported while generator "
                "output is zero."
            )

        # --------------------------------------------------
        # Fuel depletion
        # --------------------------------------------------

        if (
            context.generator_available
            and fuel <= 0
        ):
            reasons.append(
                "Generator is marked available but fuel level is depleted."
            )

        # --------------------------------------------------
        # Severity
        # --------------------------------------------------

        if not reasons:
            return FuelAnomaly(
                detected=False,
                severity="NORMAL",
                reasons=[],
            )

        critical = any(
            "outside valid range" in reason
            or "negative" in reason
            or "depleted" in reason
            for reason in reasons
        )

        return FuelAnomaly(
            detected=True,
            severity="CRITICAL" if critical else "WARNING",
            reasons=reasons,
        )