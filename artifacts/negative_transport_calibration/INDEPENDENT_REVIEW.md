# TRCAL-1 Independent Review

## Disposition

- Validity gate: `PASS_TRCAL_1_VALIDITY`
- Method effect: `NO_TRANSPORT_CALIBRATION_EFFECT`
- Overall gate: `PASS_TRCAL_1_NEGATIVE`
- Surrogate bridge: `SURROGATE_BRIDGE_WEAK`
- External-method readiness: `NOT_READY_FOR_EXTERNAL_METHOD_CLAIM`

The experiment is technically valid and the primary Plan-A hypothesis is not
supported on the preregistered W4 held-out panel.

## Archive verification

| Archive | Size | SHA-256 | CRC |
|---|---:|---|---|
| Delivery | 1,636 | `70be4772523e6dfb180777ff7accd3fa40e7cc31ca0c75d6f0e9e724888e4a17` | PASS |
| Summary | 5,747,145 | `92465c19b70b4ab32dcf48d824d2da446a9de057c31924164f83fb087610462b` | PASS |
| Full | 157,495,758 | `6f0132c0c11a182a7cfce6a8951580027ddb99ceeb35cc1a18b82aa518faf440` | PASS |

- Full payload manifest: 15,017/15,017 valid.
- Summary scope manifest: 67/67 valid.
- Independent reaggregation of 6,144 held-out method rows matched all task and
  mechanism summaries (max numerical discrepancy approximately 1e-16).
- Duplicate/missing held-out primary keys: 0/0.
- Pathwise and copy-only violations: 0.

## Primary W4 task result

| Method | Accuracy | Agreement with BF16 | Token edit |
|---|---:|---:|---:|
| RTN absmax | 0.5684 | 0.8457 | 2.461 |
| Uniform clipping | **0.5742** | 0.8750 | 2.242 |
| Margin frontier | 0.5684 | 0.8848 | 1.982 |
| Residual only | 0.5664 | 0.8809 | 1.812 |
| Hazard only | 0.5645 | 0.8848 | 1.766 |
| Transport SR | 0.5664 | **0.8926** | 1.816 |
| Transport SRH | 0.5645 | 0.8867 | **1.717** |

Primary paired contrasts for Transport SR:

- versus RTN: -0.20 percentage points,
  95% bootstrap interval [-1.95, +1.37] pp, Holm p=1;
- versus uniform clipping: -0.78 pp,
  interval [-1.95, +0.39] pp, Holm p=1.

The method therefore does not satisfy the preregistered task-success gate.

## W4 mechanism trade-off

Transport SR versus RTN:

- terminal Hamming improves by 0.01532 absolute (~28.7% relative);
- answer agreement improves by 4.69 pp;
- B_FS improves by 0.03821 (~4.1% relative).

Transport SR versus uniform clipping:

- terminal Hamming improves by 0.00916 (~19.4% relative), with paired interval
  excluding zero;
- answer agreement rises by 1.76 pp, but its interval includes zero;
- B_FS becomes worse by 0.01245 (~1.4% relative), with interval excluding zero;
- first split occurs earlier.

Thus the method changes the error morphology and endpoint fidelity, but not
held-out answer accuracy; it also fails to improve the first-divergence
objective from which the weighting was motivated.

## W3 stress result

Transport SR accuracy is 0.5645 versus 0.5000 for RTN (+6.45 pp, significant),
but uniform and margin clipping are both 0.5664. Therefore the strong W3 gain
belongs to clipping calibration in general, not transport weighting.

Transport SR/SRH are byte-identical at W3. They produce:

- terminal Hamming 0.0999 versus 0.1127 for uniform and 0.2104 for RTN;
- conditional terminal equality 0.631 versus 0.0156 for uniform.

This is a real recovery/concentration effect, but it does not improve task
accuracy over the simple calibrated baselines.

## Surrogate bridge

State-level W4 normalized logit MSE:

- split ROC AUC: 0.545;
- bootstrap 95% interval: [0.479, 0.602];
- PR AUC: 0.192;
- correlation with first-divergence residual damage: 0.052.

The proposed reconstruction-error surrogate therefore has little predictive
power for split risk.

Across methods, the reported reconstruction-objective/B_FS rank relationship
is negative rather than positive. This supports a weak bridge, but the exact
method-level correlation should be treated cautiously: the final model-free
reaggregation labels a calibration-set uniform-moment objective as
"heldout", and reconstructs RTN's objective from a zero placeholder. The
state-level AUC alone already fails the preregistered bridge gate, so this
artifact issue does not change the weak-bridge conclusion.

## Why the weighting likely failed

- Hard survival masking zeros 92.3% of W4 states and 96.9% of W3 states.
  Effective calibration-state counts are ~313 (W4 SR) and 128 (W3 SR), versus
  4,096 for uniform weighting.
- W3 RTN diverges for every calibration prompt by the second reverse step;
  W4 RTN has no survivors after the early reverse region. The method therefore
  learns from a narrow early-state slice.
- The weights are off-policy: survival is measured under baseline RTN, while
  calibration changes the resulting trajectory distribution.
- Diagonal activation-weighted weight reconstruction error is not aligned with
  selector boundary crossing or persistent terminal damage.
- The clipping grid changes many row choices, but aggregate alpha
  distributions remain very similar across calibrated methods.

## Artifact qualifications

- Scientific data, manifests, hashes, and core statistics are consistent.
- Offline calibration wall time is not reliably reported in the final timing
  table because the final resumed run loaded cached risk/moment/alpha files.
- The `--calibration-only` and `--evaluation-only` CLI flags are parsed but not
  used to branch execution in the frozen runner.
- These are reproducibility/reporting issues, not causes of the negative task
  result.

## Paper decision

Do not add TRCAL-1 as a positive algorithmic contribution. It can be reported
as an appendix negative result:

> Survival–residual weighting changed clipping scales and improved some
> endpoint-fidelity metrics, but did not outperform uniform clipping or RTN on
> the preregistered W4 GSM8K accuracy endpoint; reconstruction error was a weak
> surrogate for split risk.

The result does not justify external large-model validation of this method.

A future Plan-A2 would require a genuinely different preregistered method:
soft/on-policy survival weighting, a direct margin/persistent-damage surrogate,
or module-selective calibration. Re-tuning the current weights or clipping grid
on these outcomes would be post hoc.
