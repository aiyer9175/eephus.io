# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV side and role calibration (EFV_SIDE_ROLE_CALIBRATION).

docs/efv-v2/EFV_SIDE_ROLE_CALIBRATION.md, registered alone before the read (owner decision
EW3-42, 2026-10-19: "I feel like pitchers are inflated across the board, especially relief
pitchers"). Inside a side the served eFV grade is the side's consensus multiset re-ordered, and
the value chain prices one side-pooled six-season WAR anchor at that grade
(value_framework.fv_to_6yr_avg_war), so a pitcher and a hitter at the same grade carry the
same expected WAR. This read asks, once and on the development frames only, whether the grade
means the same realized value on both sides and for every pitcher usage role, and tests two
calibrations of the grade to a common expected-value scale against the incumbent (no mapping):

    b: g' = F_pool^-1(F_side(g))          side-specific isotonic map
    c: g' = F_pool^-1(F_side,role(g))     side x pitcher usage role

F are isotonic (PAVA) fits of the realized label, put on the six-season anchor's scale by one
scalar kappa per (frame, fold), against the eFV grade (never consensus FV), cross-fitted by
leaving out one (frame, fold) and every player in it. The implied value of any map is
kappa x 6 x fv_to_6yr_avg_war(g'), so the anchor's level is read as it stands and never
re-fitted. Comparators: the incumbent (a), a side-permuted twin of b, a role-permuted twin of c;
planted recovery with a known side and role effect. Nothing is grouped by consensus-FV level;
the only groups are frame, fold, side, usage role and within-group grade quantiles.

    python efv_side_role_calibration.py --check --cache <re-fit cache> --x3-cache <X3 cache> --work <dir>
    python efv_side_role_calibration.py --run   --cache <re-fit cache> --x3-cache <X3 cache> --work <dir>
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

import efv_output_map as OM
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
OUT_PATH = LAB_DIR / "efv_side_role_calibration.json"
ROLES_PATH = DATA_DIR / "efv_pitcher_roles.json"
DOC = "docs/efv-v2/EFV_SIDE_ROLE_CALIBRATION.md"
TOOL = "efv_side_role_calibration.py"
ITEM = "EFV_SIDE_ROLE_CALIBRATION"
OWNER_DECISION = "EW3-42 (2026-10-19)"

# the dark switch of section 8; the read never sets it
SIDE_ROLE_CALIBRATION_ON = False

SEED = 20261020
B_MAIN = 2000
B_ECE = 1000
K_NULL = 200
K_PLANT = 100
B_PLANT = 500
N_BINS = 10
TOP_SHARE = 0.10
GUARD = -0.002
SIZE_MAX = 0.10
POWER_MIN = 0.80
N_ROLE_MIN = 60
X3_RELIEF_CUT = 0.5
PLANT_SIDE = {"hit": 1.15, "pit": 0.85}
PLANT_ROLE = {"RELIEF": 0.75}
GRID = np.round(np.arange(20.0, 80.0001, 0.1), 1)
TOP_N = 50

ROLES = ("STARTER", "SHORT-START", "RELIEF")
OTHER = "OTHER"
FRAMES = ("lv_dev", "vm_dev")
SIDES = ("hit", "pit")


# ---------------------------------------------------------------------------
# the isotonic fit and the grade map (section 4)
# ---------------------------------------------------------------------------

def pava(x, y) -> tuple[np.ndarray, np.ndarray]:
    """Increasing isotonic fit of y on x (rows weighted equally, tied x pooled first).
    Returns the blocks' (mean x, mean y), strictly increasing in both: adjacent blocks whose
    means are equal are merged, so the fit is invertible between its end blocks."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.size == 0:
        return np.zeros(0), np.zeros(0)
    ux, inv = np.unique(x, return_inverse=True)
    w = np.bincount(inv).astype(np.float64)
    sy = np.bincount(inv, weights=y)
    sx = ux * w
    bw, bsx, bsy = [], [], []
    for i in range(ux.size):
        bw.append(w[i])
        bsx.append(sx[i])
        bsy.append(sy[i])
        while len(bw) > 1 and bsy[-2] / bw[-2] >= bsy[-1] / bw[-1]:
            w2, x2, y2 = bw.pop(), bsx.pop(), bsy.pop()
            bw[-1] += w2
            bsx[-1] += x2
            bsy[-1] += y2
    bw = np.asarray(bw)
    return np.asarray(bsx) / bw, np.asarray(bsy) / bw


def f_eval(curve: tuple[np.ndarray, np.ndarray], g) -> np.ndarray:
    xs, ys = curve
    return np.interp(np.asarray(g, dtype=np.float64), xs, ys)


def inverse_project(curve: tuple[np.ndarray, np.ndarray], t, g) -> np.ndarray:
    """g' = the point of the preimage {x : F(x) = t} nearest to g. F is the piecewise-linear
    interpolation of strictly increasing blocks, flat beyond its end blocks; t outside F's range
    is clamped to it, so the preimage is (-inf, x_0] at the bottom, [x_n, +inf) at the top and a
    single point inside. Non-decreasing in g whenever t is non-decreasing in g."""
    xs, ys = curve
    t = np.clip(np.asarray(t, dtype=np.float64), ys[0], ys[-1])
    g = np.asarray(g, dtype=np.float64)
    if xs.size == 1:
        return g.copy()
    pt = np.interp(t, ys, xs)
    lo = np.where(t <= ys[0], -np.inf, pt)
    hi = np.where(t >= ys[-1], np.inf, pt)
    return np.clip(g, lo, hi)


def anchor_value(g) -> np.ndarray:
    """The incumbent instrument I(g): six times the served side-pooled anchor, read as it
    stands (value_framework.fv_to_6yr_avg_war, the level surplus reconciles to)."""
    g = np.asarray(g, dtype=np.float64)
    tab = _anchor_table()
    return np.interp(g, tab[0], tab[1])


_ANCHOR: tuple | None = None


def _anchor_table() -> tuple[np.ndarray, np.ndarray]:
    global _ANCHOR
    if _ANCHOR is None:
        import value_framework as vf
        xs = np.round(np.arange(15.0, 85.0001, 0.05), 2)
        _ANCHOR = (xs, np.asarray([6.0 * float(vf.fv_to_6yr_avg_war(float(x))) for x in xs]))
    return _ANCHOR


def pooled_curve_value(g) -> np.ndarray:
    """Sensitivity instrument: the pooled outcome curve the board basis inverts."""
    cur = OM.instruments()["pooled"]["hit"]
    return OM.t_eval(cur, g)


INSTRUMENTS = {"anchor": anchor_value, "pooled_curve": pooled_curve_value}
PRIMARY = "anchor"


# ---------------------------------------------------------------------------
# rows (section 3)
# ---------------------------------------------------------------------------

def role_of_usage(u: dict | None) -> str:
    r = (u or {}).get("role")
    return r if r in ROLES else OTHER


def dev_rows(pre: dict, *, log=print) -> list[dict]:
    """The scored rows of both development frames with the served grade (map A), the served
    order, the pitcher usage role at the read and the row's group keys."""
    import efv_reliever_adj as RA
    b1 = pre["b1"]
    inp = b1["inp"]
    book = RA.RoleBook()
    out = []
    for r in pre["rows"]:
        fold_id = r["fold_id"]
        yr = int(r["year"])
        if (r["fid"].startswith("lv") and yr in F.RESERVED_LV) or (
                r["fid"].startswith("vm") and yr >= F.R_VM_FIRST_DEBUT_YEAR):
            raise F.ReservedFrameError(f"{fold_id}: a reserved row reached the read")
        g = float(pre["grades"][fold_id]["A"][r["_i"]])
        o = float(pre["groups"][fold_id]["o"][r["_i"]])
        role = None
        if r["side"] == "pit":
            test = inp.frames[r["fid"]]["by_side"]["pit"][int(r["year"])]["test"][r["_i"]]
            if test["player_key"] != r["key"]:
                raise RuntimeError(f"{fold_id}: test row {r['_i']} is not {r['key']}")
            role = role_of_usage(book.usage_of(test, "test"))
        out.append(dict(r, g=g, o=o, role=role, kg=f"{r['fid']}|{r['year']}"))
    log(f"rows: {len(out)}")
    return out


def x3_role_path(x3_cache: Path, *, log=print) -> dict[tuple, float]:
    """{(frame, year, player_key): P(ends a reliever)} for every development pitcher test
    instance, from X3's role sub-model (EFV_X3_POOLED_MODEL section 6.5) refitted per outer
    fold exactly as its pipeline does (training: the fold's reached training pitchers)."""
    import __main__
    import efv_etools_reweight as ER
    import efv_x3_pooled as X3
    for cls in ("Bank", "RowMeta"):
        if not hasattr(__main__, cls):
            setattr(__main__, cls, getattr(ER, cls))
    _comp, _built, T, _inp, folds, ets, _g = X3.Run(Path(x3_cache), log=log).prep()
    want = ("gs_share", "ip_per_g", "workload", "arsenal_depth", "c_best_sec", "e_cmd", "e_fb")
    out = {}
    for fold in folds:
        test = fold["test"]
        tr = X3.training_sets(T, fold["Y"], set(T.pk[test].tolist()))
        fold_et = ets["values"][fold["id"]]
        raw = {}
        for f in want:
            if f in X3.ETOOL_OF:
                raw[f] = np.asarray(fold_et.get(X3.ETOOL_OF[f], np.full(T.n, np.nan)), dtype=np.float64)
            else:
                raw[f] = T.base[f]
        z = {f: (v if f in X3.BINARY else X3.z_within(v, T.zgroup)) for f, v in raw.items()}
        p_rel, _rec = X3.role_model(T, z, tr["C"])
        for i in test:
            if T.side[i] == 1 and np.isfinite(p_rel[i]):
                out[(fold["fid"], int(T.year[i]), str(T.pk[i]))] = float(p_rel[i])
    log(f"X3 role path: {len(out)} pitcher test instances")
    return out


def attach_x3(rows: list[dict], p_rel: dict[tuple, float]) -> int:
    n = 0
    for r in rows:
        if r["side"] != "pit":
            continue
        p = p_rel.get((r["fid"], int(r["year"]), r["key"]))
        r["p_rel"] = p
        r["x3_role"] = (None if p is None else ("RELIEF" if p >= X3_RELIEF_CUT else "STARTER"))
        n += p is not None
    return n


def counts(rows: list[dict]) -> dict:
    """Outcome-free row counts by frame, side and usage role."""
    out: dict = {}
    for f in FRAMES:
        sub = [r for r in rows if r["fid"] == f]
        blk = {"hit": sum(r["side"] == "hit" for r in sub), "pit": sum(r["side"] == "pit" for r in sub)}
        for role in ROLES + (OTHER,):
            blk[f"pit:{role}"] = sum(r["side"] == "pit" and r["role"] == role for r in sub)
        blk["pit:x3_joined"] = sum(r["side"] == "pit" and r.get("p_rel") is not None for r in sub)
        blk["pit:x3_relief_path"] = sum(r["side"] == "pit" and r.get("x3_role") == "RELIEF" for r in sub)
        out[f] = blk
    out["players"] = len({r["key"] for r in rows})
    out["groups"] = sorted({r["kg"] for r in rows})
    return out


# ---------------------------------------------------------------------------
# the candidates (section 4)
# ---------------------------------------------------------------------------

class Arrays:
    """The rows as arrays, for one label vector y (the real label or a planted one)."""

    def __init__(self, rows: list[dict], y: np.ndarray | None = None, *, instrument: str = PRIMARY):
        self.rows = rows
        self.n = len(rows)
        self.y = np.asarray([r["y"] for r in rows], dtype=np.float64) if y is None else np.asarray(y, float)
        self.g = np.asarray([r["g"] for r in rows], dtype=np.float64)
        self.o = np.asarray([r["o"] for r in rows], dtype=np.float64)
        self.side = np.asarray([r["side"] for r in rows], dtype=object)
        self.fid = np.asarray([r["fid"] for r in rows], dtype=object)
        self.kg = np.asarray([r["kg"] for r in rows], dtype=object)
        self.key = np.asarray([r["key"] for r in rows], dtype=object)
        self.role = np.asarray([r["role"] or "" for r in rows], dtype=object)
        self.x3_role = np.asarray([r.get("x3_role") or "" for r in rows], dtype=object)
        self.inst = INSTRUMENTS[instrument]
        self.I_g = self.inst(self.g)
        self.kappa = np.zeros(self.n)
        self.kappa_by: dict = {}
        for k in np.unique(self.kg):
            m = self.kg == k
            den = float(self.I_g[m].sum())
            kap = float(self.y[m].sum() / den) if den > 0 else 0.0
            self.kappa[m] = kap
            self.kappa_by[str(k)] = kap
        self.z = np.where(self.kappa > 0, self.y / np.where(self.kappa > 0, self.kappa, 1.0), 0.0)
        self.group_ix = {str(k): np.flatnonzero(self.kg == k) for k in np.unique(self.kg)}
        self.train_ix = {}
        for k, ix in self.group_ix.items():
            keys = set(self.key[ix].tolist())
            self.train_ix[k] = np.flatnonzero((self.kg != k) & ~np.isin(self.key, list(keys)))

    def value(self, g) -> np.ndarray:
        return self.kappa * self.inst(g)


def _fit(g, z) -> tuple[np.ndarray, np.ndarray] | None:
    if len(g) == 0:
        return None
    return pava(g, z)


def map_rows(A: Arrays, ix: np.ndarray, tr: np.ndarray, *, cand: str,
             side_lab: np.ndarray | None = None, role_lab: np.ndarray | None = None) -> np.ndarray:
    """g' of the rows ix from curves fitted on the rows tr (section 4)."""
    side_lab = A.side if side_lab is None else side_lab
    if role_lab is None:
        role_lab = A.x3_role if cand == "c_x3" else A.role
    pool = _fit(A.g[tr], A.z[tr])
    out = A.g[ix].copy()
    for s in SIDES:
        trs = tr[side_lab[tr] == s]
        ms = A.side[ix] == s
        if not ms.any():
            continue
        fs = _fit(A.g[trs], A.z[trs])
        t = f_eval(fs, A.g[ix][ms])
        if cand in ("c", "c_x3") and s == "pit":
            rl = role_lab
            for role in (ROLES if cand == "c" else ("STARTER", "RELIEF")):
                trr = trs[rl[trs] == role]
                mr = ms & (rl[ix] == role)
                if not mr.any() or trr.size < N_ROLE_MIN:
                    continue
                fr = _fit(A.g[trr], A.z[trr])
                sub = np.flatnonzero(ms)
                sel = rl[ix][sub] == role
                t[sel] = f_eval(fr, A.g[ix][sub][sel])
        out[ms] = inverse_project(pool, t, A.g[ix][ms])
    return out


def cross_fit(A: Arrays, cand: str, **kw) -> np.ndarray:
    """g' of every row, each (frame, fold) group mapped by curves fitted without it."""
    gp = A.g.copy()
    if cand == "a":
        return gp
    for k, ix in A.group_ix.items():
        gp[ix] = map_rows(A, ix, A.train_ix[k], cand=cand, **kw)
    return gp


def production_maps(A: Arrays) -> dict:
    """The calibration maps fitted on every development row, as grade-to-grade tables on
    GRID (section 8). No realized level is stored, only g -> g'."""
    allix = np.arange(A.n)
    pool = _fit(A.g, A.z)
    out = {"grid": GRID.tolist(), "b": {}, "c": {}}
    for s in SIDES:
        fs = _fit(A.g[A.side == s], A.z[A.side == s])
        out["b"][s] = np.round(inverse_project(pool, f_eval(fs, GRID), GRID), 3).tolist()
        out["c"][s] = out["b"][s]
    for role in ROLES:
        m = (A.side == "pit") & (A.role == role)
        if m.sum() < N_ROLE_MIN:
            out["c"][f"pit:{role}"] = out["b"]["pit"]
            continue
        fr = _fit(A.g[m], A.z[m])
        out["c"][f"pit:{role}"] = np.round(inverse_project(pool, f_eval(fr, GRID), GRID), 3).tolist()
    out["c"][f"pit:{OTHER}"] = out["b"]["pit"]
    out["n_rows"] = int(allix.size)
    return out


def apply_map(maps: dict, cand: str, side: str, role: str | None, g) -> np.ndarray:
    grid = np.asarray(maps["grid"], dtype=np.float64)
    if cand == "b" or side == "hit":
        tab = maps["b"][side]
    else:
        tab = maps["c"].get(f"pit:{role if role in ROLES else OTHER}", maps["b"]["pit"])
    return np.interp(np.asarray(g, dtype=np.float64), grid, np.asarray(tab, dtype=np.float64))


# ---------------------------------------------------------------------------
# statistics (section 5)
# ---------------------------------------------------------------------------

def frame_var(A: Arrays) -> np.ndarray:
    v = np.zeros(A.n)
    for f in FRAMES:
        m = A.fid == f
        if m.any():
            v[m] = float(A.y[m].var())
    return np.where(v > 0, v, 1.0)


def sq_err(A: Arrays, gp: np.ndarray, var: np.ndarray) -> np.ndarray:
    return (A.y - A.value(gp)) ** 2 / var


def ece(y, v, cell, sd, ix=None) -> float:
    """Row-weighted mean over (frame, side) cells of the cell's ECE: rows sorted by the
    implied value v, N_BINS equal-count groups, mean abs(mean y - mean v), in units of the
    frame's label SD."""
    if ix is None:
        ix = np.arange(len(y))
    y, v, cell, sd = y[ix], v[ix], cell[ix], sd[ix]
    tot, n = 0.0, 0
    for c in np.unique(cell):
        m = np.flatnonzero(cell == c)
        order = m[np.argsort(v[m], kind="mergesort")]
        for ch in np.array_split(order, N_BINS):
            if ch.size:
                tot += ch.size * abs(float(y[ch].mean() - v[ch].mean())) / float(sd[ch][0])
        n += m.size
    return tot / n if n else float("nan")


def ratio_stat(y, v, num_mask, den_mask, draws) -> dict:
    """R = (sum y / sum v) over num rows, divided by the same over den rows when den_mask is
    given; player-clustered CI95."""
    def r(ix):
        a = ix[num_mask[ix]]
        if a.size == 0 or v[a].sum() <= 0:
            return np.nan
        ra = y[a].sum() / v[a].sum()
        if den_mask is None:
            return ra
        b = ix[den_mask[ix]]
        if b.size == 0 or v[b].sum() <= 0 or y[b].sum() == 0:
            return np.nan
        return ra / (y[b].sum() / v[b].sum())
    full = r(np.arange(len(y)))
    arr = np.asarray([r(ix) for ix in draws])
    arr = arr[np.isfinite(arr)]
    q = np.quantile(arr, [0.025, 0.975]) if arr.size else [np.nan, np.nan]
    return {"value": None if not np.isfinite(full) else round(float(full), 4),
            "ci95": [round(float(q[0]), 4), round(float(q[1]), 4)],
            "rows": int(num_mask.sum())}


def top_mask(A: Arrays) -> np.ndarray:
    """Rows in the top TOP_SHARE of their (frame, fold, side) group by the served grade
    (ties by the served order); a quantile of the eFV grade inside the group."""
    m = np.zeros(A.n, dtype=bool)
    for k in np.unique(A.kg):
        for s in SIDES:
            ix = np.flatnonzero((A.kg == k) & (A.side == s))
            if ix.size == 0:
                continue
            nt = int(np.ceil(TOP_SHARE * ix.size))
            order = ix[np.lexsort((-A.o[ix], -A.g[ix]))]
            m[order[:nt]] = True
    return m


def within_guard(rows: list[dict], A: Arrays, gp: np.ndarray, *, B: int) -> dict:
    """Within (frame, side, year) Spearman of the map's ordering (g', ties by the served
    order) minus the served ordering's, per side and frame (statistic 5.4)."""
    import efv5_refit as RF
    BT, _B4 = OM._tools()
    base = OM._within_rows(rows, A.o)
    sc = OM.lex_score(gp, A.o)
    rr = [dict(b_, grades=dict(b_["grades"], _x=float(sc[j]))) for j, b_ in enumerate(base)]
    out = {}
    for s in SIDES:
        for f in ("both",) + FRAMES:
            sel = [rr[j] for j in range(A.n) if A.side[j] == s and (f == "both" or A.fid[j] == f)]
            if not sel:
                continue
            a = RF.within_of(sel, "_s")["within"]
            b = RF.within_of(sel, "_x")["within"]
            blk = {"served": None if a is None else round(a, 5), "map": None if b is None else round(b, 5),
                   "delta": None if (a is None or b is None) else round(b - a, 5)}
            if B and blk["delta"] not in (None, 0.0):
                d = BT.paired(sel, "_x", "_s", "within", B=B, seed=BT.SEED)
                blk["ci95"] = d.get("ci95")
            out[f"{s}|{f}"] = blk
    return out


def read_candidates(rows: list[dict], A: Arrays, maps_cf: dict[str, np.ndarray], *, B: int,
                    seed: int, log=print) -> dict:
    """Every statistic of section 5 on the real label for the incumbent and the candidates."""
    var = frame_var(A)
    sd = np.sqrt(var)
    cell = np.asarray([f"{f}|{s}" for f, s in zip(A.fid, A.side)], dtype=object)
    keys = A.key.tolist()
    draws = OM.boot_draws(keys, B=B, seed=seed)
    se = {c: sq_err(A, gp, var) for c, gp in maps_cf.items()}
    v = {c: A.value(gp) for c, gp in maps_cf.items()}
    pit = A.side == "pit"
    out: dict = {"n": int(A.n), "kappa": {k: round(x, 5) for k, x in A.kappa_by.items()},
                 "loss": {}, "deltas": {}, "ece": {}, "calibration_slope": {}}
    for c in maps_cf:
        out["loss"][c] = {f: round(float(se[c][(A.fid == f) if f != "both" else slice(None)].mean()), 5)
                          for f in ("both",) + FRAMES}
    pairs = [(c, "a") for c in maps_cf if c != "a"]
    if "c" in maps_cf and "b" in maps_cf:
        pairs.append(("c", "b"))
    if "c_x3" in maps_cf and "b" in maps_cf:
        pairs.append(("c_x3", "b"))
    for x, base in pairs:
        key = f"{x}_vs_{base}"
        blk = {}
        d = se[base] - se[x]
        blk["both"] = OM.paired_mean(d, draws)
        for f in FRAMES:
            m = A.fid == f
            blk[f] = {"delta": round(float(d[m].mean()), 5)}
        for s in SIDES:
            m = A.side == s
            blk[s] = {"delta": round(float(d[m].mean()), 5)}
        if base == "b":
            dp = d.copy()
            blk["pit_rows"] = _paired_masked(dp, pit, draws)
            for f in FRAMES:
                m = pit & (A.fid == f)
                blk[f"pit|{f}"] = {"delta": round(float(dp[m].mean()), 5)}
        out["deltas"][key] = blk
    # ECE (5.2)
    ece_full = {c: ece(A.y, v[c], cell, sd) for c in maps_cf}
    edraws = draws[:B_ECE]
    for c in maps_cf:
        out["ece"][c] = round(ece_full[c], 5)
    out["ece_delta"] = {}
    for x, base in pairs:
        arr = np.asarray([ece(A.y, v[base], cell, sd, ix) - ece(A.y, v[x], cell, sd, ix) for ix in edraws])
        q = np.quantile(arr, [0.025, 0.975])
        out["ece_delta"][f"{x}_vs_{base}"] = {"delta": round(ece_full[base] - ece_full[x], 5),
                                              "ci95": [round(float(q[0]), 5), round(float(q[1]), 5)],
                                              "B": int(len(edraws))}
    for c in maps_cf:
        out["calibration_slope"][c] = {s: OM.calib_slope(A.y[A.side == s], v[c][A.side == s],
                                                         _sub_draws(draws, A.side == s))
                                       for s in SIDES}
    out["_v"] = v
    return out


def _paired_masked(d: np.ndarray, mask: np.ndarray, draws: list[np.ndarray]) -> dict:
    arr = []
    for ix in draws:
        sub = ix[mask[ix]]
        if sub.size:
            arr.append(float(d[sub].mean()))
    arr = np.asarray(arr)
    q = np.quantile(arr, [0.025, 0.975])
    return {"delta": round(float(d[mask].mean()), 5), "ci95": [round(float(q[0]), 5), round(float(q[1]), 5)],
            "p_le_0": round(float((arr <= 0).mean()), 5), "n": int(mask.sum())}


def _sub_draws(draws: list[np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
    """Resamples restricted to the masked rows, re-indexed to the masked subset."""
    pos = np.full(mask.size, -1)
    pos[mask] = np.arange(int(mask.sum()))
    out = []
    for ix in draws:
        sub = pos[ix[mask[ix]]]
        if sub.size:
            out.append(sub)
    return out


def descriptives(A: Arrays, *, B: int, seed: int) -> dict:
    """Section 6 (reported, decides nothing): realized over implied by side, role and the
    top tenth of each group's grades, under the incumbent."""
    draws = OM.boot_draws(A.key.tolist(), B=B, seed=seed)
    v = A.value(A.g)
    hit, pit = A.side == "hit", A.side == "pit"
    top = top_mask(A)
    out: dict = {}
    for f in ("both",) + FRAMES:
        fm = np.ones(A.n, dtype=bool) if f == "both" else (A.fid == f)
        blk = {"hit": ratio_stat(A.y, v, hit & fm, None, draws),
               "pit": ratio_stat(A.y, v, pit & fm, None, draws),
               "pit_over_hit": ratio_stat(A.y, v, pit & fm, hit & fm, draws),
               "top_hit": ratio_stat(A.y, v, hit & fm & top, None, draws),
               "top_pit": ratio_stat(A.y, v, pit & fm & top, None, draws),
               "top_pit_over_top_hit": ratio_stat(A.y, v, pit & fm & top, hit & fm & top, draws),
               "rest_pit_over_rest_hit": ratio_stat(A.y, v, pit & fm & ~top, hit & fm & ~top, draws)}
        for role in ROLES + (OTHER,):
            rm = pit & fm & (A.role == role)
            blk[f"pit:{role}"] = ratio_stat(A.y, v, rm, None, draws)
            blk[f"pit:{role}_over_hit"] = ratio_stat(A.y, v, rm, hit & fm, draws)
            blk[f"pit:{role}_over_pit:STARTER"] = ratio_stat(A.y, v, rm, pit & fm & (A.role == "STARTER"), draws)
        for role in ("STARTER", "RELIEF"):
            rm = pit & fm & (A.x3_role == role)
            blk[f"x3:{role}_over_hit"] = ratio_stat(A.y, v, rm, hit & fm, draws)
        out[f] = blk
    return out


# ---------------------------------------------------------------------------
# comparators and planted recovery (section 5.5, 5.6)
# ---------------------------------------------------------------------------

def permuted_labels(A: Arrays, rng, *, what: str) -> np.ndarray:
    """Side labels (what="side") or pitcher role labels (what="role") shuffled within each
    (frame, fold) group; the curves are fitted on the shuffled labels, the rows they map keep
    their true labels."""
    lab = (A.side if what == "side" else A.role).copy()
    for ix in A.group_ix.values():
        sel = ix if what == "side" else ix[A.side[ix] == "pit"]
        if sel.size > 1:
            lab[sel] = lab[sel][rng.permutation(sel.size)]
    return lab


def null_comparators(A: Arrays, gp_b: np.ndarray, *, K: int, seed: int, log=print) -> dict:
    var = frame_var(A)
    se_a = sq_err(A, A.g, var)
    se_b = sq_err(A, gp_b, var)
    pit = A.side == "pit"
    side_d, role_d = [], []
    for k in range(int(K)):
        rng = np.random.default_rng(int(seed) + 1000 + k)
        sl = permuted_labels(A, rng, what="side")
        gp = np.empty(A.n)
        for g, ix in A.group_ix.items():
            gp[ix] = map_rows(A, ix, A.train_ix[g], cand="b", side_lab=sl)
        side_d.append(float((se_a - sq_err(A, gp, var)).mean()))
        rl = permuted_labels(A, rng, what="role")
        gq = np.empty(A.n)
        for g, ix in A.group_ix.items():
            gq[ix] = map_rows(A, ix, A.train_ix[g], cand="c", role_lab=rl)
        role_d.append(float((se_b - sq_err(A, gq, var))[pit].mean()))
    sd, rd = np.asarray(side_d), np.asarray(role_d)
    return {"K": int(K),
            "side_permuted_b_vs_a": {"p95": round(float(np.quantile(sd, 0.95)), 5),
                                     "mean": round(float(sd.mean()), 5), "max": round(float(sd.max()), 5)},
            "role_permuted_c_vs_b_pit_rows": {"p95": round(float(np.quantile(rd, 0.95)), 5),
                                              "mean": round(float(rd.mean()), 5),
                                              "max": round(float(rd.max()), 5)},
            "_side": sd, "_role": rd}


def planted(rows: list[dict], A0: Arrays, *, kind: str, effect: bool, K: int, B: int,
            seed: int) -> dict:
    """Section 5.6. y* = v_a x m + (y_pi - mean of y in the row's (frame, fold, side) group),
    pi a permutation inside the group; m = PLANT_SIDE by side (kind "side") or PLANT_ROLE on
    pitcher usage roles (kind "role"), or 1 everywhere (effect False). The whole pipeline
    (kappa, curves, maps) is rerun on y*. A hit is a CI95 lower bound above 0 of b against a
    (side) or of c against b on the pitcher rows (role)."""
    v_a = A0.value(A0.g)
    m = np.ones(A0.n)
    if effect:
        if kind == "side":
            for s, f in PLANT_SIDE.items():
                m[A0.side == s] = f
        else:
            for role, f in PLANT_ROLE.items():
                m[(A0.side == "pit") & (A0.role == role)] = f
    cells = {}
    for j in range(A0.n):
        cells.setdefault((A0.kg[j], A0.side[j]), []).append(j)
    cells = [np.asarray(ix) for ix in cells.values()]
    draws = OM.boot_draws(A0.key.tolist(), B=B, seed=seed)
    pit = A0.side == "pit"
    hits, deltas = 0, []
    for k in range(int(K)):
        rng = np.random.default_rng(int(seed) + k)
        noise = np.zeros(A0.n)
        for ix in cells:
            noise[ix] = A0.y[rng.permutation(ix)] - A0.y[ix].mean()
        ys = v_a * m + noise
        A = Arrays(rows, ys)
        var = frame_var(A)
        gb = cross_fit(A, "b")
        if kind == "side":
            d = sq_err(A, A.g, var) - sq_err(A, gb, var)
            lb = OM.lb_only(d, draws)
            deltas.append(float(d.mean()))
        else:
            gc = cross_fit(A, "c")
            d = sq_err(A, gb, var) - sq_err(A, gc, var)
            st = _paired_masked(d, pit, draws)
            lb = st["ci95"][0]
            deltas.append(st["delta"])
        hits += lb > 0
    return {"kind": kind, "effect": bool(effect), "share_lb_above_0": round(hits / float(K), 4),
            "mean_delta": round(float(np.mean(deltas)), 5), "K": int(K), "B": int(B), "seed": int(seed),
            "multipliers": (PLANT_SIDE if kind == "side" else PLANT_ROLE) if effect else "none"}


# ---------------------------------------------------------------------------
# the rule (section 7)
# ---------------------------------------------------------------------------

def rule(read: dict, read_sens: dict, guard: dict, nulls: dict, plants: dict) -> dict:
    d = read["deltas"]
    b = d["b_vs_a"]
    c = d["c_vs_a"]
    cb = d["c_vs_b"]
    def g_ok(cand, sides):
        return all(guard[cand].get(f"{s}|{f}", {}).get("delta") is not None
                   and guard[cand][f"{s}|{f}"]["delta"] >= GUARD
                   for s in sides for f in ("both",) + FRAMES)
    rb = {"B1_mse_lb_above_0": bool(b["both"]["ci95"][0] > 0),
          "B2_each_frame_not_below_0": all(b[f]["delta"] >= 0 for f in FRAMES),
          "B3_ece_not_worse": bool(read["ece_delta"]["b_vs_a"]["delta"] >= 0),
          "B4_rank_guard": g_ok("b", SIDES),
          "B5_above_side_permuted_p95": bool(b["both"]["delta"] > nulls["side_permuted_b_vs_a"]["p95"]),
          "B6_pooled_curve_instrument": bool(read_sens["deltas"]["b_vs_a"]["both"]["delta"] > 0),
          "B7_size": bool(plants["side_null"]["share_lb_above_0"] <= SIZE_MAX)}
    rc = {"C1_mse_lb_above_0": bool(c["both"]["ci95"][0] > 0),
          "C2_each_frame_not_below_0": all(c[f]["delta"] >= 0 for f in FRAMES),
          "C3_ece_not_worse": bool(read["ece_delta"]["c_vs_a"]["delta"] >= 0),
          "C4_pitcher_rank_guard": g_ok("c", ("pit",)),
          "C5_beats_b_on_pitchers_lb_above_0": bool(cb["pit_rows"]["ci95"][0] > 0),
          "C6_above_role_permuted_p95": bool(cb["pit_rows"]["delta"] > nulls["role_permuted_c_vs_b_pit_rows"]["p95"]),
          "C7_pooled_curve_instrument": bool(read_sens["deltas"]["c_vs_a"]["both"]["delta"] > 0),
          "C8_size": bool(plants["role_null"]["share_lb_above_0"] <= SIZE_MAX)}
    pb, pc = all(rb.values()), all(rc.values())
    pow_b = plants["side"]["share_lb_above_0"]
    pow_c = plants["role"]["share_lb_above_0"]
    word_b = "PASS" if pb else ("NULL" if pow_b >= POWER_MIN else "UNRESOLVED")
    word_c = "PASS" if pc else ("NULL" if pow_c >= POWER_MIN else "UNRESOLVED")
    prepared = "c" if pc else ("b" if pb else None)
    return {"b": {"checks": rb, "passes": pb, "reading": word_b, "power": pow_b},
            "c": {"checks": rc, "passes": pc, "reading": word_c, "power": pow_c},
            "prepared": prepared}


# ---------------------------------------------------------------------------
# the live board effect (section 8)
# ---------------------------------------------------------------------------

def _r(x, k=2):
    return None if x is None else round(float(x), k)


def board_effect(maps: dict) -> dict:
    """What each candidate's production map would do to the live board (decides nothing)."""
    import value_framework as vf
    board = OM.live_board()
    roles = json.loads(ROLES_PATH.read_text(encoding="utf-8")).get("players") or {}
    out: dict = {}
    for cand in ("b", "c"):
        blk = {}
        allg = []
        for side, b in board.items():
            keys, g, c = b["keys"], b["grade"], b["c"]
            role = [role_of_usage(roles.get(k)) if side == "pit" else None for k in keys]
            gp = np.asarray([float(apply_map(maps, cand, side, role[i], g[i])) for i in range(len(keys))])
            mv = gp - g
            order = np.lexsort((-b["o"], -g))
            top = order[:TOP_N]
            e = {"rows": len(keys), "mean_shift": _r(mv.mean(), 3), "mean_abs_shift": _r(np.abs(mv).mean(), 3),
                 "rows_moving_1_or_more": int((np.abs(mv) >= 1.0).sum()),
                 "rows_moving_3_or_more": int((np.abs(mv) >= 3.0).sum()),
                 "top50_mean_shift": _r(mv[top].mean(), 3),
                 "top50_mean_war6_served": _r(anchor_value(g[top]).mean(), 3),
                 "top50_mean_war6_calibrated": _r(anchor_value(gp[top]).mean(), 3),
                 "top50": [{"player_key": keys[i], "role": role[i], "consensus": _r(c[i], 1),
                            "efv": _r(g[i], 1), "calibrated": _r(gp[i], 1),
                            "war6_served": _r(anchor_value([g[i]])[0], 2),
                            "war6_calibrated": _r(anchor_value([gp[i]])[0], 2),
                            "surplus_mm_default_timing": _r(vf.surplus_value_mm(float(g[i]), side == "pit"), 1),
                            "surplus_mm_calibrated_default_timing": _r(vf.surplus_value_mm(float(gp[i]), side == "pit"), 1)}
                           for i in top]}
            if side == "pit":
                for rr in ROLES + (OTHER,):
                    m = np.asarray([x == rr for x in role])
                    if m.any():
                        e[f"role:{rr}"] = {"rows": int(m.sum()), "mean_shift": _r(mv[m].mean(), 3),
                                           "top_by_efv": _r(g[m].max(), 1)}
            blk[side] = e
            allg += [(float(gp[i]), float(g[i]), side) for i in range(len(keys))]
        top100_x = sorted(allg, key=lambda t: (-t[0], -t[1]))[:100]
        top100_a = sorted(allg, key=lambda t: -t[1])[:100]
        blk["joint_top100_pitchers"] = {"served": sum(t[2] == "pit" for t in top100_a),
                                        "calibrated": sum(t[2] == "pit" for t in top100_x)}
        out[cand] = blk
    # the map at the live side's own grade quantiles (the median row, the 90th and the 98th
    # percentile row of each side), never at a named grade value
    qs = (0.5, 0.9, 0.98)
    at = {}
    for cand in ("b", "c"):
        at[cand] = {}
        for lab, s, r in (("hit", "hit", None), ("pit", "pit", None), ("pit:STARTER", "pit", "STARTER"),
                          ("pit:SHORT-START", "pit", "SHORT-START"), ("pit:RELIEF", "pit", "RELIEF")):
            gq = np.quantile(board[s]["grade"], qs)
            at[cand][lab] = [{"quantile": q, "efv": _r(x, 1), "calibrated": _r(apply_map(maps, cand, s, r, [x])[0], 2)}
                             for q, x in zip(qs, gq)]
    out["grade_map_at_live_quantiles"] = at
    return out


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _save(work: Path, name: str, obj) -> None:
    work.mkdir(parents=True, exist_ok=True)
    with (work / f"{name}.pkl").open("wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)


def _load(work: Path, name: str):
    p = work / f"{name}.pkl"
    if p.exists():
        with p.open("rb") as fh:
            return pickle.load(fh)
    return None


def prepare(cache_dir: Path, x3_cache: Path | None, work: Path, *, log=print) -> dict:
    """Everything outcome-free: the cache and its checks (Q1, Q3, Q4 of the output map test,
    reused), the rows, the usage roles, the X3 role path and the counts."""
    pre = OM.prepare(cache_dir, log=log)
    rows = _load(work, "rows")
    if rows is None:
        rows = dev_rows(pre, log=log)
        p_rel = x3_role_path(x3_cache, log=log) if x3_cache else {}
        attach_x3(rows, p_rel)
        _save(work, "rows", rows)
    return {"pre": pre, "rows": rows, "counts": counts(rows)}


def run(cache_dir: Path, x3_cache: Path, work: Path, *, B: int = B_MAIN, log=print) -> dict:
    import efv5_refit as RF
    import efv_labels as L
    BT, _B4 = OM._tools()
    t0 = time.time()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    prep = prepare(cache_dir, x3_cache, work, log=log)
    pre, rows = prep["pre"], prep["rows"]
    q2 = OM.parity_q2(pre["packs"], pre["b1"], pre["fit"])
    log(f"Q2: published within reproduced ({q2})")
    A = Arrays(rows)
    maps_cf = {c: cross_fit(A, c) for c in ("a", "b", "c", "c_x3")}
    if not np.array_equal(maps_cf["a"], A.g):
        raise RuntimeError("the incumbent map moved a grade")
    read = read_candidates(rows, A, maps_cf, B=B, seed=SEED, log=log)
    As = Arrays(rows, instrument="pooled_curve")
    maps_s = {c: cross_fit(As, c) for c in ("a", "b", "c")}
    read_s = read_candidates(rows, As, maps_s, B=200, seed=SEED, log=log)
    log(f"b vs a {read['deltas']['b_vs_a']['both']}; c vs a {read['deltas']['c_vs_a']['both']}")
    guard = {c: within_guard(rows, A, maps_cf[c], B=(B if c in ("c", "c_x3") else 0))
             for c in ("b", "c", "c_x3")}
    nulls = _load(work, "nulls")
    if nulls is None:
        nulls = null_comparators(A, maps_cf["b"], K=K_NULL, seed=SEED, log=log)
        _save(work, "nulls", nulls)
    plants = {}
    for name, kind, eff in (("side", "side", True), ("side_null", "side", False),
                            ("role", "role", True), ("role_null", "role", False)):
        got = _load(work, f"plant_{name}")
        if got is None:
            got = planted(rows, A, kind=kind, effect=eff, K=K_PLANT, B=B_PLANT, seed=SEED + 7)
            _save(work, f"plant_{name}", got)
        plants[name] = got
        log(f"planted {name}: {got}")
    desc = descriptives(A, B=B, seed=SEED)
    verdict = rule(read, read_s, guard, nulls, plants)
    maps = production_maps(A)
    effect = board_effect(maps)
    for r_ in (read, read_s):
        r_.pop("_v", None)
    nulls = {k: v for k, v in nulls.items() if not k.startswith("_")}
    doc = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --run", "generated_at": BT._now(),
           "role": "development", "adjudicates": False, "doc": DOC, "owner_decision": OWNER_DECISION,
           "label": pre["fit"].get("label"), "source_fit": RF.FIT_PATH.relative_to(ROOT).as_posix(),
           "served_weights": pre["weights"],
           "constants": {"seed": SEED, "B": int(B), "B_ECE": B_ECE, "K_NULL": K_NULL, "K_PLANT": K_PLANT,
                         "B_PLANT": B_PLANT, "N_BINS": N_BINS, "TOP_SHARE": TOP_SHARE, "GUARD": GUARD,
                         "SIZE_MAX": SIZE_MAX, "POWER_MIN": POWER_MIN, "N_ROLE_MIN": N_ROLE_MIN,
                         "X3_RELIEF_CUT": X3_RELIEF_CUT, "PLANT_SIDE": PLANT_SIDE, "PLANT_ROLE": PLANT_ROLE},
           "checks": {"Q1_fold_receipts": pre["q1"], "Q2_published_within": q2,
                      "Q3_reserved": "no reserved fold", "Q4_live_board": pre["q4"]},
           "counts": prep["counts"],
           "instruments": {"anchor": "6 x value_framework.fv_to_6yr_avg_war (served, side-pooled)",
                           "pooled_curve": "data/fv_outcome_curves_pooled.json curve.value"},
           "read": read, "read_pooled_curve_instrument": read_s, "rank_guard": guard,
           "null_comparators": nulls, "planted": plants, "descriptives": desc,
           "rules": verdict, "production_maps": maps, "board_effect": effect,
           "elapsed_s": round(time.time() - t0, 1),
           "code": {"tool": TOOL, "commit": BT._commit(), "tool_sha256": BT._sha(ROOT / TOOL)}}
    BT.write_doc(doc, OUT_PATH)
    log(f"wrote {OUT_PATH}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="outcome-free checks and counts")
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="the re-fit's cache (packs_RT.pkl, build1.pkl)")
    ap.add_argument("--x3-cache", default=None, help="the X3 read's cache (role path)")
    ap.add_argument("--work", default=None, help="a scratch directory")
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    if not (a.cache and a.work):
        log("refused: --cache and --work are needed")
        return 2
    x3 = Path(a.x3_cache) if a.x3_cache else None
    if a.check:
        prep = prepare(Path(a.cache), x3, Path(a.work), log=log)
        out = {"q1": prep["pre"]["q1"], "q4": prep["pre"]["q4"], "counts": prep["counts"]}
        (Path(a.work) / "check.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        log(json.dumps(out, default=str))
        return 0
    if a.run:
        if OUT_PATH.exists():
            log(f"refused: {OUT_PATH} exists; the read runs once")
            return 2
        if x3 is None:
            log("refused: --x3-cache is needed for the run")
            return 2
        run(Path(a.cache), x3, Path(a.work), B=B_MAIN if a.B is None else int(a.B), log=log)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
