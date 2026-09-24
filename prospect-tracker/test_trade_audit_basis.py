# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX Transactions Trade Audit prices every party in the Trade Machine's currency.

WHY THIS EXISTS (census M02-01 and M08-07, 2026-09-24, five verifiers CONFIRMED). The
audit priced an MLB player at career WAR x $/WAR ($11.74M) and a prospect at his baked
engine surplus, then summed both into one net. Career WAR counts seasons before the trade
and at other clubs, and the same total was credited again in every trade a player appeared
in. So the card named "ARI +$701.7M" for Nolan Arenado (Trade Machine: $3.8M), "CHC
+$431.1M" for Kevin Gausman ($0.9M) and "PHI +$199.2M" for Luis Arraez ($0.3M). The
mlb_trade_players sidecar meant to price veterans never loaded (its guard saw the {} set
just before it and returned).

Contract pinned here:
  * no audit value is career WAR x $/WAR; the dead sidecar loader is gone;
  * every party is priced at trade_values.json trade_value_mm (the posterior expected
    surplus, never its lo/hi band), by key first, then by an accent- and initial-folded
    name narrowed to the two clubs;
  * a party with no trade value is unpriced, left out of both totals, and the card names
    no winner; while the prices load the card names no winner either;
  * on the served page every priced chip equals its trade_value_mm.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest
from conftest import load_data_doc, serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _render_traded_src() -> str:
    return _function_source(_src(), "renderRecentlyTraded")


def _trade_values():
    doc = load_data_doc("trade_values.json")
    if not doc or not doc.get("players"):
        pytest.skip("data/trade_values.json not built")
    return doc


# ---------------------------------------------------------------------------
# 1. Wiring
# ---------------------------------------------------------------------------

def test_no_career_war_dollar_path_in_the_audit():
    body = _render_traded_src()
    for dead in ("_WAR_DOLLAR_VALUE", "war_vet", "surplus_mm", "mlb_trade_players",
                 "_mlbVets", "playerSurplusMM("):
        assert dead not in body, f"the Trade Audit still reads {dead}"
    assert not re.search(r"career_?[wW]ar\s*\*", body), "an audit value multiplies career WAR"
    assert "_ensureMlbTradePlayersLoaded" not in _src(), "the dead sidecar loader is back"


def test_every_party_goes_through_the_one_pricer():
    body = _render_traded_src()
    assert body.count("_taPriceParty(_TA_TV.idx") == 2, (
        "tracked rows and narrative-named players must both price through _taPriceParty")
    assert "_taVerdict(g.netDeltaA, unknownCount, pendingCount, BALANCED_THRESHOLD_MM)" in body
    assert "_taTradeValuesLoad()" in body
    assert "trade_value_lo" not in body and "trade_value_hi" not in body, (
        "the audit must never sum a quantile point")


# ---------------------------------------------------------------------------
# 2. The pricer in V8, against the served trade values
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    doc = _trade_values()
    src = _src()
    ctx = mr.MiniRacer()
    for fn in ("_taFold", "_taBuildIndex", "_taPriceParty", "_taVerdict", "_taMM"):
        ctx.eval(_function_source(src, fn))
    slim = {"generated_at": doc.get("generated_at"),
            "players": [{k: r.get(k) for k in ("player_key", "player_name", "org", "status",
                                               "fv", "position", "surplus_source",
                                               "trade_value_mm")}
                        for r in doc["players"]]}
    ctx.eval("var IDX = _taBuildIndex(%s);" % json.dumps(slim))
    return ctx


def _price(js, key, name, orgs):
    return json.loads(js.eval("JSON.stringify(_taPriceParty(IDX, %s, %s, %s))" % (
        json.dumps(key), json.dumps(name), json.dumps(orgs))))


def _tv(key: str) -> float:
    for r in _trade_values()["players"]:
        if r["player_key"] == key:
            return r["trade_value_mm"]
    pytest.skip(f"{key} not on the trade-value board today")


@pytest.mark.parametrize("key,name,orgs", [
    ("adley_rutschman", "Adley Rutschman", ["BAL", "BOS"]),
    ("luis_arraez", "Luis Arraez", ["SFG", "PHI"]),
    ("tyrone_taylor", "Tyrone Taylor", ["NYM", "CHC"]),
    ("jose_soriano", "José Soriano", ["LAA", "TOR"]),
    ("nolan_arenado", "Nolan Arenado", ["STL", "ARI"]),
])
def test_named_veterans_price_at_trade_value(js, key, name, orgs):
    want = _tv(key)
    by_key = _price(js, key, name, orgs)
    by_name = _price(js, None, name, orgs)
    for got in (by_key, by_name):
        assert got["kind"] == "tv" and got["key"] == key
        assert got["value"] == pytest.approx(want), f"{name}: audit {got['value']} vs trade value {want}"


def test_initials_and_accents_fold_together(js):
    assert js.eval("_taFold('C.J. Abrams')") == js.eval("_taFold('CJ Abrams')") == "cj_abrams"
    # String.prototype.normalize needs ICU; the embedded V8 may be built without it
    # (browsers always have it, and the served-page test below covers Chromium).
    if js.eval("'\\u00e9'.normalize('NFKD').length") != 2:
        pytest.skip("this V8 has no ICU, so NFKD folding cannot be checked here")
    assert js.eval("_taFold(%s)" % json.dumps("José Soriano")) == "jose_soriano"


def test_a_key_miss_falls_back_to_the_name_only_inside_the_two_clubs(js):
    rows = [r for r in _trade_values()["players"] if r["player_key"] == "dj_herz"]
    if not rows:
        pytest.skip("dj_herz not on the trade-value board today")
    org = rows[0]["org"]
    inside = _price(js, "dj_herz__26389", "DJ Herz", [org, "ZZZ"])
    assert inside["kind"] == "tv" and inside["value"] == pytest.approx(rows[0]["trade_value_mm"])
    outside = _price(js, "dj_herz__26389", "DJ Herz", ["ZZY", "ZZZ"])
    assert outside["kind"] == "unpriced"


def test_unknown_and_loading_parties_name_no_winner(js):
    assert _price(js, None, "Nobody Anybody", ["NYY", "BOS"])["kind"] == "unpriced"
    assert json.loads(js.eval("JSON.stringify(_taPriceParty(null, 'x', 'X', null))"))["kind"] == "pending"
    assert js.eval("_taVerdict(40, 1, 0, 5)") == "withheld"
    assert js.eval("_taVerdict(40, 0, 2, 5)") == "pending"
    assert js.eval("_taVerdict(4.9, 0, 0, 5)") == "balanced"
    assert js.eval("_taVerdict(-5.1, 0, 0, 5)") == "orgB"
    assert js.eval("_taMM(-0.4)") == "-$0.4M"


# ---------------------------------------------------------------------------
# 3. The served Transactions tab
# ---------------------------------------------------------------------------

_CARDS = """() => [...document.querySelectorAll('.trade-audit-card')].map(c => ({
  verdict: c.getAttribute('data-ta-verdict'),
  text: (c.innerText || '').replace(/\\s+/g, ' '),
  chips: [...c.querySelectorAll('[data-ta-kind]')].map(s => ({
    kind: s.getAttribute('data-ta-kind'), key: s.getAttribute('data-ta-key'),
    mm: s.getAttribute('data-ta-mm'), title: s.getAttribute('title') || ''})),
}))"""


def test_served_audit_cards_use_the_trade_value():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    tv = {r["player_key"]: r["trade_value_mm"] for r in _trade_values()["players"]}
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
        page.goto(base + "prospx/index.html#tab=traded&acq=trade", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => { const c = document.querySelectorAll('.trade-audit-card');"
            " return c.length > 5 && ![...c].some(x => x.getAttribute('data-ta-verdict') === 'pending'); }",
            timeout=180_000)
        cards = page.evaluate(_CARDS)
        browser.close()
    assert not errs, errs[:3]
    assert len(cards) > 20
    priced = 0
    for c in cards:
        kinds = [ch["kind"] for ch in c["chips"]]
        assert "pending" not in kinds
        if "unpriced" in kinds:
            assert c["verdict"] == "withheld", f"a card with an unpriced party names a winner: {c['text'][:160]}"
        else:
            assert c["verdict"] in ("orgA", "orgB", "balanced")
        for ch in c["chips"]:
            assert "career WAR ×" not in ch["title"] and "realized career value" not in ch["title"]
            if ch["kind"] == "tv" and ch["key"]:
                priced += 1
                assert ch["key"] in tv, ch
                assert float(ch["mm"]) == pytest.approx(tv[ch["key"]]), ch
    assert priced > 100, f"only {priced} priced chips on the served audit; the check proved little"
