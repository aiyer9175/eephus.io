# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""editorial_eval v2, the Spotlights re-score (census M02-04 and X01-10, owner
answer 2026-09-25 batch 4).

v1 scored a flag from its stored FV and a control from the source-snapshot
median, drew the controls as the first unflagged players by key, excluded every
key ever flagged, counted daily cohorts and used row-level Wilson intervals. v2
is registered beside it. These tests pin each repair on a synthetic board, and
pin that v1 (the GRPO forward gate's frozen template) did not move.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import editorial_eval as ee
import storage

ROOT = Path(__file__).resolve().parent


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    return tmp_path / "test.db"


def _board(rows):
    """rows: (player_key, night, consensus_fv, age)."""
    with storage.connect() as con:
        for pk, night, fv, age in rows:
            con.execute(
                "INSERT INTO metric_snapshots (player_key, snapshot_date, consensus_fv, "
                "age, status, payload_json) VALUES (?, ?, ?, ?, 'active', '{}')",
                (pk, night, fv, age))


def _flag(pk, ftype, emitted, fv=50.0, level="AA", age_band="21-23"):
    return {"player_key": pk, "flag_type": ftype, "emitted_at": emitted, "fv": fv,
            "fv_band": "50", "level": level, "age_band": age_band, "score": 1.0}


def _levels(keys, level="AA"):
    return {k: ([], level) for k in keys}


def _run(flags, levels):
    with storage.connect() as con:
        return ee.run_v2(con, flags, levels)


def test_flag_and_control_with_identical_histories_score_identically(db):
    _board([("a", "2026-06-01", 50.0, 22.0), ("a", "2026-07-01", 55.0, 22.1),
            ("b", "2026-06-01", 50.0, 22.0), ("b", "2026-07-01", 55.0, 22.1)])
    out = _run([_flag("a", "riser", "2026-06-01")], _levels(["a", "b"]))
    h = out["by_flag_type"]["riser"]["horizons"]["h30"]
    assert h["n"] == 1 and h["control_n"] == 1
    assert h["hit_rate"] == h["control_rate"] == 1.0


def test_a_control_with_a_minus_five_board_move_is_a_faller_hit(db):
    """X01-10: v1 read 0.0 over 4,827 faller control draws."""
    _board([("a", "2026-06-01", 50.0, 22.0), ("a", "2026-07-01", 50.0, 22.1),
            ("b", "2026-06-01", 50.0, 22.0), ("b", "2026-07-01", 45.0, 22.1)])
    out = _run([_flag("a", "faller", "2026-06-01")], _levels(["a", "b"]))
    h = out["by_flag_type"]["faller"]["horizons"]["h30"]
    assert h["hit_rate"] == 0.0 and h["control_rate"] == 1.0


def test_controls_are_a_seeded_random_draw_not_the_first_keys(db):
    keys = [f"c{i:02d}" for i in range(40)]
    first = ee._draw_controls(keys, "riser", "2026-06-01", "a")
    assert len(first) == ee.V2_CONTROLS_PER_FLAG == len(set(first))
    assert first != sorted(keys)[:ee.V2_CONTROLS_PER_FLAG]
    # reproducible, and independent of pool order or of any other flag
    assert ee._draw_controls(list(reversed(keys)), "riser", "2026-06-01", "a") == first
    assert ee._draw_controls(keys, "riser", "2026-06-01", "z") != first


def test_only_same_date_flags_are_excluded_from_the_pool(db):
    rows = []
    for k in ("a", "x", "y"):
        rows += [(k, "2026-06-01", 50.0, 22.0), (k, "2026-07-01", 50.0, 22.1),
                 (k, "2026-06-20", 50.0, 22.0), (k, "2026-07-20", 50.0, 22.1)]
    _board(rows)
    flags = [_flag("a", "riser", "2026-06-01"),
             _flag("x", "faller", "2026-06-01"),       # same date, other type: excluded
             _flag("y", "riser", "2026-06-20")]        # other date: still a control
    out = _run(flags, _levels(["a", "x", "y"]))
    h = out["by_flag_type"]["riser"]["horizons"]["h30"]
    # a (06-01) can draw only y; y (06-20) can draw a and x
    assert h["control_n"] == 3
    assert out["by_flag_type"]["faller"]["horizons"]["h30"]["control_n"] == 1


def test_cell_matches_level_and_age_band(db):
    _board([("a", "2026-06-01", 50.0, 22.0), ("a", "2026-07-01", 55.0, 22.1),
            ("lvl", "2026-06-01", 50.0, 22.0), ("lvl", "2026-07-01", 55.0, 22.1),
            ("old", "2026-06-01", 50.0, 26.0), ("old", "2026-07-01", 55.0, 26.1)])
    levels = {"a": ([], "AA"), "lvl": ([{"date": "2026-06-15", "from_level": "A+",
                                         "to_level": "AA"}], "AA"),
              "old": ([], "AA")}
    out = _run([_flag("a", "riser", "2026-06-01")], levels)
    # lvl was A+ on the emit night and old is in another age band: no pool
    assert out["by_flag_type"]["riser"]["flag_counts"]["empty_pool"] == 1


def test_no_board_row_at_the_end_is_unscoreable_not_a_miss(db):
    _board([("a", "2026-06-01", 50.0, 22.0), ("a", "2026-07-01", 55.0, 22.1),
            ("b", "2026-06-01", 50.0, 22.0)])          # b left the board
    out = _run([_flag("a", "riser", "2026-06-01")], _levels(["a", "b"]))
    h = out["by_flag_type"]["riser"]["horizons"]["h30"]
    assert h["n"] == 1 and h["control_n"] == 0 and h["verdict"] == "unread"


def test_cohorts_are_calendar_months(db):
    rows = []
    for k in ("a", "b"):
        for d in ("2026-06-01", "2026-06-15", "2026-07-01", "2026-07-15"):
            rows.append((k, d, 50.0, 22.0))
    _board(rows)
    out = _run([_flag("a", "riser", "2026-06-01"), _flag("a", "riser", "2026-06-15")],
               _levels(["a", "b"]))
    t = out["by_flag_type"]["riser"]
    assert t["matured_monthly_cohorts"] == 1
    assert t["kill_rule"]["eligible"] is False


def test_clustered_interval_is_wider_than_row_level_wilson():
    import numpy as np
    by_player = {"p1": [30, 30], "p2": [0, 30], "p3": [30, 30], "p4": [0, 30]}
    draws = ee._cluster_draws(by_player, np.random.default_rng(1))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    _, wlo, whi = ee._wilson(60, 120)
    assert (hi - lo) > 2 * (whi - wlo)


def test_v1_template_is_frozen_for_the_grpo_gate():
    assert ee.HIT_RULES == {
        "riser": {"fv_delta": +5.0, "direction": +1},
        "rebound": {"fv_delta": +5.0, "direction": +1},
        "faller": {"fv_delta": -5.0, "direction": -1},
    }
    assert ee.HORIZONS == (30, 60) and ee.MIN_COHORTS_FOR_KILL == 2
    for fn in ("_is_hit", "_controls", "_consensus_fv_asof", "_wilson"):
        assert callable(getattr(ee, fn))


def test_served_artifact_carries_v2_and_before_after():
    art = json.loads((ROOT / "data" / "editorial_eval.json").read_text(encoding="utf-8"))
    assert art["served_version"] == "v2" == art["v2"]["version"]
    assert "by_flag_type" in art                       # v1 block keeps its shape
    for ft in ("riser", "rebound", "faller"):
        assert set(art["before_after"][ft]) >= {"h30", "h60", "kill_rule"}
        h = art["v2"]["by_flag_type"][ft]["horizons"]["h30"]
        assert h["verdict"] in ("clears", "inside", "trails", "unread")
        if h["gap_ci"] is not None:
            assert h["clears_control"] == (h["gap_lo95"] > 0)
        assert art["before_after"][ft]["h30"]["after"]["hit_rate"] == h["hit_rate"]
        assert art["before_after"][ft]["h30"]["before"]["hit_rate"] == \
            art["by_flag_type"][ft]["horizons"]["h30"]["hit_rate"]


def test_receipts_read_the_v2_block_and_type_no_rates():
    gl = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    i = gl.index("spotlights: {")
    spec = gl[i:gl.index("fa_projection_engine: {", i)]
    assert "j.v2" in spec and "before_after" in spec
    px = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    i = px.index("function renderSpotlightTrackRecord")
    fn = px[i:px.index("function renderSpotlights()", i)]
    assert "j.v2" in fn and "before_after" in fn
    assert "renderSpotlightTrackRecord(bucket)" in px
    import re
    assert not re.search(r"\d+\.\d%", spec + fn), "a typed rate in a receipt"
