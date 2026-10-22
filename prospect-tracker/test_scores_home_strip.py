# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SCORES_7d (owner SC7-6, SC7-7): the homepage scoreboard strip.

assets/home-scores.js executed in V8 with no DOM (the test_scores_client.py
harness): the order is live, then today's games still to start, then the
latest day's finals; with nothing live or to come the latest finals show; the
strip is hidden when the latest final is more than 7 days old or the latest
file is not the job's; a slate more than a day behind the reader is a past
day. It polls every 60 s while a game is live, every 300 s while a game is to
start, never otherwise. Each game is a real link to its /scores/ game page,
nothing in the strip is aria-hidden, and the club marks are the hub's
decorative pixel chips beside the printed code.

build_home: the mount sits in the MLB band's slot (HOME_6), hidden, with the 'Scores'
tag linking /scores/, the hub named by a stamped data-hub, and the strip
script stamped and deferred; none of it renders while SCORES_LIVE is False.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).resolve().parent
SRC = (ROOT / "assets" / "home-scores.js").read_text(encoding="utf-8")

_STUB = r"""
var document = { readyState: "complete", getElementById: function () { return null; },
  addEventListener: function () {} };
var window = {};
"""

DAY = 86_400_000
TODAY = "2026-10-08"
NOW = 1791460800000 + 2 * 3_600_000   # 2026-10-08T14:00:00Z


@pytest.fixture(scope="module")
def v8():
    mr = pytest.importorskip("py_mini_racer")
    ctx = mr.MiniRacer()
    ctx.eval(_STUB)
    ctx.eval(SRC)
    ctx.eval("""var HUB = { club: function (x) { return x ? { code: String(x) } : null; },
      teamLogo: function (code, cls, o) { return '<img class="' + cls + '" src="/x/' + code + '.png?s=' + o.size +
        '" alt="' + (o.decorative ? "" : code) + '" onerror="this.remove()">'; } };""")
    return ctx


def call(ctx, expr):
    return json.loads(ctx.eval(f"JSON.stringify({expr})"))


def side(code, r=None, w=1, l=0):
    return {"code": code, "team_id": code, "short": code, "r": r, "h": None, "e": None, "wl": {"w": w, "l": l}}


def card(pk, state, start, away="AAA", home="HHH", ar=None, hr=None, **kw):
    c = {"pk": pk, "state": state, "start": start, "tbd": False, "away": side(away, ar), "home": side(home, hr),
         "line": kw.pop("line", []), "flags": kw.pop("flags", {}), "sit": kw.pop("sit", None)}
    c.update(kw)
    return c


def latest(today=TODAY, live=(), window=None, gen_ms=NOW - 60_000):
    import datetime as dt
    gen = dt.datetime.fromtimestamp(gen_ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"schema": 1, "generated_at": gen, "today": today, "index_rev": "r",
            "job": {"down_after_s": 1800}, "live": list(live), "window": window or {}}


def plan(ctx, L, docs, now=NOW):
    return call(ctx, f"window.EephusHomeScores.plan({json.dumps(L)}, {json.dumps(docs)}, {now})")


def pks(p, key):
    return [c["pk"] for c in p[key]]


# ---- the plan --------------------------------------------------------------

def test_live_then_upcoming_then_the_latest_finals(v8):
    docs = {
        TODAY: {"games": [
            card(3, "scheduled", "2026-10-08T23:05:00Z"),
            card(1, "live", "2026-10-08T17:05:00Z", ar=2, hr=1, sit={"inning": 5, "half": "top", "outs": 1, "bases": [1, 0, 0]}),
            card(4, "pregame", "2026-10-08T20:10:00Z"),
            card(2, "delayed", "2026-10-08T16:05:00Z", ar=0, hr=0, sit={"inning": 3, "half": "bottom", "outs": 0, "bases": [0, 0, 0]}),
        ]},
        "2026-10-07": {"games": [card(8, "final", "2026-10-07T23:00:00Z", ar=1, hr=4),
                                 card(7, "final", "2026-10-07T17:00:00Z", ar=5, hr=2),
                                 card(9, "postponed", "2026-10-07T18:00:00Z")]},
    }
    p = plan(v8, latest(live=[{"pk": 1, "date": TODAY}, {"pk": 2, "date": TODAY}]), docs)
    assert p["show"] is True
    assert pks(p, "live") == [2, 1]           # by first pitch
    assert pks(p, "upcoming") == [4, 3]
    assert pks(p, "finals") == [7, 8] and p["finalsDate"] == "2026-10-07"


def test_todays_finals_are_the_latest_finals(v8):
    docs = {TODAY: {"games": [card(1, "final", "2026-10-08T17:05:00Z", ar=3, hr=2),
                              card(2, "scheduled", "2026-10-08T23:05:00Z")]},
            "2026-10-07": {"games": [card(8, "final", "2026-10-07T23:00:00Z", ar=1, hr=4)]}}
    p = plan(v8, latest(), docs)
    assert pks(p, "upcoming") == [2] and pks(p, "finals") == [1] and p["finalsDate"] == TODAY


def test_nothing_live_or_to_come_shows_the_latest_finals(v8):
    docs = {"2026-10-03": {"games": [card(5, "final", "2026-10-03T20:00:00Z", ar=1, hr=0)]}}
    p = plan(v8, latest(), docs)
    assert p["show"] is True and p["live"] == [] and p["upcoming"] == []
    assert pks(p, "finals") == [5] and p["finalsDate"] == "2026-10-03"


def test_a_final_more_than_seven_days_old_hides_the_strip(v8):
    docs = {"2026-09-30": {"games": [card(5, "final", "2026-09-30T20:00:00Z", ar=1, hr=0)]}}
    p = plan(v8, latest(), docs)
    assert p["show"] is False and p["finals"] == []
    # seven days old still shows
    docs = {"2026-10-01": {"games": [card(5, "final", "2026-10-01T20:00:00Z", ar=1, hr=0)]}}
    assert plan(v8, latest(), docs)["show"] is True


def test_upcoming_games_show_without_a_recent_final(v8):
    docs = {TODAY: {"games": [card(2, "scheduled", "2026-10-08T23:05:00Z")]}}
    p = plan(v8, latest(), docs)
    assert p["show"] is True and pks(p, "upcoming") == [2] and p["finals"] == []


@pytest.mark.parametrize("bad", [None, {}, {"schema": 2, "today": TODAY, "window": {}},
                                 {"schema": 1, "today": "today", "window": {}},
                                 {"schema": 1, "today": TODAY}])
def test_a_file_that_is_not_the_jobs_hides_the_strip(v8, bad):
    p = plan(v8, bad, {TODAY: {"games": [card(1, "scheduled", "2026-10-08T23:05:00Z")]}})
    assert p["show"] is False


def test_a_past_days_slate_shows_no_live_or_upcoming_rows(v8):
    old = "2026-10-05"
    docs = {old: {"games": [card(1, "live", "2026-10-05T17:05:00Z", ar=1, hr=0, sit={"inning": 2, "half": "top"}),
                            card(2, "scheduled", "2026-10-05T23:05:00Z"),
                            card(3, "final", "2026-10-05T16:05:00Z", ar=2, hr=1)]}}
    p = plan(v8, latest(today=old, live=[{"pk": 1, "date": old}]), docs)
    assert p["live"] == [] and p["upcoming"] == [] and pks(p, "finals") == [3]


def test_the_poll_cadence(v8):
    def poll(p):
        return v8.eval(f"window.EephusHomeScores.pollMs({json.dumps(p)})")
    base = {"show": True, "live": [], "upcoming": [], "finals": []}
    assert poll(dict(base, live=[{}])) == 60000
    assert poll(dict(base, upcoming=[{}])) == 300000
    assert poll(dict(base, finals=[{}])) == 0
    assert poll(dict(base, show=False)) == 0


def test_the_dates_read_are_today_the_live_dates_and_the_latest_window_final(v8):
    w = {"2026-10-07": {"n": 4, "final": 4, "rev": "a"}, TODAY: {"n": 1, "final": 0, "rev": "b"},
         "2026-10-09": {"n": 0, "final": 0, "rev": None}, "2026-10-10": {"n": 1, "final": 0, "rev": "c"}}
    got = call(v8, f"window.EephusHomeScores.datesToRead({json.dumps(latest(window=w))})")
    assert got == {TODAY: "b", "2026-10-07": "a"}
    assert call(v8, f"window.EephusHomeScores.windowFinalDate({json.dumps(latest(window=w))})") == "2026-10-07"
    idx = {"dates": [{"d": "2026-09-26", "n": 15, "rev": "x"}, {"d": "2026-09-27", "n": 15, "rev": "y"},
                     {"d": "2026-10-07", "n": 4, "rev": "a"}]}
    assert call(v8, f"window.EephusHomeScores.indexDateBefore({json.dumps(idx)}, '2026-10-07')")["d"] == "2026-09-27"


# ---- the words ---------------------------------------------------------------

def test_the_kickers(v8):
    def k(c, p=None):
        return call(v8, f"window.EephusHomeScores.kicker({json.dumps(c)}, {json.dumps(p)})")
    assert k(card(1, "live", "x", sit={"inning": 7, "half": "bottom", "outs": 2, "bases": [1, 0, 1]})) == "Bot 7"
    assert k(card(1, "live", "x", sit={"inning": 1, "half": "top", "outs": 0})) == "Top 1"
    assert k(card(1, "delayed", "x", sit={"inning": 4, "half": "top"})) == "Delayed, Top 4"
    assert k(card(1, "delayed", "x")) == "Delayed start"
    assert k(card(1, "final", "x", line=[[0, 0]] * 9)) == "Final"
    assert k(card(1, "final", "x", line=[[0, 0]] * 11, flags={"extra_innings": True})) == "Final/11"
    assert k(card(1, "scheduled", "x", tbd=True)) == "Time TBA"
    assert re.fullmatch(r"\d{1,2}:\d{2}\s?[AP]M.*", k(card(1, "scheduled", "2026-10-08T23:05:00Z")))
    stale = {"stale": True, "asOf": NOW}
    assert k(card(1, "live", "x", sit={"inning": 2, "half": "top"}), stale).startswith("Top 2, as of ")
    sit = call(v8, "window.EephusHomeScores.situation(" + json.dumps(
        card(1, "live", "x", sit={"inning": 7, "half": "bottom", "outs": 2, "bases": [1, 0, 1]})) + ")")
    assert sit == "2 out, 1st 3rd"


def test_every_game_is_a_real_link_to_its_game_page(v8):
    docs = {TODAY: {"games": [card(11, "live", "2026-10-08T17:05:00Z", "CLE", "CHW", 2, 1,
                                   sit={"inning": 5, "half": "top", "outs": 1, "bases": [0, 0, 0]}),
                              card(12, "scheduled", "2026-10-08T23:05:00Z", "LAD", "ATL")]},
            "2026-10-07": {"games": [card(13, "final", "2026-10-07T20:00:00Z", "TBR", "NYY", 4, 3,
                                          line=[[0, 0]] * 9)]}}
    p = plan(v8, latest(), docs)
    html = v8.eval(f"window.EephusHomeScores.trackHTML({json.dumps(p)}, HUB)")
    assert re.findall(r'href="([^"]+)"', html) == ["/scores/#game=11", "/scores/#game=12", "/scores/#game=13"]
    assert "aria-hidden" not in html and "tabindex" not in html
    # the pixel chip, decorative beside the printed code, removed on error
    imgs = re.findall(r"<img [^>]+>", html)
    assert len(imgs) == 6 and all('class="sp-logo"' in i and 'alt=""' in i and "onerror" in i for i in imgs)
    assert all("?s=40" in i for i in imgs)   # SC7-8: fetched at twice the 20 px box, never pixelated
    for code in ("CLE", "CHW", "LAD", "ATL", "TBR", "NYY"):
        assert f">{code}</span>" in html
    # the finals' day carries its own label; the winner is set bold, the loser dim
    assert '<li class="sp-strip-day"><span>Wed</span><span>Oct 7</span></li>' in html
    fin = html.split('class="sp-strip-day"', 1)[1]
    assert 'sp-strip-tm is-w"' in fin and 'sp-strip-tm is-l"' in fin
    # with no hub the codes stand alone
    bare = v8.eval(f"window.EephusHomeScores.trackHTML({json.dumps(p)}, null)")
    assert "<img" not in bare and ">CLE</span>" in bare


def test_the_strip_carries_no_dash_or_banned_word():
    assert "—" not in SRC and "–" not in SRC


# ---- the shell ---------------------------------------------------------------

def _mount(page: str) -> str:
    m = re.search(r'<section class="sp-strip" id="home-scoreboard"[^>]*>.*?</section>', page, re.S)
    assert m, "the scoreboard mount is missing"
    return m.group(0)


def test_the_shell_is_a_hidden_mount_at_the_top_of_the_mlb_band():
    import scores_core
    if not scores_core.SCORES_LIVE:
        pytest.skip("SCORES_LIVE is False")
    out = B.build_home([], {})
    mount = _mount(out)
    assert " hidden" in mount.split(">", 1)[0] and 'aria-label="Scores"' in mount
    assert '<a class="sp-strip-tag" href="/scores/">Scores</a>' in mount
    assert '<ul class="sp-strip-track"></ul>' in mount
    assert f'data-hub="/assets/eephus-hub.js?v={B._asset_ver("assets/eephus-hub.js")}"' in mount
    assert f'<script src="/assets/home-scores.js?v={B._asset_ver("assets/home-scores.js")}" defer></script>' in out
    assert f'href="/assets/sports-page.css?v={B._asset_ver("assets/sports-page.css")}"' in out
    # HOME_6: the strip left the masthead block for the first slot of the MLB band
    head = out.split('<div class="home-head">', 1)[1].split('<nav class="home-jump"', 1)[0]
    assert 'id="home-scoreboard"' not in head
    band = out.split('id="band-mlb"', 1)[1]
    assert band.index('id="home-scores-slot"') < band.index('id="home-scoreboard"') < band.index('<nav class="club-logos"')
    # the news ticker is untouched and still first
    assert out.index('<div class="home-ticker"') < out.index('id="home-scoreboard"')


def test_no_strip_while_the_scores_module_is_off(monkeypatch):
    import scores_core
    monkeypatch.setattr(scores_core, "SCORES_LIVE", False)
    out = B.build_home([], {})
    assert "home-scoreboard" not in out and "home-scores.js" not in out
