# eWAR pitching blend: a reliability-weighted combination of FIP-based and runs-allowed-based pitching runs (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EWAR_PITCHING_BLEND (owner decision EW3-50). This document is
committed ALONE, before any number of its estimands is computed: no split-half moment, weight, blend
value, rank correlation or club-season sum of the blend exists, and the code that computes the read
does not exist at this commit. Nothing in this commit changes a model, an exporter, a flag or a
served artifact. Part 14 is filled in afterwards; nothing above part 14 may be edited once anything
is written below it, and a change is a dated amendment under part 14, committed alone. Its pin test
is `test_ewar_pitching_blend_gate.py`.

## 0. What kind of decision this is

- **A measurement-error combination of two published pitching run values, read once, with one
  adoption rule.** The owner's question (EW3-50): can a pitcher-season's FanGraphs FIP-based pitching
  runs and Baseball-Reference's runs-allowed-based pitching runs (defense-adjusted) be combined, with
  each source weighted by how reliable it is at that pitcher's workload and role, into a pitching
  value that forecasts next season's runs allowed better than either source alone, without losing
  the club runs-allowed accounting?
- **The candidate is a weight, not a new run construction.** Each source enters as published. The
  blend weight comes from within-season split-half reliability (odd against even appearances) and
  the cross-source covariance, fitted in forward-chained folds. No term is added to either source and
  nothing is fitted on a next-season quantity.
- **Not a reopened arm.** It is not S2 or S2b (EBR_GATE.md 9.4 and 11.3: shrunk FIP components;
  regressed contact quality, BABIP and strand terms with constants fitted on next-season persistence),
  not the global home-run shrink, not PE-P, not R2's construction (11.3.3, which this read uses only
  as its target and as a reported column) and not a runs-per-win fit. Parts 12.2 and 12.3 of
  EBR_GATE.md stand as written; nothing on their do-not-reopen lists is rescored (part 13).
- **Built dark.** The read writes its tracked record to `data/_labs/ewar_pitching_blend/record.json`
  (`data/_labs/` ships in neither deploy consumer) and its numbers to part 14. No registry row,
  glossary entry, page or served artifact is added or moved by this task. On ADOPT the blend is built
  dark behind a flag that defaults off and an owner question decides whether it is served (part 12).

## 1. Decision record

| Id | Question | Recorded answer | Status |
|---|---|---|---|
| EW3-50 | Make eWAR better than both fWAR and bWAR without redoing failed work | four arms approved: EWAR_TEAM_ACCOUNTING, EWAR_PITCHING_BLEND (this document), EWAR_UNCERTAINTY_BAND, EWAR_PEH_OLD_SEASONS | answered 2026-10-22 (`DECISIONS_FOR_OWNER.md`, EW3-50) |
| EW3-23 | The forward target of a pitching part | next-season realized runs allowed, RA9* of EBR_GATE.md 11.2.1 (park, defense and inherited runners adjusted) | answered 2026-10-15 |
| EW3-5 | Look days and registered dates | waived: the read runs on any date | answered 2026-10-14 |
| AG4-Q | What a flip commit carries | the flag, registry, glossary, copy and tests only; regenerations are listed for the integrator | answered 2026-10-22 |

Defaults this document applies, named so the orchestrator records them: predictor seasons 2017,
2018 and 2021 to 2024 (2016 is the first fold's training season only; 2020 out on both sides); the
pitcher floor 50 IP in both seasons (11.2.1's); FanGraphs' FIP basis read as `fipMinus` scaled by the
season's league FIP (part 2); roles split at games started over games pitched 0.5; IP bands 0 to 20,
20 to 40, 40 to 100 and 100 or more; the cell minimum 30 rows; the non-inferiority margin 1.0 run of
runs-allowed RMSE (part 6); the blend's club series at FanGraphs' runs per win (part 6); the planted
magnitudes of part 8.

## 2. The two sources and the blend

For pitcher j in season s (MLBAM id; position players who pitch, the `nopp` rows of the eWAR v3
preview, are out of every fit and frame and carry no departure):

```
IP_j    = outs / 3 from the frozen fWAR vintage's pitching row (`outs`)
role_j  = SP when gamesStarted / gamesPitched >= 0.5, else RP (the vintage's columns)
lgFIP_s = the IP-weighted mean of the vintage's `fip` over the season's pitching rows
F9_j    = lgFIP_s * (100 - fipMinus_j) / 100
          FanGraphs' FIP-based runs prevented above average per 9 innings (park and league adjusted)
B9_j    = 9 * sum over stints of runs_above_avg / (sum over stints of IPouts / 3)
          Baseball-Reference's runs prevented above average per 9 innings (xRA_final - RA: runs
          allowed against the runs an average pitcher would allow with this defense, park and role),
          from the site's Baseball-Reference copy (`war_source._load_last_good("pit")`), before its
          leverage adjustment
each source is centred within season: x9_j - (sum_k IP_k x9_k) / (sum_k IP_k) over the season's rows
blend9_j = w_j * F9_j + (1 - w_j) * B9_j        w_j = w(IP_j, role_j), part 4
runs_j   = blend9_j * IP_j / 9
```

A pitcher-season the Baseball-Reference copy lacks takes w = 1 (the blend is F) and is counted. Both
sources and the blend are runs prevented above average: replacement level, leverage and the runs-per-
win conversion are applied after, the same for every series, and are not part of this read.

## 3. Split-half reliability (the error side)

- **Appearances.** Every regular-season plate appearance of 2016 to 2025 (2020 out) on the runner
  record (`.cache/pbp_runners`: bases, outs, scorers, batter-runners), with the pitcher of record
  from the play-by-play corpus (`.cache/pbp_corpus`, 2018 on) or, for 2016 and 2017, from the cached
  StatsAPI play-by-play (`.cache/win_prob_hist`, `matchup.pitcher`), joined on (game, at-bat index).
  One appearance is one (game, pitcher). Never fetched; a season whose join leaves more than 0.5
  percent of plate appearances without a pitcher stops the read.
- **Per appearance:** outs recorded (outs after minus outs before over his plays); strikeouts,
  walks (intentional included, as FanGraphs' glossary formula reads), hit batters and home runs; and
  the runs charged to him, R, by a runner-ownership walk of each half-inning (a runner belongs to
  the pitcher who put him on; a pinch runner takes the replaced runner's owner; a runner the record
  cannot place, a placed extra-inning runner among them, belongs to the pitcher on the mound when he
  is first seen): every run scored is charged to the scoring runner's owner, as MLB charges it.
- **Halves.** A pitcher-season's appearances, in game order (game id), alternate odd and even. Half
  h carries IP_h = outs_h / 3 and the two proxies

```
F_h = -(13 HR_h + 3 (BB_h + HBP_h) - 2 K_h) / IP_h       the FIP rate, sign reversed, constant dropped
B_h = -9 R_h / IP_h                                       runs charged per 9, sign reversed
```

  The constants and the season-level park, defense and role baselines of F9 and B9 are the same in
  both halves of a pitcher-season, so they cancel in a half difference: the difference carries the
  sampling error of the published value (F9's FIP noise scaled by the park factor, about 5 percent,
  is disclosed and not corrected).
- **The error model.** Per inning, error variance sigma2_X and cross-source error covariance
  sigma_FB, so that a season value over IP innings carries error covariance Sigma_E / IP. Estimated
  per cell (part 4) over split rows (season IP 10 or more, both halves with at least one out):

```
h_j       = 1 / IP_odd + 1 / IP_even
sigma2_F  = sum_j (F_odd - F_even)^2 / sum_j h_j
sigma2_B  = sum_j (B_odd - B_even)^2 / sum_j h_j
sigma_FB  = sum_j (F_odd - F_even)(B_odd - B_even) / sum_j h_j
```

## 4. The signal side and the weight

- **Cells.** role (SP, RP) by IP band (0 to 20, 20 to 40, 40 to 100, 100 or more; a pitcher-season
  below 10 IP takes the first band's moments). A cell with fewer than 30 split rows or 30 season rows
  in the training seasons takes its role's pooled moments, and the record says which.
- **Signal covariance,** from the published season values of the cell's rows, each source centred
  within (season, cell):

```
Sigma_obs = the sample covariance of (F9, B9) over the cell's rows
Sigma_T   = Sigma_obs - Sigma_E * mean_j(1 / IP_j)          eigenvalues clamped at 0
```

- **The weight** is the latent-variable weight on runs-allowed talent T_B, the quantity both the
  forward target and Baseball-Reference measure: the best linear predictor of T_B from the two
  observed values at the pitcher's own IP, normalized so that the blend stays on the run scale.

```
beta_j = (Sigma_T + Sigma_E / IP_j)^(-1) * Sigma_T[:, B]
w_j    = beta_F / (beta_F + beta_B), clamped to [0, 1]; w_j = 1 when beta_F + beta_B <= 1e-9
```

  At low IP Baseball-Reference's larger error pushes w toward FanGraphs; as IP grows the weight moves
  toward the runs-allowed source in proportion to how much of its signal FanGraphs misses. With
  Sigma_T[F,F] = Sigma_T[F,B] = Sigma_T[B,B] and no error on F the weight is 1.
- **Forward-chained folds.** The moments that weight predictor season Y are fitted on the seasons
  2016 to Y - 1 (2020 out) only. No moment reads a season after Y and none reads a next-season
  quantity. The build's weights (part 12, and part 6's club series) are fitted on 2016 to 2025.
- **Reported, deciding nothing:** the build's w at each cell's median IP, per role and band, with
  each cell's sigma2_F, sigma2_B, sigma_FB, Sigma_T and row counts; the same per fold.

## 5. Test (i): next-season runs allowed per inning (predictive)

- **Pairs.** Pitcher j with IP 50 or more in Y and in Y + 1, Y in {2017, 2018, 2021, 2022, 2023,
  2024}, present in both sources in Y, with a finite RA9* in Y + 1.
- **Target:** RA9*(Y + 1), the `ra9_star` of the eWAR v3 preview (`.cache/swar/preview/swar.json`,
  EBR_GATE.md 11.2.1 and 11.3.3), sign reversed. Read only, never rebuilt by this task.
- **Statistic.** rho(X) is the pair-weighted mean over predictor seasons of the within-season
  Spearman correlation of X's rate in Y with the target. Gap against comparator K:
  `g(K) = rho(blend9) - rho(K)`, K in {F9, B9}. The blend uses the forward-chained w.
- **Two bootstraps, B = 4,000 each, seed 20261023,** each from its own generator, one index draw per
  replicate shared by every series (paired): player-clustered (pitchers drawn with replacement with
  all their pairs) and club-clustered (the 30 franchises drawn with replacement; a pair belongs to
  the franchise of its pitcher's largest Baseball-Reference IPouts stint in Y, `ewar._fold_team`).
  Each replicate recomputes every within-season Spearman on the drawn pairs (ties averaged).
- **p-value:** `p(K, k) = 1 - Phi(g(K) / sd_k)`, sd_k the bootstrap sd of g(K) under bootstrap k;
  `p_i = max over K and k`. The blend must beat both comparators under both bootstraps, an
  intersection-union test, so no correction applies inside test (i).

## 6. Test (ii): the club runs-allowed accounting (non-inferiority)

- **The yardstick** is EWAR_TEAM_ACCOUNTING's (its gate part 12): `ewar_team_accounting.score` on its
  frame (2016 to 2019 and 2021 to 2025, 270 club-seasons), its allocation, its estimands and its three
  bootstraps (season, club and player clustered, B 4,000, seed 20261023).
- **The candidate series C** is fWAR with the blend's pitching departure on the pit side:

```
d_j   = (runs_j(blend) - runs_j(F)) / RPW^F_s = (1 - w_j) (B9_j - F9_j) * IP_j / 9 / RPW^F_s
D_j   = d_j - IP_j * (sum_k d_k) / (sum_k IP_k)        re-pinned to sum to 0 per season
C     = F + D on the pit side, at FanGraphs' runs per win (league_constants)
```

  with the build's weights (fitted on 2016 to 2025; no club outcome enters a weight).
- **The cell:** runs allowed on the pit side, `d = RMSE_RA(K*) - RMSE_RA(C)`, K* the better of F and
  B on runs allowed by point RMSE in this run (the team accounting read recorded F, 51.845 against
  B's 57.276).
- **Margin M = 1.0 run** (about 2 percent of fWAR's recorded runs-allowed RMSE). NON-INFERIOR when
  `d - 1.645 sd_k > -M` under all three bootstraps. `p_ii = max over k of 1 - Phi((d + M) / sd_k)`.
- **Reported, deciding nothing:** C's wins, run differential and runs scored cells against F and B;
  C at eWAR v3's runs per win; d against the other source.

## 7. The adoption rule (Holm across the two)

- Holm at family-wise 0.05 over {p_i, p_ii}: the smaller p must be at or below 0.025 and the larger
  at or below 0.05.
- **ADOPT** when Holm rejects both nulls (the blend beats F9 and B9 on next-season runs allowed per
  inning, and C is non-inferior on the club runs-allowed accounting), the planted check of part 8
  reads PLANTED PASS and the identity check holds.
- **NOT ADOPT** otherwise. A read whose planted check failed is recorded as "UNRESOLVED (the design did
  not recover a planted blend)" and cannot ADOPT.

## 8. The null comparator, the identity check and the planted-recovery check

- **No-change null.** F9 (w = 1 everywhere) is the blend that changes nothing in eWAR; the blend must
  beat it (test (i)). Reported beside, deciding nothing: the fixed half-and-half blend (w = 0.5) and
  RA9*(Y) itself.
- **Identity check.** The blend with every w = 1 gives g(F9) = 0 exactly under every replicate and
  does not ADOPT; its departure D is 0 on every row.
- **The planted check, on the real design and on no real outcome.** It keeps the read's pitcher-
  seasons, roles, season IP, half IP, pairs and franchises, and replaces every run value by simulated
  ones. Per pitcher, two latent components follow an autoregressive path over 2016 to 2025 with
  season-to-season correlation 0.75: T_F (sd 0.5 runs per 9 for SP, 0.7 for RP) and u (sd 0.3 for SP,
  0.4 for RP). Half values are `F_h = T_F + eF / sqrt(IP_h)` and `B_h = T_F + u + eB / sqrt(IP_h)`
  with sigma_F 2.7, sigma_B 5.0 and error correlation 0.5; season values combine the halves by IP.
  - **Truth world:** the target in Y + 1 is `-(T_F + u)(Y + 1) - eT / sqrt(IP(Y + 1))`, eT with sd
    5.0: runs-allowed talent carries a part FanGraphs misses and that persists.
  - **Fake world:** the same, with u redrawn independently every season and left out of the target
    (`-T_F(Y + 1) - eT / sqrt(IP(Y + 1))`): the runs-allowed source carries a within-season signal
    that does not persist, so a blend toward it cannot forecast better than F.
  - Twenty replicates per world from a generator seeded 20261023; in each the whole procedure runs
    (moments, forward folds, blend, test (i) with B = 500 per bootstrap). Test (i) passes a replicate
    when p_i is at or below 0.025.
  - **PLANTED PASS** when the truth world passes in at least 16 of 20 replicates, the fake world in
    at most 1 of 20, and in the truth world the build's fitted w at each cell's median IP is within
    0.10 of the oracle weight (part 4's formula on the planted Sigma_T and Sigma_E), in mean absolute
    difference over cells and replicates.
  - The magnitudes are defaults taken from published orders of magnitude (pitcher true-talent spread
    in runs per 9, the persistence of FIP and of runs allowed, per-inning sampling error), not read
    from these pitcher-seasons. Test (ii)'s yardstick carries its own planted check (team accounting
    gate part 6), already recorded; it is rerun on C's departure pool and reported, deciding nothing.

## 9. Registered expectations

- **Prior evidence, disclosed (part 13):** in the eWAR v3 skill look (EBR_GATE.md 12.2, 866 pairs
  2021 to 2024) FanGraphs' FIP-based value ranked next-season RA9* about 0.05 better per inning than
  RA9* in Y did (S2's gap over B0 -0.0166 and over B0r +0.0352), while on season totals RA9* in Y did
  better (gap over B0r -0.0278 against -0.0136 over B0). Runs allowed are noisier per inning and carry
  information FIP misses.
- **Expectations** (predictions, not measurements): w near 1 below 40 IP and between 0.5 and 0.85 for
  starters at 100 IP or more; test (i)'s gap over B9 positive and its gap over F9 small, positive or
  near zero (the 50 IP floor keeps most rows where FIP is already the more reliable source), so test
  (i) is the binding test and UNRESOLVED or NOT ADOPT are plausible; test (ii) non-inferior (C moves
  pitching value toward runs allowed, which the accounting rewards: eWAR realized's R2 beat fWAR by
  10.652 runs there).

## 10. Refusals (checked before any statistic; a miss stops the read and writes nothing)

1. the frozen vintage, the eWAR v3 preview and the Baseball-Reference copy are present, and the
   preview's `fwar_vintage_id` equals the vintage's;
2. every season 2016 to 2025 but 2020 has its runner record and a pitcher source, the pitcher join
   misses at most 0.5 percent of plate appearances, and per season the appearance table's outs sum
   to the vintage's league outs within 1 percent;
3. per season, the sum over pitchers of runs charged R equals the runs scored on the runner record
   exactly;
4. each training cell's Sigma_E is positive definite before use; a fold whose pooled role moments
   are not stops the read.

## 11. The one read

1. Dry run on fixtures (`test_ewar_pitching_blend.py`): every reporting path on a synthetic design
   with null values, a missing source and a sparse cell, and the planted machinery on a synthetic
   design.
2. The planted check (part 8) and the identity check on the real design, which read no outcome,
   printed and recorded.
3. The read, ONCE: `python tools/ewar_pitching_blend_lab.py --read`, its stdout and stderr teed to the
   task's output directory before anything else runs. It checks part 10, prints the moments and the
   weights, the bootstraps' sd, then the cells, the p-values, the Holm decision and the reported
   blocks, and writes `data/_labs/ewar_pitching_blend/record.json`. A second `--read` refuses while
   the record exists.
4. **Crash protocol.** An exception before scoring began: fix and rerun, recorded. An exception after
   scoring began: STOP without rerunning, write the owner question, record VOID in part 14.
5. Part 14 records the result in a commit of its own.

## 12. What a result licenses

- **ADOPT licenses nothing served by itself.** The blend is built dark: `ewar_v3.PITCH_BLEND_LIVE`
  (default False) and a preview `.cache/ewar_v3/preview/ewar_v3_pitch_blend.json` carrying the
  headline series with C's departure, and one owner question, recorded in the task report and
  `DECISIONS_FOR_OWNER.md`: EWPB-Q1 (a) record only, nothing served (default); (b) serve the blend as
  the headline eWAR's pitching basis behind the flag, flipped by one AG4-Q flip commit (flag,
  registry row, glossary sentence, tests; the integrator regenerates `data/ewar_v3.json`); (c) (b)
  plus the blend as eWAR realized's pitching basis in place of R2.
- **NOT ADOPT:** the record and part 14 only; no owner question is required.
- May (after (b)): "eWAR's pitching value weights FanGraphs' FIP-based runs and Baseball-Reference's
  runs-allowed-based runs by how reliable each is at the pitcher's workload", with the frame and test
  (i)'s numbers. May not, under any result: that the blend measures talent; "validated" or "proven";
  any claim from a reported block.

## 13. Bans, and what was read before this registration

- **Bans.** The read relates no dark betting column to any game outcome or price
  (`docs/diamond-betting.md`); computes no realized MLB statistic by consensus-FV, FV or eFV cell
  (`docs/PROSPECT_ANCHOR_GATE.md`); reads no reserved eFV frame; runs no projections retrain and no
  `backtest.run_backtest`. It reopens nothing on EBR_GATE.md parts 12.2 and 12.3's lists: HEM+ and
  xHEM+, the S2 shrunk rates, S2b, the global HR shrink, DEM+, S3t, S3c, PE-P, the positional ladders
  v1 to v3, runs per win (FanGraphs' own is used, none is fitted) and eBR against BsR.
- **What was read before this registration (disclosed).**
  - EBR_GATE.md part 12.2's pitching cells (S2, S2b, PE-P against B0 and the B0r gaps printed beside),
    quoted in part 9.
  - EWAR_TEAM_ACCOUNTING's part 14: runs-allowed RMSE E 41.193, F 51.845, B 57.276 and the d of E
    against F (+10.652) and B (+16.083); C does not exist there.
  - To write this document the writer read the structure only: the runner record carries every
    season 2011 to 2026; the corpus carries the pitcher of record from 2018 (2020 aside); the cached
    StatsAPI play-by-play of 2016 and 2017 carries `matchup.pitcher` per at-bat index; the
    Baseball-Reference copy carries `runs_above_avg` and `IPouts` per stint; the vintage carries
    `fip`, `fipMinus`, `outs`, `gamesPitched` and `gamesStarted`. No moment, weight, blend value or
    correlation was computed.

## 14. Results

### 14.1 2026-10-22: the read, run once (lab at d711606d; local 2026-10-22 20:42, UTC 2026-10-23 00:42)

`python -u tools/ewar_pitching_blend_lab.py --read`, stdout and stderr teed to the task's output
directory; the record is `data/_labs/ewar_pitching_blend/record.json`. Inputs by sha256: the frozen
vintage `02232201...`, the eWAR v3 preview `fc640b01...`, the Baseball-Reference copy pit `3279bfbd...`,
`data/ewar_v3.json` `40ea0196...`; the runner record and corpus files per season are in the record.
Every refusal of part 10 held: zero plays without a pitcher in every season; appearance outs equal to
the vintage's league outs in every season; runs charged equal to runs scored (21,744, 22,582, 21,630,
23,467, 22,010, 20,817, 22,432, 21,343, 21,614 for 2016 to 2019 and 2021 to 2025); every fold's role
moments positive definite. 7,035 pitcher-seasons, all with both sources; 5,761 split rows; 1,307 pairs
(218, 223, 218, 216, 215, 217 for 2017, 2018, 2021 to 2024). No exception; runtime 82 s.

**VERDICT: UNRESOLVED (the design did not recover a planted blend).** The planted check read PLANTED
FAIL: the truth world passed test (i) in 14 of 20 replicates (16 needed), the fake world in 0 of 20,
and the fitted weights sat 0.112 from the oracle's in mean absolute difference (0.10 allowed). The
identity check held (gap 0 on every replicate). Under part 7 the read cannot ADOPT. The points say the
same thing on their own: the blend did not beat FanGraphs' FIP-based value, so the read would be NOT
ADOPT with a passing planted check.

**Test (i), next-season RA9* per inning** (pair-weighted within-season Spearman, B 4,000 per
bootstrap, seed 20261023):

| Series | rho | 2017 | 2018 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| blend (forward weights) | 0.3072 | 0.239 | 0.307 | 0.342 | 0.378 | 0.208 | 0.370 |
| F9, FanGraphs FIP-based | 0.3119 | 0.236 | 0.307 | 0.344 | 0.378 | 0.214 | 0.390 |
| B9, Baseball-Reference runs-allowed | 0.1962 | 0.193 | 0.193 | 0.256 | 0.179 | 0.181 | 0.174 |
| half and half (reported) | 0.2718 | 0.231 | 0.269 | 0.319 | 0.286 | 0.213 | 0.313 |
| RA9* in Y (reported) | 0.2307 | 0.267 | 0.254 | 0.257 | 0.195 | 0.166 | 0.243 |

| Comparator | Gap | sd player / club | lo (1.645 sd), player / club | p player / club |
|---|---|---|---|---|
| F9 (deciding) | -0.0046 | 0.0042 / 0.0044 | -0.0115 / -0.0119 | 0.866 / 0.852 |
| B9 (deciding) | +0.1111 | 0.0218 / 0.0212 | +0.0753 / +0.0761 | below 0.0001 / below 0.0001 |
| half and half (reported) | +0.0355 | 0.0129 / 0.0135 | +0.0143 / +0.0133 | 0.0030 / 0.0043 |
| RA9* in Y (reported) | +0.0766 | 0.0206 / 0.0223 | +0.0426 / +0.0398 | 0.0001 / 0.0003 |

p_i = 0.866: the blend beats Baseball-Reference's value by a wide margin and does not beat FanGraphs'.

**Test (ii), the club runs-allowed accounting** (the team accounting yardstick, B 4,000 per bootstrap,
seed 20261023): K* is F (runs-allowed RMSE 51.845 against B's 57.276); C's RMSE 51.217, d +0.628 runs;
sd season 0.388, club 0.747, player 0.872; lo -0.011, -0.601, -0.807, all above -1.0: NON-INFERIOR,
p_ii = 0.031. Holm over {0.866, 0.031} rejects neither (the smaller p is above 0.025). Reported,
deciding nothing: C against F on run differential d +1.657 (lo above 0 under all three bootstraps),
wins +0.033; C against B on runs allowed +6.059, run differential -4.553, wins -0.225. C's departure
carries 782.451 absolute wins over 7,035 rows, zero per season after the re-pin and 0 unallocated. The
yardstick's own planted check on C's departure pool recovered it in 2 of 20 replicates (fake 0 of 20).

**The weights (the build's fit, 2016 to 2025; w at each cell's median IP):**

| Role, IP band | Rows (split / season) | w at median IP | sigma2_F | sigma2_B | sigma_FB |
|---|---|---|---|---|---|
| SP 0-20 | 128 / 268 | 0.000 at 9.0 | 59.27 | 205.29 | 69.21 |
| SP 20-40 | 274 / 274 | 1.000 at 29.7 | 49.73 | 145.34 | 57.99 |
| SP 40-100 | 535 / 535 | 1.000 at 70.0 | 44.05 | 120.12 | 49.35 |
| SP 100+ | 1,147 / 1,147 | 0.849 at 155.0 | 32.30 | 85.16 | 33.89 |
| RP 0-20 | 773 / 1,907 | 0.000 at 8.0 | 42.43 | 133.57 | 48.41 |
| RP 20-40 | 976 / 976 | 1.000 at 29.0 | 39.34 | 112.47 | 43.75 |
| RP 40-100 | 1,878 / 1,878 | 1.000 at 59.5 | 29.67 | 80.39 | 28.77 |
| RP 100+ | 50 / 50 | 0.000 at 109.3 | 42.17 | 81.70 | 40.88 |

- Per inning, runs charged carry about 1.9 to 3.5 times FIP's error variance in every cell, and the two
  errors are strongly correlated (sigma_FB near sigma2_F).
- Between 20 and 100 IP the runs-allowed source adds no signal FanGraphs lacks: the signal
  covariances give w = 1 in all four cells. Starters at 100 IP or more take w 0.82 to 0.89 (the folds:
  0.74 in 2017, 0.91, 0.95, 0.88, 0.88 and 1.00 for 2018 to 2024). That is the only band where the
  blend differs from F9 on the pairs, and the gap shows it did not help.
- **A defect of the registered weight, disclosed and not repaired (the read ran once).** The two
  bands below 20 IP read w = 0 (all runs allowed), the opposite of the expectation of part 9. Their
  season rows include pitcher-seasons below 10 IP, which enter the signal covariance but not the
  split rows, and whose per-inning error the model understates (runs cluster within an outing), so
  part 4 reads their spread as signal (T_BB 169.4 and 51.0 runs squared per 9 squared, against 0.1 to
  0.3 above 20 IP). RP 100+ (50 rows) reads w = 0 on a near-zero F signal estimate. None of these cells
  touch test (i)'s pairs except RP 100+; they do carry C's departure on their rows in test (ii).
- The reported 20 IP floor block read the same 1,307 pairs as test (i) (the lab drew it from pairs
  already held to 50 IP), so it repeats test (i)'s points and adds nothing; disclosed, not rerun.

**What this licenses.** NOT ADOPT, recorded as UNRESOLVED: nothing is built behind
`ewar_v3.PITCH_BLEND_LIVE`, nothing is served, no owner question is raised (part 12), and no sentence
comparing the blend with fWAR or bWAR may be written. eWAR keeps FanGraphs' pitching runs in the
headline and R2 in eWAR realized. What the read measured, for any later pitching arm: on pitchers with
50 IP in both seasons FanGraphs' FIP-based value ranks next-season runs allowed better than
Baseball-Reference's runs-allowed value (rho 0.312 against 0.196) and better than any blend this
design produced; a measurement-error blend registered after this one needs an error model that holds
below 20 IP before its weights can be read there.
