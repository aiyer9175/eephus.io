#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""pitch_economy_lab: the descriptive lab, the decomposition and the constant fit.

Registration: docs/ewar/PITCH_ECONOMY_LAB.md (pitch_economy_lab_v1) and
docs/ebr-2026-09-30/EBR_GATE.md part 11.4, committed alone before any number.

  Part A  hitters: P/PA(Y) against wOBA and wRAA in Y and Y+1, raw and partial on
          BB%, K% and xwOBA (pairs 2016 to 2025 without 2020, 300 PA both seasons).
  Part B  team-game: the lineup's pitch rate against the opposing starter's and
          bullpen's outs (corpus 2018, 2019, 2021 to 2025).
  Part C  pitchers: P/BF and P/IP(Y) against RA9, IP, IP / GS and fWAR in Y+1, raw and
          partial on K%, BB% and the EM+ shrunk FIP (50 IP both seasons).
  Part D  the same-season decomposition: count lift and starter wear (hitters), the
          times-through-order table and the efficiency chain (pitchers).
  Part E  the frozen constants of PE-P and PE-H (delta_TTO, K_CL, K_P), fitted on the
          2018 and 2019 corpus seasons only.
  Part F  the trigger for the owner's HEM+, SEM+ and REM+ question.

Never: a forward, year-to-year or split-half statistic of a pitch-economy delta (the
one split-half statistic is part E's, on 2018 and 2019 inputs); a 2026 row; an FV cell;
a betting artifact, price or game result.

Run:
  python tools/pitch_economy_lab.py --dry-run --out PATH   synthetic fixture, nulls
  python -u tools/pitch_economy_lab.py --run               THE RUN (writes data/_labs/)
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pitch_economy as pe  # noqa: E402

CACHE = ROOT / ".cache"
OUT = ROOT / "data" / "_labs" / "pitch_economy_partials.json"
CONST_OUT = ROOT / "data" / "_labs" / "pitch_economy_constants.json"
COUNT_VALUE = ROOT / "data" / "count_value.json"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
CORPUS = CACHE / "pbp_corpus"
RECORD = CACHE / "pbp_runners"
WIN_PROB_INDEX = CACHE / "mlbstats_games" / "win_prob_index.json"

B = 2000
SEED = 20261015
PAIR_YEARS = (2016, 2017, 2018, 2021, 2022, 2023, 2024)
CORPUS_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
D2_SEASONS = (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)
HIT_FLOOR_PA = 300
PIT_FLOOR_IP = 50.0
PRIOR_PPA_K = 100.0
K_SPLIT_FLOOR_N = 200
K_SPLIT_FLOOR_M = 150
TTO_MIN_LATE = 30
IDENTITY_TOL = 1e-6
#: A run guard added after the first run's defect (lab part 10, 2026-10-15 note): the
#: corpus walk refuses unless the RE288 telescoping identity holds on this share of
#: plate appearances (count_value's own RECEIPT_SHARE).
IDENTITY_SHARE = 0.999
DIGITS = 6


class LabRefused(RuntimeError):
    pass


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _r(x, d=DIGITS):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, d) if math.isfinite(v) else None


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


# ==========================================================================
# statistics (lab part 2)
# ==========================================================================
def _rank(x: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    return rankdata(x)


def spearman(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return None
    rx, ry = _rank(x), _rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def partial_spearman(x, y, Z) -> float | None:
    """Pearson of the residuals of rank(x) and rank(y) on the ranks of the controls."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    Z = np.asarray(Z, float).reshape(len(x), -1)
    if len(x) < Z.shape[1] + 4:
        return None
    rz = np.column_stack([np.ones(len(x))] + [_rank(Z[:, j]) for j in range(Z.shape[1])])
    rx, ry = _rank(x), _rank(y)
    bx, *_ = np.linalg.lstsq(rz, rx, rcond=None)
    by, *_ = np.linalg.lstsq(rz, ry, rcond=None)
    ex, ey = rx - rz @ bx, ry - rz @ by
    if ex.std() == 0 or ey.std() == 0:
        return None
    return float(np.corrcoef(ex, ey)[0, 1])


def pearson(x, y) -> float | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _clusters(ids) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(row order grouped by cluster, cluster starts in that order, cluster sizes)."""
    order: dict = {}
    for i, c in enumerate(ids):
        order.setdefault(c, []).append(i)
    groups = list(order.values())
    rows = np.asarray([i for g in groups for i in g], dtype=np.int64)
    sizes = np.asarray([len(g) for g in groups], dtype=np.int64)
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int64)
    return rows, starts, sizes


def _resample(rows, starts, sizes, pick) -> np.ndarray:
    ln = sizes[pick]
    tot = int(ln.sum())
    base = np.repeat(starts[pick], ln)
    offs = np.arange(tot) - np.repeat(np.cumsum(ln) - ln, ln)
    return rows[base + offs]


def boot_ci(stat, cols: dict, ids, *, b: int = B, seed: int = SEED) -> dict:
    """Point estimate, cluster-bootstrap percentile 95 percent interval and sd.

    stat(cols_subset) -> float | None; cols: {name: array}; ids: cluster per row."""
    n = len(ids)
    point = stat(cols) if n else None
    out = {"n": int(n), "point": _r(point), "lo95": None, "hi95": None, "sd": None,
           "excludes_0": None, "boot_valid": 0}
    if point is None or n < 5:
        return out
    rows, starts, sizes = _clusters(ids)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(b):
        pick = rng.integers(0, len(sizes), len(sizes))
        idx = _resample(rows, starts, sizes, pick)
        v = stat({k: a[idx] for k, a in cols.items()})
        if v is not None and math.isfinite(v):
            vals.append(v)
    if len(vals) < b // 2:
        return out
    arr = np.asarray(vals)
    lo, hi = float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))
    out.update({"lo95": _r(lo), "hi95": _r(hi), "sd": _r(arr.std(ddof=1)),
                "excludes_0": bool(lo > 0 or hi < 0), "boot_valid": len(vals)})
    return out


def _cols_ok(cols: dict, names) -> np.ndarray:
    m = np.ones(len(next(iter(cols.values()))), dtype=bool)
    for nm in names:
        a = np.asarray(cols[nm], float)
        m &= np.isfinite(a)
    return m


def corr_block(cols: dict, ids, x: str, y: str, controls=(), seasons=None, *,
               b: int = B) -> dict:
    """One statistic: raw Spearman (no controls) or partial Spearman, pooled with a
    clustered bootstrap, plus per-season points; rows missing a needed column drop."""
    need = [x, y, *controls]
    m = _cols_ok(cols, need)
    sub = {k: np.asarray(cols[k], float)[m] for k in need}
    ids_m = np.asarray(ids, dtype=object)[m]
    if controls:
        def stat(c):
            return partial_spearman(c[x], c[y], np.column_stack([c[k] for k in controls]))
    else:
        def stat(c):
            return spearman(c[x], c[y])
    res = boot_ci(stat, sub, ids_m, b=b)
    res.update({"x": x, "y": y, "controls": list(controls), "dropped": int((~m).sum())})
    if seasons is not None:
        ss = np.asarray(seasons)[m]
        res["by_season"] = {str(s): _r(stat({k: a[ss == s] for k, a in sub.items()}))
                            for s in sorted(set(ss.tolist()))}
    return res


# ==========================================================================
# loaders (lab part 1)
# ==========================================================================
def _splits(group: str, season: int) -> list[dict]:
    path = CACHE / f"fa_statsapi_{group}_{season}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    return (doc.get("stats") or [{}])[0].get("splits") or []


def hit_lines(season: int, splits=None) -> dict:
    out = {}
    for s in splits if splits is not None else _splits("hitting", season):
        st = s.get("stat") or {}
        pid = int(s["player"]["id"])
        row = {"pa": _num(st.get("plateAppearances")), "pitches": _num(st.get("numberOfPitches")),
               "ab": _num(st.get("atBats")), "bb": _num(st.get("baseOnBalls")),
               "ibb": _num(st.get("intentionalWalks")), "hbp": _num(st.get("hitByPitch")),
               "so": _num(st.get("strikeOuts")), "sf": _num(st.get("sacFlies")),
               "h": _num(st.get("hits")), "d2": _num(st.get("doubles")),
               "d3": _num(st.get("triples")), "hr": _num(st.get("homeRuns")),
               "pos": (s.get("position") or {}).get("abbreviation"),
               "name": (s.get("player") or {}).get("fullName")}
        if pid not in out or row["pa"] > out[pid]["pa"]:
            out[pid] = row
    return out


def pit_lines(season: int, splits=None) -> dict:
    out = {}
    for s in splits if splits is not None else _splits("pitching", season):
        st = s.get("stat") or {}
        pid = int(s["player"]["id"])
        row = {"g": _num(st.get("gamesPlayed") or st.get("gamesPitched")),
               "gs": _num(st.get("gamesStarted")), "outs": _num(st.get("outs")),
               "tbf": _num(st.get("battersFaced")), "pitches": _num(st.get("numberOfPitches")),
               "k": _num(st.get("strikeOuts")), "bb": _num(st.get("baseOnBalls")),
               "hbp": _num(st.get("hitByPitch")), "hr": _num(st.get("homeRuns")),
               "r": _num(st.get("runs")), "er": _num(st.get("earnedRuns")),
               "pos": (s.get("position") or {}).get("abbreviation"),
               "name": (s.get("player") or {}).get("fullName")}
        row["ip"] = row["outs"] / 3.0
        if pid not in out or row["outs"] > out[pid]["outs"]:
            out[pid] = row
    return out


def sprp_lines(season: int, rows=None) -> dict:
    """{mlbam: {"SP": {n, pitches, outs, bf}, "RP": {...}}}, stints summed."""
    if rows is None:
        doc = json.loads((CACHE / "pitch_rates" / f"pitching_sprp_1_{season}.json")
                         .read_text(encoding="utf-8"))
        rows = doc.get("rows") or []
    out: dict = {}
    for r in rows:
        code = str(r.get("code") or "").lower()
        role = "SP" if code == "sp" else "RP" if code == "rp" else None
        if role is None:
            continue
        pid = int(r["mlbam"])
        blk = out.setdefault(pid, {}).setdefault(role, {"n": 0.0, "pitches": 0.0, "outs": 0.0, "bf": 0.0})
        blk["n"] += _num(r.get("gs") if role == "SP" else r.get("g"))
        blk["pitches"] += _num(r.get("np"))
        blk["outs"] += _num(r.get("outs"))
        blk["bf"] += _num(r.get("bf"))
    return out


def xwoba(season: int) -> dict:
    path = CACHE / "savant_mlb" / f"expected_batter_{season}.csv"
    if not path.exists():
        return {}
    out = {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for r in csv.DictReader(io.StringIO(text)):
        try:
            pid, ew, pa = int(r["player_id"]), float(r["est_woba"]), float(r["pa"])
        except (TypeError, ValueError, KeyError):
            continue
        if pa >= 100 and ew > 0:
            out[pid] = ew
    return out


def season_constants(season: int) -> dict:
    import league_constants as lc
    c = lc.constants(season) or {}
    t = lc.league_totals(season) or {}
    if not c or c.get("season") != season or not t:
        raise LabRefused(f"league constants for {season} are missing")
    return {"weights": c["woba_weights"], "scale": c["woba_scale"], "lg_woba": c["lg_woba"],
            "cfip": t["fip_constant"], "rpw": t["rpw"], "lg_pa": t["lg_pa"], "lg_ip": t["lg_ip"]}


def woba_of(h: dict, w: dict) -> float | None:
    den = h["ab"] + h["bb"] - h["ibb"] + h["sf"] + h["hbp"]
    if den <= 0:
        return None
    single = h["h"] - h["d2"] - h["d3"] - h["hr"]
    num = (w["ubb"] * (h["bb"] - h["ibb"]) + w["hbp"] * h["hbp"] + w["1b"] * single
           + w["2b"] * h["d2"] + w["3b"] * h["d3"] + w["hr"] * h["hr"])
    return num / den


def fwar_pitching(season: int) -> dict:
    doc = json.loads(VINTAGE.read_text(encoding="utf-8"))
    blk = (doc.get("seasons") or {}).get(str(season)) or {}
    pit = blk.get("pitching") or {}
    fields = pit.get("fields") or (doc.get("fields") or {}).get("pitching") or []
    if "war" not in fields:
        return {}
    i = fields.index("war")
    out = {}
    for pid, row in (pit.get("rows") or {}).items():
        try:
            out[int(pid)] = float(row[i])
        except (TypeError, ValueError, IndexError):
            continue
    return out


# ==========================================================================
# Part A: hitters
# ==========================================================================
def part_a(hit: dict, xw: dict, consts: dict, years=PAIR_YEARS, *, b: int = B) -> dict:
    cols = {k: [] for k in ("ppa", "bb", "k", "xwoba", "woba_y", "wraa_y", "woba_y1", "wraa_y1")}
    ids, seasons = [], []
    for y in years:
        h0, h1 = hit.get(y) or {}, hit.get(y + 1) or {}
        c0, c1 = consts[y], consts[y + 1]
        for pid, a in h0.items():
            z = h1.get(pid)
            if z is None or a["pos"] == "P" or a["pa"] < HIT_FLOOR_PA or z["pa"] < HIT_FLOOR_PA:
                continue
            w0, w1 = woba_of(a, c0["weights"]), woba_of(z, c1["weights"])
            if w0 is None or w1 is None or a["pitches"] <= 0:
                continue
            cols["ppa"].append(a["pitches"] / a["pa"])
            cols["bb"].append((a["bb"] - a["ibb"]) / a["pa"])
            cols["k"].append(a["so"] / a["pa"])
            cols["xwoba"].append(xw.get(y, {}).get(pid, float("nan")))
            cols["woba_y"].append(w0)
            cols["wraa_y"].append((w0 - c0["lg_woba"]) / c0["scale"] * a["pa"])
            cols["woba_y1"].append(w1)
            cols["wraa_y1"].append((w1 - c1["lg_woba"]) / c1["scale"] * z["pa"])
            ids.append(pid)
            seasons.append(y)
    cols = {k: np.asarray(v, float) for k, v in cols.items()}
    ctl = ("bb", "k", "xwoba")
    out = {"pairs": len(ids), "players": len(set(ids)),
           "pairs_by_season": {str(y): seasons.count(y) for y in years},
           "missing_xwoba": int(np.isnan(cols["xwoba"]).sum()) if len(ids) else 0,
           "A1": {}, "A2": {}, "A2b": {}, "A3": {}}
    for t in ("woba_y", "wraa_y", "woba_y1", "wraa_y1"):
        out["A1"][t] = corr_block(cols, ids, "ppa", t, (), seasons, b=b)
        out["A2"][t] = corr_block(cols, ids, "ppa", t, ctl, seasons, b=b)
    for t in ("woba_y1", "wraa_y1"):
        out["A2b"][t] = corr_block(cols, ids, "ppa", t, ctl + ("woba_y",), seasons, b=b)
    for t in ("bb", "k", "xwoba"):
        out["A3"][t] = corr_block(cols, ids, "ppa", t, (), seasons, b=b)
    return out


# ==========================================================================
# Part C: pitchers
# ==========================================================================
def _em_fip(lines: dict, season: int) -> dict:
    """{mlbam: (role, EM+ shrunk FIP)}: SEM+ for starters, REM+ for relievers (each
    module's own pool and fip_skill), the S2 start-share blend for swingmen."""
    import rem_plus as rp
    import sem_plus as sp
    starters, relievers = {}, {}
    for pid, ln in lines.items():
        if ln["ip"] <= 0 or ln["g"] <= 0:
            continue
        share = ln["gs"] / ln["g"]
        kw = dict(key=str(pid), mlbam=pid, g=ln["g"], gs=ln["gs"], ip=ln["ip"], tbf=ln["tbf"],
                  so=ln["k"], bb=ln["bb"], hbp=ln["hbp"], hr=ln["hr"], er=ln["er"], r=ln["r"],
                  pit=ln["pitches"])
        if share >= sp.MIN_START_SHARE:
            starters[pid] = sp.Starter(**kw)
        elif share <= rp.MAX_START_SHARE:
            relievers[pid] = rp.Reliever(**kw)
    spool = sp.build_pool(starters.values())
    rpool = rp.build_pool(relievers.values())
    out = {pid: ("SP", sp.fip_skill(s, spool)) for pid, s in starters.items()}
    out.update({pid: ("RP", rp.fip_skill(r, rpool)) for pid, r in relievers.items()})
    return out


def part_c(pit: dict, fwar: dict, years=PAIR_YEARS, *, b: int = B) -> dict:
    rows = []
    for y in years:
        p0, p1 = pit.get(y) or {}, pit.get(y + 1) or {}
        em = _em_fip(p0, y)
        for pid, a in p0.items():
            z = p1.get(pid)
            if (z is None or a["pos"] not in ("P", "TWP") or a["ip"] < PIT_FLOOR_IP
                    or z["ip"] < PIT_FLOOR_IP or a["tbf"] <= 0 or a["pitches"] <= 0):
                continue
            role, fip = em.get(pid, (None, None))
            share = a["gs"] / a["g"] if a["g"] else 0.0
            if role is None:
                role = "SW"
                fip = _swing_fip(a, p0, y)
            rows.append({
                "pid": pid, "season": y, "role": role,
                "pbf": a["pitches"] / a["tbf"], "pip": a["pitches"] / a["ip"],
                "k": a["k"] / a["tbf"], "bb": a["bb"] / a["tbf"],
                "emfip": fip if fip is not None else float("nan"),
                "ip_y": a["ip"], "ipgs_y": (a["ip"] / a["gs"]) if a["gs"] else float("nan"),
                "ra9_y1": 9.0 * z["r"] / z["ip"], "ip_y1": z["ip"],
                "ipgs_y1": (z["ip"] / z["gs"]) if z["gs"] >= 5 else float("nan"),
                "fwar_y1": fwar.get(y + 1, {}).get(pid, float("nan")), "share": share})
    out = {"pairs": len(rows), "by_role": {}}
    for role_key, keep in (("starters", ("SP",)), ("relievers", ("RP",)),
                           ("pooled", ("SP", "RP", "SW"))):
        sub = [r for r in rows if r["role"] in keep]
        cols = {k: np.asarray([r[k] for r in sub], float) for k in
                ("pbf", "pip", "k", "bb", "emfip", "ip_y", "ipgs_y", "ra9_y1", "ip_y1",
                 "ipgs_y1", "fwar_y1")}
        ids = [r["pid"] for r in sub]
        seasons = [r["season"] for r in sub]
        blk = {"pairs": len(sub), "players": len(set(ids)), "C1": {}, "C2": {}, "C2b": {}, "C3": {}}
        if len(sub) >= 10:
            ctl = ("k", "bb", "emfip")
            targets = ["ra9_y1", "ip_y1", "fwar_y1"] + (["ipgs_y1"] if role_key != "relievers" else [])
            for x in ("pbf", "pip"):
                for t in targets:
                    blk["C1"][f"{x}|{t}"] = corr_block(cols, ids, x, t, (), seasons, b=b)
                    blk["C2"][f"{x}|{t}"] = corr_block(cols, ids, x, t, ctl, seasons, b=b)
                blk["C2b"][f"{x}|ip_y1"] = corr_block(cols, ids, x, "ip_y1", ctl + ("ip_y",), seasons, b=b)
                if role_key != "relievers":
                    blk["C2b"][f"{x}|ipgs_y1"] = corr_block(cols, ids, x, "ipgs_y1", ctl + ("ipgs_y",),
                                                            seasons, b=b)
                blk["C2b"][f"{x}|fwar_y1"] = corr_block(cols, ids, x, "fwar_y1", ("emfip", "ip_y"),
                                                        seasons, b=b)
            for t in ("k", "bb"):
                blk["C3"][t] = corr_block(cols, ids, "pbf", t, (), seasons, b=b)
        out["by_role"][role_key] = blk
    return out


_SWING_CACHE: dict = {}


def _swing_fip(a: dict, lines: dict, season: int) -> float | None:
    """A swingman's start-share blend of S2 (pooled rates of the SEM+ and REM+ pools),
    with the start share taken from games (GS / G) because the season line has no
    role innings; used only in Part C's pooled block."""
    key = (season, id(lines))
    if key not in _SWING_CACHE:
        _SWING_CACHE[key] = s2_pools(lines)
    pools = _SWING_CACHE[key]
    if pools is None or a["g"] <= 0:
        return None
    nu = pe.s2_targets(pools["sp"], pools["rp"], a["gs"] / a["g"])
    cf = pools["cfip"]
    return pe.s2_skill_fip({"k": a["k"], "bb": a["bb"], "hbp": a["hbp"], "hr": a["hr"]},
                           a["tbf"], a["ip"], nu, cf)


def s2_pools(lines: dict, cfip: float | None = None) -> dict | None:
    sp = [ln for ln in lines.values() if ln["g"] > 0 and ln["gs"] / ln["g"] >= pe.SP_MIN_START_SHARE
          and ln["ip"] >= pe.SEM_POOL_MIN_IP]
    rp = [ln for ln in lines.values() if ln["g"] > 0 and ln["gs"] / ln["g"] <= pe.RP_MAX_START_SHARE
          and ln["tbf"] >= pe.REM_POOL_MIN_TBF]
    ps = pe.pooled_rates({"k": l["k"], "bb": l["bb"], "hbp": l["hbp"], "hr": l["hr"], "tbf": l["tbf"]}
                         for l in sp)
    pr = pe.pooled_rates({"k": l["k"], "bb": l["bb"], "hbp": l["hbp"], "hr": l["hr"], "tbf": l["tbf"]}
                         for l in rp)
    if ps is None or pr is None:
        return None
    if cfip is None:
        tot = {k: sum(l[k] for l in lines.values()) for k in ("er", "outs", "hr", "bb", "hbp", "k")}
        ip = tot["outs"] / 3.0
        cfip = 9.0 * tot["er"] / ip - (13 * tot["hr"] + 3 * (tot["bb"] + tot["hbp"]) - 2 * tot["k"]) / ip
    return {"sp": ps, "rp": pr, "cfip": cfip}


def role_fip(lines: dict, cfip: float) -> dict:
    """F_SP and F_RP: pooled FIP per nine of true starters and true relievers."""
    out = {}
    for role, keep in (("SP", lambda s: s >= pe.SP_MIN_START_SHARE),
                       ("RP", lambda s: s <= pe.RP_MAX_START_SHARE)):
        tot = {k: 0.0 for k in ("hr", "bb", "hbp", "k", "outs")}
        for ln in lines.values():
            if ln["g"] <= 0 or ln["pos"] not in ("P", "TWP") or not keep(ln["gs"] / ln["g"]):
                continue
            for k in tot:
                tot[k] += ln[k]
        out[role] = pe.fip9(tot["hr"], tot["bb"], tot["hbp"], tot["k"], tot["outs"] / 3.0, cfip)
    return out


def league_role(sprp: dict) -> dict:
    out = {}
    for role in ("SP", "RP"):
        P = sum(v[role]["pitches"] for v in sprp.values() if role in v)
        O = sum(v[role]["outs"] for v in sprp.values() if role in v)
        N = sum(v[role]["n"] for v in sprp.values() if role in v)
        out[role] = {"l_ppo": P / O if O else None, "l_pa": P / N if N else None,
                     "pitches": P, "outs": O, "n": N}
    return out


# ==========================================================================
# corpus (Parts B, D1, E)
# ==========================================================================
def _game_dates() -> dict:
    try:
        doc = json.loads(WIN_PROB_INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name, v in (doc.get("files") or {}).items():
        try:
            out[int(name.split(".")[0])] = str(v[3])
        except (ValueError, IndexError, TypeError):
            continue
    return out


def load_corpus_season(season: int) -> dict:
    import pandas as pd
    man = json.loads((RECORD / "manifest.json").read_text(encoding="utf-8"))
    blk = (man.get("seasons") or {}).get(str(season))
    if not blk:
        raise LabRefused(f"the runner record lacks {season}")
    pa = pd.read_parquet(RECORD / blk["files"]["pa"],
                         columns=["game_pk", "at_bat_index", "half", "batter_id", "is_pa",
                                  "event_type", "outs_before", "on_first", "on_second", "on_third",
                                  "end_on_first", "end_on_second", "end_on_third", "end_outs",
                                  "runs_scored_on_play", "states_json"])
    plays = pd.read_parquet(CORPUS / "plays" / str(season) / f"plays-{season}.parquet",
                            columns=["game_pk", "at_bat_index", "pitcher_id", "outs_before",
                                     "outs_after"])
    pit = pd.read_parquet(CORPUS / "pitches" / str(season) / f"pitches-{season}.parquet",
                          columns=["game_pk", "at_bat_index", "pitch_number", "call_code"])
    ev = pd.read_parquet(CORPUS / "events" / str(season) / f"events-{season}.parquet",
                         columns=["game_pk", "at_bat_index", "index", "type", "description"])
    return {"pa": pa, "plays": plays, "pitches": pit, "events": ev}


def _slices(game, abi) -> dict:
    key = game.astype(np.int64) * 10000 + abi.astype(np.int64)
    if len(key) == 0:
        return {}
    brk = np.flatnonzero(np.diff(key)) + 1
    starts = np.concatenate([[0], brk])
    stops = np.concatenate([brk, [len(key)]])
    return {int(key[a]): (int(a), int(b_)) for a, b_ in zip(starts, stops)}


def _missing(v) -> bool:
    """None, NaN or pandas' NA (the runner record's nullable integer columns)."""
    if v is None:
        return True
    try:
        import pandas as pd
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _bits(a, b_, c) -> int:
    return (0 if _missing(a) else 1) | (0 if _missing(b_) else 2) | (0 if _missing(c) else 4)


def walk_corpus_season(season: int, d: dict, t288: dict, re24: dict, dates: dict) -> dict:
    """One row per plate appearance (is_pa) with: batter, starter flag, pitcher, game,
    date key, class, pitches, count lift CL, the RE24 run value and the pass number
    against that pitcher; plus the RE288 identity receipt."""
    import count_value as cv
    pa = d["pa"].merge(d["plays"][["game_pk", "at_bat_index", "pitcher_id", "outs_after"]],
                       on=["game_pk", "at_bat_index"], how="left")
    pa = pa.sort_values(["game_pk", "at_bat_index"], kind="stable").reset_index(drop=True)
    pit = d["pitches"].sort_values(["game_pk", "at_bat_index", "pitch_number"], kind="stable")
    ev = d["events"].sort_values(["game_pk", "at_bat_index", "index"], kind="stable")
    psl = _slices(pit["game_pk"].to_numpy(), pit["at_bat_index"].to_numpy())
    esl = _slices(ev["game_pk"].to_numpy(), ev["at_bat_index"].to_numpy())
    codes = pit["call_code"].to_numpy(dtype=object)
    e_idx, e_type, e_desc = (ev["index"].to_numpy(), ev["type"].to_numpy(dtype=object),
                             ev["description"].to_numpy(dtype=object))
    T = cv.Table(t288)

    def r24(bits, outs):
        return re24[f"{int(bits)}|{int(outs)}"]

    # the starter of each fielding half: the pitcher of the half's first play
    first = pa.groupby(["game_pk", "half"], sort=False)["at_bat_index"].transform("min")
    is_first = pa["at_bat_index"] == first
    starters = dict(zip(zip(pa.loc[is_first, "game_pk"], pa.loc[is_first, "half"]),
                        pa.loc[is_first, "pitcher_id"]))
    rows = []
    receipt = {"pa": 0, "identity_exact": 0, "no_pitch": 0, "intent_walk": 0,
               "missing_pitcher": 0}
    pass_ct: dict = {}
    cols = {c: pa[c].to_numpy(dtype=object) for c in pa.columns}
    for j in range(len(pa)):
        if not bool(cols["is_pa"][j]):
            continue
        gk, ab = int(cols["game_pk"][j]), int(cols["at_bat_index"][j])
        key = gk * 10000 + ab
        a, b_ = psl.get(key, (0, 0))
        pcodes = list(codes[a:b_])
        ea, eb = esl.get(key, (0, 0))
        evs = [(int(e_idx[k]), e_type[k], e_desc[k]) for k in range(ea, eb)]
        sj = cols["states_json"][j]
        states = json.loads(sj) if isinstance(sj, str) and sj else []
        sb = _bits(cols["on_first"][j], cols["on_second"][j], cols["on_third"][j])
        so = int(cols["outs_before"][j])
        w = cv.walk_play(sb, so, pcodes, evs, states)
        steps = w["steps"]
        p_list = cv.pitch_indices(len(pcodes), [e[0] for e in evs])
        p_idx = set(p_list)
        keys = set(p_idx) | {e[0] for e in evs}
        for st in states:
            keys.add(-1 if st[0] is None else int(st[0]))
        order = sorted(keys)
        last = p_list[-1] if p_list else None
        vals = [cv.state_value(T, r24, af) - cv.state_value(T, r24, bf) + rr for bf, af, rr in steps]
        cl = 0.0
        for idx, (bf, af, rr), v in zip(order, steps, vals):
            if idx in p_idx and idx != last and bf[2] == af[2] and bf[3] == af[3] and rr == 0:
                cl += v
        eb_ = _bits(cols["end_on_first"][j], cols["end_on_second"][j], cols["end_on_third"][j])
        eo = cols["end_outs"][j]
        eo = 3 if _missing(eo) else int(eo)
        rs = cols["runs_scored_on_play"][j]
        runs = 0 if _missing(rs) else int(rs)
        rv = runs + (0.0 if eo >= 3 else r24(eb_, eo)) - (0.0 if so >= 3 else r24(sb, so))
        receipt["pa"] += 1
        receipt["identity_exact"] += int(abs(sum(vals) - rv) <= IDENTITY_TOL)
        half = cols["half"][j]
        pid = cols["pitcher_id"][j]
        if _missing(pid):
            receipt["missing_pitcher"] += 1
            pid = -1
        pid = int(pid)
        bat = int(cols["batter_id"][j])
        pk = (gk, pid, bat)
        pass_ct[pk] = pass_ct.get(pk, 0) + 1
        cls = pe.terminal_class(cols["event_type"][j])
        if cls is None:
            receipt["intent_walk"] += 1
        if not pcodes:
            receipt["no_pitch"] += 1
        rows.append((bat, gk, dates.get(gk, ""), pid, int(starters.get((gk, half)) == pid), cls,
                     len(pcodes), cl, rv, pass_ct[pk], half))
    receipt["identity_share"] = _r(receipt["identity_exact"] / receipt["pa"]) if receipt["pa"] else None
    return {"rows": rows, "receipt": receipt, "season": season}


def part_b(seasons_data: dict, hit_prev: dict, sprp_prev: dict, *, b: int = B) -> dict:
    """Team-game rows from the walked plate appearances plus the plays' outs."""
    cols = {k: [] for k in ("ppa_game", "ppa_prior", "sp_outs", "bp_outs", "sp_prior_ppo")}
    ids, seasons = [], []
    for s, blk in seasons_data.items():
        hp = hit_prev.get(s) or {}
        lg_pa = sum(v["pa"] for v in hp.values())
        lg_p = sum(v["pitches"] for v in hp.values())
        L = lg_p / lg_pa if lg_pa else 3.9
        sp_prev = sprp_prev.get(s) or {}
        lr = league_role(sp_prev) if sp_prev else {"SP": {"l_ppo": None}}
        Lsp = lr["SP"]["l_ppo"] or 5.5
        outs = blk["outs"]                      # {(game, half): {pitcher: outs}}
        side: dict = {}
        for (bat, gk, _date, pid, is_sp, _cls, npit, _cl, _rv, _pass, half) in blk["rows"]:
            k = (gk, half)
            t = side.setdefault(k, {"pa": 0, "p": 0, "prior": 0.0, "starter": None})
            t["pa"] += 1
            t["p"] += npit
            hv = hp.get(bat)
            t["prior"] += ((hv["pitches"] + PRIOR_PPA_K * L) / (hv["pa"] + PRIOR_PPA_K)) if hv else L
            if is_sp:
                t["starter"] = pid
        for k, t in side.items():
            st = t["starter"]
            o = outs.get(k) or {}
            if st is None or t["pa"] == 0 or not o:
                continue
            spo = float(o.get(st, 0))
            bpo = float(sum(v for p_, v in o.items() if p_ != st))
            prev = (sp_prev.get(st) or {}).get("SP")
            pr = pe.shrink(prev["pitches"], prev["outs"], pe.K_O, Lsp) if prev else Lsp
            cols["ppa_game"].append(t["p"] / t["pa"])
            cols["ppa_prior"].append(t["prior"] / t["pa"])
            cols["sp_outs"].append(spo)
            cols["bp_outs"].append(bpo)
            cols["sp_prior_ppo"].append(pr)
            ids.append(k[0])
            seasons.append(s)
    cols = {k: np.asarray(v, float) for k, v in cols.items()}
    out = {"rows": len(ids), "games": len(set(ids)),
           "rows_by_season": {str(s): seasons.count(s) for s in sorted(set(seasons))},
           "B1": {}, "B2": {}}
    for t in ("sp_outs", "bp_outs"):
        out["B1"][t] = corr_block(cols, ids, "ppa_game", t, (), seasons, b=b)
        out["B2"][t] = corr_block(cols, ids, "ppa_prior", t, (), seasons, b=b)
        out["B2"][t + "|partial_sp_prior_ppo"] = corr_block(cols, ids, "ppa_prior", t, ("sp_prior_ppo",),
                                                            seasons, b=b)
    return out


def play_outs(d: dict) -> dict:
    """{(game, half): {pitcher: outs}} from the corpus plays (outs_after - outs_before)."""
    pl = d["plays"].merge(d["pa"][["game_pk", "at_bat_index", "half"]], on=["game_pk", "at_bat_index"],
                          how="left")
    dlt = (pl["outs_after"].astype(float) - pl["outs_before"].astype(float)).clip(lower=0).fillna(0)
    out: dict = {}
    for gk, half, pid, o in zip(pl["game_pk"], pl["half"], pl["pitcher_id"], dlt):
        if _missing(pid):
            continue
        blk = out.setdefault((int(gk), half), {})
        blk[int(pid)] = blk.get(int(pid), 0.0) + float(o)
    return out


# ---------------------------------------------------------------------------
# Part D1 and Part E (hitters)
# ---------------------------------------------------------------------------
def class_means(rows) -> tuple[dict, dict]:
    cl_sum, cl_n, p_sum, p_n = {}, {}, {}, {}
    for (_bat, _gk, _dt_, _pid, is_sp, cls, npit, cl, _rv, _pass, _half) in rows:
        if cls is None or npit == 0:
            continue
        cl_sum[cls] = cl_sum.get(cls, 0.0) + cl
        cl_n[cls] = cl_n.get(cls, 0) + 1
        if is_sp:
            p_sum[cls] = p_sum.get(cls, 0.0) + npit
            p_n[cls] = p_n.get(cls, 0) + 1
    clbar = {c: cl_sum[c] / cl_n[c] for c in cl_n}
    pbar = {c: p_sum[c] / p_n[c] for c in p_n}
    return clbar, pbar


def hitter_residuals(rows, clbar, pbar, exclude: set) -> dict:
    """{batter: {n, clres, m, pres, games: {gk: [date, n, clres, m, pres]}}}."""
    out: dict = {}
    for (bat, gk, date, _pid, is_sp, cls, npit, cl, _rv, _pass, _half) in rows:
        if cls is None or npit == 0 or bat in exclude:
            continue
        h = out.setdefault(bat, {"n": 0, "clres": 0.0, "m": 0, "pres": 0.0, "games": {}})
        g = h["games"].setdefault(gk, [date, 0, 0.0, 0, 0.0])
        r_cl = cl - clbar[cls]
        h["n"] += 1
        h["clres"] += r_cl
        g[1] += 1
        g[2] += r_cl
        if is_sp:
            r_p = npit - pbar[cls]
            h["m"] += 1
            h["pres"] += r_p
            g[3] += 1
            g[4] += r_p
    return out


def split_half(res_by_season: dict, which: str) -> dict:
    """lab part 7: odd and even games in date order, per-PA mean residual per half."""
    xs, ys, ns = [], [], []
    floor = K_SPLIT_FLOOR_N if which == "cl" else K_SPLIT_FLOOR_M
    for _s, res in res_by_season.items():
        for _bat, h in res.items():
            tot = h["n"] if which == "cl" else h["m"]
            if tot < floor:
                continue
            games = sorted(h["games"].items(), key=lambda kv: (kv[1][0], kv[0]))
            acc = [[0, 0.0], [0, 0.0]]
            for i, (_gk, g) in enumerate(games):
                n_, r_ = (g[1], g[2]) if which == "cl" else (g[3], g[4])
                acc[i % 2][0] += n_
                acc[i % 2][1] += r_
            if acc[0][0] == 0 or acc[1][0] == 0:
                continue
            xs.append(acc[0][1] / acc[0][0])
            ys.append(acc[1][1] / acc[1][0])
            ns.append(tot)
    rho_half = pearson(xs, ys)
    nbar = float(np.mean(ns)) if ns else 0.0
    k = pe.split_half_k(rho_half, nbar)
    return {"rows": len(xs), "rho_half": _r(rho_half),
            "rho_full": _r(None if rho_half is None or rho_half <= 0 else 2 * rho_half / (1 + rho_half)),
            "nbar": _r(nbar, 2), "K": (None if not math.isfinite(k) else _r(k, 2)),
            "K_infinite": not math.isfinite(k)}


def tto_table(rows) -> tuple[dict, list]:
    """By pass (1, 2, 3, 4+) against starters: mean run value and n; and the
    starter-season sums for delta_TTO."""
    by = {}
    per: dict = {}
    for (_bat, _gk, _dt_, pid, is_sp, _cls, _npit, _cl, rv, pss, _half) in rows:
        if not is_sp:
            continue
        k = min(pss, 4)
        s = by.setdefault(k, [0, 0.0])
        s[0] += 1
        s[1] += rv
        p = per.setdefault(pid, {"late_n": 0, "late_sum": 0.0, "all_n": 0, "all_sum": 0.0})
        p["all_n"] += 1
        p["all_sum"] += rv
        if pss >= 3:
            p["late_n"] += 1
            p["late_sum"] += rv
    table = {("4+" if k == 4 else str(k)): {"n": v[0], "mean_rv": _r(v[1] / v[0])} for k, v in sorted(by.items())}
    return table, list(per.values())


# ==========================================================================
# Part D2 (pitchers): the chain, same season
# ==========================================================================
def chain_season(season: int, lines: dict, sprp: dict, consts: dict, delta: float,
                 top: int = 10) -> dict:
    cfip = consts["cfip"]
    pools = s2_pools(lines, cfip)
    rf = role_fip(lines, cfip)
    lr = league_role(sprp)
    pi = consts["lg_pa"] / (consts["lg_ip"] * 3.0)
    t9s = pe.t9(pi, delta)
    raw, roles_of, names = {}, {}, {}
    gaps = {"SP": [], "RP": []}
    cov = {"no_split": 0, "nopp": 0, "no_ip": 0}
    for pid, ln in lines.items():
        if ln["pos"] not in ("P", "TWP"):
            cov["nopp"] += 1
            continue
        if ln["ip"] <= 0 or ln["tbf"] <= 0:
            cov["no_ip"] += 1
            continue
        rl = sprp.get(pid)
        if not rl:
            cov["no_split"] += 1
            continue
        o_sp = (rl.get("SP") or {}).get("outs", 0.0)
        o_all = o_sp + (rl.get("RP") or {}).get("outs", 0.0)
        sigma = o_sp / o_all if o_all else 0.0
        nu = pe.s2_targets(pools["sp"], pools["rp"], sigma)
        fsk = pe.s2_skill_fip({"k": ln["k"], "bb": ln["bb"], "hbp": ln["hbp"], "hr": ln["hr"]},
                              ln["tbf"], ln["ip"], nu, cfip)
        lines_r = {r: {"n": v["n"], "pitches": v["pitches"], "outs": v["outs"]} for r, v in rl.items()}
        raw[pid] = pe.pe_p_raw(lines_r, fsk, rf["RP"], t9s, lr)
        for r, blk in raw[pid].items():
            gaps[r].append(blk["gap_outs"])
        share = ln["gs"] / ln["g"] if ln["g"] else 0.0
        roles_of[pid] = "SP" if share >= pe.SP_MIN_START_SHARE else "RP" if share <= pe.RP_MAX_START_SHARE else "SW"
        names[pid] = ln.get("name")
    delta_pe = pe.pe_p_delta(raw)
    rpw = consts["rpw"]
    sums = {}
    for r in ("SP", "RP"):
        g = {pid: v[r]["g"] for pid, v in raw.items() if r in v}
        o = {pid: v[r]["outs"] for pid, v in raw.items() if r in v}
        rc = pe.recentre(g, o)
        sums[r] = _r(sum(rc.values()), 9)
    by_role = {}
    for role in ("SP", "RP", "SW"):
        v = np.asarray([delta_pe[p] for p in delta_pe if roles_of.get(p) == role], float)
        if len(v):
            by_role[role] = {"n": int(len(v)), "sd_runs": _r(v.std(ddof=1) if len(v) > 1 else 0.0, 4),
                             "min_runs": _r(v.min(), 4), "max_runs": _r(v.max(), 4),
                             "share_ge_0p1_war": _r(float((np.abs(v) / rpw >= 0.1).mean()), 4),
                             "share_ge_0p5_war": _r(float((np.abs(v) / rpw >= 0.5).mean()), 4)}
    movers = sorted(delta_pe.items(), key=lambda kv: -abs(kv[1]))[:top]
    return {"season": season, "pi": _r(pi), "T9": _r(t9s), "F_SP": _r(rf["SP"]), "F_RP": _r(rf["RP"]),
            "cfip": cfip, "rpw": rpw,
            "league_role": {r: {k: _r(v, 4) for k, v in blk.items()} for r, blk in lr.items()},
            "w_per_pitch": _r(pe.wear_price(rf["RP"], rf["SP"], t9s, lr["SP"]["l_ppo"])),
            "pitchers": len(raw), "coverage": cov,
            "gap_outs": {r: {"n": len(v), "mean": _r(np.mean(v), 4) if v else None,
                             "sd": _r(np.std(v, ddof=1), 4) if len(v) > 1 else None} for r, v in gaps.items()},
            "zero_sum_by_role_runs": sums, "zero_sum_total_runs": _r(sum(delta_pe.values()), 9),
            "delta_pe_by_role": by_role,
            "top_movers": [{"mlbam": p, "name": names.get(p), "role": roles_of.get(p),
                            "delta_pe_runs": _r(v, 3), "delta_pe_war": _r(v / rpw, 3)} for p, v in movers]}


# ==========================================================================
# Part F
# ==========================================================================
def part_f(a: dict, c: dict) -> dict:
    def g(blk):
        return None if blk is None else {k: blk.get(k) for k in ("n", "point", "lo95", "hi95", "excludes_0")}
    h = (a.get("A2") or {}).get("woba_y1")
    s = (((c.get("by_role") or {}).get("starters") or {}).get("C2") or {}).get("pbf|ra9_y1")
    r = (((c.get("by_role") or {}).get("relievers") or {}).get("C2") or {}).get("pbf|ra9_y1")
    items = {"h": g(h), "s": g(s), "r": g(r)}
    shown = {k: bool(v and v.get("excludes_0")) for k, v in items.items()}
    return {"items": items, "residual_value_shown": shown, "any": any(shown.values()),
            "consequence": ("register the X-R1-style test(s) named in lab part 8 before any run"
                            if any(shown.values()) else
                            "no residual value shown: no test is run; the answer is no on this lab's numbers")}


# ==========================================================================
# the run
# ==========================================================================
def _sha_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(out: Path = OUT, const_out: Path = CONST_OUT, *, b: int = B, log=print) -> dict:
    t0 = time.time()
    seasons_all = sorted(set(PAIR_YEARS) | {y + 1 for y in PAIR_YEARS} | set(D2_SEASONS)
                         | {s - 1 for s in CORPUS_SEASONS})
    if any(s >= 2026 for s in seasons_all):
        raise LabRefused("a 2026 row would be read")
    hit = {s: hit_lines(s) for s in seasons_all}
    pit = {s: pit_lines(s) for s in seasons_all}
    sprp = {s: sprp_lines(s) for s in seasons_all}
    xw = {s: xwoba(s) for s in PAIR_YEARS}
    consts = {s: season_constants(s) for s in seasons_all}
    fwar = {y + 1: fwar_pitching(y + 1) for y in PAIR_YEARS}
    log(f"loaded season lines {seasons_all[0]}-{seasons_all[-1]} in {time.time() - t0:.1f}s")

    res = {"artifact": "pitch_economy_partials", "lab_version": "pitch_economy_lab_v1",
           "registration": ["docs/ewar/PITCH_ECONOMY_LAB.md", "docs/ebr-2026-09-30/EBR_GATE.md part 11.4"],
           "measurement_only": True, "generated_at": _now(), "git_head": _git_head(),
           "bootstrap": {"B": b, "seed": SEED, "interval": "percentile 95", "cluster": "player (Part B: game)"},
           "statistic": "Spearman; partial = Pearson of rank residuals on the controls' ranks"}
    res["A"] = part_a(hit, xw, consts, b=b)
    log(f"Part A: {res['A']['pairs']} pairs ({time.time() - t0:.1f}s)")
    res["C"] = part_c(pit, fwar, b=b)
    log(f"Part C: {res['C']['pairs']} pairs ({time.time() - t0:.1f}s)")

    cv_doc = json.loads(COUNT_VALUE.read_text(encoding="utf-8"))
    dates = _game_dates()
    walked, outs = {}, {}
    for s in CORPUS_SEASONS:
        ts = time.time()
        blk = cv_doc["by_season"][str(s)]
        d = load_corpus_season(s)
        w = walk_corpus_season(s, d, blk["re288"], blk["re24"], dates)
        walked[s] = w
        outs[s] = play_outs(d)
        log(f"  corpus {s}: {w['receipt']['pa']:,} PA, identity {w['receipt']['identity_share']}, "
            f"{time.time() - ts:.1f}s")
        if (w["receipt"]["identity_share"] or 0.0) < IDENTITY_SHARE:
            raise LabRefused(f"corpus {s}: the RE288 identity holds on {w['receipt']['identity_share']} "
                             f"of plate appearances, under {IDENTITY_SHARE}; nothing is written")
    res["B"] = part_b({s: {"rows": walked[s]["rows"], "outs": outs[s]} for s in CORPUS_SEASONS},
                      {s: hit[s - 1] for s in CORPUS_SEASONS}, {s: sprp[s - 1] for s in CORPUS_SEASONS}, b=b)
    log(f"Part B: {res['B']['rows']} rows ({time.time() - t0:.1f}s)")

    # Part E first (the constants), then Part D on the frozen values
    tto_by, starter_rows = {}, []
    for s in CORPUS_SEASONS:
        tbl, per = tto_table(walked[s]["rows"])
        dl = pe.delta_tto(per, TTO_MIN_LATE)
        tto_by[str(s)] = {"by_pass": tbl, "delta_tto": _r(dl["delta_tto"]) if dl else None,
                          "starter_seasons": dl["starter_seasons"] if dl else 0}
        if s in pe.FIT_SEASONS:
            starter_rows.extend(per)
    fit_tto = pe.delta_tto(starter_rows, TTO_MIN_LATE)
    if fit_tto is None:
        raise LabRefused("delta_TTO could not be fitted")
    delta = fit_tto["delta_tto"]
    pitcher_batters = {s: {p for p, h in hit[s].items() if h["pos"] == "P"} for s in CORPUS_SEASONS}
    means, resid = {}, {}
    for s in CORPUS_SEASONS:
        clbar, pbar = class_means(walked[s]["rows"])
        means[s] = (clbar, pbar)
        resid[s] = hitter_residuals(walked[s]["rows"], clbar, pbar, pitcher_batters[s])
    k_cl = split_half({s: resid[s] for s in pe.FIT_SEASONS}, "cl")
    k_p = split_half({s: resid[s] for s in pe.FIT_SEASONS}, "p")
    constants = {"artifact": "pitch_economy_constants", "version": pe.PITCH_ECONOMY_VERSION,
                 "registration": "docs/ewar/PITCH_ECONOMY_LAB.md part 7; EBR_GATE.md 11.4.6",
                 "fit_seasons": list(pe.FIT_SEASONS), "generated_at": res["generated_at"],
                 "git_head": res["git_head"],
                 "delta_tto": {"value": _r(delta, 8), "starter_seasons": fit_tto["starter_seasons"],
                               "late_pa": fit_tto["late_pa"], "min_late": TTO_MIN_LATE,
                               "unit": "runs per plate appearance (RE24 run value)"},
                 "K_CL": dict(k_cl, floor=K_SPLIT_FLOOR_N, unit="plate appearances"),
                 "K_P": dict(k_p, floor=K_SPLIT_FLOOR_M, unit="plate appearances against starters"),
                 "K_clamp": list(pe.K_CLAMP),
                 "by_reference": {"K_O": pe.K_O, "K_B": pe.K_B, "source": "data/starter_workload_eval.json stage1.burn_in.priors"}}
    kcl = None if k_cl["K_infinite"] else k_cl["K"]
    kp = None if k_p["K_infinite"] else k_p["K"]

    # Part D2 (pitchers), same season
    d2 = {str(s): chain_season(s, pit[s], sprp[s], consts[s], delta) for s in D2_SEASONS}
    # Part D1 (hitters), same season
    d1 = {}
    for s in CORPUS_SEASONS:
        clbar, pbar = means[s]
        w_s = d2[str(s)]["w_per_pitch"]
        c = consts[s]
        g_raw, pa_all, rows300 = {}, {}, []
        for bat, h in resid[s].items():
            g_raw[bat] = pe.pe_h_raw(h["clres"], h["n"], h["pres"], h["m"], w_s, kcl, kp)
        for bat, hl in hit[s].items():
            if hl["pos"] == "P":
                continue
            pa_all[bat] = hl["pa"]
            g_raw.setdefault(bat, 0.0)
        d_peh = pe.recentre({k: v for k, v in g_raw.items() if k in pa_all}, pa_all)
        cl_raw: dict = {}
        for (bat, _gk, _dt_, _pid, _sp, cls, npit, cl, _rv, _pss, _half) in walked[s]["rows"]:
            if cls is None or npit == 0:
                continue
            cl_raw[bat] = cl_raw.get(bat, 0.0) + cl
        for bat, h in resid[s].items():
            hl = hit[s].get(bat)
            if not hl or hl["pa"] < HIT_FLOOR_PA:
                continue
            wo = woba_of(hl, c["weights"])
            if wo is None:
                continue
            wraa = (wo - c["lg_woba"]) / c["scale"] * hl["pa"]
            rows300.append((cl_raw.get(bat, 0.0) / h["n"], h["clres"] / h["n"], wraa / hl["pa"],
                            h["clres"], w_s * h["pres"], g_raw[bat], d_peh.get(bat, 0.0)))
        arr = np.asarray(rows300, float).reshape(-1, 7)
        d1[str(s)] = {
            "class_means": {"CLbar": {k: _r(v) for k, v in clbar.items()},
                            "pbar_vs_starter": {k: _r(v, 4) for k, v in pbar.items()}},
            "w_per_pitch": w_s, "hitters_counted": len(resid[s]), "hitters_300pa": int(len(arr)),
            "same_season": {
                "spearman_cl_pa_wraa_pa": _r(spearman(arr[:, 0], arr[:, 2])),
                "pearson_cl_pa_wraa_pa": _r(pearson(arr[:, 0], arr[:, 2])),
                "spearman_clres_pa_wraa_pa": _r(spearman(arr[:, 1], arr[:, 2])),
                "pearson_clres_pa_wraa_pa": _r(pearson(arr[:, 1], arr[:, 2]))},
            "sd_runs_300pa": {"CLres": _r(arr[:, 3].std(ddof=1), 4), "W": _r(arr[:, 4].std(ddof=1), 4),
                              "g_PEH": _r(arr[:, 5].std(ddof=1), 4), "d_PEH": _r(arr[:, 6].std(ddof=1), 4)},
            "zero_sum_d_peh_runs": _r(sum(d_peh.values()), 9),
            "re288_receipt": walked[s]["receipt"]}
    res["D"] = {"D1_hitters": d1, "D2_pitchers": d2, "tto": tto_by,
                "note": "same season only; no Y+1 quantity is read in Part D"}
    res["E"] = {"constants_file": "data/_labs/pitch_economy_constants.json",
                "delta_tto": constants["delta_tto"], "K_CL": constants["K_CL"], "K_P": constants["K_P"]}
    res["F"] = part_f(res["A"], res["C"])
    res["inputs"] = {"count_value_sha256": _sha_file(COUNT_VALUE), "fwar_vintage_sha256": _sha_file(VINTAGE),
                     "corpus_manifest_sha256": _sha_file(CORPUS / "manifest.json"),
                     "runner_manifest_sha256": _sha_file(RECORD / "manifest.json")}
    res["seconds"] = round(time.time() - t0, 1)
    _write_json(const_out, constants)
    _write_json(out, res)
    log(f"wrote {out} and {const_out} in {res['seconds']}s")
    return res


# ==========================================================================
# dry run: the reporting path on a synthetic fixture with nulls
# ==========================================================================
def fixture(seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    hit, pit, xw, consts, fwar = {}, {}, {}, {}, {}
    w = {"ubb": 0.69, "hbp": 0.72, "1b": 0.88, "2b": 1.25, "3b": 1.59, "hr": 2.05}
    for s in (2016, 2017, 2021, 2022):
        consts[s] = {"weights": w, "scale": 1.24, "lg_woba": 0.315, "cfip": 3.1, "rpw": 9.8,
                     "lg_pa": 180000, "lg_ip": 43000.0}
        hit[s], pit[s], xw[s] = {}, {}, {}
        for pid in range(1, 61):
            pa = float(rng.integers(250, 650))
            hit[s][pid] = {"pa": pa, "pitches": pa * rng.uniform(3.6, 4.2), "ab": pa * 0.88,
                           "bb": pa * rng.uniform(0.05, 0.12), "ibb": 1.0, "hbp": 3.0,
                           "so": pa * rng.uniform(0.15, 0.3), "sf": 4.0, "h": pa * 0.22,
                           "d2": pa * 0.045, "d3": 2.0, "hr": pa * 0.03,
                           "pos": "P" if pid == 1 else "SS", "name": f"h{pid}"}
            if pid % 7 != 0:                   # nulls: some hitters lack xwOBA
                xw[s][pid] = float(rng.uniform(0.28, 0.38))
        for pid in range(100, 140):
            gs = float(rng.integers(0, 32)) if pid % 2 else 0.0
            g = max(gs, float(rng.integers(20, 70)))
            outs = float(rng.integers(150, 600))
            tbf = outs * 1.4
            pit[s][pid] = {"g": g, "gs": gs, "outs": outs, "ip": outs / 3.0, "tbf": tbf,
                           "pitches": tbf * rng.uniform(3.7, 4.1), "k": tbf * 0.23, "bb": tbf * 0.08,
                           "hbp": 4.0, "hr": tbf * 0.03, "r": outs * 0.15, "er": outs * 0.14,
                           "pos": "P", "name": f"p{pid}"}
        fwar[s] = {pid: float(rng.normal(1, 1)) for pid in range(100, 140) if pid % 5}
    return {"hit": hit, "pit": pit, "xw": xw, "consts": consts, "fwar": fwar}


def dry_run(out: Path, *, b: int = 50, log=print) -> dict:
    out = Path(out).resolve()
    data_dir = (ROOT / "data").resolve()
    if data_dir == out or data_dir in out.parents:
        raise LabRefused("the dry run never writes under data/")
    fx = fixture()
    res = {"mode": "dry-run", "generated_at": _now()}
    res["A"] = part_a(fx["hit"], fx["xw"], fx["consts"], years=(2016, 2021), b=b)
    res["C"] = part_c(fx["pit"], fx["fwar"], years=(2016, 2021), b=b)
    res["F"] = part_f(res["A"], res["C"])
    sprp = {pid: {"SP": {"n": ln["gs"], "pitches": ln["pitches"] * 0.8, "outs": ln["outs"] * 0.8},
                  "RP": {"n": ln["g"] - ln["gs"], "pitches": ln["pitches"] * 0.2, "outs": ln["outs"] * 0.2}}
            for pid, ln in fx["pit"][2016].items()}
    sprp = {pid: {r: v for r, v in roles.items() if v["n"] > 0} for pid, roles in sprp.items()}
    res["D2"] = chain_season(2016, fx["pit"][2016], sprp, fx["consts"][2016], 0.01)
    res["E_split_half_null"] = pe.split_half_k(None, 300.0)
    _write_json(out, json.loads(json.dumps(res, default=lambda o: None if isinstance(o, float) and not math.isfinite(o) else str(o))))
    log(f"dry run wrote {out}")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.dry_run:
        if args.out is None:
            ap.error("--dry-run needs --out")
        dry_run(args.out)
        return 0
    if OUT.exists():
        raise LabRefused(f"{OUT} exists: the lab runs once (lab part 9)")
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
