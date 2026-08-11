# TRCAL-1 Final Report

TRCAL-1 tests an independent algorithmic hypothesis; the negative METRIC-LOC-1 result did not guarantee this method. The frozen checkpoint, tokenizer, sampler, calibration grid, weights, held-out splits, and gates were not changed after held-out outcomes.

## Gates

- validity: `PASS_TRCAL_1_VALIDITY`
- surrogate bridge: `SURROGATE_BRIDGE_WEAK`
- method effect: `NO_TRANSPORT_CALIBRATION_EFFECT`
- overall: `PASS_TRCAL_1_NEGATIVE`
- external readiness: `NOT_READY_FOR_EXTERNAL_METHOD_CLAIM`

## W4 held-out task

| bit | method | example_count | exact_answer_accuracy | bf16_accuracy | answer_agreement_bf16 | mean_token_edit_distance |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | CLIP_HAZARD_ONLY | 512 | 0.564453 | 0.564453 | 0.884766 | 1.76562 |
| 4 | CLIP_MARGIN_FRONTIER | 512 | 0.568359 | 0.564453 | 0.884766 | 1.98242 |
| 4 | CLIP_RESIDUAL_ONLY | 512 | 0.566406 | 0.564453 | 0.880859 | 1.8125 |
| 4 | CLIP_TRANSPORT_SR | 512 | 0.566406 | 0.564453 | 0.892578 | 1.81641 |
| 4 | CLIP_TRANSPORT_SRH | 512 | 0.564453 | 0.564453 | 0.886719 | 1.7168 |
| 4 | CLIP_UNIFORM | 512 | 0.574219 | 0.564453 | 0.875 | 2.24219 |
| 4 | RTN_ABSMAX | 512 | 0.568359 | 0.564453 | 0.845703 | 2.46094 |

## Primary paired comparisons

| bit | method | comparator | example_count | accuracy_difference | bootstrap_lo | bootstrap_hi | one_sided_lower_95 | mcnemar_method_only_correct | mcnemar_comparator_only_correct | mcnemar_one_sided_p | holm_primary_p |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | CLIP_TRANSPORT_SR | RTN_ABSMAX | 512 | -0.00195312 | -0.0195312 | 0.0136719 | -0.015625 | 9 | 10 | 0.676197 | 1 |
| 4 | CLIP_TRANSPORT_SR | CLIP_UNIFORM | 512 | -0.0078125 | -0.0195312 | 0.00390625 | -0.0175781 | 3 | 7 | 0.945312 | 1 |

## W3 stress test

| bit | method | example_count | exact_answer_accuracy | bf16_accuracy | answer_agreement_bf16 | mean_token_edit_distance |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | CLIP_MARGIN_FRONTIER | 512 | 0.566406 | 0.564453 | 0.736328 | 5.77148 |
| 3 | CLIP_TRANSPORT_SR | 512 | 0.564453 | 0.564453 | 0.748047 | 4.72266 |
| 3 | CLIP_TRANSPORT_SRH | 512 | 0.564453 | 0.564453 | 0.748047 | 4.72266 |
| 3 | CLIP_UNIFORM | 512 | 0.566406 | 0.564453 | 0.742188 | 5.70312 |
| 3 | RTN_ABSMAX | 512 | 0.5 | 0.564453 | 0.628906 | 11.834 |

## Mechanism metrics

| bit | method | example_count | split_probability | mean_B_FS | terminal_hamming | mean_normalized_first_split_time | conditional_reagreement_rate | conditional_terminal_equality_rate | split_count | reagreement_count | final_reagreement_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | CLIP_MARGIN_FRONTIER | 512 | 1 | 0.995819 | 0.113434 | 0.0354309 | 0.0234375 | 0.0214844 | 512 | 12 | 11 |
| 3 | CLIP_TRANSPORT_SR | 512 | 1 | 0.992493 | 0.0998535 | 0.0387573 | 0.683594 | 0.630859 | 512 | 350 | 323 |
| 3 | CLIP_TRANSPORT_SRH | 512 | 1 | 0.992493 | 0.0998535 | 0.0387573 | 0.683594 | 0.630859 | 512 | 350 | 323 |
| 3 | CLIP_UNIFORM | 512 | 1 | 0.995911 | 0.112701 | 0.0353394 | 0.0175781 | 0.015625 | 512 | 9 | 8 |
| 3 | RTN_ABSMAX | 512 | 1 | 1 | 0.210419 | 0.03125 | 0 | 0 | 512 | 0 | 0 |
| 4 | CLIP_HAZARD_ONLY | 512 | 0.994141 | 0.883362 | 0.0384521 | 0.142682 | 0.980354 | 0.833006 | 509 | 499 | 424 |
| 4 | CLIP_MARGIN_FRONTIER | 512 | 1 | 0.875336 | 0.0404663 | 0.155914 | 0.972656 | 0.816406 | 512 | 498 | 418 |
| 4 | CLIP_RESIDUAL_ONLY | 512 | 0.996094 | 0.877563 | 0.0371399 | 0.150245 | 0.976471 | 0.821569 | 510 | 498 | 419 |
| 4 | CLIP_TRANSPORT_SR | 512 | 0.998047 | 0.887909 | 0.0380859 | 0.141603 | 0.978474 | 0.837573 | 511 | 500 | 428 |
| 4 | CLIP_TRANSPORT_SRH | 512 | 0.996094 | 0.890259 | 0.0364075 | 0.1375 | 0.980392 | 0.833333 | 510 | 500 | 425 |
| 4 | CLIP_UNIFORM | 512 | 1 | 0.875458 | 0.0472412 | 0.155792 | 0.982422 | 0.785156 | 512 | 503 | 402 |
| 4 | RTN_ABSMAX | 512 | 1 | 0.926117 | 0.0534058 | 0.105133 | 0.988281 | 0.769531 | 512 | 506 | 394 |

## Interpretation

The calibration objective is an empirical surrogate; no theorem-level claim that weighted reconstruction error controls split hazard is made. `MARGIN_FRONTIER` is an internal baseline, not FAIR-Calib. No activation-quantized, deployment-kernel, semantic-certificate, LLaDA/Dream, or universal task claim is permitted. No paper file was modified.
