#!/usr/bin/env python3
"""Minimal independent headline check for WP07B using PyArrow row loops."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

HORIZONS = ["H4", "H8", "H12", "H16", "H24", "H32", "FULL"]
SEVERITIES = ["W8", "W7", "W6", "W5", "W4", "W3"]


def rows(directory: Path):
    for path in sorted(directory.glob("part-*.parquet")):
        table = pq.read_table(path)
        for row in table.to_pylist():
            yield row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = args.payload_dir.resolve()
    sums = defaultdict(float); counts = defaultdict(int); prompt_sums = defaultdict(float); prompt_counts = defaultdict(int)
    violations = 0
    for row in rows(payload / "raw/horizon_endpoints"):
        if not bool(row["pathwise_check"]) or float(row["D"]) > float(row["B_FS"]) + 1e-12:
            violations += 1
        if row["family"] != "CMC":
            continue
        for metric, column in (("D_CMC", "D"), ("B_FS_CMC", "B_FS")):
            key = (row["severity"], row["horizon"], metric)
            sums[key] += float(row[column]); counts[key] += 1
            pkey = (row["prompt_id"], row["severity"], row["horizon"], metric)
            prompt_sums[pkey] += float(row[column]); prompt_counts[pkey] += 1
    direct = {"|".join(key): sums[key] / counts[key] for key in sorted(sums)}
    prompt_means = defaultdict(list)
    for key, value in prompt_sums.items():
        _, severity, horizon, metric = key
        prompt_means[(severity, horizon, metric)].append(value / prompt_counts[key])
    prompt_aggregates = {"|".join(key): sum(values) / len(values) for key, values in sorted(prompt_means.items())}
    primary = pd.read_csv(payload / "derived/cmc_certificate_cell_summary.csv").set_index(["severity", "horizon"])
    differences = []
    for severity in SEVERITIES:
        for horizon in HORIZONS:
            for metric, column in (("D_CMC", "mean_D_CMC"), ("B_FS_CMC", "mean_B_FS_CMC")):
                key = f"{severity}|{horizon}|{metric}"
                differences.append(abs(prompt_aggregates[key] - float(primary.loc[(severity, horizon), column])))
    full = {key: value for key, value in prompt_aggregates.items() if "|FULL|" in key}
    radius = math.sqrt(math.log(91 / 0.05) / (2 * 64))
    result = {
        "implementation": "direct PyArrow row iteration and Python dictionaries",
        "pathwise_violation_count": violations,
        "full_horizon_prompt_means": full,
        "hoeffding_radius": radius,
        "maximum_absolute_difference": max(differences, default=0.0),
        "primary_comparison_count": len(differences),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if violations == 0 and result["maximum_absolute_difference"] <= 1e-12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
