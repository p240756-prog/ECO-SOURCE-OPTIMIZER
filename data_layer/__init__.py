"""
data_layer
==========

Data Acquisition & Validation Strategy implementation for the
AI-Native Telecom Infrastructure Intelligence Platform.

Implements the Week-1 "data foundation":

    Tier 1  Real-world reference data (PLC logs, DISCO, NEPRA/PTA, OEM, tariff)
    Tier 2  Public / open reference datasets (NASA battery, weather, traffic)
    Tier 3  Physics-informed synthetic generation (tick-based simulator)

Everything a source produces is normalised to the 29-attribute MVP schema
(`data_layer.schema.TelemetryRecord`) before it reaches the backend.

The PLC source (`data_layer.sources.plc_source`) is an attachable adapter stub
— see its docstring for how to plug real PLC records in when they arrive.
"""

from data_layer.schema import (
    TelemetryRecord,
    GridStatus,
    TariffType,
    BatteryStatus,
    GeneratorState,
    IncidentLabel,
    RecommendedSource,
    Source,
    validate_record,
    SchemaError,
    SCHEMA_COLUMNS,
)

__all__ = [
    "TelemetryRecord",
    "GridStatus",
    "TariffType",
    "BatteryStatus",
    "GeneratorState",
    "IncidentLabel",
    "RecommendedSource",
    "Source",
    "validate_record",
    "SchemaError",
    "SCHEMA_COLUMNS",
]
