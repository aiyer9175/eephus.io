# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The circularity guard's dry run on fixtures with nulls, and its planted recovery
(docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md part 4.4): an identity series
must read gap 0 and NON-INFERIOR; a series of pure noise must read not NON-INFERIOR.
No real data is read here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import ewar_core_label_guard as G  # noqa: E402


def test_registered_parameters():
    assert G.PREDICTOR_SEASONS == (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2021, 2022, 2023, 2024)
    assert 2019 not in G.PREDICTOR_SEASONS and 2020 not in G.PREDICTOR_SEASONS
    assert G.MIN_PA == 300.0 and G.BOOT == 2000 and G.SEED == 20261022 and G.MARGIN == -0.02
    assert G.GUARD_OUTCOMES == (("runs_scored", "hit"), ("runs_allowed", "hit"),
                                ("run_differential", "total"), ("wins", "total"))
    import swar_targets as T
    assert T.GUARD_SEED == 20261024 and T.GUARD_MARGIN == -0.02 and T.GUARD_Z == 1.645


def test_identity_series_holds_with_gap_zero():
    rec = G.run(G.FixtureInputs(noise=0.0), boot=60, log=lambda *a: None)
    assert rec["g1"]["gap"] == 0.0 and rec["g1"]["non_inferior"] is True
    assert rec["g2"]["non_inferior"] is True
    assert rec["verdict"]["guard_holds"] is True
    json.dumps(G._jsonable(rec), allow_nan=True)


def test_planted_noise_does_not_hold():
    rec = G.run(G.FixtureInputs(noise=3.0), boot=60, log=lambda *a: None)
    assert rec["g1"]["gap"] < -0.1 and rec["g1"]["non_inferior"] is False
    assert rec["verdict"]["guard_holds"] is False


def test_nulls_are_skipped_not_scored():
    fx = G.FixtureInputs(noise=0.0)
    pairs = G.hitter_pairs(fx.season_rows(), G.PREDICTOR_SEASONS, G.MIN_PA)
    assert all(p["war"] is not None and p["war1"] is not None for p in pairs)
    assert all(p["mlbam"] != 999999 for p in pairs)


def test_twin_permutes_within_season_only():
    rows = {2011: {"hit": {1: {"war": 1.0}, 2: {"war": 2.0}, 3: {"war": None}}},
            2012: {"hit": {1: {"war": 1.0}}}}
    deps = {(1, 2011): {"bat": 0.5}, (2, 2011): {"bat": -0.5}, (1, 2012): {"bat": 0.25}}
    tw = G.twin_departures(rows, deps, (2011, 2012), 1)
    assert sorted(v for (m, y), v in tw.items() if y == 2011) == [-0.5, 0.5]
    assert tw[(1, 2012)] == 0.25 and (3, 2011) not in tw


def test_weighted_within_matches_hand_value():
    s = np.array([1.0, 2.0, 3.0, 1.0, 2.0, 3.0])
    t = np.array([1.0, 2.0, 3.0, 3.0, 2.0, 1.0])
    season = np.array([1, 1, 1, 2, 2, 2])
    assert G.weighted_within(s, t, season) == 0.0
    assert abs(G.weighted_within(s[:3], t[:3], season[:3]) - 1.0) < 1e-12


def test_look_refuses_a_second_run(tmp_path, monkeypatch):
    rec = tmp_path / "guard.json"
    rec.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(G, "RECORD", rec)
    assert G.main(["--look"]) == 2
