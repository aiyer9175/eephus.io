# Deal+ quadrature convergence: measured, gated, and held for an owner call

Date: 2026-09-06. Status: **MEASURED, NOT SHIPPED.** No served number moves in the
commit that carries this document.

## 1. The defect

`fa_mc.QUAD_TAUS` is `tuple(round(i / 20.0, 3) for i in range(1, 20))`, an interior grid
on the 5% marks. `expected_tier_value_usd` averages the two-piece marginal over it to
compute what its own docstring calls "NPV of E[tier value]".

That grid never evaluates `u` below 0.05 or above 0.95. The convex tail the Jensen
correction exists to capture is precisely what it truncates, so the integral comes out
low. The old note called this "slightly". It is not slight.

Measured against a converged reference (midpoint rule, n = 399, which sits 0.03% from the
n = 102,399 limit; the integral converges cleanly to a finite value, so this is genuine
convergence and not a divergent tail being truncated by luck):

| population | converged / shipped | p05 | median | p95 |
|---|---|---|---|---|
| served FA class, 231 rows | value | 1.0370 | **1.0796** | 1.1402 |
| 1,300-signing corpus | Deal+ | 1.0342 | **1.0740** | 1.1359 |

The spread matters as much as the level. A 3.4% to 13.6% range across rows means the
error moves the **order** of Deal+, not only its level, so it is not absorbable by a
constant rescale of the verdict edges.

Node count is not the cause. A **midpoint** rule on the same 19 nodes recovers most of the
gap (bias -1.761 -> -1.244 of the -1.137 available). The endpoints are the cause.

## 2. Convergence, shown

Median value on a 40-row sample, indexed to the shipped grid:

| nodes | ratio |
|---|---|
| 19 (shipped, i/20) | 1.00000 |
| 39 midpoint | 1.04419 |
| 99 | 1.04648 |
| 399 | 1.04748 |
| 1,599 | 1.04771 |
| 6,399 | 1.04776 |
| 25,599 | 1.04777 |
| 102,399 | 1.04777 |

## 3. What the lane's own gate says

`tools/_fa_jensen.py`, rebuilt on today's data: **444 forward-chained signings**, winters
2018-2022, contract terms fully realized, each scored against its own realized
tier-priced WAR. (The docstring records 449 for this lane; the corpus has drifted by five
rows since that measurement. Direction and magnitude are unchanged.)

Realized mean: **$12.447M**.

| basis | signed bias | MAE | mean predicted |
|---|---|---|---|
| naive, no correction at all | -5.169 | 10.227 | $7.278M |
| shipped grid (i/20) | -1.761 | 11.181 | $10.686M |
| converged grid (n=399) | **-1.137** | 11.412 | $11.313M |

Winter-clustered paired bootstrap, B = 2,000, converged minus shipped:

| statistic | delta | CI95 | P(right direction) |
|---|---|---|---|
| **signed bias** (this lane's stated primary metric) | **+0.624** | **[+0.551, +0.705]** | **1.0000** |
| absolute bias | -0.518 | [-0.703, +0.621] | 0.9160 |
| MAE | +0.231 | [+0.139, +0.319] | 0.0000 |

Read the `|bias|` row as the unstable statistic it is, not as a contradiction. Both biases
stay negative at the point estimate, so `|bias|` folds only in resample draws where the
converged bias crosses zero; that folding is what widens its interval to contain zero. The
signed contrast is the clean one and it excludes zero comfortably.

MAE worsening is the trade this correction **already made and shipped**: the
`expected_rational_value_usd` docstring records MAE going +1.343 worse when the correction
was adopted, on the reasoning that bias is the primary metric and "correcting a level bias
on noisy per-row bands raises dispersion. Reported, not hidden." The converged grid
continues in that direction at one sixth the size.

Neither grid overshoots. Predicted mean stays below realized on both, and the count of
rows predicted above their own realized value moves 288 -> 299 of 444.

## 4. Why it is not shipped

Deal+ is `100 * this value / price`. Converging the grid raises every published Deal+ by a
median 7.4%, and on the 1,300-row historical corpus **74 rows (5.7%) flip verdict if the
grid converges and the terciles do not**, skewing toward VALUE (pooled split 427/431/442
becomes 397/422/481 against a 33/33/33 design).

The terciles are already carrying a deferred re-cut. `fa_market.py` records, at the
2026-08-19 pooled re-cut: *"VERDICT_BAND_MODE is 'group' (owner 2026-07-30), so these
pooled edges are the fallback constants and the historical-corpus banding basis; served
verdicts are banded per group and do not move until VERDICT_GROUP_EDGES is re-cut on the
same basis (owed)."*

So shipping the quadrature fix means stacking a **second** basis move onto published
VALUE / MARKET / OVERPAY labels, on a lane where the owner was shown a table and made an
explicit choice. That is an owner call, not an executor's.

## 5. The decision package

Corpus: n = 1,300, winters 2017-2026, basis A (`100 * expected rational value / ACTUAL NPV
price`, forward-chained train-only $/WAR, ex-ante destale rate, term capped at 10). The
recipe reproduces the recorded 2026-08-19 cut: pooled own terciles come out 89/203 here
against the recorded 88.80/197.77 (the small gap is index-based versus interpolated
quantiles).

| group | n | served edges | split under them, shipped grid | split if the grid converges and edges do NOT | own terciles, shipped grid | own terciles, converged grid |
|---|---|---|---|---|---|---|
| pooled | 1300 | 89 / 198 | 427 / 431 / 442 | 397 / 422 / 481 | 89 / 203 | **96 / 218** |
| SP | 297 | 86 / 182 | 97 / 98 / 102 | 91 / 98 / 108 | 87 / 183 | **95 / 199** |
| RP | 450 | 65 / 146 | 145 / 162 / 143 | 132 / 157 / 161 | 66 / 143 | **71 / 152** |
| C | 102 | 101 / 243 | 26 / 35 / 41 | 20 / 40 / 42 | 117 / 287 | **124 / 307** |
| POS | 451 | 103 / 237 | 128 / 163 / 160 | 115 / 165 / 171 | 118 / 254 | **124 / 281** |

Splits are overpay / market / value.

Note this table also prices the ALREADY-owed re-cut on its own: on the **shipped** grid, C
and POS are meaningfully off their own terciles (served 101/243 against 117/287, and
103/237 against 118/254), while SP and RP are close. That staleness exists today and is
independent of the quadrature question.

## 6. The three options

1. **Hold.** Nothing moves. The approximation is now stated at its measured size in
   `fa_mc.expected_tier_value_usd`, so no future reader has to rediscover it, and
   `test_fa_quadrature.py` makes any change to `QUAD_TAUS` confront this document.
2. **Converge the grid and re-cut the group edges together**, to the converged column
   above. Every published rational, surplus and Deal+ rises ~7.4%; verdict labels stay
   near 33/33/33 per group; 5.7% of historical corpus verdicts move for the grid and more
   for the already-owed re-cut.
3. **Do the already-owed group re-cut alone**, on the shipped grid (SP 87/183, RP 66/143,
   C 117/287, POS 118/254), and leave the quadrature for later. This moves C and POS
   verdicts materially and touches no dollar figure.

## 7. Reproduce

```
python tools/_fa_jensen.py build      # 444-row realized-outcome corpus
```

The grid comparison and the bootstrap are driven by passing `taus=` explicitly to
`fa_mc.expected_tier_value_usd`. Monkeypatching `fa_mc.QUAD_TAUS` does **not** work:
`taus=QUAD_TAUS` is a default argument, bound once at function definition, so
`_fa_jensen.score()` keeps using the shipped grid no matter what the module attribute
says. A first pass at this measurement reported "no effect at any node count" for exactly
that reason.
