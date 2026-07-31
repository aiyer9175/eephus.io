# SCRATCH (frontier lane: REGULARIZATION / SHRINKAGE / ENSEMBLING).
# Read-only against shipped modules. Writes JSON to tools/_frontier_out/.
# Implements the RECOMMENDED evaluator from efv-evaluator-power-2026-07-24:
#   both sides pooled, (side x cohort-year) block-normalized Spearman,
#   train = production full pool minus recent busts (KM sample weights),
#   test = debuted rows, origins 2020-2024, lambda PINNED (hit .85 / pit .63),
#   paired refit bootstrap stratified on (side, decision_year).
from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as em                                     # noqa: E402  read-only
from prospect_path import _fit_linear_calibration          # noqa: E402

DATA = ROOT / "data"
OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)

ORIGINS = (2020, 2021, 2022, 2023, 2024)
LAM = {"hit": 0.85, "pit": 0.63}
SHIPPED_ALPHAS = (1.0, 10.0, 100.0)
SHIPPED_SEED = 20260707
CONTRIB = 3.0

BASE_KEYS = {s: em._feature_spec(s)[0] for s in ("hit", "pit")}


# ------------------------------------------------------------------ data
def load_pool(noise_seed=20260724):
    rng = random.Random(noise_seed)
    pool = {}
    for side, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        raw = json.loads((DATA / fn).read_text(encoding="utf-8"))
        rows = []
        for r in raw:
            p = em._prep([r], "target_censored", side)
            if not p:
                continue
            d = p[0]
            d["side"] = side
            d["bust_recent"] = bool(r.get("bust_recent"))
            d["feats"]["_noise"] = rng.gauss(0.0, 1.0)
            # ---- information-availability descriptors (NOT model features) ----
            m = r.get("milb") or {}
            n_src = float(r.get("n_sources") or 0.0)
            tool_keys = (("tool_fb", "tool_cmd", "tool_sl", "tool_ch", "tool_cb")
                         if side == "pit" else
                         ("tool_hit", "tool_game_pwr", "tool_speed", "tool_field"))
            n_tools = sum(1 for k in tool_keys if r.get(k) is not None)
            d["info"] = {
                "n_sources": n_src,
                "single_source": 1.0 if n_src <= 1 else 0.0,
                "milb_missing": float(d["feats"].get("milb_missing", 0.0)),
                "n_milb_seasons": float(m.get("n_milb_seasons") or 0.0),
                "thin_milb": 1.0 if float(m.get("n_milb_seasons") or 0.0) <= 1 else 0.0,
                "no_tools": 1.0 if n_tools == 0 else 0.0,
                "n_tools": float(n_tools),
                "fv_stddev": float(r.get("fv_stddev") or 0.0),
                # zero-information uniform, FIXED per player -> matched-prevalence
                # placebo flags (the pairing-preserving control)
                "u": rng.random(),
                "u2": rng.random(),
                "u3": rng.random(),
            }
            rows.append(d)
        pool[side] = rows
    return pool


def train_rows(rows):
    return [r for r in rows if not (r["kind"] == "bust" and r["bust_recent"])]


def test_rows(rows):
    return [r for r in rows if r["kind"] == "debuted"]


# ------------------------------------------------------------------ ridge (configurable)
def _design(train, keys):
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in train], dtype=float)
    y = np.array([r["target"] for r in train], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in train]), 1e-3, None)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd == 0, 1.0, sd)
    return (X - mu) / sd, y, w, mu, sd


def _solve(Xs, y, w, idx, alpha, b):
    Xi, wi = Xs[idx], w[idx]
    WX = Xi * wi[:, None]
    A = WX.T @ Xi + alpha * np.eye(Xs.shape[1])
    return np.linalg.solve(A, WX.T @ (y[idx] - b))


def _wmean(y, w, idx):
    ww = w[idx]
    return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())


def _rank_np(v):
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


def fit_ridge_cfg(train, keys, cfg):
    """cfg: dict(mode=..., ...). Returns a model dict with .predict-able params.
    modes:
      shipped              : exact replica of prospect_path._fit_ridge
      fixed(alpha)         : no selection
      grid(alphas)         : shipped selector on a different grid
      seedavg(K, alphas)   : average the K per-seed selected-alpha coefficient vectors
      kfold(K, alphas)     : alpha by K-fold weighted-MAE CV (all rows used)
      bag(K, base_cfg)     : bagged coefficients over K bootstrap resamples of train
    """
    if len(train) < 40:
        return None
    mode = cfg["mode"]
    if mode == "bag":
        sub = cfg["base"]
        K = cfg.get("K", 12)
        rng = np.random.default_rng(cfg.get("seed", 606) )
        n = len(train)
        acc = None
        cnt = 0
        for _ in range(K):
            idx = rng.integers(0, n, n)
            m = fit_ridge_cfg([train[i] for i in idx], keys, sub)
            if m is None:
                continue
            # bagged models have their own mu/sd; convert to a common raw-linear form
            w_raw = np.array(m["w"]) / np.array(m["sd"])
            b_raw = m["b"] - float((np.array(m["w"]) * np.array(m["mu"]) / np.array(m["sd"])).sum())
            acc = (w_raw, b_raw) if acc is None else (acc[0] + w_raw, acc[1] + b_raw)
            cnt += 1
        if not cnt:
            return None
        return {"keys": keys, "mu": [0.0] * len(keys), "sd": [1.0] * len(keys),
                "w": (acc[0] / cnt).tolist(), "b": float(acc[1] / cnt), "alpha": None}

    Xs, y, w, mu, sd = _design(train, keys)
    n = len(train)
    b_all = _wmean(y, w, np.arange(n))

    if mode == "fixed":
        alpha = float(cfg["alpha"])
        return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(),
                "w": _solve(Xs, y, w, np.arange(n), alpha, b_all).tolist(),
                "b": b_all, "alpha": alpha}

    alphas = cfg.get("alphas", SHIPPED_ALPHAS)

    if mode in ("shipped", "grid", "seedavg"):
        seeds = ([SHIPPED_SEED] if mode != "seedavg"
                 else [SHIPPED_SEED + 1000 * i for i in range(cfg.get("K", 6))])
        picked, coefs = [], []
        for sd_i in seeds:
            order = np.random.default_rng(sd_i).permutation(n)
            k = max(1, n // 5)
            ho, tri = order[:k], order[k:]
            b_tr = _wmean(y, w, tri)
            best = None
            for alpha in alphas:
                ww = _solve(Xs, y, w, tri, alpha, b_tr)
                pred = Xs[ho] @ ww + b_tr
                mae = (float(np.average(np.abs(pred - y[ho]), weights=w[ho]))
                       if w[ho].sum() > 0 else float(np.abs(pred - y[ho]).mean()))
                if best is None or mae < best[0]:
                    best = (mae, alpha)
            picked.append(best[1])
            coefs.append(_solve(Xs, y, w, np.arange(n), best[1], b_all))
        W = np.mean(coefs, axis=0)
        return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(), "w": W.tolist(),
                "b": b_all, "alpha": float(np.mean(picked)), "alpha_path": picked}

    if mode == "kfold":
        K = cfg.get("K", 5)
        order = np.random.default_rng(cfg.get("seed", SHIPPED_SEED)).permutation(n)
        folds = np.array_split(order, K)
        best = None
        for alpha in alphas:
            errs, wts = [], []
            for f in folds:
                tri = np.setdiff1d(order, f, assume_unique=False)
                b_tr = _wmean(y, w, tri)
                ww = _solve(Xs, y, w, tri, alpha, b_tr)
                pred = Xs[f] @ ww + b_tr
                errs.append(np.abs(pred - y[f]))
                wts.append(w[f])
            e = np.concatenate(errs)
            ws = np.concatenate(wts)
            mae = float(np.average(e, weights=ws))
            if best is None or mae < best[0]:
                best = (mae, alpha)
        return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(),
                "w": _solve(Xs, y, w, np.arange(n), best[1], b_all).tolist(),
                "b": b_all, "alpha": best[1]}

    raise ValueError(mode)


def predict_many(model, rows):
    keys = model["keys"]
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in rows], dtype=float)
    mu = np.array(model["mu"]); sd = np.array(model["sd"])
    return ((X - mu) / np.where(sd == 0, 1.0, sd)) @ np.array(model["w"]) + model["b"]


# ------------------------------------------------------------------ scoring
def score_records(pool, keys_map, cfg, origins=ORIGINS, sides=("hit", "pit"),
                  train_frame="fullpool", cal=True):
    """Returns list of dicts: side, year, cons, mod (calibrated), target, fv, info.
    Blending is applied later so many lambda schemes share one fit."""
    recs = []
    alphas_used = []
    for side in sides:
        rows = pool[side]
        tr_pool = train_rows(rows) if train_frame == "fullpool" else test_rows(rows)
        te_pool = test_rows(rows)
        keys = keys_map[side]
        for yr in origins:
            tr = [r for r in tr_pool if r["decision_year"] < yr]
            te = [r for r in te_pool if r["decision_year"] == yr]
            if len(te) < 15 or len(tr) < 60:
                continue
            ols = em._fit_ols_fv(tr)
            ridge = fit_ridge_cfg(tr, keys, cfg)
            if not (ols and ridge):
                continue
            if ridge.get("alpha") is not None:
                alphas_used.append((side, yr, ridge["alpha"]))
            a, b = 0.0, 1.0
            if cal:
                raw_tr = predict_many(ridge, tr)
                c = _fit_linear_calibration(list(zip(raw_tr.tolist(),
                                                     [r["target"] for r in tr])))
                if c:
                    a, b = c["a"], c["b"]
            raw_te = predict_many(ridge, te)
            for r, rp in zip(te, raw_te):
                recs.append({
                    "side": side, "year": yr,
                    "cons": max(0.0, em._pred_ols(ols, r["fv"])),
                    "mod": max(-2.0, a + b * float(rp)),
                    "target": r["target"], "fv": r["fv"], "info": r["info"],
                })
    return recs, alphas_used


# ------------------------------------------------------------------ blend schemes
def blend(recs, scheme):
    """scheme -> per-record lambda. Returns np array of predictions."""
    out = np.empty(len(recs))
    kind = scheme["kind"]
    for i, r in enumerate(recs):
        lam = LAM[r["side"]]
        if kind == "global":
            pass
        elif kind == "info_flag":
            # shrink model leg toward consensus for LOW-information rows
            f = r["info"][scheme["flag"]]
            if f >= scheme.get("thresh", 0.5):
                lam = lam * scheme["mult"]
        elif kind == "info_flag_inv":   # PLACEBO/control: shrink HIGH-information rows
            f = r["info"][scheme["flag"]]
            if f < scheme.get("thresh", 0.5):
                lam = lam * scheme["mult"]
        elif kind == "info_score":
            s = 0.0
            for k, wgt in scheme["terms"]:
                s += wgt * r["info"][k]
            s = max(0.0, min(1.0, s))      # 0 = no information, 1 = full
            lam = lam * (scheme["floor"] + (1 - scheme["floor"]) * s)
        elif kind == "tier":
            lam = scheme["map"].get(_tier(r["fv"]), lam)
        elif kind == "tier_mult":
            lam = lam * scheme["map"].get(_tier(r["fv"]), 1.0)
        elif kind == "side_lam":
            lam = scheme["lam"][r["side"]]
        else:
            raise ValueError(kind)
        out[i] = (1 - lam) * r["cons"] + lam * r["mod"]
    return out


def _tier(fv):
    if fv <= 40:
        return "lo"
    if fv <= 45:
        return "fringe"
    if fv <= 50:
        return "mid"
    return "hi"


# ------------------------------------------------------------------ metric
def _rho(p, t):
    if len(p) < 8:
        return None
    rp, rt = _rank_np(p), _rank_np(t)
    rp = rp - rp.mean(); rt = rt - rt.mean()
    d = math.sqrt(float((rp * rp).sum()) * float((rt * rt).sum()))
    return float((rp * rt).sum() / d) if d > 0 else None


def _pct(v):
    n = len(v)
    return (_rank_np(v) - 0.5) / n if n else np.array([])


def block_rho(recs, preds):
    blocks = {}
    for i, r in enumerate(recs):
        blocks.setdefault((r["side"], r["year"]), []).append(i)
    P, T = [], []
    for idx in blocks.values():
        if len(idx) < 8:
            continue
        P.append(_pct(preds[idx]))
        T.append(_pct(np.array([recs[i]["target"] for i in idx])))
    if not P:
        return None
    return _rho(np.concatenate(P), np.concatenate(T))


def block_auc(recs, preds, bar=CONTRIB):
    blocks = {}
    for i, r in enumerate(recs):
        blocks.setdefault((r["side"], r["year"]), []).append(i)
    P, Y = [], []
    for idx in blocks.values():
        if len(idx) < 8:
            continue
        P.append(_pct(preds[idx]))
        Y.append(np.array([recs[i]["target"] for i in idx]))
    if not P:
        return None
    P = np.concatenate(P); Y = np.concatenate(Y) >= bar
    npos, nneg = int(Y.sum()), int((~Y).sum())
    if npos == 0 or nneg == 0:
        return None
    r = _rank_np(P)
    return float((r[Y].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


# ------------------------------------------------------------------ bootstrap
def resample_pool(pool, rng):
    out = {}
    for side, rows in pool.items():
        by = {}
        for r in rows:
            by.setdefault(r["decision_year"], []).append(r)
        new = []
        for g in by.values():
            new.extend(g[rng.randrange(len(g))] for _ in g)
        out[side] = new
    return out
