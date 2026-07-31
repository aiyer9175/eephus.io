# WAR/PA+ and WAR/IP+: closing the shrink owner call, and the Judge question

Owner decision 2026-07-30 evening. This file closes the `owner_call: OPEN` carried in
`data/war_rate_plus_eval.json` at `pools.hit.shrink_ruling` and `pools.RP.shrink_ruling`,
and records the answer to the owner's question about why the index looks compressed.

## 1. The question: "Judge is only 25% above average?"

**It is a scale misread, not a compression bug.** The index is convention 3
(`docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md`): 100 + 10z, where ten points is
one standard deviation of the anchor pool. It is not a percent of average.

Measured on the served 2026-07-30 hitter board:

| quantity | value |
|---|---|
| pool mean WAR/PA | 0.002297 |
| pool sd WAR/PA | 0.004289 |
| pool sd / mean | **1.87** |
| Judge 2026 | 2.1 bWAR / 261 PA = 0.008046 |
| Judge as a RATIO to the pool mean | **3.50x** |
| Judge as a z-score | +1.34 |
| Judge `war_pa_plus` | **113** |
| Judge `war_pa_plus_3yr` | 125, `pct` 100 (top of the board) |

So the 3yr 125 does not mean "25% better than average". It means **+2.5 pool sigma, the
best three-year WAR rate on the board**. His actual rate is three and a half times the
league mean. The two readings differ because WAR per trip is a signed, extremely
dispersed rate: its standard deviation is 1.87x its own mean, so ratio intuitions from
wRC+ (where the sd is a fraction of the mean) do not transfer.

**The scale is verified correct, not compressed.** `live_season_scale_check` in the eval
measures exactly 10.0 points per anchor-pool sigma on all three pools, so the aStuff+ C3
defect class (advertised 10, actually 7.16) is absent here. The narrower served spread
(sd 8.99 hitters, 9.15 SP, 9.89 RP) is display-gate selection, not rescaling.

**A ratio index is mathematically undefined on this rate and must never be built**
(`bullpen_export.py:444-455`): league mean WAR/PA is about +0.0023 and WAR goes negative,
so `100 * player / pool` flips sign and blows up. There is no HEM_SPREAD_GAIN analog and
none should be added.

**What ships instead is legibility**, not a new scale: a 1yr percentile chip mirroring
the existing 3yr `pct` pattern, so "top of the board" is readable without doing z-score
arithmetic.

## 2. The owner call: SHIP THE SHRINK AS A COMPANION COLUMN

Pre-registered rule: arm S (regress the rate toward the pool rate by sample size) fired
on `hit` (pooled gap lo95 +0.0100) and `RP` (+0.0002), not on `SP`. The ship was
unshrunk, overriding the rule on four recorded reasons, and the call was left open rather
than taken silently.

**Owner ruling: close it as SHIP, but as a NEW column, not a replacement.**

- The raw `war_pa_plus` / `war_ip_plus` keep their exact current meaning. They stay the
  descriptive index of what was actually banked, and they stay reproducible from the row
  (`war` / `pa` against `pool_mean_rate`), which is the property reason 1 of the override
  was protecting.
- The shrunk variant ships beside them as `war_pa_plus_adj` / `war_ip_plus_adj`. Naming a
  shrunk number differently is required by the conventions doc: the adjusted value no
  longer reproduces `war/pa` on the row, so reusing the column name would silently change
  what a published number means.

**Implementation is the measured arm S verbatim** (`tools/war_rate_plus_lab.py:311-326`),
including its one non-obvious requirement:

```
K          = pool MEDIAN denominator
pool_rate  = sum(war) / sum(denom)
rate_shrunk= (war + pool_rate * K) / (denom + K)
mu, sd     = mean and sd OF THE SHRUNK POOL      <- not the unshrunk one
plus_adj   = 100 + 10 * (rate_shrunk - mu) / sd
```

Taking mu/sd from the shrunk pool is the defect-C3 guard: computing a z against unshrunk
moments after shrinking the numerator is exactly how aStuff+ ended up at 7.16 points per
sigma while advertising 10. Arm S already does this correctly and is the template.

## 3. What the copy must disclose

Three caveats travel with the adjusted column, all measured:

1. **The forward gate still fails.** G2 failed on all three pools: plain season bWAR
   predicts next-season WAR rate better than either index (hit 0.3711 vs 0.4058, SP
   0.2688 vs 0.2799, RP 0.0886 vs 0.0899). Both columns remain `unvalidated` display
   indexes. Neither may enter eFV, projections, or FA. Any forward WAR-rate need uses
   `war_total`.
2. **The shrink gain is mostly a volume leak.** The post-hoc volume control shows the
   pooled improvement collapses within predictor-volume terciles (within-band means at or
   under +0.0034, only hit/high clearing zero). The adjusted column is a sample-size
   readability aid, not a demonstrated accuracy gain.
3. **The adjusted number is not the player's banked rate.** At the 100-PA display gate it
   sits around 70% of the way toward league average, by construction.

## 4. Scope note

`HEM+`, `SEM+` and `REM+` need no sample-size work and must not be touched: every one of
them already shrinks each component toward its pool with its own empirical-Bayes constant
(HEM+ K_UBB 120 / K_HBP 240 / K_1B 290 / K_2B 1000 / K_3B 1600 / K_HR 170; REM+ and SEM+
K_STRIKEOUT 70 / K_WALK 170 / K_HBP 170 / K_HOMERUN 400), plus two-tier volume floors.
The WAR rates were the only unshrunk columns on the boards, which is why the owner's
sample-size ask resolves to exactly this lane.
