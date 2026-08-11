# First divergence and residual unresolved mass

For two coupled monotone masked-generation chains, let `tau` be their first divergent transition and let `R(S_tau)` be the weighted mass of MASK coordinates in the common pre-split state. Under copy-only committed coordinates, no remasking/editing, positive generation-coordinate weights, and normalized Hamming output distance,

`d(S_0^FP, S_0^Q) <= R(S_tau) 1{tau < infinity}`.

Taking expectation under a specified valid coupling gives an upper bound on that coupling cost and therefore on Wasserstein distance. The bound is coupling-specific; coordinatewise maximal coupling is not claimed to be joint maximal. See the report's complete proofs for exact indexing and terminal-kernel treatment.
