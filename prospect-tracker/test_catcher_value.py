# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Catcher value 2.0 (docs/ewar/CATCHER_VALUE_2_GATE.md) on synthetic fixtures with nulls:
WOWY is pitcher-matched, the planted fixture passes V-P and V-S, the null does not, the twin fails."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import catcher_value as cvl  # noqa: E402
import catcher_value_lab as cvlab  # noqa: E402

# catcher value 2.0 ----------------------------------------------------------------------


def test_wowy_is_pitcher_matched():
    pa = pd.DataFrame({"fld_team_id": [1] * 8, "catcher_id": [10, 10, 11, 11, 10, 10, 11, 11],
                       "pitcher_id": [1, 1, 1, 1, 2, 2, 2, 2],
                       "saved": [0.2, 0.2, 0.0, 0.0, 0.1, 0.1, 0.1, 0.1]})
    w, n = cvl.wowy(pa, 10, 1)
    assert n == 4 and np.isclose(w, 0.1)
    w2, _ = cvl.wowy(pa, 11, 1)
    assert np.isclose(w2, -0.1)


def test_catcher_dry_run_planted_passes_null_does_not():
    r = cvlab.dry_run(log=lambda *a: None)
    assert r["dry_run_pass"]


def test_catcher_twin_fails_on_a_planted_fixture():
    _, _, obs = cvlab.fixture(True)
    r = cvlab.v_s(obs, B=200)
    assert r["pass"] and r["twin_lo95"] <= 0
