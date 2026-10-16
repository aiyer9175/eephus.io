# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pitch-level run value attribution ledger, the pure core (pitch_ledger_v1).
docs/ewar/PITCH_LEDGER_GATE.md.

WHAT IT IS. Every step of the RE288 count walk (count_value.walk_play) split into named
components that sum to the step's run value dRE exactly (gate part 3), each with one
batting-side and one fielding-side owner (part 6). A measurement substrate: it forecasts
nothing and serves nothing.

THE MODELS (gate parts 4 and 5), each fitted per season on that season's steps:
  p0      the league called-strike probability: a smoothed grid over mirrored plate_x and
          the zone-normalised height, by hands and count group, calibrated to the season's
          called strikes by one logit shift;
  effects ridge logit effects for catcher, pitcher, batter and umpire on top of logit p0,
          sigma per group frozen once on 2018 (SIGMA below);
  x_x     the batted ball's expected value by contact cell and base-out state;
  e       the expected wild-pitch and passed-ball cost of a pitch with a runner on;
  e_s     the mean steal-event value by family and base-out state.

Pure: numpy and scipy only, no I/O. tools/build_pitch_ledger.py reads the stores.
"""
from __future__ import annotations

import math

import numpy as np

PITCH_LEDGER_VERSION = "pitch_ledger_v1"
GATE_DOC = "docs/ewar/PITCH_LEDGER_GATE.md"

#: Gate part 4.2: the ridge sd per person group, chosen ONCE on 2018 by held-out
#: log-likelihood (odd game_pk fit, even game_pk scored) from SIGMA_GRID, frozen here.
#: Selected 2026-10-16 on 2018 (fit rows 190,087 odd game_pk, scored rows 189,351 even
#: game_pk; log in data/_labs/ewar_innovate/pitch_ledger_sigma_selection.json) and frozen.
SIGMA_GRID = (0.05, 0.10, 0.15, 0.20, 0.30)
SIGMA_HOLD = 0.15
SIGMA: dict[str, float | None] = {"catcher": 0.15, "pitcher": 0.15, "batter": 0.15, "umpire": 0.10}
GROUPS = ("catcher", "pitcher", "batter", "umpire")

#: Gate part 4.1, the league grid.
X_LO, X_HI, X_STEP = -2.0, 2.0, 0.1
Z_LO, Z_HI, Z_STEP = -0.75, 1.75, 0.05
KERNEL_BINS = 1.5
PRIOR_N = 20.0

#: Gate part 9 (2026-10-16 dated note): the rulebook zone. Half the plate (8.5 in) plus a
#: ball radius (1.45 in) wide; the feed's zone edges plus a ball radius tall.
PLATE_HALF_FT = 8.5 / 12.0
BALL_RADIUS_FT = 1.45 / 12.0

TAKE_CODES = frozenset({"B", "*B", "C"})
CALLED_STRIKE = "C"
IN_PLAY_CODES = frozenset({"X", "D", "E"})

#: Gate part 5.2 pitch groups.
FB = frozenset({"FF", "FA", "SI", "FT", "FC"})
BR = frozenset({"SL", "ST", "SV", "CU", "KC", "CS"})
OS = frozenset({"CH", "FS", "FO", "SC", "KN", "EP"})

#: Gate part 5.1 contact cell, the interaction shrink.
K_INTERACTION = 30.0

#: Event families (gate parts 3.3 to 3.5).
WPPB = frozenset({"wild_pitch", "passed_ball"})
STEAL = {"stolen_base_2b": "2b", "stolen_base_3b": "3b", "stolen_base_home": "home",
         "caught_stealing_2b": "2b", "caught_stealing_3b": "3b", "caught_stealing_home": "home",
         "pickoff_caught_stealing_2b": "2b", "pickoff_caught_stealing_3b": "3b",
         "pickoff_caught_stealing_home": "home", "defensive_indiff": "di"}
PICKOFF = frozenset({"pickoff_1b", "pickoff_2b", "pickoff_3b", "pickoff_error_1b",
                     "pickoff_error_2b", "pickoff_error_3b", "balk", "forced_balk"})

COMPONENTS = ("x_duel", "x_bcs", "x_pcs", "x_frm", "x_ump", "x_ch", "x_oth", "x_x", "x_fld",
              "x_bexp", "x_babs", "x_blk", "x_sexp", "x_sres", "x_pk")

#: Gate part 6: (batting-side owner, fielding-side owner) per component.
OWNERS = {
    "x_duel": ("batter", "pitcher"),
    "x_bcs": ("batter", "context_fielding"),
    "x_pcs": ("context_batting", "pitcher"),
    "x_frm": ("context_batting", "catcher_framing"),
    "x_ump": ("umpire", "umpire"),
    "x_ch": ("challenge_batting", "challenge_fielding"),
    "x_oth": ("runners", "fielders_unassigned"),
    "x_x": ("batter", "pitcher"),
    "x_fld": ("batter", "fielder"),
    "x_bexp": ("context_batting", "pitcher"),
    "x_babs": ("context_batting", "catcher_blocking"),
    "x_blk": ("runners", "catcher_blocking"),
    "x_sexp": ("runners", "pitcher"),
    "x_sres": ("runners", "catcher_throwing"),
    "x_pk": ("runners", "pitcher"),
}

IDENTITY_TOL = 1e-9


def pitch_group(pt) -> int:
    """0 FB, 1 BR, 2 OS, 3 other or missing."""
    if pt in FB:
        return 0
    if pt in BR:
        return 1
    if pt in OS:
        return 2
    return 3


def count_group(balls: int, strikes: int) -> int:
    """0: 3-0 or 3-1; 1: two strikes and fewer than three balls; 2: 3-2; 3: every other count."""
    if balls == 3 and strikes < 2:
        return 0
    if strikes == 2 and balls < 3:
        return 1
    if balls == 3 and strikes == 2:
        return 2
    return 3


def hand_key(bat_side, pitch_hand) -> int:
    return (0 if bat_side == "R" else 1) * 2 + (0 if pitch_hand == "R" else 1)


def mirrored_x(plate_x, bat_side):
    x = np.asarray(plate_x, dtype=float)
    lefty = np.asarray([b == "L" for b in bat_side])
    return np.where(lefty, -x, x)


def zone_height(plate_z, sz_bot, sz_top):
    z, b, t = (np.asarray(a, dtype=float) for a in (plate_z, sz_bot, sz_top))
    with np.errstate(invalid="ignore", divide="ignore"):
        return (z - b) / (t - b)


def rulebook_strike(xm, plate_z, sz_bot, sz_top):
    """z: 1 inside the rulebook zone (gate part 9 note), 0 outside, NaN without location."""
    xm, z, b, t = (np.asarray(a, dtype=float) for a in (xm, plate_z, sz_bot, sz_top))
    ok = np.isfinite(xm) & np.isfinite(z) & np.isfinite(b) & np.isfinite(t)
    inside = ((np.abs(xm) <= PLATE_HALF_FT + BALL_RADIUS_FT)
              & (z >= b - BALL_RADIUS_FT) & (z <= t + BALL_RADIUS_FT))
    return np.where(ok, inside.astype(float), np.nan)


# --------------------------------------------------------------------------
# part 4.1: the league model p0
# --------------------------------------------------------------------------
def _bins(v, lo, hi, step):
    n = int(round((hi - lo) / step))
    i = np.floor((np.asarray(v, dtype=float) - lo) / step).astype(np.int64)
    return np.clip(i, 0, n - 1), n


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def expit(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


class LeagueModel:
    """The smoothed grid p0 of gate part 4.1."""

    def __init__(self, grids: dict, shift: float):
        self.grids = grids          # (hand, cgroup) -> p array (nx, nz)
        self.shift = float(shift)

    def raw(self, xm, zn, hand, cgrp):
        xi, _ = _bins(xm, X_LO, X_HI, X_STEP)
        zi, _ = _bins(zn, Z_LO, Z_HI, Z_STEP)
        out = np.empty(len(xi))
        hand = np.asarray(hand)
        cgrp = np.asarray(cgrp)
        for (h, c), g in self.grids.items():
            m = (hand == h) & (cgrp == c)
            if m.any():
                out[m] = g[xi[m], zi[m]]
        return out

    def predict(self, xm, zn, hand, cgrp):
        return expit(logit(self.raw(xm, zn, hand, cgrp)) + self.shift)


def solve_shift(L, y_sum: float, it: int = 60) -> float:
    """c with sum expit(L + c) = y_sum (Newton)."""
    c = 0.0
    for _ in range(it):
        p = expit(L + c)
        f = p.sum() - y_sum
        d = (p * (1 - p)).sum()
        if d <= 0:
            break
        step = f / d
        c -= step
        if abs(step) < 1e-12:
            break
    return c


def fit_league(xm, zn, hand, cgrp, y) -> LeagueModel:
    from scipy.ndimage import gaussian_filter
    xi, nx = _bins(xm, X_LO, X_HI, X_STEP)
    zi, nz = _bins(zn, Z_LO, Z_HI, Z_STEP)
    hand = np.asarray(hand)
    cgrp = np.asarray(cgrp)
    y = np.asarray(y, dtype=float)
    grids = {}
    for h in range(4):
        mh = hand == h
        nh = np.zeros((nx, nz))
        kh = np.zeros((nx, nz))
        np.add.at(nh, (xi[mh], zi[mh]), 1.0)
        np.add.at(kh, (xi[mh], zi[mh]), y[mh])
        ns = gaussian_filter(nh, KERNEL_BINS, mode="nearest")
        ks = gaussian_filter(kh, KERNEL_BINS, mode="nearest")
        with np.errstate(invalid="ignore", divide="ignore"):
            q = np.where(ns > 0, ks / ns, 0.5)
        for c in range(4):
            m = mh & (cgrp == c)
            n = np.zeros((nx, nz))
            k = np.zeros((nx, nz))
            np.add.at(n, (xi[m], zi[m]), 1.0)
            np.add.at(k, (xi[m], zi[m]), y[m])
            n_s = gaussian_filter(n, KERNEL_BINS, mode="nearest")
            k_s = gaussian_filter(k, KERNEL_BINS, mode="nearest")
            grids[(h, c)] = np.clip((k_s + PRIOR_N * q) / (n_s + PRIOR_N), 1e-6, 1 - 1e-6)
    lm = LeagueModel(grids, 0.0)
    L = logit(lm.raw(xm, zn, hand, cgrp))
    lm.shift = solve_shift(L, float(y.sum()))
    return lm


# --------------------------------------------------------------------------
# part 4.2: the person effects
# --------------------------------------------------------------------------
def encode(ids):
    """(codes 0..k-1, uniques) for an id array; missing ids get their own code -1."""
    ids = np.asarray(ids)
    uniq, inv = np.unique(ids, return_inverse=True)
    return inv.astype(np.int64), uniq


def fit_effects(L0, y, idx: dict, sigma: dict, maxiter: int = 500):
    """Ridge logit effects per group on offset L0. idx: group -> int codes; sigma: group ->
    sd. Returns (intercept, {group: effects}) with each group re-centred to a pitch-weighted
    mean of 0 and the intercept re-solved so that sum p = sum y."""
    from scipy.optimize import minimize
    L0 = np.asarray(L0, dtype=float)
    y = np.asarray(y, dtype=float)
    groups = [g for g in GROUPS if g in idx]
    sizes = [int(idx[g].max()) + 1 if len(idx[g]) else 0 for g in groups]
    offs = np.cumsum([1] + sizes)[:-1]
    npar = 1 + sum(sizes)
    lam = np.concatenate([[0.0]] + [np.full(s, 1.0 / float(sigma[g]) ** 2) for g, s in zip(groups, sizes)])

    def f(theta):
        L = L0 + theta[0]
        for g, o, s in zip(groups, offs, sizes):
            L = L + theta[o:o + s][idx[g]]
        p = expit(L)
        nll = -(y * np.log(np.clip(p, 1e-12, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-12, 1))).sum()
        nll += 0.5 * (lam * theta * theta).sum()
        r = p - y
        grad = np.empty(npar)
        grad[0] = r.sum()
        for g, o, s in zip(groups, offs, sizes):
            grad[o:o + s] = np.bincount(idx[g], weights=r, minlength=s)
        grad += lam * theta
        return nll, grad

    res = minimize(f, np.zeros(npar), jac=True, method="L-BFGS-B",
                   options={"maxiter": maxiter, "gtol": 1e-6})
    theta = res.x
    eff = {}
    b0 = float(theta[0])
    for g, o, s in zip(groups, offs, sizes):
        a = theta[o:o + s].copy()
        w = np.bincount(idx[g], minlength=s).astype(float)
        mu = float((a * w).sum() / w.sum()) if w.sum() > 0 else 0.0
        eff[g] = a - mu
        b0 += mu
    L = L0 + b0
    for g in groups:
        L = L + eff[g][idx[g]]
    b0 += solve_shift(L, float(y.sum()))
    return b0, eff, {"converged": bool(res.success), "iterations": int(res.nit), "nll": float(res.fun)}


def heldout_loglik(L0, y, idx: dict, b0: float, eff: dict, known: dict) -> float:
    """Mean log-likelihood on held-out rows; a person unseen in the fit carries 0."""
    L = np.asarray(L0, dtype=float) + b0
    for g, codes in idx.items():
        a = np.zeros(len(codes))
        ok = known[g] >= 0
        a[ok] = eff[g][known[g][ok]]
        L = L + a
    p = np.clip(expit(L), 1e-12, 1 - 1e-12)
    y = np.asarray(y, dtype=float)
    return float((y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


# --------------------------------------------------------------------------
# part 4.3: the per-pitch shares
# --------------------------------------------------------------------------
def shares(L0, parts: dict):
    """{group: d_g} with sum d_g = expit(L0 + sum a) - expit(L0) exactly (secant slope)."""
    L0 = np.asarray(L0, dtype=float)
    tot = np.zeros_like(L0)
    for a in parts.values():
        tot = tot + a
    p0 = expit(L0)
    pf = expit(L0 + tot)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(np.abs(tot) > 1e-12, (pf - p0) / np.where(tot == 0, 1, tot), p0 * (1 - p0))
    return {g: m * a for g, a in parts.items()}, pf - p0


# --------------------------------------------------------------------------
# part 3.1: a called pitch's components
# --------------------------------------------------------------------------
def called_components(v_before, v_ball, v_strike, z, s0, s1, d_c, d_p, d_b, dre):
    """Arrays of gate part 3.1. z, s0, s1 in {0, 1}; v = v_ball - v_strike."""
    v_before, v_ball, v_strike = (np.asarray(a, dtype=float) for a in (v_before, v_ball, v_strike))
    z, s0, s1, d_c, d_p, d_b, dre = (np.asarray(a, dtype=float) for a in (z, s0, s1, d_c, d_p, d_b, dre))
    v = v_ball - v_strike

    def val(call):
        return np.where(call >= 0.5, v_strike, v_ball)
    out = {
        "x_duel": val(z) - v_before,
        "x_bcs": -d_b * v,
        "x_pcs": -d_p * v,
        "x_frm": -d_c * v,
        "x_ump": -(s0 - z - d_c - d_p - d_b) * v,
        "x_ch": val(s1) - val(s0),
    }
    out["x_oth"] = dre - (val(s1) - v_before)
    return out


# --------------------------------------------------------------------------
# part 5: the cell models
# --------------------------------------------------------------------------
def cell_means(keys, vals):
    """{key: (n, mean)} for hashable keys."""
    d: dict = {}
    for k, v in zip(keys, vals):
        n, s = d.get(k, (0, 0.0))
        d[k] = (n + 1, s + float(v))
    return {k: (n, s / n) for k, (n, s) in d.items()}


def ev_bin(ls):
    if ls is None or not math.isfinite(ls):
        return None
    if ls < 60:
        return 0
    if ls >= 115:
        return 12
    return 1 + int((ls - 60) // 5)


def la_bin(la):
    if la is None or not math.isfinite(la):
        return None
    if la < -30:
        return 0
    if la >= 60:
        return 16
    return 1 + int((la + 30) // 6)


def spray_bin(hx, hy):
    if hx is None or hy is None or not (math.isfinite(hx) and math.isfinite(hy)):
        return 8
    phi = math.degrees(math.atan2(hx - 125.42, 198.27 - hy))
    if phi < -45:
        return 0
    if phi >= 45:
        return 7
    return 1 + int((phi + 45) // 15)


def contact_cell(ls, la, hx, hy, trajectory, hit_location):
    e, a = ev_bin(ls), la_bin(la)
    if e is not None and a is not None:
        return ("t", e, a, spray_bin(hx, hy))
    return ("f", str(trajectory), str(hit_location))


def expected_contact(cells, bo, dre):
    """x_x of gate part 5.1 and its season shift (x_fld sums to 0)."""
    dre = np.asarray(dre, dtype=float)
    bo = list(bo)
    m_bo = cell_means(bo, dre)
    base = np.array([m_bo[k][1] for k in bo])
    r1 = dre - base
    m_c = cell_means(cells, r1)
    rc = np.array([m_c[k][1] for k in cells])
    r2 = r1 - rc
    inter_keys = list(zip(cells, bo))
    m_i = cell_means(inter_keys, r2)
    ii = np.array([m_i[k][1] * m_i[k][0] / (m_i[k][0] + K_INTERACTION) for k in inter_keys])
    x = base + rc + ii
    shift = float((dre - x).mean()) if len(x) else 0.0
    return x + shift, shift


def blocking_cell(zn, xm, pgroup, bits):
    if zn is None or xm is None or not (math.isfinite(zn) and math.isfinite(xm)):
        zb, xb = 9, 9
    else:
        zb = -1 if zn < -0.25 else min(int((zn + 0.25) // 0.25), 8)
        xb = min(int(abs(xm) // 0.5), 4)
    return (zb, xb, int(pgroup), int(bits))


def identity_ok(comp: dict, dre) -> np.ndarray:
    tot = np.zeros(len(dre))
    for c in COMPONENTS:
        if c in comp:
            tot = tot + np.nan_to_num(np.asarray(comp[c], dtype=float))
    return np.abs(tot - np.asarray(dre, dtype=float)) <= IDENTITY_TOL
