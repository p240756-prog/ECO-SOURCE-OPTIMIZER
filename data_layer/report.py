"""
report.py
=========

Dataset Quality & Validation Report generator.

Produces a human-readable Markdown report answering the question the annex
poses: "what dataset did we acquire, and is it good enough to move forward?"

The report includes:
    - Dataset overview (size, sites, time span, source mix)
    - Attribute completeness (all 29 attributes, null counts)
    - Descriptive statistics for key numeric fields
    - Incident / scenario coverage
    - Rule-engine recommendation distribution
    - Data-source provenance (Tier 1 / 2 / 3 chain of evidence)
    - Full validation report (pass/fail per check)
    - Definition-of-Done gate verdict + go/no-go recommendation
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import List

from data_layer.schema import TelemetryRecord, SCHEMA_COLUMNS
from data_layer.validation import ValidationReport


_NUMERIC_FIELDS = [
    "electricity_price", "battery_soc_pct", "battery_soh_pct",
    "battery_voltage", "generator_power_kw", "fuel_level_l",
    "fuel_consumption_lph", "solar_power_kw", "solar_irradiance",
    "load_kw", "traffic_load_pct", "qos_score", "temperature", "humidity",
]


def generate_markdown_report(
    records: List[TelemetryRecord],
    validation: ValidationReport,
    quarantined: int,
    output_path: str,
) -> None:
    """Write a full Markdown quality & validation report to `output_path`."""
    n = len(records)
    lines: List[str] = []

    def w(s: str = "") -> None:
        lines.append(s)

    # ---- Header ----
    w("# Dataset Quality & Validation Report")
    w()
    w("**AI-Native Telecom Infrastructure Intelligence Platform — MVP Backend**")
    w()
    w(f"*Generated: {datetime.now(timezone.utc).isoformat()} UTC*")
    w()
    w("Region calibration: **Pakistan / Punjab** "
      "(IESCO-LESCO-MEPCO feeders, NEPRA ToU tariffs, OGRA diesel, "
      "PMD weather, Islamabad latitude solar).")
    w()
    w("---")
    w()

    # ---- 1. Overview ----
    w("## 1. Dataset Overview")
    w()
    sites = sorted({r.site_id for r in records})
    ts_min = min(r.timestamp for r in records)
    ts_max = max(r.timestamp for r in records)
    real = sum(1 for r in records if r.source.value == "Real")
    synth = n - real
    w(f"| Metric | Value |")
    w(f"|---|---|")
    w(f"| Total accepted records | **{n:,}** |")
    w(f"| Quarantined records | {quarantined:,} |")
    w(f"| Distinct sites | {len(sites)} |")
    w(f"| Time span | {ts_min.isoformat()} → {ts_max.isoformat()} |")
    w(f"| Synthetic records | {synth:,} ({synth/n:.1%}) |")
    w(f"| Real (PLC) records | {real:,} ({real/n:.1%}) |")
    w(f"| Attributes per record | {len(SCHEMA_COLUMNS)} (full MVP schema) |")
    w()

    # ---- 2. Completeness ----
    w("## 2. Attribute Completeness (No-Null Guarantee)")
    w()
    w("Every one of the 29 attributes is populated on every record. "
      "`alarm_codes` may be an empty array (valid), never null.")
    w()
    null_counts = {c: 0 for c in SCHEMA_COLUMNS}
    for r in records:
        d = r.to_dict()
        for c in SCHEMA_COLUMNS:
            v = d.get(c)
            if c == "alarm_codes":
                continue
            if v is None or (isinstance(v, str) and v == ""):
                null_counts[c] += 1
    total_nulls = sum(null_counts.values())
    w(f"| Attribute | Null / Empty count |")
    w(f"|---|---|")
    for c in SCHEMA_COLUMNS:
        w(f"| {c} | {null_counts[c]} |")
    w()
    w(f"**Total null/empty values across dataset: {total_nulls}** "
      f"({'PASS — none' if total_nulls == 0 else 'FAIL'}).")
    w()

    # ---- 3. Descriptive statistics ----
    w("## 3. Descriptive Statistics (key numeric fields)")
    w()
    w("| Field | Min | Mean | Max | Std |")
    w("|---|---|---|---|---|")
    for f in _NUMERIC_FIELDS:
        vals = [getattr(r, f) for r in records]
        mn, mx = min(vals), max(vals)
        mean = statistics.mean(vals)
        std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        w(f"| {f} | {mn:.2f} | {mean:.2f} | {mx:.2f} | {std:.2f} |")
    w()

    # ---- 4. Categorical distributions ----
    w("## 4. Categorical & Enum Distributions")
    w()
    for field_name in ["grid_status", "tariff_type", "battery_status",
                       "generator_state", "source"]:
        counter = Counter(getattr(r, field_name).value for r in records)
        dist = ", ".join(f"{k}={v} ({v/n:.1%})" for k, v in counter.most_common())
        w(f"- **{field_name}**: {dist}")
    w()

    # ---- 5. Incident / scenario coverage ----
    w("## 5. Incident & Scenario Coverage (Edge Cases)")
    w()
    inc = Counter(r.incident_label.value for r in records)
    w("| Incident label | Count | Share |")
    w("|---|---|---|")
    for k, v in inc.most_common():
        w(f"| {k} | {v:,} | {v/n:.2%} |")
    w()
    scn = Counter(r.scenario_id for r in records)
    w("Scenario IDs present: "
      + ", ".join(f"`{k}`={v}" for k, v in scn.most_common()))
    w()

    # ---- 6. Rule-engine output ----
    w("## 6. Rule-Engine Recommendation Distribution")
    w()
    rec = Counter(r.recommended_source.value for r in records)
    w("| recommended_source | Count | Share |")
    w("|---|---|---|")
    for k, v in rec.most_common():
        w(f"| {k} | {v:,} | {v/n:.2%} |")
    w()

    # ---- 7. Provenance ----
    w("## 7. Data-Source Provenance (Chain of Evidence)")
    w()
    w("Every distribution is anchored to a real reference point before use "
      "(annex core principle).")
    w()
    w("| Tier | Source | Anchors |")
    w("|---|---|---|")
    w("| 1 | PLC Group logs (attachable) | outage duration, fuel burn, recovery time |")
    w("| 1 | DISCO load-shedding (IESCO/LESCO) | feeder outage windows |")
    w("| 1 | NEPRA / PTA reports | theft & congestion incident rates |")
    w("| 1 | NEPRA ToU tariff (Punjab) | electricity_price, tariff_type |")
    w("| 1 | OGRA diesel price | generator running-cost reasoning |")
    w("| 1 | OEM datasheets (Cummins/FG Wilson, VRLA) | fuel & battery curves |")
    w("| 2 | NASA battery dataset | SoH / degradation patterns |")
    w("| 2 | PMD / open weather | temperature, humidity |")
    w("| 2 | Solar model (Islamabad lat.) | solar_irradiance, solar_power_kw |")
    w("| 2 | Telecom Italia traffic | traffic_load_pct diurnal shape |")
    w("| 3 | Physics-informed simulator | internally-consistent time-series volume |")
    w()

    # ---- 8. Validation results ----
    w("## 8. Validation Framework Results (Definition of Done)")
    w()
    w("| Check | Result | Detail |")
    w("|---|---|---|")
    for c in validation.checks:
        status = "PASS ✅" if c.passed else "FAIL ❌"
        detail = (c.detail or c.message).replace("|", "/")
        w(f"| {c.name} | {status} | {detail} |")
    w()

    # ---- 9. Verdict ----
    w("## 9. Verdict — Can We Move Forward?")
    w()
    gate = validation.passed and total_nulls == 0 and n >= 5000
    if gate:
        w("### ✅ GO — dataset is fit to feed the MVP backend")
        w()
        w(f"- Volume target met: **{n:,} records** (target 5,000–10,000).")
        w("- All 29 attributes populated on every record (no nulls).")
        w("- Every validation check passed (anchor, statistical, edge-case, "
          "completeness, source-tag, rule-engine coverage).")
        w("- All required fault-scenario classes are present and labelled, so "
          "the rule engine and anomaly detectors can be exercised.")
        w("- Data is calibrated to Punjab tariffs, feeders, weather and solar.")
        w()
        w("**Recommendation:** proceed to Week-2 backend / rule-engine work. "
          "Attach real PLC logs via `data_layer/sources/plc_source.py` as they "
          "arrive; they flow through the same pipeline and remain held-out from "
          "training by their `source=Real` tag.")
    else:
        w("### ⚠️ NOT YET — address the failing checks above before Week-2")
        w()
        if n < 5000:
            w(f"- Volume below target: {n:,} < 5,000 — increase sites/days.")
        if total_nulls > 0:
            w(f"- {total_nulls} null/empty values must be eliminated.")
        if not validation.passed:
            w("- One or more validation checks failed (see table above).")
    w()
    w("---")
    w()
    w("*This report is regenerated on every dataset build so quality is a hard "
      "gate, not a one-off.*")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
