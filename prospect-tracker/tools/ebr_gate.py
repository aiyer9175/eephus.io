#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""ebr_gate - the eBR outcome look, ONCE (docs/ebr-2026-09-30/EBR_GATE.md part 5).

This is the ONLY code path that computes a year-to-year, split-half or forward
statistic of eBR or of any of its parts (part 5, part 7.6). It runs once, on the
day part 7.2 allows, by

    python -u tools/ebr_gate.py --out-dir <writer output directory>

and before that day only as a dry run on synthetic fixtures with nulls:

    python -u tools/ebr_gate.py --dry-run [--out-dir <dir>]

WHAT IT COMPUTES (part 5, as amended in part 11): Leg E (the per-pair Spearman
self-persistence of (eSB + ePK + eXB) per PA against FanGraphs' BsR per PA, the
player-clustered bootstrap, B 2,000, seed 20260807, d +/- 1.645 sd, the part 8
dispositions at Delta 0.02), its guards (Leg T on club runs, the permuted twin,
frame U, the club changers), the DP leg (E-DP against Baseball-Reference's
runs_dp with its twin, DP-1 as a plumbing floor with its permuted control,
DP-2), split-half reliability with the NOISE flag, the reported-beside items of
5.6, and BEM+ (part 5.8; part 1 records EBR-Q3 (a)): its constants fit first,
gate X-B1, its twin and the 2025 to 2026 holdout. Floors (bootstrap sd,
half-width, the reachable dispositions) print BEFORE each estimate.

WHAT IT REFUSES (and then computes nothing): a non-empty part 12.1 or any eval
carrying a look block; a date before 2026-11-17 or an excluded day; no step Z
entry in FWAR_LABEL_EPOCH_GATE.md part 9 (or step A started without one); a
frozen fWAR vintage that is absent or lacks, for a frame season, any of
baseRunning, wSb, ubr, wGdp, batting, plateAppearances or numTeams on a hitting
row ('BLOCKER: other fwar vintage lacks <fields>'); a frame season failing I1 to
I9, or 2026 built before 2026-11-01; a pipeline, suite, test session or other
lab running. --owner-waived-early-read lifts ONLY the date clauses (the owner's
EW3-5 of 2026-10-14) and stamps the read as an OWNER-WAIVED EARLY READ.

WHAT IT READS: the runner record and the preview substrate (.cache/pbp_runners,
.cache/ebr), the frozen fWAR vintage (data/fwar_vintage.json), the cached
Baseball-Reference frame (.cache/war_daily/bat.parquet, never fetched), the
cached StatsAPI season lines and club season lines, the Savant caches and the
sprint file. It fetches NOTHING.

WHAT IT WRITES: the part 12.1 text of the gate document and the look block of
.cache/ebr/preview/ebr_eval.json. Nothing under data/. Leg T's and DP-2's r
values live only there (part 5.3). A look block is written as soon as scoring
begins, so a crash leaves one and any second run refuses (part 5.9).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import traceback
from collections import defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for _p in (str(ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

GATE_DOC = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"
EPOCH_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
VINTAGE = ROOT / "data" / "fwar_vintage.json"
PREVIEW_DIR = ROOT / ".cache" / "ebr" / "preview"
FROZEN_POOL = ROOT / ".cache" / "ebr" / "frozen" / "ebr_v1_pool.json"
SERVED_EVAL = ROOT / "data" / "ebr_eval.json"
SPRINT = ROOT / "data" / "savant_sprint.json"
ARM = ROOT / "data" / "savant_arm.json"
PRE_EPOCH_DIRS = (ROOT.parent.parent / "_pre_epoch_fwar_2026-10",)

# ---------------------------------------------------------------------------
# registered constants (EBR_GATE.md parts 5 and 7.2; never tuned)
# ---------------------------------------------------------------------------
PAIRS: tuple[tuple[int, int], ...] = ((2018, 2019), (2021, 2022), (2022, 2023), (2023, 2024),
                                      (2024, 2025), (2025, 2026))
FRAME_U = PAIRS[:4]
FRAME_X = PAIRS[4:]
FRAME_SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
MIN_PA = 300
PA_502 = 502
BOOT = 2000
SEED = 20260807
DELTA = 0.02
Z90 = 1.645
LEG_T_FLOOR = 0.005
NOISE_REL = 0.10
NOISE_SEASONS = 5
MIN_PAIR_ROWS = 30          # a frame pair below this is a broken frame
MIN_SUBSET_PAIR_ROWS = 10   # a subset pair below this sits out of the subset mean
LOOK_NOT_BEFORE = _dt.date(2026, 11, 17)
FREEZE_2026 = _dt.date(2026, 11, 1)
EXCLUDED_DAYS = frozenset(_dt.date.fromisoformat(d) for d in (
    "2026-10-23", "2026-11-06", "2026-11-13", "2026-11-16", "2026-11-20", "2026-12-01",
    # Part 9's look days (the plan's preamble), never shared with another look
    "2026-10-21", "2026-10-28", "2026-11-24", "2026-11-25", "2026-12-03", "2026-12-08",
    "2026-12-10", "2027-01-12", "2027-10-20", "2027-11-09", "2027-11-16"))
VINTAGE_FIELDS = ("baseRunning", "wSb", "ubr", "wGdp", "batting", "plateAppearances", "numTeams")
BUSY_TOKENS = ("run_monthly", "nightly", "pytest", "run_suite", "_lab.py", "_gate.py",
               "build_ebr", "build_runner_moves", "build_swar", "efv_export", "proj_export")
PARTS = ("sb", "pk", "xb_adv", "xb_oob", "dp")
DISPLAY = {"SB runs": ("sb", "pk"), "XB runs": ("xb_adv", "xb_oob"), "DP runs": ("dp",),
           "eBR": PARTS}
# BEM+ (part 5.8)
BEM_FIT_PAIRS = ((2018, 2019), (2021, 2022))
BEM_PRED = (2022, 2023, 2024)
BEM_HOLDOUT = (2025,)
BEM_FLOOR_Y = 100
BEM_FLOOR_NEXT = 150
BEM_POOL_FLOOR = 100
WAIVER_NOTE = "OWNER-WAIVED EARLY READ (owner EW3-5, 2026-10-14)"


class Refused(RuntimeError):
    """A precondition failed: the look computes nothing."""


# ---------------------------------------------------------------------------
# output: every line goes through say(), teed by main()
# ---------------------------------------------------------------------------
class _Tee:
    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, s):
        self.stream.write(s)
        self.fh.write(s)
        self.fh.flush()
        return len(s)

    def flush(self):
        self.stream.flush()
        self.fh.flush()


class Report:
    def __init__(self, echo=True):
        self.lines: list[str] = []
        self.echo = echo

    def say(self, s: str = "") -> None:
        self.lines.append(s)
        if self.echo:
            print(s, flush=True)

    def text(self) -> str:
        return "\n".join(self.lines)


def _f(v, nd=4) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    return f"{v:+.{nd}f}" if nd else str(v)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def _ranks(v):
    from scipy.stats import rankdata
    return rankdata(v)


def spearman(x, y):
    import numpy as np
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 4:
        return None
    rx, ry = _ranks(x), _ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def pearson(x, y):
    import numpy as np
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def disposition(d: float, sd: float, delta: float = DELTA) -> str:
    """EFV_GATE_STANDARD.md part 8 on the interval d +/- 1.645 sd."""
    lo, hi = d - Z90 * sd, d + Z90 * sd
    if lo > delta:
        return "SHIP"
    if hi < -delta:
        return "RESOLVED_LOSS"
    if lo > -delta and hi < delta:
        return "RULED OUT"
    return "UNDECIDED"


def floors(sd: float, delta: float = DELTA) -> dict:
    """What the interval's width allows, printed before the estimate."""
    h = Z90 * sd
    return {"bootstrap_sd": round(sd, 4), "half_width": round(h, 4),
            "ruled_out_reachable": bool(h < delta),
            "ship_needs_d_above": round(delta + h, 4),
            "resolved_loss_needs_d_below": round(-(delta + h), 4)}


def _say_floors(rep: Report, name: str, fl: dict) -> None:
    rep.say(f"  floors {name}: bootstrap sd {fl['bootstrap_sd']:.4f}, half-width "
            f"{fl['half_width']:.4f}; reachable: SHIP if d > {fl['ship_needs_d_above']:+.4f}, "
            f"RESOLVED_LOSS if d < {fl['resolved_loss_needs_d_below']:+.4f}, RULED OUT "
            f"{'reachable' if fl['ruled_out_reachable'] else 'NOT reachable (half-width >= 0.02)'}, "
            f"UNDECIDED always")


# ---------------------------------------------------------------------------
# the frame: one row per (pair, player), each series' value in Y and Y+1
# ---------------------------------------------------------------------------
class Frame:
    """Rows of (pair, pid) with per-series values in Y (key 0) and Y+1 (key 1)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.players = sorted({r["pid"] for r in rows})
        self._pix = {p: i for i, p in enumerate(self.players)}
        self.by_pair = {pr: [i for i, r in enumerate(rows) if r["pair"] == pr] for pr in PAIRS}

    def subset(self, keep) -> "Frame":
        return Frame([r for r in self.rows if keep(r)])

    def sizes(self) -> dict:
        return {f"{a}-{b}": len(self.by_pair[(a, b)]) for a, b in PAIRS}


def _pair_stat(fr: Frame, idx_by_pair: dict, fn, pairs, min_rows) -> dict:
    out = {}
    for pr in pairs:
        ix = idx_by_pair.get(pr) or []
        if len(ix) < min_rows:
            continue
        v = fn([fr.rows[i] for i in ix])
        if v is not None:
            out[pr] = v
    return out


def persistence_d(fr: Frame, a: str, b: str, *, pairs=PAIRS, corr=spearman,
                  min_rows=MIN_PAIR_ROWS, idx_by_pair=None) -> dict:
    """mean over pairs of corr(a_Y, a_Y+1) minus the same for b, with the per-pair
    values (a pair below min_rows sits out of both means)."""
    idx_by_pair = idx_by_pair if idx_by_pair is not None else fr.by_pair

    def one(rs):
        ra = corr([r[a][0] for r in rs], [r[a][1] for r in rs])
        rb = corr([r[b][0] for r in rs], [r[b][1] for r in rs])
        return None if ra is None or rb is None else (ra, rb)
    per = _pair_stat(fr, idx_by_pair, one, pairs, min_rows)
    if not per:
        return {"d": None, "per_pair": {}, "mean_a": None, "mean_b": None}
    ma = sum(v[0] for v in per.values()) / len(per)
    mb = sum(v[1] for v in per.values()) / len(per)
    return {"d": ma - mb, "mean_a": ma, "mean_b": mb,
            "per_pair": {f"{p[0]}-{p[1]}": [round(v[0], 4), round(v[1], 4), round(v[0] - v[1], 4)]
                         for p, v in per.items()}}


def self_persistence(fr: Frame, a: str, *, pairs=PAIRS, min_rows=MIN_PAIR_ROWS, idx_by_pair=None):
    idx_by_pair = idx_by_pair if idx_by_pair is not None else fr.by_pair
    per = _pair_stat(fr, idx_by_pair,
                     lambda rs: spearman([r[a][0] for r in rs], [r[a][1] for r in rs]),
                     pairs, min_rows)
    return (sum(per.values()) / len(per)) if per else None


def bootstrap(fr: Frame, stat, *, boot: int = BOOT, seed: int = SEED) -> list[float]:
    """Player-clustered bootstrap (players drawn with replacement, each carrying all
    his pairs; the draw of the eBR bundle's _ewar_leg_power.py): stat(idx_by_pair)
    on every replicate, None replicates dropped."""
    import numpy as np
    rng = np.random.default_rng(seed)
    players = np.array(fr.players)
    pix = np.array([fr._pix[r["pid"]] for r in fr.rows])
    out = []
    for _ in range(boot):
        draw = rng.choice(len(players), size=len(players), replace=True)
        cnt = np.bincount(draw, minlength=len(players))
        w = cnt[pix]
        idx_by_pair = {}
        for pr, ix in fr.by_pair.items():
            ix = np.asarray(ix, dtype=int)
            idx_by_pair[pr] = np.repeat(ix, w[ix]).tolist() if len(ix) else []
        v = stat(idx_by_pair)
        if v is not None:
            out.append(v)
    return out


def _sd(vals) -> float:
    import numpy as np
    return float(np.std(np.asarray(vals, dtype=float), ddof=1)) if len(vals) > 1 else float("nan")


def leg(rep: Report, fr: Frame, name: str, a: str, b: str, *, boot: int) -> dict:
    """A persistence contrast with its floors printed first, then d and the
    disposition."""
    reps = bootstrap(fr, lambda ib: persistence_d(fr, a, b, idx_by_pair=ib)["d"], boot=boot)
    sd = _sd(reps)
    fl = floors(sd)
    _say_floors(rep, name, fl)
    est = persistence_d(fr, a, b)
    d = est["d"]
    disp = disposition(d, sd) if d is not None and not math.isnan(sd) else "UNDECIDED"
    rep.say(f"  {name}: mean rho {a} {_f(est['mean_a'])}, mean rho {b} {_f(est['mean_b'])}, "
            f"d {_f(d)}, interval [{_f(d - Z90 * sd if d is not None else None)}, "
            f"{_f(d + Z90 * sd if d is not None else None)}], disposition {disp}")
    return {"d": None if d is None else round(d, 4), "mean_rho_candidate": _r(est["mean_a"]),
            "mean_rho_incumbent": _r(est["mean_b"]), "per_pair": est["per_pair"],
            "floors": fl, "replicates": len(reps), "disposition": disp}


def _r(v, nd=4):
    return None if v is None else round(float(v), nd)


def permuted(fr: Frame, key: str, *, seed: int = SEED) -> Frame:
    """`key` permuted across the frame's player-seasons within each season, each
    season independently, rows unchanged (the zero-information twin)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    vals: dict = {}
    for r in fr.rows:
        y0, y1 = r["pair"]
        vals[(r["pid"], y0)] = r[key][0]
        vals[(r["pid"], y1)] = r[key][1]
    by_season = defaultdict(list)
    for (pid, s) in sorted(vals):
        by_season[s].append(pid)
    new = {}
    for s in sorted(by_season):
        pids = by_season[s]
        perm = rng.permutation(len(pids))
        for i, j in enumerate(perm):
            new[(pids[i], s)] = vals[(pids[j], s)]
    rows = []
    for r in fr.rows:
        y0, y1 = r["pair"]
        rr = dict(r)
        rr[key] = (new[(r["pid"], y0)], new[(r["pid"], y1)])
        rows.append(rr)
    return Frame(rows)


# ---------------------------------------------------------------------------
# building the frame from the inputs
# ---------------------------------------------------------------------------
def _sub(inp, pid, s):
    return (inp["sub"].get(s) or {}).get(pid)


def build_frame(inp: dict, rep: Report) -> tuple[Frame, dict]:
    """Players with 300+ PA (official lines) in both seasons of a pair and a value in
    every series compared; one row per (pair, player)."""
    rows, dropped = [], defaultdict(int)
    for (y0, y1) in PAIRS:
        l0, l1 = inp["lines"].get(y0) or {}, inp["lines"].get(y1) or {}
        for pid in sorted(set(l0) & set(l1)):
            p0, p1 = l0[pid].get("pa") or 0, l1[pid].get("pa") or 0
            if p0 < MIN_PA or p1 < MIN_PA:
                continue
            s0, s1 = _sub(inp, pid, y0), _sub(inp, pid, y1)
            f0, f1 = (inp["fg"].get(y0) or {}).get(pid), (inp["fg"].get(y1) or {}).get(pid)
            b0, b1 = (inp["bref"].get(y0) or {}).get(pid), (inp["bref"].get(y1) or {}).get(pid)
            if s0 is None or s1 is None:
                dropped["no eBR row"] += 1
                continue
            if f0 is None or f1 is None or any(f.get(k) is None for f in (f0, f1)
                                               for k in ("baseRunning", "wSb", "plateAppearances")):
                dropped["no vintage value"] += 1
                continue
            if b0 is None or b1 is None or any(b.get("runs_dp") is None or b.get("runs_br") is None
                                               for b in (b0, b1)):
                dropped["no Baseball-Reference value"] += 1
                continue
            if not f0["plateAppearances"] or not f1["plateAppearances"]:
                dropped["vintage PA zero"] += 1
                continue

            def e(s, pa):
                return (s["sb"] + s["pk"] + s["xb_adv"] + s["xb_oob"]) / pa
            row = {"pair": (y0, y1), "pid": pid, "pa": (p0, p1),
                   "E": (e(s0, p0), e(s1, p1)),
                   "B": (f0["baseRunning"] / f0["plateAppearances"],
                         f1["baseRunning"] / f1["plateAppearances"]),
                   "G": (s0["dp"] / p0, s1["dp"] / p1),
                   "R": (b0["runs_dp"] / p0, b1["runs_dp"] / p1),
                   "SBr": ((s0["sb"] + s0["pk"]) / p0, (s1["sb"] + s1["pk"]) / p1),
                   "XBr": ((s0["xb_adv"] + s0["xb_oob"]) / p0, (s1["xb_adv"] + s1["xb_oob"]) / p1),
                   "W": (f0["wSb"] / f0["plateAppearances"], f1["wSb"] / f1["plateAppearances"]),
                   "BX": ((f0["baseRunning"] - f0["wSb"]) / f0["plateAppearances"],
                          (f1["baseRunning"] - f1["wSb"]) / f1["plateAppearances"]),
                   "WG": ((f0.get("wGdp") / p0) if f0.get("wGdp") is not None else None,
                          (f1.get("wGdp") / p1) if f1.get("wGdp") is not None else None),
                   "GO": ((s0["dp"] / s0["opp_dp"]) if s0.get("opp_dp") else None,
                          (s1["dp"] / s1["opp_dp"]) if s1.get("opp_dp") else None),
                   "BR": (b0["runs_br"] / p0, b1["runs_br"] / p1),
                   "club": (_primary_club(inp, pid, y0), _primary_club(inp, pid, y1)),
                   "vintage_pa_differs": int(f0["plateAppearances"] != p0) + int(f1["plateAppearances"] != p1)}
            rows.append(row)
    fr = Frame(rows)
    return fr, dict(dropped)


def _primary_club(inp, pid, s):
    st = (inp["stints"].get(s) or {}).get(pid) or []
    if not st:
        return None
    return sorted(st, key=lambda x: (-x[1], str(x[0])))[0][0]


# ---------------------------------------------------------------------------
# Leg T and DP-2: club runs
# ---------------------------------------------------------------------------
def club_offense(inp: dict) -> list[dict]:
    """Per club-season: off_B (FanGraphs batting + BsR), off_E (FanGraphs batting +
    eSB + ePK + eXB) and eGDP, each allocated to clubs by the Baseball-Reference stint
    plate-appearance share, beside the club's runs scored."""
    pts = []
    for s in FRAME_SEASONS:
        runs = inp["team_runs"].get(s) or {}
        acc = defaultdict(lambda: {"off_b": 0.0, "off_e": 0.0, "dp": 0.0})
        for pid, f in (inp["fg"].get(s) or {}).items():
            st = (inp["stints"].get(s) or {}).get(pid) or []
            tot = sum(pa for _, pa in st)
            if not tot or f.get("batting") is None or f.get("baseRunning") is None:
                continue
            sub = _sub(inp, pid, s) or {}
            e = sum(sub.get(p, 0.0) for p in ("sb", "pk", "xb_adv", "xb_oob"))
            for club, pa in st:
                w = pa / tot
                a = acc[club]
                a["off_b"] += w * (f["batting"] + f["baseRunning"])
                a["off_e"] += w * (f["batting"] + e)
                a["dp"] += w * sub.get("dp", 0.0)
        for club, v in sorted(acc.items()):
            if club in runs:
                pts.append({"season": s, "club": club, "runs": float(runs[club]), **v})
    return pts


def leg_t(pts: list[dict]) -> dict:
    rs = [p["runs"] for p in pts]
    r_b = pearson([p["off_b"] for p in pts], rs)
    r_e = pearson([p["off_e"] for p in pts], rs)
    r_bg = pearson([p["off_b"] + p["dp"] for p in pts], rs)
    leg_t_pass = None if r_b is None or r_e is None else bool(r_e >= r_b - LEG_T_FLOOR)
    dp2_pass = None if r_b is None or r_bg is None else bool(r_bg >= r_b - LEG_T_FLOOR)
    return {"n_club_seasons": len(pts), "r_off_B": _r(r_b), "r_off_E": _r(r_e),
            "r_off_B_plus_eGDP": _r(r_bg), "leg_t_pass": leg_t_pass, "dp2_pass": dp2_pass}


# ---------------------------------------------------------------------------
# 5.5 reliability
# ---------------------------------------------------------------------------
def reliability(inp: dict) -> dict:
    out = {}
    for s in FRAME_SEASONS:
        pg = inp["per_game"].get(s) or {}
        lines = inp["lines"].get(s) or {}
        pids = [p for p in pg if (lines.get(p) or {}).get("pa", 0) >= MIN_PA]
        blk = {}
        for name, parts in list(DISPLAY.items()) + [(p, (p,)) for p in PARTS]:
            odd = [sum(pg[p]["odd"].get(q, 0.0) for q in parts) for p in pids]
            even = [sum(pg[p]["even"].get(q, 0.0) for q in parts) for p in pids]
            r = pearson(odd, even)
            blk[name] = {"n": len(pids), "r_half": _r(r),
                         "reliability": (None if r is None else _r(2 * r / (1 + r)) if r > -1 else None)}
        out[str(s)] = blk
    names = list(DISPLAY) + list(PARTS)
    noise = {}
    for name in names:
        low = sum(1 for s in out if (out[s][name]["reliability"] is None
                                     or out[s][name]["reliability"] <= NOISE_REL))
        noise[name] = low >= NOISE_SEASONS
    return {"by_season": out, "noise": noise}


# ---------------------------------------------------------------------------
# 5.8 BEM+
# ---------------------------------------------------------------------------
BEM_PARTS = {"SB": (("sb", "pk"), ("opp_sb", "starts_on_base")),
             "XB": (("xb_adv", "xb_oob"), ("opp_xb",)),
             "DP": (("dp",), ("opp_dp",))}


def _bem_runs_chances(row):
    out = {}
    for p, (rk, ck) in BEM_PARTS.items():
        out[p] = (sum(row.get(k, 0.0) for k in rk), sum(row.get(k, 0) for k in ck))
    return out


def bem_mix(inp: dict, s: int) -> dict:
    rows = list((inp["sub"].get(s) or {}).values())
    starts = sum(r.get("starts_on_base", 0) for r in rows)
    out = {}
    for p in BEM_PARTS:
        ch = sum(_bem_runs_chances(r)[p][1] for r in rows)
        out[p] = 100.0 * ch / starts if starts else 0.0
    return out


def bem_fit(inp: dict) -> dict:
    """k_p = hm (1 - r) / r (positional_fit.fit_signal's rule), r the year-over-year
    Pearson of the part's rate at matched exposure (runners with 100+ starts on base
    in both seasons of 2018-2019 and 2021-2022), clipped to [0.05, 0.95]."""
    import statistics
    out = {}
    for p in BEM_PARTS:
        xs, ys, hm = [], [], []
        for y0, y1 in BEM_FIT_PAIRS:
            for pid, r0 in (inp["sub"].get(y0) or {}).items():
                r1 = _sub(inp, pid, y1)
                if r1 is None or r0.get("starts_on_base", 0) < BEM_POOL_FLOOR \
                        or r1.get("starts_on_base", 0) < BEM_POOL_FLOOR:
                    continue
                (u0, c0), (u1, c1) = _bem_runs_chances(r0)[p], _bem_runs_chances(r1)[p]
                if c0 <= 0 or c1 <= 0:
                    continue
                xs.append(u0 / c0)
                ys.append(u1 / c1)
                hm.append(2.0 / (1.0 / c0 + 1.0 / c1))
        r = pearson(xs, ys)
        if r is None or len(xs) < 30:
            out[p] = {"n_pairs": len(xs), "yoy_r": _r(r), "k": None}
            continue
        rc = min(max(r, 0.05), 0.95)
        hmm = statistics.mean(hm)
        out[p] = {"n_pairs": len(xs), "yoy_r": _r(rc), "hm": round(hmm, 1),
                  "k": round(hmm * (1 - rc) / rc, 1)}
    return out


def bem_values(inp: dict, s: int, ks: dict) -> dict:
    """{pid: (bem_plus unrounded, raw parent rate)} over runners with any start on base."""
    import numpy as np
    mix = bem_mix(inp, s)
    rows = inp["sub"].get(s) or {}
    rate, raw = {}, {}
    for pid, r in rows.items():
        rc = _bem_runs_chances(r)
        rate[pid] = sum((u / (c + (ks[p]["k"] or 0.0)) if (c + (ks[p]["k"] or 0.0)) > 0 else 0.0)
                        * mix[p] for p, (u, c) in rc.items())
        raw[pid] = sum(((u / c) if c > 0 else 0.0) * mix[p] for p, (u, c) in rc.items())
    pool = [rate[p] for p, r in rows.items() if r.get("starts_on_base", 0) >= BEM_POOL_FLOOR]
    if len(pool) < 2:
        return {}
    mu, sd = float(np.mean(pool)), float(np.std(pool))
    return {pid: (100.0 + 10.0 * (rate[pid] - mu) / sd if sd else 100.0, raw[pid]) for pid in rows}


def bem_rows(inp: dict, ks: dict, pred_seasons) -> tuple[list[dict], dict]:
    rows, dropped = [], defaultdict(int)
    for y in pred_seasons:
        vals = bem_values(inp, y, ks)
        for pid, r0 in (inp["sub"].get(y) or {}).items():
            r1 = _sub(inp, pid, y + 1)
            if r1 is None or r0.get("starts_on_base", 0) < BEM_FLOOR_Y \
                    or r1.get("starts_on_base", 0) < BEM_FLOOR_NEXT:
                continue
            sp = (inp["sprint"].get(y) or {}).get(pid)
            sb = ((inp["lines"].get(y) or {}).get(pid) or {}).get("sb")
            if sp is None:
                dropped["no sprint speed"] += 1
                continue
            if sb is None or pid not in vals:
                dropped["no stolen-base line"] += 1
                continue
            rows.append({"pid": pid, "y": y, "bem": vals[pid][0], "raw": vals[pid][1],
                         "sprint": sp, "sb": sb, "starts": r0["starts_on_base"],
                         "tgt": 100.0 * r1["ebr"] / r1["starts_on_base"]})
    return rows, dict(dropped)


def bem_gate(rows: list[dict], *, boot: int, seed: int = SEED) -> dict:
    import plus_lab_harness as plh
    if len(rows) < 30:
        return {"n": len(rows), "note": "too few rows", "pass": None}
    tgt = plh.zscore_within([r["y"] + 1 for r in rows], [r["tgt"] for r in rows])
    prim = [r["bem"] for r in rows]
    base = {"vs_sprint": [r["sprint"] for r in rows], "vs_sb": [float(r["sb"]) for r in rows],
            "vs_starts": [float(r["starts"]) for r in rows], "vs_raw": [r["raw"] for r in rows]}
    players = [r["pid"] for r in rows]
    pys = [r["y"] for r in rows]
    gaps = plh.cluster_boot_gaps(prim, base, tgt, players, pys, boot, seed)
    rho = {"bem_plus": _r(plh.spearman(prim, tgt))}
    rho.update({k: _r(plh.spearman(v, tgt)) for k, v in base.items()})
    twin_vals = list(prim)
    rng = random.Random(seed)
    by = defaultdict(list)
    for i, y in enumerate(pys):
        by[y].append(i)
    for y in sorted(by):
        idx = by[y]
        vs = [prim[i] for i in idx]
        rng.shuffle(vs)
        for i, v in zip(idx, vs):
            twin_vals[i] = v
    twin = plh.cluster_boot_gaps(twin_vals, {"vs_sb": base["vs_sb"]}, tgt, players, pys, boot, seed)
    clauses = {"beats_sprint": bool(gaps.get("vs_sprint") and gaps["vs_sprint"]["lo95"] > 0),
               "beats_sb": bool(gaps.get("vs_sb") and gaps["vs_sb"]["lo95"] > 0),
               "beats_starts": bool(gaps.get("vs_starts") and gaps["vs_starts"]["lo95"] > 0),
               "not_worse_than_raw": bool(gaps.get("vs_raw") and gaps["vs_raw"]["lo95"] >= -0.01)}
    twin_fails = not bool(twin.get("vs_sb") and twin["vs_sb"]["lo95"] > 0)
    return {"n": len(rows), "players": len(set(players)), "rho": rho, "gaps": gaps,
            "twin_gap_vs_sb": twin.get("vs_sb"), "twin_fails": twin_fails, "clauses": clauses,
            "pass": bool(all(clauses.values()) and twin_fails)}


# ---------------------------------------------------------------------------
# the look
# ---------------------------------------------------------------------------
def run_look(inp: dict, rep: Report, *, boot: int = BOOT) -> dict:
    """Every statistic of part 5, in the registered order. Pure over `inp`."""
    out: dict = {"constants": {"pairs": [f"{a}-{b}" for a, b in PAIRS], "boot": boot, "seed": SEED,
                               "delta": DELTA, "z": Z90, "min_pa": MIN_PA}}
    fr, dropped = build_frame(inp, rep)
    sizes = fr.sizes()
    rep.say(f"FRAME (5.1): {len(fr.rows)} runner-pairs, {len(fr.players)} players; per pair {sizes}")
    rep.say(f"  rows dropped for a missing series: {dropped or 'none'}; vintage PA differing from the "
            f"official line on {sum(r['vintage_pa_differs'] for r in fr.rows)} player-seasons")
    short = [k for k, v in sizes.items() if v < MIN_PAIR_ROWS]
    if short:
        raise RuntimeError(f"frame pairs below {MIN_PAIR_ROWS} rows: {short}")
    cc = fr.subset(lambda r: r["club"][0] is not None and r["club"][1] is not None
                   and r["club"][0] != r["club"][1])
    rep.say(f"  club changers (primary club by Baseball-Reference stint PA differs): per pair "
            f"{cc.sizes()}, {len(cc.rows)} in all")
    out["frame"] = {"rows": len(fr.rows), "players": len(fr.players), "per_pair": sizes,
                    "dropped": dropped, "club_changers_per_pair": cc.sizes()}

    # BEM+ constants first: fit before any gate statistic, then frozen
    ks = bem_fit(inp)
    rep.say("BEM+ CONSTANTS (5.8, fit before any gate statistic, frozen here): "
            + "; ".join(f"{p} k {v['k']} (r {v['yoy_r']}, n {v['n_pairs']})" for p, v in ks.items()))
    out["bem_constants"] = ks

    rep.say("LEG E (5.2): E = (eSB + ePK + eXB) / PA against B = BsR / PA")
    out["leg_e"] = leg(rep, fr, "Leg E", "E", "B", boot=boot)
    rep.say("TWIN (5.3): E permuted within each season")
    twin = permuted(fr, "E")
    out["leg_e_twin"] = leg(rep, twin, "Leg E twin", "E", "B", boot=boot)
    d_u = persistence_d(fr, "E", "B", pairs=FRAME_U)["d"]
    d_cc = persistence_d(cc, "E", "B", min_rows=MIN_SUBSET_PAIR_ROWS)
    rep.say(f"  frame U d {_f(d_u)}; club changers d {_f(d_cc['d'])} (per pair {d_cc['per_pair']})")
    out["leg_e_guards"] = {"d_frame_u": _r(d_u), "d_club_changers": _r(d_cc["d"]),
                           "club_changers_per_pair": d_cc["per_pair"]}

    pts = club_offense(inp)
    lt = leg_t(pts)
    rep.say(f"LEG T (5.3): {lt['n_club_seasons']} club-seasons; r(off_B, runs) {_f(lt['r_off_B'])}, "
            f"r(off_E, runs) {_f(lt['r_off_E'])}; passes {lt['leg_t_pass']}")
    out["leg_t"] = lt

    rep.say("DP LEG (5.4): E-DP, eGDP per PA against Baseball-Reference runs_dp per PA")
    out["e_dp"] = leg(rep, fr, "E-DP", "G", "R", boot=boot)
    out["e_dp_twin"] = leg(rep, permuted(fr, "G"), "E-DP twin", "G", "R", boot=boot)
    d_dp_u = persistence_d(fr, "G", "R", pairs=FRAME_U)["d"]
    d_dp_cc = persistence_d(cc, "G", "R", min_rows=MIN_SUBSET_PAIR_ROWS)["d"]
    rep.say(f"  E-DP frame U d_DP {_f(d_dp_u)}; club changers d_DP {_f(d_dp_cc)}")
    out["e_dp_guards"] = {"d_frame_u": _r(d_dp_u), "d_club_changers": _r(d_dp_cc)}
    go = fr.subset(lambda r: r["GO"][0] is not None and r["GO"][1] is not None)
    dp1 = _dp1(rep, go, "DP-1", boot=boot)
    dp1_perm = _dp1(rep, permuted(go, "GO"), "DP-1 permuted", boot=boot)
    out["dp1"] = dp1
    out["dp1_permuted"] = dp1_perm
    out["dp1"]["pass"] = bool(dp1["floor_clear"] and not dp1_perm["floor_clear"])
    rep.say(f"  DP-1 passes {out['dp1']['pass']} (the permuted eGDP must fail it: "
            f"{'it fails' if not dp1_perm['floor_clear'] else 'it does NOT fail'})")
    rep.say(f"  DP-2: r(off_B + eGDP, runs) {_f(lt['r_off_B_plus_eGDP'])} against r(off_B, runs) "
            f"{_f(lt['r_off_B'])}; passes {lt['dp2_pass']}")
    wg_pairs = tuple(p for p in PAIRS if p[1] <= 2024)
    wgf = fr.subset(lambda r: r["WG"][0] is not None and r["WG"][1] is not None)
    wg = self_persistence(wgf, "WG", pairs=wg_pairs)
    gg = self_persistence(wgf, "G", pairs=wg_pairs)
    rep.say(f"  reported: feed wGdp per PA persistence {_f(wg)} against eGDP's {_f(gg)} on "
            f"{len(wg_pairs)} pairs inside 2016 to 2024")
    out["wgdp_reported"] = {"pairs": [f"{a}-{b}" for a, b in wg_pairs], "rho_wgdp": _r(wg),
                            "rho_egdp": _r(gg), "difference": _r(None if wg is None or gg is None
                                                                 else gg - wg)}

    rel = reliability(inp)
    rep.say("RELIABILITY (5.5): split-half (odd against even game_pk), Spearman-Brown, PA 300+")
    for name in list(DISPLAY) + list(PARTS):
        vals = [rel["by_season"][s][name]["reliability"] for s in sorted(rel["by_season"])]
        rep.say(f"  {name}: {vals}; NOISE {rel['noise'][name]}")
    out["reliability"] = rel

    rep.say("REPORTED BESIDE (5.6)")
    rb: dict = {}
    rb["d_frame_u"] = _r(d_u)
    rb["d_frame_x"] = _r(persistence_d(fr, "E", "B", pairs=FRAME_X)["d"])
    rb["per_pair_signs"] = {k: ("+" if v[2] > 0 else "-" if v[2] < 0 else "0")
                            for k, v in out["leg_e"]["per_pair"].items()}
    rb["d_pearson"] = _r(persistence_d(fr, "E", "B", corr=pearson)["d"])
    f502 = fr.subset(lambda r: r["pa"][0] >= PA_502 and r["pa"][1] >= PA_502)
    rb["d_pa502"] = _r(persistence_d(f502, "E", "B", min_rows=MIN_SUBSET_PAIR_ROWS)["d"])
    rb["balanced_forecast"] = _balanced(fr, boot)
    rb["cross_forecasts"] = _cross(fr)
    rb["third_party"] = _third_party(fr, inp)
    rb["club_changers_per_pair"] = d_cc["per_pair"]
    rb["per_part"] = {
        "sb_runs_vs_wsb": {"persistence_d": _r(persistence_d(fr, "SBr", "W")["d"]),
                           "same_season_mean_rho": _r(_same_season(fr, "SBr", "W"))},
        "xb_runs_vs_bsr_minus_wsb": {"persistence_d": _r(persistence_d(fr, "XBr", "BX")["d"]),
                                     "same_season_mean_rho": _r(_same_season(fr, "XBr", "BX"))}}
    rb["arms"] = _arms(fr, inp)
    for k, v in rb.items():
        rep.say(f"  {k}: {json.dumps(v, sort_keys=True)}")
    out["reported"] = rb

    rep.say("BEM+ (5.8): gate X-B1, predictor seasons 2022 to 2024")
    brows, bdrop = bem_rows(inp, ks, BEM_PRED)
    rep.say(f"  rows {len(brows)}; dropped {bdrop or 'none'}")
    out["bem_plus"] = bem_gate(brows, boot=boot)
    rep.say(f"  {json.dumps(out['bem_plus'], sort_keys=True)}")
    hrows, hdrop = bem_rows(inp, ks, BEM_HOLDOUT)
    out["bem_plus_holdout"] = bem_gate(hrows, boot=boot)
    out["bem_plus_holdout"]["dropped"] = hdrop
    rep.say(f"  holdout 2025-2026 (reported beside, never merged): "
            f"{json.dumps(out['bem_plus_holdout'], sort_keys=True)}")

    out["licenses"] = licenses(out)
    rep.say("WHAT PART 6 LICENSES under part 1's answers (EBR-Q1 (a), EBR-Q2 (a), EBR-Q3 (a))")
    for k, v in out["licenses"].items():
        rep.say(f"  {k}: {v}")
    return out


def _dp1(rep: Report, fr: Frame, name: str, *, boot: int) -> dict:
    reps = bootstrap(fr, lambda ib: self_persistence(fr, "GO", idx_by_pair=ib, min_rows=MIN_SUBSET_PAIR_ROWS),
                     boot=boot)
    sd = _sd(reps)
    rep.say(f"  floors {name}: bootstrap sd {sd:.4f}, half-width {Z90 * sd:.4f}; the floor clears when "
            f"the estimate exceeds {Z90 * sd:+.4f}")
    est = self_persistence(fr, "GO", min_rows=MIN_SUBSET_PAIR_ROWS)
    clear = bool(est is not None and not math.isnan(sd) and est - Z90 * sd > 0)
    rep.say(f"  {name}: mean rho of eGDP per opportunity {_f(est)}; estimate - 1.645 sd "
            f"{_f(None if est is None else est - Z90 * sd)}; floor clears {clear}")
    return {"estimate": _r(est), "bootstrap_sd": _r(sd), "floor_clear": clear}


def _same_season(fr: Frame, a: str, b: str):
    vals = []
    for pr in PAIRS:
        rs = [fr.rows[i] for i in fr.by_pair[pr]]
        for k in (0, 1):
            v = spearman([r[a][k] for r in rs], [r[b][k] for r in rs])
            if v is not None:
                vals.append(v)
    return sum(vals) / len(vals) if vals else None


def _zrank(v):
    import numpy as np
    r = _ranks(np.asarray(v, dtype=float))
    sd = r.std()
    return (r - r.mean()) / sd if sd else r * 0.0


def _balanced_stat(fr: Frame, idx_by_pair) -> float | None:
    vals = []
    for pr in PAIRS:
        ix = idx_by_pair.get(pr) or []
        if len(ix) < MIN_SUBSET_PAIR_ROWS:
            continue
        rs = [fr.rows[i] for i in ix]
        z = (_zrank([r["E"][1] for r in rs]) + _zrank([r["B"][1] for r in rs])) / 2.0
        a = spearman([r["E"][0] for r in rs], z)
        b = spearman([r["B"][0] for r in rs], z)
        if a is not None and b is not None:
            vals.append(a - b)
    return sum(vals) / len(vals) if vals else None


def _balanced(fr: Frame, boot: int) -> dict:
    d = _balanced_stat(fr, fr.by_pair)
    sd = _sd(bootstrap(fr, lambda ib: _balanced_stat(fr, ib), boot=boot))
    return {"dX": _r(d), "bootstrap_sd": _r(sd),
            "interval": [_r(None if d is None else d - Z90 * sd), _r(None if d is None else d + Z90 * sd)]}


def _cross(fr: Frame) -> dict:
    out = {}
    for a, b in (("E", "E"), ("E", "B"), ("B", "E"), ("B", "B")):
        vals = []
        for pr in PAIRS:
            rs = [fr.rows[i] for i in fr.by_pair[pr]]
            v = spearman([r[a][0] for r in rs], [r[b][1] for r in rs])
            if v is not None:
                vals.append(v)
        out[f"{a}_to_{b}"] = _r(sum(vals) / len(vals)) if vals else None
    return out


def _third_party(fr: Frame, inp: dict) -> dict:
    out = {}
    br = {"E": [], "B": []}
    sv = {"E": [], "B": [], "n": 0}
    for pr in PAIRS:
        rs = [fr.rows[i] for i in fr.by_pair[pr]]
        t = [r["BR"][1] for r in rs]
        for k in ("E", "B"):
            v = spearman([r[k][0] for r in rs], t)
            if v is not None:
                br[k].append(v)
        y1 = pr[1]
        sav = inp["savant"].get(y1) or {}
        keep = [(r, sav[r["pid"]]) for r in rs if r["pid"] in sav and sav[r["pid"]].get("tot") is not None
                and sav[r["pid"]].get("n")]
        if len(keep) >= MIN_SUBSET_PAIR_ROWS:
            t2 = [x["tot"] / x["n"] for _, x in keep]
            sv["n"] += len(keep)
            for k in ("E", "B"):
                v = spearman([r[k][0] for r, _ in keep], t2)
                if v is not None:
                    sv[k].append(v)
    mean = lambda v: _r(sum(v) / len(v)) if v else None  # noqa: E731
    out["bref_runs_br_per_pa_next"] = {"rho_E": mean(br["E"]), "rho_B": mean(br["B"])}
    out["savant_runner_total_per_opportunity_next"] = {"rho_E": mean(sv["E"]), "rho_B": mean(sv["B"]),
                                                       "rows": sv["n"]}
    return out


def _arms(fr: Frame, inp: dict) -> dict:
    """Leg E's d with arm P on and with arm F on (point estimates), on the pairs
    whose two seasons both carry the arm."""
    out = {}
    for arm in ("P", "F"):
        ax = inp["arm_xb"].get(arm) or {}
        rows = []
        for r in fr.rows:
            y0, y1 = r["pair"]
            if y0 not in ax or y1 not in ax:
                continue
            s0, s1 = _sub(inp, r["pid"], y0), _sub(inp, r["pid"], y1)
            x0, x1 = ax[y0].get(r["pid"], 0.0), ax[y1].get(r["pid"], 0.0)
            rr = dict(r)
            rr["EA"] = ((s0["sb"] + s0["pk"] + x0) / r["pa"][0], (s1["sb"] + s1["pk"] + x1) / r["pa"][1])
            rows.append(rr)
        sub = Frame(rows)
        pairs = tuple(p for p in PAIRS if sub.by_pair[p])
        d = persistence_d(sub, "EA", "B", pairs=pairs)["d"] if pairs else None
        out[arm] = {"d": _r(d), "pairs": [f"{a}-{b}" for a, b in pairs]}
    return out


def licenses(out: dict) -> dict:
    """Part 6 under part 1's recorded answers: EBR-Q1 (a), EBR-Q2 (a), EBR-Q3 (a)."""
    e, tw, g = out["leg_e"], out["leg_e_twin"], out["leg_e_guards"]
    lt = out["leg_t"]
    void = tw["disposition"] != "RESOLVED_LOSS"
    lic: dict = {}
    if void:
        lic["outcome look"] = "VOID (the twin is not RESOLVED_LOSS): neither outcome part is admitted, no " \
                              "comparative copy, BEM+ not served (part 6.5)"
        lic["candidate part 1"] = "not admitted (VOID)"
        lic["candidate part 2"] = "not admitted (VOID)"
        lic["copy"] = "none"
        lic["bem_plus"] = "not served (VOID)"
    else:
        p1 = (e["disposition"] == "SHIP" and lt["leg_t_pass"] is True
              and (g["d_frame_u"] or 0) > 0 and (g["d_club_changers"] or 0) > 0)
        lic["candidate part 1"] = ("ADMITTED: Leg E SHIP, Leg T passes, the twin RESOLVED_LOSS, d above 0 on "
                                   "frame U and on the club changers" if p1 else
                                   f"not admitted (Leg E {e['disposition']}, Leg T pass {lt['leg_t_pass']}, "
                                   f"d frame U {g['d_frame_u']}, d club changers {g['d_club_changers']}); "
                                   "eWAR v3 keeps FanGraphs' BsR")
        dpv = out["e_dp_twin"]["disposition"] != "RESOLVED_LOSS"
        gd = out["e_dp_guards"]
        p2 = (not dpv and out["e_dp"]["disposition"] == "SHIP" and out["dp1"]["pass"]
              and lt["dp2_pass"] is True and (gd["d_frame_u"] or 0) > 0 and (gd["d_club_changers"] or 0) > 0)
        lic["candidate part 2"] = ("VOID DP leg (the E-DP twin is not RESOLVED_LOSS): not admitted" if dpv else
                                   "ADMITTED: E-DP SHIP with its guards, DP-1 and DP-2 pass" if p2 else
                                   f"not admitted (E-DP {out['e_dp']['disposition']}, DP-1 {out['dp1']['pass']}, "
                                   f"DP-2 {lt['dp2_pass']}); eWAR v3 carries no double-play part from 2016 on")
        sentences = {"SHIP": "repeats more from one season to the next than FanGraphs' BsR on the same runners",
                     "RULED OUT": "repeats about as much from one season to the next as FanGraphs' BsR on the "
                                  "same runners",
                     "RESOLVED_LOSS": "repeats less from one season to the next than FanGraphs' BsR on the same "
                                      "runners"}
        lic["copy"] = sentences.get(e["disposition"], "none (UNDECIDED)")
        dps = {k: v.replace("FanGraphs' BsR", "Baseball-Reference's double-play runs")
               for k, v in sentences.items()}
        lic["dp copy"] = (dps.get(out["e_dp"]["disposition"], "none (UNDECIDED)")
                          if not dpv else "none (VOID DP leg)")
        lic["dp repeatable word"] = "allowed (DP-1 passes)" if out["dp1"]["pass"] else "not allowed"
        lic["bem_plus"] = "served (PASS)" if out["bem_plus"].get("pass") else "not served (FAIL)"
    lic["noise flags"] = sorted(k for k, v in out["reliability"]["noise"].items() if v) or "none"
    return lic


# ---------------------------------------------------------------------------
# preconditions
# ---------------------------------------------------------------------------
def _section(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i + len(start):j]


def part_12_1_empty(doc_text: str) -> bool:
    body = _section(doc_text, "### 12.1 The outcome look (parts 5 and 6)", "### 12.2")
    return body.strip() == "EMPTY."


def has_step_z(epoch_text: str) -> bool:
    part9 = epoch_text[epoch_text.index("## 9. Results"):]
    return re.search(r"^###\s+\d{4}-\d{2}-\d{2}:\s*step Z\b", part9, re.M) is not None


def vintage_missing_fields(vintage: dict, seasons=FRAME_SEASONS) -> list[str]:
    """Fields of part 5.1 absent from a frame season's hitting block, or null on
    any of its hitting rows."""
    missing = set()
    for s in seasons:
        h = (((vintage or {}).get("seasons") or {}).get(str(s)) or {}).get("hitting") or {}
        fields = h.get("fields") or []
        rows = h.get("rows") or {}
        if not rows:
            missing.update(VINTAGE_FIELDS)
            continue
        for f in VINTAGE_FIELDS:
            if f not in fields:
                missing.add(f)
                continue
            i = fields.index(f)
            if any(r[i] is None for r in rows.values()):
                missing.add(f)
    return [f for f in VINTAGE_FIELDS if f in missing]


def _process_lines():
    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_Process | ForEach-Object "
               "{ [string]$_.ProcessId + ' ' + [string]$_.CommandLine }"]
    else:
        cmd = ["ps", "-eo", "pid=,args="]
    try:
        text = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    out = []
    for line in text.splitlines():
        head, _, rest = line.strip().partition(" ")
        if head.isdigit():
            out.append((int(head), rest))
    return out


def busy_processes(lines=None) -> list[str]:
    """A pipeline, suite, test session or other lab, this look excluded. A failed
    listing counts as busy."""
    if lines is None:
        lines = _process_lines()
    if lines is None:
        return ["the process listing failed"]
    skip = {os.getpid(), os.getppid()}
    return [f"{pid}: {cmd[:120]}" for pid, cmd in lines
            if pid not in skip and "ebr_gate.py" not in cmd
            and any(t in cmd.lower() for t in BUSY_TOKENS)]


def preconditions(*, today: _dt.date, waived: bool, gate_text: str, epoch_text: str,
                  vintage: dict | None, preview_eval: dict | None, served_eval: dict | None,
                  substrate: dict | None, busy: list[str], pre_epoch_exists: bool) -> list[str]:
    """Every refusal of the spec, in order; an empty list means the look may run."""
    why = []
    if not part_12_1_empty(gate_text):
        why.append("EBR_GATE.md part 12.1 is not empty: the look has run")
    for name, ev in (("preview", preview_eval), ("data/", served_eval)):
        if ev and ev.get("look") is not None:
            why.append(f"the {name} eval carries a look block: a second run is forbidden")
    if not waived:
        if today < LOOK_NOT_BEFORE:
            why.append(f"the date {today} is before {LOOK_NOT_BEFORE}")
        if today in EXCLUDED_DAYS:
            why.append(f"{today} is an excluded day")
    if "## 12.2" in gate_text or "### 12.2" in gate_text:
        body = _section(gate_text, "### 12.2 The skill look (parts 9.5 and 9.6)", "### 12.3")
        if today.isoformat() in body:
            why.append(f"the skill look is recorded on {today}: not the same day")
    z = has_step_z(epoch_text)
    if not z:
        why.append("FWAR_LABEL_EPOCH_GATE.md part 9 has no step Z entry"
                   + (" and step A has started" if pre_epoch_exists else ""))
    if vintage is None:
        why.append("BLOCKER: other fwar vintage absent (data/fwar_vintage.json)")
    else:
        miss = vintage_missing_fields(vintage)
        if miss:
            why.append(f"BLOCKER: other fwar vintage lacks {', '.join(miss)}")
    if substrate is None or preview_eval is None:
        why.append("no preview build of eBR (.cache/ebr/preview)")
    else:
        ident = preview_eval.get("identity") or {}
        bad = [s for s in FRAME_SEASONS if not (ident.get(str(s)) or {}).get("all_pass")
               or ((ident.get(str(s)) or {}).get("I8") or {}).get("unchanged") is False]
        if bad:
            why.append(f"frame seasons failing I1 to I9: {bad}")
        if not waived:
            frozen = (substrate.get("cadence") or {}).get("frozen_seasons") or []
            gen = str(substrate.get("generated_at") or "")[:10]
            if 2026 not in frozen or gen < FREEZE_2026.isoformat():
                why.append("2026 was built before 2026-11-01 (not frozen in the substrate)")
    if busy:
        why.append(f"busy: {busy[:5]}")
    return why


# ---------------------------------------------------------------------------
# loading the real inputs (read only; nothing is fetched)
# ---------------------------------------------------------------------------
def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _read_json(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_inputs(rep: Report) -> dict:
    import pandas as pd

    import build_ebr
    import build_runner_moves as brm
    import ebr
    import mlb_team_season
    import savant_running
    import trades
    import war_source
    stamps: dict = {}
    vintage = json.loads(VINTAGE.read_text(encoding="utf-8"))
    stamps["vintage_id"] = vintage.get("vintage_id")
    stamps["vintage_sha256"] = _sha_file(VINTAGE)
    bat_path = war_source._cache_path("bat")
    stamps["bref_frame_sha256"] = _sha_file(bat_path)
    stamps["bref_frame_fetched_at"] = _dt.datetime.fromtimestamp(
        bat_path.stat().st_mtime, _dt.timezone.utc).replace(microsecond=0).isoformat()
    rep.say(f"fWAR vintage {stamps['vintage_id']} sha256 {stamps['vintage_sha256']}")
    rep.say(f"Baseball-Reference frame (cached, never fetched) sha256 {stamps['bref_frame_sha256']} "
            f"fetched_at {stamps['bref_frame_fetched_at']}")
    sub_blob = _read_json(PREVIEW_DIR / "ebr.json")
    stamps["substrate_generated_at"] = sub_blob.get("generated_at")
    stamps["pool_sha256"] = (sub_blob.get("stamps") or {}).get("pool_sha256")
    stamps["record_built_at"] = (sub_blob.get("stamps") or {}).get("record_built_at")
    fields = sub_blob["fields"]
    sub: dict = defaultdict(dict)
    for r in sub_blob["rows"]:
        d = dict(zip(fields, r))
        sub[int(d["season"])][int(d["mlbam"])] = d
    lines, fg, bref, stints, team_runs, savant, sprint = {}, {}, {}, {}, {}, {}, {}
    vh = vintage["seasons"]
    bat = pd.read_parquet(bat_path, columns=["mlb_ID", "year_ID", "team_ID", "PA", "runs_br", "runs_dp"])
    bat["mlb_ID"] = pd.to_numeric(bat["mlb_ID"], errors="coerce")
    bat = bat.dropna(subset=["mlb_ID"])
    sprint_blob = _read_json(SPRINT) or {}
    team_fetch = {}
    for s in FRAME_SEASONS:
        ln, sha, _ = brm.official_lines(s)
        lines[s] = {pid: {"pa": c["pa"], "sb": c["sb"]} for pid, c in (ln or {}).items()}
        stamps[f"lines_{s}_sha256"] = sha
        h = vh[str(s)]["hitting"]
        fl = h["fields"]
        fg[s] = {int(pid): dict(zip(fl, row)) for pid, row in h["rows"].items()}
        d = bat[bat["year_ID"] == s]
        bref[s], stints[s] = {}, defaultdict(list)
        for mid, g in d.groupby("mlb_ID"):
            bref[s][int(mid)] = {"runs_br": float(pd.to_numeric(g["runs_br"], errors="coerce").sum()),
                                 "runs_dp": float(pd.to_numeric(g["runs_dp"], errors="coerce").sum()),
                                 "pa": float(pd.to_numeric(g["PA"], errors="coerce").fillna(0).sum())}
            for t, pa in zip(g["team_ID"], pd.to_numeric(g["PA"], errors="coerce").fillna(0)):
                if pa > 0 and isinstance(t, str):
                    stints[s][int(mid)].append((trades.canonical_org(t), float(pa)))
        doc = mlb_team_season.cached(s, "hit")
        team_fetch[str(s)] = doc.get("fetched_at")
        team_runs[s] = {r["club"]: mlb_team_season.parse_team_line(r["stat"], "hit")["r"] for r in doc["rows"]}
        sv = savant_running.load(s, offline=True)
        savant[s] = {int(m): {"tot": r.get("runner_runs_tot"), "n": r.get("N_runner_moved")}
                     for m, r in sv["brv"].items()}
        sprint[s] = {int(m): float(v[str(s)]["ft_s"]) for m, v in (sprint_blob.get("by_mlbam") or {}).items()
                     if isinstance(v, dict) and isinstance(v.get(str(s)), dict)
                     and v[str(s)].get("ft_s") is not None}
    stamps["team_runs_fetched_at"] = team_fetch
    rep.say(f"club season lines fetched_at {team_fetch}")
    # per-game credits (split-half) and the arms, recomputed from the record once
    data, man = build_ebr.load_record(seasons=list(FRAME_SEASONS))
    pool = json.loads(FROZEN_POOL.read_text(encoding="utf-8"))
    ebr.check_frozen_pool(pool)
    raw = {s: ebr.season_raw(pa) for s, (pa, rn) in data.items()}
    opps = {}
    for s, (pa, rn) in data.items():
        o = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(o)
        opps[s] = o
    arm_blob = _read_json(ARM)
    per_game, arm_xb = {}, {"P": {}, "F": {}}
    mismatch = {}
    for s in sorted(data):
        pa, rn = data[s]
        table = ebr.shrunk_table(raw[s], pool["re_pool"], float(pool["K"]), s)
        credits, _, _ = ebr.season_credits(pa, rn, table, pool["xb_pool_counts"], opps=opps[s])
        rows = ebr.substrate_rows(s, ebr.player_rows(credits, pa, opps[s]))
        mismatch[str(s)] = sum(1 for r in rows if dict(zip(ebr.FIELDS, r)) != sub[s].get(r[0]))
        pg = defaultdict(lambda: {"odd": defaultdict(float), "even": defaultdict(float)})
        for mid, _, g, part, v in credits:
            if mid is not None:
                pg[mid]["odd" if g % 2 else "even"][part] += v
        per_game[s] = pg
        bo = ebr.Backoff(opps[s], pool["xb_pool_counts"])
        prior = [op for y in (s - 3, s - 2, s - 1) for op in opps.get(y, [])]
        if prior:
            c_arm, _ = ebr.xb_parts(opps[s], ebr.RE(table), bo,
                                    pi_override=ebr.arm_p_override(opps[s], prior, bo))
            arm_xb["P"][s] = ebr.xb_by_runner(c_arm)
        tf = build_ebr.arm_tercile_fn(s, arm_blob)
        if tf is not None:
            c_arm, _ = ebr.xb_parts(opps[s], ebr.RE(table), bo,
                                    pi_override=ebr.arm_f_override(opps[s], tf, bo))
            arm_xb["F"][s] = ebr.xb_by_runner(c_arm)
    rep.say(f"substrate rows the record no longer reproduces, per season: {mismatch}")
    stamps["substrate_mismatch"] = mismatch
    return {"sub": dict(sub), "lines": lines, "fg": fg, "bref": bref, "stints": dict(stints),
            "team_runs": team_runs, "savant": savant, "sprint": sprint, "per_game": per_game,
            "arm_xb": arm_xb, "stamps": stamps}


# ---------------------------------------------------------------------------
# synthetic inputs for --dry-run (with nulls)
# ---------------------------------------------------------------------------
def synthetic_inputs(seed: int = 7, n_players: int = 420) -> dict:
    """A fake league over the frame seasons: persistent runner talent plus noise,
    every input the look reads, and nulls in each optional series."""
    import numpy as np
    rng = np.random.default_rng(seed)
    clubs = [f"C{i:02d}" for i in range(30)]
    talent = rng.normal(0, 1, n_players)
    dp_talent = rng.normal(0, 1, n_players)
    home = rng.integers(0, 30, n_players)
    inp = {k: {} for k in ("sub", "lines", "fg", "bref", "stints", "team_runs", "savant", "sprint",
                           "per_game")}
    inp["arm_xb"] = {"P": {}, "F": {}}
    for s in FRAME_SEASONS:
        sub, lines, fg, bref, stints, sav, spr, pg = {}, {}, {}, {}, {}, {}, {}, {}
        moved = rng.random(n_players) < 0.15
        home = np.where(moved, rng.integers(0, 30, n_players), home)
        for i in range(n_players):
            pid = 100000 + i
            if rng.random() < 0.06:
                continue                       # a missed season
            pa = int(rng.integers(150, 700))
            starts = int(pa * 0.3)
            sbv = 0.004 * pa * (talent[i] + rng.normal(0, 0.8)) / 3
            pkv = rng.normal(0, 0.3)
            xa = 0.004 * pa * (talent[i] + rng.normal(0, 0.9)) / 2
            xo = rng.normal(0, 0.5)
            dpv = 0.003 * pa * (dp_talent[i] + rng.normal(0, 1.0)) / 2
            sub[pid] = {"mlbam": pid, "season": s, "pa": pa, "starts_on_base": starts,
                        "opp_sb": int(starts * 0.7), "opp_xb": int(starts * 0.5), "opp_dp": int(pa * 0.2),
                        "sb": sbv, "pk": pkv, "xb_adv": xa, "xb_oob": xo, "dp": dpv,
                        "ebr": sbv + pkv + xa + xo + dpv}
            lines[pid] = {"pa": pa, "sb": max(0, int(talent[i] * 5 + 8 + rng.normal(0, 3)))}
            bsr = sbv + xa + xo + rng.normal(0, 0.8)
            fg[pid] = {"baseRunning": (None if rng.random() < 0.01 else bsr), "wSb": sbv + rng.normal(0, 0.3),
                       "ubr": xa, "wGdp": (dpv if s <= 2024 else None), "batting": rng.normal(0, 8),
                       "plateAppearances": pa, "numTeams": 1}
            bref[pid] = {"runs_br": sbv + xa + rng.normal(0, 1.0),
                         "runs_dp": (None if rng.random() < 0.01 else dpv + rng.normal(0, 0.5)), "pa": pa}
            stints[pid] = [(clubs[int(home[i])], float(pa))]
            if rng.random() < 0.9:
                sav[pid] = {"tot": xa + rng.normal(0, 0.5), "n": int(starts * 0.6) or None}
            if rng.random() < 0.85:
                spr[pid] = 27.0 + talent[i] + rng.normal(0, 0.5)
            odd = {p: sub[pid][p] * 0.5 + rng.normal(0, 0.3) for p in PARTS}
            pg[pid] = {"odd": odd, "even": {p: sub[pid][p] - odd[p] for p in PARTS}}
        inp["sub"][s], inp["lines"][s], inp["fg"][s] = sub, lines, fg
        inp["bref"][s], inp["stints"][s], inp["savant"][s] = bref, stints, sav
        inp["sprint"][s], inp["per_game"][s] = spr, pg
        runs = defaultdict(float)
        for pid, st in stints.items():
            f = fg[pid]
            runs[st[0][0]] += (f["batting"] + (f["baseRunning"] or 0.0)) + rng.normal(0, 2)
        inp["team_runs"][s] = {c: 700 + v for c, v in runs.items()}
        inp["arm_xb"]["P"][s] = {pid: v["xb_adv"] + v["xb_oob"] + rng.normal(0, 0.1) for pid, v in sub.items()}
        if s >= 2021:
            inp["arm_xb"]["F"][s] = {pid: v["xb_adv"] + v["xb_oob"] for pid, v in sub.items()}
    inp["stamps"] = {"vintage_id": "synthetic", "vintage_sha256": "0" * 64,
                     "bref_frame_sha256": "0" * 64, "bref_frame_fetched_at": "synthetic"}
    return inp


# ---------------------------------------------------------------------------
# writing the two places the look may write
# ---------------------------------------------------------------------------
def write_look_block(block: dict, eval_path: Path) -> None:
    eval_path = Path(eval_path)
    if eval_path.resolve().parent == (ROOT / "data").resolve():
        raise Refused("the look never writes under data/")
    ev = _read_json(eval_path) or {}
    ev["look"] = block
    tmp = eval_path.with_suffix(eval_path.suffix + ".tmp")
    tmp.write_text(json.dumps(ev, indent=1, sort_keys=True, separators=(",", ": ")), encoding="utf-8")
    tmp.replace(eval_path)


def part_12_1_text(*, today: _dt.date, commit: str, waived: bool, licenses_: dict, output: str) -> str:
    head = f"**{today.isoformat()}, `python -u tools/ebr_gate.py` at `{commit}`"
    head += f", {WAIVER_NOTE}.**" if waived else ".**"
    lic = "\n".join(f"- {k}: {v if isinstance(v, str) else ', '.join(v)}" for k, v in licenses_.items())
    return (f"{head}\n\nWhat part 6 licenses under part 1's recorded answers (EBR-Q1 (a), EBR-Q2 (a), "
            f"EBR-Q3 (a)):\n\n{lic}\n\nThe output of `tools/ebr_gate.py`, verbatim:\n\n```text\n{output}\n```\n")


def write_part_12_1(text: str, doc_path: Path = GATE_DOC) -> None:
    raw = Path(doc_path).read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    doc = raw.decode("utf-8")
    head = f"### 12.1 The outcome look (parts 5 and 6){nl}{nl}EMPTY.{nl}"
    if doc.count(head) != 1:
        raise Refused("part 12.1 is not the registered EMPTY block")
    new = f"### 12.1 The outcome look (parts 5 and 6){nl}{nl}" + text.replace("\n", nl)
    Path(doc_path).write_bytes(doc.replace(head, new).encode("utf-8"))


def _head_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=30, check=True).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def dry_run(rep: Report, *, boot: int = 200, out_dir: Path | None = None) -> dict:
    """The whole reporting path on synthetic fixtures with nulls; writes only into
    out_dir when one is given (a copy of the two write targets), never the real ones."""
    rep.say(f"DRY RUN on synthetic fixtures with nulls (boot {boot}); nothing real is read or written")
    inp = synthetic_inputs()
    out = run_look(inp, rep, boot=boot)
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ev = out_dir / "dry_run_ebr_eval.json"
        ev.write_text("{}", encoding="utf-8")
        write_look_block({"status": "dry-run", "result": out}, ev)
        doc = out_dir / "dry_run_EBR_GATE.md"
        doc.write_text("### 12.1 The outcome look (parts 5 and 6)\n\nEMPTY.\n\n### 12.2 x\n", encoding="utf-8")
        write_part_12_1(part_12_1_text(today=_dt.date.today(), commit=_head_commit(), waived=False,
                                       licenses_=out["licenses"], output=rep.text()), doc)
    return out


def look(rep: Report, *, today: _dt.date, waived: bool, eval_path: Path = PREVIEW_DIR / "ebr_eval.json",
         doc_path: Path = GATE_DOC) -> int:
    pre = preconditions(
        today=today, waived=waived, gate_text=Path(doc_path).read_text(encoding="utf-8"),
        epoch_text=EPOCH_DOC.read_text(encoding="utf-8"),
        vintage=_read_json(VINTAGE) if VINTAGE.exists() else None,
        preview_eval=_read_json(eval_path), served_eval=_read_json(SERVED_EVAL),
        substrate=_read_json(Path(eval_path).parent / "ebr.json"), busy=busy_processes(),
        pre_epoch_exists=any(p.exists() for p in PRE_EPOCH_DIRS))
    if pre:
        rep.say("REFUSED: the outcome look does not run.")
        for w in pre:
            rep.say(f"  {w}")
        for w in pre:
            if w.startswith("BLOCKER:"):
                rep.say(w)
        return 2
    commit = _head_commit()
    rep.say(f"eBR OUTCOME LOOK {today.isoformat()} at {commit}"
            + (f"  [{WAIVER_NOTE}]" if waived else ""))
    started = {"status": "started", "started_at": _dt.datetime.now(_dt.timezone.utc).replace(
        microsecond=0).isoformat(), "commit": commit, "waived_early_read": waived}
    write_look_block(started, eval_path)
    try:
        inp = load_inputs(rep)
        out = run_look(inp, rep, boot=BOOT)
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        rep.say("CRASH after scoring began. STOP: no rerun; an owner question (part 5.9).")
        rep.say(tb)
        write_look_block(dict(started, status="crashed", traceback=tb[-4000:]), eval_path)
        return 3
    block = dict(started, status="complete", finished_at=_dt.datetime.now(_dt.timezone.utc).replace(
        microsecond=0).isoformat(), stamps=inp["stamps"], result=out)
    write_look_block(block, eval_path)
    write_part_12_1(part_12_1_text(today=today, commit=commit, waived=waived,
                                   licenses_=out["licenses"], output=rep.text()), doc_path)
    if waived:
        rep.say("This read is an OWNER-WAIVED EARLY READ: append the dated note below the gate "
                "document's last section in the look's commit.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the eBR outcome look (runs once)")
    ap.add_argument("--out-dir", default=None, help="the writer's output directory (stdout and stderr teed)")
    ap.add_argument("--dry-run", action="store_true", help="synthetic fixtures with nulls; nothing real")
    ap.add_argument("--boot", type=int, default=200, help="dry run only: bootstrap replicates")
    ap.add_argument("--owner-waived-early-read", action="store_true",
                    help="lift the date clauses only (owner EW3-5, 2026-10-14)")
    a = ap.parse_args(argv)
    today = _dt.date.today()
    if a.out_dir:
        od = Path(a.out_dir)
        od.mkdir(parents=True, exist_ok=True)
        tag = "dry_run" if a.dry_run else "look"
        fh = open(od / f"ebr_gate_{tag}_{today.isoformat()}.log", "a", encoding="utf-8")
        sys.stdout = _Tee(sys.__stdout__, fh)
        sys.stderr = _Tee(sys.__stderr__, fh)
    rep = Report()
    if a.dry_run:
        dry_run(rep, boot=a.boot, out_dir=(Path(a.out_dir) / "dry_run") if a.out_dir else None)
        return 0
    if not a.out_dir:
        print("REFUSED: the look needs --out-dir (its stdout and stderr are teed there first)")
        return 2
    return look(rep, today=today, waived=a.owner_waived_early_read)


if __name__ == "__main__":
    sys.exit(main())
