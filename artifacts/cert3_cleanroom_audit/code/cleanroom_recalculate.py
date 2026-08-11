#!/usr/bin/env python3
"""Independent WP06-CERT-3 recalculation from frozen row-level raw artifacts.

This module intentionally does not import or inspect the authoring analysis.
It reads only provenance/config contracts and raw artifacts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml


HORIZONS = [("H4", 4), ("H8", 8), ("H12", 12), ("H16", 16),
            ("H24", 24), ("H32", 32), ("FULL", 33)]
SEVERITIES = ["W8", "W6", "W4"]
CMC_SEEDS = [260736, 260737, 260738, 260739]
CRN_SEEDS = [260736, 260737]
FP_SEEDS = [260740, 260741, 260742, 260743]
FP_PAIRS = [(260740, 260741), (260742, 260743)]
MASK_TOKEN_ID = 50257
TOL = 1e-12


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format="%.17g")


def read_shards(raw: Path, name: str, columns: list[str] | None = None) -> pd.DataFrame:
    files = sorted((raw / name).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no shards for {name}")
    return pd.concat([pd.read_parquet(f, columns=columns) for f in files],
                     ignore_index=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def tokens(value: str | list[int]) -> list[int]:
    return value if isinstance(value, list) else json.loads(value)


def hamming(a: list[int], b: list[int]) -> float:
    if len(a) != 16 or len(b) != 16:
        raise ValueError(f"expected 16 generation tokens, got {len(a)}, {len(b)}")
    return sum(x != y for x, y in zip(a, b)) / 16.0


def mismatch_type(a: list[int], b: list[int]) -> str:
    kinds: set[str] = set()
    for x, y in zip(a, b):
        if x == y:
            continue
        if x == MASK_TOKEN_ID or y == MASK_TOKEN_ID:
            kinds.add("mask-token")
        else:
            kinds.add("token-token")
    if not kinds:
        return "none"
    if len(kinds) == 2:
        return "mixed"
    return next(iter(kinds))


def load_contracts(payload: Path) -> tuple[dict, dict, dict]:
    config = yaml.safe_load((payload / "config/config.yaml").read_text())
    protocol = json.loads((payload / "config/statistical_protocol.json").read_text())
    prompt_contract = json.loads(
        (payload / "provenance/prompt_population_contract.json").read_text())
    return config, protocol, prompt_contract


def key_audit(name: str, df: pd.DataFrame, key: list[str]) -> dict[str, Any]:
    duplicate = int(df.duplicated(key, keep=False).sum())
    conflicting = 0
    if duplicate:
        nonkey = [c for c in df.columns if c not in key]
        conflicting = sum(
            1 for _, g in df[df.duplicated(key, keep=False)].groupby(key, dropna=False)
            if any(g[c].nunique(dropna=False) > 1 for c in nonkey)
        )
    return {
        "table": name,
        "primary_key": "|".join(key),
        "row_count": len(df),
        "duplicate_rows": duplicate,
        "conflicting_duplicate_groups": conflicting,
        "passed": duplicate == 0,
    }


def reconstruct_pathwise(steps: pd.DataFrame, endpoints: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    endpoint_lookup = endpoints.set_index(
        ["trajectory_id", "horizon"], drop=False).to_dict("index")
    out: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for trajectory_id, group in steps.groupby("trajectory_id", sort=True):
        g = group.sort_values("global_kernel_index")
        idxs = g.global_kernel_index.astype(int).tolist()
        if idxs != list(range(33)):
            issues.append({"type": "chain_step_mismatch", "trajectory_id": trajectory_id,
                           "detail": str(idxs)})
            continue
        family = str(g.family.iloc[0])
        prompt_id = str(g.prompt_id.iloc[0])
        seed = int(g.coupling_seed.iloc[0])
        severity = str(g.severity.iloc[0])
        rows = list(g.itertuples(index=False))
        first_split = None
        for r in rows:
            if r.fp_state_after_hash != r.q_state_after_hash:
                first_split = int(r.global_kernel_index)
                break
        for label, count in HORIZONS:
            r_end = rows[count - 1]
            fp_end = tokens(r_end.fp_generation_tokens_json)
            q_end = tokens(r_end.q_generation_tokens_json)
            d = hamming(fp_end, q_end)
            split_in_h = first_split is not None and first_split < count
            if split_in_h:
                if first_split == 0:
                    pre = [MASK_TOKEN_ID] * 16
                    pre_hash = str(rows[0].fp_state_before_hash)
                else:
                    prev = rows[first_split - 1]
                    pre = tokens(prev.fp_generation_tokens_json)
                    pre_hash = str(rows[first_split].fp_state_before_hash)
                bfs = pre.count(MASK_TOKEN_ID) / 16.0
                split_row = rows[first_split]
                fp_split = tokens(split_row.fp_generation_tokens_json)
                q_split = tokens(split_row.q_generation_tokens_json)
                split_type = mismatch_type(fp_split, q_split)
                split_count = sum(x != y for x, y in zip(fp_split, q_split))
                prefix_violation = sum(
                    1 for i, x in enumerate(pre)
                    if x != MASK_TOKEN_ID and fp_end[i] != q_end[i]
                )
            else:
                bfs = 0.0
                pre_hash = ""
                split_type = "none"
                split_count = 0
                prefix_violation = 0
            pathwise_violation = max(0.0, d - bfs)
            original = endpoint_lookup.get((trajectory_id, label))
            original_d_diff = math.nan
            original_bfs_diff = math.nan
            original_token_match = False
            if original is not None:
                original_d_diff = abs(float(original["D"]) - d)
                original_bfs_diff = abs(float(original["B_FS"]) - bfs)
                original_token_match = (
                    tokens(original["fp_generation_tokens_json"]) == fp_end and
                    tokens(original["q_generation_tokens_json"]) == q_end)
                if original_d_diff > TOL or original_bfs_diff > TOL or not original_token_match:
                    issues.append({
                        "type": "raw_endpoint_referential_mismatch",
                        "trajectory_id": trajectory_id,
                        "detail": f"{label}:D={original_d_diff},BFS={original_bfs_diff},tokens={original_token_match}",
                    })
            else:
                issues.append({"type": "missing_endpoint", "trajectory_id": trajectory_id,
                               "detail": label})
            out.append({
                "trajectory_id": trajectory_id,
                "family": family,
                "prompt_id": prompt_id,
                "coupling_seed": seed,
                "severity": severity,
                "horizon": label,
                "horizon_count": count,
                "D": d,
                "B_FS": bfs,
                "slack": bfs - d,
                "inflation": bfs / d if d > 0 else math.nan,
                "split": split_in_h,
                "no_split": not split_in_h,
                "first_split_kernel_index": first_split if split_in_h else math.nan,
                "first_split_region": (
                    "early" if split_in_h and first_split <= 10 else
                    "middle" if split_in_h and first_split <= 21 else
                    "late" if split_in_h else "none"),
                "first_split_mismatch_type": split_type,
                "first_split_coordinate_count": split_count,
                "residual_mask_count": int(round(16 * bfs)),
                "first_split_pre_state_hash": pre_hash,
                "prefix_violation_count": prefix_violation,
                "pathwise_violation": pathwise_violation,
                "fp_endpoint_tokens_json": json.dumps(fp_end, separators=(",", ":")),
                "q_endpoint_tokens_json": json.dumps(q_end, separators=(",", ":")),
                "original_D_abs_diff": original_d_diff,
                "original_B_FS_abs_diff": original_bfs_diff,
                "original_endpoint_token_match": original_token_match,
            })
    return pd.DataFrame(out), issues


def certificate_cells(pathwise: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (family, severity, horizon), g in pathwise.groupby(
            ["family", "severity", "horizon"], sort=False):
        prompt_bfs = g.groupby("prompt_id").B_FS.sum()
        total_bfs = float(prompt_bfs.sum())
        rows.append({
            "family": family,
            "severity": severity,
            "horizon": horizon,
            "horizon_count": int(g.horizon_count.iloc[0]),
            "observation_count": len(g),
            "prompt_count": g.prompt_id.nunique(),
            "seed_count": g.coupling_seed.nunique(),
            "mean_D": float(g.D.mean()),
            "mean_B_FS": float(g.B_FS.mean()),
            "split_probability": float(g.split.mean()),
            "no_split_probability": float(g.no_split.mean()),
            "nonvacuity_rate_B_FS": float((g.B_FS < 1.0).mean()),
            "median_inflation_D_positive": float(g.loc[g.D > 0, "inflation"].median())
            if (g.D > 0).any() else math.nan,
            "max_single_prompt_share_B_FS": float(prompt_bfs.max() / total_bfs)
            if total_bfs > 0 else 0.0,
        })
    result = pd.DataFrame(rows)
    result["severity"] = pd.Categorical(result.severity, SEVERITIES, ordered=True)
    result["horizon"] = pd.Categorical(
        result.horizon, [x[0] for x in HORIZONS], ordered=True)
    return result.sort_values(["family", "severity", "horizon"]).astype(
        {"severity": "string", "horizon": "string"})


def intrinsic_diversity(fp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = {(r.prompt_id, int(r.fp_seed), r.horizon):
              tokens(r.generation_tokens_json) for r in fp.itertuples(index=False)}
    obs = []
    for prompt in sorted(fp.prompt_id.unique()):
        for pair_index, (a, b) in enumerate(FP_PAIRS):
            for label, count in HORIZONS:
                x, y = lookup[(prompt, a, label)], lookup[(prompt, b, label)]
                obs.append({"prompt_id": prompt, "pair_index": pair_index,
                            "seed_a": a, "seed_b": b, "horizon": label,
                            "horizon_count": count, "Delta_ref": hamming(x, y)})
    observations = pd.DataFrame(obs)
    summary = observations.groupby(["horizon", "horizon_count"], as_index=False).agg(
        observation_count=("Delta_ref", "size"),
        prompt_count=("prompt_id", "nunique"),
        mean_Delta_ref=("Delta_ref", "mean"),
        exact_match_rate=("Delta_ref", lambda x: float((x == 0).mean())),
        median_Delta_ref=("Delta_ref", "median"),
    )
    return observations, summary


def hoeffding_tables(cells: pd.DataFrame, delta_obs: pd.DataFrame,
                     protocol: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    K = int(protocol["simultaneous_statement_count"])
    delta_family = float(protocol["family_wise_delta"])
    rows = []
    cmc = cells[cells.family == "CMC"]
    for r in cmc.itertuples(index=False):
        n = int(r.observation_count)
        radius = math.sqrt(math.log(K / delta_family) / (2 * n))
        for metric, mean in [("D_CMC", float(r.mean_D)),
                             ("B_FS_CMC", float(r.mean_B_FS))]:
            rows.append({"statement": "upper", "metric": metric,
                         "severity": str(r.severity), "horizon": str(r.horizon),
                         "n": n, "mean": mean, "radius": radius,
                         "bound": min(1.0, mean + radius)})
    for (horizon, count), g in delta_obs.groupby(["horizon", "horizon_count"]):
        n = len(g)
        mean = float(g.Delta_ref.mean())
        radius = math.sqrt(math.log(K / delta_family) / (2 * n))
        rows.append({"statement": "lower", "metric": "Delta_ref",
                     "severity": "ALL", "horizon": horizon, "n": n,
                     "mean": mean, "radius": radius,
                     "bound": max(0.0, mean - radius)})
    ucb = pd.DataFrame(rows)
    epsilons = [float(x) for x in protocol["absolute_epsilons"]]
    abs_rows = []
    ordered = [x[0] for x in HORIZONS]
    for severity in SEVERITIES:
        for metric in ["B_FS_CMC", "D_CMC"]:
            d = ucb[(ucb.severity == severity) & (ucb.metric == metric)].set_index("horizon")
            for epsilon in epsilons:
                cert = "NONE"
                empirical = "NONE"
                for h in ordered:
                    if all(float(d.loc[x, "bound"]) <= epsilon for x in ordered[:ordered.index(h)+1]):
                        cert = h
                    if all(float(d.loc[x, "mean"]) <= epsilon for x in ordered[:ordered.index(h)+1]):
                        empirical = h
                abs_rows.append({"severity": severity, "metric": metric,
                                 "epsilon": epsilon,
                                 "empirical_prefix_horizon": empirical,
                                 "certified_95_prefix_horizon": cert})
    rel_rows = []
    delta = ucb[ucb.metric == "Delta_ref"].set_index("horizon")
    for severity in SEVERITIES:
        for metric in ["B_FS_CMC", "D_CMC"]:
            d = ucb[(ucb.severity == severity) & (ucb.metric == metric)].set_index("horizon")
            for theta in [float(x) for x in protocol["relative_thetas"]]:
                cert = "NONE"
                empirical = "NONE"
                for h in ordered:
                    prefix = ordered[:ordered.index(h)+1]
                    if all(float(d.loc[x, "bound"]) <= theta * float(delta.loc[x, "bound"])
                           and float(delta.loc[x, "bound"]) > 0 for x in prefix):
                        cert = h
                    if all(float(d.loc[x, "mean"]) <= theta * float(delta.loc[x, "mean"])
                           and float(delta.loc[x, "mean"]) > 0 for x in prefix):
                        empirical = h
                rel_rows.append({"severity": severity, "metric": metric,
                                 "theta": theta,
                                 "empirical_prefix_horizon": empirical,
                                 "certified_95_prefix_horizon": cert})
    return ucb, pd.DataFrame(abs_rows), pd.DataFrame(rel_rows)


def sensitivity(pathwise: pd.DataFrame, delta_obs: pd.DataFrame, protocol: dict,
                reps: int) -> dict[str, pd.DataFrame]:
    cmc = pathwise[pathwise.family == "CMC"].copy()
    K = int(protocol["simultaneous_statement_count"])
    dfam = float(protocol["family_wise_delta"])
    radius64 = math.sqrt(math.log(K / dfam) / (2 * 64))
    prompt_rows = []
    for (severity, horizon), g in cmc.groupby(["severity", "horizon"]):
        pg = g.groupby("prompt_id")[["D", "B_FS"]].mean()
        prompt_rows.append({
            "severity": severity, "horizon": horizon, "n": 64,
            "mean_D": float(pg.D.mean()), "mean_B_FS": float(pg.B_FS.mean()),
            "radius": radius64, "UCB_D": min(1.0, float(pg.D.mean()) + radius64),
            "UCB_B_FS": min(1.0, float(pg.B_FS.mean()) + radius64),
        })
    prompt_block = pd.DataFrame(prompt_rows)

    loo_prompt = []
    for omitted in sorted(cmc.prompt_id.unique()):
        sub = cmc[cmc.prompt_id != omitted]
        for (severity, horizon), g in sub.groupby(["severity", "horizon"]):
            loo_prompt.append({"omitted_prompt": omitted, "severity": severity,
                               "horizon": horizon, "mean_D": float(g.D.mean()),
                               "mean_B_FS": float(g.B_FS.mean())})
    loo_seed = []
    for omitted in CMC_SEEDS:
        sub = cmc[cmc.coupling_seed != omitted]
        for (severity, horizon), g in sub.groupby(["severity", "horizon"]):
            loo_seed.append({"omitted_seed": omitted, "severity": severity,
                             "horizon": horizon, "mean_D": float(g.D.mean()),
                             "mean_B_FS": float(g.B_FS.mean())})

    rng = np.random.default_rng(int(protocol["bootstrap_seed"]))
    prompts = np.array(sorted(cmc.prompt_id.unique()))
    boot_rows = []
    for severity in SEVERITIES:
        for horizon, _ in HORIZONS:
            cell = cmc[(cmc.severity == severity) & (cmc.horizon == horizon)]
            arrays = {p: cell[cell.prompt_id == p][["D", "B_FS"]].to_numpy()
                      for p in prompts}
            prompt_vals = np.array([arrays[p].mean(axis=0) for p in prompts])
            boot_prompt = np.empty((reps, 2))
            boot_hier = np.empty((reps, 2))
            for b in range(reps):
                selected = rng.integers(0, len(prompts), len(prompts))
                boot_prompt[b] = prompt_vals[selected].mean(axis=0)
                vals = []
                for ix in selected:
                    a = arrays[prompts[ix]]
                    vals.append(a[rng.integers(0, len(a), len(a))].mean(axis=0))
                boot_hier[b] = np.mean(vals, axis=0)
            for kind, arr in [("prompt", boot_prompt), ("hierarchical", boot_hier)]:
                for j, metric in enumerate(["D", "B_FS"]):
                    boot_rows.append({
                        "severity": severity, "horizon": horizon,
                        "bootstrap_type": kind, "metric": metric,
                        "replicates": reps, "point_estimate": float(cell[metric].mean()),
                        "ci_low": float(np.quantile(arr[:, j], .025)),
                        "ci_high": float(np.quantile(arr[:, j], .975)),
                    })

    delta_rows = []
    for family_delta in [0.01, 0.05, 0.10]:
        for (severity, horizon), g in cmc.groupby(["severity", "horizon"]):
            radius = math.sqrt(math.log(K / family_delta) / (2 * len(g)))
            delta_rows.append({"family_delta": family_delta, "severity": severity,
                               "horizon": horizon, "n": len(g), "radius": radius,
                               "UCB_D": min(1.0, float(g.D.mean()) + radius),
                               "UCB_B_FS": min(1.0, float(g.B_FS.mean()) + radius)})

    # Secondary Maurer-Pontil-style empirical Bernstein bound with union split.
    eb_rows = []
    logterm = math.log(2 * K / dfam)
    for (severity, horizon), g in cmc.groupby(["severity", "horizon"]):
        for metric in ["D", "B_FS"]:
            x = g[metric].to_numpy(float)
            n = len(x)
            s2 = float(np.var(x, ddof=1))
            radius = math.sqrt(2 * s2 * logterm / n) + 7 * logterm / (3 * (n - 1))
            eb_rows.append({"severity": severity, "horizon": horizon,
                            "metric": metric, "n": n, "mean": float(x.mean()),
                            "sample_variance": s2, "radius": radius,
                            "UCB": min(1.0, float(x.mean()) + radius),
                            "status": "SECONDARY_NOT_PRIMARY"})
    return {
        "prompt_block_hoeffding": prompt_block,
        "leave_one_prompt_out": pd.DataFrame(loo_prompt),
        "leave_one_seed_out": pd.DataFrame(loo_seed),
        "bootstrap_sensitivity": pd.DataFrame(boot_rows),
        "delta_sensitivity": pd.DataFrame(delta_rows),
        "empirical_bernstein_secondary": pd.DataFrame(eb_rows),
    }


def audit_distributions(raw: Path, draws: int = 100_000) -> tuple[pd.DataFrame, dict]:
    rows = []
    failures = []
    for path in sorted((raw / "audit_distributions").glob("*.npz")):
        with np.load(path) as z:
            p = np.asarray(z["p"], dtype=np.float64)
            q = np.asarray(z["q"], dtype=np.float64)
        psum, qsum = float(p.sum()), float(q.sum())
        tv = 0.5 * float(np.abs(p - q).sum())
        r = np.minimum(p, q)
        alpha = float(r.sum())
        seed = int(hashlib.sha256(path.name.encode()).hexdigest()[:16], 16)
        rng = np.random.default_rng(seed)
        match_event = rng.random(draws) < alpha
        fp = np.empty(draws, dtype=np.int64)
        qq = np.empty(draws, dtype=np.int64)
        nmatch = int(match_event.sum())
        if nmatch:
            common = r / alpha
            cdf = np.cumsum(common)
            vals = np.searchsorted(cdf, rng.random(nmatch), side="right")
            fp[match_event] = vals
            qq[match_event] = vals
        nres = draws - nmatch
        if nres:
            rp = np.maximum(0.0, p - r)
            rq = np.maximum(0.0, q - r)
            rp /= rp.sum()
            rq /= rq.sum()
            fp[~match_event] = np.searchsorted(np.cumsum(rp), rng.random(nres),
                                               side="right")
            qq[~match_event] = np.searchsorted(np.cumsum(rq), rng.random(nres),
                                               side="right")
        fp_emp = np.bincount(fp, minlength=len(p)) / draws
        q_emp = np.bincount(qq, minlength=len(q)) / draws
        mismatch = float(np.mean(fp != qq))
        max_fp = float(np.max(np.abs(fp_emp - p)))
        max_q = float(np.max(np.abs(q_emp - q)))
        mismatch_tol = max(.006, 4 * math.sqrt(max(tv * (1 - tv), 0.0) / draws))
        passed = (
            np.min(p) >= -1e-12 and np.min(q) >= -1e-12 and
            abs(psum - 1) <= 1e-10 and abs(qsum - 1) <= 1e-10 and
            max_fp <= .012 and max_q <= .012 and abs(mismatch - tv) <= mismatch_tol
        )
        row = {"file": path.name, "draws": draws, "p_sum": psum, "q_sum": qsum,
               "tv": tv, "alpha": alpha, "empirical_mismatch": mismatch,
               "mismatch_abs_error": abs(mismatch - tv),
               "mismatch_tolerance": mismatch_tol,
               "fp_category_max_abs_error": max_fp,
               "q_category_max_abs_error": max_q, "passed": passed}
        rows.append(row)
        if not passed:
            failures.append(path.name)
    df = pd.DataFrame(rows)
    return df, {"pair_count": len(df), "draws_per_pair": draws,
                "failure_count": len(failures), "failures": failures,
                "status": "PASS" if not failures and len(df) >= 24 else "FAIL",
                "qualification": (
                    "Fresh clean-room Monte Carlo from archived categorical laws; "
                    "the archive does not contain the individual original audit draws.")}


def audit_rng(rnglog: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    seen: dict[str, str] = {}
    seed_owner: dict[int, str] = {}
    issues = []
    event_count = 0
    for r in rnglog.itertuples(index=False):
        try:
            events = json.loads(r.events_json)
        except Exception as exc:
            issues.append({"issue": "invalid_events_json", "trajectory_id": r.trajectory_id,
                           "detail": str(exc)})
            continue
        if isinstance(events, dict):
            # One row stores a mapping from event type to its semantic record.
            # Empty mappings are legitimate when a deterministic copy uses no draw.
            if all(isinstance(v, dict) for v in events.values()):
                events = list(events.values())
            else:
                events = [events]
        for event in events:
            event_count += 1
            key = event.get("key") or event.get("event_key")
            stable_seed = event.get("seed")
            if stable_seed is None:
                stable_seed = event.get("stable_seed")
            if key is None:
                # CRN compact records can expose the semantic fields directly.
                key = json.dumps(event, sort_keys=True, separators=(",", ":"))
            elif not isinstance(key, str):
                key = json.dumps(key, sort_keys=True, separators=(",", ":"))
            owner = f"{r.trajectory_id}:{r.global_kernel_index}:{r.generation_position}"
            if key in seen and seen[key] != owner:
                issues.append({"issue": "duplicate_event_key", "trajectory_id": r.trajectory_id,
                               "detail": key[:240]})
            else:
                seen[key] = owner
            if stable_seed is not None:
                s = int(stable_seed)
                if s in seed_owner and seed_owner[s] != key:
                    issues.append({"issue": "stable_seed_collision",
                                   "trajectory_id": r.trajectory_id,
                                   "detail": str(s)})
                else:
                    seed_owner[s] = key
    return pd.DataFrame(issues, columns=["issue", "trajectory_id", "detail"]), {
        "rng_rows": len(rnglog), "parsed_events": event_count,
        "unique_event_keys": len(seen), "unique_stable_seeds": len(seed_owner),
        "issue_count": len(issues), "status": "PASS" if not issues else "FAIL"}


def product_hazard_audit(coord: pd.DataFrame, hazard: pd.DataFrame) -> dict:
    pred = coord.groupby(["trajectory_id", "global_kernel_index"]).delta_t_i.apply(
        lambda x: 1.0 - float(np.prod(1.0 - x.to_numpy(float)))).rename("recomputed")
    h = hazard.set_index(["trajectory_id", "global_kernel_index"])
    joined = h.join(pred, how="left")
    diffs = np.abs(joined.h_CMC - joined.recomputed)
    diagonal = joined[joined.recomputed <= 1e-15]
    return {
        "common_state_steps": len(joined),
        "missing_coordinate_groups": int(joined.recomputed.isna().sum()),
        "max_formula_abs_error": float(diffs.max()),
        "formula_failure_count": int((diffs > 1e-12).sum()),
        "diagonal_step_count": len(diagonal),
        "diagonal_split_count": int(diagonal.realized_split.sum()),
        "predicted_mean_split": float(joined.recomputed.mean()),
        "empirical_mean_split": float(joined.realized_split.mean()),
        "status": "PASS" if diffs.max() <= 1e-12 and not diagonal.realized_split.any()
        else "FAIL",
    }


def first_split_survival(pathwise: pd.DataFrame) -> pd.DataFrame:
    full = pathwise[pathwise.horizon == "FULL"]
    rows = []
    for (family, severity), g in full.groupby(["family", "severity"]):
        for k in range(34):
            survived = (~g.split) | (g.first_split_kernel_index >= k)
            rows.append({"family": family, "severity": severity, "kernel_index": k,
                         "survival_probability": float(survived.mean()),
                         "trajectory_count": len(g)})
    return pd.DataFrame(rows)


def paired_cmc_crn(pathwise: pd.DataFrame) -> pd.DataFrame:
    keys = ["prompt_id", "coupling_seed", "severity", "horizon"]
    cols = keys + ["D", "B_FS", "first_split_kernel_index", "no_split"]
    cmc = pathwise[(pathwise.family == "CMC") &
                   (pathwise.coupling_seed.isin(CRN_SEEDS))][cols].copy()
    crn = pathwise[pathwise.family == "CRN"][cols].copy()
    j = cmc.merge(crn, on=keys, suffixes=("_CMC", "_CRN"), validate="one_to_one")
    j["D_CMC_minus_CRN"] = j.D_CMC - j.D_CRN
    j["B_FS_CMC_minus_CRN"] = j.B_FS_CMC - j.B_FS_CRN
    j["no_split_indicator_difference"] = j.no_split_CMC.astype(int) - j.no_split_CRN.astype(int)
    j["first_split_step_difference"] = (
        j.first_split_kernel_index_CMC.fillna(33) -
        j.first_split_kernel_index_CRN.fillna(33))
    return j


def prompt_seed_effects(pathwise: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cmc = pathwise[pathwise.family == "CMC"]
    p = cmc.groupby(["prompt_id", "severity", "horizon"], as_index=False).agg(
        seed_count=("coupling_seed", "nunique"), mean_D=("D", "mean"),
        mean_B_FS=("B_FS", "mean"), split_probability=("split", "mean"))
    s = cmc.groupby(["coupling_seed", "severity", "horizon"], as_index=False).agg(
        prompt_count=("prompt_id", "nunique"), mean_D=("D", "mean"),
        mean_B_FS=("B_FS", "mean"), split_probability=("split", "mean"))
    return p, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cert3-payload", type=Path, required=True)
    ap.add_argument("--audit-dir", type=Path, required=True)
    ap.add_argument("--bootstrap-reps", type=int, default=None)
    args = ap.parse_args()
    payload, out = args.cert3_payload.resolve(), args.audit_dir.resolve()
    raw = payload / "raw"
    out.mkdir(parents=True, exist_ok=True)
    for d in ["integrity", "recalculation", "sensitivity", "provenance"]:
        (out / d).mkdir(exist_ok=True)
    config, protocol, prompt_contract = load_contracts(payload)
    reps = args.bootstrap_reps or int(protocol["bootstrap_replicates"])
    print("Loading raw shards only", flush=True)
    trajectories = pd.concat([
        read_shards(raw, "cmc_trajectories"),
        read_shards(raw, "crn_trajectories")], ignore_index=True)
    steps = read_shards(raw, "coupled_step_events")
    endpoints = read_shards(raw, "horizon_endpoints")
    fp = read_shards(raw, "fp_reference_trajectories")
    first = read_shards(raw, "first_split_events")
    coord = read_shards(raw, "coordinate_tv_events")
    hazard = read_shards(raw, "hazard_process")
    headroom = read_shards(raw, "joint_headroom")
    rnglog = read_shards(raw, "rng_event_log")

    table_counts = {
        "cmc_trajectories": int((trajectories.family == "CMC").sum()),
        "crn_trajectories": int((trajectories.family == "CRN").sum()),
        "coupled_step_events": len(steps), "horizon_endpoints": len(endpoints),
        "fp_reference_trajectories": len(fp), "first_split_events": len(first),
        "coordinate_tv_events": len(coord), "hazard_process": len(hazard),
        "joint_headroom": len(headroom), "rng_event_log": len(rnglog)}
    expected = {"cmc_trajectories": 768, "crn_trajectories": 384,
                "coupled_step_events": 38016, "horizon_endpoints": 8064,
                "fp_reference_trajectories": 1792, "first_split_events": 1152,
                "coordinate_tv_events": 171968, "hazard_process": 10748,
                "joint_headroom": 10748, "rng_event_log": 608256}
    count_rows = [{"table": k, "expected": expected[k], "observed": v,
                   "difference": v - expected[k], "passed": v == expected[k]}
                  for k, v in table_counts.items()]
    write_csv(out / "integrity/row_count_recalculation.csv", pd.DataFrame(count_rows))

    keys = [
        key_audit("trajectories", trajectories, ["trajectory_id"]),
        key_audit("coupled_step_events", steps, ["trajectory_id", "global_kernel_index"]),
        key_audit("horizon_endpoints", endpoints,
                  ["family", "prompt_id", "coupling_seed", "severity", "horizon"]),
        key_audit("fp_reference_trajectories", fp, ["prompt_id", "fp_seed", "horizon"]),
        key_audit("first_split_events", first, ["trajectory_id"]),
        key_audit("coordinate_tv_events", coord,
                  ["trajectory_id", "global_kernel_index", "generation_position"]),
        key_audit("hazard_process", hazard, ["trajectory_id", "global_kernel_index"]),
        key_audit("joint_headroom", headroom, ["trajectory_id", "global_kernel_index"]),
        key_audit("rng_event_log", rnglog,
                  ["trajectory_id", "global_kernel_index", "generation_position"]),
    ]
    write_csv(out / "integrity/primary_key_audit.csv", pd.DataFrame(keys))

    print("Reconstructing every pathwise endpoint and first split", flush=True)
    pathwise, ref_issues = reconstruct_pathwise(steps, endpoints)
    pathwise.to_parquet(out / "recalculation/pathwise_certificate_recalculation.parquet",
                        index=False)
    violations = pathwise[(pathwise.pathwise_violation > TOL) |
                          (pathwise.prefix_violation_count > 0)].copy()
    write_csv(out / "recalculation/pathwise_violations.csv", violations)

    # Design completeness independently from manifest row counts.
    prompts = sorted(prompt_contract["prompt_ids"])
    observed_prompt_hash = trajectories[["prompt_id", "prompt_hash"]].drop_duplicates()
    hash_map = dict(zip(prompt_contract["prompt_ids"], prompt_contract["prompt_hashes"]))
    hash_fail = observed_prompt_hash[
        observed_prompt_hash.apply(lambda r: hash_map.get(r.prompt_id) != r.prompt_hash,
                                   axis=1)]
    expected_traj = {(f, p, s, q)
                     for f, seeds in [("CMC", CMC_SEEDS), ("CRN", CRN_SEEDS)]
                     for p in prompts for s in seeds for q in SEVERITIES}
    observed_traj = set(zip(trajectories.family, trajectories.prompt_id,
                            trajectories.coupling_seed.astype(int), trajectories.severity))
    expected_fp = {(p, s, h) for p in prompts for s in FP_SEEDS
                   for h, _ in HORIZONS}
    observed_fp = set(zip(fp.prompt_id, fp.fp_seed.astype(int), fp.horizon))
    valid_trajectories = set(trajectories.trajectory_id)
    ref_issues.extend(
        {"type": "orphan_step_trajectory", "trajectory_id": x, "detail": ""}
        for x in sorted(set(steps.trajectory_id) - valid_trajectories))
    ref_issues.extend(
        {"type": "orphan_endpoint_trajectory", "trajectory_id": x, "detail": ""}
        for x in sorted(set(endpoints.trajectory_id) - valid_trajectories))
    referential = pd.DataFrame(ref_issues, columns=["type", "trajectory_id", "detail"])
    write_csv(out / "integrity/referential_integrity_issues.csv", referential)

    # Numerical sanity across numeric raw columns.
    numeric_failures = []
    required_numeric = {
        "steps": (steps, ["global_kernel_index", "D_step", "fp_mask_count", "q_mask_count"]),
        "endpoints": (endpoints, ["horizon_count", "D", "B_FS", "slack"]),
        "coordinate_tv": (coord, ["global_kernel_index", "generation_position",
                                  "delta_t_i", "alpha_t_i"]),
        "hazard": (hazard, ["global_kernel_index", "max_delta", "LB_joint_TV",
                            "h_CMC", "UB_union", "R_t"]),
        "headroom": (headroom, ["global_kernel_index", "max_delta", "LB_joint_TV",
                                "h_CMC", "UB_union", "R_t"]),
    }
    for name, (df, columns) in required_numeric.items():
        # Optional first-split and inflation fields are intentionally null for
        # no-split or zero-distance rows and are not contamination.
        numeric = df[columns]
        bad = int((~np.isfinite(numeric.to_numpy(dtype=float))).sum())
        if bad:
            numeric_failures.append({"table": name, "nonfinite_values": bad})
    range_failures = int(((pathwise.D < -TOL) | (pathwise.D > 1 + TOL) |
                          (pathwise.B_FS < -TOL) | (pathwise.B_FS > 1 + TOL)).sum())
    data_integrity = {
        "prompt_count": len(prompts),
        "observed_unique_prompts": trajectories.prompt_id.nunique(),
        "prompt_hash_failures": len(hash_fail),
        "missing_trajectory_cells": len(expected_traj - observed_traj),
        "extra_trajectory_cells": len(observed_traj - expected_traj),
        "missing_fp_cells": len(expected_fp - observed_fp),
        "extra_fp_cells": len(observed_fp - expected_fp),
        "row_count_failures": sum(not x["passed"] for x in count_rows),
        "primary_key_failures": sum(not x["passed"] for x in keys),
        "referential_issue_count": len(referential),
        "numerical_nonfinite_failures": numeric_failures,
        "metric_range_failures": range_failures,
        "pathwise_reconstructed_rows": len(pathwise),
        "status": "PASS",
    }
    if any([data_integrity["observed_unique_prompts"] != 64,
            data_integrity["prompt_hash_failures"],
            data_integrity["missing_trajectory_cells"],
            data_integrity["extra_trajectory_cells"],
            data_integrity["missing_fp_cells"],
            data_integrity["extra_fp_cells"],
            data_integrity["row_count_failures"],
            data_integrity["primary_key_failures"],
            data_integrity["referential_issue_count"],
            numeric_failures, range_failures]):
        data_integrity["status"] = "FAIL"
    dump_json(out / "integrity/data_integrity_audit.json", data_integrity)

    cells = certificate_cells(pathwise)
    write_csv(out / "recalculation/independent_certificate_cell_summary.csv", cells)
    delta_obs, delta_summary = intrinsic_diversity(fp)
    write_csv(out / "recalculation/independent_intrinsic_diversity.csv", delta_summary)
    ucb, absolute, relative = hoeffding_tables(cells, delta_obs, protocol)
    write_csv(out / "recalculation/independent_certificate_ucb_summary.csv", ucb)
    write_csv(out / "recalculation/independent_certified_horizon_absolute.csv", absolute)
    write_csv(out / "recalculation/independent_certified_horizon_relative.csv", relative)
    survival = first_split_survival(pathwise)
    write_csv(out / "recalculation/independent_first_split_survival.csv", survival)
    paired = paired_cmc_crn(pathwise)
    write_csv(out / "recalculation/independent_cmc_vs_crn.csv", paired)
    prompt_effects, seed_effects = prompt_seed_effects(pathwise)
    write_csv(out / "recalculation/independent_prompt_effects.csv", prompt_effects)
    write_csv(out / "recalculation/independent_seed_effects.csv", seed_effects)
    headroom_summary = headroom.groupby(["severity"], as_index=False).agg(
        row_count=("h_CMC", "size"), mean_max_delta=("max_delta", "mean"),
        mean_h_CMC=("h_CMC", "mean"), mean_union_upper=("UB_union", "mean"),
        mean_headroom_absolute=("headroom_absolute", "mean"),
        median_headroom_ratio=("headroom_ratio", "median"))
    write_csv(out / "recalculation/independent_joint_headroom.csv", headroom_summary)
    sync = cells[cells.family.isin(["CMC", "CRN"])].merge(
        delta_summary[["horizon", "mean_Delta_ref"]], on="horizon")
    sync["synchronization_retention"] = np.where(
        sync.mean_Delta_ref > 0, 1 - sync.mean_D / sync.mean_Delta_ref, np.nan)
    write_csv(out / "recalculation/independent_synchronization_retention.csv", sync)

    print("Running independent categorical and RNG audits", flush=True)
    marginal_df, marginal_result = audit_distributions(raw)
    write_csv(out / "integrity/actual_marginal_audit.csv", marginal_df)
    rng_issues, rng_result = audit_rng(rnglog)
    write_csv(out / "integrity/rng_collision_audit.csv", rng_issues)
    product_result = product_hazard_audit(coord, hazard)
    coupling_result = {
        "categorical_marginal_audit": marginal_result,
        "product_hazard_audit": product_result,
        "rng_audit": rng_result,
        "pathwise_rows": len(pathwise),
        "pathwise_violation_count": len(violations),
        "committed_equal_prefix_violation_count":
            int((pathwise.prefix_violation_count > 0).sum()),
        "diagonal_preservation": product_result["diagonal_split_count"] == 0,
        "status": "PASS",
    }
    if (marginal_result["status"] != "PASS" or product_result["status"] != "PASS"
            or rng_result["status"] != "PASS" or len(violations)):
        coupling_result["status"] = "FAIL"
    dump_json(out / "integrity/coupling_independent_audit.json", coupling_result)

    print(f"Running {reps} prompt/hierarchical bootstrap replicates", flush=True)
    sens = sensitivity(pathwise, delta_obs, protocol, reps)
    for name, df in sens.items():
        write_csv(out / f"sensitivity/{name}.csv", df)

    radius256 = math.sqrt(math.log(49 / .05) / (2 * 256))
    radius128 = math.sqrt(math.log(49 / .05) / (2 * 128))
    theorem_note = f"""# Independent statistical theorem audit

The declared target is the equally weighted average over the fixed 64-prompt
suite of each prompt's coupling-draw expectation.  For each CMC cell there
are four bounded observations per prompt, hence

`(1/256) sum_(prompt,seed) X = (1/64) sum_prompt [(1/4) sum_seed X]`.

Hoeffding's inequality for independent, bounded, not-necessarily-identically
distributed observations therefore applies with `n=256`, provided the four
event-addressed pseudorandom streams for every prompt are treated as
independent draws.  Equal prompt replication preserves equal prompt weights.
The theorem does not confer unseen-prompt generalization.

Reuse of numeric seed identifiers across cells creates dependence between
different simultaneous statements but does not invalidate the Bonferroni
union bound: no cross-statement independence is required.  Within-cell stream
independence rests on the archived semantic event namespaces and the usual
pseudorandom-hash idealization, not on physical randomness.

The two disjoint FP seed pairs yield `n=128` bounded Delta-ref observations.
They reuse prompt identities but not trajectory seeds within a pair; the same
fixed-suite interpretation applies.

- K: 49
- family delta: 0.05
- radius n=256: {radius256:.17g}
- radius n=128: {radius128:.17g}
- primary conclusion: VALID CONDITIONAL ON ARCHIVED STREAM-INDEPENDENCE CONTRACT
"""
    (out / "recalculation/statistical_theorem_audit.md").write_text(
        theorem_note, encoding="utf-8")
    dump_json(out / "recalculation/statistical_assumption_audit.json", {
        "target": protocol["target"], "n256_valid": True,
        "reason": "equal prompt replication and within-cell independent bounded coupling draws",
        "not_unseen_prompt_generalization": True,
        "cross_cell_dependence_allowed_by_union_bound": True,
        "seed_independence_is_contractual_pseudorandom_assumption": True,
        "delta_ref_n128_valid": True,
        "radius_n256": radius256, "radius_n128": radius128,
        "status": "PASS_WITH_EXPLICIT_ASSUMPTION",
    })

    dump_json(out / "provenance/cleanroom_execution.json", {
        "source_payload": str(payload),
        "read_policy": "raw/config/provenance only; no derived/report access",
        "model_execution": False,
        "checkpoint_loaded": False,
        "bootstrap_replicates": reps,
        "python": sys.version,
        "pid": os.getpid(),
    })
    if data_integrity["status"] != "PASS" or coupling_result["status"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
