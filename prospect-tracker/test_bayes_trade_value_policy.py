from __future__ import annotations

import pytest

from bayes_trade_value import (
    bayesian_trade_value,
    archetype_policy_adjustment,
    compute_all_trade_values,
    _exposure_weighted_career_war,
    _contract_surplus_mm,
    multiposition_bonus_mm,
)


def _base_debuted_player(**overrides):
    player = {
        "player_key": "test_player",
        "player_name": "Test Player",
        "org": "TST",
        "status": "debuted",
        "position": "C",
        "is_pitcher": False,
        "fv_close": 60.0,
        "age": 21.9,
        "current_level": "MLB",
        "career_war": {
            "war_per_yr": 0.0,
            "war_seasons_count": 2,
            "seasons": {"2025": 0.0, "2026": 0.0},
        },
        "career_stats": [
            {"level": "MLB", "season": 2026, "games": 90, "pa": 350},
            {"level": "MLB", "season": 2025, "games": 20, "pa": 70},
        ],
        "statline": {"pa": 350, "k_pct": 22.0, "bb_pct": 9.0, "woba": 0.335},
        "statcast_metrics": {
            "contact_quality": {
                "xwoba_est": 0.345,
                "avg_ev": 90.5,
                "barrel_pct": 9.0,
            }
        },
        "roster_status": {"mlb_debut_date": "2025-06-01", "options_used": 0},
        "current_contract": {"signed_through": 2034, "aav_usd": 4_000_000},
        "tools": {},
        "acquisition": {},
    }
    player.update(overrides)
    return player


def test_young_premium_debuted_player_keeps_prior_floor() -> None:
    player = _base_debuted_player()
    out = bayesian_trade_value(player)

    assert "young_premium_confirming" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] >= out["prior_surplus_mm"] * 0.82 - 0.2
    assert "archetype_posterior_floor" in out["inputs_available"]


def test_older_pedigree_breakout_gets_group_floor() -> None:
    player = _base_debuted_player(
        player_key="older_breakout",
        player_name="Older Breakout",
        position="3B/OF/1B",
        fv_close=55.0,
        age=26.6,
        career_war={
            "war_per_yr": 1.1,
            "war_seasons_count": 4,
            "seasons": {"2023": 0.4, "2024": 0.6, "2025": 0.8, "2026": 2.2},
        },
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 80, "pa": 340},
            {"level": "MLB", "season": 2025, "games": 120, "pa": 480},
        ],
        statline={"pa": 340, "k_pct": 17.0, "bb_pct": 10.5, "woba": 0.375, "iso": 0.210},
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.382,
                "avg_ev": 91.8,
                "barrel_pct": 12.0,
            }
        },
        current_contract={"signed_through": 2028, "aav_usd": 2_000_000},
    )
    out = bayesian_trade_value(player)

    assert "older_pedigree_breakout" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] >= out["prior_surplus_mm"] * 0.50 - 0.2


def test_stale_mlb_prior_blocks_veteran_rental_pedigree_floor() -> None:
    player = _base_debuted_player(
        player_key="stale_prior_rental",
        player_name="Stale Prior Rental",
        position="INF",
        fv_close=65.0,
        age=29.5,
        career_war={
            "war_per_yr": 2.3,
            "war_seasons_count": 9,
            "seasons": {
                "2018": 3.4,
                "2019": 2.9,
                "2020": 0.0,
                "2021": 0.7,
                "2022": 4.1,
                "2023": 2.9,
                "2024": 1.9,
                "2025": 3.0,
                "2026": 1.8,
            },
        },
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 39, "pa": 145},
            {"level": "MLB", "season": 2025, "games": 150, "pa": 610},
            {"level": "MLB", "season": 2024, "games": 155, "pa": 630},
            {"level": "MLB", "season": 2023, "games": 158, "pa": 650},
        ],
        statline={"pa": 145, "k_pct": 18.3, "bb_pct": 14.9, "woba": 0.335, "iso": 0.096},
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.282,
                "avg_ev": 85.3,
                "barrel_pct": 7.9,
            }
        },
        current_contract={
            "signed_through": 2026,
            "aav_usd": 22_025_000,
            "salary_usd": 22_025_000,
        },
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="INF",
        age=29.5,
        fv=65.0,
        prior_surplus_mm=127.3,
        posterior_surplus_mm=20.0,
        true_talent_war=3.0,
        remaining_control_years=1.0,
        authenticity=0.98,
        worriedness={"score": 0.16},
    )

    assert "stale_mlb_prior" in policy["tags"]
    assert "older_pedigree_breakout" not in policy["tags"]
    assert policy["posterior_floor_mm"] == 0.0


def test_low_prior_breakout_is_discounted_before_full_trial() -> None:
    player = _base_debuted_player(
        position="OF",
        fv_close=45.0,
        age=23.6,
        career_stats=[{"level": "MLB", "season": 2026, "games": 45, "pa": 180}],
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="OF",
        age=23.6,
        fv=45.0,
        prior_surplus_mm=7.0,
        posterior_surplus_mm=14.0,
        true_talent_war=1.0,
        remaining_control_years=5.0,
        authenticity=1.0,
        worriedness={"score": 0.0},
    )

    assert "older_low_prior_breakout_trial" in policy["tags"]
    assert policy["posterior_multiplier"] < 1.0


def test_low_stuff_command_pitcher_gets_small_sample_discount() -> None:
    player = _base_debuted_player(
        position="SP",
        is_pitcher=True,
        fv_close=45.0,
        age=26.9,
        career_stats=[{"level": "MLB", "season": 2026, "ip": 72.0}],
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 55.0, "avg_stuff_plus": 90.0},
                    {"pitch_type": "CH", "usage_pct": 25.0, "avg_stuff_plus": 98.0},
                ]
            }
        },
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=True,
        position="SP",
        age=26.9,
        fv=45.0,
        prior_surplus_mm=20.0,
        posterior_surplus_mm=35.0,
        true_talent_war=2.3,
        remaining_control_years=5.0,
        authenticity=1.0,
        worriedness={"score": 0.0},
    )

    assert "command_pitcher_small_sample" in policy["tags"]
    assert policy["posterior_multiplier"] == pytest.approx(0.82)


def test_young_rookie_hitter_confirming_gets_prior_floor() -> None:
    player = _base_debuted_player(
        position="LF",
        fv_close=57.0,
        age=23.4,
        career_stats=[{"level": "MLB", "season": 2026, "games": 73, "pa": 269}],
        statline={"pa": 269, "k_pct": 21.9, "bb_pct": 6.5, "woba": 0.315, "iso": 0.137},
        statcast_metrics={"contact_quality": {"xwoba_est": 0.263, "barrel_pct": 9.3, "avg_ev": 90.1}},
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="LF",
        age=23.4,
        fv=57.0,
        prior_surplus_mm=45.8,
        posterior_surplus_mm=17.1,
        true_talent_war=0.66,
        remaining_control_years=6.0,
        authenticity=1.0,
        worriedness={"score": 0.0},
    )

    assert "young_rookie_hitter_confirming" in policy["tags"]
    assert policy["posterior_floor_mm"] == pytest.approx(29.8)


def test_stuff_supported_pitcher_keeps_prior_floor() -> None:
    player = _base_debuted_player(
        position="SP",
        is_pitcher=True,
        fv_close=53.0,
        age=27.8,
        career_stats=[{"level": "MLB", "season": 2024, "ip": 20.1}],
        statline={"ip": 32.0, "k_pct": 29.9, "bb_pct": 5.2, "era": "2.81"},
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 38.4, "avg_stuff_plus": 108.0},
                    {"pitch_type": "SL", "usage_pct": 21.7, "avg_stuff_plus": 111.0},
                    {"pitch_type": "CU", "usage_pct": 11.2, "avg_stuff_plus": 109.0},
                ]
            }
        },
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=True,
        position="SP",
        age=27.8,
        fv=53.0,
        prior_surplus_mm=23.1,
        posterior_surplus_mm=21.5,
        true_talent_war=0.89,
        remaining_control_years=4.0,
        authenticity=0.9,
        worriedness={"score": 0.0},
    )

    assert "stuff_supported_pitcher" in policy["tags"]
    assert policy["posterior_floor_mm"] == pytest.approx(24.3)


def test_active_arm_injury_low_stuff_pitcher_gets_discount() -> None:
    player = _base_debuted_player(
        position="SP",
        is_pitcher=True,
        fv_close=50.0,
        age=25.0,
        tools={"composite_stuff_plus": 91.0},
        roster_status={
            "mlb_debut_date": "2025-04-27",
            "options_used": 1,
            "injury_history": [
                {
                    "since": "2026-02-16",
                    "until": None,
                    "type": "60-day",
                    "reason": "Recovery from torn UCL in right arm",
                    "active": True,
                }
            ],
        },
        career_stats=[{"level": "MLB", "season": 2025, "ip": 81.1}],
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=True,
        position="SP",
        age=25.0,
        fv=50.0,
        prior_surplus_mm=18.9,
        posterior_surplus_mm=15.9,
        true_talent_war=0.45,
        remaining_control_years=5.0,
        authenticity=1.0,
        worriedness={"score": 0.0},
    )

    assert "injured_low_stuff_pitcher" in policy["tags"]
    assert "active_injured_starter_no_current_season" in policy["tags"]
    assert policy["posterior_multiplier"] == pytest.approx(0.65 * 0.72)


def test_expensive_nonstar_veteran_gets_contract_discount() -> None:
    player = _base_debuted_player(
        position="SS",
        fv_close=60.0,
        age=28.3,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 67, "pa": 269},
            {"level": "MLB", "season": 2025, "games": 139, "pa": 582},
            {"level": "MLB", "season": 2024, "games": 81, "pa": 311},
            {"level": "MLB", "season": 2023, "games": 135, "pa": 571},
        ],
        current_contract={"salary_usd": 42_000_000, "signed_through": 2028},
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="SS",
        age=28.3,
        fv=60.0,
        prior_surplus_mm=80.7,
        posterior_surplus_mm=12.5,
        true_talent_war=2.43,
        remaining_control_years=3.0,
        authenticity=1.0,
        worriedness={"score": 0.06},
    )

    assert "stale_mlb_prior" in policy["tags"]
    assert "expensive_nonstar_veteran" in policy["tags"]
    assert policy["posterior_multiplier"] == pytest.approx(0.65)


def test_stale_affiliated_debuted_player_is_excluded_from_export() -> None:
    stale = _base_debuted_player(
        player_key="stale_debuted",
        player_name="Stale Debuted",
        status="debuted",
        org="CHW",
        position="OF",
        fv_close=50.0,
        career_stats=[{"level": "AAA", "season": 2022, "games": 9, "ab": 25}],
        statline=None,
        current_season_statlines=[],
        current_contract=None,
        roster_status={"on_40_man": False, "injury_history": []},
    )
    commissioner = _base_debuted_player(
        player_key="commissioner_debuted",
        player_name="Commissioner Debuted",
        status="debuted",
        org="Office of the Commissioner",
        position="OF",
        fv_close=50.0,
        career_stats=[{"level": "MLB", "season": 2026, "games": 10, "ab": 20}],
    )
    active = _base_debuted_player(
        player_key="eligible_active",
        player_name="Eligible Active",
        status="active",
        org="TST",
        position="SS",
        fv_close=50.0,
    )

    out = compute_all_trade_values([stale, commissioner, active])

    assert {p["player_key"] for p in out} == {"eligible_active"}


def test_post_peak_expensive_middle_infielder_suppresses_additive_floors() -> None:
    player = _base_debuted_player(
        position="SS",
        fv_close=55.0,
        age=31.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 67, "pa": 269},
            {"level": "MLB", "season": 2025, "games": 160, "pa": 620},
            {"level": "MLB", "season": 2024, "games": 160, "pa": 620},
            {"level": "MLB", "season": 2023, "games": 149, "pa": 580},
        ],
        current_contract={"salary_usd": 26_000_000, "signed_through": 2031},
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="SS",
        age=31.0,
        fv=55.0,
        prior_surplus_mm=41.8,
        posterior_surplus_mm=10.6,
        true_talent_war=2.53,
        remaining_control_years=6.0,
        authenticity=0.94,
        worriedness={"score": 0.45},
    )

    assert "post_peak_expensive_middle_infielder" in policy["tags"]
    assert policy["posterior_multiplier"] == pytest.approx(0.20)
    assert policy["features"]["suppress_additive_floors"] is True


def test_no_power_premium_position_does_not_get_breakout_floor() -> None:
    player = _base_debuted_player(
        player_key="no_power_ss",
        position="SS",
        fv_close=60.0,
        age=25.1,
        statline={"pa": 420, "k_pct": 21.0, "bb_pct": 15.0, "woba": 0.315, "iso": 0.113},
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.273,
                "avg_ev": 87.8,
                "barrel_pct": 4.5,
            }
        },
        career_stats=[{"level": "MLB", "season": 2026, "games": 100, "pa": 420}],
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="SS",
        age=25.1,
        fv=60.0,
        prior_surplus_mm=72.0,
        posterior_surplus_mm=25.0,
        true_talent_war=2.3,
        remaining_control_years=3.0,
        authenticity=0.80,
        worriedness={"score": 0.08},
    )

    assert "older_pedigree_breakout" not in policy["tags"]
    assert "premium_position_breakout" not in policy["tags"]
    assert "current_offense_not_supporting_prior" in policy["tags"]
    assert policy["posterior_floor_mm"] == 0.0
    assert policy["posterior_multiplier"] < 1.0


def test_long_sample_high_prior_underachiever_reverses_prior() -> None:
    player = _base_debuted_player(
        player_key="long_sample_underachiever",
        position="SS",
        fv_close=60.0,
        age=25.1,
        statline={"pa": 420, "k_pct": 21.0, "bb_pct": 15.0, "woba": 0.315, "iso": 0.113},
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.273,
                "avg_ev": 87.8,
                "barrel_pct": 4.5,
            }
        },
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 100, "pa": 420},
            {"level": "MLB", "season": 2025, "games": 153, "pa": 600},
            {"level": "MLB", "season": 2024, "games": 160, "pa": 640},
        ],
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=False,
        position="SS",
        age=25.1,
        fv=60.0,
        prior_surplus_mm=72.0,
        posterior_surplus_mm=38.0,
        true_talent_war=2.3,
        remaining_control_years=3.0,
        authenticity=0.80,
        worriedness={"score": 0.08},
    )

    assert "high_prior_mlb_underachiever" in policy["tags"]
    assert "current_offense_not_supporting_prior" not in policy["tags"]
    assert policy["posterior_multiplier"] == pytest.approx(0.45)


def test_young_elite_stuff_pitcher_keeps_prior_floor() -> None:
    player = _base_debuted_player(
        position="SP",
        is_pitcher=True,
        fv_close=60.0,
        age=23.2,
        tools={"composite_stuff_plus": 125, "composite_cmd_plus": 122},
        career_stats=[{"level": "MLB", "season": 2026, "ip": 58.2}],
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=True,
        position="SP",
        age=23.2,
        fv=60.0,
        prior_surplus_mm=69.0,
        posterior_surplus_mm=29.0,
        true_talent_war=2.05,
        remaining_control_years=3.0,
        authenticity=0.54,
        worriedness={"score": 0.0},
    )

    assert "young_elite_stuff_pitcher" in policy["tags"]
    assert policy["posterior_floor_mm"] >= 44.0


def test_generic_lhp_with_starter_workload_gets_starter_stuff_floor() -> None:
    player = _base_debuted_player(
        position="LHP",
        is_pitcher=True,
        fv_close=57.0,
        age=23.6,
        tools={"composite_stuff_plus": 105, "composite_cmd_plus": 104},
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 11, "ip": 64.1},
            {"level": "MLB", "season": 2025, "games": 5, "ip": 16.1},
        ],
        statline={"games": 11, "ip": 64.1, "k_pct": 23.8, "bb_pct": 6.9, "era": "3.08"},
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 42.0, "avg_stuff_plus": 108.0},
                    {"pitch_type": "SL", "usage_pct": 31.0, "avg_stuff_plus": 105.0},
                    {"pitch_type": "CH", "usage_pct": 12.0, "avg_stuff_plus": 101.0},
                ]
            }
        },
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=True,
        position="RP",
        age=23.6,
        fv=57.0,
        prior_surplus_mm=7.8,
        posterior_surplus_mm=16.9,
        true_talent_war=0.82,
        remaining_control_years=5.0,
        authenticity=0.90,
        worriedness={"score": 0.0},
    )

    assert policy["features"]["starter_workload"] is True
    assert "young_elite_stuff_pitcher" in policy["tags"]
    assert policy["posterior_floor_mm"] > 25.0


def test_generic_p_post_callup_starter_is_inferred_from_ip_per_game() -> None:
    player = _base_debuted_player(
        player_key="post_callup_starter",
        position="P",
        is_pitcher=True,
        fv_close=53.0,
        age=23.2,
        career_war={
            "seasons": {"2026": 1.31},
            "career_war": 1.31,
            "war_per_yr": 1.31,
            "war_seasons_count": 1,
        },
        career_stats=[
            {"season": 2026, "level": "MLB", "games": 3, "ip": 18.1, "k_pct": 17.8, "bb_pct": 6.8},
            {"season": 2026, "level": "AAA", "games": 9, "ip": 38.0, "k_pct": 33.1, "bb_pct": 11.8},
        ],
        statline={"level": "MLB", "season": 2026, "games": 3, "ip": 18.1, "k_pct": 17.8, "bb_pct": 6.8, "era": "2.45"},
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 45.0, "avg_stuff_plus": 106.0},
                    {"pitch_type": "SL", "usage_pct": 30.0, "avg_stuff_plus": 105.0},
                ]
            }
        },
    )

    out = bayesian_trade_value(player)

    assert out["position"] == "SP"
    assert out["scarcity_mult"] == pytest.approx(1.13)
    assert out["archetype_policy"]["features"]["starter_workload"] is True


def test_bad_pitcher_cup_of_coffee_does_not_dominate_current_breakout() -> None:
    player = _base_debuted_player(
        player_key="young_starter_cup_of_coffee",
        position="LHP",
        is_pitcher=True,
        fv_close=57.0,
        age=23.6,
        current_level="MLB",
        career_war={
            "seasons": {"2025": -0.32, "2026": 0.90},
            "career_war": 0.58,
            "war_per_yr": 0.29,
            "war_seasons_count": 2,
        },
        career_stats=[
            {"season": 2026, "level": "MLB", "games": 11, "ip": 64.1, "k_pct": 23.8, "bb_pct": 6.9},
            {"season": 2025, "level": "MLB", "games": 7, "ip": 16.1, "k_pct": 25.7, "bb_pct": 10.8},
        ],
        statline={"level": "MLB", "season": 2026, "games": 11, "ip": 64.1, "k_pct": 23.8, "bb_pct": 6.9, "era": "3.08"},
        tools={"composite_stuff_plus": 105, "composite_cmd_plus": 104},
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 42.0, "avg_stuff_plus": 108.0},
                    {"pitch_type": "SL", "usage_pct": 31.0, "avg_stuff_plus": 105.0},
                ]
            }
        },
    )

    out = bayesian_trade_value(player)

    assert out["position"] == "SP"
    assert out["true_talent_war"] >= 1.30
    assert out["archetype_policy"]["posterior_floor_mm"] >= 30.0


def test_full_season_denominators_are_role_specific() -> None:
    starter = {
        "career_war": {"seasons": {"2026": 1.0}},
        "career_stats": [{"season": 2026, "level": "MLB", "ip": 75.0}],
    }
    reliever = {
        "career_war": {"seasons": {"2026": 1.0}},
        "career_stats": [{"season": 2026, "level": "MLB", "ip": 22.5}],
    }
    hitter = {
        "career_war": {"seasons": {"2026": 1.0}},
        "career_stats": [{"season": 2026, "level": "MLB", "pa": 300}],
    }
    catcher = {
        "career_war": {"seasons": {"2026": 1.0}},
        "career_stats": [{"season": 2026, "level": "MLB", "pa": 190}],
    }

    assert _exposure_weighted_career_war(starter, True, "SP")[0] == pytest.approx(2.0)
    assert _exposure_weighted_career_war(reliever, True, "RP")[0] == pytest.approx(2.0)
    assert _exposure_weighted_career_war(hitter, False, "OF")[0] == pytest.approx(2.0)
    assert _exposure_weighted_career_war(catcher, False, "C")[0] == pytest.approx(2.0)


def test_low_prior_partial_sample_hitter_gets_surplus_cap() -> None:
    player = _base_debuted_player(
        player_key="low_prior_partial_hitter",
        position="INF",
        fv_close=42.0,
        age=28.4,
        career_war={
            "seasons": {"2025": 1.9, "2026": -0.23},
            "career_war": 1.67,
            "war_per_yr": 0.83,
            "war_seasons_count": 2,
        },
        career_stats=[
            {"season": 2026, "level": "MLB", "games": 10, "ab": 14, "iso": 0.072, "k_pct": 13.3, "ops_plus_level": -70},
            {"season": 2025, "level": "MLB", "games": 76, "ab": 174, "iso": 0.104, "k_pct": 23.6, "ops_plus_level": -5},
        ],
        statline={"level": "AAA", "games": 3, "ab": 9, "iso": 0.334, "k_pct": 10.0},
    )

    out = bayesian_trade_value(player)

    assert "unsupported_partial_surplus_cap" in out["inputs_available"]
    assert out["trade_value_mm"] < 10.0


def test_no_power_infielder_partial_sample_suppresses_defensive_floor() -> None:
    player = _base_debuted_player(
        player_key="no_power_backend_inf",
        position="SS",
        fv_close=52.0,
        age=24.8,
        career_war={
            "seasons": {"2025": 0.22, "2026": 0.68},
            "career_war": 0.90,
            "war_per_yr": 0.45,
            "war_seasons_count": 2,
        },
        career_stats=[
            {"season": 2026, "level": "MLB", "games": 33, "ab": 98, "iso": 0.102, "k_pct": 28.6, "ops_plus_level": -2},
            {"season": 2025, "level": "MLB", "games": 29, "ab": 84, "iso": 0.120, "k_pct": 36.1, "ops_plus_level": -8},
        ],
        statline={"level": "MLB", "games": 33, "ab": 98, "iso": 0.102, "k_pct": 28.6, "ops_plus_level": -2},
        tools={"defense": 55.0},
    )

    out = bayesian_trade_value(player)

    assert "no_power_infield_floor_suppression" in out["inputs_available"]
    assert out["defensive_floor_mm"] == 0.0
    assert out["trade_value_mm"] < 30.0


def test_stuff_command_post_callup_starter_outranks_no_power_infielder() -> None:
    no_power_inf = _base_debuted_player(
        player_key="no_power_backend_inf",
        position="SS",
        fv_close=52.0,
        age=24.8,
        career_war={"seasons": {"2025": 0.22, "2026": 0.68}, "career_war": 0.90, "war_per_yr": 0.45, "war_seasons_count": 2},
        career_stats=[
            {"season": 2026, "level": "MLB", "games": 33, "ab": 98, "iso": 0.102, "k_pct": 28.6, "ops_plus_level": -2},
            {"season": 2025, "level": "MLB", "games": 29, "ab": 84, "iso": 0.120, "k_pct": 36.1, "ops_plus_level": -8},
        ],
        statline={"level": "MLB", "games": 33, "ab": 98, "iso": 0.102, "k_pct": 28.6, "ops_plus_level": -2},
        tools={"defense": 55.0},
    )
    starter = _base_debuted_player(
        player_key="stuff_command_starter",
        position="P",
        is_pitcher=True,
        fv_close=53.0,
        age=23.2,
        career_war={"seasons": {"2026": 1.31}, "career_war": 1.31, "war_per_yr": 1.31, "war_seasons_count": 1},
        career_stats=[{"season": 2026, "level": "MLB", "games": 3, "ip": 18.1, "k_pct": 17.8, "bb_pct": 6.8}],
        statline={"level": "MLB", "games": 3, "ip": 18.1, "k_pct": 17.8, "bb_pct": 6.8},
        statcast_metrics={"pitch_movement": {"pitch_summary": [
            {"pitch_type": "FF", "usage_pct": 45.0, "avg_stuff_plus": 106.0},
            {"pitch_type": "SL", "usage_pct": 30.0, "avg_stuff_plus": 105.0},
        ]}},
    )

    out_inf = bayesian_trade_value(no_power_inf)
    out_sp = bayesian_trade_value(starter)

    assert "young_stuff_command_starter" in out_sp["archetype_policy"]["tags"]
    assert out_sp["trade_value_mm"] > out_inf["trade_value_mm"]


def test_unsupported_partial_sample_pitcher_stays_near_prior() -> None:
    player = _base_debuted_player(
        player_key="unsupported_partial_pitcher",
        position="RHP",
        is_pitcher=True,
        fv_close=52.0,
        age=24.3,
        career_war={
            "seasons": {"2024": 1.92, "2026": 0.59},
            "career_war": 2.51,
            "war_per_yr": 1.25,
            "war_seasons_count": 2,
        },
        career_stats=[
            {"season": 2026, "level": "MLB", "games": 11, "ip": 52.1, "k_pct": 18.1, "bb_pct": 12.1, "era": "4.82"},
            {"season": 2024, "level": "MLB", "games": 6, "ip": 30.2, "k_pct": 17.2, "bb_pct": 10.9, "era": "1.17"},
        ],
        statline={"level": "MLB", "games": 11, "ip": 52.1, "k_pct": 18.1, "bb_pct": 12.1, "era": "4.82"},
        tools={"composite_stuff_plus": 102, "composite_cmd_plus": 108},
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 45.0, "avg_stuff_plus": 100.0},
                    {"pitch_type": "CH", "usage_pct": 30.0, "avg_stuff_plus": 95.0},
                ]
            }
        },
    )

    out = bayesian_trade_value(player)

    assert out["posterior_surplus_mm"] <= out["prior_surplus_mm"] * 1.26


def test_contract_surplus_can_be_negative_for_underwater_deals() -> None:
    player = _base_debuted_player(
        position="1B",
        age=34.0,
        current_contract={
            "salary_by_year": {
                "2027": 30_000_000,
                "2028": 30_000_000,
            }
        },
    )

    assert _contract_surplus_mm(player, true_talent_war=0.5, remaining_years=2.0) < 0.0


def test_validated_late_pitcher_is_separate_from_command_risk() -> None:
    player = _base_debuted_player(
        position="SP",
        is_pitcher=True,
        age=26.7,
        career_stats=[{"level": "MLB", "season": 2025, "ip": 165.0}],
        statcast_metrics={
            "pitch_movement": {
                "pitch_summary": [
                    {"pitch_type": "FF", "usage_pct": 45.0, "avg_stuff_plus": 101.0},
                    {"pitch_type": "SL", "usage_pct": 35.0, "avg_stuff_plus": 108.0},
                ]
            }
        },
    )
    policy = archetype_policy_adjustment(
        player,
        is_mlb_player=True,
        is_pitcher=True,
        position="SP",
        age=26.7,
        fv=50.0,
        prior_surplus_mm=20.0,
        posterior_surplus_mm=35.0,
        true_talent_war=2.4,
        remaining_control_years=5.0,
        authenticity=1.0,
        worriedness={"score": 0.0},
    )

    assert "validated_late_pitcher" in policy["tags"]
    assert "command_pitcher_small_sample" not in policy["tags"]
    assert policy["posterior_multiplier"] > 1.0


def test_multiposition_bonus_rewards_meaningful_defensive_usage(monkeypatch) -> None:
    def fake_usage(player_key):
        assert player_key == "sal_stewart"
        return {
            "1B": {"games": 49, "games_started": 43, "innings": 368.2},
            "3B": {"games": 28, "games_started": 20, "innings": 189.2},
            "2B": {"games": 6, "games_started": 5, "innings": 38.0},
            "DH": {"games": 8, "games_started": 8, "innings": 0.0},
        }

    import fielding

    monkeypatch.setattr(fielding, "position_usage", fake_usage)

    bonus, usage = multiposition_bonus_mm(
        "sal_stewart",
        "1B",
        is_mlb_player=True,
        remaining_years=5.0,
        posterior_surplus_mm=150.0,
    )

    assert bonus == 4.5
    assert usage["meaningful_positions"] == ["1B", "3B", "2B"]
    assert "DH" in usage["positions"]


def test_multiposition_bonus_ignores_one_off_cameos(monkeypatch) -> None:
    def fake_usage(_player_key):
        return {
            "1B": {"games": 49, "games_started": 43, "innings": 368.2},
            "3B": {"games": 1, "games_started": 0, "innings": 2.0},
        }

    import fielding

    monkeypatch.setattr(fielding, "position_usage", fake_usage)

    bonus, usage = multiposition_bonus_mm(
        "corner_bat",
        "1B",
        is_mlb_player=True,
        remaining_years=5.0,
        posterior_surplus_mm=150.0,
    )

    assert bonus == 0.0
    assert usage["meaningful_positions"] == ["1B"]


def test_mlb_projection_anchor_caps_extra_worry_and_injury_discounts(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="established_regression",
        player_name="Established Regression",
        position="2B",
        age=29.0,
        career_stats=[
            {"level": "MLB", "season": 2024, "pa": 650},
            {"level": "MLB", "season": 2025, "pa": 640},
            {"level": "MLB", "season": 2026, "pa": 300},
        ],
        roster_status={
            "mlb_debut_date": "2022-04-01",
            "injury_history": [{"type": "hamstring", "season": 2026, "days": 45}],
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 100.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (1590.0, 0.0))
    monkeypatch.setattr(
        btv,
        "worriedness_score",
        lambda _player, _level_norms=None: {
            "score": 0.80,
            "type": "approach",
            "approach_signal": 0.80,
            "contact_signal": 0.0,
            "age_discount": 0.0,
        },
    )
    monkeypatch.setattr(btv, "_injury_discount", lambda _player: 0.20)

    out = btv.bayesian_trade_value(player)

    assert out["posterior_surplus_mm"] == 100.0
    assert out["injury_discount"] == 0.08
    assert "projection_anchor_discount_cap" in out["inputs_available"]
    assert out["trade_value_mm"] > 85.0


def test_projection_anchor_penalizes_older_speed_outfielder_bad_current_year(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="older_speed_of",
        player_name="Older Speed OF",
        position="OF",
        age=29.8,
        career_stats=[
            {
                "level": "MLB",
                "season": 2026,
                "games": 70,
                "ab": 280,
                "ops": ".641",
                "obp": ".263",
                "iso": 0.173,
                "sb": 11,
                "k_pct": 29.9,
                "ops_plus_level": 97,
            },
            {"level": "MLB", "season": 2025, "games": 157, "ab": 620, "sb": 24},
            {"level": "MLB", "season": 2024, "games": 160, "ab": 671, "sb": 34},
        ],
        statline={
            "level": "MLB",
            "games": 70,
            "ab": 280,
            "ops": ".641",
            "obp": ".263",
            "iso": 0.173,
            "sb": 11,
            "k_pct": 29.9,
            "ops_plus_level": 97,
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 100.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (1571.0, 0.0))
    monkeypatch.setattr(
        btv,
        "worriedness_score",
        lambda _player, _level_norms=None: {
            "score": 0.58,
            "type": "approach",
            "approach_signal": 0.90,
            "contact_signal": 0.0,
            "age_discount": 0.0,
        },
    )
    monkeypatch.setattr(btv, "_injury_discount", lambda _player: 0.20)

    out = btv.bayesian_trade_value(player)

    assert "mlb_projection_surplus_anchor" in out["inputs_available"]
    assert any(x.startswith("projection_anchor_current_form_") for x in out["inputs_available"])
    assert out["posterior_surplus_mm"] < 85.0
    assert out["injury_discount"] == 0.12
    assert out["trade_value_mm"] < 75.0


def test_projection_anchor_does_not_over_penalize_younger_infielder_soft_down_year(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="controlled_young_3b",
        player_name="Controlled Young 3B",
        position="3B",
        age=26.3,
        career_stats=[
            {
                "level": "MLB",
                "season": 2026,
                "games": 70,
                "ab": 270,
                "ops": ".692",
                "obp": ".321",
                "iso": 0.110,
                "sb": 8,
                "k_pct": 15.5,
                "ops_plus_level": 99,
            },
            {"level": "MLB", "season": 2025, "games": 155, "ab": 620, "sb": 20},
            {"level": "MLB", "season": 2024, "games": 145, "ab": 580, "sb": 25},
        ],
        statline={
            "level": "MLB",
            "games": 70,
            "ab": 270,
            "ops": ".692",
            "obp": ".321",
            "iso": 0.110,
            "sb": 8,
            "k_pct": 15.5,
            "ops_plus_level": 99,
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 100.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (1500.0, 0.0))

    out = btv.bayesian_trade_value(player)

    assert out["posterior_surplus_mm"] == 100.0
    assert not any(x.startswith("projection_anchor_current_form_") for x in out["inputs_available"])


def test_elite_young_cheap_slugger_uses_projection_anchor_before_full_established_pa(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="elite_young_slugger",
        player_name="Elite Young Slugger",
        position="1B",
        age=23.5,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 80, "pa": 360, "ab": 300},
            {"level": "MLB", "season": 2025, "games": 110, "pa": 480, "ab": 410},
        ],
        statline={
            "level": "MLB",
            "games": 80,
            "pa": 360,
            "iso": 0.280,
            "bb_pct": 16.0,
            "k_pct": 29.0,
            "ops": ".960",
            "ops_plus_level": 150,
        },
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.390,
                "barrel_pct": 18.0,
                "avg_ev": 94.0,
            }
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 125.0)

    out = btv.bayesian_trade_value(player)

    assert out["posterior_surplus_mm"] == 125.0
    assert "elite_young_slugger_projection_anchor" in out["inputs_available"]


def test_projection_anchor_hits_low_power_contact_freefall(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="contact_freefall",
        player_name="Contact Freefall",
        position="LF",
        age=28.8,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 75, "pa": 290},
            {"level": "MLB", "season": 2025, "games": 150, "pa": 650},
            {"level": "MLB", "season": 2024, "games": 130, "pa": 550},
        ],
        statline={
            "level": "MLB",
            "games": 75,
            "pa": 290,
            "ops": ".570",
            "obp": ".315",
            "iso": 0.045,
            "k_pct": 10.0,
            "ops_plus_level": 70,
        },
        statcast_metrics={
            "contact_quality": {
                "avg_ev": 83.0,
                "barrel_pct": 0.5,
                "xwoba_est": 0.300,
            }
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 50.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (1490.0, 0.0))

    out = btv.bayesian_trade_value(player)

    assert out["posterior_surplus_mm"] < 36.0
    assert any(x.startswith("projection_anchor_current_form_") for x in out["inputs_available"])


def test_older_low_prior_corner_bat_must_be_elite_to_keep_full_anchor(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="low_prior_corner",
        player_name="Low Prior Corner",
        position="RF",
        age=27.0,
        fv_close=50.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 75, "pa": 315},
            {"level": "MLB", "season": 2025, "games": 120, "pa": 420},
            {"level": "MLB", "season": 2024, "games": 120, "pa": 430},
        ],
        statline={
            "level": "MLB",
            "games": 75,
            "pa": 315,
            "iso": 0.158,
            "ops_plus_level": 110,
        },
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.337,
                "barrel_pct": 11.0,
                "avg_ev": 90.0,
            }
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 120.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (1165.0, 0.0))

    out = btv.bayesian_trade_value(player)

    assert "low_prior_corner_bat_not_elite" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] < 90.0


def test_low_prior_nonimpact_mlb_bat_does_not_clear_top_prospect_band(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="low_prior_nonimpact_mlb_bat",
        player_name="Low Prior Nonimpact MLB Bat",
        position="3B",
        age=26.3,
        fv_close=42.0,
        career_war={
            "war_per_yr": 1.85,
            "war_seasons_count": 2,
            "seasons": {"2025": 2.69, "2026": 1.02},
        },
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 68, "pa": 242},
            {"level": "MLB", "season": 2025, "games": 136, "pa": 480},
        ],
        statline={
            "level": "MLB",
            "season": 2026,
            "games": 68,
            "pa": 242,
            "iso": 0.146,
            "ops_plus_level": 97,
            "k_pct": 14.2,
            "bb_pct": 5.4,
        },
        statcast_metrics={
            "contact_quality": {
                "xwoba_est": 0.220,
                "barrel_pct": 3.2,
                "avg_ev": 84.2,
            }
        },
        current_contract={"salary_usd": 780_000},
    )
    prospect = {
        "player_key": "live_top_prospect",
        "player_name": "Live Top Prospect",
        "org": "TST",
        "status": "active",
        "position": "SS",
        "is_pitcher": False,
        "fv_close": 52.0,
        "age": 22.0,
        "current_level": "AA",
        "statline": {"level": "AA", "games": 70, "pa": 300, "ops": ".770", "iso": 0.145, "k_pct": 22.0},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 29.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (722.0, 0.0))

    mlb_out = btv.bayesian_trade_value(player)
    prospect_out = btv.bayesian_trade_value(prospect)

    assert "low_prior_mlb_bat_not_impact" in mlb_out["archetype_policy"]["tags"]
    assert "archetype_suppress_additive_floors" in mlb_out["inputs_available"]
    assert mlb_out["trade_value_mm"] < prospect_out["trade_value_mm"]


def test_current_relief_usage_prevents_starter_floor() -> None:
    player = _base_debuted_player(
        player_key="current_reliever",
        player_name="Current Reliever",
        position="RHP",
        is_pitcher=True,
        fv_close=50.0,
        age=25.2,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 30, "ip": 27.2, "k_pct": 26.0, "bb_pct": 11.0},
            {"level": "MLB", "season": 2025, "games": 60, "ip": 65.0},
            {"level": "MLB", "season": 2024, "games": 65, "ip": 61.0},
        ],
        statline={"level": "MLB", "games": 30, "ip": 27.2, "k_pct": 26.0, "bb_pct": 11.0, "era": "2.30"},
        tools={"composite_stuff_plus": 121},
    )

    out = bayesian_trade_value(player)

    assert out["position"] == "RP"
    assert "controlled_rotation_asset" not in out["archetype_policy"]["tags"]
    assert out["trade_value_mm"] < 45.0


def test_active_prior_season_stuff_starter_does_not_get_young_controlled_floor() -> None:
    player = _base_debuted_player(
        player_key="active_tj_stuff_starter",
        player_name="Active TJ Stuff Starter",
        position="SP",
        is_pitcher=True,
        fv_close=55.0,
        age=24.8,
        current_level="AAA",
        career_war={"seasons": {"2025": -0.1}, "career_war": -0.1, "war_per_yr": -0.1, "war_seasons_count": 1},
        career_stats=[{"level": "MLB", "season": 2025, "games": 21, "ip": 65.2, "k_pct": 22.8, "bb_pct": 12.4}],
        statline={
            "level": "MLB",
            "season": 2025,
            "is_prior_season": True,
            "games": 21,
            "ip": 65.2,
            "k_pct": 22.8,
            "bb_pct": 12.4,
            "stf_plus_periph": 97,
        },
        roster_status={
            "injury_history": [
                {"active": True, "type": "60-day", "reason": "Tommy John surgery", "since": "2026-03-01"}
            ]
        },
        current_contract={"signed_through": 2028, "salary_usd": 780_000},
        tools={"composite_stuff_plus": 104},
    )

    out = bayesian_trade_value(player)

    assert "young_controlled_stuff_starter" not in out["archetype_policy"]["tags"]
    assert "controlled_rotation_asset" not in out["archetype_policy"]["tags"]
    assert out["archetype_policy"]["features"]["active_injury"] is True


def test_active_injured_starter_without_current_season_gets_extra_discount() -> None:
    player = _base_debuted_player(
        player_key="injured_validated_starter",
        player_name="Injured Validated Starter",
        position="SP",
        is_pitcher=True,
        fv_close=55.0,
        age=26.1,
        career_stats=[
            {"level": "MLB", "season": 2025, "games": 28, "ip": 160.0, "k_pct": 25.5, "bb_pct": 6.5},
            {"level": "MLB", "season": 2024, "games": 20, "ip": 73.1},
        ],
        statline={
            "level": "MLB",
            "season": 2025,
            "is_prior_season": True,
            "games": 28,
            "ip": 160.0,
            "k_pct": 25.5,
            "bb_pct": 6.5,
            "era": "3.40",
        },
        roster_status={"injury_history": [{"active": True, "type": "60-day", "reason": "fractured elbow"}]},
        current_contract={"signed_through": 2030, "salary_usd": 1_000_000},
        tools={"composite_stuff_plus": 106},
    )

    out = bayesian_trade_value(player)

    assert "active_injured_starter_no_current_season" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] < 65.0


def test_elite_young_injured_starter_can_keep_phenom_exception() -> None:
    player = _base_debuted_player(
        player_key="elite_young_injured_starter",
        player_name="Elite Young Injured Starter",
        position="SP",
        is_pitcher=True,
        fv_close=60.0,
        age=23.2,
        career_stats=[{"level": "MLB", "season": 2025, "games": 24, "ip": 120.0, "k_pct": 30.0, "bb_pct": 8.0}],
        statline={
            "level": "MLB",
            "season": 2025,
            "is_prior_season": True,
            "games": 24,
            "ip": 120.0,
            "k_pct": 30.0,
            "bb_pct": 8.0,
        },
        roster_status={"injury_history": [{"active": True, "type": "60-day", "reason": "lat strain"}]},
        current_contract={"signed_through": 2029, "salary_usd": 1_000_000},
        tools={"composite_stuff_plus": 125},
    )

    out = bayesian_trade_value(player)

    assert "young_elite_stuff_pitcher" in out["archetype_policy"]["tags"]
    assert "active_injured_starter_no_current_season" not in out["archetype_policy"]["tags"]


def test_healthy_current_breakout_starter_gets_policy_floor() -> None:
    player = _base_debuted_player(
        player_key="healthy_breakout_starter",
        player_name="Healthy Breakout Starter",
        position="SP",
        is_pitcher=True,
        fv_close=55.0,
        age=27.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 16, "ip": 94.0, "k_pct": 27.2, "bb_pct": 7.3},
            {"level": "MLB", "season": 2025, "games": 28, "ip": 145.0},
        ],
        statline={
            "level": "MLB",
            "season": 2026,
            "games": 16,
            "ip": 94.0,
            "k_pct": 27.2,
            "bb_pct": 7.3,
            "era": "3.93",
            "stf_plus_periph": 107,
        },
        roster_status={"injury_history": []},
        current_contract={},
        tools={"composite_stuff_plus": 104, "command_plus": 112},
    )

    out = bayesian_trade_value(player)

    assert "healthy_breakout_starter" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] >= 62.0


def test_productive_established_starter_ages_less_harshly_than_bat() -> None:
    player = _base_debuted_player(
        player_key="productive_established_starter",
        player_name="Productive Established Starter",
        position="SP",
        is_pitcher=True,
        fv_close=42.0,
        age=31.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 14, "ip": 78.0, "k_pct": 23.5, "bb_pct": 7.2, "era": "2.80", "whip": 1.05},
            {"level": "MLB", "season": 2025, "games": 28, "ip": 150.0, "era": "2.95"},
            {"level": "MLB", "season": 2024, "games": 24, "ip": 120.0, "era": "2.90"},
        ],
        statline={
            "level": "MLB",
            "season": 2026,
            "games": 14,
            "ip": 78.0,
            "k_pct": 23.5,
            "bb_pct": 7.2,
            "era": "2.80",
            "whip": 1.05,
            "stf_plus_periph": 106,
        },
        career_war={"war_per_yr": 3.0, "war_seasons_count": 4, "seasons": {"2026": 2.0, "2025": 3.2}},
        roster_status={"injury_history": []},
        tools={"composite_stuff_plus": 96},
    )

    out = bayesian_trade_value(player)

    assert "productive_established_starter" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] >= 58.0


def test_failed_current_mlb_pitcher_trial_gets_discount() -> None:
    player = _base_debuted_player(
        player_key="failed_current_trial_arm",
        player_name="Failed Current Trial Arm",
        position="SP",
        is_pitcher=True,
        fv_close=53.0,
        age=23.7,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 3, "ip": 9.1, "k_pct": 12.7, "bb_pct": 21.8, "era": "14.46", "whip": 3.11, "era_minus_level": 342, "level_plus_pct": -242, "stf_plus_periph": 72},
            {"level": "AAA", "season": 2026, "games": 8, "ip": 18.0, "k_pct": 14.1, "bb_pct": 15.2, "era": "11.00"},
            {"level": "MLB", "season": 2025, "games": 10, "ip": 48.2, "k_pct": 21.6, "bb_pct": 9.0, "era": "3.14"},
        ],
        statline={
            "level": "MLB",
            "season": 2026,
            "games": 3,
            "ip": 9.1,
            "k_pct": 12.7,
            "bb_pct": 21.8,
            "era": "14.46",
            "whip": 3.11,
            "stf_plus_periph": 72,
            "is_prior_season": False,
        },
        career_war={"war_per_yr": 0.29, "war_seasons_count": 2, "seasons": {"2025": 1.21, "2026": -0.62}},
        roster_status={"injury_history": []},
        tools={"composite_stuff_plus": 103},
    )

    out = bayesian_trade_value(player)

    assert "failed_current_mlb_pitcher_trial" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] < 30.0


def test_brief_past_starts_do_not_make_current_reliever_a_starter() -> None:
    player = _base_debuted_player(
        player_key="brief_past_starter",
        player_name="Brief Past Starter",
        position="RHP",
        is_pitcher=True,
        fv_close=50.0,
        age=28.8,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 2, "ip": 3.2, "k_pct": 12.0, "bb_pct": 18.0},
            {"level": "MLB", "season": 2022, "games": 4, "ip": 24.0},
        ],
        statline={"level": "MLB", "games": 2, "ip": 3.2, "k_pct": 12.0, "bb_pct": 18.0, "era": "4.90"},
        tools={"composite_stuff_plus": 113},
    )

    out = bayesian_trade_value(player)

    assert out["position"] == "RP"
    assert "controlled_rotation_asset" not in out["archetype_policy"]["tags"]


def test_mlb_hitter_500_pa_projection_anchor_grounds_middling_bat(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="grounded_mlb_bat",
        player_name="Grounded MLB Bat",
        position="RF",
        age=24.5,
        fv_close=60.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 70, "pa": 260},
            {"level": "MLB", "season": 2025, "games": 90, "pa": 300},
        ],
        statline={"level": "MLB", "games": 70, "pa": 260, "ops": ".700", "ops_plus_level": 98, "iso": 0.150},
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 35.0)

    out = btv.bayesian_trade_value(player)

    assert "mlb_projection_surplus_anchor" in out["inputs_available"]
    assert out["posterior_surplus_mm"] < 45.0


def test_young_top_active_prospect_keeps_prior_floor() -> None:
    player = {
        "player_key": "young_fv55_1b",
        "player_name": "Young FV55 1B",
        "org": "TST",
        "status": "active",
        "position": "1B",
        "is_pitcher": False,
        "fv_close": 55.0,
        "age": 21.1,
        "current_level": "AAA",
        "statline": {"level": "AAA", "games": 25, "pa": 105, "ops": ".715", "iso": 0.126, "k_pct": 26.0, "bb_pct": 8.0},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "young_top_prospect_prior_floor" in out["inputs_available"]
    assert out["posterior_surplus_mm"] >= out["prior_surplus_mm"] * 1.1


def test_college_age_top_active_prospect_keeps_prior_floor() -> None:
    player = {
        "player_key": "college_age_top_arm",
        "player_name": "College Age Top Arm",
        "org": "TST",
        "status": "active",
        "position": "RHP",
        "is_pitcher": True,
        "fv_close": 50.0,
        "age": 23.8,
        "current_level": "AA",
        "statline": {"level": "AA", "games": 14, "ip": 63.0, "k_pct": 27.0, "bb_pct": 8.5, "era": "3.40"},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "young_top_prospect_prior_floor" in out["inputs_available"]
    assert out["trade_value_mm"] > 15.2


def test_fv50_active_prospect_gets_trade_rarity_floor() -> None:
    player = {
        "player_key": "fv50_trade_rare",
        "player_name": "FV50 Trade Rare",
        "org": "TST",
        "status": "active",
        "position": "1B",
        "is_pitcher": False,
        "fv_close": 50.0,
        "age": 24.4,
        "current_level": "AA",
        "statline": {"level": "AA", "games": 66, "pa": 275, "ops": ".760", "iso": 0.120, "k_pct": 36.0, "bb_pct": 3.0, "ops_plus_level": 101},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "fv50_trade_rarity_floor" in out["inputs_available"]
    assert "fv50_trade_rarity_trade_floor" in out["inputs_available"]
    assert out["posterior_surplus_mm"] >= 30.0
    assert out["trade_value_mm"] >= 30.0


def test_nonimpact_fv50_prospect_does_not_get_trade_rarity_floor() -> None:
    player = {
        "player_key": "nonimpact_fv50",
        "player_name": "Nonimpact FV50",
        "org": "TST",
        "status": "active",
        "position": "2B",
        "is_pitcher": False,
        "fv_close": 50.0,
        "age": 23.4,
        "current_level": "AAA",
        "statline": {"level": "AAA", "games": 65, "pa": 260, "ops": ".650", "iso": 0.060, "k_pct": 26.0, "ops_plus_level": 92},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "older_nonimpact_prospect_suppression" in out["inputs_available"]
    assert "fv50_trade_rarity_floor" not in out["inputs_available"]


def test_fv50_pitcher_prospect_near_age_26_keeps_trade_rarity_floor() -> None:
    player = {
        "player_key": "fv50_near_26_arm",
        "player_name": "FV50 Near 26 Arm",
        "org": "TST",
        "status": "active",
        "position": "LHP",
        "is_pitcher": True,
        "fv_close": 50.0,
        "age": 25.8,
        "current_level": "AAA",
        "statline": {"level": "AAA", "games": 17, "ip": 72.0, "k_pct": 24.0, "bb_pct": 9.0, "era": "3.90"},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "fv50_trade_rarity_floor" in out["inputs_available"]
    assert out["trade_value_mm"] >= 30.0


def test_recent_top100_active_prospect_gets_trade_market_floor() -> None:
    player = {
        "player_key": "recent_top100_cf",
        "player_name": "Recent Top100 CF",
        "org": "TST",
        "status": "active",
        "position": "CF",
        "is_pitcher": False,
        "fv_close": 54.0,
        "age": 23.0,
        "current_level": "AA",
        "statline": {"level": "AA", "games": 60, "pa": 260, "ops": ".940", "iso": 0.220, "k_pct": 22.0, "bb_pct": 17.0},
        "career_stats": [],
        "tools": {
            "history": [
                {"snapshot_date": "2026-06-03", "interval_label": "Baseball America 2026-06-03 Top 100"}
            ],
            "source_history": {
                "mlb_pipeline": [
                    {"snapshot_date": "2026-01-22", "interval_label": "MLB Pipeline 2026 Top 100"}
                ]
            },
        },
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "recent_top100_prospect_floor" in out["inputs_available"]
    assert out["trade_value_mm"] >= 55.0


def test_elite_early_debut_top100_keeps_prospect_market_floor() -> None:
    player = _base_debuted_player(
        player_key="elite_early_debut",
        player_name="Elite Early Debut",
        position="SS",
        fv_close=60.0,
        age=20.9,
        career_war={
            "war_per_yr": 0.0,
            "war_seasons_count": 1,
            "seasons": {"2026": 0.0},
        },
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 19, "pa": 69, "ops": ".650", "iso": 0.110, "k_pct": 31.0},
            {"level": "AAA", "season": 2026, "games": 38, "pa": 170, "ops": ".816", "iso": 0.214},
        ],
        statline={"level": "MLB", "games": 19, "pa": 69, "ops": ".650", "iso": 0.110, "k_pct": 31.0, "bb_pct": 7.0},
        statcast_metrics={"contact_quality": {"avg_ev": 87.0, "barrel_pct": 5.0}},
        current_contract={"signed_through": 2032, "aav_usd": 7_500_000},
        roster_status={"mlb_debut_date": "2026-05-20", "options_used": 0},
        tools={
            "history": [
                {"snapshot_date": "2026-06-03", "interval_label": "Baseball America 2026-06-03 Top 100"}
            ]
        },
    )

    out = bayesian_trade_value(player)

    assert "early_debut_top100_prospect_floor" in out["inputs_available"]
    assert out["posterior_surplus_mm"] >= 105.0
    assert out["trade_value_mm"] >= 95.0


def test_multi_season_top100_mlb_player_can_reverse_prior() -> None:
    player = _base_debuted_player(
        player_key="multi_season_unmet_prior",
        player_name="Multi Season Unmet Prior",
        position="SS",
        fv_close=60.0,
        age=25.2,
        career_war={
            "war_per_yr": 1.1,
            "war_seasons_count": 4,
            "seasons": {"2023": 1.0, "2024": 1.1, "2025": 1.0, "2026": 1.2},
        },
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 70, "pa": 285, "ops": ".665", "iso": 0.120, "k_pct": 26.5},
            {"level": "MLB", "season": 2025, "games": 155, "pa": 620, "ops": ".675", "iso": 0.130, "k_pct": 27.0},
            {"level": "MLB", "season": 2024, "games": 150, "pa": 600, "ops": ".670", "iso": 0.125, "k_pct": 26.0},
            {"level": "MLB", "season": 2023, "games": 145, "pa": 580, "ops": ".660", "iso": 0.120, "k_pct": 28.0},
        ],
        statline={"level": "MLB", "games": 70, "pa": 285, "ops": ".665", "iso": 0.120, "k_pct": 26.5, "bb_pct": 7.5},
        statcast_metrics={"contact_quality": {"avg_ev": 87.5, "barrel_pct": 5.5}},
        current_contract={},
        roster_status={"mlb_debut_date": "2023-03-30", "options_used": 1},
        tools={
            "history": [
                {"snapshot_date": "2023-01-15", "interval_label": "MLB Pipeline 2023 Top 100"}
            ]
        },
    )

    out = bayesian_trade_value(player)

    assert "early_debut_top100_prospect_floor" not in out["inputs_available"]
    assert out["posterior_surplus_mm"] < 70.0


def test_low_power_established_shortstop_does_not_take_full_projection_anchor(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="low_power_ss",
        player_name="Low Power SS",
        position="SS",
        age=26.7,
        fv_close=50.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 74, "pa": 311, "iso": 0.111},
            {"level": "MLB", "season": 2025, "games": 150, "pa": 720, "iso": 0.172},
            {"level": "MLB", "season": 2024, "games": 100, "pa": 388, "iso": 0.101},
            {"level": "MLB", "season": 2023, "games": 130, "pa": 495, "iso": 0.113},
            {"level": "MLB", "season": 2022, "games": 130, "pa": 500, "iso": 0.067},
        ],
        statline={
            "level": "MLB",
            "games": 74,
            "pa": 311,
            "ops": ".710",
            "obp": ".358",
            "iso": 0.111,
            "k_pct": 12.9,
            "bb_pct": 15.1,
            "ops_plus_level": 104,
        },
        statcast_metrics={
            "contact_quality": {
                "avg_ev": 85.3,
                "barrel_pct": 2.7,
                "xwoba_est": 0.280,
            }
        },
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 220.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (2400.0, 0.0))

    out = btv.bayesian_trade_value(player)

    assert "mlb_projection_surplus_anchor" in out["inputs_available"]
    assert any(x.startswith("projection_anchor_current_form_") for x in out["inputs_available"])
    assert out["posterior_surplus_mm"] <= 125.0


def test_late_low_prior_free_swing_breakout_gets_projection_haircut(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="free_swing_breakout",
        player_name="Free Swing Breakout",
        position="SS",
        age=28.0,
        fv_close=45.0,
        career_stats=[
            {"level": "MLB", "season": 2026, "games": 70, "pa": 280},
            {"level": "MLB", "season": 2025, "games": 120, "pa": 500},
            {"level": "MLB", "season": 2024, "games": 100, "pa": 450},
        ],
        statline={"level": "MLB", "games": 70, "pa": 280, "ops": ".850", "iso": 0.145, "bb_pct": 3.5, "k_pct": 16.0},
        statcast_metrics={"contact_quality": {"xwoba_est": 0.285, "barrel_pct": 6.0, "avg_ev": 89.0}},
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 90.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (1230.0, 0.0))

    out = btv.bayesian_trade_value(player)

    assert any(x.startswith("projection_anchor_current_form_") for x in out["inputs_available"])
    assert out["posterior_surplus_mm"] < 65.0


def test_active_injury_keeps_full_projection_anchor_injury_discount(monkeypatch) -> None:
    import bayes_trade_value as btv

    player = _base_debuted_player(
        player_key="active_injured_pitcher",
        player_name="Active Injured Pitcher",
        position="SP",
        is_pitcher=True,
        age=28.0,
        career_stats=[{"level": "MLB", "season": 2025, "games": 30, "ip": 160.0}],
        statline={"level": "MLB", "season": 2025, "games": 30, "ip": 160.0, "k_pct": 24.0, "bb_pct": 8.0},
        roster_status={"injury_history": [{"active": True, "type": "60-day", "since": "2026-03-01"}]},
    )

    monkeypatch.setattr(btv, "_mlb_projection_surplus_mm", lambda _player: 80.0)
    monkeypatch.setattr(btv, "_career_mlb_exposure", lambda _player: (0.0, 400.0))

    out = btv.bayesian_trade_value(player)

    assert out["injury_discount"] == 0.2


def test_elite_controlled_reliever_gets_exception_floor() -> None:
    player = _base_debuted_player(
        player_key="elite_relief_arm",
        player_name="Elite Relief Arm",
        position="RP",
        is_pitcher=True,
        age=27.5,
        career_war={"seasons": {"2025": 2.5, "2026": 2.2}, "career_war": 4.7, "war_per_yr": 2.35, "war_seasons_count": 2},
        career_stats=[{"level": "MLB", "season": 2026, "games": 40, "ip": 40.0, "k_pct": 40.0, "bb_pct": 8.0}],
        statline={"level": "MLB", "games": 40, "ip": 40.0, "k_pct": 40.0, "bb_pct": 8.0, "era": "1.80"},
        current_contract={"signed_through": 2029, "salary_usd": 4_000_000},
        tools={"composite_stuff_plus": 118},
        statcast_metrics={"pitch_movement": {"pitch_summary": [
            {"pitch_type": "FF", "usage_pct": 65.0, "avg_stuff_plus": 119.0},
            {"pitch_type": "SL", "usage_pct": 35.0, "avg_stuff_plus": 116.0},
        ]}},
    )

    out = bayesian_trade_value(player)

    assert "elite_controlled_reliever" in out["archetype_policy"]["tags"]
    assert out["posterior_surplus_mm"] >= 65.0


def test_older_nonimpact_upper_minors_prospect_is_suppressed() -> None:
    player = {
        "player_key": "older_nonimpact",
        "player_name": "Older Nonimpact",
        "org": "TST",
        "status": "active",
        "position": "SS",
        "is_pitcher": False,
        "fv_close": 50.0,
        "age": 23.5,
        "current_level": "AA",
        "statline": {"level": "AA", "games": 60, "pa": 250, "ops": ".685", "iso": 0.060, "k_pct": 27.0, "ops_plus_level": 98},
        "career_stats": [],
        "tools": {},
        "acquisition": {},
    }

    out = bayesian_trade_value(player)

    assert "older_nonimpact_prospect_suppression" in out["inputs_available"]
    assert out["posterior_surplus_mm"] < out["prior_surplus_mm"] * 0.6
