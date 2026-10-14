# Will's-metrics integration program - pre-registered gates (2026-07-23)

Owner directive (verbatim intent): test Will's seven vendored model sources (milb-decision-plus,
defense-plus, advancement_pace, milb-projections, playing-time-model, swing-plus, xRV models)
extensively against eFV, eFV surplus, MLB Projections, FA, Trade Machine, Fantasy, PAL, and MLB
Stats; ship, create, or blend measured wins; iterate to the data ceiling. Local-only execution
per the standing 2026-07-23 directive (nothing committed; localhost serves the tree).

Registered BEFORE any arm runs. Seeds: 20260723, bootstrap 2000 reps, player-clustered where
applicable. One attempt per arm; marginal counts as FAIL; failed arms ledger their eval artifact
anyway. All new mechanisms land behind default-OFF env flags; flips, regens, post-flip ceilings,
and registry rows are executed centrally after all lane verdicts are in (never by lane agents).

## Prior-art constraint set (lanes NOT re-attempted here; recorded so this is auditable)

- Defense+ / Decision+ / def_value / p_hold as eFV WAR-model features: REFUTED 3x
  (2026-06-24 x2, 2026-06-29; memory wills-models-for-xfv-audit; data/prospect_def_value_eval.json).
  The binding constraint is the offense-dominated first-6yr-WAR target, not measurement quality.
- def_value / entropy into proj_lgbm on top of pos_adj_prior: REJECTED (same record).
- Swing+ / bat-tracking aggregates / pa_value-style blends into pWOBA / fwdHEM+: FROZEN until the
  2026-11-15 re-gates (data/bat_tracking_eval.json, data/pwoba_blend_regate_eval.json). New arms
  are REGISTERED for that date below (section W-NOV), not run now.
- Sub-AAA Statcast grade-path overlays: TERMINAL until A-ball cohorts resolve into the training
  matrix (~2028) per the S-XLINE-4 record (docs/efv-2026-07-23/GATES.md). Not re-registered.
- Advancement Pace+ into any predictive or valuation head: FORBIDDEN by the module's own
  contract (model_eligible=false; forbidden consumers name eFV/xFV/readiness/valuation).
  Display-layer use is sanctioned by its permitted-consumer list and handled as product work.
- xRV pkls as a scoring engine: DECLINED without a gate. Zero validation artifacts, college-only
  calibration (an average MLB fastball scores far above its own league anchor), degenerate
  sub-models (SV n=27), no handedness handling, dominated by stuff_plus_aaa at AAA. The drop's
  value is (a) the governance fix for the already-shipped CollegeSavant stuff+ lineage and
  (b) the W4 covariate experiment below, run on the shipped CollegeSavant payloads.
- MiLB pitcher eWAR / park factors v2 / latent_rate_talent / milb_xwar_projection (Will's
  milb-projections handoff): DATA-BLOCKED - zero artifacts exist locally; adapters skip. Owner
  action recorded: request the private export bundle via reports/EXTERNAL_BUILDER_START_HERE.md.
  W2 below builds the park layer in-house from our own StatsAPI access instead.
- Defensive aging slopes / def_war_share into FA long-deal decay: DECLINED. Prior ledgers
  (proj def_war_share regression, star under-projection contraindication, 2026-06-29) cover the
  mechanism class; Career+ absolute dWAR is self-refuted by its own backtest (bias -45 runs).
  Keep-alive: position-cohort PT aging profile, only under a fresh registration with owner ask.
- Full playing-time-model GBM reimplementation: STAGED, not attempted whole. W1 is the tractable
  leakage-clean slice (IL-history PT risk). The OD-roster / 40-man feature family is a named
  keep-alive pending a historical roster backfill.

---

## W1 PT-RISK: injury-history playing-time adjustment in fa_projection PT

Mechanism under test: additive PT adjustment on the Marcel PT block of
fa_projection.project_player (the pt computation, currently w1*e1 + w2*e2 + base + aging delta),
behind env flag EEPHUS_PT_RISK (default OFF). Adjustment = ridge fit on PT residual
(realized PA - incumbent Marcel PT prediction) using ONLY completed-season injury features
reconstructed from the league-wide StatsAPI transactions log:
il_days_prior1, il_stints_prior1, career_il_days, career_il_stints, age, age x il_days_prior1.
Frozen feature list; no additions after data is seen. Hitter arm ARM-H primary; pitcher arm
ARM-P (same features on IP-scale residual) runs regardless of ARM-H verdict, judged alone.

Data phase: fetch league transactions 2015-2026 (statsapi /api/v1/transactions per year),
cache .cache/mlb_transactions/, reconstruct IL stints (placement/activation pairing by person id).
STOP-D: if reconstruction yields under 15,000 stints for 2016-2025 or per-year placement counts
implausible vs the known ~1,500-2,500/yr scale, HALT the lane, record data-blocked.

Clauses (dev bases 2019-2021 forward-chained; holdout bases 2022-2024 touched ONCE):
- C1 (primary, PA accuracy): pooled dev PA MAE strictly improves vs the incumbent Marcel PT on
  identical rows AND pooled holdout PA MAE strictly improves AND player-clustered bootstrap lo95
  of the dev MAE improvement > 0 (2000 reps, seed 20260723).
- C2 (WAR no-harm): proj_eval-protocol h1 WAR MAE with the adjustment ON is not worse than OFF
  by more than +0.005 on dev AND on holdout.
- C3 (bounded pull, a priori): |pt_adj| clamped at 150 PA (hit) / 60 IP-equivalent (pit); clamp
  values are round a-priori bounds, never retuned after seeing gate data.
- C4 (sanity): pt_proj floors at 0; projected league PA sum moves under 2 percent.
Ship rule: on ALL of C1-C4 pass for a side, that side's flag flips ON centrally; regen
mlb_projections/fantasy/fa artifacts; registry row fa_pt_risk (provisional);
artifact data/fa_pt_risk_eval.json (written on any verdict, including STOP-D).
Keep-alive on FAIL: re-gate at extended IL history (2027), or with the OD-roster backfill.

## W2 PARK-LINE: in-house MiLB park factors + measurement blend into eFV rates

Mechanism under test: (i) team-season MiLB park factors (run PF + HR PF) built from our own
StatsAPI schedule scores, league-season centered, EB-shrunk toward 1.0 with a-priori game-count
prior K_G = 70, applied as a 3-season venue window using only seasons <= t (vintage-safe);
(ii) player-season rate neutralization at the eFV measurement layer (the S-XLINE pattern:
adjust the stat line BEFORE level-relative conversion) behind flag EEPHUS_PARKLINE (default
OFF), hooked exactly like efv_statcast_line in efv_dataset._milb_features, seasons 2021+ only,
players with a single dominant affiliate (>= 70 percent of PA/BF) only.

Data phase: (a) schedules with scores, sportIds 11/12/13/14/16, seasons 2021-2026, cache
.cache/milb_schedules/; (b) player-to-affiliate season mapping via a season-stats refetch that
KEEPS the team split, cache .cache/milb_team_stats/. STOP-D: either sub-phase failing cheaply
(endpoint shape, coverage under 90 percent of team-seasons) halts the lane, recorded.

Neutralization formulas (FROZEN a priori, before any data phase or arm ran; chosen for
convention-simplicity, never retuned): applied_run_pf = (venue_run_pf + 1) / 2 (half of games
are on the road, treated as neutral); applied_hr_pf = (venue_hr_pf + 1) / 2. Hitters: obp, slg,
ops, iso each divided by sqrt(applied_run_pf) (the conventional dampened rate correction).
Pitchers: era divided by applied_run_pf (runs scale 1:1). K and BB rates untouched (the layer
carries run and HR factors only, per the source design it mirrors).

Clauses:
- M (measurement validity, per side): among players with a dominant affiliate and >= 100 PA
  (hit) / >= 40 IP (pit) in consecutive seasons (next season may be 2026 only if it already has
  the same qualifying exposure), park-neutralized OPS (hit) / park-neutralized ERA (pit)
  predicts the player's own next-season raw rate better than the raw current-season rate:
  Spearman delta bootstrap lo95 > 0, 2000 reps, seed 20260723.
- 1 (invariance): flag OFF, and flag ON for uncovered rows (pre-2021, no dominant affiliate,
  unmapped venue), produce byte-identical matrices. Any drift = FAIL, implementation bug.
- 2 (in-matrix no-harm): pooled OOS blend Spearman delta >= -0.003 per side with the layer ON
  (expected ~neutral: 2021+ features reach only late cohorts; the claim is measurement, not
  training gain - the S-XLINE precedent).
- 3 (bounded pull, a priori): run PF clamped [0.90, 1.10], HR PF clamped [0.80, 1.25] at
  application time; round a-priori bounds, never retuned.
Ship rule: M + 1 + 2 + 3 all pass on a side -> central flip for that side, full regen, post-flip
served ceiling: max |xfv_grade_quantile move| among active players <= 3.0 FV vs the pre-flip
snapshot; breach -> retract, amend only with a-priori caps, full re-run (S-XLINE protocol).
M fails but factors build cleanly -> park factors ship DISPLAY-ONLY as a product option
(no gate needed; changes no served model number); loss ledgered.
Artifact data/xfv_park_line_eval.json; registry row xfv_park_line.

## W3 PAL-XRV: per-pitch-type aStuff+ into PAL conversion inputs

Mechanism under test: stuff_plus_aaa extended to emit per-pitch-TYPE scores (same trained
model, same cache, aggregation by pitch type; sidecar fields by_type per pitcher - no retrain,
no change to the existing pooled score). ARM-1: PAL stuff read upgraded - stuff_quality_score
(RP->SP) and stuff_upside (SP->RP) blend the arsenal est_woba read with a usage-weighted
per-type aStuff+ composite at w = 0.5, ONLY for pitchers with >= 100 recent AAA pitches
(current or prior season); uncovered pitchers byte-identical. Behind flag EEPHUS_PAL_XRV
(default OFF). ARM-2 (display, no served FIT change): recommend_pitch ranks candidate pitch
adds by family-hole x league-mean per-type run value instead of fixed rule order.

Clauses (ARM-1, per direction, the pal_backtest_lab retain rule):
- P1: rho(FIT, realized war_delta) with the blend ON >= incumbent rho on the identical
  conversion set, per direction (RP->SP and SP->RP judged separately).
- P2: bootstrap gap lo95 > -0.01 (2000 reps, seed 20260714 to match the PAL harness convention).
- P3 (invariance): pitchers without AAA coverage produce byte-identical FIT scores.
Expected coverage note (recorded a priori): most historical conversions lack recent-AAA
coverage; if covered-n per direction < 12 the verdict is COVERAGE-STARVED (not PASS/FAIL),
ARM-1 stays OFF, and the per-type sidecar + ARM-2 ship as display product only.
Ship rule: P1+P2+P3 pass -> central flip; PAL export regen; registry pal_stuff_xrv;
artifact data/pal_stuff_xrv_eval.json (all verdict classes ledger).

## W4 COL-XRV: college stuff+ covariate in the pitcher college->pro K% translation

Governance (unconditional, no gate): the shipped CollegeSavant stuff_plus lineage gets its
registry row + eval artifact (scale documentation, coverage, agreement with Will's xRV vintage
r ~ 0.959 on 1,472 overlapping rows, plus whatever forward checks matched pairs support).
Fixes a standing-rule violation that predates this program.

Mechanism under test: usage-weighted college stuff+ (from the shipped CollegeSavant per-pitch
payloads, TrackMan-id keyed) as an additional covariate in the pitcher college->Single-A K%
translation, matched-pairs leave-one-out protocol (the college.py harness family).
STOP-D: if matched college->pro pairs with stuff+ coverage number under 40, record
COVERAGE-STARVED, ship governance only.
Clauses:
- K1: LOO K% MAE strictly improves vs the stat-line-only translation on identical pairs.
- K2: bootstrap lo95 of the improvement > 0 (2000 reps, seed 20260723).
Ship rule: K1+K2 -> covariate lands behind flag EEPHUS_COL_XRV, central flip, collegesavant
translation artifacts regen. Artifact data/college_stuff_translation_eval.json; registry row
college_stuff_translation. FAIL ledgers; keep-alive keyed to next draft-class resolution.

---

## W-NOV: arms REGISTERED now for the frozen 2026-11-15 re-gates (NOT run in this program)

Appended to docs/efv-2026-07-23/RECHECKS.md alongside the existing pwoba_blend_regate and
bat_tracking_hitters re-runs, to be executed at the same sitting with complete 2026 outcomes:
- NOV-A (bat_tracking revival, new arm): the vendored Swing+ composite (per-season variant)
  replaces the raw bat-tracking z-aggregates as the BT leg in both the pWOBA and fwdHEM+ arms.
  Rationale recorded now: Swing+ is a validated nonlinear composite of the same fields
  (next-half xwOBAcon r 0.65 vs 0.58 bat-speed-only); arm B's 2026-07-23 miss was lo95 -0.0009.
- NOV-B (pwoba revival, new arm): pa_value-style k-blend of observed and swing-model xwOBA
  (k frozen at the vendored artifact's fitted values) as the est_woba leg.
Bars inherit the parent registrations. No 2026-outcome-dependent lane may run before Nov 15.

## Product wave (display-only, no gates required; owner-directed ship, sanity checks only)

- W5 AP+: Advancement Pace+ rebuilt from the platform milb_stats cache (2014+), hitters,
  internal column names never colliding with eFV level_rank; card block (score, percentile,
  tier, level trajectory ladder) per the module's own display charter; explicitly never an
  input to any model (enforced in code comment + test).
- W6 SWING-SEASON: per-season Swing+ from the existing swing_pitches cache (ingest group_by
  season), swing_plus.json schema extended backward-compatibly; projections-card trend +
  fantasy buy/sell mechanics-trend context.
- W7 DEF-RISK: defensive-home certainty chip (p_hold / position-distribution entropy) from the
  existing data/prospect_def_value.json on premium-position prospect cards; risk context only,
  never a grade input.

## RESULTS

(appended after runs)

### W2 PARK-LINE (run 2026-07-23; artifact data/xfv_park_line_eval.json)

Data phase COMPLETE: schedules 30/30 sport-seasons (~1,900-2,400 completed games each,
2026 partial in-season), player team-split season stats 60/60, team home/away splits
120/120. STOP-D PASS: run-PF coverage 1.0000 (1211/1211 observed team-seasons; bar 0.90);
hr_pf covered 1083/1211 (cheaply derivable via team statSplits, built as registered).
Factor table data/milb_park_factors.json (overwrites the deprecated 2026-07-02 R-PARK
infeasibility stub at the same path; that experiment's own loss ledger stays at
data/milb_park_factors_eval.json): 202 venues, league-season centered, K_G=70, 3-season
vintage-safe windows. Face-valid extremes: Hodgetown run 1.209 / HR 1.428 (window 2026),
Las Vegas 1.121/1.210, McCormick 1.133/1.215; Dickey-Stephens 0.840/0.751.

Clause M FAIL both sides (one attempt, marginal counts as FAIL):
  hit n=7527 pairs / 3606 players: rho_raw 0.2816 vs rho_neut 0.2821, delta +0.0005,
    lo95 -0.0011 (hi95 +0.0021, p_gt0 .716). Point-positive but not CI-clean.
  pit n=3073 pairs / 1863 players: delta -0.0021, lo95 -0.0051 (p_gt0 .074). Negative.
Clauses 1-3 all PASS both sides (implementation sound): clause 1 OFF byte-identical to
the committed-behavior baseline, 0 uncovered-row violations (hit 606 / pit 536 covered
rows moved, all inside the allowed feature set); clause 2 pooled OOS delta hit -0.0002 /
pit +0.0009 (bar -0.003); clause 3 clamps in code match registered bounds.

VERDICT per side: M-FAIL-DISPLAY-CANDIDATE (the registered fallback: factors built
cleanly, measurement clause missed, so the layer stays OFF permanently under this
registration and the factor table is sanctioned to ship DISPLAY-ONLY as a product
option). EEPHUS_PARKLINE_HIT / EEPHUS_PARKLINE_PIT remain default OFF; matrices
restored byte-identical to the pre-lane state. Consolidator: no flip, no regen;
add registry row xfv_park_line (loss ledger) pointing at the eval artifact; the
display-only factor-table ship is an owner product decision, not a gate matter.
Mechanism read: a half-weighted sqrt-damped one-park correction is small against
season-to-season noise plus the level-norm machinery eFV already applies; keep-alive
would need within-level home/road splits or multi-season player-park exposure, neither
registered here.

## W1-B amendment (registered 2026-07-23, after the W1 STOP-D fired and BEFORE any C-clause ran)

W1 halted on STOP-D: reconstructed MLB IL stints 2016-2025 = 8,271 vs the registered floor
15,000. Diagnosis (recorded in data/fa_pt_risk_eval.json): the floor was mis-scaled - the
registered ~1,500-2,500 per-year plausibility band is roughly 2x true MLB IL volume; the
reconstruction matches published IL-record reporting nearly exactly (2017: 694 vs ~700
published; 2018: 730 vs ~737). This is the S-XLINE-2 yardstick-mismatch class: the STOP rule
measured the wrong scale, the mechanism was never tested, dev bases were never scored, and
the 2022-2024 holdout is untouched.

Single amendment: STOP-D floor re-derived from the PUBLISHED IL-record scale (not from our
measured count): pre-COVID MLB placements run ~550-900 per year, so the 2016-2025 floor is
6,000 stints with a per-year plausibility band of 450-2,600 (2021 COVID-IL era allowed high).
Every other clause (C1-C4), the frozen feature list, arms, seeds, clamps, dev/holdout split,
and the ship rule are IDENTICAL to the W1 registration. One attempt stands: the C-clauses
have never run and run once under this amendment.

## RESULTS (recorded 2026-07-23, central consolidation; W2's own section appended by its lane)

- W1 PT-RISK: STOP-D (floor mis-scaled 2x vs published IL volume; substrate verified correct).
  W1-B amendment: STOP-D CLEARS (8,271 >= 6,000, all years in band) then BOTH ARMS FAIL the
  C-clauses honestly: ARM-H dev MAE improves +2.84 (lo95 +1.39) but holdout WORSENS 3.16 and
  league PA drift 3.48 percent breaches C4; ARM-P fails C1 dev lo95 and holdout. Mechanism
  ledgered: real in-era bounce-back signal, but post-2021 IL volume runs ~40 percent above the
  training era so the mean-zero-at-fit adjustment adds net PT out-of-era. EEPHUS_PT_RISK stays
  OFF; no sidecar written. Keep-alive: 2027 extended IL history WITH per-era standardization
  (pre-recorded requirement), or the OD-roster backfill. Ledger data/fa_pt_risk_eval.json.
- W2 PARK-LINE: M-FAIL-DISPLAY-CANDIDATE both sides (hit delta +0.0005 lo95 -0.0011; pit
  -0.0021 lo95 -0.0051); implementation clauses 1-3 all PASS; matrices restored byte-identical;
  EEPHUS_PARKLINE_* stay OFF permanently under this registration. The 202-venue factor table
  (data/milb_park_factors.json) stands as the sanctioned display-only product option.
  Ledger data/xfv_park_line_eval.json.
- W3 PAL-XRV: ARM-1 COVERAGE-STARVED (2 of 25 RP->SP, 5 of 61 SP->RP covered vs floor 12;
  retain rule never run, one attempt preserved; revival ~2028 when post-2023 AAA graduates
  accumulate). Sidecar per-type extension SHIPPED invariant-clean (pooled scores byte-identical,
  1,379 pitchers gain by_type + league xRV meta); ARM-2 recommend_pitch xRV ranking SHIPPED
  (display; 3 of first 4 sample recommendations reordered). Ledger data/pal_stuff_xrv_eval.json.
- W4 COL-XRV: gate FAIL decisively (college stuff+ vs first-pro K% r = -0.005 on 257 covered
  pairs; LOO MAE worsens 4.392 -> 4.416, lo95 -0.056). EEPHUS_COL_XRV stays OFF; keep-alive next
  class resolution. Part A governance SHIPPED: data/collegesavant_stuff_eval.json (formula
  verified exact vs Will's vintage, agreement r 0.9594 on 1,472 rows, three-scale collision
  warning). Ledger data/college_stuff_translation_eval.json.
- Product wave SHIPPED (display-only, sanity checks green): W5 AP+ (advancement_pace_export.py,
  data/advancement_pace.json 3,026 hitters + prospx panel + glossary advancement_pace_plus;
  descriptive contract enforced, ap_-prefixed fields), W6 per-season Swing+ (swing_plus.json
  seasons slices, pooled values byte-identical; projections trend tile; fantasy mechanics-trend
  chip, buy/sell ordering verified unchanged), W7 def-home chip (def_home_export.py ->
  data/def_home.json, 2,463 premium-listed hitters, tercile bands, live_listed basis flagged),
  plus the per-date news GFX (all-items guarantee, headshots + logos, canvas growth ladder).
- P1 V3 (registered in docs/efv-provisional-prior/GATES.md): ARM-A slot-trust PASS + SHIPPED
  (default ON in efv_score; post-flip served battery 12 movers, all upward, max +2.3 <= 3.0,
  zero downward; regen determinism verified 0 diffs). ARM-B DSplus and ARM-C FAIL B1 (DSplus
  adds nothing over pick tier + bonus on 294 resolved 2018-2019 draftees); flags stay OFF.
  Emerson: 48.6 -> 50.2 served (war 4.51 -> 4.99).

### W-NOV (run 2026-10-14 as OWNER-WAIVED EARLY READS; registered date was 2026-11-15)

Run by NOV15_REGATES under the owner's waiver of look days (EW3-5) and the logged
season-complete override treating 2026 as complete as of 2026-10-01 (EW3-6,
tools/plus_lab_harness.py PLUS_LAB_SEASON_COMPLETE_ASOF; the Nov 15 default is unchanged), with
the parents' frozen protocols and bars inherited. Full numbers in docs/efv-2026-07-23/RECHECKS.md
'2026-10-14 - RESULTS'.
- NOV-A: NULL on both arms (arm A gap v1 lo95 -0.0152 on 149 pairs; arm B lo95 -0.0088 on 184
  pairs). The per-season Swing+ variant exists (W6) but covers 173 / 244 bats in 2024 / 2025, so
  the pair sets are a third of the parent's. Artifact data/bat_tracking_nov_a_eval.json, registry
  row bat_tracking_nov_a.
- NOV-B: NOT AVAILABLE, not run: no per-player-season swing-model xwOBA exists on the platform
  (the vendored Swing+ artifact carries none; the registered k 250 lives in the un-vendored
  research file swing-plus/pa_value_models.joblib). Nothing was substituted.
- The parents at the same sitting: pWOBA xwOBA-blend re-gate PASS (n 953, gap v1 lo95 +0.0019;
  production diff built behind EEPHUS_PWOBA_XWOBA_BLEND, default off, owner flips); bat-tracking
  arm B PASS provisional small-n (lo95 +0.0015 on 528 pairs), arm A NULL.
