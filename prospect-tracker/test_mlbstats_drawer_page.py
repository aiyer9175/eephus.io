# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ player drawer (assets/mlbstats-drawer.js; owner ask 18 of
2026-09-30, final-pass plan Part 8 P8.2, task LT-09; owner answer LTS-3).

py_mini_racer, on the test_mlbstats_smoke.py setup: a stubbed DOM and a
synchronous fetch drive assets/mlbstats.js for real on the served hitter board.
Pinned here:
  * a dark shell (no data-drawer-src) draws no caret, ignores #player= and
    asks for nothing, so the board renders as it did before the drawer;
  * live, a caret leads every player row, and #player=<mlbam> opens ONE
    tr.mlbx-drawer straight under that player's row, with the caret's
    aria-expanded and aria-controls naming it;
  * the landing section requests no new URL and injects no script;
  * the drawer row takes no rank (site.css), and every drawer rule sits in the
    mlbx block;
  * the drawer module's percentile is the share below with ties counted half,
    flipped where lower is better, and a key the board does not carry (P/PA
    before the pitch-rate flip) draws no bar;
  * a rolling point is drawn only once its window is full, and the doubled
    window reads the same game rows (no refetch);
  * no copy string carries a forecast word, a hot or cold label or an arrow.
Nothing here writes a file or opens a socket.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
HUB_JS = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
MLBSTATS_JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
DRAWER_JS = (ROOT / "assets" / "mlbstats-drawer.js").read_text(encoding="utf-8")
SRC = "/assets/mlbstats-drawer.js?v=test"
SOTO = 665742


@pytest.fixture(scope="module")
def hitters():
    p = ROOT / "data" / "hitter_leaderboards.json"
    if not p.exists():
        pytest.skip("data/hitter_leaderboards.json is not built on this machine")
    doc = json.loads(p.read_text(encoding="utf-8"))
    if not any(r.get("mlbam") == SOTO and r.get("qualified") for r in doc.get("hitters") or []):
        pytest.skip("the sample player is not a qualified hitter on this build")
    return doc


def _prelude(hash_: str, live: bool, files: dict) -> str:
    attrs = {"data-drawer-src": SRC} if live else {}
    return """
    var __html = {}, __urls = [], __scripts = [];
    var __ATTR = %s;
    function __el(id) { return new Proxy(function () { return __el(id); }, {
      get: function (t, k) {
        if (k === 'innerHTML') return __html[id] || '';
        if (k === 'classList') return {add: function () {}, remove: function () {}, toggle: function () {}, contains: function () { return false; }};
        if (k === 'querySelectorAll') return function () { return []; };
        if (k === 'getAttribute') return function (n) { return id === 'q' && __ATTR[n] !== undefined ? __ATTR[n] : null; };
        if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener' || k === 'focus' || k === 'setSelectionRange' || k === 'appendChild') return function () {};
        if (k === 'querySelector' || k === 'closest') return function () { return __el(id + 'q'); };
        if (k === 'value' || k === 'textContent') return ''; if (k === 'checked') return true; if (k === 'selectionStart') return 0;
        if (k === 'clientWidth') return 1232;
        return __el(id); },
      set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
      apply: function () { return __el(id); }}); }
    function OK(val) { return {then: function (cb) { try { var r = cb(val); return (r && r.then) ? r : OK(r); } catch (e) { return BAD(e); } },
                               catch: function () { return OK(val); }}; }
    function BAD(err) { return {then: function (a, b) { if (b) { try { return OK(b(err)); } catch (e) { return BAD(e); } } return BAD(err); },
                                catch: function (cb) { try { return OK(cb(err)); } catch (e) { return BAD(e); } }}; }
    var __FILES = %s;
    var fetch = function (u) {
      __urls.push(String(u));
      var m = /[/]data[/]([^?]+)/.exec(String(u)); var f = m ? __FILES[m[1]] : null;
      return OK({ok: !!f, status: f ? 200 : 404, json: function () { return OK(f || null); }});
    };
    var history = {replaceState: function () {}};
    var location = {hash: '%s'};
    var document = {readyState: 'complete', getElementById: function (id) { return __el(id); },
      querySelector: function () { return __el('q'); }, querySelectorAll: function () { return []; },
      createElement: function (tag) { var o = {tag: tag}; if (tag === 'script') __scripts.push(o); return o; },
      addEventListener: function () {}, body: __el('body'), documentElement: __el('de'), head: __el('head')};
    var window = {location: location, document: document, history: history, fetch: fetch,
      EEPHUS_GL: {wire: function () {}}, addEventListener: function () {}, setTimeout: function () {}};
    var navigator = {userAgent: 'smoke'};
    var setTimeout = function () {}, clearTimeout = function () {};
    """ % (json.dumps(attrs), json.dumps(files), hash_)


def _board(hash_: str, live: bool, hitters: dict):
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, live, {"hitter_leaderboards.json": hitters}))
    ctx.eval(HUB_JS)
    ctx.eval(TIERS_JS + MLBSTATS_JS)
    return ctx


def _html(ctx) -> str:
    return ctx.eval("__html['mlbstats-hitters-root'] || ''")


# ---------------------------------------------------------------- dark
def test_a_dark_shell_draws_no_caret_and_ignores_the_player_key(hitters):
    ctx = _board("#section=hitters&player=%d" % SOTO, False, hitters)
    html = _html(ctx)
    assert "mlbstats-table" in html
    assert "mlbx-dcaret" not in html and "data-mlbdrawer" not in html
    assert "mlbx-drawer" not in html
    assert ctx.eval("__scripts.length") == 0
    urls = ctx.eval("JSON.stringify(__urls)")
    assert "drawer" not in urls and "mlbstats_trends" not in urls and "mlbstats_player" not in urls
    # the board is the board a bare hitters link draws
    assert html == _html(_board("#section=hitters", False, hitters))


# ---------------------------------------------------------------- live
def test_the_deep_link_opens_one_drawer_row_under_its_player(hitters):
    ctx = _board("#section=hitters&player=%d" % SOTO, True, hitters)
    html = _html(ctx)
    n_rows = sum(1 for r in hitters["hitters"] if r.get("qualified") is not False)
    assert html.count("mlbx-dcaret") == n_rows                 # a caret on every row shown
    assert len(re.findall(r'<tr[^>]*class="mlbx-drawer"', html)) == 1   # one drawer open
    did = "mlbx-drawer-hit-%d" % SOTO
    m = re.search(r'<tr[^>]*>(?:(?!</tr>).)*data-mlbdrawer="hit:%d"(?:(?!</tr>).)*</tr>'
                  r'<tr(?: data-mlbi="\d+")? class="mlbx-drawer" id="%s" data-export-skip><td colspan="\d+"'
                  % (SOTO, did), html, re.S)
    assert m, "the drawer row does not follow its player's row"
    caret = re.search(r'<button[^>]*data-mlbdrawer="hit:%d"[^>]*>' % SOTO, html).group(0)
    assert 'aria-expanded="true"' in caret and 'aria-controls="%s"' % did in caret
    assert caret.startswith('<button type="button"')           # Enter and Space, natively
    others = re.findall(r'<button[^>]*data-mlbdrawer="hit:(\d+)"[^>]*aria-expanded="true"', html)
    assert others == [str(SOTO)]
    assert "data-mlbdrawer-mount=\"hit:%d\"" % SOTO in html
    # The mount is filled (and the script injected) after the row is in a
    # real DOM: test_mlbstats_rank_and_charts.py drives that in Chromium.


def test_the_landing_requests_nothing_new(hitters):
    dark = _board("", False, hitters)
    live = _board("", True, hitters)
    assert live.eval("JSON.stringify(__urls)") == dark.eval("JSON.stringify(__urls)")
    assert live.eval("__scripts.length") == 0


def test_the_drawer_row_takes_no_rank_and_sits_in_the_mlbx_block():
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    i, j = css.index("/* ---- mlbx begin ---- */"), css.index("/* ---- mlbx end ---- */")
    block = css[i:j]
    assert ".mlbx .mlbstats-table tbody tr.mlbx-drawer { counter-increment: none; }" in block
    k = css.index("the player drawer (assets/mlbstats-drawer.js)")
    assert i < k < j
    assert "mlbx-drawer" not in css[:i] + css[j:]


# ---------------------------------------------------------------- the module
def _module():
    ctx = MiniRacer()
    ctx.eval("var window = {addEventListener: function () {}, innerWidth: 1280};"
             "var document = {addEventListener: function () {}};"
             "var fetch = function () { throw new Error('no fetch here'); };")
    ctx.eval(DRAWER_JS)
    return ctx


def test_the_percentile_counts_ties_half_and_flips_lower_is_better():
    ctx = _module()
    pr = lambda v, vals, low: ctx.eval("window.MLBX_DRAWER.pctRank(%s, %s, %s)"
                                       % (json.dumps(v), json.dumps(vals), "true" if low else "false"))
    assert pr(5, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], False) == 45     # 4 below, 1 tie: 4.5 of 10
    assert pr(5, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], True) == 55
    assert pr(10, list(range(1, 11)), False) == 95
    assert pr(1, list(range(1, 11)), True) == 95                     # the lowest K% reads near the top


def _pct_ctx(with_ppa: bool) -> str:
    rows = []
    for i in range(20):
        r = {"mlbam": 1000 + i, "qualified": True, "hem_plus": 80 + 2 * i, "k_pct": 0.30 - 0.005 * i,
             "bb_pct": 0.05 + 0.002 * i}
        if with_ppa:
            r["p_pa"] = 3.6 + 0.02 * i
        rows.append(r)
    me = rows[15]
    return """
    (function () {
      var rows = %s, me = rows[15], LBL = {hem_plus: "HEM+", k_pct: "K%%", bb_pct: "BB%%", p_pa: "P/PA"};
      return {board: "hit", id: String(me.mlbam), row: me, pool: {rows: rows, live: true, season: 2026},
              cell: function (k, r) { r = r || me; if (!(k in LBL)) return null;
                                      var v = r[k]; return {label: LBL[k], v: v == null ? null : v, html: String(v)}; }};
    })()""" % json.dumps(rows)


def test_percentiles_rank_against_the_qualified_pool_and_skip_a_missing_key():
    ctx = _module()
    got = json.loads(ctx.eval("JSON.stringify(window.MLBX_DRAWER.percentiles(%s))" % _pct_ctx(False)))
    by = {m["key"]: m for m in got["rows"]}
    assert set(by) == {"hem_plus", "k_pct", "bb_pct"}               # no P/PA bar without the key
    assert by["hem_plus"]["pct"] == 78 and by["hem_plus"]["n"] == 20
    assert by["k_pct"]["how"] == "low" and by["k_pct"]["pct"] == 77  # 4.5 of 20 below: 23, flipped to 77
    got = json.loads(ctx.eval("JSON.stringify(window.MLBX_DRAWER.percentiles(%s))" % _pct_ctx(True)))
    assert "p_pa" in {m["key"] for m in got["rows"]}
    html = ctx.eval("window.MLBX_DRAWER.pctPanel(%s)" % _pct_ctx(False))
    assert html.count('class="mlbp-slider"') == 3
    assert "K% is flipped: a lower value is better, so it draws the longer bar." in html


def test_a_rolling_point_is_drawn_only_once_its_window_is_full():
    ctx = _module()
    games = [["2026-04-%02d" % (i + 1), 4, 4, 1, 0, 0, 0, 0, 0, 0, i % 2, 16] for i in range(20)]
    blk = {"cols": ["date", "pa", "ab", "h", "d", "t", "hr", "bb", "hbp", "sf", "so", "pit"], "games": games}
    r15 = json.loads(ctx.eval("JSON.stringify(window.MLBX_DRAWER.rolling('hit', %s, 15))" % json.dumps(blk)))
    assert r15["games"] == 20 and len(r15["pts"]) == 6 and r15["pts"][0]["n"] == 15
    assert r15["pts"][0]["from"] == "2026-04-01" and r15["pts"][0]["to"] == "2026-04-15"
    assert abs(r15["pts"][0]["k"] - 7 / 60) < 1e-12 and abs(r15["pts"][0]["ppa"] - 4.0) < 1e-12
    r30 = json.loads(ctx.eval("JSON.stringify(window.MLBX_DRAWER.rolling('hit', %s, 30))" % json.dumps(blk)))
    assert r30["games"] == 20 and r30["pts"] == []
    # starts only, on the pitching side
    pit = {"cols": ["date", "gs", "bf", "outs", "so", "bb", "er", "pit", "li"],
           "games": [["2026-04-%02d" % (i + 1), 1 if i % 2 == 0 else 0, 20, 15, 5, 1, 2, 90, 1.0] for i in range(14)]}
    sp = json.loads(ctx.eval("JSON.stringify(window.MLBX_DRAWER.rolling('sp', %s, 5))" % json.dumps(pit)))
    assert sp["games"] == 7 and len(sp["pts"]) == 3 and sp["pts"][0]["pps"] == 90 and sp["pts"][0]["ips"] == 5
    assert json.loads(ctx.eval("JSON.stringify(window.MLBX_DRAWER.windows)")) == {"hit": [15, 30], "sp": [5, 10], "rel": [10, 20]}


def test_no_copy_string_carries_a_forecast_word_a_streak_label_or_an_arrow():
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', DRAWER_JS) + re.findall(r"'((?:[^'\\]|\\.)*)'", DRAWER_JS)
    text = " ".join(strings)
    for w in ("hot", "cold", "trending", "streak", "slump", "luck", "due", "regress", "will", "clutch", "sleeper"):
        assert not re.search(r"\b%s\b" % w, text, re.I), w
    for ch in ("↑", "↓", "▲", "▼", "↗", "↘"):
        assert ch not in DRAWER_JS
    assert "\u2014" not in DRAWER_JS and "\u2013" not in DRAWER_JS
