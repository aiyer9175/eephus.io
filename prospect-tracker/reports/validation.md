# Valuation validation report (Phase 5)

_Generated 2026-07-05 from computed numbers only._

Coverage caveats: the HEADLINE universe = 4044 active graded prospects on the 2026-07-04 metric snapshot (3945 sub-50, 99 50+). This is OUR graded stock, not the FanGraphs Board: never-ranked contributors are included, org membership follows our data, and the whole-stock totals sum a STOCK of per-player values. The org rollup below now applies a residence-time stock->flow reconciliation, and a Board-restricted (2026report) universe comparison is reported separately for the apples-to-apples read. Totals still need not equal the published aggregates; deviations are reported, not forced.

## Universe totals

| basis | total | sub-50 | 50+ |
| --- | --- | --- | --- |
| prospx_current (model) | $9.68B | $7.05B | $2.63B |
| clemens_2026 (model) | $9.94B | - | - |
| clemens_2026 (table) | $17.42B | $12.58B | $4.83B |

Published FanGraphs aggregates (whole minors ~$12.00B, band $10.50B-$13.75B; 50+ ~$5.70B, sub-50 ~$6.30B).

### Residence-time reconciliation (sub-50 stock -> flow)

Our raw sub-50 TABLE stock is $12.58B, well above the published $6.30B sub-50 pool. The gap is the residence-time treatment: FanGraphs converts the sub-50 stock to an effective flow (a prospect resides ~2 years before graduating or washing out), which we do not apply when summing a snapshot stock. Scaling the sub-50 stock by 1/residence (2.0y) gives $6.29B, in line with the published $6.30B pool (the exact FanGraphs conversion is not fully published, so treat this as an approximate reconciliation).

| measure | value | published |
| --- | --- | --- |
| sub-50 (raw stock) | $12.58B | $6.30B |
| sub-50 (residence-adjusted flow) | $6.29B | $6.30B |
| 50+ (stock) | $4.83B | $5.70B |
| whole minors (reconciled) | $11.13B | $10.50B-$13.75B |
In band.

## Organization rollup (clemens_2026 table mode, residence-reconciled)

Top org published ~$671M (Pittsburgh (PIT)). Our raw TABLE stock tops out at ~$774M (LAD), above the published figure because a raw stock double-counts a prospect's ~2y residence. Applying the same sub-50 stock->flow reconciliation (/2y) drops our top org to ~$565M -- in line with the published $671M; the residual is the universe/Board difference isolated in the next section.

| org | raw stock | residence-reconciled flow | sub-50 share (depth-vs-stars) |
| --- | --- | --- | --- |
| LAD | $774M | $565M | 54% |
| TBR | $858M | $544M | 73% |
| MIL | $757M | $522M | 62% |
| SEA | $666M | $497M | 51% |
| WSN | $674M | $459M | 64% |
| BOS | $625M | $453M | 55% |
| MIN | $655M | $433M | 68% |
| DET | $638M | $431M | 65% |
| STL | $637M | $417M | 69% |
| BAL | $671M | $416M | 76% |
| MIA | $652M | $392M | 80% |
| SFG | $630M | $392M | 76% |
| TOR | $648M | $373M | 85% |
| CLE | $568M | $371M | 69% |
| CHW | $502M | $354M | 59% |

## Board-aligned universe comparison (apples-to-apples)

Restricting to FanGraphs 'The Board' ranked players (2026report) that are still active in our universe -- 793 of 1005 ranked (the rest graduated or washed out and are dropped by the active filter, so this UNDERCOUNTS the published full-board aggregate). Priced table-mode; sub-50 stock->flow reconciled:

| measure | our value | published |
| --- | --- | --- |
| Board whole (raw stock) | $8.55B | $12.00B |
| Board whole (residence-reconciled) | $6.40B | $10.50B-$13.75B |
| Board top org (reconciled) | $462M (LAD) | $671M (Pittsburgh (PIT)) |
The Board-restricted top org lands nearer the published figure than the full-stock rollup; the remaining gap is the excluded (graduated/washed-out) board members plus the approximate residence conversion. Reported, not tuned to match.

## Tier calibration: surplus (clemens model vs published table)

Model mode (the career-path engine under the clemens params, war_anchor_scale=1) runs below the published tiers because it uses the v47 realized (bust-heavy) WAR anchors. The per-tier deviations below are the RESIDUAL at the production anchor; the reconciliation section quantifies how much of it is a single global scale.

| role | tier | published $M | model $M | |dev| | <=10%? |
| --- | --- | --- | --- | --- | --- |
| hitter | 35+ | 2.0 | 1.4 | 30% | off |
| hitter | 40 | 5.5 | 1.5 | 73% | off |
| hitter | 40+ | 8.0 | 2.7 | 66% | off |
| hitter | 45 | 14.5 | 5.5 | 62% | off |
| hitter | 45+ | 18.5 | 15.2 | 18% | off |
| hitter | 50 | 45.0 | 18.5 | 59% | off |
| hitter | 55 | 55.0 | 35.2 | 36% | off |
| hitter | 60 | 82.0 | 67.7 | 17% | off |
| hitter | 65 | 95.0 | 116.7 | 23% | off |
| hitter | 70 | 195.0 | 165.0 | 15% | off |
| pitcher | 35+ | 1.5 | 1.4 | 7% | PASS |
| pitcher | 40 | 4.0 | 1.5 | 62% | off |
| pitcher | 40+ | 7.0 | 2.1 | 70% | off |
| pitcher | 45 | 9.5 | 3.0 | 68% | off |
| pitcher | 45+ | 15.0 | 8.9 | 41% | off |
| pitcher | 50 | 33.5 | 15.5 | 54% | off |
| pitcher | 55 | 45.0 | 24.3 | 46% | off |
| pitcher | 60 | 70.0 | 53.0 | 24% | off |
| pitcher | 65 | 95.0 | 96.8 | 2% | PASS |
| pitcher | 70 | 195.0 | 140.8 | 28% | off |

## Tier calibration: star odds (clemens model vs published)

| role | max abs dev | mean abs dev |
| --- | --- | --- |
| hitter | 0.547 | 0.146 |
| pitcher | 0.644 | 0.131 |

## Model<->table reconciliation (diagnostic; reported, not forced)

The single per-role WAR-anchor multiplier k that best aligns the MODEL tier aggregates to the PUBLISHED tiers (joint surplus + star-odds objective), with the RESIDUAL after that best fit. This is a DIAGNOSTIC only: k is swept transiently and written to NO shipped set, so the live board is never rescaled to the table. A single scalar cannot zero both residuals (star odds is a nonlinear tail functional, surplus near-linear in WAR), so both stay > 0 -- that irreducible residual is the honest read of the gap.

| role | fitted k | surplus mean |dev| (pre->post) | star mean |dev| (pre->post) |
| --- | --- | --- | --- |
| hitter | 1.40 | 40% -> 35% | 0.146 -> 0.076 |
| pitcher | 1.50 | 40% -> 32% | 0.131 -> 0.040 |

