# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Two-way players get a card-only SEM+ and never touch the starter pool.

The starter board drops feed position TWP, so Shohei Ohtani's card carried no
pitching index. Admitting him to the board would move the pool anchor and the
price of every game he starts (the betting model reads the probable's SEM+ off
starters[]), which is the owner's call. The card-only half: score the two-way line
against the exact served pool and publish it on a key nothing else reads.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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


def test_the_default_mapping_still_drops_two_way_rows(monkeypatch):
    monkeypatch.setattr(be, "_team_abbrev_map", lambda: {108: "LAA"})
    monkeypatch.setattr(be, "apply_current_team", lambda rows, label="": 0)
    splits = [_split(1, "A", "P"), _split(2, "B", "TWP"), _split(3, "C", "SS")]
    assert [r["mlbam"] for r in be.rows_from_pitching_splits(splits, 2026)] == [1]
    both = be.rows_from_pitching_splits(splits, 2026, ("P", "TWP"))
    assert [r["mlbam"] for r in both] == [1, 2]
    assert "pos" not in both[0] and both[1]["pos"] == "TWP"


def test_the_card_only_score_uses_the_served_pool_and_leaves_it_alone():
    if not CACHE.exists():
        pytest.skip("no cached 2026 pitching lines")
    d = json.loads(CACHE.read_text(encoding="utf-8"))
    splits = d["stats"][0]["splits"]
    rows_all = be.rows_from_pitching_splits(splits, 2026, ("P", "TWP"))
    rows = [r for r in rows_all if not r.get("pos")]
    assert rows == be.rows_from_pitching_splits(splits, 2026), (
        "the board's pool rows must be byte-identical with two-way rows split off")
    tw = [r for r in rows_all if r.get("pos") == "TWP"]
    res = se.score_two_way_card_only(rows, tw)
    served = sem_plus.score_pool(se.build_starters(rows))
    assert res.get("pool_n", served["pool"]["n"]) == served["pool"]["n"]
    served_ids = {r["mlbam"] for r in served["starters"]}
    for r in res["starters"]:
        assert r["card_only"] is True
        assert r["mlbam"] not in served_ids


def test_no_rows_means_no_card_scores():
    assert se.score_two_way_card_only([], [])["n"] == 0


def test_nothing_that_prices_a_game_reads_the_card_only_key():
    for name in ("betting_model.py", "betting_export.py", "leaderboard_vintages.py",
                 "betting_usage.py", "dfs_export.py"):
        p = ROOT / name
        if p.exists():
            assert "two_way_card_only" not in p.read_text(encoding="utf-8"), name


def test_the_card_bakes_it_as_card_only_and_never_over_a_board_row():
    src = (ROOT / "mlb_player_export.py").read_text(encoding="utf-8")
    i = src.index("two_way_card_only")
    block = src[i:i + 900]
    assert '"cardOnly": True' in block
    assert re.search(r'if "pitch" in e:\s*\n\s*continue', block)
