# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline tests for the MLB Pipeline vintage ingest (pipeline_vintage.py).

No network. These read the landed data/pipeline_vintages.json artifact and the
pure helper functions. A ground-truth anchor (2021 #1 = Wander Franco, MLBAM
677551) pins that the boards are the correct point-in-time vintages, and the
grade-crack is verified to parse (Hit/Power/Run/Arm/Field/Overall for a hitter,
Fastball/.../Control/Overall for a pitcher, Overall == FV).
"""

import json

import pytest

import pipeline_vintage as pv

WANDER_FRANCO = 677551


@pytest.fixture(scope="module")
def landed():
    if not pv.OUT_PATH.exists():
        pytest.skip("data/pipeline_vintages.json not landed; run pipeline_vintage.py first")
    data = json.loads(pv.OUT_PATH.read_text(encoding="utf-8"))
    if not data.get("vintages"):
        pytest.skip("landed artifact has no vintages")
    return data


def test_artifact_shape(landed):
    assert "_meta" in landed and "vintages" in landed
    meta = landed["_meta"]
    assert "data-graph.mlb.com" in meta["source"]
    assert meta["years"], "no years landed"


def test_at_least_one_full_hundred_board(landed):
    """>= 1 landed year is a complete 100-player board, all with mlbam ids."""
    full = [
        y for y, board in landed["vintages"].items()
        if len(board) == 100 and all(r.get("mlbam") for r in board)
    ]
    assert full, "expected at least one 100-player board with full mlbam coverage"


def test_high_mlbam_fill_rate(landed):
    total = sum(len(b) for b in landed["vintages"].values())
    with_id = sum(1 for b in landed["vintages"].values() for r in b if r.get("mlbam"))
    assert total > 0
    assert with_id / total >= 0.98, "mlbam join rate unexpectedly low"


def test_anchor_2021_number_one_is_wander_franco(landed):
    board_2021 = landed["vintages"].get("2021")
    assert board_2021, "2021 vintage not landed"
    top = min(board_2021, key=lambda r: (r["rank"] is None, r["rank"]))
    assert top["rank"] == 1
    assert top["mlbam"] == WANDER_FRANCO
    assert "Franco" in (top["name"] or "")


def test_helpers_offline(landed):
    board = pv.vintage_board(2021)
    assert isinstance(board, list) and len(board) >= 90
    assert all(isinstance(r, dict) for r in board)

    hist = pv.player_vintages(WANDER_FRANCO)
    assert hist, "Franco should appear in >= 1 vintage"
    years = [h["year"] for h in hist]
    assert years == sorted(years), "player_vintages must be oldest-first"
    y2021 = next(h for h in hist if h["year"] == 2021)
    assert y2021["rank"] == 1

    # unknown id -> empty, never raises
    assert pv.player_vintages(-1) == []
    assert pv.player_vintages(None) == []


def test_grades_cracked_and_parse(landed):
    """Grade subfields were recovered; verify they parse as 20-80 ints, FV==Overall."""
    franco = next(
        (r for r in landed["vintages"]["2021"] if r.get("mlbam") == WANDER_FRANCO), None
    )
    assert franco is not None
    grades = franco.get("grades")
    assert grades, "Wander Franco 2021 hitter grades should be present"
    assert franco["side"] == "hit"
    for tool in ("hit", "power", "run", "arm", "field", "overall"):
        assert tool in grades, f"missing hitter tool {tool}"
        assert isinstance(grades[tool], int) and 20 <= grades[tool] <= 80
    assert grades["hit"] == 80          # Franco's fabled 80 hit tool
    assert grades["overall"] == 70      # 70 FV / #1 overall
    assert franco.get("fv") == grades["overall"]

    # A pitcher vintage parses on the pitching key set.
    pitcher = next(
        (r for r in landed["vintages"]["2021"] if r.get("side") == "pit" and r.get("grades")),
        None,
    )
    assert pitcher is not None, "expected at least one graded pitcher in 2021"
    pg = pitcher["grades"]
    assert "overall" in pg and isinstance(pg["overall"], int)
    assert any(k in pg for k in ("fastball", "curveball", "slider", "changeup", "control"))
    assert all(isinstance(v, int) and 20 <= v <= 80 for v in pg.values())
