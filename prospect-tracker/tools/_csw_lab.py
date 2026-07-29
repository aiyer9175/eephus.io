# SCRATCH (cswpitch lane). Read-only w.r.t. shipped code: builds the candidate
# csw_rel / swstr_rel columns from data/milb_pitch_rates.json, appends them to a
# numpy replica of the PRODUCTION pitcher fit, and runs the four mandatory controls
# from docs/EFV_GATE_STANDARD.md:
#   (1) paired bootstrap resampling TRAIN and TEST with a refit each draw
#   (2) a zero-information control = the SAME column row-permuted (same marginal)
#   (3) a permutation null band for the same delta
#   (4) the delta averaged over >= 4 independent forward-chained time splits
# Floor for an incremental pitcher feature add: 0.016 pooled rho (block-rho 0.0149).
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                          # noqa: E402
from _frontier_ablate import (ridge_fit, ridge_pred, ols_fit, lincal, rho,   # noqa: E402
                              _rankavg, LAM)

OUT = ROOT / "tools" / "_csw_out"
OUT.mkdir(exist_ok=True)
SEED = 20260725
SIDE = "pit"
# 6 forward-chained folds; the 4-fold gate window (2020-2023) is what the shipped
# eval scores and what the 0.016 floor was measured on.
ORIGINS = (2019, 2020, 2021, 2022, 2023, 2024)
GATE_ORIGINS = (2020, 2021, 2022, 2023)
RATES_PATH = ROOT / "data" / "milb_pitch_rates.json"


# --------------------------------------------------------------------- data
def _load_pitch_features() -> dict:
    """{(mlbam, season, level): rel-rate block} from the lane's ingest artifact."""
    if not RATES_PATH.exists():
        return {}
    d = json.loads(RATES_PATH.read_text(encoding="utf-8"))
    out = {}
    for key, v in (d.get("features") or {}).items():
        pid, season, level = key.split("|")
        out[(int(pid), int(season), level)] = v
    return out


def load(side: str = SIDE, *, extra_cols: int = 24):
    raw = json.loads((ROOT / "data" / ("xfv_pitcher_matrix.json" if side == "pit"
                                       else "xfv_hitter_matrix.json")).read_text("utf-8"))
    prep = E._prep(raw, "target_censored", side)
    assert len(prep) == len(raw)
    keys = list(E._feature_spec(side)[0])
    n = len(prep)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    y = np.array([r["target"] for r in prep], dtype=float)
    w = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None)
    fv = np.array([r["fv"] for r in prep], dtype=float)
    dy = np.array([r["decision_year"] for r in prep], dtype=int)
    deb = np.array([r["kind"] == "debuted" for r in prep])
    keep = np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                     for r, o in zip(prep, raw)])

    pf = _load_pitch_features()
    csw = np.zeros(n); swstr = np.zeros(n); pit = np.zeros(n)
    matched = np.zeros(n, dtype=bool)
    has_milb = np.zeros(n, dtype=bool)
    lvl = np.array(["" for _ in range(n)], dtype=object)
    for i, o in enumerate(raw):
        m = o.get("milb") or {}
        if m.get("milb_season"):
            has_milb[i] = True
            lvl[i] = m.get("milb_level") or ""
        k = (o.get("mlbam_id"), m.get("milb_season"), m.get("milb_level"))
        if None in k or not o.get("mlbam_id"):
            continue
        v = pf.get((int(k[0]), int(k[1]), k[2]))
        if v is None:
            continue
        csw[i] = v["csw_rel"]; swstr[i] = v["swstr_rel"]; pit[i] = v["pitches"]
        matched[i] = True

    rng = np.random.default_rng(SEED)
    names = list(keys)
    cols = [X[:, j] for j in range(X.shape[1])]

    def add(nm, col):
        names.append(nm); cols.append(np.asarray(col, dtype=float))

    add("csw_rel", csw)
    add("swstr_rel", swstr)
    # zero-information controls: the SAME column row-permuted (identical marginal,
    # identical sparsity pattern, no information), plus plain gaussian noise.
    for t in range(extra_cols):
        add(f"~perm_csw~{t}", csw[rng.permutation(n)])
    for t in range(extra_cols):
        add(f"~perm_swstr~{t}", swstr[rng.permutation(n)])
    # STRICTER zero-information twin: permute only WITHIN the matched rows, so the
    # control keeps csw_rel's exact sparsity pattern (zeros stay on the same rows)
    # as well as its marginal. Without this, a plain full-pool permutation also
    # scrambles which rows are covered, which is itself information.
    mi = np.flatnonzero(matched)
    for t in range(extra_cols):
        c = csw.copy(); c[mi] = csw[rng.permutation(mi)]
        add(f"~permin_csw~{t}", c)
    for t in range(extra_cols):
        c = swstr.copy(); c[mi] = swstr[rng.permutation(mi)]
        add(f"~permin_swstr~{t}", c)
    for t in range(extra_cols):
        add(f"~noise~{t}", rng.standard_normal(n))
    Xa = np.column_stack(cols)
    return dict(side=side, X=Xa, y=y, w=w, fv=fv, dy=dy, deb=deb, keep=keep,
                names=names, idx={k: i for i, k in enumerate(names)}, keys=keys,
                csw=csw, swstr=swstr, pitches=pit, matched=matched,
                has_milb=has_milb, level=lvl, n=n, rng=rng)


# --------------------------------------------------------------------- scoring
def score(D, cols, sel=None, origins=ORIGINS, lam=None, full_test=False):
    """Forward-chained production-config score. Returns (block, pred, target, debuted).

    full_test=False -> test on DEBUTED rows only (the shipped rank eval).
    full_test=True  -> test on every eligible row (for the debut/no-debut AUC)."""
    X, y, w, fv, dy, deb, keep = D["X"], D["y"], D["w"], D["fv"], D["dy"], D["deb"], D["keep"]
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = X[sel][:, cols], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps = deb[sel], keep[sel]
    lam = LAM[D["side"]] if lam is None else lam
    B, P, T, Dd, IX = [], [], [], [], []
    for yr in origins:
        tr = np.flatnonzero(keeps & (dys < yr))
        te = np.flatnonzero((keeps if full_test else debs) & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        a, b = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
        mod = np.maximum(-2.0, a + b * ridge_pred(rg, Xs[te]))
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr))
        P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te])
        Dd.append(debs[te])
        IX.append(sel[te])                 # original row index of each test row
    if not P:
        return None
    return (np.concatenate(B), np.concatenate(P), np.concatenate(T),
            np.concatenate(Dd), np.concatenate(IX))


def pooled_rho(r, origins=None, mask=None):
    """Pooled Spearman over the test rows, optionally restricted to `mask`
    (a boolean array over ORIGINAL row indices, for the subgroup cuts)."""
    if r is None:
        return float("nan")
    b, p, t, _d, ix = r
    m = np.isin(b, origins) if origins else np.ones(len(b), dtype=bool)
    if mask is not None:
        m = m & mask[ix]
    return rho(p[m], t[m]) if m.sum() >= 8 else float("nan")


def block_rho(r, origins=None):
    if r is None:
        return float("nan")
    b, p, t, _d, _ix = r
    PP, TT = [], []
    for yr in np.unique(b):
        if origins and yr not in origins:
            continue
        m = b == yr
        if m.sum() < 8:
            continue
        k = int(m.sum())
        PP.append((_rankavg(p[m]) - 0.5) / k)
        TT.append((_rankavg(t[m]) - 0.5) / k)
    if not PP:
        return float("nan")
    return rho(np.concatenate(PP), np.concatenate(TT))


def auc(r, origins=None):
    """Full-pool debut / no-debut discrimination AUC (block-normalized by fold)."""
    if r is None:
        return float("nan")
    b, p, t, d, _ix = r
    S, L = [], []
    for yr in np.unique(b):
        if origins and yr not in origins:
            continue
        m = b == yr
        if m.sum() < 8:
            continue
        S.append((_rankavg(p[m]) - 0.5) / int(m.sum()))
        L.append(d[m])
    if not S:
        return float("nan")
    s = np.concatenate(S); lab = np.concatenate(L).astype(bool)
    npos, nneg = int(lab.sum()), int((~lab).sum())
    if not npos or not nneg:
        return float("nan")
    rk = _rankavg(s)
    return float((rk[lab].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def per_fold_rho(r, origins=ORIGINS):
    if r is None:
        return {}
    b, p, t, _d, _ix = r
    return {int(yr): rho(p[b == yr], t[b == yr]) for yr in origins if (b == yr).sum() >= 15}


# --------------------------------------------------------------------- arms
def arms(D, n_ctrl=24):
    ix = D["idx"]
    base = [ix[k] for k in D["keys"]]
    A = {"base": np.array(base)}
    A["add_csw"] = np.array(base + [ix["csw_rel"]])
    A["add_swstr"] = np.array(base + [ix["swstr_rel"]])
    A["add_both"] = np.array(base + [ix["csw_rel"], ix["swstr_rel"]])
    swap = [ix[k] for k in D["keys"] if k != "k_rel"] + [ix["csw_rel"]]
    A["swap_krel_csw"] = np.array(swap)
    swap2 = [ix[k] for k in D["keys"] if k != "k_rel"] + [ix["swstr_rel"]]
    A["swap_krel_swstr"] = np.array(swap2)
    A["drop_krel"] = np.array([ix[k] for k in D["keys"] if k != "k_rel"])
    # zero-information controls (averaged over n_ctrl independent draws downstream)
    for t in range(n_ctrl):
        A[f"ctrl_perm_csw_{t}"] = np.array(base + [ix[f"~perm_csw~{t}"]])
        A[f"ctrl_perm_swstr_{t}"] = np.array(base + [ix[f"~perm_swstr~{t}"]])
        A[f"ctrl_permin_csw_{t}"] = np.array(base + [ix[f"~permin_csw~{t}"]])
        A[f"ctrl_permin_swstr_{t}"] = np.array(base + [ix[f"~permin_swstr~{t}"]])
        A[f"ctrl_noise_{t}"] = np.array(base + [ix[f"~noise~{t}"]])
    return A
