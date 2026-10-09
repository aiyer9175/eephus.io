"""The team-wins serve-vector tripwire meters the roll-up that serves.

Owner answer M15-4 (2026-09-25): re-run proj_backtest so the tripwire scores the
served roll-up. Until 2026-10-09 the retro block's served_recentered arm scored
the 2026-06-12 cohort vector, which stopped serving on 2026-08-04, so the
tripwire compared plain recentering against a vector nothing applied. These
pins keep the block honest after any later re-run: the served arm must equal
the arm the roll-up applies, season by season, and the forward gate must name
the frozen forecast it will grade.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import proj_export as pe
import proj_forward_vintage as pfv

ROOT = Path(__file__).resolve().parent


def _ev():
    p = ROOT / "data" / "team_outlook_eval.json"
    if not p.exists():
        pytest.skip("team_outlook_eval.json not present")
    return json.loads(p.read_text(encoding="utf-8"))


def test_the_served_arm_is_the_arm_the_roll_up_applies():
    ev = _ev()
    rb = ev["retro_backtest"]
    serving = bool(pe._cohort_intercepts())
    applied = "cohort_recentered" if serving else "recentered"
    hm = rb["ship_decision"]["holdout_mae"]
    assert hm["served_recentered"] == hm[applied], (hm, applied)
    for s in rb["team_level_per_season"]:
        assert s["served_recentered"] == s[applied], (s["season"], applied)


def test_the_tripwire_reads_the_re_run_block():
    ev = _ev()
    tw = ev["serve_vector_tripwire"]
    hm = ev["retro_backtest"]["ship_decision"]["holdout_mae"]
    assert tw["holdout_mae_served_recentered"] == hm["served_recentered"]
    assert tw["holdout_mae_recentered"] == hm["recentered"]
    assert tw["flag"] is (hm["served_recentered"] > hm["recentered"])
    assert ev["retro_backtest"]["generated_at"] >= "2026-10-09"


def test_the_forward_gate_names_the_frozen_forecast():
    fg = _ev()["forward_gate"]
    assert "frozen preseason copy" in fg["forecast"]
    assert fg["forecast_on_record"] is pfv.on_record(pe.FIRST_SEASON)[0]
