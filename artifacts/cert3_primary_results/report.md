# WP06-CERT-3 Native CMC Statistical Certification FULL

## Certified target and claim scope

The target is the average over the fixed preregistered 64-prompt suite. Uncertainty is over independent coupling draws; no broader prompt-population inference or language-quality claim is made.

## Coupling validity before results

- All hard audits: PASS
- Pathwise `D > B_FS` violations: 0
- CMC remains an independent coordinatewise product coupling, not joint maximal.

## Simultaneous one-sided statistical certificate

The primary family contains 49 one-sided Hoeffding statements at family-wise error 0.05: 21 B_FS upper bounds, 21 D_CMC upper bounds, and 7 Delta_ref lower bounds.

| severity | horizon | mean D | UCB D | mean B_FS | UCB B_FS |
|---|---|---:|---:|---:|---:|
| W8 | H4 | 0.009277 | 0.125261 | 0.105713 | 0.221697 |
| W8 | H8 | 0.026611 | 0.142595 | 0.201660 | 0.317644 |
| W8 | H12 | 0.052246 | 0.168230 | 0.285889 | 0.401873 |
| W8 | H16 | 0.081787 | 0.197771 | 0.313721 | 0.429705 |
| W8 | H24 | 0.155518 | 0.271501 | 0.351562 | 0.467546 |
| W8 | H32 | 0.234863 | 0.350847 | 0.362793 | 0.478777 |
| W8 | FULL | 0.234863 | 0.350847 | 0.362793 | 0.478777 |
| W6 | H4 | 0.020752 | 0.136736 | 0.219238 | 0.335222 |
| W6 | H8 | 0.050537 | 0.166521 | 0.353760 | 0.469744 |
| W6 | H12 | 0.091797 | 0.207781 | 0.454102 | 0.570085 |
| W6 | H16 | 0.137695 | 0.253679 | 0.513672 | 0.629656 |
| W6 | H24 | 0.266357 | 0.382341 | 0.576904 | 0.692888 |
| W6 | H32 | 0.404297 | 0.520281 | 0.595947 | 0.711931 |
| W6 | FULL | 0.404297 | 0.520281 | 0.595947 | 0.711931 |
| W4 | H4 | 0.060791 | 0.176775 | 0.568115 | 0.684099 |
| W4 | H8 | 0.139893 | 0.255876 | 0.759766 | 0.875749 |
| W4 | H12 | 0.234131 | 0.350115 | 0.877930 | 0.993914 |
| W4 | H16 | 0.330322 | 0.446306 | 0.909668 | 1.000000 |
| W4 | H24 | 0.546387 | 0.662371 | 0.918945 | 1.000000 |
| W4 | H32 | 0.767090 | 0.883074 | 0.920166 | 1.000000 |
| W4 | FULL | 0.767090 | 0.883074 | 0.920166 | 1.000000 |

## Absolute certified horizons

| severity | certificate | epsilon | H_empirical | H_95 | prefix_closed |
|---|---|---|---|---|---|
| W8 | B_FS_CMC | 0.25 | H8 | H4 | True |
| W8 | B_FS_CMC | 0.5 | FULL | FULL | True |
| W8 | B_FS_CMC | 0.75 | FULL | FULL | True |
| W8 | D_CMC | 0.25 | FULL | H16 | True |
| W8 | D_CMC | 0.5 | FULL | FULL | True |
| W8 | D_CMC | 0.75 | FULL | FULL | True |
| W6 | B_FS_CMC | 0.25 | H4 | NONE | True |
| W6 | B_FS_CMC | 0.5 | H12 | H8 | True |
| W6 | B_FS_CMC | 0.75 | FULL | FULL | True |
| W6 | D_CMC | 0.25 | H16 | H12 | True |
| W6 | D_CMC | 0.5 | FULL | H24 | True |
| W6 | D_CMC | 0.75 | FULL | FULL | True |
| W4 | B_FS_CMC | 0.25 | NONE | NONE | True |
| W4 | B_FS_CMC | 0.5 | NONE | NONE | True |
| W4 | B_FS_CMC | 0.75 | H4 | H4 | True |
| W4 | D_CMC | 0.25 | H12 | H4 | True |
| W4 | D_CMC | 0.5 | H16 | H16 | True |
| W4 | D_CMC | 0.75 | H24 | H24 | True |

## Relative certified horizons

| severity | certificate | theta | H_empirical | H_95 | prefix_closed |
|---|---|---|---|---|---|
| W8 | B_FS_CMC | 0.25 | NONE | NONE | True |
| W8 | B_FS_CMC | 0.5 | FULL | NONE | True |
| W8 | B_FS_CMC | 0.75 | FULL | NONE | True |
| W8 | D_CMC | 0.25 | FULL | NONE | True |
| W8 | D_CMC | 0.5 | FULL | NONE | True |
| W8 | D_CMC | 0.75 | FULL | NONE | True |
| W6 | B_FS_CMC | 0.25 | NONE | NONE | True |
| W6 | B_FS_CMC | 0.5 | NONE | NONE | True |
| W6 | B_FS_CMC | 0.75 | NONE | NONE | True |
| W6 | D_CMC | 0.25 | H16 | NONE | True |
| W6 | D_CMC | 0.5 | FULL | NONE | True |
| W6 | D_CMC | 0.75 | FULL | NONE | True |
| W4 | B_FS_CMC | 0.25 | NONE | NONE | True |
| W4 | B_FS_CMC | 0.5 | NONE | NONE | True |
| W4 | B_FS_CMC | 0.75 | NONE | NONE | True |
| W4 | D_CMC | 0.25 | NONE | NONE | True |
| W4 | D_CMC | 0.5 | H16 | NONE | True |
| W4 | D_CMC | 0.75 | H24 | NONE | True |

## Direct coupling versus first-divergence certificate

D_CMC is the realized cost of the implemented coupling. B_FS_CMC is the interpretable pathwise first-divergence residual-mask upper certificate. Both are coupling-specific upper routes for the fixed-suite Wasserstein target.

## CMC versus inverse-CDF CRN

- W8: mean ΔB_FS(CMC−CRN)=-0.576660; CMC lower in 0.898 of matched cells.
- W6: mean ΔB_FS(CMC−CRN)=-0.344238; CMC lower in 0.789 of matched cells.
- W4: mean ΔB_FS(CMC−CRN)=-0.074707; CMC lower in 0.500 of matched cells.

## Joint-coupling headroom

- Mean `h_CMC - max_i delta_i`: 0.060516.
- This is diagnostic headroom only; neither endpoint is asserted to equal joint transition TV.

## Prompt heterogeneity

- Maximum single-prompt aggregate B_FS share: 0.073903.
- No prompts were removed or replaced.

## Limitations

- One checkpoint, native D1, fixed 64-prompt suite, fake weight-only RTN.
- Exact-token Hamming is not semantic or language quality.
- CMC is not the globally optimal joint coupling.

## Exact archive contents and reproducibility

- All row-level raw shards are retained under `payload/raw/`.
- Model-free reproduction regenerates every table, plot, theorem check, gate, and report value.

## Gate

- **PASS_CMC_CERTIFIED_HORIZON_ALL_BITS**
- All bit widths have a simultaneous-95% B_FS horizon at epsilon 0.75, with a nontrivial W8/W6 epsilon-0.50 cell.
