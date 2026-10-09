# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ boards fit the screen: the served page, measured in Chromium.

Owner ask 2026-09-11: "make it so that the chart fits on one screen without a
need for horizontal scrolling". Before the column views the reliever and hitter
boards ran 1,424 to 1,900px wide against a 1,352px container and scrolled
sideways at every desktop width. The views (Standard, Skill, Value, Leverage,
Batting, Runs, Discipline, Catching) carry 9 to 14 columns each; All carries
every column.

THE BUDGET RULE, asserted on the SERVED page and the served data:
  * the page itself never scrolls sideways, at any width, on any board;
  * every named view (every view but All), qualified filter on and off, fits
    its own table box at 768px and wider, and its phone subset fits at 390px,
    with ONE recorded exception: the Defense Catching view fits from 1024px
    and may scroll inside its own box below that (owner answer M26-4,
    2026-09-25: one full Catching view, 826px against the 720px box at 768);
  * All carries EVERY column, the Baseball Savant display columns included
    (owner answer M26-3, 2026-09-25), so it may scroll sideways inside its own
    box, never the page, with the name column frozen at the box's left edge.
    Measured 2026-10-01: relievers 1,431px and hitters 1,385px against a box
    that stops growing at 1,352px from a 1440 window up;
  * every eWAR column a board carries is visible on its Standard view, except
    on Defense at 640px and below, where the phone subset is the four fielding
    columns a reader opened that board for (spec 4.5, owner decision O4);
  * a fitted board has no scroll box, so after a long scroll its header sits at
    the top of the viewport (390 and 1440).
A future column that breaks the budget fails here rather than shipping a
sideways scroll. Views are read from the page's own Columns strip, so a view
added later is measured without editing this file. The sixth section (eWAR,
wave 5) is measured on both of its views as soon as its payload exists on the
machine, and skipped, never failed, before that.

Every request off loopback is aborted: logos and fonts never load, which the
layout does not depend on (the logo box is sized in CSS and hidden below 1024).
Playwright and chromium are OPTIONAL; the tests skip when they are missing, and
when the boards are not built on this machine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
BOARD_FILES = ["bullpen_leaderboards.json", "starter_leaderboards.json", "hitter_leaderboards.json",
               "leverage_leaderboards.json", "defense_leaderboards.json"]
# The sixth board's payload is written by war_board_export.py, which lands on a
# later commit than this file and refuses to write under its coverage floor.
# Deliberately NOT in BOARD_FILES: making the whole module skip until that
# exporter has run once would drop the five boards it already measures. The
# eWAR cases skip on their own instead (_open would time out on a section that
# renders the computing note and no table).
WAR_FILE = "war_leaderboards.json"
# The year-window artifacts (tools/mlbstats_window_lab.py, data/war_seasons.json
# from war_board_export). Like the eWAR payload they land on a different commit
# from this file, so the window cases skip on their own rather than failing a
# machine that has not built them.
WINDOW_FILES = ["mlbstats_windows.json", "war_seasons.json"]

# (label, section, hash, qualified-only checkbox id or None)
PAGES = [
    ("relievers", "bullpen", "section=bullpen", "mlbstats-qual"),
    ("starters", "starters", "section=starters", "mlbstats-starter-qual"),
    ("hitters", "hitters", "section=hitters", "mlbstats-hitter-qual"),
    ("defense", "defense", "section=defense", "mlbstats-defense-qual"),
    ("leverage batters", "leverage", "section=leverage", "mlbstats-leverage-qual"),
    ("leverage starters", "leverage", "section=leverage&lview=starters", "mlbstats-leverage-qual"),
    ("team bullpens", "bullpen", "section=bullpen&view=teams", None),
    ("team rotations", "starters", "section=starters&sview=teams", None),
    ("team lineups", "hitters", "section=hitters&hview=teams", None),
    ("team defense", "defense", "section=defense&dview=teams", None),
    ("relievers 2025", "bullpen", "section=bullpen&rseason=2025", None),
    ("starters 2025", "starters", "section=starters&sseason=2025", None),
    ("hitters 2025", "hitters", "section=hitters&hseason=2025", None),
    ("defense 2025", "defense", "section=defense&dseason=2025", None),
    # Wave 5, the eWAR section. Both named views, and the qualified gate on the
    # players view: the one board whose columns are new to this overhaul is the
    # one that most needs the budget rule asserted on it.
    ("ewar players", "war", "section=war", "mlbstats-war-qual"),
    ("team ewar", "war", "section=war&wview=teams", None),
    # A WINDOW is a board state with its own column array (an index column
    # carries its span in the label, a count column is summed, several columns
    # are gone), so the budget rule is measured on one per section rather than
    # inferred from the season boards above.
    ("overall 2023-2025", "war", "section=war&wyears=2023-2025", "mlbstats-war-qual"),
    ("overall 2011-2026", "war", "section=war&wyears=2011-2026", None),
    ("hitters last 3", "hitters", "section=hitters&hyears=2024-2026", None),
    ("starters last 5", "starters", "section=starters&syears=2022-2026", None),
    ("bullpen last 3", "bullpen", "section=bullpen&ryears=2024-2026", None),
    ("defense last 3", "defense", "section=defense&dyears=2024-2026", None),
    ("leverage last 3", "leverage", "section=leverage&lyears=2024-2026", None),
    # The League tab (final-pass plan Part 8 P8.2, LT-08) is built dark behind
    # league_averages.MLBSTATS_LEAGUE_TEAMS_LIVE: these states are measured once
    # the served shell carries the tab and the season panels are on disk, and
    # skipped, never failed, before that. Rows are statistics, so there is one
    # view; the filtered state carries the "vs all" column, the widest it gets.
    ("league averages", "league", "section=league", None),
    ("league filtered", "league", "section=league&gpos=C,SS&ghand=L&gqual=floor", None),
    ("league pitchers", "league", "section=league&gside=pit&grole=SP,RP", None),
    ("league teams", "league", "section=league&gside=team", None),
]
# The five sections that carry a methodology fold and a Team note, which is what
# the vertical-budget case below measures. Overall carries neither (spec 4.7
# gives it a one-line explainer), and a window carries the window NOTE instead of
# the fold, so the window states are measured by their own budget case below
# rather than left out. Named rather than sliced: PAGES grew a window state per
# section and a slice would have silently measured two of those instead.
FOLD_PAGES = [p for p in PAGES if p[1] != "war" and "years=" not in p[2]][:5]
WINDOW_PAGES = [p for p in PAGES if "years=" in p[2]]
SIZES = [(390, 844), (768, 1024), (1024, 768), (1280, 800), (1440, 900)]
# Named views that may scroll inside their own box below a width, and the width
# they must fit from. The Catching view is the one (owner answer M26-4).
VIEW_FITS_FROM = {"def:catching": 1024}
# The widths the owner's answers name for the All and Catching cases.
ANSWER_WIDTHS = [(390, 844), (1024, 768), (1280, 800), (1440, 900)]
# The one Standard view that drops its eWAR column below 641px: Defense keeps
# Pos, DEM+, Fld and Inn there instead (spec 4.5). The same exception, from the
# other side, is PHONE["def"] in test_mlbstats_views.py, whose
# test_the_defense_phone_exception_is_the_only_one pins that it stays the only
# one; every other board carries eWAR at every width.
PHONE_EWAR_EXEMPT = {"defense"}
PHONE_MAX = 640

_MEASURE = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const sc = root && root.querySelector('.mlbstats-scroll:has(> table.mlbstats-table)');
  if (!sc) return null;
  const t = sc.querySelector('table');
  const shown = (th) => th && getComputedStyle(th).display !== 'none';
  const war = ['war', 'team_war'].map(k => t.querySelector('thead th[data-col="' + k + '"]'))
                                 .filter(Boolean);
  return {
    all: t.classList.contains('mlbstats-cv-all'),
    page_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    sc_sw: sc.scrollWidth, sc_cw: sc.clientWidth, table_w: t.offsetWidth,
    fit: sc.classList.contains('is-fit'),
    war_hidden: war.filter(th => !shown(th)).map(th => th.getAttribute('data-col')),
    n_visible: Array.from(t.querySelectorAll('thead th')).filter(shown).length,
  };
}
"""
_VIEWS = r"""(sec) => Array.from(document.querySelectorAll('#mlbstats-section-' + sec + ' [data-colview]'))
                          .map(b => b.getAttribute('data-colview'))"""
_STICKY = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const sc = root.querySelector('.mlbstats-scroll:has(> table.mlbstats-table)');
  const th = sc.querySelector('thead th');
  const top = sc.getBoundingClientRect().top + window.scrollY;
  window.scrollTo(0, top + 1500);
  return {fit: sc.classList.contains('is-fit'), th_top: th.getBoundingClientRect().top,
          scrolled: window.scrollY};
}
"""


def _boards_built() -> bool:
    return all((ROOT / "data" / f).exists() for f in BOARD_FILES)


def _league_built() -> bool:
    """The served shell carries the League tab and its panels are on disk."""
    shell = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    return ('data-mlbsection="league"' in shell
            and any((ROOT / "data").glob("mlb_league_panel_*.json")))


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    if not _boards_built():
        pytest.skip("the /mlbstats/ boards are not built on this machine")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 - no chromium on this machine
            pytest.skip("chromium unavailable: %s" % e)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def test_the_served_shell_carries_the_mlbx_scope():
    """The fit rules only reach the page through the .mlbx root class, which
    build_site writes into mlbstats/index.html. A stale shell (site.css edited,
    build_site not rerun) serves an unfitted page."""
    shell = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    assert 'class="fa-app mlbstats-app mlbx"' in shell, (
        "mlbstats/index.html predates the .mlbx scope: rerun build_site.py")


def _context(browser, w, h):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
    ctx.add_init_script("try { localStorage.clear(); } catch (e) {}")
    return ctx


def _open(page, server, sec, hash_):
    page.goto("about:blank")
    page.goto(server + "mlbstats/#" + hash_, wait_until="load", timeout=60_000)
    page.wait_for_selector("#mlbstats-section-%s .mlbstats-table" % sec, timeout=30_000)
    # A board can render before every artifact it reads has landed: the Overall
    # board paints off war_leaderboards.json while war_seasons.json is still in
    # flight, and that file adds two columns when it arrives. Measure the settled
    # page, not the first paint.
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:       # noqa: BLE001 - a busy page is still measurable
        pass
    page.wait_for_timeout(200)


def _check(m, w, where, problems, view=None):
    if m is None:
        problems.append("%s: no board table rendered" % where)
        return
    if m["page_overflow"] > 0:
        problems.append("%s: the PAGE scrolls sideways by %dpx" % (where, m["page_overflow"]))
    fits = m["sc_sw"] <= m["sc_cw"] and m["table_w"] <= m["sc_cw"]
    # All may scroll inside its own box at any width; a named view must fit
    # unless it is narrower than the width its recorded exception names (the
    # phone subset at 640px and below still has to fit).
    from_w = VIEW_FITS_FROM.get(view)
    must_fit = (not m["all"]) and not (from_w and PHONE_MAX < w < from_w)
    if must_fit and not fits:
        problems.append("%s: table %dpx does not fit its %dpx box" % (where, m["table_w"], m["sc_cw"]))
    if fits and not m["fit"]:
        problems.append("%s: fits but markFit did not mark it" % where)


@pytest.mark.parametrize("size", SIZES, ids=["%dx%d" % s for s in SIZES])
def test_every_board_and_view_fits_and_the_page_never_scrolls_sideways(browser, server, size):
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems, measured = [], 0
    try:
        for label, sec, hash_, qual in PAGES:
            if sec == "war" and not (ROOT / "data" / WAR_FILE).exists():
                continue
            if sec == "league":
                if not _league_built():
                    continue
                _open(page, server, sec, hash_)
                _check(page.evaluate(_MEASURE, sec), w, "%dpx %s" % (w, label), problems)
                measured += 1
                continue
            if "years=" in hash_ and not all((ROOT / "data" / f).exists() for f in WINDOW_FILES):
                continue
            if "season=" in hash_ and not (ROOT / "data" / (
                    {"bullpen": "bullpen", "starters": "starter", "hitters": "hitter",
                     "defense": "defense"}[sec] + "_history.json")).exists():
                continue
            _open(page, server, sec, hash_)
            views = page.evaluate(_VIEWS, sec) or [None]
            for v in views:
                if v:
                    page.evaluate("(v) => document.querySelector('[data-colview=\"' + v + '\"]').click()", v)
                where = "%dpx %s %s" % (w, label, v.split(":")[1] if v else "(one view)")
                m = page.evaluate(_MEASURE, sec)
                _check(m, w, where, problems, v)
                measured += 1
                exempt = (w <= PHONE_MAX and sec in PHONE_EWAR_EXEMPT)
                if m and (v is None or v.endswith(":standard")) and m["war_hidden"] and not exempt:
                    problems.append("%s: eWAR column hidden on the Standard view: %s" % (where, m["war_hidden"]))
                if qual and m and not m["all"]:
                    page.evaluate("(id) => document.getElementById(id).click()", qual)
                    _check(page.evaluate(_MEASURE, sec), w, where + " qualified off", problems, v)
                    page.evaluate("(id) => document.getElementById(id).click()", qual)
                    measured += 1
    finally:
        ctx.close()
    assert measured >= 30, measured
    assert not problems, "\n".join(problems)


_ALL_FRAME = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const sc = root.querySelector('.mlbstats-scroll:has(> table.mlbstats-table)');
  const t = sc.querySelector('table');
  const shown = (el) => getComputedStyle(el).display !== 'none';
  const heads = Array.from(t.querySelectorAll('thead th'));
  sc.scrollLeft = sc.scrollWidth;
  const name = t.querySelector('tbody td');
  const out = {
    all: t.classList.contains('mlbstats-cv-all'),
    n_heads: heads.length, n_visible: heads.filter(shown).length,
    n_off: t.querySelectorAll('.mlbstats-cv-off').length,
    doc_sw: document.documentElement.scrollWidth, inner: window.innerWidth,
    sc_sw: sc.scrollWidth, sc_cw: sc.clientWidth, scrolled: sc.scrollLeft,
    name_left: name ? Math.round(name.getBoundingClientRect().left - sc.getBoundingClientRect().left) : null,
  };
  sc.scrollLeft = 0;
  return out;
}
"""


@pytest.mark.parametrize("size", ANSWER_WIDTHS, ids=["%dx%d" % s for s in ANSWER_WIDTHS])
def test_the_all_view_carries_every_column_and_scrolls_only_inside_its_frame(browser, server, size):
    """Owner answer M26-3: All keeps every column, the Baseball Savant display
    columns included, and where that is wider than the box the TABLE scrolls,
    inside its own frame, with the name frozen at its left edge; the page never
    does. document.documentElement.scrollWidth equals the viewport at 390,
    1024, 1280 and 1440."""
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems = []
    try:
        for label, sec, hash_, _qual in FOLD_PAGES[:4]:
            _open(page, server, sec, hash_)
            alls = [v for v in page.evaluate(_VIEWS, sec) if v.endswith(":all")]
            assert alls, label
            page.evaluate("(v) => document.querySelector('[data-colview=\"' + v + '\"]').click()", alls[0])
            page.wait_for_timeout(100)
            m = page.evaluate(_ALL_FRAME, sec)
            where = "%dpx %s all" % (w, label)
            if not m["all"]:
                problems.append("%s: the All pill did not open All" % where)
            if m["n_off"] or m["n_visible"] != m["n_heads"]:
                problems.append("%s: All shows %d of %d columns" % (where, m["n_visible"], m["n_heads"]))
            if m["doc_sw"] != m["inner"]:
                problems.append("%s: the page is %dpx wide in a %dpx viewport" % (where, m["doc_sw"], m["inner"]))
            if m["sc_sw"] > m["sc_cw"]:
                if m["scrolled"] <= 0:
                    problems.append("%s: the table overflows its frame and the frame does not scroll" % where)
                if m["name_left"] is None or abs(m["name_left"]) > 1:
                    problems.append("%s: scrolled to the end, the name sits %rpx from the frame's edge"
                                    % (where, m["name_left"]))
    finally:
        ctx.close()
    assert not problems, "\n".join(problems)


_ACTIVE_VIEW = r"""(sec) => {
  const b = document.querySelector('#mlbstats-section-' + sec + ' [data-colview][aria-pressed="true"]');
  return {view: b ? b.getAttribute('data-colview') : null, hash: location.hash,
          doc_sw: document.documentElement.scrollWidth, inner: window.innerWidth,
          pills: Array.from(document.querySelectorAll('#mlbstats-section-' + sec + ' [data-colview]'))
                      .map(x => x.getAttribute('data-colview'))};
}"""


@pytest.mark.parametrize("size", ANSWER_WIDTHS, ids=["%dx%d" % s for s in ANSWER_WIDTHS])
def test_the_catching_view_and_its_retired_links_resolve(browser, server, size):
    """Owner answer M26-4: Blocking and Throwing are one Catching view. A link
    or a stored pick naming either retired id opens Catching and rewrites the
    hash to it; the page never scrolls sideways, and from 1024 the view fits."""
    w, h = size
    problems = []
    for how, old in (("link", "blocking"), ("link", "throwing"), ("stored", "blocking"),
                     ("stored", "throwing"), ("link", "catching")):
        ctx = _context(browser, w, h)
        if how == "stored":
            ctx.add_init_script("try { localStorage.setItem('mlbstats.cols.def', '%s'); } catch (e) {}" % old)
        page = ctx.new_page()
        try:
            _open(page, server, "defense", "section=defense" + ("&dcols=" + old if how == "link" else ""))
            r = page.evaluate(_ACTIVE_VIEW, "defense")
            m = page.evaluate(_MEASURE, "defense")
            where = "%dpx %s %s" % (w, how, old)
            if r["view"] != "def:catching":
                problems.append("%s: opened %r, not def:catching" % (where, r["view"]))
            if "dcols=catching" not in r["hash"]:
                problems.append("%s: the hash reads %r" % (where, r["hash"]))
            if any(p in r["pills"] for p in ("def:blocking", "def:throwing")):
                problems.append("%s: a retired pill is still on the strip: %r" % (where, r["pills"]))
            if r["doc_sw"] != r["inner"]:
                problems.append("%s: the page is %dpx wide in a %dpx viewport" % (where, r["doc_sw"], r["inner"]))
            _check(m, w, where, problems, "def:catching")
        finally:
            ctx.close()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("size", [(390, 844), (1440, 900)], ids=["390x844", "1440x900"])
def test_a_fitted_board_keeps_its_header_at_the_top_after_a_long_scroll(browser, server, size):
    ctx = _context(browser, *size)
    page = ctx.new_page()
    pages = [("bullpen", "section=bullpen"), ("hitters", "section=hitters"),
             # A window is the widest state the Overall board has (Yrs and Clubs
             # join it), so the sticky header is measured there too.
             ("war", "section=war&wyears=2023-2025")]
    try:
        for sec, hash_ in pages:
            if sec == "war" and not all((ROOT / "data" / f).exists()
                                        for f in [WAR_FILE] + WINDOW_FILES):
                continue
            _open(page, server, sec, hash_)
            r = page.evaluate(_STICKY, sec)
            assert r["fit"], (size, sec, "the Standard board should fit and lose its scroll box")
            assert r["scrolled"] > 0, (size, sec)
            assert abs(r["th_top"]) <= 1, (size, sec, r)
    finally:
        ctx.close()


# ---------------------------------------------------------------- wave 2: the vertical budget
# O2 / O3 (2026-09-11), measured on the served page: the methodology fold is
# closed, the Team note is one line, the Download CSV control rides the tab
# row at 641px and up (its own row on a phone), and at 640px and below the
# filter bar is a search box and a Filters button until the drawer opens.
# Measured when this landed, the WORST of the five sections at each size
# (Relievers, the board with the longest freshness line and the chip row):
# 8 rows on the first screen at 1440x900 (table top y 589, against 770 and 3
# rows before), 10 at 768x1024 (y 592), 3 at 390x844 (y 670, against 794 and
# 0 before). The floors are the measurement minus two rows: a longer freshness
# line or a taller banner never flakes the pin, while giving back half the
# budget fails it.
FIRST_SCREEN_ROWS = {(1440, 900): 6, (768, 1024): 8, (390, 844): 1}
# The vertical-budget test below reads this for PAGES[:5] only: the eWAR
# section carries the CSV control and the drawer but no methodology fold (spec
# 4.7 gives it a one-line explainer instead), so it is measured by the fit and
# shell tests rather than by the fold/note budget.
CSV_NAMES = {"bullpen": "mlb-leaderboards", "starters": "mlb-starters", "hitters": "mlb-hitters",
             "leverage": "mlb-leverage", "defense": "mlb-defense", "war": "mlb-ewar"}

_VERTICAL = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const shown = (el) => !!el && getComputedStyle(el).display !== 'none';
  const box = (el) => { const b = el.getBoundingClientRect();
                        return {top: b.top + scrollY, bottom: b.bottom + scrollY, left: b.left, right: b.right, h: b.height}; };
  const host = root.querySelector('[data-csv-export]');
  const bar = host && host.querySelector(':scope > .eph-csv-bar');
  const fold = root.querySelector('.mlbstats-fold');
  const note = root.querySelector('details.mlbstats-teambasis')
            || document.querySelector('#mlbstats-banner details.mlbstats-teambasis');
  const filt = root.querySelector('.mlbx-filters');
  const btn = filt && filt.querySelector(':scope > .mlbx-filtbtn');
  const roles = root.querySelector('.mlbx-filters + .mlbstats-roles');
  const t = root.querySelector('.mlbstats-scroll:has(> table.mlbstats-table) > table');
  const top = t.getBoundingClientRect().top + scrollY;
  const thH = t.querySelector('thead').getBoundingClientRect().height;
  const tr = t.querySelector('tbody tr');
  const rowH = tr ? tr.getBoundingClientRect().height : 0;
  return {
    csv_name: host && host.getAttribute('data-csv-export'),
    csv: bar ? box(bar) : null,
    csv_next: bar && bar.nextElementSibling ? box(bar.nextElementSibling) : null,
    host_right: host ? box(host).right : null,
    fold: !!fold, fold_collapsed: !!fold && fold.classList.contains('is-collapsed'),
    fold_body_shown: shown(fold && fold.querySelector('.mlbstats-collapse-body')),
    note: !!note, note_open: note ? note.open : null,
    note_summary_h: note ? box(note.querySelector('summary')).h : null,
    filt: !!filt, filt_btn_shown: shown(btn), filt_h: filt ? box(filt).h : null,
    filt_open: !!filt && filt.classList.contains('is-open'),
    filt_hidden: filt ? Array.from(filt.children).filter(c => !shown(c)).map(c => c.className || c.tagName) : null,
    filt_children: filt ? filt.children.length : null,
    roles: !!roles, roles_shown: shown(roles),
    table_top: top,
    rows_first_screen: Math.max(0, Math.floor((innerHeight - top - thH) / (rowH || 1))),
    page_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}
"""
_TAP_FILTERS = "(sec) => document.querySelector('#mlbstats-section-' + sec + ' .mlbx-filtbtn').click()"

# The window note, and the one control that must NOT be inside it.
_WINNOTE = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const note = root.querySelector('details.mlbstats-winnote');
  const est = root.querySelector('.mlbx-est');
  const idx = [...root.querySelectorAll('tbody .mlbstats-winidx')];
  return {
    note: !!note, open: note ? note.open : null,
    h: note ? note.getBoundingClientRect().height : null,
    est: !!est, est_h: est ? est.getBoundingClientRect().height : 0,
    ruler: [...root.querySelectorAll('tbody [class*="vt-"]')].length,
    idx: idx.length,
    idx_classes: [...new Set(idx.map(s => s.className))],
  };
}
"""
# Measured on the served artifacts when the window boards landed (2026-09-17),
# the WORST window state at each size: 3 rows on the first screen at 390x844
# (Overall 2024-2026 and Bullpen Last 3, table top y 631), 7 at 768x1024
# (Overall, y 568) and 9 at 1440x900 (Defense Last 3, y 554). The floors are the
# measurement minus two, the same rule the season floors above are set by.
# Before the note was closed by default the same boards measured ZERO rows at
# 390 (table top y 781 to 802 on an 844px screen).
WINDOW_FIRST_SCREEN_ROWS = {(1440, 900): 7, (768, 1024): 5, (390, 844): 1}


@pytest.mark.parametrize("size", [(390, 844), (768, 1024), (1440, 900)], ids=["390x844", "768x1024", "1440x900"])
def test_the_vertical_budget_on_a_window(browser, server, size):
    """A window is a board state of its own: its note replaces the methodology
    fold, its CSV file is named for the span, and its + index cells carry no
    value ruler. The budget rule is measured HERE rather than assumed from the
    season boards, because the note is the tallest thing this page paints and an
    always-open one put every window board's first row below the fold."""
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems = []
    try:
        for label, sec, hash_, _qual in WINDOW_PAGES:
            if not all((ROOT / "data" / f).exists() for f in WINDOW_FILES + [WAR_FILE]):
                continue
            _open(page, server, sec, hash_)
            m = page.evaluate(_VERTICAL, sec)
            n = page.evaluate(_WINNOTE, sec)
            where = "%dpx %s" % (w, label)
            if m["page_overflow"] > 0:
                problems.append("%s: the page scrolls sideways by %dpx" % (where, m["page_overflow"]))
            # The CSV file carries the span: the headers already do, and a file
            # named for one season is the one string the reader keeps.
            span = hash_.split("years=")[1].split("&")[0]
            want = CSV_NAMES[sec] + "-" + span
            if m["csv_name"] != want:
                problems.append("%s: the CSV name is %r, not %r" % (where, m["csv_name"], want))
            if not n["note"]:
                problems.append("%s: no window note" % where)
            elif n["open"]:
                problems.append("%s: the window note is open (the season fold is closed)" % where)
            elif n["h"] and n["h"] > 60:
                problems.append("%s: the closed note is %dpx, not a line or two" % (where, n["h"]))
            # Established-only changes which rows show, so it cannot be inside a
            # closed note.
            if n["est"] and not n["est_h"]:
                problems.append("%s: the Established-only control is not visible" % where)
            if n["idx"] and n["ruler"]:
                problems.append("%s: a value ruler reached a window board" % where)
            if n["idx"] and n["idx_classes"] != ["mlbstats-winidx"]:
                problems.append("%s: a window index cell carries %r" % (where, n["idx_classes"]))
            floor = WINDOW_FIRST_SCREEN_ROWS.get(size)
            if floor and m["rows_first_screen"] < floor:
                problems.append("%s: %d rows on the first screen (table top y %d), floor %d"
                                % (where, m["rows_first_screen"], m["table_top"], floor))
    finally:
        ctx.close()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("size", [(390, 844), (768, 1024), (1440, 900)], ids=["390x844", "768x1024", "1440x900"])
def test_the_vertical_budget_on_every_section(browser, server, size):
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems = []
    try:
        for label, sec, hash_, _qual in FOLD_PAGES:
            _open(page, server, sec, hash_)
            page.wait_for_selector("#mlbstats-section-%s .eph-csv-bar" % sec, timeout=10_000)
            m = page.evaluate(_VERTICAL, sec)
            where = "%dpx %s" % (w, label)
            if m["page_overflow"] > 0:
                problems.append("%s: the page scrolls sideways by %dpx" % (where, m["page_overflow"]))
            # The CSV control: on every section, with its own filename stem.
            if m["csv_name"] != CSV_NAMES[sec] or not m["csv"]:
                problems.append("%s: no Download CSV control (%r)" % (where, m["csv_name"]))
            elif m["csv_next"]:
                c, n = m["csv"], m["csv_next"]
                if w > 640 and not (c["top"] < n["bottom"] and n["top"] < c["bottom"]):
                    problems.append("%s: the CSV bar takes its own row (bar %s, next %s)" % (where, c, n))
                if w > 640 and c["right"] > m["host_right"] + 1:
                    problems.append("%s: the CSV bar overflows its section" % where)
                if w <= 640 and n["top"] < c["bottom"] - 1:
                    problems.append("%s: the CSV bar should keep its own row on a phone" % where)
            # The fold and the Team note: closed, one line.
            if not (m["fold"] and m["fold_collapsed"]) or m["fold_body_shown"]:
                problems.append("%s: the methodology fold is open (O2 closes it)" % where)
            if not m["note"]:
                problems.append("%s: no Team note details" % where)
            elif m["note_open"] or not m["note_summary_h"] or m["note_summary_h"] > 30:
                problems.append("%s: the Team note is not one closed line (%r)" % (where, m))
            # The phone drawer.
            if not m["filt"]:
                problems.append("%s: no .mlbx-filters bar" % where)
            elif w > 640:
                if m["filt_btn_shown"] or m["filt_hidden"] != ["chip mlbx-filtbtn"]:
                    problems.append("%s: on a desktop only the Filters button hides: %r" % (where, m["filt_hidden"]))
            else:
                if not m["filt_btn_shown"] or m["filt_open"] or m["filt_h"] > 44:
                    problems.append("%s: the drawer is not closed to one row (%r)" % (where, m["filt_h"]))
                if len(m["filt_hidden"]) != m["filt_children"] - 2:
                    problems.append("%s: closed, only the search box and the button show: hidden %r of %d"
                                    % (where, m["filt_hidden"], m["filt_children"]))
                if m["roles"] and m["roles_shown"]:
                    problems.append("%s: the chip row shows while the drawer is closed" % where)
                page.evaluate(_TAP_FILTERS, sec)
                page.wait_for_timeout(100)
                o = page.evaluate(_VERTICAL, sec)
                if not o["filt_open"] or o["filt_hidden"] or (o["roles"] and not o["roles_shown"]):
                    problems.append("%s: the drawer did not open every control: %r" % (where, o["filt_hidden"]))
                if o["table_top"] <= m["table_top"] or o["page_overflow"] > 0:
                    problems.append("%s: an open drawer should push the board down and never sideways" % where)
                page.evaluate(_TAP_FILTERS, sec)
                page.wait_for_timeout(100)
                if page.evaluate(_VERTICAL, sec)["filt_open"]:
                    problems.append("%s: the drawer did not close again" % where)
            floor = FIRST_SCREEN_ROWS.get(size)
            if floor and m["rows_first_screen"] < floor:
                problems.append("%s: %d rows on the first screen (table top y %d), floor %d"
                                % (where, m["rows_first_screen"], m["table_top"], floor))
    finally:
        ctx.close()
    assert not problems, "\n".join(problems)


def test_the_drawer_state_survives_a_section_switch(browser, server):
    """One flag, one delegated listener: a drawer opened on Relievers is open
    on Hitters after the section switch and after the board re-renders."""
    ctx = _context(browser, 390, 844)
    page = ctx.new_page()
    try:
        _open(page, server, "bullpen", "section=bullpen")
        page.evaluate(_TAP_FILTERS, "bullpen")
        page.wait_for_timeout(100)
        assert page.evaluate(_VERTICAL, "bullpen")["filt_open"]
        page.evaluate("() => document.querySelector('.mlbstats-sectionbtn[data-mlbsection=\"hitters\"]').click()")
        page.wait_for_selector("#mlbstats-section-hitters .mlbstats-table", timeout=30_000)
        page.wait_for_timeout(200)
        m = page.evaluate(_VERTICAL, "hitters")
        assert m["filt_open"] and m["filt_btn_shown"] and not m["filt_hidden"], m
        page.evaluate("() => document.querySelector('#mlbstats-section-hitters [data-colview=\"hit:value\"]').click()")
        page.wait_for_timeout(200)
        m = page.evaluate(_VERTICAL, "hitters")
        assert m["filt_open"] and not m["filt_hidden"], m
    finally:
        ctx.close()


_AFTER_RERENDER = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const host = root.querySelector('[data-csv-export]');
  const note = root.querySelector('details.mlbstats-teambasis')
            || document.querySelector('#mlbstats-banner details.mlbstats-teambasis');
  return {csv: !!host.querySelector(':scope > .eph-csv-bar'),
          rows: root.querySelectorAll('tbody tr').length,
          note_open: note ? note.open : null};
}
"""


_OPEN_NOTE = r"""
(sec) => {
  const note = document.querySelector('#mlbstats-section-' + sec + ' details.mlbstats-teambasis')
            || document.querySelector('#mlbstats-banner details.mlbstats-teambasis');
  note.querySelector('summary').click();
}
"""


def test_the_csv_control_and_an_opened_note_survive_a_rerender(browser, server):
    """A board render replaces its root's innerHTML, which deletes BOTH the
    Download CSV bar (the root's first child) and the open state of a native
    <details>. Measured before this: the control was gone for 0.5 to 1.5s
    after every sort, filter and view click, because only a 250ms-debounced
    observer put it back, and on a phone the board jumped with it."""
    ctx = _context(browser, 1440, 900)
    page = ctx.new_page()
    try:
        for label, sec, hash_, _qual in FOLD_PAGES:
            _open(page, server, sec, hash_)
            page.wait_for_selector("#mlbstats-section-%s .eph-csv-bar" % sec, timeout=10_000)
            page.evaluate(_OPEN_NOTE, sec)
            assert page.evaluate(_AFTER_RERENDER, sec)["note_open"], (label, "the note did not open")
            # The re-render a reader triggers most: a keystroke in the search box.
            page.fill("#mlbstats-section-%s .mlbstats-search" % sec, "a")
            after = page.evaluate(_AFTER_RERENDER, sec)      # no wait: the same tick
            assert after["csv"], (label, "the Download CSV control blinked out of the re-render")
            assert after["note_open"], (label, "the opened Team note snapped shut")
    finally:
        ctx.close()


def test_the_filters_count_names_the_qualified_gate_a_closed_drawer_hides(browser, server):
    """A phone reader who unchecks "qualified only" and closes the drawer
    would read a bare "Filters" over a board that is no longer the qualified
    pool. The count is what stops that, so the gate is in it."""
    ctx = _context(browser, 390, 844)
    page = ctx.new_page()
    try:
        _open(page, server, "bullpen", "section=bullpen")
        btn = "#mlbstats-section-bullpen .mlbx-filtbtn"
        assert page.inner_text(btn).strip() == "Filters"
        rows = "() => document.querySelectorAll('#mlbstats-section-bullpen tbody tr').length"
        qualified = page.evaluate(rows)
        page.click(btn)
        page.click("#mlbstats-qual")
        page.wait_for_timeout(200)
        assert page.evaluate(rows) > qualified, "unchecking the gate did not widen the board"
        page.click(btn)
        page.wait_for_timeout(100)
        assert page.inner_text(btn).split() == ["Filters", "1"], page.inner_text(btn)
    finally:
        ctx.close()


def test_the_served_shell_opts_every_section_into_csv_with_short_nav_labels():
    """The served shell, not the builder: mlbstats/index.html is a tracked
    build output and a stale one serves the old labels and a CSV control on
    the Bullpen section only."""
    shell = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    for sec, name in CSV_NAMES.items():
        rid = "app" if sec == "bullpen" else sec
        assert ('<div id="mlbstats-%s-root" data-csv-export="%s">' % (rid, name)) in shell, (sec, "rerun build_site.py")
    labels = dict(re.findall(r'data-mlbsection="([a-z]+)"[^>]*>([^<]+)</button>', shell))
    for sec, label in {"bullpen": "Bullpen", "starters": "Starters", "hitters": "Hitters",
                       "leverage": "Leverage", "defense": "Defense", "war": "Overall"}.items():
        assert labels.get(sec) == label, (sec, labels, "rerun build_site.py")
    # Owner decision 2026-09-17: Overall is first and is the landing section, in
    # the SERVED shell as well as the builder. A shell that still marks Bullpen
    # active paints the wrong tab over the board the script opens.
    # The League tab joins after Leverage only in a live build (and Teams,
    # task Q8_13b, before it); a dark shell is the six sections exactly.
    assert list(labels)[:6] == ["war", "hitters", "starters", "bullpen", "defense", "leverage"], list(labels)
    assert list(labels)[6:] in ([], ["league"], ["teams", "league"]), list(labels)
    assert 'class="mlbstats-sectionbtn active" data-mlbsection="war"' in shell, "rerun build_site.py"
    assert '<div id="mlbstats-section-war" class="mlbstats-section" role="tabpanel" aria-label="Overall">' \
        in shell, "rerun build_site.py"


# ---------------------------------------------------------------- the Pitches views (Q8_04)
# The pitch-rate columns ship dark (pitch_rates.SERVE_PITCH_RATES off), so the
# served boards carry no key and the Columns strip offers no Pitches view: the
# measurement above cannot reach it. This case serves the same page with the
# three boards stamped the way the exporters stamp them with the flag on
# (pitch_rates_boards over the cached season context, no request), and holds the
# Pitches views to the budget rule: each fits its box from 768px, its phone
# subset fits at 390, the team tables with their club units fit, and the page
# never scrolls sideways. Skipped, never failed, on a machine without the
# pitch-rate cache.
_PITCH_PAGES = [
    ("relievers pitches", "bullpen", "section=bullpen&rcols=pitches", "mlbstats-qual", "rel:pitches"),
    ("starters pitches", "starters", "section=starters&scols=pitches", "mlbstats-starter-qual", "sp:pitches"),
    ("hitters pitches", "hitters", "section=hitters&hcols=pitches", "mlbstats-hitter-qual", "hit:pitches"),
    ("team bullpens", "bullpen", "section=bullpen&view=teams", None, None),
    ("team rotations", "starters", "section=starters&sview=teams", None, None),
    ("team lineups", "hitters", "section=hitters&hview=teams", None, None),
]


def _stamped_boards():
    """{file name: payload bytes} for the three live boards with the flag-on
    keys, built from the served payloads; None when the cache cannot serve."""
    import json
    import pitch_rates_boards as prb
    try:
        docs = {f: json.loads((ROOT / "data" / f).read_text(encoding="utf-8")) for f in BOARD_FILES[:3]}
        ctx = prb.season_context(int(docs["starter_leaderboards.json"]["season"]), fetch=False)
    except Exception:       # noqa: BLE001 - no cache on this machine
        return None
    if ctx["league"].get("pitching_status") != "usable" or ctx["league"].get("tracking") != "usable":
        return None
    sp, rp, hit = (docs["starter_leaderboards.json"], docs["bullpen_leaderboards.json"],
                   docs["hitter_leaderboards.json"])
    prb.stamp_pitcher_rows(sp["starters"], ctx, "sp")
    prb.stamp_pitcher_teams(sp["teams"], sp["starters"], ctx, "sp")
    prb.stamp_pitcher_rows(rp["relievers"], ctx, "rp")
    prb.stamp_pitcher_teams(rp["teams"], rp["relievers"], ctx, "rp")
    np_by_id, pos_by_id = {}, {}
    for mid, line in ctx["lines"].items():
        h = line.get("hit") or {}
        np_by_id[int(mid)] = h.get("np")
        pos_by_id[int(mid)] = h.get("pos")
    prb.stamp_hitter_rows(hit["hitters"], np_by_id, ctx)
    prb.stamp_hitter_teams(hit["teams"], hit["hitters"], np_by_id, pos_by_id, ctx)
    if not any(r.get("p_ip") is not None for r in sp["starters"]):
        return None
    return {f: json.dumps(d).encode("utf-8") for f, d in docs.items()}


@pytest.fixture(scope="module")
def stamped_boards():
    out = _stamped_boards()
    if out is None:
        pytest.skip("the pitch-rate cache is not on this machine")
    return out


@pytest.mark.parametrize("size", SIZES, ids=["%dx%d" % s for s in SIZES])
def test_the_pitches_views_fit_from_768_and_their_phone_subsets_at_390(browser, server, stamped_boards, size):
    w, h = size
    ctx = _context(browser, w, h)
    def serve(body):
        return lambda route: route.fulfill(status=200, body=body, content_type="application/json")
    for name, body in stamped_boards.items():
        ctx.route(re.compile(r"^http://127\.0\.0\.1:\d+/data/%s(\?.*)?$" % re.escape(name)), serve(body))
    page = ctx.new_page()
    problems, measured = [], 0
    try:
        for label, sec, hash_, qual, view in _PITCH_PAGES:
            _open(page, server, sec, hash_)
            if view:
                pressed = page.evaluate(_ACTIVE_VIEW, sec)["view"]
                if pressed != view:
                    problems.append("%dpx %s: opened %r" % (w, label, pressed))
                    continue
            where = "%dpx %s" % (w, label)
            m = page.evaluate(_MEASURE, sec)
            _check(m, w, where, problems, view)
            measured += 1
            if qual and m:
                page.evaluate("(id) => document.getElementById(id).click()", qual)
                _check(page.evaluate(_MEASURE, sec), w, where + " qualified off", problems, view)
                page.evaluate("(id) => document.getElementById(id).click()", qual)
                measured += 1
    finally:
        ctx.close()
    assert measured == 9, measured
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- the League charts
# The over-time line, its small multiples and the players scatter are drawn at
# the cell's real width (lane design 1.7 item 2): every label prints at 8px or
# taller, at every width, and no chart pushes the page sideways. Skipped, never
# failed, while the tab is dark.
LEAGUE_CHART_PAGES = [
    ("league over time", "section=league&gview=time&gcmp=pos_C", "svg.eephus-line"),
    ("league over time pitchers", "section=league&gview=time&gside=pit&gcmp=role_RP", "svg.eephus-line"),
    ("league players chart", "section=league&gpos=C", ".mlbstats-table"),
]
_CHART_TEXT = r"""
() => {
  const root = document.getElementById('mlbstats-section-league');
  const d = root.querySelector('details[data-gfold="players"]');
  if (d) d.open = true;
  const svgs = Array.from(root.querySelectorAll('svg')).filter(s => s.getClientRects().length
    && s.getAttribute('aria-hidden') !== 'true');
  const hs = [];
  svgs.forEach(s => s.querySelectorAll('text').forEach(t => { const h = t.getBoundingClientRect().height; if (h) hs.push(h); }));
  return {n_svg: svgs.length, min_h: hs.length ? Math.min.apply(null, hs) : null,
          aria: svgs.every(s => s.getAttribute('role') === 'img' && !!s.getAttribute('aria-label')),
          page_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}
"""


@pytest.mark.parametrize("size", SIZES, ids=["%dx%d" % s for s in SIZES])
def test_the_league_charts_fit_and_print_readable_labels(browser, server, size):
    if not _league_built():
        pytest.skip("the League tab is dark in this build")
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems = []
    try:
        for label, hash_, sel in LEAGUE_CHART_PAGES:
            page.goto("about:blank")
            page.goto(server + "mlbstats/#" + hash_, wait_until="load", timeout=60_000)
            page.wait_for_selector("#mlbstats-section-league " + sel, timeout=30_000)
            page.wait_for_timeout(300)
            m = page.evaluate(_CHART_TEXT)
            where = "%dpx %s" % (w, label)
            if m["page_overflow"] > 0:
                problems.append("%s: the page scrolls sideways by %dpx" % (where, m["page_overflow"]))
            if not m["n_svg"]:
                problems.append("%s: no chart drawn" % where)
            elif m["min_h"] is not None and m["min_h"] < 8:
                problems.append("%s: a chart label prints %.1fpx tall" % (where, m["min_h"]))
            if not m["aria"]:
                problems.append("%s: a chart without role=img and an aria-label" % where)
    finally:
        ctx.close()
    assert not problems, "\n".join(problems)
