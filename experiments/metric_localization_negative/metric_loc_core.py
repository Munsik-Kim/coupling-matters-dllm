from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import random
import shutil
import statistics
import sys
import tempfile
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from safetensors import safe_open
from scipy.optimize import linprog
from scipy.stats import pointbiserialr, spearmanr
from sklearn.metrics import roc_auc_score
from transformers import AutoTokenizer


ALPHA = 0.05
SEVERITIES = ("W8", "W6", "W4")
METRICS = ("hamming", "embedding_hybrid", "tokenizer_byte_hybrid")
METRIC_LABELS = {
    "hamming": "Exact-token Hamming",
    "embedding_hybrid": "Embedding hybrid (alpha=0.05)",
    "tokenizer_byte_hybrid": "Tokenizer-byte hybrid (alpha=0.05)",
}
SOURCE_ARCHIVES = {
    "CERT3": {
        "relative": "wp06_cert3_cmc_full_20260731_114704_full_review.zip",
        "size": 119_713_469,
        "sha256": "f99e316c4a21a02d5c59aefaa9ee9401b3d0eaa23b984e1eead09dd4abb1fc45",
    },
    "CERT3R": {
        "absolute": "<PROJECT_AUDIT_ROOT>/external_inputs/PAPER_V09_RAW_TO_CLAIM_AUDIT/references/CERT3R_review.zip",
        "size": 456_198,
        "sha256": "a6c831997f35269d0c3f468f4874cb54f05d1a8c18b924759a59f9f921e8aac3",
    },
    "WP07C": {
        "relative": "runs/wp07c_prompt_population_16tok_20260801_115858/wp07c_prompt_population_16tok_20260801_115858_full_review.zip",
        "size": 102_709_093,
        "sha256": "dbb76ac22aa1734d5c168ebeb8c725c16b35165b3b07f8ed942a9d1f7ec235d3",
    },
    "WP07D": {
        "relative": "runs/wp07d_smdm_local_confirmatory_20260731_193059/wp07d_smdm_local_confirmatory_20260731_193059_full_review.zip",
        "size": 26_241_387,
        "sha256": "ffec696f7a5eb4f1f0d46dddc2dd83c8fd4262a1d52b43086d32205e5b3d7360",
    },
    "WP07D_CORRECTED_SUMMARY": {
        "absolute": "<PROJECT_AUDIT_ROOT>/external_inputs/PAPER_V09_RAW_TO_CLAIM_AUDIT/references/wp07d_corrected_summary_release.zip",
        "size": 4_996,
        "sha256": "0dd8fe3105555a8af58691ff44e62cca9774477c1dd5c70e8c5ba3e05b75491d",
    },
    "LOCAL_LIFT_TEMP_1": {
        "relative": "runs/LOCAL_LIFT_TEMP_1_20260803_083922/LOCAL_LIFT_TEMP_1_full_review.zip",
        "size": 104_355_539,
        "sha256": "20d04e580268b58de3d840d82db5e327c9704c7205ce5b48f579467a6990d65a",
    },
    "LOCAL_LIFT_TEMP_1R": {
        "relative": "runs/LOCAL_LIFT_TEMP_1R_20260803_105122/LOCAL_LIFT_TEMP_1R_full_review.zip",
        "size": 516_230,
        "sha256": "11a2673ea1301e944a9ba7fa20759dfdc9af49deb4abaac5742fbf1da9566d69",
    },
    "LOCAL_LIFT_1_TRANSITIVE": {
        "relative": "runs/LOCAL_LIFT_1_20260802_104002/LOCAL_LIFT_1_full_review.zip",
        "size": 71_680_668,
        "sha256": "65a4cad00d6602e515ec545098baa9dd3b8bcea683d0b6c28a71e7fe4536af51",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_parquet_glob(directory: Path) -> pd.DataFrame:
    files = sorted(directory.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet shards under {directory}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def resolve_archive(project_root: Path, spec: dict[str, Any]) -> Path:
    if "absolute" in spec:
        return Path(spec["absolute"])
    return project_root / spec["relative"]


def _verify_internal_sums(zf: zipfile.ZipFile) -> dict[str, Any]:
    manifests = [name for name in zf.namelist() if name.endswith("SHA256SUMS.txt")]
    checked = 0
    failures: list[dict[str, str]] = []
    for manifest in manifests:
        base = str(Path(manifest).parent)
        text = zf.read(manifest).decode("utf-8", errors="replace")
        for line in text.splitlines():
            if not line.strip() or "  " not in line:
                continue
            expected, rel = line.split("  ", 1)
            rel = rel.strip().lstrip("./")
            candidates = [rel, f"{base}/{rel}" if base != "." else rel]
            if rel.startswith("full_review/"):
                candidates.append(rel)
            candidates = list(dict.fromkeys(candidate.replace("//", "/") for candidate in candidates))
            member = next((candidate for candidate in candidates if candidate in zf.namelist()), None)
            if member is None:
                failures.append({"manifest": manifest, "path": rel, "reason": "missing"})
                continue
            actual = sha256_bytes(zf.read(member))
            checked += 1
            if actual != expected:
                failures.append({"manifest": manifest, "path": member, "reason": "hash", "actual": actual})
    return {"manifest_count": len(manifests), "checked_file_count": checked, "failure_count": len(failures), "failures": failures[:50]}


def verify_source_archives(project_root: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    records: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for name, spec in SOURCE_ARCHIVES.items():
        path = resolve_archive(project_root, spec)
        if not path.exists():
            raise FileNotFoundError(f"INCOMPLETE_METRIC_LOC_1_MISSING_SOURCE: {name}: {path}")
        size = path.stat().st_size
        digest = sha256_file(path)
        with zipfile.ZipFile(path) as zf:
            bad_member = zf.testzip()
            internal = _verify_internal_sums(zf)
            zip_entries = len(zf.infolist())
        passed = size == spec["size"] and digest == spec["sha256"] and bad_member is None and internal["failure_count"] == 0
        record = {
            "source": name,
            "path": str(path),
            "expected_size": spec["size"],
            "observed_size": size,
            "expected_sha256": spec["sha256"],
            "observed_sha256": digest,
            "crc_pass": bad_member is None,
            "internal_manifest_pass": internal["failure_count"] == 0,
            "zip_entry_count": zip_entries,
            "pass": passed,
        }
        records.append(record)
        details[name] = {**record, "internal_manifest": internal}
        if not passed:
            raise RuntimeError(f"Source archive verification failed: {stable_json(record)}")
    return details, pd.DataFrame(records)


def levenshtein_bytes(left: bytes, right: bytes) -> int:
    if left == right:
        return 0
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for j, rb in enumerate(right, 1):
        current = [j]
        for i, lb in enumerate(left, 1):
            current.append(min(current[-1] + 1, previous[i] + 1, previous[i - 1] + (lb != rb)))
        previous = current
    return previous[-1]


@dataclass
class FrozenMetricAsset:
    family: str
    checkpoint: Path
    checkpoint_sha256: str
    embedding_key: str
    tokenizer_ref: str
    mask_id: int
    vocab_size: int
    tokenizer: Any
    embeddings: np.ndarray
    piece_bytes: list[bytes]
    l_max: int
    ledger: dict[str, Any]


def _token_piece_bytes(tokenizer: Any, token_id: int, family: str) -> bytes:
    token = tokenizer.convert_ids_to_tokens(int(token_id))
    if token is None:
        return b""
    if family == "MDLM_GPT2":
        decoder = getattr(tokenizer, "byte_decoder", {})
        try:
            return bytes(decoder[character] for character in token)
        except KeyError:
            return token.encode("utf-8")
    if token.startswith("<0x") and token.endswith(">") and len(token) == 6:
        try:
            return bytes([int(token[3:5], 16)])
        except ValueError:
            pass
    return token.replace("▁", " ").encode("utf-8")


def _file_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    return {"path": str(path), "resolved_path": str(resolved), "size": resolved.stat().st_size, "sha256": sha256_file(resolved)}


def load_metric_assets(project_root: Path) -> tuple[dict[str, FrozenMetricAsset], dict[str, Any], dict[str, Any]]:
    specs = {
        "MDLM_GPT2": {
            "checkpoint": project_root / "external/mdlm-no-flash-transformers59/model.safetensors",
            "sha256": "47149e73f7552f39ea9776dbe74d925d25237bcf2ed2e2ec03cdff9d51c82aa4",
            "embedding_key": "backbone.vocab_embed.embedding",
            "tokenizer": "gpt2",
            "mask_id": 50257,
            "vocab_size": 50257,
        },
        "SMDM_GSM8K": {
            "checkpoint": Path("<EXTERNAL_ASSET_ROOT>/checkpoints/nieshen_SMDM_bcda56b/gsm8k_safetensors/mdm-1028M-3300e18-rsl-gsm8k.safetensors"),
            "sha256": "1e968c26419d5b041adf3b1825e6d2b10887c45cdab76e60ea2d8341df31618f",
            "embedding_key": "transformer.wte.weight",
            "tokenizer": "<EXTERNAL_ASSET_ROOT>/tokenizers/TinyLlama_59f6f37",
            "mask_id": 32000,
            "vocab_size": 32000,
        },
    }
    assets: dict[str, FrozenMetricAsset] = {}
    embedding_ledger: dict[str, Any] = {}
    tokenizer_ledger: dict[str, Any] = {}
    for family, spec in specs.items():
        checkpoint = Path(spec["checkpoint"])
        if not checkpoint.exists():
            raise FileNotFoundError(f"Embedding checkpoint missing: {checkpoint}")
        tokenizer = AutoTokenizer.from_pretrained(spec["tokenizer"], local_files_only=True, use_fast=False)
        with safe_open(str(checkpoint), framework="pt", device="cpu") as handle:
            if spec["embedding_key"] not in handle.keys():
                raise KeyError(f"Missing embedding key {spec['embedding_key']} in {checkpoint}")
            tensor = handle.get_tensor(spec["embedding_key"])
            raw_dtype = str(tensor.dtype)
            embeddings = tensor.float().numpy()
        if embeddings.shape[0] < spec["vocab_size"]:
            raise ValueError(f"Embedding vocabulary too small: {family}: {embeddings.shape}")
        embeddings = embeddings[: spec["vocab_size"]]
        norms = np.linalg.norm(embeddings, axis=1)
        zero_ids = np.flatnonzero(norms < 1e-12).astype(int).tolist()
        normalized = np.zeros_like(embeddings, dtype=np.float32)
        valid = norms >= 1e-12
        normalized[valid] = embeddings[valid] / norms[valid, None]
        pieces = [_token_piece_bytes(tokenizer, token_id, family) for token_id in range(spec["vocab_size"])]
        lengths = np.asarray([len(piece) for piece in pieces], dtype=np.int64)
        l_max = max(1, int(lengths.max(initial=0)))
        tokenizer_files: list[dict[str, Any]] = []
        if family == "MDLM_GPT2":
            for key in ("vocab_file", "merges_file"):
                value = tokenizer.init_kwargs.get(key)
                if value:
                    tokenizer_files.append(_file_identity(Path(value)))
        else:
            for name in ("tokenizer.json", "tokenizer.model", "tokenizer_config.json", "special_tokens_map.json"):
                path = Path(spec["tokenizer"]) / name
                if path.exists():
                    tokenizer_files.append(_file_identity(path))
        special_ids = sorted(set(int(value) for value in tokenizer.all_special_ids if value is not None))
        embedding_ledger[family] = {
            "checkpoint_path": str(checkpoint),
            "checkpoint_provenance_sha256": spec["sha256"],
            "checkpoint_size": checkpoint.stat().st_size,
            "embedding_key": spec["embedding_key"],
            "embedding_shape": list(embeddings.shape),
            "embedding_source_dtype": raw_dtype,
            "normalized_dtype": str(normalized.dtype),
            "zero_norm_token_ids": zero_ids,
            "input_embedding_selected": True,
            "tied_input_output_embeddings": False,
            "tie_note": "A distinct output-layer key is present; the preregistered input embedding was used.",
        }
        tokenizer_ledger[family] = {
            "tokenizer_reference": spec["tokenizer"],
            "tokenizer_class": type(tokenizer).__name__,
            "vocabulary_size": spec["vocab_size"],
            "mask_token_id": spec["mask_id"],
            "special_token_ids": special_ids,
            "tokenizer_files": tokenizer_files,
            "piece_extraction": "GPT-2 byte-decoder mapping" if family == "MDLM_GPT2" else "SentencePiece token string; U+2581 mapped to ASCII space; byte-fallback tokens decoded",
            "contextual_decode_used": False,
            "maximum_piece_byte_length": l_max,
            "empty_piece_token_ids": np.flatnonzero(lengths == 0).astype(int).tolist(),
        }
        assets[family] = FrozenMetricAsset(
            family=family,
            checkpoint=checkpoint,
            checkpoint_sha256=spec["sha256"],
            embedding_key=spec["embedding_key"],
            tokenizer_ref=str(spec["tokenizer"]),
            mask_id=int(spec["mask_id"]),
            vocab_size=int(spec["vocab_size"]),
            tokenizer=tokenizer,
            embeddings=normalized,
            piece_bytes=pieces,
            l_max=l_max,
            ledger=embedding_ledger[family],
        )
    return assets, embedding_ledger, tokenizer_ledger


class TokenCostCache:
    def __init__(self, assets: dict[str, FrozenMetricAsset]):
        self.assets = assets
        self.cache: dict[tuple[str, int, int], tuple[float, float, float]] = {}

    def costs(self, family: str, left: int, right: int) -> tuple[float, float, float]:
        a, b = sorted((int(left), int(right)))
        key = (family, a, b)
        if key in self.cache:
            return self.cache[key]
        asset = self.assets[family]
        if a == b:
            result = (0.0, 0.0, 0.0)
        elif a == asset.mask_id or b == asset.mask_id:
            result = (1.0, 1.0, 1.0)
        else:
            if not (0 <= a < asset.vocab_size and 0 <= b < asset.vocab_size):
                raise ValueError(f"Out-of-vocabulary terminal token: {family}: {a}, {b}")
            distance = float(np.linalg.norm(asset.embeddings[a] - asset.embeddings[b]) / 2.0)
            emb = ALPHA + (1.0 - ALPHA) * distance
            byte_distance = levenshtein_bytes(asset.piece_bytes[a], asset.piece_bytes[b]) / asset.l_max
            byte = ALPHA + (1.0 - ALPHA) * byte_distance
            result = (1.0, float(min(1.0, max(0.0, emb))), float(min(1.0, max(0.0, byte))))
        self.cache[key] = result
        return result

    def one(self, metric: str, family: str, left: int, right: int) -> float:
        return self.costs(family, left, right)[METRICS.index(metric)]

    def frame(self) -> pd.DataFrame:
        rows = []
        for (family, left, right), values in sorted(self.cache.items()):
            rows.append({"model_family": family, "token_a": left, "token_b": right, **dict(zip(METRICS, values))})
        return pd.DataFrame(rows)


def pair_metric(tokens_left: Sequence[int], tokens_right: Sequence[int], family: str, cache: TokenCostCache) -> tuple[float, float, float, int]:
    asset = cache.assets[family]
    length = max(len(tokens_left), len(tokens_right))
    if length == 0:
        return 0.0, 0.0, 0.0, 0
    left = list(map(int, tokens_left)) + [asset.mask_id] * (length - len(tokens_left))
    right = list(map(int, tokens_right)) + [asset.mask_id] * (length - len(tokens_right))
    values = np.asarray([cache.costs(family, a, b) for a, b in zip(left, right)], dtype=np.float64)
    return float(values[:, 0].mean()), float(values[:, 1].mean()), float(values[:, 2].mean()), length


def _json_tokens(value: Any) -> list[int]:
    if isinstance(value, str):
        return [int(token) for token in json.loads(value)]
    if isinstance(value, np.ndarray):
        return [int(token) for token in value.tolist()]
    return [int(token) for token in value]


def load_cert3_pairs(project_root: Path) -> pd.DataFrame:
    base = project_root / "runs/wp06_cert3_cmc_full_20260731_114704/payload"
    rows: list[dict[str, Any]] = []
    for family, directory in (("CMC", "cmc_trajectories"), ("inverse_CDF_CRN", "crn_trajectories")):
        frame = read_parquet_glob(base / "raw" / directory)
        if family == "CMC" and len(frame) != 768:
            raise ValueError(f"CERT-3 CMC count: {len(frame)}")
        if family == "inverse_CDF_CRN" and len(frame) != 384:
            raise ValueError(f"CERT-3 CRN count: {len(frame)}")
        for row in frame.to_dict("records"):
            rows.append({
                "panel": "CERT3",
                "model_family": "MDLM_GPT2",
                "pair_type": "FP_Q",
                "coupling": family,
                "prompt_id": str(row["prompt_id"]),
                "prompt_hash": str(row["prompt_hash"]),
                "draw_id": int(row["coupling_seed"]),
                "severity": str(row["severity"]),
                "temperature": np.nan,
                "left_tokens": _json_tokens(row["fp_terminal_tokens_json"]),
                "right_tokens": _json_tokens(row["q_terminal_tokens_json"]),
                "source_D": float(row["terminal_D"]),
                "source_edit_distance": np.nan,
                "answer_disagreement": np.nan,
                "correctness_disagreement": np.nan,
                "absolute_correctness_change": np.nan,
                "left_answer": None,
                "right_answer": None,
                "left_correct": None,
                "right_correct": None,
                "source_path": directory,
            })
    fp = read_parquet_glob(base / "raw/fp_reference_trajectories")
    fp = fp[fp["horizon"] == "FULL"].copy()
    if len(fp) != 256:
        raise ValueError(f"CERT-3 FP terminal count: {len(fp)}")
    lookup = {(str(r.prompt_id), int(r.fp_seed)): r for r in fp.itertuples(index=False)}
    for prompt_id in sorted(fp.prompt_id.unique()):
        for pair_index, (left_seed, right_seed) in enumerate(((260740, 260741), (260742, 260743))):
            left = lookup[(str(prompt_id), left_seed)]
            right = lookup[(str(prompt_id), right_seed)]
            rows.append({
                "panel": "CERT3",
                "model_family": "MDLM_GPT2",
                "pair_type": "FP_FP_INDEPENDENT",
                "coupling": "independent_FP",
                "prompt_id": str(prompt_id),
                "prompt_hash": str(left.prompt_hash),
                "draw_id": pair_index,
                "severity": "FP_REFERENCE",
                "temperature": np.nan,
                "left_tokens": _json_tokens(left.generation_tokens_json),
                "right_tokens": _json_tokens(right.generation_tokens_json),
                "source_D": np.nan,
                "source_edit_distance": np.nan,
                "answer_disagreement": np.nan,
                "correctness_disagreement": np.nan,
                "absolute_correctness_change": np.nan,
                "left_answer": None,
                "right_answer": None,
                "left_correct": None,
                "right_correct": None,
                "source_path": "fp_reference_trajectories",
            })
    result = pd.DataFrame(rows)
    if len(result) != 1_280:
        raise ValueError(f"CERT-3 terminal pair count: {len(result)}")
    return result


def load_wp07c_pairs(project_root: Path) -> pd.DataFrame:
    base = project_root / "runs/wp07c_prompt_population_16tok_20260801_115858/payload"
    frame = read_parquet_glob(base / "raw/cmc_trajectories")
    if len(frame) != 768:
        raise ValueError(f"WP07C CMC count: {len(frame)}")
    rows = []
    for row in frame.to_dict("records"):
        rows.append({
            "panel": "WP07C",
            "model_family": "MDLM_GPT2",
            "pair_type": "FP_Q",
            "coupling": "CMC",
            "prompt_id": str(row["prompt_id"]),
            "prompt_hash": str(row["prompt_hash"]),
            "draw_id": int(row["coupling_seed"]),
            "severity": str(row["severity"]),
            "temperature": np.nan,
            "left_tokens": _json_tokens(row["fp_terminal_tokens_json"]),
            "right_tokens": _json_tokens(row["q_terminal_tokens_json"]),
            "source_D": float(row["terminal_D"]),
            "source_edit_distance": np.nan,
            "answer_disagreement": np.nan,
            "correctness_disagreement": np.nan,
            "absolute_correctness_change": np.nan,
            "left_answer": None,
            "right_answer": None,
            "left_correct": None,
            "right_correct": None,
            "source_path": "cmc_trajectories",
        })
    return pd.DataFrame(rows)


def load_wp07d_pairs(project_root: Path) -> pd.DataFrame:
    base = project_root / "runs/wp07d_smdm_local_confirmatory_20260731_193059/payload/raw/gsm8k_outputs"
    frames: dict[tuple[str, int], pd.DataFrame] = {}
    for precision in ("BF16", "W8", "W6", "W4"):
        for seed in (260748, 260749):
            path = base / f"{precision.lower()}_seed{seed}.parquet"
            frame = pd.read_parquet(path)
            if len(frame) != 100:
                raise ValueError(f"WP07D output count {precision}/{seed}: {len(frame)}")
            frames[(precision, seed)] = frame.set_index("row_id", drop=False)
    rows: list[dict[str, Any]] = []
    for seed in (260748, 260749):
        fp = frames[("BF16", seed)]
        for severity in SEVERITIES:
            q = frames[(severity, seed)]
            for row_id in sorted(fp.index):
                left = fp.loc[row_id]
                right = q.loc[row_id]
                answer_disagreement = str(left.predicted_answer) != str(right.predicted_answer)
                correctness_disagreement = bool(left.exact_numeric_correct) != bool(right.exact_numeric_correct)
                rows.append({
                    "panel": "WP07D_GSM8K",
                    "model_family": "SMDM_GSM8K",
                    "pair_type": "BF16_Q",
                    "coupling": "official_greddy_descriptive",
                    "prompt_id": f"gsm8k_{int(row_id):03d}",
                    "prompt_hash": str(left.question_hash),
                    "draw_id": int(seed),
                    "severity": severity,
                    "temperature": np.nan,
                    "left_tokens": _json_tokens(left.generated_token_ids),
                    "right_tokens": _json_tokens(right.generated_token_ids),
                    "source_D": np.nan,
                    "source_edit_distance": np.nan,
                    "answer_disagreement": bool(answer_disagreement),
                    "correctness_disagreement": bool(correctness_disagreement),
                    "absolute_correctness_change": float(abs(int(bool(left.exact_numeric_correct)) - int(bool(right.exact_numeric_correct)))),
                    "left_answer": str(left.predicted_answer),
                    "right_answer": str(right.predicted_answer),
                    "left_correct": bool(left.exact_numeric_correct),
                    "right_correct": bool(right.exact_numeric_correct),
                    "source_path": f"gsm8k_outputs/{severity.lower()}_seed{seed}.parquet",
                })
    result = pd.DataFrame(rows)
    if len(result) != 600:
        raise ValueError(f"WP07D paired output count: {len(result)}")
    source_pairs = pd.read_csv(project_root / "runs/wp07d_smdm_local_confirmatory_20260731_193059/payload/derived/gsm8k_paired_rows.csv")
    lookup = {(int(r.row_id), int(r.decoding_seed), str(r.precision)): float(r.normalized_token_edit_distance) for r in source_pairs.itertuples(index=False)}
    result["source_edit_distance"] = [lookup[(int(row.prompt_id.split("_")[-1]), int(row.draw_id), str(row.severity))] for row in result.itertuples(index=False)]
    return result


def _temp_checkpoint_row(path: Path, source_label: str) -> dict[str, Any]:
    document = read_json(path)
    trajectory = document["trajectory"]
    task = document["task_output"]
    return {
        "panel": "LOCAL_LIFT_TEMP",
        "model_family": "SMDM_GSM8K",
        "pair_type": "FP_Q",
        "coupling": str(trajectory.get("coupling_scheme", "LIFTED_CMC" if source_label == "FROZEN_LOCAL_LIFT_1" else "UNKNOWN")),
        "prompt_id": str(trajectory["prompt_id"]),
        "prompt_hash": hashlib.sha256(str(trajectory["prompt_id"]).encode()).hexdigest(),
        "draw_id": int(trajectory["coupling_draw"]),
        "severity": str(trajectory["precision"]),
        "temperature": float(trajectory["temperature"]),
        "left_tokens": _json_tokens(task["fp_token_ids"]),
        "right_tokens": _json_tokens(task["q_token_ids"]),
        "source_D": float(trajectory["terminal_D"]),
        "source_edit_distance": np.nan,
        "answer_disagreement": str(task.get("fp_answer")) != str(task.get("q_answer")),
        "correctness_disagreement": bool(task.get("fp_correct")) != bool(task.get("q_correct")),
        "absolute_correctness_change": float(abs(int(bool(task.get("fp_correct"))) - int(bool(task.get("q_correct"))))),
        "left_answer": str(task.get("fp_answer")),
        "right_answer": str(task.get("q_answer")),
        "left_correct": bool(task.get("fp_correct")),
        "right_correct": bool(task.get("q_correct")),
        "source_path": f"{source_label}:{path.name}",
    }


def load_local_lift_pairs(project_root: Path) -> pd.DataFrame:
    new_dir = project_root / "runs/LOCAL_LIFT_TEMP_1_20260803_083922/payload/raw/checkpoints"
    new_paths = sorted(new_dir.glob("*.json"))
    if len(new_paths) != 960:
        raise ValueError(f"TEMP-1 checkpoint count: {len(new_paths)}")
    rows = [_temp_checkpoint_row(path, "LOCAL_LIFT_TEMP_1") for path in new_paths]
    predecessor_dir = project_root / "runs/LOCAL_LIFT_1_20260802_104002/raw/checkpoints"
    predecessor_paths = sorted(predecessor_dir.glob("*.json"))
    if len(predecessor_paths) != 320:
        raise ValueError(f"LOCAL-LIFT-1 checkpoint count: {len(predecessor_paths)}")
    for path in predecessor_paths:
        row = _temp_checkpoint_row(path, "FROZEN_LOCAL_LIFT_1")
        if row["temperature"] == 0.2 and len(row["left_tokens"]) == 16:
            rows.append(row)
    result = pd.DataFrame(rows)
    if len(result) != 1_152:
        raise ValueError(f"Combined temperature terminal pair count: {len(result)}")
    expected = result.groupby(["temperature", "coupling"]).size().to_dict()
    required = {(0.2, "LIFTED_CMC"): 192, (0.2, "PROPOSAL_CRN"): 192, (0.5, "LIFTED_CMC"): 192, (0.5, "PROPOSAL_CRN"): 192, (1.0, "LIFTED_CMC"): 192, (1.0, "PROPOSAL_CRN"): 192}
    if expected != required:
        raise ValueError(f"Temperature grid mismatch: {expected}")
    return result


def compute_pair_metrics(frame: pd.DataFrame, cache: TokenCostCache) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source in frame.to_dict("records"):
        hamming, embedding, byte, aligned_length = pair_metric(source["left_tokens"], source["right_tokens"], source["model_family"], cache)
        row = {key: value for key, value in source.items() if key not in ("left_tokens", "right_tokens")}
        row.update({
            "left_tokens": source["left_tokens"],
            "right_tokens": source["right_tokens"],
            "aligned_length": aligned_length,
            "D_hamming": hamming,
            "D_embedding_hybrid": embedding,
            "D_tokenizer_byte_hybrid": byte,
            "hamming_source_abs_error": abs(hamming - float(source["source_D"])) if pd.notna(source["source_D"]) else np.nan,
        })
        rows.append(row)
    return pd.DataFrame(rows)


def metric_column(metric: str) -> str:
    return {"hamming": "D_hamming", "embedding_hybrid": "D_embedding_hybrid", "tokenizer_byte_hybrid": "D_tokenizer_byte_hybrid"}[metric]


def summarize_terminal_metrics(pairs: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cert = pairs[(pairs.panel == "CERT3") & (pairs.pair_type == "FP_Q")]
    cert_summary = cert.groupby(["coupling", "severity"], as_index=False).agg(
        trajectory_count=("prompt_id", "size"),
        mean_D_hamming=("D_hamming", "mean"),
        mean_D_embedding_hybrid=("D_embedding_hybrid", "mean"),
        mean_D_tokenizer_byte_hybrid=("D_tokenizer_byte_hybrid", "mean"),
    )
    wp07c = pairs[pairs.panel == "WP07C"]
    wp07c_summary = wp07c.groupby(["coupling", "severity"], as_index=False).agg(
        trajectory_count=("prompt_id", "size"),
        prompt_count=("prompt_id", "nunique"),
        mean_D_hamming=("D_hamming", "mean"),
        mean_D_embedding_hybrid=("D_embedding_hybrid", "mean"),
        mean_D_tokenizer_byte_hybrid=("D_tokenizer_byte_hybrid", "mean"),
    )
    local = pairs[pairs.panel == "LOCAL_LIFT_TEMP"]
    local_summary = local.groupby(["temperature", "coupling", "severity"], as_index=False).agg(
        trajectory_count=("prompt_id", "size"),
        mean_D_hamming=("D_hamming", "mean"),
        mean_D_embedding_hybrid=("D_embedding_hybrid", "mean"),
        mean_D_tokenizer_byte_hybrid=("D_tokenizer_byte_hybrid", "mean"),
    )
    task_raw = pairs[pairs.panel == "WP07D_GSM8K"].copy()
    task_rows = task_raw.groupby(["prompt_id", "prompt_hash", "severity"], as_index=False).agg(
        seed_count=("draw_id", "nunique"),
        D_hamming=("D_hamming", "mean"),
        D_embedding_hybrid=("D_embedding_hybrid", "mean"),
        D_tokenizer_byte_hybrid=("D_tokenizer_byte_hybrid", "mean"),
        answer_disagreement=("answer_disagreement", "max"),
        correctness_disagreement=("correctness_disagreement", "max"),
        absolute_correctness_change=("absolute_correctness_change", "mean"),
        frozen_token_edit_distance=("source_edit_distance", "mean"),
    )
    task_rows["answer_aggregation"] = "any disagreement across two frozen decoding seeds"
    task_rows["metric_aggregation"] = "mean across two frozen decoding seeds"
    return {"cert3": cert_summary, "wp07c": wp07c_summary, "local_lift": local_summary, "wp07d_rows": task_rows}


def _cluster_means(frame: pd.DataFrame, value: str, cluster: str = "prompt_id") -> pd.Series:
    return frame.groupby(cluster)[value].mean().sort_index()


def saturation_and_ordering(pairs: pd.DataFrame, resamples: int = 20_000, seed: int = 301001) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    cert = pairs[pairs.panel == "CERT3"].copy()
    reference = cert[cert.pair_type == "FP_FP_INDEPENDENT"]
    saturation_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    prompt_ids = sorted(reference.prompt_id.unique())
    index = {prompt: i for i, prompt in enumerate(prompt_ids)}
    draw_indices = rng.integers(0, len(prompt_ids), size=(resamples, len(prompt_ids)), endpoint=False)
    for metric in METRICS:
        column = metric_column(metric)
        denominator_series = _cluster_means(reference, column).reindex(prompt_ids)
        denominator = denominator_series.to_numpy(dtype=float)
        for coupling in ("CMC", "inverse_CDF_CRN"):
            for severity in SEVERITIES:
                cell = cert[(cert.pair_type == "FP_Q") & (cert.coupling == coupling) & (cert.severity == severity)]
                numerator = _cluster_means(cell, column).reindex(prompt_ids).to_numpy(dtype=float)
                mean_num = float(numerator.mean())
                mean_den = float(denominator.mean())
                ratio = mean_num / mean_den if mean_den > 0 else np.nan
                difference = mean_num - mean_den
                boot_num = numerator[draw_indices].mean(axis=1)
                boot_den = denominator[draw_indices].mean(axis=1)
                valid = boot_den > 0
                boot_ratio = np.divide(boot_num, boot_den, out=np.full_like(boot_num, np.nan), where=valid)
                boot_difference = boot_num - boot_den
                saturation_rows.append({
                    "metric": metric,
                    "coupling": coupling,
                    "severity": severity,
                    "mean_fp_q": mean_num,
                    "mean_fp_fp_independent": mean_den,
                    "saturation_ratio": ratio,
                    "headroom": 1.0 - ratio if np.isfinite(ratio) else np.nan,
                    "quantization_minus_intrinsic": difference,
                    "prompt_count": len(prompt_ids),
                })
                bootstrap_rows.extend([
                    {"analysis": "saturation_ratio", "metric": metric, "coupling": coupling, "severity": severity, "estimate": ratio, "ci_low": float(np.nanpercentile(boot_ratio, 2.5)), "ci_high": float(np.nanpercentile(boot_ratio, 97.5)), "resamples": resamples, "seed": seed},
                    {"analysis": "quantization_minus_intrinsic", "metric": metric, "coupling": coupling, "severity": severity, "estimate": difference, "ci_low": float(np.percentile(boot_difference, 2.5)), "ci_high": float(np.percentile(boot_difference, 97.5)), "resamples": resamples, "seed": seed},
                ])
    ordering_rows: list[dict[str, Any]] = []

    def add_ordering(panel: str, coupling: str, frame: pd.DataFrame, metric: str, extra: dict[str, Any] | None = None) -> None:
        column = metric_column(metric)
        means = frame.groupby("severity")[column].mean().to_dict()
        prompt_means = frame.groupby(["prompt_id", "severity"])[column].mean().unstack("severity")
        prompt_means = prompt_means.dropna(subset=list(SEVERITIES))
        prompt_order = (prompt_means["W8"] <= prompt_means["W6"]) & (prompt_means["W6"] <= prompt_means["W4"])
        row = {
            "panel": panel,
            "coupling": coupling,
            "metric": metric,
            "mean_W8": float(means.get("W8", np.nan)),
            "mean_W6": float(means.get("W6", np.nan)),
            "mean_W4": float(means.get("W4", np.nan)),
            "aggregate_ordering_pass": bool(means.get("W8", np.inf) <= means.get("W6", -np.inf) <= means.get("W4", -np.inf)),
            "prompt_or_example_ordering_rate": float(prompt_order.mean()) if len(prompt_order) else np.nan,
            "cluster_count": int(len(prompt_order)),
        }
        if extra:
            row.update(extra)
        ordering_rows.append(row)

    for metric in METRICS:
        for coupling in ("CMC", "inverse_CDF_CRN"):
            add_ordering("CERT3", coupling, pairs[(pairs.panel == "CERT3") & (pairs.pair_type == "FP_Q") & (pairs.coupling == coupling)], metric)
        add_ordering("WP07C", "CMC", pairs[pairs.panel == "WP07C"], metric)
        add_ordering("WP07D_GSM8K", "BF16_vs_quantized", pairs[pairs.panel == "WP07D_GSM8K"], metric)
        local = pairs[pairs.panel == "LOCAL_LIFT_TEMP"]
        for (temperature, coupling), group in local.groupby(["temperature", "coupling"]):
            add_ordering("LOCAL_LIFT_TEMP", str(coupling), group, metric, {"temperature": float(temperature)})
    return pd.DataFrame(saturation_rows), pd.DataFrame(ordering_rows), pd.DataFrame(bootstrap_rows)


def _safe_auc(y: np.ndarray, score: np.ndarray) -> float:
    return float(roc_auc_score(y, score)) if len(np.unique(y)) == 2 else np.nan


def _safe_spearman(left: np.ndarray, right: np.ndarray) -> float:
    result = spearmanr(left, right)
    return float(result.statistic) if np.isfinite(result.statistic) else np.nan


def _safe_pointbiserial(binary: np.ndarray, score: np.ndarray) -> float:
    if len(np.unique(binary)) < 2:
        return np.nan
    result = pointbiserialr(binary, score)
    return float(result.statistic) if np.isfinite(result.statistic) else np.nan


def task_relevance(task_rows: pd.DataFrame, resamples: int = 20_000, seed: int = 301002) -> tuple[pd.DataFrame, dict[str, Any]]:
    estimates: list[dict[str, Any]] = []
    for metric in METRICS:
        column = metric_column(metric)
        score = task_rows[column].to_numpy(dtype=float)
        answer = task_rows.answer_disagreement.astype(int).to_numpy()
        correctness = task_rows.correctness_disagreement.astype(int).to_numpy()
        estimates.extend([
            {"metric": metric, "statistic": "answer_disagreement_auc", "estimate": _safe_auc(answer, score)},
            {"metric": metric, "statistic": "correctness_disagreement_auc", "estimate": _safe_auc(correctness, score)},
            {"metric": metric, "statistic": "mean_answer_agree", "estimate": float(score[answer == 0].mean())},
            {"metric": metric, "statistic": "mean_answer_disagree", "estimate": float(score[answer == 1].mean())},
            {"metric": metric, "statistic": "spearman_frozen_token_edit", "estimate": _safe_spearman(score, task_rows.frozen_token_edit_distance.to_numpy(dtype=float))},
            {"metric": metric, "statistic": "point_biserial_answer_disagreement", "estimate": _safe_pointbiserial(answer, score)},
        ])
    point = pd.DataFrame(estimates)
    examples = sorted(task_rows.prompt_id.unique())
    lookup = {example: task_rows[task_rows.prompt_id == example] for example in examples}
    rng = np.random.default_rng(seed)
    boot_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for _ in range(resamples):
        selected = rng.choice(examples, size=len(examples), replace=True)
        sample = pd.concat([lookup[example] for example in selected], ignore_index=True)
        for metric in METRICS:
            column = metric_column(metric)
            score = sample[column].to_numpy(dtype=float)
            answer = sample.answer_disagreement.astype(int).to_numpy()
            correctness = sample.correctness_disagreement.astype(int).to_numpy()
            values = {
                "answer_disagreement_auc": _safe_auc(answer, score),
                "correctness_disagreement_auc": _safe_auc(correctness, score),
                "mean_answer_agree": float(score[answer == 0].mean()) if np.any(answer == 0) else np.nan,
                "mean_answer_disagree": float(score[answer == 1].mean()) if np.any(answer == 1) else np.nan,
                "spearman_frozen_token_edit": _safe_spearman(score, sample.frozen_token_edit_distance.to_numpy(dtype=float)),
                "point_biserial_answer_disagreement": _safe_pointbiserial(answer, score),
            }
            for statistic, value in values.items():
                boot_values[(metric, statistic)].append(value)
    point["ci_low"] = [float(np.nanpercentile(boot_values[(row.metric, row.statistic)], 2.5)) for row in point.itertuples(index=False)]
    point["ci_high"] = [float(np.nanpercentile(boot_values[(row.metric, row.statistic)], 97.5)) for row in point.itertuples(index=False)]
    point["metric_minus_hamming"] = np.nan
    point["metric_minus_hamming_ci_low"] = np.nan
    point["metric_minus_hamming_ci_high"] = np.nan
    for statistic in point.statistic.unique():
        ham_estimate = float(point[(point.metric == "hamming") & (point.statistic == statistic)].estimate.iloc[0])
        ham_boot = np.asarray(boot_values[("hamming", statistic)], dtype=float)
        for metric in METRICS:
            mask = (point.metric == metric) & (point.statistic == statistic)
            diff = float(point.loc[mask, "estimate"].iloc[0] - ham_estimate)
            boot_diff = np.asarray(boot_values[(metric, statistic)], dtype=float) - ham_boot
            point.loc[mask, "metric_minus_hamming"] = diff
            point.loc[mask, "metric_minus_hamming_ci_low"] = float(np.nanpercentile(boot_diff, 2.5))
            point.loc[mask, "metric_minus_hamming_ci_high"] = float(np.nanpercentile(boot_diff, 97.5))
    bootstrap = {
        "schema_version": 1,
        "resamples": resamples,
        "seed": seed,
        "top_level_unit": "unique GSM8K example",
        "aggregation": "two decoding seeds averaged for metric; disagreement is any-seed disagreement",
        "interval": "percentile two-sided 95% descriptive",
        "cells": {f"{metric}|{statistic}": {"ci_low": float(np.nanpercentile(values, 2.5)), "ci_high": float(np.nanpercentile(values, 97.5))} for (metric, statistic), values in boot_values.items()},
    }
    return point, bootstrap


def metric_validity_audit(cache: TokenCostCache, observed_tokens: dict[str, set[int]], seed: int = 301004, triple_count: int = 100_000) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    result: dict[str, Any] = {"seed": seed, "deterministic_triples_per_family_metric": triple_count, "families": {}, "pass": True}
    for family, tokens in observed_tokens.items():
        token_array = np.asarray(sorted(tokens), dtype=np.int64)
        if len(token_array) < 3:
            raise ValueError(f"Too few observed tokens for validity audit: {family}")
        family_result: dict[str, Any] = {}
        indices = rng.integers(0, len(token_array), size=(triple_count, 3), endpoint=False)
        triples = token_array[indices]
        for metric in METRICS:
            max_symmetry = 0.0
            max_triangle = 0.0
            min_identity_separation = 1.0
            minimum = 1.0
            maximum = 0.0
            for left, middle, right in triples:
                c_lm = cache.one(metric, family, int(left), int(middle))
                c_ml = cache.one(metric, family, int(middle), int(left))
                c_lr = cache.one(metric, family, int(left), int(right))
                c_mr = cache.one(metric, family, int(middle), int(right))
                max_symmetry = max(max_symmetry, abs(c_lm - c_ml))
                max_triangle = max(max_triangle, c_lr - c_lm - c_mr)
                minimum = min(minimum, c_lm, c_lr, c_mr)
                maximum = max(maximum, c_lm, c_lr, c_mr)
                if left != middle:
                    min_identity_separation = min(min_identity_separation, c_lm)
            passed = max_symmetry <= 1e-12 and max_triangle <= 1e-10 and minimum >= -1e-12 and maximum <= 1 + 1e-12 and min_identity_separation > 0
            family_result[metric] = {
                "max_symmetry_error": max_symmetry,
                "max_triangle_violation": max(0.0, max_triangle),
                "minimum_cost": minimum,
                "maximum_cost": maximum,
                "minimum_distinct_token_cost": min_identity_separation,
                "pass": passed,
            }
            result["pass"] = result["pass"] and passed
        result["families"][family] = family_result
    return result


def categorical_ot_cost(p: np.ndarray, q: np.ndarray, cost: np.ndarray) -> float:
    n, m = cost.shape
    objective = cost.reshape(-1)
    equalities = np.zeros((n + m, n * m), dtype=np.float64)
    for i in range(n):
        equalities[i, i * m:(i + 1) * m] = 1.0
    for j in range(m):
        equalities[n + j, j::m] = 1.0
    rhs = np.concatenate([p, q])
    solution = linprog(objective, A_eq=equalities, b_eq=rhs, bounds=(0.0, None), method="highs")
    if not solution.success:
        raise RuntimeError(f"Categorical OT LP failed: {solution.message}")
    return float(solution.fun)


def _product_distribution(marginals: Sequence[np.ndarray]) -> tuple[list[tuple[int, ...]], np.ndarray]:
    states: list[tuple[int, ...]] = [()]
    probabilities = np.ones(1, dtype=np.float64)
    for marginal in marginals:
        states = [state + (token,) for state in states for token in range(len(marginal))]
        probabilities = np.asarray([prob * float(value) for prob in probabilities for value in marginal], dtype=np.float64)
    return states, probabilities


def theorem_synthetic_tests(seed: int = 301005) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    cases = [
        ("hamming_2coord", 2, 3, "hamming"),
        ("hamming_4coord", 4, 2, "hamming"),
        ("euclidean_3coord", 3, 3, "euclidean"),
        ("byte_3coord", 3, 3, "byte"),
    ]
    for case, coordinates, support, metric in cases:
        p_marginals = [rng.dirichlet(np.ones(support)) for _ in range(coordinates)]
        q_marginals = [rng.dirichlet(np.ones(support)) for _ in range(coordinates)]
        coordinate_costs: list[np.ndarray] = []
        for coordinate in range(coordinates):
            if metric == "hamming":
                cost = 1.0 - np.eye(support)
            elif metric == "euclidean":
                vectors = rng.normal(size=(support, 4))
                vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
                cost = ALPHA * (1.0 - np.eye(support)) + (1.0 - ALPHA) * np.linalg.norm(vectors[:, None] - vectors[None, :], axis=2) / 2.0
            else:
                pieces = [bytes([97 + token]) * (token + 1) for token in range(support)]
                lmax = max(map(len, pieces))
                cost = np.asarray([[ALPHA * (i != j) + (1 - ALPHA) * levenshtein_bytes(pieces[i], pieces[j]) / lmax for j in range(support)] for i in range(support)], dtype=float)
            coordinate_costs.append(cost)
        left_states, left_prob = _product_distribution(p_marginals)
        right_states, right_prob = _product_distribution(q_marginals)
        joint_cost = np.empty((len(left_states), len(right_states)), dtype=np.float64)
        for i, left in enumerate(left_states):
            for j, right in enumerate(right_states):
                joint_cost[i, j] = np.mean([coordinate_costs[k][left[k], right[k]] for k in range(coordinates)])
        full_joint = categorical_ot_cost(left_prob, right_prob, joint_cost)
        coordinate_values = [categorical_ot_cost(p_marginals[k], q_marginals[k], coordinate_costs[k]) for k in range(coordinates)]
        coordinate_sum = float(np.mean(coordinate_values))
        product_cost = coordinate_sum
        error = max(abs(full_joint - coordinate_sum), abs(full_joint - product_cost))
        rows.append({
            "case": case,
            "coordinates": coordinates,
            "support_per_coordinate": support,
            "metric": metric,
            "full_joint_lp": full_joint,
            "sum_coordinate_lp": coordinate_sum,
            "product_optimal_coupling_cost": product_cost,
            "maximum_absolute_error": error,
            "tolerance": 1e-10,
            "pass": error <= 1e-10,
        })
    return pd.DataFrame(rows)


def coordinate_dual(tokens_p: Sequence[int], tokens_q: Sequence[int], family: str, metric: str, cache: TokenCostCache) -> tuple[dict[int, float], float, dict[int, float], dict[int, float]]:
    counter_p = Counter(map(int, tokens_p))
    counter_q = Counter(map(int, tokens_q))
    support = sorted(set(counter_p) | set(counter_q))
    p = np.asarray([counter_p[token] / len(tokens_p) for token in support], dtype=np.float64)
    q = np.asarray([counter_q[token] / len(tokens_q) for token in support], dtype=np.float64)
    delta = p - q
    constraints = []
    rhs = []
    for i, left in enumerate(support):
        for j, right in enumerate(support):
            row = np.zeros(len(support), dtype=np.float64)
            row[i] = 1.0
            row[j] -= 1.0
            constraints.append(row)
            rhs.append(cache.one(metric, family, left, right))
    equality = np.zeros((1, len(support)), dtype=np.float64)
    equality[0, 0] = 1.0
    solution = linprog(-delta, A_ub=np.asarray(constraints), b_ub=np.asarray(rhs), A_eq=equality, b_eq=np.zeros(1), bounds=[(None, None)] * len(support), method="highs")
    if not solution.success:
        raise RuntimeError(f"Kantorovich dual failed: {family}/{metric}: {solution.message}")
    phi = solution.x.astype(np.float64)
    training_value = float(delta @ phi)
    if training_value < -1e-12:
        phi *= -1
        training_value *= -1
    phi -= phi.min()
    potentials = {token: float(value) for token, value in zip(support, phi)}
    empirical_p = {token: float(value) for token, value in zip(support, p)}
    empirical_q = {token: float(value) for token, value in zip(support, q)}
    return potentials, training_value, empirical_p, empirical_q


def train_witnesses(cert3_pairs: pd.DataFrame, cache: TokenCostCache, output_dir: Path, code_paths: Sequence[Path]) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[str, str, int], dict[int, float]]]:
    training = cert3_pairs[(cert3_pairs.panel == "CERT3") & (cert3_pairs.pair_type == "FP_Q") & (cert3_pairs.coupling == "CMC")].copy()
    potential_rows: list[dict[str, Any]] = []
    marginal_rows: list[dict[str, Any]] = []
    witnesses: dict[tuple[str, str, int], dict[int, float]] = {}
    for severity in SEVERITIES:
        cell = training[training.severity == severity]
        if len(cell) != 256:
            raise ValueError(f"Witness training count {severity}: {len(cell)}")
        for metric in METRICS:
            for position in range(16):
                fp_tokens = [int(tokens[position]) for tokens in cell.left_tokens]
                q_tokens = [int(tokens[position]) for tokens in cell.right_tokens]
                potentials, objective, p, q = coordinate_dual(fp_tokens, q_tokens, "MDLM_GPT2", metric, cache)
                witnesses[(severity, metric, position)] = potentials
                for token, value in potentials.items():
                    potential_rows.append({"severity": severity, "metric": metric, "position": position, "token_id": token, "phi": value, "training_coordinate_objective": objective, "support_size": len(potentials)})
                    marginal_rows.append({"severity": severity, "metric": metric, "position": position, "token_id": token, "p_fp": p[token], "q_quantized": q[token], "difference": p[token] - q[token]})
    potentials_frame = pd.DataFrame(potential_rows)
    marginals_frame = pd.DataFrame(marginal_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    potentials_path = output_dir / "coordinate_dual_potentials.parquet"
    marginals_path = output_dir / "witness_training_marginals.parquet"
    potentials_frame.to_parquet(potentials_path, index=False)
    marginals_frame.to_parquet(marginals_path, index=False)
    code_hashes = {str(path): sha256_file(path) for path in code_paths if path.exists()}
    asset_hashes = {
        "coordinate_dual_potentials.parquet": sha256_file(potentials_path),
        "witness_training_marginals.parquet": sha256_file(marginals_path),
        "code_hashes": code_hashes,
        "training_panel": "CERT-3 fixed 64-prompt CMC outputs only",
        "evaluation_outputs_read_for_fit": False,
    }
    write_json(output_dir / "witness_asset_hashes.json", asset_hashes)
    write_json(output_dir.parent / "provenance/WITNESS_FREEZE.json", {
        "schema_version": 1,
        "frozen_at_utc": utc_now(),
        "training_source": "CERT-3 fixed suite CMC",
        "evaluation_source": "WP07C prompt population CMC",
        "metrics": list(METRICS),
        "severities": list(SEVERITIES),
        "asset_hashes": asset_hashes,
        "independence_rule": "No WP07C terminal token was used to fit or orient any witness.",
    })
    return potentials_frame, marginals_frame, witnesses


def mcshane_value(token: int, potentials: dict[int, float], family: str, metric: str, cache: TokenCostCache) -> float:
    if int(token) in potentials:
        return float(potentials[int(token)])
    return float(min(value + cache.one(metric, family, int(token), support_token) for support_token, value in potentials.items()))


def witness_state_value(tokens: Sequence[int], severity: str, metric: str, witnesses: dict[tuple[str, str, int], dict[int, float]], cache: TokenCostCache) -> float:
    if len(tokens) != 16:
        raise ValueError(f"WP07C witness state length must be 16, got {len(tokens)}")
    values = [mcshane_value(int(token), witnesses[(severity, metric, position)], "MDLM_GPT2", metric, cache) for position, token in enumerate(tokens)]
    return float(np.mean(values))


def evaluate_witnesses(
    cert3_pairs: pd.DataFrame,
    wp07c_pairs: pd.DataFrame,
    witnesses: dict[tuple[str, str, int], dict[int, float]],
    cache: TokenCostCache,
    resamples: int = 20_000,
    seed: int = 301003,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    train_hashes = set(cert3_pairs[cert3_pairs.panel == "CERT3"].prompt_hash.dropna().astype(str))
    evaluation_prompts = wp07c_pairs[["prompt_id", "prompt_hash"]].drop_duplicates()
    evaluation_prompts["overlap_with_cert3"] = evaluation_prompts.prompt_hash.astype(str).isin(train_hashes)
    retained_prompt_ids = sorted(evaluation_prompts.loc[~evaluation_prompts.overlap_with_cert3, "prompt_id"].astype(str))
    overlap_count = int(evaluation_prompts.overlap_with_cert3.sum())
    evaluation = wp07c_pairs[wp07c_pairs.prompt_id.astype(str).isin(retained_prompt_ids)].copy()
    m = len(retained_prompt_ids)
    if m < 2:
        raise ValueError("LOWER_BOUND_GATE_INCOMPLETE: fewer than two retained prompts")
    witness_rows: list[dict[str, Any]] = []
    for severity in SEVERITIES:
        cell = evaluation[evaluation.severity == severity]
        for metric in METRICS:
            for row in cell.itertuples(index=False):
                f_fp = witness_state_value(row.left_tokens, severity, metric, witnesses, cache)
                f_q = witness_state_value(row.right_tokens, severity, metric, witnesses, cache)
                witness_rows.append({
                    "prompt_id": row.prompt_id,
                    "prompt_hash": row.prompt_hash,
                    "draw_id": int(row.draw_id),
                    "severity": severity,
                    "metric": metric,
                    "f_fp": f_fp,
                    "f_q": f_q,
                    "Y_draw": f_fp - f_q,
                    "f_range_pass": -1e-10 <= f_fp <= 1 + 1e-10 and -1e-10 <= f_q <= 1 + 1e-10,
                })
    witness_draws = pd.DataFrame(witness_rows)
    prompt_rows = witness_draws.groupby(["prompt_id", "prompt_hash", "severity", "metric"], as_index=False).agg(
        draw_count=("draw_id", "nunique"),
        f_fp=("f_fp", "mean"),
        f_q=("f_q", "mean"),
        Y=("Y_draw", "mean"),
        f_range_pass=("f_range_pass", "all"),
    )
    lower_rows: list[dict[str, Any]] = []
    bootstrap_payload: dict[str, Any] = {"schema_version": 1, "resamples": resamples, "seed": seed, "top_level_unit": "retained WP07C prompt block", "formal": False, "cells": {}}
    rng = np.random.default_rng(seed)
    log_term = math.log(2 * 9 / 0.05)
    for severity in SEVERITIES:
        for metric in METRICS:
            values = prompt_rows[(prompt_rows.severity == severity) & (prompt_rows.metric == metric)].sort_values("prompt_id").Y.to_numpy(dtype=float)
            if len(values) != m:
                raise ValueError(f"Witness cell count {severity}/{metric}: {len(values)} != {m}")
            z = (values + 1.0) / 2.0
            variance = float(np.var(z, ddof=1))
            mean_z = float(z.mean())
            penalty_variance = math.sqrt(2 * variance * log_term / m)
            penalty_range = 7 * log_term / (3 * (m - 1))
            lcb_z = mean_z - penalty_variance - penalty_range
            lcb_y = 2 * lcb_z - 1
            lcb_transport = max(0.0, lcb_y)
            bootstrap_indices = rng.integers(0, m, size=(resamples, m), endpoint=False)
            bootstrap = values[bootstrap_indices].mean(axis=1)
            lower_rows.append({
                "severity": severity,
                "metric": metric,
                "evaluation_prompt_count": m,
                "witness_estimate": float(values.mean()),
                "sample_variance_Z": variance,
                "empirical_bernstein_penalty_variance": penalty_variance,
                "empirical_bernstein_penalty_range": penalty_range,
                "empirical_bernstein_LCB_Y": lcb_y,
                "formal_transport_LCB": lcb_transport,
                "bootstrap_ci_low": float(np.percentile(bootstrap, 2.5)),
                "bootstrap_ci_high": float(np.percentile(bootstrap, 97.5)),
                "formal_LCB_positive": lcb_transport > 0,
                "family_size": 9,
                "family_error": 0.05,
                "Y_range": "[-1,1]",
            })
            bootstrap_payload["cells"][f"{severity}|{metric}"] = {"estimate": float(values.mean()), "ci_low": float(np.percentile(bootstrap, 2.5)), "ci_high": float(np.percentile(bootstrap, 97.5))}
    lower_bounds = pd.DataFrame(lower_rows)

    plugin_rows: list[dict[str, Any]] = []
    for severity in SEVERITIES:
        cell = evaluation[evaluation.severity == severity]
        for metric in METRICS:
            coordinate_values = []
            for position in range(16):
                fp_tokens = [int(tokens[position]) for tokens in cell.left_tokens]
                q_tokens = [int(tokens[position]) for tokens in cell.right_tokens]
                _, value, _, _ = coordinate_dual(fp_tokens, q_tokens, "MDLM_GPT2", metric, cache)
                coordinate_values.append(value)
            plugin_rows.append({"severity": severity, "metric": metric, "evaluation_prompt_count": m, "evaluation_draw_count": len(cell), "descriptive_plugin_coordinate_ot": float(np.mean(coordinate_values)), "label": "DESCRIPTIVE_PLUGIN_ONLY"})
    plugin = pd.DataFrame(plugin_rows)

    lip_rows: list[dict[str, Any]] = []
    maximum_violation = 0.0
    maximum_width = 0.0
    for severity in SEVERITIES:
        train_cell = cert3_pairs[(cert3_pairs.panel == "CERT3") & (cert3_pairs.pair_type == "FP_Q") & (cert3_pairs.coupling == "CMC") & (cert3_pairs.severity == severity)]
        eval_cell = evaluation[evaluation.severity == severity]
        for metric in METRICS:
            for position in range(16):
                potentials = witnesses[(severity, metric, position)]
                observed = sorted(set(int(tokens[position]) for tokens in list(train_cell.left_tokens) + list(train_cell.right_tokens) + list(eval_cell.left_tokens) + list(eval_cell.right_tokens)))
                values = {token: mcshane_value(token, potentials, "MDLM_GPT2", metric, cache) for token in observed}
                width = max(values.values()) - min(values.values())
                max_violation = 0.0
                for left in observed:
                    for right in observed:
                        max_violation = max(max_violation, values[left] - values[right] - cache.one(metric, "MDLM_GPT2", left, right))
                maximum_violation = max(maximum_violation, max_violation)
                maximum_width = max(maximum_width, width)
                lip_rows.append({"severity": severity, "metric": metric, "position": position, "observed_token_count": len(observed), "range_min": min(values.values()), "range_max": max(values.values()), "range_width": width, "max_lipschitz_violation": max(0.0, max_violation), "range_pass": width <= 1 + 1e-10 and min(values.values()) >= -1e-10 and max(values.values()) <= 1 + 1e-10, "lipschitz_pass": max_violation <= 1e-10})
    lip_audit = pd.DataFrame(lip_rows)
    independence = {
        "cert3_training_unique_prompt_hashes": len(train_hashes),
        "wp07c_evaluation_unique_prompt_hashes": len(evaluation_prompts),
        "overlap_count": overlap_count,
        "excluded_prompt_blocks": sorted(evaluation_prompts.loc[evaluation_prompts.overlap_with_cert3, "prompt_id"].astype(str).tolist()),
        "retained_evaluation_prompt_count": m,
        "replacement_prompts_added": 0,
        "pass": overlap_count == 0 or m == len(evaluation_prompts) - overlap_count,
    }
    witness_audit = {
        "maximum_lipschitz_violation": maximum_violation,
        "maximum_range_width": maximum_width,
        "all_coordinate_lipschitz_pass": bool(lip_audit.lipschitz_pass.all()),
        "all_coordinate_range_pass": bool(lip_audit.range_pass.all()),
        "all_state_f_range_pass": bool(prompt_rows.f_range_pass.all()),
        "pass": bool(lip_audit.lipschitz_pass.all() and lip_audit.range_pass.all() and prompt_rows.f_range_pass.all()),
    }
    return prompt_rows, lower_bounds, bootstrap_payload, plugin, lip_audit, evaluation_prompts, {"independence": independence, "witness": witness_audit}


def localization_table(wp07c_pairs: pd.DataFrame, lower_bounds: pd.DataFrame, retained_prompts: Sequence[str]) -> pd.DataFrame:
    evaluation = wp07c_pairs[wp07c_pairs.prompt_id.astype(str).isin(set(retained_prompts))]
    m = len(set(retained_prompts))
    rho = math.sqrt(math.log(9 / 0.05) / (2 * m))
    rows: list[dict[str, Any]] = []
    for severity in SEVERITIES:
        cell = evaluation[evaluation.severity == severity]
        for metric in METRICS:
            column = metric_column(metric)
            prompt_cost = cell.groupby("prompt_id")[column].mean()
            direct_mean = float(prompt_cost.mean())
            ucb = min(1.0, direct_mean + rho)
            lower = lower_bounds[(lower_bounds.severity == severity) & (lower_bounds.metric == metric)].iloc[0]
            lcb = float(lower.formal_transport_LCB)
            rows.append({
                "severity": severity,
                "metric": metric,
                "evaluation_prompt_count": m,
                "witness_estimate": float(lower.witness_estimate),
                "empirical_bernstein_LCB": lcb,
                "bootstrap_ci_low": float(lower.bootstrap_ci_low),
                "bootstrap_ci_high": float(lower.bootstrap_ci_high),
                "direct_CMC_mean": direct_mean,
                "direct_Hoeffding_radius": rho,
                "direct_CMC_UCB": ucb,
                "interval_width": ucb - lcb,
                "localization_fraction": lcb / ucb if ucb > 0 else np.nan,
                "LCB_positive": lcb > 0,
                "ordered_pass": lcb <= ucb + 1e-12,
                "estimand_note": "LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.",
            })
    return pd.DataFrame(rows)


def determine_gates(saturation: pd.DataFrame, ordering: pd.DataFrame, relevance: pd.DataFrame, localization: pd.DataFrame, validity_pass: bool) -> dict[str, Any]:
    ham = saturation[(saturation.metric == "hamming") & (saturation.coupling == "inverse_CDF_CRN") & (saturation.severity == "W8")].iloc[0]
    emb = saturation[(saturation.metric == "embedding_hybrid") & (saturation.coupling == "inverse_CDF_CRN") & (saturation.severity == "W8")].iloc[0]
    condition1 = float(emb.saturation_ratio) <= float(ham.saturation_ratio) - 0.10
    condition2 = bool(ordering[(ordering.panel == "CERT3") & (ordering.coupling == "CMC") & (ordering.metric == "embedding_hybrid")].aggregate_ordering_pass.iloc[0])
    alternatives = ordering[(ordering.metric == "embedding_hybrid") & (ordering.panel.isin(["WP07C", "WP07D_GSM8K", "LOCAL_LIFT_TEMP"]))]
    condition3 = bool(alternatives.aggregate_ordering_pass.any())
    emb_auc = float(relevance[(relevance.metric == "embedding_hybrid") & (relevance.statistic == "answer_disagreement_auc")].estimate.iloc[0])
    ham_auc = float(relevance[(relevance.metric == "hamming") & (relevance.statistic == "answer_disagreement_auc")].estimate.iloc[0])
    emb_spear = float(relevance[(relevance.metric == "embedding_hybrid") & (relevance.statistic == "spearman_frozen_token_edit")].estimate.iloc[0])
    ham_spear = float(relevance[(relevance.metric == "hamming") & (relevance.statistic == "spearman_frozen_token_edit")].estimate.iloc[0])
    condition4 = emb_auc >= ham_auc - 0.02 and (emb_auc >= ham_auc + 0.03 or emb_spear >= ham_spear + 0.05)
    if condition1 and condition2 and condition3 and condition4:
        metric_gate = "PRIMARY_METRIC_PROMISING"
    elif condition1 and condition2 and condition3:
        metric_gate = "METRIC_DESATURATION_ONLY"
    else:
        metric_gate = "METRIC_NOT_PROMISING"
    positive_w8 = bool(((localization.severity == "W8") & localization.LCB_positive).any())
    fraction_cells = int((localization.localization_fraction >= 0.10).sum())
    any_positive = bool(localization.LCB_positive.any())
    if positive_w8 and fraction_cells >= 2:
        lower_gate = "TRANSPORT_LOCALIZATION_NONTRIVIAL"
    elif any_positive:
        lower_gate = "LOWER_BOUND_POSITIVE_BUT_WIDE"
    else:
        lower_gate = "LOWER_BOUND_VACUOUS"
    if not validity_pass:
        overall = "FAIL_METRIC_LOC_1_VALIDITY"
    elif metric_gate == "PRIMARY_METRIC_PROMISING" and lower_gate == "TRANSPORT_LOCALIZATION_NONTRIVIAL":
        overall = "PASS_METRIC_LOC_1_STRONG"
    elif metric_gate in ("PRIMARY_METRIC_PROMISING", "METRIC_DESATURATION_ONLY") or lower_gate != "LOWER_BOUND_VACUOUS":
        overall = "PASS_METRIC_LOC_1_PARTIAL"
    else:
        overall = "PASS_METRIC_LOC_1_NEGATIVE"
    if overall == "PASS_METRIC_LOC_1_STRONG":
        readiness = "AUTHORIZED_SEPARATE_TRANSPORT_RISK_WEIGHTED_CALIBRATION_WP"
    elif overall == "PASS_METRIC_LOC_1_PARTIAL":
        if lower_gate != "LOWER_BOUND_VACUOUS" and metric_gate == "METRIC_NOT_PROMISING":
            readiness = "LOCALIZATION_ONLY_NEXT_STEP; NO_SEMANTIC_CALIBRATION_CLAIM"
        elif metric_gate != "METRIC_NOT_PROMISING" and lower_gate == "LOWER_BOUND_VACUOUS":
            readiness = "METRIC_ONLY_FOLLOWUP; CALIBRATION_NOT_AUTHORIZED"
        else:
            readiness = "LIMITED_COMPONENT_FOLLOWUP_ONLY"
    else:
        readiness = "NOT_READY"
    return {
        "metric_gate": metric_gate,
        "metric_gate_conditions": {
            "embedding_W8_CRN_saturation_improves_by_0_10": condition1,
            "CERT3_CMC_bit_ordering": condition2,
            "external_panel_bit_ordering": condition3,
            "GSM8K_relevance": condition4,
            "hamming_W8_CRN_saturation": float(ham.saturation_ratio),
            "embedding_W8_CRN_saturation": float(emb.saturation_ratio),
            "hamming_answer_auc": ham_auc,
            "embedding_answer_auc": emb_auc,
            "hamming_edit_spearman": ham_spear,
            "embedding_edit_spearman": emb_spear,
        },
        "lower_bound_gate": lower_gate,
        "lower_bound_gate_conditions": {"positive_W8_metric": positive_w8, "cells_localization_fraction_ge_0_10": fraction_cells, "any_positive_LCB": any_positive},
        "overall_gate": overall,
        "plan_a_calibration_readiness": readiness,
        "validity_pass": validity_pass,
    }


def _save_figure(fig: plt.Figure, figures: Path, stem: str, data: pd.DataFrame) -> None:
    figures.mkdir(parents=True, exist_ok=True)
    data_path = figures / f"{stem}_data.csv"
    data.to_csv(data_path, index=False)
    fig.savefig(figures / f"{stem}.png", dpi=220, bbox_inches="tight")
    fig.savefig(figures / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    (figures / f"{stem}_data.sha256").write_text(f"{sha256_file(data_path)}  {data_path.name}\n", encoding="utf-8")


def make_figures(figures: Path, saturation: pd.DataFrame, ordering: pd.DataFrame, relevance: pd.DataFrame, localization: pd.DataFrame) -> None:
    distance = saturation.copy()
    plot = distance[(distance.coupling == "CMC")].copy()
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(METRICS))
    width = 0.19
    for offset, label in enumerate(("FP_REFERENCE", "W8", "W6", "W4")):
        values = []
        for metric in METRICS:
            sub = plot[plot.metric == metric]
            values.append(float(sub.mean_fp_fp_independent.iloc[0]) if label == "FP_REFERENCE" else float(sub[sub.severity == label].mean_fp_q.iloc[0]))
        ax.bar(x + (offset - 1.5) * width, values, width, label=label)
    ax.set_xticks(x, [METRIC_LABELS[m] for m in METRICS], rotation=12, ha="right")
    ax.set_ylabel("Mean terminal distance")
    ax.set_title("CERT-3 independent-FP and CMC FP/Q distances")
    ax.legend()
    _save_figure(fig, figures, "metric_distance_comparison", distance,)

    fig, ax = plt.subplots(figsize=(9, 5))
    sat_plot = saturation[saturation.severity == "W8"].copy()
    for coupling, group in sat_plot.groupby("coupling"):
        group = group.set_index("metric").reindex(METRICS)
        ax.plot([METRIC_LABELS[m] for m in METRICS], group.saturation_ratio, marker="o", label=coupling)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("W8 saturation ratio")
    ax.set_title("W8 FP/Q distance relative to independent FP diversity")
    ax.tick_params(axis="x", rotation=12)
    ax.legend()
    _save_figure(fig, figures, "metric_saturation_comparison", saturation)

    fig, ax = plt.subplots(figsize=(10, 5))
    order_plot = ordering[(ordering.panel.isin(["CERT3", "WP07C", "WP07D_GSM8K"])) & (ordering.coupling.isin(["CMC", "BF16_vs_quantized"]))].copy()
    labels = order_plot.panel + "/" + order_plot.metric
    ax.bar(np.arange(len(order_plot)), order_plot.prompt_or_example_ordering_rate)
    ax.set_xticks(np.arange(len(order_plot)), labels, rotation=75, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Cluster-level W8≤W6≤W4 rate")
    ax.set_title("Bit ordering across frozen panels")
    _save_figure(fig, figures, "metric_bit_ordering", ordering)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    auc = relevance[relevance.statistic == "answer_disagreement_auc"].set_index("metric").reindex(METRICS)
    spear = relevance[relevance.statistic == "spearman_frozen_token_edit"].set_index("metric").reindex(METRICS)
    axes[0].bar([METRIC_LABELS[m] for m in METRICS], auc.estimate)
    axes[0].set_ylim(0, 1)
    axes[0].set_title("Answer-disagreement ROC AUC")
    axes[1].bar([METRIC_LABELS[m] for m in METRICS], spear.estimate)
    axes[1].set_ylim(-1, 1)
    axes[1].set_title("Spearman with frozen token edit")
    for ax in axes:
        ax.tick_params(axis="x", rotation=20)
    _save_figure(fig, figures, "metric_task_relevance", relevance)

    fig, ax = plt.subplots(figsize=(10, 6))
    loc = localization.copy()
    labels = [f"{row.severity}/{row.metric}" for row in loc.itertuples(index=False)]
    x = np.arange(len(loc))
    ax.vlines(x, loc.empirical_bernstein_LCB, loc.direct_CMC_UCB, color="steelblue", linewidth=4)
    ax.scatter(x, loc.empirical_bernstein_LCB, color="darkgreen", label="Witness simultaneous LCB")
    ax.scatter(x, loc.direct_CMC_UCB, color="darkred", label="Direct CMC simultaneous UCB")
    ax.set_xticks(x, labels, rotation=65, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Transport cost")
    ax.set_title("Prompt-mixture lower / average-conditional upper localization")
    ax.legend()
    _save_figure(fig, figures, "transport_localization_intervals", localization)


THEORY_FILES = {
    "GENERAL_ADDITIVE_COST_THEOREM.tex": r"""\section*{General additive token-cost product theorem}
Let $\mathcal X=\prod_{i=1}^N\mathcal X_i$, let $c_i$ be metrics with
$\operatorname{diam}(c_i)\leq1$, and let $d_c(x,y)=\sum_i\lambda_i c_i(x_i,y_i)$
for positive $\lambda_i$ summing to one.  If $P=\bigotimes_i p_i$ and
$Q=\bigotimes_i q_i$ on finite supports, then
\[
W_{d_c}(P,Q)=\sum_i\lambda_i W_{c_i}(p_i,q_i).
\]
A product of coordinatewise $c_i$-optimal couplings attains the minimum.
""",
    "FIRST_DIVERGENCE_GENERAL_COST_COROLLARY.tex": r"""\section*{First-divergence corollary for additive token metrics}
For a monotone MASK-to-token, copy-only chain and any valid path coupling
$\Gamma$, let $\tau^{(r)}$ be the first split before endpoint $r$. Then
\[
D_\Gamma^{(c)}(r)\leq \mathbb E_\Gamma\!\left[R_c(X_{\tau}^{(r)})
\mathbf 1\{\tau^{(r)}\neq\dagger\}\right],\qquad
R_c(s)=\sum_{i:s_i=\mathrm{MASK}}\lambda_i\operatorname{diam}(c_i)
\leq\sum_{i:s_i=\mathrm{MASK}}\lambda_i.
\]
""",
}


def write_theory_memos(theory_dir: Path) -> None:
    theory_dir.mkdir(parents=True, exist_ok=True)
    for name, content in THEORY_FILES.items():
        (theory_dir / name).write_text(content, encoding="utf-8")
    (theory_dir / "GENERAL_ADDITIVE_COST_PROOF.md").write_text(r"""# General additive token-cost product theorem — proof

For any coupling $\pi$ of $P$ and $Q$, its coordinate projection $\pi_i$ couples $p_i$ and $q_i$. Therefore

`E_pi[d_c(X,Y)] = sum_i lambda_i E_pi_i[c_i(X_i,Y_i)] >= sum_i lambda_i W_{c_i}(p_i,q_i)`.

Conversely, finite support guarantees an optimal coordinate coupling $\pi_i^*$ for every $i$. The product $\otimes_i\pi_i^*$ has marginals $P$ and $Q$, and its expected additive cost is exactly the sum of coordinate optima. The lower and upper inequalities coincide.

The first-divergence corollary follows because coordinates already equal and committed before the first split are copied forever. Only coordinates MASKed in the common pre-split state can contribute, and each contributes at most its metric diameter.
""", encoding="utf-8")
    (theory_dir / "THEORY_SCOPE_AND_LIMITS.md").write_text("""# Theory scope and limits

- Coordinatewise maximal coupling is coordinate-optimal for 0–1 disagreement cost, not for a general token metric.
- A general coordinate cost requires a coordinatewise cost-optimal categorical transport coupling to attain the product theorem's upper construction.
- Proposal-level coordinate optimality does not imply output- or path-level optimality.
- The embedding and tokenizer-byte costs are frozen audit metrics, not semantic equivalence or language-quality metrics.
- The held-out witness bounds the Wasserstein distance between prompt-mixture terminal laws. It is not a prompt-conditional lower bound.
- The direct CMC UCB bounds an average prompt-conditional transport cost; mixture transport is no larger than that average.
""", encoding="utf-8")


def write_contracts(payload: Path, project_root: Path, run_id: str) -> None:
    config = payload / "config"
    config.mkdir(parents=True, exist_ok=True)
    source_config = project_root / "experiments/metric_localization/configs/preregistration_metric_loc_1.json"
    shutil.copy2(source_config, config / "preregistration_metric_loc_1.json")
    write_json(config / "metric_contract.json", {
        "alpha": ALPHA,
        "position_weights": "uniform 1/N",
        "metrics": {
            "hamming": "1{v!=w}",
            "embedding_hybrid": "0.05*1{v!=w}+0.95*||normalized_input_embedding(v)-normalized_input_embedding(w)||_2/2",
            "tokenizer_byte_hybrid": "0.05*1{v!=w}+0.95*byte_Levenshtein(piece(v),piece(w))/vocabulary_Lmax",
        },
        "mask_versus_vocabulary_cost": 1.0,
        "metric_selection_tuned_after_outcomes": False,
    })
    write_json(config / "statistical_contract.json", {
        "metric_bootstrap": {"resamples": 20_000, "seed": 301001, "top_level_unit": "prompt"},
        "task_bootstrap": {"resamples": 20_000, "seed": 301002, "top_level_unit": "GSM8K example"},
        "lower_bound_bootstrap": {"resamples": 20_000, "seed": 301003, "formal": False},
        "lower_bound": {"family_size": 9, "delta": 0.05, "formula": "one-sided empirical Bernstein on Z=(Y+1)/2"},
        "upper_bound": {"family_size": 9, "delta": 0.05, "formula": "one-sided Hoeffding on per-prompt mean direct CMC cost"},
    })
    write_json(config / "witness_contract.json", {
        "training": "CERT-3 fixed 64-prompt CMC terminal outputs",
        "evaluation": "WP07C 128 IID prompt-draw CMC terminal outputs",
        "fit_uses_evaluation_outputs": False,
        "orientation": "nonnegative training empirical difference",
        "shift": "coordinate minimum set to zero",
        "unseen_extension": "McShane min_v(phi(v)+c(x,v))",
    })
    write_json(config / "gate_contract.json", {"source": "METRIC_LOC_1_CODEX_PROMPT", "metric_primary": "embedding_hybrid", "run_id": run_id})


def write_reports(payload: Path, gates: dict[str, Any], saturation: pd.DataFrame, ordering: pd.DataFrame, relevance: pd.DataFrame, localization: pd.DataFrame, raw_audit: dict[str, Any], asset_ledger: dict[str, Any]) -> None:
    reports = payload / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    def plain_table(frame: pd.DataFrame) -> str:
        return "```text\n" + frame.to_string(index=False) + "\n```"

    sat_table = plain_table(saturation)
    order_table = plain_table(ordering)
    relevance_table = plain_table(relevance)
    localization_table_md = plain_table(localization)
    (reports / "FINAL_REPORT.md").write_text(f"""# METRIC-LOC-1 final report

## Scope

This was a CPU-only, model-free reanalysis of frozen CERT-3, WP07C, WP07D, and LOCAL-LIFT outputs. No model forward, generation, trajectory, Monte Carlo experiment, GPU allocation, calibration, or paper edit was performed.

## Validity

- Raw terminal reconstruction: `{raw_audit['pass']}`
- Hamming maximum frozen-value discrepancy: `{raw_audit['hamming_reproduction_max_discrepancy']:.17g}`
- Metric/theorem/witness/statistical validity: `{gates['validity_pass']}`

## Metric saturation

{sat_table}

## Bit ordering

{order_table}

## GSM8K descriptive task relevance

{relevance_table}

These values are descriptive relevance diagnostics, not semantic or task-quality certificates.

## Terminal transport localization

{localization_table_md}

The witness LCB concerns prompt-mixture terminal laws. The direct CMC UCB concerns the average prompt-conditional cost. The ordering is `LCB_witness <= W(prompt mixture) <= average prompt-conditional W <= UCB_direct_CMC`.

## Gates

- Metric: `{gates['metric_gate']}`
- Lower bound: `{gates['lower_bound_gate']}`
- Overall: `{gates['overall_gate']}`
- Plan-A readiness: `{gates['plan_a_calibration_readiness']}`

## Limits

Embedding distance is not semantic equivalence, the plug-in coordinate OT is not a certified population lower bound, CMC is not joint maximal, and no arbitrary-prompt or large-model claim follows.
""", encoding="utf-8")
    (reports / "QUICK_REVIEW.md").write_text(f"""# METRIC-LOC-1 quick review

- Metric gate: `{gates['metric_gate']}`
- Lower-bound gate: `{gates['lower_bound_gate']}`
- Overall gate: `{gates['overall_gate']}`
- Plan-A readiness: `{gates['plan_a_calibration_readiness']}`
- Model execution: no
- GPU execution: no
- Paper modified: no
""", encoding="utf-8")
    (reports / "NEGATIVE_RESULTS.md").write_text("""# Negative and limiting results

- Any formal lower-bound cell clipped to zero is reported as vacuous, not hidden.
- Metric de-saturation and GSM8K relevance are separate criteria; one does not establish the other.
- Prompt/example-level bit ordering may fail even when aggregate ordering holds.
- The tokenizer-byte metric is secondary and cannot replace the preregistered embedding gate.
- A wide localization interval is not evidence that the witness identifies the exact terminal Wasserstein distance.
""", encoding="utf-8")
    (reports / "PAPER_ROLE_DECISION.md").write_text(f"""# Paper role decision

Overall gate: `{gates['overall_gate']}`.

No paper was edited. The result may be considered only under the preregistered routing rule. Strong status permits a later, separate work package; partial status authorizes only the component named in the readiness decision; negative status retains exact Hamming as the theorem-aligned audit metric.
""", encoding="utf-8")
    (reports / "PLAN_A_CALIBRATION_READINESS.md").write_text(f"""# Plan-A calibration readiness

Decision: `{gates['plan_a_calibration_readiness']}`.

Metric-only success does not authorize a calibration claim. Lower-bound-only success does not establish semantic relevance. No calibration was started here.
""", encoding="utf-8")
    (reports / "ALLOWED_AND_PROHIBITED_METRIC_CLAIMS.md").write_text("""# Allowed and prohibited metric claims

## Allowed

- Frozen additive metrics can be compared descriptively on these archived panels.
- A positive formal witness LCB lower-bounds prompt-mixture terminal Wasserstein distance for the frozen metric.
- The direct CMC UCB upper-bounds the average prompt-conditional transport cost under the stated sampling contract.
- Embedding rows are frozen reference-model input embeddings.

## Prohibited

- Semantic equivalence or language-quality certification.
- Exact terminal Wasserstein identification or witness tightness without interval evidence.
- Universal metric superiority or coupling-independent task certification.
- Conflating prompt-mixture Wasserstein distance with average prompt-conditional Wasserstein distance.
- Treating descriptive plug-in OT as a certified population lower bound.
- Arbitrary-prompt, large-model, LLaDA, Dream, or deployment-kernel generalization.
- Claiming a successful calibration algorithm.
""", encoding="utf-8")
    (reports / "THEORY_GENERALIZATION_MEMO.md").write_text("""# Theory generalization memo

The additive product identity holds for bounded coordinate metrics by projection of any joint coupling and construction of the product of coordinate-optimal couplings. The 0–1 coordinatewise maximal coupling is not generally cost-optimal for embedding- or byte-derived costs. The first-divergence residual theorem extends by replacing residual mask count with residual coordinate metric diameter mass.
""", encoding="utf-8")
    (payload / "lower_bound/transport_localization_notes.md").write_text("""# Transport localization estimands

`LCB_witness` is a simultaneous lower confidence bound for the Wasserstein distance between WP07C prompt-mixture terminal laws. `UCB_direct_CMC` is a simultaneous upper confidence bound on the average across retained prompts of direct CMC costs, hence on the average prompt-conditional Wasserstein distance. Convexity gives prompt-mixture W no larger than the average conditional W. These are ordered but not identical estimands.
""", encoding="utf-8")


def recursive_manifest(payload: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(payload.rglob("*")):
        if not path.is_file() or path.name in ("FILE_MANIFEST.json", "SHA256SUMS.txt"):
            continue
        relative = path.relative_to(payload).as_posix()
        classification = relative.split("/", 1)[0]
        rows.append({"relative_path": relative, "byte_size": path.stat().st_size, "sha256": sha256_file(path), "classification": classification})
    return pd.DataFrame(rows)


def write_payload_manifest(payload: Path) -> None:
    manifest = recursive_manifest(payload)
    write_json(payload / "FILE_MANIFEST.json", {"schema_version": 1, "file_count": len(manifest), "files": manifest.to_dict("records")})
    lines = [f"{row.sha256}  {row.relative_path}" for row in manifest.itertuples(index=False)]
    (payload / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
