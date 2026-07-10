# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the WAR-engine cohort diagnostic harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import pytest

import war_cohort_diagnostic as wcd


# ── bucketing helpers ────────────────────────────────────────────────────────
@pytest.mark.parametrize("age,band", [(None, "unk"), (22, "<=24"), (24, "<=24"),
                                       (27, "25-29"), (31, "30-32"), (35, "33+")])
def test_age_band(age, band):
    assert wcd._age_band(age) == band


@pytest.mark.parametrize("w,tier", [(None, "unk"), (5.0, "star_4+"), (4.0, "star_4+"),
                                    (3.0, "solid_2-4"), (1.0, "fringe_.5-2"), (0.1, "repl_<.5")])
def test_war_tier(w, tier):
    assert wcd._war_tier(w) == tier


@pytest.mark.parametrize("p,b", [(-1.0, "neg"), (0.5, "0-1"), (1.5, "1-2"),
                                 (2.5, "2-3"), (3.5, "3-4"), (9.0, "4+")])
def test_pred_bucket(p, b):
    assert wcd._pred_bucket(p) == b


# ── cell metrics + thin-cell suppression ─────────────────────────────────────
def test_thin_cell_is_stub():
    pairs = [(1.0, 1.0)] * (wcd.THIN_N - 1)
    m = wcd._cell_metrics(pairs)
    assert m["thin"] is True and m["n"] == wcd.THIN_N - 1
    assert "mean_resid" not in m and "spearman" not in m


def test_cell_metrics_resid_is_pred_minus_act():
    # 40 pairs, pred uniformly 2 over act -> mean_resid +2, no rank stats (n<50)
    pairs = [(a + 2.0, float(a)) for a in range(40)]
    m = wcd._cell_metrics(pairs)
    assert m["n"] == 40
    assert m["mean_resid"] == pytest.approx(2.0)
    assert m["mae"] == pytest.approx(2.0)
    assert "spearman" not in m   # below RANK_MIN_N


def test_cell_metrics_rank_stats_above_threshold():
    pairs = [(float(a), float(a)) for a in range(60)]   # perfect rank
    m = wcd._cell_metrics(pairs)
    assert m["n"] == 60
    assert m["spearman"] == pytest.approx(1.0, abs=1e-6)
    assert m["calib_slope"] == pytest.approx(1.0, abs=1e-6)


# ── aggregation tags every pair into exactly one cell per axis ───────────────
def test_aggregate_partitions_pairs():
    tagged = []
    for i in range(80):
        tagged.append({"pred": 5.0, "act": 3.0, "survived": True, "side": "hit",
                       "role": "C", "age_band": "25-29", "war_tier": "star_4+",
                       "pred_bucket": "4+", "h": 1})
    out = wcd._aggregate(tagged)
    cell = out["side_x_war_tier"]["hit:star_4+"]["h1"]
    assert cell["n"] == 80
    assert cell["mean_resid"] == pytest.approx(2.0)        # over-predicts by 2
    assert cell["survived_mean_resid"] == pytest.approx(2.0)


# ── real artifact + registry wiring ──────────────────────────────────────────
def test_artifact_present_and_shaped():
    art = json.loads((ROOT / "data" / "war_cohort_eval.json").read_text(encoding="utf-8"))
    assert "champion" in art and art["champion"]["n_players"] > 0
    for axis in ("by_pred_bucket", "by_age_band", "by_role", "by_base_war_tier", "side_x_war_tier"):
        assert axis in art["champion"]["cohorts"]
    assert "+ = engine over-predicts" in art["conventions"]["residual"] \
        or "over-predicts" in art["conventions"]["residual"]


def test_registered_in_model_registry():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    e = next((m for m in reg["models"] if m["model_id"] == "war_cohort_diagnostic"), None)
    assert e is not None
    assert e["verdict"] in reg["verdict_enum"]
    assert (ROOT / e["eval_artifact"]).exists()
