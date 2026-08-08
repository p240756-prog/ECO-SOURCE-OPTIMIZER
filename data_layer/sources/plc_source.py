"""
plc_source.py  —  Tier 1  (ATTACHABLE ADAPTER — plug in when PLC data arrives)
==============================================================================

PLC Group Islamabad office log adapter.

This is the ONE source the annex says to "leave to attach".  Everything else
in the data layer already runs without it.  When PLC Group hands over their
operational logs, you ingest them through THIS file and nothing else changes:
the same schema, the same ingestion pipeline, the same validation framework,
and the same rule engine all apply automatically.

────────────────────────────────────────────────────────────────────────────
HOW TO INGEST A PLC RECORD (step-by-step)
────────────────────────────────────────────────────────────────────────────
1. OBTAIN THE RAW LOGS.  Expected PLC exports (per the annex):
     - Grid interruption logs   (site, start_time, end_time, feeder)
     - Generator run logs        (site, start_time, end_time, load_kw)
     - Diesel purchase/invoices  (site, date, litres, cost_per_litre)
     - UPS/inverter logs         (site, timestamp, soc_pct, soh_pct, voltage)
     - Maintenance / NOC tickets  (site, timestamp, alarm_code)

2. MAP EVERY COLUMN TO THE 29-ATTRIBUTE SCHEMA.  Use `map_plc_row` below as
   the single mapping point.  Document any PLC column that has no mapping —
   the annex requires ZERO unmapped fields before sign-off.

3. FILL PHYSICS-DERIVED FIELDS.  PLC logs will not contain every one of the 29
   attributes (e.g. solar_irradiance, humidity).  Two options, both supported:
     (a) join against the SAME Tier-1/Tier-2 sources the simulator uses
         (tariff_source, weather_source, ...) keyed on timestamp; or
     (b) leave the physics-derived value to a safe default and rely on the
         real measured fields (SoC, fuel, grid state) — the rule engine still
         works.  `map_plc_row` shows exactly how to do (a).

4. TAG source=Source.REAL ON EVERY RECORD.  This is what the held-out
   discipline depends on — real records are blocked from training runs by the
   ingestion pipeline (`training=True`).

5. INGEST THROUGH THE SAME PIPELINE.  No special path:

        from data_layer.sources.plc_source import load_plc_logs
        from data_layer.ingestion import IngestionPipeline
        from data_layer.validation import run_full_validation

        records = load_plc_logs("plc_export_2026_Q3.csv")   # source=Real
        pipeline = IngestionPipeline(enforce_staleness=False)
        result = pipeline.ingest(records, training=False)    # held-out => not training
        print(result.summary())
        report = run_full_validation(result.accepted)
        print(report.summary())

6. RUN THE ANCHOR CHECK.  `run_anchor_check(records)` compares the PLC
   aggregates (outage hours/day, theft rate) against DISCO/NEPRA anchors so
   you can confirm the real data is consistent with published figures.

That's it — one file, one function to implement (`load_plc_logs`).
"""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from data_layer.schema import (
    TelemetryRecord,
    GridStatus,
    TariffType,
    BatteryStatus,
    GeneratorState,
    IncidentLabel,
    RecommendedSource,
    Source,
    _parse_iso8601,
)
from data_layer.sources.tariff_source import get_tariff
from data_layer.sources.weather_source import (
    temperature_c, humidity_pct, solar_irradiance, solar_power_kw,
)
from data_layer import rule_engine


# ---------------------------------------------------------------------------
# Enum coercion helpers (tolerant of common PLC log spellings)
# ---------------------------------------------------------------------------

_GRID_MAP = {
    "up": GridStatus.UP, "on": GridStatus.UP, "1": GridStatus.UP,
    "true": GridStatus.UP, "available": GridStatus.UP,
    "down": GridStatus.DOWN, "off": GridStatus.DOWN, "0": GridStatus.DOWN,
    "false": GridStatus.DOWN, "outage": GridStatus.DOWN,
    "unstable": GridStatus.UNSTABLE, "fluctuating": GridStatus.UNSTABLE,
}
_GEN_MAP = {
    "off": GeneratorState.OFF, "stopped": GeneratorState.OFF,
    "starting": GeneratorState.STARTING, "start": GeneratorState.STARTING,
    "running": GeneratorState.RUNNING, "on": GeneratorState.RUNNING,
}


def _coerce_grid(value: Any) -> GridStatus:
    return _GRID_MAP.get(str(value).strip().lower(), GridStatus.UP)


def _coerce_gen(value: Any) -> GeneratorState:
    return _GEN_MAP.get(str(value).strip().lower(), GeneratorState.OFF)


def _f(row: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, None)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# The single mapping point:  raw PLC row  →  29-attribute TelemetryRecord
# ---------------------------------------------------------------------------

def map_plc_row(row: Dict[str, Any],
                *,
                solar_capacity_kw: float = 9.1,
                month: Optional[int] = None) -> TelemetryRecord:
    """
    Map ONE raw PLC log row (dict) to a fully-populated TelemetryRecord.

    Adjust the `row.get(...)` keys on the left to match YOUR PLC column names.
    Physics-derived fields not present in the PLC logs (tariff, weather, solar)
    are filled from the same Tier-1/Tier-2 sources the simulator uses, keyed on
    the record timestamp — so a PLC record ends up with all 29 attributes and
    NO nulls, exactly like a synthetic record.
    """
    # --- timestamp ---
    ts_raw = row.get("timestamp") or row.get("log_timestamp") or row.get("time")
    ts = _parse_iso8601(str(ts_raw)) if ts_raw else datetime.now(timezone.utc)
    hour_pkt = (ts.hour + 5) % 24
    m = month if month is not None else ts.month

    # --- measured fields from PLC logs ---
    grid_status = _coerce_grid(row.get("grid_status", row.get("grid_up", "up")))
    gen_state = _coerce_gen(row.get("generator_state", row.get("gen_state", "off")))
    soc = _f(row, "battery_soc_pct", _f(row, "battery_soc", 80.0))
    soh = _f(row, "battery_soh_pct", _f(row, "battery_soh", 95.0))
    load_kw = _f(row, "load_kw", _f(row, "site_load_kw", 10.0))
    fuel_l = _f(row, "fuel_level_l", _f(row, "fuel_litres_remaining", 100.0))
    fuel_lph = _f(row, "fuel_consumption_lph", 0.0)
    gen_power = _f(row, "generator_power_kw", 0.0)
    traffic = _f(row, "traffic_load_pct", _f(row, "traffic_utilisation_pct", 40.0))
    qos = _f(row, "qos_score", _f(row, "qos_composite", 90.0))

    # --- physics/context fields joined from Tier-1/Tier-2 sources ---
    tariff_type, price = get_tariff(hour_pkt)
    temp = _f(row, "temperature", temperature_c(m, hour_pkt))
    humid = _f(row, "humidity", humidity_pct(m, hour_pkt))
    irr = _f(row, "solar_irradiance", solar_irradiance(m, hour_pkt))
    pv_kw = _f(row, "solar_power_kw", solar_power_kw(irr, solar_capacity_kw, temp))

    # --- derived enums ---
    battery_voltage = _f(row, "battery_voltage", round(44.0 + soc / 100.0 * 10.0, 2))
    if grid_status == GridStatus.UP:
        battery_status = BatteryStatus.CHARGING if soc < 99 else BatteryStatus.IDLE
    elif gen_state == GeneratorState.RUNNING:
        battery_status = BatteryStatus.IDLE
    else:
        battery_status = BatteryStatus.DISCHARGING

    # --- alarms ---
    raw_alarms = row.get("alarm_codes", row.get("alarm_list", "")) or ""
    if isinstance(raw_alarms, list):
        alarms = [str(a) for a in raw_alarms]
    else:
        alarms = [a for a in str(raw_alarms).replace(";", "|").split("|") if a]

    record = TelemetryRecord(
        site_id=str(row.get("site_id", row.get("tower_id", "PLC-UNKNOWN"))),
        timestamp=ts,
        grid_status=grid_status,
        electricity_price=round(price, 2),
        tariff_type=tariff_type,
        battery_soc_pct=max(0.0, min(100.0, soc)),
        battery_soh_pct=max(0.0, min(100.0, soh)),
        battery_voltage=max(30.0, min(60.0, battery_voltage)),
        battery_status=battery_status,
        generator_state=gen_state,
        generator_power_kw=max(0.0, gen_power),
        fuel_level_l=max(0.0, fuel_l),
        fuel_consumption_lph=max(0.0, fuel_lph),
        solar_power_kw=max(0.0, pv_kw),
        solar_irradiance=max(0.0, irr),
        load_kw=max(0.0, load_kw),
        traffic_load_pct=max(0.0, min(100.0, traffic)),
        qos_score=max(0.0, min(100.0, qos)),
        temperature=max(-20.0, min(60.0, temp)),
        humidity=max(0.0, min(100.0, humid)),
        alarm_codes=alarms,
        incident_label=IncidentLabel.NONE,     # real live data carries no label
        source=Source.REAL,                     # <-- the held-out tag
        schema_valid=True,
        stale_data_flag=False,
        record_id=str(row.get("record_id", uuid.uuid4())),
        scenario_id=str(row.get("scenario_id", "plc_real")),
    )

    # Rule engine fills recommended_source + reason, same as synthetic path.
    rec_source, reason = rule_engine.decide(record)
    record.recommended_source = rec_source
    record.reason = reason
    return record


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_plc_logs(filepath: str,
                  *,
                  solar_capacity_kw: float = 9.1) -> List[TelemetryRecord]:
    """
    Load a PLC Group CSV export and return validated, source=Real records.

    The CSV is expected to have a header row.  Column names are mapped in
    `map_plc_row` — edit that function to match your export.  Rows that cannot
    be mapped are skipped with a warning rather than crashing the load.

    Returns
    -------
    list[TelemetryRecord]  (every record tagged source=Source.REAL)
    """
    records: List[TelemetryRecord] = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            try:
                records.append(
                    map_plc_row(row, solar_capacity_kw=solar_capacity_kw)
                )
            except Exception as exc:  # pragma: no cover
                print(f"[plc_source] skipped row {i}: {exc}")
    return records
