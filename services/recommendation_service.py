from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Telemetry

from app.statebuilder.adapter import TelemetryAdapter
from app.decision.engine import DecisionEngine

from app.intelligence.anomaly.power_anomaly import (
    PowerAnomaly,
    PowerAnomalyDetector,
)

from app.intelligence.anomaly.fuel_anomaly import (
    FuelAnomaly,
    FuelAnomalyDetector,
)

from app.events.alert_engine import AlertEngine
from app.events.event_store import EventStore
from app.events.models import AlertEvent


@dataclass
class RecommendationResult:
    """
    Application-level recommendation result.

    Preserves the complete decision result together with
    anomaly diagnostics and generated operational alerts.
    """

    site_id: str
    timestamp: object

    selected_source: str | None
    estimated_cost_per_kwh: float | None

    emergency_mode: bool
    reason: str

    power_anomaly: PowerAnomaly
    fuel_anomaly: FuelAnomaly

    alerts: list[AlertEvent]

    decision: object


class RecommendationService:
    """
    Coordinates telemetry retrieval and the complete
    recommendation pipeline.

    Pipeline:

        Database
            ↓
        TelemetryAdapter
            ↓
        DecisionEngine
            ↓
        Anomaly Detection
            ↓
        AlertEngine
            ↓
        EventStore
            ↓
        RecommendationResult
    """

    def __init__(self) -> None:

        self.decision_engine = DecisionEngine()

        self.power_anomaly_detector = (
            PowerAnomalyDetector()
        )

        self.fuel_anomaly_detector = (
            FuelAnomalyDetector()
        )

        self.alert_engine = AlertEngine()

        self.event_store = EventStore()

    def recommend_latest(
        self,
        db: Session,
        site_id: str,
    ) -> RecommendationResult:

        telemetry = (
            db.query(Telemetry)
            .filter(
                Telemetry.site_id == site_id,
            )
            .order_by(
                Telemetry.timestamp.desc(),
            )
            .first()
        )

        if telemetry is None:
            raise ValueError(
                f"No telemetry found for site '{site_id}'."
            )

        return self.recommend_from_telemetry(
            telemetry=telemetry,
        )

    def recommend_from_telemetry(
        self,
        telemetry: Telemetry,
    ) -> RecommendationResult:

        # --------------------------------------------------
        # 1. Convert telemetry into decision context
        # --------------------------------------------------

        context = TelemetryAdapter.to_decision_context(
            telemetry,
        )

        # --------------------------------------------------
        # 2. Run authoritative decision pipeline
        # --------------------------------------------------

        decision = self.decision_engine.evaluate(
            context,
        )

        # --------------------------------------------------
        # 3. Detect telemetry anomalies
        # --------------------------------------------------

        power_anomaly = (
            self.power_anomaly_detector.detect(
                context,
            )
        )

        fuel_anomaly = (
            self.fuel_anomaly_detector.detect(
                context,
            )
        )

        # --------------------------------------------------
        # 4. Generate operational alerts
        # --------------------------------------------------

        alerts = self.alert_engine.evaluate(
            site_id=telemetry.site_id,
            timestamp=telemetry.timestamp,
            decision=decision,
        )

        # --------------------------------------------------
        # 5. Store generated events
        # --------------------------------------------------

        if alerts:
            self.event_store.add_many(
                alerts,
            )

        # --------------------------------------------------
        # 6. Return complete recommendation
        # --------------------------------------------------

        return RecommendationResult(
            site_id=telemetry.site_id,
            timestamp=telemetry.timestamp,
            selected_source=decision.selected_source,
            estimated_cost_per_kwh=(
                decision.estimated_cost_per_kwh
            ),
            emergency_mode=decision.emergency_mode,
            reason=decision.reason,
            power_anomaly=power_anomaly,
            fuel_anomaly=fuel_anomaly,
            alerts=alerts,
            decision=decision,
        )
    