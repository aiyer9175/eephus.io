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

import json
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


# --------------------------------------------------------------------------
# The display pass: the claim stays, the method folds, nothing is dropped
# --------------------------------------------------------------------------

def _r2(h, payload=None):
    pytest.importorskip("py_mini_racer")
    import test_management_render as R
    return R._render2(h, payload=payload)[0]


@pytest.mark.parametrize("h", ["#section=league", "#section=decisions&team=MIA&season=2026",
                               "#section=managers", "#section=clubs&team=MIA&season=2026"])
def test_the_realized_disclosure_is_the_lede_and_the_rest_is_one_click_down(h):
    """M10-21. The 94-word realized sentence printed in full under four tabs and
    pushed every table below the fold. Each tab now leads with its first sentence
    and keeps the whole of it, once, inside How this works."""
    import test_management_render as R
    full = ("Realized value, not skill. Each figure is the win probability that actually moved. "
            "A reliever who pitched well after a poor choice is in these numbers.")
    d = json.loads(json.dumps(R.SAMPLE2))
    d["decisions"]["realized_sentence"] = full
    d["clubs"]["columns_are_realized_not_skill"] = full
    html = _r2(h, d)
    assert html.count("Realized value, not skill.") == 1, h
    head, _, rest = html.partition("Realized value, not skill.")
    assert '<details class="mgmt-how"><summary>How this works</summary>' in rest, h
    tail = rest.split('<details class="mgmt-how">', 1)[1]
    assert "Each figure is the win probability that actually moved." in tail
    assert "A reliever who pitched well after a poor choice is in these numbers." in tail
    assert "The agent is the club-season." in html


def test_no_verdict_word_on_a_realized_extreme():
    """M10-04. The board headed a club-season's largest realized swing Best decision
    and Worst decision, a skill claim on a page that forbids one."""
    js = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")
    assert "Best decision" not in js and "Worst decision" not in js
    html = _r2("#section=managers")
    assert "Largest gain" in html and "Largest loss" in html
    assert re.search(r"<th>Largest gain <span class=\"mgmt-th-tag\">realized</span></th>", html)


def test_the_board_comes_before_the_dark_manager_block():
    html = _r2("#section=managers")
    assert html.index("Club-season leaderboard") < html.index("Managers <span class=\"mgmt-darktag\">not published</span>")
    assert "Blocked on: mgmt_managers ingest (M-MWAR-2)." in html, "the blocker is kept, below the board"


def test_the_census_windows_sentence_wraps_inside_the_table():
    """X06-13. The nowrap windows sentence widened the census table to 1,800 px."""
    html = _r2("#section=league")
    assert '<td class="mgmt-wrap">partition</td>' in html
    css = (ROOT / "assets" / "management.css").read_text(encoding="utf-8")
    assert ".mgmt-table--census td.mgmt-wrap { white-space: normal; min-width: 24ch; max-width: 36ch;" in css


def test_related_modules_are_linked_once_under_every_section():
    import test_management_render as R
    built = dict(R.SAMPLE2, routes={"franchise": True, "ledger": True})
    for h in ("#section=league", "#section=gate", "#section=clubs&team=MIA&season=2026"):
        html = _r2(h, built)
        assert html.count('class="mgmt-related"') == 1, h
        strip = html.split('class="mgmt-related"')[1]
        assert '<a href="/franchise/">Franchises</a>' in strip and '<a href="/ledger/">Club Ledger</a>' in strip
    html = _r2("#section=league")
    assert 'href="/franchise/"' not in html, "an unbuilt route is not linked"


def test_a_style_row_links_to_its_club_page_only_when_the_ledger_has_it():
    import test_management_render as R
    d = json.loads(json.dumps(R.SAMPLE2))
    d["teams"]["rows"] = [dict(d["teams"]["rows"][0], team="MIA", season=2026),
                          dict(d["teams"]["rows"][0], team="OAK", season=2024)]
    html = R._render("running", d, bunt_tab=True)
    assert '<a href="#section=clubs&team=MIA&season=2026" data-mlink="1">MIA</a>' in html
    assert "<tr><td>OAK</td>" in html, "a code the ledger does not carry is not linked to another club"


def test_management_css_has_no_dead_border_radius():
    """X06-25. site.css squares every corner with !important; the module's own
    radius declarations were dead and said the opposite of the brand."""
    css = (ROOT / "assets" / "management.css").read_text(encoding="utf-8")
    assert "border-radius" not in css
