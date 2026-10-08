# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB rows on /news/ and /history/ and the /fa/ IL column (Q9_22c, wiring W01
part 3 of 3).

Pinned here:
- the builder additions: il_recent (in-season IL days of the last three
  seasons, an open stint stopped at the feed's last day, the per-player files'
  il_seasons rule unchanged), on_this_day (one month file per season, one row
  per person, date and type) and the page key and both clubs on recent rows;
- /news/: MLB veterans' trades, IL placements and major-league signings join
  the feed only while mlb_events.MLB_EVENTS_LIVE is True, deduplicated by the
  site-pass plan 3.5 item 3 (a deal is one row with up to two names then "+n",
  a StatsAPI trade or IL placement replaces the board's own row and keeps the
  PROSPX href, an FA module signing absorbs a StatsAPI signing within 3 days,
  a player with no page is left out), StatsAPI text verbatim and escaped;
- /history/: the On This Day rename and the Debuts, Trades, Signings,
  Injuries sections with the MLB rows, a ledger row the MLB log also carries
  folded by transaction id;
- /fa/: the IL days column, its sort key and detail line only while the shell
  says the feed is live, in Chromium (skips without playwright).
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import date
from pathlib import Path

import pytest

import build_site as B
import mlb_events as M

ROOT = Path(__file__).parent
NYY, BOS, SEA, AFF = 147, 111, 136, 531


def _tx(tid, pid, day, code, desc, frm=None, to=None, name=None):
    t = {"id": tid, "date": day, "typeCode": code, "description": desc}
    if pid is not None:
        t["person"] = {"id": pid, "fullName": name or f"Player {pid}"}
    if frm is not None:
        t["fromTeam"] = {"id": frm}
    if to is not None:
        t["toTeam"] = {"id": to}
    return t


def _cache(tmp_path, months: dict) -> Path:
    d = tmp_path / "tx"
    d.mkdir(parents=True, exist_ok=True)
    for (y, m), rows in months.items():
        with gzip.open(M.tx_path(y, m, d), "wt", encoding="utf-8") as fh:
            json.dump({"transactions": rows}, fh)
    return d


# --------------------------------------------------------------------------
# the builder additions
# --------------------------------------------------------------------------

def test_the_three_seasons_turn_over_on_the_first_window_day():
    assert M.il_recent_seasons(date(2026, 10, 8)) == [2024, 2025, 2026]
    assert M.il_recent_seasons(date(2027, 1, 15)) == [2024, 2025, 2026]
    assert M.il_recent_seasons(date(2027, 3, 31)) == [2024, 2025, 2026]
    assert M.il_recent_seasons(date(2027, 4, 1)) == [2025, 2026, 2027]


def test_il_recent_counts_in_season_days_and_stops_an_open_stint(tmp_path):
    rows25 = [_tx(1, 10, "2025-05-01", "SC", "NYY placed X on the 10-day injured list.", None, NYY),
              _tx(2, 10, "2025-05-21", "SC", "NYY activated X from the 10-day injured list.", None, NYY)]
    rows26 = [_tx(3, 10, "2026-06-01", "SC", "NYY placed X on the 60-day injured list.", None, NYY)]
    rows23 = [_tx(4, 11, "2023-06-01", "SC", "BOS placed Y on the 15-day injured list.", None, BOS),
              _tx(5, 11, "2023-06-20", "SC", "BOS activated Y from the 15-day injured list.", None, BOS)]
    tx = _cache(tmp_path, {(2023, 6): rows23, (2025, 5): rows25, (2026, 6): rows26})
    r = M.build(tx_dir=tx, as_of=date(2026, 6, 11), players={10: {"key": "x"}, 11: {"key": "y"}},
                links={}, fa_events=[], arb=[], draft={}, mlb_ids=M.MLB_TEAM_IDS)
    il = r["index"]["il_recent"]
    assert il["seasons"] == [2024, 2025, 2026]
    # 20 days in 2025; the open 2026 stint counts Jun 1 to Jun 11, the feed's last day.
    assert il["days"] == {"10": [0, 20, 11]}
    # The per-player files keep the il_table.json rule: an open stint runs to Oct 1.
    assert r["players"][10]["il_seasons"]["2026"] == [122, 1]


def test_on_this_day_reads_the_month_and_keeps_one_row_per_person(tmp_path):
    deal = "New York Yankees traded RHP A to Boston Red Sox for LHP B."
    rows24 = [_tx(900, 1, "2024-12-10", "TR", deal, NYY, BOS, "A Arm"),
              _tx(900, 2, "2024-12-10", "TR", deal, BOS, NYY, "B Bat"),
              _tx(900, 2, "2024-12-10", "TR", deal, BOS, NYY, "B Bat"),
              _tx(901, 3, "2024-12-10", "SFA", "Seattle Mariners signed free agent C Cat.", None, SEA, "C Cat"),
              _tx(902, 4, "2024-12-10", "SFA", "Seattle Mariners signed free agent D to a minor league contract.",
                  None, SEA),
              _tx(903, 5, "2024-12-10", "TR", "An affiliate swap.", AFF, 532),
              _tx(904, 6, "2024-12-11", "TR", "Next day.", NYY, BOS)]
    rows25 = [_tx(950, 7, "2025-12-10", "TR", "Boston Red Sox traded E to Seattle Mariners.", BOS, SEA, "E Eye")]
    rows26 = [_tx(990, 8, "2026-12-10", "TR", "Too new.", BOS, SEA)]
    tx = _cache(tmp_path, {(2024, 12): rows24, (2025, 12): rows25, (2026, 12): rows26,
                           (2025, 11): [_tx(960, 9, "2025-11-10", "TR", "Other month.", BOS, SEA)]})
    out = M.on_this_day(12, 10, before_year=2026, tx_dir=tx, mlb_ids=M.MLB_TEAM_IDS)
    assert [(r["date"], r["type"], r["mlbam"]) for r in out] == [
        ("2025-12-10", "trade", 7), ("2024-12-10", "fa_sign", 3),
        ("2024-12-10", "trade", 1), ("2024-12-10", "trade", 2)]
    assert out[0]["desc"] == "Boston Red Sox traded E to Seattle Mariners."
    assert (out[0]["from"], out[0]["to"], out[0]["tx"], out[0]["name"]) == (BOS, SEA, 950, "E Eye")


def test_recent_rows_carry_the_page_key_and_both_clubs(tmp_path):
    tx = _cache(tmp_path, {(2026, 9): [
        _tx(1, 10, "2026-09-20", "TR", "Boston Red Sox traded X to New York Yankees.", BOS, NYY, "X"),
        _tx(2, 11, "2026-09-21", "SC", "NYY placed Y on the 10-day injured list.", None, NYY, "Y")]})
    r = M.build(tx_dir=tx, as_of=date(2026, 9, 30), players={10: {"key": "x_page", "name": "X"}},
                links={}, fa_events=[], arb=[], draft={}, mlb_ids=M.MLB_TEAM_IDS)
    rows = {x["mlbam"]: x for x in r["recent"]["rows"]}
    assert rows[10]["key"] == "x_page" and (rows[10]["from"], rows[10]["to"]) == (BOS, NYY)
    assert "key" not in rows[11] and "from" not in rows[11] and rows[11]["to"] == NYY


# --------------------------------------------------------------------------
# /news/
# --------------------------------------------------------------------------

DEAL = "Boston Red Sox traded RHP Vet A and SS Pro Kid to New York Yankees for C Vet C."
RECENT = {"rows": [
    {"mlbam": 10, "name": "Vet A", "date": "2026-07-30", "type": "trade", "clubs": [BOS, NYY],
     "from": BOS, "to": NYY, "desc": DEAL, "tx": 900, "deal": 900, "key": "vet_a"},
    {"mlbam": 20, "name": "Pro Kid", "date": "2026-07-30", "type": "trade", "clubs": [BOS, NYY],
     "from": BOS, "to": NYY, "desc": DEAL, "tx": 900, "deal": 900},
    {"mlbam": 40, "name": "Vet C", "date": "2026-07-30", "type": "trade", "clubs": [NYY, BOS],
     "from": NYY, "to": BOS, "desc": DEAL, "tx": 900, "deal": 900, "key": "vet_c"},
    {"mlbam": 20, "name": "Pro Kid", "date": "2026-07-29", "type": "il_place", "clubs": [NYY],
     "to": NYY, "desc": "New York Yankees placed SS Pro Kid on the 60-day injured list. Torn <UCL> & more.",
     "tx": 901, "il": "60-day IL"},
    {"mlbam": 50, "name": "No Page", "date": "2026-07-29", "type": "il_place", "clubs": [NYY],
     "to": NYY, "desc": "New York Yankees placed No Page on the 10-day injured list.", "tx": 902, "il": "10-day IL"},
    {"mlbam": 30, "name": "Fa Guy", "date": "2026-07-20", "type": "fa_sign", "clubs": [SEA],
     "to": SEA, "desc": "Seattle Mariners signed free agent Fa Guy.", "tx": 903, "key": "fa_guy_page"},
    {"mlbam": 60, "name": "Vet F", "date": "2026-07-25", "type": "fa_sign", "clubs": [SEA],
     "to": SEA, "desc": "Seattle Mariners signed free agent Vet F.", "tx": 904, "key": "vet_f"},
    {"mlbam": 61, "name": "Vet G", "date": "2026-07-25", "type": "fa_sign", "src": "fa_class",
     "to_team": "SEA", "key": "vet_g"},
    {"mlbam": 62, "name": "Vet H", "date": "2026-07-25", "type": "recall", "clubs": [AFF, NYY],
     "desc": "NYY recalled Vet H.", "tx": 905, "key": "vet_h"},
]}
BOARD_TRADE = ("2026-07-30", "trade", "⇄", "Pro Kid traded BOS→NYY", "pro_kid", "NYY", "Pro Kid", "BOS→NYY")
BOARD_IL = ("2026-07-28", "il_place", "✚", "Pro Kid to 60-day IL", "pro_kid", "NYY", "Pro Kid", "60-day IL")
OTHER = ("2026-07-30", "promo", "↑", "Some Kid promoted AA→AAA", "some_kid", "SEA", "Some Kid", "AA→AAA")


def _merge(monkeypatch, recent=RECENT):
    def fake(name):
        if name == "player_links.json":
            return {"byKey": {"fa_guy": {"mlbam": 30}}}
        if name == "mlb_events/recent.json":
            return recent
        return {}
    monkeypatch.setattr(B, "_cached_data_json", fake)
    data = {"players": [{"player_key": "pro_kid", "mlbam_id": 20}, {"player_key": "some_kid", "mlbam_id": 70}],
            "graduates": []}
    fa = [{"type": "signing", "key": "fa_guy", "date": "2026-07-21", "name": "Fa Guy"}]
    return B._news_mlb_merge([BOARD_TRADE, OTHER, BOARD_IL], data, fa)


def test_news_merge_groups_the_deal_and_replaces_the_board_rows(monkeypatch):
    merged, info = _merge(monkeypatch)
    trades = [e for e in merged if e[1] == "trade"]
    assert len(trades) == 1, "a deal is one row and the board's own trade row goes"
    t = trades[0]
    # Board player first, then up to two names and "+n"; both directions read as a swap.
    assert t[6] == "Pro Kid, Vet A +1" and t[7] == "BOS⇄NYY"
    assert t[4] == "pro_kid", "the deal keeps the PROSPX href of its board player"
    assert info[t]["descs"] == [DEAL] and info[t]["mlbam"] == 20
    ils = [e for e in merged if e[1] == "il_place"]
    assert [(e[0], e[4], e[7]) for e in ils] == [("2026-07-29", "pro_kid", "60-day IL")], ils
    assert OTHER in merged


def test_news_merge_absorbs_fa_signings_and_drops_rows_without_a_page(monkeypatch):
    merged, info = _merge(monkeypatch)
    signs = [e for e in merged if e[1] == "fa_sign"]
    assert [(e[0], e[4], e[5], e[7]) for e in signs] == [("2026-07-25", "mlb:vet_f", "SEA", "MLB deal")]
    names = {e[6] for e in merged}
    assert "Fa Guy" not in names, "the FA module's signing absorbs the StatsAPI row within 3 days"
    assert "No Page" not in names and "Vet G" not in names and "Vet H" not in names
    assert [e[0] for e in merged] == sorted((e[0] for e in merged), reverse=True)
    assert merged.index(OTHER) < merged.index(next(e for e in merged if e[1] == "trade")), \
        "prospect rows keep the head of their day"


def test_news_merge_without_rows_is_the_feed_unchanged(monkeypatch):
    merged, info = _merge(monkeypatch, recent={})
    assert merged == [BOARD_TRADE, OTHER, BOARD_IL] and info == {}


def _news(monkeypatch, live: bool) -> str:
    monkeypatch.setattr(M, "MLB_EVENTS_LIVE", live)
    monkeypatch.setattr(B, "_save_wire_fv_ledger", lambda *a, **k: None)
    _merge(monkeypatch)
    data = {"players": [{"player_key": "pro_kid", "mlbam_id": 20, "player_name": "Pro Kid", "org": "NYY",
                         "trades": [{"trade_date": "2026-07-30", "from_org": "BOS", "to_org": "NYY"}]}],
            "graduates": []}
    monkeypatch.setattr(B, "_news_recent_events", lambda ev, **k: ev)
    return B.build_news(data)


def test_news_page_flag_off_serves_no_mlb_row(monkeypatch):
    html = _news(monkeypatch, live=False)
    assert "StatsAPI" not in html and "MLB transactions" not in html and "Vet A" not in html
    assert "debuts, trades, level moves, IL, eFV changes, FA signings and options" in html


def test_news_page_flag_on_prints_statsapi_text_verbatim(monkeypatch):
    html = _news(monkeypatch, live=True)
    assert ('<span class="section-sub">MLB and MiLB transactions · eFV moves · FA · last 30 days</span>'
            in html)
    meta = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert meta == "MLB and MiLB transactions, debuts, IL moves, eFV changes and FA signings, filterable by type."
    assert "quotes its StatsAPI text" in html
    esc = "New York Yankees placed SS Pro Kid on the 60-day injured list. Torn &lt;UCL&gt; &amp; more."
    assert f'<span class="news-meta">{esc}</span>' in html
    assert f'title="{esc}"' in html
    row = re.search(r'<a class="feed-item news-item" href="([^"]*)" data-fam="fa" data-type="fa_sign"', html)
    assert row and row.group(1) == "/projections/#player=vet_f"
    assert html.count('data-type="trade"') == 1
    gfx = json.loads(re.search(r'id="news-gfx-data">(.*?)</script>', html, re.S).group(1))
    assert any(it.get("mlbam") == 60 and it["typ"] == "fa_sign" for it in gfx)


def test_mlb_page_keys_route_to_the_projections_page():
    assert B._player_href("mlb:juan_soto") == "/projections/#player=juan_soto"
    assert B._player_href("fa:x") == "/fa/#player=x" and B._player_href("pro") == "/prospx/#player=pro"


# --------------------------------------------------------------------------
# /history/
# --------------------------------------------------------------------------

def _history(monkeypatch, live: bool) -> str:
    today = date.today()
    mmdd = f"{today.month:02d}-{today.day:02d}"
    y = today.year - 2
    day = f"{y}-{mmdd}"
    monkeypatch.setattr(M, "MLB_EVENTS_LIVE", live)
    monkeypatch.setattr(B, "_cached_data_json", lambda name: (
        {"players": {"vet_a": {"key": "vet_a", "mlbam": 10}}} if name == "mlb_player_detail.json" else {}))
    tx = {mmdd: [(day, "TR", "pro_kid", "New York Yankees", False, 900),
                 (day, "SGN", "pro_two", "Boston Red Sox", False, 77)]}
    monkeypatch.setattr(B, "_load_history_db", lambda: (tx, {}))
    rows = [{"date": day, "type": "trade", "mlbam": 10, "name": "Vet A", "from": BOS, "to": NYY,
             "desc": DEAL, "tx": 900},
            {"date": day, "type": "trade", "mlbam": 20, "name": "Pro Kid", "from": BOS, "to": NYY,
             "desc": DEAL, "tx": 900},
            {"date": day, "type": "fa_sign", "mlbam": 99, "name": "No Page", "from": None, "to": SEA,
             "desc": "Seattle Mariners signed free agent No Page.", "tx": 950}]
    monkeypatch.setattr(M, "on_this_day", lambda *a, **k: rows)
    data = {"players": [{"player_key": "pro_kid", "mlbam_id": 20, "player_name": "Pro Kid", "fv_close": 50},
                        {"player_key": "pro_two", "mlbam_id": 21, "player_name": "Pro Two"}],
            "graduates": [{"player_key": "grad_a", "mlbam_id": 10, "player_name": "Vet A",
                           "trades": [{"source": "mlb_api", "trade_date": day,
                                       "from_org": "BOS", "to_org": "NYY"}]}]}
    return B.build_this_day(data)


def test_history_flag_off_is_the_prospect_page(monkeypatch):
    html = _history(monkeypatch, live=False)
    assert "Today in Prospect History - " in html and "On This Day" not in html
    assert "<h2>Signings &amp; free agency on this day</h2>" in html
    assert "Pro Kid, Vet A" not in html and "StatsAPI" not in html
    assert html.count('class="otd-row otd-trade"') == 1, "the graduate's own trade row only"


def test_history_flag_on_is_on_this_day_with_the_mlb_rows(monkeypatch):
    html = _history(monkeypatch, live=True)
    assert "<title>On This Day - eephus.io</title>" in html
    assert re.search(r"</svg>On This Day - [A-Z][a-z]+ \d+</h1>", html)
    heads = re.findall(r'<div class="kicker"><h2>([^<]+)</h2>', html)
    assert heads == ["Trades", "Signings"], heads
    # The ledger's TR row rides the MLB deal (same transaction id) and the
    # graduate's own trade row goes (same player, same day): one trade row.
    trades = html.split("<h2>Trades</h2>")[1].split("</section>")[0]
    assert trades.count('class="otd-row otd-trade"') == 1
    assert "<strong>Pro Kid, Vet A</strong>" in trades
    assert 'href="/prospx/#player=pro_kid"' in trades, "a board player keeps the PROSPX href"
    assert f'title="{DEAL}"' in trades
    signs = html.split("<h2>Signings</h2>")[1].split("</section>")[0]
    assert "Pro Two" in signs and "No Page" in signs
    assert '<div class="otd-row" data-fam="fa" data-type="fa_sign">' in signs, "no page, no link"
    assert "the earliest on this date: " in html


def test_history_label_follows_the_flag_at_import():
    assert B._HISTORY_LABEL == (B.HISTORY_LABEL_LIVE if M.MLB_EVENTS_LIVE else "Today in Prospect History")
    assert B.PAGE_LABELS["/history/"] == B._HISTORY_LABEL == B.PAGE_INDEX_NAMES["/history/"]


# --------------------------------------------------------------------------
# /fa/ IL days, last three seasons (Chromium)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


@pytest.fixture(scope="module")
def server():
    from conftest import serve_site
    with serve_site() as base:
        yield base


def _fa_members():
    cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
    links = json.loads((ROOT / "data" / "player_links.json").read_text(encoding="utf-8"))["byKey"]
    out = []
    for m in cls["members"]:
        mid = m.get("mlbam") or (links.get(m["key"]) or {}).get("mlbam")
        if mid:
            out.append((m["key"], int(mid)))
    return out


def _fa_board(browser, server, live: bool, width: int = 1440):
    if not (ROOT / "fa" / "index.html").exists() or not (ROOT / "data" / "fa_class.json").exists():
        pytest.skip("the /fa/ page or its class payload is not built")
    members = _fa_members()
    a, b = members[0], members[1]
    index = {"il_recent": {"seasons": [2024, 2025, 2026], "days": {str(a[1]): [10, 0, 5], str(b[1]): [0, 0, 300]}}}
    shell = (ROOT / "fa" / "index.html").read_text(encoding="utf-8")
    shell = re.sub(r' data-mlb-events="live"', "", shell)
    if live:
        shell = shell.replace('<div id="fa-rows" class="fa-hold"', '<div id="fa-rows" class="fa-hold" data-mlb-events="live"', 1)
    page = browser.new_page(viewport={"width": width, "height": 900})
    fetched, errors = [], []
    page.on("request", lambda r: fetched.append(r.url))
    page.on("pageerror", lambda e: errors.append(e.message))
    page.route("**/fa/", lambda route: route.fulfill(status=200, content_type="text/html", body=shell))
    page.route("**/data/mlb_events/index.json",
               lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(index)))
    page.goto(server + "fa/", wait_until="load", timeout=20_000)
    page.wait_for_selector(".fa-board-table tbody tr[data-key]", timeout=20_000)
    return page, fetched, errors, a, b


def test_fa_flag_off_draws_no_column_and_fetches_nothing(browser, server):
    page, fetched, errors, _a, _b = _fa_board(browser, server, live=False)
    try:
        assert page.locator(".fc-il").count() == 0
        assert not [u for u in fetched if "mlb_events" in u]
        assert page.locator('#fa-sort-sel option[value="ilDays"]').count() == 0
    finally:
        page.close()
    assert not errors, errors


def test_fa_flag_on_draws_the_column_sorts_and_folds(browser, server):
    page, fetched, errors, a, b = _fa_board(browser, server, live=True)
    try:
        assert [u for u in fetched if "mlb_events" in u][:1] == [server + "data/mlb_events/index.json"]
        th = page.locator("thead th.fc-il")
        assert th.count() == 1 and th.is_visible()
        assert "2024 to 2026" in th.locator("button").get_attribute("title")
        cell = page.locator(f'tr[data-key="{a[0]}"] td.fc-il')
        assert cell.inner_text().strip() == "15"
        assert "2024: 10, 2025: 0, 2026: 5" in cell.locator("span").get_attribute("title")
        page.click('button[data-fsort="ilDays"]')
        page.wait_for_timeout(100)
        first = page.locator(".fa-board-table tbody tr[data-key]").first.get_attribute("data-key")
        assert first == b[0], "IL days sorts high first"
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_timeout(100)
        assert not page.locator("thead th.fc-il").is_visible(), "the IL column folds first"
        page.click(f'tr[data-key="{a[0]}"] .fa-xp-btn')
        detail = page.locator(f"#fad-{a[0]}").inner_text()
        assert "IL DAYS" in detail.upper() and "2026: 5" in detail
        n_head = page.evaluate("document.querySelectorAll('.fa-board-table thead th').length")
        n_det = page.evaluate(f"document.querySelector('#fad-{a[0]}').children.length")
        # The detail row spans exactly the header's columns (pad per foldable column).
        assert n_det + 4 + 2 == n_head, (n_det, n_head)
    finally:
        page.close()
    assert not errors, errors
