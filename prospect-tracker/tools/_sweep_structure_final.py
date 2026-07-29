# SCRATCH: (1) LEAK-SCRUBBED AUC - the full-pool debut-discrimination AUC restricted to
# test rows that HAVE a milb block, because milb availability == mlbam-id resolution and
# an mlbam id is present for 99% of debuted rows vs 44-56% of busts.
# (2) tool_speed zero-information control: the SAME column row-permuted in place, which
# is the control the gate requires for an ablation (drop != zero-information).
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import _sweep_structure as S
from _frontier_ablate import ridge_fit, ridge_pred, ols_fit, lincal, rho

B = int(sys.argv[1]) if len(sys.argv) > 1 else 400
SEED = 4242


def score_full(side, Xa, sel):
    """Full-pool test frame; returns (pred, debut_label, has_milb) for test rows."""
    d = S.D[side]
    y, w, fv, dy, deb, keep, has = (d["y"], d["w"], d["fv"], d["dy"], d["deb"],
                                    d["keep"], d["has"])
    Xs, ys, ws, fvs, dys = Xa[sel], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps, hass = deb[sel], keep[sel], has[sel]
    lam = S.LAM[side]
    P, L, H = [], [], []
    for yr in S.ORIGINS:
        tr = np.flatnonzero(keeps & (dys < yr))
        te = np.flatnonzero(keeps & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
        mod = np.maximum(-2.0, a + b * ridge_pred(rg, Xs[te]))
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        P.append((1 - lam) * cons + lam * mod)
        L.append(debs[te]); H.append(hass[te])
    if not P:
        return None
    return np.concatenate(P), np.concatenate(L), np.concatenate(H)


ARMS = {"pit": ["base", "lvl_main", "milb_obs_ind", "lvl_x_age", "agerel_hinge"],
        "hit": ["base", "fv_hinge", "drop_tool_speed", "perm_tool_speed",
                "both_neutral_impute"]}

# permute-in-place control column for tool_speed
_rng = np.random.default_rng(SEED)
d = S.D["hit"]
j = d["idx"]["tool_speed"]
d["X"] = np.column_stack([d["X"], d["X"][_rng.permutation(len(d["y"])), j]])
d["names"] = d["names"] + ["tool_speed_perm"]
d["idx"]["tool_speed_perm"] = len(d["names"]) - 1
S.SPECIAL["perm_tool_speed"] = ("swap", ("tool_speed", "tool_speed_perm"))
S.CAND["hit"]["perm_tool_speed"] = ((lambda s: []), ())

X = {s: {a: S.build(s, a)[0] for a in ARMS[s]} for s in ARMS}
strata = {s: [np.flatnonzero(S.D[s]["dy"] == v) for v in np.unique(S.D[s]["dy"])]
          for s in ARMS}
rng = np.random.default_rng(SEED)
store = {s: {a: {"auc_all": [], "auc_obs": [], "rho_deb": []} for a in ARMS[s]}
         for s in ARMS}
t0 = time.time()
for bi in range(B + 1):
    for s in ARMS:
        sel = (np.arange(len(S.D[s]["y"])) if bi == 0 else
               np.concatenate([rng.choice(ix, size=len(ix), replace=True)
                               for ix in strata[s]]))
        for a in ARMS[s]:
            r = score_full(s, X[s][a], sel)
            rr = S.score(s, X[s][a], sel=sel)
            store[s][a]["auc_all"].append(S.auc(r[0], r[1]) if r else np.nan)
            store[s][a]["auc_obs"].append(
                S.auc(r[0][r[2]], r[1][r[2]]) if r is not None and r[2].sum() > 20 else np.nan)
            store[s][a]["rho_deb"].append(rho(rr[1], rr[2]) if rr else np.nan)
    if bi % 100 == 0:
        print(" ", bi, round(time.time() - t0, 1), "s", flush=True)

print("\n=== LEAK-SCRUBBED AUC + tool_speed zero-information control  (B=%d) ===" % B)
print("auc_all = every test row (contaminated by mlbam-id resolution)")
print("auc_obs = test rows WITH a milb block only (the leak channel held constant)\n")
for s in ARMS:
    print(f"--- {s.upper()}")
    print(f"{'arm':<22} {'d_auc_all':>10} {'CI95':>20} {'d_auc_obs':>10} {'CI95':>20}"
          f" {'P>0':>6} {'d_rho_deb':>10} {'CI95':>20}")
    for a in ARMS[s]:
        if a == "base":
            b = {k: np.array(store[s]["base"][k], float) for k in store[s]["base"]}
            print(f"{'base':<22} auc_all {b['auc_all'][0]:.4f}   "
                  f"auc_obs {b['auc_obs'][0]:.4f}   rho_deb {b['rho_deb'][0]:.4f}")
            continue
        out = []
        for k in ("auc_all", "auc_obs", "rho_deb"):
            dd = np.array(store[s][a][k], float) - np.array(store[s]["base"][k], float)
            pt = dd[0]
            dd = dd[1:][~np.isnan(dd[1:])]
            lo, hi = np.percentile(dd, [2.5, 97.5])
            out.append((pt, lo, hi, float((dd > 0).mean())))
        print(f"{a:<22} {out[0][0]:+10.4f} [{out[0][1]:+7.4f},{out[0][2]:+7.4f}]"
              f" {out[1][0]:+10.4f} [{out[1][1]:+7.4f},{out[1][2]:+7.4f}] {out[1][3]:6.3f}"
              f" {out[2][0]:+10.4f} [{out[2][1]:+7.4f},{out[2][2]:+7.4f}]")
json.dump({s: {a: {k: list(map(float, v)) for k, v in d2.items()}
               for a, d2 in store[s].items()} for s in store},
          open(ROOT / "tools" / "_sweep_out" / "final.json", "w"))
