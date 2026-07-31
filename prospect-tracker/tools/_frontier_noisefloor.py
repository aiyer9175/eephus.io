# SCRATCH (not shipped): noise-floor instrument for the shipped eFV gate.
# Replicates efv_model._run_eval's forward-chained protocol in numpy so it can be
# refit thousands of times. Verifies bit-parity against the shipped path first.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as E                      # noqa: E402  (read-only use)
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED, _fit_ridge, _predict, _spearman  # noqa: E402

SCORED_YEARS = E.SCORED_YEARS


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def load(side: str, cut: str):
    rows = json.loads((ROOT / "data" / (f"xfv_pitcher_matrix.json" if side == "pit"
                                        else "xfv_hitter_matrix.json")).read_text("utf-8"))
    if cut == "debuted_km":
        raw = [r for r in rows if r["kind"] == "debuted"]
    elif cut == "full_pool_km":
        raw = [r for r in rows if not (r["kind"] == "bust" and r.get("bust_recent"))]
    else:
        raise ValueError(cut)
    return E._prep(raw, "target_censored", side)


def arrays(data, keys):
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in data], dtype=float)
    y = np.array([r["target"] for r in data], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in data]), 1e-3, None)
    fv = np.array([r["fv"] for r in data], dtype=float)
    dy = np.array([r["decision_year"] for r in data], dtype=int)
    return X, y, w, fv, dy


# --------------------------------------------------------------------------
# model primitives (faithful re-implementations)
# --------------------------------------------------------------------------
def ridge_fit(X, y, w):
    """Byte-faithful re-implementation of prospect_path._fit_ridge on arrays."""
    n = len(y)
    if n < 40:
        return None
    k = X.shape[1]
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = sd.copy()
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd

    def _wmean(idx):
        ww = w[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        A = WX.T @ Xi + alpha * np.eye(k)
        return np.linalg.solve(A, WX.T @ (y[idx] - b))

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    kk = max(1, n // 5)
    ho, tri = order[:kk], order[kk:]
    b_tr = _wmean(tri)
    best = None
    for alpha in _ALPHAS:
        ww = _wridge(tri, alpha, b_tr)
        pred = Xs[ho] @ ww + b_tr
        mae = (float(np.average(np.abs(pred - y[ho]), weights=w[ho]))
               if w[ho].sum() > 0 else float(np.abs(pred - y[ho]).mean()))
        if best is None or mae < best[0]:
            best = (mae, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    ww = _wridge(np.arange(n), alpha, b)
    return (mu, sd, ww, b)


def ridge_pred(m, X):
    mu, sd, w, b = m
    return ((X - mu) / sd) @ w + b


def ols_fit(fv, y):
    n = len(y)
    if n < 8:
        return None
    mx, my = fv.mean(), y.mean()
    var = ((fv - mx) ** 2).sum()
    if var <= 0:
        return None
    b = ((fv - mx) * (y - my)).sum() / var
    return (my - b * mx, b)


def spear(a, b):
    if len(a) < 8:
        return np.nan
    ra, rb = rankdata(a), rankdata(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else np.nan


# --------------------------------------------------------------------------
# one forward-chained pass -> pooled predictions
# --------------------------------------------------------------------------
def fwd_chain(X, y, w, fv, dy, y_train=None, feat_cols=None):
    """Returns pooled (cons, ridge, target, fv) arrays over SCORED_YEARS folds.
    y_train lets the permutation null substitute shuffled TRAIN targets."""
    Xc = X if feat_cols is None else X[:, feat_cols]
    yt = y if y_train is None else y_train
    C, R, T, F = [], [], [], []
    for yr in SCORED_YEARS:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = ols_fit(fv[tr], yt[tr])
        rg = ridge_fit(Xc[tr], yt[tr], w[tr])
        if ols is None or rg is None:
            continue
        C.append(np.maximum(0.0, ols[0] + ols[1] * fv[te]))
        R.append(ridge_pred(rg, Xc[te]))
        T.append(y[te])
        F.append(fv[te])
    if not C:
        return None
    return (np.concatenate(C), np.concatenate(R), np.concatenate(T), np.concatenate(F))


def metrics(pooled, lam):
    c, r, t, fv = pooled
    b = (1 - lam) * c + lam * r
    out = {
        "n": len(t),
        "rho_base": spear(c, t), "rho_ridge": spear(r, t), "rho_blend": spear(b, t),
        "mae_base": float(np.abs(c - t).mean()), "mae_ridge": float(np.abs(r - t).mean()),
        "mae_blend": float(np.abs(b - t).mean()),
    }
    tier = np.round(fv / 5) * 5
    m45 = tier == 45
    out["t45_blend"] = spear(b[m45], t[m45]) if m45.sum() >= 15 else np.nan
    out["n45"] = int(m45.sum())
    out["d_rho_ridge"] = out["rho_ridge"] - out["rho_base"]
    out["d_rho_blend"] = out["rho_blend"] - out["rho_base"]
    out["d_mae_ridge"] = out["mae_ridge"] - out["mae_base"]
    out["d_mae_blend"] = out["mae_blend"] - out["mae_base"]
    return out


def blend_at(pooled, lam):
    c, r, t, fv = pooled
    b = (1 - lam) * c + lam * r
    tier = np.round(fv / 5) * 5
    m45 = tier == 45
    return (spear(b, t), spear(b[m45], t[m45]) if m45.sum() >= 15 else np.nan)


# --------------------------------------------------------------------------
def parity_check():
    """Confirm the numpy replica reproduces the shipped efv_model numbers."""
    print("=== PARITY CHECK vs shipped efv_model path ===")
    for side in ("hit", "pit"):
        keys, mono = E._feature_spec(side)
        lam = E.blend_lambda(side)
        for cut in ("debuted_km", "full_pool_km"):
            data = load(side, cut)
            X, y, w, fv, dy = arrays(data, keys)
            p = fwd_chain(X, y, w, fv, dy)
            m = metrics(p, lam)
            # shipped path
            ship = E._run_eval(data, cut, keys, mono, lam)["pooled_oos"]
            print(f"{side}/{cut} lam={lam} n={m['n']}(ship {ship['baseline']['n']})")
            for nm, k in (("baseline", "base"), ("ridge", "ridge"), ("blend", "blend")):
                print(f"   {nm:9s} replica rho={m['rho_'+k]:.4f} mae={m['mae_'+k]:.4f} "
                      f"| shipped rho={ship[nm]['spearman']} mae={ship[nm]['mae']}")


if __name__ == "__main__":
    t0 = time.time()
    parity_check()
    print("elapsed", round(time.time() - t0, 1), "s")
