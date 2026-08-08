"""
oem_curves.py  —  Tier 1
========================

OEM datasheet curves for generator fuel consumption and battery discharge.

These are the physics anchors used by the Tier-3 simulator so that battery
drain and fuel burn follow real OEM curves rather than flat assumptions.

Sources (annex Tier 1):
    Generator  — Cummins / FG Wilson fuel-vs-load tables (typical values)
    Battery    — Industrial 24V VRLA (12 × 2V cells) OEM datasheets
                 (Narada 12NDT-200, CSB GPL12520, Sacred Sun FCP-200)

All values are calibrated for a 24V nominal VRLA string (12 cells in
series, 2.0V nominal per cell).
"""

from __future__ import annotations
from typing import Dict


# ---------------------------------------------------------------------------
# Generator: fuel consumption (litres / hour) at a given load fraction
# ---------------------------------------------------------------------------
# Derived from Cummins C22D5 / FG Wilson P22-6 datasheet fuel tables.
# load_fraction = load_kw / generator_capacity_kw  (0.0 – 1.0)
# Interpolated linearly between the anchor points below.

_GENERATOR_FUEL_CURVE: Dict[float, float] = {
    0.00: 1.5,   # idle / no-load
    0.25: 2.8,
    0.50: 4.5,
    0.75: 6.3,
    1.00: 8.2,   # full rated load
}


def generator_fuel_litres_per_hour(load_kw: float,
                                   capacity_kw: float = 22.7) -> float:
    """
    Return fuel consumption (L/h) for a generator running at `load_kw`.

    Uses linear interpolation between OEM anchor points.
    Clamps load_fraction to [0, 1].
    """
    if capacity_kw <= 0:
        return 0.0
    frac = max(0.0, min(1.0, load_kw / capacity_kw))
    return _interpolate(_GENERATOR_FUEL_CURVE, frac)


# ---------------------------------------------------------------------------
# 24V VRLA Battery: Open-Circuit Voltage (OCV) vs State of Charge
# ---------------------------------------------------------------------------
# Industrial VRLA, 12 cells × 2V nominal = 24V system.
# OCV is measured after 2-4 hours rest at 25°C.
#
# Reference datasheets:
#   Narada 12NDT-200, CSB GPL12520, Sacred Sun FCP-200
#   Cross-validated with IEEE 1188-2005 Table B.1 (VRLA cells)
#
# Per-cell OCV (V)  ×  12 cells  =  String OCV (V)
#   2.15 V/cell × 12 = 25.80 V   (100% SoC — freshly charged, rested)
#   2.12 V/cell × 12 = 25.44 V   ( 90% SoC)
#   2.08 V/cell × 12 = 24.96 V   ( 75% SoC)
#   2.04 V/cell × 12 = 24.48 V   ( 50% SoC)
#   2.00 V/cell × 12 = 24.00 V   ( 25% SoC — nominal voltage)
#   1.96 V/cell × 12 = 23.52 V   ( 10% SoC — deep discharge warning)
#   1.80 V/cell × 12 = 21.60 V   (  0% SoC — end of discharge cutoff)
#
# SoC key is 0..100 (percentage), value is OCV in volts.

_VRLA_24V_OCV: Dict[float, float] = {
    0.0:   21.60,   # 1.80 V/cell — absolute cutoff
    5.0:   22.20,   # 1.85 V/cell
    10.0:  23.04,   # 1.92 V/cell
    20.0:  23.52,   # 1.96 V/cell
    30.0:  23.88,   # 1.99 V/cell
    40.0:  24.12,   # 2.01 V/cell
    50.0:  24.48,   # 2.04 V/cell
    60.0:  24.72,   # 2.06 V/cell
    70.0:  24.84,   # 2.07 V/cell
    80.0:  25.08,   # 2.09 V/cell
    90.0:  25.44,   # 2.12 V/cell
    95.0:  25.62,   # 2.135 V/cell
    100.0: 25.80,   # 2.15 V/cell
}


def battery_ocv_24v(soc_pct: float) -> float:
    """
    Return the 24V VRLA string open-circuit voltage for a given SoC (0–100).

    Uses piecewise-linear interpolation of the OEM OCV curve.
    """
    return _interpolate(_VRLA_24V_OCV, max(0.0, min(100.0, soc_pct)))


# Internal resistance of a 24V VRLA string (ohms).
# Typical new: ~30 mΩ; aged (SoH 80%): ~50 mΩ.
# Used to model voltage sag under discharge and rise under charge.
_INTERNAL_RESISTANCE_NEW_OHMS = 0.030
_INTERNAL_RESISTANCE_AGED_OHMS = 0.055


def battery_voltage_24v(soc_pct: float, current_a: float,
                        soh_pct: float = 95.0) -> float:
    """
    Return terminal voltage of a 24V VRLA string under load or charge.

    Parameters
    ----------
    soc_pct   : float  0–100 state of charge
    current_a : float  positive = discharging, negative = charging
    soh_pct   : float  state of health (affects internal resistance)

    Returns
    -------
    float  Terminal voltage in volts.
           Charging:     V_terminal = V_ocv + |I| × R_int  (voltage rises)
           Discharging:  V_terminal = V_ocv - |I| × R_int  (voltage sags)
           Idle:         V_terminal = V_ocv
    """
    ocv = battery_ocv_24v(soc_pct)

    # Internal resistance increases as battery ages (linear model)
    soh_frac = max(0.6, min(1.0, soh_pct / 100.0))
    r_int = _INTERNAL_RESISTANCE_NEW_OHMS + (
        (_INTERNAL_RESISTANCE_AGED_OHMS - _INTERNAL_RESISTANCE_NEW_OHMS)
        * (1.0 - soh_frac) / 0.4   # 0.4 = range from 1.0 to 0.6
    )

    # Voltage = OCV - I × R (convention: I > 0 = discharge → V drops)
    v_terminal = ocv - current_a * r_int

    # Clamp: charging cannot exceed absorption voltage (2.40 V/cell × 12)
    # Discharge cannot go below cutoff (1.75 V/cell × 12)
    v_terminal = max(21.00, min(28.80, v_terminal))

    return round(v_terminal, 2)


def max_achievable_soc(soh_pct: float) -> float:
    """
    Return the maximum SoC (%) a degraded battery can reach.

    A VRLA battery with SoH < 100% has reduced usable capacity.
    The charger still sees "full" at the absorption voltage, but the
    actual stored energy is less.  In practice:
      - SoH 95% → max SoC ≈ 97%
      - SoH 90% → max SoC ≈ 94%
      - SoH 85% → max SoC ≈ 91%
      - SoH 80% → max SoC ≈ 87%
      - SoH 75% → max SoC ≈ 83%

    Never reaches 100% due to float-charge inefficiency + sulfation.
    """
    # Base cap: even a new VRLA under float barely reaches 97-98%
    base_cap = 97.0
    # SoH derate: each 1% SoH loss reduces max SoC by ~0.65%
    derate = (100.0 - soh_pct) * 0.65
    return max(50.0, base_cap - derate)


# ---------------------------------------------------------------------------
# Battery: discharge rate modifier at a given SoC
# ---------------------------------------------------------------------------
# VRLA cells deliver less usable capacity at very low SoC.
# This curve returns a multiplier (0–1) applied to the nominal discharge kW.
# Anchored to industrial VRLA datasheets (e.g. Narada, CSB).

_BATTERY_DISCHARGE_CURVE: Dict[float, float] = {
    0.00: 0.0,   # empty — no discharge
    0.10: 0.5,   # near-empty — derate heavily
    0.20: 0.80,
    0.40: 0.95,
    0.60: 1.00,
    0.80: 1.00,
    1.00: 1.00,
}


def battery_discharge_multiplier(soc_pct: float) -> float:
    """
    Return a discharge-rate multiplier [0, 1] for the given SoC (0–100).

    Multiply the nominal max-discharge-kW by this value to get the
    physically achievable discharge rate at the current SoC.
    """
    frac = max(0.0, min(1.0, soc_pct / 100.0))
    return _interpolate(_BATTERY_DISCHARGE_CURVE, frac)


# ---------------------------------------------------------------------------
# Battery: charge rate modifier at a given SoC
# ---------------------------------------------------------------------------
# Charging slows as the battery approaches full (CC/CV profile).

_BATTERY_CHARGE_CURVE: Dict[float, float] = {
    0.00: 1.00,
    0.50: 1.00,
    0.80: 0.80,
    0.90: 0.50,
    0.95: 0.25,
    1.00: 0.05,
}


def battery_charge_multiplier(soc_pct: float) -> float:
    """
    Return a charge-rate multiplier [0, 1] for the given SoC (0–100).
    """
    frac = max(0.0, min(1.0, soc_pct / 100.0))
    return _interpolate(_BATTERY_CHARGE_CURVE, frac)


# ---------------------------------------------------------------------------
# Battery: SoH degradation per full cycle
# ---------------------------------------------------------------------------
# Typical VRLA: ~500 cycles to 80 % SoH.  Lithium: ~2000 cycles.
# Default is VRLA.

VRLA_SOH_LOSS_PER_CYCLE = (100.0 - 80.0) / 500.0   # % per cycle
LITHIUM_SOH_LOSS_PER_CYCLE = (100.0 - 80.0) / 2000.0


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _interpolate(curve: Dict[float, float], x: float) -> float:
    keys = sorted(curve.keys())
    if x <= keys[0]:
        return curve[keys[0]]
    if x >= keys[-1]:
        return curve[keys[-1]]
    for i in range(len(keys) - 1):
        x0, x1 = keys[i], keys[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return curve[x0] + t * (curve[x1] - curve[x0])
    return curve[keys[-1]]
