"""Tests for the farm_grade_history table (review-queue item 10, landed
2026-07-02): the composite farm LETTER grade snapshot that makes a forward
letter backtest possible (the farm_grades registry row is provisional
precisely because the letter was derived at export and never persisted).

Mirrors test_history_snapshots.py: fresh temp DB per test via monkeypatched
storage.DB_PATH, direct calls to the snapshot/loader functions.
"""
import sqlite3

import storage


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()


def _orgs():
    """Payload shaped like timeseries.json org_summary entries: the windowed
    letter/score maps the board displays plus the canonical fallbacks."""
    return [
        {"org": "TBR",
         "letter_by_window": {"6y": "A", "7y": "A+", "8y": "A+"},
         "farm_score_by_window": {"6y": 114.9, "7y": 115.2, "8y": 115.7},
         "grades": {"overall": "A"}, "farm_score": 113.0},
        {"org": "SEA",
         "letter_by_window": {"7y": "B+"},
         "farm_score_by_window": {"7y": 108.4},
         "grades": {"overall": "B"}, "farm_score": 107.1},
        # No windowed letter at all: falls back to the canonical overall.
        {"org": "WSN", "grades": {"overall": "C-"}, "farm_score": 94.2},
        # Unresolvable letters: skipped, never written.
        {"org": "BAD", "grades": {"overall": None}},
        {"org": "JNK", "grades": {"overall": "Z+"}},   # not a real letter
        {"letter_by_window": {"7y": "A"}},             # no org code
        "not-a-dict",
    ]


class TestSchema:
    def test_table_schema(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        with storage.connect() as con:
            info = con.execute("PRAGMA table_info(farm_grade_history)").fetchall()
        # PRAGMA row format: (cid, name, type, notnull, dflt_value, pk).
        cols = {r[1]: r for r in info}
        assert set(cols) == {"org", "snapshot_date", "letter", "farm_score",
                             "grade_window", "inserted_at"}
        assert cols["org"][2] == "TEXT" and cols["org"][3] == 1
        assert cols["snapshot_date"][2] == "TEXT" and cols["snapshot_date"][3] == 1
        assert cols["letter"][2] == "TEXT" and cols["letter"][3] == 1
        assert cols["farm_score"][2] == "REAL"
        assert cols["grade_window"][2] == "TEXT"
        # Composite primary key (org, snapshot_date) is what makes the
        # same-day upsert idempotent.
        pk = sorted((r[1] for r in info if r[5] > 0))
        assert pk == ["org", "snapshot_date"]

    def test_letter_set_matches_letter_grade_outputs(self):
        # The write gate must accept every letter _letter_grade can emit
        # (rank 1..n over a 30-org league) and nothing else.
        emitted = {storage._letter_grade(r, 30) for r in range(1, 31)}
        assert emitted <= storage._FARM_GRADE_LETTERS


class TestSnapshotFarmGrades:
    def test_capture_and_load(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        n = storage.snapshot_farm_grades(_orgs(), snapshot_date="2026-07-02")
        assert n == 3   # TBR, SEA, WSN; BAD/JNK/orgless/non-dict skipped
        rows = storage.load_farm_grade_history()
        by_org = {r["org"]: r for r in rows}
        assert set(by_org) == {"TBR", "SEA", "WSN"}
        # Windowed (7y principal) letter + score recorded, not the canonical.
        assert by_org["TBR"]["letter"] == "A+"
        assert by_org["TBR"]["farm_score"] == 115.2
        assert by_org["TBR"]["grade_window"] == storage.FARM_PRINCIPAL_WINDOW
        assert by_org["SEA"]["letter"] == "B+"
        # Fallback path: canonical overall letter + farm_score, tagged so.
        assert by_org["WSN"]["letter"] == "C-"
        assert by_org["WSN"]["farm_score"] == 94.2
        assert by_org["WSN"]["grade_window"] == "canonical"

    def test_no_op_when_grades_not_computable(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        assert storage.snapshot_farm_grades([], snapshot_date="2026-07-02") == 0
        assert storage.snapshot_farm_grades(
            [{"org": "TBR"}, {"org": "SEA", "grades": {}}],
            snapshot_date="2026-07-02") == 0
        assert storage.load_farm_grade_history() == []
        assert storage.farm_grade_history_dates() == []

    def test_idempotent_within_a_day(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        storage.snapshot_farm_grades(_orgs(), snapshot_date="2026-07-02")
        # Re-run the SAME day with a changed letter: overwrite, no duplicate.
        orgs = _orgs()
        orgs[0]["letter_by_window"]["7y"] = "A"
        orgs[0]["farm_score_by_window"]["7y"] = 112.0
        storage.snapshot_farm_grades(orgs, snapshot_date="2026-07-02")
        rows = storage.load_farm_grade_history(org="TBR")
        assert len(rows) == 1                      # one row per org per day
        assert rows[0]["letter"] == "A"
        assert rows[0]["farm_score"] == 112.0
        assert storage.farm_grade_history_dates() == ["2026-07-02"]
        # And globally: still exactly one row per (org, date).
        with storage.connect() as con:
            dup = con.execute(
                "SELECT org, snapshot_date, COUNT(*) c FROM farm_grade_history "
                "GROUP BY org, snapshot_date HAVING c > 1").fetchall()
        assert dup == []

    def test_append_only_across_days(self, tmp_path, monkeypatch):
        _fresh_db(tmp_path, monkeypatch)
        storage.snapshot_farm_grades(_orgs(), snapshot_date="2026-07-02")
        # Next month TBR slips to A: the new date APPENDS, the old row is
        # untouched (history is never rewritten or deleted).
        orgs = _orgs()
        orgs[0]["letter_by_window"]["7y"] = "A"
        storage.snapshot_farm_grades(orgs, snapshot_date="2026-08-01")
        hist = storage.load_farm_grade_history(org="TBR")
        assert [r["snapshot_date"] for r in hist] == ["2026-07-02", "2026-08-01"]
        assert [r["letter"] for r in hist] == ["A+", "A"]   # oldest-first series
        assert storage.farm_grade_history_dates() == ["2026-07-02", "2026-08-01"]

    def test_self_heals_missing_table(self, tmp_path, monkeypatch):
        # A pre-existing DB created before this table landed: the snapshot
        # function applies the schema itself instead of raising.
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "old.db")
        sqlite3.connect(tmp_path / "old.db").close()   # empty DB, no tables
        n = storage.snapshot_farm_grades(_orgs(), snapshot_date="2026-07-02")
        assert n == 3
        assert len(storage.load_farm_grade_history()) == 3

    def test_loader_survives_missing_table(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "DB_PATH", tmp_path / "empty.db")
        sqlite3.connect(tmp_path / "empty.db").close()
        assert storage.load_farm_grade_history() == []
        assert storage.farm_grade_history_dates() == []
