# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Class-construction + ledger guards (pure unit tests, no network)."""

from __future__ import annotations

import pytest

import fa_class as fc


# ---- option-exercise heuristic (v1, documented) ------------------------------

def test_ufa_is_locked():
    assert fc.exercise_probability({"fa_type": "ufa"}) == {"enter_prob": 1.0, "method": "locked"}


def test_opt_out_walks_when_market_beats_option():
    # Market anchor $30M vs $20M opt-out price -> strongly enters the class.
    row = {"fa_type": "opt_out", "option_price_usd": 20_000_000,
           "market_value_aav_usd": 30_000_000}
    p = fc.exercise_probability(row)
    assert p["method"] == "heuristic_logistic_v1" and p["enter_prob"] > 0.8


def test_club_option_declined_when_overpriced():
    # Club holds a $25M option on a ~$10M player -> club declines -> enters.
    row = {"fa_type": "club_option", "option_price_usd": 25_000_000,
           "prev_war": 0.8}
    p = fc.exercise_probability(row)
    assert p["enter_prob"] > 0.8


def test_club_option_exercised_on_bargain():
    # $8M option on a 4-WAR player -> club keeps him -> stays OUT of class.
    row = {"fa_type": "club_option", "option_price_usd": 8_000_000,
           "prev_war": 4.0}
    p = fc.exercise_probability(row)
    assert p["enter_prob"] < 0.2


def test_anchor_fallback_chain_uses_prev_aav():
    # No market value, no prev WAR -> the player's own AAV anchors.
    row = {"fa_type": "opt_out", "option_price_usd": 55_300_000,
           "prev_aav_usd": 42_000_000}
    p = fc.exercise_probability(row)
    assert p["method"] == "heuristic_logistic_v1" and p["enter_prob"] < 0.2


def test_no_anchor_is_explicit_unknown():
    p = fc.exercise_probability({"fa_type": "opt_out", "option_price_usd": 10_000_000})
    assert p["enter_prob"] is None and p["method"] == "insufficient_data"


def test_mutual_option_uses_documented_prior():
    p = fc.exercise_probability({"fa_type": "mutual_option", "option_price_usd": 1})
    assert p["method"] == "mutual_prior"
    assert p["enter_prob"] == fc.get_config()["class_construction"]["mutual_option_decline_prob"]


# ---- retrospective ledger -----------------------------------------------------

_SIGNING = {"class_year": 2024, "years": 4, "guarantee_usd": 80_000_000,
            "mlb_deal": True, "player_key": "test_player", "player_name": "Test Player"}


def test_ledger_realized_vs_paid(monkeypatch):
    # Pin $/WAR at a flat $10M for arithmetic transparency.
    monkeypatch.setattr(fc, "dollars_per_war_for_season", lambda s, c=None: 10_000_000.0)
    led = fc.ledger_for_signing(_SIGNING, {"2024": 3.0, "2025": 1.0}, current_season=2026)
    assert led["elapsed_years"] == 2 and led["total_years"] == 4
    assert led["war_to_date"] == 4.0
    assert led["realized_value_usd"] == 40_000_000
    assert led["paid_to_date_usd"] == 40_000_000      # level proration: 80M * 2/4
    assert led["surplus_to_date_usd"] == 0
    assert led["complete"] is False


def test_ledger_missing_elapsed_season_counts_zero(monkeypatch):
    """A signed player with NO WAR row in an elapsed season produced
    nothing that year — the ledger scores 0 for it (honest), but a player
    with no WAR resolution at all is skipped (never ghost-scored)."""
    monkeypatch.setattr(fc, "dollars_per_war_for_season", lambda s, c=None: 10_000_000.0)
    led = fc.ledger_for_signing(_SIGNING, {"2024": 2.0}, current_season=2026)
    assert led["war_to_date"] == 2.0                  # 2025 absent -> 0
    assert fc.ledger_for_signing(_SIGNING, None, current_season=2026) is None


def test_ledger_skips_milb_and_unstarted_deals():
    assert fc.ledger_for_signing({**_SIGNING, "mlb_deal": False}, {"2024": 1.0}) is None
    assert fc.ledger_for_signing({**_SIGNING, "class_year": 2030}, {}, current_season=2026) is None


def test_dpw_prefers_estimated_series(monkeypatch):
    """When the Stage-3 market model has written the per-winter $/WAR
    series, the ledger uses IT — the exact season when present, the
    nearest winter escalated otherwise."""
    series = {2024: 15_000_000.0, 2026: 15_300_000.0}
    monkeypatch.setattr(fc, "_dpw_series", lambda: series)
    assert fc.dollars_per_war_for_season(2026) == 15_300_000.0
    # 2028 absent -> nearest (2026) escalated two years at 5%
    assert fc.dollars_per_war_for_season(2028) == pytest.approx(
        15_300_000 * 1.05 ** 2, rel=1e-6)


def test_dpw_backcast_fallback_deescalates(monkeypatch):
    """Without the estimated series (fresh checkout, pre-gate), the
    documented v1 fallback backcasts the framework flat rate."""
    monkeypatch.setattr(fc, "_dpw_series", lambda: {})
    cur = fc.dollars_per_war_for_season(2026, current_season=2026)
    old = fc.dollars_per_war_for_season(2015, current_season=2026)
    assert cur > old > 0
    # 11 years of the framework's configured escalation
    assert old == pytest.approx(cur / (1.05 ** 11), rel=1e-6)
