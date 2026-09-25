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


# --------------------------------------------------------------------------- #
# X03-02: the club is the CURRENT club, not the monthly contract club
# --------------------------------------------------------------------------- #
# Before this, `team` was the Spotrac contract club first. 134 of the 1,129
# vets the eWAR board also carries sat on the club they had been traded AWAY
# from (Tarik Skubal DET on /projections/, LAD on /mlbstats/), and the FA
# 'from' column, player links, trade board org, Team Outlook and the ledger's
# club rows all inherited it.

NOW = 2026


def test_an_in_season_feed_move_beats_the_contract_club():
    club, src = pe.resolve_current_club(("LAD", "2026-08-02"), ("LAD", NOW), "DET", NOW)
    assert (club, src) == ("LAD", "feed")


def test_this_seasons_club_beats_the_contract_club_without_a_feed_row():
    # Kevin Gausman: no feed row, StatsAPI's season line (numTeams 2) says CHC.
    club, src = pe.resolve_current_club(None, ("CHC", NOW), "TOR", NOW)
    assert (club, src) == ("CHC", "season")


def test_the_feed_beats_this_seasons_line_when_he_has_not_played_since():
    # Claimed on waivers after his last appearance: the feed is newer.
    club, src = pe.resolve_current_club(("PHI", "2026-09-10"), ("CHC", NOW), None, NOW)
    assert (club, src) == ("PHI", "feed")


def test_the_contract_club_beats_an_old_season_line_and_an_old_feed_event():
    # Hurt all year: the contract he signed in the winter outranks a stale
    # 2025 line and a 2024 trade.
    club, src = pe.resolve_current_club(("ATL", "2024-08-23"), ("WSN", NOW - 1), "SEA", NOW)
    assert (club, src) == ("SEA", "contract")


def test_an_old_feed_event_only_beats_a_season_line_that_is_older_still():
    assert pe.resolve_current_club(("CHW", "2025-07-07"), ("MIA", NOW - 1), None, NOW)         == ("CHW", "feed_prior")
    # Harold Ramirez: a 2024 feed event, then a 2025 season with WSN.
    assert pe.resolve_current_club(("ATL", "2024-08-23"), ("WSN", NOW - 1), None, NOW)         == ("WSN", "last_seen")


def test_nothing_known_is_no_club():
    assert pe.resolve_current_club(None, None, None, NOW) == (None, None)
    # a malformed feed date is ignored rather than trusted
    assert pe.resolve_current_club(("NYM", ""), None, None, NOW) == (None, None)


def test_the_feed_never_places_a_player_on_a_national_team(monkeypatch):
    """A WBC roster event resolves to "Cuba", four characters, which slipped
    under the old `len(org) > 4` guard and put five players on "Cuba"."""
    import json
    import sqlite3

    import storage
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE player_transactions (player_key TEXT, payload_json TEXT)")
    con.execute("INSERT INTO player_transactions VALUES (?, ?)", ("luis_romero", json.dumps([
        {"date": "2025-07-01", "to_team_name": "Seattle Mariners"},
        {"date": "2026-02-05", "to_team_name": "Cuba"},
    ])))
    monkeypatch.setattr(storage, "connect", lambda: con)
    assert storage.authoritative_org_map() == {"luis_romero": ("SEA", "2025-07-01")}


# --------------------------------------------------------------------------- #
# the served invariant: one club per human across the artifacts
# --------------------------------------------------------------------------- #
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

import pytest  # noqa: E402

_DATA = _Path(__file__).parent / "data"

#: mlbam ids allowed to differ between artifacts built on the same day, each
#: with the reason. Empty on 2026-09-24; a release that lands between two
#: exporters in one pipeline run is the case this exists for.
ONE_CLUB_ALLOWLIST: dict[int, str] = {}


def _load(name):
    p = _DATA / name
    if not p.exists():
        pytest.skip(f"{name} not built on this machine")
    return _json.loads(p.read_text(encoding="utf-8"))


def _canon(code):
    from trades import canonical_org
    return canonical_org(code) if code else None


def test_projections_and_the_ewar_board_name_the_same_club():
    proj, war = _load("mlb_projections.json"), _load("war_leaderboards.json")
    if str(proj.get("generated_at"))[:10] != str(war.get("generated_at"))[:10]:
        pytest.skip("the two artifacts were built on different days")
    wm = {r.get("mlbam"): r for r in war.get("players") or []}
    off = [(v["name"], v.get("team"), wm[v["mlbam"]].get("team"))
           for v in proj.get("vets") or []
           if v.get("mlbam") in wm and v["mlbam"] not in ONE_CLUB_ALLOWLIST
           and _canon(v.get("team")) != _canon(wm[v["mlbam"]].get("team"))]
    assert not off, f"{len(off)} vets on a different club than the eWAR board: {off[:8]}"


def test_the_trade_board_names_a_veterans_projection_club():
    proj, tv = _load("mlb_projections.json"), _load("trade_values.json")
    club = {v["mlbam"]: v.get("team") for v in proj.get("vets") or [] if v.get("mlbam")}
    off = [(r.get("player_name"), r.get("org"), club[r["mlbam_id"]])
           for r in tv.get("players") or []
           if r.get("status") != "active" and r.get("mlbam_id") in club
           and r["mlbam_id"] not in ONE_CLUB_ALLOWLIST
           and _canon(r.get("org")) != _canon(club[r["mlbam_id"]])]
    assert not off, f"{len(off)} MLB rows on a different club than /projections/: {off[:8]}"


def test_the_fa_from_column_is_the_projection_club():
    proj = _load("mlb_projections.json")
    by_key = {v["key"]: v.get("team") for v in proj.get("vets") or [] if v.get("key")}
    for name in ("fa_class.json", "fa_class_2028.json", "fa_class_2029.json"):
        fa = _load(name)
        off = [(m.get("name"), m.get("from"), by_key[m["key"]])
               for m in fa.get("members") or []
               if m.get("key") in by_key and by_key[m["key"]]
               and m.get("from") != by_key[m["key"]]]
        assert not off, f"{name}: {len(off)} 'from' cells off the projection club: {off[:8]}"


def test_projections_publish_where_each_club_came_from():
    tb = _load("mlb_projections.json").get("team_basis")
    assert tb and tb["basis"] == "current_club"
    assert sum(tb["by_source"].values()) == tb["n_rows"]
    assert tuple(tb["order"]) == pe.CLUB_SOURCES
