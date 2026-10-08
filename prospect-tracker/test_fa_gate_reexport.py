# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A saved FA gate re-runs the FA export from cached pages (owner answer M14-1),
and the verdict edges are re-derived by one recipe (owner answer M14-2).

docs/fa-2026-10-08/GATE2_RESAVE.md sections 4 and 5. Pinned here:
  - reexport_fa_sidecars logs and reports every served file it rewrote, runs
    the export inside scrapers.cache_only(), and reports a failed export
    instead of raising;
  - scrapers.cache_only() serves a cached page whatever its age (and whatever
    `force` says) and never reaches the network for a missing one;
  - the re-export is reachable only from a persisted gate, and the test
    harness turns it off (conftest.py sets FA_GATE_REEXPORT=0);
  - derive_verdict_edges cuts linear-interpolated p33/p67, rounded half up.
"""

from __future__ import annotations

import inspect
import os
import time

import pytest

import fa_backtest as fb
import scrapers


def test_reexport_reports_each_file_it_rewrote(tmp_path):
    (tmp_path / "a.json").write_text('{"x": 1}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"y": 1}', encoding="utf-8")
    seen = {}

    def fake_export():
        seen["cache_only"] = scrapers.cache_only_active()
        (tmp_path / "a.json").write_text('{"x": 2}', encoding="utf-8")
        (tmp_path / "c.json").write_text('{"z": 1}', encoding="utf-8")

    out = fb.reexport_fa_sidecars("unit", export=fake_export, data_dir=tmp_path,
                                  names=["a.json", "b.json", "c.json", "d.json"])
    assert seen["cache_only"] is True
    assert not scrapers.cache_only_active()
    assert out["error"] is None
    assert sorted(out["rewritten"]) == ["a.json", "c.json"]
    before, after = out["rewritten"]["a.json"]
    assert before[0] == after[0] == 8 and before[1] != after[1]
    assert out["rewritten"]["c.json"][0] is None
    assert out["unchanged"] == ["b.json", "d.json"]


def test_a_failed_reexport_is_reported_not_raised(tmp_path):
    def boom():
        raise RuntimeError("no war_daily")

    out = fb.reexport_fa_sidecars("unit", export=boom, data_dir=tmp_path,
                                  names=["a.json"])
    assert out["error"] == "RuntimeError: no war_daily"
    assert out["rewritten"] == {} and out["unchanged"] == ["a.json"]
    assert not scrapers.cache_only_active()


def test_cache_only_reads_stale_pages_and_never_fetches(tmp_path, monkeypatch):
    monkeypatch.setattr(scrapers, "CACHE_DIR", tmp_path)
    page = tmp_path / "spotrac_fixture_2026.html"
    page.write_text("cached body", encoding="utf-8")
    old = time.time() - 400 * 86400
    os.utime(page, (old, old))

    def no_network(*a, **k):
        raise AssertionError("cache_only reached the network")

    monkeypatch.setattr(scrapers.requests, "get", no_network)
    with scrapers.cache_only():
        hit = scrapers._fetch("https://example.invalid/a", "spotrac_fixture_2026", force=True)
        miss = scrapers._fetch("https://example.invalid/b", "spotrac_missing_2026")
    assert (hit.status, hit.body, hit.from_cache) == (200, "cached body", True)
    assert (miss.status, miss.body) == (0, "")


def test_only_a_persisted_gate_reaches_the_reexport():
    g2 = inspect.getsource(fb.run_market_gate)
    assert g2.count("reexport_fa_sidecars(") == 1
    assert "if persist and reexport and reexport_on_persist():\n        reexport_fa_sidecars(" \
        in g2.replace("\r\n", "\n")
    g1 = inspect.getsource(fb.run_projection_gate).replace("\r\n", "\n")
    assert g1.count("reexport_fa_sidecars(") == 1
    persist_block = g1.split("    if persist:\n", 1)[1]
    assert "        if reexport and reexport_on_persist():\n            reexport_fa_sidecars(" \
        in persist_block
    for fn in (fb.run_market_gate, fb.run_projection_gate):
        assert inspect.signature(fn).parameters["reexport"].default is True


def test_the_harness_turns_the_reexport_off():
    assert os.environ.get("FA_GATE_REEXPORT") == "0"
    assert fb.reexport_on_persist() is False


def test_round_half_up_and_linear_percentiles():
    assert [fb._round_half_up(x) for x in (2.5, 3.5, 2.49, -0.5)] == [3, 4, 2, 0]
    vals = [float(v) for v in range(1, 301)]
    assert fb._pct_linear(vals, 33) == pytest.approx(99.67)
    assert fb._pct_linear(vals, 67) == pytest.approx(201.33)


def test_derive_verdict_edges_cuts_terciles_and_counts_flips():
    rows = ([{"group": "SP", "deal_plus": float(v)} for v in range(1, 301)]
            + [{"group": "RP", "deal_plus": float(v) / 2} for v in range(1, 301)])
    cells = fb.derive_verdict_edges(rows, {"SP": (90, 190), "pooled": (50, 150)})
    sp = cells["SP"]
    assert sp["edges"] == [100, 201]
    assert sp["counts"] == {"overpay": 99, "market": 101, "value": 100}
    assert sp["served_edges"] == [90, 190]
    assert sp["served_counts"] == {"overpay": 89, "market": 100, "value": 111}
    assert sp["flips"] == 10 + 11
    assert cells["RP"]["edges"] == [50, 101] and "served_edges" not in cells["RP"]
    assert cells["pooled"]["n"] == 600
    assert "C" not in cells
