"""Rebuild a task-matched audit of the public Case017 CSV.

With an input path: python audit_case017.py /path/to/episode_ledger.csv --write-pairs case017_pairs.csv
Offline (on the bundled pairs): python audit_case017.py
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

SOURCE_SHA256 = "35f689590df844332348f99c50f9ce0fb28fe12f9b816e0a196cf3d3ebae2b2a"
METRICS = ("verified", "state_correct", "fresh_validation", "final_correct")
POLICIES = ("C0", "G")
FIELDS = ["task_id"] + [p + "_" + m for p in POLICIES for m in METRICS]
EXPECTED = ((9, 8, 0, 7), (2, 15, 0, 7), (8, 9, 0, 7), (2, 15, 0, 7))

def project(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Input is not the pinned public ledger.")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 256
    subset = defaultdict(dict)
    for row in rows:
        if row["stage"] == "P2" and row["kv"] == "K1" and row["policy"] in POLICIES:
            task, policy = row["task_id"], row["policy"]
            assert policy not in subset[task]
            subset[task][policy] = row
    pairs = []
    for task, group in sorted(subset.items()):
        assert set(group) == set(POLICIES)
        row = {"task_id": task}
        for p in POLICIES:
            for m in METRICS:
                row[p + "_" + m] = group[p][m]
        pairs.append(row)
    return pairs

def audit(pairs):
    assert len(pairs) == len(set(row["task_id"] for row in pairs)) == 24
    result = {}
    for m, expected in zip(METRICS, EXPECTED):
        counts = Counter((row["C0_" + m], row["G_" + m]) for row in pairs)
        cells = [counts[x, y] for x, y in (("0", "0"), ("0", "1"), ("1", "0"), ("1", "1"))]
        assert sum(cells) == len(pairs) and tuple(cells) == expected
        result[m] = dict(zip(("00", "01", "10", "11"), cells))
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", nargs="?", type=Path)
    ap.add_argument("--write-pairs", type=Path)
    args = ap.parse_args()
    if args.source is not None:
        pairs = project(args.source)
    else:
        with Path(__file__).with_name("case017_pairs.csv").open(encoding="utf-8", newline="") as stream:
            pairs = list(csv.DictReader(stream))
    result = audit(pairs)
    if args.write_pairs is not None:
        with args.write_pairs.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(pairs)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
