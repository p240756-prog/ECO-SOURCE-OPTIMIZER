"""
schema.py
=========

MVP Backend Dataset Schema — 29 attributes.

Direct, enforceable implementation of the "AI-Native Telecom Infrastructure
Intelligence Platform — MVP Backend Dataset Schema" (29 final attributes).

Every record — real or synthetic — is written to this schema before it reaches
the backend, so the rule engine and models never need to know whether a record
came from a PLC log or the simulator.

Guarantee: after `validate_record` passes, NO field is null or empty.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Any, Dict


# ----------------------------------------------------------------------------
# Enumerations (exact labels from the MVP schema spec)
# ----------------------------------------------------------------------------

class GridStatus(str, Enum):
    UP = "Up"
    DOWN = "Down"
    UNSTABLE = "Unstable"


class TariffType(str, Enum):
    PEAK = "Peak"
    OFF_PEAK = "Off-Peak"
    NORMAL = "Normal"


class BatteryStatus(str, Enum):
    CHARGING = "Charging"
    DISCHARGING = "Discharging"
    IDLE = "Idle"


class GeneratorState(str, Enum):
    OFF = "Off"
    STARTING = "Starting"
    RUNNING = "Running"


class IncidentLabel(str, Enum):
    NONE = "None"
    OUTAGE = "Outage"
    THEFT = "Theft"
    CONGESTION = "Congestion"
    SENSOR_FAULT = "Sensor_Fault"


class RecommendedSource(str, Enum):
    SOLAR = "Solar"
    GRID = "Grid"
    BATTERY = "Battery"
    GENERATOR = "Generator"


class Source(str, Enum):
    REAL = "Real"
    SYNTHETIC = "Synthetic"


# ----------------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------------

class SchemaError(Exception):
    """Raised when a record violates the telemetry schema (typed code)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


# ----------------------------------------------------------------------------
# The canonical telemetry record — all 29 attributes
# ----------------------------------------------------------------------------

@dataclass
class TelemetryRecord:
    """One per-site, per-tick record covering all 29 MVP attributes."""

    # 1-2  Site information
    site_id: str
    timestamp: datetime                       # ISO 8601, UTC

    # 3-5  Grid information
    grid_status: GridStatus
    electricity_price: float                  # PKR / kWh (Punjab tariff)
    tariff_type: TariffType

    # 6-9  Battery system
    battery_soc_pct: float                    # 0..100
    battery_soh_pct: float                    # 0..100
    battery_voltage: float                    # V (48 V system nominal)
    battery_status: BatteryStatus

    # 10-13  Generator system
    generator_state: GeneratorState
    generator_power_kw: float
    fuel_level_l: float
    fuel_consumption_lph: float

    # 14-15  Solar system
    solar_power_kw: float
    solar_irradiance: float                   # W/m^2

    # 16  Site load
    load_kw: float

    # 17-18  Network
    traffic_load_pct: float                   # 0..100
    qos_score: float                          # 0..100

    # 19-20  Environmental conditions
    temperature: float                        # deg C
    humidity: float                           # 0..100 %

    # 21  Alarm information
    alarm_codes: List[str] = field(default_factory=list)

    # 22  Incident label (training/test)
    incident_label: IncidentLabel = IncidentLabel.NONE

    # 23-24  Rule engine output
    recommended_source: RecommendedSource = RecommendedSource.GRID
    reason: str = "default"

    # 25-27  Data metadata
    source: Source = Source.SYNTHETIC
    schema_valid: bool = True
    stale_data_flag: bool = False

    # 28-29  Record metadata
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario_id: str = "normal"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.astimezone(timezone.utc).isoformat()
        d["grid_status"] = self.grid_status.value
        d["tariff_type"] = self.tariff_type.value
        d["battery_status"] = self.battery_status.value
        d["generator_state"] = self.generator_state.value
        d["incident_label"] = self.incident_label.value
        d["recommended_source"] = self.recommended_source.value
        d["source"] = self.source.value
        return d


# ----------------------------------------------------------------------------
# Field-level validation (single record) — guarantees no null / empty field
# ----------------------------------------------------------------------------

def validate_record(record: TelemetryRecord) -> None:
    """Enforce every field-level rule. Raises SchemaError on first violation."""

    # 1 site_id
    if not record.site_id or not isinstance(record.site_id, str):
        raise SchemaError("BAD_SITE_ID", "site_id must be a non-empty string")

    # 2 timestamp
    if not isinstance(record.timestamp, datetime):
        raise SchemaError("BAD_TIMESTAMP", "timestamp must be a datetime")
    if record.timestamp.tzinfo is None:
        raise SchemaError("NAIVE_TIMESTAMP", "timestamp must be tz-aware (UTC)")

    # 3 grid_status
    if not isinstance(record.grid_status, GridStatus):
        raise SchemaError("BAD_GRID_STATUS", "grid_status must be a GridStatus")

    # 4 electricity_price
    if record.electricity_price is None or record.electricity_price <= 0:
        raise SchemaError("BAD_PRICE", "electricity_price must be > 0")

    # 5 tariff_type
    if not isinstance(record.tariff_type, TariffType):
        raise SchemaError("BAD_TARIFF", "tariff_type must be a TariffType")

    # 6 battery_soc_pct, 7 battery_soh_pct
    _check_pct("battery_soc_pct", record.battery_soc_pct)
    _check_pct("battery_soh_pct", record.battery_soh_pct)

    # 8 battery_voltage
    if record.battery_voltage is None or not (30.0 <= record.battery_voltage <= 60.0):
        raise SchemaError("BAD_VOLTAGE",
                          "battery_voltage must be within 30..60 V")

    # 9 battery_status
    if not isinstance(record.battery_status, BatteryStatus):
        raise SchemaError("BAD_BATTERY_STATUS",
                          "battery_status must be a BatteryStatus")

    # 10 generator_state
    if not isinstance(record.generator_state, GeneratorState):
        raise SchemaError("BAD_GENERATOR_STATE",
                          "generator_state must be a GeneratorState")

    # 11 generator_power_kw
    _check_nonneg("generator_power_kw", record.generator_power_kw)

    # 12 fuel_level_l
    _check_nonneg("fuel_level_l", record.fuel_level_l)

    # 13 fuel_consumption_lph
    _check_nonneg("fuel_consumption_lph", record.fuel_consumption_lph)

    # 14 solar_power_kw
    _check_nonneg("solar_power_kw", record.solar_power_kw)

    # 15 solar_irradiance
    _check_nonneg("solar_irradiance", record.solar_irradiance)

    # 16 load_kw
    if record.load_kw is None or record.load_kw < 0:
        raise SchemaError("BAD_LOAD", "load_kw must be non-negative")

    # 17 traffic_load_pct, 18 qos_score
    _check_pct("traffic_load_pct", record.traffic_load_pct)
    _check_pct("qos_score", record.qos_score)

    # 19 temperature
    if record.temperature is None or not (-20.0 <= record.temperature <= 60.0):
        raise SchemaError("BAD_TEMPERATURE",
                          "temperature must be within -20..60 C")

    # 20 humidity
    _check_pct("humidity", record.humidity)

    # 21 alarm_codes — empty list ok, null NOT ok
    if record.alarm_codes is None:
        raise SchemaError("NULL_ALARM_CODES",
                          "alarm_codes must not be null (use empty array)")
    if not isinstance(record.alarm_codes, list) or not all(
        isinstance(a, str) for a in record.alarm_codes
    ):
        raise SchemaError("BAD_ALARM_CODES",
                          "alarm_codes must be an array of strings")

    # 22 incident_label
    if not isinstance(record.incident_label, IncidentLabel):
        raise SchemaError("BAD_INCIDENT_LABEL",
                          "incident_label must be an IncidentLabel")

    # 23 recommended_source
    if not isinstance(record.recommended_source, RecommendedSource):
        raise SchemaError("BAD_RECOMMENDED_SOURCE",
                          "recommended_source must be a RecommendedSource")

    # 24 reason
    if not record.reason or not isinstance(record.reason, str):
        raise SchemaError("BAD_REASON", "reason must be a non-empty string")

    # 25 source
    if not isinstance(record.source, Source):
        raise SchemaError("BAD_SOURCE", "source must be Real or Synthetic")

    # 26 schema_valid, 27 stale_data_flag
    if not isinstance(record.schema_valid, bool):
        raise SchemaError("BAD_SCHEMA_VALID", "schema_valid must be bool")
    if not isinstance(record.stale_data_flag, bool):
        raise SchemaError("BAD_STALE_FLAG", "stale_data_flag must be bool")

    # 28 record_id
    if not record.record_id or not isinstance(record.record_id, str):
        raise SchemaError("BAD_RECORD_ID", "record_id must be a non-empty string")

    # 29 scenario_id
    if not record.scenario_id or not isinstance(record.scenario_id, str):
        raise SchemaError("BAD_SCENARIO_ID",
                          "scenario_id must be a non-empty string")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _check_pct(name: str, value: Any) -> None:
    if value is None:
        raise SchemaError("NULL_PCT", f"{name} must not be null")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise SchemaError("BAD_PCT", f"{name} must be numeric")
    if not (0.0 <= v <= 100.0):
        raise SchemaError("PCT_OUT_OF_RANGE", f"{name}={v} outside 0..100")


def _check_nonneg(name: str, value: Any) -> None:
    if value is None or value < 0:
        raise SchemaError("BAD_VALUE", f"{name} must be non-negative")


def _parse_iso8601(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError as exc:
        raise SchemaError("BAD_TIMESTAMP",
                          f"cannot parse timestamp '{value}'") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# Ordered schema columns for CSV export (all 29 attributes).
SCHEMA_COLUMNS = [
    "site_id",
    "timestamp",
    "grid_status",
    "electricity_price",
    "tariff_type",
    "battery_soc_pct",
    "battery_soh_pct",
    "battery_voltage",
    "battery_status",
    "generator_state",
    "generator_power_kw",
    "fuel_level_l",
    "fuel_consumption_lph",
    "solar_power_kw",
    "solar_irradiance",
    "load_kw",
    "traffic_load_pct",
    "qos_score",
    "temperature",
    "humidity",
    "alarm_codes",
    "incident_label",
    "recommended_source",
    "reason",
    "source",
    "schema_valid",
    "stale_data_flag",
    "record_id",
    "scenario_id",
]
