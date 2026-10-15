# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV timing-edge read pins (EFV_BEAT_TIMING_EDGE, docs/efv-v2/EFV_BEAT_TIMING_EDGE.md).

1. The read grid and the registered constants (B, seed, group floor).
2. No look-ahead: the board point read at d is never later than d (nor any source date on
   it); the to-date swap reads season S from the to-date file only, restores every module
   attribute, and leaves the other seasons alone; the nightly window refuses a fetch.
3. The statistic: the paired within delta and its one-sided lower bound on synthetic rows.
4. The pass rule as the document fixes it; the artifact, when present, agrees with it.
5. Gate compliance: no FV-cell grouping, no dash characters.

Nothing here reads a frame row or an outcome.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_timing_edge as T  # noqa: E402
import milb_history as mh  # noqa: E402

SRC = ROOT / "tools" / "efv_timing_edge.py"
DOC = ROOT / "docs" / "efv-v2" / "EFV_BEAT_TIMING_EDGE.md"


# ---------------------------------------------------------------------------
# 1. the grid and the constants
# ---------------------------------------------------------------------------

def test_read_dates_are_the_registered_month_ends():
    assert T.read_dates(2018) == ["2018-04-30", "2018-05-31", "2018-06-30", "2018-07-31",
                                  "2018-08-31", "2018-09-30"]
    assert T.LV_YEARS == (2017, 2018, 2019)
    assert T.VM_YEARS == tuple(range(2017, 2024))
    assert T.B_DEFAULT == 2000 and T.SEED == 20261015
    assert T.MIN_GROUP_ROWS == 20
    assert 2020 in T.NO_MILB_SEASONS


def test_no_reserved_year_is_read():
    for y in T.LV_YEARS:
        assert y not in (2020, 2021)
    assert max(T.VM_YEARS) < 2025


def test_the_document_is_registered_and_fixes_the_rule():
    text = DOC.read_text(encoding="utf-8")
    assert "Registration status: REGISTERED" in text
    for frag in ("B 2000, seed 20261015", "lower bound of Delta", "lv_dev AND on",
                 "S-04-30, S-05-31, S-06-30, S-07-31, S-08-31, S-09-30"):
        assert frag in text, frag


# ---------------------------------------------------------------------------
# 2. no look-ahead
# ---------------------------------------------------------------------------

def _rec():
    return {"points": [
        {"snapshot_date": "2018-01-15", "consensus_fv_raw": 45.0, "per_source": {}},
        {"snapshot_date": "2018-02-20", "consensus_fv_raw": 50.0, "per_source": {}},
        {"snapshot_date": "2018-08-01", "consensus_fv_raw": 55.0,
         "per_source": {"fangraphs": {"fv_published": 55.0}}},
        {"snapshot_date": "2017-08-01", "consensus_fv_raw": 40.0, "per_source": {}},
    ]}


def test_point_at_is_the_board_as_it_stood():
    r = _rec()
    assert T.point_at(r, 2018, "2018-07-31")["consensus_fv_raw"] == 50.0
    assert T.point_at(r, 2018, "2018-08-01")["consensus_fv_raw"] == 55.0
    assert T.point_at(r, 2018, "2018-01-10") is None          # nothing of the year yet
    for d in T.read_dates(2018):
        pt = T.point_at(r, 2018, d)
        assert pt["snapshot_date"] <= d


def test_a_source_dated_after_the_read_date_refuses():
    pt = {"snapshot_date": "2018-06-01",
          "per_source": {"fangraphs": {"snapshot_date": "2018-07-15"}}}
    with pytest.raises(AssertionError):
        T.assert_point_dated(pt, "2018-06-30")
    T.assert_point_dated(pt, "2018-07-31")


def test_season_todate_swaps_the_read_season_only(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "CACHE_DIR", tmp_path)
    row = {"mlbam": 1, "name": "x", "season": 2018, "level": "AA", "league": "EAS",
           "age": 21, "pa": 120, "ab": 100, "ops": ".800", "obp": ".350", "slg": ".450",
           "avg": ".280", "so": 20, "bb": 15, "hr": 3}
    for sport in T.MINOR_SPORTS:
        for group in T.GROUPS:
            doc = {"season": 2018, "sport": sport, "group": group, "start": "2018-01-01",
                   "end": "2018-05-31", "rows": [row] if (sport == 12 and group == "hitting")
                   else []}
            T.todate_path(group, sport, 2018, "2018-05-31").write_text(json.dumps(doc),
                                                                      encoding="utf-8")
    orig = (mh.season_splits, mh.league_norms, mh.player_index, T.D._xline, T.D._parkline)
    with T.season_todate(2018, "2018-05-31"):
        assert mh.season_splits(12, 2018, "hitting") == [row]
        assert mh.season_splits(1, 2018, "hitting") == []
        assert mh.player_index(2018, "hitting") == {1: [row]}
        assert mh.league_norms(2018, "AA", "hitting") is None     # under 30 qualified lines
        if T.D._xline is not None:
            assert T.D._xline.maybe_adjust_row(row, 1, 2018, "AAA", "hit") is row
    assert (mh.season_splits, mh.league_norms, mh.player_index, T.D._xline,
            T.D._parkline) == orig


def test_a_receipt_with_another_end_date_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "CACHE_DIR", tmp_path)
    T.todate_path("hitting", 12, 2018, "2018-05-31").write_text(
        json.dumps({"season": 2018, "end": "2018-06-30", "rows": []}), encoding="utf-8")
    with pytest.raises(AssertionError):
        T.fetch_todate(12, 2018, "hitting", "2018-05-31", fetch=False)


def test_fetch_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "CACHE_DIR", tmp_path)
    assert T.fetch_todate(12, 2020, "hitting", "2020-06-30", fetch=False) == []
    with pytest.raises(FileNotFoundError):
        T.fetch_todate(12, 2018, "hitting", "2018-05-31", fetch=False)
    with pytest.raises(ValueError):
        T.fetch_todate(12, 2018, "hitting", "2019-05-31", fetch=False)
    monkeypatch.setattr(T, "_in_nightly_window", lambda now=None: True)
    with pytest.raises(RuntimeError):
        T.fetch_todate(12, 2018, "hitting", "2018-05-31", fetch=True)


def test_nightly_window_bounds():
    at = lambda h: datetime(2026, 10, 15, h, 0, tzinfo=timezone.utc)  # noqa: E731
    assert T._in_nightly_window(at(6)) and T._in_nightly_window(at(10))
    assert not T._in_nightly_window(at(5)) and not T._in_nightly_window(at(11))


# ---------------------------------------------------------------------------
# 3. the statistic
# ---------------------------------------------------------------------------

def _synthetic(n_per=40, groups=4, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(groups):
        for i in range(n_per):
            y = float(rng.normal())
            rows.append({"key": f"p{g}_{i}", "club": f"c{i % 6}", "group": f"hit|2018|{g}",
                         "y": y, "good": y + float(rng.normal(scale=0.3)),
                         "bad": float(rng.normal())})
    return rows


def test_paired_within_reads_a_clear_gap():
    rows = _synthetic()
    out = T.paired_within(rows, "good", "bad", B=300, seed=1)
    assert out["status"] == "derived"
    assert out["delta"] > 0.5
    assert out["lb95_one_sided"] > 0
    assert out["ci95"][0] <= out["lb95_one_sided"] <= out["ci95"][1]
    same = T.paired_within(rows, "good", "good", B=100, seed=1)
    assert same["delta"] == 0.0


def test_small_groups_are_left_out():
    rows = _synthetic(n_per=10)
    out = T.paired_within(rows, "good", "bad", B=50, seed=1)
    assert out["groups_kept"] == 0 and out["status"] == "undefined"


def test_club_cluster_is_a_cluster():
    rows = _synthetic()
    out = T.paired_within(rows, "good", "bad", cluster="club", B=100, seed=1)
    assert out["n_clusters"] == 6


# ---------------------------------------------------------------------------
# 4. the pass rule
# ---------------------------------------------------------------------------

def _frames(lv, vm):
    return {"lv_dev": {"primary": {"lb95_one_sided": lv}},
            "vm_dev": {"primary": {"lb95_one_sided": vm}}}


def test_the_pass_rule_needs_both_frames_above_zero():
    assert T.verdict(_frames(0.001, 0.002))["pass"] is True
    assert T.verdict(_frames(0.001, 0.0))["pass"] is False
    assert T.verdict(_frames(-0.01, 0.02))["pass"] is False
    assert T.verdict(_frames(None, 0.02))["pass"] is False


def test_the_artifact_agrees_with_the_rule():
    if not T.OUT_PATH.exists():
        pytest.skip("the read has not run")
    doc = json.loads(T.OUT_PATH.read_text(encoding="utf-8"))
    v = T.verdict(doc["frames"])
    assert doc["verdict"]["pass"] == v["pass"]
    assert doc["served"] is False and doc["role"] == "development"
    assert doc["seed"] == T.SEED and doc["B"] == T.B_DEFAULT
    assert set(doc["frames"]) == {"lv_dev", "vm_dev"}
    text = DOC.read_text(encoding="utf-8")
    assert f"**{doc['verdict']['verdict']}**" in text


# ---------------------------------------------------------------------------
# 5. gate compliance
# ---------------------------------------------------------------------------

def test_the_module_groups_nothing_by_consensus_fv_level():
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, str)}
    for bad in ("fv_cell", "fv_bucket", "by_fv", "fv_level", "fv_bin", "fv_stratum"):
        assert not any(bad in n.lower() for n in names), bad
    for ch in (chr(0x2014), chr(0x2013)):
        assert ch not in src
        assert ch not in DOC.read_text(encoding="utf-8")
        if T.OUT_PATH.exists():
            assert ch not in T.OUT_PATH.read_text(encoding="utf-8")


def test_the_module_never_calls_the_backtest_or_a_retrain():
    src = SRC.read_text(encoding="utf-8")
    assert "run_backtest" not in src
    assert "train_proj_models" not in src
    assert "build_spent" not in src
