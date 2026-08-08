"""
tariff_source.py  —  Tier 1  (Pakistan / Punjab)
=================================================

Punjab (IESCO / LESCO / MEPCO) electricity tariff adapter.

Provides the real time-of-use (ToU) tariff structure and per-kWh prices used
to populate `electricity_price` and `tariff_type`.  Anchored to NEPRA-notified
industrial/commercial ToU tariffs for DISCOs operating in Punjab, FY 2024-25.

Reference:
    NEPRA notified Schedule of Tariff for XW-DISCOs (IESCO/LESCO/MEPCO/GEPCO)
    Time-of-Use (ToU) for B2/B3 commercial & industrial connections.
    Values in PKR / kWh.  Re-verify against the latest NEPRA notification.
"""

from __future__ import annotations
from typing import Tuple

from data_layer.schema import TariffType


# ---------------------------------------------------------------------------
# NEPRA ToU tariff (PKR / kWh) — Punjab industrial/commercial, FY 2024-25
# ---------------------------------------------------------------------------
# Peak hours attract the highest rate; off-peak the lowest.  A "Normal"
# shoulder rate is used for the remaining daytime hours.

PEAK_RATE_PKR = 48.50       # peak ToU rate
NORMAL_RATE_PKR = 39.00     # shoulder / normal daytime rate
OFF_PEAK_RATE_PKR = 30.75   # off-peak (overnight) rate

# Peak windows (PKT) per NEPRA ToU definition — evening peak in winter/summer.
# Summer peak: 18:00–22:00 ; Winter peak: 17:00–21:00.  We use a combined
# evening peak window that covers the common case.
PEAK_START_HOUR = 18
PEAK_END_HOUR = 22

# Off-peak overnight window.
OFF_PEAK_START_HOUR = 23
OFF_PEAK_END_HOUR = 6       # up to (not including) 06:00


def get_tariff(hour_pkt: int) -> Tuple[TariffType, float]:
    """
    Return (TariffType, electricity_price_PKR_per_kWh) for the given PKT hour.

    Parameters
    ----------
    hour_pkt : int  Hour of day 0-23 (Pakistan Standard Time)
    """
    h = hour_pkt % 24

    # Peak: 18:00–21:59
    if PEAK_START_HOUR <= h < PEAK_END_HOUR:
        return TariffType.PEAK, PEAK_RATE_PKR

    # Off-peak overnight: 23:00–05:59 (wraps midnight)
    if h >= OFF_PEAK_START_HOUR or h < OFF_PEAK_END_HOUR:
        return TariffType.OFF_PEAK, OFF_PEAK_RATE_PKR

    # Everything else is Normal / shoulder
    return TariffType.NORMAL, NORMAL_RATE_PKR


# ---------------------------------------------------------------------------
# Diesel price anchor (Punjab) — used for generator running-cost reasoning
# ---------------------------------------------------------------------------
# OGRA-notified High-Speed Diesel (HSD) retail price, PKR / litre.
DIESEL_PRICE_PKR_PER_LITRE = 272.0
