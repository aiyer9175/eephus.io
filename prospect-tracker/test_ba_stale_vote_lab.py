# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fixture tests for tools/ba_stale_vote_lab.py (BA_KEEP_FORWARD_READ Part C). No outcome, no
database and no build: every point is hand-made and run through the served
consensus.compute_consensus_point."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import ba_stale_vote_lab as LAB  # noqa: E402


def _s(source, date, fv, rank=None, key="p"):
    from scrapers import Snapshot
    return Snapshot(source=source, snapshot_date=date, interval_label=f"{source} {date}",
                    player_key=key, player_name="P", position="SS", org="TOR", rank=rank,
                    fv=fv, status="active")


KW = {"event_date": "2019-02-15", "total_fv_instances": 5}


def _point():
    # FanGraphs fresh (2019), MLB Pipeline two cycles old (2017), a constant anchor
    return [_s("fangraphs", "2019-02-01", 55.0), _s("mlb_pipeline", "2017-01-22", 45.0),
            _s("performance_ingest", "2018-10-01", 35.0)]


def test_votes_and_ages_skip_constant_anchors():
    assert LAB.votes(_point()) == {"fangraphs": 2019, "mlb_pipeline": 2017}
    assert LAB.ages(_point(), "2019-02-15") == {"fangraphs": 0, "mlb_pipeline": 2}


def test_rule_d_drops_the_stale_vote_only_when_a_fresh_one_remains():
    assert LAB.stale_outlets(_point(), "2019-02-15", 2) == ["mlb_pipeline"]
    only_stale = [_s("mlb_pipeline", "2017-01-22", 45.0)]
    assert LAB.stale_outlets(only_stale, "2019-02-15", 2) == []
    two_stale = [_s("fangraphs", "2016-02-01", 50.0), _s("mlb_pipeline", "2017-01-22", 45.0)]
    assert LAB.stale_outlets(two_stale, "2019-02-15", 2) == []
    assert LAB.stale_outlets(_point(), "2019-02-15", 2, only="baseballamerica") == []


def test_arm_values_through_the_served_point():
    s, t = LAB.arm_point("S", _point(), KW)
    assert s == pytest.approx(50.0) and t is False
    d, t = LAB.arm_point("D", _point(), KW)
    assert d == pytest.approx(55.0) and t is True
    w, t = LAB.arm_point("W", _point(), KW)
    assert w == pytest.approx((55.0 + 0.5 * 45.0) / 1.5, abs=0.005) and t is True
    d1, t = LAB.arm_point("D1", _point(), KW)
    assert d1 == pytest.approx(55.0) and t is True


def test_decay_grows_with_age():
    pt = [_s("fangraphs", "2019-02-01", 55.0), _s("mlb_pipeline", "2016-01-22", 45.0)]
    assert LAB.decay_weights(pt, "2019-02-15", None) == {"mlb_pipeline": 0.25}
    assert LAB.decay_weights([_s("fangraphs", "2019-02-01", 55.0)], "2019-02-15", None) is None


def test_one_cycle_old_vote_is_not_stale_under_d():
    pt = [_s("fangraphs", "2019-02-01", 55.0), _s("mlb_pipeline", "2018-01-22", 45.0)]
    assert LAB.stale_outlets(pt, "2019-02-15", 2) == []
    assert LAB.stale_outlets(pt, "2019-02-15", 1) == ["mlb_pipeline"]


def test_alias_rows_leave_with_their_outlet():
    pt = [_s("fangraphs", "2019-02-01", 55.0), _s("mlb_pipeline", "2017-01-22", 45.0),
          _s("mlb_pipeline_international", "2017-01-22", 45.0)]
    assert LAB.remove_outlets(pt, ["mlb_pipeline"]) == [pt[0]]


def test_null_drop_keeps_one_vote_and_the_count():
    rng = np.random.default_rng(1)
    pt = [_s("fangraphs", "2019-02-01", 55.0), _s("mlb_pipeline", "2017-01-22", 45.0),
          _s("baseballamerica", "2019-02-15", 60.0)]
    seen = {round(LAB.null_drop(pt, KW, 1, rng), 6) for _ in range(60)}
    assert seen <= {52.5, 57.5, 50.0} and len(seen) >= 2
    v = LAB.null_drop(pt[:1], KW, 3, rng)
    assert v == pytest.approx(55.0)


def test_planted_assignment_gives_the_highest_grade_to_the_lowest_outcome():
    units = [{"rid": 0, "fid": "vm_dev", "side": "hit", "key": "a", "war": 5.0,
              "outlet": "mlb_pipeline", "fv": 40.0},
             {"rid": 1, "fid": "vm_dev", "side": "hit", "key": "b", "war": -1.0,
              "outlet": "fangraphs", "fv": 55.0},
             {"rid": 2, "fid": "vm_dev", "side": "hit", "key": "c", "war": 2.0,
              "outlet": "mlb_pipeline", "fv": 50.0}]
    got = LAB.planted_assignment(units)
    assert got == {(1, "fangraphs"): 55.0, (2, "mlb_pipeline"): 50.0, (0, "mlb_pipeline"): 40.0}
    pt = LAB.plant_values(_point(), "mlb_pipeline", 70.0)
    assert [s.fv for s in pt] == [55.0, 70.0, 35.0]


def test_holm():
    assert LAB.holm({"G1": 0.01, "G2": 0.04}) == {"G1": 0.02, "G2": 0.04}
    assert LAB.holm({"G1": 0.03, "G2": 0.02}) == {"G2": 0.04, "G1": 0.04}
    assert LAB.holm({"G1": None, "G2": 0.02}) == {"G2": 0.02, "G1": None}


def test_registration_and_constants_match_the_document():
    doc = (HERE / LAB.DOC).read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in doc
    assert LAB.STALE_AGE == 2 and LAB.STALE_AGE_D1 == 1 and LAB.DECAY == 0.5
    assert LAB.NULL_K == 200 and LAB.PERM_SEED == 20261016
    assert LAB.ARTIFACT.parts[-3:] == ("_labs", "ba_grade", "ba_stale_vote_read.json")


def test_no_grouping_by_consensus_fv_level():
    src = (HERE / "tools" / "ba_stale_vote_lab.py").read_text(encoding="utf-8")
    for banned in ("fv_cell", "FV_CELLS", "by_fv", "fv_bucket", "cell_of"):
        assert banned not in src
