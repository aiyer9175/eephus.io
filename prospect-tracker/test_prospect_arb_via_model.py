# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Prospect arbitration through the award model (owner answer 2026-09-25,
'more' batch 11, and OD-4 2026-09-30; census X02-05; docs/ARBITRATION_GATE.md
section 19).

A prospect's arbitration seasons are the /arbitration/ board's own rung
predictions, chained from a league-minimum start: ARB 1 through
arb_model.predict (stage1), ARB 2+ through arb_model.banded_predict, each
re-inflated at the deflator's carry-forward level and floored at the league
minimum, exactly as arb_export.build_board prices a forward rung. The
reference chain below calls arb_model itself on rows built the way the board
builds them, so the engine's arithmetic copy cannot drift from the model."""

from __future__ import annotations

import math

import numpy as np
import pytest

import arb_export
import arb_model as Mod
import salary_path
import surplus_backtest_real as sbr
import valuation_sets
import value_framework as vf

FAR_SEASON = 2031   # past the deflator's last award year: the carry-forward level


def _model():
    M = vf._arb_rung_model()
    assert M, "data/arb_prospect_rungs.json is missing"
    s1 = M["stage1"]
    stage1 = {"m": (np.asarray(s1["mu"], float), np.asarray(s1["sd"], float),
                    np.asarray(s1["w"], float), float(s1["b"])),
              "smear": float(s1["smear"]), "keys": list(s1["keys"])}
    banded = {"cells": {(int(a), int(b)): float(m) for a, b, m in M["banded"]["cells"]},
              "by_band": {int(b): float(m) for b, m in M["banded"]["by_band"]}}
    defl = {int(k): float(v) for k, v in M["deflator"].items()}
    return M, stage1, banded, defl


def _reference_chain(wars, super_two, role, age0, lm):
    """The board's walk (arb_export.build_board) on a prospect's path."""
    M, stage1, banded, defl = _model()
    pre_arb = vf._arb_ladder(vf._config()["service_time"], super_two)[0]
    out = []
    for t in range(len(wars)):
        if t < pre_arb:
            out.append(lm)
            continue
        step = t - pre_arb + 1
        plat = wars[t - 1] if t > 0 else 0.0
        prof = vf.arb_rung_profile(role, plat)
        row = {"mlbam": 1, "season": FAR_SEASON, "arb_year": step,
               "super_two": bool(super_two and step == 1),
               "prior_salary": out[t - 1], "war": plat,
               "war3": sum(wars[max(0, t - 3):t]), "career_war": sum(wars[:t]),
               "age": age0 + t, "pa": prof["pa"], "ipouts": prof["ipouts"], "gs": prof["gs"],
               "league_min": lm}
        metrics = {FAR_SEASON: {1: {"hem": prof["hem"], "sem": prof["sem"], "rem": prof["rem"]}}}
        if step == 1:
            d = Mod.predict(row, metrics, defl, stage1, None)
        else:
            d = Mod.banded_predict(row, banded, defl)
        pred = d * (defl.get(FAR_SEASON) or defl[max(defl)])
        out.append(max(pred, lm))
    return out


PATHS = ([2.0] * 7, [0.4, 1.1, 2.2, 3.0, 3.4, 3.1, 2.6], [5.5] * 7, [0.0, 0.2, 0.1, 0.3, 0.2, 0.0, 0.1])


@pytest.mark.parametrize("role", vf.ARB_ROLES)
@pytest.mark.parametrize("super_two", (False, True))
@pytest.mark.parametrize("wars", PATHS)
def test_prospect_arb_seasons_equal_the_model_rungs_from_a_league_minimum_start(role, super_two, wars):
    assert vf.arb_pricing() == "arb_model"
    lm = float(vf._config()["service_time"]["league_min_usd"])
    ref = _reference_chain(wars, super_two, role, 23.5, lm)
    got = vf._arb_model_salaries(wars, super_two, (role, 23.5), lambda t: lm)
    assert got == pytest.approx(ref, rel=1e-12)
    markets = [vf.tiered_war_value_usd(w) for w in wars]
    assert vf._service_path_salaries(wars, markets, super_two, profile=(role, 23.5)) == got
    pre_arb = vf._arb_ladder(vf._config()["service_time"], super_two)[0]
    # The first arbitration rung raises off a league-minimum season.
    assert got[:pre_arb] == [lm] * pre_arb
    assert all(s >= lm for s in got)


def test_the_artifact_is_the_boards_model_and_frame():
    M, stage1, _banded, _defl = _model()
    assert M["model"] == "arb_award_v1"
    assert M["frame"] == Mod.FRAME
    assert tuple(M["stage1"]["keys"]) == Mod.CHAMPION_KEYS
    assert M["banded"]["max_cut"] == arb_export.MAX_CUT
    assert [tuple(b) for b in M["banded"]["bands_usd"]] == [
        (lo, None if hi == float("inf") else hi) for lo, hi in Mod.SALARY_BANDS]
    for role in vf.ARB_ROLES:
        prof = M["profile"][role]
        assert prof["war"] == sorted(prof["war"]) and len(set(prof["war"])) == len(prof["war"])
        assert min(prof["n"]) >= arb_export.PROFILE_MIN_ROWS
    assert vf.arb_rung_profile("hit", 3.0)["ipouts"] == 0.0
    assert vf.arb_rung_profile("rp", 1.0)["gs"] < 5 < vf.arb_rung_profile("sp", 1.0)["gs"]


def test_the_clemens_set_prices_through_the_model_and_the_base_set_keeps_the_ladder():
    assert valuation_sets.engine_params("clemens_2026")["service_time"]["arb_pricing"] == "arb_model"
    with vf.valuation_set("prospx_current"):
        assert vf.arb_pricing() == "schedule"
        wars = [2.0] * 6
        markets = [vf.tiered_war_value_usd(w) for w in wars]
        assert (vf._service_path_salaries(wars, markets, False, profile=("hit", 24.0))
                == vf._service_path_salaries(wars, markets, False))
    assert vf.arb_pricing() == "arb_model"


def test_no_profile_keeps_the_ladder_under_the_model_set():
    wars = [2.0] * 7
    markets = [vf.tiered_war_value_usd(w) for w in wars]
    st = vf._config()["service_time"]
    pre_arb, fracs = vf._arb_ladder(st, False)
    lad = vf._service_path_salaries(wars, markets, False)
    lm = float(st["league_min_usd"])
    assert lad[pre_arb:] == [max(lm, f * markets[0]) for f in fracs]


def test_a_cold_tree_falls_back_to_the_ladder(monkeypatch, tmp_path):
    monkeypatch.setattr(vf, "_ARB_PROSPECT_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(vf, "_ARB_RUNGS", None)
    assert vf.arb_pricing() == "schedule"


def test_the_non_tender_option_matches_the_salary_path_rule():
    # salary_path.tender_cliff on undiscounted terms at r = 0 is the same
    # backward induction _cliff_sum runs on already-discounted terms.
    for d, cut in (([10, -1, -30], [False, True, True]),
                   ([10, -1, 30], [False, True, True]),
                   ([-5, 30, -40], [True, True, True]),
                   ([3, -2, -2, 5], [False, False, True, True])):
        assert vf._cliff_sum(d, cut) == pytest.approx(salary_path.tender_cliff(d, cut, r=0.0)[0])
    # A pre-arbitration season is never cut, so a negative one is carried.
    assert vf._cliff_sum([-3, 10], [False, False]) == 7


def test_the_remaining_path_from_zero_is_the_prospect_path():
    for role, rel in (("hitter", False), ("pitcher", False), ("pitcher", True)):
        wars = vf._bucket_season_wars(role, 3, rel, 23.0, 1.0)
        prof = (vf.arb_role(role, rel), 23.0)
        for s2 in (False, True):
            a = vf._remaining_path_surplus_usd(wars, 0, s2, profile=prof)
            b = vf._service_path_surplus_usd(wars, s2, 0.0, profile=prof)
            assert a == pytest.approx(b, rel=1e-12)


def test_a_bust_path_is_not_charged_arbitration_it_would_be_non_tendered():
    wars = [0.1] * 7
    prof = ("hit", 24.0)
    st = vf._config()["service_time"]
    pre_arb = vf._arb_ladder(st, False)[0]
    sal = vf._arb_model_salaries(wars, False, prof, lambda t: float(st["league_min_usd"]))
    assert all(s > vf.tiered_war_value_usd(0.1) for s in sal[pre_arb:])
    net = 1.0 / (1.0 + float(vf._config()["discount_rate"]))
    pre_only = sum((vf.tiered_war_value_usd(w) - sal[t]) * net ** t
                   for t, w in enumerate(wars[:pre_arb]))
    assert vf._service_path_surplus_usd(wars, False, 0.0, profile=prof) == pytest.approx(pre_only)


def test_the_realized_side_imputes_through_the_same_chain():
    war_by_year = {"2014": 0.8, "2015": 2.1, "2016": 3.0, "2017": 3.4, "2018": 2.2, "2019": 1.5}
    seasons = sbr._impute_seasons(war_by_year, 2014, profile=("sp", "1991-03-10"))
    cfg = vf._config()
    pre_arb = int(cfg["service_time"]["pre_arb_years"])
    lm = float(cfg["service_time"]["league_min_usd"])
    wars = [war_by_year[str(y)] for y in range(2014, 2020)]
    prior = lm
    for i, s in enumerate(seasons[pre_arb:], start=pre_arb):
        y = 2014 + i
        rung = vf.arb_rung_usd(i - pre_arb + 1, prior, role="sp", super_two=False,
                               war=wars[i - 1], war3=sum(wars[max(0, i - 3):i]),
                               career_war=sum(wars[:i]),
                               age=float(int(sbr._age_at("1991-03-10", f"{y}-06-30"))),
                               league_min_usd=lm)
        assert s.salary_mm == round(rung / 1e6, 3)
        prior = rung
    # Without a profile the ladder imputes, as the surplus-odds gate reads it.
    plain = sbr._impute_seasons(war_by_year, 2014)
    fr = cfg["service_time"]["arb_model"]["fractions_of_fa_value"]
    assert plain[pre_arb].salary_mm == round(fr[0] * vf.tiered_war_value_usd(wars[pre_arb]) / 1e6, 3)


def test_the_snapshot_publishes_the_model_cost_table():
    tbl = vf.arb_model_flat_cost_table()
    assert tbl and tbl["arb_years"] == 4 and len(tbl["war"]) == len(tbl["hit"])
    lm = float(vf._config()["service_time"]["league_min_usd"])
    n = int(vf._config()["service_time"]["control_years"])
    i = tbl["war"].index(3.0)
    sal = vf._arb_model_salaries([3.0] * n, False, ("sp", None), lambda t: lm)
    assert tbl["sp"][i] == round(sum(sal[3:]) / 1e6, 3)
    with vf.valuation_set("prospx_current"):
        assert vf.arb_model_flat_cost_table() is None


def test_the_output_path_and_its_reader_name_one_file():
    assert arb_export.PROSPECT_RUNGS_PATH.name == "arb_prospect_rungs.json"
    assert vf._ARB_PROSPECT_PATH.name == "arb_prospect_rungs.json"
    assert math.isfinite(vf._arb_rung_model()["_level"])


def test_served_surplus_stays_monotone_in_fv():
    """A prospect graded higher is never priced lower: FV 20 to 80 in half
    grades, both sides, starter and reliever tags, three timings."""
    for pit, pos in ((False, "SS"), (True, "SP"), (True, "RP")):
        for age, eta in ((19, 3.0), (22, 1.0), (None, None)):
            vals = [vf.surplus_value_mm(20 + 0.5 * i, pit, pos, age=age, eta_years=eta)
                    for i in range(121)]
            assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:])), (pos, age)
