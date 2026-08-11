# WP06-CERT-3R-SIMPLE Independent Audit Report

## Scope and provenance

No model inference, checkpoint load, or trajectory regeneration occurred.
The v3.4 PDF was verified at 402,808 bytes with SHA-256
`c634f5c49a0db4d469651db183c5c9b1f3cba44b6fcedad667a799ce06d66b10`
and imported by commit `80728c313f32c2606151ff795b376d27a9f532e4`.

The 27 CERT-3 parts reconstructed to a 119,713,469-byte archive with
SHA-256 `f99e316c4a21a02d5c59aefaa9ee9401b3d0eaa23b984e1eead09dd4abb1fc45`.
ZIP CRC, all 146 payload-manifest hashes, row-level raw inclusion, and
archived reproduction metadata passed.

## Raw integrity

- Fixed prompts: 64/64, hashes matched.
- CMC trajectories: 768; CRN trajectories: 384.
- Standalone FP trajectories: 256, represented by 1,792 horizon rows.
- Coupled transition rows: 38,016.
- Horizon endpoint rows independently reconstructed: 8,064.
- RNG rows: 608,256.
- Missing design cells: 0.
- Duplicate primary keys: 0.
- Referential-integrity issues: 0.
- NaN/Inf in required numerical fields: 0.

## Coupling audit

Fresh 100,000-draw clean-room Monte Carlo passed for all 24 archived
categorical FP/Q law pairs. Both marginal error thresholds and mismatch-TV
thresholds passed. The 10,748 full-state product hazards reconstructed from
171,968 coordinate-TV rows with maximum formula error zero; 414 diagonal
steps produced zero splits. There were no semantic RNG-key or stable-seed
collisions among 512,030 recorded draw events.

The archive does not store the individual original 100,000 audit draws, so
the clean-room marginal audit is an independent resampling from the frozen
laws rather than bytewise replay of the original Monte Carlo sample.

## Pathwise certificate

For every coupled trajectory and all seven horizons, endpoint Hamming,
first split, and residual pre-split mask mass were reconstructed from
transition-state rows rather than the derived first-split table.

- Reconstructed comparisons: 8,064.
- `D_H > B_FS_H + 1e-12`: 0.
- Committed-equal pre-split prefix violations: 0.
- Raw endpoint cross-table discrepancies: 0.

## Independent headline recalculation

Full-horizon results:

| severity | mean D_CMC | UCB D_CMC | mean B_FS | UCB B_FS |
|---|---:|---:|---:|---:|
| W8 | 0.23486328125 | 0.35084712114 | 0.36279296875 | 0.47877680864 |
| W6 | 0.40429687500 | 0.52028071489 | 0.59594726562 | 0.71193110552 |
| W4 | 0.76708984375 | 0.88307368364 | 0.92016601562 | 1.00000000000 |

The second implementation used a direct PyArrow scan and Python
dictionaries. Its maximum difference from the primary clean-room pipeline
was zero, and it also found zero pathwise violations.

## Simultaneous fixed-suite certificate

The preregistered calculation uses `K=49`, family-wise error 0.05, and
Hoeffding radius `0.11598383989389408` at `n=256`. The `n=256` argument is
valid for the fixed-suite target because four equally weighted, independent
bounded coupling draws are used for each of 64 prompts. Cross-cell
dependence is permitted by the Bonferroni union bound.

This conclusion is conditional on treating distinct event-addressed
hash-based pseudorandom streams as independent Monte Carlo draws. It is not
unseen-prompt inference.

### Absolute prefix-closed 95% horizons

| severity | route | epsilon .25 | epsilon .50 | epsilon .75 |
|---|---|---|---|---|
| W8 | B_FS | H4 | FULL | FULL |
| W8 | D_CMC | H16 | FULL | FULL |
| W6 | B_FS | NONE | H8 | FULL |
| W6 | D_CMC | H12 | H24 | FULL |
| W4 | B_FS | NONE | NONE | H4 |
| W4 | D_CMC | H4 | H16 | H24 |

No relative 95% horizon survives for theta 0.25, 0.50, or 0.75.

## Conservative dependence sensitivity

Using 64 prompt means rather than 256 prompt-seed observations gives:

| severity | route | epsilon .25 | epsilon .50 | epsilon .75 |
|---|---|---|---|---|
| W8 | B_FS | NONE | H8 | FULL |
| W8 | D_CMC | H4 | FULL | FULL |
| W6 | B_FS | NONE | H4 | H16 |
| W6 | D_CMC | NONE | H24 | FULL |
| W4 | B_FS | NONE | NONE | NONE |
| W4 | D_CMC | NONE | H12 | H16 |

This weakens W4 materially but is a conservative sensitivity, not a
replacement of the preregistered theorem.

At FULL, leave-one-prompt ranges were:

- W8: D 0.227927–0.238591; B_FS 0.353423–0.368552.
- W6: D 0.398065–0.410714; B_FS 0.591022–0.605407.
- W4: D 0.764137–0.770089; B_FS 0.918899–0.922619.

Leave-one-seed ranges were:

- W8: D 0.218424–0.244466; B_FS 0.342448–0.379883.
- W6: D 0.382161–0.417643; B_FS 0.564128–0.611979.
- W4: D 0.763021–0.772135; B_FS 0.916992–0.922852.

No single omission reverses the primary numerical direction.

## Original comparison

After the blind code/output freeze, 338 headline quantities were compared
with the original tables. Discrepancies: 0. Maximum absolute floating
difference: `1.11e-16`.

## Theory and claim audit

The v3.4 theorems cover the experiment when their explicit assumptions are
maintained. No theorem counterexample was found under those assumptions.
Required qualifications are:

1. state the pseudorandom-stream independence premise beside the `n=256`
   empirical certificate;
2. update the PDF's now-stale statement that row-level audit is pending;
3. specify the route and tolerance when saying all bit widths certify;
4. retain the CMC versus joint-maximal/optimal distinction.

These do not change the primary numbers or horizons. The PDF was not edited.

## Audit gate

`AUDIT_PASS_WITH_QUALIFICATIONS`

The primary fixed-suite result survives independently and exactly.
Qualifications concern claim wording, the archived marginal-draw granularity,
and conservative prompt-block sensitivity—not a numerical, statistical, or
theorem failure.
