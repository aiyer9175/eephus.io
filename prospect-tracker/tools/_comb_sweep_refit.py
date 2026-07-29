# SCRATCH LAB (combinatorial-archetype lane, SWEEP sub-lane). READ-ONLY.
#
# STEP 3, the literal version: PERMUTE THE OUTCOME AND RE-RUN THE ENTIRE SWEEP, model
# refit included, N times, recording the best statistic each time. The residual-permutation
# null in _comb_sweep.py holds the fitted model fixed; this one does not, so it also
# absorbs the extra freedom the refit itself has.
#
# y is permuted WITHIN decision-year blocks, so year composition and the marginal outcome
# distribution are preserved exactly and only the row-to-outcome link is destroyed.
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from _comb_sweep import (OUT, SEED, ARMS, MIN_N, build, crossfit, populations,   # noqa: E402
                         enumerate_strata, indicator, residual_arms, welch_t)


def run(side="hit", pop="TRACK", nperm=200):
    t0 = time.time()
    D = build(side)
    base = populations(D)
    root = pop[:-1] if pop.endswith("C") else pop
    mask, scope = base[root]
    strata, _N, _lv = enumerate_strata(D, mask, scope)
    idx = np.flatnonzero(mask)
    M = indicator(D, strata, idx)
    keepj = M.sum(axis=0) >= MIN_N
    M = M[:, keepj]
    strata = [s for s, k in zip(strata, keepj) if k]

    pred = crossfit(D)
    R = residual_arms(D, idx, pred)
    obs = max(float(np.abs(welch_t(M, R[a])[0]).max()) for a in ARMS)
    obs_arm = {a: float(np.abs(welch_t(M, R[a])[0]).max()) for a in ARMS}

    rng = np.random.default_rng(SEED + 991)
    dy_all = D["dy"]
    y0 = D["y"].copy()
    best = np.empty(nperm)
    best_arm = {a: np.empty(nperm) for a in ARMS}
    for b in range(nperm):
        yp = y0.copy()
        for yr in np.unique(dy_all):
            sl = np.flatnonzero(dy_all == yr)
            yp[sl] = y0[rng.permutation(sl)]
        Dp = dict(D)
        Dp["y"] = yp
        pp = crossfit(Dp, y=yp)
        Rp = residual_arms(Dp, idx, pp)
        vals = {a: float(np.abs(welch_t(M, Rp[a])[0]).max()) for a in ARMS}
        for a in ARMS:
            best_arm[a][b] = vals[a]
        best[b] = max(vals.values())
    res = {"side": side, "pop": pop, "n_perm": nperm, "n_hypotheses_per_arm": len(strata),
           "n_hypotheses_family": len(ARMS) * len(strata),
           "observed_max_abs_t_joint": round(obs, 3),
           "observed_max_abs_t_by_arm": {a: round(v, 3) for a, v in obs_arm.items()},
           "refit_perm_crit95_joint": round(float(np.quantile(best, 0.95)), 3),
           "refit_perm_median_joint": round(float(np.median(best)), 3),
           "refit_perm_max_joint": round(float(best.max()), 3),
           "refit_perm_p_joint": float((best >= obs).mean()),
           "by_arm": {a: {"crit95": round(float(np.quantile(best_arm[a], 0.95)), 3),
                          "median": round(float(np.median(best_arm[a])), 3),
                          "p": float((best_arm[a] >= obs_arm[a]).mean())} for a in ARMS},
           "draws": [round(float(v), 4) for v in best]}
    fp = OUT / ("refitperm_%s_%s.json" % (side, pop))
    fp.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("[%s/%s] refit-permutation null, %d draws, K=%d per arm (%d family)"
          % (side, pop, nperm, len(strata), len(ARMS) * len(strata)))
    print("  joint: observed max|t| %.3f   perm median %.3f   crit95 %.3f   p %.4f"
          % (obs, res["refit_perm_median_joint"], res["refit_perm_crit95_joint"],
             res["refit_perm_p_joint"]))
    for a in ARMS:
        print("  %-7s observed %5.2f   perm crit95 %5.2f   median %5.2f   p %.4f"
              % (a, obs_arm[a], res["by_arm"][a]["crit95"], res["by_arm"][a]["median"],
                 res["by_arm"][a]["p"]))
    print("  %.1fs -> %s" % (time.time() - t0, fp))
    return res


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "hit",
        sys.argv[2] if len(sys.argv) > 2 else "TRACK",
        int(sys.argv[3]) if len(sys.argv) > 3 else 200)
