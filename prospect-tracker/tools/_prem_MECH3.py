"""MECHANISM lane part 3: Shapley attribution (in FV points) of the +12.15 premium
swing between Bradfield and his own historical stratum, plus counterfactuals.
Read-only.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                                  # noqa: E402
import value_framework as vf                                        # noqa: E402
import efv_model as em                                              # noqa: E402
import efv_score as es                                              # noqa: E402
from prospect_path import _predict                                  # noqa: E402

DATA = ROOT / "data"
GM_AGE = 31.1          # Bradfield's grade-map age placement


def grade_of(war, gm_age=GM_AGE):
    return vf.realized_implied_fv(war, False, age=gm_age, position="CF",
                                  exposure_seasons=es.TARGET_SEASONS)


def main():
    side = "hit"
    ridge, a, b, ols, _k = es._fit_production(side)

    matrix = json.loads((DATA / "xfv_hitter_matrix.json").read_text(encoding="utf-8"))
    scored = {s["player_key"]: s for s in
              json.loads((DATA / "xfv_scored.json").read_text(encoding="utf-8"))}
    live = json.loads((DATA / "xfv_live_hitter_matrix.json").read_text(encoding="utf-8"))
    br = next(x for x in live if x["player_key"] == "enrique_bradfield_jr")
    bf = em._vec(br, side)

    strat_rows = []
    for r in matrix:
        if r.get("is_pitcher"):
            continue
        m = r.get("milb") or {}
        if m.get("milb_level") != "AAA":
            continue
        if m.get("age") is None or float(m["age"]) < 23.5:
            continue
        if m.get("ops_rel") is None or float(m["ops_rel"]) >= 0:
            continue
        if r["player_key"] not in scored:
            continue
        strat_rows.append(r)
    sf = {k: statistics.mean([em._vec(r, side).get(k, 0.0) for r in strat_rows])
          for k in ridge["keys"]}

    keys = list(ridge["keys"])
    mu = dict(zip(ridge["keys"], ridge["mu"]))
    sd = dict(zip(ridge["keys"], ridge["sd"]))
    w = dict(zip(ridge["keys"], ridge["w"]))

    def pred_from(vals):
        return ridge["b"] + sum(w[k] * ((vals[k] - mu[k]) / (sd[k] or 1.0)) for k in keys)

    def war_from(vals):
        return max(-2.0, a + b * pred_from(vals))

    base_vals = {k: sf[k] for k in keys}
    full_vals = {k: bf.get(k, 0.0) for k in keys}
    print(f"strat pred {pred_from(base_vals):.4f} war {war_from(base_vals):.4f} "
          f"grade {grade_of(war_from(base_vals)):.4f}")
    print(f"brad  pred {pred_from(full_vals):.4f} war {war_from(full_vals):.4f} "
          f"grade {grade_of(war_from(full_vals)):.4f}")

    # ---- fine grade grid for fast Shapley ------------------------------------
    grid_w = np.arange(-0.5, 8.0001, 0.002)
    grid_g = np.array([grade_of(float(x)) for x in grid_w])

    def g_fast(war):
        return float(np.interp(war, grid_w, grid_g))

    # additive contribution deltas in PRED units
    dpred = {k: w[k] * ((full_vals[k] - base_vals[k]) / (sd[k] or 1.0)) for k in keys}
    base_pred = pred_from(base_vals)

    rng = np.random.default_rng(7)
    n_perm = 20000
    shap = {k: 0.0 for k in keys}
    idx = np.arange(len(keys))
    for _ in range(n_perm):
        rng.shuffle(idx)
        cur = base_pred
        gcur = g_fast(max(-2.0, a + b * cur))
        for i in idx:
            k = keys[i]
            cur += dpred[k]
            gn = g_fast(max(-2.0, a + b * cur))
            shap[k] += gn - gcur
            gcur = gn
    for k in shap:
        shap[k] /= n_perm

    tot = sum(shap.values())
    print(f"\nShapley FV attribution of the grade gap (sum {tot:+.3f} FV, "
          f"check {g_fast(war_from(full_vals)) - g_fast(war_from(base_vals)):+.3f})")
    for k, v in sorted(shap.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {k:18s} dpred {dpred[k]:+7.4f}   FV {v:+7.3f}")

    dcons = float(br["consensus_fv_raw"]) - statistics.mean(
        [float(r["consensus_fv_raw"]) for r in strat_rows])
    print(f"\nconsensus: brad {float(br['consensus_fv_raw']):.3f}  strat "
          f"{statistics.mean([float(r['consensus_fv_raw']) for r in strat_rows]):.3f}  "
          f"delta {dcons:+.3f}")
    print(f"NET consensus-anchor channel (fv Shapley - dcons) = {shap['fv'] - dcons:+.3f} FV")

    # served-mean vs single-row (Jensen) accounting
    served_grade_mean = statistics.mean([scored[r["player_key"]]["xfv_grade"]
                                         for r in strat_rows])
    served_prem_mean = statistics.mean([scored[r["player_key"]]["xfv_minus_consensus"]
                                        for r in strat_rows])
    print(f"\nstratum served mean grade {served_grade_mean:.3f} vs grade-of-mean-feats "
          f"{grade_of(war_from(base_vals)):.3f} -> Jensen/heterogeneity "
          f"{served_grade_mean - grade_of(war_from(base_vals)):+.3f} FV")
    print(f"stratum served mean premium {served_prem_mean:.3f}")

    # ---- counterfactual: give Bradfield the stratum consensus ----------------
    cf = dict(full_vals); cf["fv"] = sf["fv"]
    g_cf = grade_of(war_from(cf))
    print(f"\nCF Bradfield at stratum consensus {sf['fv']:.2f}: war {war_from(cf):.3f} "
          f"grade {g_cf:.3f} premium {g_cf - sf['fv']:+.3f}")
    # CF: stratum with Bradfield's consensus
    cf2 = dict(base_vals); cf2["fv"] = full_vals["fv"]
    g_cf2 = grade_of(war_from(cf2))
    print(f"CF stratum at Bradfield consensus {full_vals['fv']:.2f}: war {war_from(cf2):.3f} "
          f"grade {g_cf2:.3f} premium {g_cf2 - full_vals['fv']:+.3f}")

    # ---- premium as a function of consensus, everything else = Bradfield -----
    print("\npremium curve (Bradfield's non-fv features, sweeping the consensus anchor):")
    for c in (35, 38.73, 40, 42.5, 45.64, 50, 55):
        v = dict(full_vals); v["fv"] = c
        ww = war_from(v); gg = grade_of(ww)
        print(f"  cons {c:6.2f} -> war {ww:5.3f} grade {gg:6.3f} premium {gg - c:+6.3f}")
    print("\npremium curve (stratum-mean non-fv features, sweeping the consensus anchor):")
    for c in (35, 38.73, 40, 42.5, 45.64, 50, 55):
        v = dict(base_vals); v["fv"] = c
        ww = war_from(v); gg = grade_of(ww)
        print(f"  cons {c:6.2f} -> war {ww:5.3f} grade {gg:6.3f} premium {gg - c:+6.3f}")

    # ---- the WAR->FV curve shape --------------------------------------------
    print("\nWAR -> raw grade curve:")
    for x in (0.0, 0.25, 0.5, 0.63, 1.0, 1.5, 1.95, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 4.8, 5.5, 6.5):
        print(f"  war {x:4.2f} -> {grade_of(x):6.3f}")


if __name__ == "__main__":
    main()
