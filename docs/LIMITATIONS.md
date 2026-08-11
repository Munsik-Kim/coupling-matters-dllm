# Limitations

- The primary metric is normalized exact-token Hamming; it is auditable and
  theorem-aligned but is not a semantic metric.
- Reported coupling costs are upper bounds on terminal Wasserstein distance;
  the tested held-out lower-bound procedure was formally vacuous.
- Quantization is simulated matrix-weight, per-output-channel RTN with
  reference-precision activations, not a production kernel benchmark.
- The largest model is a 1.14B SMDM checkpoint; the archive does not establish
  LLaDA, Dream, activation-quantized, or arbitrary-prompt generalization.
- Proposal-level optimality does not imply output-level, terminal, or path
  optimality.
- Recorded pathwise checks are dependent repeated checks, not independent
  statistical observations.
