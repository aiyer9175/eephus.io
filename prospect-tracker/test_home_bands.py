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
"""
from __future__ import annotations

import inspect
import re
from datetime import date
from pathlib import Path

import pytest

import build_site as B

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
    for needle in ('id="home-scores-slot"', '<nav class="club-logos"', ">Free Agency<",
                   "MLB Projections<", "Leaders<", "Trade Machine<", "Alchemy Lab<",
                   'class="xmod-card xmod-strip-card"', ">Diamond Pass<", "FG pts"):
        assert needle in mlb, needle
    for needle in ('<nav class="band-links"', 'class="home-module spot-module"', "<h2>Top Prospects</h2>",
                   "<h2>Top Movers</h2>", "<h2>Recent Debuts</h2>", "<h2>Top Farm Systems</h2>",
                   "Prospect History", "<h2>eFV Distribution</h2>", "CollegeSavant<", "Park Factors<",
                   "<h2>Recent Trades</h2>", 'id="draft-war-room-banner"'):
        assert needle in pro, needle
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
    row = re.search(r'<nav class="club-logos"[^>]*>(.*?)</nav>', home, re.S).group(1)
    codes = re.findall(r'href="/franchise/#view=club&amp;team=([A-Z]{2,3})"', row)
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
