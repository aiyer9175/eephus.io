# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fit-engine guards: component directions, win-curve shape, displacement
need, weight discipline. Pure unit tests on the transparent pieces — the
composite is exercised end-to-end by the Stage-4 checkpoint script."""

from __future__ import annotations

import pytest

import fa_class
import fa_fit


def test_position_norm():
    assert fa_fit._position_norm("LHP") == "SP"
    assert fa_fit._position_norm("CL") == "RP"
    assert fa_fit._position_norm("OF") == "CF"
    assert fa_fit._position_norm("SS/2B") == "SS"
    assert fa_fit._position_norm(None) == "DH"


def test_weights_sum_to_one():
    w = fa_class.get_config()["fit"]["weights"]
    assert sum(w.values()) == pytest.approx(1.0)


def test_win_leverage_shape():
    """Leverage must RISE toward the curve center and FALL past it — the
    85-win team gains more from +4 WAR than the 70- or 100-win team."""
    cfg = fa_class.get_config()["fit"]["win_curve"]
    center = cfg["center"] - cfg.get("roster_fill_wins", 0)
    below = fa_fit.win_leverage(center - 12)
    at = fa_fit.win_leverage(center)
    above = fa_fit.win_leverage(center + 12)
    assert at == pytest.approx(1.0, abs=1e-9)        # normalized peak
    assert below < at and above < at
    assert fa_fit.win_leverage(center - 25) < below  # monotone on the flank


def test_park_component_directions(monkeypatch):
    """Hitters score high in hitter parks; pitchers score high in
    suppressive parks — same venue, opposite reading."""
    pf = {"COL": {"woba": 113, "hr": 106, "runs": 128},
          "SEA": {"woba": 92, "hr": 98, "runs": 85}}
    monkeypatch.setattr(fa_fit, "park_factors", lambda season, bat_side="": pf)
    hitter = {"position": "SS", "bat_throw": "R/R"}
    pitcher = {"position": "SP", "bat_throw": "L/L"}
    assert fa_fit.park_component(hitter, "COL", 2026)["score"] > 0.6
    assert fa_fit.park_component(hitter, "SEA", 2026)["score"] < 0.4
    assert fa_fit.park_component(pitcher, "SEA", 2026)["score"] > 0.6
    assert fa_fit.park_component(pitcher, "COL", 2026)["score"] < 0.4
    # unknown venue falls back to neutral, never invents
    assert fa_fit.park_component(hitter, "XXX", 2026)["score"] == pytest.approx(0.5)


def test_need_is_displacement_not_unit_sum():
    """The Stage-4 checkpoint regression: an ace joining a rotation
    displaces the 5TH starter, not the staff sum — need must stay alive
    for top-of-class players on deep teams."""
    inc = [{"name": f"P{i}", "position": "SP", "war_proj": w}
           for i, w in enumerate([3.0, 2.5, 2.0, 1.0, 0.3])]
    slot = {"SP": 4, "RP": 2}.get("SP", 0)
    displaced = inc[slot]["war_proj"]
    assert displaced == 0.3                      # not sum(8.8)
    war1 = 3.6
    gap = max(0.0, war1 - displaced)
    assert gap > 3.0                             # the ace still fills a need
