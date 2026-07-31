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

Guard 2 is RED as of 2026-07-30 and is being left red on purpose: it caught a
league-WAR level regression in the FA WAR paths within a day of that ship
landing. The measured causal chain is in test_recenter_remainder_near_zero's
docstring; the fix is owed by the FA lane, not by this bound.
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
    """RED ON PURPOSE since 2026-07-30 (remainder 4.48, roster_war_sum 886.2).

    This is the guard doing its job, and the bound is deliberately NOT widened.
    Triage 2026-07-30, all numbers measured on the SAME inputs (fa_corpus.pkl
    pickled 07-29 14:11 and the 30 spotrac_team_*.html caches from 07-29 12:45
    were both untouched by the 07-30 nightly, so nothing but code differs):

      cohort intercepts   NOT the cause. 30*REPLACEMENT_WINS + the cohort sum is
                          1388.4 before and 1388.5 after. They still fit.
      roster WAR          -43.5 (929.7 -> 886.2) = 1.45 wins/team.
      assigned depth      -11.8 (32.7 -> 20.9)   = 0.39 wins/team.
                          Together exactly the 2.64 -> 4.48 move.

    The cause is upstream of this file, in the FA WAR paths (fa_projection /
    fa_market, shipped 89112f5 on 07-29 20:36 - the E2 realized-WAR residual
    channel plus the E3 playing-time refit). Replaying the vet + depth paths on
    the identical corpus under the pre-ship code isolates it:

      vets with a path        1317 -> 1317   (nobody fell out of the universe)
      vet year-1 champion WAR 927.2 -> 866.6 (-60.6, -6.5% - a pure LEVEL drop)
      depth players           394   -> 276   (118 now project an ALL-ZERO
                                              5-season champion path)
      depth year-1 WAR        90.8  -> 43.4  (-52%)
      model league total      1018.0 -> 910.0 against the 1000-WAR benchmark

    The ship is not wrong about accuracy - Gate-1 WAR MAE 0.617 -> 0.583 on 10
    of 10 folds is real. It traded LEVEL for it, and a per-player MAE gate cannot
    see that because bias cancels in |error| and accumulates in a sum. The ship's
    own artifact says so in a field it added in the same commit:
    data/fa_gate1_eval.json pooled war bias_model -0.0770 against bias_base
    +0.0078, hitters -0.1533 (mean_pred 0.482 vs mean_actual 0.635), and the
    star slice war:hit:act_ge4 bias -3.11 against the baseline's -2.11. Shrinking
    the right tail is exactly what buys MAE and exactly what breaks a roster sum.

    So the honest fix is NOT here: either re-anchor the playing-time refit so the
    league still sums to ~1000, or re-fit the cohort intercepts on the new paths
    under their own holdout gate (proj_backtest.py). Widening this bound would
    delete the only instrument that noticed. See also REVIEW_QUEUE item 1
    (proj_lgbm star-tail refit) - this is the same under-projected star tail.
    """
    acc = _load("team_outlook_eval.json")["league_sum_accounting"]
    assert abs(acc["remainder_recenter_wins_per_team"]) < 3, (
        "the level should come from the model now (champion means + depth "
        "pool + cohort intercepts), not the recenter. See this test's "
        f"docstring for the measured causal chain: {acc}")
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


def test_vets_carry_champion_path_for_multiyear():
    """The multi-year roll-up needs the full champion MEAN array, not just the
    year-1 scalar; warChamp[0] must equal warY1Champ."""
    d = _load("mlb_projections.json")
    sample = [m for m in d["vets"] if m.get("warChamp")]
    assert len(sample) > len(d["vets"]) * 0.9, (
        f"only {len(sample)}/{len(d['vets'])} vets carry warChamp")
    for m in sample[:300]:
        assert len(m["warChamp"]) >= 1
        if m.get("warY1Champ") is not None:
            assert abs(m["warChamp"][0] - m["warY1Champ"]) < 0.06, m["name"]


def test_team_outlook_multiyear_recenter():
    """Every projected season independently recenters to the 2,430-win league
    sum (W+L=162 per team), the multi-year analogue of the year-1 guard."""
    rows = _load("mlb_projections.json")["team_outlook"]
    if not any(r.get("byYear") for r in rows):
        pytest.skip("single-season export (no byYear)")
    horizon = max(len(r.get("byYear") or []) for r in rows)
    for t in range(horizon):
        seas = [r["byYear"][t] for r in rows if t < len(r.get("byYear") or [])]
        total = sum(s["wins"] for s in seas)
        assert abs(total - 2430) < 2, f"season idx {t} projects {total} wins"
        for s in seas:
            assert abs(s["wins"] + s["losses"] - 162) < 0.2


def test_team_outlook_locked_pct_bounds():
    """The cost-controlled lock-up % is a WAR-weighted share in [0,1], and the
    controlled WAR never exceeds the everyone-stays denominator."""
    rows = _load("mlb_projections.json")["team_outlook"]
    have = [r for r in rows if r.get("lockedPct") is not None]
    if not have:
        pytest.skip("no lockedPct in export")
    assert len(have) >= 25
    for r in have:
        assert 0.0 <= r["lockedPct"] <= 1.0, r["team"]
        assert r["ctrlWar5y"] <= r["fullWar5y"] + 0.11, r["team"]


def test_team_outlook_first_season_matches_byyear():
    """The back-compat top-level fields must equal byYear[0] (GFX + older
    consumers read them directly)."""
    rows = _load("mlb_projections.json")["team_outlook"]
    for r in rows:
        if not r.get("byYear"):
            continue
        assert r["wins"] == r["byYear"][0]["wins"], r["team"]
        assert r["war"] == r["byYear"][0]["war"], r["team"]
