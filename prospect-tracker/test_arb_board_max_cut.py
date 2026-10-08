# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /arbitration/ board applies the CBA maximum-cut floor after a
contracted season (owner answer M11-2, docs/ARBITRATION_GATE.md section 15).

The board chains each award off the panel's salary and cannot see a contract
the club has already signed for the next season; the salary path floored
those rungs at 80 percent of the signed salary and the board did not, so the
two printed different figures for the same season. The board now runs the
same walk, without re-predicting the rungs after a floored one.
"""

from __future__ import annotations

import copy

import arb_export as X
import salary_path as sp


def _steps():
    return [[2028, 5_950_000, 4_641_000, 7_259_000, "ARB 3"],
            [2029, 7_000_000, 5_180_000, 8_820_000, "ARB 4"]]


def test_a_rung_after_a_signed_season_is_floored_and_the_next_is_not_re_predicted():
    steps = _steps()
    n = X._apply_max_cut_after_contract(steps, {2027: 10_000_000}, 2027)
    assert n == 1
    assert steps[0][1:4] == [8_000_000, 8_000_000, 8_000_000]
    # 7.0M clears 80% of the floored 8.0M, so it stays as published
    assert steps[1][1] == 7_000_000


def test_no_signed_salary_moves_nothing_and_pre_arb_closes_the_carry():
    steps = _steps()
    assert X._apply_max_cut_after_contract(steps, {}, 2027) == 0
    assert steps == _steps()
    pre = [[2028, 780_000, 780_000, 780_000, "PRE-ARB"],
           [2029, 1_000_000, 780_000, 1_220_000, "ARB 1"]]
    assert X._apply_max_cut_after_contract(pre, {2027: 5_000_000}, 2027) == 0
    assert pre[1][1] == 1_000_000


def test_the_board_and_the_salary_path_print_the_same_figure():
    """The path's Article VI block on the same inputs, mode "ladder" so no
    closure season is added: every season it prices from the board equals
    the floored board rung."""
    signed = {2027: 10_000_000}
    board = _steps()
    X._apply_max_cut_after_contract(board, signed, 2027)
    raw = {"steps": [{"season": s[0], "usd": s[1], "lo": s[2], "hi": s[3], "tok": s[4]}
                     for s in _steps()]}
    path = sp.salary_path(1, first_season=2027, horizon=5,
                          contract={"salary_by_year": {"2027": 10_000_000},
                                    "signed_through": 2027},
                          board_row=copy.deepcopy(raw), league_min={2027: 780_000},
                          mode="ladder", raise_fn=None)
    got = {c["season"]: c["usd"] for c in path["seasons"] if c["src"] == "arb_ladder"}
    assert got == {s[0]: s[1] for s in board}
