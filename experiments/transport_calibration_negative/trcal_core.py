from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from datasets import Dataset
from scipy.stats import binomtest, spearmanr

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from smdm_wp07a import MASK_ID, load_official_smdm, matrix_weight_names, model_logits  # noqa: E402
from wp07a_second_model_audit import extract_numeric_answer, normalize_number, state_hash, tokenizer_at  # noqa: E402

SOURCE_ROOT = Path("<EXTERNAL_ASSET_ROOT>/SMDM")
CHECKPOINT = Path("<EXTERNAL_ASSET_ROOT>/checkpoints/nieshen_SMDM_bcda56b/gsm8k_safetensors/mdm-1028M-3300e18-rsl-gsm8k.safetensors")
TOKENIZER = Path("<EXTERNAL_ASSET_ROOT>/tokenizers/TinyLlama_59f6f37")
TRAIN_ARROW = Path("<CACHE_ROOT>/huggingface/datasets/openai___gsm8k/main/0.0.0/740312add88f781978c0658806c59bc2815b9866/gsm8k-train.arrow")
TEST_PARQUET = Path("<EXTERNAL_ASSET_ROOT>/data/gsm8k_740312a/main/test-00000-of-00001.parquet")
WP07D_RUN = ROOT / "runs/wp07d_smdm_local_confirmatory_20260731_193059"
WP07D_MANIFEST = WP07D_RUN / "payload/raw/gsm8k_sample_manifest.csv"

EXPECTED = {
    "checkpoint": "1e968c26419d5b041adf3b1825e6d2b10887c45cdab76e60ea2d8341df31618f",
    "tokenizer_json": "bcd04f0eadf90287bd26e1a183ac487d8a141b09b06aecb7725bbdd343640f2e",
    "tokenizer_model": "9e556afd44213b6bd1be2b850ebbbd98f5481437a8021afaf58ee7fb1818d347",
    "test_parquet": "ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59",
    "source_commit": "583aa4716d17728dbb825aec6c24a121164d616a",
}

ALPHA_GRID = np.asarray([0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00], dtype=np.float64)
SCHEMES = ("UNIFORM", "MARGIN_FRONTIER", "RESIDUAL_ONLY", "HAZARD_ONLY", "TRANSPORT_SR", "TRANSPORT_SRH")
METHODS = {
    4: ("RTN_ABSMAX", "CLIP_UNIFORM", "CLIP_MARGIN_FRONTIER", "CLIP_RESIDUAL_ONLY", "CLIP_HAZARD_ONLY", "CLIP_TRANSPORT_SR", "CLIP_TRANSPORT_SRH"),
    3: ("RTN_ABSMAX", "CLIP_UNIFORM", "CLIP_MARGIN_FRONTIER", "CLIP_TRANSPORT_SR", "CLIP_TRANSPORT_SRH"),
}
METHOD_SCHEME = {
    "CLIP_UNIFORM": "UNIFORM",
    "CLIP_MARGIN_FRONTIER": "MARGIN_FRONTIER",
    "CLIP_RESIDUAL_ONLY": "RESIDUAL_ONLY",
    "CLIP_HAZARD_ONLY": "HAZARD_ONLY",
    "CLIP_TRANSPORT_SR": "TRANSPORT_SR",
    "CLIP_TRANSPORT_SRH": "TRANSPORT_SRH",
}
GENERATION_LENGTH = 64
STEPS = 64
CFG_SCALE = 0.1
TOLERANCE = 1.0e-12


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value: Any) -> str:
    def convert(item: Any) -> Any:
        if isinstance(item, (np.integer,)):
            return int(item)
        if isinstance(item, (np.floating,)):
            return float(item)
        if isinstance(item, (np.bool_,)):
            return bool(item)
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, torch.Tensor):
            return item.detach().cpu().tolist()
        raise TypeError(type(item))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=convert)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def tensor_sha256(value: torch.Tensor) -> str:
    raw = value.detach().contiguous().view(torch.uint8).cpu()
    array = raw.numpy()
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def row_hash(question: str, answer: str) -> str:
    q = str(question).replace("\r\n", "\n").replace("\r", "\n")
    a = str(answer).replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256((q + "\n<ANSWER>\n" + a).encode()).hexdigest()


def ordered_rows(frame: pd.DataFrame, split_name: str) -> pd.DataFrame:
    out = frame.copy().reset_index(names="source_index")
    out["row_hash"] = [row_hash(q, a) for q, a in zip(out.question, out.answer)]
    out["order_hash"] = out.row_hash.map(lambda x: hashlib.sha256(f"TRCAL-1|{split_name}|{x}".encode()).hexdigest())
    return out.sort_values(["order_hash", "source_index"]).reset_index(drop=True)


def freeze_dataset_splits(payload: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    train = Dataset.from_file(str(TRAIN_ARROW)).to_pandas()
    test = pd.read_parquet(TEST_PARQUET)
    train_ordered = ordered_rows(train, "train")
    test_ordered = ordered_rows(test, "test")
    wp07d = pd.read_csv(WP07D_MANIFEST)
    excluded_indices = set(int(x) for x in wp07d.row_id)
    excluded_hashes = set(row_hash(test.iloc[i].question, test.iloc[i].answer) for i in excluded_indices)
    eligible_test = test_ordered.loc[~test_ordered.row_hash.isin(excluded_hashes)].reset_index(drop=True)
    rows = []
    for split, source in (("calibration", train_ordered.iloc[:64]), ("validation", train_ordered.iloc[64:128]), ("test", eligible_test.iloc[:512])):
        for rank, row in enumerate(source.itertuples(index=False)):
            rows.append({
                "split": split,
                "split_rank": rank,
                "source_split": "train" if split != "test" else "test",
                "source_index": int(row.source_index),
                "row_hash": row.row_hash,
                "order_hash": row.order_hash,
                "question": str(row.question),
                "answer": str(row.answer),
                "question_hash": hashlib.sha256(str(row.question).encode()).hexdigest(),
            })
    manifest = pd.DataFrame(rows)
    if manifest.duplicated("row_hash").any():
        raise RuntimeError("TRCAL-1 split overlap or duplicate row hash")
    if len(manifest[manifest.split == "calibration"]) != 64 or len(manifest[manifest.split == "validation"]) != 64 or len(manifest[manifest.split == "test"]) != 512:
        raise RuntimeError("INCOMPLETE_TRCAL_1_DATASET")
    manifest.to_csv(payload / "provenance/data_split_manifest.csv", index=False)
    identity = {
        "dataset": "openai/gsm8k",
        "configuration": "main",
        "datasets_cache_revision": "740312add88f781978c0658806c59bc2815b9866",
        "train_arrow": str(TRAIN_ARROW),
        "train_arrow_sha256": sha256_file(TRAIN_ARROW),
        "test_parquet": str(TEST_PARQUET),
        "test_parquet_sha256": sha256_file(TEST_PARQUET),
        "wp07d_excluded_count": len(excluded_hashes),
        "row_hash_contract": "SHA256(normalized_question + newline ANSWER separator + normalized_reference_answer); line endings only",
        "ordering_contract": "SHA256(TRCAL-1|split_name|row_hash)",
    }
    write_json(payload / "provenance/dataset_identity.json", identity)
    write_json(payload / "audits/data_overlap_audit.json", {
        "calibration_validation_test_overlap": 0,
        "wp07d_test_overlap": int(manifest.loc[manifest.split == "test", "row_hash"].isin(excluded_hashes).sum()),
        "unique_rows": int(manifest.row_hash.nunique()),
        "pass": True,
    })
    return manifest, identity


def verify_assets() -> dict[str, Any]:
    values = {
        "checkpoint": sha256_file(CHECKPOINT),
        "tokenizer_json": sha256_file(TOKENIZER / "tokenizer.json"),
        "tokenizer_model": sha256_file(TOKENIZER / "tokenizer.model"),
        "test_parquet": sha256_file(TEST_PARQUET),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE_ROOT, text=True).strip(),
    }
    if values != EXPECTED:
        raise RuntimeError(f"Frozen asset mismatch: {values}")
    return {**values, "checkpoint_path": str(CHECKPOINT), "tokenizer_path": str(TOKENIZER), "source_root": str(SOURCE_ROOT), "pass": True}


def schedule() -> list[tuple[float, float, int]]:
    grid = torch.linspace(1.0, 1.0e-5, STEPS + 1, dtype=torch.float64).numpy()
    rows = []
    masked = GENERATION_LENGTH
    for i in range(STEPS):
        transfer = masked if i == STEPS - 1 else int(masked * (1.0 - grid[i + 1] / grid[i]))
        rows.append((float(grid[i]), float(grid[i + 1]), int(transfer)))
        masked -= transfer
    if sum(x[2] for x in rows) != GENERATION_LENGTH or masked != 0:
        raise RuntimeError("Fixed-count schedule does not commit exactly 64 positions")
    return rows


def prepare_state(tokenizer: Any, question: str) -> tuple[torch.Tensor, int, list[int]]:
    prompt_text = "Question: " + str(question)
    prompt_ids = tokenizer(prompt_text, add_special_tokens=True, truncation=False)["input_ids"]
    state = torch.full((1, len(prompt_ids) + GENERATION_LENGTH), MASK_ID, dtype=torch.long, device="cuda")
    state[0, :len(prompt_ids)] = torch.as_tensor(prompt_ids, dtype=torch.long, device="cuda")
    return state, len(prompt_ids), [int(x) for x in prompt_ids]


@torch.inference_mode()
def fixed_count_step(model: nn.Module, parameters: dict[str, torch.Tensor] | None, state: torch.Tensor, prompt_length: int, kernel_index: int) -> tuple[torch.Tensor, dict[str, Any]]:
    mask_index = state == MASK_ID
    generation_mask = mask_index[0, prompt_length:]
    count_masked = int(generation_mask.sum())
    if count_masked == 0:
        return state.clone(), {"transfer_count": 0, "median_token_margin": math.inf, "policy_margin": math.inf, "policy_boundary_exists": False, "masked_before": 0}
    unconditional = state.clone()
    unconditional[:, :prompt_length] = MASK_ID
    combined = torch.cat((state, unconditional), dim=0)
    logits = model_logits(model, combined, parameters)
    conditional, uncond_logits = torch.chunk(logits, 2, dim=0)
    positions = torch.nonzero(mask_index[0], as_tuple=False).squeeze(-1)
    cond = conditional[0, positions]
    unc = uncond_logits[0, positions]
    guided = unc + (CFG_SCALE + 1.0) * (cond - unc)
    probs = torch.softmax(guided.float(), dim=-1)
    top2_prob, top2_ids = torch.topk(probs, 2, dim=-1)
    sampled = top2_ids[:, 0]
    confidence = top2_prob[:, 0]
    token_margins = top2_prob[:, 0] - top2_prob[:, 1]
    t_value, s_value, _ = schedule()[kernel_index - 1]
    transfer_count = count_masked if kernel_index == STEPS else int(count_masked * (1.0 - s_value / t_value))
    next_state = state.clone()
    if transfer_count:
        selected = torch.topk(confidence, transfer_count).indices
        replacement = torch.full_like(sampled, MASK_ID)
        replacement[selected] = sampled[selected]
        next_state[0, positions] = replacement
    boundary = 0 < transfer_count < count_masked
    if boundary:
        sorted_conf = torch.sort(confidence, descending=True).values
        policy_margin = float((sorted_conf[transfer_count - 1] - sorted_conf[transfer_count]).item())
    else:
        policy_margin = math.inf
    return next_state, {
        "transfer_count": transfer_count,
        "median_token_margin": float(torch.median(token_margins).item()),
        "policy_margin": policy_margin,
        "policy_boundary_exists": boundary,
        "masked_before": count_masked,
        "masked_position_count": int(len(positions)),
    }


@torch.inference_mode()
def teacher_rollout(model: nn.Module, tokenizer: Any, row: pd.Series | Any) -> dict[str, Any]:
    state, prompt_length, prompt_ids = prepare_state(tokenizer, str(row.question))
    steps = []
    for kernel in range(1, STEPS + 1):
        pre = state.clone()
        state, meta = fixed_count_step(model, None, state, prompt_length, kernel)
        pre_generation = pre[0, prompt_length:].detach().cpu().tolist()
        post_generation = state[0, prompt_length:].detach().cpu().tolist()
        steps.append({
            "kernel_index": kernel,
            "prompt_length": prompt_length,
            "prompt_token_ids": prompt_ids,
            "pre_generation": pre_generation,
            "post_generation": post_generation,
            "pre_state_hash": state_hash(pre[0].detach().cpu().tolist()),
            "post_state_hash": state_hash(state[0].detach().cpu().tolist()),
            "residual_mass": float(np.mean(np.asarray(pre_generation) == MASK_ID)),
            **meta,
        })
    return {"row_hash": row.row_hash, "source_index": int(row.source_index), "question": str(row.question), "answer": str(row.answer), "prompt_token_ids": prompt_ids, "terminal_generation": state[0, prompt_length:].detach().cpu().tolist(), "steps": steps}


def state_from_parts(prompt_ids: Sequence[int], generation: Sequence[int]) -> torch.Tensor:
    return torch.as_tensor([list(prompt_ids) + list(generation)], dtype=torch.long, device="cuda")


@torch.inference_mode()
def baseline_pair_from_teacher(model: nn.Module, q_params: dict[str, torch.Tensor], teacher: dict[str, Any], bits: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prompt_ids = teacher["prompt_token_ids"]
    prompt_length = len(prompt_ids)
    q_state = state_from_parts(prompt_ids, [MASK_ID] * GENERATION_LENGTH)
    survived = True
    first_split = None
    risk_rows = []
    for teacher_step in teacher["steps"]:
        kernel = int(teacher_step["kernel_index"])
        fp_pre_gen = teacher_step["pre_generation"]
        q_pre_gen = q_state[0, prompt_length:].detach().cpu().tolist()
        equal_pre = survived and q_pre_gen == fp_pre_gen
        if survived and not equal_pre:
            raise RuntimeError("Survival flag inconsistent with pre-state equality")
        q_state, _ = fixed_count_step(model, q_params, q_state, prompt_length, kernel)
        q_post_gen = q_state[0, prompt_length:].detach().cpu().tolist()
        split_now = bool(equal_pre and q_post_gen != teacher_step["post_generation"])
        if split_now and first_split is None:
            first_split = {"kernel_index": kernel, "residual_mass": teacher_step["residual_mass"], "mismatch_count": int(np.sum(np.asarray(q_post_gen) != np.asarray(teacher_step["post_generation"]))) }
            survived = False
        risk_rows.append({
            "row_hash": teacher["row_hash"],
            "source_index": teacher["source_index"],
            "bit": bits,
            "kernel_index": kernel,
            "G": int(equal_pre),
            "split_now": int(split_now),
            "residual_mass": teacher_step["residual_mass"],
            "median_token_margin": teacher_step["median_token_margin"],
            "policy_margin": teacher_step["policy_margin"],
            "policy_boundary_exists": teacher_step["policy_boundary_exists"],
            "prompt_token_ids": prompt_ids,
            "pre_generation": fp_pre_gen,
            "pre_state_hash": teacher_step["pre_state_hash"],
        })
    terminal_q = q_state[0, prompt_length:].detach().cpu().tolist()
    terminal_fp = teacher["terminal_generation"]
    terminal_d = float(np.mean(np.asarray(terminal_fp) != np.asarray(terminal_q)))
    bfs = 0.0 if first_split is None else float(first_split["residual_mass"])
    return {
        "row_hash": teacher["row_hash"], "source_index": teacher["source_index"], "bit": bits,
        "first_split_step": None if first_split is None else first_split["kernel_index"],
        "B_FS": bfs, "terminal_hamming": terminal_d,
        "terminal_fp": terminal_fp, "terminal_q": terminal_q,
        "pathwise_pass": terminal_d <= bfs + TOLERANCE,
    }, risk_rows


def eligible_modules(model: nn.Module) -> dict[str, nn.Linear]:
    modules = {name: module for name, module in model.named_modules() if isinstance(module, nn.Linear)}
    expected = {name.removesuffix(".weight") for name in matrix_weight_names(model)}
    if set(modules) != expected:
        raise RuntimeError("Eligible Linear module set differs from frozen RTN matrix contract")
    return dict(sorted(modules.items()))


def quantize_weight(weight: torch.Tensor, bits: int, alpha: torch.Tensor | float = 1.0) -> tuple[torch.Tensor, torch.Tensor]:
    matrix = weight.detach().view(weight.shape[0], -1)
    qmax = 2 ** (int(bits) - 1) - 1
    qmin = -qmax - 1
    row_max = matrix.abs().amax(dim=1)
    alpha_tensor = torch.as_tensor(alpha, device=matrix.device, dtype=torch.float32).flatten()
    if alpha_tensor.numel() == 1:
        alpha_tensor = alpha_tensor.expand(matrix.shape[0])
    if alpha_tensor.numel() != matrix.shape[0]:
        raise ValueError("alpha vector does not match output-row count")
    clip = row_max.float() * alpha_tensor
    zero = row_max == 0
    scale = clip / float(qmax)
    safe = torch.where(zero, torch.ones_like(scale), scale).to(matrix.dtype)
    result = torch.round(matrix / safe[:, None]).clamp(qmin, qmax) * safe[:, None]
    result = torch.where(zero[:, None], torch.zeros_like(result), result)
    return result.view_as(weight).contiguous(), torch.where(zero, torch.zeros_like(scale), scale)


def build_rtn_parameters(model: nn.Module, bits: int) -> dict[str, torch.Tensor]:
    chosen = set(matrix_weight_names(model))
    result = {}
    for name, parameter in model.named_parameters():
        if name in chosen:
            result[name] = quantize_weight(parameter, bits, 1.0)[0]
    if set(result) != chosen:
        raise RuntimeError("RTN parameter set incomplete")
    return result


def build_risk_profiles(model: nn.Module, tokenizer: Any, calibration: pd.DataFrame, payload: Path) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    teachers: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    for row in calibration.itertuples(index=False):
        teachers.append(teacher_rollout(model, tokenizer, row))
    for bits in (4, 3):
        q_params = build_rtn_parameters(model, bits)
        for teacher in teachers:
            pair, rows = baseline_pair_from_teacher(model, q_params, teacher, bits)
            pair_rows.append(pair)
            risk_rows.extend(rows)
        del q_params
        gc.collect()
        torch.cuda.empty_cache()
    risk = pd.DataFrame(risk_rows)
    pair = pd.DataFrame(pair_rows)
    hazards = []
    for (bits, kernel), cell in risk.groupby(["bit", "kernel_index"], sort=True):
        n_survive = int(cell.G.sum())
        n_split = int(cell.split_now.sum())
        hazards.append({
            "bit": int(bits), "kernel_index": int(kernel), "n_survive": n_survive,
            "n_split": n_split, "hazard_jeffreys": (n_split + 0.5) / (n_survive + 1.0),
            "survival_probability": n_survive / len(calibration),
            "mean_residual_mass": float(cell.residual_mass.mean()),
        })
    hazard = pd.DataFrame(hazards)
    risk = risk.merge(hazard[["bit", "kernel_index", "hazard_jeffreys"]], on=["bit", "kernel_index"], validate="many_to_one")
    if risk.duplicated(["row_hash", "bit", "kernel_index"]).any():
        raise RuntimeError("Duplicate calibration risk state key")
    if not pair.pathwise_pass.all():
        raise RuntimeError("Baseline first-divergence certificate violation")
    pair.to_parquet(payload / "risk/baseline_pair_trajectories.parquet", index=False)
    hazard.to_csv(payload / "risk/survival_hazard_by_step.csv", index=False)
    risk.to_parquet(payload / "risk/calibration_state_risk_rows.parquet", index=False)
    write_json(payload / "risk/risk_profile_gate.json", {
        "pass": True, "trajectory_count": len(pair), "risk_row_count": len(risk),
        "pathwise_violations": int((~pair.pathwise_pass).sum()),
        "fixed_commit_count": True, "copy_only_monotone": True,
        "duplicate_state_keys": 0,
    })
    return teachers, risk, hazard


def build_state_weights(risk: pd.DataFrame, payload: Path) -> tuple[pd.DataFrame, dict[tuple[str, int, int, str], float]]:
    finite_token = risk[np.isfinite(risk.median_token_margin)].median_token_margin.to_numpy(float)
    finite_policy = risk[np.isfinite(risk.policy_margin)].policy_margin.to_numpy(float)
    q20_token = float(np.quantile(finite_token, 0.20))
    q20_policy = float(np.quantile(finite_policy, 0.20))
    rows = []
    lookup: dict[tuple[str, int, int, str], float] = {}
    for bits in (4, 3):
        bit_frame = risk[risk.bit == bits].copy()
        for scheme in SCHEMES:
            if scheme == "UNIFORM":
                raw = np.ones(len(bit_frame))
            elif scheme == "MARGIN_FRONTIER":
                raw = 1 + 2 * (bit_frame.median_token_margin.to_numpy() <= q20_token) + 2 * (np.isfinite(bit_frame.policy_margin.to_numpy()) & (bit_frame.policy_margin.to_numpy() <= q20_policy))
            elif scheme == "RESIDUAL_ONLY":
                raw = bit_frame.residual_mass.to_numpy(float)
            elif scheme == "HAZARD_ONLY":
                raw = bit_frame.G.to_numpy(float) * bit_frame.hazard_jeffreys.to_numpy(float)
            elif scheme == "TRANSPORT_SR":
                raw = bit_frame.G.to_numpy(float) * bit_frame.residual_mass.to_numpy(float)
            elif scheme == "TRANSPORT_SRH":
                raw = bit_frame.G.to_numpy(float) * bit_frame.hazard_jeffreys.to_numpy(float) * bit_frame.residual_mass.to_numpy(float)
            else:
                raise KeyError(scheme)
            mean = float(raw.mean())
            if not mean > 0:
                raise RuntimeError(f"Zero total calibration weight for {bits}/{scheme}")
            normalized = raw / mean
            for source, raw_weight, weight in zip(bit_frame.itertuples(index=False), raw, normalized):
                item = {
                    "row_hash": source.row_hash, "source_index": int(source.source_index),
                    "kernel_index": int(source.kernel_index), "bit": bits, "scheme": scheme,
                    "raw_weight": float(raw_weight), "normalized_weight": float(weight),
                }
                rows.append(item)
                lookup[(source.row_hash, int(source.kernel_index), bits, scheme)] = float(weight)
    frame = pd.DataFrame(rows)
    frame.to_parquet(payload / "calibration/state_weights.parquet", index=False)
    summary = frame.groupby(["bit", "scheme"], as_index=False).agg(
        state_count=("normalized_weight", "size"), mean_weight=("normalized_weight", "mean"),
        zero_fraction=("normalized_weight", lambda x: float(np.mean(np.asarray(x) == 0))),
        max_weight=("normalized_weight", "max"), effective_states=("normalized_weight", lambda x: float(np.sum(x) ** 2 / np.sum(np.asarray(x) ** 2))),
    )
    summary.to_csv(payload / "calibration/weight_scheme_summary.csv", index=False)
    contract = {
        "thresholds": {"q20_token": q20_token, "q20_policy": q20_policy},
        "schemes": list(SCHEMES), "normalization": "arithmetic mean over all calibration states equals one",
        "jeffreys_hazard": "(n_split+0.5)/(n_survive+1.0)", "weight_rows_sha256": sha256_file(payload / "calibration/state_weights.parquet"),
    }
    write_json(payload / "config/calibration_weight_contract.json", contract)
    write_json(payload / "provenance/WEIGHT_FREEZE.json", {**contract, "frozen_at_utc": utc_now()})
    return frame, lookup


@torch.inference_mode()
def collect_module_moments(model: nn.Module, teachers: list[dict[str, Any]], weights: dict[tuple[str, int, int, str], float], payload: Path) -> pd.DataFrame:
    modules = eligible_modules(model)
    combos = [(bits, scheme) for bits in (4, 3) for scheme in SCHEMES]
    accum = {name: torch.zeros((len(combos), module.in_features), device="cuda", dtype=torch.float32) for name, module in modules.items()}
    denominators = torch.zeros(len(combos), device="cuda", dtype=torch.float64)
    current = torch.zeros(len(combos), device="cuda", dtype=torch.float32)
    shapes: dict[str, set[tuple[int, ...]]] = defaultdict(set)
    dtypes: dict[str, set[str]] = defaultdict(set)
    handles = []
    for name, module in modules.items():
        def hook(_module: nn.Module, args: tuple[torch.Tensor, ...], _output: torch.Tensor, module_name: str = name) -> None:
            x = args[0].detach().float()
            shapes[module_name].add(tuple(int(v) for v in x.shape))
            dtypes[module_name].add(str(args[0].dtype))
            v = x.square().reshape(-1, x.shape[-1]).mean(dim=0)
            accum[module_name].add_(current[:, None] * v[None, :])
        handles.append(module.register_forward_hook(hook))
    try:
        for teacher in teachers:
            for step in teacher["steps"]:
                kernel = int(step["kernel_index"])
                values = [weights[(teacher["row_hash"], kernel, bits, scheme)] for bits, scheme in combos]
                current.copy_(torch.as_tensor(values, device="cuda", dtype=torch.float32))
                denominators.add_(torch.as_tensor(values, device="cuda", dtype=torch.float64))
                state = state_from_parts(teacher["prompt_token_ids"], step["pre_generation"])
                unconditional = state.clone()
                unconditional[:, :len(teacher["prompt_token_ids"])] = MASK_ID
                model_logits(model, torch.cat((state, unconditional), dim=0), None)
    finally:
        for handle in handles:
            handle.remove()
    records = []
    ledger = []
    for module_name, module in modules.items():
        moment = (accum[module_name].double() / denominators[:, None]).cpu().numpy()
        if not np.isfinite(moment).all() or np.any(moment.sum(axis=1) <= 0):
            raise RuntimeError(f"Invalid activation moment for {module_name}")
        for index, (bits, scheme) in enumerate(combos):
            records.append({"module_name": module_name, "bit": bits, "scheme": scheme, "input_dim": int(module.in_features), "moment": moment[index].tolist(), "moment_sha256": hashlib.sha256(moment[index].tobytes()).hexdigest()})
        ledger.append({"module_name": module_name, "input_dim": int(module.in_features), "output_dim": int(module.out_features), "observed_shapes": canonical_json(sorted(shapes[module_name])), "observed_dtypes": canonical_json(sorted(dtypes[module_name])), "state_count": len(teachers) * STEPS})
    frame = pd.DataFrame(records)
    frame.to_parquet(payload / "calibration/module_moments.parquet", index=False)
    pd.DataFrame(ledger).to_csv(payload / "calibration/module_moment_ledger.csv", index=False)
    expected = set(matrix_weight_names(model))
    observed = {name + ".weight" for name in modules}
    write_json(payload / "audits/activation_moment_audit.json", {
        "pass": expected == observed, "eligible_module_count": len(modules), "moment_rows": len(frame),
        "module_set_exact": expected == observed, "finite": True, "positive_sum": True,
        "replay_invariance": "FP teacher state objects were immutable and every bit/scheme moment was accumulated in the same forward call",
    })
    del accum
    gc.collect()
    torch.cuda.empty_cache()
    return frame


@torch.inference_mode()
def select_alphas(model: nn.Module, moments: pd.DataFrame, payload: Path) -> pd.DataFrame:
    parameter_map = dict(model.named_parameters())
    moment_lookup = {(row.module_name, int(row.bit), row.scheme): np.asarray(row.moment, dtype=np.float64) for row in moments.itertuples(index=False)}
    rows = []
    summary_rows = []
    weight_hashes: dict[str, str] = {}
    for weight_name in matrix_weight_names(model):
        module_name = weight_name.removesuffix(".weight")
        weight = parameter_map[weight_name].detach()
        matrix = weight.view(weight.shape[0], -1).float()
        row_energy_cache: dict[tuple[int, str], torch.Tensor] = {}
        error_cache: dict[int, list[torch.Tensor]] = {}
        scale_cache: dict[int, list[torch.Tensor]] = {}
        for bits in (4, 3):
            error_cache[bits] = []
            scale_cache[bits] = []
            for alpha in ALPHA_GRID:
                quantized, scale = quantize_weight(weight, bits, float(alpha))
                error_cache[bits].append((matrix - quantized.view_as(matrix).float()).square())
                scale_cache[bits].append(scale.float())
            for method in METHODS[bits]:
                if method == "RTN_ABSMAX":
                    selected = torch.full((matrix.shape[0],), len(ALPHA_GRID) - 1, device=matrix.device, dtype=torch.long)
                    objectives = torch.zeros(matrix.shape[0], device=matrix.device)
                else:
                    scheme = METHOD_SCHEME[method]
                    moment = torch.as_tensor(moment_lookup[(module_name, bits, scheme)], device=matrix.device, dtype=torch.float32)
                    denom = (matrix.square() * moment[None, :]).sum(dim=1) + 1e-12
                    losses = torch.stack([(err * moment[None, :]).sum(dim=1) / denom for err in error_cache[bits]], dim=1)
                    minimum = losses.min(dim=1).values
                    within = losses <= minimum[:, None] + TOLERANCE
                    selected = (within * torch.arange(len(ALPHA_GRID), device=matrix.device)[None, :]).max(dim=1).values.long()
                    objectives = losses.gather(1, selected[:, None]).squeeze(1)
                alpha_vector = torch.as_tensor(ALPHA_GRID, device=matrix.device, dtype=torch.float32)[selected]
                scales = torch.stack(scale_cache[bits], dim=1).gather(1, selected[:, None]).squeeze(1)
                quantized = quantize_weight(weight, bits, alpha_vector)[0]
                key = f"W{bits}:{method}:{weight_name}"
                weight_hashes[key] = tensor_sha256(quantized)
                rows.append({
                    "module_name": module_name, "weight_name": weight_name, "bit": bits, "method": method,
                    "output_rows": int(matrix.shape[0]), "input_dim": int(matrix.shape[1]),
                    "alpha_vector": alpha_vector.cpu().numpy().tolist(), "scale_vector": scales.cpu().numpy().tolist(),
                    "objective_vector": objectives.cpu().numpy().tolist(), "quantized_weight_sha256": weight_hashes[key],
                })
                summary_rows.append({
                    "module_name": module_name, "bit": bits, "method": method, "output_rows": int(matrix.shape[0]),
                    "fraction_alpha_below_one": float((alpha_vector < 1).float().mean()),
                    "mean_alpha": float(alpha_vector.mean()), "weighted_objective": float(objectives.mean()),
                    "quantized_weight_sha256": weight_hashes[key],
                })
        del error_cache, scale_cache
    frame = pd.DataFrame(rows)
    frame.to_parquet(payload / "calibration/selected_alpha_vectors.parquet", index=False)
    summary = pd.DataFrame(summary_rows)
    uniform = frame[frame.method == "CLIP_UNIFORM"][["weight_name", "bit", "alpha_vector"]].rename(columns={"alpha_vector": "uniform_alpha"})
    compared = frame.merge(uniform, on=["weight_name", "bit"], how="left")
    compared["fraction_rows_different_from_uniform"] = compared.apply(lambda r: float(np.mean(np.asarray(r.alpha_vector) != np.asarray(r.uniform_alpha))) if isinstance(r.uniform_alpha, (list, np.ndarray)) else np.nan, axis=1)
    summary = summary.merge(compared[["weight_name", "bit", "method", "fraction_rows_different_from_uniform"]].rename(columns={"weight_name": "module_name_weight"}), left_on=["module_name", "bit", "method"], right_on=[compared.weight_name.str.removesuffix(".weight") if False else "module_name_weight", "bit", "method"], how="left") if False else summary
    # Recompute uniform differences without relying on a heterogeneous-object merge.
    uniform_map = {(r.weight_name, int(r.bit)): np.asarray(r.alpha_vector) for r in frame[frame.method == "CLIP_UNIFORM"].itertuples(index=False)}
    summary["fraction_rows_different_from_uniform"] = [float(np.mean(np.asarray(r.alpha_vector) != uniform_map[(r.weight_name, int(r.bit))])) for r in frame.itertuples(index=False)]
    summary.to_csv(payload / "calibration/method_module_summary.csv", index=False)
    write_json(payload / "calibration/method_weight_hashes.json", weight_hashes)
    grouped_hashes: dict[str, str] = {}
    for bits in (4, 3):
        for method in METHODS[bits]:
            joined = "".join(weight_hashes[f"W{bits}:{method}:{name}"] for name in matrix_weight_names(model))
            grouped_hashes[f"W{bits}:{method}"] = hashlib.sha256(joined.encode()).hexdigest()
    identical_pairs = []
    keys = sorted(grouped_hashes)
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            if grouped_hashes[left] == grouped_hashes[right]:
                identical_pairs.append([left, right])
    write_json(payload / "audits/method_differentiation_audit.json", {
        "pass": True, "method_hashes": grouped_hashes, "byte_identical_method_pairs": identical_pairs,
        "w4_all_calibrated_identical": len({grouped_hashes[f'W4:{m}'] for m in METHODS[4] if m != 'RTN_ABSMAX'}) == 1,
    })
    return frame


def parameters_for_method(model: nn.Module, alpha_frame: pd.DataFrame, bits: int, method: str) -> dict[str, torch.Tensor]:
    chosen = alpha_frame[(alpha_frame.bit == bits) & (alpha_frame.method == method)]
    alpha_map = {row.weight_name: torch.as_tensor(row.alpha_vector, device="cuda", dtype=torch.float32) for row in chosen.itertuples(index=False)}
    result = {}
    for name, parameter in model.named_parameters():
        if name in alpha_map:
            result[name] = quantize_weight(parameter, bits, alpha_map[name])[0]
    if set(result) != set(matrix_weight_names(model)):
        raise RuntimeError(f"Method parameter set incomplete for W{bits}/{method}")
    return result


def reference_parameter_hash(model: nn.Module) -> str:
    h = hashlib.sha256()
    for name, parameter in model.named_parameters():
        h.update(name.encode())
        h.update(tensor_sha256(parameter).encode())
    return h.hexdigest()


def token_edit_distance(left: Sequence[int], right: Sequence[int]) -> int:
    previous = list(range(len(right) + 1))
    for i, x in enumerate(left, 1):
        current = [i]
        for j, y in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def numeric_correct(text: str, reference: str) -> tuple[str, str, bool]:
    predicted = extract_numeric_answer(text)
    expected = extract_numeric_answer(reference)
    p, e = normalize_number(predicted), normalize_number(expected)
    correct = p is not None and e is not None and math.isclose(p, e, rel_tol=0, abs_tol=1e-9)
    return predicted, expected, bool(correct)


@torch.inference_mode()
def guided_logits(model: nn.Module, parameters: dict[str, torch.Tensor] | None, state: torch.Tensor, prompt_length: int) -> torch.Tensor:
    unconditional = state.clone()
    unconditional[:, :prompt_length] = MASK_ID
    logits = model_logits(model, torch.cat((state, unconditional), dim=0), parameters)
    conditional, uncond = torch.chunk(logits, 2, dim=0)
    return uncond + (CFG_SCALE + 1.0) * (conditional - uncond)


def quantization_objective(model: nn.Module, alpha_frame: pd.DataFrame, moments: pd.DataFrame, bits: int, method: str, validation_scheme: str = "UNIFORM") -> float:
    params = parameters_for_method(model, alpha_frame, bits, method)
    moment_map = {(r.module_name, int(r.bit), r.scheme): np.asarray(r.moment, dtype=np.float64) for r in moments.itertuples(index=False)}
    values = []
    for name, parameter in model.named_parameters():
        if name not in params:
            continue
        module = name.removesuffix(".weight")
        m = torch.as_tensor(moment_map[(module, bits, validation_scheme)], device=parameter.device, dtype=torch.float32)
        source = parameter.detach().view(parameter.shape[0], -1).float()
        quant = params[name].view_as(source).float()
        denom = (source.square() * m[None, :]).sum(dim=1) + 1e-12
        values.append(float((((source - quant).square() * m[None, :]).sum(dim=1) / denom).mean()))
    del params
    torch.cuda.empty_cache()
    return float(np.mean(values))


@torch.inference_mode()
def evaluate_quantized_against_teacher(
    model: nn.Module,
    tokenizer: Any,
    q_params: dict[str, torch.Tensor],
    teacher: dict[str, Any],
    *,
    bits: int,
    method: str,
    split: str,
    collect_bridge: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    prompt_ids = teacher["prompt_token_ids"]
    prompt_length = len(prompt_ids)
    q_state = state_from_parts(prompt_ids, [MASK_ID] * GENERATION_LENGTH)
    first_split: dict[str, Any] | None = None
    exact_after_split = False
    trace_rows = []
    bridge_rows = []
    started = time.perf_counter()
    peak_before = torch.cuda.max_memory_allocated()
    for teacher_step in teacher["steps"]:
        kernel = int(teacher_step["kernel_index"])
        fp_pre_gen = teacher_step["pre_generation"]
        fp_post_gen = teacher_step["post_generation"]
        q_pre_gen = q_state[0, prompt_length:].detach().cpu().tolist()
        equal_pre = q_pre_gen == fp_pre_gen
        logit_metrics: dict[str, float] = {}
        if collect_bridge and first_split is None and equal_pre:
            fp_logits = guided_logits(model, None, q_state, prompt_length)[0, prompt_length:]
            q_logits = guided_logits(model, q_params, q_state, prompt_length)[0, prompt_length:]
            masked = q_state[0, prompt_length:] == MASK_ID
            fp_masked = fp_logits[masked].float()
            q_masked = q_logits[masked].float()
            difference = q_masked - fp_masked
            mse = float(difference.square().mean()) if difference.numel() else 0.0
            energy = float(fp_masked.square().mean()) if fp_masked.numel() else 0.0
            max_abs = float(difference.abs().max()) if difference.numel() else 0.0
            token_margin = float(teacher_step["median_token_margin"])
            logit_metrics = {
                "normalized_logit_mse": mse / (energy + 1e-12),
                "max_abs_logit_perturbation": max_abs,
                "margin_normalized_perturbation": max_abs / (token_margin + 1e-12) if np.isfinite(token_margin) else np.nan,
            }
            del fp_logits, q_logits, fp_masked, q_masked, difference
        q_state, _ = fixed_count_step(model, q_params, q_state, prompt_length, kernel)
        q_post_gen = q_state[0, prompt_length:].detach().cpu().tolist()
        split_now = bool(first_split is None and equal_pre and q_post_gen != fp_post_gen)
        if split_now:
            fp_arr, q_arr = np.asarray(fp_post_gen), np.asarray(q_post_gen)
            first_split = {
                "kernel_index": kernel, "residual_mass": float(teacher_step["residual_mass"]),
                "mismatch_count": int(np.sum(fp_arr != q_arr)),
                "pre_state_hash": teacher_step["pre_state_hash"],
            }
        exact_now = q_post_gen == fp_post_gen
        if first_split is not None and kernel > int(first_split["kernel_index"]) and exact_now:
            exact_after_split = True
        hamming = float(np.mean(np.asarray(q_post_gen) != np.asarray(fp_post_gen)))
        trace_rows.append({
            "row_hash": teacher["row_hash"], "source_index": teacher["source_index"], "split": split,
            "bit": bits, "method": method, "kernel_index": kernel, "equal_pre": equal_pre,
            "split_now": split_now, "exact_state_equal": exact_now, "hamming": hamming,
            "residual_mass": float(teacher_step["residual_mass"]),
            "fp_state_hash": teacher_step["post_state_hash"], "q_state_hash": state_hash(q_post_gen),
            "fp_generation": fp_post_gen, "q_generation": q_post_gen,
        })
        if collect_bridge and logit_metrics:
            bridge_rows.append({
                "row_hash": teacher["row_hash"], "source_index": teacher["source_index"], "bit": bits,
                "method": method, "kernel_index": kernel, "next_transition_split": int(split_now),
                "first_divergence_residual_damage": float(teacher_step["residual_mass"]) if split_now else 0.0,
                **logit_metrics,
            })
    fp_terminal = teacher["terminal_generation"]
    q_terminal = q_state[0, prompt_length:].detach().cpu().tolist()
    terminal_hamming = float(np.mean(np.asarray(fp_terminal) != np.asarray(q_terminal)))
    bfs = 0.0 if first_split is None else float(first_split["residual_mass"])
    decoded = tokenizer.decode(q_state[0].detach().cpu().tolist(), skip_special_tokens=True)
    fp_decoded = tokenizer.decode(list(prompt_ids) + list(fp_terminal), skip_special_tokens=True)
    predicted, expected, correct = numeric_correct(decoded, teacher["answer"])
    fp_predicted, _, fp_correct = numeric_correct(fp_decoded, teacher["answer"])
    result = {
        "row_hash": teacher["row_hash"], "source_index": teacher["source_index"], "split": split,
        "bit": bits, "method": method, "terminal_generation": q_terminal,
        "terminal_state_hash": state_hash(q_terminal), "fp_terminal_state_hash": state_hash(fp_terminal),
        "decoded_text": decoded, "fp_decoded_text": fp_decoded,
        "predicted_answer": predicted, "fp_predicted_answer": fp_predicted, "expected_answer": expected,
        "exact_answer_correct": correct, "fp_exact_answer_correct": fp_correct,
        "answer_agreement_bf16": normalize_number(predicted) is not None and normalize_number(fp_predicted) is not None and math.isclose(normalize_number(predicted), normalize_number(fp_predicted), rel_tol=0, abs_tol=1e-9),
        "terminal_hamming": terminal_hamming, "token_edit_distance": token_edit_distance(fp_terminal, q_terminal),
        "split_occurred": first_split is not None, "first_split_step": None if first_split is None else int(first_split["kernel_index"]),
        "first_split_normalized_time": None if first_split is None else float(first_split["kernel_index"] / STEPS),
        "B_FS": bfs, "terminal_exact_equality": terminal_hamming == 0,
        "reagreement_ever": bool(first_split is not None and exact_after_split),
        "final_reagreement": bool(first_split is not None and terminal_hamming == 0),
        "pathwise_pass": terminal_hamming <= bfs + TOLERANCE,
        "wall_seconds": time.perf_counter() - started,
        "peak_vram_mib": float(max(torch.cuda.max_memory_allocated(), peak_before) / 1024 ** 2),
    }
    return result, trace_rows, bridge_rows


def save_checkpoint(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    temporary.replace(path)


def load_or_create_teachers(model: nn.Module, tokenizer: Any, frame: pd.DataFrame, cache_dir: Path) -> list[dict[str, Any]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    teachers = []
    for row in frame.itertuples(index=False):
        path = cache_dir / f"{row.row_hash}.json"
        if path.exists():
            teacher = json.loads(path.read_text(encoding="utf-8"))
        else:
            teacher = teacher_rollout(model, tokenizer, row)
            save_checkpoint(path, teacher)
        teachers.append(teacher)
    return teachers


def evaluate_grid(
    model: nn.Module,
    tokenizer: Any,
    alpha_frame: pd.DataFrame,
    frame: pd.DataFrame,
    payload: Path,
    *,
    split: str,
    collect_bridge: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    teacher_dir = payload / "raw/checkpoints" / f"BF16_{split}"
    teachers = load_or_create_teachers(model, tokenizer, frame, teacher_dir)
    checkpoint_root = payload / "raw/checkpoints"
    result_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    bridge_rows: list[dict[str, Any]] = []
    reference_before = reference_parameter_hash(model)
    for bits in (4, 3):
        for method in METHODS[bits]:
            q_params = parameters_for_method(model, alpha_frame, bits, method)
            constructed_hash = hashlib.sha256("".join(tensor_sha256(q_params[name]) for name in sorted(q_params)).encode()).hexdigest()
            for teacher in teachers:
                checkpoint = checkpoint_root / f"W{bits}_{method}_{split}_{teacher['row_hash']}.json"
                trace_checkpoint = checkpoint_root / f"W{bits}_{method}_{split}_{teacher['row_hash']}.trace.json"
                bridge_checkpoint = checkpoint_root / f"W{bits}_{method}_{split}_{teacher['row_hash']}.bridge.json"
                do_bridge = collect_bridge and (bits == 4 or method == "RTN_ABSMAX")
                if checkpoint.exists() and trace_checkpoint.exists() and (not do_bridge or bridge_checkpoint.exists()):
                    result = json.loads(checkpoint.read_text(encoding="utf-8"))
                    trace = json.loads(trace_checkpoint.read_text(encoding="utf-8"))
                    bridge = json.loads(bridge_checkpoint.read_text(encoding="utf-8")) if do_bridge else []
                else:
                    result, trace, bridge = evaluate_quantized_against_teacher(model, tokenizer, q_params, teacher, bits=bits, method=method, split=split, collect_bridge=do_bridge)
                    result["quantized_parameter_set_hash"] = constructed_hash
                    save_checkpoint(checkpoint, result)
                    save_checkpoint(trace_checkpoint, trace)
                    if do_bridge:
                        save_checkpoint(bridge_checkpoint, bridge)
                result_rows.append(result)
                trace_rows.extend(trace)
                bridge_rows.extend(bridge)
            del q_params
            gc.collect()
            torch.cuda.empty_cache()
    reference_after = reference_parameter_hash(model)
    write_json(payload / "audits/reference_restoration_audit.json", {"before": reference_before, "after": reference_after, "exact": reference_before == reference_after, "functional_call_only": True})
    return pd.DataFrame(result_rows), pd.DataFrame(trace_rows), pd.DataFrame(bridge_rows)


def roc_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    positive = labels == 1
    negative = ~positive
    if positive.sum() == 0 or negative.sum() == 0:
        return float("nan")
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    return float((ranks[positive].sum() - positive.sum() * (positive.sum() + 1) / 2) / (positive.sum() * negative.sum()))


def average_precision(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    if labels.sum() == 0:
        return float("nan")
    order = np.argsort(-scores, kind="stable")
    sorted_labels = labels[order]
    precision = np.cumsum(sorted_labels) / np.arange(1, len(labels) + 1)
    return float(np.sum(precision * sorted_labels) / labels.sum())


def prompt_bootstrap_metric(frame: pd.DataFrame, metric: str, *, seed: int, resamples: int = 2000) -> tuple[float, float]:
    prompts = frame.row_hash.unique()
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(resamples):
        chosen = rng.choice(prompts, len(prompts), replace=True)
        sample = pd.concat([frame[frame.row_hash == prompt] for prompt in chosen], ignore_index=True)
        if metric == "auc":
            values.append(roc_auc(sample.next_transition_split.to_numpy(), sample.normalized_logit_mse.to_numpy()))
        elif metric == "ap":
            values.append(average_precision(sample.next_transition_split.to_numpy(), sample.normalized_logit_mse.to_numpy()))
        else:
            raise KeyError(metric)
    finite = np.asarray(values)[np.isfinite(values)]
    return (float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))) if len(finite) else (float("nan"), float("nan"))


def analyze_bridge(bridge: pd.DataFrame, validation_results: pd.DataFrame, calibration_objectives: dict[tuple[int, str], float], payload: Path) -> str:
    state_summaries = []
    for bits in (4, 3):
        cell = bridge[(bridge.bit == bits) & (bridge.method == "RTN_ABSMAX")].copy()
        auc = roc_auc(cell.next_transition_split.to_numpy(), cell.normalized_logit_mse.to_numpy())
        ap = average_precision(cell.next_transition_split.to_numpy(), cell.normalized_logit_mse.to_numpy())
        lo, hi = prompt_bootstrap_metric(cell, "auc", seed=312000 + bits)
        split_rows = cell[cell.next_transition_split == 1]
        correlation = spearmanr(split_rows.normalized_logit_mse, split_rows.first_divergence_residual_damage).statistic if len(split_rows) >= 3 else np.nan
        state_summaries.append({"bit": bits, "state_count": len(cell), "split_count": int(cell.next_transition_split.sum()), "roc_auc": auc, "roc_auc_bootstrap_lo": lo, "roc_auc_bootstrap_hi": hi, "pr_auc": ap, "spearman_residual_damage": correlation})
    state_summary = pd.DataFrame(state_summaries)
    state_summary.to_csv(payload / "bridge/state_level_bridge_summary.csv", index=False)
    bridge.to_parquet(payload / "bridge/state_level_bridge_rows.parquet", index=False)
    method_rows = []
    for method in METHODS[4]:
        cell = validation_results[(validation_results.bit == 4) & (validation_results.method == method)]
        logit_cell = bridge[(bridge.bit == 4) & (bridge.method == method)]
        method_rows.append({
            "method": method, "heldout_weighted_module_reconstruction_objective": calibration_objectives[(4, method)],
            "heldout_final_logit_mse": float(logit_cell.groupby("row_hash").normalized_logit_mse.last().mean()) if len(logit_cell) else np.nan,
            "split_probability": float(cell.split_occurred.mean()), "mean_B_FS": float(cell.B_FS.mean()),
            "terminal_hamming": float(cell.terminal_hamming.mean()), "exact_answer_accuracy": float(cell.exact_answer_correct.mean()),
            "answer_agreement": float(cell.answer_agreement_bf16.mean()),
        })
    method_summary = pd.DataFrame(method_rows)
    for left, right, name in (
        ("heldout_weighted_module_reconstruction_objective", "heldout_final_logit_mse", "rho_reconstruction_final_logit"),
        ("heldout_final_logit_mse", "split_probability", "rho_final_logit_split"),
        ("heldout_final_logit_mse", "mean_B_FS", "rho_final_logit_BFS"),
        ("heldout_weighted_module_reconstruction_objective", "mean_B_FS", "rho_calibration_BFS"),
        ("heldout_weighted_module_reconstruction_objective", "terminal_hamming", "rho_calibration_hamming"),
    ):
        method_summary[name] = float(spearmanr(method_summary[left], method_summary[right]).statistic)
    method_summary.to_csv(payload / "bridge/method_level_bridge_summary.csv", index=False)
    w4 = state_summary[state_summary.bit == 4].iloc[0]
    rho = float(method_summary.rho_calibration_BFS.iloc[0])
    label = "SURROGATE_BRIDGE_PLAUSIBLE" if float(w4.roc_auc_bootstrap_lo) > 0.60 and rho >= 0.5 else "SURROGATE_BRIDGE_WEAK"
    write_json(payload / "bridge/bridge_gate.json", {"label": label, "w4_auc_lower_95": float(w4.roc_auc_bootstrap_lo), "method_rho_calibration_objective_BFS": rho, "small_method_count_descriptive_only": True})
    return label


def paired_bootstrap(values: np.ndarray, *, seed: int, resamples: int = 20_000) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    estimates = np.empty(resamples, dtype=np.float64)
    chunk = 1000
    for start in range(0, resamples, chunk):
        end = min(resamples, start + chunk)
        indices = rng.integers(0, len(values), size=(end - start, len(values)))
        estimates[start:end] = values[indices].mean(axis=1)
    return float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975)), float(np.quantile(estimates, 0.05))


def holm_adjust(pvalues: Sequence[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = np.empty(len(pvalues), dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, (len(pvalues) - rank) * float(pvalues[index]))
        running = max(running, value)
        adjusted[index] = running
    return adjusted.tolist()


def summarize_results(results: pd.DataFrame, payload: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    task_rows = []
    mechanism_rows = []
    cost_rows = []
    for (bits, method), cell in results.groupby(["bit", "method"], sort=True):
        splits = cell[cell.split_occurred]
        task_rows.append({
            "bit": bits, "method": method, "example_count": len(cell), "exact_answer_accuracy": float(cell.exact_answer_correct.mean()),
            "bf16_accuracy": float(cell.fp_exact_answer_correct.mean()), "answer_agreement_bf16": float(cell.answer_agreement_bf16.mean()),
            "mean_token_edit_distance": float(cell.token_edit_distance.mean()),
        })
        mechanism_rows.append({
            "bit": bits, "method": method, "example_count": len(cell), "split_probability": float(cell.split_occurred.mean()),
            "mean_B_FS": float(cell.B_FS.mean()), "terminal_hamming": float(cell.terminal_hamming.mean()),
            "mean_normalized_first_split_time": float(splits.first_split_normalized_time.mean()) if len(splits) else np.nan,
            "conditional_reagreement_rate": float(splits.reagreement_ever.mean()) if len(splits) else np.nan,
            "conditional_terminal_equality_rate": float(splits.final_reagreement.mean()) if len(splits) else np.nan,
            "split_count": len(splits), "reagreement_count": int(splits.reagreement_ever.sum()), "final_reagreement_count": int(splits.final_reagreement.sum()),
        })
        cost_rows.append({"bit": bits, "method": method, "mean_inference_seconds_per_prompt": float(cell.wall_seconds.mean()), "peak_vram_mib": float(cell.peak_vram_mib.max())})
    task = pd.DataFrame(task_rows)
    mechanism = pd.DataFrame(mechanism_rows)
    cost = pd.DataFrame(cost_rows)
    task.to_csv(payload / "derived/task_summary.csv", index=False)
    mechanism.to_csv(payload / "derived/mechanism_summary.csv", index=False)
    cost.to_csv(payload / "derived/calibration_cost_summary.csv", index=False)
    comparisons = []
    comparison_specs = []
    for bits in (4, 3):
        for method in METHODS[bits]:
            if method != "CLIP_TRANSPORT_SR":
                comparison_specs.append((bits, "CLIP_TRANSPORT_SR", method))
        if "CLIP_TRANSPORT_SRH" in METHODS[bits]:
            for baseline in ("RTN_ABSMAX", "CLIP_UNIFORM", "CLIP_MARGIN_FRONTIER"):
                comparison_specs.append((bits, "CLIP_TRANSPORT_SRH", baseline))
    for index, (bits, method, comparator) in enumerate(comparison_specs):
        left = results[(results.bit == bits) & (results.method == method)].sort_values("row_hash")
        right = results[(results.bit == bits) & (results.method == comparator)].sort_values("row_hash")
        merged = left.merge(right, on="row_hash", suffixes=("_method", "_comparator"), validate="one_to_one")
        difference = merged.exact_answer_correct_method.astype(float).to_numpy() - merged.exact_answer_correct_comparator.astype(float).to_numpy()
        lo, hi, one_lo = paired_bootstrap(difference, seed=311001 + index)
        n10 = int(((merged.exact_answer_correct_method == 1) & (merged.exact_answer_correct_comparator == 0)).sum())
        n01 = int(((merged.exact_answer_correct_method == 0) & (merged.exact_answer_correct_comparator == 1)).sum())
        pvalue = float(binomtest(n10, n10 + n01, 0.5, alternative="greater").pvalue) if n10 + n01 else 1.0
        comparisons.append({"bit": bits, "method": method, "comparator": comparator, "example_count": len(merged), "accuracy_difference": float(difference.mean()), "bootstrap_lo": lo, "bootstrap_hi": hi, "one_sided_lower_95": one_lo, "mcnemar_method_only_correct": n10, "mcnemar_comparator_only_correct": n01, "mcnemar_one_sided_p": pvalue})
    comparisons_frame = pd.DataFrame(comparisons).drop_duplicates(["bit", "method", "comparator"])
    primary_mask = (comparisons_frame.bit == 4) & (comparisons_frame.method == "CLIP_TRANSPORT_SR") & comparisons_frame.comparator.isin(["RTN_ABSMAX", "CLIP_UNIFORM"])
    comparisons_frame["holm_primary_p"] = np.nan
    comparisons_frame.loc[primary_mask, "holm_primary_p"] = holm_adjust(comparisons_frame.loc[primary_mask, "mcnemar_one_sided_p"].tolist())
    comparisons_frame.to_csv(payload / "derived/paired_task_comparisons.csv", index=False)
    mech_comparisons = []
    for index, metric in enumerate(("answer_agreement_bf16", "terminal_hamming", "B_FS", "split_occurred")):
        for comparator in ("RTN_ABSMAX", "CLIP_UNIFORM", "CLIP_MARGIN_FRONTIER"):
            left = results[(results.bit == 4) & (results.method == "CLIP_TRANSPORT_SR")][["row_hash", metric]]
            right = results[(results.bit == 4) & (results.method == comparator)][["row_hash", metric]]
            merged = left.merge(right, on="row_hash", suffixes=("_method", "_comparator"))
            direction = 1 if metric == "answer_agreement_bf16" else -1
            improvement = direction * (merged[f"{metric}_method"].astype(float).to_numpy() - merged[f"{metric}_comparator"].astype(float).to_numpy())
            lo, hi, _ = paired_bootstrap(improvement, seed=311002 + index * 10 + len(mech_comparisons))
            mech_comparisons.append({"bit": 4, "method": "CLIP_TRANSPORT_SR", "comparator": comparator, "metric": metric, "improvement": float(improvement.mean()), "bootstrap_lo": lo, "bootstrap_hi": hi})
    mechanism_comparisons = pd.DataFrame(mech_comparisons)
    mechanism_comparisons.to_csv(payload / "derived/paired_mechanism_comparisons.csv", index=False)
    return task, mechanism, comparisons_frame, mechanism_comparisons


def determine_gates(task: pd.DataFrame, mechanism: pd.DataFrame, comparisons: pd.DataFrame, mechanism_comparisons: pd.DataFrame, validity: bool) -> tuple[str, str, str]:
    if not validity:
        return "FAIL_TRCAL_1_VALIDITY", "NOT_EVALUATED", "FAIL_TRCAL_1_VALIDITY"
    validity_gate = "PASS_TRCAL_1_VALIDITY"
    def comp(method: str, baseline: str) -> pd.Series:
        return comparisons[(comparisons.bit == 4) & (comparisons.method == method) & (comparisons.comparator == baseline)].iloc[0]
    sr_rtn, sr_uniform, sr_frontier = comp("CLIP_TRANSPORT_SR", "RTN_ABSMAX"), comp("CLIP_TRANSPORT_SR", "CLIP_UNIFORM"), comp("CLIP_TRANSPORT_SR", "CLIP_MARGIN_FRONTIER")
    mechanism_improved = False
    for baseline in ("CLIP_UNIFORM",):
        for metric in ("answer_agreement_bf16", "terminal_hamming", "B_FS", "split_occurred"):
            row = mechanism_comparisons[(mechanism_comparisons.comparator == baseline) & (mechanism_comparisons.metric == metric)].iloc[0]
            base = mechanism[(mechanism.bit == 4) & (mechanism.method == baseline)].iloc[0]
            column = {"answer_agreement_bf16": None, "terminal_hamming": "terminal_hamming", "B_FS": "mean_B_FS", "split_occurred": "split_probability"}[metric]
            denominator = float(task[(task.bit == 4) & (task.method == baseline)].answer_agreement_bf16.iloc[0]) if column is None else float(base[column])
            if denominator > 0 and float(row.improvement) / denominator >= 0.10 and float(row.bootstrap_lo) > 0:
                mechanism_improved = True
    strong = float(sr_rtn.accuracy_difference) >= 0.015 and (float(sr_rtn.one_sided_lower_95) > 0 or float(sr_rtn.holm_primary_p) <= 0.05) and float(sr_uniform.accuracy_difference) >= 0.010 and mechanism_improved and float(sr_frontier.accuracy_difference) >= -0.005
    if strong:
        effect = "TRANSPORT_CALIBRATION_STRONG"
        overall = "PASS_TRCAL_1_STRONG"
        return validity_gate, effect, overall
    partial = False
    w4_task_partial = float(sr_rtn.accuracy_difference) >= 0.010 and float(sr_uniform.accuracy_difference) >= 0.010 and mechanism_improved
    if w4_task_partial:
        partial = True
    best_baseline_accuracy = float(task[(task.bit == 4) & task.method.isin(["RTN_ABSMAX", "CLIP_UNIFORM", "CLIP_MARGIN_FRONTIER"])].exact_answer_accuracy.max())
    sr_accuracy = float(task[(task.bit == 4) & (task.method == "CLIP_TRANSPORT_SR")].exact_answer_accuracy.iloc[0])
    if sr_accuracy >= best_baseline_accuracy - 0.005:
        for metric in ("B_FS", "split_occurred"):
            row = mechanism_comparisons[(mechanism_comparisons.comparator == "CLIP_UNIFORM") & (mechanism_comparisons.metric == metric)].iloc[0]
            baseline_column = "mean_B_FS" if metric == "B_FS" else "split_probability"
            denominator = float(mechanism[(mechanism.bit == 4) & (mechanism.method == "CLIP_UNIFORM")][baseline_column].iloc[0])
            if denominator > 0 and float(row.improvement) / denominator >= 0.15 and float(row.bootstrap_lo) > 0:
                partial = True
    reversed_effect = float(sr_rtn.accuracy_difference) <= -0.015 and float(sr_uniform.accuracy_difference) <= -0.015 and (float(sr_rtn.bootstrap_hi) < 0 or float(sr_rtn.holm_primary_p) <= 0.05)
    if reversed_effect:
        return validity_gate, "TRANSPORT_CALIBRATION_REVERSED", "PASS_TRCAL_1_REVERSED"
    if partial:
        return validity_gate, "TRANSPORT_CALIBRATION_PARTIAL", "PASS_TRCAL_1_PARTIAL"
    return validity_gate, "NO_TRANSPORT_CALIBRATION_EFFECT", "PASS_TRCAL_1_NEGATIVE"
