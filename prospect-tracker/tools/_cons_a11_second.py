# A11 -- second metric (full-pool debut/no-debut discrimination AUC) for the gate,
# plus alternative single-source pull TRIGGERS.
from __future__ import annotations

import numpy as np

from _cons_a6_boot import (FG, MP, CONS, TGT, WT, DY, SIDE, PULL, DEBUT, BOTH,
                           FOLDS, MIN_TRAIN, MIN_TEST, rho, rankdata, _R)
from _cons_a7_full import fit, make

N = len(FG)
NSRC = np.array([r["n_sources"] for r in _R], int)
TRIG = {"live": PULL, "nsrc1": NSRC <= 1, "never": np.zeros(N, bool),
        "always_single_or_none": NSRC <= 1}


def AUC(s, lab):
    s = np.asarray(s, float)
    lab = np.asarray(lab, bool)
    npos, nneg = lab.sum(), (~lab).sum()
    if npos == 0 or nneg == 0:
        return np.nan
    r = rankdata(s) + 1.0
    return float((r[lab].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def make_trig(idx, p, kind, trig, K=0.5, prior=35.0):
    x = make(idx, p, kind, pull=None)
    w = 1.0 / (1.0 + K)
    return np.where(trig[idx], w * x + (1 - w) * prior, x)


def evaluate(pool, specs, seed=None, rng=None):
    acc = {nm: ([], [], []) for nm in specs}
    for Y in FOLDS:
        tr = pool[DY[pool] < Y]
        te = pool[DY[pool] == Y]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        p = fit(tr)
        for nm, (kind, trg, K, pr) in specs.items():
            x = (CONS[te] if kind == "served"
                 else make_trig(te, p, kind, TRIG[trg], K, pr))
            ok = ~np.isnan(x)
            acc[nm][0].append(np.asarray(x)[ok])
            acc[nm][1].append(TGT[te][ok])
            acc[nm][2].append(DEBUT[te][ok])
    out = {}
    for nm in acc:
        x = np.concatenate(acc[nm][0])
        y = np.concatenate(acc[nm][1])
        d = np.concatenate(acc[nm][2])
        out[nm] = {"rho": rho(x, y), "auc_debut": AUC(x, d),
                   "auc_contrib": AUC(x, y >= 3.0), "n": len(x)}
    return out


SPECS = {
    "served (live values)":        ("served", "live", 0.5, 35.0),
    "raw mean, no offset":         ("raw", "live", 0.5, 35.0),
    "LIVE design (offset+pull)":   ("shift", "live", 0.5, 35.0),
    "+ shipped src weights":       ("shipped", "live", 0.5, 35.0),
    "+ inverse-variance weights":  ("ivw", "live", 0.5, 35.0),
    "sd(distribution) map":        ("sd", "live", 0.5, 35.0),
    "pull removed":                ("shift", "never", 0.5, 35.0),
    "pull trigger = n_sources<=1": ("shift", "nsrc1", 0.5, 35.0),
    "pull K=1.0 prior 30":         ("shift", "live", 1.0, 30.0),
}

pool = np.arange(N)
base = evaluate(pool, SPECS)
ref = base["LIVE design (offset+pull)"]
print(f"=== A11 two-metric read, FULL pool, forward-chained (n={ref['n']}) ===")
print(f"{'variant':>30} {'rho':>8} {'d':>9} {'AUC debut':>10} {'d':>9} "
      f"{'AUC contrib':>12} {'d':>9}")
for nm, v in base.items():
    print(f"{nm:>30} {v['rho']:>8.4f} {v['rho']-ref['rho']:>+9.4f} "
          f"{v['auc_debut']:>10.4f} {v['auc_debut']-ref['auc_debut']:>+9.4f} "
          f"{v['auc_contrib']:>12.4f} {v['auc_contrib']-ref['auc_contrib']:>+9.4f}")

rng = np.random.default_rng(9)
B = 500
d = {nm: {"rho": [], "ad": [], "ac": []} for nm in SPECS}
for _ in range(B):
    b = pool[rng.integers(0, N, N)]
    r = evaluate(b, SPECS)
    rf = r["LIVE design (offset+pull)"]
    for nm in SPECS:
        d[nm]["rho"].append(r[nm]["rho"] - rf["rho"])
        d[nm]["ad"].append(r[nm]["auc_debut"] - rf["auc_debut"])
        d[nm]["ac"].append(r[nm]["auc_contrib"] - rf["auc_contrib"])
print(f"\n  paired bootstrap B={B} (refit each draw), delta vs the LIVE design:")
print(f"{'variant':>30} {'d rho CI95':>22} {'d AUCdebut CI95':>22} "
      f"{'d AUCcontrib CI95':>22}")
for nm in SPECS:
    a = np.array(d[nm]["rho"]); b1 = np.array(d[nm]["ad"]); c = np.array(d[nm]["ac"])
    f = lambda z: f"[{np.percentile(z,2.5):+.4f},{np.percentile(z,97.5):+.4f}]"
    print(f"{nm:>30} {f(a):>22} {f(b1):>22} {f(c):>22}")
