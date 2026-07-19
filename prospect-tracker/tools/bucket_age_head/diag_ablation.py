# POST-HOC DIAGNOSTIC (not a gate): grade-band-only ablation.
# Isolates how much of the age-head's pooled log-loss gain is the AGE covariate
# vs the population-level recalibration (the resolved matrix pool is far
# bustier than the incumbent's Clemens population). Same partial pooling
# (n/(n+25)), same folds, cells keyed by grade band ONLY (all rows, age not
# required). Appends a diagnostics block to results.json.
from __future__ import annotations

import json
from collections import defaultdict

import numpy as np

import gate_lab as gl


def fit_grade_only(train):
    cells = defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in train:
        cells[r["grade_band"]][r["y"]] += 1
    return {k: list(v) for k, v in cells.items()}


def grade_only_prob(cells, fv):
    inc = gl.incumbent(fv)
    cnt = cells.get(gl.tier(fv))
    if not cnt:
        return inc
    n = float(sum(cnt))
    if n <= 0:
        return inc
    w = n / (n + gl.SHRINK_N)
    emp = np.asarray(cnt, dtype=float) / n
    p = w * emp + (1.0 - w) * inc
    s = p.sum()
    return p / s if s > 0 else inc


def main():
    pool = gl.load_pool()
    rows = []
    for yr in gl.EVAL_YEARS:
        tr = [r for r in pool if r["decision_year"] < yr]
        te = [r for r in pool if r["decision_year"] == yr]
        if len(te) < gl.MIN_TEST or len(tr) < gl.MIN_TRAIN:
            continue
        cells_age = gl.fit_head(tr)
        cells_g = fit_grade_only(tr)
        for r in te:
            rr = dict(r)
            rr["p_head"] = gl.head_prob(cells_age, r["fv"], r["age"]).tolist()
            rr["p_gonly"] = grade_only_prob(cells_g, r["fv"]).tolist()
            rr["p_inc"] = gl.incumbent(r["fv"]).tolist()
            rows.append(rr)

    def ll(key, sub):
        P = np.array([r[key] for r in sub])
        Y = np.array([r["y"] for r in sub])
        return round(gl.ll_pooled(P, Y), 5)

    sub25 = [r for r in rows if r["age_band"] == "25p"]
    known = [r for r in rows if r["age_band"] is not None]
    diag = {
        "label": "POST-HOC DIAGNOSTIC (recorded after the gate ran; NOT a gate condition)",
        "question": "how much of the age-head gain is the age covariate vs population-level "
                    "recalibration of the incumbent to the (bustier) resolved matrix pool?",
        "method": "grade-band-only head, identical partial pooling n/(n+25), identical folds; "
                  "pooled multiclass log-loss on the same 524 eval rows",
        "pooled_log_loss": {
            "incumbent": ll("p_inc", rows),
            "grade_band_only_head": ll("p_gonly", rows),
            "age_head": ll("p_head", rows),
        },
        "age_25p_subset_log_loss": {
            "incumbent": ll("p_inc", sub25),
            "grade_band_only_head": ll("p_gonly", sub25),
            "age_head": ll("p_head", sub25),
        },
        "age_known_subset_log_loss": {
            "incumbent": ll("p_inc", known),
            "grade_band_only_head": ll("p_gonly", known),
            "age_head": ll("p_head", known),
        },
    }
    p = diag["pooled_log_loss"]
    diag["decomposition"] = {
        "total_gain": round(p["incumbent"] - p["age_head"], 5),
        "population_recalibration_share": round(p["incumbent"] - p["grade_band_only_head"], 5),
        "age_covariate_increment"        : round(p["grade_band_only_head"] - p["age_head"], 5),
    }

    res_path = gl.OUT
    results = json.loads(res_path.read_text(encoding="utf-8"))
    results["diagnostics_post_hoc"] = diag
    res_path.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(diag, indent=1))


if __name__ == "__main__":
    main()
