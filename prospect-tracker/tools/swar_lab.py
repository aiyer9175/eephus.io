# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 skill look's lab (candidate parts 3 to 6, PE-P and PE-H),
registered in docs/ebr-2026-09-30/EBR_GATE.md parts 9.5 and 9.6 as amended by
part 11 (11.2 to 11.7), which this file implements with their parameters
exactly and does not extend.

    python tools/swar_lab.py --dry-run          # synthetic fixtures with nulls, a temp dir only
    python -u tools/swar_lab.py --out docs/ebr-2026-09-30/swar_eval.json   # THE LOOK, once
    python -u tools/swar_lab.py --holdout       # THE HOLDOUT, once, a later day

THE QUESTION, per candidate part, since part 11.2 (owner decision EW3-23):
does the part's own component in season Y (B0, the actual arm of the part's
delta function) plus the part's re-centred delta rank the NEXT season's
REALIZED runs of that component better than B0 does? Pairs (Y, Y+1) for
predictor seasons 2021 to 2024 (2020 out on both sides); hitters 200 PA and
pitchers 50 IP in both seasons. The targets (11.2.1): batting runs (wRAA on
the season's solved weights) for the batting part and PE-H (plus the realized
starter wear W); RA9* (park, the club's defense, inherited and bequeathed
runners) as runs prevented above average for the pitching part (S2, S2b);
RSB, runs saved over a league-average reliever, for PE-P; an independent
fielding source for the fielding part (11.2.2: Baseball-Reference runs_field
for S3; for S3t the system each configuration leaves out, DRS, Statcast and
UZR, the cell's gap the mean of the per-system gaps inside one bootstrap; DRS
for the catcher component S3c on catchers with 300 or more innings at C).
The position part keeps the ladder gate's out-of-sample dMAE against
FanGraphs' positional adjustment (11.2.3). Every part also passes the team
guard (11.2.4): roster-weighted series against the next season's club runs
and wins, NON-INFERIOR under a player-clustered and a club-clustered
bootstrap. Published fWAR(Y+1) is the secondary estimand (11.2.5), scored as
part 9.5 first registered it and deciding nothing. The amended machinery's
readers and pure arithmetic live in tools/swar_targets.py.

THE PART 9.5 TEXT BELOW describes the secondary estimand's cells; the primary
cells keep every one of its rules (Holm per family, the margin, the twin, the
precedence, convention v2 primary with v1 agreeing in sign, B and the seed)
with B0 in place of fWAR(Y), the primary target in place of fWAR(Y+1) and the
amended B1 (one k per component, B1_K_AMENDED).

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
Part 11.2.10's amendment work is implemented here (EWV3_LAB_AMENDED_TARGETS):
the primary targets, B0, B0r, the amended B1, the independent fielding source,
the team guard, the position part's dMAE rule and the secondary block, with
PE-P and PE-H (11.4), S3t (11.5, eligible by owner decision EW3-37, 11.7) and
S3c (11.6). Every input is read and assembled BEFORE scoring begins, so a
missing or malformed input is a STOP, never a VOID.

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
import swar_targets as T  # noqa: E402  (part 11.2's targets, readers and team guard)

LAB_VERSION = "swar_lab/2"   # swar_lab/2: part 11's amended targets (EWV3_LAB_AMENDED_TARGETS)
REGISTRATION = "docs/ebr-2026-09-30/EBR_GATE.md parts 9.5 and 9.6, as amended by part 11 (11.2 to 11.7)"
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
#: The pitch-economy candidate parts (part 11.4), each its own Holm family.
PART_PE_P, PART_PE_H = "pe_p", "pe_h"

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
B1_PARTS = (PART_BATTING, PART_PITCHING, PART_FIELDING, PART_PE_P, PART_PE_H)
#: Era transport is a clause of WIN (components) for the pitching part and PE-P (11.4.4).
TRANSPORT_PARTS = (PART_PITCHING, PART_PE_P)

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

    # -- part 11's inputs, through swar_targets.Readers (caches only)
    def readers(self) -> "T.Readers":
        if getattr(self, "_readers", None) is None:
            self._readers = T.Readers()
        return self._readers

    def fielding_by_player(self) -> dict:
        return self.readers().fielding_by_player()

    def triangulation_runs(self) -> dict:
        return self.readers().triangulation_runs()

    def pe_pitchers(self, season: int) -> dict:
        return self.readers().pitch_economy_pitchers(int(season))

    def pe_hitters(self, season: int) -> Optional[dict]:
        return self.readers().pitch_economy_hitters(int(season))

    def team_exposure(self) -> dict:
        return self.readers().team_exposure()

    def ladder_records(self):
        return self.readers().ladder_records()

    def input_meta(self) -> dict:
        import war_source
        meta = dict(self.readers().meta)
        meta["preview_sha256"] = T.sha256_of(PREVIEW_PATH)
        for side in ("bat", "pit"):
            meta.setdefault("bwar_cache_sha256", {})[side] = T.sha256_of(war_source._cache_path(side))
        return meta

    def pe_wear(self, season: int) -> float:
        return self.readers().pitch_economy_wear(int(season))


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
        rpw = _num(blk.get("rpw"))
        for r in blk.get("hitters") or []:
            parts = r.get("parts") or {}
            hit[int(r["mlbam"])] = {
                "pa": _num(r.get("pa")), "fwar": _num(r.get("fwar")), "name": r.get("name", ""),
                "pitcher_batter": bool(r.get("pitcher_batter")),
                "tests": {p: _num((parts.get(p) or {}).get("test")) for p in swar.HITTER_PARTS},
                # part 11.2.1: the bases and the re-centred deltas (runs)
                "rpw": rpw, "wraa": _num((parts.get("bat") or {}).get("wraa")),
                "fld_b0": _num((parts.get("fld") or {}).get("b0")),
                "d": {p: _num((parts.get(p) or {}).get("d")) for p in swar.HITTER_PARTS}}
        for r in blk.get("pitchers") or []:
            parts = r.get("parts") or {}
            pit[int(r["mlbam"])] = {
                "ip": _num(r.get("ip")), "fwar": _num(r.get("fwar")), "name": r.get("name", ""),
                "sigma": _num(r.get("sigma")), "nopp": bool(r.get("nopp")),
                "tests": {v: _num((parts.get(v) or {}).get("test")) for v in swar.HR_VARIANTS + PB_VARIANTS},
                "dwar0": {v: _num((parts.get(v) or {}).get("dwar0")) for v in swar.HR_VARIANTS},
                "lb_dwar0": {v: _num((parts.get(v) or {}).get("lb_dwar0")) for v in swar.HR_VARIANTS},
                # part 11.2.1: the base war0, RA9*, games and the re-pinned Deltas (wins)
                "rpw": rpw, "war0": _num(r.get("war0")), "ra9_star": _num(r.get("ra9_star")),
                "g": _num(r.get("g")), "gs": _num(r.get("gs")),
                "delta": {v: _num((parts.get(v) or {}).get("delta")) for v in swar.HR_VARIANTS + PB_VARIANTS}}
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
                        "sigma": r0.get("sigma"), "c_inn": r0.get("c_inn")})
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
    same-season wins. The next-season wins leg of part 9.5 is replaced by the
    team guard (11.2.4) for every part it decides. Computed only inside the look
    run; printed only to its output and record."""
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
    for label, shift in (("same_season_wins", 0),):
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


def secondary_cells() -> dict:
    """The secondary estimand's families (11.2.5): part 9.5's cells as first
    registered, with the cells of the parts registered after it (S3t when
    eligible, S3c on the catcher frame, PE-P per IP, PE-H per PA)."""
    fld = dict(PART_CELLS[PART_FIELDING])
    if S3T_ELIGIBLE:
        fld.update({"S3t H-rate": ("fldt", RATE), "S3t H-cum": ("fldt", CUM)})
    fld.update({"C-rate": ("cat", RATE), "C-cum": ("cat", CUM)})
    return {PART_POSITION: PART_CELLS[PART_POSITION], PART_BATTING: PART_CELLS[PART_BATTING],
            PART_PITCHING: PART_CELLS[PART_PITCHING], PART_FIELDING: fld,
            PART_PE_P: {"side": PIT, "cells": {"PE-P rate": (PEP, RATE), "PE-P total": (PEP, CUM)}},
            PART_PE_H: {"side": HIT, "cells": {"PE-H rate": ("peh", RATE), "PE-H total": ("peh", CUM)}}}


def _secondary_frame(key: str, pairs: list[dict]) -> list[dict]:
    """The catcher component's cells read the catcher frame (11.6.2)."""
    if key == "cat":
        return [p for p in pairs if float(p.get("c_inn") or 0.0) >= T.CATCHER_MIN_INN]
    return pairs


def score_block(rows: dict, seasons: tuple, boot: int,
                log: Callable, early_pairs_p: Optional[list] = None,
                hr_choice: Optional[dict] = None, label: str = "look",
                spec: Optional[Mapping] = None) -> dict:
    """The fWAR-target cells of one block (the look's 2021 to 2024, or the
    holdout's 2025), since part 11.2 the secondary estimand: floors first, the
    HR-arm clause first among decisions (or the primary's, passed in), then
    gaps, Holm per part and dispositions. Admission never reads this block."""
    fams = spec if spec is not None else {p: PART_CELLS[p] for p in PARTS}
    fams = {p: (v if "side" in v else {"side": PART_CELLS[p]["side"], "cells": v}) for p, v in fams.items()}
    pairs_h = build_pairs(rows, HIT, seasons)
    pairs_p = build_pairs(rows, PIT, seasons)
    early_p = early_pairs_p if early_pairs_p is not None else build_pairs(rows, PIT, TRANSPORT_EARLY_SEASONS)
    _p(log, f"[{label}] frame: {len(pairs_h)} hitter pairs, {len(pairs_p)} pitcher pairs; "
            f"2016 to 2018 pitcher block {len(early_p)} pairs")

    # -- score every cell (both home-run variants on the pitcher side); draws kept
    recs: dict = {}
    for i, (part, spec) in enumerate(fams.items()):
        for j, (cell, (key, kind)) in enumerate(spec["cells"].items()):
            keys = (list(swar.HR_VARIANTS) if key == PITCH
                    else list(PB_VARIANTS) if key == PITCH_B
                    else ["pep_" + v for v in swar.HR_VARIANTS] if key == PEP else [key])
            for v in keys:
                pairs = _secondary_frame(key, pairs_p if spec["side"] == PIT else pairs_h)
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
        return (variant if key == PITCH else pb_key(variant) if key == PITCH_B
                else "pep_" + variant if key == PEP else key)

    # -- gaps and clauses
    cells: dict = {}
    for part, spec in fams.items():
        fam = {}
        for cell, (key, kind) in spec["cells"].items():
            rec = finish_cell(recs[(part, cell, _series(key))])
            if part in TRANSPORT_PARTS and kind == RATE:
                ge = point_gap_v2(early_p, _series(key), None, RATE, PIT)
                rec["transport_gap_2016_2018"] = ge
                rec["transport"] = transport_holds(ge, rec.get("gap"))
            fam[cell] = rec
        if part == PART_PITCHING:
            for r_cell, c_cell in PITCHING_ARMS.values():
                fam[c_cell]["transport"] = fam[r_cell].get("transport")
        if part == PART_PE_P:
            fam["PE-P total"]["transport"] = fam["PE-P rate"].get("transport")
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

    _p(log, f"[{label}] GAPS AND DISPOSITIONS (convention v2 against fWAR(Y); v1 must agree in sign)")
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


# --------------------------------------------------------------------------
# part 11.2: the primary targets, B0, B0r, the amended B1, the team guard
# --------------------------------------------------------------------------

#: The component frames of the primary cells (11.2.1, 11.4.4, 11.5.2, 11.6.2):
#: side, the floor's exposure (hitters 200 PA, pitchers 50 IP in both seasons)
#: and the cell's own exposure (per PA, per IP, or per game pitched for PE-P).
COMPONENTS = {
    "bat": {"side": HIT, "n": "pa"},
    "pit": {"side": PIT, "n": "ip"},
    "fld": {"side": HIT, "n": "pa"},
    "fldt:DRS": {"side": HIT, "n": "pa"},
    "fldt:Statcast": {"side": HIT, "n": "pa"},
    "fldt:UZR": {"side": HIT, "n": "pa"},
    "cat": {"side": HIT, "n": "pa"},
    "pep": {"side": PIT, "n": "g"},
    "peh": {"side": HIT, "n": "pa"},
}
#: S3t's systems (11.5.2): (component frame, the arm rebuilt without the system).
S3T_SYSTEMS = (("DRS", "fldt:DRS", "X_DRS"), ("Statcast", "fldt:Statcast", "X_SC"),
               ("UZR", "fldt:UZR", "X_UZR"))
S3T_CONFIGS = ("FULL", "X_DRS", "X_SC", "X_UZR")

#: Owner decision EW3-37 (EBR_GATE.md 11.7): S3t is scored, by override of 11.5.2's
#: eligibility sentence. False would drop its two cells (k = 4 with S3c).
S3T_ELIGIBLE = True

#: The primary families: {family: {cell: (frames, test key, kind)}}, where frames
#: names one component or the S3t systems. The pitching test keys resolve to the
#: home-run term the HR-arm clause chose (PITCH, PITCH_B), and PE-P's too (PEP).
PEP = "__pe_p__"
PRIMARY_FAMILIES: Mapping[str, dict] = {
    PART_BATTING: {"HEM+ H-rate": ("bat", "bat", RATE), "HEM+ H-cum": ("bat", "bat", CUM),
                   "xHEM+ H-rate": ("bat", "batx", RATE), "xHEM+ H-cum": ("bat", "batx", CUM)},
    PART_PITCHING: {"P-rate": ("pit", PITCH, RATE), "P-cum": ("pit", PITCH, CUM),
                    "S2b P-rate": ("pit", PITCH_B, RATE), "S2b P-cum": ("pit", PITCH_B, CUM)},
    PART_FIELDING: {"H-rate": ("fld", "fld", RATE), "H-cum": ("fld", "fld", CUM),
                    "S3t H-rate": ("S3t", "fldt", RATE), "S3t H-cum": ("S3t", "fldt", CUM),
                    "C-rate": ("cat", "cat", RATE), "C-cum": ("cat", "cat", CUM)},
    PART_PE_P: {"PE-P rate": ("pep", PEP, RATE), "PE-P total": ("pep", PEP, CUM)},
    PART_PE_H: {"PE-H rate": ("peh", "peh", RATE), "PE-H total": ("peh", "peh", CUM)},
}
PRIMARY_PARTS = tuple(PRIMARY_FAMILIES)
#: B1's component k per component frame (the S3t systems take the fielding k, 11.5.2).
B1_COMPONENT = {"bat": "bat", "pit": "pit", "fld": "fld", "S3t": "fld", "cat": "cat",
                "pep": "pep", "peh": "peh"}
#: The arms of each family with arms: {arm: (rate cell, total cell, guard series)}.
FIELDING_ARMS = {"S3": ("H-rate", "H-cum", "fld"), "S3t": ("S3t H-rate", "S3t H-cum", "fldt")}
CATCHER_CELLS = ("C-rate", "C-cum", "cat")
#: The one comparative sentence's [component's runs] (11.2.6, 11.4.5, 11.5.3, 11.6.3).
COMPONENT_RUNS = {
    "bat": "batting runs",
    "pit": "runs allowed (adjusted for park, defense and inherited runners)",
    "fld": "fielding runs (from Baseball-Reference's runs_field)",
    "fldt": "fielding runs (from the system the arm leaves out: DRS, Statcast or UZR)",
    "cat": "fielding runs (from Sports Info Solutions' DRS)",
    "pep": ("runs saved over a league-average reliever (adjusted for park, defense and "
            "inherited runners)"),
    "peh": "batting runs plus starter-wear runs",
}
AMENDED_SENTENCES = {
    WIN_COMPONENTS: ("ranked the next season's realized {x} better than the season's own {x} did, "
                     "and better than a uniformly shrunk version of them"),
    WIN_REGRESSION: "ranked the next season's realized {x} better than the season's own {x} did",
    EQUIVALENT: "ranked the next season's realized {x} about as well as the season's own {x} did",
    LOSS: "ranked the next season's realized {x} less well than the season's own {x} did",
    UNRESOLVED: None,
}
POSITION_SENTENCE = ("on held-out seasons, our ladder matched position switchers' realized defensive "
                     "and positional runs more closely than FanGraphs' positional adjustment did")


def amended_sentence(component: str, disp: str, gap=None, lo95=None, hi95=None, n=None,
                     seasons=PREDICTOR_SEASONS) -> Optional[str]:
    """The one sentence copy may carry for a part's rate cell on the primary
    target (11.2.6), with its frame and numbers; None for UNRESOLVED."""
    base = AMENDED_SENTENCES[counts_as(disp)]
    if base is None:
        return None
    base = base.format(x=COMPONENT_RUNS[component])
    if component == "cat":
        who = "catchers with 300 or more innings at C and 200 or more PA"
    elif component in ("pit", "pep"):
        who = "pitchers with 50 or more IP"
    else:
        who = "hitters with 200 or more PA"
    nums = ""
    if gap is not None and lo95 is not None and hi95 is not None and n is not None:
        nums = f", Spearman gap {gap:+.3f} (95 percent interval {lo95:+.3f} to {hi95:+.3f}, {n:,} pairs)"
    return f"{base}, on {seasons[0]} to {seasons[-1]} seasons, {who} in both seasons{nums}"


# ---- B1, amended (11.2.1): one k per component, from B0 and the target only

#: FIXED by EWV3_LAB_AMENDED_TARGETS from B0 and each component's own target
#: (no candidate part, delta or test value read), with the rule of fit_b1:
#: pooled Pearson r of the B0 rate in Y and the target rate in Y+1 on the
#: predictor pairs at the floors, r clamped [0.05, 0.95], k = hm (1 - r) / r,
#: hm the mean harmonic exposure, rounded. tools/swar_b1_fit.py --amended
#: reproduces it. The frozen fWAR constants B1_K serve the secondary estimand only.
#: Fit output, 2026-10-19, for the record (exposure: PA, IP, or games pitched):
#:   bat  pairs 800  players 380  r 0.4676  hm 471.4 PA   k 537 PA
#:   pit  pairs 670  players 356  r 0.2146  hm 109.9 IP   k 402 IP
#:   fld  pairs 800  players 380  r 0.2522  hm 471.4 PA   k 1398 PA
#:   cat  pairs 102  players 49   r 0.4547  hm 366.5 PA   k 440 PA
#:   pep  pairs 670  players 356  r 0.2327  hm 39.5 G     k 130 G
#:   peh  pairs 262  players 262  r 0.5202  hm 463.0 PA   k 427 PA   (the 2018 to 2019 pair)
#: (preview vintage 2026-10-02-57bf90f7143e, preview built 2026-10-19.)
B1_K_AMENDED: dict = {"bat": 537.0, "pit": 402.0, "fld": 1398.0, "cat": 440.0, "pep": 130.0, "peh": 427.0}
B1_AMENDED_FIT_LOG: dict = {
    "fixed_on": "2026-10-19",
    "task": "EWV3_LAB_AMENDED_TARGETS",
    "producer": "python tools/swar_b1_fit.py --amended",
    "rule": ("fit_b1's rule on the component's own pairs: pooled Pearson r of the B0 rate in Y and "
             "the target rate in Y+1 at the floors, r clamped [0.05, 0.95], k = hm (1 - r) / r, hm the "
             "mean harmonic exposure of the pairs, rounded to a whole unit; B0 and the target only"),
    "shrink_target": ("m: the season's exposure-weighted mean B0 rate over the component's rows at the "
                      "floor (the catcher frame for cat)"),
    "floors": {"hit_pa": 200.0, "pit_ip": 50.0, "catcher_inn_c": 300.0},
    "fwar_vintage_id": "2026-10-02-57bf90f7143e",
    "preview_sha256": "cc01fbf462f10ea26b254ba74729766a1ee8e9439c7cb3c10c2305e39f076bef",
    "bat": {"target": "wRAA per PA in Y+1", "fit_seasons": [2016, 2017, 2018], "n_pairs": 800,
            "n_players": 380, "r": 0.4676, "hm": 471.4, "k": 537.0},
    "pit": {"target": "RA9* runs prevented per IP in Y+1", "fit_seasons": [2016, 2017, 2018],
            "n_pairs": 670, "n_players": 356, "r": 0.2146, "hm": 109.9, "k": 402.0},
    "fld": {"target": "Baseball-Reference runs_field per PA in Y+1", "fit_seasons": [2016, 2017, 2018],
            "n_pairs": 800, "n_players": 380, "r": 0.2522, "hm": 471.4, "k": 1398.0},
    "cat": {"target": "DRS per PA in Y+1, catchers at 300 or more innings at C in Y",
            "fit_seasons": [2016, 2017, 2018], "n_pairs": 102, "n_players": 49, "r": 0.4547,
            "hm": 366.5, "k": 440.0},
    "pep": {"target": "RSB per game pitched in Y+1", "fit_seasons": [2016, 2017, 2018], "n_pairs": 670,
            "n_players": 356, "r": 0.2327, "hm": 39.5, "k": 130.0},
    "peh": {"target": "wRAA plus realized starter wear W per PA in Y+1", "fit_seasons": [2018],
            "n_pairs": 262, "n_players": 262, "r": 0.5202, "hm": 463.0, "k": 427.0},
}
#: Fit seasons per component: 2016 to 2018 predictor pairs; PE-H on the 2018 to
#: 2019 pair, the only corpus pair before the frame (11.4.4).
B1_AMENDED_SEASONS = {"bat": (2016, 2017, 2018), "pit": (2016, 2017, 2018), "fld": (2016, 2017, 2018),
                      "cat": (2016, 2017, 2018), "pep": (2016, 2017, 2018), "peh": (2018,)}


def fit_b1_pairs(pairs: list[dict]) -> dict:
    """fit_b1's rule on component pairs: B0 rate in Y against the target rate in
    Y+1. Reads n0, n1, b0 and tgt only."""
    x0, x1, hm, players = [], [], [], set()
    for p in pairs:
        if p["b0"] is None or p["tgt"] is None or p["n0"] <= 0 or p["n1"] <= 0:
            continue
        x0.append(p["b0"] / p["n0"])
        x1.append(p["tgt"] / p["n1"])
        hm.append(2.0 / (1.0 / p["n0"] + 1.0 / p["n1"]))
        players.add(p["mlbam"])
    if len(x0) < 30:
        raise LabStop(f"B1 fit: {len(x0)} pairs, under 30")
    r_raw = pearson(x0, x1)
    if r_raw is None:
        raise LabStop("B1 fit: an undefined correlation")
    r = min(max(r_raw, R_CLAMP[0]), R_CLAMP[1])
    hmm = float(np.mean(hm))
    return {"n_pairs": len(x0), "n_players": len(players), "r_raw": round(r_raw, 4), "r": round(r, 4),
            "hm": round(hmm, 1), "k": float(round(hmm * (1.0 - r) / r))}


# ---- assembling the amended inputs onto the preview's rows

def assemble(rows: dict, inputs: "LabInputs", seasons: Iterable[int], peh_seasons: Iterable[int],
             log: Callable = print, deltas: bool = True) -> dict:
    """Adds, in place, every input of the amended targets to the preview's rows
    and returns the season constants {season: {lg_ra9s, lg_ra9s_rp, w, corpus}}.
    Same-season quantities only. Called before scoring begins. With `deltas`
    False (B1's fit) no candidate part's delta is computed: only the bases'
    and the targets' inputs are attached."""
    import pitch_economy as pe
    seasons = sorted(set(int(s) for s in seasons) & set(rows))
    fb = inputs.fielding_by_player()
    tri = inputs.triangulation_runs() if (S3T_ELIGIBLE and deltas) else {}
    peh_seasons = set(int(s) for s in peh_seasons)
    consts: dict = {}
    for y in seasons:
        hit, pit = rows[y][HIT], rows[y][PIT]
        pa = {m: float(r.get("pa") or 0.0) for m, r in hit.items()}
        pb = {m for m, r in hit.items() if r.get("pitcher_batter")}
        f = fb.get(y) or {}
        for m, r in hit.items():
            x = f.get(m) or {}
            r["fg"] = {k: x.get(k) for k in ("drs", "uzr", "frp", "c_drs")}
            r["rfield"] = x.get("runs_field")
            r["c_inn"] = float(x.get("c_inn") or 0.0)
            r["sc"], r["nonc_frp"] = x.get("sc"), float(x.get("nonc_frp") or 0.0)
        lg, lg_rp = T.league_ra9_star(pit.values()), T.league_ra9_star(pit.values(), relievers_only=True)
        if not deltas:
            consts[y] = {"lg_ra9s": lg, "lg_ra9s_rp": lg_rp, "w": inputs.pe_wear(y), "corpus": False}
            peh = inputs.pe_hitters(y) if y in peh_seasons else None
            for m, r in hit.items():
                res = ((peh or {}).get("resid") or {}).get(m) or {}
                r["W"] = None if peh is None else float(consts[y]["w"]) * float(res.get("pres") or 0.0)
            consts[y]["corpus"] = peh is not None
            continue
        dc = T.catcher_deltas({m: {"sc": (f.get(m) or {}).get("sc"), "b0": r.get("fld_b0") or 0.0,
                                   "nonc_frp": (f.get(m) or {}).get("nonc_frp") or 0.0,
                                   "c_inn": r["c_inn"]} for m, r in hit.items()}, pa, pb)
        b0 = {m: r.get("fld_b0") or 0.0 for m, r in hit.items()}
        t = tri.get(y) or {}
        for cfg in (S3T_CONFIGS if S3T_ELIGIBLE else ()):
            dd = T.fldt_deltas({m: (t.get(m) or {}).get(cfg, 0.0) for m in hit}, b0, pa, pb)
            for m, r in hit.items():
                r["d"]["fldt_" + cfg] = dd[m]
        for m, r in hit.items():
            r["d"]["cat"] = dc[m]
        pep = inputs.pe_pitchers(y)
        for m, r in pit.items():
            r["d_pe"] = {v: float(pep["delta"][v].get(m, 0.0)) for v in swar.HR_VARIANTS}
        consts[y] = {"lg_ra9s": lg, "lg_ra9s_rp": lg_rp, "w": pep["w"], "corpus": False,
                     "pe_p_coverage": pep.get("coverage")}
        peh = inputs.pe_hitters(y) if y in peh_seasons else None
        if peh is None:
            for m, r in hit.items():
                r["d"].update({"peh": 0.0, "peh_cl": 0.0, "peh_p": 0.0})
                r["W"] = None
            continue
        dd = T.pe_h_deltas(peh["resid"], peh["pa"], pep["w"], pe.K_CL, pe.K_P)
        consts[y]["corpus"] = True
        for m, r in hit.items():
            res = peh["resid"].get(m) or {}
            pbat = m in pb
            r["d"].update({"peh": 0.0 if pbat else float(dd["peh"].get(m, 0.0)),
                           "peh_cl": 0.0 if pbat else float(dd["cl"].get(m, 0.0)),
                           "peh_p": 0.0 if pbat else float(dd["p"].get(m, 0.0))})
            r["W"] = float(pep["w"]) * float(res.get("pres") or 0.0)
        log(f"  assembled {y}: {len(hit)} hitters, {len(pit)} pitchers, corpus {consts[y]['corpus']}")
    return consts


# ---- the component values of one row (B0, the target construction, test values)

def _add(a, b) -> Optional[float]:
    return None if a is None or b is None else float(a) + float(b)


def comp_b0(comp: str, r: Mapping) -> Optional[float]:
    if comp in ("bat", "peh"):
        return r.get("wraa")
    if comp in ("pit", "pep"):
        return r.get("war0")
    return r.get("fld_b0")


def comp_target(comp: str, r: Mapping, k: Mapping, season: int) -> Optional[float]:
    """The target's construction on one row of `season` (the target when the row
    is Y+1, B0r when it is Y)."""
    if comp == "bat":
        return r.get("wraa")
    if comp == "pit":
        return T.runs_prevented(k.get("lg_ra9s"), r.get("ra9_star"), r.get("ip"))
    if comp == "pep":
        ip = r.get("ip")
        return T.rsb(None if ip is None else ip * 3.0, k.get("lg_ra9s_rp"), r.get("ra9_star"))
    if comp == "peh":
        return _add(r.get("wraa"), r.get("W"))
    if comp == "fld":
        return r.get("rfield")
    fg = r.get("fg") or {}
    if comp == "fldt:DRS" or comp == "cat":
        return fg.get("drs")
    if comp == "fldt:Statcast":
        return fg.get("frp")
    if comp == "fldt:UZR":
        return fg.get("uzr") if int(season) <= T.UZR_LAST else None
    raise ValueError(comp)


def comp_tests(comp: str, r: Mapping) -> dict:
    d = r.get("d") or {}
    b0 = comp_b0(comp, r)
    if comp == "bat":
        return {"bat": _add(b0, d.get("bat")), "batx": _add(b0, d.get("batx"))}
    if comp == "pit":
        out = {v: _add(b0, (r.get("delta") or {}).get(v)) for v in swar.HR_VARIANTS + PB_VARIANTS}
        rpw = r.get("rpw")
        for v in swar.HR_VARIANTS:
            dp = (r.get("d_pe") or {}).get(v)
            out["pep_" + v] = None if (dp is None or not rpw) else _add(b0, dp / rpw)
        return out
    if comp == "pep":
        rpw = r.get("rpw")
        return {"pep_" + v: (None if not rpw else _add(b0, ((r.get("d_pe") or {}).get(v) or 0.0) / rpw))
                for v in swar.HR_VARIANTS}
    if comp == "peh":
        return {k: _add(b0, d.get(k)) for k in ("peh", "peh_cl", "peh_p")}
    if comp == "fld":
        return {"fld": _add(b0, d.get("fld")), "fldt": _add(b0, d.get("fldt_FULL"))}
    if comp.startswith("fldt:"):
        cfg = dict((c, x) for _s, c, x in S3T_SYSTEMS)[comp]
        return {"fldt": _add(b0, d.get("fldt_" + cfg)), "fld": _add(b0, d.get("fld")),
                "fldt_full": _add(b0, d.get("fldt_FULL"))}
    if comp == "cat":
        return {"cat": _add(b0, d.get("cat")), "fldt_full": _add(b0, d.get("fldt_FULL"))}
    raise ValueError(comp)


def _in_frame(comp: str, r: Mapping) -> bool:
    return comp != "cat" or float(r.get("c_inn") or 0.0) >= T.CATCHER_MIN_INN


def component_pairs(rows: Mapping[int, dict], comp: str, seasons: Iterable[int], consts: Mapping,
                    with_tests: bool = True) -> list[dict]:
    """(Y, Y+1) pairs of one component at the side's floor in both seasons (2020
    out on both sides), the catcher frame for S3c. Each pair: n0, n1 (the
    component's exposure), b0, tgt (the target in Y+1), b0r (the target's
    construction in Y), tgt_alt (PE-H's wRAA(Y+1) alone), m (the season's
    exposure-weighted mean B0 rate at the floor, in the frame) and, unless
    `with_tests` is False (B1's fit), the test values."""
    spec = COMPONENTS[comp]
    side, nkey, fkey = spec["side"], spec["n"], EXPOSURE[spec["side"]]
    out = []
    for y in seasons:
        y = int(y)
        if y == EXCLUDED_SEASON or y + 1 == EXCLUDED_SEASON:
            continue
        a, b = (rows.get(y) or {}).get(side) or {}, (rows.get(y + 1) or {}).get(side) or {}
        ka, kb = consts.get(y) or {}, consts.get(y + 1) or {}
        num = den = 0.0
        for r in a.values():
            b0, n = comp_b0(comp, r), r.get(nkey)
            if _at_floor(r.get(fkey), side) and _in_frame(comp, r) and b0 is not None and n:
                num += b0
                den += n
        m = num / den if den > 0 else None
        for mid in sorted(a):
            if mid not in b:
                continue
            r0, r1 = a[mid], b[mid]
            if not (_at_floor(r0.get(fkey), side) and _at_floor(r1.get(fkey), side)):
                continue
            if not _in_frame(comp, r0):
                continue
            n0, n1 = r0.get(nkey), r1.get(nkey)
            b0, tgt = comp_b0(comp, r0), comp_target(comp, r1, kb, y + 1)
            if not n0 or not n1 or n0 <= 0 or n1 <= 0 or b0 is None or tgt is None:
                continue
            p = {"mlbam": mid, "y": y, "n0": float(n0), "n1": float(n1), "b0": float(b0),
                 "tgt": float(tgt), "b0r": comp_target(comp, r0, ka, y), "m": m,
                 "sigma": r0.get("sigma"), "c_inn1": r1.get("c_inn"),
                 "c_drs1": (r1.get("fg") or {}).get("c_drs"), "tests": {}}
            if comp == "peh":
                p["tgt_alt"] = r1.get("wraa")
            if with_tests:
                p["tests"] = comp_tests(comp, r0)
            out.append(p)
    return out


# ---- the primary cell: one or several systems, one bootstrap

def _permute_deltas(ys, ns, deltas, rng) -> np.ndarray:
    """The twin's draw: deltas permuted within (predictor season, exposure decile)."""
    out = np.zeros(len(deltas))
    ys, ns, deltas = np.asarray(ys), np.asarray(ns, float), np.asarray(deltas, float)
    for y in sorted(set(ys.tolist())):
        idx = np.flatnonzero(ys == y)
        if len(idx) >= 10:
            edges = np.quantile(ns[idx], np.linspace(0, 1, 11)[1:-1])
            dec = np.searchsorted(edges, ns[idx], side="right")
        else:
            dec = np.zeros(len(idx), dtype=int)
        for dval in sorted(set(dec.tolist())):
            members = idx[dec == dval]
            out[members] = deltas[members][rng.permutation(len(members))]
    return out


def frame_arrays(frames: list[tuple], kind: str, k_b1: float, twin_seed: int,
                 key_b: Optional[str] = None) -> Optional[dict]:
    """Stack one cell's frames [(system, pairs, test key)] into arrays: the
    series test, b0, b1, twin, b0r (and `key_b`'s test, for a contrast), the
    targets (v1 raw, v2 z within system and outcome season) and the labels."""
    lab, mid, ys, n0, n1, b0, tv, tg, m, b0r, tb = ([] for _ in range(11))
    for li, (_name, pairs, key) in enumerate(frames):
        for p in pairs:
            t = p["tests"].get(key)
            if t is None:
                continue
            if key_b is not None and p["tests"].get(key_b) is None:
                continue
            lab.append(li)
            mid.append(p["mlbam"])
            ys.append(p["y"])
            n0.append(p["n0"])
            n1.append(p["n1"])
            b0.append(p["b0"])
            tv.append(t)
            tg.append(p["tgt"])
            m.append(p["m"] if p["m"] is not None else 0.0)
            b0r.append(np.nan if p.get("b0r") is None else p["b0r"])
            tb.append(np.nan if key_b is None else p["tests"][key_b])
    if len(lab) < 4:
        return None
    A = {k: np.asarray(v, float) for k, v in (("n0", n0), ("n1", n1), ("b0", b0), ("test", tv),
                                                 ("tgt", tg), ("m", m), ("b0r", b0r), ("tb", tb))}
    lab, ys = np.asarray(lab), np.asarray(ys)
    rng = np.random.default_rng(twin_seed)
    tw = np.zeros(len(lab))
    for li in sorted(set(lab.tolist())):
        idx = np.flatnonzero(lab == li)
        tw[idx] = _permute_deltas(ys[idx], A["n0"][idx], A["test"][idx] - A["b0"][idx], rng)
    b1r = (A["b0"] + A["m"] * k_b1) / (A["n0"] + k_b1)
    if kind == RATE:
        s = {"test": A["test"] / A["n0"], "b0": A["b0"] / A["n0"], "b1": b1r,
             "twin": (A["b0"] + tw) / A["n0"]}
        if key_b is not None:
            s["test_b"] = A["tb"] / A["n0"]
        raw = A["tgt"] / A["n1"]
        b0r_s = A["b0r"] / A["n0"]
    else:
        s = {"test": A["test"], "b0": A["b0"], "b1": b1r * A["n0"], "twin": A["b0"] + tw}
        if key_b is not None:
            s["test_b"] = A["tb"]
        raw = A["tgt"]
        b0r_s = A["b0r"]
    grp = [f"{int(a)}|{int(y) + 1}" for a, y in zip(lab, ys)]
    return {"series": s, "target_v1": raw, "target_v2": zscore_within(grp, raw), "lab": lab,
            "players": list(mid), "strata": ys.tolist(), "b0r": b0r_s, "n_systems": len(frames),
            "names": [f[0] for f in frames]}


def multi_rho(series: Mapping[str, np.ndarray], target: np.ndarray, lab: np.ndarray,
              idx: Optional[np.ndarray] = None, systems: Optional[Iterable[int]] = None) -> dict:
    """The mean over systems of each series' Spearman with the target on the
    rows `idx` (all rows when None); NaN when a system's rho is undefined."""
    idx = np.arange(len(lab)) if idx is None else idx
    systems = sorted(set(lab.tolist())) if systems is None else list(systems)
    acc = {k: [] for k in series}
    for li in systems:
        sel = idx[lab[idx] == li]
        if len(sel) < 4:
            for k in series:
                acc[k].append(np.nan)
            continue
        rt = _rank(target[sel])
        for k, v in series.items():
            r = _pearson(_rank(v[sel]), rt)
            acc[k].append(np.nan if r is None else r)
    return {k: float(np.mean(v)) if v else np.nan for k, v in acc.items()}


def _rho_draws_multi(series, target, lab, draws) -> dict[str, np.ndarray]:
    systems = sorted(set(lab.tolist()))
    out = {k: np.full(len(draws), np.nan) for k in series}
    for b, idx in enumerate(draws):
        r = multi_rho(series, target, lab, idx, systems)
        for k in series:
            out[k][b] = r[k]
    return out


def _nan_none(v):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)


def prep_primary(part: str, cell: str, frames: list[tuple], kind: str, k_b1: float,
                 boot: int, seed: int, twin_seed: int) -> dict:
    """Every number a primary cell needs, draws kept; the floors are read off
    the draws before any gap prints."""
    rec = {"part": part, "cell": cell, "kind": kind, "systems": [f[0] for f in frames],
           "series": sorted(set(f[2] for f in frames)), "b1_k": k_b1}
    fa = frame_arrays(frames, kind, k_b1, twin_seed)
    if fa is None:
        rec.update(empty=True, n_pairs=0, n_players=0)
        return rec
    # a pair is one player's (Y, Y+1); S3t's systems score the same pair up to three times
    rec["n_pairs"] = len(set(zip(fa["players"], fa["strata"])))
    rec["n_rows"] = int(len(fa["lab"]))
    rec["n_players"] = len(set(fa["players"]))
    rec["n_pairs_by_system"] = {fa["names"][li]: int((fa["lab"] == li).sum()) for li in sorted(set(fa["lab"].tolist()))}
    d2 = _rho_draws_multi(fa["series"], fa["target_v2"], fa["lab"],
                          cluster_draws(fa["players"], fa["strata"], boot, seed))
    d1 = _rho_draws_multi({"test": fa["series"]["test"], "b0": fa["series"]["b0"]}, fa["target_v1"], fa["lab"],
                          iid_draws(len(fa["lab"]), boot, seed))
    rec["_fa"], rec["_draws"] = fa, {"v2": d2, "v1": d1}
    rec["floors"] = {k: v for k, v in gap_summary(d2["test"], d2["b0"]).items()
                     if k in ("n_draws", "sd", "half_width95", "mde95")}
    return rec


def finish_primary(rec: dict) -> dict:
    """The gaps, intervals and clauses of a prepared primary cell; B0r and the
    gap over it beside, with no weight."""
    if rec.get("empty"):
        return finish_cell(rec)
    fa, d2, d1 = rec["_fa"], rec["_draws"]["v2"], rec["_draws"]["v1"]
    s, t2, t1, lab = fa["series"], fa["target_v2"], fa["target_v1"], fa["lab"]
    rho = {k: _nan_none(v) for k, v in multi_rho(s, t2, lab).items()}
    g, gb1 = gap_summary(d2["test"], d2["b0"]), gap_summary(d2["test"], d2["b1"])
    gtw, g1 = gap_summary(d2["twin"], d2["b0"]), gap_summary(d1["test"], d1["b0"])
    gap = None if rho["test"] is None or rho["b0"] is None else rho["test"] - rho["b0"]
    r1 = multi_rho({"test": s["test"], "b0": s["b0"]}, t1, lab)
    v1_gap = _nan_none(r1["test"] - r1["b0"])
    pears = []
    for li in sorted(set(lab.tolist())):
        sel = lab == li
        pt, pb = pearson(s["test"][sel], t2[sel]), pearson(s["b0"][sel], t2[sel])
        if pt is not None and pb is not None:
            pears.append(pt - pb)
    ok = np.isfinite(fa["b0r"])
    b0r = None
    if ok.sum() >= 4:
        rr = multi_rho({"test": s["test"][ok], "b0r": fa["b0r"][ok]}, t2[ok], lab[ok])
        b0r = {"n_pairs": int(ok.sum()), "rho_b0r": _nan_none(rr["b0r"]),
               "gap_over_b0r": _nan_none(rr["test"] - rr["b0r"]), "weight": "none (11.2.1)"}
    per_system = {}
    for li in sorted(set(lab.tolist())):
        sel = lab == li
        a, b = spearman(s["test"][sel], t2[sel]), spearman(s["b0"][sel], t2[sel])
        per_system[fa["names"][li]] = {"n_pairs": int(sel.sum()), "rho_test": a, "rho_b0": b,
                                       "gap": None if a is None or b is None else a - b}
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
        "pearson_gap_v2": (float(np.mean(pears)) if pears else None),
        "equivalent_reachable": bool(g["mde95"] is not None and g["mde95"] <= MARGIN),
        "b0r": b0r, "per_system": per_system,
    })
    return rec


def point_gap_frames(frames: list[tuple], kind: str, k_b1: float, key_b: Optional[str] = None) -> Optional[float]:
    """The v2 point gap of the frames' test over B0 (or over `key_b`'s test, on
    the rows carrying both); no bootstrap."""
    fa = frame_arrays(frames, kind, k_b1, 0, key_b=key_b)
    if fa is None:
        return None
    other = "test_b" if key_b is not None else "b0"
    r = multi_rho({"a": fa["series"]["test"], "b": fa["series"][other]}, fa["target_v2"], fa["lab"])
    return _nan_none(r["a"] - r["b"])


def contrast_frames(frames: list[tuple], key_b: str, boot: int, seed: int, k_b1: float) -> dict:
    """An arm tie-break on the primary target: rho(arm a) - rho(arm b) on the
    rate cell, the same pairs, the same bootstrap, outside the Holm family."""
    fa = frame_arrays(frames, RATE, k_b1, 0, key_b=key_b)
    if fa is None:
        return {"n_pairs": 0, "gap": None, "lo95": None, "hi95": None, "sd": None}
    s = {"a": fa["series"]["test"], "b": fa["series"]["test_b"]}
    d = _rho_draws_multi(s, fa["target_v2"], fa["lab"], cluster_draws(fa["players"], fa["strata"], boot, seed))
    g = gap_summary(d["a"], d["b"])
    r = multi_rho(s, fa["target_v2"], fa["lab"])
    return {"n_pairs": int(len(fa["lab"])), "gap": _nan_none(r["a"] - r["b"]), "lo95": g["lo95"],
            "hi95": g["hi95"], "sd": g["sd"]}


# ---- the primary block: floors first, the HR-arm clause first, then the cells

def decide_family(fam: dict) -> dict:
    """Holm over one family's cells, then each cell's one disposition (in
    place). The cells carry their part, gaps, intervals and clauses."""
    hr = holm({c: r.get("p_one_sided") for c, r in fam.items()})
    for c, r in fam.items():
        r["holm_family"] = list(fam)
        r["holm_reject"] = hr[c]
        r["disposition"] = disposition(r)
        r["counts_as"] = counts_as(r["disposition"])
        r["ship_flag_no_weight"] = (None if r["disposition"] not in WINS
                                    else bool(r.get("gap") is not None and (r["floors"].get("sd") or 0) > 0
                                              and r["gap"] - MDE_Z * r["floors"]["sd"] > MARGIN))
        if sum(1 for d in DISPOSITIONS if d == r["disposition"]) != 1:
            raise RuntimeError(f"{r.get('part')} {c}: not exactly one disposition")
    return fam


def _resolve(key: str, variant: str) -> str:
    if key == PITCH:
        return variant
    if key == PITCH_B:
        return pb_key(variant)
    if key == PEP:
        return "pep_" + variant
    return key


def _cell_frames(frames_name: str, key: str, pairs: Mapping[str, list]) -> list[tuple]:
    if frames_name == "S3t":
        return [(sysname, pairs[comp], key) for sysname, comp, _cfg in S3T_SYSTEMS]
    return [(frames_name, pairs[frames_name], key)]


def primary_families() -> dict:
    """The families scored: S3t's cells only while S3t is eligible (11.5.2, 11.7)."""
    out = {}
    for part, cells in PRIMARY_FAMILIES.items():
        out[part] = {c: v for c, v in cells.items() if S3T_ELIGIBLE or v[0] != "S3t"}
    return out


def build_all_pairs(rows: dict, seasons: tuple, consts: Mapping) -> dict:
    return {comp: component_pairs(rows, comp, seasons, consts) for comp in COMPONENTS}


def score_primary(rows: dict, consts: Mapping, seasons: tuple, boot: int, log: Callable,
                  hr_choice: Optional[dict] = None, label: str = "look") -> dict:
    pairs = build_all_pairs(rows, seasons, consts)
    early = {c: component_pairs(rows, c, TRANSPORT_EARLY_SEASONS, consts) for c in ("pit", "pep")}
    _p(log, f"[{label}] PRIMARY frame (part 11.2): " + ", ".join(f"{c} {len(v)}" for c, v in pairs.items())
            + f"; 2016 to 2018 block: pit {len(early['pit'])}, pep {len(early['pep'])}")
    fams = primary_families()
    recs: dict = {}
    for i, (part, cells) in enumerate(fams.items()):
        for j, (cell, (fname, key, kind)) in enumerate(cells.items()):
            k_b1 = B1_K_AMENDED[B1_COMPONENT[fname]]
            keys = [_resolve(key, v) for v in swar.HR_VARIANTS] if key in (PITCH, PITCH_B, PEP) else [key]
            for kk in keys:
                recs[(part, cell, kk)] = prep_primary(part, cell, _cell_frames(fname, kk, pairs), kind, k_b1,
                                                      boot, SEED, SEED + 101 * (i + 1) + 7 * j)
    _p(log, f"[{label}] FLOORS, primary (convention v2, B = {boot}; MDE95 = 1.645 sd; no gap is printed here)")
    floors = {}
    for (part, cell, kk), rec in recs.items():
        f = rec.get("floors") or {}
        floors[f"{part}|{cell}|{kk}"] = _rd(f, 5)
        unreach = f.get("mde95") is not None and f["mde95"] > MARGIN
        _p(log, f"  {part:9s} {cell:12s} {kk:16s} n {rec['n_pairs']:5d}  sd {_fmt(f.get('sd'))}  "
                f"half-width {_fmt(f.get('half_width95'))}  MDE95 {_fmt(f.get('mde95'))}"
                + ("  EQUIVALENT unreachable (MDE95 > 0.02)" if unreach else ""))

    k_pit = B1_K_AMENDED["pit"]
    if hr_choice is None:
        g_early = point_gap_frames([("pitching", early["pit"], swar.HR_SHRUNK)], RATE, k_pit, key_b=swar.HR_FWAR)
        g_late = point_gap_frames([("pitching", pairs["pit"], swar.HR_SHRUNK)], RATE, k_pit, key_b=swar.HR_FWAR)
        hr_choice = hr_arm_clause(g_early, g_late)
        hr_choice["target"] = "RA9* in Y+1 (11.2.1), B0 the actual arm of S2"
        _p(log, f"[{label}] HR-ARM CLAUSE (primary target): P-rate gap hr_shrunk over hr_fwar, 2016-2018 "
                f"{_fmt(g_early)}, 2021-2024 {_fmt(g_late)}: "
                f"{'holds' if hr_choice['holds'] else 'fails'}; home-run term {hr_choice['variant']}")
    else:
        _p(log, f"[{label}] home-run term carried from the look: {hr_choice['variant']}")
    variant = hr_choice["variant"]

    cells: dict = {}
    for part, spec in fams.items():
        fam = {}
        for cell, (fname, key, kind) in spec.items():
            rec = finish_primary(recs[(part, cell, _resolve(key, variant))])
            if part in TRANSPORT_PARTS and kind == RATE:
                comp = "pep" if part == PART_PE_P else "pit"
                ge = point_gap_frames([(part, early[comp], _resolve(key, variant))], RATE,
                                      B1_K_AMENDED[B1_COMPONENT[fname]])
                rec["transport_gap_2016_2018"] = ge
                rec["transport"] = transport_holds(ge, rec.get("gap"))
            fam[cell] = rec
        if part in TRANSPORT_PARTS:
            for c, r in fam.items():
                if r["kind"] == CUM:
                    rate = c.replace("P-cum", "P-rate").replace("PE-P total", "PE-P rate")
                    r["transport"] = fam.get(rate, {}).get("transport")
        cells[part] = decide_family(fam)

    # PE-H's sensitivity guard (11.4.4): the rate cell on wRAA(Y+1) alone, the same bootstrap
    sens_pairs = [dict(p, tgt=p["tgt_alt"]) for p in pairs["peh"] if p.get("tgt_alt") is not None]
    srec = finish_primary(prep_primary(PART_PE_H, "PE-H rate on wRAA alone", [("pe_h", sens_pairs, "peh")],
                                       RATE, B1_K_AMENDED["peh"], boot, SEED, SEED + 101 * 5))
    sens = {"n_pairs": srec.get("n_pairs"), "gap": srec.get("gap"), "lo95": srec.get("lo95"),
            "hi95": srec.get("hi95"), "loss": bool(_lt(srec.get("hi95"), 0.0)),
            "rule": "the PE-H rate cell's gap on wRAA(Y+1) alone, W left out, must not be LOSS (hi95 below 0)"}

    _p(log, f"[{label}] GAPS AND DISPOSITIONS, primary (convention v2 against B0; v1 must agree in sign)")
    for part, fam in cells.items():
        for c, r in fam.items():
            _p(log, f"  {part:9s} {c:12s} n {r['n_pairs']:5d} gap {_fmt(r.get('gap'))} "
                    f"[{_fmt(r.get('lo95'))}, {_fmt(r.get('hi95'))}] 90% [{_fmt(r.get('lo90'))}, "
                    f"{_fmt(r.get('hi90'))}] p {_fmt(r.get('p_one_sided'))} holm {r['holm_reject']} "
                    f"| vs B1 lo95 {_fmt(r.get('b1_lo95'))} | twin lo95 {_fmt(r.get('twin_lo95'))} "
                    f"| v1 {_fmt(r.get('v1_gap'))} | B0r gap {_fmt((r.get('b0r') or {}).get('gap_over_b0r'))} "
                    f"=> {r['disposition']}")
    _p(log, f"  pe_h sensitivity (wRAA alone): gap {_fmt(sens['gap'])} hi95 {_fmt(sens['hi95'])} "
            f"loss {sens['loss']}")
    return {"pairs": pairs, "early": early, "hr": hr_choice, "variant": variant, "cells": cells,
            "floors": floors, "sensitivity": sens}


# ---- the team guard (11.2.4)

#: Each guarded series: (side, how the series reads a row, the outcomes it carries).
GUARD_SERIES = {
    "pos": (HIT, "pos", T.OUTCOMES_FIELD), "bat": (HIT, "bat", T.OUTCOMES_HIT),
    "batx": (HIT, "batx", T.OUTCOMES_HIT), "fld": (HIT, "fld", T.OUTCOMES_FIELD),
    "fldt": (HIT, "fldt_FULL", T.OUTCOMES_FIELD), "cat": (HIT, "cat", T.OUTCOMES_FIELD),
    "peh": (HIT, "peh", T.OUTCOMES_HIT),
    "S2": (PIT, PITCH, T.OUTCOMES_PIT), "S2b": (PIT, PITCH_B, T.OUTCOMES_PIT),
    "pep": (PIT, PEP, T.OUTCOMES_PIT),
}


def _series_value(side: str, how: str, r: Mapping, variant: str) -> Optional[float]:
    """The series value v_i(Y) of one row: fWAR plus the part's departure in wins."""
    fw = r.get("fwar")
    if fw is None:
        return None
    if side == HIT:
        d = (r.get("d") or {}).get(how)
        rpw = r.get("rpw")
        return fw if (d is None or not rpw) else fw + d / rpw
    if how == PEP:
        dp, rpw = (r.get("d_pe") or {}).get(variant), r.get("rpw")
        return fw if (dp is None or not rpw) else fw + dp / rpw
    d = (r.get("delta") or {}).get(_resolve(how, variant))
    return fw if d is None else fw + d


def team_guards(rows: dict, seasons: tuple, variant: str, team_exp: Mapping, standings: Mapping,
                bwar: Mapping, which: Iterable[str], boot: int, log: Callable, label: str) -> dict:
    """The guard of every named series on the club-seasons Y+1 of `seasons`."""
    ys = [int(y) for y in seasons if int(y) != EXCLUDED_SEASON and int(y) + 1 != EXCLUDED_SEASON]
    clubs = sorted({(y + 1, t) for y in ys for t in (standings.get(y + 1) or {})})
    if not clubs:
        raise RuntimeError("the team guard has no club-season with standings")
    outcomes = {
        "runs_scored": np.array([_num((standings[s][t]).get("rs")) or np.nan for s, t in clubs], float),
        "runs_allowed": np.array([-(_num((standings[s][t]).get("ra")) or np.nan) for s, t in clubs], float),
        "run_differential": np.array([(_num(standings[s][t].get("rs")) or np.nan)
                                      - (_num(standings[s][t].get("ra")) or np.nan) for s, t in clubs], float),
        "wins": np.array([float(standings[s][t]["w"]) for s, t in clubs], float),
    }
    players = sorted({m for y in ys for side in (HIT, PIT) for m in ((rows.get(y) or {}).get(side) or {})})
    nxt = {side: {(s, m): e for (sd, s, m), e in team_exp.items() if sd == side} for side in (HIT, PIT)}

    def mat(side: str, value_of) -> np.ndarray:
        vals, expo = {}, {}
        for y in ys:
            for m, r in ((rows.get(y) or {}).get(side) or {}).items():
                vals[(y, m)] = value_of(m, y, r)
                expo[(y, m)] = r.get(EXPOSURE[side])
        return T.roster_matrix(vals, expo, nxt[side], players, clubs)

    bkey = {HIT: "bat", PIT: "pit"}
    base = {side: {"frame": mat(side, lambda m, y, r: r.get("fwar")),
                   "ref": mat(side, lambda m, y, r, s=side: (bwar.get((m, y)) or {}).get(bkey[s]))}
            for side in (HIT, PIT)}
    out = {}
    for name in which:
        side, how, carried = GUARD_SERIES[name]
        part_m = mat(side, lambda m, y, r, s=side, h=how: _series_value(s, h, r, variant))
        mats = {s: {"frame": base[s]["frame"], "ref": base[s]["ref"],
                    "part": (part_m if s == side else base[s]["frame"])} for s in (HIT, PIT)}
        out[name] = T.team_guard(mats, outcomes, carried, clubs, boot=boot, seed=T.GUARD_SEED)
    _p(log, f"[{label}] TEAM GUARD FLOORS (11.2.4; B = {boot} each, seed {T.GUARD_SEED}; no dT is printed here)")
    for name, g in out.items():
        for oname, legs in T.guard_floors(g).items():
            _p(log, f"  {name:5s} {oname:16s} player sd {_fmt(legs['player']['sd'])} half-width "
                    f"{_fmt(legs['player']['half_width95'])} | club sd {_fmt(legs['club']['sd'])} half-width "
                    f"{_fmt(legs['club']['half_width95'])}")
    _p(log, f"[{label}] TEAM GUARD dT (part r minus frame r; NON-INFERIOR when dT - 1.645 sd > -0.02 under both)")
    for name, g in out.items():
        for oname, o in g["outcomes"].items():
            _p(log, f"  {name:5s} {oname:16s} n {o['n_club_seasons']:4d} dT {_fmt(o['dT'])} lower player "
                    f"{_fmt(o['player'].get('lower'))} club {_fmt(o['club'].get('lower'))} => "
                    f"{'NON-INFERIOR' if o['non_inferior'] else 'not non-inferior'}")
        _p(log, f"  {name:5s} guard: {'NON-INFERIOR' if g['non_inferior'] else 'NOT NON-INFERIOR'}"
                + (" (underpowered: a half-width above 0.02)" if g.get("underpowered") else ""))
    return out


# ---- admission, amended (11.2.6, 11.3.5, 11.4.5, 11.5.3, 11.6.3)

def _guard_ok(guards: Mapping, name: str) -> bool:
    return bool((guards.get(name) or {}).get("non_inferior"))


def arm_qualifies(cells: Mapping, rate: str, cum: str, guard_ok: bool, q1: str, extra_ok: bool = True) -> bool:
    """11.2.6: the rate cell WIN (components) (EWV3-Q1 (a)), the total cell not
    LOSS, the team guard NON-INFERIOR (and a part's own extra guard)."""
    return qualifies(_disp_of(cells, rate), _disp_of(cells, cum), q1) and guard_ok and extra_ok


def admit_amended(part: str, cells: Mapping, guards: Mapping, answers: Mapping,
                  extras: Optional[Mapping] = None) -> dict:
    """Whether a candidate part enters eWAR v3 on the primary target. `extras`
    carries "contrast" ({"lo95"}) when two arms qualify, "sensitivity" for PE-H
    and "ladder" for the position part. Returns {"part", "admitted", "arm",
    "needs_contrast", "reason"} (and "catcher_component" for fielding)."""
    extras = extras or {}
    out = {"part": part, "admitted": False, "arm": None, "needs_contrast": False, "reason": ""}
    if answers.get("void"):
        out["reason"] = "VOID run: nothing is admitted"
        if part == PART_FIELDING:
            out["catcher_component"] = {"admitted": False, "reason": out["reason"]}
        return out
    q1 = answers.get("EWV3-Q1", ANSWERS["EWV3-Q1"])
    if part == PART_POSITION:
        lad = extras.get("ladder") or {}
        ok = bool(lad.get("passes")) and _guard_ok(guards, "pos")
        out.update(admitted=ok, reason=(f"dMAE lo95 {lad.get('lo95')!r}, control fails "
                                        f"{lad.get('control_fails')!r}, guard {_guard_ok(guards, 'pos')}"))
        return out
    if part in (PART_PE_P, PART_PE_H):
        r, c = list(PRIMARY_FAMILIES[part])
        gname = "pep" if part == PART_PE_P else "peh"
        extra = True if part == PART_PE_P else not bool((extras.get("sensitivity") or {}).get("loss", True))
        ok = arm_qualifies(cells, r, c, _guard_ok(guards, gname), q1, extra)
        out.update(admitted=ok, reason=f"{r} {_disp_of(cells, r)}, {c} {_disp_of(cells, c)}, guard "
                                       f"{_guard_ok(guards, gname)}" + ("" if part == PART_PE_P
                                                                        else f", sensitivity not LOSS {extra}"))
        return out
    if part == PART_BATTING:
        arms = {"HEM+": ("HEM+ H-rate", "HEM+ H-cum", "bat"), "xHEM+": ("xHEM+ H-rate", "xHEM+ H-cum", "batx")}
        first, second = "HEM+", "xHEM+"
    elif part == PART_PITCHING:
        arms = {"S2": ("P-rate", "P-cum", "S2"), "S2b": ("S2b P-rate", "S2b P-cum", "S2b")}
        first, second = "S2", "S2b"
    elif part == PART_FIELDING:
        arms = {a: v for a, v in FIELDING_ARMS.items() if a == "S3" or (S3T_ELIGIBLE and v[0] in cells)}
        first, second = "S3", "S3t"
        r, c, g = CATCHER_CELLS
        cat_ok = arm_qualifies(cells, r, c, _guard_ok(guards, g), q1)
        out["catcher_component"] = {"admitted": cat_ok, "reason": (f"{r} {_disp_of(cells, r)}, {c} "
                                                                   f"{_disp_of(cells, c)}, guard {_guard_ok(guards, g)}")}
    else:
        raise ValueError(f"unknown candidate part {part!r}")
    quals = {a: arm_qualifies(cells, rc, cc, _guard_ok(guards, g), q1) for a, (rc, cc, g) in arms.items()}
    desc = "; ".join(f"{a}: {rc} {_disp_of(cells, rc)}, {cc} {_disp_of(cells, cc)}, guard {_guard_ok(guards, g)}"
                     for a, (rc, cc, g) in arms.items())
    if not any(quals.values()):
        out["reason"] = f"no arm qualifies ({desc})"
        return out
    if sum(quals.values()) == 1:
        arm = next(a for a, q in quals.items() if q)
        out.update(admitted=True, arm=arm, reason=f"only the {arm} arm qualifies ({desc})")
        return out
    if part == PART_BATTING and answers.get("EWV3-Q2", ANSWERS["EWV3-Q2"]) != "a":
        q2 = answers["EWV3-Q2"]
        if q2 == "c":
            out.update(admitted=True, arm="xHEM+", reason="both qualify; EWV3-Q2 (c): xHEM+")
            return out
        gh, gx = _gap_of(cells, "HEM+ H-rate"), _gap_of(cells, "xHEM+ H-rate")
        out.update(admitted=True, arm=("xHEM+" if (gx or 0) > (gh or 0) else "HEM+"),
                   reason="both qualify; EWV3-Q2 (b): the larger point gap against B0")
        return out
    contrast = extras.get("contrast")
    if not contrast:
        out.update(needs_contrast=True, reason=f"both arms qualify; the {second}-over-{first} contrast decides")
        return out
    lo = contrast.get("lo95")
    arm = second if (lo is not None and lo > 0.0) else first
    out.update(admitted=True, arm=arm, reason=(f"both qualify; contrast lo95 {lo!r} "
                                               f"{'above' if arm == second else 'not above'} 0"))
    return out


def admissions_amended(blk: dict, guards: Mapping, ladder: Mapping, boot: int, answers: Mapping,
                       log: Callable) -> dict:
    out = {}
    variant = blk["variant"]
    for part in PRIMARY_PARTS + (PART_POSITION,):
        cells = blk["cells"].get(part, {})
        extras = {"ladder": ladder, "sensitivity": blk.get("sensitivity")}
        a = admit_amended(part, cells, guards, answers, extras)
        if a["needs_contrast"]:
            if part == PART_BATTING:
                c = contrast_frames([("batting", blk["pairs"]["bat"], "batx")], "bat", boot, SEED + 9001,
                                    B1_K_AMENDED["bat"])
                what = "xHEM+ over HEM+"
            elif part == PART_PITCHING:
                c = contrast_frames([("pitching", blk["pairs"]["pit"], pb_key(variant))], variant, boot,
                                    SEED + 9002, B1_K_AMENDED["pit"])
                what = "S2b over S2"
            else:
                c = contrast_frames([(s, blk["pairs"][comp], "fldt") for s, comp, _c in S3T_SYSTEMS], "fld",
                                    boot, SEED + 9003, B1_K_AMENDED["fld"])
                what = "S3t over S3, on S3t's systems"
            _p(log, f"  {part} contrast ({what}, rate, primary target, outside Holm): gap "
                    f"{_fmt(c['gap'])} lo95 {_fmt(c['lo95'])}")
            a = admit_amended(part, cells, guards, answers, dict(extras, contrast=c))
            a["contrast"] = _rd(c, 5)
        out[part] = a
        _p(log, f"  ADMIT {part:9s}: {a['admitted']}" + (f" arm {a['arm']}" if a["arm"] else "")
                + f" ({a['reason']})"
                + (f"; catcher component {a['catcher_component']['admitted']}" if "catcher_component" in a else ""))
    return out


def amended_sentences(cells: Mapping, adm: Mapping, ladder: Mapping, mode: str) -> dict:
    """The one sentence per part (11.2.6), on the admitted arm's rate cell (else
    the first arm's), and S3c's on its own; the position part on a pass only."""
    seasons = PREDICTOR_SEASONS if mode == "look" else HOLDOUT_SEASONS
    rate_of = {PART_BATTING: {"HEM+": ("HEM+ H-rate", "bat"), "xHEM+": ("xHEM+ H-rate", "bat")},
               PART_PITCHING: {"S2": ("P-rate", "pit"), "S2b": ("S2b P-rate", "pit")},
               PART_FIELDING: {"S3": ("H-rate", "fld"), "S3t": ("S3t H-rate", "fldt")},
               PART_PE_P: {None: ("PE-P rate", "pep")}, PART_PE_H: {None: ("PE-H rate", "peh")}}
    out = {}
    for part, arms in rate_of.items():
        a = (adm.get(part) or {}).get("arm")
        cell, comp = arms.get(a) or next(iter(arms.values()))
        r = (cells.get(part) or {}).get(cell)
        out[part] = (None if not r else amended_sentence(comp, r["disposition"], r.get("gap"), r.get("lo95"),
                                                         r.get("hi95"), r.get("n_pairs"), seasons))
    rc = (cells.get(PART_FIELDING) or {}).get(CATCHER_CELLS[0])
    out["fielding_catcher_component"] = (None if not rc else amended_sentence(
        "cat", rc["disposition"], rc.get("gap"), rc.get("lo95"), rc.get("hi95"), rc.get("n_pairs"), seasons))
    out[PART_POSITION] = POSITION_SENTENCE if (ladder or {}).get("passes") else None
    return out


# ---- reported beside the primary cells (no weight)

def primary_beside(blk: dict, rows: dict, seasons: tuple) -> dict:
    variant, pairs = blk["variant"], blk["pairs"]
    k = B1_K_AMENDED

    def sub(ps, keep):
        return [p for p in ps if keep(p.get("sigma"))]
    starter = lambda s: s is not None and s >= 0.5  # noqa: E731
    reliever = lambda s: s is not None and s <= 0.10  # noqa: E731
    out = {"label": DESCRIPTIVE}
    out["pitching_subsets"] = {
        lab: {"n_pairs": len(sub(pairs["pit"], f)),
              "s2_p_rate_gap": _r(point_gap_frames([("p", sub(pairs["pit"], f), variant)], RATE, k["pit"])),
              "s2b_p_rate_gap": _r(point_gap_frames([("p", sub(pairs["pit"], f), pb_key(variant))], RATE, k["pit"])),
              "pe_p_rate_gap": _r(point_gap_frames([("p", sub(pairs["pep"], f), "pep_" + variant)], RATE, k["pep"]))}
        for lab, f in (("starter_heavy_sigma_ge_0_5", starter), ("reliever_sigma_le_0_10", reliever))}
    out["pe_p_on_the_pitching_target"] = {
        "rate_gap": _r(point_gap_frames([("p", pairs["pit"], "pep_" + variant)], RATE, k["pit"])),
        "total_gap": _r(point_gap_frames([("p", pairs["pit"], "pep_" + variant)], CUM, k["pit"]))}
    out["pe_h_terms_one_at_a_time"] = {
        t: {"rate_gap": _r(point_gap_frames([("h", pairs["peh"], t)], RATE, k["peh"])),
            "total_gap": _r(point_gap_frames([("h", pairs["peh"], t)], CUM, k["peh"]))}
        for t in ("peh_cl", "peh_p")}
    # S3t's catcher rows on DRS at C in Y+1 (11.5.2), and S3c's per-inning form (11.6.2)
    crow = [dict(p, tgt=p["c_drs1"]) for p in pairs["fld"]
            if p.get("c_drs1") is not None and (rows.get(p["y"]) or {}).get(HIT, {}).get(p["mlbam"], {}).get("c_inn", 0.0)
            >= T.CATCHER_MIN_INN]
    out["s3t_catcher_rows_on_drs_at_c"] = {"n_pairs": len(crow),
                                           "rate_gap": _r(point_gap_frames([("c", crow, "fldt")], RATE, k["fld"]))}
    sc_y, bc_y, drs_n = [], [], []
    for y in seasons:
        y = int(y)
        a, b = (rows.get(y) or {}).get(HIT) or {}, (rows.get(y + 1) or {}).get(HIT) or {}
        for m, r0 in a.items():
            r1 = b.get(m)
            if r1 is None or r0.get("c_inn", 0.0) < T.CATCHER_MIN_INN or r1.get("c_inn", 0.0) < T.CATCHER_MIN_INN:
                continue
            c1 = (r1.get("fg") or {}).get("c_drs")
            if c1 is None:
                continue
            sc, b0 = r0.get("sc"), r0.get("fld_b0")
            if sc is None or b0 is None:
                continue
            sc_y.append(sc / r0["c_inn"])
            bc_y.append((b0 - float(r0.get("nonc_frp") or 0.0)) / r0["c_inn"])
            drs_n.append(c1 / r1["c_inn"])
    out["s3c_per_inning_form"] = {"n_pairs": len(sc_y), "rho_sc_side": _r(spearman(sc_y, drs_n)),
                                  "rho_bc": _r(spearman(bc_y, drs_n)),
                                  "note": "SC and BC per inning at C in Y on DRS per inning at C in Y+1"}
    sizes = {}
    for name, side, get in (("d_fldt_full", HIT, lambda r: (r.get("d") or {}).get("fldt_FULL")),
                            ("d_cat", HIT, lambda r: (r.get("d") or {}).get("cat")),
                            ("d_peh", HIT, lambda r: (r.get("d") or {}).get("peh")),
                            ("delta_pe", PIT, lambda r: (r.get("d_pe") or {}).get(variant))):
        per = {}
        for y in seasons:
            rs = (rows.get(int(y)) or {}).get(side) or {}
            v = np.array([get(r) / r["rpw"] for r in rs.values() if get(r) is not None and r.get("rpw")], float)
            if len(v) < 2:
                per[str(y)] = None
                continue
            top = sorted(((get(r) / r["rpw"], m, r.get("name", "")) for m, r in rs.items()
                          if get(r) is not None and r.get("rpw")), key=lambda t: -abs(t[0]))[:5]
            per[str(y)] = {"n": int(len(v)), "sd_war": _r(np.std(v, ddof=1)), "max_abs_war": _r(np.max(np.abs(v))),
                           "share_ge_0_1": _r(np.mean(np.abs(v) >= 0.1)), "share_ge_0_5": _r(np.mean(np.abs(v) >= 0.5)),
                           "share_ge_1_0": _r(np.mean(np.abs(v) >= 1.0)),
                           "top_movers": [{"mlbam": m, "name": nm, "delta_war": _r(d, 3)} for d, m, nm in top]}
        sizes[name] = per
    out["delta_sizes"] = sizes
    return out


def _jsonable(o):
    """numpy scalars to Python, NaN and infinities to None, before the record is written."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if math.isfinite(f) else None
    return o


AMENDED_PREVIEW_KEYS = ("bat.wraa", "fld.b0", "war0", "ra9_star")


def check_amended_preview(payload: dict) -> None:
    """The preview carries part 11.2.1's bases (tools/build_swar.py since
    EWV3_LAB_AMENDED_TARGETS); an older swar/2 preview is refused."""
    for blk in (payload.get("seasons") or {}).values():
        h = next(iter(blk.get("hitters") or []), None)
        q = next(iter(blk.get("pitchers") or []), None)
        if h is None or q is None:
            continue
        parts = h.get("parts") or {}
        if "wraa" not in (parts.get("bat") or {}) or "b0" not in (parts.get("fld") or {}) \
                or "war0" not in q or "ra9_star" not in q:
            raise LabStop("the preview lacks part 11.2.1's bases (bat.wraa, fld.b0, war0, ra9_star): "
                          "rebuild it with python tools/build_swar.py")
        return


def secondary_tests(rows: dict) -> None:
    """The secondary estimand's test values of the parts registered after 11.2
    (fWAR + d / RPW, fWAR + Delta_PE / RPW), beside the preview's own."""
    for blk in rows.values():
        for r in blk[HIT].values():
            fw, rpw, d = r.get("fwar"), r.get("rpw"), r.get("d") or {}
            for key, dk in (("fldt", "fldt_FULL"), ("cat", "cat"), ("peh", "peh")):
                r["tests"][key] = (None if fw is None or not rpw or d.get(dk) is None
                                   else fw + d[dk] / rpw)
        for r in blk[PIT].values():
            fw, rpw = r.get("fwar"), r.get("rpw")
            for v in swar.HR_VARIANTS:
                dp = (r.get("d_pe") or {}).get(v)
                r["tests"]["pep_" + v] = None if fw is None or not rpw or dp is None else fw + dp / rpw


def run(mode: str, inputs: LabInputs, out_path: Path, boot: int = BOOT, log: Callable = print,
        today: Optional[_dt.date] = None, fail_after_scoring: bool = False) -> dict:
    """mode 'look' or 'holdout'. Raises LabStop before scoring began (nothing
    written; every input is read and assembled before then); after scoring
    began, any exception writes a VOID record."""
    today = today or _dt.date.today()
    out_path = Path(out_path)
    _refuse_out(out_path)
    existing = None
    if mode == "look":
        if out_path.exists():
            raise LabStop(f"the record exists ({out_path}): a second look is forbidden")
        need = list(range(2016, 2026))
        block_seasons = PREDICTOR_SEASONS
    elif mode == "holdout":
        if not out_path.exists():
            raise LabStop(f"no look record at {out_path}: the holdout runs after the look")
        existing = json.loads(out_path.read_text(encoding="ascii"))
        if existing.get("status") == "VOID":
            raise LabStop("the skill look is VOID: the holdout does not run (part 7.4)")
        if existing.get("holdout") is not None:
            raise LabStop("the holdout block exists: a second holdout is forbidden")
        need = list(range(2016, 2020)) + [HOLDOUT_SEASONS[0], HOLDOUT_SEASONS[0] + 1]
        block_seasons = HOLDOUT_SEASONS
    else:
        raise ValueError(mode)
    payload = inputs.preview()
    check_preview(payload, need, inputs.vintage_id())
    check_amended_preview(payload)
    rows = season_rows(payload)
    _p(log, f"swar_lab {LAB_VERSION} {mode} on {today.isoformat()}: preview vintage "
            f"{payload.get('fwar_vintage_id')}, generated {payload.get('generated_at')}; "
            f"B1 (primary) k {json.dumps(B1_K_AMENDED, sort_keys=True)}; B1 (secondary) k hit "
            f"{B1_K['hit']:g} PA, pit {B1_K['pit']:g} IP; seed {SEED}, B {boot}")
    # -- every input, read and assembled before scoring begins (a failure here is a STOP)
    peh_seasons = sorted({int(y) for y in block_seasons} | {int(y) + 1 for y in block_seasons})
    consts = assemble(rows, inputs, need, peh_seasons, log)
    secondary_tests(rows)
    team_exp = inputs.team_exposure()
    standings = inputs.standings(range(min(block_seasons), max(block_seasons) + 2))
    bwar = inputs.bwar()
    ev, ve, standing = inputs.ladder_records()
    ladder = T.ladder_test(ev, ve, standing)
    systems = T.system_table(range(min(need), max(need) + 1))
    s3_target = {str(y): T.fielding_target("fld", y) for y in range(min(need), max(need) + 1)}
    _p(log, f"inputs (sha256, read only, never fetched): {json.dumps(inputs.input_meta(), sort_keys=True)}")
    _p(log, "fielding systems by source (11.2.2), every season " + f"{min(need)} to {max(need)}: "
            + "; ".join(f"{s}: {v[0]}" for s, v in T.FIELDING_SOURCES.items())
            + f"; S3's target {sorted(set(s3_target.values()))}; S3t's DRS, Statcast and UZR (UZR to {T.UZR_LAST})"
            + "; S3c's DRS; S3t eligible " + str(S3T_ELIGIBLE) + " (owner decision EW3-37, EBR_GATE.md 11.7)")
    started = {"scoring": False}
    try:
        started["scoring"] = True
        hr_given = None if mode == "look" else existing.get("hr_arm_clause")
        prim = score_primary(rows, consts, block_seasons, boot, log, hr_choice=hr_given, label=mode)
        if fail_after_scoring:
            raise RuntimeError("injected failure after scoring began (dry run)")
        _p(log, f"[{mode}] POSITION PART (11.2.3): ladder {ladder.get('standing_ladder')} against FanGraphs' "
                f"positional adjustment ({ladder.get('comparator')}): dMAE in the ladder's favour "
                f"{_fmt(ladder.get('dmae_ladder_favour'))} [{_fmt(ladder.get('lo95'))}, {_fmt(ladder.get('hi95'))}]"
                f"; control fails {ladder.get('control_fails')}; passes {ladder.get('passes')}")
        which = [k for k in GUARD_SERIES if S3T_ELIGIBLE or k != "fldt"]
        guards = team_guards(rows, block_seasons, prim["variant"], team_exp, standings, bwar, which, boot,
                             log, mode)
        _p(log, f"[{mode}] ADMISSION (part 11.2.6; EWV3-Q1 ({ANSWERS['EWV3-Q1']}), EWV3-Q2 ({ANSWERS['EWV3-Q2']}),"
                f" PB-Q1 ({PITCHING_ARM_RULE}))"
                + (" reported only: the holdout changes no admission" if mode == "holdout" else ""))
        adm = admissions_amended(prim, guards, ladder, boot, dict(ANSWERS, void=False), log)
        beside = primary_beside(prim, rows, block_seasons)
        _p(log, f"[{mode}] SECONDARY ESTIMAND (11.2.5): published fWAR(Y+1), B1 at a32ff1bb's constants; "
                "decides nothing")
        sec = score_block(rows, block_seasons, boot, log, hr_choice=prim["hr"], label=f"{mode} secondary",
                          spec=secondary_cells())
        block = {
            "estimand": "primary: next-season realized runs of each part's own component (EBR_GATE.md 11.2.1)",
            "seasons": list(block_seasons),
            "n_pairs": {c: len(v) for c, v in prim["pairs"].items()},
            "fielding_systems": {"by_season": systems, "s3_target_by_season": s3_target},
            "s3t_eligible": {"eligible": S3T_ELIGIBLE, "by": "owner decision EW3-37 (EBR_GATE.md 11.7)"},
            "b1": {"k": dict(B1_K_AMENDED), "fit": B1_AMENDED_FIT_LOG},
            "floors_first": prim["floors"],
            "hr_arm_clause": _rd(prim["hr"], 5),
            "cells": {part: {c: _public(r) for c, r in fam.items()} for part, fam in prim["cells"].items()},
            "pe_h_sensitivity": _rd(prim["sensitivity"], 5),
            "position_ladder": ladder,
            "team_guard": guards,
            "admission": adm,
            "sentences": amended_sentences(prim["cells"], adm, ladder, mode),
            "reported_beside": beside,
            "secondary": {"label": ("secondary estimand (11.2.5): part 9.5's cells as first registered, "
                                    "published fWAR(Y+1), B1 at the constants frozen at a32ff1bb; "
                                    "decides nothing"),
                          "home_run_term": prim["variant"], "floors_first": sec["floors"],
                          "cells": {part: {c: _public(r) for c, r in fam.items()}
                                    for part, fam in sec["cells"].items()}},
        }
        _p(log, f"[{mode}] DESCRIPTIVE LEGS ({DESCRIPTIVE})")
        dseasons = list(block_seasons)
        desc = {
            "label": DESCRIPTIVE,
            "delta_sizes": leg_delta_sizes(rows, dseasons, prim["variant"]),
            "agreement": leg_agreement(rows, dseasons, prim["variant"], bwar),
            "self_persistence": leg_self_persistence(sec["pairs_h"], sec["pairs_p"], rows, prim["variant"]),
            "exposure_band_bias": leg_exposure_bias(rows, dseasons, prim["variant"]),
            "pitching_subsets": leg_pitching_subsets(sec["pairs_p"], prim["variant"]),
            "leverage_lb_disclosure": leg_leverage_lb(rows, dseasons, prim["variant"]),
            "coverage_census": leg_census(payload),
        }
        if mode == "look":
            desc["team_wins"] = leg_team_wins(rows, dseasons, prim["variant"], inputs.team_shares(), standings)
            cal_seasons = [y for y in range(2016, 2026) if y != EXCLUDED_SEASON]
            desc["split_half_calibration"] = leg_split_half(inputs, cal_seasons)
        block["descriptive"] = desc
        for k in ("agreement", "self_persistence", "pitching_subsets"):
            _p(log, f"  {k}: {json.dumps(_jsonable(desc[k]), sort_keys=True)}")
        if "team_wins" in desc:
            _p(log, f"  team_wins: {json.dumps(_jsonable(desc['team_wins']), sort_keys=True)}")
    except Exception:
        if not started["scoring"]:
            raise
        tb = traceback.format_exc()
        _p(log, "VOID: an exception after scoring began; no rerun; an owner question follows")
        _p(log, tb)
        void = {"schema": LAB_VERSION, "status": "VOID", "mode": mode, "date": today.isoformat(),
                "registration": REGISTRATION,
                "admission": {p: admit_amended(p, {}, {}, {"void": True}) for p in PRIMARY_PARTS + (PART_POSITION,)},
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
            "inputs": inputs.input_meta(),
            "params": {"seed": SEED, "boot": boot, "margin": MARGIN, "alpha": ALPHA, "mde_z": MDE_Z,
                       "floors": {"hit_pa": MIN_PA, "pit_ip": MIN_IP, "catcher_inn_c": T.CATCHER_MIN_INN},
                       "predictor_seasons": list(PREDICTOR_SEASONS),
                       "transport_early_seasons": list(TRANSPORT_EARLY_SEASONS),
                       "holdout_seasons": list(HOLDOUT_SEASONS),
                       "b1_k_primary": dict(B1_K_AMENDED), "b1_fit_primary": B1_AMENDED_FIT_LOG,
                       "b1_k_secondary": dict(B1_K), "b1_fit_secondary": B1_FIT_LOG,
                       "team_guard": {"boot": T.GUARD_BOOT if boot == BOOT else boot, "seed": T.GUARD_SEED,
                                      "z": T.GUARD_Z, "margin": T.GUARD_MARGIN},
                       "answers": dict(ANSWERS), "pb_q1": PITCHING_ARM_RULE,
                       "primary_convention": "v2", "intervals": "bootstrap percentile",
                       "p_one_sided": "(1 + #{gap draws <= 0}) / (1 + draws)"}}
    if mode == "look":
        record = dict(meta, status="SCORED", mode="look", hr_arm_clause=block["hr_arm_clause"],
                      look=block, holdout=None)
    else:
        record = existing
        record["holdout"] = dict(meta, status="SCORED", mode="holdout", block=block,
                                 note="reported beside the verdict, never merged into it; changes no admission")
    write_record(_jsonable(record), out_path)
    _p(log, f"wrote {out_path}")
    return record


# --------------------------------------------------------------------------
# the dry run: synthetic fixtures with nulls, a temporary directory only
# --------------------------------------------------------------------------

class FixtureLabInputs(LabInputs):
    """A synthetic league, 2016 to 2026: each player a fixed talent per
    component (batting, fielding, pitching), every season's realized values
    that talent plus noise, the batting and pitching deltas pulling toward the
    talent, the position and other deltas pure noise, and nulls on purpose (a
    missing test value, a missing fWAR, an xHEM+ arm absent in the holdout
    season, a missing Baseball-Reference fielding row, a pitcher with no RA9*,
    a season of the play-by-play corpus absent, UZR absent after 2024, a
    club-season with no standings)."""

    CORPUS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)

    def __init__(self, seed: int = 7, n_hit: int = 260, n_pit: int = 180):
        self.rng = np.random.default_rng(seed)
        self.n_hit, self.n_pit = n_hit, n_pit
        self._fld: dict = {}
        self._tri: dict = {}
        self._pe: dict = {}
        self._peh: dict = {}
        self._payload = self._build()

    def _build(self) -> dict:
        rng = self.rng
        seasons = {}
        th = rng.normal(0.0, 0.03, self.n_hit)         # batting runs per PA
        tf = rng.normal(0.0, 0.012, self.n_hit)        # fielding runs per PA
        tp = rng.normal(0.0, 0.08, self.n_pit)         # runs prevented per IP
        for y in range(2016, 2027):
            hit, pit = [], []
            rpw = 9.8
            fy, triy, pey, pehy = {}, {}, {v: {} for v in swar.HR_VARIANTS}, {}
            for i in range(self.n_hit):
                pa = float(rng.integers(60, 700))
                wraa = float(th[i] * pa + rng.normal(0, 7.0))
                b0f = float(tf[i] * pa + rng.normal(0, 4.0))
                fw = float((wraa + b0f) / rpw + 0.02 * pa / 10 + rng.normal(0, 0.3))
                parts = {}
                for p in swar.HITTER_PARTS:
                    pull = {"bat": 0.5, "batx": 0.7, "fld": 0.4}.get(p, 0.0)
                    base = wraa if p in ("bat", "batx") else b0f
                    true = (th[i] if p in ("bat", "batx") else tf[i]) * pa
                    d = pull * (float(true) - base) + float(rng.normal(0, 0.3 if pull else 2.0))
                    test = fw + d / rpw
                    if (p == "batx" and y == 2025 and i % 2 == 0) or (i == 3 and p == "fld"):
                        test, d = None, None
                    parts[p] = {"g": None, "d": d, "test": test}
                parts["bat"]["wraa"] = wraa
                parts["fld"]["b0"] = b0f
                hit.append({"mlbam": 1000 + i, "name": f"H{i}", "pa": pa,
                            "fwar": (None if (i == 5 and y == 2022) else fw),
                            "pitcher_batter": i == 7, "parts": parts})
                catcher = i % 13 == 0
                rec = {"drs": float(tf[i] * pa + rng.normal(0, 4.0)),
                       "uzr": (None if y > 2024 else float(tf[i] * pa + rng.normal(0, 4.0))),
                       "frp": float(tf[i] * pa + rng.normal(0, 4.0)),
                       "c_inn": float(rng.integers(350, 1100)) if catcher else 0.0,
                       "nonc_frp": 0.0 if catcher else float(tf[i] * pa + rng.normal(0, 3.0))}
                rec["sc"] = float(tf[i] * pa + rng.normal(0, 3.0)) if catcher else None
                rec["c_drs"] = rec["drs"] if catcher else None
                if not (i == 11 and y == 2023):
                    rec["runs_field"] = float(tf[i] * pa + rng.normal(0, 4.0))
                fy[1000 + i] = rec
                triy[1000 + i] = {c: float(tf[i] * pa * 0.6 + rng.normal(0, 2.0)) for c in S3T_CONFIGS}
                pehy[1000 + i] = {"n": pa * 0.95, "clres": float(rng.normal(0, 3.0)), "m": pa * 0.5,
                                  "pres": float(rng.normal(0, 20.0))}
            for i in range(self.n_pit):
                ip = float(rng.integers(10, 210))
                g = float(max(1, int(ip / float(rng.uniform(1.0, 6.0)))))
                gs = float(min(g, int(rng.integers(0, 33)))) if i % 2 else 0.0
                war0 = float(tp[i] * ip / rpw + rng.normal(0, 0.4))
                fw = war0 + float(rng.normal(0, 0.1))
                ra9 = None if (i == 6 and y == 2022) else float(4.3 - 9.0 * tp[i] + rng.normal(0, 9.0 / math.sqrt(ip)))
                sigma = float(min(1.0, max(0.0, gs / g if g else 0.0)))
                parts = {}
                for v in swar.HR_VARIANTS:
                    pull = 0.6 if v == swar.HR_SHRUNK else 0.2
                    dl = pull * (float(tp[i]) * ip / rpw - war0) + float(rng.normal(0, 0.05))
                    parts[v] = {"dfip": None, "dwar0": dl, "delta": dl,
                                "test": (None if (i == 2 and v == swar.HR_SHRUNK) else fw + dl),
                                "lb_dwar0": dl * float(rng.uniform(0.6, 1.2))}
                    db = (pull + 0.1) * (float(tp[i]) * ip / rpw - war0) + float(rng.normal(0, 0.05))
                    parts[pb_key(v)] = {"dwar0": db, "delta": db,
                                        "test": (None if (i == 4 and y == 2022) else fw + db)}
                    pey[v][5000 + i] = float(rng.normal(0, 1.0))
                pit.append({"mlbam": 5000 + i, "name": f"P{i}", "ip": ip, "g": g, "gs": gs, "fwar": fw,
                            "sigma": sigma, "nopp": i == 9, "gmli": None, "parts": parts,
                            "war0": war0, "ra9_star": ra9})
            seasons[str(y)] = {"rpw": rpw, "hitters": hit, "pitchers": pit,
                               "census": {"rows_hitters": len(hit), "rows_pitchers": len(pit)}}
            self._fld[y], self._tri[y] = fy, triy
            self._pe[y] = {"delta": pey, "w": 0.004, "coverage": {"no_split": 0, "nopp": 1, "no_ip": 0}}
            self._peh[y] = {"resid": pehy, "pa": {1000 + i: float(r["pa"]) for i, r in enumerate(hit)
                                                  if not r["pitcher_batter"]}}
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

    def team_exposure(self):
        out = {}
        sh = self.team_shares()
        for s, blk in self._payload["seasons"].items():
            for side, key, n in ((HIT, "hitters", "pa"), (PIT, "pitchers", "ip")):
                for r in blk[key]:
                    w = sh.get((side, int(s), r["mlbam"]))
                    if w:
                        out[(side, int(s), r["mlbam"])] = {t: f * r[n] for t, f in w.items()}
        return out

    def standings(self, seasons):
        out = {}
        for y in seasons:
            if int(y) == 2023:
                continue
            out[int(y)] = {}
            for j in range(30):
                w = int(60 + (j * 7 + int(y)) % 40)
                out[int(y)][f"T{j:02d}"] = {"w": w, "l": 162 - w, "rs": 600 + 3 * w + (j % 5),
                                            "ra": 900 - 3 * w + (j % 7)}
        return out

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

    def fielding_by_player(self):
        import copy
        return copy.deepcopy(self._fld)

    def triangulation_runs(self):
        return {y: {m: dict(v) for m, v in d.items()} for y, d in self._tri.items()}

    def pe_pitchers(self, season):
        return self._pe[int(season)]

    def pe_hitters(self, season):
        return self._peh.get(int(season)) if int(season) in self.CORPUS else None

    def pe_wear(self, season):
        return self._pe[int(season)]["w"]

    def ladder_records(self):
        ev = {"gate": "fixture", "seeds": {"bootstrap": 1, "draws": 50},
              "tests": {"v1_minus_fg_inv_pooled": {"dmae": 0.10, "ci95": [0.07, 0.14], "n_rows": 400,
                                                    "n_players": 60},
                        "v1_minus_fg_table_pooled": {"dmae": 0.18, "ci95": [0.14, 0.22]}}}
        ve = {"zero_ladder": {"tests": {"v1_minus_zero": {"dmae": 0.84, "ci95": [0.66, 1.03]}}}}
        return ev, ve, "v1"

    def input_meta(self):
        return {"fixture": True}


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
        # part 11's inputs: present and shaped, no value read
        import fielding_triangulation_lab as FTL
        import pitch_economy_lab as pel
        import sdr_inhouse
        need_cols = ("xMLBAMID", "Pos", "Inn", "DRS", "UZR", "FRP", "OAA", "CFraming", "bFRP", "tFRP")
        fg_ok = {}
        for y in range(2016, 2027):
            f = sdr_inhouse.RAW / f"fg_field_full_{y}.csv"
            if f.exists():
                head = f.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
                fg_ok[y] = all(c in head.replace('"', "").split(",") for c in need_cols)
            else:
                fg_ok[y] = False
        out["fg_fielding_files_ok"] = fg_ok
        out["triangulation_fit_present"] = FTL.FIT_OUT.exists()
        out["war_daily_bat_present"] = FTL.WAR_DAILY.exists()
        out["count_value_present"] = pel.COUNT_VALUE.exists()
        man = (json.loads((pel.RECORD / "manifest.json").read_text(encoding="utf-8"))
               if (pel.RECORD / "manifest.json").exists() else {})
        out["runner_record_seasons"] = sorted(int(s) for s in (man.get("seasons") or {}))
        out["sprp_lines_present"] = {y: (pel.CACHE / "pitch_rates" / f"pitching_sprp_1_{y}.json").exists()
                                     for y in range(2016, 2027)}
        out["ladder_records_present"] = {"eval": T.LADDER_EVAL.exists(), "verify": T.LADDER_VERIFY.exists()}
        if PREVIEW_PATH.exists():
            try:
                check_amended_preview(json.loads(PREVIEW_PATH.read_text(encoding="ascii")))
                out["preview_amended_bases"] = True
            except LabStop as exc:
                out["preview_amended_bases"] = str(exc)
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
