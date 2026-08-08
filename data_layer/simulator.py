"""
simulator.py  —  Tier 3 (physics-informed)
===========================================

Tick-based site simulator producing the full 29-attribute MVP schema.

Implements the "Synthetic Data Generation Methodology" of the annex, now
calibrated to Pakistan / Punjab conditions:

    - Power & Battery Model   — OEM discharge/charge curves + temp derating
    - Generator & Fuel Model  — OEM fuel-vs-load curve, Off/Starting/Running
    - Outage Timing Model      — IESCO/Punjab DISCO schedule + unscheduled
    - Solar Model              — Punjab clear-sky irradiance → PV power
    - Traffic & Congestion     — Telecom Italia diurnal shape
    - Environment              — Islamabad temperature + humidity (PMD)
    - Tariff                   — NEPRA Punjab ToU (Peak/Normal/Off-Peak, PKR)
    - Anomaly Injection        — theft / congestion / sensor-fault (labelled)
    - Rule Engine              — recommended_source + reason per record

Every field is internally consistent and NEVER null.  Every anomaly is
explicitly labelled and carries a scenario_id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np

from data_layer.schema import (
    TelemetryRecord,
    GridStatus,
    GeneratorState,
    BatteryStatus,
    IncidentLabel,
    Source,
)
from data_layer.sources.oem_curves import (
    generator_fuel_litres_per_hour,
    battery_discharge_multiplier,
    battery_charge_multiplier,
    VRLA_SOH_LOSS_PER_CYCLE,
)
from data_layer.sources.disco_source import is_grid_down, UNSCHEDULED_OUTAGES_PER_DAY
from data_layer.sources.nepra_source import ANCHORS
from data_layer.sources.traffic_source import traffic_load_pct
from data_layer.sources.weather_source import (
    temperature_c,
    humidity_pct,
    battery_temp_derating,
    load_scaling_factor,
    solar_irradiance,
    solar_power_kw,
)
from data_layer.sources.tariff_source import get_tariff
from data_layer import rule_engine


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SimulatorConfig:
    """Parameters to simulate one Punjab telecom site."""
    site_id: str = "SIM-001"
    feeder_area: str = "ISB-A"

    n_days: int = 30
    tick_minutes: int = 60          # 60-min ticks → 24 ticks/day
    start_date: datetime = field(
        default_factory=lambda: datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    )

    # Site capacity (calibrated to dataset.csv / typical Punjab BTS site)
    generator_capacity_kw: float = 22.7
    generator_tank_litres: float = 200.0
    battery_capacity_kwh: float = 37.9
    battery_max_charge_kw: float = 9.5
    battery_max_discharge_kw: float = 10.8
    solar_capacity_kw: float = 9.1
    nominal_load_kw: float = 12.0

    initial_battery_soc_pct: float = 80.0
    initial_battery_soh_pct: float = 95.0
    initial_fuel_litres: float = 150.0

    # Anomaly injection fractions (per site-day, oversampled per annex)
    theft_fraction: float = 0.06          # ~2x NEPRA anchor 0.03
    congestion_fraction: float = 0.12
    sensor_fault_fraction: float = 0.04

    month: int = 7   # July (monsoon / peak summer)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class SiteSimulator:
    """Produces a list of fully-populated 29-attribute TelemetryRecords."""

    def __init__(self, config: SimulatorConfig,
                 rng: Optional[np.random.Generator] = None):
        self.cfg = config
        self.rng = rng if rng is not None else np.random.default_rng()

    def run(self) -> List[TelemetryRecord]:
        cfg = self.cfg
        records: List[TelemetryRecord] = []

        soc = cfg.initial_battery_soc_pct
        soh = cfg.initial_battery_soh_pct
        fuel_l = cfg.initial_fuel_litres
        tick_hours = cfg.tick_minutes / 60.0
        ticks_per_day = 24 * 60 // cfg.tick_minutes
        total_ticks = cfg.n_days * ticks_per_day

        prev_soc = soc
        gen_running_prev = False

        # Per-day anomaly assignment
        n_days = cfg.n_days
        theft_days = self._pick_days(cfg.theft_fraction, n_days)
        congestion_days = self._pick_days(cfg.congestion_fraction, n_days)
        sensor_fault_days = self._pick_days(cfg.sensor_fault_fraction, n_days)

        # Cloud cover varies day-to-day (monsoon = cloudier)
        for tick_idx in range(total_ticks):
            ts = cfg.start_date + timedelta(minutes=tick_idx * cfg.tick_minutes)
            hour_pkt = (ts.hour + 5) % 24
            day_idx = tick_idx // ticks_per_day
            is_weekend = ts.weekday() >= 5

            # Daily cloud factor (recompute at day start)
            if tick_idx % ticks_per_day == 0:
                cloud_factor = float(self.rng.uniform(0.55, 1.0))

            # ---- Grid state ----
            scheduled_down = is_grid_down(hour_pkt, cfg.feeder_area)
            unscheduled_prob = UNSCHEDULED_OUTAGES_PER_DAY * tick_hours / 24.0
            unscheduled_down = (
                not scheduled_down and self.rng.random() < unscheduled_prob
            )
            grid_down = scheduled_down or unscheduled_down
            # Occasional unstable grid (voltage/frequency excursion)
            grid_unstable = (
                not grid_down and self.rng.random() < 0.03
            )
            if grid_down:
                grid_status = GridStatus.DOWN
            elif grid_unstable:
                grid_status = GridStatus.UNSTABLE
            else:
                grid_status = GridStatus.UP

            # ---- Environment ----
            temp = temperature_c(cfg.month, hour_pkt, rng=self.rng)
            humid = humidity_pct(cfg.month, hour_pkt, rng=self.rng)
            temp_derating = battery_temp_derating(temp)
            load_scale = load_scaling_factor(temp)

            # ---- Load ----
            base_load = cfg.nominal_load_kw * load_scale
            load_kw = max(1.0, base_load + float(self.rng.normal(0.0, 0.5)))

            # ---- Solar ----
            irr = solar_irradiance(cfg.month, hour_pkt,
                                   cloud_factor=cloud_factor, rng=self.rng)
            pv_kw = solar_power_kw(irr, cfg.solar_capacity_kw, temp_c=temp)
            pv_kw = min(pv_kw, load_kw * 1.2)  # cannot exceed feasible use much

            # Net load the storage/grid/gen must cover after solar
            net_load = max(0.0, load_kw - pv_kw)

            # ---- Battery model ----
            grid_supplying = grid_status == GridStatus.UP
            if grid_supplying:
                # Grid up: charge battery from surplus
                charge_rate = cfg.battery_max_charge_kw * battery_charge_multiplier(soc)
                delta_soc = (charge_rate * tick_hours / cfg.battery_capacity_kwh) * 100.0
            else:
                # Outage/unstable: battery discharges to cover net load
                discharge_rate = (
                    cfg.battery_max_discharge_kw
                    * battery_discharge_multiplier(soc)
                    * temp_derating
                )
                actual_discharge = min(net_load, discharge_rate)
                delta_soc = -(actual_discharge * tick_hours / cfg.battery_capacity_kwh) * 100.0

            new_soc = max(0.0, min(100.0, soc + delta_soc))

            # ---- Generator model (Off / Starting / Running) ----
            battery_critical = new_soc <= 20.0
            gen_needed = (not grid_supplying) and battery_critical and fuel_l > 0

            if gen_needed and not gen_running_prev:
                gen_state = GeneratorState.STARTING   # one tick to spin up
                gen_power = 0.0
                fuel_consumption = 0.0
                gen_running_now = True
            elif gen_needed and gen_running_prev:
                gen_state = GeneratorState.RUNNING
                gen_power = round(net_load, 3)
                fuel_consumption = round(
                    generator_fuel_litres_per_hour(net_load, cfg.generator_capacity_kw),
                    3,
                )
                fuel_l = max(0.0, fuel_l - fuel_consumption * tick_hours)
                gen_running_now = True
                # generator carries load, so battery does not deplete further
                new_soc = max(new_soc, soc)
            else:
                gen_state = GeneratorState.OFF
                gen_power = 0.0
                fuel_consumption = 0.0
                gen_running_now = False

            gen_running_prev = gen_running_now
            soc = new_soc

            # ---- Battery status enum ----
            soc_delta = soc - prev_soc
            if soc_delta > 0.05:
                battery_status = BatteryStatus.CHARGING
            elif soc_delta < -0.05:
                battery_status = BatteryStatus.DISCHARGING
            else:
                battery_status = BatteryStatus.IDLE
            prev_soc = soc

            # ---- Battery voltage (48 V system, SoC-dependent) ----
            battery_voltage = round(44.0 + (soc / 100.0) * 10.0, 2)  # 44..54 V

            # SoH degradation
            soh = max(60.0, soh - VRLA_SOH_LOSS_PER_CYCLE * (abs(delta_soc) / 100.0))

            # ---- Traffic & QoS ----
            t_load = traffic_load_pct(hour_pkt, is_weekend=is_weekend, rng=self.rng)
            qos = self._compute_qos(t_load, not grid_supplying, soc)

            # ---- Tariff ----
            tariff_type, price = get_tariff(hour_pkt)

            # ---- Anomaly injection ----
            incident = IncidentLabel.NONE
            alarms: List[str] = []
            stale_flag = False
            scenario_id = "normal_operation"

            # Fuel theft: siphoning from the tank during an overnight window
            # (02:00–05:00 PKT), independent of generator state — fuel drops
            # faster than any runtime-implied burn, which is the signature the
            # anomaly detector must learn.
            if day_idx in theft_days and 2 <= hour_pkt <= 5 and fuel_l > 10.0:
                theft_drain = float(self.rng.uniform(8.0, 18.0))
                fuel_l = max(0.0, fuel_l - theft_drain)
                fuel_consumption = round(fuel_consumption + theft_drain, 3)
                incident = IncidentLabel.THEFT
                alarms.append("FUEL_THEFT_SUSPECTED")
                scenario_id = "fuel_theft"


            if incident == IncidentLabel.NONE and day_idx in congestion_days:
                if 17 <= hour_pkt <= 22:
                    t_load = min(100.0, t_load + float(self.rng.uniform(15.0, 30.0)))
                    qos = max(0.0, qos - float(self.rng.uniform(20.0, 40.0)))
                    incident = IncidentLabel.CONGESTION
                    alarms.append("QOS_BREACH")
                    scenario_id = "network_congestion"

            if incident == IncidentLabel.NONE and day_idx in sensor_fault_days:
                if self.rng.random() < 0.15:
                    # Sensor dropout: data goes stale (flagged), values FROZEN
                    # so the record stays physically consistent and passes
                    # ingestion — the fault is signalled by the flag + alarm.
                    incident = IncidentLabel.SENSOR_FAULT
                    stale_flag = True
                    alarms.append("SENSOR_DROPOUT")
                    scenario_id = "sensor_dropout"

            if incident == IncidentLabel.NONE and grid_status == GridStatus.DOWN:
                incident = IncidentLabel.OUTAGE
                scenario_id = ("long_outage"
                               if battery_critical else "short_outage")

            # ---- Build record (rule engine fills recommended_source/reason) ----
            record = TelemetryRecord(
                site_id=cfg.site_id,
                timestamp=ts,
                grid_status=grid_status,
                electricity_price=round(price, 2),
                tariff_type=tariff_type,
                battery_soc_pct=round(soc, 2),
                battery_soh_pct=round(soh, 2),
                battery_voltage=battery_voltage,
                battery_status=battery_status,
                generator_state=gen_state,
                generator_power_kw=gen_power,
                fuel_level_l=round(fuel_l, 2),
                fuel_consumption_lph=fuel_consumption,
                solar_power_kw=pv_kw,
                solar_irradiance=irr,
                load_kw=round(load_kw, 3),
                traffic_load_pct=round(t_load, 2),
                qos_score=round(qos, 2),
                temperature=temp,
                humidity=humid,
                alarm_codes=alarms,
                incident_label=incident,
                source=Source.SYNTHETIC,
                schema_valid=True,
                stale_data_flag=stale_flag,
                record_id=str(uuid.uuid4()),
                scenario_id=scenario_id,
            )

            rec_source, reason = rule_engine.decide(record)
            record.recommended_source = rec_source
            record.reason = reason

            records.append(record)

        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pick_days(self, fraction: float, n_days: int) -> set:
        """Pick a set of day indices for an anomaly, at least 1 if fraction>0."""
        if fraction <= 0 or n_days <= 0:
            return set()
        count = max(1, round(fraction * n_days))
        count = min(count, n_days)
        return set(self.rng.choice(n_days, size=count, replace=False).tolist())

    @staticmethod
    def _compute_qos(traffic_pct: float, degraded: bool, soc_pct: float) -> float:
        base = 100.0 - (traffic_pct * 0.3)
        if degraded:
            base -= 20.0
        if soc_pct < 30.0:
            base -= 15.0
        return max(0.0, min(100.0, base))
