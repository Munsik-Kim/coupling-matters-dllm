import unittest

import numpy as np

from cmc_coupling import categorical_tv, product_split_hazard


class TestProductCoupling(unittest.TestCase):
    def test_product_hazard_interval(self):
        for deltas in (
            [0.1, 0.2],
            [0.01, 0.03, 0.07],
            [0.2, 0.3, 0.1, 0.05],
            [0.4, 0.1, 0.2, 0.05, 0.01],
            [0.08] * 6,
            [0.0, 0.0, 0.0],
        ):
            hazard = product_split_hazard(deltas)
            self.assertLessEqual(max(deltas), hazard + 1e-12)
            self.assertLessEqual(hazard, min(1.0, sum(deltas)) + 1e-12)

    def test_tv_definition(self):
        p = np.array([0.6, 0.4])
        q = np.array([0.2, 0.8])
        self.assertAlmostEqual(categorical_tv(p, q), 0.4)


if __name__ == "__main__":
    unittest.main()
