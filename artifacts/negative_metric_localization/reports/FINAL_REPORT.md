# METRIC-LOC-1 final report

## Scope

This was a CPU-only, model-free reanalysis of frozen CERT-3, WP07C, WP07D, and LOCAL-LIFT outputs. No model forward, generation, trajectory, Monte Carlo experiment, GPU allocation, calibration, or paper edit was performed.

## Validity

- Raw terminal reconstruction: `True`
- Hamming maximum frozen-value discrepancy: `0`
- Metric/theorem/witness/statistical validity: `True`

## Metric saturation

```text
               metric        coupling severity  mean_fp_q  mean_fp_fp_independent  saturation_ratio  headroom  quantization_minus_intrinsic  prompt_count
              hamming             CMC       W8   0.234863                0.976562          0.240500  0.759500                     -0.741699            64
              hamming             CMC       W6   0.404297                0.976562          0.414000  0.586000                     -0.572266            64
              hamming             CMC       W4   0.767090                0.976562          0.785500  0.214500                     -0.209473            64
              hamming inverse_CDF_CRN       W8   0.914551                0.976562          0.936500  0.063500                     -0.062012            64
              hamming inverse_CDF_CRN       W6   0.899902                0.976562          0.921500  0.078500                     -0.076660            64
              hamming inverse_CDF_CRN       W4   0.957520                0.976562          0.980500  0.019500                     -0.019043            64
     embedding_hybrid             CMC       W8   0.161188                0.677068          0.238068  0.761932                     -0.515879            64
     embedding_hybrid             CMC       W6   0.278149                0.677068          0.410815  0.589185                     -0.398918            64
     embedding_hybrid             CMC       W4   0.529854                0.677068          0.782572  0.217428                     -0.147214            64
     embedding_hybrid inverse_CDF_CRN       W8   0.623487                0.677068          0.920863  0.079137                     -0.053581            64
     embedding_hybrid inverse_CDF_CRN       W6   0.611828                0.677068          0.903644  0.096356                     -0.065239            64
     embedding_hybrid inverse_CDF_CRN       W4   0.654578                0.677068          0.966783  0.033217                     -0.022490            64
tokenizer_byte_hybrid             CMC       W8   0.016560                0.069724          0.237513  0.762487                     -0.053164            64
tokenizer_byte_hybrid             CMC       W6   0.028631                0.069724          0.410641  0.589359                     -0.041092            64
tokenizer_byte_hybrid             CMC       W4   0.054369                0.069724          0.779773  0.220227                     -0.015355            64
tokenizer_byte_hybrid inverse_CDF_CRN       W8   0.063858                0.069724          0.915873  0.084127                     -0.005866            64
tokenizer_byte_hybrid inverse_CDF_CRN       W6   0.062789                0.069724          0.900535  0.099465                     -0.006935            64
tokenizer_byte_hybrid inverse_CDF_CRN       W4   0.066463                0.069724          0.953235  0.046765                     -0.003261            64
```

## Bit ordering

```text
          panel          coupling                metric  mean_W8  mean_W6  mean_W4  aggregate_ordering_pass  prompt_or_example_ordering_rate  cluster_count  temperature
          CERT3               CMC               hamming 0.234863 0.404297 0.767090                     True                         0.796875             64          NaN
          CERT3   inverse_CDF_CRN               hamming 0.914551 0.899902 0.957520                    False                         0.312500             64          NaN
          WP07C               CMC               hamming 0.283203 0.438477 0.799561                     True                         0.679688            128          NaN
    WP07D_GSM8K BF16_vs_quantized               hamming 0.008503 0.013516 0.049190                     True                         0.930000            100          NaN
LOCAL_LIFT_TEMP        LIFTED_CMC               hamming 0.000977 0.000000 0.066406                    False                         0.968750             32          0.2
LOCAL_LIFT_TEMP      PROPOSAL_CRN               hamming 0.002930 0.001953 0.064453                    False                         0.968750             32          0.2
LOCAL_LIFT_TEMP        LIFTED_CMC               hamming 0.000977 0.003906 0.059570                     True                         1.000000             32          0.5
LOCAL_LIFT_TEMP      PROPOSAL_CRN               hamming 0.000000 0.000977 0.067383                     True                         1.000000             32          0.5
LOCAL_LIFT_TEMP        LIFTED_CMC               hamming 0.000977 0.014648 0.059570                     True                         0.843750             32          1.0
LOCAL_LIFT_TEMP      PROPOSAL_CRN               hamming 0.016602 0.003906 0.100586                    False                         0.812500             32          1.0
          CERT3               CMC      embedding_hybrid 0.161188 0.278149 0.529854                     True                         0.796875             64          NaN
          CERT3   inverse_CDF_CRN      embedding_hybrid 0.623487 0.611828 0.654578                    False                         0.218750             64          NaN
          WP07C               CMC      embedding_hybrid 0.195536 0.302321 0.555709                     True                         0.656250            128          NaN
    WP07D_GSM8K BF16_vs_quantized      embedding_hybrid 0.006335 0.010279 0.040216                     True                         0.930000            100          NaN
LOCAL_LIFT_TEMP        LIFTED_CMC      embedding_hybrid 0.000590 0.000000 0.045283                    False                         0.968750             32          0.2
LOCAL_LIFT_TEMP      PROPOSAL_CRN      embedding_hybrid 0.001987 0.001399 0.044111                    False                         0.968750             32          0.2
LOCAL_LIFT_TEMP        LIFTED_CMC      embedding_hybrid 0.000692 0.002495 0.040373                     True                         0.968750             32          0.5
LOCAL_LIFT_TEMP      PROPOSAL_CRN      embedding_hybrid 0.000000 0.000569 0.045570                     True                         1.000000             32          0.5
LOCAL_LIFT_TEMP        LIFTED_CMC      embedding_hybrid 0.000744 0.009831 0.040701                     True                         0.843750             32          1.0
LOCAL_LIFT_TEMP      PROPOSAL_CRN      embedding_hybrid 0.011150 0.002832 0.069274                    False                         0.812500             32          1.0
          CERT3               CMC tokenizer_byte_hybrid 0.016560 0.028631 0.054369                     True                         0.796875             64          NaN
          CERT3   inverse_CDF_CRN tokenizer_byte_hybrid 0.063858 0.062789 0.066463                    False                         0.187500             64          NaN
          WP07C               CMC tokenizer_byte_hybrid 0.019244 0.030107 0.054523                     True                         0.640625            128          NaN
    WP07D_GSM8K BF16_vs_quantized tokenizer_byte_hybrid 0.002131 0.004015 0.022124                     True                         0.940000            100          NaN
LOCAL_LIFT_TEMP        LIFTED_CMC tokenizer_byte_hybrid 0.000083 0.000000 0.006310                    False                         0.968750             32          0.2
LOCAL_LIFT_TEMP      PROPOSAL_CRN tokenizer_byte_hybrid 0.000250 0.000166 0.006109                    False                         0.968750             32          0.2
LOCAL_LIFT_TEMP        LIFTED_CMC tokenizer_byte_hybrid 0.000083 0.000333 0.005727                     True                         1.000000             32          0.5
LOCAL_LIFT_TEMP      PROPOSAL_CRN tokenizer_byte_hybrid 0.000000 0.000083 0.006255                     True                         1.000000             32          0.5
LOCAL_LIFT_TEMP        LIFTED_CMC tokenizer_byte_hybrid 0.000083 0.001591 0.005452                     True                         0.843750             32          1.0
LOCAL_LIFT_TEMP      PROPOSAL_CRN tokenizer_byte_hybrid 0.001620 0.000608 0.009840                    False                         0.812500             32          1.0
```

## GSM8K descriptive task relevance

```text
               metric                          statistic  estimate   ci_low  ci_high  metric_minus_hamming  metric_minus_hamming_ci_low  metric_minus_hamming_ci_high
              hamming            answer_disagreement_auc  0.984451 0.966543 0.997188              0.000000                     0.000000                      0.000000
              hamming       correctness_disagreement_auc  0.957288 0.926421 0.982935              0.000000                     0.000000                      0.000000
              hamming                  mean_answer_agree  0.004792 0.000929 0.010122              0.000000                     0.000000                      0.000000
              hamming               mean_answer_disagree  0.177009 0.133304 0.224099              0.000000                     0.000000                      0.000000
              hamming         spearman_frozen_token_edit  0.998337 0.995254 0.999753              0.000000                     0.000000                      0.000000
              hamming point_biserial_answer_disagreement  0.736240 0.599582 0.855863              0.000000                     0.000000                      0.000000
     embedding_hybrid            answer_disagreement_auc  0.985586 0.968930 0.997363              0.001135                     0.000000                      0.003365
     embedding_hybrid       correctness_disagreement_auc  0.953220 0.921355 0.979732             -0.004068                    -0.015101                      0.006711
     embedding_hybrid                  mean_answer_agree  0.003550 0.000654 0.007516             -0.001243                    -0.002604                     -0.000260
     embedding_hybrid               mean_answer_disagree  0.143491 0.107569 0.182355             -0.033518                    -0.045141                     -0.023679
     embedding_hybrid         spearman_frozen_token_edit  0.998453 0.995710 0.999709              0.000116                    -0.000386                      0.000766
     embedding_hybrid point_biserial_answer_disagreement  0.741811 0.613019 0.854963              0.005572                    -0.012887                      0.022022
tokenizer_byte_hybrid            answer_disagreement_auc  0.987629 0.973942 0.997111              0.003178                    -0.002672                      0.012072
tokenizer_byte_hybrid       correctness_disagreement_auc  0.942373 0.905405 0.974237             -0.014915                    -0.043390                      0.012669
tokenizer_byte_hybrid                  mean_answer_agree  0.001095 0.000091 0.002369             -0.003698                    -0.007906                     -0.000735
tokenizer_byte_hybrid               mean_answer_disagree  0.076809 0.051784 0.105910             -0.100201                    -0.134377                     -0.071212
tokenizer_byte_hybrid         spearman_frozen_token_edit  0.998463 0.995949 0.999676              0.000126                    -0.001952                      0.002299
tokenizer_byte_hybrid point_biserial_answer_disagreement  0.697009 0.592371 0.807234             -0.039231                    -0.121988                      0.063168
```

These values are descriptive relevance diagnostics, not semantic or task-quality certificates.

## Terminal transport localization

```text
severity                metric  evaluation_prompt_count  witness_estimate  empirical_bernstein_LCB  bootstrap_ci_low  bootstrap_ci_high  direct_CMC_mean  direct_Hoeffding_radius  direct_CMC_UCB  interval_width  localization_fraction  LCB_positive  ordered_pass                                                                                                            estimand_note
      W8               hamming                      128         -0.000488                      0.0         -0.009766           0.009033         0.283203                 0.142425        0.425629        0.425629                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W8      embedding_hybrid                      128          0.000833                      0.0         -0.004406           0.006112         0.195536                 0.142425        0.337961        0.337961                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W8 tokenizer_byte_hybrid                      128         -0.000077                      0.0         -0.000585           0.000458         0.019244                 0.142425        0.161669        0.161669                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W6               hamming                      128         -0.000732                      0.0         -0.010742           0.009521         0.438477                 0.142425        0.580902        0.580902                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W6      embedding_hybrid                      128          0.000430                      0.0         -0.005706           0.006717         0.302321                 0.142425        0.444747        0.444747                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W6 tokenizer_byte_hybrid                      128         -0.000128                      0.0         -0.000707           0.000453         0.030107                 0.142425        0.172532        0.172532                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W4               hamming                      128          0.051758                      0.0          0.034180           0.069336         0.799561                 0.142425        0.941986        0.941986                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W4      embedding_hybrid                      128          0.028869                      0.0          0.018283           0.039279         0.555709                 0.142425        0.698135        0.698135                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
      W4 tokenizer_byte_hybrid                      128          0.003605                      0.0          0.002445           0.004776         0.054523                 0.142425        0.196948        0.196948                    0.0         False          True LCB bounds prompt-mixture W; UCB bounds average prompt-conditional W via direct CMC; mixture W <= average conditional W.
```

The witness LCB concerns prompt-mixture terminal laws. The direct CMC UCB concerns the average prompt-conditional cost. The ordering is `LCB_witness <= W(prompt mixture) <= average prompt-conditional W <= UCB_direct_CMC`.

## Gates

- Metric: `METRIC_NOT_PROMISING`
- Lower bound: `LOWER_BOUND_VACUOUS`
- Overall: `PASS_METRIC_LOC_1_NEGATIVE`
- Plan-A readiness: `NOT_READY`

## Limits

Embedding distance is not semantic equivalence, the plug-in coordinate OT is not a certified population lower bound, CMC is not joint maximal, and no arbitrary-prompt or large-model claim follows.
