# WP06-CERT-3 Clean-Room Methods

The primary recalculation reads only the frozen payload's `raw/`,
`config/`, and `provenance/` trees. It does not import the authoring
reproduction code and does not read archived reports, plots, gates, or
derived CSV values before the blind freeze.

For every coupled trajectory, the script sorts the 33 raw native transition
rows, parses the two generation-token states, reconstructs endpoint Hamming
distance at each preregistered horizon, locates the first post-transition
state split, and counts masks in the common pre-split state. The fully masked
initial state is used when the first split is at kernel zero. It checks
`D_H <= B_FS_H + 1e-12` and that an already equal committed pre-split
coordinate never differs at the endpoint.

The categorical audit draws 100,000 fresh coupling samples from each of the
24 archived FP/Q categorical-law pairs. Product split hazards are recomputed
from coordinate TV rows. Event records are parsed to check semantic-key and
stable-seed collisions.

The primary statistical calculation uses the frozen family `K=49`,
family-wise error `0.05`, `n=256` for CMC cells, and `n=128` for disjoint FP
pairs. Absolute and relative horizon selection is prefix-closed. A separate
direct-PyArrow implementation recomputes the headline means, upper bounds,
horizons, and pathwise violation count.

No checkpoint is loaded and no model transition is executed.
