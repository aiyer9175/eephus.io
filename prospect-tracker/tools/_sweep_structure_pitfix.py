# SCRATCH: can the pitcher age-sign correctness fix be had WITHOUT importing the
# missing-block / mlbam-id-resolution channel? Read-only. Run: python tools/_sweep_structure_pitfix.py
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import _sweep_structure as S
from _frontier_ablate import ridge_fit, ridge_pred, ols_fit, lincal, rho

s = "pit"; d = S.D[s]; base = list(S.KEYS[s])
VAR = {"base": base,
       "A_level_rank": base + ["level_rank"],
       "B_level_neutral": base + ["level_rank_neutral"],
       "C_neutral_plus_ind": base + ["level_rank_neutral", "milb_obs"],
       "D_ind_only": base + ["milb_obs"]}
tr = np.flatnonzero(d["keep"])
print("=== pitcher age-sign fix variants ===\nfull-window fitted 'age' weight (declared -1):")
for n, kk in VAR.items():
    X = d["X"][:, [d["idx"][k] for k in kk]]
    w = dict(zip(kk, ridge_fit(X[tr], d["y"][tr], d["w"][tr])[2]))
    print(f"  {n:<22} age={w['age']:+.4f}   " +
          "  ".join(f"{k}={w[k]:+.4f}" for k in kk if k not in base))
print("\nper-origin forward-chained refit, 'age' weight (sign stability):")
for n, kk in VAR.items():
    row = []
    for yr in S.ORIGINS:
        t2 = np.flatnonzero(d["keep"] & (d["dy"] < yr))
        X = d["X"][:, [d["idx"][k] for k in kk]]
        row.append(dict(zip(kk, ridge_fit(X[t2], d["y"][t2], d["w"][t2])[2]))["age"])
    print(f"  {n:<22} " + " ".join(f"{v:+.4f}" for v in row) +
          f"   negative in {sum(1 for v in row if v < 0)}/5")


def score_full(Xa, sel):
    y, w, fv, dy, deb, keep, has = (d["y"], d["w"], d["fv"], d["dy"], d["deb"],
                                    d["keep"], d["has"])
    Xs, ys, ws, fvs, dys = Xa[sel], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps, hass = deb[sel], keep[sel], has[sel]
    lam = S.LAM[s]; P, L, H = [], [], []
    for yr in S.ORIGINS:
        t2 = np.flatnonzero(keeps & (dys < yr)); te = np.flatnonzero(keeps & (dys == yr))
        if len(te) < 15 or len(t2) < 60:
            continue
        o = ols_fit(fvs[t2], ys[t2]); rg = ridge_fit(Xs[t2], ys[t2], ws[t2])
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, Xs[t2]), ys[t2])
        P.append((1 - lam) * np.maximum(0.0, o[0] + o[1] * fvs[te]) +
                 lam * np.maximum(-2.0, a + b * ridge_pred(rg, Xs[te])))
        L.append(debs[te]); H.append(hass[te])
    return np.concatenate(P), np.concatenate(L), np.concatenate(H)


X = {n: d["X"][:, [d["idx"][k] for k in kk]] for n, kk in VAR.items()}
strata = [np.flatnonzero(d["dy"] == v) for v in np.unique(d["dy"])]
rng = np.random.default_rng(909); B = 500
st = {n: {"rho": [], "auc_obs": []} for n in VAR}
t0 = time.time()
for bi in range(B + 1):
    sel = (np.arange(len(d["y"])) if bi == 0 else
           np.concatenate([rng.choice(ix, size=len(ix), replace=True) for ix in strata]))
    for n in VAR:
        r = S.score(s, X[n], sel=sel); f = score_full(X[n], sel)
        st[n]["rho"].append(rho(r[1], r[2]) if r else np.nan)
        st[n]["auc_obs"].append(S.auc(f[0][f[2]], f[1][f[2]]))
print("\npaired bootstrap B=%d (pit pooled-rho MDE95 0.016); auc_obs = leak-scrubbed" % B)
print(f"{'variant':<22} {'d_rho':>9} {'CI95':>20} {'P>0':>6} "
      f"{'d_auc_obs':>10} {'CI95':>20} {'P>0':>6}")
for n in VAR:
    if n == "base":
        print(f"{'base':<22} rho {st[n]['rho'][0]:.4f}   auc_obs {st[n]['auc_obs'][0]:.4f}")
        continue
    cells = []
    for k in ("rho", "auc_obs"):
        dd = np.array(st[n][k]) - np.array(st["base"][k]); pt = dd[0]
        dd = dd[1:][~np.isnan(dd[1:])]
        lo, hi = np.percentile(dd, [2.5, 97.5])
        cells.append(f"{pt:+9.4f} [{lo:+7.4f},{hi:+7.4f}] {float((dd > 0).mean()):6.3f}")
    print(f"{n:<22} " + " ".join(cells))
print("elapsed", round(time.time() - t0, 1), "s")
