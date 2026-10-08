# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB rows on the homepage rail and ticker (HOME_3, LANE_HOME 2.5).

Pinned here, on a fixture recent.json:
- no (mlbam, date, type code) twice on the rail, the ticker or /news/;
- one row per trade deal (date, unordered club pair, normalized description),
  up to two names then "+n", the board player first, then career WAR;
- the precedence rules: a StatsAPI deal or IL placement replaces the board's
  own row and keeps the PROSPX href, an FA module signing with terms absorbs a
  StatsAPI signing within 3 days, a prospect debut absorbs a callup up to 3
  days before it, rail-ineligible types (recall, optioned) stay off, a
  draft signing shows only for a board player;
- the caps: 20 rows, at most 6 per family per day except trades, date then
  weight, the off-season fill;
- the stale-log state: the rail prints recent.json's newest date and, when
  it is more than 2 days old, carries the unmeasured state for MLB, TRD, IL;
- flag off: the rail, ticker and script are the prospect wire, whatever
  recent.json holds.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pytest

import build_site as B
import mlb_events as M

TODAY = date.today()
D1 = (TODAY - timedelta(days=1)).isoformat()
D2 = (TODAY - timedelta(days=2)).isoformat()
D3 = (TODAY - timedelta(days=3)).isoformat()
D6 = (TODAY - timedelta(days=6)).isoformat()
NYY, BOS, SEA = 147, 111, 136
DEAL_A = "Boston Red Sox traded RHP Vet A and SS Pro Kid to New York Yankees for C Vet C."
DEAL_B = "Boston Red Sox traded LHP Vet B to New York Yankees for cash."


def _r(mlbam, day, typ, tx, key=None, name=None, frm=None, to=None, desc="", **kw):
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


ROWS = [
    # Deal A: three players on one transaction id, one row repeated in the cache.
    _r(10, D1, "trade", 900, "vet_a", "Vet A", BOS, NYY, DEAL_A),
    _r(10, D1, "trade", 900, "vet_a", "Vet A", BOS, NYY, DEAL_A),
    _r(20, D1, "trade", 900, None, "Pro Kid", BOS, NYY, DEAL_A),
    _r(40, D1, "trade", 900, "vet_c", "Vet C", NYY, BOS, DEAL_A),
    # Deal B: the same clubs on the same day, another deal.
    _r(11, D1, "trade", 901, "vet_b", "Vet B", BOS, NYY, DEAL_B),
    _r(20, D2, "il_place", 902, None, "Pro Kid", None, NYY,
       "New York Yankees placed SS Pro Kid on the 60-day injured list.", il="60-day IL"),
    _r(30, D1, "fa_sign", 903, "fa_guy_page", "Fa Guy", None, SEA,
       "Seattle Mariners signed free agent Fa Guy."),
    _r(21, D3, "callup", 904, "deb_kid_mlb", "Deb Kid", None, SEA, "SEA selected Deb Kid."),
    _r(23, D1, "callup", 905, "c23", "Call Up", None, SEA, "SEA selected Call Up."),
    _r(24, D1, "recall", 906, "r24", "Re Call", None, SEA, "SEA recalled Re Call."),
    _r(25, D1, "optioned", 907, "o25", "Opt Ed", SEA, None, "SEA optioned Opt Ed."),
    _r(22, D2, "draft_sign", 908, None, "Draft Kid", None, SEA, "SEA signed Draft Kid."),
    _r(300, D2, "draft_sign", 909, "nb300", "No Board", None, SEA, "SEA signed No Board."),
    # The FA module's own row in recent.json never reaches the wire twice.
    {"mlbam": 30, "name": "Fa Guy", "date": D2, "type": "fa_sign", "src": "fa_class",
     "key": "fa_guy_page", "to_team": "SEA"},
] + [
    # Eight DFAs on one day: the family cap keeps six.
    _r(100 + i, D3, "dfa", 910 + i, f"d{i}", f"Dfa {i}", SEA, None, f"SEA designated Dfa {i}.")
    for i in range(8)
] + [
    # Five single-player deals on one day between five club pairs: every deal shows.
    _r(200 + i, D2, "trade", 920 + i, f"t{i}", f"Trade {i}", 108 + i, 133 + i, f"deal {i}")
    for i in range(5)
]
RECENT = {"through": D1, "rows": ROWS}

PLAYERS = [
    {"player_key": "pro_kid", "mlbam_id": 20, "player_name": "Pro Kid", "org": "BOS",
     "overall_rank": 5,
     "trades": [{"trade_date": D1, "from_org": "BOS", "to_org": "NYY"}],
     "il_status": {"is_on_il": True, "since": D2, "type": "60-day"}},
    {"player_key": "draft_kid", "mlbam_id": 22, "player_name": "Draft Kid", "org": "SEA",
     "overall_rank": 50},
]
GRADS = [{"player_key": "deb_kid", "mlbam_id": 21, "player_name": "Deb Kid", "org": "SEA",
          "debut_date": D1}]
FA = [{"type": "signing", "key": "fa_guy", "date": D2, "name": "Fa Guy", "to": "SEA",
       "years": 2, "guar": 18e6}]
KEY_MLBAM = {"pro_kid": 20, "draft_kid": 22, "deb_kid": 21, "fa:fa_guy": 30}


@pytest.fixture
def fake(monkeypatch):
    orig = B._cached_data_json
    store = {"recent": RECENT}

    def f(name):
        if name == "player_links.json":
            return {"byKey": {"fa_guy": {"mlbam": 30}}}
        if name == "mlb_events/recent.json":
            return store["recent"]
        if name == "mlb_player_detail.json":
            return {"players": {"vet_a": {"career": [{"war": 5.0}]},
                                "vet_c": {"career": [{"war": 20.0}], "careerPit": [{"war": 10.0}]}}}
        if name == "fa_class.json":
            return {"events": FA}
        return orig(name)
    monkeypatch.setattr(B, "_cached_data_json", f)
    monkeypatch.setattr(B, "_save_wire_fv_ledger", lambda *a, **k: None)
    monkeypatch.setattr(M, "MLB_EVENTS_LIVE", True)
    return store


def _rail(recent=RECENT, today=TODAY):
    return B._collect_events(PLAYERS, GRADS, FA, mlb_recent=recent, today=today)


def _mlbam(e):
    k = e[4]
    if k in KEY_MLBAM:
        return KEY_MLBAM[k]
    m = {r.get("key"): r["mlbam"] for r in ROWS if r.get("key")}
    return m.get(k[4:] if k.startswith("mlb:") else k)


def test_no_player_date_type_twice_and_one_row_per_deal(fake):
    rows = _rail()
    keys = [(_mlbam(e), e[0], e[1]) for e in rows]
    assert len(keys) == len(set(keys)), keys
    trades = [e for e in rows if e[1] == "trade"]
    d1 = [e for e in trades if e[0] == D1]
    assert len(d1) == 2, "deal A and deal B share clubs and a day but are two deals"
    a = next(e for e in d1 if "Pro Kid" in e[6])
    # The board player leads, then career WAR (Vet C 30 over Vet A 5), then "+n".
    assert a[6] == "Pro Kid, Vet C +1" and a[7] == "BOS⇄NYY"
    assert a[4] == "pro_kid", "the deal keeps the PROSPX href"
    assert len([e for e in trades if e[0] == D2]) == 5, "every deal shows, no family cap"


def test_precedence_rules(fake):
    rows = _rail()
    ils = [e for e in rows if e[1] == "il_place"]
    assert [(e[0], e[4], e[7]) for e in ils] == [(D2, "pro_kid", "60-day IL")], \
        "the StatsAPI placement replaces il_status"
    signs = [e for e in rows if e[1] == "fa_sign"]
    assert [(e[0], e[4]) for e in signs] == [(D2, "fa:fa_guy")], \
        "the FA module's signing with terms absorbs the StatsAPI signing a day later"
    assert signs[0][7] == "2y/$18M"
    calls = [e[6] for e in rows if e[1] == "callup"]
    assert calls == ["Call Up"], "the debut absorbs Deb Kid's callup two days before it"
    assert any(e[1] == "debut" and e[4] == "deb_kid" for e in rows)
    types = {e[1] for e in rows}
    assert not types & {"recall", "optioned"}, "rail-ineligible types stay on /news/"
    drafts = [e[6] for e in rows if e[1] == "draft_sign"]
    assert drafts == ["Draft Kid"], "a draft signing shows for a board player only"


def test_caps_order_and_family_limit(fake):
    rows = _rail()
    assert len(rows) <= B._HOME_RAIL_ROWS
    assert [e[0] for e in rows] == sorted((e[0] for e in rows), reverse=True)
    per = {}
    for e in rows:
        fam = B._WIRE_TYPES[e[1]]["fam"]
        per[(e[0], fam)] = per.get((e[0], fam), 0) + 1
    assert per[(D3, "mlb")] == B._RAIL_FAM_DAY_CAP == 6, "eight DFAs in a day capped at six"
    assert all(n <= 6 for (d, f), n in per.items() if f != "trd")
    day1 = [e[1] for e in rows if e[0] == D1]
    # Inside a day, by weight: trade 100, debut 95, callup 70.
    w = [B._WIRE_TYPES[t]["weight"] for t in day1]
    assert w == sorted(w, reverse=True), day1
    assert day1[:3] == ["trade", "trade", "debut"]


def test_window_and_the_off_season_fill(fake):
    old = (TODAY - timedelta(days=40)).isoformat()
    rows = [_r(500 + i, old, "dfa", 990 + i, f"o{i}", f"Old {i}", SEA, None) for i in range(3)]
    out = _rail(recent={"through": old, "rows": rows})
    # Older than the window: the rail fills with the newest rows rather than emptying.
    assert any(e[0] == old for e in out)
    many = [_r(600 + i, D1, "trade", 2000 + i, f"m{i}", f"M {i}", 108 + i % 10, 133 + i % 10,
               f"many {i}") for i in range(25)]
    out = _rail(recent={"through": D1, "rows": many + rows})
    assert len(out) == B._HOME_RAIL_ROWS and all(e[0] >= D6 for e in out)


def _home(fake, recent):
    fake["recent"] = recent
    return B.build_home([], {"players": PLAYERS, "graduates": GRADS, "as_of": "2026-10-01"})


def _ticker_types(page):
    tk = page.split('class="ticker-track">')[1].split("</div></div>")[0]
    items = re.findall(r'<a href="([^"]*)" tabindex="-1" data-fam="\w+" data-type="(\w+)"', tk)
    return items[: len(items) // 2]


def test_home_rail_and_ticker_carry_the_mlb_rows_once(fake):
    page = _home(fake, RECENT)
    rail = page.split('id="wire-rows">')[1].split('id="wire-empty"')[0]
    rows = re.findall(r'<a class="feed-item[^"]*" href="([^"]*)" data-fam="(\w+)" data-type="(\w+)"', rail)
    assert len(rows) == len(_rail())
    assert sum(1 for r in rows if r[2] == "trade") == 7
    assert ("/projections/#player=c23", "mlb", "callup") in rows
    tk = _ticker_types(page)
    assert len(tk) == len(rows), "the ticker shows the rail's selection"
    assert len(tk) == len(set(tk))
    assert f"MLB moves through {D1[5:7]}/{D1[8:10]}" in page
    assert 'id="wire-stale"' not in page, "a log one day old is fresh"
    assert B._WIRE_RAIL_JS_LIVE in page


def test_news_page_keeps_one_player_date_type(fake):
    page = B.build_news({"players": PLAYERS, "graduates": GRADS})
    gfx = json.loads(re.search(r'id="news-gfx-data">(.*?)</script>', page, re.S).group(1))
    keys = [(it["mlbam"], it["date"], it["typ"]) for it in gfx if it.get("mlbam")]
    assert len(keys) == len(set(keys)), keys


def test_stale_log_draws_the_unmeasured_state(fake):
    d3 = date.fromisoformat(D3)
    page = _home(fake, dict(RECENT, through=D3))
    md = f"{d3.month:02d}/{d3.day:02d}"
    st = re.search(r'<div class="wire-stale" id="wire-stale" data-fams="mlb trd inj" hidden>'
                   r'<div class="px-state is-unmeasured">.*?<div class="px-state-msg">([^<]*)</div>',
                   page, re.S)
    assert st and st.group(1) == f"MLB moves through {md}: the transaction log has not refreshed since."
    assert f"As of 2026-10-01 · MLB moves through {md}</p>" in page
    assert B._wire_mlb_freshness({}, TODAY) == ("", "No MLB transaction log on this build.")
    assert B._wire_mlb_freshness({"through": D2}, TODAY)[1] == ""
    assert "staleFams.indexOf(cur)" in B._WIRE_RAIL_JS_LIVE


def test_flag_off_is_the_prospect_wire(fake, monkeypatch):
    monkeypatch.setattr(M, "MLB_EVENTS_LIVE", False)
    with_rows = _home(fake, RECENT)
    without = _home(fake, {})
    assert with_rows == without, "flag off, recent.json is never read"
    assert 'id="wire-stale"' not in with_rows and "MLB moves through" not in with_rows
    assert B._WIRE_RAIL_JS in with_rows and B._WIRE_RAIL_JS_LIVE not in with_rows
    assert '<p class="feed-asof">As of 2026-10-01</p>' in with_rows
    assert all(len(e) == 8 for e in B._collect_events(PLAYERS, GRADS, FA))
    assert len(_ticker_types(with_rows)) <= 14
