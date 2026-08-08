# Data Acquisition & Validation Layer

Implementation of the **Data Acquisition & Validation Strategy** annex for the
AI-Native Telecom Infrastructure Intelligence Platform (PLC Group — Punjab).

It acquires a **reliable, valid, labelled 29-attribute time-series dataset**
without any field hardware, by combining three tiers of data sources and
validating the result against real-world anchors — exactly as the annex
specifies. The **PLC source is left as an attachable adapter**; every other
source is fully implemented and ingesting.

---

## Quick start

```bash
# generate + ingest + validate + report (~7,200 records)
python -m data_layer.pipeline

# custom size
python -m data_layer.pipeline --sites 40 --days 10 --seed 7
```

Outputs (written to `data_layer/`):

| File | What it is |
|---|---|
| `telemetry_dataset.csv` | The validated 29-attribute dataset (no nulls) |
| `DATASET_QUALITY_REPORT.md` | Full quality & validation report + GO/NO-GO verdict |
| `review_sample.csv` | Sample for domain-expert plausibility sign-off |
| `quarantine.csv` | Any rejected records (with typed error codes) |

---

## The three-tier acquisition strategy (annex §"Three Tiers")

| Tier | Module | Role |
|---|---|---|
| **1** | `sources/disco_source.py` | IESCO/Punjab feeder load-shedding windows |
| **1** | `sources/nepra_source.py` | NEPRA/PTA theft & congestion incident rates |
| **1** | `sources/tariff_source.py` | NEPRA Punjab **ToU tariff** (Peak/Normal/Off-Peak, PKR) + OGRA diesel |
| **1** | `sources/oem_curves.py` | Cummins/FG Wilson fuel curve + VRLA discharge/charge curves |
| **2** | `sources/weather_source.py` | Islamabad temperature, humidity, **solar irradiance → PV power** |
| **2** | `sources/traffic_source.py` | Telecom Italia diurnal/weekly traffic shape |
| **3** | `simulator.py` | Physics-informed tick simulator (produces the volume) |
| **1** | `sources/plc_source.py` | **PLC logs — attachable stub (see below)** |

**Core principle preserved:** Tier 3 never invents a distribution — it always
samples from / is constrained by a Tier-1 or Tier-2 anchor.

---

## The data layer, end to end

```
Tier-1/2 sources ─┐
                  ├─► simulator.py (Tier 3) ─► ingestion.py ─► validation.py ─► CSV + report.py
plc_source.py ────┘   (29-attr records)       (schema check   (anchor, stats,
 (attach real data)                            + quarantine)    edge-case, no-null)
```

- **`schema.py`** — the single 29-attribute `TelemetryRecord` contract. Every
  source, real or synthetic, is normalised to it. Validates ranges, enums, and
  guarantees **no nulls** (`alarm_codes` = `NONE` when empty).
- **`rule_engine.py`** — fills `recommended_source` + human-readable `reason`
  per record (Grid / Solar / Battery / Generator), implementing the annex's
  Rule Engine Test Scenario Matrix (short vs long outage, low-battery, theft,
  sensor dropout, etc.).
- **`ingestion.py`** — schema validation + typed-error **quarantine** (never
  crash, never silently accept). Enforces the `source=Real` held-out tag.
- **`validation.py`** — Anchor Check, Statistical Validation (K-S style),
  Edge-Case Audit, Completeness (no-null), Source-Tag, Rule-Engine coverage,
  Domain-Expert review sample.
- **`report.py`** — generates `DATASET_QUALITY_REPORT.md` (Definition-of-Done
  gate + GO/NO-GO).

### The 29 attributes

`site_id, timestamp, grid_status, electricity_price, tariff_type,
battery_soc_pct, battery_soh_pct, battery_voltage, battery_status,
generator_state, generator_power_kw, fuel_level_l, fuel_consumption_lph,
solar_power_kw, solar_irradiance, load_kw, traffic_load_pct, qos_score,
temperature, humidity, alarm_codes, incident_label, recommended_source,
reason, source, schema_valid, stale_data_flag, record_id, scenario_id`

---

## ✅ How to ingest a PLC record (when you get one)

The PLC source is the **only** thing left to attach. When PLC Group hands over
their operational logs, nothing else in the pipeline changes:

1. **Export PLC logs to CSV** (grid interruptions, generator runs, diesel
   invoices, UPS/inverter logs, NOC tickets).
2. **Open `data_layer/sources/plc_source.py`** and, in `map_plc_row`, change the
   `row.get("...")` keys on the left to match **your** column names. Fields the
   PLC logs don't contain (tariff, weather, solar) are auto-joined from the same
   Tier-1/Tier-2 sources — so a PLC record ends up with all 29 attributes and no
   nulls, just like a synthetic one.
3. **Ingest through the same pipeline:**

   ```python
   from data_layer.sources.plc_source import load_plc_logs
   from data_layer.ingestion import IngestionPipeline
   from data_layer.validation import run_full_validation, run_anchor_check

   records = load_plc_logs("plc_export_2026_Q3.csv")   # tagged source=Real
   pipeline = IngestionPipeline(enforce_staleness=False)
   result = pipeline.ingest(records, training=False)    # held-out, NOT training
   print(result.summary())

   run_anchor_check(records)                            # vs DISCO/NEPRA anchors
   print(run_full_validation(result.accepted).summary())
   ```

4. **Held-out discipline is automatic:** every PLC record is tagged
   `source=Real`; the ingestion pipeline blocks real records from any run marked
   `training=True`, so real data can only ever be used for final validation —
   the single most important rule in the annex.

That's it: **one file, one function (`map_plc_row`) to point at your columns.**
