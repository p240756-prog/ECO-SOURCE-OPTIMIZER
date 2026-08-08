"""
data_layer.sources
==================

One adapter per data source.  Every adapter returns a list of
`TelemetryRecord` objects (or raw anchor dicts for Tier-1/2 reference
sources that are used only for calibration, not as ingested records).

Tier 1 — real-world reference (no hardware required)
    plc_source.py       PLC Group logs  ← STUB, attach when records arrive
    disco_source.py     DISCO load-shedding schedules (IESCO / K-Electric)
    nepra_source.py     NEPRA / PTA quarterly reports
    oem_curves.py       Generator & battery OEM datasheets

Tier 2 — public / open reference datasets
    nasa_battery.py     NASA Prognostics Center battery dataset
    weather_source.py   Open weather API (Islamabad temperature / humidity)
    traffic_source.py   Telecom Italia Big Data Challenge traffic dataset
"""
