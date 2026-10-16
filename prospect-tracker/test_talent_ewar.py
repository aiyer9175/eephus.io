# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Talent eWAR (docs/ewar/TALENT_EWAR_GATE.md) on synthetic fixtures with nulls: departures are
zero-sum, the band narrows with exposure, the dispositions keep their precedence, a planted
departure wins and an all-zero one never does."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import talent_ewar as te  # noqa: E402
import talent_ewar_lab as telab  # noqa: E402

# talent eWAR ----------------------------------------------------------------------------


def test_talent_constants_frozen():
    assert te.FROZEN is not None and set(te.FROZEN) == set(te.HIT_PARTS) | set(te.PIT_PARTS)
    assert te.B1_K is not None and set(te.B1_K) == {"hit", "pit"}


def test_hitter_departures_are_zero_sum_per_season():
    rng = np.random.default_rng(1)
    n = rng.integers(1, 700, 400).astype(float)
    rates = {c: rng.normal(0, 0.02, 400) for c in te.HIT_PARTS}
    means = {c: 0.0 for c in te.HIT_PARTS}
    d = te.hitter_departures(n, rates, means, te.FROZEN)
    for c in te.HIT_PARTS:
        assert abs(float(d[c].sum())) < 1e-9


def test_pitcher_departure_is_zero_sum_on_innings():
    rng = np.random.default_rng(2)
    n = rng.integers(1, 900, 300).astype(float)
    ip = n / 4.3
    rates = {"K": rng.uniform(0.1, 0.35, 300), "BH": rng.uniform(0.04, 0.12, 300), "HR": rng.uniform(0.01, 0.05, 300)}
    means = {c: float(np.mean(v)) for c, v in rates.items()}
    D = te.pitcher_departure(n, ip, rates, means, te.FROZEN, 10.0)
    assert abs(float(D.sum())) < 1e-9


def test_band_narrows_with_exposure():
    sd_small = te.hitter_band_sd([100.0], te.FROZEN, 10.0)[0] / 100.0
    sd_big = te.hitter_band_sd([700.0], te.FROZEN, 10.0)[0] / 700.0
    assert sd_big < sd_small


def test_disposition_precedence():
    assert te.disposition(True, 0.008, 0.002, 0.014, 0.003, 0.013, 0.001, -0.1, True) == "SMALL WIN"
    assert te.disposition(True, 0.03, 0.01, 0.05, 0.012, 0.045, 0.002, -0.1, True) == "WIN (components)"
    assert te.disposition(True, 0.03, 0.01, 0.05, 0.012, 0.045, -0.002, -0.1, True) == "WIN (regression only)"
    assert te.disposition(False, -0.03, -0.05, -0.01, -0.045, -0.012, None, None, True) == "LOSS"
    assert te.disposition(False, 0.0, -0.025, 0.025, -0.015, 0.015, None, None, True) == "EQUIVALENT"


def test_talent_dry_run_planted_wins_null_never():
    r = telab.dry_run(log=lambda *a: None)
    assert r["dry_run_pass"]
    assert not r["null"]["rate"].startswith("WIN")
