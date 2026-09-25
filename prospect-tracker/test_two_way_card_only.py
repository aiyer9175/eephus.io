# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Two-way players are on the starter board (owner decision 23, 2026-09-11).

Until 2026-09-11 the starter board dropped feed position TWP, so Shohei Ohtani's
card carried a card-only SEM+ scored against the served pool without entering it.
The owner admitted two-way players: they now enter the SEM+ pool, the rotation
rollup and starters[] like any primary pitcher who passes the true-starter
filter, and the betting model prices the games they start off their own SEM+.
The card-only block is retired (empty, with a note) and one flag,
starter_export.ADMIT_TWO_WAY_TO_BOARD, restores the split exactly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import betting_model as bm
import bullpen_export as be
import sem_plus
import starter_export as se

ROOT = Path(__file__).parent
CACHE = ROOT / ".cache" / "fa_statsapi_pitching_2026.json"


def _split(pid, name, pos, gs=12, ip="80.0"):
    return {"player": {"id": pid, "fullName": name}, "team": {"id": 108},
            "position": {"abbreviation": pos},
            "stat": {"gamesPitched": gs, "gamesStarted": gs, "inningsPitched": ip,
                     "earnedRuns": 30, "runs": 32, "baseOnBalls": 25, "strikeOuts": 90,
                     "homeRuns": 9, "hitByPitch": 3, "battersFaced": 330,
                     "numberOfPitches": 1300, "completeGames": 0, "groundOuts": 80,
                     "airOuts": 70, "strikes": 820}}


def test_the_admission_ships_on_with_the_ledger_key_bumped():
    """TRIPWIRE. Admitting two-way starters moves the pool anchor and the price
    of every game one starts, so it shipped in the same commit as the
    MODEL_VERSION bump. Move this assertion only with the flag."""
    assert se.ADMIT_TWO_WAY_TO_BOARD is True
    assert bm.MODEL_VERSION != "betting_runs_v1"


def test_the_default_mapping_still_drops_two_way_rows(monkeypatch):
    """The shared loader is unchanged: a caller that wants two-way rows asks."""
    monkeypatch.setattr(be, "_team_abbrev_map", lambda: {108: "LAA"})
    monkeypatch.setattr(be, "apply_current_team", lambda rows, label="": 0)
    splits = [_split(1, "A", "P"), _split(2, "B", "TWP"), _split(3, "C", "SS")]
    assert [r["mlbam"] for r in be.rows_from_pitching_splits(splits, 2026)] == [1]
    both = be.rows_from_pitching_splits(splits, 2026, ("P", "TWP"))
    assert [r["mlbam"] for r in both] == [1, 2]
    assert "pos" not in both[0] and both[1]["pos"] == "TWP"


def _export(tmp_path, monkeypatch, splits, admit):
    monkeypatch.setattr(be, "_team_abbrev_map", lambda: {108: "LAA", 119: "LAD"})
    monkeypatch.setattr(be, "apply_current_team", lambda rows, label="": 0)
    monkeypatch.setattr(se, "load_season_pitching",
                        lambda season, positions=("P",): be.rows_from_pitching_splits(
                            splits, season, positions))
    monkeypatch.setattr(se, "_active_mlbam_ids", lambda season: None)
    monkeypatch.setattr(se, "_join_xsem_plus", lambda starters, season: 0)
    monkeypatch.setattr(se, "_join_savant_custom", lambda starters, season: {})
    monkeypatch.setattr(se, "_join_war_ip_plus", lambda starters, season: {})
    monkeypatch.setattr(se, "_join_war_ip_plus_3yr", lambda starters: {})
    monkeypatch.setattr(se, "_war_source_vintage", lambda as_of=None: {})
    monkeypatch.setattr(se, "MULTIYR_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(se, "EVAL_PATH", tmp_path / "missing_eval.json")
    monkeypatch.setattr(se, "ADMIT_TWO_WAY_TO_BOARD", admit)
    out = tmp_path / f"starters_{admit}.json"
    se.export(2026, out_path=out, write=True, log=lambda *a, **k: None, today="2026-09-11")
    return json.loads(out.read_text(encoding="utf-8"))


def test_a_two_way_starter_enters_the_pool_rotation_and_board(tmp_path, monkeypatch):
    splits = [_split(1, "A", "P"), _split(2, "B", "P", gs=14, ip="85.2"),
              _split(9, "Two Way", "TWP", gs=14, ip="85.2")]
    on = _export(tmp_path, monkeypatch, splits, True)
    off = _export(tmp_path, monkeypatch, splits, False)
    ids_on = {r["mlbam"] for r in on["starters"]}
    ids_off = {r["mlbam"] for r in off["starters"]}
    assert 9 in ids_on and 9 not in ids_off
    assert on["pool"]["n"] == off["pool"]["n"] + 1
    rot = {t["team"]: t for t in on["teams"]}["LAA"]
    assert rot["n_starters"] == 3
    assert {t["team"]: t for t in off["teams"]}["LAA"]["n_starters"] == 2
    assert on["two_way"] == {"admitted": True, "mlbam": [9], "not_on_board": [],
                             "note": on["two_way"]["note"]}
    assert off["two_way"]["mlbam"] == [] and off["two_way"]["not_on_board"] == [9]
    # The retired card-only block: present, empty, and saying why.
    assert on["two_way_card_only"]["n"] == 0 and on["two_way_card_only"]["starters"] == []
    assert "retired" in on["two_way_card_only"]["note"]
    # The flag restores the split exactly: the card-only score rides again.
    assert off["two_way_card_only"]["n"] == 1
    assert off["two_way_card_only"]["starters"][0]["card_only"] is True


def test_the_label_never_names_a_two_way_line_the_board_did_not_admit(tmp_path,
                                                                        monkeypatch):
    """A two-way row that fails the true-starter filter (a DH who threw one
    inning in relief) is listed as not on the board, never as admitted."""
    splits = [_split(1, "A", "P"), _split(9, "Two Way", "TWP", gs=14, ip="85.2"),
              _split(8, "Mop Up", "TWP", gs=0, ip="1.0")]
    on = _export(tmp_path, monkeypatch, splits, True)
    ids = {r["mlbam"] for r in on["starters"]}
    assert 9 in ids and 8 not in ids
    assert on["two_way"]["mlbam"] == [9] and on["two_way"]["not_on_board"] == [8]


def test_the_admitted_board_prices_the_two_way_probable(tmp_path, monkeypatch):
    """The betting model reads the probable's SEM+ off starters[]: a two-way
    starter is priced as himself, not as his club's rotation average."""
    splits = [_split(1, "A", "P"), _split(9, "Two Way", "TWP", gs=14, ip="85.2")]
    on = _export(tmp_path, monkeypatch, splits, True)
    data = tmp_path / "data"
    data.mkdir()
    (data / "starter_leaderboards.json").write_text(json.dumps(on), encoding="utf-8")
    monkeypatch.setattr(bm, "DATA_DIR", data)
    si = bm.starter_inputs()
    assert 9 in si and si[9]["sem_plus"] == next(
        r["sem_plus"] for r in on["starters"] if r["mlbam"] == 9)


def test_the_real_board_admits_exactly_the_two_way_rows():
    """Against the cached 2026 season lines: the admitted pool is the primary
    pool plus the two-way rows that pass the true-starter filter."""
    if not CACHE.exists():
        pytest.skip("no cached 2026 pitching lines")
    d = json.loads(CACHE.read_text(encoding="utf-8"))
    splits = d["stats"][0]["splits"]
    rows_all = be.rows_from_pitching_splits(splits, 2026, ("P", "TWP"))
    primary = [r for r in rows_all if not r.get("pos")]
    tw = [r for r in rows_all if r.get("pos") == "TWP"]
    base = sem_plus.score_pool(se.build_starters(primary))
    both = sem_plus.score_pool(se.build_starters(primary + tw))
    n_tw_starters = sum(1 for s in se.build_starters(tw) if sem_plus.is_true_starter(s)
                        and s.ip >= sem_plus.POOL_MIN_IP)
    assert both["pool"]["n"] == base["pool"]["n"] + n_tw_starters
    ids = {r["mlbam"] for r in both["starters"]}
    for s in se.build_starters(tw):
        if sem_plus.is_true_starter(s):
            assert s.mlbam in ids


def test_the_card_only_scorer_is_kept_for_the_rollback():
    assert se.score_two_way_card_only([], [])["n"] == 0


def test_nothing_that_prices_a_game_reads_the_card_only_key():
    for name in ("betting_model.py", "betting_export.py", "leaderboard_vintages.py",
                 "betting_usage.py", "dfs_export.py"):
        p = ROOT / name
        if p.exists():
            assert "two_way_card_only" not in p.read_text(encoding="utf-8"), name


def test_the_card_bakes_it_as_card_only_and_never_over_a_board_row():
    """The card still reads the retired key on an older payload, and a board row
    always wins over it."""
    src = (ROOT / "mlb_player_export.py").read_text(encoding="utf-8")
    i = src.index("two_way_card_only")
    block = src[i:i + 900]
    assert '"cardOnly": True' in block
    assert re.search(r'if "pitch" in e:\s*\n\s*continue', block)
