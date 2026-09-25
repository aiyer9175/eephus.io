# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-01 (docs/efv-v2/DRIVER_SYSTEM_V2.md, bug B1): the head-to-head scores eFV's
RAW out-of-sample score.

THE DEFECT. source_backtest overwrote the raw eFV score on every common row with
a rank remap onto the common-set consensus-FV values rounded to 0.1, and
_vm2_frame_rows did the same, on the stated ground that a monotone remap leaves
Spearman and AUC unchanged. A remap onto a grid with fewer distinct values than
rows is not one to one: 806 distinct raw scores on the vintage-matched frame
collapsed onto about 100 values, and the ties cost eFV 0.0015 to 0.0018 of
Spearman on every head-to-head cell.

These tests pin the fix: the scored column equals the raw score and the distinct
count is preserved, in the helpers and in the served artifact. The move is a
HARNESS CORRECTION on the progress ledger, never model progress.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

import efv_progress as P
import source_backtest as sb

ROOT = Path(__file__).parent
ART = ROOT / "data" / "source_backtest.json"
LEDGER = ROOT / "data" / "efv_progress.json"
GLOSSARY_JS = ROOT / "assets" / "glossary.js"


def _common(n=60, grid=5):
    """n rows over two base years; the consensus sits on a grid of `grid`
    values, so any remap onto it must tie."""
    years = [2018, 2019]
    by_year = {y: [] for y in years}
    raw = {}
    for i in range(n):
        y = years[i % 2]
        k = f"p{i}"
        by_year[y].append({"key": k, "year": y,
                           "grades": {sb.CONSENSUS_KEY: 40.0 + 5.0 * (i % grid)},
                           "outcome": {"war": float(i % 7), "debut_year": y,
                                       "contributor": i % 3 == 0}})
        raw[k] = 0.001 * ((i * 37) % 101) - 0.02
    return by_year, years, raw


def test_the_scored_column_is_the_raw_score():
    by_year, years, raw = _common()
    rows, raw_list, n = sb._attach_raw_efv(by_year, years, raw)
    assert n == len(rows) == len(raw)
    assert [c["grades"]["xfv"] for c in rows] == [raw[c["key"]] for c in rows]
    assert raw_list == [raw[c["key"]] for c in rows]


def test_the_distinct_count_is_preserved():
    by_year, years, raw = _common(n=60, grid=5)
    rows, raw_list, _ = sb._attach_raw_efv(by_year, years, raw)
    rec = sb._scored_column_receipt(rows, raw_list)
    assert rec["scored_equals_raw"] is True
    assert rec["n_distinct_scored"] == rec["n_distinct_raw"] == len(set(raw.values()))
    # the defect, reproduced: the old remap onto a five-value grid keeps five
    cons = sorted(c["grades"][sb.CONSENSUS_KEY] for c in rows)
    assert len(set(cons)) == 5 < rec["n_distinct_raw"]


def test_rows_without_an_efv_score_are_left_alone():
    by_year, years, raw = _common()
    raw.pop("p0")
    rows, _, n = sb._attach_raw_efv(by_year, years, raw)
    assert n == len(raw) and all(c["key"] != "p0" for c in rows)
    assert "xfv" not in by_year[2018][0]["grades"]
    assert sb._attach_raw_efv(by_year, years, {}) == ([], [], 0)


def test_vm2_scores_the_raw_pinned_score():
    by_year, years, raw = _common()
    rows, raw_list, _ = sb._attach_raw_efv(by_year, years, raw)
    pinned = {c["key"]: raw[c["key"]] + 0.5 for c in rows[::2]}
    receipts = {k: {"window_year": next(c["year"] for c in rows if c["key"] == k),
                    "asof_date": f"{next(c['year'] for c in rows if c['key'] == k)}-03-01",
                    "matrix_asof_date": "x", "consensus_fv_raw": 45.0,
                    "matrix_consensus_fv_raw": 45.0}
                for k in pinned}
    out, rec = sb._vm2_frame_rows(rows, raw_list, pinned, receipts,
                                  lambda c: True)
    assert out and len(out) == len(pinned)
    assert all(r["grades"]["xfv"] == pinned[r["key"]] for r in out)
    assert len({r["grades"]["xfv"] for r in out}) == len(set(pinned.values()))
    # the vm1 rows are not modified
    assert [c["grades"]["xfv"] for c in rows] == raw_list


def test_the_served_artifact_scored_the_raw_column():
    if not ART.exists():
        pytest.skip("data/source_backtest.json not built")
    acc = json.loads(ART.read_text(encoding="utf-8"))["accuracy"]
    col = acc.get("efv_scored_column")
    assert col, "source_backtest.json predates DS-01: regenerate it"
    for frame in ("common_efv", "vintage_matched", "vintage_matched_vm2"):
        r = col[frame]
        assert r["scored_equals_raw"] is True, frame
        assert r["n_distinct_scored"] == r["n_distinct_raw"], frame
        assert r["n_rows"] > 0
    assert col["vintage_matched"]["n_rows"] == acc["common_n_efv_vintage_matched"]
    assert (col["vintage_matched_vm2"]["n_rows"]
            == acc["pooled_efv_common_vintage_matched_vm2"]["xfv"]["n"])
    assert "no remap" in col["basis"]


# --------------------------------------------------------------------------
# the ledger records it as a correction, never as progress

def test_harness_correction_is_a_ledger_trigger(tmp_path):
    if not ART.exists():
        pytest.skip("data/source_backtest.json not built")
    d = tmp_path / "data"
    d.mkdir()
    shutil.copy2(ART, d / P.SB_NAME)
    note = "Harness correction DS-01: scoring fix, not model progress."
    mv = {"fingerprint": "fp|label=ewar_v2@t", "commit": "c", "label": "ewar_v2@t",
          "resolved_through": 2025}
    res = P.update(d, "harness_correction", out_path=d / "efv_progress.json",
                   ledger_path=d / "ledger.jsonl", model_version=mv, note=note,
                   now=datetime(2026, 9, 25, tzinfo=timezone.utc))
    assert res["status"] == "ok" and res["appended"]
    doc = json.loads((d / "efv_progress.json").read_text(encoding="utf-8"))
    assert doc["correction_triggers"] == ["harness_correction", "data_correction"]
    for r in doc["rows"]:
        assert r["trigger"] == "harness_correction"
        assert r["note"].startswith(note)
    assert "harness_correction" in P.CORRECTION_TRIGGERS


def test_served_correction_rows_keep_the_model_they_rescored():
    """A correction row measures the same model under a fixed harness: its
    model fingerprint equals the previous row of its frame, so the page can
    never read it as a model change."""
    if not LEDGER.exists():
        pytest.skip("data/efv_progress.json not built")
    rows = json.loads(LEDGER.read_text(encoding="utf-8"))["rows"]
    corr = [i for i, r in enumerate(rows) if r.get("trigger") in P.CORRECTION_TRIGGERS]
    for i in corr:
        r = rows[i]
        prev = [p for p in rows[:i] if p["frame"] == r["frame"]
                and p.get("model_id") == r.get("model_id")
                and (p.get("model_version") or {}).get("fingerprint")]
        if not prev:
            continue
        assert (prev[-1]["model_version"]["fingerprint"]
                == r["model_version"]["fingerprint"]), r["run_id"]
        assert "not model progress" in r["note"]


def test_the_page_marks_correction_rows_apart():
    js = GLOSSARY_JS.read_text(encoding="utf-8")
    assert "function _progIsCorrection(" in js
    assert "function _progCorrectionName(" in js
    assert ", not model progress</span>" in js
    # the chart draws a correction with its own mark before any other branch
    chart = js[js.index("function _methProgressChart("):js.index("function _progRaterCell(")]
    assert chart.index("_progIsCorrection(prog, r)") < chart.index('r.trigger === "look"')
