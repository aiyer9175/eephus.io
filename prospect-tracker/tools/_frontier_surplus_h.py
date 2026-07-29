# SCRATCH (not shipped): STAGE H -- what is a unit of RANK accuracy worth in
# surplus dollars? Fine-grained curve near the incumbent, both rho axes, with a
# player-clustered bootstrap on the local slope and a zero-information null band.
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
B = 400


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
    dpw = {y: {"overall": flat_mm} for y in range(2014, 2035)}

    rows = []
    for rec in resolved:
        lv, rz = rec.listing, rec.realized
        rows.append({"pid": lv.player_id, "fv": float(lv.fv), "pit": bool(lv.is_pitcher),
                     "pos": lv.position, "age": lv.age_at_listing, "eta": lv.eta_years,
                     "truth": float(realized_sv_pv(rz, lv.listing_year, discount_rate=disc,
                                                   dpw_by_year=dpw)),
                     "real6": float(sum(s.fwar for s in rz.seasons))})
    n = len(rows)
    T = np.array([r["truth"] for r in rows]); FV = np.array([r["fv"] for r in rows])
    W6 = np.array([r["real6"] for r in rows]); PID = np.array([r["pid"] for r in rows])
    fv_sorted = np.sort(FV)

    # price cache: (fv_value, player) -> $M. The assignment only ever hands a
    # player one of the n values in the multiset, so cache per (player, fv).
    cache = {}

    def price(i, fvv):
        k = (i, round(float(fvv), 4))
        v = cache.get(k)
        if v is None:
            raw = vf.expected_surplus_usd(fvv, rows[i]["pit"], rows[i]["pos"],
                                          age=rows[i]["age"], eta_years=rows[i]["eta"])
            v = vf.apply_calibration((raw or 0.0) / 1e6, fvv, rows[i]["pit"])
            cache[k] = v
        return v

    base_score = rankdata(FV) / n
    oracle_score = rankdata(T) / n

    def board(score):
        order = np.argsort(score, kind="stable")
        assigned = np.empty(n)
        assigned[order] = fv_sorted
        return np.array([price(i, assigned[i]) for i in range(n)])

    ws = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75, 1.0]
    SC = {w: (1 - w) * base_score + w * oracle_score for w in ws}
    PR = {w: board(SC[w]) for w in ws}
    curve = []
    for w in ws:
        curve.append({"w": w,
                      "rho_vs_realized_surplus": round(spear(SC[w], T), 4),
                      "rho_vs_realized_6yr_war": round(spear(SC[w], W6), 4),
                      "mae_mm": round(float(np.abs(PR[w] - T).mean()), 4),
                      "rmse_mm": round(float(np.sqrt(((PR[w] - T) ** 2).mean())), 3)})
    res = {"n": n, "seed": SEED, "boot": B, "curve": curve}

    # local slope near the incumbent: d(MAE) per +0.01 of rho-vs-realized-WAR,
    # bootstrapped over players (assignment recomputed inside the replicate).
    rng = np.random.default_rng(SEED)
    upid = np.unique(PID); idx_by = {p: np.flatnonzero(PID == p) for p in upid}
    slopes, d10 = [], []
    for _ in range(B):
        s = rng.integers(0, len(upid), len(upid))
        idx = np.concatenate([idx_by[upid[j]] for j in s])
        t = T[idx]
        m0 = float(np.abs(PR[0.0][idx] - t).mean())
        m1 = float(np.abs(PR[0.10][idx] - t).mean())
        r0 = spear(SC[0.0][idx], W6[idx]); r1 = spear(SC[0.10][idx], W6[idx])
        d10.append(m1 - m0)
        if abs(r1 - r0) > 1e-6:
            slopes.append((m1 - m0) / (r1 - r0) * 0.01)   # $M MAE per +0.01 rho
    q = lambda a, p: float(np.percentile(a, p))
    res["local_value_of_rank"] = {
        "definition": "$M held-out-free MAE change per +0.01 Spearman (vs realized 6yr WAR), "
                      "measured over the w=0 -> w=0.10 segment, served FV multiset held fixed",
        "point_mm_per_0.01_rho": round(float(np.mean(slopes)), 4),
        "ci95": [round(q(slopes, 2.5), 4), round(q(slopes, 97.5), 4)],
        "d_mae_w0_to_w0.10": {"mean": round(float(np.mean(d10)), 4),
                              "ci95": [round(q(d10, 2.5), 4), round(q(d10, 97.5), 4)],
                              "P(improves)": round(float((np.array(d10) < 0).mean()), 4)},
    }

    # zero-information null: random assignment of the same multiset
    rngn = np.random.default_rng(SEED + 3)
    nulls = [float(np.abs(board(rngn.permutation(base_score)) - T).mean()) for _ in range(40)]
    res["null_band_random_assignment"] = {
        "reps": len(nulls), "mae_mean": round(float(np.mean(nulls)), 3),
        "mae_sd": round(float(np.std(nulls)), 3)}
    res["headroom"] = {
        "random_board_mae": round(float(np.mean(nulls)), 3),
        "incumbent_board_mae": round(float(np.abs(PR[0.0] - T).mean()), 3),
        "perfect_rank_same_multiset_mae": round(float(np.abs(PR[1.0] - T).mean()), 3),
        "share_of_ranking_value_already_captured": round(
            (float(np.mean(nulls)) - float(np.abs(PR[0.0] - T).mean()))
            / (float(np.mean(nulls)) - float(np.abs(PR[1.0] - T).mean())), 3),
    }

    (OUT / "_surplus_stageH.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    print("done %.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
