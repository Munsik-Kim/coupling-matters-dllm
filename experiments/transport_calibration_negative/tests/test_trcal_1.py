from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch

from experiments.transport_calibration.trcal_core import (
    ALPHA_GRID,
    holm_adjust,
    quantize_weight,
    roc_auc,
    schedule,
    token_edit_distance,
)


def test_fixed_count_schedule_commits_exactly_64() -> None:
    rows = schedule()
    assert len(rows) == 64
    assert sum(row[2] for row in rows) == 64


def test_rtn_signed_symmetric_contract() -> None:
    weight = torch.tensor([[-2.0, -0.3, 0.2, 2.0], [0.0, 0.0, 0.0, 0.0]])
    quantized, scale = quantize_weight(weight, 4, 1.0)
    assert scale[0].item() == pytest.approx(2 / 7, abs=1e-7)
    assert scale[1].item() == 0
    assert torch.count_nonzero(quantized[1]) == 0


def test_clipping_alpha_grid_is_frozen() -> None:
    assert np.allclose(ALPHA_GRID, np.arange(0.50, 1.001, 0.05))


def test_float32_serialized_alpha_values_remain_on_preregistered_grid() -> None:
    serialized = np.asarray(ALPHA_GRID, dtype=np.float32).astype(np.float64)
    membership = np.isclose(serialized[:, None], ALPHA_GRID[None, :], rtol=0.0, atol=1e-7)
    assert membership.any(axis=1).all()


def test_per_row_alpha_changes_only_weight_rows() -> None:
    weight = torch.arange(12, dtype=torch.float32).reshape(3, 4) - 5
    alpha = torch.tensor([0.5, 0.75, 1.0])
    quantized, scale = quantize_weight(weight, 3, alpha)
    assert quantized.shape == weight.shape
    assert scale.shape == (3,)


def test_token_edit_distance() -> None:
    assert token_edit_distance([1, 2, 3], [1, 4, 3]) == 1
    assert token_edit_distance([], [1, 2]) == 2


def test_auc_orientation() -> None:
    assert roc_auc(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])) == 1.0


def test_holm_is_monotone_and_bounded() -> None:
    adjusted = holm_adjust([0.01, 0.04])
    assert all(0 <= value <= 1 for value in adjusted)
    assert adjusted[0] <= adjusted[1]


def test_conditional_healing_denominator_is_split_cell() -> None:
    frame = pd.DataFrame({"split": [1, 1, 0, 0], "reagree": [1, 0, 0, 0]})
    assert frame.reagree.sum() / frame.split.sum() == 0.5
    assert frame.reagree.mean() == 0.25
