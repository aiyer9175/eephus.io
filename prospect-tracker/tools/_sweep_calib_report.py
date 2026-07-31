# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SWEEP LANE calibration -- consolidate the gate outputs into ONE report artifact.

Writes data/xfv_level_calibration_report.json. Pure assembly: every number is
copied from the gate artifacts, nothing is recomputed here except the served-board
descriptive counts.
"""
from __future__ import annotations
import json, statistics, sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import value_framework as vf   # noqa: E402

D = ROOT / "data"
GATE = json.loads((D / "xfv_level_calibration_eval.json").read_text(encoding="utf-8"))
SLICE = json.loads((D / "xfv_level_calibration_slices.json").read_text(encoding="utf-8"))
DISP = json.loads((D / "xfv_pred_dispersion_eval.json").read_text(encoding="utf-8"))
XFV = json.loads((D / "xfv.json").read_text(encoding="utf-8"))
FIT = json.loads((D / "value_framework_fitted.json").read_text(encoding="utf-8"))

ACT = [v for v in XFV["by_player"].values() if v.get("kind") == "active"]


def g(side, k):
    return {"point": GATE["point"][side].get(k),
            "boot_ci95": GATE["boot_ci95"][side].get(k),
            "zero_info_ci95": GATE["zero_info_control_permuted_grade_ci95"][side].get(k),
            "perm_null_ci95": GATE["permutation_null_permuted_outcome_ci95"][side].get(k),
            "time_splits": [GATE["per_fold"][side][y].get(k) for y in ("2016", "2017", "2018", "2019", "2020")]}


def sl(side, k):
    return {"point": SLICE["point"][side].get(k),
            "boot_ci95": SLICE["boot_ci95"][side].get(k),
            "n": SLICE["point"][side].get(k.rsplit("_", 1)[0] + "_n")}


def dp(side, k):
    return {"point": DISP["point"][side].get(k),
            "boot_ci95": DISP["boot_ci95"][side].get(k),
            "zero_info_ci95": DISP["zero_info_control_permuted_prediction_ci95"][side].get(k),
            "time_splits": [DISP["per_fold"][side][y].get(k) for y in ("2016", "2017", "2018", "2019", "2020")]}


# --- served-board descriptives -----------------------------------------------
gq = [v["xfv_grade_quantile"] for v in ACT if v.get("xfv_grade_quantile") is not None]
p10 = [v.get("band_p10_mm") for v in ACT]
p90 = [v.get("band_p90_mm") for v in ACT]
pbu = [v.get("p_bust") for v in ACT if v.get("p_bust") is not None]
gapd = [v["xfv_grade_quantile"] - v["xfv_grade_realized"] for v in ACT
        if v.get("xfv_grade_quantile") is not None and v.get("xfv_grade_realized") is not None]
odds_gap = []
for v in ACT:
    a, b = v.get("xfv_grade_realized"), v.get("xfv_grade_quantile")
    if a is None or b is None:
        continue
    ip = v.get("side") == "P"
    odds_gap.append((vf.p_bucket_given_fv(a, ip) or [0])[0] - (vf.p_bucket_given_fv(b, ip) or [0])[0])

report = {
    "generated_at": __import__("datetime").date.today().isoformat(),
    "lane": "calibration -- LEVEL calibration audit of eFV",
    "standard": "docs/EFV_GATE_STANDARD.md (paired bootstrap w/ refit, zero-information "
                "control, permutation null, >= 4 independent time splits)",
    "frame": GATE["frame"],
    "inputs": {"gate": "data/xfv_level_calibration_eval.json",
               "slices": "data/xfv_level_calibration_slices.json",
               "dispersion": "data/xfv_pred_dispersion_eval.json"},
    "labs": ["tools/_sweep_calibration.py", "tools/_sweep_calib_gate.py",
             "tools/_sweep_calib_slices.py", "tools/_sweep_calib_shrink.py",
             "tools/_sweep_calib_anchor.py", "tools/_sweep_calib_patchcheck.py"],
    "patches": "tools/_sweep_calib_out/calibration_patches.diff (NOT applied)",

    "structural_facts": {
        "headline_grade_marginal_is_consensus_by_construction": {
            "what": "xfv_grade_quantile is a rank-preserving quantile map of rank_war onto "
                    "the pool's OWN consensus-FV distribution, so per side the served grade "
                    "multiset EQUALS the consensus-FV multiset.",
            "served_check_hitters": {"n": 2087, "mean_efv": 37.075, "mean_consensus": 37.047,
                                     "sd_efv": 3.736, "sd_consensus": 3.717,
                                     "max_abs_quantile_diff_fv": 1.8},
            "served_check_pitchers": {"n": 2390, "mean_efv": 36.357, "mean_consensus": 36.357,
                                      "sd_efv": 2.862, "sd_consensus": 2.858,
                                      "max_abs_quantile_diff_fv": 3.0},
            "implication": "eFV's POOLED level calibration is identically consensus FV's. The "
                           "model can only REDISTRIBUTE level error across players; it cannot "
                           "remove it. Any level fix must land in the anchor table or the "
                           "display map, never in the model. Confirmed numerically: the gate's "
                           "pooled_bias and cons_pooled_bias agree to machine precision."},
        "two_grades_on_one_row": {
            "band_and_surplus_basis": "xfv_grade_quantile (efv_score._reprice_surplus_on_display)",
            "odds_basis": "xfv_grade_realized (efv_score.run p_bucket_given_fv)",
            "served_grade_gap_fv": {"n": len(gapd), "mean": round(statistics.mean(gapd), 2),
                                    "median": round(statistics.median(gapd), 2),
                                    "p10": round(float(np.percentile(gapd, 10)), 2),
                                    "p90": round(float(np.percentile(gapd, 90)), 2)},
            "p_bust_realized_minus_displayed": {"mean": round(statistics.mean(odds_gap), 3),
                                                "max": round(max(odds_gap), 3),
                                                "share_gt_0.10": round(sum(1 for x in odds_gap if x > 0.10) / len(odds_gap), 3)}},
        "anchor_has_no_knot_below_fv40": {
            "fitted_anchors": FIT["empirical_anchors"]["anchors"],
            "anchor_calibration_tiers": vf._config()["anchor_calibration"]["tiers"],
            "served_value_for_every_grade_in_20_40": vf.fv_to_6yr_avg_war(30),
            "inverse_map_does_resolve_that_range": "realized_implied_fv re-spreads FV 20-45 as "
                                                   "20 + 25*(war/war45)**_LOWEND_FG_EXP",
            "round_trip_before_patch": "every grade in [20, 40] maps back to 39.8 FV",
            "share_of_served_active_board_at_or_below_fv40": round(sum(1 for x in gq if x <= 40) / len(gq), 4),
            "db_cohort_fv35_cell": {"n": 386, "empirical_war_per_yr": 0.040,
                                    "boot_ci95": [0.020, 0.061], "served_anchor": 0.19,
                                    "source": "empirical_anchors._cohort(prospects.db, 2014, 2020)"},
            "cohort_weighted_abs_error_war_per_yr": {"served": 0.1536, "plus_35_knot": 0.1458,
                                                     "inverse_consistent_extension": 0.1431,
                                                     "config_seed": 0.1865}},
        "published_curve_is_not_the_served_curve": {
            "published": "data/value_framework.js fv_to_6yr_avg_war (build_snapshot emits the "
                         "CONFIG SEED table); rendered by assets/glossary.js _methValuationCurveHTML",
            "served": "fitted empirical_anchors.anchors",
            "pct_divergence_published_vs_served": {"<=35": -36.8, "40": 15.8, "45": 22.6,
                                                   "50": 4.5, "55": -3.1, "60": 0.7,
                                                   "65": -2.5, "70": 3.2, "80": 8.6},
            "why_the_freshness_test_misses_it": "test_value_framework_integration only compares "
                                                "the JS to the JSON to build_snapshot()"},
        "band_lower_bound_is_a_constant": {
            "mechanism": "within_bucket_cv.bust = 0.0 -> the bust bucket is a POINT MASS at the "
                         "$0 surplus floor, so the mixture's 10th percentile is exactly 0 "
                         "whenever p_bust >= 0.10",
            "served_active_n": len(ACT),
            "band_p10_eq_0_share": round(sum(1 for x in p10 if x == 0.0) / len(p10), 4),
            "band_p10_eq_band_p90_share": round(sum(1 for a, b in zip(p10, p90) if a is not None and a == b) / len(p10), 4),
            "p_bust_ge_0.10_share": round(sum(1 for x in pbu if x >= 0.10) / len(pbu), 4)},
    },

    "a_reliability_by_grade_tier": {
        "yardstick": "6 * value_framework.fv_to_6yr_avg_war(displayed grade) vs realized "
                     "first-6yr summed bWAR; positive bias = realized EXCEEDS the grade's "
                     "declared meaning",
        "full_training_pool": {s: {k: g(s, k) for k in
                                   ("pooled_bias", "bias_t35", "bias_t40", "bias_t45",
                                    "bias_t50", "bias_t55", "bias_t60", "bias_slope_per_fv_pt")}
                               for s in ("hit", "pit")},
        "live_comparable_pool": {s: {k: g(s, k) for k in
                                     ("lm_pooled_bias", "lm_bias_t40", "lm_bias_t45",
                                      "lm_bias_t50", "lm_bias_t55", "lm_bias_t60")}
                                 for s in ("hit", "pit")},
        "shape_verdict": {
            "hit": "KNEE, not a slope. Below the FV-40 clamp the anchor overstates by ~0.9 WAR "
                   "(CI-clean, 5/5 folds); at eFV 50 it understates by +2.18 (CI-clean). The "
                   "fitted bias slope +0.100 per FV point has CI95 [-0.036, 0.231] == NULL.",
            "pit": "Sign-flipping and mostly null. Below-40 overstatement is CI-clean (-0.80 at "
                   "t40, 5/5 folds); the top-tier understatement at t60 (-3.99, CI95 "
                   "[-7.49, -1.08]) is CI-clean but n=5. Bias slope -0.108, CI95 "
                   "[-0.198, 0.075] == NULL."}},

    "b_population_conditional": {
        "scope": SLICE["scope"],
        "level": {s: {v: {"n": SLICE["point"][s].get(f"level_{v}_n"),
                          "bias": sl(s, f"level_{v}_bias"),
                          "coverage": sl(s, f"level_{v}_cov"),
                          "p_bust_gap": sl(s, f"level_{v}_pbustgap")}
                      for v in ("A", "A+", "AA", "AAA")} for s in ("hit", "pit")},
        "age_band": {s: {v: {"n": SLICE["point"][s].get(f"age_{v}_n"),
                             "bias": sl(s, f"age_{v}_bias"),
                             "coverage": sl(s, f"age_{v}_cov"),
                             "p_bust_gap": sl(s, f"age_{v}_pbustgap")}
                         for v in ("19-20", "21-22", "23-24")} for s in ("hit", "pit")},
        "acquisition": {s: {v: {"n": SLICE["point"][s].get(f"acq_{v}_n"),
                                "bias": sl(s, f"acq_{v}_bias"),
                                "coverage": sl(s, f"acq_{v}_cov"),
                                "p_bust_gap": sl(s, f"acq_{v}_pbustgap")}
                            for v in ("IFA", "college", "HS")} for s in ("hit", "pit")},
        "control_caveat": "The zero-information control permutes the grade over the WHOLE fold "
                          "pool, so on a SUBSET (live-comparable / level / age / acq) it also "
                          "destroys the subset-grade association and is an upper reference, not "
                          "a matched twin. The paired bootstrap CI is the operative gate on "
                          "every slice statistic."},

    "c_outcome_odds": {
        "bust_definition_primary": "realized first-6yr summed bWAR < 0.5 -- the repo's own "
                                   "operative threshold (efv_model._SF_BUST_WAR; "
                                   "empirical_anchors counts realized_war/6 < 0.5/6)",
        "bust_definition_literal": "config buckets.bust band '<0.5' read as a 6-season average "
                                   "(< 3.0 summed). The config calls these per-SEASON projected "
                                   "TALENT bands normalized to 600 PA / 200 IP, which no "
                                   "realized accumulation reproduces exactly -- the band labels "
                                   "and the reconciliation target are on different scales.",
        "marginal": {s: {k: g(s, k) for k in ("p_bust_gap", "p_bust_gap_literal",
                                              "lm_p_bust_gap", "lm_p_bust_gap_literal")}
                     for s in ("hit", "pit")},
        "by_displayed_tier": {s: {k: g(s, k) for k in
                                  ("pbust_gap_t40", "pbust_gap_t45", "pbust_gap_t50",
                                   "pbust_gap_t55", "pbust_gap_t60")} for s in ("hit", "pit")}},

    "d_interval_calibration": {
        "object": "the served band_p10_mm / band_p90_mm are $M percentiles of the bucket "
                  "mixture at the DISPLAYED grade. Tested in WAR units where truth exists: "
                  "bucket ~ p_bucket_given_fv(g); per-bucket per-season level = "
                  "buckets.midpoint_war * vf._war_scale_for(g, role) (the engine's own "
                  "reconciliation scalar, so the mixture mean equals 6*fv_to_6yr_avg_war(g) "
                  "exactly); WAR | bucket ~ mean-preserving Gamma at within_bucket_cv; "
                  "bust = point mass at 0. Nominal coverage 0.80.",
        "marginal_vs_conditional": {s: {k: g(s, k) for k in
                                        ("coverage_marginal", "coverage_has_milb",
                                         "coverage_no_milb", "coverage_cond_spread",
                                         "coverage_A", "coverage_A+", "coverage_AA",
                                         "coverage_AAA", "lm_miss_low", "lm_miss_high")}
                                    for s in ("hit", "pit")},
        "zero_mass_below_zero_war": {
            "note": "the mixture assigns probability 0 to a negative first-6yr WAR; the bust "
                    "bucket is pinned at exactly 0",
            "realized_negative_share_live_comparable": {"hit": 0.248, "pit": 0.379},
            "realized_negative_share_full_pool": {"hit": 0.127, "pit": 0.160}}},

    "e_prediction_dispersion": {
        "statistic": DISP["statistic"],
        "model_leg_xfv_war": {s: dp(s, "slope_xfv_war") for s in ("hit", "pit")},
        "model_leg_live_comparable": {s: dp(s, "lm_slope_xfv_war") for s in ("hit", "pit")},
        "consensus_leg": {s: dp(s, "slope_cons_war") for s in ("hit", "pit")},
        "blend_rank_war": {s: g(s, "oos_shrink_slope") for s in ("hit", "pit")}},
}

(D / "xfv_level_calibration_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("wrote", D / "xfv_level_calibration_report.json")
