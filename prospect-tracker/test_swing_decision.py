# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Swing-decision value (docs/ewar/SWING_DECISION_GATE.md) on synthetic fixtures with nulls:
the planted measure passes test X, the all-zero measure does not, the twin fails."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import swing_decision as sd  # noqa: E402
import swing_decision_lab as sdlab  # noqa: E402

# swing decisions ------------------------------------------------------------------------


def test_k_sd_is_frozen_and_finite():
    assert sd.K_SD is not None and np.isfinite(sd.K_SD) and sd.K_SD > 0


def test_decision_value_credits_the_better_choice():
    vb = np.array([0.5, 0.5])
    vball = np.array([0.6, 0.6])
    vstr = np.array([0.4, 0.4])
    # a pitch the league calls a ball (p0 0) where swinging loses: taking is right
    dv, vt, vs = sd.decision_values(vb, vball, vstr, [0, 0], np.array([0.0, 0.0]), np.array([1.0, 1.0]),
                                    np.array([0.0, 0.0]), np.array([0.0, 0.0]), np.array([0.0, 0.0]),
                                    np.array([0.0, 0.0]), [True, False])
    assert dv[0] > 0 and dv[1] < 0
    assert np.isclose(dv[0], -dv[1])


def test_split_half_k_rule():
    r = sd.split_half_k([1, 2, 3, 4, 5], [1.1, 2.2, 2.9, 4.2, 4.8], [1000] * 5)
    assert r["r_sb"] > r["r_half"] > 0 and r["K_SD"] > 0
    r0 = sd.split_half_k([1, 2, 3, 4], [4, 3, 2, 1], [1000] * 4)
    assert r0["K_SD"] == float("inf")
    assert np.allclose(sd.shrunk([1.0], [100], float("inf")), [0.0])


def test_swing_dry_run_planted_passes_null_does_not():
    r = sdlab.dry_run(log=lambda *a: None)
    assert r["dry_run_pass"]
    assert r["planted"]["verdict"] == "DEV PASS"
    assert r["null"]["verdict"] != "DEV PASS"
