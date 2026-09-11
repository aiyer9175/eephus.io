# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Unit tests for the schema-5 dark-capture builders of docs/diamond-betting.md
sections 5f (pinch hitting and bullpen hands) and 5g (team fielding), the dark
per-game candidate, the starter-share extraction, and the 5f power gate.

Every test is about whether a BUILDER produces the number it claims to, or
whether a served path stays dark. None of them relates a captured value to a
game outcome: 5c rule 1 disqualifies a candidate measured before its look, and
the 5f look is the end of the 2027 regular season. The fixture feeds carry no
score field at all, so a tally that reached for one would find nothing.

Everything is synthetic: fixture feeds in a tmp dir, an injected game list, an
injected fielding loader, a tmp memo. No network, no real cache is written.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import math
from pathlib import Path

import pytest

import betting_model as bm
import betting_usage as bu
import leaderboard_vintages as lv

ROOT = Path(__file__).parent
ORGS = ("NYM", "PHI", "ATL", "WSN")

_SPEC = importlib.util.spec_from_file_location("ph_gate", ROOT / "tools" / "ph_gate.py")
ph_gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ph_gate)


@pytest.fixture(autouse=True)
def _no_network_pitch_hand(monkeypatch):
    """reduce_current's throws join must never reach the network from a test."""
    import pal_export
    monkeypatch.setattr(pal_export, "load_pitch_hand",
                        lambda season: {101: "L", 102: "R", 103: "R", 104: "L"})


@pytest.fixture(autouse=True)
def _fresh_memo_cache():
    bu._PH_MEMO.clear()
    bu._PH_LIVE_CACHE.clear()
    yield
    bu._PH_MEMO.clear()
    bu._PH_LIVE_CACHE.clear()


# ===========================================================================
# 1. team_fld_runs (section 5g)
# ===========================================================================
def _fld_sources(*, fetched=None, prior=True):
    """Six players on one club. A catcher, a DH (no innings) and a pitcher carry
    large fielding numbers precisely so that counting any of them would show."""
    cur = {"values": {
        1: {"fld": 50.0, "team_id": None},     # catcher (C primary, some 1B)
        2: {"fld": 30.0, "team_id": None},     # DH: no fielding innings at all
        3: {"fld": 20.0, "team_id": None},     # pitcher
        4: {"fld": 4.0, "team_id": None},      # SS, has a prior-season row
        5: {"fld": -2.0, "team_id": None},     # CF/LF tie, no prior row
        6: {"fld": 2.5, "team_id": None},      # 2B, not on the board, no feed club
    }, "n_multi_team": 1}
    pri = {"values": {1: {"fld": 90.0}, 2: {"fld": 90.0}, 3: {"fld": 90.0},
                      4: {"fld": 6.0}}} if prior else {"values": {}}
    inn = {"players": {1: {"inn": {"C": 800.0, "1B": 20.0}},
                       3: {"inn": {"P": 60.0}},
                       4: {"inn": {"SS": 900.0}},
                       5: {"inn": {"CF": 500.0, "LF": 500.0}},
                       6: {"inn": {"2B": 300.0}}}}
    return {"current": cur, "prior": pri, "innings": inn,
            "fetched": fetched or {"current": "2026-09-12T02:10:00-04:00",
                                   "prior": "2026-09-01T10:00:00-04:00",
                                   "innings": "2026-09-12T02:11:00-04:00"}}


_BOARD = {"hitters": [{"mlbam": m, "team": "NYM"} for m in (1, 2, 3, 4, 5)]}


def test_a_catcher_a_dh_and_a_pitcher_contribute_nothing():
    src = _fld_sources()
    board = {m: "NYM" for m in (1, 2, 3, 4, 5)}
    vals, diag = lv.team_fld_runs_from_sources(
        src["current"]["values"], src["prior"]["values"], src["innings"]["players"],
        board, feed_club=lambda v: None)
    # SS (4 now + 6 prior) + CF (-2 now, no prior) = 8; nothing from 1, 2 or 3.
    assert vals == {"NYM": 8.0}
    assert diag["n_players"] == 2
    assert diag["n_excluded_c"] == 1
    assert diag["n_excluded_p_dh_or_none"] == 2
    assert diag["n_unplaced"] == 1          # player 6: off the board, no feed club


def test_the_feed_club_is_the_fallback_and_is_counted():
    src = _fld_sources()
    vals, diag = lv.team_fld_runs_from_sources(
        src["current"]["values"], src["prior"]["values"], src["innings"]["players"],
        {4: "NYM", 5: "NYM"}, feed_club=lambda v: "PHI")
    assert vals == {"NYM": 8.0, "PHI": 2.5}
    assert diag["n_club_from_feed"] == 1


def test_primary_position_takes_the_harder_rung_on_a_tie():
    assert lv.primary_fielding_position({"CF": 500.0, "LF": 500.0}) == "CF"
    assert lv.primary_fielding_position({"1B": 10.0, "C": 10.0}) == "C"
    assert lv.primary_fielding_position({"C": 800.0, "1B": 20.0}) == "C"
    assert lv.primary_fielding_position({}) is None
    assert lv.primary_fielding_position(None) is None
    assert lv.primary_fielding_position({"SS": 0}) is None


def test_the_fielding_rung_is_the_defense_board_s_rung():
    import dem_plus
    assert lv.FLD_POSITION_RUNG == dem_plus.POSITION_RUNG
    assert lv.FLD_EXCLUDED_POSITIONS == {"C", "P", "DH"}


def test_build_team_fld_runs_populates_and_states_its_basis():
    out = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season="2026",
                                 loader=lambda season: _fld_sources())
    blk = out["team_fld_runs"]
    assert blk["values"] == {"NYM": 8.0}
    for fact in ("2 players summed", "1 catchers", "2026-09-12T02:10:00-04:00",
                 "multi-team rows 1", "seasons 2025 and 2026"):
        assert fact in blk["basis"], fact


def test_a_cache_fetched_after_the_vintage_date_is_a_stated_null():
    """VINTAGE SAFETY. A current-season fetch dated after the record can hold
    games the record's date cannot have known; a backfill lands here always."""
    for late in ("current", "innings"):
        f = {"current": "2026-09-12T02:10:00-04:00", "prior": "2026-09-01T10:00:00-04:00",
             "innings": "2026-09-12T02:11:00-04:00"}
        f[late] = "2026-09-13T01:00:00-04:00"
        blk = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season=2026,
                                     loader=lambda season, f=f: _fld_sources(fetched=f)
                                     )["team_fld_runs"]
        assert blk["values"] == {}
        assert blk["basis"].startswith("ABSENT") and "after the vintage date" in blk["basis"]
    # A current-season fetch time nobody can state is not shown to predate it.
    f = {"current": None, "prior": "2026-09-01T10:00:00-04:00",
         "innings": "2026-09-12T02:11:00-04:00"}
    blk = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season=2026,
                                 loader=lambda season: _fld_sources(fetched=f))["team_fld_runs"]
    assert blk["values"] == {} and "fetch time is unknown" in blk["basis"]
    # The prior season is closed: its later fetch never nulls the column.
    f = {"current": "2026-09-12T02:10:00-04:00", "prior": "2026-09-30T00:00:00-04:00",
         "innings": "2026-09-12T02:11:00-04:00"}
    blk = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season=2026,
                                 loader=lambda season: _fld_sources(fetched=f))["team_fld_runs"]
    assert blk["values"] == {"NYM": 8.0}


def test_a_missing_season_or_a_raising_loader_is_a_stated_null():
    blk = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season=2026,
                                 loader=lambda season: _fld_sources(prior=False))["team_fld_runs"]
    assert blk["values"] == {} and "prior-season" in blk["basis"]

    def boom(season):
        raise OSError("disk")

    blk = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season=2026,
                                 loader=boom)["team_fld_runs"]
    assert blk["values"] == {} and "raised OSError" in blk["basis"]
    blk = lv.build_team_fld_runs(_BOARD, on_date="2026-09-12", season=2026,
                                 loader=lambda season: None)["team_fld_runs"]
    assert blk["values"] == {} and blk["basis"].startswith("ABSENT")


def test_the_fielding_builder_never_reads_the_defense_board():
    """5g: the builder reads saber_feed and never the DEM+ index, the Defense
    board or its history. Read off the file, because conftest stubs the loader
    attribute for every test."""
    src = (ROOT / "leaderboard_vintages.py").read_text(encoding="utf-8")
    block = src[src.index("# schema 5: team fielding (section 5g)"):
                src.index("# reduce the live leaderboards to a record")]
    for banned in ("defense_leaderboards", "defense_history", "dem_plus", "DEM+",
                   "dem_plus_eval"):
        assert banned not in block, banned
    assert "saber_feed.load_components" in block
    assert "defense_export.load_season_innings" in block


# ===========================================================================
# 2. the pinch-hit and relief-hand tally (section 5f)
# ===========================================================================
def _action(code, player, replaced):
    return {"type": "action", "isSubstitution": True,
            "details": {"eventType": "offensive_substitution"},
            "position": {"code": code}, "player": {"id": player},
            "replacedPlayer": {"id": replaced}}


def _play(half, pitcher, batter, event, *, hand="R", actions=()):
    """One play in the feed's shape. No score field: the fixture could not
    serve one to a tally that went looking."""
    return {"about": {"halfInning": half},
            "matchup": {"pitcher": {"id": pitcher}, "batter": {"id": batter},
                        "pitchHand": {"code": hand}},
            "result": {"eventType": event},
            "playEvents": list(actions) + [{"type": "pitch", "isPitch": True}]}


def _feed(plays):
    return {"liveData": {"plays": {"allPlays": plays}}}


def test_a_code_11_and_a_code_12_action_count_one_pinch_hit():
    t = bu.tally_game_feed(_feed([
        _play("top", 900, 1, "single"),                       # home starter
        _play("top", 901, 2, "strikeout", hand="L",
              actions=[_action("11", 2, 20), _action("12", 30, 1)]),
    ]))
    away = t["away"]
    assert away["n_ph_actions"] == 1
    assert away["ph_pa"] == 1 and away["ph_rel_pa"] == 1
    assert away["rel_pa"] == 1
    assert t["home"]["pen_pa"] == 1 and t["home"]["pen_lhp_pa"] == 1


def test_a_pinch_hitter_for_a_pinch_hitter_counts_the_pa_once():
    t = bu.tally_game_feed(_feed([
        _play("top", 900, 1, "single"),
        _play("top", 901, 6, "groundout",
              actions=[_action("11", 5, 40), _action("11", 6, 5)]),
        _play("top", 901, 7, "flyout"),
    ]))
    assert t["away"]["n_ph_actions"] == 2
    assert t["away"]["ph_pa"] == 1
    assert t["away"]["rel_pa"] == 2


def test_non_pa_terminal_events_are_excluded():
    t = bu.tally_game_feed(_feed([
        _play("top", 900, 1, "single"),
        _play("top", 901, 8, "caught_stealing_2b", hand="L",
              actions=[_action("11", 8, 80)]),
        _play("bottom", 800, 50, "walk"),
        _play("bottom", 801, 51, "pickoff_1b"),
        _play("bottom", 801, 52, "error"),
        _play("top", 902, 8, "double"),                        # his first real PA
    ]))
    # The caught stealing is no PA; the pinch hitter's PA is the next one he takes.
    assert t["away"]["rel_pa"] == 1 and t["away"]["ph_pa"] == 1
    assert t["home"]["pen_pa"] == 1 and t["home"]["pen_lhp_pa"] == 0
    # Bottom half: the away starter faced one PA; the pickoff and the runner
    # error are not plate appearances.
    assert t["home"]["rel_pa"] == 0 and t["away"]["pen_pa"] == 0


@pytest.mark.parametrize("event,is_pa", [
    ("single", True), ("field_error", True), ("strikeout", True),
    ("walk", True), ("caught_stealing_home", False), ("pickoff_caught_stealing_2b", False),
    ("wild_pitch", False), ("error", False), ("", False), (None, False),
])
def test_the_pa_classifier(event, is_pa):
    assert bu.is_pa_event(event) is is_pa


def test_the_shrink_constants_are_the_registered_ones():
    """Frozen by 5f: median split-half pseudo-counts over 2022-2025."""
    assert bu.K_PHI == 298 and bu.K_PEN == 142
    assert bu.PH_POSITION_CODE == "11"


def _game(pk, d, home="NYM", away="PHI"):
    return {"game_pk": pk, "date": d, "home_org": home, "away_org": away}


def _write_feed(feed_dir, pk, plays):
    feed_dir.mkdir(exist_ok=True)
    (feed_dir / f"{pk}.json").write_text(json.dumps(_feed(plays)), encoding="utf-8")


def _two_game_season(tmp_path):
    fd = tmp_path / "feeds"
    # Game 1: PHI bats in the top against NYM; one PH off the bench vs a lefty.
    _write_feed(fd, 1, [
        _play("top", 900, 1, "single"),
        _play("top", 901, 2, "strikeout", hand="L", actions=[_action("11", 2, 20)]),
        _play("top", 901, 3, "flyout", hand="L"),
        _play("bottom", 800, 50, "walk"),
        _play("bottom", 801, 51, "groundout", hand="R"),
    ])
    # Game 2: NYM at PHI; no pinch hitter.
    _write_feed(fd, 2, [
        _play("top", 700, 60, "single"),
        _play("top", 701, 61, "lineout", hand="R"),
        _play("bottom", 600, 70, "double"),
        _play("bottom", 601, 71, "strikeout", hand="L"),
    ])
    # Game 3 is ON the vintage date and game 4 is last season: neither may count.
    _write_feed(fd, 3, [_play("top", 900, 1, "single"),
                        _play("top", 901, 2, "single", actions=[_action("11", 2, 9)])])
    _write_feed(fd, 4, [_play("top", 900, 1, "single"),
                        _play("top", 901, 2, "single", actions=[_action("11", 2, 9)])])
    games = [_game(1, "2026-09-01"), _game(2, "2026-09-02", home="PHI", away="NYM"),
             _game(3, "2026-09-03"), _game(4, "2025-09-01"),
             _game(5, "2026-09-02")]                           # 5 has no feed on disk
    return fd, games


def test_the_tally_is_strictly_before_the_vintage_date_and_shrunk(tmp_path):
    fd, games = _two_game_season(tmp_path)
    memo = tmp_path / "memo.json"
    out = bu.build_schema5_team_columns(on_date="2026-09-03", games=games,
                                        feed_dir=fd, tally_path=memo)
    # Relief PA: PHI batting 2 (game 1) + 1 (game 2) = 3, one by a pinch hitter;
    # NYM batting 1 + 1 = 2, none. League phi = 1 / 5.
    lg = 1 / 5
    assert out["ph_share"]["values"]["PHI"] == round((1 + bu.K_PHI * lg) / (3 + bu.K_PHI), 5)
    assert out["ph_share"]["values"]["NYM"] == round((0 + bu.K_PHI * lg) / (2 + bu.K_PHI), 5)
    # Relief PA thrown: NYM 2 in game 1 and 1 in game 2, all three left-handed;
    # PHI 1 in each game, both right-handed. League 3 / 5.
    lgl = 3 / 5
    assert out["pen_lhp_share"]["values"]["NYM"] == round((3 + bu.K_PEN * lgl) / (3 + bu.K_PEN), 5)
    assert out["pen_lhp_share"]["values"]["PHI"] == round((0 + bu.K_PEN * lgl) / (2 + bu.K_PEN), 5)
    basis = out["ph_share"]["basis"]
    assert "2 game(s) tallied" in basis and "1 without a cached feed" in basis
    assert "K_PHI 298" in basis


def test_the_memo_means_a_tallied_game_never_reopens_its_feed(tmp_path, monkeypatch):
    fd, games = _two_game_season(tmp_path)
    memo = tmp_path / "memo.json"
    first = bu.build_schema5_team_columns(on_date="2026-09-03", games=games,
                                          feed_dir=fd, tally_path=memo)
    blob = json.loads(memo.read_text(encoding="utf-8"))
    assert blob["version"] == bu.PH_TALLY_VERSION
    assert set(blob["games"]) == {"1", "2"}                 # the feedless game is retried
    bu._PH_MEMO.clear()

    def no_feed(*a, **k):
        raise AssertionError("a memoized game opened its feed")

    monkeypatch.setattr(bu, "_feed", lambda pk, fd=None: None if int(pk) == 5 else no_feed())
    again = bu.build_schema5_team_columns(on_date="2026-09-03", games=games,
                                          feed_dir=fd, tally_path=memo)
    assert again["ph_share"]["values"] == first["ph_share"]["values"]
    assert again["pen_lhp_share"]["values"] == first["pen_lhp_share"]["values"]


def test_no_tallied_game_is_a_stated_null(tmp_path):
    out = bu.build_schema5_team_columns(on_date="2026-04-01", games=[],
                                        feed_dir=tmp_path, tally_path=tmp_path / "m.json")
    for c in lv.SCHEMA5_PH_TALLY_COLUMNS:
        assert out[c]["values"] == {} and out[c]["basis"].startswith("ABSENT")


def test_the_live_read_uses_the_memo_alone(tmp_path, monkeypatch):
    fd, games = _two_game_season(tmp_path)
    memo = tmp_path / "memo.json"
    built = bu.build_schema5_team_columns(on_date="2026-09-03", games=games,
                                          feed_dir=fd, tally_path=memo)

    def no_feed(*a, **k):
        raise AssertionError("the live read opened a feed")

    monkeypatch.setattr(bu, "_feed", no_feed)
    live = bu.live_ph_columns(on_date="2026-09-03", tally_path=memo)
    for org in ("NYM", "PHI"):
        assert live[org]["ph_share"] == built["ph_share"]["values"][org]
        assert live[org]["pen_lhp_share"] == built["pen_lhp_share"]["values"][org]
    assert bu.live_ph_columns(on_date="2026-09-03", tally_path=tmp_path / "none.json") == {}


def test_the_tally_reads_no_score_field():
    """Section 5c rule 1, structurally: the tally's source names no score or
    run field, and reads the completed-games rows for pk, date and orgs only."""
    src = "".join(inspect.getsource(f) for f in (
        bu.tally_game_feed, bu.ph_tallies, bu.ph_columns_from_tallies,
        bu.build_schema5_team_columns, bu.live_ph_columns))
    for banned in ("homeScore", "awayScore", "home_runs", "away_runs", "isScoringPlay",
                   "rbi", "linescore", "winProbability", "leverage"):
        assert banned not in src, banned


# ===========================================================================
# 3. the four hitter-derived columns (section 5f)
# ===========================================================================
def _slot(slot, bats, split, pa, season=100):
    return {"slot": slot, "key": str(slot), "bats": bats, "hem_plus": season,
            "hem_plus_split": split, "pa": pa}


def _team(team="NYM"):
    return {
        "team": team, "offense_plus": 104.0,
        "orders": {
            "vl": [_slot(1, "L", 90, 400), _slot(2, "L", None, 300, season=150),
                   _slot(3, "S", 120, 500), _slot(4, "R", 110, 450)],
            "vr": [_slot(1, "R", 95, 500), _slot(2, "R", 85, 250),
                   _slot(3, "L", 130, 480)],
        },
        "bench": [
            {"key": "b1", "bats": "R", "pa": 200, "pos": ["1B"],
             "hem_plus_split": {"L": 120, "R": 90}},
            {"key": "b2", "bats": "S", "pa": 100, "pos": ["2B"],
             "hem_plus_split": {"L": 100, "R": 110}},
            {"key": "b3", "bats": "L", "pa": 150, "pos": ["LF"],
             "hem_plus_split": {"L": 70, "R": 115}},
            {"key": "b4", "bats": "R", "pa": 50, "pos": ["P"],
             "hem_plus_split": {"L": 200, "R": 200}},
            {"key": "b5", "bats": "L", "pa": 300, "pos": ["CF"], "hem_plus": 160,
             "hem_plus_split": {"L": None, "R": None}},
        ],
    }


def test_the_lineup_and_bench_reductions():
    got = lv.ph_splits_from_hitter_team(_team())
    # vs LHP, the nine's bats WITHOUT the edge: the one L slot with a split. The
    # L slot without a split is skipped, never filled with its season 150; the
    # switch hitter and the righty hold the edge and are out.
    assert got["lineup_dis_vs_lhp"] == 90.0
    assert got["lineup_dis_vs_rhp"] == round((95 * 500 + 85 * 250) / 750, 3)
    # Bench WITH the edge: vs LHP the righty and the switch hitter; vs RHP the
    # lefty and the switch hitter. The pitcher is never a bench bat, and the
    # lefty with no split (season 160) is skipped rather than defaulted.
    assert got["bench_adv_vs_lhp"] == round((120 * 200 + 100 * 100) / 300, 3)
    assert got["bench_adv_vs_rhp"] == round((110 * 100 + 115 * 150) / 250, 3)


def test_no_qualifying_bat_is_none_never_a_season_number():
    t = _team()
    t["bench"] = [{"key": "x", "bats": "R", "pa": 300, "hem_plus": 140}]
    t["orders"]["vl"] = [_slot(1, "R", 100, 400)]
    got = lv.ph_splits_from_hitter_team(t)
    assert got["lineup_dis_vs_lhp"] is None
    assert got["bench_adv_vs_lhp"] is None and got["bench_adv_vs_rhp"] is None
    assert lv.ph_splits_from_hitter_team({}) == {c: None for c in lv.SCHEMA5_PH_HITTER_COLUMNS}


def test_the_display_markers_never_move_a_dark_column():
    """The builder reads the raw bench rows and the orders, never the page's
    platoon markers, whose display constants must be free to move."""
    base = lv.ph_splits_from_hitter_team(_team())
    poisoned = dict(_team(), platoon_options={"vl": [{"bench_key": "b5", "delta": 99}]},
                    slot_meta={"1": {"pos": ["DH"]}})
    assert lv.ph_splits_from_hitter_team(poisoned) == base
    for mod in ("betting_usage.py",):
        src = (ROOT / mod).read_text(encoding="utf-8")
        for key in ("platoon_options", "slot_meta", "regulars_out", "lineup_cards"):
            assert f'"{key}"' not in src and f"'{key}'" not in src, (mod, key)


def test_a_down_hand_lens_is_a_stated_null_for_all_four():
    blob = {"bat_side": {"available": False}, "teams": [_team()]}
    out = lv.build_ph_hitter_columns(blob)
    for c in lv.SCHEMA5_PH_HITTER_COLUMNS:
        assert out[c]["values"] == {} and out[c]["basis"].startswith("ABSENT")


def test_the_builder_reports_bench_rows_split_backed():
    out = lv.build_ph_hitter_columns({"bat_side": {"available": True},
                                      "platoon_splits": {"available": True},
                                      "teams": [_team("NYM"), _team("PHI")]})
    assert out["bench_adv_vs_lhp"]["values"] == {"NYM": 113.333, "PHI": 113.333}
    assert "bench rows split-backed 8 of 10" in out["bench_adv_vs_lhp"]["basis"]


def _write_boards(data, teams):
    (data / "hitter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-09-11", "bat_side": {"available": True},
        "teams": teams, "hitters": []}), encoding="utf-8")
    (data / "starter_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-09-11",
        "teams": [{"team": t["team"], "rotation_plus": 100, "starter_ip": 500.0}
                  for t in teams],
        "starters": [{"mlbam": 101, "team": "NYM", "sem_plus": 105,
                      "ip_per_gs": 5.5, "role": "SP"}]}), encoding="utf-8")
    (data / "bullpen_leaderboards.json").write_text(json.dumps({
        "season": "2026", "as_of": "2026-09-11",
        "teams": [{"team": t["team"], "bullpen_plus": 100, "relief_ip": 300.0}
                  for t in teams], "relievers": []}), encoding="utf-8")


@pytest.fixture()
def _quiet(monkeypatch):
    """No feed scan: the schema-4 builders and the tally are stubbed."""
    monkeypatch.setattr(bu, "build_schema4_team_columns",
                        lambda **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                     for c in lv.SCHEMA4_TEAM_COLUMNS})
    monkeypatch.setattr(bu, "build_pitcher_schema4", lambda *a, **k: {})
    monkeypatch.setattr(bu, "build_schema5_team_columns",
                        lambda **k: {c: {"values": {}, "basis": "ABSENT: stubbed"}
                                     for c in lv.SCHEMA5_PH_TALLY_COLUMNS})


def test_the_write_and_live_paths_reduce_the_same_four(tmp_path, monkeypatch, _quiet):
    data = tmp_path / "data"
    data.mkdir()
    _write_boards(data, [_team("NYM"), _team("PHI")])
    rec = lv.reduce_current(on_date="2026-09-12", data_dir=data)
    row = lv.team_row(rec, "NYM")
    assert row["lineup_dis_vs_lhp"] == 90.0
    assert row["bench_adv_vs_rhp"] == round((110 * 100 + 115 * 150) / 250, 3)
    assert rec["feature_basis"]["lineup_dis_vs_lhp"]["n"] == 2
    # Orders, Offense+ and the 5e splits are read, never written: same values as
    # the helpers that existed before 5f.
    assert row["off_vs_lhp"] == lv.off_splits_from_hitter_team(_team())[0]
    monkeypatch.setattr(bm, "DATA_DIR", data)
    live = bm.team_inputs()
    vint = bm.team_inputs_from_vintage(rec)
    for c in lv.SCHEMA5_PH_HITTER_COLUMNS + lv.SCHEMA5_PARK_TEAM_COLUMNS:
        assert live["NYM"][c] == vint["NYM"][c], c
    assert set(live["NYM"]) == set(vint["NYM"])


# ===========================================================================
# 4. the dark candidate, and the starter share it shares with the served model
# ===========================================================================
def _legacy_game_prevention_z(team, starter, teams):
    """game_prevention_z VERBATIM as it stood before the _starter_share
    extraction (betting_model at 705f32cd). The served price must not move by
    one bit."""
    scale = teams.get("_scale") or {}
    mu = scale.get("prev_mu", 100.0)
    sd = scale.get("prev_sd", 1.0) or 1.0
    pen_plus = team.get("bullpen_plus", 100.0)
    if starter and starter.get("sem_plus") is not None:
        share = (starter.get("ip_per_gs") or (bm.DEFAULT_SP_SHARE * 9.0)) / 9.0
        share = max(0.25, min(0.85, share))
        sp_plus = float(starter["sem_plus"])
        src = "probable"
    else:
        share = float(team.get("sp_ip_share") or bm.DEFAULT_SP_SHARE)
        sp_plus = float(team.get("rotation_plus", 100.0))
        src = "rotation-average"
    blended = share * sp_plus + (1.0 - share) * pen_plus
    return (blended - mu) / sd, {
        "starter_plus": round(sp_plus, 1), "bullpen_plus": round(pen_plus, 1),
        "starter_share": round(share, 3), "blend_plus": round(blended, 1),
        "source": src,
    }


def _teams(extra=None):
    off = {"NYM": 108.3, "PHI": 101.7, "ATL": 96.2, "WSN": 91.9}
    rots = {"NYM": 104.1, "PHI": 99.9, "ATL": 103.3, "WSN": 94.4}
    pens = {"NYM": 101.2, "PHI": 97.3, "ATL": 105.8, "WSN": 92.6}
    sip = {"NYM": 561.1, "PHI": 590.2, "ATL": 0.0, "WSN": 520.7}
    rip = {"NYM": 380.3, "PHI": 350.9, "ATL": 0.0, "WSN": 410.4}
    ex = extra or {
        "NYM": {"off_vs_lhp": 104.0, "off_vs_rhp": 110.0, "ph_share": 0.06,
                "pen_lhp_share": 0.35, "lineup_dis_vs_lhp": 92.0,
                "bench_adv_vs_lhp": 112.0, "lineup_dis_vs_rhp": 99.0,
                "bench_adv_vs_rhp": 95.0},
        "PHI": {"off_vs_lhp": 100.0, "off_vs_rhp": 102.0, "ph_share": 0.04,
                "pen_lhp_share": 0.25, "lineup_dis_vs_lhp": None,
                "bench_adv_vs_lhp": 108.0, "lineup_dis_vs_rhp": 90.0,
                "bench_adv_vs_rhp": None},
        "ATL": {"off_vs_lhp": 95.0, "off_vs_rhp": 97.0, "ph_share": 0.05,
                "pen_lhp_share": 0.30},
        "WSN": {"off_vs_lhp": 90.0, "off_vs_rhp": 93.0, "ph_share": None,
                "pen_lhp_share": None},
    }
    return bm._assemble_team_inputs(off, rots, pens, sip, rip, ex)


_STARTERS = [None, {"sem_plus": 118.0, "ip_per_gs": 5.9},
             {"sem_plus": 91.0, "ip_per_gs": None}, {"sem_plus": 99.0, "ip_per_gs": 1.2},
             {"sem_plus": 130.0, "ip_per_gs": 8.8}, {"sem_plus": None, "ip_per_gs": 6.0},
             {"sem_plus": 104.4, "ip_per_gs": 6.1, "throws": "L"}]


def test_the_starter_share_extraction_is_bit_identical():
    teams = _teams()
    for org in ORGS:
        for st in _STARTERS:
            assert bm.game_prevention_z(teams[org], st, teams) == \
                _legacy_game_prevention_z(teams[org], st, teams), (org, st)


_LINES = [x / 2 for x in range(11, 27)]


def _evaluated(p):
    """A game_probabilities dict with its returned callables evaluated on a grid
    of lines and splits, so a byte comparison covers every served side."""
    out = {}
    for k, v in (p or {}).items():
        if k in ("over", "total_sides"):
            out[k] = [v(x) for x in _LINES]
        elif k == "runline_at_split":
            out[k] = [v(None), v((0.0, 0.0)), v((0.6, 0.6)), v((0.3, 0.7))]
        else:
            out[k] = v
    return out


def test_every_served_price_is_bit_identical_after_the_extraction(monkeypatch):
    teams = _teams()
    parks = {"NYM": 1.02, "PHI": 1.04, "ATL": 0.98, "WSN": 1.0}
    kw = dict(teams=teams, parks=parks, coeffs=dict(bm.LITERATURE_COEFFS),
              home_adj=0.11, diff_shrink=0.83)

    def prices():
        out = []
        for h in ORGS:
            for a in ORGS:
                if h == a:
                    continue
                for hs in _STARTERS[:4]:
                    for as_ in _STARTERS[3:]:
                        out.append(bm.expected_runs(h, a, home_sp=hs, away_sp=as_, **kw))
                        out.append(_evaluated(bm.game_probabilities(
                            h, a, home_sp=hs, away_sp=as_, tie_home=0.52, **kw)))
        return out

    new = prices()
    monkeypatch.setattr(bm, "game_prevention_z", _legacy_game_prevention_z)
    old = prices()
    assert json.dumps(new, sort_keys=True) == json.dumps(old, sort_keys=True)
    assert new == old


def test_the_candidate_is_the_registered_formula():
    teams = _teams()
    s, o = teams["NYM"], teams["PHI"]
    st = {"sem_plus": 110.0, "ip_per_gs": 5.4}
    z, det = bm.game_offense_ph_z(s, o, st, teams)
    w = bm._starter_share(o, st)[0]
    p_bar = (0.35 + 0.25 + 0.30) / 3
    g_l, g_r = max(0.0, 112.0 - 92.0), max(0.0, 95.0 - 99.0)
    arm_a = (0.25 - p_bar) * (104.0 - 110.0)
    arm_b = 0.06 * (0.25 * g_l + 0.75 * g_r)
    expect = s["z_off"] + (1 - w) * (arm_a + arm_b) / teams["_scale"]["off_sd"]
    assert z == pytest.approx(expect, rel=1e-12)
    assert det["g_R"] == 0.0 and det["g_L"] == 20.0
    assert det["pL_bar"] == pytest.approx(p_bar)
    assert det["arm_a_z"] + det["arm_b_z"] == pytest.approx(det["delta_z"])
    # w is the served model's own starter share, from the one helper.
    assert det["starter_share"] == w
    assert round(w, 3) == bm.game_prevention_z(o, st, teams)[1]["starter_share"]


def test_the_candidate_never_reads_the_probable_s_hand():
    """5e reads `throws`; 5f must not, or the two candidates share a lever."""
    teams = _teams()
    a = bm.game_offense_ph_z(teams["NYM"], teams["PHI"],
                             {"sem_plus": 110.0, "ip_per_gs": 5.4, "throws": "L"}, teams)
    b = bm.game_offense_ph_z(teams["NYM"], teams["PHI"],
                             {"sem_plus": 110.0, "ip_per_gs": 5.4, "throws": "R"}, teams)
    assert a == b
    assert "throws" not in inspect.getsource(bm.game_offense_ph_z).split('"""')[-1]


def test_the_candidate_is_the_served_offense_when_it_has_nothing_to_add():
    ex = {o: {"off_vs_lhp": 100.0, "off_vs_rhp": 100.0, "ph_share": 0.0,
              "pen_lhp_share": 0.3, "bench_adv_vs_lhp": 110.0,
              "lineup_dis_vs_lhp": 95.0} for o in ORGS}
    teams = _teams(ex)
    z, det = bm.game_offense_ph_z(teams["NYM"], teams["PHI"], None, teams)
    assert z == teams["NYM"]["z_off"] and det["delta_z"] == 0.0


def test_the_eval_exclusions():
    teams = _teams()
    z, det = bm.game_offense_ph_z(teams["WSN"], teams["NYM"], None, teams)
    assert z is None and "scoring side ph_share null" in det["excluded"]
    z, det = bm.game_offense_ph_z(teams["NYM"], teams["WSN"], None, teams)
    assert z is None and "opposing pen_lhp_share null" in det["excluded"]
    z, det = bm.game_offense_ph_z(teams["ATL"], teams["NYM"], None, teams)
    assert z is None and "all four hitter-derived columns null" in det["excluded"]
    # One hand's null is the "no qualifying bat" case: g = 0, not an exclusion.
    z, det = bm.game_offense_ph_z(teams["PHI"], teams["NYM"], None, teams)
    assert z is not None and det["g_L"] == 0.0 and det["g_R"] == 0.0


def test_expected_runs_never_reaches_the_candidate(monkeypatch):
    """DARK MEANS DARK. No served path calls game_offense_ph_z: not by name in
    its source, and not at run time with the function booby-trapped."""
    import betting_export as be
    served = [bm.expected_runs, bm.game_probabilities, bm.game_prevention_z,
              bm._design_rows, bm.fit_coefficients, bm.build_context, bm.backtest,
              be.team_bets]
    for fn in served:
        assert "game_offense_ph_z" not in inspect.getsource(fn), fn.__name__
    for mod in ("betting_export.py", "dfs_export.py", "betting_shadow.py",
                "betting_settle.py", "betting_learning.py", "betting_weather.py"):
        assert "game_offense_ph_z" not in (ROOT / mod).read_text(encoding="utf-8"), mod

    def trap(*a, **k):
        raise AssertionError("a served path reached game_offense_ph_z")

    monkeypatch.setattr(bm, "game_offense_ph_z", trap)
    teams = _teams()
    kw = dict(teams=teams, parks={}, coeffs=dict(bm.LITERATURE_COEFFS),
              home_adj=0.0, diff_shrink=1.0)
    assert bm.expected_runs("NYM", "PHI", **kw) is not None
    assert bm.game_probabilities("NYM", "PHI", tie_home=0.5, **kw) is not None


def test_no_served_export_reads_a_5f_or_5g_column():
    """Every served consumer of the team inputs, by source. A column name
    appearing in one of them is a feature that shipped around its gate."""
    import betting_export as be
    cols = lv.SCHEMA5_PH_TEAM_COLUMNS + lv.SCHEMA5_FLD_TEAM_COLUMNS
    served_fns = [bm.expected_runs, bm.game_probabilities, bm.game_prevention_z,
                  bm._starter_share, bm._design_rows, bm.fit_coefficients,
                  bm.build_context, bm.backtest, bm.park_index, bm.league_context,
                  be.team_bets]
    for fn in served_fns:
        src = inspect.getsource(fn)
        for c in cols:
            assert c not in src, f"{fn.__name__} reads the dark column {c}"
    for mod in ("betting_export.py", "dfs_export.py", "betting_shadow.py",
                "betting_settle.py", "betting_learning.py", "betting_weather.py"):
        src = (ROOT / mod).read_text(encoding="utf-8")
        for c in cols:
            assert c not in src, f"{mod} reads the dark column {c}"
    # The eval artifact's feature-basis block stays schema 3 by name.
    assert "DARK3_TEAM_COLUMNS" in inspect.getsource(bm._feature_basis)


# ===========================================================================
# 5. the 5f power gate (tools/ph_gate.py)
# ===========================================================================
def _rows(n, d):
    return [{"game_pk": i, "date": "2027-06-01", "p_candidate": 0.5 + d,
             "p_served": 0.5} for i in range(n)]


def test_the_gate_refuses_to_run_before_the_end_of_the_2027_regular_season():
    rows = {q: _rows(1000, 0.2) for q in ph_gate.SPLIT_QUANTILES}
    for today, end in (("2026-12-01", "2026-09-27"),     # 2026 is not a look season
                       ("2027-06-01", "2027-09-26"),     # mid-season
                       ("2027-09-26", "2027-09-26"),     # the last day itself
                       ("2027-10-01", None),             # end date not supplied
                       ("2027-07-01", "2027-06-30")):    # an unbelievable end
        with pytest.raises(ph_gate.LookRefused):
            ph_gate.run_precondition(rows, today=today, regular_season_end=end)
    out = ph_gate.run_precondition(rows, today="2027-09-28",
                                   regular_season_end="2027-09-26")
    assert out["status"] == "POWERED"


def test_the_gate_refuses_the_outcome_join():
    """A frame carrying any result field is refused before any arithmetic, and
    an UNDERPOWERED precondition refuses the join outright."""
    for bad in ("home_runs", "away_runs", "home_win", "won", "result", "y", "score"):
        rows = {q: _rows(10, 0.01) for q in ph_gate.SPLIT_QUANTILES}
        rows[0.7][3] = dict(rows[0.7][3], **{bad: 1})
        with pytest.raises(ph_gate.OutcomeJoinRefused):
            ph_gate.power_precondition(rows)
    weak = {q: _rows(1000, 0.001) for q in ph_gate.SPLIT_QUANTILES}
    out = ph_gate.run_precondition(weak, today="2027-10-02", regular_season_end="2027-09-26")
    assert out["status"] == "UNDERPOWERED" and out["outcome_join"].startswith("REFUSED")
    with pytest.raises(ph_gate.OutcomeJoinRefused):
        ph_gate.require_powered(out)


def test_the_precondition_arithmetic():
    """sqrt(n) * RMS against 1.645, at EVERY quantile: one weak quantile fails
    the lot. RMS 0.001 at n 1,000 is the design lane's 'about 5 percent power'."""
    rows = {0.6: _rows(1000, 0.1), 0.7: _rows(1000, 0.1), 0.8: _rows(1000, 0.001)}
    out = ph_gate.power_precondition(rows)
    assert out["status"] == "UNDERPOWERED"
    q8 = out["by_quantile"][0.8]
    assert q8["n_eval"] == 1000 and q8["rms"] == pytest.approx(0.001)
    assert q8["expected_t"] == pytest.approx(math.sqrt(1000) * 0.001)
    assert out["by_quantile"][0.6]["holds"] is True
    assert ph_gate.power_precondition({})["status"] == "UNDERPOWERED"
