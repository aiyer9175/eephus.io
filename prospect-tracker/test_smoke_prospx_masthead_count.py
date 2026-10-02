# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke audit 2026-10-01, finding SPR07 (PROSPX), as corrected by the quality
audit 2026-10-02, finding QPRC01.

The masthead read "7,964 prospects tracked" (stored board actives plus draft-board
and overseas rows) directly above "Showing 1-50 of 8076" (board rows plus the
provisional rows outside that total). SPR07 relabelled the total "scouted" and
titled it "graded on the prospect board ... The board also ranks provisional
prospects", both false: 2,701 of the 4,691 actives sit in the board's own
unranked "Not yet graded by any source" section. The masthead now reads
"prospects tracked" and its title gives the ranked count the page computes and
says the rest are listed, unranked, in that section. No number changes.
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
    assert "</strong> prospects tracked</span>" in fn, "the masthead total lost its label"
    assert "scouted prospects tracked" not in fn, (
        "the masthead calls a total that folds in 2,701 ungraded board actives 'scouted'")
    assert "also ranks provisional" not in fn, (
        "the title says the board ranks prospects its own section leaves unranked")
    assert "graded on the prospect board" not in fn, (
        "the title calls every board active graded")
    assert "carry a scouting-source grade and are ranked" in fn
    assert "listed, unranked, under" in fn
    assert "!inProvSection(p)" in fn, "the ranked count must come from the section rule the board uses"
