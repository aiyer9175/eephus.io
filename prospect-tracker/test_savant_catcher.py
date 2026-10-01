# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Contract for the Savant catcher blocking and throwing display columns (X05-02).

Pinned here:
  SEASON. Both boards stamp start_year on every row; a payload naming another
  season, or missing a pinned field, is refused (the catcher-framing path that
  ewar.py probed ignored its season, so the season is checked on the rows).
  SCOPE. Only rows whose primary position is C are stamped, and no team row
  gains a catcher column (dem_plus.TEAM_ROLLUP_FRAMING holds club totals).
  COVERAGE. On the served Defense board both boards reach >= 98% of qualified
  catchers, and a full season carries >= 60 catchers on each board.
  COPY. The three modules that called the catcher boards unanswerable no longer do.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import savant_catcher as SC

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8").replace("\r\n", "\n")

BLK_HEAD = "player_id,player_name,team_name,start_year,end_year,pitches,catcher_blocking_runs,blocks_above_average"
THR_HEAD = ("player_id,player_name,team_name,start_year,end_year,sb_attempts,catcher_stealing_runs,"
            "caught_stealing_above_average,pop_time,exchange_time,arm_strength")


def _loader(year=2026):
    blk = BLK_HEAD + "\n" + f'1,"A, B",SEA,{year},,3633,3,12\n' + f'9,"C, D",SEA,{year},,500,-1,-2\n'
    thr = THR_HEAD + "\n" + f'1,"A, B",SEA,{year},{year},67,-3.812,-5.77,1.9912,0.671,79.24\n'
    return lambda season, board: blk if board == "blocking" else thr


def test_shape_refuses_another_season_or_a_missing_field():
    blk = _loader()(2026, "blocking")
    assert SC.shape_ok(blk, 2026, "blocking")
    assert not SC.shape_ok(blk, 2025, "blocking")
    assert not SC.shape_ok(blk.replace("blocks_above_average", "baa"), 2026, "blocking")
    assert not SC.shape_ok(blk, 2026, "throwing")
    assert not SC.shape_ok("", 2026, "throwing")


def test_join_stamps_catchers_only_with_pinned_rounding():
    rows = [{"mlbam": 1, "pos": "C", "qualified": True},
            {"mlbam": 9, "pos": "1B", "qualified": True},
            {"mlbam": 2, "pos": "C", "qualified": False}]
    meta = SC.join(rows, 2026, loader=_loader())
    c, first_base, other = rows
    assert c["c_blk_runs"] == 3 and c["c_blk_aa"] == 12 and c["c_blk_pitches"] == 3633
    assert c["c_sb_att"] == 67 and c["c_cs_runs"] == -3.8 and c["c_cs_aa"] == -5.8
    assert c["c_pop"] == 1.99 and c["c_exchange"] == 0.67 and c["c_arm"] == 79.2
    assert not any(k.startswith("c_") for k in first_base), "a non-catcher row was stamped"
    assert not any(k.startswith("c_") for k in other), "a catcher with no Savant row was stamped"
    assert meta["n_catchers"] == 2 and meta["n_catchers_qualified"] == 1
    assert meta["n_joined"] == {"blocking": 1, "throwing": 1}
    assert meta["use"].startswith("display only")


def _board():
    p = ROOT / "data" / "defense_leaderboards.json"
    if not p.exists():
        pytest.skip("defense board absent")
    d = json.loads(p.read_text(encoding="utf-8"))
    m = d.get("savant_catcher")
    if not m or not m.get("available"):
        pytest.skip("catcher block unavailable on this build")
    return d, m


def test_served_board_joins_qualified_catchers_and_stays_off_team_rows():
    d, m = _board()
    assert m["season"] == d["season"]
    for b in SC.BOARDS:
        assert m["n_source_rows"][b] >= 60, (b, m["n_source_rows"][b])
        assert m["n_joined_qualified"][b] / m["n_catchers_qualified"] >= 0.98, b
    stamped = [r for r in d["fielders"] if any(k in SC.COLUMNS for k in r)]
    assert stamped and all(r["pos"] == "C" for r in stamped)
    for t in d.get("teams") or []:
        assert not any(k in SC.COLUMNS for k in t), t.get("team")


def test_every_column_renders_in_the_catching_view():
    m = re.search(r"\n  var DEFENSE_COLS = \[\n(.*?)\n  \];", JS, re.S)
    keys = set(re.findall(r'^    \{ key: "([a-z0-9_]+)"', m.group(1), re.M))
    assert set(SC.COLUMNS) <= keys, sorted(set(SC.COLUMNS) - keys)
    reg = re.search(r"\n  var COL_VIEWS = \{\n(.*?)\n  \};", JS, re.S).group(1)
    # ONE Catching view with all nine columns (owner answer M26-4, 2026-09-25);
    # below a 1024 window it may scroll inside its own frame (test_mlbstats_fit.py).
    view = re.search(r'\{ id: "catching", label: "Catching",(.*?)\] \}', reg, re.S)
    assert view
    shown = set(re.findall(r'"([a-z0-9_]+)"', view.group(1)))
    assert set(SC.COLUMNS) <= shown, sorted(set(SC.COLUMNS) - shown)


@pytest.mark.parametrize("path", ["positional_fit.py", "savant_oaa.py"])
def test_no_module_still_says_the_catcher_boards_did_not_answer(path):
    src = (ROOT / path).read_text(encoding="utf-8")
    assert "did not answer probes" not in src, path
