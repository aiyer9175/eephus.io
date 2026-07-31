# S-XLINE gate registration - 2026-07-23

Experiment: Statcast measurement upgrade of AAA stat lines feeding eFV
(efv_statcast_line.maybe_adjust_row, hooked in efv_dataset._milb_features).
Owner directive 2026-07-23: "Work with Statcast to find ways to improve eFV for
both hitters and pitchers until you find correlation that will improve the model."

Registered BEFORE the in-matrix gate run. Seed: none needed (closed-form ridge,
deterministic dataset build). Lab: tools/efv_statcast_line_lab.py ->
data/xfv_statcast_line_eval.json.

## Mechanism under test
For AAA player-seasons 2023+ with a qualified (>= 100 PA) Savant minors
aggregate row, blend the expected-stat gap into the actual line BEFORE the
level-relative conversion:
- hitters: avg/obp/slg += 0.5 * (x_stat - stat) measured within Savant;
  ops = obp' + slg'.
- pitchers: era *= clamp(1 + 0.5 * (xwoba_a - woba_a)/max(woba_a, .200),
  [0.75, 1.25]).
Uncovered rows, non-AAA levels, and pre-2023 seasons are byte-identical to the
incumbent path.

## Clause M - measurement validity (ALREADY RUN 2026-07-23, PASS)
Next-season prediction of the same stat family must improve with the blend on
AAA season-pairs (bootstrap 2000, seed 20260723, scripts in session scratchpad):
- Hitters: blend50 vs actual wOBA, delta rho +0.0253, CI95 [+0.0046, +0.0449],
  P(>0) = 0.991, n = 776. PASS.
- Pitchers: xSLG-against blend +0.0511, CI95 [+0.0115, +0.0907], P = 0.996,
  n = 491; xwOBA-against direction-consistent (P = 0.90). The shipped era
  correction uses the xwOBA-against relative gap (run-scale); this clause
  records that the era formulation itself is NOT separately outcome-validated -
  clauses 1-3 are its guard. PASS (recorded honestly).

## Clause 1 - uncovered-row invariance (hard invariant)
Rebuild the matrix OFF and ON per side. Every row without a covered AAA 2023+
season must be IDENTICAL (all feature keys). Any drift = FAIL (implementation
bug, do not ship).

## Clause 2 - in-matrix no-harm (per side)
efv_model.run(persist=False) on the OFF matrix vs the ON matrix. The
debuted-KM pooled OOS Spearman of the shipped blend must not degrade by more
than 0.003 (delta >= -0.003). This is a measurement upgrade whose covered
training rows are almost entirely the censored 2024 cohort; a rank GAIN is not
claimed and not required. PASS/FAIL per side; a side that fails does not ship
(the other may).

## Clause 3 - bounded pull (covered rows)
Among rows that changed, the max absolute change in any *_rel feature must be
sane (< 0.5 on the rate scales; era_rel < 1.2), and after any flip the max
served grade move among covered ACTIVE players must be <= 3 FV points
(post-flip check recorded in the eval artifact; a larger move = retract).

## Ship rule
Clause M (done) + Clauses 1-3 PASS for a side -> flip that side's default in
efv_statcast_line.py, rebuild matrices, regen served artifacts, registry row
xfv_statcast_line verdict provisional (validated at the measurement layer,
no-harm at the model layer). FAIL -> defaults stay off, eval artifact ships as
the loss ledger, keep-alive keyed to 2025 debuts entering the matrix.

## RESULTS (2026-07-23 local run)
Artifact: data/xfv_statcast_line_eval.json. VERDICT: PASS both sides -> defaults
flipped ON in efv_statcast_line.py.
- hit: clause1 invariance PASS (0 violations, 66 changed rows), clause2 delta
  +0.0000 (pooled blend Spearman unchanged - the covered rows are 2024-cohort
  censored TRAIN-side rows that never enter the 2020-2023 forward-chained
  folds, so the flagship eval is unaffected by construction), clause3 bounded
  (max |delta| within bars). PASS.
- pit: clause1 PASS (0 violations, 68 changed rows), clause2 delta +0.0000
  (same structural reason), clause3 bounded. PASS.
- Effect surface: LIVE scoring of covered actives (AAA 2023+ w/ >= 100 Savant
  PA: ~342 hitters + ~137 pitchers) and every future fold that includes 2024+
  cohorts. The trained 2020-2023 eval is byte-identical today.
- Clause 3 post-flip half (max served grade move <= 3 FV among covered
  actives) is checked at the regen step and recorded in the eval artifact.

## AMENDMENT + RE-RUN (2026-07-23, same day)
First post-flip regen: 104 active grade moves, 103 within the bound, ONE
breach: nic_kent -3.3 (2026 AAA slg .556 vs xslg .357 on 174 PA, a .199 gap;
the uncapped correction moved his served grade past the 3.0 bound). Per the
registered rule the ship was RETRACTED and the mechanism amended: fixed
measurement-sanity caps on per-stat gaps (|d_avg|,|d_obp| <= 0.050,
|d_slg| <= 0.100; round a-priori bounds, chosen to bound single-partial-season
grade impact, not tuned to any performance metric; the pitcher arm already
carried the [0.75, 1.25] era-multiplier clamp). FULL gate re-run under the
amended mechanism follows; ship only if clauses 1-3 AND the post-flip check
all pass. Results below.

RE-RUN RESULTS (capped mechanism): hit PASS (clause1 0 violations / 66 changed,
clause2 delta +0.0000, clause3 bounded), pit PASS (0 / 68, +0.0000, bounded).
POST-FLIP v2: PASS - 97 active served-grade moves, max delta 2.7 <= 3.0.
SHIP STANDS: defaults ON with caps; artifact data/xfv_statcast_line_eval.json;
registry row xfv_statcast_line (provisional). Served eFV artifacts regenerated
2026-07-23 local (regen_all 47s); the deploy box restamps the golden on its
own regen per convention.

# S-XLINE-2 gate registration - 2026-07-23 (pre-registered BEFORE the backfill)

Extension of S-XLINE to sub-AAA levels using the FIRST-PARTY StatsAPI game-feed
tracking that statcast_metrics.py already harvests (in-house xwoba_est from
EV/LA). Measured live coverage (>= 25 tracked BBE): AAA 356, A 346, CPX 206,
AA/A+ ~0 (park hardware). Owner directive 2026-07-23: backfill + gate + test
other Statcast correlations across full coverage.

Frozen arm list (no additions after data is seen). Seed 20260723, 2000
bootstrap reps, ship bar lo95 > 0 unless stated. Lab:
tools/efv_statcast_line2_lab.py -> data/xfv_statcast_line2_eval.json.

## Clause V0 - measurement-proxy validity (STOP gate)
On AAA players with BOTH sources in the same season (feeds xwoba_est AND
Savant xwOBA, >= 25 BBE / >= 100 PA): Spearman agreement must be >= 0.70 and
mean bias must be stable enough to correct (report r, rho, bias, slope).
Below 0.70 the in-house proxy is too weak to carry a gate: STOP, ledger, done.

## Clause M-A (PRIMARY) - A-ball measurement upgrade
Season pairs (Y in 2023, 2024, 2025 -> Y+1 outcome at any level, z within the
destination pool, >= 150 PA both legs, >= 25 tracked BBE in Y): blend50 of the
xwoba_est-implied gap into the actual line must predict next-season wOBA
better than the actual line. lo95 > 0 ships the measurement clause.

## Clause M-CPX (SECONDARY) - complex-league arm
Same design at CPX. Registered as likely underpowered (tiny samples, rookie
ages); an honest NULL closes it without touching the A-ball verdict.

## AUX arms (registered exploratory; each lo95 > 0 or it is a recorded NULL)
- AUX-1 hit p90 EV, level-relative, A-ball, vs next-season wOBA z. (The AAA
  early-window read was ANTI-correlated for raw power; this tests the younger
  level honestly rather than assuming.)
- AUX-2 hit whiff/swing-miss (zone_metrics) at A-ball vs next-season K% and
  wOBA z.
- AUX-3 pit fastball velo (feeds) at A-ball vs next-season K% against.

## Selection-bias falsification (mandatory report, any arm)
Tracked-park coverage is not random. Among players with the SAME current
season stat line band, covered vs uncovered players' next-season outcomes must
not differ materially (report the gap + CI); a big gap means coverage itself
is informative and the arm's effect is confounded - flag and do not ship.

## Ship rule
V0 pass + M-A pass -> implement the sub-AAA gap source in efv_statcast_line
(feeds-based gap index, same W=0.5, same caps .050/.050/.100, levels A/CPX
2023+) behind default-OFF flags, then the SAME in-matrix clauses as S-XLINE
(invariance, no-harm >= -0.003, bounded pull, post-flip max served move <= 3)
before any flip. AUX passes inform FUTURE registrations only; nothing ships
from an AUX read alone.

## Backfill scope (frozen)
Hitter feeds for A + CPX + (AAA as needed for V0), seasons 2023-2025, via the
module's own feed_cache (gamePk-shared, throttled per module discipline);
outcome lines from milb_history (no feeds needed). Cache growth is refetchable
per tools/prune_cache allowlist.

## RESULTS
(filled by tools/efv_statcast_line2_lab.py, 2026-07-23 local run)

Clause V0: STOP. AAA 2026 overlap (stored feed aggregates >= 25 BBE vs
Savant >= 100 PA), n = 365 matched: Spearman 0.6365 (bar 0.70), Pearson
0.6895, mean bias feed-minus-Savant +0.0424, OLS slope 0.5411. Per the
registration the backfill was NOT run and no arm (M-A, M-CPX, AUX-1/2/3,
selection-bias) was executed. Artifact data/xfv_statcast_line2_eval.json is
the V0 loss ledger.

Ledger diagnostics (descriptive, gate untouched): agreement does not rise
with BBE (0.637 at 40+, 0.629 at 100+ -> structural, not sampling noise);
the raw pre-adjustment aggregate agrees slightly WORSE (0.614); the feed
estimate clears the bar against the contact-flavored Savant xSLG (0.714);
the residual vs full xwOBA loads on Savant K% (rho 0.47) and BB%. Reading:
the EV/LA surface is usable, but contact-only xwoba_est vs full xwOBA was a
quantity-mismatched yardstick. Keep-alive: any revival needs a NEW
registration with a like-for-like V0 (K/BB-completed reconstruction of the
feed estimate, or an xSLG-family agreement gate) BEFORE any re-run; nothing
proceeds under this one.

# S-XLINE-3 gate registration - 2026-07-23 (pre-registered; supersedes S-XLINE-2's V0 quantity ONLY)

S-XLINE-2's V0 STOP was a yardstick mismatch, not proxy weakness: the feed
xwoba_est is CONTACT-ONLY (EV/LA, xwOBAcon-scale) and was compared against
FULL xwOBA; the residual loads on the omitted K/BB channel (K% rho 0.47, BB%
0.32) and the same estimate clears 0.714 against contact-flavored xSLG.
Amendment (the ONLY change from S-XLINE-2): complete the feed estimate to
full-xwOBA scale before comparing, using the player's ACTUAL K/BB/HBP counts
from the stat line, mirroring how Savant constructs xwOBA (expected value on
contact, actual value on non-contact events):
  xwoba_est_full = (wBB*BB + wHBP*HBP + xwobacon_est*BIP_events) / PA_denom
  with the standard linear weights the codebase already uses. Exact event
  accounting is implementation-defined from milb_history stat lines and MUST
  be frozen in the lab header before V0 runs.

All other clauses are IDENTICAL to S-XLINE-2 and re-frozen here by reference:
- V0': xwoba_est_full vs Savant full xwOBA, AAA both-source players, >= 25
  BBE / >= 100 PA, Spearman >= 0.70 or STOP.
- M-A (primary): A-ball pairs 2023-2025 -> Y+1, blend50 of the capped gap
  (xwoba_est_full - wOBA, cap 0.050) into the actual line, must beat the
  actual line predicting next-season wOBA z; lo95 > 0, seed 20260723, 2000.
- M-CPX secondary, AUX-1/2/3, selection-bias falsification, backfill scope,
  ship rule (default-OFF flags + full in-matrix clauses + 3-FV post-flip
  ceiling before any flip): all as registered for S-XLINE-2.
Lab: tools/efv_statcast_line2_lab.py extended with the completed-estimate
quantity -> data/xfv_statcast_line3_eval.json.

## RESULTS
(2026-07-23 local run; artifact data/xfv_statcast_line3_eval.json)

V0' PASS: n = 365 matched (AAA 2026 both-source, 0 lost at the stat-line
join), Spearman 0.7796 (bar 0.70), Pearson 0.8003, mean bias +0.0060, OLS
slope 0.8409. The K/BB completion fixed the yardstick: the contact-only
estimate on the SAME subset reads 0.6365. Backfill executed per the frozen
scope: A + CPX hitter feeds 2023-2025, 8,464 feeds processed, 0 errors
(pitcher rows came free from the same games).

- M-A (PRIMARY): NULL. n = 247 covered pairs; rho actual line 0.1839 vs
  blend50 0.1804, delta -0.0035, CI95 [-0.0502, +0.0440], P(>0) = 0.43. The
  AAA measurement-upgrade mechanism does NOT clear at A-ball; no feeds-based
  gap source ships and the efv_statcast_line default stays AAA-only.
- M-CPX (SECONDARY): UNTRAINABLE, n = 4 covered pairs (registered as likely
  underpowered; closed without touching the A-ball verdict).
- AUX-1 p90 EV: PASS. n = 247, rho 0.1312, CI95 [0.0041, 0.2498].
- AUX-2 whiff: PASS. n = 788 (call codes need no hardware, near-full
  coverage); vs next K% rho 0.6567 CI95 [0.6112, 0.6959] (registered
  direction); vs next wOBA rho -0.1083 CI95 [-0.1754, -0.0401].
- AUX-3 pit FB velo: PASS. n = 227, rho 0.2485, CI95 [0.1248, 0.3724].
- Selection bias: CLEAN on every arm run (A-ball covered-vs-uncovered gap
  +0.0908 z CI95 [-0.065, +0.234]; AUX-3 +0.0992 CI95 [-0.053, +0.256];
  AUX-2 universe fully covered). No confounded flags.

VERDICT: M-A NULL closes the sub-AAA measurement-blend lane under this
registration; the three AUX passes are raw forward correlations only and
license nothing by themselves - they are the registered inputs to
S-XLINE-4 (below), which tests whether they add anything BEYOND the stat
line. Registry row xfv_statcast_line3 (deprecated: primary NULL; AUX
passes recorded for S-XLINE-4).

# S-XLINE-4 gate registration - 2026-07-23 (pre-registered; incremental arms on the AUX winners)

S-XLINE-3 outcome: M-A NULL (the AAA measurement-upgrade mechanism does not
clear at A-ball, n=247), M-CPX untrainable (n=4), selection-bias clean, and
three AUX passes recorded: AUX-1 p90 EV level-relative (rho 0.131 CI
[0.004, 0.250]), AUX-2 whiff from call codes (near-full coverage n=788, rho
0.657 vs next K%, -0.108 vs next wOBA), AUX-3 pitcher FB velo (rho 0.249 CI
[0.125, 0.372]). Raw forward correlation is NOT incremental value: the stat
line already carries ISO/K/BB into eFV. S-XLINE-4 tests exactly that gap.

Frozen design (no additions after data is seen; all data already local from
the S-XLINE-3 backfill; seed 20260723, 2000 reps):
- Baseline predictor per arm: cross-fitted ridge (5-fold, by player) on the
  CURRENT-season stat-line inputs eFV consumes (hitters: wOBA-proxy z, K%,
  BB%, ISO z, age-for-level; pitchers: K%a, BB%a, ERA z, age-for-level),
  predicting the arm's outcome (hitters: next-season wOBA z; pitchers:
  next-season K%a).
- INC-1: AUX-1 p90 EV z vs the hitter baseline residual. lo95 > 0 proceeds.
- INC-2: AUX-2 whiff share vs the hitter baseline residual (sign: negative
  helps wOBA; and separately vs next-K% residual, sign positive).
- INC-3: AUX-3 FB velo vs the pitcher baseline residual. lo95 > 0 proceeds.
- Age interaction report (descriptive, not verdict-bearing): incremental rho
  by age-for-level half (younger vs older), each arm.

## Ship rule
An INC pass makes the signal ELIGIBLE for a bounded live overlay on A/CPX
prospects (the training matrix has ~no A-ball-covered resolved rows, so an
in-matrix feature ship is impossible until those cohorts resolve; the overlay
is the reliever-ceiling-dial precedent): magnitude bounded so no served grade
moves more than 2 FV points, default-OFF flag, post-flip check vs a fresh
baseline snapshot with the 2-FV ceiling, registry row provisional, chip
copy in the eFV explainer. INC fail = recorded NULL, signal stays display-only.

## RESULTS
(2026-07-23 local run; artifact data/xfv_statcast_line4_eval.json, lab
`inc` command, seed 20260723, 2000 reps)

Baselines (cross-fitted ridge, 5-fold by player, lambda 1.0 a-priori,
trained on the FULL stat-line-eligible universe - the strongest stat-line
baseline, biasing against a false INC pass): hit next-wOBA-z OOF Spearman
0.3080 (n = 788); hit next-K%-z 0.7005 (n = 788); pit next-K%a-z 0.4212
(n = 699).

- INC-1 p90 EV vs hitter wOBA residual: NULL. n = 247, rho 0.0579, CI95
  [-0.0725, +0.1821], P(>0) = 0.81. The stat line's ISO z absorbs the raw
  AUX-1 correlation (0.1312 -> 0.0579 incremental); p90 EV stays
  display-only.
- INC-2 whiff share: PASS on the K channel only. vs next-K% residual rho
  +0.0965, CI95 [+0.0277, +0.1604], P(>0) = 0.995 (n = 788) - whiff adds
  strikeout information BEYOND the line's own K%. vs wOBA residual rho
  -0.0266, CI95 [-0.0920, +0.0422]: NULL - no wOBA value beyond the line.
  Overlay eligibility extends only to the K channel.
- INC-3 FB velo vs pitcher K%a residual: PASS. n = 227, rho 0.1423, CI95
  [+0.0196, +0.2704], P(>0) = 0.99. Velo carries real K information beyond
  the line's K%a/BB%a/ERA/age.

Age interaction (descriptive, registered): every arm reads slightly
STRONGER in the older-than-median half (INC-1 0.033 young / 0.096 old;
INC-2 K 0.069 / 0.124; INC-2 wOBA +0.003 / -0.062; INC-3 0.119 / 0.148,
medians age 20 hit / 22 pit). No younger-half amplification story; the
signals are not merely re-encoding age-for-level.

VERDICT: two INC passes -> whiff share (hitters, K channel) and FB velo
(pitchers, K%a channel) become ELIGIBLE for the bounded live overlay per
the registered ship rule (2-FV ceiling, default-OFF flag, post-flip
check); p90 EV stays display-only. NOTHING ships from this run - the
overlay is a separate implementation + post-flip check. Registry row
xfv_statcast_line4 (provisional per the pre-registered verdict rule: at
least one INC pass).

## OVERLAY IMPLEMENTATION + POST-FLIP BATTERY (2026-07-23, same day)

Implementation per the registered ship rule: efv_statcast_overlay.overlay_fv
(default-OFF flags EEPHUS_XOVERLAY_HIT/PIT, the efv_statcast_line pattern) +
statcast_alevel_export baking data/statcast_alevel_signals.json (current-season
A/CPX signals from the stored zone_metrics/statcast_metrics payloads + cached
milb_history K legs; offline, zero fetches; baked 603 players: hit A 317 /
CPX 137, pit A 90 / CPX 59). Residual coefficients FROZEN 2026-07-23 on the
exact INC pair populations (hit whiff_z ~ k_z: slope 0.887083, intercept
0.013667, n 788, resid_sd 0.4712; pit velo_z ~ k_a_z: slope 0.218195,
intercept -0.009135, n 227, resid_sd 0.9672); serve time never refits
(constants pasted, no fit code in the exporter). Lean = clamp(0.6 *
direction * residual_z, +-2.0) FV on the MODEL leg of run_live (priced
through the blend's own consensus-OLS FV->WAR slope, blend rebuilt like the
multiplicative dials), chip "A-ball Statcast lean". Live coverage at flip:
400 hitters + 134 pitchers nonzero.

Battery (registered: OFF invariance, then post-flip vs a fresh baseline
snapshot with the 2-FV served ceiling):
- (a) OFF invariance: PASS. Flags OFF regen_all with the hook in place ->
  data/xfv.json BYTE-IDENTICAL (sha256 ef04e91a before and after).
- (b) post-flip ceiling: FAIL. Flags ON regen vs the OFF snapshot: 103
  active xfv_grade_quantile movers, direction 53 up / 50 down (51.5/48.5,
  well inside the 70/30 sanity band), but max |move| 5.0 FV with 22 breaches
  of the registered 2.0 ceiling (top movers: evan_estevez +5.0, then a band
  of +-2.7s: brayan_cortesia, ilan_fernandez, queni_pineda, arturo_flores,
  estevan_moreno -2.7; jase_mitchell, connor_rasmussen, angel_arredondo,
  michael_carico +2.7). Realized xfv_grade max move 12.8 (the WAR->grade
  curve is nearly flat at the fringe, so a bounded WAR-space lean unwinds
  into a large realized-grade move).
- Structural reading (recorded, not litigated): the served headline is the
  rank-preserving quantile map onto the live consensus-FV distribution, and
  in the fringe region where nearly every A/CPX prospect lives the step
  between ADJACENT display values is 2.7 FV (35.0 <-> 37.7). ANY overlay
  that reorders players across that boundary moves a served grade 2.7 > 2.0,
  so the registered ceiling is unsatisfiable for a rank-moving overlay of
  any magnitude - the same class of display-layer blocker as the pit-bench
  bucket ledger. No BETA exists that passes, so there is nothing to tune
  (and re-tuning after seeing the data would be gate-shopping anyway).

VERDICT: post-flip check FAIL -> per clause (c) the flip was REVERTED
(flags OFF regen, data/xfv.json byte-identical to the ef04e91a baseline,
verified) and the overlay defaults STAY OFF. The implementation remains in
the tree as a dead-by-default dial (OFF proven byte-identical by (a);
test_statcast_overlay.py pins OFF=identity, the +-2 clamp, both sign
directions, and frozen-coefficient loading), and regen_all keeps the signal
sidecar fresh (best-effort, compare-before-write) so a future registration
can revisit with a display-space bound. The overlay block in
data/xfv_statcast_line4_eval.json is the ledger; registry row
xfv_statcast_overlay (deprecated - failed the registered post-flip ceiling).
Keep-alive: any revival needs a NEW registration whose ceiling is defined
on a surface the mechanism can actually bound (e.g. clamp the DISPLAYED
quantile grade against a no-overlay shadow ranking, or bound rank
displacement), registered BEFORE any re-run.

# F-SIDE-FIX gate registration - 2026-07-23 (pre-registered BEFORE the gate run)

Owner-authorized OUTPUT-CHANGING fairness fix for the F-SIDE top-of-joint-board
pitcher over-promotion, under EXACTLY the framing the 2026-07-15 J-DISP loss
ledger queued for owner sign-off (data/xfv_joint_map_eval.json + registry row
xfv_joint_display_map: "re-register G1 as a no-harm band (lo95 >= -0.005) to
ship ARM-2 as a fairness fix"). The owner has now authorized that framing.

## Re-baselined F-SIDE (prerequisite, run FIRST, 2026-07-23)

The registered baseline predated the pit lambda move 0.61 -> 0.52 and the
2026-07-23 trade-deadline FanGraphs board ingestion. F-SIDE was regenerated
TWICE (pre- and post-ingestion labeled matrices; identical output - the
historical labeled pool is insensitive to the new current-date snapshots, so
the post-ingestion run is the standing artifact). Current vintage, lambdas
hit 0.70 / pit 0.52, pools n_hit 804 / n_pit 846:

- STOP-check: top-25 hit-minus-pit mean +4.07, CI90 [1.64, 6.46] EXCLUDES 0
  (p_hit_gt_pit 0.997) -> the skew stands, the fix proceeds.
- top-25 pit share: display 0.37 vs raw rank_war frame 0.11 (inflation 3.36x).
- 55_plus binding cell: +2.81 CI90 [0.69, 4.81].
- per-fold top-25 diffs: 2020 +4.29 / 2021 +1.21 / 2022 +9.40 / 2023 +4.86
  (4/4 hit_gt_pit). Binding rules B1-B4 all PASS.
- S1 caps re-baselined: max allowed candidate top-25 mean diff 5.53 (= 4.07 +
  1.455 SE), median 5.01 (= 2.83 + 2.177 SE).
- S4 cells at this vintage: rank_war 051-100 -1.27, 101-200 -0.57,
  equal-FV40 -0.21 (all negative; pitchers outperform mid-board - any
  blanket pitcher penalty stays BANNED).

## Corrective mechanism (frozen; implemented behind a default-OFF flag)

The 2026-07-15 candidate patch code is gone (the lane workspace was a session
scratchpad); the mechanism is RE-DERIVED per the owner instruction as the
ARM-2-style TOP-BAND joint display recalibration, implemented in
efv_score.py (constants SIDE_FAIRNESS_FIX_DEFAULT / SFF_KNEE_RAW /
SFF_MOVE_CAP_FV, pure core joint_band_recal, serve wrapper
_apply_side_fairness_fix; flag env-overridable EEPHUS_SIDE_FAIRNESS_FIX,
the efv_statcast_line pattern):

1. Scope: ONLY rows whose incumbent per-side display grade (after the
   per-side quantile map + the inert TOP-QUANT hook) is >= 52.5 raw - the
   display-55 knee, the F-SIDE 55_plus_binding boundary. Rows below the knee
   are byte-identical (the per-side map "blends back" trivially: the band is
   re-anchored at the knee and everything below is untouched).
2. Joint order: band rows from BOTH sides ordered by the ARM-2 expected-WAR
   crosswalk - per side, unweighted PAVA (nondecreasing) of realized
   first-6yr WAR (target_censored basis) over the labeled pool's rank_war
   quantiles, read at each row's within-side rank quantile (interpolated,
   6dp-rounded so PAVA flat blocks tie exactly); ties rank_war -> side (hit
   first) -> within-side index (the ARM-2 interleave, verbatim).
3. Reassignment: the band's OWN display-value multiset is reassigned along
   the joint order (rank-preserving within each side by construction; the
   served grade-value distribution is invariant; nothing crosses the knee in
   either direction).
4. Bound: each row's move is clamped to +-3.0 FV (SFF_MOVE_CAP_FV) - an
   a-priori round bound equal to the standing served-move ceiling (the
   S-XLINE cap precedent: chosen to bound served impact, not tuned to any
   performance metric). Clamping by the monotone envelope preserves
   within-side order.
5. Untouched by construction: rank_war, xfv_grade (realized), p_bucket,
   p_bust, factors, KRP+. Surplus is repriced off the corrected display
   AFTER the hook, exactly as it was off the incumbent map.
6. Serve seam (recorded honestly): scoring is per-side; each side's run
   re-anchors ITS OWN band rows against the other side's scored artifact
   (regen order writes hit before pit, so the pit run reads same-regen hit
   inputs and the hit run reads previous-regen pit inputs; the joint key
   uses only fix-invariant fields (rank_war, realized_war_6yr) plus the
   stamped incumbent display (xfv_grade_display_preside), so the fixed point
   is reached within one regen and repeated regens on identical inputs are
   idempotent). Serve-time crosswalk curves are fit on the full labeled
   pools (the production-fit analogue); the EVAL frame below fits them per
   fold on PRE-FOLD train rows only (OOS-honest).

## Frozen gates (registered BEFORE the lab run; seed 20260723, 2000 reps)

Eval frame: F-SIDE full_pool_km, forward-chained folds 2020-2023, live
lambdas hit 0.70 / pit 0.52, prototype-verbatim incumbent display map;
candidate = the mechanism above applied within each fold-year test pool with
per-fold train-fit crosswalks. Lab: tools/efv_side_fairness_fix_lab.py ->
data/xfv_side_fairness_fix_eval.json.

- G1' pooled-Spearman NO-HARM (the owner-re-registered framing): joint-board
  pooled Spearman(display grade, realized WAR), both sides all folds pooled;
  paired bootstrap gap = rho_candidate - rho_incumbent; PASS iff lo95(gap)
  >= -0.005 (lo95 = 5th percentile of the bootstrap gap distribution, the
  J-DISP G1 convention).
- F1 fairness efficacy (what makes this a FIX, not churn):
  - F1a: pooled candidate top-25 pit share must close AT LEAST ONE-THIRD of
    the display-vs-raw excess: share_cand <= share_inc - (share_inc -
    share_raw)/3. At the re-baselined numbers: share_cand <= 0.37 -
    (0.37 - 0.11)/3 = 0.283.
  - F1b: candidate top-25 hit-minus-pit mean diff (point estimate, seed-7
    F-SIDE-comparability stream) strictly below the incumbent 4.07.
- S1 (registered F-SIDE gate): candidate top-25 mean diff <= 5.53 AND median
  diff <= 5.01 (no widening beyond 1 SE; trivially co-satisfied with F1b for
  the mean, kept as registered for the median).
- S2 (registered): hit pooled blend Spearman floor 0.3785. The fix never
  touches rank_war; the lab ASSERTS rank_war identity per row (the blend rho
  is therefore unchanged by construction) and additionally reports the
  hit-side within-side display Spearman delta (weak ties only; expected ~0).
- S3 (registered): pit BENCH/GOOD bucket log-loss no-harm. p_bucket / p_bust
  are upstream of the display map and untouched; the post-flip battery
  ASSERTS byte-identity of p_bucket and p_bust per player in the served
  artifacts (a stronger condition than the +1.0% ceilings, which are
  recorded for reference: bench <= 0.26303, good <= 0.0452).
- S4 (registered, the anti-blanket-penalty gate):
  - S4a: the rank_war-frame mid-band cells (051-100, 101-200) and equal-FV40
    cells are display-independent; the lab ASSERTS they are identical under
    the candidate (rank_war and fv untouched).
  - S4b (ARM-2 restamp analogue): the CANDIDATE-display mid-band cells
    (051-100, 101-200) must not move hit-favorable beyond the incumbent cell
    mean diff + 1 incumbent bootstrap SE.
- Hard invariants (any violation = implementation bug, do not ship):
  - I1 below-knee rows byte-identical (display and every other field);
  - I2 within-side weak monotonicity of the candidate display in rank_war;
  - I3 per-row |candidate - incumbent| <= 3.0 FV.
- Post-flip served ceiling (standing): after defaults flip ON and regen, the
  max |xfv_grade_quantile move| among ACTIVE players vs the fresh pre-flip
  snapshot of data/xfv.json must be <= 3.0 FV; a breach REVERTS the flip
  (the S-XLINE precedent) and is recorded here.

Ship rule: ALL of G1', F1a, F1b, S1, S4b plus invariants pass -> flip
SIDE_FAIRNESS_FIX_DEFAULT to True, regen served artifacts, run the post-flip
battery (ceiling + S3 byte-identity + below-knee invariance on served files),
registry row xfv_side_fairness_fix verdict provisional, MODEL_GLOSSARY
internal entry, gen_audit_docs regen. ANY FAIL -> defaults stay OFF, the
eval artifact ships as the loss ledger, keep-alive = resolved 2024+ cohorts
(the same key as every closed top-band lane).

Vintage integrity note: the 2026-07-23 trade-deadline ingestion landed
mid-session; every OFF/ON comparison in the lab is computed in one process
from the SAME frozen post-ingestion matrix snapshot (hash-recorded in the
artifact), and the F-SIDE re-baseline above was re-run on that vintage
before any gate was judged.

## RESULTS
(2026-07-23 local run; artifact data/xfv_side_fairness_fix_eval.json; frozen
post-ingestion matrix snapshot hashes recorded in the artifact protocol)

VERDICT: **FAIL on F1b -> NO SHIP.** Defaults stay OFF
(SIDE_FAIRNESS_FIX_DEFAULT = False); the implementation remains in the tree
as a dead-by-default dial (the TOP-QUANT / S-XLINE-4 overlay precedent) and
the artifact is the loss ledger. No served number changed.

- G1' pooled Spearman NO-HARM: PASS. rho 0.2644 incumbent -> 0.2640
  candidate, gap -0.0004, lo95 -0.0015 (bar -0.005), CI90 [-0.0015, +0.0006],
  p_gap>0 0.225. The owner-re-registered no-harm band is comfortably met -
  the top-band variant avoids the full-board J-DISP Spearman tension almost
  entirely (69 of 1,650 frame rows move).
- F1a top-25 share: PASS, and strongly. Pooled candidate top-25 pit share
  0.20 vs incumbent 0.37 (bar <= 0.283; raw rank_war frame 0.11) - 65% of
  the display-vs-raw excess closed under the 3.0-FV cap. Per fold:
  2020 0.28 -> 0.16, 2021 0.48 -> 0.48, 2022 0.48 -> 0.04, 2023 0.24 -> 0.12.
- F1b top-25 equal-slot gap: **FAIL.** Candidate hit-minus-pit mean diff
  4.15 (seed-7 stream) vs incumbent 4.07; the registration demanded strictly
  below. Composition: cand top-25 = 80 hit (mean 8.50) + 20 pit (mean 4.35)
  vs inc 63 hit (9.16) + 37 pit (5.09).
- S1 no-widening: PASS (4.15 <= 5.53 mean; 2.65 <= 5.01 median).
- S2: PASS by construction (rank_war byte-identity asserted via the fold
  refit check, all 1,650 frame rows reproduced bit-for-bit; hit-side display
  Spearman 0.2757 -> 0.2742, an in-band reshuffle effect on the hit side
  only, reported for honesty - the registered S2 quantity, the blend rho vs
  the 0.3785 floor, is a function of rank_war and is unchanged).
- S4a: PASS by construction (rank_war / fv / war untouched). S4b candidate
  display mid-band restamp: PASS both cells (051-100 cand mean diff within
  incumbent + 1 SE; same 101-200).
- Invariants: I1 below-knee identity PASS (0 violations); I2 within-side
  monotonicity PASS (0 strict-pair violations, 0 candidate-introduced tie
  inversions); I3 move cap PASS (max |move| 3.0).
- LAB DEFECT RECORD (RELIEF-SHAPE precedent): the first run's I2 check
  compared adjacent rows in (rank_war, pk) order and flagged 9 rank_war TIE
  pairs (all below the knee) whose incumbent display values were assigned in
  a different list-stable order - all 9 present identically in the incumbent
  map, zero candidate-introduced. The check was corrected to the registered
  quantity (strict pairs + tie-parity vs incumbent) and the lab re-run:
  every other number identical, verdict unchanged by the fix (F1b was FAIL
  on both runs).

Structural reading (ledgered, matches the TOP-QUANT root cause): the capped
top-band joint recalibration reliably fixes the OVER-REPRESENTATION channel
(the share of top slots pitchers occupy) at zero pooled-accuracy cost, but
it cannot move the EQUAL-SLOT realized-WAR gap, because the pitcher display
tail carries no realized-WAR gradient - which pitchers survive in the top
band is outcome-arbitrary (fold 2022: nick_lodolo demoted -3.0 then realized
12.69 WAR while dl_hall was promoted +3.0 and realized 0.68), and the
hitters promoted from just below the cut dilute the hit-side mean. The F1b
metric is structurally insensitive to within-tail selection at this data
resolution.

Keep-alive: resolved 2024+ cohorts (a pitcher tail with realized gradient),
OR a NEW owner registration whose primary efficacy metric is the
over-representation channel (F1a) this mechanism demonstrably fixes - that
registration would need the owner to accept that the equal-slot gap is not
the deliverable. No re-run under THIS registration; the one attempt is
spent. Registry row xfv_side_fairness_fix (deprecated - failed F1b).
