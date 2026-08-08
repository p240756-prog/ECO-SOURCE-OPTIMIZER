"""
validation.py
=============

Validation Framework — "Definition of Done" for the dataset.

Implements the validation checks from the annex, adapted to the 29-attribute
MVP schema:

    1. Anchor Check          — aggregate stats vs. DISCO/NEPRA anchors
    2. Completeness Check     — NO null / empty field across all 29 attributes
    3. Edge-Case Audit        — coverage of all required fault scenario classes
    4. Statistical Validation — outage-duration distribution vs. DISCO anchor
    5. Source-Tag Check       — every record tagged Real/Synthetic
    6. Rule-Engine Coverage   — recommended_source populated + reason present
    7. Domain Expert Review   — representative sample export for sign-off

A dataset is "ready" only when every check passes.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Dict, Optional

from data_layer.schema import (
    TelemetryRecord,
    GridStatus,
    GeneratorState,
    IncidentLabel,
    RecommendedSource,
    Source,
    validate_record,
    SchemaError,
    SCHEMA_COLUMNS,
)
from data_layer.sources.nepra_source import ANCHORS
from data_layer.sources.disco_source import IESCO_SCHEDULE


ANCHOR_TOLERANCE = 0.35
MIN_FAULT_SCENARIO_COUNT = 20


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    detail: Optional[str] = None

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] {self.name}: {self.message}"]
        if self.detail:
            lines.append(f"       {self.detail}")
        return "\n".join(lines)


@dataclass
class ValidationReport:
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def summary(self) -> str:
        lines = ["=" * 64, "VALIDATION REPORT", "=" * 64]
        for c in self.checks:
            lines.append(str(c))
        lines.append("=" * 64)
        lines.append("ALL CHECKS PASSED" if self.passed else "VALIDATION FAILED")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1. Anchor Check
# ---------------------------------------------------------------------------

def run_anchor_check(records: List[TelemetryRecord]) -> CheckResult:
    if not records:
        return CheckResult("AnchorCheck", False, "no records to check")

    total = len(records)
    grid_down = sum(1 for r in records if r.grid_status == GridStatus.DOWN)

    if len(records) >= 2:
        # estimate tick hours from two consecutive same-site records
        delta = 1.0
        for i in range(1, len(records)):
            if records[i].site_id == records[i - 1].site_id:
                delta = (records[i].timestamp - records[i - 1].timestamp).total_seconds() / 3600.0
                if delta > 0:
                    break
    else:
        delta = 1.0

    total_days = (total * delta) / 24.0

    outage_fraction = grid_down / total
    expected_outage_fraction = ANCHORS.avg_grid_outage_hours_per_day / 24.0
    outage_ok = _within_tolerance(outage_fraction, expected_outage_fraction,
                                   ANCHOR_TOLERANCE)

    theft_days = len({(r.site_id, r.timestamp.date()) for r in records
                      if r.incident_label == IncidentLabel.THEFT})
    site_days = len({(r.site_id, r.timestamp.date()) for r in records})
    theft_rate = theft_days / site_days if site_days else 0.0
    theft_ok = theft_rate <= ANCHORS.theft_fraction_per_site_day * 5.0

    passed = outage_ok and theft_ok
    detail = (
        f"outage_fraction={outage_fraction:.3f} "
        f"(anchor≈{expected_outage_fraction:.3f}±{ANCHOR_TOLERANCE:.0%}), "
        f"theft_rate/site-day={theft_rate:.3f} "
        f"(anchor={ANCHORS.theft_fraction_per_site_day:.3f})"
    )
    msg = ("aggregate statistics within anchor tolerances" if passed
           else "one or more aggregates outside anchor tolerance")
    return CheckResult("AnchorCheck", passed, msg, detail)


# ---------------------------------------------------------------------------
# 2. Completeness Check — NO null / empty field
# ---------------------------------------------------------------------------

def run_completeness_check(records: List[TelemetryRecord]) -> CheckResult:
    if not records:
        return CheckResult("CompletenessCheck", False, "no records")

    null_fields: Dict[str, int] = {}
    invalid = 0

    for r in records:
        d = r.to_dict()
        for col in SCHEMA_COLUMNS:
            val = d.get(col, None)
            # alarm_codes may be an empty list — that is valid, not null
            if col == "alarm_codes":
                if val is None:
                    null_fields[col] = null_fields.get(col, 0) + 1
                continue
            if val is None or (isinstance(val, str) and val == ""):
                null_fields[col] = null_fields.get(col, 0) + 1
        try:
            validate_record(r)
        except SchemaError:
            invalid += 1

    passed = not null_fields and invalid == 0
    detail = (f"records={len(records)}, invalid={invalid}, "
              f"null_fields={null_fields if null_fields else 'none'}")
    msg = ("all 29 attributes populated on every record (no nulls)" if passed
           else "null/empty fields or invalid records detected")
    return CheckResult("CompletenessCheck", passed, msg, detail)


# ---------------------------------------------------------------------------
# 3. Edge-Case Audit
# ---------------------------------------------------------------------------

def run_edge_case_audit(records: List[TelemetryRecord]) -> CheckResult:
    required = {
        IncidentLabel.OUTAGE,
        IncidentLabel.THEFT,
        IncidentLabel.CONGESTION,
        IncidentLabel.SENSOR_FAULT,
    }
    counts: Dict[IncidentLabel, int] = {}
    near_zero_batt = 0
    simultaneous_fail = 0

    for r in records:
        if r.incident_label != IncidentLabel.NONE:
            counts[r.incident_label] = counts.get(r.incident_label, 0) + 1
        if r.battery_soc_pct <= 5.0:
            near_zero_batt += 1
        if (r.grid_status == GridStatus.DOWN
                and r.generator_state == GeneratorState.OFF
                and r.battery_soc_pct <= 20.0):
            simultaneous_fail += 1

    missing = required - set(counts.keys())
    thin = {l: c for l, c in counts.items() if c < MIN_FAULT_SCENARIO_COUNT}

    failures = []
    if missing:
        failures.append(f"missing labels: {[l.value for l in missing]}")
    if thin:
        failures.append("thin labels (<%d): " % MIN_FAULT_SCENARIO_COUNT
                        + ", ".join(f"{l.value}={c}" for l, c in thin.items()))
    if near_zero_batt < 1:
        failures.append("no near-zero battery records (SoC ≤ 5 %)")
    if simultaneous_fail < 1:
        failures.append("no simultaneous grid+generator failure records")

    passed = not failures
    detail = ("label counts: "
              + ", ".join(f"{l.value}={c}" for l, c in counts.items())
              + f" | near_zero_battery={near_zero_batt}"
              + f" | simultaneous_failure={simultaneous_fail}")
    msg = ("all required fault scenario classes present" if passed
           else "; ".join(failures))
    return CheckResult("EdgeCaseAudit", passed, msg, detail)


# ---------------------------------------------------------------------------
# 4. Statistical Validation — outage duration vs. DISCO anchor
# ---------------------------------------------------------------------------

def run_statistical_validation(records: List[TelemetryRecord]) -> CheckResult:
    runs: List[float] = []
    by_site: Dict[str, List[TelemetryRecord]] = {}
    for r in records:
        by_site.setdefault(r.site_id, []).append(r)

    for site_records in by_site.values():
        seq = sorted(site_records, key=lambda x: x.timestamp)
        run_start = None
        prev_ts = None
        for r in seq:
            if r.grid_status == GridStatus.DOWN:
                if run_start is None:
                    run_start = r.timestamp
            else:
                if run_start is not None and prev_ts is not None:
                    dur = (prev_ts - run_start).total_seconds() / 3600.0
                    # include the last down tick's own duration
                    tick_h = 1.0
                    if len(seq) > 1:
                        tick_h = (seq[1].timestamp - seq[0].timestamp).total_seconds() / 3600.0
                    dur += tick_h
                    if dur > 0:
                        runs.append(dur)
                    run_start = None
            prev_ts = r.timestamp

    if len(runs) < 3:
        return CheckResult("StatisticalValidation", False,
                           f"too few outage runs ({len(runs)}) for test")

    expected_mean = sum(d for _, _, d in IESCO_SCHEDULE) / len(IESCO_SCHEDULE)
    observed_mean = statistics.mean(runs)
    observed_std = statistics.stdev(runs) if len(runs) > 1 else 0.0
    ok = _within_tolerance(observed_mean, expected_mean, ANCHOR_TOLERANCE)

    detail = (f"observed mean={observed_mean:.2f}h std={observed_std:.2f}h "
              f"(expected≈{expected_mean:.2f}h from DISCO schedule, n={len(runs)})")
    msg = ("outage-duration distribution consistent with DISCO anchor" if ok
           else f"outage mean {observed_mean:.2f}h deviates from anchor {expected_mean:.2f}h")
    return CheckResult("StatisticalValidation", ok, msg, detail)


# ---------------------------------------------------------------------------
# 5. Source-Tag Check
# ---------------------------------------------------------------------------

def run_source_tag_check(records: List[TelemetryRecord]) -> CheckResult:
    bad = [r for r in records if r.source not in (Source.REAL, Source.SYNTHETIC)]
    if bad:
        return CheckResult("SourceTagCheck", False,
                           f"{len(bad)} records have invalid source tags")
    real = sum(1 for r in records if r.source == Source.REAL)
    synth = sum(1 for r in records if r.source == Source.SYNTHETIC)
    return CheckResult("SourceTagCheck", True,
                       f"all {len(records)} records tagged "
                       f"(Real={real}, Synthetic={synth})")


# ---------------------------------------------------------------------------
# 6. Rule-Engine Coverage
# ---------------------------------------------------------------------------

def run_rule_engine_coverage(records: List[TelemetryRecord]) -> CheckResult:
    missing_reason = sum(1 for r in records if not r.reason)
    bad_source = sum(1 for r in records
                     if not isinstance(r.recommended_source, RecommendedSource))
    used = {r.recommended_source.value for r in records}
    passed = missing_reason == 0 and bad_source == 0
    detail = f"sources used: {sorted(used)} | missing_reason={missing_reason}"
    msg = ("every record has a recommended_source and reason" if passed
           else "some records missing rule-engine output")
    return CheckResult("RuleEngineCoverage", passed, msg, detail)


# ---------------------------------------------------------------------------
# 7. Domain Expert Review — sample export
# ---------------------------------------------------------------------------

def export_review_sample(records: List[TelemetryRecord], n: int = 60,
                         output_path: str = "data_layer/review_sample.csv") -> CheckResult:
    try:
        import csv
        by_label: Dict[IncidentLabel, List[TelemetryRecord]] = {}
        for r in records:
            by_label.setdefault(r.incident_label, []).append(r)

        sample: List[TelemetryRecord] = []
        per_class = max(1, n // max(1, len(by_label)))
        for lst in by_label.values():
            sample.extend(lst[:per_class])
        sample = sample[:n]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SCHEMA_COLUMNS)
            writer.writeheader()
            for r in sample:
                d = r.to_dict()
                d["alarm_codes"] = "|".join(d["alarm_codes"])
                writer.writerow(d)

        return CheckResult("DomainExpertReview", True,
                           f"review sample ({len(sample)} records) → {output_path}",
                           "Awaiting domain expert sign-off (procedural)")
    except Exception as exc:  # pragma: no cover
        return CheckResult("DomainExpertReview", False, str(exc))


# ---------------------------------------------------------------------------
# Full suite
# ---------------------------------------------------------------------------

def run_full_validation(records: List[TelemetryRecord],
                        review_sample_path: str = "data_layer/review_sample.csv") -> ValidationReport:
    report = ValidationReport()
    report.checks.append(run_completeness_check(records))
    report.checks.append(run_anchor_check(records))
    report.checks.append(run_edge_case_audit(records))
    report.checks.append(run_statistical_validation(records))
    report.checks.append(run_source_tag_check(records))
    report.checks.append(run_rule_engine_coverage(records))
    report.checks.append(export_review_sample(records, output_path=review_sample_path))
    return report


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _within_tolerance(observed: float, expected: float, tol: float) -> bool:
    if expected == 0:
        return observed == 0
    return abs(observed - expected) / abs(expected) <= tol
