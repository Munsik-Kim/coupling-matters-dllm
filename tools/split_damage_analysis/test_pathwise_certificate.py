import unittest


def residual_bound(pre_split, left_endpoint, right_endpoint, mask=-1):
    residual = sum(value == mask for value in pre_split)
    distance = sum(a != b for a, b in zip(left_endpoint, right_endpoint))
    return distance / len(pre_split), residual / len(pre_split)


class TestPathwiseCertificate(unittest.TestCase):
    def test_copy_only_residual_bound(self):
        d, bound = residual_bound([3, -1, -1, 8], [3, 2, 4, 8], [3, 9, 4, 8])
        self.assertLessEqual(d, bound)

    def test_no_split(self):
        d, _ = residual_bound([-1, -1], [2, 5], [2, 5])
        self.assertEqual(d, 0.0)

    def test_committed_equal_prefix_cannot_change(self):
        pre = [7, -1, -1]
        left = [7, 2, 3]
        right = [7, 4, 3]
        self.assertEqual(left[0], right[0])
        d, bound = residual_bound(pre, left, right)
        self.assertLessEqual(d, bound)


if __name__ == "__main__":
    unittest.main()
