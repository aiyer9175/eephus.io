# ADVERSARIAL VERIFY of lane "discover". Independent re-derivation.
# Writes nothing outside the scratchpad. Not part of the build.
from __future__ import annotations

import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from efv_model import _decision_year, _feature_spec, _fit_ols_fv, _pred_ols, _prep  # noqa
from prospect_path import _fit_ridge, _fit_linear_calibration, _predict            # noqa
from _arch_theory import theory_hit, theory_pit                                    # noqa

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")

LAM = {"hit": 0.70, "pit": 0.80}
YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)

_MID = ("C", "SS", "2B", "CF")
_TOOL_D = {"tool_hit": 47.9, "tool_speed": 50.7, "tool_game_pwr": 45.0,
           "tool_field": 45.0, "tool_raw_pwr": 50.0, "tool_fb": 58.0, "tool_cmd": 45.0}
CK_HIT = ["age", "age_rel_level", "level_rank", "n_milb_seasons",
          "k_rel", "bb_rel", "iso_rel", "obp_rel", "prod_trend",
          "peak_iso_rel", "peak_k_rel",
          "tool_hit", "tool_game_pwr", "tool_speed", "tool_field",
          "is_mid", "is_college", "is_ifa"]
CK_PIT = ["age", "age_rel_level", "level_rank", "n_milb_seasons",
          "k_rel", "bb_rel", "era_rel", "peak_k_rel", "peak_bb_rel",
          "tool_fb", "tool_cmd", "is_college", "is_ifa"]
CK = {"hit": CK_HIT, "pit": CK_PIT}


def load(side):
    name = "hitter" if side == "hit" else "pitcher"
    rows = json.loads((ROOT / "data" / f"xfv_{name}_matrix.json").read_text(encoding="utf-8"))
    return [r for r in rows if not (r.get("kind") == "bust" and r.get("bust_recent"))]


def cfeat(r):
    m = r.get("milb") or {}
    def g(v, d=0.0):
        return float(v) if v is not None else d
    pos = (r.get("position") or "").split("/")[0].strip().upper()
    d = {"age": g(m.get("age"), 22.5), "age_rel_level": g(m.get("age_rel_level")),
         "level_rank": g(m.get("level_rank")),
         "n_milb_seasons": min(g(m.get("n_milb_seasons")), 8.0),
         "k_rel": g(m.get("k_rel")), "bb_rel": g(m.get("bb_rel")),
         "iso_rel": g(m.get("iso_rel")), "obp_rel": g(m.get("obp_rel")),
         "ops_rel": g(m.get("ops_rel")), "prod_trend": g(m.get("prod_trend")),
         "peak_iso_rel": g(m.get("peak_iso_rel")), "peak_k_rel": g(m.get("peak_k_rel")),
         "peak_ops_rel": g(m.get("peak_ops_rel")), "era_rel": g(m.get("era_rel")),
         "peak_bb_rel": g(m.get("peak_bb_rel")),
         "is_mid": 1.0 if pos in _MID else 0.0,
         "is_college": g(r.get("is_college")), "is_ifa": g(r.get("is_ifa"))}
    for t, dv in _TOOL_D.items():
        d[t] = g(r.get(t), dv)
    return d


def oof(side):
    """My own forward-chained OOF. Independent of _arch_discover."""
    rows = load(side)
    keys, _ = _feature_spec(side)
    data = _prep(rows, "target_censored", side)
    by_key = {r["player_key"]: r for r in rows}
    out = []
    for yr in YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(tr) < 80 or not te:
            continue
        ridge = _fit_ridge(tr, keys)
        ols = _fit_ols_fv(tr)
        if not ridge or not ols:
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        lam = LAM[side]
        for r in te:
            src = by_key[r["player_key"]]
            pred = (1 - lam) * _pred_ols(ols, r["fv"]) + lam * (a + b * _predict(ridge, r["feats"]))
            out.append({"player_key": r["player_key"], "year": yr, "kind": r["kind"],
                        "target": r["target"], "pred": pred, "resid": r["target"] - pred,
                        "weight": float(src.get("weight", 1.0)),
                        "censored": bool(src.get("censored")),
                        "target_resolved": src.get("target_resolved"),
                        "fv": r["fv"], "has_milb": bool(src.get("milb")),
                        "src": src})
    return out


def center_by_year(rows, field, wf="weight"):
    v = np.array([r[field] for r in rows], float)
    w = np.array([r[wf] for r in rows], float)
    idx = defaultdict(list)
    for i, r in enumerate(rows):
        idx[r["year"]].append(i)
    out = v.copy()
    for _y, ii in idx.items():
        ii = np.array(ii)
        m = np.average(v[ii], weights=w[ii]) if w[ii].sum() > 0 else v[ii].mean()
        out[ii] = v[ii] - m
    return out


def eta2(lab, y, w):
    gm = np.average(y, weights=w)
    sst = float(np.sum(w * (y - gm) ** 2))
    if sst <= 0:
        return 0.0
    ssb = 0.0
    for g in np.unique(lab):
        i = lab == g
        ww = w[i].sum()
        if ww <= 0:
            continue
        ssb += ww * (float(np.average(y[i], weights=w[i])) - gm) ** 2
    return ssb / sst


def perm_test(rows, labels, field, B=3000, seed=101, weighted=True):
    y = center_by_year(rows, field)
    w = np.array([r["weight"] for r in rows], float) if weighted else np.ones(len(rows))
    lab = np.asarray(labels)
    obs = eta2(lab, y, w)
    rng = np.random.default_rng(seed)
    blocks = defaultdict(list)
    for i, r in enumerate(rows):
        blocks[r["year"]].append(i)
    blocks = {k: np.array(v) for k, v in blocks.items()}
    null = np.empty(B)
    for b in range(B):
        pl = lab.copy()
        for ii in blocks.values():
            pl[ii] = rng.permutation(lab[ii])
        null[b] = eta2(pl, y, w)
    return {"obs": float(obs), "null_mean": float(null.mean()),
            "p95": float(np.percentile(null, 95)), "p": float((null >= obs).mean()),
            "n": len(rows), "k": int(len(np.unique(lab)))}
