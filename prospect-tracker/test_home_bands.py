# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HOME_4: the two-band homepage (LANE_HOME 3.1 and 3.2, SP-Q2, SP-D1).

The homepage takes the shared site header; the left column is the MLB News
rail (20 rows, key, All MLB News link, as-of line), sticky with its own scroll
above 900 px and a 6-row block after the masthead at 900 px and below. The
main column is a slim masthead, the MLB band and the Prospects band in
HOME_BAND_ORDER, then the site strip. Every block of LANE_HOME 3.2 sits in
its band; the sidebar search, the module nav, the drawer, "More analysis
soon", the glossary teaser and the scatter teaser are gone. Measured at HEAD
before the change: the first news row at y 1165 at 1280 x 900 and inside the
closed drawer at 390; the first MLB content at y 1886 of 2829 at 1280.

HOME_5: while mlb_events.MLB_EVENTS_LIVE is True the MLB band carries the
Transactions module (Trades: every deal of the last 30 days, one row per deal,
board prospects flagged by overall rank, the PROSPX Trade Audit link only on a
deal with a board player; Roster moves: 8 rows of 60-day IL placements, DFAs,
claims and contract selections of the last 7 days) and the prospect-only
Recent Trades module leaves the Prospects band. Off, the page is unchanged.
"""
from __future__ import annotations

import inspect
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import build_site as B
import mlb_events as M

ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def home() -> str:
    return (ROOT / "index.html").read_text(encoding="utf-8")


def _band(page: str, band: str) -> str:
    start = page.index(f'<section class="home-band home-band--{band}"')
    # the band runs to the next band, the forums slot or the site strip
    nxt = [i for i in (page.find('<section class="home-band ', start + 10),
                       page.find('<div id="home-forums-slot"', start),
                       page.find('<section class="home-site-strip"', start)) if i > start]
    return page[start:min(nxt)]


# ---- structure of the served page ------------------------------------------

def test_the_bands_follow_the_one_order_constant(home):
    assert B.HOME_BAND_ORDER == ("mlb", "pro")
    found = re.findall(r'<section class="home-band home-band--(\w+)"', home)
    assert tuple(found) == B.HOME_BAND_ORDER
    jump = re.search(r'<nav class="home-jump"[^>]*>(.*?)</nav>', home, re.S).group(1)
    assert re.findall(r'href="#band-(\w+)"', jump) == list(B.HOME_BAND_ORDER)
    # each band head: a 32 px mark, an h2, one count line, the family rule
    for b in B.HOME_BAND_ORDER:
        head = _band(home, b).split('<div class="band-head">', 1)[1].split("</div></div>", 1)[0]
        assert 'width="32"' in head and "<h2" in head and 'class="band-count"' in head, b


def test_the_reversal_is_one_line(monkeypatch):
    monkeypatch.setattr(B, "HOME_BAND_ORDER", ("pro", "mlb"))
    out = B.build_home([], {})
    assert re.findall(r'<section class="home-band home-band--(\w+)"', out) == ["pro", "mlb"]


def test_every_block_sits_in_its_band(home):
    mlb, pro = _band(home, "mlb"), _band(home, "pro")
    # While the MLB events feed is live, Recent Trades merges into the MLB
    # band's Transactions module (HOME_5); off, it stays in the Prospects band.
    live = B._events_live()
    trades = ("<h2>Transactions</h2>", "<h2>Recent Trades</h2>")
    for needle in ('id="home-scores-slot"', '<nav class="club-logos"', ">Free Agency<",
                   "MLB Projections<", "Leaders<", "Trade Machine<", "Alchemy Lab<",
                   'class="xmod-card xmod-strip-card"', ">Diamond Pass<", "FG pts") + trades[:live]:
        assert needle in mlb, needle
    for needle in ('<nav class="band-links"', 'class="home-module spot-module"', "<h2>Top Prospects</h2>",
                   "<h2>Top Movers</h2>", "<h2>Recent Debuts</h2>", "<h2>Top Farm Systems</h2>",
                   B._HISTORY_LABEL, "<h2>eFV Distribution</h2>", "CollegeSavant<", "Park Factors<",
                   'id="draft-war-room-banner"') + trades[1:] * (not live):
        assert needle in pro, needle
    assert trades[1] not in mlb and trades[0] not in pro
    assert (trades[1] in home) is not live
    # the MLB band carries no prospect module and the Prospects band no MLB card
    for needle in ("<h2>Top Prospects</h2>", "spot-module", "Park Factors<"):
        assert needle not in mlb, needle
    for needle in ("MLB Projections<", "Trade Machine<", "club-logos"):
        assert needle not in pro, needle
    strip = home.split('<section class="home-site-strip"', 1)[1].split("</section>", 1)[0]
    for needle in ("Articles<", "Model Accountability<", f"{B.GLOSSARY_DISPLAY_NAME}<"):
        assert needle in strip, needle
    # the merged cards: one leader row each, linking its own section
    leaders = mlb.split("Leaders</span>", 1)[1].split('<div class="xmod-card', 1)[0]
    assert re.findall(r'href="/mlbstats/#section=(\w+)', leaders) == ["bullpen", "defense", "leverage"]


def test_thirty_club_logos_link_their_franchise_view(home):
    # club links through the resolver (owner ask 9): the #team=<CODE> shape
    row = re.search(r'<nav class="club-logos"[^>]*>(.*?)</nav>', home, re.S).group(1)
    codes = re.findall(r'class="club-logo-link club-link" href="/franchise/#team=([A-Z]{2,3})" data-club="\1"', row)
    assert len(codes) == 30 == len(set(codes))
    assert set(codes) == {r["code"] for r in B._club_table()["rows"]}
    assert len(re.findall(r'<img class="club-logo" ', row)) == 30


def test_the_removed_blocks_are_gone(home):
    for gone in ('class="sb-search"', "Search prospects", "More analysis soon", 'class="glossary-teaser"',
                 'class="scatter-teaser"', 'class="home-sidebar"', 'class="sb-nav"', 'class="sb-subnav"',
                 "home-nav-toggle", 'class="sb-brand"', "Today's term", "Build a scatterplot"):
        assert gone not in home, gone
    for name in ("_scatter_teaser", "_glossary_teaser_terms", "_cross_module_strip", "THEME_BTN",
                 "_HOME_DRAWER_JS"):
        assert not hasattr(B, name), name


def test_one_nav_vocabulary(home):
    assert home.count('<header class="eephus-nav">') == 1
    assert "sidebar_labels" not in inspect.getsource(B.build_home)
    assert 'aria-label="Modules"' not in home
    # no second module list on the page: every module link lives in the header
    # (the footer keeps its own short list)
    body = home.split("</header>", 1)[1].split('<footer class="eephus-footer"', 1)[0]
    for _k, _lab, href in B.nav_leaves():
        if href in ("/", "/prospx/", "/articles/", "/glossary/", "/fa/", "/projections/", "/trademachine/",
                    "/pal/", "/diamond/", "/fantasy/", "/betting/", "/collegesavant/", "/forums/",
                    "/mlbstats/"):
            continue   # a module card's own link, not a nav list
        assert f'<a href="{href}">' not in body, href


def test_the_rail_is_the_news(home):
    rail = home.split('<aside class="home-rail"', 1)[1].split("</aside>", 1)[0]
    rows = re.findall(r'<a class="feed-item( wire-more)?"', rail)
    assert 0 < len(rows) <= B._HOME_RAIL_ROWS
    assert [bool(m) for m in rows] == [i >= B._HOME_RAIL_PHONE_ROWS for i in range(len(rows))]
    assert f'<a class="feed-all" href="/news/">All {B.NEWS_LABEL} →</a>' in rail
    assert '<p class="feed-asof">As of ' in rail and 'id="wire-key"' in rail


# ---- the lead and the callouts ---------------------------------------------

def _art(days_old: int) -> dict:
    d = date.fromordinal(date.today().toordinal() - days_old).isoformat()
    return {"title": "A Piece", "slug": "a-piece", "date_sort": d, "date_disp": d, "summary": "S",
            "author": "W"}


def test_the_lead_runs_only_while_the_newest_article_is_fresh():
    fresh = B.build_home([_art(B._HOME_LEAD_MAX_DAYS)], {})
    stale = B.build_home([_art(B._HOME_LEAD_MAX_DAYS + 1)], {})
    assert '<article class="lead-story' in fresh
    assert '<article class="lead-story' not in stale
    strip = stale.split('<section class="home-site-strip"', 1)[1]
    assert 'href="/articles/a-piece/"' in strip and "the latest piece" in strip


def test_one_callout_per_band_from_its_own_calendar(monkeypatch):
    oct7 = date(2026, 10, 7)
    assert "FanGraphs list season" in B._date_callout("pro", oct7)
    jul20 = date(2026, 7, 20)
    assert "MLB trade deadline" in B._date_callout("mlb", jul20)
    assert "trade deadline" not in B._date_callout("pro", jul20)
    assert "Draft" not in B._date_callout("mlb", date(2026, 7, 1))
    real = B._cached_data_json

    def bracket(series, as_of="2026-10-05"):
        def fake(name):
            if name == "bracket_sim.json":
                return {"season": 2026, "as_of": as_of, "serve": {"on": True}, "series": series}
            return real(name)
        return fake
    live = [{"round": "F", "decided": True}, {"round": "W", "decided": False}]
    monkeypatch.setattr(B, "_cached_data_json", bracket(live))
    assert "Postseason" in B._date_callout("mlb", oct7)
    monkeypatch.setattr(B, "_cached_data_json", bracket([{"round": "W", "decided": True}]))
    assert "Postseason" not in B._date_callout("mlb", oct7)
    monkeypatch.setattr(B, "_cached_data_json", bracket(live, as_of="2026-09-01"))
    assert "Postseason" not in B._date_callout("mlb", oct7)


# ---- the Transactions module (HOME_5), on a fixture recent.json ------------

TX_TODAY = date.today()


def _d(n: int) -> str:
    return (TX_TODAY - timedelta(days=n)).isoformat()


NYY, BOS, SEA, TEX = 147, 111, 136, 140
DEAL_A = "Boston Red Sox traded RHP Vet A and SS Pro Kid to New York Yankees for C Vet C."


def _tx(mlbam, day, typ, tx, key=None, name=None, frm=None, to=None, desc="", **kw):
    r = {"mlbam": mlbam, "name": name or f"P{mlbam}", "date": day, "type": typ, "tx": tx,
         "clubs": [c for c in (frm, to) if c is not None], "desc": desc or f"row {tx}"}
    if key:
        r["key"] = key
    if frm is not None:
        r["from"] = frm
    if to is not None:
        r["to"] = to
    if typ == "trade":
        r["deal"] = tx
    r.update(kw)
    return r


TX_ROWS = [
    # Deal A: two veterans and a board prospect, one row repeated in the cache.
    _tx(10, _d(1), "trade", 900, "vet_a", "Vet A", BOS, NYY, DEAL_A),
    _tx(10, _d(1), "trade", 900, "vet_a", "Vet A", BOS, NYY, DEAL_A),
    _tx(20, _d(1), "trade", 900, None, "Pro Kid", BOS, NYY, DEAL_A),
    _tx(40, _d(1), "trade", 900, "vet_c", "Vet C", NYY, BOS, DEAL_A),
    # Deal B: the same clubs and day, another deal, no board player.
    _tx(11, _d(1), "trade", 901, "vet_b", "Vet B", BOS, NYY, "Boston Red Sox traded LHP Vet B."),
    # Outside the 30-day window.
    _tx(12, _d(32), "trade", 902, "vet_old", "Vet Old", BOS, SEA, "old deal"),
] + [
    # Seven more single-player deals: ten in all, the first eight show.
    _tx(200 + i, _d(2), "trade", 920 + i, f"t{i}", f"Trade {i}", 108 + i, 133 + i, f"deal {i}")
    for i in range(7)
] + [
    _tx(50, _d(2), "il_place", 950, "il60", "Sixty Day", None, SEA,
        "Seattle Mariners placed RHP Sixty Day on the 60-day injured list.", il="60-day IL"),
    _tx(51, _d(1), "il_place", 951, "il15", "Fifteen Day", None, SEA,
        "Seattle Mariners placed RHP Fifteen Day on the 15-day injured list.", il="15-day IL"),
    _tx(52, _d(1), "claim", 952, "cl", "Claimed Guy", SEA, TEX, "Texas Rangers claimed Claimed Guy."),
    _tx(53, _d(3), "callup", 953, "cu", "Selected Guy", None, TEX, "Texas Rangers selected Selected Guy."),
    _tx(54, _d(1), "recall", 954, "rc", "Recalled Guy", None, TEX, "Texas Rangers recalled Recalled Guy."),
    _tx(55, _d(9), "dfa", 955, "olddfa", "Old Dfa", TEX, None, "Texas Rangers designated Old Dfa."),
] + [
    _tx(60 + i, _d(4), "dfa", 960 + i, f"dfa{i}", f"Dfa {i}", TEX, None, f"Texas Rangers designated Dfa {i}.")
    for i in range(7)
]
TX_RECENT = {"through": _d(1), "rows": TX_ROWS}
TX_PLAYERS = [
    # The StatsAPI deal replaces Pro Kid's own trade row within a day.
    {"player_key": "pro_kid", "mlbam_id": 20, "player_name": "Pro Kid", "org": "NYY",
     "overall_rank": 5, "trades": [{"trade_date": _d(1), "from_org": "BOS", "to_org": "NYY"}]},
    # A board trade StatsAPI does not carry: a deal from the board's own row.
    {"player_key": "board_two", "mlbam_id": 22, "player_name": "Board Two", "org": "TEX",
     "overall_rank": 50, "trades": [{"trade_date": _d(3), "from_org": "SEA", "to_org": "TEX"}]},
]


@pytest.fixture
def tx_fake(monkeypatch):
    orig = B._cached_data_json
    store = {"recent": TX_RECENT}

    def f(name):
        if name == "mlb_events/recent.json":
            return store["recent"]
        if name == "player_links.json":
            return {"byKey": {}}
        if name == "fa_class.json":
            return {"events": []}
        if name == "mlb_player_detail.json":
            return {"players": {"vet_a": {"career": [{"war": 5.0}]},
                                "vet_c": {"career": [{"war": 20.0}], "careerPit": [{"war": 10.0}]}}}
        return orig(name)
    monkeypatch.setattr(B, "_cached_data_json", f)
    monkeypatch.setattr(B, "_save_wire_fv_ledger", lambda *a, **k: None)
    monkeypatch.setattr(M, "MLB_EVENTS_LIVE", True)
    return store


def _tx_home(store, recent) -> str:
    store["recent"] = recent
    return B.build_home([], {"players": TX_PLAYERS, "graduates": [], "as_of": "2026-10-01"})


def _tx_col(page: str, col: str) -> str:
    return page.split(f'<div class="tx-col" id="tx-{col}">', 1)[1].split('<div class="tx-col"', 1)[0]


_DEAL_RE = r'<div class="tx-row" data-fam="trd" data-type="trade"[^>]*>(.*?)</div>'


def test_transactions_list_each_deal_once_and_flag_board_players(tx_fake):
    page = _tx_home(tx_fake, TX_RECENT)
    mlb, pro = _band(page, "mlb"), _band(page, "pro")
    assert "<h2>Transactions</h2>" in mlb and 'class="tx-mod"' not in pro
    assert "<h2>Recent Trades</h2>" not in page, "Recent Trades merges into Trades"
    trades = _tx_col(page, "trades")
    deals = re.findall(_DEAL_RE, trades)
    # Deal A, deal B, seven single-player deals, Board Two's own deal; the old
    # deal is outside the window and Pro Kid's own trade row is replaced.
    assert len(deals) == 10, deals
    assert sum("Pro Kid" in d for d in deals) == 1
    assert not any("Vet Old" in d for d in deals)
    shown, more = trades.split('<details class="tx-all">', 1)
    assert len(re.findall(r'class="tx-row"', shown)) == B._TX_TRADE_ROWS
    assert "<summary>2 more deals</summary>" in more
    a = next(d for d in deals if "Pro Kid" in d)
    # The board player leads, then career WAR (Vet C 30 over Vet A 5), then "+n".
    names = re.sub(r"<[^>]+>", "", a.split('class="tx-names">', 1)[1].split('<a class="tx-audit"', 1)[0])
    assert names == "Pro Kidboard rank #5, Vet C+1"
    assert '<span class="tx-rank"><span class="visually-hidden">board rank </span>#5</span>' in a
    assert 'title="Traded BOS ⇄ NYY"' in a, "players moved both ways"
    two = next(d for d in deals if "Board Two" in d)
    assert ">#50</span>" in two and 'title="Traded SEA → TEX"' in two
    assert sum(d.count('class="tx-rank"') for d in deals) == 2, "only board players carry a rank"


def test_the_trade_audit_link_rides_only_deals_with_a_board_player(tx_fake):
    page = _tx_home(tx_fake, TX_RECENT)
    deals = re.findall(_DEAL_RE, _tx_col(page, "trades"))
    audits = [re.search(r'<a class="tx-audit" href="([^"]+)">Trade Audit</a>', d) for d in deals]
    with_board = [d for d in deals if 'class="tx-rank"' in d]
    assert sum(1 for x in audits if x) == len(with_board) == 2
    hrefs = sorted(x.group(1) for x in audits if x)
    assert hrefs == ["/prospx/#tab=traded&amp;acq=trade&amp;q=Board%20Two",
                     "/prospx/#tab=traded&amp;acq=trade&amp;q=Pro%20Kid"]
    assert "tx-audit" not in next(d for d in deals if "Vet B" in d)


def test_roster_moves_are_the_last_week_of_four_types(tx_fake):
    page = _tx_home(tx_fake, TX_RECENT)
    moves = re.findall(r'<(?:a|div) class="tx-row"(?: href="[^"]*")? data-fam="(\w+)" data-type="(\w+)"'
                       r' title="([^"]*)"', _tx_col(page, "moves"))
    assert len(moves) == B._TX_MOVE_ROWS == 8
    assert {t for _f, t, _d in moves} <= set(B._TX_MOVE_TYPES)
    titles = [t for _f, _t, t in moves]
    assert not any("15-day" in t or "Old Dfa" in t or "recalled" in t for t in titles)
    # date first, then the weight: the claim (75) before the 60-day IL a day older
    assert titles[:2] == ["Texas Rangers claimed Claimed Guy.",
                          "Seattle Mariners placed RHP Sixty Day on the 60-day injured list."]
    assert {f for f, _t, _d in moves} == {"mlb", "inj"}
    assert '<span class="wire-val">60-day IL</span>' in page


def test_a_stale_log_draws_the_unmeasured_state(tx_fake):
    page = _tx_home(tx_fake, dict(TX_RECENT, through=_d(5)))
    for col in ("trades", "moves"):
        assert 'class="px-state is-unmeasured"' in _tx_col(page, col), col
    fresh = _tx_home(tx_fake, {"through": _d(1), "rows": []})
    assert "No roster moves in the last 7 days." in _tx_col(fresh, "moves")


def test_flag_off_keeps_recent_trades_and_never_builds_transactions(tx_fake, monkeypatch):
    monkeypatch.setattr(M, "MLB_EVENTS_LIVE", False)
    with_rows = _tx_home(tx_fake, TX_RECENT)

    def boom(*a, **k):
        raise AssertionError("the Transactions module is built with the flag off")
    monkeypatch.setattr(B, "_home_transactions", boom)
    assert _tx_home(tx_fake, {}) == with_rows, "flag off, recent.json is never read"
    assert "<h2>Recent Trades</h2>" in _band(with_rows, "pro")
    assert 'class="tx-mod"' not in with_rows and "<h2>Transactions</h2>" not in with_rows


# ---- the browser: the news is on screen, never in a drawer ------------------

_FIRST_ROW_JS = """() => {
  const el = document.querySelector('#wire-rows .feed-item');
  if (!el) return null;
  let e = el, hidden = false;
  while (e && e !== document.body) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden' || e.hidden) hidden = true;
    e = e.parentElement;
  }
  const r = el.getBoundingClientRect();
  return {top: r.top + scrollY, h: r.height, hidden, sw: document.documentElement.scrollWidth, iw: innerWidth};
}"""


@pytest.fixture(scope="module")
def browser_runs():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site
    out: dict = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        for width in (1280, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900})
            page = ctx.new_page()
            page.goto(base + "index.html", wait_until="load", timeout=30_000)
            out[f"row_{width}"] = page.evaluate(_FIRST_ROW_JS)
            if width == 1280:
                stops = []
                for _ in range(10):
                    page.keyboard.press("Tab")
                    stops.append(page.evaluate("() => document.activeElement.className || document.activeElement.tagName"))
                    if "skip-link" in stops[-1]:
                        page.keyboard.press("Enter")
                        page.keyboard.press("Tab")
                        stops.append(page.evaluate("() => !!document.activeElement.closest('main')"))
                        break
                out["tab"] = stops
                # the rail keeps its own scroller beside the page
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(200)
                out["rail_after_scroll"] = page.evaluate(
                    "() => Math.round(document.querySelector('.home-rail').getBoundingClientRect().top)")
            else:
                page.evaluate("document.getElementById('band-pro').scrollIntoView()")
                page.wait_for_timeout(200)
                out["jump_390"] = page.evaluate(
                    "() => Math.round(document.querySelector('.home-jump').getBoundingClientRect().top)")
            ctx.close()
        browser.close()
    return out


def test_first_news_row_is_on_screen_at_1280(browser_runs):
    r = browser_runs["row_1280"]
    assert r and not r["hidden"] and r["top"] + r["h"] <= 900, r
    assert r["sw"] == r["iw"]
    assert browser_runs["rail_after_scroll"] == 0


def test_first_news_row_is_in_the_page_at_390(browser_runs):
    r = browser_runs["row_390"]
    assert r and not r["hidden"] and r["top"] < 1100, r
    assert r["sw"] == r["iw"]
    assert browser_runs["jump_390"] == 0, "the jump bar sticks to the top on a phone"


def test_tab_order_reaches_main_within_ten_stops(browser_runs):
    stops = browser_runs["tab"]
    assert stops[-1] is True and len(stops) <= 10, stops


# ---- HOME_6: the Scores / Standings slot at the top of the MLB band ---------
# assets/home-scores.js run in V8 with no DOM (the test_scores_client.py
# harness) over a fixture of each state: games, postseason, off season and
# missing (plus a stale file). The strip links /scores/ in every drawn state.

import json

HS_SRC = (ROOT / "assets" / "home-scores.js").read_text(encoding="utf-8")
HS_DAY = 86_400_000
HS_NOW = 1791460800000 + 2 * 3_600_000   # 2026-10-08T14:00:00Z


@pytest.fixture(scope="module")
def hs():
    mr = pytest.importorskip("py_mini_racer")
    ctx = mr.MiniRacer()
    ctx.eval('var document = { readyState: "complete", getElementById: function () { return null; },'
             ' addEventListener: function () {} }; var window = {};')
    ctx.eval(HS_SRC)
    ctx.eval("""var HUB = { club: function (x) { return x ? { code: String(x) } : null; },
      teamLogo: function (code, cls, o) { return '<img class="' + cls + '" src="/x/' + code + '.png?s=' + o.size +
        '" alt="">'; } };""")
    return ctx


def _js(ctx, expr):
    return json.loads(ctx.eval(f"JSON.stringify({expr})"))


def _gen(ms):
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _latest(gen_ms=HS_NOW - 60_000, today="2026-10-08", n=2):
    return {"schema": 1, "generated_at": _gen(gen_ms), "today": today, "index_rev": "r",
            "job": {"down_after_s": 1800}, "live": [],
            "window": {today: {"n": n, "final": 0, "live": 0, "pre": n, "rev": "x"}}}


def _side(code, r=None):
    return {"code": code, "team_id": code, "short": code, "r": r, "wl": {"w": 1, "l": 0}}


def _game(pk, state, away="AAA", home="HHH"):
    return {"pk": pk, "state": state, "start": "2026-10-08T23:00:00Z", "tbd": False, "line": [], "flags": {},
            "away": _side(away, 3 if state != "scheduled" else None),
            "home": _side(home, 2 if state != "scheduled" else None),
            "sit": {"inning": 5, "half": "top", "outs": 1, "bases": [1, 0, 0]} if state == "live" else None}


BRACKET = {"done": False, "first": "2026-09-29", "last": "2026-10-31", "rounds": [
    {"name": "Division Series", "series": [{"id": "D_1", "lg": "AL", "over": True, "best_of": 5, "winner_id": 1,
        "text": "AAA wins 3-0", "clubs": [{"code": "AAA", "team_id": 1, "wins": 3}, {"code": "BBB", "team_id": 2, "wins": 0}]}]},
    {"name": "World Series", "series": [{"id": "W_1", "lg": "", "over": False, "best_of": 7, "winner_id": None,
        "text": "MIL leads 1-0", "clubs": [{"code": "MIL", "team_id": 158, "wins": 1}, {"code": "TBR", "team_id": 139, "wins": 0}]}]}]}
STANDINGS = {"as_of": "2026-09-27", "final": True, "rows": [
    {"code": "TBR", "div": "ALE", "w": 98, "l": 64, "qualified": "division", "ranks": {"div": 1}},
    {"code": "NYY", "div": "ALE", "w": 90, "l": 72, "qualified": "wc", "ranks": {"div": 2}},
    {"code": "MIL", "div": "NLC", "w": 103, "l": 59, "qualified": "division", "ranks": {"div": 1}}]}


def _state(ctx, L, ctx_in, now=HS_NOW):
    return _js(ctx, f"window.EephusHomeScores.slotState({json.dumps(L)}, {json.dumps(ctx_in)}, {now})")


def _html(ctx, S):
    return ctx.eval(f"window.EephusHomeScores.stateTrackHTML({json.dumps(S)}, HUB)")


def _suffix(ctx, S, L):
    return ctx.eval(f"window.EephusHomeScores.countSuffix({json.dumps(S)}, {json.dumps(L)}, {HS_NOW})")


def test_games_state_draws_line_scores_that_link_the_scores_page(hs):
    L = _latest()
    docs = {"2026-10-08": {"games": [_game(1, "live"), _game(2, "scheduled", "CCC", "DDD")]}}
    S = _state(hs, L, {"docs": docs})
    assert S["kind"] == "games"
    h = _html(hs, S)
    assert h.count('<li class="sp-strip-g') == 2
    assert re.findall(r'href="(/scores/#game=\d+)"', h) == ["/scores/#game=1", "/scores/#game=2"]
    assert "Top 5" in h and "<img" in h
    assert _suffix(hs, S, L) == "2 games today"


def test_postseason_state_draws_the_current_round_series(hs):
    L = _latest()
    S = _state(hs, L, {"docs": {}, "index": {"season": 2026, "bracket": BRACKET}})
    assert S["kind"] == "postseason" and S["round"]["name"] == "World Series"
    h = _html(hs, S)
    assert h.count('<li class="sp-strip-g') == 1
    assert 'href="/scores/#bracket=2026"' in h and "World Series" in h and "Best of 7" in h
    assert "MIL" in h and "TBR" in h and "Division" not in h
    assert _suffix(hs, S, L) == "World Series"
    # a finished bracket more than a week old is no longer the state
    old = dict(BRACKET, done=True, last="2026-09-20")
    S2 = _state(hs, L, {"docs": {}, "index": {"season": 2026, "bracket": old}, "standings": STANDINGS})
    assert S2["kind"] == "offseason"


def test_off_season_state_draws_the_division_leaders(hs):
    L = _latest(n=0)
    L["window"] = {"2026-10-08": {"n": 0, "final": 0, "live": 0, "pre": 0, "rev": None}}
    assert _js(hs, f"window.EephusHomeScores.needsStandings({json.dumps(L)}, {{}}, {HS_NOW})") is True
    S = _state(hs, L, {"docs": {}, "index": {"season": 2026, "bracket": None}, "standings": STANDINGS})
    assert S["kind"] == "offseason"
    h = _html(hs, S)
    assert h.count('<li class="sp-strip-g') == 2          # one leader per division in the file
    assert ">AL East<" in h and ">NL Central<" in h and "98-64" in h and "103-59" in h
    assert "Final" in h and "Sep 27" in h and 'href="/standings/"' in h
    assert _suffix(hs, S, L) == "final standings"


@pytest.mark.parametrize("why", ["missing", "wrong_schema", "stale", "no_standings"])
def test_missing_or_old_files_draw_the_unmeasured_state(hs, why):
    L = _latest(gen_ms=HS_NOW - 9 * HS_DAY) if why == "stale" else _latest(n=0)
    if why == "wrong_schema":
        L["schema"] = 2
    if why == "no_standings":
        L["window"] = {"2026-10-08": {"n": 0, "final": 0, "live": 0, "pre": 0, "rev": None}}
    arg = "null" if why == "missing" else json.dumps(L)
    S = _js(hs, f"window.EephusHomeScores.slotState({arg}, {{}}, {HS_NOW})")
    assert S["kind"] == "unmeasured"
    box = hs.eval(f"window.EephusHomeScores.unmeasuredHTML({json.dumps(S)}, 'Scores / Standings')")
    assert "is-unmeasured" in box and "Scores / Standings has no current data" in box
    assert 'href="/scores/"' in box
    if why == "stale":
        assert S["date"] == "2026-09-29" and "last updated Sep 29" in box
    if why in ("missing", "wrong_schema"):
        assert "last updated" not in box


def test_the_slot_sits_first_in_the_mlb_band_and_reads_the_name_constant(home):
    import scores_core
    if not scores_core.SCORES_LIVE:
        pytest.skip("SCORES_LIVE is False")
    mlb = _band(home, "mlb")
    body = mlb.split('<div class="band-head">', 1)[1].split("</div></div>", 1)[1]
    assert body.index('id="home-scores-slot"') < body.index('<nav class="club-logos"')
    slot = body.split('id="home-scores-slot">', 1)[1]
    assert slot.startswith("<link") and 'id="home-scoreboard"' in slot[:400]
    assert f'data-name="{B.SCORES_DISPLAY_NAME}"' in slot and 'href="/scores/"' in slot
    assert 'id="home-scores-state"' in slot
    assert 'id="home-mlb-count">' in mlb
    # the strip is no longer in the masthead block, and the script holds no literal module name
    assert 'id="home-scoreboard"' not in home.split('<nav class="home-jump"', 1)[0]
    assert "Scores / Standings" not in HS_SRC.split("(function () {", 1)[1]


def test_the_slot_is_absent_while_the_scores_module_is_off(monkeypatch):
    import scores_core
    monkeypatch.setattr(scores_core, "SCORES_LIVE", False)
    out = B.build_home([], {})
    assert "home-scoreboard" not in out and "home-mlb-count" not in out
    assert re.search(r'band-count">\d+ clubs<', out)
