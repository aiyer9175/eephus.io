# A12 -- full gate on the one candidate that moved a second metric: widening the
# single-source pull TRIGGER from "1 published-FV instance ever" to "1 source at
# the decision point". Zero-information control = a row-permuted trigger with the
# identical firing rate.
from __future__ import annotations

import numpy as np

from _cons_a6_boot import (FG, MP, CONS, TGT, DY, SIDE, PULL, DEBUT, FOLDS,
                           MIN_TRAIN, MIN_TEST, rho, rankdata, _R)
from _cons_a7_full import fit, make

N = len(FG)
NSRC = np.array([r["n_sources"] for r in _R], int)
NS1 = NSRC <= 1
print(f"pool n={N}   live trigger fires on {PULL.sum()} rows ({PULL.mean():.1%})")
print(f"           n_sources<=1 fires on {NS1.sum()} rows ({NS1.mean():.1%})")
print(f"           overlap {int((PULL & NS1).sum())}")


def AUC(s, lab):
    npos, nneg = lab.sum(), (~lab).sum()
    if npos == 0 or nneg == 0:
        return np.nan
    r = rankdata(np.asarray(s, float)) + 1.0
    return float((r[lab].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def run(pool, trig, perm_tgt=None, K=0.5, prior=35.0):
    xs, ys, ds, pf = [], [], [], {}
    for Y in FOLDS:
        tr = pool[DY[pool] < Y]
        te = pool[DY[pool] == Y]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        p = fit(tr)
        x = make(te, p, "shift", pull=None)
        w = 1.0 / (1.0 + K)
        x = np.where(trig[te], w * x + (1 - w) * prior, x)
        t = TGT[te] if perm_tgt is None else perm_tgt.permutation(TGT[te])
        ok = ~np.isnan(x)
        xs.append(x[ok]); ys.append(t[ok]); ds.append(DEBUT[te][ok])
        pf[int(Y)] = rho(x[ok], t[ok])
    x, y, d = np.concatenate(xs), np.concatenate(ys), np.concatenate(ds)
    return {"rho": rho(x, y), "mean_fold": float(np.mean(list(pf.values()))),
            "auc_debut": AUC(x, d), "auc_contrib": AUC(x, y >= 3.0), "per_fold": pf}


pool = np.arange(N)
live = run(pool, PULL)
cand = run(pool, NS1)
print("\n=== A12 point estimates (full pool, forward-chained) ===")
for nm, r in (("live trigger", live), ("n_sources<=1", cand)):
    print(f"  {nm:>14}: rho {r['rho']:.4f}  mean-fold {r['mean_fold']:.4f}  "
          f"AUCdebut {r['auc_debut']:.4f}  AUCcontrib {r['auc_contrib']:.4f}")
print(f"  DELTA          : rho {cand['rho']-live['rho']:+.4f}  "
      f"mean-fold {cand['mean_fold']-live['mean_fold']:+.4f}  "
      f"AUCdebut {cand['auc_debut']-live['auc_debut']:+.4f}  "
      f"AUCcontrib {cand['auc_contrib']-live['auc_contrib']:+.4f}")
print("  per-fold rho delta: " + "  ".join(
    f"{y}:{cand['per_fold'][y]-live['per_fold'][y]:+.4f}" for y in sorted(live['per_fold'])))

# ---- zero-information control: permuted trigger, identical firing rate ----
rng = np.random.default_rng(3)
c = {"rho": [], "mf": [], "ad": [], "ac": []}
for _ in range(300):
    t = rng.permutation(NS1)
    r = run(pool, t)
    c["rho"].append(r["rho"] - live["rho"])
    c["mf"].append(r["mean_fold"] - live["mean_fold"])
    c["ad"].append(r["auc_debut"] - live["auc_debut"])
    c["ac"].append(r["auc_contrib"] - live["auc_contrib"])
print("\n  ZERO-INFORMATION CONTROL (trigger row-permuted, same firing rate, 300 draws):")
for k, lbl, obs in (("rho", "rho", cand['rho'] - live['rho']),
                    ("mf", "mean-fold", cand['mean_fold'] - live['mean_fold']),
                    ("ad", "AUC debut", cand['auc_debut'] - live['auc_debut']),
                    ("ac", "AUC contrib", cand['auc_contrib'] - live['auc_contrib'])):
    a = np.array(c[k])
    print(f"    {lbl:>12}: control mean {a.mean():+.4f} p95 {np.percentile(a,95):+.4f} "
          f"| observed {obs:+.4f} -> "
          f"{'CLEARS control' if obs > np.percentile(a,95) else 'FAILS control'}")

# ---- permutation null band (target shuffled within fold) ----
rngp = np.random.default_rng(19)
nl = {"rho": [], "ad": []}
for _ in range(250):
    a = run(pool, NS1, perm_tgt=rngp)
    b = run(pool, PULL, perm_tgt=rngp)
    nl["rho"].append(a["rho"] - b["rho"])
    nl["ad"].append(a["auc_debut"] - b["auc_debut"])
print("\n  permutation null band (target shuffled):")
for k, obs in (("rho", cand['rho'] - live['rho']),
               ("ad", cand['auc_debut'] - live['auc_debut'])):
    a = np.abs(np.array(nl[k]))
    print(f"    {k:>4}: null |d| p95 {np.percentile(a,95):.4f}  observed |d| {abs(obs):.4f} "
          f"-> {'OUTSIDE' if abs(obs) > np.percentile(a,95) else 'INSIDE (null)'}")

# ---- paired bootstrap with refit ----
rngb = np.random.default_rng(41)
d = {"rho": [], "mf": [], "ad": [], "ac": []}
for _ in range(600):
    b = pool[rngb.integers(0, N, N)]
    a1, a2 = run(b, NS1), run(b, PULL)
    d["rho"].append(a1["rho"] - a2["rho"])
    d["mf"].append(a1["mean_fold"] - a2["mean_fold"])
    d["ad"].append(a1["auc_debut"] - a2["auc_debut"])
    d["ac"].append(a1["auc_contrib"] - a2["auc_contrib"])
print("\n  paired bootstrap (train+test resampled, refit each draw), B=600:")
for k, lbl, obs in (("rho", "rho", cand['rho'] - live['rho']),
                    ("mf", "mean-fold", cand['mean_fold'] - live['mean_fold']),
                    ("ad", "AUC debut", cand['auc_debut'] - live['auc_debut']),
                    ("ac", "AUC contrib", cand['auc_contrib'] - live['auc_contrib'])):
    a = np.array(d[k])
    print(f"    {lbl:>12}: d {obs:+.4f}  CI95 [{np.percentile(a,2.5):+.4f},"
          f"{np.percentile(a,97.5):+.4f}]  MDE95 {2*1.96*a.std(ddof=1):.4f}  "
          f"P(>0) {np.mean(a>0):.3f}")

# ---- debuted-only cohort (the shipped eval's cut) ----
dp = np.where(DEBUT)[0]
l2, c2 = run(dp, PULL), run(dp, NS1)
print(f"\n  debuted-only cohort: d rho {c2['rho']-l2['rho']:+.4f}  "
      f"d mean-fold {c2['mean_fold']-l2['mean_fold']:+.4f}")
