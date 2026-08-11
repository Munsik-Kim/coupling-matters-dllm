# General additive token-cost product theorem — proof

For any coupling $\pi$ of $P$ and $Q$, its coordinate projection $\pi_i$ couples $p_i$ and $q_i$. Therefore

`E_pi[d_c(X,Y)] = sum_i lambda_i E_pi_i[c_i(X_i,Y_i)] >= sum_i lambda_i W_{c_i}(p_i,q_i)`.

Conversely, finite support guarantees an optimal coordinate coupling $\pi_i^*$ for every $i$. The product $\otimes_i\pi_i^*$ has marginals $P$ and $Q$, and its expected additive cost is exactly the sum of coordinate optima. The lower and upper inequalities coincide.

The first-divergence corollary follows because coordinates already equal and committed before the first split are copied forever. Only coordinates MASKed in the common pre-split state can contribute, and each contributes at most its metric diameter.
