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
import json
from pathlib import Path

import pytest

import arb_export as X
import salary_path as sp

ROOT = Path(__file__).parent


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


def test_the_served_board_and_the_served_path_agree_on_every_ladder_season():
    """Census X03-07's acceptance: an arbitration season the projections path
    takes from the board (src arb_ladder) carries the board's own figure."""
    try:
        board = json.loads((ROOT / "data" / "arbitration.json").read_text(encoding="utf-8"))
        proj = json.loads((ROOT / "data" / "mlb_projections.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pytest.skip("served artifacts absent")
    vint = next((v.get("salVintage") for v in proj.get("vets") or [] if v.get("salVintage")), None)
    if vint and vint != board.get("generated_at"):
        pytest.skip("the projections payload was priced off another board vintage")
    by = {r["m"]: {s[0]: s[1] for s in r["l"]} for r in board["rows"]}
    bad = []
    for v in proj.get("vets") or []:
        l = by.get(int(v["mlbam"])) if v.get("mlbam") else None
        for c in v.get("salPath") or []:
            if l and c[5] == "arb_ladder" and c[0] in l and l[c[0]] != c[1]:
                bad.append((v["key"], c[0], l[c[0]], c[1]))
    assert not bad, bad[:5]
