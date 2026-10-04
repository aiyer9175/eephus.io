# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /management/ display pass and the clubs-page accessibility findings it
carried (surface-quality audit 2026-10-02, DISPLAY_management).

  QCLA18  a glossary tooltip closes on Escape, and every module's masthead terms
          carry aria-describedby without the module wiring its own masthead;
  QCLA19  the section strips are tab strips a keyboard can walk (ArrowLeft,
          ArrowRight, Home, End), each tab names its panel and the panel names
          its tab; every management section opens with an h2.

The key and tooltip behaviour was measured in Chromium on /management/, /ledger/,
/franchise/, /hof/, /trademachine/ and /arbitration/ (the report in the lane's
scratchpad); these tests pin the code paths that produce it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
GL = (ROOT / "assets" / "eephus-gl.js").read_text(encoding="utf-8")
UI = (ROOT / "assets" / "eephus-ui.js").read_text(encoding="utf-8")


def test_escape_closes_a_glossary_tooltip():
    """QCLA18. #gl-tip stayed open after Escape whether hover or focus opened it."""
    m = re.search(r'addEventListener\("keydown", e => \{\s*if \(e\.key === "Escape" && _tipFor\) tipHide\(\);', GL)
    assert m, "no Escape handler closes the term tooltip"


def test_every_masthead_is_wired_by_the_glossary_runtime():
    """QCLA18. The masthead terms on /management/, /trademachine/, /hof/ and
    /arbitration/ had no aria-describedby because those modules never called
    EEPHUS_GL.wire on the server-rendered masthead."""
    i = GL.index('document.querySelectorAll(".section-head").forEach(h => wire(h))')
    assert i < GL.index("window.EEPHUS_GL = {"), "the masthead is wired before the API is published"


def test_one_shared_tablist_key_handler_with_a_stable_entry_point():
    """QCLA19. ArrowRight left focus on the same tab on every clubs-page strip."""
    assert "function wireTablist(list)" in UI and "wireTablist: wireTablist," in UI
    for key in ('"ArrowLeft"', '"ArrowRight"', '"Home"', '"End"'):
        assert key in UI.split("function wireTablist(list)")[1], key
    body = UI.split('document.addEventListener("keydown", function (e) {', 1)[1].split("});", 1)[0]
    assert "tabs[j].focus();" in body and "click()" not in body, "arrows move focus; they never activate"
    w = UI.split("function wireTablist(list)")[1].split("document.addEventListener")[0]
    assert 'setAttribute("role", "tabpanel")' in w and 'setAttribute("aria-controls", panel.id)' in w
    assert 'hasAttribute("aria-controls")' in w, "a strip whose template wires its panels is left alone"
    assert "attributeFilter: [\"aria-selected\"]" in w, "the panel label follows the selected tab"


def test_the_management_shell_wires_tabs_to_their_panel():
    import build_site as B
    html = B.build_management()
    tabs = re.findall(r'<button type="button" class="mlbstats-sectionbtn[^"]*" data-mgmtsection="([a-z]+)" role="tab" '
                      r'id="mgmt-tab-\1" aria-controls="mgmt-section"', html)
    assert len(tabs) == 10, tabs
    assert '<div id="mgmt-section" class="mlbstats-section" role="tabpanel" aria-labelledby="mgmt-tab-league">' in html
    js = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")
    assert 'panel.setAttribute("aria-labelledby", "mgmt-tab-" + state.section)' in js


@pytest.mark.parametrize("section", ["league", "running", "decisions", "clubs", "managers", "bunt",
                                     "reference", "gate", "challenges", "lineups"])
def test_every_management_section_opens_with_an_h2(section):
    """QCLA19. The Decisions view had only the page h1, and League went from h1 to h3."""
    pytest.importorskip("py_mini_racer")
    import test_management_render as R
    h = "#section=%s" % section
    if section in ("decisions", "clubs"):
        h += "&team=MIA&season=2026"
    html, _ = R._render2(h)
    if section == "bunt":
        html = R._render("bunt", bunt_tab=True)
    heads = re.findall(r"<(h[1-6])\b", html)
    assert heads and heads[0] == "h2", (section, heads[:3])
    levels = [int(x[1]) for x in heads]
    assert all(b - a <= 1 for a, b in zip(levels, levels[1:])), (section, levels)
