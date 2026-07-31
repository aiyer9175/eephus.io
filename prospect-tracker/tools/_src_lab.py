# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Lane `sources`: test the five new data sources as eFV / FA model inputs.

MEASUREMENT ONLY. Nothing here edits efv_model.py or efv_dataset.py; candidate
columns are attached to a COPY of the prepped matrix rows and the shipped fold
engine is re-run with the extra ridge key. Every numeric claim is gated by
docs/EFV_GATE_STANDARD.md:
  (1) paired bootstrap resampling TRAIN and TEST with a refit per draw
  (2) a zero-information control (row-permuted twin of the SAME column)
  (3) a permutation null band
  (4) the effect averaged over the 4 forward-chained folds (2020-2023)

Stages:
  python tools/_src_lab.py cover     # coverage census (run FIRST, cheap)
  python tools/_src_lab.py feat <name>   # single-feature gate
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import efv_model as XM
from efv_model import _prep, _fit_ols_fv, _pred_ols, _feature_spec
from prospect_path import _spearman, _fit_ridge, _predict, _fit_linear_calibration
from efv_dataset import matrix_path

DATA = ROOT / "data"
SCORED_YEARS = XM.SCORED_YEARS          # (2020, 2021, 2022, 2023)
LAM = {"hit": 0.70, "pit": 0.61}        # shipped stamps, held fixed


# ---------------------------------------------------------------------------
# source loaders
# ---------------------------------------------------------------------------

def _j(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


_SRC = {}


def src(name):
    if name not in _SRC:
        _SRC[name] = _j(name + ".json")
    return _SRC[name]


def raw_rows(side):
    return json.loads(matrix_path(side).read_text(encoding="utf-8"))


def decision_year(r):
    return XM._decision_year(r)


# ---- TJ -------------------------------------------------------------------

def tj_index():
    return src("tj_surgery")["players"]


def tj_feats(mlbam, cutoff_year):
    """Surgeries strictly BEFORE cutoff_year. Returns dict or None when the
    player id is unknown to the sheet (absence != zero for coverage counting;
    the model column treats unknown as zero with a coverage indicator)."""
    ev = tj_index().get(str(mlbam))
    if ev is None:
        return None
    pre = [e for e in ev if e.get("year") is not None and int(e["year"]) < cutoff_year]
    if not pre:
        return {"tj_pre": 0.0, "tj_count": 0.0, "yrs_since": None}
    last = max(int(e["year"]) for e in pre)
    return {"tj_pre": 1.0, "tj_count": float(len(pre)),
            "yrs_since": float(cutoff_year - last)}


# ---- draft slot / bonus ---------------------------------------------------

def draft_index():
    return src("draft_bonus_slot")


# ---- amateur leagues ------------------------------------------------------

def amateur_index():
    return src("amateur_leagues")


# ---- pipeline vintages ----------------------------------------------------

def pipeline_index():
    """-> {year: {mlbam: rec}}"""
    v = src("pipeline_vintages")["vintages"]
    out = {}
    for yr, recs in v.items():
        m = {}
        for rec in recs:
            mid = rec.get("mlbam") or rec.get("mlbam_id") or (rec.get("player") or {}).get("id")
            if mid:
                m[str(mid)] = rec
        out[int(yr)] = m
    return out


# ---- venue ----------------------------------------------------------------

def venue_index():
    return src("venue_meta")


# ---------------------------------------------------------------------------
# scoring helpers (mirror tools/efv_improve_sweep_lab.py)
# ---------------------------------------------------------------------------

def _tier(fv):
    return round(fv / 5) * 5


def splits(recs):
    if len(recs) < 30:
        return {"n": len(recs), "error": "too few rows"}
    sp = _spearman([r[0] for r in recs], [r[1] for r in recs])
    byt = defaultdict(list)
    for p, t, fv, yr in recs:
        byt[_tier(fv)].append((p, t))
    t45 = None
    g = byt.get(45) or []
    if len(g) >= 15:
        r = _spearman([a for a, _ in g], [b for _, b in g])
        t45 = round(r, 4) if r is not None else None
    per_year = {}
    byy = defaultdict(list)
    for p, t, fv, yr in recs:
        byy[yr].append((p, t))
    for yr, gg in sorted(byy.items()):
        if len(gg) >= 12:
            r = _spearman([a for a, _ in gg], [b for _, b in gg])
            if r is not None:
                per_year[str(yr)] = round(r, 4)
    return {"n": len(recs), "spearman": round(sp, 4), "t45": t45, "per_year": per_year}


def block_rho(recs_by_side):
    """(side x cohort-year) block-normalized pooled Spearman, both sides pooled."""
    zs, zt = [], []
    for side, recs in recs_by_side.items():
        by = defaultdict(list)
        for p, t, fv, yr in recs:
            by[yr].append((p, t))
        for yr, g in by.items():
            if len(g) < 8:
                continue
            pr = _ranks([a for a, _ in g])
            tr = _ranks([b for _, b in g])
            n = len(g)
            for i in range(n):
                zs.append((pr[i] - (n + 1) / 2) / n)
                zt.append((tr[i] - (n + 1) / 2) / n)
    if len(zs) < 30:
        return None
    return _spearman(zs, zt)


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    rk = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            rk[order[k]] = avg
        i = j + 1
    return rk


def auc(pred, lab):
    pos = [p for p, l in zip(pred, lab) if l]
    neg = [p for p, l in zip(pred, lab) if not l]
    if not pos or not neg:
        return None
    allv = pos + neg
    rk = _ranks(allv)
    rsum = sum(rk[: len(pos)])
    return (rsum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


# ---------------------------------------------------------------------------
# fold engine with an extra feature column
# ---------------------------------------------------------------------------

def folds(data, side, extra_keys=(), lam=None):
    keys, _mono = _feature_spec(side)
    keys = list(keys) + list(extra_keys)
    lam = LAM[side] if lam is None else lam
    out = defaultdict(list)
    for yr in SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = _fit_ols_fv(train)
        ridge = _fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        cal = _fit_linear_calibration(
            [(_predict(ridge, r["feats"]), r["target"]) for r in train])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in test:
            cons = max(0.0, _pred_ols(ols, r["fv"]))
            rp = a + b * _predict(ridge, r["feats"])
            out["baseline"].append((cons, r["target"], r["fv"], yr))
            out["ridge"].append((rp, r["target"], r["fv"], yr))
            out["blend"].append(((1 - lam) * cons + lam * rp, r["target"], r["fv"], yr))
    return out


def paired_boot(data, side, extra_keys, B=400, seed=11):
    """Paired bootstrap: resample the WHOLE pool (train AND test share the draw)
    and refit both arms on every draw. Returns the delta distribution."""
    rnd = random.Random(seed)
    n = len(data)
    deltas = []
    for _b in range(B):
        idx = [rnd.randrange(n) for _ in range(n)]
        draw = [data[i] for i in idx]
        base = folds(draw, side)
        cand = folds(draw, side, extra_keys)
        rb = _spearman([r[0] for r in base["blend"]], [r[1] for r in base["blend"]])
        rc = _spearman([r[0] for r in cand["blend"]], [r[1] for r in cand["blend"]])
        if rb is None or rc is None:
            continue
        deltas.append(rc - rb)
    deltas.sort()
    return deltas


def pct(xs, q):
    if not xs:
        return None
    i = max(0, min(len(xs) - 1, int(round(q * (len(xs) - 1)))))
    return xs[i]


def summarize(deltas):
    if not deltas:
        return {}
    m = sum(deltas) / len(deltas)
    sd = math.sqrt(sum((d - m) ** 2 for d in deltas) / max(1, len(deltas) - 1))
    return {"mean": round(m, 5), "sd": round(sd, 5),
            "ci95": [round(pct(deltas, 0.025), 5), round(pct(deltas, 0.975), 5)],
            "p_gt0": round(sum(1 for d in deltas if d > 0) / len(deltas), 3),
            "B": len(deltas)}


def attach(data, rows_by_key, col_fn, names):
    """Return a NEW prepped list with extra feature keys attached."""
    out = []
    for r in data:
        raw = rows_by_key.get(r["player_key"])
        vals = col_fn(raw, r) if raw is not None else {k: 0.0 for k in names}
        rr = dict(r)
        rr["feats"] = {**r["feats"], **{k: float(vals.get(k, 0.0)) for k in names}}
        out.append(rr)
    return out


def permute_col(data, names, seed=5):
    """Zero-information control: row-permute the SAME columns (identical marginal)."""
    rnd = random.Random(seed)
    vals = [[r["feats"][k] for k in names] for r in data]
    idx = list(range(len(data)))
    rnd.shuffle(idx)
    out = []
    for i, r in enumerate(data):
        rr = dict(r)
        rr["feats"] = {**r["feats"], **{k: vals[idx[i]][j] for j, k in enumerate(names)}}
        out.append(rr)
    return out


if __name__ == "__main__":
    print("import-only module; run the stage scripts")
