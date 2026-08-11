# Reproducibility

## Tier 1 — repository-only

Run `make verify`, `make test`, and `make paper`. This checks the public manifest, links, structured metadata, archives, CPU-only theorem/coupling regressions, and a clean LaTeX build.

## Tier 2 — compact artifact re-analysis

Selected public scripts reconstruct tables/checks from compact artifacts. Individual artifact READMEs name any external compact source required. No model inference is performed.

## Tier 3 — full experiment rerun

Requires public MDLM/SMDM checkpoints, public datasets, GPU compute, exact compatible environments, and omitted large raw work-package data. The repository is therefore not described as fully self-contained for Tier 3.
