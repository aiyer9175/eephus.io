# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline label check's guard: dry run on fixtures with nulls and its planted
recovery (docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md parts 4.4 and 4.5). An identity
series must read gap 0, hold, and match the registered structure; planted noise on the
hitting side must fail G-1; planted noise on the pitching side alone must fail G-2 (the
core guard's club leg kept pitchers on fWAR, this one carries the label there). No real
data is read here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import ewar_core_label_guard as C  # noqa: E402
import ewar_headline_label_guard as G  # noqa: E402


def _quiet(*a, **k):
    return None


def test_registered_parameters_are_the_core_guards():
    assert C.PREDICTOR_SEASONS == (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2021, 2022, 2023, 2024)
    assert C.MIN_PA == 300.0 and C.BOOT == 2000 and C.SEED == 20261022 and C.MARGIN == -0.02
    assert G.GATE_DOC == "docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md"
    assert G.RECORD.name == "ewar_headline_label_guard.json"


def test_identity_series_holds_and_matches_the_structure():
    rec = G.run(G.FixtureInputs(), boot=60, log=_quiet)
    assert rec["g1"]["gap"] == 0.0 and rec["g1"]["non_inferior"] is True
    assert rec["g1"]["twin"]["gap"] == 0.0
    assert rec["g2"]["holds"] is True
    assert rec["structure"]["holds"] is True
    assert rec["verdict"]["guard_holds"] is True and rec["verdict"]["switch_cleared"] is True
    json.dumps(C._jsonable(rec), allow_nan=True)


def test_planted_hitting_noise_fails_g1_and_the_structure():
    rec = G.run(G.FixtureInputs(noise=3.0), boot=60, log=_quiet)
    assert rec["g1"]["gap"] < -0.1 and rec["g1"]["non_inferior"] is False
    assert rec["verdict"]["guard_holds"] is False
    assert rec["structure"]["holds"] is False and rec["verdict"]["switch_cleared"] is False


def test_planted_pitching_noise_fails_g2():
    rec = G.run(G.FixtureInputs(pit_noise=3.0), boot=60, log=_quiet)
    assert rec["g1"]["gap"] == 0.0
    assert rec["g2"]["n_departing_cells"] > 0
    assert rec["g2"]["holds"] is False
    assert rec["verdict"]["guard_holds"] is False and rec["verdict"]["switch_cleared"] is False


def test_structure_check_reads_exact_zeros_only():
    g1 = {"gap": 0.0, "twin": {"gap": 0.0}, "n_pairs_departing": 0}
    g2 = {"n_departing_cells": 0, "outcomes": {"wins": {"dT": 0.0}}}
    assert G.structure_check(g1, g2)["holds"] is True
    assert G.structure_check(dict(g1, gap=1e-12), g2)["holds"] is False
    assert G.structure_check(g1, {"n_departing_cells": 0, "outcomes": {"wins": {"dT": 1e-9}}})["holds"] is False
    assert G.structure_check(g1, {"n_departing_cells": 0, "outcomes": {}})["holds"] is False


def test_look_refuses_a_second_run(tmp_path, monkeypatch):
    rec = tmp_path / "guard.json"
    rec.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(G, "RECORD", rec)
    assert G.main(["--look"]) == 2
