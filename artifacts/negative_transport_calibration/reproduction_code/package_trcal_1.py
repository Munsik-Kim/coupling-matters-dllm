#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def manifest(root: Path, filename: str = "SCOPE_FILE_MANIFEST.json") -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != filename:
            rows.append({"relative_path": path.relative_to(root).as_posix(), "byte_size": path.stat().st_size, "sha256": sha(path)})
    write_json(root / filename, {"schema_version": 1, "file_count": len(rows), "files": rows})


def payload_manifest(payload: Path) -> None:
    rows = []
    for path in sorted(payload.rglob("*")):
        if path.is_file() and path.name not in {"FILE_MANIFEST.json", "SHA256SUMS.txt"}:
            rows.append({"relative_path": path.relative_to(payload).as_posix(), "byte_size": path.stat().st_size, "sha256": sha(path)})
    write_json(payload / "FILE_MANIFEST.json", {"schema_version": 1, "file_count": len(rows), "files": rows})
    (payload / "SHA256SUMS.txt").write_text(
        "".join(f"{row['sha256']}  {row['relative_path']}\n" for row in rows), encoding="utf-8"
    )


def zip_tree(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent).as_posix())
    with zipfile.ZipFile(destination) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failure: {bad}")


def verify_extraction(archive: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="trcal_verify_") as temporary:
        target = Path(temporary)
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(target)
        scope = next(target.rglob("SCOPE_FILE_MANIFEST.json"), None)
        if scope:
            root = scope.parent
            data = json.loads(scope.read_text())
            for row in data["files"]:
                path = root / row["relative_path"]
                if not path.is_file() or path.stat().st_size != row["byte_size"] or sha(path) != row["sha256"]:
                    raise RuntimeError(f"Extracted scope verification failed: {row['relative_path']}")


def verify_full_reproduction(archive: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="trcal_reproduce_") as temporary:
        target = Path(temporary)
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(target)
        source_run = target / "TRCAL_1_full_review"
        archived_repo = source_run / "payload/code_snapshot/repo"
        command = [sys.executable, str(archived_repo / "experiments/transport_calibration/scripts/reproduce_trcal_1.py"), "--source-run", str(source_run), "--model-free"]
        result = subprocess.run(command, cwd=archived_repo, text=True, capture_output=True, env={**dict(__import__("os").environ), "TMPDIR": "/tmp", "MPLCONFIGDIR": "/tmp/trcal_mpl"})
        if result.returncode != 0:
            raise RuntimeError(f"Clean extracted model-free reproduction failed:\n{result.stdout}\n{result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    payload = run_dir / "payload"
    starting = json.loads((payload / "provenance/preflight_start.json").read_text())
    final_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    final_branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    final_status = subprocess.check_output(["git", "status", "--short", "--branch"], cwd=ROOT, text=True)
    (payload / "provenance/git_state_after.txt").write_text(
        f"HEAD {final_head}\nbranch {final_branch}\n{final_status}", encoding="utf-8"
    )
    (payload / "provenance/command_history.txt").write_text(
        "TRCAL-1 canonical commands\n"
        "1. preflight source/hash/split audit\n"
        "2. run_trcal_1.py --smoke\n"
        "3. run_trcal_1.py --preset FULL --resume\n"
        "4. reproduce_trcal_1.py --source-run <run_dir> --model-free\n"
        "5. package_trcal_1.py --run-dir <run_dir>\n",
        encoding="utf-8",
    )
    payload_manifest(payload)
    gate = json.loads((payload / "audits/gate_decision.json").read_text())
    timing = json.loads((payload / "logs/pipeline_timing.json").read_text())
    package_root = run_dir / "package_staging"
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir()

    summary_root = package_root / "TRCAL_1_summary_review"
    summary_root.mkdir()
    for rel in ("reports", "figures"):
        shutil.copytree(payload / rel, summary_root / rel)
    for rel in ("derived", "bridge"):
        shutil.copytree(payload / rel, summary_root / rel)
    for rel in (
        "risk/survival_hazard_by_step.csv", "calibration/weight_scheme_summary.csv",
        "calibration/method_module_summary.csv", "audits/gate_decision.json",
        "audits/method_differentiation_audit.json", "audits/smoke_validity.json",
        "config/preregistration_trcal_1.json", "config/runtime_gate.json",
        "config/quantization_contract.json", "config/calibration_weight_contract.json",
        "config/statistical_contract.json", "provenance/model_asset_hashes.json",
        "provenance/dataset_identity.json", "provenance/data_split_manifest.csv", "STATUS.json",
    ):
        target = summary_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payload / rel, target)
    code = summary_root / "reproduction_code"
    code.mkdir()
    for path in (
        ROOT / "experiments/transport_calibration/trcal_core.py",
        ROOT / "experiments/transport_calibration/scripts/reproduce_trcal_1.py",
        ROOT / "experiments/transport_calibration/scripts/package_trcal_1.py",
    ):
        shutil.copy2(path, code / path.name)
    manifest(summary_root)
    summary_zip = run_dir / "TRCAL_1_summary_review.zip"
    zip_tree(summary_root, summary_zip)
    verify_extraction(summary_zip)

    full_root = package_root / "TRCAL_1_full_review"
    full_root.mkdir()
    shutil.copytree(payload, full_root / "payload")
    (full_root / "ARCHIVE_CONTENTS.md").write_text("# TRCAL-1 full review\n\nContains the complete scientific payload, row-level checkpoints, risk rows, activation moments, alpha vectors, raw evaluation rows, code, tests, reports, and logs. It does not duplicate model checkpoints or predecessor archives.\n", encoding="utf-8")
    (full_root / "REPRODUCE_ANALYSIS.txt").write_text("cd TRCAL_1_full_review/payload/code_snapshot/repo\npython experiments/transport_calibration/scripts/reproduce_trcal_1.py --source-run ../../.. --model-free\n", encoding="utf-8")
    manifest(full_root)
    full_zip = run_dir / "TRCAL_1_full_review.zip"
    zip_tree(full_root, full_zip)
    verify_extraction(full_zip)
    verify_full_reproduction(full_zip)

    delivery_root = package_root / "TRCAL_1_delivery"
    delivery_root.mkdir()
    upload = [summary_zip.name, full_zip.name, "TRCAL_1_delivery.zip"]
    delivery = {
        "work_package": "TRCAL_1", "selected_preset": timing["selected_preset"],
        "actual_runtime_seconds": timing.get("actual_end_to_end_seconds", timing["total_seconds"]), "peak_vram_mib": timing["peak_vram_mib"],
        "gates": gate, "summary": {"filename": summary_zip.name, "size": summary_zip.stat().st_size, "sha256": sha(summary_zip), "crc": "PASS"},
        "full": {"filename": full_zip.name, "size": full_zip.stat().st_size, "sha256": sha(full_zip), "crc": "PASS"},
        "starting_git_head": starting["starting_head"], "final_git_head": final_head,
        "final_branch": final_branch, "final_worktree_status": final_status.strip(),
        "source_requirements": ["pinned public model/tokenizer/GSM8K sources referenced in payload provenance"],
        "upload_checklist": upload, "paper_modified": False, "external_gpu_started": False,
        "reproduction_command": "python experiments/transport_calibration/scripts/reproduce_trcal_1.py --source-run <run_dir> --model-free",
    }
    write_json(delivery_root / "delivery_verification.json", delivery)
    (delivery_root / "UPLOAD_CHECKLIST.txt").write_text("\n".join(upload) + "\n", encoding="utf-8")
    manifest(delivery_root)
    delivery_zip = run_dir / "TRCAL_1_delivery.zip"
    zip_tree(delivery_root, delivery_zip)
    verify_extraction(delivery_zip)
    final = {**delivery, "delivery": {"filename": delivery_zip.name, "size": delivery_zip.stat().st_size, "sha256": sha(delivery_zip), "crc": "PASS"}}
    write_json(run_dir / "delivery_verification.json", final)
    print(json.dumps(final, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
