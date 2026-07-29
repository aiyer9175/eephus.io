# eFV holistic program - pre-registered gates (2026-07-24 cycle; plan: docs/plans/efv-holistic-2026-07-23.md)

Owner directive: maximize eFV + surplus Spearman/AUC across eras, tiers, cohorts,
disagreements, head-to-head; wRC+ lane; full pitcher physics + hitter Statcast component
sweep; platoon; tiebreaker; bug hunts; all-modules holistic. "Proceed" given 2026-07-23.

Registered BEFORE any arm runs. Default seed 20260724, 2000 bootstrap reps,
player-clustered unless stated. One attempt per arm; marginal = FAIL; failed arms ledger.
All mechanisms default-OFF until central flip; post-flip served ceiling 3.0 FV vs a
pre-flip snapshot unless a lane defines its own display-space bound. Same-run baselines
only. Data pulls are data-phase (STOP-D checks below), never gate evidence.

Prior-art: the closed-lane appendix of the plan binds this whole file; no listed lane
re-runs here.

---

## G-SCORE (Phase 0a, no gate): the eFV Scoreboard
tools/efv_scoreboard.py -> data/xfv_scoreboard_eval.json + glossary panel. Pooled
Spearman/AUC, per-era, per-tier, per-cohort, t45/wm, head-to-head vs consensus/FG/Pipeline,
top-20-percent capture, biggest-disagreement receipts; win/loss marked per cell.
Descriptive; registered here so the artifact has a registration pointer.

## G-BUGS (Phase 0b, no gate): adversarial bug hunts
Three read-only finder fronts (feeds / score path / surplus chain) + adversarial verify;
only CONFIRMED defects get fixes; correctness fixes ship without gates; any served-number
change runs the standard battery + ledger note. Findings artifact:
data/xfv_bughunt_2026_07_24.json (companion on xfv_hitter/xfv_pitcher rows).

## W-XLINE-W (Phase 1a): S-XLINE hitter weight amendment
Mechanism: efv_statcast_line W_HIT 0.5 -> 0.7 (single arm; pit untouched; caps
D_CAP_AVG/OBP/SLG unchanged). Clauses:
- M': on the SAME measurement pairs protocol as the shipped study, blend at w=0.7 beats
  raw with lo95 > 0 AND point(0.7) >= point(0.5). (Re-read of the existing grid, frozen
  protocol, no new freedom.)
- 1: uncovered-row invariance byte-identical; OFF = committed behavior.
- 2: in-matrix pooled OOS no-harm >= -0.003 both sides.
- Ship: flip W_HIT constant; combined post-flip battery with W-XISO if both pass
  (single 3.0 FV ceiling vs one pre-flip snapshot).
Artifact: data/xfv_statcast_line_eval.json gains a w07 block (companion).

## W-XISO (Phase 1c): S-XLINE fourth delta
Mechanism: d_iso = W_HIT * cap(x_iso_gap, 0.060) where x_iso = xslg - xba from the same
Savant aggregates; cap 0.060 a-priori round. Clauses: M (iso-gap blend predicts
next-season iso better than raw, lo95 > 0), 1 invariance, 2 no-harm >= -0.003, ship as
above. Artifact: same file, xiso block.

## W-WRC (Phase 1b): in-house linear-weights rate
Data phase: .cache/milb_full_stats/ full-component refetch (2B/3B/HBP/SF/SB), sportIds
11-14+16, 2011-2026. STOP-D: component coverage under 85 percent of matrix player-seasons.
Build: woba-lite with fixed FG-style weights scaled to league-season run environment;
level-relative, reliability-shrunk (K_REL_PA 100) -> wrc_rel. NO park layer.
A-priori null recorded: decomposed components usually dominate composites.
Arms (efv_lab_runner, hit side; one attempt each, judged independently):
- A1 replace: wrc_rel in place of ops_rel. Bar: pooled OOS blend Spearman delta >= +0.004
  AND wm >= -0.0011.
- A2 add: wrc_rel alongside. Same bars.
- A3 fringe: t45 >= +0.015 with pooled AND wm >= -0.0011 (LR-FRINGE convention).
- A4 (conditional, registered now): shrunken component-weighted composite fitted to
  next-season woba (measurement clause M lo95 > 0 prerequisite) as a feature; runs ONLY
  if A1 or A2 shows point-positive pooled delta; same bars as A2.
Ship: highest passing arm only. Artifact: data/xfv_wrc_eval.json.

## W-SB (Phase 2c): hit_sb_rel
sb rate vs level norm, shrunk, from the same refetch. Bar: pooled >= +0.004 AND wm >=
-0.0011; fringe signature records keep-alive only (no fringe ship this cycle).
Artifact: xfv_wrc_eval.json sb block.

## W-PLATOON (Phase 2a): platoon split features - the headline lane
Data phase: statsapi statSplits vl/vr, hitting + pitching, sportIds 11/12/13/14/16,
seasons 2011-2026, cache .cache/milb_platoon/. Probe 2011-2014 first. STOP-D: pull
infeasible OR split coverage under 60 percent of matrix player-seasons 2015+ (earlier
seasons may be missing-flagged like other vintage-limited features; that alone is not a
STOP).
Frozen features (reliability-shrunk at K=100 split-PA/BF, level-relative where normed):
- hit: platoon_gap_rel (weak-side minus strong-side woba-proxy gap vs level norm),
  same_hand_share (exposure context), bats_s (switch indicator).
- pit: platoon_gap_rel (opposite-hand vulnerability), opp_hand_share.
Arms (efv_lab_runner, per side, judged independently): full set per side; then a
pre-registered fringe read (t45 >= +0.015, pooled/wm >= -0.0011) if the full-set pooled
read is flat. Pooled ship bar: >= +0.004 AND wm >= -0.0011 per side.
Cohort hypothesis recorded a-priori: target weak cells = int'l bats + top-25 pitchers;
per-cohort reads reported, never gating (the +-0.01 AUC noise floor stands).
Artifact: data/xfv_platoon_eval.json.

## W-DISC (Phase 2b): swing-decision components -> xfv_ungraded ONLY
Features from cached A/CPX/AAA game feeds (2023+, our own call codes): take_share_rel,
zone_rec_proxy (z-take minus o-take proxy from pixel zones where present else call-code
approximation - method frozen in the lab header before the run), twoK_take_rel.
Harness: xfv_ungraded OOS protocol (low-minors target cohort). Bar: low-minors pooled
Spearman delta lo95 > 0 (2000 reps, seed 20260724). Ship: ungraded feature list + regen
(provisional cohort only). Flagship matrix lane stays closed. Artifact:
data/xfv_ungraded_disc_eval.json.

## W-SCREEN (Phase 3b): pitcher physics forward screen (one shot)
Sample: AAA pitchers with consecutive-season pairs 2023->2024, 2024->2025 (complete next
seasons only). Frozen candidates: velo, ivb, hb_abs, spin, ext, rel_ht, arm_angle,
mix_entropy, stuff_spread (per-type aStuff+ SD), velo_adj_ivb (ivb residual on velo),
vaa + vaaoe (ONLY if the bounded refetch lands; absence recorded, not a STOP).
Per candidate: incremental Spearman vs next-season K% (whiff-family) or ERA (others)
AFTER residualizing on pooled aStuff+; survivor bar: lo95 > 0. Survivors become OVERLAY-R
legs with coefficients frozen from this screen. Artifact: data/aaa_physics_screen_eval.json.

## W-SCREEN-SUB (owner addendum 2026-07-23, registered before any sub-AAA arm ran):
## A / CPX pitcher physics screen from cached StatsAPI game feeds
Owner direction: extend the physics screen below AAA the same way the Statcast-percentiles
work already derives sub-AAA metrics from MLBStatsAPI feeds. Sample: A and CPX pitchers
with consecutive-season pairs (2023->2024, 2024->2025) whose physics come from the cached
game feeds (.cache feeds, 8,702 games; TRACKED PARKS ONLY - untracked parks are absent,
recorded as coverage, never imputed). Reuse the S-XLINE-2/3 feed-parsing machinery
(tools/efv_statcast_line2_lab.py) rather than re-implementing extraction.
Frozen candidates (subset of W-SCREEN, limited to feed-derivable fields): velo, ivb, hb_abs,
spin, rel_ht (from x0/z0), mix_entropy, vaa + vaaoe where coordinate vectors exist.
Protocol identical to W-SCREEN: incremental Spearman vs next-season K% (whiff-family) or
ERA (others) after residualizing on the frozen stat-line ridge from the line-4 lab (the
sub-AAA analog of the aStuff+ residualization; the exact residualizer is named in the lab
header BEFORE any correlation is computed), survivor bar lo95 > 0, 2000 player-clustered
reps, seed 20260724, ONE attempt. Qualification floors: >= 150 tracked pitches both
seasons, >= 40 IP-proxy outcomes. Survivors feed W-OVERLAY-R legs under the same 4.0/40
ceiling, coverage-gated to tracked-park players only (invariance: untracked players never
move). Closed lanes stay closed: nothing K-measurement-shaped vs raw K%, no raw-EV hitter
features. Artifact: data/aaa_physics_screen_eval.json sub_aaa block (same file, separate
frozen section).

## W-OVERLAY-R (Phase 3c): overlay revival under a display-space ceiling
Mechanism: the built efv_statcast_overlay (frozen coefficients, beta 0.6, internal FV-lean
cap 2.0, model-leg-only, blend rebuild) with legs whiff (hit) + fb_velo (pit) + any
W-SCREEN survivors (frozen coefficients). NEW registered ceiling (the S-XLINE-4 keep-alive
prescription, owner-authorized): after flip + full regen, for every active player the
served xfv_grade_quantile may differ from a same-run NO-OVERLAY shadow ranking by at most
4.0 FV AND at most 40 board rank positions. (Owner-selected 2026-07-23 via the decision
queue, choosing the looser of three offered bounds BEFORE any overlay arm ran; the 3.0/25
draft bound is superseded.) Clauses:
- 1: OFF = byte-identity (already test-pinned).
- 2: only covered players move (signal coverage from statcast_alevel_signals + AAA sample
  floors as built).
- 3: ceiling battery as defined above; breach -> revert + record (no amendment this cycle).
Ship: flip OVERLAY_HIT/PIT defaults. Artifact: data/xfv_statcast_overlay_eval.json
(new; the deprecated registry row updates to provisional on PASS).

## W-PROXY2 (Phase 4a): xfv_proxy v2
Expanded features (hit: whiff/chase/z-contact/xwobacon/ev90/maxev/barrel/hardhit/pull-air
from savant_minors + feeds; pit: physics profile + per-type stuff + mix). Same forward
protocol as shipped proxy. Bar per side: OOS r improvement vs same-run shipped-proxy
baseline, lo95 > 0. Ship: proxy artifact regen + detail tile continues as leading
indicator. Artifact: data/xfv_proxy_eval.json v2 block.

## W-TBS2 (Phase 4b): tiebreaker stack
Universe: resolved cohorts, tie groups = identical displayed quantile grade at 0.1 grain.
Stack: xfv_proxy score, then p_bucket star odds, then aStuff+ (pitchers). Metric: pooled
within-tie realized-6yr-WAR ordering (Spearman across tie groups, group-clustered
bootstrap). Bar: improvement over incumbent TBS ordering, lo95 > 0, seed 20260724.
Constraint recorded: AP+ contractually excluded from any ordering role. Ship: prospx
tie-break comparator update (single-owner prospx pass at consolidation).
Artifact: data/xfv_tbs2_eval.json.

## W-SURPLUS (Phase 5):
- S1 isotonic refresh: refit calibration on the current resolved pool
  (tools/fit_surplus_calibration.py). Bars: LOyO held-out slope in [0.90, 1.10] AND
  PIT coverage >= the shipped artifact's. Ship = calibration block restamp + ledger.
- S2 eta-hazard-lite: 40-man selection (historical selection dates from the
  .cache/mlb_transactions substrate) + level + age adjust eta_years. STOP-D: historical
  selection-date coverage under 60 percent of debuted cohort. Gate: eta_backtest
  forward-chained debuted MAE improves AND within-1yr share improves; overdue guardrail
  within +-120 of the accepted KM drift. Artifact: data/eta_hazard_eval.json.
- S3 role-arg A/B: sv_distribution position arg from measured positions_played primary
  vs listed. Gate: resolved-pitcher bucket likelihood (pooled logloss) not worse AND
  role-mismatch subcohort improves; if no clean resolved read exists the lane records
  AUDIT-ONLY (no ship) - honesty over reach. Artifact: data/xfv_role_arg_eval.json.

## W-FSIDE-SHIP (owner-authorized 2026-07-23 via the decision queue): joint top-band
## display recalibration as a FAIRNESS fix
The recorded owner option from the 2026-07-15 joint-display-map ledger is now exercised:
the pooled-gain bar G1 re-registers as NO-HARM. Mechanism: the in-tree default-OFF joint
top-band recalibration (efv_score F-SIDE-FIX hook family; the lane agent reconciles the
07-15 ARM-2 candidate with the in-score implementation and states which shipped mechanism
is under test BEFORE running). Fresh one-attempt run at current vintage. Clauses:
- G1' pooled OOS Spearman delta lo95 >= -0.005 (no-harm, owner-authorized framing).
- G2 fairness efficacy: top-25 hit-over-pit realized-WAR gap shrinks vs incumbent AND
  top-25 pitcher share moves toward the measured deserved share.
- G3 mid-board no-harm: ranks 51-200 pooled Spearman delta >= -0.003.
- G4 flag-OFF bit-identity.
- Battery: served moves confined to the top band (top 50 overall); max served
  xfv_grade_quantile move <= 4.0 FV (aligned with today's owner bound); full mover log.
Ship: flip the in-score default. Artifact: data/xfv_fside_ship_eval.json.

## W-STAR (Phase 6, projections): star-slice-only mean head
The one unexplored variant from the mean-head ledger: apply the mean-head recenter to the
ex-ante star slice only, all horizons. Harness: mean_head_backtest variant. Bars: star
bias improves on dev AND holdout; pooled MAE not worse than +0.005 dev AND holdout.
Artifact: proj_horizon_eval.json challenger block (companion convention).

## Execution waves
A (parallel, read-only or new-file-only): G-SCORE, G-BUGS finders, data pulls (platoon,
full components, VAA-bounded), physics sidecar + W-SCREEN. B (serial): confirmed bug
fixes. C (parallel, disjoint owners): W-XLINE-W + W-XISO, W-WRC + W-SB, W-PLATOON,
W-DISC, W-OVERLAY-R, W-PROXY2, W-TBS2, W-SURPLUS, W-STAR. D (serial): flips, batteries,
regens, registry/glossary/docs, prospx wiring, scoreboard regen, RESULTS.

## RESULTS
(appended after runs)

## RESULTS - settled non-ship lanes (recorded 2026-07-24; PASS lanes pending independent verification)

Baselines same-run on the wave-B repaired tree (matrices regenerated after the label repairs;
scoreboard re-baseline hit pooled .373 / pit .302, 26/31 cells still won vs consensus).

- G-BUGS: 12 confirmed defects (2 P0 served-number, 6 P1), zero refutations; all fixed in wave B
  except named residuals. Ledger data/xfv_bughunt_2026_07_24.json. The two P0s: eFV surplus
  skipped the isotonic calibration layer site-wide (now priced through it - every prospect
  surplus moved to the calibrated basis, max_clark 65.5->72.9); the P1 V3 slot-trust
  (pick,bonus) key collision leaked into 5 served backgrade rows (now gated on
  acq_year==CURRENT_SEASON, dj_davis pedigree 1.21->0.54). Feeds: 20 MLB-career players were
  training as 0-WAR busts at full weight (adolis_garcia/senga/yoshida...) - now excluded; 24
  wrong-player mlbam resolutions nulled + a resolver vintage guard added. These are TRAINING-
  INPUT changes: matrices + goldens restamp on the central regen (done).
- W-PLATOON: FAIL both sides (hit pooled -0.0036 / wm -0.030; pit pooled -0.0108 / wm -0.0401;
  both fringe reads fail). Final-pre-decision-season platoon splits too noisy post-shrink; they
  damage within-FV-tier ordering (worst at fv40/50). A-priori int'l-bats AND top-25-pitcher weak
  cells REFUTED (extremes are small-sample reverse splits: Correa +0.14 off 72 PA vs LHP). The
  headline new-trainable-feature lane is spent this vintage. Artifact data/xfv_platoon_eval.json.
- W-OVERLAY-R: FAIL. Clauses 1 (OFF identity, tests 10/10) + 2 (covered-only) PASS, but clause 3
  ceiling breached: max 5.0 FV (bar 4.0) and max 963 board ranks (bar 40); 386/4205 = 9.2% exceed
  the 40-rank bound. Structural, not a bug: covered players cluster in the flat FV35-37.7 display
  tail where a bounded +-2.0 FV lean shoves a player a full consensus-grade step + hundreds of
  ranks. vaa leg had 0 live coverage (2026 CSVs not in the bounded refetch). Defaults stay OFF;
  no amendment this cycle. Sub-AAA survivors (ivb/vaa, 8.3% coverage) -> display-only owner queue.
  Artifact data/xfv_statcast_overlay_eval.json. Physics SCREEN survivors (AAA velo/spin/vaa,
  sub-AAA ivb/vaa) are validated signal but unshippable as a rank-moving overlay at this display
  resolution - same class as the S-XLINE-4 fringe-step blocker.
- W-TBS2: FAIL (marginal). Challenger stack (proxy->star->aStuff+) within-tie realized-WAR
  ordering delta +0.0572, lo95 -0.0008 vs bar >0. Robust: clean star-only lo95 -0.0002; vs
  eFV-only incumbent lo95 -0.0167. Proxy has 0 coverage on resolved cohorts (abstains every pair);
  aStuff+ leg is look-ahead-tainted and still fails; the incumbent xfv_war_6yr-anchored TBS wins
  the real top-of-group head-to-heads (keeps Clase 11.52 WAR over a 0-WAR tie-mate). Incumbent
  TBS retained; no prospx change. Revival = proxy accruing resolved coverage (~2030). Artifact
  data/xfv_tbs2_eval.json.
- W-PROXY2: FAIL both sides. Hit marginal (r 0.2415->0.2452, lo95 negative); pit actively
  harmful (-0.168, training-fold starvation: the 2025 fold trains on the 2024 cohort alone).
  Feature list expanded but the pre-debut Statcast substrate cannot yet carry it. Artifact
  data/xfv_proxy_eval.json v2 block. Revival ~2027 (more resolved Statcast-era cohorts).
- W-STAR (projections): FAIL. Star-slice-only mean head (the one unexplored mean-head variant)
  worsens dev star bias (+0.065->+0.276) and star MAE (1.84->1.93); clause A needs dev AND
  holdout to improve, dev regressed. The implied-mean recenter is too aggressive for the star
  slice at this vintage. Block star_slice_mean_head in data/proj_horizon_eval.json.
- W-WRC + W-SB: NO SHIP all arms. In-house linear-weights wrc_rel (no park layer) replaced/added
  vs ops_rel: the a-priori null held - eFV already consumes the decomposed pieces (k/bb/iso/obp
  rel), which dominate the composite; wrc_rel adds no pooled/fringe gain. hit_sb_rel likewise.
  INTEGRITY NOTE: the dead-run left a pre-seeded lab asserting a fabricated 'W-SB PASS' via
  mean-imputation of milb-missing rows; the resumed agent discarded it and re-ran faithfully
  (0-impute per the ops_rel convention) -> honest NO SHIP. Artifact data/xfv_wrc_eval.json.
- W-SURPLUS S3 role-arg: AUDIT-ONLY (no ship). The bucket-probability gate metric is
  position-invariant by construction (position enters only the dollar layer); measured source
  (positions_played) excludes pitchers; listed source is handedness-only for the resolved cohort.
  Future framing = GS-share role on the dollar layer, a new registration. Artifact
  data/xfv_role_arg_eval.json.

## RESULTS - PASS lanes (PENDING independent adversarial verification before any flip)
A fabricated PASS was caught in this batch (W-SB above), so W-XLINE-W/W-XISO, W-FSIDE-SHIP, and
W-SURPLUS S1/S2 are being independently re-derived before Wave D applies any served-moving flip.
Verdicts + flip records append here after verification.

## RESULTS - PASS lanes (independently re-verified, then shipped 2026-07-24)

A fabricated PASS was caught in the batch (W-SB, via mean-imputation), so all three PASS lanes
were independently re-derived by adversarial verifiers (own method, real scoring path, not the
labs) BEFORE any flip. All three reproduced to the decimal with no fabrication. Owner decisions
taken via the decision queue where the change was outward-facing.

- W-XLINE-W + W-XISO: SHIP (both arms, independently verified). efv_statcast_line W_HIT 0.5->0.7
  (M' lo95 +0.0056, point(0.7)>=point(0.5)) + fourth capped delta d_iso = W_HIT*cap(xslg-xba,
  0.060) (M lo95 +0.0154, p~1.0); in-matrix no-harm +0.0 both sides; OFF byte-identical. VERIFIED
  CAVEAT (recorded): the no-harm clause is structurally vacuous - all ~66 covered rows are 2024+
  debuts outside the 2020-2023 OOS folds, so the evidence is purely the next-season-AAA-line
  measurement proxy (same situation as the shipped w=0.5 layer); w=0.7 lifts the point delta but
  thins lo95 (XISO is the sturdier arm). Flipped both defaults; combined post-flip battery max
  move within 3.0 FV. Artifact data/xfv_statcast_line_eval.json (w07 + xiso blocks).
- W-FSIDE-SHIP: SHIP (owner-authorized, independently verified through run_live/run OFF-vs-ON).
  The wave-B label repairs flipped the fairness clause from the 07-23 FAIL to PASS: top-25 pit
  share 0.37->0.21 (toward deserved 0.12), hit-over-pit realized-WAR gap 4.07->3.85, G1' no-harm
  lo95 -0.0014, mid-board (51-200) delta 0.0, G4 OFF bit-identity. Owner chose WHOLE-BOARD
  application: 467 movers incl. debuted backgrades (Skenes/Ohtani/Giolito -3.0), all bounded by
  the mechanism's 3.0 FV cap (<= the 4.0 owner ceiling), confined to the top band. kade_anderson
  62->59, eli_willits 59->62. Default flipped ON. Registry xfv_side_fairness_fix deprecated ->
  provisional. Artifact data/xfv_fside_ship_eval.json.
- W-SURPLUS S1: SHIP (owner-authorized). isotonic-real-v3 -> v4 calibration refit; both frozen
  bars reproduce exactly under independent refit (LOyO held-out slope 1.081 in [0.90,1.10]; PIT
  P10-P90 coverage 0.869 >= v3 0.859). PROVENANCE CORRECTED by verification: v3 is NOT stale from
  the wave-B label repairs (labels aggregate-stable) - it is stale because two intentional post-v3
  valuation re-anchors (2026-06-22 xFV seam + 2026-07-04 Clemens) moved the dollar layer, so v3
  now under-prices the pool; the refit partially undoes that mid-band re-anchor (a deliberate
  recalibration, owner-acknowledged). Served FV45-55 prospect surplus +40 to +120% (pit FV45
  +120%, larger than first reported). The wave-B F1 fix (surplus prices through calibration) makes
  this load-bearing. prospx_current base-identity table RE-CAPTURED under v4
  (config/valuation_sets/prospx_current.yaml, v3 grid preserved in-file) + test_valuation_sets
  re-stamped (17.7->31.6, 69 green) + golden restamped. S2 eta-hazard PASSED its backtest but was
  NOT shipped (owner chose S1 alone); hook stays default-OFF (registry eta_hazard_lite provisional).
  S3 role-arg AUDIT-ONLY. Artifact: value_framework_config.yaml calibration block + data/eta_hazard_eval.json.

## Program tally (2026-07-24 cycle)
Lanes run: 14 (9 Wave-C gates + W-STAR + W-SCREEN x2 + G-SCORE + G-BUGS). SHIPS: 3 model/valuation
(XLINE, FSIDE, S1-surplus) + the G-BUGS correctness battery (2 P0 + 6 P1 fixed). NON-SHIPS (clean
ledgers): W-PLATOON, W-OVERLAY-R, W-TBS2, W-PROXY2, W-STAR, W-WRC/SB, W-DISC (starved), W-SURPLUS
S2 (gated-not-flipped) + S3 (audit). The headline new-trainable lane (platoon) failed; the biggest
wins were correctness (the calibration P0 + label repairs) and the owner-authorized fairness ship.
