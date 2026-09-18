# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ YEAR RANGE, on the page: what a window may say, and how.

Owner decision 2026-09-17: build the multi-year index now, the lab-backed way.
So a window is two different things depending on the column, and the whole point
of this module is that the page can never confuse them:

  * a COUNT sums and a RATE pools, over any span, which the Overall board does
    in the browser by folding data/war_seasons.json;
  * a "+" INDEX is a lab pass. 100 on one is the average of ONE season's pool,
    so tools/mlbstats_window_lab.py precomputes a FIXED set of windows by the
    recipe the shipped 3-year columns already use, and an index appears ONLY on
    a window that lab actually computed. On any other window the board says so
    in one line instead of printing a number on a scale nobody computed.

What is pinned here, in the order the spec numbers it:

  T1        no index reaches a pool it was not computed against, and a window
            index never routes through a value-ruler helper;
  T10/T11   every old *season= deep link still resolves, the new *years= key is
            validated rather than trusted, and #hseason=2019 - which rendered an
            EMPTY board before this change - opens Current;
  T12       one key can never be matched by another (the anchor);
  T13       the note names exactly the columns this board dropped, built from
            the board's own column array rather than typed;
  T14       the 2020 and in-progress sentences are read off season_share, and no
            percentage for either is a literal anywhere in the JS;
  T15       the window rides the export header and the shareable card, so a
            range number cannot leave the page under a single-season heading;
  T-FROZEN  a window never renders a frozen *_3yr column beside a summed one;
  T-CLUB    the club basis is stated whenever it is the club of production;
  T-EXP     the per-season lines under a row sum to the total printed above it;
  T-QUAL    the window's qualified rule is published on the payload and
            reported, never typed into the page.

The fixtures are small and synthetic on purpose: the shapes are the served
ones (data/mlbstats_windows.json, data/mlbstats_window_l3.json and
data/war_seasons.json), and a test that needed the 2 MB artifacts would skip on
every machine that has not run the lab.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import test_mlbstats_smoke as smoke
import test_mlbstats_views as views

MiniRacer = smoke.MiniRacer
ROOT = Path(__file__).parent
JS = views.JS

# ---------------------------------------------------------------- fixtures
# data/mlbstats_windows.json: the manifest. One window, so a test can ask for a
# span the lab did NOT build and get the refusal.
WINDOWS = {
    "generated_at": "2026-09-17", "schema": 1, "live_season": 2026,
    "war_provider": "ewar_v2", "ewar_generated_at": "2026-09-03T12:35:09",
    "excluded_seasons": [2020],
    "qualified_rule_window": {
        "overall": {"min_pa": 100, "min_ip": 30,
                    "rule": "PA >= 100 or IP >= 30 over the whole window"},
        "hitters": {"min_pa": 200, "rule": "PA >= 200 over the whole window"},
    },
    "columns": {
        "hitters": {
            "sum": ["pa", "hr", "sb", "war"],
            "pool": {"avg": {"denom": "ab", "formula": "H / AB"},
                     "obp": {"denom": "obp", "formula": "(H + BB + HBP) / (AB + BB + HBP + SF)"}},
            "recomposed": {"ops": "pooled OBP + pooled SLG"},
            "index": {"hem_plus": "PA-weighted mean of the per-season HEM+"},
            "hidden": {"wrc_plus": "wRC+ is MLB's published season index.",
                       "hem_plus_3yr": "A frozen lab artifact with a window of its own.",
                       "war_pa_plus_3yr": "The same frozen window.",
                       "woba": "The shrink target is that season's pool.",
                       "xhem_plus": "Anchored to one season's pool."},
        },
    },
    "windows": [{"key": "l3", "name": "Last 3", "label": "2024-2026", "years": 3,
                 "seasons": [2024, 2025, 2026], "file": "mlbstats_window_l3.json",
                 "n_rows": {"hitters": 2},
                 "pool_stats": {"hitters": {"hem_plus": {"n": 2, "mean": 96.06, "sd": 13.93}}}}],
    "season_share": {"2020": 0.3703, "2026": 0.9404},
}
WINDOW_L3 = {
    "generated_at": "2026-09-17", "schema": 1, "war_provider": "ewar_v2",
    "excluded_seasons": [2020], "live_season": 2026,
    "name": "Last 3", "window": {"key": "l3", "label": "2024-2026", "years": 3,
                                 "seasons": [2024, 2025, 2026]},
    "columns": WINDOWS["columns"], "qualified_rule_window": WINDOWS["qualified_rule_window"],
    "season_share": {"2020": 0.3703, "2026": 0.9404},
    "pool_stats": {"hitters": {"hem_plus": {"n": 2, "mean": 96.06, "sd": 13.93}}},
    "n_rows": {"hitters": 2},
    "boards": {"hitters": {"hitters": [
        {"mlbam": 592450, "name": "Window Judge", "team": "NYY", "yrs": 3,
         "clubs": ["NYY"], "last_season": 2026, "pa": 1668, "hr": 129, "sb": 27,
         "avg": 0.311, "obp": 0.441, "ops": 1.103, "war": 22.4, "war_n": 3,
         "qualified": True, "denoms": {"pa": 1668, "ab": 1337, "obp": 1665},
         "hem_plus": 180, "hem_plus_pct": 100, "hem_plus_tag": "established",
         "hem_plus_n": 3, "hem_plus_denom": 1668.0},
        {"mlbam": 777, "name": "Thin Window", "team": "BOS", "yrs": 1,
         "clubs": ["SD", "BOS"], "last_season": 2026, "pa": 240, "hr": 9, "sb": 1,
         "avg": 0.244, "obp": 0.301, "ops": 0.671, "war": 0.6, "war_n": 1,
         "qualified": True, "denoms": {"pa": 240, "ab": 220, "obp": 238},
         "hem_plus": 118, "hem_plus_pct": 61, "hem_plus_tag": "provisional",
         "hem_plus_n": 1, "hem_plus_denom": 240.0},
    ]}},
}
# data/war_seasons.json: positional rows by `fields`, clubs and positions in
# dictionaries, absent denominators null rather than zero.
WAR_SEASONS = {
    "generated_at": "2026-09-17", "schema": 1, "war_provider": "ewar_v2",
    "seasons": [2019, 2020, 2024, 2025, 2026],
    "fields": ["season", "war_bat", "war_pit", "pa", "ip", "age", "pos", "g", "gs", "tm"],
    "tm": ["LAA/LAD", "NYY"], "pos": ["TWP", "RF"],
    "season_share": {"2019": 0.9985, "2020": 0.3703, "2024": 0.9995, "2025": 1.0, "2026": 0.9404},
    "qualified_rule_window": {"min_pa": 100, "min_ip": 30},
    "players": {
        "660271": ["Two Way", [
            [2024, 6.58, 1.78, 727, 47.0, 30, 0, 158, 14, 0],
            [2025, 3.37, 2.75, 596, 85.7, 31, 0, 134, 14, 0],
            [2026, 1.04, 0.31, 210, 20.3, 32, 0, 64, 4, 0]]],
        "592450": ["Bat Only", [
            [2019, 4.20, None, 600, None, 27, 1, 140, None, 1],
            [2024, 9.65, None, 679, None, 32, 1, 152, None, 1],
            [2025, 1.89, None, 285, None, 33, 1, 66, None, 1],
            [2026, 2.51, None, 401, None, 34, 1, 96, None, 1]]],
        "999": ["", [[2020, 0.42, None, 180, None, 28, 1, 52, None, 1]]],
    },
}


# A sentinel: this artifact is NOT served, which is what a machine where the
# lab has never run looks like (a 404 on the window files).
ABSENT = object()


def _routes_js(windows=None, l3=None, seasons=None) -> str:
    """Answer the three window artifacts by URL, and 404 the ones this case
    withholds. Its own promise shim, so it composes with any section prelude."""
    doc = {"mlbstats_windows.json": WINDOWS if windows is None else windows,
           "mlbstats_window_l3.json": WINDOW_L3 if l3 is None else l3,
           "war_seasons.json": WAR_SEASONS if seasons is None else seasons}
    routes = json.dumps({k: json.dumps(v) for k, v in doc.items() if v is not ABSENT})
    return """
    var ROUTES=%s;
    function WP(val){return {then:function(cb){var r;
      try { r=cb(val); } catch (e) { return {then:function(){return this;},
                                             catch:function(c){c(e);return this;}}; }
      return (r&&r.then)?r:WP(r);},catch:function(){return WP(val);}};}
    var __prevFetch=fetch;
    fetch=function(url){
      var u=String(url);
      for (var k in ROUTES) {
        if (u.indexOf(k)>=0) {
          var body=ROUTES[k];
          return WP({ok:true,status:200,json:function(){return WP(JSON.parse(body));}});
        }
      }
      if (u.indexOf('mlbstats_window')>=0 || u.indexOf('war_seasons')>=0) {
        return WP({ok:false,status:404,json:function(){return WP(null);}});
      }
      return __prevFetch(url);
    };
    """ % routes


# The page's range control, its Established gate and its expander all ride ONE
# delegated listener each, the pattern the phone drawer and the team Clear
# already use, so the harness has to be able to reach a document listener. It
# records them and fires a synthetic event whose target answers closest() for
# exactly one attribute, which is all those handlers ask of it.
_DOC_STUB = r"""
var __doc = {}, __hashes = [];
history.replaceState = function (a, b, u) { __hashes.push(String(u)); };
document.addEventListener = function (ev, fn) { (__doc[ev] = __doc[ev] || []).push(fn); };
function __fire(ev, attr, value, val2) {
  var el = {
    getAttribute: function (a) { return a === attr ? value : null; },
    value: val2 == null ? "" : String(val2),
    classList: {contains: function () { return false; }},
    closest: function (sel) { return sel === "[" + attr + "]" ? el : null; }
  };
  el.target = el;
  (__doc[ev] || []).forEach(function (fn) { fn({target: el}); });
}
"""


def _prelude(hash_: str, windows=None, l3=None, seasons=None, war=None) -> str:
    return (views._war_prelude(hash_, war) + _routes_js(windows, l3, seasons) + _DOC_STUB)


def _render(hash_: str, root: str = "mlbstats-war-root", **kw) -> str:
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, **kw) + JS)
    return ctx.eval("__html['%s'] || ''" % root)


def _ctx(hash_: str, **kw):
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, **kw) + JS)
    return ctx


def _war_html(ctx) -> str:
    return ctx.eval("__html['mlbstats-war-root'] || ''")


def _hitters(hash_: str, **kw) -> str:
    """The hitter board's own prelude with the window artifacts routed in."""
    ctx = MiniRacer()
    ctx.eval(smoke._hitter_prelude(hash_) + _routes_js(**kw) + _DOC_STUB + JS)
    return ctx.eval("__html['mlbstats-hitters-root'] || ''")


def _heads(html: str) -> list[tuple[str, str, str]]:
    return views._heads(html)


def _visible(html: str) -> list[str]:
    return views._visible(html)


def _cells(html: str, key: str) -> list[str]:
    """One column's rendered values, in row order. The expander's child row is
    not a player row and is skipped here, which is also what the CSV scraper
    does with it (data-export-skip on the row)."""
    i = [k for _, k, _ in _heads(html)].index(key)
    body = views._table(html).split("<tbody>")[1]
    out = []
    for row in re.findall(r"<tr([^>]*)>(.*?)</tr>", body, re.S):
        if "mlbx-seasonrow" in row[0]:
            continue
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row[1], re.S)
        assert len(tds) > i, (key, len(tds))
        out.append(tds[i])
    return out


# ---------------------------------------------------------------- T1 / T-FROZEN
INDEX_HELPERS = ("remCell", "runCell", "hemCell", "wrcCell", "vtCell")


def test_a_window_index_never_routes_through_a_value_ruler_helper():
    """THE HEADLINE TEST. A window pool is a different pool, measured on the two
    artifacts the page itself reads: on the served 2026 hitter board
    (data/hitter_leaderboards.json, 658 rows) HEM+ averages 95.49 with a standard
    deviation of 13.76 and the ruler's elite cut of 120 takes 6.1% of it; on the
    served Last 5 window (data/mlbstats_window_l5.json, 746 rows, the pool_stats
    block the column tooltip prints) it averages 95.41 with a standard deviation
    of 13.15 and 120 takes 4.2%. Same numeral, same word, a third fewer players.
    So the window cell carries the numeral and no band, and the ONE function that
    builds it is read here the way test_value_ruler reads the eWAR columns."""
    i = JS.index("function windowIndexCol(")
    body = JS[i:JS.index("\n  function ", i + 10)]
    for helper in INDEX_HELPERS:
        assert helper + "(" not in body, (helper, body)
    assert "EephusTiers" not in body
    # NOT .rem-plus: that class is cursor:help and there is no per-cell tooltip
    # behind it, so it would be an affordance with nothing under it.
    assert 'class="mlbstats-winidx"' in body
    assert 'class="rem-plus' not in body, body
    # and the class it does carry paints no band
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    rule = re.search(r"\.mlbx .mlbstats-table .mlbstats-winidx \{([^}]*)\}", css).group(1)
    assert "var(--text-primary)" in rule and "vt-" not in rule


def test_an_index_renders_only_on_a_window_the_lab_computed():
    """2024-2026 is the lab's window, so HEM+ is on the board with its span in
    the header. 2021-2024 is not, so there is no board at all: a refusal that
    names the span, offers the windows that exist, and points at the Overall
    board, whose every column is a count."""
    on = _hitters("#section=hitters&hyears=2024-2026")
    assert "hem_plus" in _visible(on), _visible(on)
    assert "2024-2026" in {k: t for _, k, t in _heads(on)}["hem_plus"]
    off = _hitters("#section=hitters&hyears=2021-2024")
    assert "mlbstats-table" not in off, "a board rendered on a window the lab never built"
    assert "2021-2024 is not a window this board can build" in off
    assert 'data-mlbgoto="war:2021-2024"' in off, "the refusal does not offer the span on the count board"
    assert 'data-mlbrange="hitters:l3"' in off, "the refusal does not offer the window that exists"


def test_a_window_never_renders_a_frozen_lab_column(board="hitters"):
    """T-FROZEN. A *_3yr column is a frozen artifact with a window of ITS own; a
    2024-2026 board beside a "3yr" column would be two windows in one row."""
    html = _hitters("#section=hitters&hyears=2024-2026")
    keys = [k for _, k, _ in _heads(html)]
    assert not [k for k in keys if k.endswith("_3yr")], keys
    assert "gmli_3yr" not in keys and "wrc_plus" not in keys


def _note(html: str) -> str:
    """The window note, summary and body. It is a <details>, so the body is in
    the DOM whether it is open or not and a text assertion reads the whole of
    it."""
    note = html[html.index("mlbstats-winnote"):]
    return note[:note.index("</details>")]


def _labels(html: str) -> dict:
    """key -> the label the header prints, read off data-export-text, which is
    the same escaped string the note's dropped list is built from."""
    out = {}
    for _, key, tag in _heads(html):
        m = re.search(r'data-export-text="([^"]*)"', tag)
        out[key] = m.group(1) if m else key
    return out


def test_the_note_names_exactly_what_this_board_dropped():
    """T13. The dropped list is the board's OWN column array minus the keys this
    window's payload can fill, so a column added to either side is named by this
    sentence without anyone editing it, and the reason is the artifact's where it
    has one."""
    html = _hitters("#section=hitters&hyears=2024-2026")
    note = _note(html)
    assert "Off on this window:" in note
    for label in ("wRC+", "HEM+ 3yr", "WAR/PA+ 3yr", "Shrunk wOBA", "xHEM+"):
        assert label in note, (label, note)
    # and the reason rides the column it belongs to, not the sentence
    assert "wRC+ is MLB&#x27;s published season index." in note or \
           "wRC+ is MLB's published season index." in note


def test_every_column_the_window_drops_is_named_by_the_note():
    """The half the spot-check could not see: a column the LAB CLASSIFIES
    NOWHERE (not sum, pool, recomposed, index or hidden) used to vanish in
    silence under a sentence that claimed to name everything that went. Measured
    on the served artifacts when this landed, six did: Bullpen lost Luck (wOBA),
    WAR/IP+ adj and WPA/LI, Starters WAR/IP+ adj, Hitters WAR/PA+ adj and the
    starters view of Leverage GS. So the assertion is COVERAGE: every key the
    Current board carries is either on the window board or named in the note."""
    cur = _labels(_hitters("#section=hitters&hcols=all"))
    win = _hitters("#section=hitters&hyears=2024-2026&hcols=all")
    on = {k for _, k, _ in _heads(win)}
    note = _note(win)
    silent = [(k, lbl) for k, lbl in cur.items() if k not in on and lbl not in note]
    assert not silent, silent
    # exactly, in both directions: the sentence lists every column that went and
    # nothing that stayed.
    dropped = set(re.findall(r'">([^<]+)</span>', note.split("Off on this window:")[1]))
    win_labels = _labels(win)
    assert dropped == {lbl for k, lbl in cur.items() if k not in on}, dropped
    assert not (dropped & {win_labels[k] for k in on}), dropped


# ---------------------------------------------------------------- T10 / T11 / T12
def _hash_after(ctx) -> str:
    """The last URL writeHash left behind. A board that has not been touched
    writes nothing at all, which is the point of the bare-URL case: the page
    does not grow a suffix on its own."""
    n = ctx.eval("__hashes.length")
    return ctx.eval("__hashes[__hashes.length - 1]") if n else ""


def test_every_old_season_deep_link_still_resolves():
    """T10. #wseason=2019 is a window of one season and renders the 2019 board;
    the URL it writes back is byte-identical to the one that was pasted."""
    ctx = _ctx("#section=war&wseason=2019")
    html = _war_html(ctx)
    assert "mlbstats-table" in html
    assert "2019, 1 season." in html
    assert "Bat Only" in html and "Two Way" not in html      # only 2019 has a line
    # The board has not been touched, so nothing was rewritten: the URL that was
    # pasted is the URL that is there.
    assert _hash_after(ctx) == ""
    ctx.eval("__fire('click', 'data-mlbrange', 'war:l3');")
    assert _hash_after(ctx) == "#section=war&wyears=2024-2026", _hash_after(ctx)
    ctx.eval("__fire('change', 'data-mlbrangesel', 'war:lo', '2019');")
    ctx.eval("__fire('change', 'data-mlbrangesel', 'war:hi', '2019');")
    assert _hash_after(ctx) == "#section=war&wseason=2019", _hash_after(ctx)


def test_a_window_writes_its_own_key_and_current_writes_neither():
    ctx = _ctx("#section=war")
    assert _hash_after(ctx) == "", "a bare URL grew a suffix on its own"
    ctx.eval("__fire('click', 'data-mlbrange', 'war:l3');")
    assert _hash_after(ctx) == "#section=war&wyears=2024-2026"
    ctx.eval("__fire('click', 'data-mlbrange', 'war:current');")
    last = _hash_after(ctx)
    assert last == "#section=war", last
    assert "wyears" not in last and "wseason" not in last
    # An inverted pick pushes the other end with it, so the board can never be
    # asked for a span that runs backwards.
    ctx.eval("__fire('change', 'data-mlbrangesel', 'war:lo', '2024');")
    ctx.eval("__fire('change', 'data-mlbrangesel', 'war:hi', '2019');")
    assert _hash_after(ctx) == "#section=war&wseason=2019", _hash_after(ctx)


def test_a_range_key_is_validated_not_trusted():
    """T11, and the LIVE BUG it closes: #hseason=2019 passed the regex, resolved
    to nothing and rendered an empty board. Now the board opens Current and says
    which key it refused."""
    for bad in ("#section=war&wyears=1999-2026", "#section=war&wyears=2025-2024",
                "#section=war&wyears=abcd-2026", "#section=war&wseason=2017"):
        html = _render(bad)
        assert "mlbstats-table" in html, bad
        assert "2026" in html, bad
        assert ", 3 seasons." not in html, bad
    refused = _render("#section=war&wseason=2017")
    assert "2017 is not a season this board publishes" in refused
    assert "opened on Current" in refused


def test_a_years_key_cannot_be_matched_by_another_key():
    """T12. The anchor is the reason sview= cannot match view=; the same one is
    on every window key, and a season key can never swallow a span (readSeason's
    \\b matches between 2023 and the hyphen, which is why the window is a
    SEPARATE key and not a widened one)."""
    i = JS.index("function readRange(")
    body = JS[i:JS.index("\n  function ", i + 10)]
    assert '"(?:^#|[#&])" + key + "=(\\\\d{4})-(\\\\d{4})\\\\b"' in body, body
    # a span in the OLD key is read as one season by old JS, so the page must
    # never write one there
    j = JS.index("function pushWindow(")
    push = JS[j:JS.index("\n  function ", j + 10)]
    assert "if (w.lo === w.hi) parts.push(seasonKey" in push
    assert "else parts.push(yearsKey" in push
    for a, b in (("wyears", "ryears"), ("hyears", "wyears"), ("rseason", "ryears")):
        assert a != b
    html = _render("#section=war&xwyears=2024-2026")
    assert ", 3 seasons." not in html, "a key with a prefix matched the window key"


# ---------------------------------------------------------------- T14
def test_the_short_season_disclosure_is_read_from_the_payload():
    """T14. 2020 and the season being played both come off season_share, and
    NEITHER percentage is a literal in the JS: a payload that ships a different
    share says so by itself."""
    html = _render("#section=war&wyears=2019-2026")
    assert "2020 is inside this window and produced 37% of a normal season." in html
    assert "2026 is still being played and has produced 94% of a normal season so far." in html
    clean = _render("#section=war&wyears=2024-2025")
    assert "normal season" not in clean, "a complete window raised the short-season note"
    for literal in ("37%", "94%", "37 %", "94 %"):
        assert literal not in JS, literal


def test_a_payload_without_season_share_says_nothing_rather_than_guessing():
    seasons = json.loads(json.dumps(WAR_SEASONS))
    seasons.pop("season_share")
    html = _render("#section=war&wyears=2019-2026", seasons=seasons)
    assert "mlbstats-table" in html
    assert "normal season" not in html


# ---------------------------------------------------------------- T15
def test_the_window_rides_the_export_header_and_the_card():
    """T15. The visible header keeps the metric's name; the EXPORT header, which
    is what the CSV writes, carries the span, so a range number cannot leave the
    page under a single-season heading. The shareable card says it in the
    subtitle."""
    html = _render("#section=war&wyears=2024-2026")
    heads = {k: t for _, k, t in _heads(html)}
    assert 'data-export-text="eWAR 2024-2026"' in heads["war"], heads["war"]
    assert 'data-export-text="Player"' in heads["name"], "the name column is not a window number"
    i = JS.index("function seasonBits(")
    body = JS[i:JS.index("\n    function spec(", i)]
    assert "seasonSel.hi - seasonSel.lo + 1" in body, body
    assert '" seasons"' in body


# ---------------------------------------------------------------- T-CLUB
def test_the_club_basis_is_stated_whenever_it_changes():
    """T-CLUB. On Current the club is the roster today and the served team_basis
    block says so. On a window it is the club of production, and the note says
    THAT, with every club the player produced for in the name tooltip."""
    win = _render("#section=war&wyears=2024-2026")
    assert "Club is every club of production inside the window" in win
    assert "the club filter and the search box match any of them" in win
    assert "Clubs of production: LAA, LAD" in win, "the +N tooltip does not name the clubs"
    assert "club (produced for)" in win, "the select kept its roster-today label on a window"
    cur = _render("#section=war")
    assert "club of production" not in cur
    assert ">team <select" in cur, "the Current select stopped saying which basis it is on"
    assert "Team column:" in cur, "the served club basis stopped being stated on Current"


def test_the_window_club_filter_is_every_club_of_production():
    """OWNER DECISION D9, and the defect it closes: the filter matched the LAST
    club only, so 2024-2026 filtered by LAA lost a player who produced for LAA in
    2024 and is filed under LAD. The select offers the window's clubs, the filter
    matches any of them, and so does the search box."""
    html = _render("#section=war&wyears=2024-2026&team=LAA")
    names = [re.sub(r"<[^>]+>", "", c) for c in _cells(html, "name")]
    assert any("Two Way" in n for n in names), names      # LAA/LAD, filed under LAD
    opts = _render("#section=war&wyears=2024-2026")
    assert '<option value="LAA"' in opts and '<option value="LAD"' in opts, "the select"
    # the club the row is NOT on still filters it out
    empty = _render("#section=war&wyears=2024-2026&team=BOS")
    assert "mlbstats-table" not in empty or "Two Way" not in empty


def test_a_row_the_substrate_does_not_name_is_still_addressable():
    """A fold row with no name prints the player's MLBAM id rather than a null
    marker, and the search box matches that id: a ranked board whose rows cannot
    be pointed at is a board a reader cannot use."""
    html = _render("#section=war&wyears=2019-2026")
    assert "#999" in html, html[:400]
    hit = _render("#section=war&wyears=2019-2026&q=999")
    assert "#999" in hit


# ---------------------------------------------------------------- T-EXP
def test_the_expanded_seasons_sum_to_the_printed_total():
    """T-EXP. The child rows are rendered from the SAME fold as the total, so
    the explanation cannot disagree with the number above it. The two sides sum
    unrounded and round once, which is the board's own rule over one season, so
    the printed lines need not add to the total - and the cell ADDS THEM UP for
    that row rather than claiming a bound. Measured on the served substrate, the
    bound the copy used to claim is false on a long window: 0 of 2072 rows are
    over a tenth on 2024-2026, 19 of 2630 reach 0.2 on 2022-2026 and 160 of 5149
    reach 0.4 on 2011-2026."""
    ctx = _ctx("#section=war&wyears=2024-2026")
    assert "mlbx-caret" in _war_html(ctx), "no expander on the window board"
    ctx.eval("__fire('click', 'data-mlbexpand', '660271');")
    html = _war_html(ctx)
    assert "mlbx-seasonrow" in html
    row = html[html.index("mlbx-seasonrow"):]
    row = row[:row.index("</tr>")]
    seasons = re.findall(r"<b>(20\d\d)</b>.*?<b>(-?\d+\.\d)</b>", row)
    assert [s for s, _ in seasons] == ["2026", "2025", "2024"], seasons
    total = float(re.search(r"<b>Total</b> <b>(-?\d+\.\d)</b>", row).group(1))
    assert abs(sum(float(v) for _, v in seasons) - total) <= 0.1, (seasons, total)
    printed = float(re.sub(r"<[^>]+>", "", _cells(html, "war")[0]))
    assert printed == total, (printed, total)
    assert "the lines need not add to it exactly" in row, row
    said = float(re.search(r"These lines add to (-?\d+\.\d)", row).group(1))
    assert abs(said - sum(float(v) for _, v in seasons)) < 0.051, (said, seasons)


def test_the_expander_is_not_a_page_state():
    """An expanded row is a glance: it takes no hash key, so a copied URL does
    not carry one reader's open rows to another."""
    ctx = _ctx("#section=war&wyears=2024-2026")
    before = ctx.eval("__hashes.length")
    ctx.eval("__fire('click', 'data-mlbexpand', '660271');")
    assert "mlbx-seasonrow" in _war_html(ctx)
    assert ctx.eval("__hashes.length") == before, "the expander wrote a hash key"


# ---------------------------------------------------------------- T-QUAL
def test_the_window_qualified_rule_is_published_not_typed():
    """T-QUAL. Both floors are read off the payload - the substrate's for the
    Overall fold, the lab's per-board rule for the five role boards - so a
    payload that ships a different floor says so by itself."""
    html = _render("#section=war&wyears=2024-2026")
    assert "Qualified: 100 plate appearances or 30 innings over the whole window." in html
    seasons = json.loads(json.dumps(WAR_SEASONS))
    seasons["qualified_rule_window"] = {"min_pa": 250, "min_ip": 60}
    moved = _render("#section=war&wyears=2024-2026", seasons=seasons)
    assert "Qualified: 250 plate appearances or 60 innings" in moved
    hit = _hitters("#section=hitters&hyears=2024-2026")
    assert "Qualified: PA &gt;= 200 over the whole window." in hit or \
           "Qualified: PA >= 200 over the whole window." in hit
    for typed in ('"100 plate appearances"', "min_pa: 100", "PA >= 200"):
        assert typed not in JS, typed


# ---------------------------------------------------------------- the fold
def test_the_fold_sums_the_sides_unrounded_and_rounds_once():
    """The board's own rule over one season, applied to a window. Two Way's
    three seasons carry 6.58 + 3.37 + 1.04 of batting and 1.78 + 2.75 + 0.31 of
    pitching: 15.83, which prints 15.8. Summing the SERVED tenths would print
    15.9, one rounding error per season."""
    html = _render("#section=war&wyears=2024-2026")
    war = [re.sub(r"<[^>]+>", "", c) for c in _cells(html, "war")]
    assert war[0] == "15.8", war
    bat = [re.sub(r"<[^>]+>", "", c) for c in _cells(html, "war_bat")]
    assert bat[0] == "11.0", bat                      # 6.58 + 3.37 + 1.04 = 10.99


def test_an_absent_denominator_is_blank_and_never_zero():
    """A hitter who never pitched serves a blank IP, not 0.0: an absent season is
    unobserved, not a performance of zero. The same rule arb_metrics.trailing
    states in its own docstring."""
    html = _render("#section=war&wyears=2024-2026")
    ip = [re.sub(r"<[^>]+>", "", c).strip() for c in _cells(html, "ip")]
    assert ip[0] == "153.0", ip                        # the two-way player pitched
    assert ip[1] == "-", ip                            # the bat-only player did not
    pit = [re.sub(r"<[^>]+>", "", c).strip() for c in _cells(html, "war_pit")]
    assert pit[1] == "-", pit
    assert "0.0" not in (ip[1], pit[1])


def test_each_side_divides_by_its_own_denominator():
    """Bat/600 is over PA and Pitch/200 is over IP. A single eWAR/600 on the
    total would charge a two-way player's pitching to his plate appearances."""
    html = _render("#section=war&wyears=2024-2026&wcols=rate")
    vis = _visible(html)
    assert "bat_600" in vis and "pitch_200" in vis, vis
    bat = float(re.sub(r"<[^>]+>", "", _cells(html, "bat_600")[0]))
    pitch = float(re.sub(r"<[^>]+>", "", _cells(html, "pitch_200")[0]))
    assert abs(bat - 10.99 / 1533 * 600) < 0.05, bat
    assert abs(pitch - 4.84 / 153.0 * 200) < 0.05, pitch


def test_the_window_universe_is_every_season_not_the_qualified_ones():
    """T-UNIVERSE, the page half: the fold reads every player-season in the
    substrate and the qualified rule filters the RENDERED rows, so a season a
    player did not qualify in is still inside his window's denominator."""
    html = _render("#section=war&wyears=2024-2026")
    pa = [int(re.sub(r"<[^>]+>", "", c)) for c in _cells(html, "pa")]
    assert pa[0] == 727 + 596 + 210, pa            # the 210-PA season is in it


def test_a_row_with_no_name_is_disclosed_rather_than_hidden():
    """The substrate names the players on the CURRENT board and leaves the rest
    blank, so a window reaching past today's rosters loses names the fold still
    has numbers for. The count is stated on the board; the rows are not dropped,
    because dropping them would change the leaderboard."""
    html = _render("#section=war&wyears=2019-2026")
    assert re.search(r"<b>1 of \d+ rows carry no name:</b>", html), html[:400]
    assert "the names return by themselves when the exporter fills the field" in html
    assert "print the player&#x27;s MLBAM id instead, which the search box matches" in html or \
           "print the player's MLBAM id instead, which the search box matches" in html


# ---------------------------------------------------------------- the control
def test_the_control_offers_the_windows_the_lab_built_and_a_from_to():
    html = _render("#section=war")
    assert 'data-mlbrange="war:current"' in html
    assert 'data-mlbrange="war:l3"' in html
    assert 'data-mlbrange="war:all"' in html
    assert 'data-mlbrangesel="war:lo"' in html and 'data-mlbrangesel="war:hi"' in html
    for year in WAR_SEASONS["seasons"]:
        assert '<option value="%d"' % year in html
    assert 'data-mlbseason=' not in html, "the season pills came back beside the picker"


def test_a_board_with_no_window_artifact_still_serves_its_season():
    """The lab has never run on this machine (a 404 on every window file). The
    presets are simply not offered, the season boards are untouched, and nothing
    on the page claims a window it cannot build."""
    bare = _render("#section=war", windows=ABSENT, l3=ABSENT)
    assert "mlbstats-table" in bare
    assert 'data-mlbrange="war:l3"' not in bare
    assert 'data-mlbrange="war:current"' in bare


def test_established_only_is_on_by_default_on_an_index_window():
    """Measured on the served Last 3 hitter board: 233 of 587 rows (40%) are
    provisional, and they reach the top 25, which is what a denominator-weighted
    mean of per-season values does with a partial window. So the gate defaults
    ON, and it is a named control rather than a silent filter."""
    html = _hitters("#section=hitters&hyears=2024-2026")
    assert 'data-mlbest="hitters"' in html and 'aria-pressed="true"' in html
    names = [re.sub(r"<[^>]+>", "", c) for c in _cells(html, "name")]
    assert any("Window Judge" in n for n in names), names
    assert not any("Thin Window" in n for n in names), names
