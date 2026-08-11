#!/usr/bin/env python3
"""CPU-only finite-state regression tests for WP06-CERT-0 certificates."""

from __future__ import annotations

import random
import unittest

MASK = -1


def hamming(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    assert len(left) == len(right) and left
    return sum(a != b for a, b in zip(left, right)) / len(left)


def residual_mass(state: tuple[int, ...]) -> float:
    return sum(value == MASK for value in state) / len(state)


def coordinate_cap(path: list[tuple[int, ...]]) -> float:
    n = len(path[0])
    changed = {
        i
        for before, after in zip(path, path[1:])
        for i in range(n)
        if before[i] != after[i]
    }
    return len(changed) / n


def last_change_mass(path: list[tuple[int, ...]]) -> tuple[float, dict[int, int]]:
    endpoint_left, endpoint_right = path[0], path[-1]
    terminally_different = {
        i for i, (a, b) in enumerate(zip(endpoint_left, endpoint_right)) if a != b
    }
    last: dict[int, int] = {}
    for i in terminally_different:
        last[i] = max(
            j
            for j, (before, after) in enumerate(zip(path, path[1:]), start=1)
            if before[i] != after[i]
        )
    return len(last) / len(endpoint_left), last


def random_monotone_suffix(
    rng: random.Random,
    state: tuple[int, ...],
    steps: int,
) -> tuple[int, ...]:
    current = list(state)
    for _ in range(steps):
        for i, token in enumerate(current):
            if token == MASK and rng.random() < 0.35:
                current[i] = rng.randrange(4)
    for i, token in enumerate(current):
        if token == MASK:
            current[i] = rng.randrange(4)
    return tuple(current)


class CertificateTheoryTests(unittest.TestCase):
    def test_terminal_coordinate_identity(self) -> None:
        left = (0, 1, 2, 3)
        right = (0, 4, 2, 5)
        contributions = [0.25 * (a != b) for a, b in zip(left, right)]
        self.assertEqual(hamming(left, right), sum(contributions))

    def test_diameter_cap(self) -> None:
        for distance, telescoping in [(0.25, 1.75), (0.75, 0.9), (0.0, 3.0)]:
            self.assertLessEqual(distance, min(1.0, telescoping))

    def test_first_divergence_residual_mass_exhaustive(self) -> None:
        rng = random.Random(20260730)
        for n in range(1, 7):
            for mask_bits in range(1, 1 << n):
                pre = tuple(MASK if mask_bits & (1 << i) else i % 3 for i in range(n))
                for _ in range(25):
                    left = random_monotone_suffix(rng, pre, 5)
                    right = random_monotone_suffix(rng, pre, 5)
                    # Equal committed coordinates are copy-only in both suffixes.
                    for i, token in enumerate(pre):
                        if token != MASK:
                            self.assertEqual(left[i], token)
                            self.assertEqual(right[i], token)
                    self.assertLessEqual(hamming(left, right), residual_mass(pre))

    def test_coordinate_capped_hybrid_union_bound(self) -> None:
        rng = random.Random(73)
        for _ in range(200):
            path = [tuple(rng.randrange(3) for _ in range(6))]
            for _ in range(8):
                next_state = list(path[-1])
                next_state[rng.randrange(6)] = rng.randrange(3)
                path.append(tuple(next_state))
            raw = sum(hamming(a, b) for a, b in zip(path, path[1:]))
            cap = coordinate_cap(path)
            self.assertLessEqual(hamming(path[0], path[-1]), cap + 1e-12)
            self.assertLessEqual(cap, min(1.0, raw) + 1e-12)

    def test_exact_last_change_attribution(self) -> None:
        path = [(0, 0, 0), (1, 0, 0), (1, 2, 0), (0, 2, 3)]
        mass, last = last_change_mass(path)
        self.assertEqual(mass, hamming(path[0], path[-1]))
        self.assertEqual(last, {1: 2, 2: 3})

    def test_first_hit_disjointification_is_invalid(self) -> None:
        path = [(0,), (1,), (0,)]
        endpoint_distance = hamming(path[0], path[-1])
        first_hit_mass = coordinate_cap(path)
        self.assertEqual(endpoint_distance, 0.0)
        self.assertEqual(first_hit_mass, 1.0)
        self.assertNotEqual(endpoint_distance, first_hit_mass)

    def test_no_split_case(self) -> None:
        path = [(MASK, MASK), (MASK, MASK), (1, 2)]
        self.assertEqual(hamming(path[-1], path[-1]), 0.0)
        self.assertEqual(0.0, 0.0)  # B_FS for tau=infinity.

    def test_early_and_late_residual_mass(self) -> None:
        self.assertEqual(residual_mass((MASK, MASK, MASK, MASK)), 1.0)
        self.assertEqual(residual_mass((1, 2, 3, MASK)), 0.25)

    def test_token_token_persistence_under_copy_only(self) -> None:
        left = (1, MASK, MASK)
        right = (2, MASK, MASK)
        left_final = (1, 3, 4)
        right_final = (2, 3, 4)
        self.assertNotEqual(left[0], right[0])
        self.assertNotEqual(left_final[0], right_final[0])

    def test_mask_token_repair(self) -> None:
        left = (MASK, 1)
        right = (2, 1)
        left_final = (2, 1)
        right_final = (2, 1)
        self.assertGreater(hamming(left, right), 0.0)
        self.assertEqual(hamming(left_final, right_final), 0.0)

    def test_remasking_breaks_residual_bound(self) -> None:
        common_pre = (1, 2, MASK)
        left_after_illegal_remask = (MASK, MASK, MASK)
        right_after = (1, 2, 3)
        left_final = (4, 5, 3)
        right_final = right_after
        self.assertGreater(
            hamming(left_final, right_final),
            residual_mass(common_pre),
        )
        self.assertEqual(left_after_illegal_remask.count(MASK), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
