# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV 3.5 OD2 TOP-QUANT -- cross-side re-anchor of the PITCHER display-grade
tail above the display-55 knee (raw 52.5: the grade that displays as 55 or
better under the round-to-nearest eFV scale, the F-SIDE 55_plus_binding cell
boundary).

MOTIVATION (F-SIDE, data/xfv_side_fairness_eval.json): the per-side quantile
display map re-inflates pitcher tail share 2.47x vs the calibration-honest
rank_war frame; joint display-grade top-25 pitchers realized 5.09 mean
first-6yr WAR vs hitters 9.04.

STATUS: GATED INERT. The 2026-07-15 evaluation (data/xfv_topquant_eval.json)
REJECTED every fitted candidate at the pre-registered primary gate (joint
top-25 gap <= +2.45 with CI90 covering 0): the pitcher display tail carries no
realized-WAR gradient (OLS slope -0.02, Theil-Sen LOFO ratio range 0.05-0.70),
so monotone tail relabeling cannot honestly close the gap. active_remap()
therefore returns None -- the efv_score hooks are no-ops and every published
number is byte-identical -- unless a FUTURE re-registered eval artifact stamps
ship.enabled AND ship.gate_pass true. Do not flip those flags by hand; they
are written by the eval line only.

Remap contract when active (candidate_if_reregistered):
    f(g) = g                                for g <  knee_raw
    f(g) = knee + slope_ratio * (g - knee)  for g >= knee_raw   (pitchers only)
Monotone within side by construction (slope_ratio in (0, 1]); rows below the
knee byte-identical; rank_war / xfv_grade (realized) / p_bucket / p_bust are
never touched (they live upstream of the display map)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
_EVAL_PATH = DATA_DIR / "xfv_topquant_eval.json"
_CACHE: dict = {}


def active_remap() -> dict | None:
    """The shipping remap parameters, or None when the line is gated off.
    Reads data/xfv_topquant_eval.json meta once per process: requires
    ship.enabled AND ship.gate_pass (both stamped by the eval line, never by
    hand) plus a sane slope_ratio in (0, 1)."""
    if "remap" in _CACHE:
        return _CACHE["remap"]
    remap = None
    try:
        ship = json.loads(_EVAL_PATH.read_text(encoding="utf-8")).get("ship") or {}
        if ship.get("enabled") and ship.get("gate_pass"):
            cand = ship.get("candidate_if_reregistered") or {}
            knee = float(cand.get("knee_raw", 52.5))
            ratio = float(cand.get("slope_ratio", 1.0))
            if 0.0 < ratio < 1.0:
                remap = {"knee": knee, "ratio": ratio}
    except (OSError, ValueError, TypeError):
        remap = None            # missing/malformed artifact -> gated off
    _CACHE["remap"] = remap
    return remap


def apply_display_remap(scored: list, is_pit: bool) -> int:
    """Apply the TOP-QUANT pitcher tail remap to a scored pool IN PLACE,
    AFTER the per-side quantile display map and BEFORE the surplus re-price
    (so surplus_mm follows the remapped displayed grade). Hitters and rows
    below the knee are untouched. Returns the number of rows changed (0 when
    gated off -- the current, gate-FAILED state)."""
    if not is_pit or not scored:
        return 0
    remap = active_remap()
    if remap is None:
        return 0
    knee, ratio = remap["knee"], remap["ratio"]
    n = 0
    for s in scored:
        g = s.get("xfv_grade_display")
        if g is None or g < knee:
            continue
        ng = round(knee + ratio * (g - knee), 1)
        if ng != g:
            s["xfv_grade_display"] = ng
            if s.get("consensus_fv") is not None:
                s["xfv_minus_consensus_display"] = round(ng - s["consensus_fv"], 1)
            n += 1
    if n:
        log.info("TOP-QUANT remap active: %d pitcher display grades re-anchored", n)
    return n
