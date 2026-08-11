# LOCAL-LIFT-TEMP-1R Independent Verification

## Disposition

- Scientific correction gate: `PASS_LOCAL_LIFT_TEMP_1R_MODEL_FREE_CORRECTION`
- Preserved scientific gates:
  - interface: `PASS_LOCAL_LIFT_TEMP_1_INTERFACE`
  - effect: `COUPLING_EFFECT_MIXED`
  - stochastic stress: `PUSHFORWARD_STOCHASTICITY_INCREASED`
  - original overall: `PASS_LOCAL_LIFT_TEMP_1_FULL`
- Independent disposition:
  `PASS_WITH_MINOR_ARTIFACT_METADATA_FIX`

## Archive identity

| Archive | Size (bytes) | SHA-256 | CRC |
|---|---:|---|---|
| Summary | 499,885 | `d5f709a44522968b6d4ced8c5ba48f355171b85399d5d642eb9c578a8e73b924` | PASS |
| Full | 516,230 | `11a2673ea1301e944a9ba7fa20759dfdc9af49deb4abaac5742fbf1da9566d69` | PASS |
| Delivery | 2,142 | `7d0426cfa60c56865a0041d91cb66cd36bb9471345584c1d5c9174b2094d8246` | PASS |

Internal package verification:

- Full: 59 manifest payload files, zero missing/extra/hash/size/SHA-list failures.
- Summary: 47 manifest payload files, zero missing/extra/hash/size/SHA-list failures.
- Delivery: 3 manifest payload files, zero missing/extra/hash/size/SHA-list failures.

## Raw reconstruction

The correction independently parsed the immutable source archives:

- new `LOCAL-LIFT-TEMP-1`: 960 checkpoint JSON files;
- predecessor `LOCAL-LIFT-1`: 320 checkpoint JSON files;
- predecessor length-16 T=0/T=0.2 rows used for the merged table: 288;
- combined relevant rows: 1,248;
- duplicate primary keys: 0.

An independent second implementation matched all exact counts and rates.

## Healing estimand correction

The old columns were all-trajectory incidences:

- `P(split and later re-agreement)`;
- `P(split and terminal equality)`.

The corrected release separately reports:

- all-trajectory incidence;
- `P(re-agreement at least once | split)`;
- `P(terminal equality | split)`.

All 21 temperature/bit/coupling cells agree exactly with raw checkpoint JSON.

### Temperature 1.0 conditional healing

| Bit | Coupling | Split | Re-agree | P(re-agree | split) | P(terminal equality | split) |
|---|---|---:|---:|---:|---:|
| W4 | LIFTED_CMC | 52 | 44 | 0.846154 | 0.730769 |
| W4 | PROPOSAL_CRN | 57 | 47 | 0.824561 | 0.684211 |
| W6 | LIFTED_CMC | 28 | 23 | 0.821429 | 0.821429 |
| W6 | PROPOSAL_CRN | 26 | 25 | 0.961538 | 0.923077 |
| W8 | LIFTED_CMC | 13 | 12 | 0.923077 | 0.923077 |
| W8 | PROPOSAL_CRN | 19 | 15 | 0.789474 | 0.789474 |

The direction remains mixed. Healing does not establish universal dominance of either coupling.

## Frozen predecessor backfill

Six formerly blank LIFTED_CMC cells were reconstructed directly from
`LOCAL_LIFT_1` checkpoint JSON:

- T=0: W4/W6/W8;
- T=0.2: W4/W6/W8.

Completed cells: 6/6. Remaining conditional-healing cells with a positive
split denominator and missing values: 0.

## Scientific no-change check

For the corrected main table, the following ten non-healing fields match the
source table exactly, with maximum absolute difference 0:

- prompt blocks;
- D mean and interval;
- B_FS mean and interval;
- split and no-split probability;
- mean first-split step.

The temperature evidence memo also preserves the source T=1 macro gap and
bootstrap interval exactly.

Qualification: the correction release references other frozen TEMP-1 outputs
(gap, channel, concentration, certificate, and audit files) by immutable source
archive/hash; it does not constitute a new full reaggregation of those outputs.
That is appropriate for this narrowly scoped metadata/report correction, but
the phrase “all scientific outputs re-audited” should not be used.

## Reports and figures

Required reports now exist:

- `PAPER_ROLE_DECISION.md`;
- `ALLOWED_AND_PROHIBITED_TEMPERATURE_CLAIMS.md`;
- result-specific temperature evidence memo;
- provenance correction;
- correction report.

The corrected figures distinguish all-trajectory incidence from conditional
healing and use explicit conditional labels.

## Provenance

- Clean preflight HEAD: `0078b704ed5a79e3a2bdfdbaab676e0930b66ed7`
- Final correction commit:
  `869f3f83c52c3532390c7c1eab16027ec32d95a6`
- Final branch: `main`
- Final working tree: clean
- Tests: 35 passed, 7 skipped, 0 failed
- Model execution: false
- GPU execution: false

## Minor artifact metadata issue

`figures/PLOTTED_DATA_SHA256.json` contains seven entries and incorrectly
includes a hash for itself. The six actual figure/PDF/CSV entries all match;
only the self-entry is stale, because the file changed when it was written.

This does not affect:

- scientific values;
- figure data;
- ZIP CRC;
- package `FILE_MANIFEST.json`;
- package SHA lists.

Recommended fix: exclude `PLOTTED_DATA_SHA256.json` from its own hash ledger
and regenerate the JSON plus summary/full/delivery archives. No model or GPU
execution is required.

The summary archive uses `SUMMARY_SHA256SUMS.txt` rather than the standard
`SHA256SUMS.txt`. It is internally consistent and fully verified, so this is a
naming convention rather than a correctness failure. It can be standardized
in the same model-free repackaging step.

## Paper role

The supplied decision is supported:

`MAIN_TEXT_COMPACT_MIXED_EFFECT`

Use one compact main-text result showing that coupling dependence survives
outside the deterministic limit, while no universal coupling ordering is
observed. Put per-bit healing, channel, and concentration details in the
appendix.

## Next action

1. Apply the tiny plotted-data-ledger fix; optionally standardize the summary
   SHA-list filename.
2. Freeze the corrected TEMP-1R release.
3. Apply the already frozen v0.9 factual corrections.
4. Integrate the mixed temperature result into a compressed conference-core
   v0.10.
5. No additional local GPU experiment is required.
