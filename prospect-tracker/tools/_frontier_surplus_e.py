# SCRATCH (not shipped): STAGE E -- tier-level calibration + the value of rank
# accuracy in DOLLARS, on the real resolved surplus pool.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
from backtest import realized_sv_pv                                 # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)
SEED = 20260724
B = 2000


def spear(a, b):
    ra, rb = rankdata(a), rankdata(b)
    ra = ra - ra.mean(); rb = rb - rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else np.nan


def main():
    t0 = time.time()
    records, _ = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    flat_mm = vf.dollars_per_war_flat()
    dpw_flat = {y: {"overall": flat_mm} for y in range(2014, 2035)}

    rows = []
    for rec in resolved:
        lv, rz = rec.listing, rec.realized
        truth = realized_sv_pv(rz, lv.listing_year, discount_rate=disc, dpw_by_year=dpw_flat)
        raw = vf.expected_surplus_usd(lv.fv, lv.is_pitcher, lv.position,
                                      age=lv.age_at_listing, eta_years=lv.eta_years)
        pred = vf.apply_calibration((raw or 0.0) / 1e6, lv.fv, lv.is_pitcher)
        wars = [float(s.fwar) for s in sorted(rz.seasons, key=lambda s: s.year)]
        rows.append({"pid": lv.player_id, "year": int(lv.listing_year), "fv": float(lv.fv),
                     "is_pit": bool(lv.is_pitcher), "pos": lv.position,
                     "age": lv.age_at_listing, "eta": lv.eta_years,
                     "truth": float(truth), "pred": float(pred),
                     "real6": float(sum(wars)), "debuted": rz.debut_year is not None})

    T = np.array([r["truth"] for r in rows])
    P = np.array([r["pred"] for r in rows])
    FV = np.array([r["fv"] for r in rows])
    R6 = np.array([r["real6"] for r in rows])
    PIT = np.array([r["is_pit"] for r in rows])
    PID = np.array([r["pid"] for r in rows])
    res = {"n": len(rows), "seed": SEED, "boot": B}

    # ---- E1/E2: bias by FV tier, dollars AND WAR ---------------------------
    upid = np.unique(PID)
    idx_by = {p: np.flatnonzero(PID == p) for p in upid}
    rng = np.random.default_rng(SEED)
    boots = [np.concatenate([idx_by[upid[j]] for j in rng.integers(0, len(upid), len(upid))])
             for _ in range(B)]

    def tier_of(f):
        return int(np.clip(np.round(f / 5) * 5, 35, 65))

    TIER = np.array([tier_of(f) for f in FV])
    war_pred = np.array([(vf.fv_to_6yr_avg_war(f) or 0.0) * 6 for f in FV])
    tiers = []
    for tv in sorted(set(TIER.tolist())):
        m = TIER == tv
        if m.sum() < 20:
            continue
        db = [float((P[b][TIER[b] == tv] - T[b][TIER[b] == tv]).mean())
              for b in boots if (TIER[b] == tv).sum() >= 5]
        wb = [float((war_pred[b][TIER[b] == tv] - R6[b][TIER[b] == tv]).mean())
              for b in boots if (TIER[b] == tv).sum() >= 5]
        tiers.append({
            "fv_tier": tv, "n": int(m.sum()),
            "pred_mm": round(float(P[m].mean()), 2), "truth_mm": round(float(T[m].mean()), 2),
            "bias_mm": round(float((P[m] - T[m]).mean()), 2),
            "bias_mm_ci95": [round(float(np.percentile(db, 2.5)), 2),
                             round(float(np.percentile(db, 97.5)), 2)],
            "P(overpriced)": round(float((np.array(db) > 0).mean()), 3),
            "mae_mm": round(float(np.abs(P[m] - T[m]).mean()), 2),
            "war_pred": round(float(war_pred[m].mean()), 2),
            "war_realized": round(float(R6[m].mean()), 2),
            "war_bias": round(float((war_pred[m] - R6[m]).mean()), 2),
            "war_bias_ci95": [round(float(np.percentile(wb, 2.5)), 2),
                              round(float(np.percentile(wb, 97.5)), 2)],
            "P(war_overpredicted)": round(float((np.array(wb) > 0).mean()), 3),
            "bust_rate": round(float((R6[m] <= 0).mean()), 3),
        })
    res["by_fv_tier"] = tiers

    # per side
    side_tiers = {}
    for lab, mm in (("hit", ~PIT), ("pit", PIT)):
        out = []
        for tv in sorted(set(TIER[mm].tolist())):
            m = mm & (TIER == tv)
            if m.sum() < 20:
                continue
            out.append({"fv_tier": tv, "n": int(m.sum()),
                        "bias_mm": round(float((P[m] - T[m]).mean()), 2),
                        "war_bias": round(float((war_pred[m] - R6[m]).mean()), 2),
                        "truth_mm": round(float(T[m].mean()), 2),
                        "pred_mm": round(float(P[m].mean()), 2)})
        side_tiers[lab] = out
    res["by_fv_tier_by_side"] = side_tiers

    # ---- E3: the WAR->$ derivative (what a WAR error is worth) -------------
    deriv = []
    for fvv in (40, 45, 50, 55, 60, 65):
        for is_pit, lab in ((False, "hit"), (True, "pit")):
            w0 = (vf.fv_to_6yr_avg_war(fvv) or 0.0) * 6
            s0 = vf.apply_calibration((vf.expected_surplus_usd(fvv, is_pit, None) or 0) / 1e6,
                                      fvv, is_pit)
            # +1.0 WAR over the window, expressed back through the grade map
            fv1 = vf.realized_implied_fv(w0 + 1.0, is_pit, exposure_seasons=6)
            s1 = vf.apply_calibration((vf.expected_surplus_usd(fv1, is_pit, None) or 0) / 1e6,
                                      fv1, is_pit)
            deriv.append({"side": lab, "fv": fvv, "war6": round(w0, 2),
                          "surplus_mm": round(s0, 2),
                          "d_surplus_per_war_mm": round(s1 - s0, 2)})
    res["d_dollar_per_war"] = deriv

    # ---- E4: what is RANK accuracy worth in dollars? -----------------------
    # Hold the served FV multiset fixed (the production display map does exactly
    # this) and vary only WHICH player gets which grade, interpolating from the
    # incumbent (consensus FV) ordering toward the oracle (realized surplus)
    # ordering. Gives a rho -> dollar-MAE curve on the real pool.
    n = len(rows)
    fv_sorted = np.sort(FV)
    base_score = rankdata(FV) / n
    oracle_score = rankdata(T) / n
    curve = []
    rng2 = np.random.default_rng(SEED + 1)
    for w in (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0):
        sc = (1 - w) * base_score + w * oracle_score
        order = np.argsort(sc, kind="stable")
        assigned = np.empty(n)
        assigned[order] = fv_sorted
        pr = np.array([vf.apply_calibration(
            (vf.expected_surplus_usd(assigned[i], rows[i]["is_pit"], rows[i]["pos"],
                                     age=rows[i]["age"], eta_years=rows[i]["eta"]) or 0) / 1e6,
            assigned[i], rows[i]["is_pit"]) for i in range(n)])
        curve.append({"w_toward_oracle": w,
                      "rho_score_vs_truth": round(spear(sc, T), 4),
                      "mae_mm": round(float(np.abs(pr - T).mean()), 3),
                      "rmse_mm": round(float(np.sqrt(((pr - T) ** 2).mean())), 3),
                      "bias_mm": round(float((pr - T).mean()), 3)})
    res["rank_to_dollar_curve"] = curve
    res["rank_to_dollar_note"] = ("Served FV multiset held fixed (== the production quantile "
                                  "display map's contract); only the player->grade assignment "
                                  "changes. rho is Spearman of the assignment score vs realized "
                                  "surplus on the same n.")

    # null band: random re-assignment of the same multiset
    nulls = []
    for _ in range(40):
        sc = rng2.permutation(base_score)
        order = np.argsort(sc, kind="stable")
        assigned = np.empty(n); assigned[order] = fv_sorted
        pr = np.array([vf.apply_calibration(
            (vf.expected_surplus_usd(assigned[i], rows[i]["is_pit"], rows[i]["pos"],
                                     age=rows[i]["age"], eta_years=rows[i]["eta"]) or 0) / 1e6,
            assigned[i], rows[i]["is_pit"]) for i in range(n)])
        nulls.append(float(np.abs(pr - T).mean()))
    res["rank_null_band"] = {"reps": len(nulls), "mae_mean": round(float(np.mean(nulls)), 3),
                             "mae_sd": round(float(np.std(nulls)), 3),
                             "mae_min": round(float(np.min(nulls)), 3),
                             "note": "random assignment of the same FV multiset (zero-information ranking)"}

    (OUT / "_surplus_stageE.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    print("done %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
