# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""ODDS LANE: emit data/xfv_odds_dispersion_eval.json from the measured gate outputs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

gate = json.loads((ROOT / "tools" / "_prem_odds_gate_out.json").read_text(encoding="utf-8"))
sv = [k for k in gate if k.startswith("SERVED")][0]
g = gate[sv]

art = {
 "generated_at": "2026-07-25",
 "model": "eFV outcome-odds DISPERSION calibration (served p_bust read at the realized-implied grade)",
 "lane": ("odds -- the CONDITIONAL p_bust surface. The concurrent thin-sample lane "
          "(data/xfv_thin_pbust_eval.json) is DISJOINT: it owns efv_ungraded PROVISIONAL "
          "rows, this owns source-graded served rows. No collision."),
 "status": ("CANDIDATE. Patch written and INERT (efv_odds_calibration.py + "
            "tools/_prem_odds.patch); efv_score.py NOT edited (live-file constraint). "
            "Nothing committed."),
 "defect": {
  "statement": ("p_bust is served as vf.p_bucket_given_fv(xfv_grade, is_pitcher)[bust]. That "
                "curve is fitted over the Clemens published-list population and keyed on "
                "CONSENSUS FV; production reads it at xfv_grade = vf.realized_implied_fv(...), "
                "a different and much wider scale. A probability curve read at 2.4x its fitted "
                "dispersion returns log-odds that are far too steep."),
  "dispersion_ratio": {
   "sd_consensus_fv_raw": 6.57, "sd_xfv_grade": 15.54, "ratio": 2.37,
   "fitted_platt_slope_b": 0.3671, "implied_steepness_1_over_b": 2.72,
   "reading": ("the correction slope recovered from OUTCOMES independently reproduces the "
               "dispersion ratio measured from the two grade scales")},
  "bradfield": {"served_p_bust": 0.239, "xfv_grade": 50.9724, "consensus_fv": 45.6,
                "stratum_realized_bust_rate_shipped_band": 0.778, "stratum_n": 9}},
 "frame": {
  "definition": ("forward-chained out-of-fold replication of the served chain (per-fold ridge "
                 "-> linear calibration -> xfv_war -> realized_implied_fv -> p_bucket_given_fv), "
                 "decision years 2014-2020, fully resolved; served-comparable = has a MiLB "
                 "track record (milb dict present, rates_missing == 0)"),
  "n_served_comparable": 516, "n_pooled": 1926,
  "why_not_the_shipped_SCORED_YEARS": (
    "production forward-chains on 2020-2023, but 2021-2023 are CENSORED for every debuted row "
    "and resolve BUST-ONLY: 3 of the 4 shipped folds cannot test a probability at all (2021 "
    "resolved 3 debuted / 99 bust; 2022 0 / 247; 2023 2 / 285). Decision years 2014-2020 are "
    "the only years in which every row carries a closed 6-season window."),
  "bust_event": (
    "the SHIPPED band: 6-year AVERAGE annual WAR < 0.5 (summed first-6yr WAR < 3.0). NOTE the "
    "lane brief's 78.3% figure used SUMMED WAR < 0.5, a stricter and rarer event; under the "
    "shipped band the stratum bust rates are HIGHER, not lower.")},
 "reliability_incumbent_served_comparable": {
  "pooled": {"n": 516, "predicted": 0.5492, "observed": 0.6822,
             "ci95_observed": [0.6408, 0.7209], "gap": 0.1329},
  "by_predicted_bin": [
   {"bin": "0.00-0.09", "n": 64, "served": 0.0356, "observed": 0.2656, "ci95": [0.1730, 0.3848], "miscalibrated": True},
   {"bin": "0.09-0.22", "n": 65, "served": 0.1445, "observed": 0.5077, "ci95": [0.3892, 0.6254], "miscalibrated": True},
   {"bin": "0.22-0.38", "n": 64, "served": 0.3065, "observed": 0.6094, "ci95": [0.4869, 0.7194], "miscalibrated": True},
   {"bin": "0.38-0.50", "n": 65, "served": 0.4411, "observed": 0.7077, "ci95": [0.5880, 0.8042], "miscalibrated": True},
   {"bin": "0.50-0.74", "n": 64, "served": 0.6261, "observed": 0.7969, "ci95": [0.6829, 0.8773], "miscalibrated": True},
   {"bin": "0.75-0.95", "n": 65, "served": 0.8677, "observed": 0.8615, "ci95": [0.7573, 0.9254], "miscalibrated": False},
   {"bin": "0.96-0.98", "n": 64, "served": 0.9818, "observed": 0.8438, "ci95": [0.7357, 0.9129], "miscalibrated": True},
   {"bin": "0.98-0.99", "n": 65, "served": 0.9867, "observed": 0.8615, "ci95": [0.7573, 0.9254], "miscalibrated": True}],
  "by_efv_grade_band": [
   {"band": "20-35", "n": 172, "served": 0.9644, "observed": 0.8547, "gap": -0.1098, "miscalibrated": True},
   {"band": "35-40", "n": 31, "served": 0.7767, "observed": 0.8710, "gap": 0.0942, "miscalibrated": False},
   {"band": "40-45", "n": 53, "served": 0.6129, "observed": 0.7925, "gap": 0.1796, "miscalibrated": True},
   {"band": "45-50", "n": 103, "served": 0.4089, "observed": 0.6602, "gap": 0.2513, "miscalibrated": True},
   {"band": "50-55", "n": 49, "served": 0.2269, "observed": 0.6122, "gap": 0.3853, "miscalibrated": True},
   {"band": "55-80", "n": 107, "served": 0.0722, "observed": 0.3551, "gap": 0.2830, "miscalibrated": True}],
  "by_level": [
   {"level": "DSL", "n": 5, "served": 0.9047, "observed": 1.0, "miscalibrated": False},
   {"level": "CPX", "n": 16, "served": 0.6767, "observed": 1.0, "miscalibrated": True},
   {"level": "A", "n": 48, "served": 0.5458, "observed": 0.7708, "miscalibrated": True},
   {"level": "A+", "n": 85, "served": 0.5078, "observed": 0.7176, "miscalibrated": True},
   {"level": "AA", "n": 222, "served": 0.5353, "observed": 0.6622, "miscalibrated": True},
   {"level": "AAA", "n": 140, "served": 0.5704, "observed": 0.6143, "miscalibrated": False}],
  "by_age_band": [
   {"band": "age<=21", "n": 221, "served": 0.3888, "observed": 0.6018, "miscalibrated": True},
   {"band": "age 21-23.5", "n": 233, "served": 0.6300, "observed": 0.7167, "miscalibrated": True},
   {"band": "age>=23.5", "n": 62, "served": 0.8177, "observed": 0.8387, "miscalibrated": False}],
  "by_production_band": [
   {"band": "ops_rel<0", "n": 79, "served": 0.6095, "observed": 0.7215, "miscalibrated": True},
   {"band": "ops_rel>=0", "n": 165, "served": 0.3650, "observed": 0.5758, "miscalibrated": True}],
  "bradfield_stratum_and_neighbours": [
   {"cell": "AAA, age>=23.5, ops_rel<0", "n": 9, "served": 0.7267, "observed": 0.7778, "ci95": [0.4526, 0.9368], "miscalibrated": False},
   {"cell": "AAA, age>=23.5, ops_rel>=0", "n": 8, "served": 0.5555, "observed": 0.3750, "ci95": [0.1368, 0.6943], "miscalibrated": False},
   {"cell": "AAA, age<23.5, ops_rel<0", "n": 27, "served": 0.4883, "observed": 0.6296, "ci95": [0.4423, 0.7847], "miscalibrated": False},
   {"cell": "AAA, age<23.5, ops_rel>=0", "n": 31, "served": 0.2045, "observed": 0.3226, "ci95": [0.1857, 0.4986], "miscalibrated": False}],
  "headline_reading": (
    "the error is a GLOBAL over-sharpness, not a stratum surface. Bradfield's OWN cell is one "
    "of the few that is NOT miscalibrated: conditional on the grade he was given, his odds are "
    "fine. The 'factor of three' in the brief compares his p_bust (0.239, off grade 51) to a "
    "stratum rate realized by players the model historically graded ~33. That is the GRADE "
    "arriving in the odds, not an independent odds defect.")},
 "why": {
  "M1_conditioning": ("NULL. A level/age/production head is indistinguishable from its own "
                      "row-permuted twin and sits inside the label-permutation null band."),
  "M2_no_track_record_composition": (
    "NOT the driver. Gap is +0.1329 on rows WITH a track record and +0.1576 on rows without: "
    "essentially the same defect in both populations."),
  "M3_bust_bucket_pinned_at_zero_surplus": (
    "REAL but mis-assigned to this lane. 162 of 162 (100%) served-comparable rows with NEGATIVE "
    "first-6yr WAR already fall INSIDE the shipped bust band, so p_bust covers them. The "
    "'probability zero' defect lives in the SURPLUS FAN (bucket midpoint_war 0.0, "
    "surplus_floor_usd 0), not in p_bust."),
  "M4_scale_mismatch": (
    "CONFIRMED, and it is the mechanism. The curve is miscalibrated on BOTH keys in LEVEL "
    "(consensus read +0.1303, eFV read +0.1329) but only the eFV read carries a SLOPE error: by "
    "consensus band the gap is nearly flat (+0.165 / +0.133 / +0.110 / +0.062 / +0.169), while "
    "by eFV band it swings -0.079 -> +0.385. The level term is the known bustier-population "
    "effect; the slope term is new and is the dispersion mismatch.")},
 "gates": {
  "standard": ("docs/EFV_GATE_STANDARD.md. p_bust is a probability, so it is graded with PROPER "
               "SCORING RULES (Brier, log loss) plus a Murphy reliability/resolution "
               "decomposition, never with a rank metric."),
  "protocol": ("4 forward-chained time splits (2017-2020, each fitted strictly on "
               "decision_year < Y); paired bootstrap B=500 resampling TRAIN and TEST with a "
               "refit on every draw; a zero-information CONTROL that row-permutes the SAME "
               "covariate columns at identical degrees of freedom; a 300-draw label-permutation "
               "null band."),
  "point_estimates_served_comparable": g["point"],
  "conditional_head_VERDICT": "NULL",
  "conditional_head_evidence": {
   "R1_minus_R2_brier": g["deltas"]["R1-R2"]["brier"],
   "CTRL_minus_R2_brier": g["deltas"]["CTRL-R2"]["brier"],
   "R1_minus_CTRL_brier": g["deltas"]["R1-CTRL"]["brier"],
   "permutation_null": g["perm_null"],
   "reading": ("the conditional head does not beat the covariate-free recalibration "
               "(P(>0)=0.298), is indistinguishable from its permuted twin (P(>0)=0.654), and "
               "its gain sits inside the 95% permutation null band. The added columns are "
               "degrees-of-freedom cost, not information.")},
  "recalibration_VERDICT": "PASS on every proper score",
  "recalibration_evidence": {
   "note": "[mean, lo95, hi95, P(>0)]; positive means the INCUMBENT is worse",
   "INC_minus_recal_brier": [0.03953, 0.01655, 0.05934, 1.0],
   "INC_minus_recal_logloss": [0.15546, 0.07339, 0.22676, 0.994],
   "INC_minus_recal_reliability": [0.04297, 0.02149, 0.06125, 1.0],
   "resolution_under_one_global_transform": {
    "before": 0.03201, "after": 0.03201,
    "note": ("strictly monotone => resolution preserved EXACTLY and board order invariant. The "
             "small pooled drop (0.03201 -> 0.02839) in the fold-chained table is an artifact of "
             "pooling four DIFFERENT per-fold transforms, not a loss of sharpness.")},
   "reliability_under_one_global_transform": {"before": 0.05469, "after": 0.02627}},
  "incumbent_vs_a_constant_base_rate": {
   "brier": g["deltas"]["INC-CONST"]["brier"],
   "logloss": g["deltas"]["INC-CONST"]["logloss"],
   "reading": ("the served p_bust carries NO Brier skill over always printing the base rate "
               "(P(>0)=0.432) and is strictly WORSE than the base rate under log loss "
               "(P(>0)=0.942). Its resolution (0.032) is real but entirely consumed by its "
               "reliability error (0.055). The recalibration is what converts that resolution "
               "into skill.")},
  "level_vs_slope_decomposition": {
   "R0_level_only_the_CLOSED_line": {"brier": 0.19341, "logloss": 0.68900},
   "R1_level_plus_slope": {"brier": 0.18903, "logloss": 0.56536},
   "R0_minus_R1_brier": [0.00232, -0.01984, 0.01662, 0.658],
   "R0_minus_R1_logloss": [0.11178, 0.02068, 0.19575, 0.984],
   "reading": ("the SLOPE term is NOT captured by the population level shift that the "
               "2026-07-15 BUCKET-AGE-HEAD lane closed: it wins on log loss with a CI excluding "
               "zero. Brier is comparatively blind here because it barely punishes tail "
               "over-confidence; log loss does, and that is precisely the defect.")},
  "mean_preserving_variant_VERDICT": "FAIL -- measured, not assumed",
  "mean_preserving_variant_evidence": {
   "INC_minus_A_brier": [-0.00813, -0.03543, 0.01030, 0.250],
   "INC_minus_A_reliability": [-0.00363, -0.02928, 0.01570, 0.386],
   "reading": ("a slope-only correction that preserves the incumbent mean (which would have "
               "avoided the closed population-level term entirely) is WORSE than the incumbent. "
               "Compressing toward a wrong centre concentrates mass in the wrong place, so level "
               "and slope are not separable and the intercept must be carried.")}},
 "robustness": {
  "note": "positive delta = incumbent worse = the fix wins. [mean, lo95, hi95, P(>0)]",
  "shipped_bust_band_served": {"brier": [0.03862, 0.01504, 0.05909, 1.0],
                               "logloss": [0.15263, 0.05637, 0.23236, 0.995]},
  "lead_brief_definition_total_war_lt_0_5": {"brier": [0.01478, -0.00919, 0.04306, 0.853],
                                             "logloss": [0.13492, -0.21189, 0.28535, 0.895]},
  "alt_total_war_lt_1_0": {"brier": [0.01312, -0.01286, 0.03518, 0.865],
                           "logloss": [0.08791, -0.28174, 0.22755, 0.892]},
  "hitters_only": {"n": 200, "brier": [0.03358, -0.00049, 0.06825, 0.968],
                   "logloss": [0.12502, -0.02895, 0.25295, 0.955]},
  "pitchers_only": {"n": 233, "brier": [0.02345, -0.00110, 0.04828, 0.973],
                    "logloss": [0.07604, 0.00547, 0.14601, 0.980]},
  "pooled_incl_no_track_record": {"n": 1355, "brier": [0.04105, 0.03051, 0.05073, 1.0],
                                  "logloss": [0.11694, 0.08756, 0.14254, 1.0]},
  "honest_limits": [
   ("The win is specific to the SHIPPED bust event (6yr avg WAR < 0.5). Under the brief's "
    "stricter summed-WAR<0.5 event the sign holds but both CIs straddle zero. p_bust claims to "
    "predict the shipped event, so that is the event gated, but this must not be over-claimed "
    "as definition-free."),
   ("Neither side alone clears both metrics with a CI excluding zero (hitters Brier lo95 "
    "-0.00049, pitchers Brier lo95 -0.00110); the strong result needs both sides pooled. The "
    "per-side slopes are nonetheless within noise of each other (0.3749 vs 0.3553)."),
   ("TRAIN/SERVE DENSITY MISMATCH: the calibration frame has 132 of 516 rows at p_inc >= 0.95, "
    "whereas the LIVE board has 3231 of 4231 there. The correction is supported at the top (that "
    "bin realizes 0.86 against a served 0.987) but it is fitted where the mass is thinner than "
    "where it is applied."),
   ("The MiLB feature cache floors at 2014, so the served-comparable subpool is only 516 of 1926 "
    "resolved rows: the years with the best track-record coverage (2021+) are exactly the years "
    "whose debuted rows are still censored."),
   ("The forward-chained slope drifts DOWNWARD as the training window grows (0.470 / 0.392 / "
    "0.289 / 0.276). The shipped full-frame 0.3671 is the conservative end; a re-fit after the "
    "next resolution cycle will likely ask for MORE compression, not less.")]},
 "proposal": {
  "form": ("logit(p') = A + B*logit(p_bust), per side, applied ONLY where p_bust is read at the "
           "eFV realized-implied grade"),
  "constants": {"hit": [0.7268, 0.3749], "pit": [0.7269, 0.3553],
                "global_alternative": [0.7204, 0.3671]},
  "files": {"new_inert_module": "efv_odds_calibration.py",
            "exact_patch": "tools/_prem_odds.patch", "lab": "tools/_prem_odds*.py"},
  "scope_exclusions": [
   ("efv_ungraded PROVISIONAL rows -- the concurrent thin-sample lane "
    "(data/xfv_thin_pbust_eval.json) owns those and already replaces p_bust there; the patch "
    "carries a hard provisional= guard so the lanes compose instead of stacking."),
   ("p_bust read at a CONSENSUS FV grade (trade machine, /projections/, FA): on its native key "
    "the curve has a flat level gap and NO slope error, so this instrument is wrong there.")],
  "blast_radius": ("p_bust and p_bucket ONLY. xfv_grade, xfv_grade_display, rank_war and every "
                   "dollar figure are computed independently of the bucket vector, and the map is "
                   "strictly monotone, so no rank, grade, board slot or surplus value changes.")},
 "served_impact": {
  "in_scope_active_rows": 4231,
  "rows_moving_ge_0_10": 344, "share": 0.081, "direction": "344 increases, 0 decreases",
  "top_100_board_rows_moving_ge_0_10": 100,
  "median_move_all_in_scope": -0.073,
  "mean_p_bust": {"before": 0.9114, "after": 0.8681},
  "bradfield": {
   "p_bust_before": 0.239, "p_bust_after": 0.5726, "delta": 0.3336,
   "p_bucket_after": {"bust": 0.573, "bench": 0.125, "regular": 0.164, "good": 0.120, "star": 0.019},
   "note": ("his grade, board slot and surplus are UNCHANGED by this lane; only the odds move. "
            "0.573 still sits below his stratum's realized 0.778 because the residual gap is "
            "carried by the GRADE (51 against a cohort the model historically graded ~33), which "
            "is the grade lane's to answer.")}},
 "loss_ledger": {
  "date": "2026-07-25", "lane": "odds -- conditional p_bust surface",
  "hypothesis": ("p_bust is wrong CONDITIONAL on stratum (level x age x production), most "
                 "visibly for old, below-median, Triple-A hitters"),
  "verdict": "HYPOTHESIS REJECTED, DIFFERENT DEFECT FOUND AND GATED",
  "what_failed": [
   ("conditional head on level/age/production: indistinguishable from its row-permuted twin, "
    "inside the permutation null band"),
   ("mean-preserving slope-only correction: worse than the incumbent on Brier and on "
    "reliability")],
  "what_passed": [
   ("global monotone dispersion recalibration of p_bust at the eFV grade: Brier, log loss and "
    "reliability all improved with CI95 excluding zero; resolution preserved exactly")],
  "what_would_be_different": ("re-run after the 2021-2023 debut cohorts resolve; the "
                              "served-comparable frame roughly triples and the per-side gates "
                              "become independently powered.")}}

out = ROOT / "data" / "xfv_odds_dispersion_eval.json"
out.write_text(json.dumps(art, indent=1), encoding="utf-8")
print("wrote", out, len(json.dumps(art)), "bytes")
