# SCRATCH part 2 of the POOLED-MODEL lane. Read-only wrt shipped modules.
#   (A) alpha-PINNED arms      -> isolate coefficient-sharing loss from alpha-selection noise
#   (B) deviation-penalty sweep-> the full continuum separate <-> fully pooled, fixed multipliers
#   (C) MEASUREMENT PRECISION  -> sd of a paired CANDIDATE delta under sep vs under pooled arms,
#                                 with a placebo null band, on the SAME bootstrap replicates
# Run: python tools/_frontier_pooled2.py         (FP2_B draws, default 200; FP2_MODE=abc)

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _frontier_pooled as fp                     # noqa: E402

OUT = ROOT / "tools" / "_frontier_out"


# ---- alpha-pinned scoring (monkey-free: pass an explicit alpha grid) -------------
def score_pinned(pool, arm, alpha, cand=None, dev_mult=None, drop=None, seed=fp.RIDGE_SEED):
    """Same as fp.score but with the ridge alpha PINNED (no holdout selection) and,
    for the dev-sweep, a FIXED deviation-penalty multiplier."""
    old = fp.ALPHAS
    fp.ALPHAS = (alpha,)
    try:
        if dev_mult is None:
            return fp.score(pool, arm, cand=cand, drop=drop, ridge_seed=seed)
        # fixed dev multiplier: temporarily replace the grid builder
        oldgrid = fp.pen_grid_for
        fp.pen_grid_for = lambda a, keys, c: [
            ("dev%g" % dev_mult,
             np.where(np.array([1.0 if k.startswith("dev_") else 0.0
                                for k in keys + c]) > 0, dev_mult, 1.0))]
        try:
            return fp.score(pool, arm, cand=cand, drop=drop, ridge_seed=seed)
        finally:
            fp.pen_grid_for = oldgrid
    finally:
        fp.ALPHAS = old


def main():
    t0 = time.time()
    mode = os.environ.get("FP2_MODE", "abc")
    pool = fp.load_pool()
    res = {}

    # ---------------------------------------------------------------- (A) alpha pinned
    if "a" in mode:
        print("=== (A) ALPHA-PINNED point estimates (isolates sharing from alpha-holdout noise) ===")
        print("alpha  arm   rho_hit  rho_pit  block_rho   cauc")
        A = {}
        for alpha in (1.0, 10.0, 100.0):
            for arm in ("sep", "p1", "p2", "p3", "p4", "p6"):
                m = fp.metrics(score_pinned(pool, arm, alpha))
                A["%g|%s" % (alpha, arm)] = m
                print("%-6g %-5s %7.4f %8.4f %10.4f %6.4f"
                      % (alpha, arm, m["rho_hit"], m["rho_pit"], m["block_rho"], m["cauc"]))
        res["alpha_pinned"] = A
        print("   (%.0fs)" % (time.time() - t0), flush=True)

    # ---------------------------------------------------------------- (B) dev sweep
    if "b" in mode:
        print("\n=== (B) DEVIATION-PENALTY SWEEP "
              "(dev->0 == the two separate models; dev->inf == one shared coefficient) ===")
        Bm = {}
        for arm in ("p6", "p3"):
            for alpha in (10.0, 100.0):
                print("\n arm=%s alpha=%g" % (arm, alpha))
                print(" dev_mult  rho_hit  rho_pit  block_rho   cauc")
                for dm in (0.001, 0.01, 0.1, 0.5, 1.0, 4.0, 16.0, 64.0, 1e4):
                    m = fp.metrics(score_pinned(pool, arm, alpha, dev_mult=dm))
                    Bm["%s|%g|%g" % (arm, alpha, dm)] = m
                    print(" %-9g %7.4f %8.4f %10.4f %6.4f"
                          % (dm, m["rho_hit"], m["rho_pit"], m["block_rho"], m["cauc"]))
        res["dev_sweep"] = Bm
        print("   (%.0fs)" % (time.time() - t0), flush=True)

    # ---------------------------------------------------------------- (C) precision
    if "c" in mode:
        B = int(os.environ.get("FP2_B", "200"))
        ARMS = ["sep", "p1", "p4", "p6"]
        CANDS = {"prod_trend": {"cand": ["prod_trend"], "drop": None},
                 "drop_peakk": {"cand": [], "drop": {"peak_k_rel", "peak_k_skill",
                                                     "dev_peak_k_skill",
                                                     "hit_peak_k_rel", "pit_peak_k_rel"}}}
        PLACEBO = ["_z%02d" % j for j in range(6)]
        print("\n=== (C) MEASUREMENT PRECISION: paired candidate delta under each arm "
              "(B=%d, metric = block_rho, both sides, production fit) ===" % B)
        MK = ["block_rho", "rho_hit", "rho_pit"]
        rng = np.random.default_rng(fp.SEED + 7)
        names = list(CANDS) + PLACEBO
        acc = {a: {c: {k: [] for k in MK} for c in names} for a in ARMS}

        def deltas(p, a):
            base = fp.metrics(fp.score(p, a))
            d = {}
            for cname, spec in CANDS.items():
                m = fp.metrics(fp.score(p, a, **spec))
                d[cname] = {k: m[k] - base[k] for k in MK}
            for z in PLACEBO:
                m = fp.metrics(fp.score(p, a, cand=[z]))
                d[z] = {k: m[k] - base[k] for k in MK}
            return d

        pt = {a: deltas(pool, a) for a in ARMS}
        for bi in range(B):
            rp = fp.resample(pool, rng)
            for a in ARMS:
                d = deltas(rp, a)
                for c in names:
                    for k in MK:
                        acc[a][c][k].append(d[c][k])
            if (bi + 1) % 20 == 0:
                print("  boot %d/%d  %.0fs" % (bi + 1, B, time.time() - t0), flush=True)

        C = {}
        for k in MK:
            print("\n--- metric %s ---" % k)
            print("arm   candidate     point     mean       sd     CI95              P(>0)   MDE95")
            for a in ARMS:
                C.setdefault(a, {})
                for cname in names:
                    s = fp.summ(acc[a][cname][k])
                    C[a].setdefault(cname, {})[k] = s
                    if not s or cname.startswith("_z"):
                        continue
                    print("%-5s %-12s %+0.4f  %+0.4f  %0.5f  [%+0.4f,%+0.4f]  %.3f  %0.4f"
                          % (a, cname, pt[a][cname][k], s["mean"], s["sd"], s["lo"], s["hi"],
                             s["p_gt0"], 1.645 * s["sd"]))
            print(" NULL BAND (6 zero-information placebo columns, real refits):")
            for a in ARMS:
                vals = [x for z in PLACEBO for x in acc[a][z][k]]
                pts = [pt[a][z][k] for z in PLACEBO]
                print("  %-5s placebo delta sd %0.5f | max |point| %0.5f | mean %+0.5f"
                      % (a, float(np.std(vals, ddof=1)), float(np.max(np.abs(pts))),
                         float(np.mean(vals))))
        res["precision"] = {"point": pt, "boot": C, "B": B, "metrics": MK,
                            "placebo_sd": {a: {k: float(np.std([x for z in PLACEBO
                                                                for x in acc[a][z][k]], ddof=1))
                                               for k in MK} for a in ARMS}}

    json.dump(res, open(OUT / "_scratch_pooled2.json", "w"), indent=1, default=float)
    print("\ntotal %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
