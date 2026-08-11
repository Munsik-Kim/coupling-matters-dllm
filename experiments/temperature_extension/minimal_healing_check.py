#!/usr/bin/env python3
"""Second minimal, loop-only healing count implementation for TEMP-1R."""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path


def read(path: Path, prefix: str, source: str) -> list[dict]:
    rows = []
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist()
                         if name.startswith(prefix) and name.endswith(".json"))
        for name in members:
            record = json.loads(archive.read(name))
            trajectory = record["trajectory"]
            if source == "FROZEN_LOCAL_LIFT_1" and not (
                    int(trajectory["generation_length"]) == 16 and
                    float(trajectory["temperature"]) in (0.0, 0.2)):
                continue
            first = trajectory.get("first_split")
            split = first is not None
            ever = (bool(trajectory["reagreement_ever"]) if "reagreement_ever" in trajectory
                    else bool(split and any(bool(step.get("exact_reagreement", False))
                                            for step in record.get("steps", []))))
            final = (bool(trajectory["final_reagreement"]) if "final_reagreement" in trajectory
                     else bool(split and float(trajectory["terminal_D"]) == 0.0))
            rows.append({"source": source, "temperature": float(trajectory["temperature"]),
                         "precision": str(trajectory["precision"]),
                         "coupling_scheme": str(trajectory.get("coupling_scheme", "LIFTED_CMC")),
                         "split": split, "ever": ever, "final": final})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-temp-full-review", type=Path, required=True)
    parser.add_argument("--source-lift1-full-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = read(args.source_temp_full_review, "full_review/payload/raw/checkpoints/", "LOCAL_LIFT_TEMP_1")
    rows += read(args.source_lift1_full_review, "raw/checkpoints/", "FROZEN_LOCAL_LIFT_1")
    groups: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        key = (row["temperature"], row["precision"], row["coupling_scheme"], row["source"])
        values = groups[key]
        values[0] += 1
        values[1] += int(row["split"])
        values[2] += int(row["ever"])
        values[3] += int(row["final"])
    output = []
    for key in sorted(groups):
        total, split, ever, final = groups[key]
        output.append({"temperature": key[0], "precision": key[1], "coupling_scheme": key[2],
                       "source": key[3], "trajectory_count": total, "split_trajectory_count": split,
                       "reagreement_count": ever, "final_reagreement_count": final,
                       "split_and_reagreement_incidence": ever / total,
                       "conditional_reagreement_rate": ever / split if split else math.nan,
                       "split_and_final_reagreement_incidence": final / total,
                       "conditional_final_reagreement_rate": final / split if split else math.nan})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
