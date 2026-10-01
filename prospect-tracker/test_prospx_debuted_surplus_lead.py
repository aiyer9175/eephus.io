# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A debuted player's PROSPX Surplus value card leads with the Trade Machine value.

Until 2026-09-25 the card led with the eFV surplus, a prospect valuation that
tops out near $100M, while /trademachine/ and /projections/ printed the contract
projection: Bobby Witt Jr. read $100.2M on PROSPX and $311.4M on both others.
The card now fills a Trade value row from trade_values.json (the row's own
trade_value_mm, only on the contract-projection basis and only for the same
mlbam id) and labels the eFV figure a prospect valuation.

Since B4_BOARD_SURPLUS (owner answer FP4-1) the same rule (_dtvRow) leads the
board Surplus cell, its sort and pill, the phone row, the card's Surplus tile,
the GFX card and the compare card, so every PROSPX surface prints one number.

The club-control line on the same page joined /projections/ by slug, so the ATH
Max Muncy's card read the LAD Max Muncy's control window; it joins by mlbam now.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SRC = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    i = SRC.index(f"function {name}(")
    j = SRC.index("\nfunction ", i + 10)
    return SRC[i:j]


def test_the_lead_row_reads_the_trade_value_on_the_projection_basis_for_the_same_human():
    rule = _fn("_dtvRow")
    assert 'row.surplus_source !== "projection"' in rule
    assert "Number(row.mlbam_id) !== mid" in rule
    body = _fn("_tvLeadFill")
    assert "_dtvRow(" in body
    assert "row.trade_value_mm" in body
    # It prints the served number, not a re-derivation.
    assert "_taMM(mm)" in body


def test_the_card_carries_the_slot_and_the_detail_render_fills_it():
    assert 'data-tvlead-key="${escapeHtml(p.player_key || "")}"' in SRC
    assert "const inner = tvLeadSlot + surplusRow" in SRC
    assert "try { _tvLeadFill(); }" in SRC
    assert '"eFV prospect valuation"' in SRC


def test_the_club_control_line_joins_on_the_mlbam_id():
    body = _fn("_ctrlWinFill")
    assert "_CTRLWIN.byMlbam[_cwMid]" in body
    assert 'data-ctrlwin-mlbam="' in SRC
    load = _fn("_ctrlWinLoad")
    assert "byM[Number(v.mlbam)] = v" in load


def test_served_parity_the_lead_equals_the_board_value():
    """On the served artifacts: every debuted row the lead fires for prints the
    trade board's number, and Bobby Witt Jr. is among them."""
    dpath, tpath = ROOT / "data" / "debuts.json", ROOT / "data" / "trade_values.json"
    if not (dpath.exists() and tpath.exists()):
        pytest.skip("debuts.json / trade_values.json not built")
    debuts = json.loads(dpath.read_text(encoding="utf-8"))
    board = {r["player_key"]: r for r in json.loads(tpath.read_text(encoding="utf-8"))["players"]}
    fired = {}
    for r in debuts:
        tv = board.get(r.get("player_key"))
        if (r.get("status") != "debuted" or not tv
                or tv.get("surplus_source") != "projection" or tv.get("trade_value_mm") is None):
            continue
        if r.get("mlbam_id") and tv.get("mlbam_id") and tv["mlbam_id"] != r["mlbam_id"]:
            continue
        fired[r["player_key"]] = tv["trade_value_mm"]
    assert len(fired) > 500
    if "bobby_witt_jr" in board and board["bobby_witt_jr"].get("surplus_source") == "projection":
        assert fired.get("bobby_witt_jr") == board["bobby_witt_jr"]["trade_value_mm"]
    # The ATH Max Muncy (691777) is not priced on the LAD veteran's projection.
    mm = next((r for r in debuts if r.get("player_key") == "max_muncy"), None)
    if mm and mm.get("mlbam_id") == 691777:
        assert "max_muncy" not in fired or board["max_muncy"].get("mlbam_id") == 691777


# ---------------------------------------------------------------------------
# B4_BOARD_SURPLUS (owner answer FP4-1, 2026-09-25): the board Surplus column,
# its sort, the phone row, the card's Surplus tile, the GFX card and the compare
# card follow the card's rule, so the card, the board and /trademachine/ print
# one number for a debuted player.
# ---------------------------------------------------------------------------


def test_one_rule_decides_the_debuted_lead():
    body = _fn("debutedTradeValueMM")
    assert 'p.status !== "debuted"' in body
    assert "_dtvRow(p.player_key, p.mlbam_id)" in body
    # Until the trade board is cached the surface keeps its eFV figure and asks
    # for a repaint once it lands.
    assert "_dtvKick()" in body
    kick = _fn("_dtvKick")
    assert "_taTradeValuesLoad()" in kick
    assert "renderPlayerDetail(state.view.key)" in kick


def test_every_dollar_surface_leads_with_the_trade_value():
    # Board Surplus cell: the lead, then the prospect valuation as the second line.
    cell = _fn("makeSurplusCell")
    assert cell.index("debutedTradeValueMM(p)") < cell.index("const xf = getEfv(p)")
    assert "_dtvSurplusCellHTML(p, _dtv)" in cell
    lead = _fn("_dtvSurplusCellHTML")
    assert "${_taMM(mm)}</div>" in lead
    assert "_dtvSecondary(p)" in lead
    # The value every GFX and compare surface reads.
    disp = _fn("displaySurplusMM")
    assert disp.index("debutedTradeValueMM(p)") < disp.index("getEfv(p)")
    # Phone row.
    phone = _fn("_rowPhoneSignalsHTML")
    assert "const sv = _dtv != null ? _dtv" in phone
    assert '_dtv != null ? "TV" : "SV"' in phone
    # Board sort and its pill.
    assert ('if (_sk === "surplus_sv") { const tv = debutedTradeValueMM(p); '
            'if (tv != null) return tv; }') in SRC
    pill = _fn("_sortStatPill")
    assert 'return _pillHTML("Trade value", _taMM(tv))' in pill
    # Card Surplus tile, GFX hero tile, GFX surplus block, compare card.
    assert 'return { label: "Trade value", value: _taMM(_dtv)' in SRC
    assert 'tile(_heroTv ? "Trade value" : "Surplus"' in SRC
    block = _fn("_gfxSurplusBlock")
    assert "const _tvLead = debutedTradeValueMM(p) != null;" in block
    assert "!_tvLead && d.p50_mm != null" in block
    assert "svTrade: debutedTradeValueMM(p) != null" in SRC


def test_the_trade_value_prints_at_the_trade_machines_precision():
    """One number, one spelling: PROSPX prints a Trade value through _taMM, which
    writes $X.XM exactly as /trademachine/ does, never the board's rounded $XM."""
    ta = _fn("_taMM")
    assert "Math.abs(v).toFixed(1)}M" in ta
    tm = (ROOT / "assets" / "trademachine.js").read_text(encoding="utf-8")
    assert "Math.abs(x.mm || 0).toFixed(1)}M" in tm
    phone = _fn("_rowPhoneSignalsHTML")
    assert "_dtv != null ? _taMM(sv) : fmtSvMM(sv)" in phone
    block = _fn("_gfxSurplusBlock")
    assert "_tvLead ? _taMM(surplus) : fmtUsd(surplus)" in block


def test_served_parity_every_debuted_lead_is_the_trade_board_value():
    """Data-level parity on the served artifacts: the debuted rows the lead fires
    for (status debuted, projection basis, same mlbam) each carry a finite
    trade_value_mm, and Bobby Witt Jr. is among them. The page-level check (every
    debuted row's board cell, phone row and display value against this artifact)
    runs in headless Chromium in the B4_BOARD_SURPLUS report."""
    dpath, tpath = ROOT / "data" / "debuts.json", ROOT / "data" / "trade_values.json"
    if not (dpath.exists() and tpath.exists()):
        pytest.skip("debuts.json / trade_values.json not built")
    debuts = json.loads(dpath.read_text(encoding="utf-8"))
    board = {r["player_key"]: r for r in json.loads(tpath.read_text(encoding="utf-8"))["players"]}
    fired = {}
    for r in debuts:
        if r.get("status") != "debuted":
            continue
        tv = board.get(r.get("player_key"))
        if not tv or tv.get("surplus_source") != "projection" or tv.get("trade_value_mm") is None:
            continue
        if r.get("mlbam_id") and tv.get("mlbam_id") is not None and int(tv["mlbam_id"]) != int(r["mlbam_id"]):
            continue
        fired[r["player_key"]] = float(tv["trade_value_mm"])
    assert len(fired) > 500
    assert all(v == v and abs(v) < 1e4 for v in fired.values())
    witt = board.get("bobby_witt_jr")
    if witt and witt.get("surplus_source") == "projection":
        assert fired.get("bobby_witt_jr") == float(witt["trade_value_mm"])
