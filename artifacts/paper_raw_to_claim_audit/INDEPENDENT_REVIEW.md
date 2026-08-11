# Independent review of PAPER-V0.9 raw-to-claim audit

## Independent disposition

- Archive integrity: PASS
- Core empirical recomputation: PASS WITH REQUIRED PAPER PATCHES
- Full paper-wide raw-to-claim completeness: PARTIAL
- Candidate patch usability: FAIL (not a valid unified diff)
- Recommended practical status: SCIENTIFIC CORE PASSES; APPLY CORRECTIONS AND COMPLETE FOCUSED AUDIT GAPS

## Confirmed audit corrections

1. WP07C trajectory split probabilities are 0.578125 / 0.8359375 / 1.0. The manuscript's 0.8046875 / 0.96875 / 1.0 values are prompt-block any-split fractions.
2. WP07C W8 conditional trajectory damage is 0.4898648649, not 0.3519417476. The old 0.352 ratio mixed a trajectory-mean numerator with a prompt-block denominator.
3. 0.98779296875 is from a separate 32-token CERT-0 audit. The matched 16-token CERT-3 FP-reference mean is 0.9765625.
4. 24,864 is a count of recorded pathwise trajectory-horizon checks, not independent statistical observations.

## Core results that survive

- CERT-3 direct CMC means and UCBs.
- Prompt-population direct means/UCBs and absolute horizons.
- 24,864 = 8,064 + 6,048 + 6,048 + 3,072 + 1,632, with zero pathwise violations.
- WP05A flip rates and 127/128 severity ordering.
- Propagation incidence/damage/region values.
- WP07B point estimates and fixed-effect slopes.
- WP07D SMDM/GSM8K point estimates and corrected McNemar values.
- LOCAL-LIFT main channel fractions, direct/first-divergence values, and raw counts.

## Audit implementation limitations

1. The stated 451/566 RAW_VERIFIED coverage is heuristic. Claim statuses are assigned by claim class and keyword routing, not by a per-claim raw-source/value/difference comparison.
2. The theorem gate checks proof-pointer presence, not proof correctness or whether the main statement is stronger than the proof; `statement_stronger_than_proof` is hard-coded false.
3. The figure gate marks `data_arrays_match=true` by construction and does not numerically extract and compare the manuscript source figure data.
4. The package verifier reports zero internal manifest entries checked due a schema-parsing mismatch, although independent archive verification confirms the delivered audit ZIPs themselves are internally valid.
5. Only six primitive tests were run.
6. Several immutable review archives were absent; raw run directories were used, and most run-to-commit heads are `NOT_RECORDED_AT_STANDARD_PATH`.
7. WP05A AUROC is a frozen-derived fallback, not an independent raw refit.
8. WP07B bootstrap confidence intervals were not independently recomputed.
9. Relative-certificate failure is asserted rather than independently recalculated in the audit code.
10. The candidate patch contains bare `@@` hunk headers and fails `patch --dry-run` as an invalid unified diff.

## Additional v0.9 fixes not present in the audit patch

- `greddy` -> `greedy` in two locations.
- State explicitly that K=92 gives radius 0.342726 for LOCAL-LIFT.
- Add 1,632 = 288*5 + 32*6.
- Disambiguate “monotonicity violation” as copy-only state-monotonicity violation.
- Disclose the small W8 > W6 terminal-D inversion.
- Harmonize 6.2%/6.3% rounding in figure/table text.
- Move or remove the length-16 task-floor rows.
- Reduce small-sample channel percentages and the 6.1x ratio in the abstract, or attach uncertainty in the body.

## Recommended next action

Do not apply the delivered candidate patch directly. Create v0.10 from v0.9 using a valid patch that combines:

- the four audit-confirmed corrections;
- the additional known wording/notation corrections;
- conference-length compression;
- later temperature-extension results only after their separate preregistered run.

Before calling the audit fully complete, perform a focused audit R1 for:

- exact claim-to-raw ledger for all load-bearing main-paper claims;
- WP07B bootstrap CIs;
- relative-certificate calculations;
- genuine theorem statement/proof scope review;
- genuine figure-data comparison;
- immutable run-to-commit provenance where available.
