# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX payload and render-cost pins (DISPLAY_prospx, quality audit 2026-10-02).

QPRP08: every PROSPX view fetched data/eta_eval.json at boot (943,657 bytes raw) to
read km_survival_by_level (about 0.5 KB). eta_backtest now also writes the slim
curves file and the page reads that; the eval artifact stays the receipt.

QPRP05: each pitch row of a pitcher card rebuilt the same-level cohort by scanning
every player and debut (24 scans per card render). The peer values are built once
per synchronous render pass; a 571-row in-page check against the old scan printed
identical HTML for every row.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
PAGE = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")


def test_qprp08_page_reads_the_slim_curves_file():
    assert 'fetch("/data/eta_curves.json"' in PAGE
    assert 'fetch("/data/eta_eval.json"' not in PAGE


def test_qprp08_curves_file_is_the_eval_block_verbatim():
    ev = ROOT / "data" / "eta_eval.json"
    cv = ROOT / "data" / "eta_curves.json"
    if not (ev.exists() and cv.exists()):
        pytest.skip("eta artifacts not built")
    a = json.loads(ev.read_text(encoding="utf-8"))["km_survival_by_level"]
    b = json.loads(cv.read_text(encoding="utf-8"))["km_survival_by_level"]
    assert a == b
    assert cv.stat().st_size < 4096


def test_qprp08_writer_and_harness_redirect():
    import eta_backtest
    src = (ROOT / "eta_backtest.py").read_text(encoding="utf-8")
    assert "write_curves(out)" in src
    assert eta_backtest.CURVES_PATH.name == "eta_curves.json"
    conf = (ROOT / "conftest.py").read_text(encoding="utf-8")
    assert '("eta_backtest", "CURVES_PATH", "data/eta_curves.json")' in conf


def test_qprp08_write_curves_lands_on_the_redirected_path(tmp_path, monkeypatch):
    import eta_backtest
    monkeypatch.setattr(eta_backtest, "CURVES_PATH", tmp_path / "c.json")
    eta_backtest.write_curves({"km_survival_by_level": {"AA": [0.5, 0.25]}, "other": 1})
    got = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert got["km_survival_by_level"] == {"AA": [0.5, 0.25]}
    assert "other" not in got


def test_qprp05_stuff_percentile_scans_once_per_render_pass():
    i = PAGE.index("function _pitchStuffPeerVals(")
    memo = PAGE[i:i + 1600]
    assert "queueMicrotask(() => { _pxStuffPeerMemo = null; })" in memo
    j = PAGE.index("function _formatPitchStuffPercentile(")
    fmt = PAGE[j:j + 1400]
    assert "_pitchStuffPeerVals(level, type)" in fmt
    assert ".filter(e => e.key !== selfKey)" in fmt
    assert "DATA.players" not in fmt  # no per-row cohort scan
    assert "function _sameLevelPitcherStatcastCohort(" not in PAGE
