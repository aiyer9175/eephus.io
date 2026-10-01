"""Source coverage beside metric_snapshots (owner answer B4SP-2, 2026-10-01).

From the first run after this landed, every metric_snapshots row records the
number of outlets grading the player (source_n, source_keys) and his best
league-wide rank (best_rank, best_rank_source, best_rank_date), so a later
Spotlights v3 can score the new-source and top-100 legs point in time. The
schema change is forward only: rows written before it keep NULL.

Schema tests: the columns exist on a fresh DB, the migration adds them to a DB
built on the old DDL, runs twice without error and back-fills nothing.
Structure tests: the writer records, keeps and overwrites coverage as
documented, and the definitions in consensus.point_source_coverage hold on a
synthetic corpus. Wiring test: the nightly snapshot passes the coverage in.
"""
import sqlite3
from pathlib import Path

import consensus
import storage
from scrapers import Snapshot

COV_COLS = ["source_n", "source_keys", "best_rank", "best_rank_source", "best_rank_date"]

# The metric_snapshots DDL as it stood before 2026-10-01 (no coverage columns).
_OLD_DDL = """
CREATE TABLE metric_snapshots (
    player_key    TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    overall_rank  INTEGER,
    consensus_fv  REAL,
    fv_plus       INTEGER NOT NULL DEFAULT 0,
    fv_tier       TEXT,
    org           TEXT,
    position      TEXT,
    status        TEXT,
    is_pitcher    INTEGER NOT NULL DEFAULT 0,
    age           REAL,
    payload_json  TEXT NOT NULL,
    inserted_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (player_key, snapshot_date)
);
"""


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()


def _columns(db_path) -> dict:
    con = sqlite3.connect(db_path)
    try:
        return {r[1]: r for r in con.execute("PRAGMA table_info(metric_snapshots)")}
    finally:
        con.close()


def _rows(db_path, date) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        return {r["player_key"]: dict(r) for r in con.execute(
            "SELECT * FROM metric_snapshots WHERE snapshot_date = ?", (date,))}
    finally:
        con.close()


def _players():
    return [
        {"player_key": "a_one", "overall_rank": 1, "fv_close": 60.0, "org": "MIL",
         "position": "SS", "status": "active", "age": 19.1},
        {"player_key": "b_two", "overall_rank": 2, "fv_close": 50.0, "org": "SEA",
         "position": "SP", "status": "active", "age": 21.4},
    ]


_COV = {
    "a_one": {"source_n": 3, "source_keys": "baseballamerica,fangraphs,mlb_pipeline",
              "best_rank": 12, "best_rank_source": "mlb_pipeline",
              "best_rank_date": "2026-09-30"},
    # b_two is left out on purpose: a board key the build did not produce.
}


class TestSchema:
    def test_fresh_db_has_nullable_coverage_columns(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        cols = _columns(tmp_path / "test.db")
        for c in COV_COLS:
            assert c in cols, c
            assert cols[c][3] == 0, f"{c} must be nullable"
            assert cols[c][4] is None, f"{c} must carry no default (NULL = not recorded)"
        assert [c for c, _ in storage.METRIC_SNAPSHOT_COVERAGE_COLUMNS] == COV_COLS

    def test_migration_adds_columns_idempotently_and_never_backfills(self, tmp_path, monkeypatch):
        db = tmp_path / "old.db"
        con = sqlite3.connect(db)
        con.executescript(_OLD_DDL)
        con.execute("INSERT INTO metric_snapshots (player_key, snapshot_date, overall_rank, "
                    "consensus_fv, payload_json) VALUES ('old_row', '2026-09-30', 5, 55.0, '{}')")
        con.commit()
        con.close()
        assert not set(COV_COLS) & set(_columns(db))

        monkeypatch.setattr(storage, "DB_PATH", db)
        storage.init_db()
        storage.init_db()          # second run: every ALTER is a no-op
        assert set(COV_COLS) <= set(_columns(db))
        old = _rows(db, "2026-09-30")["old_row"]
        assert all(old[c] is None for c in COV_COLS), "forward only: no back-fill"
        assert old["consensus_fv"] == 55.0
        assert storage.metric_snapshot_coverage_start() is None


class TestWriter:
    def test_records_coverage_and_null_for_a_missing_key(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        n = storage.snapshot_board_metrics(_players(), snapshot_date="2026-10-02",
                                           source_coverage=_COV)
        assert n == 2
        rows = _rows(tmp_path / "test.db", "2026-10-02")
        assert {c: rows["a_one"][c] for c in COV_COLS} == _COV["a_one"]
        assert all(rows["b_two"][c] is None for c in COV_COLS), \
            "a key missing from the build records NULL, never a made-up 0"
        assert storage.metric_snapshot_coverage_start() == "2026-10-02"

    def test_without_coverage_new_rows_stay_null(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        storage.snapshot_board_metrics(_players(), snapshot_date="2026-10-02")
        rows = _rows(tmp_path / "test.db", "2026-10-02")
        assert all(r[c] is None for r in rows.values() for c in COV_COLS)
        assert storage.metric_snapshot_coverage_start() is None

    def test_same_date_rerun_keeps_or_overwrites_as_documented(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        db = tmp_path / "test.db"
        storage.snapshot_board_metrics(_players(), snapshot_date="2026-10-02",
                                       source_coverage=_COV)
        # A re-run with no coverage (e.g. the rank re-bake path) keeps it.
        players = _players()
        players[0]["fv_close"] = 61.0
        storage.snapshot_board_metrics(players, snapshot_date="2026-10-02")
        row = _rows(db, "2026-10-02")["a_one"]
        assert row["consensus_fv"] == 61.0
        assert row["source_n"] == 3 and row["best_rank"] == 12
        # A re-run WITH coverage overwrites it, including back to no rank.
        new = {"a_one": {"source_n": 4, "source_keys": "a,b,c,d", "best_rank": None,
                         "best_rank_source": None, "best_rank_date": None}}
        storage.snapshot_board_metrics(players, snapshot_date="2026-10-02",
                                       source_coverage=new)
        row = _rows(db, "2026-10-02")["a_one"]
        assert row["source_n"] == 4 and row["source_keys"] == "a,b,c,d"
        assert row["best_rank"] is None and row["best_rank_source"] is None


def _s(source, label, date, key, org, rank=None, fv=None):
    return Snapshot(source=source, snapshot_date=date, interval_label=label,
                    player_key=key, player_name=key.replace("_", " ").title(),
                    position="SS", org=org, rank=rank, fv=fv, status="active")


class TestDefinitions:
    """consensus.point_source_coverage on a synthetic corpus."""

    def _corpus(self):
        P = "pat_prospect"
        return [
            # League-wide Top 100 (rows name two orgs): P is #40.
            _s("baseballamerica", "Baseball America 2026 Top 100", "2026-06-01", P, "MIL", rank=40, fv=55.0),
            _s("baseballamerica", "Baseball America 2026 Top 100", "2026-06-01", "q_other", "SEA", rank=41, fv=55.0),
            # The same outlet's LATER org list: rank 2 is an org position and
            # must not hide the Top 100 rank; its FV is BA's current vote.
            _s("baseballamerica", "Baseball America 2026 Midseason Brewers Top 30", "2026-08-01", P, "MIL", rank=2, fv=50.0),
            # An org list the label rule cannot see: every ranked row names MIL.
            _s("fangraphs", "FanGraphs 2026 Brewers Top 50", "2026-07-01", P, "MIL", rank=1, fv=50.0),
            _s("fangraphs", "FanGraphs 2026 Brewers Top 50", "2026-07-01", "r_other", "MIL", rank=2, fv=45.0),
            # Alias folds into mlb_pipeline; no rank.
            _s("mlb_pipeline_international", "MLB Pipeline 2026 International", "2026-07-15", P, "MIL", fv=45.0),
            # A rank <= 0 on a board with no org at all is not a rank.
            _s("espn", "ESPN 2026 In-Season", "2026-07-20", P, None, rank=0),
            _s("espn", "ESPN 2026 In-Season", "2026-07-20", "s_other", None, rank=3),
            # Constant placeholder: never a grading outlet.
            _s("auto_detect", "auto", "2026-07-25", P, "MIL", fv=35.0),
        ]

    def _coverage(self, snaps):
        ts = consensus.build_timeseries(snaps)
        return consensus.source_coverage_by_player(ts)

    def test_counts_and_best_rank(self):
        cov = self._coverage(self._corpus())["pat_prospect"]
        assert cov["source_n"] == 3
        assert cov["source_keys"] == "baseballamerica,fangraphs,mlb_pipeline"
        assert (cov["best_rank"], cov["best_rank_source"], cov["best_rank_date"]) == \
            (40, "baseballamerica", "2026-06-01")

    def test_newer_league_wide_list_replaces_the_outlet_rank(self):
        snaps = self._corpus() + [
            _s("baseballamerica", "Baseball America 2026 Midseason Top 100", "2026-08-15",
               "pat_prospect", "MIL", rank=77, fv=50.0),
            _s("baseballamerica", "Baseball America 2026 Midseason Top 100", "2026-08-15",
               "q_other", "SEA", rank=78, fv=50.0),
        ]
        cov = self._coverage(snaps)["pat_prospect"]
        assert (cov["best_rank"], cov["best_rank_date"]) == (77, "2026-08-15")

    def test_no_league_wide_rank_is_none_and_anchor_only_is_zero(self):
        snaps = [_s("auto_detect", "auto", "2026-07-25", "solo", "MIL", fv=35.0),
                 _s("mlb_pipeline", "MLB Pipeline 2026 Brewers Top 30", "2026-07-26",
                    "solo", "MIL", rank=9)]
        cov = self._coverage(snaps)["solo"]
        assert cov == {"source_n": 0, "source_keys": "", "best_rank": None,
                       "best_rank_source": None, "best_rank_date": None}

    def test_point_without_record_is_none(self):
        assert consensus.point_source_coverage(None) is None


def test_nightly_snapshot_passes_the_coverage():
    """The same nightly step that writes the snapshot records the coverage."""
    src = (Path(__file__).parent / "run_monthly.py").read_text(encoding="utf-8")
    assert "_source_cov = _src_cov_by_player(timeseries)" in src
    assert "source_coverage=_source_cov" in src
    # computed before the build is freed, so it reads the exported build
    assert src.index("_source_cov = _src_cov_by_player(timeseries)") < \
        src.index("all_snaps = timeseries = career_cache")
