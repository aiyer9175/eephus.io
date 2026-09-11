# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Section 7g: the total-scoped NB2 dispersion, the shape half of the Over-lean
repair.

  1. Not served, and a stray context key cannot reprice a total.
  2. With a dispersion the TOTAL moves and nothing else: every moneyline and
     runline number is bit-identical.
  3. Without one the total is the shipped Poisson, bit for bit, and the row
     carries no new key.
  4. The NB total keeps the mean and moves mass below it: Over 8.5 falls at a
     league-typical pair of lambdas.
  5. The fit finds almost no dispersion when the truth is Poisson and recovers it
     when the truth is overdispersed.

Offline: synthetic teams, synthetic rows, a tmp context file.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

import betting_model as bm

TEAMS = {"_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
         "KCR": {"z_off": 0.10, "offense_plus": 102.0, "bullpen_plus": 101.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60},
         "CHC": {"z_off": 0.05, "offense_plus": 101.0, "bullpen_plus": 100.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60}}
KW = dict(teams=TEAMS, parks={"KCR": 1.0}, coeffs=dict(bm.LITERATURE_COEFFS),
          home_adj=0.2, diff_shrink=0.8)
ML_RL_KEYS = ("p_home", "p_away", "p_home_minus_1_5", "p_away_minus_1_5",
              "p_home_plus_1_5", "p_away_plus_1_5", "p_tie", "lam_home", "lam_away",
              "fair_total")


def _ctx(tmp_path: Path, **extra) -> Path:
    p = tmp_path / "betting_model_context.json"
    p.write_text(json.dumps(extra), encoding="utf-8")
    return p


def test_the_total_dispersion_is_not_served():
    """The tripwire: flipping SERVE_TOTAL_DISPERSION moves this test, the section
    7g record and MODEL_VERSION in one commit, and only from the gate."""
    assert bm.SERVE_TOTAL_DISPERSION is False
    assert bm.served_total_dispersion() is None


def test_a_stray_context_key_cannot_reprice_a_total(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "CONTEXT_PATH", _ctx(tmp_path, total_dispersion_alpha=0.3))
    assert bm.served_total_dispersion() is None
    gp = bm.game_probabilities("KCR", "CHC", **KW)
    assert "total_dispersion_alpha" not in gp


def test_a_dispersion_moves_the_total_and_nothing_else():
    base = bm.game_probabilities("KCR", "CHC", tie_home=0.49, **KW)
    moved = bm.game_probabilities("KCR", "CHC", tie_home=0.49, total_alpha=0.3, **KW)
    for k in ML_RL_KEYS:
        assert base[k] == moved[k], k
    assert moved["total_dispersion_alpha"] == 0.3
    assert moved["over"](8.5) != base["over"](8.5)


def test_no_dispersion_is_the_shipped_poisson_total_bit_for_bit():
    a = bm.game_probabilities("KCR", "CHC", tie_home=0.49, **KW)
    b = bm.game_probabilities("KCR", "CHC", tie_home=0.49, total_alpha=None, **KW)
    for line in (6.5, 7.5, 8.5, 9.5, 10.5, 11.5):
        assert a["over"](line) == b["over"](line)
    assert "total_dispersion_alpha" not in b


def test_the_nb_total_keeps_its_mean_and_moves_the_middle_down():
    lh, la = 4.4, 4.4
    pois = bm._total_pmf(lh, la, None)
    nb = bm._total_pmf(lh, la, 0.3)
    assert sum(nb) == pytest.approx(1.0, abs=1e-6)
    mean_nb = sum(k * p for k, p in enumerate(nb))
    assert mean_nb == pytest.approx(lh + la, abs=0.02)
    assert bm._pmf_over(nb, 8.5) < bm._pmf_over(pois, 8.5), (
        "at the league mean the dispersed total must put less mass over 8.5: "
        "that is the whole defect")
    assert bm._pmf_over(nb, 12.5) > bm._pmf_over(pois, 12.5)


def _nb_draw(rng, mean, alpha):
    r = 1.0 / alpha
    lam = rng.gammavariate(r, mean / r)
    # Poisson draw by inversion
    k, p, s, u = 0, math.exp(-lam), math.exp(-lam), rng.random()
    while u > s and k < 60:
        k += 1
        p *= lam / k
        s += p
    return k


def _pois_draw(rng, lam):
    k, p, s, u = 0, math.exp(-lam), math.exp(-lam), rng.random()
    while u > s and k < 60:
        k += 1
        p *= lam / k
        s += p
    return k


def test_the_fit_finds_little_dispersion_when_the_truth_is_poisson():
    rng = random.Random(7)
    rows = []
    for _ in range(400):
        lh, la = 4.0 + rng.random(), 4.0 + rng.random()
        rows.append((lh, la, _pois_draw(rng, lh) + _pois_draw(rng, la)))
    fit = bm.fit_total_dispersion(rows)
    assert fit["alpha"] < 0.08, fit["alpha"]


def test_the_fit_recovers_an_overdispersed_truth():
    rng = random.Random(11)
    rows = []
    for _ in range(600):
        lh, la = 4.0 + rng.random(), 4.0 + rng.random()
        rows.append((lh, la, _nb_draw(rng, lh, 0.3) + _nb_draw(rng, la, 0.3)))
    fit = bm.fit_total_dispersion(rows)
    assert 0.15 < fit["alpha"] < 0.5, fit["alpha"]
    assert fit["log_loss_nb"] < fit["log_loss_poisson"]


def test_the_fit_is_deterministic_and_refuses_an_empty_window():
    rows = [(4.2, 4.5, 9), (4.0, 4.1, 5), (5.0, 3.8, 12), (4.4, 4.4, 7)]
    assert bm.fit_total_dispersion(rows) == bm.fit_total_dispersion(rows)
    assert bm.fit_total_dispersion([]) is None


def test_the_gate_criteria_name_the_grid_the_scope_and_all_four_splits():
    c = bm.TOTAL_DISPERSION_GATE_CRITERIA
    for want in ("7.5, 8.5, 9.5, 10.5", "TOTAL only", "ALL FOUR", "moneyline",
                 "never criteria"):
        assert want in c, want
