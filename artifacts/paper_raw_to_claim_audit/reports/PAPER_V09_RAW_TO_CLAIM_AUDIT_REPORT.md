# Paper v0.9 Raw-to-Claim Audit

## Outcome

- Overall: `PASS_PAPER_V09_WITH_CANDIDATE_PATCHES`
- Theory: `PASS_THEORY_PROOF_MAP`
- Empirical: `PASS_RAW_REAGGREGATION_WITH_PATCHES`
- Figures: `PASS_FIGURE_WITH_RENDER_ONLY_DIFFERENCES`
- Counts: `PASS_COUNT_RECONCILIATION`
- Model/GPU execution: none

## Primary findings

- Paper package and PDF hashes: PASS.
- Claim inventory: 566 claims; 451 raw-verified (79.7%).
- CERT-3 full direct means: W8 0.234863, W6 0.404297, W4 0.767090.
- Prompt-population full direct means: W8 0.283203, W6 0.438477, W4 0.799561.
- Pathwise count: 24864 = 8064 + 6048 + 6048 + 3072 + 1632; violations 0.
- Primary certificate UCBs, horizons, and pathwise checks reproduce. Two secondary WP07C diagnostics require correction: prompt-block any-split was labeled as trajectory split probability, and a mixed-denominator ratio was called conditional damage.
- Candidate patch also clarifies the 24,864 check count and identifies the separate 32-token source of the 0.9878 intrinsic-diversity number.

## Qualification

A fresh LaTeX compile and PDF raster QA could not be performed because the protected environment has no TeX engine or PDF renderer. The supplied package's PDF, font/preflight records, source, and internal hashes were verified; all five empirical source PNGs were visually inspected separately.
