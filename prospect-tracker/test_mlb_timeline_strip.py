# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /projections/#player= Timeline strip (Q9_22b, wiring W01 part 2 of 3).

Pinned here:
- the dark path: while mlb_events.MLB_EVENTS_LIVE is False the page shell
  carries no data-mlb-events attribute, assets/projections.js requests nothing
  under /data/mlb_events/, and the player page has no timeline slot, so the
  served page is what it was before this lane;
- the live path (flag on, fixture payload): one request for the card's own
  MLBAM file, rows keyed by type code and family with the hidden family prefix,
  StatsAPI text verbatim and escaped, IL list and in-season days, trade and
  arbitration clubs through the hub's one club resolver, the season IL note,
  older seasons behind one disclosure, and quiet states for a missing file and a
  failed fetch;
- the type table covers every code the builder writes, each family is one of
  the five of plan 3.1, and each interim pictogram exists in the sprite.

The JS runs in py_mini_racer on the DOM stub of test_projections_smoke.py; the
module skips where py_mini_racer is unavailable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("py_mini_racer")

import test_projections_smoke as S  # noqa: E402

ROOT = Path(__file__).parent
JS_SRC = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")

# vet_guy's MLBAM id in the smoke fixture is 545361.
EVENTS = {
    "schema": 1, "mlbam": 545361, "key": "vet_guy", "name": "Vet Guy", "through": "2025-07-23",
    "il_seasons": {"2022": [30, 1]},
    "rows": [
        {"date": "2019-06-20", "type": "draft_sign", "src": "statsapi",
         "desc": "Boston Red Sox signed SS Vet Guy.", "tx": 1, "from": None, "to": 111},
        {"date": "2021-05-01", "type": "callup", "src": "statsapi",
         "desc": "Boston Red Sox selected the contract of SS Vet Guy from Worcester Red Sox.",
         "tx": 2, "from": 533, "to": 111},
        {"date": "2021-06-01", "type": "optioned", "src": "statsapi",
         "desc": "Boston Red Sox optioned SS Vet Guy to Worcester Red Sox.", "tx": 3, "from": 111, "to": 533},
        {"date": "2021-07-01", "type": "recall", "src": "statsapi",
         "desc": "Boston Red Sox recalled SS Vet Guy from Worcester Red Sox.", "tx": 4, "from": 533, "to": 111},
        {"date": "2022-06-01", "type": "il_place", "src": "statsapi",
         "desc": "Boston Red Sox placed SS Vet Guy on the 10-day injured list. Left hamstring strain & <soreness>.",
         "tx": 5, "from": None, "to": 111, "il": "10-day IL", "il_days": 30, "il_end": "2022-07-01"},
        {"date": "2022-07-01", "type": "il_return", "src": "statsapi",
         "desc": "Boston Red Sox activated SS Vet Guy from the 10-day injured list.", "tx": 6,
         "from": None, "to": 111, "il": "10-day IL"},
        {"date": None, "season": 2024, "type": "arb_salary", "src": "arb", "club": "BOS",
         "arb_year": 2, "salary_usd": 7825000},
        {"date": "2025-06-15", "type": "trade", "src": "statsapi",
         "desc": "Boston Red Sox traded SS Vet Guy to New York Yankees for RHP Some Arm.",
         "tx": 7, "from": 111, "to": 147, "deal": 7},
        {"date": "2025-07-02", "type": "dfa", "src": "statsapi",
         "desc": "New York Yankees designated SS Vet Guy for assignment.", "tx": 8, "from": None, "to": 147},
        {"date": "2025-07-05", "type": "claim", "src": "statsapi",
         "desc": "Seattle Mariners claimed SS Vet Guy off waivers from New York Yankees.",
         "tx": 9, "from": 147, "to": 136},
        {"date": "2025-07-20", "type": "fa_sign", "src": "fa_class", "key": "vet_guy",
         "to_team": "SEA", "years": 2, "guarantee_usd": 18000000, "aav_usd": 9000000},
    ],
}

# The hub's club resolver, reduced to the four clubs the fixture names. Minor
# league affiliates (533) resolve to nothing, as they do in eephus-hub.js.
HUB_CLUBS = """
var __CLUBS={111:'BOS',147:'NYY',136:'SEA',BOS:'BOS',NYY:'NYY',SEA:'SEA'};
EEPHUS_HUB.club=function(x){var c=__CLUBS[x];return c?{code:c}:null;};
EEPHUS_HUB.clubLinkHTML=function(x){var c=EEPHUS_HUB.club(x);
  return '<a class="club-link" href="/franchise/#team='+c.code+'" data-club="'+c.code+'"><span>'+c.code+'</span></a>';};
"""

_GETATTR = "if(k==='getAttribute')return function(){return null;};"


def _run(live: bool, payload=EVENTS) -> tuple[dict, list]:
    """Render #player=vet_guy; returns (innerHTML by id, fetched URLs).

    payload: a dict served at the card's events URL, 404 for a missing file,
    or "fail" for a network failure."""
    prelude = S._prelude("#player=vet_guy")
    assert _GETATTR in prelude, "the smoke test changed its element stub"
    prelude = prelude.replace(
        _GETATTR,
        "if(k==='getAttribute')return function(a){return (id==='proj-rows'&&a==='data-mlb-events')?__EVLIVE:null;};")
    url = "/data/mlb_events/545361.json"
    shim = (
        f"var __EVLIVE={json.dumps('live' if live else None)};"
        f"var __EV={{{json.dumps(url)}:{json.dumps(payload)}}};"
        "var __fetched=[];var __f0=fetch;"
        "fetch=function(u){__fetched.push(u);"
        " if(Object.prototype.hasOwnProperty.call(__EV,u)){var p=__EV[u];"
        "  if(p===404)return FT({ok:false,status:404,json:function(){return FT(null);}});"
        "  if(p==='fail')return {then:function(){return this;},catch:function(cb){cb(new Error('down'));return this;}};"
        "  return FT({ok:true,status:200,json:function(){return FT(p);}});}"
        " return __f0(u);};"
        "window.fetch=fetch;"
    )
    ctx = S.MiniRacer()
    ctx.eval("var __EVLIVE=null;" + prelude + shim + HUB_CLUBS + S.TIERS_JS + JS_SRC)
    return json.loads(ctx.eval("JSON.stringify(__html)")), json.loads(ctx.eval("JSON.stringify(__fetched)"))


def test_flag_off_requests_nothing_and_emits_no_slot():
    html, fetched = _run(live=False)
    assert not [u for u in fetched if "mlb_events" in u], fetched
    page = html["proj-rows"]
    assert "Vet Guy" in page, "the player page did not render"
    assert 'data-mlbp-slot="timeline"' not in page
    assert "mlbp-tl" not in page and "mlbp-slot-timeline" not in html


def test_flag_on_fetches_the_cards_own_file_once_into_its_slot():
    html, fetched = _run(live=True)
    assert [u for u in fetched if "mlb_events" in u] == ["/data/mlb_events/545361.json"]
    assert 'data-mlbp-slot="timeline"' in html["proj-rows"]
    tl = html.get("mlbp-slot-timeline", "")
    assert 'data-mlbp-section="timeline"' in tl and "MLB moves through Jul 23, 2025" in tl


def test_rows_key_by_type_and_family_with_the_hidden_prefix():
    tl = _run(live=True)[0]["mlbp-slot-timeline"]
    rows = re.findall(r'<li class="mlbp-tl-row" data-fam="([a-z]+)" data-type="([a-z_0-9]+)">(.*?)</li>', tl)
    assert len(rows) == len(EVENTS["rows"])
    fam = {t: f for f, t, _ in rows}
    assert fam == {"draft_sign": "pro", "callup": "mlb", "optioned": "mlb", "recall": "mlb",
                   "il_place": "inj", "il_return": "inj", "arb_salary": "fa", "trade": "trd",
                   "dfa": "mlb", "claim": "mlb", "fa_sign": "fa"}
    prefix = {"pro": "Prospect:", "mlb": "MLB:", "fa": "Free agency:", "trd": "Trade:", "inj": "Injury:"}
    for f, _t, body in rows:
        assert f'<span class="visually-hidden">{prefix[f]}</span>' in body
        assert '<use href="/assets/eephus-icons.svg#i-' in body
    # newest first: the signing leads, the draft signing closes the list
    assert rows[0][1] == "fa_sign" and rows[-1][1] == "draft_sign"


def test_statsapi_text_is_verbatim_and_escaped():
    tl = _run(live=True)[0]["mlbp-slot-timeline"]
    assert "Left hamstring strain &amp; &lt;soreness&gt;." in tl
    assert "<soreness>" not in tl
    assert "Boston Red Sox traded SS Vet Guy to New York Yankees for RHP Some Arm." in tl


def test_values_carry_il_days_trade_clubs_terms_and_arbitration():
    tl = _run(live=True)[0]["mlbp-slot-timeline"]
    assert "10-day IL · 30 in-season days" in tl
    trade = re.search(r'data-type="trade">.*?</li>', tl).group(0)
    assert 'data-club="BOS"' in trade and 'data-club="NYY"' in trade and "&rarr;" in trade
    claim = re.search(r'data-type="claim">.*?</li>', tl).group(0)
    assert 'claimed from <a class="club-link"' in claim and 'data-club="NYY"' in claim
    sign = re.search(r'data-type="fa_sign">.*?</li>', tl).group(0)
    assert "Free-agent signing" in sign and "2y/$18.0M" in sign and 'data-club="SEA"' in sign
    arb = re.search(r'data-type="arb_salary">.*?</li>', tl).group(0)
    assert "$7.8M · arb-2" in arb and 'data-club="BOS"' in arb and ">season<" in arb
    # an affiliate (533) is never linked to a guessed club
    opt = re.search(r'data-type="optioned">.*?</li>', tl).group(0)
    assert "club-link" not in opt and "data-club-nolink" not in opt


def test_seasons_group_with_the_il_note_and_older_seasons_fold():
    tl = _run(live=True)[0]["mlbp-slot-timeline"]
    assert "1 IL stint, 30 in-season days" in tl
    open_part, _, folded = tl.partition('<details class="mlbp-tl-more">')
    assert folded, "older seasons were not folded"
    years_open = re.findall(r'<div class="mlbp-tl-year">(\d{4})', open_part)
    years_folded = re.findall(r'<div class="mlbp-tl-year">(\d{4})', folded)
    assert years_open == ["2025", "2024", "2022", "2021"] and years_folded == ["2019"]
    assert "1 earlier move" in folded


def test_strip_draws_pins_and_il_bars_on_one_axis():
    tl = _run(live=True)[0]["mlbp-slot-timeline"]
    strip = re.search(r'<div class="mlbp-tl-strip" aria-hidden="true">.*?<div class="mlbp-tl-axis">(.*?)</div></div>', tl)
    assert strip, "no strip"
    assert re.findall(r">(\d{4})</span>", strip.group(1)) == ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
    pins = re.findall(r'class="mlbp-tl-pin[^"]*" data-fam="[a-z]+" data-type="([a-z_0-9]+)"', tl)
    assert sorted(pins) == sorted(r["type"] for r in EVENTS["rows"]
                                  if r["date"] and r["type"] not in ("il_place", "il_return"))
    assert len(re.findall(r'class="mlbp-tl-bar" data-fam="inj"', tl)) == 1


def test_missing_file_renders_nothing_and_a_failed_fetch_says_so():
    html, _ = _run(live=True, payload=404)
    assert html.get("mlbp-slot-timeline", "") == ""
    html, _ = _run(live=True, payload="fail")
    assert "The transaction timeline failed to load." in html.get("mlbp-slot-timeline", "")


def test_an_open_stint_reads_open_not_a_count_of_days_not_yet_played():
    """The builder closes a stint with no activation at its window's end (Oct 1);
    when the feed stops before that day the page says open through the feed's
    last day and prints no day count for that season."""
    row = {"date": "2025-07-10", "type": "il_place", "src": "statsapi",
           "desc": "New York Yankees placed SS Vet Guy on the 60-day injured list. Left calf strain.",
           "tx": 20, "from": None, "to": 147, "il": "60-day IL", "il_days": 83, "il_end": None}
    html, _ = _run(live=True, payload=dict(EVENTS, rows=[row], il_seasons={"2025": [83, 1]}))
    tl = html["mlbp-slot-timeline"]
    assert "60-day IL · open through Jul 23" in tl and "1 IL stint, 1 open" in tl
    assert "83" not in tl
    # the same stint once the feed has passed the window reads its days
    html, _ = _run(live=True, payload=dict(EVENTS, rows=[row], il_seasons={"2025": [83, 1]},
                                           through="2025-10-30"))
    assert "60-day IL · 83 in-season days" in html["mlbp-slot-timeline"]


def test_an_il_bar_stops_at_its_season_window():
    """A stint the builder closes with a placement two seasons later (no
    activation on file) draws to Oct 1 of its own season, not across years."""
    rows = [{"date": "2018-09-24", "type": "il_place", "src": "statsapi",
             "desc": "Baltimore Orioles placed RF Vet Guy on the 60-day disabled list. Right ankle surgery.",
             "tx": 30, "from": None, "to": 110, "il": "60-day DL", "il_days": 7, "il_end": "2020-08-15"},
            {"date": "2020-08-15", "type": "il_place", "src": "statsapi",
             "desc": "Baltimore Orioles placed RF Vet Guy on the 10-day injured list.",
             "tx": 31, "from": None, "to": 110, "il": "10-day IL", "il_days": 30, "il_end": "2020-09-14"}]
    tl = _run(live=True, payload=dict(EVENTS, rows=rows, il_seasons={}, through="2020-09-30"))[0]["mlbp-slot-timeline"]
    bars = re.findall(r'class="mlbp-tl-bar"[^>]*style="left:([\d.]+)%;width:([\d.]+)%" title="([^"]*)"', tl)
    assert len(bars) == 2, bars
    (_l0, w0, t0), (_l1, w1, t1) = bars
    assert t0 == "60-day DL, Sep 24, 2018" and float(w0) < 1.0
    assert t1 == "10-day IL, Aug 15, 2020 to Sep 14, 2020"


def test_no_rows_reads_as_none_on_file():
    html, _ = _run(live=True, payload=dict(EVENTS, rows=[], il_seasons={}))
    assert "No MLB transactions on file." in html["mlbp-slot-timeline"]


def test_type_table_covers_the_builder_and_the_sprite():
    import mlb_events
    body = re.search(r"const TL_TYPES = \{(.*?)\n  \};", JS_SRC, re.S).group(1)
    table = dict((k, (f, i)) for k, f, i in
                 re.findall(r'(\w+):\s*\{ fam: "(\w+)",\s*ico: "([\w-]+)"', body))
    assert set(mlb_events.TYPE_CODES) <= set(table), set(mlb_events.TYPE_CODES) - set(table)
    sprite = (ROOT / "assets" / "eephus-icons.svg").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="i-([a-z0-9-]+)"', sprite))
    for code, (fam, ico) in table.items():
        assert fam in {"pro", "mlb", "fa", "trd", "inj"}, code
        assert ico in ids, (code, ico)


def test_the_shell_attribute_follows_the_one_flag(monkeypatch):
    import build_site as B
    import mlb_events
    assert mlb_events.MLB_EVENTS_LIVE is False, "a build commit never sets the flag"
    assert "data-mlb-events" not in B.build_projections()
    monkeypatch.setattr(mlb_events, "MLB_EVENTS_LIVE", True)
    assert re.search(r'<div id="proj-rows"[^>]* data-mlb-events="live"', B.build_projections())
