# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 skill look's lab (candidate parts 3 to 6), registered in
docs/ebr-2026-09-30/EBR_GATE.md parts 9.5 and 9.6, which this file implements
with their parameters exactly and does not extend.

    python tools/swar_lab.py --dry-run          # synthetic fixtures with nulls, a temp dir only
    python -u tools/swar_lab.py --out docs/ebr-2026-09-30/swar_eval.json   # THE LOOK, once
    python -u tools/swar_lab.py --holdout       # THE HOLDOUT, once, a later day

THE QUESTION, per candidate part: does fWAR(Y) plus the part's re-centred delta
rank published fWAR(Y+1) better than fWAR(Y) does? Pairs (Y, Y+1) for
predictor seasons 2021 to 2024 (2020 out on both sides); hitters 200 PA and
pitchers 50 IP in both seasons; the target published fWAR(Y+1) per PA or per
IP (the rate cell) and in total (the cumulative cell).

WHAT IS FIXED HERE, BY REGISTRATION. Each candidate part is its own Holm
family over its own cells (position {H-rate, H-cum}; batting {HEM+ H-rate,
HEM+ H-cum, xHEM+ H-rate, xHEM+ H-cum}; pitching {P-rate, P-cum}; fielding
{H-rate, H-cum}); no correction across parts. Spearman gap against B0 =
fWAR(Y); convention v2 primary (player-clustered, season-stratified
bootstrap, within-outcome-season z target), v1 reported and required to agree
in sign (iid pair bootstrap, raw pooled target); Pearson beside, no weight.
B1, the uniformly shrunk fWAR (x n + m k) / (n + k), one k per side fitted on
the 2016 to 2018 predictor pairs on published fWAR only and frozen below
before the look. The twin: the part's delta permuted across players within
(season, side, exposure decile), added back to fWAR. Era transport (pitching):
the P-rate point gap positive in the 2016 to 2018 block and the 2021 to 2024
block. The home-run arm clause is computed FIRST: the P-rate gap of the
home-run-shrunk pitching part over the part on fWAR's own home-run term must
be positive in both blocks under v2, else the home-run term reverts to
fWAR's. MDE95 = 1.645 bootstrap sd, printed with the sd and the half-width of
every cell before any gap. B = 2,000, seed 20261008.

DISPOSITIONS (orchestrator ruling X1). Each cell takes the first disposition
that holds in the order WIN, SMALL WIN, LOSS, EQUIVALENT, UNRESOLVED, so
exactly one applies: disposition() below, a pure function. ADMISSION (part
9.6) under part 1's recorded answers EWV3-Q1 (a) and EWV3-Q2 (a): admit()
below, a pure function. The batting tie-break contrast (rho of the xHEM+ test
value minus rho of the HEM+ test value, same pairs, same bootstrap) is
computed only when both arms qualify, outside the Holm family.

DESCRIPTIVE LEGS (no verdict weight, labelled descriptive in the record):
delta sizes, agreement with fWAR and bWAR, team-season sums against
same-season and next-season wins (computed only in a look run, printed only
to its output and its record), self-persistence, exposure-band bias, the
starter-heavy and reliever subsets of the pitching part, the L-B (gmLI 1)
disclosure, split-half calibration of the batting and pitching constants on
the play-by-play corpus, and the coverage census.

INPUTS. The fresh preview tools/build_swar.py writes (.cache/swar/preview/
swar.json: fWAR from the frozen vintage, PA, IP and every part's test value
per player-season), the frozen vintage's id, the cached bWAR frames
(war_source's last-good cache, never fetched), the cached StatsAPI
standings (ewar.standings, never fetched) and the play-by-play corpus. The lab
WRITES only its record (--out, never under data/) or, under --dry-run, a
temporary directory. A second run of the look or of the holdout is refused.

THE PITCHING BASIS (part 11.3, owner decision EW3-20). Candidate part 5 has
two arms, S2 (the cells P-rate, P-cum) and the blended basis S2b (S2b P-rate,
S2b P-cum), in ONE Holm family of k = 4. S2b's series is its build on the
home-run term the HR-arm clause chose for S2 (the clause reads S2 only). The
era transport clause applies to each arm's own rate cell. Admission mirrors the
batting arms: one qualifying arm enters; when both qualify S2 enters unless
S2b's rate gap over S2's (same pairs, same bootstrap, outside the Holm family)
has lo95 above 0 (PITCHING_ARM_RULE, the default of owner question PB-Q1).
This lab still scores every cell on published fWAR(Y+1); part 11.2.10's
amendment work (the primary targets, RA9*(Y+1) for pitching, which the preview
now carries per pitcher-season as ra9_star) lands before the look.

CRASH PROTOCOL. The operator tees stdout and stderr to the writer's output
directory before the run. An exception after scoring began writes a VOID
record (which admits nothing) to the record path and exits 3; no rerun.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import swar  # noqa: E402  (pure: the version stamp and the K constants, by reference)

LAB_VERSION = "swar_lab/1"
REGISTRATION = "docs/ebr-2026-09-30/EBR_GATE.md parts 9.5 and 9.6"
DEFAULT_RECORD = ROOT / "docs" / "ebr-2026-09-30" / "swar_eval.json"
PREVIEW_PATH = ROOT / ".cache" / "swar" / "preview" / "swar.json"
PBP_PLAYS_DIR = ROOT / ".cache" / "pbp_corpus" / "plays"

# --------------------------------------------------------------------------
# registered parameters (part 9.5)
# --------------------------------------------------------------------------

SEED = 20261008
BOOT = 2000
MARGIN = 0.02
ALPHA = 0.05
MDE_Z = 1.645
PREDICTOR_SEASONS = (2021, 2022, 2023, 2024)
TRANSPORT_EARLY_SEASONS = (2016, 2017, 2018)
HOLDOUT_SEASONS = (2025,)
B1_FIT_SEASONS = (2016, 2017, 2018)
EXCLUDED_SEASON = 2020
MIN_PA = 200.0
MIN_IP = 50.0

#: The recorded answers of part 1 (DECISIONS_FOR_OWNER.md, 2026-10-01).
ANSWERS = {"EWV3-Q1": "a", "EWV3-Q2": "a"}

# --------------------------------------------------------------------------
# B1: one k per side, FROZEN before the look
# --------------------------------------------------------------------------

#: B1's shrink constants, in plate appearances (hit) and innings (pit). FIXED
#: by EWV3_SKILL_BUILD_LAB on 2026-10-14 from the 2016 to 2018 predictor pairs
#: (outcomes 2017 to 2019), published fWAR only, before any look, with the
#: rule of positional_fit.fit_signal that DEM+'s K_INN used (the precedent
#: part 9.5 cites): the pooled Pearson year-over-year r of fWAR per PA (per
#: IP) on pairs at the look's floors in both seasons, r clamped to [0.05,
#: 0.95], k = hm x (1 - r) / r with hm the mean harmonic exposure of the pairs,
#: rounded to a whole unit. tools/swar_b1_fit.py reproduces it; it reads only
#: fWAR, PA and IP and computes no statistic of any candidate part. Fit output,
#: for the record:
#:   hit  pairs 800  players 380  r 0.4160  hm 471.4 PA  k 662 PA
#:   pit  pairs 670  players 356  r 0.3108  hm 109.9 IP  k 244 IP
#: (preview vintage 2026-10-02-0341299c20ec, preview built 2026-10-14.)
#: The shrink target m is the season's own exposure-weighted fWAR rate over
#: that side's rows at the floor in that season (sum fWAR / sum n).
B1_K = {"hit": 662.0, "pit": 244.0}
B1_FIT_LOG = {
    "fixed_on": "2026-10-14",
    "task": "EWV3_SKILL_BUILD_LAB",
    "producer": "python tools/swar_b1_fit.py",
    "rule": ("positional_fit.fit_signal (the DEM+ K_INN precedent): pooled Pearson "
             "year-over-year r of fWAR per exposure on pairs at the look's floors in "
             "both seasons, r clamped [0.05, 0.95], k = hm (1 - r) / r, hm the mean "
             "harmonic exposure of the pairs, rounded to a whole unit"),
    "shrink_target": ("m: the season's exposure-weighted fWAR rate over the side's rows "
                      "at the floor in that season"),
    "fit_seasons": [2016, 2017, 2018],
    "floors": {"hit_pa": 200.0, "pit_ip": 50.0},
    "fwar_vintage_id": "2026-10-02-0341299c20ec",
    "hit": {"n_pairs": 800, "n_players": 380, "r": 0.4160, "hm": 471.4, "k": 662.0},
    "pit": {"n_pairs": 670, "n_players": 356, "r": 0.3108, "hm": 109.9, "k": 244.0},
}

R_CLAMP = (0.05, 0.95)

# --------------------------------------------------------------------------
# the candidate parts and their cells
# --------------------------------------------------------------------------

HIT, PIT = "hit", "pit"
RATE, CUM = "rate", "cum"

PART_POSITION, PART_BATTING, PART_PITCHING, PART_FIELDING = (
    "position", "batting", "pitching", "fielding")
PARTS = (PART_POSITION, PART_BATTING, PART_PITCHING, PART_FIELDING)

#: Per part: its side, and its cells as {cell: (series, kind)}. The pitching
#: part's series is the home-run variant the HR-arm clause picks (PITCH below).
PITCH = "__pitching__"
#: The blended pitching basis S2b (part 11.3): its series is the S2b build on the
#: home-run variant the HR-arm clause picks for S2.
PITCH_B = "__pitching_blend__"
PB_PREFIX = "pb_"


def pb_key(variant: str) -> str:
    """The preview key of S2b on one home-run variant of S2."""
    return PB_PREFIX + variant


PB_VARIANTS = tuple(pb_key(v) for v in swar.HR_VARIANTS)
PART_CELLS: Mapping[str, dict] = {
    PART_POSITION: {"side": HIT, "cells": {"H-rate": ("pos", RATE), "H-cum": ("pos", CUM)}},
    PART_BATTING: {"side": HIT, "cells": {
        "HEM+ H-rate": ("bat", RATE), "HEM+ H-cum": ("bat", CUM),
        "xHEM+ H-rate": ("batx", RATE), "xHEM+ H-cum": ("batx", CUM)}},
    PART_PITCHING: {"side": PIT, "cells": {"P-rate": (PITCH, RATE), "P-cum": (PITCH, CUM),
                                           "S2b P-rate": (PITCH_B, RATE), "S2b P-cum": (PITCH_B, CUM)}},
    PART_FIELDING: {"side": HIT, "cells": {"H-rate": ("fld", RATE), "H-cum": ("fld", CUM)}},
}
#: The batting part's two arms: {arm: (rate cell, cumulative cell)}.
BATTING_ARMS = {"HEM+": ("HEM+ H-rate", "HEM+ H-cum"), "xHEM+": ("xHEM+ H-rate", "xHEM+ H-cum")}
#: The pitching part's two arms (part 11.3): {arm: (rate cell, cumulative cell)}.
PITCHING_ARMS = {"S2": ("P-rate", "P-cum"), "S2b": ("S2b P-rate", "S2b P-cum")}
#: Part 11.3.5's arm choice when both pitching arms qualify (owner question
#: PB-Q1, default "a"): S2 unless S2b's rate contrast over S2 has lo95 above 0.
PITCHING_ARM_RULE = "a"
#: The rate and cumulative cell of every other part (the pitching entry is S2's).
RATE_CUM = {PART_POSITION: ("H-rate", "H-cum"), PART_PITCHING: ("P-rate", "P-cum"),
            PART_FIELDING: ("H-rate", "H-cum")}

#: B1 is a clause of WIN (components) for the shrunk-skill parts only; the
#: ladder is no shrink (part 9.5).
B1_PARTS = (PART_BATTING, PART_PITCHING, PART_FIELDING)
#: Era transport is a clause of WIN (components) for the pitching part only.
TRANSPORT_PARTS = (PART_PITCHING,)

# --------------------------------------------------------------------------
# dispositions (part 9.5, orchestrator ruling X1), pure
# --------------------------------------------------------------------------

WIN_COMPONENTS = "WIN (components)"
WIN_REGRESSION = "WIN (regression only)"
SMALL_WIN = "SMALL WIN"
LOSS = "LOSS"
EQUIVALENT = "EQUIVALENT"
UNRESOLVED = "UNRESOLVED"
DISPOSITIONS = (WIN_COMPONENTS, WIN_REGRESSION, SMALL_WIN, LOSS, EQUIVALENT, UNRESOLVED)
WINS = (WIN_COMPONENTS, WIN_REGRESSION)


def _gt(v, x) -> bool:
    return v is not None and v > x


def _lt(v, x) -> bool:
    return v is not None and v < x


def disposition(cell: Mapping) -> str:
    """The one disposition of a cell against B0: the first that holds in the
    order WIN, SMALL WIN, LOSS, EQUIVALENT, UNRESOLVED.

    `cell` keys (any may be None, which never satisfies a clause):
      part           the candidate part (decides whether B1 and transport apply)
      holm_reject    the part's Holm family rejected this cell's null
      gap            the point gap against B0 (convention v2)
      lo95, hi95     its 95 percent bootstrap interval
      lo90, hi90     its 90 percent bootstrap interval
      b1_lo95        lo95 of the gap against B1 (parts 4, 5 and 6)
      twin_lo95      lo95 of the twin's gap against B0
      transport      the era transport clause held (part 5)
      v1_sign_agrees convention v1's point gap agrees in sign (default True)

    WIN: Holm rejects, lo95 > 0 and the gap at least +0.02; WIN (components)
    when also lo95 > 0 against B1 (not for the position part), the twin's
    lo95 <= 0 and, for the pitching part, transport holds; WIN (regression
    only) otherwise. SMALL WIN: Holm rejects and lo95 > 0 with the gap under
    +0.02. LOSS: hi95 < 0. EQUIVALENT: the 90 percent interval inside -0.02 to
    +0.02. UNRESOLVED: anything else. A positive disposition (WIN, SMALL WIN)
    also needs convention v1 to agree in sign."""
    part = cell.get("part")
    holm = cell.get("holm_reject") is True
    gap, lo95, hi95 = cell.get("gap"), cell.get("lo95"), cell.get("hi95")
    lo90, hi90 = cell.get("lo90"), cell.get("hi90")
    v1_ok = cell.get("v1_sign_agrees", True) is True
    if holm and v1_ok and _gt(lo95, 0.0) and gap is not None and gap >= MARGIN:
        b1_ok = True if part not in B1_PARTS else _gt(cell.get("b1_lo95"), 0.0)
        twin = cell.get("twin_lo95")
        twin_ok = twin is not None and twin <= 0.0
        tr_ok = True if part not in TRANSPORT_PARTS else cell.get("transport") is True
        return WIN_COMPONENTS if (b1_ok and twin_ok and tr_ok) else WIN_REGRESSION
    if holm and v1_ok and _gt(lo95, 0.0) and gap is not None and gap < MARGIN:
        return SMALL_WIN
    if _lt(hi95, 0.0):
        return LOSS
    if lo90 is not None and hi90 is not None and lo90 >= -MARGIN and hi90 <= MARGIN:
        return EQUIVALENT
    return UNRESOLVED


def counts_as(disp: str) -> str:
    """What a disposition counts as for admission and copy: SMALL WIN counts
    as EQUIVALENT; every other disposition counts as itself."""
    if disp not in DISPOSITIONS:
        raise ValueError(f"unknown disposition {disp!r}")
    return EQUIVALENT if disp == SMALL_WIN else disp


#: The one comparative sentence part 9.6 licenses, by the rate cell's
#: disposition (the frame and numbers are added by licensed_sentence).
SENTENCES = {
    WIN_COMPONENTS: ("ranked the next season's fWAR better than fWAR itself did, and better "
                     "than a uniformly shrunk fWAR"),
    WIN_REGRESSION: "ranked the next season's fWAR better than fWAR itself did",
    EQUIVALENT: "ranked the next season's fWAR about as well as fWAR itself did",
    LOSS: "ranked the next season's fWAR less well than fWAR itself did",
    UNRESOLVED: None,
}


def licensed_sentence(part: str, disp: str, gap=None, lo95=None, hi95=None, n=None,
                      seasons=PREDICTOR_SEASONS) -> Optional[str]:
    """The one sentence copy may carry for a part's rate cell (part 9.6), with
    its frame and numbers; None for UNRESOLVED."""
    c = counts_as(disp)
    base = SENTENCES[c]
    if base is None:
        return None
    if part == PART_POSITION and c == WIN_COMPONENTS:
        base = SENTENCES[WIN_REGRESSION]
    who = ("pitchers with 50 or more IP" if part == PART_PITCHING
           else "hitters with 200 or more PA")
    nums = ""
    if gap is not None and lo95 is not None and hi95 is not None and n is not None:
        nums = f", Spearman gap {gap:+.3f} (95 percent interval {lo95:+.3f} to {hi95:+.3f}, {n:,} pairs)"
    return f"{base}, on {seasons[0]} to {seasons[-1]} seasons, {who} in both seasons{nums}"


# --------------------------------------------------------------------------
# admission (part 9.6), pure
# --------------------------------------------------------------------------

def _disp_of(cells: Mapping, name: str) -> Optional[str]:
    c = cells.get(name)
    if c is None:
        return None
    return c if isinstance(c, str) else c.get("disposition")


def _gap_of(cells: Mapping, name: str):
    c = cells.get(name)
    return None if (c is None or isinstance(c, str)) else c.get("gap")


def qualifies(rate_disp: Optional[str], cum_disp: Optional[str], q1: str) -> bool:
    """EWV3-Q1 (a): the rate cell WIN (components) and the cumulative cell not
    LOSS. (b): any WIN on the rate cell and the cumulative cell not LOSS."""
    if rate_disp is None or cum_disp is None:
        return False
    if q1 == "a":
        ok = rate_disp == WIN_COMPONENTS
    elif q1 == "b":
        ok = rate_disp in WINS
    else:
        raise ValueError(f"EWV3-Q1 answer {q1!r} is not a or b")
    return ok and cum_disp != LOSS


def admit(part: str, cells: Mapping, answers: Mapping) -> dict:
    """Part 9.6: whether a candidate part enters eWAR v3, under the recorded
    answers. `cells` maps each cell name of the part to its disposition (a
    string, or a dict carrying "disposition" and "gap"); for the batting part
    it may carry "contrast", the xHEM+-over-HEM+ rate contrast {"lo95": ...},
    which the lab computes only when both arms qualify. `answers` carries
    "EWV3-Q1", "EWV3-Q2" and "void" (a VOID run admits nothing).

    Returns {"part", "admitted", "arm", "needs_contrast", "reason"}."""
    out = {"part": part, "admitted": False, "arm": None, "needs_contrast": False, "reason": ""}
    if answers.get("void"):
        out["reason"] = "VOID run: nothing is admitted"
        return out
    q1 = answers.get("EWV3-Q1", ANSWERS["EWV3-Q1"])
    if part == PART_BATTING:
        q2 = answers.get("EWV3-Q2", ANSWERS["EWV3-Q2"])
        quals = {arm: qualifies(_disp_of(cells, r), _disp_of(cells, c), q1)
                 for arm, (r, c) in BATTING_ARMS.items()}
        if not any(quals.values()):
            out["reason"] = "neither batting arm qualifies"
            return out
        if quals["HEM+"] and not quals["xHEM+"]:
            out.update(admitted=True, arm="HEM+", reason="only the HEM+ arm qualifies")
            return out
        if quals["xHEM+"] and not quals["HEM+"]:
            out.update(admitted=True, arm="xHEM+", reason="only the xHEM+ arm qualifies")
            return out
        # both qualify: EWV3-Q2
        if q2 == "c":
            out.update(admitted=True, arm="xHEM+", reason="both qualify; EWV3-Q2 (c): xHEM+")
            return out
        if q2 == "b":
            gh, gx = _gap_of(cells, "HEM+ H-rate"), _gap_of(cells, "xHEM+ H-rate")
            if gh is None or gx is None:
                raise ValueError("EWV3-Q2 (b) needs both arms' rate gaps against B0")
            arm = "xHEM+" if gx > gh else "HEM+"
            out.update(admitted=True, arm=arm,
                       reason="both qualify; EWV3-Q2 (b): the larger point gap against B0")
            return out
        if q2 != "a":
            raise ValueError(f"EWV3-Q2 answer {q2!r} is not a, b or c")
        contrast = cells.get("contrast")
        if not contrast:
            out.update(needs_contrast=True,
                       reason="both qualify; EWV3-Q2 (a) needs the xHEM+-over-HEM+ contrast")
            return out
        lo = contrast.get("lo95")
        arm = "xHEM+" if (lo is not None and lo > 0.0) else "HEM+"
        out.update(admitted=True, arm=arm,
                   reason=f"both qualify; EWV3-Q2 (a): contrast lo95 {lo!r} "
                          f"{'above' if arm == 'xHEM+' else 'not above'} 0")
        return out
    if part == PART_PITCHING:
        return _admit_pitching(cells, q1, out)
    if part not in RATE_CUM:
        raise ValueError(f"unknown candidate part {part!r}")
    r, c = RATE_CUM[part]
    if qualifies(_disp_of(cells, r), _disp_of(cells, c), q1):
        out.update(admitted=True, reason=f"{r} {_disp_of(cells, r)}, {c} {_disp_of(cells, c)}")
    else:
        out["reason"] = f"{r} {_disp_of(cells, r)}, {c} {_disp_of(cells, c)}: not admitted"
    return out


def _admit_pitching(cells: Mapping, q1: str, out: dict) -> dict:
    """Part 11.3.5: S2 and S2b each qualify by S2's rule; one qualifying arm
    enters; both qualifying need the S2b-over-S2 rate contrast ("contrast" in
    `cells`, {"lo95": ...}), and S2b enters only when its lo95 is above 0."""
    quals = {arm: qualifies(_disp_of(cells, r), _disp_of(cells, c), q1)
             for arm, (r, c) in PITCHING_ARMS.items()}
    desc = ", ".join(f"{r} {_disp_of(cells, r)}, {c} {_disp_of(cells, c)}"
                     for r, c in PITCHING_ARMS.values())
    if not any(quals.values()):
        out["reason"] = f"{desc}: not admitted"
        return out
    if quals["S2"] != quals["S2b"]:
        arm = "S2" if quals["S2"] else "S2b"
        out.update(admitted=True, arm=arm, reason=f"only the {arm} arm qualifies ({desc})")
        return out
    if PITCHING_ARM_RULE != "a":
        raise ValueError(f"PB-Q1 rule {PITCHING_ARM_RULE!r} is not registered")
    contrast = cells.get("contrast")
    if not contrast:
        out.update(needs_contrast=True,
                   reason="both pitching arms qualify; part 11.3.5 needs the S2b-over-S2 contrast")
        return out
    lo = contrast.get("lo95")
    arm = "S2b" if (lo is not None and lo > 0.0) else "S2"
    out.update(admitted=True, arm=arm,
               reason=f"both qualify; part 11.3.5: contrast lo95 {lo!r} "
                      f"{'above' if arm == 'S2b' else 'not above'} 0")
    return out


def hr_arm_clause(gap_early, gap_late) -> dict:
    """The HR-arm clause (part 9.5, computed FIRST): the P-rate gap of the
    home-run-shrunk pitching part over the part on fWAR's own home-run term,
    positive in BOTH blocks under v2, keeps the shrunk term; otherwise the
    home-run term reverts to fWAR's in both pitcher cells and in the served
    series, 'consistent with R2e.2's closure'."""
    holds = _gt(gap_early, 0.0) and _gt(gap_late, 0.0)
    return {"gap_2016_2018": gap_early, "gap_2021_2024": gap_late, "holds": holds,
            "variant": swar.HR_SHRUNK if holds else swar.HR_FWAR,
            "note": (None if holds else "consistent with R2e.2's closure; licenses no HR-shrink "
                                        "proposal for eWAR v2, and R2e.2 is not re-run")}


def transport_holds(gap_early, gap_late) -> bool:
    """Era transport: the P-rate point gap against B0 positive in both blocks."""
    return _gt(gap_early, 0.0) and _gt(gap_late, 0.0)


def holm(pvals: Mapping[str, Optional[float]], alpha: float = ALPHA) -> dict:
    """Holm step-down over one family; a None p never rejects and counts in m."""
    m = len(pvals)
    order = sorted(pvals, key=lambda k: (1.0 if pvals[k] is None else pvals[k], k))
    out = {k: False for k in pvals}
    for i, k in enumerate(order):
        p = pvals[k]
        if p is not None and p <= alpha / (m - i):
            out[k] = True
        else:
            break
    return out


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def _rank(a: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    return rankdata(a, method="average")


def _pearson(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if len(x) < 4:
        return None
    sx, sy = float(np.std(x)), float(np.std(y))
    if sx == 0.0 or sy == 0.0:
        return None
    return float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))


def spearman(x, y) -> Optional[float]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 4:
        return None
    return _pearson(_rank(x), _rank(y))


def pearson(x, y) -> Optional[float]:
    return _pearson(np.asarray(x, float), np.asarray(y, float))


def zscore_within(groups, values) -> np.ndarray:
    """Within-outcome-season z (plus_lab_harness.zscore_within, sample sd)."""
    g, v = np.asarray(groups), np.asarray(values, float)
    out = np.zeros(len(v))
    for key in np.unique(g):
        m = g == key
        if m.sum() < 2:
            continue
        sd = float(np.std(v[m], ddof=1))
        out[m] = (v[m] - v[m].mean()) / sd if sd else 0.0
    return out


def cluster_draws(players, strata, boot: int, seed: int) -> list[np.ndarray]:
    """Convention v2 replicate indices: players resampled with replacement
    within strata (each player's first predictor season in the frame), all of
    a player's pairs moving together (plus_lab_harness.cluster_boot_gaps)."""
    players = list(players)
    by_player: dict = {}
    first: dict = {}
    for i, (p, s) in enumerate(zip(players, strata)):
        by_player.setdefault(p, []).append(i)
        first[p] = min(first.get(p, s), s)
    groups: dict = {}
    for p, s in first.items():
        groups.setdefault(s, []).append(p)
    groups = {s: sorted(groups[s], key=str) for s in sorted(groups)}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(boot):
        idx: list = []
        for s, pl in groups.items():
            for j in rng.integers(0, len(pl), len(pl)):
                idx.extend(by_player[pl[j]])
        out.append(np.asarray(idx, dtype=np.int64))
    return out


def iid_draws(n: int, boot: int, seed: int) -> list[np.ndarray]:
    """Convention v1 replicate indices: an iid pair resample."""
    rng = np.random.default_rng(seed)
    return [rng.integers(0, n, n) for _ in range(boot)] if n else []


def rho_draws(series: Mapping[str, np.ndarray], target: np.ndarray,
              draws: list[np.ndarray]) -> dict[str, np.ndarray]:
    """Spearman of every series against the target on each replicate (NaN where
    undefined), one ranking of the target per replicate."""
    out = {k: np.full(len(draws), np.nan) for k in series}
    for b, idx in enumerate(draws):
        if len(idx) < 4:
            continue
        rt = _rank(target[idx])
        for k, s in series.items():
            r = _pearson(_rank(s[idx]), rt)
            out[k][b] = np.nan if r is None else r
    return out


def gap_summary(a: np.ndarray, b: np.ndarray) -> dict:
    """The bootstrap summary of rho_a - rho_b on shared replicates."""
    d = a - b
    d = d[~np.isnan(d)]
    if len(d) < 10:
        return {"n_draws": int(len(d)), "sd": None, "lo95": None, "hi95": None,
                "lo90": None, "hi90": None, "p_one_sided": None, "mde95": None,
                "half_width95": None}
    s = np.sort(d)
    n = len(s)
    q = lambda f: float(s[min(n - 1, max(0, int(f * n)))])  # noqa: E731
    lo95, hi95 = q(0.025), float(s[max(0, int(0.975 * n) - 1)])
    sd = float(np.std(d, ddof=1))
    return {"n_draws": n, "sd": sd, "lo95": lo95, "hi95": hi95,
            "lo90": q(0.05), "hi90": float(s[max(0, int(0.95 * n) - 1)]),
            "p_one_sided": float((1 + int((d <= 0.0).sum())) / (1 + n)),
            "mde95": MDE_Z * sd, "half_width95": (hi95 - lo95) / 2.0}


def _r(v, nd=4):
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, np.integer)):
        return int(v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if f != f else round(f, nd)


def _rd(d: Mapping, nd=4) -> dict:
    return {k: (_r(v, nd) if isinstance(v, (int, float, np.integer, np.floating)) else v)
            for k, v in d.items()}


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------

class LabStop(RuntimeError):
    """A precondition failed before scoring began: nothing is written."""


class LabInputs:
    """Every input the look reads, one method each, so the dry run supplies
    fixtures by subclassing. Nothing here fetches."""

    def preview(self) -> dict:
        if not PREVIEW_PATH.exists():
            raise LabStop(f"the preview is absent: run python tools/build_swar.py ({PREVIEW_PATH})")
        return json.loads(PREVIEW_PATH.read_text(encoding="ascii"))

    def vintage_id(self) -> Optional[str]:
        import fwar_vintage
        if not fwar_vintage.available():
            raise LabStop("the frozen fWAR vintage (data/fwar_vintage.json) is absent")
        return str(fwar_vintage.load().get("vintage_id") or "")

    def bwar(self) -> dict:
        """{(mlbam, season): {"bat": WAR, "pit": WAR}} off war_source's
        last-good bWAR cache (read only, never fetched); {} when absent."""
        import war_source
        out: dict = {}
        for side in ("bat", "pit"):
            df = war_source._load_last_good(side)
            if df is None:
                continue
            g = df.dropna(subset=["WAR"]).groupby(["mlb_ID", "year_ID"])["WAR"].sum()
            for (mid, y), w in g.items():
                try:
                    out.setdefault((int(mid), int(y)), {})[side] = float(w)
                except (TypeError, ValueError):
                    continue
        return out

    def team_shares(self) -> dict:
        """{(side, season, mlbam): {team: share}} from the bWAR stint frames'
        team_ID, by PA (bat) and IPouts (pit); {} when absent."""
        import war_source
        out: dict = {}
        for side, col, key in (("bat", "PA", HIT), ("pit", "IPouts", PIT)):
            df = war_source._load_last_good(side)
            if df is None or col not in df.columns:
                continue
            sub = df[["mlb_ID", "year_ID", "team_ID", col]].dropna()
            for (mid, y), grp in sub.groupby(["mlb_ID", "year_ID"]):
                tot = float(grp[col].sum())
                if tot <= 0:
                    continue
                try:
                    k = (key, int(y), int(mid))
                except (TypeError, ValueError):
                    continue
                shares = out.setdefault(k, {})
                for t, e in zip(grp["team_ID"], grp[col]):
                    shares[str(t)] = shares.get(str(t), 0.0) + float(e) / tot
        return out

    def standings(self, seasons) -> dict:
        import ewar
        return ewar.standings(seasons)

    def pbp_plays(self, season: int):
        """The play table of one season (game_pk, batter_id, pitcher_id,
        event_type), or None when the corpus lacks it."""
        path = PBP_PLAYS_DIR / str(int(season)) / f"plays-{int(season)}.parquet"
        if not path.exists():
            return None
        import pandas as pd
        return pd.read_parquet(path, columns=["game_pk", "batter_id", "pitcher_id", "event_type"])


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def season_rows(payload: dict) -> dict:
    """{season: {"hit": {mlbam: row}, "pit": {mlbam: row}}} off the preview.
    A hitter row: pa, fwar, name, tests {pos, bat, batx, fld}; a pitcher row:
    ip, fwar, name, sigma, nopp, tests {hr_shrunk, hr_fwar}, dwar0, lb_dwar0."""
    out: dict = {}
    for s, blk in (payload.get("seasons") or {}).items():
        hit, pit = {}, {}
        for r in blk.get("hitters") or []:
            parts = r.get("parts") or {}
            hit[int(r["mlbam"])] = {
                "pa": _num(r.get("pa")), "fwar": _num(r.get("fwar")), "name": r.get("name", ""),
                "pitcher_batter": bool(r.get("pitcher_batter")),
                "tests": {p: _num((parts.get(p) or {}).get("test")) for p in swar.HITTER_PARTS}}
        for r in blk.get("pitchers") or []:
            parts = r.get("parts") or {}
            pit[int(r["mlbam"])] = {
                "ip": _num(r.get("ip")), "fwar": _num(r.get("fwar")), "name": r.get("name", ""),
                "sigma": _num(r.get("sigma")), "nopp": bool(r.get("nopp")),
                "tests": {v: _num((parts.get(v) or {}).get("test")) for v in swar.HR_VARIANTS + PB_VARIANTS},
                "dwar0": {v: _num((parts.get(v) or {}).get("dwar0")) for v in swar.HR_VARIANTS},
                "lb_dwar0": {v: _num((parts.get(v) or {}).get("lb_dwar0")) for v in swar.HR_VARIANTS}}
        out[int(s)] = {HIT: hit, PIT: pit}
    return out


def exposure_rows(payload: dict) -> dict:
    """The B1 fit's view of the preview: {season: {side: {mlbam: (n, fWAR)}}},
    published fWAR and exposure ONLY (no part, no delta, no test value)."""
    out: dict = {}
    for s, blk in (payload.get("seasons") or {}).items():
        hit = {int(r["mlbam"]): (_num(r.get("pa")), _num(r.get("fwar"))) for r in blk.get("hitters") or []}
        pit = {int(r["mlbam"]): (_num(r.get("ip")), _num(r.get("fwar"))) for r in blk.get("pitchers") or []}
        out[int(s)] = {HIT: hit, PIT: pit}
    return out


FLOOR = {HIT: MIN_PA, PIT: MIN_IP}
EXPOSURE = {HIT: "pa", PIT: "ip"}


def _at_floor(n, side) -> bool:
    return n is not None and n >= FLOOR[side]


# --------------------------------------------------------------------------
# B1
# --------------------------------------------------------------------------

def fit_b1(exp_rows: Mapping[int, Mapping], side: str, seasons: Iterable[int] = B1_FIT_SEASONS) -> dict:
    """One k per side on (Y, Y+1) pairs at the floors in both seasons:
    pooled Pearson r of fWAR per exposure, clamped, k = hm (1 - r) / r."""
    x0, x1, hm, players = [], [], [], set()
    for y in seasons:
        a, b = (exp_rows.get(int(y)) or {}).get(side) or {}, (exp_rows.get(int(y) + 1) or {}).get(side) or {}
        for mid, (n0, w0) in a.items():
            if mid not in b:
                continue
            n1, w1 = b[mid]
            if not (_at_floor(n0, side) and _at_floor(n1, side)) or w0 is None or w1 is None:
                continue
            x0.append(w0 / n0)
            x1.append(w1 / n1)
            hm.append(2.0 / (1.0 / n0 + 1.0 / n1))
            players.add(mid)
    if len(x0) < 30:
        raise LabStop(f"B1 fit ({side}): {len(x0)} pairs, under 30")
    r_raw = pearson(x0, x1)
    r = min(max(r_raw, R_CLAMP[0]), R_CLAMP[1])
    hmm = float(np.mean(hm))
    return {"n_pairs": len(x0), "n_players": len(players), "r_raw": r_raw, "r": round(r, 4),
            "hm": round(hmm, 1), "k": float(round(hmm * (1.0 - r) / r))}


def shrink_target(rows: Mapping[int, dict], side: str) -> Optional[float]:
    """m_s: the season's exposure-weighted fWAR rate over the side's rows at the floor."""
    num = den = 0.0
    for r in rows.values():
        n, w = r.get(EXPOSURE[side]), r.get("fwar")
        if _at_floor(n, side) and w is not None:
            num += w
            den += n
    return num / den if den > 0 else None


def b1_rate(fwar: float, n: float, m: float, k: float) -> float:
    """(x n + m k) / (n + k), x = fWAR / n: the uniformly shrunk fWAR rate."""
    return (float(fwar) + float(m) * float(k)) / (float(n) + float(k))


# --------------------------------------------------------------------------
# frames and cells
# --------------------------------------------------------------------------

def build_pairs(rows: Mapping[int, dict], side: str, seasons: Iterable[int]) -> list[dict]:
    """(Y, Y+1) pairs at the side's floor in both seasons, 2020 out on both
    sides; each pair carries the Y row (with its tests) and fWAR(Y+1), n(Y+1)."""
    out = []
    for y in seasons:
        y = int(y)
        if y == EXCLUDED_SEASON or y + 1 == EXCLUDED_SEASON:
            continue
        a, b = (rows.get(y) or {}).get(side) or {}, (rows.get(y + 1) or {}).get(side) or {}
        m = shrink_target(a, side)
        for mid in sorted(a):
            if mid not in b:
                continue
            r0, r1 = a[mid], b[mid]
            n0, n1 = r0.get(EXPOSURE[side]), r1.get(EXPOSURE[side])
            if not (_at_floor(n0, side) and _at_floor(n1, side)):
                continue
            if r0.get("fwar") is None or r1.get("fwar") is None:
                continue
            out.append({"mlbam": mid, "y": y, "n0": n0, "n1": n1, "fwar0": r0["fwar"],
                        "fwar1": r1["fwar"], "tests": dict(r0["tests"]), "m": m,
                        "sigma": r0.get("sigma")})
    return out


def _series_frame(pairs: list[dict], series_keys: Iterable[str]) -> list[dict]:
    """The pairs on which every named test value is present."""
    keys = list(series_keys)
    return [p for p in pairs if all(p["tests"].get(k) is not None for k in keys)]


def twin_deltas(pairs: list[dict], key: str, seed: int) -> list[float]:
    """The part's delta (test - fWAR) permuted across players within
    (predictor season, exposure decile); the side is fixed by the frame."""
    rng = np.random.default_rng(seed)
    out = [0.0] * len(pairs)
    by_season: dict = {}
    for i, p in enumerate(pairs):
        by_season.setdefault(p["y"], []).append(i)
    for y in sorted(by_season):
        idx = by_season[y]
        ns = np.array([pairs[i]["n0"] for i in idx], float)
        if len(idx) >= 10:
            edges = np.quantile(ns, np.linspace(0, 1, 11)[1:-1])
            dec = np.searchsorted(edges, ns, side="right")
        else:
            dec = np.zeros(len(idx), dtype=int)
        for d in sorted(set(dec.tolist())):
            members = [idx[j] for j in range(len(idx)) if dec[j] == d]
            deltas = [pairs[i]["tests"][key] - pairs[i]["fwar0"] for i in members]
            perm = rng.permutation(len(members))
            for slot, j in zip(members, perm):
                out[slot] = deltas[j]
    return out


def cell_series(pairs: list[dict], key: str, kind: str, side: str, twin: list[float]) -> dict:
    """Arrays for one cell: test, B0, B1, twin, and the targets (v1 raw, v2 z)."""
    k = B1_K[side]
    n0 = np.array([p["n0"] for p in pairs], float)
    n1 = np.array([p["n1"] for p in pairs], float)
    f0 = np.array([p["fwar0"] for p in pairs], float)
    f1 = np.array([p["fwar1"] for p in pairs], float)
    tv = np.array([p["tests"][key] for p in pairs], float)
    m = np.array([p["m"] if p["m"] is not None else 0.0 for p in pairs], float)
    tw = f0 + np.array(twin, float)
    b1r = (f0 + m * k) / (n0 + k)
    if kind == RATE:
        s = {"test": tv / n0, "b0": f0 / n0, "b1": b1r, "twin": tw / n0}
        raw = f1 / n1
    else:
        s = {"test": tv, "b0": f0, "b1": b1r * n0, "twin": tw}
        raw = f1
    out_season = np.array([p["y"] + 1 for p in pairs])
    return {"series": s, "target_v1": raw, "target_v2": zscore_within(out_season, raw)}


def score_cell(part: str, cell: str, key: str, kind: str, side: str, pairs: list[dict],
               boot: int, seed: int, twin_seed: int) -> dict:
    """Every number one cell needs, with its bootstrap draws kept for the
    floors; the gap itself is read only after the floors print."""
    frame = _series_frame(pairs, [key])
    players = [p["mlbam"] for p in frame]
    rec = {"part": part, "cell": cell, "series": key, "kind": kind, "side": side,
           "n_pairs": len(frame), "n_players": len(set(players))}
    if len(frame) < 4:
        rec["empty"] = True
        return rec
    tw = twin_deltas(frame, key, twin_seed)
    cs = cell_series(frame, key, kind, side, tw)
    s = cs["series"]
    strata = [p["y"] for p in frame]
    d2 = rho_draws(s, cs["target_v2"], cluster_draws(players, strata, boot, seed))
    d1 = rho_draws({"test": s["test"], "b0": s["b0"]}, cs["target_v1"], iid_draws(len(frame), boot, seed))
    rec["_draws"] = {"v2": d2, "v1": d1}
    rec["_cs"] = cs
    rec["floors"] = {k: v for k, v in gap_summary(d2["test"], d2["b0"]).items()
                     if k in ("n_draws", "sd", "half_width95", "mde95")}
    return rec


def finish_cell(rec: dict) -> dict:
    """The gaps, intervals and clauses of a scored cell (after the floors)."""
    if rec.get("empty"):
        rec.update({"gap": None, "lo95": None, "hi95": None, "lo90": None, "hi90": None,
                    "p_one_sided": None, "b1_lo95": None, "twin_lo95": None, "v1_gap": None,
                    "v1_sign_agrees": False, "floors": {"n_draws": 0, "sd": None,
                                                         "half_width95": None, "mde95": None}})
        return rec
    cs, d2, d1 = rec["_cs"], rec["_draws"]["v2"], rec["_draws"]["v1"]
    s, t2, t1 = cs["series"], cs["target_v2"], cs["target_v1"]
    rho = {k: spearman(v, t2) for k, v in s.items()}
    g = gap_summary(d2["test"], d2["b0"])
    gb1 = gap_summary(d2["test"], d2["b1"])
    gtw = gap_summary(d2["twin"], d2["b0"])
    g1 = gap_summary(d1["test"], d1["b0"])
    gap = None if rho["test"] is None or rho["b0"] is None else rho["test"] - rho["b0"]
    v1t, v1b = spearman(s["test"], t1), spearman(s["b0"], t1)
    v1_gap = None if v1t is None or v1b is None else v1t - v1b
    pt, pb = pearson(s["test"], t2), pearson(s["b0"], t2)
    rec.update({
        "rho_test": rho["test"], "rho_b0": rho["b0"], "rho_b1": rho["b1"], "rho_twin": rho["twin"],
        "gap": gap, "lo95": g["lo95"], "hi95": g["hi95"], "lo90": g["lo90"], "hi90": g["hi90"],
        "p_one_sided": g["p_one_sided"],
        "gap_b1": (None if rho["test"] is None or rho["b1"] is None else rho["test"] - rho["b1"]),
        "b1_lo95": gb1["lo95"], "b1_hi95": gb1["hi95"],
        "twin_gap": (None if rho["twin"] is None or rho["b0"] is None else rho["twin"] - rho["b0"]),
        "twin_lo95": gtw["lo95"], "twin_hi95": gtw["hi95"],
        "v1_gap": v1_gap, "v1_lo95": g1["lo95"], "v1_hi95": g1["hi95"],
        "v1_sign_agrees": bool(v1_gap is not None and gap is not None
                               and (v1_gap > 0) == (gap > 0) and v1_gap != 0 and gap != 0),
        "pearson_gap_v2": (None if pt is None or pb is None else pt - pb),
        "equivalent_reachable": bool(g["mde95"] is not None and g["mde95"] <= MARGIN),
    })
    return rec


def _public(rec: dict) -> dict:
    out = {k: v for k, v in rec.items() if not k.startswith("_")}
    out["floors"] = _rd(out.get("floors") or {}, 5)
    return _rd(out, 5)


def point_gap_v2(pairs: list[dict], key_a: str, key_b: Optional[str], kind: str, side: str) -> Optional[float]:
    """The v2 point gap of series a over series b (b None: over B0) on the
    pairs where both are present; no bootstrap."""
    keys = [key_a] + ([key_b] if key_b else [])
    frame = _series_frame(pairs, keys)
    if len(frame) < 4:
        return None
    cs = cell_series(frame, key_a, kind, side, [0.0] * len(frame))
    t2 = cs["target_v2"]
    ra = spearman(cs["series"]["test"], t2)
    if key_b is None:
        rb = spearman(cs["series"]["b0"], t2)
    else:
        rb = spearman(cell_series(frame, key_b, kind, side, [0.0] * len(frame))["series"]["test"], t2)
    return None if ra is None or rb is None else ra - rb


def contrast_cell(pairs: list[dict], boot: int, seed: int, key_a: str = "batx", key_b: str = "bat",
                  side: str = HIT) -> dict:
    """An arm tie-break: rho(arm a test) - rho(arm b test) on the rate cell,
    same pairs, same bootstrap; outside the Holm family. The batting default is
    xHEM+ over HEM+; the pitching one (part 11.3.5) S2b over S2."""
    frame = _series_frame(pairs, [key_b, key_a])
    if len(frame) < 4:
        return {"n_pairs": len(frame), "gap": None, "lo95": None, "hi95": None}
    a = cell_series(frame, key_a, RATE, side, [0.0] * len(frame))
    b = cell_series(frame, key_b, RATE, side, [0.0] * len(frame))
    t2 = a["target_v2"]
    players = [p["mlbam"] for p in frame]
    d = rho_draws({"x": a["series"]["test"], "h": b["series"]["test"]}, t2,
                  cluster_draws(players, [p["y"] for p in frame], boot, seed))
    g = gap_summary(d["x"], d["h"])
    rx, rh = spearman(a["series"]["test"], t2), spearman(b["series"]["test"], t2)
    return {"n_pairs": len(frame), "gap": None if rx is None or rh is None else rx - rh,
            "lo95": g["lo95"], "hi95": g["hi95"], "sd": g["sd"]}


# --------------------------------------------------------------------------
# descriptive legs (no verdict weight)
# --------------------------------------------------------------------------

DESCRIPTIVE = "descriptive: no verdict weight; claims nothing (part 8)"


def leg_delta_sizes(rows: dict, seasons: Iterable[int], variant: str) -> dict:
    out: dict = {}
    for part, side, key in ([(p, HIT, p) for p in swar.HITTER_PARTS] + [("pit", PIT, variant),
                                                                          ("pit_s2b", PIT, pb_key(variant))]):
        per = {}
        for y in seasons:
            rs = (rows.get(int(y)) or {}).get(side) or {}
            ds = [(r["tests"][key] - r["fwar"], mid, r.get("name", "")) for mid, r in rs.items()
                  if r["tests"].get(key) is not None and r.get("fwar") is not None]
            if not ds:
                per[str(y)] = None
                continue
            v = np.array([d[0] for d in ds], float)
            top = sorted(ds, key=lambda d: -abs(d[0]))[:5]
            per[str(y)] = {"n": len(v), "sd": _r(np.std(v, ddof=1) if len(v) > 1 else 0.0),
                           "max_abs": _r(np.max(np.abs(v))),
                           "share_ge_0_1": _r(np.mean(np.abs(v) >= 0.1)),
                           "share_ge_0_5": _r(np.mean(np.abs(v) >= 0.5)),
                           "share_ge_1_0": _r(np.mean(np.abs(v) >= 1.0)),
                           "top_movers": [{"mlbam": m, "name": nm, "delta": _r(d, 3)} for d, m, nm in top]}
        out[part] = per
    return out


def leg_agreement(rows: dict, seasons: Iterable[int], variant: str, bwar: Mapping) -> dict:
    out: dict = {}
    for part, side, key, bkey in ([(p, HIT, p, "bat") for p in swar.HITTER_PARTS]
                                  + [("pit", PIT, variant, "pit"), ("pit_s2b", PIT, pb_key(variant), "pit")]):
        tv, fw, tb, bw = [], [], [], []
        for y in seasons:
            for mid, r in ((rows.get(int(y)) or {}).get(side) or {}).items():
                if not _at_floor(r.get(EXPOSURE[side]), side):
                    continue
                if r["tests"].get(key) is None or r.get("fwar") is None:
                    continue
                tv.append(r["tests"][key])
                fw.append(r["fwar"])
                b = (bwar.get((mid, int(y))) or {}).get(bkey)
                if b is not None:
                    tb.append(r["tests"][key])
                    bw.append(b)
        out[part] = {"n": len(tv), "spearman_with_fwar": _r(spearman(tv, fw)),
                     "n_bwar": len(tb), "spearman_with_bwar": _r(spearman(tb, bw)) if tb else None}
    return out


def leg_team_wins(rows: dict, seasons: Iterable[int], variant: str, shares: Mapping,
                  standings: Mapping) -> dict:
    """Team-season sums of each test value (the other side at fWAR) against
    same-season wins and, on full-schedule pairs only, next-season wins.
    Computed only inside the look run; printed only to its output and record."""
    series_names = ["fwar"] + list(swar.HITTER_PARTS) + ["pit"]
    sums: dict = {}
    unallocated = 0
    for y in seasons:
        y = int(y)
        for side in (HIT, PIT):
            for mid, r in ((rows.get(y) or {}).get(side) or {}).items():
                if r.get("fwar") is None:
                    continue
                sh = shares.get((side, y, mid))
                if not sh:
                    unallocated += 1
                    continue
                for t, w in sh.items():
                    tot = sums.setdefault((y, t), {s: 0.0 for s in series_names})
                    for s in series_names:
                        if s == "fwar":
                            v = r["fwar"]
                        elif side == HIT and s in swar.HITTER_PARTS:
                            v = r["tests"].get(s)
                        elif side == PIT and s == "pit":
                            v = r["tests"].get(variant)
                        else:
                            v = r["fwar"]
                        tot[s] += w * (r["fwar"] if v is None else v)
    out = {"unallocated_rows": unallocated}
    for label, shift in (("same_season_wins", 0), ("next_season_wins", 1)):
        xs = {s: [] for s in series_names}
        ws = []
        for (y, t), tot in sorted(sums.items()):
            yy = y + shift
            if shift and (y == EXCLUDED_SEASON or yy == EXCLUDED_SEASON):
                continue
            rec = (standings.get(yy) or {}).get(t)
            if not rec:
                continue
            ws.append(float(rec["w"]))
            for s in series_names:
                xs[s].append(tot[s])
        rs = {s: _r(pearson(xs[s], ws)) for s in series_names}
        out[label] = {"n_team_seasons": len(ws), "pearson_r": rs,
                      "r_minus_fwar": {s: (_r(rs[s] - rs["fwar"]) if rs[s] is not None
                                           and rs["fwar"] is not None else None)
                                       for s in series_names if s != "fwar"}}
    return out


def leg_self_persistence(pairs_h: list[dict], pairs_p: list[dict], rows: dict, variant: str) -> dict:
    """Spearman of each test value per exposure in Y against the same in Y+1
    (reported, never a win: shrinkage raises it mechanically), beside fWAR's."""
    out = {}
    for part, side, key, pairs in ([(p, HIT, p, pairs_h) for p in swar.HITTER_PARTS]
                                   + [("pit", PIT, variant, pairs_p)]):
        a, b, fa, fb = [], [], [], []
        for p in pairs:
            nxt = ((rows.get(p["y"] + 1) or {}).get(side) or {}).get(p["mlbam"])
            if nxt is None:
                continue
            fa.append(p["fwar0"] / p["n0"])
            fb.append(p["fwar1"] / p["n1"])
            t0, t1 = p["tests"].get(key), nxt["tests"].get(key)
            if t0 is not None and t1 is not None:
                a.append(t0 / p["n0"])
                b.append(t1 / p["n1"])
        out[part] = {"n": len(a), "test": _r(spearman(a, b)), "fwar": _r(spearman(fa, fb))}
    return out


BANDS = {HIT: ((0.0, 100.0), (100.0, 200.0), (200.0, 400.0), (400.0, math.inf)),
         PIT: ((0.0, 20.0), (20.0, 40.0), (40.0, 100.0), (100.0, math.inf))}


def leg_exposure_bias(rows: dict, seasons: Iterable[int], variant: str) -> dict:
    out = {}
    for part, side, key in ([(p, HIT, p) for p in swar.HITTER_PARTS] + [("pit", PIT, variant),
                                                                          ("pit_s2b", PIT, pb_key(variant))]):
        per = {}
        for lo, hi in BANDS[side]:
            v = []
            for y in seasons:
                for r in ((rows.get(int(y)) or {}).get(side) or {}).values():
                    n = r.get(EXPOSURE[side])
                    if n is None or n <= 0 or not (lo <= n < hi):
                        continue
                    if r["tests"].get(key) is None or r.get("fwar") is None:
                        continue
                    v.append(r["tests"][key] - r["fwar"])
            per[f"{lo:g}-{hi:g}"] = {"n": len(v), "mean_test_minus_fwar": _r(np.mean(v), 5) if v else None}
        out[part] = per
    return out


def leg_pitching_subsets(pairs_p: list[dict], variant: str) -> dict:
    out = {}
    for label, keep in (("starter_heavy_sigma_ge_0_5", lambda s: s is not None and s >= 0.5),
                        ("reliever_sigma_le_0_10", lambda s: s is not None and s <= 0.10)):
        sub = [p for p in pairs_p if keep(p.get("sigma"))]
        out[label] = {"n_pairs": len(sub), "p_rate_gap_v2": _r(point_gap_v2(sub, variant, None, RATE, PIT)),
                      "s2b_p_rate_gap_v2": _r(point_gap_v2(sub, pb_key(variant), None, RATE, PIT))}
    return out


def leg_leverage_lb(rows: dict, seasons: Iterable[int], variant: str) -> dict:
    """L-B (gmLI 1 in both arms) beside L-A, before the re-pin: a disclosure."""
    out = {}
    for y in seasons:
        la, lb = [], []
        for r in ((rows.get(int(y)) or {}).get(PIT) or {}).values():
            a, b = r["dwar0"].get(variant), r["lb_dwar0"].get(variant)
            if a is None or b is None or r.get("nopp"):
                continue
            la.append(a)
            lb.append(b)
        if len(la) < 2:
            out[str(y)] = None
            continue
        la_, lb_ = np.array(la), np.array(lb)
        out[str(y)] = {"n": len(la), "sd_la": _r(np.std(la_, ddof=1)), "sd_lb": _r(np.std(lb_, ddof=1)),
                       "pearson": _r(pearson(la_, lb_)), "mean_abs_diff": _r(np.mean(np.abs(la_ - lb_)))}
    return out


BAT_EVENT_TYPES = {"ubb": ("walk",), "hbp": ("hit_by_pitch",), "1b": ("single",),
                   "2b": ("double",), "3b": ("triple",), "hr": ("home_run",)}
NOT_IN_WOBA_DENOM = ("intent_walk", "sac_bunt", "sac_bunt_double_play", "catcher_interf")
PIT_EVENT_TYPES = {"k": ("strikeout", "strikeout_double_play"), "bb": ("walk", "intent_walk"),
                   "hbp": ("hit_by_pitch",), "hr": ("home_run",)}
SPLIT_BANDS = {"bat": ((100.0, 300.0), (300.0, 500.0), (500.0, math.inf)),
               "pit": ((100.0, 300.0), (300.0, 600.0), (600.0, math.inf))}


def _split_half_counts(plays, who: str, events: Mapping, denom_excl: tuple):
    """{player: {"n": [h0, h1], e: [h0, h1]}}: alternate games (game_pk order)."""
    df = plays.dropna(subset=["event_type"])
    pid_col = "batter_id" if who == "bat" else "pitcher_id"
    out: dict = {}
    for pid, grp in df.groupby(pid_col):
        games = sorted(grp["game_pk"].unique().tolist())
        half = {g: i % 2 for i, g in enumerate(games)}
        rec = {"n": [0.0, 0.0]}
        for e in events:
            rec[e] = [0.0, 0.0]
        for g, et in zip(grp["game_pk"].tolist(), grp["event_type"].tolist()):
            h = half[g]
            if et not in denom_excl:
                rec["n"][h] += 1.0
            for e, kinds in events.items():
                if et in kinds:
                    rec[e][h] += 1.0
        out[int(pid)] = rec
    return out


def leg_split_half(inputs: LabInputs, seasons: Iterable[int]) -> dict:
    """Split-half reliability of each raw component rate by exposure band,
    Spearman-Brown corrected, against the reliability each constant implies,
    n / (n + K) at the band's mean full-season exposure. Changes no constant."""
    acc = {"bat": {}, "pit": {}}
    used = []
    for y in seasons:
        plays = inputs.pbp_plays(int(y))
        if plays is None:
            continue
        used.append(int(y))
        for who, events, excl in (("bat", BAT_EVENT_TYPES, NOT_IN_WOBA_DENOM), ("pit", PIT_EVENT_TYPES, ())):
            for pid, rec in _split_half_counts(plays, who, events, excl).items():
                acc[who][(int(y), pid)] = rec
    out = {"seasons": used, "components": {}}
    for who, ks in (("bat", swar.BAT_K), ("pit", swar.PIT_K)):
        comp = {}
        for e, k in ks.items():
            bands = {}
            for lo, hi in SPLIT_BANDS[who]:
                h0, h1, nfull = [], [], []
                for rec in acc[who].values():
                    n = rec["n"][0] + rec["n"][1]
                    if not (lo <= n < hi) or rec["n"][0] <= 0 or rec["n"][1] <= 0:
                        continue
                    h0.append(rec[e][0] / rec["n"][0])
                    h1.append(rec[e][1] / rec["n"][1])
                    nfull.append(n)
                r = pearson(h0, h1) if len(h0) >= 30 else None
                sb = None if r is None or r <= -1 else 2.0 * r / (1.0 + r)
                mn = float(np.mean(nfull)) if nfull else None
                bands[f"{lo:g}-{hi:g}"] = {"n_players": len(h0), "split_half_r": _r(r),
                                           "spearman_brown": _r(sb), "mean_n": _r(mn, 1),
                                           "implied_n_over_n_plus_k": _r(mn / (mn + float(k))) if mn else None}
            comp[e] = {"K": float(k), "bands": bands}
        out["components"][who] = comp
    return out


def leg_census(payload: dict) -> dict:
    return {"per_season": {s: b.get("census") for s, b in (payload.get("seasons") or {}).items()},
            "total": payload.get("census_total")}


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def _p(log, *a):
    log(" ".join(str(x) for x in a))


def _fmt(v, nd=4):
    return "null" if v is None else f"{v:+.{nd}f}"


def check_preview(payload: dict, need: Iterable[int], vintage_id: Optional[str]) -> None:
    if payload.get("schema") != swar.SWAR_VERSION:
        raise LabStop(f"preview schema {payload.get('schema')!r} is not {swar.SWAR_VERSION!r}")
    if vintage_id is not None and payload.get("fwar_vintage_id") != vintage_id:
        raise LabStop(f"preview vintage {payload.get('fwar_vintage_id')!r} is not the frozen "
                      f"vintage {vintage_id!r}: rebuild the preview")
    have = {int(s) for s in (payload.get("seasons") or {})}
    missing = sorted(set(int(s) for s in need) - have)
    if missing:
        raise LabStop(f"the preview lacks seasons {missing}")


def _refuse_out(path: Path) -> None:
    rp = Path(path).resolve()
    try:
        rp.relative_to((ROOT / "data").resolve())
    except ValueError:
        return
    raise LabStop(f"the lab never writes under data/: {path}")


def write_record(record: dict, path: Path) -> Path:
    path = Path(path)
    _refuse_out(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    text = json.dumps(record, indent=1, ensure_ascii=True, allow_nan=False, sort_keys=False) + "\n"
    with open(tmp, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


def score_block(rows: dict, seasons: tuple, boot: int,
                log: Callable, early_pairs_p: Optional[list] = None,
                hr_choice: Optional[dict] = None, label: str = "look") -> dict:
    """The cells of one block (the look's 2021 to 2024, or the holdout's 2025):
    floors first, the HR-arm clause first among decisions, then gaps,
    Holm per part, dispositions and admission."""
    pairs_h = build_pairs(rows, HIT, seasons)
    pairs_p = build_pairs(rows, PIT, seasons)
    early_p = early_pairs_p if early_pairs_p is not None else build_pairs(rows, PIT, TRANSPORT_EARLY_SEASONS)
    _p(log, f"[{label}] frame: {len(pairs_h)} hitter pairs, {len(pairs_p)} pitcher pairs; "
            f"2016 to 2018 pitcher block {len(early_p)} pairs")

    # -- score every cell (both home-run variants on the pitcher side); draws kept
    recs: dict = {}
    for i, part in enumerate(PARTS):
        spec = PART_CELLS[part]
        for j, (cell, (key, kind)) in enumerate(spec["cells"].items()):
            keys = (list(swar.HR_VARIANTS) if key == PITCH
                    else list(PB_VARIANTS) if key == PITCH_B else [key])
            for v in keys:
                pairs = pairs_p if spec["side"] == PIT else pairs_h
                recs[(part, cell, v)] = score_cell(part, cell, v, kind, spec["side"], pairs,
                                                   boot, SEED, SEED + 101 * (i + 1) + 7 * j)
    # -- floors first: sd, half-width, MDE95, before any gap
    _p(log, f"[{label}] FLOORS (convention v2, B = {boot}; MDE95 = 1.645 sd; no gap is printed here)")
    floors = {}
    for (part, cell, v), rec in recs.items():
        f = rec.get("floors") or {}
        floors[f"{part}|{cell}|{v}"] = _rd(f, 5)
        unreach = f.get("mde95") is not None and f["mde95"] > MARGIN
        _p(log, f"  {part:9s} {cell:13s} {v:9s} n {rec['n_pairs']:5d}  sd {_fmt(f.get('sd'))}  "
                f"half-width {_fmt(f.get('half_width95'))}  MDE95 {_fmt(f.get('mde95'))}"
                + ("  EQUIVALENT unreachable (MDE95 > 0.02)" if unreach else ""))

    # -- the HR-arm clause, FIRST among decisions
    if hr_choice is None:
        g_early = point_gap_v2(early_p, swar.HR_SHRUNK, swar.HR_FWAR, RATE, PIT)
        g_late = point_gap_v2(pairs_p, swar.HR_SHRUNK, swar.HR_FWAR, RATE, PIT)
        hr_choice = hr_arm_clause(g_early, g_late)
        _p(log, f"[{label}] HR-ARM CLAUSE: P-rate gap hr_shrunk over hr_fwar, 2016-2018 "
                f"{_fmt(g_early)}, 2021-2024 {_fmt(g_late)}: "
                f"{'holds' if hr_choice['holds'] else 'fails'}; home-run term {hr_choice['variant']}")
    else:
        _p(log, f"[{label}] home-run term carried from the look: {hr_choice['variant']}")
    variant = hr_choice["variant"]

    def _series(key: str) -> str:
        return variant if key == PITCH else pb_key(variant) if key == PITCH_B else key

    # -- gaps and clauses
    cells: dict = {}
    for part in PARTS:
        spec = PART_CELLS[part]
        fam = {}
        for cell, (key, kind) in spec["cells"].items():
            rec = finish_cell(recs[(part, cell, _series(key))])
            if part == PART_PITCHING and kind == RATE:
                ge = point_gap_v2(early_p, _series(key), None, RATE, PIT)
                rec["transport_gap_2016_2018"] = ge
                rec["transport"] = transport_holds(ge, rec.get("gap"))
            fam[cell] = rec
        if part == PART_PITCHING:
            for r_cell, c_cell in PITCHING_ARMS.values():
                fam[c_cell]["transport"] = fam[r_cell].get("transport")
        hr = holm({c: r.get("p_one_sided") for c, r in fam.items()})
        for c, r in fam.items():
            r["holm_family"] = list(fam)
            r["holm_reject"] = hr[c]
            r["disposition"] = disposition(r)
            r["counts_as"] = counts_as(r["disposition"])
            r["ship_flag_no_weight"] = (None if r["disposition"] not in WINS
                                        else bool(r.get("gap") is not None and (r["floors"].get("sd") or 0) > 0
                                                  and r["gap"] - MDE_Z * r["floors"]["sd"] > MARGIN))
        cells[part] = fam
    # exactly one disposition per cell, every cell
    for part, fam in cells.items():
        for c, r in fam.items():
            hits = [d for d in DISPOSITIONS if d == r["disposition"]]
            if len(hits) != 1:
                raise RuntimeError(f"{part} {c}: {len(hits)} dispositions")

    _p(log, f"[{label}] GAPS AND DISPOSITIONS (convention v2 against B0; v1 must agree in sign)")
    for part, fam in cells.items():
        for c, r in fam.items():
            _p(log, f"  {part:9s} {c:13s} n {r['n_pairs']:5d} gap {_fmt(r.get('gap'))} "
                    f"[{_fmt(r.get('lo95'))}, {_fmt(r.get('hi95'))}] 90% [{_fmt(r.get('lo90'))}, "
                    f"{_fmt(r.get('hi90'))}] MDE95 {_fmt(r['floors'].get('mde95'))} p {_fmt(r.get('p_one_sided'))} "
                    f"holm {r['holm_reject']} "
                    f"| vs B1 lo95 {_fmt(r.get('b1_lo95'))} | twin lo95 {_fmt(r.get('twin_lo95'))} "
                    f"| v1 {_fmt(r.get('v1_gap'))} | pearson {_fmt(r.get('pearson_gap_v2'))} "
                    f"=> {r['disposition']}"
                    + (f" (SHIP flag, no weight: {r['ship_flag_no_weight']})" if r["disposition"] in WINS else ""))

    return {"pairs_h": pairs_h, "pairs_p": pairs_p, "early_p": early_p, "hr": hr_choice,
            "variant": variant, "cells": cells, "floors": floors}


def _sentence(part: str, fam: dict, adm: dict, mode: str) -> Optional[str]:
    """The licensed sentence of the part's rate cell (the admitted batting arm,
    else the HEM+ arm)."""
    if part == PART_PITCHING:
        rate = PITCHING_ARMS[adm.get("arm") or "S2"][0]
    else:
        rate = RATE_CUM[part][0] if part in RATE_CUM else BATTING_ARMS[adm.get("arm") or "HEM+"][0]
    r = fam[rate]
    return licensed_sentence(part, r["disposition"], r.get("gap"), r.get("lo95"), r.get("hi95"),
                             r.get("n_pairs"), PREDICTOR_SEASONS if mode == "look" else HOLDOUT_SEASONS)


def admissions(cells: dict, pairs_h: list, boot: int, answers: Mapping, log: Callable,
               pairs_p: Optional[list] = None, variant: str = swar.HR_SHRUNK) -> tuple[dict, Optional[dict]]:
    out, contrast, pitching_contrast = {}, None, None
    pairs_p = pairs_p or []
    for part in PARTS:
        fam = cells[part]
        a = admit(part, fam, answers)
        if a["needs_contrast"] and part == PART_PITCHING:
            pc = contrast_cell(pairs_p, boot, SEED + 9002, pb_key(variant), variant, PIT)
            _p(log, f"  pitching contrast (S2b over S2, rate, outside Holm): gap "
                    f"{_fmt(pc['gap'])} lo95 {_fmt(pc['lo95'])}")
            a = admit(part, dict(fam, contrast=pc), answers)
            pitching_contrast = pc
        elif a["needs_contrast"]:
            contrast = contrast_cell(pairs_h, boot, SEED + 9001)
            _p(log, f"  batting contrast (xHEM+ over HEM+, rate, outside Holm): gap "
                    f"{_fmt(contrast['gap'])} lo95 {_fmt(contrast['lo95'])}")
            a = admit(part, dict(fam, contrast=contrast), answers)
        out[part] = a
        _p(log, f"  ADMIT {part:9s}: {a['admitted']}" + (f" arm {a['arm']}" if a["arm"] else "")
                + f" ({a['reason']})")
    if pitching_contrast is not None:
        out[PART_PITCHING]["contrast"] = _rd(pitching_contrast, 5)
    return out, contrast


def run(mode: str, inputs: LabInputs, out_path: Path, boot: int = BOOT, log: Callable = print,
        today: Optional[_dt.date] = None, fail_after_scoring: bool = False) -> dict:
    """mode 'look' or 'holdout'. Raises LabStop before scoring began (nothing
    written); after scoring began, any exception writes a VOID record."""
    today = today or _dt.date.today()
    out_path = Path(out_path)
    _refuse_out(out_path)
    existing = None
    if mode == "look":
        if out_path.exists():
            raise LabStop(f"the record exists ({out_path}): a second look is forbidden")
        need = list(range(2016, 2026))
    elif mode == "holdout":
        if not out_path.exists():
            raise LabStop(f"no look record at {out_path}: the holdout runs after the look")
        existing = json.loads(out_path.read_text(encoding="ascii"))
        if existing.get("status") == "VOID":
            raise LabStop("the skill look is VOID: the holdout does not run (part 7.4)")
        if existing.get("holdout") is not None:
            raise LabStop("the holdout block exists: a second holdout is forbidden")
        need = list(range(2016, 2020)) + [HOLDOUT_SEASONS[0], HOLDOUT_SEASONS[0] + 1]
    else:
        raise ValueError(mode)
    payload = inputs.preview()
    check_preview(payload, need, inputs.vintage_id())
    rows = season_rows(payload)
    _p(log, f"swar_lab {LAB_VERSION} {mode} on {today.isoformat()}: preview vintage "
            f"{payload.get('fwar_vintage_id')}, generated {payload.get('generated_at')}; "
            f"B1 k hit {B1_K['hit']:g} PA, pit {B1_K['pit']:g} IP; seed {SEED}, B {boot}")
    started = {"scoring": False}
    try:
        started["scoring"] = True
        if mode == "look":
            blk = score_block(rows, PREDICTOR_SEASONS, boot, log, label="look")
        else:
            blk = score_block(rows, HOLDOUT_SEASONS, boot, log, label="holdout",
                              hr_choice=existing["hr_arm_clause"])
        if fail_after_scoring:
            raise RuntimeError("injected failure after scoring began (dry run)")
        _p(log, f"[{mode}] ADMISSION (part 9.6; EWV3-Q1 ({ANSWERS['EWV3-Q1']}), EWV3-Q2 ({ANSWERS['EWV3-Q2']}))"
                + (" reported only: the holdout changes no admission" if mode == "holdout" else ""))
        adm, contrast = admissions(blk["cells"], blk["pairs_h"], boot, dict(ANSWERS, void=False), log,
                                   blk["pairs_p"], blk["variant"])
        block = {
            "seasons": list(PREDICTOR_SEASONS if mode == "look" else HOLDOUT_SEASONS),
            "n_pairs": {"hit": len(blk["pairs_h"]), "pit": len(blk["pairs_p"])},
            "floors_first": blk["floors"],
            "hr_arm_clause": _rd(blk["hr"], 5),
            "cells": {part: {c: _public(r) for c, r in fam.items()} for part, fam in blk["cells"].items()},
            "batting_contrast": _rd(contrast, 5) if contrast else None,
            "admission": adm,
            "sentences": {part: _sentence(part, blk["cells"][part], adm[part], mode) for part in PARTS},
        }
        # -- descriptive legs
        _p(log, f"[{mode}] DESCRIPTIVE LEGS ({DESCRIPTIVE})")
        dseasons = [y for y in (PREDICTOR_SEASONS if mode == "look" else HOLDOUT_SEASONS)]
        desc = {
            "label": DESCRIPTIVE,
            "delta_sizes": leg_delta_sizes(rows, dseasons, blk["variant"]),
            "agreement": leg_agreement(rows, dseasons, blk["variant"], inputs.bwar()),
            "self_persistence": leg_self_persistence(blk["pairs_h"], blk["pairs_p"], rows, blk["variant"]),
            "exposure_band_bias": leg_exposure_bias(rows, dseasons, blk["variant"]),
            "pitching_subsets": leg_pitching_subsets(blk["pairs_p"], blk["variant"]),
            "leverage_lb_disclosure": leg_leverage_lb(rows, dseasons, blk["variant"]),
            "coverage_census": leg_census(payload),
        }
        if mode == "look":
            desc["team_wins"] = leg_team_wins(rows, dseasons, blk["variant"], inputs.team_shares(),
                                              inputs.standings(range(min(dseasons), max(dseasons) + 2)))
            cal_seasons = [y for y in range(2016, 2026) if y != EXCLUDED_SEASON]
            desc["split_half_calibration"] = leg_split_half(inputs, cal_seasons)
        block["descriptive"] = desc
        for k in ("agreement", "self_persistence", "pitching_subsets"):
            _p(log, f"  {k}: {json.dumps(desc[k], sort_keys=True)}")
        if "team_wins" in desc:
            _p(log, f"  team_wins: {json.dumps(desc['team_wins'], sort_keys=True)}")
    except Exception:
        if not started["scoring"]:
            raise
        tb = traceback.format_exc()
        _p(log, "VOID: an exception after scoring began; no rerun; an owner question follows")
        _p(log, tb)
        void = {"schema": LAB_VERSION, "status": "VOID", "mode": mode, "date": today.isoformat(),
                "registration": REGISTRATION, "admission": {p: admit(p, {}, {"void": True}) for p in PARTS},
                "traceback": tb}
        if mode == "look":
            write_record(void, out_path)
        else:
            existing["holdout"] = void
            write_record(existing, out_path)
        raise
    meta = {"schema": LAB_VERSION, "registration": REGISTRATION, "date": today.isoformat(),
            "preview_generated_at": payload.get("generated_at"),
            "fwar_vintage_id": payload.get("fwar_vintage_id"),
            "params": {"seed": SEED, "boot": boot, "margin": MARGIN, "alpha": ALPHA, "mde_z": MDE_Z,
                       "floors": {"hit_pa": MIN_PA, "pit_ip": MIN_IP},
                       "predictor_seasons": list(PREDICTOR_SEASONS),
                       "transport_early_seasons": list(TRANSPORT_EARLY_SEASONS),
                       "holdout_seasons": list(HOLDOUT_SEASONS),
                       "b1_k": dict(B1_K), "b1_fit": B1_FIT_LOG, "answers": dict(ANSWERS),
                       "primary_convention": "v2", "intervals": "bootstrap percentile",
                       "p_one_sided": "(1 + #{gap draws <= 0}) / (1 + draws)"}}
    if mode == "look":
        record = dict(meta, status="SCORED", mode="look", hr_arm_clause=block["hr_arm_clause"],
                      look=block, holdout=None)
    else:
        record = existing
        record["holdout"] = dict(meta, status="SCORED", mode="holdout", block=block,
                                 note="reported beside the verdict, never merged into it; changes no admission")
    write_record(record, out_path)
    _p(log, f"wrote {out_path}")
    return record


# --------------------------------------------------------------------------
# the dry run: synthetic fixtures with nulls, a temporary directory only
# --------------------------------------------------------------------------

class FixtureLabInputs(LabInputs):
    """A synthetic league, 2016 to 2026: random fWAR around a fixed talent,
    batting and pitching deltas that pull toward that talent, position and
    fielding deltas of pure noise, and nulls on purpose (a missing test value, a
    missing fWAR, an xHEM+ arm absent in the holdout season, a season of the
    play-by-play corpus absent)."""

    def __init__(self, seed: int = 7, n_hit: int = 260, n_pit: int = 180):
        self.rng = np.random.default_rng(seed)
        self.n_hit, self.n_pit = n_hit, n_pit
        self._payload = self._build()

    def _build(self) -> dict:
        rng = self.rng
        seasons = {}
        th = rng.normal(0.004, 0.006, self.n_hit)
        tp = rng.normal(0.010, 0.012, self.n_pit)
        for y in range(2016, 2027):
            hit, pit = [], []
            for i in range(self.n_hit):
                pa = float(rng.integers(60, 700))
                fw = float(th[i] * pa + rng.normal(0, 0.8))
                parts = {}
                for p in swar.HITTER_PARTS:
                    # the batting arms carry true talent (so the WIN path, the
                    # admission rule and the batting contrast all run); the
                    # other parts are pure noise
                    pull = {"bat": 0.5, "batx": 0.7}.get(p, 0.0)
                    d = pull * (float(th[i]) * pa - fw) + float(rng.normal(0, 0.05 if pull else 0.3))
                    test = fw + d
                    if (p == "batx" and y == 2025 and i % 2 == 0) or (i == 3 and p == "fld"):
                        test = None
                    parts[p] = {"g": None, "d": None, "test": test}
                hit.append({"mlbam": 1000 + i, "name": f"H{i}", "pa": pa,
                            "fwar": (None if (i == 5 and y == 2022) else fw),
                            "pitcher_batter": i == 7, "parts": parts})
            for i in range(self.n_pit):
                ip = float(rng.integers(10, 210))
                fw = float(tp[i] * ip + rng.normal(0, 0.5))
                sigma = float(min(1.0, max(0.0, rng.normal(0.5, 0.4))))
                parts = {}
                for v in swar.HR_VARIANTS:
                    pull = 0.6 if v == swar.HR_SHRUNK else 0.2
                    dl = pull * (float(tp[i]) * ip - fw) + float(rng.normal(0, 0.05))
                    parts[v] = {"dfip": None, "dwar0": dl, "delta": dl,
                                "test": (None if (i == 2 and v == swar.HR_SHRUNK) else fw + dl),
                                "lb_dwar0": dl * float(rng.uniform(0.6, 1.2))}
                    # the blended arm S2b: a slightly stronger pull, and a null on purpose
                    db = (pull + 0.1) * (float(tp[i]) * ip - fw) + float(rng.normal(0, 0.05))
                    parts[pb_key(v)] = {"dwar0": db, "delta": db,
                                        "test": (None if (i == 4 and y == 2022) else fw + db)}
                pit.append({"mlbam": 5000 + i, "name": f"P{i}", "ip": ip, "fwar": fw,
                            "sigma": sigma, "nopp": i == 9, "gmli": None, "parts": parts})
            seasons[str(y)] = {"hitters": hit, "pitchers": pit,
                               "census": {"rows_hitters": len(hit), "rows_pitchers": len(pit)}}
        return {"schema": swar.SWAR_VERSION, "fwar_vintage_id": "fixture", "generated_at": "fixture",
                "seasons": seasons, "census_total": {"rows_hitters": 0, "rows_pitchers": 0}}

    def preview(self):
        return json.loads(json.dumps(self._payload))

    def vintage_id(self):
        return "fixture"

    def bwar(self):
        out = {}
        for s, blk in self._payload["seasons"].items():
            for r in blk["hitters"][::2]:
                if r["fwar"] is not None:
                    out.setdefault((r["mlbam"], int(s)), {})["bat"] = r["fwar"] * 0.9
            for r in blk["pitchers"][::3]:
                out.setdefault((r["mlbam"], int(s)), {})["pit"] = r["fwar"] * 1.1
        return out

    def team_shares(self):
        out = {}
        teams = [f"T{j:02d}" for j in range(30)]
        for s, blk in self._payload["seasons"].items():
            for k, r in enumerate(blk["hitters"]):
                if k % 11 == 0:
                    continue
                out[(HIT, int(s), r["mlbam"])] = {teams[k % 30]: 1.0}
            for k, r in enumerate(blk["pitchers"]):
                out[(PIT, int(s), r["mlbam"])] = {teams[k % 30]: 0.6, teams[(k + 1) % 30]: 0.4}
        return out

    def standings(self, seasons):
        return {int(y): {f"T{j:02d}": {"w": int(60 + (j * 7 + y) % 40), "l": 162 - int(60 + (j * 7 + y) % 40)}
                         for j in range(30)} for y in seasons if int(y) != 2023}

    def pbp_plays(self, season):
        if int(season) == 2019:
            return None
        import pandas as pd
        rng = np.random.default_rng(int(season))
        kinds = ["field_out", "single", "double", "triple", "home_run", "walk", "intent_walk",
                 "hit_by_pitch", "strikeout", "sac_bunt", None]
        probs = np.array([0.45, 0.14, 0.045, 0.004, 0.03, 0.08, 0.005, 0.01, 0.22, 0.004, 0.002])
        n = 24000
        return pd.DataFrame({
            "game_pk": rng.integers(1, 500, n),
            "batter_id": rng.integers(1000, 1060, n),
            "pitcher_id": rng.integers(5000, 5040, n),
            "event_type": rng.choice(np.array(kinds, dtype=object), n, p=probs / probs.sum()),
        })


def preflight_real_inputs(log: Callable = print) -> dict:
    """Structure only, no value: whether each real input the look reads is
    present and shaped as the lab expects. Computes no statistic."""
    out = {}
    try:
        if PREVIEW_PATH.exists():
            p = json.loads(PREVIEW_PATH.read_text(encoding="ascii"))
            seasons = sorted(int(s) for s in p.get("seasons") or {})
            blk = (p.get("seasons") or {}).get(str(seasons[-1])) if seasons else {}
            h = (blk.get("hitters") or [{}])[0]
            q = (blk.get("pitchers") or [{}])[0]
            out["preview"] = {
                "schema_ok": p.get("schema") == swar.SWAR_VERSION, "seasons": seasons,
                "hitter_keys_ok": all(k in h for k in ("mlbam", "pa", "fwar", "parts"))
                and all(k in (h.get("parts") or {}) for k in swar.HITTER_PARTS),
                "pitcher_keys_ok": all(k in q for k in ("mlbam", "ip", "fwar", "sigma", "nopp", "parts"))
                and all(k in (q.get("parts") or {}) for k in swar.HR_VARIANTS + PB_VARIANTS)}
            try:
                import fwar_vintage
                out["preview"]["vintage_matches"] = (
                    fwar_vintage.available() and p.get("fwar_vintage_id") == fwar_vintage.load().get("vintage_id"))
            except Exception as exc:  # noqa: BLE001  (a structural check reports, never raises)
                out["preview"]["vintage_matches"] = f"unreadable: {exc}"
        else:
            out["preview"] = "absent"
        import war_source
        for side in ("bat", "pit"):
            df = war_source._load_last_good(side)
            need = ("mlb_ID", "year_ID", "team_ID", "WAR", "PA" if side == "bat" else "IPouts")
            out[f"bwar_cache_{side}"] = (None if df is None else all(c in df.columns for c in need))
        import ewar
        out["standings_seasons"] = sorted(ewar.standings(range(2016, 2027)))
        out["pbp_seasons"] = sorted(int(d.name) for d in PBP_PLAYS_DIR.iterdir()
                                    if d.is_dir() and d.name.isdigit()) if PBP_PLAYS_DIR.exists() else []
        import pyarrow.parquet as pq
        cols_ok = {}
        for y in out["pbp_seasons"]:
            f = PBP_PLAYS_DIR / str(y) / f"plays-{y}.parquet"
            cols_ok[y] = f.exists() and all(c in pq.read_schema(f).names for c in
                                            ("game_pk", "batter_id", "pitcher_id", "event_type"))
        out["pbp_columns_ok"] = cols_ok
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    _p(log, f"preflight (structure only, no value computed): {json.dumps(out, sort_keys=True)}")
    return out


def dry_run(log: Callable = print, boot: int = BOOT, tmp_dir: Optional[Path] = None) -> dict:
    """The whole reporting path on synthetic fixtures with nulls: the look,
    the holdout, a refused second look, a VOID run and the admission rule,
    written only under a temporary directory."""
    tmp = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="swar_lab_dry_"))
    _refuse_out(tmp / "x.json")
    out = tmp / "swar_eval.json"
    _p(log, f"DRY RUN in {tmp} (fixtures with nulls; nothing real is scored)")
    inputs = FixtureLabInputs()
    rec = run("look", inputs, out, boot=boot, log=log, today=_dt.date(2026, 11, 17))
    for part, fam in rec["look"]["cells"].items():
        for c, r in fam.items():
            if r["disposition"] not in DISPOSITIONS:
                raise AssertionError(f"{part} {c}: {r['disposition']!r}")
    try:
        run("look", inputs, out, boot=boot, log=lambda *a: None)
        raise AssertionError("a second look was not refused")
    except LabStop:
        _p(log, "  a second look is refused: ok")
    rec = run("holdout", inputs, out, boot=boot, log=log, today=_dt.date(2026, 11, 18))
    if rec.get("holdout", {}).get("status") != "SCORED":
        raise AssertionError("the holdout block is missing")
    try:
        run("holdout", inputs, out, boot=boot, log=lambda *a: None)
        raise AssertionError("a second holdout was not refused")
    except LabStop:
        _p(log, "  a second holdout is refused: ok")
    void_out = tmp / "swar_eval_void.json"
    try:
        run("look", inputs, void_out, boot=max(50, boot // 10), log=lambda *a: None, fail_after_scoring=True)
        raise AssertionError("the injected failure did not raise")
    except RuntimeError:
        v = json.loads(void_out.read_text(encoding="ascii"))
        if v.get("status") != "VOID" or any(a["admitted"] for a in v["admission"].values()):
            raise AssertionError("the VOID record admits something")
        _p(log, "  a crash after scoring began writes VOID and admits nothing: ok")
    try:
        run("holdout", inputs, void_out, boot=boot, log=lambda *a: None)
        raise AssertionError("a holdout after a VOID look was not refused")
    except LabStop:
        _p(log, "  no holdout after a VOID look: ok")
    try:
        _refuse_out(ROOT / "data" / "swar_eval.json")
        raise AssertionError("a data/ record path was not refused")
    except LabStop:
        _p(log, "  a record under data/ is refused: ok")
    preflight_real_inputs(log)
    _p(log, f"DRY RUN OK: {out}")
    return {"tmp": str(tmp), "record": str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="eWAR v3 skill look lab (EBR_GATE.md part 9.5)")
    ap.add_argument("--dry-run", action="store_true", help="synthetic fixtures with nulls, a temp dir only")
    ap.add_argument("--holdout", action="store_true", help="the holdout run (part 7.4), once")
    ap.add_argument("--out", help=f"the record path (default {DEFAULT_RECORD.relative_to(ROOT)})")
    args = ap.parse_args(argv)
    if args.dry_run:
        try:
            dry_run()
        except Exception:
            traceback.print_exc()
            print("DRY RUN FAILED", file=sys.stderr)
            return 1
        return 0
    out = Path(args.out) if args.out else DEFAULT_RECORD
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    try:
        run("holdout" if args.holdout else "look", LabInputs(), out)
    except LabStop as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("VOID: see the record and the traceback above; no rerun", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
