# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Positional ladder v3: the corrected re-read (docs/ewar/LADDER_V3_GATE.md).

WHAT THIS IS
    The re-read the v2 verification asked for (owner decision EW3-29). Fielding
    runs only set the gaps INSIDE the infield (2B, 3B, SS) and INSIDE the
    outfield (LF, CF, RF), measured on the same players moving between them, on
    three sources with Statcast fielding runs centred within (position, season)
    and the player's own level over all his seasons (a player fixed effect,
    gate amendment A1). The level of each group, 1B and DH come from
    the registered anchor, the offense-equalizing gap among regulars; C is
    carried from v1. Everything is scored against an all-zero fielding ladder,
    v1 and scaled copies of v1, and the fitting step must recover a planted
    ladder on a real-design simulation.

    Every function here takes plain records, so the lab's fixture dry run, the
    simulation and the real read go through the same code. tools/ladder_v3_lab.py
    is the read.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import ladder_v2 as L2

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EVAL_PATH = DATA_DIR / "positional_ladder_v3_eval.json"
OUT_PATH = DATA_DIR / "positional_ladder_v3.json"

UNIT_INN = L2.UNIT_INN
FIELD, OAA7, LADDER9, SOURCES = L2.FIELD, L2.OAA7, L2.LADDER9, L2.SOURCES
IF3 = ("2B", "3B", "SS")
OF3 = ("LF", "CF", "RF")
GROUPS = {"IF": IF3, "OF": OF3}
GROUP_REF = {"IF": "SS", "OF": "CF"}

# Gate constants (docs/ewar/LADDER_V3_GATE.md). Changing one is an amendment.
GROUP_MIN_SHARE = 0.95
EARLY_MIN_INN = 150.0
RECOVERY_LO = 0.80
RECOVERY_HI = 1.25
SIM_SEEDS = (7, 8, 9, 10, 11)
SIM_SD_GLOVE = 5.0
SIM_SD_SEASON = 6.0
SIM_AGE_SLOPE = 0.18
SIM_TOTAL_SD = 2.0
SIM_STRESS = 3.0
SIM_MOVER_SHARE = 0.75


# ===================================================================== data
def centre_savant(recs: dict) -> dict:
    """Records with every Statcast FRP centred within (position, season):
    frp - inn_p x (sum frp / sum inn at p that season). Gate part 2."""
    acc = defaultdict(lambda: [0.0, 0.0])
    for (m, t), r in recs.items():
        if r.get("sav"):
            for p, v in r["sav"].items():
                i = (r.get("inn") or {}).get(p, 0.0)
                if i > 0 and v is not None:
                    acc[(p, t)][0] += v
                    acc[(p, t)][1] += i
    out = {}
    for k, r in recs.items():
        if r.get("sav"):
            rr = dict(r)
            rr["sav"] = {p: (v - acc[(p, k[1])][0] / acc[(p, k[1])][1] * r["inn"].get(p, 0.0)
                             if acc[(p, k[1])][1] > 0 and v is not None else v)
                         for p, v in r["sav"].items()}
            out[k] = rr
        else:
            out[k] = r
    return out


def savant_league_rates(recs: dict, seasons) -> dict:
    """Pooled Statcast FRP per 1,277.7 innings by position (before centring)."""
    acc = defaultdict(lambda: [0.0, 0.0])
    for (m, t), r in recs.items():
        if t in seasons and r.get("sav"):
            for p, v in r["sav"].items():
                i = (r.get("inn") or {}).get(p, 0.0)
                if i > 0 and v is not None:
                    acc[p][0] += v
                    acc[p][1] += i
    return {p: (round(acc[p][0] / acc[p][1] * UNIT_INN, 2) if acc[p][1] else None) for p in OAA7}


class Rows3:
    """Row tables for one source: across-season (A, with the two earlier
    seasons the multi-season term reads) and Statcast same-season pairs (B)."""

    def __init__(self, src: str):
        self.src = src
        self.pos = L2.SOURCE_POS[src]
        self.A = None
        self.B = None
        self.S = None


def build_rows(records: dict) -> dict:
    """{src: Rows3}. Pass records with Statcast already centred."""
    out = {}
    for src in SOURCES:
        R = Rows3(src)
        P = len(R.pos)
        V = {}
        for key, rec in records.items():
            if (rec.get("p_inn") or 0.0) > L2.MAX_P_INN:
                continue
            v = L2.source_view(rec, src)
            if v is None:
                continue
            V[key] = (v[1], v[2], v[3] / v[2] * UNIT_INN)
        keys = sorted(V)
        R.S = {"m": np.array([k[0] for k in keys], dtype=np.int64),
               "t": np.array([k[1] for k in keys], dtype=np.int64),
               "S": np.array([V[k][0] for k in keys]).reshape(len(keys), P),
               "f": np.array([V[k][1] for k in keys]), "r": np.array([V[k][2] for k in keys]),
               "age": np.array([np.nan if records[k].get("age") is None else float(records[k]["age"])
                                for k in keys])}
        cols = defaultdict(list)
        for (m, t), (S1, f1, r1) in V.items():
            prev = V.get((m, t - 1))
            if prev is None:
                continue
            S0, f0, r0 = prev
            if f0 < L2.ACROSS_MIN_INN or f1 < L2.ACROSS_MIN_INN:
                continue
            age = records[(m, t - 1)].get("age")
            cols["m"].append(m)
            cols["t"].append(t)
            cols["r0"].append(r0)
            cols["r1"].append(r1)
            cols["S0"].append(S0)
            cols["S1"].append(S1)
            cols["w"].append(L2._hm(f0, f1) / 1000.0)
            cols["age"].append(np.nan if age is None else float(age))
            es, ei, er = [], [], []
            for j in (2, 3):
                e = V.get((m, t - j))
                if e is not None and e[1] >= EARLY_MIN_INN:
                    es.append(e[0])
                    ei.append(e[1])
                    er.append(e[2])
                else:
                    es.append(np.zeros(P))
                    ei.append(0.0)
                    er.append(0.0)
            cols["ES"].append(es)
            cols["Einn"].append(ei)
            cols["Er"].append(er)
        n = len(cols["m"])
        S0 = np.array(cols["S0"]).reshape(n, P)
        S1 = np.array(cols["S1"]).reshape(n, P)
        tvd = 0.5 * np.abs(S1 - S0).sum(axis=1) if n else np.zeros(0)
        ES = np.array(cols["ES"]).reshape(n, 2, P)
        Einn = np.array(cols["Einn"]).reshape(n, 2)
        Er = np.array(cols["Er"]).reshape(n, 2)
        den = Einn.sum(1)
        miss = den <= 0
        safe = np.where(miss, 1.0, den)
        R.A = {
            "m": np.array(cols["m"], dtype=np.int64), "t": np.array(cols["t"], dtype=np.int64),
            "r0": np.array(cols["r0"]), "r1": np.array(cols["r1"]), "S0": S0, "S1": S1,
            "w": np.array(cols["w"]), "age": np.array(cols["age"]),
            "switch": tvd >= L2.SWITCH_TVD, "tvd": tvd,
            "ES": ES, "Einn": Einn, "Er": Er,
            # every-position multi-season terms (the scoring's, gate part 4)
            "rbar": np.where(miss, 0.0, (Einn * Er).sum(1) / safe),
            "sbar": np.where(miss[:, None], 0.0, (Einn[:, :, None] * ES).sum(1) / safe[:, None]),
            "miss": miss.astype(float),
        }
        bm, bt, ba, bb, bra, brb, bw = [], [], [], [], [], [], []
        if src == "SAVANT":
            for (m, t), rec in records.items():
                sav = rec.get("sav")
                if not sav or (rec.get("p_inn") or 0.0) > L2.MAX_P_INN:
                    continue
                inn = rec.get("inn") or {}
                ok = [p for p in OAA7 if inn.get(p, 0.0) >= L2.WITHIN_MIN_INN
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
                        bw.append(L2._hm(inn[a], inn[b]) / 1000.0)
        R.B = {"m": np.array(bm, dtype=np.int64), "t": np.array(bt, dtype=np.int64),
               "a": np.array(ba, dtype=np.int64), "b": np.array(bb, dtype=np.int64),
               "ra": np.array(bra), "rb": np.array(brb), "w": np.array(bw)}
        out[src] = R
    return out


def mask_A(A, seasons, drop=None):
    """Across rows whose later season is in `seasons` and none of whose seasons
    t-3 to t is `drop` (gate part 4)."""
    mk = np.isin(A["t"], list(seasons))
    if drop is not None:
        for j in range(4):
            mk &= (A["t"] - j) != drop
    return mk


def mask_B(B, seasons, drop=None):
    mk = np.isin(B["t"], list(seasons))
    if drop is not None:
        mk &= B["t"] != drop
    return mk


# ============================================================ the group fit
def mask_S(S, seasons, drop=None):
    """Season rows in `seasons`, not `drop`."""
    mk = np.isin(S["t"], list(seasons))
    if drop is not None:
        mk &= S["t"] != drop
    return mk


def fit_group(R: Rows3, group: tuple, e9: dict, mS=None, mB=None, wmult=None):
    """Gate part 1 (a) as amended (A1): the within-group difficulty vector for
    one source from the player's own level over all his seasons in the group
    (a player fixed effect), an age term and his innings shares:
        r_{m,t} = a_m + beta (age_t - 27) + sum_p s_{t,p} D_p + e
    weighted by innings / 1,000 and solved by within-player demeaning, plus
    Statcast same-season pairs inside the group. Returns None when there is
    nothing to fit."""
    S, B = R.S, R.B
    gi = [R.pos.index(p) for p in group]
    g = len(gi)
    n_all = len(S["m"])
    if mS is None:
        mS = np.ones(n_all, dtype=bool)
    gs = S["S"][:, gi].sum(1) if n_all else np.zeros(0)
    sel = (mS & (S["f"] >= EARLY_MIN_INN) & (gs >= GROUP_MIN_SHARE) & ~np.isnan(S["age"]))
    w = S["f"][sel] / 1000.0
    if wmult is not None:
        w = w * wmult(S["m"][sel])
    idx = np.where(sel)[0][w > 0]
    w = w[w > 0]
    m = S["m"][idx]
    _u, inv, cnt = np.unique(m, return_inverse=True, return_counts=True)
    multi = cnt[inv] >= 2
    idx, w, m = idx[multi], w[multi], m[multi]
    _u, inv = np.unique(m, return_inverse=True)
    n_players = len(_u)
    Sh = S["S"][idx][:, gi] / gs[idx, None]
    r = S["r"][idx]
    age = S["age"][idx] - L2.AGE_CENTRE
    nA = len(w)
    if nA:
        Wp = np.bincount(inv, weights=w)

        def dm(x):
            return x - (np.bincount(inv, weights=w * x) / Wp)[inv]
        Xs = np.column_stack([dm(age)] + [dm(Sh[:, j]) for j in range(g)])
        yd = dm(r)
        # movers: players whose share at some group position ranges by 0.25
        # or more across their seasons in the fit
        hi = np.full((n_players, g), -np.inf)
        lo = np.full((n_players, g), np.inf)
        np.maximum.at(hi, inv, Sh)
        np.minimum.at(lo, inv, Sh)
        n_movers = int(((hi - lo).max(1) >= L2.SWITCH_TVD).sum())
    else:
        Xs = np.zeros((0, 1 + g))
        yd = np.zeros(0)
        n_movers = 0
    nB = 0
    XB = np.zeros((0, g))
    dyB = np.zeros(0)
    wB = np.zeros(0)
    if len(B["m"]):
        inG = np.isin(B["a"], gi) & np.isin(B["b"], gi)
        if mB is not None:
            inG &= mB
        wB = B["w"][inG].copy()
        if wmult is not None:
            wB = wB * wmult(B["m"][inG])
        kb = wB > 0
        a_ = B["a"][inG][kb]
        b_ = B["b"][inG][kb]
        dyB = (B["rb"][inG] - B["ra"][inG])[kb]
        wB = wB[kb]
        nB = len(wB)
        XB = np.zeros((nB, g))
        loc = {gidx: j for j, gidx in enumerate(gi)}
        for i in range(nB):
            XB[i, loc[int(b_[i])]] += 1.0
            XB[i, loc[int(a_[i])]] -= 1.0
    if nA + nB < 12:
        return None
    e = np.array([e9[p] for p in group])
    e = e / e.sum()
    sA, sB = np.sqrt(w), np.sqrt(wB)
    con = np.concatenate([[0.0], e])[None, :] * L2.CONSTRAINT_W
    XBk = np.hstack([np.zeros((nB, 1)), XB])
    X = np.vstack([Xs * sA[:, None], XBk * sB[:, None], con])
    y = np.concatenate([yd * sA, dyB * sB, [0.0]])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y[:-1] - X[:-1] @ beta
    dof = max(1, nA + nB - n_players - g)
    sigma2 = float(res @ res) / dof
    try:
        cov = sigma2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        cov = sigma2 * np.linalg.pinv(X.T @ X)
    return {
        "src": R.src, "group": list(group),
        "W": {p: float(-beta[1 + j]) for j, p in enumerate(group)},
        "var": {p: float(max(cov[1 + j, 1 + j], 1e-9)) for j, p in enumerate(group)},
        "beta_age": float(beta[0]),
        "n_seasons": int(nA), "n_players": int(n_players), "n_movers": int(n_movers),
        "n_within": int(nB),
    }


def pool_shapes(fits: dict, group: tuple, e9: dict):
    """Inverse-variance pool of the sources' group shapes, recentred to an
    exposure-weighted zero over the group. (W, var) or (None, None)."""
    W, V = {}, {}
    for p in group:
        num = den = 0.0
        for f in fits.values():
            if f and p in f["W"]:
                num += f["W"][p] / f["var"][p]
                den += 1.0 / f["var"][p]
        if den <= 0:
            return None, None
        W[p], V[p] = num / den, 1.0 / den
    e = np.array([e9[p] for p in group])
    e = e / e.sum()
    mu = float(sum(ei * W[p] for ei, p in zip(e, group)))
    return {p: W[p] - mu for p in group}, V


def regulars(records: dict) -> dict:
    """The anchor's rows (gate part 1 b), built once: regulars (400+ PA) with a
    primary position under ladder_v2.fit_offense's rule, unchanged."""
    m_, t_, p_, rate_, pa_ = [], [], [], [], []
    for (m, t), rec in records.items():
        pa = rec.get("pa") or 0
        rb = rec.get("runs_bat")
        if pa < L2.OFF_MIN_PA or rb is None:
            continue
        inn = rec.get("inn") or {}
        tot = sum(inn.get(p, 0.0) for p in FIELD)
        dh_g = rec.get("dh_g") or 0
        fld_g = rec.get("fld_g") or 0
        prim = None
        if dh_g + fld_g > 0 and dh_g / (dh_g + fld_g) >= L2.OFF_PRIMARY_SHARE:
            prim = "DH"
        elif tot > 0:
            p, v = max(((p, inn.get(p, 0.0)) for p in FIELD), key=lambda kv: kv[1])
            if v >= L2.OFF_PRIMARY_SHARE * tot:
                prim = p
        if prim is None:
            continue
        m_.append(m)
        t_.append(t)
        p_.append(LADDER9.index(prim))
        rate_.append(rb / pa * 650.0)
        pa_.append(float(pa))
    return {"m": np.array(m_, dtype=np.int64), "t": np.array(t_, dtype=np.int64),
            "p": np.array(p_, dtype=np.int64), "rate": np.array(rate_), "pa": np.array(pa_)}


def offense(reg: dict, seasons, e9: dict, wmult=None):
    """The anchor: -(O_p - grand) over LADDER9, recentred, where O_p is the
    PA-weighted mean batting runs per 650 PA of regulars whose primary is p
    (ladder_v2.fit_offense's numbers). wmult: per-player bootstrap counts.
    None when a position has no regulars."""
    mk = np.isin(reg["t"], list(seasons))
    w = reg["pa"][mk]
    if wmult is not None:
        w = w * wmult(reg["m"][mk])
    num = np.bincount(reg["p"][mk], weights=w * reg["rate"][mk], minlength=9)
    den = np.bincount(reg["p"][mk], weights=w, minlength=9)
    if (den <= 0).any():
        return None
    grand = num.sum() / den.sum()
    return L2.recentre({p: -(num[i] / den[i] - grand) for i, p in enumerate(LADDER9)}, e9)


def group_level(L: dict, group: tuple, e9: dict) -> float:
    e = np.array([e9[p] for p in group])
    e = e / e.sum()
    return float(sum(ei * L[p] for ei, p in zip(e, group)))


def carry_c(L8: dict, v1: dict, e9: dict) -> float:
    """Gate part 1 (d): C keeps v1's offset to v1's seven-position mean."""
    return L2.mean7(L8, e9) + (v1["C"] - L2.mean7(v1, e9))


def assemble(shapes: dict, off: dict, v1_for_c: dict, e9: dict, levels: bool = True) -> dict:
    """Gate part 1 (c) and (d). shapes {"IF": W, "OF": W}; off the offense
    ladder. levels=False gives the shapes-on-zero reference (every group level
    and 1B at 0, DH as the anchored ladder's)."""
    L = {}
    for gname, grp in GROUPS.items():
        lev = group_level(off, grp, e9) if levels else 0.0
        for p in grp:
            L[p] = shapes[gname][p] + lev
    L["1B"] = off["1B"] if levels else 0.0
    L["DH"] = off["DH"]
    L["C"] = 0.0
    L["C"] = carry_c(L, v1_for_c, e9)
    return L2.recentre(L, e9)


def fit_v3(rows: dict, reg: dict, e9: dict, v1_for_c: dict, seasons, drop=None,
           wmult=None, return_fits=False):
    """v3 on the given seasons (a row's later season), excluding `drop`."""
    fits = {g: {} for g in GROUPS}
    for s, R in rows.items():
        mS = mask_S(R.S, seasons, drop)
        mB = mask_B(R.B, seasons, drop)
        for gname, grp in GROUPS.items():
            fits[gname][s] = fit_group(R, grp, e9, mS, mB, wmult=wmult)
    shapes, svar = {}, {}
    for gname, grp in GROUPS.items():
        shapes[gname], svar[gname] = pool_shapes(fits[gname], grp, e9)
    off_seasons = set(seasons) - ({drop} if drop is not None else set())
    off = offense(reg, off_seasons, e9, wmult=wmult)
    info = {"fits": {g: {s: _fit_summary(f) for s, f in fs.items()} for g, fs in fits.items()},
            "shapes": {g: (None if W is None else {p: round(v, 4) for p, v in W.items()})
                       for g, W in shapes.items()},
            "offense": None if off is None else {p: round(v, 4) for p, v in off.items()}}
    if off is None or any(W is None for W in shapes.values()) or v1_for_c is None:
        info["error"] = "a group shape, the anchor or v1 for C is missing"
        return (None, None, info, fits) if return_fits else (None, None, info)
    L = assemble(shapes, off, v1_for_c, e9)
    S0 = assemble(shapes, off, v1_for_c, e9, levels=False)
    return (L, S0, info, fits) if return_fits else (L, S0, info)


def _fit_summary(f):
    if f is None:
        return None
    return {"W": {p: round(v, 4) for p, v in f["W"].items()},
            "se": {p: round(float(np.sqrt(v)), 4) for p, v in f["var"].items()},
            **{k: (round(f[k], 4) if isinstance(f[k], float) else f[k])
               for k in ("beta_age", "n_seasons", "n_players", "n_movers", "n_within")}}


# ================================================================== scoring
def score_rows(rows: dict, ladders: dict, t: int, train_seasons) -> tuple:
    """Held-out loss rows for season t: (primary, a2). Each a list of
    (mlbam, src, kind, w, {name: (abs, sq)}, t), as ladder_v2.score_rows."""
    out, out2 = [], []
    for s, R in rows.items():
        A = R.A
        P = R.pos
        trn = mask_A(A, train_seasons, drop=t)
        tst = (A["t"] == t) & A["switch"]
        if tst.any() and trn.sum() > 4:
            preds, preds2 = {}, {}
            w = A["w"][trn]
            sw = np.sqrt(w)
            for name, L in ladders.items():
                if L is None:
                    continue
                Lv = np.array([L[p] for p in P])
                y = A["r1"] + (A["S1"] - A["S0"]) @ Lv
                rstar = np.where(A["miss"] > 0, 0.0, A["rbar"] + (A["sbar"] - A["S0"]) @ Lv)
                X = np.vstack([np.ones(len(y)), A["r0"], rstar, A["miss"]]).T
                ab, *_ = np.linalg.lstsq(X[trn] * sw[:, None], y[trn] * sw, rcond=None)
                preds[name] = y[tst] - X[tst] @ ab
                X2 = X[:, :2]
                ab2, *_ = np.linalg.lstsq(X2[trn] * sw[:, None], y[trn] * sw, rcond=None)
                preds2[name] = y[tst] - X2[tst] @ ab2
            ms, ws = A["m"][tst], A["w"][tst]
            for i in range(len(ms)):
                out.append((int(ms[i]), s, "across", float(ws[i]),
                            {n: (abs(float(e[i])), float(e[i]) ** 2) for n, e in preds.items()}, t))
                out2.append((int(ms[i]), s, "across", float(ws[i]),
                             {n: (abs(float(e[i])), float(e[i]) ** 2) for n, e in preds2.items()}, t))
        B = R.B
        tb = B["t"] == t
        if tb.any():
            errs = {}
            for name, L in ladders.items():
                if L is None:
                    continue
                Lv = np.array([L[p] for p in OAA7])
                errs[name] = (B["rb"][tb] + Lv[B["b"][tb]]) - (B["ra"][tb] + Lv[B["a"][tb]])
            ms, ws = B["m"][tb], B["w"][tb]
            for i in range(len(ms)):
                row = (int(ms[i]), s, "within", float(ws[i]),
                       {n: (abs(float(e[i])), float(e[i]) ** 2) for n, e in errs.items()}, t)
                out.append(row)
                out2.append(row)
    return out, out2


# =============================================================== simulation
def simulate(recs: dict, e9: dict, seed: int, sel: float = 0.0, fam: float = 0.0):
    """Gate part 6, the verifier's t2 construction: real innings, ages and
    coverage, simulated fielding runs. Returns (sim records, G over FIELD
    (2016-2026 innings-weighted mean glove), planted q over LADDER9)."""
    rng = np.random.default_rng(seed)
    q = L2.fg_table_ladder(e9)
    car = defaultdict(lambda: defaultdict(float))
    for (m, t), r in sorted(recs.items()):
        for p, i in (r.get("inn") or {}).items():
            car[m][p] += i
    prim = {m: max(c, key=c.get) for m, c in car.items() if c}
    movers = {m for m, c in car.items() if m in prim
              and c[prim[m]] / max(sum(c.values()), 1e-9) < SIM_MOVER_SHARE}
    a = {m: q[prim[m]] + rng.normal(0, SIM_SD_GLOVE) for m in sorted(prim)}
    talent = {}
    for (m, t), r in sorted(recs.items()):
        if m not in a:
            continue
        age = r.get("age") if r.get("age") is not None else 27.0
        base = a[m] - SIM_AGE_SLOPE * (age - 27.0)
        tp = {}
        for p, i in sorted((r.get("inn") or {}).items()):
            x = base + rng.normal(0, SIM_SD_SEASON / np.sqrt(max(i, 50.0) / UNIT_INN))
            if fam and p != prim[m]:
                x -= fam
            if sel and m in movers:
                x -= sel
            tp[p] = x
        talent[(m, t)] = tp
    acc = defaultdict(lambda: [0.0, 0.0])
    for (m, t), tp in talent.items():
        for p, x in tp.items():
            i = recs[(m, t)]["inn"][p]
            acc[(p, t)][0] += i * x
            acc[(p, t)][1] += i
    Gs = defaultdict(float)
    Gw = defaultdict(float)
    for (m, t), tp in talent.items():
        if 2016 <= t <= 2026:
            for p, x in tp.items():
                i = recs[(m, t)]["inn"][p]
                Gs[p] += i * x
                Gw[p] += i
    G = {p: Gs[p] / Gw[p] for p in FIELD if Gw[p] > 0}
    sim = {}
    for key, r in recs.items():
        tp = talent.get(key)
        rr = dict(r)
        rr["runs"] = dict(r.get("runs") or {})
        if tp is None:
            sim[key] = rr
            continue
        t = key[1]
        pr = {p: (x - acc[(p, t)][0] / acc[(p, t)][1]) * r["inn"][p] / UNIT_INN
              for p, x in tp.items()}
        tot = sum(pr.values())
        for s in ("BREF", "FG"):
            if rr["runs"].get(s) is not None:
                rr["runs"][s] = tot + rng.normal(0, SIM_TOTAL_SD)
        if r.get("sav"):
            rr["sav"] = {p: pr[p] for p in r["sav"] if p in pr}
        sim[key] = rr
    return sim, G, q


def recovery(sim_recs: dict, G: dict, e9: dict, seasons) -> dict:
    """Part 1 (a) on simulated runs; the four within-group ratios."""
    rows = build_rows(centre_savant(sim_recs))
    out = {"ratios": {}, "recovered": {}, "target": {}}
    for gname, grp in GROUPS.items():
        fits = {s: fit_group(R, grp, e9, mask_S(R.S, seasons), mask_B(R.B, seasons))
                for s, R in rows.items()}
        W, _ = pool_shapes(fits, grp, e9)
        ref = GROUP_REF[gname]
        for p in grp:
            if p == ref:
                continue
            tgt = G[p] - G[ref]
            got = None if W is None else W[p] - W[ref]
            out["target"][p] = round(tgt, 3)
            out["recovered"][p] = None if got is None else round(got, 3)
            out["ratios"][p] = None if got is None or tgt == 0 else round(got / tgt, 4)
    return out


# ================================================================== helpers
def ladder_round(L, nd=4):
    return None if L is None else {p: round(float(L[p]), nd) for p in LADDER9}


def write_eval(record: dict) -> None:
    blob = json.dumps(record, indent=1)
    if chr(0x2014) in blob or chr(0x2013) in blob:
        raise SystemExit("refusing: a dash in the record")
    EVAL_PATH.write_text(blob + chr(10), encoding="utf-8")


if __name__ == "__main__":
    print("ladder_v3: the read is tools/ladder_v3_lab.py (--dry-run, then --read once)")
    sys.exit(0)
