# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV, age graded on a curve within level, as SKILL-head columns (EFV4_AGE_CURVE; owner
decision EW2-13, 2026-10-10: "grading age on a curve where it boosts players youngest for
their level the most and punishes players oldest for their level the most").

WHY THIS IS NOT A CLOSED ARM. age_rel_level is today a TIMING-head driver only (when a
player debuts, not how good he becomes); the closed age arms were a linear hitter age
term, age products and splits, and a context correction to consensus. None was a graded,
playing-time-weighted, nonlinear position of the player in his level-season's age
distribution offered to the SKILL head on the fWAR label.

THE COLUMN. For a read at year V as of its cutoff (efv_w2_milb.last_readable_season, the
efv_dataset as-of rule), take the most recent readable season in which the player has a
MiLB line of at least LINE_MIN exposure (50 PA hitters, 60 BF pitchers), walking back at
most MAX_BACK seasons. For each such line at level L, place his age in the (season, L,
side) age distribution of every line with at least NORM_MIN exposure (StatsAPI season
age, whole years): the z-score against that distribution and the mid-rank share of the
distribution OLDER than him (p, so the youngest have p near 1). The column is the
exposure-weighted mean over his lines that season of one of four curves, each declared
2026-10-10 before any read:

    C1 linear     -z                                    (younger is better, straight line)
    C2 graded     probit(p), clipped to [-2.5, +2.5]    (the curve: tails move most)
    C3 tails      +(p - 0.9) / 0.1 when p >= 0.9, -(0.1 - p) / 0.1 when p <= 0.1, else 0
    C4 graded x level   C2 times the level weight AAA 1.3, AA 1.2, A+ 1.1, A 1.0,
                  CPX 0.9, DSL 0.8 (young at a harder level counts more, old at a harder
                  level is punished more)

Ages are whole years in the source, so many players tie; mid-ranks share ties evenly.

THE READS reuse efv_w2_milb's development pipeline unchanged (lv_dev through the
screening lab's Frame and measure_arm with DS-06 admission per fold; vm_dev at vm2 with
the base parity check), with this module's columns swapped in. Spent frames are not read
here; a configuration that clears the development bar is read there by its own step.

BANS. No served number moves; nothing served imports this module. Nothing groups by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md). No column reads a label, WAR or debut.

Run:  python efv_w2_agecurve.py --dev-read [--B 2000]
      python efv_w2_agecurve.py --ledger
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from statistics import NormalDist

import efv_w2_milb as M

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "data" / "_labs" / "efv_w2" / "efv_w2_agecurve.json"
TOOL = "efv_w2_agecurve.py"

MAX_BACK = 3
CLIP = 2.5
TAIL = 0.10
LEVEL_WEIGHT = {"AAA": 1.3, "AA": 1.2, "A+": 1.1, "A": 1.0, "CPX": 0.9, "DSL": 0.8}
CURVES = ("c1_linear", "c2_graded", "c3_tails", "c4_graded_level")

STATS: dict[str, dict] = {f"{c}_{s}": {"side": s, "curve": c, "k": 0.0}
                          for s in ("hit", "pit") for c in CURVES}
ARMS: tuple[dict, ...] = tuple(
    {"name": f"w2a_{st}", "stat": st, "side": spec["side"], "head": "skill",
     "kind": "column", "retest": False,
     "column": {"source": "module", "module": "efv_w2_agecurve", "attr": "screen_column",
                "arg": st}}
    for st, spec in STATS.items())
NOTE = ("eFV age curve (EFV4_AGE_CURVE, owner EW2-13 2026-10-10), development read only: "
        "selects and adjudicates nothing; no served number moves")

_ND = NormalDist()
_DIST: dict = {}


def level_ages(season: int, level: str, side: str) -> list[float]:
    """Sorted ages of every line at (season, level, side) with NORM_MIN exposure."""
    key = (int(season), level, side)
    if key not in _DIST:
        ages = []
        for lvls in M.season_lines(int(season), side).values():
            slot = lvls.get(level)
            if slot and slot.get("age") is not None and \
                    M.exposure(slot["counts"], side) >= M.NORM_MIN[side]:
                ages.append(float(slot["age"]))
        _DIST[key] = sorted(ages)
    return _DIST[key]


def position(age: float, ages: list[float]) -> tuple[float, float] | None:
    """(z, p): z against the distribution, p the mid-rank share OLDER than `age`."""
    n = len(ages)
    if n < M.NORM_MIN_LINES:
        return None
    mean = sum(ages) / n
    sd = math.sqrt(sum((a - mean) ** 2 for a in ages) / (n - 1)) if n > 1 else 0.0
    if sd <= 0:
        return None
    older = sum(1 for a in ages if a > age)
    same = sum(1 for a in ages if a == age)
    p = (older + 0.5 * same) / n
    return (age - mean) / sd, p


def curve_value(curve: str, z: float, p: float, level: str) -> float:
    if curve == "c1_linear":
        return -z
    pc = min(max(p, 1e-6), 1 - 1e-6)
    graded = max(-CLIP, min(CLIP, _ND.inv_cdf(pc)))
    if curve == "c2_graded":
        return graded
    if curve == "c3_tails":
        if p >= 1 - TAIL:
            return (p - (1 - TAIL)) / TAIL
        if p <= TAIL:
            return -(TAIL - p) / TAIL
        return 0.0
    if curve == "c4_graded_level":
        return graded * LEVEL_WEIGHT.get(level, 1.0)
    raise ValueError(curve)


def profile(mlbam, read_year: int, cutoff, side: str, floor: int, stats=None) -> dict:
    """{stat: value | None} for one person, read at `read_year` as of `cutoff`."""
    stats = [s for s in (stats or STATS) if STATS[s]["side"] == side]
    out: dict = {s: None for s in stats}
    out["_seasons"] = []
    if not mlbam:
        return out
    pid = int(mlbam)
    top = M.last_readable_season(read_year, cutoff)
    for season in range(top, max(int(floor), top - MAX_BACK + 1) - 1, -1):
        lvls = M.season_lines(season, side).get(pid) or {}
        lines = []
        for lv, slot in lvls.items():
            w = M.exposure(slot["counts"], side)
            if w < M.LINE_MIN[side] or slot.get("age") is None:
                continue
            pos = position(float(slot["age"]), level_ages(season, lv, side))
            if pos is not None:
                lines.append((lv, w, pos))
        if not lines:
            continue
        out["_seasons"].append(season)
        tot = sum(w for _, w, _ in lines)
        for s in stats:
            c = STATS[s]["curve"]
            out[s] = sum(w * curve_value(c, z, p, lv) for lv, w, (z, p) in lines) / tot
        break
    return out


def screen_column(stat: str, side: str, frames: dict) -> dict:
    return M.screen_column(stat, side, frames)


def norms_receipt() -> dict:
    """Lines per (side, season, level) in the age distributions the curves read."""
    out = {}
    for side in ("hit", "pit"):
        for season in M.SEASONS:
            for lv in LEVEL_WEIGHT:
                n = len(level_ages(season, lv, side))
                if n:
                    out[f"{side}|{season}|{lv}"] = n
    return out


def _install():
    """Point efv_w2_milb's development pipeline at this module's columns."""
    M.norms_receipt = norms_receipt
    M.STATS = STATS
    M.ARMS = ARMS
    M.profile = profile
    M.NOTE = NOTE
    M.TOOL = TOOL
    M.ABSENT = {}
    M.OUT_PATH = OUT_PATH
    M._LV_CACHE.clear()
    M._cand_orig = getattr(M, "_cand_orig", M._cand)

    def _cand(arm):
        out = M._cand_orig(arm)
        out["what"] = f"{arm['stat']}: age graded on a curve within level (efv_w2_agecurve)"
        return out
    M._cand = _cand


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dev-read", action="store_true")
    ap.add_argument("--ledger", action="store_true")
    ap.add_argument("--ledger-path", default=None)
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args()
    _install()
    if a.dev_read:
        t0 = time.time()
        res = M.dev_read(B=a.B, out=OUT_PATH)
        print(json.dumps(res["summary"], indent=1), f"{time.time() - t0:.0f} s")
    if a.ledger:
        print(json.dumps(M.update_ledger(path=OUT_PATH, ledger_path=a.ledger_path), indent=1))
