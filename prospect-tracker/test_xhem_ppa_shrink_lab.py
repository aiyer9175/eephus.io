# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/xhem_ppa_shrink_lab.py: the construction of docs/ewar/XHEM_PPA_SHRINK_GATE.md
part 3, the pass rule of part 6 and the fixtures of part 7. Synthetic inputs only;
no cache is read."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import hem_plus  # noqa: E402
import xhem_ppa_shrink_lab as lab  # noqa: E402


def _line(pa=400.0, pitches=1560.0, ab=350.0, bb=40.0, ibb=2.0, hbp=4.0, sf=3.0, pos="LF"):
    return {"pa": pa, "pitches": pitches, "ab": ab, "bb": bb, "ibb": ibb, "hbp": hbp,
            "sf": sf, "pos": pos}


def test_frozen_constants_match_the_registration():
    assert lab.K_PPA == 100.0
    assert lab.K_UBB == hem_plus.K_UBB == 120.0
    assert lab.GAIN == hem_plus.HEM_SPREAD_GAIN
    assert lab.PRED_YEARS == (2016, 2017, 2018, 2021, 2022, 2023, 2024)
    assert lab.FIT_YEARS == (2013, 2014, 2015)
    assert (lab.B, lab.SEED, lab.PERM_SEED, lab.MDE_Z) == (2000, 20261015, 20261018, 1.645)
    assert lab.PAIR_MIN_PA == 200.0 and lab.SERVED_MIN_PA == 100.0
    assert all(y < 2026 for y in lab.SAVANT_YEARS + lab.PRED_YEARS + lab.FIT_YEARS)


def test_shrunk_xwoba_by_hand():
    ln = _line()
    lg = {"L": 3.9, "lgBB": 0.08}
    d = 350 + 40 - 2 + 3 + 4
    s = lab.sppa(ln, lg["L"])
    assert s == pytest.approx((1560 + 100 * 3.9) / (400 + 100))
    t = 0.08 + 0.12 * (s - 3.9)
    r_raw = 38 / d
    r_shr = (38 + 120 * t) / (d + 120)
    assert lab.shrunk_xwoba(0.330, ln, s, lg, 0.12, 0.69) == pytest.approx(0.330 + 0.69 * (r_shr - r_raw))


def test_walk_target_floors_at_zero():
    ln = _line(pitches=1000.0)
    lg = {"L": 3.9, "lgBB": 0.08}
    d = lab.denom(ln)
    got = lab.shrunk_xwoba(0.3, ln, 2.0, lg, 1.0, 0.69)
    assert got == pytest.approx(0.3 + 0.69 * (38 / (d + 120) - 38 / d))


def test_null_arm_is_the_served_xhem_plus_unrounded():
    sav = {1: (0.32, 0.34, 500.0), 2: (0.30, 0.29, 300.0), 3: (0.2, 0.5, 50.0)}
    lines = {1: _line(), 2: _line(pa=300.0, pitches=1100.0, ab=270.0, bb=20.0)}
    out = lab.season_arms(sav, lines, 0.69, 0.12, random.Random(1))
    pool = (0.34 * 500 + 0.29 * 300) / 800
    assert out["arms"]["N"][1] == pytest.approx(100 + hem_plus.HEM_SPREAD_GAIN * (100 * 0.34 / pool - 100))
    assert 3 not in out["arms"]["N"]            # under the served PA floor
    assert out["served_pool"] == 2 and out["served_pool_unjoined"] == 0


def test_unjoined_pool_hitter_keeps_his_xwoba_in_every_arm():
    sav = {1: (0.32, 0.34, 500.0), 2: (0.30, 0.29, 300.0)}
    lines = {1: _line(), 2: _line(pitches=0.0)}
    out = lab.season_arms(sav, lines, 0.69, 0.12, random.Random(1))
    assert out["served_pool_unjoined"] == 1
    for a in ("V", "P", "M"):
        assert out["arms"][a][2] - out["arms"]["N"][2] == pytest.approx(
            hem_plus.HEM_SPREAD_GAIN * 100 * 0.29 * (1 / out["pool_means"][a] - 1 / out["pool_means"]["N"]))


def test_slope_fit_is_pooled_within_season_and_skips_pitchers():
    rng = random.Random(3)
    by = {}
    for y in (2013, 2014, 2015):
        rows = {}
        for i in range(150):
            x = 3.6 + rng.random() * 0.6 + (0.1 if y == 2015 else 0.0)
            r = 0.02 + 0.2 * (x - 3.6)
            pa = 400.0
            d = 390.0
            u = r * d
            rows[i] = {"pa": pa, "pitches": x * pa, "ab": d - u, "bb": u, "ibb": 0.0, "hbp": 0.0,
                       "sf": 0.0, "pos": "C"}
        rows[999] = {"pa": 400.0, "pitches": 2000.0, "ab": 100.0, "bb": 290.0, "ibb": 0.0,
                     "hbp": 0.0, "sf": 0.0, "pos": "P"}
        by[y] = rows
    fit = lab.fit_slope(by)
    assert fit["b"] == pytest.approx(0.2, abs=1e-9)
    assert fit["n"] == 450


def test_slope_fit_refuses_a_thin_sample():
    with pytest.raises(lab.LabRefused):
        lab.fit_slope({2013: {1: _line(), 2: _line(pitches=1700.0, bb=60.0)}})


def _cell(lo):
    return {"lo95_gt_0": lo > 0}


@pytest.mark.parametrize("v1,v2,p1,p2,status", [
    (0.01, 0.01, -0.01, -0.01, "VALIDATED"),
    (0.01, 0.01, 0.01, -0.01, "VOID"),
    (0.01, 0.01, -0.01, 0.002, "VOID"),
    (0.01, -0.01, -0.01, -0.01, "PROVISIONAL"),
    (-0.01, 0.01, -0.01, -0.01, "PROVISIONAL"),
    (-0.01, -0.01, -0.01, -0.01, "NOT VALIDATED"),
    (0.0, 0.0, -0.01, -0.01, "NOT VALIDATED"),
])
def test_pass_rule(v1, v2, p1, p2, status):
    cells = {"v1": {"V": _cell(v1), "P": _cell(p1)}, "v2": {"V": _cell(v2), "P": _cell(p2)}}
    got = lab.verdict(cells)
    assert got["status"] == status
    assert got["builds_dark"] == (status == "VALIDATED")
    assert got["holm"]["k"] == 1


def test_nulls_fixture_runs_end_to_end_and_matches_the_harness():
    sav, lines, w, fit_lines = lab.fixture("nulls", n_players=160, seed=11)
    res = lab.core(sav, lines, w, fit_lines, boot=40, log=lambda *_: None)
    assert res["pairs"]["dropped_no_statsapi_line"] > 0
    for conv in ("v1", "v2"):
        for a in ("V", "P", "M"):
            c = res["results_by_convention"][conv][a]
            assert c["n_boot_draws"] == 40 and c["mde95_in_run"] is not None
    assert set(res["rho_by_predictor_season"]) == {str(y) for y in lab.PRED_YEARS}


def test_planted_signal_is_recovered():
    sav, lines, w, fit_lines = lab.fixture("planted", n_players=300, seed=5)
    res = lab.core(sav, lines, w, fit_lines, boot=60, log=lambda *_: None)
    cv = res["results_by_convention"]
    assert cv["v1"]["V"]["lo95_gt_0"] and cv["v2"]["V"]["lo95_gt_0"]


def test_permutation_is_deterministic():
    sav, lines, w, fit_lines = lab.fixture("planted", n_players=200, seed=2)
    a = lab.core(sav, lines, w, fit_lines, boot=10, log=lambda *_: None, assert_harness=False)
    b = lab.core(sav, lines, w, fit_lines, boot=10, log=lambda *_: None, assert_harness=False)
    assert a["results_by_convention"] == b["results_by_convention"]


def test_2026_is_refused():
    with pytest.raises(lab.LabRefused):
        lab.load_savant(2026)
    with pytest.raises(lab.LabRefused):
        lab.load_lines(2026)


def test_run_refuses_a_season_complete_override(monkeypatch, tmp_path):
    monkeypatch.setenv(lab.plh.SEASON_COMPLETE_ASOF_ENV, "2026:2026-10-01")
    with pytest.raises(lab.LabRefused):
        lab.run(tmp_path / "x.json", log=lambda *_: None)
    assert not (tmp_path / "x.json").exists()
