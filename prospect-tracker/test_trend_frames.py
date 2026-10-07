# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""trend_frames.club_by_game on fixture sidecars (League Trends plan 5.1, ruling T5).

A traded batter outvoted by his teammates, a game whose two halves vote for one
club left unresolved, the refusal below mgmt_teams.MIN_RESOLVED_SHARE, and the
isolation: the corpus map builder is never called and no betting cache is read.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import mgmt_teams
import trend_frames as T

SEASON = 2025


def _sidecar(root: Path, games: dict) -> Path:
    """games: {pk: {"top": [batter, ...], "bottom": [batter, ...]}}, one plate
    appearance per listed batter, two pitches each."""
    rows, grows = [], []
    for pk, halves in games.items():
        abi = 0
        for half in ("top", "bottom"):
            for b in halves.get(half, []):
                for n in (1, 2):
                    rows.append({"game_pk": pk, "at_bat_index": abi, "pitch_number": n,
                                 "half": half, "batter": b})
                abi += 1
        grows.append({"game_pk": pk, "start_time": f"{SEASON}-06-01T23:10:00Z"})
    d = root / str(SEASON)
    d.mkdir(parents=True, exist_ok=True)
    p = pd.DataFrame(rows)
    p["batter"] = p["batter"].astype("Int64")
    p.to_parquet(d / f"pitches-{SEASON}.parquet", index=False)
    pd.DataFrame(grows).to_parquet(d / f"games-{SEASON}.parquet", index=False)
    return root


def _war(root: Path, rows) -> Path:
    p = root / "bat.parquet"
    pd.DataFrame(rows, columns=["mlb_ID", "year_ID", "team_ID", "PA"]).to_parquet(p, index=False)
    return p


# clubs AAA (batters 1..9) and BBB (batters 11..19); batter 50 traded AAA -> BBB
_ROSTERS = [(i, SEASON, "AAA", 500) for i in range(1, 10)] + \
           [(i, SEASON, "BBB", 500) for i in range(11, 20)] + \
           [(50, SEASON, "AAA", 400), (50, SEASON, "BBB", 100)]


def _normal(pk_home_bbb: bool):
    a, b = list(range(1, 10)), list(range(11, 20))
    return {"top": a, "bottom": b} if pk_home_bbb else {"top": b, "bottom": a}


def test_traded_batter_outvoted_by_teammates(tmp_path):
    # batter 50 (0.8 AAA, 0.2 BBB) bats for BBB at home among his new teammates
    games = {1: {"top": list(range(1, 10)), "bottom": [50, 11, 12, 13]}}
    pdir = _sidecar(tmp_path / "phys", games)
    war = _war(tmp_path, _ROSTERS)
    m = T.club_by_game(SEASON, physics_dir=pdir, war_daily=war)
    assert m == {1: {"home": "BBB", "away": "AAA", "season": SEASON}}


def test_bottom_half_bats_at_home(tmp_path):
    pdir = _sidecar(tmp_path / "phys", {7: _normal(False)})
    m = T.club_by_game(SEASON, physics_dir=pdir, war_daily=_war(tmp_path, _ROSTERS))
    assert m[7]["home"] == "AAA" and m[7]["away"] == "BBB"


def test_same_club_both_halves_unresolved(tmp_path):
    games = {pk: _normal(pk % 2 == 0) for pk in range(1, 60)}
    # game 99: both halves batted by AAA players -> one club, unresolved
    games[99] = {"top": [1, 2, 3], "bottom": [4, 5, 6]}
    pdir = _sidecar(tmp_path / "phys", games)
    cm = T.resolve_clubs(SEASON, physics_dir=pdir, war_daily=_war(tmp_path, _ROSTERS))
    assert 99 not in cm.games
    assert cm.meta["same_club"] == 1
    assert cm.meta["resolved"] == 59 and cm.meta["games"] == 60
    assert cm.meta["share"] >= mgmt_teams.MIN_RESOLVED_SHARE


def test_tied_half_unresolved(tmp_path):
    games = {pk: _normal(pk % 2 == 0) for pk in range(1, 60)}
    games[98] = {"top": [1, 11], "bottom": list(range(11, 20))}   # top half 500 vs 500
    pdir = _sidecar(tmp_path / "phys", games)
    cm = T.resolve_clubs(SEASON, physics_dir=pdir, war_daily=_war(tmp_path, _ROSTERS))
    assert 98 not in cm.games and cm.meta["tied_halves"] == 1


def test_refusal_below_the_floor(tmp_path):
    games = {pk: _normal(pk % 2 == 0) for pk in range(1, 59)}
    games[97] = {"top": [1, 2], "bottom": [3, 4]}
    games[99] = {"top": [11, 12], "bottom": [13, 14]}
    pdir = _sidecar(tmp_path / "phys", games)                     # 58 of 60 = 0.967
    with pytest.raises(ValueError, match="MIN_RESOLVED_SHARE"):
        T.club_by_game(SEASON, physics_dir=pdir, war_daily=_war(tmp_path, _ROSTERS))


def test_floor_is_mgmt_teams_constant():
    assert T.MIN_RESOLVED_SHARE is mgmt_teams.MIN_RESOLVED_SHARE
    assert T.player_team_weights is mgmt_teams.player_team_weights


def test_never_builds_the_corpus_map_or_reads_betting(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("trend_frames called the corpus map builder")
    monkeypatch.setattr(mgmt_teams, "build_map", boom)
    monkeypatch.setattr(mgmt_teams, "validate_against_ground_truth", boom)
    monkeypatch.setattr(mgmt_teams, "CORPUS", tmp_path / "no_corpus")
    pdir = _sidecar(tmp_path / "phys", {1: _normal(True)})
    assert T.club_by_game(SEASON, physics_dir=pdir, war_daily=_war(tmp_path, _ROSTERS))
    src = Path(T.__file__).read_text(encoding="utf-8")
    for banned in ("build_map(", ".cache/betting", "completed_games", "betting_model_context",
                   "leaderboard_vintages", "lineup_captures", "game_feeds", "weather_forecasts",
                   ".cache/odds", "mg_pen_", "mg_hook_", "sp_n365", "sp_budget", "sp_ppo",
                   "sp_xouts", "bat_ppa_l30"):
        assert banned not in src


def test_missing_sidecar_season(tmp_path):
    with pytest.raises(FileNotFoundError):
        T.club_by_game(SEASON, physics_dir=tmp_path / "empty", war_daily=_war(tmp_path, _ROSTERS))
