# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The /betting/ display pass (2026-10-07), one test per finding.

QREC04  the validation panel's "No." names the season-to-date fit, not the
        vintage backtest it sits under.
QREA07  the provisional and postseason tags (and the slate-lean and unpriced
        tags, which had the same defect) take focus, show their sentence on
        focus, and point aria-describedby at a node holding it.
QREA19  the section tabs control a tabpanel and move on the arrow keys; a
        board that arrives ordered says so; the /diamond/ table, which does not
        sort, is pinned in test_diamond_display_pass.py.
QREA21  the active segmented button and the book name in a highlighted row
        clear 4.5:1 on their tokens.
QREP03  player_links.json is fetched only by a section that prints a name.
QREP04  the shell reserves the feed strip and the section before first paint.
COPY    the masthead lede lost the sentence that repeats the Record tab, and the
        Futures method notes sit one click below the board; every pinned
        disclosure stays.

Offline: py_mini_racer over the module's own fixtures, the built shells, and
headless Chromium over a loopback server for the four browser facts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site
import test_betting as tb
import test_betting_policy_copy as pc
from conftest import serve_site

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# QREC04
# ---------------------------------------------------------------------------
def test_the_validation_no_names_the_season_to_date_fit():
    d = pc._base()
    assert d["model"]["validation"]["headline_mode"] == "contaminated"
    html = pc._validation(payload=d)
    text = pc._text(html)
    assert "<strong>No.</strong>" in html
    assert ("The board's served prices come from the season-to-date fit (contaminated "
            "mode), which cannot validate; the vintage backtest above grades the method "
            "out of sample and is what the gates read.") in text
    assert "Headline numbers come from the contaminated mode" not in text


def test_the_pick_tab_copy_of_the_panel_points_at_the_validation_tab():
    c = pc._ctx(pc._base())
    text = pc._text(c.eval("__show('potd')"))
    if "Is the model validated?" not in text:
        pytest.skip("this fixture renders no validation panel on the pick tab")
    assert "the vintage backtest on the Validation tab grades the method" in text


# ---------------------------------------------------------------------------
# QREA07
# ---------------------------------------------------------------------------
_TIP_RE = re.compile(r'<span class="([^"]*bt-tipped[^"]*)" tabindex="0" title="([^"]*)" '
                     r'data-tip="([^"]*)" aria-describedby="(bt-tip-[0-9a-z]+)">')


def test_the_provisional_tag_is_focusable_and_described():
    html = pc._ctx(pc._base()).eval("__show('potd')")
    tags = [m for m in _TIP_RE.finditer(html) if "bt-prov" in m.group(1)]
    assert tags, "no provisional tag rendered on the pick tab"
    for m in tags:
        assert m.group(2) == m.group(3), "the focus tip and the hover title disagree"
        assert m.group(2).startswith("Cleared a policy floor, not a measured threshold.")
    assert html.count("bt-prov") == len(tags), "a provisional tag escaped the focus wiring"


def test_the_postseason_tag_is_focusable_and_described():
    d = pc._base()
    games = d.get("team_bets") or []
    assert games, "fixture has no game cards"
    games[0]["game_type"] = "D"
    games[0]["series"] = "AL Division Series"
    c = pc._ctx(d)
    c.eval("__show('teams')")
    html = c.eval("__show('teams')")
    tags = [m for m in _TIP_RE.finditer(html) if "bt-post" in m.group(1)]
    assert tags, "no postseason tag rendered on the game card"
    assert tags[0].group(2) == ("AL Division Series: the model was fitted and graded on "
                                "regular-season games only")
    assert "never graded on a postseason game" in pc._text(html)


def test_no_tag_keeps_its_sentence_in_a_title_alone():
    """The four tag builders that used to emit a bare title now go through
    tipTag; a new one written the old way fails here."""
    for cls in ("bt-prov", "bt-post", "bt-totlean", "bt-unpriced"):
        assert f'<span class="bt-tag bt-tag-warn {cls}" title=' not in JS, cls
        assert f'tipTag("bt-tag bt-tag-warn {cls}"' in JS, cls
    assert ".bt-tipped:focus::after{content:attr(data-tip)" in JS


# ---------------------------------------------------------------------------
# QREA19
# ---------------------------------------------------------------------------
def test_the_tabs_control_a_tabpanel():
    shell = build_site.build_betting()
    ids = re.findall(r'data-bettingsection="(\w+)" role="tab" id="bt-tab-(\w+)" '
                     r'aria-controls="betting-section"', shell)
    assert len(ids) == 9 and all(a == b for a, b in ids)
    assert ('<div id="betting-section" class="mlbstats-section" role="tabpanel" '
            'aria-labelledby="bt-tab-potd">') in shell
    assert '"ArrowRight"' in JS and '"Home"' in JS and '"End"' in JS


# ---------------------------------------------------------------------------
# QREA21
# ---------------------------------------------------------------------------
def _hex(block: str, token: str) -> str:
    m = re.search(re.escape(token) + r":\s*(#[0-9A-Fa-f]{6})", block)
    assert m, token
    return m.group(1)


def _contrast(a: str, b: str) -> float:
    def lum(h):
        r, g, bl = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bl)
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_active_segment_and_the_highlighted_book_clear_aa():
    assert '".bt-seg-btn.is-on{background:var(--text-cyan);color:var(--text-on-accent)}"' in JS
    root = CSS[CSS.index(":root"):CSS.index(":root") + 20000]
    assert _contrast(_hex(root, "--text-cyan"), _hex(root, "--text-on-accent")) >= 4.5
    assert '".bt-table tr.bt-bestrow .bt-dim{color:var(--text-secondary)}"' in JS
    assert '".betting-app .egfx-chip-glyph{opacity:1}"' in JS


# ---------------------------------------------------------------------------
# QREP04 and the copy
# ---------------------------------------------------------------------------
def test_the_shell_reserves_the_late_painted_slots():
    shell = build_site.build_betting()
    i = shell.index("#betting-feedhealth:empty{min-height:37px}")
    assert i < shell.index('<div id="betting-feedhealth">')
    assert "#betting-section{min-height:70vh;display:flow-root}" in shell


def test_the_masthead_lede_says_it_once():
    shell = build_site.build_betting()
    sub = re.search(r'<span class="section-sub">(.*?)</span>', shell).group(1)
    words = len(re.sub(r"<[^>]+>", "", sub).split())
    assert words <= 20, words          # 30 before the pass
    assert "append-only" in sub


def test_the_futures_method_notes_are_collapsed_not_deleted():
    i = JS.index("function renderFutures")
    body = JS[i:i + 4000]
    j = body.index('<summary class="bt-details-sum">How this board works</summary>')
    for key in ("what_would_have_to_happen", "and_then_still_not_an_edge",
                "why_the_price_column_is_not_called_fair", "what_the_intervals_are",
                "win_total_basis"):
        assert body.index(key) > j, key


# ---------------------------------------------------------------------------
# Browser facts: keyboard tabs, focus tip, the links fetch, layout shift
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _payload_ok():
    try:
        d = json.loads((ROOT / "data" / "betting.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(d.get("team_bets"))


CLS_INIT = """window.__cls = 0; new PerformanceObserver(function (l) {
  l.getEntries().forEach(function (e) { if (!e.hadRecentInput) window.__cls += e.value; });
}).observe({type: 'layout-shift', buffered: true});"""


def test_browser_tabs_keys_tips_links_and_shift(server):
    pytest.importorskip("playwright.sync_api")
    if not _payload_ok():
        pytest.skip("no served betting payload in this checkout")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            c = b.new_context(viewport={"width": 1280, "height": 800})
            c.add_init_script(CLS_INIT)
            pg = c.new_page()
            got = []
            pg.on("requestfinished", lambda r: got.append(r.url))
            pg.goto(server + "betting/#section=futures", wait_until="networkidle", timeout=90_000)
            pg.wait_for_timeout(800)
            # QREP03: a clubs-only section never asks for the player map.
            assert not any("player_links.json" in u for u in got)
            # QREP04: measured 0.51 to 0.65 before the pass on a cold load.
            assert pg.evaluate("window.__cls") < 0.1
            # QREA19: arrows move between tabs and open them.
            pg.focus("#bt-tab-futures")
            pg.keyboard.press("ArrowRight")
            pg.wait_for_timeout(300)
            st = pg.evaluate("""() => [document.activeElement.id, location.hash,
              document.getElementById('betting-section').getAttribute('aria-labelledby'),
              document.querySelectorAll('[role=tab][tabindex="0"]').length]""")
            assert st == ["bt-tab-mybets", "#section=mybets", "bt-tab-mybets", 1], st
            pg.keyboard.press("Home")
            assert pg.evaluate("document.activeElement.id") == "bt-tab-potd"
            c.close()

            c = b.new_context(viewport={"width": 390, "height": 844})
            pg = c.new_page()
            pg.goto(server + "betting/#section=potd", wait_until="networkidle", timeout=90_000)
            pg.wait_for_timeout(600)
            tag = pg.query_selector(".bt-tipped")
            if tag is not None:
                tag.focus()
                info = pg.evaluate("""() => { const t = document.activeElement;
                  const d = document.getElementById(t.getAttribute('aria-describedby'));
                  return [t.classList.contains('bt-tipped'), d ? d.textContent : null,
                          t.getAttribute('data-tip'),
                          getComputedStyle(t, '::after').content.length > 2,
                          document.documentElement.scrollWidth <= document.documentElement.clientWidth]; }""")
                assert info[0] and info[1] == info[2] and info[3] and info[4], info
            c.close()
        finally:
            b.close()
