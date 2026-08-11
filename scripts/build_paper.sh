#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp -a "$ROOT/paper/source" "$TMP/source"
mkdir -p "$TMP/out"
if command -v latexmk >/dev/null; then
  (cd "$TMP/source" && latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$TMP/out" main.tex)
elif command -v tectonic >/dev/null; then
  (cd "$TMP/source" && tectonic -c minimal --keep-logs --outdir "$TMP/out" main.tex)
else
  echo "latexmk or tectonic is required" >&2
  exit 2
fi
test -s "$TMP/out/main.pdf"
head -c 5 "$TMP/out/main.pdf" | grep -q '%PDF-'
mkdir -p "$ROOT/build"
cp "$TMP/out/main.pdf" "$ROOT/build/Coupling_Matters_Technical_Report_v1.0.0.pdf"
echo "clean paper build: $ROOT/build/Coupling_Matters_Technical_Report_v1.0.0.pdf"
