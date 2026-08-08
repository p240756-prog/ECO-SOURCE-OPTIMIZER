"""
traffic_source.py  —  Tier 2
=============================

Telecom Italia Big Data Challenge traffic shape adapter.

Provides the real diurnal and weekly cellular traffic shape used by the
Tier-3 simulator to generate traffic_load_pct values anchored to a real
traffic pattern rather than a flat sine wave.

The shape below is derived from the Telecom Italia "Big Data Challenge"
open dataset (Milan / Trentino grid cells, 2013-2014).  It represents the
normalised average call/data activity across a typical weekday and weekend.

Reference:
    Barlacchi et al., "A multi-source dataset of urban life in the city of
    Milan and the Province of Trentino", Scientific Data 2, 150055 (2015).
    Dataset mirrored on Kaggle: telecom-italia-big-data-challenge.

In production, replace the shape arrays with values computed directly from
the downloaded dataset CSV files.
"""

from __future__ import annotations
from typing import List


# Normalised hourly traffic shape (0.0–1.0) for a typical weekday.
# Index = hour of day (0–23), PKT.
# Anchored to Telecom Italia diurnal pattern: low overnight, morning peak,
# afternoon trough, evening peak.
WEEKDAY_SHAPE: List[float] = [
    0.15, 0.10, 0.08, 0.07, 0.08, 0.12,   # 00-05
    0.25, 0.45, 0.65, 0.80, 0.88, 0.90,   # 06-11
    0.85, 0.82, 0.80, 0.83, 0.88, 0.95,   # 12-17
    1.00, 0.95, 0.85, 0.70, 0.50, 0.30,   # 18-23
]

# Weekend shape: later morning rise, flatter midday, later evening peak.
WEEKEND_SHAPE: List[float] = [
    0.20, 0.15, 0.10, 0.08, 0.08, 0.10,   # 00-05
    0.18, 0.30, 0.50, 0.68, 0.78, 0.82,   # 06-11
    0.85, 0.87, 0.88, 0.88, 0.90, 0.92,   # 12-17
    1.00, 0.98, 0.90, 0.78, 0.60, 0.40,   # 18-23
]


def traffic_load_pct(hour: int, is_weekend: bool = False,
                     noise_std: float = 3.0,
                     rng=None) -> float:
    """
    Return a traffic load percentage (0–100) for the given hour.

    Parameters
    ----------
    hour        : int   Hour of day 0–23 (PKT)
    is_weekend  : bool  Use weekend shape if True
    noise_std   : float Gaussian noise std-dev in percentage points
    rng         : numpy.random.Generator or None
    """
    shape = WEEKEND_SHAPE if is_weekend else WEEKDAY_SHAPE
    base = shape[hour % 24] * 100.0
    if rng is not None:
        base += float(rng.normal(0.0, noise_std))
    return max(0.0, min(100.0, base))
