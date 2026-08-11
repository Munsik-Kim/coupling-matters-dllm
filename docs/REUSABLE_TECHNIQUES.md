# Reusable techniques

## A. First divergence and residual unresolved mass

**Problem.** Control downstream distortion after two coupled chains first split. **Formal object.** First split `tau` and residual MASK mass `R(S_tau)`. **Proved.** Under monotone copy-only assumptions, endpoint normalized Hamming is at most residual mass. **Implementation.** `theory/first_divergence.md` and `tools/split_damage_analysis/`. **Observed.** Tighter couplings delayed first split and reduced certificate cost, but bounds could saturate. **Limit.** Remasking/editing invalidates the simple theorem. **Potential reuse / not established in this report.** Other irreversible iterative inference systems.

## B. Hybrid and propagated-error decomposition

**Problem.** Attribute a global endpoint gap to local kernel replacements. **Formal object.** A canonical sequence of FP/Q hybrid chains and adjacent distances. **Proved.** Telescoping for the specified hybrid construction; not for arbitrary couplings. **Implementation.** report proofs and compact CERT-3/CERT-1 evidence. **Observed.** Raw sums were often loose. **Potential reuse / not established in this report.** Layerwise or stepwise approximate inference audits.

## C. Multiplicity versus cancellation/healing

**Problem.** Explain slack between accumulated coordinate changes and endpoint difference. **Formal object.** per-coordinate change count, union event, and endpoint event. **Proved.** Exact multiplicity/cancellation gap identities. **Implementation.** `tools/split_damage_analysis/test_certificate_theory.py`. **Observed.** Healing/cancellation can materially separate incidence from endpoint damage. **Limit.** It is attribution unless paired with a predictive bound.

## D. Split incidence versus conditional damage

**Problem.** Avoid conflating how often a local mismatch occurs with damage after it occurs. **Formal object.** `P(split)` and `E[D | split]`. **Established.** Exact expectation decomposition; empirical directions remain model/sampler specific. **Implementation.** compact propagation/temperature artifacts and `minimal_healing_check.py`. **Limit.** Conditional rates use split counts, never all-trajectory denominators.

## E. Event-addressed RNG

**Problem.** Branch-dependent control flow can desynchronize ordinary PRNG streams. **Formal object.** deterministic uniforms keyed by experiment namespace, state identity, global step, coordinate, and event type. **Established.** An implementation invariant audited by rerun and branch-order checks. **Implementation.** `tools/event_addressed_rng/`. **Limit.** Stable keys do not imply optimal coupling.

## F. Coupling audit and marginal validity

**Problem.** An attractive paired result is invalid if either branch marginal is wrong. **Formal object.** categorical marginal error, mismatch-versus-TV, diagonal preservation, and product split hazard. **Established.** Algebraic contracts plus finite-sample tests. **Implementation.** `tools/coupling_audit/`. **Potential reuse / not established in this report.** Any paired stochastic-kernel evaluation with reconstructable marginals.

## G. Prompt-block finite-sample aggregation

**Problem.** Prevent token/step pseudoreplication. **Formal object.** fixed-suite or prompt-level bounded averages and prefix-closed horizons. **Established.** The declared Hoeffding family for its stated target. **Implementation.** `tools/split_damage_analysis/test_statistical_certificate.py`. **Limit.** Fixed-suite confidence does not imply unseen-prompt generalization.

## H. Raw-to-claim clean-room audit

**Problem.** Detect correlated analysis and reporting errors. **Formal object.** blinded independent aggregation, hash freeze, second implementation, and theorem-to-raw traceability. **Implementation.** `tools/raw_to_claim_audit/` and compact audit artifacts. **Observed.** It exposed wording/provenance qualifications while preserving validated primary calculations. **Potential reuse / not established in this report.** Other computational research releases.
