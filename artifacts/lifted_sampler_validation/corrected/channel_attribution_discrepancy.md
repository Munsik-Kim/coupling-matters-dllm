# Channel attribution discrepancy

The predecessor grouped channel rows by `precision, temperature`, which mixed lengths 16 and 64 for W8/W4 at temperature 0.2. LOCAL-LIFT-1R uses `generation_length, precision, temperature`. The predecessor trajectory, pathwise, and marginal gates are unchanged; this is a report aggregation correction. Length 16 is the only W8/W6/W4 cross-precision comparison.
