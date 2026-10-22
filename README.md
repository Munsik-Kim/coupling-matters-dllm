# Coupling Matters

Developed mathematical bounds and CPU audit tools to study how low-bit changes in a masked text generator spread to its final output. The comparisons control the randomness shared by the original and changed models, so the synchronization rule is part of the analysis.

**Preprint / technical report; not peer reviewed.**

Munsik Kim — Independent Researcher, Republic of Korea

Zenodo: https://zenodo.org/records/21880649  
DOI: https://doi.org/10.5281/zenodo.21880649

## Overview

Post-training quantization can change token choices, commit sets, and later states in masked diffusion language models. This public research compendium develops and audits finite-horizon transport bounds in which the coupling used to synchronize full-precision and quantized generation is part of the measured upper bound. The central first-divergence result bounds later normalized Hamming distortion by residual unresolved mask mass under explicit monotone, copy-only assumptions.

This repository contains the technical report, compact evidence, selected model-free experiment code, independent audits, preregistered negative investigations, and reusable techniques extracted from the project. It does not contain the private development repository, its history, model checkpoints, private logs, or large raw trajectory archives.

## Main contributions

- A first-divergence residual-unresolved-mass certificate for monotone copy-only masked generation.
- Coupling-aware finite-horizon measurements and simultaneous fixed-suite statistical bounds.
- Native coordinatewise maximal-coupling primitives with marginal and product-hazard audits.
- Independent clean-room and raw-to-claim verification artifacts.
- Explicit negative results for additive token metrics, terminal witnesses, and transport-weighted clipping.

## Repository map

- [`paper/`](paper/README.md): released PDF and complete LaTeX source.
- [`theory/`](theory/README.md): concise theorem, assumptions, and propagation guides.
- [`experiments/`](experiments/README.md): public model-free analysis code and independent cross-checks.
- [`tools/`](tools/README.md): reusable coupling, RNG, certificate, and audit utilities.
- [`artifacts/`](artifacts/README.md): compact public evidence indexed by work package.
- [`docs/`](docs/REPOSITORY_MAP.md): maps, limitations, negative results, and reproducibility tiers.
- [`manifests/`](manifests/README.md): GitHub-tree integrity and provenance ledgers.

## Quick verification

```bash
make verify
make test
make paper
```

The default tests are CPU-only and do not download models or datasets. `make paper` requires `latexmk` and a standard LaTeX installation.

## Reproducibility tiers

1. **Repository-only verification:** manifest checks, a clean paper build, CPU-only theorem/coupling tests, and compact-file validation.
2. **Compact artifact re-analysis:** public tables and selected reproduction scripts; no checkpoint redistribution.
3. **Full experiment rerun:** external public models/datasets, GPU compute, and some omitted large work-package data are required. See [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

## Model and data requirements

No model or dataset is needed for Tier 1. The report used public MDLM and SMDM checkpoints and public evaluation data; none are redistributed here. Exact scope and omissions are listed in [`docs/DATA_AND_MODELS.md`](docs/DATA_AND_MODELS.md) and [`manifests/OMITTED_LARGE_ARTIFACTS.csv`](manifests/OMITTED_LARGE_ARTIFACTS.csv).

## Limitations and negative results

The certificates are metric-, sampler-, coupling-, model-, and population-specific. They do not certify semantic quality or deployment kernels, and coordinatewise maximal coupling is not claimed to be joint-optimal. See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) and [`docs/NEGATIVE_RESULTS.md`](docs/NEGATIVE_RESULTS.md).

The preregistered negative investigations found that the tested embedding/byte metrics did not materially resolve exact-token saturation; held-out witness lower confidence bounds were vacuous; and survival-residual transport-weighted clipping did not beat uniform clipping on the primary W4 endpoint.

## Citation

Please cite the Zenodo record using [`CITATION.cff`](CITATION.cff): DOI [`10.5281/zenodo.21880649`](https://doi.org/10.5281/zenodo.21880649).

## Licenses

Original code is Apache-2.0. The report, original figures, compact tables, and reports are CC BY 4.0. Third-party material retains its original license. See [`LICENSE_SCOPE.md`](LICENSE_SCOPE.md).
