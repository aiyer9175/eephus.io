# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""SHRINKAGE LANE: conditional (per-stratum) blend lambda for eFV.

HYPOTHESIS. The eFV blend is (1-lam)*consensus_OLS + lam*ridge with a single global
lam per side (0.70 hit / 0.54 pit). The premium the ridge adds over the consensus anchor
is measurably valuable at Triple-A overall (+0.35) and for speed-first bats (+0.47) but is
a measured NULL on old + below-median + Triple-A (-0.04, CI95 [-0.29,+0.20]). A global
lambda cannot express that. Test: shrink the ridge toward consensus ONLY in strata where
the premium has no out-of-fold signal.

LEAKAGE DISCIPLINE (the whole point). The per-stratum lambda is estimated with an INNER
forward chain inside each outer TRAIN fold. Outer test rows never touch stratum selection.
The stratum PARTITION is a fixed ex-ante function of (level_rank, age_rel_level, ops_rel)
declared before any lambda is fit.

ARMS
  BASE       shipped global lambda
  GLOB:x     degenerate alternative -- global lambda moved to x (requirement (d))
  HIER:k     12-cell ex-ante grid, hierarchical shrink lam_s = (n*lamhat_s + k*lam_g)/(n+k)
  GATE:dip   12-cell grid, hard gate: inner-OOF premium rho <= 0 -> lam_s = lam_g*(1-dip)
  TGT:dip    the lead's hand-named stratum only (AAA & age>=23.5 & ops_rel<0), rest global
  RAND:seed  zero-information control -- strata assigned at random with the SAME marginal
             sizes as the grid, same estimator, same gate (requirement (c))

METRICS (requirement (b)): pooled Spearman on the forward-chained OOS debuted rows, the
same restricted to the SERVED population (has a MiLB track record), t45, and the
debut/no-debut discrimination AUC in both framings.

Read-only. Writes nothing but its own JSON report.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import os; os.chdir(ROOT)

import efv_model as XM
from prospect_path import _spearman, _fit_ridge, _predict
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec, _decision_year, _vec
from efv_dataset import matrix_path

SCORED_YEARS = XM.SCORED_YEARS
LAM_GRID = [round(0.05 * i, 2) for i in range(21)]
MIN_STRAT_N = 25          # inner-OOF rows required before a stratum gets its own lambda
INNER_MIN_TRAIN = 50
INNER_MIN_TEST = 8


# ---------------------------------------------------------------- data

def _bucket(m):
    """Ex-ante stratum. Declared BEFORE any lambda is fit. None = unstratifiable."""
    if not isinstance(m, dict):
        return None
    lr, arl, ops = m.get("level_rank"), m.get("age_rel_level"), m.get("ops_rel")
    if lr is None or arl is None:
        return None
    lvl = "HIGH" if lr >= 5 else ("MID" if lr >= 4 else "LOW")
    ageb = "OLD" if arl >= 0 else "YOUNG"
    prod = "BELOW" if (ops is not None and ops < 0) else "ABOVE"
    return f"{lvl}/{ageb}/{prod}"


def _is_target(m):
    """The lead's hand-named Bradfield profile."""
    if not isinstance(m, dict):
        return False
    return (m.get("milb_level") == "AAA" and (m.get("age") or 0) >= 23.5
            and (m.get("ops_rel") or 0) < 0)


def load_all(side):
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        if r.get("consensus_fv_raw") is None:
            continue
        kind = r["kind"]
        if kind == "debuted" and r.get("target_censored") is None:
            continue
        m = r.get("milb") if isinstance(r.get("milb"), dict) else {}
        out.append({
            "player_key": r["player_key"],
            "kind": kind,
            "decision_year": _decision_year(r),
            "feats": _vec(r, side),
            "fv": float(r["consensus_fv_raw"]),
            "weight": float(r.get("weight", 1.0)),
            "target": (float(r["target_censored"]) if kind == "debuted" else None),
            "strat": _bucket(m),
            "served": bool(m.get("milb_level")),
            "is_target": _is_target(m),
        })
    return out


_CACHE = {}
def data_for(side):
    if side not in _CACHE:
        _CACHE[side] = load_all(side)
    return _CACHE[side]


# ---------------------------------------------------------------- stats

def _auc(scores, labels):
    pairs = sorted(zip(scores, labels))
    n = len(pairs)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    pos = [ranks[k] for k in range(n) if pairs[k][1] == 1]
    npos, nneg = len(pos), n - len(pos)
    if not npos or not nneg:
        return None
    return (sum(pos) - npos * (npos + 1) / 2) / (npos * nneg)


# ---------------------------------------------------------------- core fit

def _fit_fold(train_rows, keys):
    trf = [{"feats": r["feats"], "target": r["target"], "weight": r["weight"], "fv": r["fv"]}
           for r in train_rows if r["target"] is not None]
    if len(trf) < 40:
        return None, None
    ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target"]} for r in trf])
    ridge = _fit_ridge(trf, keys)
    return ols, ridge


def _inner_oof(train_rows, keys):
    """Inner forward chain INSIDE the outer train fold -> out-of-fold (rp, cw, y, strat)."""
    lab = [r for r in train_rows if r["target"] is not None]
    years = sorted({r["decision_year"] for r in lab})
    oof = []
    for y in years:
        itr = [r for r in lab if r["decision_year"] < y]
        ite = [r for r in lab if r["decision_year"] == y]
        if len(itr) < INNER_MIN_TRAIN or len(ite) < INNER_MIN_TEST:
            continue
        ols, ridge = _fit_fold(itr, keys)
        if not (ols and ridge):
            continue
        for r in ite:
            oof.append((_predict(ridge, r["feats"]), max(0.0, _pred_ols(ols, r["fv"])),
                        r["target"], r["strat"], r["is_target"]))
    return oof


def _lam_map(oof, lam_g, mode, param, strat_of_row=None):
    """Per-stratum lambda estimated from INNER-OOF train rows only."""
    if mode == "global":
        return {}, {}
    by = defaultdict(list)
    for rp, cw, y, s, tgt in oof:
        key = "TARGET" if (mode == "target" and tgt) else s
        if mode == "target" and not tgt:
            key = "REST"
        if key is None:
            continue
        by[key].append((rp, cw, y))
    lams, diag = {}, {}
    for s, g in by.items():
        if len(g) < MIN_STRAT_N:
            continue
        ys = [y for _, _, y in g]
        if mode in ("hier",):
            best, bl = None, lam_g
            for l in LAM_GRID:
                r = _spearman([(1 - l) * cw + l * rp for rp, cw, _ in g], ys)
                if r is not None and (best is None or r > best):
                    best, bl = r, l
            k = float(param)
            lams[s] = (len(g) * bl + k * lam_g) / (len(g) + k)
            diag[s] = {"n": len(g), "lamhat": bl, "lam_applied": round(lams[s], 4)}
        else:  # gate on the premium's own out-of-fold rank correlation
            rho_p = _spearman([rp - cw for rp, cw, _ in g], ys)
            if rho_p is not None and rho_p <= 0:
                lams[s] = lam_g * (1.0 - float(param))
            else:
                lams[s] = lam_g
            diag[s] = {"n": len(g), "rho_prem": round(rho_p, 4) if rho_p is not None else None,
                       "lam_applied": round(lams[s], 4)}
    return lams, diag


def run_arm(side, mode, param, rand_seed=None, collect_lams=False, rows=None):
    keys = _feature_spec(side)[0]
    lam_g = blend_lambda(side)
    if mode == "global":
        lam_g = float(param)
    if rows is None:
        rows = data_for(side)

    rnd = random.Random(rand_seed) if rand_seed is not None else None
    rand_assign = {}
    if rnd is not None:
        # same marginal sizes as the real grid, assignment permuted across players
        labelled = [r for r in rows if r["strat"] is not None]
        labels = [r["strat"] for r in labelled]
        rnd.shuffle(labels)
        for r, l in zip(labelled, labels):
            rand_assign[r["player_key"]] = l

    pooled, auc_rows, lam_log = [], [], {}
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        tr_lab = [r for r in tr if r["target"] is not None]
        te_lab = [r for r in te if r["target"] is not None]
        if len(te_lab) < 12 or len(tr_lab) < 50:
            continue
        ols, ridge = _fit_fold(tr, keys)
        if not (ols and ridge):
            continue

        if mode == "global":
            lams = {}
        else:
            if mode == "rand":
                oof = _inner_oof_rand(tr, keys, rand_assign)
                est_mode = "gate"
            else:
                oof = _inner_oof(tr, keys)
                est_mode = mode          # "hier" | "gate" | "target"
            lams, diag = _lam_map(oof, lam_g, est_mode, param)
            if collect_lams:
                lam_log[yr] = diag

        def lam_for(r):
            if mode == "global":
                return lam_g
            if mode == "target":
                return lams.get("TARGET" if r["is_target"] else "REST", lam_g)
            if mode == "rand":
                return lams.get(rand_assign.get(r["player_key"]), lam_g)
            return lams.get(r["strat"], lam_g)

        for r in te:
            rp = _predict(ridge, r["feats"])
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            l = lam_for(r)
            b = (1 - l) * cw + l * rp
            if r["target"] is not None:
                pooled.append({"b": b, "y": r["target"], "fv": r["fv"], "served": r["served"],
                               "strat": r["strat"], "is_target": r["is_target"],
                               "prem": rp - cw, "lam": l})
            auc_rows.append({"b": b, "lab": 1 if r["kind"] == "debuted" else 0,
                             "served": r["served"]})
    return pooled, auc_rows, lam_log


def _inner_oof_rand(train_rows, keys, rand_assign):
    lab = [r for r in train_rows if r["target"] is not None]
    years = sorted({r["decision_year"] for r in lab})
    oof = []
    for y in years:
        itr = [r for r in lab if r["decision_year"] < y]
        ite = [r for r in lab if r["decision_year"] == y]
        if len(itr) < INNER_MIN_TRAIN or len(ite) < INNER_MIN_TEST:
            continue
        ols, ridge = _fit_fold(itr, keys)
        if not (ols and ridge):
            continue
        for r in ite:
            oof.append((_predict(ridge, r["feats"]), max(0.0, _pred_ols(ols, r["fv"])),
                        r["target"], rand_assign.get(r["player_key"]), r["is_target"]))
    return oof


def summarize(pooled, auc_rows):
    def rho(sel):
        if len(sel) < 15:
            return None
        return _spearman([x["b"] for x in sel], [x["y"] for x in sel])
    served = [x for x in pooled if x["served"]]
    t45 = [x for x in pooled if round(x["fv"] / 5) * 5 == 45]
    tgt = [x for x in pooled if x["is_target"]]
    a_all = _auc([x["b"] for x in auc_rows], [x["lab"] for x in auc_rows])
    a_srv = _auc([x["b"] for x in auc_rows if x["served"]],
                 [x["lab"] for x in auc_rows if x["served"]])
    return {
        "n": len(pooled), "rho_pooled": rho(pooled),
        "n_served": len(served), "rho_served": rho(served),
        "n_t45": len(t45), "t45": rho(t45),
        "n_target": len(tgt), "rho_target": rho(tgt),
        "auc_pooled": a_all, "n_auc": len(auc_rows),
        "auc_served": a_srv, "n_auc_served": sum(1 for x in auc_rows if x["served"]),
    }
