"""
pipeline.py
===========

Top-level data pipeline runner.

Wires together the full data layer:

    Tier-1/2 sources  →  Tier-3 simulator  →  ingestion (schema validation
    + quarantine)  →  validation framework  →  CSV export  →  quality report

This is the single entry point for Week-1 dataset generation.  It produces a
validated, labelled, 29-attribute dataset (target 5,000–10,000 records) ready
for the MVP backend, plus a Markdown Dataset Quality & Validation Report.

Usage
-----
    python -m data_layer.pipeline                 # default ~7,200 records
    python -m data_layer.pipeline --sites 40 --days 10 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone
from typing import List

import numpy as np

from data_layer.schema import TelemetryRecord, SCHEMA_COLUMNS
from data_layer.simulator import SiteSimulator, SimulatorConfig
from data_layer.ingestion import IngestionPipeline
from data_layer.validation import run_full_validation
from data_layer.report import generate_markdown_report


# ---------------------------------------------------------------------------
# Site registry — Punjab telecom sites across IESCO/LESCO-style feeders
# ---------------------------------------------------------------------------

_FEEDERS = ["ISB-A", "ISB-B", "ISB-C", "ISB-RURAL"]
_CITY_PREFIX = {
    "ISB-A": "ISB", "ISB-B": "RWP", "ISB-C": "LHR", "ISB-RURAL": "MUL",
}


def build_site_registry(n_sites: int, rng: np.random.Generator) -> dict:
    """Create a site registry of Punjab sites with varied load/solar/battery."""
    registry = {}
    for i in range(n_sites):
        feeder = _FEEDERS[i % len(_FEEDERS)]
        prefix = _CITY_PREFIX[feeder]
        site_id = f"{prefix}-{i:03d}"
        registry[site_id] = {
            "feeder_area": feeder,
            "nominal_load_kw": round(float(rng.uniform(8.0, 16.0)), 1),
            "solar_capacity_kw": round(float(rng.uniform(6.0, 12.0)), 1),
            "battery_capacity_kwh": round(float(rng.uniform(30.0, 45.0)), 1),
        }
    return registry


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    n_days: int = 10,
    n_sites: int = 30,
    seed: int = 7,
    output_dir: str = "data_layer",
    tick_minutes: int = 60,
) -> bool:
    """
    Generate, ingest, validate, export a dataset and write the quality report.

    Returns True if the Definition-of-Done gate passes.
    """
    os.makedirs(output_dir, exist_ok=True)
    rng = np.random.default_rng(seed)

    registry = build_site_registry(n_sites, rng)
    all_records: List[TelemetryRecord] = []

    ticks_per_day = 24 * 60 // tick_minutes
    projected = n_sites * n_days * ticks_per_day

    print(f"\n{'='*64}")
    print("Data Acquisition & Validation Pipeline — Punjab MVP dataset")
    print(f"  Sites: {n_sites} | Days: {n_days} | Tick: {tick_minutes} min")
    print(f"  Projected records: ~{projected:,} | Seed: {seed}")
    print(f"{'='*64}\n")

    # ---- Step 1: Tier-3 simulation (anchored to Tier-1/2 sources) ----
    print("Step 1/5  Generating records (Tier-3 simulator + Tier-1/2 anchors)...")
    for site_id, meta in registry.items():
        cfg = SimulatorConfig(
            site_id=site_id,
            feeder_area=meta["feeder_area"],
            nominal_load_kw=meta["nominal_load_kw"],
            solar_capacity_kw=meta["solar_capacity_kw"],
            battery_capacity_kwh=meta["battery_capacity_kwh"],
            n_days=n_days,
            tick_minutes=tick_minutes,
            start_date=datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
        )
        all_records.extend(SiteSimulator(cfg, rng=rng).run())
    print(f"  Generated {len(all_records):,} records across {n_sites} sites.\n")

    # ---- Step 2: Ingestion (schema validation + quarantine) ----
    print("Step 2/5  Ingestion pipeline (schema validation + quarantine)...")
    pipeline = IngestionPipeline(enforce_staleness=False)  # historical batch
    result = pipeline.ingest(all_records, training=True)
    print(result.summary())
    print()
    accepted = result.accepted

    # ---- Step 3: Malformed-data / failure testing (adversarial) ----
    print("Step 3/5  Malformed-data & failure testing (adversarial ingest)...")
    _run_malformed_tests(accepted)
    print()

    # ---- Step 4: Validation framework ----
    print("Step 4/5  Validation framework (Definition of Done)...")
    review_path = os.path.join(output_dir, "review_sample.csv")
    report = run_full_validation(accepted, review_sample_path=review_path)
    print(report.summary())
    print()

    # ---- Step 5: Export + quality report ----
    print("Step 5/5  Exporting dataset + quality report...")
    dataset_path = os.path.join(output_dir, "telemetry_dataset.csv")
    _export_csv(accepted, dataset_path)
    print(f"  Dataset       → {dataset_path}  ({len(accepted):,} records)")
    print(f"  Review sample → {review_path}")

    if result.quarantined:
        q_path = os.path.join(output_dir, "quarantine.csv")
        _export_quarantine(result.quarantined, q_path)
        print(f"  Quarantine    → {q_path}  ({len(result.quarantined)} records)")

    report_path = os.path.join(output_dir, "DATASET_QUALITY_REPORT.md")
    generate_markdown_report(accepted, report, len(result.quarantined), report_path)
    print(f"  Quality report→ {report_path}")

    gate = report.passed and len(accepted) >= 5000
    print(f"\n{'='*64}")
    print(f"Definition-of-Done gate: "
          f"{'PASSED — GO for Week-2' if gate else 'FAILED — see report'}")
    print(f"{'='*64}\n")
    return gate


# ---------------------------------------------------------------------------
# Malformed-data testing (annex requirement)
# ---------------------------------------------------------------------------

def _run_malformed_tests(accepted: List[TelemetryRecord]) -> None:
    """Feed deliberately broken records and confirm they are all rejected."""
    import copy
    from data_layer.schema import GridStatus, GeneratorState

    if not accepted:
        print("  (no accepted records to derive malformed cases from)")
        return

    base = accepted[0]
    cases = []

    # missing required field (empty site_id)
    r = copy.deepcopy(base); r.site_id = ""
    cases.append(("missing site_id", r))
    # out-of-range percentage
    r = copy.deepcopy(base); r.battery_soc_pct = 150.0
    cases.append(("SoC > 100", r))
    # negative fuel
    r = copy.deepcopy(base); r.fuel_level_l = -5.0
    cases.append(("negative fuel", r))
    # bad voltage
    r = copy.deepcopy(base); r.battery_voltage = 5.0
    cases.append(("voltage out of range", r))
    # zero price
    r = copy.deepcopy(base); r.electricity_price = 0.0
    cases.append(("zero electricity_price", r))
    # empty reason
    r = copy.deepcopy(base); r.reason = ""
    cases.append(("empty reason", r))

    from data_layer.ingestion import IngestionPipeline
    rejected = 0
    for label, rec in cases:
        p = IngestionPipeline(enforce_staleness=False)
        res = p.ingest([rec])
        ok = len(res.quarantined) == 1 and len(res.accepted) == 0
        rejected += 1 if ok else 0
        code = res.quarantined[0].error_code if res.quarantined else "ACCEPTED!"
        mark = "[OK]" if ok else "[!!]"
        print(f"    {mark} {label:26s} -> {code}")

    print(f"  Malformed-data testing: {rejected}/{len(cases)} correctly rejected.")


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _export_csv(records: List[TelemetryRecord], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCHEMA_COLUMNS)
        writer.writeheader()
        for r in records:
            d = r.to_dict()
            # Empty alarm array → explicit "NONE" so no cell is ever empty/null
            d["alarm_codes"] = "|".join(d["alarm_codes"]) if d["alarm_codes"] else "NONE"
            writer.writerow(d)



def _export_quarantine(entries, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["site_id", "timestamp", "error_code", "error_message"])
        for q in entries:
            writer.writerow([q.raw.site_id, q.raw.timestamp.isoformat(),
                             q.error_code, q.error_message])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Acquisition & Validation Pipeline")
    parser.add_argument("--days",  type=int, default=10)
    parser.add_argument("--sites", type=int, default=30)
    parser.add_argument("--seed",  type=int, default=7)
    parser.add_argument("--tick",  type=int, default=60)
    parser.add_argument("--out",   type=str, default="data_layer")
    args = parser.parse_args()

    run_pipeline(n_days=args.days, n_sites=args.sites, seed=args.seed,
                 output_dir=args.out, tick_minutes=args.tick)
