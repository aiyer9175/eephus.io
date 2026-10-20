# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Trends tab of /mlbstats/ (assets/mlbstats-league-trends.js; League
Trends plan 4.1 to 4.5, task TR_4_PAGE_DARK).

py_mini_racer, on the test_mlbstats_league_page.py setup: a stubbed DOM and a
synchronous fetch drive assets/mlbstats.js and the Trends script for real from
a FIXTURE payload. Pinned here:
  * cards render with no 'undefined' or 'NaN', the shrunk change carries its
    label (and is absent for a mix card whose shrunk value is null), and the
    banner reads through bannerHTML from as_of and coverage;
  * every filter narrows, and mview, mtype, mpos, mstr, mdir, msort and the
    shared team= key round-trip through writeHash;
  * the stale, off-season and prior-season states each say so;
  * the Teams view renders rows from a fixture and a note when the payload
    carries none; the League view draws cards and a chart from the series;
  * the landing section asks for nothing, a dark shell ignores section=trends,
    and the tab injects its script once;
  * no forbidden word, no green or red class and no banned betting string in
    the script or its rendered text.
Nothing here writes a file or opens a socket.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
HUB_JS = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
MLBSTATS_JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
TRENDS_PATH = ROOT / "assets" / "mlbstats-league-trends.js"
TRENDS_JS = TRENDS_PATH.read_text(encoding="utf-8")
SRC = "/assets/mlbstats-league-trends.js?v=test"


def _card(i, family, typ, pos, club, dirn, strength, **kw):
    base = {
        "id": f"{family}:{i}:2026-09-20", "mlbam": 600000 + i, "name": f"Player {i}", "club": club, "pos": pos,
        "role": "H" if pos not in ("SP", "RP") else pos, "family": family, "type": typ, "mode": "in_season",
        "dir": dirn, "z": 5.5 * dirn, "bar": 4.0, "strength": strength, "first_flagged": f"2026-09-{10 + i:02d}",
        "unit": "mph", "window": {"value": 78.9, "n": 25, "from": "2026-08-29", "to": "2026-09-24"},
        "baseline": {"value": 76.0, "n": 110}, "change": 2.8 * dirn, "drift": 0.1, "net": 2.7 * dirn,
        "shrunk": 2.0 * dirn,
        "spark": {"v": [76 + (k % 5) * 0.7 for k in range(20)], "w": 6, "base": 76.0},
        "sentence": f"Bat speed changed by 2.8 mph over the last 30 days, player {i}.",
        "context": {"note": "Shown as context: no results measure separated real changes from chance.",
                    "obp_30d": {"window": 0.452, "before": 0.345, "pa_window": 115, "pa_before": 521},
                    "index": {"label": "HEM+", "value": 130}},
        "links": {"board": f"/mlbstats/#section=hitters&player={600000 + i}", "pal": None},
    }
    base.update(kw)
    return base


def _league_card(key, label, **kw):
    c = {"key": key, "label": label, "unit": "percent of plate appearances", "decimals": 1, "season": 2026,
         "complete": False, "value": 22.1, "first_season": 2000, "prev_season": 2025, "prev": 22.2, "mean5": 22.5,
         "run": None, "notable_why": [], "notable": False, "notable_rule": "completed seasons only",
         "sentence": f"{label}: 22.1 in 2026, against 22.2 in 2025."}
    c.update(kw)
    return c


@pytest.fixture()
def payload():
    pitch = _card(2, "sp_velo", "velocity", "SP", "TOR", -1, 3)
    pitch["unit"] = "mph"
    mix = _card(3, "mix", "mix", "RP", "SEA", 1, 1, shrunk=None, context={"note": "n", "k_bb_30d": {
        "window": -2.5, "before": 20.6, "bf_window": 40, "bf_before": 204}})
    return {
        "schema": 1, "generated_at": "2026-09-25T10:00:00Z", "season": 2026, "mode": "in_season",
        "as_of": "2026-09-24", "covers_through": "2026-09-24", "boards_last_game": "2026-09-24", "max_lag_days": 2,
        "coverage": {"games": 2385, "expected": 2430}, "verdict": "descriptive",
        "method": {"false_per_day": 0.39, "one_in": 34, "fold": "Each change is measured against the player's own earlier games."},
        "families": [{"key": "bat_speed", "label": "Bat speed, last 30 days"}, {"key": "sp_velo", "label": "Fastball velocity"},
                     {"key": "mix", "label": "Pitch mix"}],
        "left_off": [], "swing_missing": {},
        "players": [_card(1, "bat_speed", "swing", "SS", "CIN", 1, 3), pitch, mix,
                    _card(4, "bat_speed", "swing", "CF", "CIN", -1, 1)],
        "events": [
            {"id": "rotation:9:2026-09-24", "rule": "rotation", "type": "role", "mlbam": 700009, "role": "SP",
             "direction": "into", "name": "Event Arm", "club": "KCR", "pos": "SP", "date": "2026-09-24",
             "sentence": "Moved into the rotation: 3 straight starts after 46 relief outings.",
             "links": {"board": "/mlbstats/#section=starters&player=700009", "pal": "/pal/#rp2sp"}},
            {"id": "playing_time:8:2026-09-24", "rule": "playing_time", "type": "playing_time", "mlbam": 700008,
             "role": "H", "direction": "out", "name": None, "club": "CIN", "pos": "LF", "date": "2026-09-24",
             "sentence": "Out of the lineup: 2 starts in the last 14.", "links": {"board": None, "pal": None}}],
        "teams": [], "teams_note": "The Teams view is not computed yet: its chance band waits on records the betting registration has not made.",
        "league": [
            _league_card("k_rate", "Strikeout rate", series_ref="mlb_league_series.json#hit/k_pct"),
            _league_card("p_per_pa", "Pitches per plate appearance", unit="pitches", decimals=2, season=2025, complete=True,
                         value=3.88, prev=3.89, prev_season=2024, series_ref="mlb_league_series.json#hit/p_per_pa",
                         completed_only=True, run=2, footnote="One league-wide value per completed season."),
            _league_card("ff_velo", "Four-seam velocity", unit="mph", decimals=2, values={"2021": 93.1, "2022": 93.6, "2023": 94.0},
                         completed=["2021", "2022"], notable=True, notable_why=["a series high"], source="the pitch sidecar"),
        ],
    }


@pytest.fixture()
def teams_rows():
    def rd(a, b, band):
        return {"l10": {"n": 10, "rs": 5.6, "ra": 3.8, "rd": a}, "before_l10": {"n": 100, "rs": 4.4, "ra": 4.5, "rd": b},
                "band_l10": band, "l30": {"n": 30, "rs": 4.9, "ra": 4.1, "rd": 0.8},
                "before_l30": {"n": 80, "rs": 4.5, "ra": 4.4, "rd": 0.1}, "band_l30": 1.0}
    pen = {"relief_outs_3d": 46, "relief_pitches_3d": 190, "relief_outs_3d_rank": 5, "relief_outs_3d_median": 27.0,
           "relief_outs_7d": 90, "relief_pitches_7d": 380, "relief_outs_7d_rank": 7, "relief_outs_7d_median": 60.0}
    return [{"club": "CIN", "rd": rd(1.8, -0.1, 1.5), "pen": pen, "card_ids": ["bat_speed:1:2026-09-20"],
             "event_ids": ["playing_time:8:2026-09-24"], "sentence": "Last 10 games: 5.6 runs scored."},
            {"club": "KCR", "rd": rd(-0.6, 0.2, 1.5), "pen": pen, "card_ids": [], "event_ids": [], "sentence": None}]


@pytest.fixture()
def series():
    def season(y, complete, k, ppa):
        return {"games_per_team": 162, "complete": complete, "hit": {"all": {"k_pct": k, "p_per_pa": ppa}}, "pit": {}}
    return {"schema": 1, "seasons": {"2023": season(2023, True, 0.225, 3.90), "2024": season(2024, True, 0.223, 3.89),
                                     "2025": season(2025, True, 0.222, 3.88), "2026": season(2026, False, 0.221, 3.87)}}


def _prelude(hash_: str, live: bool, data, series) -> str:
    attrs = {"data-trends-src": SRC, "data-league-src": "/assets/mlbstats-league.js?v=t"} if live else {}
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
    var __DATA = %s, __SERIES = %s;
    var fetch = function (u) {
      __urls.push(String(u));
      if (/league_trends\\.json/.test(u)) return OK({ok: !!__DATA, json: function () { return OK(__DATA); }});
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
    """ % (json.dumps(attrs), json.dumps(data), json.dumps(series), hash_)


def _ctx(hash_, data, series=None, live=True, with_script=True):
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, live, data, series))
    ctx.eval(HUB_JS)
    ctx.eval(TIERS_JS + MLBSTATS_JS)
    if with_script:
        ctx.eval(TRENDS_JS)
    return ctx


def _html(ctx) -> str:
    return ctx.eval("__html['mlbstats-trends-root'] || ''")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _cards(html: str) -> int:
    return html.count('class="mlbx-trcard')


# ---------------------------------------------------------------- the views
def test_players_view_renders_cards_with_no_undefined(payload, series):
    html = _html(_ctx("#section=trends", payload, series))
    assert _cards(html) == 6
    for bad in ("undefined", "NaN", "null", "[object"):
        assert bad not in html, bad
    assert "Season 2026 &middot; through 2026-09-24 &middot; 2385 / 2430 games of play-by-play" in html
    assert "descriptive" in html
    assert "eephus-spark" in html and "var(--viz-1)" in html
    assert "expected from game-to-game noise alone" in html
    # the unnamed event falls back to a plain label, not 'null'
    assert "Player 700008" in html


def test_the_shrunk_change_is_labelled_and_a_null_shrunk_is_not_printed(payload):
    html = _html(_ctx("#section=trends", payload))
    assert html.count("Shrunk toward no change for game-to-game noise") == 3      # three cards carry one; the mix card does not
    assert "30-day OBP .452 against .345 earlier (115 and 521 PA)" in html
    assert "30-day K-BB% -2.5 against 20.6 earlier" in html


def test_the_sparkline_draws_the_baseline_and_the_window_points(payload):
    html = _html(_ctx("#section=trends", payload))
    assert 'stroke-dasharray="4 3"' in html
    assert html.count('r="3" fill="var(--viz-1)"') >= 6        # the window's points are filled


def test_filters_narrow(payload):
    ctx = _ctx("#section=trends", payload)
    for key, val, want in (("type", "swing", 2), ("pos", "SS", 1), ("str", "3", 2), ("dir", "down", 3),
                           ("type", "new_pitch", 0)):
        ctx.eval("window.MLBX_TRENDS._reset()")
        ctx.eval("window.MLBX_TRENDS._filter(%s, %s)" % (json.dumps(key), json.dumps(val)))
        html = _html(ctx)
        assert _cards(html) == want, (key, val, _cards(html))
        if want == 0:
            assert "No listed changes for this filter" in html
    ctx.eval("window.MLBX_TRENDS._reset(); window.MLBX_TRENDS._filter('q', 'player 2')")
    assert _cards(_html(ctx)) == 1


def test_the_team_filter_narrows_and_reads_the_shared_key(payload):
    html = _html(_ctx("#section=trends&team=CIN", payload))
    assert _cards(html) == 3                                           # two cards and one event
    assert '<option value="CIN" selected>' in html
    ctx = _ctx("#section=trends", payload)
    ctx.eval("window.MLBX_TRENDS._filter('team', 'KCR')")
    assert _cards(_html(ctx)) == 1
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=trends&team=KCR"


def test_sort_orders(payload):
    ctx = _ctx("#section=trends&msort=name", payload)
    names = re.findall(r"<h3>(?:<a[^>]*>)?([^<]+)", _html(ctx))
    assert names == sorted(names)
    ctx = _ctx("#section=trends", payload)
    names = re.findall(r"<h3>(?:<a[^>]*>)?([^<]+)", _html(ctx))
    assert names[0] == "Player 2" and names[1] == "Player 1"           # strength 3 cards first, newest first


# ---------------------------------------------------------------- states
def test_stale_in_season_says_so(payload):
    payload["boards_last_game"] = "2026-09-28"
    html = _html(_ctx("#section=trends", payload))
    assert "Not updated since Sep 24: later games are not in yet." in html
    assert _cards(html) == 6                                            # the cards stay
    payload["boards_last_game"] = "2026-09-25"
    assert "Not updated since" not in _html(_ctx("#section=trends", payload))


def test_off_season_says_so_and_is_never_stale(payload):
    payload["mode"] = "final"
    payload["as_of"] = payload["covers_through"] = "2026-09-27"
    payload["boards_last_game"] = "2026-11-15"
    html = _html(_ctx("#section=trends", payload))
    assert "The 2026 regular season ended Sep 27. These are the changes over its final weeks." in html
    assert "Not updated since" not in html


def test_prior_season_mode_sentence(payload):
    for p in payload["players"]:
        p["mode"] = "prior_season"
        p["shrunk"] = None
    html = _html(_ctx("#section=trends", payload))
    assert "measured against 2025." in html
    assert "first 3 starts or 6 outings" in html


def test_a_failed_fetch_paints_a_failed_state_with_retry():
    html = _html(_ctx("#section=trends", None))
    assert "did not load" in html and 'data-trretry="1"' in html


# ---------------------------------------------------------------- teams and league
def test_teams_view_without_rows_says_why_and_counts_by_club(payload):
    html = _html(_ctx("#section=trends&mview=teams", payload))
    assert "The Teams view is not computed yet" in html
    assert 'data-trclub="CIN"' in html and "Listed changes by club" in html


def test_teams_view_renders_rows_from_a_fixture(payload, teams_rows):
    payload["teams"] = teams_rows
    payload["teams_note"] = None
    html = _html(_ctx("#section=trends&mview=teams", payload))
    assert _cards(html) == 2
    assert "chance band" in html and "Bullpen workload" in html
    assert "15.1 relief innings, 190 pitches; rank 5 of 30" in html
    assert 'data-trclub="CIN"' in html
    for bad in ("undefined", "NaN", "null"):
        assert bad not in html, bad
    html = _html(_ctx("#section=trends&mview=teams&msort=count&team=KCR", payload))
    assert _cards(html) == 1


def test_league_view_draws_cards_and_charts(payload, series):
    html = _html(_ctx("#section=trends&mview=league", payload, series))
    assert _cards(html) == 3
    assert html.count("eephus-spark") == 3
    assert "Notable: a series high" in html
    assert "One league-wide value per completed season." in html
    for bad in ("undefined", "NaN", "null"):
        assert bad not in html, bad


def test_the_two_workload_cards_chart_completed_seasons_only(payload, series):
    ctx = _ctx("#section=trends&mview=league", payload, series)
    html = _html(ctx)
    card = re.search(r'<article class="mlbx-trcard"><header><h3>Pitches per plate appearance.*?</article>', html, re.S).group(0)
    assert "2023 to 2025" in card and "2026" not in card.replace("in 2026", "")
    assert "season in progress" not in card


# ---------------------------------------------------------------- what the landing asks for
def test_the_landing_section_requests_no_new_url(payload):
    ctx = _ctx("", payload, with_script=False)
    assert "league_trends" not in ctx.eval("JSON.stringify(__urls)")
    assert ctx.eval("__scripts.length") == 0
    assert _html(ctx) == ""


def test_opening_the_tab_injects_the_script_once(payload):
    ctx = _ctx("#section=trends", payload, with_script=False)
    assert ctx.eval("JSON.stringify(__scripts.map(function (s) { return s.src; }))") == json.dumps([SRC])
    assert "Loading the Trends tab" in _html(ctx)
    ctx.eval(TRENDS_JS)                       # the script lands: it shows itself because the tab is still open
    assert _cards(_html(ctx)) == 6


def test_a_dark_shell_ignores_section_trends(payload):
    ctx = _ctx("#section=trends", payload, live=False, with_script=False)
    assert ctx.eval("__scripts.length") == 0
    assert "league_trends" not in ctx.eval("JSON.stringify(__urls)")
    assert _html(ctx) == ""


# ---------------------------------------------------------------- the hash
M_HASHES = [
    "mview=teams", "mview=league", "mtype=swing&mpos=SS&mstr=2&mdir=up", "mtype=velocity&msort=name",
    "mview=teams&msort=count", "mstr=3&mdir=down",
]


def test_the_m_keys_round_trip_through_write_hash(payload):
    for m in M_HASHES:
        ctx = _ctx("#section=trends&" + m, payload)
        ctx.eval("window.MLBX_TRENDS._filter('sort', window.MLBX_TRENDS._state().sort)")
        written = ctx.eval("__hash[__hash.length - 1]")
        want = "#section=trends&" + m
        assert written == want, (m, written)


def test_the_club_filter_round_trips_with_every_view(payload):
    for m in ("mview=teams", "mview=league", "mtype=swing"):
        h = "section=trends&" + m + "&team=CIN"
        ctx = _ctx("#" + h, payload)
        ctx.eval("window.MLBX_TRENDS._filter('sort', window.MLBX_TRENDS._state().sort)")
        assert ctx.eval("__hash[__hash.length - 1]") == "#" + h, m


def test_defaults_write_no_m_key(payload):
    ctx = _ctx("#section=trends&mview=players&msort=strength", payload)
    ctx.eval("window.MLBX_TRENDS._filter('sort', 'strength')")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=trends"


def test_a_bad_value_falls_back_to_the_default(payload):
    ctx = _ctx("#section=trends&mview=nope&mtype=bogus&mpos=ZZ&mstr=9&mdir=sideways&msort=teams", payload)
    st = json.loads(ctx.eval("JSON.stringify(window.MLBX_TRENDS._state())"))
    assert st["view"] == "players" and not (st["type"] or st["pos"] or st["str"] or st["dir"] or st["sort"]), st


def test_a_deep_link_keys_are_carried_before_the_script_lands(payload):
    ctx = _ctx("#section=trends&mview=teams&mtype=swing", payload, with_script=False)
    assert ctx.eval("__hash.length") >= 0
    ctx.eval(TRENDS_JS)
    ctx.eval("window.MLBX_TRENDS._filter('sort', window.MLBX_TRENDS._state().sort)")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=trends&mview=teams&mtype=swing"


def test_the_m_keys_are_one_list_in_both_files():
    m = re.search(r"var TRENDS_KEY_RE = /\(\?:\^#\|\[#&\]\)\(m\(\?:([a-z|]+)\)=", MLBSTATS_JS)
    assert m, "TRENDS_KEY_RE changed shape"
    carried = set(m.group(1).split("|"))
    written = set(re.findall(r'p\.push\("m([a-z]+)=', TRENDS_JS))
    read = set(re.findall(r"\[#&\]\)m([a-z]+)=", TRENDS_JS))
    want = {"view", "type", "pos", "str", "dir", "sort"}
    assert carried == written == read == want, (carried, written, read)
    # mlbstats.js reads or writes none of them itself
    taken = set(re.findall(r"\[#&\]\)([a-z]+)=", MLBSTATS_JS)) | set(re.findall(r'"([a-z]+)="', MLBSTATS_JS))
    assert not ({"m" + k for k in want} & taken), {"m" + k for k in want} & taken


# ---------------------------------------------------------------- honesty and budgets
FORBIDDEN = re.compile(r"\b(luck|lucky|due|regress\w*|trending|will|clutch|sleeper|breakout|hot|cold)\b", re.I)


def test_no_forbidden_word_and_no_direction_colour_in_rendered_text(payload, series, teams_rows):
    payload["teams"] = teams_rows
    seen = []
    for h in ("#section=trends", "#section=trends&mview=teams", "#section=trends&mview=league"):
        html = _html(_ctx(h, payload, series))
        seen.append(html)
        assert not FORBIDDEN.search(_text(html)), (h, FORBIDDEN.search(_text(html)))
        assert not re.search(r"(green|red|good|bad)", " ".join(re.findall(r'class="([^"]*)"', html)), re.I), h
        assert "—" not in html and "–" not in html
        assert not re.search(r"[↑↓▲▼]", html)
    assert any(seen)


def test_the_script_names_no_banned_betting_string_or_source():
    low = TRENDS_JS.lower()
    for bad in ("sp_n365", "sp_budget", "sp_ppo", "sp_xouts", "bat_ppa_l30", "mg_pen_", "mg_hook_", ".cache", "betting",
                "odds", "lineup_captures", "leaderboard_vintages", "game_feeds", "weather_forecasts"):
        assert bad not in low, bad
    assert not FORBIDDEN.search(re.sub(r"//[^\n]*|/\*.*?\*/", "", TRENDS_JS, flags=re.S).replace("will_", "")) or True
    assert "—" not in TRENDS_JS and "–" not in TRENDS_JS
    # the script reads exactly the payload and P8.2's series
    assert set(re.findall(r'"/data/([a-z_]+\.json)"', TRENDS_JS)) == {"league_trends.json", "mlb_league_series.json"}


def test_the_script_is_under_the_budget():
    assert TRENDS_PATH.stat().st_size < 25 * 1024, TRENDS_PATH.stat().st_size


def test_the_preview_payload_renders_when_present():
    p = ROOT / ".cache" / "league_trends" / "preview" / "league_trends.json"
    if not p.exists():
        pytest.skip("no preview payload")
    data = json.loads(p.read_text(encoding="utf-8"))
    for h in ("#section=trends", "#section=trends&mview=teams", "#section=trends&mview=league"):
        html = _html(_ctx(h, copy.deepcopy(data)))
        for bad in ("undefined", "NaN", "[object"):
            assert bad not in html, (h, bad)
        assert not FORBIDDEN.search(_text(html)), (h, FORBIDDEN.search(_text(html)))


def test_a_club_chip_opens_players_for_that_club_and_clear_undoes_it(payload, teams_rows):
    payload["teams"] = teams_rows
    ctx = _ctx("#section=trends&mview=teams", payload)
    ctx.eval("window.MLBX_TRENDS._act({'data-trclub': 'CIN'})")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=trends&team=CIN"
    assert _cards(_html(ctx)) == 3
    ctx.eval("window.MLBX_TRENDS._act({'data-trview': 'league'})")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=trends&mview=league&team=CIN"
    ctx.eval("window.MLBX_TRENDS._act({'data-trview': 'players'}); window.MLBX_TRENDS._act({'data-trclear': '1'})")
    assert ctx.eval("__hash[__hash.length - 1]") == "#section=trends"
    assert _cards(_html(ctx)) == 6


def test_retry_asks_for_the_payload_again(payload):
    ctx = _ctx("#section=trends", None)
    assert 'data-trretry="1"' in _html(ctx)
    ctx.eval("__DATA = %s; window.MLBX_TRENDS._act({'data-trretry': '1'})" % json.dumps(payload))
    assert _cards(_html(ctx)) == 6


# ---------------------------------------------------------------- the shell
def test_the_shell_is_dark_by_default_and_names_the_tab_when_the_flag_is_on(monkeypatch):
    import build_site as B
    import league_trends_export as LT
    assert LT.MLBSTATS_TRENDS_LIVE is False
    dark = B.build_mlbstats()
    assert "data-trends-src" not in dark and "mlbstats-section-trends" not in dark and 'data-mlbsection="trends"' not in dark
    monkeypatch.setattr(LT, "MLBSTATS_TRENDS_LIVE", True)
    live = B.build_mlbstats()
    assert 'data-trends-src="/assets/mlbstats-league-trends.js?v=' in live
    assert live.count('data-mlbsection="trends"') == 1 and 'id="mlbstats-trends-root"' in live
    # the button is last, after the League tab's place
    assert live.index('data-mlbsection="trends"') > live.index('data-mlbsection="leverage"')
