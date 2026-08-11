#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

SCRIPT = Path(__file__).resolve()
PROJECT = SCRIPT.parents[3]
RUNNER = SCRIPT.with_name("run_metric_loc_1.py")
SECOND = SCRIPT.with_name("minimal_second_check.py")

LOAD_BEARING = [
    "metrics/cert3_metric_summary.csv",
    "metrics/wp07c_metric_summary.csv",
    "metrics/wp07d_metric_rows.csv",
    "metrics/local_lift_metric_summary.csv",
    "metrics/saturation_summary.csv",
    "metrics/bit_ordering_summary.csv",
    "metrics/gsm8k_task_relevance.csv",
    "lower_bound/transport_lower_bounds.csv",
    "lower_bound/descriptive_plugin_coordinate_ot.csv",
    "lower_bound/transport_localization_table.csv",
    "audits/theory_synthetic_test_results.csv",
    "audits/gate_decision.json",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args: argparse.Namespace) -> int:
    if not args.model_free:
        raise RuntimeError("Reproduction requires --model-free")
    source_root = args.source_root.resolve()
    run_dir = args.run_dir.resolve()
    command = [sys.executable, str(RUNNER), "--project-root", str(source_root), "--run-dir", str(run_dir), "--model-free", "--resume"]
    runner = subprocess.run(command, cwd=source_root, text=True, capture_output=True)
    if runner.returncode != 0:
        print(runner.stdout)
        print(runner.stderr, file=sys.stderr)
        return runner.returncode
    second = subprocess.run([sys.executable, str(SECOND), "--payload-dir", str(run_dir / "payload")], cwd=source_root, text=True, capture_output=True)
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s", str(PROJECT / "experiments/metric_localization/tests")], cwd=source_root, text=True, capture_output=True)
    comparisons = []
    if args.reference_run:
        reference = args.reference_run.resolve() / "payload"
        candidate = run_dir / "payload"
        for relative in LOAD_BEARING:
            left = reference / relative
            right = candidate / relative
            comparisons.append({"path": relative, "reference_sha256": digest(left), "reproduced_sha256": digest(right), "match": left.read_bytes() == right.read_bytes()})
    verification = {
        "schema_version": 1,
        "model_execution": False,
        "gpu_execution": False,
        "runner_return_code": runner.returncode,
        "second_implementation_return_code": second.returncode,
        "pytest_return_code": tests.returncode,
        "load_bearing_comparisons": comparisons,
        "pass": runner.returncode == 0 and second.returncode == 0 and tests.returncode == 0 and all(row["match"] for row in comparisons),
    }
    tests_dir = run_dir / "payload/tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "reproduction_verification.json").write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (tests_dir / "pytest_output.txt").write_text(tests.stdout + "\n" + tests.stderr, encoding="utf-8")
    print(json.dumps(verification, indent=2))
    return 0 if verification["pass"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--reference-run", type=Path)
    parser.add_argument("--model-free", action="store_true")
    raise SystemExit(main(parser.parse_args()))
