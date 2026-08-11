#!/usr/bin/env python3
"""Minimal independent headline check using direct PyArrow row iteration."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

HORIZONS = ["H4", "H8", "H12", "H16", "H24", "H32", "FULL"]
SEVERITIES = ["W8", "W6", "W4"]
METRICS = ["D_CMC", "B_FS_CMC"]


def rows_from(directory: Path):
    for path in sorted(directory.glob("*.parquet")):
        table = pq.read_table(path)
        for batch in table.to_batches(max_chunksize=8192):
            for row in batch.to_pylist():
                yield row


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cert3-payload", type=Path, required=True)
    p.add_argument("--audit-dir", type=Path, required=True)
    args = p.parse_args()
    sums = defaultdict(lambda: [0.0, 0.0, 0])
    violations = 0
    for row in rows_from(args.cert3_payload / "raw/horizon_endpoints"):
        if row["family"] != "CMC":
            continue
        key = (row["severity"], row["horizon"])
        sums[key][0] += float(row["D"])
        sums[key][1] += float(row["B_FS"])
        sums[key][2] += 1
        if float(row["D"]) > float(row["B_FS"]) + 1e-12:
            violations += 1
    radius = math.sqrt(math.log(49 / .05) / (2 * 256))
    headline = {}
    for severity in SEVERITIES:
        for horizon in HORIZONS:
            dsum, bsum, n = sums[(severity, horizon)]
            headline[f"{severity}/{horizon}"] = {
                "n": n, "mean_D_CMC": dsum / n, "mean_B_FS_CMC": bsum / n,
                "UCB_D_CMC": min(1.0, dsum / n + radius),
                "UCB_B_FS_CMC": min(1.0, bsum / n + radius),
            }
    absolute = {}
    for severity in SEVERITIES:
        for metric, key in [("D_CMC", "UCB_D_CMC"), ("B_FS_CMC", "UCB_B_FS_CMC")]:
            for epsilon in [.25, .5, .75]:
                selected = "NONE"
                for i, horizon in enumerate(HORIZONS):
                    if all(headline[f"{severity}/{h}"][key] <= epsilon
                           for h in HORIZONS[:i + 1]):
                        selected = horizon
                absolute[f"{severity}/{metric}/{epsilon}"] = selected

    # Compare against the first implementation without sharing its aggregation code.
    first_values = {}
    with (args.audit_dir / "recalculation/independent_certificate_ucb_summary.csv").open(
            newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["severity"] in SEVERITIES and r["metric"] in METRICS:
                first_values[(r["severity"], r["horizon"], r["metric"])] = (
                    float(r["mean"]), float(r["bound"]))
    max_diff = 0.0
    mismatches = []
    for severity in SEVERITIES:
        for horizon in HORIZONS:
            h = headline[f"{severity}/{horizon}"]
            for metric, mk, bk in [
                    ("D_CMC", "mean_D_CMC", "UCB_D_CMC"),
                    ("B_FS_CMC", "mean_B_FS_CMC", "UCB_B_FS_CMC")]:
                a = first_values[(severity, horizon, metric)]
                diff = max(abs(h[mk] - a[0]), abs(h[bk] - a[1]))
                max_diff = max(max_diff, diff)
                if diff > 1e-10:
                    mismatches.append(
                        {"severity": severity, "horizon": horizon,
                         "metric": metric, "max_abs_diff": diff})
    result = {
        "implementation": "direct PyArrow scan + Python dictionaries",
        "pathwise_violation_count": violations,
        "hoeffding_radius_n256": radius,
        "full_horizon": {s: headline[f"{s}/FULL"] for s in SEVERITIES},
        "absolute_certified_horizons": absolute,
        "maximum_first_vs_second_abs_diff": max_diff,
        "mismatches": mismatches,
        "status": "PASS" if not mismatches and violations == 0 else "FAIL",
    }
    out = args.audit_dir / "comparison/dual_implementation_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
