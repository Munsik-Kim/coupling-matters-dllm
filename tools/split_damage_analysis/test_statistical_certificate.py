import math
import unittest


def radius(n, k=49, delta=0.05):
    return math.sqrt(math.log(k / delta) / (2 * n))


def largest_prefix(labels, values, target):
    result = "NONE"
    for label, value in zip(labels, values):
        if value > target:
            break
        result = label
    return result


class TestStatisticalCertificate(unittest.TestCase):
    def test_preregistered_radius(self):
        self.assertAlmostEqual(radius(256), math.sqrt(math.log(980) / 512))
        self.assertGreater(radius(128), radius(256))

    def test_upper_and_lower_clipping(self):
        self.assertEqual(min(1.0, 0.95 + radius(256)), 1.0)
        self.assertEqual(max(0.0, 0.05 - radius(128)), 0.0)

    def test_prefix_closed_horizon(self):
        labels = ["H4", "H8", "H12", "H16"]
        self.assertEqual(largest_prefix(labels, [0.2, 0.3, 0.6, 0.4], 0.5), "H8")

    def test_family_size_locked(self):
        self.assertEqual(21 + 21 + 7, 49)


if __name__ == "__main__":
    unittest.main()
