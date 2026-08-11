#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, math, re, zipfile
from pathlib import Path

SKIP_PARTS={".git","build","__pycache__",".pytest_cache"}
BINARY={".pdf",".png",".jpg",".jpeg",".gif",".npz",".parquet",".pyc"}
MANIFEST_EXCLUDED={"manifests/GITHUB_FILE_MANIFEST.json","manifests/GITHUB_SHA256SUMS.txt"}

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def patterns():
    return {
      "private_home": re.compile(re.escape("/"+"home/"+"ms"+"kim"),re.I),
      "windows_mount": re.compile(re.escape("/"+"mnt/"+"c/")+"|"+re.escape("/"+"mnt/"+"d/"),re.I),
      "windows_user": re.compile(r"[A-Za-z]:"+re.escape("\\")+r"Users"+re.escape("\\"),re.I),
      "private_cloud": re.compile(r"(?:drive|docs)"+re.escape(".google.com")+r"|one"+"drive|share"+"point",re.I),
      "github_token": re.compile("gh"+"p_[A-Za-z0-9]{20,}|github_"+"pat_[A-Za-z0-9_]{20,}"),
      "generic_secret": re.compile(r"(?:OPENAI_API_KEY|HF_TOKEN|HUGGINGFACE_TOKEN|RUNPOD_API_KEY|GITHUB_TOKEN)\s*[:=]\s*\S+"),
      "provider_key": re.compile(r"(?<![A-Za-z0-9])"+"s"+"k-[A-Za-z0-9_-]{20,}|(?<![A-Za-z0-9])h"+"f_[A-Za-z0-9]{20,}|AK"+"IA[0-9A-Z]{16}"),
      "private_key": re.compile("BEGIN "+"(?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
      "bearer": re.compile(r"Bearer\s+[A-Za-z0-9._~-]{20,}",re.I),
    }

def text_findings(label, data):
    try: text=data.decode("utf-8")
    except UnicodeDecodeError: return []
    out=[]
    for name,rx in patterns().items():
        for m in rx.finditer(text): out.append((label,name,m.start()))
    email=re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for m in email.finditer(text):
        if not m.group(0).endswith("@users.noreply.github.com"): out.append((label,"email",m.start()))
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=Path(".")); args=ap.parse_args(); root=args.root.resolve()
    manifest=json.loads((root/"manifests/GITHUB_FILE_MANIFEST.json").read_text())
    failures=[]; actual=[]; findings=[]; large=[]
    for path in sorted(root.rglob("*")):
        rel=path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts): continue
        if path.is_symlink():
            target=path.resolve()
            if root!=target and root not in target.parents: failures.append(f"escaping symlink: {rel}")
            continue
        if not path.is_file(): continue
        rp=rel.as_posix()
        if rp not in MANIFEST_EXCLUDED: actual.append(rp)
        size=path.stat().st_size
        if size>=25_000_000: large.append((rp,size))
        if size>=100_000_000: failures.append(f"file >=100MB: {rp}")
        if path.name==".env" or path.suffix.lower() not in BINARY:
            findings.extend(text_findings(rp,path.read_bytes()))
        if path.suffix.lower()==".zip":
            try:
                with zipfile.ZipFile(path) as z:
                    bad=z.testzip()
                    if bad: failures.append(f"bad zip member: {rp}:{bad}")
                    for info in z.infolist():
                        if info.file_size<=5_000_000 and Path(info.filename).suffix.lower() not in BINARY:
                            findings.extend(text_findings(rp+"!"+info.filename,z.read(info)))
            except zipfile.BadZipFile: failures.append(f"bad zip: {rp}")
    expected={r["path"]:r for r in manifest["files"]}
    if set(actual)!=set(expected): failures.append(f"manifest path mismatch missing={sorted(set(expected)-set(actual))} extra={sorted(set(actual)-set(expected))}")
    for rp,row in expected.items():
        path=root/rp
        if path.is_file() and (path.stat().st_size!=row["size_bytes"] or digest(path)!=row["sha256"]): failures.append(f"manifest hash/size: {rp}")
    if findings: failures.extend(f"sensitive pattern {kind}: {label}" for label,kind,_ in findings)
    for md in root.rglob("*.md"):
        if any(part in SKIP_PARTS for part in md.relative_to(root).parts): continue
        text=md.read_text(errors="replace")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)",text):
            target=link.split("#",1)[0].strip().strip("<>")
            if not target or re.match(r"(?:https?://|mailto:)",target): continue
            if not (md.parent/target).exists(): failures.append(f"broken link {md.relative_to(root)} -> {target}")
    try:
        import yaml
        yaml.safe_load((root/"CITATION.cff").read_text())
        for y in list(root.rglob("*.yaml"))+list(root.rglob("*.yml")): yaml.safe_load(y.read_text())
    except Exception as e: failures.append(f"YAML/CFF parse: {e}")
    for j in root.rglob("*.json"):
        if any(part in SKIP_PARTS for part in j.relative_to(root).parts): continue
        try: json.loads(j.read_text())
        except Exception as e: failures.append(f"JSON parse {j.relative_to(root)}: {e}")
    status={"manifest_files":len(expected),"sensitive_findings":len(findings),"files_ge_25mb":large,"failures":failures}
    print(json.dumps(status,indent=2))
    raise SystemExit(1 if failures else 0)
if __name__=="__main__": main()
