# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PJ-C component scorer (proj_eval.run_components, task PJ_3_COMPONENT_SCORER,
docs/PROJ_COMPONENTS_GATE.md sections 3 to 5): the dry run on fixtures with
nulls the look requires first, the frame guards, the hand-computed statistics,
the H0 / P0 exposure test and the seeded bootstrap. Every frame here is a
fixture; the scorer is never run on real data by this file."""

from __future__ import annotations

import json

import pytest

import proj_eval as pe

SEED = 20261124


def _row(mlbam, base=2016, h=1, side="hit", exposure=600.0, labels=None,
         exposure_base=550.0, exposure_hist=None, **extra):
    r = {"mlbam": mlbam, "side": side, "base": base, "h": h,
         "label_season": base + h - 1, "exposure": exposure,
         "exposure_base": exposure_base, "labels": labels or {}}
    if exposure_hist is not None:
        r["exposure_hist"] = exposure_hist
    r.update(extra)
    return r


# --- the hand-computed rate fixture ------------------------------------------
# P1: 600 PA, 3.0 BsR runs (rate 3.0 per 600), star (550 PA in B - 1)
# P2: 300 PA, -1.5 runs (rate -3.0 per 600), not star (200 PA in B - 1)
# P3: absent season (0 PA), pooled actual 0 runs
_CAND = {1: {"rate": 2.0, "exposure": 550.0, "p10": 0.0, "p90": 4.0},
         2: {"rate": -1.0, "exposure": 400.0, "p10": 0.0, "p90": 2.0},
         3: {"rate": 1.0, "exposure": 300.0, "p10": -1.0, "p90": 1.0}}
_NAIVE = {1: 4.0, 2: 0.0, 3: 0.5}


def _rate_frame():
    return [
        _row(1, exposure=600.0, labels={"bsr": 3.0}, exposure_base=550.0),
        _row(2, exposure=300.0, labels={"bsr": -1.5}, exposure_base=200.0),
        _row(3, exposure=0.0, labels={"bsr": None}, exposure_base=100.0),
    ]


def _rate_report(**kw):
    return pe.run_components(
        _rate_frame(), {"bsr": lambda r: _CAND[r["mlbam"]]},
        {"bsr": {"naive": lambda r: _NAIVE[r["mlbam"]],
                 "implicit": lambda r: 0.0}},
        [(2016, 1)], SEED, B=200, **kw)


def test_hand_computed_rate_statistics():
    c = _rate_report()["components"]["bsr"]["horizons"][1]
    assert (c["n"], c["n_survived"], c["n_star"]) == (3, 2, 1)
    # exposure-weighted rate MAE on survived rows: (600*1 + 300*2) / 900
    assert c["mae"] == pytest.approx(1.3333, abs=1e-4)
    assert c["bias"] == pytest.approx(0.0, abs=1e-9)
    assert c["mae_star"] == pytest.approx(1.0)
    # runs MAE at projected exposure, pooled (absent = 0 runs) and survived
    assert c["runs_mae"] == pytest.approx(0.8333, abs=1e-4)
    assert c["runs_mae_survived"] == pytest.approx(1.0, abs=1e-4)
    # 80% range coverage on season runs: P1 in, P2 out, P3 (0 runs) in
    assert c["coverage"] == pytest.approx(0.6667, abs=1e-4)
    assert c["coverage_survived"] == pytest.approx(0.5)
    assert c["pinball_q10"] is not None and c["pinball_q90"] is not None
    naive, implicit = c["comparators"]["naive"], c["comparators"]["implicit"]
    assert naive["mae"] == pytest.approx(1.6667, abs=1e-4)
    assert implicit["mae"] == pytest.approx(3.0)
    assert naive["pooled"]["delta"] == pytest.approx(-0.3333, abs=1e-4)
    assert implicit["pooled"]["delta"] == pytest.approx(-1.6667, abs=1e-4)
    assert naive["pooled"]["n_players"] == 2      # survived rows only


def test_upper_bound_and_mde_apply_the_vif():
    rep = _rate_report(vif=1.8)
    blk = rep["components"]["bsr"]["horizons"][1]["comparators"]["naive"]["pooled"]
    mde = 1.645 * blk["sd"] * 1.8
    assert blk["mde95"] == pytest.approx(mde, abs=1e-4)
    assert blk["ub95"] == pytest.approx(blk["delta"] + mde, abs=2e-4)
    rep1 = _rate_report(vif=1.0)
    blk1 = rep1["components"]["bsr"]["horizons"][1]["comparators"]["naive"]["pooled"]
    assert blk1["sd"] == blk["sd"]                 # the VIF never touches the draws
    assert blk["mde95"] == pytest.approx(blk1["mde95"] * 1.8, abs=2e-4)


def test_dry_run_with_nulls_never_crashes_and_prints_na():
    """The look's reporting path dry-run (section 5): a cell with zero rows,
    a component missing for every row, a comparator returning None, a player
    with one season."""
    frame = [
        # fld_pos label missing on every survived row
        _row(10, labels={"bsr": 1.0, "fld_pos": None}, exposure_base=300.0),
        _row(11, labels={"bsr": -0.5, "fld_pos": None}, exposure=250.0,
             exposure_base=300.0),
        # a pitcher whose RA9-gap comparator returns None
        _row(20, side="pit", exposure=150.0, exposure_base=160.0,
             labels={"ra9_gap": 2.0}),
        # a player with one season of history (PA test)
        _row(30, exposure=420.0, exposure_hist={2015: 300.0}),
    ]
    preds = {
        "bsr": lambda r: 0.5,
        "fld_pos": lambda r: {"rate": 1.0, "exposure": 500.0},
        "ra9_gap": lambda r: {"rate": 0.0},
        "pa": lambda r: {"exposure": 400.0} if r.get("exposure_hist") else None,
    }
    comps = {
        "bsr": {"naive": lambda r: 0.0, "implicit": lambda r: 0.0},
        "fld_pos": {"naive": lambda r: 0.0, "implicit": lambda r: 0.0},
        "ra9_gap": {"naive": lambda r: None, "implicit": lambda r: 0.0},
    }
    # (2016, 3) holds no row at all
    rep = pe.run_components(frame, preds, comps, [(2016, 1), (2016, 3)], SEED, B=100)
    C = rep["components"]
    assert C["bsr"]["horizons"][3]["n"] == 0
    assert C["fld_pos"]["horizons"][1]["n"] == 0
    assert C["fld_pos"]["horizons"][1]["n_dropped"] == {"no_label": 3}
    assert C["ra9_gap"]["horizons"][1]["n"] == 0
    assert C["ra9_gap"]["horizons"][1]["n_dropped"] == {"comparator:naive": 1}
    pa = C["pa"]["horizons"][1]
    assert pa["n"] == 1 and pa["n_dropped"] == {"no_candidate": 2}
    one = pa["comparators"]["prior_season"]["pooled"]
    # one player: no spread to measure, so no bound rather than a zero sd
    assert one["n_players"] == 1 and one["sd"] is None
    assert one["ub95"] is None and one["mde95"] is None and one["delta"] == -100.0
    text = pe.format_components_report(rep)
    assert "n/a (n=0)" in text
    for comp in ("bsr", "fld_pos", "ra9_gap", "pa"):
        assert comp in text
    # survived rows exist but no star row: the star slice prints n/a (n=0)
    assert "star n 0 MAE n/a (n=0)" in text
    json.dumps(rep)                                  # the report serialises


def test_exposure_test_against_prior_season_and_543():
    """H0's registered exposure test (section 4.3): exposure MAE on survived
    rows against the prior-season and the 5/4/3 three-season exposure, the
    built-in comparators, on identical rows."""
    frame = [
        _row(1, exposure=550.0, exposure_hist={2015: 600, 2014: 500, 2013: 400}),
        _row(2, exposure=450.0, exposure_hist={2015: 200}),          # one season
        _row(3, exposure=0.0, exposure_hist={"2014": 400}),          # absent, str keys
    ]
    pred = {1: 580.0, 2: 300.0, 3: 350.0}
    rep = pe.run_components(frame, {"pa": lambda r: pred[r["mlbam"]]}, {},
                            [(2016, 1)], SEED, B=200)
    blk = rep["components"]["pa"]
    assert blk["kind"] == "exposure" and blk["unit"] == "PA"
    assert blk["comparators"] == ["prior_season", "w543"]
    c = blk["horizons"][1]
    assert (c["n"], c["n_survived"]) == (3, 2)
    assert c["mae"] == pytest.approx(90.0)                   # (30 + 150) / 2
    assert c["comparators"]["prior_season"]["mae"] == pytest.approx(150.0)
    assert c["comparators"]["w543"]["mae"] == pytest.approx((100 / 3 + 250) / 2, abs=1e-3)
    assert c["comparators"]["prior_season"]["pooled"]["delta"] == pytest.approx(-60.0)
    assert pe._exposure_prior_season(frame[2]) == 0.0       # no B - 1 season
    assert pe._exposure_543(frame[2]) == pytest.approx(400.0)
    assert pe._exposure_543(_row(9, exposure_hist={})) is None
    assert pe._exposure_prior_season(_row(9)) is None       # history unknown


def test_ip_exposure_test_uses_the_pitcher_star_floor():
    frame = [_row(1, side="pit", exposure=130.0, exposure_base=125.0,
                  exposure_hist={2015: 125.0}),
             _row(2, side="pit", exposure=60.0, exposure_base=70.0,
                  exposure_hist={2015: 70.0, 2014: 40.0})]
    rep = pe.run_components(frame, {"ip": lambda r: 100.0}, {}, [(2016, 1)], SEED, B=50)
    c = rep["components"]["ip"]["horizons"][1]
    assert c["n_star"] == 1 and rep["components"]["ip"]["unit"] == "IP"


def test_seeded_bootstrap_is_reproducible():
    import random
    rnd = random.Random(7)
    deltas = {p: [(rnd.uniform(-2, 1), rnd.uniform(50, 650)) for _ in range(3)]
              for p in range(40)}
    a = pe._paired_cluster_bootstrap(deltas, 1000, SEED)
    b = pe._paired_cluster_bootstrap(deltas, 1000, SEED)
    c = pe._paired_cluster_bootstrap(deltas, 1000, SEED + 1)
    assert a == b
    assert a["sd"] != c["sd"] and a["point"] == c["point"]
    num = sum(d * w for rows in deltas.values() for d, w in rows)
    den = sum(w for rows in deltas.values() for _d, w in rows)
    assert a["point"] == pytest.approx(num / den)
    assert (a["n_players"], a["n_rows"], a["B"], a["seed"]) == (40, 120, 1000, SEED)
    # unweighted floats, an empty map and a player with no usable row
    single = pe._paired_cluster_bootstrap({1: [1.0, 3.0]}, 10, SEED)
    assert single["point"] == 2.0 and single["sd"] is None
    empty = pe._paired_cluster_bootstrap({}, 10, SEED)
    assert empty["point"] is None and empty["sd"] is None
    assert pe._paired_cluster_bootstrap({1: [None], 2: []}, 10, SEED)["n_players"] == 0


def test_dev_guard_refuses_label_seasons_above_2021():
    with pytest.raises(ValueError, match="above 2021"):
        _scorer_on_cells([(2021, 2)])
    with pytest.raises(ValueError, match="excluded"):
        _scorer_on_cells([(2019, 2)])                        # label season 2020
    with pytest.raises(ValueError, match="horizon"):
        _scorer_on_cells([(2016, 6)])
    _scorer_on_cells([(2014, 1), (2017, 5), (2021, 1)])      # DEV cells are fine


def _scorer_on_cells(cells, **kw):
    return pe.run_components([], {"bsr": lambda r: 0.0},
                             {"bsr": {"naive": lambda r: 0.0}}, cells, SEED,
                             B=10, **kw)


def test_look_guard_one_look_and_no_2026(tmp_path, monkeypatch):
    monkeypatch.setattr(pe, "DATA_DIR", tmp_path)
    with pytest.raises(ValueError, match="never"):
        _scorer_on_cells([(2025, 2)], look=True)              # label season 2026
    # no artifact yet: the holdout cells may be read once
    rep = _scorer_on_cells([(2022, 4), (2024, 2)], look=True)
    assert rep["look"] is True and rep["label_seasons"] == [2025]
    art = tmp_path / pe.COMPONENTS_EVAL_NAME
    art.write_text(json.dumps({"dev": {}}), encoding="utf-8")
    _scorer_on_cells([(2022, 1)], look=True)                  # dev block only: fine
    art.write_text(json.dumps({"dev": {}, "holdout": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="runs once"):
        _scorer_on_cells([(2022, 1)], look=True)
    art.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="unparseable"):
        _scorer_on_cells([(2022, 1)], look=True)


def test_no_war_residual_is_ever_computed():
    frame = [_row(1, labels={"bsr": 1.0})]
    with pytest.raises(ValueError, match="war"):
        pe.run_components(frame, {"bsr": lambda r: {"rate": 1.0, "war": 2.0}},
                          {"bsr": {"naive": lambda r: 0.0}}, [(2016, 1)], SEED, B=10)
    with pytest.raises(ValueError, match="war"):
        pe.run_components(frame, {"bsr": lambda r: 1.0},
                          {"bsr": {"naive": lambda r: {"WAR": 0.0}}},
                          [(2016, 1)], SEED, B=10)
    with pytest.raises(ValueError, match="war"):
        pe.run_components(frame, {"war": lambda r: 1.0},
                          {"war": {"naive": lambda r: 0.0}}, [(2016, 1)], SEED, B=10)
    assert "war" not in {k.lower() for k in pe.COMPONENT_SPECS}


def test_rows_outside_the_cells_never_reach_a_predictor():
    seen = []

    def pred(r):
        seen.append((r["mlbam"], r["base"]))
        return 0.0
    frame = [_row(1, labels={"bsr": 1.0}),
             _row(2, base=2022, labels={"bsr": 9.0})]          # a holdout row
    pe.run_components(frame, {"bsr": pred}, {"bsr": {"naive": lambda r: 0.0}},
                      [(2016, 1)], SEED, B=10)
    assert seen == [(1, 2016)]


def test_contract_errors_are_loud():
    frame = [_row(1, labels={"bsr": 1.0})]
    with pytest.raises(ValueError, match="unknown component"):
        pe.run_components(frame, {"speed": lambda r: 0.0},
                          {"speed": {"naive": lambda r: 0.0}}, [(2016, 1)], SEED)
    with pytest.raises(ValueError, match="no comparator"):
        pe.run_components(frame, {"bsr": lambda r: 0.0}, {}, [(2016, 1)], SEED)
    with pytest.raises(ValueError, match="base \\+ h - 1"):
        bad = _row(1, labels={"bsr": 1.0})
        bad["label_season"] = 2019
        pe.run_components([bad], {"bsr": lambda r: 0.0},
                          {"bsr": {"naive": lambda r: 0.0}}, [(2016, 1)], SEED)
