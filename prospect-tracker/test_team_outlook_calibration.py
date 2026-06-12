# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Team Outlook calibration guards (the 83-win-Dodgers post-mortem).

Two failure modes are pinned here so they cannot silently return:
  1. LEVEL - the roll-up once summed ML quantile-head points (median-like,
     ~520 league WAR) over a floor-gated universe (~56% of the league);
     the league projected to 1,991 wins instead of 2,430.
  2. ACCOUNTING - the recentering remainder must stay near zero now that
     the level comes from the model (champion means + depth pool +
     cohort intercepts); a growing remainder means a regression upstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def _load(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"{name} not exported on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def test_league_wins_sum_to_2430():
    rows = _load("mlb_projections.json")["team_outlook"]
    assert len(rows) == 30
    total = sum(r["wins"] for r in rows)
    assert abs(total - 2430) < 2, f"league projects {total} wins (real season = 2430)"
    for r in rows:
        assert abs(r["wins"] + r["losses"] - 162) < 0.2, r["team"]


def test_best_team_is_plausible():
    """The original bug reading: the best team in baseball projected 83
    wins. Projected best should land in the (compressed) 88-105 band and
    the worst in 55-75 - levels a reader can take literally."""
    rows = _load("mlb_projections.json")["team_outlook"]
    best, worst = rows[0]["wins"], rows[-1]["wins"]
    assert 88 <= best <= 105, f"best team projects {best}"
    assert 55 <= worst <= 75, f"worst team projects {worst}"


def test_recenter_remainder_near_zero():
    acc = _load("team_outlook_eval.json")["league_sum_accounting"]
    assert abs(acc["remainder_recenter_wins_per_team"]) < 3, (
        "the level should come from the model now (champion means + depth "
        f"pool + cohort intercepts), not the recenter: {acc}")
    assert 900 <= acc["roster_war_sum"] <= 1100, acc["roster_war_sum"]


def test_retro_backtest_block_preserved():
    """proj_export must never clobber the committed backtest measurement."""
    ev = _load("team_outlook_eval.json")
    rb = ev.get("retro_backtest")
    assert rb, "retro_backtest block missing from team_outlook_eval.json"
    assert rb["player_level"]["pooled"]["n"] > 5000
    assert rb["ship_decision"]["holdout_mae"] is not None


def test_vets_carry_champion_year1_for_aggregation():
    d = _load("mlb_projections.json")
    n = sum(1 for m in d["vets"] if m.get("warY1Champ") is not None)
    assert n > len(d["vets"]) * 0.9, (
        f"only {n}/{len(d['vets'])} vets carry warY1Champ - team sums "
        "would fall back to the median-like displayed points")
