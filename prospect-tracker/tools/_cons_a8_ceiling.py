# A8 -- HEADROOM CEILING. If the best out-of-time LINEAR recombination of the two
# outlets' raw grades cannot beat the live consensus design, the lane is closed.
from __future__ import annotations

import numpy as np

from _cons_a6_boot import (FG, MP, CONS, TGT, WT, DY, SIDE, PULL, DEBUT, BOTH,
                           FOLDS, MIN_TRAIN, MIN_TEST, rho, _R)
from _cons_a7_full import fit, make
from _cons_data import ci

N = len(FG)


def ceiling_pred(tr, te):
    """OLS on the coverage-aware design: WAR ~ 1 + fg*has_fg + mp*has_mp + has_fg
    (so each coverage class gets its own intercept AND slope). Fit on TRAIN only."""
    def design(idx):
        f, m = FG[idx], MP[idx]
        hf, hm = (~np.isnan(f)).astype(float), (~np.isnan(m)).astype(float)
        return np.column_stack([np.ones(len(idx)), hf, hf * np.nan_to_num(f),
                                hm * np.nan_to_num(m), PULL[idx].astype(float)])
    X, y, w = design(tr), TGT[tr], WT[tr]
    b = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]
    return design(te) @ b


def run(pool):
    acc = {k: ([], []) for k in ("live", "ceiling", "served")}
    pf = {k: {} for k in acc}
    for Y in FOLDS:
        tr = pool[DY[pool] < Y]
        te = pool[DY[pool] == Y]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        p = fit(tr)
        x_live = make(te, p, "shift", Y=Y)
        x_ceil = ceiling_pred(tr, te)
        t = TGT[te]
        ok = ~np.isnan(x_live)
        for k, x in (("live", x_live), ("ceiling", x_ceil), ("served", CONS[te])):
            acc[k][0].append(np.asarray(x)[ok])
            acc[k][1].append(t[ok])
            pf[k][int(Y)] = rho(np.asarray(x)[ok], t[ok])
    out = {}
    for k in acc:
        x, y = np.concatenate(acc[k][0]), np.concatenate(acc[k][1])
        out[k] = {"pooled": rho(x, y),
                  "mean_fold": float(np.mean([v for v in pf[k].values() if np.isfinite(v)])),
                  "per_fold": pf[k], "n": len(x)}
    return out


for cohort, mask in (("full", np.ones(N, bool)), ("debuted", DEBUT)):
    pool = np.where(mask)[0]
    r = run(pool)
    print(f"\n=== A8 headroom ceiling, cohort={cohort} (n={r['live']['n']}) ===")
    for k in ("served", "live", "ceiling"):
        print(f"  {k:>8}: pooled {r[k]['pooled']:.4f}  mean-fold {r[k]['mean_fold']:.4f}")
    print(f"  CEILING minus LIVE: pooled {r['ceiling']['pooled']-r['live']['pooled']:+.4f}  "
          f"mean-fold {r['ceiling']['mean_fold']-r['live']['mean_fold']:+.4f}")
    rng = np.random.default_rng(5)
    d = []
    for _ in range(500):
        b = pool[rng.integers(0, len(pool), len(pool))]
        rr = run(b)
        d.append(rr["ceiling"]["pooled"] - rr["live"]["pooled"])
    d = np.array(d)
    lo, hi = np.percentile(d, [2.5, 97.5])
    print(f"  paired bootstrap CI95 [{lo:+.4f},{hi:+.4f}]  P(ceiling > live) = {np.mean(d>0):.3f}")
    print("  per-fold: " + "  ".join(f"{y}:{r['ceiling']['per_fold'][y]-r['live']['per_fold'][y]:+.4f}"
                                     for y in sorted(r['live']['per_fold'])))

# per-side view of the live design vs served
for side, nm in ((0, "hit"), (1, "pit")):
    pool = np.where(DEBUT & (SIDE == side))[0]
    if len(pool) < 300:
        pool = np.where(SIDE == side)[0]
    r = run(pool)
    print(f"\n  side={nm} (n={r['live']['n']}): served {r['served']['pooled']:.4f}  "
          f"live-reconstruction {r['live']['pooled']:.4f}  ceiling {r['ceiling']['pooled']:.4f}")
