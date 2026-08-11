# WP07D-LOCAL — SMDM Confirmatory Certificate and GSM8K Descriptive Panel

## Scope

Track A is a fixed 32-prompt second-model confirmatory result for the factorized official `origin` sampler. Track B is a separate descriptive GSM8K panel for the nonfactorized global top-k `greddy` sampler. No numerical estimand is pooled.

## Track A

| generation_length | severity | mean_D | mean_B_FS | UCB_D | UCB_B_FS |
| --- | --- | --- | --- | --- | --- |
| 16 | W4 | 0.71484375 | 0.94824219 | 0.94715139 | 1 |
| 64 | W4 | 0.76098633 | 0.99023438 | 0.99329396 | 1 |
| 16 | W6 | 0.44433594 | 0.76171875 | 0.67664357 | 0.99402639 |
| 64 | W6 | 0.57421875 | 0.91796875 | 0.80652639 | 1 |
| 16 | W8 | 0.20117188 | 0.36816406 | 0.43347951 | 0.6004717 |
| 64 | W8 | 0.36694336 | 0.66894531 | 0.599251 | 0.90125295 |

Gate: `PASS_SMDM_SECOND_MODEL_CONFIRMATORY`. H-A1=True; H-A2=True; H-A3=True; H-A4=True.

The Hoeffding calculation targets the fixed prompt-suite average over event-addressed coupling draws. It is not prompt-population generalization.

## Track B

| precision | rows | examples | seeds | exact_accuracy | extraction_success | generation_failure_rate | mean_output_length | mean_repetition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BF16 | 200 | 100 | 2 | 0.51 | 1 | 0 | 113.31 | 0.025683045 |
| W8 | 200 | 100 | 2 | 0.51 | 1 | 0 | 113.33 | 0.025731826 |
| W6 | 200 | 100 | 2 | 0.5 | 1 | 0 | 113.29 | 0.025787583 |
| W4 | 200 | 100 | 2 | 0.49 | 1 | 0 | 115.29 | 0.026996388 |

Gate: `PASS_GSM8K_DESCRIPTIVE_RELEVANCE`. These task outputs have no CMC, B_FS, or Wasserstein certificate.

## Overall

Gate: `PASS_LOCAL_SECOND_MODEL_PACKAGE`.

No 128-token generation and no external GPU were used.
