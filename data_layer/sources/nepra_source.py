"""
nepra_source.py  —  Tier 1
===========================

NEPRA / PTA quarterly & annual report adapter.

Provides sector-wide anchor statistics used to calibrate the *frequency* of
synthetic incidents so the injected theft / outage rates match national
averages rather than an invented number.

In production, replace the constants below with figures extracted from the
latest NEPRA "State of Industry" report and PTA annual report for the relevant
provinces.  Re-verify at time of use — these reports are updated periodically.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class NepraAnchors:
    """
    Sector-wide anchor rates from NEPRA / PTA reports.

    All rates are expressed per-site-day so the simulator can sample against
    them directly.
    """
    # Fraction of site-days that contain a fuel-theft event.
    # Anchored to PTA-reported telecom fuel/equipment theft incidence.
    theft_fraction_per_site_day: float = 0.03      # ~3 % of site-days

    # Fraction of site-days with a congestion (QoS breach) event.
    congestion_fraction_per_site_day: float = 0.08

    # Fraction of site-days with a sensor / telemetry fault.
    sensor_fault_fraction_per_site_day: float = 0.02

    # National average tower downtime (fraction of time), NEPRA/PTA.
    avg_tower_downtime_fraction: float = 0.06

    # National average grid-outage hours per day (NEPRA load-shed stats).
    avg_grid_outage_hours_per_day: float = 8.0


# Singleton instance used across the data layer.
ANCHORS = NepraAnchors()
