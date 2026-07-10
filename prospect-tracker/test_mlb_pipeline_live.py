# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Pipeline LIVE capture health gate (run_daily step d0b) — pure
unit tests, no network. The gate's job: a degraded parse must be
refused, a healthy board must pass untouched."""

from __future__ import annotations

from scrapers import Snapshot, validate_pipeline_live_board


def _board(n=100, fv=50.0, org="NYY", name_fmt="Player {i}"):
    return [Snapshot(source="mlb_pipeline", snapshot_date="2026-06-11",
                     interval_label="MLB Pipeline Live 2026-06-11",
                     player_key=f"p{i}", player_name=name_fmt.format(i=i),
                     position="SS", org=org, rank=i, fv=fv, status="active")
            for i in range(1, n + 1)]


def test_healthy_board_passes():
    assert validate_pipeline_live_board(_board()) == []


def test_short_board_refused():
    probs = validate_pipeline_live_board(_board(n=40))
    assert any("only 40" in p for p in probs)


def test_missing_fv_refused():
    probs = validate_pipeline_live_board(_board(fv=None))
    assert any("FV coverage" in p for p in probs)


def test_missing_org_refused():
    probs = validate_pipeline_live_board(_board(org=None))
    assert any("org coverage" in p for p in probs)


def test_duplicate_ranks_refused():
    rows = _board()
    rows[5] = rows[5]._replace(rank=1) if hasattr(rows[5], "_replace") else rows[5]
    if rows[5].rank != 1:           # dataclass, not namedtuple
        rows[5].rank = 1
    probs = validate_pipeline_live_board(rows)
    assert any("duplicate ranks" in p for p in probs)


def test_unresolved_names_refused():
    probs = validate_pipeline_live_board(_board(name_fmt="Person {i}"))
    assert any("unresolved player names" in p for p in probs)
