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


# --------------------------------------------------------------------------- #
# trend_frames.pitch_game_frame on fixture payloads, sidecar and swing files
# (TR_2A_DETECT_DARK: the corpus root on an empty directory, the swing source
# read and never written, a missing season named)
# --------------------------------------------------------------------------- #
import json  # noqa: E402

FRAME_SEASON = 2025
CLUB_A = {"bats": list(range(1, 10)), "sp": 201, "rp": 202}
CLUB_B = {"bats": list(range(11, 20)), "sp": 211, "rp": 212}


def _fx_pitch(n, pitcher, batter, *, ptype="FF", call="B", speed=95.0, launch=None):
    ev = {"isPitch": True, "type": "pitch", "pitchNumber": n, "index": n - 1,
          "details": {"call": {"code": call}, "type": {"code": ptype}, "isInPlay": call == "X"},
          "pitchData": {"startSpeed": speed, "zone": 5 if call != "B" else 13, "extension": 6.5,
                        "breaks": {"breakVerticalInduced": 16.0, "breakHorizontal": -7.0,
                                   "spinRate": 2300}},
          "defense": {"pitcher": {"id": pitcher}}, "offense": {"batter": {"id": batter}}}
    if launch is not None:
        ev["hitData"] = {"launchSpeed": launch, "launchAngle": 12}
    return ev


def _fx_play(abi, half, batter, pitcher, event, outs, pitches, *, start=None, li=1.0):
    about = {"atBatIndex": abi, "halfInning": half, "isTopInning": half == "top", "inning": 1}
    if start:
        about["startTime"] = start
    return {"result": {"type": "atBat", "eventType": event, "event": event, "rbi": 0,
                       "awayScore": 0, "homeScore": 0},
            "about": about, "count": {"balls": 0, "strikes": 0, "outs": outs},
            "matchup": {"batter": {"id": batter}, "batSide": {"code": "R"},
                        "pitcher": {"id": pitcher}, "pitchHand": {"code": "R"}},
            "runners": [], "playEvents": pitches,
            "credits": [{"player": {"id": batter}, "credit": "b_pa"},
                        {"player": {"id": pitcher}, "credit": "p_pa"}],
            "leverageIndex": li, "homeTeamWinProbability": 50.0,
            "homeTeamWinProbabilityAdded": 0.0, "atBatIndex": abi}


def _fx_game(i: int):
    """Game i: a 9-batter half each way against the starter, then the reliever
    faces the leadoff man once, entering at Leverage Index 1.7."""
    home, away = (CLUB_A, CLUB_B) if i % 2 == 0 else (CLUB_B, CLUB_A)
    start = f"{FRAME_SEASON}-05-{1 + i:02d}T23:05:00.000Z"
    plays, abi = [], 0
    for half, bats, pit in (("top", away, home), ("bottom", home, away)):
        for j, b in enumerate(bats["bats"]):
            sp = pit["sp"]
            plays.append(_fx_play(abi, half, b, sp, "field_out", min(3, (j % 3) + 1), [
                _fx_pitch(1, sp, b, ptype="FF", call="B"),
                _fx_pitch(2, sp, b, ptype="SL", call="S", speed=86.0),
                _fx_pitch(3, sp, b, ptype="FF", call="X", launch=98.0 + j)],
                start=start if abi == 0 else None, li=0.9))
            abi += 1
        rp, b = pit["rp"], bats["bats"][0]
        plays.append(_fx_play(abi, half, b, rp, "strikeout", 3, [
            _fx_pitch(1, rp, b, ptype="FF", call="S", speed=97.0),
            _fx_pitch(2, rp, b, ptype="FF", call="S", speed=97.0),
            _fx_pitch(3, rp, b, ptype="FF", call="S", speed=97.0)], li=1.7))
        abi += 1
    return 990000 + i, plays


def _fx_day_files(d: Path, season: int, games: list) -> Path:
    """One Savant day file per fixture game date; a bunt and a taken pitch on
    every date (neither is a competitive swing)."""
    d.mkdir(parents=True, exist_ok=True)
    head = ("game_date,game_pk,batter,at_bat_number,pitch_number,description,"
            "bat_speed,swing_length,attack_angle\n")
    for i, pk in games:
        day = f"{season}-05-{1 + i:02d}"
        rows = [f"{day},{pk},{b},{k + 1},3,hit_into_play,{70 + b % 7}.5,7.{b % 9},{10 + b % 5}.0\n"
                for k, b in enumerate(CLUB_A["bats"] + CLUB_B["bats"])]
        rows.append(f"{day},{pk},1,1,2,foul_bunt,31.0,2.0,-20.0\n")
        rows.append(f"{day},{pk},2,2,1,ball,,,\n")
        (d / f"{day}.csv").write_text(head + "".join(rows), encoding="utf-8", newline="")
    return d


def _fx_swing_pitches(d: Path, season: int, games: list) -> Path:
    """The Swing+ cache layout, <batter>_<season>.csv."""
    d.mkdir(parents=True, exist_ok=True)
    head = "game_date,batter,game_pk,description,bat_speed,swing_length,attack_angle\n"
    for b in CLUB_A["bats"] + CLUB_B["bats"]:
        rows = [f"{season}-05-{1 + i:02d},{b},{pk},hit_into_play,{70 + b % 7}.5,7.{b % 9},"
                f"{10 + b % 5}.0\n" for i, pk in games]
        (d / f"{b}_{season}.csv").write_text(head + "".join(rows), encoding="utf-8", newline="")
    return d


def _tree_state(d: Path) -> dict:
    return {str(p.relative_to(d)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture()
def fx(tmp_path):
    from tools import build_pitch_physics as B
    wp = tmp_path / "win_prob"
    wp.mkdir()
    games = []
    for i in range(20):
        pk, plays = _fx_game(i)
        (wp / f"{pk}.json").write_text(json.dumps(plays), encoding="utf-8")
        games.append((i, pk))
    phys = tmp_path / "phys"
    B.build(win_prob_dir=wp, out_dir=phys, live_season=2026)
    war = tmp_path / "bat.parquet"
    rows = [(b, FRAME_SEASON, "AAA", 500) for b in CLUB_A["bats"]] + \
           [(b, FRAME_SEASON, "BBB", 500) for b in CLUB_B["bats"]]
    pd.DataFrame(rows, columns=["mlb_ID", "year_ID", "team_ID", "PA"]).to_parquet(war, index=False)
    empty = tmp_path / "empty_corpus"
    empty.mkdir()
    days = _fx_day_files(tmp_path / "savant_days", FRAME_SEASON, games)
    _fx_day_files(days, FRAME_SEASON - 1, [(i, 980000 + i) for i in range(5)])
    sp = _fx_swing_pitches(tmp_path / "swing_pitches", FRAME_SEASON, games)
    _fx_swing_pitches(sp, FRAME_SEASON - 1, [(i, 980000 + i) for i in range(5)])
    kw = dict(physics_dir=phys, war_daily=war, corpus_dir=empty, win_prob_dir=wp,
              games_memo_dir=tmp_path / "games_memo", memo_dir=tmp_path / "frame_memo",
              receipts={})
    return {"kw": kw, "days": days, "swing_pitches": sp, "games": games, "tmp": tmp_path}


def test_frame_builds_with_the_corpus_root_on_an_empty_directory(fx):
    f = T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **fx["kw"])
    assert f.meta["game_lines"]["source"] == "payload"
    assert len(f.games) == 20 and f.games["home"].notna().all()
    assert list(f.games["game_seq"]) == list(range(20))
    # four pitchers a game, the two starters flagged; the reliever's entry LI
    assert len(f.pit) == 80 and int(f.pit["start"].sum()) == 40
    rp = f.pit[f.pit["pitcher"] == 202]
    assert (rp["li"] == 1.7).all() and not rp["start"].any()
    assert (rp["np"] == 3).all() and (rp["whiffs"] == 3).all()
    # the starter on the mound in the top half pitches for the home club
    g0 = f.games.iloc[0]
    sp0 = f.pit[(f.pit["game_pk"] == g0["game_pk"]) & (f.pit["pitcher"] == 201)]
    assert sp0["club"].tolist() == [g0["home"]] == ["AAA"]
    # arsenal: the starter's fastballs, 18 a game at 95.0, all to right-handed batters
    a = f.arsenal[(f.arsenal["pitcher"] == 201) & (f.arsenal["pitch_type"] == "FF")]
    assert (a["n"] == 18).all() and (a["bat_side"] == "R").all()
    assert (a["s_start_speed"] / a["n_start_speed"]).round(4).eq(95.0).all()
    assert (a["q_start_speed"] - a["s_start_speed"] ** 2 / a["n_start_speed"]).abs().max() < 1e-3
    # batters: nine started per half; the leadoff man saw the reliever too
    assert int(f.bat["started"].sum()) == 20 * 18
    lead = f.bat[(f.bat["batter"] == 1)]
    assert (lead["seen"] == 6).all() and (lead["pa"] == 2).all() and (lead["bbe"] == 1).all()
    # swings: bunts and taken pitches are not swings; 18 a game
    assert len(f.swings) == 20 * 18
    assert f.swings["bat_speed"].min() >= 50
    assert f.meta["swing"]["source"] == "savant_days"
    assert f.meta["swing"]["counts"]["2025"]["hitters"] == 18
    assert f.meta["swing"]["as_of"] == f"{FRAME_SEASON}-05-20"
    # the previous season's cut for every hitter with swings in it
    assert set(f.prior_cut) == set(CLUB_A["bats"] + CLUB_B["bats"])


@pytest.mark.parametrize("source", ["savant_days", "swing_pitches"])
def test_the_swing_source_is_read_and_never_written(fx, source):
    d = fx["days"] if source == "savant_days" else fx["swing_pitches"]
    before = _tree_state(d)
    f = T.pitch_game_frame(FRAME_SEASON, swing_source=source, swing_dir=d, **fx["kw"])
    assert len(f.swings) == 20 * 18 and f.meta["swing"]["source"] == source
    T.pitch_game_frame(FRAME_SEASON, swing_source=source, swing_dir=d, **fx["kw"])   # memo
    T.check_swing_seasons([2024, 2025], source=source, swing_dir=d, receipts={})
    assert _tree_state(d) == before


def test_a_missing_needed_season_is_named(fx):
    for p in fx["days"].glob(f"{FRAME_SEASON - 1}-*.csv"):
        p.unlink()
    with pytest.raises(T.SwingSeasonsMissing, match=str(FRAME_SEASON - 1)) as e:
        T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **fx["kw"])
    assert e.value.seasons == [FRAME_SEASON - 1]
    assert not (fx["kw"]["memo_dir"] / str(FRAME_SEASON) / "meta.json").exists()


def test_a_season_below_its_receipt_is_missing(fx):
    kw = dict(fx["kw"], receipts={FRAME_SEASON: {"hitters": 19, "swings": 1}})
    with pytest.raises(T.SwingSeasonsMissing, match=f"{FRAME_SEASON}.*hitters 18") as e:
        T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **kw)
    assert e.value.seasons == [FRAME_SEASON]


def test_a_pruned_season_fails_the_memo_too(fx):
    T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **fx["kw"])
    for p in sorted(fx["days"].glob(f"{FRAME_SEASON}-*.csv")):
        p.unlink()
    with pytest.raises(T.SwingSeasonsMissing, match=str(FRAME_SEASON)):
        T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **fx["kw"])


def test_the_memo_returns_the_same_frame(fx):
    a = T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **fx["kw"])
    b = T.pitch_game_frame(FRAME_SEASON, swing_dir=fx["days"], **fx["kw"])
    for t in ("games", "pit", "arsenal", "bat", "swings"):
        pd.testing.assert_frame_equal(getattr(a, t).reset_index(drop=True),
                                      getattr(b, t).reset_index(drop=True), check_dtype=False)
    assert a.prior_cut == b.prior_cut and a.meta["key"] == b.meta["key"]


def test_the_pinned_receipts_are_the_backfill_counts():
    r = T.SWING_RECEIPTS["savant_days"]
    assert r[2024] == {"hitters": 650, "swings": 316997}
    assert r[2025] == {"hitters": 672, "swings": 330422}
    assert T.SWING_RECEIPTS["swing_pitches"][2024]["hitters"] == 195
    assert T.SWING_RECEIPTS["swing_pitches"][2025]["hitters"] == 281
    assert T.SWING_SOURCE == "savant_days"
    assert T.needed_swing_seasons(2024) == [2024]
    assert T.needed_swing_seasons(2027) == [2026, 2027]
    assert T.needed_swing_seasons(2023) == []


def test_the_frame_writes_only_its_memo():
    src = Path(T.__file__).read_text(encoding="utf-8")
    assert ".to_csv(" not in src and "open(" not in src
    assert src.count("write_text(") == 1 and src.count("to_parquet(") == 1
    assert "import mlbstats_games as G" in src
