# eFV pitcher usage (reliever) adjustment (EFV_RELIEVER_ADJ): method, fixed before any number

Registration status: REGISTERED

Written 2026-10-15 (task EFV_RELIEVER_ADJ) under the owner's decision EW3-31 of 2026-10-15
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), verbatim: "Why is Brandon Clarke graded so
highly? It seems like maybe we're overgrading relievers, can we apply a reliever adjustment
(reliever identification done by checking a prospect's GS vs IP)".

This document is committed ALONE, before the module `efv_reliever_adj.py` exists and before
any outcome of this read is computed. Sections 1 to 10 are written before the read; the run
appends section 11 (the numbers) and section 12 (the verdict). No em-dashes. Nothing here, in
its code or in its artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`,
binding): the groups are frame, side, list year or decision year, fold, usage role and the
model's own shift. Only the development frames are read (lv_dev, vm_dev, pitchers); no
reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and later) is built
or scored, `backtest.run_backtest` is never called, and no projection model is retrained.

The only outcome-blind number looked at before this registration: the class counts of the
cut points below on the live pitcher matrix (2,506 rows, read season 2026): RELIEF 1,442,
SHORT-START 160, STARTER 772, under 5 appearances 35, no line 97.

## 1. The example and the question

Brandon Clarke (STL, age 23.5): consensus FV 45.9 (pitcher consensus rank 42 of 941), served
eFV 49.8 (order rank 13) under the served re-fit RT (`docs/efv-v2/EFV_V5_REFIT.md`; pitcher
head w_skill 1.0, w_time 0). His chips: the population translation +20.5, called plus
swinging strikes +15.4, strikeouts beyond whiff +10.3, command grade -8.4, nine more +32.9.
Every 2025 and 2026 minor league appearance is a start (2025: 14 G, 14 GS, 38.0 IP; 2026:
10 G, 10 GS, 29.2 IP), about 2.7 to 3.0 innings per start: reliever-length outings, which
face each lineup about once and can lift strikeout and whiff rates. A games-started rule
alone calls him a starter; the owner's GS against IP rule (innings per start) does not.

The question: does the served pitcher model over-predict for pitchers used in short outings
or in relief, given the shift it makes off consensus; and does an adjustment fixed by the
three candidates of section 4 order pitchers better on the development frames.

## 2. The usage classification (fixed here)

**Inputs.** Minor league season lines from `milb_history.season_splits` (cache only), the
affiliated levels DSL, CPX, A, A+, AA, AAA (`efv_w2_popmle.LEVEL_RANK`), the non-affiliated
Mexican League out (`efv_w2_popmle.NON_AFFILIATED_LEAGUES`, the repaired population's rule).
Per season and pitcher, summed over every line: G, GS, IP (outs / 3; "12.1" is 12 innings and
one out) and BF. Major league lines do not enter.

**As of each read; never a season after it.** The read season is the last minor league season
the row's own read could see, `efv_w2_milb.last_readable_season(read_year, cutoff)`, the rule
every minor league column of the model uses:

- list-vintage rows (lv_dev test and training rows of vintage V): read year V, cutoff the
  frame's window start (`efv_vintage_frame.build_frame`), so the read season is V - 1; the
  person id is the frame's outcome-blind id;
- vintage-matched matrix rows (vm_dev training rows, the production rows): read year the
  decision year, cutoff the matrix row's own cutoff; a vm_dev TEST row reads at its pinned
  preseason as-of date where it has one (`efv5_combined._pinned_asof`, the population
  column's own rule, `efv_w2_popmle.vm_values`);
- twin rows (`efv5_refit` A4): the twin's read season;
- the live board: the live read season (2026, `efv5_combined` live read).

**Window.** The read season alone when it holds 5 or more appearances; otherwise the read
season plus the season before it (summed).

**Quantities.** Starter share GS / G, IP per appearance IP / G, IP per start IP / GS (all
innings over starts: relief innings of a mostly-starting pitcher count, which lengthens the
figure, so the rule errs toward STARTER), BF per appearance BF / G.

**Classes (cut points fixed here, before any outcome read):**

| class | rule |
|---|---|
| RELIEF | G >= 5 and GS / G < 0.5 |
| SHORT-START | G >= 5 and GS / G >= 0.5 and IP / GS < 3.5 |
| STARTER | G >= 5 and GS / G >= 0.5 and IP / GS >= 3.5 |
| FEW | 1 to 4 appearances in the window |
| NO-LINE | no affiliated line in the window |

FEW and NO-LINE carry no usage reading; every candidate treats them as STARTER rows (the
reference: no adjustment). The card label (section 9) prints nothing for them.

**Sensitivity grid (reported, decides nothing).** GS / G cut in {0.4, 0.5, 0.6} x IP / GS cut
in {3.0, 3.5, 4.0} x window in {the rule above, always the read season plus the one before}:
class counts, the realized shares of section 3 (E1) and candidate (b)'s pooled difference
(section 5) at each of the 18 cells.

## 3. The estimand (on the development frames, pitchers only)

The rows: the pitcher scored rows of lv_dev (list vintages 2017 to 2019) and vm_dev (decision
years 2017 to 2023) of the served re-fit's committed read, with RT's own fold heads and its
cross-fitted read weights (`data/_labs/efv5/efv5_refit_fit.json`, `weights_cross_fitted.RT`).
The read rebuilds RT's orders from the committed read's cached fold builds and must reproduce
its pitcher within Spearman (lv_dev 0.1442, vm_dev 0.3853) to 5e-5 before anything is read;
otherwise it refuses.

On each fold's scored rows: u_c and u_y (the within-fold consensus and fWAR-label
percentiles, DS-08's own), e_skill and e_time of the fold's heads, and the model's shift
s = w_skill x e_skill + w_time x e_time (the order minus u_c at the fold's read weights).

- **E1, realized share by role.** Pooled over the folds of both frames: OLS
  u_y ~ 1 + u_c + sum over roles r of I(r) x s + I(SHORT-START) + I(RELIEF) (FEW and NO-LINE
  in the STARTER role). The realized share of role r is rho_r = c_r / c_uc: 1 means the shift
  is realized at the size the order gives it (in consensus percentile units), below 1 means
  the model over-predicts that role. Reported: rho for STARTER, SHORT-START, RELIEF, for the
  pooled non-starter role, and rho_nonstarter minus rho_STARTER, each with a player-clustered
  bootstrap CI95 (B 2000, seed 20261017); per frame beside it.
- **E2, the audit's D4 measure.** Per (frame, fold): out_pct (the label percentile), the
  centered shift (s minus its fold mean), the quadratic expectation of out_pct in u_c fitted
  within (frame, side); model-up rows are the top fifth of centered shift within (frame,
  fold). By role: n, mean residual (out_pct minus the expectation), mean implied (the
  expectation's slope at u_c times the centered shift) and their ratio (the realized
  fraction), with player-clustered CI95. Reported; decides nothing.

## 4. The candidates

Each candidate changes the pitcher order only; hitters are untouched. Each keeps RT's heads,
data, folds, timing head and cross-fitted read discipline except for its own change.

| id | what | fitted on |
|---|---|---|
| Z | the zero adjustment: RT as served, recomputed | the comparator (null) |
| A | ROLE-HEAD: a role term in the skill head | each fold's own head training rows |
| B | ROLE-SHRINK: a role-specific weight on the skill shift | DS-08's out-of-fold pool, cross-fitted |
| C | WORKLOAD: rate drivers normalized for outing length before the head | each fold's own head training rows |

**A, ROLE-HEAD.** For each fold (and production): RT's fitted skill head gives e_skill on its
own has-block training rows (`efv_v2_model.skill_training_rows`); a weighted least squares on
those rows (the head's row weights) u_y ~ 1 + u_c + e_skill + I(SS) x e_skill + I(R) x
e_skill + I(SS) + I(R), with SS = SHORT-START and R = RELIEF, gives a_uc, g_SS, g_R, d_SS,
d_R. A row's skill term becomes e_skill + (g_role x e_skill + d_role) / a_uc (0 added for
STARTER, FEW, NO-LINE). Weights then follow DS-08 exactly as RT's (cross-fitted for the read,
pooled for production) on the adjusted term.

**B, ROLE-SHRINK.** DS-08's rule with the skill term split by role: pooled OLS
u_y ~ 1 + u_c + I(REF) x e_skill + I(SS) x e_skill + I(R) x e_skill + e_time + I(SS) + I(R)
(REF = STARTER, FEW, NO-LINE; the role intercepts are nuisance controls and never enter the
order), w_role = clip(c_role / c_uc, 0, 1), w_time = clip(c_time / c_uc, 0, 1), 0 when
c_uc <= 0. The read uses each fold's weights from the pool with that fold left out
(cross-fitted, RT's own rule); production uses the pool of every fold. The order is
u_c + w_role x e_skill + w_time x e_time.

**C, WORKLOAD.** Before the skill head is fitted (each fold and production), every pitcher
rate driver the head can read is normalized for outing length: the driver x is regressed on
z = log(BF per appearance) over the fold's training rows that carry both (OLS with an
intercept), and x becomes x - b x (z - mean z of those rows) on training, test and live rows
alike (the training coefficients; rows without a usage line keep x). The rate drivers: the
strikeout block `k_rel`; the group cells of strikeout rate and strikeout minus walk rate
(`g5_pit_A_all_all_k_pct`, `g5_pit_A_young_all_k_pct`, `g5_pit_A_all_SP_k_pct`,
`g5_pit_A_all_all_k_minus_bb`, `g5_pit_A_young_all_k_minus_bb`, `g5_pit_A_all_SP_k_minus_bb`);
called plus swinging strikes `w2p_csw_p`; called strikes `w2p_cstr_p`; strikeouts beyond whiff
`w2p_k_resid_p`; the population translation `w4p_pop_pit` (after RT's within-group rank). No
pitcher whiff-rate column exists in the head, so the owner's "whiff" maps to the strikeout
and CSW columns. The skill head is then refitted as RT's (`efv5_refit.fit_heads` skill part:
the same candidate columns, V2 admission, alpha, the nested-CV lambda); the timing head stays
RT's. Weights follow DS-08 as RT's (cross-fitted; pooled for production).

## 5. The statistic, the null comparator and the recovery check

**Statistic.** The program's primary (`efv_v2_stat`): within (side, list year) Spearman of the
order with the fWAR label, size-weighted over groups of 20 or more rows, on the PITCHER scored
rows. Per frame: candidate minus Z, paired E_cond CI95 (players resampled, scores fixed,
B 2000, seed 20260906). Pooled: one paired E_cond over both frames' pitcher rows, groups
(frame, year), player clusters spanning both frames. Raters beside: consensus, MLB Pipeline,
FanGraphs. Never a cell by consensus-FV level.

**Null comparator.** Z, the zero adjustment (the current model), is the comparator of the
ship rule. Beside it, a permuted-role null for A and B (decides nothing): the usage roles
shuffled within each (frame, fold) among the scored rows and within each training year among
the training rows, A and B re-derived, the pooled point difference recorded; K 200 for B,
K 50 for A, seed 20261018. The real candidate's difference is reported with its percentile in
that null. C has no role label to permute; its null is Z.

**Planted-effect recovery (real design).** On the pooled development pitcher rows (their u_c,
shift s, role, fold groups and player clusters as read): a latent L = u_c + k_role x s + sigma
x N(0, 1), the simulated label the within-fold percentile of L; sigma is set once so that
under the null plant (k = 1 for every role) RT's within Spearman with the simulated label
equals its observed pooled pitcher within. Two plants, 200 replications each, seed 20261019:
NULL (k = 1 everywhere) and PLANT (k_STARTER = 1, k_SHORT-START = k_RELIEF = 0.4). For each:
the mean and spread of E1's rho by role, and B's pooled difference against Z with its pass
rate under the ship rule (E_cond B 200 per replication). The read is called able to see a
usage effect of this size when, under PLANT, E1 recovers rho_nonstarter within 0.15 of 0.4
on average and B passes in at least half the replications, and, under NULL, B passes in at
most 10 percent. A read that cannot see the plant says so in the verdict.

## 6. The ship rule (fixed here, before any number)

A candidate X in {A, B, C} passes when BOTH hold on the pitcher rows:

1. it beats Z on the pooled development frames with the CI95 lower bound of the pooled
   paired difference above 0;
2. it trails Z by no more than 0.005 on either frame (X minus Z >= -0.005 on lv_dev and on
   vm_dev, point estimates).

If several pass, the one with the largest pooled difference is prepared (disclosed).

On a pass: the adjustment is built DARK. `efv_reliever_adj.RELIEVER_ADJ_ON = False`; with it
True the served pitcher order applies the prepared candidate's production fit
(`data/efv_reliever_adj_weights.json`), and `OWNER_QUESTION.md` in the task's report states the
board effect and the flip. With the flag False every served artifact is byte identical to the
code before this task. On a fail: nothing is prepared; the read and the reasons are recorded.

## 7. The board effect (reported)

On the live board of the run date (`efv5_refit.score_board` machinery, the served RT
production fit), for each candidate's production fit: Brandon Clarke (eFV, rank, consensus,
usage), the 20 largest movers among SHORT-START and RELIEF pitchers by absolute change in eFV
(before and after), the class counts on the 941 board pitchers, and the mean absolute eFV
minus consensus by class, before and after. Descriptive for a candidate that does not pass.

## 8. The ledger and the artifacts

- `data/_labs/efv5/efv_reliever_adj_fit.json`: the receipts (parity, cache hashes, class
  counts), E1, E2, every candidate's read, the nulls, the recovery check, the grid, the ship
  reading, the board effect.
- `data/efv_reliever_adj_weights.json`: only on a pass, the prepared production fit (read by
  the serve path only when the flag is True).
- `data/efv_pitcher_roles.json`: the usage classification of every live board pitcher (the
  card label of section 9); written regardless of the verdict.
- Code `efv_reliever_adj.py`, tests `test_efv_reliever_adj.py`.

## 9. The card label (regardless of the verdict)

The PROSPX card of a pitcher with a usage reading prints one plain line with the class and its
numbers, for example "Usage: Short starts (2026 MiLB): 10 G, 10 GS, 29.2 IP, 3.0 IP per
start", with Starter, Short starts or Reliever as the class word. It is a statement of usage,
not a grade input, and moves no number. FEW and NO-LINE print nothing.

## 10. Defaults applied (the owner may choose differently) and bans

- D-1 the cut points of section 2 (the owner's example: GS / G 0.5, IP / GS 3.5), minimum 5
  appearances, the read season alone unless it has fewer than 5.
- D-2 IP per start is all innings over starts (no start-only innings exist in the lines).
- D-3 FEW and NO-LINE rows are the reference (no adjustment).
- D-4 C's workload covariate is log BF per appearance (a times-through-the-order proxy), one
  covariate for every rate driver.
- D-5 the ship rule's pooled lower bound above 0 (the spec's rule, stricter than the re-fit's
  point rule).
- Bans: no reserved row; no statistic by consensus-FV cell (the test scans the module
  source); no projections retrain; the fWAR label epoch's runbook untouched;
  `backtest.run_backtest` never called; the served grade does not move in this task (every
  new served path is behind `RELIEVER_ADJ_ON = False`).
