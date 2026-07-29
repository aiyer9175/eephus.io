# Consensus lane (2026-07-25) -- shared dataset + stats helpers.
# ANALYSIS ONLY. Writes nothing outside tools/_cons_out/.
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
OUT = HERE / "_cons_out"
OUT.mkdir(exist_ok=True)


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _decision_year(r):
    """Mirror efv_model._decision_year: debut year for debuted, last prospect
    point year + 1 for busts (proxied here off asof_date)."""
    if r.get("kind") == "debuted" and r.get("debut_year"):
        return int(r["debut_year"])
    a = str(r.get("asof_date") or "")[:4]
    return int(a) + 1 if a.isdigit() else None


def load_matrix_rows():
    """One row per player from the shipped eFV matrices (the surface eFV consumes).

    Carries the RAW published per-source FVs (fv_published), the served consensus,
    the KM-censored first-6yr bWAR target, and the decision year for forward chaining.
    """
    rows = []
    for side, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        for r in json.loads((DATA / fn).read_text(encoding="utf-8")):
            tc = _f(r.get("target_censored"))
            if tc is None:
                continue
            cons = _f(r.get("consensus_fv_raw"))
            if cons is None:
                continue
            dy = _decision_year(r)
            if dy is None:
                continue
            asof = str(r.get("asof_date") or "")
            rows.append({
                "player_key": r["player_key"],
                "side": side,
                "kind": r["kind"],
                "decision_year": dy,
                "asof_year": int(asof[:4]) if asof[:4].isdigit() else None,
                "target": tc,
                "target_resolved": _f(r.get("target_resolved")),
                "weight": _f(r.get("weight")) or 1.0,
                "cons": cons,
                "pre": _f(r.get("consensus_fv_pre_shrinkage")),
                "fg": _f(r.get("fv_fangraphs")),
                "mp": _f(r.get("fv_mlb_pipeline")),
                "n_sources": int(_f(r.get("n_sources")) or 0),
                "is_ifa": bool(_f(r.get("is_ifa"))),
                "is_college": bool(_f(r.get("is_college"))),
                "pick_overall": _f(r.get("pick_overall")),
                "position": r.get("position"),
                "debut_year": r.get("debut_year"),
            })
    return rows


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def spearman(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 4:
        return None
    rx = _rank(x)
    ry = _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _rank(a):
    a = np.asarray(a, float)
    order = a.argsort(kind="mergesort")
    ranks = np.empty(len(a), float)
    ranks[order] = np.arange(len(a), dtype=float)
    # average ties
    sa = a[order]
    i = 0
    while i < len(sa):
        j = i
        while j + 1 < len(sa) and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def auc(scores, labels):
    scores = np.asarray(scores, float)
    labels = np.asarray(labels, bool)
    npos, nneg = labels.sum(), (~labels).sum()
    if npos == 0 or nneg == 0:
        return None
    r = _rank(scores) + 1.0
    return float((r[labels].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def cluster_bootstrap(keys, stat_fn, B=2000, seed=17):
    """Resample PLAYERS (clusters) with replacement, recompute stat_fn(idx).

    keys: array of cluster ids per row. stat_fn takes an index array.
    Returns (samples list). NaN draws dropped.
    """
    rng = random.Random(seed)
    keys = np.asarray(keys)
    uniq, inv = np.unique(keys, return_inverse=True)
    by_c = [np.where(inv == i)[0] for i in range(len(uniq))]
    n = len(uniq)
    out = []
    for _ in range(B):
        pick = [by_c[rng.randrange(n)] for _ in range(n)]
        idx = np.concatenate(pick)
        v = stat_fn(idx)
        if v is not None and np.isfinite(v):
            out.append(float(v))
    return out


def ci(samples, lo=2.5, hi=97.5):
    if not samples:
        return (None, None)
    a = np.asarray(samples, float)
    return (float(np.percentile(a, lo)), float(np.percentile(a, hi)))


def fmt(v, nd=4):
    return "None" if v is None else f"{v:.{nd}f}"
