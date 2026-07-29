# SCRATCH: (a) ridge alpha sweep + selector variants, under the recommended evaluator.
# Run: python tools/_frontier_shrink_a.py [B]
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontier_shrink import (ORIGINS, LAM, BASE_KEYS, OUT, load_pool, score_records,
                              blend, block_rho, resample_pool, _rho, train_rows,
                              test_rows)

GLOBAL = {"kind": "global"}


# ---- the arms (all are RIDGE-FIT changes, so each needs its own score_records)
def arms():
    a = {"shipped": {"mode": "shipped"}}
    for al in (0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0):
        a[f"fixed_{al:g}"] = {"mode": "fixed", "alpha": al}
    a["grid_wide"] = {"mode": "grid", "alphas": (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)}
    a["seedavg6"] = {"mode": "seedavg", "K": 6}
    a["seedavg6_wide"] = {"mode": "seedavg", "K": 6,
                          "alphas": (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)}
    a["kfold5"] = {"mode": "kfold", "K": 5}
    a["kfold5_wide"] = {"mode": "kfold", "K": 5,
                        "alphas": (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)}
    a["bag12"] = {"mode": "bag", "K": 12, "base": {"mode": "shipped"}, "seed": 606}
    a["bag12_fixed30"] = {"mode": "bag", "K": 12, "base": {"mode": "fixed", "alpha": 30.0},
                          "seed": 606}
    return a


def main(B=250):
    t0 = time.time()
    pool = load_pool()
    print("pool", {s: len(v) for s, v in pool.items()},
          "train", {s: len(train_rows(v)) for s, v in pool.items()},
          "test", {s: len(test_rows(v)) for s, v in pool.items()}, flush=True)

    # ---------- PARITY: reproduce the shipped gate row (hit only, debuted train,
    # origins 2020-2023, pooled raw Spearman) ----------
    rec_p, _ = score_records(pool, BASE_KEYS, {"mode": "shipped"},
                             origins=(2020, 2021, 2022, 2023), sides=("hit",),
                             train_frame="debuted")
    pr = blend(rec_p, GLOBAL)
    print(f"PARITY hit/debuted/2020-23 pooled blend rho = "
          f"{_rho(pr, [r['target'] for r in rec_p]):.4f}  n={len(rec_p)}", flush=True)
    rec_pp, _ = score_records(pool, BASE_KEYS, {"mode": "shipped"},
                              origins=(2020, 2021, 2022, 2023), sides=("pit",),
                              train_frame="debuted")
    pr2 = blend(rec_pp, GLOBAL)
    print(f"PARITY pit/debuted/2020-23 pooled blend rho = "
          f"{_rho(pr2, [r['target'] for r in rec_pp]):.4f}  n={len(rec_pp)}", flush=True)

    A = arms()

    # ---------- point estimates on the recommended evaluator ----------
    point, alph = {}, {}
    for name, cfg in A.items():
        recs, au = score_records(pool, BASE_KEYS, cfg)
        point[name] = block_rho(recs, blend(recs, GLOBAL))
        alph[name] = au
        if name == "shipped":
            n_reco = len(recs)
    print(f"\nRECOMMENDED evaluator n = {n_reco}  (both sides, origins {ORIGINS})")
    print("\n== point block_rho by ridge config ==")
    for name in A:
        d = point[name] - point["shipped"]
        ap = ",".join(f"{a:g}" for _s, _y, a in alph[name]) if alph[name] else "-"
        print(f"  {name:16s} {point[name]:.5f}  d={d:+.5f}   alpha_path[{ap}]")
    print(f"[{time.time()-t0:.0f}s]", flush=True)

    # ---------- selected-alpha instability across bootstrap resamples ----------
    rngA = random.Random(31337)
    flips = {"shipped": [], "kfold5": [], "seedavg6": []}
    for _ in range(60):
        rp = resample_pool(pool, rngA)
        for nm in flips:
            _r, au = score_records(rp, BASE_KEYS, A[nm])
            flips[nm].append([a for _s, _y, a in au])
    print("\n== selected-alpha stability across 60 resampled datasets ==")
    base_path = {nm: [a for _s, _y, a in alph[nm]] for nm in flips}
    for nm, paths in flips.items():
        arr = np.array(paths, dtype=float)
        bp = np.array(base_path[nm], dtype=float)
        same = float((arr == bp).mean()) if arr.shape[1] == len(bp) else float("nan")
        print(f"  {nm:10s} base={list(bp)}  frac-fold-matches-base={same:.3f}  "
              f"distinct_paths={len(set(map(tuple, paths)))}/60  "
              f"log10alpha_sd_per_fold={np.log10(arr).std(axis=0, ddof=1).round(3).tolist()}")
    print(f"[{time.time()-t0:.0f}s]", flush=True)

    # ---------- paired refit bootstrap for a shortlist ----------
    SHORT = ["fixed_1", "fixed_10", "fixed_30", "fixed_100", "fixed_300", "fixed_1000",
             "grid_wide", "seedavg6", "seedavg6_wide", "kfold5", "kfold5_wide",
             "bag12", "bag12_fixed30"]
    boots = {nm: [] for nm in SHORT + ["shipped"]}
    rng = random.Random(4242)
    for b in range(B):
        rp = resample_pool(pool, rng)
        for nm in ["shipped"] + SHORT:
            recs, _ = score_records(rp, BASE_KEYS, A[nm])
            boots[nm].append(block_rho(recs, blend(recs, GLOBAL)))
        if (b + 1) % 25 == 0:
            print(f"[{time.time()-t0:.0f}s] boot {b+1}/{B}", flush=True)

    base = np.array(boots["shipped"], dtype=float)
    print(f"\n== paired refit bootstrap (B={B}, strat on side x decision_year) ==")
    print(f"{'arm':16s} {'delta':>9s} {'boot_mean':>10s} {'sd':>8s} {'CI95lo':>9s} "
          f"{'CI95hi':>9s} {'P(d>0)':>7s} {'MDE95':>8s}")
    res = {}
    for nm in SHORT:
        c = np.array(boots[nm], dtype=float)
        d = c - base
        sd = float(d.std(ddof=1))
        res[nm] = {"delta": round(point[nm] - point["shipped"], 5),
                   "boot_mean": round(float(d.mean()), 5), "sd": round(sd, 5),
                   "ci95": [round(float(np.percentile(d, 2.5)), 5),
                            round(float(np.percentile(d, 97.5)), 5)],
                   "p_gt0": round(float((d > 0).mean()), 3),
                   "mde95_80": round(2.49 * sd, 5)}
        r = res[nm]
        print(f"{nm:16s} {r['delta']:>9.5f} {r['boot_mean']:>10.5f} {r['sd']:>8.5f} "
              f"{r['ci95'][0]:>9.5f} {r['ci95'][1]:>9.5f} {r['p_gt0']:>7.3f} "
              f"{r['mde95_80']:>8.5f}")

    out = {"n": n_reco, "origins": list(ORIGINS), "lam": LAM, "B": B,
           "point": {k: round(v, 5) for k, v in point.items()},
           "alpha_paths": {k: [[s, y, a] for s, y, a in v] for k, v in alph.items()},
           "alpha_stability": {nm: {"base": base_path[nm],
                                    "distinct": len(set(map(tuple, p))),
                                    "paths": p[:20]} for nm, p in flips.items()},
           "bootstrap": res,
           "arm_sd_shipped": round(float(base.std(ddof=1)), 5)}
    (OUT / "_scratch_shrink_a.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote", OUT / "_scratch_shrink_a.json", f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(B=int(sys.argv[1]) if len(sys.argv) > 1 else 250)
