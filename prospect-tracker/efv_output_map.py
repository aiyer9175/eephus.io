# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV output map test (EFV_OUTPUT_MAP_TEST).

docs/efv-v2/EFV_OUTPUT_MAP_TEST.md, registered alone before this module existed (owner
decision EW3-35, 2026-10-16). The served grade is the consensus value of the side's list-year
group at the rank of the order index (efv_v2_model.output_map, map A). This read tests, once
and on the development frames only, three maps that carry the order's shift onto the grade
scale instead (B: through the local slope of the group's smoothed consensus quantile
function; C: a density-damped rank map; D: the smoothed quantile function evaluated at the
order index), on grade MAGNITUDE: the squared error of the implied value
kappa_G x T_side(grade) against the frame's label, T a committed per-side outcome curve read
as it stands, kappa_G one scalar per (frame, side, fold). Comparators: Z (consensus itself)
and N_X (a rank map whose shift is scaled to move as little as X). The within Spearman of each
map's ordering is a guard. Planted power and size close the read.

No model is refitted (the served RT heads and weights build the order index); no reserved row
is built or scored; nothing is grouped, counted or averaged by consensus-FV level (the groups
are side, frame and fold); no grade-to-WAR table is fitted.

    python efv_output_map.py --check --cache <re-fit cache> --work <scratch dir>
    python efv_output_map.py --run --cache <re-fit cache> --work <scratch dir>
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

import efv5_refit as RF
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv5"
OUT_PATH = LAB_DIR / "efv_output_map_test.json"
CURVES_PATH = DATA_DIR / "fv_outcome_curves.json"
POOLED_PATH = DATA_DIR / "fv_outcome_curves_pooled.json"
XFV_PATH = DATA_DIR / "xfv.json"
REREAD_PATH = LAB_DIR / "efv5_refit_pit_reread.json"
DOC = "docs/efv-v2/EFV_OUTPUT_MAP_TEST.md"
TOOL = "efv_output_map.py"
ITEM = "EFV_OUTPUT_MAP_TEST"

#: Registered constants (the document, sections 2 to 6).
SEED = 20261016
B_MAIN = 2000
K_PLANT = 100
B_PLANT = 1000
H_SMOOTH = 0.01
H_SLOPE = 0.02
GUARD = -0.002
SIZE_MAX = 0.10
POWER_MIN = 0.80
HOLM_ALPHA = 0.05
BISECT_STEPS = 60
PARITY_TOL = 1e-4
CANDIDATES: tuple[str, ...] = ("B", "C", "D")
MAPS: tuple[str, ...] = ("A", "B", "C", "D", "D0", "Z")
INSTRUMENTS: tuple[str, ...] = ("perside", "pooled", "clemens")
PRIMARY = "perside"
NAMED = "sebastian_walcott"
TOP_N = 50


# ---------------------------------------------------------------------------
# the maps (section 2), one group at a time
# ---------------------------------------------------------------------------

def smoothed_quantile(c, h: float = H_SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """(t, v~): the group's sorted consensus values at positions r / n, smoothed by a
    symmetric truncated moving average of half-width k = max(1, round(h x n)) ranks (k = 0
    when h is 0), then a running maximum so the curve never falls."""
    v = np.sort(np.asarray(c, dtype=np.float64))
    n = v.size
    t = np.arange(1, n + 1, dtype=np.float64) / n
    if n == 0 or h <= 0:
        return t, v.copy()
    k = max(1, int(round(h * n)))
    cs = np.concatenate([[0.0], np.cumsum(v)])
    r = np.arange(n)
    kr = np.minimum(np.minimum(k, r), n - 1 - r)
    lo, hi = r - kr, r + kr + 1
    sm = (cs[hi] - cs[lo]) / (hi - lo)
    return t, np.maximum.accumulate(sm)


def q_eval(t: np.ndarray, v: np.ndarray, u) -> np.ndarray:
    """Q(u): linear between (t_r, v_r), held at the end values outside [t_1, t_n]."""
    return np.interp(np.asarray(u, dtype=np.float64), t, v)


def local_slope(t: np.ndarray, v: np.ndarray, u, h: float = H_SLOPE) -> np.ndarray:
    """D(u): grade points per unit of percentile over [u - h, u + h] cut to [t_1, t_n]."""
    u = np.asarray(u, dtype=np.float64)
    hi = np.minimum(u + h, t[-1])
    lo = np.maximum(u - h, t[0])
    width = hi - lo
    out = np.zeros(u.size)
    ok = width > 0
    out[ok] = (q_eval(t, v, hi[ok]) - q_eval(t, v, lo[ok])) / width[ok]
    return out


def map_group(name: str, c, o, *, m: float | None = None) -> np.ndarray:
    """Map `name` on one group: c the group's consensus values (the served map's value
    set), o the served order index. `m` scales the shift of the null comparator N."""
    c = np.asarray(c, dtype=np.float64)
    o = np.asarray(o, dtype=np.float64)
    n = c.size
    if n == 0:
        return np.zeros(0)
    one = [0] * n
    u = H.within_pct(c, one)
    s = o - u
    if name == "A":
        return H.output_map(o, one, c)
    if name == "Z":
        return c.copy()
    if name == "N":
        return H.output_map(u + float(m) * s, one, c)
    if name == "D0":
        t, v = smoothed_quantile(c, 0.0)
        return q_eval(t, v, o)
    t, v = smoothed_quantile(c, H_SMOOTH)
    if name == "D":
        return q_eval(t, v, o)
    d = local_slope(t, v, u)
    if name == "B":
        return np.clip(c + s * d, c.min(), c.max())
    if name == "C":
        pos = d[d > 0]
        lam = np.ones(n)
        if pos.size:
            d_med = float(np.median(pos))
            big = d > 0
            lam[big] = np.minimum(1.0, d_med / d[big])
        return H.output_map(u + lam * s, one, c)
    raise ValueError(f"unknown map {name!r}")


def lex_score(g, o) -> np.ndarray:
    """A score ordering rows by (g, then o), equal pairs sharing their mean rank: the rank
    guard reads each map's own ordering with ties broken by the served order."""
    g = np.asarray(g, dtype=np.float64)
    o = np.asarray(o, dtype=np.float64)
    idx = np.lexsort((o, g))
    rank = np.empty(g.size)
    rank[idx] = np.arange(1, g.size + 1, dtype=np.float64)
    pairs: dict = {}
    for i in range(g.size):
        pairs.setdefault((g[i], o[i]), []).append(i)
    for ix in pairs.values():
        if len(ix) > 1:
            rank[ix] = rank[ix].mean()
    return rank


def movement(groups: list[tuple[np.ndarray, np.ndarray]], name: str, *, m: float | None = None) -> float:
    """Mean abs(g - c) of a map over the rows of every group given (outcome-free)."""
    tot = n = 0.0
    for c, o in groups:
        g = map_group(name, c, o, m=m)
        tot += float(np.abs(g - c).sum())
        n += c.size
    return tot / n if n else 0.0


def matched_m(groups: list[tuple[np.ndarray, np.ndarray]], target: float, *,
              steps: int = BISECT_STEPS) -> dict:
    """m in [0, 1] with the rank map's movement at u + m x s equal to `target`; m = 1 when
    the rank map at full shift moves no more than the target."""
    full = movement(groups, "N", m=1.0)
    if full <= target:
        return {"m": 1.0, "movement": full, "target": target, "capped": True}
    lo, hi = 0.0, 1.0
    for _ in range(int(steps)):
        mid = 0.5 * (lo + hi)
        if movement(groups, "N", m=mid) < target:
            lo = mid
        else:
            hi = mid
    m = 0.5 * (lo + hi)
    return {"m": m, "movement": movement(groups, "N", m=m), "target": target, "capped": False}


# ---------------------------------------------------------------------------
# the instruments (section 4): committed curves, read as they stand
# ---------------------------------------------------------------------------

def instruments() -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    """{instrument: {side: (knots, values)}}; evaluated linearly, flat past the end knots."""
    cur = json.loads(CURVES_PATH.read_text(encoding="utf-8"))
    pooled = json.loads(POOLED_PATH.read_text(encoding="utf-8"))["curve"]
    out: dict = {"perside": {}, "pooled": {}, "clemens": {}}
    for side in F.SIDES:
        w = cur["curves"][side]["war"]
        out["perside"][side] = (np.asarray(w["knots"], float), np.asarray(w["value"], float))
        out["pooled"][side] = (np.asarray(pooled["knots"], float), np.asarray(pooled["value"], float))
        tab = cur["conversions"]["clemens_2026"][f"table_{side}"]
        kv = sorted((float(k), float(v)) for k, v in tab.items())
        kv = [(20.0, 0.0)] + kv
        out["clemens"][side] = (np.asarray([k for k, _ in kv]), np.asarray([v for _, v in kv]))
    return out


def t_eval(curve: tuple[np.ndarray, np.ndarray], g) -> np.ndarray:
    return np.interp(np.asarray(g, dtype=np.float64), curve[0], curve[1])


# ---------------------------------------------------------------------------
# the paired statistics (section 4)
# ---------------------------------------------------------------------------

def boot_draws(keys: list, *, B: int, seed: int) -> list[np.ndarray]:
    """B player-clustered resamples of the rows (source_backtest's own resampler)."""
    import source_backtest as SB
    ids: dict = {}
    for k in keys:
        ids.setdefault(k, len(ids))
    order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
    rng = np.random.default_rng(int(seed))
    return [SB._cluster_draw(np, rng, order, starts, lens) for _ in range(int(B))]


def paired_mean(d: np.ndarray, draws: list[np.ndarray]) -> dict:
    """mean(d) with the paired cluster CI95 and the one-sided p (share of draws at or below 0)."""
    d = np.asarray(d, dtype=np.float64)
    arr = np.asarray([float(d[ix].mean()) for ix in draws if ix.size])
    q = np.quantile(arr, [0.025, 0.975])
    return {"delta": round(float(d.mean()), 5), "ci95": [round(float(q[0]), 5), round(float(q[1]), 5)],
            "p_le_0": round(float((arr <= 0).mean()), 5), "sd": round(float(arr.std(ddof=1)), 5),
            "n": int(d.size), "B_used": int(arr.size)}


def lb_only(d: np.ndarray, draws: list[np.ndarray]) -> float:
    arr = np.asarray([float(d[ix].mean()) for ix in draws if ix.size])
    return float(np.quantile(arr, 0.025))


def calib_slope(y: np.ndarray, v: np.ndarray, draws: list[np.ndarray]) -> dict:
    def slope(ix):
        vv, yy = v[ix], y[ix]
        var = float(vv.var())
        return float(((vv - vv.mean()) * (yy - yy.mean())).mean() / var) if var > 0 else np.nan
    full = slope(np.arange(y.size))
    arr = np.asarray([slope(ix) for ix in draws if ix.size])
    arr = arr[np.isfinite(arr)]
    q = np.quantile(arr, [0.025, 0.975])
    return {"slope": round(full, 4), "ci95": [round(float(q[0]), 4), round(float(q[1]), 4)]}


def holm(pvals: dict[str, float], alpha: float = HOLM_ALPHA) -> dict[str, bool]:
    """Holm's step-down: True where the hypothesis is rejected."""
    order = sorted(pvals, key=lambda k: (pvals[k], k))
    m = len(order)
    out = {k: False for k in order}
    for j, k in enumerate(order):
        if pvals[k] <= alpha / (m - j):
            out[k] = True
        else:
            break
    return out


# ---------------------------------------------------------------------------
# the development rows (section 3)
# ---------------------------------------------------------------------------

def _tools():
    return RF._tools()


def load_cache(cache_dir: Path) -> tuple[list[dict], dict]:
    cache_dir = Path(cache_dir)
    _tools()
    with (cache_dir / "packs_RT.pkl").open("rb") as fh:
        packs, _rec = pickle.load(fh)
    with (cache_dir / "build1.pkl").open("rb") as fh:
        b1 = pickle.load(fh)
    return packs, b1


def check_reserved(b1: dict) -> None:
    BT, _B4 = _tools()
    for fid in BT.FRAMES_DEV:
        for side in F.SIDES:
            for f in b1["inp"].frames[fid]["by_side"][side]:
                if fid.startswith("lv") and int(f) in F.RESERVED_LV:
                    raise F.ReservedFrameError("a reserved list vintage reached the read")
                if fid.startswith("vm") and int(f) >= F.R_VM_FIRST_DEBUT_YEAR:
                    raise F.ReservedFrameError("a reserved debut cohort reached the read")


def check_receipts(packs: list[dict], fit: dict) -> dict:
    """Q1: each cached fold model's nonzero skill list equals the fit artifact's receipt."""
    rec = fit["fold_receipts"]["RT"]
    out = {}
    for p in packs:
        head = (p.get("model") or {}).get("skill") or {}
        got = [k for k, b in zip(head.get("keys") or [], head.get("beta") or []) if b != 0.0]
        want = rec[p["fold_id"]]["skill_nonzero"]
        if got != want:
            raise RuntimeError(f"Q1: {p['fold_id']}: cached nonzero keys differ from the receipt")
        out[p["fold_id"]] = len(got)
    return out


def served_weights() -> dict[str, dict[str, float]]:
    w = json.loads(RF.WEIGHTS_PATH.read_text(encoding="utf-8"))["weights"]
    return {s: {"w_skill": float(w[s]["w_skill"]), "w_time": float(w[s]["w_time"])} for s in F.SIDES}


def fold_groups(packs: list[dict], b1: dict, weights: dict) -> dict[str, dict]:
    """{fold id: {"side", "fid", "fold", "keys", "c", "u", "o"}} over each fold's TEST rows
    (the group the map runs on), orders at the given per-side weights."""
    inp = b1["inp"]
    out = {}
    for p in packs:
        blk = inp.frames[p["fid"]]["by_side"][p["side"]][int(p["fold"])]
        keys = [r["player_key"] for r in blk["test"]]
        if keys != list(p["keys"]):
            raise RuntimeError(f"{p['fold_id']}: the test rows differ from the cached pack")
        c = np.asarray([float(r["fv"]) for r in blk["test"]])
        u = H.within_pct(c, [0] * c.size)
        if c.size and float(np.max(np.abs(u - np.asarray(p["u_c"])))) > 1e-12:
            raise RuntimeError(f"{p['fold_id']}: u_c of the pack is not within_pct of the test fv")
        w = weights[p["side"]] if "w_skill" not in weights else weights
        o = u + w["w_skill"] * np.asarray(p["e_s"]) + w["w_time"] * np.asarray(p["e_t"])
        out[p["fold_id"]] = {"side": p["side"], "fid": p["fid"], "fold": int(p["fold"]),
                             "keys": keys, "c": c, "u": u, "o": o,
                             "e_s": np.asarray(p["e_s"]), "e_t": np.asarray(p["e_t"])}
    return out


def scored_rows(b1: dict, groups: dict[str, dict]) -> tuple[list[dict], int]:
    """The scored rows of both frames that sit in a fold's test rows: key, side, fid, fold id,
    group (frame|side|year), label, contributor and the row's index in its fold group.
    Returns (rows, rows whose test fv differs from the scored consensus grade)."""
    BT, _B4 = _tools()
    inp = b1["inp"]
    out, differ = [], 0
    for fold_id, g in groups.items():
        pos = {k: i for i, k in enumerate(g["keys"])}
        for c in inp.scored(g["fid"]):
            if c["side"] != g["side"] or int(c["year"]) != g["fold"] or c["key"] not in pos:
                continue
            i = pos[c["key"]]
            if abs(float(c["grades"][BT.CONS]) - float(g["c"][i])) > 1e-9:
                differ += 1
            out.append({"key": c["key"], "side": g["side"], "fid": g["fid"], "fold_id": fold_id,
                        "year": int(c["year"]), "group": f"{g['fid']}|{c['group']}",
                        "y": float(c["outcome"]["war"]),
                        "contributor": bool(c["outcome"]["contributor"]),
                        "cons_scored": float(c["grades"][BT.CONS]), "_i": i})
    return out, differ


def all_maps(groups: dict[str, dict], m_by: dict[str, dict[str, float]] | None = None) -> dict[str, dict[str, np.ndarray]]:
    """{fold id: {map: grades over the fold's test rows}}; m_by {side: {candidate: m}} adds
    the null comparators N_<candidate>."""
    out = {}
    for fold_id, g in groups.items():
        mp = {name: map_group(name, g["c"], g["o"]) for name in MAPS}
        if m_by:
            for x, m in (m_by.get(g["side"]) or {}).items():
                mp[f"N_{x}"] = map_group("N", g["c"], g["o"], m=m)
        out[fold_id] = mp
    return out


def side_groups(groups: dict[str, dict], side: str) -> list[tuple[np.ndarray, np.ndarray]]:
    return [(g["c"], g["o"]) for g in groups.values() if g["side"] == side]


def matched_nulls(groups: dict[str, dict]) -> dict[str, dict[str, dict]]:
    """Per side and candidate, the m of N_X (outcome-free, on the development test rows)."""
    out: dict = {}
    for side in F.SIDES:
        sg = side_groups(groups, side)
        out[side] = {"A_movement": movement(sg, "A")}
        for x in CANDIDATES:
            out[side][x] = matched_m(sg, movement(sg, x))
    return out


# ---------------------------------------------------------------------------
# parity on published numbers (Q2) and on the live board (Q4)
# ---------------------------------------------------------------------------

def _within_rows(rows: list[dict], score: np.ndarray) -> list[dict]:
    BT, _B4 = _tools()
    return [{"key": r["key"], "side": r["side"], "group": r["group"],
             "grades": {"_s": float(score[j]), BT.CONS: r["cons_scored"]},
             "outcome": {"war": r["y"], "contributor": r["contributor"]}}
            for j, r in enumerate(rows)]


def parity_q2(packs: list[dict], b1: dict, fit: dict) -> dict:
    """Q2: the cross-fitted RT orders reproduce the fit artifact's within per frame and side;
    the served pitcher weights reproduce the pitcher re-read's pooled within."""
    cf = fit["weights_cross_fitted"]["RT"]
    out = {}
    for side in F.SIDES:
        for fid in ("lv_dev", "vm_dev"):
            mine = [p for p in packs if p["side"] == side and p["fid"] == fid]
            gw = {}
            for p in mine:
                w = cf[side][p["fold_id"]]
                gw.update(fold_groups([p], b1, {"w_skill": w["w_skill"], "w_time": w["w_time"]}))
            rows, _d = scored_rows(b1, gw)
            score = np.asarray([gw[r["fold_id"]]["o"][r["_i"]] for r in rows])
            got = RF.within_of(_within_rows(rows, score), "_s")["within"]
            want = fit["frames"][fid]["per_side"][side]["raters"]["efv_v5_rt"]["within"]
            if got is None or abs(got - want) > PARITY_TOL:
                raise RuntimeError(f"Q2: {fid} {side} within {got} against the artifact's {want}")
            out[f"{fid}|{side}"] = {"within": round(got, 5), "artifact": want}
    sw = served_weights()
    pit = [p for p in packs if p["side"] == "pit"]
    gp = fold_groups(pit, b1, sw)
    rows, _d = scored_rows(b1, gp)
    score = np.asarray([gp[r["fold_id"]]["o"][r["_i"]] for r in rows])
    got = RF.within_of(_within_rows(rows, score), "_s")["within"]
    want = json.loads(REREAD_PATH.read_text(encoding="utf-8"))["read"]["both"]["raters"]["rr_served"]
    if got is None or abs(got - want) > PARITY_TOL:
        raise RuntimeError(f"Q2: pitcher served-weight within {got} against the re-read's {want}")
    out["both|pit|served"] = {"within": round(got, 5), "artifact": want}
    return out


def live_board() -> dict[str, dict]:
    """{side: {"keys", "c", "u", "o", "grade", "u_served"}} from the served board and the live
    matrices' consensus_fv_raw (the served map's value set)."""
    import efv_dataset as D
    xfv = json.loads(XFV_PATH.read_text(encoding="utf-8"))["by_player"]
    out = {}
    for side in F.SIDES:
        raw = {r["player_key"]: r for r in json.loads(D.live_matrix_path(side).read_text(encoding="utf-8"))
               if r.get("player_key")}
        keys, c, us, o, gr = [], [], [], [], []
        for k, v in xfv.items():
            e = v.get("efv_v2")
            if not e or e.get("group", [None])[0] != side:
                continue
            keys.append(k)
            c.append(float(raw[k]["consensus_fv_raw"]))
            us.append(float(e["u_c"]))
            o.append(float(e["order_idx"]))
            gr.append(float(v["xfv_grade"]))
        c = np.asarray(c)
        out[side] = {"keys": keys, "c": c, "u": H.within_pct(c, [0] * c.size),
                     "u_served": np.asarray(us), "o": np.asarray(o), "grade": np.asarray(gr)}
    return out


def parity_q4(board: dict[str, dict]) -> dict:
    out = {}
    for side, b in board.items():
        du = float(np.max(np.abs(b["u"] - b["u_served"])))
        ga = map_group("A", b["c"], b["o"])
        dg = float(np.max(np.abs(ga - b["grade"])))
        if du > 1e-6 or dg > 0.05 + 1e-9:
            raise RuntimeError(f"Q4: {side} live board does not reproduce (u {du}, grade {dg})")
        out[side] = {"rows": len(b["keys"]), "max_abs_u": du, "max_abs_grade_vs_served_one_decimal": dg}
    return out


def _r(x, k=2):
    return None if x is None else round(float(x), k)


def board_effect(board: dict[str, dict]) -> dict:
    """Section 8, outcome-free, for every map."""
    out = {}
    for side, b in board.items():
        c, o, keys = b["c"], b["o"], b["keys"]
        n = c.size
        gm = {name: map_group(name, c, o) for name in ("A", "B", "C", "D", "D0")}
        cons_top = np.lexsort((-o, -c))[:TOP_N]
        blk = {"rows": n, "top_value": _r(c.max(), 2)}
        named = keys.index(NAMED) if NAMED in keys else None
        for name, g in gm.items():
            top = np.lexsort((-o, -g))[:TOP_N]
            rank_of = np.empty(n, dtype=int)
            rank_of[np.lexsort((-o, -g))] = np.arange(1, n + 1)
            mv = g - gm["A"]
            e = {"mean_abs_minus_consensus": _r(np.abs(g - c).mean(), 3),
                 "mean_minus_consensus": _r((g - c).mean(), 3),
                 "rows_moving_3_or_more_vs_A": int((np.abs(mv) >= 3.0).sum()),
                 "largest_up_vs_A": _r(mv.max(), 2), "largest_down_vs_A": _r(mv.min(), 2),
                 "rows_at_top_value": int((g >= c.max() - 1e-9).sum()),
                 "top50_by_consensus": {"mean_grade": _r(g[cons_top].mean(), 2),
                                        "mean_A": _r(gm["A"][cons_top].mean(), 2),
                                        "mean_consensus": _r(c[cons_top].mean(), 2)},
                 "top50_by_map": {"mean_grade": _r(g[top].mean(), 2),
                                  "mean_A": _r(gm["A"][top].mean(), 2),
                                  "mean_consensus": _r(c[top].mean(), 2),
                                  "rows": [{"player_key": keys[i], "grade": _r(g[i], 1),
                                            "A": _r(gm["A"][i], 1), "consensus": _r(c[i], 1)}
                                           for i in top]}}
            if named is not None:
                e["named"] = {"player_key": NAMED, "grade": _r(g[named], 1), "A": _r(gm["A"][named], 1),
                              "consensus": _r(c[named], 1), "rank_by_map": int(rank_of[named]),
                              "consensus_rank": int(1 + (c > c[named]).sum())}
            blk[name] = e
        out[side] = blk
    return out


# ---------------------------------------------------------------------------
# the read (sections 4 to 6)
# ---------------------------------------------------------------------------

def implied(rows: list[dict], grades: dict[str, dict[str, np.ndarray]], inst: dict, name: str) -> tuple[np.ndarray, dict]:
    """v = kappa_G x T_side(g) of map `name` on the rows, kappa_G from the zero comparator."""
    by: dict = {}
    for j, r in enumerate(rows):
        by.setdefault(r["fold_id"], []).append(j)
    v = np.zeros(len(rows))
    kappa = {}
    for fold_id, ix in by.items():
        ix = np.asarray(ix)
        side = rows[ix[0]]["side"]
        cur = inst[side]
        ii = np.asarray([rows[j]["_i"] for j in ix])
        tz = t_eval(cur, grades[fold_id]["Z"][ii])
        y = np.asarray([rows[j]["y"] for j in ix])
        k = float(y.sum() / tz.sum())
        kappa[fold_id] = k
        v[ix] = k * t_eval(cur, grades[fold_id][name][ii])
    return v, kappa


def side_read(rows: list[dict], grades: dict, inst_all: dict, *, B: int, seed: int) -> dict:
    """Every statistic of section 4 on one side's rows (both frames and each frame)."""
    BT, _B4 = _tools()
    y = np.asarray([r["y"] for r in rows])
    keys = [r["key"] for r in rows]
    fids = np.asarray([r["fid"] for r in rows])
    draws = {"both": boot_draws(keys, B=B, seed=seed)}
    idx = {"both": np.arange(len(rows))}
    for f in ("lv_dev", "vm_dev"):
        ix = np.flatnonzero(fids == f)
        idx[f] = ix
        draws[f] = boot_draws([keys[j] for j in ix], B=B, seed=seed)
    names = [n for n in next(iter(grades.values())) if not n.startswith("_")]
    out: dict = {"n": {k: int(v.size) for k, v in idx.items()}, "kappa": {}, "loss": {}, "deltas": {}}
    for iname in INSTRUMENTS:
        inst = inst_all[iname]
        v, kappa = {}, None
        for name in names:
            v[name], kappa = implied(rows, grades, inst, name)
        out["kappa"][iname] = {k: round(x, 5) for k, x in kappa.items()}
        se = {n: (y - v[n]) ** 2 for n in names}
        ae = {n: np.abs(y - v[n]) for n in names}
        out["loss"][iname] = {f: {n: {"mse": round(float(se[n][ix].mean()), 4),
                                      "mae": round(float(ae[n][ix].mean()), 4)} for n in names}
                              for f, ix in idx.items()}
        blk = {}
        pairs = [(x, "A") for x in CANDIDATES + ("D0",)] + [(x, f"N_{x}") for x in CANDIDATES
                                                           if f"N_{x}" in names]
        pairs += [("A", "Z")] + [(x, "Z") for x in CANDIDATES]
        for a, b in pairs:
            key = f"{a}_vs_{b}"
            blk[key] = {}
            for f, ix in idx.items():
                sub = {"mse": paired_mean(se[b][ix] - se[a][ix], draws[f]),
                       "mae": paired_mean(ae[b][ix] - ae[a][ix], draws[f])}
                if iname != PRIMARY:
                    sub = {"mse": {"delta": sub["mse"]["delta"], "ci95": sub["mse"]["ci95"]},
                           "mae": {"delta": sub["mae"]["delta"]}}
                blk[key][f] = sub
        out["deltas"][iname] = blk
        if iname == PRIMARY:
            out["calibration"] = {n: calib_slope(y, v[n], draws["both"]) for n in names}
            out["_v"] = v
    # the rank guard (statistic 4)
    o = np.asarray([grades[r["fold_id"]]["_o"][r["_i"]] for r in rows])
    base = _within_rows(rows, o)
    guard = {}
    for x in CANDIDATES + ("D0",):
        g = np.asarray([grades[r["fold_id"]][x][r["_i"]] for r in rows])
        sc = lex_score(g, o)
        rr = [dict(b_, grades=dict(b_["grades"], _x=float(sc[j]))) for j, b_ in enumerate(base)]
        guard[x] = {}
        for f, ix in idx.items():
            sel = [rr[j] for j in ix]
            d = BT.paired(sel, "_x", "_s", "within", B=B, seed=BT.SEED)
            guard[x][f] = {"delta": d.get("delta"), "ci95": d.get("ci95"), "a": d.get("a"), "b": d.get("b")}
    out["guard"] = guard
    return out


def planted(rows: list[dict], v: dict[str, np.ndarray], x: str, *, K: int = K_PLANT,
            B: int = B_PLANT, seed: int = SEED) -> dict:
    """Section 5: POWER (truth X) and SIZE (truth A) of the primary statistic for X."""
    y = np.asarray([r["y"] for r in rows])
    keys = [r["key"] for r in rows]
    draws = boot_draws(keys, B=B, seed=seed)
    by: dict = {}
    for j, r in enumerate(rows):
        by.setdefault(r["fold_id"], []).append(j)
    groups = [np.asarray(ix) for ix in by.values()]
    res = {}
    for truth in (x, "A"):
        hits, deltas = 0, []
        for k in range(int(K)):
            rng = np.random.default_rng(int(seed) + k)
            noise = np.zeros(y.size)
            for ix in groups:
                noise[ix] = y[rng.permutation(ix)] - y[ix].mean()
            ys = v[truth] + noise
            d = (ys - v["A"]) ** 2 - (ys - v[x]) ** 2
            deltas.append(float(d.mean()))
            if lb_only(d, draws) > 0:
                hits += 1
        res["power" if truth == x else "size"] = round(hits / float(K), 4)
        res[f"mean_delta_truth_{truth}"] = round(float(np.mean(deltas)), 5)
    res.update(K=int(K), B=int(B), seed=int(seed))
    return res


def rule(read: dict, plant: dict, x: str, holm_ok: bool) -> dict:
    p = read["deltas"][PRIMARY][f"{x}_vs_A"]
    lb = p["both"]["mse"]["ci95"][0]
    checks = {
        "1_mse_lb_above_0_and_holm": bool(lb > 0 and holm_ok),
        "2_no_frame_below_0": all(p[f]["mse"]["delta"] >= 0 for f in ("lv_dev", "vm_dev")),
        "3_mae_not_worse": bool(p["both"]["mae"]["delta"] >= 0),
        "4_rank_guard": all((read["guard"][x][f]["delta"] is not None
                             and read["guard"][x][f]["delta"] >= GUARD) for f in ("both", "lv_dev", "vm_dev")),
        "5_beats_null_comparator": bool(read["deltas"][PRIMARY].get(f"{x}_vs_N_{x}", {})
                                        .get("both", {}).get("mse", {}).get("delta", 0.0) > 0),
        "6_sensitivity_instruments": all(read["deltas"][i][f"{x}_vs_A"]["both"]["mse"]["delta"] > 0
                                         for i in INSTRUMENTS if i != PRIMARY),
        "7_size": bool(plant["size"] <= SIZE_MAX),
    }
    passes = all(checks.values())
    word = "PASS" if passes else ("NULL" if plant["power"] >= POWER_MIN else "UNRESOLVED")
    return {"checks": checks, "passes": passes, "reading": word}


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


def prepare(cache_dir: Path, *, log=print) -> dict:
    """Everything outcome-free: the cache, Q1, Q3, Q4, the groups, the maps, the null
    comparators' m and the board effect."""
    packs, b1 = load_cache(cache_dir)
    check_reserved(b1)
    fit = json.loads(RF.FIT_PATH.read_text(encoding="utf-8"))
    q1 = check_receipts(packs, fit)
    log(f"Q1: {len(q1)} fold receipts match")
    sw = served_weights()
    groups = fold_groups(packs, b1, sw)
    rows, differ = scored_rows(b1, groups)
    nulls = matched_nulls(groups)
    m_by = {s: {x: nulls[s][x]["m"] for x in CANDIDATES} for s in F.SIDES}
    grades = all_maps(groups, m_by)
    for fold_id, g in groups.items():
        grades[fold_id]["_o"] = g["o"]
    board = live_board()
    q4 = parity_q4(board)
    log(f"Q4: live board reproduces ({q4})")
    effect = board_effect(board)
    return {"packs": packs, "b1": b1, "fit": fit, "q1": q1, "q4": q4, "weights": sw,
            "groups": groups, "rows": rows, "differ": differ, "nulls": nulls,
            "grades": grades, "board": effect}


def run(cache_dir: Path, work: Path, *, B: int = B_MAIN, log=print) -> dict:
    import efv_labels as L
    BT, _B4 = _tools()
    t0 = time.time()
    if L.provider() != BT.FROZEN_PROVIDER:
        raise RuntimeError(f"label provider is {L.provider()!r}, not {BT.FROZEN_PROVIDER!r}")
    pre = prepare(cache_dir, log=log)
    q2 = parity_q2(pre["packs"], pre["b1"], pre["fit"])
    log(f"Q2: published within reproduced ({q2})")
    inst = instruments()
    reads, plants = {}, {}
    for side in F.SIDES:
        rows = [r for r in pre["rows"] if r["side"] == side]
        got = _load(work, f"read_{side}")
        if got is None:
            got = side_read(rows, pre["grades"], inst, B=B, seed=SEED)
            _save(work, f"read_{side}", got)
        reads[side] = got
        log(f"{side}: n {got['n']}")
        plants[side] = {}
        for x in CANDIDATES:
            pl = _load(work, f"plant_{side}_{x}")
            if pl is None:
                pl = planted(rows, got["_v"], x)
                _save(work, f"plant_{side}_{x}", pl)
            plants[side][x] = pl
            log(f"  {x}: mse {got['deltas'][PRIMARY][f'{x}_vs_A']['both']['mse']} planted {pl}")
    pvals = {f"{x}|{s}": reads[s]["deltas"][PRIMARY][f"{x}_vs_A"]["both"]["mse"]["p_le_0"]
             for s in F.SIDES for x in CANDIDATES}
    holm_ok = holm(pvals)
    rules = {s: {x: rule(reads[s], plants[s][x], x, holm_ok[f"{x}|{s}"]) for x in CANDIDATES}
             for s in F.SIDES}
    prepared = {}
    for s in F.SIDES:
        ok = [x for x in CANDIDATES if rules[s][x]["passes"]]
        if ok:
            prepared[s] = max(ok, key=lambda x: reads[s]["deltas"][PRIMARY][f"{x}_vs_A"]["both"]["mse"]["delta"])
    for s in F.SIDES:
        reads[s].pop("_v", None)
    doc = {"schema": 1, "item": ITEM, "produced_by": f"{TOOL} --run", "generated_at": BT._now(),
           "role": "development", "adjudicates": False, "doc": DOC,
           "owner_decision": "EW3-35 (2026-10-16)", "label": pre["fit"].get("label"),
           "source_fit": RF.FIT_PATH.relative_to(ROOT).as_posix(),
           "source_fit_generated_at": pre["fit"].get("generated_at"),
           "served_weights": pre["weights"],
           "constants": {"H_SMOOTH": H_SMOOTH, "H_SLOPE": H_SLOPE, "B": int(B), "K_PLANT": K_PLANT,
                         "B_PLANT": B_PLANT, "seed": SEED, "guard": GUARD, "size_max": SIZE_MAX,
                         "power_min": POWER_MIN, "holm_alpha": HOLM_ALPHA},
           "checks": {"Q1_fold_receipts": pre["q1"], "Q2_published_within": q2,
                      "Q3_reserved": "no reserved fold", "Q4_live_board": pre["q4"],
                      "scored_rows_whose_test_fv_differs_from_scored_consensus": pre["differ"]},
           "instruments": {"perside": "data/fv_outcome_curves.json curves.<side>.war.value",
                           "pooled": "data/fv_outcome_curves_pooled.json curve.value",
                           "clemens": "data/fv_outcome_curves.json conversions.clemens_2026.table_<side>, (20, 0) added"},
           "null_comparators": pre["nulls"], "reads": reads, "planted": plants,
           "holm": {"p": pvals, "rejected": holm_ok}, "rules": rules,
           "prepared": prepared or None, "board_effect": pre["board"],
           "elapsed_s": round(time.time() - t0, 1),
           "code": {"tool": TOOL, "commit": BT._commit(), "tool_sha256": BT._sha(ROOT / TOOL)}}
    BT.write_doc(doc, OUT_PATH)
    log(f"wrote {OUT_PATH}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="outcome-free checks and the board effect")
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
        pre = prepare(Path(a.cache), log=log)
        out = {"q1": pre["q1"], "q4": pre["q4"], "differ": pre["differ"], "nulls": pre["nulls"],
               "board_effect": pre["board"],
               "rows": {s: sum(1 for r in pre["rows"] if r["side"] == s) for s in F.SIDES}}
        Path(a.work).mkdir(parents=True, exist_ok=True)
        (Path(a.work) / "check.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        log(json.dumps({k: out[k] for k in ("q1", "q4", "differ", "nulls", "rows")}, default=str))
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
