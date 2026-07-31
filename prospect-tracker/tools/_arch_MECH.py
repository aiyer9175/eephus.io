# SCRATCH (not shipped): ARCHETYPE MECHANISM lab.
# Gates the four candidate mechanisms by which an "archetype" could enter eFV,
# plus the item-E population-mismatch control arm, under docs/EFV_GATE_STANDARD.md.
#
# Faithful numpy re-implementation of the shipped forward-chained protocol
# (prospect_path._fit_ridge with the CURRENT 5-fold alpha CV, _fit_ols_fv,
# _fit_linear_calibration) so it can be refit thousands of times.
#
# Serving convention matches efv_score.run_live (NOT efv_model._run_eval):
#   cons  = max(0, ols(fv))
#   model = max(-2, a + b*ridge_pred)          a,b = train-fit linear calibration
#   blend = (1-lam)*cons + lam*model
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as E                                        # noqa: E402
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED       # noqa: E402

FOLDS = (2019, 2020, 2021, 2022, 2023, 2024)     # 6 forward-chained splits
SHIPPED_FOLDS = (2020, 2021, 2022, 2023)         # efv_model.SCORED_YEARS

ARCH_AXES = {
    "hit": ["age", "age_rel_level", "level_rank", "k_rel", "obp_rel", "ops_rel",
            "tool_hit", "tool_speed", "pos_prem", "is_ifa", "is_college",
            "n_milb_seasons"],
    "pit": ["age", "age_rel_level", "level_rank", "k_rel", "bb_rel", "era_rel",
            "peak_k_rel", "tool_fb", "is_ifa", "is_college", "n_milb_seasons"],
}


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def load(side: str, cut: str = "production"):
    """production = the pool fit_production_stack actually fits (full minus recent busts)."""
    rows = json.loads((ROOT / "data" / ("xfv_pitcher_matrix.json" if side == "pit"
                                        else "xfv_hitter_matrix.json")).read_text("utf-8"))
    is_pit = side == "pit"
    if cut == "production":
        raw = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
               and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    elif cut == "debuted":
        raw = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
               and r["kind"] == "debuted"]
    else:
        raise ValueError(cut)
    data = E._prep(raw, "target_censored", side)
    by_key = {r["player_key"]: r for r in raw}
    for d in data:
        src = by_key[d["player_key"]]
        d["track"] = 1.0 if src.get("milb") else 0.0
        d["debuted"] = 1.0 if d["kind"] == "debuted" else 0.0
    return data


def arrays(data, keys, arch_keys):
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in data], float)
    A = np.array([[r["feats"].get(k, 0.0) for k in arch_keys] for r in data], float)
    return {
        "X": X, "A": A, "arch_cols": {k: i for i, k in enumerate(arch_keys)},
        "y": np.array([r["target"] for r in data], float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in data]), 1e-3, None),
        "fv": np.array([r["fv"] for r in data], float),
        "dy": np.array([r["decision_year"] for r in data], int),
        "tr": np.array([r["track"] for r in data], float),
        "deb": np.array([r["debuted"] for r in data], float),
    }


# --------------------------------------------------------------------------
# primitives (faithful to the shipped code as of 2026-07-25)
# --------------------------------------------------------------------------
def ridge_fit(X, y, w, std_mask=None):
    """prospect_path._fit_ridge, current 5-fold alpha CV.
    std_mask: optional boolean row mask used ONLY for mu/sd (item-E arm)."""
    n = len(y)
    if n < 40:
        return None
    k = X.shape[1]
    S = X if std_mask is None else X[std_mask]
    if len(S) < 20:
        S = X
    mu, sd = S.mean(axis=0), S.std(axis=0).copy()
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd

    def _wmean(idx):
        ww = w[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        A = WX.T @ Xi + alpha * np.eye(k)
        try:
            return np.linalg.solve(A, WX.T @ (y[idx] - b))
        except np.linalg.LinAlgError:
            return np.linalg.lstsq(A, WX.T @ (y[idx] - b), rcond=None)[0]

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    folds = np.array_split(order, 5)
    best = None
    for alpha in _ALPHAS:
        err = wsum = 0.0
        for i in range(len(folds)):
            ho = folds[i]
            tri = np.concatenate([folds[j] for j in range(len(folds)) if j != i])
            if len(ho) == 0 or len(tri) == 0:
                continue
            b_tr = _wmean(tri)
            pred = Xs[ho] @ _wridge(tri, alpha, b_tr) + b_tr
            ww = w[ho]
            if ww.sum() > 0:
                err += float(np.sum(np.abs(pred - y[ho]) * ww)); wsum += float(ww.sum())
            else:
                err += float(np.sum(np.abs(pred - y[ho]))); wsum += float(len(ho))
        mae = (err / wsum) if wsum > 0 else float("inf")
        if best is None or mae < best[0]:
            best = (mae, alpha)
    b = _wmean(np.arange(n))
    return (mu, sd, _wridge(np.arange(n), best[1], b), b)


def ridge_pred(m, X):
    mu, sd, w, b = m
    return ((X - mu) / sd) @ w + b


def ols_fit(fv, y):
    if len(y) < 8:
        return None
    mx, my = fv.mean(), y.mean()
    var = ((fv - mx) ** 2).sum()
    if var <= 0:
        return None
    b = ((fv - mx) * (y - my)).sum() / var
    return (my - b * mx, b)


def lin_cal(pred, y):
    """prospect_path._fit_linear_calibration (unweighted OLS y ~ a + b*pred)."""
    if len(y) < 8:
        return (0.0, 1.0)
    mx, my = pred.mean(), y.mean()
    var = ((pred - mx) ** 2).sum()
    if var <= 0:
        return (0.0, 1.0)
    b = ((pred - mx) * (y - my)).sum() / var
    return (my - b * mx, b)


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def _rank(v):
    v = np.asarray(v, float)
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v), float)
    sv = v[order]
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and sv[j + 1] == sv[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def spear(a, b):
    if len(a) < 8:
        return np.nan
    ra, rb = _rank(a) - (len(a) + 1) / 2.0, _rank(b) - (len(b) + 1) / 2.0
    den = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / den) if den else np.nan


def auc(score, lab):
    lab = np.asarray(lab, float)
    if lab.sum() < 5 or (1 - lab).sum() < 5:
        return np.nan
    r = _rank(score)
    n1, n0 = lab.sum(), (1 - lab).sum()
    return float((r[lab == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def metrics(pred, y, fv, blk, deb, tag=""):
    """pooled rho, block-rho (fold-block normalized), t45, discrimination AUC,
    plus PROPER SCORING on the WAR scale (MAE / RMSE / calibration slope+intercept)
    so level-only mechanisms are graded on level, not only on rank."""
    out = {"n": len(y), "rho": spear(pred, y), "auc": auc(pred, deb),
           "mae": float(np.abs(pred - y).mean()),
           "rmse": float(np.sqrt(((pred - y) ** 2).mean())),
           "bias": float((pred - y).mean())}
    ca = lin_cal(pred, y)
    out["cal_b"] = float(ca[1])                     # 1.0 = level-correct
    # Brier on realized bust (first-6yr WAR < 0.5), pred mapped through the
    # train-free logistic of its own pooled rank -> proper score, rank-invariant
    # part removed by construction so it grades LEVEL not order.
    out["brier"] = float(np.mean((np.clip(pred, 0, 6) / 6.0 - (y >= 0.5)) ** 2))
    # block-rho: within-block rank-uniformize both sides, then pool
    up, uy = np.empty(len(y)), np.empty(len(y))
    for b in np.unique(blk):
        m = blk == b
        if m.sum() < 3:
            up[m] = 0.5; uy[m] = 0.5; continue
        up[m] = _rank(pred[m]) / (m.sum() + 1.0)
        uy[m] = _rank(y[m]) / (m.sum() + 1.0)
    out["block_rho"] = spear(up, uy)
    m45 = (np.round(fv / 5.0) * 5.0) == 45
    out["t45"] = spear(pred[m45], y[m45]) if m45.sum() >= 15 else np.nan
    out["n45"] = int(m45.sum())
    return {(tag + k if tag else k): v for k, v in out.items()}


# --------------------------------------------------------------------------
# k-means (train-only fit, applied forward)
# --------------------------------------------------------------------------
def kmeans_fit(A, k, seed=11, iters=60):
    rng = np.random.default_rng(seed)
    mu, sd = A.mean(0), A.std(0).copy()
    sd[sd == 0] = 1.0
    Z = (A - mu) / sd
    # k-means++ init
    C = [Z[rng.integers(len(Z))]]
    for _ in range(k - 1):
        d = np.min(((Z[:, None, :] - np.array(C)[None]) ** 2).sum(-1), axis=1)
        p = d / d.sum() if d.sum() > 0 else np.full(len(Z), 1.0 / len(Z))
        C.append(Z[rng.choice(len(Z), p=p)])
    C = np.array(C)
    for _ in range(iters):
        lab = np.argmin(((Z[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        newC = np.array([Z[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return {"mu": mu, "sd": sd, "C": C, "k": k}


def kmeans_assign(km, A):
    Z = (A - km["mu"]) / km["sd"]
    return np.argmin(((Z[:, None, :] - km["C"][None]) ** 2).sum(-1), axis=1)


def kmeans_soft(km, A, tau=1.0):
    Z = (A - km["mu"]) / km["sd"]
    d = np.sqrt(((Z[:, None, :] - km["C"][None]) ** 2).sum(-1))
    e = np.exp(-d / max(tau, 1e-6))
    return e / np.clip(e.sum(1, keepdims=True), 1e-9, None)


def semantic_labels(D, idx):
    """HAND-DEFINED archetype strata (hitters). CIRCULARITY WARNING: the cut points
    come from an outcome table computed on resolved rows that OVERLAP these test
    folds, so this arm is descriptive only -- it is NOT a leakage-clean estimate."""
    A = D["A"]; cols = D["arch_cols"]
    age = A[idx, cols["age"]]
    lvl = A[idx, cols["level_rank"]]
    ops = A[idx, cols["ops_rel"]]
    tr = D["tr"][idx]
    lab = np.full(len(idx), 3, int)                 # 3 = everything else
    lab[(tr < 0.5)] = 2                             # 2 = no pro track record
    lab[(tr > 0.5) & (lvl >= 4.5) & (age >= 23.5) & (ops < 0)] = 0   # old AAA under-producer
    lab[(tr > 0.5) & (lvl >= 4.5) & (age <= 22.0) & (ops > 0)] = 1   # young AAA producer
    return lab


def make_labels(D, itr, ite, ctx, rng=None, shuffle=False):
    """Archetype membership. Fitted on TRAIN ONLY and applied forward."""
    if ctx.get("arch_mode") == "semantic":
        ltr, lte, k = semantic_labels(D, itr), semantic_labels(D, ite), 4
    else:
        km = kmeans_fit(D["A"][itr], ctx["k"], seed=ctx.get("seed", 11))
        ltr, lte, k = kmeans_assign(km, D["A"][itr]), kmeans_assign(km, D["A"][ite]), ctx["k"]
    if shuffle:
        ltr, lte = rng.permutation(ltr), rng.permutation(lte)
    return ltr, lte, k


def onehot(lab, k):
    M = np.zeros((len(lab), k))
    M[np.arange(len(lab)), lab] = 1.0
    return M[:, 1:]        # drop first level (ridge has an intercept b)


# --------------------------------------------------------------------------
# arms
# --------------------------------------------------------------------------
def _legs(Xtr, ytr, wtr, fvtr, Xte, fvte, std_mask=None):
    rg = ridge_fit(Xtr, ytr, wtr, std_mask=std_mask)
    ols = ols_fit(fvtr, ytr)
    if rg is None or ols is None:
        return None
    a, b = lin_cal(ridge_pred(rg, Xtr), ytr)
    cons = np.maximum(0.0, ols[0] + ols[1] * fvte)
    model = np.maximum(-2.0, a + b * ridge_pred(rg, Xte))
    return cons, model


def knn_pred(Ztr, ytr, Zte, k=20):
    """Inverse-distance kNN in standardized archetype space (efv_model._pred_comps
    generalized). Returns (pred, mean_nbr_distance) so thin neighbourhoods can be
    handled explicitly by the caller."""
    d = np.sqrt(((Zte[:, None, :] - Ztr[None]) ** 2).sum(-1))
    idx = np.argsort(d, axis=1)[:, :k]
    dn = np.take_along_axis(d, idx, 1)
    w = 1.0 / (dn + 1e-6)
    return (w * ytr[idx]).sum(1) / w.sum(1), dn.mean(1)


def run_arm(arm, D, folds, lam, rng=None, ctx=None):
    """Returns pooled (pred, y, fv, blk, deb, tr) over the forward-chained folds."""
    ctx = ctx or {}
    P, Y, F, B, Db, Tr = [], [], [], [], [], []
    X, A, y, w, fv, dy, tr, deb = (D["X"], D["A"], D["y"], D["w"], D["fv"],
                                   D["dy"], D["tr"], D["deb"])
    for yr in folds:
        itr = np.flatnonzero(dy < yr)
        ite = np.flatnonzero(dy == yr)
        if len(ite) < 15 or len(itr) < 60:
            continue
        Xtr, Xte = X[itr], X[ite]
        std_mask = None
        pred = None

        if arm == "BASE":
            pass
        elif arm == "E1_STD_TR":
            std_mask = tr[itr] > 0.5
        elif arm == "E1_CTRL":                       # random subset, same size
            n_tr = int((tr[itr] > 0.5).sum())
            m = np.zeros(len(itr), bool)
            m[rng.choice(len(itr), size=n_tr, replace=False)] = True
            std_mask = m
        elif arm in ("E2_NOTRACK", "E2_CTRL"):
            col_tr = (1.0 - tr[itr])[:, None]
            col_te = (1.0 - tr[ite])[:, None]
            if arm == "E2_CTRL":
                col_tr = rng.permutation(col_tr)
                col_te = rng.permutation(col_te)
            Xtr = np.hstack([Xtr, col_tr]); Xte = np.hstack([Xte, col_te])
        elif arm == "E2X_INTERACT":
            mkeys = ctx["milb_cols"]
            t_tr, t_te = tr[itr][:, None], tr[ite][:, None]
            Xtr = np.hstack([Xtr, 1.0 - t_tr, t_tr * Xtr[:, mkeys]])
            Xte = np.hstack([Xte, 1.0 - t_te, t_te * Xte[:, mkeys]])
        elif arm == "E3_TR_ONLY":
            keep = tr[itr] > 0.5
            if keep.sum() < 60:
                continue
            itr = itr[keep]
            Xtr = X[itr]
        elif arm == "E3_CTRL":
            n_tr = int((tr[itr] > 0.5).sum())
            if n_tr < 60:
                continue
            itr = rng.choice(itr, size=n_tr, replace=False)
            Xtr = X[itr]
        elif arm.startswith(("M1_ARCH", "M1_CTRL", "M1B_DIST", "M1B_CTRL")):
            if arm.startswith("M1B"):
                km = kmeans_fit(A[itr], ctx["k"], seed=ctx.get("seed", 11))
                Str = kmeans_soft(km, A[itr]); Ste = kmeans_soft(km, A[ite])
                if arm.startswith("M1B_CTRL"):
                    Str = Str[rng.permutation(len(itr))]
                    Ste = Ste[rng.permutation(len(ite))]
                Xtr = np.hstack([Xtr, Str[:, 1:]]); Xte = np.hstack([Xte, Ste[:, 1:]])
            else:
                ltr, lte, k = make_labels(D, itr, ite, ctx, rng,
                                          shuffle=arm.startswith("M1_CTRL"))
                Xtr = np.hstack([Xtr, onehot(ltr, k)]); Xte = np.hstack([Xte, onehot(lte, k)])

        legs = _legs(Xtr, y[itr], w[itr], fv[itr], Xte, fv[ite], std_mask=std_mask)
        if legs is None:
            continue
        cons, model = legs

        # ---- mechanisms that post-process the legs -------------------------
        if arm in ("M2_COMP", "M2_CTRL"):
            km_axes = ctx["comp_axes"]
            Atr, Ate = km_axes[itr], km_axes[ite]
            mu, sd = Atr.mean(0), Atr.std(0).copy(); sd[sd == 0] = 1.0
            Ztr, Zte = (Atr - mu) / sd, (Ate - mu) / sd
            kk = ctx.get("knn_k", 20)
            if arm == "M2_CTRL":
                # zero-information twin: same structure, neighbours drawn at random
                idx = rng.integers(0, len(itr), size=(len(ite), kk))
                kp = y[itr][idx].mean(1)
                dbar = np.full(len(ite), 1.0)
            else:
                kp, dbar = knn_pred(Ztr, y[itr], Zte, k=kk)
            # comp weight chosen OUT OF FOLD inside train (inner forward split)
            omega = ctx.get("omega")
            if omega is None:
                omega = _select_omega(D, itr, ctx, lam, rng, arm)
            # thin-neighbourhood guard: shrink omega where comps are far away
            thin = ctx.get("thin_cut")
            wgt = np.full(len(ite), omega)
            if thin is not None:
                wgt = omega * np.clip(thin / np.maximum(dbar, 1e-6), 0.0, 1.0)
            model = (1 - wgt) * model + wgt * kp
        elif arm in ("M3_CONDCAL", "M3_CTRL"):
            ltr, lte, k = make_labels(D, itr, ite, ctx, rng, shuffle=(arm == "M3_CTRL"))
            # per-archetype affine recalibration of the MODEL leg, fitted on train
            rg = ridge_fit(X[itr], y[itr], w[itr])
            a0, b0 = lin_cal(ridge_pred(rg, X[itr]), y[itr])
            ptr = np.maximum(-2.0, a0 + b0 * ridge_pred(rg, X[itr]))
            new = model.copy()
            for g in range(k):
                mg = ltr == g
                if mg.sum() < 30:
                    continue
                ag, bg = lin_cal(ptr[mg], y[itr][mg])
                sel = lte == g
                if sel.any():
                    new[sel] = np.maximum(-2.0, ag + bg * model[sel])
            model = new
        elif arm in ("M4_SHRINK", "M4_CTRL"):
            ltr, lte, k = make_labels(D, itr, ite, ctx, rng, shuffle=(arm == "M4_CTRL"))
            lam_g = _stratum_lambda(D, itr, ltr, k, lam, ctx)
            lv = np.array([lam_g.get(int(g), lam) for g in lte])
            return_pred = (1 - lv) * cons + lv * model
            P.append(return_pred); Y.append(y[ite]); F.append(fv[ite])
            B.append(np.full(len(ite), yr)); Db.append(deb[ite]); Tr.append(tr[ite])
            continue

        P.append((1 - lam) * cons + lam * model)
        Y.append(y[ite]); F.append(fv[ite]); B.append(np.full(len(ite), yr))
        Db.append(deb[ite]); Tr.append(tr[ite])

    if not P:
        return None
    return tuple(np.concatenate(v) for v in (P, Y, F, B, Db, Tr))


def _select_omega(D, itr, ctx, lam, rng, arm):
    """Choose the comp-blend weight strictly inside TRAIN via an inner forward split."""
    dy = D["dy"][itr]
    cut = np.quantile(dy, 0.70)
    inner_tr = itr[dy < cut]
    inner_te = itr[dy >= cut]
    if len(inner_tr) < 60 or len(inner_te) < 25:
        return 0.0
    legs = _legs(D["X"][inner_tr], D["y"][inner_tr], D["w"][inner_tr],
                 D["fv"][inner_tr], D["X"][inner_te], D["fv"][inner_te])
    if legs is None:
        return 0.0
    cons, model = legs
    Ax = ctx["comp_axes"]
    mu, sd = Ax[inner_tr].mean(0), Ax[inner_tr].std(0).copy(); sd[sd == 0] = 1.0
    kk = ctx.get("knn_k", 20)
    if arm == "M2_CTRL":
        idx = rng.integers(0, len(inner_tr), size=(len(inner_te), kk))
        kp = D["y"][inner_tr][idx].mean(1)
    else:
        kp, _ = knn_pred((Ax[inner_tr] - mu) / sd, D["y"][inner_tr],
                         (Ax[inner_te] - mu) / sd, k=kk)
    best, bo = -9.0, 0.0
    for om in np.arange(0.0, 0.65, 0.05):
        p = (1 - lam) * cons + lam * ((1 - om) * model + om * kp)
        s = spear(p, D["y"][inner_te])
        if s == s and s > best:
            best, bo = s, float(om)
    return bo


def _stratum_lambda(D, itr, ltr, k, lam, ctx):
    """Per-archetype lambda estimated STRICTLY out of fold inside TRAIN."""
    dy = D["dy"][itr]
    cut = np.quantile(dy, 0.70)
    a_idx = np.flatnonzero(dy < cut)
    b_idx = np.flatnonzero(dy >= cut)
    if len(a_idx) < 60 or len(b_idx) < 25:
        return {}
    ia, ib = itr[a_idx], itr[b_idx]
    legs = _legs(D["X"][ia], D["y"][ia], D["w"][ia], D["fv"][ia],
                 D["X"][ib], D["fv"][ib])
    if legs is None:
        return {}
    cons, model = legs
    yb, lb = D["y"][ib], ltr[b_idx]
    out = {}
    grid = np.arange(0.0, 0.95, 0.05)
    for g in range(k):
        m = lb == g
        if m.sum() < 25:
            continue
        best, bl = -9.0, lam
        for L in grid:
            s = spear((1 - L) * cons[m] + L * model[m], yb[m])
            if s == s and s > best:
                best, bl = s, float(L)
        out[g] = bl
    return out


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def score_arm(res, tr_only=False):
    if res is None:
        return None
    P, Y, F, B, Db, Tr = res
    if tr_only:
        m = Tr > 0.5
        if m.sum() < 40:
            return None
        P, Y, F, B, Db = P[m], Y[m], F[m], B[m], Db[m]
    return metrics(P, Y, F, B, Db)
