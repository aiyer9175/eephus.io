"""Pins for the trade-value forward backtest (instrument-maturation eval).

Gate doc: docs/trade-2026-08-19/TRADE_FORWARD_GATE.md
Tool:     tools/trade_value_forward_backtest.py
Artifact: data/trade_machine_eval.json (forward_backtest block)
"""

import json
import os
import sqlite3
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

ARTIFACT = os.path.join(_HERE, "data", "trade_machine_eval.json")


def _load_artifact():
    with open(ARTIFACT, encoding="utf-8") as f:
        return json.load(f)


def test_artifact_has_generated_at():
    d = _load_artifact()
    assert d.get("generated_at"), "trade_machine_eval.json generated_at is empty"
    # ISO date, 2026 or later (the artifact was undated before 2026-08-19)
    assert d["generated_at"] >= "2026-08-19"


def test_forward_backtest_block_shape():
    d = _load_artifact()
    fb = d.get("forward_backtest")
    assert fb, "forward_backtest block missing"
    assert fb.get("no_win_claims") is True
    assert fb.get("kind") == "instrument_maturation"

    s1 = fb["s1_value_stability"]
    assert isinstance(s1["spearman"], float)
    assert s1["n_pairs"] > 0
    assert s1["n_players"] > 0
    assert s1["n_origin_dates"] >= 1
    lo, hi = s1["ci95_player_clustered_bootstrap"]
    assert lo <= s1["spearman"] <= hi
    assert s1["bootstrap_B"] == 1000

    s2 = fb["s2_movement_signal"]
    assert isinstance(s2["spearman_value_vs_delta"], float)
    assert s2["n_pairs"] == s1["n_pairs"]
    assert "control" in s2 and s2["control"]["B"] == 1000
    assert "interpretation" in s2 and s2["interpretation"]

    s3 = fb["s3_coverage"]
    assert s3["n_pairs"] == s1["n_pairs"]
    assert s3["snapshot_dates_total"] >= 2
    # drops must reconcile: candidates = pairs + all dropped
    dropped = (s3["dropped_player_absent_at_t2"]
               + s3["dropped_null_value_at_t"]
               + s3["dropped_null_value_at_t2"])
    assert s3["candidate_rows_at_partnered_dates"] == s3["n_pairs"] + dropped


def test_parent_artifact_keys_preserved():
    d = _load_artifact()
    for key in ("model", "conventions", "slice_a", "slice_a_prime_by_source",
                "ship", "honest_note"):
        assert key in d, f"pre-existing key {key} lost by read-modify-write"
    assert d["ship"] is False


def _make_db(tmp_path, dates):
    db = tmp_path / "tiny.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE trade_value_history ("
        "player_key TEXT NOT NULL, snapshot_date TEXT NOT NULL, "
        "trade_value_mm REAL, surplus_source TEXT, trade_value_tier TEXT, "
        "trade_value_grade TEXT, xfv_grade REAL, status TEXT, age REAL, "
        "position TEXT, org TEXT, "
        "inserted_at TEXT NOT NULL DEFAULT (datetime('now')), "
        "PRIMARY KEY (player_key, snapshot_date))"
    )
    for d in dates:
        for pk, v in (("a", 1.0), ("b", 2.0)):
            con.execute(
                "INSERT INTO trade_value_history "
                "(player_key, snapshot_date, trade_value_mm) VALUES (?,?,?)",
                (pk, d, v),
            )
    con.commit()
    con.close()
    return db


def test_tool_refuses_fewer_than_two_snapshot_dates(tmp_path):
    from tools import trade_value_forward_backtest as fbt

    db = _make_db(tmp_path, ["2026-06-25"])
    with pytest.raises(fbt.TooFewSnapshots):
        fbt.run_lab(db)
    # and via the CLI path: exit code 2, nothing written
    rc = fbt.main(["--dry-run", "--db", str(db)])
    assert rc == 2


def test_tool_refuses_empty_history(tmp_path):
    from tools import trade_value_forward_backtest as fbt

    db = _make_db(tmp_path, [])
    with pytest.raises(fbt.TooFewSnapshots):
        fbt.run_lab(db)
