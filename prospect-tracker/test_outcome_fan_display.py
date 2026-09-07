# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A percentile range must never be printed as if it contained its own headline.

THE MATH IS FINE AND MUST NOT BE "FIXED". A P10-to-P90 interval is a percentile
range; the surplus printed beside it is a MEAN. On a bust-heavy fan the two need
not contain each other, and at the bottom of the board they routinely do not. A
grade-20 bat carries P(bust) 0.915, so its 10th through 90th percentile all sit
on the $0-surplus floor while every dollar it is worth lives in the top decile.
brandon_lockridge is the clean case: p10 = p25 = p50 = p75 = p90 = 0.7, mean 1.5.

MEASURED 2026-09-06, before the display repair:
    data/xfv.json          4,825 of 9,505 rows with P10 == P90; 928 of those with
                           an expected surplus ABOVE P90.
    data/trade_values.json 3,957 zero-width bands; 592 that exclude the price in
                           the cell beside them.

Those rows rendered as "P10-P90 $0.7M-$0.7M" next to a headline of $1.5M, which
reads as a broken range, and one prospx site skipped the band outright on the
grounds that it "carries no information" when in fact it carries the single most
decision-relevant fact on the card: four outcomes in five land on the floor.

This file pins the WORDING, not the numbers. If a future change makes the fan
non-degenerate the counts move and these tests stay green; if a future edit drops
the flat-fan branch from a renderer, they go red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DATA = HERE / "data"


def _json(name):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def _fan_rows():
    by = _json("xfv.json").get("by_player") or {}
    out = []
    for key, r in by.items():
        d = r.get("dist") or {}
        lo = d.get("p10_mm") if d.get("p10_mm") is not None else r.get("band_p10_mm")
        hi = d.get("p90_mm") if d.get("p90_mm") is not None else r.get("band_p90_mm")
        if lo is None or hi is None:
            continue
        out.append((key, float(lo), float(hi), r.get("surplus_mm")))
    return out


def test_a_degenerate_fan_is_stated_not_printed_as_a_range():
    """prospx must have a flat-fan branch wherever it prints a P10-P90 range."""
    src = (HERE / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "function fmtFanRange(" in src, "the shared fan formatter is gone"
    assert "80%+ of outcomes at" in src, (
        "the flat-fan wording is gone; a degenerate fan will print as a range again"
    )
    # Every remaining literal "P10-P90 ${" template is a bare range with no flat
    # branch. The formatter exists precisely so there are none.
    bare = src.count("`P10-P90 ${")
    assert bare == 0, (
        f"{bare} site(s) still interpolate a bare P10-P90 range instead of calling "
        f"fmtFanRange, so a P10 == P90 row prints '$0.7M-$0.7M' there"
    )


def test_the_headline_outside_its_own_fan_is_said_out_loud():
    src = (HERE / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "function fanOutsideNote(" in src
    assert "sits above the 90th percentile" in src
    board = (HERE / "assets" / "trademachine.js").read_text(encoding="utf-8")
    assert "sits above the 90th percentile" in board, (
        "the board tooltip no longer explains a price that falls outside its range"
    )
    assert "More than 80% of modelled outcomes land at" in board, (
        "the board tooltip prints a zero-width band as a range again"
    )


def test_the_degenerate_case_is_real_on_this_build():
    """Guard against the wording tests passing over an empty case.

    If no served row is degenerate the two tests above still pass while pinning
    nothing, so say so rather than going quietly green.
    """
    rows = _fan_rows()
    flat = [r for r in rows if abs(r[2] - r[1]) < 1e-9]
    if not flat:
        pytest.skip("no degenerate fans on this build; the wording tests above "
                    "pin nothing about the case they were written for")
    assert len(flat) > 0


def test_the_published_fan_is_ordered_even_where_it_is_flat():
    """P10 <= P90 always. A crossed fan is a real defect, unlike a flat one."""
    crossed = [(k, lo, hi) for k, lo, hi, _ in _fan_rows() if hi < lo - 1e-9]
    assert not crossed, f"{len(crossed)} row(s) publish P90 below P10: {crossed[:5]}"


def test_board_bounds_are_ordered():
    rows = _json("trade_values.json")["players"]
    crossed = [(r.get("player_key"), r["trade_value_lo"], r["trade_value_hi"])
               for r in rows
               if r.get("trade_value_lo") is not None
               and r.get("trade_value_hi") is not None
               and float(r["trade_value_hi"]) < float(r["trade_value_lo"]) - 1e-9]
    assert not crossed, f"{len(crossed)} board row(s) publish hi below lo: {crossed[:5]}"
