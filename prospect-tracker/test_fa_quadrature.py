# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Deal+ quadrature grid is load-bearing for published VERDICT LABELS.

fa_mc.QUAD_TAUS is an interior grid on the 5% marks. It never evaluates u below
0.05 or above 0.95, so it truncates exactly the convex tail the Jensen correction
exists to capture, and it comes out 7.4% low against a converged reference.

That is a real defect and the lane's own gate says converging it helps: signed
bias -1.761 to -1.137 against a realized $12.447M, delta +0.624, CI95 [+0.551,
+0.705], P(right direction) 1.0000 on a winter-clustered paired bootstrap of 444
realized signings. It is NOT shipped because Deal+ = 100 * this value / price, so
converging the grid lifts every published Deal+ by a median 7.4% and flips 74 of
1,300 historical corpus verdicts unless the terciles move with it, and those
terciles already carry a re-cut the owner deferred.

The whole file is a tripwire, not a correctness check. Changing QUAD_TAUS is
allowed; changing it WITHOUT the edge re-cut is the thing that silently
re-labels the board. See docs/fa-2026-09-06/QUAD_CONVERGENCE.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fa_mc
import fa_market as fm

HERE = Path(__file__).parent
DOC = HERE / "docs" / "fa-2026-09-06" / "QUAD_CONVERGENCE.md"

SHIPPED_GRID = tuple(round(i / 20.0, 3) for i in range(1, 20))
# The converged column of the decision package, per position group.
CONVERGED_EDGES = {"SP": (95, 199), "RP": (71, 152), "C": (124, 307), "POS": (124, 281)}


def test_the_decision_package_is_on_disk():
    assert DOC.exists(), (
        "docs/fa-2026-09-06/QUAD_CONVERGENCE.md is gone. It carries the gate result, "
        "the re-cut edges, and the reason the grid is still i/20; without it the next "
        "reader re-derives all of it or, worse, changes the grid without knowing the "
        "verdict labels ride on it"
    )


def test_the_grid_has_not_moved_without_the_edges():
    """A grid change and an edge re-cut must land together, or not at all."""
    if tuple(fa_mc.QUAD_TAUS) == SHIPPED_GRID:
        return                              # option 1: hold. Nothing to check.
    # The grid moved. Then the edges must have moved WITH it.
    assert dict(fm.VERDICT_GROUP_EDGES) != {"SP": (86, 182), "RP": (65, 146),
                                            "C": (101, 243), "POS": (103, 237)}, (
        "fa_mc.QUAD_TAUS changed but fa_market.VERDICT_GROUP_EDGES is still the "
        "2026-07-30 cut. Deal+ = 100 * expected rational value / price, so a grid "
        "change lifts every Deal+ by roughly 7.4% and re-labels the board toward "
        "VALUE without anyone deciding to. Re-cut the edges in the same commit "
        "(docs/fa-2026-09-06/QUAD_CONVERGENCE.md section 5 has the numbers) or "
        "revert the grid."
    )


def test_the_shipped_grid_still_truncates_both_tails():
    """Pin the SHAPE of the defect, so the docstring's numbers keep describing it.

    If someone switches to a midpoint rule at the same node count, this goes red
    and the measured figures in fa_mc and in the gate doc need re-taking, because
    a midpoint rule on 19 nodes already recovers most of the gap.
    """
    if tuple(fa_mc.QUAD_TAUS) != SHIPPED_GRID:
        pytest.skip("the grid moved; the recorded gap figures no longer apply")
    taus = sorted(fa_mc.QUAD_TAUS)
    assert taus[0] == 0.05 and taus[-1] == 0.95, (
        "QUAD_TAUS no longer spans 0.05 to 0.95, so the 7.4% understatement recorded "
        "in fa_mc.expected_tier_value_usd and the gate doc is measuring a grid that "
        "is not the one that ships"
    )
    assert len(taus) == 19


def test_the_understatement_is_stated_not_called_slight():
    """The docstring must carry the measured size, not the word it used to use."""
    src = Path(fa_mc.__file__).read_text(encoding="utf-8")
    assert "understates the tails slightly" not in src, (
        "the quadrature note calls a 7.4% truncation 'slight' again"
    )
    assert "7.4%" in src or "1.0796" in src, (
        "the quadrature note no longer states the measured size of its own "
        "approximation, so a reader has to rediscover it"
    )


def test_the_converged_edges_are_recorded_for_whoever_ships_it():
    doc = DOC.read_text(encoding="utf-8")
    for group, (lo, hi) in CONVERGED_EDGES.items():
        assert f"{lo} / {hi}" in doc, (
            f"the converged {group} edges {lo}/{hi} are no longer in the decision "
            f"package, so option 2 cannot be executed from it"
        )
