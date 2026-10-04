# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The club free-agent spend profile and the payroll history (owner ask 3,
2026-09-30; Part 8 lane finance_to_fa_arb, Leg A).

"Which teams actually spend money in free agency", answered as a FACT on the
Club Ledger and in Franchise MARKET: each club's share of league free-agent
guarantee dollars by the winter each deal was signed, its band mix, its re-sign
share and its QO counts, plus its tax payroll and payor tier season by season
off the cached Spotrac pages. These tests hold the lines that make it a ledger
and not a forecast:

  1. The shares of a window sum to one over the thirty clubs, and a club's
     dollars are exactly the Spend by winter cells it shares a source with.
  2. The payroll history is the cached tax page, parsed again here, and every
     row prints its own season's threshold. The reader never opens a socket.
  3. The writer still refuses projected_payroll and payroll_forecast, no cell
     takes a colour, and no history row runs past the current season.
  4. The board keeps ten preview rows under the 950,000-byte guard (the
     owner's VAL1-Q1 answer) and every shard stays under 160,000 bytes.
  5. With LEDGER_FA_SPEND_PROFILE off the export carries none of it.

The flag-on build is computed in memory (build_all never writes); the served
files are checked against whichever way the committed flag points.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "ledger_board.json"
SHARD_DIR = ROOT / "data" / "ledger_clubs"
JS = ROOT / "assets" / "ledger.js"
FJS = ROOT / "assets" / "franchise.js"
CACHE = ROOT / ".cache"


def _inputs_or_skip():
    for name in ("fa_archive.json", "fa_meta.json", "mlb_projections.json", "trade_values.json"):
        if not (ROOT / "data" / name).exists():
            pytest.skip(f"data/{name} absent; the ledger build needs it")


@pytest.fixture(scope="module")
def built_on():
    """(doc, shards) from build_all with the flag on, in memory."""
    _inputs_or_skip()
    import ledger_export as L
    saved = L.LEDGER_FA_SPEND_PROFILE
    L.LEDGER_FA_SPEND_PROFILE = True
    try:
        doc, shards = L.build_all()
    finally:
        L.LEDGER_FA_SPEND_PROFILE = saved
    return doc, shards


@pytest.fixture(scope="module")
def built_off():
    _inputs_or_skip()
    import ledger_export as L
    saved = L.LEDGER_FA_SPEND_PROFILE
    L.LEDGER_FA_SPEND_PROFILE = False
    try:
        doc, shards = L.build_all()
    finally:
        L.LEDGER_FA_SPEND_PROFILE = saved
    return doc, shards


def _need_cache():
    if not (CACHE / "spotrac_tax_2026.html").exists():
        pytest.skip("the cached Spotrac tax pages are not on this box")


# --------------------------------------------------------------------------
# 1. the shares and the reconciliation to Spend by winter
# --------------------------------------------------------------------------

def test_the_thirty_shares_of_each_window_sum_to_one(built_on):
    doc, shards = built_on
    assert len(shards) == 30
    lp = doc["league"]["fa_spend_profile"]
    for wk in ("recent", "all"):
        shares = [s["fa"]["profile"]["share"][wk][1] for s in shards.values()]
        assert abs(sum(shares) - 1.0) <= 1e-9, (wk, sum(shares))
        assert sum(s["fa"]["profile"]["share"][wk][0] for s in shards.values()) == lp["league_usd"][wk]
        ranks = sorted(s["fa"]["profile"]["share"][wk][2] for s in shards.values())
        assert ranks[0] == 1 and ranks[-1] <= 30
    col = [r["fa_share_3"] for r in doc["league"]["rows"]]
    assert abs(sum(col) - 1.0) <= 1e-9
    for r in doc["league"]["rows"]:
        assert r["fa_share_3"] == shards[r["club"]]["fa"]["profile"]["share"]["recent"][1], r["club"]


def test_a_clubs_dollars_equal_its_spend_by_winter_cells_exactly(built_on):
    doc, shards = built_on
    import ledger_export as L
    i_year, i_spend = 0, 2
    assert doc["field_key"]["fa.winters"].startswith("[winter, n_in, spend_in_usd,")
    win = doc["league"]["fa_spend_profile"]["windows"]
    for c, club in doc["clubs"].items():
        cells = {row[i_year]: row[i_spend] for row in club["fa"]["winters"]}
        for wk, (first, last, n) in win.items():
            years = [y for y in cells if first <= y <= last]
            assert len(years) == n, (c, wk)
            assert shards[c]["fa"]["profile"]["share"][wk][0] == sum(cells[y] for y in years), (c, wk)
    # the bands, departures and QO counts hold to their own identities
    arch = json.loads((ROOT / "data" / "fa_archive.json").read_text(encoding="utf-8"))
    prof = L.club_fa_spend_profile(arch["winters"], sorted(doc["clubs"]))
    for c in doc["clubs"]:
        p = prof["clubs"][c]
        assert p == shards[c]["fa"]["profile"], c
        for wk in ("recent", "all"):
            milb_usd = sum(int(float(s.get("guar") or 0)) for w in arch["winters"]
                           if win[wk][0] <= w["year"] <= win[wk][1]
                           for s in w["signings"] if s.get("milb") and L._canon(s.get("to")) == c)
            assert sum(b[1] for b in p["bands"][wk]) == p["share"][wk][0] - milb_usd, (c, wk)
            n_dep, n_res, sh = p["resign"][wk]
            assert 0 <= n_res <= n_dep and (sh is None) == (n_dep == 0)
            qo_in = sum(row[4] for row in doc["clubs"][c]["fa"]["winters"] if win[wk][0] <= row[0] <= win[wk][1])
            assert p["qo"][wk][0] == qo_in, (c, wk)


def test_the_band_edges_are_half_open():
    import ledger_export as L
    assert [L._fa_band(g) for g in (0, 9_999_999, 10_000_000, 49_999_999, 50_000_000, 100_000_000, 7e8)] == \
        [0, 0, 1, 1, 2, 3, 3]
    assert [k for k, _lo, _hi in L.FA_PROFILE_BANDS] == ["under_10m", "10m_50m", "50m_100m", "100m_up"]


def test_the_profile_on_a_fixture():
    import ledger_export as L
    winters = [
        {"year": 2024, "signings": [
            {"to": "LAD", "from": "LAD", "guar": 120_000_000, "qo": True},
            {"to": "NYY", "from": "LAD", "guar": 30_000_000, "qo": True},
            {"to": "NYY", "from": "BOS", "guar": 0, "milb": True}]},
        {"year": 2025, "signings": [{"to": "BOS", "from": "NYY", "guar": 50_000_000}]},
    ]
    p = L.club_fa_spend_profile(winters, ["BOS", "LAD", "NYY"], recent=1)
    assert p["windows"] == {"recent": [2025, 2025, 1], "all": [2024, 2025, 2]}
    assert p["league_usd"] == {"recent": 50_000_000, "all": 200_000_000}
    lad = p["clubs"]["LAD"]
    assert lad["share"]["all"] == [120_000_000, 0.6, 1] and lad["share"]["recent"] == [0, 0.0, 2]
    assert lad["resign"]["all"] == [2, 1, 0.5] and lad["qo"]["all"] == [1, 1], "a re-signing is no QO departure"
    assert lad["bands"]["all"] == [[0, 0], [0, 0], [0, 0], [1, 120_000_000]]
    nyy = p["clubs"]["NYY"]
    assert nyy["n_milb_in"]["all"] == 1 and nyy["bands"]["all"][1] == [1, 30_000_000] and nyy["qo"]["all"] == [1, 0]
    assert p["clubs"]["BOS"]["resign"]["all"] == [0, 0, None], "a minor-league departure is not a departure"


# --------------------------------------------------------------------------
# 2. the payroll history: the cached page, parsed again, never fetched
# --------------------------------------------------------------------------

def test_the_payroll_history_reproduces_the_cached_tax_pages_and_prints_its_seasons_threshold(built_on):
    _need_cache()
    doc, shards = built_on
    import fa_cba
    import fa_sources
    import ledger_export as L
    cen = doc["sections"]["payroll_history"]["census"]
    assert doc["sections"]["payroll_history"]["live"] is True
    for y in L.PAYROLL_HISTORY_SEASONS:
        p = CACHE / f"spotrac_tax_{y}.html"
        if not p.exists():
            assert y in cen["missing_tax"], y
            continue
        body = p.read_text(encoding="utf-8")
        T = fa_sources.parse_spotrac_tax_threshold(body)
        assert T and cen["threshold_by_season"][str(y)] == T, y
        try:
            rule = fa_cba.cbt_threshold(y)
        except LookupError:
            rule = None
        if rule and not rule["carry_forward"]:
            assert rule["threshold_usd"] == T, (y, "the page and cba_rules disagree")
        parsed = {L._canon(r["team"]): r for r in fa_sources.parse_spotrac_tax_body(body, y)}
        assert len(parsed) == 30, y
        for c, s in shards.items():
            row = next(r for r in s["payroll"]["history"] if r[0] == y)
            src = parsed[c]
            assert row[1] == src["tax_payroll_usd"] and row[2] == (src["payor_status_raw"] or None), (c, y)
            assert row[3] == T, (c, y, "every row prints its own season's threshold")
            assert row[4] == src["tax_payroll_usd"] - T, (c, y)
            assert row[5] == (src["est_tax_bill_usd"] or None), (c, y)
    for c, s in shards.items():
        seasons = [r[0] for r in s["payroll"]["history"]]
        assert seasons == sorted(seasons) and seasons[-1] <= L.SEASON_NOW, (c, "no row past the current season")
        assert doc["clubs"][c]["payroll"]["history"] == {"status": "shard", "n": len(seasons),
                                                          "first": seasons[0], "last": seasons[-1]}


def test_the_reader_and_the_build_never_open_a_socket(monkeypatch):
    _need_cache()
    _inputs_or_skip()
    import socket
    import fa_sources
    import ledger_export as L

    def _no(*a, **k):
        raise AssertionError("a socket was opened")
    monkeypatch.setattr(socket, "socket", _no)
    monkeypatch.setattr(socket, "create_connection", _no)
    try:
        import requests
        monkeypatch.setattr(requests.sessions.Session, "request", _no)
    except ImportError:
        pass
    monkeypatch.setattr(fa_sources, "_fetch", _no)
    h = fa_sources.read_cached_payroll_history([2016, 2026])
    assert len(h["seasons"][2016]["tax"]) == 30 and h["missing_payroll"] == [2016]
    monkeypatch.setattr(L, "LEDGER_FA_SPEND_PROFILE", True)
    doc, shards = L.build_all()
    assert all("payroll" in s and s["payroll"]["history"] for s in shards.values())


def test_the_reader_refuses_the_network_structurally(tmp_path, monkeypatch):
    import fa_sources

    def _parse_that_dials(body, year):
        import socket
        socket.create_connection(("www.spotrac.com", 443), timeout=1)
        return []
    (tmp_path / "spotrac_tax_2020.html").write_text("<table></table>", encoding="utf-8")
    monkeypatch.setattr(fa_sources, "parse_spotrac_tax_body", _parse_that_dials)
    with pytest.raises(fa_sources.NetworkDisabled):
        fa_sources.read_cached_payroll_history([2020], tmp_path)
    import socket
    assert socket.create_connection.__name__ == "create_connection", "the socket module is restored"
    h = fa_sources.read_cached_payroll_history([2021], tmp_path)
    assert h["missing_tax"] == [2021] and h["missing_payroll"] == [2021], "a missing page is missing, not fetched"


def test_the_threshold_tile_parses():
    import fa_sources
    html = '<div id="tax_threshold" class="form-select">\n   $189,000,000   </div>'
    assert fa_sources.parse_spotrac_tax_threshold(html) == 189_000_000
    assert fa_sources.parse_spotrac_tax_threshold("<div></div>") is None


# --------------------------------------------------------------------------
# 3. the NEVER list
# --------------------------------------------------------------------------

def test_the_key_walker_still_refuses_a_payroll_forecast(built_on):
    import copy as _copy
    import ledger_export as L
    doc, shards = built_on
    assert L.FORBIDDEN_KEY_FRAGMENTS == ("projected_payroll", "payroll_forecast")
    for frag in L.FORBIDDEN_KEY_FRAGMENTS:
        bad = _copy.deepcopy(doc)
        bad["clubs"]["LAD"]["payroll"]["history"]["club_" + frag] = 1
        with pytest.raises(AssertionError):
            L._assert_document(bad)
        bad_sd = _copy.deepcopy(shards)
        bad_sd["LAD"]["fa"]["profile"][frag + "_usd"] = 1
        with pytest.raises(AssertionError):
            L._assert_shards(doc, bad_sd)
    L._assert_document(doc)
    L._assert_shards(doc, shards)


def test_no_cell_of_the_profile_or_the_history_takes_a_colour(built_on):
    doc, _shards = built_on
    assert "fa_share_3" not in doc["league"]["coloured"] and "fa_share_3" not in doc["league"]["means"]["values"]
    js = JS.read_text(encoding="utf-8")
    for fn in ("renderFaProfile", "renderPayrollHistory"):
        i = js.index("function " + fn + "(")
        j = js.index("\n  function ", i + 10)
        body = js[i:j]
        for banned in ("signCls(", "zCell(", "zCls(", "costMoney(", "signedMoney(", "EephusTiers"):
            assert banned not in body, (fn, banned)
    assert 'if (key === "fa_share_3") return pct(v, 1);' in js
    fjs = FJS.read_text(encoding="utf-8")
    i = fjs.index("function marketProfile(")
    body = fjs[i:fjs.index("\n  var PANEL_NOTE", i)]
    for banned in ("signCls(", "signedMoney(", "tierInk("):
        assert banned not in body, banned


def test_the_copy_says_realized_not_a_forecast_and_carries_no_dash(built_on):
    import ledger_export as L
    doc, _shards = built_on
    assert L.FA_PROFILE_COPY == ("Share of league free-agent dollars, by the winter each deal was signed. "
                                 "Realized spending, not a forecast.")
    assert doc["copy"]["fa_profile_lede"] == L.FA_PROFILE_COPY
    col = next(c for c in doc["league"]["columns"] if c[0] == "fa_share_3")
    assert col[1] == "FA $ share, 3 winters" and col[3].startswith(L.FA_PROFILE_COPY)
    assert any("free-agent spending forecast" in s for s in doc["what_this_page_does_not_claim"])
    txt = json.dumps({k: v for k, v in doc["copy"].items() if k.startswith(("fa_profile", "payroll_history"))},
                     ensure_ascii=False)
    assert chr(0x2014) not in txt and chr(0x2013) not in txt
    assert not re.search(r"\b(will|due|trending|regress)\b", txt.lower())


# --------------------------------------------------------------------------
# 4. the budgets: ten preview rows under the guard, every shard under its cap
# --------------------------------------------------------------------------

def test_the_board_keeps_ten_preview_rows_under_the_guard_and_every_shard_under_its_cap(built_on):
    import ledger_export as L
    doc, shards = built_on
    assert doc["shards"]["preview_n"] == L.PREVIEW_N == 10, "the owner's VAL1-Q1 answer, undone silently"
    assert L._doc_bytes(doc) <= L.PREVIEW_GUARD_BYTES == 950_000
    for c, s in shards.items():
        assert len(L._shard_bytes(s)) <= L.SHARD_CAP_BYTES == 160_000, c


# --------------------------------------------------------------------------
# 5. the flag: off carries nothing, and the served files follow the flag
# --------------------------------------------------------------------------

def test_with_the_flag_off_the_export_carries_none_of_it(built_off):
    import ledger_export as L
    doc, shards = built_off
    assert "fa_spend_profile" not in doc["league"] and "fa_spend_profile" not in doc["sections"]
    assert all("fa_share_3" not in r for r in doc["league"]["rows"])
    assert all(c[0] != "fa_share_3" for c in doc["league"]["columns"])
    assert set(doc["columns"]) == set(L.COLUMNS)
    for c, s in shards.items():
        assert "payroll" not in s and "fa" not in s, c
        assert doc["clubs"][c]["payroll"]["history"] == {"status": "dark", "seasons": []}, c
    assert not any(k.startswith(("fa_profile", "payroll_history_")) for k in doc["copy"])
    assert doc["sections"]["payroll_history"]["live"] is False


def test_the_franchise_market_prints_the_ledgers_shares_and_band_mix(built_on, monkeypatch):
    _inputs_or_skip()
    import franchise_export as F
    import ledger_export as L
    _doc, shards = built_on
    monkeypatch.setattr(L, "LEDGER_FA_SPEND_PROFILE", True)
    try:
        fdoc = F.build()
    except F.FranchiseRefusal as exc:
        pytest.skip(f"franchise build refused on this box: {exc}")
    for club in fdoc["clubs"]:
        sp = club["sections"]["market"]["spend_profile"]
        led = shards[club["code"]]["fa"]["profile"]
        assert sp["share"] == led["share"] and sp["bands"] == led["bands"], club["code"]
        mk = next(b for b in club["tree"]["branches"] if b["key"] == "market")
        leaves = {lf["key"]: lf for lf in mk["leaves"]}
        assert leaves["fa_share_recent"]["value"] == led["share"]["recent"][1]
        assert leaves["fa_share_all"]["value"] == led["share"]["all"][1]
        assert leaves["fa_share_recent"]["ladder"] is None and leaves["fa_share_recent"]["kind"] == "pct"
    monkeypatch.setattr(L, "LEDGER_FA_SPEND_PROFILE", False)
    off = F.build()
    assert all("spend_profile" not in c["sections"]["market"] for c in off["clubs"])
    assert "market_profile_lede" not in off["copy"]


def test_the_served_files_follow_the_committed_flag():
    import ledger_export as L
    if not ART.exists():
        pytest.skip("run python ledger_export.py")
    d = json.loads(ART.read_text(encoding="utf-8"))
    shard = json.loads((SHARD_DIR / "LAD.json").read_text(encoding="utf-8"))
    if not L.LEDGER_FA_SPEND_PROFILE:
        assert "fa_spend_profile" not in d["league"] and "fa" not in shard
        return
    assert "fa_spend_profile" in d["league"] and shard["fa"]["profile"]["share"]["recent"][2] >= 1
    assert d["shards"]["preview_n"] == 10 and ART.stat().st_size <= L.PREVIEW_GUARD_BYTES
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in g["entries"]}
    for gid in list(d["copy"]["fa_profile_gl"].values()) + ["fa_dollar_share"]:
        assert gid in ids, gid
    reg = {m["model_id"]: m for m in json.loads((ROOT / "data" / "model_registry.json")
                                                .read_text(encoding="utf-8"))["models"]}
    row = reg["club_fa_spend_profile"]
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "measurement_only"
    assert row["eval_artifact"] is None
    assert "descriptive, no forward claim" in row["baseline"] and "descriptive, no forward claim" in row["metric"]
