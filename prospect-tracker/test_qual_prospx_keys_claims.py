# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Quality audit 2026-10-02, findings QPRA02 and QPRC02 (PROSPX).

QPRA02: 52 glossary pills per board page, 5 per card, 9 FV history fold rows and
the Health overview tile were mouse-only (no tabindex, no role), and the glossary
popover had no role and never took focus. QPRC02: the eFV chip tooltip said the
model "predicts a calibrated 6-yr WAR outcome distribution" while the Debuted tab
measures a bust ECE of 0.134 and the registry row xfv_dist_recalibration exists
to fix that miscalibration. QPRC01 (the masthead) is pinned in
test_smoke_prospx_masthead_count.py.
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


def _controls() -> str:
    m = re.search(r'A11Y_CLICK_CONTROLS = "([^"]+)"', PAGE)
    assert m, "the click-only control selector is not declared"
    return m.group(1)


def test_qpra02_decorate_stamps_the_three_click_only_controls():
    sel = _controls()
    for part in (".g-term[data-term]", "tr.psh-fold-row", ".overview-tile[onclick]"):
        assert part in sel, part
    fn = _block(PAGE, PAGE.index("function decorateA11yRows()"))
    assert "querySelectorAll(A11Y_CLICK_CONTROLS)" in fn
    assert 'setAttribute("tabindex", "0")' in fn and 'setAttribute("role", "button")' in fn
    assert '"aria-expanded"' in fn, "fold rows announce their open state"
    toggle = _block(PAGE, PAGE.index("function _pshToggleFold("))
    assert '"aria-expanded"' in toggle, "the fold toggle keeps aria-expanded in step"
    # A Health tile on a card with no Health tab clicked nothing (franklin_arias):
    # it links only when the tab exists, so no focusable control is dead.
    assert re.search(r'_ovTile\(_ovHealth,\s*\(ilSection \|\| healthSection\) \? "health" : null\)', PAGE)


def test_qpra02_keydown_routes_controls_before_rows_and_skips_nested_buttons():
    start = PAGE.index('document.getElementById("content").addEventListener("keydown"')
    fn = _block(PAGE, start)
    i_ctl = fn.index("closest(A11Y_CLICK_CONTROLS)")
    i_click = fn.index("ctl.click()")
    i_row = fn.index('closest("[data-key], [data-org]")')
    assert i_ctl < i_click < i_row, "controls must be handled before the row branch"
    i_skip = fn.index('closest("a,button")')
    i_go = fn.index("goToPlayer(")
    assert i_row < i_skip < i_go, "the row handler must skip a,button targets before opening the card"


def test_qpra02_glossary_popover_is_a_dialog_that_takes_and_returns_focus():
    fn = _block(PAGE, PAGE.index("function openGlossaryPopover("))
    assert 'setAttribute("role", "dialog")' in fn
    assert '"aria-label"' in fn
    assert "pop.focus(" in fn, "focus moves into the popover on open"
    esc = fn[fn.index("const escDismiss"):]
    assert 'e.key === "Escape"' in esc
    assert "anchorEl.focus()" in esc, "Escape hands focus back to the term"


def test_qprc02_no_calibration_claim_in_the_efv_tooltip():
    assert "calibrated 6-yr WAR outcome distribution" not in PAGE
    assert "its calibration is measured on the Debuted tab" in PAGE
