# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV pitcher usage (reliever) adjustment (EFV_RELIEVER_ADJ; owner decision EW3-31,
2026-10-15; method docs/efv-v2/EFV_RELIEVER_ADJ.md, committed alone before this module).

THE QUESTION. Does the served pitcher order (eFV v5 COMBINED re-fit RT) over-predict for
pitchers used in short outings or in relief, given the shift it makes off consensus, and
does an adjustment order pitchers better on the development frames.

THE USAGE CLASSIFICATION (the document, section 2): from the minor league lines through the
row's read season only, starter share GS / G, IP per appearance, IP per start and BF per
appearance; RELIEF (GS / G < 0.5), SHORT-START (GS / G >= 0.5, IP / GS < 3.5), STARTER,
FEW (1 to 4 appearances) and NO-LINE.

THE READ. RT's committed development read rebuilt from its cached fold builds (parity
checked against data/_labs/efv5/efv5_refit_fit.json), then the estimand (E1 realized share
of the shift by role, E2 the audit's D4 measure) and three candidates against the zero
adjustment Z: A (a role term in the skill head), B (a role-specific DS-08 weight on the
skill shift), C (rate drivers normalized for outing length before the head). A permuted-role
null and a planted-effect recovery check on the real design sit beside the ship rule.

THE SERVED PATH. RELIEVER_ADJ_ON stays False here; on a pass the prepared candidate's
production fit is stored and the owner flips it. The usage label of the PROSPX card
(data/efv_pitcher_roles.json, export_roles) is a statement of usage and moves no grade.

RESERVED FRAMES. Only the development frames' cached builds are read; the list-vintage frame
builder is called for vintages 2011 to 2019 only (its own guard raises on 2020 and 2021).

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): the strata are frame, side, year, fold, usage
role and the model's own shift; nothing here groups, counts or averages rows by
consensus-FV level; test_efv_reliever_adj.py scans this source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import sys
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
FIT_PATH = LAB_DIR / "efv_reliever_adj_fit.json"
WEIGHTS_PATH = DATA_DIR / "efv_reliever_adj_weights.json"
ROLES_PATH = DATA_DIR / "efv_pitcher_roles.json"
RT_FIT_PATH = LAB_DIR / "efv5_refit_fit.json"
DOC = "docs/efv-v2/EFV_RELIEVER_ADJ.md"
TOOL = "efv_reliever_adj.py"
ITEM = "EFV_RELIEVER_ADJ"
OWNER_DECISION = "EW3-31 (2026-10-15)"

#: THE SWITCH. False: nothing here changes a served grade. True (only after a PREPARED read
#: and the owner's flip): the served pitcher order applies the prepared candidate's
#: production fit from data/efv_reliever_adj_weights.json.
RELIEVER_ADJ_ON = False

# ---------------------------------------------------------------------------
# section 2: the usage classification (fixed before any outcome read)
# ---------------------------------------------------------------------------

STARTER, SHORT, RELIEF, FEW, NO_LINE = "STARTER", "SHORT-START", "RELIEF", "FEW", "NO-LINE"
ROLES: tuple[str, ...] = (STARTER, SHORT, RELIEF, FEW, NO_LINE)
#: the classes a candidate adjusts; every other class is the reference (no adjustment)
ADJUSTED: tuple[str, ...] = (SHORT, RELIEF)
MIN_G = 5
GS_SHARE_CUT = 0.5
IP_PER_GS_CUT = 3.5
WINDOWS: tuple[str, ...] = ("rule", "two")
GRID_GS: tuple[float, ...] = (0.4, 0.5, 0.6)
GRID_IPGS: tuple[float, ...] = (3.0, 3.5, 4.0)
#: the card's class words (section 9)
LABEL_WORD = {STARTER: "Starter", SHORT: "Short starts", RELIEF: "Reliever"}

# ---------------------------------------------------------------------------
# sections 3 to 6: the read's constants
# ---------------------------------------------------------------------------

BOOT_B = 2000
BOOT_SEED = 20261017
PERM_SEED = 20261018
SIM_SEED = 20261019
PERM_K = {"A": 50, "B": 200}
SIM_REPS = 200
SIM_B = 200
PLANT_K = 0.4
MAX_TRAIL = 0.005
PARITY_TOL = 5e-5
#: RT's committed pitcher within Spearman (efv5_refit_fit.json frames.*.per_side.pit)
PARITY_KEY = "efv_v5_rt"
CANDIDATES: tuple[str, ...] = ("A", "B", "C")
KEY = {"Z": "efv_rel_z", "A": "efv_rel_a", "B": "efv_rel_b", "C": "efv_rel_c"}
FRAMES: tuple[str, ...] = ("lv_dev", "vm_dev")
#: section 4, C: the pitcher rate drivers normalized for outing length (v2 keys)
RATE_KEYS: tuple[str, ...] = (
    "k_rel",
    "scr_g5_pit_A_all_all_k_pct", "scr_g5_pit_A_young_all_k_pct", "scr_g5_pit_A_all_SP_k_pct",
    "scr_g5_pit_A_all_all_k_minus_bb", "scr_g5_pit_A_young_all_k_minus_bb",
    "scr_g5_pit_A_all_SP_k_minus_bb",
    "scr_w2p_csw_p", "scr_w2p_cstr_p", "scr_w2p_k_resid_p", "scr_w4p_pop_pit",
)
SIDE = "pit"


def _modules():
    import efv5_combined as V5C
    import efv5_refit as R5
    import efv_v2_model as H
    return V5C, R5, H


def _tools():
    import efv5_combined as V5C
    return V5C._tools()


def _rnd(v, d=4):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return round(f, d) if math.isfinite(f) else None


# ---------------------------------------------------------------------------
# the lines
# ---------------------------------------------------------------------------

def _num(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


@lru_cache(maxsize=None)
def season_usage(season: int) -> dict:
    """{mlbam: (G, GS, outs, BF)} summed over one season's affiliated minor league pitching
    lines (cache only; the non-affiliated Mexican League out, the repaired population's
    rule)."""
    import efv_w2_popmle as PM
    import milb_history as mh
    acc: dict = {}
    for sp in PM.SPORTS:
        for r in mh.season_splits(int(sp), int(season), "pitching", fetch=False):
            pid, lv = r.get("mlbam"), r.get("level")
            if not pid or lv not in PM.LEVEL_RANK:
                continue
            if (int(sp), str(r.get("league") or "")) in PM.NON_AFFILIATED_LEAGUES:
                continue
            a = acc.setdefault(int(pid), [0.0, 0.0, 0.0, 0.0])
            a[0] += _num(r.get("g"))
            a[1] += _num(r.get("gs"))
            a[2] += PM._outs(r.get("ip")) or 0.0
            a[3] += _num(r.get("bf"))
    return {k: tuple(v) for k, v in acc.items()}


def ip_text(outs: float) -> str:
    """Innings as box scores print them (89 outs is "29.2")."""
    o = int(round(float(outs)))
    return f"{o // 3}.{o % 3}"


def classify(g: float, gs: float, outs: float, *, gs_cut: float = GS_SHARE_CUT,
             ipgs_cut: float = IP_PER_GS_CUT, min_g: int = MIN_G) -> str:
    """The class of a summed window (section 2)."""
    if g <= 0:
        return NO_LINE
    if g < min_g:
        return FEW
    if gs / g < gs_cut:
        return RELIEF
    if (outs / 3.0) / gs < ipgs_cut:
        return SHORT
    return STARTER


def usage(mlbam, read_season, *, window: str = "rule", gs_cut: float = GS_SHARE_CUT,
          ipgs_cut: float = IP_PER_GS_CUT, min_g: int = MIN_G) -> dict:
    """The usage reading of one pitcher as of a read season: the read season's lines alone
    when they hold min_g or more appearances, else the read season plus the one before
    (window "two": always both). Never a season after the read season."""
    if window not in WINDOWS:
        raise ValueError(window)
    if not mlbam or read_season is None:
        return {"role": NO_LINE}
    mid, rs = int(mlbam), int(read_season)
    tot = [0.0, 0.0, 0.0, 0.0]
    seasons = []
    cur = season_usage(rs).get(mid)
    if cur and cur[0] > 0:
        tot = [a + b for a, b in zip(tot, cur)]
        seasons.append(rs)
    if window == "two" or tot[0] < min_g:
        prev = season_usage(rs - 1).get(mid)
        if prev and prev[0] > 0:
            tot = [a + b for a, b in zip(tot, prev)]
            seasons.insert(0, rs - 1)
    g, gs, outs, bf = tot
    role = classify(g, gs, outs, gs_cut=gs_cut, ipgs_cut=ipgs_cut, min_g=min_g)
    if role == NO_LINE:
        return {"role": NO_LINE, "read_season": rs}
    ip = outs / 3.0
    return {"role": role, "read_season": rs, "seasons": seasons, "g": int(g), "gs": int(gs),
            "ip": ip_text(outs), "outs": int(outs), "bf": int(bf),
            "gs_share": gs / g, "ip_per_g": ip / g,
            "ip_per_gs": (ip / gs) if gs > 0 else None, "bf_per_g": (bf / g) if g > 0 else None}


def role_group(role: str) -> str:
    """The candidates' grouping: SHORT-START and RELIEF are adjusted, the rest is the
    reference."""
    return role if role in ADJUSTED else "REF"


def label_text(u: dict) -> str | None:
    """The card's plain line (section 9); None for FEW and NO-LINE."""
    word = LABEL_WORD.get(u.get("role"))
    if word is None:
        return None
    ss = u.get("seasons") or []
    when = (f"{ss[0]}" if len(ss) == 1 else f"{ss[0]}-{str(ss[-1])[2:]}") if ss else ""
    per = (f"{u['ip_per_gs']:.1f} IP per start" if u["role"] != RELIEF and u.get("ip_per_gs")
           else f"{u['ip_per_g']:.1f} IP per appearance")
    return (f"Usage: {word} ({when} MiLB): {u['g']} G, {u['gs']} GS, {u['ip']} IP, {per}")


# ---------------------------------------------------------------------------
# the read of each row (section 2: as of each read)
# ---------------------------------------------------------------------------

class RoleBook:
    """(mlbam, read season) of every pitcher row the read touches, by the row's own read:
    list-vintage rows read V - 1 with the frame's outcome-blind id; matrix rows read at
    their cutoff (a vm_dev test row at its pinned preseason as-of date); twins at their
    read season; live rows at the live read season."""

    def __init__(self, *, live_season: int | None = None):
        V5C, _R5, _H = _modules()
        self.raw = V5C._raw_by_side()[SIDE]
        self.pinned = V5C._pinned_asof(SIDE)
        self.live_season = live_season
        self._lv: dict = {}
        self._universe = None

    def lv_ids(self, V: int) -> dict:
        import efv_vintage_frame as F
        V = int(V)
        if V in F.RESERVED_LV:
            raise F.ReservedFrameError(f"list vintage {V} is reserved")
        if V not in self._lv:
            if self._universe is None:
                self._universe = F.load_universe()
            rows = F.build_frame(SIDE, V, universe=self._universe, milb=False, sidecars=False)
            self._lv[V] = {r["player_key"]: (r.get("mlbam_id"), (r.get("window") or [None])[0])
                           for r in rows}
        return self._lv[V]

    def read_of(self, row: dict, kind: str) -> tuple:
        from efv_w2_milb import last_readable_season
        pk = row["player_key"]
        if row.get("twin"):
            return row.get("mlbam_id"), int(row["twin_read_season"])
        fr = row.get("frame")
        if fr == "live":
            return row.get("mlbam_id"), self.live_season
        dy = int(row["decision_year"])
        if fr == "lv":
            mid, lo = self.lv_ids(dy).get(pk, (None, None))
            return mid, last_readable_season(dy, lo)
        raw = self.raw.get(pk) or {}
        cut = raw.get("cutoff")
        if kind == "test" and self.pinned.get(pk):
            cut = self.pinned[pk]
        return raw.get("mlbam_id"), last_readable_season(dy, cut)

    def usage_of(self, row: dict, kind: str, **kw) -> dict:
        mid, rs = self.read_of(row, kind)
        return usage(mid, rs, **kw)


# ---------------------------------------------------------------------------
# the cached development builds of the committed RT read
# ---------------------------------------------------------------------------

def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_cache(cache_dir: Path) -> tuple[dict, list, dict]:
    """(build1, RT's fold packs, receipt) from the re-fit read's cache directory."""
    _tools()
    cache_dir = Path(cache_dir)
    rec = {}
    with (cache_dir / "build1.pkl").open("rb") as fh:
        b1 = pickle.load(fh)
    with (cache_dir / "packs_RT.pkl").open("rb") as fh:
        packs, _r = pickle.load(fh)
    for n in ("build1.pkl", "packs_RT.pkl"):
        rec[n] = {"sha256": _sha(cache_dir / n), "bytes": (cache_dir / n).stat().st_size}
    return b1, packs, rec


class Fold:
    """One pitcher fold of RT's read: the pack (test-row and scored-row terms), its
    cross-fitted weights, its test and training rows, and the rows' usage."""

    def __init__(self, pack: dict, wcf: dict, test: list, train: list):
        self.p = pack
        self.fid = pack["fid"]
        self.fold = int(pack["fold"])
        self.fold_id = pack["fold_id"]
        self.w = wcf
        self.test = test
        self.train = train
        self.u_test: list = []
        self.u_train: list = []

    @property
    def keys(self):
        return self.p["keys"]


def build_folds(b1: dict, packs: list, wcf: dict, book: RoleBook, *, log=print) -> list[Fold]:
    """Every pitcher fold of both development frames with the rows each candidate reads
    (the re-fit's FC design: lv_dev trains on its fold's list-vintage rows, vm_dev on its
    earlier matrix rows plus their twins)."""
    V5C, R5, _H = _modules()
    inp = b1["inp"]
    twins = b1["twins"][SIDE]
    out = []
    for p in packs:
        if p["side"] != SIDE:
            continue
        fid, Y = p["fid"], int(p["fold"])
        blk = inp.frames[fid]["by_side"][SIDE][Y]
        cols = (inp.cols.get(fid) or {}).get(SIDE) or {}
        te = V5C.attach(blk["test"], SIDE, cols, "test")
        tr = V5C.attach(blk["train"], SIDE, cols, "train")
        if fid == "vm_dev":
            tr = tr + [t for t in twins if int(t["decision_year"]) < Y]
        if [r["player_key"] for r in te] != list(p["keys"]):
            raise RuntimeError(f"{p['fold_id']}: the test rows differ from the pack's")
        f = Fold(p, wcf[p["fold_id"]], te, tr)
        f.u_test = [book.usage_of(r, "test") for r in te]
        f.u_train = [book.usage_of(r, "train") for r in tr]
        out.append(f)
        log(f"  {p['fold_id']}: {len(te)} test rows, {len(tr)} training rows")
    return out


# ---------------------------------------------------------------------------
# orders and statistics
# ---------------------------------------------------------------------------

def scored_rows(inp, fid: str) -> list[dict]:
    return [c for c in inp.scored(fid, sides=(SIDE,))]


def rows_with(inp, fid: str, orders: dict[str, dict]) -> list[dict]:
    """The frame's pitcher scored rows with each configuration's order under KEY[name];
    orders[name] = {(fid, fold, key): order}."""
    out = []
    for c in scored_rows(inp, fid):
        g = dict(c["grades"])
        k = (fid, int(c["year"]), c["key"])
        for name, od in orders.items():
            if k in od:
                g[KEY[name]] = float(od[k])
        out.append(dict(c, grades=g))
    return out


def within_of(rows: list[dict], key: str) -> float | None:
    import efv_v2_stat as S
    BT, _B4 = _tools()
    sel = [c for c in rows if c["grades"].get(key) is not None]
    if not sel:
        return None
    st = S.rater_stats([c["grades"][key] for c in sel], [c["outcome"]["war"] for c in sel],
                       [bool(c["outcome"]["contributor"]) for c in sel],
                       [c["group"] for c in sel], [c["grades"][BT.CONS] for c in sel])
    return st["within"]


def pooled_delta(rows_by_frame: dict, a: str, b: str, *, B: int, seed: int | None = None) -> dict:
    """The paired within difference over both frames' pitcher rows: groups (frame, year),
    player clusters spanning the frames (E_cond)."""
    import efv_v2_stat as S
    BT, _B4 = _tools()
    sel = [(fid, c) for fid in FRAMES for c in rows_by_frame[fid]
           if c["grades"].get(a) is not None and c["grades"].get(b) is not None]
    d = S.paired_delta([c["key"] for _f, c in sel], [f"{f}|{c['group']}" for f, c in sel],
                       [c["outcome"]["war"] for _f, c in sel],
                       [bool(c["outcome"]["contributor"]) for _f, c in sel],
                       [c["grades"][a] for _f, c in sel], [c["grades"][b] for _f, c in sel],
                       [c["grades"][BT.CONS] for _f, c in sel], statistic="within",
                       B=int(B), seed=BT.SEED if seed is None else int(seed))
    return {k: d.get(k) for k in ("delta", "ci95", "n", "n_clusters", "a", "b", "status",
                                  "p_gt_0", "mde95")}


def frame_delta(rows: list[dict], a: str, b: str, *, B: int) -> dict:
    BT, _B4 = _tools()
    d = BT.paired(rows, a, b, "within", B=B, seed=BT.SEED)
    return {k: d.get(k) for k in ("delta", "ci95", "n", "a", "b", "reading", "status")}


def orders_of(folds: list[Fold], term) -> dict:
    """{(fid, fold, key): order} on every test row: term(fold) gives the order array."""
    out = {}
    for f in folds:
        o = term(f)
        for k, v in zip(f.keys, o):
            out[(f.fid, f.fold, k)] = float(v)
    return out


def z_term(f: Fold) -> np.ndarray:
    """Z: RT as read (u_c plus the cross-fitted weights times the head terms)."""
    return f.p["u_c"] + f.w["w_skill"] * f.p["e_s"] + f.w["w_time"] * f.p["e_t"]


# ---------------------------------------------------------------------------
# the scored-row terms of the weight rule (DS-08's own arrays) with roles
# ---------------------------------------------------------------------------

def ols_roles(f: Fold, roles_test: list[str] | None = None) -> list[str]:
    roles_test = roles_test if roles_test is not None else [u["role"] for u in f.u_test]
    pos = {k: i for i, k in enumerate(f.keys)}
    return [roles_test[pos[k]] for k in f.p["ols"]["keys"]]


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def _share(r):
    _V5C, _R5, H = _modules()
    return H._share(r)


def role_ols(u_c, u_y, e_s, e_t, groups, *, with_time: bool = True) -> dict:
    """B's rule (section 4): OLS u_y ~ 1 + u_c + sum over role groups g of I(g) x e_skill +
    e_time + I(SHORT-START) + I(RELIEF); w_g = clip(c_g / c_uc, 0, 1). A role group absent
    from the rows takes the reference weight."""
    u_c, u_y, e_s, e_t = (np.asarray(a, dtype=np.float64) for a in (u_c, u_y, e_s, e_t))
    g = np.asarray(groups)
    cols, names = [np.ones(u_y.size), u_c], ["intercept", "u_c"]
    present = [r for r in ("REF",) + ADJUSTED if np.any(g == r)]
    for r in present:
        cols.append(e_s * (g == r))
        names.append(f"e_skill|{r}")
    if with_time and np.any(e_t != 0):
        cols.append(e_t)
        names.append("e_time")
    for r in ADJUSTED:
        if np.any(g == r):
            cols.append((g == r).astype(np.float64))
            names.append(f"I|{r}")
    b = _ols(np.column_stack(cols), u_y)
    coef = dict(zip(names, (float(x) for x in b)))
    c_uc = coef["u_c"]
    out = {"n": int(u_y.size), "coef": coef}
    ref = None
    for r in ("REF",) + ADJUSTED:
        c = coef.get(f"e_skill|{r}")
        ratio = (c / c_uc) if (c is not None and c_uc > 0) else None
        if r == "REF":
            ref = ratio
        out[f"ratio|{r}"] = ratio
    for r in ("REF",) + ADJUSTED:
        ratio = out[f"ratio|{r}"] if out[f"ratio|{r}"] is not None else ref
        out[f"w|{r}"] = _share(ratio)
    ct = coef.get("e_time")
    out["ratio|time"] = (ct / c_uc) if (ct is not None and c_uc > 0) else None
    out["w|time"] = _share(out["ratio|time"])
    return out


def _pool(folds: list[Fold], e_of=None, roles_of=None) -> tuple:
    u_c, u_y, e_s, e_t, gr, keys = [], [], [], [], [], []
    for f in folds:
        o = f.p["ols"]
        u_c.append(o["u_c"])
        u_y.append(o["u_y"])
        e_s.append(e_of(f) if e_of else o["e_s"])
        e_t.append(o["e_t"])
        rl = roles_of(f) if roles_of else ols_roles(f)
        gr += [role_group(r) for r in rl]
        keys += list(o["keys"])
    cat = (lambda a: np.concatenate(a) if a else np.zeros(0))
    return cat(u_c), cat(u_y), cat(e_s), cat(e_t), gr, keys


def b_weights(folds: list[Fold], roles_of=None) -> dict:
    u_c, u_y, e_s, e_t, gr, _k = _pool(folds, roles_of=roles_of)
    return role_ols(u_c, u_y, e_s, e_t, gr)


def b_cross_fitted(folds: list[Fold], roles_of=None) -> dict:
    return {f.fold_id: b_weights([g for g in folds if g.fold_id != f.fold_id], roles_of)
            for f in folds}


def b_orders(folds: list[Fold], wcf: dict, roles_test_of=None) -> dict:
    def term(f):
        w = wcf[f.fold_id]
        rl = roles_test_of(f) if roles_test_of else [u["role"] for u in f.u_test]
        ws = np.asarray([w[f"w|{role_group(r)}"] for r in rl])
        return f.p["u_c"] + ws * f.p["e_s"] + w["w|time"] * f.p["e_t"]
    return orders_of(folds, term)


# ---------------------------------------------------------------------------
# E1 and E2: the estimand
# ---------------------------------------------------------------------------

def _shift_arrays(folds: list[Fold], roles_of=None) -> dict:
    """Pooled scored-row arrays: u_c, u_y, shift s (RT's cross-fitted weights), role,
    frame, fold and player key."""
    u_c, u_y, s, roles, fr, fo, keys = [], [], [], [], [], [], []
    for f in folds:
        o = f.p["ols"]
        u_c.append(o["u_c"])
        u_y.append(o["u_y"])
        s.append(f.w["w_skill"] * o["e_s"] + f.w["w_time"] * o["e_t"])
        rl = roles_of(f) if roles_of else ols_roles(f)
        roles += list(rl)
        fr += [f.fid] * len(rl)
        fo += [f.fold] * len(rl)
        keys += list(o["keys"])
    return {"u_c": np.concatenate(u_c), "u_y": np.concatenate(u_y), "s": np.concatenate(s),
            "role": np.asarray(roles), "frame": np.asarray(fr), "fold": np.asarray(fo),
            "key": np.asarray(keys)}


def realized_shares(u_c, u_y, s, role) -> dict:
    """E1: rho_r = c_r / c_uc in u_y ~ 1 + u_c + sum_r I(r) x s + I(SS) + I(R), with FEW and
    NO-LINE in the STARTER role; and the pooled non-starter form."""
    g = np.asarray([r if r in ADJUSTED else STARTER for r in role])
    out = {}
    cols, names = [np.ones(u_y.size), u_c], ["intercept", "u_c"]
    for r in (STARTER,) + ADJUSTED:
        if np.any(g == r):
            cols.append(s * (g == r))
            names.append(r)
    for r in ADJUSTED:
        if np.any(g == r):
            cols.append((g == r).astype(np.float64))
            names.append(f"I|{r}")
    b = dict(zip(names, _ols(np.column_stack(cols), u_y)))
    for r in (STARTER,) + ADJUSTED:
        out[r] = float(b[r] / b["u_c"]) if (r in b and b["u_c"] > 0) else None
    ns = np.isin(g, ADJUSTED)
    X = np.column_stack([np.ones(u_y.size), u_c, s * ~ns, s * ns, ns.astype(np.float64)])
    b2 = _ols(X, u_y)
    out["NONSTARTER"] = float(b2[3] / b2[1]) if b2[1] > 0 else None
    out["NONSTARTER_minus_STARTER"] = (None if out["NONSTARTER"] is None or out[STARTER] is None
                                       else out["NONSTARTER"] - out[STARTER])
    out["n"] = {r: int(np.sum(g == r)) for r in (STARTER,) + ADJUSTED}
    return out


def _clusters(keys) -> list:
    ids: dict = {}
    for k in keys:
        ids.setdefault(k, len(ids))
    cl = np.asarray([ids[k] for k in keys])
    return [np.flatnonzero(cl == i) for i in range(len(ids))]


def boot_shares(arr: dict, *, B: int = BOOT_B, seed: int = BOOT_SEED, mask=None) -> dict:
    m = np.ones(arr["u_c"].size, dtype=bool) if mask is None else mask
    a = {k: v[m] for k, v in arr.items()}
    est = realized_shares(a["u_c"], a["u_y"], a["s"], a["role"])
    members = _clusters(a["key"])
    rng = np.random.default_rng(int(seed))
    got: dict = {k: [] for k in est if k != "n"}
    for _ in range(int(B)):
        draw = rng.integers(0, len(members), size=len(members))
        ix = np.concatenate([members[j] for j in draw])
        try:
            e = realized_shares(a["u_c"][ix], a["u_y"][ix], a["s"][ix], a["role"][ix])
        except np.linalg.LinAlgError:
            continue
        for k in got:
            if e.get(k) is not None:
                got[k].append(e[k])
    out = {"n": est["n"], "B": int(B), "seed": int(seed), "unit": "player cluster"}
    for k in got:
        v = np.asarray(got[k])
        out[k] = {"est": _rnd(est[k]),
                  "ci95": ([_rnd(np.quantile(v, 0.025)), _rnd(np.quantile(v, 0.975))]
                           if v.size > 1 else None)}
    return out


def d4_measure(arr: dict, *, B: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """E2: the audit's D4 measure by role on model-up rows (the top fifth of the centered
    shift within (frame, fold)); out_pct is the fold's label percentile (u_y)."""
    n = arr["u_c"].size
    shc = np.zeros(n)
    up = np.zeros(n, dtype=bool)
    for fr in np.unique(arr["frame"]):
        for fo in np.unique(arr["fold"][arr["frame"] == fr]):
            m = (arr["frame"] == fr) & (arr["fold"] == fo)
            ix = np.flatnonzero(m)
            c = arr["s"][ix] - arr["s"][ix].mean()
            shc[ix] = c
            cut = np.quantile(c, 0.8)
            up[ix] = c >= cut
    expq = np.zeros(n)
    slope = np.zeros(n)
    for fr in np.unique(arr["frame"]):
        m = arr["frame"] == fr
        uc = arr["u_c"][m]
        b = _ols(np.column_stack([np.ones(uc.size), uc, uc ** 2]), arr["u_y"][m])
        expq[m] = b[0] + b[1] * uc + b[2] * uc ** 2
        slope[m] = b[1] + 2 * b[2] * uc
    resid = arr["u_y"] - expq
    implied = slope * shc
    g = np.asarray([r if r in ADJUSTED else STARTER for r in arr["role"]])
    out = {"model_up": "top fifth of the centered shift within (frame, fold)"}
    rng = np.random.default_rng(int(seed))
    for r in (STARTER,) + ADJUSTED + ("NONSTARTER",):
        m = up & (np.isin(g, ADJUSTED) if r == "NONSTARTER" else (g == r))
        ix = np.flatnonzero(m)
        if ix.size < 8:
            out[r] = {"n": int(ix.size), "status": "too few rows"}
            continue
        members = _clusters(arr["key"][ix])
        rs, im = resid[ix], implied[ix]
        draws = []
        for _ in range(int(B)):
            d = rng.integers(0, len(members), size=len(members))
            j = np.concatenate([members[q] for q in d])
            draws.append((rs[j].mean(), im[j].mean()))
        dr = np.asarray(draws)
        out[r] = {"n": int(ix.size), "mean_resid": _rnd(rs.mean()),
                  "mean_resid_ci95": [_rnd(np.quantile(dr[:, 0], 0.025)),
                                      _rnd(np.quantile(dr[:, 0], 0.975))],
                  "mean_implied": _rnd(im.mean()),
                  "realized_fraction": _rnd(rs.mean() / im.mean()) if im.mean() > 0 else None}
    return out


# ---------------------------------------------------------------------------
# A: the role term in the skill head (fitted on the head's own training rows)
# ---------------------------------------------------------------------------

def _train_terms(f: Fold, head: dict, train: list[dict], roles: list[str]) -> dict:
    """(u_c, u_y, e_skill, weight, role) on the head's has-block training rows (RT's
    transform applied, as the head was fitted)."""
    V5C, R5, H = _modules()
    import efv_v2_candidates as C
    tr_x = R5.rank_transform(train, SIDE)
    u_c = C._uc(tr_x)
    _u, u_y = H._percentiles(tr_x)
    idx = [i for i, r in enumerate(tr_x) if r["v2"]["has_block"]]
    rows = [tr_x[i] for i in idx]
    e = H.e_skill(head, rows)
    return {"u_c": u_c[idx], "u_y": u_y[idx], "e": e, "w": C._weights_of(rows),
            "role": np.asarray([roles[i] for i in idx]), "year": np.asarray(
                [int(tr_x[i]["decision_year"]) for i in idx])}


def role_term_fit(t: dict) -> dict:
    """A's head term: WLS u_y ~ 1 + u_c + e + I(SS) x e + I(R) x e + I(SS) + I(R)."""
    _V5C, _R5, H = _modules()
    g = np.asarray([role_group(r) for r in t["role"]])
    cols = [np.ones(t["e"].size), t["u_c"], t["e"]]
    names = ["intercept", "u_c", "e"]
    for r in ADJUSTED:
        if np.sum(g == r) >= 2:
            cols.append(t["e"] * (g == r))
            names.append(f"g|{r}")
    for r in ADJUSTED:
        if np.sum(g == r) >= 2:
            cols.append((g == r).astype(np.float64))
            names.append(f"d|{r}")
    Z = np.column_stack(cols)
    b = H._wls(Z, t["u_y"], t["w"], np.zeros(Z.shape[1]))
    coef = dict(zip(names, (float(x) for x in b)))
    return {"coef": coef, "a_uc": coef["u_c"], "n": int(t["e"].size),
            "n_by_role": {r: int(np.sum(g == r)) for r in ("REF",) + ADJUSTED}}


def role_term_apply(fit: dict, e: np.ndarray, roles) -> np.ndarray:
    """e_skill + (g_role x e_skill + d_role) / a_uc (0 added for the reference)."""
    c = fit["coef"]
    a = fit["a_uc"]
    out = np.asarray(e, dtype=np.float64).copy()
    if not (a > 0):
        return out
    for i, r in enumerate(roles):
        rg = role_group(r)
        if rg == "REF":
            continue
        out[i] += (c.get(f"g|{rg}", 0.0) * e[i] + c.get(f"d|{rg}", 0.0)) / a
    return out


# ---------------------------------------------------------------------------
# C: rate drivers normalized for outing length before the head
# ---------------------------------------------------------------------------

def _z_of(u: dict) -> float | None:
    b = u.get("bf_per_g")
    return math.log(b) if (b is not None and b > 0) else None


def workload_fit(rows: list[dict], zs: list) -> dict:
    """{key: (slope, mean z)} of every rate driver on log BF per appearance over the
    training rows carrying both (OLS with an intercept)."""
    out = {}
    for k in RATE_KEYS:
        xs, zz = [], []
        for r, z in zip(rows, zs):
            v = r["v2"].get(k)
            if v is None or z is None:
                continue
            xs.append(float(v))
            zz.append(float(z))
        if len(xs) < 20 or np.std(zz) == 0:
            continue
        x, z = np.asarray(xs), np.asarray(zz)
        b = _ols(np.column_stack([np.ones(z.size), z]), x)
        out[k] = (float(b[1]), float(z.mean()))
    return out


def workload_apply(rows: list[dict], zs: list, fit: dict) -> list[dict]:
    out = []
    for r, z in zip(rows, zs):
        if z is None:
            out.append(r)
            continue
        v2 = dict(r["v2"])
        for k, (b, zbar) in fit.items():
            if v2.get(k) is not None:
                v2[k] = float(v2[k]) - b * (z - zbar)
        out.append(dict(r, v2=v2))
    return out


def fit_skill(skill_rows: list[dict], skill_frame: str) -> dict | None:
    """The skill part of efv5_refit.fit_heads on its rows (RT's candidate columns, V2
    admission, alpha, the nested-CV lambda)."""
    V5C, R5, H = _modules()
    import efv_v2_candidates as C
    import efv_v3 as V3
    C.guard_training_rows(skill_rows, skill_frame)
    cfg = V3.base_config()
    ob_s = skill_frame == "lv"
    ab_s = ob_s and H.absence_admitted(SIDE)
    s_cands = V3.head_candidates(cfg, SIDE, "skill", ids_outcome_blind=ob_s, absence_admitted=ab_s)
    v2_keys, alpha_s = (), None
    if s_cands:
        v2_keys, _checks = C._admitted_keys_a(skill_rows, s_cands, target="u_y",
                                              has_block_only=True)
        if v2_keys:
            def fit_s(tr, a):
                return C._skill_fit_g(tr, v2_keys, a, C._v2_design(v2_keys))
            alpha_s = C._select_alpha_g(skill_rows, fit_s, C._skill_loss)
    sk_c = R5.refit_candidates(SIDE, "skill", dark=True)
    lam_s = V5C.select_lambda(skill_rows, "skill", v2_keys, alpha_s, sk_c)
    head = V5C.joint_skill(skill_rows, v2_keys, alpha_s, sk_c, lam_s)
    if head is not None:
        head["score_sd"] = C._score_sd(head, H.skill_training_rows(skill_rows))
        head["lam"] = lam_s
    return head


def c_fold(f: Fold, *, identity: bool = False, zs_train=None, zs_test=None) -> dict:
    """C on one fold: rank (RT), normalize (training coefficients), refit the skill head,
    e_skill on the test rows. identity=True skips the normalization (the parity check of
    the refit path against RT's own fold head)."""
    BT, _B4 = _tools()
    V5C, R5, H = _modules()
    tr_x = R5.rank_transform(f.train, SIDE)
    te_x = R5.rank_transform(f.test, SIDE)
    zs_tr = zs_train if zs_train is not None else [_z_of(u) for u in f.u_train]
    zs_te = zs_test if zs_test is not None else [_z_of(u) for u in f.u_test]
    fit = {}
    if not identity:
        fit = workload_fit(tr_x, zs_tr)
        tr_x = workload_apply(tr_x, zs_tr, fit)
        te_x = workload_apply(te_x, zs_te, fit)
    head = fit_skill(tr_x, BT.FRAME_KIND[f.fid])
    e = H.e_skill(head, te_x)
    pos = {k: i for i, k in enumerate(f.keys)}
    e_ols = np.asarray([e[pos[k]] for k in f.p["ols"]["keys"]])
    return {"e_s": e, "e_ols": e_ols, "workload": {k: [_rnd(b, 5), _rnd(m, 4)]
                                                   for k, (b, m) in fit.items()},
            "lam": V5C._lam_str((head or {}).get("lam")),
            "nonzero": [k for k, b in zip((head or {}).get("keys") or [],
                                          (head or {}).get("beta") or []) if b != 0.0]}


# ---------------------------------------------------------------------------
# DS-08 weights on a modified skill term (A and C)
# ---------------------------------------------------------------------------

def ds08_cross_fitted(folds: list[Fold], e_ols: dict) -> dict:
    """RT's weight rule (efv5_refit.cross_fitted) on the folds with e_skill replaced."""
    _V5C, R5, _H = _modules()
    pk = [{"fold_id": f.fold_id, "side": SIDE,
           "ols": dict(f.p["ols"], e_s=np.asarray(e_ols[f.fold_id]))} for f in folds]
    return R5.cross_fitted(pk)


def ds08_pooled(folds: list[Fold], e_ols: dict) -> dict:
    _V5C, R5, _H = _modules()
    pk = [{"fold_id": f.fold_id, "side": SIDE,
           "ols": dict(f.p["ols"], e_s=np.asarray(e_ols[f.fold_id]))} for f in folds]
    return R5.weights_from(pk)


def orders_e(folds: list[Fold], e_test: dict, wcf: dict) -> dict:
    def term(f):
        w = wcf[f.fold_id]
        return f.p["u_c"] + w["w_skill"] * np.asarray(e_test[f.fold_id]) + w["w_time"] * f.p["e_t"]
    return orders_of(folds, term)


# ---------------------------------------------------------------------------
# the ship rule (section 6)
# ---------------------------------------------------------------------------

def ship_reading(reads: dict) -> dict:
    out = {}
    for c in CANDIDATES:
        r = reads[c]
        lo = (r["pooled"].get("ci95") or [None, None])[0]
        per = {fid: r["frames"][fid].get("delta") for fid in FRAMES}
        rule1 = lo is not None and lo > 0
        rule2 = all(v is not None and v >= -MAX_TRAIL for v in per.values())
        out[c] = {"pooled_delta": r["pooled"].get("delta"), "pooled_ci95": r["pooled"].get("ci95"),
                  "frame_deltas": per, "rule_pooled_lower_above_zero": bool(rule1),
                  "rule_no_frame_trails": bool(rule2), "passes": bool(rule1 and rule2)}
    passing = [c for c in CANDIDATES if out[c]["passes"]]
    prepared = max(passing, key=lambda c: out[c]["pooled_delta"]) if passing else None
    return {"rule": ("pitcher rows; pooled over lv_dev and vm_dev, within Spearman minus Z with "
                     f"CI95 lower bound above 0, and minus Z >= -{MAX_TRAIL} on each frame"),
            "candidates": out, "passing": passing, "prepared": prepared}


# ---------------------------------------------------------------------------
# the planted-effect recovery check (section 5)
# ---------------------------------------------------------------------------

def _sim_rows(arr: dict, L: np.ndarray, orders: dict[str, np.ndarray]) -> dict:
    """Frame-keyed rows in the stat machinery's shape for one simulated label."""
    out = {fid: [] for fid in FRAMES}
    BT, _B4 = _tools()
    for i in range(arr["u_c"].size):
        g = {BT.CONS: float(arr["u_c"][i])}
        for name, o in orders.items():
            g[KEY[name]] = float(o[i])
        out[str(arr["frame"][i])].append(
            {"key": str(arr["key"][i]), "group": f"pit|{int(arr['fold'][i])}",
             "side": SIDE, "year": int(arr["fold"][i]), "grades": g,
             "outcome": {"war": float(L[i]), "contributor": False}})
    return out


def _sim_within(arr, L, o) -> float:
    rows = _sim_rows(arr, L, {"Z": o})
    vals, ns = [], []
    for fid in FRAMES:
        w = within_of(rows[fid], KEY["Z"])
        if w is not None:
            vals.append(w)
            ns.append(len(rows[fid]))
    return float(np.dot(vals, ns) / np.sum(ns))


def simulate(arr: dict, packs_arr: dict, *, target: float, reps: int = SIM_REPS,
             B: int = SIM_B, seed: int = SIM_SEED, log=print) -> dict:
    """NULL and PLANT on the real design (section 5). packs_arr holds the scored-row
    e_skill, e_time and fold id the B rule reads."""
    import efv_v2_model as H
    rng = np.random.default_rng(int(seed))
    n = arr["u_c"].size
    g = np.asarray([r if r in ADJUSTED else STARTER for r in arr["role"]])
    z_order = arr["u_c"] + arr["s"]
    grp = [f"{a}|{b}" for a, b in zip(arr["frame"], arr["fold"])]
    noise = rng.standard_normal((40, n))

    def within_at(sig):
        return float(np.mean([_sim_within(arr, arr["u_c"] + arr["s"] + sig * noise[j], z_order)
                              for j in range(8)]))
    lo, hi = 0.01, 5.0
    for _ in range(18):
        mid = math.sqrt(lo * hi)
        if within_at(mid) > target:
            lo = mid
        else:
            hi = mid
    sigma = math.sqrt(lo * hi)
    log(f"  sigma {sigma:.4f} (target within {target:.4f})")
    fold_ids = packs_arr["fold_id"]
    uniq = sorted(set(fold_ids))
    out = {"sigma": _rnd(sigma, 5), "target_within": _rnd(target), "reps": int(reps),
           "B": int(B), "seed": int(seed), "plants": {}}
    for plant, kmap in (("NULL", {STARTER: 1.0, SHORT: 1.0, RELIEF: 1.0}),
                        ("PLANT", {STARTER: 1.0, SHORT: PLANT_K, RELIEF: PLANT_K})):
        k = np.asarray([kmap[x] for x in g])
        rec = {"k": kmap, "rho": {STARTER: [], SHORT: [], RELIEF: [], "NONSTARTER": []},
               "b_pooled": [], "b_pass": 0, "b_lower_above_0": 0, "z_within": []}
        t0 = time.time()
        for _rep in range(int(reps)):
            L = arr["u_c"] + k * arr["s"] + sigma * rng.standard_normal(n)
            u_y = H.within_pct(L, grp)
            sh = realized_shares(arr["u_c"], u_y, arr["s"], arr["role"])
            for r in rec["rho"]:
                if sh.get(r) is not None:
                    rec["rho"][r].append(sh[r])
            # B's cross-fitted weights on the simulated label, then its order
            ws = np.zeros(n)
            wt = np.zeros(n)
            for fid in uniq:
                m = fold_ids != fid
                w = role_ols(arr["u_c"][m], u_y[m], packs_arr["e_s"][m], packs_arr["e_t"][m],
                             [role_group(x) for x in arr["role"][m]])
                mm = fold_ids == fid
                ws[mm] = [w[f"w|{role_group(x)}"] for x in arr["role"][mm]]
                wt[mm] = w["w|time"]
            b_order = arr["u_c"] + ws * packs_arr["e_s"] + wt * packs_arr["e_t"]
            rows = _sim_rows(arr, L, {"Z": z_order, "B": b_order})
            pd = pooled_delta(rows, KEY["B"], KEY["Z"], B=B, seed=int(rng.integers(1 << 30)))
            per = []
            for fid in FRAMES:
                a = within_of(rows[fid], KEY["B"])
                b = within_of(rows[fid], KEY["Z"])
                per.append(None if a is None or b is None else a - b)
            lo95 = (pd.get("ci95") or [None, None])[0]
            ok1 = lo95 is not None and lo95 > 0
            ok2 = all(v is not None and v >= -MAX_TRAIL for v in per)
            rec["b_pooled"].append(pd.get("delta"))
            rec["b_lower_above_0"] += int(ok1)
            rec["b_pass"] += int(ok1 and ok2)
        summ = {"k": kmap, "seconds": round(time.time() - t0, 1)}
        for r, v in rec["rho"].items():
            a = np.asarray(v)
            summ[f"rho_{r}"] = {"mean": _rnd(a.mean()), "sd": _rnd(a.std(ddof=1)),
                                "p05": _rnd(np.quantile(a, 0.05)), "p95": _rnd(np.quantile(a, 0.95))}
        bp = np.asarray([x for x in rec["b_pooled"] if x is not None])
        summ["b_pooled_delta"] = {"mean": _rnd(bp.mean(), 5), "sd": _rnd(bp.std(ddof=1), 5)}
        summ["b_pass_rate"] = _rnd(rec["b_pass"] / reps)
        summ["b_lower_above_0_rate"] = _rnd(rec["b_lower_above_0"] / reps)
        out["plants"][plant] = summ
        log(f"  {plant}: rho_nonstarter {summ['rho_NONSTARTER']['mean']}, "
            f"B pass rate {summ['b_pass_rate']} ({summ['seconds']} s)")
    pl, nu = out["plants"]["PLANT"], out["plants"]["NULL"]
    rec_ok = (pl["rho_NONSTARTER"]["mean"] is not None
              and abs(pl["rho_NONSTARTER"]["mean"] - PLANT_K) <= 0.15
              and pl["b_pass_rate"] >= 0.5 and nu["b_pass_rate"] <= 0.10)
    out["recovery_rule"] = ("under PLANT E1 recovers rho_nonstarter within 0.15 of "
                            f"{PLANT_K} on average and B passes in at least half the "
                            "replications; under NULL B passes in at most 10 percent")
    out["can_see_the_plant"] = bool(rec_ok)
    return out


# ---------------------------------------------------------------------------
# the live board (section 7) and the card label (section 9)
# ---------------------------------------------------------------------------

def live_board_rows(*, today: str, model: dict) -> tuple[list[dict], list[dict], int]:
    """(the served pitcher rows with RT's live candidate columns, the live matrix, the live
    read season)."""
    import efv_dataset as D
    import efv_v2_serve as S
    V5C, _R5, _H = _modules()
    live = json.loads(D.live_matrix_path(SIDE).read_text(encoding="utf-8"))
    rows = S.live_rows(SIDE, live, today=today)
    rows = S._with_live_candidates(SIDE, rows, live, model, today)
    season = int(V5C.live_read(today)["season"])
    return rows, live, season


def board_scores(rows: list[dict], order: np.ndarray) -> dict:
    """{player_key: {grade, rank, fv}} of one order on the live rows (DS-07 output map)."""
    _V5C, _R5, H = _modules()
    groups = [int(r["decision_year"]) for r in rows]
    fv = np.asarray([float(r["fv"]) for r in rows])
    grade = H.output_map(order, groups, fv)
    n = len(rows)
    ix = sorted(range(n), key=lambda i: (-order[i], rows[i]["player_key"]))
    rank = {i: k + 1 for k, i in enumerate(ix)}
    return {r["player_key"]: {"grade": float(grade[i]), "rank": rank[i], "fv": float(fv[i]),
                              "order_idx": float(order[i])} for i, r in enumerate(rows)}


def board_effect(rows: list[dict], usages: list[dict], before: dict, after: dict) -> dict:
    roles = {r["player_key"]: u["role"] for r, u in zip(rows, usages)}
    keys = sorted(before)
    mv = sorted([k for k in keys if roles.get(k) in ADJUSTED],
                key=lambda k: (-abs(after[k]["grade"] - before[k]["grade"]), k))
    by_class = {}
    for cl in ROLES:
        ks = [k for k in keys if roles.get(k) == cl]
        if not ks:
            continue
        by_class[cl] = {"n": len(ks),
                        "mean_abs_efv_minus_consensus": {
                            "before": _rnd(np.mean([abs(before[k]["grade"] - before[k]["fv"]) for k in ks]), 3),
                            "after": _rnd(np.mean([abs(after[k]["grade"] - after[k]["fv"]) for k in ks]), 3)},
                        "mean_efv_minus_consensus": {
                            "before": _rnd(np.mean([before[k]["grade"] - before[k]["fv"] for k in ks]), 3),
                            "after": _rnd(np.mean([after[k]["grade"] - after[k]["fv"] for k in ks]), 3)}}
    moved = np.asarray([abs(after[k]["grade"] - before[k]["grade"]) for k in keys])
    out = {"n": len(keys), "by_class": by_class,
           "moved_1_or_more": int(np.sum(moved >= 1.0 - 1e-9)),
           "max_move": _rnd(moved.max(), 1) if moved.size else None,
           "top20_short_or_relief": [
               {"player_key": k, "role": roles[k], "consensus": _rnd(before[k]["fv"], 1),
                "before": _rnd(before[k]["grade"], 1), "after": _rnd(after[k]["grade"], 1),
                "rank_before": before[k]["rank"], "rank_after": after[k]["rank"]}
               for k in mv[:20]]}
    if "brandon_clarke" in before:
        k = "brandon_clarke"
        out["brandon_clarke"] = {"role": roles.get(k), "consensus": _rnd(before[k]["fv"], 1),
                                 "before": _rnd(before[k]["grade"], 1), "after": _rnd(after[k]["grade"], 1),
                                 "rank_before": before[k]["rank"], "rank_after": after[k]["rank"]}
    return out


def roles_doc(rows_live: list[dict], *, season: int, generated_at: str | None = None) -> dict:
    """data/efv_pitcher_roles.json: the usage reading of every live board pitcher (the card
    label of section 9). A statement of usage; no grade reads it."""
    players = {}
    counts = {r: 0 for r in ROLES}
    for r in rows_live:
        u = usage(r.get("mlbam_id"), season)
        counts[u["role"]] += 1
        rec = {"mlbam": r.get("mlbam_id"), "role": u["role"]}
        if u["role"] not in (NO_LINE,):
            rec.update({"seasons": u["seasons"], "g": u["g"], "gs": u["gs"], "ip": u["ip"],
                        "bf": u["bf"], "gs_share": _rnd(u["gs_share"], 3),
                        "ip_per_g": _rnd(u["ip_per_g"], 2), "ip_per_gs": _rnd(u["ip_per_gs"], 2),
                        "bf_per_g": _rnd(u["bf_per_g"], 2)})
        lab = label_text(u)
        if lab:
            rec["label"] = lab
            rec["word"] = LABEL_WORD[u["role"]]
        players[r["player_key"]] = rec
    return {"schema": 1, "item": ITEM, "produced_by": TOOL, "doc": DOC,
            "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "read_season": int(season),
            "rule": {"min_g": MIN_G, "gs_share_cut": GS_SHARE_CUT, "ip_per_gs_cut": IP_PER_GS_CUT,
                     "window": ("the read season's affiliated minor league lines; the season "
                                "before is added when the read season has fewer than "
                                f"{MIN_G} appearances"),
                     "classes": {RELIEF: f"GS / G < {GS_SHARE_CUT}",
                                 SHORT: f"GS / G >= {GS_SHARE_CUT} and IP / GS < {IP_PER_GS_CUT}",
                                 STARTER: f"GS / G >= {GS_SHARE_CUT} and IP / GS >= {IP_PER_GS_CUT}",
                                 FEW: f"1 to {MIN_G - 1} appearances", NO_LINE: "no line"}},
            "note": ("a statement of minor league usage printed on the PROSPX card; it moves no "
                     "grade (docs/efv-v2/EFV_RELIEVER_ADJ.md section 9)"),
            "counts": counts, "players": players}


def export_roles(*, out: Path | None = None, today: str | None = None, log=print) -> dict:
    """Write the card label artifact for the live pitcher board (no model is scored)."""
    import efv_dataset as D
    import efv_v2_serve as S
    V5C, _R5, _H = _modules()
    today = today or date.today().isoformat()
    season = int(V5C.live_read(today)["season"])
    live = json.loads(D.live_matrix_path(SIDE).read_text(encoding="utf-8"))
    rows = [r for r in live if r.get("player_key") and S.gradeable(r)]
    doc = roles_doc(rows, season=season)
    p = Path(out or ROLES_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n"
    p.write_text(txt, encoding="utf-8", newline="\n")
    log(f"wrote {p} ({len(doc['players'])} pitchers, read season {season}: {doc['counts']})")
    return doc


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _code() -> dict:
    BT, _B4 = _tools()
    return {"commit": BT._commit(), "tool": TOOL, "tool_sha256": BT._sha(ROOT / TOOL),
            "efv5_refit_sha256": BT._sha(ROOT / "efv5_refit.py"),
            "doc": DOC, "doc_sha256": BT._sha(ROOT / DOC)}


def run(*, cache_dir: Path, work_dir: Path, B: int = BOOT_B, today: str | None = None,
        log=print, sim_reps: int = SIM_REPS) -> dict:
    """The registered read, once (sections 3 to 7)."""
    import efv_labels as L
    import efv_w2_popmle as PM
    BT, _B4 = _tools()
    V5C, R5, H = _modules()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    if not (R5.EFV_V5_REFIT_ON and PM.POP_REPAIR_ON):
        raise RuntimeError("the served model is not the re-fit RT; the read compares against it")
    today = today or date.today().isoformat()
    t0 = time.time()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    rt = json.loads(RT_FIT_PATH.read_text(encoding="utf-8"))
    wcf = rt["weights_cross_fitted"]["RT"][SIDE]
    log("loading the re-fit read's cached builds")
    b1, packs, cache_rec = load_cache(cache_dir)
    inp = b1["inp"]
    book = RoleBook()
    with R5.pop_repair(True):
        folds = build_folds(b1, packs, wcf, book, log=log)
        # ---- parity: Z must reproduce RT's committed pitcher read ---------------------
        oz = orders_of(folds, z_term)
        rows = {fid: rows_with(inp, fid, {"Z": oz}) for fid in FRAMES}
        parity = {}
        for fid in FRAMES:
            got = within_of(rows[fid], KEY["Z"])
            want = rt["frames"][fid]["per_side"][SIDE]["raters"][PARITY_KEY]["within"]
            parity[fid] = {"recomputed": _rnd(got, 5), "committed": want}
            if got is None or abs(got - want) > PARITY_TOL:
                raise RuntimeError(f"Z does not reproduce RT's committed pitcher read on {fid}: "
                                   f"{got} against {want}; nothing is read")
        log(f"Z reproduces RT's committed pitcher read: {parity}")
        # ---- class counts (outcome-blind) ---------------------------------------------
        counts = {}
        for fid in FRAMES:
            c = {r: 0 for r in ROLES}
            for f in folds:
                if f.fid != fid:
                    continue
                for r in ols_roles(f):
                    c[r] += 1
            counts[fid] = c
        # ---- E1 and E2 -------------------------------------------------------------------
        arr = _shift_arrays(folds)
        e1 = {"pooled": boot_shares(arr, B=B)}
        for fid in FRAMES:
            e1[fid] = boot_shares(arr, B=B, mask=arr["frame"] == fid)
        e2 = d4_measure(arr, B=B)
        log(f"E1 pooled: {json.dumps({k: v for k, v in e1['pooled'].items() if k not in ('B', 'seed', 'unit')})}")
        # ---- B -------------------------------------------------------------------------
        b_cf = b_cross_fitted(folds)
        ob = b_orders(folds, b_cf)
        b_prod = b_weights(folds)
        # ---- A -------------------------------------------------------------------------
        a_fits, a_test, a_ols, a_train_terms = {}, {}, {}, {}
        for f in folds:
            head = f.p["model"]["skill"]
            t = _train_terms(f, head, f.train, [u["role"] for u in f.u_train])
            a_train_terms[f.fold_id] = t
            fit = role_term_fit(t)
            a_fits[f.fold_id] = fit
            a_test[f.fold_id] = role_term_apply(fit, f.p["e_s"], [u["role"] for u in f.u_test])
            a_ols[f.fold_id] = role_term_apply(fit, f.p["ols"]["e_s"], ols_roles(f))
        a_cf = ds08_cross_fitted(folds, a_ols)
        oa = orders_e(folds, a_test, a_cf)
        # ---- C -------------------------------------------------------------------------
        c_cache = work_dir / "c_folds.pkl"
        if c_cache.exists():
            with c_cache.open("rb") as fh:
                c_res = pickle.load(fh)
            log("  cache hit c_folds.pkl")
        else:
            c_res = {}
            for f in folds:
                t1 = time.time()
                c_res[f.fold_id] = c_fold(f)
                log(f"  C {f.fold_id}: lambda {c_res[f.fold_id]['lam']} ({round(time.time() - t1, 1)} s)")
            with c_cache.open("wb") as fh:
                pickle.dump(c_res, fh, protocol=pickle.HIGHEST_PROTOCOL)
        c_cf = ds08_cross_fitted(folds, {k: v["e_ols"] for k, v in c_res.items()})
        oc = orders_e(folds, {k: v["e_s"] for k, v in c_res.items()}, c_cf)
        # ---- the read --------------------------------------------------------------------
        orders = {"Z": oz, "A": oa, "B": ob, "C": oc}
        rows = {fid: rows_with(inp, fid, orders) for fid in FRAMES}
        raters = {}
        for fid in FRAMES:
            raters[fid] = {name: _rnd(within_of(rows[fid], KEY[name]), 5) for name in orders}
            for k in (BT.CONS, "mlb_pipeline", "fangraphs"):
                raters[fid][k] = _rnd(within_of(rows[fid], k), 5)
        reads = {}
        for c in CANDIDATES:
            reads[c] = {"frames": {fid: frame_delta(rows[fid], KEY[c], KEY["Z"], B=B) for fid in FRAMES},
                        "pooled": pooled_delta(rows, KEY[c], KEY["Z"], B=B),
                        "vs_consensus": {fid: frame_delta(rows[fid], KEY[c], BT.CONS, B=B)
                                         for fid in FRAMES}}
            log(f"  {c}: pooled {reads[c]['pooled'].get('delta')} {reads[c]['pooled'].get('ci95')}, "
                f"lv {reads[c]['frames']['lv_dev'].get('delta')}, vm {reads[c]['frames']['vm_dev'].get('delta')}")
        z_vs_cons = {fid: frame_delta(rows[fid], KEY["Z"], BT.CONS, B=B) for fid in FRAMES}
        ship = ship_reading(reads)
        log(f"ship: passing {ship['passing']}, prepared {ship['prepared']}")
        # ---- the permuted-role null (A and B) -------------------------------------------
        rng = np.random.default_rng(PERM_SEED)
        perm = {"B": [], "A": []}
        rows_z = {fid: rows_with(inp, fid, {"Z": oz}) for fid in FRAMES}
        for name in ("B", "A"):
            for _k in range(PERM_K[name]):
                pt = {}
                for f in folds:
                    rl = [u["role"] for u in f.u_test]
                    pt[f.fold_id] = list(rng.permutation(rl))
                if name == "B":
                    roles_of = (lambda f, pt=pt: ols_roles(f, pt[f.fold_id]))
                    wc = b_cross_fitted(folds, roles_of)
                    o = b_orders(folds, wc, roles_test_of=lambda f, pt=pt: pt[f.fold_id])
                else:
                    e_t_, e_o_ = {}, {}
                    for f in folds:
                        t = dict(a_train_terms[f.fold_id])
                        rr = t["role"].copy()
                        for y in np.unique(t["year"]):
                            m = np.flatnonzero(t["year"] == y)
                            rr[m] = rng.permutation(rr[m])
                        t["role"] = rr
                        fit = role_term_fit(t)
                        e_t_[f.fold_id] = role_term_apply(fit, f.p["e_s"], pt[f.fold_id])
                        e_o_[f.fold_id] = role_term_apply(fit, f.p["ols"]["e_s"],
                                                          ols_roles(f, pt[f.fold_id]))
                    o = orders_e(folds, e_t_, ds08_cross_fitted(folds, e_o_))
                rp = {fid: [dict(c, grades=dict(c["grades"], **{KEY[name]: o[(fid, int(c["year"]), c["key"])]}))
                            for c in rows_z[fid]] for fid in FRAMES}
                perm[name].append(pooled_delta(rp, KEY[name], KEY["Z"], B=0).get("delta"))
            log(f"  permuted-role null {name}: {PERM_K[name]} draws")
        null = {}
        for name, v in perm.items():
            a = np.asarray([x for x in v if x is not None])
            real = reads[name]["pooled"].get("delta")
            null[name] = {"K": len(a), "seed": PERM_SEED, "mean": _rnd(a.mean(), 5),
                          "p95": _rnd(np.quantile(a, 0.95), 5), "max": _rnd(a.max(), 5),
                          "real": real, "real_percentile": _rnd(float(np.mean(a < real)), 3)
                          if real is not None else None}
        # ---- the sensitivity grid (B and E1; decides nothing) -----------------------------
        grid = []
        for window in WINDOWS:
            for gsc in GRID_GS:
                for ipc in GRID_IPGS:
                    kw = {"window": window, "gs_cut": gsc, "ipgs_cut": ipc}
                    rt_ = {f.fold_id: [book.usage_of(r, "test", **kw)["role"] for r in f.test]
                           for f in folds}
                    roles_of = (lambda f, rt_=rt_: ols_roles(f, rt_[f.fold_id]))
                    ar = _shift_arrays(folds, roles_of)
                    sh = realized_shares(ar["u_c"], ar["u_y"], ar["s"], ar["role"])
                    wc = b_cross_fitted(folds, roles_of)
                    o = b_orders(folds, wc, roles_test_of=lambda f, rt_=rt_: rt_[f.fold_id])
                    rp = {fid: [dict(c, grades=dict(c["grades"], **{KEY["B"]: o[(fid, int(c["year"]), c["key"])]}))
                                for c in rows_z[fid]] for fid in FRAMES}
                    cnt = {r: int(np.sum(ar["role"] == r)) for r in ROLES}
                    grid.append({"window": window, "gs_share_cut": gsc, "ip_per_gs_cut": ipc,
                                 "counts": cnt,
                                 "rho": {k: _rnd(v) for k, v in sh.items() if k != "n"},
                                 "b_pooled_delta": _rnd(pooled_delta(rp, KEY["B"], KEY["Z"], B=0).get("delta"), 5)})
        log(f"  grid: {len(grid)} cells")
        # ---- the planted-effect recovery check --------------------------------------------
        target = pooled_delta(rows, KEY["Z"], KEY["Z"], B=0).get("a")
        pa = {"e_s": np.concatenate([f.p["ols"]["e_s"] for f in folds]),
              "e_t": np.concatenate([f.p["ols"]["e_t"] for f in folds]),
              "fold_id": np.asarray([f.fold_id for f in folds for _k in f.p["ols"]["keys"]])}
        sim = simulate(arr, pa, target=float(target), reps=sim_reps, log=log)
        # ---- production fits and the board effect --------------------------------------
        prod_z = R5.production_models()[SIDE]
        live_rows_, _live, season = live_board_rows(today=today, model=prod_z)
        book.live_season = season
        usages_live = [book.usage_of(r, "live") for r in live_rows_]
        roles_live = [u["role"] for u in usages_live]
        e_live = H.e_skill(prod_z["skill"], live_rows_)
        e_tl = H.e_time(prod_z["timing"], live_rows_) if prod_z["w_time"] > 0 else np.zeros(len(live_rows_))
        u_c_live = H.within_pct([float(r["fv"]) for r in live_rows_],
                                [int(r["decision_year"]) for r in live_rows_])
        o_z = u_c_live + prod_z["w_skill"] * e_live + prod_z["w_time"] * e_tl
        before = board_scores(live_rows_, o_z)
        # served check: the recomputed board is the served one
        xfv = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))["by_player"]
        chk = (xfv.get("brandon_clarke") or {})
        served_check = {"brandon_clarke": {"served": chk.get("xfv_grade"),
                                           "served_rank": (chk.get("efv_v2") or {}).get("order_rank"),
                                           "recomputed": _rnd(before.get("brandon_clarke", {}).get("grade"), 2),
                                           "recomputed_rank": before.get("brandon_clarke", {}).get("rank")}}
        boards, prod = {}, {}
        # B
        wl = np.asarray([b_prod[f"w|{role_group(r)}"] for r in roles_live])
        o_b = u_c_live + wl * e_live + b_prod["w|time"] * e_tl
        boards["B"] = board_effect(live_rows_, usages_live, before, board_scores(live_rows_, o_b))
        prod["B"] = {"weights": {k: _rnd(v, 5) for k, v in b_prod.items() if k.startswith(("w|", "ratio|"))},
                     "coef": {k: _rnd(v, 5) for k, v in b_prod["coef"].items()}, "n": b_prod["n"]}
        # A
        tr_prod = list(b1["prod"][SIDE]) + list(b1["twins"][SIDE])
        u_prod = [book.usage_of(r, "train") for r in tr_prod]
        a_pf = role_term_fit(_train_terms(None, prod_z["skill"], tr_prod, [u["role"] for u in u_prod]))
        a_w = ds08_pooled(folds, a_ols)
        e_a = role_term_apply(a_pf, e_live, roles_live)
        o_a = u_c_live + a_w["w_skill"] * e_a + a_w["w_time"] * e_tl
        boards["A"] = board_effect(live_rows_, usages_live, before, board_scores(live_rows_, o_a))
        prod["A"] = {"role_term": {k: _rnd(v, 5) for k, v in a_pf["coef"].items()},
                     "n": a_pf["n"], "n_by_role": a_pf["n_by_role"],
                     "w_skill": _rnd(a_w["w_skill"], 5), "w_time": _rnd(a_w["w_time"], 5)}
        # C
        c_pcache = work_dir / "c_prod.pkl"
        if c_pcache.exists():
            with c_pcache.open("rb") as fh:
                c_prod = pickle.load(fh)
        else:
            tr_x = R5.rank_transform(tr_prod, SIDE)
            zs = [_z_of(u) for u in u_prod]
            wf = workload_fit(tr_x, zs)
            head_c = fit_skill(workload_apply(tr_x, zs, wf), "vm")
            c_prod = {"workload": wf, "head": head_c}
            with c_pcache.open("wb") as fh:
                pickle.dump(c_prod, fh, protocol=pickle.HIGHEST_PROTOCOL)
        c_w = ds08_pooled(folds, {k: v["e_ols"] for k, v in c_res.items()})
        live_c = workload_apply(live_rows_, [_z_of(u) for u in usages_live], c_prod["workload"])
        e_c = H.e_skill(c_prod["head"], live_c)
        o_c = u_c_live + c_w["w_skill"] * e_c + c_w["w_time"] * e_tl
        boards["C"] = board_effect(live_rows_, usages_live, before, board_scores(live_rows_, o_c))
        prod["C"] = {"workload": {k: [_rnd(b, 5), _rnd(m, 4)] for k, (b, m) in c_prod["workload"].items()},
                     "lam": V5C._lam_str((c_prod["head"] or {}).get("lam")),
                     "w_skill": _rnd(c_w["w_skill"], 5), "w_time": _rnd(c_w["w_time"], 5),
                     "skill_keys": (c_prod["head"] or {}).get("keys"),
                     "skill_beta": [_rnd(b, 5) for b in (c_prod["head"] or {}).get("beta") or []]}
        live_counts = {r: roles_live.count(r) for r in ROLES}
        clarke = None
        for r, u in zip(live_rows_, usages_live):
            if r["player_key"] == "brandon_clarke":
                clarke = u
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
           "role": "development", "adjudicates": False, "doc": DOC,
           "owner_decision": OWNER_DECISION, "label": rt.get("label"), "code": _code(),
           "comparator": "Z: the served re-fit RT (pitchers), recomputed from its committed read",
           "cache": cache_rec, "parity": parity,
           "classification": {"min_g": MIN_G, "gs_share_cut": GS_SHARE_CUT,
                              "ip_per_gs_cut": IP_PER_GS_CUT, "window": "rule",
                              "counts_scored_rows": counts, "counts_live": live_counts,
                              "live_read_season": season, "brandon_clarke": clarke},
           "E1_realized_share": e1, "E2_d4": e2,
           "raters_within": raters, "reads": reads, "z_vs_consensus": z_vs_cons,
           "weights": {"B_cross_fitted": {k: {kk: _rnd(vv, 4) for kk, vv in v.items() if kk.startswith(("w|", "ratio|"))}
                                          for k, v in b_cf.items()},
                       "A_role_term_by_fold": {k: {"coef": {kk: _rnd(vv, 5) for kk, vv in v["coef"].items()},
                                                   "n": v["n"], "n_by_role": v["n_by_role"]}
                                               for k, v in a_fits.items()},
                       "A_cross_fitted": {k: {kk: _rnd(vv, 4) for kk, vv in v.items()} for k, v in a_cf.items()},
                       "C_cross_fitted": {k: {kk: _rnd(vv, 4) for kk, vv in v.items()} for k, v in c_cf.items()},
                       "C_by_fold": {k: {"lam": v["lam"], "workload": v["workload"],
                                         "nonzero": v["nonzero"]} for k, v in c_res.items()}},
           "ship": ship, "permuted_role_null": null, "grid": grid, "recovery": sim,
           "production": prod, "board": boards, "served_check": served_check,
           "elapsed_s": round(time.time() - t0, 1)}
    BT.write_doc(doc, FIT_PATH)
    log(f"wrote {FIT_PATH} ({round(time.time() - t0, 1)} s)")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="the registered read, once")
    ap.add_argument("--cache", default=None, help="the re-fit read's cache directory")
    ap.add_argument("--work", default=None, help="a scratch directory for this read's builds")
    ap.add_argument("--B", type=int, default=None)
    ap.add_argument("--export-roles", action="store_true",
                    help="write data/efv_pitcher_roles.json (the card's usage label)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)
    if a.export_roles:
        export_roles(out=Path(a.out) if a.out else None, log=log)
        return 0
    if a.run:
        if FIT_PATH.exists():
            log(f"refused: {FIT_PATH} exists; the registered read runs once")
            return 2
        if not (a.cache and a.work):
            log("refused: --cache (the re-fit read's builds) and --work are needed")
            return 2
        run(cache_dir=Path(a.cache), work_dir=Path(a.work), B=BOOT_B if a.B is None else int(a.B),
            log=log)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
