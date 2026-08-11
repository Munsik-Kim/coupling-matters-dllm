#!/usr/bin/env python3
"""Reproduce all WP07D-LOCAL derived results without model execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest

HORIZON_ORDER = ["H8", "H16", "H32", "FULL"]
SEVERITY_ORDER = ["W8", "W6", "W4"]
PRECISION_ORDER = ["BF16", "W8", "W6", "W4"]
K = 50
DELTA = 0.05


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_parts(directory: Path) -> pd.DataFrame:
    files = sorted(directory.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No raw shards: {directory}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def levenshtein(a: list[int], b: list[int]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(value) for value in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in frame.itertuples(index=False, name=None):
        values = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append("NA" if not math.isfinite(float(value)) else f"{float(value):.8g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def bootstrap_paired(values: pd.DataFrame, seed: int = 290000) -> tuple[float, float]:
    piv = values.pivot_table(index="row_id", columns="precision", values="exact_numeric_correct", aggfunc="mean")
    if "BF16" not in piv or len(piv) == 0:
        return math.nan, math.nan
    q = str(values.precision.drop_duplicates().loc[lambda x: x != "BF16"].iloc[0])
    diffs = (piv[q] - piv["BF16"]).dropna().to_numpy(float)
    rng = np.random.default_rng(seed)
    means = np.mean(rng.choice(diffs, size=(5000, len(diffs)), replace=True), axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def generate(payload: Path) -> dict[str, Any]:
    derived = payload / "derived"
    plots = derived / "plots"
    report_dir = payload / "report"
    derived.mkdir(exist_ok=True)
    plots.mkdir(exist_ok=True)
    report_dir.mkdir(exist_ok=True)

    endpoints = read_parts(payload / "raw/origin_horizon_endpoints")
    expected_endpoints = 2 * 2 * 3 * 32 * 2 * 4
    if len(endpoints) != expected_endpoints:
        raise RuntimeError(f"Origin endpoint row count {len(endpoints)} != {expected_endpoints}")
    key = ["family", "seed", "severity", "prompt_id", "generation_length", "horizon"]
    if endpoints.duplicated(key).any():
        raise RuntimeError("Duplicate origin endpoint primary key")
    if (endpoints.D > endpoints.B_FS + 1e-12).any():
        raise RuntimeError("Pathwise certificate violation")

    grouped = endpoints.groupby(["family", "generation_length", "severity", "horizon"], sort=False).agg(n=("D", "size"), mean_D=("D", "mean"), mean_B_FS=("B_FS", "mean"), split_rate=("split_by_horizon", "mean"), median_inflation=("D", lambda _: math.nan)).reset_index()
    for idx, row in grouped.iterrows():
        cell = endpoints[(endpoints.family == row.family) & (endpoints.generation_length == row.generation_length) & (endpoints.severity == row.severity) & (endpoints.horizon == row.horizon)]
        positive = cell[cell.D > 0]
        grouped.loc[idx, "median_inflation"] = float(np.median(positive.B_FS / positive.D)) if len(positive) else math.nan
    grouped.to_csv(derived / "origin_certificate_summary.csv", index=False)

    radius64 = math.sqrt(math.log(K / DELTA) / (2 * 64))
    radius32 = math.sqrt(math.log(K / DELTA) / (2 * 32))
    cmc = grouped[grouped.family == "CMC"].copy()
    cmc["hoeffding_radius_n64"] = radius64
    cmc["UCB_D"] = np.minimum(1.0, cmc.mean_D + radius64)
    cmc["UCB_B_FS"] = np.minimum(1.0, cmc.mean_B_FS + radius64)
    cmc["prompt_block_radius_n32"] = radius32
    cmc["prompt_block_UCB_D"] = np.minimum(1.0, cmc.mean_D + radius32)
    cmc["prompt_block_UCB_B_FS"] = np.minimum(1.0, cmc.mean_B_FS + radius32)
    cmc.to_csv(derived / "origin_certificate_ucb.csv", index=False)

    paired = endpoints.pivot_table(index=["prompt_id", "seed", "generation_length", "severity", "horizon"], columns="family", values=["D", "B_FS"]).reset_index()
    paired.columns = ["_".join(col).strip("_") if isinstance(col, tuple) else col for col in paired.columns]
    paired["D_CMC_minus_CRN"] = paired["D_CMC"] - paired["D_inverse_CDF_CRN"]
    paired["B_FS_CMC_minus_CRN"] = paired["B_FS_CMC"] - paired["B_FS_inverse_CDF_CRN"]
    paired.to_csv(derived / "origin_cmc_vs_crn.csv", index=False)

    precision_rows = []
    for length in (16, 64):
        for horizon in HORIZON_ORDER:
            cell = cmc[(cmc.generation_length == length) & (cmc.horizon == horizon)].set_index("severity")
            dvals = [float(cell.loc[s, "mean_D"]) for s in SEVERITY_ORDER]
            bvals = [float(cell.loc[s, "mean_B_FS"]) for s in SEVERITY_ORDER]
            precision_rows.append({"generation_length": length, "horizon": horizon, "D_W8": dvals[0], "D_W6": dvals[1], "D_W4": dvals[2], "D_order_pass": dvals[0] <= dvals[1] + 1e-15 <= dvals[2] + 1e-15, "BFS_W8": bvals[0], "BFS_W6": bvals[1], "BFS_W4": bvals[2], "BFS_order_pass": bvals[0] <= bvals[1] + 1e-15 <= bvals[2] + 1e-15})
    precision = pd.DataFrame(precision_rows)
    precision.to_csv(derived / "origin_precision_ordering.csv", index=False)

    first_split = endpoints.groupby(["family", "generation_length", "severity", "horizon", "first_split_kernel"], dropna=False).size().rename("count").reset_index()
    first_split["fraction"] = first_split["count"] / first_split.groupby(["family", "generation_length", "severity", "horizon"])["count"].transform("sum")
    first_split.to_csv(derived / "origin_split_survival.csv", index=False)

    step_events = read_parts(payload / "raw/origin_step_events")
    progress = step_events.groupby(["family", "generation_length", "severity", "kernel_index"]).agg(mean_fp_masked_fraction=("fp_masked_fraction", "mean"), mean_q_masked_fraction=("q_masked_fraction", "mean"), mean_fp_committed=("fp_cumulative_committed", "mean"), mean_q_committed=("q_cumulative_committed", "mean"), mean_hamming=("hamming", "mean"), mean_product_split_hazard=("product_split_hazard", "mean")).reset_index()
    progress["normalized_generation_progress"] = progress.kernel_index / 32
    progress.to_csv(derived / "origin_progress_analysis.csv", index=False)

    prompt_effects = endpoints[endpoints.family == "CMC"].groupby(["prompt_id", "generation_length", "severity", "horizon"]).agg(mean_D=("D", "mean"), mean_B_FS=("B_FS", "mean")).reset_index()
    seed_effects = endpoints[endpoints.family == "CMC"].groupby(["seed", "generation_length", "severity", "horizon"]).agg(mean_D=("D", "mean"), mean_B_FS=("B_FS", "mean")).reset_index()
    prompt_effects.to_csv(derived / "origin_prompt_effects.csv", index=False)
    seed_effects.to_csv(derived / "origin_seed_effects.csv", index=False)

    reference = read_parts(payload / "raw/origin_bf16_reference")
    ref_h = reference[reference["horizon"].notna()].copy() if "horizon" in reference else reference
    # Directory contains trajectory rows and horizon rows; only horizon shards have a horizon column.
    if "horizon" not in reference.columns:
        raise RuntimeError("BF16 reference horizons missing")
    ref_h = reference.dropna(subset=["horizon"])
    ref_piv = ref_h.pivot_table(index=["prompt_id", "generation_length", "horizon"], columns="seed", values="state", aggfunc="first").reset_index()
    delta_rows = []
    for row in ref_piv.itertuples(index=False):
        left = np.asarray(getattr(row, "_3", None)) if False else None
        values = row._asdict()
        seeds = [column for column in ref_piv.columns if isinstance(column, (int, np.integer))]
        if len(seeds) != 2:
            continue
        a, b = np.asarray(values[str(seeds[0])] if str(seeds[0]) in values else ref_piv.loc[len(delta_rows), seeds[0]]), np.asarray(values[str(seeds[1])] if str(seeds[1]) in values else ref_piv.loc[len(delta_rows), seeds[1]])
        delta_rows.append({"prompt_id": values["prompt_id"], "generation_length": values["generation_length"], "horizon": values["horizon"], "Delta_ref": float(np.mean(a != b))})
    # Pandas namedtuple handling of integer columns is fragile; deterministic merge is clearer.
    if len(delta_rows) != 32 * 2 * 4:
        left = ref_h[ref_h.seed == 260746].rename(columns={"state": "state_a"})
        right = ref_h[ref_h.seed == 260747].rename(columns={"state": "state_b"})
        merged_ref = left.merge(right, on=["prompt_id", "generation_length", "horizon"], validate="one_to_one")
        delta_rows = [{"prompt_id": row.prompt_id, "generation_length": row.generation_length, "horizon": row.horizon, "Delta_ref": float(np.mean(np.asarray(row.state_a) != np.asarray(row.state_b)))} for row in merged_ref.itertuples()]
    delta = pd.DataFrame(delta_rows)
    delta_summary = delta.groupby(["generation_length", "horizon"]).agg(n=("Delta_ref", "size"), mean_Delta_ref=("Delta_ref", "mean"), exact_match_rate=("Delta_ref", lambda x: np.mean(np.asarray(x) == 0))).reset_index()
    delta_summary["hoeffding_LCB"] = np.maximum(0, delta_summary.mean_Delta_ref - radius32)
    delta_summary.to_csv(derived / "origin_intrinsic_diversity.csv", index=False)

    sync = cmc.merge(delta_summary[["generation_length", "horizon", "mean_Delta_ref"]], on=["generation_length", "horizon"])
    sync["synchronization_retention_D"] = np.where(sync.mean_Delta_ref > 0, 1 - sync.mean_D / sync.mean_Delta_ref, np.nan)
    sync["synchronization_retention_BFS"] = np.where(sync.mean_Delta_ref > 0, 1 - sync.mean_B_FS / sync.mean_Delta_ref, np.nan)
    sync.to_csv(derived / "origin_synchronization_retention.csv", index=False)

    # Track A preregistered gates use FULL cells for H-A1/H-A2 and four W8/W6 length cells for H-A3.
    full_order = precision[precision.horizon == "FULL"]
    h_a1 = bool(full_order.D_order_pass.all())
    h_a2 = bool(full_order.BFS_order_pass.all())
    cmp_full = paired[(paired.horizon == "FULL") & paired.severity.isin(["W8", "W6"])]
    h_a3 = bool(cmp_full.groupby(["generation_length", "severity"]).D_CMC_minus_CRN.mean().lt(0).all())
    h_a4 = bool((endpoints.D <= endpoints.B_FS + 1e-12).all())
    full_cmc = endpoints[(endpoints.family == "CMC") & (endpoints.horizon == "FULL")]
    prompt_share = full_cmc.groupby("prompt_id").B_FS.sum()
    max_share = float(prompt_share.max() / prompt_share.sum()) if prompt_share.sum() > 0 else 0.0
    hard = json.loads((payload / "audits/pathwise_checks.json").read_text())["pass"]
    if not hard:
        track_a_gate = "FAIL_SMDM_AUDIT"
    elif h_a1 and h_a2 and h_a3 and h_a4 and max_share <= 0.5:
        track_a_gate = "PASS_SMDM_SECOND_MODEL_CONFIRMATORY"
    elif h_a3 and h_a4:
        track_a_gate = "PASS_SMDM_COUPLING_DIRECTION_ONLY"
    else:
        track_a_gate = "VALID_SMDM_RESULT_DIFFERS"
    track_a = {"gate": track_a_gate, "H_A1": h_a1, "H_A2": h_a2, "H_A3": h_a3, "H_A4": h_a4, "max_single_prompt_share": max_share, "fixed_suite_scope": "p032-p063 only; no prompt-population generalization"}
    write_json(derived / "track_a_gate.json", track_a)

    task = read_parts(payload / "raw/gsm8k_outputs")
    task_key = ["row_id", "decoding_seed", "precision"]
    if task.duplicated(task_key).any():
        raise RuntimeError("Duplicate GSM8K task row")
    task_summary = task.groupby("precision").agg(rows=("row_id", "size"), examples=("row_id", "nunique"), seeds=("decoding_seed", "nunique"), exact_accuracy=("exact_numeric_correct", "mean"), extraction_success=("extraction_success", "mean"), generation_failure_rate=("failure_category", lambda x: np.mean(np.asarray(x) != "none")), mean_output_length=("output_token_length", "mean"), mean_repetition=("adjacent_repetition_rate", "mean")).reindex(PRECISION_ORDER).reset_index()
    task_summary.to_csv(derived / "gsm8k_accuracy_summary.csv", index=False)

    bf = task[task.precision == "BF16"][["row_id", "decoding_seed", "exact_numeric_correct", "generated_token_ids", "generated_text"]].rename(columns={"exact_numeric_correct": "bf16_correct", "generated_token_ids": "bf16_tokens", "generated_text": "bf16_text"})
    paired_rows = []
    for precision in SEVERITY_ORDER:
        q = task[task.precision == precision].merge(bf, on=["row_id", "decoding_seed"], validate="one_to_one")
        for row in q.itertuples():
            edit = levenshtein(list(row.generated_token_ids), list(row.bf16_tokens))
            paired_rows.append({"row_id": row.row_id, "decoding_seed": row.decoding_seed, "precision": precision, "q_correct": bool(row.exact_numeric_correct), "bf16_correct": bool(row.bf16_correct), "accuracy_difference": int(row.exact_numeric_correct) - int(row.bf16_correct), "final_answer_agreement": row.predicted_answer == task[(task.row_id == row.row_id) & (task.decoding_seed == row.decoding_seed) & (task.precision == "BF16")].predicted_answer.iloc[0], "normalized_token_edit_distance": edit / max(len(row.generated_token_ids), len(row.bf16_tokens), 1), "text_exact_match": row.generated_text == row.bf16_text})
    paired_task = pd.DataFrame(paired_rows)
    paired_summary_rows = []
    for precision in SEVERITY_ORDER:
        cell = paired_task[paired_task.precision == precision]
        bootstrap_input = pd.concat([task[task.precision == "BF16"], task[task.precision == precision]])
        low, high = bootstrap_paired(bootstrap_input, seed=291000 + int(precision[1:]))
        discordant_q_win = int(((cell.q_correct == 1) & (cell.bf16_correct == 0)).sum())
        discordant_fp_win = int(((cell.q_correct == 0) & (cell.bf16_correct == 1)).sum())
        mcnemar_p = float(binomtest(min(discordant_q_win, discordant_fp_win), discordant_q_win + discordant_fp_win, 0.5).pvalue) if discordant_q_win + discordant_fp_win else 1.0
        paired_summary_rows.append({"precision": precision, "paired_rows": len(cell), "mean_accuracy_difference": cell.accuracy_difference.mean(), "bootstrap_95_low": low, "bootstrap_95_high": high, "answer_agreement": cell.final_answer_agreement.mean(), "mean_normalized_token_edit_distance": cell.normalized_token_edit_distance.mean(), "mcnemar_q_wins": discordant_q_win, "mcnemar_bf16_wins": discordant_fp_win, "mcnemar_exact_p": mcnemar_p})
    paired_task.to_csv(derived / "gsm8k_paired_rows.csv", index=False)
    pd.DataFrame(paired_summary_rows).to_csv(derived / "gsm8k_paired_differences.csv", index=False)
    task.groupby(["precision", "failure_category"]).size().rename("count").reset_index().to_csv(derived / "gsm8k_failure_analysis.csv", index=False)
    task.groupby(["decoding_seed", "precision"]).agg(accuracy=("exact_numeric_correct", "mean"), extraction=("extraction_success", "mean")).reset_index().to_csv(derived / "gsm8k_seed_sensitivity.csv", index=False)

    bf_summary = task_summary[task_summary.precision == "BF16"].iloc[0]
    complete = task.groupby(["decoding_seed", "precision"]).row_id.nunique().eq(100).all()
    task_accs = task_summary.set_index("precision").exact_accuracy
    nonmonotone = not (task_accs["W8"] >= task_accs["W6"] >= task_accs["W4"])
    material = bool(np.max(np.abs(task_accs[["W8", "W6", "W4"]] - task_accs["BF16"])) >= 0.10)
    if not complete:
        track_b_gate = "FAIL_TASK_AUDIT"
    elif bf_summary.exact_accuracy < 0.20 or bf_summary.extraction_success < 0.90:
        track_b_gate = "TASK_RESULT_FLOOR"
    elif nonmonotone or material:
        track_b_gate = "VALID_TASK_DEGRADATION_RESULT"
    else:
        track_b_gate = "PASS_GSM8K_DESCRIPTIVE_RELEVANCE"
    track_b = {"gate": track_b_gate, "complete_paired_blocks": bool(complete), "bf16_accuracy": float(bf_summary.exact_accuracy), "bf16_extraction_success": float(bf_summary.extraction_success), "accuracy_nonmonotone": bool(nonmonotone), "material_absolute_difference_threshold_0_10": material, "certificate_claim": False}
    write_json(derived / "track_b_gate.json", track_b)

    if track_a_gate == "FAIL_SMDM_AUDIT" or track_b_gate == "FAIL_TASK_AUDIT":
        overall_gate = "FAIL_WP07D_LOCAL"
    elif track_a_gate in {"PASS_SMDM_SECOND_MODEL_CONFIRMATORY", "PASS_SMDM_COUPLING_DIRECTION_ONLY"} and track_b_gate in {"PASS_GSM8K_DESCRIPTIVE_RELEVANCE", "VALID_TASK_DEGRADATION_RESULT"}:
        overall_gate = "PASS_LOCAL_SECOND_MODEL_PACKAGE"
    elif track_a_gate in {"PASS_SMDM_SECOND_MODEL_CONFIRMATORY", "PASS_SMDM_COUPLING_DIRECTION_ONLY"}:
        overall_gate = "PASS_CERTIFICATE_ONLY_TASK_INVALID"
    else:
        overall_gate = "VALID_SECOND_MODEL_RESULT_DIFFERS"
    overall = {"gate": overall_gate, "track_a_gate": track_a_gate, "track_b_gate": track_b_gate, "numerical_estimands_pooled": False}
    write_json(derived / "overall_gate.json", overall)

    table_candidates = pd.concat([cmc.assign(table="origin_certificate"), task_summary.assign(table="gsm8k_descriptive")], ignore_index=True, sort=False)
    table_candidates.to_csv(derived / "paper_table_candidates.csv", index=False)

    # Compact plots, intentionally separated by track.
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for length, ax in zip((16, 64), axes):
        for severity in SEVERITY_ORDER:
            cell = cmc[(cmc.generation_length == length) & (cmc.severity == severity)].set_index("horizon").loc[HORIZON_ORDER]
            ax.plot(HORIZON_ORDER, cell.mean_D, marker="o", label=f"{severity} D")
            ax.plot(HORIZON_ORDER, cell.mean_B_FS, marker="x", linestyle="--", label=f"{severity} B_FS")
        ax.set_title(f"Origin length {length}")
        ax.set_ylim(0, 1)
        ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(plots / "origin_bounds.png", dpi=180); plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 4)); ax.bar(task_summary.precision, task_summary.exact_accuracy); ax.set_ylim(0, 1); ax.set_ylabel("Exact numeric accuracy"); ax.set_title("GSM8K descriptive panel (not certified)"); fig.tight_layout(); fig.savefig(plots / "gsm8k_accuracy.png", dpi=180); plt.close(fig)

    full_summary = cmc[cmc.horizon == "FULL"][["generation_length", "severity", "mean_D", "mean_B_FS", "UCB_D", "UCB_B_FS"]]
    report_lines = [
        "# WP07D-LOCAL — SMDM Confirmatory Certificate and GSM8K Descriptive Panel", "",
        "## Scope", "", "Track A is a fixed 32-prompt second-model confirmatory result for the factorized official `origin` sampler. Track B is a separate descriptive GSM8K panel for the nonfactorized global top-k `greddy` sampler. No numerical estimand is pooled.", "",
        "## Track A", "", markdown_table(full_summary), "", f"Gate: `{track_a_gate}`. H-A1={h_a1}; H-A2={h_a2}; H-A3={h_a3}; H-A4={h_a4}.", "",
        "The Hoeffding calculation targets the fixed prompt-suite average over event-addressed coupling draws. It is not prompt-population generalization.", "",
        "## Track B", "", markdown_table(task_summary), "", f"Gate: `{track_b_gate}`. These task outputs have no CMC, B_FS, or Wasserstein certificate.", "",
        "## Overall", "", f"Gate: `{overall_gate}`.", "", "No 128-token generation and no external GPU were used.",
    ]
    (report_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    (report_dir / "QUICK_REVIEW.md").write_text(f"# Quick review\n\n- Track A: `{track_a_gate}`\n- Track B: `{track_b_gate}`\n- Overall: `{overall_gate}`\n- Pathwise violations: 0\n- Tracks pooled: no\n", encoding="utf-8")
    (report_dir / "CLAIM_SCOPE.md").write_text("# Claim scope\n\nTrack A supports only the fixed p032–p063 suite, this SMDM checkpoint, BF16 versus fake weight-only RTN, the official origin sampler, and lengths 16/64. CMC is coordinatewise maximal, not joint maximal or Wasserstein-optimal. Track B is descriptive task relevance only; it provides no transition or Wasserstein certificate.\n", encoding="utf-8")
    (report_dir / "paper_claim_recommendations.md").write_text("# Paper claim recommendations\n\nReport Track A as a fixed-suite second-model confirmation when its gate permits. Report Track B in a separate descriptive table. Do not call BF16 FP32, do not infer prompt-population generalization, and do not attach the origin-sampler certificate to the GSM8K top-k sampler.\n", encoding="utf-8")
    (report_dir / "external_gpu_implications.md").write_text("# External GPU implications\n\nNo external GPU is needed to complete the preregistered 16/64-token package. A one-shot external-GPU 128-token run remains outside WP07D and is neither started nor automatically justified by task-panel results.\n", encoding="utf-8")

    row_counts = {"origin_horizon_endpoints": len(endpoints), "origin_step_events": len(step_events), "origin_bf16_reference_rows": len(reference), "gsm8k_outputs": len(task), "gsm8k_paired_rows": len(paired_task)}
    write_json(payload / "ROW_COUNTS.json", row_counts)
    write_json(payload / "PRIMARY_KEYS.json", {"origin_horizon_endpoints": key, "gsm8k_outputs": task_key, "duplicates": 0})
    return {"track_a": track_a, "track_b": track_b, "overall": overall, "row_counts": row_counts}


def output_hashes(payload: Path) -> dict[str, str]:
    files = sorted(list((payload / "derived").glob("*.csv")) + list((payload / "derived").glob("*.json")) + list((payload / "report").glob("*.md")) + [payload / "ROW_COUNTS.json", payload / "PRIMARY_KEYS.json"])
    return {str(path.relative_to(payload)): sha256_file(path) for path in files}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--write-expected", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    payload = args.payload_dir.resolve()
    result = generate(payload)
    hashes = output_hashes(payload)
    expected_path = payload / "REPRODUCTION_EXPECTED.json"
    if args.write_expected:
        write_json(expected_path, {"hashes": hashes, "headline": result})
    if args.verify:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        mismatches = {key: {"expected": value, "observed": hashes.get(key)} for key, value in expected["hashes"].items() if hashes.get(key) != value}
        if mismatches or result != expected["headline"]:
            raise RuntimeError(f"Reproduction mismatch: {mismatches}")
    write_json(payload / "REPRODUCTION_VERIFICATION.json", {"model_execution": False, "return_code": 0, "verified": bool(args.verify), "output_hash_count": len(hashes)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
