# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The knots-only calibration entry (VAL_5, DESIGN_v2 section 6;
docs/dpw-2026-09-25/DPW_PATH_GATE.md 0a): backtest.fit_calibration_knots fits
the binned isotonic map and computes NOTHING else (no by_fv_tier, which would be
a realized statistic by consensus-FV cell, no sensitivity table, no PIT, no
slope, no bias, no held-out figure), never calls run_backtest, and the repaired
tools/fit_surplus_calibration.py names only the pool, n, the knot count and the
target pricing. Run on the backtest's own SYNTHETIC cohort only."""

from __future__ import annotations

import inspect
import json

import pytest

import backtest
import dpw_testkit as kit
import value_framework as vf

BANNED = ("by_fv_tier", "sensitivity", "pit", "slope", "bias", "held_out", "cross_validated",
          "raw_calibration", "raw_errors", "coverage")


@pytest.fixture(scope="module")
def records():
    recs, _ = backtest.make_synthetic_cohort(n_per_year=30)
    return recs


@pytest.fixture(autouse=True)
def _no_run_backtest(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("run_backtest called from the knots-only path")
    monkeypatch.setattr(backtest, "run_backtest", boom)


def _keys(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k).lower())
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def test_today_flat_returns_the_map_and_nothing_else(records):
    fit = backtest.fit_calibration_knots(records, target_pricing="today_flat")
    assert set(fit) == {"n_players", "n_bins", "target_pricing", "fitted_correction"}
    keys = _keys(fit)
    for b in BANNED:
        assert not any(b in k for k in keys), b
    assert fit["n_players"] == sum(1 for r in records if r.listing.pre_debut)
    xs, ys = fit["fitted_correction"]["x_mm"], fit["fitted_correction"]["y_mm"]
    assert len(xs) == len(ys) >= 2 and all(b >= a for a, b in zip(ys, ys[1:]))


def test_the_return_carries_no_fv_or_tier_key(records):
    """M11_PROSPECT_ARB_VIA_MODEL (docs/PROSPECT_ANCHOR_GATE.md): the refit the
    prospect arbitration swap runs may not return anything keyed by an FV cell
    or a tier, at any depth."""
    for target in ("today_flat",):
        keys = _keys(backtest.fit_calibration_knots(records, target_pricing=target))
        assert not [k for k in keys if "fv" in k or "tier" in k], keys


def test_today_path_needs_the_unified_path(records, tmp_path):
    with pytest.raises(ValueError):
        backtest.fit_calibration_knots(records, target_pricing="today_path")
    with pytest.raises(ValueError):
        backtest.fit_calibration_knots(records, target_pricing="historical")
    with kit.unified(tmp_path):
        fit = backtest.fit_calibration_knots(records, target_pricing="today_path")
        assert set(fit) == {"n_players", "n_bins", "target_pricing", "fitted_correction"}
        assert fit["target_pricing"] == "today_path"
        assert vf.dpw_path_active()


def test_the_entry_computes_no_fv_cell_statistic():
    src = inspect.getsource(backtest.fit_calibration_knots)
    for b in ("by_fv_tier", "run_backtest(", "sensitivity", "pit_", "slope", "bias"):
        assert b not in src.replace("no slope, no bias", "").replace(
            "No by_fv_tier", "").replace("computes nothing else", ""), b


def test_the_tool_provenance_names_only_pool_n_knots_and_target():
    from tools import fit_surplus_calibration as fsc
    text = fsc.fit_provenance(412, 25, "today_path")
    low = text.lower()
    for b in ("slope", "bias", "held-out", "held out", "cross", "pit"):
        assert b not in low, b
    for want in ("n=412", "25 knots", "today_path", "resolved pool"):
        assert want in text, want
    src = inspect.getsource(fsc)
    assert "run_backtest" not in src.replace("never calls backtest.run_backtest", "")
    assert "fit_calibration_knots" in src
    assert "from surplus_backtest_real import build_cohorts" in src
    block_src = inspect.getsource(fsc.build_block)
    assert "fit_calibration_knots(resolved, target_pricing=target_pricing)" in block_src
    assert inspect.signature(fsc.main).parameters["argv"].default is None


def test_the_tool_writes_only_when_given_a_path(monkeypatch, tmp_path, capsys):
    from tools import fit_surplus_calibration as fsc
    monkeypatch.setattr(fsc, "build_block", lambda target="today_flat": {"enabled": True,
                                                                         "target_pricing": target})
    assert fsc.main([]) == 0
    assert list(tmp_path.iterdir()) == []
    out = tmp_path / "fit.json"
    assert fsc.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["target_pricing"] == "today_flat"
