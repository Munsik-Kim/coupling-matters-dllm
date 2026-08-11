import unittest

import numpy as np

from cmc_coupling import categorical_tv, empirical_maximal_coupling, maximal_couple


class TestCMCCategorical(unittest.TestCase):
    def test_diagonal_preservation(self):
        p = np.array([0.1, 0.2, 0.7], dtype=np.float64)
        for seed in range(32):
            left, right, row = maximal_couple(p, p, event_prefix=("diag", seed))
            self.assertEqual(left, right)
            self.assertEqual(row["delta"], 0.0)

    def test_empirical_marginals_and_tv(self):
        p = np.array([0.55, 0.30, 0.15], dtype=np.float64)
        q = np.array([0.10, 0.45, 0.45], dtype=np.float64)
        row = empirical_maximal_coupling(p, q, draws=100_000, seed=260910)
        self.assertLess(row["fp_max_abs_error"], 0.006)
        self.assertLess(row["q_max_abs_error"], 0.006)
        self.assertLess(abs(row["mismatch_rate"] - categorical_tv(p, q)), 0.006)
        self.assertTrue(row["residual_samples_all_different"])

    def test_branch_order_invariance(self):
        p = np.array([0.4, 0.1, 0.5], dtype=np.float64)
        q = np.array([0.2, 0.7, 0.1], dtype=np.float64)
        for seed in range(64):
            a = maximal_couple(p, q, event_prefix=("order", seed), branch_order="FP_Q")
            b = maximal_couple(p, q, event_prefix=("order", seed), branch_order="Q_FP")
            self.assertEqual(a[:2], b[:2])


if __name__ == "__main__":
    unittest.main()
