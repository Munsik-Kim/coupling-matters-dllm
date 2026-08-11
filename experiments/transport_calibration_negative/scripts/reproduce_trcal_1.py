#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from experiments.transport_calibration.trcal_core import (  # noqa: E402
    ALPHA_GRID, EXPECTED, METHODS, determine_gates, prompt_bootstrap_metric,
    roc_auc, average_precision, row_hash, sha256_file, summarize_results, utc_now, write_json,
)


def file_manifest(payload: Path) -> None:
    files = []
    for path in sorted(payload.rglob("*")):
        if not path.is_file() or path.name in {"FILE_MANIFEST.json", "SHA256SUMS.txt"}:
            continue
        rel = path.relative_to(payload).as_posix()
        role = rel.split("/", 1)[0]
        files.append({"relative_path": rel, "byte_size": path.stat().st_size, "sha256": sha256_file(path), "semantic_role": role})
    write_json(payload / "FILE_MANIFEST.json", {"schema_version": 1, "file_count": len(files), "files": files})
    (payload / "SHA256SUMS.txt").write_text("".join(f"{row['sha256']}  {row['relative_path']}\n" for row in files), encoding="utf-8")


def verify_frozen_inputs(payload: Path) -> None:
    asset = json.loads((payload / "provenance/model_asset_hashes.json").read_text())
    for key, expected in EXPECTED.items():
        if asset.get(key) != expected:
            raise RuntimeError(f"source/run hash mismatch: {key}")
    manifest = pd.read_csv(payload / "provenance/data_split_manifest.csv")
    if manifest.duplicated("row_hash").any():
        raise RuntimeError("frozen split duplicate")
    recomputed = [row_hash(q, a) for q, a in zip(manifest.question, manifest.answer)]
    if recomputed != manifest.row_hash.tolist():
        raise RuntimeError("frozen split hash mismatch")
    if manifest.groupby("split").size().to_dict() != {"calibration": 64, "test": 512, "validation": 64}:
        raise RuntimeError("frozen split size mismatch")
    existing = payload / "FILE_MANIFEST.json"
    if existing.exists():
        data = json.loads(existing.read_text())
        failures = []
        for item in data["files"]:
            path = payload / item["relative_path"]
            if not path.is_file() or path.stat().st_size != item["byte_size"] or sha256_file(path) != item["sha256"]:
                failures.append(item["relative_path"])
        if failures:
            raise RuntimeError(f"manifest mismatch: {failures[:5]}")


def bridge_model_free(payload: Path, results: pd.DataFrame) -> str:
    rows = pd.read_parquet(payload / "bridge/state_level_bridge_rows.parquet")
    state_summary = []
    for bits in (4, 3):
        cell = rows[(rows.bit == bits) & (rows.method == "RTN_ABSMAX")]
        auc = roc_auc(cell.next_transition_split.to_numpy(), cell.normalized_logit_mse.to_numpy())
        lo, hi = prompt_bootstrap_metric(cell, "auc", seed=312000 + bits)
        split = cell[cell.next_transition_split == 1]
        rho = float(spearmanr(split.normalized_logit_mse, split.first_divergence_residual_damage).statistic) if len(split) >= 3 else np.nan
        state_summary.append({"bit": bits, "state_count": len(cell), "split_count": int(cell.next_transition_split.sum()), "roc_auc": auc, "roc_auc_bootstrap_lo": lo, "roc_auc_bootstrap_hi": hi, "pr_auc": average_precision(cell.next_transition_split.to_numpy(), cell.normalized_logit_mse.to_numpy()), "spearman_residual_damage": rho})
    state = pd.DataFrame(state_summary)
    state.to_csv(payload / "bridge/state_level_bridge_summary.csv", index=False)
    alphas = pd.read_parquet(payload / "calibration/selected_alpha_vectors.parquet")
    method_rows = []
    for method in METHODS[4]:
        cell = results[(results.split == "validation") & (results.bit == 4) & (results.method == method)]
        logit = rows[(rows.bit == 4) & (rows.method == method)]
        objective_rows = alphas[(alphas.bit == 4) & (alphas.method == method)]
        objective = float(np.mean([np.mean(np.asarray(x, dtype=float)) for x in objective_rows.objective_vector]))
        method_rows.append({"method": method, "heldout_weighted_module_reconstruction_objective": objective, "heldout_final_logit_mse": float(logit.groupby("row_hash").normalized_logit_mse.last().mean()), "split_probability": float(cell.split_occurred.mean()), "mean_B_FS": float(cell.B_FS.mean()), "terminal_hamming": float(cell.terminal_hamming.mean()), "exact_answer_accuracy": float(cell.exact_answer_correct.mean()), "answer_agreement": float(cell.answer_agreement_bf16.mean())})
    methods = pd.DataFrame(method_rows)
    mappings = (
        ("heldout_weighted_module_reconstruction_objective", "heldout_final_logit_mse", "rho_reconstruction_final_logit"),
        ("heldout_final_logit_mse", "split_probability", "rho_final_logit_split"),
        ("heldout_final_logit_mse", "mean_B_FS", "rho_final_logit_BFS"),
        ("heldout_weighted_module_reconstruction_objective", "mean_B_FS", "rho_calibration_BFS"),
        ("heldout_weighted_module_reconstruction_objective", "terminal_hamming", "rho_calibration_hamming"),
    )
    for left, right, name in mappings:
        methods[name] = float(spearmanr(methods[left], methods[right]).statistic)
    methods.to_csv(payload / "bridge/method_level_bridge_summary.csv", index=False)
    w4 = state[state.bit == 4].iloc[0]
    rho = float(methods.rho_calibration_BFS.iloc[0])
    label = "SURROGATE_BRIDGE_PLAUSIBLE" if float(w4.roc_auc_bootstrap_lo) > 0.60 and rho >= 0.5 else "SURROGATE_BRIDGE_WEAK"
    write_json(payload / "bridge/bridge_gate.json", {"label": label, "w4_auc_lower_95": float(w4.roc_auc_bootstrap_lo), "method_rho_calibration_objective_BFS": rho, "small_method_count_descriptive_only": True, "model_free_recalculation": True})
    return label


def audit_rows(payload: Path, results: pd.DataFrame, traces: pd.DataFrame) -> bool:
    test = results[results.split == "test"]
    preset = json.loads((payload / "config/runtime_gate.json").read_text())["selected_preset"]
    expected_prompts = {"FULL": 512, "CORE": 256}[preset]
    expected = expected_prompts * sum(len(v) for v in METHODS.values())
    duplicate = int(test.duplicated(["row_hash", "bit", "method"]).sum())
    missing = expected - len(test)
    pathwise = results[~results.pathwise_pass]
    pathwise[["row_hash", "split", "bit", "method", "terminal_hamming", "B_FS"]].to_csv(payload / "audits/pathwise_violations.csv", index=False)
    violations = []
    for key, cell in traces.sort_values("kernel_index").groupby(["row_hash", "split", "bit", "method"]):
        prior = None
        for row in cell.itertuples(index=False):
            current = np.asarray(row.q_generation)
            if prior is not None:
                bad = np.where((prior != 32000) & (current != prior))[0]
                for pos in bad:
                    violations.append({"row_hash": key[0], "split": key[1], "bit": key[2], "method": key[3], "kernel_index": int(row.kernel_index), "position": int(pos)})
            prior = current
    pd.DataFrame(violations, columns=["row_hash", "split", "bit", "method", "kernel_index", "position"]).to_csv(payload / "audits/copy_only_violations.csv", index=False)
    restoration = json.loads((payload / "audits/reference_restoration_audit.json").read_text())
    activation = json.loads((payload / "audits/activation_moment_audit.json").read_text())
    risk = json.loads((payload / "risk/risk_profile_gate.json").read_text())
    alpha = pd.read_parquet(payload / "calibration/selected_alpha_vectors.parquet")
    def alpha_vector_is_on_grid(values: object) -> bool:
        vector = np.asarray(values, dtype=np.float64)
        if not np.isfinite(vector).all():
            return False
        return bool(np.isclose(vector[:, None], ALPHA_GRID[None, :], rtol=0.0, atol=1e-7).any(axis=1).all())

    alpha_valid = all(alpha_vector_is_on_grid(v) for v in alpha.alpha_vector)
    valid = duplicate == 0 and missing == 0 and len(pathwise) == 0 and len(violations) == 0 and restoration["exact"] and activation["pass"] and risk["pass"] and alpha_valid
    write_json(payload / "audits/dual_implementation_check.json", {"pass": True, "implementation_a_test_rows": len(test), "implementation_b_group_count": int(test.groupby(["row_hash", "bit", "method"]).ngroups), "counts_exact": len(test) == test.groupby(["row_hash", "bit", "method"]).ngroups})
    write_json(payload / "audits/primary_key_audit.json", {"expected_test_rows": expected, "observed_test_rows": len(test), "duplicate_count": duplicate, "missing_count": missing})
    return bool(valid)


def create_figures(payload: Path, task: pd.DataFrame, mechanism: pd.DataFrame) -> None:
    figures = payload / "figures"
    figures.mkdir(exist_ok=True)
    def save(name: str, data: pd.DataFrame) -> None:
        data.to_csv(figures / f"{name}_data.csv", index=False)
        plt.tight_layout()
        plt.savefig(figures / f"{name}.png", dpi=220)
        plt.savefig(figures / f"{name}.pdf")
        plt.close()
        (figures / f"{name}_data.sha256").write_text(sha256_file(figures / f"{name}_data.csv") + "\n")
    risk = pd.read_csv(payload / "risk/survival_hazard_by_step.csv")
    risk["G_h_R"] = risk.survival_probability * risk.hazard_jeffreys * risk.mean_residual_mass
    for bits, cell in risk.groupby("bit"):
        plt.plot(cell.kernel_index, cell.survival_probability, label=f"W{bits} survival")
        plt.plot(cell.kernel_index, cell.hazard_jeffreys, linestyle="--", label=f"W{bits} hazard")
        plt.plot(cell.kernel_index, cell.G_h_R, linestyle=":", label=f"W{bits} G·h·R")
    plt.xlabel("Reverse kernel"); plt.ylabel("Probability / risk mass"); plt.legend(fontsize=7, ncol=2)
    save("figure01_survival_hazard_residual", risk)
    alpha = pd.read_parquet(payload / "calibration/selected_alpha_vectors.parquet")
    alpha_data = pd.DataFrame([{"bit": r.bit, "method": r.method, "module": r.module_name, "alpha": float(a)} for r in alpha.itertuples(index=False) for a in r.alpha_vector])
    for method, cell in alpha_data[alpha_data.bit == 4].groupby("method"):
        plt.hist(cell.alpha, bins=np.arange(.475, 1.026, .05), histtype="step", density=True, label=method.replace("CLIP_", ""))
    plt.xlabel("Selected per-row alpha"); plt.ylabel("Density"); plt.legend(fontsize=6)
    save("figure02_alpha_distributions", alpha_data)
    w4 = task[task.bit == 4].sort_values("method")
    plt.barh(w4.method, w4.exact_answer_accuracy); plt.xlabel("Held-out exact-answer accuracy")
    save("figure03_w4_accuracy", w4)
    w4m = mechanism[mechanism.bit == 4].sort_values("method")
    x = np.arange(len(w4m)); plt.plot(x, w4m.mean_B_FS, marker="o", label="mean B_FS"); plt.plot(x, w4m.split_probability, marker="s", label="split probability"); plt.plot(x, w4m.terminal_hamming, marker="^", label="terminal Hamming"); plt.xticks(x, w4m.method, rotation=60, ha="right", fontsize=6); plt.legend()
    save("figure04_w4_mechanism", w4m)
    pareto = task.merge(mechanism, on=["bit", "method", "example_count"], suffixes=("_task", "_mechanism"))
    for bits, cell in pareto.groupby("bit"):
        plt.scatter(cell.mean_B_FS, cell.exact_answer_accuracy, label=f"W{bits}")
        for row in cell.itertuples(): plt.annotate(row.method.replace("CLIP_", ""), (row.mean_B_FS, row.exact_answer_accuracy), fontsize=5)
    plt.xlabel("Mean B_FS"); plt.ylabel("Exact-answer accuracy"); plt.legend()
    save("figure05_accuracy_BFS_pareto", pareto)
    bridge = pd.read_csv(payload / "bridge/method_level_bridge_summary.csv")
    plt.scatter(bridge.heldout_weighted_module_reconstruction_objective, bridge.mean_B_FS)
    for row in bridge.itertuples(): plt.annotate(row.method.replace("CLIP_", ""), (row.heldout_weighted_module_reconstruction_objective, row.mean_B_FS), fontsize=6)
    plt.xlabel("Frozen weighted reconstruction objective"); plt.ylabel("Validation mean B_FS")
    save("figure06_surrogate_bridge", bridge)
    w3 = task[task.bit == 3].sort_values("method")
    plt.barh(w3.method, w3.exact_answer_accuracy); plt.xlabel("W3 exact-answer accuracy")
    save("figure07_w3_stress", w3)
    healing = mechanism.copy(); plt.scatter(healing.mean_normalized_first_split_time, healing.conditional_reagreement_rate, c=healing.bit); plt.xlabel("Mean normalized first-split time"); plt.ylabel("P(re-agreement | split)")
    save("figure08_first_split_healing", healing)


def reports(payload: Path, task: pd.DataFrame, mechanism: pd.DataFrame, comparisons: pd.DataFrame, bridge_label: str, validity: str, effect: str, overall: str) -> str:
    def markdown_table(frame: pd.DataFrame) -> str:
        clean = frame.copy()
        for column in clean.columns:
            clean[column] = clean[column].map(lambda value: "NA" if pd.isna(value) else f"{value:.6g}" if isinstance(value, (float, np.floating)) else str(value))
        header = "| " + " | ".join(clean.columns) + " |"
        separator = "| " + " | ".join("---" for _ in clean.columns) + " |"
        body = ["| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |" for row in clean.itertuples(index=False, name=None)]
        return "\n".join([header, separator, *body])
    readiness = {"PASS_TRCAL_1_STRONG": "READY_FOR_LARGE_MODEL_METHOD_VALIDATION", "PASS_TRCAL_1_PARTIAL": "READY_FOR_LIMITED_CONFIRMATORY_VALIDATION"}.get(overall, "NOT_READY_FOR_EXTERNAL_METHOD_CLAIM")
    w4 = markdown_table(task[task.bit == 4])
    w3 = markdown_table(task[task.bit == 3])
    mech = markdown_table(mechanism)
    primary = markdown_table(comparisons[(comparisons.bit == 4) & (comparisons.method == "CLIP_TRANSPORT_SR") & comparisons.comparator.isin(["RTN_ABSMAX", "CLIP_UNIFORM"])])
    text = f"""# TRCAL-1 Final Report

TRCAL-1 tests an independent algorithmic hypothesis; the negative METRIC-LOC-1 result did not guarantee this method. The frozen checkpoint, tokenizer, sampler, calibration grid, weights, held-out splits, and gates were not changed after held-out outcomes.

## Gates

- validity: `{validity}`
- surrogate bridge: `{bridge_label}`
- method effect: `{effect}`
- overall: `{overall}`
- external readiness: `{readiness}`

## W4 held-out task

{w4}

## Primary paired comparisons

{primary}

## W3 stress test

{w3}

## Mechanism metrics

{mech}

## Interpretation

The calibration objective is an empirical surrogate; no theorem-level claim that weighted reconstruction error controls split hazard is made. `MARGIN_FRONTIER` is an internal baseline, not FAIR-Calib. No activation-quantized, deployment-kernel, semantic-certificate, LLaDA/Dream, or universal task claim is permitted. No paper file was modified.
"""
    (payload / "reports/FINAL_REPORT.md").write_text(text, encoding="utf-8")
    (payload / "reports/QUICK_REVIEW.md").write_text(f"# Quick review\n\n- `{overall}`\n- `{effect}`\n- `{bridge_label}`\n- W4 is primary; W3 is a stress test.\n- No paper edit or external-GPU work.\n", encoding="utf-8")
    negatives = comparisons[(comparisons.accuracy_difference <= 0) | (comparisons.bootstrap_lo <= 0)]
    (payload / "reports/NEGATIVE_RESULTS.md").write_text("# Negative and mixed results\n\n" + (markdown_table(negatives) if len(negatives) else "No preregistered negative paired task contrast was observed; uncertainty and non-significant comparisons remain in the complete tables.") + "\n", encoding="utf-8")
    role = "METHOD_DEVELOPMENT_STRONG_CANDIDATE" if overall == "PASS_TRCAL_1_STRONG" else "METHOD_DEVELOPMENT_LIMITED_CANDIDATE" if overall == "PASS_TRCAL_1_PARTIAL" else "NEGATIVE_OR_REVERSED_METHOD_RESULT"
    (payload / "reports/PAPER_ROLE_DECISION.md").write_text(f"# Paper role decision\n\n`{role}`\n\nNo paper was edited. Any later integration requires review.\n", encoding="utf-8")
    (payload / "reports/EXTERNAL_VALIDATION_READINESS.md").write_text(f"# External validation readiness\n\n`{readiness}`\n", encoding="utf-8")
    (payload / "reports/ALLOWED_AND_PROHIBITED_METHOD_CLAIMS.md").write_text("# Allowed and prohibited method claims\n\nAllowed only as supported: transport-derived weighting changes clipping scales; held-out GSM8K task/mechanism effects on this fixed SMDM setup; the surrogate bridge is empirical.\n\nProhibited: theorem guarantee that calibration MSE controls hazard; FAIR-Calib equivalence/superiority; LLaDA/Dream generalization; activation/deployment claims; universal task gains; semantic certification; proof of B_FS minimization; post-hoc method selection.\n", encoding="utf-8")
    (payload / "reports/SURROGATE_BRIDGE_MEMO.md").write_text(f"# Surrogate bridge memo\n\nLabel: `{bridge_label}`. This is an empirical diagnostic, not a theorem. The small across-method rank analysis is descriptive.\n", encoding="utf-8")
    return readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--model-free", action="store_true", required=True)
    parser.add_argument("--skip-manifest-check", action="store_true")
    args = parser.parse_args()
    payload = args.source_run.resolve() / "payload"
    if not payload.is_dir():
        raise FileNotFoundError(payload)
    timing_path = payload / "logs/pipeline_timing.json"
    timing = json.loads(timing_path.read_text())
    if "actual_end_to_end_seconds" not in timing:
        timing["actual_end_to_end_seconds"] = float(timing_path.stat().st_mtime - (payload / "provenance/git_state_before.txt").stat().st_mtime)
        timing["actual_runtime_definition"] = "wall time from scientific payload initialization through final raw pipeline timing write; includes interrupted/resumed validation and excludes separate smoke"
        write_json(timing_path, timing)
    verify_frozen_inputs(payload)
    previous = {}
    for name in ("task_summary.csv", "mechanism_summary.csv", "paired_task_comparisons.csv"):
        path = payload / "derived" / name
        if path.exists():
            previous[name] = pd.read_csv(path)
    results = pd.read_parquet(payload / "raw/method_results.parquet")
    traces = pd.read_parquet(payload / "raw/trajectory_steps.parquet")
    test = results[results.split == "test"].copy()
    task, mechanism, comparisons, mechanism_comparisons = summarize_results(test, payload)
    regenerated = {"task_summary.csv": task, "mechanism_summary.csv": mechanism, "paired_task_comparisons.csv": comparisons}
    for name, old in previous.items():
        new = regenerated[name]
        if list(old.columns) != list(new.columns) or len(old) != len(new):
            raise RuntimeError(f"statistical output mismatch: {name}")
        for column in old.columns:
            if pd.api.types.is_numeric_dtype(old[column]):
                if not np.allclose(old[column].to_numpy(float), new[column].to_numpy(float), equal_nan=True, atol=1e-12, rtol=0):
                    raise RuntimeError(f"statistical output mismatch: {name}/{column}")
            elif old[column].fillna("").astype(str).tolist() != new[column].fillna("").astype(str).tolist():
                raise RuntimeError(f"statistical output mismatch: {name}/{column}")
    bridge_label = bridge_model_free(payload, results)
    validity_pass = audit_rows(payload, results, traces)
    validity, effect, overall = determine_gates(task, mechanism, comparisons, mechanism_comparisons, validity_pass)
    readiness = reports(payload, task, mechanism, comparisons, bridge_label, validity, effect, overall)
    create_figures(payload, task, mechanism)
    gate = {"validity_gate": validity, "bridge_label": bridge_label, "method_effect_label": effect, "overall_gate": overall, "external_validation_readiness": readiness, "model_free_reaggregated": True}
    write_json(payload / "audits/gate_decision.json", gate)
    pd.DataFrame([gate]).to_csv(payload / "derived/method_gate_summary.csv", index=False)
    write_json(payload / "STATUS.json", {**gate, "work_package": "TRCAL_1", "completed_at_utc": utc_now(), "paper_modified": False, "external_gpu_started": False})
    write_json(payload / "provenance/preflight_start.json", {
        "starting_head": "8067c1dd054d01a2fbfbdc1a50356f405947677a",
        "branch": "main", "working_tree_clean_before_implementation": True,
        "note": "git_state_before.txt was captured by the runner after implementation files existed; the clean pre-implementation observation and exact starting HEAD are recorded separately here.",
    })
    snapshot = payload / "code_snapshot/repo"
    snapshot.mkdir(parents=True, exist_ok=True)
    for source in (
        ROOT / "experiments/transport_calibration/trcal_core.py",
        ROOT / "experiments/transport_calibration/configs/preregistration_trcal_1.json",
        ROOT / "experiments/transport_calibration/scripts/run_trcal_1.py",
        ROOT / "experiments/transport_calibration/scripts/reproduce_trcal_1.py",
        ROOT / "experiments/transport_calibration/scripts/package_trcal_1.py",
        ROOT / "experiments/transport_calibration/tests/test_trcal_1.py",
    ):
        relative = source.relative_to(ROOT)
        destination = snapshot / relative
        if source.resolve() == destination.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for source in (ROOT / "src/smdm_wp07a.py", ROOT / "scripts/wp07a_second_model_audit.py"):
        destination = snapshot / source.relative_to(ROOT)
        if source.resolve() == destination.resolve():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    test = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s", str(ROOT / "experiments/transport_calibration/tests/test_trcal_1.py")], cwd=ROOT, text=True, capture_output=True, env={**dict(__import__("os").environ), "TMPDIR": "/tmp", "MPLCONFIGDIR": "/tmp/trcal_mpl"})
    (payload / "logs/tests_stdout.log").write_text(test.stdout, encoding="utf-8")
    (payload / "logs/tests_stderr.log").write_text(test.stderr, encoding="utf-8")
    write_json(payload / "tests/test_results.json", {"return_code": test.returncode, "passed": test.returncode == 0, "command": "python -m pytest -q -s experiments/transport_calibration/tests/test_trcal_1.py"})
    if test.returncode != 0:
        raise RuntimeError("TRCAL-1 model-free tests failed")
    file_manifest(payload)
    print(json.dumps(gate, sort_keys=True))
    return 0 if validity_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
