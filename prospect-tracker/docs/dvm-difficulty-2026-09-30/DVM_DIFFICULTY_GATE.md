# DvM+ development-difficulty gate: DVM_DIFFICULTY_GATE (registered 2026-10-07)

Registration status: REGISTERED

Covers one study, ordered by the owner on 2026-09-30 (ask 6, verbatim): "Weight DvM+ by
difficulty of developing FV / different traits in different groups (HS prep prospects vs
college prospects vs IFA prospects: what traits are easier / harder to develop?).
Additionally, it is probably harder to develop from 60 FV -> 70 FV than it is to develop
from 40 FV -> 50 FV, can we check to see if this is true and weight DvM+ accordingly?"

The design is the Part 8 lane `dvm_difficulty.md` (Parts C, D and E; DVM-2 of its Part H),
summarized in the final-pass plan as P8.7 ("DvM+ weighted by development difficulty"). The
owner's answers Q-DVM-1 to Q-DVM-6 (2026-10-01, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
the two "ANSWERED 2026-10-01" tables that carry them) bind every section below; each is the
recommended option (A). Producer: `tools/dvm_difficulty_lab.py` (its frame module was
committed as DVM-1 at `14c45886`; the model, the read and the validation are DVM-3, built
on fixtures only, after this commit). Artifacts, written ONLY by the one look:
`data/dvm_difficulty.json` and `data/dvm_difficulty_eval.json`. Pinned by
`test_dvm_difficulty_gate.py`. Registry row: a new `dvm_difficulty` row written at the look.

This document is committed ALONE, before any grade difference, growth statistic or rate is
computed on real data. Sections 1 to 17 are frozen at this commit. Section 18 is EMPTY and
is filled only with the look's verbatim output. No em-dashes. No statistic here, in the lab
or in its artifacts is a realized MLB outcome cut by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`); section 2 and section 14 say why this study is not one
and what it waits for anyway.

---

## 0. What was already seen

- Counts only. The lane's inventory (`dvm_difficulty.md` Part B, on the archived 2026-09-04
  store opened read-only) and the DVM-1 frame counts (`14c45886`; `frame_counts.json` and
  `power_block.json` in the DVM-1 task directory and under `.cache/dvm_difficulty/`) read
  start reads, list slots, completed pairs by source, side and start year (never by rung),
  origin coverage of START reads by side and rung (inputs), level and age coverage, and the
  clustering. No grade difference, growth, rate by rung, WAR, debut or graduation quantity
  was computed by either.
- One disclosure carried from the lane (`dvm_difficulty.md` D.5): its pooled list-presence
  counts for start years 2019 to 2021 are the only R-LV-touching numbers it read; they are
  pooled over side and rung, and no grade or outcome was read.
- The served DvM+ family already computes on every grade step in its windows, the 2020 and
  2021 lists included (FV-DvM+ 7y window; the Tendencies toolDev panel). That is serving,
  not this study's read, and it adjudicates nothing here.

## 1. Preconditions at this commit

| id | precondition | state at registration |
|---|---|---|
| P-1 | VAL_4's tenure table, or the lab's own tenure split registered as the fallback | VAL_4 not built (`docs/farm-attribution-2026-09-25/` absent); the fallback is registered in section 7 |
| P-2 | origin unknown share at most 0.05 overall and at most 0.10 in every side x rung cell used for H1 | HOLDS: 31 of 14,961 start reads (0.0021); largest cell pit 60, 2 of 189 (DVM-1, `14c45886`) |
| P-3 | level and age coverage from the outcome-blind identity, by side and list year | PUBLISHED (DVM-1 `level_age_coverage_by_side_year`) |
| P-4 | the 2026 MLB Pipeline preseason list backfilled, or the 2025 to 2026 step declared FanGraphs and BA only | DECLARED: 7 frame reads in the store; the step is FanGraphs and Baseball America only (`PIPELINE_2026_PRESEASON_DECLARED_ABSENT`) |
| P-5 | the power block recomputed on the frozen frame and written here | section 12 |
| Q | owner answers Q-DVM-1 to Q-DVM-3 (and Q-DVM-4 to Q-DVM-6) | ANSWERED, all A |
| E | the ETA look record (`docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md` section 8) | EXISTS: SHIP CANDIDATE, arm B recommended (`be53132d`, 2026-09-30) |
| Z | the fWAR label epoch's step Z entry (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9) | RECORDED 2026-10-03 |

## 2. Frame (lane C.1 and C.2)

**Unit.** A row is a same-source pair `i = (player p, source s, start list year V, horizon h)`,
h in {1, 2} years, s in {MLB Pipeline, FanGraphs, Baseball America} (Q-DVM-4 A: each source's
own printed grades, list to list; never the eFV retrospective series). Start read: s's latest
active read of p inside `[V-01-01, min(V-05-01, debut))` (the window of
`efv_vintage_frame.window_bounds`, parity pinned by `test_dvm_difficulty_frame.py`). End
read: s's latest read inside `[V+h-01-01, min(V+h-05-01, debut))`. International boards,
overseas boards and graduate lists are not preseason lists. A source publishes a list in a
year when it holds at least 100 reads there (`MIN_LIST_READS = 100`); a source with no list
in V+h puts the row out of frame (not censored). The 12-month horizon drives the served index
(Q-DVM-5 A, annual preseason steps); 24 months is the hypothesis read's second horizon and a
sensitivity.

**Frame rules.**

| rule | excludes | lifted when |
|---|---|---|
| F-R1 | any read in list year 2020 or 2021, so any pair with an endpoint in either (eFV R-LV, `efv_vintage_frame.RESERVED_LV`) | the R-LV look record exists in `docs/efv-v2/EFV_V2_GATE.md` part 9 (`## 9. Results`) when the look starts (Q-DVM-1 A) |
| F-R2 | any end read that is the debut-year preseason read of a player who debuted in 2025 or later (an R-VM input grade, `R_VM_FIRST_DEBUT_YEAR = 2025`); such a read is never loaded, grade or printed origin | not at this look, on any path |
| F-R3 | the lab builds no frame before the ETA look record exists (a VOID counts) | met (section 1, row E) |
| F-R4 | no WAR, no `career_war`, no label module, no debut, graduation or bust rate by rung, no read of `value_framework.fv_to_6yr_avg_war` | never |
| F-R5 | no eFV input of any kind (`xfv_history`, `xfv.json`, V2 scores, any `efv_*` module except the outcome-blind `efv_identity`) | never |

F-R2 holds on every path of this look (a default: one frame rule instead of a per-cohort
lift, so the R-VM looks' state cannot change this frame).

**The two frames, decided only by whether a record exists (outcome-blind).**
- FULL: the R-LV record exists when the look starts. Every published list year is read,
  2020 and 2021 included.
- COMPLEMENT: no R-LV record exists and the date is on or after 2027-01-31. List years 2020
  and 2021 stay out.
The look reports which frame it read in its first output line.

**The store.** The look reads the copy frozen by the SQLite backup API at registration time:
`.cache/dvm_difficulty/prospects_frozen.db`, frozen 2026-10-03T21:36:18Z, sha256
`7d7e56533e6c62ef3ec3d8400e079974779ea59ca533dbc0e43939f596d6a56e`. If that file is missing
or its sha256 differs at the look, the look takes a fresh backup-API copy, prints both
hashes, recounts the complement-frame start reads and completed pairs, and STOPS with an
owner question if either count differs from section 12's (14,961 start reads; 8,020 and
3,205 completed pairs) by more than 1 percent.

## 3. Outcome and censoring (lane C.3)

```
G      = fv + 2.5 x fv_plus          the source's own 20-80 grade; FanGraphs "45+" = 47.5
y_i    = G_end - G_start             grade growth, points
w_i    = W(G_end) - W(G_start)       value growth
W      = storage.FV_EXPECTED_WAR linearly interpolated (storage._fv_to_expected_war):
         20 0.0, 25 0.0, 30 0.0, 35 0.1, 40 0.5, 45 1.5, 50 3.0, 55 6.0, 60 12.0,
         65 17.0, 70 25.0, 75 40.0, 80 60.0
```

W is a fixed primer table, not a realized quantity; the lab copies it (the lab never imports
`storage`) and a parity test pins the copy. FV_EXPECTED_WAR is not changed by this study.

A missing end read is coded by a rule fixed here, before any growth is read:
- **Graduated** (debut before the end window closed): `G_end` = the last same-source read
  before the debut.
- **Dropped** (in affiliated ball, absent from the source's end list): `G_end` = one rung (5
  points) below the lowest grade that source printed for his club at V+h, never above
  `G_start`.
- **Exited** (no affiliated activity in season V+h-1 or V+h, from the minor league caches
  through the outcome-blind identity): coded as dropped.

Sensitivity frames, reported beside the primary: **S1** drops every censored row; **S2**
codes graduates at `G_start + 5`. Censored counts are published pooled over side and rung,
never by rung (F-R4).

Tool rows (section 8): a graduated row takes the tool grade of the last same-source read
before the debut; a dropped or exited row has no tool end grade and leaves the tool frame
(a default: no tool analogue of the drop rule exists). Tool S2 codes a graduate's tool at its
start grade + 5; tool S1 drops graduates too.

## 4. Covariates, all as of the start read (lane C.4)

- side: hit or pit from the position at the start read; two-way players are hitters.
- start rung `r = 5 x floor(G_start / 5)`, cells `<=35, 40, 45, 50, 55, 60, 65+`.
- origin g in {HS, college (junior college folded in, reported apart where n allows), IFA
  amateur, pro/overseas (signed at 21 or older, or an NPB, KBO, CPBL or Cuba pro), unknown};
  precedence as DVM-1 built it: the FanGraphs list-printed origin, then
  `draft_players.player_type`, the overseas tables and `acquisitions`, the parsed MLB
  Pipeline report text, the age rule last, then the IFA entry rule (disjoint from the age
  rule). Never `players.birth_date`.
- level band L in {pre-pro, DSL/CPX, A/A+, AA/AAA, unresolved} and `age_rel` (bounded at 3)
  from the last completed minor league season before V on the outcome-blind identity;
  `agemiss` flag. "unresolved" (an ambiguous or missing identity) is its own band (a
  default; DVM-1 counts these reads per side and year).
- source s and list year V.
- tool rows only: the start tool-grade rung, the start FV rung, and on FanGraphs rows the
  start future-minus-present gap with a "gap known" flag.

## 5. The model: location, shrinkage, scale (lane C.5, exact)

Weighted least squares per side, weight `omega_i = 1 / n_sources(p, V, h)` so a player-year
counts once however many sources list him:

```
y_i = a[s,V] + b[s,side,r] + c[side,g] + d[side,L] + e[side]*age_rel_i + f[side]*agemiss_i
      + u[side,g,r] + eps_i

u[c]      shrunk origin-by-rung interaction for cell c = (side, g, r):
          u_hat[c] = n_c / (n_c + k_u) * mean_c(residual of the additive fit)   if n_c >= 20
          u_hat[c] = 0                                                           if n_c <  20
k_u       = max(20, s2_eps / tau2_u),  tau2_u = max(0, var_c(mean residual) - mean_c(s2_eps / n_c))
            (method of moments across cells, frozen into the table artifact; tau2_u = 0 means
            no interaction survives and every u_hat is 0)
E_i       = additive fit + u_hat[c(i)]                       expected grade growth
s_hat     = sqrt( (nu_c * s2_c + 30 * s2_side) / (nu_c + 30) ),  cell c = (side, r), nu_c = n_c - 1
            (spread of y - E, shrunk toward the side spread with 30 pseudo degrees of freedom:
            the spread floor)
E^W_i     = the same model with w_i as the outcome           expected value growth
```

`b[s,side,r]` needs 30 pairs in its cell or it pools across sources (`b[side,r]`, with the
source effect carried by `a`). At serve time each (source, step year) is re-centered to a
league-mean residual of 0. The fitted table, the u cells, the spreads, `k_u`, `tau2_u` and
`k_org` are frozen into `data/dvm_difficulty.json` at the look.

## 6. Row credit (lane C.6 and C.7; owner answer Q-DVM-2 A)

- **DV, value above expected (the owner's choice):** `v_i = w_i - E^W_i`, in expected-WAR
  units. It keeps the tail weighting of the W table (a 70 to 80 counts at least 10 times a
  40 to 50, `test_dvm_tail_weight.py`) and adds difficulty through the expectation.
- **D0, difficulty only (reported, not served):** `z_i = (y_i - E_i) / s_hat[side, r_i]`; a
  mid-PIT normal score of y under its cell's step distribution is reported beside it, and if
  the two club indices correlate below 0.9 the read says so.

The owner's 60 to 70 against 40 to 50 question, as a credit ratio read at the look (origin,
level, age and source held at the frame's pooled mix):

| statistic | ratio, 60 to 70 over 40 to 50 |
|---|---|
| today's FV-DvM+ (arithmetic on the table) | 13.0 / 2.5 = 5.2 |
| DV | (13.0 - E^W[60]) / (2.5 - E^W[40]) |
| D0 | ((10 - E[60]) / s_hat[60]) / ((10 - E[40]) / s_hat[40]) |

A ratio whose denominator is at or below 0 is printed as "undefined" with both terms.

## 7. Club aggregation (lane C.8)

For club o and window W (12-month steps whose end list year falls in the window), clubs
joined through `trades.canonical_org` (30 clubs):

```
tau_io    share of pair i's days that player p spent with club o
D_o       = sum_i tau_io * omega_i * c_i / sum_i tau_io * omega_i         c = v (DV) or z (D0)
N_o       = (sum_i tau_io * omega_i)^2 / sum_i (tau_io * omega_i)^2       Kish effective n
D~_o      = D_o * N_o / (N_o + k_org)                                     shrink toward 0
k_org     = s2_within / tau2_org by method of moments on the fit frame, bounded to [5, 50], frozen
DvM+_o[W] = 100 + 10 * (D~_o - mean(D~)) / sd(D~)   across the 30 clubs, unclamped, rounded to nearest
```

A club-window publishes only with `N_o >= 10`; below that the cell renders " - ". The cohort
(hitter, pitcher) and bucket (C, INF, OF, SP, RP) versions restrict the pairs; the 3-way
blend, its over-grading penalty and the bucket weights are unchanged.

**Tenure shares (P-1).** VAL_4's tenure table if it is committed when the look starts;
otherwise this fallback, registered here: the pair's interval runs from the start read's date
to the end read's date (for a censored row, to the end window's close, capped at the debut);
on each day the club is the club printed on the player's latest read of any source dated on
or before that day (international and overseas boards excluded), overridden by a later
`trades` row's `to_org`, both canonicalized; `tau_io` is the share of the interval's days at
club o, and the shares of a pair sum to 1. The receipt names which tenure source was read.

## 8. Tools (lane C.9)

Per tool t, the model of section 5 on future tool-grade growth with the start tool rung in
place of the FV rung and the tool covariates of section 4, credited as D0 (`z` in tool-grade
spread units; Q-DVM-2 A: the FV-to-WAR table means nothing for a single tool), aggregated
per club and tool as in section 7, and combined with the existing position-importance
weights (`storage._BUCKET_TOOL_IMPORTANCE`). The FV-to-WAR transform, the tool level weights
and the 1.35 stretch are dropped from the tool credit: level and age sit in the expectation.
The Tendencies toolDev panel reads the same per-tool residuals at the flip.

## 9. The player index (lane C.10; owner answer Q-DVM-6 A)

Player index = the mean of the player's own DV credits over his last 3 annual steps (each
step's credit de-duplicated across sources by `omega`), shrunk `n / (n + 2)`, published
`100 + 10 * value / sd` across actives, rounded to nearest, labelled "DvM+ (player)"; the
payload key `dollar_dvm_plus` is kept. It conditions on the START rung and uses shrunk spreads.

## 10. H1: traits easier or harder to develop by origin group (lane D.2)

For side and trait t in {hit: FV, hit, game_pwr, raw_pwr, speed, field, arm; pit: FV, fb,
sl, cb, ch, cmd} (13 traits), contrasts HS minus college, IFA minus college, HS minus IFA:

```
Theta_total(g1,g2)  = E[y | g1, r] - E[y | g2, r], averaged over r with the pooled start-rung
                      weights of trait t; controls: source x year only
Theta_direct(g1,g2) = c[side,g1] - c[side,g2] in the full model of section 5 (adds level band,
                      age_rel, agemiss)
```

- Horizon: 12 months primary; 24 months secondary, in Holm families of its own that grant no
  verdict word.
- Inference: player-clustered bootstrap (resample players; a drawn player brings all his
  rows), B 2000, seed 20261201, percentile CI95, two-sided p = 2 x min(share <= 0, share >= 0),
  floored at 1/B.
- Multiplicity: one Holm family per estimand, 13 traits x 3 contrasts = 39 cells each (Theta_total
  39, Theta_direct 39). pitch_sel, bat_ctrl (FanGraphs only) and ct (thin) are descriptive,
  outside the families.
- Minimum n: each compared group needs 100 completed pairs for that side and trait; else the
  cell reads "unpowered", is shown descriptively, and keeps its place in the family with p = 1.
- Verdict word ("easier for HS hitters") only when all hold: Holm-resolved on the primary
  censoring frame; the same sign under S1 and S2; the same sign on Pipeline and FanGraphs
  separately; the same sign in at least two of three eras by start list year (2011-2016,
  2017-2019, 2022 on; on the FULL frame the middle era is 2017-2021). Otherwise "not
  resolved".
- Control: origin labels permuted within (source, year, side, rung), 500 draws, seed
  20261201; an observed contrast inside the permutation 95 percent band is reported as such.

## 11. H2: the next rung is harder to reach from a higher rung (lane D.3)

```
P_k(r) = P(y >= 5k | start rung r, x)     k = 1 (one rung), k = 2 (two rungs: the owner's 40->50 vs 60->70)
         adjusted by logistic regression with the covariates of section 4, standardized to the
         side's pooled covariate mix
m(r)   = E[y | r, x]                      mean drift by rung
```

- Tests per side, FV only: (i) trend, the slope of logit P_1 on rung (40 = 0, 45 = 1, 50 = 2,
  55 = 3, 60+ = 4; the `<=35` cell is left out because the list cut sits there) below 0,
  one-sided, at 12 and at 24 months; (ii) the owner's contrast, P_2(60+) below P_2(40),
  one-sided, 24 months primary and 12 months secondary. **Holm family of 8** (2 sides x 4).
- Inference: the player-clustered bootstrap of section 10 (B 2000, seed 20261201); one-sided
  p = share of draws on or past 0 in the wrong direction, floored at 1/B. The logistic
  regressions carry an L2 penalty of 1.0 on every coefficient except the intercept and the
  rung terms, weights `omega`.
- Minimum n: a test reads "unpowered" when either compared rung cell (40, and 60+ for the
  contrast; any of 40 to 60+ for the trend) has fewer than 50 completed pairs at that horizon,
  and keeps its place in the family with p = 1.
- Verdict "higher rungs are harder" only when the primary, S1 and S2 frames all agree after
  Holm.
- **Pre-stated structural caveats.** Each can make H2 hold with no development story at all:
  the FV scale is bounded and sources hand out very few 65+ grades; regression to the mean
  pulls high start grades down; and graduation removes the fastest top-rung risers from the
  lists before their next read, which biases the top rungs toward "harder" under the primary
  AND the S1 frame. A pass therefore reads "list grades rise less often from higher rungs",
  never "developing talent is harder there", and S2 is the check on the graduation channel.
- Descriptive difficulty table (the Development tab explainer's source): P_1, P_2 and m by
  side and rung, 12 and 24 months, under the primary frame with S1 and S2 beside it, by origin
  where a cell holds 50 completed pairs.

## 12. Power, from DVM-1's counts (P-5), before any growth is read

Recomputed by `dvm_difficulty_lab.power_block` from the DVM-1 counts on the frozen store
(COMPLEMENT frame; `14c45886`): effective pairs = start reads in the cells x the pooled
completion share of the horizon (one number per horizon, never by rung) / 1.5068 sources per
player-year, before the widening from players recurring across years (2.98 start reads per
player). ASSUMED, not read: base rate p 0.20, spread 5 grade points, alpha 0.05 two-sided,
power 0.80. H2 differences are in probability; H1 gaps in grade points at the Holm-strictest
alpha / 39. Frame totals: 14,961 start reads (5,021 players, 9,929 player-years); 12 months
14,961 list slots and 8,020 completed pairs (pooled share 0.5361); 24 months 11,035 slots and
3,205 completed pairs (0.2904).

| horizon | side | H2 eff. pairs rung 40 | H2 eff. pairs 60+ | H2 detectable diff | H2 at alpha / 8 | H1 eff. pairs HS / COL / IFA (rungs 40-55) | H1 detectable gap HS-COL / IFA-COL / HS-IFA |
|---|---|---|---|---|---|---|---|
| 12m | hit | 702.7 | 130.9 | 0.1067 | 0.1362 | 666.4 / 773.8 / 979.1 | 1.07 / 0.98 / 1.02 |
| 12m | pit | 726.5 | 81.5 | 0.1309 | 0.1671 | 578.2 / 1094.0 / 458.6 | 1.04 / 1.13 / 1.27 |
| 24m | hit | 256.1 | 59.2 | 0.1616 | 0.2063 | 266.3 / 309.5 / 378.9 | 1.70 / 1.56 / 1.62 |
| 24m | pit | 267.5 | 39.1 | 0.1918 | 0.2448 | 233.6 / 440.4 / 171.1 | 1.64 / 1.83 / 2.04 |

Read: these supersede the lane's planning figures (about 9 and 11 points of one-rung rate,
about 0.9 grade points for H1). A one-rung rate difference smaller than about 0.11 (hitters)
or 0.13 (pitchers) between rung 40 and 60+ at 12 months is below 80 percent power; the
owner's two-rung contrast from 60+ at 24 months is the thinnest test and may read
"unpowered". On the FULL frame the counts rise and these figures are conservative.
Validation: about 8,020 / 1.5068 = 5,322 player-steps over 12 start years and 30 clubs, about
15 per club-year, so a mean-Spearman delta is resolvable only near 0.1 and a tie is the modal
outcome.

## 13. Validation before serving (lane Part E) and the decision rule

**Arms.** C0 = today's DvM+ logic (value growth credited against zero, summed over the window
as the served series does) rebuilt on the same same-source frame; DV and D0 as in sections
6 and 7. "C0 as a mean" is reported beside them and adjudicates nothing.

**Frame.** Club-years (o, Y), Y a preseason (May 1). The index at Y uses steps ending at or
before Y; the target is the step Y to Y+1. FULL frame: Y = 2012 to 2025. COMPLEMENT frame: Y
in 2012-2018 and 2023-2025, windows truncated where they would cross a 2020 or 2021
endpoint. The 2025 to 2026 target is FanGraphs and BA only (P-4). **Leave-three-years-out:**
each validation year's expectation model is refit leaving out list years Y-1, Y and Y+1, so
neither the index year nor the target year informs the expectation that scores them. Every
club enters with its shrunk `D~_o` (the `N_o >= 10` floor is a publication rule only).

| id | statistic | role |
|---|---|---|
| V-P1 | mean over Y of Spearman(index at Y on a 3-year window, club RAW value growth in step Y to Y+1) across the 30 clubs | primary, non-inferiority |
| V-P2 | the same with the target = club mean RESIDUAL value growth `w - E^W` under the leave-three-years-out expectation for Y, one expectation shared by all arms | primary, superiority |
| V-S | mean over Y of Spearman(index on the 1-year window at Y, the same at Y+1), disjoint windows | reported with Holm; read only beside V-C |
| V-C | mean over Y of max over k of abs Spearman(index at Y, composition_k at Y); composition = share HS, share college, share IFA, mean start rung, mean age_rel, number of pairs | construct check |

V-S is not validity: club composition persists, so an index that tracks composition looks
more stable than one that has removed it.

**Inference.** Club-clustered bootstrap (resample the 30 clubs with all their years), B 2000,
seed 20261201, paired deltas against C0. Holm across DV and D0 within V-P2 (family of 2) and
within V-S (family of 2).

**Decision rule (lane E.5; owner answer Q-DVM-3 A).** DV, the owner's chosen value layer,
is a SHIP CANDIDATE when all hold:
1. V-C: its composition maximum is at most 0.20, or at least 0.10 below C0's;
2. V-P1: non-inferior to C0 (the one-sided 95 percent lower bound of the delta is above -0.05);
3. no Holm-resolved loss to C0 on V-P2 or V-S.

A tie on prediction ships under Q-DVM-3 A when 1 to 3 hold. Copy derives from the artifact
only: a resolved V-P1 win allows "predicts next-year farm growth better than the previous
index"; a resolved V-P2 win allows "predicts next year's growth above expectation better";
with neither, "difficulty-adjusted; ties the previous index on prediction", and the V-C
number, not an adjective, states how far the index tracks origin mix. Otherwise NO SHIP: the
served DvM+ stays as it is and the failed arm is a block inside
`data/dvm_difficulty_eval.json`, never a new eval file. A SHIP CANDIDATE flips nothing: the
flag `storage.DVM_DIFFICULTY_ARM` stays None until the owner flips it (DVM-6), after the
served build (DVM-5), with the blast radius published and "farm letters move" said plainly.

## 14. The clock

| when | what |
|---|---|
| this commit | the registration, results EMPTY |
| after this commit | DVM-3 builds the lab on FIXTURES ONLY; no growth on real data |
| **the look, once** | the first run of `python tools/dvm_difficulty_lab.py --look` on or after the LATER of (a) 2026-12-01, (b) the ETA look record (exists, `be53132d`; a VOID would also count) and (c) the R-LV look record in `docs/efv-v2/EFV_V2_GATE.md` part 9, on the FULL frame; or, if no R-LV record exists, the first run on or after **2027-01-31** on the COMPLEMENT frame |
| on EVERY path | only after the PROSPECT_ANCHOR look record exists in `docs/PROSPECT_ANCHOR_GATE.md` section 18 (`## 18. Results`): the S2 frame codes graduates at `G_start + 5`, so its by-rung difference from the primary frame is arithmetic on graduation share by FV rung, the quantity F-R4 bans before that look |

- The lab refuses before its clock and refuses a second scored look (it may re-print the
  stored result).
- Never on another registered look's date (`docs/*GATE*.md`, `docs/diamond-betting.md`;
  known now: 2026-10-23, 11-06, 11-13, 11-20, the eFV reserved-read day, 12-03, 12-08, 12-10,
  2027-01-12), never in a session that takes another gate's look, never while a pipeline,
  nightly or pytest runs.
- Crash protocol: before the look, a full dry run of the reporting path on fixtures with
  nulls; the look's stdout and stderr are teed to the task directory before anything else
  runs; on any exception after scoring began, STOP without rerunning and write the owner
  question.

## 15. Isolation, input pins and the firewall

- The lab and its artifacts live outside every eFV module (the eFV tests scan those modules
  for FV-level groupings). An AST test bans label, `career_war`, `value_framework`, `storage`
  and every `efv_*` import except `efv_identity`.
- Inputs pinned by sha256 at the look's start and end, and the look aborts if any moves: the
  frozen store (section 2), `data/debuts.json`, `data/inactive.json`, `data/timeseries.json`,
  `data/debut_redates.json`, the minor league season caches and the draft history cache
  (`dvm_difficulty_lab.input_pins`). Probes are logged to `PROBES.jsonl` in the task
  directory.
- Artifacts: `data/dvm_difficulty.json` (frozen table, coefficients, shrunk cells, spreads,
  k values, frame receipt, input pins), a model internal no page reads before the flip, listed
  in `deploy/data_exclude.txt` by the look's commit; `data/dvm_difficulty_eval.json` (H1, H2,
  validation, the decision), an eval artifact that ships with the registry row.
- **Firewall.** No output of this lab (tables, residuals, club indices) enters any eFV head,
  driver or stratum without its own registration naming this artifact in its forking-paths
  count. Staff Gems may add the frozen expectation table as a baseline term only after this
  look, through its own registration (final-pass plan 8.D, row 7). The per-(club, season,
  player) residuals with tenure shares are exported for it.
- Nothing in this study predicts an MLB outcome; it describes how list grades move.

## 16. Honest priors (recorded before the read, so the read can be checked against them)

- H2 probably reads "higher rungs rise less often", for the structural reasons in section 11.
- The HS and IFA advantage in raw growth is probably mostly age, so Theta_direct may be small.
- The validation probably ties on prediction, which is why the composition check (V-C) carries
  the decision.

## 17. Amendments

None. An amendment is dated, filed before the look, names what moved on disk since this
commit, and changes no threshold, frame, family, seed, margin or criterion.

---

## 18. Results

**EMPTY AT REGISTRATION.**

Nothing is written here before the look. The first entry is dated, names the commit and the
frame (FULL or COMPLEMENT), and carries the look's verbatim output.
