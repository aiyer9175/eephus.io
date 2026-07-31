# scratch lab (lane: nested) -- IS THE ARCHETYPE-SEARCH PROCEDURE WORTH ANYTHING?
#
# Wraps the COMBINATORIAL archetype search (discretise -> enumerate -> score ->
# select top-k) inside forward-chained NESTED cross-validation.
#
#   inner loop  : the complete search runs on decision_year < Y only
#   outer loop  : the selected archetypes are applied to decision_year == Y,
#                 which was untouched during discretisation, enumeration,
#                 cut-point fitting, scoring and selection.
#
# Reported: (a) in-sample best, (b) nested-CV lift, (c) the gap = selection bias
# in the model's own units, (d) the same under a permuted-outcome zero-information
# control, (e) sensitivity to k.
#
# Read-only w.r.t. every shipped artifact. Writes only under the scratchpad.
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _arch_discover as A  # noqa: E402

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
OUT = SCRATCH / "comb_nested"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- pre-registered
# Frozen BEFORE any outcome statistic is computed. See cmd_prereg().
NFLOOR_POOLED = 40      # minimum rows per stratum, pooled arm
NFLOOR_TR = 30          # minimum rows per stratum, track-record arm
MAX_ORDER = 3           # 1-way, 2-way and 3-way conjunctions
KS = (1, 3, 10)         # selection-rule sensitivity
OUTER_YEARS = (2020, 2021, 2022, 2023, 2024)   # forward-chained outer test folds
JACCARD_MAX = 0.50      # greedy de-duplication threshold during selection

_MID = ("SS", "2B", "CF")
_CORNER = ("1B", "3B", "LF", "RF", "DH", "OF")


def _posgroup(r):
    p = (r.get("position") or "").split("/")[0].strip().upper()
    if p == "C":
        return 0
    if p in _MID:
        return 1
    if p in _CORNER:
        return 2
    return 3


def _path(r):
    if float(r.get("is_ifa") or 0) > 0.5:
        return 2
    if float(r.get("is_college") or 0) > 0.5:
        return 1
    return 0


# axis name -> (extractor, kind, nbins)
# kind "q" = train-fold quantile bins; kind "c" = fixed categorical/threshold bins
def _m(r, k, d=0.0):
    v = (r.get("milb") or {}).get(k)
    return float(v) if v is not None else d


def _tool(r, k, d):
    v = r.get(k)
    return float(v) if v is not None else d


AXES = [
    ("age",            lambda r: _m(r, "age", 22.5),            "c", [20.5, 22.0, 23.5]),
    ("age_rel_level",  lambda r: _m(r, "age_rel_level"),        "c", [-1.0, 0.0, 1.0]),
    ("level_rank",     lambda r: _m(r, "level_rank"),           "c", [0.5, 2.5, 3.5]),
    ("n_milb_seasons", lambda r: _m(r, "n_milb_seasons"),       "c", [1.5, 3.5]),
    ("ops_rel",        lambda r: _m(r, "ops_rel"),              "q", 3),
    ("iso_rel",        lambda r: _m(r, "iso_rel"),              "q", 3),
    ("obp_rel",        lambda r: _m(r, "obp_rel"),              "q", 3),
    ("k_rel",          lambda r: _m(r, "k_rel"),                "q", 3),
    ("bb_rel",         lambda r: _m(r, "bb_rel"),               "q", 3),
    ("prod_trend",     lambda r: _m(r, "prod_trend"),           "q", 3),
    ("pos_group",      _posgroup,                               "c", None),
    ("path",           _path,                                   "c", None),
    ("tool_hit",       lambda r: _tool(r, "tool_hit", 47.9),    "q", 3),
    ("tool_game_pwr",  lambda r: _tool(r, "tool_game_pwr", 45.0), "q", 3),
    ("tool_speed",     lambda r: _tool(r, "tool_speed", 50.7),  "q", 3),
    ("tool_field",     lambda r: _tool(r, "tool_field", 45.0),  "q", 3),
    ("fv",             lambda r: float(r["fv"]),                "c", [42.5, 47.5, 52.5]),
    ("has_milb",       lambda r: 1.0 if r["has_milb"] else 0.0, "c", [0.5]),
]

AXIS_NAMES = [a[0] for a in AXES]


def bin_index(rows, axis, train_rows):
    """Bin assignment for every row, with cut-points fit on TRAIN ROWS ONLY."""
    name, fn, kind, spec = axis
    v = np.array([fn(r) for r in rows], dtype=float)
    if kind == "c":
        if spec is None:
            return v.astype(int), None
        cuts = np.array(spec, dtype=float)
        return np.searchsorted(cuts, v, side="right"), list(cuts)
    tv = np.array([fn(r) for r in train_rows], dtype=float)
    qs = [100.0 * i / spec for i in range(1, spec)]
    cuts = np.unique(np.percentile(tv, qs))
    return np.searchsorted(cuts, v, side="right"), list(cuts)


def enumerate_candidates(rows, train_rows, nfloor, max_order=MAX_ORDER):
    """Return (mask matrix [n x C] bool, list of candidate descriptors).

    A candidate is a conjunction of one bin drawn from each of 1..max_order
    distinct axes. Candidates with fewer than `nfloor` TRAIN rows are dropped
    (pre-registered stratum-size floor)."""
    n = len(rows)
    tr_idx = np.array([i for i, r in enumerate(rows) if r["_is_train"]])
    onehot, labels = [], []
    for ax in AXES:
        bi, cuts = bin_index(rows, ax, train_rows)
        uniq = sorted(set(bi.tolist()))
        oh = np.stack([bi == u for u in uniq], axis=1)
        onehot.append(oh)
        labels.append([(ax[0], int(u), cuts) for u in uniq])

    cols, desc = [], []

    def _push(mask, d):
        if mask[tr_idx].sum() >= nfloor:
            cols.append(mask)
            desc.append(d)

    na = len(AXES)
    for a in range(na):
        for i in range(onehot[a].shape[1]):
            _push(onehot[a][:, i], [labels[a][i]])
    if max_order >= 2:
        for a in range(na):
            for b in range(a + 1, na):
                for i in range(onehot[a].shape[1]):
                    ma = onehot[a][:, i]
                    if ma[tr_idx].sum() < nfloor:
                        continue
                    for j in range(onehot[b].shape[1]):
                        _push(ma & onehot[b][:, j], [labels[a][i], labels[b][j]])
    if max_order >= 3:
        for a in range(na):
            for b in range(a + 1, na):
                for c in range(b + 1, na):
                    for i in range(onehot[a].shape[1]):
                        ma = onehot[a][:, i]
                        if ma[tr_idx].sum() < nfloor:
                            continue
                        for j in range(onehot[b].shape[1]):
                            mb = ma & onehot[b][:, j]
                            if mb[tr_idx].sum() < nfloor:
                                continue
                            for k in range(onehot[c].shape[1]):
                                _push(mb & onehot[c][:, k], [labels[a][i], labels[b][j],
                                                             labels[c][k]])
    M = np.stack(cols, axis=1) if cols else np.zeros((n, 0), dtype=bool)
    return M, desc


def desc_str(d):
    parts = []
    for name, u, cuts in d:
        if cuts is None:
            parts.append(f"{name}={u}")
        else:
            lo = "-inf" if u == 0 else f"{cuts[u-1]:.4g}"
            hi = "+inf" if u >= len(cuts) else f"{cuts[u]:.4g}"
            parts.append(f"{name}[{lo},{hi})")
    return " & ".join(parts)


# ---------------------------------------------------------------- scoring
def block_center(y, w, blocks):
    """Year-block centred, weight-aware. A year-composition shift cannot
    masquerade as archetype signal."""
    out = y.astype(float).copy()
    for b in np.unique(blocks):
        i = blocks == b
        ww = w[i]
        m = np.average(y[i], weights=ww) if ww.sum() > 0 else y[i].mean()
        out[i] = y[i] - m
    return out


def score_all(M, y, w):
    """Weighted two-sample t-like statistic for EVERY candidate at once.

    t_c = (mean_in - mean_out) / se, computed from three mat-vec products so the
    whole family (and every permutation replicate of it) is cheap."""
    Mf = M.astype(np.float64)
    W = w
    wy = w * y
    wy2 = w * y * y
    n_in = Mf.T @ W
    s_in = Mf.T @ wy
    q_in = Mf.T @ wy2
    N = W.sum()
    S = wy.sum()
    Q = wy2.sum()
    n_out = N - n_in
    s_out = S - s_in
    q_out = Q - q_in
    with np.errstate(divide="ignore", invalid="ignore"):
        m_in = s_in / n_in
        m_out = s_out / n_out
        v_in = q_in / n_in - m_in ** 2
        v_out = q_out / n_out - m_out ** 2
        # effective sample sizes from the weights
        se = np.sqrt(np.clip(v_in, 0, None) / np.clip(n_in, 1e-9, None)
                     + np.clip(v_out, 0, None) / np.clip(n_out, 1e-9, None))
        t = (m_in - m_out) / se
    t[~np.isfinite(t)] = 0.0
    return t, m_in, m_out, n_in


def select_topk(t, M, k, tr_idx, jac_max=JACCARD_MAX):
    """Greedy top-k by |t| with Jaccard de-duplication so k near-identical
    strata cannot pose as k independent discoveries."""
    order = np.argsort(-np.abs(t))
    chosen = []
    for c in order:
        if len(chosen) >= k:
            break
        mc = M[tr_idx, c]
        if mc.sum() == 0:
            continue
        ok = True
        for c2 in chosen:
            m2 = M[tr_idx, c2]
            inter = (mc & m2).sum()
            union = (mc | m2).sum()
            if union and inter / union > jac_max:
                ok = False
                break
        if ok:
            chosen.append(int(c))
    return chosen


# ---------------------------------------------------------------- metrics
def _rank(x):
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x), dtype=float)
    r[o] = np.arange(len(x), dtype=float)
    # average ties
    xs = x[o]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            r[o[i:j + 1]] = np.mean(r[o[i:j + 1]])
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = _rank(np.asarray(a, float)), _rank(np.asarray(b, float))
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d > 0 else 0.0


def eta2(labels, y, w):
    gm = np.average(y, weights=w)
    sst = float(np.sum(w * (y - gm) ** 2))
    if sst <= 0:
        return 0.0
    ssb = 0.0
    for g in np.unique(labels):
        i = labels == g
        ww = w[i].sum()
        if ww <= 0:
            continue
        ssb += ww * (float(np.average(y[i], weights=w[i])) - gm) ** 2
    return ssb / sst


def apply_offsets(M, chosen, offsets):
    """Additive archetype offset: mean of the train offsets of every stratum a
    row belongs to (0 when it matches none)."""
    n = M.shape[0]
    tot = np.zeros(n)
    cnt = np.zeros(n)
    for c, d in zip(chosen, offsets):
        m = M[:, c]
        tot[m] += d
        cnt[m] += 1
    adj = np.zeros(n)
    nz = cnt > 0
    adj[nz] = tot[nz] / cnt[nz]
    return adj


def bh_q(p):
    p = np.asarray(p, float)
    n = len(p)
    o = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank in range(n - 1, -1, -1):
        i = o[rank]
        val = p[i] * n / (rank + 1)
        prev = min(prev, val)
        q[i] = prev
    return q
