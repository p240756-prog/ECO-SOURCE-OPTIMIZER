from app.events.models import AlertEvent


class AlertEngine:
    """
    Converts operational conditions into actionable alerts.

    This layer does not select an energy source.
    It only identifies conditions that require attention.
    """

    def evaluate(
        self,
        site_id: str,
        timestamp,
        decision,
    ) -> list[AlertEvent]:

        alerts: list[AlertEvent] = []

        if decision.emergency_mode:
            alerts.append(
                AlertEvent(
                    site_id=site_id,
                    timestamp=timestamp,
                    alert_type="EMERGENCY_POWER",
                    severity="CRITICAL",
                    message=(
                        "No energy source passed the complete "
                        "technical, safety, and economic decision pipeline."
                    ),
                )
            )

        state = decision.state

        if not state.battery_safe:
            alerts.append(
                AlertEvent(
                    site_id=site_id,
                    timestamp=timestamp,
                    alert_type="BATTERY_SAFETY",
                    severity="HIGH",
                    message="Battery is not considered safe for discharge.",
                    source="battery",
                )
            )

        if not state.grid_stable:
            alerts.append(
                AlertEvent(
                    site_id=site_id,
                    timestamp=timestamp,
                    alert_type="GRID_INSTABILITY",
                    severity="HIGH",
                    message="Grid conditions are outside the configured stable range.",
                    source="grid",
                )
            )

        if not state.generator_ready:
            alerts.append(
                AlertEvent(
                    site_id=site_id,
                    timestamp=timestamp,
                    alert_type="GENERATOR_UNAVAILABLE",
                    severity="HIGH",
                    message="Generator is not currently ready for operation.",
                    source="generator",
                )
            )

        return alerts