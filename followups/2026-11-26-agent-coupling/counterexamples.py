#!/usr/bin/env python3
"""Exact coupling counterexamples, using only the Python 3 standard library.

Run: python counterexamples.py > counterexamples.json
All paired laws are enumerated without sampling or floating-point arithmetic.
"""

from fractions import Fraction as F
from itertools import product
import json


HALF = F(1, 2)
QUARTER = F(1, 4)


def summarize_outcomes(pairs):
    """Summarize an iterator of (success A, success B, probability) triples."""
    joint = [[F(0), F(0)], [F(0), F(0)]]
    for a, b, mass in pairs:
        assert mass >= 0
        joint[int(a)][int(b)] += mass
    assert sum(map(sum, joint)) == 1
    loss, both_success = joint[1]
    recovery = joint[0][1]
    delta = recovery - loss
    return dict(success_a=loss + both_success, success_b=recovery + both_success,
                both_success=both_success, recovery=recovery, loss=loss, delta=delta,
                variance_paired_difference=recovery + loss - delta**2)


def check_joint(table, marginal_a, marginal_b):
    assert all(x >= 0 for row in table for x in row)
    assert tuple(map(sum, table)) == marginal_a
    assert tuple(map(sum, zip(*table))) == marginal_b


def opposite_argument_policies():
    # Both tools can do the job. Policy A sends the valid argument only to tool
    # 0; policy B only to tool 1. The environment rule is common and deterministic.
    tables = dict(same_tool=((HALF, 0), (0, HALF)),
                  independent=((QUARTER, QUARTER), (QUARTER, QUARTER)),
                  opposite_tool=((0, HALF), (HALF, 0)))
    results = {}
    for name, table in tables.items():
        check_joint(table, (HALF, HALF), (HALF, HALF))
        result = summarize_outcomes((a == 0, b == 1, table[a][b])
                                    for a, b in product(range(2), repeat=2))
        assert result['success_a'] == result['success_b'] == HALF
        assert result['recovery'] == result['loss'] == result['variance_paired_difference'] / 2
        results[name] = result
    assert [results[name]['recovery'] for name in tables] == [HALF, QUARTER, 0]
    return results


def asymmetric_reveal():
    # At t=1 A publicly reveals its fair bit, and B publicly waits. At t=2 A
    # copies its bit; B's own one-step transition requires a fair draw. A
    # co-adapted coupling must respect B's kernel given the WHOLE joint prefix.
    tables = dict(coadapted=((QUARTER, QUARTER), (QUARTER, QUARTER)),
                  unrestricted_match=((HALF, 0), (0, HALF)),
                  unrestricted_flip=((0, HALF), (HALF, 0)))
    results = {}
    for name, table in tables.items():
        check_joint(table, (HALF, HALF), (HALF, HALF))
        conditional_b_one = [table[a][1] / HALF for a in range(2)]
        coadapted = conditional_b_one == [HALF, HALF]
        assert coadapted == (name == 'coadapted')
        result = summarize_outcomes((a, b, table[a][b]) for a, b in product(range(2), repeat=2))
        assert result['success_a'] == result['success_b'] == HALF
        results[name] = dict(b_one_given_a_zero_or_one=conditional_b_one,
                             respects_both_step_kernels=coadapted, final=result)
    assert [results[name]['final']['recovery'] for name in tables] == [QUARTER, 0, HALF]
    return results


def main_simulator_extremes():
    # These are the raw stage kernels of the separately runnable main simulator.
    # Success requires label 1 at each stage. The equal tool succeeds on both
    # whenever arm A succeeds, using monotone argument/verification couplings.
    # The disjoint assignment makes simultaneous correct tool choice impossible.
    p_tool, q_tool = (HALF, QUARTER, QUARTER), (QUARTER, QUARTER, HALF)
    tools = dict(max_joint_success=((QUARTER, 0, QUARTER), (0, QUARTER, 0), (0, 0, QUARTER)),
                 min_joint_success=((QUARTER, QUARTER, 0), (0, 0, QUARTER), (0, 0, QUARTER)))
    binary = ((QUARTER, QUARTER), (0, HALF))
    check_joint(binary, (HALF, HALF), (QUARTER, 1 - QUARTER))
    results = {}
    paths = list(product(range(3), range(2), range(2)))
    for name, tool in tools.items():
        check_joint(tool, p_tool, q_tool)
        pairs = ((a == (1, 1, 1), b == (1, 1, 1), tool[a[0]][b[0]] *
                  binary[a[1]][b[1]] * binary[a[2]][b[2]]) for a, b in product(paths, repeat=2))
        final = summarize_outcomes(pairs)
        assert (final['success_a'], final['success_b']) == (F(1, 16), F(9, 64))
        results[name] = dict(tool_joint=tool, argument_joint=binary, verification_joint=binary, final=final)
    assert results['max_joint_success']['final']['both_success'] == F(1, 16)
    assert results['min_joint_success']['final']['both_success'] == 0
    return results


if __name__ == '__main__':
    payload = dict(opposite_argument_policies=opposite_argument_policies(),
                   asymmetric_reveal=asymmetric_reveal(),
                   main_simulator_extremes=main_simulator_extremes())
    print(json.dumps(payload, default=str, indent=2))
