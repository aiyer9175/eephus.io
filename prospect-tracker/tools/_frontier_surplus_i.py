# SCRATCH (not shipped): STAGE I -- clean apples-to-apples bound comparison.
# All three boards priced through the SAME in-sample refit floored-linear
# calibration, so the only difference is the information/constraint:
#   (1) incumbent   : listed consensus FV, as served
#   (2) perfect rank: same FV MULTISET, perfect ordering (the display-map contract)
#   (3) free grade  : perfect 6yr-WAR foresight, grade unconstrained
# The gap (2)-(3) is the price of pinning the served grade distribution to the
# consensus FV distribution.
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only     # noqa: E402
from backtest import realized_sv_pv                                 # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"
SEED = 20260724
B = 2000


def cal_insample(raw, truth):
    lr = stats.linregress(raw, truth)
    return np.maximum(0.0, lr.slope * raw + lr.intercept)


def main():
    records, _ = build_cohorts()
    resolved = _resolved_only(records)
    cfg = vf._config()
    disc = float(cfg["discount_rate"])
    dpw = {y: {"overall": vf.dollars_per_war_flat()} for y in range(2014, 2035)}
    rows = [{"pid": r.listing.player_id, "fv": float(r.listing.fv),
             "pit": bool(r.listing.is_pitcher), "pos": r.listing.position,
             "age": r.listing.age_at_listing, "eta": r.listing.eta_years,
             "truth": float(realized_sv_pv(r.realized, r.listing.listing_year,
                                           discount_rate=disc, dpw_by_year=dpw)),
             "real6": float(sum(s.fwar for s in r.realized.seasons))} for r in resolved]
    n = len(rows)
    T = np.array([r["truth"] for r in rows]); FV = np.array([r["fv"] for r in rows])
    W6 = np.array([r["real6"] for r in rows]); PID = np.array([r["pid"] for r in rows])

    def raw_at(fvs):
        return np.array([(vf.expected_surplus_usd(float(fvs[i]), rows[i]["pit"], rows[i]["pos"],
                                                  age=rows[i]["age"], eta_years=rows[i]["eta"])
                          or 0.0) / 1e6 for i in range(n)])

    # (1) incumbent
    raw1 = raw_at(FV)
    # (2) perfect rank, same multiset
    fv_sorted = np.sort(FV)
    order = np.argsort(rankdata(T), kind="stable")
    fv2 = np.empty(n); fv2[order] = fv_sorted
    raw2 = raw_at(fv2)
    # (3) free grade from perfect WAR
    fv3 = np.array([vf.realized_implied_fv(rows[i]["real6"], rows[i]["pit"],
                                           position=rows[i]["pos"], exposure_seasons=6) or 20.0
                    for i in range(n)])
    raw3 = raw_at(fv3)

    P = {"1_incumbent": cal_insample(raw1, T), "2_perfect_rank_fixed_multiset": cal_insample(raw2, T),
         "3_perfect_war_free_grade": cal_insample(raw3, T)}
    res = {"n": n, "note": "all three priced through the SAME in-sample floored-linear calibration",
           "levels": {k: {"mae": round(float(np.abs(v - T).mean()), 3),
                          "rmse": round(float(np.sqrt(((v - T) ** 2).mean())), 3),
                          "bias": round(float((v - T).mean()), 3),
                          "served_fv_mean": round(float(f.mean()), 2),
                          "served_fv_sd": round(float(f.std()), 2)}
                      for (k, v), f in zip(P.items(), (FV, fv2, fv3))}}
    res["gaps"] = {
        "multiset_constraint_cost_mm": round(res["levels"]["2_perfect_rank_fixed_multiset"]["mae"]
                                             - res["levels"]["3_perfect_war_free_grade"]["mae"], 3),
        "ranking_headroom_mm": round(res["levels"]["1_incumbent"]["mae"]
                                     - res["levels"]["2_perfect_rank_fixed_multiset"]["mae"], 3),
    }

    rng = np.random.default_rng(SEED)
    upid = np.unique(PID); idx_by = {p: np.flatnonzero(PID == p) for p in upid}
    g1, g2 = [], []
    for _ in range(B):
        s = rng.integers(0, len(upid), len(upid))
        idx = np.concatenate([idx_by[upid[j]] for j in s])
        t = T[idx]
        m = {k: float(np.abs(cal_insample(r[idx], t) - t).mean())
             for k, r in (("1", raw1), ("2", raw2), ("3", raw3))}
        g1.append(m["2"] - m["3"]); g2.append(m["1"] - m["2"])
    q = lambda a, p: round(float(np.percentile(a, p)), 3)
    res["bootstrap"] = {
        "reps": B, "cluster": "player",
        "multiset_constraint_cost": {"mean": round(float(np.mean(g1)), 3),
                                     "ci95": [q(g1, 2.5), q(g1, 97.5)],
                                     "P(>0)": round(float((np.array(g1) > 0).mean()), 4)},
        "ranking_headroom": {"mean": round(float(np.mean(g2)), 3),
                             "ci95": [q(g2, 2.5), q(g2, 97.5)],
                             "P(>0)": round(float((np.array(g2) > 0).mean()), 4)},
    }
    (OUT / "_surplus_stageI.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
