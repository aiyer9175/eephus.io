# eFV tracking-era head: results in plain language

Generated 2026-10-15T12:49:45Z by `efv5_tracking_head.py` from `data/efv5_tracking_head.json` (70.7 s, bootstrap B 2000). Registration: `docs/efv-v2/EFV_TRACKING_HEAD_GATE.md` (sha256 a3918d6565e9), read the same day as an owner-waived early read (EW3-5). eFV tracking-era head, development read (EW3-1): short-horizon label, nothing served moves, no number by consensus-FV level, consensus FV a covariate and a comparator only. spent: the label window reaches a 2025 or later debut cohort (R-VM, spent since the 10-08 confirmation); an owner-authorised short-horizon read (EW3-1).

## 1. What was asked

For prospects with minor-league pitch tracking (2021 and later; the Florida State League and, from 2022, Triple-A), does a head that adds the tracking metrics to PROSPX consensus FV order a held-out cohort better than consensus alone AND better than the served eFV v2, on a short label the tracking era can already resolve: reached MLB within 3 seasons (reach3) and fWAR per MLB season over those seasons (rate3)? The head enters eFV only on a lead over both (EW3-1).

## 2. The verdict

- hitters: **DOES NOT SHIP** (fails at least one of the four strict inequalities).
- pitchers: **SHIPS** (beats consensus and served V2 on both statistics as point estimates).

## 3. The held-out cohort (2023), read once

| side | rows (reached) | score | AUC reach3 | Spearman rate3 | head minus it: AUC (CI95) | head minus it: rho (CI95) |
|---|---|---|---|---|---|---|
| hit | 124 (73) | head | +0.6465 | +0.3258 |  |  |
| hit | 124 (73) | consensus | +0.5939 | +0.3318 | +0.0526 [+0.0011, +0.1083] | -0.0060 [-0.0745, +0.0663] |
| hit | 124 (73) | v2 | +0.6052 | +0.3657 | +0.0413 [-0.0181, +0.1046] | -0.0399 [-0.1333, +0.0551] |
| pit | 122 (91) | head | +0.6324 | +0.2389 |  |  |
| pit | 122 (91) | consensus | +0.5635 | +0.1918 | +0.0689 [-0.0183, +0.1517] | +0.0471 [-0.0758, +0.1681] |
| pit | 122 (91) | v2 | +0.5803 | +0.1772 | +0.0521 [-0.0259, +0.1280] | +0.0617 [-0.0587, +0.1796] |

Every held-out number is labelled spent: the 2023 cohort's window reaches the 2025 and 2026 debut cohorts.

## 4. The training cohorts (2021, 2022), out of fold: the selection frame

| side | rows (reached) | score | AUC reach3 | Spearman rate3 | head minus it: AUC (CI95) | head minus it: rho (CI95) |
|---|---|---|---|---|---|---|
| hit | 154 (45) | head | +0.8006 | +0.2642 |  |  |
| hit | 154 (45) | consensus | +0.7363 | +0.2826 | +0.0643 [+0.0114, +0.1202] | -0.0184 [-0.1015, +0.0659] |
| hit | 154 (45) | v2 | +0.7727 | +0.2802 | +0.0279 [-0.0262, +0.0851] | -0.0160 [-0.0951, +0.0628] |
| pit | 160 (74) | head | +0.7283 | +0.2541 |  |  |
| pit | 160 (74) | consensus | +0.6026 | +0.2264 | +0.1257 [+0.0488, +0.2052] | +0.0277 [-0.0891, +0.1434] |
| pit | 160 (74) | v2 | +0.6150 | +0.2367 | +0.1133 [+0.0409, +0.1862] | +0.0174 [-0.0902, +0.1254] |

## 5. Which tracking metrics carry the weight

Standardised coefficients of the fitted heads at the selected penalties (a metric 'carries weight' when its sign holds in every training fold and it holds at least 15 percent of its head's metric weight). This describes the fit; it admits nothing by itself.

### Hitters (lambda reach inf, lambda rate 300.0)

| head | metric | coefficient (z) | share of metric weight | sign stable | carries weight |
|---|---|---|---|---|---|
| reach | exit velocity, 90th pct | +0.0000 | 0.00 | no | no |
| reach | hard-hit rate | +0.0000 | 0.00 | no | no |
| reach | barrel rate | +0.0000 | 0.00 | no | no |
| reach | chase rate | +0.0000 | 0.00 | no | no |
| reach | zone contact rate | +0.0000 | 0.00 | no | no |
| rate | exit velocity, 90th pct | -0.0257 | 0.51 | yes | yes |
| rate | hard-hit rate | -0.0034 | 0.07 | no | no |
| rate | barrel rate | -0.0138 | 0.28 | no | no |
| rate | chase rate | -0.0055 | 0.11 | no | no |
| rate | zone contact rate | +0.0017 | 0.03 | no | no |

### Pitchers (lambda reach 30.0, lambda rate 10.0)

| head | metric | coefficient (z) | share of metric weight | sign stable | carries weight |
|---|---|---|---|---|---|
| reach | aStuff+ | +0.1802 | 0.30 | yes | yes |
| reach | top-end fastball velocity (95th pct) | +0.0391 | 0.07 | no | no |
| reach | fastball ride (induced vertical break) | -0.0267 | 0.05 | no | no |
| reach | xwOBA against | -0.0698 | 0.12 | yes | no |
| reach | exit velocity against | -0.1185 | 0.20 | yes | yes |
| reach | arm angle | -0.1576 | 0.27 | yes | yes |
| rate | aStuff+ | +0.0495 | 0.19 | yes | yes |
| rate | top-end fastball velocity (95th pct) | -0.0154 | 0.06 | no | no |
| rate | fastball ride (induced vertical break) | +0.0439 | 0.17 | no | no |
| rate | xwOBA against | -0.0042 | 0.02 | no | no |
| rate | exit velocity against | -0.1197 | 0.47 | yes | yes |
| rate | arm angle | -0.0218 | 0.09 | yes | no |

## 6. By group on the held-out cohort (reporting only)

| side | group | n (reached) | head AUC / rho | consensus AUC / rho | V2 AUC / rho |
|---|---|---|---|---|---|
| hit | corner outfielders (LF, RF, OF) | 41 (23) | +0.6159 / +0.3581 | +0.5700 / +0.4090 | +0.5435 / +0.4339 |
| hit | other infielders (2B, 3B, IF) | 30 (21) | +0.7831 / +0.4233 | +0.6905 / +0.4796 | +0.7778 / +0.5256 |
| hit | shortstops | 25 (12) | +0.6218 / +0.4529 | +0.5577 / +0.4061 | +0.5256 / +0.3459 |
| hit | A | 60 (17) | +0.6881 / +0.3805 | +0.7066 / +0.3800 | +0.7018 / +0.3351 |
| hit | AAA | 64 (56) | +0.6719 / +0.3629 | +0.7165 / +0.3222 | +0.7009 / +0.3651 |
| pit | relievers | 49 (38) | +0.6340 / +0.3066 | +0.5096 / +0.1129 | +0.5335 / +0.0941 |
| pit | starters | 73 (53) | +0.6604 / +0.1841 | +0.6236 / +0.2040 | +0.6434 / +0.1957 |
| pit | A | 41 (19) | +0.6770 / +0.1319 | +0.7524 / +0.1360 | +0.7584 / +0.0583 |
| pit | AAA | 81 (72) | +0.4460 / +0.2386 | +0.4792 / +0.2683 | +0.4691 / +0.2496 |

## 7. The frame

| side | cohort | level | role | rows | reached within 3 | spent |
|---|---|---|---|---|---|---|
| hit | 2021 | A | train | 69 | 20 | no |
| hit | 2022 | A | train | 63 | 7 | yes |
| hit | 2022 | AAA | train | 22 | 18 | yes |
| hit | 2023 | A | holdout | 60 | 17 | yes |
| hit | 2023 | AAA | holdout | 64 | 56 | yes |
| pit | 2021 | A | train | 56 | 20 | no |
| pit | 2022 | A | train | 61 | 19 | yes |
| pit | 2022 | AAA | train | 43 | 35 | yes |
| pit | 2023 | A | holdout | 41 | 19 | yes |
| pit | 2023 | AAA | holdout | 81 | 72 | yes |

Served V2 joined on {'hit': {'train': 154, 'holdout': 124, 'train_missing_v2': 0, 'holdout_missing_v2': 0}, 'pit': {'train': 160, 'holdout': 122, 'train_missing_v2': 0, 'holdout_missing_v2': 0}} (rows missing a V2 score are left out of every comparison). fWAR vintage 2026-10-02-0341299c20ec.

## 8. What happens next

A side that ships enters eFV for its tracked prospects at the registered blend (w_head 0.5), with the note 'tracking-era head, short-horizon label (reached MLB within 3 seasons; fWAR per MLB season over those seasons)' on every surface that shows the grade; the flip and the rebuild are listed under the task's INTEGRATION NOTES.

