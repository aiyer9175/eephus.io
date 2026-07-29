# SCRATCH (contact lane): k_rel / peak_k_rel collinearity measurement.
# READ-ONLY w.r.t. efv_model.py / efv_dataset.py -- a concurrent workflow owns them.
# Numpy replica of the PRODUCTION fit config:
#   train = full pool minus bust_recent, decision_year < Y, KM sample weights
#   test  = debuted rows, decision_year == Y
#   fit   = OLS(WAR~fv) + weighted ridge (alpha by 5-fold CV over a seeded permutation,
#           matching prospect_path._fit_ridge as shipped 2026-07-24) + linear calibration
#   score = (1-lam)*max(0,cons) + lam*max(-2, a + b*ridge); lam = LIVE efv_model.blend_lambda
#   metric= pooled OOS Spearman per side (the gate's "incremental feature" statistic)
#           + (side x origin) block-normalized pooled Spearman as the second metric.
# Run: python tools/_contact_lab.py <mode>
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

OUT = ROOT / "tools" / "_contact_out"
OUT.mkdir(exist_ok=True)

ORIGINS = (2020, 2021, 2022, 2023, 2024)     # 5 independent forward-chained time splits
LAM = {s: E.blend_lambda(s) for s in ("hit", "pit")}
SEED = 20260725
SIDES = ("hit", "pit")


# --------------------------------------------------------------------- data
def load_side(side: str):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text(encoding="utf-8"))
    prep = E._prep(raw, "target_censored", side)
    assert len(prep) == len(raw)
    keys, mono = E._feature_spec(side)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    deb = np.array([r["kind"] == "debuted" for r in prep])
    keep = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                     for r, o in zip(prep, raw)])
    return dict(side=side, X=X, y=y, w=w, fv=fv, dy=dy, deb=deb, keep=keep,
                keys=list(keys), mono=list(mono), idx={k: i for i, k in enumerate(keys)})


# --------------------------------------------------------------------- ridge (production)
def ridge_fit(X, y, w, bounds=None):
    """Weighted ridge, standardized, alpha by 5-fold CV on a seeded permutation.
    `bounds` = optional (lo, hi) arrays for a SIGN-CONSTRAINED fit (arm A)."""
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
        if bounds is None:
            WX = Xi * wi[:, None]
            A = WX.T @ Xi + alpha * np.eye(k)
            return np.linalg.solve(A, WX.T @ (y[idx] - b))
        # constrained: same objective as the weighted ridge normal equations, solved as a
        # bounded least-squares on the augmented system  [sqrt(W)Xs ; sqrt(alpha)I].
        from scipy.optimize import lsq_linear
        sw = np.sqrt(wi)
        A = np.vstack([Xi * sw[:, None], math.sqrt(alpha) * np.eye(k)])
        rhs = np.concatenate([(y[idx] - b) * sw, np.zeros(k)])
        r = lsq_linear(A, rhs, bounds=bounds, tol=1e-10, max_iter=200)
        return r.x

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    folds = np.array_split(order, 5)
    best = None
    for alpha in _ALPHAS:
        err_sum, w_sum = 0.0, 0.0
        for i in range(len(folds)):
            ho = folds[i]
            tri = np.concatenate([folds[j] for j in range(len(folds)) if j != i])
            if len(ho) == 0 or len(tri) == 0:
                continue
            b_tr = _wmean(tri)
            pred = Xs[ho] @ _wridge(tri, alpha, b_tr) + b_tr
            ww = w[ho]
            if ww.sum() > 0:
                err_sum += float(np.sum(np.abs(pred - y[ho]) * ww)); w_sum += float(ww.sum())
            else:
                err_sum += float(np.sum(np.abs(pred - y[ho]))); w_sum += float(len(ho))
        mae = (err_sum / w_sum) if w_sum > 0 else float("inf")
        if best is None or mae < best[0]:
            best = (mae, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    ww = _wridge(np.arange(n), alpha, b)
    return (mu, sd, ww, b, alpha)


def ridge_pred(m, X):
    mu, sd, ww, b = m[0], m[1], m[2], m[3]
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
    i, n = 0, len(s)
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


def block_rho(parts):
    PP, TT = [], []
    for b, p, t in parts:
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


# --------------------------------------------------------------------- ARMS
# An arm = (design transform fitted on TRAIN and applied to TEST, sign bounds).
# Transform signature: fit(Xtr, keys, mono) -> (apply(X) -> X', keys', mono')

def _idx(keys, k):
    return keys.index(k) if k in keys else None


def arm_base(Xtr, keys, mono, rng):
    return (lambda X: X), list(keys), list(mono), None


def _bounds_for(keys, mono, targets):
    lo = np.full(len(keys), -np.inf)
    hi = np.full(len(keys), np.inf)
    for k in targets:
        j = _idx(keys, k)
        if j is None:
            continue
        if mono[j] > 0:
            lo[j] = 0.0
        elif mono[j] < 0:
            hi[j] = 0.0
    return (lo, hi)


def arm_A1(Xtr, keys, mono, rng):
    """Enforce the DECLARED sign on k_rel only."""
    return (lambda X: X), list(keys), list(mono), _bounds_for(keys, mono, ["k_rel"])


def arm_A2(Xtr, keys, mono, rng):
    """Enforce the DECLARED sign on BOTH contact terms."""
    return (lambda X: X), list(keys), list(mono), _bounds_for(keys, mono, ["k_rel", "peak_k_rel"])


def arm_A_all(Xtr, keys, mono, rng):
    """Enforce the declared sign on EVERY feature with a declared direction."""
    return (lambda X: X), list(keys), list(mono), _bounds_for(
        keys, mono, [k for k, m in zip(keys, mono) if m])


def arm_B_drop(Xtr, keys, mono, rng):
    """Collapse the pair: drop peak_k_rel, keep k_rel."""
    j = _idx(keys, "peak_k_rel")
    cols = [i for i in range(len(keys)) if i != j]
    return (lambda X: X[:, cols]), [keys[i] for i in cols], [mono[i] for i in cols], None


def arm_B_dropk(Xtr, keys, mono, rng):
    """Collapse the pair the other way: drop k_rel, keep peak_k_rel."""
    j = _idx(keys, "k_rel")
    cols = [i for i in range(len(keys)) if i != j]
    return (lambda X: X[:, cols]), [keys[i] for i in cols], [mono[i] for i in cols], None


def arm_B_blend(Xtr, keys, mono, rng):
    """Collapse the pair into ONE blended contact rate: mean(k_rel, peak_k_rel)."""
    a, b = _idx(keys, "k_rel"), _idx(keys, "peak_k_rel")
    keep = [i for i in range(len(keys)) if i != b]
    ka = keep.index(a)

    def ap(X):
        Z = X[:, keep].copy()
        Z[:, ka] = 0.5 * (X[:, a] + X[:, b])
        return Z
    nk = [keys[i] for i in keep]
    nk[ka] = "contact_blend"
    return ap, nk, [mono[i] for i in keep], None


def arm_C_orth(Xtr, keys, mono, rng):
    """Orthogonalise: keep k_rel, replace peak_k_rel with resid(peak ~ current), the
    regression fitted on the TRAIN fold only."""
    a, b = _idx(keys, "k_rel"), _idx(keys, "peak_k_rel")
    c = ols_fit(Xtr[:, a], Xtr[:, b]) or (0.0, 0.0)

    def ap(X):
        Z = X.copy()
        Z[:, b] = X[:, b] - (c[0] + c[1] * X[:, a])
        return Z
    nk = list(keys)
    nk[b] = "peak_k_resid"
    return ap, nk, list(mono), None


def _perm_arm(col):
    """ZERO-INFORMATION CONTROL: row-permute the SAME column (identical marginal,
    no information). Permutation is drawn per replicate from the replicate rng."""
    def f(Xtr, keys, mono, rng):
        j = _idx(keys, col)
        perm = rng.permutation(Xtr.shape[0])   # placeholder; real perm applied in score_side

        def ap(X):
            return X
        return ap, list(keys), list(mono), None
    return f


ARMS = {
    "base":      arm_base,
    "A1_sign_k": arm_A1,
    "A2_sign_both": arm_A2,
    "A3_sign_all": arm_A_all,
    "B_drop_peak": arm_B_drop,
    "B_drop_k":   arm_B_dropk,
    "B_blend":    arm_B_blend,
    "C_orth":     arm_C_orth,
}
# arms implemented as a whole-column row-permutation of the FULL matrix (applied before
# the forward chain, so train and test share the scrambled column) -- the gate's
# zero-information control.
PERM_ARMS = {"ctrl_perm_peak": "peak_k_rel", "ctrl_perm_k": "k_rel"}


# --------------------------------------------------------------------- one pass
def score_side(D, arm, sel=None, perm_col=None, rng=None, origins=ORIGINS):
    """Forward-chained OOS scores for one side under `arm`. Returns (origin, pred, target)."""
    X, y, w, fv, dy, deb, keep = D["X"], D["y"], D["w"], D["fv"], D["dy"], D["deb"], D["keep"]
    keys, mono = D["keys"], D["mono"]
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = X[sel], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps = deb[sel], keep[sel]
    if perm_col is not None:
        j = keys.index(perm_col)
        Xs = Xs.copy()
        Xs[:, j] = Xs[rng.permutation(len(ys)), j]
    lam = LAM[D["side"]]
    fn = ARMS[arm]
    B, P, T = [], [], []
    for yr in origins:
        tr = np.flatnonzero(keeps & (dys < yr))
        te = np.flatnonzero(debs & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        ap, nk, nm, bounds = fn(Xs[tr], keys, mono, rng)
        Xtr, Xte = ap(Xs[tr]), ap(Xs[te])
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xtr, ys[tr], ws[tr], bounds=bounds)
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, Xtr), ys[tr])
        mod = np.maximum(-2.0, a + b * ridge_pred(rg, Xte))
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr))
        P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te])
    if not P:
        return None
    return (np.concatenate(B), np.concatenate(P), np.concatenate(T))


def per_origin_rho(r):
    b, p, t = r
    return {int(yr): rho(p[b == yr], t[b == yr]) for yr in np.unique(b)}


# --------------------------------------------------------------------- modes
def diag():
    """Collinearity + fitted-vs-declared sign audit. No bootstrap."""
    rep = {}
    for side in SIDES:
        D = load_side(side)
        keys, mono = D["keys"], D["mono"]
        tr = np.flatnonzero(D["keep"])                     # production TRAIN frame
        X = D["X"][tr]
        # full-window standardized ridge (matches efv_model._feature_diagnostics)
        rg = ridge_fit(X, D["y"][tr], D["w"][tr])
        wts = dict(zip(keys, [round(float(v), 3) for v in rg[2]]))
        signs = []
        for k, m in zip(keys, mono):
            if not m:
                continue
            fw = wts[k]
            if fw * m < 0:
                signs.append({"feature": k, "declared": int(m), "fitted_std_w": fw})
        # collinearity
        a, b = keys.index("k_rel"), keys.index("peak_k_rel")
        r = float(np.corrcoef(X[:, a], X[:, b])[0, 1])
        # VIF over the full shipped design
        Z = (X - X.mean(0)) / np.where(X.std(0) == 0, 1.0, X.std(0))
        vif = {}
        for k in ("k_rel", "peak_k_rel"):
            j = keys.index(k)
            others = [i for i in range(len(keys)) if i != j]
            A = np.column_stack([Z[:, others], np.ones(len(Z))])
            coef, *_ = np.linalg.lstsq(A, Z[:, j], rcond=None)
            resid = Z[:, j] - A @ coef
            r2 = 1.0 - float(resid.var()) / float(Z[:, j].var())
            vif[k] = {"r2_on_all_others": round(r2, 4),
                      "vif": round(1.0 / max(1e-9, 1 - r2), 3)}
        # pairwise-only VIF (the two contact terms alone)
        pair_vif = round(1.0 / max(1e-9, 1 - r * r), 3)
        # per-side test-frame correlation too
        te = np.flatnonzero(D["deb"] & np.isin(D["dy"], ORIGINS))
        r_te = float(np.corrcoef(D["X"][te][:, a], D["X"][te][:, b])[0, 1])
        rep[side] = {
            "n_train_frame": int(len(tr)),
            "alpha": rg[4],
            "ridge_std_weights": wts,
            "declared_sign_violations": signs,
            "corr_k_peak_train": round(r, 4),
            "corr_k_peak_test": round(r_te, 4),
            "shared_variance_pct": round(100 * r * r, 1),
            "pairwise_vif": pair_vif,
            "vif_full_design": vif,
            "sd_k_rel": round(float(X[:, a].std()), 4),
            "sd_peak_k_rel": round(float(X[:, b].std()), 4),
            "std_w_k": wts["k_rel"], "std_w_peak": wts["peak_k_rel"],
            "net_std_w": round(wts["k_rel"] + wts["peak_k_rel"], 3),
        }
        # how much the two terms cancel PER PLAYER on the live/served scale
        zk = (X[:, a] - X[:, a].mean()) / (X[:, a].std() or 1)
        zp = (X[:, b] - X[:, b].mean()) / (X[:, b].std() or 1)
        ck, cp = wts["k_rel"] * zk, wts["peak_k_rel"] * zp
        rep[side]["contrib_sd_k"] = round(float(ck.std()), 4)
        rep[side]["contrib_sd_peak"] = round(float(cp.std()), 4)
        rep[side]["contrib_sd_sum"] = round(float((ck + cp).std()), 4)
        rep[side]["cancellation_pct"] = round(
            100 * (1 - float((ck + cp).std()) / (float(ck.std()) + float(cp.std()))), 1)
    (OUT / "diag.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


def point():
    """Point estimates for every arm, pooled + per-origin."""
    rep = {}
    rng = np.random.default_rng(SEED)
    for side in SIDES:
        D = load_side(side)
        rep[side] = {}
        for name in ARMS:
            r = score_side(D, name, rng=rng)
            rep[side][name] = {"pooled_rho": round(rho(r[1], r[2]), 4), "n": int(len(r[2])),
                               "block_rho": round(block_rho([r]), 4),
                               "per_origin": {k: round(v, 4) for k, v in per_origin_rho(r).items()}}
        for name, col in PERM_ARMS.items():
            r = score_side(D, "base", perm_col=col, rng=np.random.default_rng(SEED + 11))
            rep[side][name] = {"pooled_rho": round(rho(r[1], r[2]), 4), "n": int(len(r[2])),
                               "block_rho": round(block_rho([r]), 4),
                               "per_origin": {k: round(v, 4) for k, v in per_origin_rho(r).items()}}
        base = rep[side]["base"]["pooled_rho"]
        for name in rep[side]:
            rep[side][name]["delta_vs_base"] = round(rep[side][name]["pooled_rho"] - base, 4)
            rep[side][name]["mean_origin_delta"] = round(
                float(np.mean([rep[side][name]["per_origin"][k] - rep[side]["base"]["per_origin"][k]
                               for k in rep[side]["base"]["per_origin"]])), 4)
    (OUT / "point.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


def boot(B=400):
    """PAIRED bootstrap: resample players with replacement within (side, decision_year)
    over the WHOLE pool (train AND test) and REFIT every arm on the same replicate."""
    D = {s: load_side(s) for s in SIDES}
    strata = {s: [np.flatnonzero(D[s]["dy"] == v) for v in np.unique(D[s]["dy"])] for s in SIDES}
    names = list(ARMS) + list(PERM_ARMS)
    store = {s: {n: [] for n in names} for s in SIDES}
    rng = np.random.default_rng(SEED)
    t0 = time.time()
    for bi in range(B + 1):
        for s in SIDES:
            sel = (np.arange(len(D[s]["y"])) if bi == 0 else
                   np.concatenate([rng.choice(ix, size=len(ix), replace=True)
                                   for ix in strata[s]]))
            for n in names:
                if n in PERM_ARMS:
                    r = score_side(D[s], "base", sel=sel, perm_col=PERM_ARMS[n], rng=rng)
                else:
                    r = score_side(D[s], n, sel=sel, rng=rng)
                store[s][n].append(float("nan") if r is None else rho(r[1], r[2]))
        if bi % 25 == 0:
            print(bi, round(time.time() - t0, 1), "s", flush=True)
    json.dump(store, open(OUT / "boot.json", "w"))
    print("done", B, round(time.time() - t0, 1), "s")


def perm_null(N=200):
    """PERMUTATION NULL BAND for the same quantity: delta(pooled rho) when the SAME
    column is row-permuted, N independent permutations, full sample."""
    rep = {}
    for s in SIDES:
        D = load_side(s)
        base = rho(*score_side(D, "base", rng=np.random.default_rng(SEED))[1:])
        rep[s] = {"base": round(base, 4)}
        for col in ("peak_k_rel", "k_rel"):
            ds = []
            for i in range(N):
                r = score_side(D, "base", perm_col=col,
                               rng=np.random.default_rng(SEED + 1000 + i))
                ds.append(rho(r[1], r[2]) - base)
            ds = np.array(ds)
            rep[s]["perm_" + col] = {
                "n": N, "mean": round(float(ds.mean()), 4), "sd": round(float(ds.std()), 4),
                "p2.5": round(float(np.percentile(ds, 2.5)), 4),
                "p97.5": round(float(np.percentile(ds, 97.5)), 4),
                "abs_p95": round(float(np.percentile(np.abs(ds), 95)), 4)}
        print(s, json.dumps(rep[s]), flush=True)
    (OUT / "perm_null.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")


def report():
    st = json.load(open(OUT / "boot.json"))
    rep = {}
    for s in SIDES:
        rep[s] = {}
        base = np.array(st[s]["base"], dtype=float)
        for n, v in st[s].items():
            v = np.array(v, dtype=float)
            d = v[1:] - base[1:]
            d = d[~np.isnan(d)]
            rep[s][n] = {
                "point_rho": round(float(v[0]), 4),
                "point_delta": round(float(v[0] - base[0]), 4),
                "boot_mean_delta": round(float(d.mean()), 4),
                "sd": round(float(d.std()), 4),
                "ci95": [round(float(np.percentile(d, 2.5)), 4),
                         round(float(np.percentile(d, 97.5)), 4)],
                "P(improves)": round(float((d > 0).mean()), 3),
                "B": int(len(d))}
        rep[s]["_boot_sd_of_base_rho"] = round(float(np.nanstd(base[1:])), 4)
    (OUT / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


def signs(B=300):
    """SYSTEMATIC CHECK: for every shipped feature with a declared monotone direction,
    is the FITTED standardized weight's sign stable, and does it agree with the
    declaration? Fits (a) the full-window production train frame, (b) each
    forward-chained fold's train set, (c) B stratified bootstrap resamples."""
    rep = {}
    rng = np.random.default_rng(SEED)
    for side in SIDES:
        D = load_side(side)
        keys, mono = D["keys"], D["mono"]
        tr = np.flatnonzero(D["keep"])
        full = ridge_fit(D["X"][tr], D["y"][tr], D["w"][tr])[2]
        folds = {}
        for yr in ORIGINS:
            ix = np.flatnonzero(D["keep"] & (D["dy"] < yr))
            if len(ix) < 60:
                continue
            folds[yr] = ridge_fit(D["X"][ix], D["y"][ix], D["w"][ix])[2]
        strata = [np.flatnonzero(D["dy"][tr] == v) for v in np.unique(D["dy"][tr])]
        draws = []
        for _ in range(B):
            sel = tr[np.concatenate([rng.choice(ix, size=len(ix), replace=True)
                                     for ix in strata])]
            draws.append(ridge_fit(D["X"][sel], D["y"][sel], D["w"][sel])[2])
        draws = np.array(draws)
        rep[side] = {}
        for j, (k, m) in enumerate(zip(keys, mono)):
            col = draws[:, j]
            agree = float(np.mean(col * m > 0)) if m else None
            rep[side][k] = {
                "declared": int(m),
                "full_window_w": round(float(full[j]), 3),
                "fold_w": {int(y): round(float(v[j]), 3) for y, v in folds.items()},
                "boot_mean": round(float(col.mean()), 3),
                "boot_sd": round(float(col.std()), 3),
                "boot_ci95": [round(float(np.percentile(col, 2.5)), 3),
                              round(float(np.percentile(col, 97.5)), 3)],
                "P(sign agrees with declared)": (None if agree is None else round(agree, 3)),
                "CONTRADICTS": bool(m and full[j] * m < 0),
            }
    (OUT / "signs.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    for s in SIDES:
        print("=====", s)
        for k, v in rep[s].items():
            if not v["declared"]:
                continue
            flag = "  <-- CONTRADICTS DECLARED" if v["CONTRADICTS"] else ""
            print("  %-15s declared %+d  fitted %+.3f  boot %+.3f+-%.3f  P(agree)=%.2f%s"
                  % (k, v["declared"], v["full_window_w"], v["boot_mean"], v["boot_sd"],
                     v["P(sign agrees with declared)"], flag))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "diag"
    t0 = time.time()
    if mode == "diag":
        diag()
    elif mode == "point":
        point()
    elif mode == "boot":
        boot(int(sys.argv[2]) if len(sys.argv) > 2 else 400)
    elif mode == "perm":
        perm_null(int(sys.argv[2]) if len(sys.argv) > 2 else 200)
    elif mode == "report":
        report()
    elif mode == "signs":
        signs(int(sys.argv[2]) if len(sys.argv) > 2 else 300)
    print("elapsed", round(time.time() - t0, 1), "s", file=sys.stderr)
