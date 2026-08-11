# LOCAL-LIFT-TEMP-1R Final Report

## Scope

CPU-only model-free correction of the frozen LOCAL-LIFT-TEMP-1 release. No model, tokenizer, checkpoint, CUDA runtime, trajectory, Monte Carlo panel, or bootstrap draw was executed.

## Healing estimand correction

The former "re-agreement probability" was an all-trajectory incidence `P(split and later re-agreement)`, not `P(re-agreement | split)`. The corrected release reports exact counts, the incidence, and count-based conditional rates separately.

| temperature | precision | coupling_scheme | mean_D | mean_B_FS | split_probability | split_trajectory_count | reagreement_count | conditional_reagreement_rate | conditional_final_reagreement_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | W4 | LIFTED_CMC | 0.0664062 | 0.664062 | 0.875 | 28 | 24 | 0.857143 | 0.75 |
| 0 | W6 | LIFTED_CMC | 0.00195312 | 0.279297 | 0.4375 | 14 | 13 | 0.928571 | 0.928571 |
| 0 | W8 | LIFTED_CMC | 0.00195312 | 0.158203 | 0.28125 | 9 | 8 | 0.888889 | 0.888889 |
| 0.2 | W4 | LIFTED_CMC | 0.0664062 | 0.667969 | 0.90625 | 58 | 47 | 0.810345 | 0.758621 |
| 0.2 | W4 | PROPOSAL_CRN | 0.0644531 | 0.666016 | 0.890625 | 57 | 46 | 0.807018 | 0.754386 |
| 0.2 | W6 | LIFTED_CMC | 0 | 0.275391 | 0.40625 | 26 | 26 | 1 | 1 |
| 0.2 | W6 | PROPOSAL_CRN | 0.00195312 | 0.279297 | 0.4375 | 28 | 26 | 0.928571 | 0.928571 |
| 0.2 | W8 | LIFTED_CMC | 0.000976562 | 0.146484 | 0.25 | 16 | 15 | 0.9375 | 0.9375 |
| 0.2 | W8 | PROPOSAL_CRN | 0.00292969 | 0.167969 | 0.3125 | 20 | 17 | 0.85 | 0.85 |
| 0.5 | W4 | LIFTED_CMC | 0.0595703 | 0.658203 | 0.875 | 56 | 45 | 0.803571 | 0.714286 |
| 0.5 | W4 | PROPOSAL_CRN | 0.0673828 | 0.65918 | 0.859375 | 55 | 46 | 0.836364 | 0.727273 |
| 0.5 | W6 | LIFTED_CMC | 0.00390625 | 0.294922 | 0.46875 | 30 | 26 | 0.866667 | 0.866667 |
| 0.5 | W6 | PROPOSAL_CRN | 0.000976562 | 0.269531 | 0.40625 | 26 | 25 | 0.961538 | 0.961538 |
| 0.5 | W8 | LIFTED_CMC | 0.000976562 | 0.149414 | 0.25 | 16 | 15 | 0.9375 | 0.9375 |
| 0.5 | W8 | PROPOSAL_CRN | 0 | 0.154297 | 0.25 | 16 | 16 | 1 | 1 |
| 1 | W4 | LIFTED_CMC | 0.0595703 | 0.643555 | 0.8125 | 52 | 44 | 0.846154 | 0.730769 |
| 1 | W4 | PROPOSAL_CRN | 0.100586 | 0.683594 | 0.890625 | 57 | 47 | 0.824561 | 0.684211 |
| 1 | W6 | LIFTED_CMC | 0.0146484 | 0.268555 | 0.4375 | 28 | 23 | 0.821429 | 0.821429 |
| 1 | W6 | PROPOSAL_CRN | 0.00390625 | 0.269531 | 0.40625 | 26 | 25 | 0.961538 | 0.923077 |
| 1 | W8 | LIFTED_CMC | 0.000976562 | 0.115234 | 0.203125 | 13 | 12 | 0.923077 | 0.923077 |
| 1 | W8 | PROPOSAL_CRN | 0.0166016 | 0.158203 | 0.296875 | 19 | 15 | 0.789474 | 0.789474 |

At temperature 1.0 the count-based conditional re-agreement rates are:

| precision | coupling_scheme | split_trajectory_count | reagreement_count | conditional_reagreement_rate |
| --- | --- | --- | --- | --- |
| W4 | LIFTED_CMC | 52 | 44 | 0.846154 |
| W4 | PROPOSAL_CRN | 57 | 47 | 0.824561 |
| W6 | LIFTED_CMC | 28 | 23 | 0.821429 |
| W6 | PROPOSAL_CRN | 26 | 25 | 0.961538 |
| W8 | LIFTED_CMC | 13 | 12 | 0.923077 |
| W8 | PROPOSAL_CRN | 19 | 15 | 0.789474 |

W4 was 44/52 = 0.846 for LIFTED and 47/57 = 0.825 for CRN; W6 was 23/28 = 0.821 versus 25/26 = 0.962; W8 was 12/13 = 0.923 versus 15/19 = 0.789. These finite-grid directions are mixed. A larger all-trajectory incidence does not imply stronger conditional healing.

## Frozen scientific results

The interface gate remains `PASS_LOCAL_LIFT_TEMP_1_INTERFACE`; effect label remains `COUPLING_EFFECT_MIXED`; stochastic-stress label remains `PUSHFORWARD_STOCHASTICITY_INCREASED`; scientific overall gate remains `PASS_LOCAL_LIFT_TEMP_1_FULL`. All D, B_FS, split, gap, bootstrap, sign-test, Holm, channel, concentration, and K=120 values are unchanged.

## Correction gate

`PASS_LOCAL_LIFT_TEMP_1R_MODEL_FREE_CORRECTION`

No paper source was edited.
