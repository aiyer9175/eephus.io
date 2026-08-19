"""Tests for the two vintage score archives (2026-08-19).

1. grpo_score_history: the GRPO breakout-score archive in prospects.db.
   grpo_scores.json is overwritten by every retrain, so this table is the
   only thing that makes a forward badge eval possible (gate registration:
   docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md). Append-only, INSERT OR IGNORE
   on (snapshot_date, player_key): a same-day re-run is a no-op.

2. farm_grade_history: RECONCILED, not duplicated. Served farm letters were
   already accruing via storage.snapshot_farm_grades (review-queue item 10,
   landed 2026-07-02; 30 orgs per date, daily cadence, covered in depth by
   test_farm_grade_history.py). The pin here only guards against a second
   parallel farm archive ever being added.

Mirrors test_farm_grade_history.py: fresh temp DB per test, direct calls to
the snapshot/loader functions. Every test runs against tmp_path paths so no
row ever lands in the real prospects.db.
"""
import json
import sqlite3

import grpo_prospect
import storage


def _write_scores(tmp_path, all_scores, generated_at="2026-08-19"):
    """Write a minimal grpo_scores.json-shaped artifact into tmp_path."""
    p = tmp_path / "grpo_scores.json"
    p.write_text(json.dumps({
        "generated_at": generated_at,
        "scored_count": len(all_scores),
        "all_scores":   all_scores,
    }), encoding="utf-8")
    return p


def _scores():
    """Payload shaped like grpo_scores.json all_scores entries."""
    return {
        "alexander_frias": {"player_key": "alexander_frias",
                            "breakout_score": 0.812, "fv_adj": 9.4},
        "some_catcher":    {"player_key": "some_catcher",
                            "breakout_score": 0.5},
        "zero_score_guy":  {"player_key": "zero_score_guy",
                            "breakout_score": 0.0},   # 0.0 is a real score, kept
        # Unresolvable rows: skipped, never written.
        "no_score_guy":    {"player_key": "no_score_guy"},
        "nan_guy":         {"player_key": "nan_guy", "breakout_score": float("nan")},
        "text_guy":        {"player_key": "text_guy", "breakout_score": "high"},
        "not_a_dict":      "bogus",
    }


class TestGrpoScoreHistory:
    def test_table_created_and_rows_written(self, tmp_path):
        db = tmp_path / "test.db"
        sp = _write_scores(tmp_path, _scores())
        n = grpo_prospect.snapshot_grpo_scores(
            scores_path=sp, db_path=db, snapshot_date="2026-08-19")
        assert n == 3   # frias, catcher, zero-score; the 4 bad rows skipped
        con = sqlite3.connect(db)
        try:
            info = con.execute("PRAGMA table_info(grpo_score_history)").fetchall()
            cols = {r[1]: r for r in info}
            assert set(cols) == {"snapshot_date", "player_key", "score",
                                 "inserted_at"}
            assert cols["snapshot_date"][2] == "TEXT" and cols["snapshot_date"][3] == 1
            assert cols["player_key"][2] == "TEXT" and cols["player_key"][3] == 1
            assert cols["score"][2] == "REAL" and cols["score"][3] == 1
            # Composite primary key is what makes INSERT OR IGNORE idempotent.
            pk = sorted(r[1] for r in info if r[5] > 0)
            assert pk == ["player_key", "snapshot_date"]
            rows = con.execute(
                "SELECT player_key, score FROM grpo_score_history "
                "WHERE snapshot_date='2026-08-19'").fetchall()
        finally:
            con.close()
        by_key = dict(rows)
        assert by_key == {"alexander_frias": 0.812, "some_catcher": 0.5,
                          "zero_score_guy": 0.0}

    def test_same_day_rerun_is_a_no_op(self, tmp_path):
        db = tmp_path / "test.db"
        sp = _write_scores(tmp_path, _scores())
        grpo_prospect.snapshot_grpo_scores(
            scores_path=sp, db_path=db, snapshot_date="2026-08-19")
        # Re-run the SAME day with a CHANGED score: OR IGNORE means the first
        # write of the day wins (append-only vintage, never an upsert).
        changed = _scores()
        changed["alexander_frias"]["breakout_score"] = 0.4
        sp2 = _write_scores(tmp_path, changed)
        n2 = grpo_prospect.snapshot_grpo_scores(
            scores_path=sp2, db_path=db, snapshot_date="2026-08-19")
        assert n2 == 0
        hist = grpo_prospect.load_grpo_score_history(
            player_key="alexander_frias", db_path=db)
        assert len(hist) == 1
        assert hist[0]["score"] == 0.812   # first write preserved
        con = sqlite3.connect(db)
        try:
            dup = con.execute(
                "SELECT snapshot_date, player_key, COUNT(*) c FROM "
                "grpo_score_history GROUP BY snapshot_date, player_key "
                "HAVING c > 1").fetchall()
        finally:
            con.close()
        assert dup == []

    def test_second_date_appends(self, tmp_path):
        db = tmp_path / "test.db"
        sp = _write_scores(tmp_path, _scores())
        grpo_prospect.snapshot_grpo_scores(
            scores_path=sp, db_path=db, snapshot_date="2026-08-19")
        changed = _scores()
        changed["alexander_frias"]["breakout_score"] = 0.75
        sp2 = _write_scores(tmp_path, changed, generated_at="2026-09-19")
        n2 = grpo_prospect.snapshot_grpo_scores(
            scores_path=sp2, db_path=db, snapshot_date="2026-09-19")
        assert n2 == 3
        hist = grpo_prospect.load_grpo_score_history(
            player_key="alexander_frias", db_path=db)
        assert [r["snapshot_date"] for r in hist] == ["2026-08-19", "2026-09-19"]
        assert [r["score"] for r in hist] == [0.812, 0.75]   # oldest-first series

    def test_missing_or_empty_artifact_is_a_no_op(self, tmp_path):
        db = tmp_path / "test.db"
        assert grpo_prospect.snapshot_grpo_scores(
            scores_path=tmp_path / "absent.json", db_path=db,
            snapshot_date="2026-08-19") == 0
        sp = _write_scores(tmp_path, {})
        assert grpo_prospect.snapshot_grpo_scores(
            scores_path=sp, db_path=db, snapshot_date="2026-08-19") == 0

    def test_self_heals_pre_existing_db(self, tmp_path):
        # A DB created before this table landed: the snapshot function
        # applies its own schema instead of raising.
        db = tmp_path / "old.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE unrelated (x INTEGER)")
        con.commit()
        con.close()
        sp = _write_scores(tmp_path, _scores())
        n = grpo_prospect.snapshot_grpo_scores(
            scores_path=sp, db_path=db, snapshot_date="2026-08-19")
        assert n == 3

    def test_loader_survives_missing_table_and_db(self, tmp_path):
        assert grpo_prospect.load_grpo_score_history(
            db_path=tmp_path / "nonexistent.db") == []
        db = tmp_path / "empty.db"
        sqlite3.connect(db).close()   # empty DB, no tables
        assert grpo_prospect.load_grpo_score_history(db_path=db) == []


class TestFarmLetterArchiveReconciliation:
    """The farm letter archive PRE-EXISTS (storage.farm_grade_history,
    2026-07-02). These pins document the reconciliation so a later session
    does not add a duplicate archive next to it."""

    def test_farm_letter_archive_lives_in_storage(self):
        assert callable(getattr(storage, "snapshot_farm_grades", None))
        assert callable(getattr(storage, "load_farm_grade_history", None))
        assert "farm_grade_history" in storage.SCHEMA

    def test_grpo_module_owns_no_farm_archive(self):
        # grpo_prospect archives GRPO scores only; the org-letter archive is
        # storage's. A farm table appearing here means someone duplicated it.
        assert "farm_grade_history" not in grpo_prospect._GRPO_HISTORY_SCHEMA
        assert not hasattr(grpo_prospect, "snapshot_farm_grades")
