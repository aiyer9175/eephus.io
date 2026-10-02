# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke audit 2026-10-01, findings SPR02, SPR03, SPR04 and SPR05 (PROSPX).

SPR02: the sticky .detail-tabs strip on a player card or farm detail sat at
top 0 under the sticky .section-tabs bar (z-index 50), so every tab was
covered at 1280 and the first row at 390. It now parks at the bar's height,
which a ResizeObserver writes to the root as --px-section-tabs-h.

SPR03: at 390 the board row's identity line held the headshot, the name and
three buttons, so the flex:1 name column fell to 0 px. The phone block now
gives the name a 96 px floor and lets the line wrap.

SPR04: a failed board payload replaced #content with developer copy (no role,
"python run_monthly.py", README) and wiped the section nav. It now paints the
pixel state component's failed kind (role=alert) under the kept section nav,
with a Retry that re-runs the boot.

SPR05: the Debuted header's Level label sat in the 28 px first track and
broke mid-word (LEVE / L). It prints Lvl on one line there.
"""
from __future__ import annotations

import re
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


def _media_blocks(max_px_low: int, max_px_high: int) -> list[str]:
    out = []
    for m in re.finditer(r"@media \(max-width: ?(\d+)px\) \{", PAGE):
        if max_px_low <= int(m.group(1)) <= max_px_high:
            out.append(_block(PAGE, m.start()))
    return out


def test_spr02_detail_tabs_park_below_the_section_bar():
    rule = _block(PAGE, PAGE.index("    .detail-tabs {"))
    assert "position: sticky;" in rule
    top = re.search(r"\n\s*top:\s*([^;]+);", rule).group(1).strip()
    assert top == "var(--px-section-tabs-h, 74px)", top
    # the variable is written from the live bar, on every boot that mounts it
    fn = _block(PAGE, PAGE.index("function _watchSectionTabsHeight()"))
    assert 'getElementById("section-tabs")' in fn and "offsetHeight" in fn
    assert 'setProperty("--px-section-tabs-h"' in fn and "ResizeObserver" in fn
    assert PAGE.count("_watchSectionTabsHeight();") >= 2


def test_spr03_phone_row_gives_the_name_a_floor_and_wraps_the_buttons():
    phone = _media_blocks(640, 640)
    blocks = "\n".join(phone)
    m = re.search(r"\.player-row-idrow > \.player-name-stack \{ min-width: (\d+)px !important; \}", blocks)
    assert m and int(m.group(1)) >= 96, "the 640px block gives .player-name-stack no floor"
    assert re.search(r"\.player-row-idrow \{ flex-wrap: wrap;", blocks)
    # the Debuted rows share the classes, so the same floor reaches them
    assert '<div class="player-row-idrow" style="display:flex;align-items:center;gap:10px;min-width:0;">' in PAGE
    # desktop keeps its one-line row: the floor and the wrap live only in the phone block
    rest = PAGE
    for b in phone:
        rest = rest.replace(b, "")
    assert "flex-wrap: wrap; row-gap: 4px;" not in rest


def test_spr04_failed_board_load_is_the_component_failed_kind_under_the_nav():
    boot = _block(PAGE, PAGE.index("async function _bootProspx()"))
    branch = _block(boot, boot.index("if (DATA.__error)"))
    assert "_renderBootFailure(content, DATA.__error);" in branch
    assert "run_monthly.py" not in branch and "README" not in branch
    fail = _block(PAGE, PAGE.index("function _renderBootFailure(content, detail)"))
    assert '_pxStateHTML("failed"' in fail
    assert "run_monthly.py" not in fail and "README" not in fail
    assert "The prospect board could not load. Try again in a moment." in fail
    assert "data-px-retry" in fail and "_bootProspx();" in fail
    assert 'querySelector("#section-tabs")' in fail and "content.appendChild(nav)" in fail
    assert 'meta.textContent = "Prospect data did not load."' in fail
    assert "console.error(" in fail
    helper = _block(PAGE, PAGE.index("function _pxStateHTML(kind, msg)"))
    assert "window.EephusState" in helper and "S.html(kind, msg)" in helper
    assert 'role="alert"' in helper


def test_spr05_debut_level_header_is_one_line_in_the_narrow_grid():
    blocks = [b for b in _media_blocks(640, 900) if ".debut-header, .debut-row {" in b]
    assert blocks, "no narrow debut grid block"
    b = blocks[0]
    assert ".debut-header .debut-level-cell { white-space: nowrap; }" in b
    assert ".debut-header .debut-lvl-short { display: inline; }" in b
    assert ('<span class="debut-level-cell" title="Level"><span class="debut-lvl-long">Level</span>'
            '<span class="debut-lvl-short" aria-hidden="true">Lvl</span></span>') in PAGE
    assert ".debut-header .debut-lvl-short { display: none; }" in PAGE
