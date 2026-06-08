# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for the TJStats scraper + ingest (tjstats.py).

Synthetic payloads only — no network. Covers the join (MLBAM id + scout FV),
FV gating on historical boards, org mapping, validation guards, and idempotent
per-(MLBAM, snapshot) storage with the ranking-integrity property (historical
snapshots land on older dates and never overwrite the Live row)."""

from __future__ import annotations

import json

import pytest

import storage
import tjstats


# ── Synthetic fixtures shaped like the real endpoints ────────────────────────
def _rankings():
    return [
        {"rank_value": "1", "player_id": "815908", "name": "Jesús Made", "prev_rank": "1",
         "position": "SS", "parent_org_id": "158", "age": "18", "height": "6' 1\"",
         "weight": "221", "bat_side": "S", "throw_side": "R", "report": "Elite bat."},
        {"rank_value": "2", "player_id": "815549", "name": "Ryan Sloan", "prev_rank": "4",
         "position": "P", "parent_org_id": "136", "age": "19", "report": "Big arm."},
    ]


def _batters():
    return [{"player_id": "815908", "fv": "60.0", "hit_fv": "60.0", "hit_pv": "45.0",
             "power_fv": "55.0", "power_pv": "40.0", "speed_fv": "55.0", "speed_pv": "55.0",
             "defense_fv": "55.0", "defense_pv": "50.0", "decisions_fv": "60.0",
             "eta": "2027", "updated_at": "2026-05-12 19:19:35"}]


def _pitchers():
    return [{"player_id": "815549", "fv": "60.0", "fastball_fv": "70.0", "fastball_pv": "60.0",
             "slider_fv": "60.0", "command_fv": "50.0", "risk": "High", "eta": "2028",
             "updated_at": "2026-05-12 19:19:35"}]


def _bio():
    return [{"player_id": "815908", "abbreviation": "MIL", "parent_org_id": "158"},
            {"player_id": "815549", "abbreviation": "SEA", "parent_org_id": "136"}]


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "tj.db")
    storage.init_db()


# ── build_board: join + FV + tools + org ─────────────────────────────────────
def test_build_board_joins_fv_and_tools():
    board = tjstats.build_board(_rankings(), _batters(), _pitchers(), _bio(), with_fv=True)
    assert len(board) == 2
    made = board[0]
    assert made["mlbam_id"] == "815908" and made["rank"] == 1 and made["fv"] == 60.0
    assert made["type"] == "batter" and made["org"] == "MIL"
    # future grades map to eephus tool keys (power -> game_pwr, defense -> field)
    assert made["tools"] == {"hit": 60.0, "game_pwr": 55.0, "speed": 55.0, "field": 55.0}
    assert made["report"] == "Elite bat."
    sloan = board[1]
    assert sloan["type"] == "pitcher" and sloan["fv"] == 60.0
    assert sloan["tools"]["fb"] == 70.0 and sloan["tools"]["cmd"] == 50.0
    assert sloan["risk"] == "High"


def test_build_board_historical_has_no_fv():
    # with_fv=False (a snapshot older than current scout grades) -> FV/tools NULL,
    # so we never stamp today's grades on an old date.
    board = tjstats.build_board(_rankings(), _batters(), _pitchers(), _bio(), with_fv=False)
    assert all(r["fv"] is None for r in board)
    assert all(r["tools"] == {} for r in board)
    # rank + bio + writeup are still point-in-time present
    assert board[0]["rank"] == 1 and board[0]["report"] == "Elite bat."


def test_org_map_covers_athletics_and_nationals():
    assert tjstats.MLBAM_TEAM_ID_TO_ABBR["133"] == "ATH"
    assert tjstats.MLBAM_TEAM_ID_TO_ABBR["120"] == "WSH"
    # falls back to the team-id map when bio has no abbreviation
    r = {"parent_org_id": "133"}
    assert tjstats._org_for(r, None) == "ATH"


# ── validation guards ────────────────────────────────────────────────────────
def test_validate_rejects_short_payload():
    board = tjstats.build_board(_rankings(), _batters(), _pitchers(), _bio())
    with pytest.raises(tjstats.TJStatsValidationError):
        tjstats.validate_board(board, require_fv=True, expect_min=90)


def test_validate_rejects_dupes_and_offscale():
    good = tjstats.build_board(_rankings(), _batters(), _pitchers(), _bio())
    with pytest.raises(tjstats.TJStatsValidationError):  # off-scale FV
        bad = [dict(good[0], fv=140.0), dict(good[1])]
        tjstats.validate_board(bad, require_fv=True, expect_min=2)
    with pytest.raises(tjstats.TJStatsValidationError):  # duplicate MLBAM id
        dupe = [dict(good[0]), dict(good[0])]
        tjstats.validate_board(dupe, require_fv=False, expect_min=2)


# ── ingest: storage, key resolution, idempotency, ranking integrity ─────────
def _live_scrape(date="2026-06-08"):
    board = tjstats.build_board(_rankings(), _batters(), _pitchers(), _bio(), with_fv=True)
    return {"kind": "live", "label": f"Live {date}", "effective_date": date,
            "captured_at": f"{date}T01:00:00+00:00", "source_modified_at": None,
            "source_url": tjstats.SOURCE_PAGE, "board": board}


def test_ingest_writes_both_stores_and_resolves_keys(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    stats = tjstats.ingest_board(_live_scrape())
    assert stats["n_players"] == 2 and stats["snapshots_written"] == 2
    assert stats["sidecar_written"] == 2 and stats["name_fallback"] == 2  # no photo map yet

    # generic snapshots row (consensus input) — name-slug key, source=tjstats
    snaps = storage.load_all_snapshots()
    tj = [s for s in snaps if s.source == "tjstats"]
    assert len(tj) == 2
    made = next(s for s in tj if s.player_key == "jesus_made")
    assert made.fv == 60.0 and made.rank == 1 and made.org == "MIL"
    assert made.snapshot_date == "2026-06-08" and made.interval_label == "Live 2026-06-08"

    # sidecar row — MLBAM-keyed grain with writeup + capture timestamp
    side = storage.load_tjstats_snapshots("Live 2026-06-08")
    assert {r["mlbam_id"] for r in side} == {"815908", "815549"}
    s_made = next(r for r in side if r["mlbam_id"] == "815908")
    assert s_made["writeup"] == "Elite bat." and s_made["captured_at"].endswith("+00:00")
    assert s_made["with_fv"] == 1 and json.loads(s_made["grades_json"])["hit_fv"] == 60.0


def test_ingest_prefers_mlbam_join_over_name(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    # seed an MLBAM->key mapping that differs from the name slug
    storage.upsert_photo_ctx({815908: {"ctx": "67", "player_key": "jesus_made_canonical"}})
    stats = tjstats.ingest_board(_live_scrape())
    assert stats["id_join"] == 1  # made resolved via MLBAM map
    keys = {s.player_key for s in storage.load_all_snapshots() if s.source == "tjstats"}
    assert "jesus_made_canonical" in keys


def test_idempotent_same_day_and_history_does_not_touch_live(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    tjstats.ingest_board(_live_scrape("2026-06-08"))
    tjstats.ingest_board(_live_scrape("2026-06-08"))   # same-day re-run
    side = storage.load_tjstats_snapshots()
    assert len([r for r in side if r["snapshot_label"] == "Live 2026-06-08"]) == 2  # upserted in place, not duplicated

    # a named historical board lands in the SIDECAR ONLY — it must never enter the
    # generic snapshots table (the consensus input), so historical TJStats data
    # can't shift present-day consensus or farm rankings.
    hist = {"kind": "named", "snapshot_id": "3", "label": "April 2026",
            "effective_date": "2026-04-14", "captured_at": "2026-06-08T01:00:00+00:00",
            "with_fv": False, "source_url": tjstats.SOURCE_PAGE,
            "board": tjstats.build_board(_rankings(), [], [], _bio(), with_fv=False)}
    res = tjstats.ingest_board(hist)
    assert res["snapshots_written"] == 0 and res["sidecar_written"] == 2
    tj = [s for s in storage.load_all_snapshots() if s.source == "tjstats"]
    # the only tjstats rows in the consensus table are the Live ones — no 'April 2026'
    assert {s.interval_label for s in tj} == {"Live 2026-06-08"}
    live_made = next(s for s in tj if s.player_key == "jesus_made")
    assert live_made.fv == 60.0 and live_made.snapshot_date == "2026-06-08"   # current intact
    # but the historical board IS in the point-in-time sidecar (Time Machine)
    assert any(r["snapshot_label"] == "April 2026" for r in storage.load_tjstats_snapshots())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
