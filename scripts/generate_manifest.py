#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

EXCLUDED = {"manifests/GITHUB_FILE_MANIFEST.json", "manifests/GITHUB_SHA256SUMS.txt"}

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--root", type=Path, default=Path(".")); a=p.parse_args()
    root=a.root.resolve(); rows=[]
    ignored={".git","build","__pycache__",".pytest_cache"}
    for path in sorted(root.rglob("*")):
        relpath=path.relative_to(root)
        if not path.is_file() or any(part in ignored for part in relpath.parts): continue
        rel=relpath.as_posix()
        if rel in EXCLUDED: continue
        rows.append({"path":rel,"size_bytes":path.stat().st_size,"sha256":digest(path)})
    manifest={"schema_version":"1.0","repository":"Munsik-Kim/coupling-matters-dllm","version":"v1.0.0","file_count":len(rows),"files":rows}
    (root/"manifests/GITHUB_FILE_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root/"manifests/GITHUB_SHA256SUMS.txt").write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in rows))
    print(f"manifest files: {len(rows)}")
if __name__=="__main__": main()
