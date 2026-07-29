# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- STEP 3: does the refit beat the shipped map OUT OF SAMPLE?

Everything is evaluated on PRODUCTION-SCALE predictions (scale=norm), because that
is what production actually feeds the calibration. The arms differ only in the map
applied on top of the SAME predictions:

  shipped     max(0, 1.382491*p - 2.318551)   fit on the RAW-scale pool
  refit_ols   max(0, a*p + b), OLS on the TRAIN fold   (mean-calibrated)
  refit_lad   max(0, a*p + b), LAD  on the TRAIN fold   (v5's own stated objective:
              minimise held-out MAE -- refit here so the comparison is like-for-like)
  identity    p                               no calibration at all
  zeroinfo    TRAIN-fold mean realized        zero-information control

Splits: forward-chained. mode="expanding" trains on every earlier listing year;
mode="rolling3" trains on the 3 immediately preceding years (the pool's coverage
broadens over time, so an expanding window trains on a different population than
it tests on -- both are reported rather than picking the flattering one).
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from _dpw_RECAL_fit import (SCRATCH, SHIPPED, apply_map, cov_rate,       # noqa: E402
                            coverage, fit_floored_linear, metrics, prep,
                            set_regime)

DRAWS = 2000
SEED = 20260725
TIERS = [(40, 45), (45, 50), (50, 55), (55, 100)]
ARMS = ("refit_ols", "refit_lad", "shipped", "identity", "zeroinfo")


def fit_lad(pred: np.ndarray, real: np.ndarray, start=None) -> tuple[float, float]:
    """LAD fit of the FLOORED linear map -- the objective linearmap-v5's own
    provenance names ('minimize held-out MAE'). Nelder-Mead from the OLS point."""
    from scipy.optimize import minimize
    p = np.asarray(pred, float); r = np.asarray(real, float)
    x0 = np.array(start if start is not None else fit_floored_linear(p, r), float)

    def obj(x):
        return float(np.abs(r - np.maximum(0.0, x[0] * p + x[1])).mean())
    res = minimize(obj, x0, method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-5, "maxiter": 800})
    return float(res.x[0]), float(res.x[1])


def _blank(c, r):
    return {"n": int(len(c)), "slope": float("nan"), "intercept": float("nan"),
            "r2": float("nan"), "bias": float((r - c).mean()),
            "mae": float(np.abs(r - c).mean()),
            "rmse": float(np.sqrt(((r - c) ** 2).mean())), "spearman": float("nan")}


def arm_eval(name, coef, d, idx_tr, idx_te, const=None) -> dict:
    p_te = d["pred"][idx_te]
    r_te = d["real"][idx_te]
    if const is not None:
        c_te = np.full(len(p_te), const)
        pits = None
    else:
        c_te = apply_map(coef, p_te)
        pits, _ = coverage(coef, d["pred"][idx_tr], d["real"][idx_tr],
                           p_te, r_te, d["draws"][idx_te])
    out = {"arm": name, "coef": list(coef) if coef else None,
           "floored_frac": float((c_te == 0).mean())}
    out.update(metrics(c_te, r_te) if len(np.unique(c_te)) > 1 else _blank(c_te, r_te))
    if pits is not None:
        out["coverage"] = cov_rate(pits)
        out["pits"] = pits
    out["corrected"] = c_te
    return out


def train_idx(d, ty, mode):
    if mode == "rolling3":
        return np.flatnonzero((d["year"] < ty) & (d["year"] >= ty - 3))
    return np.flatnonzero(d["year"] < ty)


def run(pool_name: str, dpw: str, anchors: str, *, target="today",
        scale="norm", gate="raw", mode="expanding", n_perm=200) -> dict:
    anch_tbl = json.loads((SCRATCH / "recal_anchors.json").read_text())["norm"]["anchors"]
    info = set_regime(dpw, anchors, anch_tbl)
    pool = pickle.loads((SCRATCH / f"recal_pool_{pool_name}.pkl").read_bytes())
    d = prep(pool, scale=scale, gate=gate, target=target, draws=DRAWS)
    years = sorted(set(d["year"].tolist()))
    rng = np.random.default_rng(SEED)

    folds = []
    for i, ty in enumerate(years):
        if i == 0:
            continue
        idx_tr = train_idx(d, ty, mode)
        idx_te = np.flatnonzero(d["year"] == ty)
        if len(idx_tr) < 50 or len(idx_te) < 20:
            continue
        ols = fit_floored_linear(d["pred"][idx_tr], d["real"][idx_tr])
        lad = fit_lad(d["pred"][idx_tr], d["real"][idx_tr], start=ols)
        arms = {
            "refit_ols": arm_eval("refit_ols", ols, d, idx_tr, idx_te),
            "refit_lad": arm_eval("refit_lad", lad, d, idx_tr, idx_te),
            "shipped": arm_eval("shipped", SHIPPED, d, idx_tr, idx_te),
            "identity": arm_eval("identity", (1.0, 0.0), d, idx_tr, idx_te),
            "zeroinfo": arm_eval("zeroinfo", None, d, idx_tr, idx_te,
                                 const=float(d["real"][idx_tr].mean())),
        }
        perm = {"mae": [], "rmse": [], "bias": []}
        for _ in range(n_perm):
            pm = rng.permutation(idx_tr)
            c = fit_floored_linear(d["pred"][idx_tr], d["real"][pm])
            e = d["real"][idx_te] - apply_map(c, d["pred"][idx_te])
            perm["mae"].append(float(np.abs(e).mean()))
            perm["rmse"].append(float(np.sqrt((e ** 2).mean())))
            perm["bias"].append(float(e.mean()))
        folds.append({"test_year": int(ty), "n_train": int(len(idx_tr)),
                      "n_test": int(len(idx_te)), "ols": list(ols), "lad": list(lad),
                      "arms": arms, "perm": perm,
                      "idx_te": idx_te, "idx_tr": idx_tr})
    return {"info": info, "d": d, "folds": folds, "years": years, "mode": mode,
            "regime": {"pool": pool_name, "dpw": dpw, "anchors": anchors,
                       "target": target, "scale": scale, "gate": gate, "mode": mode}}


def pooled(res: dict) -> dict:
    d = res["d"]
    out = {}
    idx = np.concatenate([f["idx_te"] for f in res["folds"]])
    r = d["real"][idx]
    fv = d["fv"][idx]
    pit_role = d["is_pit"][idx]
    for arm in ARMS:
        c = np.concatenate([f["arms"][arm]["corrected"] for f in res["folds"]])
        m = metrics(c, r) if len(np.unique(c)) > 1 else _blank(c, r)
        row = {"metrics": m, "floored_frac": float((c == 0).mean()),
               "aggregate_pred_musd": float(c.sum()),
               "aggregate_real_musd": float(r.sum())}
        if "pits" in res["folds"][0]["arms"][arm]:
            p = np.concatenate([f["arms"][arm]["pits"] for f in res["folds"]])
            row["coverage_marginal"] = cov_rate(p)
            row["coverage_by_tier"] = {}
            for lo, hi in TIERS:
                sel = (fv >= lo) & (fv < hi)
                if sel.sum() >= 20:
                    row["coverage_by_tier"][f"{lo}-{hi if hi<100 else 80}"] = {
                        "n": int(sel.sum()), "cov": cov_rate(p[sel])}
            row["coverage_by_role"] = {
                "hitter": {"n": int((~pit_role).sum()), "cov": cov_rate(p[~pit_role])},
                "pitcher": {"n": int(pit_role.sum()), "cov": cov_rate(p[pit_role])}}
            row["coverage_by_outcome"] = {
                "realized_zero": {"n": int((r == 0).sum()), "cov": cov_rate(p[r == 0])},
                "realized_pos": {"n": int((r > 0).sum()), "cov": cov_rate(p[r > 0])}}
        row["reliability_by_tier"] = {}
        for lo, hi in TIERS:
            sel = (fv >= lo) & (fv < hi)
            if sel.sum() >= 20:
                row["reliability_by_tier"][f"{lo}-{hi if hi<100 else 80}"] = {
                    "n": int(sel.sum()), "pred_mean": float(c[sel].mean()),
                    "real_mean": float(r[sel].mean()),
                    "mae": float(np.abs(r[sel] - c[sel]).mean()),
                    "rmse": float(np.sqrt(((r[sel] - c[sel]) ** 2).mean()))}
        out[arm] = row
    return out
