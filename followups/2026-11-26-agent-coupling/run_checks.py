"""Recompute all numbers and compare to the included exact-result snapshots."""
from pathlib import Path
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CASES = (
    ("coupling_agent_exact.py", "coupling_agent_exact.json"),
    ("counterexamples.py", "counterexamples.json"),
    ("audit_case017.py", "case017_counts.json"),
)
for script, snapshot in CASES:
    output = subprocess.check_output([sys.executable, str(HERE / script)], text=True)
    actual = json.loads(output)
    expected = json.loads((HERE / snapshot).read_text(encoding="utf-8"))
    if actual != expected:
        raise ValueError(f"Recomputed values differ from {snapshot}")
    print(f"PASS {script} -> {snapshot}")
