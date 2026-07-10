# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 4 -- Star Odds: definition, Poisson-binomial + Gamma-survival building
blocks, monotone-in-FV shrinkage, pitcher<hitter role mix, published-table
display value, calibration report, and the xFV label view artifact."""
import json
from pathlib import Path

import pytest

import value_framework as vf

_DATA = Path(vf.__file__).resolve().parent / "data"


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
def test_poisson_binomial_ge():
    assert vf._poisson_binomial_ge([0.5, 0.5], 2) == pytest.approx(0.25)
    assert vf._poisson_binomial_ge([0.5, 0.5, 0.5], 2) == pytest.approx(0.5)
    assert vf._poisson_binomial_ge([1.0, 1.0], 2) == pytest.approx(1.0)
    assert vf._poisson_binomial_ge([0.0, 0.0, 0.0], 2) == pytest.approx(0.0)
    assert vf._poisson_binomial_ge([0.9, 0.1], 1) == pytest.approx(1 - 0.1 * 0.9)
    assert vf._poisson_binomial_ge([0.3, 0.4, 0.5], 0) == 1.0


def test_season_ge_prob():
    # cv==0 is a point mass at the level.
    assert vf._season_ge_prob(5.0, 0.0, 4.0) == 1.0
    assert vf._season_ge_prob(3.0, 0.0, 4.0) == 0.0
    assert vf._season_ge_prob(0.0, 0.5, 4.0) == 0.0
    # Monotone increasing in the level for a fixed cv.
    lo = vf._season_ge_prob(2.0, 0.5, 4.0)
    hi = vf._season_ge_prob(4.0, 0.5, 4.0)
    assert 0.0 < lo < hi < 1.0


# --------------------------------------------------------------------------
# star_odds: range, ordering, monotonicity, role mix
# --------------------------------------------------------------------------
def test_star_odds_range_and_ordering():
    for fv in (40, 45, 50, 55, 60, 65, 70):
        h = vf.star_odds(fv, False)
        p = vf.star_odds(fv, True)
        assert 0.0 <= h <= 1.0 and 0.0 <= p <= 1.0
        # Pitchers blend in bullpen-capped paths that cannot clear 4 WAR -> lower.
        assert p <= h + 1e-9
    # Rises with FV.
    assert vf.star_odds(70, False) > vf.star_odds(50, False) > vf.star_odds(40, False)


@pytest.mark.parametrize("is_pit", [False, True])
def test_star_odds_curve_is_monotone(is_pit):
    c = vf.star_odds_curve(is_pit)
    odds = c["odds"]
    assert all(odds[i] <= odds[i + 1] + 1e-9 for i in range(len(odds) - 1))
    assert len(c["fv"]) == len(c["raw"]) == len(c["odds"])


def test_star_definition_from_active_set():
    assert vf._star_def() == (2, 4.0)   # default
    with vf.valuation_set("clemens_2026"):
        assert vf._star_def() == (2, 4.0)
        assert int(vf._config()["service_time"]["control_years"]) == 7


# --------------------------------------------------------------------------
# Published (table-mode) display value -- the credible industry number
# --------------------------------------------------------------------------
def test_published_star_odds_matches_table():
    assert vf.published_star_odds(50, False) == pytest.approx(0.135, abs=1e-6)
    assert vf.published_star_odds(50, True) == pytest.approx(0.070, abs=1e-6)
    assert vf.published_star_odds(70, False) == pytest.approx(0.875, abs=1e-6)
    # Monotone non-decreasing by construction of the published table.
    seq = [vf.published_star_odds(fv, False) for fv in (40, 45, 50, 55, 60, 65, 70)]
    assert all(seq[i] <= seq[i + 1] + 1e-9 for i in range(len(seq) - 1))


# --------------------------------------------------------------------------
# Calibration report + snapshot
# --------------------------------------------------------------------------
def test_calibration_report_structure():
    rep = vf.star_odds_calibration("clemens_2026")
    assert set(rep["roles"]) == {"hitter", "pitcher"}
    for role in ("hitter", "pitcher"):
        d = rep["roles"][role]
        assert "max_abs_dev" in d and d["tiers"]
        for row in d["tiers"]:
            assert {"tier", "fv", "published", "model", "abs_dev"} <= set(row)
    # Restored to the default set (clemens_2026) after the report's context manager.
    assert vf.active_valuation_set() == "clemens_2026"


def test_snapshot_carries_star_odds():
    snap = vf.build_snapshot()
    so = snap["star_odds"]
    assert so["definition"] == {"min_seasons": 2, "war_threshold": 4.0}
    assert so["published_by_grade"]["hitter"]["50"] == pytest.approx(0.135, abs=1e-6)
    assert "model_by_grade" in so and "model_curve" in so
    assert set(so["calibration"]) == {"hitter", "pitcher"}


# --------------------------------------------------------------------------
# Artifacts on disk (real numbers only)
# --------------------------------------------------------------------------
def test_star_odds_eval_artifact():
    doc = json.loads((_DATA / "star_odds_eval.json").read_text(encoding="utf-8"))
    assert doc["experiment"] == "star-odds-calibration"
    assert "gate" in doc and "max_abs_dev" in doc["gate"]
    assert set(doc["calibration"]["roles"]) == {"hitter", "pitcher"}


def test_star_label_view_artifact():
    doc = json.loads((_DATA / "star_label_view.json").read_text(encoding="utf-8"))
    c = doc["counts"]
    assert c["n_players"] > 1000
    # A real, small, positive star class (career-wide ~1e2 per the data inventory).
    assert 50 <= c["n_star_career"] <= 250
    assert doc["definition"]["min_seasons"] == 2 and doc["definition"]["war_threshold"] == 4.0
    # Every record carries real per-season control WAR (no synthesized outcomes).
    top = doc["players"][0]
    assert {"player_key", "debut_year", "control_seasons", "star"} <= set(top)
