import json
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent

g5 = json.loads((HERE / "gate5_report_pt_rule.json").read_text(encoding="utf-8"))
g5c = json.loads((HERE / "gate5_report.json").read_text(encoding="utf-8"))
g2 = json.loads((HERE / "gate2_variants.json").read_text(encoding="utf-8"))
new = json.loads((ROOT / "data/xfv_ungraded.json").read_text(encoding="utf-8"))
old = json.loads((ROOT / "data/xfv_ungraded.json.pbust-backup-20260725").read_text(encoding="utf-8"))
nb, ob = new["by_player"], old["by_player"]
ch = sorted(x for x in (nb[k]["p_bust"] - ob[k]["p_bust"] for k in nb) if abs(x) > 1e-9)
top = sorted(((nb[k]["p_bust"] - ob[k]["p_bust"], nb[k]["name"], nb[k]["xfv_grade"],
               nb[k]["level"], nb[k]["side"], ob[k]["p_bust"], nb[k]["p_bust"]) for k in nb),
             key=lambda t: -abs(t[0]))[:10]

out = {
    "generated_at": datetime.date.today().isoformat(),
    "model": "eFV provisional p_bust, thin-sample population conditional",
    "owner_authorization": (
        "amends the standing 'p_bucket / p_bust are NEVER touched' invariant to "
        "'NEVER touched EXCEPT by the thin-sample conditional'; scope is efv_ungraded "
        "provisional rows only"),
    "defect": {
        "statement": (
            "served p_bust came from vf.p_bucket_given_fv, a curve fitted on the Clemens "
            "published-list population (source-graded prospects with a pro track record) and "
            "keyed on the GRADE alone, then applied unchanged to a provisional grade fitted "
            "off as little as 80 plate appearances of DSL production"),
        "served_example": {"player": "an 87-PA DSL bat at provisional grade 44.9 (2026-07-25 build)",
                           "p_bust_before": 0.510, "p_bust_after": 0.884,
                           "p_bust_on_the_pre_cap_deployed_build": 0.201},
    },
    "population": {
        "definition": (
            "source-ungraded as of the cohort season, never MLB-exposed at or before it, "
            "primary-level exposure at or above the served grade floor (80 PA / 90 BF), "
            "primary level on the DSL..AAA ladder"),
        "cohort_seasons": [2015, 2016, 2017, 2018],
        "n_player_seasons": 19812,
        "why_these_seasons": (
            "8 to 11 seasons of realized outcome; 97.8% of eventual DSL/CPX debuts occur within "
            "8 seasons of the cohort season (measured on this cohort). The MiLB feature cache "
            "floors at 2014, which caps the earliest usable cohort at 2015"),
        "sensitivity_2019": "same sign and a larger gap on the still-censored 2019 cohort",
    },
    "label": {
        "bust": "first-6-MLB-season summed bWAR < 3.0 (Clemens bucket 0, under 0.5 WAR/season)",
        "never_reached_mlb": "bust with certainty, no WAR join needed",
        "unknown_rows": (
            "reached MLB but absent from career_war. PRIMARY rule: bust when first-6-season MLB "
            "PA/BF is under 300. VALIDATED not assumed: of 1,144 cohort rows with a KNOWN "
            "first-6yr WAR, 0 of the 487 under 300 PA/BF reached 3.0 WAR (highest 1.58; still 0 "
            "of 639 at a 500 threshold). Unknowns at or above 300 PA/BF stay labelled NON-bust "
            "although 63.9% of the KNOWN rows above 300 are busts, so the fitted curve is a "
            "LOWER bound on the true bust rate"),
        "bracketing_variants_all_pass": ["all unknowns non-bust", "all unknowns bust"],
    },
    "historical_hit_rate_with_n": {
        "ungraded DSL hitters, provisional grade >= 35": {"n": 87, "observed_bust": 0.881},
        "ungraded DSL pitchers, provisional grade >= 35": {"n": 314, "observed_bust": 0.990},
        "ungraded DSL hitters, all grades": {"n": 2236, "observed_bust": 0.992},
        "ungraded DSL pitchers, all grades": {"n": 2167, "observed_bust": 0.992},
        "grade >= 35 pooled, observed vs served": g5["sensitivity"],
    },
    "gates": {
        "standard": "docs/EFV_GATE_STANDARD.md",
        "protocol": (
            "B = 400 paired bootstrap draws resampling the TRAIN matrix AND the TEST cohort, "
            "refitting the provisional ridge on every draw; leave-one-cohort-year-out folds over "
            "4 independent cohort years"),
        "G1_defect_grade_ge35": g5["g1_gap_emp_minus_incumbent_grade_ge35"],
        "G2_G3_logloss": g5["logloss"],
        "G2_G3_brier": g5["brier"],
        "deltas_positive_means_first_is_worse": g5["deltas_logloss_positive_means_first_is_worse"],
        "G4_label_permutation_null": g5["label_permutation_null_constant_minus_headD"],
        "G5_monotone_in_grade_within_level": True,
        "verdict": "ALL PASS",
    },
    "head": g5["head_point_fit"],
    "oof_calibration": g5["oof_calibration"],
    "conservative_label_run": {
        "note": "the same battery under the strictly-conservative labeling (every unknown a NON-bust)",
        "G1": g5c["g1_gap_emp_minus_incumbent_grade_ge35"],
        "deltas": g5c["deltas_logloss_positive_means_first_is_worse"],
    },
    "rejected_variants": {
        "linear level_rank term (head B)": (
            "beat the incumbent out of fold but is misspecified: the realized level-to-bust "
            "relation is NOT monotone (ungraded AAA is org filler and busts more than ungraded "
            "AA), so a linear term forces AAA below AA exactly where it moves served numbers "
            "most. Rejected in favour of categorical levels"),
        "grade-only (head A)": {
            "oof_logloss_vs_headD": g5["deltas_logloss_positive_means_first_is_worse"]["headA - headD"],
            "note": "real but dominated; level carries information the grade does not"},
        "covariate-free population offset (constant)": (
            "a measured NULL against the incumbent (+0.0015 CI95 [-0.0046, 0.0079], P = 0.695). "
            "This is the ablation that killed BUCKET-AGE-HEAD; here it fails, so none of the "
            "gain is population recalibration"),
        "grade-clipping variants C36..C44": g2,
    },
    "served_blast_radius": {
        "artifact": "data/xfv_ungraded.json",
        "cards_total": len(nb),
        "cards_with_p_bust_changed": len(ch),
        "raised": sum(1 for x in ch if x > 0),
        "lowered": sum(1 for x in ch if x < 0),
        "delta_quantiles": {str(q): round(ch[int(q * (len(ch) - 1))], 3)
                            for q in (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)},
        "count_by_magnitude": {f">={t}": sum(1 for x in ch if abs(x) >= t)
                               for t in (0.02, 0.05, 0.10, 0.20, 0.30)},
        "largest_moves": [{"name": n, "side": s, "level": l, "grade": g, "before": o,
                           "after": nn, "delta": round(dd, 3)}
                          for dd, n, g, l, s, o, nn in top],
        "unchanged_elsewhere": "xfv_grade and surplus_mm are byte-identical on all 3,419 rows",
        "served_clamp": {
            "range": [0.02, 0.99],
            "rows_at_ceiling": sum(1 for v in nb.values() if abs(v["p_bust"] - 0.99) < 1e-9),
            "why": ("the card rounds to whole percent, so a value at or above 0.995 would print "
                    "P(bust) 100% and claim a certainty no model has. 0.99 also sits BELOW the "
                    "measured DSL cell rate (0.992 on both sides, n = 2,236 / 2,167), so the "
                    "clamp can only make a served row look SAFER than the cohort was"),
        },
        "consumers": ("storage._load_ungraded_by_org reads only xfv_grade, so farm depth / "
                      "top-end pools are unaffected. New row fields p_bust_basis and "
                      "p_bust_low_confidence are available for the product surfaces"),
    },
    "limits": [
        "serves p_bust and p_bucket only; surplus dollars stay on the engine grade-anchored path",
        ("hitter 45+ band still under-called out of fold (0.743 against 0.813 observed, n = 107); "
         "the provisional maximum is " + str(new["meta"]["grade_dist"]["max"]) + " on the "
         + str(new["meta"]["generated_at"]) + " build read here (data/xfv_ungraded.json "
         "meta.grade_dist.max), so check how full that band is before relying on this"),
        ("MiLB feature history floors at 2014, so early cohort rows see 1 to 2 prior seasons; that "
         "matters for n_milb_seasons at the upper levels, not for the 17-to-19-year-old DSL/CPX "
         "population the defect lives in"),
        ("the provisional ridge is fitted on the full labeled matrix rather than forward-chained "
         "(decision_year < cohort year leaves n = 3 to 163 rows). The bias direction is "
         "conservative against the claim: label leakage makes the grade look MORE discriminating, "
         "so the residual bust rate measured at high grades is an understatement"),
        ("rows whose level does not resolve to the ladder keep the incumbent odds and are flagged "
         "p_bust_low_confidence; 0 such rows in the current build"),
    ],
    "lab": "tools/pbust_thin/ (cohort.py, score.py, gate.py, gate2.py, gate3.py, gate5.py)",
}
p = ROOT / "data/xfv_thin_pbust_eval.json"
p.write_text(json.dumps(out, indent=1), encoding="utf-8")
print("wrote", p, p.stat().st_size)
