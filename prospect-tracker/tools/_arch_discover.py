# scratch lab (lane: discover) -- archetype discovery on the resolved pool.
# NOT part of the build. Writes only to the scratchpad.
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from efv_model import (_decision_year, _feature_spec, _fit_ols_fv, _pred_ols,
                       _prep, _vec)                                    # noqa: E402
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration  # noqa: E402

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
SCRATCH.mkdir(parents=True, exist_ok=True)

LAM = {"hit": 0.70, "pit": 0.80}
TEST_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
RESOLVED_YEARS = (2016, 2017, 2018, 2019, 2020)


def load(side):
    name = "hitter" if side == "hit" else "pitcher"
    rows = json.loads((ROOT / "data" / f"xfv_{name}_matrix.json").read_text(encoding="utf-8"))
    return [r for r in rows if not (r.get("kind") == "bust" and r.get("bust_recent"))]


def oof(side, target_key="target_censored", years=TEST_YEARS):
    """Shipped-faithful forward-chained out-of-fold predictions.

    Train on every non-bust_recent row with decision_year < Y using the SHIPPED
    feature set, KM sample weights and target_censored; predict rows with
    decision_year == Y. Blend = (1-lam)*consensus_OLS + lam*calibrated ridge.
    """
    rows = load(side)
    keys, _m = _feature_spec(side)
    data = _prep(rows, "target_censored", side)
    by_key = {r["player_key"]: r for r in rows}
    out = []
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(tr) < 80 or not te:
            continue
        ridge = _fit_ridge(tr, keys)
        ols = _fit_ols_fv(tr)
        if not ridge or not ols:
            continue
        raw_tr = [(_predict(ridge, r["feats"]), r["target"]) for r in tr]
        cal = _fit_linear_calibration(raw_tr)
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        lam = LAM[side]
        for r in te:
            src = by_key[r["player_key"]]
            tgt = src.get(target_key)
            if tgt is None:
                continue
            rg = a + b * _predict(ridge, r["feats"])
            ol = _pred_ols(ols, r["fv"])
            out.append({
                "player_key": r["player_key"], "kind": r["kind"], "year": yr,
                "target": float(tgt), "target_resolved": src.get("target_resolved"),
                "target_censored": src.get("target_censored"),
                "censored": bool(src.get("censored")),
                "weight": float(src.get("weight", 1.0) or 1.0),
                "pred": (1 - lam) * ol + lam * rg, "pred_ridge": rg, "pred_ols": ol,
                "fv": r["fv"], "feats": r["feats"], "has_milb": bool(src.get("milb")),
                "milb": src.get("milb") or {}, "position": src.get("position"),
                "tool_hit": src.get("tool_hit"), "tool_game_pwr": src.get("tool_game_pwr"),
                "tool_raw_pwr": src.get("tool_raw_pwr"), "tool_speed": src.get("tool_speed"),
                "tool_field": src.get("tool_field"), "tool_fb": src.get("tool_fb"),
                "tool_cmd": src.get("tool_cmd"),
                "is_college": src.get("is_college"), "is_ifa": src.get("is_ifa"),
            })
    for r in out:
        r["resid"] = r["target"] - r["pred"]
    return out


# --------------------------------------------------------------------------
# archetype feature space (track-record rows only -- the served-board population)
# --------------------------------------------------------------------------
_MID = ("C", "SS", "2B", "CF")
_TOOL_D = {"tool_hit": 47.9, "tool_speed": 50.7, "tool_game_pwr": 45.0,
           "tool_field": 45.0, "tool_raw_pwr": 50.0, "tool_fb": 58.0, "tool_cmd": 45.0}

CLUSTER_KEYS_HIT = ["age", "age_rel_level", "level_rank", "n_milb_seasons",
                    "k_rel", "bb_rel", "iso_rel", "obp_rel", "prod_trend",
                    "peak_iso_rel", "peak_k_rel",
                    "tool_hit", "tool_game_pwr", "tool_speed", "tool_field",
                    "is_mid", "is_college", "is_ifa"]
CLUSTER_KEYS_PIT = ["age", "age_rel_level", "level_rank", "n_milb_seasons",
                    "k_rel", "bb_rel", "era_rel", "peak_k_rel", "peak_bb_rel",
                    "tool_fb", "tool_cmd", "is_college", "is_ifa"]


def cfeat(r, side):
    m = r["milb"] or {}
    def g(v, d=0.0):
        return float(v) if v is not None else d
    pos = (r.get("position") or "").split("/")[0].strip().upper()
    d = {
        "age": g(m.get("age"), 22.5), "age_rel_level": g(m.get("age_rel_level")),
        "level_rank": g(m.get("level_rank")), "n_milb_seasons": min(g(m.get("n_milb_seasons")), 8.0),
        "k_rel": g(m.get("k_rel")), "bb_rel": g(m.get("bb_rel")),
        "iso_rel": g(m.get("iso_rel")), "obp_rel": g(m.get("obp_rel")),
        "ops_rel": g(m.get("ops_rel")), "prod_trend": g(m.get("prod_trend")),
        "peak_iso_rel": g(m.get("peak_iso_rel")), "peak_k_rel": g(m.get("peak_k_rel")),
        "peak_ops_rel": g(m.get("peak_ops_rel")), "era_rel": g(m.get("era_rel")),
        "peak_bb_rel": g(m.get("peak_bb_rel")),
        "is_mid": 1.0 if pos in _MID else 0.0,
        "is_college": g(r.get("is_college")), "is_ifa": g(r.get("is_ifa")),
    }
    for t, dv in _TOOL_D.items():
        d[t] = g(r.get(t), dv)
    return d


def zmat(rowfeats, keys, mu=None, sd=None):
    X = np.array([[f[k] for k in keys] for f in rowfeats], dtype=float)
    if mu is None:
        mu, sd = X.mean(axis=0), X.std(axis=0)
        sd = np.where(sd == 0, 1.0, sd)
    return (X - mu) / sd, mu, sd


# --------------------------------------------------------------------------
# decisive statistic: archetype eta^2 on the out-of-fold residual
# --------------------------------------------------------------------------
def eta2(labels, resid, w=None):
    """Weighted between-group share of residual variance. Groups with n<2 fold
    into their own cell (they still cost a dof, which the control band prices)."""
    labels = np.asarray(labels)
    resid = np.asarray(resid, dtype=float)
    w = np.ones_like(resid) if w is None else np.asarray(w, dtype=float)
    gm = np.average(resid, weights=w)
    sst = float(np.sum(w * (resid - gm) ** 2))
    if sst <= 0:
        return 0.0
    ssb = 0.0
    for g in np.unique(labels):
        i = labels == g
        if w[i].sum() <= 0:
            continue
        ssb += float(w[i].sum()) * (float(np.average(resid[i], weights=w[i])) - gm) ** 2
    return ssb / sst


def control_band(labels, resid, w=None, B=4000, seed=11):
    """Zero-information twin: the SAME label vector row-permuted, so the marginal
    group sizes are identical and only the row<->outcome pairing is destroyed."""
    rng = np.random.default_rng(seed)
    lab = np.asarray(labels)
    vals = np.empty(B)
    for i in range(B):
        vals[i] = eta2(rng.permutation(lab), resid, w)
    return vals


def blockwise(rows, key="year"):
    """Residuals centred within (year) block so a year-composition artifact cannot
    masquerade as archetype signal."""
    out = []
    for yr in sorted({r[key] for r in rows}):
        sub = [r for r in rows if r[key] == yr]
        w = np.array([r["weight"] for r in sub])
        rs = np.array([r["resid"] for r in sub])
        m = np.average(rs, weights=w) if w.sum() > 0 else rs.mean()
        for r, v in zip(sub, rs - m):
            q = dict(r)
            q["resid_bw"] = float(v)
            out.append(q)
    return out


def boot_ci(x, w=None, B=4000, seed=5):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    w = np.ones_like(x) if w is None else np.asarray(w, dtype=float)
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"))
    m = np.empty(B)
    for i in range(B):
        idx = rng.integers(0, n, n)
        ww = w[idx]
        m[i] = np.average(x[idx], weights=ww) if ww.sum() > 0 else x[idx].mean()
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))
