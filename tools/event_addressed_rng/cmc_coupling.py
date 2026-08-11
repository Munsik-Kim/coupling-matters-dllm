"""Coordinatewise maximal coupling primitives for native-D1 CERT-2."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

import numpy as np


def stable_seed(base_seed: int, *address: Any) -> int:
    """Return the workbench-compatible stable 63-bit semantic-event seed."""
    payload = json.dumps(
        [int(base_seed), *[str(value) for value in address]],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "little") & ((1 << 63) - 1)


def normalize_probabilities(
    values: np.ndarray,
    *,
    tolerance: float = 1.0e-12,
    material_negative_tolerance: float = 1.0e-10,
) -> np.ndarray:
    """Validate and normalize one categorical law in stable float64."""
    result = np.asarray(values, dtype=np.float64).copy()
    if result.ndim != 1 or result.size == 0:
        raise ValueError("Categorical probabilities must be a nonempty vector.")
    if not np.isfinite(result).all():
        raise FloatingPointError("Categorical probabilities contain NaN/Inf.")
    minimum = float(result.min())
    if minimum < -float(material_negative_tolerance):
        raise FloatingPointError(f"Material negative probability: {minimum}")
    if minimum < 0.0:
        result[result < 0.0] = 0.0
    total = float(result.sum(dtype=np.float64))
    if not math.isfinite(total) or total <= 0.0:
        raise FloatingPointError("Categorical probability mass is invalid.")
    result /= total
    error = abs(float(result.sum(dtype=np.float64)) - 1.0)
    if error > float(tolerance):
        raise FloatingPointError(f"Probability normalization error: {error}")
    return result


def probability_sha256(values: np.ndarray) -> str:
    normalized = np.asarray(values, dtype="<f8")
    return hashlib.sha256(normalized.tobytes()).hexdigest()


def event_uniform(prefix: Iterable[Any], event_type: str, draw_index: int = 0) -> dict[str, Any]:
    key = tuple(prefix) + (str(event_type), int(draw_index))
    seed = int(stable_seed(0, *key))
    uniform = float(np.random.default_rng(seed).random())
    return {
        "event_key": list(key),
        "stable_seed": seed,
        "uniform": uniform,
        "uniform_sha256": hashlib.sha256(
            np.asarray([uniform], dtype="<f8").tobytes()
        ).hexdigest(),
    }


def sample_categorical(probabilities: np.ndarray, uniform: float) -> int:
    if not 0.0 <= float(uniform) < 1.0:
        raise ValueError("Uniform must lie in [0,1).")
    cumulative = np.cumsum(probabilities, dtype=np.float64)
    cumulative[-1] = 1.0
    return min(
        int(np.searchsorted(cumulative, float(uniform), side="right")),
        len(probabilities) - 1,
    )


def categorical_tv(p: np.ndarray, q: np.ndarray) -> float:
    return float(0.5 * np.abs(p - q).sum(dtype=np.float64))


def maximal_couple(
    p: np.ndarray,
    q: np.ndarray,
    *,
    event_prefix: Iterable[Any],
    tolerance: float = 1.0e-12,
    material_negative_tolerance: float = 1.0e-10,
    branch_order: str = "FP_Q",
) -> tuple[int, int, dict[str, Any]]:
    """Maximally couple two categorical laws using event-addressed draws."""
    if branch_order not in {"FP_Q", "Q_FP"}:
        raise ValueError(branch_order)
    p = normalize_probabilities(
        p,
        tolerance=tolerance,
        material_negative_tolerance=material_negative_tolerance,
    )
    q = normalize_probabilities(
        q,
        tolerance=tolerance,
        material_negative_tolerance=material_negative_tolerance,
    )
    if p.shape != q.shape:
        raise ValueError("Coupled categorical laws need identical support.")
    overlap = np.minimum(p, q)
    alpha = float(overlap.sum(dtype=np.float64))
    alpha = min(max(alpha, 0.0), 1.0)
    delta = categorical_tv(p, q)
    events: dict[str, Any] = {}
    decision = event_uniform(event_prefix, "match_decision")
    events["match_decision"] = decision

    if np.array_equal(p, q) or 1.0 - alpha <= tolerance:
        common = normalize_probabilities(0.5 * (p + q), tolerance=tolerance)
        overlap_event = event_uniform(event_prefix, "overlap_category")
        events["overlap_category"] = overlap_event
        token = sample_categorical(common, overlap_event["uniform"])
        return token, token, {
            "alpha": 1.0,
            "delta": 0.0,
            "matched": True,
            "numerical_equal_path": True,
            "events": events,
        }

    if decision["uniform"] < alpha and alpha > tolerance:
        common = normalize_probabilities(overlap / alpha, tolerance=tolerance)
        overlap_event = event_uniform(event_prefix, "overlap_category")
        events["overlap_category"] = overlap_event
        token = sample_categorical(common, overlap_event["uniform"])
        return token, token, {
            "alpha": alpha,
            "delta": delta,
            "matched": True,
            "numerical_equal_path": False,
            "events": events,
        }

    p_residual = p - overlap
    q_residual = q - overlap
    if float(p_residual.min()) < -material_negative_tolerance:
        raise FloatingPointError("Material negative FP residual mass.")
    if float(q_residual.min()) < -material_negative_tolerance:
        raise FloatingPointError("Material negative Q residual mass.")
    p_residual[p_residual < 0.0] = 0.0
    q_residual[q_residual < 0.0] = 0.0
    if alpha <= tolerance:
        p_conditional = normalize_probabilities(p_residual, tolerance=tolerance)
        q_conditional = normalize_probabilities(q_residual, tolerance=tolerance)
    else:
        denominator = 1.0 - alpha
        p_conditional = normalize_probabilities(
            p_residual / denominator, tolerance=tolerance
        )
        q_conditional = normalize_probabilities(
            q_residual / denominator, tolerance=tolerance
        )
    residual_events = {
        "FP": event_uniform(event_prefix, "FP_residual_category"),
        "Q": event_uniform(event_prefix, "Q_residual_category"),
    }
    events.update(residual_events)
    outputs: dict[str, int] = {}
    order = ("FP", "Q") if branch_order == "FP_Q" else ("Q", "FP")
    for branch in order:
        distribution = p_conditional if branch == "FP" else q_conditional
        outputs[branch] = sample_categorical(
            distribution, residual_events[branch]["uniform"]
        )
    if outputs["FP"] == outputs["Q"]:
        raise RuntimeError("Maximal-coupling residual samples did not differ.")
    return outputs["FP"], outputs["Q"], {
        "alpha": alpha,
        "delta": delta,
        "matched": False,
        "numerical_equal_path": False,
        "residual_supports_disjoint": not bool(
            np.any((p_residual > tolerance) & (q_residual > tolerance))
        ),
        "events": events,
    }


def inverse_cdf_couple(
    p: np.ndarray,
    q: np.ndarray,
    *,
    event_prefix: Iterable[Any],
    tolerance: float = 1.0e-12,
) -> tuple[int, int, dict[str, Any]]:
    p = normalize_probabilities(p, tolerance=tolerance)
    q = normalize_probabilities(q, tolerance=tolerance)
    event = event_uniform(event_prefix, "shared_inverse_cdf")
    fp = sample_categorical(p, event["uniform"])
    quantized = sample_categorical(q, event["uniform"])
    return fp, quantized, {
        "delta": categorical_tv(p, q),
        "matched": fp == quantized,
        "events": {"shared_inverse_cdf": event},
    }


def product_split_hazard(deltas: Iterable[float]) -> float:
    values = np.asarray(list(deltas), dtype=np.float64)
    if values.size == 0:
        return 0.0
    if np.any(values < -1.0e-12) or np.any(values > 1.0 + 1.0e-12):
        raise ValueError("Coordinate TV values are outside [0,1].")
    values = np.clip(values, 0.0, 1.0)
    return float(1.0 - np.prod(1.0 - values, dtype=np.float64))


def empirical_maximal_coupling(
    p: np.ndarray, q: np.ndarray, *, draws: int, seed: int
) -> dict[str, Any]:
    """Vectorized CPU marginal audit of the categorical maximal coupling."""
    p = normalize_probabilities(p)
    q = normalize_probabilities(q)
    overlap = np.minimum(p, q)
    alpha = float(overlap.sum(dtype=np.float64))
    rng = np.random.default_rng(int(seed))
    decision = rng.random(int(draws))
    matched = decision < alpha
    fp_tokens = np.empty(int(draws), dtype=np.int64)
    q_tokens = np.empty(int(draws), dtype=np.int64)
    match_count = int(matched.sum())
    if match_count:
        common = normalize_probabilities(overlap / max(alpha, np.finfo(float).tiny))
        cdf = np.cumsum(common, dtype=np.float64)
        cdf[-1] = 1.0
        tokens = np.searchsorted(cdf, rng.random(match_count), side="right")
        fp_tokens[matched] = tokens
        q_tokens[matched] = tokens
    residual_count = int(draws) - match_count
    if residual_count:
        p_residual = normalize_probabilities(p - overlap)
        q_residual = normalize_probabilities(q - overlap)
        fp_cdf = np.cumsum(p_residual, dtype=np.float64)
        q_cdf = np.cumsum(q_residual, dtype=np.float64)
        fp_cdf[-1] = 1.0
        q_cdf[-1] = 1.0
        fp_tokens[~matched] = np.searchsorted(
            fp_cdf, rng.random(residual_count), side="right"
        )
        q_tokens[~matched] = np.searchsorted(
            q_cdf, rng.random(residual_count), side="right"
        )
    fp_counts = np.bincount(fp_tokens, minlength=len(p)).astype(np.float64)
    q_counts = np.bincount(q_tokens, minlength=len(q)).astype(np.float64)
    fp_empirical = fp_counts / int(draws)
    q_empirical = q_counts / int(draws)
    mismatch_rate = float(np.mean(fp_tokens != q_tokens))
    return {
        "draws": int(draws),
        "alpha": alpha,
        "tv": categorical_tv(p, q),
        "mismatch_rate": mismatch_rate,
        "fp_max_abs_error": float(np.max(np.abs(fp_empirical - p))),
        "q_max_abs_error": float(np.max(np.abs(q_empirical - q))),
        "residual_samples_all_different": bool(
            np.all(fp_tokens[~matched] != q_tokens[~matched])
        ),
        "fp_empirical": fp_empirical,
        "q_empirical": q_empirical,
    }


def wilson_interval(successes: int, total: int, z: float = 2.5758293035489004) -> tuple[float, float]:
    if total <= 0:
        return math.nan, math.nan
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / total
        + z * z / (4.0 * total * total)
    ) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def record_digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
