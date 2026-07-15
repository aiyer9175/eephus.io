# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eFV production seam (efv_score.py) unit tests.

Pins the flagship grade's three load-bearing invariants:
  1. the realized-implied-FV mapping efv_score uses is monotone in E[6yr WAR]
     (higher projected WAR never yields a lower grade -> the OOS rank edge holds);
  2. the eFV display grade rounds to NEAREST 0.1 -- the deliberate exception to the
     site's grades-round-UP (ceiling) rule;
  3. the live injury + Statcast+ tilt factors are bounded (Statcast at +/-18%), so an
     extreme live input can never blow up the WAR projection / grade / surplus.

Pure-data, no network, no writes.
"""
import json
import math
from pathlib import Path

import pytest

import efv_score

DATA = Path(efv_score.__file__).parent / "data"


# --------------------------------------------------------------------------
# 1. Monotonicity of the realized-implied-FV mapping efv_score scores through
# --------------------------------------------------------------------------
# efv_score does: xfv_grade = vf.realized_implied_fv(xfv_war, is_pit, age=, position=).
# We drive that EXACT seam (efv_score.vf) so the test tracks whatever function the
# production module actually calls, not a hand-picked stand-in.
@pytest.mark.parametrize("is_pit", [False, True])
@pytest.mark.parametrize("age,pos", [(None, None), (21.0, "SS"), (26.0, "RP")])
def test_grade_is_monotone_in_expected_war(is_pit, age, pos):
    riv = efv_score.vf.realized_implied_fv
    wars = [-3.0, -1.0, 0.0, 0.5, 1.0, 2.0, 4.0, 7.0, 12.0, 20.0, 35.0]
    grades = [riv(w, is_pit, age=age, position=pos) for w in wars]
    assert all(g is not None for g in grades), "seam returned None for a real WAR input"
    # non-decreasing: a higher projected WAR is NEVER graded lower (ties allowed at floor/cap)
    for lo, hi in zip(grades, grades[1:]):
        assert hi >= lo - 1e-9, f"grade dropped as WAR rose: {lo} -> {hi}"
    # and the mapping actually moves (not a constant) across the range
    assert grades[-1] > grades[0]
    # clamped to the 20-80 grade scale
    assert all(20.0 - 1e-9 <= g <= 80.0 + 1e-9 for g in grades)


# --------------------------------------------------------------------------
# 2. eFV display grade rounds to NEAREST 0.1 (the exception to grades-round-UP)
# --------------------------------------------------------------------------
# efv_score stores the grade as round(xfv_grade, 1) (run / run_live / run_backgrade).
# That is round-to-nearest, NOT math.ceil -- the documented eFV exception to the
# site-wide "grades display the ceiling" rule.
def test_display_grade_rounds_to_nearest_not_up():
    riv = efv_score.vf.realized_implied_fv
    raw = riv(1.0, False)                       # lands at ~37.64 (a clean non-integer)
    assert raw is not None and abs(raw - round(raw)) > 0.05, "need a fractional raw grade"
    efv_display = round(raw, 1)                 # the convention efv_score applies
    # rounds to the nearest tenth -- here DOWN, which the ceiling rule could never do
    assert efv_display == pytest.approx(37.6, abs=1e-9)
    assert efv_display < raw                    # rounded down -> definitively not a ceiling
    assert efv_display != math.ceil(raw)        # grades-round-UP would give 38; eFV does not


def test_committed_grades_carry_the_round_to_nearest_signature():
    """The shipped artifact proves the rule in production: eFV grades sit on a 0.1
    grid AND many are non-integers -- impossible if they were integer-ceiled like FV."""
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    grades = [e["xfv_grade"] for e in doc["by_player"].values() if e.get("xfv_grade") is not None]
    assert grades, "no eFV grades in the committed artifact"
    assert all(abs(g - round(g, 1)) < 1e-9 for g in grades), "grades not quantized to 0.1"
    non_integer = [g for g in grades if abs(g - round(g)) > 1e-9]
    # a real share are non-integers -> not the integer round-UP convention FV grades use
    assert len(non_integer) > 0.1 * len(grades)


# --------------------------------------------------------------------------
# 3. Live tilt factors are bounded on extreme inputs
# --------------------------------------------------------------------------
def test_injury_factor_bounds():
    # every LIVE multiplier stacked at its worst -> bounded, never above 1.0
    worst = {"il_on": True, "il_type": "60-day IL", "il_days_12mo": 400.0,
             "il_stints_12mo": 9.0, "is_post_tj": True}
    f = efv_score._injury_factor(worst)
    assert 0.5 <= f <= 1.0
    # 0.70 * 0.82 * 0.92 (post-TJ no longer multiplies - owner 2026-07-15)
    assert f == round(0.70 * 0.82 * 0.92, 3), \
        "stacked worst case must be the three LIVE components only"
    # a healthy record is a no-op
    assert efv_score._injury_factor({}) == 1.0
    # Owner directive 2026-07-15: post-TJ STATUS alone (fully recovered, zero
    # IL time - the Kade Anderson case) is NOT an injury and carries NO penalty.
    assert efv_score._injury_factor({"is_post_tj": True}) == 1.0
    # missing / None fields (the only non-numeric the live board ever produces)
    # never throw or escape the band
    for r in ({"il_days_12mo": None}, {"il_on": True, "il_type": None},
              {"il_stints_12mo": None}, {"is_post_tj": True}):
        assert 0.5 <= efv_score._injury_factor(r) <= 1.0


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_statcast_factor_bounded_pm18pct(side):
    # SC+ is a 100-centered index; extreme values on either side clamp to +/-18%
    hi = efv_score._statcast_factor({"statcast_plus": 10_000}, side)
    lo = efv_score._statcast_factor({"statcast_plus": -10_000}, side)
    assert hi == pytest.approx(1.18, abs=1e-9)
    assert lo == pytest.approx(0.82, abs=1e-9)
    # every input stays inside the band
    for sc in (40, 70, 100, 130, 160, 1e9, -1e9):
        assert 0.82 <= efv_score._statcast_factor({"statcast_plus": sc}, side) <= 1.18
    # no Statcast+ (lower levels) or non-numeric -> untouched
    assert efv_score._statcast_factor({}, side) == 1.0
    assert efv_score._statcast_factor({"statcast_plus": None}, side) == 1.0
    assert efv_score._statcast_factor({"statcast_plus": "n/a"}, side) == 1.0
