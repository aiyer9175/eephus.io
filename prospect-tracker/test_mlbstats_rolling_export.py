# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""mlbstats_rolling_export: the drawer's per-player game files.

Pins the files mlbstats_player/*.json and mlbstats_player_index.json: per-player
game sums equal the boards' season counts where the frame covers the boards'
games; the stale rule compares GAME dates and refuses a frame that stops five
days before the boards' last game; the OFF-SEASON case (boards built
2026-11-15, last game 2026-09-27, a corpus built 2026-10-02 covering
2026-09-27) builds; the reconciliation gate; a player who left the boards
loses his file; and the dark flag. Fixtures live under tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mlbstats_games as G
import mlbstats_rolling_export as R
import mlbstats_trends_export as T
from test_mlbstats_games import PK_A, PK_B, SEASON, game_a, game_b, write_corpus, write_payloads


def _w(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


#: The fixture games' season lines, by hand (test_mlbstats_games.game_a and
#: game_b): what a board built after both games would print.
HITTERS = [{"mlbam": 301, "pa": 3, "ab": 3, "hr": 0, "bb": 0},
           {"mlbam": 302, "pa": 3, "ab": 2, "hr": 0, "bb": 1},
           {"mlbam": 303, "pa": 2, "ab": 2, "hr": 1, "bb": 0},
           {"mlbam": 401, "pa": 2, "ab": 1, "hr": 0, "bb": 1},
           {"mlbam": 402, "pa": 1, "ab": 1, "hr": 0, "bb": 0}]
STARTERS = [{"mlbam": 101, "gs": 1, "g": 1, "tbf": 5, "ip": 0.7},
            {"mlbam": 201, "gs": 1, "g": 1, "tbf": 3, "ip": 1.0},
            {"mlbam": 103, "gs": 1, "g": 1, "tbf": 2, "ip": 0.7},
            {"mlbam": 202, "gs": 1, "g": 1, "tbf": 1, "ip": 0.3}]
RELIEVERS = [{"mlbam": 102, "g": 1, "tbf": 1, "ip": 0.3}]


def write_boards(d: Path, as_of: str, hitters=None, starters=None, relievers=None) -> None:
    _w(d / "hitter_leaderboards.json", {"season": SEASON, "as_of": as_of,
                                        "hitters": HITTERS if hitters is None else hitters})
    _w(d / "starter_leaderboards.json", {"season": SEASON, "as_of": as_of,
                                         "starters": STARTERS if starters is None else starters})
    _w(d / "bullpen_leaderboards.json", {"season": SEASON, "as_of": as_of,
                                         "relievers": RELIEVERS if relievers is None else relievers})


@pytest.fixture()
def fx(tmp_path):
    games = {PK_A: game_a(), PK_B: game_b()}
    wp, corpus, memo = tmp_path / "win_prob", tmp_path / "corpus", tmp_path / "memo"
    write_payloads(wp, games)
    write_corpus(corpus, games)            # manifest built_at 2026-10-02
    frame = G.player_game_frame(SEASON, corpus_dir=corpus, win_prob_dir=wp, memo_dir=memo)
    data = tmp_path / "data"
    return {"frame": frame, "data": data, "out": tmp_path / "out"}


def _export(fx, as_of, dates, **kw):
    write_boards(fx["data"], as_of, **kw)
    return R.export(out=fx["out"], data_dir=fx["data"], frame=fx["frame"],
                    game_dates=dates, log=lambda *a: None)


def test_game_sums_equal_the_board_counts_within_the_frame_coverage(fx):
    s = _export(fx, "2026-09-28", ["2026-09-27"])
    assert s["refused"] is None and s["written"]
    idx = json.loads((fx["out"] / R.INDEX_NAME).read_text(encoding="utf-8"))
    assert idx["covers_through"] == "2026-09-27" == idx["boards_last_game"]
    chk = idx["board_check"]
    assert chk["complete"] is True
    for blk in chk["boards"].values():
        assert blk["mismatched"] == {} and blk["without_games"] == 0
    # the files themselves sum to the board lines
    sd = fx["out"] / R.SHARD_DIR_NAME
    for b in HITTERS:
        doc = json.loads((sd / f"{b['mlbam']}.json").read_text(encoding="utf-8"))
        cols, games = doc["hit"]["cols"], doc["hit"]["games"]
        tot = {c: sum(g[cols.index(c)] for g in games) for c in ("pa", "ab", "hr", "bb")}
        assert tot == {k: b[k] for k in ("pa", "ab", "hr", "bb")}, b["mlbam"]
    for b in STARTERS + RELIEVERS:
        doc = json.loads((sd / f"{b['mlbam']}.json").read_text(encoding="utf-8"))
        cols, games = doc["pit"]["cols"], doc["pit"]["games"]
        assert sum(g[cols.index("bf")] for g in games) == b["tbf"]
        assert sum(g[cols.index("outs")] for g in games) == round(b["ip"] * 3)
        assert sum(g[cols.index("gs")] for g in games) == b.get("gs", 0)
    assert doc["pit"]["cols"] == R.PIT_COLS
    assert idx["counts"]["players"] == len(HITTERS) + len(STARTERS) + len(RELIEVERS)
    assert idx["corpus_built_at"] == "2026-10-02T12:00:00+00:00"


def test_games_in_a_file_are_in_start_time_order(fx):
    _export(fx, "2026-09-28", ["2026-09-27"])
    doc = json.loads((fx["out"] / R.SHARD_DIR_NAME / "301.json").read_text(encoding="utf-8"))
    # game B (17:05 UTC) before game A (02:05 UTC the next day, same Eastern date)
    assert [g[1] for g in doc["hit"]["games"]] == [1, 2]
    assert [g[0] for g in doc["hit"]["games"]] == ["2026-09-27", "2026-09-27"]


def test_a_frame_five_days_behind_the_boards_refuses_and_keeps_the_last_good_files(fx):
    good = _export(fx, "2026-09-28", ["2026-09-27"])
    assert good["written"]
    idx_before = (fx["out"] / R.INDEX_NAME).read_bytes()
    s = _export(fx, "2026-10-03", ["2026-09-27", "2026-10-02"])
    assert s["written"] is False
    assert "5 days before the boards' last game on 2026-10-02" in s["refused"]
    assert (fx["out"] / R.INDEX_NAME).read_bytes() == idx_before


def test_the_off_season_does_not_refuse(fx):
    """Boards rebuilt 2026-11-15 (their as_of moves every night all winter), last
    game 2026-09-27, a corpus built 2026-10-02 covering 2026-09-27: both GAME
    dates have stopped, so the build goes ahead."""
    assert fx["frame"].meta["corpus_built_at"].startswith("2026-10-02")
    s = _export(fx, "2026-11-15", ["2026-09-26", "2026-09-27"])
    assert s["refused"] is None and s["written"]
    idx = json.loads((fx["out"] / R.INDEX_NAME).read_text(encoding="utf-8"))
    assert idx["as_of"] == "2026-11-15" and idx["boards_last_game"] == "2026-09-27"
    assert idx["board_check"]["complete"] is True


def test_the_stale_rule_compares_game_dates_never_build_stamps():
    assert R.stale_reason("2026-09-27", "2026-09-27") is None
    assert R.stale_reason("2026-09-25", "2026-09-27") is None          # 2 days: builds
    assert "3 days" in R.stale_reason("2026-09-24", "2026-09-27")
    assert R.stale_reason(None, "2026-09-27") is not None
    assert R.boards_last_game_date("2026-11-15", ["2026-09-26", "2026-09-27"]) == "2026-09-27"
    assert R.boards_last_game_date("2026-09-26", ["2026-09-26", "2026-09-27"]) == "2026-09-26"
    assert R.boards_last_game_date("2026-03-01", ["2026-03-25"]) is None
    import inspect
    src = inspect.getsource(R.stale_reason)
    assert "built_at" not in src and "as_of" not in src


def test_a_frame_one_day_behind_builds_without_the_reconciliation_gate(fx):
    s = _export(fx, "2026-09-29", ["2026-09-27", "2026-09-28"])
    assert s["written"]
    idx = json.loads((fx["out"] / R.INDEX_NAME).read_text(encoding="utf-8"))
    assert idx["board_check"]["complete"] is False


def test_a_board_that_does_not_reconcile_refuses(fx):
    off = [dict(h) for h in HITTERS]
    off[0]["pa"] += 1
    s = _export(fx, "2026-09-28", ["2026-09-27"], hitters=off)
    assert s["written"] is False and "hitter_leaderboards pa: 1 of 5" in s["refused"]
    # at bats are reported, not gated (official scoring changes move them by one)
    off = [dict(h) for h in HITTERS]
    off[0]["ab"] += 1
    s = _export(fx, "2026-09-28", ["2026-09-27"], hitters=off)
    assert s["written"]
    idx = json.loads((fx["out"] / R.INDEX_NAME).read_text(encoding="utf-8"))
    assert idx["board_check"]["boards"]["hitter_leaderboards"]["mismatched"] == {"ab": 1}


def test_a_player_who_left_the_boards_loses_his_file(fx):
    _export(fx, "2026-09-28", ["2026-09-27"])
    sd = fx["out"] / R.SHARD_DIR_NAME
    assert (sd / "402.json").exists()
    s = _export(fx, "2026-09-28", ["2026-09-27"], hitters=HITTERS[:4])
    assert s["removed"] == 1 and not (sd / "402.json").exists()
    idx = json.loads((fx["out"] / R.INDEX_NAME).read_text(encoding="utf-8"))
    assert 402 not in idx["players"]["hit"]


def test_the_flag_is_dark_and_writes_only_the_preview_directory():
    assert T.MLBSTATS_DRAWER_LIVE is False
    assert R.out_dir() == T.PREVIEW_DIR
    assert R.SERVED_DIR == R.DATA_DIR / R.SHARD_DIR_NAME
    assert not (R.DATA_DIR / R.INDEX_NAME).exists(), "mlbstats_player_index.json shipped early"
    assert not any(R.SERVED_DIR.glob("*.json")), "mlbstats_player/*.json shipped early"
