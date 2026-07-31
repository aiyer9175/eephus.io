# scratch lab (lane: discover) -- the CONTINUOUS form of the owner's question.
#
# "Can we use profile comps for specific archetypes to improve eFV?" A k-cluster
# partition is a coarse discretisation of that idea. The sharper instrument: for
# every test row, take its k nearest profile comps among rows whose outcome was
# already known at decision time, and ask whether the comps' OWN out-of-fold
# residuals predict this row's out-of-fold residual.
#
# Strictly forward: fold year Y uses only comps with decision_year < Y, and each
# comp's residual is itself out-of-fold (produced by an earlier fold). Nothing in
# the neighbour pool has seen year Y.
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _arch_discover as A      # noqa: E402
import _arch_ridge as R         # noqa: E402


def run(side, k=25, B=2000, seed=13):
    tr = pickle.load(open(A.SCRATCH / f"clu3_{side}.pkl", "rb"))
    rows = {r["player_key"]: r for r in A.load(side)}
    keys = R.CK[side]
    for r in tr:
        r["_x"] = np.array([R._cf(rows[r["player_key"]], side)[q] for q in keys], float)
    years = sorted({r["year"] for r in tr})
    out = []
    for yi, yr in enumerate(years):
        pool = [r for r in tr if r["year"] < yr]
        te = [r for r in tr if r["year"] == yr]
        if len(pool) < 120 or len(te) < 25:
            continue
        P = np.array([r["_x"] for r in pool])
        mu, sd = P.mean(0), P.std(0)
        sd = np.where(sd == 0, 1.0, sd)
        Pz = (P - mu) / sd
        pres = np.array([r["resid"] for r in pool])
        T = (np.array([r["_x"] for r in te]) - mu) / sd
        d = ((T[:, None, :] - Pz[None, :, :]) ** 2).sum(-1)
        nn = np.argsort(d, axis=1)[:, :k]
        for r, idx in zip(te, nn):
            out.append({"year": yr, "comp_resid": float(pres[idx].mean()),
                        "resid": r["resid"], "weight": r["weight"],
                        "player_key": r["player_key"]})
    if len(out) < 100:
        return None
    # year-block centre both sides so vintage cannot create the correlation
    def cen(f):
        v = np.array([o[f] for o in out], float)
        for y in {o["year"] for o in out}:
            i = np.array([o["year"] == y for o in out])
            v[i] -= v[i].mean()
        return v
    x, y = cen("comp_resid"), cen("resid")
    rho = float(spearmanr(x, y).statistic)
    rng = np.random.default_rng(seed)
    blocks = {}
    for i, o in enumerate(out):
        blocks.setdefault(o["year"], []).append(i)
    null = np.empty(B)
    for b in range(B):
        xp = x.copy()
        for _yy, ii in blocks.items():
            ii = np.array(ii)
            xp[ii] = rng.permutation(x[ii])
        null[b] = spearmanr(xp, y).statistic
    return {"n": len(out), "k": k, "rho": rho, "null_p95": float(np.percentile(null, 95)),
            "null_p5": float(np.percentile(null, 5)),
            "p": float((null >= rho).mean()),
            "years": sorted({o["year"] for o in out})}
