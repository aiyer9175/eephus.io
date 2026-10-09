# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX Leaderboards stat sheet (site pass PROSPX_2_LB_TABLE).

The single-stat card list (65 to 87 px rows, the stat hidden on phones, a "#"
that printed the board rank) became a condensed table: one row per prospect,
four views per side, header sort, the MiLB rate-title qualifier, one combined
"All MiLB" row per prospect-season, and the shared .mlbstats-table dialect for
the sticky header and the frozen Rk + Player rail (LANE_SURFACES 2.2).

Contract pinned here:
  * the columns and default sort of every view are the design's (2.2 tables);
  * every stat header carries the Library id test_prospx_lb_library.HEADER_GL
    gives it, and the identity and count columns carry none;
  * the rendered table: .mlbstats-col-rank on the Rk th and every Rk td,
    aria-sort on every sortable header with exactly one sorted, data-gl on
    every stat header;
  * no raw hex or rgba in the new code; cellHeatColor, the Standout ribbon on
    this tab, the stat chips and the four dead LB_STATS keys are gone;
  * served numbers: FIP and K-BB% print for every qualified pitcher and equal
    data/prospx_leaderboard.json; combined rows print the rates their summed
    components give; Rk is the position in the sort with equal printed values
    sharing a number; the window engine keeps _LB_FIP_CONST = 3.10;
  * in a browser: at 1280 the first row sits above y 600 with the filters
    closed, rows are 28 px and the header stays put after 40 rows; at 390 the
    sorted value is on screen on every row with no page overflow and rows are
    32 px.
Reads data/, never writes it.
"""
from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
import warnings
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conftest import load_data_doc, serve_site
from test_prospx_lb_library import HEADER_GL, NO_GL

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"

DESIGN = {  # LANE_SURFACES 2.2: columns after the identity block, default sort
    ("hit", "std"): (["PA", "G", "AVG", "OBP", "SLG", "OPS", "ISO", "BB%", "K%", "HR", "SB"], "OPS", "desc"),
    ("hit", "rel"): (["PA", "OPS+ lvl", "ISO+", "PD+", "POW+", "RPS+", "SC+", "$DvM+"], "RPS+", "desc"),
    ("hit", "bb"): (["BBE", "Avg EV", "90th EV", "Max EV", "Hard%", "Brl%", "Pull-air%", "xwOBA est",
                     "xwOBAcon est"], "90th EV", "desc"),
    ("hit", "swing"): (["Pitches", "Z-Swing%", "Z-Con%", "Chase%"], "Chase%", "asc"),
    ("pit", "std"): (["IP", "G", "ERA", "FIP", "WHIP", "K%", "BB%", "K-BB%", "HR/9"], "K-BB%", "desc"),
    ("pit", "rel"): (["IP", "ERA- lvl", "pStuff+", "KRP+"], "KRP+", "desc"),
    ("pit", "pitch"): (["Tracked", "FB velo", "FB IVB", "Whiff%", "Chase%", "Z-Swing%", "Z-Con%"], "Whiff%", "desc"),
    ("pit", "contact"): (["BBE", "Avg EVa", "HardA%", "BrlA%"], "HardA%", "asc"),
}
VIEW_NAMES = {"std": "Standard", "rel": "Level-relative", "bb": "Batted ball", "swing": "Swing decisions",
              "pitch": "Pitch data", "contact": "Contact allowed"}
IDENTITY = ["Rk", "Player", "Age", "Org", "Lvl", "eFV"]

CONFIG_START = "// Cross-org leaderboards: a stat sheet (site pass PROSPX_2_LB_TABLE)."
CONFIG_END = "// Watchlist tab - renders the starred"
RENDER_START = "// ---- Leaderboards stat sheet: data, rows, sort and render"
RENDER_END = "// =============================================================================\n// TIME MACHINE"
CSS_START = "/* ---- Leaderboards stat sheet (site pass PROSPX_2_LB_TABLE)"
CSS_END = "/* === Prospect news ticker"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8").replace("\r\n", "\n")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i:src.index(end, i)]


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, name
    return m.group(0)


# ---------------------------------------------------------------------------
# Static: the code that ships
# ---------------------------------------------------------------------------

def test_no_raw_colour_in_the_new_code():
    src = _src()
    for block in (_block(src, CONFIG_START, CONFIG_END), _block(src, RENDER_START, RENDER_END),
                  _block(src, CSS_START, CSS_END)):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b(?![=-])", re.sub(r"#(player|farm-org)=", "", block)), "raw hex"
        assert not re.search(r"rgba?\(", block), "raw rgb/rgba"


def test_the_retired_pieces_are_gone():
    src = _src()
    section = _block(src, '<div id="leaderboards-section"', "<!-- Charts - user-built scatter plots")
    assert "whats-standout-leaderboards" not in src            # the ribbon stays on Spotlights only
    assert "news-row-standout" not in section
    assert "data-lb-stat" not in src and "data-lb-dir" not in src and "data-lb-season" not in src
    assert "function cellHeatColor" not in src
    render = _block(src, RENDER_START, RENDER_END)
    for gone in ("headshotHTML", "rankTrendHTML", "compare-add-btn", "_miniSparkline", "rankNumRarityClass",
                 "fvRaritySpriteHTML", "cf-badge"):
        assert gone not in render, gone
    assert 'src="/assets/eephus-tiers.js?v=' in src
    assert re.search(r"^const _LB_FIP_CONST = 3\.10;$", src, re.M)


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval("""
      var window = {}; var state = {pageSizes: {leaderboard: 50}, pages: {leaderboard: 1}};
      var DATA = {players: []};
      function escapeHtml(s) { return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
      function getEfv(p) { return p._x || null; }
      function efvBoardValue(x) { return (x && x.xfv_grade != null) ? Number(x.xfv_grade) : null; }
      function efvGradeDisplay(x) { const v = efvBoardValue(x); return v != null ? Math.round(v) : null; }
      function inProvSection(p) { return false; }
      function boardRankOf(p) { return p._rank || null; }
      function fvClass(l) { return 'fv-' + (Math.floor(parseInt(l, 10) / 5) * 5); }
      function positionBucket(p) { return p; }
      function positionMatches(b, f) { return b === f; }
      function _pxSeasonLabel() { return 'Last'; }
      function _statRowOrgMetaHTML(p, r) { return {split: false, labelHTML: escapeHtml(r.org || '-')}; }
    """)
    ctx.eval(_block(src, CONFIG_START, CONFIG_END))
    ctx.eval(_block(src, RENDER_START, RENDER_END))
    return ctx


def test_every_view_has_the_designed_columns_and_default_sort(js):
    stats = js.eval("JSON.stringify(Object.fromEntries(Object.entries(LB_STATS).map(([k, v]) => [k, {label: v.label, hi: v.hi, gl: v.gl || null}])))")
    stats = json.loads(stats)
    views = json.loads(js.eval("JSON.stringify(LB_VIEWS)"))
    ids = json.loads(js.eval("JSON.stringify(LB_ID_COLS)"))
    assert [c["label"] for c in ids] == IDENTITY
    assert [c["w"] for c in ids] == [48, 200, 44, 52, 56, 44]
    got = {}
    for side, vs in views.items():
        assert [v["label"] for v in vs] == [VIEW_NAMES[v["id"]] for v in vs]
        for v in vs:
            labels = [stats[c[0]]["label"] for c in v["cols"]]
            sort = stats[v["sort"]]
            got[(side, v["id"])] = (labels, sort["label"], "desc" if sort["hi"] else "asc")
    assert got == DESIGN
    for gone in ("swing_plus", "k_per_9", "bb_per_9", "ivb_ff"):
        assert gone not in stats


def test_every_stat_header_points_at_its_library_entry(js):
    stats = json.loads(js.eval("JSON.stringify(Object.fromEntries(Object.entries(LB_STATS).map(([k, v]) => [k, {label: v.label, gl: v.gl || null}])))"))
    views = json.loads(js.eval("JSON.stringify(LB_VIEWS)"))
    want = {(s, v, label): gid for s, v, label, gid in HEADER_GL}
    for side, vs in views.items():
        for v in vs:
            for key, _w in v["cols"]:
                label = stats[key]["label"]
                gid = want.get((side, v["label"], label))
                if label in NO_GL:
                    assert stats[key]["gl"] is None, (side, v["label"], label)
                else:
                    assert gid is not None, (side, v["label"], label)
                    assert stats[key]["gl"] == gid, (side, v["label"], label, stats[key]["gl"], gid)
    ids = json.loads(js.eval("JSON.stringify(LB_ID_COLS)"))
    assert {c["label"]: c.get("gl") for c in ids}["eFV"] == "xfv"


# ---------------------------------------------------------------------------
# The rendered table (head and row HTML from the page's own functions)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def doc():
    d = load_data_doc("prospx_leaderboard.json")
    if not d or not d.get("rows"):
        pytest.skip("data/prospx_leaderboard.json not built")
    return d


@pytest.fixture(scope="module")
def loaded(js, doc):
    keys = sorted({r["k"] for r in doc["rows"]})
    pit = {r["k"] for r in doc["rows"] if r["side"] == "pit"}
    players = [{"player_key": k, "player_name": k, "position": "RHP" if k in pit else "SS",
                "statline": {}, "_x": {"xfv_grade": 45.4}, "_rank": i + 1} for i, k in enumerate(keys)]
    js.eval("DATA.prospx_leaderboard = %s;" % json.dumps(doc))
    js.eval("DATA.players = %s;" % json.dumps(players))
    js.eval("_lbIndex = null;")
    return js


class _Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.th, self.rows, self._row = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "th":
            self.th.append(a)
        elif tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._row.append(a)

    def handle_endtag(self, tag):
        if tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = None


def _render(js, side, view, season=None):
    js.eval("state.lbSide = %s; state.lbView = %s; state.lbSort = ''; state.lbDir = ''; state.lbSeason = %s;"
            % (json.dumps(side), json.dumps(view), json.dumps(str(season or ""))))
    return json.loads(js.eval("""(() => {
      const B = _lbBuild();
      const rows = B.view.src === 'season' ? _lbSeasonRows(B.ix, B.side, B.view, B.season, 'all')
                                           : _lbTrackRows(B.ix, B.side, B.view, 'all');
      _lbSortRows(rows, B.sortKey, B.dir);
      const order = LB_ID_COLS.map(c => ({k: c.k, w: c.w, label: c.label, title: c.title, gl: c.gl}))
        .concat(B.cols.map(c => ({k: c[0], w: c[1]})));
      const head = _lbHeadHTML(B, order);
      const body = rows.slice(0, 25).map(x => _lbRowHTML(B, order, x, () => 50)).join('');
      return JSON.stringify({html: '<table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>',
                             view: B.view.id, season: B.season, n: rows.length});
    })()"""))


@pytest.mark.parametrize("side,view", sorted(DESIGN))
def test_rendered_table_structure(loaded, side, view):
    out = _render(loaded, side, view)
    assert out["view"] == view and out["n"] > 0
    t = _Table()
    t.feed(out["html"])
    cols, sort_label, sort_dir = DESIGN[(side, view)]
    assert len(t.th) == len(IDENTITY) + len(cols)
    assert "mlbstats-col-rank" in t.th[0].get("class", "")
    assert "aria-sort" not in t.th[0]
    assert all(h.get("aria-sort") in ("none", "ascending", "descending") for h in t.th[1:])
    sorted_heads = [i for i, h in enumerate(t.th) if h.get("aria-sort") != "none" and i]
    assert len(sorted_heads) == 1
    assert t.th[sorted_heads[0]]["aria-sort"] == ("descending" if sort_dir == "desc" else "ascending")
    for i, h in enumerate(t.th[len(IDENTITY):]):
        if cols[i] in NO_GL:
            assert not h.get("data-gl"), (side, view, cols[i])
        else:
            assert h.get("data-gl"), (side, view, cols[i])
    assert t.th[IDENTITY.index("eFV")].get("data-gl") == "xfv"
    assert t.rows and all("mlbstats-col-rank" in r[0].get("class", "") for r in t.rows)
    assert all(len(r) == len(t.th) for r in t.rows)


def test_past_season_current_only_views_are_disabled_not_empty(loaded, doc):
    past = [s for s in doc["seasons"] if s != doc["current_season"]]
    if not past:
        pytest.skip("one season only")
    out = _render(loaded, "hit", "bb", past[-1])
    assert out["view"] == "std" and out["n"] > 0
    reasons = json.loads(loaded.eval("JSON.stringify(_lbBuild().reasons)"))
    assert "bb" in reasons and "swing" in reasons and "std" not in reasons


# ---------------------------------------------------------------------------
# Served numbers pinned to the export
# ---------------------------------------------------------------------------

def _fix(v, n):
    """Number.prototype.toFixed: the exact binary value, ties away from zero."""
    q = Decimal(1).scaleb(-n)
    return str(Decimal(v).quantize(q, rounding=ROUND_HALF_UP))


def _f3(v):
    t = _fix(v, 3)
    return t[1:] if t.startswith("0.") else t


def test_fip_and_kbb_print_for_every_qualified_pitcher(loaded, doc):
    got = json.loads(loaded.eval("""(() => {
      const ix = _lbIdx(); const out = [];
      for (const r of ix.doc.rows) {
        if (r.side !== 'pit' || !_lbQualifies(ix.doc, r)) continue;
        const x = {p: {player_name: r.k}, r: {vals: _lbPitVals(r)}};
        out.push([r.k, r.s, r.lvl, _lbCellText(x, 'fip'), _lbCellText(x, 'kbb')]);
      }
      return JSON.stringify(out);
    })()"""))
    assert len(got) > 500
    want = {(r["k"], r["s"], r["lvl"]): r for r in doc["rows"] if r["side"] == "pit"}
    for k, s, lvl, fip, kbb in got:
        r = want[(k, s, lvl)]
        assert fip != "-" and kbb != "-", (k, s, lvl)
        assert fip == _fix(r["fip"], 2), (k, s, lvl, fip, r["fip"])
        assert kbb == _fix(r["kbb"], 1), (k, s, lvl, kbb, r["kbb"])


def test_combined_rows_print_the_rates_of_their_summed_components(loaded, doc):
    got = json.loads(loaded.eval("""(() => {
      const ix = _lbIdx(); const out = [];
      for (const r of ix.doc.rows) {
        if (r.side !== 'hit' || r.lvl !== 'MiLB' || !(r.ab > 0)) continue;
        const x = {p: {player_name: r.k}, r: {vals: _lbHitVals(r)}};
        out.push([r.k, r.s, _lbCellText(x, 'obp'), _lbCellText(x, 'slg'), _lbCellText(x, 'ops'), _lbLvlText(r)]);
      }
      return JSON.stringify(out);
    })()"""))
    rows = {(r["k"], r["s"]): r for r in doc["rows"] if r["side"] == "hit" and r["lvl"] == "MiLB"}
    assert len(got) > 1000
    for k, s, obp, slg, ops, lvl in got:
        r = rows[(k, s)]
        o = (r["h"] + r["bb"] + r["hbp"]) / (r["ab"] + r["bb"] + r["hbp"] + r["sf"])
        g = (r["h"] + r["d"] + 2 * r["t"] + 3 * r["hr"]) / r["ab"]
        assert obp == _f3(o) and slg == _f3(g) and ops == _f3(o + g), (k, s)
        assert lvl == "/".join(r["lvls"]), (k, s, lvl)


def test_rk_is_the_position_in_the_sort(loaded, doc):
    got = json.loads(loaded.eval("""(() => {
      state.lbSide = 'hit'; state.lbView = 'std'; state.lbSort = ''; state.lbDir = ''; state.lbSeason = '';
      const B = _lbBuild();
      const rows = _lbSeasonRows(B.ix, 'hit', B.view, B.season, 'all').filter(x => x.r.qual);
      _lbSortRows(rows, 'ops', 'desc');
      return JSON.stringify(rows.map(x => [x.rk, _lbCellText(x, 'ops'), _lbCellVal(x, 'ops')]));
    })()"""))
    assert len(got) > 100
    first_at = {}
    for i, (rk, txt, v) in enumerate(got):
        first_at.setdefault(txt, i + 1)
        assert rk == first_at[txt], (i, rk, txt)
        if i:
            assert v <= got[i - 1][2]
    assert any(got[i][0] == got[i - 1][0] for i in range(1, len(got))), "no shared rank to exercise"


def test_qualifier_reads_the_rule_and_team_games_from_the_file(loaded, doc):
    q = doc["basis"]["qualifier"]
    assert (q["pa_per_team_game"], q["ip_per_team_game"]) == (2.7, 0.8)
    src = _block(_src(), RENDER_START, RENDER_END)
    assert "2.7 *" not in src and "0.8 *" not in src
    n = 0
    for r in doc["rows"]:
        tg = r.get("tg") if r["lvl"] == "MiLB" else doc["team_games"].get(str(r["s"]), {}).get(r["lvl"])
        want = bool(tg) and ((r.get("pa", 0) >= 2.7 * tg) if r["side"] == "hit" else (r.get("outs", 0) / 3 >= 0.8 * tg))
        got = loaded.eval("_lbQualifies(DATA.prospx_leaderboard, %s)" % json.dumps(r))
        assert got == want, r
        n += 1
        if n > 3000:
            break


# ---------------------------------------------------------------------------
# In a browser
# ---------------------------------------------------------------------------

_MEASURE = """() => {
  const t = document.querySelector('#leaderboard-rows table.px-lb-table');
  const rows = [...t.querySelectorAll('tbody tr')];
  const hs = rows.map(r => r.getBoundingClientRect().height).sort((a, b) => a - b);
  const th = t.querySelector('th.is-sorted');
  const idx = [...th.parentNode.children].indexOf(th);
  return {
    filtersOpen: document.getElementById('leaderboard-bar').classList.contains('is-open'),
    firstTop: rows[0].getBoundingClientRect().top + scrollY,
    rowH: hs[hs.length >> 1], n: rows.length, docW: document.documentElement.scrollWidth,
    visible: rows.every(r => { const c = r.children[idx]; const b = c.getBoundingClientRect();
      return b.left >= 0 && b.right <= innerWidth + 0.5 && c.textContent.trim() !== ''; }),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    if not (ROOT / "data" / "timeseries.json").exists() or not (ROOT / "data" / "prospx_leaderboard.json").exists():
        pytest.skip("data not built")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        with serve_site() as base:
            yield b, base
        b.close()


def _open(browser, width):
    b, base = browser
    pg = b.new_page(viewport={"width": width, "height": 900 if width > 600 else 844})
    pg.goto(base + "prospx/#tab=leaderboards", wait_until="domcontentloaded", timeout=180000)
    pg.wait_for_selector("#leaderboard-rows table.px-lb-table tbody tr", timeout=300000)
    pg.evaluate("() => window.scrollTo(0, 0)")
    return pg


def test_desktop_density_and_sticky_header(browser):
    pg = _open(browser, 1280)
    m = pg.evaluate(_MEASURE)
    assert not m["filtersOpen"]
    assert m["firstTop"] < 600, m
    assert abs(m["rowH"] - 28) <= 0.5, m
    stuck = pg.evaluate("""() => { const sc = document.querySelector('.px-lb-scroll'); sc.scrollIntoView();
      sc.scrollTop = 40 * 28; const a = document.querySelector('.px-lb-table thead th').getBoundingClientRect();
      const b = sc.getBoundingClientRect(); return Math.abs(a.top - b.top) < 1; }""")
    assert stuck
    pg.close()


def test_phone_keeps_the_sorted_value_on_screen(browser):
    pg = _open(browser, 390)
    m = pg.evaluate(_MEASURE)
    assert m["docW"] <= 390, m
    assert m["visible"], m
    assert abs(m["rowH"] - 32) <= 0.5, m
    pg.close()


def test_heat_is_the_percentile_in_the_level_pool_not_in_the_filtered_rows(browser):
    """The sorted cell's tint is its percentile among every qualified row of the
    side, season and level (LANE_SURFACES 2.2), so an Org filter keeps it."""
    pg = _open(browser, 1280)
    out = pg.evaluate("""() => {
      const tint = k => { const tr = document.querySelector('.px-lb-table tbody tr[data-key="' + k + '"]');
        const td = tr && tr.querySelector('td.px-lb-sorted'); return td ? td.getAttribute('style') : null; };
      const k = document.querySelector('.px-lb-table tbody tr:nth-child(5)').dataset.key;
      const before = tint(k);
      const org = _lbLast.rows.find(x => x.p.player_key === k).r.org;
      state.lbOrg = org; renderLeaderboards();
      const after = tint(k), n = _lbLast.rows.length;
      state.lbOrg = 'all'; renderLeaderboards();
      return {k, org, before, after, n};
    }""")
    assert out["before"] and out["before"] == out["after"], out
    assert out["n"] < 100, out
    pg.close()
