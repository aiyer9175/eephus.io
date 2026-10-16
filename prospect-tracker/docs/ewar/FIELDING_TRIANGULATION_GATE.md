# Fielding triangulation: SDR, OAA, DRS, UZR and FanGraphs fielding as noisy readings of one skill (fielding_triangulation_v1)

Task EWAR_LADDER (owner decisions EW3-16, EW3-18, EW3-19, EW3-20 and its UZR amendment, EW3-23,
EW3-25, EW3-29; `C:/Users/noah/baseball-projects/_audit_2026-09-09/DECISIONS_FOR_OWNER.md`). This
document is committed ALONE, with its pin test `test_fielding_triangulation_registration.py` and
the dated amendment 11.5 of `docs/ebr-2026-09-30/EBR_GATE.md`, before any number of its
estimands is computed. It fixes the sources, the measurement model and its fit window, the eWAR
v3 part built from it, the read's frame, legs, comparators, statistics, twin, Holm family and
verdict, what the read licenses, and why the ladder half of the task is not re-read here. A change
after the first number is a dated entry in part 12 that says what changed and why, never an edit
above it. The read runs ONCE (part 5).

STATUS: REGISTERED, RESULTS EMPTY.

## 0. What this decides, and the route it takes

- **The question.** Treat each published fielding system as a noisy reading of one latent fielding
  skill per position. Does the reliability-weighted combination (the triangulation, T) forecast a
  player's fielding runs next season, measured by a system it did not read, better than the
  fielding the eWAR v3 frame carries today (FanGraphs' fielding runs, `Fld`), and does it carry
  at least as much information about next season's club runs allowed beyond FIP?
- **Why a model and not a rule.** The ewar-map plan (T3 step 3, "our own layer") asks the data to
  decide whether "OAA in the outfield, DRS in the infield" is right instead of asserting it. The
  weights below come from each source's persistence across seasons and from the sources'
  covariance within a season, per position, fitted once on 2016 to 2018 and frozen.
- **The route (the blend ban).** An OAA and DRS blend is on the 2026-09-09 plan's negative list
  outside the SDR gates G-A and G-B (`docs/master-plan-2026-09-09-fangraphs-ewar-betting.md`).
  This read is that route: its two deciding legs are G-A's forward leg (in the EW3-23 form G-A's
  C5 already uses: next-season fielding runs from a system the candidate did not read) and G-A's
  and G-B's team leg (next-season club runs allowed beyond FIP), with Holm across the two, as
  `docs/sdr-2026-08-18/SDR_EVAL_GATE.md` Amendment 2026-10-15 fixes them for SDR. G-B's merge
  object, a w-grid over eWAR v2's Baseball-Reference fielding, is not run: eWAR v2 is frozen by
  registration (`docs/ebr-2026-09-30/EBR_GATE.md` part 9.1), and the owner moved the fielding
  improvement into eWAR v3 (EW3-17, EW3-20). The eWAR route is candidate part 6's second arm S3t
  (EBR_GATE.md 11.5), which only the skill look admits.
- **SDR's own read.** In-house SDR failed G-A on 2026-10-15 (C1 self-persistence below OAA, C2
  below rfield, C5 UNRESOLVED; `data/sdr_eval.json`). This document does not re-read SDR alone as a
  candidate; SDR enters here as one reading among five, and part 5.6 reports, deciding nothing,
  whether SDR alone ranks next season's fielding as well as the triangulation (the owner's
  EW3-20 amendment ask).
- **Timing.** The fit and the read run on 2026-10-16 and are recorded as an OWNER-WAIVED EARLY
  READ (EW3-5). No data this read needs is missing: the 2026 regular season is complete.

## 1. Data (caches only; this task fetches nothing)

- **FanGraphs fielding leaderboard, combined over clubs, per season 2016 to 2026:**
  `.cache/sdr/home/defense_plus/data/raw/fg_field_full_<Y>.csv`, fetched by task EWAR_SDR_INHOUSE
  into `.cache/sdr/` (`.cache/sdr/fetch_manifest.json` holds each URL, sha256, row count and fetch
  time). One row per player-season-position. Columns read: `xMLBAMID`, `Pos`, `Inn` (FanGraphs
  thirds notation, read as `tools/sdr_eval_gate.fg_ip` reads it), `DRS`, `UZR`, `OAA`, `FRP`,
  `CFraming`, `bFRP`, `tFRP`. Pitcher rows (`Pos` P) are dropped.
- **UZR (the EW3-20 amendment).** The owner asked for UZR from the FanGraphs fielding leaderboard,
  all positions it rates, 2016 on, in `.cache/sdr/`. The cache above already holds it: UZR is
  populated on non-catcher rows for 2016 to 2024 and is empty for 2025 and 2026 in FanGraphs' own
  leaderboard. No fetch is made for it; a season FanGraphs does not publish is a missing reading
  (part 3.5), never filled.
- **FanGraphs fielding split by club:** `fg_field_split_<Y>.csv`, same folder (the club innings of
  part 5.3). **FanGraphs club pitching totals:** `fg_team_pit_<Y>.csv`, same folder (`R`, `FIP`,
  `IP`, `teamid`).
- **SDR:** the accepted drop `data/drops/wills/sdr_defense_card__2026-10-15.csv` (sha256
  8a41d1c2...358e, the drop G-A read), column `sdr_runs` (Will's 06 `dplus_runs`), and the two
  leave-one-system-out variants G-A's C5 built, `.cache/sdr/home/defense_plus/reports/
  06_defense_plus_<Y>__no_drs.csv` and `__no_statcast.csv` (column `dplus_runs`). SDR exists only
  on rows with 300 or more innings at the position, seasons 2017 to 2026.
- **The frozen fWAR vintage:** `data/fwar_vintage.json` (vintage id 2026-10-02-57bf90f7143e as it
  stands at the fit), hitting fields `fielding` (Fld), the framing residual Frm
  (`saber_feed.framing_residual`) and `plateAppearances`.
- **DEM+ constants by reference:** `dem_plus.K_INN` (the S3 shrink).
- **Baseball-Reference `runs_field`:** `.cache/war_daily/bat.parquet`, reported only (part 5.6),
  read as `tools/sdr_eval_gate.load_real` reads it.

## 2. The sources and what each measures

| Reading | What it is | System | Rates C | Seasons |
|---|---|---|---|---|
| SDR | Will's Defense+ composite: within position-season z-scores of OAA, DRS and FRP, reliability-weighted, shrunk by Inn / (Inn + 269) | reads DRS and Statcast | no (catchers carry component readings, part 3.6) | 2017 to 2026, 300+ innings rows |
| SDR without DRS / without Statcast | G-A C5's variants: 06 re-run with that system's weight at zero | Statcast only / DRS only | no | as SDR |
| OAA | Statcast outs above average, as FanGraphs republishes it per position | Statcast | no | 2016 on |
| DRS | Sports Info Solutions defensive runs saved | DRS (SIS data) | yes, not used for C here | 2016 on |
| UZR | FanGraphs' ultimate zone rating on SIS batted-ball data | shares DRS's data provider | no | 2016 to 2024 |
| FRP | FanGraphs Fielding Run Prevention: FanGraphs' fielding runs at the position | Statcast | catcher parts read in part 3.6 | 2016 on |
| DEM+ | rel x (Fld + Frm), rel = Inn / (Inn + K_INN): a fixed function of FanGraphs fielding and innings | as FanGraphs fielding | yes | 2016 on |

- **FanGraphs Fld at the position level is FRP.** The vintage's `fielding` is a player-season
  total; FRP is FanGraphs' fielding run value per position on the same leaderboard. Their
  same-season Pearson over non-catcher player-seasons read 0.967 (2017), 0.953 (2021) and 0.934
  (2025) in the census of part 10, so FRP is the position-level reading of the base's Fld.
- **DEM+ is nested, not a separate reading.** Row for row DEM+'s runs are FanGraphs fielding times
  a factor that depends on innings only. As a sixth column it would make the covariance of part 3
  singular and add no information. Its contribution, an innings-dependent shrink of FanGraphs
  fielding, is nested in the triangulation's own innings-dependent combination (part 3.4). The
  candidate part DEM+ already defines, S3, is kept as a reported comparator (part 5.6) and stays
  the first arm of candidate part 6. Part 11's per-position table lists DEM+ as "nested in FRP".
- **Systems,** for the leave-one-out rule of part 5.2: the DRS system is {DRS, UZR} (UZR shares
  DRS's batted-ball data provider, so a target from one never scores a reading of the other);
  the Statcast system is {OAA, FRP}; SDR reads both, so a leg that removes a system uses the SDR
  variant without it.

## 3. The measurement model (fit once on data seasons 2016 to 2018, frozen)

### 3.1 Rates and centring

For row r (player, season, position p, innings n_r) and reading s with runs y_s,r:

```
x_s,r  = 1000 * y_s,r / n_r                                runs per 1,000 innings
x_s,r <- x_s,r - (innings-weighted mean of x_s over the rows of (p, season) where s is present)
```

Every reading is centred within its own (position, season), so a source's league level at a
position (Statcast OAA in centre field is not centred by its publisher) never enters.

### 3.2 The fit sets (non-catcher positions 1B, 2B, 3B, SS, LF, CF, RF, each fitted alone)

- **Same-season set:** rows of data seasons 2016, 2017 and 2018 with n_r of 100 or more.
- **Cross-season set:** pairs (Y, Y + 1), Y in {2016, 2017}, of a player with 200 or more innings at
  p in both seasons. No 2019 row is read by the fit.
- The seven series fitted jointly: SDR, SDR without DRS, SDR without Statcast, OAA, DRS, UZR, FRP.

### 3.3 Signal, total and noise covariance

```
C_st   = mean over cross-season pairs with s in Y and t in Y+1 present of x_s(Y) * x_t(Y+1)
C      <- (C + C') / 2                                       the persistent signal shared by s and t
lambda = sqrt(max(e1, 0)) * v1                               e1, v1: the leading eigenpair of C;
                                                             sign so that the sum of lambda is positive
for each pair (s, t), s = t included, on same-season rows with both present:
  x_s,r * x_t,r = A_st + Psi_st * (1000 / n_r) + error       ordinary least squares, one intercept and
                                                             one slope per pair
A, Psi <- symmetric; A's eigenvalues floored at 0; Psi's at 0.001 * trace(Psi) / k
Sigma(n) = A + Psi * 1000 / n                                the total covariance of a row's readings
```

- A is the same-season signal covariance and Psi the per-inning noise covariance. Psi is a full
  matrix, so readings that share data (SDR and its inputs, DRS and UZR) carry correlated noise and
  are not counted as independent evidence. C is read across seasons, where measurement noise is
  independent whatever data two readings share, so lambda carries only skill that persists.
- **Floors.** A pair (s, t) with fewer than 30 same-season rows, or a series with fewer than 20
  cross-season pairs against FRP, drops that series from the position's model; the fit log says so.

### 3.4 The triangulated rate of a row (the best linear predictor)

```
a        = the readings present on row r (among the configuration's readings, part 3.5)
T_rate,r = lambda_FRP * lambda_a' Sigma_aa(n_r)^-1 x_a,r     0 when a is empty
T_runs,r = T_rate,r * n_r / 1000
```

T_rate is the best linear predictor of the row's next-season FanGraphs fielding rate (FRP, the
base's scale) from the readings it has, at its own innings: few innings shrink it toward 0, a
reading with large noise or little persistence gets little weight, two readings that share noise
share weight. It nests DEM+'s innings shrink of a single reading.

### 3.5 Configurations and missing readings

| Configuration | Readings | Used by |
|---|---|---|
| FULL | SDR, OAA, DRS, UZR, FRP | the eWAR part S3t (part 4), the team leg (part 5.3), every reported cell not named below |
| X_DRS | SDR without DRS, OAA, FRP | the forward leg's DRS-system target (part 5.2) |
| X_UZR | SDR without DRS, OAA, FRP | the forward leg's UZR target (part 5.2) |
| X_SC | SDR without Statcast, DRS, UZR | the forward leg's Statcast target (part 5.2) |

A configuration uses the sub-blocks of the one joint fit; nothing is refitted per configuration.
A reading missing on a row (SDR below 300 innings or in 2016, UZR after 2024, OAA where Statcast
publishes none) is left out of a for that row only.

### 3.6 Catchers: SDR's catcher components only

OAA and UZR do not rate catchers. Catchers are valued on SDR's catcher components (Will's
25_catcher_components.py: framing, blocking, throwing), each in runs and shrunk by its own
reliability:

```
components k: framing  = CFraming (the drop's framing_runs, FanGraphs' framing runs)
              blocking = bFRP     (Statcast blocking runs as FanGraphs hosts them)
              throwing = tFRP     (Statcast throwing runs as FanGraphs hosts them)
r_k   = Pearson of the component's rate (runs per 1,000 innings, centred within season) in Y and Y+1
        on pairs Y in {2016, 2017} of catchers with 300+ innings at C in both seasons,
        clamped to 0.05 to 0.95
K_k   = hm * (1 - r_k) / r_k        hm: the mean over those pairs of the harmonic mean of the two
                                     innings, rounded to a whole inning (B1's rule, swar_lab.fit_b1)
T_C,r = sum over k of y_k,r * n_r / (n_r + K_k)                 runs, 0 for a missing component
```

- Disclosed: the drop's blocking column is Savant's and starts in 2018, so it has no pair inside
  the fit window; FanGraphs' Statcast blocking (bFRP, 2016 on) stands in. Will's stage measures
  throwing by pop time, which is not in runs; tFRP is the runs reading of the same skill.

### 3.7 What the fit writes

`tools/fielding_triangulation_lab.py fit` writes `data/_labs/fielding_triangulation_fit.json`
once, in its own commit before the read: per position lambda, A, Psi, the dropped series, the row
and pair counts, and the weights w(n) = lambda_FRP * Sigma(n)^-1 lambda at n = 500 and 1,000
innings on FULL; the three catcher K_k with their r and pair counts; the input sha256s. The fit
reads no season after 2018 and no target of part 5. The read refits nothing.

## 4. The eWAR v3 part S3t (candidate part 6, second arm; scored only by the skill look)

```
hitter i, season s:
  T_i      = sum over i's non-catcher rows r of T_runs,r (FULL) + sum over i's catcher rows of T_C,r
  g_fldt,i = T_i - (Fld_i + Frm_i if i caught, else Fld_i)      the base's fielding, dem_plus.fld_total
  d_fldt,i = g_fldt,i - PA_i * (sum_k g_fldt,k) / (sum_k PA_k)   swar.recentre, per season, hitters
  test value (part 9.4 form)   fWAR_i + d_fldt,i / RPW_s
```

- Seasons 2016 on, as S3. Pitcher-batters carry 0 (S3's rule). A hitter with no fielding row
  carries T_i = 0 and g = minus his base fielding, then the re-centring.
- **Invariants** (pinned in `test_fielding_triangulation.py`): (1) a row with no reading carries
  T 0; (2) d_fldt sums to 0 per season within 1e-9 runs; (3) a pitcher-batter carries 0; (4) a
  reading that is absent on every row leaves every T unchanged; (5) with one reading, T_rate equals
  lambda_FRP * lambda_s * x_s / (A_ss + Psi_ss * 1000 / n); (6) catcher K_k infinite gives T_C 0;
  (7) the build never writes `data/ewar.json` and imports no `fg_leaderboards`.
- How the skill look scores it, and what admits it: EBR_GATE.md 11.5. This document's read
  (part 5) decides only whether S3t is scored there at all (part 5.5).

## 5. The read (once; G-A's forward leg and G-A/G-B's team leg, Holm k = 2)

### 5.1 Frame

- Predictor seasons Y = 2019 to 2025, outcome seasons 2020 to 2026: every predictor season is
  after the fit window. Pairs touching 2020 are included (per-inning rates); the pooled statistics
  without them are printed beside, deciding nothing.
- Bootstrap B = 2,000, seed 20261016 (this document's commit date as YYYYMMDD); the twin's
  permutation seed 20261017.
- **Floors first.** Before any gap, the run prints each deciding leg's bootstrap sd, 95 percent
  half-width and MDE95 = 1.645 sd.

### 5.2 Leg L1, forward on next season's fielding runs from a system the candidate did not read

- **Rows:** non-catcher player-season-position rows with 300 or more innings at the position (G-A's
  frame rows). A player-season's rate of a reading m is the sum of m's runs over his frame rows
  where m is present, divided by those rows' innings; for T it is the sum of T_runs over all his
  frame rows divided by their innings.
- **Pairs:** a player with frame rows in Y and in Y + 1.
- **Three systems, each scored on its own pairs:**

| System left out | Target, rate in Y + 1 | T configuration | Comparator in Y (does not read the target's system) |
|---|---|---|---|
| DRS | DRS per inning | X_DRS | FRP (the base's fielding at the position) |
| Statcast | FRP per inning | X_SC | DRS |
| UZR | UZR per inning, Y + 1 at most 2024 | X_UZR | FRP |

  The UZR leg also leaves DRS out because the two share a data provider. On the Statcast leg the
  base's own fielding cannot be the comparator (it is the target's system), so the incumbent that
  does not read Statcast stands in, as in G-A's C5.
- **Statistic:** per system, gap_S = Spearman(T configuration rate in Y, target in Y + 1) minus
  Spearman(comparator rate in Y, target in Y + 1), on the pairs where all three are present. The
  leg's gap is the mean of the three gaps. One player-clustered bootstrap (players drawn with
  replacement with all their pairs; the three gaps recomputed on the same draw): LB95 the 2.5th
  percentile of the leg's gap, one-sided p the share of draws at or below 0.
- **L1 passes** when its gap is above 0, LB95 is above 0, Holm (part 5.4) rejects, and its twin
  does not pass the same rule.

### 5.3 Leg L2, next season's club runs allowed beyond FIP, roster-weighted

- **Player rates in Y (all rows, all positions, any innings):** T on FULL, rate_T,i = (sum of
  T_runs over his non-catcher rows + sum of T_C over his catcher rows) / his fielding innings; the
  base, rate_B0,i = (Fld_i + Frm_i if he caught) / his fielding innings, from the vintage.
- **Roster weighting (EBR_GATE.md 11.2.4's form, turnover handled):** for club c in Y + 1,
  S_c = sum over players of rate_i(Y) * n_ic(Y + 1), n_ic his non-pitcher fielding innings with c
  in Y + 1 (FanGraphs split by club, `teamid`). A player with no fielding innings in Y enters at 0.
  S_c is standardized within its season.
- **Target:** club runs allowed in Y + 1 residualized on club FIP runs within the season (G-A's
  construction, `tools/sdr_eval_gate.club_target`: R on FIP x IP / 9, least squares across the 30
  clubs, standardized, sign reversed so fewer runs than FIP implies ranks higher).
- **Statistic:** Spearman of S_c with the target pooled over the club-season pairs (30 a season, 7
  seasons); gap = rho(T) minus rho(B0). Player-clustered bootstrap (players drawn with replacement,
  every club sum recomputed from the drawn players, outcomes fixed), the deciding interval; a
  club-clustered bootstrap (franchises drawn with all their club-seasons) printed beside.
- **L2 passes** when its gap is above 0, its player-clustered LB95 is above 0, Holm rejects and its
  twin does not pass. **NON-INFERIOR** (part 5.5's flag) when gap minus 1.645 sd is above -0.02
  under both bootstraps.

### 5.4 Holm, twins, verdict

- **Holm** across L1 and L2 at alpha 0.05 on the one-sided p.
- **The twin, per leg:** T's row rates permuted within (position, season) among the leg's rows
  (frame rows for L1, every rated row for L2), seed 20261017, one draw, each configuration
  permuted on its own rows with the same seed; scored by the leg's rule with its own Holm pair. A
  leg is not creditable if its twin passes.
- **Verdict:** PASS when L1 and L2 both pass; PARTIAL when one does; FAIL when neither does (G-A's
  rule). A null is a complete result.

### 5.5 What the read decides for the skill look

S3t is scored in the eWAR v3 skill look (EBR_GATE.md 11.5) only when L1 passes AND L2 is
NON-INFERIOR. Otherwise S3t is not scored, candidate part 6 keeps S3 as its only arm (Holm k = 2),
and the record says so. Nothing else follows from this read: no served number moves, nothing
enters eWAR v2, and the skill look alone admits a part into eWAR v3.

### 5.6 Reported beside, deciding nothing

- **Per position:** loadings, the diagonal of A and Psi, the FULL weights w(500) and w(1,000) and
  each reading's share of them; a reading "carries weight" at a position when its share of the
  absolute weights at 1,000 innings is 0.10 or more. The three catcher K_k.
- **SDR alone against the triangulation** (the EW3-20 amendment ask): on each L1 system's pairs, the
  matching SDR (without DRS on the DRS and UZR legs, without Statcast on the Statcast leg) against
  that leg's T configuration, the gap SDR minus T with its bootstrap interval, pooled (mean of the
  three) and per position.
- **S3 (DEM+'s shrink of FanGraphs fielding)** on the DRS and UZR legs (it reads Statcast), and on
  L2; **the equal-weight blend** (the mean of the present readings' within position-season
  z-scores, in FRP's runs by FRP's within position-season sd) on every leg; **B-Ref rfield** on L2.
- **L1 per position** (each position's pairs, the three gaps and their mean, intervals), the
  without-2020 values of both legs, the club-clustered interval of L2.
- **Catchers:** catchers with 300+ innings at C in Y and Y + 1, T_C against the base's catcher
  fielding (FRP + CFraming at C) on DRS per inning at C in Y + 1, with its interval.
- **Same-season agreement** of T (FULL) with each reading (Spearman, non-catcher frame rows).
- **Face validity:** the top and bottom ten by T_runs per position in 2026, named.

## 6. What each result licenses

- **PASS or PARTIAL** licenses one sentence, with its frame and numbers: "on 2019 to 2025 seasons,
  a reliability-weighted combination of SDR, OAA, DRS, UZR and FanGraphs fielding ranked the next
  season's fielding runs, measured by a system it did not read, better than a single system did
  (Spearman gap +x, 95 percent interval a to b, n pairs)", and for L2 only on its own pass, "and
  tracked the next season's club runs allowed beyond FIP better than FanGraphs fielding". No
  sentence claims "better defense metric", "true talent" or "more accurate WAR".
- **FAIL** licenses no comparative sentence. The measurement may be described as a measurement.
- **Registry:** a row `fielding_triangulation` (verdict provisional, `measured_not_adopted` unless
  the skill look later admits S3t), eval artifact `data/fielding_triangulation_eval.json`, written
  by an idempotent script that keeps the registry's line endings. MODEL_REGISTRY.md is regenerated.
- **Served:** nothing. No page reads T, no exporter writes it, and no flag exists.

## 7. Registered expectations (predictions, not measurements)

L1's gap is small and positive and most likely UNRESOLVED at LB95: G-A's C5, the closest prior
read (SDR without a system against the incumbent not reading it, on overlapping pairs), read a gap
near zero with an interval spanning it. L2 is underpowered (210 club-season pairs) and most likely
fails at LB95 while staying NON-INFERIOR. Both twins fail. The weights load on OAA and FRP in the
outfield and spread over DRS, OAA and FRP in the infield; DEM+ carries none of its own. SDR alone
ties the triangulation (SDR is itself a reliability-weighted blend of three of the five readings).
The verdict most likely FAIL or PARTIAL.

## 8. Power

No power figure is computed before the read, because one would relate a reading to a next-season
quantity on the read's own pairs. For scale only: G-A's C1 on 1,644 SDR pairs (2017 to 2025)
printed a 95 percent half-width near 0.04 for a difference of two Spearman correlations; this
read's L1 has fewer pairs (predictor seasons 2019 to 2025) and averages three gaps, and its L2 has
210 club pairs against G-A's 270. Where the printed MDE95 exceeds a gap, the record says the leg
could not see it.

## 9. The ladder half of the task, and the Position Fit scale defect

- **Not re-read here (DEFERRED to an unseen frame).** EW3-25 lets this task refine the positional
  ladder only through the ladder's own pass rule; EW3-29 says build on LADDER_V3_REREAD's outcome.
  That outcome (`docs/ewar/LADDER_V3_GATE.md` part 9): v3 failed criteria 1, 3 and 5 on the
  2016 to 2026 seasons; an all-zero fielding ladder scored within its interval; the real design is
  too thin to recover a planted gap; v1 stays on Position Fit and no ladder artifact exists. Every
  season of switchers has now been read twice (v2 and v3). A ladder built on the triangulated
  fielding of this document and scored on the same seasons would be a third choice among looks at
  the same rows, under a rule whose zero comparator already ties. The honest frame for any further
  ladder is the 2027 season's switchers, which do not exist yet. No ladder number is computed by
  this task.
- **The Position Fit scale defect** (2026-09-09 plan :329: a Statcast-scale D(p) composed with the
  Baseball-Reference-scale ladder) was confirmed by EWAR_LADDER_REDERIVE and fixed there
  (`positional_fit.POSFIT_ONE_SCALE = True`, `docs/ewar/LADDER_V2_GATE.md` part 8), and the fix was
  kept by LADDER_V2_REVERT (b1d2e94f). Nothing further is owed here.

## 10. What was read before this registration

- **Census, same-season only, no next-season quantity:** row counts and the share of non-catcher
  rows carrying each reading per season (DRS on every row; OAA about 0.85 to 0.88; FRP 0.93 to 0.96;
  UZR 0.80 to 0.86 through 2024 and none after; no OAA or UZR on any catcher row); the same-season
  Pearson of FRP summed per player-season with the vintage's Fld (part 2); that catcher FRP is the
  sum of its blocking, throwing and framing parts and that the vintage's Frm equals CFraming
  exactly; the columns of the SDR variant reports. None relates a reading to another season.
- **Prior reads on overlapping pairs,** each a published record: G-A (`data/sdr_eval.json`: C1, C2,
  C5, C6 and the per-position cells, predictor seasons 2017 to 2025, SDR, OAA, rfield, DRS, FRP and
  UZR self-persistence and cross-system cells); DEM+'s gate (`docs/dem-plus-2026-09-11/
  DEM_PLUS_GATE.md`, FanGraphs fielding's own next-season rate); the K_INN fit (2016 to 2018). This
  read is therefore not blind on the single readings' persistence. The fit window excludes every
  predictor season of the read, and the twin carries the blind weight.
- No number of T, of any weight, loading or K of part 3, or of any leg of part 5 exists at this
  commit: no code computes them yet.

## 11. Results

EMPTY.

## 12. Amendments

EMPTY.
