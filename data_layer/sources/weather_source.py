"""
weather_source.py  —  Tier 2
=============================

Open weather adapter for Islamabad temperature and humidity.

Provides a realistic temperature series correlated with load-shedding
intensity and battery performance.  In production, replace the stub below
with a live call to Open-Meteo (free, no API key required) or
OpenWeatherMap.

Reference (annex Tier 2):
    Open weather APIs — Islamabad temperature, humidity
    Used to add a realistic confounding variable instead of pure random noise.
"""

from __future__ import annotations
import math
from typing import Optional


# ---------------------------------------------------------------------------
# Islamabad monthly mean temperature (°C) — Pakistan Meteorological Dept.
# Index 0 = January, 11 = December
# ---------------------------------------------------------------------------
_MONTHLY_MEAN_TEMP_C = [
    10.5, 12.8, 17.5, 23.0, 28.5, 33.0,
    32.5, 31.0, 28.0, 22.5, 16.0, 11.5,
]

# Diurnal swing (°C peak-to-trough) — typical Islamabad value
_DIURNAL_SWING_C = 10.0


def temperature_c(month: int, hour_pkt: int,
                  noise_std: float = 1.5,
                  rng=None) -> float:
    """
    Return an estimated temperature (°C) for Islamabad.

    Parameters
    ----------
    month     : int  1–12
    hour_pkt  : int  0–23 (Pakistan Standard Time)
    noise_std : float  Gaussian noise std-dev in °C
    rng       : numpy.random.Generator or None
    """
    base = _MONTHLY_MEAN_TEMP_C[(month - 1) % 12]
    # Diurnal cycle: minimum at ~05:00, maximum at ~15:00
    diurnal = (_DIURNAL_SWING_C / 2.0) * math.sin(
        math.pi * (hour_pkt - 5) / 10.0
    )
    temp = base + diurnal
    if rng is not None:
        temp += float(rng.normal(0.0, noise_std))
    return round(temp, 1)


def battery_temp_derating(temp_c: float) -> float:
    """
    Return a capacity derating factor (0–1) for the battery at `temp_c`.

    Industrial VRLA batteries lose ~1 % capacity per °C above 25 °C and
    ~0.5 % per °C below 15 °C.  Used by the simulator to make battery
    runtime shorter in summer and slightly shorter in winter.
    """
    if temp_c > 25.0:
        loss = min(0.30, (temp_c - 25.0) * 0.01)
    elif temp_c < 15.0:
        loss = min(0.15, (15.0 - temp_c) * 0.005)
    else:
        loss = 0.0
    return max(0.70, 1.0 - loss)


def load_scaling_factor(temp_c: float) -> float:
    """
    Return a site load scaling factor driven by ambient temperature.

    Cooling loads increase above 30 °C (air-conditioning for BTS equipment).
    Anchored to typical telecom site HVAC behaviour.
    """
    if temp_c > 30.0:
        return 1.0 + min(0.25, (temp_c - 30.0) * 0.02)
    return 1.0


# ---------------------------------------------------------------------------
# Islamabad / Punjab monthly mean relative humidity (%) — PMD
# ---------------------------------------------------------------------------
_MONTHLY_MEAN_HUMIDITY = [
    62, 58, 55, 48, 40, 45,     # Jan–Jun
    68, 72, 65, 55, 58, 60,     # Jul–Dec  (monsoon peak Jul–Aug)
]


def humidity_pct(month: int, hour_pkt: int,
                 noise_std: float = 4.0,
                 rng=None) -> float:
    """
    Return an estimated relative humidity (%) for the given month/hour.

    Humidity is highest before dawn and lowest mid-afternoon (inverse of the
    diurnal temperature cycle).
    """
    base = _MONTHLY_MEAN_HUMIDITY[(month - 1) % 12]
    # Inverse diurnal swing: peak humidity ~05:00, trough ~15:00
    diurnal = -12.0 * math.sin(math.pi * (hour_pkt - 5) / 10.0)
    h = base + diurnal
    if rng is not None:
        h += float(rng.normal(0.0, noise_std))
    return max(0.0, min(100.0, round(h, 1)))


# ---------------------------------------------------------------------------
# Solar irradiance model (W/m^2) — clear-sky, Islamabad/Punjab latitude ~33.7°N
# ---------------------------------------------------------------------------
# Peak clear-sky GHI ~ 950 W/m^2 in summer, ~600 W/m^2 in winter.
_MONTHLY_PEAK_GHI = [
    600, 680, 780, 880, 950, 980,   # Jan–Jun
    900, 880, 850, 760, 650, 580,   # Jul–Dec
]


def solar_irradiance(month: int, hour_pkt: int,
                     cloud_factor: float = 1.0,
                     rng=None) -> float:
    """
    Return solar irradiance (W/m^2) for the given month/hour.

    Zero before sunrise (~06:00) and after sunset (~19:00); a sinusoidal
    daylight curve peaking at solar noon (~12:30 PKT).  `cloud_factor` in
    [0,1] attenuates clear-sky irradiance (1.0 = clear sky).
    """
    if hour_pkt < 6 or hour_pkt > 19:
        return 0.0
    peak = _MONTHLY_PEAK_GHI[(month - 1) % 12]
    # Daylight sine: 0 at 06:00 and 19:00, max near 12:30
    frac = math.sin(math.pi * (hour_pkt - 6) / 13.0)
    ghi = peak * max(0.0, frac) * max(0.0, min(1.0, cloud_factor))
    if rng is not None:
        ghi += float(rng.normal(0.0, 15.0))
    return max(0.0, round(ghi, 1))


def solar_power_kw(irradiance_wm2: float, panel_capacity_kw: float,
                   temp_c: float = 25.0) -> float:
    """
    Convert irradiance to AC solar power (kW) for a given panel capacity.

    Uses STC reference 1000 W/m^2 and a temperature derate above 25 °C
    (~0.4 %/°C, typical crystalline-silicon coefficient).
    """
    ratio = irradiance_wm2 / 1000.0
    temp_derate = 1.0 - max(0.0, (temp_c - 25.0)) * 0.004
    power = panel_capacity_kw * ratio * temp_derate
    return max(0.0, round(power, 3))


