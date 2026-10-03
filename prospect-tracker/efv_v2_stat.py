# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The registered scoring statistic of eFV v2 (DS-15, docs/efv-v2/EFV_V2_GATE.md s3).

Owner answer DS-Q3 (2026-09-25): the reserved frames are scored WITHIN (side, vintage)
as the primary statistic, POOLED as the secondary, with the SAME output map for every
rater. This module is that statistic and nothing else, so the development read (DS-16,
tools/efv_v2_dev_read.py) and the look runner (EV-13) compute it with one piece of code.

    group      (side, vintage): on a list-vintage frame the list vintage V, on the
               vintage-matched frame the base year (the debut year).
    map        every rater's own score, inside each group, is ranked (ties averaged) onto
               that group's consensus FV values: efv_v2_model.output_map, the map V2
               itself uses to turn its order into a grade (DS-07). It is applied on the
               rows a comparison scores, to both raters of the comparison, for the pooled
               statistic and the AUC, where every rater then shares consensus's own level
               per group and differs only in its order inside groups. It keeps each
               rater's order inside a group but can TIE rows the rater separates (the
               consensus values repeat), so the within statistic reads each rater's OWN
               score, never the mapped one.
    within     PRIMARY. The size-weighted mean over groups of the Spearman rho of the
               rater's own score against the outcome, over groups holding at least
               MIN_GROUP_ROWS rows of the comparison. Weight = the group's row count.
               V2's own score is its order index, not its mapped grade.
    pooled     SECONDARY. Spearman rho of the mapped score against the outcome over every
               row of the comparison.
    auc        The contributor AUC of the mapped score, pooled (the veto leg, PROGRAM.md
               s2.1).
    interval   paired and player-clustered: source_backtest's own resampler
               (_cluster_layout / _cluster_draw), B draws from a fixed seed; the scores
               are fixed and only players are resampled (E_cond). In a draw a group whose
               rho is undefined for either rater is left out for both. mde95 = 1.645 x
               the SD of the drawn deltas (one-sided, docs/EFV_GATE_STANDARD.md).

DISCLOSED (EFV_V2_GATE.md s3.4): the within statistic was chosen after the spent
vintage-matched frame vm1 showed it favours eFV (pooled -0.0131, within +0.0058 against
consensus, lane I3) and after reconciliation S1 showed one Pipeline ordering reading
+0.018 within and -0.008 pooled after the map.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the only groups are side and vintage.
Nothing here groups, counts or averages rows by consensus-FV level.
"""
from __future__ import annotations

import numpy as np

import efv_v2_model as H
import source_backtest as SB

#: A group enters the within statistic when it holds at least this many rows of the
#: comparison (the convention of reconciliation S1, fixed in the gate before the read).
MIN_GROUP_ROWS = 20
PRIMARY = "within"
SECONDARY = "pooled"
STATISTICS = (PRIMARY, SECONDARY, "auc")
STAT_LABEL = {
    "within": "within (side, vintage) Spearman, size-weighted",
    "pooled": "pooled Spearman after the identical output map",
    "auc": "contributor AUC after the identical output map, pooled",
}
#: A paired interval needs more usable draws than this (source_backtest's own rule).
_MAX_TOO_FEW_DRAWS = 49
B_DEFAULT = SB._CLAIM_BOOT_B
SEED_DEFAULT = SB._CLAIM_SEED
Z95 = SB._Z95


def map_scores(score, groups, consensus) -> np.ndarray:
    """The identical output map: inside each group, the rater's order onto the group's
    consensus values, ties averaged (efv_v2_model.output_map)."""
    return H.output_map(np.asarray(score, dtype=np.float64), list(groups),
                        np.asarray(consensus, dtype=np.float64))


def _rho(x: np.ndarray, y: np.ndarray) -> float | None:
    if x.size < 3:
        return None
    return SB._corr_np(np, SB._ranks_np(np, x), SB._ranks_np(np, y))


def kept_groups(codes: np.ndarray, min_rows: int = MIN_GROUP_ROWS) -> np.ndarray:
    """The group codes with at least min_rows rows."""
    u, c = np.unique(codes, return_counts=True)
    return u[c >= min_rows]


def within(score, y, codes, keep, idx=None) -> tuple[float | None, int, int]:
    """(size-weighted within-group rho, rows used, groups used) over the rows idx."""
    s = np.asarray(score, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    cc = np.asarray(codes)
    ix = np.arange(s.size) if idx is None else np.asarray(idx)
    tot = 0.0
    n = g = 0
    gc = cc[ix]
    for u in keep:
        m = ix[gc == u]
        r = _rho(s[m], yy[m])
        if r is None:
            continue
        tot += r * m.size
        n += m.size
        g += 1
    return (tot / n if n else None), n, g


def _within_pair(a, b, y, codes, keep, idx):
    """Paired within statistic: a group counts only when both raters have a rho."""
    gc = codes[idx]
    ta = tb = 0.0
    n = 0
    for u in keep:
        m = idx[gc == u]
        if m.size < 3:
            continue
        yr = SB._ranks_np(np, y[m])
        ra = SB._corr_np(np, SB._ranks_np(np, a[m]), yr)
        rb = SB._corr_np(np, SB._ranks_np(np, b[m]), yr)
        if ra is None or rb is None:
            continue
        ta += ra * m.size
        tb += rb * m.size
        n += m.size
    if not n:
        return None, None
    return ta / n, tb / n


def _auc(score: np.ndarray, pos: np.ndarray) -> float | None:
    return SB._auc_np(np, score, pos)


def rater_stats(score, y, contributor, groups, consensus,
                min_rows: int = MIN_GROUP_ROWS) -> dict:
    """One rater on its own rows: within, pooled and AUC, with the counts."""
    s = np.asarray(score, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    codes = np.asarray([str(g) for g in groups])
    keep = kept_groups(codes, min_rows)
    w, n_w, g_w = within(s, yy, codes, keep)
    mp = map_scores(s, list(codes), consensus)
    p = _rho(mp, yy)
    a = _auc(mp, np.asarray(contributor, dtype=bool))
    rnd = (lambda v: None if v is None else round(float(v), 4))
    return {"n": int(s.size), "within": rnd(w), "within_rows": n_w,
            "within_groups": g_w, "pooled": rnd(p), "auc": rnd(a)}


def paired_delta(keys, groups, y, contributor, a, b, consensus, *, statistic: str,
                 B: int = B_DEFAULT, seed: int = SEED_DEFAULT,
                 min_rows: int = MIN_GROUP_ROWS, premapped: bool = False,
                 floor_rows: int | None = None, floor_clusters: int | None = None) -> dict:
    """stat(a) - stat(b) on the rows given (both raters present on every row), with a
    paired player-clustered CI95. `consensus` is the consensus FV on the same rows (the
    map's value set). Scores are fixed; only players are resampled (E_cond).

    `premapped=True` (the scoreboard matrix, EFV3_D2): `a` and `b` already carry the
    identical output map computed once on the WHOLE frame, so the map is not refit on
    the rows given (a cell is a subset; the map is the frame's). `floor_rows` /
    `floor_clusters` replace the claim-instrument floor gate (source_backtest
    _CLAIM_MIN_ROWS / _CLAIM_MIN_CLUSTERS) for the matrix's 40-row cells (lane D
    E3-Q4 = A). Both default to the behaviour every other caller has."""
    if statistic not in STATISTICS:
        raise ValueError(f"statistic must be one of {STATISTICS}, not {statistic!r}")
    av = np.asarray(a, dtype=np.float64)
    bv = np.asarray(b, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    pos = np.asarray(contributor, dtype=bool)
    codes = np.asarray([str(g) for g in groups])
    n = av.size
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    n_clusters = len(ids)
    keep = kept_groups(codes, min_rows)
    floor_r = SB._CLAIM_MIN_ROWS if floor_rows is None else int(floor_rows)
    floor_c = SB._CLAIM_MIN_CLUSTERS if floor_clusters is None else int(floor_clusters)
    if statistic != "within" and not premapped:
        av = map_scores(av, list(codes), consensus)
        bv = map_scores(bv, list(codes), consensus)

    def stat(idx):
        if statistic == "within":
            return _within_pair(av, bv, yy, codes, keep, idx)
        if statistic == "pooled":
            yr = SB._ranks_np(np, yy[idx])
            return (SB._corr_np(np, SB._ranks_np(np, av[idx]), yr),
                    SB._corr_np(np, SB._ranks_np(np, bv[idx]), yr))
        return _auc(av[idx], pos[idx]), _auc(bv[idx], pos[idx])

    full = np.arange(n)
    pa, pb = stat(full)
    out = {"statistic": statistic, "label": STAT_LABEL[statistic], "n": int(n),
           "n_clusters": n_clusters,
           "groups_kept": [str(u) for u in keep] if statistic == "within" else None,
           "rows_in_kept_groups": (int(np.isin(codes, keep).sum())
                                   if statistic == "within" else None),
           "min_group_rows": min_rows if statistic == "within" else None,
           "a": None if pa is None else round(pa, 5),
           "b": None if pb is None else round(pb, 5),
           "delta": None if (pa is None or pb is None) else round(pa - pb, 5),
           "ci95": None, "sd": None, "mde95": None, "p_gt_0": None,
           "B": int(B), "B_used": 0, "seed": int(seed), "estimator": "E_cond",
           "ci95_estimator": "E_cond, paired, player-clustered"}
    if premapped and statistic != "within":
        out["map"] = "identical output map computed once on the whole frame (premapped)"
    if out["delta"] is None or n < floor_r or n_clusters < floor_c:
        out["status"] = "not derived: below the floor gate or undefined"
        return out
    order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(int(B)):
        idx = SB._cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        xa, xb = stat(idx)
        if xa is not None and xb is not None:
            diffs.append(xa - xb)
    if len(diffs) <= _MAX_TOO_FEW_DRAWS:
        out["status"] = "not derived: too few usable draws"
        return out
    d = np.asarray(diffs, dtype=np.float64)
    sd = float(d.std(ddof=1))
    q = np.quantile(d, [0.025, 0.975])
    out.update(ci95=[round(float(q[0]), 4), round(float(q[1]), 4)], sd=round(sd, 5),
               mde95=round(Z95 * sd, 4), p_gt_0=round(float((d > 0).mean()), 4),
               B_used=len(diffs), status="derived")
    return out


def reading(ci) -> str:
    """The development reading of an interval (a development read adjudicates nothing)."""
    if not (isinstance(ci, list) and len(ci) == 2):
        return "development only; no interval"
    if ci[0] > 0:
        return "development only; CI95 above zero"
    if ci[1] < 0:
        return "development only; CI95 below zero"
    return "development only; CI95 spans zero"
