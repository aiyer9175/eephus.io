"""ADVERSARIAL re-derivation of the proj_def_prior re-gate.

Independent of tools/_am_proj_e_defprior.py. Adds the two things that harness
was missing:
  * a PERMUTATION NULL BAND (5 independent row-permutations of the SAME
    column, not one), and
  * the PAIRED live-minus-permuted bootstrap, which is the statistic that
    actually adjudicates "is the feature better than its zero-information
    twin", instead of eyeballing whether one CI contains the other's point.
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
from lightgbm import LGBMRegressor  # noqa: E402

SIDE, H = "hit", 5
DEV = [2017, 2018, 2019, 2021]
HOLD = [2022, 2023, 2024]
NPERM = 5

corpus = fp.build_corpus()
names = proj_ml.feature_names(SIDE)
PIDX = names.index("pos_adj_prior")
frame = proj_ml.build_training_frame(corpus, 2003, 2025)[SIDE]
X, Y, R, LS = frame["X"], frame["y"], frame["rows"], frame["label_season"]
print("PIDX", PIDX, "X", X.shape, flush=True)

VAR = {"live": X}
Xz = X.copy(); Xz[:, PIDX] = 0.0
VAR["zeroed"] = Xz
for p in range(NPERM):
    rp = np.random.default_rng(9000 + p)
    Xp = X.copy(); Xp[:, PIDX] = rp.permutation(X[:, PIDX])
    VAR[f"perm{p}"] = Xp

err = {v: defaultdict(list) for v in VAR}
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
            err[v][B].append((h, ridx[te], np.abs(m.predict(Xv[ridx[te]]) - y[te])))
    print(f"  base {B} {time.time()-t0:.0f}s", flush=True)


def pooled(v, bases):
    a = [e for B in bases for (_, _, e) in err[v][B]]
    return float(np.concatenate(a).mean())


out = {"n_perm": NPERM, "pooled": {}, "boot": {}}
for scope, bases in (("holdout", HOLD), ("all", DEV + HOLD)):
    z = pooled("zeroed", bases)
    eff = {v: z - pooled(v, bases) for v in VAR if v != "zeroed"}
    perms = [eff[f"perm{p}"] for p in range(NPERM)]
    out["pooled"][scope] = {
        "zeroed_mae": round(z, 5),
        "delta_live": round(eff["live"], 5),
        "perm_band": [round(x, 5) for x in sorted(perms)],
        "perm_mean": round(float(np.mean(perms)), 5),
        "live_beats_n_of_perms": int(sum(eff["live"] > x for x in perms)),
    }
    print(scope, json.dumps(out["pooled"][scope]), flush=True)

    # paired bootstrap, clustered on the (player, base) feature-vector row
    dl, dpm, grp = [], [[] for _ in range(NPERM)], []
    for B in bases:
        for j, (h, idx, ez) in enumerate(err["zeroed"][B]):
            dl.append(ez - err["live"][B][j][2])
            for p in range(NPERM):
                dpm[p].append(ez - err[f"perm{p}"][B][j][2])
            grp.append(idx)
    dl = np.concatenate(dl); grp = np.concatenate(grp)
    dpm = [np.concatenate(x) for x in dpm]
    dpbar = np.mean(dpm, axis=0)
    uniq = np.unique(grp)
    pos = {g: np.where(grp == g)[0] for g in uniq}
    rb = np.random.default_rng(7)
    bl, bd = [], []
    for _ in range(400):
        pick = rb.choice(uniq, size=len(uniq), replace=True)
        ii = np.concatenate([pos[g] for g in pick])
        bl.append(dl[ii].mean())
        bd.append(dl[ii].mean() - dpbar[ii].mean())   # PAIRED live - permuted twin
    bl, bd = np.asarray(bl), np.asarray(bd)
    out["boot"][scope] = {
        "n_rows": int(len(dl)), "n_clusters": int(len(uniq)),
        "live_mean": float(bl.mean()), "live_ci95": [float(np.percentile(bl, 2.5)),
                                                     float(np.percentile(bl, 97.5))],
        "live_minus_perm_mean": float(bd.mean()),
        "live_minus_perm_ci95": [float(np.percentile(bd, 2.5)),
                                 float(np.percentile(bd, 97.5))],
        "P_live_beats_perm": float((bd > 0).mean()),
    }
    print(scope, json.dumps(out["boot"][scope], indent=1), flush=True)

(ROOT / "tools" / "_av_proj_out_defprior.json").write_text(json.dumps(out, indent=1))
print("saved", flush=True)
