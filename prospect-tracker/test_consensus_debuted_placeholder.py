# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A debuted player's placeholder consensus points are dropped (owner answer
Q2, 2026-10-22, 'Exclude for debuted').

The auto-discovery stamp (performance_ingest, a flat FV 35) keeps firing on a
debuted player's MLB line. Once his real sources stop voting (a graduates row
carries no FV), the last-resort fold-back let the stamp make a point of its own,
which became his latest consensus, his low and one end of his range: Mason
Miller read 'Consensus range 35 (Oct 2026)-49'. The fix drops constant-anchor-only
points from a DEBUTED player's series (build_timeseries for a snapshot debut,
storage.export_timeseries_json for an MLB API debut or an outright); prospects
keep the fold-back. Pure unit tests: no DB, no network, no data/ artifacts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import consensus
from consensus import build_timeseries, strip_placeholder_points
from scrapers import Snapshot

ROOT = Path(__file__).parent


def _s(source, fv, date, *, status="active", label=None, key="mm"):
    return Snapshot(source=source, snapshot_date=date,
                    interval_label=label or f"{source} {date}",
                    player_key=key, player_name="Mason Test", position="RHP",
                    org="ATH", rank=None, fv=fv, status=status, tools=None)


def _graduate_with_stamp():
    return [
        _s("fangraphs", 40.0, "2022-01-20"),
        _s("fangraphs", 50.0, "2023-01-20"),
        _s("fangraphs", None, "2023-11-13", status="debuted", label="2023graduates"),
        _s("performance_ingest", 35.0, "2026-10-02", label="2026_performance"),
    ]


def _one(ts, key="mm"):
    return next(p for p in ts if p.player_key == key)


def test_the_defect_reproduces_with_the_drop_off(monkeypatch):
    monkeypatch.setattr(consensus, "DROP_DEBUTED_PLACEHOLDER_POINTS", False)
    p = _one(build_timeseries(_graduate_with_stamp()))
    assert p.status == "debuted"
    assert p.points[-1].sources_contributing == ["performance_ingest"]
    assert p.fv_close == 35.0 and p.fv_low == 35.0 and p.fv_low_date == "2026-10-02"


def test_debuted_latest_consensus_is_the_real_last_grade():
    p = _one(build_timeseries(_graduate_with_stamp()))
    assert all("performance_ingest" not in pt.sources_contributing for pt in p.points)
    assert p.points[-1].snapshot_date < "2026-10-02"
    assert p.fv_close == p.points[-1].consensus_fv
    assert p.fv_close > 35.0
    assert p.fv_low_date != "2026-10-02" and p.fv_high >= p.fv_close


def test_debuted_player_with_no_real_grade_has_no_consensus():
    snaps = [_s("performance_ingest", 35.0, "2026-01-01", label="2026_performance", key="x"),
             _s("auto_detect", None, "2026-05-01", status="debuted", key="x")]
    p = _one(build_timeseries(snaps), "x")
    assert p.status == "debuted"
    assert p.points == []
    assert p.fv_close == 0.0 and p.fv_low is None and p.fv_high is None


def test_a_prospect_keeps_the_last_resort_fold_back():
    p = _one(build_timeseries([_s("performance_ingest", 35.0, "2026-06-01", key="pr")]), "pr")
    assert p.status != "debuted"
    assert len(p.points) == 1 and p.fv_close == 35.0


def test_a_real_grade_at_the_stamp_date_is_kept():
    # A real source still voting when the stamp fires is not a placeholder.
    snaps = [_s("fangraphs", 40.0, "2024-01-20", key="r"),
             _s("auto_detect", None, "2024-06-01", status="debuted", key="r"),
             _s("performance_ingest", 35.0, "2026-10-02", label="2026_performance", key="r")]
    p = _one(build_timeseries(snaps), "r")
    assert p.points[-1].snapshot_date == "2026-10-02"
    assert p.points[-1].sources_contributing == ["fangraphs"]


def test_strip_rereads_the_candles_for_a_debut_known_only_at_export(monkeypatch):
    # storage.export_timeseries_json learns some debuts from the MLB API date or an
    # outright, after build_timeseries ran; the seam strips and re-reads the candles.
    snaps = [_s("fangraphs", 45.0, "2023-01-20", key="api"),
             _s("fangraphs", None, "2024-01-20", label="FanGraphs 2024 drop", key="api"),
             _s("performance_ingest", 35.0, "2026-10-02", label="2026_performance", key="api")]
    p = _one(build_timeseries(snaps), "api")
    assert p.status != "debuted" and p.fv_close == 35.0
    assert strip_placeholder_points(p) is True
    assert p.points[-1].snapshot_date == "2023-01-20"
    assert p.fv_close == p.points[-1].consensus_fv > 35.0
    assert p.fv_low == p.fv_close and p.fv_low_date == "2023-01-20"
    assert strip_placeholder_points(p) is False   # idempotent


def test_the_export_seam_applies_the_rule_on_the_cascade_debut_test():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    fn = src[src.index("def export_timeseries_json"):]
    seam = fn[:fn.index("source_events_by_key = load_source_events()")]
    assert "_consensus_q2.DROP_DEBUTED_PLACEHOLDER_POINTS" in seam
    assert "_consensus_q2.strip_placeholder_points(_p_q2)" in seam
    for test in ('_p_q2.status == "debuted"', '.get("mlb_debut_date")', '"outrighted"'):
        assert test in seam
    # the seam runs before the graduation cascade reads any point
    assert fn.index("_consensus_q2.strip_placeholder_points") < fn.index("grads.append(p)")
