# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 6 -- Draft War Room implied pick surplus: clemens_2026 tier value for the
drafted player's FV/role minus the cost (actual signing bonus if known, else the
expected slot). Real bonus/slot data only; no guessed bonuses."""
import pytest

import valuation_sets as vs


# --------------------------------------------------------------------------
# Pure helper
# --------------------------------------------------------------------------
def test_actual_bonus_basis():
    # 60 FV hitter -> clemens table $82M; actual $8M bonus -> $74M surplus.
    r = vs.implied_pick_surplus(60.0, False, bonus_usd=8_000_000, slot_usd=9_000_000)
    assert r["basis"] == "actual_bonus"
    assert r["tier_value_usd"] == pytest.approx(82_000_000, abs=1)
    assert r["surplus_usd"] == pytest.approx(74_000_000, abs=1)


def test_expected_slot_basis_when_unsigned():
    # No bonus yet -> price against the expected slot (the input, not a guess).
    r = vs.implied_pick_surplus(60.0, False, bonus_usd=None, slot_usd=9_000_000)
    assert r["basis"] == "expected_slot"
    assert r["surplus_usd"] == pytest.approx(73_000_000, abs=1)


def test_over_slot_uses_actual_bonus():
    # Over-slot deal: actual bonus (10M) exceeds slot (9M); we use the actual.
    r = vs.implied_pick_surplus(60.0, False, bonus_usd=10_000_000, slot_usd=9_000_000)
    assert r["basis"] == "actual_bonus"
    assert r["surplus_usd"] == pytest.approx(72_000_000, abs=1)


def test_role_split():
    # 50 FV: hitter tier $45M, pitcher tier $33.5M.
    h = vs.implied_pick_surplus(50.0, False, slot_usd=5_000_000)
    p = vs.implied_pick_surplus(50.0, True, slot_usd=5_000_000)
    assert h["tier_value_usd"] == pytest.approx(45_000_000, abs=1)
    assert p["tier_value_usd"] == pytest.approx(33_500_000, abs=1)
    assert h["surplus_usd"] > p["surplus_usd"]


def test_no_cost_returns_none():
    assert vs.implied_pick_surplus(60.0, False, bonus_usd=None, slot_usd=None) is None
    assert vs.implied_pick_surplus(None, False, slot_usd=5_000_000) is None


# --------------------------------------------------------------------------
# Live poller wiring
# --------------------------------------------------------------------------
def test_price_pick_carries_implied_surplus():
    from tools import draft_live_poller as dlp
    from prospect_savant import _norm_name
    name = "Test Hitter"
    board = {_norm_name(name): {"player_key": "test_hitter", "consensus_fv": 55.0,
                                "consensus_pick": 3, "position": "SS", "player_type": "COLh"}}
    row = {"pick_overall": 3, "player_name": name, "bonus_usd": 4_000_000,
           "slot_usd": 5_000_000, "round_label": "1", "team": "XYZ"}
    out = dlp._price_pick(row, board, {})
    assert out["implied_pick_surplus_basis"] == "actual_bonus"
    # 55 FV hitter clemens tier $55M minus $4M bonus.
    assert out["clemens_tier_value_usd"] == pytest.approx(55_000_000, abs=1)
    assert out["implied_pick_surplus_usd"] == pytest.approx(51_000_000, abs=1)


def test_price_pick_pitcher_role_and_slot_fallback():
    from tools import draft_live_poller as dlp
    from prospect_savant import _norm_name
    name = "Test Arm"
    board = {_norm_name(name): {"player_key": "test_arm", "consensus_fv": 50.0,
                               "consensus_pick": 10, "position": "RHP", "player_type": "COLp"}}
    row = {"pick_overall": 10, "player_name": name, "bonus_usd": None,
           "slot_usd": 5_000_000, "round_label": "1", "team": "XYZ"}
    out = dlp._price_pick(row, board, {})
    assert out["implied_pick_surplus_basis"] == "expected_slot"
    assert out["clemens_tier_value_usd"] == pytest.approx(33_500_000, abs=1)   # pitcher tier


def test_price_pick_off_board_no_surplus():
    from tools import draft_live_poller as dlp
    row = {"pick_overall": 500, "player_name": "Unknown Person", "bonus_usd": 100_000,
           "slot_usd": 150_000, "round_label": "16", "team": "XYZ"}
    out = dlp._price_pick(row, {}, {})
    assert out["implied_pick_surplus_usd"] is None   # not on our board -> no FV -> no guess
