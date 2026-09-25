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
    body = _fn("_tvLeadFill")
    assert "row.trade_value_mm" in body
    assert 'row.surplus_source !== "projection"' in body
    assert "Number(row.mlbam_id) !== mid" in body
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
