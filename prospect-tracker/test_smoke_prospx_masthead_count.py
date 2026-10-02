# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke audit 2026-10-01, finding SPR07 (PROSPX).

The masthead read "7,964 prospects tracked" (graded board rows plus draft-board
and overseas rows) directly above "Showing 1-50 of 8076" (graded board rows plus
the provisional rows no source has graded). Two totals, nothing saying they
count different pools. The masthead now names its pool ("scouted prospects
tracked") and its title gives the split and says the board also ranks the
provisional pool. No number changes.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent
PAGE = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")


def _block(src: str, start: int) -> str:
    """The text from `start` through the brace that closes the first { after it."""
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError("unbalanced braces")


def test_spr07_masthead_count_names_the_pool_it_counts():
    fn = _block(PAGE, PAGE.index("function updateMeta()"))
    assert ("</strong> scouted prospects tracked</span>" in fn
            and "</strong> prospects tracked" not in fn
            and "The board also ranks provisional prospects no scouting source has graded yet" in fn), (
        "the masthead total prints a bare 'prospects tracked' while the board total "
        "folds in the provisional rows")
