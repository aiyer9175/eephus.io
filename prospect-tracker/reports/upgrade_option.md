# Upgrade-option layer (Phase 7, Tier 2)

_Generated 2026-07-04 from computed numbers only. UI deferred; report + registry only._

A prospect's grade is a call option on development. We model the grade as a role-split absorbing Markov chain (grades 35-70, plus graduated and out) with an annual step, estimated from our own dated grade history (fangraphs + mlb_pipeline snapshots, Laplace-smoothed). Payoff = the clemens_2026 table value of the grade a player graduates from.

- total = expected payoff under the full chain (grade can move)
- intrinsic = payoff under frozen-grade transitions (stay / graduate / out at the current grade)
- option = total - intrinsic; OPT% = option / total

Low grades are long-dated out-of-the-money calls on development: most of their value is option. High grades are thin in our data and their graduation timing is partly censored, so their OPT% runs low or negative (grade mobility at the top is net-downgrade risk the frozen view ignores). Nobody publishes OPT%.

## Hitter

| FV | total $M | intrinsic $M | option $M | OPT% | obs (n) | annual upgrade | annual graduate | board n | agg option $B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | 4.0 | 0.3 | 3.6 | 92% | 940 | 33% | 6% | 1117 | 4.07 |
| 40 | 6.3 | 1.6 | 4.7 | 75% | 2528 | 17% | 8% | 544 | 2.55 |
| 45 | 11.4 | 4.6 | 6.9 | 60% | 2252 | 15% | 8% | 160 | 1.1 |
| 50 | 24.5 | 26.2 | -1.7 | -7% | 1031 | 20% | 10% | 71 | -0.12 |
| 55 | 41.8 | 48.2 | -6.4 | -15% | 458 | 15% | 16% | 22 | -0.14 |
| 60 | 60.1 | 79.1 | -18.9 | -32% | 221 | 15% | 18% | 7 | -0.13 |
| 65 | 86.9 | 92.8 | -5.9 | -7% | 55 | 9% | 36% | 0 | -0.0 |
| 70 | 146.1 | 187.5 | -41.4 | -28% | 30 | 0% | 36% | 0 | -0.0 |

## Pitcher

| FV | total $M | intrinsic $M | option $M | OPT% | obs (n) | annual upgrade | annual graduate | board n | agg option $B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 35 | 2.0 | 0.3 | 1.6 | 82% | 1376 | 27% | 8% | 1507 | 2.44 |
| 40 | 3.3 | 1.7 | 1.6 | 49% | 2520 | 14% | 10% | 448 | 0.72 |
| 45 | 5.8 | 3.2 | 2.6 | 45% | 1967 | 13% | 9% | 113 | 0.3 |
| 50 | 12.6 | 19.0 | -6.4 | -50% | 786 | 15% | 10% | 49 | -0.31 |
| 55 | 21.2 | 33.1 | -11.9 | -56% | 306 | 12% | 13% | 3 | -0.04 |
| 60 | 26.2 | 60.9 | -34.7 | -132% | 177 | 4% | 13% | 3 | -0.1 |
| 65 | 48.2 | 87.1 | -38.9 | -81% | 18 | 11% | 24% | 0 | -0.0 |
| 70 | 67.9 | 162.5 | -94.6 | -139% | 10 | 0% | 17% | 0 | -0.0 |

## Acceptance

- 45 FV hitter OPT% = 60% (target > 50%): PASS
- 60 FV hitter OPT% = -32% (well below the 45 FV): PASS

## Config-prior cross-check

The config-prior mode uses a labelled literature anchor (45 FV position player ~20% upgrade odds), NOT estimated from our data. It is a sanity cross-check only: 45 FV hitter OPT% is 91% under the config prior vs 60% from our data.

