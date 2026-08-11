#!/usr/bin/env python3
"""Independent direct-PyArrow headline cross-check for WP07C."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

HORIZONS = ["H4", "H8", "H12", "H16", "H24", "H32", "FULL"]
SEVERITIES = ["W8", "W6", "W4"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = defaultdict(lambda: [0.0, 0.0, 0])
    prompt_values = defaultdict(list)
    violations = 0
    for path in sorted((args.payload_dir / "raw/horizon_endpoints").glob("part-*.parquet")):
        table = pq.read_table(path, columns=["family", "prompt_id", "severity", "horizon", "D", "B_FS", "pathwise_check"])
        for family, prompt, severity, horizon, d_value, bound, passed in zip(*(table[name].to_pylist() for name in table.column_names), strict=True):
            if not passed:
                violations += 1
            if family == "CMC":
                prompt_values[(prompt, severity, horizon)].append((float(d_value), float(bound)))
    for (prompt, severity, horizon), rows in prompt_values.items():
        if len(rows) != 2:
            raise RuntimeError(f"Expected two CMC draws: {prompt}/{severity}/{horizon}")
        key = (severity, horizon)
        values[key][0] += sum(row[0] for row in rows) / 2
        values[key][1] += sum(row[1] for row in rows) / 2
        values[key][2] += 1
    radius = math.sqrt(math.log(49 / 0.05) / (2 * 128))
    headline = {}
    absolute = []
    for severity in SEVERITIES:
        d_bounds, b_bounds = {}, {}
        for horizon in HORIZONS:
            total_d, total_b, count = values[(severity, horizon)]
            if count != 128:
                raise RuntimeError(f"Prompt count mismatch: {severity}/{horizon}/{count}")
            mean_d, mean_b = total_d / count, total_b / count
            d_bounds[horizon], b_bounds[horizon] = min(1.0, mean_d + radius), min(1.0, mean_b + radius)
            if horizon == "FULL":
                headline[severity] = {"mean_D_CMC": mean_d, "mean_B_FS_CMC": mean_b, "UCB_D_CMC": d_bounds[horizon], "UCB_B_FS_CMC": b_bounds[horizon]}
        for route, bounds in (("D_CMC", d_bounds), ("B_FS_CMC", b_bounds)):
            for epsilon in (0.25, 0.5, 0.75):
                selected = "NONE"
                for horizon in HORIZONS:
                    if bounds[horizon] > epsilon:
                        break
                    selected = horizon
                absolute.append({"severity": severity, "route": route, "epsilon": epsilon, "certified_horizon_95": selected})
    result = {"headline": headline, "hoeffding_radius": radius, "absolute_horizons": absolute, "pathwise_violation_count": violations, "loading_route": "direct_pyarrow_python_dictionary"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
