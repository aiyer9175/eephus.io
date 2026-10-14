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


def _prelude(hash_: str, live: bool, panels: dict, series: dict | None, live_season: int,
             teams: dict | None = None) -> str:
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
    var __PANELS = %s, __SERIES = %s, __TEAMS = %s;
    var fetch = function (u) {
      __urls.push(String(u));
      var m = /mlb_league_panel_(\\d{4})/.exec(u);
      if (m) return OK({ok: !!__PANELS[m[1]], json: function () { return OK(__PANELS[m[1]] || null); }});
      if (/mlb_league_series/.test(u)) return OK({ok: !!__SERIES, json: function () { return OK(__SERIES); }});
      if (/mlb_team_stats/.test(u)) return OK({ok: !!__TEAMS, json: function () { return OK(__TEAMS); }});
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
           json.dumps(series), json.dumps(teams), hash_)


def _ctx(hash_: str, payloads: dict | None, live: bool = True, with_league: bool = True,
         teams: dict | None = None):
    p = payloads or {"panels": {}, "series": None, "live": 2026}
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, live, p["panels"], p["series"], p["live"], teams))
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


# =============================================================================
# The Teams tab (Q8_13b: owner asks 15 and 20 of 2026-09-30, final-pass plan
# Part 8 P8.2, task LT-08, the Teams half). The same script as League, its own
# host and its own t keys. A synthetic thirty-club payload in the shape
# team_stats_export.py writes drives every test, so nothing here needs a cache;
# one smoke test reads the exporter's real served payload when it exists.
# =============================================================================
CLUBS = ["ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL", "DET", "HOU", "KCR", "LAA",
         "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX",
         "TOR", "WSN"]
TEAMS_SERVED = ROOT / "data" / "mlb_team_stats.json"
HIST_COLS = ["club", "g", "w", "l", "rs", "ra", "xw", "xl", "p_per_pa", "p_per_ip", "sp_p_per_ip", "rp_p_per_ip",
             "sp_ip_per_gs", "relief_ip_share", "lineup_par", "rotation_par", "bullpen_par", "offense_plus",
             "rotation_plus", "bullpen_plus", "team_dem_plus"]


def _team_doc() -> dict:
    """Thirty clubs with distinct wins, run differentials and rollups, the
    payload's keys and nothing more (no division-title field exists in it)."""
    teams, hist = [], []
    for i, c in enumerate(CLUBS):
        w = 60 + i
        rs, ra = 650 + 3 * i, 760 - 2 * i
        xw = 61 + (i * 7) % 30
        teams.append({
            "club": c, "code": c, "team_id": 100 + i, "lg": "AL" if i % 2 else "NL", "g": 162,
            "w": w, "l": 162 - w, "rs": rs, "ra": ra, "rd": rs - ra, "xw": xw, "xl": 162 - xw,
            "w_minus_xw": w - xw, "one_run": [20 + i % 7, 22 - i % 5], "extra_inning": [5 + i % 3, 6 - i % 4],
            "roster": {"offense_plus": 90 + i, "offense_plus_raw": 90.4 + i, "heart_hem": 110 + i,
                       "rotation_plus": 85 + i, "rotation_plus_raw": 85.2 + i, "front_sem": 100 + i,
                       "bullpen_plus": 120 - i, "bullpen_plus_raw": 119.6 - i, "leverage_deploy_plus": 95 + i,
                       "leverage_deploy_cov": 1.0, "high_lev_core_rem": 100 + i % 9,
                       "team_dem_plus": 95 + i % 11, "team_dem_plus_raw": 95.3 + i % 11, "war": 20.0 + i / 2,
                       "lineup_p_pa": None, "lineup_par": None, "rot_p_ip": None, "rot_par": None,
                       "pen_p_ip": None, "pen_par": None},
            "earned": {"offense_plus": 91 + i, "offense_plus_raw": 91.3 + i, "rotation_plus": 86 + i,
                       "rotation_plus_raw": 86.1 + i, "bullpen_plus": 119 - i, "bullpen_plus_raw": 118.8 - i,
                       "team_dem_plus": 96 + i % 11, "team_dem_plus_raw": 96.2 + i % 11, "war": 21.0 + i / 2},
            "pitches": {"p_per_pa": 3.8 + i / 200, "lineup_par": 97 + i % 7, "p_per_ip": 16.0 + i / 50,
                        "sp_p_per_ip": 16.1 + i / 40, "rotation_par": 95 + i % 9, "sp_ip_per_gs": 5.0 + i / 60,
                        "rp_p_per_ip": 16.5 - i / 40, "bullpen_par": 96 + i % 8, "relief_ip_share": 0.40 + i / 1000},
            "depth": {"heart_hem": 110 + i, "rest_hem": 92.0 + i / 3, "gap": 18.0 - i / 3,
                      "pa_share_hem_100": 0.45 + i / 200, "n_rest": 20},
            "tendencies": {"style": {"games": 162, "partial": False, "hook_median_pitches": 85.0 + i % 9,
                                     "z_hook": -1.5 + i / 10, "z_pen": 1.2 - i / 12, "z_bench": 0.3 - i / 15,
                                     "z_ibb": -0.4 + i / 20, "z_visit": 0.9 - i / 16, "pen_per_game": 3.1 + i / 100},
                           "running": {"attempts": 40 + i, "success_rate": 0.70 + i / 300, "share_2B": 0.9,
                                       "share_3B": 0.1 - i / 1000, "mean_breakeven_faced": 0.74}},
        })
        hist.append([c, 162, w + 1, 161 - w, rs - 5, ra + 5, xw, 162 - xw, 3.85, 16.4, 16.3, 16.6, 5.2, 0.41,
                     100, 100, 100, 92 + i, 87 + i, 118 - i, 97 + i % 11])
    means = {"offense_plus_pa_weighted": 99.87, "rotation_plus_ip_weighted": 102.1,
             "bullpen_plus_ip_weighted": 101.54, "team_dem_plus_inn_weighted": 100.79}
    return {
        "schema": 1, "season": 2026, "live_season": 2026, "complete": False,
        "as_of": {"boards": {"hitter_leaderboards": {"season": 2026, "as_of": "2026-10-03"}}, "team_lines": None},
        "league": {"roster": {"means": means}, "earned": {"means": dict(means, rotation_plus_ip_weighted=102.11)},
                   "pitches": {}, "coverage": {"offense_pa": 183848.0, "league_pa": 183849, "rotation_ip": 24206.0,
                                               "bullpen_ip": 15677.7, "league_ip": 43079.7}},
        "columns": {"style_z": ["z_hook", "z_pen", "z_bench", "z_ibb", "z_visit"],
                    "value_ruler": {"offense_plus": "ratio", "rotation_plus": "z", "bullpen_plus": "z",
                                    "leverage_deploy_plus": "z", "team_dem_plus": "z"}},
        "copy": {"lead": "Every number here is what happened, copied, summed or re-weighted. Descriptive: not a forecast.",
                 "basis_earned": "Earned basis sentence.", "basis_roster": "Club today sentence.",
                 "past_seasons": "Past seasons show the earned basis only.", "xwl": "xW-L sentence.",
                 "w_minus_xw": "W - xW sentence.", "plus_scale": "Scale sentence.", "coverage": "Coverage sentence.",
                 "tendencies": {"style_sentence": "Style, not skill.", "why_no_plus_metric": "a reason."}},
        "teams": teams,
        "history": {"cols": HIST_COLS, "seasons": {"2025": {"rows": hist, "index_basis": "lab panel",
                                                             "league": {"earned": means}}}},
    }


def _teams_ctx(hash_: str, doc: dict | None = None, live: bool = True, with_league: bool = True):
    return _ctx(hash_, None, live=live, with_league=with_league, teams=_team_doc() if doc is None else doc)


def _teams_html(ctx) -> str:
    return ctx.eval("__html['mlbstats-teams-root'] || ''")


def _body_rows(html: str) -> list[str]:
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r"<tr>(.*?)</tr>", body)


def _clubs_in_order(html: str) -> list[str]:
    return [re.search(r'data-club="([A-Z]+)"', r).group(1) for r in _body_rows(html)]


def _cells_of(html: str, key: str) -> list[str]:
    """The td of column `key` on every body row, by the header's position."""
    head = re.findall(r'<th [^>]*data-col="([a-z0-9_]+)"', html.split("<tbody>", 1)[0])
    i = head.index(key)
    return [re.findall(r"<td[^>]*>.*?</td>", r)[i] for r in _body_rows(html)]


VIEWS = {"standard": ("W-L", "RD", "xW-L", "W - xW", "Offense+", "Rotation+", "Bullpen+", "Team DEM+", "eWAR today", "eWAR earned"),
         "emplus": ("Offense+", "vs lg", "Heart 3", "Front 3", "Hi-Lev Core", "Lev Deploy+", "Team DEM+"),
         "runs": ("RS", "RA", "RS/G", "RA/G", "1-run", "Extra inn"),
         "pitch": ("Lineup P/PA", "Lineup PAR", "Staff P/IP", "Rotation P/IP", "Rotation PAR", "Bullpen P/IP",
                   "Bullpen PAR", "Rotation IP/GS", "Relief IP %"),
         "depth": ("Heart 3", "Rest", "Gap", "PA at 100+"),
         "tend": ("Hook", "Hook z", "Pen z", "Bench z", "IBB z", "Visit z", "SB att", "SB%", "To 3B")}


def test_every_teams_view_renders_thirty_clubs():
    for view, labels in VIEWS.items():
        html = _teams_html(_teams_ctx("#section=teams" + ("" if view == "standard" else "&tcols=" + view)))
        assert "mlbx-tmtable" in html, view
        assert len(_body_rows(html)) == 30, view
        for lab in labels:
            assert (">" + lab + "<" in html) or (">" + lab + ' <span class="mlbx-tmtag">' in html), (view, lab)
        # every club links to its Franchises page through the hub
        assert html.count('href="/franchise/#team=') == 30, view


def test_the_teams_table_sorts():
    doc = _team_doc()
    by_wins = [t["club"] for t in sorted(doc["teams"], key=lambda t: -t["w"])]
    assert _clubs_in_order(_teams_html(_teams_ctx("#section=teams"))) == by_wins
    by_rd = [t["club"] for t in sorted(doc["teams"], key=lambda t: t["rd"])]
    assert _clubs_in_order(_teams_html(_teams_ctx("#section=teams&tsort=rd.a"))) == by_rd
    by_pen = [t["club"] for t in sorted(doc["teams"], key=lambda t: -t["earned"]["bullpen_plus"])]
    assert _clubs_in_order(_teams_html(_teams_ctx("#section=teams&tsort=bullpen_plus.d"))) == by_pen
    # a header click sorts descending first, a second click flips it, and the club sorts A to Z first
    ctx = _teams_ctx("#section=teams")
    ctx.eval("window.MLBX_LEAGUE._teamClick({'data-tsort': 'xwl'})")
    xw = [t["club"] for t in sorted(doc["teams"], key=lambda t: (-t["xw"] / 162, t["club"]))]
    assert _clubs_in_order(_teams_html(ctx)) == xw
    ctx.eval("window.MLBX_LEAGUE._teamClick({'data-tsort': 'xwl'})")
    assert _clubs_in_order(_teams_html(ctx)) == [t["club"] for t in sorted(doc["teams"], key=lambda t: (t["xw"] / 162, t["club"]))]
    ctx.eval("window.MLBX_LEAGUE._teamClick({'data-tsort': 'club'})")
    assert _clubs_in_order(_teams_html(ctx)) == sorted(CLUBS)
    assert 'aria-sort="ascending" data-col="club"' in _teams_html(ctx)
    # the basis pill moves the rollups, and the sort follows the basis on screen
    ctx = _teams_ctx("#section=teams&tbasis=today&tsort=offense_plus.d")
    assert _clubs_in_order(_teams_html(ctx)) == [t["club"] for t in sorted(doc["teams"], key=lambda t: -t["roster"]["offense_plus"])]
    assert _cells_of(_teams_html(ctx), "offense_plus")[0].endswith(">%d</span></td>" % max(t["roster"]["offense_plus"] for t in doc["teams"]))


def test_tendency_cells_carry_no_value_class():
    html = _teams_html(_teams_ctx("#section=teams&tcols=tend"))
    for key in ("hook", "z_hook", "z_pen", "z_bench", "z_ibb", "z_visit", "pen_g", "sb_att", "sb_pct", "to3b"):
        for td in _cells_of(html, key):
            assert not re.search(r'class="[^"]*\b(vt|rem-plus)\b', td), (key, td)
            assert "vt-" not in td, (key, td)
    # the signed text columns take no colour either
    html = _teams_html(_teams_ctx("#section=teams&tcols=emplus"))
    for key in ("offense_plus_vs", "rotation_plus_vs", "bullpen_plus_vs", "team_dem_plus_vs"):
        assert all("vt" not in td and "rem-plus" not in td for td in _cells_of(html, key)), key
    html = _teams_html(_teams_ctx("#section=teams&tcols=runs"))
    for key in ("rd", "wx"):
        assert all("vt" not in td and "class=" not in td.split(">", 1)[1] for td in _cells_of(html, key)), key


def test_the_em_plus_columns_carry_the_board_families():
    html = _teams_html(_teams_ctx("#section=teams&tcols=emplus&tbasis=today"))
    want = {"offense_plus": "ratio", "heart_hem": "ratio", "rotation_plus": "z", "front_sem": "run",
            "bullpen_plus": "z", "high_lev_core_rem": "z", "leverage_deploy_plus": "z", "team_dem_plus": "z"}
    for key, fam in want.items():
        cells = _cells_of(html, key)
        assert all("vt-fam-" + fam in td for td in cells), (key, cells[0])


def test_the_value_ruler_key_sits_on_the_table():
    """Owner answer A-3: the legend chip rides the team rollups' table."""
    html = _teams_html(_teams_ctx("#section=teams"))
    assert 'class="vt-key"' in html and 'data-gl="value_ruler"' in html
    assert html.index('class="vt-key"') < html.index("<table")
    # a view with no ruler column carries no key
    assert 'class="vt-key"' not in _teams_html(_teams_ctx("#section=teams&tcols=tend"))


def test_the_league_means_and_vs_lg_read_from_the_payload():
    doc = _team_doc()
    doc["league"]["earned"]["means"]["offense_plus_pa_weighted"] = 97.25
    html = _teams_html(_teams_ctx("#section=teams&tcols=emplus", doc))
    assert "Offense+ 97.3," in html          # nearest, one decimal, from the payload
    first = sorted(doc["teams"], key=lambda t: -t["w"])[0]
    want = round(first["earned"]["offense_plus_raw"] - 97.25, 1)
    assert _cells_of(html, "offense_plus_vs")[0] == "<td>%s%.1f</td>" % ("+" if want > 0 else "", want)


def test_a_past_season_is_earned_only():
    doc = _team_doc()
    html = _teams_html(_teams_ctx("#section=teams&tseason=2025&tbasis=today", doc))
    assert "Season 2025" in html and "Past seasons show the earned basis only." in html
    assert 'data-tbasis="today" aria-pressed="false" disabled' in html
    assert ">eWAR today<" not in html and ">1-run<" not in html
    rows = sorted(doc["history"]["seasons"]["2025"]["rows"], key=lambda r: -r[17])
    ctx = _teams_ctx("#section=teams&tseason=2025&tsort=offense_plus.d", doc)
    assert _clubs_in_order(_teams_html(ctx)) == [r[0] for r in rows]
    # the live-only views say so instead of printing a column of dashes
    assert "live season only" in _teams_html(_teams_ctx("#section=teams&tseason=2025&tcols=tend", doc))


def test_no_division_title_field():
    """8.E: the Teams tab shows no division-title field in any case."""
    low = LEAGUE_JS.lower()
    for bad in ("division", "divchamp", "clinch", "champion"):
        assert bad not in low, bad
    html = _teams_html(_teams_ctx("#section=teams")).lower()
    assert "division" not in html and "champion" not in html


def test_no_fit_line_or_correlation_on_the_runs_charts():
    html = _teams_html(_teams_ctx("#section=teams&tcols=runs"))
    assert html.count('role="img"') == 2
    assert "y = x" in html                    # the identity line on wins against expected wins
    for bad in ("slope", "correl", "r =", "r&#178;", "trend", "regress", "fitted line"):
        assert bad not in html.lower(), bad
    i = LEAGUE_JS.index("function tCharts")
    body = LEAGUE_JS[i:LEAGUE_JS.index("\n  }\n", i) if "\n  }\n" in LEAGUE_JS[i:] else i + 4000]
    assert "fit:" not in body and "trend" not in body.lower()


# ---------------------------------------------------------------- the t keys
T_HASHES = [
    "tseason=2025",
    "tcols=emplus&tbasis=today",
    "tcols=runs&tsort=rd.a",
    "tseason=2025&tcols=pitch&tsort=rp_p_ip.d",
    "tcols=tend&tbasis=today&tsort=z_hook.a",
]


def test_the_t_keys_round_trip_through_write_hash():
    for t in T_HASHES:
        ctx = _teams_ctx("#section=teams&" + t)
        ctx.eval("window.MLBX_LEAGUE._writeHash()")
        written = ctx.eval("__hash[__hash.length - 1]")
        assert written == "#section=teams&" + t, (t, written)


def test_teams_defaults_write_no_t_key():
    ctx = _teams_ctx("#section=teams&tcols=standard&tbasis=earned&tsort=wl.d")
    ctx.eval("window.MLBX_LEAGUE._writeHash()")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=teams"


def test_t_keys_ride_through_before_the_script_lands():
    """mlbstats.js writes the hash at init when a column view is off its
    default, before the lazy script has landed: a deep link's t keys survive."""
    ctx = _teams_ctx("#section=teams&hcols=discipline&tcols=runs&tsort=rd.a", with_league=False)
    assert "Loading the Teams tab" in _teams_html(ctx)
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=teams&hcols=discipline&tcols=runs&tsort=rd.a"


def test_the_t_keys_are_one_list_and_collide_with_nothing():
    m = re.search(r"var TEAMS_KEY_RE = /\(\?:\^#\|\[#&\]\)\(t\(\?:([a-z|]+)\)=", MLBSTATS_JS)
    assert m, "TEAMS_KEY_RE changed shape"
    carried = set(m.group(1).split("|"))
    written = set(re.findall(r'p\.push\("t([a-z]+)="', LEAGUE_JS))
    read = set(re.findall(r"\[#&\]\)t([a-z]+)=", LEAGUE_JS))
    want = {"season", "cols", "basis", "sort"}
    assert carried == written == read == want, (carried, written, read)
    taken = set(re.findall(r"\[#&\]\)([a-z]+)=", MLBSTATS_JS)) | set(re.findall(r'"([a-z]+)="', MLBSTATS_JS))
    taken |= {"g" + k for k in ("view", "side", "season", "pos", "role", "hand", "age", "qual", "lg", "stat", "cmp")}
    assert not ({"t" + k for k in want} & taken), {"t" + k for k in want} & taken


def test_a_dark_shell_ignores_section_teams():
    ctx = _teams_ctx("#section=teams", live=False, with_league=False)
    assert ctx.eval("__scripts.length") == 0
    assert "team_stats" not in ctx.eval("JSON.stringify(__urls)")
    assert _teams_html(ctx) == ""


def test_teams_and_league_share_one_script_load():
    ctx = _teams_ctx("#section=teams", with_league=False)
    assert "Loading the Teams tab" in _teams_html(ctx)
    assert ctx.eval("__scripts.length") == 1
    ctx.eval(LEAGUE_JS)            # the script lands: Teams shows itself, the tab is still open
    assert "mlbx-tmtable" in _teams_html(ctx)
    assert any("mlb_team_stats" in u for u in json.loads(ctx.eval("JSON.stringify(__urls)")))


def test_the_landing_section_never_asks_for_team_stats():
    ctx = _teams_ctx("", with_league=False)
    assert "team_stats" not in ctx.eval("JSON.stringify(__urls)")
    assert ctx.eval("__scripts.length") == 0


def test_the_real_served_payload_renders_every_view():
    if not TEAMS_SERVED.exists():
        pytest.skip("the Team Stats payload is not built on this machine")
    doc = json.loads(TEAMS_SERVED.read_text(encoding="utf-8"))
    for view in VIEWS:
        html = _teams_html(_teams_ctx("#section=teams&tcols=" + view, doc))
        assert len(_body_rows(html)) == len(doc["teams"]), view
    hist = sorted((doc.get("history") or {}).get("seasons") or {})
    if hist:
        html = _teams_html(_teams_ctx("#section=teams&tseason=%s" % hist[-1], doc))
        assert len(_body_rows(html)) == 30


def test_no_forecast_word_in_the_teams_copy():
    i = LEAGUE_JS.index("// The Teams tab (owner asks 15 and 20")
    block = LEAGUE_JS[i:]
    strings = re.findall(r'"((?:[^"\\]|\\.)*)"', block)
    copy = " ".join(s for s in strings if " " in s).lower()
    for w in ("luck", " due ", "regress", "trending", " will ", "clutch", "sleeper", "breakout", "unlucky"):
        assert w not in copy, w


# ---------------------------------------------------------------- the F-SCORE column (FS_2B_SURFACES_DARK)
# Owner ask B (2026-09-30), plan 8.E and orchestrator ruling X13: ONE column,
# the score, letter and rank team_stats_export copies from the F-SCORE payload,
# on the live season only and only while the payload carries the join; no
# division-title field, no pillar. Synthetic join over the fixture's clubs.
def _fs_team_doc() -> dict:
    doc = _team_doc()
    for i, t in enumerate(doc["teams"]):
        t["fscore"] = {"score": round(80.0 + 1.5 * i, 1), "letter": "A" if i > 24 else "C", "rank": 30 - i}
    doc["fscore"] = {"joined": True, "generated_at": "2026-10-09T09:00:00+00:00", "as_of": "2026-10-09", "n": 30}
    return doc


def test_the_fscore_column_renders_from_the_join():
    doc = _fs_team_doc()
    html = _teams_html(_teams_ctx("#section=teams", doc))
    head = re.search(r'<th [^>]*data-col="fscore"[^>]*>.*?</th>', html).group(0)
    assert ">F-SCORE<" in head and 'data-gl="franchise_score"' in head
    assert "mlbstats-cv-wide" in head, "F-SCORE is not in the phone subset"
    cells = _cells_of(html, "fscore")
    assert len(cells) == 30
    by_club = {t["club"]: t["fscore"] for t in doc["teams"]}
    for club, cell in zip(_clubs_in_order(html), cells):
        fs = by_club[club]
        assert 'href="/franchise/#team=' + club + '&amp;sec=fscore"' in cell, cell
        assert '<span class="mlbx-fsletter">' + fs["letter"] + "</span>" in cell, cell
        assert re.search(r'<span class="rem-plus vt [^"]*vt-fam-z[^"]*">' + re.escape("%.1f" % fs["score"]) + "</span>", cell), cell
        assert "F-SCORE rank " + str(fs["rank"]) in cell
    # sorted by F-SCORE, highest first
    order = _clubs_in_order(_teams_html(_teams_ctx("#section=teams&tsort=fscore.d", doc)))
    assert order == [t["club"] for t in sorted(doc["teams"], key=lambda t: -t["fscore"]["score"])]
    # one column, Standard view only, live season only
    for view in ("emplus", "runs", "pitch", "depth", "tend"):
        assert 'data-col="fscore"' not in _teams_html(_teams_ctx("#section=teams&tcols=" + view, doc)), view
    assert 'data-col="fscore"' not in _teams_html(_teams_ctx("#section=teams&tseason=2025", doc))


def test_the_fscore_column_is_absent_without_the_join():
    """FSCORE_LIVE False: team_stats_export writes the pending note and no
    per-club block, so the Teams tab renders exactly the columns it had."""
    base = _teams_html(_teams_ctx("#section=teams"))
    assert 'data-col="fscore"' not in base and "F-SCORE" not in base
    doc = _team_doc()
    doc["fscore"] = {"joined": False, "note": "data/fscore.json is not on disk yet"}
    assert _teams_html(_teams_ctx("#section=teams", doc)) == base


def test_the_teams_tab_carries_no_division_title_field_with_fscore_joined():
    """8.E and ruling X13 hold with the join on: the F-SCORE column adds no
    division-title, title or pennant field, and its letter takes no tier class."""
    html = _teams_html(_teams_ctx("#section=teams", _fs_team_doc())).lower()
    for bad in ("division", "champion", "clinch", "pennant", "titles"):
        assert bad not in html, bad
    for cell in _cells_of(_teams_html(_teams_ctx("#section=teams", _fs_team_doc())), "fscore"):
        assert re.search(r'<span class="mlbx-fsletter">[A-F][+-]?</span>', cell)
    i = LEAGUE_JS.index('tdef({ key: "fscore"')
    assert 'fscore: true' in LEAGUE_JS[i:i + 200] and "live: true" in LEAGUE_JS[i:i + 200]
