# Finalize results.json: honest decomposition labels + notes + emit the
# production head artifact (patched/data/xfv_bucket_age_head.json).
from __future__ import annotations

import json
from datetime import date

import gate_lab as gl


def main():
    results = json.loads(gl.OUT.read_text(encoding="utf-8"))

    # --- relabel the ablation decomposition honestly (coverage/shrink confound) ---
    diag = results["diagnostics_post_hoc"]
    p = diag["pooled_log_loss"]
    k = diag["age_known_subset_log_loss"]
    diag["decomposition"] = {
        "age_head_gain_vs_incumbent": round(p["incumbent"] - p["age_head"], 5),
        "grade_band_only_gain_vs_incumbent": round(p["incumbent"] - p["grade_band_only_head"], 5),
        "age_head_minus_grade_band_only_positive_is_worse":
            round(p["age_head"] - p["grade_band_only_head"], 5),
        "age_known_subset_age_head_minus_grade_band_only":
            round(k["age_head"] - k["grade_band_only_head"], 5),
        "caveat": "NOT a clean age-signal estimate: the age head covers only the 40% "
                  "age-known rows (incumbent fallback elsewhere) and its smaller cells "
                  "carry much heavier n/(n+25) shrink toward the population-miscalibrated "
                  "incumbent than the large grade-band cells; a hierarchical variant "
                  "(age cells shrunk toward the GRADE-BAND empirical rather than the "
                  "incumbent) was NOT pre-registered and was not gated here",
    }
    diag["reading"] = (
        "the registered age head is DOMINATED by its own covariate-free ablation on the "
        "identical eval rows (pooled 0.30733 vs 0.17907; age-known subset 0.33450 vs "
        "0.26921; 25+ subset 0.28004 vs 0.21162). The G1/G3 passes are therefore driven "
        "by population-level recalibration of the incumbent to the bustier resolved pool "
        "- the effect class the CLOSED grade-monotone calibration line (X-ISO/E-ISO2/3/4) "
        "already established as blocked - not by age information."
    )

    # --- honest context notes -------------------------------------------------
    results["notes"] = {
        "population_mismatch": "the incumbent p_bucket table is calibrated on the Clemens "
                               "published-list population; the resolved matrix pool (busts from "
                               "inactive.json included) is far bustier (fv45 pit band pooled "
                               "empirical bust ~0.87 vs incumbent 0.51 at fv45), so ANY "
                               "recalibration toward this pool posts large in-population "
                               "log-loss gains regardless of covariate",
        "g2_population_caveat": "G2 (bench/good) passing here does NOT contradict the E-ISO4 "
                                "pit-BENCH blocker: that line evaluated the KM full pool "
                                "(target_censored, censored rows carried with weights); this "
                                "pre-registration fixed the RESOLVED-only frame, where realized "
                                "bench/good frequencies are lower and cutting bench/good mass "
                                "is rewarded",
        "fold_composition": "resolved-only framing makes the 2021-2023 eval folds bust-only "
                            "(debut cohorts 2021+ are censored until they resolve); only the "
                            "2020 fold (n=204, 104 debuted / 100 busts) tests non-bust "
                            "discrimination",
        "moore_motivation_check": "the registered motivation numbers do NOT reproduce under "
                                  "the lab conventions: the fv45/25+ cell is n=8 with empirical "
                                  "p_bust 0.750 (claim: 0.81), and mean realized WAR6 RISES "
                                  "with age inside fv45 (0.51/1.70/2.51 across bands) - the "
                                  "within-band age-bust gradient lives at fv40 (25+ bust 0.988, "
                                  "n=81), not at Moore's band; incumbent p_bust(48.0)=0.388 "
                                  "ties the published figure to his pre-overlay grade ~48 "
                                  "(current live grade 45.8 -> incumbent 0.476)",
        "age_missingness": "age is recoverable for only 623/1569 resolved rows and missingness "
                           "correlates with the outcome (busts are 72% of age-missing rows vs "
                           "58% of age-known): the head's serve population (live rows, age "
                           "always present) is NOT the fit population - an additional unpriced "
                           "train/serve mismatch",
    }

    v = results["gate"]["verdict"]
    results["loss_ledger"] = None
    if v != "PASS":
        results["loss_ledger"] = {
            "date": date.today().isoformat(),
            "experiment": "BUCKET-AGE-HEAD: pit-only p(bucket | grade_band, age_band) below "
                          "the grade-monotone constraint (partial pooling n/(n+25) toward the "
                          "incumbent row); the recorded-open covariate path after the "
                          "grade-monotone calibration line was CLOSED",
            "hypothesis": "within grade bands, age carries real outcome signal (the Moore "
                          "case: published p_bust 0.388 vs claimed band-empirical 0.81), so an "
                          "age-banded bucket head improves calibration without touching the "
                          "grade-only incumbent or its five non-eFV consumers",
            "result": {
                "verdict": "FAIL (G4: grade monotone-sanity)",
                "g1_pooled_ll": "PASS 0.36184 -> 0.30733 (delta -0.05451, CI90 "
                                "[-0.06153, -0.04730], P(delta<=0)=1.0)",
                "g2_bench_good": "PASS bench -11.2% rel / good -17.0% rel (guard was <=+1.0%)",
                "g3_age25p_ll": "PASS 0.36661 -> 0.28004 (delta -0.08657, CI90 "
                                "[-0.09935, -0.07349])",
                "g4_monotone": "FAIL: 12 band-seam stochastic-ordering violations across all "
                               "three age bands; worst +0.07621 P(bust) jump crossing INTO the "
                               "fv35 band at 32.5/32.75 (all-bust empirical cells vs incumbent "
                               "fallback below support); further seams at 37.5, 47.5, 52.75, "
                               "62.75, 67.5, 72.75 (thin n=1-8 cells)",
            },
            "diagnosis": "two independent kill mechanisms: (1) the piecewise (grade_band x "
                         "age_band) cell structure cannot preserve grade stochastic ordering "
                         "at band seams when cell empiricals sit far from the incumbent curve "
                         "- the head does NOT stay 'below the grade-monotone constraint' as "
                         "designed; (2) the post-hoc ablation shows the registered head is "
                         "dominated by a covariate-free grade-band recalibration on the same "
                         "rows, so the G1/G3 gains are population recalibration (the CLOSED "
                         "line), not age signal",
            "what_would_be_different": "a hierarchical head (age cells shrunk toward the "
                                       "grade-band EMPIRICAL, itself monotone-repaired across "
                                       "bands, e.g. isotonic in grade per age band) plus a "
                                       "serve-population-matched fit frame; requires fresh "
                                       "pre-registration and should wait for the S5 tripwire "
                                       "(2024 debuted cohorts resolving) when the Moore-class "
                                       "RP cohort becomes gateable",
            "disposition": "NO SHIP. Incumbent p_bucket_given_fv untouched in production; "
                           "candidate implementation preserved in patched/ for the re-run; "
                           "re-attempt only under the rerun_marker trigger with a redesigned "
                           "shrink target",
        }

    gl.OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("results.json finalized; verdict:", v)

    # --- production head artifact ----------------------------------------------
    pool = gl.load_pool()
    cells = gl.fit_head(pool)
    head = {
        "generated_at": date.today().isoformat(),
        "model": "BUCKET-AGE-HEAD (pit-only p(bucket | grade_band, age_band))",
        "status": "CANDIDATE - FAILED its pre-registered gate (G4 grade monotone-sanity); "
                  "DO NOT SHIP without a gate PASS under the rerun marker",
        "seed": gl.SEED,
        "shrink_n": gl.SHRINK_N,
        "age_bands": {"le22": "age < 23", "23_24": "23 <= age < 25", "25p": "age >= 25"},
        "grade_band_convention": "int(round(fv/5)*5) (efv_isotonic_lab._tier)",
        "buckets": list(gl.BUCKETS),
        "fit_population": "resolved labeled pitcher matrix, debuted+busts, bust_recent "
                          "excluded, censored==False (n=%d)" % len(pool),
        "cells": {f"{gb}|{ab}": {"n": int(sum(c)), "counts": [int(x) for x in c]}
                  for (gb, ab), c in sorted(cells.items())},
        "rerun_marker": json.loads(gl.OUT.read_text(encoding="utf-8"))["rerun_marker"],
    }
    gl.HEAD_JSON.parent.mkdir(parents=True, exist_ok=True)
    gl.HEAD_JSON.write_text(json.dumps(head, indent=1), encoding="utf-8")
    print("wrote", gl.HEAD_JSON)


if __name__ == "__main__":
    main()
