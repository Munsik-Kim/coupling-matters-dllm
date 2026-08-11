# Independent statistical theorem audit

The declared target is the equally weighted average over the fixed 64-prompt
suite of each prompt's coupling-draw expectation.  For each CMC cell there
are four bounded observations per prompt, hence

`(1/256) sum_(prompt,seed) X = (1/64) sum_prompt [(1/4) sum_seed X]`.

Hoeffding's inequality for independent, bounded, not-necessarily-identically
distributed observations therefore applies with `n=256`, provided the four
event-addressed pseudorandom streams for every prompt are treated as
independent draws.  Equal prompt replication preserves equal prompt weights.
The theorem does not confer unseen-prompt generalization.

Reuse of numeric seed identifiers across cells creates dependence between
different simultaneous statements but does not invalidate the Bonferroni
union bound: no cross-statement independence is required.  Within-cell stream
independence rests on the archived semantic event namespaces and the usual
pseudorandom-hash idealization, not on physical randomness.

The two disjoint FP seed pairs yield `n=128` bounded Delta-ref observations.
They reuse prompt identities but not trajectory seeds within a pair; the same
fixed-suite interpretation applies.

- K: 49
- family delta: 0.05
- radius n=256: 0.11598383989389408
- radius n=128: 0.16402591939405464
- primary conclusion: VALID CONDITIONAL ON ARCHIVED STREAM-INDEPENDENCE CONTRACT
