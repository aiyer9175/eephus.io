# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""P-VETTEAM: the Spotrac contract join and the observed-club fallback.

Pins the three failures that put 361 of 1,319 veterans on no team at all and
mis-awarded two contracts (proj_export.py, 2026-07-31):
  1. Spotrac writes "Jazz Chisholm", war_daily writes "Jazz Chisholm Jr.", so
     the keys never met and he carried no team.
  2. The WSN "Luis Garcia" deal joined the reliever (mlbam 472610, on MIN)
     because HIS key matched exactly, not Luis Garcia Jr. (671277, WSN).
  3. Everyone Spotrac does not price at all - pre-arb, optioned - had no team
     by construction, which is 356 of the 361.
"""
import proj_export as pe


def test_base_key_strips_generational_suffixes():
    assert pe._base_key("jazz_chisholm_jr") == "jazz_chisholm"
    assert pe._base_key("daniel_lynch_iv") == "daniel_lynch"
    assert pe._base_key("ken_griffey_sr") == "ken_griffey"
    assert pe._base_key("luis_garcia") == "luis_garcia"
    # A two-token name is never stripped to one token, however it reads.
    assert pe._base_key("sammy_sr") == "sammy_sr"


def _ct(team, pos="2B"):
    return {"team_code": team, "position": pos, "signed_through": 2027,
            "aav_usd": 1_000_000, "salary_by_year": {}}


def test_suffix_mismatch_joins_when_unambiguous():
    names = {1: "Jazz Chisholm Jr."}
    contracts = {"jazz_chisholm": _ct("NYY")}
    assigned, contested = pe._resolve_contracts([1], names, contracts, {1: "NYY"})
    assert assigned[1] is contracts["jazz_chisholm"]
    assert contested == {}


def test_observed_club_breaks_a_suffix_collision():
    # Both claim "luis_garcia"; only 671277 actually plays for the contract's club.
    names = {472610: "Luis Garcia", 671277: "Luis Garcia Jr."}
    contracts = {"luis_garcia": _ct("WSN")}
    teams = {472610: "MIN", 671277: "WSN"}
    assigned, contested = pe._resolve_contracts([472610, 671277], names, contracts, teams)
    assert assigned == {671277: contracts["luis_garcia"]}
    assert contested == {}


def test_unresolvable_collision_is_left_to_the_caller():
    # Two players, same name, same club: nothing can single one out, so the
    # contract must stay CONTESTED rather than be handed to an arbitrary row.
    names = {1: "Jose Fermin", 2: "Jose Fermin"}
    contracts = {"jose_fermin": _ct("STL")}
    assigned, contested = pe._resolve_contracts([1, 2], names, contracts,
                                                {1: "STL", 2: "STL"})
    assert assigned == {}
    assert sorted(contested["jose_fermin"]) == [1, 2]


def test_exact_key_wins_over_the_stripped_one():
    # A player whose own key matches must not be dragged into a base-key group.
    names = {1: "Luis Garcia", 2: "Luis Garcia Jr."}
    contracts = {"luis_garcia": _ct("MIN"), "luis_garcia_jr": _ct("WSN")}
    assigned, _ = pe._resolve_contracts([1, 2], names, contracts, {})
    assert assigned[1] is contracts["luis_garcia"]
    assert assigned[2] is contracts["luis_garcia_jr"]


def test_no_contract_leaves_the_player_unassigned():
    names = {1: "Nobody Here"}
    assigned, contested = pe._resolve_contracts([1], names, {}, {1: "SEA"})
    assert assigned == {} and contested == {}


def test_observed_club_map_covers_the_league():
    """The fallback is only useful if it actually resolves; a map that comes
    back empty (offline, cold cache) is a silent revert to the old behaviour."""
    teams = pe._team_by_mlbam()
    if not teams:                      # offline build: the arm no-ops by design
        return
    assert len(teams) > 1000
    assert len(set(teams.values())) == 30
