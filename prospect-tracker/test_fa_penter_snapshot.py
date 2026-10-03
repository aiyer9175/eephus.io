# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M04-05 (2026-09-25): the served P(enter) record and the October cadence.

docs/fa-2026-08-19/PENTER_DECISION_EVAL_PREREG.md scores "the LAST served
value before" each option decision, "read from artifact snapshots". Nothing
kept those values: data/fa_class.json is rewritten every night and the box's
nightly checkout reverts the tracked copy. And the daily scrape (run_monthly
d10) ran Nov-Mar while option inference opens Oct 1, so an October decision
was first seen on Nov 1.

Everything here runs on a throwaway DB or on source text. No network.
"""

from __future__ import annotations

import datetime
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.fixture()
def fa_db(tmp_path, monkeypatch):
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_penter.db", raising=False)
    try:
        storage.init_db()
    except sqlite3.OperationalError:
        pytest.skip("storage cannot init on a temp path in this layout")
    # No postseason schedule on disk: the option window opens November 1.
    import fa_pipeline
    monkeypatch.setattr(fa_pipeline, "POSTSEASON_CACHE_DIR", tmp_path)
    yield storage


def _write_class(tmp_path, members, generated_at="2026-09-25"):
    p = tmp_path / "fa_class.json"
    p.write_text(json.dumps({"generated_at": generated_at, "class_year": 2027,
                             "members": members}), encoding="utf-8")
    return p


def _rows(storage):
    con = sqlite3.connect(storage.DB_PATH)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM fa_penter_served_history ORDER BY player_key")]


MEMBERS = [
    {"key": "club_opt", "status": "pending_option", "type": "club_option",
     "optPrice": 12_000_000, "enterProb": 0.41, "enterProbSrc": "band_priced_club_side",
     "projAav": 14_000_000, "projAavP10": 8_000_000, "projAavP90": 22_000_000},
    {"key": "mutual", "status": "pending_option", "type": "mutual_option",
     "optPrice": 9_000_000, "enterProb": 0.85},
    {"key": "plain_ufa", "status": "locked", "type": "ufa", "enterProb": 1.0},
]


def test_snapshot_records_every_pending_option_member_read_back_from_the_file(fa_db, tmp_path):
    import fa_export
    n = fa_export.snapshot_served_penter(_write_class(tmp_path, MEMBERS))
    assert n == 2
    rows = _rows(fa_db)
    assert [r["player_key"] for r in rows] == ["club_opt", "mutual"]
    today = datetime.date.today().isoformat()
    assert all(r["snapshot_date"] == today and r["class_year"] == 2027 for r in rows)
    club = rows[0]
    assert club["enter_prob"] == 0.41 and club["enter_prob_src"] == "band_priced_club_side"
    assert club["opt_price_usd"] == 12_000_000 and club["fa_type"] == "club_option"
    assert club["fa_class_generated_at"] == "2026-09-25"
    # The v1 prior rows are scored objects too, and carry no v2 source.
    assert rows[1]["enter_prob"] == 0.85 and rows[1]["enter_prob_src"] is None


def test_a_second_write_the_same_night_replaces_and_adds_nothing(fa_db, tmp_path):
    import fa_export
    fa_export.snapshot_served_penter(_write_class(tmp_path, MEMBERS))
    later = [dict(MEMBERS[0], enterProb=0.44), MEMBERS[1]]
    fa_export.snapshot_served_penter(_write_class(tmp_path, later, "2026-09-25b"))
    rows = _rows(fa_db)
    assert len(rows) == 2
    assert rows[0]["enter_prob"] == 0.44, "the night's LAST served value must win"


def test_the_writer_cannot_be_pointed_at_a_past_date():
    import storage
    params = inspect.signature(storage.snapshot_fa_penter).parameters
    assert "snapshot_date" not in params


def test_d10p_runs_after_both_fa_export_branches():
    src = (HERE / "run_monthly.py").read_text(encoding="utf-8")
    i_b = src.index('"d10b. FA re-export off fresh projections"')
    i_p = src.index('"d10p. FA P(enter) served snapshot"')
    i_c = src.index('"d10c. TJStats Live second capture"')
    assert i_b < i_p < i_c
    # Outside the if/else, at the same depth as the d10 branch test.
    line = src[src.rfind("\n", 0, i_p) + 1:i_p]
    assert line.startswith("        with _step(") and not line.startswith("            ")


def test_the_daily_scrape_covers_the_whole_option_window():
    import fa_pipeline
    assert set(fa_pipeline.QO_WINDOW_MONTHS) <= set(fa_pipeline.DAILY_SCRAPE_MONTHS)
    assert 10 in fa_pipeline.DAILY_SCRAPE_MONTHS
    src = (HERE / "run_monthly.py").read_text(encoding="utf-8")
    assert "if date.today().month in _FA_DAILY_MONTHS:" in src
    assert "if date.today().month in (11, 12, 1, 2, 3):" not in src


def test_current_spotrac_class_pages_refresh_every_night_and_old_ones_stay_cached():
    import scrapers
    nxt = datetime.date.today().year + 1
    assert scrapers._cache_ttl_for_key(f"spotrac_fa_avail_{nxt}") <= 6 * 3600
    assert scrapers._cache_ttl_for_key(f"spotrac_fa_class_{nxt}") <= 6 * 3600
    assert scrapers._cache_ttl_for_key("spotrac_fa_class_2016") >= 24 * 3600


# ---- the mass-drop hold on option_exercised -------------------------------

def _member(key, status):
    return {"player_key": key, "player_name": key.replace("_", " ").title(),
            "status": status, "position": "SP"}


def test_every_pending_row_vanishing_at_once_stamps_no_exercise(fa_db):
    """The 2026-06-12 signature (every pending row gone, nothing re-listed),
    now inside the window the daily scrape covers. The day is November 4:
    since HOME_1 (2026-10-02) the window opens after the World Series, so an
    October 6 run would stamp nothing for the window's reason, not the hold's."""
    import fa_pipeline
    prior = {f"opt_{i}": _member(f"opt_{i}", "pending_option") for i in range(12)}
    out = fa_pipeline.track_winter_events(
        2027, prior, [_member("bystander", "locked")], signed_rows=[],
        as_of=datetime.date(2026, 11, 4))
    assert out["inserted"] == 0
    assert fa_db.load_fa_events(2027) == []


def test_a_real_decision_day_with_declines_still_stamps_every_exercise(fa_db):
    import fa_pipeline
    prior = {f"opt_{i}": _member(f"opt_{i}", "pending_option") for i in range(12)}
    avail = [_member("opt_0", "locked"), _member("bystander", "locked")]
    fa_pipeline.track_winter_events(2027, prior, avail, signed_rows=[],
                                    as_of=datetime.date(2026, 11, 4))
    types = [e["event_type"] for e in fa_db.load_fa_events(2027)]
    assert types.count("option_declined") == 1
    assert types.count("option_exercised") == 11


def test_a_small_pending_pool_is_not_held(fa_db):
    import fa_pipeline
    prior = {f"opt_{i}": _member(f"opt_{i}", "pending_option") for i in range(3)}
    fa_pipeline.track_winter_events(2027, prior, [_member("bystander", "locked")],
                                    signed_rows=[], as_of=datetime.date(2026, 11, 4))
    assert len(fa_db.load_fa_events(2027)) == 3
