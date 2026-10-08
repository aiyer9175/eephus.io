# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The League tab of /mlbstats/ (assets/mlbstats-league.js; owner asks 13 and
14 of 2026-09-30, final-pass plan Part 8 P8.2, task LT-08, the League half).

py_mini_racer, on the test_mlbstats_smoke.py setup: a stubbed DOM and a
synchronous fetch drive assets/mlbstats.js and the League script for real.
Pinned here:
  * the Averages and Over time views render rows;
  * "vs all" appears only while a filter is on;
  * the landing section requests no League URL and injects no script, and a
    dark shell (no data-league-src) ignores section=league outright;
  * the g keys round-trip through the hash, through mlbstats.js writeHash;
  * a Leverage deep link with lview and lseason still opens Leverage, and the
    League state does not read either key;
  * ONE RECIPE: pooling the payload's player rows in the browser reproduces
    every precomputed group of a real season (league_averages.py derived them
    through the shipped derivations), count for count and value for value;
  * no hash key or group names a grade, and no copy string in the script
    carries a forecast word.

The panels are built from the gitignored season caches (as
test_league_averages_export.py builds them); the tests that need them skip
when the caches are absent. Nothing here writes a file or opens a socket.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
CACHE = ROOT / ".cache"
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
HUB_JS = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
MLBSTATS_JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
LEAGUE_JS = (ROOT / "assets" / "mlbstats-league.js").read_text(encoding="utf-8")
SRC = "/assets/mlbstats-league.js?v=test"


def _have(season: int) -> bool:
    return ((CACHE / f"fa_statsapi_hitting_{season}.json").exists()
            and (CACHE / f"fa_statsapi_pitching_{season}.json").exists())


@pytest.fixture(scope="module")
def payloads():
    """A completed season's panel and the live one, and the series over them."""
    if not _have(2025):
        pytest.skip("season caches absent")
    import league_averages as L
    live = L.live_season_of()
    panels = {}
    for y in sorted({2024, 2025, live}):
        if _have(y):
            panels[y] = L.build_panel(y, live_season=live)
    series = L.build_series(panels, live_season=live)
    return {"panels": panels, "series": series, "live": live}


def _prelude(hash_: str, live: bool, panels: dict, series: dict | None, live_season: int) -> str:
    """The smoke-test DOM stub, plus: the root's data-league-src while `live`,
    a fetch that serves the League payloads by URL and records every URL, a
    synchronous thenable that carries a throw to the next catch (so a loader's
    error path runs instead of escaping), and a script-element recorder."""
    attrs = {"data-league-src": SRC, "data-league-live": str(live_season)} if live else {}
    return """
    var __html = {}, __urls = [], __scripts = [], __hash = [];
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
    var __PANELS = %s, __SERIES = %s;
    var fetch = function (u) {
      __urls.push(String(u));
      var m = /mlb_league_panel_(\\d{4})/.exec(u);
      if (m) return OK({ok: !!__PANELS[m[1]], json: function () { return OK(__PANELS[m[1]] || null); }});
      if (/mlb_league_series/.test(u)) return OK({ok: !!__SERIES, json: function () { return OK(__SERIES); }});
      return OK({ok: false, status: 404, json: function () { return OK(null); }});
    };
    var history = {replaceState: function (a, b, u) { __hash.push(String(u)); }};
    var location = {hash: '%s'};
    var document = {readyState: 'complete', getElementById: function (id) { return __el(id); },
      querySelector: function () { return __el('q'); }, querySelectorAll: function () { return []; },
      createElement: function (tag) { var o = {tag: tag}; if (tag === 'script') __scripts.push(o); return o; },
      addEventListener: function () {}, body: __el('body'), documentElement: __el('de'), head: __el('head')};
    var window = {location: location, document: document, history: history, fetch: fetch,
      EEPHUS_GL: {wire: function () {}}, addEventListener: function () {}, setTimeout: function () {}};
    var navigator = {userAgent: 'smoke'};
    var setTimeout = function () {}, clearTimeout = function () {};
    """ % (json.dumps(attrs), json.dumps({str(k): v for k, v in panels.items()}),
           json.dumps(series), hash_)


def _ctx(hash_: str, payloads: dict | None, live: bool = True, with_league: bool = True):
    p = payloads or {"panels": {}, "series": None, "live": 2026}
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, live, p["panels"], p["series"], p["live"]))
    ctx.eval(HUB_JS)
    ctx.eval(TIERS_JS + MLBSTATS_JS)
    if with_league:
        ctx.eval(LEAGUE_JS)
    return ctx


def _league_html(ctx) -> str:
    return ctx.eval("__html['mlbstats-league-root'] || ''")


# ---------------------------------------------------------------- the views
def test_the_averages_view_renders_rows_for_each_side(payloads):
    for side, want in (("", ("AVG", "OBP", "P/PA", "HEM+")), ("&gside=pit", ("ERA", "P/IP", "SEM+")),
                       ("&gside=team", ("RS/G", "Rotation P/IP", "Relief IP share"))):
        html = _league_html(_ctx("#section=league" + side, payloads))
        assert "mlbx-lgtable" in html, side
        assert html.count("<tr") >= 10, side
        for label in want:
            assert label in html, (side, label)
        assert "Every number here is what happened, pooled." in html


def test_vs_all_appears_only_while_a_filter_is_on(payloads):
    assert ">vs all<" not in _league_html(_ctx("#section=league", payloads))
    assert ">vs all<" not in _league_html(_ctx("#section=league&gside=pit", payloads))
    for h in ("&gpos=C", "&ghand=L", "&gage=age_25_27", "&gqual=floor", "&glg=AL", "&gside=pit&grole=RP",
              "&gpos=C,SS&ghand=L&gqual=150"):
        html = _league_html(_ctx("#section=league" + h, payloads))
        assert ">vs all<" in html, h
        # signed, in text ink: the cell carries no ruler or up/down class
        cells = re.findall(r'<td class="([^"]*mlbx-lgvs[^"]*)">', html)
        assert cells and all(c == "mlbx-lgnum mlbx-lgvs" for c in cells), (h, set(cells))


def test_the_over_time_view_draws_the_chart_the_glance_grid_and_the_numbers(payloads):
    html = _league_html(_ctx("#section=league&gview=time&gcmp=pos_C", payloads))
    assert "eephus-line" in html and 'role="img"' in html
    assert "Position C" in html                       # the compare series is drawn and named
    assert html.count('data-gpick="') >= 8             # the small multiples
    assert "eephus-chart-table" in html and "<td>" in html   # the numbers twin
    for y in payloads["panels"]:
        assert ">%d<" % y in html
    html = _league_html(_ctx("#section=league&gview=time&gside=pit&gstat=p_per_ip&gcmp=role_RP", payloads))
    assert "Relievers" in html and "P/IP by season" in html


def test_a_missing_panel_paints_a_failed_state_with_retry(payloads):
    html = _league_html(_ctx("#section=league&gseason=2001", payloads))
    assert "did not load" in html and 'data-gretry="panel"' in html


# ---------------------------------------------------------------- what the landing asks for
def test_the_landing_section_requests_no_new_url(payloads):
    ctx = _ctx("", payloads, with_league=False)
    urls = ctx.eval("JSON.stringify(__urls)")
    assert "league" not in urls, urls
    assert ctx.eval("__scripts.length") == 0
    assert _league_html(ctx) == ""


def test_opening_the_tab_injects_the_script_once(payloads):
    ctx = _ctx("#section=league", payloads, with_league=False)
    assert ctx.eval("JSON.stringify(__scripts.map(function (s) { return s.src; }))") == json.dumps([SRC])
    assert "Loading the League tab" in _league_html(ctx)
    ctx.eval(LEAGUE_JS)   # the script lands: it shows itself because the tab is still open
    assert "mlbx-lgtable" in _league_html(ctx)


def test_a_dark_shell_ignores_section_league(payloads):
    ctx = _ctx("#section=league", payloads, live=False, with_league=False)
    assert ctx.eval("__scripts.length") == 0
    assert "league" not in ctx.eval("JSON.stringify(__urls)")
    assert _league_html(ctx) == ""


# ---------------------------------------------------------------- the hash
G_HASHES = [
    "gview=time",
    "gside=pit&gseason=2025&grole=SP,RP&ghand=L&gage=age_28_30&gqual=board&glg=NL",
    "gpos=C,SS,P&ghand=S&gqual=250",
    "gview=time&gside=team&gstat=rs_g&gcmp=club_mean",
    "gview=time&gstat=k_pct&gcmp=bats_L",
]


def test_the_g_keys_round_trip_through_write_hash(payloads):
    for g in G_HASHES:
        ctx = _ctx("#section=league&" + g, payloads)
        ctx.eval("window.MLBX_LEAGUE._writeHash()")
        written = ctx.eval("__hash[__hash.length - 1]")
        assert written == "#section=league&" + g, (g, written)


def test_defaults_write_no_g_key(payloads):
    ctx = _ctx("#section=league&gview=avg&gside=hit&gstat=p_per_pa", payloads)
    ctx.eval("window.MLBX_LEAGUE._writeHash()")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=league"


def test_a_leverage_deep_link_still_opens_leverage(payloads):
    h = "#section=leverage&lview=starters&lseason=2025"
    ctx = _ctx(h, payloads)
    assert _league_html(ctx) == ""
    assert "league" not in ctx.eval("JSON.stringify(__urls)")
    assert ctx.eval("__html['mlbstats-leverage-root'] || ''")
    # the League state reads neither Leverage key
    ctx.eval("window.MLBX_LEAGUE._reset(); window.MLBX_LEAGUE.readHash(%s)" % json.dumps(h))
    st = json.loads(ctx.eval("JSON.stringify(window.MLBX_LEAGUE._state())"))
    assert st["view"] == "avg" and st["season"] is None, st
    assert ctx.eval("JSON.stringify(window.MLBX_LEAGUE.hashParts())") == "[]"


def test_the_league_keys_are_one_list_in_both_files():
    """mlbstats.js carries a deep link's g keys through before the League
    script lands; the two key lists must be the same list."""
    m = re.search(r"var LEAGUE_KEY_RE = /\(\?:\^#\|\[#&\]\)\(g\(\?:([a-z|]+)\)=", MLBSTATS_JS)
    assert m, "LEAGUE_KEY_RE changed shape"
    carried = set(m.group(1).split("|"))
    written = set(re.findall(r'p\.push\("g([a-z]+)="', LEAGUE_JS))
    read = set(re.findall(r"\[#&\]\)g([a-z]+)=", LEAGUE_JS))
    want = {"view", "side", "season", "pos", "role", "hand", "age", "qual", "lg", "stat", "cmp"}
    assert carried == written == read == want, (carried, written, read)
    # no League key collides with a key mlbstats.js already reads or writes
    taken = set(re.findall(r"\[#&\]\)([a-z]+)=", MLBSTATS_JS)) | set(re.findall(r'"([a-z]+)="', MLBSTATS_JS))
    assert not ({"g" + k for k in want} & taken), {"g" + k for k in want} & taken


# ---------------------------------------------------------------- one recipe
def _state(side, key):
    st = {"pos": [], "role": [], "hand": [], "age": "", "qual": "", "lg": ""}
    if side == "hit":
        if key == "all":
            return st
        if key == "all_incl_p":
            st["pos"] = ["P"]
        elif key.startswith("pos_"):
            st["pos"] = [key[4:]]
        elif key.startswith("bats_"):
            st["hand"] = [key[5:]]
    else:
        if key == "pitchers_only":
            return st
        if key == "all":
            st["role"] = ["POS"]
        elif key.startswith("role_"):
            st["role"] = [key[5:]]
        elif key.startswith("throws_"):
            st["hand"] = [key[7:]]
    if key.startswith("age_"):
        st["age"] = key
    elif key.startswith("sample_"):
        st["qual"] = key[7:]
    elif key.startswith("lg_"):
        st["lg"] = key[3:]
    return st


def test_browser_pooling_reproduces_every_payload_group(payloads):
    ctx = MiniRacer()
    ctx.eval("var window = {addEventListener: function () {}}; var location = {hash: ''};" + LEAGUE_JS)
    checked = 0
    problems = []
    for y, doc in payloads["panels"].items():
        ctx.eval("var DOC = %s;" % json.dumps(doc))
        for side in ("hit", "pit"):
            for key, g in doc["groups"][side].items():
                if key in ("sp_innings", "rp_innings"):
                    continue      # club role lines, not player rows
                st = _state(side, key)
                gk = ctx.eval("window.MLBX_LEAGUE._groupKey(%s, %s)" % (json.dumps(side), json.dumps(st)))
                if gk != key:
                    problems.append((y, side, key, "maps to", gk))
                r = json.loads(ctx.eval("JSON.stringify(window.MLBX_LEAGUE._pool(DOC, %s, %s))"
                                        % (json.dumps(side), json.dumps(st))))
                for f in ("n", "n_floor", "pa", "ip"):
                    if f in g:
                        checked += 1
                        if g[f] != r.get(f):
                            problems.append((y, side, key, f, g[f], r.get(f)))
                for k, v in g["league"].items():
                    if k == "sp_ip_per_gs":
                        continue
                    checked += 1
                    if v != r["league"].get(k):
                        problems.append((y, side, key, "league", k, v, r["league"].get(k)))
                for k, d in g["dist"].items():
                    for f in ("mean", "median", "sd", "n"):
                        checked += 1
                        if d.get(f) != (r["dist"].get(k) or {}).get(f):
                            problems.append((y, side, key, "dist", k, f, d.get(f), (r["dist"].get(k) or {}).get(f)))
    assert checked > 5000, checked
    assert not problems, problems[:20]


def test_python_rounding_on_exact_ties():
    ctx = MiniRacer()
    ctx.eval("var window = {addEventListener: function () {}}; var location = {hash: ''};" + LEAGUE_JS)
    for x, n in ((0.125, 2), (4.125, 2), (2.675, 2), (0.0005, 3), (1.5, 0), (2.5, 0), (-0.125, 2), (3.14159, 3)):
        assert ctx.eval("window.MLBX_LEAGUE._pyRound(%r, %d)" % (x, n)) == round(x, n), (x, n)


# ---------------------------------------------------------------- honesty
def test_no_key_or_group_names_a_grade_and_no_matchup_split_exists():
    low = LEAGUE_JS.lower()
    for bad in ("gfv", "gefv", "ggrade", "vs_lhp", "vs_rhp", "opp_hand", "data-gclub"):
        assert bad not in low, bad
    # the hand filter is the player's own side
    assert "r.bats" in LEAGUE_JS and "r.throws" in LEAGUE_JS


def test_no_forecast_word_in_the_copy():
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', LEAGUE_JS) + re.findall(r"'((?:[^'\\]|\\.)*)'", LEAGUE_JS)
    copy = " ".join(s for s in strings if " " in s).lower()
    for w in ("luck", " due ", "regress", "trending", " will ", "clutch", "sleeper", "breakout"):
        assert w not in copy, w
    assert "—" not in LEAGUE_JS and "–" not in LEAGUE_JS
