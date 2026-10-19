# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV hitter position calibration (EFV_HITTER_POSITION_CALIBRATION).

docs/efv-v2/EFV_HITTER_POSITION_CALIBRATION.md, registered alone before the read (owner
decisions EW3-47 and EW3-48, 2026-10-19). The follow-up of EFV_SIDE_ROLE_CALIBRATION on
hitters: at the same served eFV grade, does a hitter's realized value (the registered fWAR
label, which carries the positional adjustment) depend on the position he was LISTED at on
the grade date? Five groups, ex ante only:

    C | SS/CF | 2B/3B | LF/RF | 1B/DH     (a multi-position listing takes the most demanding)

The candidate is ONE partially pooled multiplicative group offset on the expected-value
scale: per group the realized over implied ratio R_j (implied = kappa x the served
six-season anchor at the grade), log R_j shrunk to the precision-weighted mean by an
empirical-Bayes (DerSimonian-Laird) between-group variance, never five free offsets. Within
each (frame, fold) group the offsets only re-allocate value (the group's realized sum is
kept), so the level is never re-fitted. Cross-fitted by leaving out one (frame, fold) and
every player in it. Comparators: zero adjustment (the null), a group-permuted twin and a
planted offset the fit must recover.

Amendment EW3-48: three AS-OF terms on top of the group offset, each tested against the
group-only model on the grade dates the MiLB fielding play-by-play covers (2021 and later):
MiLB fielding runs at the listed position up to the grade date (per 1,000 chances, shrunk to
the position mean by its reliability), positional versatility rebuilt from the same
play-by-play as of the grade date, and the listed-SS/CF x MFR interaction. data/
positions_played.json is never read (career-to-date); the season census is read only on the
outcome side (where a listed SS or CF later played), never as a frame input.

Nothing is grouped by consensus-FV level; the only groups are frame, fold and listed
position.

    python efv_hitter_position_calibration.py --check --cache <re-fit cache> --work <dir>
    python efv_hitter_position_calibration.py --run   --cache <re-fit cache> --work <dir>
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
import efv_side_role_calibration as SRC
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
OUT_PATH = LAB_DIR / "efv_hitter_position_calibration.json"
SEASON_CENSUS_PATH = DATA_DIR / "positions_played_seasons.json"
MFR_TABLES = ROOT / ".cache" / "milb_fielding" / "tables"
DOC = "docs/efv-v2/EFV_HITTER_POSITION_CALIBRATION.md"
TOOL = "efv_hitter_position_calibration.py"
ITEM = "EFV_HITTER_POSITION_CALIBRATION"
OWNER_DECISION = "EW3-47 and EW3-48 (2026-10-19)"

# the dark switch of section 9; the read never sets it
HITTER_POSITION_CALIBRATION_ON = False

SEED = 20261021
B_MAIN = 4000
B_MDE = 1000
K_NULL = 200
K_PLANT = 100
B_PLANT = 500
LB_Q = 0.05                    # the one-sided 95 percent lower bound
SIZE_MAX = 0.10
POWER_MIN = 0.80
RECOVER_TOL = 0.5              # recovered log effect within 50 percent of the planted one
R_FLOOR = 0.05
PLANT_GROUP = "SS/CF"
PLANT_MULT = 1.25
PLANT_BETA = 0.30
Z_MDE = 1.6449 + 0.8416        # one-sided 5 percent, 80 percent power
TERM_FIRST_YEAR = 2021
MIN_G = 10
MIN_GS = 5
GS_INN = 5.0                   # a game with 5 or more innings at the position counts as a start
QMLE_RIDGE = 1e-3
TOP_N = 50

GROUPS = ("C", "SS/CF", "2B/3B", "LF/RF", "1B/DH")
UNLISTED = "UNLISTED"
GENERIC_OF_CELL = "OF (generic listing)"
SPECTRUM = ("C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH")
GROUP_OF = {"C": "C", "SS": "SS/CF", "CF": "SS/CF", "2B": "2B/3B", "3B": "2B/3B",
            "LF": "LF/RF", "RF": "LF/RF", "1B": "1B/DH", "DH": "1B/DH"}
#: tokens that LIST each member (the player is listed at every one): most demanding wins
MULTI = {"MIF": ("SS", "2B"), "MI": ("SS", "2B"), "CI": ("3B", "1B")}
#: tokens that name SOME member of a set without saying which: resolved by the player's own
#: earlier specific listings, else the default
GENERIC = {"OF": ("CF", "LF", "RF"), "IF": ("SS", "2B", "3B", "1B"),
           "INF": ("SS", "2B", "3B", "1B"), "UT": ("SS", "2B", "3B", "1B", "CF", "LF", "RF"),
           "UTIL": ("SS", "2B", "3B", "1B", "CF", "LF", "RF")}
GENERIC_DEFAULT = {"OF": "LF", "IF": "2B", "INF": "2B", "UT": "2B", "UTIL": "2B"}
PITCHER_TOKENS = frozenset({"P", "RHP", "LHP", "SP", "RP"})
POS_NUM = {"C": 2, "1B": 3, "2B": 4, "3B": 5, "SS": 6, "LF": 7, "CF": 8, "RF": 9}
NUM_POS = {v: k for k, v in POS_NUM.items()}
PREMIUM = ("C", "SS", "CF")
SPORT_NAME = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "ROK"}
CHANCE_COLS = ("range_chances", "dp_opps", "arm_opps", "frame_n", "throw_n")
TERMS = ("mfr", "versatility", "sscf_x_mfr")
FRAMES = ("lv_dev", "vm_dev")


# ---------------------------------------------------------------------------
# the listed position at the grade date (section 3)
# ---------------------------------------------------------------------------

def tokens(pos) -> list[str]:
    s = str(pos or "").upper().replace("-", "/").replace(",", "/").replace(" ", "/")
    return [t for t in (x.strip() for x in s.split("/")) if t and t not in PITCHER_TOKENS]


def _most_demanding(cands) -> str | None:
    c = [t for t in cands if t in SPECTRUM]
    return min(c, key=SPECTRUM.index) if c else None


def resolve_listing(listed: list, history: list | None = None) -> dict:
    """The listed position of one row: `listed` the position strings of each source's as-of
    entry, `history` every earlier listing string of the player (dated on or before the grade
    date). Specific tokens (and MIF, MI, CI, which list each member) take the most demanding;
    a generic token alone (OF, IF, INF, UT, UTIL) is resolved by the most demanding specific
    token of its set in the player's own earlier listings, else its default."""
    toks = [t for p in listed for t in tokens(p)]
    spec = [t for t in toks if t in SPECTRUM]
    for t in toks:
        spec += list(MULTI.get(t, ()))
    best = _most_demanding(spec)
    if best:
        return {"group": GROUP_OF[best], "token": best, "how": "listed"}
    gen = [t for t in toks if t in GENERIC]
    if not gen:
        return {"group": UNLISTED, "token": None, "how": "unlisted"}
    members = set()
    for t in gen:
        members |= set(GENERIC[t])
    old = [t for p in (history or ()) for t in tokens(p)]
    old += [m for t in old for m in MULTI.get(t, ())]
    hit = _most_demanding([t for t in old if t in members])
    if hit:
        return {"group": GROUP_OF[hit], "token": hit, "how": "generic_by_history"}
    tok = GENERIC_DEFAULT[gen[0]]
    return {"group": GROUP_OF[tok], "token": tok, "how": "generic_default"}


def _asof_point(r: dict, U: dict, recs: dict) -> tuple[str | None, str | None, dict]:
    """(as-of date, org, record): the latest points[] entry inside the row's grade window
    (lv_dev: efv_vintage_frame.window_bounds, as frame_row reads it; vm_dev: the preseason
    window efv_dataset.preseason_consensus_asof reads)."""
    import efv_dataset as D
    if r["fid"] == "lv_dev":
        rec = U.get(r["key"]) or {}
        lo, hi = F.window_bounds(int(r["year"]), D.debut_day_for_cutoff(rec)[0])
    else:
        rec = recs.get(r["key"]) or U.get(r["key"]) or {}
        lo, hi = D.preseason_window(int(r["year"]))
    pts = [p for p in (rec.get("points") or [])
           if p.get("snapshot_date") and lo <= str(p["snapshot_date"])[:10] < hi]
    if not pts:
        return None, None, rec
    pt = sorted(pts, key=lambda p: str(p["snapshot_date"]))[-1]
    return str(pt["snapshot_date"])[:10], pt.get("org"), rec


def hitter_rows(pre: dict, *, log=print) -> list[dict]:
    """The hitter rows of both development frames with the served grade (map A), the served
    order, the as-of date, the club at the grade date and the listed position."""
    import efv_dataset as D
    import efv_w2_scout as W
    import trades
    U = F.load_universe()
    recs = D.asof_records()
    idx = W.default_index()
    out = []
    for r in pre["rows"]:
        if r["side"] != "hit":
            continue
        yr = int(r["year"])
        if (r["fid"].startswith("lv") and yr in F.RESERVED_LV) or (
                r["fid"].startswith("vm") and yr >= F.R_VM_FIRST_DEBUT_YEAR):
            raise F.ReservedFrameError(f"{r['fold_id']}: a reserved row reached the read")
        g = float(pre["grades"][r["fold_id"]]["A"][r["_i"]])
        o = float(pre["groups"][r["fold_id"]]["o"][r["_i"]])
        asof, org, rec = _asof_point(r, U, recs)
        ent = idx.asof(r["key"], asof) if asof else {}
        listed = [e[5] for e in ent.values()]
        hist = [e[5] for e in (idx.by_key.get(r["key"]) or ()) if asof and e[0] <= asof]
        lst = resolve_listing(listed, hist)
        club = trades.canonical_org(org) if org else None
        mid = rec.get("mlbam_id")
        try:
            mid = int(mid) if mid else None
        except (TypeError, ValueError):
            mid = None
        out.append({"key": r["key"], "fid": r["fid"], "year": yr, "fold_id": r["fold_id"],
                    "kg": f"{r['fid']}|{yr}", "y": float(r["y"]), "g": g, "o": o,
                    "asof": asof, "club": club or f"?{r['key']}", "club_known": bool(club),
                    "group": lst["group"], "token": lst["token"], "how": lst["how"],
                    "mlbam": mid})
    log(f"hitter rows: {len(out)}")
    return out


# ---------------------------------------------------------------------------
# the as-of fielding terms (section 5)
# ---------------------------------------------------------------------------

def load_mfr():
    """The MFR build's game rows with their dates, the level factors F_L and the position
    reliability constants k (innings), read as the gate's build wrote them."""
    import pandas as pd
    meta = json.loads((MFR_TABLES / "build_meta.json").read_text(encoding="utf-8"))
    gr = pd.read_parquet(MFR_TABLES / "game_rows.parquet",
                         columns=["sport", "season", "gidx", "pid", "pos", "inn", "runs", *CHANCE_COLS])
    games = pd.read_parquet(MFR_TABLES / "games.parquet", columns=["gidx", "date"])
    gr = gr.merge(games, on="gidx", how="left")
    by_name = {v: k for k, v in SPORT_NAME.items()}
    FL = {by_name[n]: float(f) for n, f in meta["levels"]["F"].items()}
    gr["fr"] = gr.runs * gr.sport.map(FL).astype(float)
    gr["ch"] = gr[list(CHANCE_COLS)].sum(axis=1)
    k_inn = {int(p): float(v["k"]) for p, v in meta["k"].items()}
    return {"gr": gr, "FL": FL, "k_inn": k_inn, "meta_levels": meta["levels"]}


def mfr_scale(M: dict, year: int) -> dict[int, dict]:
    """Per position: chances per inning and the SD of the shrunk rate over the MiLB
    population (player x position aggregates, 200 or more innings) from the seasons before
    `year` only."""
    gr = M["gr"]
    pop = gr[gr.season < int(year)]
    out = {}
    if not len(pop):
        return out
    agg = pop.groupby(["pid", "pos"], as_index=False)[["fr", "ch", "inn"]].sum()
    for p, k in M["k_inn"].items():
        a = agg[agg.pos == p]
        if not len(a) or float(a.inn.sum()) <= 0:
            continue
        cpi = float(a.ch.sum() / a.inn.sum())
        k_ch = k * cpi
        q = a[a.inn >= 200.0]
        rate = 1000.0 * q.fr / (q.ch + k_ch)
        sd = float(rate.std(ddof=1)) if len(q) > 2 else float("nan")
        out[p] = {"chances_per_inning": cpi, "k_chances": k_ch, "sd": sd, "n_pop": int(len(q))}
    return out


def asof_terms(rows: list[dict], M: dict, *, log=print) -> dict:
    """The raw as-of term values of the rows whose grade date is TERM_FIRST_YEAR or later:
    {i: {"mfr_rate", "mfr_z", "mfr_chances", "n_pos", "prem_share", "games"}} from the MiLB
    play-by-play game rows dated before the row's grade date."""
    gr = M["gr"]
    scales: dict = {}
    out = {}
    for i, r in enumerate(rows):
        if r["year"] < TERM_FIRST_YEAR:
            continue
        blk = {"mfr_rate": None, "mfr_z": None, "mfr_chances": 0.0, "n_pos": None,
               "prem_share": None, "games": 0}
        if r["mlbam"] and r["asof"]:
            sub = gr[(gr.pid == r["mlbam"]) & (gr.date < r["asof"])]
            if len(sub):
                pg = sub.groupby("pos").agg(g=("gidx", "nunique"))
                gs = sub[sub.inn >= GS_INN].groupby("pos").gidx.nunique()
                qual = [p for p in pg.index if (int(pg.loc[p, "g"]) >= MIN_G or int(gs.get(p, 0)) >= MIN_GS)
                        and p in NUM_POS]
                tot = int(pg.g.sum())
                blk["games"] = tot
                blk["n_pos"] = int(len(qual))
                prem = int(sum(int(pg.loc[POS_NUM[p], "g"]) for p in PREMIUM if POS_NUM[p] in pg.index))
                blk["prem_share"] = prem / tot if tot else None
                p = POS_NUM.get(r["token"] or "")
                if p is not None:
                    if r["year"] not in scales:
                        scales[r["year"]] = mfr_scale(M, r["year"])
                    sc = scales[r["year"]].get(p)
                    at = sub[sub.pos == p]
                    if sc is not None:
                        ch = float(at.ch.sum())
                        rate = 1000.0 * float(at.fr.sum()) / (ch + sc["k_chances"])
                        blk["mfr_rate"] = rate
                        blk["mfr_chances"] = ch
                        blk["mfr_z"] = rate / sc["sd"] if sc["sd"] and np.isfinite(sc["sd"]) else 0.0
        out[i] = blk
    log(f"as-of terms: {len(out)} rows with a grade date in {TERM_FIRST_YEAR} or later")
    return {"by_row": out, "scales": {str(y): {NUM_POS[p]: v for p, v in s.items()} for y, s in scales.items()}}


def term_matrix(rows: list[dict], terms: dict, term: str, ix: np.ndarray) -> np.ndarray:
    """Raw columns of one term on the rows ix (missing values as NaN): mfr -> [mfr_z];
    versatility -> [n_pos, prem_share]; sscf_x_mfr -> [1(listed SS/CF) x mfr_z]."""
    cols = []
    for i in ix:
        b = terms["by_row"].get(int(i)) or {}
        z = b.get("mfr_z")
        if term == "mfr":
            cols.append([np.nan if z is None else z])
        elif term == "versatility":
            cols.append([np.nan if b.get("n_pos") is None else b["n_pos"],
                         np.nan if b.get("prem_share") is None else b["prem_share"]])
        else:
            s = 1.0 if rows[int(i)]["group"] == "SS/CF" else 0.0
            cols.append([np.nan if z is None else s * z])
    return np.asarray(cols, dtype=np.float64).reshape(len(ix), -1)


def standardize(X: np.ndarray, fit_rows: np.ndarray, *, term: str) -> np.ndarray:
    """MFR columns are already on the position's SD scale with 0 at the position mean (a
    missing value is the position mean, 0). Versatility columns are centred and scaled on
    the fitting rows, a missing value set to the fitting rows' mean (0)."""
    X = X.copy()
    if term in ("mfr", "sscf_x_mfr"):
        return np.nan_to_num(X, nan=0.0)
    for j in range(X.shape[1]):
        col = X[fit_rows, j]
        col = col[np.isfinite(col)]
        mu = float(col.mean()) if col.size else 0.0
        sd = float(col.std(ddof=1)) if col.size > 2 else 1.0
        sd = sd if sd > 0 else 1.0
        X[:, j] = np.where(np.isfinite(X[:, j]), (X[:, j] - mu) / sd, 0.0)
    return X


# ---------------------------------------------------------------------------
# arrays, the group offset and its cross-fit (section 4)
# ---------------------------------------------------------------------------

class Arrays:
    """The hitter rows as arrays for one label vector y."""

    def __init__(self, rows: list[dict], y: np.ndarray | None = None, *, groups: tuple = GROUPS,
                 group_key: str = "group"):
        self.rows = rows
        self.groups = tuple(groups)
        self.n = len(rows)
        self.y = np.asarray([r["y"] for r in rows], dtype=np.float64) if y is None else np.asarray(y, float)
        self.g = np.asarray([r["g"] for r in rows], dtype=np.float64)
        self.o = np.asarray([r["o"] for r in rows], dtype=np.float64)
        self.fid = np.asarray([r["fid"] for r in rows], dtype=object)
        self.kg = np.asarray([r["kg"] for r in rows], dtype=object)
        self.key = np.asarray([r["key"] for r in rows], dtype=object)
        self.club = np.asarray([r["club"] for r in rows], dtype=object)
        self.year = np.asarray([r["year"] for r in rows], dtype=np.int64)
        gi = {g: j for j, g in enumerate(self.groups)}
        self.grp = np.asarray([gi.get(r[group_key], -1) for r in rows], dtype=np.int64)
        self.I = SRC.anchor_value(self.g)
        self.group_ix = {str(k): np.flatnonzero(self.kg == k) for k in np.unique(self.kg)}
        self.train_ix = {}
        for k, ix in self.group_ix.items():
            keys = set(self.key[ix].tolist())
            self.train_ix[k] = np.flatnonzero((self.kg != k) & ~np.isin(self.key, list(keys)))
        self.v_a = self.renorm(np.ones(self.n))
        var = np.ones(self.n)
        for f in FRAMES:
            m = self.fid == f
            if m.any():
                var[m] = float(self.y[m].var()) or 1.0
        self.var = var

    def renorm(self, factor: np.ndarray, ix: np.ndarray | None = None) -> np.ndarray:
        """Implied value with a per-row factor: inside each (frame, fold) group the realized
        sum is kept, v_i = (sum y) x I_i f_i / sum (I f). With factor 1 this is the incumbent
        kappa x I."""
        out = np.zeros(self.n)
        groups = self.group_ix.items() if ix is None else [
            (k, np.intersect1d(gx, ix)) for k, gx in self.group_ix.items()]
        for _k, gx in groups:
            if gx.size == 0:
                continue
            w = self.I[gx] * factor[gx]
            den = float(w.sum())
            out[gx] = float(self.y[gx].sum()) * w / den if den > 0 else 0.0
        return out

    def sq_err(self, v: np.ndarray) -> np.ndarray:
        return (self.y - v) ** 2 / self.var


def group_fit(y, v, grp, key, k: int = len(GROUPS)) -> dict:
    """The partially pooled offset: per group R_j = sum y / sum v, theta_j = log R_j with its
    player-clustered delta-method variance s2_j; tau2 by DerSimonian-Laird over the groups;
    theta*_j = theta_bar + tau2 / (tau2 + s2_j) (theta_j - theta_bar)."""
    th = np.zeros(k)
    s2 = np.full(k, np.inf)
    R = np.full(k, np.nan)
    n = np.zeros(k, dtype=np.int64)
    for j in range(k):
        m = grp == j
        n[j] = int(m.sum())
        if n[j] < 2:
            continue
        Y, V = float(y[m].sum()), float(v[m].sum())
        if V <= 0:
            continue
        r = max(Y / V, R_FLOOR)
        e = y[m] - r * v[m]
        _u, inv = np.unique(key[m], return_inverse=True)
        ep = np.bincount(inv, weights=e)
        var_r = float((ep ** 2).sum()) / V ** 2
        R[j] = Y / V
        th[j] = np.log(r)
        s2[j] = max(var_r / r ** 2, 1e-8)
    ok = np.isfinite(s2)
    if ok.sum() < 2:
        return {"theta": th, "s2": s2, "R": R, "n": n, "theta_bar": 0.0, "tau2": 0.0, "Q": 0.0,
                "shrink": np.zeros(k), "theta_star": np.zeros(k)}
    w = 1.0 / s2[ok]
    tb = float((w * th[ok]).sum() / w.sum())
    Q = float((w * (th[ok] - tb) ** 2).sum())
    c = float(w.sum() - (w ** 2).sum() / w.sum())
    tau2 = max(0.0, (Q - (ok.sum() - 1)) / c) if c > 0 else 0.0
    shrink = np.where(ok, tau2 / (tau2 + np.where(ok, s2, 1.0)), 0.0)
    ths = np.where(ok, tb + shrink * (th - tb), tb)
    return {"theta": th, "s2": s2, "R": R, "n": n, "theta_bar": tb, "tau2": tau2, "Q": Q,
            "shrink": shrink, "theta_star": ths}


def factor_of(fit: dict, grp: np.ndarray) -> np.ndarray:
    th = np.where(grp >= 0, fit["theta_star"][np.clip(grp, 0, None)], fit["theta_bar"])
    return np.exp(th)


def cross_fit_group(A: Arrays, *, grp_fit: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """The group-only correction's implied value of every row, each (frame, fold) group from
    offsets fitted without it and without its players; grp_fit (a permuted labelling) is
    used for the fit only, the mapped rows keep their own listed group."""
    gf = A.grp if grp_fit is None else grp_fit
    factor = np.ones(A.n)
    fits = {}
    for k, ix in A.group_ix.items():
        tr = A.train_ix[k]
        fit = group_fit(A.y[tr], A.v_a[tr], gf[tr], A.key[tr], len(A.groups))
        factor[ix] = factor_of(fit, A.grp[ix])
        fits[k] = fit
    return A.renorm(factor), fits


# ---------------------------------------------------------------------------
# the two-way clustered bootstrap (section 6)
# ---------------------------------------------------------------------------

def twoway_weights(players, clubs, *, B: int, seed: int) -> np.ndarray:
    """B x n pigeonhole weights: players and clubs are resampled independently with
    replacement and each row weighs (its player's count) x (its club's count)."""
    rng = np.random.default_rng(int(seed))
    _pu, pi = np.unique(np.asarray(players, dtype=object).astype(str), return_inverse=True)
    _cu, ci = np.unique(np.asarray(clubs, dtype=object).astype(str), return_inverse=True)
    npl, ncl = int(pi.max()) + 1, int(ci.max()) + 1
    W = np.empty((int(B), pi.size), dtype=np.float32)
    for b in range(int(B)):
        mp = rng.multinomial(npl, np.full(npl, 1.0 / npl))
        mc = rng.multinomial(ncl, np.full(ncl, 1.0 / ncl))
        W[b] = mp[pi] * mc[ci]
    return W


def wmean_draws(d: np.ndarray, W: np.ndarray) -> np.ndarray:
    s = W.sum(axis=1)
    ok = s > 0
    return (W[ok] @ np.asarray(d, dtype=np.float64)) / s[ok]


def paired(d: np.ndarray, W: np.ndarray) -> dict:
    arr = wmean_draws(d, W)
    return {"delta": round(float(np.mean(d)), 5),
            "lb95_one_sided": round(float(np.quantile(arr, LB_Q)), 5),
            "ci90": [round(float(np.quantile(arr, LB_Q)), 5), round(float(np.quantile(arr, 1 - LB_Q)), 5)],
            "p_le_0": round(float((arr <= 0).mean()), 5), "n": int(np.size(d)), "B_used": int(arr.size)}


def ratio_ci(y, v, num, den, W) -> dict:
    """(sum y / sum v) over num rows, over the same on den rows when den is given; two-way
    clustered 90 and 95 percent intervals."""
    def r(w):
        a = (w * num).astype(np.float64)
        va = float(a @ v)
        if va <= 0:
            return np.nan
        ra = float(a @ y) / va
        if den is None:
            return ra
        b = (w * den).astype(np.float64)
        vb, yb = float(b @ v), float(b @ y)
        if vb <= 0 or yb == 0:
            return np.nan
        return ra / (yb / vb)
    full = r(np.ones(len(y)))
    arr = np.asarray([r(w) for w in W])
    arr = arr[np.isfinite(arr)]
    q = np.quantile(arr, [0.025, 0.975]) if arr.size else [np.nan, np.nan]
    return {"value": None if not np.isfinite(full) else round(float(full), 4),
            "ci95": [round(float(q[0]), 4), round(float(q[1]), 4)], "rows": int(np.sum(num))}


# ---------------------------------------------------------------------------
# the terms against the group-only model (section 5)
# ---------------------------------------------------------------------------

def qmle(y, off, X) -> np.ndarray:
    """Poisson quasi-likelihood slope(s) of y on X with the log offset off (Newton, a tiny
    ridge; the score is sum x (y - mu), valid for a label that can be negative)."""
    p = X.shape[1]
    b = np.zeros(p)
    for _ in range(100):
        eta = np.clip(off + X @ b, -30.0, 30.0)
        mu = np.exp(eta)
        gr = X.T @ (y - mu) - QMLE_RIDGE * b
        H = X.T @ (X * mu[:, None]) + QMLE_RIDGE * np.eye(p)
        try:
            step = np.linalg.solve(H, gr)
        except np.linalg.LinAlgError:
            break
        b = np.clip(b + step, -5.0, 5.0)
        if float(np.max(np.abs(step))) < 1e-10:
            break
    return b


def term_rows(A: Arrays) -> np.ndarray:
    return np.flatnonzero(A.year >= TERM_FIRST_YEAR)


def cross_fit_term(A: Arrays, rows: list[dict], terms: dict, term: str, *,
                   fits: dict, x_perm: np.ndarray | None = None) -> dict:
    """The term model on the term frame: for each held-out (frame, fold) group k with a
    grade date in TERM_FIRST_YEAR or later, the base is the group offset fitted without k
    (fits[k]) re-allocated inside every term group; beta is the QMLE of the term on the
    other term groups' rows (k's players excluded) with the log base as offset; k's rows get
    base x exp(x beta), re-allocated inside k. Returns the base and term values on the term
    rows and the per-fold betas."""
    T = term_rows(A)
    kgs = sorted({str(k) for k in A.kg[T]})
    v_base = np.zeros(A.n)
    v_term = np.zeros(A.n)
    betas = {}
    Xraw = term_matrix(rows, terms, term, np.arange(A.n))
    for k in kgs:
        fk = factor_of(fits[k], A.grp)
        vb = A.renorm(fk, T)
        ix = A.group_ix[k]
        kk = set(A.key[ix].tolist())
        tr = np.asarray([i for i in T if A.kg[i] != k and A.key[i] not in kk], dtype=np.int64)
        X = standardize(Xraw if x_perm is None else Xraw[x_perm], tr, term=term)
        if tr.size == 0 or not np.any(vb[tr] > 0):
            beta = np.zeros(X.shape[1])
        else:
            okr = tr[vb[tr] > 0]
            beta = qmle(A.y[okr], np.log(vb[okr]), X[okr])
        betas[k] = beta.tolist()
        v_base[ix] = vb[ix]
        f = np.ones(A.n)
        f[ix] = np.exp(X[ix] @ beta)
        w = vb[ix] * f[ix]
        den = float(w.sum())
        v_term[ix] = float(A.y[ix].sum()) * w / den if den > 0 else 0.0
    return {"T": T, "v_base": v_base, "v_term": v_term, "betas": betas}


def production_term(A: Arrays, rows: list[dict], terms: dict, term: str, prod_fit: dict) -> np.ndarray:
    """The term's slope(s) fitted on every term row with the production group offset."""
    T = term_rows(A)
    vb = A.renorm(factor_of(prod_fit, A.grp), T)
    X = standardize(term_matrix(rows, terms, term, np.arange(A.n)), T, term=term)
    okr = T[vb[T] > 0]
    return qmle(A.y[okr], np.log(vb[okr]), X[okr]) if okr.size else np.zeros(X.shape[1])


# ---------------------------------------------------------------------------
# comparators and planted recovery (sections 6.3, 6.4)
# ---------------------------------------------------------------------------

def _noise(A0: Arrays, rng) -> np.ndarray:
    out = np.zeros(A0.n)
    for ix in A0.group_ix.values():
        out[ix] = A0.y[rng.permutation(ix)] - A0.y[ix].mean()
    return out


def recovered_ratio(fit: dict, j: int) -> float:
    """exp(theta*_j minus the precision-weighted mean of the other groups' theta*)."""
    s2 = fit["s2"]
    ok = np.isfinite(s2)
    others = [i for i in range(len(s2)) if i != j and ok[i]]
    if not others:
        return float("nan")
    w = np.asarray([1.0 / s2[i] for i in others])
    t = np.asarray([fit["theta_star"][i] for i in others])
    return float(np.exp(fit["theta_star"][j] - (w * t).sum() / w.sum()))


def planted_group(rows: list[dict], A0: Arrays, *, effect: bool, K: int, B: int, seed: int) -> dict:
    """y* = v_a x m + noise (the label's own spread, permuted inside each (frame, fold)),
    m = PLANT_MULT on the PLANT_GROUP rows (1 everywhere with effect False); kappa, the
    offsets and the cross-fit are rerun on y*. A hit is a one-sided 95 percent lower bound
    above 0 of the correction against zero adjustment."""
    j = GROUPS.index(PLANT_GROUP)
    m = np.where((A0.grp == j) & effect, PLANT_MULT, 1.0)
    W = twoway_weights(A0.key, A0.club, B=B, seed=seed)
    hits, deltas, rec = 0, [], []
    for k in range(int(K)):
        rng = np.random.default_rng(int(seed) + k)
        A = Arrays(rows, A0.v_a * m + _noise(A0, rng))
        v_p, _f = cross_fit_group(A)
        d = A.sq_err(A.v_a) - A.sq_err(v_p)
        lb = float(np.quantile(wmean_draws(d, W), LB_Q))
        hits += lb > 0
        deltas.append(float(d.mean()))
        prod = group_fit(A.y, A.v_a, A.grp, A.key)
        rec.append(recovered_ratio(prod, j))
    rec = np.asarray(rec)
    med = float(np.nanmedian(rec))
    ok = bool(abs(np.log(med) - np.log(PLANT_MULT)) <= RECOVER_TOL * abs(np.log(PLANT_MULT))) if effect else None
    return {"effect": bool(effect), "group": PLANT_GROUP, "multiplier": PLANT_MULT if effect else 1.0,
            "share_lb_above_0": round(hits / float(K), 4), "mean_delta": round(float(np.mean(deltas)), 5),
            "recovered_ratio_median": round(med, 4),
            "recovered_ratio_p10_p90": [round(float(np.nanquantile(rec, 0.1)), 4),
                                        round(float(np.nanquantile(rec, 0.9)), 4)],
            "recovered": ok, "K": int(K), "B": int(B), "seed": int(seed)}


def planted_term(rows: list[dict], A0: Arrays, terms: dict, term: str, *, effect: bool, K: int,
                 B: int, seed: int) -> dict:
    """y* = v_a x exp(PLANT_BETA x each standardized term column) re-allocated inside each
    (frame, fold) + noise; the whole pipeline (offsets, cross-fit, term) is rerun. A hit is a
    one-sided 95 percent lower bound above 0 of the term model against the group-only model
    on the term rows; recovery reads the production slope(s)."""
    T = term_rows(A0)
    X = standardize(term_matrix(rows, terms, term, np.arange(A0.n)), T, term=term)
    lin = np.zeros(A0.n)
    if effect:
        lin[T] = PLANT_BETA * X[T].sum(axis=1)
    mu = A0.renorm(np.exp(lin))
    WT = twoway_weights(A0.key[T], A0.club[T], B=B, seed=seed)
    hits, deltas, rec = 0, [], []
    for k in range(int(K)):
        rng = np.random.default_rng(int(seed) + k)
        A = Arrays(rows, mu + _noise(A0, rng))
        _vp, fits = cross_fit_group(A)
        ct = cross_fit_term(A, rows, terms, term, fits=fits)
        d = (A.sq_err(ct["v_base"]) - A.sq_err(ct["v_term"]))[T]
        lb = float(np.quantile(wmean_draws(d, WT), LB_Q))
        hits += lb > 0
        deltas.append(float(d.mean()))
        prod = group_fit(A.y, A.v_a, A.grp, A.key)
        rec.append(production_term(A, rows, terms, term, prod))
    rec = np.asarray(rec)
    med = np.median(rec, axis=0)
    ok = (bool(np.all(np.abs(med - PLANT_BETA) <= RECOVER_TOL * PLANT_BETA)) if effect else None)
    return {"term": term, "effect": bool(effect), "beta_planted": PLANT_BETA if effect else 0.0,
            "share_lb_above_0": round(hits / float(K), 4), "mean_delta": round(float(np.mean(deltas)), 5),
            "recovered_beta_median": [round(float(x), 4) for x in med],
            "recovered": ok, "K": int(K), "B": int(B), "seed": int(seed)}


def permuted_group_null(A: Arrays, *, K: int, seed: int) -> dict:
    out = []
    se_a = A.sq_err(A.v_a)
    for k in range(int(K)):
        rng = np.random.default_rng(int(seed) + 1000 + k)
        lab = A.grp.copy()
        for ix in A.group_ix.values():
            lab[ix] = lab[ix][rng.permutation(ix.size)]
        v, _f = cross_fit_group(A, grp_fit=lab)
        out.append(float((se_a - A.sq_err(v)).mean()))
    a = np.asarray(out)
    return {"K": int(K), "p95": round(float(np.quantile(a, 0.95)), 5), "mean": round(float(a.mean()), 5),
            "max": round(float(a.max()), 5)}


def permuted_term_null(A: Arrays, rows, terms, term, fits, *, K: int, seed: int) -> dict:
    T = term_rows(A)
    out = []
    for k in range(int(K)):
        rng = np.random.default_rng(int(seed) + 2000 + k)
        perm = np.arange(A.n)
        for kg in sorted({str(x) for x in A.kg[T]}):
            ix = A.group_ix[kg]
            perm[ix] = ix[rng.permutation(ix.size)]
        ct = cross_fit_term(A, rows, terms, term, fits=fits, x_perm=perm)
        out.append(float((A.sq_err(ct["v_base"]) - A.sq_err(ct["v_term"]))[T].mean()))
    a = np.asarray(out)
    return {"K": int(K), "p95": round(float(np.quantile(a, 0.95)), 5), "mean": round(float(a.mean()), 5)}


# ---------------------------------------------------------------------------
# descriptives (section 7): realized over implied by group, and the SS/CF movers
# ---------------------------------------------------------------------------

def eventual_positions(rows: list[dict]) -> dict[int, str | None]:
    """OUTCOME SIDE ONLY: the most-played non-DH position (games, MLB and MiLB) in the
    seasons from the row's grade year on, from the as-of season census
    (positions_played_seasons.json). Never a frame input."""
    try:
        doc = json.loads(SEASON_CENSUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    players = doc.get("players") or {}
    out = {}
    for i, r in enumerate(rows):
        sm = players.get(str(r["mlbam"])) if r["mlbam"] else None
        if not sm:
            out[i] = None
            continue
        tot: dict[str, int] = {}
        for season, by_pos in sm.items():
            try:
                yr = int(season)
            except (TypeError, ValueError):
                continue
            if yr < r["year"]:
                continue
            for pos, cell in (by_pos or {}).items():
                p = str(pos).upper()
                if p not in POS_NUM:
                    continue
                try:
                    g = int(cell[0] or 0)
                except (TypeError, ValueError, IndexError):
                    g = int((cell or {}).get("g") or 0) if isinstance(cell, dict) else 0
                tot[p] = tot.get(p, 0) + g
        out[i] = (max(sorted(tot), key=lambda p: (tot[p], -SPECTRUM.index(p)))
                  if tot and max(tot.values()) > 0 else None)
    return out


def descriptives(rows: list[dict], A: Arrays, W: np.ndarray) -> dict:
    out: dict = {"by_group": {}, "movers": {}}
    allh = np.ones(A.n, dtype=bool)
    for f in ("both",) + FRAMES:
        fm = allh if f == "both" else (A.fid == f)
        blk = {}
        for j, gname in enumerate(GROUPS):
            m = fm & (A.grp == j)
            blk[gname] = {"over_implied": ratio_ci(A.y, A.v_a, m, None, W),
                          "over_all_hitters": ratio_ci(A.y, A.v_a, m, fm, W)}
        blk[UNLISTED] = {"rows": int((fm & (A.grp < 0)).sum())}
        out["by_group"][f] = blk
    ev = eventual_positions(rows)
    j = GROUPS.index("SS/CF")
    sscf = A.grp == j
    lower = {"2B/3B", "LF/RF", "1B/DH"}
    known = np.asarray([ev.get(i) is not None for i in range(A.n)])
    mover = np.asarray([ev.get(i) is not None and GROUP_OF[ev[i]] in lower for i in range(A.n)])
    stayer = known & ~mover
    for f in ("both",) + FRAMES:
        fm = allh if f == "both" else (A.fid == f)
        base = fm & sscf
        out["movers"][f] = {
            "listed_sscf": int(base.sum()), "eventual_known": int((base & known).sum()),
            "movers_down": int((base & mover).sum()),
            "move_rate": (round(float((base & mover).sum() / max(1, (base & known).sum())), 4)
                          if (base & known).any() else None),
            "movers_over_implied": ratio_ci(A.y, A.v_a, base & mover, None, W),
            "stayers_over_implied": ratio_ci(A.y, A.v_a, base & stayer, None, W),
            "movers_over_stayers": ratio_ci(A.y, A.v_a, base & mover, base & stayer, W),
            "unknown_over_implied": ratio_ci(A.y, A.v_a, base & ~known, None, W)}
    out["eventual_coverage_rows"] = int(known.sum())
    return out


# ---------------------------------------------------------------------------
# the rule (section 8)
# ---------------------------------------------------------------------------

def rule(read: dict, plants: dict, term_reads: dict, term_plants: dict) -> dict:
    g = read["group_vs_zero"]["both"]
    pg, pn = plants["group"], plants["group_null"]
    rg = {"G1_lb95_above_0": bool(g["lb95_one_sided"] > 0),
          "G2_planted_recovered": bool(pg["recovered"]),
          "G3_size": bool(pn["share_lb_above_0"] <= SIZE_MAX)}
    passes = all(rg.values())
    word = "PASS" if passes else ("NULL" if pg["share_lb_above_0"] >= POWER_MIN else "UNRESOLVED")
    out = {"group": {"checks": rg, "passes": passes, "reading": word, "power": pg["share_lb_above_0"]}}
    for t in TERMS:
        d = term_reads[t]["term_vs_group"]
        p, pz = term_plants[t], term_plants[f"{t}_null"]
        rc = {"T1_lb95_above_0": bool(d["lb95_one_sided"] > 0),
              "T2_planted_recovered": bool(p["recovered"]),
              "T3_size": bool(pz["share_lb_above_0"] <= SIZE_MAX)}
        ok = all(rc.values())
        out[t] = {"checks": rc, "passes": ok, "power": p["share_lb_above_0"],
                  "reading": "PASS" if ok else ("NULL" if p["share_lb_above_0"] >= POWER_MIN else "UNDERPOWERED")}
    out["prepared"] = ({"group": True, "terms": [t for t in TERMS if out[t]["passes"]]}
                       if passes else None)
    return out


# ---------------------------------------------------------------------------
# the live board (section 9, decides nothing)
# ---------------------------------------------------------------------------

def board_effect(prod: dict) -> dict:
    """The production offsets on the live hitter board, at each live hitter's CURRENT listed
    position (the listing that is ex ante for the live grade); the live hitters' total implied
    value is kept, so the offsets only re-allocate it."""
    board = OM.live_board()["hit"]
    U = F.load_universe()
    keys, g, o = board["keys"], board["grade"], board["o"]
    lst = [resolve_listing([(U.get(k) or {}).get("position")]) for k in keys]
    gi = {gname: j for j, gname in enumerate(GROUPS)}
    grp = np.asarray([gi.get(x["group"], -1) for x in lst])
    f = factor_of(prod, grp)
    I = SRC.anchor_value(g)
    v = I * f * float(I.sum()) / float((I * f).sum())
    out = {"rows": len(keys), "by_group": {}}
    for j, gname in enumerate(GROUPS + (UNLISTED,)):
        m = grp == (j if gname != UNLISTED else -1)
        if m.any():
            out["by_group"][gname] = {"rows": int(m.sum()),
                                      "value_factor": round(float(v[m].sum() / I[m].sum()), 4),
                                      "mean_war6_change": round(float((v - I)[m].mean()), 3)}
    order = np.lexsort((-o, -g))[:TOP_N]
    out["top50"] = {"mean_war6_served": round(float(I[order].mean()), 3),
                    "mean_war6_calibrated": round(float(v[order].mean()), 3),
                    "rows": [{"player_key": keys[i], "group": lst[i]["group"], "efv": round(float(g[i]), 1),
                              "war6_served": round(float(I[i]), 2), "war6_calibrated": round(float(v[i]), 2)}
                             for i in order]}
    return out


# ---------------------------------------------------------------------------
# counts and the run
# ---------------------------------------------------------------------------

def counts(rows: list[dict], terms: dict | None = None) -> dict:
    out: dict = {}
    for f in FRAMES:
        sub = [r for r in rows if r["fid"] == f]
        blk = {"rows": len(sub)}
        for gname in GROUPS + (UNLISTED,):
            blk[gname] = sum(r["group"] == gname for r in sub)
        for how in ("listed", "generic_by_history", "generic_default", "unlisted"):
            blk[f"how:{how}"] = sum(r["how"] == how for r in sub)
        blk["club_unknown"] = sum(not r["club_known"] for r in sub)
        out[f] = blk
    out["players"] = len({r["key"] for r in rows})
    out["clubs"] = len({r["club"] for r in rows if r["club_known"]})
    out["groups"] = sorted({r["kg"] for r in rows})
    if terms is not None:
        by = terms["by_row"]
        tb: dict = {}
        for i, b in by.items():
            yr = rows[i]["year"]
            e = tb.setdefault(str(yr), {"rows": 0, "with_games": 0, "with_mfr_at_listed": 0,
                                        "mfr_chances_ge_200": 0, "n_pos_ge_2": 0})
            e["rows"] += 1
            e["with_games"] += b["games"] > 0
            e["with_mfr_at_listed"] += b["mfr_chances"] > 0
            e["mfr_chances_ge_200"] += b["mfr_chances"] >= 200
            e["n_pos_ge_2"] += (b["n_pos"] or 0) >= 2
        out["term_frame"] = tb
        out["term_frame_groups"] = {gname: sum(rows[i]["group"] == gname for i in by) for gname in GROUPS}
    return out


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


def prepare(cache_dir: Path, work: Path, *, log=print) -> dict:
    """Everything outcome-free: the cache and its checks (Q1, Q3, Q4 of the output map test,
    reused), the hitter rows, the listings, the clubs and the as-of terms."""
    pre = OM.prepare(cache_dir, log=log)
    got = _load(work, "rows")
    if got is None:
        rows = hitter_rows(pre, log=log)
        terms = asof_terms(rows, load_mfr(), log=log)
        got = {"rows": rows, "terms": terms}
        _save(work, "rows", got)
    return {"pre": pre, "rows": got["rows"], "terms": got["terms"],
            "counts": counts(got["rows"], got["terms"])}


def _clean(fit: dict, groups: tuple = GROUPS) -> dict:
    return {"groups": list(groups), "n": fit["n"].tolist(),
            "theta_bar": round(float(fit["theta_bar"]), 5), "tau2": round(float(fit["tau2"]), 6),
            "Q": round(float(fit["Q"]), 4),
            "shrink": [round(float(x), 4) for x in fit["shrink"]],
            "factor": [round(float(np.exp(t - fit["theta_bar"])), 4) for t in fit["theta_star"]],
            "raw_ratio_over_pool": [None if not np.isfinite(t) or not np.isfinite(s) else
                                    round(float(np.exp(t - fit["theta_bar"])), 4)
                                    for t, s in zip(fit["theta"], fit["s2"])],
            "se_log": [None if not np.isfinite(s) else round(float(np.sqrt(s)), 4) for s in fit["s2"]],
            "mde_log_one_sided": [None if not np.isfinite(s) else round(float(Z_MDE * np.sqrt(s)), 4)
                                  for s in fit["s2"]]}


def run(cache_dir: Path, work: Path, *, B: int = B_MAIN, log=print) -> dict:
    import efv5_refit as RF
    import efv_labels as L
    BT, _B4 = OM._tools()
    t0 = time.time()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    prep = prepare(cache_dir, work, log=log)
    pre, rows, terms = prep["pre"], prep["rows"], prep["terms"]
    q2 = OM.parity_q2(pre["packs"], pre["b1"], pre["fit"])
    log(f"Q2: published within reproduced ({q2})")
    A = Arrays(rows)
    W = twoway_weights(A.key, A.club, B=B, seed=SEED)
    v_p, fits = cross_fit_group(A)
    d = A.sq_err(A.v_a) - A.sq_err(v_p)
    read: dict = {"group_vs_zero": {"both": paired(d, W)}}
    for f in FRAMES:
        m = A.fid == f
        read["group_vs_zero"][f] = {"delta": round(float(d[m].mean()), 5), "n": int(m.sum())}
    log(f"group vs zero: {read['group_vs_zero']['both']}")
    read["loss"] = {"zero": round(float(A.sq_err(A.v_a).mean()), 5), "group": round(float(A.sq_err(v_p).mean()), 5)}
    read["fold_offsets"] = {k: _clean(f) for k, f in fits.items()}
    # sensitivity, decides nothing: a generic OF listing as its own pooled cell
    rows6 = [dict(r, group6=(GENERIC_OF_CELL if r["how"] == "generic_default" and r["group"] == "LF/RF"
                             else r["group"])) for r in rows]
    A6 = Arrays(rows6, groups=GROUPS + (GENERIC_OF_CELL,), group_key="group6")
    v6, _f6 = cross_fit_group(A6)
    read["sensitivity_generic_of_cell"] = {
        "rows_in_cell": int((A6.grp == len(GROUPS)).sum()),
        "vs_zero": paired(A6.sq_err(A6.v_a) - A6.sq_err(v6), W),
        "production": _clean(group_fit(A6.y, A6.v_a, A6.grp, A6.key, len(A6.groups)), A6.groups)}
    T = term_rows(A)
    WT = twoway_weights(A.key[T], A.club[T], B=B, seed=SEED + 1)
    dT = d[T]
    read["group_vs_zero"]["term_frame"] = paired(dT, WT)
    term_reads: dict = {}
    for t in TERMS:
        ct = cross_fit_term(A, rows, terms, t, fits=fits)
        dt = (A.sq_err(ct["v_base"]) - A.sq_err(ct["v_term"]))[T]
        prod_fit = group_fit(A.y, A.v_a, A.grp, A.key)
        beta = production_term(A, rows, terms, t, prod_fit)
        # the slope's two-way clustered SE on the term rows (production fit), for the MDE
        Wm = twoway_weights(A.key[T], A.club[T], B=B_MDE, seed=SEED + 2)
        vb = A.renorm(factor_of(prod_fit, A.grp), T)
        X = standardize(term_matrix(rows, terms, t, np.arange(A.n)), T, term=t)
        bs = []
        for w in Wm:
            sel = np.repeat(T, w.astype(np.int64))
            sel = sel[vb[sel] > 0]
            if sel.size > 5:
                bs.append(qmle(A.y[sel], np.log(vb[sel]), X[sel]))
        bs = np.asarray(bs)
        se = bs.std(axis=0, ddof=1) if len(bs) > 2 else np.full(len(beta), np.nan)
        term_reads[t] = {"term_vs_group": paired(dt, WT), "fold_betas": ct["betas"],
                         "beta_production": [round(float(x), 4) for x in beta],
                         "beta_se_twoway": [round(float(x), 4) for x in se],
                         "beta_mde_one_sided": [round(float(Z_MDE * x), 4) for x in se],
                         "n_term_rows": int(T.size)}
        for yr in sorted({int(x) for x in A.year[T]}):
            m = A.year[T] == yr
            term_reads[t][f"delta_{yr}"] = round(float(dt[m].mean()), 5)
        log(f"term {t}: {term_reads[t]['term_vs_group']} beta {term_reads[t]['beta_production']}")
    nulls = _load(work, "nulls")
    if nulls is None:
        nulls = {"group_permuted": permuted_group_null(A, K=K_NULL, seed=SEED)}
        for t in TERMS:
            nulls[f"{t}_permuted"] = permuted_term_null(A, rows, terms, t, fits, K=K_NULL, seed=SEED)
        _save(work, "nulls", nulls)
    plants = _load(work, "plants")
    if plants is None:
        plants = {"group": planted_group(rows, A, effect=True, K=K_PLANT, B=B_PLANT, seed=SEED + 7),
                  "group_null": planted_group(rows, A, effect=False, K=K_PLANT, B=B_PLANT, seed=SEED + 7)}
        _save(work, "plants", plants)
    log(f"planted group: {plants['group']}; null: {plants['group_null']}")
    term_plants = _load(work, "term_plants")
    if term_plants is None:
        term_plants = {}
        for t in TERMS:
            term_plants[t] = planted_term(rows, A, terms, t, effect=True, K=K_PLANT, B=B_PLANT, seed=SEED + 11)
            term_plants[f"{t}_null"] = planted_term(rows, A, terms, t, effect=False, K=K_PLANT, B=B_PLANT,
                                                    seed=SEED + 11)
            log(f"planted {t}: {term_plants[t]}; null: {term_plants[f'{t}_null']}")
        _save(work, "term_plants", term_plants)
    desc = descriptives(rows, A, W)
    verdict = rule(read, plants, term_reads, term_plants)
    prod = group_fit(A.y, A.v_a, A.grp, A.key)
    effect = board_effect(prod)
    T_years = sorted({int(x) for x in A.year[T]})
    censor = {str(y): {"rows": int((A.year[T] == y).sum()), "seasons_observed_through_2026": 2026 - y + 1}
              for y in T_years}
    doc = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --run", "generated_at": BT._now(),
           "role": "development", "adjudicates": False, "doc": DOC, "owner_decision": OWNER_DECISION,
           "label": pre["fit"].get("label"), "source_fit": RF.FIT_PATH.relative_to(ROOT).as_posix(),
           "served_weights": pre["weights"],
           "constants": {"seed": SEED, "B": int(B), "B_MDE": B_MDE, "K_NULL": K_NULL, "K_PLANT": K_PLANT,
                         "B_PLANT": B_PLANT, "LB_Q": LB_Q, "SIZE_MAX": SIZE_MAX, "POWER_MIN": POWER_MIN,
                         "RECOVER_TOL": RECOVER_TOL, "R_FLOOR": R_FLOOR, "PLANT_GROUP": PLANT_GROUP,
                         "PLANT_MULT": PLANT_MULT, "PLANT_BETA": PLANT_BETA,
                         "TERM_FIRST_YEAR": TERM_FIRST_YEAR, "MIN_G": MIN_G, "MIN_GS": MIN_GS,
                         "GS_INN": GS_INN, "GROUPS": list(GROUPS)},
           "checks": {"Q1_fold_receipts": pre["q1"], "Q2_published_within": q2,
                      "Q3_reserved": "no reserved fold", "Q4_live_board": pre["q4"]},
           "counts": prep["counts"], "term_frame_censoring": censor,
           "mfr_scales": terms["scales"],
           "instrument": "6 x value_framework.fv_to_6yr_avg_war (served, side-pooled)",
           "read": read, "terms": term_reads, "null_comparators": nulls, "planted": plants,
           "planted_terms": term_plants, "descriptives": desc, "rules": verdict,
           "production_offsets": _clean(prod), "board_effect": effect,
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
    ap.add_argument("--work", default=None, help="a scratch directory")
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    if not (a.cache and a.work):
        log("refused: --cache and --work are needed")
        return 2
    if a.check:
        prep = prepare(Path(a.cache), Path(a.work), log=log)
        out = {"q1": prep["pre"]["q1"], "q4": prep["pre"]["q4"], "counts": prep["counts"]}
        (Path(a.work) / "check.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        log(json.dumps(out, default=str))
        return 0
    if a.run:
        if OUT_PATH.exists():
            log(f"refused: {OUT_PATH} exists; the read runs once")
            return 2
        run(Path(a.cache), Path(a.work), B=B_MAIN if a.B is None else int(a.B), log=log)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
