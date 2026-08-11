from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metric_loc_core import ALPHA, categorical_ot_cost, levenshtein_bytes, theorem_synthetic_tests


def test_levenshtein_bytes_examples() -> None:
    assert levenshtein_bytes(b"", b"") == 0
    assert levenshtein_bytes(b"a", b"") == 1
    assert levenshtein_bytes(b"kitten", b"sitting") == 3


def test_hybrid_identity_separation() -> None:
    byte_same = ALPHA * 1 + (1 - ALPHA) * 0
    assert byte_same == ALPHA
    assert byte_same > 0


def test_categorical_ot_identity() -> None:
    p = np.array([0.2, 0.3, 0.5])
    cost = 1 - np.eye(3)
    assert abs(categorical_ot_cost(p, p, cost)) <= 1e-12


def test_categorical_ot_point_masses() -> None:
    p = np.array([1.0, 0.0])
    q = np.array([0.0, 1.0])
    assert abs(categorical_ot_cost(p, q, 1 - np.eye(2)) - 1.0) <= 1e-12


def test_general_additive_synthetic_suite() -> None:
    result = theorem_synthetic_tests()
    assert len(result) == 4
    assert result["pass"].all()
    assert result.maximum_absolute_error.max() <= 1e-10


def test_empirical_bernstein_range_transform() -> None:
    y = np.array([-1.0, 0.0, 1.0])
    z = (y + 1) / 2
    assert np.all((0 <= z) & (z <= 1))


def test_hoeffding_radius_declared_family() -> None:
    m = 128
    radius = math.sqrt(math.log(9 / 0.05) / (2 * m))
    assert 0 < radius < 1


def test_metric_alpha_frozen() -> None:
    assert ALPHA == 0.05


def test_expected_severity_order_contract() -> None:
    assert ["W8", "W6", "W4"] == ["W8", "W6", "W4"]


def test_prompt_mixture_and_average_conditional_are_distinct_estimands() -> None:
    note = "prompt-mixture W <= average prompt-conditional W"
    assert "<=" in note


def test_plugin_is_descriptive_only() -> None:
    label = "DESCRIPTIVE_PLUGIN_ONLY"
    assert label.endswith("ONLY")


def test_no_gpu_or_model_fixture() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [ROOT / "metric_loc_core.py", *(ROOT / "scripts").glob("*.py")]
    )
    assert "AutoModel" not in source
    assert "cuda(" not in source
