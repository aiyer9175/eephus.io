# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CLV grading lives BESIDE the record, never inside it.

WHY A SIDECAR. The closing line does not exist when a pick is posted; it lands
hours later. Writing it back into the published row would be exactly the edit
`check_append_only` exists to forbid, and carving out an exception for "only the
CLV fields" would put a hole in the single guarantee that makes a public betting
record worth reading at all. So the record stays immutable and the grade lives in
data/betting_clv.json, keyed by bet_id.

`grade_clv` has existed since the module was written and nothing ever called it.
This is the wiring, and these are its tests.

WHAT THESE PIN
  1. Grading never mutates the record, and the record still passes its own
     append-only check afterwards.
  2. A pick is graded against the BOOK IT WAS TAKEN AT, not the best close
     across books. Grading a DraftKings bet against FanDuel's close invents
     value the bettor never had access to.
  3. A missing close snapshot produces an UNGRADED ENTRY WITH A REASON, not a
     missing row. A pick absent from this file would read as "no bet that day",
     which is the empty-but-valid failure this codebase keeps getting bitten by.
  4. Rates over an empty set are None, not 0.0.
  5. A total is only graded against the same NUMBER. A different line is a
     different bet.
  6. Grading is idempotent.
"""
from __future__ import annotations

import json

import pytest

be = pytest.importorskip("betting_export")
bi = pytest.importorskip("betting_ingest")


DAY = "2026-08-01"

RECORD = [
    {"bet_id": "aaaa1111bbbb2222", "posted_at": f"{DAY}T15:02:00+00:00",
     "slate_date": DAY, "market": "h2h", "selection": "NYM",
     "book": "draftkings", "odds_at_post": -140, "stake_units": 1.0,
     "result": "won"},
    {"bet_id": "cccc3333dddd4444", "posted_at": f"{DAY}T15:01:00+00:00",
     "slate_date": DAY, "market": "totals", "selection": "Under 8.5",
     "book": "fanduel", "odds_at_post": -105, "stake_units": 1.0,
     "result": "lost"},
]

RAW = [{
    "id": "evt1", "commence_time": f"{DAY}T23:10:00Z",
    "home_team": "New York Mets", "away_team": "Atlanta Braves",
    "bookmakers": [
        {"key": "draftkings", "title": "DraftKings",
         "last_update": f"{DAY}T22:55:00Z",
         "markets": [
             {"key": "h2h", "outcomes": [
                 {"name": "New York Mets", "price": -160},
                 {"name": "Atlanta Braves", "price": 140}]},
             {"key": "totals", "outcomes": [
                 {"name": "Over", "price": -110, "point": 8.5},
                 {"name": "Under", "price": -110, "point": 8.5}]}]},
        {"key": "fanduel", "title": "FanDuel",
         "last_update": f"{DAY}T22:56:00Z",
         "markets": [
             {"key": "h2h", "outcomes": [
                 {"name": "New York Mets", "price": -120},
                 {"name": "Atlanta Braves", "price": 100}]},
             {"key": "totals", "outcomes": [
                 {"name": "Over", "price": -125, "point": 8.5},
                 {"name": "Under", "price": -115, "point": 8.5}]}]},
    ],
}]


@pytest.fixture
def with_close(monkeypatch):
    monkeypatch.setattr(bi, "closing_snapshot",
                        lambda day: {"events": RAW} if day == DAY else None)


@pytest.fixture
def without_close(monkeypatch):
    monkeypatch.setattr(bi, "closing_snapshot", lambda day: None)


def _by_id(payload):
    return {p["bet_id"]: p for p in payload["picks"]}


def test_grading_does_not_touch_the_record(with_close, tmp_path):
    """The record is the evidence. Grading is derived from it and may never
    write to it."""
    before = json.dumps(RECORD, sort_keys=True)
    be.grade_record_clv(rows=RECORD, write=False)
    assert json.dumps(RECORD, sort_keys=True) == before
    be.check_append_only(RECORD, RECORD)          # still append-only clean


def test_a_pick_is_graded_at_the_book_it_was_taken_at(with_close):
    """THE MEASUREMENT. The Mets bet was posted at -140 on DraftKings, which
    closed -160 there and -120 on FanDuel. Grading against FanDuel would call a
    winner a loser."""
    g = _by_id(be.grade_record_clv(rows=RECORD, write=False))["aaaa1111bbbb2222"]
    assert g["graded"] is True
    assert g["odds_at_close"] == -160, (
        "the close must come from the pick's own book; -120 here means it "
        "grabbed FanDuel and invented value the bettor could not have had")
    assert g["beat_close"] is True
    assert g["clv_pct"] > 0


def test_a_total_is_graded_at_its_own_number(with_close):
    g = _by_id(be.grade_record_clv(rows=RECORD, write=False))["cccc3333dddd4444"]
    assert g["graded"] is True
    assert g["odds_at_close"] == -115, "Under 8.5 on FanDuel closed -115"


def test_a_total_on_a_different_line_is_not_graded(with_close):
    """A moved total is a different bet. Grading 9.5 against the 8.5 close would
    silently compare two different wagers."""
    row = dict(RECORD[1], bet_id="dddd", selection="Under 9.5")
    g = _by_id(be.grade_record_clv(rows=[row], write=False))["dddd"]
    assert g["graded"] is False
    assert "no closing" in g["reason"]


def test_a_missing_close_snapshot_is_named_not_skipped(without_close):
    """THE SILENT-EMPTY GUARD. A pick that vanishes from this file reads as a
    day with no bets."""
    payload = be.grade_record_clv(rows=RECORD, write=False)
    assert payload["n_graded"] == 0
    assert payload["n_ungraded"] == 2, "both picks must still appear"
    for g in payload["picks"]:
        assert g["graded"] is False
        assert "close job did not fire" in g["reason"]
    assert "no closing snapshot" in payload["ungraded_reasons"]


def test_rates_over_an_empty_set_are_none_not_zero(without_close):
    """A 0% beat-close rate over zero graded bets is a lie that looks like a
    measurement."""
    payload = be.grade_record_clv(rows=RECORD, write=False)
    assert payload["beat_close_rate"] is None
    assert payload["avg_clv_pct"] is None


def test_an_empty_record_grades_to_an_empty_report(with_close):
    payload = be.grade_record_clv(rows=[], write=False)
    assert payload["n_rows"] == 0 and payload["picks"] == []
    assert payload["beat_close_rate"] is None


def test_grading_is_idempotent(with_close):
    a = be.grade_record_clv(rows=RECORD, write=False)
    b = be.grade_record_clv(rows=RECORD, write=False)
    assert a["picks"] == b["picks"]


def test_the_sidecar_writes_where_the_page_can_read_it(with_close, tmp_path):
    out = tmp_path / "betting_clv.json"
    be.grade_record_clv(rows=RECORD, write=True, path=out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_graded"] == 2
    assert payload["source"].startswith("derived from")
