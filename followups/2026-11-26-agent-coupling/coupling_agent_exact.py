#!/usr/bin/env python3
"""Exact CPU enumeration of two stochastic agents. Run with Python 3.8+.

python coupling_agent_exact.py > coupling_agent_exact.json

All probability arithmetic uses fractions. Each arm's three draws are
independent within that arm. Coupling is specified separately at each draw.
The two tools that inspect data cannot write. A wrong-ID write leaves the
target unchanged. The fresh check, when requested, reads the target.
"""
from collections import defaultdict
from fractions import Fraction as F
from itertools import product
import json


STAGES = ("tool", "argument", "verification")
FIRST_DIFFERENCE = STAGES + ("none",)
LABELS = (
    ("read_metadata", "set_flag_on", "read_history"),
    ("wrong_id", "target_id"),
    ("stop", "fresh_status_check"),
)
P = (
    (F(1, 2), F(1, 4), F(1, 4)),
    (F(1, 2), F(1, 2)),
    (F(1, 2), F(1, 2)),
)
Q = (
    (F(1, 4), F(1, 4), F(1, 2)),
    (F(1, 4), F(3, 4)),
    (F(1, 4), F(3, 4)),
)
METRICS = ("correct_tool", "correct_argument", "target_state_on", "verified_success")


def metrics(path):
    tool, argument, verification = path
    correct_tool = tool == 1
    correct_argument = argument == 1
    state_on = correct_tool and correct_argument
    return (correct_tool, correct_argument, state_on, state_on and verification == 1)


def independent(p, q):
    return [[a * b for b in q] for a in p]


def maximal(p, q):
    """Put minimum masses on the diagonal. Couple surplus and deficit independently."""
    diagonal = [min(a, b) for a, b in zip(p, q)]
    residual = 1 - sum(diagonal)
    joint = [[F(0) for _ in q] for _ in p]
    for i in range(len(p)):
        joint[i][i] = diagonal[i]
        if residual:
            for j in range(len(q)):
                joint[i][j] += (p[i] - diagonal[i]) * (q[j] - diagonal[j]) / residual
    return joint


def shared_gumbel(p, q):
    """Exact shared exponential race, equivalent to common additive Gumbels.

    For a category i to win both races, conditioning on its Exp(1) clock
    E_i=t gives E_k >= max(p_k/p_i,q_k/q_i)*t for k != i. Integrating gives
    the diagonal reciprocal below. An A winner i and B winner j require
    p_i/q_i >= p_j/q_j. Ordered by this ratio, the table is upper triangular.
    For two or three categories the marginals and diagonal fix all cells.
    """
    n = len(p)
    assert n == len(q) and n in (2, 3) and min(p + q) > 0
    joint = [[F(0) for _ in q] for _ in p]
    for i in range(n):
        joint[i][i] = 1 / sum(max(a / p[i], b / q[i]) for a, b in zip(p, q))
    order = sorted(range(n), key=lambda i: p[i] / q[i], reverse=True)
    first, last = order[0], order[-1]
    if n == 3:
        middle = order[1]
        joint[first][middle] = q[middle] - joint[middle][middle]
        joint[middle][last] = p[middle] - joint[middle][middle]
    joint[first][last] = p[first] - sum(joint[first])
    return joint


def verify_joint(joint, p, q):
    assert all(value >= 0 for row in joint for value in row)
    assert tuple(map(sum, joint)) == p
    assert tuple(map(sum, zip(*joint))) == q


def path_law(kernels):
    paths = product(*(range(len(kernel)) for kernel in kernels))
    return {path: kernels[0][path[0]] * kernels[1][path[1]] * kernels[2][path[2]]
            for path in paths}


def first_difference(a, b):
    return next((stage for stage, x, y in zip(STAGES, a, b) if x != y), "none")


def metric_summary(table):
    neither, recovery, loss, both = (table[i] for i in ((0, 0), (0, 1), (1, 0), (1, 1)))
    a, b = loss + both, recovery + both
    delta = b - a
    assert sum((neither, recovery, loss, both)) == 1
    assert delta == recovery - loss
    assert max(F(0), b - a) <= recovery <= min(b, 1 - a)
    assert max(F(0), a - b) <= loss <= min(a, 1 - b)
    return dict(a=a, b=b, both_fail=neither, recovery=recovery, loss=loss,
                both_pass=both, delta=delta, disagreement=recovery + loss,
                variance_paired_difference=recovery + loss - delta**2)


def evaluate(coupler):
    joints = [coupler(p, q) for p, q in zip(P, Q)]
    for joint, p, q in zip(joints, P, Q):
        verify_joint(joint, p, q)
    p_paths, q_paths = path_law(P), path_law(Q)
    observed_p, observed_q = defaultdict(F), defaultdict(F)
    tables = [defaultdict(F) for _ in METRICS]
    by_first = {key: {"mass": F(0), "recovery": F(0), "loss": F(0)}
                for key in FIRST_DIFFERENCE}
    for a in p_paths:
        for b in q_paths:
            w = joints[0][a[0]][b[0]] * joints[1][a[1]][b[1]] * joints[2][a[2]][b[2]]
            observed_p[a] += w
            observed_q[b] += w
            scores_a, scores_b = metrics(a), metrics(b)
            for table, x, y in zip(tables, scores_a, scores_b):
                table[int(x), int(y)] += w
            bucket = by_first[first_difference(a, b)]
            bucket["mass"] += w
            if scores_b[-1] and not scores_a[-1]:
                bucket["recovery"] += w
            if scores_a[-1] and not scores_b[-1]:
                bucket["loss"] += w
    assert observed_p == p_paths and observed_q == q_paths
    summaries = {key: metric_summary(table) for key, table in zip(METRICS, tables)}
    for index, summary in enumerate(summaries.values()):
        for label, paths in (("a", p_paths), ("b", q_paths)):
            assert summary[label] == sum(w for path, w in paths.items() if metrics(path)[index])
    assert sum(bucket["mass"] for bucket in by_first.values()) == 1
    for key in ("recovery", "loss"):
        assert sum(bucket[key] for bucket in by_first.values()) == summaries["verified_success"][key]
        assert by_first["none"][key] == 0
    return dict(stage_joint_matrices=dict(zip(STAGES, joints)), metrics=summaries,
                first_raw_difference_and_final_outcome=by_first)


def verified_success_rate(kernels):
    return sum(w for path, w in path_law(kernels).items() if metrics(path)[-1])


def one_stage_oracles():
    """Intervene on one decision of B. All downstream B kernels are preserved."""
    baseline = verified_success_rate(Q)
    results = {}
    for stage_index, stage in enumerate(STAGES):
        # In each label list, index 1 is the oracle action for this objective.
        kernels = list(Q)
        kernels[stage_index] = tuple(F(action == 1) for action in range(len(Q[stage_index])))
        rate = verified_success_rate(kernels)
        results[stage] = dict(rate=rate, gain=rate - baseline)
    assert tuple(item["gain"] for item in results.values()) == (F(27, 64), F(3, 64), F(3, 64))
    return dict(baseline=baseline, interventions=results)


def a_to_b_substitutions():
    """Switch known decision kernels to study marginal effects in this simulator."""
    rates = {}
    for mask in product((False, True), repeat=3):
        kernels = [Q[i] if use_b else P[i] for i, use_b in enumerate(mask)]
        label = "+".join(stage for stage, use_b in zip(STAGES, mask) if use_b) or "none"
        rates[label] = verified_success_rate(kernels)
    interaction = rates["argument+verification"] - rates["argument"] - rates["verification"] + rates["none"]
    assert rates["tool"] == rates["none"]
    assert rates["argument"] - rates["none"] == rates["verification"] - rates["none"] == F(1, 32)
    assert interaction == F(1, 64)
    return dict(rate_by_b_stages=rates, argument_verification_interaction=interaction)


def main():
    results = {fn.__name__: evaluate(fn) for fn in (independent, shared_gumbel, maximal)}
    assert results["shared_gumbel"]["stage_joint_matrices"]["tool"] == [
        [F(1, 4), F(1, 20), F(1, 5)],
        [0, F(1, 5), F(1, 20)],
        [0, 0, F(1, 4)],
    ]
    expected_final_recovery_loss = {
        "independent": (F(135, 1024), F(55, 1024)),
        "shared_gumbel": (F(29, 320), F(1, 80)),
        "maximal": (F(5, 64), F(0)),
    }
    for name, result in results.items():
        final = result["metrics"]["verified_success"]
        assert (final["recovery"], final["loss"]) == expected_final_recovery_loss[name]
    payload = dict(labels=dict(zip(STAGES, LABELS)), a=dict(zip(STAGES, P)),
                   b=dict(zip(STAGES, Q)), results=results,
                   b_oracle_one_stage=one_stage_oracles(),
                   a_to_b_substitutions=a_to_b_substitutions())
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
