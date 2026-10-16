# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Swing-decision value, the pure core (swing_decision_v1). docs/ewar/SWING_DECISION_GATE.md.

For every pitch a batter decides on: the run value of the decision he made minus the one he
did not make, each valued at what the league gets from that decision on that pitch (gate
parts 2.2 and 2.3 as fixed by the dated note 8.1):

  VT - V(before) = p0 (V(strike) - V(before)) + (1 - p0) (V(ball) - V(before))
  VS - V(before) = P_w (V(strike) - V(before)) + P_f (V(foul) - V(before)) + P_ip (m_bo + r_loc)
  DV = VT - VS for a take, VS - VT for a swing

SD per batter-season = sum (DV - DVbar_s); SD100 = 100 SD / decisions; SD~ = SD / (decisions +
K_SD). K_SD is fitted ONCE on 2018 by split-half reliability and frozen below.

Pure: numpy and pandas, no I/O.
"""
from __future__ import annotations

import numpy as np

SWING_DECISION_VERSION = "swing_decision_v1"
GATE_DOC = "docs/ewar/SWING_DECISION_GATE.md"

TAKES = frozenset({"B", "*B", "C"})
WHIFF = frozenset({"S", "W", "T"})
FOUL = frozenset({"F"})
IN_PLAY = frozenset({"X", "D", "E"})
SWINGS = WHIFF | FOUL | IN_PLAY

X_LO, X_HI, X_STEP = -2.0, 2.0, 0.25
Z_LO, Z_HI, Z_STEP = -1.0, 2.0, 0.15
K_CELL = 25.0

#: Gate part 2.5: fitted once on 2018 (split-half over alternate plate appearances, batters
#: with 1,000 or more decisions, Spearman-Brown corrected). Fitted 2026-10-16: 307 batters,
#: half r 0.7236, Spearman-Brown 0.8396, median 1,869 decisions; log in
#: data/_labs/ewar_innovate/swing_decision_k_fit.json. Frozen.
K_SD: float | None = 357.0258
SPLIT_FLOOR = 1000


def loc_bins(xm, zn):
    nx = int(round((X_HI - X_LO) / X_STEP))
    nz = int(round((Z_HI - Z_LO) / Z_STEP))
    xi = np.clip(np.floor((np.asarray(xm, dtype=float) - X_LO) / X_STEP), 0, nx - 1).astype(np.int64)
    zi = np.clip(np.floor((np.asarray(zn, dtype=float) - Z_LO) / Z_STEP), 0, nz - 1).astype(np.int64)
    return xi * nz + zi


def shrunk_rates(df, value_cols, n_col, loc, parent, cell, k=K_CELL):
    """Cell rates shrunk toward the parent, the parent toward the location cell (gate 2.3).
    df has the per-row indicator/value columns; returns {col: array per row}."""
    out = {}
    g_loc = df.groupby(loc)
    g_par = df.groupby(parent)
    g_cel = df.groupby(cell)
    n_loc = g_loc[n_col].transform("sum").to_numpy(dtype=float)
    n_par = g_par[n_col].transform("sum").to_numpy(dtype=float)
    n_cel = g_cel[n_col].transform("sum").to_numpy(dtype=float)
    for c in value_cols:
        s_loc = g_loc[c].transform("sum").to_numpy(dtype=float)
        s_par = g_par[c].transform("sum").to_numpy(dtype=float)
        s_cel = g_cel[c].transform("sum").to_numpy(dtype=float)
        with np.errstate(invalid="ignore", divide="ignore"):
            r_loc = np.where(n_loc > 0, s_loc / np.where(n_loc > 0, n_loc, 1), 0.0)
        r_par = (s_par + k * r_loc) / (n_par + k)
        out[c] = (s_cel + k * r_par) / (n_cel + k)
    return out


def decision_values(v_before, v_ball, v_strike, strikes, p0, pw, pf, pip, m_bo, r_loc, is_take):
    """DV per pitch (gate 2.4)."""
    vb, vball, vstr = (np.asarray(a, dtype=float) for a in (v_before, v_ball, v_strike))
    v_foul = np.where(np.asarray(strikes) >= 2, vb, vstr)
    vt = p0 * (vstr - vb) + (1 - p0) * (vball - vb)
    vs = pw * (vstr - vb) + pf * (v_foul - vb) + pip * (m_bo + r_loc)
    return np.where(np.asarray(is_take, dtype=bool), vt - vs, vs - vt), vt, vs


def batter_totals(batter, dv, dvbar):
    import pandas as pd
    d = pd.DataFrame({"batter": batter, "x": np.asarray(dv, dtype=float) - dvbar})
    g = d.groupby("batter")["x"]
    out = pd.DataFrame({"SD": g.sum(), "decisions": g.size()})
    out["SD100"] = 100.0 * out["SD"] / out["decisions"]
    return out


def shrunk(sd, decisions, k):
    if k is None or not np.isfinite(k):
        return np.zeros(len(np.atleast_1d(sd)))
    return np.asarray(sd, dtype=float) / (np.asarray(decisions, dtype=float) + float(k))


def split_half_k(half_a, half_b, decisions) -> dict:
    """Gate 2.5: K_SD = d_med (1 - r_sb) / r_sb; r_sb the Spearman-Brown corrected Pearson of
    the two halves' SD100. r_sb at or below 0 sets K_SD to infinity."""
    a = np.asarray(half_a, dtype=float)
    b = np.asarray(half_b, dtype=float)
    r = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float("nan")
    r_sb = 2 * r / (1 + r) if np.isfinite(r) and r > -1 else float("nan")
    d_med = float(np.median(decisions))
    k = d_med * (1 - r_sb) / r_sb if (np.isfinite(r_sb) and r_sb > 0) else float("inf")
    return {"n": int(len(a)), "r_half": r, "r_sb": r_sb, "d_med": d_med, "K_SD": k}
