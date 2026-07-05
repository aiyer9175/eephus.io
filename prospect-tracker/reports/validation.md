# Valuation validation report (Phase 5)

_Generated 2026-07-04 from computed numbers only._

Coverage caveats: universe = 4044 active graded prospects on the 2026-07-04 metric snapshot (3945 sub-50, 99 50+). This is OUR graded stock, not the FanGraphs Board: never-ranked contributors are excluded, org membership follows our data, and NO residence-time stock->flow conversion is applied (we sum a stock of per-player values). Totals therefore need not equal the published aggregates; deviations are reported, not forced.

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

## Organization rollup (clemens_2026 table mode)

Top org published ~$671M (Pittsburgh). Ours:

| org | total value | sub-50 share (depth-vs-stars) |
| --- | --- | --- |
| TBR | $858M | 73% |
| LAD | $774M | 54% |
| MIL | $757M | 62% |
| WSN | $674M | 64% |
| BAL | $671M | 76% |
| SEA | $666M | 51% |
| MIN | $655M | 68% |
| MIA | $652M | 80% |
| TOR | $648M | 85% |
| DET | $638M | 65% |
| STL | $637M | 69% |
| SFG | $630M | 76% |
| BOS | $625M | 55% |
| PIT | $577M | 79% |
| ARI | $573M | 92% |

## Tier calibration: surplus (clemens model vs published table)

Model mode uses the v47 realized anchors, so it runs below the published tiers (the reconciliation gap the new framework surfaces). Deviations:

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

| role | max abs deviation |
| --- | --- |
| hitter | 0.547 |
| pitcher | 0.644 |

