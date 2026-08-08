"""
ingestion.py
============

Ingestion pipeline with schema validation and quarantine.

Implements the "Ingestion and Testing Pipeline for the Rule Engine" section
of the annex:

    Simulator or log replay → ingestion API → schema validation →
    state builder → rule engine → event store → dashboard and alerts

Every record is validated before it enters the event store.  Malformed
records are quarantined with a typed error — the pipeline never crashes or
silently accepts bad data.

Cross-record checks (single-record checks live in schema.py):
    - Staleness: timestamp older than max_staleness_seconds (sets stale flag)
    - Duplicate timestamps for the same site
    - Out-of-order records
    - Physically impossible battery-SoC rate-of-change
    - Conflicting readings (generator running while grid up + battery high)
    - Held-out real data guard (source=Real blocked from training runs)

On acceptance the pipeline stamps schema_valid=True.  Stale (but otherwise
valid) records are accepted with stale_data_flag=True rather than dropped, so
the rule engine can fall back to last-known-safe state (annex behaviour).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from data_layer.schema import (
    TelemetryRecord,
    GeneratorState,
    GridStatus,
    Source,
    validate_record,
    SchemaError,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_STALENESS_SECONDS: int = 3600          # 1 hour
MAX_SOC_CHANGE_PER_MINUTE: float = 5.0     # %/min — impossible above this


# ---------------------------------------------------------------------------
# Quarantine + result types
# ---------------------------------------------------------------------------

@dataclass
class QuarantineEntry:
    raw: TelemetryRecord
    error_code: str
    error_message: str
    quarantined_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __str__(self) -> str:
        return (
            f"[{self.error_code}] site={self.raw.site_id} "
            f"ts={self.raw.timestamp.isoformat()} — {self.error_message}"
        )


@dataclass
class IngestionResult:
    accepted: List[TelemetryRecord] = field(default_factory=list)
    quarantined: List[QuarantineEntry] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.accepted) + len(self.quarantined)

    @property
    def acceptance_rate(self) -> float:
        return len(self.accepted) / self.total if self.total else 0.0

    def summary(self) -> str:
        lines = [
            f"Ingestion complete: {self.total} records processed",
            f"  Accepted   : {len(self.accepted)} ({self.acceptance_rate:.1%})",
            f"  Quarantined: {len(self.quarantined)}",
        ]
        if self.quarantined:
            lines.append("  Quarantine errors (first 10):")
            for q in self.quarantined[:10]:
                lines.append(f"    {q}")
            if len(self.quarantined) > 10:
                lines.append(f"    ... and {len(self.quarantined) - 10} more")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class IngestionPipeline:
    """Validates, cross-checks, and accepts or quarantines telemetry records."""

    def __init__(
        self,
        max_staleness_seconds: int = MAX_STALENESS_SECONDS,
        max_soc_change_per_minute: float = MAX_SOC_CHANGE_PER_MINUTE,
        block_real_in_training: bool = True,
        enforce_staleness: bool = True,
    ):
        self.max_staleness_seconds = max_staleness_seconds
        self.max_soc_change_per_minute = max_soc_change_per_minute
        self.block_real_in_training = block_real_in_training
        self.enforce_staleness = enforce_staleness

        self._last_seen: Dict[str, TelemetryRecord] = {}
        self._seen_timestamps: Dict[str, set] = {}

    def reset(self) -> None:
        self._last_seen.clear()
        self._seen_timestamps.clear()

    def ingest(
        self,
        records: List[TelemetryRecord],
        *,
        training: bool = False,
    ) -> IngestionResult:
        result = IngestionResult()
        now_utc = datetime.now(timezone.utc)

        for record in records:
            error = self._validate(record, training=training, now_utc=now_utc)
            if error is not None:
                record.schema_valid = False
                result.quarantined.append(
                    QuarantineEntry(record, error[0], error[1])
                )
            else:
                record.schema_valid = True
                result.accepted.append(record)
                self._update_state(record)

        return result

    # ------------------------------------------------------------------

    def _validate(
        self,
        record: TelemetryRecord,
        *,
        training: bool,
        now_utc: datetime,
    ) -> Optional[Tuple[str, str]]:

        # 1. Field-level schema validation
        try:
            validate_record(record)
        except SchemaError as exc:
            return (exc.code, exc.message)

        # 2. Staleness (flag, but only quarantine if enforcing live staleness)
        age_seconds = (now_utc - record.timestamp).total_seconds()
        if self.enforce_staleness and age_seconds > self.max_staleness_seconds:
            # For historical / batch data we do not enforce; controlled by flag.
            record.stale_data_flag = True

        # 3. Future timestamp
        if age_seconds < -60:
            return ("FUTURE_TIMESTAMP",
                    f"timestamp is {-age_seconds:.0f}s in the future")

        # 4. Duplicate timestamp for same site
        seen = self._seen_timestamps.setdefault(record.site_id, set())
        if record.timestamp.isoformat() in seen:
            return ("DUPLICATE_TIMESTAMP",
                    f"duplicate timestamp {record.timestamp.isoformat()} "
                    f"for site {record.site_id}")

        # 5. Cross-record checks
        prev = self._last_seen.get(record.site_id)
        if prev is not None:
            cross = self._cross_record_checks(prev, record)
            if cross is not None:
                return cross

        # 6. Conflicting readings
        if (record.generator_state == GeneratorState.RUNNING
                and record.grid_status == GridStatus.UP
                and record.battery_soc_pct > 80.0):
            return ("CONFLICTING_READINGS",
                    "generator RUNNING while grid UP and battery SoC > 80 % — "
                    "physically inconsistent; flagged for review")

        # 7. Held-out real data guard
        if training and self.block_real_in_training and record.source == Source.REAL:
            return ("REAL_DATA_IN_TRAINING",
                    "source=Real record blocked from training run "
                    "(held-out validation discipline)")

        return None

    def _cross_record_checks(
        self,
        prev: TelemetryRecord,
        curr: TelemetryRecord,
    ) -> Optional[Tuple[str, str]]:
        delta_seconds = (curr.timestamp - prev.timestamp).total_seconds()

        if delta_seconds < 0:
            return ("OUT_OF_ORDER",
                    f"record timestamp {curr.timestamp.isoformat()} is before "
                    f"previous {prev.timestamp.isoformat()}")
        if delta_seconds == 0:
            return None

        delta_minutes = delta_seconds / 60.0

        # Skip SoC rate check across a flagged sensor dropout (frozen/jumpy)
        if curr.stale_data_flag or prev.stale_data_flag:
            return None

        soc_change = abs(curr.battery_soc_pct - prev.battery_soc_pct)
        soc_rate = soc_change / delta_minutes if delta_minutes > 0 else 0.0
        if soc_rate > self.max_soc_change_per_minute:
            return ("SOC_RATE_VIOLATION",
                    f"battery SoC changed {soc_change:.1f} % in "
                    f"{delta_minutes:.1f} min ({soc_rate:.2f} %/min > max "
                    f"{self.max_soc_change_per_minute} %/min)")

        return None

    def _update_state(self, record: TelemetryRecord) -> None:
        self._last_seen[record.site_id] = record
        self._seen_timestamps.setdefault(record.site_id, set()).add(
            record.timestamp.isoformat()
        )
