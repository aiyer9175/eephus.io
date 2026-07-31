# SCRATCH (not shipped): consensus-anchor improvement lab.
# Level-1 instrument: does a recalibrated / reweighted consensus anchor rank realized
# WAR better than the shipped consensus_fv_raw?  Forward-chained, paired bootstrap with
# refit, pairing-preserving null bands.  Nothing here is imported by shipped code.
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as E  # noqa: E402

SEED = 20260724
SOURCES = ("fangraphs", "mlb_pipeline")


# ---------------------------------------------------------------- data
def load_rows(side: str, cut: str = "debuted_km"):
    fn = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    raw = json.loads((ROOT / "data" / fn).read_text("utf-8"))
    if cut == "debuted_km":
        raw = [r for r in raw if r["kind"] == "debuted"]
    elif cut == "full_pool_km":
        raw = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
    out = []
    for r in raw:
        t = r.get("target_censored")
        if t is None or r.get("consensus_fv_raw") is None:
            continue
        out.append({
            "side": side,
            "key": r["player_key"],
            "dy": E._decision_year(r),
            "y": float(t),
            "w": max(1e-3, float(r.get("weight", 1.0) or 0.0)),
            "cons": float(r["consensus_fv_raw"]),
            "fg": (None if r.get("fv_fangraphs") is None else float(r["fv_fangraphs"])),
            "mp": (None if r.get("fv_mlb_pipeline") is None else float(r["fv_mlb_pipeline"])),
            "nsrc": float(r.get("n_sources") or 0.0),
            "row": r,
        })
    return out


def to_arrays(rows):
    return {
        "cons": np.array([r["cons"] for r in rows]),
        "fg": np.array([np.nan if r["fg"] is None else r["fg"] for r in rows]),
        "mp": np.array([np.nan if r["mp"] is None else r["mp"] for r in rows]),
        "y": np.array([r["y"] for r in rows]),
        "w": np.array([r["w"] for r in rows]),
        "dy": np.array([r["dy"] for r in rows], dtype=int),
        "nsrc": np.array([r["nsrc"] for r in rows]),
        "n": len(rows),
    }


# ---------------------------------------------------------------- metric
def _rank01(v):
    return (rankdata(v) - 0.5) / len(v)


def spear(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if len(a) < 8:
        return np.nan
    ra, rb = rankdata(a), rankdata(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else np.nan


def auc(scores, labels):
    scores = np.asarray(scores, float)
    labels = np.asarray(labels, bool)
    p, q = labels.sum(), (~labels).sum()
    if p == 0 or q == 0:
        return np.nan
    r = rankdata(scores)
    return float((r[labels].sum() - p * (p + 1) / 2) / (p * q))


# ---------------------------------------------------------------- anchor primitives
def _wols(x, yv, w):
    """weighted OLS y ~ a + b x on finite x; returns (a, b, resid_var)."""
    m = np.isfinite(x) & np.isfinite(yv)
    if m.sum() < 25:
        return None
    xi, yi, wi = x[m], yv[m], w[m]
    sw = wi.sum()
    mx = (wi * xi).sum() / sw
    my = (wi * yi).sum() / sw
    var = (wi * (xi - mx) ** 2).sum()
    if var <= 0:
        return None
    b = (wi * (xi - mx) * (yi - my)).sum() / var
    a = my - b * mx
    res = yi - (a + b * xi)
    v = float((wi * res ** 2).sum() / sw)
    return (a, b, max(v, 1e-6))


def _moments(x, w):
    m = np.isfinite(x)
    if m.sum() < 25:
        return None
    xi, wi = x[m], w[m]
    sw = wi.sum()
    mu = (wi * xi).sum() / sw
    sd = np.sqrt((wi * (xi - mu) ** 2).sum() / sw)
    return (float(mu), float(max(sd, 1e-6)))


def _ecdf_fit(x):
    m = np.isfinite(x)
    if m.sum() < 25:
        return None
    return np.sort(x[m])


def _ecdf_apply(srt, x):
    return np.searchsorted(srt, x, side="left") / max(len(srt), 1)


def fit_anchor(tr, y_override=None):
    """Fit every anchor variant's parameters on TRAIN arrays only."""
    yv = tr["y"] if y_override is None else y_override
    w = tr["w"]
    P = {}
    P["cons_ols"] = _wols(tr["cons"], yv, w)
    P["cons_mom"] = _moments(tr["cons"], w)
    P["ecdf_cons"] = _ecdf_fit(tr["cons"])
    for k in ("fg", "mp"):
        P[f"ols_{k}"] = _wols(tr[k], yv, w)
        P[f"mom_{k}"] = _moments(tr[k], w)
        P[f"ecdf_{k}"] = _ecdf_fit(tr[k])
    # rank-based per-source skill (for scalar vote weights), train only
    for k in ("fg", "mp"):
        m = np.isfinite(tr[k])
        P[f"rho_{k}"] = spear(tr[k][m], yv[m]) if m.sum() >= 40 else np.nan
    return P


def _combine(base, parts, ws):
    """Weighted mean of the available parts; `base` where nothing is available."""
    n = len(base)
    num = np.zeros(n)
    den = np.zeros(n)
    for arr, wt in zip(parts, ws):
        m = np.isfinite(arr)
        num[m] += wt * arr[m]
        den[m] += wt
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), base)


def apply_anchor(kind, P, te, weights=None):
    """Anchor value (higher = better prospect) for every test row."""
    cons, fg, mp = te["cons"], te["fg"], te["mp"]
    n = len(cons)

    if kind == "shipped":
        return cons.copy()
    if kind == "affine_twin":                       # rank-identical control
        return 3.7 * cons - 111.0
    if kind == "plain_mean":                        # unweighted mean of published FVs
        return _combine(cons, [fg, mp], [1.0, 1.0])

    if kind in ("zmap", "zmap_custom"):             # per-source bias+scale -> z
        zs = []
        for k, arr in (("fg", fg), ("mp", mp)):
            mo = P[f"mom_{k}"]
            zs.append((arr - mo[0]) / mo[1] if mo else np.full(n, np.nan))
        cm = P["cons_mom"]
        base = (cons - cm[0]) / cm[1] if cm else cons
        ws = list(weights) if kind == "zmap_custom" else [1.0, 1.0]
        return _combine(base, zs, ws)

    if kind == "qmap":                              # per-source quantile map
        zs = []
        for k, arr in (("fg", fg), ("mp", mp)):
            e = P[f"ecdf_{k}"]
            if e is None:
                zs.append(np.full(n, np.nan))
                continue
            v = _ecdf_apply(e, arr).astype(float)
            v[~np.isfinite(arr)] = np.nan
            zs.append(v)
        base = (_ecdf_apply(P["ecdf_cons"], cons).astype(float)
                if P["ecdf_cons"] is not None else cons)
        return _combine(base, zs, [1.0, 1.0])

    if kind in ("warcal", "warcal_prec"):           # per-source WAR calibration
        preds, ws = [], []
        for k, arr in (("fg", fg), ("mp", mp)):
            o = P[f"ols_{k}"]
            if o is None:
                preds.append(np.full(n, np.nan))
                ws.append(0.0)
                continue
            preds.append(o[0] + o[1] * arr)
            ws.append((1.0 / o[2]) if kind == "warcal_prec" else 1.0)
        co = P["cons_ols"]
        base = (co[0] + co[1] * cons) if co else cons
        return _combine(base, preds, ws)

    if kind == "custom":                            # explicit vote weights on RAW published FV
        return _combine(cons, [fg, mp], list(weights))

    if kind == "rho_vote":                          # scalar vote weights from train Spearman
        rf, rm = P["rho_fg"], P["rho_mp"]
        if not (np.isfinite(rf) and np.isfinite(rm)):
            return cons.copy()
        mean = (max(rf, 0.05) + max(rm, 0.05)) / 2.0
        wf = np.clip(max(rf, 0.05) / mean, 0.6, 1.4)
        wm = np.clip(max(rm, 0.05) / mean, 0.6, 1.4)
        return _combine(cons, [fg, mp], [wf, wm])

    raise ValueError(kind)


# ---------------------------------------------------------------- forward-chained eval
def fwd_anchor(kinds, sides_data, origins, weights_by_kind=None, y_shuffle_rng=None,
               ret_extra=False):
    """Fit anchors on decision_year<Y, score on ==Y, pool block-percentile ranks."""
    weights_by_kind = weights_by_kind or {}
    preds = {k: [] for k in kinds}
    tgt, blk, raw_y = [], [], []
    for side, A in sides_data.items():
        for Y in origins:
            tri = np.flatnonzero(A["dy"] < Y)
            tei = np.flatnonzero(A["dy"] == Y)
            if len(tei) < 15 or len(tri) < 60:
                continue
            tr = {k: v[tri] for k, v in A.items() if isinstance(v, np.ndarray)}
            te = {k: v[tei] for k, v in A.items() if isinstance(v, np.ndarray)}
            yov = None
            if y_shuffle_rng is not None:
                yov = tr["y"][y_shuffle_rng.permutation(len(tri))]
            P = fit_anchor(tr, y_override=yov)
            for k in kinds:
                preds[k].append(_rank01(apply_anchor(k, P, te, weights=weights_by_kind.get(k))))
            tgt.append(_rank01(te["y"]))
            raw_y.append(te["y"])
            blk.append(np.full(len(tei), f"{side}{Y}"))
    if not tgt:
        return None
    out = ({k: np.concatenate(v) for k, v in preds.items()},
           np.concatenate(tgt), np.concatenate(blk))
    if ret_extra:
        return out + (np.concatenate(raw_y),)
    return out


def score(preds, tgt, kinds):
    return {k: spear(preds[k], tgt) for k in kinds}
