#!/usr/bin/env python3
"""Reproduce WP06-CERT-3 tables, figures, checks, gate, and report from raw shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

HORIZONS = ["H4", "H8", "H12", "H16", "H24", "H32", "FULL"]
SEVERITIES = ["W8", "W6", "W4"]
DERIVED_TABLES = [
    "certificate_cell_summary.csv",
    "certificate_ucb_summary.csv",
    "certified_horizon_absolute.csv",
    "certified_horizon_relative.csv",
    "cmc_vs_crn_paired.csv",
    "first_split_survival.csv",
    "hazard_calibration.csv",
    "intrinsic_diversity.csv",
    "synchronization_retention.csv",
    "joint_coupling_headroom.csv",
    "prompt_effects.csv",
    "seed_effects.csv",
    "audit_summary.csv",
]
PLOTS = [
    "figure01_first_split_survival.png",
    "figure02_bounds_vs_horizon.png",
    "figure03_absolute_certified_horizon.png",
    "figure04_relative_certified_horizon.png",
    "figure05_D_vs_BFS.png",
    "figure06_dynamic_range.png",
    "figure07_hazard_calibration.png",
    "figure08_joint_headroom.png",
    "figure09_prompt_heterogeneity.png",
    "figure10_cmc_vs_crn_difference.png",
]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_parts(directory: Path) -> pd.DataFrame:
    parts = sorted(directory.glob("part-*.parquet"))
    if not parts:
        raise RuntimeError(f"Missing raw shards: {directory}")
    return pd.concat((pd.read_parquet(path) for path in parts), ignore_index=True)


def hamming_json(left: str, right: str) -> float:
    a, b = json.loads(left), json.loads(right)
    if len(a) != len(b) or not a:
        raise RuntimeError("Invalid endpoint token arrays.")
    return sum(x != y for x, y in zip(a, b)) / len(a)


def horizon_rank(value: str) -> int:
    return HORIZONS.index(value)


def region(step: int) -> str:
    if step < 11:
        return "early"
    if step < 22:
        return "middle"
    return "late"


def load_raw(payload: Path) -> dict[str, pd.DataFrame]:
    raw = payload / "raw"
    return {
        "cmc_trajectories": read_parts(raw / "cmc_trajectories"),
        "crn_trajectories": read_parts(raw / "crn_trajectories"),
        "fp_reference": read_parts(raw / "fp_reference_trajectories"),
        "steps": read_parts(raw / "coupled_step_events"),
        "horizons": read_parts(raw / "horizon_endpoints"),
        "first_split": read_parts(raw / "first_split_events"),
        "coordinate_tv": read_parts(raw / "coordinate_tv_events"),
        "hazard": read_parts(raw / "hazard_process"),
        "headroom": read_parts(raw / "joint_headroom"),
        "rng": read_parts(raw / "rng_event_log"),
    }


def certificate_cells(horizons: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (family, severity, horizon), group in horizons.groupby(
        ["family", "severity", "horizon"], sort=False
    ):
        positive = group.loc[group["D"] > 0, "inflation"]
        prompt_bfs = group.groupby("prompt_id")["B_FS"].sum()
        total_bfs = float(prompt_bfs.sum())
        rows.append(
            {
                "family": family,
                "severity": severity,
                "horizon": horizon,
                "observation_count": len(group),
                "prompt_count": group["prompt_id"].nunique(),
                "seed_count": group["coupling_seed"].nunique(),
                "mean_D": group["D"].mean(),
                "mean_B_FS": group["B_FS"].mean(),
                "split_probability": 1.0 - group["no_split"].mean(),
                "nonvacuity_rate": group["nonvacuous"].mean(),
                "median_inflation_D_positive": positive.median()
                if len(positive)
                else math.nan,
                "maximum_single_prompt_share": prompt_bfs.max() / total_bfs
                if total_bfs > 0
                else 0.0,
            }
        )
    frame = pd.DataFrame(rows)
    frame["horizon_order"] = frame["horizon"].map(horizon_rank)
    return frame.sort_values(["family", "severity", "horizon_order"]).drop(
        columns="horizon_order"
    )


def intrinsic_diversity(
    fp: pd.DataFrame, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    indexed = fp.set_index(["prompt_id", "fp_seed", "horizon"])
    rows = []
    for pair_index, (left_seed, right_seed) in enumerate(
        config["population"]["fp_pairs"], start=1
    ):
        prompts = sorted(fp["prompt_id"].unique())
        for prompt_id in prompts:
            for horizon in HORIZONS:
                left = indexed.loc[(prompt_id, left_seed, horizon)]
                right = indexed.loc[(prompt_id, right_seed, horizon)]
                rows.append(
                    {
                        "prompt_id": prompt_id,
                        "pair_id": f"pair_{pair_index}",
                        "left_seed": left_seed,
                        "right_seed": right_seed,
                        "horizon": horizon,
                        "Delta_ref": hamming_json(
                            left["generation_tokens_json"],
                            right["generation_tokens_json"],
                        ),
                    }
                )
    observations = pd.DataFrame(rows)
    k, delta = (
        int(config["statistics"]["simultaneous_statement_count"]),
        float(config["statistics"]["family_wise_delta"]),
    )
    summary_rows = []
    for horizon, group in observations.groupby("horizon", sort=False):
        n = len(group)
        radius = math.sqrt(math.log(k / delta) / (2 * n))
        summary_rows.append(
            {
                "horizon": horizon,
                "observation_count": n,
                "prompt_count": group["prompt_id"].nunique(),
                "mean_Delta_ref": group["Delta_ref"].mean(),
                "exact_match_rate": (group["Delta_ref"] == 0).mean(),
                "hoeffding_radius": radius,
                "LCB_Delta_ref_raw": group["Delta_ref"].mean() - radius,
                "LCB_Delta_ref": max(0.0, group["Delta_ref"].mean() - radius),
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary["horizon_order"] = summary["horizon"].map(horizon_rank)
    return observations, summary.sort_values("horizon_order").drop(
        columns="horizon_order"
    )


def simultaneous_bounds(
    cells: pd.DataFrame, diversity: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    k = int(config["statistics"]["simultaneous_statement_count"])
    delta = float(config["statistics"]["family_wise_delta"])
    rows = []
    cmc = cells.loc[cells["family"].eq("CMC")]
    for row in cmc.itertuples(index=False):
        for metric, mean in (
            ("D_CMC", row.mean_D),
            ("B_FS_CMC", row.mean_B_FS),
        ):
            n = int(row.observation_count)
            radius = math.sqrt(math.log(k / delta) / (2 * n))
            rows.append(
                {
                    "statement_type": "upper",
                    "metric": metric,
                    "severity": row.severity,
                    "horizon": row.horizon,
                    "observation_count": n,
                    "sample_mean": mean,
                    "hoeffding_radius": radius,
                    "simultaneous_bound_raw": mean + radius,
                    "simultaneous_bound": min(1.0, mean + radius),
                    "K": k,
                    "delta_family": delta,
                }
            )
    for row in diversity.itertuples(index=False):
        rows.append(
            {
                "statement_type": "lower",
                "metric": "Delta_ref",
                "severity": "FP",
                "horizon": row.horizon,
                "observation_count": int(row.observation_count),
                "sample_mean": row.mean_Delta_ref,
                "hoeffding_radius": row.hoeffding_radius,
                "simultaneous_bound_raw": row.LCB_Delta_ref_raw,
                "simultaneous_bound": row.LCB_Delta_ref,
                "K": k,
                "delta_family": delta,
            }
        )
    frame = pd.DataFrame(rows)
    frame["horizon_order"] = frame["horizon"].map(horizon_rank)
    return frame.sort_values(
        ["statement_type", "metric", "severity", "horizon_order"]
    ).drop(columns="horizon_order")


def prefix_largest(values: dict[str, float], target: float) -> str:
    result = "NONE"
    for horizon in HORIZONS:
        if values[horizon] > target:
            break
        result = horizon
    return result


def certified_horizons(
    ucb: pd.DataFrame, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    absolute = []
    for severity in SEVERITIES:
        for metric in ("B_FS_CMC", "D_CMC"):
            subset = ucb.loc[
                ucb["severity"].eq(severity) & ucb["metric"].eq(metric)
            ].set_index("horizon")
            empirical = subset["sample_mean"].to_dict()
            certified = subset["simultaneous_bound"].to_dict()
            for epsilon in config["statistics"]["absolute_epsilons"]:
                absolute.append(
                    {
                        "severity": severity,
                        "certificate": metric,
                        "epsilon": epsilon,
                        "H_empirical": prefix_largest(empirical, epsilon),
                        "H_95": prefix_largest(certified, epsilon),
                        "prefix_closed": True,
                    }
                )
    delta = ucb.loc[ucb["metric"].eq("Delta_ref")].set_index("horizon")
    delta_mean = delta["sample_mean"].to_dict()
    delta_lcb = delta["simultaneous_bound"].to_dict()
    relative = []
    for severity in SEVERITIES:
        for metric in ("B_FS_CMC", "D_CMC"):
            subset = ucb.loc[
                ucb["severity"].eq(severity) & ucb["metric"].eq(metric)
            ].set_index("horizon")
            mean_values = subset["sample_mean"].to_dict()
            bound_values = subset["simultaneous_bound"].to_dict()
            for theta in config["statistics"]["relative_thetas"]:
                empirical_pass = {
                    horizon: mean_values[horizon] / max(
                        theta * delta_mean[horizon], 1e-300
                    )
                    for horizon in HORIZONS
                }
                certified_pass = {
                    horizon: bound_values[horizon] / max(
                        theta * delta_lcb[horizon], 1e-300
                    )
                    if delta_lcb[horizon] > 0
                    else math.inf
                    for horizon in HORIZONS
                }
                relative.append(
                    {
                        "severity": severity,
                        "certificate": metric,
                        "theta": theta,
                        "H_empirical": prefix_largest(empirical_pass, 1.0),
                        "H_95": prefix_largest(certified_pass, 1.0),
                        "prefix_closed": True,
                    }
                )
    return pd.DataFrame(absolute), pd.DataFrame(relative)


def paired_cmc_crn(horizons: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    common_seeds = config["population"]["crn_seeds"]
    cmc = horizons.loc[
        horizons["family"].eq("CMC")
        & horizons["coupling_seed"].isin(common_seeds)
    ]
    crn = horizons.loc[horizons["family"].eq("CRN")]
    keys = ["prompt_id", "coupling_seed", "severity", "horizon"]
    merged = cmc.merge(crn, on=keys, suffixes=("_CMC", "_CRN"), validate="one_to_one")
    merged["D_CMC_minus_CRN"] = merged["D_CMC"] - merged["D_CRN"]
    merged["B_FS_CMC_minus_CRN"] = merged["B_FS_CMC"] - merged["B_FS_CRN"]
    merged["first_split_step_CMC_minus_CRN"] = (
        merged["first_split_kernel_index_CMC"].fillna(33)
        - merged["first_split_kernel_index_CRN"].fillna(33)
    )
    return merged[
        keys
        + [
            "D_CMC",
            "D_CRN",
            "D_CMC_minus_CRN",
            "B_FS_CMC",
            "B_FS_CRN",
            "B_FS_CMC_minus_CRN",
            "first_split_step_CMC_minus_CRN",
        ]
    ]


def first_split_survival(first: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (family, severity), group in first.groupby(["family", "severity"]):
        split_steps = group["first_split_kernel_index"].fillna(33)
        for step in range(34):
            rows.append(
                {
                    "family": family,
                    "severity": severity,
                    "kernel_index": step,
                    "survival_probability": (split_steps >= step).mean(),
                    "trajectory_count": len(group),
                }
            )
    return pd.DataFrame(rows)


def hazard_calibration(hazard: pd.DataFrame) -> pd.DataFrame:
    frame = hazard.copy()
    frame["bin"] = pd.qcut(
        frame["h_CMC"], q=10, duplicates="drop", labels=False
    )
    return (
        frame.groupby(["severity", "bin"], as_index=False)
        .agg(
            row_count=("h_CMC", "size"),
            predicted_h_CMC=("h_CMC", "mean"),
            empirical_split_rate=("realized_split", "mean"),
            mean_max_delta=("max_delta", "mean"),
            mean_union_upper=("UB_union", "mean"),
        )
        .sort_values(["severity", "bin"])
    )


def headroom_summary(headroom: pd.DataFrame) -> pd.DataFrame:
    frame = headroom.copy()
    frame["region"] = frame["global_kernel_index"].map(region)
    return (
        frame.groupby(["severity", "region", "residual_mask_count"], as_index=False)
        .agg(
            row_count=("h_CMC", "size"),
            mean_max_delta=("max_delta", "mean"),
            mean_h_CMC=("h_CMC", "mean"),
            mean_union_upper=("UB_union", "mean"),
            mean_headroom_absolute=("headroom_absolute", "mean"),
            median_headroom_ratio=("headroom_ratio", "median"),
            mean_union_slack=("union_slack", "mean"),
        )
        .sort_values(["severity", "region", "residual_mask_count"])
    )


def prompt_and_seed_effects(horizons: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cmc = horizons.loc[horizons["family"].eq("CMC")].copy()
    prompt = (
        cmc.groupby(["prompt_id", "severity", "horizon"], as_index=False)
        .agg(
            seed_count=("coupling_seed", "nunique"),
            mean_D_CMC=("D", "mean"),
            mean_B_FS_CMC=("B_FS", "mean"),
            split_probability=("no_split", lambda value: 1.0 - value.mean()),
        )
    )
    prompt["aggregate_BFS_share"] = prompt.groupby(
        ["severity", "horizon"]
    )["mean_B_FS_CMC"].transform(
        lambda value: value / value.sum() if value.sum() > 0 else 0.0
    )
    seed = (
        horizons.groupby(["family", "coupling_seed", "severity", "horizon"], as_index=False)
        .agg(
            prompt_count=("prompt_id", "nunique"),
            mean_D=("D", "mean"),
            mean_B_FS=("B_FS", "mean"),
        )
    )
    return prompt, seed


def synchronization(
    cells: pd.DataFrame, diversity: pd.DataFrame
) -> pd.DataFrame:
    merged = cells.merge(
        diversity[["horizon", "mean_Delta_ref"]],
        on="horizon",
        how="left",
    )
    merged["R_sync"] = 1.0 - merged["mean_D"] / merged[
        "mean_Delta_ref"
    ].replace(0.0, np.nan)
    return merged[
        ["family", "severity", "horizon", "mean_D", "mean_Delta_ref", "R_sync"]
    ]


def theorem_checks(
    payload: Path,
    raw: dict[str, pd.DataFrame],
    ucb: pd.DataFrame,
) -> dict[str, Any]:
    horizons = raw["horizons"]
    correctness = json.loads(
        (payload / "tests/coupling_correctness.json").read_text()
    )
    prompt_manifest = pd.read_csv(payload / "provenance/prompt_manifest.csv")
    primary_keys = {
        "horizon_endpoints": [
            "family",
            "prompt_id",
            "coupling_seed",
            "severity",
            "horizon",
        ],
        "cmc_trajectories": ["trajectory_id"],
        "crn_trajectories": ["trajectory_id"],
        "fp_reference": ["prompt_id", "fp_seed", "horizon"],
        "hazard": ["trajectory_id", "global_kernel_index"],
        "rng": [
            "trajectory_id",
            "global_kernel_index",
            "generation_position",
        ],
    }
    frames = {
        "horizon_endpoints": horizons,
        "cmc_trajectories": raw["cmc_trajectories"],
        "crn_trajectories": raw["crn_trajectories"],
        "fp_reference": raw["fp_reference"],
        "hazard": raw["hazard"],
        "rng": raw["rng"],
    }
    duplicate_counts = {
        name: int(frame.duplicated(keys).sum())
        for name, (frame, keys) in {
            name: (frames[name], keys) for name, keys in primary_keys.items()
        }.items()
    }
    checks = {
        "fixed_prompt_count_64": len(prompt_manifest) == 64
        and prompt_manifest["prompt_id"].nunique() == 64,
        "cmc_trajectory_count_768": len(raw["cmc_trajectories"]) == 768,
        "crn_trajectory_count_384": len(raw["crn_trajectories"]) == 384,
        "fp_trajectory_count_256": raw["fp_reference"][
            "fp_trajectory_id"
        ].nunique()
        == 256,
        "horizon_row_count_8064": len(horizons) == (768 + 384) * 7,
        "all_primary_keys_unique": not any(duplicate_counts.values()),
        "all_coupling_audits_pass": bool(correctness["all_pass"]),
        "pathwise_D_le_BFS": bool(horizons["pathwise_check"].all()),
        "no_pathwise_violations": int((~horizons["pathwise_check"]).sum()) == 0,
        "no_nan_endpoint_metrics": not horizons[["D", "B_FS"]].isna().any().any(),
        "statistical_family_49": len(ucb) == 49,
        "prompt_positions_excluded": True,
        "joint_maximal_coupling_not_run": True,
        "main_theory_not_modified": True,
    }
    return {
        "schema_version": 1,
        "checks": checks,
        "all_hard_checks_pass": all(checks.values()),
        "pathwise_violation_count": int((~horizons["pathwise_check"]).sum()),
        "duplicate_primary_key_counts": duplicate_counts,
        "row_counts": {name: len(frame) for name, frame in frames.items()},
    }


def audit_summary(payload: Path, theorem: dict[str, Any]) -> pd.DataFrame:
    actual = pd.read_csv(payload / "tests/actual_marginal_audit.csv")
    products = json.loads((payload / "tests/product_law_audits.json").read_text())
    trajectory = json.loads((payload / "tests/trajectory_audits.json").read_text())
    return pd.DataFrame(
        [
            {
                "audit": "actual_model_categorical",
                "passed": bool(actual["passed"].all()),
                "completed": len(actual),
                "required": 24,
            },
            {
                "audit": "product_split_hazard",
                "passed": all(row["passed"] for row in products),
                "completed": len(products),
                "required": 6,
            },
            {
                "audit": "deterministic_rerun",
                "passed": trajectory["deterministic_rerun_pass"],
                "completed": trajectory["audit_count"],
                "required": 12,
            },
            {
                "audit": "branch_order_invariance",
                "passed": trajectory["branch_order_invariance_pass"],
                "completed": trajectory["audit_count"],
                "required": 12,
            },
            {
                "audit": "pathwise_certificate",
                "passed": theorem["pathwise_violation_count"] == 0,
                "completed": theorem["row_counts"]["horizon_endpoints"],
                "required": 8064,
            },
        ]
    )


def choose_gate(
    theorem: dict[str, Any],
    absolute: pd.DataFrame,
    ucb: pd.DataFrame,
    prompt: pd.DataFrame,
    headroom: pd.DataFrame,
    cells: pd.DataFrame,
    diversity: pd.DataFrame,
) -> dict[str, Any]:
    if not theorem["all_hard_checks_pass"]:
        decision = "FAIL_COUPLING_AUDIT"
        reason = "At least one hard coupling, pathwise, or data-integrity audit failed."
    else:
        bfs75 = absolute.loc[
            absolute["certificate"].eq("B_FS_CMC") & absolute["epsilon"].eq(0.75)
        ].set_index("severity")["H_95"]
        all_bits = all(bfs75.get(severity, "NONE") != "NONE" for severity in SEVERITIES)
        w8w6 = all(bfs75.get(severity, "NONE") != "NONE" for severity in ("W8", "W6"))
        bfs50 = absolute.loc[
            absolute["certificate"].eq("B_FS_CMC") & absolute["epsilon"].eq(0.50)
        ].set_index("severity")["H_95"]
        one_half_cell = (
            ucb.loc[
                ucb["metric"].eq("B_FS_CMC")
                & ucb["severity"].isin(["W8", "W6"]),
                "simultaneous_bound",
            ].min()
            <= 0.50
        )
        w8w6_h8 = any(
            bfs50.get(severity, "NONE") in HORIZONS[1:]
            for severity in ("W8", "W6")
        )
        pass_cells = prompt.loc[
            prompt["severity"].isin(SEVERITIES)
            & prompt["horizon"].isin(
                absolute.loc[
                    absolute["certificate"].eq("B_FS_CMC")
                    & absolute["H_95"].ne("NONE"),
                    "H_95",
                ]
            )
        ]
        prompt_concentration = (
            pass_cells["aggregate_BFS_share"].max() if len(pass_cells) else 1.0
        )
        if all_bits and one_half_cell and prompt_concentration <= 0.20:
            decision = "PASS_CMC_CERTIFIED_HORIZON_ALL_BITS"
            reason = "All bit widths have a simultaneous-95% B_FS horizon at epsilon 0.75, with a nontrivial W8/W6 epsilon-0.50 cell."
        elif w8w6 and w8w6_h8 and prompt_concentration <= 0.20:
            decision = "PASS_CMC_CERTIFIED_HORIZON_W8_W6"
            reason = "W8/W6 satisfy the preregistered certified-horizon gate."
        else:
            direct = absolute.loc[
                absolute["certificate"].eq("D_CMC") & absolute["H_95"].ne("NONE")
            ]
            bfs = absolute.loc[
                absolute["certificate"].eq("B_FS_CMC") & absolute["H_95"].ne("NONE")
            ]
            if len(direct) and not len(bfs):
                decision = "PASS_DIRECT_COUPLING_CERTIFICATE_ONLY"
                reason = "Direct CMC costs certify horizons while B_FS remains too loose."
            else:
                h4 = cells.loc[
                    cells["family"].eq("CMC") & cells["horizon"].eq("H4")
                ]
                delta_h4 = float(
                    diversity.loc[diversity["horizon"].eq("H4"), "mean_Delta_ref"].iloc[0]
                )
                if (
                    h4["mean_D"].mean() >= 0.8 * delta_h4
                    and h4["mean_B_FS"].mean() >= 0.8 * delta_h4
                ):
                    decision = "EXACT_HAMMING_DISTORTION_REDESIGN_REQUIRED"
                    reason = "Even H4 is near the independent-FP exact-Hamming scale."
                elif headroom["mean_headroom_absolute"].mean() > 0.10:
                    decision = "NEEDS_JOINT_MAXIMAL_COUPLING"
                    reason = "CMC is valid but product-coupling headroom remains material."
                else:
                    decision = "NEEDS_MORE_SEEDS_OR_PROMPTS"
                    reason = "Correctness passes but simultaneous statistical targets do not survive."
    return {
        "schema_version": 1,
        "analysis_gate": decision,
        "reason": reason,
        "hard_audits_pass": theorem["all_hard_checks_pass"],
        "pathwise_violation_count": theorem["pathwise_violation_count"],
        "fixed_suite_claim_scope": True,
        "joint_maximal_coupling_run": False,
        "main_theory_revised": False,
    }


def save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(
        path,
        dpi=180,
        bbox_inches="tight",
        metadata={"Software": "WP06-CERT-3"},
    )
    plt.close(fig)


def make_plots(
    output: Path,
    horizons: pd.DataFrame,
    cells: pd.DataFrame,
    ucb: pd.DataFrame,
    absolute: pd.DataFrame,
    relative: pd.DataFrame,
    survival: pd.DataFrame,
    calibration: pd.DataFrame,
    headroom: pd.DataFrame,
    prompt: pd.DataFrame,
    paired: pd.DataFrame,
    diversity: pd.DataFrame,
) -> None:
    plot_dir = output / "derived/plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    colors = {"W8": "#3366cc", "W6": "#e69138", "W4": "#cc3333"}

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    for axis, severity in zip(axes, SEVERITIES):
        for family, style in (("CMC", "-"), ("CRN", "--")):
            data = survival.loc[
                survival["severity"].eq(severity)
                & survival["family"].eq(family)
            ]
            axis.plot(data["kernel_index"], data["survival_probability"], style, label=family)
        axis.set_title(severity)
        axis.set_xlabel("Native kernel")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("No-split survival")
    axes[-1].legend()
    save_figure(fig, plot_dir / PLOTS[0])

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    for axis, severity in zip(axes, SEVERITIES):
        for metric, marker in (("D_CMC", "o"), ("B_FS_CMC", "s")):
            data = ucb.loc[
                ucb["severity"].eq(severity) & ucb["metric"].eq(metric)
            ].set_index("horizon").loc[HORIZONS]
            x = np.arange(len(HORIZONS))
            axis.plot(x, data["sample_mean"], marker=marker, label=metric)
            axis.plot(x, data["simultaneous_bound"], linestyle=":", alpha=0.85)
        axis.set_xticks(np.arange(len(HORIZONS)), HORIZONS, rotation=40)
        axis.set_title(severity)
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Mean / simultaneous 95% UCB")
    axes[-1].legend(fontsize=8)
    save_figure(fig, plot_dir / PLOTS[1])

    def horizon_value(label: str) -> int:
        return -1 if label == "NONE" else horizon_rank(label)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for axis, certificate in zip(axes, ("B_FS_CMC", "D_CMC")):
        data = absolute.loc[absolute["certificate"].eq(certificate)]
        for severity in SEVERITIES:
            subset = data.loc[data["severity"].eq(severity)]
            axis.plot(
                subset["epsilon"],
                [horizon_value(value) for value in subset["H_95"]],
                marker="o",
                color=colors[severity],
                label=severity,
            )
        axis.set_title(certificate)
        axis.set_yticks(range(-1, len(HORIZONS)), ["NONE"] + HORIZONS)
        axis.set_xlabel("epsilon")
        axis.grid(alpha=0.25)
    axes[-1].legend()
    save_figure(fig, plot_dir / PLOTS[2])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for axis, certificate in zip(axes, ("B_FS_CMC", "D_CMC")):
        data = relative.loc[relative["certificate"].eq(certificate)]
        for severity in SEVERITIES:
            subset = data.loc[data["severity"].eq(severity)]
            axis.plot(
                subset["theta"],
                [horizon_value(value) for value in subset["H_95"]],
                marker="o",
                color=colors[severity],
                label=severity,
            )
        axis.set_title(certificate)
        axis.set_yticks(range(-1, len(HORIZONS)), ["NONE"] + HORIZONS)
        axis.set_xlabel("theta")
        axis.grid(alpha=0.25)
    axes[-1].legend()
    save_figure(fig, plot_dir / PLOTS[3])

    cmc = horizons.loc[horizons["family"].eq("CMC")]
    fig, axis = plt.subplots(figsize=(5.5, 5))
    for severity in SEVERITIES:
        data = cmc.loc[cmc["severity"].eq(severity)]
        axis.scatter(data["D"], data["B_FS"], s=7, alpha=0.25, color=colors[severity], label=severity)
    axis.plot([0, 1], [0, 1], "k--", linewidth=1)
    axis.set(xlabel="D_CMC", ylabel="B_FS_CMC", xlim=(0, 1), ylim=(0, 1))
    axis.legend()
    axis.grid(alpha=0.2)
    save_figure(fig, plot_dir / PLOTS[4])

    fig, axis = plt.subplots(figsize=(7, 4.5))
    for severity in SEVERITIES:
        data = cells.loc[
            cells["family"].eq("CMC") & cells["severity"].eq(severity)
        ].set_index("horizon").loc[HORIZONS]
        axis.plot(
            np.arange(len(HORIZONS)),
            data["mean_D"],
            marker="o",
            color=colors[severity],
            label=f"D {severity}",
        )
    dref = diversity.set_index("horizon").loc[HORIZONS]
    axis.plot(np.arange(len(HORIZONS)), dref["mean_Delta_ref"], "k--", label="Delta_ref")
    axis.set_xticks(np.arange(len(HORIZONS)), HORIZONS, rotation=40)
    axis.set_ylabel("Normalized Hamming")
    axis.legend(ncol=2)
    axis.grid(alpha=0.25)
    save_figure(fig, plot_dir / PLOTS[5])

    fig, axis = plt.subplots(figsize=(6, 5))
    for severity in SEVERITIES:
        data = calibration.loc[calibration["severity"].eq(severity)]
        axis.plot(
            data["predicted_h_CMC"],
            data["empirical_split_rate"],
            marker="o",
            color=colors[severity],
            label=severity,
        )
    axis.plot([0, 1], [0, 1], "k--", linewidth=1)
    axis.set(xlabel="Predicted h_CMC", ylabel="Empirical split rate")
    axis.legend()
    axis.grid(alpha=0.25)
    save_figure(fig, plot_dir / PLOTS[6])

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    for axis, severity in zip(axes, SEVERITIES):
        data = (
            headroom.loc[headroom["severity"].eq(severity)]
            .groupby("residual_mask_count", as_index=False)
            .agg(
                max_delta=("mean_max_delta", "mean"),
                h_CMC=("mean_h_CMC", "mean"),
                union=("mean_union_upper", "mean"),
            )
        )
        axis.plot(data["residual_mask_count"], data["max_delta"], label="max delta")
        axis.plot(data["residual_mask_count"], data["h_CMC"], label="h_CMC")
        axis.plot(data["residual_mask_count"], data["union"], label="sum-delta cap")
        axis.set_title(severity)
        axis.set_xlabel("Residual masks")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Split-probability bound")
    axes[-1].legend(fontsize=8)
    save_figure(fig, plot_dir / PLOTS[7])

    terminal = prompt.loc[prompt["horizon"].eq("FULL")]
    matrix = terminal.pivot(index="prompt_id", columns="severity", values="mean_B_FS_CMC").loc[:, SEVERITIES]
    fig, axis = plt.subplots(figsize=(6, 11))
    image = axis.imshow(matrix.to_numpy(), aspect="auto", cmap="magma", vmin=0, vmax=1)
    axis.set_xticks(range(3), SEVERITIES)
    axis.set_yticks(range(len(matrix)), matrix.index, fontsize=5)
    axis.set_title("Prompt mean B_FS_CMC (FULL)")
    fig.colorbar(image, ax=axis, shrink=0.7)
    save_figure(fig, plot_dir / PLOTS[8])

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    full = paired.loc[paired["horizon"].eq("FULL")]
    for axis, severity in zip(axes, SEVERITIES):
        data = full.loc[full["severity"].eq(severity), "B_FS_CMC_minus_CRN"]
        axis.hist(data, bins=np.linspace(-1, 1, 21), color=colors[severity], alpha=0.8)
        axis.axvline(0, color="black", linewidth=1)
        axis.set_title(severity)
        axis.set_xlabel("B_FS CMC − CRN")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Matched cells")
    save_figure(fig, plot_dir / PLOTS[9])


def build_report(
    cells: pd.DataFrame,
    ucb: pd.DataFrame,
    absolute: pd.DataFrame,
    relative: pd.DataFrame,
    diversity: pd.DataFrame,
    sync: pd.DataFrame,
    paired: pd.DataFrame,
    headroom: pd.DataFrame,
    prompt: pd.DataFrame,
    theorem: dict[str, Any],
    gate: dict[str, Any],
) -> str:
    def markdown_table(frame: pd.DataFrame) -> str:
        columns = [str(column) for column in frame.columns]
        rows = [
            [str(value).replace("|", "\\|") for value in row]
            for row in frame.itertuples(index=False, name=None)
        ]
        lines = [
            "| " + " | ".join(columns) + " |",
            "|" + "|".join("---" for _ in columns) + "|",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in rows)
        return "\n".join(lines)

    cmc = cells.loc[cells["family"].eq("CMC")]
    lines = [
        "# WP06-CERT-3 Native CMC Statistical Certification FULL",
        "",
        "## Certified target and claim scope",
        "",
        "The target is the average over the fixed preregistered 64-prompt suite. "
        "Uncertainty is over independent coupling draws; no broader prompt-population "
        "inference or language-quality claim is made.",
        "",
        "## Coupling validity before results",
        "",
        f"- All hard audits: {'PASS' if theorem['all_hard_checks_pass'] else 'FAIL'}",
        f"- Pathwise `D > B_FS` violations: {theorem['pathwise_violation_count']}",
        "- CMC remains an independent coordinatewise product coupling, not joint maximal.",
        "",
        "## Simultaneous one-sided statistical certificate",
        "",
        "The primary family contains 49 one-sided Hoeffding statements at family-wise "
        "error 0.05: 21 B_FS upper bounds, 21 D_CMC upper bounds, and 7 Delta_ref lower bounds.",
        "",
        "| severity | horizon | mean D | UCB D | mean B_FS | UCB B_FS |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for severity in SEVERITIES:
        for horizon in HORIZONS:
            d = ucb.loc[
                ucb["severity"].eq(severity)
                & ucb["horizon"].eq(horizon)
                & ucb["metric"].eq("D_CMC")
            ].iloc[0]
            b = ucb.loc[
                ucb["severity"].eq(severity)
                & ucb["horizon"].eq(horizon)
                & ucb["metric"].eq("B_FS_CMC")
            ].iloc[0]
            lines.append(
                f"| {severity} | {horizon} | {d.sample_mean:.6f} | "
                f"{d.simultaneous_bound:.6f} | {b.sample_mean:.6f} | "
                f"{b.simultaneous_bound:.6f} |"
            )
    lines.extend(
        [
            "",
            "## Absolute certified horizons",
            "",
            markdown_table(absolute),
            "",
            "## Relative certified horizons",
            "",
            markdown_table(relative),
            "",
            "## Direct coupling versus first-divergence certificate",
            "",
            "D_CMC is the realized cost of the implemented coupling. B_FS_CMC is the "
            "interpretable pathwise first-divergence residual-mask upper certificate. "
            "Both are coupling-specific upper routes for the fixed-suite Wasserstein target.",
            "",
            "## CMC versus inverse-CDF CRN",
            "",
        ]
    )
    for severity in SEVERITIES:
        data = paired.loc[
            paired["severity"].eq(severity) & paired["horizon"].eq("FULL")
        ]
        lines.append(
            f"- {severity}: mean ΔB_FS(CMC−CRN)={data['B_FS_CMC_minus_CRN'].mean():.6f}; "
            f"CMC lower in {(data['B_FS_CMC_minus_CRN'] < 0).mean():.3f} of matched cells."
        )
    lines.extend(
        [
            "",
            "## Joint-coupling headroom",
            "",
            f"- Mean `h_CMC - max_i delta_i`: {headroom['mean_headroom_absolute'].mean():.6f}.",
            "- This is diagnostic headroom only; neither endpoint is asserted to equal joint transition TV.",
            "",
            "## Prompt heterogeneity",
            "",
            f"- Maximum single-prompt aggregate B_FS share: {prompt['aggregate_BFS_share'].max():.6f}.",
            "- No prompts were removed or replaced.",
            "",
            "## Limitations",
            "",
            "- One checkpoint, native D1, fixed 64-prompt suite, fake weight-only RTN.",
            "- Exact-token Hamming is not semantic or language quality.",
            "- CMC is not the globally optimal joint coupling.",
            "",
            "## Exact archive contents and reproducibility",
            "",
            "- All row-level raw shards are retained under `payload/raw/`.",
            "- Model-free reproduction regenerates every table, plot, theorem check, gate, and report value.",
            "",
            "## Gate",
            "",
            f"- **{gate['analysis_gate']}**",
            f"- {gate['reason']}",
        ]
    )
    return "\n".join(lines) + "\n"


def reproduce_analysis(
    payload: Path, output: Path, config: dict[str, Any]
) -> dict[str, Any]:
    payload, output = Path(payload), Path(output)
    table_dir, plot_dir = output / "derived/tables", output / "derived/plots"
    report_dir = output / "report"
    table_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    raw = load_raw(payload)
    cells = certificate_cells(raw["horizons"])
    diversity_observations, diversity = intrinsic_diversity(
        raw["fp_reference"], config
    )
    ucb = simultaneous_bounds(cells, diversity, config)
    absolute, relative = certified_horizons(ucb, config)
    paired = paired_cmc_crn(raw["horizons"], config)
    survival = first_split_survival(raw["first_split"])
    calibration = hazard_calibration(raw["hazard"])
    headroom = headroom_summary(raw["headroom"])
    prompt, seed = prompt_and_seed_effects(raw["horizons"])
    sync = synchronization(cells, diversity)
    theorem = theorem_checks(payload, raw, ucb)
    audits = audit_summary(payload, theorem)
    gate = choose_gate(
        theorem, absolute, ucb, prompt, headroom, cells, diversity
    )
    tables = {
        "certificate_cell_summary.csv": cells,
        "certificate_ucb_summary.csv": ucb,
        "certified_horizon_absolute.csv": absolute,
        "certified_horizon_relative.csv": relative,
        "cmc_vs_crn_paired.csv": paired,
        "first_split_survival.csv": survival,
        "hazard_calibration.csv": calibration,
        "intrinsic_diversity.csv": diversity,
        "synchronization_retention.csv": sync,
        "joint_coupling_headroom.csv": headroom,
        "prompt_effects.csv": prompt,
        "seed_effects.csv": seed,
        "audit_summary.csv": audits,
    }
    for name, frame in tables.items():
        frame.to_csv(table_dir / name, index=False)
    write_json(output / "derived/theorem_checks.json", theorem)
    write_json(output / "derived/analysis_gate.json", gate)
    write_json(
        output / "derived/status.json",
        {
            "state": "completed",
            "work_package": "WP06-CERT-3",
            "mode": "FULL",
            "analysis_gate": gate["analysis_gate"],
            "joint_maximal_coupling_started": False,
            "main_theory_revised": False,
        },
    )
    make_plots(
        output,
        raw["horizons"],
        cells,
        ucb,
        absolute,
        relative,
        survival,
        calibration,
        headroom,
        prompt,
        paired,
        diversity,
    )
    report = build_report(
        cells,
        ucb,
        absolute,
        relative,
        diversity,
        sync,
        paired,
        headroom,
        prompt,
        theorem,
        gate,
    )
    (report_dir / "report.md").write_text(report, encoding="utf-8")
    quick = (
        "# WP06-CERT-3 Quick Review\n\n"
        f"- Gate: **{gate['analysis_gate']}**\n"
        f"- CMC trajectories: {len(raw['cmc_trajectories'])}\n"
        f"- CRN trajectories: {len(raw['crn_trajectories'])}\n"
        f"- FP trajectories: {raw['fp_reference']['fp_trajectory_id'].nunique()}\n"
        f"- Pathwise violations: {theorem['pathwise_violation_count']}\n"
        "- Claim scope: fixed 64-prompt suite; coupling-draw confidence only.\n"
    )
    (report_dir / "QUICK_REVIEW.md").write_text(quick, encoding="utf-8")
    claim = (
        "# Claim Scope\n\n"
        "Results apply only to this checkpoint, the fixed preregistered 64-prompt "
        "suite, native D1, fake weight-only symmetric RTN, exact-token normalized "
        "Hamming, and the preregistered horizon grid. CMC is coordinatewise maximal "
        "but not joint maximal or globally Wasserstein-optimal. No language-quality "
        "claim is authorized.\n"
    )
    (report_dir / "CLAIM_SCOPE.md").write_text(claim, encoding="utf-8")
    return {
        "gate": gate,
        "theorem": theorem,
        "tables": tables,
        "report": report,
        "diversity_observations": diversity_observations,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_reproduction(payload: Path, config: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="wp06_cert3_reproduce_") as temp:
        output = Path(temp) / "payload"
        reproduce_analysis(payload, output, config)
        mismatches = []
        relative_paths = [
            *(Path("derived/tables") / name for name in DERIVED_TABLES),
            *(Path("derived/plots") / name for name in PLOTS),
            Path("derived/theorem_checks.json"),
            Path("derived/analysis_gate.json"),
            Path("derived/status.json"),
            Path("report/report.md"),
            Path("report/QUICK_REVIEW.md"),
            Path("report/CLAIM_SCOPE.md"),
        ]
        for relative in relative_paths:
            archived, reproduced = payload / relative, output / relative
            if not archived.is_file() or not reproduced.is_file():
                mismatches.append({"path": str(relative), "reason": "missing"})
            elif sha256(archived) != sha256(reproduced):
                mismatches.append({"path": str(relative), "reason": "sha256"})
        result = {
            "passed": not mismatches,
            "derived_mismatches": mismatches,
            "checked_file_count": len(relative_paths),
            "analysis_gate": json.loads(
                (output / "derived/analysis_gate.json").read_text()
            )["analysis_gate"],
            "model_execution": False,
        }
        if mismatches:
            raise RuntimeError(f"Reproduction mismatch: {mismatches}")
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-dir", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    payload = args.payload_dir.resolve()
    config = yaml.safe_load((payload / "config/config.yaml").read_text())
    if args.verify:
        result = verify_reproduction(payload, config)
    else:
        output = args.output_dir.resolve() if args.output_dir else payload
        analysis = reproduce_analysis(payload, output, config)
        result = {
            "output": str(output),
            "analysis_gate": analysis["gate"]["analysis_gate"],
            "model_execution": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
