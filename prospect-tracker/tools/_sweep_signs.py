# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""SWEEP LANE `signs` -- declared-vs-fitted monotone sign audit for the eFV feature sets.

SCRATCH LAB. Writes nothing into the served pipeline; the shipped modules are
untouched (this lane may not edit efv_model.py / efv_dataset.py).

WHAT IT MEASURES
  1. served signs   -- efv_model.fit_production_stack (the EXACT fit efv_score
                       ._fit_production serves), standardized ridge weights vs the
                       monotone direction declared in _FEATURES_HIT / _FEATURES_PIT.
  2. fold stability -- the same ridge refit on every forward-chained fold
                       (train = decision_year < Y), Y = 2014..2024 (11 folds), so a
                       sign that CHATTERS is separated from one that is stably wrong.
  3. marginal vs partial -- weighted Pearson + Spearman of the raw column against
                       realized WAR (marginal) beside the standardized ridge weight
                       and the UNREGULARIZED OLS partial. A feature whose marginal
                       agrees with the declaration but whose partial does not is a
                       SUPPRESSOR (a legitimate conditional effect), not a wrong sign.
  4. partner drop   -- refit with the declared collinear partner removed. If the
                       sign snaps back to the declaration, the contradiction is a
                       collinear SPLIT, not an independent effect.
  5. drop gate      -- full EFV_GATE_STANDARD adjudication of removing one feature:
                       >= 4 (here 11) forward-chained time splits, paired bootstrap
                       resampling TRAIN AND TEST with a refit per draw, a
                       zero-information control (the same column row-permuted), and
                       a permutation null band.

Everything runs off a numpy replica of prospect_path._fit_ridge that is verified
bit-for-bit against the real one (see `verify_replica`), so 2,000-draw bootstraps
are affordable.

Run:  python tools/_sweep_signs.py            (full audit + pitcher-age adjudication)
      python tools/_sweep_signs.py --quick    (audit + stability only)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import efv_model as M                                      # noqa: E402
from efv_dataset import matrix_path                        # noqa: E402
from prospect_path import _fit_ridge, _ALPHAS, _RIDGE_HOLDOUT_SEED   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "xfv_sign_audit.json"

FOLDS = tuple(range(2014, 2025))          # 11 forward-chained folds
BOOT = 2000
PERM = 1000
SEED = 20260725

# Structurally collinear partners (efv_factor_groups.GROUPS, plus the age pair the
# grouping module deliberately leaves ungrouped for DISPLAY but which is still the
# collinearity to test for a SIGN split).
PARTNER = {
    "k_rel": "peak_k_rel", "peak_k_rel": "k_rel",
    "bb_rel": "peak_bb_rel", "peak_bb_rel": "bb_rel",
    "obp_rel": "peak_obp_rel", "peak_obp_rel": "obp_rel",
    "ops_rel": "peak_ops_rel", "peak_ops_rel": "ops_rel",
    "iso_rel": "peak_iso_rel", "peak_iso_rel": "iso_rel",
    "age": "age_rel_level", "age_rel_level": "age",
    "milb_missing": "n_milb_seasons", "n_milb_seasons": "milb_missing",
}


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def load(side: str):
    """The production pool, exactly as fit_production_stack selects it."""
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    return M._prep(pool, "target_censored", side)


def arrays(data, keys):
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in data], dtype=float)
    y = np.array([r["target"] for r in data], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in data]), 1e-3, None)
    yr = np.array([r["decision_year"] for r in data], dtype=int)
    fv = np.array([r["fv"] for r in data], dtype=float)
    return X, y, w, yr, fv


# ---------------------------------------------------------------------------
# ridge replica (bit-for-bit with prospect_path._fit_ridge)
# ---------------------------------------------------------------------------

def ridge_np(X, y, w):
    n = len(y)
    if n < 40:
        return None
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = sd.copy()
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    p = X.shape[1]

    def _wmean(idx):
        ww = w[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        return np.linalg.solve(WX.T @ Xi + alpha * np.eye(p), WX.T @ (y[idx] - b))

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    folds = np.array_split(order, 5)
    best = None
    for alpha in _ALPHAS:
        es = ws = 0.0
        for i in range(len(folds)):
            ho = folds[i]
            tri = np.concatenate([folds[j] for j in range(len(folds)) if j != i])
            if len(ho) == 0 or len(tri) == 0:
                continue
            b_tr = _wmean(tri)
            pred = Xs[ho] @ _wridge(tri, alpha, b_tr) + b_tr
            ww = w[ho]
            if ww.sum() > 0:
                es += float(np.sum(np.abs(pred - y[ho]) * ww)); ws += float(ww.sum())
            else:
                es += float(np.sum(np.abs(pred - y[ho]))); ws += float(len(ho))
        mae = (es / ws) if ws > 0 else float("inf")
        if best is None or mae < best[0]:
            best = (mae, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    return {"mu": mu, "sd": sd, "w": _wridge(np.arange(n), alpha, b), "b": b, "alpha": alpha}


def predict_np(m, X):
    return ((X - m["mu"]) / m["sd"]) @ m["w"] + m["b"]


def verify_replica(side="hit"):
    keys, _ = M._feature_spec(side)
    data = load(side)
    X, y, w, _, _ = arrays(data, keys)
    a = _fit_ridge(data, keys)
    b = ridge_np(X, y, w)
    d = float(np.max(np.abs(np.array(a["w"]) - b["w"])))
    return {"max_abs_weight_diff": d, "alpha_match": a["alpha"] == b["alpha"], "ok": d < 1e-9}


# ---------------------------------------------------------------------------
# stats helpers
# ---------------------------------------------------------------------------

def spearman(a, b):
    if len(a) < 8:
        return None
    ra = _rank(np.asarray(a, float)); rb = _rank(np.asarray(b, float))
    ra = ra - ra.mean(); rb = rb - rb.mean()
    d = float(np.sqrt((ra @ ra) * (rb @ rb)))
    return float(ra @ rb / d) if d else None


def _rank(v):
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


def wcorr(x, y, w):
    """Weighted Pearson."""
    sw = w.sum()
    mx = (w * x).sum() / sw; my = (w * y).sum() / sw
    cx = x - mx; cy = y - my
    vx = (w * cx * cx).sum(); vy = (w * cy * cy).sum()
    return float((w * cx * cy).sum() / np.sqrt(vx * vy)) if vx > 0 and vy > 0 else None


def wols(X, y, w):
    """Unregularized weighted OLS on standardized columns (the PARTIAL, no shrinkage)."""
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = sd.copy(); sd[sd == 0] = 1.0
    Xs = np.column_stack([np.ones(len(y)), (X - mu) / sd])
    WX = Xs * w[:, None]
    try:
        return np.linalg.solve(WX.T @ Xs, WX.T @ y)[1:]
    except np.linalg.LinAlgError:
        return np.full(X.shape[1], np.nan)


# ---------------------------------------------------------------------------
# 1-4: the audit
# ---------------------------------------------------------------------------

def contradicts(decl: int, w: float, tol: float = 1e-9) -> bool:
    """Machine-checkable rule: a NONZERO declaration contradicted by the fitted sign."""
    return decl != 0 and abs(w) > tol and (w > 0) != (decl > 0)


def audit_side(side: str) -> dict:
    keys, mono = M._feature_spec(side)
    data = load(side)
    X, y, w, yr, _ = arrays(data, keys)

    served = ridge_np(X, y, w)
    ols_partial = wols(X, y, w)

    # fold stability. DEGENERATE-FOLD GUARD: the 2014/2015 folds train only on rows
    # from before the StatsAPI MiLB floor, so every production column is CONSTANT
    # (k_rel/age_rel_level/peak_k_rel all exactly 0, age all at the 22.5 impute).
    # ridge_np standardizes a zero-variance column to all-zeros and returns weight
    # exactly 0. Counting those as "does not agree with the declaration" would
    # manufacture instability, so a fold only counts for a feature when that
    # feature's column actually VARIES in the fold's training rows.
    fold_w = {k: [] for k in keys}
    fold_years = []
    for Y in FOLDS:
        tr = yr < Y
        te = yr == Y
        if te.sum() < 15 or tr.sum() < 60:
            continue
        m = ridge_np(X[tr], y[tr], w[tr])
        if m is None:
            continue
        fold_years.append(Y)
        for i, k in enumerate(keys):
            if float(X[tr, i].std()) <= 0:
                continue                      # degenerate: the fold carries no info
            fold_w[k].append(float(m["w"][i]))

    # partner-drop refit
    partner_drop = {}
    for k in keys:
        p = PARTNER.get(k)
        if p in keys:
            sub = [q for q in keys if q != p]
            Xs = X[:, [keys.index(q) for q in sub]]
            m = ridge_np(Xs, y, w)
            partner_drop[k] = {"partner": p, "w_without_partner": float(m["w"][sub.index(k)])}

    feats = {}
    for i, k in enumerate(keys):
        decl = mono[i]
        wser = float(served["w"][i])
        fw = fold_w[k]
        n_pos = sum(1 for v in fw if v > 0)
        n_agree = sum(1 for v in fw if decl == 0 or (v > 0) == (decl > 0)) if decl else None
        marg_p = wcorr(X[:, i], y, w)
        marg_s = spearman(X[:, i], y)
        pd = partner_drop.get(k)
        con = contradicts(decl, wser)
        # suppressor = marginal AGREES with the declaration while the partial does not
        supp = bool(con and marg_p is not None and decl != 0 and (marg_p > 0) == (decl > 0))
        split = bool(con and pd and not contradicts(decl, pd["w_without_partner"]))
        feats[k] = {
            "declared": decl,
            "served_w": round(wser, 4),
            "contradiction": con,
            "fold_w_mean": round(float(np.mean(fw)), 4) if fw else None,
            "fold_w_min": round(float(np.min(fw)), 4) if fw else None,
            "fold_w_max": round(float(np.max(fw)), 4) if fw else None,
            "folds_positive": n_pos, "folds_n": len(fw),
            "folds_agreeing_with_declaration": n_agree,
            "sign_stable_across_folds": bool(fw) and (n_pos == 0 or n_pos == len(fw)),
            "marginal_wpearson": round(marg_p, 4) if marg_p is not None else None,
            "marginal_spearman": round(marg_s, 4) if marg_s is not None else None,
            "ols_partial_std": round(float(ols_partial[i]), 4),
            "partner": (pd or {}).get("partner"),
            "w_without_partner": (round(pd["w_without_partner"], 4) if pd else None),
            "verdict": ("SUPPRESSOR" if supp and not split else
                        "COLLINEAR_SPLIT" if split else
                        "WRONG_SIGN" if con else "OK"),
        }
    return {"side": side, "n": len(data), "alpha": served["alpha"],
            "fold_years": fold_years, "features": feats,
            "contradictions": [k for k, v in feats.items() if v["contradiction"]]}


def audit_provisional() -> dict:
    """The provisional (no-FV) sets in efv_ungraded carry NO declarations of their own;
    they reuse efv_model._vec columns, so the flagship declaration is the only stated
    intent for those same keys. Audit them against it."""
    import efv_ungraded as U
    decl_hit = dict(M._FEATURES_HIT)
    decl_pit = dict(M._FEATURES_PIT)
    # fall back to the other side's declaration for keys the flagship set does not carry
    # on this side (e.g. iso_rel, era_rel, peak_obp_rel) -- recorded as UNDECLARED.
    out = {}
    for side, keys, decl in (("hit", U._NOFV_HIT, decl_hit), ("pit", U._NOFV_PIT, decl_pit)):
        data = [r for r in load(side)]
        # provisional fit is production-bearing rows only
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        is_pit = side == "pit"
        pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
                and not (r.get("kind") == "bust" and r.get("bust_recent"))]
        data = M._prep(pool, "target_censored", side)
        X, y, w, _, _ = arrays(data, keys)
        m = ridge_np(X, y, w)
        feats = {}
        for i, k in enumerate(keys):
            d = decl.get(k)
            wv = float(m["w"][i])
            feats[k] = {"declared": d, "served_w": round(wv, 4),
                        "undeclared": d is None,
                        "contradiction": bool(d is not None and contradicts(d, wv)),
                        "marginal_wpearson": round(wcorr(X[:, i], y, w) or 0.0, 4)}
        out[side] = {"n": len(data), "features": feats,
                     "contradictions": [k for k, v in feats.items() if v["contradiction"]],
                     "undeclared": [k for k, v in feats.items() if v["undeclared"]]}
    return out


# ---------------------------------------------------------------------------
# 5: the full drop gate
# ---------------------------------------------------------------------------

def _fwd_pooled_rho(X, y, w, yr, cols, lam, fv):
    """Forward-chained pooled Spearman of the SHIPPED blend leg, over FOLDS."""
    preds, targs = [], []
    per_fold = {}
    for Y in FOLDS:
        tr = yr < Y; te = yr == Y
        if te.sum() < 15 or tr.sum() < 60:
            continue
        m = ridge_np(X[np.ix_(tr, cols)], y[tr], w[tr])
        if m is None:
            continue
        # consensus OLS anchor on the same train rows
        fvt = fv[tr]
        vx = ((fvt - fvt.mean()) ** 2).sum()
        if vx <= 0:
            continue
        b = ((fvt - fvt.mean()) * (y[tr] - y[tr].mean())).sum() / vx
        a = y[tr].mean() - b * fvt.mean()
        cons = np.maximum(0.0, a + b * fv[te])
        mod = predict_np(m, X[np.ix_(te, cols)])
        p = (1 - lam) * cons + lam * mod
        preds.append(p); targs.append(y[te])
        r = spearman(p, y[te])
        if r is not None:
            per_fold[int(Y)] = round(r, 4)
    if not preds:
        return None, {}
    return spearman(np.concatenate(preds), np.concatenate(targs)), per_fold


def drop_gate(side: str, feat: str, boot: int = BOOT, perm: int = PERM) -> dict:
    """Adjudicate REMOVING `feat` under EFV_GATE_STANDARD.

    delta = rho(without feat) - rho(with feat). Positive delta = dropping HELPS.
    Controls: (a) a row-permuted twin of the same column kept in the set (zero
    information, same marginal) -- if permuting scores like dropping, the column
    carries no information; (b) a permutation null band on the delta statistic;
    (c) paired bootstrap resampling TRAIN AND TEST with a refit each draw;
    (d) 11 forward-chained time splits, plus the per-fold deltas."""
    keys, _ = M._feature_spec(side)
    data = load(side)
    X, y, w, yr, fv = arrays(data, keys)
    lam = M.blend_lambda(side)
    j = keys.index(feat)
    full = list(range(len(keys)))
    less = [i for i in full if i != j]

    rho_full, pf_full = _fwd_pooled_rho(X, y, w, yr, full, lam, fv)
    rho_less, pf_less = _fwd_pooled_rho(X, y, w, yr, less, lam, fv)
    per_fold_delta = {k: round(pf_less[k] - pf_full[k], 4)
                      for k in pf_full if k in pf_less}

    rng = np.random.default_rng(SEED)

    # zero-information control: same column, row-permuted, KEPT in the set
    ctrl = []
    for _ in range(200):
        Xp = X.copy()
        Xp[:, j] = X[rng.permutation(len(y)), j]
        r, _ = _fwd_pooled_rho(Xp, y, w, yr, full, lam, fv)
        if r is not None:
            ctrl.append(r - rho_full)
    ctrl = np.array(ctrl)

    # paired bootstrap: resample the WHOLE pool (train AND test), refit per draw
    deltas = []
    n = len(y)
    for _ in range(boot):
        idx = rng.integers(0, n, n)
        Xb, yb, wb, yrb, fvb = X[idx], y[idx], w[idx], yr[idx], fv[idx]
        a1, _ = _fwd_pooled_rho(Xb, yb, wb, yrb, full, lam, fvb)
        a2, _ = _fwd_pooled_rho(Xb, yb, wb, yrb, less, lam, fvb)
        if a1 is not None and a2 is not None:
            deltas.append(a2 - a1)
    deltas = np.array(deltas)

    # permutation null band for the SAME statistic (labels shuffled within fold)
    nulls = []
    for _ in range(perm):
        yp = y.copy()
        for Y in set(yr.tolist()):
            m = yr == Y
            yp[m] = y[m][rng.permutation(int(m.sum()))]
        a1, _ = _fwd_pooled_rho(X, yp, w, yr, full, lam, fv)
        a2, _ = _fwd_pooled_rho(X, yp, w, yr, less, lam, fv)
        if a1 is not None and a2 is not None:
            nulls.append(a2 - a1)
    nulls = np.array(nulls)

    mde = 0.016 if side == "pit" else 0.017
    d = float(rho_less - rho_full)
    return {
        "side": side, "feature": feat, "lambda": lam, "n": n,
        "rho_with": round(float(rho_full), 4), "rho_without": round(float(rho_less), 4),
        "delta_drop_minus_keep": round(d, 5),
        "mde95_feature_add": mde,
        "x_of_floor": round(abs(d) / mde, 3),
        "per_fold_delta": per_fold_delta,
        "folds_drop_helps": sum(1 for v in per_fold_delta.values() if v > 0),
        "folds_n": len(per_fold_delta),
        "boot": {"n": int(len(deltas)), "mean": round(float(deltas.mean()), 5),
                 "sd": round(float(deltas.std(ddof=1)), 5),
                 "ci95": [round(float(np.percentile(deltas, 2.5)), 5),
                          round(float(np.percentile(deltas, 97.5)), 5)],
                 "p_drop_helps": round(float((deltas > 0).mean()), 4)},
        "zero_info_control": {"n": int(len(ctrl)), "mean": round(float(ctrl.mean()), 5),
                              "p95_abs": round(float(np.percentile(np.abs(ctrl), 95)), 5),
                              "band": [round(float(np.percentile(ctrl, 2.5)), 5),
                                       round(float(np.percentile(ctrl, 97.5)), 5)]},
        "permutation_null": {"n": int(len(nulls)),
                             "band95": [round(float(np.percentile(nulls, 2.5)), 5),
                                        round(float(np.percentile(nulls, 97.5)), 5)],
                             "p_two_sided": round(float((np.abs(nulls) >= abs(d)).mean()), 4)},
        "verdict": ("NULL (below MDE95 and CI straddles 0)"
                    if abs(d) < mde or (deltas.min() < 0 < deltas.max()
                                        and not (np.percentile(deltas, 2.5) > 0
                                                 or np.percentile(deltas, 97.5) < 0))
                    else "RESOLVABLE"),
    }


# ---------------------------------------------------------------------------

def main(quick=False):
    res = {"replica_check": verify_replica("hit"),
           "gate_standard": "docs/EFV_GATE_STANDARD.md",
           "flagship": {s: audit_side(s) for s in ("hit", "pit")},
           "provisional": audit_provisional()}
    if not quick:
        res["drop_gate"] = {
            "pit_age": drop_gate("pit", "age"),
            "hit_n_milb_seasons": drop_gate("hit", "n_milb_seasons"),
            "hit_k_rel": drop_gate("hit", "k_rel"),
            "hit_milb_missing": drop_gate("hit", "milb_missing"),
        }
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1)[:200])
    print("wrote", OUT)
    return res


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
