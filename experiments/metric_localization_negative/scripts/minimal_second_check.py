#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


METRICS = ("hamming", "embedding_hybrid", "tokenizer_byte_hybrid")
COLUMNS = ("D_hamming", "D_embedding_hybrid", "D_tokenizer_byte_hybrid")
MASKS = {"MDLM_GPT2": 50257, "SMDM_GSM8K": 32000}


def main(payload: Path) -> int:
    pairs = pd.read_parquet(payload / "metrics/terminal_pair_metrics.parquet")
    costs = pd.read_parquet(payload / "metrics/observed_token_cost_cache.parquet")
    lookup = {}
    for row in costs.itertuples(index=False):
        lookup[(row.model_family, int(row.token_a), int(row.token_b))] = (float(row.hamming), float(row.embedding_hybrid), float(row.tokenizer_byte_hybrid))
    maximum_pair_error = 0.0
    recomputed = []
    for row in pairs.itertuples(index=False):
        left = list(map(int, row.left_tokens))
        right = list(map(int, row.right_tokens))
        length = max(len(left), len(right))
        left += [MASKS[row.model_family]] * (length - len(left))
        right += [MASKS[row.model_family]] * (length - len(right))
        sums = np.zeros(3, dtype=float)
        for a, b in zip(left, right):
            key = (row.model_family, min(a, b), max(a, b))
            sums += np.asarray(lookup[key])
        values = sums / length if length else sums
        original = np.asarray([row.D_hamming, row.D_embedding_hybrid, row.D_tokenizer_byte_hybrid], dtype=float)
        maximum_pair_error = max(maximum_pair_error, float(np.max(np.abs(values - original))))
        recomputed.append(values)
    values = np.asarray(recomputed)
    for index, column in enumerate(COLUMNS):
        pairs[f"second_{column}"] = values[:, index]
    keys = ["panel", "pair_type", "coupling", "severity", "temperature"]
    maximum_mean_error = 0.0
    for _, group in pairs.groupby(keys, dropna=False):
        for column in COLUMNS:
            maximum_mean_error = max(maximum_mean_error, abs(float(group[column].mean()) - float(group[f"second_{column}"].mean())))

    localization = pd.read_csv(payload / "lower_bound/transport_localization_table.csv")
    witness = pd.read_parquet(payload / "lower_bound/evaluation_witness_rows.parquet")
    maximum_bound_error = 0.0
    for row in localization.itertuples(index=False):
        y = witness[(witness.severity == row.severity) & (witness.metric == row.metric)].sort_values("prompt_id").Y.to_numpy(dtype=float)
        m = len(y)
        z = (y + 1) / 2
        log_term = math.log(2 * 9 / 0.05)
        lcb_y = 2 * (float(z.mean()) - math.sqrt(2 * float(np.var(z, ddof=1)) * log_term / m) - 7 * log_term / (3 * (m - 1))) - 1
        lcb = max(0.0, lcb_y)
        cell = pairs[(pairs.panel == "WP07C") & (pairs.severity == row.severity)]
        column = COLUMNS[METRICS.index(row.metric)]
        direct = float(cell.groupby("prompt_id")[column].mean().mean())
        ucb = min(1.0, direct + math.sqrt(math.log(9 / 0.05) / (2 * m)))
        maximum_bound_error = max(maximum_bound_error, abs(lcb - row.empirical_bernstein_LCB), abs(ucb - row.direct_CMC_UCB), abs(direct - row.direct_CMC_mean))
    result = {
        "schema_version": 1,
        "implementation": "independent loop/dictionary arithmetic; does not import metric_loc_core",
        "terminal_pair_count": len(pairs),
        "maximum_pair_metric_discrepancy": maximum_pair_error,
        "maximum_group_mean_discrepancy": maximum_mean_error,
        "maximum_LCB_UCB_discrepancy": maximum_bound_error,
        "tolerance": 1e-10,
        "pass": max(maximum_pair_error, maximum_mean_error, maximum_bound_error) <= 1e-10,
    }
    path = payload / "audits/dual_implementation_check.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-dir", type=Path, required=True)
    raise SystemExit(main(parser.parse_args().payload_dir.resolve()))
