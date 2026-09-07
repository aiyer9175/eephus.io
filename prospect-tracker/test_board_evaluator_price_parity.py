# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A player must not carry two prices at once.

The Trade Machine renders a player through two code paths that read two
different fields off the SAME row of data/trade_values.json:

    the board table   -> trade_value_mm         (assets/trademachine.js:889, :1008)
    the deal evaluator-> posterior_surplus_mm   (assets/trademachine.js:1224, :1237)

`apply_platform_surplus` writes the same figure to both on every re-pointed row,
so those two names are one served price. The compute that runs BEFORE it emits
them as genuinely different quantities: trade_value_mm is the final price and
posterior_surplus_mm is the Kalman posterior, taken before scarcity, the
defensive floor, the option and Rule 5 premiums and the injury and worry
discounts. Any branch that forgets to write both therefore leaks the internal
quantity onto a served surface.

MEASURED 2026-09-06, before the fix: 20 rows quoted two prices. Emmanuel Clase
read $2.7M in the board table and $0.0M in the evaluator that prices a deal
containing him. Nineteen of the twenty had been moved onto the un-repointed
path that same day by the control-window gate; the twentieth predated it. The
board table and the evaluator are two views of one number, and nothing pinned
them together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DATA = HERE / "data"
TOL = 0.051          # both fields are rounded to one decimal


def _board():
    p = DATA / "trade_values.json"
    if not p.exists():
        pytest.skip("trade_values.json not built on this machine")
    return json.loads(p.read_text(encoding="utf-8")).get("players") or []


def test_board_price_and_evaluator_price_are_the_same_number():
    """Every priced row shows one price on both surfaces."""
    split = [
        (r.get("player_key"), r.get("surplus_source"),
         r["trade_value_mm"], r["posterior_surplus_mm"])
        for r in _board()
        if r.get("trade_value_mm") is not None
        and r.get("posterior_surplus_mm") is not None
        and abs(float(r["trade_value_mm"]) - float(r["posterior_surplus_mm"])) > TOL
    ]
    assert not split, (
        f"{len(split)} row(s) quote a different price in the board table than in "
        f"the deal evaluator, e.g. "
        + "; ".join(f"{k} [{s}] board ${tv}M vs evaluator ${ps}M"
                    for k, s, tv, ps in split[:5])
    )


def test_a_priced_row_is_priced_on_both_surfaces():
    """Neither field may be null while the other carries a number.

    A row with trade_value_mm and no posterior_surplus_mm renders on the board
    and is unbuyable in the evaluator; the reverse prices a deal around a player
    the board says has no price. Both unpriced together is fine and is what the
    inactive and unrepointable ledgers deliberately produce.
    """
    half = [(r.get("player_key"), r.get("surplus_source"))
            for r in _board()
            if (r.get("trade_value_mm") is None) != (r.get("posterior_surplus_mm") is None)]
    assert not half, (
        f"{len(half)} row(s) are priced on one surface and unpriced on the other: "
        f"{half[:5]}"
    )


def test_the_unrepointed_path_is_covered_by_this_test():
    """Guard against the invariant passing because the risky path is empty.

    Every branch of `apply_platform_surplus` except one assigns both fields from
    the same local. The `bayes_unrepointed` branch assigns neither, and is where
    the 20 split prices came from. If that branch ever stops appearing on the
    board the two tests above still pass while testing nothing about it, so say
    so out loud instead of going quietly green.
    """
    n = sum(1 for r in _board() if r.get("surplus_source") == "bayes_unrepointed")
    if not n:
        pytest.skip("no bayes_unrepointed rows on this board; the parity tests "
                    "above no longer exercise the branch that broke")
    assert n > 0


def test_withheld_backgrade_stamp_has_a_reader():
    """`efv_backgrade_withheld` must render somewhere a reader looks.

    The stamp's stated justification is that "a row that quietly changes basis
    is indistinguishable from one that never did". That is only true if the
    change reaches a surface. It shipped with ZERO readers in the frontend.
    """
    stamped = [r for r in _board() if r.get("efv_backgrade_withheld")]
    if not stamped:
        pytest.skip("no withheld rows on this board")
    js = (HERE / "assets" / "trademachine.js").read_text(encoding="utf-8")
    assert "efv_backgrade_withheld" in js, (
        f"{len(stamped)} board row(s) carry efv_backgrade_withheld and no "
        f"frontend code reads it"
    )
