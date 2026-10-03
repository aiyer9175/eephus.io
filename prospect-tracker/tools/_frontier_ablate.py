# SCRATCH (frontier lane: SHIPPED-FEATURE ABLATION AUDIT). Read-only w.r.t. shipped code.
# Numpy replica of the PRODUCTION fit config under the Foundation "recommended evaluator":
#   train = full pool minus bust_recent, decision_year < Y, KM sample weights
#   test  = debuted rows, decision_year == Y
#   fit   = OLS(WAR~fv) + weighted ridge (alpha holdout, seeded) + linear calibration
#   score = (1-lam)*max(0,cons) + lam*max(-2, a + b*ridge);  lam PINNED (hit .85 / pit .54)
#   metric= block-normalized ((side, origin) percentile) pooled Spearman
# Run: python tools/_frontier_ablate.py <mode>
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as E                                        # noqa: E402 read-only
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED       # noqa: E402

ORIGINS = (2020, 2021, 2022, 2023, 2024)
GATE_ORIGINS = (2020, 2021, 2022, 2023)
LAM = {"hit": 0.85, "pit": 0.54}          # live served values (efv_model.blend_lambda)
SEED = 20260724

RIDGE_SEED = [_RIDGE_HOLDOUT_SEED]   # mutable: alpha-holdout seed sensitivity
KEYS = {s: E._feature_spec(s)[0] for s in ("hit", "pit")}
N_NOISE = 20


# --------------------------------------------------------------------- data
def load_side(side: str):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text(encoding="utf-8"))
    prep = E._prep(raw, "target_censored", side)
    assert len(prep) == len(raw)
    keys = list(KEYS[side])
    rng = np.random.default_rng(SEED + (7 if side == "pit" else 3))
    n = len(prep)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    debuted = np.array([r["kind"] == "debuted" for r in prep])
    keep_tr = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                        for r, o in zip(prep, raw)])
    # extra columns appended AFTER the shipped block: permuted twins + noise
    extra_names, extra_cols = [], []
    for j, k in enumerate(keys):                       # pairing-preserving placebo twins
        perm = rng.permutation(n)
        extra_names.append("~perm~" + k)
        extra_cols.append(X[perm, j])
    for j in range(N_NOISE):                           # zero-information controls
        extra_names.append("~noise~%d" % j)
        extra_cols.append(rng.standard_normal(n))
    Xa = np.column_stack([X] + extra_cols)
    names = keys + extra_names
    return dict(side=side, X=Xa, y=y, w=w, fv=fv, dy=dy, deb=debuted, keep=keep_tr,
                names=names, idx={k: i for i, k in enumerate(names)}, keys=keys)


# --------------------------------------------------------------------- primitives
def ridge_fit(X, y, w):
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

    order = np.random.default_rng(RIDGE_SEED[0]).permutation(n)
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
    mu, sd, ww, b = m
    return ((X - mu) / sd) @ ww + b


def ols_fit(x, y):
    if len(y) < 8:
        return None
    mx, my = x.mean(), y.mean()
    var = float(((x - mx) ** 2).sum())
    if var <= 0:
        return None
    b = float(((x - mx) * (y - my)).sum()) / var
    return (my - b * mx, b)


def lincal(pred, obs):
    if len(pred) < 50:
        return (0.0, 1.0)
    c = ols_fit(pred, obs)
    if c is None:
        return (0.0, 1.0)
    return (round(c[0], 4), round(c[1], 4))


def _rankavg(v):
    v = np.asarray(v, dtype=float)
    order = v.argsort(kind="mergesort")
    r = np.empty(len(v), dtype=float)
    r[order] = np.arange(1, len(v) + 1, dtype=float)
    s = v[order]
    i = 0
    n = len(s)
    while i < n:
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def rho(p, t):
    if len(p) < 8:
        return float("nan")
    rp, rt = _rankavg(p), _rankavg(t)
    rp = rp - rp.mean()
    rt = rt - rt.mean()
    d = math.sqrt(float((rp * rp).sum()) * float((rt * rt).sum()))
    return float((rp * rt).sum() / d) if d > 0 else float("nan")


# --------------------------------------------------------------------- one pass
def score_side(D, cols, sel=None, origins=ORIGINS, lam=None, train_frame="full", cal=True):
    """Forward-chained scores for one side. `sel` = row index subset (bootstrap resample)
    into D's arrays; None = all rows. Returns (blockid, pred, target) arrays."""
    X, y, w, fv, dy, deb, keep = D["X"], D["y"], D["w"], D["fv"], D["dy"], D["deb"], D["keep"]
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = X[sel][:, cols], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps = deb[sel], keep[sel]
    lam = LAM[D["side"]] if lam is None else lam
    trmask = keeps if train_frame == "full" else debs
    B, P, T = [], [], []
    for yr in origins:
        tr = np.flatnonzero(trmask & (dys < yr))
        te = np.flatnonzero(debs & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        if cal:
            a, b = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
            mod = np.maximum(-2.0, a + b * ridge_pred(rg, Xs[te]))
        else:
            mod = ridge_pred(rg, Xs[te])
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr))
        P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te])
    if not P:
        return None
    return (np.concatenate(B), np.concatenate(P), np.concatenate(T))


def block_rho(parts):
    """parts = list of (side_tag, blockid, pred, target). Percentile-normalize within
    (side, block) then pool and Spearman."""
    PP, TT = [], []
    for tag, b, p, t in parts:
        for yr in np.unique(b):
            m = b == yr
            if m.sum() < 8:
                continue
            n = int(m.sum())
            PP.append((_rankavg(p[m]) - 0.5) / n)
            TT.append((_rankavg(t[m]) - 0.5) / n)
    if not PP:
        return float("nan")
    return rho(np.concatenate(PP), np.concatenate(TT))


# --------------------------------------------------------------------- parity
def parity():
    print("=== PARITY: replica (gate config, no calibration, debuted train+test, 2020-23) "
          "vs shipped efv_model._run_eval ===")
    for side in ("hit", "pit"):
        D = load_side(side)
        cols = np.arange(len(D["keys"]))
        r = score_side(D, cols, origins=GATE_ORIGINS, train_frame="debuted", cal=False)
        b, p, t = r
        keys, mono = E._feature_spec(side)
        lam = E.blend_lambda(side)
        raw = json.loads((ROOT / "data" / ("xfv_pitcher_matrix.json" if side == "pit"
                                           else "xfv_hitter_matrix.json")).read_text("utf-8"))
        data = E._prep([x for x in raw if x["kind"] == "debuted"], "target_censored", side)
        ship = E._run_eval(data, "debuted_km", keys, mono, lam)["pooled_oos"]["blend"]
        print(f"  {side}: lam={LAM[side]} (live {lam})  replica n={len(t)} rho={rho(p,t):.4f}"
              f"   | shipped n={ship['n']} rho={ship['spearman']}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parity"
    t0 = time.time()
    if mode == "parity":
        parity()
    print("elapsed", round(time.time() - t0, 1), "s")
