# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /pal/ display pass (DISPLAY_pal, 2026-10-08).

One test per surface-quality finding the pass fixed, where a test can pin it:

  QREA14  light-theme ink: the RP->SP FIT score, the RP->SP direction chip and
          the SP->RP chip read at AA on the paper they sit on (the SP->RP chip
          lost its .85 opacity, which put it at 3.88:1).
  QREA15  the Conversion History and Position Fit sub-view strips are real
          tabs (role, selected state, the panel they control); a header that
          does not sort does not show the sort cursor; the per-row FIT term
          keeps its glossary hook but leaves the Tab order.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from test_qual_light_theme_ink import SITE, _decl, _light_dark, _ratio, _rule

ROOT = Path(__file__).parent
PAL_JS = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")


# ---- QREA14 -----------------------------------------------------------------
@pytest.mark.parametrize("selector", [".pal-hi", ".pal-dir--rp2sp", ".pal-dir--sp2rp"])
def test_pal_score_and_direction_inks_read_aa_in_light(selector):
    light, dark = _light_dark()
    body = _rule(SITE, selector)
    assert _decl(body, "opacity") is None, f"{selector} dims its text with opacity again"
    colour = _decl(body, "color")
    tok = re.fullmatch(r"var\((--[a-z0-9-]+)\)", colour or "")
    assert tok, (selector, colour)
    ink = light[tok.group(1)]
    for g in ("--bg-primary", "--bg-secondary", "--bg-tertiary"):
        r = _ratio(ink, light[g])
        assert r >= 4.5, f"{selector} {ink} on {g} {light[g]} reads {r:.2f}:1"


def test_the_cyan_reading_ink_leaves_dark_on_its_accent():
    _, dark = _light_dark()
    assert dark["--text-cyan"] == dark["--accent-cyan"]


# ---- QREA15 -----------------------------------------------------------------
def test_unsortable_pal_headers_do_not_show_the_sort_cursor():
    body = _rule(SITE, ".pal-app .mlbstats-table th:not([data-col])")
    assert _decl(body, "cursor") == "default"


def test_sub_view_strips_are_tabs_that_name_their_panel():
    src = PAL_JS[PAL_JS.index("function viewTab"):PAL_JS.index("function historyToggle")]
    assert 'role="tab"' in src and "aria-selected" in src and 'aria-controls="pal-view"' in src
    assert 'id="pal-view" role="tabpanel"' in src
    toggle = PAL_JS[PAL_JS.index("function historyToggle"):PAL_JS.index("function renderHistory")]
    assert 'viewTab("data-histview"' in toggle
    assert 'viewTab("data-pfview"' in PAL_JS


def test_the_row_fit_term_keeps_its_hook_and_leaves_the_tab_order():
    fit = PAL_JS[PAL_JS.index("function fitCell"):PAL_JS.index("function dirClass")]
    assert 'data-gl="' in fit and 'tabindex="-1"' in fit
