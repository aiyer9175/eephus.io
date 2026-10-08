# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The team picker: team logos in every team dropdown (owner ask 2026-09-24,
"add team logos to every dropdown menu that is team-based, similar to how we
did with PROSPX").

assets/eephus-teampick.js upgrades any select[data-team-picker] in place: the
native select stays in the page as the value, the options and the handlers,
and a logo trigger plus a searchable listbox is painted beside it. What is
pinned here:

  WIRED     every team select the 2026-09-24 census found carries the
            attribute at its build site. The list is written out, so a new
            team select that is not marked shows up in review as a missing
            row, and one that loses the attribute fails by name.
  NOT WIRED the one team control that is not a dropdown (the FA Team fits chip
            row) is named with its reason, and no team-named select anywhere
            in the served sources goes unmarked without a row here.
  LOGOS     the one club resolver (EEPHUS_HUB.club in assets/eephus-hub.js)
            covers the thirty clubs and every code alias a source spells
            differently, and agrees with trades.canonical_org, the Python
            canonicaliser, on every one of them.
  PAGE      on three pages (a generated MLB page, the fantasy dynasty board,
            the PROSPX charts tab) the trigger renders, the panel lists thirty
            logos plus All, a pick sets the native value and fires change,
            Escape closes and gives focus back, and at 390 the panel stays
            inside the viewport.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---- WIRED ---------------------------------------------------------------------
# (source file, the id or marker that finds the select's opening tag). Every
# row is a team select from the census; the tag must carry data-team-picker.
WIRED = [
    ("assets/arbitration.js", 'id="arb-team"'),
    ("assets/ledger.js", 'id="ledger-club"'),
    ("assets/franchise.js", 'id="fr-club"'),
    ("assets/projections.js", 'id="proj-team"'),
    ("assets/redraft.js", 'id="rd-f-team"'),
    ("assets/dynasty.js", 'id="dyn-f-org"'),
    ("assets/dfs.js", 'id="dfs-f-team"'),
    ("build_site.py", 'id="tb-org-filter"'),
    ("prospx/index.html", 'id="chart-filter-org"'),
    ("prospx/index.html", 'id="ifa-all-org"'),
    ("prospx/index.html", 'id="farm-compare-select"'),
    ("prospx/index.html", 'id="sim-team-select"'),
    ("collegesavant/app.js", "data-team-filter"),
    ("collegesavant/pitcher_app.js", "data-team-filter"),
    # the Alchemy Lab's org filter, one select over every player list (2026-10-08)
    ("assets/pal.js", 'id="pal-org"'),
]
# The six MLB Stats team selects are built by one helper, teamSelect(id, ...),
# and the management club select by sel(id, opts, label, attrs).
MLBSTATS_IDS = ("mlbstats-team", "mlbstats-starter-team", "mlbstats-hitter-team",
                "mlbstats-leverage-team", "mlbstats-defense-team", "mlbstats-war-team")

# Team controls that are deliberately left alone, with the reason.
NOT_WIRED = {
    "assets/fa.js button[data-fa-team]": "a row of thirty chip buttons, not a dropdown",
}


def _select_tags(text: str, marker: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"<select\b[^>]*>", text) if marker in m.group(0)]


@pytest.mark.parametrize("rel,marker", WIRED)
def test_every_census_team_select_is_marked(rel, marker):
    tags = _select_tags(_src(rel), marker)
    assert tags, (rel, marker, "the select is gone from its build site")
    for t in tags:
        assert "data-team-picker" in t, (rel, t)


def test_the_college_selects_ask_for_the_school_mode():
    for rel in ("collegesavant/app.js", "collegesavant/pitcher_app.js"):
        for t in _select_tags(_src(rel), "data-team-filter"):
            assert 'data-team-picker="college"' in t, (rel, t)


def test_the_helper_built_team_selects_are_marked():
    js = _src("assets/mlbstats.js")
    helper = re.search(r"function teamSelect\(id[^)]*\)\s*\{(.*?)\n  \}", js, re.S)
    assert helper, "teamSelect helper not found"
    assert "data-team-picker" in helper.group(1)
    for i in MLBSTATS_IDS:
        assert re.search(r"teamSelect\(\s*['\"]" + re.escape(i) + r"['\"]", js), (i, "no longer built by teamSelect")
    mg = _src("assets/management.js")
    assert re.search(r"sel\(\s*\"mgmt-club\"[^)]*\"data-team-picker\"\)", mg), "mgmt-club lost the attribute"


def test_no_team_named_select_goes_unmarked():
    """A select whose id names a team, an org or a club is a team select
    unless it is listed as something else here."""
    not_team = {"tb-exact-pos-filter"}
    files = [*sorted(ROOT.glob("assets/*.js")), ROOT / "build_site.py", ROOT / "prospx/index.html"]
    bad = []
    for p in files:
        if p.name in ("eephus-teampick.js", "fantasy.js"):   # the component itself; the frozen parity copy
            continue
        for t in re.findall(r"<select\b[^>]*>", p.read_text(encoding="utf-8")):
            m = re.search(r'id="([^"$]+)"', t)
            if not m or m.group(1) in not_team:
                continue
            if re.search(r"team|org|club", m.group(1), re.I) and "data-team-picker" not in t:
                bad.append((p.name, m.group(1)))
    assert not bad, bad


def test_the_not_wired_chip_row_is_still_a_chip_row():
    js = _src("assets/fa.js")
    assert "data-fa-team" in js and not _select_tags(js, "data-fa-team"), NOT_WIRED


def test_every_page_that_marks_a_select_loads_the_picker_after_the_hub():
    for page in ("arbitration", "ledger", "franchise", "management", "mlbstats", "projections",
                 "trademachine", "fantasy", "pal"):
        html = _src(page + "/index.html")
        hub = html.find("/assets/eephus-hub.js?v=")
        pick = html.find("/assets/eephus-teampick.js?v=")
        assert hub >= 0 and pick > hub, page
    for page in ("prospx/index.html", "collegesavant/index.html", "collegesavant/pitcher_index.html"):
        html = _src(page)
        hub = html.find("/assets/eephus-hub.js?v=")
        pick = html.find("/assets/eephus-teampick.js?v=")
        assert hub >= 0 and pick > hub, page


# ---- LOGOS -----------------------------------------------------------------------
ROW_RE = re.compile(r'\["([A-Z]{3})", "([a-z]+)", "([^"]+)", (\d+)((?:, "[A-Z]+")*)\]')
ALIASES = {"AZ": "ARI", "CWS": "CHW", "KC": "KCR", "SD": "SDP", "SF": "SFG", "TB": "TBR",
           "WSH": "WSN", "OAK": "ATH", "FLA": "MIA"}


def _club_rows():
    js = _src("assets/eephus-hub.js")
    block = js[js.index("var _CLUB_ROWS"):js.index("var _CLUB_OLD_NAMES")]
    rows = {}
    for code, slug, name, mlbam, al in ROW_RE.findall(block):
        rows[code] = {"slug": slug, "name": name, "id": int(mlbam), "aliases": re.findall(r'"([A-Z]+)"', al)}
    return rows


def test_the_club_table_holds_thirty_clubs_and_every_alias():
    rows = _club_rows()
    assert len(rows) == 30, sorted(rows)
    assert len({r["id"] for r in rows.values()}) == 30
    alias_to = {a: c for c, r in rows.items() for a in r["aliases"]}
    for a, c in ALIASES.items():
        assert alias_to.get(a) == c, (a, alias_to.get(a), c)
    # logos come through ESPN's resizing combiner since QCLP05 (2026-10-02)
    assert "https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/" in _src("assets/eephus-hub.js")


def test_the_club_table_agrees_with_the_python_canonicaliser():
    trades = pytest.importorskip("trades")
    rows = _club_rows()
    for code, r in rows.items():
        assert trades.canonical_org(code) == code, code
        assert trades.canonical_org(r["name"]) == code, (r["name"], trades.canonical_org(r["name"]))
        for a in r["aliases"]:
            # FLA is folded to the Marlins for the logo only; canonical_org
            # passes a short code through unless it is in its remap, and the
            # 2011 Marlins code is not. Its full name agrees.
            if a == "FLA":
                assert trades.canonical_org("Florida Marlins") == code
                continue
            assert trades.canonical_org(a) == code, (a, trades.canonical_org(a), code)
        got = trades.canonical_org_from_id(r["id"])
        if got is not None:                      # tjstats is optional on this machine
            assert got == code, (r["id"], got, code)


# ---- PAGE ------------------------------------------------------------------------
_PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                     "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")

PAGES = [
    ("arbitration", "arbitration/", "#arb-team", None),
    ("fantasy dynasty", "fantasy/#m=dynasty", "#dyn-f-org", None),
    ("prospx charts", "prospx/#tab=charts", "#chart-filter-org", None),
    ("pal", "pal/", "#pal-org", None),
]

_STATE = r"""
s => { const sel = document.querySelector(s); if (!sel) return null;
  const t = sel.previousElementSibling;
  return { enhanced: !!sel._teampick, n: sel.options.length, value: sel.value,
           display: getComputedStyle(sel).display, tabindex: sel.getAttribute('tabindex'),
           trig: t && t.classList.contains('teampick-trigger'), haspopup: t && t.getAttribute('aria-haspopup'),
           expanded: t && t.getAttribute('aria-expanded'), aria: t && t.getAttribute('aria-label'),
           label: t && t.innerText.trim(), text: sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '' }; }
"""
_PANEL = r"""
() => { const p = document.querySelector('.teampick-panel'); if (!p) return null;
  const r = p.getBoundingClientRect();
  const rows = p.querySelectorAll('[role=option]');
  return { listbox: !!p.querySelector('[role=listbox]'), rows: rows.length,
           logos: Array.prototype.filter.call(rows, x => { const i = x.querySelector('img.teampick-logo');
             return i && i.src.indexOf('https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/') === 0; }).length,
           glyphs: p.querySelectorAll('.teampick-glyph').length,
           left: r.left, right: r.right, top: r.top, bottom: r.bottom,
           vw: document.documentElement.clientWidth, vh: innerHeight }; }
"""


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site
    with serve_site() as base, sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip("chromium unavailable: %s" % e)
        yield base, b
        b.close()


def _page(browser, w, h):
    base, b = browser
    ctx = b.new_context(viewport={"width": w, "height": h})
    ctx.route(re.compile(r"^https://a\.espncdn\.com/.*"),
              lambda route: route.fulfill(status=200, content_type="image/png", body=_PNG))
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:|https://a\.espncdn\.com/).*"), lambda route: route.abort())
    page = ctx.new_page()
    page.set_default_timeout(30_000)
    return base, ctx, page


def _open(page, base, path, css):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + path, wait_until="load", timeout=60_000)
    page.wait_for_function(
        "s => { const e = document.querySelector(s); return e && e.options.length > 1 && e._teampick; }", arg=css)
    page.wait_for_timeout(300)
    return errors


@pytest.mark.parametrize("label,path,css,_", PAGES, ids=[p[0] for p in PAGES])
def test_the_picker_on_the_page(browser, label, path, css, _):
    base, ctx, page = _page(browser, 1280, 900)
    try:
        errors = _open(page, base, path, css)
        st = page.evaluate(_STATE, css)
        assert st["trig"] and st["display"] == "none" and st["tabindex"] == "-1", (label, st)
        assert st["haspopup"] == "listbox" and st["expanded"] == "false", (label, st)
        assert st["text"] in st["aria"], (label, st)
        trig = page.locator(css).locator("xpath=preceding-sibling::button[1]")
        trig.scroll_into_view_if_needed()
        trig.click()
        panel = page.evaluate(_PANEL)
        assert panel and panel["listbox"], (label, panel)
        assert panel["rows"] == st["n"] == 31 and panel["logos"] == 30 and panel["glyphs"] == 1, (label, panel)
        assert page.evaluate("s => document.querySelector(s).previousElementSibling.getAttribute('aria-expanded')",
                             css) == "true"
        # pick the fifth club; the module's own change handler runs
        page.evaluate("""s => { window.__tp = []; document.addEventListener('change', e => {
            if (e.target.matches && e.target.matches(s)) window.__tp.push(e.target.value); }, true); }""", css)
        want = page.evaluate("s => document.querySelector(s).options[5].value", css)
        page.locator('.teampick-panel [role=option][data-i="5"]').click()
        page.wait_for_timeout(600)
        assert page.evaluate("() => window.__tp") == [want], label
        after = page.evaluate(_STATE, css)
        assert after["value"] == want and want in after["label"], (label, want, after)
        assert not page.evaluate("() => !!document.querySelector('.teampick-panel')")
        # Escape closes and hands focus back to the trigger
        page.evaluate("s => document.querySelector(s).previousElementSibling.focus()", css)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(150)
        assert page.evaluate("() => document.activeElement.getAttribute('role')") == "option", label
        page.keyboard.press("End")
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        assert page.evaluate("""s => !document.querySelector('.teampick-panel')
            && document.activeElement === document.querySelector(s).previousElementSibling""", css), label
        assert page.evaluate("s => document.querySelector(s).value", css) == want, label
        # Enter in an EMPTY search keeps the chosen club (the first row is "All";
        # taking it silently reset the filter, review finding 2026-09-24)
        trig.click()
        page.wait_for_timeout(150)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        assert not page.evaluate("() => !!document.querySelector('.teampick-panel')"), label
        assert page.evaluate("s => document.querySelector(s).value", css) == want, label
        assert page.evaluate("() => window.__tp") == [want], label
        # a type-ahead "/" on a focused row stays in the picker: the site's
        # quick-search shortcut must not open over it
        trig.click()
        page.wait_for_timeout(150)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("/")
        page.wait_for_timeout(200)
        assert page.evaluate("""() => { const o = document.getElementById('qk-overlay');
            return !(o && o.classList.contains('is-open')); }"""), label
        assert page.evaluate("() => !!document.querySelector('.teampick-panel')"), label
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        # Tab closes the panel and moves on past the trigger
        trig.click()
        page.wait_for_timeout(150)
        page.keyboard.press("Tab")
        page.wait_for_timeout(200)
        assert page.evaluate("""s => !document.querySelector('.teampick-panel')
            && document.activeElement !== document.querySelector(s).previousElementSibling""", css), label
        assert page.evaluate("s => document.querySelector(s).value", css) == want, label
        assert not errors, (label, errors)
    finally:
        ctx.close()


@pytest.mark.parametrize("label,path,css,_", PAGES, ids=[p[0] for p in PAGES])
def test_the_panel_stays_inside_a_phone_viewport(browser, label, path, css, _):
    base, ctx, page = _page(browser, 390, 844)
    try:
        _open(page, base, path, css)
        trig = page.locator(css).locator("xpath=preceding-sibling::button[1]")
        trig.scroll_into_view_if_needed()
        trig.click()
        page.wait_for_timeout(200)
        p = page.evaluate(_PANEL)
        assert p, label
        assert p["left"] >= 0 and p["right"] <= p["vw"] and p["top"] >= 0 and p["bottom"] <= p["vh"], (label, p)
        assert page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    finally:
        ctx.close()


# The trigger replaces a select that stood in a bar beside other fields; it
# must stand at that height (rendered review 2026-09-25: 24px beside the 27px
# search on /mlbstats/, 24 beside the 25.6px season select on /management/,
# 24 beside the 44px PROSPX chart selects at phone width, and 24 beside the
# 27px player search on /arbitration/).
HEIGHT_CASES = [
    ("mlbstats bullpen", "mlbstats/#section=bullpen", "#mlbstats-team", "#mlbstats-q", 1280, 900),
    ("management clubs", "management/#section=clubs", "#mgmt-club", "#mgmt-cseason", 1280, 900),
    ("prospx charts phone", "prospx/#tab=charts", "#chart-filter-org", "#chart-filter-level", 390, 844),
    ("arbitration", "arbitration/", "#arb-team", "#arb-q", 1280, 900),
]


@pytest.mark.parametrize("label,path,css,sib,w,h", HEIGHT_CASES, ids=[c[0] for c in HEIGHT_CASES])
def test_the_trigger_stands_at_its_bar_height(browser, label, path, css, sib, w, h):
    base, ctx, page = _page(browser, w, h)
    try:
        _open(page, base, path, css)
        got = page.evaluate("""([s, o]) => { const t = document.querySelector(s).previousElementSibling;
            const b = document.querySelector(o); if (!t || !b) return null;
            return {trig: t.getBoundingClientRect().height, sib: b.getBoundingClientRect().height}; }""",
                            [css, sib])
        assert got and got["sib"] > 0, (label, got)
        assert abs(got["trig"] - got["sib"]) <= 1.0, (label, got)
    finally:
        ctx.close()
