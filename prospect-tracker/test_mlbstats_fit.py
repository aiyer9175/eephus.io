# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ boards fit the screen: the served page, measured in Chromium.

Owner ask 2026-09-11: "make it so that the chart fits on one screen without a
need for horizontal scrolling". Before the column views the reliever and hitter
boards ran 1,424 to 1,900px wide against a 1,352px container and scrolled
sideways at every desktop width. The views (Standard, Skill, Value, Leverage,
Batting, Runs) carry 9 to 13 columns each; All carries every column.

THE BUDGET RULE, asserted on the SERVED page and the served data:
  * the page itself never scrolls sideways, at any width, on any board;
  * every named view (every view but All), qualified filter on and off, fits
    its own table box at 768px and wider, and its phone subset fits at 390px;
  * All fits at 1263px (a 1280 window with a classic 17px scrollbar) and wider;
    narrower, All may scroll inside its own box, never the page;
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
]
SIZES = [(390, 844), (768, 1024), (1024, 768), (1280, 800), (1440, 900)]
ALL_FITS_FROM = 1263
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
    page.wait_for_timeout(200)


def _check(m, w, where, problems, all_only=False):
    if m is None:
        problems.append("%s: no board table rendered" % where)
        return
    if m["page_overflow"] > 0:
        problems.append("%s: the PAGE scrolls sideways by %dpx" % (where, m["page_overflow"]))
    fits = m["sc_sw"] <= m["sc_cw"] and m["table_w"] <= m["sc_cw"]
    must_fit = (w >= ALL_FITS_FROM) if m["all"] else (not all_only)
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
                _check(m, w, where, problems)
                measured += 1
                exempt = (w <= PHONE_MAX and sec in PHONE_EWAR_EXEMPT)
                if m and (v is None or v.endswith(":standard")) and m["war_hidden"] and not exempt:
                    problems.append("%s: eWAR column hidden on the Standard view: %s" % (where, m["war_hidden"]))
                if qual and m and not m["all"]:
                    page.evaluate("(id) => document.getElementById(id).click()", qual)
                    _check(page.evaluate(_MEASURE, sec), w, where + " qualified off", problems)
                    page.evaluate("(id) => document.getElementById(id).click()", qual)
                    measured += 1
    finally:
        ctx.close()
    assert measured >= 30, measured
    assert not problems, "\n".join(problems)


def test_the_all_view_fits_a_1280_window_with_a_classic_scrollbar(browser, server):
    ctx = _context(browser, ALL_FITS_FROM, 800)
    page = ctx.new_page()
    problems = []
    try:
        for label, sec, hash_, _qual in PAGES[:4]:
            _open(page, server, sec, hash_)
            alls = [v for v in page.evaluate(_VIEWS, sec) if v.endswith(":all")]
            assert alls, label
            page.evaluate("(v) => document.querySelector('[data-colview=\"' + v + '\"]').click()", alls[0])
            m = page.evaluate(_MEASURE, sec)
            assert m and m["all"], label
            _check(m, ALL_FITS_FROM, "%dpx %s all" % (ALL_FITS_FROM, label), problems, all_only=True)
    finally:
        ctx.close()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("size", [(390, 844), (1440, 900)], ids=["390x844", "1440x900"])
def test_a_fitted_board_keeps_its_header_at_the_top_after_a_long_scroll(browser, server, size):
    ctx = _context(browser, *size)
    page = ctx.new_page()
    try:
        for sec in ("bullpen", "hitters"):
            _open(page, server, sec, "section=" + sec)
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


@pytest.mark.parametrize("size", [(390, 844), (768, 1024), (1440, 900)], ids=["390x844", "768x1024", "1440x900"])
def test_the_vertical_budget_on_every_section(browser, server, size):
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems = []
    try:
        for label, sec, hash_, _qual in PAGES[:5]:
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
        for label, sec, hash_, _qual in PAGES[:5]:
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
                       "leverage": "Leverage", "defense": "Defense", "war": "eWAR"}.items():
        assert labels.get(sec) == label, (sec, labels, "rerun build_site.py")
    # O1: Bullpen stays the landing board and eWAR is the LAST button, so no
    # bare /mlbstats/ URL changes what it opens.
    assert list(labels)[0] == "bullpen" and list(labels)[-1] == "war", list(labels)
