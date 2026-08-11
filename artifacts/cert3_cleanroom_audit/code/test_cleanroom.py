import math

from audit.wp06_cert3_cleanroom.cleanroom_recalculate import (
    HORIZONS,
    hamming,
    mismatch_type,
)


def test_hamming_generation_only():
    a = list(range(16))
    b = list(range(16))
    b[0] = 99
    assert hamming(a, b) == 1 / 16


def test_mismatch_types():
    base = [50257] * 16
    token = base.copy()
    token[0] = 1
    assert mismatch_type(base, token) == "mask-token"
    token2 = token.copy()
    token2[0] = 2
    assert mismatch_type(token, token2) == "token-token"


def test_hoeffding_radius():
    got = math.sqrt(math.log(49 / .05) / (2 * 256))
    assert 0 < got < .2


def test_horizon_order():
    assert [x[1] for x in HORIZONS] == [4, 8, 12, 16, 24, 32, 33]
