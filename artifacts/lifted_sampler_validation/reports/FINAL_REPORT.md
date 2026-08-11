# LOCAL-LIFT-1R final report

## Result

`PASS_LOCAL_LIFT_1R_CORRECTED_RELEASE`. Independent aggregation: `PASS_INDEPENDENT_REAGGREGATION`. Reachable-state audit: `PASS_REACHABLE_STATE_PUSHFORWARD_AUDIT`.

## Independent source reconstruction

The immutable 320 predecessor checkpoint JSON files were scanned directly. Reconstructed counts were: {'trajectory': 320, 'endpoints': 1632, 'steps': 6656, 'same_state_events': 5507, 'proposal_positions': 204800, 'rng_events': 416014, 'task_output': 320}. Load-bearing original-versus-independent discrepancies: 0.

## Corrected channel attribution - length 16

| generation_length | precision | temperature | trajectory_count | split_trajectory_count | no_split_count | proposal_first_count | proposal_first_fraction | policy_first_count | policy_first_fraction | simultaneous_proposal_policy_count | simultaneous_proposal_policy_fraction | mean_terminal_damage_proposal | mean_terminal_damage_policy | mean_terminal_damage_simultaneous | median_first_split_step | mean_normalized_first_split_progress | reagreement_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | W4 | 0.0 | 32 | 28 | 4 | 0 | 0.0 | 19 | 0.6785714285714286 | 9 | 0.32142857142857145 | nan | 0.02631578947368421 | 0.18055555555555555 | 6.0 | 0.36607142857142855 | 0.8571428571428571 |
| 16 | W6 | 0.0 | 32 | 14 | 18 | 1 | 0.07142857142857142 | 12 | 0.8571428571428571 | 1 | 0.07142857142857142 | 0.0625 | 0.0 | 0.0 | 8.0 | 0.48660714285714285 | 0.9285714285714286 |
| 16 | W8 | 0.0 | 32 | 9 | 23 | 1 | 0.1111111111111111 | 7 | 0.7777777777777778 | 1 | 0.1111111111111111 | 0.0625 | 0.0 | 0.0 | 9.0 | 0.5625 | 0.8888888888888888 |
| 16 | W4 | 0.2 | 64 | 58 | 6 | 1 | 0.017241379310344827 | 34 | 0.5862068965517241 | 23 | 0.39655172413793105 | 0.0625 | 0.02389705882352941 | 0.14673913043478262 | 6.0 | 0.3879310344827586 | 0.8103448275862069 |
| 16 | W6 | 0.2 | 64 | 26 | 38 | 0 | 0.0 | 22 | 0.8461538461538461 | 4 | 0.15384615384615385 | nan | 0.0 | 0.0 | 7.0 | 0.44711538461538464 | 1.0 |
| 16 | W8 | 0.2 | 64 | 16 | 48 | 1 | 0.0625 | 14 | 0.875 | 1 | 0.0625 | 0.0625 | 0.0 | 0.0 | 9.0 | 0.5390625 | 0.9375 |

## Corrected channel attribution - length 64 sensitivity

| generation_length | precision | temperature | trajectory_count | split_trajectory_count | no_split_count | proposal_first_count | proposal_first_fraction | policy_first_count | policy_first_fraction | simultaneous_proposal_policy_count | simultaneous_proposal_policy_fraction | mean_terminal_damage_proposal | mean_terminal_damage_policy | mean_terminal_damage_simultaneous | median_first_split_step | mean_normalized_first_split_progress | reagreement_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 64 | W4 | 0.2 | 16 | 16 | 0 | 0 | 0.0 | 2 | 0.125 | 14 | 0.875 | nan | 0.0 | 0.11160714285714286 | 5.5 | 0.111328125 | 1.0 |
| 64 | W8 | 0.2 | 16 | 14 | 2 | 0 | 0.0 | 12 | 0.8571428571428571 | 2 | 0.14285714285714285 | nan | 0.0 | 0.0 | 16.0 | 0.33482142857142855 | 1.0 |

## Claim scope

The proposal-level lifted interface, its pushed-forward marginals, the monotone first-divergence inequality, and the bounded-functional inequality are supported within the pinned fixed suite and finite preregistered audits. Policy-first divergence dominates W8/W6 length-16 first splits. The first-divergence route is valid but loose, and current GSM8K UCBs do not provide a useful accuracy certificate.

This is not output-level joint maximality, terminal/path optimality, a semantic certificate, a prompt-population guarantee, or a deployment-kernel result. Length-64 evidence is sensitivity-only, and the 30 reachable states are a finite implementation audit.
