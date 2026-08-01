# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Spotrac FA-page parser guards, against committed fixture HTML (no
network). Exercises every branch the live pages showed in June 2026:
header-order shuffle, QO <small> markers, both money display forms,
minor-league deals (Value "-"), org normalization, the full option
taxonomy, and the unknown-taxonomy loud-degrade path."""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import fa_sources as fs

FIXTURE = Path(__file__).parent / "test_fixtures" / "fa_pages_sample.html"


@pytest.fixture(scope="module")
def soup() -> BeautifulSoup:
    return BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")


# ---- cell parsers ----------------------------------------------------------

def test_parse_money_forms():
    assert fs._parse_money("$210,000,000") == 210_000_000
    assert fs._parse_money("$55.3M") == 55_300_000
    assert fs._parse_money("$12.0M") == 12_000_000
    assert fs._parse_money("$-177,772,931") == -177_772_931
    assert fs._parse_money("-") is None
    assert fs._parse_money("") is None
    assert fs._parse_money(None) is None


def test_parse_fa_type_taxonomy():
    assert fs._parse_fa_type("UFA") == {"fa_type": "ufa", "fa_type_raw": "UFA", "option_price_usd": None}
    t = fs._parse_fa_type("OPT-OUT / $55.3M")
    assert t["fa_type"] == "opt_out" and t["option_price_usd"] == 55_300_000
    assert fs._parse_fa_type("CONDITIONAL-CLUB / $20.0M")["fa_type"] == "conditional_club_option"
    # A taxonomy value Spotrac invents later degrades LOUDLY, not silently.
    nt = fs._parse_fa_type("VESTING / $9.0M")
    assert nt["fa_type"] == "unknown" and nt["fa_type_raw"] == "VESTING / $9.0M"


# ---- signed-class table ----------------------------------------------------

def test_signed_table_parses_terms_qo_and_orgs(soup):
    rows = fs._parse_signed_table(soup.find("table", class_="signed"), 2016)
    assert len(rows) == 3
    sch = rows[0]
    assert sch["player_name"] == "Max Scherzer" and sch["qo"] is True
    assert sch["player_key"] == "max_scherzer"
    assert sch["spotrac_id"] == "12345" and sch["spotrac_slug"] == "max-scherzer"
    assert sch["from_team"] == "DET" and sch["to_team"] == "WSN"   # WSH normalized
    assert sch["years"] == 7 and sch["guarantee_usd"] == 210_000_000
    assert sch["mlb_deal"] is True


def test_signed_table_milb_deal_flag_and_org_overrides(soup):
    rows = fs._parse_signed_table(soup.find("table", class_="signed"), 2016)
    milb = rows[1]
    assert milb["guarantee_usd"] is None and milb["mlb_deal"] is False
    assert milb["from_team"] == "CHW" and milb["to_team"] == "SDP"  # CWS/SD normalized
    assert rows[2]["from_team"] == "TBR" and rows[2]["to_team"] == "KCR"


# ---- available tables (both column orders) ----------------------------------

def test_available_order_a(soup):
    rows = fs._parse_available_table(soup.find("table", class_="avail-a"), 2027)
    assert len(rows) == 2
    bo = rows[0]
    assert bo["player_key"] == "bo_bichette" and bo["fa_type"] == "opt_out"
    assert bo["option_price_usd"] == 55_300_000 and bo["age"] == 28.2
    assert bo["from_team"] == "NYM" and bo["prev_war"] == 3.1
    plain = rows[1]
    assert plain["fa_type"] == "ufa" and plain["prev_aav_usd"] is None
    assert plain["from_team"] == "CHW"
    assert plain["market_value_aav_usd"] == 12_000_000


def test_available_order_b_shuffled_headers(soup):
    """The remaining-unsigned tables shuffle column order — parsing must
    key off headers, never positions."""
    rows = fs._parse_available_table(soup.find("table", class_="avail-b"), 2024)
    assert len(rows) == 2
    vet = rows[0]
    assert vet["fa_type"] == "mutual_option" and vet["option_price_usd"] == 6_500_000
    assert vet["from_team"] == "WSN" and vet["prev_war"] == 0.8 and vet["age"] == 35.4
    cond = rows[1]
    assert cond["fa_type"] == "conditional_club_option"
    assert cond["from_team"] == "SFG" and cond["market_value_aav_usd"] == 19_500_000


# ---- compact available layout (2026-07-30 Spotrac redesign) ------------------

def test_available_compact_layout(soup):
    """The 2-column layout that silently froze the 2027 board for a day:
    every field the old six columns carried now lives inside one cell."""
    rows = fs._parse_available_table(soup.find("table", class_="avail-compact"), 2027)
    assert len(rows) == 3
    bo = rows[0]
    assert bo["player_key"] == "bo_bichette" and bo["position"] == "3B"
    assert bo["fa_type"] == "opt_out" and bo["fa_type_raw"] == "ETO"
    assert bo["age"] == 28.3 and bo["prev_aav_usd"] == 42_000_000
    assert bo["from_team"] == "NYM" and bo["spotrac_id"] == "19942"
    # Fields the compact layout stopped publishing come back None, never stale.
    assert bo["option_price_usd"] is None
    assert bo["market_value_aav_usd"] is None and bo["prev_war"] is None


def test_available_compact_missing_pill_is_plain_ufa(soup):
    rows = fs._parse_available_table(soup.find("table", class_="avail-compact"), 2027)
    gray = rows[1]
    assert gray["player_key"] == "sonny_gray" and gray["fa_type"] == "ufa"
    assert gray["position"] == "SP" and gray["prev_aav_usd"] == 25_000_000


def test_available_compact_team_logo_variants(soup):
    """Logo basenames are not uniform - mlb_nym.png, cle_2022.png,
    ath_2025.png all have to resolve or coverage silently drops."""
    rows = fs._parse_available_table(soup.find("table", class_="avail-compact"), 2027)
    assert [r["from_team"] for r in rows] == ["NYM", "CLE", "ATH"]
    assert rows[2]["fa_type"] == "club_option"


def test_available_unknown_layout_still_degrades_loudly(soup, caplog):
    """The compact fallback must not swallow a genuinely unknown shape."""
    rows = fs._parse_available_table(soup.find("table", class_="avail-unknown"), 2027)
    assert rows == []
    assert any("unrecognized header set" in r.getMessage() for r in caplog.records)


# ---- tax ledger --------------------------------------------------------------

def test_tax_table_parses_status_space_and_team(soup):
    # Reuse the internal header-mapped parse via a tiny shim that mirrors
    # scrape_spotrac_tax's body on a fixture table.
    table = soup.find("table", class_="tax")
    hmap = fs._header_map(table)
    assert "tax payroll" in hmap and "status" in hmap
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        rows.append({
            "team": fs._team_from_cell(tds[hmap["team"]]),
            "status": tds[hmap["status"]].get_text(strip=True),
            "tax": fs._parse_money(tds[hmap["tax payroll"]].get_text(strip=True)),
            "space": fs._parse_money(tds[hmap["space"]].get_text(strip=True)),
        })
    assert rows[0]["team"] == "LAD" and rows[0]["status"] == "3+-Time"
    assert rows[0]["space"] == -177_772_931
    assert rows[1]["team"] == "CHW" and rows[1]["tax"] == 95_000_000
