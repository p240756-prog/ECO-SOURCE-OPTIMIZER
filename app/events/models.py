from dataclasses import dataclass
from datetime import datetime


@dataclass
class AlertEvent:
    site_id: str
    timestamp: datetime
    alert_type: str
    severity: str
    message: str
    source: str | None = None
    acknowledged: bool = False