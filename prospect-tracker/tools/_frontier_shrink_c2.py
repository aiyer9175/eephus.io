# SCRATCH: (c2) the CHURN vs ACCURACY tradeoff curve for the blend lambda, plus the
# alpha-selection flip rate at PRODUCTION n. Both legs use the same lambda multipliers
# so the churn saving and the rank cost are read off the same arm.
# Run: python tools/_frontier_shrink_c2.py [R] [B]
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontier_shrink import (LAM, BASE_KEYS, OUT, load_pool, train_rows, block_rho,
                              score_records, resample_pool)
from _frontier_shrink_c import load_live, serve, perturb

MULTS = (0.0, 0.25, 0.4118, 0.5882, 0.8235, 1.0, 1.1765)
SH = {"mode": "shipped"}


def main(R=40, B=250):
    t0 = time.time()
    pool = load_pool()
    live = load_live()
    tr = {s: train_rows(pool[s]) for s in ("hit", "pit")}

    # ---------- alpha selection at PRODUCTION n under a 10%-drop rebuild ----------
    rng = random.Random(777)
    picks = {s: [] for s in ("hit", "pit")}
    runs = {m: {s: [] for s in ("hit", "pit")} for m in MULTS}
    for i in range(R):
        pert = {s: perturb(tr[s], rng, "drop") for s in ("hit", "pit")}
        for s in ("hit", "pit"):
            for m in MULTS:
                _rw, dg, al = serve(pert[s], live[s], s, SH, m)
                runs[m][s].append(dg)
                if m == 1.0:
                    picks[s].append(al)
        if (i + 1) % 10 == 0:
            print(f"[{time.time()-t0:.0f}s] churn run {i+1}/{R}", flush=True)
    print("\n== shipped alpha selected at PRODUCTION n (10%-drop rebuilds) ==")
    for s in ("hit", "pit"):
        print(f"  {s}: {dict(Counter(picks[s]))}   (n_train ~ {len(tr[s])})")

    churn = {}
    print(f"\n== CHURN of the SERVED display grade vs lambda (R={R}, drop-10% rebuilds) ==")
    print(f"{'lam_mult':>9s} {'lam_hit':>8s} {'lam_pit':>8s} {'sd_grade':>9s} "
          f"{'mad_pair':>9s} {'p|d|>1.0':>9s} {'vs_shipped':>11s}")
    for m in MULTS:
        agg = {}
        tot = 0
        for s in ("hit", "pit"):
            M = np.vstack(runs[m][s])
            dp = np.abs(np.diff(M, axis=0))
            n = M.shape[1]
            tot += n
            agg["sd_grade"] = agg.get("sd_grade", 0) + float(M.std(axis=0, ddof=1).mean()) * n
            agg["mad_pair"] = agg.get("mad_pair", 0) + float(dp.mean()) * n
            agg["p_gt_10"] = agg.get("p_gt_10", 0) + float((dp >= 1.0).mean()) * n
        agg = {k: v / tot for k, v in agg.items()}
        churn[m] = agg
    base_c = churn[1.0]
    for m in MULTS:
        a = churn[m]
        print(f"{m:>9.4f} {LAM['hit']*m:>8.3f} {LAM['pit']*m:>8.3f} {a['sd_grade']:>9.4f} "
              f"{a['mad_pair']:>9.4f} {a['p_gt_10']:>9.4f} "
              f"{(a['sd_grade']/base_c['sd_grade']-1)*100:>10.1f}%")

    # ---------- paired rank cost of the SAME lambda multipliers ----------
    def bl(recs, m):
        return np.array([(1 - LAM[r["side"]] * m) * r["cons"] + LAM[r["side"]] * m * r["mod"]
                         for r in recs])
    recs, _ = score_records(pool, BASE_KEYS, SH)
    point = {m: block_rho(recs, bl(recs, m)) for m in MULTS}
    boots = {m: [] for m in MULTS}
    rng2 = random.Random(4242)
    for b in range(B):
        rp = resample_pool(pool, rng2)
        rr, _ = score_records(rp, BASE_KEYS, SH)
        for m in MULTS:
            boots[m].append(block_rho(rr, bl(rr, m)))
        if (b + 1) % 50 == 0:
            print(f"[{time.time()-t0:.0f}s] rho boot {b+1}/{B}", flush=True)
    base_b = np.array(boots[1.0], dtype=float)
    print(f"\n== RANK cost of the same lambda multipliers (recommended evaluator, "
          f"n={len(recs)}, B={B}) ==")
    print(f"{'lam_mult':>9s} {'block_rho':>10s} {'delta':>9s} {'sd':>8s} {'CI95lo':>9s} "
          f"{'CI95hi':>9s} {'P(d>0)':>7s} {'MDE95':>8s}  {'churn_vs_shipped':>16s}")
    res = {}
    for m in MULTS:
        d = np.array(boots[m], dtype=float) - base_b
        sd = float(d.std(ddof=1))
        res[m] = {"block_rho": round(point[m], 5),
                  "delta": round(point[m] - point[1.0], 5), "sd": round(sd, 5),
                  "ci95": [round(float(np.percentile(d, 2.5)), 5),
                           round(float(np.percentile(d, 97.5)), 5)],
                  "p_gt0": round(float((d > 0).mean()), 3),
                  "mde95_80": round(2.49 * sd, 5),
                  "churn": {k: round(v, 5) for k, v in churn[m].items()},
                  "churn_rel_pct": round((churn[m]["sd_grade"] / base_c["sd_grade"] - 1) * 100, 2)}
        r = res[m]
        print(f"{m:>9.4f} {r['block_rho']:>10.5f} {r['delta']:>9.5f} {r['sd']:>8.5f} "
              f"{r['ci95'][0]:>9.5f} {r['ci95'][1]:>9.5f} {r['p_gt0']:>7.3f} "
              f"{r['mde95_80']:>8.5f}  {r['churn_rel_pct']:>15.1f}%")

    (OUT / "_scratch_shrink_c2.json").write_text(json.dumps(
        {"R": R, "B": B, "n_eval": len(recs), "lam": LAM,
         "alpha_picks_production_n": {s: {str(k): v for k, v in Counter(picks[s]).items()}
                                      for s in picks},
         "train_n": {s: len(v) for s, v in tr.items()},
         "arms": {str(k): v for k, v in res.items()}}, indent=1), encoding="utf-8")
    print("\nwrote", OUT / "_scratch_shrink_c2.json", f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(R=int(sys.argv[1]) if len(sys.argv) > 1 else 40,
         B=int(sys.argv[2]) if len(sys.argv) > 2 else 250)
