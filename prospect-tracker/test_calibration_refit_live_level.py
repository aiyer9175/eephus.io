# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CAL_KNOTS_REFIT_17M (owner answer VAL1-Q2, 2026-09-30): the served
prospect-surplus calibration at the live $/WAR level IS the knots-only refit,
not the VAL_1 bridge.

VAL_1 moved prospect surplus to the free-agent winter level and applied the v6
map (fit at the FanGraphs $11.74M) by unit conversion, s * f(x / s) with
s = live / 11,740,000. That bridge is inexact (the league-minimum and anchor
legs do not scale with the level). The one sanctioned refit fits the same map
through backtest.fit_calibration_knots at the live level, so the knots are
applied as fitted: fit_dpw_flat_usd equals the live level, the scale is the
identity, and the function stays for a future level change. The held-out
figures are not re-measured (that needs the backtest docs/PROSPECT_ANCHOR_GATE.md
bans before its look), and the registry and glossary say so."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import numpy as np
import pytest

import backtest
import surplus_backtest_real as sbr
import value_framework as vf
from efv_vintage_frame import RESERVED_LV

ROOT = Path(__file__).parent
V6_X = [0.82, 1.1, 1.42, 1.85, 2.09, 3.34, 5.06, 8.04, 9.59, 19.35, 36.42, 400.0]
V6_Y = [0.67, 1.59, 2.78, 2.95, 3.48, 5.2, 9.3, 13.76, 20.78, 35.68, 57.56, 523.59]
V6_FIT_USD = 11_740_000.0
LABEL = ("measured at $11.74M before the refit; not re-measured until "
         "docs/PROSPECT_ANCHOR_GATE.md's look")


def _cal():
    return vf._config()["calibration"]


def test_the_knots_are_fit_at_the_live_level():
    cal = _cal()
    series = json.loads((ROOT / "data" / "fa_dpw_series.json").read_text(encoding="utf-8"))
    live = int(series["pricing"]["level_usd"])
    assert int(cal["fit_dpw_flat_usd"]) == live
    assert int(round(vf._flat_rate_usd())) == live
    assert vf.calibration_level_scale() == 1.0
    assert vf.calibration_stamp()["dpw_level_usd"] == live


def test_the_served_map_is_the_refit_knots_not_the_bridge():
    """apply_calibration at the live level equals interpolation on the refit
    knots directly, and differs from the v6 bridge s * f6(x / s)."""
    cal = _cal()
    xs = [float(v) for v in cal["isotonic"]["x_mm"]]
    ys = [float(v) for v in cal["isotonic"]["y_mm"]]
    s = vf._flat_rate_usd() / V6_FIT_USD
    grid = [0.5, 1.18, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0, 500.0]
    served = [vf.apply_calibration(x) for x in grid]
    assert served == pytest.approx([float(np.interp(x, xs, ys)) for x in grid], abs=1e-9)
    bridge = [s * float(np.interp(x / s, V6_X, V6_Y)) for x in grid]
    assert max(abs(a - b) for a, b in zip(served, bridge)) > 1.0
    assert s == pytest.approx(1.4358, abs=5e-4)


def test_the_stamp_records_the_refit_date_level_and_entry_point():
    cal = _cal()
    assert cal["fit_entry_point"] == "backtest.fit_calibration_knots"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cal["fit_date"]))
    assert str(cal["version"]).endswith(str(cal["fit_date"]))
    assert cal["target_pricing"] == "today_flat"
    assert "n=2235" in cal["fit_rows"] and "2017-2019" in cal["fit_rows"]
    assert "_resolved_only" in cal["fit_rows"]
    assert "n=2235" in cal["fit_provenance"]


def test_the_training_rows_touch_no_reserved_frame():
    """The pool is the 2017-2019 listings, resolved by LAST_FULL_SEASON: the
    R-LV list vintages and the R-VM 2025+ debut cohorts cannot enter."""
    years = set(sbr.LISTING_YEARS)
    assert years == {2017, 2018, 2019}
    assert not (years & set(RESERVED_LV))
    assert max(years) < 2025
    assert sbr.LAST_FULL_SEASON == 2025 and sbr.CONTROL_YEARS == 6
    doc = inspect.getdoc(backtest.fit_calibration_knots)
    for must in ("build_cohorts", "_resolved_only", "2017-2019", "pre_debut", "n=2235"):
        assert must in doc, must


def test_the_tool_stamps_the_entry_point_and_rows(monkeypatch):
    from tools import fit_surplus_calibration as fsc
    fake = {"n_players": 7, "n_bins": 25, "target_pricing": "today_flat",
            "fitted_correction": {"method": "isotonic", "x_mm": [1.0, 2.0, 3.0],
                                  "y_mm": [1.0, 2.5, 4.0]}}
    monkeypatch.setattr(fsc, "build_cohorts", lambda: ([], {}))
    monkeypatch.setattr(fsc, "_resolved_only", lambda recs: recs)
    monkeypatch.setattr(fsc, "fit_calibration_knots", lambda recs, target_pricing: fake)
    block = fsc.build_block("today_flat")
    assert block["fit_entry_point"] == "backtest.fit_calibration_knots"
    assert block["fit_rows"] == ("surplus_backtest_real.build_cohorts pre-debut listings "
                                 "2017-2019, _resolved_only, n=7")
    assert block["version"].endswith(block["fit_date"])
    assert block["fit_dpw_flat_usd"] == int(round(vf.dollars_per_war_flat() * 1e6))


def test_registry_and_glossary_carry_the_remeasure_label():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "prospect_surplus")
    assert row["remeasure_pending"].startswith(LABEL)
    # The summary is served copy (no docs/ path under copy rule L8), so it
    # carries the short form of the same label.
    assert "measured at $11.74M before the refit; not re-measured until the Prospect Anchor look" in row["summary"]
    assert "fit_dpw_flat_usd is the live level" in row["notes"]
    # The glossary is served copy too (copy rule L8 bans a docs/ path there), so
    # the three entries carry the same label in its served form.
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in gl["entries"]}
    for eid in ("value_framework", "surplus_value", "dpw_tier"):
        text = (entries[eid].get("definition") or "") + (entries[eid].get("methodology") or "")
        assert "measured at $11.74M before the refit; not re-measured until the Prospect Anchor look" in text, eid
