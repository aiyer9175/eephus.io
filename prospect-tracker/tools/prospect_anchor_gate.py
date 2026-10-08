# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The prospect realized-anchor calibration gate's ONE lab (docs/PROSPECT_ANCHOR_GATE.md).

Registration: docs/PROSPECT_ANCHOR_GATE.md (pre-registered 2026-09-23). The lab implements
sections 1, 2 (L1 and L2: nothing is read if these fail), 4, 5, 6, 7, 8, 11 and 12 as
written; the artifact's shape is section 15; the bans are section 16; the sentences are
section 17. Read-only over every production module. Writes exactly one artifact,
data/prospect_anchor_gate.json, and, under one outcome, the key `empirical_anchors_v2` of
data/value_framework_fitted.json (never through `value_framework.py --fit`).

Modes:
  python -u tools/prospect_anchor_gate.py                 THE LOOK. Once. Refused before the
                                                          later of 2026-11-20 and step Z + 14
                                                          days, on a registered look day, when
                                                          section 18 is not empty, when the
                                                          artifact exists, or on any label but
                                                          fwar.
  python tools/prospect_anchor_gate.py --fixture F --out O  the whole reporting path on a
                                                          fixture frame (tests only). Refuses to
                                                          write the real artifact path.
  python tools/prospect_anchor_gate.py --fit-v2           section 11, refused unless the
                                                          artifact's verdict reads MISCALIBRATED.
                                                          Takes no K, prior, side table or knots.

What is pre-registered and NOT a free choice here (every number is the gate's own): the five
cells (5.1), the floor n >= 40 (5.2, the anchor's own min_n_robust), B 2000 seed 20260923
two-sided 90 percent (5.3), the margin formula (5.4), the 0.75x to 1.25x pin on the look-day
margin (5.4), the Holm family at alpha 0.10 (6.3), MDE95 as 1.645 times the bootstrap standard
error of D_C (section 8), the detection check at B 1000 seed 20260923 with its 0.80 label, the
coverage check at n_check 200, the lever's K 30, knots 45 to 70, caps [0.5, 2.0] and 0.15, the
twin's 75 percent rule and the out-of-fold floor (section 11).

Nothing here reads data/mlb_projections.json, any proj_ml output or warChamp (L7).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
ARTIFACT = DATA / "prospect_anchor_gate.json"
GATE_DOC = ROOT / "docs" / "PROSPECT_ANCHOR_GATE.md"
EPOCH_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
FITTED_PATH = DATA / "value_framework_fitted.json"
POOLED_CURVE = DATA / "fv_outcome_curves_pooled.json"
FORBIDDEN_INPUT = "data/mlb_projections.json"

# ---------------------------------------------------------------------------
# Registered constants (docs/PROSPECT_ANCHOR_GATE.md, by section). Pinned by
# test_prospect_anchor_gate.py.
# ---------------------------------------------------------------------------
# 5.1 Cells on the raw as-of consensus FV: (name, lower, upper, knot). Every range is
# [lower, upper) except 65+, whose upper bound 80 is inclusive.
CELLS = (("45", 42.5, 47.5, 45.0),
         ("50", 47.5, 52.5, 50.0),
         ("55", 52.5, 57.5, 55.0),
         ("60", 57.5, 62.5, 60.0),
         ("65+", 62.5, 80.0, 65.0))
CELL_NAMES = tuple(c[0] for c in CELLS)
UPPER_INCLUSIVE = ("65+",)
TARGET_SEASONS = 6                      # the label is a six-season total; D divides once
MIN_N = 40                              # 5.2: anchor_calibration.min_n_robust, reused
B_BOOT = 2000                           # 5.3
SEED = 20260923                         # 5.3, section 8, section 11
CI_LO, CI_HI = 0.05, 0.95               # 5.3: two-sided 90 percent
MDE_Z = 1.645                           # section 8: MDE95 = 1.645 x bootstrap se of D_C
UNDERPOWERED_MULT = 2.0                 # 6.1: MDE95 > 2 * m_C reads UNDECIDED_UNDERPOWERED
HOLM_ALPHA = 0.10                       # 6.3
DETECT_B = 1000                         # section 8: design-matched simulation runs
DETECT_SEED = 20260923
DETECT_FLOOR = 0.80
COVERAGE_N_CHECK = 200                  # section 8: n_check >= 200
RATIO_BOUNDS = (0.75, 1.25)             # 5.4: look-day m_C against design-day m_C
LOOK_FLOOR = _dt.date(2026, 11, 20)     # section 14
STEP_Z_LAG_DAYS = 14                    # section 14
LOOK_SLIP_DATE = _dt.date(2026, 12, 31)  # section 14: the look slips with the epoch after this
# Registered look days of OTHER gates on which no lab of this gate runs (section 14 and the
# epoch calendar): the PROJ_PATH looks and the eFV reserved read.
BLOCKED_DAYS = (_dt.date(2026, 10, 23), _dt.date(2026, 11, 6), _dt.date(2026, 11, 13),
                _dt.date(2026, 12, 1))
# 5.4 design-day illustration, arithmetic on the served 2026-09-04 table.
DESIGN_DAY = {"45": {"anchor_lo": 0.196, "anchor_hi": 0.500, "m": 0.152},
              "50": {"anchor_lo": 0.500, "anchor_hi": 0.830, "m": 0.165},
              "55": {"anchor_lo": 0.830, "anchor_hi": 1.210, "m": 0.190},
              "60": {"anchor_lo": 1.210, "anchor_hi": 1.725, "m": 0.258},
              "65+": {"anchor_lo": 1.725, "anchor_hi": 2.250, "m": 0.263}}
CONFIRMED_REQUIRES_H = ("45", "50", "55")   # 6.2
# Section 15: the closed verdict vocabulary, and the one annotation that is not a verdict.
VERDICTS = ("CONFIRMED", "MISCALIBRATED", "UNDECIDED", "UNPOWERED", "UNDECIDED_UNDERPOWERED",
            "NOT_AVAILABLE", "VOID", "REFUSED", "NULL")
ANNOTATION = "SOURCE_SCALE_SUSPECT"
# The commit c5167587 row (section 0 and section 15): published, never adjudicated.
NAMED_ROW = {"player_key": "jesus_made", "commit": "c5167587", "efv_in_commit": 61.9,
             "expected_five_year_in_commit": 7.5, "prime_in_commit": 15.4}
# Section 11, the lever (exists only under MISCALIBRATED).
V2_KNOTS = (45.0, 50.0, 55.0, 60.0, 65.0, 70.0)
V2_PRIOR_ONLY_KNOT = 80.0
V2_K_SHRINK = 30.0                      # the pooled curve's own k_shrink, reused
V2_FACTOR_CAP = (0.5, 2.0)              # 11.2
V2_MAX_REPAIR_MOVE = 0.15               # 11.2, WAR per season
TWIN_SHARE = 0.75                       # 11.3
OOF_YEARS = (2016, 2017, 2018, 2019, 2020, 2021)   # 11.4
OOF_MIN_FOLDS_FOR = 4                   # 11.4
V2_KEY = "empirical_anchors_v2"

# ---------------------------------------------------------------------------
# The criteria, VERBATIM from the gate, published beside every result (section 15).
# ---------------------------------------------------------------------------
CRITERIA = {
    "estimand": ("D_i = label_i / 6 - fv_to_6yr_avg_war(fv_i), WAR per season, over the "
                 "resolved rows of cell C; the gate asks whether |E[D_C]| lies inside a "
                 "tolerance fixed in section 5.4. Positive D_C is realized ABOVE the anchor."),
    "cells": ("45 [42.5, 47.5); 50 [47.5, 52.5); 55 [52.5, 57.5); 60 [57.5, 62.5); "
              "65+ [62.5, 80]. Each row's assigned level is the anchor at ITS OWN FV, never "
              "the knot value."),
    "floor": ("A cell carries a verdict only with n >= 40 resolved rows on the frame being "
              "read. 40 is anchor_calibration.min_n_robust. Below 40 the cell reads UNPOWERED "
              "and publishes its n and its point estimate without an interval."),
    "statistic": ("D_C = mean over rows of label_i / 6 - anchor(fv_i). R_C = mean(label_i / 6) "
                  "/ mean(anchor(fv_i)), reported, never adjudicated. Interval: percentile "
                  "bootstrap over rows, B = 2000, seed 20260923, two-sided 90 percent."),
    "margin": "m_C = ( anchor(k_C + 2.5) - anchor(k_C - 2.5) ) / 2, on the served table at the look (for the 65+ cell, at k = 65).",
    "margin_pin": ("A look-day m_C outside 0.75x to 1.25x of the design-day figure at any "
                   "cell requires an amendment filed BEFORE the look; without that "
                   "amendment the look is not taken."),
    "CONFIRMED": "n >= 40 and the 90 percent interval on D_C lies entirely inside [-m_C, +m_C]",
    "MISCALIBRATED": ("n >= 40 and the interval lies entirely outside the band on one side, "
                      "after the Holm step in 6.3; the sign is published"),
    "UNDECIDED": "n >= 40 and neither",
    "UNPOWERED": ("n < 40, or the cell's MDE95 (1.645 times the bootstrap standard error of "
                  "D_C, the sd of the B draws, never the residual sd of the rows) exceeds "
                  "2 * m_C, in which case the cell is labelled UNDECIDED_UNDERPOWERED and "
                  "counts as unpowered for 6.2"),
    "frame_S": "S (shared): veto only. MISCALIBRATED, or nothing. It can never return CONFIRMED.",
    "frame_pooled": "H + S (pooled, read): reported per cell as a descriptive, labelled READ. Carries no verdict.",
    "verdict_MISCALIBRATED": ("MISCALIBRATED if ANY powered cell on H is MISCALIBRATED under "
                              "the Holm family and survives the concordance rule, OR any "
                              "powered cell on S is MISCALIBRATED under its own Holm family."),
    "concordance": ("A cell that reads MISCALIBRATED on H, where S is ALSO powered at that cell "
                    "and S's 90 percent interval on D_C lies entirely on the opposite side of "
                    "zero from H's point estimate d_C, reads UNDECIDED at that cell, with both "
                    "frames' numbers published and the cell labelled SOURCE_SCALE_SUSPECT."),
    "verdict_CONFIRMED": ("CONFIRMED if EVERY powered cell on H is CONFIRMED, no powered cell on "
                          "S is MISCALIBRATED, AND the powered cells on H include at least 45, "
                          "50 and 55."),
    "verdict_UNDECIDED": "UNDECIDED otherwise, with every cell's disposition published.",
    "holm": ("Family H: the powered cells on frame H, at most five. Family S: the powered cells "
             "on frame S, at most five. Two families, each under Holm at family alpha 0.10. "
             "p_C: if d_C > +m_C, p_C = 2 * (fraction of bootstrap draws with D*_C <= +m_C); "
             "if d_C < -m_C, p_C = 2 * (fraction with D*_C >= -m_C); otherwise p_C = 1. A cell "
             "with d_C on the wrong side of the band reads UNDECIDED whatever its p_C."),
    "one_parameter": ("If MISCALIBRATED, whether the powered cells' residuals are consistent "
                      "with a single multiplicative LEVEL error (all R_C inside one another's "
                      "intervals) or with a SHAPE error (they are not). Descriptive."),
    "per_side": ("Per side: reported, never adjudicated. No copy may cite a per-side number "
                 "from this artifact as evidence about the anchor."),
    "power_MDE95": ("MDE95 = 1.645 times the bootstrap standard error of D_C, the standard "
                    "deviation of the B bootstrap draws of D_C, and NOT the residual sd of the "
                    "rows."),
    "power_detection": ("A design-matched simulation planting a residual of exactly +m_C at "
                        "each powered cell with the cell's own residual sd and n, B = 1000, "
                        "seed 20260923; the fraction of simulated runs returning MISCALIBRATED "
                        "is published, and a cell below 0.80 is labelled as one where a "
                        "MISCALIBRATED verdict would be a lucky read, without changing its "
                        "disposition rule."),
    "power_coverage": ("A two-sided coverage check on the bootstrap interval itself, n_check "
                       ">= 200, at the cell's n: a too-NARROW interval manufactures CONFIRMED, "
                       "the direction the check exists to catch."),
    "L3": "Only rows with censored == False enter any cell. No tail-projected label enters.",
    "L4": ("A never-debuted prospect is a 0, not a missing value, and a debuted prospect's "
           "absent season inside his window is a 0."),
    "L7": ("The artifact carries no field read from data/mlb_projections.json, no proj_ml "
           "output and no warChamp."),
    "lever": ("Section 11 exists only under MISCALIBRATED: knots 45 to 70, cell [k - 2.5, "
              "k + 2.5) (the 70 cell runs to 80), raw cell mean shrunk toward the Clemens 2026 "
              "prior in per-season units, 0.5 * (clemens_hit + clemens_pit), K = 30; 80 the "
              "prior alone; 20 through 40 the served knots byte for byte; monotone "
              "non-decreasing repair; three decimals; caps [0.5, 2.0] and 0.15 WAR per season; "
              "the one-parameter twin ships if it captures 75 percent; one read site."),
}

SENTENCES = {
    "CONFIRMED": ("The realized anchor is CONFIRMED at FV cells {confirmed} on the holdout "
                  "frame: the bust-inclusive first-six-season mean of resolved prospects at "
                  "each of those FVs sits within one grade step of the level the framework "
                  "assigns. Cells {unpowered} were unpowered on the holdout and read "
                  "{s_dispositions} on the shared frame, which can fail the anchor and cannot "
                  "confirm it. Nothing served moves. The open question of commit c5167587 is "
                  "answered: the expected path is the calibrated bust-inclusive mean. If the "
                  "row still reads low beside its bust probability, that is the mixture's "
                  "shape (design audit F07), not its level, and it has its own registration."),
    "MISCALIBRATED_LOW": ("The realized anchor is MISCALIBRATED LOW at FV cells {cells} on "
                          "frame {frame}: resolved prospects delivered {d_c} WAR per season "
                          "more than the framework assigns, interval {interval}, beyond the "
                          "one-grade-step tolerance {m_c}. A recalibration lever is built "
                          "behind SERVE_PROSPECT_ANCHOR_V2, default off; its out-of-fold check "
                          "on read rows reads {oof}. Nothing served moves until the owner "
                          "flips it. This is a statement about the level of the anchor, not "
                          "about the shape of the mixture, and not about any player."),
    "MISCALIBRATED_HIGH": ("The realized anchor is MISCALIBRATED HIGH at FV cells {cells} on "
                           "frame {frame}: resolved prospects delivered {d_c} WAR per season "
                           "less than the framework assigns, interval {interval}, beyond the "
                           "one-grade-step tolerance {m_c}. A recalibration lever is built "
                           "behind SERVE_PROSPECT_ANCHOR_V2, default off; its out-of-fold "
                           "check on read rows reads {oof}. Nothing served moves until the "
                           "owner flips it. This is a statement about the level of the anchor, "
                           "not about the shape of the mixture, and not about any player. The "
                           "owner's suspicion that the anchor is calibrated low is falsified "
                           "at these cells."),
    "UNDECIDED": ("The realized anchor is UNDECIDED at FV cells {cells}: the interval on the "
                  "realized-minus-assigned level crosses the tolerance band. Nothing served "
                  "moves. The question re-arms when RESOLVED_THROUGH reaches 2027 under a new "
                  "registration that discloses this read. UNDECIDED is not a confirmation and "
                  "no copy may treat it as one."),
    "UNPOWERED_H": ("The resolved holdout carries {n} prospects at FV {cell}, below the 40-row "
                    "floor the anchor itself declares for trusting a tier. The anchor is not "
                    "adjudicated there. The shared frame reads {s_disposition}."),
    "UNPOWERED_10_4": ("the resolved holdout carries too few prospects at this FV to adjudicate "
                       "the anchor there; the shared frame's reading is {s_disposition}, which "
                       "can fail the anchor and cannot confirm it"),
    "LEVER_REFUSED": ("The recalibrated anchor moves knot {knot} by a factor of {factor}, "
                      "outside [0.5, 2.0]. A correction of that size is the shape of the "
                      "Quantity A / Quantity B trap and is evidence the frame is measuring the "
                      "wrong quantity, not evidence about the anchor. The lever is refused and "
                      "nothing ships."),
    "LEVER_NULL": ("The recalibrated anchor does not beat the incumbent rule out of fold by "
                   "more than the floor ({mde95}) on the forward-chained decision years, {k} of "
                   "6 folds in its favour, on rows this gate had already read. Reported as a "
                   "NULL. The flag stays off and the MISCALIBRATED verdict on the anchor stands "
                   "unrepaired."),
    "CONCORDANCE": ("Cell {cell} reads MISCALIBRATED on the holdout frame, whose rows at that "
                    "cell are {share} single-source MLB Pipeline-scale FV, and the opposite "
                    "sign on the shared frame, interval {interval}. The two frames disagree in "
                    "direction, which is the signature of a source-scale offset and not of the "
                    "anchor's level; the cell reads UNDECIDED and nothing ships from it."),
    "UNCONDITIONAL": ("Every number here is on the published fWAR label frozen per season. It "
                      "is a statement about that definition of WAR. The anchor's agreement or "
                      "disagreement with it is not evidence that the label is more or less "
                      "accurate than any other."),
}


class LabRefused(RuntimeError):
    """A guard fired. Nothing was read and nothing was written."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _f(x):
    """A JSON-safe float, or None."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _r(x, nd=4):
    v = _f(x)
    return None if v is None else round(v, nd)


def interp_anchor(anchors: dict):
    """The served interpolation rule of value_framework.fv_to_6yr_avg_war over a
    {knot: value} table (piecewise linear, clamped). Used on FIXTURE tables; the
    real run passes value_framework.fv_to_6yr_avg_war itself."""
    pts = sorted((float(k), float(v)) for k, v in anchors.items())

    def f(fv):
        x = _f(fv)
        if x is None:
            return None
        if x <= pts[0][0]:
            return pts[0][1]
        if x >= pts[-1][0]:
            return pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0)
                return y0 * (1 - t) + y1 * t
        return pts[-1][1]
    return f


def cell_of(fv) -> str | None:
    """5.1: the cell a raw as-of consensus FV falls in, or None (sub-45 is OUT)."""
    x = _f(fv)
    if x is None:
        return None
    for name, lo, hi, _k in CELLS:
        if name in UPPER_INCLUSIVE:
            if lo <= x <= hi:
                return name
        elif lo <= x < hi:
            return name
    return None


def margins(anchor) -> dict:
    """5.4: m_C at every cell from the served table, beside the design-day value and
    their ratio, with the 0.75x to 1.25x pin evaluated. Computed BEFORE any cell is read."""
    out = {}
    for name, _lo, _hi, k in CELLS:
        a_lo = float(anchor(k - 2.5))
        a_hi = float(anchor(k + 2.5))
        m = (a_hi - a_lo) / 2.0
        design = DESIGN_DAY[name]
        ratio = (m / design["m"]) if design["m"] else None
        out[name] = {"knot": k, "anchor_at_k_minus_2_5": _r(a_lo, 6),
                     "anchor_at_k_plus_2_5": _r(a_hi, 6), "m_c": _r(m, 6),
                     "design_day_anchor_lo": design["anchor_lo"],
                     "design_day_anchor_hi": design["anchor_hi"],
                     "design_day_m_c": design["m"], "ratio_to_design_day": _r(ratio, 4),
                     "ratio_inside_pin": (ratio is not None
                                          and RATIO_BOUNDS[0] <= ratio <= RATIO_BOUNDS[1]),
                     "criterion": CRITERIA["margin"]}
    return out


# ---------------------------------------------------------------------------
# Rows and frames
# ---------------------------------------------------------------------------
def prepare_rows(raw_rows) -> tuple[list[dict], dict]:
    """Normalise a frame's rows and count what is dropped. A row needs a player_key,
    a finite fv and a finite label; censored rows are out (L3). None values in the
    census fields (n_sources, fv_fangraphs, fv_mlb_pipeline, year) are carried as None
    and never dropped. Nothing is read from a projection input (L7)."""
    rows, drops = [], {"no_player_key": 0, "fv_missing": 0, "label_missing": 0,
                       "censored": 0, "below_cells": 0}
    for r in raw_rows or []:
        pk = r.get("player_key")
        if not pk:
            drops["no_player_key"] += 1
            continue
        fv = _f(r.get("fv"))
        war = _f(r.get("war"))
        if fv is None:
            drops["fv_missing"] += 1
            continue
        if war is None:
            drops["label_missing"] += 1
            continue
        if bool(r.get("censored")):
            drops["censored"] += 1
            continue
        cell = cell_of(fv)
        if cell is None:
            drops["below_cells"] += 1
        yr = r.get("year")
        try:
            yr = int(yr) if yr is not None else None
        except (TypeError, ValueError):
            yr = None
        rows.append({"player_key": str(pk), "side": str(r.get("side") or ""), "fv": fv,
                     "war": war, "cell": cell, "year": yr,
                     "n_sources": _f(r.get("n_sources")),
                     "fv_fangraphs": _f(r.get("fv_fangraphs")),
                     "fv_mlb_pipeline": _f(r.get("fv_mlb_pipeline"))})
    return rows, drops


def partition(rows: list[dict], cohort_keys) -> tuple[list[dict], list[dict]]:
    """4.1: H = resolved rows whose player_key is NOT in the anchor's fit cohort; S = the
    rows whose key IS. Mechanical; no key may land in both."""
    keys = set(cohort_keys or ())
    h = [r for r in rows if r["player_key"] not in keys]
    s = [r for r in rows if r["player_key"] in keys]
    hk, sk = {r["player_key"] for r in h}, {r["player_key"] for r in s}
    if hk & sk:
        raise LabRefused(f"frames H and S share {len(hk & sk)} player keys")
    return h, s


def source_census(rows: list[dict]) -> dict:
    """4.1 (i): mean n_sources, the share of rows with n_sources == 1, and the share whose
    only source is the Pipeline (fv_fangraphs null and fv_mlb_pipeline present)."""
    n = len(rows)
    ns = [r["n_sources"] for r in rows if r["n_sources"] is not None]
    single = sum(1 for r in rows if r["n_sources"] is not None and r["n_sources"] == 1)
    pipe = sum(1 for r in rows if r["fv_fangraphs"] is None and r["fv_mlb_pipeline"] is not None)
    return {"n": n, "mean_n_sources": _r(sum(ns) / len(ns), 4) if ns else None,
            "n_sources_known": len(ns),
            "share_single_source": _r(single / n, 4) if n else None,
            "share_pipeline_only": _r(pipe / n, 4) if n else None}


def year_census(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        key = str(r["year"]) if r["year"] is not None else "unknown"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# The statistic (5.3), its bootstrap, and the per-cell power figures (section 8)
# ---------------------------------------------------------------------------
def _bootstrap_means(resid: np.ndarray, level: np.ndarray, rng: np.random.Generator,
                     b: int = B_BOOT) -> tuple[np.ndarray, np.ndarray]:
    """Percentile bootstrap over rows (players: L2 asserts cross-side overlap is 0).
    Returns the B draws of D_C and of R_C from the SAME resampled indices."""
    n = resid.shape[0]
    idx = rng.integers(0, n, size=(b, n))
    d = resid[idx].mean(axis=1)
    anchor_draw = level[idx].mean(axis=1)
    realized_draw = d + anchor_draw
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(anchor_draw > 0, realized_draw / anchor_draw, np.nan)
    return d, r


def cell_estimate(rows: list[dict], anchor, m_c: float, knot: float,
                  rng: np.random.Generator, with_interval: bool = True) -> dict:
    """D_C, R_C, the interval, the bootstrap standard error, MDE95 and p_C for one cell on
    one frame. `with_interval` False (n below the floor) publishes the point estimate only."""
    n = len(rows)
    out = {"n": n, "floor": MIN_N, "zero_convention": CRITERIA["L4"]}
    if n == 0:
        out.update({"d_c": None, "r_c": None, "mean_label_per_season": None,
                    "mean_assigned_anchor": None, "knot_anchor": _r(anchor(knot), 6),
                    "residual_sd": None, "se": None, "boot_se": None, "mde95": None,
                    "ci90": None, "r_ci90": None, "p_c": None, "draws": None,
                    "r_draws": None})
        return out
    realized = np.array([r["war"] / TARGET_SEASONS for r in rows], dtype=float)
    level = np.array([float(anchor(r["fv"])) for r in rows], dtype=float)
    resid = realized - level
    d_c = float(resid.mean())
    mean_level = float(level.mean())
    r_c = (float(realized.mean()) / mean_level) if mean_level > 0 else None
    sd = float(resid.std(ddof=1)) if n > 1 else 0.0
    out.update({"d_c": _r(d_c, 6), "r_c": _r(r_c, 6),
                "mean_label_per_season": _r(realized.mean(), 6),
                "mean_assigned_anchor": _r(mean_level, 6), "knot_anchor": _r(anchor(knot), 6),
                "residual_sd": _r(sd, 6), "se": _r(sd / math.sqrt(n), 6) if n > 1 else None})
    if not with_interval or n < 2:
        out.update({"boot_se": None, "mde95": None, "ci90": None, "r_ci90": None,
                    "p_c": None, "draws": None, "r_draws": None})
        return out
    d_draws, r_draws = _bootstrap_means(resid, level, rng)
    boot_se = float(d_draws.std(ddof=1))
    lo, hi = (float(np.quantile(d_draws, CI_LO)), float(np.quantile(d_draws, CI_HI)))
    finite_r = r_draws[np.isfinite(r_draws)]
    r_ci = ([_r(np.quantile(finite_r, CI_LO), 6), _r(np.quantile(finite_r, CI_HI), 6)]
            if finite_r.size else None)
    if d_c > m_c:
        p_c = 2.0 * float((d_draws <= m_c).mean())
    elif d_c < -m_c:
        p_c = 2.0 * float((d_draws >= -m_c).mean())
    else:
        p_c = 1.0
    p_c = min(1.0, p_c)
    out.update({"boot_se": _r(boot_se, 6), "mde95": _r(MDE_Z * boot_se, 6),
                "ci90": [_r(lo, 6), _r(hi, 6)], "r_ci90": r_ci, "p_c": _r(p_c, 6),
                "draws": d_draws, "r_draws": r_draws})
    return out


def detection_check(n: int, sd: float, m_c: float, rng: np.random.Generator) -> float:
    """Section 8: plant +m_C with the cell's own residual sd and n; the fraction of DETECT_B
    simulated runs whose two-sided 90 percent bootstrap interval lies entirely above +m_C
    (the cell's own MISCALIBRATED criterion, read on the cell alone)."""
    hits = 0
    for _ in range(DETECT_B):
        sample = rng.normal(m_c, sd, size=n)
        idx = rng.integers(0, n, size=(B_BOOT, n))
        draws = sample[idx].mean(axis=1)
        if float(np.quantile(draws, CI_LO)) > m_c:
            hits += 1
    return hits / DETECT_B


def coverage_check(resid: np.ndarray, rng: np.random.Generator) -> dict:
    """Section 8: two-sided coverage of the 90 percent bootstrap interval at the cell's n,
    with the cell's own residual rows as the population (truth = their mean). Publishes the
    coverage and the two one-sided miss rates; too NARROW (coverage under 0.90) is the
    permissive direction."""
    n = resid.shape[0]
    truth = float(resid.mean())
    below = above = 0
    for _ in range(COVERAGE_N_CHECK):
        sample = resid[rng.integers(0, n, size=n)]
        idx = rng.integers(0, n, size=(B_BOOT, n))
        draws = sample[idx].mean(axis=1)
        lo, hi = float(np.quantile(draws, CI_LO)), float(np.quantile(draws, CI_HI))
        if truth < lo:
            above += 1       # the interval sat entirely above the truth
        elif truth > hi:
            below += 1
    cov = 1.0 - (below + above) / COVERAGE_N_CHECK
    return {"n_check": COVERAGE_N_CHECK, "coverage": _r(cov, 4),
            "miss_interval_above_truth": _r(above / COVERAGE_N_CHECK, 4),
            "miss_interval_below_truth": _r(below / COVERAGE_N_CHECK, 4),
            "nominal": 0.90, "too_narrow": cov < 0.90}


# ---------------------------------------------------------------------------
# Decision rule (section 6)
# ---------------------------------------------------------------------------
def holm(pvals: dict, alpha: float = HOLM_ALPHA) -> dict:
    """Holm step-down over a family of {cell: p}. Returns k, the ordered p-values with the
    threshold each met, the set rejected and the step at which Holm stopped."""
    k = len(pvals)
    ordered = sorted(pvals.items(), key=lambda kv: (kv[1], kv[0]))
    rejected, stopped_at, steps = [], None, []
    for i, (cell, p) in enumerate(ordered, start=1):
        thr = alpha / (k - i + 1)
        ok = stopped_at is None and p <= thr
        steps.append({"step": i, "cell": cell, "p_c": _r(p, 6), "threshold": _r(thr, 6),
                      "rejected": bool(ok)})
        if ok:
            rejected.append(cell)
        elif stopped_at is None:
            stopped_at = i
    return {"alpha": alpha, "k": k, "ordered": steps, "rejected": rejected,
            "stopped_at_step": stopped_at}


def _raw_disposition(est: dict, m_c: float) -> str:
    """6.1 per cell, before the Holm step and the concordance rule."""
    if est["n"] < MIN_N or est["ci90"] is None:
        return "UNPOWERED"
    if est["mde95"] is not None and est["mde95"] > UNDERPOWERED_MULT * m_c:
        return "UNDECIDED_UNDERPOWERED"
    lo, hi = est["ci90"]
    if -m_c <= lo and hi <= m_c:
        return "CONFIRMED"
    if lo > m_c or hi < -m_c:
        return "MISCALIBRATED_CANDIDATE"
    return "UNDECIDED"


def adjudicate(frame_est: dict, margin: dict, frame: str) -> dict:
    """Dispositions on one frame (H or S) after the Holm family of 6.3. On S, CONFIRMED is
    never returned (4.1: veto only); the inside-band case reads UNDECIDED there."""
    powered = {}
    raw = {}
    for name in CELL_NAMES:
        est = frame_est[name]
        m_c = margin[name]["m_c"]
        d = _raw_disposition(est, m_c)
        raw[name] = d
        if d in ("CONFIRMED", "MISCALIBRATED_CANDIDATE", "UNDECIDED"):
            powered[name] = est["p_c"] if est["p_c"] is not None else 1.0
    fam = holm(powered)
    out = {}
    for name in CELL_NAMES:
        d = raw[name]
        if d == "MISCALIBRATED_CANDIDATE":
            d = "MISCALIBRATED" if name in fam["rejected"] else "UNDECIDED"
        if frame == "S" and d == "CONFIRMED":
            d = "UNDECIDED"
        sign = None
        if d == "MISCALIBRATED":
            sign = "positive" if frame_est[name]["d_c"] > 0 else "negative"
        out[name] = {"disposition": d, "in_family": name in powered, "sign": sign,
                     "p_c": frame_est[name]["p_c"],
                     "holm_step": next((s["step"] for s in fam["ordered"] if s["cell"] == name),
                                       None)}
    return {"cells": out, "family": fam, "frame": frame,
            "note": CRITERIA["frame_S"] if frame == "S" else None}


def apply_concordance(h_adj: dict, s_adj: dict, h_est: dict, s_est: dict) -> list[str]:
    """6.2: an H MISCALIBRATED where S is powered at the cell and S's interval lies entirely
    on the opposite side of zero from H's d_C reads UNDECIDED, annotated SOURCE_SCALE_SUSPECT.
    Returns the cells the rule fired on."""
    fired = []
    for name in CELL_NAMES:
        if h_adj["cells"][name]["disposition"] != "MISCALIBRATED":
            continue
        if not s_adj["cells"][name]["in_family"]:
            continue
        s_ci = s_est[name]["ci90"]
        d_h = h_est[name]["d_c"]
        if s_ci is None or d_h is None:
            continue
        opposite = (d_h > 0 and s_ci[1] < 0) or (d_h < 0 and s_ci[0] > 0)
        if opposite:
            h_adj["cells"][name]["disposition"] = "UNDECIDED"
            h_adj["cells"][name]["annotation"] = ANNOTATION
            h_adj["cells"][name]["s_ci90"] = s_ci
            fired.append(name)
    return fired


def anchor_verdict(h_adj: dict, s_adj: dict) -> str:
    """6.2, in the order the gate states it: MISCALIBRATED (any surviving veto), then
    CONFIRMED (every powered H cell CONFIRMED, no powered S MISCALIBRATED, H powered at 45,
    50 and 55), else UNDECIDED."""
    h_cells, s_cells = h_adj["cells"], s_adj["cells"]
    if any(c["disposition"] == "MISCALIBRATED" for c in h_cells.values()):
        return "MISCALIBRATED"
    if any(c["disposition"] == "MISCALIBRATED" for c in s_cells.values()):
        return "MISCALIBRATED"
    h_powered = [n for n in CELL_NAMES if h_cells[n]["in_family"]]
    if (h_powered and all(h_cells[n]["disposition"] == "CONFIRMED" for n in h_powered)
            and all(c in h_powered for c in CONFIRMED_REQUIRES_H)):
        return "CONFIRMED"
    return "UNDECIDED"


def one_parameter_reading(h_est: dict, s_est: dict, h_adj: dict, s_adj: dict) -> dict:
    """6.4: all powered cells' R_C inside one another's intervals (LEVEL) or not (SHAPE)."""
    out = {}
    for frame, est, adj in (("H", h_est, h_adj), ("S", s_est, s_adj)):
        cells = [n for n in CELL_NAMES if adj["cells"][n]["in_family"]
                 and est[n]["r_c"] is not None and est[n]["r_ci90"] is not None]
        if len(cells) < 2:
            out[frame] = {"cells": cells, "reading": None,
                          "note": "fewer than two powered cells with a ratio interval"}
            continue
        consistent = all(est[b]["r_ci90"][0] <= est[a]["r_c"] <= est[b]["r_ci90"][1]
                         for a in cells for b in cells)
        out[frame] = {"cells": cells, "reading": "LEVEL" if consistent else "SHAPE",
                      "r_c": {c: est[c]["r_c"] for c in cells},
                      "r_ci90": {c: est[c]["r_ci90"] for c in cells}}
    out["criterion"] = CRITERIA["one_parameter"]
    return out


# ---------------------------------------------------------------------------
# The artifact (section 15): power first, then cells, then the verdict
# ---------------------------------------------------------------------------
def _strip_draws(est: dict) -> dict:
    return {k: v for k, v in est.items() if k not in ("draws", "r_draws")}


def _per_side(rows: list[dict], anchor, m_c: float, knot: float, rng) -> dict:
    out = {}
    for side in ("hit", "pit"):
        sub = [r for r in rows if r["side"] == side]
        est = cell_estimate(sub, anchor, m_c, knot, rng, with_interval=len(sub) >= MIN_N)
        out[side] = _strip_draws(est)
        out[side]["interval_published"] = len(sub) >= MIN_N
    out["resolver"] = "efv_dataset._side_match and the matrix's own side"
    out["criterion"] = CRITERIA["per_side"]
    return out


def build_artifact(frame: dict, anchor, *, stamps: dict, identity: dict,
                   named_row: dict | None = None, run_meta: dict | None = None,
                   detect: bool = True) -> dict:
    """Compute everything on one frame dict {rows, cohort_keys} with one anchor callable.
    The ORDER of the top-level keys is the artifact's contract: ... "power", "cells",
    "verdict" ... (section 8 and section 15). Returns a JSON-ready dict."""
    t0 = time.time()
    rows, drops = prepare_rows(frame.get("rows"))
    h, s = partition(rows, frame.get("cohort_keys"))
    margin = margins(anchor)
    frames = {"H": h, "S": s, "H+S": rows}
    # One generator, seeded once, consumed in a fixed order (frames H, S, H+S; cells in order).
    rng = np.random.default_rng(SEED)
    est: dict = {}
    for fr in ("H", "S", "H+S"):
        est[fr] = {}
        for name, _lo, _hi, knot in CELLS:
            sub = [r for r in frames[fr] if r["cell"] == name]
            est[fr][name] = cell_estimate(sub, anchor, margin[name]["m_c"], knot, rng,
                                          with_interval=len(sub) >= MIN_N)
    # ---- power block (section 8), before any cell is adjudicated ----------------------
    power = {"criterion_mde95": CRITERIA["power_MDE95"],
             "criterion_detection": CRITERIA["power_detection"],
             "criterion_coverage": CRITERIA["power_coverage"],
             "margin_pin": CRITERIA["margin_pin"],
             "margin_pin_bounds": list(RATIO_BOUNDS),
             "margin_pin_holds": all(margin[n]["ratio_inside_pin"] for n in CELL_NAMES),
             "margins": margin, "frames": {}}
    det_rng = np.random.default_rng(DETECT_SEED)
    cov_rng = np.random.default_rng(SEED)
    for fr in ("H", "S"):
        power["frames"][fr] = {}
        for name, _lo, _hi, _knot in CELLS:
            e = est[fr][name]
            m_c = margin[name]["m_c"]
            powered = e["n"] >= MIN_N and e["ci90"] is not None
            blk = {"n": e["n"], "residual_sd": e["residual_sd"], "se": e["se"],
                   "boot_se": e["boot_se"], "mde95": e["mde95"], "m_c": m_c,
                   "two_m_c": _r(2 * m_c, 6), "design_day_m_c": margin[name]["design_day_m_c"],
                   "ratio_to_design_day": margin[name]["ratio_to_design_day"],
                   "powered_by_n": e["n"] >= MIN_N,
                   "underpowered_by_mde": (powered and e["mde95"] > UNDERPOWERED_MULT * m_c),
                   "detection": None, "coverage": None}
            if powered and detect and e["residual_sd"]:
                frac = detection_check(e["n"], e["residual_sd"], m_c, det_rng)
                blk["detection"] = {"b": DETECT_B, "seed": DETECT_SEED, "planted": m_c,
                                    "fraction_miscalibrated": _r(frac, 4),
                                    "lucky_read_label": frac < DETECT_FLOOR,
                                    "floor": DETECT_FLOOR}
                sub = [r for r in frames[fr] if r["cell"] == name]
                resid = np.array([r["war"] / TARGET_SEASONS - float(anchor(r["fv"]))
                                  for r in sub])
                blk["coverage"] = coverage_check(resid, cov_rng)
            power["frames"][fr][name] = blk
    # ---- cells ------------------------------------------------------------------------
    h_adj = adjudicate(est["H"], margin, "H")
    s_adj = adjudicate(est["S"], margin, "S")
    fired = apply_concordance(h_adj, s_adj, est["H"], est["S"])
    side_rng = np.random.default_rng(SEED)
    cells: dict = {}
    for name, _lo, _hi, knot in CELLS:
        m_c = margin[name]["m_c"]
        blk = {"range": CRITERIA["cells"], "knot": knot, "m_c": m_c,
               "anchor_values_for_m_c": [margin[name]["anchor_at_k_minus_2_5"],
                                         margin[name]["anchor_at_k_plus_2_5"]],
               "criteria": {k: CRITERIA[k] for k in ("CONFIRMED", "MISCALIBRATED",
                                                     "UNDECIDED", "UNPOWERED", "holm",
                                                     "concordance")}}
        for fr, adj in (("H", h_adj), ("S", s_adj)):
            e = _strip_draws(est[fr][name])
            a = adj["cells"][name]
            e.update({"disposition": a["disposition"], "sign": a["sign"],
                      "family": f"family_{fr}" if a["in_family"] else None,
                      "holm_step": a["holm_step"],
                      "annotation": a.get("annotation"),
                      "source_census": source_census([r for r in frames[fr]
                                                      if r["cell"] == name]),
                      "per_side": _per_side([r for r in frames[fr] if r["cell"] == name],
                                            anchor, m_c, knot, side_rng)})
            if a.get("annotation") == ANNOTATION:
                e["s_ci90"] = a.get("s_ci90")
            blk[fr] = e
        pooled = _strip_draws(est["H+S"][name])
        pooled.update({"label": "READ", "criterion": CRITERIA["frame_pooled"],
                       "per_side": _per_side([r for r in rows if r["cell"] == name], anchor,
                                             m_c, knot, side_rng)})
        blk["H+S"] = pooled
        if blk["H"]["disposition"] == "UNPOWERED":
            blk["H"]["sentence"] = SENTENCES["UNPOWERED_H"].format(
                n=blk["H"]["n"], cell=name, s_disposition=blk["S"]["disposition"])
            blk["H"]["sentence_10_4"] = SENTENCES["UNPOWERED_10_4"].format(
                s_disposition=blk["S"]["disposition"])
        if blk["H"].get("annotation") == ANNOTATION:
            share = blk["H"]["source_census"]["share_pipeline_only"]
            blk["H"]["sentence"] = SENTENCES["CONCORDANCE"].format(
                cell=name, share=share, interval=blk["H"].get("s_ci90"))
        cells[name] = blk
    verdict = anchor_verdict(h_adj, s_adj)
    sentence = _verdict_sentence(verdict, cells, h_adj, s_adj)
    art = {
        "line": "docs/PROSPECT_ANCHOR_GATE.md: the realized anchor's one look",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "registration": "docs/PROSPECT_ANCHOR_GATE.md (pre-registered 2026-09-23)",
        "estimand": CRITERIA["estimand"],
        "label_stamps": stamps,
        "identity_checks": identity,
        "frame_integrity": {"L3": CRITERIA["L3"], "L4": CRITERIA["L4"], "L7": CRITERIA["L7"],
                            "forbidden_input": FORBIDDEN_INPUT, "dropped": drops,
                            "rows_in_cells": sum(1 for r in rows if r["cell"]),
                            "rows_below_cells": drops["below_cells"]},
        "frames": {"H": {"rows": len(h), "in_cells": sum(1 for r in h if r["cell"]),
                         "definition": "resolved rows whose player_key is NOT in the anchor's fit cohort",
                         "may_carry_verdict": True,
                         "decision_year_census": year_census([r for r in h if r["cell"]]),
                         "source_census": source_census([r for r in h if r["cell"]])},
                   "S": {"rows": len(s), "in_cells": sum(1 for r in s if r["cell"]),
                         "definition": "resolved rows whose player_key IS in the anchor's fit cohort",
                         "may_carry_verdict": "veto only",
                         "source_census": source_census([r for r in s if r["cell"]])},
                   "cohort_keys": len(set(frame.get("cohort_keys") or ())),
                   "no_key_in_both": True},
        "method": {"statistic": CRITERIA["statistic"], "floor": CRITERIA["floor"],
                   "b": B_BOOT, "seed": SEED, "ci": [CI_LO, CI_HI],
                   "quantile": "numpy.quantile, linear",
                   "bootstrap_unit": "rows (players; cross-side key overlap is 0 by L2)"},
        "power": power,
        "cells": cells,
        "verdict": verdict,
        "verdict_vocabulary": list(VERDICTS),
        "verdict_criteria": {k: CRITERIA[k] for k in ("verdict_MISCALIBRATED", "concordance",
                                                       "verdict_CONFIRMED", "verdict_UNDECIDED")},
        "families": {"H": h_adj["family"], "S": s_adj["family"],
                     "combined_false_miscalibrated_rate_at_most": 0.19},
        "concordance_fired": fired,
        "one_parameter_reading": (one_parameter_reading(est["H"], est["S"], h_adj, s_adj)
                                  if verdict == "MISCALIBRATED" else None),
        "sentence": sentence,
        "unconditional_sentence": SENTENCES["UNCONDITIONAL"],
        "named_row": named_row,
        "lever": None,
        "run": dict(run_meta or {}, seed=SEED, b=B_BOOT, wall_time_s=round(time.time() - t0, 2)),
    }
    return art


def _verdict_sentence(verdict: str, cells: dict, h_adj: dict, s_adj: dict) -> str:
    if verdict == "CONFIRMED":
        confirmed = [n for n in CELL_NAMES if cells[n]["H"]["disposition"] == "CONFIRMED"]
        unpowered = [n for n in CELL_NAMES if cells[n]["H"]["disposition"]
                     in ("UNPOWERED", "UNDECIDED_UNDERPOWERED")]
        return SENTENCES["CONFIRMED"].format(
            confirmed=confirmed, unpowered=unpowered,
            s_dispositions=[cells[n]["S"]["disposition"] for n in unpowered])
    if verdict == "MISCALIBRATED":
        parts = []
        for fr in ("H", "S"):
            mis = [n for n in CELL_NAMES if cells[n][fr]["disposition"] == "MISCALIBRATED"]
            if not mis:
                continue
            first = cells[mis[0]][fr]
            key = "MISCALIBRATED_LOW" if first["sign"] == "positive" else "MISCALIBRATED_HIGH"
            parts.append(SENTENCES[key].format(
                cells=mis, frame=fr, d_c={n: cells[n][fr]["d_c"] for n in mis},
                interval={n: cells[n][fr]["ci90"] for n in mis},
                m_c={n: cells[n]["m_c"] for n in mis}, oof="not yet run"))
        return " ".join(parts)
    und = [n for n in CELL_NAMES if cells[n]["H"]["disposition"]
           in ("UNDECIDED", "UNDECIDED_UNDERPOWERED")]
    return SENTENCES["UNDECIDED"].format(cells=und)


# ---------------------------------------------------------------------------
# Guards (section 14, section 16): the clock, one look, the label
# ---------------------------------------------------------------------------
def step_z_entry(text: str | None = None) -> str | None:
    """The dated step Z entry in part 9 of the epoch gate (a heading or line that carries a
    date and the words 'step Z'), or None. A precondition DISCLOSURE under part 3 is not it."""
    if text is None:
        try:
            text = EPOCH_DOC.read_text(encoding="utf-8")
        except OSError:
            return None
    if "## 9. Results" not in text:
        return None
    part9 = text.split("## 9. Results", 1)[1]
    m = re.search(r"^###\s+(\d{4}-\d{2}-\d{2}):[^\n]*\bstep Z\b", part9, flags=re.M)
    return m.group(1) if m else None


def look_floor(step_z: str | None) -> _dt.date | None:
    """Section 14: the LATER of 2026-11-20 and step Z + 14 days. None without step Z."""
    if not step_z:
        return None
    z = _dt.date.fromisoformat(step_z)
    return max(LOOK_FLOOR, z + _dt.timedelta(days=STEP_Z_LAG_DAYS))


def section_18_is_empty(text: str | None = None) -> bool:
    """True while section 18 carries only its registration text (no dated entry)."""
    if text is None:
        text = GATE_DOC.read_text(encoding="utf-8")
    if "## 18. Results" not in text:
        return False
    body = text.split("## 18. Results", 1)[1]
    if "**EMPTY AT REGISTRATION.**" not in body:
        return False
    return not re.search(r"^###\s", body, flags=re.M)


def check_clock(today: _dt.date | None = None, step_z: str | None = None) -> dict:
    today = today or _dt.date.today()
    if step_z is None:
        step_z = step_z_entry()
    if step_z is None:
        raise LabRefused("refused: FWAR_LABEL_EPOCH_GATE.md part 9 records no step Z entry "
                         "(section 14, section 16)")
    floor = look_floor(step_z)
    if today in BLOCKED_DAYS:
        raise LabRefused(f"refused: {today} is another gate's registered look day")
    if today < floor:
        raise LabRefused(f"refused: today {today} is before the look floor {floor} "
                         f"(max of {LOOK_FLOOR} and step Z {step_z} + {STEP_Z_LAG_DAYS} days)")
    return {"today": today.isoformat(), "step_z_entry": step_z, "look_floor": floor.isoformat()}


def check_one_look(artifact_path: Path = ARTIFACT, gate_text: str | None = None) -> None:
    if artifact_path.exists():
        raise LabRefused(f"refused: {artifact_path.name} exists; the look is taken once")
    if not section_18_is_empty(gate_text):
        raise LabRefused("refused: docs/PROSPECT_ANCHOR_GATE.md section 18 is not empty; "
                         "the look is taken once")


def check_label(provider: str, report_targets: dict, fitted_ea: dict, step_z: str) -> None:
    """L1 and the eWAR v2 ban: the matrices and the anchor refit must both sit on fwar."""
    if str(provider) != "fwar":
        raise LabRefused(f"refused: the label provider is {provider!r}, not fwar "
                         "(section 16: never on the eWAR v2 label)")
    for side, tgt in report_targets.items():
        if "(fwar)" not in str(tgt or ""):
            raise LabRefused(f"refused: the {side} matrix report's target reads {tgt!r}, "
                             "not the fwar label")
    gen = str(fitted_ea.get("generated_at") or "")[:10]
    if not gen or gen < step_z:
        raise LabRefused(f"refused: empirical_anchors.generated_at {gen!r} predates the step Z "
                         f"entry {step_z}; step J did not run on this label")
    for key in ("generated_at", "cohort_window", "n_cohort"):
        if fitted_ea.get(key) in (None, ""):
            raise LabRefused(f"refused: the fitted file names no {key} (L1: a run that cannot "
                             "name all five stamps is void)")


# ---------------------------------------------------------------------------
# Real data (the look): loaders, read-only over production modules
# ---------------------------------------------------------------------------
def _augment_from_matrices(pool: dict) -> list[dict]:
    """Join the pooled curve lab's rows back to the matrices for the census fields and the
    debut year. The loader itself is reused unchanged (L2)."""
    import efv_dataset
    out = []
    for side in ("hit", "pit"):
        meta = {r["player_key"]: r for r in json.loads(
            efv_dataset.matrix_path(side).read_text(encoding="utf-8"))}
        for r in pool[side]:
            m = meta.get(r["player_key"]) or {}
            out.append({"player_key": r["player_key"], "side": side, "fv": r["fv"],
                        "war": r["war"], "censored": r["censored"], "year": r["year"],
                        "debut_year": m.get("debut_year"), "n_sources": m.get("n_sources"),
                        "fv_fangraphs": m.get("fv_fangraphs"),
                        "fv_mlb_pipeline": m.get("fv_mlb_pipeline")})
    return out


def load_real_frame(step_z: str) -> tuple[dict, dict, dict, dict]:
    """L1, L2 and L6 on the production artifacts. Returns (frame, stamps, identity, extras)."""
    import efv_dataset
    import empirical_anchors
    import war_source
    import storage
    import value_framework as vf
    sys.path.insert(0, str(ROOT / "tools"))
    import fv_outcome_curves_lab as curves

    fitted = json.loads(FITTED_PATH.read_text(encoding="utf-8"))
    ea = fitted.get("empirical_anchors") or {}
    reports = {}
    for side in ("hit", "pit"):
        p = efv_dataset.report_path(side)
        reports[side] = (json.loads(p.read_text(encoding="utf-8")).get("target")
                         if p.exists() else None)
    check_label(war_source.DEFAULT_PROVIDER, reports, ea, step_z)
    stamps = {"war_basis": {"provider": war_source.DEFAULT_PROVIDER,
                            "matrix_report_target": reports,
                            "board_label_term": next((t for t in
                                                      storage.BOARD_BASIS_FINGERPRINT.split("|")
                                                      if t.startswith("label=")), None)},
              "RESOLVED_THROUGH": efv_dataset.RESOLVED_THROUGH,
              "label_window_rule": {"SERVICE_ALIGNED_WINDOW": efv_dataset.SERVICE_ALIGNED_WINDOW,
                                    "_SERVICE_YEAR_CUT_MMDD": efv_dataset._SERVICE_YEAR_CUT_MMDD},
              "empirical_anchors_generated_at": ea.get("generated_at"),
              "empirical_anchors_cohort_window": ea.get("cohort_window"),
              "empirical_anchors_n_cohort": ea.get("n_cohort"),
              "served_anchors": ea.get("anchors"),
              "anchors_provenance": ea.get("anchors_provenance"),
              "use_empirical": bool(vf._config().get("anchor_calibration", {}).get("use_empirical")),
              "min_n_robust": vf._config().get("anchor_calibration", {}).get("min_n_robust")}
    if int(stamps["min_n_robust"] or 0) != MIN_N:
        raise LabRefused(f"refused: anchor_calibration.min_n_robust is {stamps['min_n_robust']}, "
                         f"the registered floor is {MIN_N}")
    # L2: the pooled curve lab's loader and identity checks, unchanged, against its own
    # published counts on the same label.
    pool, checks = curves.load_pool()
    published = (json.loads(POOLED_CURVE.read_text(encoding="utf-8")).get("pool") or {}
                 ).get("identity_checks") or {}
    identity = {"lab": "tools/fv_outcome_curves_lab.load_pool, unchanged", "checks": checks,
                "published": published, "vintage": curves.verify_vintage()}
    for side in ("hit", "pit"):
        for key in ("target_censored_mismatches", "consensus_fv_raw_mismatches",
                    "censored_flag_mismatches"):
            got = int(checks[side][key])
            ref = int((published.get(side) or {}).get(key, 0))
            if got > ref:
                raise LabRefused(f"refused: L2 {side} {key} {got} exceeds the pooled curve's "
                                 f"published {ref}; the run stops")
    if int(checks["cross_side_key_overlap"]) != 0:
        raise LabRefused("refused: L2 cross-side key overlap is not 0; the bootstrap would "
                         "not be player-clustered and the run is void")
    # L6: the anchor cohort reproduced from the DB at the fitted file's window.
    y0, y1 = [int(v) for v in ea["cohort_window"]]
    cohort = empirical_anchors._cohort(empirical_anchors._DB_DEFAULT, y0, y1)
    n_fit = int(ea["n_cohort"])
    if abs(len(cohort) - n_fit) > 0.01 * n_fit:
        raise LabRefused(f"refused: L6 the DB reproduces n_cohort {len(cohort)} against the "
                         f"fitted file's {n_fit}, outside 1 percent; the partition is not the "
                         "fit frame")
    identity["L6"] = {"cohort_window": [y0, y1], "n_cohort_fitted": n_fit,
                      "n_cohort_reproduced": len(cohort), "within_1pct": True}
    frame = {"rows": _augment_from_matrices(pool), "cohort_keys": sorted(cohort.keys())}
    extras = {"fitted": fitted, "vf": vf}
    return frame, stamps, identity, extras


def named_row_block(vf, fitted_anchor) -> dict | None:
    """Section 0 row 6 and section 15: the served anchor at the named row's FV beside the
    served path mean, computed by code (never read from data/mlb_projections.json), with no
    disposition attached. Read-only on data/xfv.json."""
    try:
        by = json.loads((DATA / "xfv.json").read_text(encoding="utf-8")).get("by_player") or {}
    except (OSError, ValueError):
        return {"player_key": NAMED_ROW["player_key"], "available": False}
    rec = by.get(NAMED_ROW["player_key"]) or {}
    out = dict(NAMED_ROW)
    out["available"] = bool(rec)
    out["served_xfv_grade"] = rec.get("xfv_grade")
    out["served_xfv_grade_quantile"] = rec.get("xfv_grade_quantile")
    out["served_consensus_fv"] = rec.get("consensus_fv")
    out["anchor_at_efv_in_commit"] = _r(fitted_anchor(NAMED_ROW["efv_in_commit"]), 4)
    out["anchor_at_served_grade"] = (_r(fitted_anchor(rec["xfv_grade"]), 4)
                                     if rec.get("xfv_grade") is not None else None)
    out["expected_five_year_per_season_in_commit"] = round(
        NAMED_ROW["expected_five_year_in_commit"] / 5.0, 4)
    price_fv = rec.get("xfv_grade_quantile")
    if price_fv is not None:
        try:
            is_pit = (rec.get("side") == "pit")
            role = vf._role_key(is_pit)
            probs = vf.p_bucket_given_fv(float(price_fv), is_pit)
            scale = vf._war_scale_for(float(price_fv), role)
            paths = [vf._bucket_season_wars(role, i, False, None, scale)
                     for i in range(len(probs))]
            n_yrs = len(paths[0])
            mean_path = [sum(pr * paths[i][t] for i, pr in enumerate(probs))
                         for t in range(n_yrs)]
            out["served_path_mean_per_season_at_pricing_grade"] = _r(
                sum(mean_path[:5]) / min(5, len(mean_path)), 4)
            out["served_path_basis"] = ("value_framework.p_bucket_given_fv x "
                                        "_bucket_season_wars at xfv_grade_quantile, "
                                        "five-season mean, no calibration shift, no age")
        except Exception as exc:  # the path is a report, never a verdict
            out["served_path_mean_per_season_at_pricing_grade"] = None
            out["served_path_error"] = str(exc)[:200]
    out["disposition"] = None
    out["note"] = "published beside the anchor so the reconciliation is done by code; nothing about the row is adjudicated"
    return out


_BANNED_KEYS = ("warChamp", "warY1Champ", "proj_ml", "proj_lgbm", "mlb_projections")


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_keys(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")
    else:
        yield path


def write_artifact(art: dict, path: Path) -> None:
    """L7, enforced on the artifact's KEYS: no field derives from a projection input. The
    criterion sentence itself names the banned file, so the check is on keys, not text."""
    for key_path in _walk_keys(art):
        low = key_path.lower()
        if any(b.lower() in low for b in _BANNED_KEYS):
            raise LabRefused(f"refused: the artifact carries a projection-derived field {key_path} (L7)")
    text = json.dumps(art, indent=1, default=_json_default)
    path.write_text(text, encoding="utf-8")


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not serialisable: {type(o).__name__}")


# ---------------------------------------------------------------------------
# Section 11: the lever, only under MISCALIBRATED
# ---------------------------------------------------------------------------
def _clemens_prior_per_season():
    """11.1: 0.5 * (clemens_hit + clemens_pit), each with the pooled curve lab's declared
    linear ramp, in per-season units (the tables are six-season totals)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import fv_outcome_curves_lab as curves
    hit, pit = curves._prior_clemens("hit"), curves._prior_clemens("pit")
    return lambda fv: 0.5 * (hit(fv) + pit(fv)) / TARGET_SEASONS


def _lever_cells(rows: list[dict]) -> dict:
    """Knot cells [k - 2.5, k + 2.5) for 45..65 and [67.5, 80] for 70, raw means of war / 6."""
    out = {}
    for k in V2_KNOTS:
        lo, hi = k - 2.5, (80.0 if k == 70.0 else k + 2.5)
        sub = [r["war"] / TARGET_SEASONS for r in rows
               if lo <= r["fv"] <= hi and (k == 70.0 or r["fv"] < hi)]
        out[k] = {"n": len(sub), "raw_mean": (sum(sub) / len(sub)) if sub else None}
    return out


def fit_v2_table(rows: list[dict], served: dict, prior) -> dict:
    """11.1 on a row list: the shrunk raw cell means, the prior-only 80 knot, the served
    sub-45 knots byte for byte, the monotone non-decreasing repair and its maximum move."""
    cells = _lever_cells(rows)
    raw, prior_v = {}, {}
    for k in V2_KNOTS:
        c = cells[k]
        p = float(prior(k))
        prior_v[k] = p
        n = c["n"]
        raw[k] = ((n * c["raw_mean"] + V2_K_SHRINK * p) / (n + V2_K_SHRINK)) if n else p
    raw[V2_PRIOR_ONLY_KNOT] = float(prior(V2_PRIOR_ONLY_KNOT))
    prior_v[V2_PRIOR_ONLY_KNOT] = raw[V2_PRIOR_ONLY_KNOT]
    anchors = {}
    for k, v in sorted(served.items(), key=lambda kv: float(kv[0])):
        if float(k) < 45:
            anchors[str(k)] = v            # byte for byte
    prev, max_move = None, 0.0
    for k in sorted(raw):
        v = raw[k] if prev is None else max(raw[k], prev)
        max_move = max(max_move, v - raw[k])
        anchors[str(int(k))] = round(v, 3)
        prev = v
    return {"anchors": anchors, "raw_shrunk": {str(int(k)): _r(v, 6) for k, v in raw.items()},
            "prior_per_knot": {str(int(k)): _r(v, 6) for k, v in prior_v.items()},
            "rows_per_knot": {str(int(k)): cells[k]["n"] for k in V2_KNOTS},
            "raw_cell_mean": {str(int(k)): _r(cells[k]["raw_mean"], 6) for k in V2_KNOTS},
            "monotone_repair_max_move": _r(max_move, 6), "k_shrink": V2_K_SHRINK}


def _served_interp(served: dict):
    return interp_anchor(served)


def twin_scalar(rows: list[dict], served: dict) -> dict:
    """11.3: the best single scalar s on the served table at knots 45 and up, fitted by
    cell-n-weighted least squares against the raw cell means."""
    cells = _lever_cells(rows)
    sv = _served_interp(served)
    num = den = 0.0
    for k in V2_KNOTS:
        c = cells[k]
        if not c["n"]:
            continue
        a = float(sv(k))
        num += c["n"] * a * c["raw_mean"]
        den += c["n"] * a * a
    s = (num / den) if den else 1.0
    anchors = {}
    for k, v in sorted(served.items(), key=lambda kv: float(kv[0])):
        anchors[str(k)] = v if float(k) < 45 else round(float(v) * s, 3)
    return {"scale": round(s, 3), "anchors": anchors}


def _loss_sq(rows: list[dict], table: dict) -> float:
    """Cell-n-weighted squared error of a table against the raw cell means."""
    cells = _lever_cells(rows)
    f = interp_anchor(table)
    num = den = 0.0
    for k in V2_KNOTS:
        c = cells[k]
        if c["n"]:
            num += c["n"] * (float(f(k)) - c["raw_mean"]) ** 2
            den += c["n"]
    return (num / den) if den else 0.0


def _loss_abs(rows: list[dict], table: dict) -> tuple[float, float]:
    """Cell-n-weighted mean absolute residual of a table against the raw cell means of
    `rows`; returns (weighted sum, weight) so folds pool."""
    cells = _lever_cells(rows)
    f = interp_anchor(table)
    num = den = 0.0
    for k in V2_KNOTS:
        c = cells[k]
        if c["n"]:
            num += c["n"] * abs(float(f(k)) - c["raw_mean"])
            den += c["n"]
    return num, den


def incumbent_rule_table(rows: list[dict], served: dict, public_reference: dict) -> dict:
    """11.4's comparator: derive_empirical_war_anchors's arithmetic (the 0.5 public blend with
    the thin-cell extra, monotone, two decimals) on the given rows at this gate's cells."""
    cells = _lever_cells(rows)
    ref = {float(k): float(v) for k, v in public_reference.items()}
    anchors = {}
    for k, v in sorted(served.items(), key=lambda kv: float(kv[0])):
        if float(k) < 45:
            anchors[str(k)] = v
    prev = None
    for k in list(V2_KNOTS) + [V2_PRIOR_ONLY_KNOT]:
        c = cells.get(k, {"n": 0, "raw_mean": None})
        rt = ref.get(k)
        if rt is None:
            rt = max((ref[x] for x in ref if x <= k), default=0.0)
        n = c["n"]
        if n == 0:
            val = rt
        else:
            w = min(0.95, 0.5 + 0.4 * max(0.0, 1.0 - n / MIN_N))
            val = (1.0 - w) * c["raw_mean"] + w * rt
        v = val if prev is None else max(val, prev)
        anchors[str(int(k))] = round(v, 2)
        prev = v
    return anchors


def out_of_fold_check(rows: list[dict], served: dict, prior, public_reference: dict,
                      cohort_window) -> dict:
    """11.4: forward-chained decision years 2016..2021; fit v2, the twin and the incumbent
    rule on rows with year <= Y - 1; score cells on year Y; cell-n-weighted mean absolute
    residual pooled over folds; paired bootstrap over players B 2000 seed 20260923;
    one-sided MDE95; PASS needs v2 ahead of the incumbent rule by more than the floor and
    at least 4 of 6 folds in its favour."""
    rng = np.random.default_rng(SEED)
    folds = []
    y0, y1 = (int(cohort_window[0]), int(cohort_window[1])) if cohort_window else (None, None)
    for y in OOF_YEARS:
        test = [r for r in rows if r["year"] == y and r["cell"]]
        train = [r for r in rows if r["year"] is not None and r["year"] <= y - 1]
        if not test or not train:
            folds.append({"year": y, "n_test": len(test), "n_train": len(train),
                          "scored": False})
            continue
        v2 = fit_v2_table(train, served, prior)["anchors"]
        twin = twin_scalar(train, served)["anchors"]
        inc = incumbent_rule_table(train, served, public_reference)
        losses = {"v2": _loss_abs(test, v2), "twin": _loss_abs(test, twin),
                  "incumbent_rule": _loss_abs(test, inc), "served": _loss_abs(test, served)}
        # paired bootstrap over the fold's test players (the fits stay fixed)
        diffs = np.empty(B_BOOT)
        for b in range(B_BOOT):
            idx = rng.integers(0, len(test), size=len(test))
            samp = [test[i] for i in idx]
            li, _ = _loss_abs(samp, inc)
            lv, _ = _loss_abs(samp, v2)
            diffs[b] = li - lv
        folds.append({"year": y, "n_test": len(test), "n_train": len(train), "scored": True,
                      "tables": {"v2": v2, "twin": twin, "incumbent_rule": inc},
                      "loss": {k: _r(v[0] / v[1], 6) if v[1] else None for k, v in losses.items()},
                      "weight": losses["v2"][1],
                      "served_partially_in_sample": (y0 is not None and y0 <= y <= y1),
                      "v2_ahead": losses["v2"][0] < losses["incumbent_rule"][0],
                      "_diffs": diffs, "_num": {k: v[0] for k, v in losses.items()}})
    scored = [f for f in folds if f["scored"]]
    w_total = sum(f["weight"] for f in scored)
    pooled = {k: (sum(f["_num"][k] for f in scored) / w_total if w_total else None)
              for k in ("v2", "twin", "incumbent_rule", "served")}
    if scored and w_total:
        pooled_diffs = sum(f["_diffs"] for f in scored) / w_total
        se = float(pooled_diffs.std(ddof=1))
    else:
        se = None
    diff = ((pooled["incumbent_rule"] - pooled["v2"])
            if pooled["incumbent_rule"] is not None and pooled["v2"] is not None else None)
    mde95 = (MDE_Z * se) if se is not None else None
    k_for = sum(1 for f in scored if f["v2_ahead"])
    passed = (diff is not None and mde95 is not None and diff > mde95
              and k_for >= OOF_MIN_FOLDS_FOR and len(scored) == len(OOF_YEARS))
    for f in folds:
        f.pop("_diffs", None)
        f.pop("_num", None)
    return {"folds": folds, "pooled_loss": {k: _r(v, 6) for k, v in pooled.items()},
            "improvement_incumbent_minus_v2": _r(diff, 6), "boot_se": _r(se, 6),
            "mde95_one_sided": _r(mde95, 6), "folds_in_v2_favour": k_for,
            "folds_scored": len(scored), "min_folds_for": OOF_MIN_FOLDS_FOR,
            "result": "PASS" if passed else "NULL", "b": B_BOOT, "seed": SEED,
            "comparator": "the incumbent RULE (derive_empirical_war_anchors's arithmetic) on the same fold rows",
            "statistic": "cell-n-weighted mean absolute residual against the raw cell means, pooled over folds"}


def run_lever(frame: dict, served: dict, prior, public_reference: dict, cohort_window,
              label_stamp: str) -> dict:
    """Section 11 end to end on read rows. Returns the lever block; the caller writes the
    key only on PASS."""
    rows, _drops = prepare_rows(frame.get("rows"))
    sv = _served_interp(served)
    fit = fit_v2_table(rows, served, prior)
    # 11.2 caps
    refused = None
    for k in V2_KNOTS:
        s_v = float(served.get(str(int(k)), served.get(int(k), sv(k))))
        v = float(fit["anchors"][str(int(k))])
        factor = (v / s_v) if s_v else None
        if factor is None or not (V2_FACTOR_CAP[0] <= factor <= V2_FACTOR_CAP[1]):
            refused = {"knot": int(k), "factor": _r(factor, 4), "cap": list(V2_FACTOR_CAP),
                       "sentence": SENTENCES["LEVER_REFUSED"].format(knot=int(k),
                                                                     factor=_r(factor, 3))}
            break
    if refused is None and fit["monotone_repair_max_move"] > V2_MAX_REPAIR_MOVE:
        refused = {"monotone_repair_max_move": fit["monotone_repair_max_move"],
                   "cap": V2_MAX_REPAIR_MOVE,
                   "sentence": ("A monotone repair moving a knot by more than 0.15 WAR per "
                                "season refuses the lever: the raw cells disagree with each "
                                "other by more than the tolerance.")}
    block = {"criterion": CRITERIA["lever"], "fit": fit, "caps": {"factor": list(V2_FACTOR_CAP),
             "max_repair_move": V2_MAX_REPAIR_MOVE}, "refused": refused}
    if refused:
        block["result"] = "REFUSED"
        return block
    # 11.3 the twin
    twin = twin_scalar(rows, served)
    loss_served = _loss_sq(rows, served)
    loss_v2 = _loss_sq(rows, fit["anchors"])
    loss_twin = _loss_sq(rows, twin["anchors"])
    imp_v2 = loss_served - loss_v2
    imp_twin = loss_served - loss_twin
    share = (imp_twin / imp_v2) if imp_v2 > 0 else None
    form = "scalar" if (share is not None and share >= TWIN_SHARE) else "table"
    chosen = twin["anchors"] if form == "scalar" else fit["anchors"]
    f_old, f_new = sv, interp_anchor(chosen)
    block["twin"] = {"scale": twin["scale"], "loss_served": _r(loss_served, 6),
                     "loss_v2": _r(loss_v2, 6), "loss_twin": _r(loss_twin, 6),
                     "share_captured": _r(share, 4), "rule": TWIN_SHARE, "form": form,
                     "slope_40_to_45_pre": _r((f_old(45) - f_old(40)) / 5.0, 6),
                     "slope_40_to_45_post": _r((f_new(45) - f_new(40)) / 5.0, 6)}
    # 11.4 out of fold on read rows
    oof = out_of_fold_check(rows, served, prior, public_reference, cohort_window)
    block["out_of_fold"] = oof
    block["result"] = oof["result"]
    if oof["result"] == "NULL":
        block["sentence"] = SENTENCES["LEVER_NULL"].format(mde95=oof["mde95_one_sided"],
                                                           k=oof["folds_in_v2_favour"])
    block["candidate"] = {"form": form, "anchors": chosen,
                          "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
                          "seed": SEED, "label": label_stamp,
                          "rows_per_knot": fit["rows_per_knot"],
                          "prior_per_knot": fit["prior_per_knot"],
                          "fitted_per_knot": fit["raw_shrunk"],
                          "served_per_knot": {str(int(k)): served.get(str(int(k)))
                                              for k in list(V2_KNOTS) + [80.0]},
                          "monotone_repair_max_move": fit["monotone_repair_max_move"],
                          "out_of_fold": oof["result"]}
    if form == "scalar":
        block["candidate"]["scale"] = twin["scale"]
    return block


def write_v2_key(fitted_path: Path, candidate: dict) -> None:
    """Write exactly one key, empirical_anchors_v2, into the fitted file, in the file's own
    format (json indent 2, sorted keys, the --fit writer's convention). Never --fit."""
    fitted = json.loads(fitted_path.read_text(encoding="utf-8"))
    fitted[V2_KEY] = candidate
    fitted_path.write_text(json.dumps(fitted, indent=2, sort_keys=True), encoding="utf-8")


def fit_v2_mode(artifact_path: Path = ARTIFACT, fitted_path: Path = FITTED_PATH,
                frame: dict | None = None, write: bool = True) -> dict:
    """--fit-v2: refused unless the artifact's verdict reads MISCALIBRATED. Takes no K,
    prior, side table or knot set (section 16)."""
    if not artifact_path.exists():
        raise LabRefused("--fit-v2 refused: no artifact; the verdict must exist first")
    art = json.loads(artifact_path.read_text(encoding="utf-8"))
    if art.get("verdict") != "MISCALIBRATED":
        raise LabRefused(f"--fit-v2 refused: the verdict reads {art.get('verdict')!r}, "
                         "not MISCALIBRATED (section 11)")
    if art.get("lever") not in (None, {}):
        raise LabRefused("--fit-v2 refused: the artifact already carries a lever block")
    fitted = json.loads(fitted_path.read_text(encoding="utf-8"))
    if V2_KEY in fitted:
        raise LabRefused(f"--fit-v2 refused: {V2_KEY} already exists in the fitted file")
    served = dict((fitted.get("empirical_anchors") or {}).get("anchors") or {})
    if not served:
        raise LabRefused("--fit-v2 refused: the fitted file carries no empirical_anchors")
    if frame is None:
        step_z = step_z_entry()
        frame, _stamps, _identity, _extras = load_real_frame(step_z)
    import value_framework as vf
    public_reference = vf._config().get("anchor_calibration", {}).get("public_reference", {})
    cohort_window = (fitted.get("empirical_anchors") or {}).get("cohort_window")
    label = json.dumps((art.get("label_stamps") or {}).get("war_basis"), sort_keys=True)
    block = run_lever(frame, served, _clemens_prior_per_season(), public_reference,
                      cohort_window, label)
    art["lever"] = block
    if write:
        write_artifact(art, artifact_path)
        if block["result"] == "PASS":
            write_v2_key(fitted_path, block["candidate"])
    return block


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def run_fixture(fixture_path: Path, out_path: Path, detect: bool = True) -> dict:
    """The whole reporting path on a fixture frame. Never the real artifact path."""
    if out_path.resolve() == ARTIFACT.resolve():
        raise LabRefused("fixture mode refuses to write the real artifact path")
    fx = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    anchor = interp_anchor(fx["anchors"])
    art = build_artifact({"rows": fx["rows"], "cohort_keys": fx.get("cohort_keys") or []},
                         anchor, stamps=fx.get("stamps") or {"fixture": True},
                         identity=fx.get("identity") or {"fixture": True},
                         named_row=None, run_meta={"mode": "fixture", "fixture": str(fixture_path)},
                         detect=detect)
    write_artifact(art, Path(out_path))
    return art


def run_look(today: _dt.date | None = None) -> dict:
    """THE LOOK. Every guard, in order, before a single row is read."""
    clock = check_clock(today)
    check_one_look()
    if _dt.date.fromisoformat(clock["today"]) > LOOK_SLIP_DATE:
        raise LabRefused(f"refused: after {LOOK_SLIP_DATE} the look slips with the epoch and "
                         "needs an amendment filed before it (section 14)")
    frame, stamps, identity, extras = load_real_frame(clock["step_z_entry"])
    vf = extras["vf"]
    fitted_anchor = vf.fv_to_6yr_avg_war
    served = (extras["fitted"].get("empirical_anchors") or {}).get("anchors") or {}
    f_check = interp_anchor(served)
    for k in (40.0, 45.0, 47.5, 50.0, 55.0, 60.0, 62.5, 65.0, 70.0, 80.0):
        if abs(float(fitted_anchor(k)) - float(f_check(k))) > 1e-9:
            raise LabRefused("refused: value_framework.fv_to_6yr_avg_war does not read the "
                             "fitted empirical_anchors table (the flag must be off)")
    art = build_artifact(frame, fitted_anchor, stamps=stamps, identity=identity,
                         named_row=named_row_block(vf, fitted_anchor),
                         run_meta={"mode": "look", **clock, "command": "python -u tools/prospect_anchor_gate.py"})
    write_artifact(art, ARTIFACT)
    return art


def _report(art: dict) -> None:
    print(f"verdict: {art['verdict']}")
    for name in CELL_NAMES:
        c = art["cells"][name]
        print(f"  cell {name:>3}  H n={c['H']['n']:>5} d={c['H']['d_c']} ci={c['H']['ci90']} "
              f"{c['H']['disposition']}  |  S n={c['S']['n']:>5} d={c['S']['d_c']} "
              f"ci={c['S']['ci90']} {c['S']['disposition']}  m_C={c['m_c']}")
    print(f"margin pin holds: {art['power']['margin_pin_holds']}")
    print(art["sentence"])
    print(art["unconditional_sentence"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixture", help="run the reporting path on a fixture frame (tests)")
    ap.add_argument("--out", help="where the fixture run writes (never the real artifact)")
    ap.add_argument("--no-detect", action="store_true", help="fixture mode: skip the detection and coverage simulations")
    ap.add_argument("--fit-v2", action="store_true", help="section 11; refused unless the verdict reads MISCALIBRATED")
    args = ap.parse_args(argv)
    try:
        if args.fit_v2:
            if args.fixture or args.out:
                raise LabRefused("--fit-v2 takes no arguments: no K, prior, side table or knots")
            block = fit_v2_mode()
            print(f"lever: {block['result']}")
            return 0
        if args.fixture:
            if not args.out:
                raise LabRefused("--fixture needs --out")
            art = run_fixture(Path(args.fixture), Path(args.out), detect=not args.no_detect)
            _report(art)
            return 0
        art = run_look()
        _report(art)
        return 0
    except LabRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
