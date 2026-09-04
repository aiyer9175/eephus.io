# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR v2 fielding blend: the two endpoints must be exact.

eWAR v1 REPLACED B-Ref's rfield with the Statcast read wherever Statcast
covered the innings. The v1 attribution arms then measured that the fielding
swap alone lost BOTH gates (same-season team-wins r 0.8777 and next-season
0.2255, against a bWAR baseline of 0.8803 / 0.2481), while the pitching swap
paid for itself. The mechanical reason is that the two do not measure the same
quantity: Savant FRP is range, and B-Ref rfield also carries arm, catcher
framing and blocking, first-base scoops and the double-play pivot. A
replacement therefore swaps a better metric in for a NARROWER one and drops
real value.

v2 blends over the covered fraction instead. The whole design rests on the
blend being a true interpolation between the two incumbents, so the endpoints
are asserted here rather than assumed:

    w = 1.0  ->  exactly eWAR v1
    w = 0.0  ->  exactly bWAR's fielding

If either endpoint drifts, every w in between is measuring something nobody
chose, and the grid search that picks w would be selecting on a broken axis.

Since the 2026-09-03 epoch eWAR v2 is the SERVED series (war_source default
provider), so the w = 0.0 endpoint is also the served-copy statement
'position players match bWAR except in seasons they also pitched': a drift here
would make that copy false.

The exception clause is not hedging. Measured 2026-09-04 during the label epoch:
107 of 1,899 hitter rows on the eFV board carry a season where the player also
took the mound, 183 of those 187 seasons under 10 IP, and the pitching swap
re-prices them. The FIP re-pricing strips the balls in play that are most of the
damage in a blowout inning, so it can hand a position player +0.68 WAR for 1.0 IP.
The fielding endpoint asserted below is untouched by that; the copy is what had to
change, because the old wording claimed an identity the pitching arm does not
promise. See docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md section 7.

These tests exercise the arithmetic directly rather than running build(), which
needs the war_daily frames and several minutes; the arithmetic under test is a
closed-form expression and is reproduced here from the shipped source so a
change to one and not the other fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = (Path(__file__).parent / "ewar.py").read_text(encoding="utf-8")


def blend(runs_statcast: float, rfield_bref: float, share: float, w: float) -> float:
    """The shipped path, guard included.

    The guard is part of the contract, not boilerplate: ewar.build short-circuits
    to plain rfield when there is no Statcast coverage at all, BEFORE the blend
    expression runs. Modelling the expression without it would assert a property
    the shipped code does not have (and, on the first draft of this file, did:
    the zero-coverage case only holds because of the guard).
    """
    if share <= 0:
        return rfield_bref
    covered = w * runs_statcast + (1.0 - w) * (rfield_bref * share)
    return covered + rfield_bref * (1.0 - share)


CASES = [
    # (statcast runs, bref rfield, covered share)
    (8.0, 3.0, 1.00),     # full coverage, Statcast likes him more
    (-6.0, 2.0, 1.00),    # full coverage, and they disagree in sign
    (4.0, 4.0, 0.60),     # partial coverage, agreeing
    (0.0, -9.0, 0.35),    # mostly uncovered, bref strongly negative
    (12.5, -1.5, 0.85),
    (0.0, 0.0, 0.50),     # degenerate
]


@pytest.mark.parametrize("statcast,bref,share", CASES)
def test_w_one_reproduces_v1_exactly(statcast, bref, share):
    """v1 was: statcast over covered innings, rfield pro-rated over the rest."""
    v1 = statcast + bref * (1.0 - share)
    assert blend(statcast, bref, share, 1.0) == pytest.approx(v1, abs=1e-12)


@pytest.mark.parametrize("statcast,bref,share", CASES)
def test_w_zero_reproduces_bwar_exactly(statcast, bref, share):
    """At w=0 the Statcast read must vanish, whatever its value or coverage."""
    assert blend(statcast, bref, share, 0.0) == pytest.approx(bref, abs=1e-12)


@pytest.mark.parametrize("statcast,bref,share", CASES)
def test_blend_is_monotone_between_the_endpoints(statcast, bref, share):
    lo, hi = blend(statcast, bref, share, 0.0), blend(statcast, bref, share, 1.0)
    vals = [blend(statcast, bref, share, w) for w in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert vals == sorted(vals) or vals == sorted(vals, reverse=True), (
        "the blend is not monotone in w, so a grid search over w is not "
        "searching a single axis")
    for v in vals:
        assert min(lo, hi) - 1e-9 <= v <= max(lo, hi) + 1e-9


def test_uncovered_innings_never_take_a_statcast_read():
    """A player with zero coverage must price identically at every w."""
    for w in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert blend(999.0, 5.0, 0.0, w) == pytest.approx(5.0, abs=1e-12)


def test_half_weight_is_the_average_over_covered_innings():
    """Sanity: at full coverage, w=0.5 is the midpoint of the two incumbents."""
    assert blend(10.0, 2.0, 1.0, 0.5) == pytest.approx(6.0, abs=1e-12)


# --- the shipped source must still contain this arithmetic ------------------

def test_build_exposes_the_blend_parameter():
    m = re.search(r"def build\((.*?)\) -> dict:", SRC, re.S)
    assert m, "could not find ewar.build"
    assert "fielding_blend_w" in m.group(1), (
        "build no longer takes fielding_blend_w; the v2 grid search has no axis")


def test_default_is_the_measured_optimum_zero():
    """The default is 0.0: eWAR v2 uses NO Statcast fielding.

    Measured over 2016-2025, 300 team-seasons, pitching swap on throughout, so
    w=0 is the pitching-only arm. Both FORWARD legs are monotone decreasing in
    w: next-season r 0.2524 -> 0.2359 and run-prevention |r| 0.3780 -> 0.3559 as
    w goes 0 -> 1. The blend was built to rescue the fielding swap and instead
    established the optimum is not to use it.

    This test previously pinned the default at 1.0 (eWAR v1). It moved because
    the evidence moved, which is the point of having built the axis.
    """
    assert re.search(r"w_blend\s*=\s*0\.0 if fielding_blend_w is None", SRC), (
        "the default blend weight is no longer 0.0. w>0 was measured to cost "
        "next-season signal AND run-prevention correlation, monotonically; do "
        "not raise it without re-running the grid in build()'s docstring")


def test_only_the_covered_fraction_is_blended():
    """Guards the exact expression, so a refactor cannot quietly re-weight
    the uncovered innings (which have no Statcast read to weight)."""
    assert "covered_e = w_blend * rec[\"runs\"] + (1.0 - w_blend) * (bref * share)" in SRC
    assert "e_field = covered_e + bref * (1.0 - share)" in SRC


def test_meta_records_the_weight():
    assert '"fielding_blend_w"' in SRC, (
        "the payload does not record which fielding configuration produced it")
