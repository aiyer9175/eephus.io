# SCRATCH: what each archetype mechanism does to the SERVED board, and to
# Enrique Bradfield Jr specifically. Replicates efv_score.run_live's headline:
#   rank_war = (1-lam)*max(0, ols(fv_effective)) + lam*max(-2, a + b*ridge)
#   grade    = rank-preserving quantile map of rank_war onto the sorted
#              consensus_fv of the live pool
# (the multiplicative live tilts -- injury / Statcast / age / role -- are
# arm-invariant and omitted, so these are ARM DELTAS on the pre-tilt grade.)
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                     # noqa: E402
import efv_dataset as ED                  # noqa: E402
import _arch_MECH as M                    # noqa: E402

SIDE = sys.argv[1] if len(sys.argv) > 1 else "hit"
WHO = "enrique_bradfield_jr"

keys, _ = E._feature_spec(SIDE)
axes = M.ARCH_AXES[SIDE]
train = M.load(SIDE, "production")
D = M.arrays(train, keys, axes)
lam = E.blend_lambda(SIDE)

live = [r for r in json.loads(ED.live_matrix_path(SIDE).read_text(encoding="utf-8"))
        if r.get("milb") and r.get("consensus_fv_raw") is not None]
Lx = np.array([[E._vec(r, SIDE).get(k, 0.0) for k in keys] for r in live], float)
La = np.array([[E._vec(r, SIDE).get(k, 0.0) for k in axes] for r in live], float)
Lfv_disp = np.array([float(r["consensus_fv_raw"]) for r in live], float)
Lfv_anch = np.array([float(r.get("fv_effective") if r.get("fv_effective") is not None
                           else r["consensus_fv_raw"]) for r in live], float)
Lkey = [r["player_key"] for r in live]
target = np.sort(Lfv_disp)
m = len(live)
idx_who = Lkey.index(WHO) if WHO in Lkey else None
print(f"{SIDE}: live scored pool m={m}  train n={len(train)}  lam={lam}")


def grade_of(rank_war):
    order = sorted(range(m), key=lambda i: (rank_war[i], Lkey[i]))
    g = np.empty(m)
    for pos, i in enumerate(order):
        p = pos / (m - 1) if m > 1 else 0.0
        lo = int(p * (m - 1)); hi = min(m - 1, lo + 1); fr = p * (m - 1) - lo
        g[i] = target[lo] * (1 - fr) + target[hi] * fr
    rk = np.empty(m, int)
    for pos, i in enumerate(order):
        rk[i] = m - pos            # 1 = best
    return g, rk


def fit_arm(arm, ctx):
    X, y, w, fv, tr = D["X"], D["y"], D["w"], D["fv"], D["tr"]
    Xtr, Lx2 = X, Lx
    std_mask = None
    labs = None
    if arm == "E1_STD_TR":
        std_mask = tr > 0.5
    elif arm == "E2_NOTRACK":
        Xtr = np.hstack([X, (1.0 - tr)[:, None]])
        Lx2 = np.hstack([Lx, np.zeros((m, 1))])          # every live row has a track record
    elif arm == "E3_TR_ONLY":
        keep = tr > 0.5
        Xtr = X[keep]; y = y[keep]; w = w[keep]; fv = fv[keep]
    elif arm in ("M1_ARCH", "M3_CONDCAL", "M4_SHRINK"):
        km = M.kmeans_fit(D["A"], ctx["k"], seed=ctx["seed"])
        labs = (M.kmeans_assign(km, D["A"]), M.kmeans_assign(km, La))
        if arm == "M1_ARCH":
            Xtr = np.hstack([X, M.onehot(labs[0], ctx["k"])])
            Lx2 = np.hstack([Lx, M.onehot(labs[1], ctx["k"])])
    rg = M.ridge_fit(Xtr, y, w, std_mask=std_mask)
    ols = M.ols_fit(fv, y)
    a, b = M.lin_cal(M.ridge_pred(rg, Xtr), y)
    model = np.maximum(-2.0, a + b * M.ridge_pred(rg, Lx2))
    cons = np.maximum(0.0, ols[0] + ols[1] * Lfv_anch)
    lamv = np.full(m, lam)
    if arm == "M3_CONDCAL":
        ptr = np.maximum(-2.0, a + b * M.ridge_pred(rg, Xtr))
        for g in range(ctx["k"]):
            mg = labs[0] == g
            if mg.sum() < 30:
                continue
            ag, bg = M.lin_cal(ptr[mg], y[mg])
            sel = labs[1] == g
            if sel.any():
                model[sel] = np.maximum(-2.0, ag + bg * model[sel])
    if arm == "M4_SHRINK":
        lg = M._stratum_lambda(D, np.arange(len(D["y"])), labs[0], ctx["k"], lam, ctx)
        lamv = np.array([lg.get(int(g), lam) for g in labs[1]])
    if arm == "M2_COMP":
        mu, sd = D["A"].mean(0), D["A"].std(0).copy(); sd[sd == 0] = 1.0
        kp, _d = M.knn_pred((D["A"] - mu) / sd, D["y"], (La - mu) / sd, k=ctx["knn_k"])
        model = 0.35 * kp + 0.65 * model      # omega at the top of the OOF-selected range
    return (1 - lamv) * cons + lamv * model


CTX = {"k": 6, "seed": 11, "knn_k": 20, "comp_axes": D["A"]}
base_rw = fit_arm("BASE", CTX)
bg, brk = grade_of(base_rw)
print(f"\nBASE pre-tilt grade for {WHO}: {bg[idx_who]:.2f} "
      f"(consensus {Lfv_disp[idx_who]:.2f}, board rank {brk[idx_who]} of {m})")

print(f"\n{'arm':<14}{'grade':>8}{'d_grade':>9}{'rank':>7}{'d_rank':>8}"
      f"{'medianAbsMove':>15}{'p90Move':>9}")
for arm in ("E1_STD_TR", "E2_NOTRACK", "E3_TR_ONLY", "M1_ARCH", "M2_COMP",
            "M3_CONDCAL", "M4_SHRINK"):
    rw = fit_arm(arm, CTX)
    g, rk = grade_of(rw)
    d = g - bg
    print(f"{arm:<14}{g[idx_who]:8.2f}{d[idx_who]:+9.2f}{rk[idx_who]:7d}"
          f"{rk[idx_who]-brk[idx_who]:+8d}{np.median(np.abs(d)):15.3f}"
          f"{np.percentile(np.abs(d), 90):9.3f}")

# --- who Bradfield's nearest archetype comps actually are ------------------
km = M.kmeans_fit(D["A"], CTX["k"], seed=CTX["seed"])
ltr, lte = M.kmeans_assign(km, D["A"]), M.kmeans_assign(km, La)
gb = int(lte[idx_who])
mg = ltr == gb
print(f"\nBradfield k-means archetype: cluster {gb}  train members={int(mg.sum())}  "
      f"mean 6yr WAR={D['y'][mg].mean():.2f}  bust rate(<0.5)={(D['y'][mg] < 0.5).mean():.3f}")
print("cluster sizes / mean WAR:",
      {int(g): (int((ltr == g).sum()), round(float(D['y'][ltr == g].mean()), 2))
       for g in range(CTX["k"])})
mu, sd = D["A"].mean(0), D["A"].std(0).copy(); sd[sd == 0] = 1.0
Z, zq = (D["A"] - mu) / sd, (La[idx_who] - mu) / sd
dist = np.sqrt(((Z - zq) ** 2).sum(1))
o = np.argsort(dist)[:15]
print("\n15 nearest profile comps (archetype space, full labeled pool):")
for i in o:
    print(f"   {train[i]['player_key']:<34}d={dist[i]:.2f}  6yrWAR={D['y'][i]:+.2f}  "
          f"consFV={D['fv'][i]:.0f}  {'debuted' if D['deb'][i] else 'never-MLB'}")
print(f"kNN(20) comp prediction for Bradfield: "
      f"{M.knn_pred(Z, D['y'], zq[None, :], k=20)[0][0]:.2f} WAR  |  "
      f"model leg BASE: {base_rw[idx_who]:.2f} rank_war")
