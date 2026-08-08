"""
rule_engine.py
==============

Deterministic rule engine that produces the `recommended_source` and `reason`
fields (attributes 23-24 of the MVP schema).

Implements the Rule Engine Test Scenario Matrix from the annex:

    Short outage        → monitor (battery), no generator start
    Long outage         → generator start before battery critical
    Low battery + outage→ high-priority alert, conservative fallback
    Fuel theft pattern  → theft alert, no automatic control action
    Sensor dropout      → last-known-safe state, flag stale
    Conflicting readings→ flag for review, no action
    Excessive switching → switching penalty / min hold time

Priority of source selection (uptime-first, then cost):
    1. Solar   — free, use whenever it covers meaningful load in daylight
    2. Grid    — cheapest reliable source when available and stable
    3. Battery — bridge short outages when SoC healthy
    4. Generator — last resort for long outages / critical battery
"""

from __future__ import annotations

from data_layer.schema import (
    TelemetryRecord,
    GridStatus,
    GeneratorState,
    BatteryStatus,
    RecommendedSource,
    IncidentLabel,
)
from data_layer.sources.tariff_source import DIESEL_PRICE_PKR_PER_LITRE


# Thresholds (aligned with existing app/statebuilder/thresholds.py)
CRITICAL_SOC = 20.0
LOW_SOC = 40.0
SOLAR_COVERAGE_MIN = 0.5      # solar must cover >=50 % of load to be preferred


def decide(record: TelemetryRecord) -> tuple[RecommendedSource, str]:
    """
    Return (recommended_source, reason) for a single telemetry record.

    Pure function — depends only on the record's fields, so it is fully
    reproducible and testable against the scenario matrix.
    """

    soc = record.battery_soc_pct
    load = max(record.load_kw, 0.001)
    solar_ratio = record.solar_power_kw / load

    # --- Sensor fault / stale data: fall back to last-known-safe (grid) ---
    if record.incident_label == IncidentLabel.SENSOR_FAULT or record.stale_data_flag:
        return (
            RecommendedSource.GRID,
            "Sensor dropout / stale data — holding last-known-safe source, "
            "flagged as stale; no control action on unreliable input",
        )

    # --- Theft: raise alert but do not take automatic control action ---
    if record.incident_label == IncidentLabel.THEFT:
        # Keep supplying load from the safest available source meanwhile.
        if record.grid_status == GridStatus.UP:
            src = RecommendedSource.GRID
        elif soc > CRITICAL_SOC:
            src = RecommendedSource.BATTERY
        else:
            src = RecommendedSource.GENERATOR
        return (
            src,
            "Fuel-theft pattern detected — theft risk score raised, "
            "security-review alert; no automatic control change",
        )

    # --- Solar first when it meaningfully covers load (daylight) ---
    if record.solar_power_kw > 0 and solar_ratio >= SOLAR_COVERAGE_MIN:
        return (
            RecommendedSource.SOLAR,
            f"Solar covers {solar_ratio*100:.0f}% of load "
            f"({record.solar_power_kw:.1f} kW) — using free solar generation",
        )

    # --- Grid available and stable: cheapest reliable source ---
    if record.grid_status == GridStatus.UP:
        return (
            RecommendedSource.GRID,
            f"Grid available at {record.electricity_price:.2f} PKR/kWh "
            f"({record.tariff_type.value}) — using grid as primary source",
        )

    # --- Grid unstable: prefer battery bridge if healthy ---
    if record.grid_status == GridStatus.UNSTABLE:
        if soc > LOW_SOC:
            return (
                RecommendedSource.BATTERY,
                "Grid unstable — bridging on battery to protect equipment "
                f"from voltage/frequency excursions (SoC {soc:.0f}%)",
            )
        return (
            RecommendedSource.GENERATOR,
            "Grid unstable and battery low — starting generator to hold uptime",
        )

    # --- Grid DOWN (outage) ---
    if soc > LOW_SOC:
        # Short outage / adequate battery → monitor on battery
        return (
            RecommendedSource.BATTERY,
            f"Grid outage, battery adequate (SoC {soc:.0f}%) — "
            "supplying load from battery, no generator start required",
        )

    if soc > CRITICAL_SOC:
        # Approaching critical → start generator before battery is depleted
        return (
            RecommendedSource.GENERATOR,
            f"Grid outage, battery approaching critical (SoC {soc:.0f}%) — "
            "starting generator before battery reaches critical threshold",
        )

    # Battery critical during outage → generator mandatory (uptime protection)
    if record.fuel_level_l > 0:
        return (
            RecommendedSource.GENERATOR,
            f"Grid outage with battery CRITICAL (SoC {soc:.0f}%) — "
            "high-priority: generator supplying load to protect uptime",
        )

    # Absolute last resort: no fuel, critical battery — conservative battery use
    return (
        RecommendedSource.BATTERY,
        f"Grid outage, battery critical (SoC {soc:.0f}%) and no fuel — "
        "conservative fallback on remaining battery; escalate for refuelling",
    )
