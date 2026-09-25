# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EV-00 pins for tools/efv_progress_backfill.py (docs/efv-v2/PROGRAM.md s5.4).

A committed version without a head-to-head verdict yields no row, and every
backfilled interval is null: a CI cannot be recomputed from a committed number
and the ledger layer computes nothing. Per-source values are taken from a
scoreboard version only when its `vs` block sits on the verdict's frame.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_progress as P                      # noqa: E402
import efv_progress_backfill as B             # noqa: E402

VERDICT = {"basis": "pooled_efv_common_vintage_matched",
           "basis_note": "base year equals the eFV decision year",
           "n": 800, "xfv_spearman": 0.4, "consensus_spearman": 0.41,
           "delta": -0.01, "mde95": 0.0303, "resolvable": False,
           "verdict": "not resolvable at this power"}


def _vs(n):
    cell = lambda e, c: {"n": n, "efv": e, "consensus": c, "margin": round(e - c, 4)}  # noqa: E731
    return {"prospx_consensus": {"spearman": cell(0.4, 0.41), "auc_contributor": cell(0.75, 0.74)},
            "fangraphs": {"spearman": cell(0.4, 0.37), "auc_contributor": cell(0.75, 0.72)},
            "mlb_pipeline": {"spearman": cell(0.4, 0.405), "auc_contributor": cell(0.75, 0.745)}}


def test_a_version_without_a_verdict_yields_no_row():
    assert B.row_from_version({"accuracy": {}}, B.SB_PATH, "a" * 40, "2026-08-01") is None
    assert B.row_from_version({"head_to_head": {}}, B.SC_PATH, "b" * 40, "2026-08-01") is None
    assert B.row_from_version({}, B.SC_PATH, "c" * 40, "2026-08-01") is None


def test_backfilled_ci95_is_null_and_rater_frame_is_checked():
    on = {"generated_at": "2026-09-01",
          "source_backtest_freshness": {"artifact_generated_at": "2026-09-01T10:00:00Z"},
          "head_to_head": {"verdict_vs_consensus": VERDICT, "vs_frame": "vintage_matched",
                           "vs": _vs(800)}}
    r = B.row_from_version(on, B.SC_PATH, "d" * 40, "2026-09-01")
    assert r["trigger"] == "backfill" and r["frame"] == "vm" and r["role"] == "headline"
    for legs in r["deltas"].values():
        for leg in legs.values():
            assert leg["ci95"] is None
    assert r["raters"]["fangraphs"]["spearman"] == 0.37
    assert r["deltas"]["vs_prospx_consensus"]["spearman"]["delta"] == VERDICT["delta"]
    assert r["content_hash"] == P.content_hash(r)
    assert r["run_id"].startswith("2026-09-01T10:00:00Z|vm|")
    # An older version scored the sources on a different frame: no source raters.
    off = {"generated_at": "2026-08-16",
           "head_to_head": {"verdict_vs_consensus": VERDICT, "vs": _vs(3234)}}
    r2 = B.row_from_version(off, B.SC_PATH, "e" * 40, "2026-08-16")
    assert set(r2["raters"]) == {"efv", "prospx_consensus"}
    assert set(r2["deltas"]) == {"vs_prospx_consensus"}


def test_an_old_headline_basis_backfills_as_a_tilted_row():
    old = dict(VERDICT, basis="pooled_efv_common (identical rows)", n=3210)
    old.pop("basis_note")
    r = B.row_from_version({"head_to_head": {"verdict_vs_consensus": old}},
                           B.SC_PATH, "f" * 40, "2026-08-07")
    assert r["frame"] == "all_vintages" and r["role"] == "tilted" and r["tilted"] is True
    assert r["note"] and "—" not in r["note"]


def test_the_tool_runs_once(tmp_path, monkeypatch):
    out, led = tmp_path / "efv_progress.json", tmp_path / "ledger.jsonl"
    out.write_text(json.dumps({"schema": 1, "rows": [{"run_id": "x", "trigger": "backfill",
                                                        "frame": "vm", "date": "2026-08-01"}]}),
                   encoding="utf-8")
    monkeypatch.setattr(P, "OUT_PATH", out)
    monkeypatch.setattr(P, "LEDGER_PATH", led)
    assert B.main([]) == 1
    assert not led.exists()


def test_served_backfill_receipt():
    served = ROOT / "data" / "efv_progress.json"
    if not served.exists():
        pytest.skip("data/efv_progress.json not built")
    doc = json.loads(served.read_text(encoding="utf-8"))
    rec = doc.get("backfill")
    assert rec, "the backfill ran once and its receipt is committed with the ledger"
    assert set(rec["paths"]) == {B.SB_PATH, B.SC_PATH}
    n_back = sum(1 for r in doc["rows"] if r["trigger"] == "backfill")
    assert n_back <= rec["rows_emitted"]
