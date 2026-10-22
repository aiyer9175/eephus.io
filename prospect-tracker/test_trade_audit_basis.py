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
  * a party with no trade value is unpriced and counts as $0 on the side that received
    him (owner answer M9-1, 2026-09-25, replacing the withheld verdict): the card still
    names a winner or reads balanced, and a footnote names every unpriced party as
    valued at zero; while the prices load the card names no winner;
  * on the served page every priced chip equals its trade_value_mm;
  * the page reads the slim sidecar data/trade_values_slim.json (owner answer M10-1),
    written by tools/export_trade_values.write_slim_sidecar from the board just
    written, with every field the pricer and the debuted lead read; the full board is
    the fallback only when the sidecar cannot be read.
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
from tools import export_trade_values as etv  # noqa: E402


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
    assert "_taVerdict(g.netDeltaA, pendingCount, BALANCED_THRESHOLD_MM)" in body
    assert "withheld" not in body, "an unpriced party no longer withholds the verdict (M9-1)"
    assert "_taTradeValuesLoad()" in body
    assert "trade_value_lo" not in body and "trade_value_hi" not in body, (
        "the audit must never sum a quantile point")


# ---------------------------------------------------------------------------
# 2. The pricer in V8, against the served trade values
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js(tmp_path_factory):
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    _trade_values()
    src = _src()
    ctx = mr.MiniRacer()
    for fn in ("_taFold", "_taBuildIndex", "_taPriceParty", "_taVerdict", "_taMM"):
        ctx.eval(_function_source(src, fn))
    # The index is built from what the page reads: the slim sidecar, written by the
    # real writer from the served board into a tmp dir (never into data/).
    out = tmp_path_factory.mktemp("slim") / etv.SLIM_NAME
    etv.write_slim_sidecar(ROOT / "data" / "trade_values.json", out)
    ctx.eval("var IDX = _taBuildIndex(%s);" % out.read_text(encoding="utf-8"))
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


def test_loading_names_no_winner_and_unpriced_is_zero(js):
    assert _price(js, None, "Nobody Anybody", ["NYY", "BOS"])["kind"] == "unpriced"
    assert json.loads(js.eval("JSON.stringify(_taPriceParty(null, 'x', 'X', null))"))["kind"] == "pending"
    # an unpriced party is $0 inside netDeltaA, so the verdict reads only the net
    assert js.eval("_taVerdict(40, 0, 5)") == "orgA"
    assert js.eval("_taVerdict(40, 2, 5)") == "pending"
    assert js.eval("_taVerdict(4.9, 0, 5)") == "balanced"
    assert js.eval("_taVerdict(-5.1, 0, 5)") == "orgB"
    assert js.eval("_taMM(-0.4)") == "-$0.4M"


# ---------------------------------------------------------------------------
# 3. The served Transactions tab
# ---------------------------------------------------------------------------

_CARDS = """() => [...document.querySelectorAll('.trade-audit-card')].map(c => ({
  verdict: c.getAttribute('data-ta-verdict'), net: c.getAttribute('data-ta-net'),
  text: (c.innerText || '').replace(/\\s+/g, ' '),
  foot: (c.querySelector('.ta-unpriced-foot') || {}).innerText || null,
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
        fetched: list[str] = []
        page.on("request", lambda r: fetched.append(r.url.split("?")[0].rsplit("/", 1)[-1]))
        page.goto(base + "prospx/index.html#tab=traded&acq=trade", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => { const c = document.querySelectorAll('.trade-audit-card');"
            " return c.length > 5 && ![...c].some(x => x.getAttribute('data-ta-verdict') === 'pending'); }",
            timeout=180_000)
        cards = page.evaluate(_CARDS)
        browser.close()
    assert not errs, errs[:3]
    if (ROOT / "data" / etv.SLIM_NAME).exists():
        assert etv.SLIM_NAME in fetched and "trade_values.json" not in fetched, (
            "the Transactions tab reads the slim sidecar, not the 4.9 MB board (M10-1)")
    assert len(cards) > 20
    priced = 0
    for c in cards:
        kinds = [ch["kind"] for ch in c["chips"]]
        assert "pending" not in kinds
        assert c["verdict"] in ("orgA", "orgB", "balanced"), c["text"][:160]
        n_unpriced = kinds.count("unpriced")
        if n_unpriced:
            assert c["foot"] and "Unpriced, valued at $0" in c["foot"], c["text"][:160]
            assert c["foot"].count("(to ") == n_unpriced, "the footnote names every unpriced party"
        else:
            assert not c["foot"]
        for ch in c["chips"]:
            if ch["kind"] == "unpriced":
                assert ch["mm"] == "0" and "valued at $0" in ch["title"], ch
            assert "career WAR ×" not in ch["title"] and "realized career value" not in ch["title"]
            if ch["kind"] == "tv" and ch["key"]:
                priced += 1
                assert ch["key"] in tv, ch
                assert float(ch["mm"]) == pytest.approx(tv[ch["key"]]), ch
    assert priced > 100, f"only {priced} priced chips on the served audit; the check proved little"


# ---------------------------------------------------------------------------
# 4. The slim sidecar (owner answer M10-1, 2026-09-25)
# ---------------------------------------------------------------------------

def _row_fields_read_by_the_page() -> set[str]:
    """Every field prospx reads off a trade-value row: the pricer, the index and
    the debuted lead all name their row `row` or `r`."""
    src = _src()
    fields: set[str] = set()
    for fn in ("_taBuildIndex", "_taPriceParty", "_dtvRow", "_tvLeadFill", "debutedTradeValueMM"):
        body = _function_source(src, fn)
        fields |= set(re.findall(r"\b(?:row|r)\.([a-z_][a-z0-9_]*)", body))
    return fields - {"length"}


def test_the_sidecar_carries_every_field_the_page_reads():
    read = _row_fields_read_by_the_page()
    assert {"player_key", "trade_value_mm", "surplus_source", "mlbam_id"} <= read, read
    missing = read - set(etv.SLIM_FIELDS)
    assert not missing, f"prospx reads {sorted(missing)} off a trade-value row but the sidecar drops it"
    assert "trade_value_lo" not in etv.SLIM_FIELDS and "trade_value_hi" not in etv.SLIM_FIELDS


def test_the_writer_copies_exactly_the_slim_fields(tmp_path):
    src = tmp_path / "trade_values.json"
    src.write_text(json.dumps({
        "generated_at": "2026-10-01T00:00:00Z", "calibration": {"version": "x"},
        "players": [
            {"player_key": "a_b", "mlbam_id": 1, "player_name": "A B", "org": "NYY",
             "status": "debuted", "fv": None, "position": "SS", "surplus_source": "projection",
             "trade_value_mm": 12.5, "trade_value_lo": -3.0, "trade_value_hi": 40.0, "contract": {}},
            {"player_key": "c_d", "player_name": "C D", "trade_value_mm": None},
        ]}), encoding="utf-8")
    n = etv.write_slim_sidecar(src)
    out = tmp_path / etv.SLIM_NAME
    assert n == 2 and out.exists(), "the default output sits beside the board it was written from"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["generated_at"] == "2026-10-01T00:00:00Z" and doc["count"] == 2
    assert doc["source"] == "trade_values.json" and doc["fields"] == list(etv.SLIM_FIELDS)
    assert [list(r) for r in doc["players"]] == [list(etv.SLIM_FIELDS)] * 2
    assert doc["players"][0]["trade_value_mm"] == 12.5 and doc["players"][1]["mlbam_id"] is None
    assert "trade_value_lo" not in out.read_text(encoding="utf-8")


def test_main_writes_both_outputs_under_the_data_dir_it_is_given(tmp_path, monkeypatch):
    """The second output path follows --data-dir, so a redirected run never touches
    the served data/trade_values_slim.json (the board writer is stubbed here)."""
    import bayes_trade_value
    real = ROOT / "data" / etv.SLIM_NAME
    before = real.stat().st_mtime_ns if real.exists() else None
    (tmp_path / "timeseries.json").write_text(json.dumps({"players": []}), encoding="utf-8")

    def _fake_export(players, out_path, level_norms=None):
        Path(out_path).write_text(json.dumps({"generated_at": "g", "players": [
            {"player_key": "x", "player_name": "X", "trade_value_mm": 1.0}]}), encoding="utf-8")
        return 1
    monkeypatch.setattr(bayes_trade_value, "export_trade_values_json", _fake_export)
    monkeypatch.setattr(bayes_trade_value, "_reset_cache", lambda: None)
    assert etv.main(["--data-dir", str(tmp_path), "--passes", "1"]) == 0
    slim = json.loads((tmp_path / etv.SLIM_NAME).read_text(encoding="utf-8"))
    assert slim["count"] == 1 and slim["players"][0]["player_key"] == "x"
    after = real.stat().st_mtime_ns if real.exists() else None
    assert before == after, "a redirected run wrote the served sidecar"


def test_the_page_reads_the_sidecar_first_and_the_full_board_only_as_fallback():
    body = _function_source(_src(), "_taTradeValuesLoad")
    i_slim, i_full = body.find('get("trade_values_slim.json")'), body.find('get("trade_values.json")')
    assert 0 <= i_slim < i_full, "the sidecar is read first, the full board only when it cannot be"
    assert etv.SLIM_NAME == "trade_values_slim.json"


def test_the_nightly_rebuild_writes_the_sidecar_too():
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i_tv = rm.find('export_trade_values_json(tv_players, out_dir / "trade_values.json"')
    i_slim = rm.find('write_slim_sidecar(out_dir / "trade_values.json")')
    assert 0 <= i_tv < i_slim, "run_monthly's rebuild path must write the sidecar after the board"


def test_the_sidecar_ships_in_both_deploy_consumers():
    name = etv.SLIM_NAME
    excluded = [ln.strip() for ln in (ROOT / "deploy" / "data_exclude.txt").read_text(
        encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    assert name not in excluded
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "--include='/data/*.json'" in nightly, "the nightly rsync ships data/*.json at depth one"
    wf = ROOT.parent / ".github" / "workflows" / "deploy-prospect-tracker.yml"
    if wf.exists():
        assert "find data -maxdepth 1 \\( -name '*.json'" in wf.read_text(encoding="utf-8"), (
            "the CI workflow copies data/*.json at depth one")
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/trade_values.json" in gi and f"data/{name}" in gi, (
        "the sidecar is rebuilt with the board every night, so it is ignored like the board")
