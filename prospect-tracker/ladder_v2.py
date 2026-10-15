# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Positional ladder v2: the position-switcher network ladder (docs/ewar/LADDER_V2_GATE.md).

WHAT THIS IS
    The positional adjustment measured from what players do when they change
    position, on three fielding sources, instead of recovered from the constants
    one site publishes. v1 (positional_fit.fit_ladder) inverts Baseball-Reference's
    runs_position, so a v1 rung reads "what Baseball-Reference prices the position
    at". A v2 rung reads "how many fielding runs the same player gains or loses
    moving there", which is what a positional adjustment exists to cancel.

THE FIT, per fielding source S (BREF runs_field, FanGraphs fld, Savant FRP)
    across-season rows, the same player in seasons t-1 and t (gate amendment A1):
        r_t = alpha + beta (age_{t-1} - 27) + k r_{t-1} + sum_p (s_{t,p} - s_{t-1,p}) D_p
    within-season rows (Savant only, the source that splits runs by position):
        r_b - r_a = D_b - D_a
    r = fielding runs per UNIT_INN fielded innings, s = fielded-innings shares,
    k = glove persistence (a linear coefficient). Every source centres its runs
    within position, so the mean glove of the players seen at a position is that
    position's rung; conditioning on r_{t-1} against that prior keeps a move made
    after a bad year from reading as position difficulty, and stayers (whose share
    change is zero) set alpha, beta and k while switchers identify D.
    L_S(p) = -D_S(p).
    Sources are aligned on the seven Statcast positions and pooled by inverse
    variance; C and DH are attached by the gate's part 3; everything is recentred
    on one exposure vector (gate part 4).

    Every function here takes plain records, so the lab's fixture dry run and the
    real read go through the same code. tools/ladder_v2_lab.py is the read;
    `python ladder_v2.py` rebuilds data/positional_ladder_v2.json from the frozen
    read (exposure vector and verdict) without re-scoring anything.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EVAL_PATH = DATA_DIR / "positional_ladder_v2_eval.json"
OUT_PATH = DATA_DIR / "positional_ladder_v2.json"

#: The gate's unit: 650 PA x 1.9657 innings per PA, the served v1 conversion.
UNIT_INN = 1277.7
FIELD = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
OAA7 = ("1B", "2B", "3B", "SS", "LF", "CF", "RF")
LADDER9 = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")
SOURCES = ("BREF", "FG", "SAVANT")
SOURCE_POS = {"BREF": FIELD, "FG": FIELD, "SAVANT": OAA7}

# Gate constants (docs/ewar/LADDER_V2_GATE.md). Changing one is an amendment.
ACROSS_MIN_INN = 300.0
SWITCH_TVD = 0.25
WITHIN_MIN_INN = 150.0
MAX_P_INN = 20.0
SAVANT_MAX_C_SHARE = 0.05
AGE_CENTRE = 27.0
CONSTRAINT_W = 1000.0
DH_MIN_SHARE = 0.25
DH_MIN_1B_SHARE = 0.90
DH_MIN_INN = 150.0
C_MAX_SE = 1.5
C_MIN_ROWS = 30
C_CHANGE = 0.25
OFF_MIN_PA = 400
OFF_PRIMARY_SHARE = 0.75
FG_TABLE_162 = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5,
                "LF": -7.5, "RF": -7.5, "1B": -12.5, "DH": -17.5}
FULL_SEASON_INN = 1458.0


def _hm(a: float, b: float) -> float:
    return 2.0 / (1.0 / a + 1.0 / b) if a > 0 and b > 0 else 0.0


# ======================================================================= records
# One record per (mlbam, season):
#   inn      {pos: innings} over FIELD (StatsAPI)       p_inn  innings at P
#   dh_g     DH games      fld_g  games at fielding positions
#   age      Baseball-Reference season age or None
#   runs     {"BREF": float|None, "FG": float|None}     season totals
#   sav      {pos: frp} over OAA7, or None               Savant per position
#   pa, runs_bat, runs_position, fg_pos                  (v1 / c / FG inversion)

def source_view(rec: dict, src: str):
    """(positions, shares array, fielded innings, runs) for one source, or None."""
    inn = rec.get("inn") or {}
    if src == "SAVANT":
        sav = rec.get("sav")
        if not sav:
            return None
        tot8 = sum(inn.get(p, 0.0) for p in FIELD)
        if tot8 <= 0 or inn.get("C", 0.0) > SAVANT_MAX_C_SHARE * tot8:
            return None
        pos = OAA7
        runs = float(sum(v for p, v in sav.items() if p in OAA7 and v is not None))
    else:
        runs = (rec.get("runs") or {}).get(src)
        if runs is None:
            return None
        pos = FIELD
        runs = float(runs)
    fielded = sum(inn.get(p, 0.0) for p in pos)
    if fielded <= 0:
        return None
    shares = np.array([inn.get(p, 0.0) / fielded for p in pos])
    return pos, shares, fielded, runs


class Rows:
    """Numpy row tables for one source: across-season (A) and within-season (B)."""

    def __init__(self, src: str):
        self.src = src
        self.pos = SOURCE_POS[src]
        self.A = None
        self.B = None
        self.DHT = None


def build_rows(records: dict) -> dict:
    """{src: Rows} from the record dict. Pure; no fitting."""
    out = {}
    for src in SOURCES:
        R = Rows(src)
        P = len(R.pos)
        m_, t_, r0_, r1_, w_, age_, f0_, f1_ = [], [], [], [], [], [], [], []
        S0_, S1_ = [], []
        for (m, t), rec in records.items():
            prev = records.get((m, t - 1))
            if prev is None:
                continue
            if (rec.get("p_inn") or 0.0) > MAX_P_INN or (prev.get("p_inn") or 0.0) > MAX_P_INN:
                continue
            v1 = source_view(rec, src)
            v0 = source_view(prev, src)
            if v1 is None or v0 is None:
                continue
            if v0[2] < ACROSS_MIN_INN or v1[2] < ACROSS_MIN_INN:
                continue
            m_.append(m)
            t_.append(t)
            r0_.append(v0[3] / v0[2] * UNIT_INN)
            r1_.append(v1[3] / v1[2] * UNIT_INN)
            S0_.append(v0[1])
            S1_.append(v1[1])
            w_.append(_hm(v0[2], v1[2]) / 1000.0)
            age = prev.get("age")
            age_.append(np.nan if age is None else float(age))
            f0_.append(v0[2])
            f1_.append(v1[2])
        S0 = np.array(S0_).reshape(-1, P)
        S1 = np.array(S1_).reshape(-1, P)
        tvd = 0.5 * np.abs(S1 - S0).sum(axis=1) if len(S0_) else np.zeros(0)
        ci = R.pos.index("C") if "C" in R.pos else None
        R.A = {
            "m": np.array(m_, dtype=np.int64), "t": np.array(t_, dtype=np.int64),
            "r0": np.array(r0_), "r1": np.array(r1_), "S0": S0, "S1": S1,
            "w": np.array(w_), "age": np.array(age_),
            "switch": tvd >= SWITCH_TVD, "tvd": tvd,
            "cchg": (np.abs(S1[:, ci] - S0[:, ci]) if ci is not None and len(S0_)
                     else np.zeros(len(m_))),
        }
        # within-season pairs: Savant only
        bm, bt, ba, bb, bra, brb, bw = [], [], [], [], [], [], []
        if src == "SAVANT":
            for (m, t), rec in records.items():
                sav = rec.get("sav")
                if not sav or (rec.get("p_inn") or 0.0) > MAX_P_INN:
                    continue
                inn = rec.get("inn") or {}
                ok = [p for p in OAA7 if inn.get(p, 0.0) >= WITHIN_MIN_INN
                      and sav.get(p) is not None]
                for i in range(len(ok)):
                    for j in range(i + 1, len(ok)):
                        a, b = ok[i], ok[j]
                        bm.append(m)
                        bt.append(t)
                        ba.append(OAA7.index(a))
                        bb.append(OAA7.index(b))
                        bra.append(sav[a] / inn[a] * UNIT_INN)
                        brb.append(sav[b] / inn[b] * UNIT_INN)
                        bw.append(_hm(inn[a], inn[b]) / 1000.0)
        R.B = {"m": np.array(bm, dtype=np.int64), "t": np.array(bt, dtype=np.int64),
               "a": np.array(ba, dtype=np.int64), "b": np.array(bb, dtype=np.int64),
               "ra": np.array(bra), "rb": np.array(brb), "w": np.array(bw)}
        # DH-type player-seasons: their fielding rate at 1B (gate part 3)
        dm, dt, dr = [], [], []
        for (m, t), rec in records.items():
            if (rec.get("p_inn") or 0.0) > MAX_P_INN:
                continue
            dh_g = rec.get("dh_g") or 0
            fld_g = rec.get("fld_g") or 0
            if dh_g + fld_g <= 0 or dh_g / (dh_g + fld_g) < DH_MIN_SHARE:
                continue
            inn = rec.get("inn") or {}
            tot8 = sum(inn.get(p, 0.0) for p in FIELD)
            if tot8 < DH_MIN_INN or inn.get("1B", 0.0) < DH_MIN_1B_SHARE * tot8:
                continue
            if src == "SAVANT":
                sav = rec.get("sav") or {}
                if sav.get("1B") is None or inn.get("1B", 0.0) <= 0:
                    continue
                r = sav["1B"] / inn["1B"] * UNIT_INN
            else:
                v = source_view(rec, src)
                if v is None:
                    continue
                r = v[3] / v[2] * UNIT_INN
            dm.append(m)
            dt.append(t)
            dr.append(r)
        R.DHT = {"m": np.array(dm, dtype=np.int64), "t": np.array(dt, dtype=np.int64),
                 "r": np.array(dr)}
        out[src] = R
    return out


# ================================================================ the network
def _season_mask_A(A, seasons, drop=None):
    """Across rows whose later season is in `seasons` and neither season is `drop`."""
    mk = np.isin(A["t"], list(seasons))
    if drop is not None:
        mk &= (A["t"] != drop) & (A["t"] - 1 != drop)
    return mk


def fit_network(R: Rows, e9: dict, mA=None, mB=None, wmult=None):
    """WLS fit of the difficulty vector D for one source (gate part 1, b).

    mA / mB: boolean masks selecting training rows. wmult: per-player weight
    multiplier {mlbam: count} for the cluster bootstrap (None = 1).
    Returns None when there is nothing to fit."""
    A, B = R.A, R.B
    P = len(R.pos)
    if mA is None:
        mA = np.ones(len(A["m"]), dtype=bool)
    if mB is None:
        mB = np.ones(len(B["m"]), dtype=bool)
    mA = mA & ~np.isnan(A["age"])
    wA = A["w"][mA].copy()
    wB = B["w"][mB].copy()
    if wmult is not None:
        wA = wA * wmult(A["m"][mA])
        wB = wB * wmult(B["m"][mB])
        keepA = wA > 0
        keepB = wB > 0
    else:
        keepA = np.ones(len(wA), dtype=bool)
        keepB = np.ones(len(wB), dtype=bool)
    r0 = A["r0"][mA][keepA]
    r1 = A["r1"][mA][keepA]
    S0 = A["S0"][mA][keepA]
    S1 = A["S1"][mA][keepA]
    age = A["age"][mA][keepA] - AGE_CENTRE
    wA = wA[keepA]
    ba = B["a"][mB][keepB]
    bb = B["b"][mB][keepB]
    dyB = (B["rb"][mB] - B["ra"][mB])[keepB]
    wB = wB[keepB]
    nA, nB = len(wA), len(wB)
    if nA + nB < 12:
        return None
    XB = np.zeros((nB, P))
    if nB:
        XB[np.arange(nB), bb] += 1.0
        XB[np.arange(nB), ba] -= 1.0
    # positions with no information in this fit are dropped (a null cell)
    info = np.zeros(P)
    if nA:
        info += np.abs(S1 - S0).sum(axis=0)
    if nB:
        info += np.abs(XB).sum(axis=0)
    keep = info > 0
    if keep.sum() < 2:
        return None
    kidx = np.where(keep)[0]
    e = np.array([e9.get(R.pos[i], 0.0) for i in kidx])
    e = e / e.sum() if e.sum() > 0 else np.full(len(kidx), 1.0 / len(kidx))
    sA = np.sqrt(wA)
    sB = np.sqrt(wB)
    XA = np.hstack([np.ones((nA, 1)), age[:, None], r0[:, None], (S1 - S0)[:, kidx]])
    XBk = np.hstack([np.zeros((nB, 3)), XB[:, kidx]])
    con = np.concatenate([[0.0, 0.0, 0.0], e])[None, :]
    X = np.vstack([XA * sA[:, None], XBk * sB[:, None], con * CONSTRAINT_W])
    y = np.concatenate([r1 * sA, dyB * sB, [0.0]])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y[:-1] - X[:-1] @ beta
    sse = float(res @ res)
    k = float(beta[2])
    dof = max(1, nA + nB - (3 + len(kidx)))
    sigma2 = sse / dof
    try:
        cov = sigma2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        cov = sigma2 * np.linalg.pinv(X.T @ X)
    D = {p: None for p in R.pos}
    V = {p: None for p in R.pos}
    for j, i in enumerate(kidx):
        D[R.pos[i]] = float(beta[3 + j])
        V[R.pos[i]] = float(max(cov[3 + j, 3 + j], 1e-9))
    nsw = int(A["switch"][mA][keepA].sum()) if nA else 0
    ncc = int((A["cchg"][mA][keepA] >= C_CHANGE).sum()) if nA else 0
    return {"src": R.src, "D": D, "var": V, "k": k, "alpha": float(beta[0]),
            "beta_age": float(beta[1]), "n_across": nA, "n_within": nB,
            "n_switch": nsw, "n_c_change": ncc, "sigma2": sigma2}


def source_ladder(fit: dict, e9: dict) -> dict:
    """L_S = -D_S, aligned so the exposure-weighted mean over the seven Statcast
    positions it rates is zero. {pos: (value, var)}; positions it lacks are absent."""
    have = [p for p in OAA7 if fit["D"].get(p) is not None]
    if not have:
        return {}
    w = np.array([e9[p] for p in have])
    w = w / w.sum()
    mean7 = float(sum(wi * -fit["D"][p] for wi, p in zip(w, have)))
    out = {}
    for p, d in fit["D"].items():
        if d is None:
            continue
        out[p] = (-d - mean7, fit["var"][p])
    return out


def dh_mu(R: Rows, mask=None, wmult=None):
    """Mean 1B fielding rate of DH-type player-seasons for one source: (mu, var, n)."""
    D = R.DHT
    if mask is None:
        mask = np.ones(len(D["m"]), dtype=bool)
    r = D["r"][mask]
    w = np.ones(len(r))
    if wmult is not None:
        w = wmult(D["m"][mask]).astype(float)
    if w.sum() < 2:
        return None
    mu = float((w * r).sum() / w.sum())
    var = float((w * (r - mu) ** 2).sum() / max(1.0, w.sum() - 1.0))
    return mu, var / w.sum(), float(w.sum())


def recentre(L: dict, e9: dict) -> dict:
    c = sum(e9[p] * L[p] for p in LADDER9)
    return {p: L[p] - c for p in LADDER9}


def mean7(L: dict, e9: dict) -> float:
    w = np.array([e9[p] for p in OAA7])
    w = w / w.sum()
    return float(sum(wi * L[p] for wi, p in zip(w, OAA7)))


def pool_ladder(fits: dict, dhs: dict, e9: dict, v1_for_c: dict):
    """The gate's (b): pool the source legs, attach C and DH, recentre.
    fits {src: fit or None}; dhs {src: (mu, var, n) or None};
    v1_for_c: the v1 ladder used when the C rule falls back.
    Returns (ladder9, var9, info) or (None, None, info)."""
    legs = {s: source_ladder(f, e9) for s, f in fits.items() if f}
    info = {"legs": {s: {p: round(v[0], 4) for p, v in L.items()} for s, L in legs.items()}}
    L, V = {}, {}
    for p in OAA7:
        num = den = 0.0
        for s, leg in legs.items():
            if p in leg:
                num += leg[p][0] / leg[p][1]
                den += 1.0 / leg[p][1]
        if den <= 0:
            return None, None, dict(info, error=f"no source rates {p}")
        L[p] = num / den
        V[p] = 1.0 / den
    # C: the BREF and FG network, else carried from v1 (gate part 3)
    num = den = 0.0
    for s in ("BREF", "FG"):
        if s in legs and "C" in legs[s]:
            num += legs[s]["C"][0] / legs[s]["C"][1]
            den += 1.0 / legs[s]["C"][1]
    n_cc = max([fits[s]["n_c_change"] for s in ("BREF", "FG") if fits.get(s)] or [0])
    c_se = math.sqrt(1.0 / den) if den > 0 else None
    if den > 0 and c_se <= C_MAX_SE and n_cc >= C_MIN_ROWS:
        L["C"] = num / den
        V["C"] = 1.0 / den
        info["c_branch"] = "network"
    elif v1_for_c is None:
        return None, None, dict(info, error="C falls back to v1 and no v1 ladder was given")
    else:
        L["C"] = v1_for_c["C"] - mean7(v1_for_c, e9)
        V["C"] = None
        info["c_branch"] = "carried_from_v1"
    info["c_network"] = None if den <= 0 else round(num / den, 4)
    info["c_network_se"] = None if c_se is None else round(c_se, 4)
    info["c_rows"] = n_cc
    # DH: L(1B) + the 1B rate of DH-type player-seasons, pooled
    num = den = 0.0
    nd = 0.0
    for s, d in dhs.items():
        if d and d[1] > 0:
            num += d[0] / d[1]
            den += 1.0 / d[1]
            nd += d[2]
    if den <= 0:
        return None, None, dict(info, error="no DH-type rows")
    mu = num / den
    L["DH"] = L["1B"] + mu
    V["DH"] = V["1B"] + 1.0 / den
    info["dh_mu"] = round(mu, 4)
    info["dh_mu_se"] = round(math.sqrt(1.0 / den), 4)
    info["dh_rows"] = nd
    return recentre(L, e9), V, info


# ======================================================= v1, c, FG inversion
def inversion_rows(records: dict, seasons, min_pa: int = 200, y_key="runs_position"):
    """positional_fit._ladder_design's construction on records: innings shares with
    a residual DH column, y = y_key per 650 PA. Returns (X, y, keys, inn_per_pa)."""
    ipp = []
    for (m, t), rec in records.items():
        if t not in seasons or (rec.get("pa") or 0) < 400:
            continue
        tot = sum((rec.get("inn") or {}).get(p, 0.0) for p in FIELD)
        if tot > 0:
            ipp.append(tot / rec["pa"])
    inn_per_pa = float(np.median(ipp)) if ipp else 1.98
    X, y, keys = [], [], []
    for (m, t), rec in records.items():
        if t not in seasons:
            continue
        pa = rec.get("pa") or 0
        yy = rec.get(y_key)
        if pa < min_pa or yy is None:
            continue
        inn = rec.get("inn") or {}
        if not inn:
            continue
        ex = {p: float(inn.get(p, 0.0)) for p in FIELD}
        fielded = sum(ex.values())
        ex["DH"] = max(0.0, pa * inn_per_pa - fielded)
        tot = sum(ex.values())
        if tot <= 0:
            continue
        X.append([ex[p] / tot for p in LADDER9])
        y.append(yy / pa * 650.0)
        keys.append((m, t))
    return np.array(X).reshape(-1, 9), np.array(y), keys, inn_per_pa


def fit_inversion(records, seasons, e9, y_key="runs_position", want_var=False):
    X, y, keys, ipp = inversion_rows(records, seasons, y_key=y_key)
    if len(y) < 30:
        return (None, None) if want_var else None
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    L = recentre({p: float(v) for p, v in zip(LADDER9, b)}, e9)
    if not want_var:
        return L
    res = y - X @ b
    s2 = float(res @ res) / max(1, len(y) - 9)
    try:
        cov = s2 * np.linalg.inv(X.T @ X)
        V = {p: float(max(cov[i, i], 1e-9)) for i, p in enumerate(LADDER9)}
    except np.linalg.LinAlgError:
        V = {p: None for p in LADDER9}
    return L, V


def fit_offense(records, seasons, e9):
    """The gate's (c): the hitting gap by primary position among regulars."""
    acc = defaultdict(lambda: [0.0, 0.0])
    for (m, t), rec in records.items():
        if t not in seasons:
            continue
        pa = rec.get("pa") or 0
        rb = rec.get("runs_bat")
        if pa < OFF_MIN_PA or rb is None:
            continue
        inn = rec.get("inn") or {}
        tot = sum(inn.get(p, 0.0) for p in FIELD)
        dh_g = rec.get("dh_g") or 0
        fld_g = rec.get("fld_g") or 0
        prim = None
        if dh_g + fld_g > 0 and dh_g / (dh_g + fld_g) >= OFF_PRIMARY_SHARE:
            prim = "DH"
        elif tot > 0:
            p, v = max(((p, inn.get(p, 0.0)) for p in FIELD), key=lambda kv: kv[1])
            if v >= OFF_PRIMARY_SHARE * tot:
                prim = p
        if prim is None:
            continue
        acc[prim][0] += rb / pa * 650.0 * pa
        acc[prim][1] += pa
    if any(acc[p][1] <= 0 for p in LADDER9):
        return None
    tot_pa = sum(acc[p][1] for p in LADDER9)
    grand = sum(acc[p][0] for p in LADDER9) / tot_pa
    return recentre({p: -(acc[p][0] / acc[p][1] - grand) for p in LADDER9}, e9)


def fg_table_ladder(e9):
    return recentre({p: v * UNIT_INN / FULL_SEASON_INN for p, v in FG_TABLE_162.items()}, e9)


# ======================================================== the b pipeline
def fit_b(rows: dict, e9: dict, v1_for_c: dict, seasons, drop=None, wmult=None,
          return_fits=False):
    """(b) on the given seasons (later season of a row), excluding `drop`."""
    fits, dhs = {}, {}
    for s, R in rows.items():
        mA = _season_mask_A(R.A, seasons, drop)
        mB = np.isin(R.B["t"], list(seasons))
        mD = np.isin(R.DHT["t"], list(seasons))
        if drop is not None:
            mB &= R.B["t"] != drop
            mD &= R.DHT["t"] != drop
        fits[s] = fit_network(R, e9, mA, mB, wmult=wmult)
        dhs[s] = dh_mu(R, mD, wmult=wmult)
    L, V, info = pool_ladder(fits, dhs, e9, v1_for_c)
    info["fits"] = {s: (None if f is None else {
        "k": round(f["k"], 4), "alpha": round(f["alpha"], 4), "beta_age": round(f["beta_age"], 4),
        "n_across": f["n_across"], "n_within": f["n_within"], "n_switch": f["n_switch"],
        "n_c_change": f["n_c_change"]}) for s, f in fits.items()}
    if return_fits:
        return L, V, info, fits
    return L, V, info


# ================================================================ scoring
def _T(r, S, Lvec):
    return r + S @ Lvec


def score_rows(rows: dict, ladders: dict, t: int, train_seasons) -> list:
    """Held-out loss rows for season t. ladders {name: ladder9}.
    Returns [(mlbam, src, kind, w, {name: (abs, sq)}, t)]."""
    out = []
    for s, R in rows.items():
        A = R.A
        P = R.pos
        trn = _season_mask_A(A, train_seasons, drop=t)
        tst = (A["t"] == t) & A["switch"]
        if tst.any():
            preds = {}
            for name, L in ladders.items():
                if L is None:
                    continue
                # gate amendment A2: T_t_hat = a_L + k_L r_{t-1} + sum_p s_{t-1,p} L_p,
                # (a_L, k_L) by WLS of T_t - L.s_{t-1} on [1, r_{t-1}] over training rows
                Lv = np.array([L[p] for p in P])
                y = _T(A["r1"], A["S1"], Lv) - A["S0"] @ Lv
                w = A["w"][trn]
                X = np.vstack([np.ones(trn.sum()), A["r0"][trn]]).T
                sw = np.sqrt(w)
                ab, *_ = np.linalg.lstsq(X * sw[:, None], y[trn] * sw, rcond=None)
                preds[name] = y[tst] - (ab[0] + ab[1] * A["r0"][tst])
            ms = A["m"][tst]
            ws = A["w"][tst]
            for i in range(len(ms)):
                out.append((int(ms[i]), s, "across", float(ws[i]),
                            {n: (abs(float(e[i])), float(e[i]) ** 2) for n, e in preds.items()},
                            t))
        B = R.B
        tb = B["t"] == t
        if tb.any():
            errs = {}
            for name, L in ladders.items():
                if L is None:
                    continue
                Lv = np.array([L[p] for p in OAA7])
                errs[name] = (B["rb"][tb] + Lv[B["b"][tb]]) - (B["ra"][tb] + Lv[B["a"][tb]])
            ms = B["m"][tb]
            ws = B["w"][tb]
            for i in range(len(ms)):
                out.append((int(ms[i]), s, "within", float(ws[i]),
                            {n: (abs(float(e[i])), float(e[i]) ** 2) for n, e in errs.items()},
                            t))
    return out


def summarize(loss_rows: list, names, sel=None) -> dict:
    """Weighted MAE / MSE per ladder over the selected rows."""
    out = {}
    rs = [r for r in loss_rows if sel is None or sel(r)]
    W = sum(r[3] for r in rs)
    for n in names:
        if W <= 0 or any(n not in r[4] for r in rs):
            out[n] = None
            continue
        out[n] = {"mae": sum(r[3] * r[4][n][0] for r in rs) / W,
                  "mse": sum(r[3] * r[4][n][1] for r in rs) / W,
                  "n_rows": len(rs), "weight": W}
    return out


def cluster_boot(loss_rows: list, a: str, b: str, sel=None, draws=2000, seed=20261015):
    """dMAE = MAE(a) - MAE(b) (positive favours b) with a paired player-cluster
    bootstrap. Also dMSE. Returns None when there is nothing to compare."""
    rs = [r for r in loss_rows if (sel is None or sel(r)) and a in r[4] and b in r[4]]
    if not rs:
        return None
    pid = {}
    for r in rs:
        pid.setdefault(r[0], len(pid))
    n = len(pid)
    W = np.zeros(n)
    Aa = np.zeros(n)
    Ab = np.zeros(n)
    Sa = np.zeros(n)
    Sb = np.zeros(n)
    for r in rs:
        i = pid[r[0]]
        W[i] += r[3]
        Aa[i] += r[3] * r[4][a][0]
        Ab[i] += r[3] * r[4][b][0]
        Sa[i] += r[3] * r[4][a][1]
        Sb[i] += r[3] * r[4][b][1]
    d_mae = (Aa.sum() - Ab.sum()) / W.sum()
    d_mse = (Sa.sum() - Sb.sum()) / W.sum()
    rng = np.random.default_rng(seed)
    bm, bs = [], []
    for _ in range(draws):
        c = rng.multinomial(n, np.full(n, 1.0 / n))
        ww = (c * W).sum()
        bm.append(((c * Aa).sum() - (c * Ab).sum()) / ww)
        bs.append(((c * Sa).sum() - (c * Sb).sum()) / ww)
    bm = np.array(bm)
    bs = np.array(bs)
    return {"dmae": float(d_mae),
            "ci95": [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))],
            "dmse": float(d_mse),
            "dmse_ci95": [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
            "n_rows": len(rs), "n_players": n, "draws": draws, "seed": seed}


# ======================================================= per-season shrink (d)
def per_season_shrunk(single: dict, pooled: dict, pooled_var_single: dict,
                      neighbours) -> tuple:
    """single {season: ladder9}; pooled ladder9; pooled_var_single {season: var9}
    (the single-season fits' sampling variances); neighbours: seasons whose
    deviation is applied. Returns (ladder9, shrink {pos: factor}, tau2)."""
    seasons = [s for s, L in single.items() if L is not None]
    out, fac, tau = {}, {}, {}
    for p in LADDER9:
        devs = [single[s][p] - pooled[p] for s in seasons]
        vs = [pooled_var_single[s].get(p) for s in seasons
              if pooled_var_single.get(s) and pooled_var_single[s].get(p) is not None]
        if len(devs) < 3 or not vs:
            out[p], fac[p], tau[p] = pooled[p], 0.0, None
            continue
        t2 = max(0.0, float(np.var(devs, ddof=1)) - float(np.mean(vs)))
        nb = [s for s in neighbours if s in seasons]
        if not nb:
            out[p], fac[p], tau[p] = pooled[p], 0.0, t2
            continue
        vn = [pooled_var_single[s].get(p) for s in nb if pooled_var_single.get(s)]
        vn = [v for v in vn if v is not None]
        vbar = float(np.mean(vn)) if vn else float(np.mean(vs))
        f = t2 / (t2 + vbar / len(nb)) if (t2 + vbar) > 0 else 0.0
        out[p] = pooled[p] + f * float(np.mean([single[s][p] - pooled[p] for s in nb]))
        fac[p], tau[p] = f, t2
    return out, fac, tau


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def ladder_round(L, nd=4):
    return None if L is None else {p: _r(L[p], nd) for p in LADDER9}


def write_eval(record: dict) -> None:
    """Write the read's record (the Library's Positional Ladder view reads it)."""
    EVAL_PATH.write_text(json.dumps(record, indent=1) + chr(10), encoding="utf-8")


def identification(values: dict, e9: dict) -> dict:
    """The sums block positional_fit publishes for v1, for the same reason: only
    the exposure-weighted sum is zero; the display column centres the eight
    fielding rungs (the folklore convention) and shifts every rung by one constant."""
    fielders = [p for p in LADDER9 if p != "DH"]
    s8 = sum(values[p] for p in fielders)
    return {
        "convention": "exposure-weighted sum-to-zero",
        "sum_exposure_weighted": round(sum(e9[p] * values[p] for p in LADDER9), 4),
        "sum_equal_weight_9": round(sum(values[p] for p in LADDER9), 3),
        "sum_equal_weight_fielders": round(s8, 3),
        "exposure_share": {p: e9[p] for p in LADDER9},
        "values_fielder_centred": {p: round(values[p] - s8 / len(fielders), 2)
                                   for p in LADDER9},
    }


# ============================================================ the producer
def main() -> int:
    """Rebuild data/positional_ladder_v2.json from the frozen read. The read itself
    (and the scoring) is tools/ladder_v2_lab.py --read, which runs once."""
    if not EVAL_PATH.exists():
        print("positional_ladder_v2: no read recorded (data/positional_ladder_v2_eval.json); "
              "run tools/ladder_v2_lab.py --read once")
        return 1
    ev = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    payload = ev.get("ladder_artifact")
    if not payload:
        print("positional_ladder_v2: the read carries no ladder_artifact block")
        return 1
    payload = dict(payload)
    payload["verdict"] = ev.get("verdict")
    payload["identification"] = identification(payload["values"], payload["exposure_share"])
    OUT_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
