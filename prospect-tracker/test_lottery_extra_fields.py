# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lottery-odds backend: top-6 odds + team record (2026-07-31).

Tankathon's projected-order table already published a "Top 6" column (the
chance of landing anywhere in the 6-pick lottery) and a "Record" column next
to the "#1 OVR" column we were keeping. The scraper found the odds cell by
scanning for the LAST cell containing '%', which happened to land on
'#1 OVR' but gave no way to reach 'Top 6' at all.

Cell-index trap this pins: the header row and the data rows have DIFFERENT
lengths. Measured on .cache/tankathon_mlb.html (2026-07-31):

    header (10): Pick|Team|Record Rec|Win% Pct|GB|Streak|L10|Top 6|#1 OVR|''
    data   ( 9): 1|Colorado COL|42 - 67|.385|--|Lost 4|3-7|86.3 %|17.95 %

so the two odds columns are indexed from the END of the DATA row, and a
header-aligned index would be off by one.

Offline: parses .cache/, and the storage round-trip uses an isolated
per-test DB via monkeypatched DB_PATH."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import scrapers
import storage
from scrapers import scrape_tankathon_lottery

CACHE = Path(__file__).parent / ".cache"

# Sanity bounds for an MLB regular season. A "record" parsed out of the L10
# column ("3-7") would blow the lower bound on a mid-season page.
_MIN_GAMES, _MAX_GAMES = 10, 163


class CellParsers(unittest.TestCase):
    def test_pct_cell(self):
        self.assertEqual(scrapers._parse_pct_cell("17.95 %"), 17.95)
        self.assertEqual(scrapers._parse_pct_cell("86.3 %"), 86.3)

    def test_empty_pct_is_none_not_zero(self):
        """A playoff team has no published chance. That is NOT a published
        0% - conflating them would render a real claim we never received."""
        for raw in ("", "--", "-", "n/a"):
            self.assertIsNone(scrapers._parse_pct_cell(raw), raw)

    def test_record_cell_prefers_the_spaced_pattern(self):
        cells = ["1", "Colorado COL", "42 - 67", ".385", "--", "Lost 4", "3-7",
                 "86.3 %", "17.95 %"]
        self.assertEqual(scrapers._parse_record_cell(cells), (42, 67))

    def test_record_cell_never_reads_the_l10_column(self):
        """'3-7' (last ten) has no spaces around the dash; '42 - 67' does.
        Without that discrimination a team's L10 becomes its season record."""
        self.assertEqual(scrapers._parse_record_cell(["x", "y", "3-7"]),
                         (None, None))

    def test_record_cell_missing(self):
        self.assertEqual(scrapers._parse_record_cell(["1", "COL"]), (None, None))


class TankathonExtraFields(unittest.TestCase):
    def setUp(self):
        if not (CACHE / "tankathon_mlb.html").exists():
            self.skipTest("no cached Tankathon page")
        self.rows = scrape_tankathon_lottery(2027)
        self.regular = [r for r in self.rows if r["round_label"] == "1"]

    def test_every_row_carries_the_new_keys(self):
        for r in self.rows:
            for k in ("odds_pct", "odds_top6_pct", "wins", "losses"):
                self.assertIn(k, r, f"{k} missing from {r}")

    def test_regular_rows_all_have_a_record(self):
        self.assertGreaterEqual(len(self.regular), 30)
        for r in self.regular:
            self.assertIsNotNone(r["wins"], r)
            self.assertIsNotNone(r["losses"], r)
            total = r["wins"] + r["losses"]
            self.assertTrue(_MIN_GAMES <= total <= _MAX_GAMES,
                            f"{r['team']} played {total} games: {r}")

    def test_top6_is_captured_wherever_number_one_odds_are(self):
        """The two columns are published together; capturing one without the
        other means the end-indexing slipped."""
        for r in self.regular:
            self.assertEqual(r["odds_pct"] is None, r["odds_top6_pct"] is None,
                             f"odds/top6 presence disagrees: {r}")

    def test_at_least_the_lottery_slots_carry_odds(self):
        with_odds = [r for r in self.regular if r["odds_pct"] is not None]
        self.assertGreaterEqual(len(with_odds), 6)

    def test_top6_dominates_number_one_odds(self):
        """P(top 6) >= P(#1) is an arithmetic necessity - #1 is inside the
        top 6. A violation means the two columns got swapped."""
        for r in self.regular:
            if r["odds_pct"] is not None and r["odds_top6_pct"] is not None:
                self.assertGreaterEqual(r["odds_top6_pct"], r["odds_pct"], r)

    def test_odds_are_percentages_not_probabilities(self):
        for r in self.regular:
            for k in ("odds_pct", "odds_top6_pct"):
                if r[k] is not None:
                    self.assertTrue(0.0 <= r[k] <= 100.0, f"{k}={r[k]} in {r}")

    def test_playoff_rows_carry_no_odds(self):
        """Picks 19-30 are playoff teams: no lottery entry, so both odds
        columns are blank on the page."""
        for r in self.regular:
            if r["pick_pos"] >= 19:
                self.assertIsNone(r["odds_pct"], r)
                self.assertIsNone(r["odds_top6_pct"], r)

    def test_comp_picks_are_excluded_from_standings_fields(self):
        """Comp picks come from a sidebar with no standings columns, and
        their pick_pos (31-42) is a synthetic renumbering, not a real slot.
        Every standings-derived field must stay None so nothing can average
        them into a real number."""
        for r in self.rows:
            if r["round_label"] in ("1A", "1B"):
                self.assertIsNone(r["wins"], r)
                self.assertIsNone(r["losses"], r)
                self.assertIsNone(r["odds_top6_pct"], r)
                self.assertGreaterEqual(r["pick_pos"], 31)


# ---------------------------------------------------------------------------
# Storage round-trip. pytest style so each test gets its own DB, mirroring
# test_scrape_lottery_spotrac.py.
# ---------------------------------------------------------------------------

def _row(**kw):
    base = dict(draft_year=2027, team="COL", pick_pos=1, odds_pct=17.95,
                odds_top6_pct=86.3, wins=42, losses=67, round_label="1",
                snapshot_date="2026-07-31", source="tankathon")
    base.update(kw)
    return base


def test_new_columns_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    storage.upsert_draft_lottery_odds([_row()])
    got = storage.load_draft_lottery_odds(2027, latest_only=True)
    assert len(got) == 1
    r = got[0]
    assert r["odds_pct"] == 17.95
    assert r["odds_top6_pct"] == 86.3
    assert r["wins"] == 42 and r["losses"] == 67


def test_historical_rows_read_back_as_null(tmp_path, monkeypatch):
    """Rows written before this change have no top6/record. NULL is the
    honest value - we never captured those numbers on those dates - and the
    frontend tolerates it."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    legacy = _row()
    for k in ("odds_top6_pct", "wins", "losses"):
        legacy.pop(k)
    storage.upsert_draft_lottery_odds([legacy])
    r = storage.load_draft_lottery_odds(2027, latest_only=True)[0]
    assert r["odds_top6_pct"] is None
    assert r["wins"] is None and r["losses"] is None


def test_an_older_scraper_build_cannot_blank_stored_values(tmp_path, monkeypatch):
    """The upsert COALESCEs the new columns. A re-run of a build that does
    not emit them (or a partial scrape) must not erase a good capture from
    the same day."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    storage.upsert_draft_lottery_odds([_row()])
    stale = _row()
    for k in ("odds_top6_pct", "wins", "losses"):
        stale.pop(k)
    storage.upsert_draft_lottery_odds([stale])
    r = storage.load_draft_lottery_odds(2027, latest_only=True)[0]
    assert r["odds_top6_pct"] == 86.3
    assert r["wins"] == 42 and r["losses"] == 67


def test_migration_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    storage.init_db()
    storage.init_db()
    with storage.connect() as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(draft_lottery_odds)")]
    for c in ("odds_pct", "odds_top6_pct", "wins", "losses"):
        assert cols.count(c) == 1, f"{c} appears {cols.count(c)} times: {cols}"


def test_migration_adds_columns_to_a_pre_existing_old_table(tmp_path, monkeypatch):
    """The ADD COLUMN block must run AFTER the NOT NULL table rebuild - that
    rebuild recreates the table from the OLD column list and would otherwise
    drop the new ones."""
    import sqlite3
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE draft_lottery_odds (
            draft_year    INTEGER NOT NULL,
            team          TEXT NOT NULL,
            pick_pos      INTEGER NOT NULL,
            odds_pct      REAL NOT NULL,
            round_label   TEXT NOT NULL DEFAULT '1',
            snapshot_date TEXT NOT NULL,
            source        TEXT NOT NULL,
            inserted_at   TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (draft_year, team, pick_pos, snapshot_date)
        );
        INSERT INTO draft_lottery_odds
          (draft_year, team, pick_pos, odds_pct, round_label, snapshot_date, source)
        VALUES (2027, 'COL', 1, 17.95, '1', '2026-06-01', 'tankathon');
    """)
    con.commit()
    con.close()

    monkeypatch.setattr(storage, "DB_PATH", db)
    storage.init_db()
    with storage.connect() as con2:
        cols = [r[1] for r in con2.execute("PRAGMA table_info(draft_lottery_odds)")]
    for c in ("odds_top6_pct", "wins", "losses"):
        assert c in cols, f"{c} missing after migration: {cols}"
    got = storage.load_draft_lottery_odds(2027, latest_only=False)
    assert len(got) == 1, "the pre-existing row must survive the migration"
    assert got[0]["odds_pct"] == 17.95
    assert got[0]["odds_top6_pct"] is None


def test_draft_export_emits_the_documented_field_names(tmp_path, monkeypatch):
    """The frontend contract. These exact keys ride into
    data/draft_timeseries.json under classes[].lottery_odds[]."""
    import draft_export
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "t.db")
    storage.init_db()
    storage.upsert_draft_lottery_odds([_row(), _row(team="LAA", pick_pos=2,
                                             odds_pct=14.36, odds_top6_pct=80.2,
                                             wins=46, losses=64)])
    lottery = {2027: storage.load_draft_lottery_odds(2027, latest_only=True)}
    cls = draft_export._build_class(2027, [], {}, {}, {}, {},
                                    lottery_by_year=lottery)
    odds = cls["lottery_odds"]
    assert len(odds) == 2
    assert [r["pick_pos"] for r in odds] == [1, 2], "must sort by pick_pos"
    assert set(odds[0]) == {"team", "odds_pct", "odds_top6_pct", "wins",
                            "losses", "pick_pos", "round_label", "snapshot_date"}
    assert odds[0]["odds_top6_pct"] == 86.3
    assert odds[0]["wins"] == 42 and odds[0]["losses"] == 67


if __name__ == "__main__":
    unittest.main()
