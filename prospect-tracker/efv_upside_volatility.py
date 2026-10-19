# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV upside and volatility drivers (EFV_UPSIDE_VOLATILITY_DRIVERS; owner decision EW3-35,
registration docs/efv-v2/EFV_UPSIDE_VOLATILITY_DRIVERS.md, committed alone before this code).

The question: do upside markers (body frame and projectability, speed, athleticism, age for
level, statistical tails) or volatility markers (velocity change, workload spikes, prior
surgeries, IL history, delivery) carry information that PROSPX consensus FV has not priced,
for the EXPECTED outcome or only for the shape of the outcome distribution? Each marker is
read on the development frames, by side and position group, twice:

    mean          the within (frame, side, year) Spearman of a leave-one-year-out ridge score
                  on (consensus percentile, marker z, missing) minus consensus's, against the
                  frame's own label (lv_dev W3, vm_dev career WAR to date)
    distribution  a leave-one-year-out threshold logistic CDF of six-season fWAR (L6, fully
                  observed rows) on (consensus percentile) against (consensus percentile,
                  marker z, missing), scored by the threshold-weighted CRPS on a fixed WAR
                  grid and by the log loss of the bust, middle and star classes

with a player-clustered bootstrap, BH q within each (family, score), the consensus-only zero
comparator, a permuted-twin null comparator and a planted recovery check. DESCRIPTIVE: the
artifact is role development, adjudicates nothing, and its only output is the list of passing
markers handed to EFV_X3_POOLED_MODEL (docs/efv-v2/EFV_X3_CANDIDATE_LIST.md).

BANS. No served module imports this one and no served number moves. Nothing is grouped,
counted or averaged by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md): the groups are
frame, side, year, hitter position group and pitcher role, and the outcome classes are cut on
WAR. No reserved row (list vintages 2020 and 2021, debut cohorts 2025 and later) is built or
scored; backtest.run_backtest is never called; no projections retrain; no fetch.

Run:  python efv_upside_volatility.py --coverage   (marker coverage only: no label is read)
      python efv_upside_volatility.py --run         (the registered read; writes the artifact)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "_labs" / "efv5" / "efv_upside_volatility.json"
DOC = "docs/efv-v2/EFV_UPSIDE_VOLATILITY_DRIVERS.md"
TOOL = "efv_upside_volatility.py"
ITEM = "EFV_UPSIDE_VOLATILITY_DRIVERS"
DB_PATH = ROOT / "prospects.db"
TJ_PATH = DATA_DIR / "tj_surgery.json"

SIDES = ("hit", "pit")
FRAMES = ("lv_dev", "vm_dev")
FAMILIES = ("U", "V")
SCORES = ("mean", "crps", "logloss")

# ---------------------------------------------------------------------------
# registered constants (section 10, D-5)
# ---------------------------------------------------------------------------
LOOKBACK_DAYS = 730
PRIOR_GAP_DAYS = 300
SPIKE_IP = 30.0
STAR_WAR = 10.0
BUST_WAR = 0.0
GRID = (-1.0, 0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0, 22.0,
        26.0, 30.0)
LAMBDA_LOGIT = 1.0
RIDGE_ALPHA = 1.0
MIN_GROUP_ROWS = 20
MIN_ROWS = 150
MIN_MARKER = 40
MIN_CLASS = 15
K_NULL = 20
K_PLANT = 40
B_BOOT = 2000
B_PLANT = 500
RHO_M = 0.20
DELTA_T = 1.0
CANDIDATE_Q = 0.10
POWER_MIN = 0.80
SEED = 20261016
NULL_SEED = 20261017
QUAL_EXPOSURE = 100.0
SEASON_END_MMDD = "-10-01"
MINOR_SPORTS = (11, 12, 13, 14, 15, 16)
DROP_LEAGUES = frozenset({"MEX"})
RP_GS_SHARE = 0.5
POS_GROUP = {"C": "C", "SS": "SS", "CF": "CF", "2B": "IF", "3B": "IF", "IF": "IF",
             "INF": "IF", "UTIL": "IF", "UT": "IF", "MI": "IF", "CI": "IF",
             "LF": "COF", "RF": "COF", "OF": "COF", "1B": "1B/DH", "DH": "1B/DH"}
HIT_GROUPS = ("all", "C", "SS", "CF", "IF", "COF", "1B/DH")
PIT_GROUPS = ("all", "SP", "RP")
LEVERS = {"short": -1.0, "med": 0.0, "long": 1.0}

#: id -> (family, sides, name, label)
MARKERS: dict[str, tuple[str, tuple[str, ...], str, str]] = {
    "U01": ("U", ("hit", "pit"), "height_in", "height, inches"),
    "U02": ("U", ("hit", "pit"), "weight_lb", "weight, pounds"),
    "U03": ("U", ("hit", "pit"), "frame_resid", "weight less its height-and-age prediction"),
    "U04": ("U", ("hit", "pit"), "fg_frame", "FanGraphs frame"),
    "U05": ("U", ("hit", "pit"), "fg_athl", "FanGraphs athleticism"),
    "U06": ("U", ("hit", "pit"), "fg_levers", "FanGraphs levers"),
    "U07": ("U", ("hit",), "run_grade", "consensus run grade"),
    "U08": ("U", ("hit",), "sb_rate", "stolen bases per time on first"),
    "U09": ("U", ("hit",), "triple_rate", "triples per ball in play"),
    "U10": ("U", ("hit",), "athl_comp", "athleticism composite"),
    "U11": ("U", ("hit", "pit"), "age_rel_level", "age for level"),
    "U12": ("U", ("hit",), "iso_peak_z", "peak ISO against level"),
    "U13": ("U", ("hit",), "contact_peak_z", "peak contact (low K%) against level"),
    "U14": ("U", ("hit",), "max_ev", "max exit velocity"),
    "U15": ("U", ("pit",), "k_peak_z", "peak K% against level"),
    "U16": ("U", ("pit",), "bb_best_z", "best (lowest) BB% against level"),
    "U17": ("U", ("pit",), "fb_tops", "fastball top velocity"),
    "U18": ("U", ("pit",), "fb_sits", "fastball sitting velocity"),
    "V01": ("V", ("pit",), "velo_change", "sitting velocity change"),
    "V02": ("V", ("pit",), "tops_change", "top velocity change"),
    "V03": ("V", ("pit",), "workload_spike", "innings over prior high"),
    "V04": ("V", ("pit",), "workload_spike_flag", "innings spike of 30 or more"),
    "V05": ("V", ("hit", "pit"), "surgery_count", "prior Tommy John or UCL procedures"),
    "V06": ("V", ("hit", "pit"), "il_stints", "IL stints"),
    "V07": ("V", ("hit", "pit"), "il_days", "IL days, log1p"),
    "V08": ("V", ("hit", "pit"), "il_recurrent", "repeated IL stints"),
    "V09": ("V", ("hit", "pit"), "il_60day", "60-day IL stints"),
    "V10": ("V", ("pit",), "fg_delivery", "FanGraphs delivery"),
}


class LookAheadError(AssertionError):
    pass


def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def markers_for(side: str) -> list[str]:
    return [m for m, (_f, sides, _n, _l) in MARKERS.items() if side in sides]


def groups_for(side: str) -> tuple[str, ...]:
    return HIT_GROUPS if side == "hit" else PIT_GROUPS


# ---------------------------------------------------------------------------
# parsing (outcome-free)
# ---------------------------------------------------------------------------

def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def parse_height(v) -> float | None:
    """Inches from 6' 2 (FanGraphs) or a number of inches."""
    if v is None:
        return None
    x = _f(v)
    if x is not None:
        return x if 55 <= x <= 90 else None
    m = re.match(r"\s*(\d)\s*'\s*(\d{1,2})?", str(v))
    if not m:
        return None
    inch = 12.0 * int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)
    return inch if 55 <= inch <= 90 else None


def parse_velo(v) -> float | None:
    """The midpoint of a printed range (92-95 reads 93.5), or the single number."""
    if v is None:
        return None
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(v))]
    nums = [n for n in nums if 60 <= n <= 110]
    if not nums:
        return None
    return float(np.mean(nums[:2]))


def parse_levers(v) -> float | None:
    return LEVERS.get(str(v or "").strip().lower())


def parse_scale(v) -> float | None:
    """A FanGraphs -2 to 2 scale value."""
    x = _f(v)
    return x if x is not None and -2 <= x <= 2 else None


def outs_of(ip) -> float:
    whole, _, frac = str(ip or "0").partition(".")
    try:
        return float(int(whole or 0) * 3 + (int(frac[:1]) if frac else 0))
    except ValueError:
        return 0.0


def _day(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# sources (read only)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def fg_boards() -> dict[str, list[tuple[str, dict]]]:
    """{player_key: [(snapshot_date, FanGraphs extras)]} sorted by date."""
    out: dict[str, list[tuple[str, dict]]] = {}
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("select player_key, snapshot_date, tools_json from snapshots "
                           "where source = 'fangraphs'").fetchall()
    finally:
        con.close()
    for pk, sd, tj in rows:
        if not pk or not sd:
            continue
        try:
            t = json.loads(tj) if tj else {}
        except ValueError:
            continue
        ex = t.get("_extras") if isinstance(t, dict) else None
        if isinstance(ex, dict):
            out.setdefault(pk, []).append((str(sd)[:10], ex))
    for v in out.values():
        v.sort(key=lambda e: e[0])
    return out


def board_asof(boards: list[tuple[str, dict]], A: str, field: str,
               parse=None) -> tuple[str, float] | None:
    """(date, value) of the latest board dated on or before A, within the lookback, that
    carries the field."""
    lo = (_day(A) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    best = None
    for d, ex in boards:
        if d > A:
            break
        if d < lo:
            continue
        v = ex.get(field)
        if v in (None, ""):
            continue
        x = parse(v) if parse else _f(v)
        if x is not None:
            best = (d, x)
    if best is not None and best[0] > A:
        raise LookAheadError(f"board {best[0]} after {A}")
    return best


def change_asof(boards, A: str, field: str, parse) -> float | None:
    """Value on the latest board at A minus value on the latest board dated at least
    PRIOR_GAP_DAYS earlier (inside the lookback)."""
    cur = board_asof(boards, A, field, parse)
    if cur is None:
        return None
    prior_cap = (_day(cur[0]) - timedelta(days=PRIOR_GAP_DAYS)).isoformat()
    lo = (_day(A) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    prev = None
    for d, ex in boards:
        if d > prior_cap:
            break
        if d < lo:
            continue
        x = parse(ex.get(field)) if ex.get(field) not in (None, "") else None
        if x is not None:
            prev = (d, x)
    return None if prev is None else cur[1] - prev[1]


@lru_cache(maxsize=1)
def bio_panel() -> dict:
    import efv_drivers as DRV
    return DRV.load_bio_panel()


def panel_asof(player_key: str, A: str) -> tuple[float | None, float | None]:
    lo = (_day(A) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    best = None
    for e in bio_panel().get(player_key) or ():
        d = str(e.get("vintage") or "")[:10]
        if not d or d > A or d < lo:
            continue
        if best is None or d > best[0]:
            best = (d, e)
    if best is None:
        return None, None
    e = best[1]
    return parse_height(e.get("h")), _f(e.get("w"))


@lru_cache(maxsize=1)
def universe() -> dict:
    import efv_vintage_frame as F
    return F.load_universe()


def tools_asof(player_key: str, A: str) -> dict:
    lo = (_day(A) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    best = None
    for p in (universe().get(player_key) or {}).get("points") or ():
        d = str(p.get("snapshot_date") or "")[:10]
        if not d or d > A or d < lo:
            continue
        if best is None or d >= best[0]:
            best = (d, p.get("tools_consensus") or {})
    return {} if best is None else {k: _f(v) for k, v in best[1].items()}


@lru_cache(maxsize=1)
def tj_index() -> dict[int, list[str]]:
    d = json.loads(TJ_PATH.read_text(encoding="utf-8"))
    out: dict[int, list[str]] = {}
    for k, entries in (d.get("players") or {}).items():
        try:
            pid = int(k)
        except (TypeError, ValueError):
            continue
        out[pid] = sorted(str(e.get("date") or "")[:10] for e in entries
                          if _day(e.get("date")) is not None)
    return out


def surgeries_before(mlbam, C: str) -> float | None:
    try:
        pid = int(mlbam)
    except (TypeError, ValueError):
        return None
    return float(sum(1 for d in tj_index().get(pid, ()) if d < C))


@lru_cache(maxsize=1)
def il_index():
    import efv_w2_il_backfill as IL
    return IL.stint_index()


# ---------------------------------------------------------------------------
# MiLB lines
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def season_lines(season: int, side: str) -> tuple:
    """Affiliated (non-MLB) lines of a season, MEX dropped."""
    import milb_history as mh
    grp = "hitting" if side == "hit" else "pitching"
    out = []
    for sp in MINOR_SPORTS:
        for r in mh.season_splits(sp, int(season), grp, fetch=False):
            if not r.get("mlbam") or (r.get("league") or "") in DROP_LEAGUES:
                continue
            e = _f(r.get("pa")) if side == "hit" else _f(r.get("bf"))
            if not e or e <= 0:
                continue
            out.append(r)
    return tuple(out)


@lru_cache(maxsize=None)
def by_player(season: int, side: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in season_lines(season, side):
        out.setdefault(int(r["mlbam"]), []).append(r)
    return out


def _n(r, k) -> float:
    return _f(r.get(k)) or 0.0


def _rates(lines: list[dict], side: str) -> dict:
    s = {k: sum(_n(r, k) for r in lines) for k in ("pa", "ab", "h", "doubles", "triples",
                                                    "hr", "bb", "hbp", "sf", "so", "sb",
                                                    "bf")}
    out = {}
    if side == "hit":
        if s["pa"] > 0:
            out["k"] = s["so"] / s["pa"]
            out["exp"] = s["pa"]
        if s["ab"] > 0:
            out["iso"] = (s["doubles"] + 2 * s["triples"] + 3 * s["hr"]) / s["ab"]
    else:
        if s["bf"] > 0:
            out["k"] = s["so"] / s["bf"]
            out["bb"] = s["bb"] / s["bf"]
            out["exp"] = s["bf"]
    return out


@lru_cache(maxsize=None)
def level_norms(season: int, side: str) -> dict:
    """{level: {stat: (mean, sd)}} over the qualified lines of the level-season."""
    by: dict = {}
    for r in season_lines(season, side):
        rt = _rates([r], side)
        if rt.get("exp", 0) < QUAL_EXPOSURE:
            continue
        for st, v in rt.items():
            if st != "exp":
                by.setdefault(r.get("level"), {}).setdefault(st, []).append(v)
    return {lv: {st: (float(np.mean(v)), float(np.std(v))) for st, v in d.items()
                 if len(v) >= 30}
            for lv, d in by.items()}


@lru_cache(maxsize=None)
def level_mean_age(season: int, side: str) -> dict:
    num: dict = {}
    den: dict = {}
    for r in season_lines(season, side):
        a = _f(r.get("age"))
        e = _f(r.get("pa")) if side == "hit" else _f(r.get("bf"))
        if a is None or not e:
            continue
        num[r.get("level")] = num.get(r.get("level"), 0.0) + a * e
        den[r.get("level")] = den.get(r.get("level"), 0.0) + e
    return {k: num[k] / den[k] for k in num if den[k] > 0}


def _main_level(lines: list[dict], side: str) -> tuple[str | None, list[dict]]:
    exp: dict = {}
    for r in lines:
        e = _f(r.get("pa")) if side == "hit" else _f(r.get("bf"))
        exp[r.get("level")] = exp.get(r.get("level"), 0.0) + (e or 0.0)
    if not exp:
        return None, []
    lv = max(sorted(exp), key=lambda k: exp[k])
    return lv, [r for r in lines if r.get("level") == lv]


def milb_window(year: int, cutoff: str | None) -> list[int]:
    import efv_x1_translate as X1
    T = X1.top_season(int(year), cutoff)
    return X1._played_window(T, 3)


def milb_markers(mlbam, year: int, cutoff: str | None, side: str) -> dict:
    """The MiLB-line markers of one row (U08, U09, U11, U12, U13, U15, U16, V03, V04)
    and the pitcher role on season T."""
    out: dict = {"sb_rate": None, "triple_rate": None, "age_rel_level": None,
                 "iso_peak_z": None, "contact_peak_z": None, "k_peak_z": None,
                 "bb_best_z": None, "workload_spike": None, "workload_spike_flag": None,
                 "_role": None, "_age_T": None}
    if not mlbam:
        return out
    pid = int(mlbam)
    win = milb_window(year, cutoff)
    asof = str(cutoff)[:10] if cutoff else f"{int(year)}-01-01"
    got = []
    for s in win:
        if f"{s}{SEASON_END_MMDD}" > asof:
            raise LookAheadError(f"season {s} ended after {asof}")
        ls = by_player(s, side).get(pid)
        if ls:
            got.append((s, ls))
    if not got:
        return out
    T = win[0]
    # age for level: the newest season with a line
    s0, l0 = got[0]
    # the age U03 reads: the exposure-weighted season age of the newest season with a line,
    # carried to season T. Outcome-blind (the line ages); the frame row's birth date is NOT
    # used, because on lv_dev it is present almost only for players who later reached MLB.
    wa = [(_f(r.get("age")), _f(r.get("pa")) if side == "hit" else _f(r.get("bf")))
          for r in l0]
    wa = [(a, e) for a, e in wa if a is not None and e]
    if wa:
        out["_age_T"] = (sum(a * e for a, e in wa) / sum(e for _a, e in wa)
                         + float(T - s0))
    lv, main = _main_level(l0, side)
    ages = [_f(r.get("age")) for r in main if _f(r.get("age")) is not None]
    mean_age = level_mean_age(s0, side).get(lv)
    if ages and mean_age is not None:
        out["age_rel_level"] = float(np.mean(ages)) - mean_age
    # peaks against the level-season
    peaks: dict = {}
    for s, ls in got:
        lv, main = _main_level(ls, side)
        rt = _rates(main, side)
        if rt.get("exp", 0) < QUAL_EXPOSURE:
            continue
        nm = level_norms(s, side).get(lv) or {}
        for st, sign, name in ((("iso", 1, "iso_peak_z"), ("k", -1, "contact_peak_z"))
                               if side == "hit" else
                               (("k", 1, "k_peak_z"), ("bb", -1, "bb_best_z"))):
            if st in rt and st in nm and nm[st][1] > 0:
                z = sign * (rt[st] - nm[st][0]) / nm[st][1]
                peaks[name] = max(peaks.get(name, -np.inf), z)
    for k, v in peaks.items():
        out[k] = float(v)
    if side == "hit":
        allines = [r for _s, ls in got for r in ls]
        pa = sum(_n(r, "pa") for r in allines)
        if pa >= QUAL_EXPOSURE:
            singles = sum(_n(r, "h") - _n(r, "doubles") - _n(r, "triples") - _n(r, "hr")
                          for r in allines)
            on1 = singles + sum(_n(r, "bb") + _n(r, "hbp") for r in allines)
            if on1 > 0:
                out["sb_rate"] = sum(_n(r, "sb") for r in allines) / on1
            bip = sum(_n(r, "ab") - _n(r, "so") - _n(r, "hr") + _n(r, "sf") for r in allines)
            if bip > 0:
                out["triple_rate"] = sum(_n(r, "triples") for r in allines) / bip
        return out
    seasons = dict(got)
    if T in seasons:
        g = sum(_n(r, "g") for r in seasons[T])
        gs = sum(_n(r, "gs") for r in seasons[T])
        if g > 0:
            out["_role"] = "SP" if gs / g >= RP_GS_SHARE else "RP"
        prior = [sum(outs_of(r.get("ip")) for r in seasons[s]) / 3.0 for s in win[1:]
                 if s in seasons]
        if prior:
            ip_t = sum(outs_of(r.get("ip")) for r in seasons[T]) / 3.0
            out["workload_spike"] = ip_t - max(prior)
            out["workload_spike_flag"] = float(out["workload_spike"] >= SPIKE_IP)
    return out


# ---------------------------------------------------------------------------
# rows and markers
# ---------------------------------------------------------------------------

def build_rows(log=print) -> dict:
    """{fid: {side: [row]}}: the scored rows of both development frames with the facts the
    markers read (ids, as-of dates, position, birth date) and the L6 label. Guards first."""
    _tools()
    import efv_v2_assemble as ASM
    import efv_v2_model as H
    import efv_v2_model_class_screen as MCS
    import efv_vintage_frame as F
    import efv_w2_il_backfill as IL
    frames_lv = ASM.build_frames()
    if any(int(V) in F.RESERVED_LV for s in F.SIDES for V in frames_lv[s]):
        raise F.ReservedFrameError("lv frames carry a reserved vintage")
    orig = ASM.build_frames
    ASM.build_frames = lambda *a, **k: frames_lv
    try:
        inputs = MCS.build_inputs(log=log)
    finally:
        ASM.build_frames = orig
    out: dict = {"lv_dev": {}, "vm_dev": {}}
    for side in F.SIDES:
        lv_by = {}
        for V, (rows, labs) in frames_lv[side].items():
            for r, lab in zip(rows, labs):
                lv_by[(r["player_key"], int(V))] = (r, lab)
        rows = []
        for V, blk in inputs["frames"]["lv_dev"]["by_side"][side].items():
            if int(V) in F.RESERVED_LV:
                raise F.ReservedFrameError(f"lv_dev reaches {V}")
            for c in blk["scored"]:
                fr, lab = lv_by.get((c["key"], int(V))) or ({}, {})
                l6 = lab.get("l6")
                rows.append({
                    "key": c["key"], "side": side, "year": int(V), "frame": "lv_dev",
                    "group": f"lv_dev|{side}|{int(V)}", "rk": f"lv_dev|{c['key']}|{int(V)}",
                    "cons": float(c["grades"]["prospx_consensus"]),
                    "y": float(c["outcome"]["war"]),
                    "l6": (float(l6) if (l6 is not None and lab.get("l6_censored") is False)
                           else None),
                    "mlbam": fr.get("mlbam_id"), "milb_cutoff": (fr.get("window") or [None])[0],
                    "A": str(fr.get("asof_date") or f"{int(V)}-01-01")[:10],
                    "C": IL.lv_cutoff(int(V)),
                    "position": fr.get("position")})
        out["lv_dev"][side] = rows
        raw = {r["player_key"]: r for r in json.loads(
            H._matrix_path(side).read_text(encoding="utf-8"))}
        mine: dict = {}
        H.pinned_inputs(side, H.matrix_training_rows(side), mine)
        rows = []
        for yr, blk in inputs["frames"]["vm_dev"]["by_side"][side].items():
            if int(yr) >= F.R_VM_FIRST_DEBUT_YEAR:
                raise F.ReservedFrameError(f"vm_dev reaches R-VM: {yr}")
            for c in blk["scored"]:
                rw = raw.get(c["key"]) or {}
                asof = (mine.get(c["key"]) or {}).get("asof_date")
                t6 = rw.get("target_resolved")
                rows.append({
                    "key": c["key"], "side": side, "year": int(yr), "frame": "vm_dev",
                    "group": f"vm_dev|{side}|{int(yr)}", "rk": f"vm_dev|{c['key']}|{int(yr)}",
                    "cons": float(c["grades"]["prospx_consensus"]),
                    "y": float(c["outcome"]["war"]),
                    "l6": (float(t6) if (t6 is not None and rw.get("censored") is False)
                           else None),
                    "mlbam": rw.get("mlbam_id"), "milb_cutoff": asof,
                    "A": str(asof or f"{int(yr)}-01-01")[:10],
                    "C": IL.vm_cutoff(rw, int(yr)),
                    "position": rw.get("position")})
        out["vm_dev"][side] = rows
    return out


def row_facts(r: dict) -> dict:
    """Every outcome-free fact the markers read for one row (the cell-level markers U03 and
    U10 are finished in cell_values / group_values)."""
    import efv_w2_il_backfill as IL
    side, A, C = r["side"], r["A"], r["C"]
    b = fg_boards().get(r["key"]) or []
    out: dict = {}
    h = board_asof(b, A, "height", parse_height)
    w = board_asof(b, A, "weight")
    ph, pw = panel_asof(r["key"], A)
    out["height_in"] = h[1] if h else ph
    out["weight_lb"] = w[1] if w else pw
    for name, field, parse in (("fg_frame", "frame", parse_scale),
                               ("fg_athl", "athl", parse_scale),
                               ("fg_levers", "levers", parse_levers),
                               ("max_ev", "max_ev", None),
                               ("fb_tops", "tops", None),
                               ("fb_sits", "sits", parse_velo),
                               ("fg_delivery", "delivery", parse_scale)):
        got = board_asof(b, A, field, parse)
        out[name] = got[1] if got else None
    if side == "hit":
        out["max_ev"] = out["max_ev"] if out["max_ev"] and 85 <= out["max_ev"] <= 125 else None
        out["fb_tops"] = out["fb_sits"] = out["fg_delivery"] = None
        t = tools_asof(r["key"], A)
        out["run_grade"] = t.get("speed")
        out["_field"] = t.get("field")
        out["_arm"] = t.get("throw")
    else:
        out["max_ev"] = None
        out["fb_tops"] = out["fb_tops"] if out["fb_tops"] and 80 <= out["fb_tops"] <= 106 else None
        out["velo_change"] = change_asof(b, A, "sits", parse_velo)
        out["tops_change"] = change_asof(b, A, "tops", lambda v: _f(v))
    out.update(milb_markers(r.get("mlbam"), r["year"], r.get("milb_cutoff"), side))
    out["_age_A"] = out.pop("_age_T")
    out["surgery_count"] = surgeries_before(r.get("mlbam"), C)
    il = IL.asof(r.get("mlbam"), C, il_index())
    out["il_stints"] = il.get("il_stints_pre")
    out["il_days"] = (None if il.get("il_days_pre") is None
                      else math.log1p(float(il["il_days_pre"])))
    out["il_recurrent"] = il.get("il_recurrent_pre")
    out["il_60day"] = il.get("il_60day_pre")
    # the listing position's first token (efv5_atlas.position_group: SS/2B reads SS)
    pos = POS_GROUP.get(str(r.get("position") or "").upper().split("/")[0].strip())
    out["_group"] = pos if side == "hit" else out.get("_role")
    return out


def _z(v: np.ndarray) -> np.ndarray:
    have = ~np.isnan(v)
    out = np.full(v.shape, np.nan)
    if have.sum() >= 2:
        sd = float(np.std(v[have]))
        out[have] = (v[have] - float(np.mean(v[have]))) / sd if sd > 0 else 0.0
    return out


def group_values(rows: list[dict], facts: dict) -> None:
    """U10 (hitters): the mean of the within (frame, side, year) z of the run, field and
    arm grades and FanGraphs athleticism, at least two present. Written into facts."""
    by: dict = {}
    for r in rows:
        by.setdefault(r["group"], []).append(r["rk"])
    for _g, rks in by.items():
        comps = []
        for k in ("run_grade", "_field", "_arm", "fg_athl"):
            v = np.array([np.nan if facts[rk].get(k) is None else facts[rk][k] for rk in rks])
            comps.append(_z(v))
        M = np.vstack(comps)
        cnt = (~np.isnan(M)).sum(axis=0)
        tot = np.where(np.isnan(M), 0.0, M).sum(axis=0)
        for i, rk in enumerate(rks):
            facts[rk]["athl_comp"] = None if cnt[i] < 2 else float(tot[i] / cnt[i])


def cell_values(rows: list[dict], facts: dict, name: str) -> dict:
    """{rk: value | None} for one marker on a cell's rows. U03 is the residual of weight on
    (1, height, age) fitted inside each (frame, side, year) group on the cell's rows."""
    if name != "frame_resid":
        return {r["rk"]: facts[r["rk"]].get(name) for r in rows}
    out = {r["rk"]: None for r in rows}
    by: dict = {}
    for r in rows:
        f = facts[r["rk"]]
        if None not in (f.get("height_in"), f.get("weight_lb"), f.get("_age_A")):
            by.setdefault(r["group"], []).append(r["rk"])
    for _g, rks in by.items():
        if len(rks) < 5:
            continue
        X = np.array([[1.0, facts[k]["height_in"], facts[k]["_age_A"]] for k in rks])
        y = np.array([facts[k]["weight_lb"] for k in rks])
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        for k, e in zip(rks, y - X @ b):
            out[k] = float(e)
    return out


# ---------------------------------------------------------------------------
# the design (per cell)
# ---------------------------------------------------------------------------

def _pct(v: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    return rankdata(v, method="average") / max(len(v), 1)


def design(rows: list[dict], vals: dict, target: str) -> tuple:
    """Per row (u_c, z, m, u_t) inside each (frame, side, year) group; u_t the target's
    percentile (target 'y'), or None for the distribution read."""
    n = len(rows)
    uc, z, m, ut = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    by: dict = {}
    for i, r in enumerate(rows):
        by.setdefault(r["group"], []).append(i)
    for _g, ix in by.items():
        ix = np.asarray(ix)
        uc[ix] = _pct(np.array([rows[i]["cons"] for i in ix]))
        if target == "y":
            ut[ix] = _pct(np.array([rows[i]["y"] for i in ix]))
        v = np.array([np.nan if vals.get(rows[i]["rk"]) is None else float(vals[rows[i]["rk"]])
                      for i in ix])
        zz = _z(v)
        z[ix] = np.where(np.isnan(zz), 0.0, zz)
        m[ix] = np.isnan(v).astype(float)
    return uc, z, m, ut


def loyo_ridge(rows: list[dict], X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Leave-one-year-out ridge inside each frame (intercept free)."""
    P = np.eye(X.shape[1]) * RIDGE_ALPHA
    P[0, 0] = 0.0
    frames = np.array([r["frame"] for r in rows])
    years = np.array([r["year"] for r in rows])
    out = np.zeros(len(rows))
    for fid in np.unique(frames):
        for yr in np.unique(years[frames == fid]):
            te = (frames == fid) & (years == yr)
            tr = (frames == fid) & (years != yr)
            if tr.sum() < 10:
                out[te] = X[te, 1]
                continue
            b = np.linalg.solve(X[tr].T @ X[tr] + P, X[tr].T @ y[tr])
            out[te] = X[te] @ b
    return out


def mean_score(rows: list[dict], vals: dict) -> np.ndarray:
    uc, z, m, ut = design(rows, vals, "y")
    X = np.column_stack([np.ones(len(rows)), uc, z, m])
    return loyo_ridge(rows, X, ut)


def _within(score, rows, idx=None) -> tuple[float | None, float | None]:
    import efv_v2_stat as S
    codes = np.asarray([r["group"] for r in rows])
    keep = S.kept_groups(codes, MIN_GROUP_ROWS)
    a = np.asarray(score, dtype=np.float64)
    b = np.asarray([r["cons"] for r in rows], dtype=np.float64)
    y = np.asarray([r["y"] for r in rows], dtype=np.float64)
    ix = np.arange(len(rows)) if idx is None else idx
    return S._within_pair(a, b, y, codes, keep, ix)


def mean_delta_point(rows, vals) -> float | None:
    pa, pb = _within(mean_score(rows, vals), rows)
    return None if pa is None or pb is None else float(pa - pb)


def mean_read(rows: list[dict], vals: dict, *, B: int, seed: int = SEED) -> dict:
    import efv_v2_stat as S
    score = mean_score(rows, vals)
    d = S.paired_delta([r["key"] for r in rows], [r["group"] for r in rows],
                       [r["y"] for r in rows], [False] * len(rows), score,
                       [r["cons"] for r in rows], [r["cons"] for r in rows],
                       statistic="within", B=B, seed=seed, min_rows=MIN_GROUP_ROWS)
    p = None
    if d.get("p_gt_0") is not None and d.get("B_used"):
        p = max(1.0 - float(d["p_gt_0"]), 1.0 / (int(d["B_used"]) + 1))
    per_frame = {}
    for fid in FRAMES:
        sub = [i for i, r in enumerate(rows) if r["frame"] == fid]
        if sub:
            pa, pb = _within(score, rows, np.asarray(sub))
            per_frame[fid] = None if pa is None or pb is None else round(pa - pb, 5)
    return {"delta": d.get("delta"), "ci95": d.get("ci95"), "p": p, "status": d.get("status"),
            "n": d.get("n"), "n_clusters": d.get("n_clusters"),
            "rows_in_kept_groups": d.get("rows_in_kept_groups"), "per_frame": per_frame}


# ---------------------------------------------------------------------------
# the distribution read
# ---------------------------------------------------------------------------

def grid_weights(grid=GRID) -> np.ndarray:
    g = np.asarray(grid, dtype=np.float64)
    w = np.zeros(g.size)
    w[1:] += np.diff(g) / 2.0
    w[:-1] += np.diff(g) / 2.0
    return w


W_GRID = grid_weights()
J_BUST = GRID.index(BUST_WAR)
J_STAR = GRID.index(STAR_WAR)


def fit_threshold_logit(X: np.ndarray, Yb: np.ndarray, lam: float = LAMBDA_LOGIT,
                        iters: int = 50, tol: float = 1e-8) -> np.ndarray:
    """Ridge logistic per threshold column of Yb (n, J), all at once by Newton steps.
    Returns coefficients (p, J); a degenerate column gets None-marked NaN coefficients."""
    n, p = X.shape
    J = Yb.shape[1]
    B = np.zeros((p, J))
    R = np.eye(p) * lam
    R[0, 0] = 0.0
    frac = Yb.mean(axis=0)
    ok = (frac > 0) & (frac < 1)
    B[0, ok] = np.log(frac[ok] / (1 - frac[ok]))
    for _ in range(iters):
        eta = np.clip(X @ B, -30, 30)
        P = 1.0 / (1.0 + np.exp(-eta))
        G = X.T @ (P - Yb) + R @ B
        Wt = P * (1 - P)
        H = np.einsum("ni,nj,nk->jik", X, Wt, X) + R[None, :, :]
        step = np.linalg.solve(H, G.T[:, :, None])[:, :, 0].T
        B -= step
        if not ok.any() or float(np.max(np.abs(step[:, ok]))) < tol:
            break
    B[:, ~ok] = np.nan
    return B


def predict_cdf(Xtr, ytr, Xte) -> np.ndarray:
    g = np.asarray(GRID)
    Yb = (ytr[:, None] <= g[None, :]).astype(float)
    B = fit_threshold_logit(Xtr, Yb)
    Fte = np.zeros((Xte.shape[0], g.size))
    for j in range(g.size):
        if np.isnan(B[0, j]):
            Fte[:, j] = (Yb[:, j].sum() + 0.5) / (Yb.shape[0] + 1.0)
        else:
            Fte[:, j] = 1.0 / (1.0 + np.exp(-np.clip(Xte @ B[:, j], -30, 30)))
    return np.maximum.accumulate(Fte, axis=1)


def crps_rows(Fm: np.ndarray, y: np.ndarray) -> np.ndarray:
    ind = (y[:, None] <= np.asarray(GRID)[None, :]).astype(float)
    return ((Fm - ind) ** 2 * W_GRID[None, :]).sum(axis=1)


def class_of(y: np.ndarray) -> np.ndarray:
    """0 BUST (at or below 0), 2 STAR (above STAR_WAR), 1 MID."""
    return np.where(y <= BUST_WAR, 0, np.where(y > STAR_WAR, 2, 1))


def logloss_rows(Fm: np.ndarray, y: np.ndarray) -> np.ndarray:
    pb = Fm[:, J_BUST]
    ps = 1.0 - Fm[:, J_STAR]
    pm = Fm[:, J_STAR] - Fm[:, J_BUST]
    P = np.clip(np.column_stack([pb, pm, ps]), 1e-6, None)
    c = class_of(y)
    return -np.log(P[np.arange(len(y)), c])


def dist_scores(rows: list[dict], vals: dict | None) -> tuple[np.ndarray, np.ndarray]:
    """Per-row (CRPS, log loss) of the leave-one-year-out CDF on (u_c) when vals is None,
    else on (u_c, z, m). rows: L6 rows only."""
    uc, z, m, _ = design(rows, vals or {}, "none")
    one = np.ones(len(rows))
    X = np.column_stack([one, uc]) if vals is None else np.column_stack([one, uc, z, m])
    y = np.array([r["l6"] for r in rows], dtype=np.float64)
    frames = np.array([r["frame"] for r in rows])
    years = np.array([r["year"] for r in rows])
    Fm = np.zeros((len(rows), len(GRID)))
    for fid in np.unique(frames):
        for yr in np.unique(years[frames == fid]):
            te = (frames == fid) & (years == yr)
            tr = (frames == fid) & (years != yr)
            if tr.sum() < 10:
                # too few training rows: the training rows' empirical CDF (0.5 with none)
                emp = ((y[tr][:, None] <= np.asarray(GRID)[None, :]).mean(axis=0)
                       if tr.any() else np.full(len(GRID), 0.5))
                Fm[te] = np.tile(emp, (int(te.sum()), 1))
                continue
            Fm[te] = predict_cdf(X[tr], y[tr], X[te])
    return crps_rows(Fm, y), logloss_rows(Fm, y)


def cluster_boot(diff: np.ndarray, keys: list[str], *, B: int, seed: int) -> dict:
    """Mean of the paired row differences with a player-clustered bootstrap."""
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    cid = np.array([ids[k] for k in keys])
    nc = len(ids)
    s = np.bincount(cid, weights=diff, minlength=nc)
    c = np.bincount(cid, minlength=nc).astype(float)
    rng = np.random.default_rng(seed)
    draws = np.empty(B)
    for b in range(B):
        w = np.bincount(rng.integers(0, nc, nc), minlength=nc)
        draws[b] = (w @ s) / (w @ c)
    mean = float(diff.mean())
    q = np.quantile(draws, [0.025, 0.975])
    p = max(float((draws <= 0).mean()), 1.0 / (B + 1))
    return {"delta": round(mean, 6), "ci95": [round(float(q[0]), 6), round(float(q[1]), 6)],
            "p": p, "n": int(diff.size), "n_clusters": nc}


def dist_read(rows: list[dict], vals: dict, *, B: int, seed: int = SEED,
              base: tuple | None = None) -> dict:
    cb, lb = base if base is not None else dist_scores(rows, None)
    cc, lc = dist_scores(rows, vals)
    keys = [r["key"] for r in rows]
    out = {}
    for name, a, b in (("crps", cb, cc), ("logloss", lb, lc)):
        d = a - b
        res = cluster_boot(d, keys, B=B, seed=seed) if B else {"delta": float(d.mean())}
        res["per_frame"] = {fid: round(float(d[[r["frame"] == fid for r in rows]].mean()), 6)
                            for fid in FRAMES if any(r["frame"] == fid for r in rows)}
        out[name] = res
    return out


def dist_delta_point(rows, vals, base) -> dict:
    cb, lb = base
    cc, lc = dist_scores(rows, vals)
    return {"crps": float((cb - cc).mean()), "logloss": float((lb - lc).mean())}


# ---------------------------------------------------------------------------
# comparators, BH, rule
# ---------------------------------------------------------------------------

def permute_within(rows: list[dict], vals: dict, rng) -> dict:
    by: dict = {}
    for r in rows:
        by.setdefault(r["group"], []).append(r["rk"])
    out = {}
    for g in sorted(by):
        ks = by[g]
        v = [vals.get(k) for k in ks]
        perm = rng.permutation(len(ks))
        for i, k in enumerate(ks):
            out[k] = v[int(perm[i])]
    return out


def bh(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg q values, in the input order."""
    p = np.asarray(pvals, dtype=np.float64)
    n = p.size
    if n == 0:
        return []
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank in range(n, 0, -1):
        i = order[rank - 1]
        prev = min(prev, p[i] * n / rank)
        q[i] = prev
    return [float(x) for x in q]


def passes(res: dict, null95: float | None, q: float | None, frame_ok: bool) -> dict:
    ci = res.get("ci95")
    checks = {"delta_above_0": res.get("delta") is not None and res["delta"] > 0,
              "ci95_low_above_0": isinstance(ci, list) and ci[0] > 0,
              "bh_q": q is not None and q <= CANDIDATE_Q,
              "above_null95": (null95 is not None and res.get("delta") is not None
                               and res["delta"] > null95),
              "frames_not_negative": bool(frame_ok)}
    return {"checks": checks, "passes": all(checks.values())}


def classify(mean_ok: bool, crps_ok: bool, ll_ok: bool) -> str:
    if mean_ok and (crps_ok or ll_ok):
        return "BOTH"
    if mean_ok:
        return "MEAN"
    if crps_ok or ll_ok:
        return "TAILS ONLY"
    return "NONE"


# ---------------------------------------------------------------------------
# the planted check
# ---------------------------------------------------------------------------

def _normal_scores(rows: list[dict]) -> np.ndarray:
    from scipy.stats import norm, rankdata
    out = np.zeros(len(rows))
    by: dict = {}
    for i, r in enumerate(rows):
        by.setdefault(r["group"], []).append(i)
    for _g, ix in by.items():
        ix = np.asarray(ix)
        rk = rankdata([rows[i]["y"] for i in ix], method="average")
        out[ix] = norm.ppf((rk - 0.5) / len(ix))
    return out


def plant_values(kind: str, rows: list[dict], rng) -> dict:
    eps = rng.standard_normal(len(rows))
    if kind == "P0":
        x = eps
    elif kind == "PM":
        x = RHO_M * _normal_scores(rows) + math.sqrt(1 - RHO_M ** 2) * eps
    elif kind == "PT":
        star = np.array([1.0 if (r["l6"] is not None and r["l6"] > STAR_WAR) else 0.0
                         for r in rows])
        x = DELTA_T * star + eps
    else:
        raise ValueError(kind)
    return {r["rk"]: float(v) for r, v in zip(rows, x)}


def planted(rows: list[dict], *, K: int = K_PLANT, B: int = B_PLANT, log=print) -> dict:
    l6rows = [r for r in rows if r["l6"] is not None]
    base = dist_scores(l6rows, None)
    res: dict = {k: {s: [] for s in SCORES} for k in ("P0", "PM", "PT")}
    for kind in ("P0", "PM", "PT"):
        for k in range(K):
            rng = np.random.default_rng(SEED + 1000 * ("P0", "PM", "PT").index(kind) + k)
            v = plant_values(kind, rows, rng)
            mr = mean_read(rows, v, B=B, seed=SEED + k)
            dr = dist_read(l6rows, v, B=B, seed=SEED + k, base=base)
            res[kind]["mean"].append((mr["delta"], (mr["ci95"] or [None])[0]))
            res[kind]["crps"].append((dr["crps"]["delta"], dr["crps"]["ci95"][0]))
            res[kind]["logloss"].append((dr["logloss"]["delta"], dr["logloss"]["ci95"][0]))
        log(f"    planted {kind}: {K} draws")
    out: dict = {}
    for s in SCORES:
        d0 = np.array([d for d, _lo in res["P0"][s] if d is not None])
        null95 = float(np.quantile(d0, 0.95)) if d0.size else None
        size = float(np.mean([lo is not None and lo > 0 for _d, lo in res["P0"][s]]))
        ent = {"null95": None if null95 is None else round(null95, 6), "size": round(size, 3)}
        for kind in ("PM", "PT"):
            hits = [d is not None and lo is not None and lo > 0 and null95 is not None
                    and d > null95 for d, lo in res[kind][s]]
            ent[f"power_{kind}"] = round(float(np.mean(hits)), 3)
            ent[f"mean_delta_{kind}"] = round(float(np.mean([d for d, _ in res[kind][s]
                                                             if d is not None])), 6)
        out[s] = ent
    return out


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------

def coverage(frames: dict, facts: dict) -> dict:
    out: dict = {}
    for side in SIDES:
        for mid in markers_for(side):
            name = MARKERS[mid][2]
            ent = {}
            for fid in FRAMES:
                rows = frames[fid][side]
                if name == "frame_resid":
                    vals = cell_values(rows, facts, name)
                    n = sum(1 for v in vals.values() if v is not None)
                else:
                    n = sum(1 for r in rows if facts[r["rk"]].get(name) is not None)
                ent[fid] = {"rows": len(rows), "with_value": n}
            out[f"{side}|{mid}"] = ent
    return out


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    except OSError:
        return None


def _git(*args) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _rnd(v, d=6):
    return None if v is None else round(float(v), d)


def collect(log=print) -> tuple[dict, dict]:
    frames = build_rows(log=log)
    facts: dict = {}
    for fid in FRAMES:
        for side in SIDES:
            for r in frames[fid][side]:
                facts[r["rk"]] = row_facts(r)
            if side == "hit":
                group_values(frames[fid][side], facts)
    return frames, facts


def cell_rows(frames: dict, facts: dict, side: str, grp: str) -> list[dict]:
    rows = frames["lv_dev"][side] + frames["vm_dev"][side]
    if grp == "all":
        return rows
    return [r for r in rows if facts[r["rk"]].get("_group") == grp]


def run(*, B: int = B_BOOT, K_null: int = K_NULL, K_plant: int = K_PLANT,
        B_plant: int = B_PLANT, out: Path | None = OUT_PATH, log=print,
        collected: tuple | None = None) -> dict:
    import efv_labels as L
    import efv_vintage_frame as F
    t0 = time.time()
    frames, facts = collected if collected is not None else collect(log=log)
    for fid in FRAMES:
        for side in SIDES:
            for r in frames[fid][side]:
                if fid == "lv_dev" and r["year"] in F.RESERVED_LV:
                    raise F.ReservedFrameError(f"lv_dev {r['year']}")
                if fid == "vm_dev" and r["year"] >= F.R_VM_FIRST_DEBUT_YEAR:
                    raise F.ReservedFrameError(f"vm_dev {r['year']}")
    log(f"rows and markers ready ({round(time.time() - t0, 1)} s)")
    cov = coverage(frames, facts)
    cells: dict = {}
    thin: dict = {}
    for side in SIDES:
        for grp in groups_for(side):
            rows = cell_rows(frames, facts, side, grp)
            l6rows = [r for r in rows if r["l6"] is not None]
            base = dist_scores(l6rows, None) if len(l6rows) >= MIN_ROWS else None
            for mid in markers_for(side):
                fam, _s, name, _l = MARKERS[mid]
                cid = f"{side}|{grp}|{mid}"
                vals = cell_values(rows, facts, name)
                n_mark = sum(1 for v in vals.values() if v is not None)
                n_mark6 = sum(1 for r in l6rows if vals.get(r["rk"]) is not None)
                y6 = np.array([r["l6"] for r in l6rows]) if l6rows else np.array([])
                n_star = int((y6 > STAR_WAR).sum())
                n_bust = int((y6 <= BUST_WAR).sum())
                ent = {"family": fam, "side": side, "group": grp, "marker": mid,
                       "name": name, "rows": len(rows), "rows_with_marker": n_mark,
                       "l6_rows": len(l6rows), "l6_rows_with_marker": n_mark6,
                       "l6_star": n_star, "l6_bust": n_bust,
                       "marker_rows_by_frame": {fid: sum(1 for r in rows if r["frame"] == fid
                                                         and vals.get(r["rk"]) is not None)
                                                for fid in FRAMES},
                       "marker_l6_rows_by_frame": {fid: sum(1 for r in l6rows
                                                            if r["frame"] == fid and
                                                            vals.get(r["rk"]) is not None)
                                                   for fid in FRAMES},
                       "reads": {}}
                if len(rows) >= MIN_ROWS and n_mark >= MIN_MARKER:
                    t1 = time.time()
                    mr = mean_read(rows, vals, B=B)
                    rng = np.random.default_rng(NULL_SEED + int(hashlib.sha256(
                        cid.encode()).hexdigest()[:6], 16))
                    tw = [mean_delta_point(rows, permute_within(rows, vals, rng))
                          for _ in range(K_null)]
                    tw = [t for t in tw if t is not None]
                    mr["null95"] = _rnd(np.quantile(tw, 0.95)) if tw else None
                    mr["null_mean"] = _rnd(np.mean(tw)) if tw else None
                    ent["reads"]["mean"] = mr
                    log(f"  {cid} mean {mr['delta']} {mr['ci95']} null95 {mr['null95']} "
                        f"({round(time.time() - t1, 1)} s)")
                else:
                    thin.setdefault("mean", []).append(cid)
                if (base is not None and n_mark6 >= MIN_MARKER and n_star >= MIN_CLASS
                        and n_bust >= MIN_CLASS):
                    dr = dist_read(l6rows, vals, B=B, base=base)
                    rng = np.random.default_rng(NULL_SEED + 7 + int(hashlib.sha256(
                        cid.encode()).hexdigest()[:6], 16))
                    tws = [dist_delta_point(l6rows, permute_within(l6rows, vals, rng), base)
                           for _ in range(K_null)]
                    for s in ("crps", "logloss"):
                        tv = [t[s] for t in tws]
                        dr[s]["null95"] = _rnd(np.quantile(tv, 0.95))
                        dr[s]["null_mean"] = _rnd(np.mean(tv))
                        ent["reads"][s] = dr[s]
                    log(f"  {cid} crps {dr['crps']['delta']} {dr['crps']['ci95']} logloss "
                        f"{dr['logloss']['delta']} {dr['logloss']['ci95']}")
                else:
                    thin.setdefault("distribution", []).append(cid)
                cells[cid] = ent
    # BH within (family, score) over every scored cell
    for fam in FAMILIES:
        for s in SCORES:
            ids = [c for c, e in cells.items() if e["family"] == fam and s in e["reads"]
                   and e["reads"][s].get("p") is not None]
            qs = bh([cells[c]["reads"][s]["p"] for c in ids])
            for c, q in zip(ids, qs):
                cells[c]["reads"][s]["q"] = round(q, 6)
    # the rule and the classification
    for cid, e in cells.items():
        ok = {}
        for s in SCORES:
            r = e["reads"].get(s)
            if r is None:
                ok[s] = False
                continue
            nby = e["marker_rows_by_frame"] if s == "mean" else e["marker_l6_rows_by_frame"]
            frame_ok = all((r["per_frame"].get(fid) is None or r["per_frame"][fid] >= 0)
                           for fid in FRAMES if nby.get(fid, 0) >= MIN_MARKER)
            rule = passes(r, r.get("null95"), r.get("q"), frame_ok)
            r["rule"] = rule
            ok[s] = rule["passes"]
        e["scored"] = sorted(e["reads"])
        # section 8 classifies scored cells only; a cell below the minimum on every read is
        # listed as thin (section 6)
        e["class"] = (classify(ok["mean"], ok["crps"], ok["logloss"]) if e["scored"]
                      else "THIN")
    log(f"cells done ({round(time.time() - t0, 1)} s); planted check ...")
    plant = {}
    for side in SIDES:
        rows = cell_rows(frames, facts, side, "all")
        plant[side] = planted(rows, K=K_plant, B=B_plant, log=log)
        log(f"  planted {side}: {plant[side]}")
    for cid, e in cells.items():
        if e["class"] == "NONE":
            # Registered (section 8): a NONE on a side whose planted power for each scored
            # score (the better of the mean and tail plants) is at or above POWER_MIN is a
            # NULL, else UNRESOLVED. The plants have full coverage on the side's "all" rows,
            # so power_caveat marks a NULL read on a subgroup or on a marker covering under
            # half its rows, where the cell holds fewer informative rows than the plant did.
            pw = plant[e["side"]]
            res = [max(pw[s]["power_PM"], pw[s]["power_PT"]) >= POWER_MIN for s in e["scored"]]
            e["none_reading"] = "NULL" if (res and all(res)) else "UNRESOLVED"
            e["power_caveat"] = not (e["group"] == "all"
                                     and e["rows_with_marker"] >= 0.5 * e["rows"])
    handoff = sorted(f"{cid}|{s}" for cid, e in cells.items() for s in e["scored"]
                     if e["reads"][s]["rule"]["passes"])
    rows_rec = {f"{fid}|{side}": {"rows": len(frames[fid][side]),
                                  "l6_rows": sum(1 for r in frames[fid][side]
                                                 if r["l6"] is not None),
                                  "years": sorted({r["year"] for r in frames[fid][side]})}
                for fid in FRAMES for side in SIDES}
    doc = {"schema": 1, "item": ITEM, "produced_by": TOOL,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "role": "development", "descriptive": True, "adjudicates": False,
           "selects": False, "served": False,
           "owner_decision": "EW3-35 (2026-10-16)",
           "registration": {"doc": DOC, "commit": _git("log", "-1", "--format=%h", "--", DOC)},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"),
                    "module_sha256": _sha(Path(__file__))},
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "mean_read": "frame label: lv_dev W3, vm_dev career WAR to date",
                     "distribution_read": "L6 six-season fWAR, fully observed rows only"},
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "anchor_gate_grouping": False},
           "constants": {"lookback_days": LOOKBACK_DAYS, "prior_gap_days": PRIOR_GAP_DAYS,
                         "spike_ip": SPIKE_IP, "star_war": STAR_WAR, "bust_war": BUST_WAR,
                         "grid": list(GRID), "lambda_logit": LAMBDA_LOGIT,
                         "ridge_alpha": RIDGE_ALPHA, "min_group_rows": MIN_GROUP_ROWS,
                         "min_rows": MIN_ROWS, "min_marker": MIN_MARKER,
                         "min_class": MIN_CLASS, "k_null": K_null, "k_plant": K_plant,
                         "B": B, "B_plant": B_plant, "rho_m": RHO_M, "delta_t": DELTA_T,
                         "candidate_q": CANDIDATE_Q, "power_min": POWER_MIN, "seed": SEED,
                         "null_seed": NULL_SEED},
           "markers": {m: {"family": f, "sides": list(s), "name": n, "label": lab}
                       for m, (f, s, n, lab) in MARKERS.items()},
           "rows": rows_rec, "coverage": cov, "thin": thin, "cells": cells,
           "planted": plant, "handoff_x3": handoff,
           "classes": {c: e["class"] for c, e in cells.items()},
           "elapsed_s": round(time.time() - t0, 1)}
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
        log(f"wrote {out} ({doc['elapsed_s']} s)")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--coverage", action="store_true", help="marker coverage only")
    ap.add_argument("--run", action="store_true", help="the registered read")
    a = ap.parse_args()

    def _log(msg):
        print(msg, flush=True)
    if a.coverage:
        fr, fa = collect(log=lambda m: None)
        _log(json.dumps(coverage(fr, fa), indent=1))
    if a.run:
        d = run(log=_log)
        _log(json.dumps(d["handoff_x3"]))
