# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_games.player_game_frame: the public per-game frame (plan Part 8 8.E).

Pins: the payload path equals the corpus path on fixture games; with the corpus
root pointed at an empty directory the frame still returns the live season's
games from the payloads (League Trends' first check, TR_1_FRAMES_DARK); games
are ordered by the first play's startTime and dated on the US Eastern calendar;
the plate appearance follows the scorer's credits, each pitch its own pitcher and
batter, and runs their responsible pitcher. Every fixture lives under tmp_path;
nothing here writes the real .cache/mlbstats_games memo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import mlbstats_games as G

SEASON = 2026
PK_A, PK_B = 900001, 900002


# --------------------------------------------------------------------------- #
# fixture payloads (the winProbability shape the corpus is built from)
# --------------------------------------------------------------------------- #
def _pitch(pitcher, batter, code="B"):
    return {"isPitch": True, "type": "pitch", "details": {"call": {"code": code}},
            "defense": {"pitcher": {"id": pitcher}}, "offense": {"batter": {"id": batter}}}


def _play(abi, half, inning, batter, pitcher, event, outs, pitches, *, start=None,
          li=None, runners=(), credits=None, away=0, home=0):
    about = {"atBatIndex": abi, "halfInning": half, "isTopInning": half == "top",
             "inning": inning}
    if start:
        about["startTime"] = start
    cb, cp = credits if credits else (batter, pitcher)
    return {
        "result": {"type": "atBat", "eventType": event, "event": event, "rbi": 0,
                   "awayScore": away, "homeScore": home},
        "about": about,
        "count": {"balls": 0, "strikes": 0, "outs": outs},
        "matchup": {"batter": {"id": batter}, "batSide": {"code": "R"},
                    "pitcher": {"id": pitcher}, "pitchHand": {"code": "R"}},
        "runners": list(runners),
        "playEvents": list(pitches),
        "credits": [{"player": {"id": cb}, "credit": "b_pa"},
                    {"player": {"id": cp}, "credit": "p_pa"}],
        "leverageIndex": li, "homeTeamWinProbability": 50.0,
        "homeTeamWinProbabilityAdded": 0.0, "atBatIndex": abi,
    }


def _runner(rid, start, end, *, out=False, scores=False, earned=False, resp=None):
    d = {"runner": {"id": rid}, "isScoringEvent": scores, "earned": earned,
         "responsiblePitcher": ({"id": resp} if resp else None)}
    return {"movement": {"start": start, "end": end, "isOut": out}, "details": d}


def game_a(start="2026-09-28T02:05:00.000Z"):
    """Home pitchers 101 (starter) and 102; away pitcher 201. Away batters 301,
    302, 303 and pinch hitter 304; home batters 401, 402, 403. The start is
    10:05 pm Eastern on 2026-09-27 (02:05 UTC on the 28th)."""
    P1, P2, A1 = 101, 102, 201
    return [
        _play(0, "top", 1, 301, P1, "strikeout", 1,
              [_pitch(P1, 301, "S"), _pitch(P1, 301, "S"), _pitch(P1, 301, "S")], start=start),
        _play(1, "top", 1, 302, P1, "single", 1, [_pitch(P1, 302), _pitch(P1, 302, "X")],
              li=1.10, runners=[_runner(302, None, "1B")]),
        _play(2, "top", 1, 303, P1, "home_run", 1, [_pitch(P1, 303, "X")], li=1.30, away=2,
              runners=[_runner(302, "1B", "score", scores=True, earned=True, resp=P1),
                       _runner(303, None, "score", scores=True, earned=True, resp=P1)]),
        _play(3, "top", 1, 301, P1, "single", 1, [_pitch(P1, 301, "X")], li=0.80, away=2,
              runners=[_runner(301, None, "1B")]),
        # caught stealing ends no plate appearance: batter 302 saw two pitches
        _play(4, "top", 1, 302, P1, "caught_stealing_2b", 2, [_pitch(P1, 302), _pitch(P1, 302)],
              li=0.70, away=2, runners=[_runner(301, "1B", None, out=True)]),
        # reliever 102 enters on a 2-0 count; the walk is charged to 101 (rule 9.16)
        _play(5, "top", 1, 302, P2, "walk", 2,
              [_pitch(P1, 302), _pitch(P1, 302), _pitch(P2, 302), _pitch(P2, 302)],
              li=0.60, away=2, credits=(302, P1), runners=[_runner(302, None, "1B")]),
        # pinch hitter 304 enters with two strikes on 303; the strikeout is 303's (rule 9.15)
        _play(6, "top", 1, 304, P2, "strikeout", 3,
              [_pitch(P2, 303, "S"), _pitch(P2, 303, "S"), _pitch(P2, 304, "S")],
              li=0.90, away=2, credits=(303, P2)),
        _play(7, "bottom", 1, 401, A1, "walk", 0,
              [_pitch(A1, 401), _pitch(A1, 401), _pitch(A1, 401), _pitch(A1, 401)], li=0.90,
              away=2, runners=[_runner(401, None, "1B")]),
        _play(8, "bottom", 1, 402, A1, "grounded_into_double_play", 2, [_pitch(A1, 402, "X")],
              li=1.00, away=2, runners=[_runner(401, "1B", None, out=True),
                                        _runner(402, None, None, out=True)]),
        _play(9, "bottom", 1, 403, A1, "field_out", 3, [_pitch(A1, 403, "X")], li=0.50, away=2,
              runners=[_runner(403, None, None, out=True)]),
    ]


def game_b(start="2026-09-27T17:05:00.000Z"):
    """An earlier game the same Eastern day: home pitcher 103, away pitcher 202."""
    return [
        _play(0, "top", 1, 301, 103, "single", 0, [_pitch(103, 301, "X")], start=start,
              runners=[_runner(301, None, "1B")]),
        _play(1, "top", 1, 302, 103, "double_play", 2, [_pitch(103, 302, "X")], li=0.95,
              runners=[_runner(301, "1B", None, out=True), _runner(302, None, None, out=True)]),
        _play(2, "bottom", 1, 401, 202, "strikeout", 1,
              [_pitch(202, 401, "S"), _pitch(202, 401, "S"), _pitch(202, 401, "S")], li=0.85),
    ]


def write_payloads(win_prob: Path, games: dict) -> None:
    win_prob.mkdir(parents=True, exist_ok=True)
    for pk, plays in games.items():
        (win_prob / f"{pk}.json").write_text(json.dumps(plays), encoding="utf-8")


def write_corpus(corpus: Path, games: dict, season: int = SEASON) -> None:
    """The corpus tables for the fixture games, through the builder's own pure
    row functions (tools/build_pbp_corpus.game_tables)."""
    from tools import build_pbp_corpus as bpc
    plays, pitches = [], []
    for pk, g in games.items():
        p, q, _e = bpc.game_tables(g, pk, season)
        plays += p
        pitches += q
    for name, rows in (("plays", plays), ("pitches", pitches)):
        d = corpus / name / str(season)
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(d / f"{name}-{season}.parquet", index=False)
    (corpus / "manifest.json").write_text(json.dumps({"built_at": "2026-10-02T12:00:00+00:00"}),
                                          encoding="utf-8")


@pytest.fixture()
def dirs(tmp_path):
    games = {PK_A: game_a(), PK_B: game_b()}
    wp, corpus, memo = tmp_path / "win_prob", tmp_path / "corpus", tmp_path / "memo"
    write_payloads(wp, games)
    write_corpus(corpus, games)
    return {"win_prob_dir": wp, "corpus_dir": corpus, "memo_dir": memo, "tmp": tmp_path}


def _row(df, pk, mlbam):
    r = df[(df["game_pk"] == pk) & (df["mlbam"] == mlbam)]
    assert len(r) == 1, (pk, mlbam, len(r))
    return r.iloc[0]


# --------------------------------------------------------------------------- #
# the two paths
# --------------------------------------------------------------------------- #
def test_the_payload_path_equals_the_corpus_path_on_the_fixture_games(dirs):
    a = G.player_game_frame(SEASON, corpus_dir=dirs["corpus_dir"],
                            win_prob_dir=dirs["win_prob_dir"], memo_dir=dirs["memo_dir"])
    empty = dirs["tmp"] / "empty"
    empty.mkdir()
    b = G.player_game_frame(SEASON, corpus_dir=empty, win_prob_dir=dirs["win_prob_dir"],
                            memo_dir=dirs["tmp"] / "memo_b")
    assert a.meta["source"] == "corpus" and b.meta["source"] == "payload"
    assert a.meta["corpus_built_at"] == "2026-10-02T12:00:00+00:00"
    pd.testing.assert_frame_equal(a.hit, b.hit)
    pd.testing.assert_frame_equal(a.pit, b.pit)
    assert list(a.hit.columns) == G.HIT_KEYS + G.HIT_COLS
    assert list(a.pit.columns) == G.PIT_KEYS + G.PIT_COLS


def test_an_empty_corpus_root_still_returns_the_live_season(dirs, monkeypatch):
    """TR_1_FRAMES_DARK's first check: the deploy box has .cache/win_prob and no
    .cache/pbp_corpus, so the module default is pointed at an empty directory."""
    empty = dirs["tmp"] / "no_corpus"
    empty.mkdir()
    monkeypatch.setattr(G, "CORPUS_DIR", empty)
    monkeypatch.setattr(G, "WIN_PROB_DIR", dirs["win_prob_dir"])
    monkeypatch.setattr(G, "MEMO_DIR", dirs["tmp"] / "memo_default")
    f = G.player_game_frame(SEASON)
    assert f.meta["source"] == "payload"
    assert f.meta["games"] == 2 and set(f.hit["game_pk"]) == {PK_A, PK_B}
    assert f.meta["covers_through"] == "2026-09-27"
    # the memo landed where the module was told, not in the real cache
    assert (dirs["tmp"] / "memo_default" / f"layers_{SEASON}.json").exists()


def test_a_season_with_no_payloads_is_an_empty_frame(dirs):
    f = G.player_game_frame(2019, corpus_dir=dirs["tmp"] / "none",
                            win_prob_dir=dirs["win_prob_dir"], memo_dir=dirs["memo_dir"])
    assert f.meta["games"] == 0 and f.hit.empty and f.pit.empty
    assert f.meta["covers_through"] is None


# --------------------------------------------------------------------------- #
# order, dates and the scoring layer
# --------------------------------------------------------------------------- #
def test_games_are_ordered_by_first_play_start_and_dated_eastern(dirs):
    f = G.player_game_frame(SEASON, **{k: v for k, v in dirs.items() if k != "tmp"})
    seq = f.hit.drop_duplicates("game_pk").set_index("game_pk")["game_seq"].to_dict()
    assert seq == {PK_B: 0, PK_A: 1}
    # 02:05 UTC on the 28th is 10:05 pm Eastern on the 27th
    assert set(f.hit.loc[f.hit["game_pk"] == PK_A, "date"]) == {"2026-09-27"}
    assert G.game_date("2026-03-26T00:25:18.211Z") == "2026-03-25"
    assert G.game_date("2026-07-04T17:05:00Z") == "2026-07-04"
    assert list(f.hit["game_seq"]) == sorted(f.hit["game_seq"])


def test_the_credits_charge_the_plate_appearance(dirs):
    f = G.player_game_frame(SEASON, **{k: v for k, v in dirs.items() if k != "tmp"})
    h, p = f.hit, f.pit
    # rule 9.15: 303 is charged the strikeout 304 finished; 304 saw one pitch
    r303 = _row(h, PK_A, 303)
    assert (r303.pa, r303.ab, r303.h, r303.hr, r303.so, r303.pit) == (2, 2, 1, 1, 1, 3)
    r304 = _row(h, PK_A, 304)
    assert (r304.pa, r304.so, r304.pit) == (0, 0, 1)
    # the caught stealing is no plate appearance, but 302 saw its two pitches
    r302 = _row(h, PK_A, 302)
    assert (r302.pa, r302.ab, r302.h, r302.bb, r302.pit) == (2, 1, 1, 1, 8)
    # rule 9.16: the walk is 101's; 102 threw two of that plate appearance's pitches
    s101 = _row(p, PK_A, 101)
    assert (s101.gs, s101.bf, s101.outs, s101.h, s101.hr, s101.bb, s101.so) == (1, 5, 2, 3, 1, 1, 1)
    assert (s101.r, s101.er, s101.pit) == (2, 2, 11)
    assert s101.li == pytest.approx(1.10)          # the first play carries no LI
    s102 = _row(p, PK_A, 102)
    assert (s102.gs, s102.bf, s102.outs, s102.so, s102.bb, s102.pit) == (0, 1, 1, 1, 0, 5)
    assert s102.li == pytest.approx(0.60)          # entered on the walk's play
    s201 = _row(p, PK_A, 201)
    assert (s201.gs, s201.bf, s201.outs, s201.bb, s201.pit) == (1, 3, 3, 1, 6)
    assert bool(s201.home) is False and bool(s101.home) is True
    assert bool(_row(h, PK_A, 401).home) is True


def test_the_frame_sums_reconcile_inside_each_game(dirs):
    """Plate appearances equal batters faced, and pitches seen equal pitches
    thrown, in every game: no event is charged to one side only."""
    f = G.player_game_frame(SEASON, **{k: v for k, v in dirs.items() if k != "tmp"})
    for pk in (PK_A, PK_B):
        h = f.hit[f.hit["game_pk"] == pk]
        p = f.pit[f.pit["game_pk"] == pk]
        assert h["pa"].sum() == p["bf"].sum()
        assert h["pit"].sum() == p["pit"].sum()
        assert h["so"].sum() == p["so"].sum() and h["bb"].sum() == p["bb"].sum()
        assert p["gs"].sum() == 2


def test_the_memo_is_reused_and_refreshed_when_a_payload_moves(dirs):
    kw = {k: v for k, v in dirs.items() if k != "tmp"}
    G.player_game_frame(SEASON, **kw)
    memo = json.loads((dirs["memo_dir"] / f"layers_{SEASON}.json").read_text(encoding="utf-8"))
    assert set(memo["games"]) == {str(PK_A), str(PK_B)}
    # a re-fetched payload with a new start moves the order on the next build
    write_payloads(dirs["win_prob_dir"], {PK_B: game_b(start="2026-09-28T03:05:00.000Z")})
    f = G.player_game_frame(SEASON, corpus_dir=dirs["tmp"] / "none",
                            win_prob_dir=dirs["win_prob_dir"], memo_dir=dirs["memo_dir"])
    seq = f.hit.drop_duplicates("game_pk").set_index("game_pk")["game_seq"].to_dict()
    assert seq == {PK_A: 0, PK_B: 1}


def test_the_module_is_documented_as_public():
    doc = G.__doc__ or ""
    assert "PUBLIC" in doc and "player_game_frame(season)" in doc
    assert "League Trends" in doc
    import inspect
    sig = inspect.signature(G.player_game_frame)
    assert list(sig.parameters)[0] == "season"
