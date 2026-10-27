# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Trade Audit's REALIZED leg (owner answer M9, 2026-09-25).

The audit card prices every party at today's trade value. This leg adds what each club
actually got after the trade: the WAR a player produced for the club that received him from
the trade date, from per-stint season WAR on the displayed eWAR v2 basis, priced at the same
$/WAR the trade value uses, shown beside the value-today verdict and labelled realized to
date with the as-of date. Players with no MLB time contribute zero and keep their
value-today figure.

Contract pinned here (data/trade_realized.json, trade_realized_export.py, prospx
_taRealizedWar):
  * a player traded mid-season credits each club only its own stint, and a player with no
    stint with the sender that season credits every stint with the receiver;
  * seasons before the trade year are never credited;
  * the credits reconcile to the player's season WAR (per-stint rows sum to the season
    total served in war_seasons.json);
  * the $/WAR is the trade value's own (calibration dpw_level_usd);
  * the realized leg never enters the value-today total or verdict;
  * the served Transactions tab renders the leg on every card.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import pytest
from conftest import load_data_doc, serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
sys.path.insert(0, str(ROOT))
import trade_realized_export as tre  # noqa: E402


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _artifact():
    doc = load_data_doc("trade_realized.json")
    if not doc or not doc.get("players"):
        pytest.skip("data/trade_realized.json not built")
    return doc


# ---------------------------------------------------------------------------
# 1. Wiring: the leg is read from its own artifact and never enters the verdict
# ---------------------------------------------------------------------------

def test_the_leg_never_enters_the_value_today_total():
    body = _function_source(_src(), "renderRecentlyTraded")
    for needle in ("g.aReceived = ", "g.bReceived = ", "g.netDeltaA = "):
        line = next(ln for ln in body.splitlines() if needle in ln)
        assert "rz" not in line.lower() and "realized" not in line.lower(), line
    assert "_taVerdict(g.netDeltaA, pendingCount, BALANCED_THRESHOLD_MM)" in body
    assert "_taRealizedWar(rzDoc" in body and "_taRealizedLoad()" in body
    assert "trade_value_lo" not in body and "trade_value_hi" not in body, (
        "the audit must never sum a quantile point")


def test_the_page_reads_its_own_artifact():
    body = _function_source(_src(), "_taRealizedLoad")
    assert 'trade_realized.json' in body


def test_the_artifact_is_catalogued_and_pinned_here():
    import data_catalog as dc
    row = next((a for a in dc.ARTIFACTS if a["file"] == "trade_realized.json"), None)
    assert row and row["pinned_by"] == Path(__file__).name


def test_the_rebuild_path_writes_the_artifact_after_the_board():
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i_slim = rm.find('write_slim_sidecar(out_dir / "trade_values.json")')
    i_rz = rm.find("_export_trade_realized(out_path=out_dir")
    assert 0 <= i_slim < i_rz, "the realized export reads the board the rebuild just wrote"


# ---------------------------------------------------------------------------
# 2. The crediting rule, in V8, on fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval(_function_source(_src(), "_taRealizedWar"))
    return ctx


def _credit(js, rows_by_player, mlbam, date, frm, to):
    doc = {"players": rows_by_player}
    return json.loads(js.eval("JSON.stringify(_taRealizedWar(%s, %s, %s, %s, %s))" % (
        json.dumps(doc), json.dumps(mlbam), json.dumps(date), json.dumps(frm), json.dumps(to))))


# Patrick Bailey's 2026 as the stint frame carries it: SFG stint 1, then CLE stint 2.
BAILEY = {"672275": [
    [2025, "SFG", 1, 0, 1.11],
    [2026, "SFG", 1, 0, -0.33],
    [2026, "CLE", 2, 0, 1.22],
    [2027, "CLE", 1, 0, 2.0],
]}


def test_a_mid_season_trade_credits_each_club_only_its_stint(js):
    to_cle = _credit(js, BAILEY, 672275, "2026-07-30", "SFG", "CLE")
    assert to_cle["war"] == pytest.approx(1.22 + 2.0)
    assert [s["season"] for s in to_cle["seasons"]] == [2026, 2027] and to_cle["mlb"]
    # The reverse direction (CLE to SFG, were it traded back) credits SFG nothing from 2026:
    # its stint came BEFORE the CLE stint, and the 2027 season has no SFG row.
    back = _credit(js, BAILEY, 672275, "2026-07-30", "CLE", "SFG")
    assert back["war"] == 0 and not back["mlb"]


def test_both_clubs_stints_add_back_to_the_season_total(js):
    total_2026 = -0.33 + 1.22
    a = _credit(js, {"1": [r for r in BAILEY["672275"] if r[0] == 2026]}, 1, "2026-01-01", None, "SFG")
    b = _credit(js, {"1": [r for r in BAILEY["672275"] if r[0] == 2026]}, 1, "2026-01-01", None, "CLE")
    assert a["war"] + b["war"] == pytest.approx(total_2026)


def test_seasons_before_the_trade_are_never_credited(js):
    got = _credit(js, BAILEY, 672275, "2027-02-01", "SFG", "CLE")
    assert [s["season"] for s in got["seasons"]] == [2027] and got["war"] == pytest.approx(2.0)
    # an offseason trade after the 2025 season: his 2025 stint with the sender is not CLE's
    off = _credit(js, BAILEY, 672275, "2025-12-10", "SFG", "CLE")
    assert [s["season"] for s in off["seasons"]] == [2026, 2027]
    assert off["war"] == pytest.approx(1.22 + 2.0)


def test_no_stint_with_the_sender_credits_every_stint_with_the_receiver(js):
    rows = {"7": [[2024, "ATH", 1, 1, 0.5], [2024, "ATH", 2, 1, 0.25]]}
    got = _credit(js, rows, 7, "2024-03-01", "NYY", "ATH")
    assert got["war"] == pytest.approx(0.75)


def test_two_way_player_credits_both_sides(js):
    rows = {"9": [[2025, "LAA", 1, 0, 1.0], [2025, "LAD", 2, 0, 6.0], [2025, "LAD", 1, 1, 1.5]]}
    got = _credit(js, rows, 9, "2025-01-15", "LAA", "LAD")
    assert got["war"] == pytest.approx(7.5)


def test_no_mlb_time_is_zero_not_missing(js):
    for doc_rows, mlbam in (({}, 5), ({"5": []}, 5), ({"6": [[2026, "BOS", 1, 0, 1.0]]}, 5), ({"5": [[2026, "BOS", 1, 0, 1.0]]}, None)):
        got = _credit(js, doc_rows, mlbam, "2026-01-01", "NYY", "BOS")
        assert got["war"] == 0 and got["seasons"] == [] and got["mlb"] is False
    # a player whose only MLB rows are with a third club earns zero for the receiver
    got = _credit(js, {"5": [[2026, "SEA", 1, 0, 3.0]]}, 5, "2026-01-01", "NYY", "BOS")
    assert got["war"] == 0 and got["mlb"] is False


# ---------------------------------------------------------------------------
# 3. The artifact reconciles to the served season WAR and to the trade value's $/WAR
# ---------------------------------------------------------------------------

def test_stint_rows_sum_to_the_served_season_war():
    art = _artifact()
    seasons = load_data_doc("war_seasons.json")
    if not seasons or not seasons.get("players"):
        pytest.skip("data/war_seasons.json not built")
    served = seasons["players"]
    compared = multi = 0
    worst = 0.0
    for mlbam, rows in art["players"].items():
        blob = served.get(mlbam)
        if not blob:
            continue
        by_season: dict[int, list] = {}
        for r in rows:
            by_season.setdefault(r[0], []).append(r)
        for srow in blob[1]:
            season, war_bat, war_pit = srow[0], srow[1], srow[2]
            mine = by_season.get(season)
            if not mine:
                continue
            want = (war_bat or 0.0) + (war_pit or 0.0)
            got = sum(r[4] for r in mine)
            worst = max(worst, abs(got - want))
            compared += 1
            multi += len({r[1] for r in mine}) > 1
            assert abs(got - want) <= 0.0006 * len(mine) + 0.002, (mlbam, season, got, want)
    assert compared > 1000 and multi > 50, (compared, multi)


def test_a_player_traded_mid_season_credits_his_clubs_the_season_total(js):
    art = _artifact()
    checked = 0
    for mlbam, rows in art["players"].items():
        by_season: dict[int, list] = {}
        for r in rows:
            by_season.setdefault(r[0], []).append(r)
        for season, mine in by_season.items():
            clubs = {r[1] for r in mine}
            if len(clubs) < 2:
                continue
            season_rows = {mlbam: mine}
            per_club = sum(_credit(js, season_rows, mlbam, f"{season}-01-01", None, c)["war"] for c in clubs)
            assert per_club == pytest.approx(sum(r[4] for r in mine), abs=0.002), (mlbam, season)
            checked += 1
        if checked >= 60:
            break
    assert checked >= 20, checked


def test_the_dollars_per_war_is_the_trade_values_own():
    art = _artifact()
    board = load_data_doc("trade_values.json")
    if not board:
        pytest.skip("data/trade_values.json not built")
    dpw = board["calibration"]["dpw_level_usd"]
    assert art["dollars_per_war_mm"] * 1e6 == pytest.approx(dpw, abs=1.0)
    # the displayed WAR basis: eWAR v3 since the display flip (it read ewar_v2 before)
    import war_source
    assert art["war_provider"] == war_source.DISPLAY_PROVIDER, "the displayed WAR basis"
    assert art["fields"] == tre.FIELDS and art["n_players"] == len(art["players"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", art["as_of"])


# ---------------------------------------------------------------------------
# 4. The exporter
# ---------------------------------------------------------------------------

def _frame(rows):
    return [dict(zip(("mlb_ID", "year_ID", "team_ID", "stint_ID", "WAR"), r)) for r in rows]


def test_build_players_keeps_board_players_canonical_clubs_and_the_floor():
    nan = float("nan")
    bat = _frame([
        (1, 2025, "SFG", 1, 0.5), (1, 2025, "CLE", 2, 0.25),
        (1, 2005, "SFG", 1, 9.0),        # before the first season
        (2, 2024, "OAK", 1, 1.0),        # canonical club code
        (3, 2024, "NYY", 1, 4.0),        # not on the board
        (4, 2024, "NYY", 1, nan),        # no WAR
    ])
    pit = _frame([(1, 2025, "SFG", 1, 0.125)])
    out = tre.build_players({"bat": bat, "pit": pit}, {1, 2, 4})
    assert out == {
        1: [[2025, "SFG", 1, 0, 0.5], [2025, "SFG", 1, 1, 0.125], [2025, "CLE", 2, 0, 0.25]],
        2: [[2024, "ATH", 1, 0, 1.0]],
    }


def test_export_refuses_a_dead_read_and_keeps_the_previous_file(tmp_path):
    board = tmp_path / "trade_values.json"
    board.write_text(json.dumps({"players": [{"mlbam_id": 1}]}), encoding="utf-8")
    out = tmp_path / "trade_realized.json"
    out.write_text('{"keep": true}', encoding="utf-8")
    n = tre.export(out_path=out, board_path=board, log=lambda *_: None,
                   frames={"bat": _frame([(1, 2025, "SFG", 1, 0.5)]), "pit": _frame([])})
    assert n == 0 and json.loads(out.read_text(encoding="utf-8")) == {"keep": True}


def test_export_writes_beside_the_board_it_was_given(tmp_path, monkeypatch):
    monkeypatch.setattr(tre, "MIN_PLAYERS", 1)
    board = tmp_path / "trade_values.json"
    board.write_text(json.dumps({"players": [{"mlbam_id": 1}, {"mlbam_id": None}]}), encoding="utf-8")
    real = ROOT / "data" / "trade_realized.json"
    before = real.stat().st_mtime_ns if real.exists() else None
    n = tre.export(board_path=board, out_path=tmp_path / "trade_realized.json", today="2026-10-08",
                   log=lambda *_: None,
                   frames={"bat": _frame([(1, 2025, "SFG", 1, 0.5)]), "pit": _frame([])})
    doc = json.loads((tmp_path / "trade_realized.json").read_text(encoding="utf-8"))
    assert n == 1 and doc["players"] == {"1": [[2025, "SFG", 1, 0, 0.5]]}
    assert doc["as_of"] == "2026-10-08" and doc["fields"] == tre.FIELDS
    assert (real.stat().st_mtime_ns if real.exists() else None) == before, (
        "a redirected run wrote the served artifact")


# ---------------------------------------------------------------------------
# 5. The served Transactions tab
# ---------------------------------------------------------------------------

_CARDS = """() => [...document.querySelectorAll('.trade-audit-card')].map(c => {
  const z = c.querySelector('.ta-realized');
  return {
    text: (c.innerText || '').replace(/\\s+/g, ' '),
    verdict: c.getAttribute('data-ta-verdict'), net: c.getAttribute('data-ta-net'),
    rz: z ? { state: z.getAttribute('data-ta-rz'), verdict: z.getAttribute('data-ta-rz-verdict'),
              net: z.getAttribute('data-ta-rz-net'), a: z.getAttribute('data-ta-rz-a'),
              b: z.getAttribute('data-ta-rz-b'), text: (z.innerText || '').replace(/\\s+/g, ' ') } : null,
    chips: [...c.querySelectorAll('[data-ta-kind]')].map(s => ({
      kind: s.getAttribute('data-ta-kind'), mm: s.getAttribute('data-ta-mm'),
      rwar: s.getAttribute('data-ta-rwar'), mlbam: s.getAttribute('data-ta-mlbam'),
      title: s.getAttribute('title') || ''})),
  };
})"""


def test_served_audit_cards_carry_the_realized_leg():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    art = _artifact()
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        fetched: list[str] = []
        page.on("request", lambda r: fetched.append(r.url.split("?")[0].rsplit("/", 1)[-1]))
        page.goto(base + "prospx/index.html#tab=traded&acq=trade", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => { const c = document.querySelectorAll('.trade-audit-card');"
            " return c.length > 5 && ![...c].some(x => x.getAttribute('data-ta-verdict') === 'pending')"
            " && ![...document.querySelectorAll('.ta-realized')].some(z => z.getAttribute('data-ta-rz') !== 'ready'); }",
            timeout=180_000)
        cards = page.evaluate(_CARDS)
        browser.close()
    assert not errs, errs[:3]
    assert "trade_realized.json" in fetched
    assert len(cards) > 20
    credited = 0
    for c in cards:
        z = c["rz"]
        assert z and z["state"] == "ready", c["text"][:160]
        assert "realized to date" in z["text"].lower() and f"through {art['as_of']}" in z["text"]
        assert z["verdict"] in ("orgA", "orgB", "balanced", "none"), z
        assert c["verdict"] in ("orgA", "orgB", "balanced"), "the value-today verdict is untouched"
        rw = [float(ch["rwar"]) for ch in c["chips"] if ch["rwar"] not in ("", None)]
        assert len(rw) == len(c["chips"]), "every party carries a realized figure, zero included"
        assert abs(float(z["a"]) + float(z["b"]) - sum(rw)) < 0.01
        if z["verdict"] == "none":
            assert all(r == 0 for r in rw) and "No MLB time since the trade" in z["text"]
        for ch in c["chips"]:
            if not ch["mlbam"] or ch["mlbam"] not in art["players"]:
                assert float(ch["rwar"]) == 0, ch
            if float(ch["rwar"]) != 0:
                credited += 1
                assert "Realized to date" in ch["title"] and "WAR for" in ch["title"], ch
    assert credited > 20, f"only {credited} credited chips on the served audit; the check proved little"
