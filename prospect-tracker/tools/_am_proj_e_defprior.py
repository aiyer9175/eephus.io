"""AM-PROJ (a/e): re-gate the SHIPPED proj_ml defensive prior against the
zero-information control the original gate never ran.

The registry ships `pos_adj_prior` on a holdout pooled-MAE delta of -0.0027 with
no floor, no bootstrap and no control. This harness reproduces the protocol
(hitters, q50 only, forward-chained, label season <= B-1) and adds:

  live    : the shipped feature as-is
  zeroed  : the column set to 0.0 (the "no defensive prior" baseline)
  perm    : the SAME column, ROW-PERMUTED -- identical marginal distribution,
            zero information. If `perm` beats `zeroed` by as much as `live`
            does, the shipped feature is not a result.

Effect = MAE(zeroed) - MAE(variant); positive favours the variant.
Floor: cluster bootstrap over players on the paired per-row absolute-error
differences. This is TEST-SIDE only, which the gate standard documents as
understating sd by 1.6-1.8x, so the conservative floor is 1.7 x 1.96 x sd.
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp  # noqa: E402
import proj_ml  # noqa: E402

SIDE = "hit"
H = 5
DEV = [2017, 2018, 2019, 2021]
HOLD = [2022, 2023, 2024]
SEED = 20260725

corpus = fp.build_corpus()
names = proj_ml.feature_names(SIDE)
PIDX = names.index("pos_adj_prior")
print("pos_adj_prior at index", PIDX, "of", len(names))

frame = proj_ml.build_training_frame(corpus, 2003, 2025)[SIDE]
X, Y, R, LS = frame["X"], frame["y"], frame["rows"], frame["label_season"]
print("X", X.shape)

rng = np.random.default_rng(SEED)
X_perm = X.copy()
X_perm[:, PIDX] = rng.permutation(X[:, PIDX])
X_zero = X.copy()
X_zero[:, PIDX] = 0.0
VAR = {"live": X, "zeroed": X_zero, "perm": X_perm}

from lightgbm import LGBMRegressor  # noqa: E402

err = {v: defaultdict(list) for v in VAR}      # variant -> base -> per-row |err|
key = defaultdict(list)                        # base -> row identity for pairing
t0 = time.time()
for B in DEV + HOLD:
    for h in range(1, H + 1):
        ridx, ls = R[h], LS[h]
        tr = np.where(ls <= B - 1)[0]
        te = np.where(ls == B + h - 1)[0]
        if len(tr) < 500 or len(te) < 50:
            continue
        y = Y[h]
        for v, Xv in VAR.items():
            m = LGBMRegressor(alpha=0.50, **proj_ml._params_for(h))
            m.fit(Xv[ridx[tr]], y[tr])
            p = m.predict(Xv[ridx[te]])
            err[v][B].append((h, ridx[te], np.abs(p - y[te])))
    print(f"  base {B} done {time.time()-t0:.0f}s")


def pooled(v, bases):
    a = [e for B in bases for (_, _, e) in err[v][B]]
    return float(np.concatenate(a).mean()) if a else float("nan")


out = {"dev_bases": DEV, "holdout_bases": HOLD, "pooled": {}}
for scope, bases in (("dev", DEV), ("holdout", HOLD), ("all", DEV + HOLD)):
    z = pooled("zeroed", bases)
    out["pooled"][scope] = {v: round(pooled(v, bases), 5) for v in VAR}
    out["pooled"][scope]["delta_live"] = round(z - pooled("live", bases), 5)
    out["pooled"][scope]["delta_perm"] = round(z - pooled("perm", bases), 5)
    print(f"{scope:<8} zeroed {z:.5f}  live {pooled('live',bases):.5f} "
          f"(delta {z-pooled('live',bases):+.5f})  perm {pooled('perm',bases):.5f} "
          f"(delta {z-pooled('perm',bases):+.5f})")

# cluster bootstrap over the eval ROWS' feature-vector identity (one vector per
# player-base), on the paired per-row absolute-error differences
for scope, bases in (("holdout", HOLD), ("all", DEV + HOLD)):
    dl, dp, grp = [], [], []
    for B in bases:
        z = {(h, tuple(i)): e for (h, i, e) in [(a, b, c) for a, b, c in err["zeroed"][B]]}
        for (h, idx, ez), (_, _, el), (_, _, ep) in zip(err["zeroed"][B], err["live"][B],
                                                        err["perm"][B]):
            dl.append(ez - el)
            dp.append(ez - ep)
            grp.append(idx)
    dl, dp, grp = np.concatenate(dl), np.concatenate(dp), np.concatenate(grp)
    uniq = np.unique(grp)
    pos = {g: np.where(grp == g)[0] for g in uniq}
    r2 = np.random.default_rng(SEED + 1)
    bl, bp = [], []
    for _ in range(400):
        pick = r2.choice(uniq, size=len(uniq), replace=True)
        ii = np.concatenate([pos[g] for g in pick])
        bl.append(dl[ii].mean())
        bp.append(dp[ii].mean())
    bl, bp = np.asarray(bl), np.asarray(bp)
    out[f"boot_{scope}"] = {
        "n_rows": int(len(dl)), "n_clusters": int(len(uniq)),
        "live_mean": float(bl.mean()), "live_sd": float(bl.std(ddof=1)),
        "live_mde95_testside": float(1.96 * bl.std(ddof=1)),
        "live_mde95_conservative": float(1.7 * 1.96 * bl.std(ddof=1)),
        "live_ci95": [float(np.percentile(bl, 2.5)), float(np.percentile(bl, 97.5))],
        "perm_mean": float(bp.mean()),
        "perm_ci95": [float(np.percentile(bp, 2.5)), float(np.percentile(bp, 97.5))],
    }
    b = out[f"boot_{scope}"]
    print(f"[{scope}] n={b['n_rows']} clusters={b['n_clusters']} "
          f"live {b['live_mean']:+.5f} CI95 [{b['live_ci95'][0]:+.5f},{b['live_ci95'][1]:+.5f}] "
          f"MDE95(test-side) {b['live_mde95_testside']:.5f} "
          f"MDE95(conservative) {b['live_mde95_conservative']:.5f} | "
          f"perm {b['perm_mean']:+.5f} CI95 [{b['perm_ci95'][0]:+.5f},{b['perm_ci95'][1]:+.5f}]")

json.dump(out, open(ROOT / "tools" / "_am_proj_out_defprior.json", "w"), indent=1)
print("saved")
