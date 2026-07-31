# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""MULTIVARIATE REGRESSION label instrument for censored PITCHER cohorts.

Design (built against the three diagnostics that preceded it):
  * attrition  -> the survival axis is nearly exhausted (+0.006 label rho for a PERFECT
                  survival flag); spend capacity on MAGNITUDE-AMONG-SURVIVORS instead.
  * transmission -> the label->model channel is almost pure RANK, and the rank that matters
                  is the TOP QUARTILE's. Magnitude can be borrowed (a monotone remap costs
                  at most ~10% of headroom). So: fit for ORDER, then push the score through
                  a monotone train-fitted map to recover WAR units.
  * role      -> do NOT split the map by role; role enters only as a covariate.
  * horizon   -> build for span=3 and degrade gracefully on sparsity (per-season normalised
                  features + explicit seasons_pitched / gaps).

CIRCULARITY: every feature is derived from rec['war'] (career WAR by season since debut),
rec['lines'] (realized MLB pitching lines) and rec['tj_years'] (injury). rec['row'] is never
read - no consensus FV, tool grades, draft pick/bonus, and no age (age IS an eFV predictor).

API: fit(train_rows) -> state ; predict(state, rec, span) -> float (6yr-WAR-equivalent).
The state fits lazily per span, so the same instrument is span-aware without refitting.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import efv_pitcher_label_harness as H  # noqa: E402


# ---------------------------------------------------------------------------
# features - post-debut REALIZED only
# ---------------------------------------------------------------------------

def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    xs = np.arange(n, dtype=float)
    xs -= xs.mean()
    den = float((xs * xs).sum())
    return float((xs * (np.asarray(ys, dtype=float) - float(np.mean(ys)))).sum() / den) if den else 0.0


def features(rec: dict, span: int) -> dict:
    """Early-window realized feature vector. Trajectory/role/quality terms are the ones the
    diagnostics said separate slow-burn aces (low war3, rising IP, good rates) from
    early innings-eaters (high war3, flat/falling IP, mediocre rates)."""
    w = H.window(rec, span)
    wars = [_f(rec["war"].get(i)) for i in range(span)]
    ip = []; g = []; gs = []; bf = []; pres = []
    for i in range(span):
        ln = rec["lines"].get(i)
        if ln:
            ip.append(_f(ln.get("ip"))); g.append(_f(ln.get("g"))); gs.append(_f(ln.get("gs")))
            bf.append(_f(ln.get("bf"))); pres.append(1.0)
        else:
            ip.append(0.0); g.append(0.0); gs.append(0.0); bf.append(0.0); pres.append(0.0)
    ip_tot, bf_tot, seen = sum(ip), sum(bf), sum(pres)
    ip_max = max(ip) if ip else 0.0
    gsr = [(gs[i] / g[i]) if g[i] else 0.0 for i in range(span)]
    li = max([i for i in range(span) if pres[i]], default=-1)
    fi = min([i for i in range(span) if pres[i]], default=-1)
    sqrt_ip = math.sqrt(max(0.0, ip_tot))
    return {
        # bulk outcome
        "war": w["war"], "war_ps": w["war_per_season"],
        "war_last": wars[-1], "war_max": max(wars), "war_min": min(wars),
        "war_slope": _slope(wars),
        "war_lastshare": (wars[-1] / w["war"]) if abs(w["war"]) > 0.5 else 0.0,
        # workload / durability / ramp (the attrition + IP-cap axis)
        "ip": ip_tot, "ip_ps": w["ip_per_season"], "sqrt_ip": sqrt_ip,
        "ip_last": ip[-1], "ip_max": ip_max, "ip_slope": _slope(ip),
        "ip_ramp": (ip[-1] / ip_max) if ip_max else 0.0,
        "ip_conc": (ip_max / ip_tot) if ip_tot else 0.0,
        "seasons_pitched": w["seasons_pitched"], "lines_missing": w["lines_missing"],
        "gaps": float(span) - seen,
        "bf_ps": bf_tot / max(1, span),
        # role + role TRAJECTORY (covariate only, never a split)
        "g": w["g"], "gs": w["gs"], "gs_ratio": w["gs_ratio"],
        "gs_ratio_last": gsr[li] if li >= 0 else 0.0,
        "gs_ratio_d": (gsr[li] - gsr[fi]) if (li >= 0 and fi >= 0) else 0.0,
        # per-inning quality, decoupled from bulk
        "k_pct": w["k_pct"], "bb_pct": w["bb_pct"], "kbb": w["kbb"],
        "era": w["era"], "war_per_ip": w["war_per_ip"] * 100.0,
        # injury
        "tj_in": w["tj_in_window"], "tj_pre": w["tj_pre_debut"],
        # quality x exposure interactions (ridge cannot find these on its own)
        "kbb_x_sqrtip": w["kbb"] * sqrt_ip,
        "k_x_ipramp": w["k_pct"] * ((ip[-1] / ip_max) if ip_max else 0.0),
        "gsr_x_ipps": w["gs_ratio"] * w["ip_per_season"],
        "warip_x_sqrtip": (w["war_per_ip"] * 100.0) * sqrt_ip,
        "span": float(span),
    }


KEYS = sorted(features({"war": {}, "lines": {}, "tj_years": [], "dy": 2015}, 3).keys())


def _matrix(recs, span):
    return np.array([[features(r, span)[k] for k in KEYS] for r in recs], dtype=float)


def _obs_war(rec, span):
    return sum(_f(rec["war"].get(i)) for i in range(span))


def _obs_war_vec(recs, span):
    return np.array([_obs_war(r, span) for r in recs], dtype=float)


# ---------------------------------------------------------------------------
# small regularized learners
# ---------------------------------------------------------------------------

def _ssqrt(y):
    return np.sign(y) * np.sqrt(np.abs(y))


def _ridge_fit(X, y, alpha):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    b = float(y.mean())
    wgt = np.linalg.solve(Xs.T @ Xs + alpha * np.eye(X.shape[1]), Xs.T @ (y - b))
    return {"mu": mu, "sd": sd, "w": wgt, "b": b}


def _ridge_pred(st, X):
    return ((X - st["mu"]) / st["sd"]) @ st["w"] + st["b"]


_GBM_PARAMS = dict(objective="regression", num_leaves=4, learning_rate=0.03, n_estimators=250,
                   min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
                   reg_lambda=5.0, verbose=-1, random_state=13)


def _gbm_fit(X, y):
    try:
        import lightgbm as lgb
    except ImportError:
        return None
    m = lgb.LGBMRegressor(**_GBM_PARAMS)
    m.fit(X, y)
    return m


def _ecdf_maker(vals):
    """train-fitted empirical CDF -> per-record quantile (no cohort context needed)."""
    s = np.sort(np.asarray(vals, dtype=float))

    def q(v):
        return float(np.searchsorted(s, v, side="right")) / max(1, len(s))
    return q


def _qmap_maker(train_scores, train_true):
    """monotone score -> WAR map: quantile transport onto the TRAIN true6 marginal.
    Rank-preserving by construction, so it changes MAGNITUDE only (per the transmission
    diagnostic, magnitude is worth <=10% of headroom and rank is worth ~98%)."""
    ecdf = _ecdf_maker(train_scores)
    ys = np.sort(np.asarray(train_true, dtype=float))
    n = len(ys)

    def m(score):
        u = min(max(ecdf(score), 1e-6), 1 - 1e-6)
        pos = u * (n - 1)
        lo = int(math.floor(pos)); hi = min(n - 1, lo + 1)
        return float(ys[lo] + (ys[hi] - ys[lo]) * (pos - lo))
    return m


# ---------------------------------------------------------------------------
# the instrument
# ---------------------------------------------------------------------------

RIDGE_ALPHA = 100.0        # picked by 5-fold CV on the EARLY cohort only
TWOPART_ALPHA = 300.0
KM_WEIGHT = 0.5            # quantile weight on the KM ordering in the ensemble arm


def _build(train_rows, span, mode):
    X = _matrix(train_rows, span)
    y6 = np.array([r["true6"] for r in train_rows], dtype=float)
    st = {"mode": mode, "span": span}
    if mode == "twopart":
        # label = EXACT observed WAR + regressed remaining WAR (the hazard x magnitude shape
        # the attrition diagnostic recommended). KM is the degenerate case remaining := observed.
        rem = np.array([r["true6"] - _obs_war(r, span) for r in train_rows], dtype=float)
        st["ridge"] = _ridge_fit(X, rem, TWOPART_ALPHA)
        tr_scores = _obs_war_vec(train_rows, span) + _ridge_pred(st["ridge"], X)
        st["qmap"] = _qmap_maker(tr_scores, y6)
        return st
    if mode in ("ridge", "ens", "kmblend"):
        st["ridge"] = _ridge_fit(X, _ssqrt(y6), RIDGE_ALPHA)
    if mode in ("gbm", "ens", "kmblend"):
        st["gbm"] = _gbm_fit(X, _ssqrt(y6))
    raw = _raw_scores(st, X, train_rows, span)
    st["km_ecdf"] = _ecdf_maker([H.km_label(r, span) for r in train_rows])
    if mode in ("ens", "kmblend"):
        st["ridge_ecdf"] = _ecdf_maker(raw["ridge"])
        st["gbm_ecdf"] = _ecdf_maker(raw["gbm"]) if raw.get("gbm") is not None else None
        blend = _blend_scores(st, raw, [H.km_label(r, span) for r in train_rows], mode)
        st["qmap"] = _qmap_maker(blend, y6)
    else:
        st["qmap"] = _qmap_maker(raw[mode], y6)
    return st


def _raw_scores(st, X, recs, span):
    out = {}
    if "ridge" in st:
        out["ridge"] = _ridge_pred(st["ridge"], X)
    if st.get("gbm") is not None:
        out["gbm"] = st["gbm"].predict(X)
    return out


def _blend_scores(st, raw, km_labels, mode):
    ru = np.array([st["ridge_ecdf"](v) for v in raw["ridge"]])
    gu = (np.array([st["gbm_ecdf"](v) for v in raw["gbm"]])
          if st.get("gbm_ecdf") is not None else ru)
    ku = np.array([st["km_ecdf"](v) for v in km_labels])
    model_u = 0.5 * ru + 0.5 * gu
    if mode == "ens":
        return model_u
    return (1 - KM_WEIGHT) * ku + KM_WEIGHT * model_u


def make(mode="ens", qmap=True):
    """Returns (fit_fn, predict_fn) for one arm of the instrument."""
    def fit(train_rows):
        return {"rows": list(train_rows), "cache": {}, "mode": mode, "qmap": qmap}

    def predict(state, rec, span):
        key = int(span)
        st = state["cache"].get(key)
        if st is None:
            st = _build(state["rows"], key, state["mode"])
            state["cache"][key] = st
        X = _matrix([rec], key)
        raw = _raw_scores(st, X, [rec], key)
        if state["mode"] in ("ens", "kmblend"):
            score = float(_blend_scores(st, raw, [H.km_label(rec, key)], state["mode"])[0])
        elif state["mode"] == "twopart":
            return float(_obs_war(rec, key) + raw["ridge"][0]) if not state["qmap"] \
                else float(st["qmap"](float(_obs_war(rec, key) + raw["ridge"][0])))
        else:
            score = float(raw[state["mode"]][0])
        return float(st["qmap"](score)) if state["qmap"] else score

    return fit, predict


CANDIDATES = {
    "M1_ridge_qmap": make("ridge", qmap=True),
    "M2_gbm_qmap": make("gbm", qmap=True),
    "M3_twopart_raw": make("twopart", qmap=False),
    "M4_ens_ridge_gbm": make("ens", qmap=True),
    "M5_ens_plus_km": make("kmblend", qmap=True),
}


# ---------------------------------------------------------------------------
# overfitting guard: in-fit vs cross-validated label fidelity on the EARLY cohort
# ---------------------------------------------------------------------------

def _spearman_local(a, b):
    from prospect_path import _spearman
    return _spearman(list(a), list(b))


def overfit_report(pool, span, folds=5, seed=7):
    early = [r for r in pool if H.EARLY[0] <= r["dy"] <= H.EARLY[1]]
    mid = [r for r in pool if H.MID[0] <= r["dy"] <= H.MID[1]]
    y_e = [r["true6"] for r in early]
    y_m = [r["true6"] for r in mid]
    print(f"\n  OVERFIT GUARD (early n={len(early)}, {folds}-fold CV; mid n={len(mid)} is a true "
          f"forward transfer)  span={span}")
    print(f"    {'arm':20} {'in-fit':>8} {'cv':>8} {'mid':>8} {'mid_topQ':>9} {'mid_dec_rec':>11}")
    km = [H.km_label(r, span) for r in mid]
    print(f"    {'KM_baseline':20} {'-':>8} {'-':>8} {_spearman_local(km,y_m):>8.4f} "
          f"{_topq(km,y_m):>9.3f} {_dec(km,y_m):>11.2f}")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(early))
    for name, (fit_fn, pred_fn) in CANDIDATES.items():
        st = fit_fn(early)
        infit = [pred_fn(st, r, span) for r in early]
        cv = [0.0] * len(early)
        for k in range(folds):
            ho = order[k::folds]
            hoset = set(ho.tolist())
            tr = [early[i] for i in range(len(early)) if i not in hoset]
            stk = fit_fn(tr)
            for i in ho:
                cv[i] = pred_fn(stk, early[i], span)
        lm = [pred_fn(st, r, span) for r in mid]
        print(f"    {name:20} {_spearman_local(infit,y_e):>8.4f} {_spearman_local(cv,y_e):>8.4f} "
              f"{_spearman_local(lm,y_m):>8.4f} {_topq(lm,y_m):>9.3f} {_dec(lm,y_m):>11.2f}")


def _topq(pred, true):
    p, t = np.asarray(pred, dtype=float), np.asarray(true, dtype=float)
    thr = np.quantile(t, 0.75)
    m = t >= thr
    return _spearman_local(p[m], t[m]) if m.sum() >= 5 else float("nan")


def _dec(pred, true, q=0.9):
    p, t = np.asarray(pred, dtype=float), np.asarray(true, dtype=float)
    k = max(1, int(round(len(t) * (1 - q))))
    return len(set(np.argsort(-t)[:k].tolist()) & set(np.argsort(-p)[:k].tolist())) / k


if __name__ == "__main__":
    spans = [int(a) for a in sys.argv[1:]] or [3, 4]
    pool = H.build_pool("pit")
    for sp in spans:
        overfit_report(pool, sp)
        print(f"\n{'='*78}\n  HARNESS GATE  span={sp}\n{'='*78}")
        H.run_gate(CANDIDATES, span=sp, side="pit")
